"""Save upload/download endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile

from retroweb.api.deps import DbDep, SettingsDep, StorageDep, UserDep
from retroweb.api.serializers import save_out
from retroweb.api.uploads import read_bounded
from retroweb.core.errors import NotFoundError
from retroweb.models import SaveType
from retroweb.schemas.saves import SaveOut
from retroweb.services import games as game_service
from retroweb.services import saves as save_service

router = APIRouter(tags=["saves"])


@router.get("/games/{game_id}/saves", response_model=list[SaveOut])
def list_saves(
    game_id: str, db: DbDep, user: UserDep, save_type: SaveType | None = None
) -> list[SaveOut]:
    game_service.get_game(db, game_id)
    return [save_out(row) for row in save_service.list_saves(db, user, game_id, save_type)]


@router.post("/games/{game_id}/saves", response_model=SaveOut, status_code=201)
def upload_save(
    game_id: str,
    db: DbDep,
    user: UserDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    save_type: Annotated[SaveType, Form()],
    emulator_id: Annotated[str, Form(max_length=64)],
    slot: Annotated[int, Form()] = 0,
    core_id: Annotated[str | None, Form(max_length=64)] = None,
    core_version: Annotated[str | None, Form(max_length=64)] = None,
    client_modified_at: Annotated[datetime | None, Form()] = None,
    screenshot: Annotated[UploadFile | None, File()] = None,
) -> SaveOut:
    game = game_service.get_game(db, game_id)
    data = read_bounded(file, settings.max_save_upload_bytes)
    shot = read_bounded(screenshot, settings.max_cover_upload_bytes) if screenshot else None
    row = save_service.upsert_save(
        db,
        storage,
        user,
        game,
        save_type=save_type,
        slot=slot,
        data=data,
        emulator_id=emulator_id,
        core_id=core_id,
        core_version=core_version,
        screenshot=shot,
        client_modified_at=client_modified_at,
    )
    return save_out(row)


@router.get("/saves/{save_id}", response_model=SaveOut)
def get_save(save_id: str, db: DbDep, user: UserDep) -> SaveOut:
    return save_out(save_service.get_save(db, user, save_id))


@router.get("/saves/{save_id}/download")
def download_save(save_id: str, db: DbDep, user: UserDep, storage: StorageDep) -> Response:
    row = save_service.get_save(db, user, save_id)
    data = save_service.read_save_data(storage, row)
    filename = row.storage_key.rsplit("/", 1)[-1]
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Save-Updated-At": row.updated_at.isoformat(),
        },
    )


@router.get("/saves/{save_id}/screenshot")
def save_screenshot(save_id: str, db: DbDep, user: UserDep, storage: StorageDep) -> Response:
    row = save_service.get_save(db, user, save_id)
    if not row.screenshot_key or not storage.exists(row.screenshot_key):
        raise NotFoundError("This save has no screenshot")
    return Response(
        storage.read(row.screenshot_key),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.delete("/saves/{save_id}", status_code=204)
def delete_save(save_id: str, db: DbDep, user: UserDep, storage: StorageDep) -> Response:
    row = save_service.get_save(db, user, save_id)
    save_service.delete_save(db, storage, row)
    return Response(status_code=204)
