from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobCreate(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=10)
    run_after: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        return value.strip()

    @field_validator("idempotency_key")
    @classmethod
    def _idempotency_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key não pode ser vazio")
        return value


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None
    type: str
    payload: dict[str, Any]
    status: str
    priority: int
    run_after: datetime
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    idempotency_key: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class JobPage(BaseModel):
    items: list[JobOut]
    next_cursor: str | None
