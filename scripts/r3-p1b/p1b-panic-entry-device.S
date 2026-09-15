/* thyme R3 P1B PANIC_ENTRY-8 FAIL-CLOSED panic() ENTRY checkpoint.
 *
 * ARCHITECTURE: INLINE at the canonical panic() function entry. panic text is
 * already mapped executable; the probe runs only if the audited canonical
 * panic symbol is invoked. No prior-round padding, no unproven external cave.
 * The 76-byte diagnostic CORE is byte-identical to the T0/T1/T2/T3/T4/C_DELAY
 * true-device proven core.
 *
 * The entry-preservation prefix is NOT in this file: the predevice composer
 * prepends the original panic entry word when the landing audit requires it.
 * This file is the delay/reset core only.
 *
 * DESTRUCTIVE DIAGNOSTIC: REACH -> DAIF mask -> 8s CNTPCT register-only delay
 * -> PSCI SYSTEM_RESET (fid 0x84000009, smc #0) -> wfe forever.
 * Fully independent of the panic timeout mechanism and of delay calibration:
 * this core never reads the timeout variable and never calls any calibrated
 * busy-wait. It never returns and never executes the overwritten panic body.
 *
 * Register discipline: w0/x0 (PSCI FID), x9, x10, x11, x12, x13, NZCV only.
 * No stack, no loads, no stores, no MMIO, PC-relative only, zero relocs.
 */
#ifndef P1B_PANIC_ENTRY_DELAY
#error "P1B_PANIC_ENTRY_DELAY required"
#endif
#if (P1B_PANIC_ENTRY_DELAY) != 8
#error "P1B_PANIC_ENTRY_DELAY must be 8 (PANIC_ENTRY-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_panic_entry_checkpoint
r3_panic_entry_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_PANIC_ENTRY_DELAY
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
