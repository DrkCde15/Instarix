import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _clean_username(value: str) -> str:
    value = value.strip().lstrip("@")
    if not USERNAME_RE.match(value):
        raise ValueError("username inválido para o Instagram")
    return value


class AccountCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=31)
    password: str = Field(min_length=6, max_length=128)
    proxy: str | None = Field(default=None, max_length=500)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return _clean_username(value)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("label não pode ser vazio")
        return value


class AccountUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    proxy: str | None = Field(default=None, max_length=500)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("label não pode ser vazio")
        return value


class TwoFactorIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().replace(" ", "")
        if not re.fullmatch(r"[A-Za-z0-9-]{4,16}", value):
            raise ValueError("código de verificação inválido")
        return value


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    username: str
    status: str
    has_proxy: bool
    has_session: bool
    last_login_at: datetime | None
    last_error_code: str | None
    created_at: datetime


class LoginAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    method: str | None
    attempts: int
    error_code: str | None
    created_at: datetime
    expires_at: datetime | None
    finished_at: datetime | None


class AccountPage(BaseModel):
    items: list[AccountOut]
    next_cursor: str | None
