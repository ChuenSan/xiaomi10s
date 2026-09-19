# Slot B late-level (level-7) MID/LOW/HIGH failure isolation (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION`. CI status:
workflow authored (`thyme-slot-b-late-level-isolation.yml`), run pending.
Final gate: `LATE_LEVEL_STAGE=MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION`
with `PAIR_DIFF=DELAY_CONSTANT_ONLY` (fail-closed on any gate failure).

## Scope

Inline-only failure isolation inside the late (level-7) initcall span
`[__initcall7_start, __initcall_end)` — 86 entries — between two frozen
results that must be reconciled:

- `MAINLINE_V2_R3_SLOT_B_LEVEL7_EARLIEST_INLINE` proved the index-0 entry
  `kernel_do_mounts_initrd_sysctls_init` reached
  (`kernel_do_mounts_initrd_sysctls_init` entry, `LATE_DEVPROBE` pair,
  `ENTRY=PROVEN` semantics) — the late level STARTS.
- `MAINLINE_V2_R3_SLOT_B_LATE_COMPLETE_AND_INITRAMFS_WAIT_ISOLATION` composed
  the caller-side `late_complete` checkpoint after `do_basic_setup()` (which
  returns only after every late initcall ran) and observed
  `SHIFT_NOT_OBSERVED` for the WAITENTRY pair — the late level never
  demonstrably FINISHED.

The unasked question this round answers: if late index 0 is entered but the
late level does not complete, where inside `[1, 85]` does execution stop?
Answering it needs no new caller-side machinery: three additional INLINE
entry checkpoints at the mathematical midpoint and the two bisection children
of the 86-entry span — MID = index 43, LOW = index 21, HIGH = index 64 —
localize the stall to one of the two halves (and then quarters on rerun).

## Selection policy (frozen)

- MID is the frozen mathematical midpoint of the 86-entry span: index 43
  (`86 // 2`, i.e. `ceil(85 / 2)` of the 0-based index range `[0, 85]`).
- LOW ≈ 21 = `43 // 2`, HIGH ≈ 64 = `43 + 43 // 2`: midpoints of the lower
  and upper halves.
- If a nominal index cannot host a safe INLINE probe (any gate below fails),
  the nearest entry by minimal index distance is selected instead (lower
  index wins ties), and the deviation reason is recorded in
  `selection.json` and the audit summary (`LATE_<F>_DEVIATION=`).
- Deviation is never taken for convenience; the nominal candidate is always
  audited first and its failure reasons are logged verbatim.

## Probe-safety gates (per candidate, machine-readable PASS/FAIL)

`TARGET_UNIQUE`, `REGISTRATION_LATE`, `INIT_TEXT` (target must live in
`.init.text`), `FUNCTION_SIZE`, `ENTRY_PAD` (`paciasp` or `bti c`, preserved
verbatim as window word 0), `WINDOW_FIT` (window = 4 + core; 56-byte
ultracompact core → window 60, 52-byte no-daifset core → window 56),
`INCOMING_BRANCH` (no incoming branch to the entry or into the window
interior), `CFG_CLOSURE` (every function-internal branch whose source
survives the overwrite must target outside the window; a function-local
back-edge forces a larger window exactly like the `topology_init`
precedent, window 160), `SYMBOL_SCAN`, `SECTION_SCAN`, `EXTENT_SCAN`
(no cross-function overwrite), `LITERAL_SCAN`, `RELOCATION_SCAN`,
`RUNTIME_REWRITE` (`__ex_table`, `.altinstructions`, `__jump_table`,
`.static_call_sites`, `.kcfi_traps` overlap = 0), `IMAGE_GEOMETRY`.

Trampolines, islands, PREL32 retargeting, shared `do_initcall*` checkpoints
and cross-function overwrite are FORBIDDEN, as in the level-7 earliest round.
The PREL32 table word of each selected entry stays byte-identical.

## Family naming and evidence semantics

| Family | Pair names | Nominal index |
|---|---|---|
| `late_mid` | `LATE_MID8` / `LATE_MID1` | 43 |
| `late_low` | `LATE_LOW8` / `LATE_LOW1` | 21 |
| `late_high` | `LATE_HIGH8` / `LATE_HIGH1` | 64 |

For each family `<F>` ∈ {`LATE_MID`, `LATE_LOW`, `LATE_HIGH`}:

