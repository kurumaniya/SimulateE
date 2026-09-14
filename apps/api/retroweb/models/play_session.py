from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from retroweb.core.clock import utcnow
from retroweb.models.base import Base, IdMixin


class PlaySession(IdMixin, Base):
    """One sitting of one game. All timestamps are set by the server."""

    __tablename__ = "play_sessions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    device: Mapped[str | None] = mapped_column(String(255))
    emulator_id: Mapped[str | None] = mapped_column(String(64))
