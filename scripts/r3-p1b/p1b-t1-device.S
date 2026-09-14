/* thyme R3 P1B T1 FAIL-CLOSED primary_entry reachability checkpoint, spliced
 * at T1_CHECKPOINT_OFFSET (the deterministic zero padding after the Image
 * file, before the RT-D trailer). primary_entry's first instruction
 * (bl record_mmu_state) is replaced by "b T1_CHECKPOINT"; from there:
 *   DAIF mask -> 8s CNTPCT register-only delay -> PSCI SYSTEM_RESET (smc #0)
 *   -> on ANY smc return: wfe forever.
 * DESTRUCTIVE DIAGNOSTIC ONLY: it NEVER returns to primary_entry, NEVER
 * executes record_mmu_state, NEVER continues normal Linux. A future positive
 * proves ONLY that the unmodified FIX8 trampoline branch delivered control
 * to the primary_entry address (R2); it does NOT prove normal primary_entry
 * execution (E1 stays NOT_PROVEN).
 * Timer + reset primitives are the T0-proven instruction sequence
 * (p1b-t0-device.S). No x0/DTB dereference, no loads, no stores, no stack,
 * no MMU/EL manipulation, PC-relative only, zero relocations.
 * Clobber registers: w0/x0 (PSCI FID), x9, x10, x11, x12, x13, NZCV.
 * x1/x2/x3 hold the boot contract values and are never written.
 */
#ifndef P1B_T1_DELAY
#error "P1B_T1_DELAY required"
#endif
#if (P1B_T1_DELAY) != 8
#error "P1B_T1_DELAY must be 8 (T1-8 device candidate only)"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_t1_checkpoint
r3_t1_checkpoint:
	msr	daifset, #0xf
	isb
	mrs	x9, cntfrq_el0
	movz	x10, #P1B_T1_DELAY
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
