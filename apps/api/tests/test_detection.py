from __future__ import annotations

from retroweb.library.detection import Detection, detect_system
from retroweb.library.systems import GameSystem
from tests.conftest import make_gba_rom


def test_folder_name_wins() -> None:
    assert detect_system("roms/gba/game.gba", b"").system is GameSystem.GBA
    assert detect_system("roms/gba/game.gba", b"").reason == "folder"


def test_folder_alias() -> None:
    assert detect_system("roms/famicom/game.nes", b"").system is GameSystem.NES


def test_unique_extension_without_folder() -> None:
    detection = detect_system("roms/misc/game.nds", b"")
    assert detection.system is GameSystem.NDS
    assert detection.reason == "extension"


def test_header_sniff_gba() -> None:
    detection = detect_system("roms/unsorted/mystery.gba", make_gba_rom())
    assert detection.system is GameSystem.GBA


def test_ambiguous_bin_uses_header() -> None:
    header = bytearray(0x200)
    header[0x100:0x104] = b"SEGA"
    detection = detect_system("roms/unsorted/game.bin", bytes(header))
    assert detection.system is GameSystem.GENESIS
    assert detection.reason == "header"


def test_ambiguous_bin_unknown_without_header() -> None:
    assert detect_system("roms/unsorted/game.bin", bytes(0x200)).system is None


def test_folder_does_not_override_impossible_extension() -> None:
    # A .nds file in the gba folder is clearly not a GBA ROM.
    assert detect_system("roms/gba/game.nds", b"").system is GameSystem.NDS


def _pbp(category: bytes) -> bytes:
    """Minimal PBP: header, then a PARAM.SFO with one CATEGORY entry."""
    import struct

    key_table = b"CATEGORY\0\0\0\0"
    data = category.ljust(4, b"\0")
    index = struct.pack("<HHIII", 0, 0x0204, 3, 4, 0)
    sfo = (
        struct.pack("<IIIII", 0x46535000, 0x101, 36, 36 + len(key_table), 1)
        + index
        + key_table
        + data
    )
    offsets = [0x28] + [0x28 + len(sfo)] * 7
    return b"\0PBP" + struct.pack("<I", 0x10000) + struct.pack("<8I", *offsets) + sfo


def test_pbp_category_separates_psp_from_ps1_classics() -> None:
    assert detect_system("roms/EBOOT.PBP", _pbp(b"MG")) == Detection(GameSystem.PSP, "header")
    assert detect_system("roms/EBOOT.PBP", _pbp(b"ME")) == Detection(GameSystem.PS1, "header")
    # Unreadable SFO: still a PSP package.
    assert detect_system("roms/x.pbp", b"\0PBP" + b"\0" * 60).system is GameSystem.PSP
