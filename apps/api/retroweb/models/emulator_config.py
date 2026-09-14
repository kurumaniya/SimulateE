from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from retroweb.core.clock import utcnow
from retroweb.models.base import Base, IdMixin


class GameEmulatorConfig(IdMixin, Base):
    """Per-game emulator settings.

    ``config_json`` holds ``{"common": {...}, "adapter": {...}}``: common
    options every adapter understands (volume, etc.) plus adapter-specific
    options (PSP resolution scale, ...). Stored as text for portability.
    """

    __tablename__ = "game_emulator_configs"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", "emulator_id", name="uq_game_emulator_config"),
    )

    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    emulator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    core: Mapped[str | None] = mapped_column(String(64))
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
