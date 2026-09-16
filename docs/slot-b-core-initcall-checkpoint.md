# Slot B core-initcall completion checkpoint

## Scope and frozen evidence

This round is CI/source/binary audit and public payload preparation only. Public
GHA run `35102390662` at `da3228714baa9d4739d3035dc99643dd9b5bb90c`
reused authoritative kernel bundle `35040148509`; it did not rebuild the kernel,
pack a boot image, access a device or write a partition.

The preceding true-device result remains frozen: PURE8 `35.017469042s`, PURE1
`27.909857042s`, delta `-7.107612000s`, error `-0.107612000s`, STRONG.
Therefore `PURE_INITCALLS_COMPLETED=PROVEN` and
`FIRST_CORE_INITCALL_ENTRY=PROVEN`. This CI result does not advance runtime
evidence: `CORE_INITCALLS_COMPLETED=NOT_PROVEN` and
`FIRST_POSTCORE_INITCALL_ENTRY=NOT_PROVEN` until a separately authorized
matched true-device pair succeeds.

## Exact source boundary

Linux 6.6.156 commit `8b73de7da85fde281a385e0b26eda9bffd3ca477`
was checked in Actions after applying the frozen project patch queue.
`init/main.c` maps levels as follows and iterates each half-open interval:

- pure: `__initcall0_start..__initcall1_start`
- core: `__initcall1_start..__initcall2_start`
- postcore: `__initcall2_start..__initcall3_start`

`include/asm-generic/vmlinux.lds.h` orders the matching sections, while
`include/linux/init.h` and the exact config select 4-byte signed PREL32 entries
(`.long target - .`). Thus entering the first entry decoded at
`__initcall2_start` strictly follows completion of the core interval.
`CORE_COMPLETE_BOUNDARY_SOURCE_PROVEN=YES`.

## Authoritative table decode

All addresses below came from the exact GHA vmlinux, not System.map ordering.
The table is in `.init.data`; every entry is a 4-byte PREL32 displacement.

| boundary | link VA | Image offset | first decoded target |
| --- | --- | --- | --- |
| `__initcall1_start` | `0xffff800081d0a9d0` | `0x1d0a9d0` | `fpsimd_init` at `0xffff800081b33d74` |
| `__initcall2_start` | `0xffff800081d0ab6c` | `0x1d0ab6c` | `debug_monitors_init` at `0xffff800081b338a8` |
| `__initcall3_start` | `0xffff800081d0ac48` | `0x1d0ac48` | `reserve_memblock_reserved_regions` at `0xffff800081b33f60` |

The `__initcall2_start` word is `0xffe28d3c` (signed displacement
`-1929924`), resolving uniquely to `debug_monitors_init`. Exact source search
finds the unique registration in `arch/arm64/kernel/debug-monitors.c`:
`postcore_initcall(debug_monitors_init)`. The target is `.init.text`, link VA
`0xffff800081b338a8`, Image offset `0x1b338a8`, size exactly 60 bytes.

## Entry and range audit

The whole original function is 15 instructions:

```text
ffff800081b338a8: d503233f  paciasp
ffff800081b338ac: a9bf7bfd  stp x29, x30, [sp, #-0x10]!
ffff800081b338b0: 910003fd  mov x29, sp
ffff800081b338b4: 90fff781  adrp x1, 0xffff800081a23000
ffff800081b338b8: 91329421  add x1, x1, #0xca5
ffff800081b338bc: d0ff2703  adrp x3, 0xffff800080015000
ffff800081b338c0: 91113063  add x3, x3, #0x44c
ffff800081b338c4: 52800ec0  mov w0, #0x76
ffff800081b338c8: 52800022  mov w2, #0x1
ffff800081b338cc: aa1f03e4  mov x4, xzr
ffff800081b338d0: 2a1f03e5  mov w5, wzr
ffff800081b338d4: 97957404  bl __cpuhp_setup_state
ffff800081b338d8: a8c17bfd  ldp x29, x30, [sp], #0x10
ffff800081b338dc: d50323bf  autiasp
ffff800081b338e0: d65f03c0  ret
```

Entry bytes are `3f2303d5`; PAC is present and preserved. BTI is not a separate
entry instruction. Exact config has SCS, CFI and fentry disabled. The original
function has a stack frame; the replacement diagnostic does not use the stack.
There are no aliases, direct incoming branches to the entry, incoming branches
into the 60-byte overwrite interior, internal branches, back edges or literal
load instructions. The next symbol starts exactly at the window end, so the
60-byte probe does not cross a function boundary.

