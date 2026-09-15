"""Central definition of game systems.

Must stay in sync with ``packages/shared/src/systems.ts`` (a test checks the
enum ids match). Adding a system here is not enough to play it: an emulator
adapter in the frontend must claim it (``supported`` is reported by the API
from ``ADAPTER_SUPPORTED_SYSTEMS`` for informational purposes).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class GameSystem(enum.StrEnum):
    GB = "gb"
    GBC = "gbc"
    GBA = "gba"
    NES = "nes"
    SNES = "snes"
    GENESIS = "genesis"
    N64 = "n64"
    PS1 = "ps1"
    PSP = "psp"
    NDS = "nds"


@dataclass(frozen=True)
class SystemInfo:
    id: GameSystem
    name: str
    short_name: str
    manufacturer: str
    extensions: tuple[str, ...]
    # Folder names under roms/ that map to this system (lowercase).
    folder_aliases: tuple[str, ...] = field(default_factory=tuple)
    # Extensions that are ambiguous across systems (need header sniffing).
    ambiguous_extensions: tuple[str, ...] = field(default_factory=tuple)


SYSTEMS: dict[GameSystem, SystemInfo] = {
    GameSystem.GB: SystemInfo(
        GameSystem.GB, "Game Boy", "GB", "Nintendo", (".gb",), ("gb", "gameboy")
    ),
    GameSystem.GBC: SystemInfo(
        GameSystem.GBC, "Game Boy Color", "GBC", "Nintendo", (".gbc",), ("gbc",)
    ),
    GameSystem.GBA: SystemInfo(
        GameSystem.GBA, "Game Boy Advance", "GBA", "Nintendo", (".gba",), ("gba",)
    ),
    GameSystem.NES: SystemInfo(
        GameSystem.NES,
        "Nintendo Entertainment System",
        "NES",
        "Nintendo",
        (".nes", ".fds", ".unf", ".unif"),
        ("nes", "fc", "famicom"),
    ),
    GameSystem.SNES: SystemInfo(
        GameSystem.SNES,
        "Super Nintendo",
        "SNES",
        "Nintendo",
        (".sfc", ".smc"),
        ("snes", "sfc", "superfamicom"),
    ),
    GameSystem.GENESIS: SystemInfo(
        GameSystem.GENESIS,
        "Sega Genesis / Mega Drive",
        "Genesis",
        "Sega",
        (".md", ".gen", ".smd", ".bin"),
        ("genesis", "megadrive", "md"),
        ambiguous_extensions=(".bin",),
    ),
    GameSystem.N64: SystemInfo(
        GameSystem.N64,
        "Nintendo 64",
        "N64",
        "Nintendo",
        (".z64", ".n64", ".v64"),
        ("n64",),
    ),
    # Extensions are the ones PCSX-ReARMed accepts in EmulatorJS (core.json);
    # .chd and .iso are deliberately absent because that build cannot open them.
    GameSystem.PS1: SystemInfo(
        GameSystem.PS1,
        "PlayStation",
        "PS1",
        "Sony",
        (".cue", ".pbp", ".m3u", ".ccd", ".img", ".bin"),
        ("ps1", "psx", "playstation"),
        ambiguous_extensions=(".bin",),
    ),
    GameSystem.PSP: SystemInfo(
        GameSystem.PSP,
        "PlayStation Portable",
        "PSP",
        "Sony",
        (".iso", ".cso", ".pbp"),
        ("psp",),
        ambiguous_extensions=(".iso", ".pbp"),
    ),
    GameSystem.NDS: SystemInfo(
        GameSystem.NDS, "Nintendo DS", "NDS", "Nintendo", (".nds",), ("nds", "ds")
    ),
}

# Systems the frontend currently has an adapter for. Informational: the
# registry in packages/emulator-core is the source of truth in the browser.
ADAPTER_SUPPORTED_SYSTEMS: frozenset[GameSystem] = frozenset(
    {
        GameSystem.GBA,
        GameSystem.GB,
        GameSystem.GBC,
        GameSystem.NES,
        GameSystem.SNES,
        GameSystem.GENESIS,
        GameSystem.PS1,
        GameSystem.N64,
        GameSystem.NDS,
    }
)


def system_for_folder(folder: str) -> GameSystem | None:
    needle = folder.lower()
    for info in SYSTEMS.values():
        if needle == info.id.value or needle in info.folder_aliases:
            return info.id
    return None


def systems_for_extension(extension: str) -> list[GameSystem]:
    ext = extension.lower()
    return [info.id for info in SYSTEMS.values() if ext in info.extensions]


def is_extension_valid_for(system: GameSystem, extension: str) -> bool:
    return extension.lower() in SYSTEMS[system].extensions


# Files that describe other files rather than containing game data themselves.
CONTAINER_EXTENSIONS: frozenset[str] = frozenset({".cue"})


def all_extensions() -> frozenset[str]:
    return frozenset(ext for info in SYSTEMS.values() for ext in info.extensions)
