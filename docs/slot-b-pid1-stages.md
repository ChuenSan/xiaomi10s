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
operation and authorized the separately approved
`MAINLINE_V2_R3_SLOT_B_CORE1_TRUE_DEVICE_CONTROL` stage recorded below.

## CORE1 true-device member B

The exact frozen CORE1 boot
`a66c3f7a95e05905f5f65d96cb7f378ccdad9edf33814271425829ce10fe3e6c`
(37380096 bytes) passed the observer full-SHA gate and ran exactly once via
RAM-only `fastboot boot` on confirmed Slot B. Sending was OKAY in 0.931s and
Booting was OKAY in 0.222s. It automatically returned to Fastboot B in
`27.878020583s`, retry 7→6; no manual recovery was used.

The frozen member-A reference remains `CORE8_TOTAL=34.961135333s`.
`PAIR_DELTA=-7.083114750s`, expected `-7.000000000s`,
`PAIR_ERROR=-0.083114750s`, and `ABS_PAIR_ERROR=0.083114750s`. The primary
matched-delay verdict is **STRONG**. Absolute CORE1 timing was not used as the
proof criterion.

This proves `CORE_INITCALLS_COMPLETED=PROVEN` and
`FIRST_POSTCORE_INITCALL_ENTRY=PROVEN`. It does not prove the overwritten
`debug_monitors_init` body. `FIRST_POSTCORE_INITCALL_BODY`, postcore and later
initcall completion, `wait_for_initramfs`, console and `/init` remain
`NOT_PROVEN`; USB remains `FROZEN`.

All 16 boot-chain hashes and the P15 prefix matched before and after the test.
Current B remains `STOCK_V14_VENDOR_DTBO_PLUS_PROVEN_P15_RECOVERY`; Android A
was restored healthy (`_a`, `boot_completed=1`, root, stock 4.19.157-perf).
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `EXPERIMENTAL_BOOTS=1`. CORE8,
CORE1, PURE and CONSOLE reruns are forbidden. Evidence:
`artifacts/slot-b-core1-20260916/`.

Final gate: `MAINLINE_V2_R3_SLOT_B_CORE_INITCALLS_COMPLETED_PROVEN`.

## Postcore-initcall completion checkpoint CI readiness

Public GHA `35169202296` at
`88b67da2d70a2a57949f13457a0a460de2649270` completed source audit, exact
PREL32 table decode, target audit, public 8s/1s candidate preparation and
independent static reverify without a kernel rebuild. It confirmed:

- `__initcall2_start=0xffff800081d0ab6c`
- `__initcall3_start=0xffff800081d0ac48`
- `__initcall4_start=0xffff800081d0ae0c`
- first arch initcall `reserve_memblock_reserved_regions` at
  `0xffff800081b33f60` / Image `0x1b33f60`, from
  `arch/arm64/kernel/setup.c`

The target is `.init.text`, 324 bytes, entry `paciasp`. The 60-byte checkpoint
stays inside the function; the target window is byte-exact against frozen FIX8.
No prior literal-address exception was generalized. Incoming-branch,
relocation and runtime-rewrite gates remain enabled and passed.

POSTCORE8 payload
`537a021f6278130957fa666f32421d4f624e84803f00075e3ab2001b8eb9e98b`
and POSTCORE1 payload
`3a4b50c956413dabfd739181ca1ed19aca618002e0292782bf02b271ac9cd59f`
differ only at `[0x1b33f6d,0x1b33f6f)`, instruction 3's delay encoding.
Expected future delta is `-7.000s`; STRONG is `<=1.000s` absolute error and
SUPPORTED `<=2.000s`.

This CI gate does not change runtime evidence:
`POSTCORE_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_ARCH_INITCALL_ENTRY=NOT_PROVEN`. No private pack, boot image or device
operation occurred. Final gate:
`MAINLINE_V2_R3_SLOT_B_POSTCORE_INITCALLS_CHECKPOINT_CI_READY`. This public
CI gate authorized no device operation.

## Postcore-initcall private gate freeze

Private pack `35170737800` and independent reverify-only `35170837546` froze
the POSTCORE8/POSTCORE1 boot members without kernel rebuild or payload
regeneration. Both are 37380096 bytes:

| member | boot SHA256 |
| --- | --- |
| POSTCORE8 | `141d67931f8792036119c131d93ffa74649af2c6c44d086b489851230075355c` |
| POSTCORE1 | `4762a9fd29e109affb1c8864247887334508d9af2d6b183b7bf0200a05b697f1` |

