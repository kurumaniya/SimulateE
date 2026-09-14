"""Route keys to providers by their first path segment.

``roms/...`` may live on one provider (say S3) while ``saves/...`` stays on
local disk. Phase 1 mounts a LocalStorageProvider per data sub-directory,
which also lets each directory be relocated through configuration.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import BinaryIO

from retroweb.storage.base import (
    DEFAULT_CHUNK_SIZE,
    InvalidStorageKeyError,
    StorageObject,
    StorageProvider,
    normalize_key,
)


class MountedStorage(StorageProvider):
    def __init__(self, mounts: dict[str, StorageProvider]) -> None:
        self._mounts = mounts

    def _route(self, key: str) -> tuple[StorageProvider, str]:
        normalized = normalize_key(key)
        mount, _, rest = normalized.partition("/")
        provider = self._mounts.get(mount)
        if provider is None:
            raise InvalidStorageKeyError(f"unknown storage mount '{mount}'")
        return provider, rest

    def exists(self, key: str) -> bool:
        provider, rest = self._route(key)
        return bool(rest) and provider.exists(rest)

    def read(self, key: str) -> bytes:
        provider, rest = self._route(key)
        return provider.read(rest)

    def write(self, key: str, data: bytes | BinaryIO) -> None:
        provider, rest = self._route(key)
        if not rest:
            raise InvalidStorageKeyError("cannot write to a mount root")
        provider.write(rest, data)

    def delete(self, key: str) -> None:
        provider, rest = self._route(key)
        if rest:
            provider.delete(rest)

    def size(self, key: str) -> int:
        provider, rest = self._route(key)
        return provider.size(rest)

    def modified_at(self, key: str) -> datetime:
        provider, rest = self._route(key)
        return provider.modified_at(rest)

    def stream(
        self,
        key: str,
        start: int = 0,
        end: int | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        provider, rest = self._route(key)
        return provider.stream(rest, start, end, chunk_size)

    def list(self, prefix: str) -> Iterator[StorageObject]:
        normalized = normalize_key(prefix)
        mount, _, rest = normalized.partition("/")
        provider = self._mounts.get(mount)
        if provider is None:
            raise InvalidStorageKeyError(f"unknown storage mount '{mount}'")
        for obj in provider.list(rest):
            yield StorageObject(
                key=f"{mount}/{obj.key}", size=obj.size, modified_at=obj.modified_at
            )
