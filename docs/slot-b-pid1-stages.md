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

`35051089708` then rejected the 72-byte do_initcalls prefix because its loop
backedge at `+0x5c` jumps into `+0x3c`. The candidate window is expanded only
to 96 bytes, covering that original branch source as well as its destination,
while staying within the 148-byte function. The same device-proven core still
terminates in its WFE loop; six unreachable NOP words fill the expanded prefix.
All bytes outside the prefix remain frozen. The incoming-branch guard itself
is unchanged, and a regression fixture still rejects a branch from outside
the expanded window. The two pair members differ only in their timer immediate.

INITCALLS public audit `35051568196` and private pack/independent verification
`35051853455` passed. Both boot images are 37380096 B:

| member | boot SHA256 |
| --- | --- |
| INITCALLS8 | `15a9c504d4a44b8596c5d73d002bb8d5e9c5cf50c44fcc0c2a53da89f2cb2fe5` |
| INITCALLS1 | `b07810cf2d8d17b7518d63033c650a8272f89dccee73d2a03e278455a2e6e65f` |

The same preregistered B-only matched-pair protocol applies: 8s first, then
1s only after a valid return and unchanged protected hashes, expected delta
−7s, STRONG <=1s error, SUPPORTED <=2s. A positive proves `smp_init` returned
and driver-core initialization reached main initcall entry; the online CPU
count and initcall completion are not inferred. Freeze observer CI before use.

## INITCALLS pair true-device result

Observer CI `35053398445` passed. INITCALLS8 booted once at 03:53:34.925 UTC
and returned in 35.356176458s; INITCALLS1 booted once at 03:56:49.346 UTC
and returned in 28.379876083s. Delta `-6.976300375s`, error `+0.023699625s`:
**STRONG**. `DO_INITCALLS_ENTRY=PROVEN`; the preceding SMP/topology and
`driver_init` core setup returned. CPU count and actual device-probe success
remain unobserved. Both returns stayed B with retry 7→6. All 16 protected
boot-chain hashes and P15 prefix remained unchanged, and Android A is healthy.
No partition was flashed; each member ran once in RAM.

Next candidate: `console_on_rootfs` entry (`0x1b30da4`), after the main initcall
path and `wait_for_initramfs` returned. This does not prove console opening,
that every driver succeeded, or `/init` execution. The second source caller
is legacy `init_linuxrc`, reached only from later initrd root preparation;
the main PID1 console call precedes `prepare_namespace` in the normal path.

The external-P15-ramdisk override hypothesis was checked before changing any
image: R3 uses its dedicated, embedded RT-D, not the ABL-updated DTB. Linux
unpacks an external initrd only when `initrd_start` is nonzero. The new CI gate
checks the exact frozen DTB's `/chosen` for absence of BOTH initrd address
properties. An external ramdisk in the boot envelope alone is not evidence
that Linux consumes it. No INITRAMFS_FORCE or packing change is made on that
unconfirmed hypothesis.

The first console audit `35054566914` found two ADD-immediate address deltas:
`0x1b30db8` (`0x912c3000`→`0x912c5000`) and `0x1b30dd4`
(`0x91022000`→`0x91024000`). Disassembly and source identify the arguments as
`/dev/console` for `filp_open` and the KERN_ERR initial-console warning for
`_printk`. The new gate must prove these exact two strings at each image's
separate linked address, preserve every other instruction, and resolve both
call targets. No blanket string/address normalization is allowed. Negative
fixtures cover extra code changes and wrong text/addresses; private wrapping
independently verifies the frozen literals. The initrd-source gate now runs
before window auditing and exports its result even if a window is rejected.

Public console audit `35055586198` and private pack/independent verification
`35055709127` passed. CI proved both literal identities, all original window
safety gates, and `runtime_dtb_external_initrd=false`: `/chosen` has only
`bootargs` and `stdout-path`. The external-ramdisk override hypothesis is not
applicable to the R3 DTB path; no packaging workaround is required.

| member | boot SHA256 (37380096 B each) |
| --- | --- |
| CONSOLE8 | `9892a58c7627df78f5fc3acd64926aa054a2c9b6ca1f05ef65e2c0d289fd445d` |
| CONSOLE1 | `c116cf585516f1e6d9835a90ef0324745fd12f84f5d7cb36528e7aa73f2983b1` |

The same B-only 8s/1s protocol applies, with unchanged −7s delta and error
thresholds. A valid first automatic return and unchanged partition readback
are prerequisites for the second member. This is not a USB or userspace test.
