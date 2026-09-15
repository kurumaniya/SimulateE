"""BIOS file inventory: what is installed, uploads, deletion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from retroweb.core.errors import NotFoundError, UnsupportedRomError, ValidationError
from retroweb.core.logging import get_logger
from retroweb.library.bios import (
    BIOS_REGISTRY,
    BiosSpec,
    SystemBiosInfo,
    bios_spec,
    bios_storage_key,
    spec_for_md5,
)
from retroweb.library.filenames import sanitize_filename
from retroweb.library.systems import GameSystem
from retroweb.storage import StorageProvider

log = get_logger(__name__)


@dataclass
class InstalledBios:
    spec: BiosSpec
    size_bytes: int
    sha256: str
    md5: str
    verified: bool | None  # None when the registry has no digest to compare


@dataclass
class SystemBiosStatus:
    info: SystemBiosInfo
    installed: list[InstalledBios]

    @property
    def ready(self) -> bool:
        return bool(self.installed) or self.info.optional


def _digests(data: bytes) -> tuple[str, str]:
    return hashlib.sha256(data).hexdigest(), hashlib.md5(data).hexdigest()  # noqa: S324


def inspect_system(storage: StorageProvider, info: SystemBiosInfo) -> SystemBiosStatus:
    installed: list[InstalledBios] = []
    for spec in info.files:
        key = bios_storage_key(info.system, spec.filename)
        if not storage.exists(key):
            continue
        data = storage.read(key)
        sha256, md5 = _digests(data)
        installed.append(
            InstalledBios(
                spec=spec,
                size_bytes=len(data),
                sha256=sha256,
                md5=md5,
                verified=(md5 == spec.md5) if spec.md5 else None,
            )
        )
    return SystemBiosStatus(info=info, installed=installed)


def inventory(storage: StorageProvider) -> list[SystemBiosStatus]:
    return [inspect_system(storage, info) for info in BIOS_REGISTRY.values()]


def system_status(storage: StorageProvider, system: GameSystem) -> SystemBiosStatus:
    info = BIOS_REGISTRY.get(system)
    if info is None:
        raise NotFoundError(f"{system.value} does not use a BIOS")
    return inspect_system(storage, info)


def install(
    storage: StorageProvider, system: GameSystem, original_name: str, data: bytes
) -> InstalledBios:
    """Store an uploaded BIOS under its canonical name.

    The file is accepted when its name is in the registry for the system, or
    when its MD5 matches a known image (the file is then renamed to the
    canonical name so the emulator finds it).
    """
    if not data:
        raise ValidationError("BIOS file is empty")
    sha256, md5 = _digests(data)
    spec = bios_spec(system, sanitize_filename(original_name)) or spec_for_md5(system, md5)
    if spec is None:
        raise UnsupportedRomError(
            f"'{original_name}' is not a known {system.value.upper()} BIOS file name and its "
            "content does not match a known image",
        )
    if spec.md5 and md5 != spec.md5:
        # Right name, unexpected content: keep it (revisions exist) but flag it.
        log.warning("bios.unverified", system=system.value, filename=spec.filename, md5=md5)
    storage.write(bios_storage_key(system, spec.filename), data)
    log.info("bios.installed", system=system.value, filename=spec.filename, size=len(data))
    return InstalledBios(
        spec=spec,
        size_bytes=len(data),
        sha256=sha256,
        md5=md5,
        verified=(md5 == spec.md5) if spec.md5 else None,
    )


def remove(storage: StorageProvider, system: GameSystem, filename: str) -> None:
    spec = bios_spec(system, filename)
    if spec is None:
        raise NotFoundError("Unknown BIOS file")
    key = bios_storage_key(system, spec.filename)
    if not storage.exists(key):
        raise NotFoundError("BIOS file is not installed")
    storage.delete(key)
    log.info("bios.removed", system=system.value, filename=spec.filename)


def read_file(storage: StorageProvider, system: GameSystem, filename: str) -> tuple[str, bytes]:
    """Bytes of an installed BIOS, addressed only by registry name."""
    spec = bios_spec(system, filename)
    if spec is None:
        raise NotFoundError("Unknown BIOS file")
    key = bios_storage_key(system, spec.filename)
    if not storage.exists(key):
        raise NotFoundError("BIOS file is not installed", code="bios_missing")
    log.info("bios.download", system=system.value, filename=spec.filename)
    return spec.filename, storage.read(key)


def preferred_file(storage: StorageProvider, system: GameSystem) -> str | None:
    """The BIOS file the launcher should hand to the emulator, if any."""
    info = BIOS_REGISTRY.get(system)
    if info is None:
        return None
    for spec in info.files:
        if storage.exists(bios_storage_key(system, spec.filename)):
            return spec.filename
    return None
