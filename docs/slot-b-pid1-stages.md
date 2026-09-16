# Slot B post-PID1 initialization

KINIT8/KINIT1 proved PID1 entry. Continue on the frozen normal FIX8 payload;
no earlier checkpoint is left active. All assembly, composition, audits and
boot wrapping are Actions-only, reusing kernel bundle `35040148509`.

## Source order and proof boundaries

Linux `init/main.c` and the matching Actions-exported function disassembly:

1. `kernel_init` waits for `kthreadd_done`, then calls `kernel_init_freeable`.
2. `kernel_init_freeable` performs memory/task setup, `smp_prepare_cpus`,
   workqueue/RCU setup and pre-SMP initcalls, then calls `smp_init`.
3. `smp_init` returns before scheduler topology, driver initcalls,
   `wait_for_initramfs`, console setup and rootfs access.

A positive entry checkpoint proves the preceding path, never its overwritten
function body or `/init`. Next-stage device execution depends on the actual
previous result; this is not an automatically executed device matrix.

## FREE8/FREE1 frozen pair

Target `kernel_init_freeable` VA `0xffff800081b3103c`, Image offset `0x1b3103c`.
72-byte inline window, original landing word preserved, compact core already
validated by the KINIT pair. Public `35047929982`, private pack plus independent
verify `35048049205`; only delay-immediate bytes differ. Both boots 37380096 B.

| member | boot SHA256 |
| --- | --- |
| FREE8 | `9c294a544cf1e178b7f638a40901fbddf97e3556ff57f18646114cd2d921be93` |
| FREE1 | `8cf15312cd5803d33c8e889c5a87ad22edaa050da5455a92e68c37adfffffa19` |

Both originate from healthy Android A → ADB bootloader → verified B. Boot
images run in RAM; B stays stock V14 vendor/DTBO plus P15 recovery. A, vbmeta
and firmware are never flashed. Each member executes once. FREE1 requires a
valid automatic B Fastboot return from FREE8 and unchanged protected partition
hashes. Primary delta is FREE1−FREE8 = −7s; abs(error)<=1s STRONG, <=2s
SUPPORTED. No return/manual recovery invalidates the pair and stops automatic
progression. Absolute timing alone is not proof. A positive proves the
`kthreadd_done` wait completed, not SMP or `/init`.

## FREE pair true-device result

Observer CI `35048364342` passed. FREE8 booted once at 02:34:06.397 UTC and
returned in 35.151693708s. FREE1 booted once at 02:36:24.425 UTC and returned
in 28.236296167s. Delta `-6.915397541s`, error `+0.084602459s`: **STRONG**.
`KERNEL_INIT_FREEABLE_ENTRY=PROVEN`; `KTHREADD_DONE_WAIT_COMPLETED=PROVEN`.
Its body, SMP and `/init` remain unproven. Both returns stayed B (retry 7→6).
All 16 protected boot-chain hashes and P15 prefix matched before/between/after;
zero partition flashes. Android A is healthy. Do not rerun this completed pair.

## SMP entry audit hold

Run `35048719320` rejected `smp_init` before producing a payload:
`TARGET_WINDOW_DIFFERS_FROM_AUDIT_IMAGE`. The bundle and frozen payload agree
at earlier checkpoints, but not this proposed overwrite window. The cause
must be resolved from exported disassembly and exact word differences, not
by disabling the identity gate. No SMP device test or private pack ran.
Automatic old-stage composition is now disabled; explicit Actions dispatch
selects each new diagnostic while source/observer regression CI stays active.
