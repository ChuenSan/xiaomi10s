/* 52-byte core: proven 56-byte CNTPCT/PSCI sequence without DAIF mask. */
.section .text, "ax", @progbits
.p2align 2
.global slot_b_subsys52_checkpoint
slot_b_subsys52_checkpoint:
	mrs	x9, cntfrq_el0
	lsl	x10, x9, #3
	mrs	x11, cntpct_el0
1:
	isb
	mrs	x12, cntpct_el0
	sub	x13, x12, x11
	cmp	x13, x10
	b.lo	1b
	movz	w0, #0x0009
	movk	w0, #0x8400, lsl #16
	smc	#0
2:
	wfe
	b	2b
