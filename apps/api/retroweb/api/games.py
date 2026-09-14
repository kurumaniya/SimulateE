"""Game library endpoints: listing, details, favorites, scan, upload, ROM/cover."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from retroweb.api.deps import DbDep, ScannerDep, SettingsDep, StorageDep, UserDep
from retroweb.api.ranges import UnsatisfiableRangeError, parse_range
from retroweb.api.serializers import game_detail, game_summary
from retroweb.api.uploads import read_bounded, spool_bounded
from retroweb.core.errors import (
    DuplicateRomError,
    InvalidFilenameError,
    NotFoundError,
    RomMissingError,
    UnsupportedRomError,
    ValidationError,
)
from retroweb.core.logging import get_logger
from retroweb.library.filenames import sanitize_filename, split_extension
from retroweb.library.systems import GameSystem, is_extension_valid_for
from retroweb.schemas.games import (
    FavoriteRequest,
    GameDetail,
    GameListResponse,
    GameUpdate,
    ScanResponse,
)
from retroweb.services import games as game_service
from retroweb.services.games import SortKey

log = get_logger(__name__)
router = APIRouter(prefix="/games", tags=["games"])

COVER_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


@router.get("", response_model=GameListResponse)
def list_games(
    db: DbDep,
    user: UserDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    system: GameSystem | None = None,
    favorite: bool | None = None,
    sort: SortKey = "title",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GameListResponse:
    items, total = game_service.list_games(
        db, user, query=q, system=system, favorite=favorite, sort=sort, limit=limit, offset=offset
    )
    return GameListResponse(
        items=[game_summary(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.post("/scan", response_model=ScanResponse)
def scan_library(db: DbDep, scanner: ScannerDep, _user: UserDep) -> ScanResponse:
    result = scanner.scan_directory(db)
    return ScanResponse(**result.as_dict())


@router.post("/upload", response_model=GameDetail, status_code=201)
def upload_rom(
    db: DbDep,
    user: UserDep,
    storage: StorageDep,
    scanner: ScannerDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    system: Annotated[GameSystem, Form()],
) -> GameDetail:
    safe_name = sanitize_filename(file.filename or "")
    stem, extension = split_extension(safe_name)
    if not stem or not extension:
        raise InvalidFilenameError("Upload needs a file name with an extension")
    if not is_extension_valid_for(system, extension):
        raise UnsupportedRomError(f"'{extension}' is not a {system.value.upper()} ROM extension")

    key = f"roms/{system.value}/{safe_name}"
    if storage.exists(key):
        raise DuplicateRomError("A file with this name already exists in the library")

    spool, _size = spool_bounded(file, settings.max_rom_upload_bytes)
    try:
        storage.write(key, spool)
    finally:
        spool.close()

    try:
        game_file = scanner.scan_single(db, key)
    except ValueError as exc:
        storage.delete(key)
        raise UnsupportedRomError(str(exc)) from exc
    if game_file.storage_key != key:
        # Content already in the library under another path; keep the original.
        storage.delete(key)
        raise DuplicateRomError("This ROM is already in the library")
    log.info("rom.uploaded", key=key, game_id=game_file.game_id)
    return game_detail(game_service.get_game_item(db, user, game_file.game_id))


@router.get("/{game_id}", response_model=GameDetail)
def get_game(game_id: str, db: DbDep, user: UserDep) -> GameDetail:
    return game_detail(game_service.get_game_item(db, user, game_id))


@router.patch("/{game_id}", response_model=GameDetail)
def update_game(game_id: str, payload: GameUpdate, db: DbDep, user: UserDep) -> GameDetail:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("No fields to update")
    game_service.update_game(db, game_id, changes)
    return game_detail(game_service.get_game_item(db, user, game_id))


@router.post("/{game_id}/favorite", response_model=GameDetail)
def set_favorite(game_id: str, payload: FavoriteRequest, db: DbDep, user: UserDep) -> GameDetail:
    game_service.set_favorite(db, game_id, payload.favorite)
    return game_detail(game_service.get_game_item(db, user, game_id))


def _rom_response(
    game_id: str,
    db: DbDep,
    storage: StorageDep,
    range_header: str | None,
    if_none_match: str | None,
    head: bool,
) -> Response:
    game = game_service.get_game(db, game_id)
    game_file = game.primary_file
    if game_file is None or not storage.exists(game_file.storage_key):
        raise RomMissingError()
    total = storage.size(game_file.storage_key)
    etag = f'"{game_file.sha256}"'
    headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(game_file.filename)}",
        "Cross-Origin-Resource-Policy": "same-origin",
    }
    if if_none_match and etag in [tag.strip() for tag in if_none_match.split(",")]:
        return Response(status_code=304, headers=headers)
    try:
        byte_range = parse_range(range_header, total)
    except UnsatisfiableRangeError:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{total}"})

    if byte_range is None:
        start, end, status = 0, total - 1, 200
        headers["Content-Length"] = str(total)
    else:
        start, end, status = byte_range.start, byte_range.end, 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(byte_range.length)

    log.info("rom.serve", game_id=game_id, status=status, start=start, end=end)
    if head or total == 0:
        return Response(status_code=status, headers=headers, media_type="application/octet-stream")

    def body() -> Iterator[bytes]:
        yield from storage.stream(game_file.storage_key, start, end)

    return StreamingResponse(
        body(), status_code=status, headers=headers, media_type="application/octet-stream"
    )


@router.api_route("/{game_id}/rom", methods=["GET", "HEAD"])
def download_rom(
    game_id: str,
    request: Request,
    db: DbDep,
    storage: StorageDep,
    _user: UserDep,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    return _rom_response(
        game_id, db, storage, range_header, if_none_match, head=request.method == "HEAD"
    )


@router.api_route("/{game_id}/rom/{filename}", methods=["GET", "HEAD"])
def download_rom_named(
    game_id: str,
    filename: str,
    request: Request,
    db: DbDep,
    storage: StorageDep,
    _user: UserDep,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    """Same bytes as ``/rom``; the filename suffix gives browser caches a unique key.

    The filename is *only* compared against the stored name; it is never used
    to locate a file.
    """
    game = game_service.get_game(db, game_id)
    game_file = game.primary_file
    if game_file is None or game_file.filename != filename:
        raise NotFoundError("Unknown ROM file name for this game")
    return _rom_response(
        game_id, db, storage, range_header, if_none_match, head=request.method == "HEAD"
    )


@router.get("/{game_id}/cover")
def get_cover(game_id: str, db: DbDep, storage: StorageDep) -> Response:
    game = game_service.get_game(db, game_id)
    if not game.cover_key or not storage.exists(game.cover_key):
        raise NotFoundError("This game has no cover")
    extension = split_extension(game.cover_key)[1]
    media_type = next((mime for mime, ext in COVER_TYPES.items() if ext == extension), "image/jpeg")
    return Response(
        storage.read(game.cover_key),
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{game.updated_at.timestamp()}"',
        },
    )


@router.put("/{game_id}/cover", response_model=GameDetail)
def upload_cover(
    game_id: str,
    db: DbDep,
    user: UserDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
) -> GameDetail:
    game = game_service.get_game(db, game_id)
    extension = COVER_TYPES.get(file.content_type or "")
    if extension is None:
        raise ValidationError("Cover must be PNG, JPEG or WebP")
    data = read_bounded(file, settings.max_cover_upload_bytes)
    if not data:
        raise ValidationError("Cover file is empty")
    key = f"covers/{game.id}{extension}"
    if game.cover_key and game.cover_key != key:
        storage.delete(game.cover_key)
    storage.write(key, data)
    game_service.update_game(db, game_id, {"cover_key": key})
    return game_detail(game_service.get_game_item(db, user, game_id))
