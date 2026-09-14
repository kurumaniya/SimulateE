# Emulator support

RetroWeb does not implement emulators. It integrates existing browser /
WebAssembly emulators behind the `EmulatorAdapter` interface
(`packages/emulator-core`). This page lists the systems, which adapter and core
serve them, and what has actually been verified.

Status legend: **working** = end-to-end verified in this repository,
**available** = the core ships with the integrated runtime but has not been
wired/tested here yet, **planned** = not started.

| System | Enum id | Extensions | Adapter | Core | Status | Known issues |
|--------|---------|------------|---------|------|--------|--------------|
| Game Boy Advance | `gba` | `.gba` | EmulatorJS | mGBA | **working** (Phase 1) | Threads disabled; HLE BIOS used unless a BIOS is uploaded (BIOS upload UI is planned) |
| Game Boy | `gb` | `.gb` | EmulatorJS | Gambatte | planned (Phase 2) | |
| Game Boy Color | `gbc` | `.gbc` | EmulatorJS | Gambatte | planned (Phase 2) | |
| NES / Famicom | `nes` | `.nes`, `.fds`, `.unf` | EmulatorJS | FCEUmm / Nestopia | planned (Phase 2) | |
| SNES / Super Famicom | `snes` | `.sfc`, `.smc` | EmulatorJS | Snes9x | planned (Phase 2) | |
| Sega Genesis / Mega Drive | `genesis` | `.md`, `.gen`, `.smd`, `.bin` | EmulatorJS | Genesis Plus GX | planned (Phase 2) | `.bin` is ambiguous; header sniffing needed |
| PlayStation | `ps1` | `.cue`+`.bin`, `.chd`, `.pbp` | EmulatorJS | PCSX-ReARMed | planned (Phase 3) | Requires user-supplied BIOS; multi-file games need `GameFile` grouping |
| Nintendo 64 | `n64` | `.z64`, `.n64`, `.v64` | EmulatorJS | Mupen64Plus-Next / ParaLLEl | planned (Phase 3) | Performance-sensitive |
| Nintendo DS | `nds` | `.nds` | melonDS (EmulatorJS ships a melonDS core; a dedicated adapter is required for dual-screen layout & touch) | melonDS | planned (Phase 4) | Screen layouts, touch mapping |
| PSP | `psp` | `.iso`, `.cso`, `.pbp` | PPSSPP (EmulatorJS ships a PPSSPP core that **requires threads + WebGL2**) | PPSSPP | planned (Phase 5) | Needs COOP/COEP (already served), large ISOs need Range streaming (already implemented) |

## EmulatorJS integration (verified against 4.2.3 source)

Distribution: EmulatorJS is published on npm as `@emulatorjs/emulatorjs`
(runtime) and `@emulatorjs/core-<name>` (one package per core). The runtime
package contains **unminified** sources under `data/src/` plus `data/loader.js`
and `data/emulator.css`; no cores. `scripts/fetch-emulatorjs.mjs` downloads the
pinned tarballs from the npm registry and lays them out as EmulatorJS expects:

```
apps/web/public/emulatorjs/
  loader.js, emulator.css, src/*.js, localization/*.json, compression/*
  cores/mgba-wasm.data
  cores/mgba-legacy-wasm.data          (WebGL1 fallback)
  cores/mgba-thread-wasm.data          (used when threads are enabled)
  cores/mgba-thread-legacy-wasm.data
  cores/reports/mgba.json              (build metadata; enables core caching)
```

Facts the adapter relies on (all read from `data/src/emulator.js`,
`GameManager.js`, `loader.js`):

* `loader.js` is a thin bootstrap: it loads the scripts and calls
  `new EmulatorJS(selector, config)`; the class is exported as
  `window.EmulatorJS`. The adapter performs the same bootstrap itself so it can
  pass a config object instead of `window.EJS_*` globals. Because the npm
  package has no `emulator.min.js`, the adapter loads the `src/` scripts in the
  order `loader.js` uses.
* Config keys used: `dataPath` (must end with `/`), `system` (`"gba"`),
  `gameUrl` (string URL; EmulatorJS fetches it with XHR), `gameName`,
  `biosUrl`, `threads`, `startOnLoad`, `volume`, `disableDatabases`,
  `backgroundColor`, `color`, `buttonOpts`, `noAutoFocus`, `capture`.
* Events (`emulator.on(name, cb)`): `ready`, `start`, `exit`, `saveState`,
  `loadState`, `saveSave`, `loadSave`, `saveDatabaseLoaded`.
