/* R3 P1 entry-state probe. Registers only: no stack, no memory read/write,
 * no absolute address, no relocations. CurrentEL first; SCTLR_EL1 read only
 * on the EL1 path, SCTLR_EL2 only on the EL2 path; unexpected EL reads no
 * SCTLR at all. Bit positions verified against linux-6.6
 * arch/arm64/include/asm/sysreg.h: SCTLR_ELx_M=BIT(0), SCTLR_ELx_C=BIT(2);
 * arch/arm64/include/asm/ptrace.h: CurrentEL_EL1=(1<<2)=4, EL2=(2<<2)=8.
 * Preregistered STATE->DELAY mapping (4s buckets):
 *   EL1 M0 C0=4s  EL1 M0 C1=8s  EL1 M1 C0=12s EL1 M1 C1=16s
 *   EL2 M0 C0=20s EL2 M0 C1=24s EL2 M1 C0=28s EL2 M1 C1=32s
 *   unexpected EL=36s
 * Termination: PSCI SYSTEM_RESET 0x84000009 via SMC, same as P0.
 */
.section .text, "ax", @progbits
.p2align 2
.global _start
_start:
	b	probe_entry
	b	probe_entry
	.quad	0x80000
	.quad	0x2220000
	.quad	0xa
	.quad	0
	.quad	0
	.quad	0
	.word	0x644d5241
	.word	0

.org 0x40
probe_entry:
	isb
	mrs	x1, CurrentEL
	cmp	x1, #8
	b.eq	el2_state
	cmp	x1, #4
	b.eq	el1_state
	b	unexpected_el

el1_state:
	movz	x5, #0
	mrs	x2, sctlr_el1
	b	decode_state

el2_state:
	movz	x5, #4
	mrs	x2, sctlr_el2
	b	decode_state

unexpected_el:
	movz	x5, #8
	b	encode_delay

decode_state:
	movz	x6, #0
	tbz	x2, #0, 1f
	movz	x6, #2
1:
	tbz	x2, #2, 2f
	add	x6, x6, #1
2:
	add	x5, x5, x6

encode_delay:
	add	x5, x5, x5
	add	x5, x5, x5
	add	x5, x5, #4
	mrs	x6, cntfrq_el0
	mul	x5, x6, x5
	isb
	mrs	x7, cntpct_el0
5:
	isb
	mrs	x8, cntpct_el0
	sub	x9, x8, x7
	cmp	x9, x5
	b.hs	6f
	yield
	b	5b
6:
	movz	w0, #0x0009
	movk	w0, #0x8400, lsl #16
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	smc	#0
7:
	wfe
	b	7b
