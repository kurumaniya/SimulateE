"""Minimal cue sheet parsing: which track files a .cue references."""

from __future__ import annotations

import re

_FILE_LINE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+\S+\s*$', re.IGNORECASE | re.MULTILINE)

MAX_CUE_BYTES = 64 * 1024


def referenced_files(cue_text: str) -> list[str]:
    """File names (as written, path components stripped) named by FILE lines."""
    names: list[str] = []
    for quoted, bare in _FILE_LINE.findall(cue_text):
        name = (quoted or bare).replace("\\", "/").split("/")[-1].strip()
        if name and name not in names:
            names.append(name)
    return names
