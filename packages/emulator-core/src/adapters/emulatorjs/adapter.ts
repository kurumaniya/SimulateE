import { GameSystem } from "@retroweb/shared";
import type {
  CoreDescriptor,
  EmulatorAdapter,
  EmulatorConfig,
  EmulatorEvent,
  EmulatorEventMap,
  GameLaunchData,
  ScreenLayout,
} from "../../adapter";
import { EmulatorError } from "../../errors";
import { BASE_REQUIREMENTS, type CapabilityRequirement } from "../../capabilities";
import { clearTree, packTree, unpackTree } from "./memstick";
import { loadEmulatorJsRuntime } from "./runtime";
import type { EjsConfig, EjsFileSystem, EjsGameManager, EjsInstance } from "./types";

export const EMULATORJS_ID = "emulatorjs";
/** Pinned in scripts/fetch-emulatorjs.mjs; the runtime reports it at run time too. */
export const EMULATORJS_VERSION = "4.2.3";

interface CoreScreenLayout extends ScreenLayout {
  /** Value of the core option that selects this layout. */
  value: string;
}

interface SystemBinding {
  /** EmulatorJS `system` config value. */
  ejsSystem: string;
  /** libretro core EmulatorJS selects for that system. */
  coreId: string;
  /** Core options and EmulatorJS settings applied at boot (user settings win). */
  defaultOptions?: Record<string, string>;
  /**
   * "single": EmulatorJS downloads `biosUrl` into the system directory.
   * "system-dir": the core looks several files up by name; the adapter
   * writes every installed file itself before content loads.
   */
  biosMode?: "single" | "system-dir";
  /**
   * Extension of the battery save the core writes itself when it differs
   * from the `.srm` RetroArch reports (melonDS saves `<game>.sav`).
   */
  saveFileExtension?: string;
  /** Core option that selects the screen arrangement, with its values. */
  layoutOption?: string;
  screenLayouts?: CoreScreenLayout[];
  /** The core takes absolute pointer input: never lock the mouse on click. */
  absolutePointer?: boolean;
  /**
   * "required": EmulatorJS only ships a threaded build of this core, so the
   * page must be cross-origin isolated (SharedArrayBuffer) to run it.
   */
  threads?: "required";
  /** The core renders through WebGL2 only (EmulatorJS ships no legacy build). */
  webgl2?: "required";
  /**
   * "memstick": the core keeps saves as a directory tree on a virtual
   * memory stick instead of one SRAM file; the adapter packs and unpacks
   * that tree (see `MEMSTICK_SAVE_DIR`).
   */
  saveModel?: "memstick";
  /**
   * Where RetroArch's per-core save directory lands in the emulator FS
   * (`savefile_directory` "/data/saves" plus the core's library name). Used
   * before content loads; checked against the path the core reports after.
   */
  saveDirectory?: string;
}

/** Sub-directory of a PSP memory stick that holds game saves. */
const MEMSTICK_SAVE_DIR = "PSP/SAVEDATA";

/**
 * melonDS `melonds_screen_layout` values (src/libretro/libretro_core_options.h
 * in EmulatorJS/melonDS). The first entry is the default.
 */
const NDS_LAYOUTS: CoreScreenLayout[] = [
  { id: "top-bottom", label: "Vertical: top / bottom", value: "Top/Bottom" },
  { id: "bottom-top", label: "Vertical: bottom / top", value: "Bottom/Top" },
  { id: "left-right", label: "Side by side: top left", value: "Left/Right" },
  { id: "right-left", label: "Side by side: bottom left", value: "Right/Left" },
  { id: "hybrid-top", label: "Hybrid: large top", value: "Hybrid Top" },
  { id: "hybrid-bottom", label: "Hybrid: large bottom", value: "Hybrid Bottom" },
  { id: "top-only", label: "Top screen only", value: "Top Only" },
  { id: "bottom-only", label: "Bottom screen only", value: "Bottom Only" },
];

