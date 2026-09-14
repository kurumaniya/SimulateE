import { EmulatorError } from "../../errors";

/**
 * EmulatorJS's `loader.js` loads these files in this order and then constructs
 * `EmulatorJS`. The adapter performs the same bootstrap so it can pass a
 * config object instead of `window.EJS_*` globals. The npm package ships no
 * minified bundle, so the `src/` files are used directly.
 */
const RUNTIME_SCRIPTS = [
  "src/emulator.js",
  "src/nipplejs.js",
  "src/shaders.js",
  "src/storage.js",
  "src/gamepad.js",
  "src/GameManager.js",
  "src/socket.io.min.js",
  "src/compression.js",
];
const RUNTIME_STYLESHEET = "emulator.css";

const loaded = new Map<string, Promise<void>>();

function loadScript(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${url}"]`);
    if (existing?.dataset.loaded === "true") return resolve();
    const script = existing ?? document.createElement("script");
    script.src = url;
    script.async = false;
    script.addEventListener("load", () => {
      script.dataset.loaded = "true";
      resolve();
    });
    script.addEventListener("error", () => reject(new Error(`Failed to load ${url}`)));
    if (!existing) document.head.appendChild(script);
  });
}

function loadStylesheet(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`link[href="${url}"]`)) return resolve();
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url;
    link.addEventListener("load", () => resolve());
    link.addEventListener("error", () => reject(new Error(`Failed to load ${url}`)));
    document.head.appendChild(link);
  });
}

/** Load the EmulatorJS runtime once per assets base URL. */
export function loadEmulatorJsRuntime(assetsBaseUrl: string): Promise<void> {
  const base = assetsBaseUrl.endsWith("/") ? assetsBaseUrl : `${assetsBaseUrl}/`;
  let pending = loaded.get(base);
  if (!pending) {
    pending = (async () => {
      try {
        await loadStylesheet(`${base}${RUNTIME_STYLESHEET}`);
        for (const file of RUNTIME_SCRIPTS) {
          await loadScript(`${base}${file}`);
        }
      } catch (error) {
        loaded.delete(base);
        throw new EmulatorError(
          "assets_missing",
          "The emulator runtime is not installed on this server. Run `npm run fetch-emulator`.",
          error,
        );
      }
      if (typeof window.EmulatorJS !== "function") {
        loaded.delete(base);
        throw new EmulatorError(
          "assets_missing",
          "The emulator runtime loaded but did not expose EmulatorJS.",
        );
      }
    })();
    loaded.set(base, pending);
  }
  return pending;
}
