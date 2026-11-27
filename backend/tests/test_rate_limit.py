from app.core.config import get_settings
from app.core.ratelimit import (
    AuthGuard,
    RedisLockoutStore,
    RedisWindowLimiter,
    get_auth_guard,
)
from app.main import app
from tests.helpers import register


def install_guard(client, **overrides) -> AuthGuard:
    settings = get_settings().model_copy(update=overrides)
    guard = AuthGuard(settings)
    app.dependency_overrides[get_auth_guard] = lambda: guard
    return guard


def login(client, *, email="owner@example.com", password="senha-forte-123"):
    return client.post("/v1/auth/token", json={"email": email, "password": password})


def test_login_is_rate_limited_by_ip(client):
    tokens = register(client)
    install_guard(
        client,
        auth_login_limit=3,
        auth_login_window_seconds=300,
        auth_max_failed_logins=1000,
    )

    for _ in range(3):
        assert login(client, password="errada").status_code == 401

    blocked = login(client)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    retry_after = int(blocked.headers["Retry-After"])
    assert 1 <= retry_after <= 300

    # Um Bearer válido continua funcionando: o limite é só do login.
    assert (
        client.get(
            "/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        ).status_code
        == 200
    )


def test_register_is_rate_limited_by_ip(client):
    install_guard(client, auth_register_limit=1, auth_register_window_seconds=3600)
    register(client, email="um@example.com", tenant_name="Um")

    blocked = client.post(
        "/v1/auth/register",
        json={
            "tenant_name": "Dois",
            "email": "dois@example.com",
            "password": "senha-forte-123",
        },
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in blocked.headers


def test_account_is_locked_after_repeated_failures(client):
    tokens = register(client)
    install_guard(
        client,
        auth_login_limit=1000,
        auth_max_failed_logins=3,
        auth_failed_login_window_seconds=300,
        auth_lockout_seconds=300,
    )

    for _ in range(3):
        assert login(client, password="errada").status_code == 401

    # Mesmo a senha correta é recusada durante o lockout.
    locked = login(client)
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "account_locked"
    assert int(locked.headers["Retry-After"]) >= 1

    # O bloqueio é por conta: outro email (inexistente) não é afetado.
    other = login(client, email="ninguem@example.com", password="errada")
    assert other.status_code == 401

    # E o token emitido antes do lockout continua válido.
    assert (
        client.get(
            "/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        ).status_code
        == 200
    )


def test_successful_login_clears_failures(client):
    register(client)
    install_guard(
        client,
        auth_login_limit=1000,
        auth_max_failed_logins=3,
        auth_failed_login_window_seconds=300,
        auth_lockout_seconds=300,
    )

    assert login(client, password="errada").status_code == 401
    assert login(client, password="errada").status_code == 401
    assert login(client).status_code == 200

    # O contador zerou; duas novas falhas ainda não bloqueiam.
    assert login(client, password="errada").status_code == 401
    assert login(client, password="errada").status_code == 401
    assert login(client).status_code == 200


def test_refresh_is_rate_limited_by_ip(client):
    tokens = register(client)
    install_guard(client, auth_refresh_limit=2, auth_refresh_window_seconds=300)

    first = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
    )
    assert second.status_code == 200

    blocked = client.post(
        "/v1/auth/refresh", json={"refresh_token": second.json()["refresh_token"]}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


class FakeRedis:
    """Cliente mínimo para exercitar o store compartilhado sem servidor."""

    def __init__(self, *, eval_results=None, get_result=None) -> None:
        self.eval_results = list(eval_results or [])
        self.get_result = get_result
        self.eval_calls: list[tuple] = []
        self.deleted: list[str] = []

    def eval(self, *args):
        self.eval_calls.append(args)
        return self.eval_results.pop(0) if self.eval_results else (1, 0)

    def get(self, key: str):
        return self.get_result

    def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        return len(keys)


def test_redis_limiter_returns_retry_after_from_server():
    client = FakeRedis(eval_results=[(0, 2.4)])
    limiter = RedisWindowLimiter("redis://localhost:6379/0", client=client)

    assert limiter.consume("login:1.2.3.4", 3, 300) == 2.4
    # KEYS[1] é o nome da janela; todas as instâncias usam a mesma chave.
    assert client.eval_calls[0][2] == "instarix:rl:login:1.2.3.4"


def test_redis_limiter_allows_when_slot_available():
    client = FakeRedis(eval_results=[(1, 0)])
    limiter = RedisWindowLimiter("redis://localhost:6379/0", client=client)

    assert limiter.consume("refresh:1.2.3.4", 30, 300) is None


def test_redis_lockout_writes_to_shared_keys():
    client = FakeRedis()
    store = RedisLockoutStore("redis://localhost:6379/0", client=client)
    settings = get_settings().model_copy(
        update={
            "auth_max_failed_logins": 3,
            "auth_failed_login_window_seconds": 300,
            "auth_lockout_seconds": 300,
        }
    )

    store.record_failure("owner@example.com", settings)

    assert client.eval_calls[0][2] == "instarix:lock:fail:owner@example.com"
    assert client.eval_calls[0][3] == "instarix:lock:until:owner@example.com"


def test_guard_uses_redis_store_when_configured():
    settings = get_settings().model_copy(update={"rate_limit_backend": "redis"})

    guard = AuthGuard(settings)

    assert isinstance(guard._limiter, RedisWindowLimiter)
    assert isinstance(guard._lockout, RedisLockoutStore)
