# Architecture

RetroWeb is a self-hosted web platform for playing a personal retro game
collection in the browser. Think "Steam / Plex for retro games": the product is
the **library**; emulators are an implementation detail hidden underneath it.

This document describes the system as it exists in the repository. Anything
that is planned but not implemented is marked **planned**.

## 1. High-level shape

```
Browser
  │  Next.js pages (library UI)                 apps/web
  │  Emulator Adapter layer (TypeScript)         packages/emulator-core
  │  SaveSyncManager + IndexedDB cache           apps/web/src/lib/saves
  │
  │  REST (same origin: Next.js rewrites /api/* to the API server)
  ▼
FastAPI backend                                 apps/api
  ├── Game library (Game, GameFile)
  ├── Saves (battery saves + save states)
  ├── Play sessions (play time, last played)
  ├── Users (single-user mode in Phase 1)
  ├── ROM scanner + metadata providers
  └── StorageProvider abstraction
        └── LocalStorageProvider → data/{roms,saves,states,bios,covers,screenshots}
              (S3 / MinIO / WebDAV: planned)
Database: SQLite (dev) / PostgreSQL (prod) through SQLAlchemy + Alembic
```

Five parts are deliberately decoupled: **frontend**, **backend**, **emulator
adapters**, **storage**, **database**. Each talks to its neighbours only through
an interface (REST API, `EmulatorAdapter`, `StorageProvider`, SQLAlchemy models).

## 2. Repository layout

```
apps/
  web/                 Next.js 16 (App Router) + React + TypeScript + Tailwind
    src/app/           routes: / (home), /library, /games/[id], /play/[id], /settings
    src/components/    UI building blocks
    src/lib/api/       typed API client + error model
    src/lib/saves/     SaveSyncManager, IndexedDB store
    src/lib/emulator/  browser capability detection, registry wiring
    public/emulatorjs/ EmulatorJS runtime + cores (fetched, git-ignored)
  api/                 FastAPI
    retroweb/
      core/            config, logging, database session
      models/          SQLAlchemy models
      schemas/         Pydantic request/response models
      storage/         StorageProvider interface + LocalStorageProvider
      library/         systems registry, scanner, metadata providers
      services/        business logic (games, saves, sessions)
      api/             routers
    alembic/           migrations
    tests/
packages/
  shared/              GameSystem enum + system metadata (TypeScript)
  emulator-core/       EmulatorAdapter interface, EmulatorRegistry, adapters
data/                  user data (git-ignored) – roms/ saves/ states/ bios/ covers/ screenshots/
docs/                  this folder
docker/                Dockerfiles; docker-compose.yml lives at the repo root
scripts/               tooling (fetch-emulatorjs.mjs, make-test-rom.py)
```

## 3. Frontend architecture

* **Next.js App Router**, all library pages are client components that fetch
  from the same-origin `/api` (Next.js `rewrites` forward to the API server).
  There is exactly one API base URL in the browser, so COOP/COEP isolation is
  simple: everything the page loads is same-origin.
* **TanStack Query** caches API responses and handles invalidation after
  favorites, scans and uploads.
* `src/lib/api/client.ts` converts HTTP failures into a typed `ApiError` with a
  machine-readable `code` (`rom_missing`, `unsupported_rom`, `bios_missing`, …)
  so UI can show specific messages instead of "Something went wrong".
* The **player** page (`/play/[id]`) does not know which emulator runs the
  game. It asks `EmulatorRegistry.getEmulator(system)` for an adapter and uses
  only the `EmulatorAdapter` interface.
* `BrowserCapabilities` probes WebAssembly, WebGL, SharedArrayBuffer,
  Gamepad API and IndexedDB before an emulator is created and produces
  user-facing errors when a requirement is missing.

### Cross-origin isolation

`next.config.ts` sends

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

on every page when `CROSS_ORIGIN_ISOLATION=true` (default). This makes
`SharedArrayBuffer` available, which threaded cores (PPSSPP, DOSBox) need.
mGBA does not need it, but enabling it from day one means the deployment story
does not change later. Any reverse proxy in front of the web app must preserve
these headers (see README → Deployment).

## 4. Backend architecture

* **FastAPI** with synchronous SQLAlchemy sessions (`Session` per request).
  Routers are thin; logic lives in `services/`.
