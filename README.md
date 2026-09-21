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

- Twelve systems playable in the browser: GBA, GB, GBC, NES, SNES, Genesis, PlayStation, Nintendo 64, Nintendo DS, PSP, Sega Saturn and Arcade (FBNeo)
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
- Game identification against the No-Intro / Redump lists by digest, serial or name: English title, developer, publisher, release year, and the right box art even for translated ROMs with a home-made file name
- Cover art fetched on request from the libretro-thumbnails collection, per game or for the whole library (background job with progress)
- Range-capable ROM streaming (no base64, no whole-file buffering)
- Storage abstraction (`StorageProvider`) with a local filesystem provider
- Optional accounts: single implicit user by default, or sign-in with per-user saves, play time and favorites, admin-managed library and users
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
| Sega Saturn | **working** (EmulatorJS · Yabause; `.cue`+`.bin`, `.iso`, `.ccd`; BIOS optional, compatibility is limited, see below) |
| Arcade | **working** (EmulatorJS · FBNeo; zipped ROM sets under their exact set name; `neogeo.zip` for Neo Geo games) |
| Dreamcast | not possible yet: EmulatorJS ships no Dreamcast core (no `flycast` package in any release), and no other browser build is mature enough to integrate |

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
data/roms/saturn/Some Game (USA).cue   + its .bin tracks (or a single .iso)
data/roms/arcade/sf2.zip               an FBNeo ROM set, zipped, under its set name
```

Then **Settings → Scan library** (or `POST /api/games/scan`). The scanner
detects the system from the folder name, the extension and the file header,
hashes the file, and creates a library entry. Re-scanning is safe: unchanged
files are skipped, moved files are re-linked by hash, removed files are
flagged as missing. You can also upload a ROM from the Settings page.

Filenames in No-Intro style (`Title (Region).gba`) are parsed for the title and
region. Cover art can be uploaded on the game page or fetched online (see
[Cover art](#cover-art)); a placeholder is shown otherwise. Files with any other
name are recognised by their content, see [Game identification](#game-identification).

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
- **Sega Saturn**: optional `saturn_bios.bin`. Without it Yabause uses a high-level BIOS
  that starts fewer games.
- **Arcade**: `neogeo.zip` for Neo Geo games only; it is handed to FBNeo next to the game.
- **GBA, Nintendo 64, PSP**: no BIOS needed.
- **Game Boy / Game Boy Color**: optional `gb_bios.bin` / `gbc_bios.bin` boot
  ROMs; when installed Gambatte plays the start-up logo.
- **Famicom Disk System**: `disksys.rom` is required for `.fds` images only.

RetroWeb never downloads BIOS files.

## Game identification

**Settings → Identify games** (or **Identify game** on a game page) matches each file
against the No-Intro / Redump release lists published as
[libretro-database](https://github.com/libretro/libretro-database):

1. by **digest** (SHA-1, then CRC32) of the dump, computed the way those databases do:
   without the iNES header, without an SNES copier header, Nintendo 64 images in
   big-endian order;
2. by the **serial** stored inside the image: the game code in a GBA / GBC / NDS / N64
   header, `SLUS-01234` from a PlayStation disc's `SYSTEM.CNF`, `ULUS-10041` from a
   PSP disc. A translated or patched ROM no longer matches by digest but keeps its
   serial, so `炸弹人锦标赛[汉化].gba` is still recognised as *Bomberman Tournament*;
3. by **name**, when the file name's title equals a release title.

A match sets the English title, region, developer, publisher and release year (fields
you edited yourself are kept; your own title stays the display title) and records the
release name, which is what box art is filed under. Each system's list is downloaded
once and cached in `data/cache/gamedb` for `GAMEDB_TTL_DAYS` (14) days; an outage falls
back to the cached copy. Only name lists are downloaded, never games. The lists carry
no descriptions: those still need a keyed provider (ScreenScraper, IGDB) and are not
implemented. `ONLINE_METADATA=false` disables identification together with cover art;
`GAMEDB_BASE_URL` points at a mirror.

## Cover art

Box art comes from the [libretro-thumbnails](https://github.com/libretro-thumbnails/libretro-thumbnails)
collection, looked up by the game's release name when it has been identified (fetching
a cover identifies the game first) and by the ROM's file name otherwise (No-Intro /
Redump style names match best; when the exact name is missing, the closest entry with the same
title and region is used). Nothing is fetched automatically: press **Fetch
cover online** on a game page, or **Settings → Fetch missing
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

## Accounts

By default RetroWeb runs in **single-user mode**: one implicit account, no
login. Set `SINGLE_USER_MODE=false` to enable accounts:

- The first visitor creates the **administrator** account at `/login`. It
  takes over the implicit account, so saves, play time and favorites made
  before the switch stay with it.
- Administrators manage the library (scan, uploads, BIOS files, cover art)
  and accounts (**Settings → Users**). Everyone else plays: saves, play
  time and favorites are per account; the game library is shared.
- Accounts are created by an administrator unless `ALLOW_REGISTRATION=true`.
- Logins are HttpOnly cookies backed by a server-side session table
  (`SESSION_TTL_DAYS`, sliding). Set `SESSION_COOKIE_SECURE=true` when the
  app is only reached over HTTPS. Passwords are hashed with scrypt.
- There is no rate limiting on sign-in; keep a reverse-proxy gate (Basic
  auth, VPN) in front of a public deployment.

## Deployment notes

The web app sends `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` so that threaded emulator cores
can use `SharedArrayBuffer`. If you place nginx / Caddy / Traefik in front,
proxy both the pages and `/api` through the **same origin** and keep those
headers. Configuration is done through `.env` (see `.env.example`).

## Known limitations

- Closing the browser tab without pressing **Quit** relies on the periodic save
  sync (every 60 s) and a best-effort flush when the tab is hidden; the
  automatic resume point is only captured by Quit.
- Controller remapping uses EmulatorJS's built-in *Control Settings* dialog,
  opened from the 🎮 button in the RetroWeb toolbar (or EmulatorJS's bottom bar).
- PS1 `.chd`/`.iso` images cannot be opened by the EmulatorJS PCSX-ReARMed build; use `.cue`+`.bin` or `.pbp`. Disc swapping for `.m3u` sets uses EmulatorJS's *Disks* menu in the bottom bar.
- Nintendo 64 needs WebGL2 and is slow without GPU acceleration.
- Sega Saturn and Arcade files are recognised **only inside `roms/saturn/` and
  `roms/arcade/`** (aliases: `segasaturn`, `ss`; `fbneo`, `fba`, `neogeo`): `.cue`, `.iso`
  and `.zip` say nothing about the system on their own. A `.zip` anywhere else is ignored.
- Arcade: FBNeo finds a game by its set name, so keep `sf2.zip` called `sf2.zip` (the
  library shows the real title after **Identify games**). Sets must match the FBNeo
  version EmulatorJS 4.2.3 ships. Clone sets that need their parent's files (split sets)
  are not supported yet: use parent sets or non-merged sets. Arcade boards keep no battery
  save; the automatic resume state and save slots work as everywhere else.
- Sega Saturn: Yabause is the only Saturn core EmulatorJS has. It is an old, software-
  rendered emulator: many commercial games run slowly or not at all, more so without a
  real BIOS. `.chd` images are not supported.
- PSP: PPSSPP only runs cross-origin isolated (the app sends the headers;
  a reverse proxy in front of it must keep them) with WebGL2. Saves are the
  whole `PSP/SAVEDATA` tree of a per-browser memory stick, packed as a tar;
  save states are about 40 MB each.
- Nintendo DS: melonDS writes the cart save about three seconds after the
  game's last write, so quitting inside that window can lose the very last
  in-game save. DSi mode, microphone and Wi-Fi are not exposed.
- On phones EmulatorJS's on-screen controls appear automatically; a tap brings the RetroWeb toolbar back, which scrolls sideways on narrow screens.

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
8. ~~Phase 8 — Touch: on-screen controls verified, toolbar reachable by tap, Controls button for remapping~~ done
9. ~~Phase 9 — Accounts: sign-in, admin role, per-user saves and favorites~~ done
10. ~~Phase 10 — Game identification by digest / serial / name (libretro-database): titles, developer, publisher, year, covers for renamed and translated ROMs~~ done
11. ~~Phase 11 — Sega Saturn (Yabause) and Arcade (FBNeo)~~ done
12. Later — S3/WebDAV storage; game descriptions (needs a keyed provider); arcade clone sets; Dreamcast once a browser core exists

Not planned: cloud gaming, netplay, achievements, streaming, social features.
