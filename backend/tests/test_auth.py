import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import hash_refresh_token
from app.db.models import RefreshToken, User
from tests.helpers import bearer, register


def test_register_login_and_me(client):
    tokens = register(client)
    me = client.get("/v1/me", headers=bearer(tokens))
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"] == "owner@example.com"
    assert body["role"] == "owner"
    assert body["tenant_slug"] == "acme"


def test_register_duplicate_email_conflicts(client):
    register(client)
    response = client.post(
        "/v1/auth/register",
        json={
            "tenant_name": "Outra",
            "email": "OWNER@example.com",
            "password": "outra-senha-123",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_login_wrong_password_is_unauthorized(client):
    register(client)
    response = client.post(
        "/v1/auth/token",
        json={"email": "owner@example.com", "password": "errada"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_refresh_rotation_and_reuse_detection(client, session_factory):
    tokens = register(client)

    rotated = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert new_tokens["access_token"] != tokens["access_token"]

    # Reutilizar o token antigo revoga a família inteira.
    reuse = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "token_reuse_detected"

    family_revoked = client.post(
        "/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert family_revoked.status_code == 401
    assert family_revoked.json()["error"]["code"] == "token_reuse_detected"

    with session_factory() as session:
        rows = session.query(RefreshToken).all()
        assert all(row.revoked_at is not None for row in rows)
        # Nunca persistir o token em claro.
        assert all(
            row.token_hash != tokens["refresh_token"] for row in rows
        )
        assert any(
            row.token_hash == hash_refresh_token(tokens["refresh_token"]) for row in rows
        )


def test_refresh_and_logout_use_httponly_cookie(client):
    created = client.post(
        "/v1/auth/register",
        json={
            "tenant_name": "Cookie Co",
            "email": "cookie@example.com",
            "password": "senha-forte-123",
        },
    )
    assert created.status_code == 201, created.text
    set_cookie = created.headers["set-cookie"]
    assert "instarix_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/v1/auth" in set_cookie

    first = created.json()
    assert client.cookies.get("instarix_refresh") == first["refresh_token"]

    refreshed = client.post("/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    second = refreshed.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert client.cookies.get("instarix_refresh") == second["refresh_token"]

    assert client.post("/v1/auth/logout").status_code == 204
    assert client.post("/v1/auth/refresh").status_code == 401


def test_refresh_with_cookie_rejects_cross_site_origin(client):
    tokens = register(client)

    # Token no corpo é um cliente não-browser: passa da checagem de CSRF.
    body_token = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Origin": "https://evil.example"},
    )
    assert body_token.status_code == 200, body_token.text

    blocked = client.post(
        "/v1/auth/refresh", headers={"Origin": "https://evil.example"}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_origin_rejected"

    same_origin = client.post(
        "/v1/auth/refresh", headers={"Origin": "http://testserver"}
    )
    assert same_origin.status_code == 200, same_origin.text


def test_cookie_refresh_allows_loopback_dev_proxy(client):
    register(client)
    # O proxy do Vite reescreve o Host, mas origem e destino são loopback.
    response = client.post(
        "/v1/auth/refresh",
        headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
    )
    assert response.status_code == 200, response.text


def test_token_responses_are_not_cacheable(client):
    created = client.post(
        "/v1/auth/register",
        json={
            "tenant_name": "Cache Co",
            "email": "cache@example.com",
            "password": "senha-forte-123",
        },
    )
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth_cookie_samesite": "none", "auth_cookie_secure": False},
        {"cors_origins": ["*"]},
    ],
)
def test_insecure_cookie_and_cors_settings_are_rejected(overrides):
    base = {
        "jwt_secret": "test-secret-" + "x" * 40,
        "secrets_keys": "chave-de-teste",
        "environment": "dev",
    }
    with pytest.raises(ValidationError):
        Settings(**base, **overrides)


def test_logout_revokes_refresh_token(client):
    tokens = register(client)
    assert (
        client.post(
            "/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 204
    )
    response = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


def test_missing_and_invalid_credentials(client):
    assert client.get("/v1/me").status_code == 401

    bad = client.get("/v1/me", headers={"Authorization": "Bearer nao-e-um-jwt"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"

    bad_key = client.get("/v1/me", headers={"X-API-Key": "ik_live_xxx_yyy"})
    assert bad_key.status_code == 401


def test_inactive_user_is_rejected(client, session_factory):
    tokens = register(client)
    with session_factory() as session:
        user = session.query(User).one()
        user.is_active = False
        session.commit()

    response = client.get("/v1/me", headers=bearer(tokens))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "user_inactive"