Extracted payloads exactly match public run `35169202296`. The private pair
still differs only by two delay bytes at `[0x1b33f6d,0x1b33f6f)`, and all
geometry is identical. Observer fixtures `35170993710` and CORE observer
regression `35170993608` passed with separate full-SHA gates.

Execution is split and ordered POSTCORE8 then POSTCORE1, one member per
true-device stage. POSTCORE8 alone cannot advance runtime evidence. POSTCORE1
remains blocked until POSTCORE8's result is frozen and the user separately
approves member B. This round performed no device operation.

The former readiness gate was
`READY_FOR_R3_SLOT_B_POSTCORE8_DEVICE_CONTROL=YES` and
`READY_FOR_R3_SLOT_B_POSTCORE1_DEVICE_CONTROL=NO`. The separately approved
member-A round is now complete.

## POSTCORE8 true-device result

Exactly one identity-gated POSTCORE8 RAM boot used frozen boot SHA256
`141d67931f8792036119c131d93ffa74649af2c6c44d086b489851230075355c`
(size 37380096). Sending and Booting were OKAY in 0.923s and 0.221s.
Automatic Fastboot B return occurred at `POSTCORE8_TOTAL=34.936234167s`, with
retry 7→6 and no manual recovery. Current B's 16-chain hashes and P15 prefix
matched before and after. Android A was restored healthy. Partition image
writes were zero and Slot A was not written.

This records `POSTCORE8_MEMBER_A_COMPLETED=YES` only. POSTCORE1 was not run,
so `PAIR_DELTA=NOT_AVAILABLE` and `PAIR_VERDICT=PENDING_POSTCORE1`.
`POSTCORE_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_ARCH_INITCALL_ENTRY=NOT_PROVEN`; body completion and all later stages
remain NOT_PROVEN. POSTCORE1 remains blocked pending a no-device gate review
and separate approval.

The member-A gate remains
`MAINLINE_V2_R3_SLOT_B_POSTCORE8_MEMBER_A_COMPLETED`; evidence is under
`artifacts/slot-b-postcore8-20260917/`.

## POSTCORE1 device gate review

No-device GHA review froze `POSTCORE8_TOTAL=34.936234167s`. Reverify-only run
`35174714051` reconfirmed POSTCORE1 boot
`4762a9fd29e109affb1c8864247887334508d9af2d6b183b7bf0200a05b697f1`
(size 37380096), extracted public payload
`3a4b50c956413dabfd739181ca1ed19aca618002e0292782bf02b271ac9cd59f`,
target/window, preserved `paciasp`, 1s CNTPCT/PSCI/WFE semantics, RT-D,
`/init`, initramfs and P15/OEM envelope. No build, repack or regeneration ran.
The pair remains two-byte `DELAY_CONSTANT_ONLY` at
`[0x1b33f6d,0x1b33f6f)`, with identical geometry and POSTCORE1 as the only
active diagnostic.

Observer review `35174717152` passed the exact POSTCORE1 full-SHA gate and all
negative identities. Observer behavior is unchanged from readiness commit
`66d93d314ac6c4540475f34bd207c036ddc793bd`; prior CORE regression
`35170993608` remains valid.

The future primary equation is
`POSTCORE1_TOTAL-34.936234167s`, expected `-7.000000000s`; STRONG is absolute
error `<=1.000s`, SUPPORTED `<=2.000s`. POSTCORE8 cannot be rerun and absolute
POSTCORE1 timing cannot substitute for the pair. Runtime evidence remains
unchanged.

The former readiness gate was
`READY_FOR_R3_SLOT_B_POSTCORE1_DEVICE_CONTROL=YES`. The separately approved
member-B round is now complete.

## POSTCORE1 true-device result

Exactly one identity-gated POSTCORE1 RAM boot used frozen boot SHA256
`4762a9fd29e109affb1c8864247887334508d9af2d6b183b7bf0200a05b697f1`
(size 37380096). Sending and Booting were OKAY in 0.924s and 0.221s.
Automatic Fastboot B return occurred at `POSTCORE1_TOTAL=27.996538750s`, with
retry 7→6 and no manual recovery. Against frozen
`POSTCORE8_TOTAL=34.936234167s`, `PAIR_DELTA=-6.939695417s`,
`PAIR_ERROR=+0.060304583s`, `ABS_PAIR_ERROR=0.060304583s`: **STRONG**.
Therefore `POSTCORE_INITCALLS_COMPLETED=PROVEN` and
`FIRST_ARCH_INITCALL_ENTRY=PROVEN`.

