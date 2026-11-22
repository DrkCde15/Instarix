from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.permissions import validate_scopes


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(min_length=1)

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: list[str]) -> list[str]:
        try:
            return validate_scopes(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    # A chave em claro é retornada apenas na criação.
    key: str
