/* Read a registered device's first two name bytes; never resume the worker. */
.section .text, "ax", @progbits
.p2align 2
.global deferred_name_checkpoint
deferred_name_checkpoint:
    msr daifset, #0xf
    cbz x20, invalid
    ldr x8, [x20]
    cbz x8, invalid
    ldrb w9, [x8]
    cbz w9, invalid
    ldrb w8, [x8, #NAME_OFFSET]
#if CODE_KIND == 0
    mov x8, #7
#elif CODE_KIND == 1
    mov x8, #0
#elif CODE_KIND == 2
    ubfx x8, x8, #0, #4
#elif CODE_KIND == 3
    ubfx x8, x8, #4, #4
#else
#error Unsupported CODE_KIND
#endif
    b have_code
invalid:
    mov x8, #16
have_code:
    add x8, x8, #1
    mrs x9, cntfrq_el0
    mul x10, x9, x8
    mrs x11, cntpct_el0
1:
    isb
    mrs x12, cntpct_el0
    sub x13, x12, x11
    cmp x13, x10
    b.lo 1b
    movz w0, #0x0009
    movk w0, #0x8400, lsl #16
    smc #0
2:
    wfe
    b 2b
