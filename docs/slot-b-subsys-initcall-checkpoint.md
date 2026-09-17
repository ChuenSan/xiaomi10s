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
It authorized no device operation. Next, only after explicit approval:
`MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_PRIVATE_GATE_FINALIZATION_CI`.

Evidence: `artifacts/slot-b-subsys-initcall-redesign-20260917/`.