* **Config** is a single `pydantic-settings` object (`core/config.py`) read from
  `.env`. `APP_NAME` is configurable; the name "RetroWeb" is not baked into code.
* **Logging** is `structlog`. Events: `rom.scan.*`, `game.launch`, `save.upload`,
  `save.download`, `emulator.selected`, `cover.*`, `job.*`, plus errors. Never
  logs secrets or save contents.
* **Users**: Phase 1 runs in *single user mode*. A default user row is created
  on startup and `get_current_user` returns it. The dependency is the only
  place to change when authentication is added.
* **Security**: every file the API serves is resolved from a database row
  (`GET /api/games/{id}/rom`), never from a client-provided path. The storage
  provider additionally rejects any key that escapes its root. Upload
  filenames are sanitized, extensions validated against the system registry,
  and sizes limited.

## 5. Database schema (Phase 1)

```
users            id, username, password_hash (nullable), created_at
games            id, title, title_en, title_ja, title_zh, system, cover_key,
                 developer, publisher, release_date, region, description,
                 favorite, created_at, updated_at
game_files       id, game_id, storage_key, filename, extension, size_bytes,
                 sha256 (unique), region, label, is_primary, role (primary|companion),
                 missing, created_at
game_saves       id, game_id, user_id, save_type (battery|state), slot,
                 storage_key, size_bytes, screenshot_key, emulator_id, core_id,
                 core_version, client_modified_at, created_at, updated_at
                 unique(game_id, user_id, save_type, slot)
play_sessions    id, user_id, game_id, started_at, last_heartbeat_at, ended_at,
                 duration_seconds, device, emulator_id
game_emulator_configs
                 id, game_id, user_id, emulator_id, core, config_json, updated_at
```

Design notes:

* **Game vs GameFile**: a game can own several files (regions, translations,
  discs). The scanner creates one game per primary file; files a `.cue` sheet
  names (`role = companion`) attach to the cue's game and are streamed by id
  (`/api/games/{id}/files/{file_id}/{filename}`). The API exposes the
  *primary* file's hash/size on the game; `rom_missing` is true when any file
  is missing.
* **Saves** record `emulator_id`, `core_id`, `core_version` so that a save
  state created by mGBA 0.10 is never silently loaded into another core.
* **Play sessions** are server-timed: the client only says "started",
  "heartbeat", "ended". Duration is computed on the server and capped at the
  last heartbeat + grace period, so a client cannot claim 500 hours.
* Only portable column types are used (no SQLite-only JSON functions); Alembic
  migrations target both SQLite and PostgreSQL.

## 6. Storage abstraction

See [storage.md](storage.md). Business code never calls `open()` on a path;
it asks the `StorageProvider` for `exists / read / write / delete / stream /
size / list / modified_at` on an *object key* such as `roms/gba/game.gba`.

## 7. Emulator Adapter layer

See [emulator-support.md](emulator-support.md) for the runtime details of each
adapter. The contract (`packages/emulator-core/src/adapter.ts`):

```ts
interface EmulatorAdapter {
  readonly id: string
  readonly supportedSystems: GameSystem[]
  initialize(config: EmulatorConfig): Promise<void>
  loadGame(game: GameLaunchData): Promise<void>
  start / pause / resume / stop / reset
  getSaveData(): Promise<Uint8Array | null>
  loadSaveData(data: Uint8Array): Promise<void>
  saveState(): Promise<Uint8Array>          // bytes go to the server, not the emulator
  loadState(data: Uint8Array): Promise<void>
  getScreenshot(): Promise<Blob>
  getScreenLayouts() / getScreenLayout() / setScreenLayout(id)   // multi-screen consoles; empty otherwise
  setVolume / setMuted / enterFullscreen / exitFullscreen
  on(event, handler)                         // 'ready' | 'started' | 'exited' | 'error'
  destroy(): Promise<void>
}
```

Slot bookkeeping is intentionally **not** inside the adapter: adapters move
bytes; the platform decides where slots live (server + IndexedDB backup).

`EmulatorRegistry` maps a `GameSystem` to an adapter factory plus a core
descriptor (`core_id`, `core_version`). UI code calls
`registry.getEmulator(game.system)`; there is no `if (system === "gba")`
scattered through the app.

## 8. Save architecture

Two different things, never mixed:

