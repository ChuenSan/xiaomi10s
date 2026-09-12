/* NEGATIVE CONTROL: absolute-address implementation. Loads a hardcoded
 * physical address from a cross-section literal via ADRP+LDR. The .o must
 * carry relocations. Every gate must REJECT. */
.section .rodata, "a", @progbits
.global abs_sym
abs_sym:
	.quad	0xa0080000

.section .text, "ax", @progbits
.global _start
_start:
	adrp	x0, abs_sym
	ldr	x0, [x0, :lo12:abs_sym]
	ret