The first arch body, later initcall levels, `wait_for_initramfs`, console,
`/init` and Linux full boot remain NOT_PROVEN; USB remains FROZEN. Current B's
16-chain hashes and P15 prefix matched before and after. Android A was restored
healthy. Partition image writes were zero and Slot A was not written.
POSTCORE8 and POSTCORE1 reruns are forbidden. Evidence:
`artifacts/slot-b-postcore1-20260917/`.

Final gate: `MAINLINE_V2_R3_SLOT_B_POSTCORE_INITCALLS_COMPLETED_PROVEN`.
POSTCORE8 and POSTCORE1 reruns remain forbidden. See
`docs/slot-b-postcore-initcall-checkpoint.md`.

## Arch-initcall completion checkpoint CI readiness

Public GHA `35182765631` at `fa4be7884cd91902ba22fc50bebc15a5f47cf8d2`
completed source audit, exact PREL32 table decode, target audit, public 8s/1s
candidate preparation and independent static reverify without a kernel rebuild.
It confirmed:

- `__initcall3_start=0xffff800081d0ac48`
- `__initcall4_start=0xffff800081d0ae0c`
- `__initcall5_start=0xffff800081d0b0d4`
- first subsys initcall `topology_init` at `0xffff800081b346fc` / Image
  `0x1b346fc`, from `arch/arm64/kernel/setup.c`

The target is `.init.text`, 188 bytes, entry `paciasp`. The 60-byte diagnostic
would leave the loop back-edge `+0x9c → +0x38` entering overwrite interior, so
the accepted window is 160 bytes with 100 NOP bytes after the 56-byte CNTPCT
PSCI core. The 160-byte window is byte-exact against frozen FIX8. No prior
literal-address exception was generalized. Incoming-branch, relocation and
runtime-rewrite gates remain enabled and passed.

ARCH8 payload
`feb46bb3da436c00ac54ee7898e9b1789a11f30878eb8859a2fcecf719d9cad5`
and ARCH1 payload
`efa7cc1c43302fd93872d905352f5737bd388aa698a9383b5d929e98223d2fc1`
differ only at `[0x1b34709,0x1b3470b)`, instruction 3's delay encoding.
Expected future delta is `-7.000s`; STRONG is `<=1.000s` absolute error and
SUPPORTED `<=2.000s`.

This CI gate does not change runtime evidence:
`ARCH_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_SUBSYS_INITCALL_ENTRY=NOT_PROVEN`. No private pack, boot image or device
operation occurred. Final gate:
`MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_CHECKPOINT_CI_READY`.
`READY_FOR_ARCH_INITCALLS_PRIVATE_GATE=YES`. This public CI gate authorized no
device operation.

## Arch-initcall private gate freeze

Private pack `35185168680` and independent reverify-only `35185358880` froze
the ARCH8/ARCH1 boot members without kernel rebuild or payload regeneration.
Both are 37380096 bytes:

| member | boot SHA256 |
| --- | --- |
| ARCH8 | `7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d` |
| ARCH1 | `f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113` |

Extracted payloads exactly match public run `35182765631`. The private pair
still differs only by two delay bytes at `[0x1b34709,0x1b3470b)`, the 160-byte
window remains EXACT, and 60-byte topology_init probes stay rejected. Observer
fixtures `35185723809`, CORE observer regression `35185723784` and POSTCORE
observer `35185723808` passed with separate full-SHA gates plus the 160-byte
geometry.

Execution is split and ordered ARCH8 then ARCH1, one member per true-device
stage. ARCH8 alone cannot advance runtime evidence. ARCH1 remains blocked until
ARCH8's result is frozen and the user separately approves member B. This round
performed no device operation.

The former readiness gate was `READY_FOR_R3_SLOT_B_ARCH8_DEVICE_CONTROL=YES`
and `READY_FOR_R3_SLOT_B_ARCH1_DEVICE_CONTROL=NO`. The separately approved
member-A round is now complete.

## ARCH8 true-device result

