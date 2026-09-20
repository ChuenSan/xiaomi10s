/* 44-byte COMPACT48 core: DELETE-ONLY transform of the proven 56-byte core.
 * Drops `msr daifset,#0xf` (never in the subsys core), the loop `isb`, and the
 * terminal `wfe`. The original `paciasp` entry pad is NOT emitted here -- it is
 * prepended by Python (cp.pad_probe) so this object is exactly the 44-byte
 * diagnostic core whose sha256 is CORE44_SHA. All instructions are
 * position-independent: only local PC-relative branches (`b.lo`, `b .`), so the
 * assembled object carries ZERO relocations. */
.section .text, "ax", @progbits
.p2align 2
.global slot_b_compact44_checkpoint
slot_b_compact44_checkpoint:
	mrs	x9, cntfrq_el0
	lsl	x10, x9, #3
	mrs	x11, cntpct_el0
1:
	mrs	x12, cntpct_el0
	sub	x13, x12, x11
	cmp	x13, x10
	b.lo	1b
	movz	w0, #0x0009
	movk	w0, #0x8400, lsl #16
	smc	#0
	b	.
