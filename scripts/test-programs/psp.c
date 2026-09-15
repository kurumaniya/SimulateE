/*
 * RetroWeb PSP test program (user-mode module, direct syscalls).
 *
 * On boot: read ms0:/PSP/SAVEDATA/RWEB00001/COUNTER.BIN from the memory
 * stick, bump the boot counter (byte 0, magic "RWEB" at bytes 4..7), write
 * it back, and fill the screen with a colour derived from the counter.
 *
 * Everything the program needs from the firmware is imported by NID through
 * psp-stubs.S; the module info, export table and linker script (psp.ld)
 * follow the layout the PSP kernel (and PPSSPP's loader) expects. No SDK
 * code is linked in.
 */

typedef unsigned int u32;

int sceDisplaySetMode(int mode, int width, int height);
int sceDisplaySetFrameBuf(void *topaddr, int bufferwidth, int pixelformat, int sync);
int sceDisplayWaitVblankStart(void);
int sceIoOpen(const char *file, int flags, int mode);
int sceIoRead(int fd, void *data, u32 size);
int sceIoWrite(int fd, const void *data, u32 size);
int sceIoClose(int fd);
int sceIoMkdir(const char *dir, int mode);
int sceKernelSleepThread(void);
void sceKernelDcacheWritebackAll(void);

#define PSP_O_RDONLY 0x0001
#define PSP_O_WRONLY 0x0002
#define PSP_O_CREAT 0x0200
#define PSP_O_TRUNC 0x0400
#define PSP_DISPLAY_PIXEL_FORMAT_8888 3
#define PSP_DISPLAY_SETBUF_NEXTFRAME 1

#define VRAM_UNCACHED 0x44000000u
#define BUFFER_WIDTH 512
#define SCREEN_WIDTH 480
#define SCREEN_HEIGHT 272

/* Symbols the linker script defines around .lib.ent and .lib.stub. */
extern char __lib_ent_top[], __lib_ent_bottom[], __lib_stub_top[], __lib_stub_bottom[];

int module_start(u32 args, void *argp);

typedef struct {
  unsigned short attributes;
  unsigned char version[2];
  char name[28];
  void *gp;
  void *ent_top;
  void *ent_end;
  void *stub_top;
  void *stub_end;
} ModuleInfo;

const ModuleInfo module_info __attribute__((section(".rodata.sceModuleInfo"), aligned(16), used)) = {
    0, {1, 1}, "RetroWebTest", 0, __lib_ent_top, __lib_ent_bottom, __lib_stub_top, __lib_stub_bottom,
};

/* syslib export: module_start (0xD632ACDB) and module_info (0xF01D73A7). */
static const u32 syslib_exports[4] __attribute__((section(".rodata.sceResident"), used)) = {
    0xD632ACDB, 0xF01D73A7, (u32)module_start, (u32)&module_info,
};

typedef struct {
  const char *name;
  unsigned short version;
  unsigned short attribute;
  unsigned char len;
  unsigned char vcount;
  unsigned short fcount;
  const void *exports;
} LibraryEntry;

const LibraryEntry library_exports[1] __attribute__((section(".lib.ent"), used)) = {
    {0, 0, 0x8000, 4, 1, 1, syslib_exports},
};

static const char SAVE_DIR[] = "ms0:/PSP/SAVEDATA/RWEB00001";
static const char SAVE_FILE[] = "ms0:/PSP/SAVEDATA/RWEB00001/COUNTER.BIN";

static u32 bump_counter(void) {
  unsigned char record[8];
  u32 counter = 0;
  sceIoMkdir("ms0:/PSP", 0777);
  sceIoMkdir("ms0:/PSP/SAVEDATA", 0777);
  sceIoMkdir(SAVE_DIR, 0777);
  int fd = sceIoOpen(SAVE_FILE, PSP_O_RDONLY, 0777);
  if (fd >= 0) {
    if (sceIoRead(fd, record, 8) == 8 && record[4] == 'R' && record[5] == 'W' && record[6] == 'E' &&
        record[7] == 'B') {
      counter = record[0];
    }
    sceIoClose(fd);
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
  fd = sceIoOpen(SAVE_FILE, PSP_O_WRONLY | PSP_O_CREAT | PSP_O_TRUNC, 0777);
  if (fd >= 0) {
    sceIoWrite(fd, record, 8);
    sceIoClose(fd);
  }
  return counter;
}

int module_start(u32 args, void *argp) {
  (void)args;
  (void)argp;
  u32 counter = bump_counter();

  sceDisplaySetMode(0, SCREEN_WIDTH, SCREEN_HEIGHT);
  /* ABGR8888: opaque, blue base, green rising with the counter. */
  u32 colour = 0xFFC00000u | ((counter & 0x1Fu) << 11);
  volatile u32 *fb = (volatile u32 *)VRAM_UNCACHED;
  for (int i = 0; i < BUFFER_WIDTH * SCREEN_HEIGHT; i++) {
    fb[i] = colour;
  }
  sceKernelDcacheWritebackAll();
  sceDisplaySetFrameBuf((void *)VRAM_UNCACHED, BUFFER_WIDTH, PSP_DISPLAY_PIXEL_FORMAT_8888,
                        PSP_DISPLAY_SETBUF_NEXTFRAME);
  for (;;) {
    sceDisplayWaitVblankStart();
  }
}
