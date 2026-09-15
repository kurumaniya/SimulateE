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
| Game Boy | `gb` | `.gb` | EmulatorJS | Gambatte | **working** (Phase 2) | Runs without a boot ROM (Gambatte's built-in start-up); a user-supplied boot ROM is not wired yet |
| Game Boy Color | `gbc` | `.gbc` | EmulatorJS | Gambatte | **working** (Phase 2) | Same core as GB (EmulatorJS system id `gb`) |
| NES / Famicom | `nes` | `.nes`, `.fds`, `.unf` | EmulatorJS | FCEUmm | **working** (Phase 2) | FDS needs a user-supplied BIOS (no upload UI yet); Nestopia core is available but not wired |
| SNES / Super Famicom | `snes` | `.sfc`, `.smc` | EmulatorJS | Snes9x | **working** (Phase 2) | |
| Sega Genesis / Mega Drive | `genesis` | `.md`, `.gen`, `.smd`, `.bin` | EmulatorJS | Genesis Plus GX | **working** (Phase 2) | `.bin` is ambiguous; put files under `roms/genesis/` or rely on the `SEGA` header sniff. Sega CD / 32X are not registered |
| PlayStation | `ps1` | `.cue`+`.bin`/`.img`, `.pbp`, `.m3u`, `.ccd` | EmulatorJS | PCSX-ReARMed | **working** (Phase 3) | The EmulatorJS build of PCSX-ReARMed does not accept `.chd`, `.iso` or `.exe`. Runs without a BIOS through HLE; upload one in Settings for full compatibility. Multi-disc (`.m3u`) is not grouped by the scanner yet |
| Nintendo 64 | `n64` | `.z64`, `.n64`, `.v64` | EmulatorJS | Mupen64Plus-Next (GLideN64, WebGL2); ParaLLEl-N64 available via `adapterOptions.retroarchCore` | **working** (Phase 3) | Needs WebGL2. Slow without GPU acceleration (headless CI runs at a few fps) |
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
  cores/<core>-wasm.data               (mgba, gambatte, fceumm, snes9x, genesis_plus_gx,
                                        pcsx_rearmed, mupen64plus_next, parallel_n64)
  cores/<core>-legacy-wasm.data        (WebGL1 fallback)
  cores/<core>-thread-wasm.data        (used when threads are enabled)
  cores/<core>-thread-legacy-wasm.data
  cores/reports/<core>.json            (build metadata; enables core caching)
```

Adapter bindings (`SYSTEM_BINDINGS` in `adapters/emulatorjs/adapter.ts`), taken
from `getCores()` in `emulator.js`:

| RetroWeb system | EmulatorJS `system` | core |
|-----------------|---------------------|------|
| `gba` | `gba` | `mgba` |
| `gb`, `gbc` | `gb` | `gambatte` |
| `nes` | `nes` | `fceumm` |
| `snes` | `snes` | `snes9x` |
| `genesis` | `segaMD` | `genesis_plus_gx` |
| `ps1` | `psx` | `pcsx_rearmed` |
| `n64` | `n64` | `mupen64plus_next` (`parallel_n64` on request) |

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
* Core selection follows the table above. Cores that need threads
  (`ppsspp`, `dosbox_pure`) fail unless `threads: true` **and**
  `SharedArrayBuffer` exists.
* Core caching: EmulatorJS caches cores/ROMs in its own IndexedDB keyed by the
  last URL path segment. RetroWeb ROM URLs therefore end in the file name
  (`/api/games/{id}/rom/{filename}`) so different games never share a cache
  key.

Behaviour the adapter adds on top (verified end to end by `e2e/play-flow.spec.ts`
with the homebrew ROMs from `scripts/make-test-rom.py`, one per system):

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
* **BIOS**: `GameLaunchData.biosUrl` is passed as EmulatorJS `biosUrl`;
  EmulatorJS downloads it and writes it next to the content at `/` (its
  RetroArch build reports `SYSTEM_DIRECTORY: "/"`), which is where
  PCSX-ReARMed looks. The URL's last segment must be the canonical BIOS file
  name, which `/api/bios/{system}/{filename}` guarantees.
* **Companion files** (`.cue` + `.bin` tracks): EmulatorJS's `externalFiles`
  option is *not* used. In 4.2.3 it calls `FS.writeFile(path, ArrayBuffer)` for
  explicit paths, which Emscripten rejects after creating the node, leaving an
  empty file (the warning only shows with `EJS_DEBUG_XX`). The adapter fetches
  the companions itself and writes them on the `saveDatabaseLoaded` event,
  before RetroArch opens the content. The cue is stored by EmulatorJS under its
  URL-encoded name; its `FILE` lines reference the real names, which is what
  the adapter writes.
* **Alternative cores**: `adapterOptions.retroarchCore` becomes EmulatorJS
  `defaultOptions.retroarch_core` (e.g. `parallel_n64`). There is no UI for
  it yet.

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
* Mupen64Plus-Next blocks the main thread while it waits for the game to
  present a frame: a program that never changes `VI_ORIGIN` freezes the page.
  Real games always swap buffers, but keep it in mind for homebrew.

Battery-save layout differs per core (all verified): mGBA, Gambatte, FCEUmm
and Snes9x expose SRAM byte-for-byte; Genesis Plus GX stores odd-byte SRAM at
odd indices of the `.srm`; PCSX-ReARMed's `.srm` is memory card 1 (128 KiB);
Mupen64Plus-Next's `.srm` bundles EEPROM, mempaks, SRAM and FlashRAM
(290 KiB). RetroWeb never interprets the bytes, it only moves them, so this
only matters to the test ROMs. For PS1 and N64 the e2e test plants a marker in
the save the core produced and checks it survives server → emulator → server.

### Test ROM notes (PS1 / N64)

* The PS1 test is a real MODE2/2352 disc image with an ISO9660 file system,
  `SYSTEM.CNF` and a PS-X EXE, plus its cue sheet. EDC/ECC fields are zero;
  the emulator does not verify them.
* The N64 test boots through a 64-byte emulator-only IPL3 stub
  (`scripts/test-programs/ipl3.S`). libdragon's public-domain IPL3 was tried
  first, but on the Mupen64Plus build EmulatorJS ships its RDRAM detection
  reports 64 MB and the boot crashes into an exception loop at `0x80000300`.
  The stub relies on the emulator's HLE PIF boot, so the ROM is not valid for
  real hardware.

Save-state compatibility: every state uploaded by the EmulatorJS adapter is
tagged `emulator_id="emulatorjs"`, `core_id` (`mgba`, `gambatte`, …),
`core_version="<emulatorjs version>"` (EmulatorJS does not expose the libretro
core's own version string; the EmulatorJS release pins the core build).

## Input

EmulatorJS handles keyboard and Gamepad API input itself (Xbox and PlayStation
controllers use the standard gamepad mapping; the built-in *Control Settings*
menu allows remapping). RetroWeb exposes a virtual-button vocabulary in
`packages/emulator-core/src/input.ts` so future adapters (melonDS, PPSSPP)
share one mapping model; a RetroWeb-level remapping UI is planned.

Default keyboard layout (EmulatorJS RetroPad defaults; SNES/Genesis add X/Y
and L/R, C on the Genesis maps to the RetroPad A button):

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
