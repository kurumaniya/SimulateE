#!/usr/bin/env python3
"""Offline sanity checks for the hand-assembled test ROMs.

Runs each program twice on a CPU emulator with persistent battery RAM and
checks that the counter goes 1 → 2. Optional dependencies (dev only):
unicorn (ARM, 68000), pyboy (Game Boy), py65 (6502). SNES is only covered by
the Playwright e2e test because no lightweight 65816 emulator is available.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROMS = Path("data/roms")


def check_gba() -> None:
    from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc

    rom = (ROMS / "gba" / "RetroWeb Test (World).gba").read_bytes()
    sram = bytearray(b"\xff" * 0x10000)
    for expected in (1, 2):
        mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(0x08000000, 0x100000)
        mu.mem_write(0x08000000, rom)
        mu.mem_map(0x04000000, 0x1000)
        mu.mem_map(0x06000000, 0x18000)
        mu.mem_map(0x0E000000, 0x10000)
        mu.mem_write(0x0E000000, bytes(sram))
        mu.emu_start(0x08000000, 0, count=200_000)
        sram = bytearray(mu.mem_read(0x0E000000, 0x10000))
        assert sram[0] == expected, ("gba", sram[0], expected)
        assert mu.mem_read(0x06012BFC, 4) != b"\0\0\0\0", "gba: screen not filled"
    print("gba ok")


def check_genesis() -> None:
    from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
    from unicorn.m68k_const import UC_CPU_M68K_M68000, UC_M68K_REG_A7

    rom = (ROMS / "genesis" / "RetroWeb Test (World).md").read_bytes()
    sram = bytearray(b"\xff" * 0x10000)
    for expected in (1, 2):
        mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_M68000)  # default is ColdFire: no byte immediates
        mu.mem_map(0x000000, 0x100000)
        mu.mem_write(0, rom)
        mu.mem_map(0x200000, 0x10000)
        mu.mem_write(0x200000, bytes(sram))
        mu.mem_map(0xA10000, 0x10000)  # I/O + TMSS
        mu.mem_map(0xC00000, 0x10000)  # VDP
        mu.mem_map(0xFF0000, 0x10000)  # work RAM
        mu.reg_write(UC_M68K_REG_A7, 0x00FFFE00)
        mu.emu_start(0x200, 0, count=200)
        sram = bytearray(mu.mem_read(0x200000, 0x10000))
        assert bytes(sram[3:10:2]) == b"RWEB", ("genesis magic", bytes(sram[0:10]))
        assert sram[1] == expected, ("genesis", sram[1], expected)
    print("genesis ok")


def check_gb(system: str) -> None:
    from pyboy import PyBoy

    path = ROMS / system / f"RetroWeb Test (World).{system}"
    ram = None
    for expected in (1, 2):
        boy = PyBoy(str(path), window="null", sound_emulated=False)
        if ram is not None:
            boy.memory[0x0000] = 0x0A  # MBC1: enable cartridge RAM before seeding it
            boy.memory[0xA000:0xA005] = list(ram)
        for _ in range(120):
            boy.tick()
        ram = bytes(boy.memory[0xA000:0xA005])
        boy.stop(save=False)
        assert ram[1:5] == b"RWEB", (system, "magic", ram)
        assert ram[0] == expected, (system, ram[0], expected)
    print(f"{system} ok")


def check_nes() -> None:
    from py65.devices.mpu6502 import MPU

    rom = (ROMS / "nes" / "RetroWeb Test (World).nes").read_bytes()
    prg = rom[16 : 16 + 16 * 1024]
    wram = bytes(0x2000)
    for expected in (1, 2):
        mpu = MPU()
        mem = mpu.memory
        mem[0xC000:0x10000] = list(prg)
        mem[0x6000:0x8000] = list(wram)
        mem[0x2002] = 0x80  # pretend the PPU is always in vblank
        mpu.pc = mem[0xFFFC] | (mem[0xFFFD] << 8)
        for _ in range(500):
            mpu.step()
            mem[0x2002] = 0x80
        wram = bytes(mem[0x6000:0x8000])
        assert wram[1:5] == b"RWEB", ("nes magic", wram[:5])
        assert wram[0] == expected, ("nes", wram[0], expected)
        assert mpu.pc == 0xC071, ("nes: not in idle loop", hex(mpu.pc))
    print("nes ok")


CHECKS = {"gba": check_gba, "genesis": check_genesis, "gb": lambda: check_gb("gb"),
          "gbc": lambda: check_gb("gbc"), "nes": check_nes}

if __name__ == "__main__":
    failed = False
    for name in sys.argv[1:] or CHECKS:
        try:
            CHECKS[name]()
        except ImportError as exc:
            print(f"{name}: skipped ({exc})")
        except AssertionError as exc:
            failed = True
            print(f"{name}: FAILED {exc}")
    sys.exit(1 if failed else 0)
