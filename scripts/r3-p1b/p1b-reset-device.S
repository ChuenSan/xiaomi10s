/* thyme R3 P1B RESET pair fail-closed machine_restart ENTRY checkpoint.
 *
 * Shared source for RESET8 (P1B_RESET_DELAY=8) and RESET1 (P1B_RESET_DELAY=1).
 * The ONLY intentional semantic variable between the two members is that
 * programmed CNTPCT delay immediate. Probe placement, entry-word handling,
 * timer algorithm, PSCI FID, SMC, WFE loop and fail-closed shape are identical.
 *
 * ARCHITECTURE: INLINE at the selected Linux software-restart choke entry
 * (primary: machine_restart). The probe runs only if that symbol is invoked.
 * No prior-round padding, no unproven external cave.
 * The 76-byte diagnostic CORE is byte-identical to the T0/T1/T2/T3/T4/C_DELAY
 * true-device proven core except for the delay immediate on RESET1.
 *
 * The entry-preservation prefix is NOT in this file: the predevice composer
 * prepends the original entry word when the landing audit requires it.
 * This file is the delay/reset core only.
 *
 * DESTRUCTIVE DIAGNOSTIC: REACH -> DAIF mask -> programmed CNTPCT delay
 * -> PSCI SYSTEM_RESET (fid 0x84000009, smc #0) -> wfe forever.
 * Never returns, never fall-through, never executes the overwritten body.
 *
 * Register discipline: w0/x0 (PSCI FID), x9, x10, x11, x12, x13, NZCV only.
 * No stack, no loads, no stores, no MMIO, PC-relative only, zero relocs.
 */
#ifndef P1B_RESET_DELAY
#error "P1B_RESET_DELAY required"
#endif
#if (P1B_RESET_DELAY) != 8 && (P1B_RESET_DELAY) != 1
#error "P1B_RESET_DELAY must be 8 (RESET8) or 1 (RESET1)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_restart_choke_checkpoint
r3_restart_choke_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_RESET_DELAY
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
