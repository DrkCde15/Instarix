"""Rate limiting e proteção contra brute force para endpoints de auth.

Por padrão o estado fica em memória, por processo (suficiente para um único
worker). Com ``RATE_LIMIT_BACKEND=redis``, janelas, falhas de login e lockout
passam a ser compartilhados entre workers/instâncias via ``REDIS_URL``.
Se o Redis estiver indisponível, as rotas protegidas falham fechado (503) em
vez de liberar o acesso com limites locais.

As janelas em memória usam ``time.monotonic()``; no Redis, o relógio do
próprio servidor é usado para que todos os processos vejam a mesma janela.
"""

import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from typing import Protocol

import redis

from app.core.config import Settings, get_settings
from app.core.errors import AppError

_REDIS_OPTIONS = {
    "decode_responses": True,
    "socket_connect_timeout": 0.2,
    "socket_timeout": 0.2,
}
_LIMIT_PREFIX = "instarix:rl"
_LOCK_PREFIX = "instarix:lock"

# Verificação e registro atômicos da janela deslizante (ZSET por chave).
_LUA_CONSUME = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = math.ceil(window * 1000) + 1000
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 0
  if oldest[2] then retry = tonumber(oldest[2]) + window - now end
  redis.call('PEXPIRE', key, ttl)
  return {0, retry}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, ttl)
return {1, 0}
"""

# Contagem de falhas e lockout em uma única transação no Redis.
_LUA_RECORD_FAILURE = """
local failures_key = KEYS[1]
local until_key = KEYS[2]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_failures = tonumber(ARGV[3])
local lockout = tonumber(ARGV[4])
local member = ARGV[5]
redis.call('ZREMRANGEBYSCORE', failures_key, 0, now - window)
redis.call('ZADD', failures_key, now, member)
redis.call('PEXPIRE', failures_key, math.ceil(window) + 1)
if redis.call('ZCARD', failures_key) >= max_failures then
  redis.call('DEL', failures_key)
  redis.call('SET', until_key, now + lockout, 'EX', math.ceil(lockout) + 1)
  return 1
end
return 0
"""


class WindowLimiter(Protocol):
    def consume(
        self, key: str, limit: int, window_seconds: int, now: float | None = None
    ) -> float | None: ...


class LockoutStore(Protocol):
    def retry_after(self, key: str) -> float | None: ...

    def record_failure(self, key: str, settings: Settings) -> None: ...

    def clear(self, key: str) -> None: ...


def _redis_client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, **_REDIS_OPTIONS)


def _shared(fn: Callable[..., object], *args: object, **kwargs: object) -> object:
    """Chamada ao Redis que falha fechado se o store compartilhado cair."""
    try:
        return fn(*args, **kwargs)
    except redis.RedisError as exc:
        raise AppError(
            503,
            "rate_limit_unavailable",
            "Serviço de limite de requisições indisponível.",
        ) from exc


class RateLimiter:
    """Janela deslizante em memória, com limite no número de chaves."""

    def __init__(self, max_keys: int = 10_000) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def consume(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> float | None:
        """Registra uma tentativa; retorna segundos de espera se bloqueada."""
        if limit <= 0:
            return None
        now = time.monotonic() if now is None else now

        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= limit:
                return max(0.0, events[0] + window_seconds - now)

            events.append(now)
            if len(self._events) > self._max_keys:
                # Evita crescimento ilimitado sob chaves forjadas (ex.: IPs
                # aleatórios em X-Forwarded-For quando mal configurado).
                self._events.pop(next(iter(self._events)))
            return None


class RedisWindowLimiter:
    """Janela deslizante no Redis, compartilhada entre processos."""

    def __init__(
        self,
        url: str,
        *,
        client: redis.Redis | None = None,
        prefix: str = _LIMIT_PREFIX,
    ) -> None:
        self._client = client or _redis_client(url)
        self._prefix = prefix

    def consume(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> float | None:
        if limit <= 0:
            return None
        current = time.time()
        member = f"{current:.6f}-{uuid.uuid4().hex}"
        allowed, retry = _shared(
            self._client.eval,
            _LUA_CONSUME,
            1,
            f"{self._prefix}:{key}",
            current,
            window_seconds,
            limit,
            member,
        )
        if allowed:
            return None
        return max(0.0, float(retry))


class MemoryLockoutStore:
    """Falhas de login e lockout em memória, por processo."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_accounts: int = 10_000,
    ) -> None:
        self._clock = clock
        self._max_accounts = max_accounts
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> float | None:
        now = self._clock()
        with self._lock:
            locked_until = self._locked_until.get(key)
            if locked_until is None:
                return None
            if locked_until <= now:
                self._locked_until.pop(key, None)
                return None
            return locked_until - now

    def record_failure(self, key: str, settings: Settings) -> None:
        now = self._clock()
        window = settings.auth_failed_login_window_seconds
        with self._lock:
            failures = self._failures.setdefault(key, deque())
            cutoff = now - window
            while failures and failures[0] <= cutoff:
                failures.popleft()
            failures.append(now)

            if len(failures) >= settings.auth_max_failed_logins:
                self._locked_until[key] = now + settings.auth_lockout_seconds
                failures.clear()
            self._prune(now, window)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def _prune(self, now: float, window: int) -> None:
        if len(self._failures) <= self._max_accounts:
            return
        stale = [
            key
            for key, events in self._failures.items()
            if not events or events[-1] <= now - window
        ]
        for key in stale:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

        while len(self._failures) > self._max_accounts:
            oldest = min(
                self._failures,
                key=lambda key: self._failures[key][-1] if self._failures[key] else 0.0,
            )
            self._failures.pop(oldest, None)
            self._locked_until.pop(oldest, None)


