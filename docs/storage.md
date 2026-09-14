# Storage

All user data lives behind `retroweb.storage.StorageProvider`
(`apps/api/retroweb/storage/base.py`). Business code addresses **object keys**,
never filesystem paths:

```
roms/gba/Pokemon - Emerald Version (USA).gba
saves/<user_id>/<game_id>/battery-0.sav
states/<user_id>/<game_id>/state-1.state
screenshots/<user_id>/<game_id>/state-1.png
covers/<game_id>.jpg
bios/gba_bios.bin
```

## Interface

```python
class StorageProvider(ABC):
    def exists(self, key: str) -> bool
    def read(self, key: str) -> bytes                  # small objects only
    def write(self, key: str, data: bytes | BinaryIO) -> None
    def delete(self, key: str) -> None
    def size(self, key: str) -> int
    def modified_at(self, key: str) -> datetime
    def stream(self, key: str, start: int = 0, end: int | None = None,
               chunk_size: int = 1 MiB) -> Iterator[bytes]
    def list(self, prefix: str) -> Iterator[StorageObject]   # key, size, modified_at
```

`stream()` is what the ROM endpoint uses; large files never pass through a
single `bytes` object. `read()` is reserved for covers, saves and states.

## Providers

| Provider               | Status  | Notes |
|------------------------|---------|-------|
| `LocalStorageProvider` | working | Root = `DATA_PATH`. Every key is normalised and resolved; keys that escape the root (`..`, absolute paths, drive letters) raise `InvalidStorageKeyError`. |
| S3 / MinIO             | planned | Range requests map naturally to `stream(start, end)`. |
| WebDAV / NAS           | planned | |

## Directory layout (local provider)

```
data/
├── roms/         user-provided ROM files, organised by system folder
│   └── gba/
├── saves/        battery saves, per user / game
├── states/       save states, per user / game
├── bios/         user-provided BIOS files (never downloaded by the app)
├── covers/       cover art
└── screenshots/  save-state thumbnails
```

The sub-directories can be relocated individually with `ROM_PATH`, `SAVE_PATH`,
`STATE_PATH`, `BIOS_PATH`, `COVER_PATH`, `SCREENSHOT_PATH`. Internally each
becomes a *mount* in `MountedStorage`, which routes a key by its first path
segment to the right provider; this is also how an S3 bucket could hold ROMs
while saves stay local.

## Security rules

* The API never accepts a storage key or path from the client. A game id is
  resolved to a `GameFile` row, whose `storage_key` was produced by the scanner.
* Upload filenames are reduced to a safe character set and the extension must
  be valid for the target system.
* Providers refuse keys containing `..`, leading `/`, `\`, NUL, or that resolve
  outside their root after `realpath`.
