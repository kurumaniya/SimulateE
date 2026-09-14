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
    return MountedStorage(mounts)


__all__ = [
    "InvalidStorageKeyError",
    "LocalStorageProvider",
    "MountedStorage",
    "StorageObject",
    "StorageProvider",
    "build_storage",
]
