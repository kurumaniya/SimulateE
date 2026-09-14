"""Battery saves and save states: upload, list, download, delete."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from retroweb.core.clock import as_utc
from retroweb.core.errors import NotFoundError, ValidationError
from retroweb.core.logging import get_logger
from retroweb.models import BATTERY_SLOT, Game, GameSave, SaveType, User
from retroweb.storage import StorageProvider

log = get_logger(__name__)

STATE_EXTENSION = ".state"
BATTERY_EXTENSION = ".sav"
MAX_STATE_SLOT = 9


def _validate_slot(save_type: SaveType, slot: int) -> None:
    if save_type is SaveType.BATTERY and slot != BATTERY_SLOT:
        raise ValidationError("Battery saves always use slot 0")
    if save_type is SaveType.STATE and not (-1 <= slot <= MAX_STATE_SLOT):
        raise ValidationError(f"State slot must be between -1 and {MAX_STATE_SLOT}")


def storage_key_for(user: User, game: Game, save_type: SaveType, slot: int) -> str:
    if save_type is SaveType.BATTERY:
        return f"saves/{user.id}/{game.id}/battery-{slot}{BATTERY_EXTENSION}"
    return f"states/{user.id}/{game.id}/state-{slot}{STATE_EXTENSION}"


def screenshot_key_for(user: User, game: Game, save_type: SaveType, slot: int) -> str:
    return f"screenshots/{user.id}/{game.id}/{save_type.value}-{slot}.png"


def list_saves(
    db: Session, user: User, game_id: str, save_type: SaveType | None = None
) -> list[GameSave]:
    stmt = select(GameSave).where(GameSave.user_id == user.id, GameSave.game_id == game_id)
    if save_type is not None:
        stmt = stmt.where(GameSave.save_type == save_type.value)
    stmt = stmt.order_by(GameSave.save_type.asc(), GameSave.slot.asc())
    return list(db.scalars(stmt))


def get_save(db: Session, user: User, save_id: str) -> GameSave:
    row = db.get(GameSave, save_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Save not found", code="save_not_found")
    return row


def upsert_save(
    db: Session,
    storage: StorageProvider,
    user: User,
    game: Game,
    *,
    save_type: SaveType,
    slot: int,
    data: bytes,
    emulator_id: str,
    core_id: str | None,
    core_version: str | None,
    screenshot: bytes | None,
    client_modified_at: datetime | None,
) -> GameSave:
    _validate_slot(save_type, slot)
    if not data:
        raise ValidationError("Save data is empty")

    key = storage_key_for(user, game, save_type, slot)
    storage.write(key, data)
    screenshot_key: str | None = None
    if screenshot:
        screenshot_key = screenshot_key_for(user, game, save_type, slot)
        storage.write(screenshot_key, screenshot)

    row = db.scalar(
        select(GameSave).where(
            GameSave.user_id == user.id,
            GameSave.game_id == game.id,
            GameSave.save_type == save_type.value,
            GameSave.slot == slot,
        )
    )
    if row is None:
        row = GameSave(
            game_id=game.id,
            user_id=user.id,
            save_type=save_type.value,
            slot=slot,
            storage_key=key,
            size_bytes=len(data),
            emulator_id=emulator_id,
        )
        db.add(row)
    row.storage_key = key
    row.size_bytes = len(data)
    row.emulator_id = emulator_id
    row.core_id = core_id
    row.core_version = core_version
    row.client_modified_at = as_utc(client_modified_at) if client_modified_at else None
    if screenshot_key:
        row.screenshot_key = screenshot_key
    db.commit()
    log.info(
        "save.upload",
        game_id=game.id,
        save_type=save_type.value,
        slot=slot,
        size=len(data),
        emulator=emulator_id,
        core=core_id,
    )
    return row


def read_save_data(storage: StorageProvider, row: GameSave) -> bytes:
    if not storage.exists(row.storage_key):
        raise NotFoundError("Save file is missing from storage", code="save_not_found")
    log.info("save.download", save_id=row.id, game_id=row.game_id, save_type=row.save_type)
    return storage.read(row.storage_key)


def delete_save(db: Session, storage: StorageProvider, row: GameSave) -> None:
    storage.delete(row.storage_key)
    if row.screenshot_key:
        storage.delete(row.screenshot_key)
    db.delete(row)
    db.commit()
    log.info("save.deleted", save_id=row.id, game_id=row.game_id, save_type=row.save_type)
