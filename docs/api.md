# REST API

Base path: `/api`. All responses are JSON unless noted. Errors use

```json
{ "error": { "code": "rom_missing", "message": "The ROM file for this game is missing on disk." } }
```

Error codes: `not_found`, `validation_error`, `rom_missing`, `unsupported_rom`,
`invalid_filename`, `file_too_large`, `duplicate_rom`, `save_not_found`,
`session_not_found`, `session_already_ended`, `storage_error`,
`invalid_storage_key`, `bios_missing`, `cover_not_found`, `feature_disabled`,
`metadata_unavailable`, `job_running`.

## Systems

| Method | Path | Description |
|--------|------|-------------|
| GET | `/systems` | All known systems: id, name, short name, extensions, `supported` (has an adapter) |
| GET | `/systems/{system}` | One system |

## Games

| Method | Path | Description |
|--------|------|-------------|
| GET | `/games` | List. Query: `q`, `system`, `favorite`, `sort` (`title`, `recently_played`, `recently_added`, `play_time`), `limit`, `offset` |
| GET | `/games/{id}` | Detail incl. `play_time_seconds`, `last_played_at`, `has_auto_state`, files |
| PATCH | `/games/{id}` | Edit metadata (title, developer, publisher, release_date, region, description) |
| POST | `/games/{id}/favorite` | Body `{ "favorite": true }` |
| POST | `/games/scan` | Scan the ROM directory; returns `{ added, updated, missing, skipped, errors }` |
| POST | `/games/upload` | Multipart: `file`, `system`. Stores the ROM under `roms/<system>/` and scans it |
| GET | `/games/{id}/rom` | ROM binary. Supports `Range`, sends `Accept-Ranges`, `ETag` (sha256), `Content-Disposition` |
| GET | `/games/{id}/rom/{filename}` | Same as above; `filename` must equal the stored file name (used so browser caches key per game) |
| GET | `/games/{id}/files/{file_id}/{filename}` | Any file of a multi-file game (cue tracks). Same streaming/Range behaviour as `/rom`; `filename` must match |
| GET | `/games/{id}/cover` | Cover image or 404 |
| PUT | `/games/{id}/cover` | Multipart `file` (png/jpg/webp, size limited) |
| POST | `/games/{id}/cover/fetch` | Look the box art up in libretro-thumbnails by file name and store it (replaces an existing cover). 404 `cover_not_found`, 409 `feature_disabled`, 502 `metadata_unavailable` |
| GET | `/library/home` | Sections for the home page: `continue_playing`, `recently_played`, `recently_added`, `favorites`, `platforms` |

## Cover art jobs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/library/covers/fetch` | Start a background job fetching a cover for every game without one → 202 + job. 409 `job_running` while one is active, 409 `feature_disabled` when `ONLINE_METADATA=false` |
| GET | `/library/jobs` | Recent jobs, newest first |
| GET | `/library/jobs/{id}` | `{ id, kind, status (queued/running/done/failed), total, done, counters: { fetched, not_found, skipped, failed }, errors, created_at, started_at, finished_at }` |

Jobs live in the API process's memory; they are not persisted across restarts.

## Saves

| Method | Path | Description |
|--------|------|-------------|
| GET | `/games/{id}/saves` | Query `save_type` (`battery`/`state`). Returns metadata only |
| POST | `/games/{id}/saves` | Multipart: `file`, `save_type`, `slot`, `emulator_id`, `core_id`, `core_version`, optional `screenshot`, optional `client_modified_at`. Upserts on (game, user, type, slot) |
| GET | `/saves/{id}` | Metadata |
| GET | `/saves/{id}/download` | Binary |
| GET | `/saves/{id}/screenshot` | PNG or 404 |
| DELETE | `/saves/{id}` | Delete save and screenshot |

Slot conventions: battery saves use slot `0`. Save states use `1..N` for manual
slots and `-1` for the automatic "Resume" state written on quit.

## Play sessions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/play-sessions` | Body `{ game_id, device?, emulator_id? }` → session. Ends any other open session of the user |
| PATCH | `/play-sessions/{id}` | Body `{ "action": "heartbeat" }` or `{ "action": "end" }` |
| GET | `/play-sessions/recent` | Most recent sessions with game summary |

Duration is computed server-side: `min(ended_at, last_heartbeat + grace) - started_at`.
Sessions that never received `end` are closed at their last heartbeat when a
new session starts.

## BIOS

| Method | Path | Description |
|--------|------|-------------|
| GET | `/bios` | Every system that uses a BIOS with its accepted files and install state |
| GET | `/bios/{system}` | One system (404 when the system uses no BIOS) |
| POST | `/bios/{system}` | Multipart `file`. Accepted when the name is known for the system or the MD5 matches a known image (then renamed). `verified` reports the digest check |
| GET | `/bios/{system}/{filename}` | Binary, by registry name only |
| DELETE | `/bios/{system}/{filename}` | Remove |

Error codes added: `bios_missing`.

## Health

`GET /api/health` → `{ "status": "ok", "app": "<APP_NAME>", "version": "…" }`
