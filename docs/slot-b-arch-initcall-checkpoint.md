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

`ARCH_PRIVATE_PACK=NO`

`ARCH_DEVICE_OPERATION=NO`

Final public-CI gate: `MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_CHECKPOINT_CI_READY`.
It authorizes no device operation. Recommended next, only after explicit user
approval: `MAINLINE_V2_R3_SLOT_B_ARCH_INITCALLS_PRIVATE_GATE_FINALIZATION_CI`.
