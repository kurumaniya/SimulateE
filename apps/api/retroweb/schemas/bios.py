from __future__ import annotations

from pydantic import BaseModel

from retroweb.library.systems import GameSystem


class BiosFileOut(BaseModel):
    filename: str
    description: str
    known_md5: str | None
    installed: bool
    size_bytes: int | None = None
    sha256: str | None = None
    md5: str | None = None
    # True/False when a known digest exists to compare against, else None.
    verified: bool | None = None


class SystemBiosOut(BaseModel):
    system: GameSystem
    note: str
    optional: bool
    ready: bool
    preferred_file: str | None
    files: list[BiosFileOut]
