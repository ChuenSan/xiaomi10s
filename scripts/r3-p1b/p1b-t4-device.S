/* thyme R3 P1B T4-8 FAIL-CLOSED post-stage C checkpoint.
 *
 * ARCHITECTURE: INLINE. Mid-function fallthrough inside start_kernel
 * .init.text after the selected C-stage call returns. No padding, no
 * external cave, no T1 0x2230000 mapping claim. The CPU is already
 * executing this VA (MMU-on, EL1).
 *
 * Selected stage (GHA re-derives; preferred):
 *   C6 parse_args("Booting kernel") COMPLETE = first insn AFTER that BL.
 *
 * Fallback (only if C6 cannot close):
 *   C3 setup_arch RETURN = first insn AFTER the setup_arch BL.
 *
 *   control: ABL -> code1 "b 0x40" -> UNMODIFIED frozen FIX8 trampoline
 *            -> primary_entry / head.S / __primary_switched (FIX8 bytes;
 *               T2 probe gone) -> bl start_kernel
 *            -> start_kernel ENTRY is ORIGINAL FIX8 paciasp + prologue
 *               (T3 probe gone)
 *            -> normal start_kernel body through the selected call
 *            -> *** the first instruction after that call returns is THIS
 *               probe ***
 *
 * NO entry pad. This is not a function entry and is not an indirect
 * target: arrival is BL-return fallthrough. BTI is not checked on the
 * return. The 76-byte diagnostic core is byte-identical to the T0/T1
 * true-device proven core and to T3 probe[4:80] / T2 probe[4:80].
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
#ifndef P1B_T4_DELAY
#error "P1B_T4_DELAY required"
#endif
#if (P1B_T4_DELAY) != 8
#error "P1B_T4_DELAY must be 8 (T4-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_t4_checkpoint
r3_t4_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_T4_DELAY
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
