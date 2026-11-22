"""Handlers dos jobs de leitura.

Cada handler roda dentro de uma sessão de banco já transacional e devolve o
``result`` do job. Nada aqui abre transação própria: o worker é quem grava
sucesso/falha, junto com a eventual mudança de estado da conta.
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import Cipher
from app.core.time import utcnow
from app.db.models import IgAccount, IgAccountStatus, InsightsSnapshot, Job, MediaAsset
from app.jobs.payloads import (
    AccountHealthPayload,
    InsightsAccountPayload,
    MediaDownloadPayload,
    MediaListPayload,
)
from app.services.ig_gateway import IgGateway, IgGatewayError
from app.services.storage import MediaStorage, content_type_for

logger = logging.getLogger(__name__)


class JobError(Exception):
    """Falha de negócio do job, já sanitizada para resposta/log."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        account_status: str | None = None,
        clear_session: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.account_status = account_status
        self.clear_session = clear_session


@dataclass
class JobContext:
    db: Session
    job: Job
    account: IgAccount
    cipher: Cipher
    gateway: IgGateway
    storage: MediaStorage


def _session(ctx: JobContext) -> tuple[dict[str, Any], str | None]:
    if ctx.account.status != IgAccountStatus.ACTIVE:
        raise JobError(
            "account_not_active",
            "A conta não está ativa; faça login antes de enfileirar operações.",
        )
    if not ctx.account.session_enc:
        raise JobError(
            "account_no_session", "A conta não tem sessão salva; faça login primeiro."
        )
    try:
        session = ctx.cipher.decrypt_json(ctx.account.session_enc)
        proxy = (
            ctx.cipher.decrypt(ctx.account.proxy_enc)
            if ctx.account.proxy_enc
            else None
        )
    except Exception as exc:  # noqa: BLE001 - segredo corrompido/chave ausente
        logger.warning(
            "job_session_decrypt_failed job_id=%s account_id=%s",
            ctx.job.id,
            ctx.account.id,
        )
        raise JobError(
            "invalid_session_payload",
            "A sessão salva não pôde ser lida; faça login novamente.",
            account_status=IgAccountStatus.NEEDS_REAUTH,
            clear_session=True,
        ) from exc
    return session, proxy


def _gateway_call(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except IgGatewayError as exc:
        raise JobError(
            exc.code,
            exc.message,
            retryable=exc.retryable,
            account_status=exc.account_status,
            clear_session=exc.account_status == IgAccountStatus.NEEDS_REAUTH,
        ) from exc


def asset_summary(asset: MediaAsset) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "media_pk": asset.media_pk,
        "kind": asset.kind,
        "size_bytes": asset.size_bytes,
        "content_type": asset.content_type,
    }


def handle_media_list(ctx: JobContext) -> dict[str, Any]:
    payload = MediaListPayload.model_validate(ctx.job.payload)
    session, proxy = _session(ctx)
    username = payload.username or ctx.account.username
    items = _gateway_call(
        lambda: ctx.gateway.media_list(
            username=username,
            amount=payload.amount,
            proxy=proxy,
            session=session,
        )
    )
    return {
        "username": username,
        "items": items,
        "fetched_at": utcnow().isoformat(),
    }


def handle_media_download(ctx: JobContext) -> dict[str, Any]:
    payload = MediaDownloadPayload.model_validate(ctx.job.payload)
    existing = list(
        ctx.db.scalars(
            select(MediaAsset).where(
                MediaAsset.account_id == ctx.account.id,
                MediaAsset.media_pk == payload.media_pk,
                MediaAsset.kind.in_(payload.kinds),
            )
        )
    )
    by_kind = {asset.kind: asset for asset in existing}
    if len(by_kind) == len(payload.kinds):
        return {
            "media_pk": payload.media_pk,
            "assets": [asset_summary(asset) for asset in existing],
            "cached": True,
        }

    session, proxy = _session(ctx)
    with tempfile.TemporaryDirectory(prefix="instarix-media-") as tmp:
        downloaded = _gateway_call(
            lambda: ctx.gateway.media_download(
                media_pk=payload.media_pk,
                kinds=payload.kinds,
                proxy=proxy,
                session=session,
                folder=Path(tmp),
            )
        )
        if not downloaded:
            raise JobError(
                "media_not_downloadable",
                "Nenhum arquivo compatível foi encontrado para esse post.",
            )

        for item in downloaded:
            if item.kind in by_kind:
                continue
            key = (
                f"{ctx.account.tenant_id}/{ctx.account.id}/"
                f"{payload.media_pk}_{item.kind}{item.path.suffix.lower()}"
            )
            size = ctx.storage.save(item.path, key)
            asset = MediaAsset(
                tenant_id=ctx.account.tenant_id,
                account_id=ctx.account.id,
                media_pk=payload.media_pk,
                kind=item.kind,
                storage_key=key,
                size_bytes=size,
                content_type=content_type_for(item.path),
            )
            ctx.db.add(asset)
            ctx.db.flush()
            by_kind[item.kind] = asset

    return {
        "media_pk": payload.media_pk,
        "assets": [asset_summary(asset) for asset in by_kind.values()],
        "cached": False,
    }


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def handle_insights_account(ctx: JobContext) -> dict[str, Any]:
    InsightsAccountPayload.model_validate(ctx.job.payload)
    session, proxy = _session(ctx)
    data = _gateway_call(
        lambda: ctx.gateway.insights_account(proxy=proxy, session=session)
    )
    now = utcnow()
    snapshot = InsightsSnapshot(
        tenant_id=ctx.account.tenant_id,
        account_id=ctx.account.id,
        data=_jsonable(data),
        captured_at=now,
    )
    ctx.db.add(snapshot)
    ctx.db.flush()
    return {"snapshot_id": str(snapshot.id), "captured_at": now.isoformat()}


def handle_account_health(ctx: JobContext) -> dict[str, Any]:
    AccountHealthPayload.model_validate(ctx.job.payload)
    session, proxy = _session(ctx)
    outcome = _gateway_call(
        lambda: ctx.gateway.health(
            username=ctx.account.username,
            proxy=proxy,
            session=session,
        )
    )
    now = utcnow()
    ctx.account.last_health_at = now
    if outcome.status == "ok":
        return {"status": "ok"}
    if outcome.status == "unavailable":
        # Falha de rede/5xx não invalida a sessão: o job pode ser repetido.
        raise JobError(
            "instagram_unavailable",
            "Falha temporária ao falar com o Instagram.",
            retryable=True,
        )

    ctx.account.status = IgAccountStatus.NEEDS_REAUTH
    ctx.account.session_enc = None
    ctx.account.last_error_code = "account_needs_reauth"
    ctx.account.last_error_message = "A sessão salva foi recusada pelo Instagram."
    return {"status": "needs_reauth"}


HANDLERS: dict[str, Callable[[JobContext], dict[str, Any]]] = {
    "media.list": handle_media_list,
    "media.download": handle_media_download,
    "insights.account": handle_insights_account,
    "account.health": handle_account_health,
}
