/**
 * Minimal typings for the parts of the EmulatorJS 4.2.3 runtime the adapter
 * touches. Verified against `data/src/emulator.js` and `GameManager.js`;
 * see docs/emulator-support.md.
 */
export interface EjsFileSystem {
  writeFile(path: string, data: Uint8Array): void;
  readFile(path: string): Uint8Array;
  unlink(path: string): void;
  mkdir(path: string): void;
  analyzePath(path: string): { exists: boolean };
  stat(path: string): { mtime: Date; size: number };
}

export interface EjsGameManager {
  FS: EjsFileSystem;
  getState(): Uint8Array;
  loadState(state: Uint8Array): void;
  getSaveFile(save?: boolean): Uint8Array | null;
  getSaveFilePath(): string;
  loadSaveFiles(): void;
  saveSaveFiles(): void;
  restart(): void;
  supportsStates(): boolean;
  toggleMainLoop(playing: number): void;
  /** Sets a libretro core option at run time (`ejs_set_variable`). */
  setVariable(option: string, value: string): void;
}

export interface EjsInstance {
  ejs_version: string;
  started: boolean;
  paused: boolean;
  failedToStart: boolean;
  volume: number;
  muted: boolean;
  gameManager?: EjsGameManager;
  /** Set from the core's `supportsMouse` flag; a canvas click then locks the pointer. */
  enableMouseLock?: boolean;
  /** Value of a setting as EmulatorJS's own menu holds it (after start). */
  getSettingValue?(id: string): string | null;
  /** Applies a setting through EmulatorJS's menu path, persisting it in its localStorage. */
  menuOptionChanged?(option: string, value: string): void;
  textElem?: HTMLElement | null;
  elements: { parent: HTMLElement; menu?: HTMLElement };
  gamepad?: { terminate(): void };
  on(event: string, handler: (payload?: unknown) => void): void;
  callEvent(event: string, data?: unknown): number;
  startButtonClicked(target: HTMLElement | Event): void;
  pause?(dontUpdate?: boolean): void;
  play?(dontUpdate?: boolean): void;
  setVolume?(volume: number): void;
  toggleFullscreen?(fullscreen: boolean): void;
  takeScreenshot(
    source: "canvas" | "retroarch",
    format: string,
    upscale: number,
  ): Promise<{ blob: Blob; format: string }>;
}

export interface EjsConfig {
  dataPath: string;
  system: string;
  gameUrl: string;
  gameName?: string;
  biosUrl?: string;
  threads?: boolean;
  startOnLoad?: boolean;
  volume?: number;
  disableDatabases?: boolean;
  backgroundColor?: string;
  color?: string;
  noAutoFocus?: boolean;
  buttonOpts?: Record<string, boolean>;
  capture?: { photo?: { source?: string; format?: string; upscale?: number } };
  /**
   * Absolute path inside the emulator FS → URL. Not used by the adapter:
   * in 4.2.3 explicit paths are written with an ArrayBuffer, which Emscripten
   * rejects, leaving an empty file. See `writeCompanionFiles`.
   */
  externalFiles?: Record<string, string>;
  langJson?: Record<string, string>;
  /** Initial values for EmulatorJS settings (e.g. `retroarch_core`). */
  defaultOptions?: Record<string, string>;
}

export type EjsConstructor = new (selector: string, config: EjsConfig) => EjsInstance;

declare global {
  interface Window {
    EmulatorJS?: EjsConstructor;
  }
}
