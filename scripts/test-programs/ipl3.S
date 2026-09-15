/* Minimal emulator-only IPL3: copy the program from ROM (0x1000) to RDRAM
 * 0x80000400 and jump there. Runs from SP DMEM (0xA4000040) after the
 * emulator's HLE PIF boot. No RDRAM init, no CIC: real hardware needs more. */
    .set noreorder
    .section .text
    .globl _start
_start:
    lui   $t0, 0xB000
    ori   $t0, $t0, 0x1000      /* source: cartridge ROM + 0x1000 (uncached) */
    lui   $t1, 0xA000
    ori   $t1, $t1, 0x0400      /* destination: RDRAM 0x400 (uncached view) */
    li    $t2, 4096             /* words to copy (16 KiB) */
copy:
    lw    $t3, 0($t0)
    sw    $t3, 0($t1)
    addiu $t0, $t0, 4
    addiu $t1, $t1, 4
    addiu $t2, $t2, -1
    bne   $t2, $zero, copy
    nop
    lui   $t4, 0x8000
    ori   $t4, $t4, 0x0400
    jr    $t4
    nop
