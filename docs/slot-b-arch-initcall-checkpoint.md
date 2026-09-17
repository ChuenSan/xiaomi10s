# Slot B arch-initcall completion checkpoint

## Scope

`MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_CHECKPOINT_CI_AUDIT` is complete.
Public GHA run `35182765631` at `fa4be7884cd91902ba22fc50bebc15a5f47cf8d2`
reused authoritative Linux 6.6.156 bundle `35040148509`. It performed source
audit, initcall-table decode, exact first-subsys target audit, public 8s/1s
payload preparation and independent static reverify. It did not rebuild the
kernel, pack a private boot image, access a device or write a partition.

Frozen POSTCORE runtime remains `POSTCORE_INITCALLS_COMPLETED=PROVEN` and
`FIRST_ARCH_INITCALL_ENTRY=PROVEN`. This CI result does not advance runtime
evidence: `FIRST_ARCH_INITCALL_BODY=NOT_PROVEN`,
`ARCH_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_SUBSYS_INITCALL_ENTRY=NOT_PROVEN`.

## Exact source boundary and table decode

Exact Linux 6.6.156 `init/main.c`, `include/linux/init.h`,
`include/asm-generic/vmlinux.lds.h` and `arch/arm64/Kconfig` map arch to
`__initcall3_start..__initcall4_start` and subsys to
`__initcall4_start..__initcall5_start`. arm64 selects
`HAVE_ARCH_PREL32_RELOCATIONS`; entries are 4-byte signed PREL32
(`.long stub - .`). Entering the first target decoded at
`__initcall4_start` therefore strictly follows completion of the arch
interval.

All values below were decoded from the authoritative vmlinux, never inferred
from System.map ordering:

| boundary | link VA | Image offset | first decoded target |
| --- | --- | --- | --- |
| `__initcall3_start` | `0xffff800081d0ac48` | `0x1d0ac48` | `reserve_memblock_reserved_regions` |
| `__initcall4_start` | `0xffff800081d0ae0c` | `0x1d0ae0c` | `topology_init` |
| `__initcall5_start` | `0xffff800081d0b0d4` | `0x1d0b0d4` | `create_debug_debugfs_entry` |

The `__initcall4_start` word is `0xffe298f0`, signed displacement `-1926928`,
and uniquely resolves to `topology_init` at `0xffff800081b346fc`, Image offset
`0x1b346fc`. Table uniqueness checked 1732 PREL32 entries. The exact
registration is `subsys_initcall(topology_init)` in
`arch/arm64/kernel/setup.c`.

`ARCH_LEVEL_BOUNDARY_SOURCE_PROVEN=YES`

`FIRST_SUBSYS_ENTRY_IMPLIES_ARCH_COMPLETE=YES`

`INITCALL_ENTRY_ENCODING=PREL32`

`FIRST_SUBSYS_INITCALL_TARGET_UNIQUE=PASS`

## Target audit

The target is `.init.text`, 188 bytes, entry `paciasp` `3f2303d5`. PAC is
present; BTI/SCS/CFI/fentry are off. A 60-byte diagnostic would leave the
function-local loop back-edge `+0x9c → +0x38` jumping into overwrite interior,
so the accepted window is expanded to 160 bytes: preserved `paciasp`, the
already audited 56-byte stack/memory-free CNTPCT elapsed 8s/1s core, PSCI
SYSTEM_RESET `0x84000009` via `smc #0`, fail-closed WFE, then 100 bytes of NOP.
The expanded window stays inside the 188-byte function and overwrites the
back-edge source. Incoming-interior is empty after expansion. Relocation,
exception-table, alternatives, jump-label, static-call and KCFI rewrite
audits passed. The authoritative Image and frozen FIX8 baseline are byte-exact
in the 160-byte window; no literal-address exception was used or generalized.

No shared `do_initcalls` loop return point is used. CORE and POSTCORE probe
windows were not copied.

## Public matched pair

| member | public payload SHA256 | checkpoint SHA256 |
| --- | --- | --- |
| ARCH8 | `feb46bb3da436c00ac54ee7898e9b1789a11f30878eb8859a2fcecf719d9cad5` | `8fe238cbb9af83d194f2ccedd58a2c715c451b8469fbe76c15cf8106107d1b03` |
| ARCH1 | `efa7cc1c43302fd93872d905352f5737bd388aa698a9383b5d929e98223d2fc1` | `9ac42ce52f9974dba8fac43da9cae815596a0dc88e756a6378dac44c7e398f57` |

