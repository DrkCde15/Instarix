"""Fluxos de automação e suas execuções."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Flow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flows"
    __table_args__ = (Index("ix_flows_account", "account_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(
        String(40), default="geral", server_default=text("'geral'"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    graph: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    trigger_source: Mapped[str] = mapped_column(
        String(32), default="manual", server_default=text("'manual'"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ig_accounts.id", ondelete="SET NULL"), nullable=True
    )
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=30, server_default=text("30"), nullable=False
    )
    last_poll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class FlowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flow_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    context: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    steps: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
