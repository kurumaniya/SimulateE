from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    total: int
    done: int
    counters: dict[str, int]
    errors: list[str]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
