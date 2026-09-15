/* RetroWeb N64 test: two green 320x240 16-bit framebuffers, swapped on every
 * vertical retrace so the emulator's video plugin sees a new frame each time,
 * exactly like a real game. */
#define VI ((volatile unsigned int *)0xA4400000)
#define VI_ORIGIN 1
#define VI_CURRENT 4

static inline __attribute__((always_inline)) void fill(volatile unsigned short *fb, unsigned short colour) {
    for (int i = 0; i < 320 * 240; i++) fb[i] = colour;
}

void _start(void) {
    volatile unsigned short *fb0 = (volatile unsigned short *)0xA0100000;
    volatile unsigned short *fb1 = (volatile unsigned short *)0xA0130000;
    fill(fb0, 0x07C1); /* RGBA5551 green */
    fill(fb1, 0x07C1);
    VI[VI_ORIGIN] = 0x00100000;
    VI[2] = 320;         /* width */
    VI[3] = 2;           /* interrupt line */
    VI[5] = 0x03E52239;  /* burst */
    VI[6] = 0x0000020D;  /* v sync */
    VI[7] = 0x00000C15;  /* h sync */
    VI[8] = 0x0C150C15;  /* leap */
    VI[9] = 0x006C02EC;  /* h start */
    VI[10] = 0x002501FF; /* v start */
    VI[11] = 0x000E0204; /* v burst */
    VI[12] = 0x00000200; /* x scale */
    VI[13] = 0x00000400; /* y scale */
    VI[0] = 0x00003202;  /* status: 16bpp */
    unsigned last = VI[VI_CURRENT];
    unsigned which = 0;
    for (;;) {
        unsigned line = VI[VI_CURRENT] & ~1u;
        if (line < last) { /* new field: swap buffers */
            which ^= 1;
            VI[VI_ORIGIN] = which ? 0x00130000 : 0x00100000;
        }
        last = line;
    }
}
