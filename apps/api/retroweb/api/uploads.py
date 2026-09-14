"""Helpers for bounded multipart uploads."""

from __future__ import annotations

import tempfile
from typing import BinaryIO

from fastapi import UploadFile

from retroweb.core.errors import FileTooLargeError

CHUNK = 1024 * 1024


def read_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    """Read a small upload fully into memory, refusing oversized bodies early."""
    buffer = bytearray()
    while True:
        chunk = upload.file.read(CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise FileTooLargeError(f"File exceeds the limit of {max_bytes} bytes")
    return bytes(buffer)


def spool_bounded(upload: UploadFile, max_bytes: int) -> tuple[BinaryIO, int]:
    """Copy a large upload to a temporary file, enforcing the size limit."""
    spool: BinaryIO = tempfile.SpooledTemporaryFile(max_size=8 * CHUNK)  # type: ignore[assignment]
    total = 0
    while True:
        chunk = upload.file.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            spool.close()
            raise FileTooLargeError(f"File exceeds the limit of {max_bytes} bytes")
        spool.write(chunk)
    spool.seek(0)
    return spool, total
