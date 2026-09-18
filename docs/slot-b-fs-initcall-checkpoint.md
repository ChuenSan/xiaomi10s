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

## Post-39 inline pair

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_POST39_INLINE_BISECTION` used
authoritative 53-entry table index 46 `af_unix_init`
(`0xffff800081bae798` / `0x1bae798`, `net/unix/af_unix.c`, 216B). Floor
midpoint of proven index 39 and first-device pseudo-index 53. INLINE
only: preserved `paciasp` + 56B ultracompact, CFG window 60. PREL32
unchanged. Trampoline/island not used.

Public `35315008166` at `762edbc`. POST39_8 payload
`cec40af0f6096e330e2455c30cbc34ed935bbd5cb8473e39c6865654a48accc0`,
POST39_1 payload
`e9e4bcca4d8d3226005990d6eb24ebb658c11ef5d921baa6d9519d0a9c1b936b`.
Pair DELAY_CONSTANT_ONLY 2 bytes `[0x1bae7a5,0x1bae7a7)`. Independent
reverify PASS. Private pack `35315583867` / reverify `35315692138`.
Observer `35315984122` plus CORE/POSTCORE/ARCH/SUBSYS/FS/isolation
regressions PASS at `57485ba`.

| | SHA-256 | size |
| --- | --- | --- |
| POST39_8 boot | `b1ba8335dd671a9d026783e5539547fb2df3d314e7d8757b769b823967d1d4d6` | 37380096 |
| POST39_1 boot | `23a24d95ac8fe17229b3e425d777b3b7938d32c110a8070546836aaba79f6e8f` | 37380096 |

One POST39_8 then one POST39_1 RAM-only Slot B boot. Both
`AUTOMATIC_FASTBOOT_RETURN`, retry 7→6.

| | Sending | Booting | TOTAL |
| --- | --- | --- | --- |
| POST39_8 | OKAY 0.919s | OKAY 0.221s | `35.401581125s` |
| POST39_1 | OKAY 0.914s | OKAY 0.220s | `28.351287500s` |

- `PAIR_DELTA=-7.050293625s`
- `EXPECTED=-7.000000000s`
- `PAIR_ERROR=-0.050293625s`
- `POST39_PAIR_VERDICT=STRONG`

`AF_UNIX_INIT_ENTRY=PROVEN`. Do not upgrade
`FS_INITCALLS_COMPLETED` or `FIRST_DEVICE_INITCALL_ENTRY`. Current B
16-chain and P15 prefix MATCH. Android A restored. Partition writes 0.
Final gate: `R3_SLOT_B_FS_POST39_ENTRY_PROVEN`.

Evidence: `artifacts/slot-b-fs-post39-20260918/`.

## Post-46 inline pair

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_POST46_INLINE_BISECTION` used
authoritative 53-entry table index 49 `vlan_offload_init`
(`0xffff800081baedfc` / `0x1baedfc`, `net/8021q/vlan_core.c`, 60B). Floor
midpoint of proven index 46 and first-device pseudo-index 53. INLINE
only: preserved `paciasp` + 56B ultracompact, CFG window 60. PREL32
unchanged. Trampoline/island not used.

Public `35319626212` at `38c12e1`. POST46_8 payload
`fe4d52eae539b1d65afe71f6d067da341a48842540e46cf5a493d4f221b5c2d1`,
POST46_1 payload
`ef0da933d52f9ba2a5c432bccecded31cf497843240e720fa386ebbd637f6490`.
Pair DELAY_CONSTANT_ONLY 2 bytes `[0x1baee09,0x1baee0a)`. Independent
reverify PASS. Private pack `35320432106` / reverify `35320507360`.
Observer `35320679232` plus CORE/POSTCORE/ARCH/SUBSYS/FS/isolation
regressions PASS at `9bea4d7`.

| | SHA-256 | size |
| --- | --- | --- |
| POST46_8 boot | `4092ceaedb54f94fe6079cdf987fd719620a712465fee30d9fd20b8a3e5dc843` | 37380096 |
| POST46_1 boot | `f0b80158e90f91f8dbbb47cd84f8b92be93d86cad9690514859af3629061ea32` | 37380096 |

One POST46_8 then one POST46_1 RAM-only Slot B boot. Both
`AUTOMATIC_FASTBOOT_RETURN`, retry 7→6.

| | Sending | Booting | TOTAL |
| --- | --- | --- | --- |
| POST46_8 | OKAY 0.912s | OKAY 0.220s | `35.374136875s` |
| POST46_1 | OKAY 0.939s | OKAY 0.227s | `28.311953000s` |