class RedisLockoutStore:
    """Falhas de login e lockout no Redis, compartilhados entre processos."""

    def __init__(
        self,
        url: str,
        *,
        client: redis.Redis | None = None,
        prefix: str = _LOCK_PREFIX,
    ) -> None:
        self._client = client or _redis_client(url)
        self._prefix = prefix

    def retry_after(self, key: str) -> float | None:
        current = time.time()
        until_key = f"{self._prefix}:until:{key}"
        raw = _shared(self._client.get, until_key)
        if raw is None:
            return None
        locked_until = float(raw)
        if locked_until <= current:
            _shared(self._client.delete, until_key)
            return None
        return locked_until - current

    def record_failure(self, key: str, settings: Settings) -> None:
        current = time.time()
        _shared(
            self._client.eval,
            _LUA_RECORD_FAILURE,
            2,
            f"{self._prefix}:fail:{key}",
            f"{self._prefix}:until:{key}",
            current,
            settings.auth_failed_login_window_seconds,
            settings.auth_max_failed_logins,
            settings.auth_lockout_seconds,
            f"{current:.6f}-{uuid.uuid4().hex}",
        )

    def clear(self, key: str) -> None:
        _shared(
            self._client.delete,
            f"{self._prefix}:until:{key}",
            f"{self._prefix}:fail:{key}",
        )


def _new_limiter(settings: Settings) -> WindowLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisWindowLimiter(settings.redis_url)
    return RateLimiter()


def _new_lockout(
    settings: Settings,
    clock: Callable[[], float],
    max_accounts: int = 10_000,
) -> LockoutStore:
    if settings.rate_limit_backend == "redis":
        return RedisLockoutStore(settings.redis_url)
    return MemoryLockoutStore(clock=clock, max_accounts=max_accounts)


class AuthGuard:
    def __init__(
        self,
        settings: Settings,
        *,
        limiter: WindowLimiter | None = None,
        lockout: LockoutStore | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_accounts: int = 10_000,
    ) -> None:
        self._settings = settings
        self._limiter = limiter or _new_limiter(settings)
        self._lockout = lockout or _new_lockout(settings, clock, max_accounts)

    # -- limites por IP -------------------------------------------------

    def limit_login_ip(self, ip: str) -> None:
        self._consume(
            f"login:{ip}",
            self._settings.auth_login_limit,
            self._settings.auth_login_window_seconds,
            "rate_limited",
            "Muitas tentativas de login.",
        )

    def limit_register_ip(self, ip: str) -> None:
        self._consume(
            f"register:{ip}",
            self._settings.auth_register_limit,
            self._settings.auth_register_window_seconds,
            "rate_limited",
            "Muitos cadastros a partir deste IP.",
        )

    def limit_refresh_ip(self, ip: str) -> None:
        self._consume(
            f"refresh:{ip}",
            self._settings.auth_refresh_limit,
            self._settings.auth_refresh_window_seconds,
            "rate_limited",
            "Muitas renovações de sessão.",
        )

    # -- bloqueio por conta --------------------------------------------

    def check_login_account(self, email: str) -> None:
        """Bloqueia por email, inclusive inexistente, para não revelar contas."""
        retry_after = self._lockout.retry_after(_email_key(email))
        if retry_after is not None:
            self._raise_locked(retry_after, "Conta temporariamente bloqueada.")

    def record_login_failure(self, email: str) -> None:
        self._lockout.record_failure(_email_key(email), self._settings)

    def clear_login_failures(self, email: str) -> None:
        self._lockout.clear(_email_key(email))

    # -- internos -------------------------------------------------------

    def _consume(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        code: str,
        message: str,
    ) -> None:
        retry_after = self._limiter.consume(key, limit, window_seconds)
        if retry_after is not None:
            self._raise(retry_after, 429, code, message)

    @staticmethod
    def _raise(retry_after: float, status: int, code: str, message: str) -> None:
        seconds = max(1, math.ceil(retry_after))
        raise AppError(
            status,
            code,
            f"{message} Tente novamente em {seconds}s.",
            headers={"Retry-After": str(seconds)},
        )

    @staticmethod
    def _raise_locked(retry_after: float, message: str) -> None:
        AuthGuard._raise(retry_after, 429, "account_locked", message)


def _email_key(email: str) -> str:
    return email.strip().lower()


class ApiKeyGuard:
    """Rate limit por prefixo de API key, em janela deslizante."""

    def __init__(self, settings: Settings, *, limiter: WindowLimiter | None = None) -> None:
        self._settings = settings
        self._limiter = limiter or _new_limiter(settings)

    def check(self, key_prefix: str) -> None:
        retry_after = self._limiter.consume(
            f"api-key:{key_prefix}",
            self._settings.api_key_rate_limit,
            self._settings.api_key_rate_window_seconds,
        )
        if retry_after is None:
            return
        seconds = max(1, math.ceil(retry_after))
        raise AppError(
            429,
            "api_key_rate_limited",
            f"Rate limit da API key excedido. Tente novamente em {seconds}s.",
            headers={"Retry-After": str(seconds)},
        )


_guard: AuthGuard | None = None


def get_auth_guard() -> AuthGuard:
    global _guard
    if _guard is None:
        _guard = AuthGuard(get_settings())
    return _guard


def reset_auth_guard() -> None:
    global _guard
    _guard = None


_api_key_guard: ApiKeyGuard | None = None


def get_api_key_guard() -> ApiKeyGuard:
    global _api_key_guard
    if _api_key_guard is None:
        _api_key_guard = ApiKeyGuard(get_settings())
    return _api_key_guard


def reset_api_key_guard() -> None:
    global _api_key_guard
    _api_key_guard = None
