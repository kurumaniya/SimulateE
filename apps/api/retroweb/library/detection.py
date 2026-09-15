"""System detection for a ROM file: folder name, extension, then header bytes."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from retroweb.library.filenames import split_extension
from retroweb.library.systems import (
    SYSTEMS,
    GameSystem,
    system_for_folder,
    systems_for_extension,
)

HEADER_BYTES = 0x200
CD_SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


@dataclass(frozen=True)
class Detection:
    system: GameSystem | None
    reason: str  # "folder" | "extension" | "header" | "unknown"


def _sniff_header(header: bytes, candidates: list[GameSystem]) -> GameSystem | None:
    """Confirm a candidate by well-known header signatures."""
    for system in candidates:
        if system is GameSystem.GBA and len(header) > 0xB2 and header[0xB2] == 0x96:
            # Fixed value byte in the GBA cartridge header.
            return system
        if system is GameSystem.NES and header[:4] == b"NES\x1a":
            return system
        if system is GameSystem.NDS and len(header) > 0x15E and header[0x15C:0x15E] == b"\x56\xcf":
            # Nintendo logo CRC in the DS header.
            return system
        if system is GameSystem.N64 and header[:4] in (
            b"\x80\x37\x12\x40",
            b"\x37\x80\x40\x12",
            b"\x40\x12\x37\x80",
        ):
            return system
        if system is GameSystem.GENESIS and header[0x100:0x104] in (b"SEGA", b" SEG"):
            return system
        if system is GameSystem.PS1 and header[:12] == CD_SYNC:
            # Raw 2352-byte CD sector: a disc image track, not a cartridge dump.
            return system
        if system in (GameSystem.PSP, GameSystem.PS1) and header[:4] == b"\0PBP":
            return _pbp_system(header)
    return None


def _pbp_system(header: bytes) -> GameSystem:
    """A PBP is a PSP package; PS1 classics converted for the PSP say so in
    PARAM.SFO (CATEGORY "ME"). Anything else is treated as PSP content."""
    return GameSystem.PS1 if _sfo_value(header, b"CATEGORY") == b"ME" else GameSystem.PSP


def _sfo_value(header: bytes, wanted: bytes) -> bytes | None:
    """Read one string entry of the PARAM.SFO embedded at the PBP's first offset."""
    try:
        (sfo_offset,) = struct.unpack_from("<I", header, 8)
        magic, _version, key_table, data_table, count = struct.unpack_from(
            "<IIIII", header, sfo_offset
        )
        if magic != 0x46535000:
            return None
        for i in range(count):
            key_offset, _fmt, length, _max_len, data_offset = struct.unpack_from(
                "<HHIII", header, sfo_offset + 20 + i * 16
            )
            key_start = sfo_offset + key_table + key_offset
            key_end = header.index(b"\0", key_start)
            if header[key_start:key_end] == wanted:
                start = sfo_offset + data_table + data_offset
                return header[start : start + length].rstrip(b"\0")
    except (struct.error, ValueError):
        return None
    return None


def detect_system(key: str, header: bytes) -> Detection:
    """Decide which system a ROM belongs to.

    Priority: the ``roms/<system>/`` folder is an explicit user statement, so it
    wins as long as the extension is plausible for that system. Otherwise a
    unique extension decides, and ambiguous extensions fall back to header
    sniffing.
    """
    parts = key.split("/")
    filename = parts[-1]
    _, extension = split_extension(filename)
    folder_system = None
    for folder in parts[:-1]:
        folder_system = system_for_folder(folder) or folder_system

    by_extension = systems_for_extension(extension) if extension else []

    if folder_system is not None:
        if extension in SYSTEMS[folder_system].extensions or not by_extension:
            return Detection(folder_system, "folder")

    if len(by_extension) == 1 and extension not in SYSTEMS[by_extension[0]].ambiguous_extensions:
        return Detection(by_extension[0], "extension")

    sniffed = _sniff_header(header, by_extension or list(SYSTEMS))
    if sniffed is not None:
        return Detection(sniffed, "header")
    if len(by_extension) == 1:
        return Detection(by_extension[0], "extension")
    return Detection(None, "unknown")
