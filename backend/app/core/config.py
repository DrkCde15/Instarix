"""Configuração do backend, lida do ambiente / backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://instarix:instarix@localhost:5432/instarix"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str
    jwt_issuer: str = "instarix"
    jwt_audience: str = "instarix-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Refresh token em cookie httpOnly para o navegador. O corpo da resposta
    # continua trazendo o token para clientes não-browser.
    auth_cookie_secure: bool | None = None
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_cookie_domain: str | None = None
    auth_refresh_cookie_name: str = "instarix_refresh"
    auth_cookie_path: str = "/v1/auth"

    # Só confie em X-Forwarded-For atrás de um proxy reverso controlado.
    trust_proxy_headers: bool = False

    # Proxies de conta: em produção recusa hosts privados por padrão.
    proxy_allow_private: bool | None = None

    # Chaves Fernet em CSV; a primeira criptografa, todas descriptografam.
    secrets_keys: str
    registration_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=list)

    # Rate limiting dos endpoints de auth (por IP, janela deslizante).
    # limit <= 0 desativa aquele limite.
    auth_login_limit: int = 10
    auth_login_window_seconds: int = 300
    auth_register_limit: int = 5
    auth_register_window_seconds: int = 3600
    auth_refresh_limit: int = 30
    auth_refresh_window_seconds: int = 300

    # Lockout temporário por conta após falhas de login.
    auth_max_failed_logins: int = 5
    auth_failed_login_window_seconds: int = 900
    auth_lockout_seconds: int = 900

    # Fila de jobs (Postgres como fonte da verdade).
    job_poll_interval_seconds: float = 2.0
    job_lock_timeout_seconds: int = 600
    job_backoff_base_seconds: int = 5
    job_worker_threads: int = 2
    # Sobe o worker no processo da API. Conveniente para desenvolvimento local;
    # em produção mantenha false e rode o worker como processo separado.
    embedded_worker_enabled: bool = False

    # Storage local de mídia; em produção use um volume compartilhado.
    media_storage_dir: str = str(BASE_DIR / "media")

    # Uploads de mídia para publicação (multipart).
    upload_max_bytes: int = 25 * 1024 * 1024

    # Webhooks: timeout, tentativas e backoff exponencial.
    webhook_timeout_seconds: float = 5.0
    webhook_max_attempts: int = 5
    webhook_backoff_base_seconds: int = 10

    # Rate limit por API key (janela deslizante, por processo).
    # limit <= 0 desativa.
    api_key_rate_limit: int = 600
    api_key_rate_window_seconds: int = 60

    # Quotas por plano. 0 significa ilimitado.
    quota_free_accounts: int = 3
    quota_free_jobs_per_day: int = 100
    quota_pro_accounts: int = 25
    quota_pro_jobs_per_day: int = 5000

    # RLS opt-in (PostgreSQL). Requer scripts/enable_rls.py e um role de
    # worker com BYPASSRLS. Desativado por padrão porque o SQLite dos testes
    # não suporta policies.
    rls_enabled: bool = False

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET precisa de ao menos 32 caracteres")
        return value

    @field_validator("secrets_keys")
    @classmethod
    def _secrets_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SECRETS_KEYS não pode ser vazio")
        return value

    @field_validator("cors_origins")
    @classmethod
    def _cors_origins_explicit(cls, value: list[str]) -> list[str]:
        # Com cookies de sessão o CORS usa credenciais; curinga é inválido e
        # transformaria qualquer site em origem confiável.
        if "*" in value:
            raise ValueError(
                "CORS_ORIGINS não aceita '*'; liste as origens exatas do frontend"
            )
        return value

    @model_validator(mode="after")
    def _cookie_flags_consistent(self) -> "Settings":
        # SameSite=None só é aceito por navegadores com Secure; sem isso o
        # cookie seria descartado ou trafegaria sem proteção.
        if self.auth_cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "AUTH_COOKIE_SAMESITE=none exige AUTH_COOKIE_SECURE=true"
            )
        return self

    @property
    def secret_key_list(self) -> list[str]:
        return [item.strip() for item in self.secrets_keys.split(",") if item.strip()]

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

    @property
    def cookie_secure(self) -> bool:
        return self.is_prod if self.auth_cookie_secure is None else self.auth_cookie_secure

    @property
    def allow_private_proxies(self) -> bool:
        if self.proxy_allow_private is None:
            return not self.is_prod
        return self.proxy_allow_private


@lru_cache
def get_settings() -> Settings:
    return Settings()
