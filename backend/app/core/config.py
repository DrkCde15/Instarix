"""Configuração do backend, lida do ambiente / backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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

    # Storage local de mídia; em produção use um volume compartilhado.
    media_storage_dir: str = str(BASE_DIR / "media")

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

    @property
    def secret_key_list(self) -> list[str]:
        return [item.strip() for item in self.secrets_keys.split(",") if item.strip()]

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