- STRONG (the 8 s → 1 s pair shifts the measurable stall by ≈ 7 s):
  `<F>_ENTRY=PROVEN` — that initcall entry was reached. Nothing more: it does
  not prove the body returned, nor later initcalls, nor console or /init.
- No shift between the pair members: only
  `<F>_CHECKPOINT_SHIFT_NOT_OBSERVED`. It is NEVER recorded as
  `TARGET_NOT_REACHED` — absence of a shift is not evidence of non-entry.
- A family with `ENTRY=PROVEN` together with a lower half-failure localizes
  the stall after the proven entry; the next rerun bisects the unproven half.
- `<F>_CHECKPOINT_SHIFT_NOT_OBSERVED` never upgrades
  `kernel_do_mounts_initrd_sysctls_init_ENTRY=PROVEN` and never contradicts
  the WAITENTRY `SHIFT_NOT_OBSERVED`; it only narrows the unproven interval.

Each pair differs from the frozen FIX8 base in exactly one 60-byte (or
56-byte) window and the two members differ from each other in exactly two
bytes — the CNTPCT delay constant (`lsl #3` vs `lsl #0`,
`0xD37DF12A` vs `0xD340FD2A`), `DELAY_CONSTANT_ONLY`, expected delta −7 s.

## CI chain (GHA only, bundle 35040148509, no kernel rebuild)

| Stage | Workflow run |
|---|---|
| Source tests | pending |
| Map + selection + three pairs | pending |
| Job summary | pending |

Inputs downloaded exactly like the level-7 earliest round: bundle
`thyme-slot-b-kernel-audit-bundle` from run 35040148509, frozen FIX8 payload
`thyme-r3-p1b-fix8-fix24` from run 34741153230 (SHA-verified); the 56-byte
ultracompact and 52-byte no-daifset cores are re-assembled in-run from
`checkpoint-ultracompact.S` / `checkpoint-subsys52.S` and gated for
equivalence. All three families are composed in ONE workflow run.

## Authoritative map (TO FILL after the GHA run)

<!-- Placeholder: paste the 86-entry late-map.json digest from the
     thyme-late-level-isolation-map-and-audits artifact: entry_count,
     __initcall7_start / __initcall_end VAs, per-entry
     index / table VA / PREL32 word / target VA / symbol / function size /
     section / registration, and the selected MID/LOW/HIGH records with
     deviation reasons. The map is re-derived from the bundle vmlinux in the
     workflow; the local reference table
     artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/late-table.json
     is a cross-check fixture only. -->

Known from the local reference (non-authoritative, to be re-confirmed):

- Index 0 identity (frozen): `kernel_do_mounts_initrd_sysctls_init`,
  table slot VA `0xffff800081d0c2d8`, PREL32 word `0xffe25da0`
  (relative −1942112), target VA `0xffff800081b32078`, image offset
  `0x1b32078`, function size 60, entry `paciasp`, no BTI,
  `late_initcall(kernel_do_mounts_initrd_sysctls_init)` from
  `init/do_mounts_initrd.c`.
- 82 of the 86 decoded targets live in `.init.text`; FOUR are legal
  non-`__init` late registrations whose functions live in `.text` and can
  never host an inline probe: index 28 `init_subsystem`,
  index 53 `sync_state_resume_initcall`, index 54 `deferred_probe_initcall`,
  index 64 `init_subsystem`. The `INIT_TEXT` selection gate excludes them;
  the map records their true section.
- Predicted selections (reference-based, pending GHA confirmation):
  MID 43 `integrity_fs_init` (size 112, window 60, 56-byte core);
  LOW 21 `kexec_core_sysctl_init` (size 60, window 60, 56-byte core);
  HIGH nominal 64 `init_subsystem` FAILS (`TARGET_NOT_INIT_TEXT` +
  `FUNCTION_TOO_SMALL`) → nearest-safe fallback index 63 `bpf_kfunc_init`
  (size 260, window 60, 56-byte core), deviation distance 1.

## Failure handling

The module and the workflow fail closed: any gate failure, any span drift
(count ≠ 86, hole, index-0 identity drift, non-unique target), any bundle
hash drift or any pair that is not `DELAY_CONSTANT_ONLY` aborts the run
before an artifact is published. No device image is ever produced
(`payload-only scope` assert).
