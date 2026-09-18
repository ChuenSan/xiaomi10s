# Slot B FS-initcall completion checkpoint

## Scope

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_TRAMPOLINE_REDESIGN_CI` is complete.
Public GHA run `35215536867` at `150cb9a299a551bd8d90f269c90aed9aae994776`
reused authoritative Linux 6.6.156 bundle `35040148509`. It did not rebuild
the kernel, pack a private boot image, access a device or write a partition.

Frozen SUBSYS runtime remains `SUBSYS_INITCALLS_COMPLETED=PROVEN` and
`FIRST_FS_INITCALL_ENTRY=PROVEN`. This CI result does not advance runtime
evidence.

## Frozen causal boundary

Linux 6.6.156 maps:

- `do_initcall_level(5)` walks `[__initcall5_start, __initcall6_start)`
- rootfs is linker-placed between 5 and 6 and has no separate runtime pass
- first device PREL32 at `__initcall6_start` is the next real runtime entry

| field | value |
| --- | --- |
| table VA | `0xffff800081d0b1a8` |
| entry word | `0xffe29610` |
| signed displacement | `-1927664` |
| target VA | `0xffff800081b347b8` |
| Image offset | `0x1b347b8` |
| symbol | `register_arm64_panic_block` |
| source | `arch/arm64/kernel/setup.c` |
| registration | `device_initcall(register_arm64_panic_block)` |
| section | `.init.text` |
| size | 48 |
| entry0 | `paciasp` `d503233f` |

`FIRST_DEVICE_ENTRY_IMPLIES_FS_COMPLETE=YES`

`FS_COMPLETE_TARGET_UNIQUE=PASS`

PREL32 still points at `register_arm64_panic_block`. The table is not rewritten.

## Selected probe architecture

`ENTRY_TRAMPOLINE`

Inline 4B `paciasp` + 52B proven CNTPCT/PSCI core needs 56B and does not fit.
A 44B core would drop fail-closed or timer/PSCI instructions. The 48B function
is a straight line with no internal back-edge.

Entry stub (8B, inside the function):

| offset | original | probe |
| --- | --- | --- |
| `0x1b347b8` | `paciasp` | preserved `d503233f` |
| `0x1b347bc` | `stp x29, x30` | `b island` `0x17936e04` |

Remainder `[0x1b347c0, 0x1b347e8)` stays original and is not executed.

## Island identity

| field | value |
| --- | --- |
| kind | `RESERVED_EFI_HOLE` |
| Image | `[0xffcc, 0x10000)` |
| VA | `0xffff80008000ffcc` |
| size | 52 |
| section | `.head.text` AX |
| padding | NOP (`0xd503201f`) |
| covering | `__efistub__text`, `_text` |
| next symbol | `0xffff800080010000` |
| live tramp | `[0x40, 0x70)` SHA `362d9c6e…dc623` untouched |

Direct AArch64 `B` from `0x1b347bc` to `0xffcc` is in range (~27.17MiB). No veneer.

Diagnostic core is the independently assembled 52-byte no-daifset sequence:
CNTPCT elapsed, PSCI `0x84000009` `smc #0`, WFE fail-closed. 8s `lsl #3`
`0xd37df12a` vs 1s UBFM `0xd340fd2a`.

## Ownership / xref / runtime rewrite

Stub window 8B and island 52B: no incoming interior, no interior symbols, no
relocs, no absolute-VA literals into the overwrite, `__jump_table` /
`.static_call_sites` / `.kcfi_traps` ABSENT, `__ex_table` and
`.altinstructions` present but do not overlap either window.

`FS_CFG_CLOSURE_PROVEN=YES`

`FS_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES`

`FIRST_DEVICE_PREL32_TARGET_UNCHANGED=YES`

`FIX8_TRAMPOLINE_IDENTICAL=YES`

## Pair

| | SHA-256 |
| --- | --- |
| FS8 | `1a4da6f924ec09f58bb37edb8bb41d74e9e138b91c9b5c69a4479035da6718ee` |
| FS1 | `e36d4a18d78bdabbcb209e87472a3240bdbc93d3a5b55cd88f182d295aa75e49` |

`FS_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY` 2 bytes `[0xffd1,0xffd3)`
(island instruction 1). Image-wide vs FIX8: only `[0x1b347bc,0x1b347c0)` and
`[0xffcc,0x10000)`. RT-D, `/init`, initramfs unchanged.
`RUNTIME_DTB_EXTERNAL_INITRD=NO`.

Independent reverify `35215536867` PASS. Negative fixtures PASS.

## Gate

`FS_PAIR_PUBLIC_READY=YES`

