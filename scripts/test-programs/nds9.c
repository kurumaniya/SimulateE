/*
 * RetroWeb NDS test program, ARM9 side.
 *
 * On boot: read the cartridge EEPROM, bump the boot counter (byte 0, magic
 * "RWEB" at bytes 4..7), write it back, and paint the top screen with a
 * colour derived from the counter.
 *
 * Then: poll the mailbox the ARM7 fills from the touch screen. While the
 * screen is touched the bottom screen turns green; each new touch is also
 * recorded in the EEPROM at offset 0x10 ('T', touch number, x, y) so the
 * e2e test can prove pointer input reached the emulated console.
 *
 * Both screens are plain backdrop colour (2D engines in mode 1 with no
 * backgrounds enabled), so no VRAM setup is needed. Built for direct boot
 * only: it relies on the emulator having set up CP15, stacks and POWCNT1.
 */

#define REG32(a) (*(volatile unsigned int *)(a))
#define REG16(a) (*(volatile unsigned short *)(a))

#define POWCNT1 0x04000304u
#define DISPCNT_A 0x04000000u
#define DISPCNT_B 0x04001000u
#define PALETTE_A 0x05000000u
#define PALETTE_B 0x05000400u
#define AUXSPICNT 0x040001A0u
#define AUXSPIDATA 0x040001A2u

/* Shared with nds7.c: [0] touch count, [1] x, [2] y, [3] currently touching. */
#define MAILBOX 0x02300000u

/* One byte over the cartridge SPI bus (EEPROM). `last` releases chip select. */
static unsigned char spi_byte(unsigned char value, int last) {
  REG16(AUXSPICNT) = last ? 0xA000u : 0xA040u; /* enable | SPI mode | hold */
  REG16(AUXSPIDATA) = value;
  while (REG16(AUXSPICNT) & 0x80u) {
  }
  return (unsigned char)REG16(AUXSPIDATA);
}

static void eeprom_read(unsigned address, unsigned char *out, int count) {
  spi_byte(0x03, 0);
  spi_byte((unsigned char)(address >> 8), 0);
  spi_byte((unsigned char)address, 0);
  for (int i = 0; i < count; i++) {
    out[i] = spi_byte(0x00, i == count - 1);
  }
}

static void eeprom_write(unsigned address, const unsigned char *data, int count) {
  spi_byte(0x06, 1); /* write enable */
  spi_byte(0x02, 0);
  spi_byte((unsigned char)(address >> 8), 0);
  spi_byte((unsigned char)address, 0);
  for (int i = 0; i < count; i++) {
    spi_byte(data[i], i == count - 1);
  }
}

void _start(void) {
  REG32(POWCNT1) = 0x820Fu; /* both LCDs and 2D engines on, engine A on top */
  REG32(DISPCNT_A) = 0x00010000u; /* graphics display, no layers: backdrop */
  REG32(DISPCNT_B) = 0x00010000u;

  unsigned char record[8];
  eeprom_read(0, record, 8);
  unsigned counter = 0;
  if (record[4] == 'R' && record[5] == 'W' && record[6] == 'E' && record[7] == 'B') {
    counter = record[0];
  }
  counter = (counter + 1) & 0xFFu;
  record[0] = (unsigned char)counter;
  record[1] = 0;
  record[2] = 0;
  record[3] = 0;
  record[4] = 'R';
  record[5] = 'W';
  record[6] = 'E';
  record[7] = 'B';
  eeprom_write(0, record, 8);

  /* Top screen: blue, with green rising with the counter. */
  REG16(PALETTE_A) = (unsigned short)(0x7C00u | ((counter & 0x1Fu) << 5));
  /* Bottom screen: dark red until touched. */
  REG16(PALETTE_B) = 0x0010u;

  volatile unsigned *mailbox = (volatile unsigned *)MAILBOX;
  mailbox[0] = 0;
  mailbox[3] = 0;
  unsigned seen = 0;
  for (;;) {
    unsigned touches = mailbox[0];
    if (touches != seen) {
      seen = touches;
      unsigned char touch[4];
      touch[0] = 'T';
      touch[1] = (unsigned char)touches;
      touch[2] = (unsigned char)mailbox[1];
      touch[3] = (unsigned char)mailbox[2];
      eeprom_write(0x10, touch, 4);
    }
    REG16(PALETTE_B) = mailbox[3] ? 0x03E0u : 0x0010u;
  }
}
