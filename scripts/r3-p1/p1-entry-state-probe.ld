OUTPUT_ARCH(aarch64)
ENTRY(_start)
SECTIONS {
	. = 0;
	.text : {
		*(.text)
		*(.text.*)
	}
	/DISCARD/ : {
		*(.comment)
		*(.note*)
		*(.eh_frame*)
		*(.ARM.attributes)
		*(.debug*)
		*(.rela*)
		*(.rel.*)
	}
}
