# Slot B late-level (level-7) MID/LOW/HIGH failure isolation (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION`. CI status:
COMPLETE — public run `35423178838` (SUCCESS), private packs
`35424193072` / `35424195341` / `35424197194` (SUCCESS), reverify-only
`35424872255` / `35424873873` / `35424875736` (SUCCESS), observer fixtures
`35425270933` (mid) / `35425306958` (low) / `35425242780` (high) (SUCCESS).
Final gate: `R3_SLOT_B_LATE_LEVEL_BISECTION_PROGRESS` — MID pair STRONG,
`LATEST_PROVEN_LATE_INDEX=43`, `NEXT_DIAGNOSTIC_INTERVAL=43..86`;
LATE_HIGH8 recorded `NO_RETURN_WITHIN_120S` without interpretation,
LATE_HIGH1 not executed (ladder), LOW pair not executed (lower half already
proven by the MID STRONG).

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
| Source tests (in run 35423178838) | PASS (247 tests) |
| Map + selection + three pairs | `35423178838` SUCCESS @ `20daa73e` |
| Private pack mid / low / high | `35424193072` / `35424195341` / `35424197194` SUCCESS @ private `9dedee7` |
| Independent reverify-only mid / low / high | `35424872255` / `35424873873` / `35424875736` SUCCESS |
| Freeze commit | `d8a29e2` (observe.py registry + verdict routes, fixture SHAs) |
| Observer fixtures mid / low / high | `35425270933` / `35425306958` / `35425242780` SUCCESS |

Inputs downloaded exactly like the level-7 earliest round: bundle
`thyme-slot-b-kernel-audit-bundle` from run 35040148509, frozen FIX8 payload
`thyme-r3-p1b-fix8-fix24` from run 34741153230 (SHA-verified); the 56-byte
ultracompact and 52-byte no-daifset cores are re-assembled in-run from
`checkpoint-ultracompact.S` / `checkpoint-subsys52.S` and gated for
equivalence. All three families are composed in ONE workflow run.

## Authoritative map (GHA run 35423178838)

Re-derived from bundle 35040148509 vmlinux; 86 entries, 4-byte slot
continuity, no holes, index-0 identity equals the frozen record (table slot
`0xffff800081d0c2d8`, word `0xffe25da0`, target `0xffff800081b32078`, size
60). Full per-entry records: `late-map.json` in artifact
`thyme-late-level-isolation-map-and-audits`, mirrored under
`artifacts/slot-b-late-level-20260919/ci/gh/`.

- 82 of 86 decoded targets live in `.init.text`; four legal non-`__init`
  late registrations live in `.text` and can never host an inline probe:
  index 28 `init_subsystem`, 53 `sync_state_resume_initcall`,
  54 `deferred_probe_initcall`, 64 `init_subsystem`.
- Selected targets (all 15 gates PASS, all `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT`,
  window 60, core 56):
  - MID = 43 `integrity_fs_init` (`0xffff800081b5bd1c` / `0x1b5bd1c`, size
    112, `late_initcall(integrity_fs_init)`, security/integrity/iint.c),
    deviation NONE; internal branches `+0x2c/+0x38` overwritten, no window-
    interior branch targets, surviving back-edge `+0x6c → +0x3c` outside the
    window; pair diff `[0x1b5bd29,0x1b5bd2b)`.
  - LOW = 21 `kexec_core_sysctl_init` (`0xffff800081b47510` / `0x1b47510`,
    size 60 — whole-function rewrite shape like the proven index-0 probe,
    no internal branches, `late_initcall(kexec_core_sysctl_init)`,
    kernel/kexec_core.c), deviation NONE; pair diff `[0x1b4751d,0x1b4751f)`.
  - HIGH nominal 64 `init_subsystem` REJECTED
    (`REGISTRATION_LATE:NOT_LATE_INITCALL:None`, `TARGET_NOT_INIT_TEXT:.text`,
    `FUNCTION_TOO_SMALL` 40B) → nearest-safe fallback **index 63
    `bpf_kfunc_init`** (`0xffff800081baa15c` / `0x1baa15c`, size 260,
    `late_initcall(bpf_kfunc_init)`, net/core/filter.c), deviation distance 1
    recorded verbatim; 11 forward CBZs to `+0xf8`, no back edges, no
    window-interior targets; pair diff `[0x1baa169,0x1baa16b)`.

