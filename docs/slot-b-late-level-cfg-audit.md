# Slot B — late (level-7) initcall INLINE probes: MID/LOW CFG & geometry pre-audit

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION`
Module: `scripts/slot_b/late_level_cfg_audit.py` (this document is its pre-audit report)
Role: independent CFG/geometry cross-check of the Sub Agent A selection machinery.
The module shares no code with `checkpoint.py` / `post_initcalls.py` (branch decoder,
window-closure fixpoint and gate logic re-derived from the frozen calibration facts)
and imports nothing from Sub Agent A.

## Status: PRE-AUDIT (no GHA map yet)

Locally decidable gates are evaluated against existing text/JSON artifacts only.
Everything that requires instruction-level or full-image data is reported
`PENDING` with the exact missing item named (`PENDING_AUTHORITATIVE_MAP` policy);
nothing about entries 21/43/64 is assumed beyond what the artifacts establish.

## Authoritative inputs (read-only)

| artifact | path (relative to repo root) |
| --- | --- |
| late span table, 86 entries | `artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/late-table.json` |
| frozen bundle identity | `artifacts/slot-b-level6-inline-20260918/bundle/bundle.json` (run 35036419486; Image `43fb1c91…`, vmlinux `295bfdb1…` — identical to the level-7 round bundle) |
| frozen System.map (167,221 symbols) | `artifacts/slot-b-level6-inline-20260918/bundle/System.map` |
| proven level-7 index-0 probe | `artifacts/slot-b-level7-20260918/ci/l7-pair/8/checkpoint/*` + `ci/l7-gates.txt` |
| post-initcalls caller audit | `artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/{audit,verification}.json`, `caller.txt`, `basic-setup.txt`, `initcalls.txt` |
| round history | `docs/slot-b-level7-late-initcall-checkpoint.md` |

No binary was parsed beyond the System.map text; no kernel was built, no image
was patched or validated, no existing file was modified.

## Function sizes: derivation method and calibration

`System.map` carries no size column, so a size is derived as
`next text symbol VA - symbol VA` (lowercase `t` local text symbols; `T` accepted
when immediately adjacent; verified that no non-text symbol is interleaved for
the symbols used). The method is validated against all six frozen precedents —
exact reproduction, 6/6:

| precedent | frozen size | System.map delta | frozen window / core |
| --- | --- | --- | --- |
| kernel_do_mounts_initrd_sysctls_init (index 0) | 60 | 60 | window 60, 56B ultracompact |
| vlan_offload_init | 60 | 60 | window 60, core 56 |
| af_unix_init | 216 | 216 | window 60 |
| chr_dev_init | 184 | 184 | window 56, core 52 (no-daifset) |
| topology_init | 188 | 188 | window 160 (back-edge +0x9c -> +0x38) |
| create_debug_debugfs_entry | 56 | 56 | window 56, core 52 (no-daifset) |

The GHA authoritative map must still confirm with `nm -S` symbol sizes; the
evaluator treats an unconfirmed size as `PENDING`.

## Gate model (9 gates, PASS / FAIL / PENDING)

1. `WINDOW_FIT` — window is 4-aligned, >= 56, and fits inside the function
   (window <= function size; no cross-function overwrite).
2. `ENTRY_PACIASP` — word at target VA is `paciasp` (`0xd503233f`).
3. `INCOMING_BRANCHES` — image-wide scan at the final window: 0 branches from
   outside the function to its entry, 0 from outside the window into the window
   interior (function-local branches overwritten by the window are excluded —
   the topology_init 160-byte window mechanism).
4. `INTERNAL_BRANCH_CLOSURE` — no internal branch source surviving the window
   targets the window interior; the grow fixpoint (round-up of the farthest
   surviving source) must stay within the function (`CFG_CLOSURE_EXCEEDS_FUNCTION`
   otherwise). A 56-byte window with the 52B core is the chr_dev_init-style
   alternative when the first branch target sits at the window edge.
5. `LITERAL_RELOCATION_OVERLAP` — 0 relocation sites and 0 adrp+add literal
   references resolving into the window.
6. `EXTABLE_OVERLAP` — 0 `__ex_table` insn VAs inside the window.
7. `RUNTIME_REWRITE_OVERLAP` — 0 `.altinstructions` orig ranges overlapping the
   window; `__jump_table` / `.static_call_sites` / `.kcfi_traps` are already
   established ABSENT in the frozen bundle (`audit.json`, run 35040148509
   reverify of the same vmlinux sha `295bfdb1…`).
8. `INITCALL_TABLE_OVERLAP` — 0 overlap with the late span
   `[0xffff800081d0c2d8, 0xffff800081d0c430)` or any other level span.
9. `PREL32_ENTRY_UNCHANGED` — the table word decodes to the window start and the
   probe writes only the function prologue (inline-only, trampoline/island/
   PREL32-retarget/shared-checkpoint forbidden by design).

Architecture policy (level-6/7 selector, calibrated): size >= 60 ->
`INLINE_PACIASP_PLUS_56B_ULTRACOMPACT` (window floor 60); 56 <= size < 60 ->
`INLINE_PACIASP_PLUS_52B_NO_DAIFSET` (window 56); smaller -> no inline probe.

## MID candidate — nominal index 43 `integrity_fs_init`

| field | value |
| --- | --- |
| late-table entry | index 43, entry VA `0xffff800081d0c384`, image offset `0x1d0c384`, word `0xffe4f998`, relative -1771112 |
| target VA / image offset | `0xffff800081b5bd1c` / `0x1b5bd1c` |
| function size | 112 bytes (next text symbol `integrity_audit_setup` at `0xffff800081b5bd8c`) |
| predicted architecture | `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT` (112 >= 60) |
| predicted window | 60 (floor; may grow to at most 112 under the closure fixpoint) |
| locally decidable gates | WINDOW_FIT PASS, INITCALL_TABLE_OVERLAP PASS, PREL32_ENTRY_UNCHANGED PASS |
| pending gates | ENTRY_PACIASP, INCOMING_BRANCHES, INTERNAL_BRANCH_CLOSURE, LITERAL_RELOCATION_OVERLAP, EXTABLE_OVERLAP, RUNTIME_REWRITE_OVERLAP |
| overall | PENDING_AUTHORITATIVE_MAP |

Source-shape caveat (no local disassembly): upstream `integrity_fs_init` mounts
a filesystem and can carry an IS_ERR conditional branch; if a chr_dev_init-style
internal branch exists (`target` inside the first 60 bytes, `source` beyond),
the 60-byte window fails closure and the minimal closed window (<= 112) applies,
or a 56-byte window with the 52B no-daifset core if no branch targets (0, 56).
This is exactly what the authoritative disassembly must decide.

## LOW candidate — nominal index 21 `kexec_core_sysctl_init`

| field | value |
| --- | --- |
| late-table entry | index 21, entry VA `0xffff800081d0c32c`, image offset `0x1d0c32c`, word `0xffe3b1e4`, relative -1855004 |
| target VA / image offset | `0xffff800081b47510` / `0x1b47510` |
| function size | 60 bytes exactly (next text symbol `cgroup_init_early` at `0xffff800081b4754c`) |
| predicted architecture | `INLINE_PACIASP_PLUS_56B_ULTRACOMPACT` (60 >= 60) |
| predicted window | 60 == whole function (same total-rewrite shape as the proven index-0 probe) |
| locally decidable gates | WINDOW_FIT PASS, INITCALL_TABLE_OVERLAP PASS, PREL32_ENTRY_UNCHANGED PASS |
| pending gates | ENTRY_PACIASP, INCOMING_BRANCHES, INTERNAL_BRANCH_CLOSURE, LITERAL_RELOCATION_OVERLAP, EXTABLE_OVERLAP, RUNTIME_REWRITE_OVERLAP |
| overall | PENDING_AUTHORITATIVE_MAP |

With window == function size every internal branch is automatically overwritten,
so the remaining risks are only the image-wide incoming scan and the
extable/alternatives/literal scans. The window/function equality is safe for the
same reason as index 0: the probe ends in a fail-closed `wfe; b .` loop and the
removed body is never reached.

## Nearest-safe-neighbor fallback lists

Search policy: from the nominal index, order by minimal |delta| (ties: lower
index first), evaluate the locally decidable gates, report the first
configuration with no FAIL (the primary), plus rejections and conditional
candidates. Sizes from the calibrated System.map method; index 64
(`init_subsystem` alias, `0xffff800080f4a804`, 40 bytes) is TOO_SMALL for any
inline probe.

MID fallback (nominal 43) — rejected: 42 `init_root_keyring` 36B, 44
`crypto_algapi_init` 32B, 45 `blk_timeout_init` 24B, 46 `mst_irq_pm_init` 40B,
47 `pci_resource_alignment_sysfs_init` 44B, 37 `max_swapfiles_check` 12B (all
`TOO_SMALL: size < 56`). Conditional in |delta| order: 43 (112B), 41
`pstore_init` (92B), 40 `check_early_ioremap_leak` (108B), 39
`split_huge_pages_debugfs` (60B), 38 `slab_sysfs_init` (400B), 48
`pci_sysfs_init` (112B), 49 `bert_init` (408B), 36 `fault_around_debugfs` (60B),
50 `clk_debug_init` (288B), 35 `load_system_certificate_list` (80B), 51
`setup_vcpu_hotplug_event` (64B).

LOW fallback (nominal 21) — rejected: 22 `bpf_rstat_kfunc_init` 40B, 19
`bpf_ksym_iter_register` 40B, 28 `init_subsystem` 40B (all TOO_SMALL).
Conditional in |delta| order: 21 (60B), 20 `kernel_acct_sysctls_init` (60B), 23
`taskstats_init` (88B), 18 `tk_debug_sleep_time_init` (60B), 24
`bpf_global_ma_init` (60B), 17 `swiotlb_create_default_debugfs` (176B), 25
`bpf_syscall_sysctl_init` (60B), 16 `init_srcu_module_notifier` (72B), 26
`kfunc_init` (164B), 15 `printk_late_init` (388B), 27 `bpf_map_iter_init` (64B),
14 `pm_debugfs_init` (60B), 13 `cpu_latency_qos_init` (88B), 29
`task_iter_init` (232B).

## Expected probe payload behavior (both primaries)

Both primaries reuse the proven index-0 payload family: original `paciasp` word
+ the 56-byte CNTPCT/PSCI ultracompact core (`reference_core_sha256`
`8b90e4c5…`), optionally NOP-padded (`0xd503201f`) if the closure fixpoint grows
the MID window beyond 60. Pair (delay 8 vs 1) differs in 2 bytes at word 3
(`[target+13, target+15)`), `DELAY_CONSTANT_ONLY` — identical to the frozen
index-0 pair diff `[0x1b32085, 0x1b32085+2)`. Inline-only: no trampoline, no
island, no PREL32 retarget, no shared `do_initcall*` checkpoint, no
cross-function overwrite.

## Unit-test calibration (scripts/slot_b/test_late_level_cfg_audit.py — 29 tests, green)

- frozen index-0 identity (real 15-word frozen body, `bl 0x…578bc` roundtrip,
  PREL32 `0xffe25da0` decode) passes all 9 gates at window 60;
  window 64 and window 52 FAIL `WINDOW_FIT`.
- chr_dev_init precedent: internal branch `+0x6c -> +0x38`; window 56 closes
  (PASS), window 60 fails closure with `minimal closed window 112`.
- topology_init precedent: back-edge `+0x9c -> +0x38`; fixpoint derives exactly
  160; window 160 PASS, window 60 FAIL.
- create_debug_debugfs_entry precedent: 56B no-daifset PASS.
- broken fixtures requiring FAIL: non-paciasp entry, incoming interior/entry
  branches, extable hit, alternatives overlap, relocation in window, table-span
  overlap, PREL32 mismatch, TOO_SMALL function (40B), malformed branch beyond
  the function (`CFG_CLOSURE_EXCEEDS_FUNCTION`), jump_table-present PENDING.
- artifact calibration: all six precedent sizes reproduced from System.map;
  late table = 86 entries with the frozen identity of index 0; neighbor searches
  return the nominal indices 21/43 as primaries.

## What the authoritative GHA map must supply (exact list)

1. `nm -S` symbol sizes (or objdump extents) confirming 112 (`integrity_fs_init`)
   and 60 (`kexec_core_sysctl_init`).
2. First instruction word at `0xffff800081b5bd1c` and `0xffff800081b47510`
   (expected `paciasp`, `0xd503233f`).
3. Full-image branch scan at each final window: `incoming_entry` and
   `incoming_window_interior` must both be empty.
4. Internal branches / back-edges of both functions (window closure fixpoint).
5. Relocation-site scan (`relocations_in_window == 0`) and the adrp+add
   literal-reference scan resolving into each window.
6. Decoded `__ex_table` insn VAs (994 entries) checked against each window.
7. Decoded `.altinstructions` orig ranges (37287 entries) checked against each
   window.
8. Registration macro confirmation from the kernel source for both symbols
   (the source tree is not present in this worktree).

## Embedded pre-audit JSON (compact; primaries carry full gate reports)

```json
{
  "module": "late_level_cfg_audit",
  "frozen_bundle_run": "35036419486",
  "late_span": {
    "start": "0xffff800081d0c2d8",
    "end": "0xffff800081d0c430",
    "entries": 86
  },
  "size_method": "next-text-symbol delta from the frozen System.map; validated against all six frozen precedents (exact match)",
  "calibration": [
    {
      "case": "index-0 identity",
      "symbol": "kernel_do_mounts_initrd_sysctls_init",
      "va": "0xffff800081b32078",
      "frozen_size": 60,
      "frozen_window": 60,
      "frozen_architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
      "system_map_size": 60,
      "size_match": true
    },
    {
      "case": "fs precedent",
      "symbol": "vlan_offload_init",
      "va": "0xffff800081baedfc",
      "frozen_size": 60,
      "frozen_window": 60,
      "frozen_architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
      "system_map_size": 60,
      "size_match": true
    },
    {
      "case": "fs precedent",
      "symbol": "af_unix_init",
      "va": "0xffff800081bae798",
      "frozen_size": 216,
      "frozen_window": 60,
      "frozen_architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
      "system_map_size": 216,
      "size_match": true
    },
    {
      "case": "fs precedent",
      "symbol": "chr_dev_init",
      "va": "0xffff800081b8cd40",
      "frozen_size": 184,
      "frozen_window": 56,
      "frozen_architecture": "INLINE_PACIASP_PLUS_52B_NO_DAIFSET",
      "system_map_size": 184,
      "size_match": true
    },
    {
      "case": "arch precedent",
      "symbol": "topology_init",
      "va": "0xffff800081b346fc",
      "frozen_size": 188,
      "frozen_window": 160,
      "frozen_architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
      "system_map_size": 188,
      "size_match": true
    },
    {
      "case": "fs precedent",
      "symbol": "create_debug_debugfs_entry",
      "va": "0xffff8000800149e0",
      "frozen_size": 56,
      "frozen_window": 56,
      "frozen_architecture": "INLINE_PACIASP_PLUS_52B_NO_DAIFSET",
      "system_map_size": 56,
      "size_match": true
    }
  ],
  "MID": {
    "nominal_index": 43,
    "primary": {
      "index": 43,
      "symbol": "integrity_fs_init",
      "target_va": "0xffff800081b5bd1c",
      "image_offset": "0x1b5bd1c",
      "function_size": 112,
      "window": 60,
      "predicted_architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
      "derived_window": null,
      "gates": [
        {
          "gate": "WINDOW_FIT",
          "status": "PASS",
          "reason": "window 60 fits inside function size 112 (no cross-function overwrite)"
        },
        {
          "gate": "ENTRY_PACIASP",
          "status": "PENDING",
          "reason": "entry instruction word unknown",
          "missing": [
            "first instruction word at target_va (objdump of the target function)"
          ]
        },
        {
          "gate": "INCOMING_BRANCHES",
          "status": "PENDING",
          "reason": "image-wide branch topology unknown",
          "missing": [
            "full-image branch scan at the final window (incoming_entry and incoming_window_interior must both be empty)"
          ]
        },
        {
          "gate": "INTERNAL_BRANCH_CLOSURE",
          "status": "PENDING",
          "reason": "internal branch topology unknown",
          "missing": [
            "disassembly of the target function (internal branches / back-edges and their window coverage)"
          ]
        },
        {
          "gate": "LITERAL_RELOCATION_OVERLAP",
          "status": "PENDING",
          "reason": "literal-pool / relocation evidence absent",
          "missing": [
            "relocation site list over the image (relocations_in_window == 0)",
            "adrp+add literal-reference scan resolving into the window"
          ]
        },
        {
          "gate": "EXTABLE_OVERLAP",
          "status": "PENDING",
          "reason": "__ex_table insn addresses unknown",
          "missing": [
            "decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: insn = &entry->insn + s32) checked against the window"
          ]
        },
        {
          "gate": "RUNTIME_REWRITE_OVERLAP",
          "status": "PENDING",
          "reason": "runtime-rewrite tables not fully characterized",
          "missing": [
            "decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) checked against the window"
          ]
        },
        {
          "gate": "INITCALL_TABLE_OVERLAP",
          "status": "PASS",
          "reason": "0 overlap with the late span [__initcall7_start, __initcall_end) or any other level span"
        },
        {
          "gate": "PREL32_ENTRY_UNCHANGED",
          "status": "PASS",
          "reason": "table word decodes to the window start; the probe writes only the function prologue, .init.data untouched (PREL32_TARGET_UNCHANGED)"
        }
      ],
      "overall": "PENDING",
      "missing_authoritative_map": [
        "first instruction word at target_va (objdump of the target function)",
        "full-image branch scan at the final window (incoming_entry and incoming_window_interior must both be empty)",
        "disassembly of the target function (internal branches / back-edges and their window coverage)",
        "relocation site list over the image (relocations_in_window == 0)",
        "adrp+add literal-reference scan resolving into the window",
        "decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: insn = &entry->insn + s32) checked against the window",
        "decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) checked against the window"
      ],
      "delta": 0
    },
    "rejected": [
      {
        "index": 42,
        "symbol": "init_root_keyring",
        "target_va": "0xffff800081b5ab84",
        "function_size": 36,
        "delta": -1,
        "reason": "TOO_SMALL: size 36 < 56"
      },
      {
        "index": 44,
        "symbol": "crypto_algapi_init",
        "target_va": "0xffff800081b5bdfc",
        "function_size": 32,
        "delta": 1,
        "reason": "TOO_SMALL: size 32 < 56"
      },
      {
        "index": 45,
        "symbol": "blk_timeout_init",
        "target_va": "0xffff800081b5c734",
        "function_size": 24,
        "delta": 2,
        "reason": "TOO_SMALL: size 24 < 56"
      },
      {
        "index": 46,
        "symbol": "mst_irq_pm_init",
        "target_va": "0xffff800081b648e0",
        "function_size": 40,
        "delta": 3,
        "reason": "TOO_SMALL: size 40 < 56"
      },
      {
        "index": 47,
        "symbol": "pci_resource_alignment_sysfs_init",
        "target_va": "0xffff800081b6849c",
        "function_size": 44,
        "delta": 4,
        "reason": "TOO_SMALL: size 44 < 56"
      },
      {
        "index": 37,
        "symbol": "max_swapfiles_check",
        "target_va": "0xffff800081b4ff30",
        "function_size": 12,
        "delta": -6,
        "reason": "TOO_SMALL: size 12 < 56"
      }
    ],
    "conditional_candidates": [
      {
        "index": 43,
        "delta": 0,
        "symbol": "integrity_fs_init",
        "target_va": "0xffff800081b5bd1c",
        "function_size": 112,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 41,
        "delta": -2,
        "symbol": "pstore_init",
        "target_va": "0xffff800081b5a6fc",
        "function_size": 92,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 40,
        "delta": -3,
        "symbol": "check_early_ioremap_leak",
        "target_va": "0xffff800081b54348",
        "function_size": 108,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 39,
        "delta": -4,
        "symbol": "split_huge_pages_debugfs",
        "target_va": "0xffff800081b536f0",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 38,
        "delta": -5,
        "symbol": "slab_sysfs_init",
        "target_va": "0xffff800081b52c5c",
        "function_size": 400,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 48,
        "delta": 5,
        "symbol": "pci_sysfs_init",
        "target_va": "0xffff800081b689f8",
        "function_size": 112,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 49,
        "delta": 6,
        "symbol": "bert_init",
        "target_va": "0xffff800081b7017c",
        "function_size": 408,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 36,
        "delta": -7,
        "symbol": "fault_around_debugfs",
        "target_va": "0xffff800081b4e908",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 50,
        "delta": 7,
        "symbol": "clk_debug_init",
        "target_va": "0xffff800081b72f14",
        "function_size": 288,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 35,
        "delta": -8,
        "symbol": "load_system_certificate_list",
        "target_va": "0xffff800081b499e8",
        "function_size": 80,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 51,
        "delta": 8,
        "symbol": "setup_vcpu_hotplug_event",
        "target_va": "0xffff800081b87130",
        "function_size": 64,
        "window": 60,
        "overall": "PENDING"
      }
    ]
  },
  "LOW": {
    "nominal_index": 21,
    "primary": {
      "index": 21,
      "symbol": "kexec_core_sysctl_init",
      "target_va": "0xffff800081b47510",
      "image_offset": "0x1b47510",
      "function_size": 60,
      "window": 60,
      "predicted_architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
      "derived_window": null,
      "gates": [
        {
          "gate": "WINDOW_FIT",
          "status": "PASS",
          "reason": "window 60 fits inside function size 60 (no cross-function overwrite)"
        },
        {
          "gate": "ENTRY_PACIASP",
          "status": "PENDING",
          "reason": "entry instruction word unknown",
          "missing": [
            "first instruction word at target_va (objdump of the target function)"
          ]
        },
        {
          "gate": "INCOMING_BRANCHES",
          "status": "PENDING",
          "reason": "image-wide branch topology unknown",
          "missing": [
            "full-image branch scan at the final window (incoming_entry and incoming_window_interior must both be empty)"
          ]
        },
        {
          "gate": "INTERNAL_BRANCH_CLOSURE",
          "status": "PENDING",
          "reason": "internal branch topology unknown",
          "missing": [
            "disassembly of the target function (internal branches / back-edges and their window coverage)"
          ]
        },
        {
          "gate": "LITERAL_RELOCATION_OVERLAP",
          "status": "PENDING",
          "reason": "literal-pool / relocation evidence absent",
          "missing": [
            "relocation site list over the image (relocations_in_window == 0)",
            "adrp+add literal-reference scan resolving into the window"
          ]
        },
        {
          "gate": "EXTABLE_OVERLAP",
          "status": "PENDING",
          "reason": "__ex_table insn addresses unknown",
          "missing": [
            "decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: insn = &entry->insn + s32) checked against the window"
          ]
        },
        {
          "gate": "RUNTIME_REWRITE_OVERLAP",
          "status": "PENDING",
          "reason": "runtime-rewrite tables not fully characterized",
          "missing": [
            "decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) checked against the window"
          ]
        },
        {
          "gate": "INITCALL_TABLE_OVERLAP",
          "status": "PASS",
          "reason": "0 overlap with the late span [__initcall7_start, __initcall_end) or any other level span"
        },
        {
          "gate": "PREL32_ENTRY_UNCHANGED",
          "status": "PASS",
          "reason": "table word decodes to the window start; the probe writes only the function prologue, .init.data untouched (PREL32_TARGET_UNCHANGED)"
        }
      ],
      "overall": "PENDING",
      "missing_authoritative_map": [
        "first instruction word at target_va (objdump of the target function)",
        "full-image branch scan at the final window (incoming_entry and incoming_window_interior must both be empty)",
        "disassembly of the target function (internal branches / back-edges and their window coverage)",
        "relocation site list over the image (relocations_in_window == 0)",
        "adrp+add literal-reference scan resolving into the window",
        "decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: insn = &entry->insn + s32) checked against the window",
        "decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) checked against the window"
      ],
      "delta": 0
    },
    "rejected": [
      {
        "index": 22,
        "symbol": "bpf_rstat_kfunc_init",
        "target_va": "0xffff800081b47fb8",
        "function_size": 40,
        "delta": 1,
        "reason": "TOO_SMALL: size 40 < 56"
      },
      {
        "index": 19,
        "symbol": "bpf_ksym_iter_register",
        "target_va": "0xffff800081b4677c",
        "function_size": 40,
        "delta": -2,
        "reason": "TOO_SMALL: size 40 < 56"
      },
      {
        "index": 28,
        "symbol": "init_subsystem",
        "target_va": "0xffff8000801bead8",
        "function_size": 40,
        "delta": 7,
        "reason": "TOO_SMALL: size 40 < 56"
      }
    ],
    "conditional_candidates": [
      {
        "index": 21,
        "delta": 0,
        "symbol": "kexec_core_sysctl_init",
        "target_va": "0xffff800081b47510",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 20,
        "delta": -1,
        "symbol": "kernel_acct_sysctls_init",
        "target_va": "0xffff800081b467dc",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 23,
        "delta": 2,
        "symbol": "taskstats_init",
        "target_va": "0xffff800081b48b60",
        "function_size": 88,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 18,
        "delta": -3,
        "symbol": "tk_debug_sleep_time_init",
        "target_va": "0xffff800081b463b0",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 24,
        "delta": 3,
        "symbol": "bpf_global_ma_init",
        "target_va": "0xffff800081b48c14",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 17,
        "delta": -4,
        "symbol": "swiotlb_create_default_debugfs",
        "target_va": "0xffff800081b45140",
        "function_size": 176,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 25,
        "delta": 4,
        "symbol": "bpf_syscall_sysctl_init",
        "target_va": "0xffff800081b48c50",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 16,
        "delta": -5,
        "symbol": "init_srcu_module_notifier",
        "target_va": "0xffff800081b43878",
        "function_size": 72,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 26,
        "delta": 5,
        "symbol": "kfunc_init",
        "target_va": "0xffff800081b48cf0",
        "function_size": 164,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 15,
        "delta": -6,
        "symbol": "printk_late_init",
        "target_va": "0xffff800081b42e00",
        "function_size": 388,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 27,
        "delta": 6,
        "symbol": "bpf_map_iter_init",
        "target_va": "0xffff800081b48dac",
        "function_size": 64,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 14,
        "delta": -7,
        "symbol": "pm_debugfs_init",
        "target_va": "0xffff800081b41ec0",
        "function_size": 60,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 13,
        "delta": -8,
        "symbol": "cpu_latency_qos_init",
        "target_va": "0xffff800081b41e68",
        "function_size": 88,
        "window": 60,
        "overall": "PENDING"
      },
      {
        "index": 29,
        "delta": 8,
        "symbol": "task_iter_init",
        "target_va": "0xffff800081b48e10",
        "function_size": 232,
        "window": 60,
        "overall": "PENDING"
      }
    ]
  },
  "index_64_note": "init_subsystem alias (0xffff800080f4a804, 40 bytes) is TOO_SMALL for any inline probe",
  "pending_authoritative_map": {
    "MID": [
      "first instruction word at target_va (objdump of the target function)",
      "full-image branch scan at the final window (incoming_entry and incoming_window_interior must both be empty)",
      "disassembly of the target function (internal branches / back-edges and their window coverage)",
      "relocation site list over the image (relocations_in_window == 0)",
      "adrp+add literal-reference scan resolving into the window",
      "decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: insn = &entry->insn + s32) checked against the window",
      "decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) checked against the window"
    ],
    "LOW": [
      "first instruction word at target_va (objdump of the target function)",
      "full-image branch scan at the final window (incoming_entry and incoming_window_interior must both be empty)",
      "disassembly of the target function (internal branches / back-edges and their window coverage)",
      "relocation site list over the image (relocations_in_window == 0)",
      "adrp+add literal-reference scan resolving into the window",
      "decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: insn = &entry->insn + s32) checked against the window",
      "decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) checked against the window"
    ]
  },
  "frozen_rewrites": {
    "__ex_table": {
      "entries": 994,
      "sha256": "e93f6326dba119d9b5091b9c31295e47086ce45813b6f1a62dde0655ca65a9be"
    },
    "altinstructions": {
      "entries": 37287,
      "sha256": "a98a9bc613c12519ea5fd8f1e168ede872af0d8474fa385df6bc1cc17fdc36a6"
    },
    "__jump_table": "ABSENT",
    "static_call_sites": "ABSENT",
    "kcfi_traps": "ABSENT"
  }
}
```

Regenerate the full JSON (all gates for every neighbor) with:

```
python3 scripts/slot_b/late_level_cfg_audit.py --emit-report
```
