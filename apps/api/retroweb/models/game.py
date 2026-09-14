from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from retroweb.core.clock import utcnow
from retroweb.models.base import Base, IdMixin, TimestampMixin


class Game(IdMixin, TimestampMixin, Base):
    """A game in the library. Files are separate rows (see GameFile)."""

    __tablename__ = "games"

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title_en: Mapped[str | None] = mapped_column(String(255))
    title_ja: Mapped[str | None] = mapped_column(String(255))
    title_zh: Mapped[str | None] = mapped_column(String(255))

    # GameSystem id, e.g. "gba". Stored as a string so adding systems is not a migration.
    system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    cover_key: Mapped[str | None] = mapped_column(String(512))
    developer: Mapped[str | None] = mapped_column(String(255))
    publisher: Mapped[str | None] = mapped_column(String(255))
    release_date: Mapped[date | None] = mapped_column(Date)
    region: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    files: Mapped[list[GameFile]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="GameFile.created_at"
    )

    @property
    def primary_file(self) -> GameFile | None:
        for file in self.files:
            if file.is_primary:
                return file
        return self.files[0] if self.files else None


class GameFile(IdMixin, Base):
    """A concrete ROM file belonging to a game (region, revision, disc, hack...)."""

    __tablename__ = "game_files"
    __table_args__ = (UniqueConstraint("sha256", name="uq_game_files_sha256"),)

    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    missing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    game: Mapped[Game] = relationship(back_populates="files")
