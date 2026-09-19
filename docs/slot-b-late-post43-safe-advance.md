# Slot B late-level post-43 safe advance (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_POST43_SAFE_ADVANCE_CI`. CI status:
COMPLETE — public run `35435068388` (SUCCESS @ `c6da8e8`), private pack
`35435526523` (SUCCESS @ private `c75bf0a`), independent reverify-only
`35435680009` (SUCCESS), identity freeze commits `2b793bc` + `a3f3b78`,
observer fixtures `35436961277` (SUCCESS, 108 cross-identity rejections).
Final gate: **`R3_SLOT_B_LATE_POST43_SAFE_ADVANCE_CI_READY`**,
`READY_FOR_LATE_POST43_DEVICE_PAIR=YES`. No device operation was performed;
the POST43 device split pair is the next separately authorized step.

## Scope

After `R3_SLOT_B_LATE_LEVEL_BISECTION_PROGRESS` (`LATEST_PROVEN_LATE_INDEX=43`,
`NEXT_DIAGNOSTIC_INTERVAL=43..86`, LATE_HIGH8 `NO_RETURN_WITHIN_120S` frozen as
`DEVICE_BEHAVIOR_ANOMALY`), this round (a) re-audited the HIGH8 probe target
statically, (b) selected the next real-device candidate strictly inside
`43 < index < 63`, (c) pre-audited the next bisection layer, and (d) closed the
full identity chain for the new candidate. LATE_HIGH8 was NOT re-run;
LATE_HIGH1 stays `NOT_EXECUTED`; all historical frozen pairs stay frozen.

## Track A — HIGH8 static forensic: `HIGH8_STATIC_PROBE_DEFECT_FOUND=NO`

Independent re-audit of index 63 `bpf_kfunc_init` (260B, .init.text,
`0x1baa15c`, window 60 `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT`): all 15 gates
re-verified from the GHA artifacts; bundle vmlinux/Image byte-identical over 28
alloc sections; full-image scans found 0 direct branches into the window, 0
adrp+add formations, 0 absolute pointers; the only 4-byte relative reference is
the initcall PREL32 slot itself plus one stream-data coincidence inside
`linux_banner` (.rodata); `__ex_table`/`.altinstructions`/`.rela.dyn`/
`.relr.dyn`/`__bug_table` re-scanned field-by-field with zero overlap; the
private HIGH8 boot re-extracted from the frozen identity matches the audited
window bit-exactly (`window-agreement=EXACT`); the HIGH8 probe bytes are
byte-identical to the device-proven MID43 probe (same checkpoint/core SHA).
Eight gate-coverage gap classes (G1–G8: ex_table fixup field, altinstructions
alt_offset, jump_table target, full-image 4-byte relative refs, adrp+add
formation, bug_table/mcount/patchable sections, rela.dyn addend, unaligned
8-byte pointers) were enumerated and — except unaligned 8-byte pointers
(recorded residual) — closed empirically for HIGH8 and structurally by the new
`WINDOW_REFERENCE_FORENSIC` gate for every new window. The verdict does NOT
license any inference about whether index 63 executed at runtime; the frozen
`DEVICE_BEHAVIOR_ANOMALY` stands and runtime evidence stays
`LATE_INITCALLS_COMPLETED=NOT_PROVEN`.

## Track B — post-43 target: index 55 `genpd_debug_init`

From the authoritative 86-entry map (re-derived in-run from bundle 35040148509,
count 86, index-0 identity verified): nominal 53 `sync_state_resume_initcall`
and 54 `deferred_probe_initcall` are `.text` (INIT_TEXT fail), 52
`boot_wait_for_devices` is 48B (FUNCTION_TOO_SMALL). At distance 2 both 51
`setup_vcpu_hotplug_event` and 55 `genpd_debug_init` pass the 15 frozen gates,
but 51's entry pad is **`bti c`** (0xD503245F) — no device-proven precedent —
while 55's pad is **`paciasp`** (same class as the proven 0/21/43 targets).
The round requirement "paciasp-compatible" (user-frozen; the probe family is
`paciasp + 56B ultracompact`) therefore breaks the frozen lower-index tie in
favor of 55, recorded verbatim as the round gate `ROUND_PAD_CLASS`
(`BTI_C_PAD_EXCLUDED_ROUND_REQUIRES_PACIASP`). Selected: **index 55
`genpd_debug_init`** (`0xffff800081b8e964` / `0x1b8e964`, 128B,
`late_initcall(genpd_debug_init)`, drivers/base/power/domain.c, table slot
`0xffff800081d0c3b4`, word `0xffe825b0`, relative −1563216), window 60, cleanest
CFG in the span (no internal branches in the window, single surviving back-edge
`+0x68→+0x54` entirely outside it).

Guards new in this round: `FROZEN_LATE_INDICES=(0,21,43,63)` excluded from
selection, `FROZEN_WINDOW_DISJOINT` against every frozen probe window,
`FROZEN_PAYLOAD_DISJOINT` against the six frozen payload SHAs (recomposing
index 63 would byte-reproduce LATE_HIGH8/1 — a de-facto rerun), dynamic
children nominals `(43+target)//2, (target+63)//2` with hard bounds
`43 < lower < target < upper < 63` (fail-closed, never beyond 63).

## Window agreement (round layout-literal proof)

