"""Rate limiting e proteção contra brute force para endpoints de auth.

O estado é mantido em memória, por processo. Isso é suficiente para um único
worker; com múltiplos workers/instâncias os limites efetivos são multiplicados
pelo número de processos. Para implantação horizontal, substitua o store por
Redis (``REDIS_URL``) mantendo a interface de ``AuthGuard``.

As janelas usam ``time.monotonic()`` para não sofrer com ajustes de relógio.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from app.core.config import Settings, get_settings
from app.core.errors import AppError


class RateLimiter:
    """Janela deslizante por chave, com limite no número de chaves."""

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


class AuthGuard:
    def __init__(
        self,
        settings: Settings,
        *,
        limiter: RateLimiter | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_accounts: int = 10_000,
    ) -> None:
        self._settings = settings
        self._limiter = limiter or RateLimiter()
        self._clock = clock
        self._max_accounts = max_accounts
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

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
        """Falha com 429 se o email estiver em lockout.

        Aplicado a qualquer email (inclusive inexistente), para não revelar
        quais contas existem.
        """
        key = _email_key(email)
        now = self._clock()
        with self._lock:
            locked_until = self._locked_until.get(key)
            if locked_until is None:
                return
            if locked_until <= now:
                self._locked_until.pop(key, None)
                return
            retry_after = locked_until - now

        self._raise_locked(retry_after, "Conta temporariamente bloqueada.")

    def record_login_failure(self, email: str) -> None:
        key = _email_key(email)
        now = self._clock()
        window = self._settings.auth_failed_login_window_seconds

        with self._lock:
            failures = self._failures.setdefault(key, deque())
            cutoff = now - window
            while failures and failures[0] <= cutoff:
                failures.popleft()
            failures.append(now)

            if len(failures) >= self._settings.auth_max_failed_logins:
                self._locked_until[key] = now + self._settings.auth_lockout_seconds
                failures.clear()

            self._prune(now, window)

    def clear_login_failures(self, email: str) -> None:
        key = _email_key(email)
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

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

    @staticmethod
    def _raise(retry_after: float, status: int, code: str, message: str) -> None:
        seconds = max(1, math.ceil(retry_after))
        raise AppError(
            status,
            code,
            f"{message} Tente novamente em {seconds}s.",
            headers={"Retry-After": str(seconds)},
        )

    def _raise_locked(self, retry_after: float, message: str) -> None:
        self._raise(retry_after, 429, "account_locked", message)


def _email_key(email: str) -> str:
    return email.strip().lower()


class ApiKeyGuard:
    """Rate limit por prefixo de API key, em janela deslizante."""

    def __init__(
        self,
        settings: Settings,
        *,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._limiter = limiter or RateLimiter()

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
