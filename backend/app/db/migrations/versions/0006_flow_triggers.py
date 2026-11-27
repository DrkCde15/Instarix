"""Configuração de gatilho por polling nos fluxos.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode recria a tabela no SQLite, que não suporta ALTER FOREIGN KEY.
    with op.batch_alter_table("flows") as batch_op:
        batch_op.add_column(
            sa.Column(
                "trigger_source",
                sa.String(length=32),
                server_default=sa.text("'manual'"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "poll_interval_seconds",
                sa.Integer(),
                server_default=sa.text("30"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_seen_id", sa.String(length=120), nullable=True)
        )
        batch_op.create_index("ix_flows_account", ["account_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_flows_account_id_ig_accounts",
            "ig_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("flows") as batch_op:
        batch_op.drop_constraint(
            "fk_flows_account_id_ig_accounts", type_="foreignkey"
        )
        batch_op.drop_index("ix_flows_account")
        batch_op.drop_column("last_seen_id")
        batch_op.drop_column("last_poll_at")
        batch_op.drop_column("poll_interval_seconds")
        batch_op.drop_column("account_id")
        batch_op.drop_column("trigger_source")