Exactly one identity-gated ARCH8 RAM boot used frozen boot SHA256
`7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d`
(size 37380096). Sending and Booting were OKAY in 0.928s and 0.222s.
Automatic Fastboot B return occurred at `ARCH8_TOTAL=34.99866775s`, with retry
7→6 and no manual recovery. The 160-byte topology_init window and 60-byte
rejection remained the frozen identity. Current B's 16-chain hashes and P15
prefix matched before and after. Android A was restored healthy. Partition
image writes were zero and Slot A was not written.

This records `ARCH8_MEMBER_A_COMPLETED=YES` only. ARCH1 was not run, so
`PAIR_DELTA=NOT_AVAILABLE` and `PAIR_VERDICT=PENDING_ARCH1`.
`ARCH_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_SUBSYS_INITCALL_ENTRY=NOT_PROVEN`; body completion and all later stages
remain NOT_PROVEN. ARCH1 remains blocked pending a no-device gate review and
separate approval.

The member-A gate is `MAINLINE_V2_R3_SLOT_B_ARCH8_MEMBER_A_COMPLETED`; evidence
is under `artifacts/slot-b-arch8-20260917/`.

## ARCH1 device gate review

No-device GHA review froze `ARCH8_TOTAL=34.99866775s`. Reverify-only run
`35187716061` reconfirmed ARCH1 boot
`f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113`
(size 37380096), extracted public payload
`efa7cc1c43302fd93872d905352f5737bd388aa698a9383b5d929e98223d2fc1`,
target/window, preserved `paciasp`, 160-byte CFG covering `+0x9c → +0x38`,
60-byte rejection, 1s CNTPCT/PSCI/WFE semantics, RT-D, `/init`, initramfs and
P15/OEM envelope. No build, repack or regeneration ran. The pair remains
two-byte `DELAY_CONSTANT_ONLY` at `[0x1b34709,0x1b3470b)`, with identical
geometry and ARCH1 as the only active diagnostic.

Observer review `35187718697` passed the exact ARCH1 full-SHA gate, 160-byte
geometry and all negative identities. Observer behavior is unchanged from
readiness commit `fb4ab8d1548d8644518ed143eda36f10609f75d1`; CORE review
`35187721522` and POSTCORE review `35187723891` remain valid.

The future primary equation is `ARCH1_TOTAL-34.99866775s`, expected
`-7.000000000s`; STRONG is absolute error `<=1.000s`, SUPPORTED `<=2.000s`.
ARCH8 cannot be rerun and absolute ARCH1 timing cannot substitute for the pair.
Runtime evidence remains unchanged.

Final gate: `READY_FOR_R3_SLOT_B_ARCH1_DEVICE_CONTROL=YES`. This review
performed no device operation. The separately approved member-B round is now
complete.

## ARCH1 true-device result

Exactly one identity-gated ARCH1 RAM boot used frozen boot SHA256
`f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113`
(size 37380096). Sending and Booting were OKAY in 0.921s and 0.221s.
Automatic Fastboot B return occurred at `ARCH1_TOTAL=27.979913459s`, retry
7→6, no manual recovery. The 160-byte topology_init window and 60-byte
rejection remained the frozen identity. Current B's 16-chain hashes and P15
prefix matched before and after. Android A was restored healthy. Partition
image writes were zero and Slot A was not written. ARCH8 was not rerun.

Pair calculation used the frozen member-A total only:
`ARCH8_TOTAL=34.99866775s`, `ARCH1_TOTAL=27.979913459s`,
`PAIR_DELTA=-7.018754291s`, `EXPECTED=-7.000000000s`,
`PAIR_ERROR=-0.018754291s`, `ABS_PAIR_ERROR=0.018754291s`.
`ARCH_PAIR_VERDICT=STRONG`. Absolute ARCH1 timing is descriptive only.

Runtime upgrade: `ARCH_INITCALLS_COMPLETED=PROVEN` and
`FIRST_SUBSYS_INITCALL_ENTRY=PROVEN`. Body completion, later initcall levels,
console, `/init` and USB remain NOT_PROVEN/FROZEN. ARCH8 and ARCH1 reruns are
forbidden. Evidence: `artifacts/slot-b-arch1-20260917/`.

Final gate: `MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_COMPLETED_PROVEN`.
Recommended next, only after explicit user approval:
`MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_CHECKPOINT_CI_AUDIT`. See
`docs/slot-b-arch-initcall-checkpoint.md`.

## Subsys-initcall completion checkpoint CI

