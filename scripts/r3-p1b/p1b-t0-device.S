/* thyme R3 P1B T0-8 FAIL-CLOSED device checkpoint trampoline, linked at
 * Image offset 0x40 (reserved __EFI_PE_HEADER hole [0x40, 0x10000)).
 * Same handoff contract prefix as p1b-trampoline.S (DAIF mask, x0 -> RT-D
 * trailer at S + DTB_OFFSET, x1=x2=x3=0, PC-relative, no stack, no stores,
 * no relocations). The frozen FIX8 handoff's final "branch primary_entry"
 * slot is REPLACED by the T0 diagnostic checkpoint; no branch to
 * primary_entry exists in this file:
 *   reach T0 -> CNTPCT-scaled 8s register-only delay -> PSCI SYSTEM_RESET
 *   (smc #0) -> on unexpected smc return, wfe forever.
 * Semantics: REACH -> DELAY -> RESET -> NEVER CONTINUE NORMAL BOOT.
 * Packer injects (see p1b-t0-predevice.py):
 *   P1B_DTB_REL    signed byte displacement from the ADR below to the RT-D
 *                  trailer: DTB_OFFSET - offset_of(dtb_rel)
 *   P1B_T0_DELAY   checkpoint delay seconds; must be 8 (T0-8 candidate only)
 * Clobber registers: x0/w0 (PSCI FID), x9, x10, x11, x12, x13, NZCV.
 */
#ifndef P1B_DTB_REL
#error "P1B_DTB_REL required"
#endif
#ifndef P1B_T0_DELAY
#error "P1B_T0_DELAY required"
#endif
#if (P1B_T0_DELAY) != 8
#error "P1B_T0_DELAY must be 8 (T0-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_t0_device_entry
r3_t0_device_entry:
	msr	daifset, #0xf
	isb
	adr	x0, dtb_rel
	ldr	x9, dtb_rel
	add	x0, x0, x9
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_T0_DELAY
	mul	x10, x9, x10
	isb
	mrs	x11, cntpct_el0
1:
	isb
	mrs	x12, cntpct_el0
	sub	x13, x12, x11
	cmp	x13, x10
	b.hs	2f
	yield
	b	1b
2:
	movz	w0, #0x0009
	movk	w0, #0x8400, lsl #16
	smc	#0
3:
	wfe
	b	3b
	.p2align 3
dtb_rel:
	.quad	P1B_DTB_REL
