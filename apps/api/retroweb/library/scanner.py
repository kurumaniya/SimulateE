"""Scan the ROM storage and reconcile it with the database.

The scanner is the only code that creates ``Game``/``GameFile`` rows from
files. It identifies files by SHA-256 so renames and moves are detected and
duplicates are skipped.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from retroweb.core.logging import get_logger
from retroweb.library.detection import HEADER_BYTES, Detection, detect_system
from retroweb.library.filenames import split_extension
from retroweb.library.metadata import FilenameMetadataProvider, GameMetadata, MetadataProvider
from retroweb.library.systems import GameSystem, all_extensions
from retroweb.models import Game, GameFile
from retroweb.storage import StorageObject, StorageProvider

log = get_logger(__name__)

ROM_PREFIX = "roms"


@dataclass
class ScannedFile:
    key: str
    filename: str
    extension: str
    size: int
    sha256: str
    detection: Detection
    metadata: GameMetadata


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

    def inspect(self, obj: StorageObject) -> ScannedFile | None:
        filename = obj.key.split("/")[-1]
        _, extension = split_extension(filename)
        if extension not in all_extensions():
            return None
        sha256, header = self.calculate_hash(obj.key)
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
        )

    # -- reconciliation ---------------------------------------------------

    def scan_directory(self, session: Session, prefix: str = ROM_PREFIX) -> ScanResult:
        result = ScanResult()
        seen_keys: set[str] = set()
        log.info("rom.scan.started", prefix=prefix)

        for obj in self.storage.list(prefix):
            try:
                scanned = self.inspect(obj)
            except Exception as exc:  # noqa: BLE001 - keep scanning other files
                log.warning("rom.scan.file_failed", key=obj.key, error=str(exc))
                result.errors.append(f"{obj.key}: {exc}")
                continue
            if scanned is None:
                result.skipped += 1
                continue
            seen_keys.add(scanned.key)
            self._reconcile_file(session, scanned, result)

        self._flag_missing(session, prefix, seen_keys, result)
        session.commit()
        log.info("rom.scan.finished", **result.as_dict())
        return result

    def scan_single(self, session: Session, key: str) -> GameFile:
        """Scan one freshly uploaded file and return its GameFile."""
        obj = StorageObject(
            key=key, size=self.storage.size(key), modified_at=self.storage.modified_at(key)
        )
        scanned = self.inspect(obj)
        if scanned is None:
            raise ValueError("file is not a recognised ROM")
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
            by_key.missing = False
            result.updated += 1
            log.info("rom.scan.replaced", key=scanned.key, game_id=by_key.game_id)
            return by_key

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
            region=scanned.metadata.region,
            label=scanned.metadata.label,
            is_primary=True,
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

    def _flag_missing(
        self, session: Session, prefix: str, seen_keys: set[str], result: ScanResult
    ) -> None:
        rows = session.scalars(
            select(GameFile).where(GameFile.storage_key.like(f"{prefix}/%"))
        ).all()
        for row in rows:
            present = row.storage_key in seen_keys
            if not present and not row.missing:
                row.missing = True
                result.missing += 1
                log.warning("rom.scan.missing", key=row.storage_key, game_id=row.game_id)
