# Slot B subsys-initcall completion checkpoint

## Scope

`MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_PROBE_REDESIGN_CI` is complete.
Public GHA run `35195817696` at `e201a8d74bf94c3b9e9014ee91dfe952d17ad027`
reused authoritative Linux 6.6.156 bundle `35040148509`. It redesigned the
first-FS probe to fit the 56-byte target, prepared public SUBSYS8/SUBSYS1
payloads and independently reverified them. It did not rebuild the kernel,
pack a private boot image, access a device or write a partition.

Frozen ARCH runtime remains `ARCH_INITCALLS_COMPLETED=PROVEN` and
`FIRST_SUBSYS_INITCALL_ENTRY=PROVEN`. This CI result does not advance
runtime evidence.

## Exact source boundary

Exact Linux 6.6.156 maps:

- subsys runtime: `__initcall4_start..__initcall5_start`
- fs runtime: `__initcall5_start..__initcall6_start`
- next linker after level 5: `__initcallrootfs_start`

arm64 entries are 4-byte signed PREL32. Entering the first target decoded at
`__initcall5_start` strictly follows completion of the subsys interval.

`SUBSYS_LEVEL_BOUNDARY_SOURCE_PROVEN=YES`

`FIRST_FS_ENTRY_IMPLIES_SUBSYS_COMPLETE=YES`

`INITCALL_ENTRY_ENCODING=PREL32`

`FIRST_FS_PREL32_TARGET_UNCHANGED=YES`

## Table decode

| boundary | link VA | Image offset |
| --- | --- | --- |
| `__initcall4_start` | `0xffff800081d0ae0c` | `0x1d0ae0c` |
| `__initcall5_start` | `0xffff800081d0b0d4` | `0x1d0b0d4` |
| `__initcallrootfs_start` | `0xffff800081d0b1a4` | `0x1d0b1a4` |
| `__initcall6_start` | `0xffff800081d0b1a8` | `0x1d0b1a8` |

The `__initcall5_start` word is `0xfe30990c`, signed displacement
`-30369524`, uniquely `create_debug_debugfs_entry` at
`0xffff8000800149e0` / Image `0x149e0`. Registration
`fs_initcall(create_debug_debugfs_entry)` in
`arch/arm64/kernel/debug-monitors.c`.

`FIRST_FS_INITCALL_TARGET_UNIQUE=PASS`

## Target / 60B rejection

The target is `.text`, 56 bytes, entry `paciasp` `3f2303d5`. PAC yes; BTI no.
Straight-line CFG: no internal branch, forward branch or back-edge.

Proven diagnostic was 4B `paciasp` + 56B CNTPCT/PSCI core = 60B.
60 > 56, so a 60B inline overwrite is rejected.

`SUBSYS_60B_INLINE_REJECTED=YES`

## Design A: 56B-total inline

Selected. Design B trampoline was not required.

Layout:

- `+0x00`: original `paciasp`
- `+0x04`..`+0x37`: 52B diagnostic core

Total overwrite 56B, exactly the function, next symbol untouched.

The 52B core is the proven 56B ultra-compact sequence with only
`msr daifset, #0xf` removed:

| | 56B proven | 52B selected |
| --- | --- | --- |
| instruction count | 14 | 13 |
| removed | `msr daifset, #0xf` | IRQ mask only |
| CNTFRQ / LSL-or-copy / CNTPCT start / ISB loop / SUB / CMP / B.LO | identical | identical |
| 8s encoding | `lsl x10, x9, #3` | same |
| 1s encoding | `UBFM x10, x9, #0, #63` | same |
| PSCI | `movz/movk w0, #0x84000009` + `smc #0` | same |
| fail-closed | `wfe; b` | same |
| stack / memory / MMIO / literal pool / helper | none | none |

IRQ masking is not part of the CNTPCT elapsed-time or PSCI/WFE model.
The 52B binary was assembled in GHA and required to be byte-identical to
`proven56[4:]`.

`SUBSYS_52B_CORE_INDEPENDENTLY_AUDITED=YES`

`SUBSYS_INLINE_FUNCTION_RANGE_SAFE=YES`

`SUBSYS_SELECTED_PROBE_ARCHITECTURE=INLINE_56B_TOTAL`

`SUBSYS_CFG_CLOSURE_PROVEN=YES`

`SUBSYS_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES`

## Window identity

The 56-byte original window matches frozen FIX8 except one ADD immediate at
`0x149f0`: bundle `0x91019000` vs frozen `0x9101b000`. ADRP `0x9000d0e0` is
unchanged. Both ADRP/ADD pairs resolve to the same NUL string
`debug_enabled` at `0x1a30064` vs `0x1a3006c` (8-byte layout delta). The
following `bl` resolves to `debugfs_create_bool`. No other window byte
differs. This is not a reuse of CORE/SMP narrow gates.

