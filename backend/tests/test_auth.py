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
