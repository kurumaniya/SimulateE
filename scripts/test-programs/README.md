# Test programs

Sources of the compiled test programs embedded in `../make-test-rom.py`.
They only paint the screen so the emulator can be seen running.

```bash
mipsel-linux-gnu-gcc -O1 -march=r3000 -mabi=32 -msoft-float -nostdlib -ffreestanding \
  -fno-pic -mno-abicalls -G0 -fno-builtin -Wl,--build-id=none -Wl,-N \
  -Wl,-Ttext=0x80010000 -Wl,-e,_start -o ps1.elf ps1.c
mipsel-linux-gnu-objcopy -O binary -j .text ps1.elf ps1.bin

mips-linux-gnu-gcc -O1 -march=vr4300 -mabi=32 -msoft-float -nostdlib -ffreestanding \
  -fno-pic -mno-abicalls -G0 -fno-builtin -Wl,--build-id=none -Wl,-N \
  -Wl,-Ttext=0x80000400 -Wl,-e,_start -o n64.elf n64.c
mips-linux-gnu-objcopy -O binary -j .text n64.elf n64.bin
```

The N64 ROM is booted by `ipl3.S`, a 64-byte stub that only copies the
program from ROM offset 0x1000 to RDRAM and jumps to it. It depends on the
emulator's high-level PIF boot (no RDRAM initialisation, no CIC handshake),
so the ROM runs in emulators but not on real hardware. Assemble it with:

```bash
mips-linux-gnu-gcc -march=vr4300 -mabi=32 -nostdlib -ffreestanding -fno-pic -mno-abicalls   -Wl,--build-id=none -Wl,-N -Wl,-Ttext=0xA4000040 -Wl,-e,_start -o ipl3.elf ipl3.S
mips-linux-gnu-objcopy -O binary -j .text ipl3.elf ipl3.bin
```

No Nintendo or Sony code is included.

The NDS program is two bare-metal C files: `nds9.c` (ARM9: EEPROM boot
counter, backdrop colours, touch log) and `nds7.c` (ARM7: reads the touch
screen controller over SPI into a mailbox in main RAM). Built with clang:

```bash
clang --target=armv5te-none-eabi -mcpu=arm946e-s -marm -O1 -nostdlib -ffreestanding \
  -fno-builtin -fno-pic -fno-stack-protector -c nds9.c -o nds9.o
ld.lld -Ttext=0x02000000 -e _start --build-id=none -o nds9.elf nds9.o
llvm-objcopy -O binary -j .text nds9.elf nds9.bin

clang --target=armv4t-none-eabi -mcpu=arm7tdmi -marm -O1 -nostdlib -ffreestanding \
  -fno-builtin -fno-pic -fno-stack-protector -c nds7.c -o nds7.o
ld.lld -Ttext=0x03800000 -e _start --build-id=none -o nds7.elf nds7.o
llvm-objcopy -O binary -j .text nds7.elf nds7.bin
```

The DS header carries no Nintendo logo bitmap and no encrypted secure
area, so the ROM only runs through an emulator's direct boot (melonDS with
FreeBIOS), not on real hardware or through the DS firmware menu.
