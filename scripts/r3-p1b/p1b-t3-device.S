/* thyme R3 P1B T3-8 FAIL-CLOSED start_kernel ADDRESS reachability checkpoint.
 *
 * ARCHITECTURE: INLINE. The probe is written directly over the first
 * contiguous instructions of start_kernel in kernel .init.text, i.e. inside
 * code the CPU is ALREADY executing when it arrives. No padding region, no
 * external code cave, no extra mapping claim. The overwritten bytes are real
 * Image content (the function prologue), not padding.
 *
 *   control: ABL -> code1 "b 0x40" -> UNMODIFIED frozen FIX8 trampoline
 *            -> primary_entry (byte-identical to FIX8)
 *            -> record_mmu_state / preserve_boot_args / create_idmap /
 *               init_kernel_el / __cpu_setup / __primary_switch (identical)
 *            -> __enable_mmu: SCTLR_EL1.M=1, TTBR0/TTBR1 installed
 *            -> __primary_switched (ORIGINAL FIX8 bytes restored: the T2
 *               probe is gone) -> init_cpu_task / VBAR_EL1 / BSS clear /
 *               early_fdt_map / init_feature_override / finalise_el2
 *            -> "bl start_kernel"
 *            -> *** the first instruction of start_kernel is THIS probe ***
 *
 * ENTRY PAD. The original first instruction of start_kernel in this build is
 * `paciasp` (0xd503233f), NOT `bti c`. CONFIG_ARM64_BTI_KERNEL does enable
 * -mbranch-protection=pac-ret+bti for C code, but LLVM omits the BTI landing
 * pad for a function whose address is never taken, and start_kernel is
 * reached only by the direct `bl start_kernel` in __primary_switched (a
 * direct branch is not BTI-checked). The T3 probe therefore re-emits
 * `paciasp` verbatim as its first instruction, so the instruction at the
 * start_kernel entry address is bit-for-bit the original one; there is no BTI
 * landing-pad requirement to preserve at this entry
 * (T3_BTI_LANDING_REQUIRED=NO). It is emitted as .inst so the pad cannot
 * depend on any assembler feature flag. The 76-byte diagnostic core that
 * follows is byte-identical to the T0/T1 true-device proven core and to the
 * T2 probe core; the only difference from T2 is the checkpoint ADDRESS and
 * the preserved entry instruction.
 *
 * Semantics: REACH -> DAIF mask -> 8s CNTPCT register-only delay ->
 * PSCI SYSTEM_RESET (smc #0) -> on ANY unexpected smc return, wfe forever.
 * DESTRUCTIVE DIAGNOSTIC ONLY: it never returns, never executes the
 * overwritten prologue, never runs the start_kernel body.
 *
 * Register discipline: w0/x0 (PSCI FID), x9, x10, x11, x12, x13, NZCV only.
 * No stack, no loads, no stores, no MMIO, no MMU/EL/TTBR manipulation,
 * PC-relative only, zero runtime relocations. `paciasp` reads SP as an
 * architectural register and performs no memory access.
 */
#ifndef P1B_T3_DELAY
#error "P1B_T3_DELAY required"
#endif
#if (P1B_T3_DELAY) != 8
#error "P1B_T3_DELAY must be 8 (T3-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_t3_checkpoint
r3_t3_checkpoint:
	.inst	0xd503233f
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_T3_DELAY
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
