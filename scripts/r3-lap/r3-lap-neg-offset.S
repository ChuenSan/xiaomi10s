/* NEGATIVE CONTROL: wrong image-base offset. image_base label is no longer
 * payload offset 0, so the ADR target is non-zero. Every gate must REJECT. */
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
	adr	x0, image_base
	movz	x1, #0xffff
	movk	x1, #0x1f, lsl #16
	and	x0, x0, x1
	movz	x2, #0x8
	lsl	x2, x2, #16
	cmp	x0, x2
	b.eq	match
	movz	x5, #24
	b	arm_timer
match:
	movz	x5, #8
arm_timer:
	mrs	x6, cntfrq_el0
	mul	x5, x6, x5
	isb
	mrs	x7, cntpct_el0
5:
	isb
	mrs	x8, cntpct_el0
	sub	x9, x8, x7
	cmp	x9, x5
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

/* NEG: image_base misplaced away from payload offset 0 */
.global image_base
image_base:
	nop
