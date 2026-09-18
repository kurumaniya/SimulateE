"""users.is_admin, login sessions, per-user favorites

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-18

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), server_default="0", nullable=False))

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.create_index("ix_user_sessions_user_id", ["user_id"], unique=False)

    op.create_table(
        "user_favorites",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "game_id"),
    )
    with op.batch_alter_table("user_favorites", schema=None) as batch_op:
        batch_op.create_index("ix_user_favorites_game_id", ["game_id"], unique=False)

    # The global favorite flag becomes a favorite for every existing user
    # (single-user mode has exactly one).
    op.execute(
        "INSERT INTO user_favorites (user_id, game_id, created_at) "
        "SELECT u.id, g.id, CURRENT_TIMESTAMP FROM games g CROSS JOIN users u WHERE g.favorite"
    )
    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.drop_column("favorite")


def downgrade() -> None:
    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.add_column(sa.Column("favorite", sa.Boolean(), server_default="0", nullable=False))
    op.execute("UPDATE games SET favorite = 1 WHERE id IN (SELECT game_id FROM user_favorites)")
    op.drop_table("user_favorites")
    op.drop_table("user_sessions")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_admin")
