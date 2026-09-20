# Slot B late index-52 COMPACT_INLINE_48B core (2026-09-20)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_INDEX52_COMPACT_INLINE_CORE_CI`. CI-only.
`DEVICE_BOOT=0`. Final gate: **`R3_SLOT_B_LATE_INDEX52_COMPACT_CORE_CI_READY`**.

## Round intent

Tightest permitted experimental boundary: solve exactly one problem — index 52
`boot_wait_for_devices` is 48 B, which is smaller than the 56 B minimum of every
frozen inline family. Nothing else moves: `.text` policy, trampoline / island,
PREL32 retarget and cross-function overwrite stay forbidden; `PACIASP_PLUS_52B`,
`PACIASP_PLUS_56B` and `BTI_C_PLUS_56B` stay frozen and unmodified. Index 54
`.text` is **not** touched.

## Geometry (fresh GHA, never copied)

| Field | Value |
|---|---|
| symbol | `boot_wait_for_devices` |
| source | `drivers/xen/xenbus/xenbus_probe_frontend.c` `late_initcall(...)` |
| target VA / Image | `0xffff800081b87ec8` / `0x1b87ec8` |
| table slot / word | `0xffff800081d0c3a8` / `0xffe7bb20` (PREL32 `-1590496`) |
| section | `.init.text` |
| function | 48 B (next symbol `register_xen_platform_notifier` at `+0x30`) |
| entry pad | `paciasp` `0xD503233F` preserved verbatim |
| window / core | **48 B / 44 B** `COMPACT_INLINE_48B` |
| tail | **none** — window end == function end |
| CFG | one branch only (`bl wait_for_devices` at `+0x1c`); no conditional, no backedge |
| incoming refs | 0 to the entry, 0 into the interior (full-Image branch-pattern scan, 8 791 680 words) |
| window agreement | `EXACT` / `LAYOUT_LITERAL_ADDRESS_DELTA_VERIFIED` |
| pair diff | `[0x1b87ed1,0x1b87ed2]` `DELAY_CONSTANT_ONLY` (8s `0xD37DF12A` / 1s `0xD340FD2A`) |

Original 48 B decode (bundle Image, matches frozen FIX8): `paciasp`; `stp x29,x30`;
`mov x29,sp`; `adrp x8,#0xffff8000821fd000`; `mov w9,#1`; `mov x0,xzr`;
`strb w9,[x8,#0x1b0]` (`ready_to_wait_for_devices`); `bl wait_for_devices`;
`mov w0,wzr`; `ldp`; `autiasp`; `ret`. Source:

```c
static int __init boot_wait_for_devices(void)
{
	if (!xen_has_pv_devices())
		return -ENODEV;
	ready_to_wait_for_devices = 1;
	wait_for_devices(NULL);
	return 0;
}
late_initcall(boot_wait_for_devices);
```

## Entry pad class and the 44-byte decision

**`MAX_CORE_BYTES = 44`, entry pad preserved.** The decision is audit-driven, not
inherited:

1. `CONFIG_ARM64_BTI_KERNEL=y` and `CONFIG_ARM64_BTI=y` on this exact bundled
   build, and initcall dispatch is a controlled indirect call
   (`do_one_initcall: ret = fn();`, BLR, BTYPE `0b10`).
2. The original entry word is `paciasp` (`0xD503233F`), i.e. the target class is
   `PACIASP_ONLY` — the reverse polarity of the index-51 `BTI_C_ONLY` round.
   Substituting a non-landing-pad instruction (`mrs`) at the entry would move the
   first executed word off the landing-pad class.
3. Dropping the pad buys **nothing**: a 44 B pad-preserving core exists and is a
   delete-only transform of the device-proven 56 B core, so the 4 B is never the
   binding constraint.
4. Asymmetry of risk: if the pad were required and dropped, the probe would fault
   on its first indirect entry; preserving it cannot fail.

UNRESOLVED (recorded, not reinterpreted): index 51 `setup_vcpu_hotplug_event`
carries an explicit `bti c` before its `paciasp` while index 52 carries
`paciasp` alone. Probable per-TU `-mbranch-protection` difference; no functional
impact and it does not change the decision above.

## Compact core (44 B, delete-only)