/**
 * Systems the EmulatorJS adapter claims, with the EmulatorJS `system` id and
 * the libretro core it selects for it (see `getCores()` in emulator.js).
 * Each entry is verified end to end by e2e/play-flow.spec.ts before it lands.
 */
const SYSTEM_BINDINGS: Partial<Record<GameSystem, SystemBinding>> = {
  [GameSystem.GBA]: { ejsSystem: "gba", coreId: "mgba" },
  // Gambatte looks gb_bios.bin / gbc_bios.bin up in its system directory
  // when the bootloader option is on; without the files it boots as before.
  [GameSystem.GB]: {
    ejsSystem: "gb",
    coreId: "gambatte",
    biosMode: "system-dir",
    defaultOptions: { gambatte_gb_bootloader: "enabled" },
  },
  [GameSystem.GBC]: {
    ejsSystem: "gb",
    coreId: "gambatte",
    biosMode: "system-dir",
    defaultOptions: { gambatte_gb_bootloader: "enabled" },
  },
  // FCEUmm reads disksys.rom from the system directory for FDS images.
  [GameSystem.NES]: { ejsSystem: "nes", coreId: "fceumm", biosMode: "system-dir" },
  [GameSystem.SNES]: { ejsSystem: "snes", coreId: "snes9x" },
  [GameSystem.GENESIS]: { ejsSystem: "segaMD", coreId: "genesis_plus_gx" },
  [GameSystem.PS1]: { ejsSystem: "psx", coreId: "pcsx_rearmed" },
  [GameSystem.N64]: { ejsSystem: "n64", coreId: "mupen64plus_next" },
  [GameSystem.NDS]: {
    ejsSystem: "nds",
    coreId: "melonds",
    biosMode: "system-dir",
    saveFileExtension: ".sav",
    layoutOption: "melonds_screen_layout",
    screenLayouts: NDS_LAYOUTS,
    absolutePointer: true,
    defaultOptions: {
      // "Touch" reads RetroArch's absolute pointer (mouse position or finger);
      // the default "Mouse" mode moves a cursor by relative deltas and needs
      // pointer lock, which is useless on a touch screen.
      melonds_touch_mode: "Touch",
      // EmulatorJS's own setting; the core's supportsMouse flag turns it on.
      lockMouse: "disabled",
      // Skip the firmware menu: works with FreeBIOS and with real firmware.
      melonds_boot_directly: "enabled",
    },
  },
  // Yabause reads saturn_bios.bin from the system directory and falls back to
  // its high-level BIOS without it. Battery saves are the console's internal
  // backup RAM, which the core writes as its save file.
  [GameSystem.SATURN]: { ejsSystem: "segaSaturn", coreId: "yabause", biosMode: "system-dir" },
  // EmulatorJS hands an arcade set to the core zipped and under the last path
  // segment of the ROM URL, which RetroWeb keeps equal to the set's file name
  // (FBNeo identifies a game by that name). neogeo.zip, when installed, is
  // written next to it.
  [GameSystem.ARCADE]: { ejsSystem: "arcade", coreId: "fbneo", biosMode: "system-dir" },
  [GameSystem.PSP]: {
    ejsSystem: "psp",
    coreId: "ppsspp",
    threads: "required",
    webgl2: "required",
    saveModel: "memstick",
    saveDirectory: "/data/saves/PPSSPP",
  },
};

/** Milliseconds between checks for EmulatorJS's failure flag while loading. */
const LOAD_POLL_MS = 250;
/** EmulatorJS aborts the WASM module one second after the exit event. */
const EXIT_TEARDOWN_MS = 1100;

type Handler = (payload: unknown) => void;

let containerCounter = 0;

export class EmulatorJSAdapter implements EmulatorAdapter {
  readonly id = EMULATORJS_ID;
  readonly supportedSystems = Object.keys(SYSTEM_BINDINGS) as GameSystem[];