Payload identities (public run): LATE_MID8
`8cfc9150534e4cb1e6e0ff9dbe2f346014b321e9d1a41eba547efcc8c6fa563a`, LATE_MID1
`cc1e67f408044da6673cb94628abfa911e065ce3af95ef9a86aab21a4b26b247`, LATE_LOW8
`a36cf28fc9cd8a4d1bdfe93ad31c403bfd1d7fbfaa2a9abf9142c331d28b659d`, LATE_LOW1
`40b71779527dc2ae03cd900f3c6ad8a81d841c04144abfcc96a7652b12d96fb1`,
LATE_HIGH8 `c9f160597287666b73004db604c1525786eca5daef2e6fc7d43a647d2896be2d`,
LATE_HIGH1 `c4c4115940159c138ee7742473fc09b852eaeb06e7b81c1e208787edb644a67d`
(37369041 each; pair diffs DELAY_CONSTANT_ONLY 2 bytes). Frozen boot
identities (private packs, 37380096 each, locally re-hashed): LATE_MID8
`9f8f164cea838ee5ea3b572922cc40d9a9ab0ca022077b92b3a7152dfbe040d5`, LATE_MID1
`f0f0abbbfd1b7e586dbd542160dd2f55f43d0303430b0cd7cefb2c788bb77e37`, LATE_LOW8
`911903f143ae773de57bed04a974e8d3d39c76d48605bbe1855051affcc2d2db`, LATE_LOW1
`536459c464c4576e684fd5080ba41e1c8f40a010b6d520d948737ef36914cb4a`,
LATE_HIGH8 `b5da8e368df68ead77d9f702ff0c668d09413413c932f15a053e722843fd8629`,
LATE_HIGH1 `7b95a512fdb917fe39ed9991c7c2bb361929ca71b354b33146892e85120555cc`.

## Device round (2026-09-19, slot-b-p15-fastboot-return-v1)

Hard gates before every member: Android A healthy, Current B 16-chain + P15
prefix MATCH (device-side `sha256sum` via `adb shell su -c`), RAM-only
`fastboot boot` of the exact frozen identity, one boot per member.

- LATE_MID8 member A: `AUTOMATIC_FASTBOOT_RETURN`,
  `LATE_MID8_TOTAL=35.142601208s`, retry 7→6, identity
  `9f8f164c…040d5` matched before interaction. Android A restored; 16-chain
  + P15 prefix re-MATCH after the member.
- LATE_MID1 member B: `AUTOMATIC_FASTBOOT_RETURN`,
  `LATE_MID1_TOTAL=28.367189750s`, retry 7→6, identity
  `f0f0abbb…77e37` matched. Pair: `PAIR_DELTA=-6.775411458s`, expected
  `-7.000000000s`, `PAIR_ERROR=+0.224588542s` → **STRONG**.
  `INTEGRITY_FS_INIT_ENTRY=PROVEN`, `LATE_MID_ENTRY=PROVEN`. Reaching the
  index-43 entry also proves late entries 0..42 each returned (sequential
  `do_initcall_level` execution), so the unproven interval collapses from
  `[1,85]` to **`43..86`** (diagnostic direction only for 43..85; the
  WAITENTRY no-shift stays frozen and uninterpreted).
- LATE_HIGH8 member A (index 63 `bpf_kfunc_init`): boot accepted (Sending
  OKAY 0.901s, Booting OKAY 0.221s), then `NO_RETURN_WITHIN_120S` — no
  fastboot, no adb, no USB enumeration for 9+ minutes after boot. Recorded
  WITHOUT interpretation: no entry, non-entry, completion or non-completion
  claim is licensed. `LATE_HIGH8_RERUN_FORBIDDEN=YES`. LATE_HIGH1 was NOT
  executed (ladder requires a valid member-A return):
  `LATE_HIGH_PAIR_VERDICT=NOT_EVALUABLE`. LOW pair NOT executed: the MID
  STRONG already proves the lower half; an extra pair there would burn
  device boots without information gain.
- Device state at round close: awaiting the proven physical recovery
  (Power + Volume-Down → Fastboot B), identical in class to the frozen
  RESET8 `NO_RETURN_WITHIN_120S` recovery. On-disk Current B, Slot A and all
  16 recorded partition hashes were last verified MATCH after the MID pair;
  re-verification is part of the recovery round.
- `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `USB=FROZEN`,
  `LATE_INITCALLS_COMPLETED=NOT_PROVEN`, `WAIT_FOR_INITRAMFS_RETURN=NOT_PROVEN`,
  `CONSOLE_ON_ROOTFS=NOT_PROVEN`, `INIT_EXECUTED=NOT_PROVEN`.
- Final gate: **`R3_SLOT_B_LATE_LEVEL_BISECTION_PROGRESS`**,
  `LATEST_PROVEN_LATE_INDEX=43`, `NEXT_DIAGNOSTIC_INTERVAL=43..86`.
  Next stage after recovery: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_43_86_ISOLATION_CI`
  (next bisection layer inside 43..86; the HIGH no-return is a device-behavior
  boundary, not an interval refinement).

## Failure handling

The module and the workflow fail closed: any gate failure, any span drift
(count ≠ 86, hole, index-0 identity drift, non-unique target), any bundle
hash drift or any pair that is not `DELAY_CONSTANT_ONLY` aborts the run
before an artifact is published. No device image is ever produced
(`payload-only scope` assert).
