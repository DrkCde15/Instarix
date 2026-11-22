"""Datas UTC (SQLite devolve datetimes sem timezone)."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Anexa UTC a datetimes naive vindos do banco."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
