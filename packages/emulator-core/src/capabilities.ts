/**
 * Feature detection run before an emulator is created, so failures are
 * explained ("your browser lacks WebGL") instead of surfacing as a blank canvas.
 */
export interface BrowserCapabilities {
  webAssembly: boolean;
  webgl: boolean;
  webgl2: boolean;
  sharedArrayBuffer: boolean;
  crossOriginIsolated: boolean;
  gamepad: boolean;
  indexedDb: boolean;
  fullscreen: boolean;
  audioContext: boolean;
}

export function detectBrowserCapabilities(): BrowserCapabilities {
  const hasWindow = typeof window !== "undefined";
  const probeWebgl = (context: "webgl" | "webgl2"): boolean => {
    if (!hasWindow || typeof document === "undefined") return false;
    try {
      const canvas = document.createElement("canvas");
      return canvas.getContext(context) !== null;
    } catch {
      return false;
    }
  };
  return {
    webAssembly: typeof WebAssembly === "object" && typeof WebAssembly.instantiate === "function",
    webgl: probeWebgl("webgl"),
    webgl2: probeWebgl("webgl2"),
    sharedArrayBuffer: hasWindow && typeof SharedArrayBuffer === "function",
    crossOriginIsolated: hasWindow && Boolean(window.crossOriginIsolated),
    gamepad: hasWindow && typeof navigator !== "undefined" && "getGamepads" in navigator,
    indexedDb: hasWindow && typeof indexedDB !== "undefined",
    fullscreen:
      hasWindow && typeof document !== "undefined" && "requestFullscreen" in document.documentElement,
    audioContext:
      hasWindow &&
      (typeof AudioContext === "function" ||
        typeof (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext ===
          "function"),
  };
}

export interface CapabilityRequirement {
  key: keyof BrowserCapabilities;
  label: string;
}

/** Requirements for running any core with EmulatorJS. */
export const BASE_REQUIREMENTS: CapabilityRequirement[] = [
  { key: "webAssembly", label: "WebAssembly" },
  { key: "webgl", label: "WebGL" },
];

export const THREADED_REQUIREMENTS: CapabilityRequirement[] = [
  ...BASE_REQUIREMENTS,
  { key: "sharedArrayBuffer", label: "SharedArrayBuffer (needs COOP/COEP headers)" },
];

export function missingCapabilities(
  capabilities: BrowserCapabilities,
  requirements: CapabilityRequirement[],
): CapabilityRequirement[] {
  return requirements.filter((requirement) => !capabilities[requirement.key]);
}
