"""Identify library games against the No-Intro / Redump / FBNeo name lists.

The lists are the clrmamepro DATs of libretro-database: release names with
the digests and serials of known dumps. RetroWeb downloads a system's list
once, caches it on disk, and looks the user's own file up in it:

1. **hash**: SHA-1 (then CRC32) of the database-style dump;
2. **serial**: the product code inside the image. Translated and patched
   ROMs fail the digest but keep their serial;
3. **name**: the file name's title equals a release title (arcade sets match
   on the set's file name, which is how FBNeo itself finds them).

A match gives the game its canonical release name (used for cover art), an
English title, the region, and developer / publisher / release date when the
attribute lists have them. Fields the user already filled in are kept.

Only names and digests travel over the network; never game data.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from retroweb import __version__
from retroweb.core.config import Settings
from retroweb.core.database import get_session
from retroweb.core.errors import AppError
from retroweb.core.logging import get_logger
from retroweb.library.artwork import closest_release, normalize_title
from retroweb.library.datfile import DatGame, parse_dat
from retroweb.library.metadata import FilenameMetadataProvider
from retroweb.library.romid import (
    DISC_PROBE_BYTES,
    DISC_SYSTEMS,
    FULL_HASH_LIMIT,
    Fingerprint,
    fingerprint,
)
from retroweb.library.systems import CONTAINER_EXTENSIONS, GameSystem
from retroweb.models import Game, GameFile
from retroweb.services.jobs import Job
from retroweb.storage import StorageProvider

log = get_logger(__name__)

IdentifyOutcome = Literal["hash", "serial", "name", "not_found", "skipped"]

IDENTIFY_JOB = "library.identify"

# DAT file stem per system (the same names the thumbnail server uses) and the
# database folders that carry it.
SYSTEM_DATS: dict[GameSystem, tuple[str, tuple[str, ...]]] = {
    GameSystem.GB: ("Nintendo - Game Boy", ("no-intro",)),
    GameSystem.GBC: ("Nintendo - Game Boy Color", ("no-intro",)),
    GameSystem.GBA: ("Nintendo - Game Boy Advance", ("no-intro",)),
    GameSystem.NES: ("Nintendo - Nintendo Entertainment System", ("no-intro",)),
    GameSystem.SNES: ("Nintendo - Super Nintendo Entertainment System", ("no-intro",)),
    GameSystem.GENESIS: ("Sega - Mega Drive - Genesis", ("no-intro",)),
    GameSystem.N64: ("Nintendo - Nintendo 64", ("no-intro",)),
    GameSystem.NDS: ("Nintendo - Nintendo DS", ("no-intro",)),
    GameSystem.PS1: ("Sony - PlayStation", ("redump",)),
    GameSystem.PSP: ("Sony - PlayStation Portable", ("redump", "no-intro")),
    GameSystem.SATURN: ("Sega - Saturn", ("redump",)),
    GameSystem.ARCADE: ("FBNeo - Arcade Games", ("fbneo-split",)),
}
# Further name lists merged into a system's index: (folder, DAT stem). PSN
# downloads (NPJH-…, NPUG-… serials) live in their own No-Intro list.
EXTRA_DATS: dict[GameSystem, tuple[tuple[str, str], ...]] = {
    GameSystem.PSP: (("no-intro", "Sony - PlayStation Portable (PSN)"),),
}
# Systems whose games are found by the ROM set's file name, not its content.
SET_NAME_SYSTEMS: frozenset[GameSystem] = frozenset({GameSystem.ARCADE})

ATTRIBUTE_FOLDERS = ("developer", "publisher", "releaseyear", "releasemonth")

# Track data a cue sheet or playlist points at.
_TRACK_EXTENSIONS = (".bin", ".img", ".iso")
# A title that is only a short code without spaces: "2728", "2005C19", "SRHT", "cmplete-03".
_CATALOGUE_CODE = re.compile(r"^[A-Za-z0-9_-]{1,12}$")
_CJK = re.compile("[\u3400-\u9fff\uf900-\ufaff]")
_KANA = re.compile("[\u3040-\u30ff]")


class GameDatabaseUnavailableError(AppError):
    """The game database could not be downloaded and no cached copy exists."""

    status_code = 502
    code = "metadata_unavailable"


@dataclass(frozen=True)
class Release:
    name: str
    region: str | None
    crc: str | None
    attributes: tuple[tuple[str, str], ...] = ()


class SystemIndex:
    """Lookup tables over one system's releases."""

    def __init__(self, games: list[DatGame]) -> None:
        self.releases: list[Release] = []
        self.by_sha1: dict[str, int] = {}
        self.by_crc: dict[str, int] = {}
        self.by_serial: dict[str, list[int]] = {}
        self.by_title: dict[str, list[int]] = {}
        # Every attribute any source states for a release name (the developer,
        # publisher and release-date lists repeat the name with one field each).
        self.attributes_by_name: dict[str, dict[str, str]] = {}
        self.by_rom_name: dict[str, int] = {}
        for game in games:
            if not game.name:
                continue
            first_crc = next((rom.crc for rom in game.roms if rom.crc), None)
            position = len(self.releases)
            self.releases.append(
                Release(game.name, game.region, first_crc, tuple(sorted(game.attributes.items())))
            )
            self.by_title.setdefault(normalize_title(game.name), []).append(position)
            if game.attributes:
                merged = self.attributes_by_name.setdefault(game.name, {})
                for key, value in game.attributes.items():
                    merged.setdefault(key, value)
            serials = {game.serial} | {rom.serial for rom in game.roms}
            for serial in serials:
                if serial:
                    self.by_serial.setdefault(_serial_key(serial), []).append(position)
            for rom in game.roms:
                if rom.sha1:
                    self.by_sha1.setdefault(rom.sha1, position)
                if rom.crc:
                    self.by_crc.setdefault(rom.crc, position)
                if rom.name:
                    self.by_rom_name.setdefault(rom.name.lower(), position)

    def __len__(self) -> int:
        return len(self.releases)

    def _closest(self, wanted: str, positions: list[int]) -> Release | None:
        by_name = {self.releases[i].name: self.releases[i] for i in positions}
        best = closest_release(wanted, by_name)
        return by_name[best] if best else None

    def find(
        self, print_: Fingerprint | None, filename: str
    ) -> tuple[Release, Literal["hash", "serial", "name"]] | None:
        if print_ is not None:
            position = self.by_sha1.get(print_.sha1) if print_.sha1 else None
            if position is None and print_.crc32:
                position = self.by_crc.get(print_.crc32)
            if position is not None:
                return self.releases[position], "hash"
            if print_.serial:
                candidates = self.by_serial.get(_serial_key(print_.serial), [])
                release = self._closest(filename, candidates)
                if release is not None:
                    return release, "serial"
        position = self.by_rom_name.get(filename.lower())
        if position is not None:
            return self.releases[position], "name"
        title = normalize_title(filename.rsplit(".", 1)[0])
        release = self._closest(filename, self.by_title.get(title, [])) if title else None
        return (release, "name") if release is not None else None