No relocation targets the window. `__ex_table` (994 decoded entries) and
`.altinstructions` (37287 decoded entries) have no overlap. Jump-label,
static-call and KCFI rewrite sections are absent. The vmlinux SHA remained
unchanged after audit. `CORE_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES` and
`FIRST_POSTCORE_ENTRY_AUDIT=PASS`.

## Exact frozen-baseline delta gate

The audit Image and frozen FIX8 differ in the target window at one instruction
only: Image `0x91329421`, FIX8 `0x9132b421`, at Image offset `0x1b338b8`.
The unchanged ADRP plus each ADD resolves respectively to offsets `0x1a23ca5`
and `0x1a23cad`. Both contain the exact NUL-terminated string
`arm64/debug_monitors:starting`, and the call resolves independently to
`__cpuhp_setup_state`. The admitted verdict is the target-specific
`CORE_INITCALL_NAME_LITERAL_ADDRESS_DELTA_VERIFIED`; it does not generalize any
prior literal waiver.

## 60-byte diagnostic

The historical 72-byte entry+compact core cannot fit the 60-byte function and
was rejected. The accepted design preserves the 4-byte `paciasp` entry and uses
a 56-byte ultra-compact core, ending exactly at the function boundary. It keeps
the same CNTPCT elapsed-time algorithm and PSCI reset primitive; frequency
scaling uses `LSL #3` for 8 seconds and `LSL #0` for 1 second. An ISB remains in
the polling loop before every current-counter read. It is stack-free, has no
normal-memory read/write, no MMIO and no relocation.

```text
msr DAIFSet,#0xf; mrs x9,CNTFRQ_EL0; lsl x10,x9,#delay
mrs x11,CNTPCT_EL0
loop: isb; mrs x12,CNTPCT_EL0; sub x13,x12,x11; cmp x13,x10; b.lo loop
movz/movk w0,0x84000009; smc #0
wfe; b wfe
```

SMC return therefore fails closed in WFE forever.
`CORE_CHECKPOINT_DIAGNOSTIC_SAFE=YES`.

## Public matched pair

| member | public payload SHA256 | checkpoint SHA256 |
| --- | --- | --- |
| CORE8 | `1e35411ba4d9bdeb48af47c0269a96b63a9214be5483601a9dfa5f8bdcfcc0a8` | `13746511fcfb13c65bfd19ca3651a1d1ee3607438e84a531ec54968455c69559` |
| CORE1 | `4ccf9e26edc0a37d2eade6a29c8dd73947b17dde57c0630dc1562616e3cf0704` | `a3246d73828b68f14fbe20ac1d34e09bd4a2ad14784954a6e95c94c5e6739abc` |

The pair changes exactly two bytes at `[0x1b338b5,0x1b338b7)`, both in
instruction index 3: `lsl x10,x9,#3` (`0xd37df12a`) becomes the semantically
1-second `0xd340fd2a`. No other payload byte changes. Expected future pair delta
is `-7.000s`; STRONG is absolute error `<=1.0s`, SUPPORTED `<=2.0s`.

Independent GHA reverify passed baseline-outside-window identity, table decode,
function extent, pair diff, timer/reset words, fail-closed tail, RT-D,
`/init` and initramfs identity. The baseline is frozen normal FIX8
`4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41`;
all prior REST/KINIT/FREE/SMP/INITCALLS/PURE/CONSOLE probes are absent. RT-D is
`4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`,
with only `bootargs` and `stdout-path` under `/chosen`; external initrd remains
false and `/init` is unchanged.

## Gate

`CORE_CHECKPOINT_SOURCE_AUDIT=PASS`

`CORE_CHECKPOINT_BINARY_AUDIT=PASS`

`CORE_CHECKPOINT_PROBE_SAFE=YES`

`CORE_PAIR_PUBLIC_READY=YES`

`READY_FOR_CORE_INITCALLS_PRIVATE_GATE=YES`

`MAINLINE_V2_R3_SLOT_B_CORE_INITCALLS_CHECKPOINT_CI_READY`

This is not device authorization. `CORE_PRIVATE_PACK=NO`,
`CORE_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`.
Recommended next round:
`MAINLINE_V2_R3_SLOT_B_CORE_INITCALLS_PRIVATE_GATE_FINALIZATION_CI`.
