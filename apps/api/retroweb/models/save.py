from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from retroweb.models.base import Base, IdMixin, TimestampMixin


class SaveType(enum.StrEnum):
    BATTERY = "battery"
    STATE = "state"


BATTERY_SLOT = 0
AUTO_STATE_SLOT = -1


class GameSave(IdMixin, TimestampMixin, Base):
    """Either a battery save (game-created) or a save state (emulator snapshot)."""

    __tablename__ = "game_saves"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", "save_type", "slot", name="uq_game_saves_slot"),
    )

    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    save_type: Mapped[str] = mapped_column(String(16), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    screenshot_key: Mapped[str | None] = mapped_column(String(1024))

    # Save states are only guaranteed to load in the exact core that wrote them.
    emulator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    core_id: Mapped[str | None] = mapped_column(String(64))
    core_version: Mapped[str | None] = mapped_column(String(64))

    # When the client last observed the data changing; used for newest-wins sync.
    client_modified_at: Mapped[datetime | None] = mapped_column(DateTime)
