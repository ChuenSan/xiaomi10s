/* Negative control: store to unknown RAM. Must be REJECTED. */
.section .text, "ax", @progbits
.global _start
_start:
	str	xzr, [x0]
	ret