Public GHA `35193200415` at `06f567b7f2f8c207862a937a1418fd8c30b44f7c`
completed source audit and exact PREL32 table decode without a kernel rebuild.
It confirmed:

- `__initcall4_start=0xffff800081d0ae0c`
- `__initcall5_start=0xffff800081d0b0d4`
- next linker boundary `__initcallrootfs_start=0xffff800081d0b1a4`
- fs runtime end `__initcall6_start=0xffff800081d0b1a8`
- first fs initcall `create_debug_debugfs_entry` at `0xffff8000800149e0` /
  Image `0x149e0`, from `arch/arm64/kernel/debug-monitors.c`

The target is `.text`, 56 bytes, entry `paciasp`, unique table decode,
`fs_initcall(create_debug_debugfs_entry)`. CFG is a straight line with no
internal or back-edge. A 60-byte inline overwrite is rejected. Public GHA
`35195817696` at `e201a8d74bf94c3b9e9014ee91dfe952d17ad027` selected Design A:
preserved `paciasp` plus a 52-byte core that is the proven 56-byte CNTPCT/PSCI
sequence without `msr daifset`. Total 56 bytes, function-range safe. One ADD
immediate at `0x149f0` is closed as
`SUBSYS_FS_NAME_LITERAL_ADDRESS_DELTA_VERIFIED` to identical `debug_enabled`.
SUBSYS8 payload
`22400cb378098ce32ef77698de552e8a3690ebda0f377cacc630d69fa0f6d108` and
SUBSYS1 payload
`c9738f1043c4467b66f2f63305ec20c17b2e648fdd9802fda07e8321e37d5194`
differ only at `[0x149e9,0x149eb)`, instruction 2. Independent reverify
passed. Runtime evidence is unchanged:
`SUBSYS_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_FS_INITCALL_ENTRY=NOT_PROVEN`. No private pack or device operation.
Final gate: `MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_CHECKPOINT_CI_READY`.
`READY_FOR_SUBSYS_INITCALLS_PRIVATE_GATE=YES`.
The separately approved private-gate stage is now complete.

## Subsys-initcall private gate freeze

Private pack `35197516266` and independent reverify-only `35197852552` froze
the SUBSYS8/SUBSYS1 boot members without kernel rebuild or payload
regeneration. Both are 37380096 bytes:

| member | boot SHA256 |
| --- | --- |
| SUBSYS8 | `e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1` |
| SUBSYS1 | `df14e7bcdf409deeeede70d7217f420091a6e9a292b0670443df50c0a0e8b9a1` |

Extracted payloads exactly match public run `35195817696`. The private pair
still differs only by two delay bytes at `[0x149e9,0x149eb)`, the 56-byte
window remains in-function, 52-byte core has no daifset, and 60B probes stay
rejected. Observer fixtures `35197854423` passed with separate full-SHA gates
plus the 56-byte geometry. Execution is split and ordered SUBSYS8 then
SUBSYS1. The former readiness gate was
`READY_FOR_R3_SLOT_B_SUBSYS8_DEVICE_CONTROL=YES`.

## SUBSYS8 true-device member A

Exactly one RAM-only Slot B boot of frozen SUBSYS8
`e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1`
(37380096). Sending OKAY 0.941s, Booting OKAY 0.220s. Automatic Fastboot B
return in `34.702650958s`, retry 7→6. Identity, 56-byte window, 52-byte
no-daifset core and `debug_enabled` ADD gate passed. Current B 16-chain hashes
and P15 prefix matched before/after. Android A restored healthy. SUBSYS1 was
not executed. Absolute ~35s is descriptive only.
`SUBSYS8_MEMBER_A_COMPLETED=YES`.
`SUBSYS_INITCALLS_COMPLETED=NOT_PROVEN`.
`FIRST_FS_INITCALL_ENTRY=NOT_PROVEN`.
`PAIR_VERDICT=PENDING_SUBSYS1`.
`READY_FOR_R3_SLOT_B_SUBSYS1_DEVICE_CONTROL=NO`.
Final gate: `MAINLINE_V2_R3_SLOT_B_SUBSYS8_MEMBER_A_COMPLETED`.
Recommended next: `MAINLINE_V2_R3_SLOT_B_SUBSYS1_DEVICE_GATE_REVIEW`.
See `docs/slot-b-subsys-initcall-checkpoint.md`.
