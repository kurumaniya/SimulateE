"""game_files.file_modified_at: lets a rescan skip hashing unchanged files

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("game_files", schema=None) as batch_op:
        batch_op.add_column(sa.Column("file_modified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game_files", schema=None) as batch_op:
        batch_op.drop_column("file_modified_at")
