import json

from tests.helpers import bearer, create_account, register
from tests.test_jobs import enqueue, login_account
from tests.test_webhooks import create_webhook


def logs(client, tokens, **params):
    response = client.get("/v1/audit-logs", params=params, headers=bearer(tokens))
    assert response.status_code == 200, response.text
    return response.json()


def test_sensitive_actions_are_audited_without_secrets(client, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens, password="senha-secreta-ig")
    login_account(client, tokens, account["id"])

    updated = client.patch(
        f"/v1/accounts/{account['id']}",
        json={"label": "Novo rótulo", "password": "outra-senha-secreta"},
        headers=bearer(tokens),
    )
    assert updated.status_code == 200

    enqueue(client, tokens, account["id"], "media.list")
    key = client.post(
        "/v1/api-keys",
        json={"name": "CI", "scopes": ["jobs:read"]},
        headers=bearer(tokens),
    ).json()
    created_wh = create_webhook(client, tokens)

    body = logs(client, tokens)
    actions = {item["action"] for item in body["items"]}
    assert {
        "account.created",
        "account.login",
        "account.updated",
        "job.created",
        "api_key.created",
        "webhook.created",
    } <= actions

    serialized = json.dumps(body)
    assert "senha-secreta-ig" not in serialized
    assert "outra-senha-secreta" not in serialized
    assert key["key"] not in serialized
    assert created_wh.json()["secret"] not in serialized
    assert "proxies" not in serialized

    updated_log = next(
        item for item in body["items"] if item["action"] == "account.updated"
    )
    assert updated_log["metadata"] == {"changed_fields": ["label", "password"]}
    assert updated_log["account_id"] == account["id"]
    assert updated_log["ip"] is not None


def test_audit_is_tenant_isolated_and_requires_scope(client):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    create_account(client, alice)

    assert logs(client, bob)["items"] == []

    read_key = client.post(
        "/v1/api-keys",
        json={"name": "auditoria", "scopes": ["audit:read"]},
        headers=bearer(alice),
    ).json()
    allowed = client.get(
        "/v1/audit-logs", headers={"X-API-Key": read_key["key"]}
    )
    assert allowed.status_code == 200

    jobs_key = client.post(
        "/v1/api-keys",
        json={"name": "jobs", "scopes": ["jobs:read"]},
        headers=bearer(alice),
    ).json()
    denied = client.get("/v1/audit-logs", headers={"X-API-Key": jobs_key["key"]})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_permission"


def test_audit_filters_and_pagination(client):
    tokens = register(client)
    for index in range(3):
        create_account(client, tokens, username=f"conta_{index}")

    filtered = logs(client, tokens, action="account.created", limit=2)
    assert len(filtered["items"]) == 2
    assert filtered["next_cursor"] is not None

    next_page = client.get(
        "/v1/audit-logs",
        params={"action": "account.created", "limit": 2, "cursor": filtered["next_cursor"]},
        headers=bearer(tokens),
    ).json()
    assert len(next_page["items"]) == 1
    assert next_page["next_cursor"] is None