| Kind         | Produced by            | Files                          | API `save_type` |
|--------------|------------------------|--------------------------------|-----------------|
| Battery save | the game itself        | `.sav` / `.srm` in `data/saves`| `battery`       |
| Save state   | the emulator           | `.state` in `data/states`      | `state`         |

Flow on launch:

```
server (latest battery save + optional auto state)
   ↓ download
SaveSyncManager  ←→ IndexedDB backup (dirty flag, modified_at)
   ↓ newest wins
adapter.loadSaveData()  → emulator
```

During play the manager polls `adapter.getSaveData()` on an interval, hashes
the bytes and uploads only when they changed; the IndexedDB copy is written
first so a dropped connection never loses progress. On quit it flushes the
battery save, captures an **auto save state** ("Resume" slot) with a screenshot,
uploads both, then ends the play session.

Conflict policy in Phase 1: `newest modified_at wins`. The manager isolates this
in one function so a smarter policy can replace it.

## 9. ROM scanning

`GameScanner` walks `roms/` through the storage provider:

1. `detect_system()` – folder name (`roms/gba/…`) wins, then the extension
   table, then header sniffing for GBA (`0x96` fixed byte) and NES (`NES\x1a`).
2. `calculate_hash()` – streaming SHA-256 + size.
3. `extract_basic_metadata()` – `MetadataProvider` chain; Phase 1 has
   `FilenameMetadataProvider` (No-Intro style `Title (Region) (Rev 1).gba`).
4. Upsert by hash: known hash → update location if the file moved; new hash →
   new `Game` + `GameFile`. Files that vanished are flagged `missing`.

## 9b. BIOS files

BIOS images are user uploads, never downloads. `library/bios.py` is a
registry of the file names (and known MD5s) each system accepts;
`services/bios.py` keeps the inventory in `bios/<system>/<name>` through the
storage provider, and `/api/bios` exposes status, upload (validated by name or
by digest, renamed to the canonical name), download and delete. No database
table is involved: the files on storage are the source of truth. The player
asks `/api/bios/{system}` for the preferred file and passes its URL to the
adapter.

## 9c. Cover art

Box art is looked up on request in the libretro-thumbnails collection
(`https://thumbnails.libretro.com/<System>/Named_Boxarts/<name>.png`), which
is named exactly like No-Intro / Redump dumps, so the scanner's file names
usually resolve in one request. `library/artwork.py` holds the name logic:
the system directory table, RetroArch's `&*/:`<>?\|` → `_` substitution, and
a fuzzy fallback that parses the server's directory index (cached per system
for a day) and picks the entry with the same normalised title, scoring shared
region tokens up and beta/proto/demo tags down. `services/artwork.py` does
the HTTP through an injectable `httpx` transport (tests run a fake server)
and writes the PNG to `covers/<game_id>.png`.

Library-wide fetching runs as a background job (`services/jobs.py`: one
thread per job, one active job per kind, progress counters polled through
`/api/library/jobs/{id}`). The job runner is process-local and deliberately
simple; it is also the hook for making library scans asynchronous later.
`ONLINE_METADATA=false` turns the endpoints off (409 `feature_disabled`).

## 10. Request flow for playing a game

```
GET  /api/games/{id}            game detail (+ has_auto_state, last played, play time)
POST /api/play-sessions         {game_id} → session id
GET  /api/games/{id}/saves      list battery/state saves
GET  /api/saves/{id}/download   binary
GET  /api/games/{id}/rom        binary, Range supported, cached by hash ETag
GET  /api/games/{id}/files/…    companion files (cue tracks), same streaming
GET  /api/bios/{system}         preferred BIOS file, if any
   … play …
POST /api/games/{id}/saves      multipart battery / state (+ screenshot)
PATCH /api/play-sessions/{id}   {action: "heartbeat" | "end"}
```

## 11. Player lifecycle (`apps/web/src/components/player/usePlayerSession.ts`)

```
capability check → registry.getEmulator(system) → adapter.initialize()
  → adapter.loadGame()  (HEAD /rom first: 404 ⇒ "ROM missing")
  → POST /play-sessions
  → adapter.start()
  → SaveSyncManager.restoreBatterySave()  (newest of server / IndexedDB, then core reset)
  → optional: load auto state (?resume=1)
  → periodic sync (60 s) + heartbeat (30 s)
quit → flush battery save → capture auto state + screenshot → destroy → end session
```