  private config?: EmulatorConfig;
  private game?: GameLaunchData;
  private binding?: SystemBinding;
  private emulator?: EjsInstance;
  private mount?: HTMLElement;
  private volume = 0.5;
  private muted = false;
  private startedFlag = false;
  private exited = false;
  private layoutId: string | null = null;
  private initialSaveWritten = false;
  private readonly handlers = new Map<EmulatorEvent, Set<Handler>>();

  get core(): CoreDescriptor {
    return {
      emulatorId: this.id,
      coreId: this.binding?.coreId ?? "unknown",
      coreVersion: this.emulator?.ejs_version ?? EMULATORJS_VERSION,
    };
  }

  capabilityRequirements(system: GameSystem): CapabilityRequirement[] {
    const binding = SYSTEM_BINDINGS[system];
    const requirements = [...BASE_REQUIREMENTS];
    if (binding?.webgl2 === "required") {
      requirements.push({ key: "webgl2", label: "WebGL2" });
    }
    if (binding?.threads === "required") {
      requirements.push({
        key: "sharedArrayBuffer",
        label: "SharedArrayBuffer (the page must be served cross-origin isolated)",
      });
    }
    return requirements;
  }

  async initialize(config: EmulatorConfig): Promise<void> {
    this.config = config;
    this.volume = config.volume;
    this.muted = config.muted;
    await loadEmulatorJsRuntime(config.assetsBaseUrl);
  }

