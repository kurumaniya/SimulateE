"""Minimal cue sheet and playlist parsing: which files a .cue / .m3u references."""

from __future__ import annotations

import re

_FILE_LINE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+\S+\s*$', re.IGNORECASE | re.MULTILINE)

MAX_CUE_BYTES = 64 * 1024


def playlist_entries(m3u_text: str) -> list[str]:
    """File names listed by an .m3u (one per line, ``#`` comments ignored), in order."""
    names: list[str] = []
    for raw in m3u_text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        name = line.replace("\\", "/").split("/")[-1].strip()
        if name and name not in names:
            names.append(name)
    return names


def referenced_files(cue_text: str) -> list[str]:
    """File names (as written, path components stripped) named by FILE lines."""
    names: list[str] = []
    for quoted, bare in _FILE_LINE.findall(cue_text):
        name = (quoted or bare).replace("\\", "/").split("/")[-1].strip()
        if name and name not in names:
            names.append(name)
    return names