Payload size 37369041 each. The pair differs only at
`[0x1b34709,0x1b3470b)`, instruction index 3's delay encoding.
Independent GHA reverify passed baseline-outside-window identity, table
decode, 160-byte function extent, NOP tail, pair diff, timer/reset words,
fail-closed tail, RT-D, `/init` and initramfs identity.

The frozen future equation is `ARCH1_TOTAL-ARCH8_TOTAL`, expected `-7.000s`;
STRONG requires absolute error `<=1.000s`, SUPPORTED `<=2.000s`. A future
positive pair may prove arch completion and first subsys entry, never the
overwritten `topology_init` body or later initcall levels.

## Gate

`ARCH_CHECKPOINT_SOURCE_AUDIT=PASS`

`ARCH_CHECKPOINT_BINARY_AUDIT=PASS`

`FIRST_SUBSYS_ENTRY_AUDIT=PASS`

`ARCH_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES`

`ARCH_CHECKPOINT_PROBE_SAFE=YES`

`ARCH_PAIR_STATIC_REVERIFY=PASS`

`ARCH_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY`

`ARCH_ALL_PRIOR_STAGE_PROBES_REMOVED=YES`

`ARCH_PAIR_PUBLIC_READY=YES`

`READY_FOR_ARCH_INITCALLS_PRIVATE_GATE=YES`

The public-CI gate was `MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_CHECKPOINT_CI_READY`.
It authorized no device operation. The separately approved private-gate result
is recorded below.

## Private gate freeze

Private GHA pack `35185168680` wrapped the two frozen public payloads in the
same proven Slot B/P15 OEM envelope without rebuilding or regenerating them.
Independent reverify-only run `35185358880` downloaded those exact artifacts;
it did not repack, rebuild or regenerate. Both members reconfirmed the 160-byte
window, rejected any 60-byte topology_init probe, and covered back-edge source
`+0x9c`.

| member | private boot SHA256 | size | extracted payload SHA256 |
| --- | --- | --- | --- |
| ARCH8 | `7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d` | 37380096 | `feb46bb3da436c00ac54ee7898e9b1789a11f30878eb8859a2fcecf719d9cad5` |
| ARCH1 | `f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113` | 37380096 | `efa7cc1c43302fd93872d905352f5737bd388aa698a9383b5d929e98223d2fc1` |

Private extracted payloads differ by exactly two bytes at
`[0x1b34709,0x1b3470b)`, `DELAY_CONSTANT_ONLY`. Geometry is identical:
Image file 35166720, header `image_size=0x2230000`, DTB offset `0x2380000`,
payload 37369041 and boot 37380096. Envelope is `KERNEL_PAYLOAD_ONLY` vs FIX8.

Observer GHA `35185723809` froze separate full-SHA gates plus the 160-byte
geometry. ARCH8 accepts only ARCH8; ARCH1 accepts only ARCH1. Each rejects its
sibling, POSTCORE, CORE, PURE, CONSOLE, INITCALLS, SMP, FREE, KINIT, REST,
FIX8, wrong size, one-byte mutation, payload swap, wrong target, wrong window,
60-byte probe, live back-edge source, wrong delay and wrong PSCI. CORE observer
regression `35185723784` and POSTCORE observer `35185723808` passed.

Future device execution is split and ordered `ARCH8_THEN_ARCH1`. The next stage
may run one ARCH8 RAM-only member only after separate user approval. ARCH8
alone can record only `ARCH8_MEMBER_A_COMPLETED` and a total. ARCH1 remains
blocked until that result is frozen and the user approves a separate stage.
No-shift records `ARCH_INITCALLS_CHECKPOINT_SHIFT_NOT_OBSERVED` and routes to
`ARCH_INITCALLS_FAILURE_ISOLATION_CI`; it never asserts that arch initcalls
did not complete.

`ARCH_PUBLIC_PAIR_PASS=YES`

`ARCH_TARGET_IDENTITY_FROZEN=YES`

`ARCH_160B_CFG_CLOSURE_REVERIFIED=YES`

`ARCH_60B_WINDOW_REJECTED=YES`

`ARCH_FUNCTION_RANGE_SAFE=YES`

`ARCH_PUBLIC_PAIR_SINGLE_VARIABLE_REVERIFIED=YES`

`ARCH8_PRIVATE_PACK_PASS=YES`

`ARCH1_PRIVATE_PACK_PASS=YES`

`ARCH8_PRIVATE_REVERIFY_PASS=YES`

`ARCH1_PRIVATE_REVERIFY_PASS=YES`

`ARCH_60B_CFG_NEGATIVE_FIXTURE=PASS`