`COMPACT_INLINE_48B` is the frozen 56 B `BTI_C_PLUS_56B_ULTRACOMPACT` core minus
exactly three instructions: `msr daifset,#0xf`, the loop `isb`, and the terminal
`wfe`.

| off | word | instruction | role |
|---|---|---|---|
| `+00` | `0xD503233F` | `paciasp` | preserved entry pad |
| `+04` | `0xD53BE009` | `mrs x9,cntfrq_el0` | runtime frequency |
| `+08` | `0xD37DF12A` | `lsl x10,x9,#3` | **delay constant** (1s: `0xD340FD2A`) |
| `+0c` | `0xD53BE02B` | `mrs x11,cntpct_el0` | start |
| `+10` | `0xD53BE02C` | `mrs x12,cntpct_el0` | loop head |
| `+14` | `0xCB0B018D` | `sub x13,x12,x11` | elapsed |
| `+18` | `0xEB0A01BF` | `cmp x13,x10` | target |
| `+1c` | `0x54FFFFA3` | `b.lo +0x10` | spin |
| `+20` | `0x52800120` | `movz w0,#9` | PSCI |
| `+24` | `0x72B08000` | `movk w0,#0x8400,lsl#16` | `SYSTEM_RESET` |
| `+28` | `0xD4000003` | `smc #0` | reset |
| `+2c` | `0x14000000` | `b .` | fail-closed terminal |

Ten of the eleven core words are byte-identical to the frozen 56 B core; the two
non-identical words are re-derived, not re-designed: the loop backedge `b.lo`
(imm19 `-4 → -3`, because deleting the `isb` shortened the loop span) and the
terminal (`wfe; b` self-loop → single `b .`).

Deletion justification, each with semantic equivalence and failure behaviour:

1. `msr daifset,#0xf` — already absent in the frozen
   `INLINE_PACIASP_PLUS_52B_NO_DAIFSET` member. Interrupts may be taken during
   the delay; the comparison is against absolute elapsed `cntpct - start`, so an
   interrupt can only **lengthen** the delay, never shorten it. Failure
   behaviour: bounded overshoot, pair delta unchanged.
2. loop `isb` — a serialisation hint, not a safety semantic. `CNTPCT_EL0` is
   monotonically non-decreasing; a stale read causes one more iteration, never an
   early exit. Failure behaviour strictly on the long side.
3. terminal `wfe` → `b .` — `wfe` is a power hint. Fail-closed is strictly
   preserved: `b .` cannot fall through into `register_xen_platform_notifier`
   and cannot return to `do_one_initcall`. It is reachable only if `smc #0`
   returns, i.e. only if `SYSTEM_RESET` was refused.

Register liveness: every register is written before it is read; the core never
touches `SP`, `x29`, `x30` or memory, never executes the original `stp`/`ldp`,
and contains no `ret`, no PAC/AUT hint and no indirect-call word.

Rejected alternatives (each buys zero bytes at 44 B):
hardcoding the timer frequency (no on-disk artifact establishes `CNTFRQ` for
this build; 8 = 2³ and 1 = 2⁰ are exact powers of two so `lsl` needs no
materialised constant); branching/calling an existing reset function (a
cross-function trampoline, and the frozen observable must stay the inline
`smc #0` idiom); any literal pool, island, PREL32 retarget or second-function
overlap.

## Pair

`COMPACT52_8` / `COMPACT52_1`: same target, same 48 B window, same 44 B core,
sole intentional difference the delay constant. `PAIR_DIFF=DELAY_CONSTANT_ONLY`.

## Gate chain (all GHA, no local build)

