"""Scan the ROM storage and reconcile it with the database.

The scanner is the only code that creates ``Game``/``GameFile`` rows from
files. It identifies files by SHA-256 so renames and moves are detected and
duplicates are skipped.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retroweb.core.logging import get_logger
from retroweb.library.cuesheet import MAX_CUE_BYTES, playlist_entries, referenced_files
from retroweb.library.detection import HEADER_BYTES, Detection, detect_system
from retroweb.library.filenames import split_extension
from retroweb.library.metadata import FilenameMetadataProvider, GameMetadata, MetadataProvider
from retroweb.library.systems import (
    CONTAINER_EXTENSIONS,
    CONTAINER_ORDER,
    GameSystem,
    all_extensions,
)
from retroweb.models import FILE_ROLE_COMPANION, FILE_ROLE_PRIMARY, Game, GameFile
from retroweb.storage import StorageObject, StorageProvider

log = get_logger(__name__)

ROM_PREFIX = "roms"

# (files inspected so far, files to inspect)
ProgressCallback = Callable[[int, int], None]


@dataclass
class ScannedFile:
    key: str
    filename: str
    extension: str
    size: int
    sha256: str
    detection: Detection
    metadata: GameMetadata
    modified_at: datetime | None = None
    role: str = FILE_ROLE_PRIMARY
    # Storage key of the container file (.cue / .m3u) this companion belongs to.
    parent_key: str | None = None
    # For a container: the storage keys of the files it names, in order.
    companion_keys: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    added: int = 0
    updated: int = 0
    missing: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "added": self.added,
            "updated": self.updated,
            "missing": self.missing,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class GameScanner:
    def __init__(
        self,
        storage: StorageProvider,
        metadata_providers: list[MetadataProvider] | None = None,
    ) -> None:
        self.storage = storage
        self.metadata_providers = metadata_providers or [FilenameMetadataProvider()]

    # -- pieces -----------------------------------------------------------

    def calculate_hash(self, key: str) -> tuple[str, bytes]:
        """Streaming SHA-256; also returns the first bytes for header sniffing."""
        digest = hashlib.sha256()
        header = b""
        for chunk in self.storage.stream(key):
            if len(header) < HEADER_BYTES:
                header += chunk[: HEADER_BYTES - len(header)]
            digest.update(chunk)
        return digest.hexdigest(), header

    def extract_basic_metadata(self, filename: str, system: GameSystem) -> GameMetadata:
        merged: GameMetadata | None = None
        for provider in self.metadata_providers:
            found = provider.from_filename(filename, system)
            if found is None:
                continue
            if merged is None:
                merged = found
            else:
                merged.merge_missing(found)
        return merged or GameMetadata(title=split_extension(filename)[0])

    def inspect(
        self, obj: StorageObject, companions: dict[str, str] | None = None
    ) -> ScannedFile | None:
        filename = obj.key.split("/")[-1]
        _, extension = split_extension(filename)
        if extension not in all_extensions():
            return None
        sha256, header = self.calculate_hash(obj.key)
        parent_key = (companions or {}).get(obj.key)
        if parent_key is not None:
            # Track data named by a cue sheet: it belongs to the cue's game.
            parent_detection = detect_system(parent_key, b"")
            return ScannedFile(
                key=obj.key,
                filename=filename,
                extension=extension,
                size=obj.size,
                sha256=sha256,
                detection=parent_detection,
                metadata=GameMetadata(title=split_extension(filename)[0]),
                modified_at=obj.modified_at,
                role=FILE_ROLE_COMPANION,
                parent_key=parent_key,
            )
        detection = detect_system(obj.key, header)
        if detection.system is None:
            return None
        metadata = self.extract_basic_metadata(filename, detection.system)
        return ScannedFile(
            key=obj.key,
            filename=filename,
            extension=extension,
            size=obj.size,
            sha256=sha256,
            detection=detection,
            metadata=metadata,
            modified_at=obj.modified_at,
        )

    def find_companions(self, objects: list[StorageObject]) -> tuple[dict[str, str], set[str]]:
        """Read playlists and cue sheets: ``(companion key → owning container key,
        every key a container names whether or not it exists)``.

        Playlists are read first: a cue sheet named by an ``.m3u`` belongs to
        the playlist, and so do the tracks that cue sheet names, so a
        multi-disc set is one game whose primary file is the playlist.
        """
        keys = {obj.key for obj in objects}
        companions: dict[str, str] = {}
        referenced: set[str] = set()
        containers = [
            (obj, split_extension(obj.key.split("/")[-1])[1])
            for obj in objects
            if split_extension(obj.key.split("/")[-1])[1] in CONTAINER_EXTENSIONS
            and obj.size <= MAX_CUE_BYTES
        ]
        containers.sort(key=lambda item: CONTAINER_ORDER.index(item[1]))
        for obj, extension in containers:
            folder = obj.key.rsplit("/", 1)[0]
            try:
                text = self.storage.read(obj.key).decode("utf-8", errors="replace")
            except OSError as exc:
                log.warning("rom.scan.cue_unreadable", key=obj.key, error=str(exc))
                continue
            names = playlist_entries(text) if extension == ".m3u" else referenced_files(text)
            # A cue sheet that is itself inside a playlist hands its tracks to the playlist.
            owner = companions.get(obj.key, obj.key)
            for name in names:
                candidate = f"{folder}/{name}"
                referenced.add(candidate)
                if candidate in keys and candidate != owner and candidate not in companions:
                    companions[candidate] = owner
        return companions, referenced

    @staticmethod
    def _attach_companion_keys(
        scanned_files: list[ScannedFile], companions: dict[str, str]
    ) -> None:
        by_container: dict[str, list[str]] = {}
        for companion_key, container_key in companions.items():
            by_container.setdefault(container_key, []).append(companion_key)
        for scanned in scanned_files:
            if scanned.role == FILE_ROLE_PRIMARY:
                scanned.companion_keys = by_container.get(scanned.key, [])

    # -- reconciliation ---------------------------------------------------

    def scan_directory(
        self,
        session: Session,
        prefix: str = ROM_PREFIX,
        progress: ProgressCallback | None = None,
    ) -> ScanResult:
        result = ScanResult()
        seen_keys: set[str] = set()
        log.info("rom.scan.started", prefix=prefix)

        objects = list(self.storage.list(prefix))
        companions, referenced = self.find_companions(objects)
        known = self._known_files(session, prefix)
        scanned_files: list[ScannedFile] = []
        for index, obj in enumerate(objects, start=1):
            if self._unchanged(obj, known):
                # Same key, size and mtime as when it was last hashed: keep the
                # row as it is. Reading a large image again on every rescan is
                # what makes a NAS-backed library unusable.
                seen_keys.add(obj.key)
                result.skipped += 1
                if progress:
                    progress(index, len(objects))
                continue
            try:
                scanned = self.inspect(obj, companions)
            except Exception as exc:  # noqa: BLE001 - keep scanning other files
                log.warning("rom.scan.file_failed", key=obj.key, error=str(exc))
                result.errors.append(f"{obj.key}: {exc}")
                continue
            finally:
                if progress:
                    progress(index, len(objects))
            if scanned is None:
                result.skipped += 1
                continue
            seen_keys.add(scanned.key)
            scanned_files.append(scanned)
        self._attach_companion_keys(scanned_files, companions)

        # Containers first so companions can attach to their game.
        scanned_files.sort(key=lambda item: item.role == FILE_ROLE_COMPANION)
        for scanned in scanned_files:
            self._reconcile_file(session, scanned, result)

        self._flag_missing(session, prefix, seen_keys, referenced, result)
        session.commit()
        log.info("rom.scan.finished", **result.as_dict())
        return result

    @staticmethod
    def _known_files(session: Session, prefix: str) -> dict[str, tuple[int, datetime | None]]:
        """Storage key → (size, mtime) of every present file already in the library."""
        rows = session.execute(
            select(GameFile.storage_key, GameFile.size_bytes, GameFile.file_modified_at).where(
                GameFile.storage_key.startswith(prefix + "/"), GameFile.missing.is_(False)
            )
        )
        return {key: (size, modified_at) for key, size, modified_at in rows}

    @staticmethod
    def _unchanged(obj: StorageObject, known: dict[str, tuple[int, datetime | None]]) -> bool:
        entry = known.get(obj.key)
        if entry is None:
            return False
        size, modified_at = entry
        if modified_at is None:
            return False
        return size == obj.size and modified_at.replace(microsecond=0) == obj.modified_at.replace(
            microsecond=0
        )

    def scan_single(self, session: Session, key: str) -> GameFile:
        """Scan one freshly uploaded file and return its GameFile."""
        obj = StorageObject(
            key=key, size=self.storage.size(key), modified_at=self.storage.modified_at(key)
        )
        folder = key.rsplit("/", 1)[0]
        siblings = list(self.storage.list(folder))
        companions, _referenced = self.find_companions(siblings)
        scanned = self.inspect(obj, companions)
        if scanned is None:
            raise ValueError("file is not a recognised ROM")
        self._attach_companion_keys([scanned], companions)
        result = ScanResult()
        game_file = self._reconcile_file(session, scanned, result)
        session.commit()
        return game_file

    def _reconcile_file(
        self, session: Session, scanned: ScannedFile, result: ScanResult
    ) -> GameFile:
        existing = session.scalar(select(GameFile).where(GameFile.sha256 == scanned.sha256))
        if existing is not None:
            changed = False
            if scanned.role == FILE_ROLE_COMPANION and existing.role != FILE_ROLE_COMPANION:
                # A disc that used to be its own game is now named by a playlist.
                parent = session.scalar(
                    select(GameFile).where(GameFile.storage_key == scanned.parent_key)
                )
                if parent is not None and parent.game_id != existing.game_id:
                    self._move_files(session, [existing], parent.game_id)
                    changed = True
            if existing.storage_key != scanned.key and self.storage.exists(existing.storage_key):
                # Identical content at two paths: keep the original, ignore the copy.
                result.skipped += 1
                log.info("rom.scan.duplicate", key=scanned.key, original=existing.storage_key)
                return existing
            if existing.storage_key != scanned.key:
                # The file was moved or renamed; keep following it by hash.
                # A stale row at the new key would violate uniqueness, so drop it.
                stale = session.scalar(select(GameFile).where(GameFile.storage_key == scanned.key))
                if stale is not None and stale.id != existing.id:
                    session.delete(stale)
                    session.flush()
                existing.storage_key = scanned.key
                existing.filename = scanned.filename
                changed = True
            if existing.missing:
                existing.missing = False
                changed = True
            if existing.file_modified_at != scanned.modified_at:
                existing.file_modified_at = scanned.modified_at
            if changed:
                result.updated += 1
                log.info("rom.scan.updated", key=scanned.key, game_id=existing.game_id)
            else:
                result.skipped += 1
            return existing

        by_key = session.scalar(select(GameFile).where(GameFile.storage_key == scanned.key))
        if by_key is not None:
            # Same path, different content: treat as a replaced file.
            by_key.sha256 = scanned.sha256
            by_key.size_bytes = scanned.size
            by_key.file_modified_at = scanned.modified_at
            by_key.missing = False
            result.updated += 1
            log.info("rom.scan.replaced", key=scanned.key, game_id=by_key.game_id)
            return by_key

        if scanned.role == FILE_ROLE_COMPANION:
            parent = session.scalar(
                select(GameFile).where(GameFile.storage_key == scanned.parent_key)
            )
            if parent is None:
                raise ValueError(f"companion {scanned.key} has no scanned container")
            game_file = GameFile(
                game_id=parent.game_id,
                storage_key=scanned.key,
                filename=scanned.filename,
                extension=scanned.extension,
                size_bytes=scanned.size,
                sha256=scanned.sha256,
                file_modified_at=scanned.modified_at,
                is_primary=False,
                role=FILE_ROLE_COMPANION,
            )
            session.add(game_file)
            session.flush()
            result.added += 1
            log.info("rom.scan.companion", key=scanned.key, game_id=parent.game_id)
            return game_file

        adopted = self._adopt_game(session, scanned)
        if adopted is not None:
            # A playlist arrived for discs that already had their own entries:
            # keep the first disc's game (and its saves), re-title it after the
            # playlist and demote every disc to a companion.
            game = adopted
            game.title = scanned.metadata.title
            game.region = scanned.metadata.region
            for row in game.files:
                row.is_primary = False
                row.role = FILE_ROLE_COMPANION
            log.info("rom.scan.adopted", key=scanned.key, game_id=game.id)
        else:
            game = Game(
                title=scanned.metadata.title,
                system=scanned.detection.system.value if scanned.detection.system else "",
                region=scanned.metadata.region,
                developer=scanned.metadata.developer,
                publisher=scanned.metadata.publisher,
                release_date=scanned.metadata.release_date,
                description=scanned.metadata.description,
            )
        game_file = GameFile(
            storage_key=scanned.key,
            filename=scanned.filename,
            extension=scanned.extension,
            size_bytes=scanned.size,
            sha256=scanned.sha256,
            file_modified_at=scanned.modified_at,
            region=scanned.metadata.region,
            label=scanned.metadata.label,
            is_primary=True,
            role=FILE_ROLE_PRIMARY,
        )
        game.files.append(game_file)
        session.add(game)
        session.flush()
        result.added += 1
        log.info(
            "rom.scan.added",
            key=scanned.key,
            game_id=game.id,
            system=game.system,
            detected_by=scanned.detection.reason,
        )
        return game_file

    def _adopt_game(self, session: Session, scanned: ScannedFile) -> Game | None:
        """The game a new container should join: the one owned by the first of
        its companions that is already a primary file, with every other
        companion's files moved over. ``None`` when no companion is known."""
        if not scanned.companion_keys:
            return None
        rows = session.scalars(
            select(GameFile).where(GameFile.storage_key.in_(scanned.companion_keys))
        ).all()
        by_key = {row.storage_key: row for row in rows}
        owner = next(
            (
                by_key[key]
                for key in scanned.companion_keys
                if key in by_key and by_key[key].role == FILE_ROLE_PRIMARY
            ),
            None,
        )
        if owner is None:
            return None
        game = owner.game
        self._move_files(session, [row for row in rows if row.game_id != game.id], game.id)
        session.refresh(game)
        return game

    def _move_files(self, session: Session, rows: list[GameFile], game_id: str) -> None:
        """Re-home files as companions of ``game_id``; games left empty are removed."""
        emptied: set[str] = set()
        for row in rows:
            emptied.add(row.game_id)
            row.game_id = game_id
            row.is_primary = False
            row.role = FILE_ROLE_COMPANION
        session.flush()
        for old_id in emptied:
            remaining = session.scalar(
                select(func.count(GameFile.id)).where(GameFile.game_id == old_id)
            )
            if not remaining:
                old = session.get(Game, old_id)
                if old is not None:
                    log.warning("rom.scan.merged_game_removed", game_id=old_id, title=old.title)
                    session.delete(old)
        session.flush()

    def _flag_missing(
        self,
        session: Session,
        prefix: str,
        seen_keys: set[str],
        referenced_keys: set[str],
        result: ScanResult,
    ) -> None:
        """Flag files that vanished. A companion that no container names any
        more (a renamed disc) is dropped instead, so the game stays playable."""
        rows = session.scalars(
            select(GameFile).where(GameFile.storage_key.like(f"{prefix}/%"))
        ).all()
        for row in rows:
            if row.storage_key in seen_keys:
                continue
            if row.role == FILE_ROLE_COMPANION and row.storage_key not in referenced_keys:
                log.info("rom.scan.companion_dropped", key=row.storage_key, game_id=row.game_id)
                session.delete(row)
                result.updated += 1
                continue
            if not row.missing:
                row.missing = True
                result.missing += 1
                log.warning("rom.scan.missing", key=row.storage_key, game_id=row.game_id)