* Runtime methods:
  * `emulator.gameManager.getState(): Uint8Array` and `loadState(bytes)`.
  * `emulator.gameManager.getSaveFile(): Uint8Array | null` (flushes the
    core's save RAM first), `getSaveFilePath()`, `loadSaveFiles()`.
    Battery saves live in the Emscripten FS under `/data/saves`, which
    EmulatorJS mounts as IDBFS with `autoPersist`.
  * `emulator.pause()`, `emulator.play()`, `emulator.paused`, `emulator.started`.
  * `emulator.gameManager.restart()`.
  * `emulator.takeScreenshot(source, format, upscale) → {blob, format}`.
  * `emulator.setVolume(0..1)`, `emulator.toggleFullscreen(bool)`.
  * `emulator.callEvent("exit")` flushes saves, stops the main loop, unmounts
    `/data/saves` and aborts the module after 1 s. There is no `destroy()`;
    the adapter removes the container contents afterwards.
* Core selection: `system: "gba"` → `mgba`. Cores that need threads
  (`ppsspp`, `dosbox_pure`) fail unless `threads: true` **and**
  `SharedArrayBuffer` exists.
* Core caching: EmulatorJS caches cores/ROMs in its own IndexedDB keyed by the
  last URL path segment. RetroWeb ROM URLs therefore end in the file name
  (`/api/games/{id}/rom/{filename}`) so different games never share a cache
  key.

Behaviour the adapter adds on top (verified end to end by `e2e/gba-flow.spec.ts`
with the homebrew ROM from `scripts/make-test-rom.py`):

* **Battery save injection**: EmulatorJS only exposes the core's save path
  once content is loaded, so the game has already booted once by the time the
  server's save can be written. `SaveSyncManager` writes the file, calls
  `loadSaveFiles()` and then `reset()`s the core so the game boots with the
  save in place. The reboot is invisible to the player (it happens during the
  loading screen).
* **Player controls**: RetroWeb draws its own toolbar (pause, reset, save/load
  state slots, screenshot, volume, fullscreen, quit). EmulatorJS's bottom bar is
  kept with only two buttons, *Settings* (core options, shaders, save interval)
  and *Control Settings* (keyboard/gamepad remapping), because RetroWeb has no
  equivalent yet. Both bars auto-hide; move the mouse or press Escape.
* The EmulatorJS instance is attached to its mount element as `__emulatorjs`
  for debugging and tests.

Known issues:

* On `localhost` EmulatorJS calls `checkForUpdates()` against
  `cdn.emulatorjs.org`; when that host is unreachable the rejected fetch shows
  up in the Next.js dev overlay. It is harmless and does not happen on other
  hostnames.
* EmulatorJS registers `window`/`document` listeners it never removes. The
  adapter neutralises them (`started = false`, gamepad loop terminated) but
  they accumulate across in-app navigations until the page reloads.
* The core's save file name is derived from the ROM URL's last segment, so it
  contains URL-encoding (`RetroWeb%20Test.srm` inside the emulator FS). It is
  internal only; RetroWeb names server-side saves by game id.
* Closing the tab without pressing Quit relies on the periodic sync (60 s) and
  the `visibilitychange` flush; the automatic resume state is only captured by
  Quit.

Save-state compatibility: every state uploaded by the EmulatorJS adapter is
tagged `emulator_id="emulatorjs"`, `core_id="mgba"`,
`core_version="<emulatorjs version>"` (EmulatorJS does not expose the libretro
core's own version string; the EmulatorJS release pins the core build).

## Input

EmulatorJS handles keyboard and Gamepad API input itself (Xbox and PlayStation
controllers use the standard gamepad mapping; the built-in *Control Settings*
menu allows remapping). RetroWeb exposes a virtual-button vocabulary in
`packages/emulator-core/src/input.ts` so future adapters (melonDS, PPSSPP)
share one mapping model; a RetroWeb-level remapping UI is planned.

Default keyboard layout for GBA (EmulatorJS defaults):

| Virtual | Key |
|---------|-----|
| D-pad | Arrow keys |
| A | X |
| B | Z |
| L / R | Q / E |
| Start | Enter |
| Select | Shift |

## Browser requirements

Checked by `BrowserCapabilities` before an emulator is created:

| Capability | Needed by |
|------------|-----------|
| WebAssembly | all |
| WebGL (1 or 2) | all (WebGL2 preferred; legacy core used otherwise) |
| IndexedDB | save backup + EmulatorJS caches |
| SharedArrayBuffer | threaded cores only (PPSSPP, DOSBox) — requires COOP/COEP headers |
| Gamepad API | controller support (optional) |
| Fullscreen API | fullscreen button (optional) |
