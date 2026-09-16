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

Actions `35049158504` isolated exactly one ADD-immediate word at `0x1b466fc`:
bundle `0x912dc000`, frozen `0x912de000`. `35049462400` confirmed that the
ADRP/ADD pair points to `0x1a30b70` versus `0x1a30b78`, respectively, and BOTH
addresses hold exactly `\\x016smp: Bringing up secondary CPUs ...\\n\\0`.
The difference is the log string's linked address, not different SMP logic.

The new audit accepts only this exact pair of ADD encodings, unchanged
surrounding instructions, the exact source string at both derived addresses,
and the independently resolved `_printk` call. Every other window must remain
byte-exact. The manifest explicitly records
`SMP_PRINTK_LITERAL_ADDRESS_DELTA_VERIFIED`, never claims byte equality.
Negative fixtures reject any other instruction, offset or string drift;
private verification also checks the frozen literal. Incoming branches,
relocations and runtime rewrite gates remain mandatory. This does not change
any runtime code outside the new diagnostic window or rebuild the kernel.

Public SMP pair audit `35049745503` and private pack/independent verification
`35049851963` passed. Both boot images are 37380096 B:

| member | boot SHA256 |
| --- | --- |
| SMP8 | `915214b436376189a4bd871b574567d07a3884edf9706a9c6971829912ead689` |
| SMP1 | `fbdb4ef8cddf228977953f5371e65e7134e121867f4b932637546fa43bfb2950` |

Use the same preregistered B-only matched-pair protocol and thresholds as
FREE. SMP1 is conditional on a valid SMP8 return plus unchanged protected
partition hashes. A positive proves pre-SMP initialization reached the
`smp_init` entry, not secondary CPU bring-up or `/init`. The updated observer
must pass CI before either device operation.

## SMP pair true-device result

Observer CI `35050078930` passed before testing. SMP8 booted once at
03:01:04.771 UTC and returned in 35.174554375s; SMP1 booted once at
03:03:12.758 UTC and returned in 28.200887000s. Delta `-6.973667375s`,
error `+0.026332625s`: **STRONG**. `SMP_INIT_ENTRY=PROVEN`.
Pre-SMP setup and its initcalls reached this boundary. The SMP body and
secondary CPU count remain unproven. All 16 recorded A/B boot-chain hashes
and P15 prefix matched before/between/after; no partition writes. Both
returns were B, retry 7→6, and Android A is healthy after readback.

Next is `do_basic_setup` entry (`0xffff800081b311a8`), rederived in Actions.
The matching `kernel_init_freeable` disassembly calls it after `smp_init`,
`sched_init_smp`, `workqueue_init_topology` and `page_alloc_init_late`.
A positive proves these functions returned, NOT that all secondary CPUs
came online. Driver initcalls, initramfs readiness and `/init` remain separate.
Use the same 8s/1s pair protocol, safety/context gates and unchanged thresholds.

Audit `35050781222` rejected `do_basic_setup`: it is only 40 bytes, so a
72-byte probe would cross into `do_initcalls`. Window bytes matched exactly;
this was a diagnostic geometry rejection, not a device failure. The extent
gate remains unchanged. Its disassembly shows `cpuset_init_smp`, `driver_init`
and `init_irq_proc` followed by `bl do_initcalls` at `0x1b311c0`.

The next candidate is therefore `do_initcalls` entry at `0x1b311d0`. A positive
proves the preceding SMP/topology and driver-core setup returned, not the main
initcall levels, initramfs or `/init`. No do_basic_setup device test occurred.
