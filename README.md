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

- Eight systems playable in the browser: GBA, GB, GBC, NES, SNES, Genesis, PlayStation, Nintendo 64
- BIOS management: upload the BIOS images you own in Settings, verified against known digests; nothing is downloaded for you
- Multi-file games: a `.cue` sheet and the `.bin` tracks it names are one library entry; an `.m3u` groups a multi-disc set (discs that already had entries are merged, saves kept)
- Library scanning of `data/roms/<system>/` with SHA-256 based duplicate detection, run as a background job with progress
- Home dashboard: Continue Playing, Recently Played, Recently Added, Favorites, Platforms
- Library grid with search, platform filter, favorites filter and sorting
- Game details: cover, metadata, play time, last played, Play / Resume / Favorite
- Immersive player with pause, reset, save/load state slots, screenshot, volume, mute, fullscreen, quit
- Keyboard and gamepad input (Xbox / PlayStation via the Gamepad API)
- Battery saves synced to the server (auto on quit + periodic while playing) with an IndexedDB backup
- Automatic "Resume" save state captured on quit
- Play sessions with server-side play time
- ROM upload and cover upload from the Settings / game pages
- Cover art fetched on request from the libretro-thumbnails collection, per game or for the whole library (background job with progress)
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
| PlayStation | **working** (EmulatorJS · PCSX-ReARMed; `.cue`+`.bin`, `.pbp`; BIOS optional) |
| Nintendo 64 | **working** (EmulatorJS · Mupen64Plus-Next; needs WebGL2) |
| Nintendo DS | **working** (EmulatorJS · melonDS; screen layouts, mouse/finger touch; BIOS optional) |
| PSP | **working** (EmulatorJS · PPSSPP; needs a cross-origin-isolated page and WebGL2) |
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
                          # PS1/N64: boot + a marker planted in the server save survives the round trip
                          # NDS: mouse and finger touches are logged by the test program in both layouts
                          # PSP: counter lives in the memory-stick save tree (packed as tar)
```

The API creates the SQLite database and runs Alembic migrations on startup.
Relative paths in `.env` resolve against the directory containing `.env`.

## ROM setup

Put files you own under the system folder:

```
data/roms/gba/Some Game (USA).gba
data/roms/ps1/Some Game (USA).cue      + the .bin tracks it references
data/roms/n64/Some Game (USA).z64
```

Then **Settings → Scan library** (or `POST /api/games/scan`). The scanner
detects the system from the folder name, the extension and the file header,
hashes the file, and creates a library entry. Re-scanning is safe: unchanged
files are skipped, moved files are re-linked by hash, removed files are
flagged as missing. You can also upload a ROM from the Settings page.

Filenames in No-Intro style (`Title (Region).gba`) are parsed for the title and
region. Cover art can be uploaded on the game page or fetched online (see
[Cover art](#cover-art)); a placeholder is shown otherwise. Online metadata
for titles and descriptions is planned (`MetadataProvider` interface).

## BIOS setup

Open **Settings → BIOS files**. Each system lists the file names it accepts;
upload the image dumped from your own console and it is stored under
`data/bios/<system>/` with its canonical name. Known images are verified by
MD5; an unknown digest is kept but flagged.

- **PlayStation**: optional. Without a BIOS, PCSX-ReARMed uses its built-in
  high-level BIOS, which runs many but not all games. Upload `scph1001.bin`,
  `scph5501.bin`, `scph5500.bin`, `scph5502.bin`, `scph7001.bin` or
  `psxonpsp660.bin` for full compatibility.
- **Nintendo DS**: optional. melonDS boots games directly with its built-in
  FreeBIOS. Upload `bios7.bin`, `bios9.bin` and `firmware.bin` (all three)
  for full compatibility; no digests are checked for these.
- **GBA, Nintendo 64, PSP**: no BIOS needed.
- **Game Boy / Game Boy Color**: optional `gb_bios.bin` / `gbc_bios.bin` boot
  ROMs; when installed Gambatte plays the start-up logo.
- **Famicom Disk System**: `disksys.rom` is required for `.fds` images only.

RetroWeb never downloads BIOS files.

## Cover art

Box art comes from the [libretro-thumbnails](https://github.com/libretro-thumbnails/libretro-thumbnails)
collection, looked up by the ROM's file name (No-Intro / Redump style names
match best; when the exact name is missing, the closest entry with the same
title and region is used). Nothing is fetched automatically: press **Fetch
cover online** on a game page, or **Settings → Cover art → Fetch missing
covers** to run a background job over the whole library. Only images are
downloaded. Set `ONLINE_METADATA=false` to disable it, or
`THUMBNAILS_BASE_URL` to point at a mirror.

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
- Closing the browser tab without pressing **Quit** relies on the periodic save
  sync (every 60 s) and a best-effort flush when the tab is hidden; the
  automatic resume point is only captured by Quit.
- Controller remapping uses EmulatorJS's built-in *Control Settings* menu
  (bottom bar, shown on mouse movement); a RetroWeb-level remapping UI is planned.
- PS1 `.chd`/`.iso` images cannot be opened by the EmulatorJS PCSX-ReARMed build; use `.cue`+`.bin` or `.pbp`. Disc swapping for `.m3u` sets uses EmulatorJS's *Disks* menu in the bottom bar.
- Nintendo 64 needs WebGL2 and is slow without GPU acceleration.
- PSP: PPSSPP only runs cross-origin isolated (the app sends the headers;
  a reverse proxy in front of it must keep them) with WebGL2. Saves are the
  whole `PSP/SAVEDATA` tree of a per-browser memory stick, packed as a tar;
  save states are about 40 MB each.
- Nintendo DS: melonDS writes the cart save about three seconds after the
  game's last write, so quitting inside that window can lose the very last
  in-game save. DSi mode, microphone and Wi-Fi are not exposed.
- Mobile works but is not optimised; EmulatorJS's on-screen controls appear on touch devices.

## Legal notice

Emulator software ≠ copyrighted game ROMs.

RetroWeb bundles no games and no BIOS images. It only catalogs and runs files
that you place in your own data directory or upload yourself. You are
responsible for owning the games you play. The included EmulatorJS runtime and
libretro cores are distributed under their own licenses (GPL-3.0 and others);
see their repositories. Cover images are fetched, on request, from the
libretro-thumbnails collection, whose contents are maintained by that project.

## Roadmap

1. ~~Phase 1 — GBA end to end~~ done
2. ~~Phase 2 — GB, GBC, NES, SNES, Genesis via EmulatorJS~~ done
3. ~~Phase 3 — BIOS upload, PlayStation, Nintendo 64~~ done
4. ~~Phase 4 — Nintendo DS (melonDS, dual-screen layouts, touch)~~ done
5. ~~Phase 5 — PSP (PPSSPP, threads)~~ done
6. ~~Phase 6 — Cover art from libretro-thumbnails (per game + library-wide background job)~~ done
7. ~~Phase 7 — Background scan with progress, `.m3u` multi-disc sets, GB/GBC boot ROMs and FDS BIOS wired~~ done
8. Later — multi-user accounts; Dreamcast, Saturn, Arcade; S3/WebDAV storage; online titles/descriptions; input remapping UI

Not planned: cloud gaming, netplay, achievements, streaming, social features.
