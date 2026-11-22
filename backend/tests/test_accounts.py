from app.core.crypto import get_cipher
from app.db.models import IgAccount, User
from tests.helpers import bearer, create_account, register


def test_create_account_encrypts_secrets_and_never_returns_them(client, session_factory):
    tokens = register(client)
    created = create_account(client, tokens, proxy="http://user:pass@proxy.local:8080")

    assert created["status"] == "pending_login"
    assert created["has_proxy"] is True
    assert "password" not in created
    assert "proxy" not in created

    cipher = get_cipher()
    with session_factory() as session:
        account = session.query(IgAccount).one()
        assert "senha-instagram" not in account.password_enc
        assert "user:pass" not in (account.proxy_enc or "")
        assert cipher.decrypt(account.password_enc) == "senha-instagram"
        assert cipher.decrypt(account.proxy_enc) == "http://user:pass@proxy.local:8080"
        device = cipher.decrypt_json(account.device_settings_enc)
        assert device["uuids"]["uuid"]
        assert "authorization_data" not in device
        assert "cookies" not in device


def test_duplicate_username_is_case_insensitive_per_tenant(client):
    tokens = register(client)
    create_account(client, tokens, username="MinhaConta")

    response = client.post(
        "/v1/accounts",
        json={"label": "x", "username": "minhaconta", "password": "outra-senha"},
        headers=bearer(tokens),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_exists"


def test_invalid_proxy_is_rejected(client):
    tokens = register(client)
    response = client.post(
        "/v1/accounts",
        json={
            "label": "x",
            "username": "conta",
            "password": "senha-instagram",
            "proxy": "socks5://sem-suporte",
        },
        headers=bearer(tokens),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_proxy"


def test_password_update_forces_reauth_and_clears_session(client, session_factory):
    tokens = register(client)
    account = create_account(client, tokens)

    with session_factory() as session:
        row = session.query(IgAccount).one()
        row.session_enc = get_cipher().encrypt_json({"cookies": {}})
        row.status = "active"
        session.commit()

    response = client.patch(
        f"/v1/accounts/{account['id']}",
        json={"password": "nova-senha-123"},
        headers=bearer(tokens),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "needs_reauth"

    with session_factory() as session:
        row = session.query(IgAccount).one()
        assert row.session_enc is None
        assert get_cipher().decrypt(row.password_enc) == "nova-senha-123"


def test_proxy_can_be_cleared_with_null(client):
    tokens = register(client)
    account = create_account(client, tokens, proxy="http://proxy.local:8080")

    response = client.patch(
        f"/v1/accounts/{account['id']}",
        json={"proxy": None},
        headers=bearer(tokens),
    )
    assert response.status_code == 200
    assert response.json()["has_proxy"] is False


def test_soft_delete_hides_account_and_frees_username(client):
    tokens = register(client)
    account = create_account(client, tokens, username="descartavel")

    assert (
        client.delete(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).status_code
        == 204
    )
    assert (
        client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).status_code
        == 404
    )

    # Username único é parcial (só contas ativas).
    recreated = create_account(client, tokens, username="descartavel")
    assert recreated["id"] != account["id"]


def test_cursor_pagination(client):
    tokens = register(client)
    for index in range(3):
        create_account(client, tokens, username=f"conta_{index}", label=f"Conta {index}")

    first = client.get("/v1/accounts?limit=2", headers=bearer(tokens))
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 2
    assert page["next_cursor"]

    second = client.get(
        f"/v1/accounts?limit=2&cursor={page['next_cursor']}", headers=bearer(tokens)
    )
    assert second.status_code == 200, second.text
    second_page = second.json()
    assert len(second_page["items"]) == 1
    assert second_page["next_cursor"] is None

    ids = {item["id"] for item in page["items"]} | {
        item["id"] for item in second_page["items"]
    }
    assert len(ids) == 3

    invalid = client.get("/v1/accounts?cursor=nao-e-cursor", headers=bearer(tokens))
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_cursor"


def test_viewer_cannot_create_accounts(client, session_factory):
    tokens = register(client)
    with session_factory() as session:
        user = session.query(User).one()
        user.role = "viewer"
        session.commit()

    response = client.post(
        "/v1/accounts",
        json={"label": "x", "username": "conta", "password": "senha-instagram"},
        headers=bearer(tokens),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_permission"

    # Leitura continua permitida.
    assert client.get("/v1/accounts", headers=bearer(tokens)).status_code == 200


def test_unknown_status_filter_is_rejected(client):
    tokens = register(client)
    response = client.get("/v1/accounts?status=hacked", headers=bearer(tokens))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_status"
