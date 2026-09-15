/*
 * RetroWeb NDS test program, ARM7 side.
 *
 * The ARM7 owns the touch-screen controller (TSC2046 on the SPI bus). This
 * loop reads it continuously and publishes the result to a mailbox in main
 * RAM that the ARM9 program (nds9.c) polls:
 *
 *   mailbox[0]  number of separate touches so far
 *   mailbox[1]  x in screen pixels (0..255)
 *   mailbox[2]  y in screen pixels (0..191)
 *   mailbox[3]  1 while the screen is touched
 *
 * Pen contact comes from EXTKEYIN bit 6 (0 while the pen is down), the same
 * signal the DS firmware uses. The controller then answers a 0x90 (Y) or
 * 0xD0 (X) command with a 12-bit value spread over the next two bytes.
 * (Reading Y == 0xFFF as "released" is not enough: before the first touch
 * the emulated controller reports 0, which would look like a pen at 0,0.)
 */

#define REG16(a) (*(volatile unsigned short *)(a))

#define SPICNT 0x040001C0u
#define SPIDATA 0x040001C2u
#define EXTKEYIN 0x04000136u
#define PEN_UP 0x40u
#define MAILBOX 0x02300000u

static unsigned spi_byte(unsigned char value, int hold) {
  /* enable | device 2 (touch screen) | 8-bit | slowest clock */
  REG16(SPICNT) = (unsigned short)(0x8200u | (hold ? 0x0800u : 0u));
  REG16(SPIDATA) = value;
  while (REG16(SPICNT) & 0x80u) {
  }
  return REG16(SPIDATA) & 0xFFu;
}

static unsigned tsc_read(unsigned char command) {
  spi_byte(command, 1);
  unsigned high = spi_byte(0x00, 1);
  unsigned low = spi_byte(0x00, 0);
  return (((high << 8) | low) >> 3) & 0xFFFu;
}

void _start(void) {
  volatile unsigned *mailbox = (volatile unsigned *)MAILBOX;
  unsigned touches = 0;
  int touching = 0;
  for (;;) {
    if ((REG16(EXTKEYIN) & PEN_UP) == 0) {
      unsigned x = tsc_read(0xD0);
      unsigned y = tsc_read(0x90);
      mailbox[1] = x >> 4;
      mailbox[2] = y >> 4;
      mailbox[3] = 1;
      if (!touching) {
        touching = 1;
        touches++;
        mailbox[0] = touches;
      }
    } else {
      mailbox[3] = 0;
      touching = 0;
    }
  }
}
