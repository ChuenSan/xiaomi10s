/* thyme R3 P1B T1 gap probe, spliced into the first free byte after the
 * Image file (the payload gap, inside the 2MiB-aligned trailer geometry).
 * primary_entry's first instruction (bl record_mmu_state) is replaced by a
 * branch here; the probe then:
 *   controlled CNTPCT delay -> PSCI SYSTEM_RESET (smc #0) -> wfe spin.
 * Register discipline: x9-x15 only; x0-x3 are untouched so the probe cannot
 * disturb the boot protocol state it is measuring. Physical mode (MMU off,
 * no stack, no stores, no relocations). DIAGNOSTIC ONLY.
 * P1B_PROBE_DELAY is injected by p1b-panic-checkpoint-isolation.py.
 */
#ifndef P1B_PROBE_DELAY
#error "P1B_PROBE_DELAY required"
#endif
#if (P1B_PROBE_DELAY) <= 0 || (P1B_PROBE_DELAY) > 0xffff
#error "P1B_PROBE_DELAY out of range"
#endif

.section .text, "ax", @progbits
.p2align 2
.global r3_t1_probe
r3_t1_probe:
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
3:
	wfe
	b	3b
