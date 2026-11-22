from app.core.security import hash_api_key_secret, parse_api_key
from app.db.models import ApiKey
from tests.helpers import bearer, register


def test_api_key_is_returned_once_and_stored_hashed(client, session_factory):
    tokens = register(client)
    response = client.post(
        "/v1/api-keys",
        json={"name": "CI read", "scopes": ["accounts:read"]},
        headers=bearer(tokens),
    )
    assert response.status_code == 201, response.text
    created = response.json()
    raw = created["key"]
    assert raw.startswith("ik_live_")

    listed = client.get("/v1/api-keys", headers=bearer(tokens)).json()
    assert len(listed) == 1
    assert "key" not in listed[0]

    with session_factory() as session:
        row = session.query(ApiKey).one()
        parsed = parse_api_key(raw)
        assert parsed is not None
        prefix, secret = parsed
        assert row.key_prefix == prefix
        assert row.key_hash == hash_api_key_secret(secret)
        assert row.key_hash != raw  # só o hash, nunca a chave


def test_api_key_scopes_limit_access(client):
    tokens = register(client)
    created = client.post(
        "/v1/api-keys",
        json={"name": "read-only", "scopes": ["accounts:read"]},
        headers=bearer(tokens),
    ).json()
    headers = {"X-API-Key": created["key"]}

    assert client.get("/v1/accounts", headers=headers).status_code == 200

    denied = client.post(
        "/v1/accounts",
        json={"label": "x", "username": "conta", "password": "senha-instagram"},
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_permission"


def test_api_key_with_write_scope_can_create_accounts(client):
    tokens = register(client)
    created = client.post(
        "/v1/api-keys",
        json={"name": "writer", "scopes": ["accounts:write"]},
        headers=bearer(tokens),
    ).json()

    response = client.post(
        "/v1/accounts",
        json={"label": "via api key", "username": "conta_key", "password": "senha-instagram"},
        headers={"X-API-Key": created["key"]},
    )
    assert response.status_code == 201, response.text


def test_invalid_scopes_are_rejected(client):
    tokens = register(client)
    invalid = client.post(
        "/v1/api-keys",
        json={"name": "x", "scopes": ["root"]},
        headers=bearer(tokens),
    )
    assert invalid.status_code == 422


def test_revoked_api_key_stops_working(client):
    tokens = register(client)
    created = client.post(
        "/v1/api-keys",
        json={"name": "temporária", "scopes": ["accounts:read"]},
        headers=bearer(tokens),
    ).json()
    headers = {"X-API-Key": created["key"]}
    assert client.get("/v1/accounts", headers=headers).status_code == 200

    revoke = client.delete(f"/v1/api-keys/{created['id']}", headers=bearer(tokens))
    assert revoke.status_code == 204

    assert client.get("/v1/accounts", headers=headers).status_code == 401