`READY_FOR_FS_INITCALLS_PRIVATE_GATE=YES`

Runtime evidence is unchanged:

`FIRST_FS_INITCALL_BODY=NOT_PROVEN`

`FS_INITCALLS_COMPLETED=NOT_PROVEN`

`FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN`

Final gate of the public trampoline CI was
`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_CHECKPOINT_CI_READY`.

## Private gate

Private pack `35221241185` at private-ci `e9a8293` spliced the frozen public
payloads without a kernel rebuild. Independent reverify `35221411477` PASS.
Observer fixtures `35222087312` and CORE/POSTCORE/ARCH/SUBSYS regressions
`35222087165`/`35222087194`/`35222087181`/`35222087497` PASS at public
`0b8f7f1`.

| | SHA-256 | size |
| --- | --- | --- |
| FS8 boot | `cfc9f3f9c931126aceb47a5dcc39c12227f34eceb7ad2d9e6642088f3b7e6594` | 37380096 |
| FS1 boot | `2377b227fd0eb4105330eec64f19843d7d64d42f994b12b999571cca6f4e3a1b` | 37380096 |

Extracted payloads match the public pair. Private pair remains
`DELAY_CONSTANT_ONLY` 2 bytes `[0xffd1,0xffd3)`. Stub, island, PREL32, live
trampoline `[0x40,0x70)` and P15 envelope identical. Image-wide vs FIX8 is
stub `[0x1b347bc,0x1b347c0)` plus island `[0xffcc,0x10000)` only.

`READY_FOR_FS8_FS1_DEVICE_PAIR=YES`

## Device pair

Exactly one FS8 then one FS1 RAM-only Slot B boot, each from healthy Android A.
Both `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6, no manual recovery.

| | Sending | Booting | TOTAL |
| --- | --- | --- | --- |
| FS8 | OKAY 0.901s | OKAY 0.222s | `31.909265209s` |
| FS1 | OKAY 0.920s | OKAY 0.222s | `31.953695875s` |

- `PAIR_DELTA=+0.044430666s`
- `EXPECTED=-7.000000000s`
- `PAIR_ERROR=+7.044430666s`
- `ABS_PAIR_ERROR=7.044430666s`
- `FS_PAIR_VERDICT=SHIFT_NOT_OBSERVED`

Absolute ~32s is descriptive only. Do not write
`FS_INITCALLS_NOT_COMPLETED`.

Runtime evidence is unchanged:

`FIRST_FS_INITCALL_BODY=NOT_PROVEN`

`FS_INITCALLS_COMPLETED=NOT_PROVEN`

`FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN`

`FIRST_DEVICE_INITCALL_BODY=NOT_PROVEN`

`DEVICE_INITCALLS_COMPLETED=NOT_PROVEN`

`LATE_INITCALLS_COMPLETED=NOT_PROVEN`

`CONSOLE_ON_ROOTFS=NOT_PROVEN`

`/init=NOT_PROVEN`

`USB=FROZEN`

Current B 16-chain hashes and P15 prefix MATCH before/after both members.
Android A restored healthy. Partition writes 0. Slot A untouched.
`FS8_RERUN_FORBIDDEN=YES`. `FS1_RERUN_FORBIDDEN=YES`.
SUBSYS8/SUBSYS1/ARCH/POSTCORE/CORE/PURE/CONSOLE reruns remain forbidden.

Final gate: `R3_SLOT_B_FS_INITCALLS_CHECKPOINT_SHIFT_NOT_OBSERVED`.

Recommended next:
`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_FAILURE_ISOLATION_CI`.

Evidence: `artifacts/slot-b-fs-private-gate-20260917/`,
`artifacts/slot-b-fs8-20260917/`, `artifacts/slot-b-fs1-20260917/`.

## Failure isolation CI

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_FAILURE_ISOLATION_CI` completed
GHA-only. Public run `35230518371` at `f217326`. Private pack
`35233229575`. Independent private reverify `35234689905`. Observer
`35234636839` at `9db9b22`. No kernel rebuild, no device, Slot A
untouched. FS8/FS1 reruns remain forbidden.

Static forensic of failed FS8/FS1: `STATIC_DESIGN_DEFECT=NO`.
`HEAD_TEXT_RUNTIME_RX=HYPOTHESIS_UNPROVEN`.

CONTROL-A target `create_debug_debugfs_entry` `0xffff8000800149e0` /
`0x149e0` size 56. Forced `ENTRY_TRAMPOLINE` island `[0xffcc,0x10000)`
52B no-daifset. PREL32 `__initcall5_start` unchanged.

