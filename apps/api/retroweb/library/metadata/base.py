"""Metadata provider interface.

Phase 1 only derives metadata from the filename. Online providers
(ScreenScraper, IGDB, TheGamesDB) implement the same interface later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from retroweb.library.systems import GameSystem


@dataclass
class GameMetadata:
    title: str
    region: str | None = None
    developer: str | None = None
    publisher: str | None = None
    release_date: date | None = None
    description: str | None = None
    label: str | None = None  # e.g. "Rev 1", "Beta", "Translation"

    def merge_missing(self, other: GameMetadata) -> None:
        """Fill in fields this record lacks from ``other``."""
        for name in ("region", "developer", "publisher", "release_date", "description", "label"):
            if getattr(self, name) is None and getattr(other, name) is not None:
                setattr(self, name, getattr(other, name))


class MetadataProvider(ABC):
    id: str = "base"

    @abstractmethod
    def from_filename(self, filename: str, system: GameSystem) -> GameMetadata | None:
        """Cheap, offline extraction. Return ``None`` if nothing useful."""

    async def search_game(self, title: str, system: GameSystem) -> list[GameMetadata]:
        """Online lookup. Default: nothing."""
        return []