- `PAIR_DELTA=-7.062183875s`
- `EXPECTED=-7.000000000s`
- `PAIR_ERROR=-0.062183875s`
- `POST46_PAIR_VERDICT=STRONG`

`VLAN_OFFLOAD_INIT_ENTRY=PROVEN`. Do not upgrade
`FS_INITCALLS_COMPLETED` or `FIRST_DEVICE_INITCALL_ENTRY`. Current B
16-chain and P15 prefix MATCH. Android A restored. Partition writes 0.
Slot A untouched. `POST468_RERUN_FORBIDDEN=YES`.
`POST461_RERUN_FORBIDDEN=YES`.

Final gate: `R3_SLOT_B_FS_POST46_ENTRY_PROVEN`.

Next: continue inline-only bisection in index 49 → first-device (pseudo 53).

Evidence: `artifacts/slot-b-fs-post46-20260918/`.

## Post-49 inline pair

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_POST49_INLINE_BISECTION` used
authoritative 53-entry table index 51 `acpi_reserve_resources`
(`0xffff800081b6b2fc` / `0x1b6b2fc`, `drivers/acpi/osl.c`, 256B). Floor
midpoint of proven index 49 and first-device pseudo-index 53. INLINE
only: preserved `paciasp` + 56B ultracompact, CFG window 60. PREL32
unchanged. Trampoline/island not used.

Public `35329721571` at `8696732`. POST49_8 payload
`ce749ac143dd42bc6ded9fe9bcc0808c31b9347b84e7e2122ae4dba6b6a88378`,
POST49_1 payload
`2be85c5beac519c80cdd1c8b42847a9f70735174366578cf35ed1a3ba930797a`.
Pair DELAY_CONSTANT_ONLY 2 bytes `[0x1b6b309,0x1b6b30a)`. Independent
reverify PASS. Private pack `35330249339` / reverify `35330316795`.
Observer `35330479511` PASS at `dcc2168`.

| | SHA-256 | size |
| --- | --- | --- |
| POST49_8 boot | `c8ff8dc637d80ef1b0d0a3dbab6869f3879450998a9df546e2af25cea64b2a14` | 37380096 |
| POST49_1 boot | `73c63cf6360a962d7fc555f65281aef23da1864ff185f30dfa693d69e8862a6c` | 37380096 |

One POST49_8 then one POST49_1 RAM-only Slot B boot. Both
`AUTOMATIC_FASTBOOT_RETURN`, retry 7→6.

| | Sending | Booting | TOTAL |
| --- | --- | --- | --- |
| POST49_8 | OKAY 0.917s | OKAY 0.221s | `35.434585083s` |
| POST49_1 | OKAY 0.913s | OKAY 0.221s | `28.439815292s` |

- `PAIR_DELTA=-6.994769791s`
- `EXPECTED=-7.000000000s`
- `PAIR_ERROR=0.005230209s`
- `POST49_PAIR_VERDICT=STRONG`

`ACPI_RESERVE_RESOURCES_ENTRY=PROVEN`. Do not upgrade
`FS_INITCALLS_COMPLETED` or `FIRST_DEVICE_INITCALL_ENTRY`. Current B
16-chain and P15 prefix MATCH. Android A restored. Partition writes 0.
Slot A untouched. `POST498_RERUN_FORBIDDEN=YES`.
`POST491_RERUN_FORBIDDEN=YES`.

## Post-51 inline pair (Final Level 5 entry: populate_rootfs)

`MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_FINAL_INLINE_BISECTION` tested authoritative 53-entry table index 52 `populate_rootfs` (`0xffff800081b32388` / `0x1b32388`, `init/initramfs.c`, `rootfs_initcall`, 88B). This is the final initcall in Level 5 before `__initcall6_start`. INLINE only: preserved `paciasp` + 56B ultracompact, CFG window 60B. PREL32 unchanged. Trampoline/island not used.

Public `35332535696` at `55e8ddc`. POST51_8 payload `841fbb7135d2bc8881beeedf3f97a6842290ff934a406b7c287cddef565208b5`, POST51_1 payload `60477426b24458e19204fc4a3f0b9479968059eb174bbf045ea4e18e7027748b`. Pair DELAY_CONSTANT_ONLY 2 bytes `[0x1b32395,0x1b32397)`. Independent reverify PASS. Private pack `35333095217` / reverify `35333156029`. Observer `35333239931` PASS at `7629ea4`.

| | SHA-256 | size |
| --- | --- | --- |
| POST51_8 boot | `7d6e527c977b3dd08d9f4896d44648bc7b9020993a8841e91285c84c67cc81ae` | 37380096 |
| POST51_1 boot | `3c825488ba0b41a534369a476f05f3b20c1279f017275212dc52d4761e3d9d1a` | 37380096 |

One POST51_8 then one POST51_1 RAM-only Slot B boot. Both `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6.

