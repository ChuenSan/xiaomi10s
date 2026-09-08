OUTPUT_FORMAT("elf64-littleaarch64")
OUTPUT_ARCH(aarch64)
ENTRY(_start)
SECTIONS
{
	. = 0x400000;
	.text : { *(.text .text.*) }
	.rodata : { *(.rodata .rodata.*) }
	/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
