import { GameSystem } from "@retroweb/shared";
import type {
  CoreDescriptor,
  EmulatorAdapter,
  EmulatorConfig,
  EmulatorEvent,
  EmulatorEventMap,
  GameLaunchData,
} from "../../adapter";
import { EmulatorError } from "../../errors";
import { loadEmulatorJsRuntime } from "./runtime";
import type { EjsConfig, EjsFileSystem, EjsInstance } from "./types";

export const EMULATORJS_ID = "emulatorjs";
/** Pinned in scripts/fetch-emulatorjs.mjs; the runtime reports it at run time too. */
export const EMULATORJS_VERSION = "4.2.3";

interface SystemBinding {
  /** EmulatorJS `system` config value. */
  ejsSystem: string;
  /** libretro core EmulatorJS selects for that system. */
  coreId: string;
}

/** Systems the EmulatorJS adapter claims. Extend per phase after verifying. */
const SYSTEM_BINDINGS: Partial<Record<GameSystem, SystemBinding>> = {
  [GameSystem.GBA]: { ejsSystem: "gba", coreId: "mgba" },
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
  private readonly handlers = new Map<EmulatorEvent, Set<Handler>>();

  get core(): CoreDescriptor {
    return {
      emulatorId: this.id,
      coreId: this.binding?.coreId ?? "unknown",
      coreVersion: this.emulator?.ejs_version ?? EMULATORJS_VERSION,
    };
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
    const ejsConfig: EjsConfig = {
      dataPath: base,
      system: binding.ejsSystem,
      gameUrl: game.romUrl,
      gameName: game.gameId,
      biosUrl: game.biosUrl,
      threads: config.threads && typeof SharedArrayBuffer === "function",
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
        settings: true,
        gamepad: true,
      },
      capture: { photo: { source: "canvas", format: "png", upscale: 1 } },
    };

    const ready = new Promise<void>((resolve, reject) => {
      let settled = false;
      const emulator = new EmulatorJS(`#${mount.id}`, ejsConfig);
      this.emulator = emulator;
      // Expose the instance on its mount for debugging tools and e2e tests.
      (mount as HTMLElement & { __emulatorjs?: EjsInstance }).__emulatorjs = emulator;
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
    const data = manager.getSaveFile();
    return data ? new Uint8Array(data) : null;
  }

  async loadSaveData(data: Uint8Array): Promise<void> {
    const manager = this.requireRunning().gameManager;
    if (!manager) throw new EmulatorError("not_running", "Emulator is not running.");
    const path = manager.getSaveFilePath();
    ensureParentDirectories(manager.FS, path);
    if (manager.FS.analyzePath(path).exists) manager.FS.unlink(path);
    manager.FS.writeFile(path, data);
    manager.loadSaveFiles();
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
