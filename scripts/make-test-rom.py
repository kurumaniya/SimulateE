#!/usr/bin/env python3
"""Generate tiny homebrew test ROMs (no copyrighted content) for every system
RetroWeb can currently play.

Each program does the same thing on boot: bump a counter stored in the
cartridge's battery-backed RAM and paint the screen with a colour derived
from it. That lets the scan → play → save → resume pipeline be verified end
to end (e2e/play-flow.spec.ts) without any commercial game.

    python scripts/make-test-rom.py            # all systems into data/roms/<system>/
    python scripts/make-test-rom.py gba nes    # a subset

Where the counter lives in the battery save file (index into the .sav/.srm):

    gba      byte 0      (fresh SRAM reads 0xFF, treated as 0)
    gb/gbc   byte 0      (magic "RWEB" at bytes 1-4 marks initialised RAM)
    nes      byte 0      (magic at 1-4)
    snes     byte 0      (magic at 1-4)
    genesis  byte 1      (odd-byte SRAM; magic at 3,5,7,9)

The 6502/65816 programs were assembled with ca65 (sources in the docstrings
below); the ARM, SM83 and 68000 programs are hand-assembled and verified with
Unicorn/PyBoy in scripts/verify-test-roms.py.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Game Boy Advance (ARM7TDMI). Fresh SRAM is 0xFF, which is treated as 0.
# ---------------------------------------------------------------------------
GBA_CODE = [
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


def build_gba() -> bytes:
    rom = bytearray(64 * 1024)
    struct.pack_into("<I", rom, 0x00, 0xEA00002E)  # b 0xC0
    rom[0xA0:0xAC] = b"RETROWEBTEST"
    rom[0xAC:0xB0] = b"RWTE"
    rom[0xB0:0xB2] = b"00"
    rom[0xB2] = 0x96
    checksum = 0
    for i in range(0xA0, 0xBD):
        checksum -= rom[i]
    rom[0xBD] = (checksum - 0x19) & 0xFF
    for index, word in enumerate(GBA_CODE):
        struct.pack_into("<I", rom, 0xC0 + index * 4, word)
    rom[0x200:0x20C] = b"SRAM_V113\0\0\0"  # mGBA save-type marker
    return bytes(rom)


# ---------------------------------------------------------------------------
# Game Boy / Game Boy Color (SM83). MBC1 + 8 KiB RAM + battery.
# ---------------------------------------------------------------------------
GB_CODE = bytes.fromhex(
    "F3"  # di
    "31FEFF"  # ld sp, $FFFE
    "3E0A"  # ld a, $0A
    "EA0000"  # ld ($0000), a         ; enable cart RAM
    "FA01A0"  # ld a, ($A001)
    "FE52"  # cp 'R'
    "2019"  # jr nz, fresh (+25)
    "FA02A0"  # ld a, ($A002)
    "FE57"  # cp 'W'
    "2012"  # jr nz, fresh (+18)
    "FA03A0"  # ld a, ($A003)
    "FE45"  # cp 'E'
    "200B"  # jr nz, fresh (+11)
    "FA04A0"  # ld a, ($A004)
    "FE42"  # cp 'B'
    "2004"  # jr nz, fresh (+4)
    "FA00A0"  # ld a, ($A000)         ; counter
    "1815"  # jr bump (+21)
    # fresh:
    "3E52"  # ld a, 'R'
    "EA01A0"  # ld ($A001), a
    "3E57"  # ld a, 'W'
    "EA02A0"  # ld ($A002), a
    "3E45"  # ld a, 'E'
    "EA03A0"  # ld ($A003), a
    "3E42"  # ld a, 'B'
    "EA04A0"  # ld ($A004), a
    "AF"  # xor a                 ; counter = 0
    # bump:
    "3C"  # inc a
    "EA00A0"  # ld ($A000), a
    "47"  # ld b, a
    "E603"  # and 3
    "E047"  # ldh ($FF47), a        ; DMG palette: colour 0 = counter & 3
    "3E80"  # ld a, $80
    "E068"  # ldh ($FF68), a        ; CGB: BCPS auto-increment, index 0
    "78"  # ld a, b
    "E069"  # ldh ($FF69), a        ; BCPD low byte
    "3E03"  # ld a, $03
    "E069"  # ldh ($FF69), a        ; BCPD high byte
    "3E91"  # ld a, $91
    "E040"  # ldh ($FF40), a        ; LCD on, BG on
    "18FE"  # loop: jr loop
)


def build_gb(color: bool) -> bytes:
    rom = bytearray(32 * 1024)
    rom[0x100:0x104] = bytes.fromhex("00C35001")  # nop; jp $150
    title = b"RWEBTESTGBC" if color else b"RWEBTESTGB"
    rom[0x134 : 0x134 + len(title)] = title
    rom[0x143] = 0x80 if color else 0x00  # CGB compatible flag
    rom[0x147] = 0x03  # MBC1 + RAM + BATTERY
    rom[0x148] = 0x00  # 32 KiB ROM
    rom[0x149] = 0x02  # 8 KiB RAM
    rom[0x14A] = 0x01  # non-Japanese
    checksum = 0
    for i in range(0x134, 0x14D):
        checksum = (checksum - rom[i] - 1) & 0xFF
    rom[0x14D] = checksum
    rom[0x150 : 0x150 + len(GB_CODE)] = GB_CODE
    return bytes(rom)


# ---------------------------------------------------------------------------
# NES (6502, NROM-128, battery). Assembled with ca65 from:
#
#   .org $C000
#   reset: sei; cld; ldx #$FF; txs; lda #0; sta $2000; sta $2001
#          bit $2002; w1: bit $2002; bpl w1; w2: bit $2002; bpl w2
#          ; magic "RWEB" at $6001..$6004 else initialise counter to 0
#          ...; bump: inc $6000
#          lda #$3F; sta $2006; lda #0; sta $2006; lda $6000; and #$3F; sta $2007
#          lda #0; sta $2006; sta $2006; lda #$0A; sta $2001; loop: jmp loop
#   nmi:   rti
# ---------------------------------------------------------------------------
NES_CODE = bytes.fromhex(
    "78d8a2ff9aa9008d00208d01202c02202c022010fb2c022010fbad0160c952d015ad0260"
    "c957d00ead0360c945d007ad0460c942f019a9008d0060a9528d0160a9578d0260a9458d"
    "0360a9428d0460ee0060a93f8d0620a9008d0620ad0060293f8d0720a9008d06208d0620"
    "a90a8d01204c71c040"
)
NES_RESET = 0xC000
NES_NMI = 0xC074


def build_nes() -> bytes:
    prg = bytearray(16 * 1024)
    prg[: len(NES_CODE)] = NES_CODE
    struct.pack_into("<HHH", prg, 0x3FFA, NES_NMI, NES_RESET, NES_NMI)
    header = bytearray(16)
    header[0:4] = b"NES\x1a"
    header[4] = 1  # 16 KiB PRG
    header[5] = 1  # 8 KiB CHR
    header[6] = 0x02  # battery-backed PRG RAM, mapper 0
    chr_rom = bytes(8 * 1024)
    return bytes(header) + bytes(prg) + chr_rom


# ---------------------------------------------------------------------------
# SNES (65816, LoROM, SRAM + battery). Assembled with ca65 --cpu 65816 from:
#
#   .org $8000
#   reset: sei; clc; xce; sep #$30; ldx #$FF; txs; lda #$80; sta $2100
#          ; magic "RWEB" at $70:0001..0004 else initialise counter to 0
#          bump: lda $700000; inc a; sta $700000
#          stz $2121; lda #$1F; sta $2122; lda $700000; and #$7F; sta $2122
#          lda #$0F; sta $2100; loop: bra loop
#   nmi:   rti
# ---------------------------------------------------------------------------
SNES_CODE = bytes.fromhex(
    "7818fbe230a2ff9aa9808d0021af010070c952d018af020070c957d010af030070c945d0"
    "08af040070c942f01ea9008f000070a9528f010070a9578f020070a9458f030070a9428f"
    "040070af0000701a8f0000709c2121a91f8d2221af000070297f8d2221a90f8d002180fe40"
)
SNES_RESET = 0x8000
SNES_NMI = 0x806C


def build_snes() -> bytes:
    rom = bytearray(32 * 1024)
    rom[: len(SNES_CODE)] = SNES_CODE
    header = 0x7FC0
    rom[header : header + 21] = b"RETROWEB TEST".ljust(21)
    rom[header + 0x15] = 0x20  # LoROM, slow
    rom[header + 0x16] = 0x02  # ROM + RAM + battery
    rom[header + 0x17] = 0x05  # 32 KiB ROM
    rom[header + 0x18] = 0x03  # 8 KiB SRAM
    rom[header + 0x19] = 0x01  # USA
    rom[header + 0x1A] = 0x33
    # Vectors (emulation mode): NMI at $FFFA, RESET at $FFFC, IRQ at $FFFE.
    struct.pack_into("<HHH", rom, 0x7FFA, SNES_NMI, SNES_RESET, SNES_NMI)
    struct.pack_into("<HH", rom, 0x7FEA, SNES_NMI, SNES_NMI)  # native NMI / IRQ
    checksum = sum(rom) & 0xFFFF
    struct.pack_into("<HH", rom, header + 0x1C, checksum ^ 0xFFFF, checksum)
    checksum = sum(rom) & 0xFFFF
    struct.pack_into("<HH", rom, header + 0x1C, checksum ^ 0xFFFF, checksum)
    return bytes(rom)


# ---------------------------------------------------------------------------
# Sega Genesis / Mega Drive (68000). SRAM on odd bytes at $200001-$203FFF.
# ---------------------------------------------------------------------------
GENESIS_CODE = bytes.fromhex(
    "1039 00A10001"  # move.b $A10001, d0      ; hardware version
    "0200 000F"  # andi.b #$0F, d0
    "670A"  # beq.s +10               ; no TMSS on version 0
    "23FC 53454741 00A14000"  # move.l #'SEGA', $A14000
    "1239 00200003"  # move.b $200003, d1      ; magic "RWEB" at odd bytes 3,5,7,9
    "0C01 0052"  # cmpi.b #'R', d1
    "662C"  # bne.s fresh (+44)
    "1239 00200005"  # move.b $200005, d1
    "0C01 0057"  # cmpi.b #'W', d1
    "6620"  # bne.s fresh (+32)
    "1239 00200007"  # move.b $200007, d1
    "0C01 0045"  # cmpi.b #'E', d1
    "6614"  # bne.s fresh (+20)
    "1239 00200009"  # move.b $200009, d1
    "0C01 0042"  # cmpi.b #'B', d1
    "6608"  # bne.s fresh (+8)
    "1239 00200001"  # move.b $200001, d1      ; counter
    "6022"  # bra.s bump (+34)
    # fresh:
    "13FC 0052 00200003"  # move.b #'R', $200003
    "13FC 0057 00200005"  # move.b #'W', $200005
    "13FC 0045 00200007"  # move.b #'E', $200007
    "13FC 0042 00200009"  # move.b #'B', $200009
    "7200"  # moveq #0, d1
    # bump:
    "5201"  # addq.b #1, d1
    "13C1 00200001"  # move.b d1, $200001
    "33FC 8004 00C00004"  # VDP reg 0
    "33FC 8144 00C00004"  # VDP reg 1: display on
    "33FC 8700 00C00004"  # VDP reg 7: backdrop = palette 0 colour 0
    "23FC C0000000 00C00004"  # CRAM write address 0
    "1401"  # move.b d1, d2
    "0242 0007"  # andi.w #7, d2
    "EB4A"  # lsl.w #5, d2            ; green = counter
    "0042 000E"  # ori.w #$E, d2           ; red = max
    "33C2 00C00000"  # move.w d2, $C00000
    "60FE"  # loop: bra.s loop
    "4E73"  # rte (all other vectors)
)
GENESIS_ENTRY = 0x200


def build_genesis() -> bytes:
    rom = bytearray(64 * 1024)
    rte = GENESIS_ENTRY + len(GENESIS_CODE) - 2
    struct.pack_into(">II", rom, 0, 0x00FFFE00, GENESIS_ENTRY)  # SP, PC
    for vector in range(2, 64):
        struct.pack_into(">I", rom, vector * 4, rte)
    rom[0x100:0x110] = b"SEGA MEGA DRIVE "
    rom[0x110:0x120] = b"(C)RWEB 2026.SEP"
    rom[0x120:0x150] = b"RETROWEB TEST".ljust(48)
    rom[0x150:0x180] = b"RETROWEB TEST".ljust(48)
    rom[0x180:0x18E] = b"GM 00000000-00"
    rom[0x190:0x1A0] = b"J".ljust(16)
    struct.pack_into(">II", rom, 0x1A0, 0, len(rom) - 1)  # ROM range
    struct.pack_into(">II", rom, 0x1A8, 0x00FF0000, 0x00FFFFFF)  # RAM range
    rom[0x1B0:0x1B2] = b"RA"
    rom[0x1B2] = 0xF8  # backup RAM, odd bytes
    rom[0x1B3] = 0x20
    struct.pack_into(">II", rom, 0x1B4, 0x00200001, 0x00203FFF)
    rom[0x1F0:0x1F3] = b"JUE"
    rom[GENESIS_ENTRY : GENESIS_ENTRY + len(GENESIS_CODE)] = GENESIS_CODE
    checksum = sum(struct.unpack(f">{(len(rom) - 0x200) // 2}H", rom[0x200:])) & 0xFFFF
    struct.pack_into(">H", rom, 0x18E, checksum)
    return bytes(rom)


BUILDERS = {
    "gba": ("RetroWeb Test (World).gba", build_gba),
    "gb": ("RetroWeb Test (World).gb", lambda: build_gb(color=False)),
    "gbc": ("RetroWeb Test (World).gbc", lambda: build_gb(color=True)),
    "nes": ("RetroWeb Test (World).nes", build_nes),
    "snes": ("RetroWeb Test (World).sfc", build_snes),
    "genesis": ("RetroWeb Test (World).md", build_genesis),
}


def main() -> None:
    systems = sys.argv[1:] or list(BUILDERS)
    root = Path("data/roms")
    for system in systems:
        filename, builder = BUILDERS[system]
        target = root / system / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        data = builder()
        target.write_bytes(data)
        print(f"wrote {target} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