  async loadGame(game: GameLaunchData): Promise<void> {
    const config = this.requireConfig();
    const binding = SYSTEM_BINDINGS[game.system];
    if (!binding) {
      throw new EmulatorError("unsupported_system", `EmulatorJS cannot run ${game.system}.`);
    }
    this.game = game;
    this.binding = binding;
    this.initialSaveWritten = false;
    await this.assertRomReachable(game.romUrl);

    const EmulatorJS = window.EmulatorJS;
    if (!EmulatorJS) {
      throw new EmulatorError("assets_missing", "EmulatorJS runtime is not loaded.");
    }

    config.container.replaceChildren();
    const mount = document.createElement("div");
    mount.id = `retroweb-ejs-${++containerCounter}`;
    mount.style.width = "100%";
    mount.style.height = "100%";
    config.container.appendChild(mount);
    this.mount = mount;

    const base = config.assetsBaseUrl.endsWith("/")
      ? config.assetsBaseUrl
      : `${config.assetsBaseUrl}/`;
    const systemDirFiles = binding.biosMode === "system-dir" ? (game.biosFiles ?? []) : [];
    const sharedMemory = typeof SharedArrayBuffer === "function";
    if (binding.threads === "required" && !sharedMemory) {
      throw new EmulatorError(
        "unsupported_browser",
        "This system needs a threaded emulator core: the page must be served cross-origin isolated (COOP/COEP headers) and the browser must expose SharedArrayBuffer.",
      );
    }
    const ejsConfig: EjsConfig = {
      dataPath: base,
      system: binding.ejsSystem,
      gameUrl: game.romUrl,
      gameName: game.gameId,
      biosUrl: binding.biosMode === "system-dir" ? undefined : game.biosUrl,
      threads: binding.threads === "required" || (config.threads && sharedMemory),
      startOnLoad: false,
      volume: this.muted ? 0 : this.volume,
      // RetroWeb owns ROM caching and save persistence; EmulatorJS's own
      // IndexedDB caches would only duplicate data and key ROMs by file name.
      disableDatabases: true,
      backgroundColor: "#000000",
      color: "#6d5df0",
      noAutoFocus: false,
      // RetroWeb draws its own player controls. Keep only what it does not
      // replace yet: the core settings menu and the controller remapping UI.
      buttonOpts: {
        playPause: false,
        restart: false,
        mute: false,
        fullscreen: false,
        saveState: false,
        loadState: false,
        quickSave: false,
        quickLoad: false,
        screenshot: false,
        screenRecord: false,
        cheat: false,
        cacheManager: false,
        exitEmulation: false,
        netplay: false,
        saveSavFiles: false,
        loadSavFiles: false,
        volumeSlider: false,
        volume: false,
        settings: true,
        gamepad: true,
      },
      capture: { photo: { source: "canvas", format: "png", upscale: 1 } },
    };
    const defaultOptions: Record<string, string> = { ...binding.defaultOptions };
    const preferredCore = config.adapterOptions?.retroarchCore;
    if (typeof preferredCore === "string" && preferredCore) {
      // Lets a system run on an alternative libretro core (e.g. ParaLLEl-N64
      // instead of Mupen64Plus-Next). EmulatorJS validates it against its list.
      defaultOptions.retroarch_core = preferredCore;
    }
    this.layoutId = null;
    if (binding.layoutOption && binding.screenLayouts?.length) {
      const wanted = config.adapterOptions?.screenLayout;
      const layout =
        binding.screenLayouts.find((entry) => entry.id === wanted) ?? binding.screenLayouts[0];
      defaultOptions[binding.layoutOption] = layout.value;
      this.layoutId = layout.id;
    }
    if (Object.keys(defaultOptions).length > 0) ejsConfig.defaultOptions = defaultOptions;
    // Companion files (cue tracks) must sit next to the primary file under
    // their exact names before RetroArch opens the content, and so must BIOS
    // files the core looks up in its system directory ("/"). They are fetched
    // up front and written synchronously once EmulatorJS has mounted its FS.
    const companions = await this.fetchCompanions([
      ...(game.companionFiles ?? []),
      ...systemDirFiles,
    ]);

    const ready = new Promise<void>((resolve, reject) => {
      let settled = false;
      const emulator = new EmulatorJS(`#${mount.id}`, ejsConfig);
      this.emulator = emulator;
      // EmulatorJS 4.2.3 builds the disk menu (multi-disc .m3u sets) before it
      // creates `allSettings`, and `menuOptionChanged("disk", …)` then throws
      // "Cannot set properties of undefined". Creating the map first is enough;
      // `setupSettingsMenu()` replaces it later as usual.
      if (!emulator.allSettings) emulator.allSettings = {};
      // Expose the instance on its mount for debugging tools and e2e tests.
      (mount as HTMLElement & { __emulatorjs?: EjsInstance }).__emulatorjs = emulator;
      emulator.on("saveDatabaseLoaded", (fs) => {
        try {
          writeCompanionFiles(fs as EjsFileSystem, companions);
          if (binding.saveModel === "memstick" && binding.saveDirectory) {
            // The memory stick persists in the browser across games. RetroWeb
            // owns saves server-side, so start every game from an empty
            // SAVEDATA holding only this game's own tree. This must happen
            // before boot: PPSSPP's retro_reset asserts on a boot thread it
            // never joined, so the usual inject-then-reset path is unusable.
            const root = `${binding.saveDirectory}/${MEMSTICK_SAVE_DIR}`;
            clearTree(fs as EjsFileSystem, root);
            if (game.batterySave) {
              unpackTree(fs as EjsFileSystem, root, game.batterySave);
              this.initialSaveWritten = true;
            }
          }
        } catch (error) {
          console.error("failed to prepare the emulator file system", error);
        }
      });
      emulator.on("ready", () => {
        if (settled) return;
        settled = true;
        this.emit("ready", undefined);
        resolve();
      });
      emulator.on("start", () => {
        this.startedFlag = true;
        this.emit("started", undefined);
      });
      emulator.on("exit", () => {
        this.exited = true;
        this.startedFlag = false;
        this.emit("exited", undefined);
      });
      const poll = window.setInterval(() => {
        if (!emulator.failedToStart) return;
        window.clearInterval(poll);
        if (settled) return;
        settled = true;
        reject(this.failure(emulator));
      }, LOAD_POLL_MS);
      emulator.on("ready", () => window.clearInterval(poll));
    });
    await ready;
  }