`PRIVATE_ARCH_PAIR_DIFF_REVERIFIED=YES`

`ARCH_PAIR_GEOMETRY_IDENTICAL=YES`

`ARCH_PAIR_P15_ENVELOPE_IDENTICAL=YES`

`ARCH8_OBSERVER_READY=YES`

`ARCH1_OBSERVER_READY=YES`

`ARCH_PAIR_OBSERVER_FIXTURES=PASS`

`ARCH_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED`

`ARCH_PAIR_EXECUTION_ORDER=ARCH8_THEN_ARCH1`

`ARCH8_DEVICE_AUTHORIZED=NO`

`ARCH1_DEVICE_AUTHORIZED=NO`

The former readiness gate was `READY_FOR_R3_SLOT_B_ARCH8_DEVICE_CONTROL=YES`.
The separately approved ARCH8 true-device round is recorded below.

## ARCH8 true-device member A

`MAINLINE_V2_R3_SLOT_B_ARCH8_TRUE_DEVICE_CONTROL` executed exactly one RAM-only
ARCH8 boot. The authoritative artifact retained full SHA256
`7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d`
and size 37380096 immediately before Fastboot interaction; frozen observer
identity validation passed. The 160-byte window, `paciasp`, back-edge coverage
`+0x9c → +0x38`, and 60-byte rejection remained the frozen identity. No image
partition was written. ARCH1 was not present and was not executed.

The device began from healthy Android A (`_a`, `boot_completed=1`, Magisk root,
stock `4.19.157-perf-g9d90dd04aa7c`). All 16 boot-chain hashes and the P15
prefix matched the frozen baseline. Bootloader preflight returned
`product=thyme`, `unlocked=yes`, `current-slot=a`; the only metadata transition
before the experiment was `set_active b`.

| event | UTC / value |
| --- | --- |
| `T_COMMAND_START` | `2026-09-17T05:41:18.425545Z` |
| Sending | OKAY, `0.928s` |
| Booting | OKAY, `0.222s` |
| `T_BOOTING_OKAY` | `2026-09-17T05:41:19.607554Z` |
| `T_FASTBOOT_DISAPPEAR` | `2026-09-17T05:41:20.803622Z` |
| `T_FASTBOOT_B_RETURN` | `2026-09-17T05:41:54.637607Z` |
| `ARCH8_TOTAL` | `34.99866775s` |

The result was `AUTOMATIC_FASTBOOT_RETURN`; Slot B retry changed 7→6 and no
manual recovery was needed. Fastboot returned on B, then the sole permitted
recovery metadata action selected A and rebooted stock Android. Post-test all
16 hashes and the P15 prefix still matched, so
`CURRENT_B_UNCHANGED_AFTER_ARCH8=YES` and
`ANDROID_A_RESTORED_AFTER_ARCH8=YES`. Pstore was empty, which is not negative
evidence. Evidence is under `artifacts/slot-b-arch8-20260917/`.

This single member proves only `ARCH8_MEMBER_A_COMPLETED=YES` and freezes its
total. Absolute timing is descriptive only. `ARCH1_TOTAL=NOT_RUN`,
`PAIR_DELTA=NOT_AVAILABLE`, and `PAIR_VERDICT=PENDING_ARCH1`.
`ARCH_INITCALLS_COMPLETED` and `FIRST_SUBSYS_INITCALL_ENTRY` remain
`NOT_PROVEN`; the first subsys body and every later initcall level also remain
`NOT_PROVEN`. ARCH1 remains unauthorized pending a separate gate review and
explicit user approval.

`EXPERIMENTAL_BOOTS=1`

`PARTITION_WRITES=0`

`SLOT_A_WRITTEN=NO`

`ARCH8_MEMBER_A_COMPLETED=YES`

`ARCH8_BEHAVIOR_CLASS=AUTOMATIC_FASTBOOT_RETURN`

`ARCH8_TOTAL_S=34.99866775`

`ARCH1_TOTAL=NOT_RUN`

`PAIR_DELTA=NOT_AVAILABLE`

`PAIR_VERDICT=PENDING_ARCH1`

Final gate: `MAINLINE_V2_R3_SLOT_B_ARCH8_MEMBER_A_COMPLETED`.
The subsequent no-device ARCH1 gate review is recorded below.

## ARCH1 device gate review

`MAINLINE_V2_R3_SLOT_B_ARCH1_DEVICE_GATE_REVIEW` froze member A at
`ARCH8_TOTAL=34.99866775s`; ARCH8 may not be rerun. GHA-only reverify-only run
`35187716061` downloaded the immutable private artifacts from pack run
`35185168680` without rebuild, repack or regeneration. It reconfirmed:

