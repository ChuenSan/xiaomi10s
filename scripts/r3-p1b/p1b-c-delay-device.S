/* thyme R3 P1B C_DELAY-8 FAIL-CLOSED post-calibrate_delay checkpoint.
 *
 * ARCHITECTURE: INLINE. Mid-function fallthrough inside start_kernel
 * .init.text after calibrate_delay() returns. No padding, no external
 * cave, no T1 0x2230000 mapping claim. The CPU is already executing
 * this VA (MMU-on, EL1).
 *
 * Selected stage (GHA re-derives from exact vmlinux; JSON is not sole gate):
 *   C_DELAY = CALIBRATE_DELAY_COMPLETE = first insn AFTER that BL.
 *
 *   control: ABL -> code1 "b 0x40" -> UNMODIFIED frozen FIX8 trampoline
 *            -> primary_entry / head.S / __primary_switched (FIX8 bytes)
 *            -> bl start_kernel
 *            -> start_kernel ENTRY is ORIGINAL FIX8 word0 + prologue
 *            -> normal start_kernel body through C6 parse_args COMPLETE
 *               (T4 C6 inline probe is gone; C6 bytes are FIX8)
 *            -> normal C6 -> calibrate_delay path
 *            -> *** the first instruction after calibrate_delay returns
 *               is THIS probe ***
 *
 * NO entry pad. This is not a function entry and is not an indirect
 * target: arrival is BL-return fallthrough. landing-pad is not checked on
 * the return. The 76-byte diagnostic core is byte-identical to the T0/T1
 * true-device proven core and to T4/T3/T2 probe cores (T4 is the 76-byte
 * T1 core; T3/T2 are that core after a 4-byte entry pad).
 *
 * Semantics: REACH -> DAIF mask -> 8s CNTPCT register-only delay ->
 * PSCI SYSTEM_RESET (smc #0) -> on ANY unexpected smc return, wfe forever.
 * DESTRUCTIVE DIAGNOSTIC ONLY: it never returns, never continues the
 * overwritten instructions.
 *
 * Register discipline: w0/x0 (PSCI FID), x9, x10, x11, x12, x13, NZCV only.
 * No stack, no loads, no stores, no MMIO, no MMU/EL/TTBR manipulation,
 * PC-relative only, zero runtime relocations.
 */
#ifndef P1B_C_DELAY_DELAY
#error "P1B_C_DELAY_DELAY required"
#endif
#if (P1B_C_DELAY_DELAY) != 8
#error "P1B_C_DELAY_DELAY must be 8 (C_DELAY-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_c_delay_checkpoint
r3_c_delay_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_C_DELAY_DELAY
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
