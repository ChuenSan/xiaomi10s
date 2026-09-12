/* NEGATIVE CONTROL: absolute symbol relocation. A data quad references a
 * cross-section text symbol, producing R_AARCH64_ABS64. Every gate must
 * REJECT. */
.section .rodata, "a", @progbits
.global base_addr
base_addr:
	.quad	text_base

.section .text, "ax", @progbits
.global _start
.global text_base
_start:
	b	1f
1:
	nop
text_base:
	nop
