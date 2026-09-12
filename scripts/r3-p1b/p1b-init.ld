OUTPUT_ARCH(aarch64)
ENTRY(main)
SECTIONS {
	. = 0x400000;
	.text : { *(.text*) }
	.rodata : { *(.rodata*) *(.data*) }
	.bss : { *(.bss*) *(COMMON) }
	/DISCARD/ : {
		*(.comment)
		*(.note*)
		*(.eh_frame*)
		*(.ARM.attributes)
		*(.debug*)
	}
}