| | SHA-256 |
| --- | --- |
| CONTROL8 payload | `98d7f0ebff37af94f272ba5042da50e987073052fc018ab02d5e6c87ba626096` |
| CONTROL1 payload | `c219658aeec53697c4d29dfdaac0d2b5c671726e15831af677380678bb7864e2` |
| CONTROL8 boot | `2feff8bc1c055f5b2fade01e00c992b49277068b6a0f95d145cd31fe9a87ecc1` |
| CONTROL1 boot | `4551a94079ace87062f6a51444bfdbff76982e1b34b4b65658022df9e0c6db99` |

CONTROL-B midpoint index 26 `proc_meminfo_init` `0xffff800081b5770c` /
`0x1b5770c` size 76. Selected `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT`
window 60. PREL32 of that table slot unchanged.

| | SHA-256 |
| --- | --- |
| MID8 payload | `0dba6383a2f494bd33ba4623ef86eeb33cc8942961bf31b7d58c25d49c20c392` |
| MID1 payload | `ca98a432b8c8bb0f6035de47cf9f7b77b6d45fcffab3d8d8e9e5cf21611a2973` |
| MID8 boot | `89614d8a2d85ba53ca34d353db558fe8cbfc775740b85d3b1b899ef35bc7b4b0` |
| MID1 boot | `b2b7cd68a68886ebcc7f6fc598d22c7a27ecc9698a7397ec97b58271627c1499` |

Both pairs `DELAY_CONSTANT_ONLY`. Live tramp `[0x40,0x70)` identical.

`READY_FOR_FS_TRAMPOLINE_CONTROL_DEVICE_PAIR=YES`

`READY_FOR_FS_MIDPOINT_DEVICE_PAIR=YES`

Runtime unchanged: `FS_INITCALLS_COMPLETED=NOT_PROVEN`,
`FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN`.

Final gate: `R3_SLOT_B_FS_FAILURE_ISOLATION_CONTROLS_READY`.

## Upper-half inline pair

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_UPPER_HALF_BISECTION` used authoritative
53-entry table index 39 `chr_dev_init` (`0xffff800081b8cd40` / `0x1b8cd40`,
`drivers/char/mem.c`, 184B). Floor midpoint of proven index 26 and
first-device pseudo-index 53. INLINE only: preserved `paciasp` + 52B
no-daifset, CFG window 56. 60B ultracompact rejected (`cdac → cd78`).
PREL32 unchanged. Trampoline/island not used.

Public `35301142854` at `772fa97`. UPPER8 payload
`0f5b6e63b34e14260252a54afa7c9ec9f9ee7fb358a5a8ff90b3b712179d24ca`,
UPPER1 payload
`3a357674992f6be6e5adef14b774c7cf673218f38a4b14e237827947eca5b329`.
Pair DELAY_CONSTANT_ONLY 2 bytes `[0x1b8cd49,0x1b8cd4b)`. Independent
reverify PASS. Private pack `35301554578` / reverify `35301624269`.
Observer `35302378493` plus CORE/POSTCORE/ARCH/SUBSYS/FS/isolation
regressions PASS at `a177b95`.

| | SHA-256 | size |
| --- | --- | --- |
| UPPER8 boot | `bae4daac1fff579deaaf81707312373240a01bac7cf4a73b4abeac514d8fe9e9` | 37380096 |
| UPPER1 boot | `e68e1786d906258f46d15b66fb70b87e72b499698dca89c337f48d038dd5aa44` | 37380096 |

One UPPER8 then one UPPER1 RAM-only Slot B boot. Both
`AUTOMATIC_FASTBOOT_RETURN`, retry 7→6.

| | Sending | Booting | TOTAL |
| --- | --- | --- | --- |
| UPPER8 | OKAY 0.910s | OKAY 0.221s | `35.331862750s` |
| UPPER1 | OKAY 0.903s | OKAY 0.220s | `28.487730667s` |

- `PAIR_DELTA=-6.844132083s`
- `EXPECTED=-7.000000000s`
- `PAIR_ERROR=+0.155867917s`
- `UPPER_PAIR_VERDICT=STRONG`

`CHR_DEV_INIT_ENTRY=PROVEN`. Do not upgrade
`FS_INITCALLS_COMPLETED` or `FIRST_DEVICE_INITCALL_ENTRY`. Current B
16-chain and P15 prefix MATCH. Android A restored. Partition writes 0.
Slot A untouched. `UPPER8_RERUN_FORBIDDEN=YES`.
`UPPER1_RERUN_FORBIDDEN=YES`.

Final gate: `R3_SLOT_B_FS_UPPER_HALF_ENTRY_PROVEN`.

Next: continue inline-only bisection in index 39 → first-device.

Evidence: `artifacts/slot-b-fs-upper-20260918/`.



