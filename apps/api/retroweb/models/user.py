from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from retroweb.core.clock import utcnow
from retroweb.models.base import Base, IdMixin


class User(IdMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Nullable so the implicit single-user account has no password. Real
    # accounts store an scrypt hash produced by services/auth.py.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Admins manage the library (scan, uploads, BIOS, covers) and other users.
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class UserSession(IdMixin, Base):
    """A browser login. The cookie carries a random token; only its hash is stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))


class UserFavorite(Base):
    """A game one user marked as favorite."""

    __tablename__ = "user_favorites"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