| | Sending | Booting | TOTAL |
| --- | --- | --- | --- |
| POST51_8 | OKAY 0.902s | OKAY 0.220s | `35.055794459s` |
| POST51_1 | OKAY 0.915s | OKAY 0.220s | `28.236344500s` |

- `PAIR_DELTA=-6.819449959s`
- `EXPECTED=-7.000000000s`
- `PAIR_ERROR=0.180550041s`
- `POST51_PAIR_VERDICT=STRONG`

`POPULATE_ROOTFS_ENTRY=PROVEN`. All 53 initcalls in Level 5 (`[__initcall5_start, __initcall6_start)`) have their entry execution PROVEN.
Do not upgrade `FS_INITCALLS_COMPLETED` or `FIRST_DEVICE_INITCALL_ENTRY`. Current B 16-chain and P15 prefix MATCH. Android A restored. Partition writes 0. Slot A untouched. `POST518_RERUN_FORBIDDEN=YES`. `POST511_RERUN_FORBIDDEN=YES`.

Final gate: `R3_SLOT_B_FS_POST51_ENTRY_PROVEN`.

Final unresolved boundary: Adjacent initcalls `[52, 53)`:
- Index 52: `populate_rootfs` entry (**PROVEN**)
- Index 53: `register_arm64_panic_block` entry (`device_initcall`, first device initcall, **SHIFT_NOT_OBSERVED**)

Evidence: `artifacts/slot-b-fs-post51-20260918/`.

## Populate_rootfs return isolation

`MAINLINE_V2_R3_SLOT_B_FS_POPULATE_ROOTFS_RETURN_ISOLATION` is CI-only.
Public isolation `35339942693` and observer `35339942856` at `31efc13`.
Authoritative Linux 6.6.156 bundle `35040148509` / FIX8
`4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41`.
No kernel rebuild, no pair composition, no private pack, no device.

Exact 88B `populate_rootfs` at `0xffff800081b32388` / Image `0x1b32388`:

| off | insn | meaning |
| --- | --- | --- |
| `+0x00` | `paciasp` | POST51 ENTRY (PROVEN) |
| `+0x24` | `bl async_schedule_node_domain` | schedule only |
| `+0x28` | cookie `str` | P1 first post-schedule insn |
| `+0x34` | `bl __usermodehelper_set_disable_depth` | `usermodehelper_enable` |
| `+0x40` | `cbnz` → `+0x48` | default `initramfs_async=true` skips wait |
| `+0x44` | `bl wait_for_initramfs` | dead on thyme cmdline |
| `+0x48` | `mov w0, wzr` | P2 join / epilogue |
| `+0x54` | `ret` | function end; next is `do_populate_rootfs` |

P1 remaining `[+0x28, +0x58)` = 48B `<` 52B proven core.
P2 remaining `[+0x48, +0x58)` = 16B.
48B `select_fs_complete_core` would pick `ENTRY_TRAMPOLINE`; island is
forbidden. Shared `do_initcall_level` / `do_one_initcall` after-return
sites are rejected (`SHARED_DO_INITCALL_LEVEL`). Cross-function into
`do_populate_rootfs` is rejected.

Thyme RT-D bootargs `rdinit=/init panic=5 loglevel=7` do not set
`initramfs_async=`. Default true: `populate_rootfs` returns without
waiting for `do_populate_rootfs`. Old first-device trampoline
`SHIFT_NOT_OBSERVED` does not prove non-return.

No 8s/1s pair was generated.

Runtime unchanged:

`POPULATE_ROOTFS_ENTRY=PROVEN`

`FS_INITCALLS_COMPLETED=NOT_PROVEN`

`FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN`

Final gate: `R3_SLOT_B_POPULATE_ROOTFS_RETURN_ISOLATION_NOT_READY`.

Evidence: `artifacts/slot-b-fs-rootfs-return-20260918/`.

## Last level-5 return gated inline probe

`MAINLINE_V2_R3_SLOT_B_FS_LAST_INITCALL_RETURN_GATED_PROBE` is a CI-only
static audit. Public GHA run `35343586849` at `040e167` reused the
authoritative Linux 6.6.156 bundle `35040148509` and downloaded the frozen
FIX8 payload (sha256
`4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41`). It did
not rebuild the kernel, pack a private boot image, access a device or write a
partition.

