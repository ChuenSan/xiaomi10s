# Slot B late level — upper-half CFG/geometry audit and level-7 completion bracket (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION`.
Auditor: Sub Agent C — independent CFG/geometry cross-check of the selection
machinery (no code imported from it; every gate re-derived from the frozen
artifacts). Module: `scripts/slot_b/late_level_upper_audit.py`; tests:
`scripts/slot_b/test_late_level_upper_audit.py` (36 tests, green).

Evidence classes used below:

- `FROZEN_ARTIFACT` — GHA-produced JSON/text (`late-table.json`, `audit.json`,
  `window.txt`, `pair.json`, device-round report).
- `LOCAL_BINARY` — derived here from sha-pinned GHA-produced binaries
  (`payload.bin` DEVPROBE8 = frozen bytes outside its own probe window; bundle
  `Image`/`vmlinux`, shas verified against `audit.json`). Code layout of the
  frozen payload kernel equals the bundle's (only rodata-reference immediates
  differ); the audited regions used here were additionally checked byte-exact
  against the bundle Image.
- `PENDING_AUTHORITATIVE_MAP` — needs the authoritative GHA nm/objdump/source
  re-derivation before any device round.

## 1. HIGH reference-table entry (nominal upper child ~index 64)

From `artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/late-table.json`
(FROZEN_ARTIFACT):

| field | value |
| --- | --- |
| span | `[__initcall7_start=0xffff800081d0c2d8, __initcall_end=0xffff800081d0c430)`, 86 entries |
| index | 64 |
| symbol (alias) | `init_subsystem` |
| table entry VA | `0xffff800081d0c3d8` |
| table entry image offset | `0x1d0c3d8` (30458840) |
| PREL32 word | `0xff23e42c` (relative −14425044) |
| target VA | `0xffff800080f4a804` (`.text`, not `.init.text`) |
| target image offset | `0xf4a804` |

## 2. Locally derivable geometry for index 64 — REJECTED (TOO_SMALL)

| gate | result | basis |
| --- | --- | --- |
| FUNCTION_EXTENT | size = 40 (ELF `st_size` == next-symbol extent, both agree) | LOCAL_BINARY |
| MIN_WINDOW | **FAIL**: 40 < 56; INLINE only, trampoline forbidden | LOCAL_BINARY |
| PACIASP_ENTRY | entry word `0xd503233f` (paciasp) — moot given size | LOCAL_BINARY |

The span contains a second `init_subsystem` instance (index 28 @
`0xffff8000801bead8`, also 40 B) — equally unusable. The nominal upper-child
midpoint cannot host any inline probe; the nearest-safe-neighbor policy governs.

## 3. Nearest-safe-neighbor policy from nominal 64

Order: `|index−64|` ascending, lower index first on ties:
`64, 63, 65, 62, 66, 61, 67, 60, ...` (late-level floor-midpoint convention).

Rejections around the nominal (LOCAL_BINARY, sha-pinned payload/vmlinux):

| index | symbol | size | rejection |
| --- | --- | --- | --- |
| 64 | init_subsystem | 40 | MIN_WINDOW FAIL |
| 65 | xdp_metadata_init | 40 | MIN_WINDOW FAIL |
| 66 | bpf_sockmap_iter_init | 52 | MIN_WINDOW FAIL |
| 62 | of_fdt_raw_init | 136 | PACIASP_ENTRY FAIL — entry is `bti c` (`0xd503245f`) |
| 61 | psci_debugfs_init | 100 | PACIASP_ENTRY FAIL — entry is `bti c` |
| 67 | bpf_sk_storage_map_iter_init | 52 | MIN_WINDOW FAIL |

### First passable configuration: index 63 `bpf_kfunc_init`

| field | value | basis |
| --- | --- | --- |
| table entry | VA `0xffff800081d0c3d4`, offset `0x1d0c3d4`, word `0xffe9dd88`, rel −1450616 | FROZEN_ARTIFACT |
| target VA | `0xffff800081baa15c` (`0x1baa15c`) | FROZEN_ARTIFACT |
| function size | 260 (`st_size` == extent) | LOCAL_BINARY |
| entry | paciasp `0xd503233f`; no BTI | LOCAL_BINARY |
| window | 60 (no closure growth; `derived_window == 60`) | LOCAL_BINARY |
| core | `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT` (paciasp + 56 B core, no pad) | predicted |
| pair diff | `[0x1baa169, 0x1baa16b)` — DELAY_CONSTANT_ONLY (delay word at probe word 3, identical rule to the frozen index-0 diff `[0x1b32085,0x1b32087)`) | predicted |

Gate-by-gate (all LOCAL_BINARY): WINDOW_FIT PASS (60 ≤ 260);
NO_CROSS_FUNCTION_OVERWRITE PASS; PACIASP_ENTRY PASS; INCOMING_ENTRY_BRANCH
PASS (none); INCOMING_WINDOW_INTERIOR PASS (none); CFG_CLOSURE PASS — 8
forward CBZs (`+0x1c..+0xa8 → +0xf8`), 0 back edges, 0 surviving
interior-target sources; RELOCATION_OVERLAP PASS (0 of 284143-class sites);
LITERAL_OVERLAP PASS (0); EXTABLE_OVERLAP PASS (0);
ALTERNATIVES_OVERLAP PASS (0); `__jump_table`/`.static_call_sites`/
`.kcfi_traps` ABSENT (frozen audit.json); INITCALL_TABLE_OVERLAP PASS
(0/86 entry words in window, 0 interior targets); PREL32_UNCHANGED PASS.
REGISTRATION: `PENDING_AUTHORITATIVE_MAP` (source-contract macro check runs
authoritatively in CI; the local `linux-6.6` tree is not populated).

