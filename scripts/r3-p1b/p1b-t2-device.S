/* thyme R3 P1B T2-8 FAIL-CLOSED __primary_switched reachability checkpoint.
 *
 * ARCHITECTURE: INLINE. The probe is written directly over the first
 * contiguous instructions of __primary_switched in kernel .head.text, i.e.
 * inside executable kernel text that the CPU is ALREADY executing when it
 * arrives. No padding region, no external checkpoint, no extra mapping claim.
 *
 *   control: ABL -> code1 "b 0x40" -> UNMODIFIED frozen FIX8 trampoline
 *            (sha 362d9c6e..., word[8] still "b primary_entry")
 *            -> primary_entry (byte-identical to FIX8: no patch at all)
 *            -> record_mmu_state / preserve_boot_args / create_idmap /
 *               init_kernel_el / __cpu_setup / __primary_switch
 *               (byte-identical to FIX8)
 *            -> __enable_mmu: SCTLR_EL1.M=1, TTBR0/TTBR1 installed
 *            -> create_kernel_mapping / load_ttbr1 init_pg_dir /
 *               __relocate_kernel
 *            -> ldr x8, =__primary_switched ; br x8
 *            -> *** the first instruction of __primary_switched is THIS
 *               probe ***
 *
 * Semantics: REACH -> DAIF mask -> 8s CNTPCT register-only delay ->
 * PSCI SYSTEM_RESET (smc #0) -> on ANY unexpected smc return, wfe forever.
 * DESTRUCTIVE DIAGNOSTIC ONLY: it never returns, never executes the
 * overwritten __primary_switched instructions, never reaches start_kernel.
 *
 * The delay/reset core below is byte-identical to the T0/T1 true-device
 * proven diagnostic core (scripts/r3-p1b/p1b-t1-device.S); only the
 * insertion mechanics differ (T1 branched here from primary_entry, T2 is
 * reached by falling into the natural __primary_switched entry).
 *
 * Register discipline: w0/x0 (PSCI FID), x9, x10, x11, x12, x13, NZCV only.
 * x1/x2/x3 and the callee-saved boot contract x19..x25 are NEVER written.
 * No stack, no loads, no stores, no MMIO, no MMU/EL/TTBR manipulation,
 * PC-relative only, zero runtime relocations.
 */
#ifndef P1B_T2_DELAY
#error "P1B_T2_DELAY required"
#endif
#if (P1B_T2_DELAY) != 8
#error "P1B_T2_DELAY must be 8 (T2-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_t2_checkpoint
r3_t2_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_T2_DELAY
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
