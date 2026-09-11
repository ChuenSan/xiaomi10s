/* Negative control: absolute DRAM constant. Must be REJECTED. */
.section .text, "ax", @progbits
.global _start
_start:
	ldr	x0, =0x80000000
	ret
