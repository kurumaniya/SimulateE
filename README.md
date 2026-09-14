# RetroWeb

A self-hosted, browser-based retro gaming platform: a **game library first**
(think Steam or Plex for your own retro collection), with emulators running in
the browser underneath it.

> RetroWeb manages **your own** game files. It does not ship, download, search
> for or link to commercial ROMs or BIOS files. See [Legal notice](#legal-notice).

## What is this?

You open a website, see your collection with cover art, play time and "Continue
Playing", click a game, and it runs — the platform picks the right emulator
core, restores your save, tracks play time and uploads your save when you quit.
Open it on another device and resume.

## Features (implemented)

- Six systems playable in the browser: GBA, GB, GBC, NES, SNES, Genesis (see below)
- Library scanning of `data/roms/<system>/` with SHA-256 based duplicate detection
- Home dashboard: Continue Playing, Recently Played, Recently Added, Favorites, Platforms
- Library grid with search, platform filter, favorites filter and sorting
- Game details: cover, metadata, play time, last played, Play / Resume / Favorite
- Immersive player with pause, reset, save/load state slots, screenshot, volume, mute, fullscreen, quit
- Keyboard and gamepad input (Xbox / PlayStation via the Gamepad API)
- Battery saves synced to the server (auto on quit + periodic while playing) with an IndexedDB backup
- Automatic "Resume" save state captured on quit
- Play sessions with server-side play time
- ROM upload and cover upload from the Settings / game pages
- Range-capable ROM streaming (no base64, no whole-file buffering)
- Storage abstraction (`StorageProvider`) with a local filesystem provider
- Docker Compose deployment (SQLite by default, PostgreSQL override)

## Supported systems

| System | Status |
|--------|--------|
| Game Boy Advance | **working** (EmulatorJS · mGBA) |
| Game Boy / Game Boy Color | **working** (EmulatorJS · Gambatte) |
| NES / Famicom | **working** (EmulatorJS · FCEUmm) |
| SNES / Super Famicom | **working** (EmulatorJS · Snes9x) |
| Sega Genesis / Mega Drive | **working** (EmulatorJS · Genesis Plus GX) |
| PlayStation, Nintendo 64 | planned (Phase 3) |
| Nintendo DS | planned (Phase 4, melonDS) |
| PSP | planned (Phase 5, PPSSPP) |
| Dreamcast, Saturn, Arcade | later |

Details and known issues: [docs/emulator-support.md](docs/emulator-support.md).

## Architecture

```
Browser ── Next.js UI ── Emulator Adapter layer (EmulatorJS today)
   │
   │ REST (same origin, proxied by Next.js)
   ▼
FastAPI ── Library · Saves · Play sessions · Users · Scanner
   │
   ▼
StorageProvider (local disk today; S3/NAS later) + SQLite / PostgreSQL
```

Read [docs/architecture.md](docs/architecture.md), [docs/storage.md](docs/storage.md),
[docs/api.md](docs/api.md).

## Quick start (Docker)

```bash
cp .env.example .env            # edit SECRET_KEY at least
mkdir -p data/roms/gba
cp /path/to/your/own/game.gba data/roms/gba/
docker compose up -d --build
```

Open http://localhost:3000, go to **Settings → Scan library**, then play.

PostgreSQL instead of SQLite:

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

The Compose setup builds the web image with `API_PROXY_TARGET=http://api:8000`
baked in (Next.js rewrites are resolved at build time). The Docker images have
not yet been built in an automated pipeline; the development flow below is the
one verified end to end.

## Development

Requirements: Node ≥ 20, Python ≥ 3.11.

```bash
# 1. Backend
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example ../../.env
uvicorn retroweb.main:app --reload --port 8000     # from apps/api

# 2. Frontend (new terminal, repo root)
npm install
npm run fetch-emulator          # downloads EmulatorJS + mGBA core into apps/web/public/emulatorjs
npm run dev                     # http://localhost:3000
```

Checks:

```bash
cd apps/api && pytest && ruff check . && mypy retroweb
npm run lint && npm run typecheck && npm run build
```

End-to-end test (needs both dev servers running and Chromium via Playwright):

```bash
npm run make-test-rom     # writes a tiny homebrew ROM for each system into data/roms/<system>/
npm run e2e               # per system: play → save → quit → replay restores it; GBA also checks resume
```

The API creates the SQLite database and runs Alembic migrations on startup.
Relative paths in `.env` resolve against the directory containing `.env`.

## ROM setup

Put files you own under the system folder:

```
data/roms/gba/Some Game (USA).gba
```

Then **Settings → Scan library** (or `POST /api/games/scan`). The scanner
detects the system from the folder name, the extension and the file header,
hashes the file, and creates a library entry. Re-scanning is safe: unchanged
files are skipped, moved files are re-linked by hash, removed files are
flagged as missing. You can also upload a ROM from the Settings page.

Filenames in No-Intro style (`Title (Region).gba`) are parsed for the title and
region. Cover art can be uploaded on the game page; a placeholder is shown
otherwise. Online metadata providers are planned (`MetadataProvider` interface).

## BIOS setup

GBA runs with mGBA's built-in high-level BIOS; no file is required.
Systems that need a BIOS (PlayStation, …) are not integrated yet. When they
are, BIOS files will be user-uploaded into `data/bios/` — RetroWeb will never
download them.

## Save system

- **Battery saves** (`.sav`/`.srm`, created by the game) are stored in
  `data/saves/`, downloaded before the game starts and uploaded periodically
  and on quit. The browser keeps an IndexedDB backup so a dropped connection
  does not lose progress; the newest copy wins on the next launch.
- **Save states** (emulator snapshots) are stored in `data/states/` with a
  screenshot and the emulator/core version that produced them. Slot `-1` is the
  automatic "Resume" state written when you quit.

See [docs/architecture.md → Save architecture](docs/architecture.md#8-save-architecture).

## Deployment notes

The web app sends `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` so that threaded emulator cores
can use `SharedArrayBuffer`. If you place nginx / Caddy / Traefik in front,
proxy both the pages and `/api` through the **same origin** and keep those
headers. Configuration is done through `.env` (see `.env.example`).

## Known limitations

- Single implicit user; no login yet (the `User` model and dependency are in place).
- Library scan runs synchronously inside the request.
- Closing the browser tab without pressing **Quit** relies on the periodic save
  sync (every 60 s) and a best-effort flush when the tab is hidden; the
  automatic resume point is only captured by Quit.
- Controller remapping uses EmulatorJS's built-in *Control Settings* menu
  (bottom bar, shown on mouse movement); a RetroWeb-level remapping UI is planned.
- BIOS upload has no UI yet (none of the current systems need one; FDS and GB boot ROMs are not wired).
- Mobile works but is not optimised; virtual on-screen controls are planned.

## Legal notice

Emulator software ≠ copyrighted game ROMs.

RetroWeb bundles no games and no BIOS images. It only catalogs and runs files
that you place in your own data directory or upload yourself. You are
responsible for owning the games you play. The included EmulatorJS runtime and
libretro cores are distributed under their own licenses (GPL-3.0 and others);
see their repositories.

## Roadmap

1. ~~Phase 1 — GBA end to end~~ done
2. ~~Phase 2 — GB, GBC, NES, SNES, Genesis via EmulatorJS~~ done
3. Phase 3 — PlayStation (BIOS upload), Nintendo 64
4. Phase 4 — Nintendo DS (melonDS, dual-screen layouts, touch)
5. Phase 5 — PSP (PPSSPP, threads)
6. Later — Dreamcast, Saturn, Arcade; S3/WebDAV storage; online metadata; multi-user accounts; input remapping UI

Not planned: cloud gaming, netplay, achievements, streaming, social features.
