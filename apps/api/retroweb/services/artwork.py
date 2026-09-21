"""Fetch cover art from the libretro-thumbnails collection.

Only artwork is ever downloaded: a game's box art, looked up by the name of
the user's own ROM file. See ``library/artwork.py`` for the naming rules.
"""

from __future__ import annotations

import threading
import time
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from retroweb import __version__
from retroweb.core.config import Settings
from retroweb.core.database import get_session
from retroweb.core.errors import AppError
from retroweb.core.logging import get_logger
from retroweb.library.artwork import (
    THUMBNAIL_SYSTEM_DIRS,
    best_match,
    index_path,
    parse_index,
    thumbnail_name,
    thumbnail_path,
)
from retroweb.library.systems import GameSystem
from retroweb.models import Game
from retroweb.services import games as game_service
from retroweb.services.identify import GameDatabaseUnavailableError, GameIdentifier, identify_game
from retroweb.services.jobs import Job
from retroweb.storage import StorageProvider

log = get_logger(__name__)

FetchOutcome = Literal["fetched", "skipped", "not_found"]

INDEX_TTL_SECONDS = 24 * 3600
COVER_FETCH_JOB = "covers.fetch"


class MetadataUnavailableError(AppError):
    """The online metadata source could not be reached."""

    status_code = 502
    code = "metadata_unavailable"


class ArtworkFetcher:
    """HTTP client for the thumbnail server with a cached per-system index."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.enabled = settings.online_metadata
        self._client = httpx.Client(
            base_url=settings.thumbnails_base_url.rstrip("/"),
            timeout=settings.thumbnails_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": f"{settings.app_name}/{__version__}"},
            transport=transport,
        )
        self._index: dict[GameSystem, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def find_cover(self, system: GameSystem, rom_filename: str) -> tuple[str, bytes] | None:
        """``(thumbnail name, PNG bytes)`` for the file, or ``None`` when unknown."""
        if system not in THUMBNAIL_SYSTEM_DIRS:
            return None
        name = thumbnail_name(rom_filename)
        if not name:
            return None
        data = self._download(thumbnail_path(system, name))
        if data is not None:
            return name, data
        match = best_match(name, self.index(system))
        if match is None or match == name:
            return None
        data = self._download(thumbnail_path(system, match))
        return (match, data) if data is not None else None

    def index(self, system: GameSystem) -> list[str]:
        """Every thumbnail name the server has for ``system`` (cached for a day)."""
        with self._lock:
            cached = self._index.get(system)
            if cached and time.monotonic() - cached[0] < INDEX_TTL_SECONDS:
                return cached[1]
        response = self._get(index_path(system))
        names = parse_index(response.text) if response.status_code == 200 else []
        with self._lock:
            self._index[system] = (time.monotonic(), names)
        log.info("cover.index", system=system.value, entries=len(names))
        return names

    def _download(self, path: str) -> bytes | None:
        response = self._get(path)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise MetadataUnavailableError(f"Thumbnail server answered HTTP {response.status_code}")
        if not response.headers.get("content-type", "").startswith("image/"):
            return None
        return response.content

    def _get(self, path: str) -> httpx.Response:
        try:
            return self._client.get(path)
        except httpx.HTTPError as exc:
            raise MetadataUnavailableError(f"Thumbnail server unreachable: {exc}") from exc


def fetch_cover(
    db: Session,
    storage: StorageProvider,
    fetcher: ArtworkFetcher,
    game_id: str,
    *,
    force: bool,
    identifier: GameIdentifier | None = None,
) -> FetchOutcome:
    """Look the game's cover up online and store it; ``force`` replaces an existing one.

    Box art is filed under the release's database name, so a game that has not
    been identified yet is identified first (when an ``identifier`` is given):
    that is what finds the cover of a file with a translated or home-made name.
    """
    game = game_service.get_game(db, game_id)
    if game.cover_key and not force:
        return "skipped"
    if identifier is not None and identifier.enabled and not game.canonical_name:
        try:
            identify_game(db, storage, identifier, game)
        except GameDatabaseUnavailableError as exc:
            # The file name may still be a release name: carry on without the database.
            log.warning("cover.identify_unavailable", game_id=game.id, error=str(exc))
    primary = game.primary_file
    source_name = primary.filename if primary else f"{game.title}.rom"
    if game.canonical_name:
        source_name = f"{game.canonical_name}{primary.extension if primary else '.rom'}"
    found = fetcher.find_cover(GameSystem(game.system), source_name)
    if found is None:
        log.info("cover.not_found", game_id=game.id, system=game.system, name=source_name)
        return "not_found"
    name, data = found
    key = f"covers/{game.id}.png"
    if game.cover_key and game.cover_key != key:
        storage.delete(game.cover_key)
    storage.write(key, data)
    game_service.update_game(db, game.id, {"cover_key": key})
    log.info("cover.fetched", game_id=game.id, system=game.system, name=name, size=len(data))
    return "fetched"


def fetch_missing_covers(
    job: Job,
    storage: StorageProvider,
    fetcher: ArtworkFetcher,
    identifier: GameIdentifier | None = None,
) -> None:
    """Job body: fetch a cover for every game that has none."""
    for db in get_session():
        game_ids = list(
            db.scalars(select(Game.id).where(Game.cover_key.is_(None)).order_by(Game.title))
        )
        job.total = len(game_ids)
        for game_id in game_ids:
            try:
                outcome = fetch_cover(
                    db, storage, fetcher, game_id, force=False, identifier=identifier
                )
            except MetadataUnavailableError as exc:
                # The source is down: stop instead of failing every remaining game.
                job.error(str(exc))
                job.bump("failed")
                job.done += 1
                raise
            except Exception as exc:  # noqa: BLE001 - one bad game must not stop the batch
                job.bump("failed")
                job.error(f"{game_id}: {exc}")
                log.warning("cover.fetch_failed", game_id=game_id, error=str(exc))
            else:
                job.bump(outcome)
            job.done += 1
