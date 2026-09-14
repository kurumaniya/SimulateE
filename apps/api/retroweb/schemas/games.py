from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from retroweb.library.systems import GameSystem
from retroweb.schemas.common import ApiModel


class GameFileOut(ApiModel):
    id: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str
    region: str | None
    label: str | None
    is_primary: bool
    missing: bool


class GameSummary(ApiModel):
    id: str
    title: str
    system: GameSystem
    favorite: bool
    region: str | None
    has_cover: bool
    rom_missing: bool
    play_time_seconds: int
    last_played_at: datetime | None
    has_auto_state: bool
    created_at: datetime


class GameDetail(GameSummary):
    title_en: str | None
    title_ja: str | None
    title_zh: str | None
    developer: str | None
    publisher: str | None
    release_date: date | None
    description: str | None
    rom_filename: str | None
    rom_hash: str | None
    rom_size: int | None
    files: list[GameFileOut]
    updated_at: datetime


class GameListResponse(BaseModel):
    items: list[GameSummary]
    total: int
    limit: int
    offset: int


class GameUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    title_ja: str | None = Field(default=None, max_length=255)
    title_zh: str | None = Field(default=None, max_length=255)
    developer: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    release_date: date | None = None
    region: str | None = Field(default=None, max_length=64)
    description: str | None = None


class FavoriteRequest(BaseModel):
    favorite: bool


class ScanResponse(BaseModel):
    added: int
    updated: int
    missing: int
    skipped: int
    errors: list[str]


class PlatformSummary(BaseModel):
    system: GameSystem
    name: str
    short_name: str
    count: int
    supported: bool


class HomeResponse(BaseModel):
    continue_playing: list[GameSummary]
    recently_played: list[GameSummary]
    recently_added: list[GameSummary]
    favorites: list[GameSummary]
    platforms: list[PlatformSummary]


class SystemOut(BaseModel):
    id: GameSystem
    name: str
    short_name: str
    manufacturer: str
    extensions: list[str]
    supported: bool
