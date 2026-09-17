# Slot B postcore-initcall completion checkpoint

## Scope

`MAINLINE_V2_R3_SLOT_B_POSTCORE_INITCALLS_CHECKPOINT_CI_AUDIT` is complete.
Public GHA run `35169202296` at `88b67da2d70a2a57949f13457a0a460de2649270`
reused authoritative Linux 6.6.156 bundle `35040148509`. It performed source
audit, initcall-table decode, exact target audit, public 8s/1s payload
preparation and independent static reverify. It did not rebuild the kernel,
pack a private boot image, access a device or write a partition.

The frozen runtime result remains `CORE_INITCALLS_COMPLETED=PROVEN` and
`FIRST_POSTCORE_INITCALL_ENTRY=PROVEN`. This CI result does not advance runtime
evidence: `FIRST_POSTCORE_INITCALL_BODY=NOT_PROVEN`,
`POSTCORE_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_ARCH_INITCALL_ENTRY=NOT_PROVEN`.

## Exact source boundary and table decode

Exact Linux 6.6.156 source maps postcore to
`__initcall2_start..__initcall3_start` and arch to
`__initcall3_start..__initcall4_start`. The table uses 4-byte signed PREL32
entries. Entering the first target decoded at `__initcall3_start` therefore
strictly follows completion of the postcore interval.

All values below were decoded from the authoritative vmlinux, never inferred
from System.map ordering:

| boundary | link VA | Image offset | first decoded target |
| --- | --- | --- | --- |
| `__initcall2_start` | `0xffff800081d0ab6c` | `0x1d0ab6c` | `debug_monitors_init` |
| `__initcall3_start` | `0xffff800081d0ac48` | `0x1d0ac48` | `reserve_memblock_reserved_regions` |
| `__initcall4_start` | `0xffff800081d0ae0c` | `0x1d0ae0c` | `topology_init` |

The `__initcall3_start` word is `0xffe29318`, signed displacement `-1928424`,
and uniquely resolves to `reserve_memblock_reserved_regions` at
`0xffff800081b33f60`, Image offset `0x1b33f60`. The exact registration is
`arch_initcall(reserve_memblock_reserved_regions)` in
`arch/arm64/kernel/setup.c`.

## Target audit

The target is `.init.text`, 324 bytes, with entry `paciasp`. The 60-byte
checkpoint preserves that landing instruction and stays within the function.
The incoming-interior branch gate remains enabled and found no external entry
into the overwrite window. Relocation, exception-table, alternatives,
jump-label, static-call and KCFI rewrite audits passed. The authoritative Image
and frozen FIX8 baseline are byte-exact in the target window; no literal-address
exception was used or generalized.

The diagnostic is the already audited 56-byte stack/memory-free CNTPCT elapsed
8s/1s core followed by PSCI SYSTEM_RESET `0x84000009` via `smc #0`, failing
closed in WFE if SMC returns. No cross-function overwrite or shared
`do_initcalls` loop return point is used.

## Public matched pair

| member | public payload SHA256 | checkpoint SHA256 |
| --- | --- | --- |
| POSTCORE8 | `537a021f6278130957fa666f32421d4f624e84803f00075e3ab2001b8eb9e98b` | `13746511fcfb13c65bfd19ca3651a1d1ee3607438e84a531ec54968455c69559` |
| POSTCORE1 | `3a4b50c956413dabfd739181ca1ed19aca618002e0292782bf02b271ac9cd59f` | `a3246d73828b68f14fbe20ac1d34e09bd4a2ad14784954a6e95c94c5e6739abc` |

The pair differs only at `[0x1b33f6d,0x1b33f6f)`, instruction index 3's
delay encoding. Independent GHA reverify passed baseline-outside-window
identity, table decode, function extent, pair diff, timer/reset words,
fail-closed tail, RT-D, `/init` and initramfs identity.

The frozen future equation is `POSTCORE1_TOTAL-POSTCORE8_TOTAL`, expected
`-7.000s`; STRONG requires absolute error `<=1.000s`, SUPPORTED `<=2.000s`.
A future positive pair may prove postcore completion and first arch entry,
never the overwritten arch function body or later initcall levels.

## Gate

