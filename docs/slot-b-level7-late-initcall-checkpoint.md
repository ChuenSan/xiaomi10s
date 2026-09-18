# Slot B — level-7 earliest-safe inline checkpoint (device initcalls completion)

Round: `MAINLINE_V2_R3_SLOT_B_DEVICE_INITCALLS_COMPLETION_OR_BISECTION`
Path taken: A (direct level-7 completion checkpoint). Path B (level-6 midpoint)
was prepared but not needed.

## Question

`DEVICE_INITCALLS_COMPLETED` was `NOT_PROVEN` after the level-6 round proved the
earliest safe *level-6* entry (`cpuinfo_regs_init`, span index 1). Reaching a
level-7 entry is the cheapest possible direct proof that the whole level-6
("device") level returned, because `init/main.c` walks the levels strictly
sequentially:

```c
initcall_levels[] = { __initcall0_start, ... __initcall7_start, __initcall_end };
do_initcalls(): for (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++)
                    do_initcall_level(level, command_line);
```

So `selected level-7 entry reached  =>  do_initcall_level(6) returned  =>  all
1100 device initcalls returned`. The level loop runs before `init_post()`, so a
level-7 checkpoint cannot accidentally prove `CONSOLE_ON_ROOTFS` or `/init`.

## Boundary facts (frozen authoritative bundle, run 35040148509)

| symbol | VA |
| --- | --- |
| `__initcall6_start` | `0xffff800081d0b1a8` |
| `__initcall7_start` | `0xffff800081d0c2d8` |
| `__initcall_end` | `0xffff800081d0c430` |

Level-6 span = 1100 entries, level-7 span = 86 entries, level-5 frozen runtime
span = 53 entries. Level-7 is the last level, so its end is `__initcall_end`.

`__initcall_end` is the table **end marker**, not a boundary entry: it holds no
PREL32 word and `entry_va == end`, so it must be resolved as a plain symbol. The
first push routed it through `resolve_initcall_boundary` and died with
`INITCALL_TABLE_BOUNDARY_INVALID`.

## Selected target — index 0 (earliest possible)

```
symbol          kernel_do_mounts_initrd_sysctls_init
registration    late_initcall(kernel_do_mounts_initrd_sysctls_init)
source          init/do_mounts_initrd.c
table index     0        table entry VA 0xffff800081d0c2d8   PREL32 -1942112
target VA       0xffff800081b32078     Image offset 0x1b32078
function size   60 bytes exactly (window == function: a total rewrite)
entry           paciasp (3f2303d5)     BTI absent
```

The selector scans forward from index 0 and takes the first entry that passes the
safety gate: real late initcall, `function_size >= 56`, `paciasp` entry, no branch
target landing inside the 60-byte window, no incoming entry branch, CFG closure
proven. Index 0 passes with **zero** branches of any kind (0 incoming entry, 0
incoming window interior, 0 internal), so the scan never advances.

Probe: `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT` — the original `paciasp` word plus
the proven 56-byte CNTPCT/PSCI core. INLINE-only: no trampoline, no island, no
PREL32 retarget, no cross-function overwrite.

## Why the window/function equality is safe

The 60-byte window covers the whole function, ending exactly on the function
boundary. The probe ends in a fail-closed `wfe; b .` loop after the PSCI
`SYSTEM_RESET` (`smc 0x84000009`), so it never falls through into the next
function, and the removed `bl register_sysctl_init` / `ret` are never reached.

## Pre-device gates

| gate | result |
| --- | --- |
| public GHA `35353624700` @ `7405612c` | source-tests + decode + independent reverify all PASS |
| independent reverify | re-derives the level-7 table (86), re-runs the selector over the whole image, asserts index 0 / VA / size 60 / window 60 / architecture |
| CFG closure | `cfg_closure_proven=YES`, `surviving_into_interior=[]` |
| runtime rewrite tables | 0 overlaps in `__ex_table` / `.altinstructions` (`__jump_table`, `.static_call_sites`, `.kcfi_traps` absent) |
| window vs payload agreement | `FS_COMPLETE_LAYOUT_LITERAL_ADDRESS_DELTA_VERIFIED` — the two differing `add` immediates resolve to the identical `"kernel"` and `"kern_do_mounts_initrd_table"` literals, 8 bytes later in the frozen layout |
| `PREL32_TARGET_UNCHANGED` | YES |
| private pack `35354732517` | LATE_DEVPROBE8 boot `44e5001f…60fe8f`, LATE_DEVPROBE1 boot `0d24156e…22453`, each 37380096 bytes |
| private reverify-only `35354880397` | PASS, no rebuild, no repack |
| observer fixtures `35355539693` | PASS; the frozen level-6 devprobe fixtures and every other observer family also passed |

Pair diff: 2 bytes at `[0x1b32085,0x1b32087)` (probe word 3), `DELAY_CONSTANT_ONLY`
— the `lsl x10, x9, #3` (8 s) versus `ubfm` (1 s) delay encoding.

## Device round (RAM-only, one boot per member)

| member | image sha256 | total_s |
| --- | --- | --- |
| LATE_DEVPROBE8 | `44e5001fab6f7c662e1847972b886d1aa4f7a51e3f969b4dce834ae34b60fe8f` | 35.41181133300415 |
| LATE_DEVPROBE1 | `0d24156eeb37f31aceac314fe7df78a9dfaffd162134c3b5d7aa029d2e512453` | 28.56227325000509 |

`PAIR_DELTA=-6.849538082999061s`, `EXPECTED=-7.000000000s`,
`PAIR_ERROR=+0.15046191700093914s`, `|error| <= 1.0s` → **STRONG**.

Both members returned automatically (retry 7→6), `STATUS=AUTOMATIC_FASTBOOT_RETURN`,
one experimental boot each, no second boot of any member.

Integrity: 16-chain hashes and the P15 prefix (`133e063b…7d34`) matched
pre / between / post; `PARTITION_WRITES=0`; `SLOT_A_WRITTEN=NO`; Slot A was never
written, erased or formatted; Slot B was reached only via `--set-active`
(persistent boot state, no image write); healthy stock Android A
(`4.19.157-perf-g9d90dd04aa7c`, `_a`) restored.

## Runtime evidence delta

Newly PROVEN:
`DEVICE_INITCALLS_COMPLETED`, `FIRST_LATE_INITCALL_ENTRY`,
`KERNEL_DO_MOUNTS_INITRD_SYSCTLS_INIT_ENTRY`.

Unchanged (must stay NOT_PROVEN): `LATE_INITCALLS_COMPLETED`,
`WAIT_FOR_INITRAMFS_RETURN`, `CONSOLE_ON_ROOTFS`, `INIT_EXECUTED`.
`USB=FROZEN`.

Already PROVEN and untouched: `FS_INITCALLS_COMPLETED`,
`FIRST_DEVICE_INITCALL_ENTRY`, `CPUINFO_REGS_INIT_ENTRY`.

Final gate: `MAINLINE_V2_R3_SLOT_B_DEVICE_INITCALLS_COMPLETED_PROVEN`.
Next stage: `LATE_INITCALLS_COMPLETED_HANDOFF`.

## Frozen / forbidden

LATE_DEVPROBE8 and LATE_DEVPROBE1 are consumed: no rerun. Every earlier pair
remains forbidden to rerun. The historical trampoline/island reachability probe
stays retired.

Evidence: `artifacts/slot-b-level7-20260918/` (`ci/`, `pair/`, `private/`,
`device-round/`).
