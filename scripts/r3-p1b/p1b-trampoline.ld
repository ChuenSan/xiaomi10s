OUTPUT_ARCH(aarch64)
ENTRY(r3_handoff_entry)
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
