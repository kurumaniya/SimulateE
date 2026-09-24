"""Fingerprint a ROM the way the No-Intro / Redump databases do.

The library's identity key stays the SHA-256 of the raw file. The digests
here exist only to look a game up in a public database, so they follow that
database's conventions instead:

* NES: the 16-byte iNES header is not part of the dump;
* SNES: a 512-byte copier header (``.smc``) is not part of the dump;
* Nintendo 64: dumps are big-endian (``.z64``); ``.v64`` and ``.n64`` files
  are byte-swapped back before hashing.

A *serial* is the product code stored inside the image (cartridge header or
disc file system). A translated or patched ROM no longer matches by digest,
but it almost always keeps its serial, which is enough to name the game.
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass

from retroweb.library.systems import GameSystem

# How much of the image is kept for serial extraction. Cartridge headers sit in
# the first kilobyte; a disc's SYSTEM.CNF / UMD_DATA.BIN sits in its first
# few megabytes.
CARTRIDGE_PROBE_BYTES = 0x1000
DISC_PROBE_BYTES = 8 * 1024 * 1024

_N64_BYTE_SWAPPED = b"\x37\x80\x40\x12"  # .v64
_N64_LITTLE_ENDIAN = b"\x40\x12\x37\x80"  # .n64

_GAME_CODE = re.compile(rb"^[A-Z0-9]{4}$")
# "BOOT = cdrom:\SLUS_012.34;1" (also BOOT2 on later discs)
_PS1_BOOT = re.compile(rb"BOOT\d?\s*=\s*cdrom\d?:\\*([A-Z]{4})[_-](\d{3})\.(\d{2})", re.IGNORECASE)
# UMD_DATA.BIN: "ULUS-10041|0123456789ABCDEF|0001|G"
_PSP_DISC_ID = re.compile(rb"([A-Z]{4})-(\d{5})\|")
# Saturn system ID in the first sector: hardware id, maker id (16 bytes each),
# then the product number and version: "T-8106G   V1.000".
_SATURN_ID = re.compile(rb"SEGA SEGASATURN .{16}([A-Z0-9][A-Z0-9 -]{9})V\d", re.DOTALL)

_CSO_HEADER = 24
_SFO_MAGIC = b"\0PSF"
# DISC_ID in PARAM.SFO: "UCJS10041" (no dash)
_DISC_ID = re.compile(rb"^([A-Z]{4})(\d{5})$")

_CARTRIDGE_SERIAL_OFFSETS: dict[GameSystem, int] = {
    GameSystem.GBA: 0xAC,
    GameSystem.NDS: 0x0C,
    GameSystem.N64: 0x3B,
    GameSystem.GBC: 0x13F,
}
DISC_SYSTEMS: frozenset[GameSystem] = frozenset({GameSystem.PS1, GameSystem.PSP, GameSystem.SATURN})
# Disc images above this size are not hashed in full for identification: the
# serial in the first megabytes names them, and a second full read of a 1 GB
# image on network storage costs more than a digest match is worth.
FULL_HASH_LIMIT = 256 * 1024 * 1024


@dataclass(frozen=True)
class Fingerprint:
    crc32: str | None  # upper-case hex; None when only the head was probed
    sha1: str | None  # upper-case hex; None when only the head was probed
    size: int  # bytes that were hashed (after header removal)
    serial: str | None


def _n64_order(head: bytes) -> str:
    if head.startswith(_N64_BYTE_SWAPPED):
        return "v64"
    if head.startswith(_N64_LITTLE_ENDIAN):
        return "n64"
    return "z64"


def _swap(data: bytes, width: int) -> bytes:
    """Reverse every ``width``-byte group (``len(data)`` must be a multiple)."""
    out = bytearray(len(data))
    for offset in range(width):
        out[offset::width] = data[width - 1 - offset :: width]
    return bytes(out)


def _cartridge_serial(system: GameSystem, head: bytes) -> str | None:
    offset = _CARTRIDGE_SERIAL_OFFSETS.get(system)
    if offset is None or len(head) < offset + 4:
        return None
    code = head[offset : offset + 4]
    return code.decode("ascii") if _GAME_CODE.match(code) else None


def _cso_head(head: bytes) -> bytes:
    """The first sectors of a CSO/ZSO-compressed PSP image, decompressed.

    Only the blocks whose compressed bytes lie inside ``head`` are decoded; the
    UMD file system's UMD_DATA.BIN sits at the very start, which is all the
    serial lookup needs.
    """
    if len(head) < 24 or head[:4] != b"CISO":
        return head
    _magic, _header_size, total, block_size, _ver, align = struct.unpack_from("<4sIQIBB", head, 0)
    if block_size == 0 or total == 0:
        return head
    # The block index follows the fixed 24-byte header; the header_size field
    # is informational and many tools leave it at 0.
    count = min(total // block_size + 1, (len(head) - _CSO_HEADER) // 4)
    entries = struct.unpack_from(f"<{count}I", head, _CSO_HEADER)
    out = bytearray()
    for index in range(count - 1):
        start = (entries[index] & 0x7FFFFFFF) << align
        end = (entries[index + 1] & 0x7FFFFFFF) << align
        if end > len(head) or end <= start:
            break
        chunk = head[start:end]
        if entries[index] & 0x80000000:
            out += chunk  # stored as-is
        else:
            try:
                out += zlib.decompress(chunk, wbits=-15)
            except zlib.error:
                break
        if len(out) >= DISC_PROBE_BYTES:
            break
    return bytes(out)


def _sfo_value(sfo: bytes, wanted: bytes) -> bytes | None:
    """One string entry of a PARAM.SFO blob (``sfo`` starts at its magic)."""
    try:
        magic, _version, key_table, data_table, count = struct.unpack_from("<IIIII", sfo, 0)
        if magic != 0x46535000:
            return None
        for i in range(count):
            key_offset, _fmt, length, _max_len, data_offset = struct.unpack_from(
                "<HHIII", sfo, 20 + i * 16
            )
            key_start = key_table + key_offset
            key_end = sfo.index(b"\0", key_start)
            if sfo[key_start:key_end] == wanted:
                start = data_table + data_offset
                return sfo[start : start + length].rstrip(b"\0")
    except (struct.error, ValueError):
        return None
    return None


def _sfo_disc_id(head: bytes) -> str | None:
    """DISC_ID from any PARAM.SFO found in the head (PBP packages, discs without UMD_DATA.BIN)."""
    start = 0
    while True:
        at = head.find(_SFO_MAGIC, start)
        if at < 0:
            return None
        value = _sfo_value(head[at : at + 65536], b"DISC_ID")
        if value:
            match = _DISC_ID.match(value)
            if match:
                return f"{match.group(1).decode()}-{match.group(2).decode()}"
        start = at + 4


def _disc_serial(system: GameSystem, head: bytes) -> str | None:
    if system is GameSystem.PSP:
        head = _cso_head(head)
    if system is GameSystem.PS1:
        match = _PS1_BOOT.search(head)
        if match:
            prefix, major, minor = match.groups()
            return f"{prefix.decode().upper()}-{major.decode()}{minor.decode()}"
    if system is GameSystem.PSP:
        match = _PSP_DISC_ID.search(head)
        if match:
            return f"{match.group(1).decode()}-{match.group(2).decode()}"
        return _sfo_disc_id(head)
    if system is GameSystem.SATURN:
        match = _SATURN_ID.search(head)
        if match:
            return match.group(1).decode("ascii").strip() or None
    return None


def fingerprint(
    system: GameSystem, chunks: Iterable[bytes], total_size: int, *, probe_only: bool = False
) -> Fingerprint:
    """Database-style CRC32 / SHA-1 and the embedded serial of one image.

    With ``probe_only`` the digests are skipped and reading stops once the
    serial probe is full, so a large disc image costs a few megabytes.
    """
    is_disc = system in DISC_SYSTEMS
    probe_limit = DISC_PROBE_BYTES if is_disc else CARTRIDGE_PROBE_BYTES
    if probe_only:
        probe = bytearray()
        for chunk in chunks:
            probe.extend(chunk[: probe_limit - len(probe)])
            if len(probe) >= probe_limit:
                break
        head = bytes(probe)
        serial = _disc_serial(system, head) if is_disc else _cartridge_serial(system, head)
        return Fingerprint(crc32=None, sha1=None, size=total_size, serial=serial)

    sha1 = hashlib.sha1(usedforsecurity=False)
    crc = 0
    hashed = 0
    probe = bytearray()
    pending = b""  # not yet hashed: waiting for the header decision / alignment
    skip: int | None = None  # bytes still to drop from the front; None = undecided
    order = "z64"

    def feed(data: bytes) -> None:
        nonlocal crc, hashed
        if not data:
            return
        sha1.update(data)
        crc = zlib.crc32(data, crc)
        hashed += len(data)
        if len(probe) < probe_limit:
            probe.extend(data[: probe_limit - len(probe)])

    for chunk in chunks:
        pending += chunk
        if skip is None:
            if len(pending) < min(16, total_size):
                continue
            skip = 0
            if system is GameSystem.NES and pending.startswith(b"NES\x1a"):
                skip = 16
            elif system is GameSystem.SNES and total_size % 1024 == 512:
                skip = 512
            elif system is GameSystem.N64:
                order = _n64_order(pending)
        if skip:
            dropped = min(skip, len(pending))
            pending = pending[dropped:]
            skip -= dropped
            if skip:
                continue
        if system is GameSystem.N64 and order != "z64":
            usable = len(pending) - len(pending) % 4
            data, pending = pending[:usable], pending[usable:]
            feed(_swap(data, 2 if order == "v64" else 4))
        else:
            feed(pending)
            pending = b""
    feed(pending)  # an unaligned tail (damaged dump) is hashed as it is

    head = bytes(probe)
    serial = _disc_serial(system, head) if is_disc else _cartridge_serial(system, head)
    return Fingerprint(
        crc32=f"{crc & 0xFFFFFFFF:08X}",
        sha1=sha1.hexdigest().upper(),
        size=hashed,
        serial=serial,
    )
