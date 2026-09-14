#!/usr/bin/env python3
"""Generate a tiny homebrew GBA test ROM (no copyrighted content).

On every boot the program increments a counter stored in SRAM (0x0E000000)
and fills the screen with a colour derived from that counter. It exists so the
scan → play → save → resume pipeline can be verified end-to-end without any
commercial game:

    python scripts/make-test-rom.py data/roms/gba/RetroWeb Test (World).gba

The ROM embeds the "SRAM_V113" marker mGBA uses to pick the SRAM save type,
so the emulator produces a 32 KiB .sav whose first byte is the boot counter.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROM_SIZE = 64 * 1024
ENTRY_OFFSET = 0xC0

# Hand-assembled ARM7TDMI code (little-endian words); see comments.
CODE = [
    0xE3A00404,  # mov r0, #0x04000000      ; I/O base
    0xE3A01C04,  # mov r1, #0x400           ; BG2 enable
    0xE3811003,  # orr r1, r1, #3           ; video mode 3
    0xE1C010B0,  # strh r1, [r0]            ; REG_DISPCNT
    0xE3A0240E,  # mov r2, #0x0E000000      ; SRAM base
    0xE5D23000,  # ldrb r3, [r2]            ; counter = SRAM[0]
    0xE35300FF,  # cmp r3, #0xFF            ; fresh SRAM reads as 0xFF
    0x03A03000,  # moveq r3, #0             ; ...treat it as 0
    0xE2833001,  # add r3, r3, #1
    0xE5C23000,  # strb r3, [r2]            ; SRAM[0] = counter + 1
    0xE3A04406,  # mov r4, #0x06000000      ; VRAM
    0xE3A05B4B,  # mov r5, #0x12C00         ; 240*160*2 bytes
    0xE203601F,  # and r6, r3, #0x1F
    0xE1A06286,  # mov r6, r6, lsl #5       ; green = counter
    0xE386601F,  # orr r6, r6, #0x1F        ; red = max
    0xE1866806,  # orr r6, r6, r6, lsl #16  ; two pixels per word
    0xE4846004,  # loop: str r6, [r4], #4
    0xE2555004,  # subs r5, r5, #4
    0x1AFFFFFC,  # bne loop
    0xEAFFFFFE,  # halt: b halt
]


def build() -> bytes:
    rom = bytearray(ROM_SIZE)
    struct.pack_into("<I", rom, 0x00, 0xEA00002E)  # b entry (0xC0)
    rom[0xA0:0xAC] = b"RETROWEBTEST"  # game title
    rom[0xAC:0xB0] = b"RWTE"  # game code
    rom[0xB0:0xB2] = b"00"  # maker code
    rom[0xB2] = 0x96  # fixed value
    rom[0xBC] = 0x00  # software version
    checksum = 0
    for i in range(0xA0, 0xBD):
        checksum -= rom[i]
    rom[0xBD] = (checksum - 0x19) & 0xFF  # header complement
    for index, word in enumerate(CODE):
        struct.pack_into("<I", rom, ENTRY_OFFSET + index * 4, word)
    marker = b"SRAM_V113\0\0\0"
    rom[0x200 : 0x200 + len(marker)] = marker
    return bytes(rom)


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/roms/gba/RetroWeb Test (World).gba")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build())
    print(f"wrote {target} ({ROM_SIZE} bytes)")


if __name__ == "__main__":
    main()
