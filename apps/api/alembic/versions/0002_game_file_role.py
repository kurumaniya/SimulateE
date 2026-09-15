"""game_files.role for companion files (cue/bin)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("game_files", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=16), server_default="primary", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("game_files", schema=None) as batch_op:
        batch_op.drop_column("role")
