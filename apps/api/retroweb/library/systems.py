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
    SATURN = "saturn"
    ARCADE = "arcade"


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
    # True: files belong to this system only inside one of its folders. Its
    # extensions say nothing on their own (.zip, .iso, .cue) and there is no
    # header to sniff, so extension-based detection never picks it.
    folder_only: bool = False


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
    # Yabause opens cue/bin, ccd/img and iso images. Folder only: every one of
    # those extensions already belongs to the PlayStation or the PSP.
    GameSystem.SATURN: SystemInfo(
        GameSystem.SATURN,
        "Sega Saturn",
        "Saturn",
        "Sega",
        (".cue", ".ccd", ".iso", ".m3u", ".img", ".bin"),
        ("saturn", "segasaturn", "ss"),
        folder_only=True,
    ),
    # FBNeo loads a ROM set by its exact MAME-style file name (sf2.zip); the
    # archive is handed to the core as it is and never unpacked.
    GameSystem.ARCADE: SystemInfo(
        GameSystem.ARCADE,
        "Arcade",
        "Arcade",
        "Various",
        (".zip",),
        ("arcade", "fbneo", "fba", "neogeo"),
        folder_only=True,
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
        GameSystem.PSP,
        GameSystem.SATURN,
        GameSystem.ARCADE,
    }
)


def system_for_folder(folder: str) -> GameSystem | None:
    needle = folder.lower()
    for info in SYSTEMS.values():
        if needle == info.id.value or needle in info.folder_aliases:
            return info.id
    return None


def systems_for_extension(extension: str, *, include_folder_only: bool = False) -> list[GameSystem]:
    ext = extension.lower()
    return [
        info.id
        for info in SYSTEMS.values()
        if ext in info.extensions and (include_folder_only or not info.folder_only)
    ]


def is_extension_valid_for(system: GameSystem, extension: str) -> bool:
    return extension.lower() in SYSTEMS[system].extensions


# Files that describe other files rather than containing game data themselves,
# in the order the scanner reads them: a playlist (.m3u) names cue sheets,
# a cue sheet names its tracks.
CONTAINER_ORDER: tuple[str, ...] = (".m3u", ".cue")
CONTAINER_EXTENSIONS: frozenset[str] = frozenset(CONTAINER_ORDER)


def all_extensions() -> frozenset[str]:
    return frozenset(ext for info in SYSTEMS.values() for ext in info.extensions)
