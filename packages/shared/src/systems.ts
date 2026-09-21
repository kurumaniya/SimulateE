/**
 * Game systems known to the platform.
 *
 * Mirrors `apps/api/retroweb/library/systems.py`; the backend test suite
 * checks that both enums contain the same ids.
 */
export enum GameSystem {
  GB = "gb",
  GBC = "gbc",
  GBA = "gba",
  NES = "nes",
  SNES = "snes",
  GENESIS = "genesis",
  N64 = "n64",
  PS1 = "ps1",
  PSP = "psp",
  NDS = "nds",
  SATURN = "saturn",
  ARCADE = "arcade",
}

export interface SystemInfo {
  id: GameSystem;
  name: string;
  shortName: string;
  manufacturer: string;
  extensions: string[];
  /** Accent used for platform badges and placeholder covers. */
  accent: string;
}

export const SYSTEMS: Record<GameSystem, SystemInfo> = {
  [GameSystem.GB]: {
    id: GameSystem.GB,
    name: "Game Boy",
    shortName: "GB",
    manufacturer: "Nintendo",
    extensions: [".gb"],
    accent: "#8fae4f",
  },
  [GameSystem.GBC]: {
    id: GameSystem.GBC,
    name: "Game Boy Color",
    shortName: "GBC",
    manufacturer: "Nintendo",
    extensions: [".gbc"],
    accent: "#7b5cd6",
  },
  [GameSystem.GBA]: {
    id: GameSystem.GBA,
    name: "Game Boy Advance",
    shortName: "GBA",
    manufacturer: "Nintendo",
    extensions: [".gba"],
    accent: "#5b4bd8",
  },
  [GameSystem.NES]: {
    id: GameSystem.NES,
    name: "Nintendo Entertainment System",
    shortName: "NES",
    manufacturer: "Nintendo",
    extensions: [".nes", ".fds", ".unf", ".unif"],
    accent: "#c94848",
  },
  [GameSystem.SNES]: {
    id: GameSystem.SNES,
    name: "Super Nintendo",
    shortName: "SNES",
    manufacturer: "Nintendo",
    extensions: [".sfc", ".smc"],
    accent: "#8a6fd8",
  },
  [GameSystem.GENESIS]: {
    id: GameSystem.GENESIS,
    name: "Sega Genesis / Mega Drive",
    shortName: "Genesis",
    manufacturer: "Sega",
    extensions: [".md", ".gen", ".smd", ".bin"],
    accent: "#2f6fd6",
  },
  [GameSystem.N64]: {
    id: GameSystem.N64,
    name: "Nintendo 64",
    shortName: "N64",
    manufacturer: "Nintendo",
    extensions: [".z64", ".n64", ".v64"],
    accent: "#2c9c5a",
  },
  [GameSystem.PS1]: {
    id: GameSystem.PS1,
    name: "PlayStation",
    shortName: "PS1",
    manufacturer: "Sony",
    // Mirrors the backend registry: what the EmulatorJS PCSX-ReARMed build
    // can open. .chd and .iso are deliberately absent.
    extensions: [".cue", ".pbp", ".m3u", ".ccd", ".img", ".bin"],
    accent: "#9aa4b2",
  },
  [GameSystem.PSP]: {
    id: GameSystem.PSP,
    name: "PlayStation Portable",
    shortName: "PSP",
    manufacturer: "Sony",
    extensions: [".iso", ".cso", ".pbp"],
    accent: "#3b3f4a",
  },
  [GameSystem.NDS]: {
    id: GameSystem.NDS,
    name: "Nintendo DS",
    shortName: "NDS",
    manufacturer: "Nintendo",
    extensions: [".nds"],
    accent: "#c2c8d0",
  },
  [GameSystem.SATURN]: {
    id: GameSystem.SATURN,
    name: "Sega Saturn",
    shortName: "Saturn",
    manufacturer: "Sega",
    // Recognised only inside roms/saturn/: every extension is shared with PS1 or PSP.
    extensions: [".cue", ".ccd", ".iso", ".m3u", ".img", ".bin"],
    accent: "#4a6fd0",
  },
  [GameSystem.ARCADE]: {
    id: GameSystem.ARCADE,
    name: "Arcade",
    shortName: "Arcade",
    manufacturer: "Various",
    // FBNeo ROM sets, kept zipped under their exact set name (roms/arcade/sf2.zip).
    extensions: [".zip"],
    accent: "#e0a030",
  },
};

export const ALL_SYSTEMS: SystemInfo[] = Object.values(SYSTEMS);

export function systemInfo(system: GameSystem | string): SystemInfo | undefined {
  return SYSTEMS[system as GameSystem];
}

export function systemName(system: GameSystem | string): string {
  return systemInfo(system)?.name ?? String(system).toUpperCase();
}
