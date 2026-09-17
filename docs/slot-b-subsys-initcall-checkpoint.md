# Slot B subsys-initcall completion checkpoint

## Scope

`MAINLINE_V2_R3_SLOT_B_SUBSYS_INITCALLS_CHECKPOINT_CI_AUDIT` is complete.
Public GHA run `35193200415` at `06f567b7f2f8c207862a937a1418fd8c30b44f7c`
reused authoritative Linux 6.6.156 bundle `35040148509`. It performed source
audit, initcall-table decode, exact first-FS target identity and CFG dump.
It did not rebuild the kernel, pack a private boot image, access a device or
write a partition. It did not emit SUBSYS8/SUBSYS1 payloads.

Frozen ARCH runtime remains `ARCH_INITCALLS_COMPLETED=PROVEN` and
`FIRST_SUBSYS_INITCALL_ENTRY=PROVEN`. This CI result does not advance
runtime evidence.

## Exact source boundary

Exact Linux 6.6.156 `init/main.c`, `include/linux/init.h`,
`include/asm-generic/vmlinux.lds.h` and `arch/arm64/Kconfig` map:

- subsys runtime interval: `__initcall4_start..__initcall5_start`
- fs runtime interval: `__initcall5_start..__initcall6_start`
- linker order after level 5: `INIT_CALLS_LEVEL(rootfs)` then `6`

arm64 selects `HAVE_ARCH_PREL32_RELOCATIONS`; entries are 4-byte signed
PREL32 (`.long stub - .`). Entering the first target decoded at
`__initcall5_start` therefore strictly follows completion of the subsys
interval.

`SUBSYS_LEVEL_BOUNDARY_SOURCE_PROVEN=YES`

`FIRST_FS_ENTRY_IMPLIES_SUBSYS_COMPLETE=YES`

`INITCALL_ENTRY_ENCODING=PREL32`

## Table decode

All values below were decoded from the authoritative vmlinux, never inferred
from System.map ordering. Table uniqueness checked the full PREL32 initcall
table. Linker order `va4 < va5 < va_rootfs < va6` was required and passed.

| boundary | link VA | Image offset |
| --- | --- | --- |
| `__initcall4_start` | `0xffff800081d0ae0c` | `0x1d0ae0c` |
| `__initcall5_start` | `0xffff800081d0b0d4` | `0x1d0b0d4` |
| `__initcallrootfs_start` | `0xffff800081d0b1a4` | `0x1d0b1a4` |
| `__initcall6_start` | `0xffff800081d0b1a8` | `0x1d0b1a8` |

The `__initcall5_start` word is `0xfe30990c`, signed displacement
`-30369524`, and uniquely resolves to `create_debug_debugfs_entry` at
`0xffff8000800149e0`, Image offset `0x149e0`. Alias set is exactly that
symbol. Registration is `fs_initcall(create_debug_debugfs_entry)` in
`arch/arm64/kernel/debug-monitors.c`.

`FIRST_FS_INITCALL_TARGET_UNIQUE=PASS`

## Target / CFG audit

The target is `.text`, 56 bytes, entry `paciasp` `3f2303d5`. PAC is present;
BTI/SCS/CFI/fentry are off. The function is a straight line: frame setup,
ADRP/ADD for the `debug_enabled` name and variable, `bl debugfs_create_bool`,
zero return, `autiasp`, `ret`. No internal branches, no back-edges, no
forward edges inside the function.

The probe window is derived from this CFG, not copied from topology_init's
160-byte ARCH solution. Minimum proven diagnostic is preserved `paciasp`
plus the 56-byte CNTPCT/PSCI `0x84000009` fail-closed WFE core: 60 bytes.
56 < 60, so the proven core cannot be placed without covering the next
symbol. Hard-stuffing, inheriting ARCH 160B, and shrinking the proven core
were all rejected this round.

`FIRST_FS_ENTRY_AUDIT=PASS`

`SUBSYS_PROBE_WINDOW_DERIVED_FROM_TARGET_CFG=YES`

`SUBSYS_CHECKPOINT_PROBE_SAFE=NO`

`PROBE_LARGER_THAN_TARGET_FUNCTION`

## Public matched pair

Not generated. Pair diff, independent reverify and private-gate readiness
are blocked until a later probe redesign that stays inside the 56-byte
function or uses a proven entry-preserving trampoline.

`SUBSYS_PAIR_PUBLIC_READY=NO`

`READY_FOR_SUBSYS_INITCALLS_PRIVATE_GATE=NO`

`SUBSYS_PRIVATE_PACK=NO`

`SUBSYS_DEVICE_OPERATION=NO`

## Gate

`SUBSYS_CHECKPOINT_SOURCE_AUDIT=PASS`

`SUBSYS_CHECKPOINT_BINARY_AUDIT=PASS`

`FIRST_FS_TARGET_IDENTITY=PASS`

`SUBSYS_FUNCTION_RANGE_SAFE=NO`

The public-CI gate is
`R3_SLOT_B_SUBSYS_INITCALLS_CHECKPOINT_PREDEVICE_NOT_READY`.
It authorized no device operation. Recommended next, only after explicit
user approval: redesign the first-FS probe. Do not skip to FS completion
and do not run a device experiment.

Evidence: `artifacts/slot-b-subsys-initcall-20260917/`.
