import { EmulatorRegistry, createEmulatorJSAdapter, EMULATORJS_ID, EmulatorJSAdapter } from "@retroweb/emulator-core";

/** Where scripts/fetch-emulatorjs.mjs places the runtime (served by Next.js). */
export const EMULATORJS_ASSETS_URL = "/emulatorjs/";

let registry: EmulatorRegistry | undefined;

/** The single place that knows which adapter serves which system. */
export function getEmulatorRegistry(): EmulatorRegistry {
  if (!registry) {
    registry = new EmulatorRegistry();
    registry.register(EMULATORJS_ID, new EmulatorJSAdapter().supportedSystems, createEmulatorJSAdapter);
  }
  return registry;
}
