from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MediaListOut(BaseModel):
    job_id: UUID
    username: str
    items: list[dict[str, Any]]
    cached_at: datetime | None


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    media_pk: str
    kind: str
    size_bytes: int
    content_type: str
    created_at: datetime


class InsightsSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    data: dict[str, Any]
    captured_at: datetime
