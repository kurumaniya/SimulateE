"""Play session endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from retroweb.api.deps import DbDep, SettingsDep, UserDep
from retroweb.api.serializers import game_summary, session_out
from retroweb.schemas.sessions import (
    PlaySessionCreate,
    PlaySessionOut,
    PlaySessionUpdate,
    RecentSessionOut,
)
from retroweb.services import games as game_service
from retroweb.services import sessions as session_service

router = APIRouter(prefix="/play-sessions", tags=["play-sessions"])


@router.post("", response_model=PlaySessionOut, status_code=201)
def start(
    payload: PlaySessionCreate, db: DbDep, user: UserDep, settings: SettingsDep
) -> PlaySessionOut:
    row = session_service.start_session(
        db, user, settings, payload.game_id, payload.device, payload.emulator_id
    )
    return session_out(row, settings)


@router.get("/recent", response_model=list[RecentSessionOut])
def recent(
    db: DbDep,
    user: UserDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RecentSessionOut]:
    session_service.close_stale_sessions(db, user, settings)
    db.commit()
    rows = session_service.recent_sessions(db, user, limit)
    out: list[RecentSessionOut] = []
    for row in rows:
        item = game_service.get_game_item(db, user, row.game_id)
        out.append(RecentSessionOut(session=session_out(row, settings), game=game_summary(item)))
    return out


@router.patch("/{session_id}", response_model=PlaySessionOut)
def update(
    session_id: str, payload: PlaySessionUpdate, db: DbDep, user: UserDep, settings: SettingsDep
) -> PlaySessionOut:
    if payload.action == "heartbeat":
        row = session_service.heartbeat(db, user, session_id)
    else:
        row = session_service.end_session(db, user, settings, session_id)
    return session_out(row, settings)
