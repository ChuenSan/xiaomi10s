# Slot B rest_init checkpoint

## Recovered evidence

The user restored Fastboot after RESET8's no-return. Product/unlocked matched;
slot remained B and B retry count remained 6 (same as before RESET8). Selecting
the untouched Android A restored ADB/root. All 16 recorded A/B boot-chain full
hashes, plus the P15 boot prefix, match the post-preparation baseline.

Pstore remains empty. OEM oops record 1253 contains only the stock P15 control:
`Run /init` at 1.419841s, restart at 16.420051s (15.000210s difference).
No Mainline trace is present. Logdump/rawdump match the older baseline. These
are not evidence that Mainline never ran or that any particular reset cause
was responsible. RESET8/RESET1 are not retried.

## Next controlled question

Does the FIX8 normal kernel path reach `rest_init()` after `calibrate_delay()`?
Linux `init/main.c` calls `arch_call_rest_init()` at the end of `start_kernel`;
the arm64 weak implementation calls `rest_init`. This entry precedes kernel
thread creation, SMP bring-up, driver initcalls and `/init` execution.

The checkpoint reuses the exact 76-byte, device-proven 8s CNTPCT + PSCI reset
core, preceded by the unchanged original PAC/BTI entry word. It is composed
from frozen FIX8, not from the RESET8-instrumented payload. Only the audited
entry window changes; trampoline, RT-D, initramfs and all other bytes remain
frozen. All compilation, composition and binary checks are GitHub Actions only.

A positive shows entry reachability and the preceding normal start_kernel
path, not rest_init's body or a completed Linux boot. A missing return is
inconclusive and requires recovery; never execute a second blind boot.

## Audit and reuse

The prior release artifacts omitted vmlinux. This Actions workflow therefore
builds one matching audit kernel and preserves Image, vmlinux, System.map,
configuration and hashes as `thyme-slot-b-kernel-audit-bundle`. Subsequent
checkpoint audits consume that bundle without rebuilding the kernel.

The new branch scan explicitly adds `_text` to Image offsets and checks B/BL,
B.cond, CBZ/CBNZ and TBZ/TBNZ. The legacy T3 scanner mixes offset-space PCs with
VA-space windows and its disassembly confirmation excludes several branch
families; it is not used here. Unit tests cover the high-VA case and backward
branches. Runtime table extraction fails closed; alternative instruction
ranges are checked for overlap, not only starting addresses.

The selected function's VA, extent, section, original instructions and frozen
bytes must agree. Interior symbols, incoming branches, literals, relocations,
exception/alternative/jump/static-call records are checked before emission.
OEM boot wrapping stays in private Actions. Slot B retains stock V14 + P15
recovery. Before a device test, freeze the new boot SHA and extend the B-only
observer allowlist in CI. No Slot A, vbmeta or firmware flash is involved.
