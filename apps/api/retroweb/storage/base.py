"""Storage abstraction.

Business code addresses objects by *key* (``roms/gba/game.gba``) and never by
filesystem path, so the local provider can later be swapped for S3, MinIO or
WebDAV without touching services.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO

DEFAULT_CHUNK_SIZE = 1024 * 1024

_KEY_SEGMENT_FORBIDDEN = re.compile(r"[\x00\\]")


class InvalidStorageKeyError(ValueError):
    """The key is malformed or would escape the storage root."""


@dataclass(frozen=True)
class StorageObject:
    key: str
    size: int
    modified_at: datetime


def normalize_key(key: str) -> str:
    """Validate and canonicalise a storage key.

    Keys are ``/``-separated relative paths. Absolute paths, ``..`` segments,
    backslashes and control characters are rejected outright rather than
    "cleaned", because a rejected request is safer than a guessed one.
    """
    if not isinstance(key, str) or not key:
        raise InvalidStorageKeyError("empty key")
    if _KEY_SEGMENT_FORBIDDEN.search(key):
        raise InvalidStorageKeyError("key contains forbidden characters")
    if key.startswith("/") or re.match(r"^[A-Za-z]:", key):
        raise InvalidStorageKeyError("key must be relative")
    segments = key.split("/")
    cleaned: list[str] = []
    for segment in segments:
        if segment in ("", "."):
            continue
        if segment == "..":
            raise InvalidStorageKeyError("key must not contain '..'")
        cleaned.append(segment)
    if not cleaned:
        raise InvalidStorageKeyError("empty key")
    return "/".join(cleaned)


class StorageProvider(ABC):
    """Minimal object-store style interface.

    ``read``/``write`` are for small objects (saves, covers). Large objects
    (ROMs) go through ``stream`` so they never sit in memory at once.
    """

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def write(self, key: str, data: bytes | BinaryIO) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def modified_at(self, key: str) -> datetime: ...

    @abstractmethod
    def stream(
        self,
        key: str,
        start: int = 0,
        end: int | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        """Yield bytes ``[start, end]`` (inclusive end, like HTTP ranges)."""

    @abstractmethod
    def list(self, prefix: str) -> Iterator[StorageObject]:
        """Recursively list objects under ``prefix``."""