### Fallback ladder beyond the first passable

50 of 86 late entries are geometry-passable; the nearest passable ladder from
64 is `63 → 60 (efi_earlycon_unmap_fb) → 68 (bpf_prog_test_run_init) → ...`.
The full machine-readable ladder is emitted by
`python3 scripts/slot_b/late_level_upper_audit.py --limit N`.

## 4. Level-7 completion boundary bracket (formalized)

Encoded machine-checkably as
`LEVEL7_COMPLETION_CHECKPOINT=CANDIDATE(late_complete)` in
`late_level_upper_audit.py` and verified against the frozen
`audit.json`/`window.txt` by `verify_boundary_bracket()`.

Causal chain (each step grounded in the frozen evidence):

1. `do_initcall_level(7)` walks the 86-entry late span
   `[__initcall7_start, __initcall_end)` with no early exit; its return implies
   every late entry returned through `do_one_initcall()`.
2. `do_initcalls()` runs levels 0..7 strictly sequentially (disassembly in
   `audit/initcalls.txt`); its return implies `do_initcall_level(7)` returned.
3. `do_basic_setup()` ends with `do_initcalls()` (byte-exact tail in
   `audit/basic-setup.txt`); its return implies `do_initcalls()` returned.
4. `kernel_init_freeable` executes `bl do_basic_setup` at `0x1b31138` and
   `bl wait_for_initramfs` at `0x1b3113c` with nothing between
   (`audit/caller.txt`); the `late_complete` window `[0x1b3113c, 0x1b31174)`
   replaces the latter call, so the probe fires iff `do_basic_setup` returned.

Acceptance rule: `LATE_INITCALLS_COMPLETED` upgrades to `PROVEN` iff a device
pair at `late_complete` — or at a strictly later checkpoint that causally
implies `late_complete` execution (`wait_complete`, which proves
`wait_for_initramfs_return`, hence the preceding `bl` executed, hence
`do_basic_setup` returned) — is **STRONG**:
`|PAIR_DELTA − (−7.0)| ≤ 1.0 s`.

Negative rules (encoded, machine-checked):

- A STRONG pair at any interior late entry (indices 0..85, including index 85)
  does NOT imply completion: it proves only that the entries before that index
  were reached; the remaining entries and the level return stay unproven. A
  last-late-entry STRONG does NOT license `LATE_INITCALLS_COMPLETED=PROVEN`.
- The frozen WAITENTRY device pair (`WAITENTRY8_TOTAL=45.212251791s`,
  `WAITENTRY1_TOTAL=48.412371375s`, `PAIR_DELTA=+3.200119584s` vs expected
  −7.000 s) is `SHIFT_NOT_OBSERVED`. A no-shift is the absence of evidence: it
  implies neither completion nor non-completion and is never upgraded to any
  completion claim. `WAITENTRY8/1` are rerun-FORBIDDEN.

`verify_boundary_bracket()` re-derives the device pair delta from the two
frozen totals and confirms `strong=False`, so the current encoded claim is
exactly `NONE` — matching `R3_SLOT_B_INITRAMFS_WAIT_CHECKPOINT_SHIFT_NOT_OBSERVED`.

## 5. Calibration (unit tests, 36 green)

Hermetic synthetic fixtures reproduce the frozen precedent topologies:

- index-0 identity (paciasp + straight line + external BL): selects window 60,
  core `56B_ULTRACOMPACT`, all gates PASS.
- chr_dev_init topology: forced 56 B window PASSES (`52B_NO_DAIFSET`); the 60 B
  configuration FAILS CFG_CLOSURE with the surviving `+0x6c → +0x38` branch
  (`cdac → cd78`), reproducing the frozen "60B ultracompact rejected" record.
- topology_init topology: the back-edge `+0x9c → +0x38` forces derivation
  60 → 160; windows 60/112/144 FAIL closure, 160 PASSES.
- Broken fixtures all FAIL: too-small function, `bti c` entry, incoming
  interior/entry branch, relocation overlap, literal overlap, extable overlap,
  alternatives overlap, initcall-table word/target in window, interior symbol,
  window past function end.
- Decoder cross-checked against the frozen core loop encodings; `pair_diff`
  reproduces the frozen index-0 `[0x1b32085,0x1b32087)` and caller
  `[0x1b31145,0x1b31147)` diffs.

Artifact-grounded tests (skip if artifacts absent) re-derive all of the above
from the sha-pinned binaries plus the frozen late table, the frozen precedent
functions (index 0, chr_dev_init, topology_init, af_unix_init 216/60,
vlan_offload_init 60/60, create_debug_debugfs_entry 56/56), the nominal-64
rejection, the neighbor ladder, and the boundary bracket against `audit.json`.

## 6. PENDING_AUTHORITATIVE_MAP

- REGISTRATION macro/source for index 63 (`bpf_kfunc_init`) and every other
  candidate — CI source-contract gate is authoritative (local tree absent).
- All LOCAL_BINARY facts (sizes, topologies, overlaps) await the authoritative
  GHA nm/objdump re-derivation before any device round; locally they come from
  sha-pinned GHA binaries, parsed with the module's own ELF reader.
- Selection verdict for the round (63 vs a different policy choice) belongs to
  the round owner; this module only reports geometry passability.

## 7. Reproduce

```
python3 scripts/slot_b/late_level_upper_audit.py            # CLI pre-audit (JSON)
python3 scripts/slot_b/test_late_level_upper_audit.py       # 36 tests
```
