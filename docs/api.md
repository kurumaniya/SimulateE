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

## Accounts

Single-user mode (`SINGLE_USER_MODE=true`, the default): every request acts
as the implicit account and the endpoints below answer 409 `feature_disabled`
(except `GET /auth/status`). Multi-user mode: a login cookie
(`retroweb_session`, HttpOnly) is required everywhere else; without one the
API answers 401 `unauthorized`. Library management (scan, uploads, BIOS,
cover art, metadata edits) and `/users` need an administrator, else 403
`forbidden`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/status` | `{ mode: single/multi, setup_required, registration_open, user }` — never fails |
| POST | `/auth/setup` | First account (admin) → 201 + cookie; claims the implicit account. 409 `setup_complete` afterwards |
| POST | `/auth/register` | Self-registration when `ALLOW_REGISTRATION=true`, else 403 `registration_closed` |
| POST | `/auth/login` | `{ username, password }` → user + cookie. 401 `invalid_credentials` |
| POST | `/auth/logout` | Revokes the session, clears the cookie |
| GET | `/auth/me` | The signed-in user |
| PATCH | `/auth/password` | `{ current_password, new_password }` |
| GET | `/users` | Admin: all accounts |
| POST | `/users` | Admin: `{ username, password, is_admin }` |
| PATCH | `/users/{id}` | Admin: `{ password?, is_admin? }` (not your own admin role) |
| DELETE | `/users/{id}` | Admin: remove an account and its saves (not yourself) |

Usernames: 2–32 characters of letters, digits, `.`, `_`, `-`; passwords at
least 8 characters. Error codes: `unauthorized`, `invalid_credentials`,
`forbidden`, `username_taken`, `setup_complete`, `registration_closed`.

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
| POST | `/games/scan` | Scan the ROM directory synchronously; returns `{ added, updated, missing, skipped, errors }` (kept for scripts and tests) |
| POST | `/library/scan` | Same scan as a background job → 202 + job (`counters` carry the same four counts, `done`/`total` count files hashed). 409 `job_running` while one is active |
| POST | `/games/upload` | Multipart: `file`, `system`. Stores the ROM under `roms/<system>/` and scans it |
| GET | `/games/{id}/rom` | ROM binary. Supports `Range`, sends `Accept-Ranges`, `ETag` (sha256), `Content-Disposition` |
| GET | `/games/{id}/rom/{filename}` | Same as above; `filename` must equal the stored file name (used so browser caches key per game) |
| GET | `/games/{id}/files/{file_id}/{filename}` | Any file of a multi-file game (cue tracks). Same streaming/Range behaviour as `/rom`; `filename` must match |
| GET | `/games/{id}/cover` | Cover image or 404 |
| PUT | `/games/{id}/cover` | Multipart `file` (png/jpg/webp, size limited) |
| POST | `/games/{id}/cover/fetch` | Look the box art up in libretro-thumbnails by file name and store it (replaces an existing cover). 404 `cover_not_found`, 409 `feature_disabled`, 502 `metadata_unavailable` |
| GET | `/library/home` | Sections for the home page: `continue_playing`, `recently_played`, `recently_added`, `favorites`, `platforms` |

## Background jobs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/library/scan` | See above |
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