Bundle Image vs frozen FIX8 payload inside each selected window: 49/60/63
`EXACT`; 55 has exactly two differing words (`0x1b8e978`, `0x1b8e99c`), both
ADD halves of ADRP+ADD literal pairs whose ADRP pages are identical and whose
resolutions (`0x81a43ce8→0x81a43cf0`, `0x81a753a5→0x81a753ad`) land in .rodata
in both builds — proven `LAYOUT_LITERAL_ADDRESS_DELTA_VERIFIED` by the new
round proof (superset of the FS-round proof: same-page ADD-imm deltas and ADR
single-word forms accepted, both-build section resolution required, anything
else fails loudly; POST49's 404B window: 4 ADRP+ADD pairs + 1 ADR, all 10
resolutions in .rodata).

## Track C — children (public-READY, no private pack)

- Lower child **49 `bert_init`** (408B, paciasp, window 404 CFG-forced,
  whole-function rewrite shape like the proven 0/21 precedents): pair PASS,
  `POST49_8` `ea5062e6…` / `POST49_1` `ac50b409…`.
- Upper child nominal 59 `efi_shutdown_init` and 58
  `register_update_efi_random_seed` are both `bti c` → excluded by
  `ROUND_PAD_CLASS`; **60 `efi_earlycon_unmap_fb`** (80B, paciasp, window 60)
  selected at distance 1: pair PASS, `POST60_8` `99c078ab…` / `POST60_1`
  `eb069f9e…`.
- Residual for the layer after next: 61/62 are `bti c`; if 49 and 60 both
  return-shift, the remaining paciasp-compatible candidate inside (60,63) is
  none before the frozen anomalous 63 (whose own pad IS paciasp) — recorded
  for the next round's decision, not interpreted.

## Probe geometry (device-verified family only)

`INLINE_PACIASP_PLUS_56B_ULTRACOMPACT`, window 60 = paciasp (word 0 preserved
verbatim) + 56B terminal core (daifset, CNTPCT elapsed spin, PSCI
`SMC 0x84000009`, wfe fallback). POST43_8/POST43_1 differ in exactly 2 bytes,
`[0x1b8e971,0x1b8e972)` = `0xD37DF12A`/`0xD340FD2A` (lsl #3 vs lsl #0),
`PAIR_DIFF=DELAY_CONSTANT_ONLY`, expected delta −7 s. Payload identities
(public run): `POST43_8`
`1e209f98ba86d03a2c8df65f69152efd8d1f32b575356428d87989a83c306687`, `POST43_1`
`ce3c0a64ca72c5d5f579917e3561107491026765984e1dc0fcc5b3c599d64d27` (37369041
each). Frozen boot identities (private pack `35435526523`, 37380096 each,
reverified by `35435680009`): `POST43_8`
`00f8bdbb546e346a00d08182e269293ef4f3bb892810a46de06a77da2ca73a26`, `POST43_1`
`c9fb8d39383cec9c86f02d73b20ab864c53d5c3e9439c8c9cd7abb322e8ff8cc`. Private
gates confirmed `LATE_LEVEL_OUTSIDE_WINDOW_FIX8_IDENTITY`, PREL32 unchanged,
RT-D unchanged, `ENVELOPE_MATCH=KERNEL_PAYLOAD_ONLY`, `OLD_PROBES_ABSENT=YES`,
`PAIR_GEOMETRY_IDENTICAL`, `PAIR_P15_ENVELOPE_IDENTICAL`,
`PRIVATE_PAIR_DIFF_REVERIFIED`. Observer fixtures (`35436961277`): exact-SHA
accepts, wrong-size/wrong-SHA/sibling-swap/mutant rejects, 108 cross-identity
rejections, 60B geometry + 56/52/64B negative fixtures, index-55 table gate,
`POST43_STRONG_PROVES_TARGET_ENTRY` with
`late_initcalls_completed/wait_for_initramfs_return/console_on_rootfs_entry/
init_executed` all `NOT_PROVEN`, no-shift never claims not-reached.

## Evidence

`artifacts/slot-b-late-post43-20260919/` — `ci/gh/map-and-audits` +
`ci/gh/pairs` (public run), `private/post43-pair` (pack identities),
`observer/` (fixtures + unit tests), `forensic/` (HIGH8 static report +
scan results). CI chain: bundle 35040148509 + FIX8 34741153230 reused, no
kernel rebuild, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `USB=FROZEN`,
`LOCAL_BUILD=NO` throughout; no rerun of any frozen pair; LATE_HIGH8 and
LATE_HIGH1 untouched.

## Next stage (after explicit authorization)

`MAINLINE_V2_R3_SLOT_B_LATE_POST43_DEVICE_PAIR` — device split pair
POST43_8 then POST43_1 under the established runbook discipline (Android A
healthy, Current B 16-chain + P15 prefix MATCH, RAM-only `fastboot boot` of
the exact frozen identity, one boot per member, `NO_RETURN_WITHIN_120S`
handling per the RESET8/HIGH8 precedent class). A STRONG verdict proves
`GENPD_DEBUG_INIT_ENTRY=PROVEN` → `LATEST_PROVEN_LATE_INDEX=55`, interval
collapses to `55..86`, and the next candidates are the recorded children
49/60; a `SHIFT_NOT_OBSERVED` narrows the anomaly zone into 44..55 without
any not-reached claim.