  async start(): Promise<void> {
    const emulator = this.requireEmulator();
    const mount = this.mount;
    const button = mount?.querySelector<HTMLElement>(".ejs_start_button");
    if (!button) {
      throw new EmulatorError("emulator_failed", "EmulatorJS start button not found.");
    }
    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const finish = (fn: () => void) => {
        if (settled) return;
        settled = true;
        window.clearInterval(poll);
        fn();
      };
      emulator.on("start", () => finish(resolve));
      const poll = window.setInterval(() => {
        if (emulator.failedToStart) finish(() => reject(this.failure(emulator)));
      }, LOAD_POLL_MS);
      emulator.startButtonClicked(button);
    });
    this.applyVolume();
    if (this.binding?.absolutePointer) {
      // `lockMouse: disabled` above covers the menu path; the core's
      // supportsMouse flag sets this directly, so clear it once more.
      emulator.enableMouseLock = false;
    }
    emulator.elements.parent.focus();
  }

  getScreenLayouts(): ScreenLayout[] {
    return (this.binding?.screenLayouts ?? []).map(({ id, label }) => ({ id, label }));
  }

  getScreenLayout(): string | null {
    const binding = this.binding;
    if (!binding?.layoutOption || !binding.screenLayouts) return null;
    // EmulatorJS's own settings menu may hold a value it persisted earlier.
    const stored = this.emulator?.getSettingValue?.(binding.layoutOption);
    const match = binding.screenLayouts.find((entry) => entry.value === stored);
    return match?.id ?? this.layoutId;
  }

  async setScreenLayout(id: string): Promise<void> {
    const binding = this.binding;
    const layout = binding?.screenLayouts?.find((entry) => entry.id === id);
    if (!binding?.layoutOption || !layout) {
      throw new EmulatorError("emulator_failed", `Unknown screen layout "${id}".`);
    }
    const emulator = this.requireRunning();
    // Goes through EmulatorJS so its menu and the core agree; the core picks
    // the change up on its next frame (RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE).
    if (typeof emulator.menuOptionChanged === "function") {
      emulator.menuOptionChanged(binding.layoutOption, layout.value);
    } else {
      emulator.gameManager?.setVariable(binding.layoutOption, layout.value);
    }
    this.layoutId = layout.id;
    emulator.elements.parent.focus();
  }

  async pause(): Promise<void> {
    const emulator = this.requireRunning();
    emulator.pause?.();
  }

  async resume(): Promise<void> {
    const emulator = this.requireRunning();
    emulator.play?.();
    emulator.elements.parent.focus();
  }

  async stop(): Promise<void> {
    const emulator = this.emulator;
    if (!emulator || this.exited) return;
    if (this.startedFlag) {
      emulator.callEvent("exit");
    }
    this.exited = true;
    this.startedFlag = false;
    // Listeners EmulatorJS registered on window/document guard on `started`;
    // clearing it turns them into no-ops after teardown.
    emulator.started = false;
    emulator.gamepad?.terminate();
  }

  async reset(): Promise<void> {
    const emulator = this.requireRunning();
    emulator.gameManager?.restart();
  }

  isRunning(): boolean {
    return this.startedFlag && !this.exited;
  }

  isPaused(): boolean {
    return this.emulator?.paused ?? true;
  }

  async getSaveData(): Promise<Uint8Array | null> {
    const manager = this.requireRunning().gameManager;
    if (!manager) return null;
    if (this.binding?.saveModel === "memstick") {
      return packTree(manager.FS, this.memstickSaveDir(manager));
    }
    // Ask RetroArch to flush SRAM to its file first (no-op for cores that
    // write their own save file), then read whichever file this core keeps.
    manager.saveSaveFiles();
    const path = this.saveFilePath(manager);
    if (!manager.FS.analyzePath(path).exists) return null;
    return new Uint8Array(manager.FS.readFile(path));
  }

  initialSaveApplied(): boolean {
    return this.initialSaveWritten;
  }

  async loadSaveData(data: Uint8Array): Promise<void> {
    const manager = this.requireRunning().gameManager;
    if (!manager) throw new EmulatorError("not_running", "Emulator is not running.");
    if (this.binding?.saveModel === "memstick") {
      const root = this.memstickSaveDir(manager);
      clearTree(manager.FS, root);
      unpackTree(manager.FS, root, data);
      return; // the reset that follows re-reads the memory stick
    }
    const path = this.saveFilePath(manager);
    ensureParentDirectories(manager.FS, path);
    if (manager.FS.analyzePath(path).exists) manager.FS.unlink(path);
    manager.FS.writeFile(path, data);
    // Cores exposing SRAM through libretro re-read it here; cores that manage
    // the file themselves (melonDS) pick it up on the reset that follows.
    manager.loadSaveFiles();
  }

  /**
   * Where the running core keeps its battery save. RetroArch reports the
   * SRAM path (`.srm`); a core that writes its own save file next to it
   * under another extension is mapped through `saveFileExtension`.
   */
  /** `<save directory>/PSP/SAVEDATA`, taking the directory from the core once it runs. */
  private memstickSaveDir(manager: EjsGameManager): string {
    const reported = manager.getSaveFilePath();
    const directory = reported.slice(0, Math.max(0, reported.lastIndexOf("/")));
    const expected = this.binding?.saveDirectory;
    if (expected && expected !== directory) {
      console.warn(`memory stick expected at ${expected} but the core reports ${directory}`);
    }
    return `${directory}/${MEMSTICK_SAVE_DIR}`;
  }

  private saveFilePath(manager: EjsGameManager): string {
    const reported = manager.getSaveFilePath();
    const extension = this.binding?.saveFileExtension;
    if (!extension) return reported;
    const dot = reported.lastIndexOf(".");
    const slash = reported.lastIndexOf("/");
    return (dot > slash ? reported.slice(0, dot) : reported) + extension;
  }

  async saveState(): Promise<Uint8Array> {
    const manager = this.requireRunning().gameManager;
    if (!manager) throw new EmulatorError("not_running", "Emulator is not running.");
    try {
      return new Uint8Array(manager.getState());
    } catch (error) {
      throw new EmulatorError("state_failed", "The emulator could not serialise its state.", error);
    }
  }

  async loadState(data: Uint8Array): Promise<void> {
    const manager = this.requireRunning().gameManager;
    if (!manager) throw new EmulatorError("not_running", "Emulator is not running.");
    try {
      manager.loadState(new Uint8Array(data));
    } catch (error) {
      throw new EmulatorError("state_failed", "The emulator rejected this save state.", error);
    }
  }

  async getScreenshot(): Promise<Blob> {
    const emulator = this.requireRunning();
    const { blob } = await emulator.takeScreenshot("canvas", "png", 1);
    return blob;
  }

  setVolume(volume: number): void {
    this.volume = Math.min(1, Math.max(0, volume));
    this.applyVolume();
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    this.applyVolume();
  }

  async enterFullscreen(): Promise<void> {
    const target = this.config?.fullscreenTarget ?? this.config?.container;
    if (target && !document.fullscreenElement) await target.requestFullscreen();
  }

  async exitFullscreen(): Promise<void> {
    if (document.fullscreenElement) await document.exitFullscreen();
  }

  openControlSettings(): boolean {
    const menu = this.emulator?.controlMenu;
    if (!menu || !this.isRunning()) return false;
    // Same as EmulatorJS's own bottom-bar button: the dialog is a hidden
    // element it built at start-up.
    menu.style.display = "";
    return true;
  }

  on<E extends EmulatorEvent>(event: E, handler: (payload: EmulatorEventMap[E]) => void): () => void {
    let set = this.handlers.get(event);
    if (!set) {
      set = new Set();
      this.handlers.set(event, set);
    }
    const wrapped = handler as Handler;
    set.add(wrapped);
    return () => set?.delete(wrapped);
  }

  async destroy(): Promise<void> {
    await this.stop();
    this.handlers.clear();
    const mount = this.mount;
    this.mount = undefined;
    this.emulator = undefined;
    if (mount) {
      // Give EmulatorJS its one-second grace period to flush and abort the
      // module before the canvas disappears from the document.
      await new Promise((resolve) => window.setTimeout(resolve, EXIT_TEARDOWN_MS));
      mount.remove();
    }
  }

  // -- internals ----------------------------------------------------------

  private emit<E extends EmulatorEvent>(event: E, payload: EmulatorEventMap[E]): void {
    this.handlers.get(event)?.forEach((handler) => handler(payload));
  }

  private applyVolume(): void {
    const emulator = this.emulator;
    if (!emulator) return;
    const effective = this.muted ? 0 : this.volume;
    emulator.volume = this.volume;
    if (typeof emulator.setVolume === "function" && this.startedFlag) {
      emulator.setVolume(effective);
    }
  }

  private requireConfig(): EmulatorConfig {
    if (!this.config) throw new EmulatorError("emulator_failed", "Adapter not initialised.");
    return this.config;
  }

  private requireEmulator(): EjsInstance {
    if (!this.emulator) throw new EmulatorError("not_running", "No game is loaded.");
    return this.emulator;
  }

  private requireRunning(): EjsInstance {
    const emulator = this.requireEmulator();
    if (!this.startedFlag || this.exited) {
      throw new EmulatorError("not_running", "The game is not running.");
    }
    return emulator;
  }

  private failure(emulator: EjsInstance): EmulatorError {
    const text = emulator.textElem?.innerText?.trim() ?? "";
    if (/bios/i.test(text)) {
      return new EmulatorError("bios_missing", "This game needs a BIOS file that is not installed.");
    }
    if (/network/i.test(text)) {
      return new EmulatorError("rom_download_failed", "The ROM could not be downloaded.");
    }
    return new EmulatorError("emulator_failed", text || "The emulator failed to start.");
  }

  private async fetchCompanions(
    files: { filename: string; url: string }[],
  ): Promise<{ filename: string; data: Uint8Array }[]> {
    return Promise.all(
      files.map(async (file) => {
        let response: Response;
        try {
          response = await fetch(file.url, { credentials: "same-origin" });
        } catch (error) {
          throw new EmulatorError(
            "rom_download_failed",
            `Could not download ${file.filename}.`,
            error,
          );
        }
        if (response.status === 404) {
          throw new EmulatorError("rom_missing", `${file.filename} is missing on the server.`);
        }
        if (!response.ok) {
          throw new EmulatorError(
            "rom_download_failed",
            `The server refused ${file.filename} (HTTP ${response.status}).`,
          );
        }
        return { filename: file.filename, data: new Uint8Array(await response.arrayBuffer()) };
      }),
    );
  }

  private async assertRomReachable(romUrl: string): Promise<void> {
    let response: Response;
    try {
      response = await fetch(romUrl, { method: "HEAD", credentials: "same-origin" });
    } catch (error) {
      throw new EmulatorError("rom_download_failed", "Could not reach the server for the ROM.", error);
    }
    if (response.status === 404) {
      throw new EmulatorError("rom_missing", "The ROM file for this game is missing on the server.");
    }
    if (!response.ok) {
      throw new EmulatorError(
        "rom_download_failed",
        `The server refused the ROM download (HTTP ${response.status}).`,
      );
    }
  }
}

function writeCompanionFiles(
  fs: EjsFileSystem,
  companions: { filename: string; data: Uint8Array }[],
): void {
  for (const companion of companions) {
    const path = `/${companion.filename}`;
    if (fs.analyzePath(path).exists) fs.unlink(path);
    fs.writeFile(path, companion.data);
  }
}

function ensureParentDirectories(fs: EjsFileSystem, path: string): void {
  const parts = path.split("/").filter(Boolean);
  let current = "";
  for (let i = 0; i < parts.length - 1; i += 1) {
    current += `/${parts[i]}`;
    if (!fs.analyzePath(current).exists) fs.mkdir(current);
  }
}

export function createEmulatorJSAdapter(): EmulatorAdapter {
  return new EmulatorJSAdapter();
}
