import type { GameSystem } from "@retroweb/shared";
import type { AdapterFactory, EmulatorAdapter } from "./adapter";
import { EmulatorError } from "./errors";

interface Registration {
  adapterId: string;
  factory: AdapterFactory;
}

/**
 * Maps a system to the adapter that runs it. UI code asks the registry;
 * nothing else in the app switches on system ids.
 */
export class EmulatorRegistry {
  private readonly bySystem = new Map<GameSystem, Registration>();

  register(adapterId: string, systems: GameSystem[], factory: AdapterFactory): void {
    for (const system of systems) {
      this.bySystem.set(system, { adapterId, factory });
    }
  }

  supports(system: GameSystem): boolean {
    return this.bySystem.has(system);
  }

  supportedSystems(): GameSystem[] {
    return [...this.bySystem.keys()];
  }

  adapterIdFor(system: GameSystem): string | undefined {
    return this.bySystem.get(system)?.adapterId;
  }

  getEmulator(system: GameSystem): EmulatorAdapter {
    const registration = this.bySystem.get(system);
    if (!registration) {
      throw new EmulatorError(
        "unsupported_system",
        `No emulator is available for ${system} yet.`,
      );
    }
    return registration.factory();
  }
}