`POSTCORE_CHECKPOINT_SOURCE_AUDIT=PASS`

`POSTCORE_CHECKPOINT_BINARY_AUDIT=PASS`

`POSTCORE_PAIR_STATIC_REVERIFY=PASS`

`POSTCORE_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY`

`POSTCORE_PAIR_PUBLIC_READY=YES`

`READY_FOR_POSTCORE_INITCALLS_PRIVATE_GATE=YES`

The public-CI gate was `MAINLINE_V2_R3_SLOT_B_POSTCORE_INITCALLS_CHECKPOINT_CI_READY`.
It authorized no device operation. The separately approved private-gate result
is recorded below.

## Private gate freeze

Private GHA pack `35170737800` wrapped the two frozen public payloads in the
same proven Slot B/P15 OEM envelope without rebuilding or regenerating them.
Independent reverify-only run `35170837546` downloaded those exact artifacts;
it did not repack, rebuild or regenerate.

| member | private boot SHA256 | size | extracted payload SHA256 |
| --- | --- | --- | --- |
| POSTCORE8 | `141d67931f8792036119c131d93ffa74649af2c6c44d086b489851230075355c` | 37380096 | `537a021f6278130957fa666f32421d4f624e84803f00075e3ab2001b8eb9e98b` |
| POSTCORE1 | `4762a9fd29e109affb1c8864247887334508d9af2d6b183b7bf0200a05b697f1` | 37380096 | `3a4b50c956413dabfd739181ca1ed19aca618002e0292782bf02b271ac9cd59f` |

The reverify reconfirmed the exact target and boundary, preserved `paciasp`,
60-byte in-function window, 8s/1s CNTPCT encodings, PSCI `0x84000009`, SMC,
fail-closed WFE, prior-probe absence, frozen RT-D, `/init`, initramfs and the
P15/OEM envelope. Extracted private payloads differ by exactly two bytes at
`[0x1b33f6d,0x1b33f6f)`, `DELAY_CONSTANT_ONLY`. Geometry is identical:
Image file 35166720, header `image_size=0x2230000`, DTB offset `0x2380000`,
payload 37369041 and boot 37380096.

Observer GHA `35170993710` froze separate full-SHA gates. POSTCORE8 accepts
only POSTCORE8; POSTCORE1 accepts only POSTCORE1. Each rejects its sibling,
CORE, PURE, CONSOLE, INITCALLS, SMP, FREE, KINIT, REST, FIX8, wrong size,
one-byte mutation, payload swap, wrong checkpoint, wrong delay and wrong PSCI.
The completed CORE observer regression `35170993608` passed.

Future device execution is split and ordered `POSTCORE8_THEN_POSTCORE1`.
The next stage may run one POSTCORE8 RAM-only member only after separate user
approval. POSTCORE8 alone can record only `POSTCORE8_MEMBER_A_COMPLETED` and a
total. POSTCORE1 remains blocked until that result is frozen and the user
approves a separate stage. No-shift records
`POSTCORE_INITCALLS_CHECKPOINT_SHIFT_NOT_OBSERVED` and routes to
`POSTCORE_INITCALLS_FAILURE_ISOLATION_CI`; it never asserts that postcore
initcalls did not complete.

`POSTCORE_PUBLIC_PAIR_PASS=YES`

`POSTCORE_TARGET_IDENTITY_FROZEN=YES`

`POSTCORE_PROOF_BOUNDARY_AUDITED=PASS`

`POSTCORE8_PRIVATE_PACK_PASS=YES`

`POSTCORE1_PRIVATE_PACK_PASS=YES`

`POSTCORE8_PRIVATE_REVERIFY_PASS=YES`

`POSTCORE1_PRIVATE_REVERIFY_PASS=YES`

`PRIVATE_POSTCORE_PAIR_DIFF_REVERIFIED=YES`

`POSTCORE_PAIR_GEOMETRY_IDENTICAL=YES`

`POSTCORE8_OBSERVER_READY=YES`

`POSTCORE1_OBSERVER_READY=YES`

`POSTCORE_PAIR_OBSERVER_FIXTURES=PASS`

`POSTCORE_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED`

`POSTCORE_PAIR_EXECUTION_ORDER=POSTCORE8_THEN_POSTCORE1`

