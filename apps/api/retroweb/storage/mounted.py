"""Route keys to providers by prefix.

``roms/...`` may live on one provider (say S3) while ``saves/...`` stays on
local disk. Mounts are keyed by a key prefix and may nest: ``roms`` on local
disk with ``roms/psp`` on a NAS mount. A key is routed to the mount with the
longest matching prefix, and listing a parent hides whatever a nested mount
shadows, so the two never disagree about where ``roms/psp/x.iso`` lives.
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
        self._mounts = {normalize_key(prefix): provider for prefix, provider in mounts.items()}
        # Longest prefix first so nested mounts win over their parent.
        self._order = sorted(self._mounts, key=len, reverse=True)

    def _route(self, key: str) -> tuple[str, StorageProvider, str]:
        """``(mount prefix, provider, key inside the mount)`` for ``key``."""
        normalized = normalize_key(key)
        for prefix in self._order:
            if normalized == prefix:
                return prefix, self._mounts[prefix], ""
            if normalized.startswith(prefix + "/"):
                return prefix, self._mounts[prefix], normalized[len(prefix) + 1 :]
        mount = normalized.partition("/")[0]
        raise InvalidStorageKeyError(f"unknown storage mount '{mount}'")

    def _shadowed_by(self, prefix: str) -> list[str]:
        """Mount prefixes nested inside ``prefix`` (their keys are not this mount's)."""
        return [other for other in self._mounts if other.startswith(prefix + "/")]

    def exists(self, key: str) -> bool:
        _, provider, rest = self._route(key)
        return bool(rest) and provider.exists(rest)

    def read(self, key: str) -> bytes:
        _, provider, rest = self._route(key)
        return provider.read(rest)

    def write(self, key: str, data: bytes | BinaryIO) -> None:
        _, provider, rest = self._route(key)
        if not rest:
            raise InvalidStorageKeyError("cannot write to a mount root")
        provider.write(rest, data)

    def delete(self, key: str) -> None:
        _, provider, rest = self._route(key)
        if rest:
            provider.delete(rest)

    def size(self, key: str) -> int:
        _, provider, rest = self._route(key)
        return provider.size(rest)

    def modified_at(self, key: str) -> datetime:
        _, provider, rest = self._route(key)
        return provider.modified_at(rest)

    def stream(
        self,
        key: str,
        start: int = 0,
        end: int | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        _, provider, rest = self._route(key)
        return provider.stream(rest, start, end, chunk_size)

    def list(self, prefix: str) -> Iterator[StorageObject]:
        """Objects under ``prefix`` across the mount it lands in and any mounts nested in it."""
        normalized = normalize_key(prefix)
        mount, provider, rest = self._route(normalized)
        shadows = self._shadowed_by(mount)
        for obj in provider.list(rest):
            key = f"{mount}/{obj.key}"
            if any(key.startswith(other + "/") for other in shadows):
                continue  # a nested mount owns this path
            yield StorageObject(key=key, size=obj.size, modified_at=obj.modified_at)
        for other in sorted(shadows):
            if other == normalized or other.startswith(normalized + "/"):
                inner_rest = ""
            elif normalized.startswith(other + "/"):
                inner_rest = normalized[len(other) + 1 :]
            else:
                continue
            for obj in self._mounts[other].list(inner_rest):
                yield StorageObject(
                    key=f"{other}/{obj.key}", size=obj.size, modified_at=obj.modified_at
                )