`SUBSYS_FS_NAME_LITERAL_ADDRESS_DELTA_VERIFIED`

## Public matched pair

| member | public payload SHA256 | checkpoint SHA256 |
| --- | --- | --- |
| SUBSYS8 | `22400cb378098ce32ef77698de552e8a3690ebda0f377cacc630d69fa0f6d108` | `cb0dccf49f5722d5183dad7fe35173b3da828e33121eb6cd23bf468b780aff63` |
| SUBSYS1 | `c9738f1043c4467b66f2f63305ec20c17b2e648fdd9802fda07e8321e37d5194` | `ada0513d692a3c1657390f94eeba0207fb97cce53a1bbea88353f27d04a554c9` |

Payload size 37369041 each. The pair differs only at
`[0x149e9,0x149eb)`, window instruction 2's delay encoding.
Independent GHA reverify passed baseline-outside-window identity, PREL32
target unchanged, 56-byte function extent, pair diff, timer/reset words,
fail-closed tail, RT-D, `/init` and initramfs identity.

Expected future delta `-7.000s`; STRONG `<=1.000s`, SUPPORTED `<=2.000s`.
A future positive pair may prove subsys completion and first FS entry, never
the overwritten `create_debug_debugfs_entry` body or later initcall levels.

## Gate

`SUBSYS_CHECKPOINT_SOURCE_AUDIT=PASS`

`SUBSYS_CHECKPOINT_BINARY_AUDIT=PASS`

`FIRST_FS_ENTRY_AUDIT=PASS`

`SUBSYS_PAIR_STATIC_REVERIFY=PASS`

`SUBSYS_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY`

`SUBSYS_ALL_PRIOR_STAGE_PROBES_REMOVED=YES`

`SUBSYS_PAIR_PUBLIC_READY=YES`

`READY_FOR_SUBSYS_INITCALLS_PRIVATE_GATE=YES`

The public-CI gate is
`MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_CHECKPOINT_CI_READY`.
The separately approved private-gate result is recorded below.

## Private gate freeze

Private GHA pack `35197516266` wrapped the two frozen public payloads in the
same proven Slot B/P15 OEM envelope without rebuilding or regenerating them.
Independent reverify-only run `35197852552` downloaded those exact artifacts;
it did not repack, rebuild or regenerate. Both members reconfirmed the 56-byte
window, 52-byte no-daifset core, PREL32 target unchanged, and the
`debug_enabled` ADD layout delta. 60B and 57B windows stay rejected.

| member | private boot SHA256 | size | extracted payload SHA256 |
| --- | --- | --- | --- |
| SUBSYS8 | `e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1` | 37380096 | `22400cb378098ce32ef77698de552e8a3690ebda0f377cacc630d69fa0f6d108` |
| SUBSYS1 | `df14e7bcdf409deeeede70d7217f420091a6e9a292b0670443df50c0a0e8b9a1` | 37380096 | `c9738f1043c4467b66f2f63305ec20c17b2e648fdd9802fda07e8321e37d5194` |

Private extracted payloads differ by exactly two bytes at
`[0x149e9,0x149eb)`, `DELAY_CONSTANT_ONLY`. Geometry is identical:
Image file 35166720, header `image_size=0x2230000`, DTB offset `0x2380000`,
payload 37369041 and boot 37380096. Envelope is `KERNEL_PAYLOAD_ONLY` vs FIX8.

Observer GHA `35197854423` froze separate full-SHA gates plus the 56-byte
geometry and 52-byte core. SUBSYS8 accepts only SUBSYS8; SUBSYS1 accepts only
SUBSYS1. Each rejects its sibling, ARCH, POSTCORE, CORE, PURE, CONSOLE,
INITCALLS, SMP, FREE, KINIT, REST, FIX8, 60B/57B windows, daifset, trampoline,
wrong PREL32, wrong `debug_enabled` ADD, wrong delay and wrong PSCI. CORE
observer regression `35197854428`, POSTCORE observer `35197854432` and ARCH
observer `35197854485` passed.

Future device execution is split and ordered `SUBSYS8_THEN_SUBSYS1`.
SUBSYS8 alone can record only `SUBSYS8_MEMBER_A_COMPLETED` and a total.
SUBSYS1 remains blocked until that result is frozen and the user approves a
separate stage. No-shift records
`SUBSYS_INITCALLS_CHECKPOINT_SHIFT_NOT_OBSERVED` and routes to
`SUBSYS_INITCALLS_FAILURE_ISOLATION_CI`.