Causal boundary (source at `8b73de7da85fde281a385e0b26eda9bffd3ca477`):
`INIT_CALLS_LEVEL(5)` -> `INIT_CALLS_LEVEL(rootfs)` -> `INIT_CALLS_LEVEL(6)`
in `include/asm-generic/vmlinux.lds.h`, so the single
`rootfs_initcall(populate_rootfs)` entry sits at the END of level 5, at table
slot `0xffff800081d0b1a4` (`__initcall6_start - 4`), PREL32 `-1936924`
decoding to `0xffff800081b32388`. `do_initcall_level(5)` iterates
`[__initcall5_start, __initcall6_start)` = 53 PREL32 entries sequentially and
returns only after `do_one_initcall` returned for all of them, last of which
is `populate_rootfs`. So `LEVEL5_RETURN_IMPLIES_FS_COMPLETE=YES`.

Gated condition audited: level == 5 AND the current initcall slot ==
`0xffff800081d0b1a4` (or equivalently the decoded fn == `populate_rootfs`).
Candidate inline sites and spare bytes:

- `do_initcall_level` loop-exit block `0xffff800081b312fc`: 20B, the shared
  epilogue entered by both the normal loop exit and the `b.hs` early skip at
  `0xffff800081b312dc`; spare 0B.
- `do_initcalls` post-level block `0xffff800081b31224`: 64B, of which 40B is
  live on every level (loop increment + boundary check + epilogue) and 24B is
  a cold kmalloc-failure block whose repurposing changes caller semantics;
  spare 0B.
- `do_one_initcall` post-`blr x19` tail `0xffff800080014458`: 104B, fully
  live for every initcall; spare 0B.
- `do_one_initcall` tracepoint-finish block `0xffff80008001454c`: 68B, guarded
  by the runtime-patchable static key read at `0xffff800080014458`
  (`cbnz w8`) and therefore neither provably dead nor uniquely bound.

Probe geometry: a unique gate needs an absolute comparison
(adrp + add + cmp + b.cond = 16B), or 8B where the level register is already
live; the frozen, device-proven CNTPCT + PSCI `0x84000009` + WFE core is 52B.
Minimum inline footprint is therefore 60B, and every displaced live
instruction must be re-materialised inside the same function. No candidate
function carries trailing padding (`do_initcalls` ends exactly at
`0xffff800081b31264`; `do_initcall_level` exactly at `0xffff800081b31310`),
so the tightest deficit is `MIN_INLINE_DEFICIT_BYTES=60`.

Rejected: unconditional shared-caller probe, out-of-function trampoline,
island, code cave, `PREL32` or table-order change, any change to a non-target
iteration, loss of the loop increment or boundary check, cross-function
overwrite, runtime rewrite / incoming-branch conflict.

No 8s/1s pair was generated (`PAIR_GENERATED=NO`, `LASTRET8_GENERATED=NO`,
`LASTRET1_GENERATED=NO`), so no public pack, no private pack, no observer and
no device boot occurred this round. The old first-device trampoline
`SHIFT_NOT_OBSERVED` still does not prove `populate_rootfs` non-return.

Runtime unchanged:

`POPULATE_ROOTFS_RETURN=NOT_PROVEN`

`FS_INITCALLS_COMPLETED=NOT_PROVEN`

`FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN`

Final gate: `R3_SLOT_B_FS_LAST_RETURN_GATED_PROBE_NOT_READY`.

Evidence: `artifacts/slot-b-fs-lastinitcall-gated-20260918/`.

## Level-6 earliest safe inline checkpoint

`MAINLINE_V2_R3_SLOT_B_FS_COMPLETE_VIA_LEVEL6_INLINE_CHECKPOINT` retires the
non-injectable `LAST_LEVEL5_RETURN` checkpoint and instead proves FS completion
from the **level-6 side**: it selects the earliest *safe* level-6
(`device_initcall`) entry and places the inline matched-delay probe there.

Causal chain (source `8b73de7`, bundle `35040148509`): `do_initcall_level(5)`
walks `[__initcall5_start, __initcall6_start)` and returns only after the last
of its 53 entries; `__initcall6_start` then begins the level-6 span. Reaching
any real level-6 entry N therefore implies level-5 returned, hence
`FS_INITCALLS_COMPLETED=PROVEN` and `FIRST_DEVICE_INITCALL_ENTRY=PROVEN`. When N
is not the first entry the entries before it are recorded as sequentially
completed, but `DEVICE_INITCALLS_COMPLETED` is **not** upgraded.

### Selection rule and target

