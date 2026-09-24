from pathlib import Path

from retroweb.core.config import Settings
from retroweb.storage.base import InvalidStorageKeyError, StorageObject, StorageProvider
from retroweb.storage.local import LocalStorageProvider
from retroweb.storage.mounted import MountedStorage


def build_storage(settings: Settings) -> StorageProvider:
    """Create the storage graph described by settings (local disk in Phase 1)."""
    mounts: dict[str, StorageProvider] = {
        name: LocalStorageProvider(Path(path)) for name, path in settings.storage_roots().items()
    }
    for folder, path in settings.rom_mount_roots().items():
        # A per-system folder on another disk or a NAS mount (see ROM_MOUNTS).
        mounts[f"roms/{folder}"] = LocalStorageProvider(path)
    return MountedStorage(mounts)


__all__ = [
    "InvalidStorageKeyError",
    "LocalStorageProvider",
    "MountedStorage",
    "StorageObject",
    "StorageProvider",
    "build_storage",
]