def _serial_key(serial: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", serial.upper())


class GameIdentifier:
    """Downloads, caches and queries the per-system release lists."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.enabled = settings.online_metadata
        self._ttl_seconds = settings.gamedb_ttl_days * 24 * 3600
        self._cache_dir = settings.resolved_data_path() / "cache" / "gamedb"
        self._client = httpx.Client(
            base_url=settings.gamedb_base_url.rstrip("/"),
            timeout=settings.gamedb_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": f"{settings.app_name}/{__version__}"},
            transport=transport,
        )
        self._indexes: dict[GameSystem, tuple[float, SystemIndex]] = {}
        self._attributes: dict[tuple[GameSystem, str], tuple[float, dict[str, str]]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    # -- downloads ---------------------------------------------------------

    def _cache_file(self, folder: str, stem: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{folder}__{stem}")
        return self._cache_dir / f"{safe}.dat"

    def _load(self, folder: str, stem: str) -> str | None:
        """DAT text from the disk cache or the network; ``None`` when it does not exist."""
        cached = self._cache_file(folder, stem)
        fresh = cached.is_file() and time.time() - cached.stat().st_mtime < self._ttl_seconds
        if fresh:
            # An empty file records "the database has no such list" (a cached 404).
            return cached.read_text(encoding="utf-8", errors="replace") or None
        path = f"/metadat/{quote(folder)}/{quote(stem + '.dat')}"
        try:
            response = self._client.get(path)
        except httpx.HTTPError as exc:
            if cached.is_file():
                log.warning("gamedb.stale", folder=folder, system=stem, error=str(exc))
                return cached.read_text(encoding="utf-8", errors="replace") or None
            raise GameDatabaseUnavailableError(f"Game database unreachable: {exc}") from exc
        if response.status_code == 404:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(b"")
            return None
        if response.status_code != 200:
            if cached.is_file():
                return cached.read_text(encoding="utf-8", errors="replace") or None
            raise GameDatabaseUnavailableError(
                f"Game database answered HTTP {response.status_code}"
            )
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(response.content)
        log.info("gamedb.downloaded", folder=folder, system=stem, size=len(response.content))
        return response.text

    def index(self, system: GameSystem) -> SystemIndex | None:
        source = SYSTEM_DATS.get(system)
        if source is None:
            return None
        with self._lock:
            held = self._indexes.get(system)
            if held and time.monotonic() - held[0] < self._ttl_seconds:
                return held[1]
        stem, folders = source
        games: list[DatGame] = []
        # The attribute lists (developer, publisher, …) name releases the main
        # lists lack (PSP Minis, for one) and carry their serials, so they join
        # the index too; their attributes ride along on the Release.
        sources = (
            [(folder, stem) for folder in folders]
            + list(EXTRA_DATS.get(system, ()))
            + [(folder, stem) for folder in ATTRIBUTE_FOLDERS]
        )
        for folder, dat_stem in sources:
            text = self._load(folder, dat_stem)
            if text:
                games.extend(parse_dat(text))
        built = SystemIndex(games)
        with self._lock:
            self._indexes[system] = (time.monotonic(), built)
        log.info("gamedb.index", system=system.value, releases=len(built))
        return built

    def attribute(self, system: GameSystem, folder: str, crc: str) -> str | None:
        """One attribute (developer, publisher, …) of the release with this CRC."""
        source = SYSTEM_DATS.get(system)
        if source is None:
            return None
        key = (system, folder)
        with self._lock:
            held = self._attributes.get(key)
        if held is None or time.monotonic() - held[0] >= self._ttl_seconds:
            try:
                text = self._load(folder, source[0])
            except GameDatabaseUnavailableError as exc:
                # Attributes are a bonus: the release itself is already known.
                log.warning("gamedb.attribute_unavailable", folder=folder, error=str(exc))
                return None
            table: dict[str, str] = {}
            for game in parse_dat(text) if text else []:
                value = game.attributes.get(folder)
                if value:
                    for rom in game.roms:
                        if rom.crc:
                            table.setdefault(rom.crc, value)
            held = (time.monotonic(), table)
            with self._lock:
                self._attributes[key] = held
        return held[1].get(crc)


# -- applying a match --------------------------------------------------------


def _fingerprint_target(game: Game) -> GameFile | None:
    """The file whose content names the game: the ROM, or a disc's first data track."""
    primary = game.primary_file
    if primary is None:
        return None
    if primary.extension not in CONTAINER_EXTENSIONS and primary.extension != ".ccd":
        return primary
    tracks = [f for f in game.companion_files if f.extension in _TRACK_EXTENSIONS]
    return tracks[0] if tracks else None


def _release_date(year: str | None, month: str | None) -> date | None:
    if not year or not year.isdigit():
        return None
    month_number = int(month) if month and month.isdigit() and 1 <= int(month) <= 12 else 1
    try:
        return date(int(year), month_number, 1)
    except ValueError:
        return None


def identify_game(
    db: Session,
    storage: StorageProvider,
    identifier: GameIdentifier,
    game: Game,
    *,
    force: bool = False,
) -> IdentifyOutcome:
    """Look one game up and store what was found. Commits."""
    if game.canonical_name and not force:
        return "skipped"
    try:
        system = GameSystem(game.system)
    except ValueError:
        return "not_found"
    index = identifier.index(system)
    primary = game.primary_file
    if index is None or primary is None:
        return "not_found"

    print_: Fingerprint | None = None
    target = _fingerprint_target(game)
    if system not in SET_NAME_SYSTEMS and target is not None and not target.missing:
        if target.crc32 and target.sha1 and target.serial and not force:
            print_ = Fingerprint(target.crc32, target.sha1, target.size_bytes, target.serial)
        elif target.crc32 and target.sha1 and not force and storage.exists(target.storage_key):
            # Digests are known but no serial was read back then (an older probe):
            # re-read the head only, it is cheap and the serial may match now.
            head = fingerprint(
                system,
                storage.stream(target.storage_key, 0, DISC_PROBE_BYTES - 1),
                target.size_bytes,
                probe_only=True,
            )
            target.serial = head.serial
            print_ = Fingerprint(target.crc32, target.sha1, target.size_bytes, head.serial)
        elif storage.exists(target.storage_key):
            probe_only = system in DISC_SYSTEMS and target.size_bytes > FULL_HASH_LIMIT
            # A bounded range, not an abandoned full stream: leaving a FUSE file half
            # read and closing it early left the reader stuck in the kernel (2026-09-24).
            chunks = (
                storage.stream(target.storage_key, 0, DISC_PROBE_BYTES - 1)
                if probe_only
                else storage.stream(target.storage_key)
            )
            print_ = fingerprint(system, chunks, target.size_bytes, probe_only=probe_only)
            if not probe_only:
                target.crc32, target.sha1 = print_.crc32, print_.sha1
            target.serial = print_.serial

    found = index.find(print_, primary.filename)
    if found is None:
        db.commit()  # keep the digests: the next attempt need not hash again
        log.info("game.identify.not_found", game_id=game.id, system=game.system)
        return "not_found"

    release, how = found
    game.canonical_name = release.name
    game.identified_by = how
    parsed = FilenameMetadataProvider().from_filename(release.name + primary.extension, system)
    if parsed is not None:
        stem = primary.filename.rsplit(".", 1)[0]
        if (system in SET_NAME_SYSTEMS and game.title == stem) or _CATALOGUE_CODE.match(game.title):
            # The file name gave no real title: an arcade set name ("sf2") or a
            # bare catalogue code ("2728", "2005C19"). Use the release name.
            game.title = parsed.title
        if not game.title_en:
            game.title_en = parsed.title
        if not game.region and parsed.region:
            game.region = parsed.region
    if not game.region and release.region:
        game.region = release.region
    if not game.title_zh and not game.title_ja and _CJK.search(game.title):
        if _KANA.search(game.title):
            game.title_ja = game.title
        else:
            game.title_zh = game.title

    attributes = dict(release.attributes)
    # The attribute lists are keyed by CRC; a release matched by serial (or a
    # disc image that was only probed) still finds them by its exact name.
    for key, value in index.attributes_by_name.get(release.name, {}).items():
        attributes.setdefault(key, value)
    lookup = release.crc
    for folder in ATTRIBUTE_FOLDERS:
        if folder not in attributes and lookup:
            found_value = identifier.attribute(system, folder, lookup)
            if found_value:
                attributes[folder] = found_value
    if not game.developer and attributes.get("developer"):
        game.developer = attributes["developer"]
    if not game.publisher and attributes.get("publisher"):
        game.publisher = attributes["publisher"]
    if game.release_date is None:
        game.release_date = _release_date(
            attributes.get("releaseyear"), attributes.get("releasemonth")
        )
    db.commit()
    log.info(
        "game.identified", game_id=game.id, system=game.system, name=release.name, identified_by=how
    )
    return how


def identify_library(
    job: Job, storage: StorageProvider, identifier: GameIdentifier, *, force: bool = False
) -> None:
    """Job body: identify every game that has no canonical name yet."""
    for db in get_session():
        query = select(Game.id).order_by(Game.system, Game.title)
        if not force:
            query = query.where(Game.canonical_name.is_(None))
        game_ids = list(db.scalars(query))
        job.total = len(game_ids)
        for game_id in game_ids:
            game = db.get(Game, game_id)
            try:
                outcome = (
                    identify_game(db, storage, identifier, game, force=force)
                    if game is not None
                    else "not_found"
                )
            except GameDatabaseUnavailableError as exc:
                job.error(str(exc))
                job.bump("failed")
                job.done += 1
                raise
            except Exception as exc:  # noqa: BLE001 - one bad game must not stop the batch
                db.rollback()
                job.bump("failed")
                job.error(f"{game_id}: {exc}")
                log.warning("game.identify.failed", game_id=game_id, error=str(exc))
            else:
                job.bump(outcome)
            job.done += 1
