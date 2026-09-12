/* thyme R3 P1 direct in-place x0 trampoline prototype.
 * Position-independent. No stack. No RAM store. No SCTLR/ERET/EL switch.
 * Packer injects:
 *   P1_DTB_REL    signed byte displacement from the ADR below to the DTB
 *   P1_ENTRY_REL  signed byte displacement from the B to primary_entry
 * Code0 of a clean Image branches here (P0 geometry, offset 0x40).
 */
#ifndef P1_DTB_REL
#error "P1_DTB_REL required"
#endif
#ifndef P1_ENTRY_REL
#error "P1_ENTRY_REL required"
#endif
#if (P1_ENTRY_REL) % 4
#error "P1_ENTRY_REL must be 4-byte aligned"
#endif

.section .text, "ax", @progbits
.p2align 2
.global _start
_start:
	b	p1_entry
	b	p1_entry
	.quad	0x80000
	.quad	0x2220000
	.quad	0xa
	.quad	0
	.quad	0
	.quad	0
	.word	0x644d5241
	.word	0

.org 0x40
p1_entry:
	isb
	adr	x0, dtb_rel
	ldr	x9, dtb_rel
	add	x0, x0, x9
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	isb
	.inst	0x14000000 | (((P1_ENTRY_REL) / 4) & 0x03ffffff)
	.p2align 3
dtb_rel:
	.quad	P1_DTB_REL
