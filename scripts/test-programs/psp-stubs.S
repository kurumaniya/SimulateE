/*
 * Firmware imports for psp.c, laid out the way the PSP kernel expects
 * (same shape as the PSP SDK's STUB_START / STUB_FUNC macros):
 *
 *   .lib.stub         one 5-word entry per module: name, version|attr,
 *                     (function count << 16) | 5, NID table, stub table
 *   .rodata.sceNid    the NIDs, one per imported function
 *   .sceStub.text     8 bytes per function; the loader patches each into
 *                     "jr $ra / syscall n"
 *
 * NIDs are taken from the PSP SDK's sceDisplay.S, IoFileMgrForUser.S,
 * ThreadManForUser.S and UtilsForUser.S.
 */

.macro STUB_START module, flags_ver, stub_len
	.section .rodata.sceResident, "a"
	.word	0
__stub_modulestr_\module:
	.asciz	"\module"
	.align	2
	.section .lib.stub, "a", @progbits
	.word	__stub_modulestr_\module
	.word	\flags_ver
	.word	\stub_len
	.word	__stub_idtable_\module
	.word	__stub_text_\module
	.section .rodata.sceNid, "a"
__stub_idtable_\module:
	.section .sceStub.text, "ax", @progbits
__stub_text_\module:
.endm

.macro STUB_FUNC funcid, funcname
	.set push
	.set noreorder
	.section .sceStub.text, "ax", @progbits
	.globl	\funcname
	.type	\funcname, @function
\funcname:
	jr	$ra
	nop
	.section .rodata.sceNid, "a"
	.word	\funcid
	.set pop
.endm

	STUB_START "sceDisplay", 0x40090000, 0x00030005
	STUB_FUNC 0x0E20F177, sceDisplaySetMode
	STUB_FUNC 0x289D82FE, sceDisplaySetFrameBuf
	STUB_FUNC 0x984C27E7, sceDisplayWaitVblankStart

	STUB_START "IoFileMgrForUser", 0x40090000, 0x00050005
	STUB_FUNC 0x109F50BC, sceIoOpen
	STUB_FUNC 0x6A638D83, sceIoRead
	STUB_FUNC 0x42EC03AC, sceIoWrite
	STUB_FUNC 0x810C4BC3, sceIoClose
	STUB_FUNC 0x06A70004, sceIoMkdir

	STUB_START "ThreadManForUser", 0x40090000, 0x00010005
	STUB_FUNC 0x9ACE131E, sceKernelSleepThread

	STUB_START "UtilsForUser", 0x40090000, 0x00010005
	STUB_FUNC 0x79D1C3FA, sceKernelDcacheWritebackAll