- ARCH1 boot SHA256
  `f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113`,
  size 37380096
- extracted payload SHA256
  `efa7cc1c43302fd93872d905352f5737bd388aa698a9383b5d929e98223d2fc1`
- target `topology_init`, boundary `__initcall4_start`, 188-byte function,
  160-byte in-function window and preserved `paciasp`
- back-edge `+0x9c → +0x38` source covered; 60-byte window still rejected
- 1s CNTPCT elapsed loop, PSCI SYSTEM_RESET `0x84000009`, `smc #0`, and
  fail-closed WFE loop
- frozen RT-D `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`,
  bootargs `rdinit=/init panic=5 loglevel=7`, unchanged `/init` and initramfs,
  no external initrd, and matching P15/OEM envelope
- all REST/KINIT/FREE/SMP/DO_INITCALLS/PURE/CORE/POSTCORE/CONSOLE diagnostics
  removed; ARCH1 is the sole active checkpoint

The private payload pair still differs by exactly two bytes at
`[0x1b34709,0x1b3470b)`, instruction 3 only, attributed
`DELAY_CONSTANT_ONLY`; geometry and every non-delay property remain identical.
Therefore `ARCH_PAIR_SINGLE_VARIABLE_STILL_VALID=YES`.

Observer source is byte-identical to readiness commit
`fb4ab8d1548d8644518ed143eda36f10609f75d1`. GHA observer review run
`35187718697` passed the ARCH1 exact full-SHA gate, 160-byte geometry, 60-byte
rejection, unit tests, future pair boundaries, one-boot/RAM-only discipline,
and rejection of ARCH8, POSTCORE, CORE, PURE, CONSOLE, INITCALLS, SMP, FREE,
KINIT, REST, RESET, FIX8, wrong size, one-byte mutation, payload swap, wrong
checkpoint, wrong delay and wrong PSCI. CORE observer review `35187721522` and
POSTCORE observer review `35187723891` passed; prior CORE/POSTCORE regressions
remain applicable because observer behavior did not change.

Future member B must use the same timing algorithm:
`ARCH1_TOTAL-34.99866775s`. Expected delta is `-7.000000000s`, with STRONG
absolute pair error `<=1.000s` and SUPPORTED `<=2.000s`. Absolute ARCH1 timing
is secondary only. A comparable no-shift result routes to
`MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_FAILURE_ISOLATION_CI`; ambiguous
behavior routes to the same isolation stage without changing the windows.

This review performed no device interaction or partition write. Current B and
Android A remain frozen from the ARCH8 result. A future ARCH1 round must
independently repeat pre/post integrity checks, begin from healthy Android A,
select B, run exactly one full-SHA-gated RAM boot, return to A without image
writes, and never retry a rejected boot.

`ARCH8_MEMBER_A_FROZEN=YES`

`ARCH8_TOTAL_FROZEN=34.99866775`

`ARCH1_PUBLIC_PAYLOAD_IDENTITY=PASS`

`ARCH1_PRIVATE_BOOT_IDENTITY=PASS`

`ARCH1_PRIVATE_REVERIFY=PASS`

`ARCH_160B_CFG_CLOSURE_STILL_VALID=YES`

`ARCH_60B_WINDOW_REJECTED=YES`

`BACKEDGE_SOURCE_COVERED=YES`

`ARCH_PAIR_SINGLE_VARIABLE_STILL_VALID=YES`

`ARCH_PAIR_GEOMETRY_IDENTICAL=YES`

`ARCH1_CHECKPOINT_IDENTITY=PASS`

`ARCH1_ONLY_ACTIVE_DIAGNOSTIC=YES`

`ARCH1_OBSERVER_IDENTITY_GATE_READY=YES`

`ARCH1_OBSERVER_REGRESSION_SAFE=YES`

`CURRENT_B_AFTER_ARCH8=UNCHANGED`

`ANDROID_A_AFTER_ARCH8=RESTORED`

`PAIR_EQUATION_FROZEN=YES`

`DEVICE_OPERATION=NO`

`PARTITION_WRITES=0`

`SLOT_A_WRITTEN=NO`

Final gate: `READY_FOR_R3_SLOT_B_ARCH1_DEVICE_CONTROL=YES`.
This readiness gate is not itself true-device authorization. Recommended next,
only after explicit user approval:
`MAINLINE_V2_R3_SLOT_B_ARCH1_TRUE_DEVICE_CONTROL`.
