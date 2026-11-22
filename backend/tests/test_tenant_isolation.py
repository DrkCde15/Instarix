from tests.helpers import bearer, create_account, register


def test_accounts_are_isolated_between_tenants(client):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    account = create_account(client, alice, username="so_da_alice")

    assert client.get("/v1/accounts", headers=bearer(bob)).json()["items"] == []
    assert (
        client.get(f"/v1/accounts/{account['id']}", headers=bearer(bob)).status_code
        == 404
    )
    assert (
        client.patch(
            f"/v1/accounts/{account['id']}",
            json={"label": "invadida"},
            headers=bearer(bob),
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v1/accounts/{account['id']}", headers=bearer(bob)).status_code
        == 404
    )

    # E a conta continua intacta para o dono.
    mine = client.get(f"/v1/accounts/{account['id']}", headers=bearer(alice))
    assert mine.status_code == 200
    assert mine.json()["label"] == "Conta de teste"


def test_api_keys_are_isolated_between_tenants(client):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")

    created = client.post(
        "/v1/api-keys",
        json={"name": "CI", "scopes": ["accounts:read"]},
        headers=bearer(alice),
    )
    assert created.status_code == 201

    assert client.get("/v1/api-keys", headers=bearer(bob)).json() == []
    assert (
        client.delete(
            f"/v1/api-keys/{created.json()['id']}", headers=bearer(bob)
        ).status_code
        == 404
    )
