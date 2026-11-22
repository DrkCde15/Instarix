from tests.helpers import bearer, create_account, register
from tests.test_jobs import enqueue


def test_metrics_exposes_queue_and_accounts(client):
    tokens = register(client)
    account = create_account(client, tokens)
    enqueue(client, tokens, account["id"])

    response = client.get("/v1/metrics", headers=bearer(tokens))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert 'jobs_total{type="media.list",status="queued"} 1' in body
    assert 'queue_depth{priority="5"} 1' in body
    assert 'accounts_by_status{status="pending_login"} 1' in body
    assert "webhook_delivery_failures_total 0" in body


def test_metrics_requires_admin_scope(client):
    tokens = register(client)
    key = client.post(
        "/v1/api-keys",
        json={"name": "leitura", "scopes": ["accounts:read"]},
        headers=bearer(tokens),
    ).json()
    denied = client.get("/v1/metrics", headers={"X-API-Key": key["key"]})
    assert denied.status_code == 403
