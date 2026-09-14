import type { GameSystem } from "@retroweb/shared";

/** Options every adapter understands. Adapter-specific options are nested. */
export interface EmulatorConfig {
  /** Element the emulator renders into. Emptied by the adapter. */
  container: HTMLElement;
  /** Element to fullscreen (defaults to `container`); lets the UI keep its overlay. */
  fullscreenTarget?: HTMLElement;
  /** Base URL (with trailing slash) where emulator runtime assets are served. */
  assetsBaseUrl: string;
  volume: number;
  muted: boolean;
  /** Ask the runtime to use threads when the browser supports them. */
  threads: boolean;
  /** Opaque adapter-specific options (e.g. PSP resolution scale). */
  adapterOptions?: Record<string, unknown>;
}

export interface GameLaunchData {
  gameId: string;
  title: string;
  system: GameSystem;
  /** Same-origin URL that streams the ROM (supports Range requests). */
  romUrl: string;
  romFilename: string;
  /** Same-origin URL of a user-supplied BIOS, when the system needs one. */
  biosUrl?: string;
}

export type EmulatorEvent = "ready" | "started" | "exited" | "error";

export interface EmulatorEventMap {
  ready: void;
  started: void;
  exited: void;
  error: EmulatorErrorLike;
}

export interface EmulatorErrorLike {
  code: string;
  message: string;
}

export interface CoreDescriptor {
  /** Adapter id, e.g. "emulatorjs". */
  emulatorId: string;
  /** Core id inside the adapter, e.g. "mgba". */
  coreId: string;
  /** Version string stored alongside save states for compatibility checks. */
  coreVersion: string;
}

/**
 * The only surface the UI touches. Adapters move bytes and drive the
 * emulator; they do not know about slots, servers or IndexedDB.
 */
export interface EmulatorAdapter {
  readonly id: string;
  readonly supportedSystems: GameSystem[];
  readonly core: CoreDescriptor;

  initialize(config: EmulatorConfig): Promise<void>;
  loadGame(game: GameLaunchData): Promise<void>;

  start(): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  stop(): Promise<void>;
  reset(): Promise<void>;
  isRunning(): boolean;
  isPaused(): boolean;

  /** Battery save (SRAM/flash) as the emulator currently holds it. */
  getSaveData(): Promise<Uint8Array | null>;
  loadSaveData(data: Uint8Array): Promise<void>;

  /** Serialise the full emulator state. */
  saveState(): Promise<Uint8Array>;
  loadState(data: Uint8Array): Promise<void>;

  getScreenshot(): Promise<Blob>;

  setVolume(volume: number): void;
  setMuted(muted: boolean): void;
  enterFullscreen(): Promise<void>;
  exitFullscreen(): Promise<void>;

  on<E extends EmulatorEvent>(event: E, handler: (payload: EmulatorEventMap[E]) => void): () => void;

  destroy(): Promise<void>;
}

export type AdapterFactory = () => EmulatorAdapter;
