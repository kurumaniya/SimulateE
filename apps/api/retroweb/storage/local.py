"""Filesystem-backed StorageProvider."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from retroweb.storage.base import (
    DEFAULT_CHUNK_SIZE,
    InvalidStorageKeyError,
    StorageObject,
    StorageProvider,
    normalize_key,
)


class LocalStorageProvider(StorageProvider):
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """Resolve a key to a path *inside* the root, or raise."""
        normalized = normalize_key(key)
        candidate = (self.root / normalized).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise InvalidStorageKeyError("key escapes storage root") from exc
        return candidate

    def _key_for(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write(self, key: str, data: bytes | BinaryIO) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling temp file and rename so readers never see a
        # half-written save.
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("wb") as handle:
            if isinstance(data, bytes | bytearray | memoryview):
                handle.write(data)
            else:
                shutil.copyfileobj(data, handle, DEFAULT_CHUNK_SIZE)
        os.replace(tmp, path)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def modified_at(self, key: str) -> datetime:
        mtime = self._path(key).stat().st_mtime
        return datetime.fromtimestamp(mtime, UTC).replace(tzinfo=None)

    def stream(
        self,
        key: str,
        start: int = 0,
        end: int | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        path = self._path(key)
        total = path.stat().st_size
        last = total - 1 if end is None else min(end, total - 1)
        remaining = last - start + 1
        if remaining <= 0:
            return
        with path.open("rb") as handle:
            handle.seek(start)
            while remaining > 0:
                chunk = handle.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def list(self, prefix: str) -> Iterator[StorageObject]:
        base = self._path(prefix) if prefix else self.root
        if not base.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                full = Path(dirpath) / name
                stat = full.stat()
                yield StorageObject(
                    key=self._key_for(full),
                    size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, UTC).replace(tzinfo=None),
                )
