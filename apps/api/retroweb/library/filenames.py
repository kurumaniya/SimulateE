"""Filename helpers shared by the scanner and upload endpoints."""

from __future__ import annotations

import re
import unicodedata

_UNSAFE = re.compile(r"[^\w\s\-.()\[\]&',!+]", re.UNICODE)
_MULTI_SPACE = re.compile(r"\s+")


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Reduce an untrusted upload filename to a safe basename.

    Keeps letters (any script), digits, spaces and the punctuation common in
    ROM names. Strips directory components, control characters and leading
    dots so the result can never be a hidden file or path traversal.
    """
    base = name.replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")
    base = _UNSAFE.sub("", base)
    base = _MULTI_SPACE.sub(" ", base).strip().lstrip(".")
    if len(base) > max_length:
        stem, dot, ext = base.rpartition(".")
        if dot and len(ext) <= 8:
            base = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            base = base[:max_length]
    return base


def split_extension(filename: str) -> tuple[str, str]:
    """Return (stem, '.ext') with a lowercase extension."""
    stem, dot, ext = filename.rpartition(".")
    if not dot or not stem:
        return filename, ""
    return stem, "." + ext.lower()