`POSTCORE8_DEVICE_AUTHORIZED=NO`

`POSTCORE1_DEVICE_AUTHORIZED=NO`

`DEVICE_OPERATION=NO`

`PARTITION_WRITES=0`

`SLOT_A_WRITTEN=NO`

Final gate: `READY_FOR_R3_SLOT_B_POSTCORE8_DEVICE_CONTROL=YES`.
`READY_FOR_R3_SLOT_B_POSTCORE1_DEVICE_CONTROL=NO`. This readiness gate was not
itself true-device authorization. The separately approved POSTCORE8 device
round is recorded below.

## POSTCORE8 true-device member A

`MAINLINE_V2_R3_SLOT_B_POSTCORE8_TRUE_DEVICE_CONTROL` executed exactly one
RAM-only POSTCORE8 boot. The authoritative artifact retained full SHA256
`141d67931f8792036119c131d93ffa74649af2c6c44d086b489851230075355c`
and size 37380096 immediately before Fastboot interaction; frozen observer
identity validation passed. No image partition was written.

The device began from healthy Android A (`_a`, `boot_completed=1`, Magisk root,
stock `4.19.157-perf-g9d90dd04aa7c`). All 16 boot-chain hashes and the P15
prefix matched the frozen baseline. Bootloader preflight returned
`product=thyme`, `unlocked=yes`, `current-slot=a`; the only metadata transition
before the experiment was `set_active b`.

| event | UTC / value |
| --- | --- |
| `T_COMMAND_START` | `2026-09-17T01:49:20.120523Z` |
| Sending | OKAY, `0.923s` |
| Booting | OKAY, `0.221s` |
| `T_BOOTING_OKAY` | `2026-09-17T01:49:21.295321Z` |
| `T_FASTBOOT_DISAPPEAR` | `2026-09-17T01:49:22.600013Z` |
| `T_FASTBOOT_B_RETURN` | `2026-09-17T01:49:56.249332Z` |
| `POSTCORE8_TOTAL` | `34.936234167s` |

The result was `AUTOMATIC_FASTBOOT_RETURN`; Slot B retry changed 7→6 and no
manual recovery was needed. Fastboot returned on B, then the sole permitted
recovery metadata action selected A and rebooted stock Android. Post-test all
16 hashes and the P15 prefix still matched, so
`CURRENT_B_UNCHANGED_AFTER_POSTCORE8=YES` and
`ANDROID_A_RESTORED_AFTER_POSTCORE8=YES`. Pstore was empty, which is not
negative evidence; stock boot reason `bootloader` is not checkpoint evidence.
Evidence is under `artifacts/slot-b-postcore8-20260917/`.

This single member proves only `POSTCORE8_MEMBER_A_COMPLETED=YES` and freezes
its total. Absolute timing is descriptive only. `POSTCORE1_TOTAL=NOT_RUN`,
`PAIR_DELTA=NOT_AVAILABLE`, and `PAIR_VERDICT=PENDING_POSTCORE1`.
`POSTCORE_INITCALLS_COMPLETED` and `FIRST_ARCH_INITCALL_ENTRY` remain
`NOT_PROVEN`; the first arch body and every later initcall level also remain
`NOT_PROVEN`. POSTCORE1 remains unauthorized pending a separate gate review
and explicit user approval.

`EXPERIMENTAL_BOOTS=1`

`PARTITION_WRITES=0`

`SLOT_A_WRITTEN=NO`

`POSTCORE8_MEMBER_A_COMPLETED=YES`

`POSTCORE8_BEHAVIOR_CLASS=AUTOMATIC_FASTBOOT_RETURN`

`POSTCORE8_TOTAL_S=34.936234167`

`POSTCORE1_TOTAL=NOT_RUN`

`PAIR_DELTA=NOT_AVAILABLE`

`PAIR_VERDICT=PENDING_POSTCORE1`

Final gate: `MAINLINE_V2_R3_SLOT_B_POSTCORE8_MEMBER_A_COMPLETED`.
Recommended next: `MAINLINE_V2_R3_SLOT_B_POSTCORE1_DEVICE_GATE_REVIEW`, with
no device operation in that review.
