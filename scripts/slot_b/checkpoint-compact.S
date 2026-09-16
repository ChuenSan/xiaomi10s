/* Same CNTPCT/PSCI diagnostic as T1; inverted polling branch fits in 68 bytes. */
.section .text, "ax", @progbits
.p2align 2
.global slot_b_compact_checkpoint
slot_b_compact_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #8
	mul	x10, x9, x10
	isb
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
