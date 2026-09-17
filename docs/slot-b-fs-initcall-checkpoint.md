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

Final gate: `MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_CHECKPOINT_CI_READY`.

This is not device authorization.

Recommended next, after separate approval:
`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_PRIVATE_GATE_FINALIZATION_CI`.
SUBSYS8/SUBSYS1/ARCH/POSTCORE/CORE/PURE/CONSOLE reruns remain forbidden.

Evidence: `artifacts/slot-b-fs-initcall-redesign-20260917-r2/`.
