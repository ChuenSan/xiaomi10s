/* thyme R3 P1B minimal handoff trampoline, linked at Image offset 0x40.
 * Position-relative: no absolute S, no GOT, no relocations, no stores,
 * no stack, no MMU/cache/EL manipulation, no copydown.
 * Packer injects (see p1b-build.py):
 *   P1B_DTB_REL    signed byte displacement from the ADR below to the RT-D
 *                  trailer: DTB_OFFSET - offset_of(dtb_rel)
 *   P1B_ENTRY_REL  signed byte displacement from the B below to primary_entry:
 *                  primary_entry_off - offset_of(b_primary)
 * Image code0 stays the untouched EFI signature nop; Image code1 is patched
 * from "b primary_entry" to "b 0x40" (this trampoline).
 */
#ifndef P1B_DTB_REL
#error "P1B_DTB_REL required"
#endif
#ifndef P1B_ENTRY_REL
#error "P1B_ENTRY_REL required"
#endif
#if (P1B_ENTRY_REL) % 4
#error "P1B_ENTRY_REL must be 4-byte aligned"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_handoff_entry
r3_handoff_entry:
	msr	daifset, #0xf
	isb
	adr	x0, dtb_rel
	ldr	x9, dtb_rel
	add	x0, x0, x9
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
b_primary:
	.inst	0x14000000 | (((P1B_ENTRY_REL) / 4) & 0x03ffffff)
	.p2align 3
dtb_rel:
	.quad	P1B_DTB_REL
