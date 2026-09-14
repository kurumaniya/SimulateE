from __future__ import annotations

from datetime import datetime

from retroweb.models import SaveType
from retroweb.schemas.common import ApiModel


class SaveOut(ApiModel):
    id: str
    game_id: str
    save_type: SaveType
    slot: int
    size_bytes: int
    has_screenshot: bool
    emulator_id: str
    core_id: str | None
    core_version: str | None
    client_modified_at: datetime | None
    created_at: datetime
    updated_at: datetime
