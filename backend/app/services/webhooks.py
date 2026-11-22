"""Webhooks de saída com HMAC, retry e backoff."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import random
import secrets
import uuid
from datetime import timedelta
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import Cipher
from app.core.errors import AppError, not_found
from app.core.time import utcnow
from app.db.models import WebhookDelivery, WebhookEndpoint, WebhookStatus

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


class HttpWebhookNotifier:
    """POST com urllib (sem dependência extra)."""

    def send(
        self, url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> int:
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return int(response.status)
        except HTTPError as exc:
            raise WebhookSendError(
                "webhook_http_error",
                "O endpoint respondeu com erro HTTP.",
                status=exc.code,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise WebhookSendError(
                "webhook_send_error", "Não foi possível entregar o webhook."
            ) from exc


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


def validate_webhook_url(url: str) -> str:
    url = url.strip()
    if len(url) > 2048:
        raise AppError(422, "invalid_webhook_url", "URL do webhook é muito longa.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AppError(
            422, "invalid_webhook_url", "A URL deve ser http(s) com host."
        )
    if parts.username or parts.password:
        raise AppError(
            422, "invalid_webhook_url", "A URL não pode conter credenciais."
        )
    host = parts.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise AppError(422, "invalid_webhook_url", "Host de webhook não permitido.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ):
        raise AppError(422, "invalid_webhook_url", "IP de webhook não permitido.")
    return url


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
            delivery.payload, separators=(",", ":"), sort_keys=True, default=str
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
