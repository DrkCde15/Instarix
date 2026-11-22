"""Jobs, assets de mídia e snapshots de insights.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="queued", nullable=False
        ),
        sa.Column("priority", sa.SmallInteger(), server_default="5", nullable=False),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_jobs_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ig_accounts.id"],
            name="fk_jobs_account_id_ig_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_jobs_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index(
        "ix_jobs_claim", "jobs", ["status", "run_after", "priority"]
    )
    op.create_index(
        "ix_jobs_tenant_created", "jobs", ["tenant_id", "created_at"]
    )
    op.create_index(
        "uq_jobs_account_running",
        "jobs",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "uq_jobs_tenant_idempotency",
        "jobs",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("media_pk", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_media_assets_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ig_accounts.id"],
            name="fk_media_assets_account_id_ig_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
    )
    op.create_index(
        "uq_media_assets_account_media_kind",
        "media_assets",
        ["account_id", "media_pk", "kind"],
        unique=True,
    )
    op.create_index(
        "ix_media_assets_tenant_created",
        "media_assets",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "insights_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_insights_snapshots_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ig_accounts.id"],
            name="fk_insights_snapshots_account_id_ig_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_insights_snapshots"),
    )
    op.create_index(
        "ix_insights_snapshots_account_captured",
        "insights_snapshots",
        ["account_id", "captured_at"],
    )
    op.create_index(
        "ix_insights_snapshots_tenant_created",
        "insights_snapshots",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_insights_snapshots_tenant_created", table_name="insights_snapshots"
    )
    op.drop_index(
        "ix_insights_snapshots_account_captured", table_name="insights_snapshots"
    )
    op.drop_table("insights_snapshots")

    op.drop_index("ix_media_assets_tenant_created", table_name="media_assets")
    op.drop_index("uq_media_assets_account_media_kind", table_name="media_assets")
    op.drop_table("media_assets")

    op.drop_index("uq_jobs_tenant_idempotency", table_name="jobs")
    op.drop_index("uq_jobs_account_running", table_name="jobs")
    op.drop_index("ix_jobs_tenant_created", table_name="jobs")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
