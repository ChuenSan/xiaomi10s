# Slot B late post50 device round (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_49_55_ISOLATION`. Device: Xiaomi
Mi 10S (thyme / M2102J2SC) serial `41a5627b`, operated serially by the main
agent from healthy Android A. Final gate:
**`R3_SLOT_B_LATE_LEVEL_49_55_BISECTION_PROGRESS`**.

## Round intent and selection

Working diagnostic interval `49..55` after the POST43 round: index 49
`bert_init` ENTRY=PROVEN (STRONG), index 55 `genpd_debug_init`
SHIFT_NOT_OBSERVED (frozen, no not-reached claim licensed). The mathematical
midpoint index 52 `boot_wait_for_devices` is 48 B and permanently fails
`FUNCTION_TOO_SMALL` under both verified inline families (minimum licensed
footprint 56 B = 4 B paciasp + 52 B core). Nearest-safe walk (nominal 52):
52 too small → 51 `setup_vcpu_hotplug_event` bti c pad excluded by
`ROUND_PAD_CLASS=PACIASP_ONLY` → 53 `sync_state_resume_initcall` .text +
32 B → **chosen index 50 `clk_debug_init`** (deviation distance 2). Index 54
`deferred_probe_initcall` stays excluded by the `INIT_TEXT` hard gate; index 63
HIGH8 and index 60 were never candidates on this branch.

## Gate chain (all GHA, no local build)

| Stage | Run | Result |
|---|---|---|
| Public CI (`LATE_LEVEL_49_55_ISOLATION_CI`) | `35443931029` @ `7c5675a` | SUCCESS — 16 gates PASS, HIGH8 forensic re-audit `NO_STATIC_PROBE_DEFECT_FOUND` |
| Private pack | `35444373873` @ private `bcb0b42` | SUCCESS — boots `POST50_8` `679d296f…102d5` / `POST50_1` `373b7386…4330a` (37380096) |
| Independent reverify | `35444607542` | SUCCESS (`reverify_only=true`) |
| Identity freeze | `6cefc1e` | `observe.py` + fixtures + tests + workflow |
| Observer fixtures | `35444790761` | SUCCESS — family `post50`, 116 cross-identity rejections |

Geometry: index 50 `clk_debug_init` (`0xffff800081b72f14`/`0x1b72f14`, 288 B,
window 60, core 56 B `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT`, entry pad
`paciasp` freshly GHA-confirmed, table slot `0xffff800081d0c3a0` word
`0xffe66b74`, window agreement `LAYOUT_LITERAL_ADDRESS_DELTA_VERIFIED` (1
same-page ADRP+ADD literal word at `0x1b72f2c`), pair diff
`[0x1b72f21,0x1b72f23)` `DELAY_CONSTANT_ONLY`). Payloads `28d1af69…fa40b` (8s)
/ `aa7605ad…dc821` (1s).

## Device pair (RAM-only Slot B, one boot per member)

| Member | Boot identity (frozen) | Behavior | total_s |
|---|---|---|---|
| `POST50_8` | `679d296f…b7102d5` (37380096) | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 35.526256000 |
| `POST50_1` | `373b7386…684330a` (37380096) | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 28.380970375 |

`PAIR_DELTA=-7.145285625s` vs expected `-7.000000000s`
(`PAIR_ERROR=-0.145285625s`) → **`STRONG`**: `CLK_DEBUG_INIT_ENTRY=PROVEN` /
`late_post50_entry=PROVEN`. Reaching the index-50 entry proves late entries
0..49 each returned (sequential `do_initcall_level` contract) →
**`LATEST_PROVEN_LATE_INDEX=50`**. `NO_RETURN_WITHIN_120S` did not occur.
Current B 16-chain + P15 prefix (`133e063b…87d34`) MATCH pre / between / post;
Android A restored healthy after each member (`_a`,
`4.19.157-perf-g9d90dd04aa7c`); `PARTITION_WRITES=0`; `SLOT_A_WRITTEN=NO`;
USB `FROZEN`. `late_post508`/`late_post501` are rerun-FORBIDDEN.

## Branch logic and child

STRONG at the chosen index advances the proven frontier: next diagnostic
interval is **`50..55`**. The same-round child pair is NOT executed: inside
`50..55` no candidate is licensable under current round policy (51 bti c pad,
52 FUNCTION_TOO_SMALL, 53 .text + 32 B, 54 .text `INIT_TEXT` hard gate, 55
frozen no-shift) — `CHILD_GATED=NO_CANDIDATE_WITHIN_POLICY`. Runtime evidence
otherwise unchanged: `LATE_INITCALLS_COMPLETED`, `WAIT_FOR_INITRAMFS_ENTRY`,
`WAIT_FOR_INITRAMFS_RETURN`, `CONSOLE_ON_ROOTFS`, `INIT_EXECUTED` all stay
`NOT_PROVEN`.

## Evidence

`artifacts/slot-b-late-post50-20260919/` — `ci/gh/` (map-and-audits, logs),
`private/late-post50-pair/` + `late-post50-reverify/`, `device-round/`
(context.json, host logs, observer `result.json`/`events.json`, partition
snapshots pre/between/post, set-active records, android-a records, this
report). Chain: public `35443931029` @ `7c5675a`, private pack `35444373873`
@ `bcb0b42`, reverify `35444607542`, freeze `6cefc1e`, fixtures `35444790761`.
