from fastapi.testclient import TestClient


def register(
    client: TestClient,
    *,
    email: str = "owner@example.com",
    tenant_name: str = "Acme",
    password: str = "senha-forte-123",
) -> dict:
    response = client.post(
        "/v1/auth/register",
        json={"tenant_name": tenant_name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def create_account(
    client: TestClient,
    tokens: dict,
    *,
    username: str = "conta_teste",
    label: str = "Conta de teste",
    password: str = "senha-instagram",
    proxy: str | None = None,
) -> dict:
    body: dict = {"label": label, "username": username, "password": password}
    if proxy is not None:
        body["proxy"] = proxy
    response = client.post("/v1/accounts", json=body, headers=bearer(tokens))
    assert response.status_code == 201, response.text
    return response.json()
