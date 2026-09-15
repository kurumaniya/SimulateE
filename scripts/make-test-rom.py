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
    ps1      (no in-game write: the program only paints the screen; the e2e
              test injects bytes into the memory card and checks they survive)
    n64      (same: paints the screen; save round-trip checked by injection)
    nds      byte 0      (EEPROM; magic "RWEB" at bytes 4-7; each touch of the
              bottom screen is logged at 0x10 as 'T', touch number, x, y)

The 6502/65816 programs were assembled with ca65 (sources in the docstrings
below); the ARM, SM83 and 68000 programs are hand-assembled and verified with
Unicorn/PyBoy in scripts/verify-test-roms.py. The PS1 and N64 programs are C
compiled with mipsel-/mips-linux-gnu-gcc (sources in scripts/test-programs/).
The N64 ROM boots through a 64-byte emulator-only IPL3 stub (ipl3.S); the
libdragon IPL3 was tried first but its RDRAM detection crashes on the
Mupen64Plus build EmulatorJS ships. The NDS ROM (ARM9 + ARM7 programs in
scripts/test-programs/nds9.c and nds7.c, built with clang) relies on the
emulator's direct boot: it carries no Nintendo logo or secure area.
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


# ---------------------------------------------------------------------------
# PlayStation: a MODE2/2352 disc image (ISO9660) holding SYSTEM.CNF and a
# PS-X EXE built from scripts/test-programs/ps1.c, plus its cue sheet.
# ---------------------------------------------------------------------------
PS1_PROGRAM = bytes.fromhex(
    "801f023c141840ac0008033c01006324141843acc606033c60026324141843ac0407033c"
    "10006324141843ac0005033c141843ac00e1033c101843ac00e3033c101843ac03e4033c"
    "3fbd6334101843ac00e5033c101843ac0002033c40ff6334101843ac101840acf000033c"
    "40016324101843ac0003033c141843acffff001000000000000000000000000000000000"
)
PS1_LOAD_ADDRESS = 0x80010000
CD_SECTOR = 2048


def _both_endian32(value: int) -> bytes:
    return struct.pack("<I", value) + struct.pack(">I", value)


def _both_endian16(value: int) -> bytes:
    return struct.pack("<H", value) + struct.pack(">H", value)


def _iso_dir_record(name: bytes, lba: int, size: int, flags: int) -> bytes:
    rec = bytearray(b"\0\0")
    rec += _both_endian32(lba) + _both_endian32(size)
    rec += bytes([126, 1, 1, 0, 0, 0, 0])  # recording date 2026-01-01
    rec += bytes([flags, 0, 0]) + _both_endian16(1)
    rec += bytes([len(name)]) + name
    if len(rec) % 2:
        rec += b"\0"
    rec[0] = len(rec)
    return bytes(rec)


def _psx_exe(program: bytes) -> bytes:
    header = bytearray(CD_SECTOR)
    header[0:8] = b"PS-X EXE"
    text_size = (len(program) + CD_SECTOR - 1) // CD_SECTOR * CD_SECTOR
    struct.pack_into("<I", header, 0x10, PS1_LOAD_ADDRESS)  # initial PC
    struct.pack_into("<I", header, 0x18, PS1_LOAD_ADDRESS)  # text address
    struct.pack_into("<I", header, 0x1C, text_size)
    struct.pack_into("<I", header, 0x30, 0x801FFFF0)  # initial SP
    header[0x4C:0x4C + 32] = b"RetroWeb homebrew test program  "
    return bytes(header) + program.ljust(text_size, b"\0")