The former readiness gate was `READY_FOR_R3_SLOT_B_SUBSYS8_DEVICE_CONTROL=YES`.
The separately approved SUBSYS8 true-device round is recorded below.

## SUBSYS8 true-device member A

`MAINLINE_V2_R3_SLOT_B_SUBSYS8_TRUE_DEVICE_CONTROL` executed exactly one
RAM-only SUBSYS8 boot. The authoritative artifact retained full SHA256
`e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1`
and size 37380096 immediately before Fastboot interaction; frozen observer
identity validation passed. The 56-byte window, preserved `paciasp`, 52-byte
no-daifset core, PREL32 target, `debug_enabled` ADD gate and 60-byte rejection
remained the frozen identity. No image partition was written. SUBSYS1 was not
present and was not executed.

The device began from healthy Android A (`_a`, `boot_completed=1`, Magisk root,
stock `4.19.157-perf-g9d90dd04aa7c`). All 16 boot-chain hashes and the P15
prefix matched the frozen baseline. Bootloader preflight returned
`product=thyme`, `unlocked=yes`, `current-slot=a`; the only metadata transition
before the experiment was `set_active b`.

| event | UTC / value |
| --- | --- |
| `T_COMMAND_START` | `2026-09-17T08:23:57.121540Z` |
| Sending | OKAY, `0.941s` |
| Booting | OKAY, `0.220s` |
| `T_BOOTING_OKAY` | `2026-09-17T08:23:58.317639Z` |
| `T_FASTBOOT_DISAPPEAR` | `2026-09-17T08:23:59.685214Z` |
| `T_FASTBOOT_B_RETURN` | `2026-09-17T08:24:33.055695Z` |
| `SUBSYS8_TOTAL` | `34.702650958s` |

The result was `AUTOMATIC_FASTBOOT_RETURN`; Slot B retry changed 7→6 and no
manual recovery was needed. Fastboot returned on B, then the sole permitted
recovery metadata action selected A and rebooted stock Android. Post-test all
16 hashes and the P15 prefix still matched, so
`CURRENT_B_UNCHANGED_AFTER_SUBSYS8=YES` and
`ANDROID_A_RESTORED_AFTER_SUBSYS8=YES`. Pstore was empty, which is not negative
evidence. Evidence is under `artifacts/slot-b-subsys8-20260917/`.

This single member proves only `SUBSYS8_MEMBER_A_COMPLETED=YES` and freezes its
total. Absolute ~35s is descriptive only and is not pair proof.
`SUBSYS1_TOTAL=NOT_RUN`, `PAIR_DELTA=NOT_AVAILABLE`, and
`PAIR_VERDICT=PENDING_SUBSYS1`. `SUBSYS_INITCALLS_COMPLETED` and
`FIRST_FS_INITCALL_ENTRY` remain `NOT_PROVEN`; the first FS body and every
later initcall level also remain `NOT_PROVEN`. SUBSYS1 remains unauthorized
pending a separate gate review and explicit user approval.

`EXPERIMENTAL_BOOTS=1`

`PARTITION_WRITES=0`

`SLOT_A_WRITTEN=NO`

`SUBSYS8_MEMBER_A_COMPLETED=YES`

`SUBSYS8_BEHAVIOR_CLASS=AUTOMATIC_FASTBOOT_RETURN`

`SUBSYS8_TOTAL_S=34.702650958`

`SUBSYS1_TOTAL=NOT_RUN`

`PAIR_DELTA=NOT_AVAILABLE`

`PAIR_VERDICT=PENDING_SUBSYS1`

`READY_FOR_R3_SLOT_B_SUBSYS1_DEVICE_CONTROL=NO` was the post-member-A state.
The subsequent no-device SUBSYS1 gate review is recorded below.

## SUBSYS1 device gate review

`MAINLINE_V2_R3_SLOT_B_SUBSYS1_DEVICE_GATE_REVIEW` froze member A at
`SUBSYS8_TOTAL=34.702650958s`; SUBSYS8 may not be rerun. GHA-only reverify-only
run `35201320107` downloaded the immutable private artifacts from pack run
`35197516266` without rebuild, repack or regeneration. It reconfirmed:

- SUBSYS1 boot SHA256
  `df14e7bcdf409deeeede70d7217f420091a6e9a292b0670443df50c0a0e8b9a1`,
  size 37380096
- extracted payload SHA256
  `c9738f1043c4467b66f2f63305ec20c17b2e648fdd9802fda07e8321e37d5194`
- target `create_debug_debugfs_entry`, boundary `__initcall5_start`, 56-byte
  function, 56-byte in-function window and preserved `paciasp`
- 52-byte diagnostic core with `daifset` absent; 60-byte and 57-byte windows
  still rejected; next symbol untouched
