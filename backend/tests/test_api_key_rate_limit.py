from app.api.deps import get_api_key_guard
from app.core.config import get_settings
from app.core.ratelimit import ApiKeyGuard
from app.main import app
from tests.helpers import bearer, register


def test_api_key_rate_limit_returns_429(client):
    tokens = register(client)
    key = client.post(
        "/v1/api-keys",
        json={"name": "limitada", "scopes": ["accounts:read"]},
        headers=bearer(tokens),
    ).json()
    settings = get_settings().model_copy(
        update={"api_key_rate_limit": 2, "api_key_rate_window_seconds": 60}
    )
    guard = ApiKeyGuard(settings)
    app.dependency_overrides[get_api_key_guard] = lambda: guard
    headers = {"X-API-Key": key["key"]}

    assert client.get("/v1/accounts", headers=headers).status_code == 200
    assert client.get("/v1/accounts", headers=headers).status_code == 200
    blocked = client.get("/v1/accounts", headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "api_key_rate_limited"
    assert blocked.headers["retry-after"]

    # JWT não passa pelo limite por API key.
    assert client.get("/v1/accounts", headers=bearer(tokens)).status_code == 200
