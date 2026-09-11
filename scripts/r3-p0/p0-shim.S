/* thyme R3 P0 entry-proof shim.
 * Position-independent, no stack, no RAM write, no DTB/MMIO access.
 * Delay seconds are injected by -DP0_DELAY_SECONDS={0,8,24}.
 */
#ifndef P0_DELAY_SECONDS
#error "P0_DELAY_SECONDS required"
#endif

.section .text, "ax", @progbits
.p2align 2
.global _start
_start:
	b	p0_entry
	b	p0_entry
	.quad	0x80000
	.quad	0x2220000
	.quad	0xa
	.quad	0
	.quad	0
	.quad	0
	.word	0x644d5241
	.word	0

.org 0x40
p0_entry:
	isb
	mrs	x1, cntfrq_el0
	movz	x2, #P0_DELAY_SECONDS
	mul	x3, x1, x2
	isb
	mrs	x4, cntpct_el0
1:
	isb
	mrs	x5, cntpct_el0
	sub	x6, x5, x4
	cmp	x6, x3
	b.hs	2f
	yield
	b	1b
2:
	movz	w0, #0x0009
	movk	w0, #0x8400, lsl #16
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	mov	x4, xzr
	mov	x5, xzr
	mov	x6, xzr
	mov	x7, xzr
	smc	#0
3:
	wfe
	b	3b