- 1s CNTPCT elapsed loop, PSCI SYSTEM_RESET `0x84000009`, `smc #0`, and
  fail-closed WFE loop
- ADD at `0x149f0` still `0x91019000` vs FIX8 `0x9101b000`, both
  `debug_enabled`: `SUBSYS_FS_NAME_LITERAL_ADDRESS_DELTA_VERIFIED=PASS`
- PREL32 target unchanged
- frozen RT-D `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`,
  bootargs `rdinit=/init panic=5 loglevel=7`, unchanged `/init` and initramfs,
  no external initrd, and matching P15/OEM envelope
- all REST/KINIT/FREE/SMP/DO_INITCALLS/PURE/CORE/POSTCORE/ARCH/CONSOLE
  diagnostics removed; SUBSYS1 is the sole active checkpoint

The private payload pair still differs by exactly two bytes at
`[0x149e9,0x149eb)`, instruction 2 only, attributed `DELAY_CONSTANT_ONLY`;
geometry and every non-delay property remain identical. Therefore
`SUBSYS_PAIR_SINGLE_VARIABLE_STILL_VALID=YES`.

Observer source is byte-identical to readiness commit
`92633a354fddc65c195ed1a2872f8250db836a84`. GHA observer review run
`35201324281` passed the SUBSYS1 exact full-SHA gate, 56-byte geometry, 52-byte
core, daifset-absent, 60/57-byte rejection, ADD narrow-gate fixture, unit tests,
future pair boundaries, one-boot/RAM-only discipline, and rejection of SUBSYS8,
ARCH, POSTCORE, CORE, PURE, CONSOLE, INITCALLS, SMP, FREE, KINIT, REST, RESET,
FIX8, wrong size, one-byte mutation, payload swap, wrong checkpoint, wrong delay
and wrong PSCI. CORE observer review `35201328691`, POSTCORE observer review
`35201332615` and ARCH observer review `35201336960` passed; prior regressions
remain applicable because observer behavior did not change.

Future member B must use the same timing algorithm:
`SUBSYS1_TOTAL-34.702650958s`. Expected delta is `-7.000000000s`, with STRONG
absolute pair error `<=1.000s` and SUPPORTED `<=2.000s`. Absolute SUBSYS1 timing
is secondary only. A comparable no-shift result routes to
`MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_FAILURE_ISOLATION_CI`; ambiguous
behavior routes to the same isolation stage without changing the windows.

This review performed no device interaction or partition write. Current B and
Android A remain frozen from the SUBSYS8 result. A future SUBSYS1 round must
independently repeat pre/post integrity checks, begin from healthy Android A,
select B, run exactly one full-SHA-gated RAM boot, return to A without image
writes, and never retry a rejected boot.

`SUBSYS8_MEMBER_A_FROZEN=YES`

`SUBSYS8_TOTAL_FROZEN=34.702650958`

`SUBSYS1_PUBLIC_PAYLOAD_IDENTITY=PASS`

`SUBSYS1_PRIVATE_BOOT_IDENTITY=PASS`

`SUBSYS1_PRIVATE_REVERIFY=PASS`

`FIRST_FS_PREL32_TARGET_UNCHANGED=YES`

`SUBSYS_INLINE_56B_TOTAL_STILL_VALID=YES`

`SUBSYS_52B_CORE_IDENTITY_STILL_VALID=YES`

`SUBSYS_DAIFSET_ABSENT=YES`

`SUBSYS_60B_INLINE_REJECTED=YES`

`SUBSYS_FS_NAME_LITERAL_ADDRESS_DELTA_VERIFIED=YES`

`SUBSYS_PAIR_SINGLE_VARIABLE_STILL_VALID=YES`

`SUBSYS_PAIR_GEOMETRY_IDENTICAL=YES`

`SUBSYS1_CHECKPOINT_IDENTITY=PASS`

`SUBSYS1_OBSERVER_IDENTITY_GATE_READY=YES`

`SUBSYS1_OBSERVER_REGRESSION_SAFE=YES`

`CURRENT_B_AFTER_SUBSYS8=UNCHANGED`

`ANDROID_A_AFTER_SUBSYS8=RESTORED`

`PAIR_EQUATION_FROZEN=YES`

`DEVICE_OPERATION=NO`

`READY_FOR_R3_SLOT_B_SUBSYS1_DEVICE_CONTROL=YES`

Final gate: `READY_FOR_R3_SLOT_B_SUBSYS1_DEVICE_CONTROL`.
Recommended next, after separate user approval:
`MAINLINE_V2_R3_SLOT_B_SUBSYS1_TRUE_DEVICE_CONTROL`.
This review did not execute SUBSYS1.

Evidence: `artifacts/slot-b-subsys1-gate-review-20260917/`.
