/**
 * Emulator failures carry a machine-readable code so the UI can explain what
 * went wrong (missing BIOS vs. unsupported browser vs. network).
 */
export type EmulatorErrorCode =
  | "unsupported_browser"
  | "unsupported_system"
  | "assets_missing"
  | "rom_missing"
  | "rom_download_failed"
  | "bios_missing"
  | "emulator_failed"
  | "state_failed"
  | "not_running";

export class EmulatorError extends Error {
  readonly code: EmulatorErrorCode;
  readonly cause?: unknown;

  constructor(code: EmulatorErrorCode, message: string, cause?: unknown) {
    super(message);
    this.name = "EmulatorError";
    this.code = code;
    this.cause = cause;
  }
}