Additive `checkpoint.py` symbol `level6_earliest` decodes
`[__initcall6_start, __initcall7_start)` (1100 PREL32 entries), then walks from
index 0 and returns the first entry whose function extent fits an inline probe
(`>=56B` for the proven 52B core, `>=60B` for the proven 56B core) and whose
entry window is CFG-closed (no incoming branch into the window interior, no
incoming branch to the entry). Trampoline, island, code cave, `PREL32`
retarget, table-order change and shared `do_initcall*` checkpoints remain
rejected.

Decoded and frozen:

| index | symbol | VA / offset | size | registration | result |
| --- | --- | --- | --- | --- | --- |
| 0 | `register_arm64_panic_block` | `0xffff800081b347b8` / `0x1b347b8` | 48 | `device_initcall` | skipped `TOO_SMALL` |
| **1** | **`cpuinfo_regs_init`** | **`0xffff800081b34d8c` / `0x1b34d8c`** | **220** | **`device_initcall(cpuinfo_regs_init)`** | **selected** |

Selected target: table slot `0xffff800081d0b1ac` (PREL32 `-1926176`), source
`arch/arm64/kernel/cpuinfo.c`, entry `paciasp`, `BTI=ABSENT`. Probe =
`INLINE_PACIASP_PLUS_56B_ULTRACOMPACT`, window 60B, 56B core, `DAIFSET=PRESENT`;
its first internal branch source lies at `+0x5c` (outside the 60B window), so
the window does not grow. `CFG_CLOSURE_PROVEN=YES`, incoming-window-interior
count 0, runtime rewrite safe, `PREL32_TARGET_UNCHANGED=YES`.

### CI closure (all Actions-only, no local build)

- Public `LEVEL6_EARLIEST_INLINE_CHECKPOINT_CI` run `35347353966` at `64f12bf`:
  `source-tests`, `level6-earliest-decode`, `independent-reverify` all PASS.
  Pair diff is exactly two bytes at `[0x1b34d99,0x1b34d9b)`,
  `PAIR_DIFF=DELAY_CONSTANT_ONLY`.
- Private pack `35347030524`:
  `DEVPROBE8_BOOT_SHA256=94ae6d10…f64b31`,
  `DEVPROBE1_BOOT_SHA256=2e8b1f5b…a2b90f`, both 37380096 bytes.
- Independent private reverify `35348155046`: PASS.
- Observer fixtures `35347354061`: PASS (80 cross-identity rejections, geometry
  and verdict-boundary fixtures).

A labelling defect in the first decode run (`35346116687`) published the
level-5 runtime span count under the name `LEVEL6_SPAN_ENTRY_COUNT`. It is
recorded here rather than reinterpreted: that run's `=53` is the level-5 span,
the level-6 span is 1100, and the corrected labels are published by
`35347353966`. Both runs carry identical payload SHA256s
(`98023192…9c9b2b`, `fb1660ec…5256ef`).

### Device pair

Two RAM-only boots, one per member, serial `41a5627b`:

| member | total_s | retry | status |
| --- | --- | --- | --- |
| DEVPROBE8 | 35.33681691699894 | 7→6 | `AUTOMATIC_FASTBOOT_RETURN` |
| DEVPROBE1 | 28.199255542000174 | 6 | `AUTOMATIC_FASTBOOT_RETURN` |

`PAIR_DELTA=-7.137561374998768s`, expected `-7.000s`, error
`-0.13756137499876786s` → `abs(error) <= 1s` → **STRONG**.

16-chain partition hashes matched before, between and after the two members;
`boot_b` P15 prefix `133e063b…ea87d34` MATCH throughout; Android A restored
healthy (kernel `4.19.157-perf-g9d90dd04aa7c`, slot `_a`) after each member.
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `SECOND_MEMBER_BOOT=FORBIDDEN_NOT_TAKEN`.

Runtime after this round:

`FS_INITCALLS_COMPLETED=PROVEN`

`FIRST_DEVICE_INITCALL_ENTRY=PROVEN`

`CPUINFO_REGS_INIT_ENTRY=PROVEN`

`DEVICE_INITCALLS_COMPLETED=NOT_PROVEN`

`LATE_INITCALLS_COMPLETED=NOT_PROVEN`

`CONSOLE_ON_ROOTFS=NOT_PROVEN`

`INIT_EXECUTED=NOT_PROVEN`

`USB=FROZEN`

Final gate: `MAINLINE_V2_R3_SLOT_B_FS_INITCALLS_COMPLETED_PROVEN`.

Evidence: `artifacts/slot-b-level6-inline-20260918/`.
