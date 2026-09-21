"""games.canonical_name / identified_by, game_files.crc32 / sha1 / serial

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-21

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.add_column(sa.Column("canonical_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("identified_by", sa.String(length=16), nullable=True))
    with op.batch_alter_table("game_files", schema=None) as batch_op:
        batch_op.add_column(sa.Column("crc32", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("sha1", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("serial", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game_files", schema=None) as batch_op:
        batch_op.drop_column("serial")
        batch_op.drop_column("sha1")
        batch_op.drop_column("crc32")
    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.drop_column("identified_by")
        batch_op.drop_column("canonical_name")
