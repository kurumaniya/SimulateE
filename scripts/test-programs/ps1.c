/* RetroWeb PS1 test: paint the screen green through the GPU and idle. */
#define GP0 (*(volatile unsigned int *)0x1F801810)
#define GP1 (*(volatile unsigned int *)0x1F801814)

void _start(void) {
    GP1 = 0x00000000;                      /* reset GPU */
    GP1 = 0x08000001;                      /* 320x240, NTSC, 15-bit */
    GP1 = 0x06C60260;                      /* horizontal display range */
    GP1 = 0x07040010;                      /* vertical display range */
    GP1 = 0x05000000;                      /* display area at 0,0 */
    GP0 = 0xE1000000;                      /* draw mode */
    GP0 = 0xE3000000;                      /* drawing area top-left 0,0 */
    GP0 = 0xE4000000 | (239u << 10) | 319; /* drawing area bottom-right */
    GP0 = 0xE5000000;                      /* drawing offset 0,0 */
    GP0 = 0x0200FF40;                      /* fill rectangle, colour 0xBBGGRR */
    GP0 = 0x00000000;                      /* y<<16 | x */
    GP0 = (240u << 16) | 320;              /* h<<16 | w */
    GP1 = 0x03000000;                      /* display enable */
    for (;;) {
    }
}
