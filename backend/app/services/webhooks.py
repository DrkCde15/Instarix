"""Webhooks de saída com HMAC, retry e backoff."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import random
import secrets
import socket
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol
from urllib.parse import SplitResult, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import Cipher
from app.core.errors import AppError, not_found
from app.core.time import utcnow
from app.db.models import IgAccount, WebhookDelivery, WebhookEndpoint, WebhookStatus

logger = logging.getLogger(__name__)

EVENT_JOB_SUCCEEDED = "job.succeeded"
EVENT_JOB_FAILED = "job.failed"
WEBHOOK_EVENTS = frozenset({EVENT_JOB_SUCCEEDED, EVENT_JOB_FAILED})


class WebhookSendError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class WebhookNotifier(Protocol):
    def send(
        self, url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> int: ...


def _connect_pinned(address: str, port: int, timeout: float | None) -> socket.socket:
    """Conecta direto no IP já validado, sem nova consulta DNS."""
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
    except OSError:
        sock.close()
        raise
    return sock


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection presa ao IP validado, imune a DNS rebinding."""

    def __init__(
        self, host: str, port: int, *, resolved_ip: str, timeout: float | None
    ) -> None:
        super().__init__(host, port, timeout=timeout)
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        self.sock = _connect_pinned(self._resolved_ip, self.port, self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS presa ao IP validado, mantendo SNI e validação de certificado."""

    def __init__(
        self, host: str, port: int, *, resolved_ip: str, timeout: float | None
    ) -> None:
        super().__init__(host, port, timeout=timeout)
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        sock = _connect_pinned(self._resolved_ip, self.port, self.timeout)
        try:
            # server_hostname mantém o certificado vinculado ao hostname.
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


class HttpWebhookNotifier:
    """POST com http.client, sem redirects e com o IP pinado.

    A URL é resolvida uma única vez e a conexão usa o IP já validado. Assim,
    uma segunda resposta DNS (DNS rebinding) não desvia a requisição para a
    rede interna entre a validação e o envio. Redirects nunca são seguidos.
    """

    def send(
        self, url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> int:
        try:
            target = resolve_webhook_target(url)
        except AppError as exc:
            raise WebhookSendError("webhook_url_blocked", exc.message) from exc

        connection_cls = (
            _PinnedHTTPSConnection if target.scheme == "https" else _PinnedHTTPConnection
        )
        connection = connection_cls(
            target.host, target.port, resolved_ip=target.ip, timeout=timeout
        )
        try:
            connection.request("POST", target.path, body=body, headers=headers)
            response = connection.getresponse()
            return int(response.status)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise WebhookSendError(
                "webhook_send_error", "Não foi possível entregar o webhook."
            ) from exc
        finally:
            connection.close()


def sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def validate_events(events: list[str]) -> list[str]:
    normalized = sorted(set(events))
    unknown = sorted(set(normalized) - WEBHOOK_EVENTS)
    if unknown:
        raise AppError(
            422,
            "invalid_webhook_event",
            f"Eventos desconhecidos: {', '.join(unknown)}.",
        )
    if not normalized:
        raise AppError(422, "invalid_webhook_event", "Informe ao menos um evento.")
    return normalized


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Só aceita endereços globais (exclui privado, loopback, CGNAT, etc.)."""
    return address.is_global


def _url_port(parts: SplitResult) -> int:
    try:
        return parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise AppError(
            422, "invalid_webhook_url", "Porta inválida na URL do webhook."
        ) from exc


def _resolve_public_address(host: str, port: int) -> str:
    """Resolve o host uma única vez e devolve um IP global validado."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AppError(
            422,
            "invalid_webhook_url",
            "Não foi possível resolver o host do webhook.",
        ) from exc
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise AppError(
            422,
            "invalid_webhook_url",
            "Não foi possível resolver o host do webhook.",
        )
    if any(not _is_public(ipaddress.ip_address(address)) for address in addresses):
        raise AppError(
            422,
            "invalid_webhook_url",
            "O host do webhook resolve para um IP não permitido.",
        )
    return addresses[0]


def validate_webhook_url(url: str, *, resolve: bool = False) -> str:
    url = url.strip()
    if len(url) > 2048:
        raise AppError(422, "invalid_webhook_url", "URL do webhook é muito longa.")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise AppError(422, "invalid_webhook_url", "URL do webhook inválida.") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AppError(
            422, "invalid_webhook_url", "A URL deve ser http(s) com host."
        )
    if parts.username or parts.password:
        raise AppError(
            422, "invalid_webhook_url", "A URL não pode conter credenciais."
        )
    _url_port(parts)  # valida a porta mesmo sem resolver o DNS
    host = parts.hostname.lower()
    if (
        host in {"localhost", "localhost.localdomain"}
        or host.endswith(".local")
        or host.endswith(".internal")
    ):
        raise AppError(422, "invalid_webhook_url", "Host de webhook não permitido.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not resolve:
            return url
        _resolve_public_address(host, _url_port(parts))
        return url
    if not _is_public(address):
        raise AppError(422, "invalid_webhook_url", "IP de webhook não permitido.")
    return url


@dataclass(frozen=True)
class WebhookTarget:
    """Destino de entrega com o IP já resolvido e validado."""

    url: str
    scheme: str
    host: str
    port: int
    path: str
    ip: str


def resolve_webhook_target(url: str) -> WebhookTarget:
    """Valida a URL e resolve o IP exatamente uma vez, para pinar a conexão."""
    url = validate_webhook_url(url)
    parts = urlsplit(url)
    host = parts.hostname.lower()  # type: ignore[union-attr]
    port = _url_port(parts)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        ip = _resolve_public_address(host, port)
    else:
        ip = str(address)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return WebhookTarget(
        url=url,
        scheme=parts.scheme,
        host=host,
        port=port,
        path=path,
        ip=ip,
    )


def manychat_payload(db: Session, delivery: WebhookDelivery) -> dict[str, Any]:
    """Converte o payload do job para o formato de webhook do ManyChat.

    O payload original continua gravado em ``delivery.payload`` para auditoria;
    aqui só montamos o corpo enviado ao endpoint do cliente.
    """
    data = delivery.payload or {}
    account_id = data.get("account_id")
    account: IgAccount | None = None
    if account_id:
        try:
            account = db.scalar(
                select(IgAccount).where(
                    IgAccount.id == uuid.UUID(str(account_id)),
                    IgAccount.tenant_id == delivery.tenant_id,
                    IgAccount.deleted_at.is_(None),
                )
            )
        except (ValueError, TypeError, AttributeError):
            account = None

    return {
        "subscriber_id": str(account_id or ""),
        "channel": "INSTAGRAM",
        "name": account.label if account else str(account_id or ""),
        "username": account.username if account else "",
        "event": delivery.event,
        "custom_fields": {
            "job_id": data.get("job_id"),
            "account_id": account_id,
            "type": data.get("type"),
            "status": data.get("status"),
            "error_code": data.get("error_code"),
        },
    }


class WebhookService:
    def __init__(self, db: Session, cipher: Cipher, settings: Settings) -> None:
        self.db = db
        self.cipher = cipher
        self.settings = settings

    def create(
        self,
        tenant_id: uuid.UUID,
        *,
        url: str,
        events: list[str],
    ) -> tuple[WebhookEndpoint, str]:
        raw_secret = secrets.token_urlsafe(32)
        endpoint = WebhookEndpoint(
            tenant_id=tenant_id,
            url=validate_webhook_url(url),
            secret_enc=self.cipher.encrypt(raw_secret),
            events=validate_events(events),
            is_active=True,
        )
        self.db.add(endpoint)
        self.db.commit()
        return endpoint, raw_secret

    def list(self, tenant_id: uuid.UUID) -> list[WebhookEndpoint]:
        return list(
            self.db.scalars(
                select(WebhookEndpoint)
                .where(
                    WebhookEndpoint.tenant_id == tenant_id,
                    WebhookEndpoint.deleted_at.is_(None),
                )
                .order_by(WebhookEndpoint.created_at.desc())
            )
        )

    def get(self, tenant_id: uuid.UUID, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        endpoint = self.db.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.deleted_at.is_(None),
            )
        )
        if endpoint is None:
            raise not_found("webhook_not_found", "Webhook não encontrado.")
        return endpoint

    def delete(self, tenant_id: uuid.UUID, endpoint_id: uuid.UUID) -> None:
        endpoint = self.get(tenant_id, endpoint_id)
        endpoint.deleted_at = utcnow()
        endpoint.is_active = False
        self.db.commit()

    def deliveries(
        self, tenant_id: uuid.UUID, endpoint_id: uuid.UUID, limit: int = 100
    ) -> list[WebhookDelivery]:
        self.get(tenant_id, endpoint_id)
        return list(
            self.db.scalars(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.tenant_id == tenant_id,
                    WebhookDelivery.endpoint_id == endpoint_id,
                )
                .order_by(WebhookDelivery.created_at.desc())
                .limit(limit)
            )
        )

    def enqueue_event(
        self,
        tenant_id: uuid.UUID,
        event: str,
        payload: dict[str, Any],
    ) -> int:
        endpoints = self.db.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.is_active.is_(True),
                WebhookEndpoint.deleted_at.is_(None),
            )
        )
        created = 0
        for endpoint in endpoints:
            if event not in (endpoint.events or []):
                continue
            self.db.add(
                WebhookDelivery(
                    tenant_id=tenant_id,
                    endpoint_id=endpoint.id,
                    event=event,
                    payload=payload,
                    status=WebhookStatus.PENDING,
                    attempts=0,
                    max_attempts=self.settings.webhook_max_attempts,
                    next_attempt_at=utcnow(),
                )
            )
            created += 1
        return created

    def deliver_due(
        self,
        notifier: WebhookNotifier | None = None,
        *,
        limit: int = 20,
    ) -> int:
        notifier = notifier or HttpWebhookNotifier()
        now = utcnow()
        deliveries = list(
            self.db.scalars(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.status == WebhookStatus.PENDING,
                    WebhookDelivery.next_attempt_at <= now,
                )
                .order_by(WebhookDelivery.next_attempt_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for delivery in deliveries:
            self._deliver_one(delivery, notifier)
        if deliveries:
            self.db.commit()
        return len(deliveries)

    def _deliver_one(
        self, delivery: WebhookDelivery, notifier: WebhookNotifier
    ) -> None:
        delivery.attempts += 1
        endpoint = self.db.get(WebhookEndpoint, delivery.endpoint_id)
        if (
            endpoint is None
            or not endpoint.is_active
            or endpoint.deleted_at is not None
        ):
            delivery.status = WebhookStatus.FAILED
            delivery.error_code = "webhook_endpoint_inactive"
            delivery.error_message = "O endpoint foi removido ou desativado."
            delivery.finished_at = utcnow()
            return
        try:
            secret = self.cipher.decrypt(endpoint.secret_enc)
        except Exception:  # noqa: BLE001 - segredo ilegível não deve vazar
            logger.warning("webhook_secret_decrypt_failed delivery_id=%s", delivery.id)
            delivery.status = WebhookStatus.FAILED
            delivery.error_code = "webhook_secret_invalid"
            delivery.error_message = "O segredo do webhook não pôde ser lido."
            delivery.finished_at = utcnow()
            return

        body = json.dumps(
            manychat_payload(self.db, delivery),
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode()
        timestamp = str(int(utcnow().timestamp()))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Instarix-Webhooks/1.0",
            "X-Instarix-Event": delivery.event,
            "X-Instarix-Delivery": str(delivery.id),
            "X-Instarix-Timestamp": timestamp,
            "X-Instarix-Signature": f"sha256={sign_payload(secret, timestamp, body)}",
        }

        try:
            status = notifier.send(
                endpoint.url,
                body,
                headers,
                self.settings.webhook_timeout_seconds,
            )
        except WebhookSendError as exc:
            self._retry(delivery, exc.code, exc.message, exc.status)
        except Exception:  # noqa: BLE001 - erro inesperado do transporte
            logger.exception("webhook_delivery_crashed delivery_id=%s", delivery.id)
            self._retry(
                delivery,
                "webhook_send_error",
                "Erro inesperado ao entregar o webhook.",
                None,
            )
        else:
            if 200 <= status < 300:
                delivery.status = WebhookStatus.SUCCEEDED
                delivery.response_status = status
                delivery.error_code = None
                delivery.error_message = None
                delivery.finished_at = utcnow()
            else:
                self._retry(
                    delivery,
                    "webhook_http_error",
                    "O endpoint respondeu com erro HTTP.",
                    status,
                )

    def _retry(
        self,
        delivery: WebhookDelivery,
        code: str,
        message: str,
        response_status: int | None,
    ) -> None:
        delivery.response_status = response_status
        delivery.error_code = code
        delivery.error_message = message[:500]
        if delivery.attempts >= delivery.max_attempts:
            delivery.status = WebhookStatus.FAILED
            delivery.finished_at = utcnow()
            logger.warning(
                "webhook_delivery_failed delivery_id=%s attempts=%s",
                delivery.id,
                delivery.attempts,
            )
            return
        delay = self.settings.webhook_backoff_base_seconds * (
            2 ** max(0, delivery.attempts - 1)
        ) + random.uniform(0, 1)
        delivery.status = WebhookStatus.PENDING
        delivery.next_attempt_at = utcnow() + timedelta(seconds=delay)
        logger.info(
            "webhook_retry_scheduled delivery_id=%s attempt=%s/%s delay=%.1fs",
            delivery.id,
            delivery.attempts,
            delivery.max_attempts,
            delay,
        )