def build_ps1_disc() -> bytes:
    exe = _psx_exe(PS1_PROGRAM)
    cnf = b"BOOT = cdrom:\\MAIN.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFFF0\r\n"
    root_lba, cnf_lba, exe_lba = 20, 21, 22
    total = exe_lba + len(exe) // CD_SECTOR + 1
    root = (
        _iso_dir_record(b"\0", root_lba, CD_SECTOR, 2)
        + _iso_dir_record(b"\1", root_lba, CD_SECTOR, 2)
        + _iso_dir_record(b"MAIN.EXE;1", exe_lba, len(exe), 0)
        + _iso_dir_record(b"SYSTEM.CNF;1", cnf_lba, len(cnf), 0)
    )
    pvd = bytearray(CD_SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[8:40] = b"PLAYSTATION".ljust(32)
    pvd[40:72] = b"RETROWEB".ljust(32)
    pvd[80:88] = _both_endian32(total)
    pvd[120:124] = _both_endian16(1)
    pvd[124:128] = _both_endian16(1)
    pvd[128:132] = _both_endian16(CD_SECTOR)
    pvd[132:140] = _both_endian32(10)
    struct.pack_into("<I", pvd, 140, 18)
    struct.pack_into(">I", pvd, 148, 19)
    root_record = _iso_dir_record(b"\0", root_lba, CD_SECTOR, 2)
    pvd[156 : 156 + len(root_record)] = root_record
    pvd[190:318] = b"RETROWEB".ljust(128)
    path_l = bytes([1, 0]) + struct.pack("<I", root_lba) + struct.pack("<H", 1) + b"\0\0"
    path_m = bytes([1, 0]) + struct.pack(">I", root_lba) + struct.pack(">H", 1) + b"\0\0"
    terminator = bytes([255]) + b"CD001" + bytes([1])
    sectors: dict[int, bytes] = {
        16: bytes(pvd),
        17: terminator,
        18: path_l,
        19: path_m,
        root_lba: root,
        cnf_lba: cnf,
    }
    for offset in range(0, len(exe), CD_SECTOR):
        sectors[exe_lba + offset // CD_SECTOR] = exe[offset : offset + CD_SECTOR]

    def bcd(value: int) -> int:
        return ((value // 10) << 4) | (value % 10)

    image = bytearray()
    for lba in range(total):
        data = sectors.get(lba, b"").ljust(CD_SECTOR, b"\0")
        frames = lba + 150  # two-second pregap
        msf = bytes([bcd(frames // 4500), bcd((frames // 75) % 60), bcd(frames % 75), 2])
        subheader = bytes([0, 0, 8, 0, 0, 0, 8, 0])  # mode 2 form 1, data
        # EDC/ECC left zero: emulators do not verify them.
        image += b"\x00" + b"\xff" * 10 + b"\x00" + msf + subheader + data + bytes(280)
    return bytes(image)


def build_ps1_cue(bin_name: str) -> bytes:
    return f'FILE "{bin_name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'.encode()


# ---------------------------------------------------------------------------
# Nintendo 64. The cartridge boot code (IPL3) is a 64-byte emulator-only stub
# assembled from scripts/test-programs/ipl3.S: it copies the program from ROM
# offset 0x1000 to RDRAM 0x80000400 and jumps there. It relies on the
# emulator's HLE PIF boot (no RDRAM init, no CIC), so it is not a real
# console boot loader. Program built from scripts/test-programs/n64.c.
# ---------------------------------------------------------------------------
N64_IPL3_STUB = bytes.fromhex(
    "3c08b000350810003c09a00035290400240a10008d0b0000ad2b00002508000425290004254affff1540fffa000000003c0c8000358c04000180000800000000"
)
N64_PROGRAM = bytes.fromhex(
    "3c02a010240407c13c03a01224635800a4440000244200021443fffd000000003c02a013"
    "240407c13c03a01524635800a4440000244200021443fffd000000003c02a4403c030010"
    "ac43000424030140ac43000824030002ac43000c3c0303e524632239ac4300142403020d"
    "ac43001824030c15ac43001c3c030c1524630c15ac4300203c03006c246302ecac430024"
    "3c030025246301ffac4300283c03000e24630204ac43002c24030200ac43003024030400"
    "ac43003424033202ac4300008c430010000028253c04a4402406fffe240700013c090010"
    "100000053c08001301202825ac85000400602825004018258c820010004610240043182b"
    "5060fffc0040182510a7fff638a300011000fff501002825000000000000000000000000"
)
N64_ENTRY = 0x80000400


def build_n64() -> bytes:
    rom = bytearray(1024 * 1024)
    # PI BSD config, clock rate, entry point, release; CRCs left zero (HLE boot).
    struct.pack_into(">IIII", rom, 0, 0x80371240, 0x0000000F, N64_ENTRY, 0x00001444)
    rom[0x40 : 0x40 + len(N64_IPL3_STUB)] = N64_IPL3_STUB
    rom[0x20:0x34] = b"RETROWEB TEST".ljust(20)
    rom[0x3B:0x3F] = b"NRWE"  # media 'N', id 'RW', region 'E'
    rom[0x1000 : 0x1000 + len(N64_PROGRAM)] = N64_PROGRAM
    return bytes(rom)


# ---------------------------------------------------------------------------
# Nintendo DS (ARM946E-S + ARM7TDMI). Direct boot only; EEPROM 64 kbit save.
# Sources: scripts/test-programs/nds9.c and nds7.c.
# ---------------------------------------------------------------------------
NDS9_PROGRAM = bytes.fromhex(
    "0cd04de21a0ea0e3010380e30f10a0e3821c81e3641180e50113a0e30128a0e3002081e5"
    "602e80e5f0129fe5b010c0e10310a0e3b210c0e181ada0e302a98ae3b020d0e1800012e3"
    "fcffff1ab220d0e1b0a0c0e10020a0e3b220c0e1b020d0e1800012e3fcffff1ab220d0e1"
    "b0a0c0e10020a0e3b220c0e1b020d0e1800012e3fcffff1ab220d0e10070a0e390229fe5"
    "04308de20060a0e3070056e30a10a0e10210a001b010c0e1b270c0e1b010d0e1800011e3"
    "fcffff1ab210d0e10610c3e7016086e2080056e3f2ffff1a0a1aa0e3b010c0e10610a0e3"
    "b210c0e10b10dde54270a0e30b70cde50470dde508c0dde50950dde50a40dde54560a0e3"
    "0a60cde55760a0e30960cde55260a0e30860cde50060a0e30760cde50660cde50560cde5"
    "016087e201e0a0e3420051e30170a0e3ff700602450054e30e70a011571025e252602ce2"
    "011096e10e70a0110470cde5b010d0e1800011e3fcffff1ab210d0e1b0a0c0e10210a0e3"
    "b210c0e1b010d0e1800011e3fcffff1ab210d0e1b0a0c0e10010a0e3b210c0e1b010d0e1"
    "800011e3fcffff1ab210d0e1b0a0c0e10010a0e3b210c0e1b010d0e1800011e3fcffff1a"
    "b210d0e10060a0e3070056e30a10a0e10210a001b010c0e10610d3e7b210c0e1b010d0e1"
    "800011e3fcffff1ab210d0e1016086e2080056e3f2ffff1a1f1ba0e3871281e10534a0e3"
    "b010c3e101eba0e305e48ee31010a0e3b010cee12336a0e30010a0e3001083e50c50a0e3"
    "235685e3001085e50290a0e30d70a0e10040a0e3040000ea001095e5000051e33e1ea0e3"
    "1010a003b010cee100c093e504005ce1f7ffff0a084015e5041015e50a6aa0e3b060c0e1"
    "0660a0e3b260c0e101c0cde55460a0e30060cde50240cde50310cde5b010d0e1800011e3"
    "fcffff1ab210d0e1b0a0c0e1b290c0e1b010d0e1800011e3fcffff1ab210d0e1b0a0c0e1"
    "0010a0e3b210c0e1b010d0e1800011e3fcffff1ab210d0e1b0a0c0e11010a0e3b210c0e1"
    "b010d0e1800011e3fcffff1ab210d0e10080a0e3030058e30a10a0e10210a001b010c0e1"
    "0810d7e7b210c0e1b010d0e1800011e3fcffff1ab210d0e1018088e2040058e3f2ffff1a"
    "0c40a0e1c4ffffea40a0ffff00a0ffff"
)
NDS7_PROGRAM = bytes.fromhex(
    "04d04de20000a0e30c20a0e3232682e3073da0e3013383e38a1ca0e382aca0e3ffc0a0e3"
    "ffcc8ce3ffe0a0e30150a0e30060a0e300608de5010000ea000082e50850a0e1ba6853e1"
    "406016e22683a0e1f9ffff1ab010c3e1d040a0e3b240c3e1b060d3e1800016e3fcffff1a"
    "b260d3e1b010c3e1b200c3e1b060d3e1800016e3fcffff1ab260d3e1b0a0c3e1b200c3e1"
    "b070d3e1800017e3fcffff1ab270d3e1b010c3e19040a0e3b240c3e1ff7007e2066487e1"
    "0c6006e0a693a0e1b060d3e1800016e3fcffff1ab260d3e1b010c3e1b200c3e1b060d3e1"
    "800016e3fcffff1ab260d3e1b0a0c3e1b200c3e1b070d3e1800017e3fcffff1ab270d3e1"
    "ff4009e2084002e5ff4007e2064484e1a4430ee0044002e50140a0e3004082e5010015e3"
    "0850a0e1c6ffff0a00609de5016086e22346a0e3006084e50050a0e3bcffffea"
)


def _crc16(data: bytes) -> int:
    """CRC-16 (poly 0xA001, init 0xFFFF) as used by the DS header."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build_nds() -> bytes:
    rom = bytearray(1024 * 1024)
    rom[0x00:0x0C] = b"RETROWEBTEST"
    # Game code absent from melonDS's ROM list, and ARM9 code placed at
    # 0x8000 (a retail-style layout, past the secure area): melonDS then
    # treats the cart as retail with a 64 kbit EEPROM save instead of a
    # save-less homebrew cart.
    rom[0x0C:0x10] = b"RWEB"
    rom[0x10:0x12] = b"01"
    rom[0x14] = 3  # capacity: 128 KiB << 3 = 1 MiB
    arm9_offset, arm7_offset = 0x8000, 0x10000
    struct.pack_into("<IIII", rom, 0x20, arm9_offset, 0x02000000, 0x02000000, len(NDS9_PROGRAM))
    struct.pack_into("<IIII", rom, 0x30, arm7_offset, 0x03800000, 0x03800000, len(NDS7_PROGRAM))
    struct.pack_into("<II", rom, 0x60, 0x00586000, 0x001808F8)  # cart command settings
    struct.pack_into("<H", rom, 0x6E, 0x051E)  # secure area delay
    struct.pack_into("<II", rom, 0x80, arm7_offset + len(NDS7_PROGRAM), 0x4000)
    # 0x15C holds the checksum the BIOS expects for the Nintendo logo. The
    # logo bitmap itself is not included; the emulator's direct boot skips it.
    struct.pack_into("<H", rom, 0x15C, 0xCF56)
    struct.pack_into("<H", rom, 0x15E, _crc16(bytes(rom[:0x15E])))
    rom[arm9_offset : arm9_offset + len(NDS9_PROGRAM)] = NDS9_PROGRAM
    rom[arm7_offset : arm7_offset + len(NDS7_PROGRAM)] = NDS7_PROGRAM
    return bytes(rom)


BUILDERS = {
    "gba": ("RetroWeb Test (World).gba", build_gba),
    "gb": ("RetroWeb Test (World).gb", lambda: build_gb(color=False)),
    "gbc": ("RetroWeb Test (World).gbc", lambda: build_gb(color=True)),
    "nes": ("RetroWeb Test (World).nes", build_nes),
    "snes": ("RetroWeb Test (World).sfc", build_snes),
    "genesis": ("RetroWeb Test (World).md", build_genesis),
    "ps1": ("RetroWeb Test (World).cue", lambda: build_ps1_cue("RetroWeb Test (World).bin")),
    "n64": ("RetroWeb Test (World).z64", build_n64),
    "nds": ("RetroWeb Test (World).nds", build_nds),
}
# Extra files written next to the primary one.
COMPANIONS = {"ps1": ("RetroWeb Test (World).bin", build_ps1_disc)}


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
        if system in COMPANIONS:
            companion_name, companion_builder = COMPANIONS[system]
            companion = root / system / companion_name
            companion_data = companion_builder()
            companion.write_bytes(companion_data)
            print(f"wrote {companion} ({len(companion_data)} bytes)")


if __name__ == "__main__":
    main()
