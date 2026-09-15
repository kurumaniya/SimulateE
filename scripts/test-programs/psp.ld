/* Static (pre-relocated) PSP user executable, loaded at the usual 0x08804000. */
ENTRY(module_start)
/* One flat segment and no header segment: the loader copies PT_LOADs as they are. */
PHDRS { image PT_LOAD FLAGS(7); }
SECTIONS
{
  . = 0x08804000;
  .text : { *(.text .text.*) } :image
  .sceStub.text : { *(.sceStub.text) } :image
  .rodata.sceModuleInfo : { *(.rodata.sceModuleInfo) } :image
  .lib.ent : { __lib_ent_top = .; *(.lib.ent) __lib_ent_bottom = .; } :image
  .lib.stub : { __lib_stub_top = .; *(.lib.stub) __lib_stub_bottom = .; } :image
  .rodata.sceNid : { *(.rodata.sceNid) } :image
  .rodata.sceResident : { *(.rodata.sceResident) } :image
  .rodata : { *(.rodata .rodata.*) } :image
  .data : { *(.data .data.*) } :image
  .bss : { *(.bss .bss.* COMMON) } :image
  /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.comment) *(.note.*) *(.pdr) *(.mdebug.*) }
}