The toolbar hides after 3 s of inactivity while running; pointer movement or
Escape shows it. Errors are rendered by code (`rom_missing`, `assets_missing`,
`bios_missing`, `unsupported_browser`, …) with a relevant next action.

## 12. Testing

* `apps/api/tests`: 48 pytest cases (detection, hashing, duplicates, path
  traversal, Range streaming, saves, sessions, uploads, enum sync with the
  TypeScript package).
* `e2e/play-flow.spec.ts` (Playwright): for every supported system, play →
  quit → battery save on server → replay restores it; plus resume for GBA. It
  uses the homebrew ROMs produced by `scripts/make-test-rom.py` (one per
  system: ARM, SM83, 6502, 65816, 68000 programs that bump a counter in
  battery RAM on boot), so the assertions check real emulator output (counter
  1 after the first session, 2 after the second).
* `scripts/verify-test-roms.py` runs the same programs offline on Unicorn,
  PyBoy and py65 to catch assembly mistakes before touching a browser.

## 13. Decisions log

| Decision | Choice | Why |
|----------|--------|-----|
| Emulator for GBA | EmulatorJS 4.2.3 + mGBA core | Mature, actively released, npm-distributed (`@emulatorjs/*`), verified API |
| EmulatorJS delivery | Fetched into `apps/web/public/emulatorjs` by script, not committed | 4 MB per core; keeps repo small; pinned version |
| API access from browser | Same-origin via Next.js rewrites | One origin ⇒ COOP/COEP just works, no CORS for ROM streaming |
| DB access | Sync SQLAlchemy | Simplest correct option with SQLite; PostgreSQL via psycopg |
| Play time | Server-timed sessions with heartbeat | Client cannot forge play time |
| Resume | Auto save state captured on quit | "Resume" continues exactly where the player stopped, not just from the last in-game save |
| Save sync policy | newest-wins, isolated function | Enough for one user; replaceable |
| Scan execution | Synchronous request | Simple; libraries of thousands of files still scan in seconds unless files are huge (documented limitation) |
| Save injection | Write save, then reset the core | EmulatorJS exposes the save path only after content loads; a reset makes the game boot with the save |
| Test content | Hand-assembled homebrew ROM | Lets CI verify play/save/resume without any copyrighted data |
| BIOS storage | Files on storage, no DB table | The registry defines validity; the inventory is just "which known files exist" |
| Companion files | Adapter writes them into the emulator FS itself | EmulatorJS's `externalFiles` writes empty files for explicit paths in 4.2.3 |
| N64 test boot | Custom 64-byte IPL3 stub | libdragon's IPL3 crashes on this Mupen64Plus build; the stub only needs the emulator's HLE boot |
| NDS | EmulatorJS's melonDS core, no separate build | Layouts and touch are core options the adapter drives; a second WASM build would duplicate the runtime for no gain |
| Screen layouts | Adapter capability (`getScreenLayouts` / `setScreenLayout`), ids not core option strings | The toolbar stays core-agnostic; a PSP or DeSmuME adapter maps the same ids to its own options |
| NDS touch | Core `Touch` mode (absolute pointer), mouse lock off | Works identically for mouse and finger; the core's `Mouse` mode needs pointer lock and breaks touch screens |
| NDS BIOS | Adapter writes every installed file into the system directory | EmulatorJS's `biosUrl` handles a single file; melonDS looks three up by name |
| PSP saves | `PSP/SAVEDATA` tree packed as an uncompressed tar, one blob per game | Keeps the server's one-blob battery model; PPSSPP has no SRAM; the tree is emptied before each boot because the browser memory stick is shared |
| Battery save timing | Resolved before the emulator loads, applied before boot when the adapter can (`initialSaveApplied`), otherwise inject + reset after start | PPSSPP's `retro_reset` asserts on its never-joined boot thread; restoring before boot also removes a reboot for every core that can take it |
| Proxy body size | `experimental.proxyClientMaxBodySize = 2gb` | Next.js drops rewritten request bodies over 10 MB; PPSSPP states are ~40 MB and ROM uploads larger |
| Cover art source | libretro-thumbnails over HTTP, on request only | No API key or account, names match the scanner's No-Intro file names, and a directory index allows fuzzy matching; nothing is fetched behind the user's back |
| Background jobs | In-process thread + polled counters | Enough for one server process and a single user; a queue would add a dependency for no gain today |
