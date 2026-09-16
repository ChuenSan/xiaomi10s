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

## CONSOLE pair true-device result

Observer CI `35056576698` passed. CONSOLE8 booted once at 04:43:21.259 UTC
and returned in 48.255931209s; CONSOLE1 booted once at 04:49:32.400 UTC and
returned in 48.337103709s. Delta `+0.081172500s`, expected `-7s`, error
`+7.081172500s`: **SHIFT_NOT_OBSERVED**. `CONSOLE_ON_ROOTFS_ENTRY=NOT_PROVEN`,
`CONSOLE_OPENED=NOT_PROVEN`, `/init=NOT_PROVEN`. Both automatic returns stayed
B (retry 7→6). All 16 recorded A/B boot-chain hashes and the P15 prefix
matched before/between/after; zero partition flashes. Android A is healthy
(`_a`, `boot_completed=1`, `bootreason=bootloader`). pstore remains empty;
oops has no Linux 6.6 / THYME-R3 marker. Stock 4.19 later reports
`hw_reset reason1 is 0x2` after Android A is already running; that is not a
Mainline panic/console/init proof.

Do not rerun CONSOLE8/CONSOLE1. Absolute ~48s is not an entry proof. The last
proven boundary remains `do_initcalls` entry. Next is isolation of the hang
between that entry and `console_on_rootfs`: initcall levels `pure`→`late`,
then `wait_for_initramfs`. Keep the same frozen FIX8 payload, compact core,
GHA-only composition and B-only RAM protocol. USB, BusyBox userspace and
INITRAMFS_FORCE remain frozen until a later proven boundary requires them.

## First post-pure checkpoint readiness

Public audit `35095344774` resolved `__initcall1_start`'s PREL32 entry to the
unique `fpsimd_init` target at `0xffff800081b33d74` (Image `0x1b33d74`). This
is the first core initcall: a positive pair proves all pure initcalls completed
and this entry was reached, not its body or core-level completion. The target
is 128 bytes, so the 72-byte compact probe stays within the function.

The audit found one word delta at `0x1b33d9c`: ADD `0x913b7421` in the audit
Image versus `0x913b9421` in FIX8. Both ADRP/ADD pairs resolve to the exact
NUL-terminated `arm64/fpsimd:dead` cpuhp state name (`0x1940edd` versus
`0x1940ee5`), and the following call resolves to `__cpuhp_setup_state`.
Only this exact address delta is admitted; all other identity, branch,
relocation and runtime-rewrite gates remain active. Verdict:
`INITCALL_NAME_LITERAL_ADDRESS_DELTA_VERIFIED`.

Private pack and independent verification `35095564792` passed without a
kernel rebuild. Both boots are 37380096 bytes:

| member | boot SHA256 |
| --- | --- |
| PURE8 | `86d5c664e17675cf23322158782f2a0d2b9a7a1f075adc98c51f441ff4612a4b` |
| PURE1 | `08346222366202abf2d033b0f9bc9d3c11ac3ccd806727bf0d17d40dcf0ba57a` |

Observer CI `35095805149` passed. PURE8 booted once at 12:30:36.520 UTC and
returned in `35.017469042s`; PURE1 booted once at 12:32:56.978 UTC and returned
in `27.909857042s`. Delta `-7.107612000s`, error `-0.107612000s`: **STRONG**.
All pure initcalls completed and the first core initcall entry was reached.
The `fpsimd_init` body, core-level completion and every later level remain
unproven.

Both returns stayed B with retry 7→6. All 16 protected boot-chain hashes and
the P15 prefix matched before/between/after; no partition was flashed. Android
A is healthy after recovery. Each member ran exactly once in RAM. Evidence is
in `artifacts/slot-b-pure-pair-20260916/`; do not rerun this pair.

The next source-ordered level is core completion, observed at the first
postcore initcall entry derived from `__initcall2_start`. It must not be
inferred from the PURE result.

## Core-initcall completion checkpoint CI readiness

Public GHA `35102390662` completed the new source/binary audit and independent
reverify without rebuilding the kernel. Exact Linux 6.6.156 source maps pure,
core and postcore to `__initcall0_start..__initcall1_start`,
`__initcall1_start..__initcall2_start` and
`__initcall2_start..__initcall3_start`. The exact vmlinux uses 4-byte PREL32
entries. `__initcall2_start` is VA `0xffff800081d0ab6c`, Image offset
`0x1d0ab6c`; its first word decodes uniquely to `debug_monitors_init` at VA
`0xffff800081b338a8`, Image offset `0x1b338a8`, registered by
`postcore_initcall` in `arch/arm64/kernel/debug-monitors.c`.

The function is exactly 60 bytes. The historical 72-byte compact checkpoint
was rejected as too large, so the accepted inline design preserves the entry
`paciasp` and uses a 56-byte stack/memory-free CNTPCT elapsed-time + PSCI
SYSTEM_RESET core ending exactly at the function boundary. Incoming-interior,
back-edge, relocation, exception-table, alternatives, jump-label, static-call
and KCFI gates pass. One target-specific linked-string ADD difference is
closed as `CORE_INITCALL_NAME_LITERAL_ADDRESS_DELTA_VERIFIED`; both addresses
contain exact `arm64/debug_monitors:starting`, and the call resolves to
`__cpuhp_setup_state`.