| Stage | Run | Result |
|---|---|---|
| Public CI (`LATE_INDEX52_COMPACT_INLINE_CORE_CI`) | `35516067282` @ `e537423` | SUCCESS — 36 source tests, authoritative `clang-18` assembly of the 44 B core (zero relocations, size 44, sha256 match), 16/16 geometry gates, 92/92 workflow gate lines |
| Private pack | `35516663217` @ private `6a0fb8d` | SUCCESS — `COMPACT52_8` boot `64a2ed16…68529`, `COMPACT52_1` boot `771d29da…cd100` (37380096 both) |
| Independent reverify | `35516756018` | SUCCESS — `COMPACT52__PAIR_IDENTITY_MATCH=YES`, `PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY`, `COMPACT52__PAIR_DIFF_INDEPENDENTLY_DERIVED=YES`, `COMPACT52__PAIR_DIFF_RANGE=[0x1b87ed1,0x1b87ed3)` |
| Observer fixtures | `35514833635` @ `443f328` | SUCCESS — family `compact52`, `COMPACT52_OBSERVER_FIXTURES=PASS`, 124 cross-identity rejections, 20 fixture tests + 38 base safety tests |

Payloads: `COMPACT52_8`
`e5c7b8d818303cdd8b2c60400aee2578e55734b33fbfca9fdcf55423a40128a5`,
`COMPACT52_1`
`c71f47acce6654c0bfc27b189be0e72b826780e173b186f5c1a0dee2a2d77ed1`.
An independent local reconstruction of both payloads from the frozen FIX8 base plus
the pinned 44 B core reproduces both shas byte for byte, and the composition
reproduces the CI pair-diff offsets `[28868305, 28868306]`.

Two fixes were needed inside this round and are recorded rather than hidden: the
fail-closed terminal check originally read the frozen base's last word (the
function's own `ret`) instead of the composed window's, and one workflow gate
pinned `KERNEL_BTI_CONFIG=ABSENT` where the real config is `y`. Both were
re-verified against the real CI output before re-pushing.

## Hard gates and negative fixtures

All required gates are emitted by the probe and asserted by the workflow:
`TOTAL_INLINE_FOOTPRINT=48`, `TOTAL_WINDOW_LE_48=YES`, `MAX_CORE_BYTES=44`,
`ENTRY_PAD_PRESERVED=YES`, `ENTRY_PAD_CLASS=PACIASP`,
`WINDOW_END_IS_FUNCTION_END=YES`, `NO_INCOMING_WINDOW_INTERIOR=YES`,
`NO_SURVIVING_BRANCH_INTO_OVERWRITTEN_INTERIOR=YES`, `NO_RELOCATION_OVERLAP=YES`,
`NO_RUNTIME_REWRITE_OVERLAP=YES`, `NO_TRAMPOLINE=YES`, `NO_ISLAND=YES`,
`NO_PREL32_CHANGE=YES`, `NO_TEXT_POLICY_RELAXATION=YES`,
`TARGET_SECTION_INIT_TEXT=YES`, `NO_ORIGINAL_REGISTER_DEPENDENCY=YES`,
`CORE_REGISTER_LIVENESS_WRITE_BEFORE_READ=YES`, `FAIL_CLOSED_TERMINAL=YES`,
`TERMINAL_IS_SELF_BRANCH=YES`, `NO_RET_IN_WINDOW=YES`,
`PSCI_RESET_IDIOM_EXACT=YES`, `RESET_ID_WORD=0x84000009`,
`FAMILY_COLLISION_WITH_FROZEN=NO`.

Negative fixtures cover, at minimum: core over budget, total window over 48,
window crossing the function end, entry pad replaced or misclassified as
`bti c` (`ROUND_PAD_CLASS_BTI_C_EXCLUDED`), branch into the overwritten
interior, extra pair diff, `ret` inside the window, terminal not a self-branch,
timer-invariant misuse, `.text` target, frozen-family collision
(`COMPACT_INLINE_48B` vs `PACIASP_PLUS_52B` / `PACIASP_PLUS_56B` /
`BTI_C_PLUS_56B`), PREL32 change, and non-`paciasp` pad classes.

## Runtime evidence

Unchanged and deliberately so: `LATEST_PROVEN_LATE_INDEX=51`,
`BOOT_WAIT_FOR_DEVICES_ENTRY=NOT_PROVEN`, `DEVICE_BOOT=0`,
`LATE_INITCALLS_COMPLETED` / `WAIT_FOR_INITRAMFS_ENTRY` /
`WAIT_FOR_INITRAMFS_RETURN` `NOT_PROVEN`, `LATE_HIGH1=NOT_EXECUTED`,
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`. Dirty worktree
`/Volumes/LinuxDev/thyme-mainline` @`5550dc2` untouched.

