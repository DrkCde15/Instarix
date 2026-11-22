from datetime import timedelta

from app.core.crypto import get_cipher
from app.core.time import utcnow
from app.db.models import IgAccount, LoginAttempt, User
from app.services.ig_gateway import HealthOutcome, LoginOutcome
from tests.fakes import FakeIgGateway, success_outcome
from tests.helpers import bearer, create_account, register


def login_account(client, tokens, account_id):
    return client.post(f"/v1/accounts/{account_id}/login", headers=bearer(tokens))


def submit_2fa(client, tokens, account_id, code="123456"):
    return client.post(
        f"/v1/accounts/{account_id}/2fa",
        json={"code": code},
        headers=bearer(tokens),
    )


def start_2fa(client, tokens, account_id, gateway: FakeIgGateway):
    gateway.login_outcome = LoginOutcome("2fa_required", two_fa_method="totp")
    response = login_account(client, tokens, account_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "2fa_required"


def test_login_success_persists_encrypted_session(
    client, session_factory, ig_gateway: FakeIgGateway
):
    tokens = register(client)
    account = create_account(client, tokens)

    response = login_account(client, tokens, account["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["has_session"] is True
    assert body["last_login_at"] is not None

    call = ig_gateway.login_calls[-1]
    assert call["username"] == "conta_teste"
    assert call["password"] == "senha-instagram"
    assert call["proxy"] is None
    assert call["session"] is None

    with session_factory() as session:
        row = session.query(IgAccount).one()
        # Perfil de dispositivo gerado na criação é reutilizado.
        assert call["device_settings"] == get_cipher().decrypt_json(
            row.device_settings_enc
        )
        assert "sessao-secreta" not in (row.session_enc or "")
        assert get_cipher().decrypt_json(row.session_enc) == ig_gateway.login_outcome.session
        attempt = session.query(LoginAttempt).one()
        assert attempt.status == "succeeded"
        assert attempt.finished_at is not None


def test_login_reuses_stored_session(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    assert login_account(client, tokens, account["id"]).status_code == 200

    second = login_account(client, tokens, account["id"])
    assert second.status_code == 200, second.text
    assert ig_gateway.login_calls[-1]["session"] == ig_gateway.login_outcome.session


def test_login_2fa_flow(client, session_factory, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    start_2fa(client, tokens, account["id"], ig_gateway)

    attempts = client.get(
        f"/v1/accounts/{account['id']}/login-attempts", headers=bearer(tokens)
    ).json()
    assert len(attempts) == 1
    assert attempts[0]["status"] == "pending_2fa"
    assert attempts[0]["attempts"] == 0
    assert attempts[0]["expires_at"] is not None
    assert "code" not in attempts[0]

    ig_gateway.login_outcome = success_outcome()
    response = submit_2fa(client, tokens, account["id"], "654321")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert response.json()["has_session"] is True

    call = ig_gateway.login_calls[-1]
    assert call["verification_code"] == "654321"
    assert call["session"] is None

    with session_factory() as session:
        attempt = session.query(LoginAttempt).order_by(LoginAttempt.created_at.desc()).first()
        assert attempt.status == "succeeded"


def test_wrong_2fa_code_has_attempt_limit(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    start_2fa(client, tokens, account["id"], ig_gateway)

    ig_gateway.login_outcome = LoginOutcome("2fa_required", two_fa_method="totp")
    first = submit_2fa(client, tokens, account["id"], "000000")
    assert first.status_code == 400
    assert first.json()["error"]["code"] == "invalid_verification_code"
    assert "2" in first.json()["error"]["message"]

    second = submit_2fa(client, tokens, account["id"], "000000")
    assert second.status_code == 400
    assert "1" in second.json()["error"]["message"]

    third = submit_2fa(client, tokens, account["id"], "000000")
    assert third.status_code == 400
    assert "Nenhuma tentativa restante" in third.json()["error"]["message"]

    status = client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()
    assert status["status"] == "needs_reauth"
    assert status["has_session"] is False

    after = submit_2fa(client, tokens, account["id"], "000000")
    assert after.status_code == 409
    assert after.json()["error"]["code"] == "two_factor_not_pending"


def test_expired_2fa_returns_to_login(client, session_factory, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    start_2fa(client, tokens, account["id"], ig_gateway)

    with session_factory() as session:
        attempt = session.query(LoginAttempt).one()
        attempt.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()

    response = submit_2fa(client, tokens, account["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "two_factor_expired"

    status = client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()
    assert status["status"] == "pending_login"

    with session_factory() as session:
        assert session.query(LoginAttempt).one().status == "expired"


def test_challenge_and_bad_password_set_terminal_states(
    client, ig_gateway: FakeIgGateway
):
    tokens = register(client)
    account = create_account(client, tokens)

    ig_gateway.login_outcome = LoginOutcome("challenge_required")
    challenge = login_account(client, tokens, account["id"])
    assert challenge.status_code == 409
    assert challenge.json()["error"]["code"] == "account_challenge_required"
    assert (
        client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()[
            "status"
        ]
        == "challenge_required"
    )

    ig_gateway.login_outcome = LoginOutcome("bad_password")
    bad = login_account(client, tokens, account["id"])
    assert bad.status_code == 409
    assert bad.json()["error"]["code"] == "account_needs_reauth"
    assert (
        client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()[
            "status"
        ]
        == "needs_reauth"
    )


def test_transient_error_keeps_state(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)

    ig_gateway.login_outcome = LoginOutcome(
        "unavailable",
        error_code="instagram_unavailable",
        error_message="Falha temporária ao falar com o Instagram.",
    )
    response = login_account(client, tokens, account["id"])
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "instagram_unavailable"

    body = client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()
    assert body["status"] == "pending_login"
    assert body["last_error_code"] == "instagram_unavailable"


def test_transient_2fa_failure_keeps_attempt_pending(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    start_2fa(client, tokens, account["id"], ig_gateway)

    ig_gateway.login_outcome = LoginOutcome(
        "unavailable", error_code="instagram_unavailable"
    )
    failed = submit_2fa(client, tokens, account["id"])
    assert failed.status_code == 502

    pending = client.get(
        f"/v1/accounts/{account['id']}/login-attempts", headers=bearer(tokens)
    ).json()
    assert [item["status"] for item in pending] == ["pending_2fa"]

    ig_gateway.login_outcome = success_outcome()
    assert submit_2fa(client, tokens, account["id"]).status_code == 200


def test_health_check(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    assert login_account(client, tokens, account["id"]).status_code == 200

    healthy = client.get(f"/v1/accounts/{account['id']}/health", headers=bearer(tokens))
    assert healthy.status_code == 200
    assert healthy.json()["status"] == "active"
    assert healthy.json()["last_login_at"] is not None
    assert ig_gateway.health_calls

    ig_gateway.health_outcome = HealthOutcome("invalid")
    invalid = client.get(f"/v1/accounts/{account['id']}/health", headers=bearer(tokens))
    assert invalid.status_code == 200
    assert invalid.json()["status"] == "needs_reauth"
    assert invalid.json()["has_session"] is False

    no_session = client.get(
        f"/v1/accounts/{account['id']}/health", headers=bearer(tokens)
    )
    assert no_session.status_code == 409
    assert no_session.json()["error"]["code"] == "account_no_session"


def test_logout_clears_session(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    assert login_account(client, tokens, account["id"]).status_code == 200

    response = client.post(
        f"/v1/accounts/{account['id']}/logout", headers=bearer(tokens)
    )
    assert response.status_code == 204
    assert len(ig_gateway.logout_calls) == 1

    body = client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()
    assert body["status"] == "pending_login"
    assert body["has_session"] is False

    # Sem sessão, não chama o Instagram de novo.
    assert (
        client.post(
            f"/v1/accounts/{account['id']}/logout", headers=bearer(tokens)
        ).status_code
        == 204
    )
    assert len(ig_gateway.logout_calls) == 1


def test_login_requires_tenant_and_scope(client, ig_gateway: FakeIgGateway):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    account = create_account(client, alice)

    assert login_account(client, bob, account["id"]).status_code == 404
    assert (
        client.get(
            f"/v1/accounts/{account['id']}/login-attempts", headers=bearer(bob)
        ).status_code
        == 404
    )

    read_key = client.post(
        "/v1/api-keys",
        json={"name": "read", "scopes": ["accounts:read"]},
        headers=bearer(alice),
    ).json()
    denied = client.post(
        f"/v1/accounts/{account['id']}/login",
        headers={"X-API-Key": read_key["key"]},
    )
    assert denied.status_code == 403


def test_2fa_scope_allows_two_factor_only(client, ig_gateway: FakeIgGateway):
    tokens = register(client)
    account = create_account(client, tokens)
    start_2fa(client, tokens, account["id"], ig_gateway)

    key = client.post(
        "/v1/api-keys",
        json={"name": "2fa", "scopes": ["accounts:2fa"]},
        headers=bearer(tokens),
    ).json()
    ig_gateway.login_outcome = success_outcome()
    response = client.post(
        f"/v1/accounts/{account['id']}/2fa",
        json={"code": "123456"},
        headers={"X-API-Key": key["key"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"


def test_admin_role_can_submit_two_factor(
    client, session_factory, ig_gateway: FakeIgGateway
):
    tokens = register(client)
    account = create_account(client, tokens)
    start_2fa(client, tokens, account["id"], ig_gateway)

    with session_factory() as session:
        user = session.query(User).one()
        user.role = "admin"
        session.commit()

    ig_gateway.login_outcome = success_outcome()
    response = submit_2fa(client, tokens, account["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"


def test_disabled_account_cannot_login(client, session_factory):
    tokens = register(client)
    account = create_account(client, tokens)
    with session_factory() as session:
        row = session.query(IgAccount).one()
        row.status = "disabled"
        session.commit()

    response = login_account(client, tokens, account["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_disabled"


def test_invalid_2fa_payload(client):
    tokens = register(client)
    account = create_account(client, tokens)

    response = client.post(
        f"/v1/accounts/{account['id']}/2fa",
        json={"code": "a"},
        headers=bearer(tokens),
    )
    assert response.status_code == 422
