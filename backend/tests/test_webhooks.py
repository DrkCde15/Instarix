import json
import socket
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.errors import AppError
from app.core.time import utcnow
from app.db.models import WebhookDelivery
from app.services.ig_gateway import IgAuthError
from app.services.webhooks import (
    WebhookSendError,
    WebhookService,
    sign_payload,
    validate_webhook_url,
)
from tests.helpers import bearer, create_account, register
from tests.test_jobs import enqueue, login_account, run_next


class FakeNotifier:
    def __init__(self, status=200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.calls: list[dict] = []

    def send(self, url, body, headers, timeout):
        self.calls.append(
            {"url": url, "body": body, "headers": headers, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return self.status


def create_webhook(client, tokens, *, events=("job.succeeded",), url="https://example.com/hook"):
    return client.post(
        "/v1/webhooks",
        json={"url": url, "events": list(events)},
        headers=bearer(tokens),
    )


def test_webhook_crud_and_tenant_isolation(client):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")

    created = create_webhook(client, alice)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret"]
    assert body["events"] == ["job.succeeded"]

    listed = client.get("/v1/webhooks", headers=bearer(alice)).json()
    assert len(listed) == 1
    assert "secret" not in listed[0]
    assert listed[0]["id"] == body["id"]
    assert client.get("/v1/webhooks", headers=bearer(bob)).json() == []

    unknown = create_webhook(client, alice, events=("job.nope",))
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "invalid_webhook_event"

    local = create_webhook(client, alice, url="http://127.0.0.1/hook")
    assert local.status_code == 422
    assert local.json()["error"]["code"] == "invalid_webhook_url"

    assert (
        client.delete(f"/v1/webhooks/{body['id']}", headers=bearer(bob)).status_code
        == 404
    )
    deleted = client.delete(f"/v1/webhooks/{body['id']}", headers=bearer(alice))
    assert deleted.status_code == 204
    assert client.get("/v1/webhooks", headers=bearer(alice)).json() == []


def test_webhook_send_validation_blocks_private_resolution(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]

    monkeypatch.setattr("app.services.webhooks.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(AppError) as exc:
        validate_webhook_url("https://example.com/hook", resolve=True)
    assert exc.value.code == "invalid_webhook_url"


def test_job_event_is_delivered_with_hmac(client, worker, session_factory, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    endpoint = create_webhook(client, tokens).json()

    job = enqueue(client, tokens, account["id"]).json()
    run_next(worker)

    deliveries = client.get(
        f"/v1/webhooks/{endpoint['id']}/deliveries", headers=bearer(tokens)
    ).json()
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["status"] == "pending"
    assert delivery["payload"]["job_id"] == job["id"]
    assert delivery["payload"]["type"] == "media.list"
    assert "session" not in json.dumps(delivery["payload"])

    notifier = FakeNotifier(status=204)
    with session_factory() as db:
        service = WebhookService(db, get_cipher(), get_settings())
        assert service.deliver_due(notifier) == 1

    assert len(notifier.calls) == 1
    call = notifier.calls[0]
    assert call["url"] == "https://example.com/hook"
    headers = call["headers"]
    assert headers["X-Instarix-Event"] == "job.succeeded"
    expected = sign_payload(
        endpoint["secret"], headers["X-Instarix-Timestamp"], call["body"]
    )
    assert headers["X-Instarix-Signature"] == f"sha256={expected}"
    assert json.loads(call["body"]) == delivery["payload"]

    after = client.get(
        f"/v1/webhooks/{endpoint['id']}/deliveries", headers=bearer(tokens)
    ).json()[0]
    assert after["status"] == "succeeded"
    assert after["response_status"] == 204
    assert after["finished_at"] is not None


def test_failed_delivery_retries_and_can_use_due_again(
    client, worker, session_factory, ig_gateway
):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    endpoint = create_webhook(client, tokens, events=("job.failed",)).json()

    ig_gateway.media_list_error = IgAuthError()
    enqueue(client, tokens, account["id"]).json()
    run_next(worker)

    notifier = FakeNotifier(error=WebhookSendError("webhook_http_error", "falhou", 500))
    with session_factory() as db:
        service = WebhookService(db, get_cipher(), get_settings())
        assert service.deliver_due(notifier) == 1

    first = client.get(
        f"/v1/webhooks/{endpoint['id']}/deliveries", headers=bearer(tokens)
    ).json()[0]
    assert first["status"] == "pending"
    assert first["attempts"] == 1
    assert first["error_code"] == "webhook_http_error"
    assert first["response_status"] == 500

    with session_factory() as db:
        row = db.query(WebhookDelivery).one()
        row.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()

    notifier.error = None
    notifier.status = 200
    with session_factory() as db:
        service = WebhookService(db, get_cipher(), get_settings())
        assert service.deliver_due(notifier) == 1

    second = client.get(
        f"/v1/webhooks/{endpoint['id']}/deliveries", headers=bearer(tokens)
    ).json()[0]
    assert second["status"] == "succeeded"
    assert second["attempts"] == 2
    assert second["error_code"] is None


def test_delivery_stops_at_max_attempts(client, worker, session_factory, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    endpoint = create_webhook(client, tokens).json()
    enqueue(client, tokens, account["id"]).json()
    run_next(worker)

    with session_factory() as db:
        row = db.query(WebhookDelivery).one()
        row.max_attempts = 1
        db.commit()

    notifier = FakeNotifier(error=WebhookSendError("webhook_send_error", "falhou"))
    with session_factory() as db:
        service = WebhookService(db, get_cipher(), get_settings())
        service.deliver_due(notifier)

    body = client.get(
        f"/v1/webhooks/{endpoint['id']}/deliveries", headers=bearer(tokens)
    ).json()[0]
    assert body["status"] == "failed"
    assert body["attempts"] == 1
    assert body["finished_at"] is not None
