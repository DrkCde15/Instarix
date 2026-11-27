"""Descrição e categoria dos fluxos.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("flows") as batch_op:
        batch_op.add_column(sa.Column("description", sa.String(length=500), nullable=True))
        batch_op.add_column(
            sa.Column(
                "category",
                sa.String(length=40),
                server_default=sa.text("'geral'"),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("flows") as batch_op:
        batch_op.drop_column("category")
        batch_op.drop_column("description")
