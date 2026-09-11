/* Negative control: cross-section absolute symbol. .o must have relocs. */
.section .rodata, "a", @progbits
.global abs_sym
abs_sym:
	.quad	0x80000000

.section .text, "ax", @progbits
.global _start
_start:
	adrp	x0, abs_sym
	ldr	x0, [x0, :lo12:abs_sym]
	ret
