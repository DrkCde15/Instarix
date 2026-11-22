"""Assets de mídia baixados e snapshots de insights."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index(
            "uq_media_assets_account_media_kind",
            "account_id",
            "media_pk",
            "kind",
            unique=True,
        ),
        Index("ix_media_assets_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ig_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_pk: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)


class InsightsSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "insights_snapshots"
    __table_args__ = (
        Index(
            "ix_insights_snapshots_account_captured",
            "account_id",
            "captured_at",
        ),
        Index("ix_insights_snapshots_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ig_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
