"""Jobs assíncronos executados por conta."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"

    ALL = (QUEUED, RUNNING, AWAITING_INPUT, SUCCEEDED, FAILED, CANCELED)


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "run_after", "priority"),
        Index("ix_jobs_tenant_created", "tenant_id", "created_at"),
        # No máximo um job running por conta: é a garantia final da
        # serialização, mesmo com vários workers/dispatchers.
        Index(
            "uq_jobs_account_running",
            "account_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index(
            "uq_jobs_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ig_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, default=5, server_default="5", nullable=False
    )
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
