"""Conta do Instagram: credenciais e sessão sempre criptografadas."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IgAccountStatus:
    PENDING_LOGIN = "pending_login"
    ACTIVE = "active"
    TWO_FA_REQUIRED = "2fa_required"
    CHALLENGE_REQUIRED = "challenge_required"
    NEEDS_REAUTH = "needs_reauth"
    DISABLED = "disabled"

    ALL = (
        PENDING_LOGIN,
        ACTIVE,
        TWO_FA_REQUIRED,
        CHALLENGE_REQUIRED,
        NEEDS_REAUTH,
        DISABLED,
    )


class IgAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ig_accounts"
    __table_args__ = (
        Index(
            "uq_ig_accounts_tenant_username",
            "tenant_id",
            text("lower(username)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_ig_accounts_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(30), nullable=False)

    # Ciphertext "<fingerprint>:<token>" (ver app.core.crypto).
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_settings_enc: Mapped[str] = mapped_column(Text, nullable=False)
    session_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        default=IgAccountStatus.PENDING_LOGIN,
        server_default=IgAccountStatus.PENDING_LOGIN,
        nullable=False,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def has_proxy(self) -> bool:
        return self.proxy_enc is not None

    @property
    def has_session(self) -> bool:
        return self.session_enc is not None
