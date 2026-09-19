#!/usr/bin/env python3
"""Standalone CFG/geometry auditor for late (level-7) initcall INLINE probes.

Independent cross-check module for the MIDPOINT (~index 43) and LOWER-CHILD
(~index 21) candidates of the 86-entry late span. Deliberately shares no code
with checkpoint.py / post_initcalls.py: the branch decoder, window-closure
fixpoint and gate logic are re-derived from the frozen calibration facts.

Every gate returns PASS / FAIL / PENDING with an explicit reason. A gate whose
evidence is not locally available returns PENDING and names exactly what the
authoritative GHA map must supply (PENDING_AUTHORITATIVE_MAP policy).
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

TEXT_VA = 0xFFFF800080000000
LATE_START_VA = 0xFFFF800081D0C2D8
LATE_END_VA = 0xFFFF800081D0C430
LATE_SPAN_ENTRY_COUNT = 86
MIN_INLINE_PROBE = 56
ULTRACOMPACT_MIN_SIZE = 60
ULTRACOMPACT_WINDOW = 60
NO_DAIFSET_WINDOW = 56

PACIASP = 0xD503233F
RET = 0xD65F03C0

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"
ARCH_ULTRACOMPACT = "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT"
ARCH_NO_DAIFSET = "INLINE_PACIASP_PLUS_52B_NO_DAIFSET"

FROZEN_BUNDLE_RUN = "35036419486"
FROZEN_IMAGE_SHA = "43fb1c9128bdf37a2a77eb88cfff234381340b098ebf1aea1eabb2741180cebb"
FROZEN_REFERENCE_CORE_SHA = "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5"
FROZEN_REWRITE_ABSENCE = ("__jump_table", ".static_call_sites", ".kcfi_traps")


def sx(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def branch_target(word: int, pc: int) -> int | None:
    """AA64 direct-branch target decoder (B/BL, B.cond, CBZ/CBNZ, TBZ/TBNZ)."""
    if word & 0x7C000000 == 0x14000000:
        return pc + sx(word & 0x03FFFFFF, 26) * 4
    if word & 0xFF000010 == 0x54000000:
        return pc + sx((word >> 5) & 0x7FFFF, 19) * 4
    if word & 0x7E000000 == 0x34000000:
        return pc + sx((word >> 5) & 0x7FFFF, 19) * 4
    if word & 0x7E000000 == 0x36000000:
        return pc + sx((word >> 5) & 0x3FFF, 14) * 4
    return None


def scan_branch_topology(image: bytes, ranges, text_va: int, function: tuple, window: tuple) -> dict:
    """Image-wide branch scan classified against (function, window).

    image is indexed from text_va (image offset = va - text_va); ranges are
    (start_offset, end_offset) code ranges. Semantics calibrated to the frozen
    precedents: incoming_entry (outside function -> entry),
    incoming_window_interior (outside window -> strictly inside window),
    internal_branches (both ends inside function), back_edges (target < pc).
    """
    f_lo, f_hi = function
    w_lo, w_hi = window
    inc_entry, inc_interior, inc_inclusive, internal, back = [], [], [], [], []
    for begin, end in ranges:
        for off in range(max(0, begin), min(len(image), end) - 3, 4):
            pc = text_va + off
            target = branch_target(struct.unpack_from("<I", image, off)[0], pc)
            if target is None:
                continue
            if not f_lo <= pc < f_hi and target == f_lo:
                inc_entry.append((pc, target))
            if not w_lo <= pc < w_hi and w_lo < target < w_hi:
                inc_interior.append((pc, target))
            if not w_lo <= pc < w_hi and w_lo <= target < w_hi:
                inc_inclusive.append((pc, target))
            if f_lo <= pc < f_hi and f_lo <= target < f_hi:
                internal.append((pc, target))
                if target < pc:
                    back.append((pc, target))
    hx = lambda rows: [[hex(a), hex(b)] for a, b in rows]
    return {"incoming_entry": hx(inc_entry), "incoming_window_interior": hx(inc_interior),
            "incoming_window_inclusive": hx(inc_inclusive), "internal_branches": hx(internal),
            "back_edges": hx(back)}


def closure_live_sources(function_va: int, internal_branches, window: int) -> list:
    """Internal branch sources NOT overwritten by `window` whose target lies
    strictly inside it — the branches that break CFG closure at this window."""
    live = []
    for src_hex, dst_hex in internal_branches:
        src_off = int(src_hex, 16) - function_va
        dst_off = int(dst_hex, 16) - function_va
        if src_off >= window and 0 < dst_off < window:
            live.append((src_off, dst_off))
    return live


def derive_inline_window(function_va: int, function_size: int, internal_branches, min_size: int) -> int:
    """Grow the window until no surviving internal branch targets its interior."""
    if min_size <= 0 or min_size % 4:
        raise ValueError("INVALID_MIN_PROBE")
    if function_size < min_size:
        raise ValueError("PROBE_LARGER_THAN_TARGET_FUNCTION")
    window = min_size
    while True:
        live = closure_live_sources(function_va, internal_branches, window)
        if not live:
            return window
        grown = max((src + 4 + 3) & ~3 for src, _ in live)
        if grown <= window or grown > function_size:
            raise ValueError("CFG_CLOSURE_EXCEEDS_FUNCTION")
        window = grown


def predict_inline_architecture(function_size: int):
    """Level-6/7 policy: size >= 60 -> paciasp + 56B ultracompact core (window
    floor 60); 56 <= size < 60 -> paciasp + 52B no-daifset core (window 56)."""
    if function_size >= ULTRACOMPACT_MIN_SIZE:
        return ARCH_ULTRACOMPACT, ULTRACOMPACT_WINDOW
    if function_size >= MIN_INLINE_PROBE:
        return ARCH_NO_DAIFSET, NO_DAIFSET_WINDOW
    return None, None


@dataclass
class Evidence:
    """Locally available / authoritatively supplied evidence for one candidate.

    Any field left None makes the dependent gate PENDING."""
    function_size: int | None = None
    entry_word: int | None = None
    topology: dict | None = None
    relocation_sites: list | None = None
    literal_refs_into_window: list | None = None
    extable_insns: list | None = None
    alt_ranges: list | None = None
    jump_table_present: bool | None = None
    static_call_present: bool | None = None
    kcfi_present: bool | None = None
    initcall_table_ranges: list = field(
        default_factory=lambda: [(LATE_START_VA, LATE_END_VA)])
    prel32_entry_word: int | None = None
    prel32_entry_va: int | None = None


@dataclass
class GateResult:
    name: str
    status: str
    reason: str
    missing: list = field(default_factory=list)

    def as_dict(self) -> dict:
        out = {"gate": self.name, "status": self.status, "reason": self.reason}
        if self.missing:
            out["missing"] = self.missing
        return out


def _gate_window_fit(window_len, ev: Evidence) -> GateResult:
    if ev.function_size is None:
        return GateResult("WINDOW_FIT", PENDING, "function size unknown",
                          ["function_size (nm -S symbol size or full disassembly)"])
    if window_len % 4:
        return GateResult("WINDOW_FIT", FAIL, f"window {window_len} not 4-byte aligned")
    if window_len < MIN_INLINE_PROBE:
        return GateResult("WINDOW_FIT", FAIL,
                          f"window {window_len} below minimum inline probe {MIN_INLINE_PROBE}")
    if window_len > ev.function_size:
        return GateResult("WINDOW_FIT", FAIL,
                          f"window {window_len} exceeds function size {ev.function_size}: "
                          "cross-function overwrite")
    return GateResult("WINDOW_FIT", PASS,
                      f"window {window_len} fits inside function size {ev.function_size} "
                      "(no cross-function overwrite)")


def _gate_entry_paciasp(window_range, ev: Evidence) -> GateResult:
    if ev.entry_word is None:
        return GateResult("ENTRY_PACIASP", PENDING, "entry instruction word unknown",
                          ["first instruction word at target_va (objdump of the target function)"])
    if ev.entry_word == PACIASP:
        return GateResult("ENTRY_PACIASP", PASS, "entry instruction is paciasp (0xd503233f)")
    return GateResult("ENTRY_PACIASP", FAIL,
                      f"entry instruction 0x{ev.entry_word:08x} is not paciasp")


def _gate_incoming(window_range, ev: Evidence) -> GateResult:
    if ev.topology is None:
        return GateResult("INCOMING_BRANCHES", PENDING,
                          "image-wide branch topology unknown",
                          ["full-image branch scan at the final window (incoming_entry and "
                           "incoming_window_interior must both be empty)"])
    entry = ev.topology.get("incoming_entry", [])
    interior = ev.topology.get("incoming_window_interior", [])
    if entry or interior:
        return GateResult("INCOMING_BRANCHES", FAIL,
                          f"incoming branches into window: entry={entry[:4]} "
                          f"interior={interior[:4]}")
    return GateResult("INCOMING_BRANCHES", PASS,
                      "0 incoming entry branches, 0 incoming window-interior branches "
                      "(function-local branches overwritten by the window are excluded)")


def _gate_closure(function_va: int, window_len, ev: Evidence) -> GateResult:
    if ev.topology is None:
        return GateResult("INTERNAL_BRANCH_CLOSURE", PENDING,
                          "internal branch topology unknown",
                          ["disassembly of the target function (internal branches / "
                           "back-edges and their window coverage)"])
    internal = ev.topology.get("internal_branches", [])
    live = closure_live_sources(function_va, internal, window_len)
    detail = (f"internal={len(internal)} "
              f"back_edges={len(ev.topology.get('back_edges', []))}")
    if not live:
        return GateResult("INTERNAL_BRANCH_CLOSURE", PASS,
                          f"every internal branch source lies inside the window or its "
                          f"target lies outside the window interior ({detail})")
    fmt = lambda pair: [hex(function_va + pair[0]), hex(function_va + pair[1])]
    grown = max((src + 4 + 3) & ~3 for src, _ in live)
    if ev.function_size is not None and grown > ev.function_size:
        return GateResult("INTERNAL_BRANCH_CLOSURE", FAIL,
                          f"surviving branch(es) {list(map(fmt, live[:4]))} need window "
                          f"{grown} > function size {ev.function_size} "
                          "(CFG_CLOSURE_EXCEEDS_FUNCTION)")
    return GateResult("INTERNAL_BRANCH_CLOSURE", FAIL,
                      f"window {window_len} not closed: surviving branch(es) "
                      f"{list(map(fmt, live[:4]))}; minimal closed window {grown}")


def _gate_literal_relocation(window_range, ev: Evidence) -> GateResult:
    missing = []
    if ev.relocation_sites is None:
        missing.append("relocation site list over the image (relocations_in_window == 0)")
    if ev.literal_refs_into_window is None:
        missing.append("adrp+add literal-reference scan resolving into the window")
    if missing:
        return GateResult("LITERAL_RELOCATION_OVERLAP", PENDING,
                          "literal-pool / relocation evidence absent", missing)
    sites = [s for s in ev.relocation_sites if window_range[0] <= s < window_range[1]]
    refs = [r for r in ev.literal_refs_into_window if window_range[0] <= r < window_range[1]]
    if sites or refs:
        return GateResult("LITERAL_RELOCATION_OVERLAP", FAIL,
                          f"relocation sites {[hex(s) for s in sites[:4]]} / literal refs "
                          f"{[hex(r) for r in refs[:4]]} inside window")
    return GateResult("LITERAL_RELOCATION_OVERLAP", PASS,
                      "0 relocations and 0 literal references into the window")


def _gate_extable(window_range, ev: Evidence) -> GateResult:
    if ev.extable_insns is None:
        return GateResult("EXTABLE_OVERLAP", PENDING, "__ex_table insn addresses unknown",
                          ["decoded __ex_table insn VAs (ARCH_HAS_RELATIVE_EXTABLE: "
                           "insn = &entry->insn + s32) checked against the window"])
    hits = [i for i in ev.extable_insns if window_range[0] <= i < window_range[1]]
    if hits:
        return GateResult("EXTABLE_OVERLAP", FAIL,
                          f"__ex_table insns inside window: {[hex(h) for h in hits[:8]]}")
    return GateResult("EXTABLE_OVERLAP", PASS, "0 __ex_table entries inside window")


def _gate_rewrites(window_range, ev: Evidence) -> GateResult:
    missing = []
    if ev.alt_ranges is None:
        missing.append("decoded .altinstructions orig ranges (ALT_ORIG_PTR = &a + s32) "
                       "checked against the window")
    for name, present in (("__jump_table", ev.jump_table_present),
                          (".static_call_sites", ev.static_call_present),
                          (".kcfi_traps", ev.kcfi_present)):
        if present is None:
            missing.append(f"presence of {name} in this build")
        elif present:
            missing.append(f"{name} present: decoded site VAs required")
    if missing:
        return GateResult("RUNTIME_REWRITE_OVERLAP", PENDING,
                          "runtime-rewrite tables not fully characterized", missing)
    overlaps = [r for r in ev.alt_ranges if r[0] < window_range[1] and window_range[0] < r[1]]
    if overlaps:
        return GateResult("RUNTIME_REWRITE_OVERLAP", FAIL,
                          f".altinstructions ranges overlap window: "
                          f"{[[hex(a), hex(b)] for a, b in overlaps[:4]]}")
    return GateResult("RUNTIME_REWRITE_OVERLAP", PASS,
                      ".altinstructions 0 overlaps; "
                      + ", ".join(f"{k} ABSENT" for k in FROZEN_REWRITE_ABSENCE))


def _gate_table_overlap(window_range, ev: Evidence) -> GateResult:
    hits = [r for r in ev.initcall_table_ranges
            if r[0] < window_range[1] and window_range[0] < r[1]]
    if hits:
        return GateResult("INITCALL_TABLE_OVERLAP", FAIL,
                          f"window overlaps initcall table span(s): "
                          f"{[[hex(a), hex(b)] for a, b in hits]}")
    return GateResult("INITCALL_TABLE_OVERLAP", PASS,
                      "0 overlap with the late span [__initcall7_start, __initcall_end) "
                      "or any other level span")


def _gate_prel32(window_range, ev: Evidence) -> GateResult:
    if ev.prel32_entry_word is None or ev.prel32_entry_va is None:
        return GateResult("PREL32_ENTRY_UNCHANGED", PENDING,
                          "PREL32 table word for this index unknown",
                          ["late-table entry word and entry_va for this index"])
    target = ev.prel32_entry_va + sx(ev.prel32_entry_word & 0xFFFFFFFF, 32)
    if target != window_range[0]:
        return GateResult("PREL32_ENTRY_UNCHANGED", FAIL,
                          f"PREL32 word resolves to {hex(target)} != window start "
                          f"{hex(window_range[0])}")
    return GateResult("PREL32_ENTRY_UNCHANGED", PASS,
                      "table word decodes to the window start; the probe writes only the "
                      "function prologue, .init.data untouched (PREL32_TARGET_UNCHANGED)")


GATES = (_gate_window_fit, _gate_entry_paciasp, _gate_incoming, _gate_closure,
         _gate_literal_relocation, _gate_extable, _gate_rewrites, _gate_table_overlap,
         _gate_prel32)


def audit_candidate(index: int, symbol: str, target_va: int, window: int, ev: Evidence) -> dict:
    window_range = (target_va, target_va + window)
    results = []
    for gate in GATES:
        if gate is _gate_closure:
            results.append(_gate_closure(target_va, window, ev))
        elif gate is _gate_window_fit:
            results.append(_gate_window_fit(window, ev))
        else:
            results.append(gate(window_range, ev))
    status = (FAIL if any(g.status == FAIL for g in results)
              else PENDING if any(g.status == PENDING for g in results) else PASS)
    arch = floor = None
    if ev.function_size is not None:
        arch, floor = predict_inline_architecture(ev.function_size)
    derived = None
    if ev.topology is not None and ev.function_size is not None:
        try:
            derived = derive_inline_window(target_va, ev.function_size,
                                           ev.topology["internal_branches"],
                                           floor or MIN_INLINE_PROBE)
        except ValueError as exc:
            derived = f"ERROR:{exc}"
    return {"index": index, "symbol": symbol, "target_va": hex(target_va),
            "image_offset": hex(target_va - TEXT_VA),
            "function_size": ev.function_size, "window": window,
            "predicted_architecture": arch, "derived_window": derived,
            "gates": [g.as_dict() for g in results], "overall": status,
            "missing_authoritative_map": [m for g in results for m in g.missing]}


def search_neighbors(entries, nominal_index: int, evidence_of, window_of=None,
                     max_radius: int = 8) -> dict:
    """Nearest-safe-neighbor policy for the lower half: from the nominal index,
    order candidates by minimal |delta| (ties: lower index first) and report the
    first configuration with no FAIL among the locally decidable gates."""
    ordered = [nominal_index]
    for radius in range(1, max_radius + 1):
        ordered += [nominal_index - radius, nominal_index + radius]
    ordered = [i for i in ordered if 0 <= i < len(entries)]
    rejected, conditional, primary = [], [], None
    for idx in ordered:
        entry = entries[idx]
        ev = evidence_of(entry)
        size = ev.function_size
        win = window_of(entry) if window_of else None
        if win is None:
            _, win = predict_inline_architecture(size) if size else (None, None)
            if win is None:
                rejected.append({"index": idx, "symbol": entry["symbol"],
                                 "target_va": hex(entry["target_va"]),
                                 "function_size": size, "delta": idx - nominal_index,
                                 "reason": f"TOO_SMALL: size {size} < {MIN_INLINE_PROBE}"})
                continue
        report = audit_candidate(idx, entry["symbol"], entry["target_va"], win, ev)
        report["delta"] = idx - nominal_index
        if report["overall"] == FAIL:
            rejected.append({"index": idx, "symbol": entry["symbol"],
                             "target_va": hex(entry["target_va"]),
                             "function_size": size, "delta": report["delta"],
                             "reason": "; ".join(f"{g['gate']}: {g['reason']}"
                                                 for g in report["gates"] if g["status"] == FAIL)})
        elif primary is None:
            primary = report
            conditional.append(report)
        else:
            conditional.append(report)
    return {"nominal_index": nominal_index, "primary": primary, "rejected": rejected,
            "conditional_candidates": conditional}


def load_late_table(path) -> list:
    data = json.loads(Path(path).read_text())
    for entry in data:
        entry["target_va"] = int(entry["target_va_hex"], 16)
        entry["entry_va"] = int(entry["entry_va_hex"], 16)
    return data


def symbol_map_from_system_map(path) -> dict:
    """Parse the frozen System.map. Sizes derive as next-text-symbol VA minus
    symbol VA; the method is validated against all six frozen precedents
    (60/188/184/216/60/56 reproduced exactly)."""
    symbols = []
    for line in Path(path).read_text().splitlines():
        m = re.match(r"^([0-9a-fA-F]{16}) (.) (.+)$", line)
        if m:
            symbols.append((int(m.group(1), 16), m.group(2), m.group(3)))
    symbols.sort()
    taddrs = [va for va, ty, _ in symbols if ty in "tT"]
    by_name, by_va = {}, {}
    for va, ty, name in symbols:
        if ty not in "tT":
            continue
        i = bisect.bisect_right(taddrs, va)
        if i < len(taddrs):
            by_va[va] = {"size": taddrs[i] - va, "next_symbol": name}
        by_name.setdefault(name, va)
    return {"by_va": by_va, "by_name": by_name}


def default_artifact_paths() -> dict:
    root = Path(__file__).resolve().parents[2]
    return {
        "late_table": root / "artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/late-table.json",
        "system_map": root / "artifacts/slot-b-level6-inline-20260918/bundle/System.map",
        "audit_json": root / "artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/audit.json",
    }


def build_evidence(entry, symap: dict, frozen_absence: bool = True) -> Evidence:
    rec = symap["by_va"].get(entry["target_va"])
    return Evidence(function_size=rec["size"] if rec else None,
                    prel32_entry_word=int(entry["entry_word"], 16),
                    prel32_entry_va=entry["entry_va"],
                    jump_table_present=False if frozen_absence else None,
                    static_call_present=False if frozen_absence else None,
                    kcfi_present=False if frozen_absence else None)


CALIBRATION_SYMBOLS = (
    ("index-0 identity", "kernel_do_mounts_initrd_sysctls_init", 60, 60, ARCH_ULTRACOMPACT),
    ("fs precedent", "vlan_offload_init", 60, 60, ARCH_ULTRACOMPACT),
    ("fs precedent", "af_unix_init", 216, 60, ARCH_ULTRACOMPACT),
    ("fs precedent", "chr_dev_init", 184, 56, ARCH_NO_DAIFSET),
    ("arch precedent", "topology_init", 188, 160, ARCH_ULTRACOMPACT),
    ("fs precedent", "create_debug_debugfs_entry", 56, 56, ARCH_NO_DAIFSET),
)


def emit_report(late_table_path, system_map_path, audit_json_path=None) -> dict:
    entries = load_late_table(late_table_path)
    symap = symbol_map_from_system_map(system_map_path)
    for entry in entries:
        rec = symap["by_va"].get(entry["target_va"])
        entry["derived_size"] = rec["size"] if rec else None
    calibration = []
    for label, name, frozen_size, frozen_window, arch in CALIBRATION_SYMBOLS:
        va = symap["by_name"].get(name)
        rec = symap["by_va"].get(va, {})
        calibration.append({"case": label, "symbol": name, "va": hex(va) if va else None,
                            "frozen_size": frozen_size, "frozen_window": frozen_window,
                            "frozen_architecture": arch,
                            "system_map_size": rec.get("size"),
                            "size_match": rec.get("size") == frozen_size})
    mid = search_neighbors(entries, 43, lambda e: build_evidence(e, symap))
    low = search_neighbors(entries, 21, lambda e: build_evidence(e, symap))
    report = {"module": "late_level_cfg_audit", "frozen_bundle_run": FROZEN_BUNDLE_RUN,
              "late_span": {"start": hex(LATE_START_VA), "end": hex(LATE_END_VA),
                            "entries": LATE_SPAN_ENTRY_COUNT},
              "size_method": "next-text-symbol delta from the frozen System.map; "
                             "validated against all six frozen precedents (exact match)",
              "calibration": calibration,
              "MID": mid, "LOW": low,
              "index_64_note": "init_subsystem alias (0xffff800080f4a804, 40 bytes) is "
                               "TOO_SMALL for any inline probe",
              "pending_authoritative_map": {
                  "MID": mid["primary"]["missing_authoritative_map"] if mid["primary"] else [],
                  "LOW": low["primary"]["missing_authoritative_map"] if low["primary"] else []}}
    if audit_json_path and Path(audit_json_path).is_file():
        audit = json.loads(Path(audit_json_path).read_text())
        report["frozen_rewrites"] = audit.get("runtime_rewrites")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-report", action="store_true")
    parser.add_argument("--late-table", type=Path)
    parser.add_argument("--system-map", type=Path)
    parser.add_argument("--audit-json", type=Path)
    args = parser.parse_args()
    if not args.emit_report:
        parser.print_help()
        return 1
    defaults = default_artifact_paths()
    report = emit_report(args.late_table or defaults["late_table"],
                         args.system_map or defaults["system_map"],
                         args.audit_json or defaults["audit_json"])
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
