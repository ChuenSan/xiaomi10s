/* R3 P1 ABL entry-state probe prototype. Design only this round.
 * Delay encoding after a P0-class CNTPCT wait:
 *   delay = 8 + 16*(EL==EL2) + 32*(SCTLR_ELx.M) + 64*(SCTLR_ELx.C)
 * Then PSCI SYSTEM_RESET 0x84000009 via SMC, same as P0.
 * No stack. No RAM store. No SCTLR write. No ERET.
 */
.section .text, "ax", @progbits
.p2align 2
.global _start
_start:
	b	probe_entry
	b	probe_entry
	.quad	0x80000
	.quad	0x2220000
	.quad	0xa
	.quad	0
	.quad	0
	.quad	0
	.word	0x644d5241
	.word	0

.org 0x40
probe_entry:
	isb
	mrs	x1, CurrentEL
	cmp	x1, #8
	mrs	x2, sctlr_el1
	b.ne	1f
	mrs	x2, sctlr_el2
1:
	movz	x3, #8
	b.ne	2f
	add	x3, x3, #16
2:
	tbz	x2, #0, 3f
	add	x3, x3, #32
3:
	tbz	x2, #2, 4f
	add	x3, x3, #64
4:
	mrs	x1, cntfrq_el0
	mul	x3, x1, x3
	isb
	mrs	x4, cntpct_el0
5:
	isb
	mrs	x5, cntpct_el0
	sub	x6, x5, x4
	cmp	x6, x3
	b.hs	6f
	yield
	b	5b
6:
	movz	w0, #0x0009
	movk	w0, #0x8400, lsl #16
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	smc	#0
7:
	wfe
	b	7b
