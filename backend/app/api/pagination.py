"""Cursor opaco (created_at, id) para paginação estável."""

import base64
import binascii
import uuid
from datetime import datetime

from app.core.errors import AppError
from app.core.time import as_utc


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{as_utc(created_at).isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp, _, raw_id = raw.partition("|")
        return as_utc(datetime.fromisoformat(timestamp)), uuid.UUID(raw_id)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise AppError(422, "invalid_cursor", "cursor inválido.") from exc
