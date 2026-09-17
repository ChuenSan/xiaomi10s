# Slot B FS-initcall completion checkpoint

## Scope

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_CHECKPOINT_CI_AUDIT` is complete.
Public GHA run `35208519342` at `736c96ea348989a708f7638c2dfd6409aac1798c`
reused authoritative Linux 6.6.156 bundle `35040148509`. It proved linker
and runtime traversal semantics for fs/rootfs/device, enumerated the level-5
PREL32 span, and decoded the first device entry. It did not rebuild the
kernel, generate an FS8/FS1 payload pair, pack a private boot image, access a
device or write a partition.

Frozen SUBSYS runtime remains `SUBSYS_INITCALLS_COMPLETED=PROVEN` and
`FIRST_FS_INITCALL_ENTRY=PROVEN`. This CI result does not advance runtime
evidence.

## Exact source / linker / runtime semantics

Exact Linux 6.6.156 maps:

- `INIT_CALLS` linker order: `0,1,2,3,4,5,rootfs,6,7`
- `INIT_CALLS_LEVEL(level)` sets `__initcall##level##_start = .` then keeps
  `.initcall##level##.init` and `.initcall##level##s.init`
- `fs_initcall` → 5, `fs_initcall_sync` → 5s, `rootfs_initcall` → rootfs,
  `device_initcall` / `__initcall` → 6
- `initcall_levels[]` is `0..7,end` and does **not** name
  `__initcallrootfs_start`
- `do_initcall_level(level)` walks `[initcall_levels[level], initcall_levels[level+1])`
  via PREL32 `initcall_from_entry`
- therefore `do_initcall_level(5)` is `[__initcall5_start, __initcall6_start)`
- rootfs entries are linker-placed between 5 and 6, so they execute in the
  same level-5 loop
- `populate_rootfs` is `rootfs_initcall(populate_rootfs)` in
  `init/initramfs.c`; `wait_for_initramfs` is later and is not an initcall
  pass
- arm64 `vmlinux.lds.S` emits `INIT_CALLS` in `.init.data`

`FS_LINKER_ORDER_PROVEN=YES`

`ROOTFS_LINKER_POSITION_PROVEN=YES`

`ROOTFS_HAS_SEPARATE_RUNTIME_PASS=NO`

`ROOTFS_INCLUDED_IN_LEVEL5_TRAVERSAL=YES`

`ROOTFS_START_IS_MARKER_ONLY=YES`

`FIRST_DEVICE_ENTRY_IMPLIES_FS_COMPLETE=YES`

`INITCALL_ENTRY_ENCODING=PREL32`

## Independently reconfirmed VAs

| boundary | link VA | Image offset |
| --- | --- | --- |
| `__initcall5_start` | `0xffff800081d0b0d4` | `0x1d0b0d4` |
| `__initcallrootfs_start` | `0xffff800081d0b1a4` | `0x1d0b1a4` |
| `__initcall6_start` | `0xffff800081d0b1a8` | `0x1d0b1a8` |

`__initcallrootfs_start` is a linker marker, not a callable. The one PREL32
between it and `__initcall6_start` is `populate_rootfs`.

## Level-5 runtime span

`FS_RUNTIME_SPAN_ENTRY_COUNT=53`

`ROOTFS_ENTRY_COUNT=1`

`ROOTFS_ENTRIES_BETWEEN_ROOTFS_AND_6=1`

First FS identity reconfirmed: `create_debug_debugfs_entry` at
`0xffff8000800149e0` / Image `0x149e0`,
`fs_initcall(create_debug_debugfs_entry)` in
`arch/arm64/kernel/debug-monitors.c`. Runtime remains
`FIRST_FS_INITCALL_ENTRY=PROVEN` and `FIRST_FS_INITCALL_BODY=NOT_PROVEN`.

The sole rootfs entry is `populate_rootfs` at `0xffff800081b32388`,
`rootfs_initcall(populate_rootfs)` in `init/initramfs.c`. It executes inside
`do_initcall_level(5)`.

## FS-complete causal boundary

Entering the first target decoded at `__initcall6_start` strictly follows
completion of `[__initcall5_start, __initcall6_start)`, including the rootfs
entry. The checkpoint must sit on that real next runtime function. The
initcall table is not rewritten.

`FS_COMPLETE_CAUSAL_BOUNDARY_SYMBOL=register_arm64_panic_block`

`FS_COMPLETE_CAUSAL_BOUNDARY_REASON=do_initcall_level(5) end is __initcall6_start; rootfs is inside that span`

`FIRST_DEVICE_ENTRY_IMPLIES_FS_COMPLETE=YES`

## First device PREL32 decode

| field | value |
| --- | --- |
| table entry VA | `0xffff800081d0b1a8` |
| entry word | `0xffe29610` |
| signed displacement | `-1927664` |
| target VA | `0xffff800081b347b8` |
| Image offset | `0x1b347b8` |
| symbol | `register_arm64_panic_block` |
| source | `arch/arm64/kernel/setup.c` |
| registration | `device_initcall(register_arm64_panic_block)` |
| section | `.init.text` |
| size | 48 |
| unique | PASS |

`FS_COMPLETE_TARGET_UNIQUE=PASS`

## Entry / CFG

Entry0 is `paciasp` `d503233f` / `3f2303d5`. PAC yes; BTI no. The 48-byte
function is a straight line: frame setup, two ADRP/ADD pairs, `bl
atomic_notifier_chain_register`, `mov w0, wzr`, frame teardown, `autiasp`,
`ret`. No internal back-edge. The 52-byte no-daifset core plus preserved
`paciasp` needs 56 bytes and does not fit. A 60-byte ultracompact overlay
also does not fit. Probe window was not derived because no inline core fits.

`FS_COMPLETE_TARGET_ENTRY_AUDIT=PASS` for identity/disassembly.

`FS_PROBE_WINDOW_DERIVED_FROM_TARGET_CFG=NO`

`FS_CFG_CLOSURE_PROVEN=NO`

`FS_CHECKPOINT_RUNTIME_REWRITE_SAFE=NO` (no candidate window)

`FS8` / `FS1` were not generated. Pair diff is not applicable.

`FS_ALL_PRIOR_STAGE_PROBES_REMOVED=YES` (no new payload; baseline untouched)

## Gate

`FS_CHECKPOINT_SOURCE_AUDIT=PASS`

`FS_CHECKPOINT_BINARY_AUDIT=PASS` for span and first-device decode

`FS_PAIR_PUBLIC_READY=NO`

`READY_FOR_FS_INITCALLS_PRIVATE_GATE=NO`

Runtime evidence is unchanged:

`FIRST_FS_INITCALL_BODY=NOT_PROVEN`

`FS_INITCALLS_COMPLETED=NOT_PROVEN`

`FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN`

`DEVICE_INITCALLS_COMPLETED=NOT_PROVEN`

`LATE_INITCALLS_COMPLETED=NOT_PROVEN`

`CONSOLE_ON_ROOTFS_ENTRY=NOT_PROVEN`

`/init=NOT_PROVEN`

`USB=FROZEN`

Final gate: `R3_SLOT_B_FS_INITCALLS_CHECKPOINT_PREDEVICE_NOT_READY`.

Recommended next, CI-only after separate approval: an entry-preserving
trampoline (or a still-smaller independently audited core) at
`register_arm64_panic_block`. Do not skip to device-complete. Do not run a
true-device experiment. SUBSYS8/SUBSYS1/ARCH/POSTCORE/CORE/PURE/CONSOLE
reruns remain forbidden.

Evidence: `artifacts/slot-b-fs-initcall-20260917/`.
