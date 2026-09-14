from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from retroweb.schemas.common import ApiModel
from retroweb.schemas.games import GameSummary


class PlaySessionCreate(BaseModel):
    game_id: str
    device: str | None = Field(default=None, max_length=255)
    emulator_id: str | None = Field(default=None, max_length=64)


class PlaySessionUpdate(BaseModel):
    action: Literal["heartbeat", "end"]


class PlaySessionOut(ApiModel):
    id: str
    game_id: str
    started_at: datetime
    last_heartbeat_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    device: str | None
    emulator_id: str | None
    heartbeat_interval_seconds: int


class RecentSessionOut(BaseModel):
    session: PlaySessionOut
    game: GameSummary
