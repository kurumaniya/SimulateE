"""Known BIOS files per system.

RetroWeb never downloads BIOS images. This registry only says which files a
system *can* use so the Settings page can show what is installed and uploads
can be validated by name (and by hash when a well-known digest exists).

Digests are MD5 because that is what the libretro core documentation and
No-Intro datasets publish; the value stored on disk is verified by SHA-256 as
well so the API can expose both.
"""

from __future__ import annotations

from dataclasses import dataclass

from retroweb.library.systems import GameSystem


@dataclass(frozen=True)
class BiosSpec:
    filename: str
    description: str
    # Known-good MD5 (lowercase hex). None when several revisions are accepted.
    md5: str | None = None
    # Whether the emulator needs *some* file of this group to run the system.
    required: bool = True


@dataclass(frozen=True)
class SystemBiosInfo:
    system: GameSystem
    # Human summary shown in Settings.
    note: str
    files: tuple[BiosSpec, ...]
    # True when the core can run without any of the files (HLE fallback).
    optional: bool


# Digests from the PCSX-ReARMed / libretro documentation.
BIOS_REGISTRY: dict[GameSystem, SystemBiosInfo] = {
    GameSystem.PS1: SystemBiosInfo(
        system=GameSystem.PS1,
        note=(
            "PCSX-ReARMed uses one PlayStation BIOS image. Without one it falls back to a "
            "high-level BIOS emulation that runs many games but not all."
        ),
        optional=True,
        files=(
            BiosSpec("scph5501.bin", "SCPH-5501 (USA)", "490f666e1afb15b7362b406ed1cea246"),
            BiosSpec("scph5500.bin", "SCPH-5500 (Japan)", "8dd7d5296a650fac7319bce665a6a53c"),
            BiosSpec("scph5502.bin", "SCPH-5502 (Europe)", "32736f17079d0b2b7024407c39bd3050"),
            BiosSpec("scph1001.bin", "SCPH-1001 (USA)", "924e392ed05558ffdb115408c263dccf"),
            BiosSpec("scph7001.bin", "SCPH-7001 (USA)", "1e68c231d0896b7eadcad1d7d8e76129"),
            BiosSpec("scph7003.bin", "SCPH-7003 (USA)", "1e68c231d0896b7eadcad1d7d8e76129"),
            BiosSpec(
                "psxonpsp660.bin", "PSP built-in PS1 BIOS", "c53ca5908936d412331790f4426c6c33"
            ),
        ),
    ),
    GameSystem.GB: SystemBiosInfo(
        system=GameSystem.GB,
        note="Optional Game Boy boot ROM: shows the scrolling logo on start-up.",
        optional=True,
        files=(BiosSpec("gb_bios.bin", "Game Boy boot ROM", "32fbbd84168d3482956eb3c5051637f5"),),
    ),
    GameSystem.GBC: SystemBiosInfo(
        system=GameSystem.GBC,
        note="Optional Game Boy Color boot ROM: shows the start-up logo animation.",
        optional=True,
        files=(
            BiosSpec("gbc_bios.bin", "Game Boy Color boot ROM", "dbfce9db9deaa2567f6a84fde55f9680"),
        ),
    ),
    GameSystem.NDS: SystemBiosInfo(
        system=GameSystem.NDS,
        note=(
            "melonDS boots games directly with its built-in FreeBIOS when nothing is installed. "
            "Upload all three original files (ARM7 BIOS, ARM9 BIOS, firmware) for full "
            "compatibility; the DS firmware menu itself is not exposed."
        ),
        optional=True,
        # No digests: several firmware revisions exist and RetroWeb only
        # records checksums it can cite.
        files=(
            BiosSpec("bios7.bin", "Nintendo DS ARM7 BIOS (16 KiB)", None),
            BiosSpec("bios9.bin", "Nintendo DS ARM9 BIOS (4 KiB)", None),
            BiosSpec("firmware.bin", "Nintendo DS firmware (256 KiB)", None),
        ),
    ),
    GameSystem.NES: SystemBiosInfo(
        system=GameSystem.NES,
        note="Only Famicom Disk System (.fds) images need it; cartridge games run without.",
        optional=True,
        files=(
            BiosSpec("disksys.rom", "Famicom Disk System BIOS", "ca30b50f880eb660a320674ed365ef7a"),
        ),
    ),
}

MAX_BIOS_BYTES = 8 * 1024 * 1024


def bios_info(system: GameSystem) -> SystemBiosInfo | None:
    return BIOS_REGISTRY.get(system)


def bios_spec(system: GameSystem, filename: str) -> BiosSpec | None:
    info = BIOS_REGISTRY.get(system)
    if info is None:
        return None
    wanted = filename.lower()
    for spec in info.files:
        if spec.filename == wanted:
            return spec
    return None


def spec_for_md5(system: GameSystem, md5: str) -> BiosSpec | None:
    info = BIOS_REGISTRY.get(system)
    if info is None:
        return None
    for spec in info.files:
        if spec.md5 and spec.md5 == md5.lower():
            return spec
    return None


def bios_storage_key(system: GameSystem, filename: str) -> str:
    return f"bios/{system.value}/{filename}"
