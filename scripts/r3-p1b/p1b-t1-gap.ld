OUTPUT_ARCH(aarch64)
ENTRY(r3_t1_probe)
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
	}
}
