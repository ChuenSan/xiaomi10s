/* thyme R3 P1B T0 reach-and-reset checkpoint trampoline, linked at Image
 * offset 0x40. Same handoff contract as p1b-trampoline.S (DAIF mask, x0 ->
 * RT-D trailer, x1=x2=x3=0, PC-relative, no stack, no stores, no
 * relocations), with the probe inserted after the register setup and before
 * the branch to primary_entry:
 *   reach T0 -> controlled CNTPCT delay -> PSCI SYSTEM_RESET (smc #0)
 *   -> on smc return, restore x0/x1/x2/x3 and fall through to primary_entry.
 * Fail-safe: if the reset does not take effect, the normal P1B handoff
 * contract is restored bit for bit and Linux boot continues.
 * DIAGNOSTIC ONLY: a T0 signature proves trampoline reachability, not Linux
 * entry, not RT-D consumption by the kernel, not a normal boot.
 * Packer injects (see p1b-panic-checkpoint-isolation.py):
 *   P1B_DTB_REL      byte displacement ADR -> RT-D trailer
 *   P1B_ENTRY_REL    byte displacement B -> primary_entry
 *   P1B_PROBE_DELAY  checkpoint delay in seconds (CNTPCT-scaled)
 */
#ifndef P1B_DTB_REL
#error "P1B_DTB_REL required"
#endif
#ifndef P1B_ENTRY_REL
#error "P1B_ENTRY_REL required"
#endif
#ifndef P1B_PROBE_DELAY
#error "P1B_PROBE_DELAY required"
#endif
#if (P1B_ENTRY_REL) % 4
#error "P1B_ENTRY_REL must be 4-byte aligned"
#endif
#if (P1B_PROBE_DELAY) <= 0 || (P1B_PROBE_DELAY) > 0xffff
#error "P1B_PROBE_DELAY out of range"
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
	mov	x15, x0
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_PROBE_DELAY
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
	mov	x0, x15
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
b_primary:
	.inst	0x14000000 | (((P1B_ENTRY_REL) / 4) & 0x03ffffff)
	.p2align 3
dtb_rel:
	.quad	P1B_DTB_REL