CORE8 payload
`1e35411ba4d9bdeb48af47c0269a96b63a9214be5483601a9dfa5f8bdcfcc0a8`
and CORE1 payload
`4ccf9e26edc0a37d2eade6a29c8dd73947b17dde57c0630dc1562616e3cf0704`
differ only at `[0x1b338b5,0x1b338b7)`, instruction 3's delay encoding.
The frozen FIX8 baseline, RT-D, `/init` and initramfs match; all prior probes
are absent. Runtime evidence remains `CORE_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_POSTCORE_INITCALL_ENTRY=NOT_PROVEN`. See
`docs/slot-b-core-initcall-checkpoint.md`.

## Core-initcall private gate freeze

Private pack `35105559604` and independent reverify `35105810959` froze two
boot identities without kernel rebuild. Observer fixtures `35107904900` and
regression `35107904896` passed. Both boots are 37380096 bytes:

| member | boot SHA256 |
| --- | --- |
| CORE8 | `5d7d5b88668e1925e3a79c677c2b630bb81d66135fec2761016de1da52fd7272` |
| CORE1 | `a66c3f7a95e05905f5f65d96cb7f378ccdad9edf33814271425829ce10fe3e6c` |

Extracted payloads match the public pair. Private diff remains 2 bytes at
`[0x1b338b5,0x1b338b7)`, DELAY_CONSTANT_ONLY. Geometry is identical. Each
observer accepts only its full boot SHA and refuses the sibling plus all
older images. Device execution is split: CORE8 first, then wait for user
approval before CORE1. A positive future STRONG pair may prove core-level
completion and first postcore entry, never `debug_monitors_init` body or
later levels. `READY_FOR_R3_SLOT_B_CORE8_DEVICE_CONTROL=YES`.
`READY_FOR_R3_SLOT_B_CORE1_DEVICE_CONTROL=NO`. `DEVICE_OPERATION=NO`.

## CORE8 true-device member A

Observer CI `35107904900` remained the frozen CORE8 full-SHA gate. Healthy
Android A (`_a`, `boot_completed=1`, Magisk su) was confirmed, then
`adb reboot bootloader`, `current-slot=a`, `set_active b`,
`current-slot=b`. Exactly one RAM-only `fastboot boot` of CORE8
`5d7d5b88668e1925e3a79c677c2b630bb81d66135fec2761016de1da52fd7272`
(37380096) ran at 14:45:42.613 UTC. Sending OKAY 0.943s, Booting OKAY
0.220s. Automatic Fastboot B return in `34.961135333s`, retry 7→6.
CORE1 was not placed in any fallback and was not executed.

This freezes `CORE8_MEMBER_A_COMPLETED=YES` and `CORE8_TOTAL=34.961135333s`
only. It does not prove `CORE_INITCALLS_COMPLETED` or
`FIRST_POSTCORE_INITCALL_ENTRY`. Pair delta remains unavailable until a
separately approved CORE1 member. Absolute ~35s must not be treated as a
core-complete hard gate.

Fastboot fetch is unsupported on this bootloader, so Current B 16-chain
hashes and the P15 prefix were re-read from restored Android A. All 16
hashes and prefix `133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34`
matched the pre-CORE8 record. Zero partition flashes; Slot A untouched.
Android A is healthy after `set_active a` + `fastboot reboot`. pstore is
empty (Mainline defconfig has no `CONFIG_PSTORE`; empty is not
counter-evidence). Stock 4.19 later reports `hw_reset reason1 is 0x2`;
that is not a Mainline checkpoint proof.

Evidence: `artifacts/slot-b-core8-20260916/`. Do not rerun CORE8, PURE or
CONSOLE.

## CORE1 device gate review

The read-only `MAINLINE_V2_R3_SLOT_B_CORE1_DEVICE_GATE_REVIEW` reconfirmed the
frozen member-B identity: public payload
`4ccf9e26edc0a37d2eade6a29c8dd73947b17dde57c0630dc1562616e3cf0704`, boot
`a66c3f7a95e05905f5f65d96cb7f378ccdad9edf33814271425829ce10fe3e6c`,
37380096 bytes, pack `35105559604`, reverify `35105810959`. Extracted payload,
checkpoint window, 1-second delay encoding, PSCI FID, geometry, RT-D, `/init`
and initramfs remain verified. No new mismatch was admitted.

The pair still differs only by 2 bytes at `[0x1b338b5,0x1b338b7)`, instruction
3, for `8s → 1s`. CORE1 contains only the first-postcore-entry diagnostic; all
historical probes and the CORE8 delay member are absent. Observer fixtures
`35163693773` and safety regression `35163693772` passed at
`8249c145b0bc7932cb1f893733e11d9fca7e3ae8`; the SUPPORTED branch emits
`STRONGLY_SUPPORTED` without upgrading body or later-stage evidence. The CORE1
full-SHA gate rejects the sibling, all historical candidates, wrong
size, mutations, wrong checkpoint and wrong delay.

The frozen future primary equation is
`PAIR_DELTA=CORE1_TOTAL-34.961135333s`,
`PAIR_ERROR=PAIR_DELTA+7.000000000s`; STRONG is absolute error `<=1.000s` and
SUPPORTED `<=2.000s`. Absolute CORE1 time is secondary. CORE8's result alone
continues to prove no additional reachability.

`READY_FOR_R3_SLOT_B_CORE1_DEVICE_CONTROL=YES`. This review performed no device
operation and authorizes no automatic execution. The next separately approved
stage is `MAINLINE_V2_R3_SLOT_B_CORE1_TRUE_DEVICE_CONTROL`: one CORE1 Slot B
RAM-only boot, with fresh pre/post Current B readback and Android A recovery.
