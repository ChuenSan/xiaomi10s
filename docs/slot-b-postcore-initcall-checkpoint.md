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

`PRIVATE_PACK=NO`

`DEVICE_OPERATION=NO`

`SLOT_A_WRITTEN=NO`

Final gate: `MAINLINE_V2_R3_SLOT_B_POSTCORE_INITCALLS_CHECKPOINT_CI_READY`.
This is not device authorization. Wait for explicit user approval before any
private pack, observer freeze or device stage.
