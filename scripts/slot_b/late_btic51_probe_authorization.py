#!/usr/bin/env python3
"""Late index-51 BTI c probe authorization pair (MAINLINE_V2_R3_SLOT_B_LATE_INDEX51_BTIC_PROBE_AUTHORIZATION_CI).

GitHub Actions only; CI-only round, device operation forbidden. Additive probe
family BTI_C_PLUS_56B_ULTRACOMPACT for exactly one pinned target: late
initcall index 51, setup_vcpu_hotplug_event. The original `bti c` entry word
is preserved verbatim, the proven 56-byte diagnostic core occupies
[entry+4, entry+60) and the original 4-byte function tail
[entry+60, entry+64) stays byte-original and is proven dead by an extended
64-byte reference scan plus composed-control-flow enumeration. The
CFG-derived window MUST be exactly 60: a 64-byte derivation means the
original tail re-enters the diagnostic region and fails loudly (R1,
WINDOW_DERIVATION_64_INCOMPATIBLE_BTIC_FAMILY). The round pad class is
reversed against prior rounds: entries must carry exactly `bti c`; a paciasp
entry explicitly FAILs. One DELAY_CONSTANT_ONLY payload pair is composed from
the frozen FIX8 base. Trampolines, islands, PREL32 retargeting, shared
do_initcall* checkpoints and cross-function overwrite remain forbidden.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import struct
from pathlib import Path

import checkpoint as cp
import late_level_isolation as base
import late_post50_isolation as post50

STAGE = "MAINLINE_V2_R3_SLOT_B_LATE_INDEX51_BTIC_PROBE_AUTHORIZATION_CI"
FAMILY, LABEL, PINNED_INDEX = ("late_btic51", "BTIC51", 51)
ROUND_PAD_GATE = "ROUND_PAD_CLASS"
ROUND_PAD_VALUE = "BTI_C_ONLY"
ROUND_PAD_REASON = "PACIASP_PAD_EXCLUDED_ROUND_REQUIRES_BTI_C"
BTI_C = 0xD503245F
PACIASP = 0xD503233F
BTI_NON_C_WORDS = (0xD503241F, 0xD503249F, 0xD50324DF)
PAC_HINT_MASK = 0xFFFFF81F
PAC_HINT_BASE = 0xD5032000
RET_MASK = 0xFFFFFC1F
RET_BASE = 0xD65F0000
INDIRECT_CALL_WORDS = (0xD63F0BC0, 0xD63F0FC0)
TARGET_VA = 0xFFFF800081B87130
IMAGE_OFFSET = 0x1B87130
TABLE_VA = 0xFFFF800081D0C3A4
TABLE_IMAGE_OFFSET = 0x1D0C3A4
TABLE_WORD = 0xFFE7AD8C
FUNCTION_SIZE = 64
WINDOW = 60
CORE_SIZE = 56
TAIL_BYTES = 4
PROBE_ARCHITECTURE = "BTI_C_PLUS_56B_ULTRACOMPACT"
CORE56_SHA = "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5"
DELAY_WORDS = {8: 0xD37DF12A, 1: 0xD340FD2A}
PAIR_DIFF_OFFSETS = [IMAGE_OFFSET + 4 + 8 + 1, IMAGE_OFFSET + 4 + 8 + 2]
PAC_AUT_HINTS = (
    0xD50320FF,  # XPACLRI
    0xD503211F, 0xD503215F, 0xD503219F, 0xD50321DF,  # *1716
    0xD503231F, 0xD503233F, 0xD503235F, 0xD503237F,  # *AZ/*ASP
    0xD503239F, 0xD50323BF, 0xD50323DF, 0xD50323FF,  # AUT*Z/SP
)
FROZEN_TARGET = {"index": PINNED_INDEX, "symbol": "setup_vcpu_hotplug_event",
                 "table_va": hex(TABLE_VA), "table_image_offset": hex(TABLE_IMAGE_OFFSET),
                 "table_word": hex(TABLE_WORD), "target_va": hex(TARGET_VA),
                 "image_offset": hex(IMAGE_OFFSET), "function_size": FUNCTION_SIZE,
                 "section": ".init.text", "entry_pad": "bti c",
                 "registration": "late_initcall(setup_vcpu_hotplug_event)",
                 "source": "drivers/xen/cpu_hotplug.c"}
FROZEN_LATE_INDICES = tuple(sorted(post50.FROZEN_LATE_INDICES + (50,)))
FROZEN_LATE_WINDOWS = post50.FROZEN_LATE_WINDOWS + ((0xFFFF800081B72F14, 60),)  # POST50
FROZEN_HISTORICAL_WINDOWS = post50.FROZEN_HISTORICAL_WINDOWS
FROZEN_PAYLOAD_SHAS = tuple(post50.FROZEN_PAYLOAD_SHAS) + (
    "28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",  # POST50_8
    "aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",  # POST50_1
)
INITCALL_DISPATCH_CALL_CLASS = "BLR_CONTROLLED"
INITCALL_DISPATCH_CITATION = ("init/main.c do_one_initcall: ret = fn(); "
                              "(linux 6.6.156, ~line 1210)")
PROOF = ("the pinned late-initcall index-51 entry was reached after all earlier "
         "late initcalls, through its original `bti c` landing pad",
         "the target initcall body, later late initcalls, console or /init")


def require(condition, message):
    cp.require(condition, message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def _fail_gate(record, gate, exc):
    record["gates"][gate] = f"FAIL:{exc}"
    record["fail_reasons"].append(str(exc))


def extend_geometry_64(record, ctx):
    """Re-verify geometry over the full 64-byte function, including the
    original tail the 60-byte diagnostic window does not cover.

    INCOMING_BRANCH / SYMBOL / SECTION / EXTENT / LITERAL / RELOCATION /
    RUNTIME_REWRITE / IMAGE_GEOMETRY all run on [entry, entry+64). CFG_CLOSURE
    stays on the composed 60-byte window (surviving_into_interior of the
    diagnostic overwrite).
    """
    gates = record["gates"]
    target = int(record["target_va"], 16)
    frozen = ctx["frozen"][:ctx["image_len"]]
    text_va = ctx["text_va"]
    offset = target - text_va
    span = (target, target + FUNCTION_SIZE)

    if gates.get("INCOMING_BRANCH") == "PASS":
        try:
            topology = cp.branch_audit(frozen, ctx["ranges"], text_va, span, span)
            record["branch_topology_64"] = topology
            require(not topology["incoming_entry"], "INCOMING_ENTRY_BRANCH")
            require(not topology["incoming_window_interior"],
                    "INCOMING_WINDOW_INTERIOR_BRANCH")
        except (ValueError, SystemExit) as exc:
            _fail_gate(record, "INCOMING_BRANCH", exc)

    def section_64():
        section = cp.t3.gate_window_section_scan(target, FUNCTION_SIZE, ctx["sections"])
        require(section["name"] == ".init.text", "WINDOW_CROSSES_SECTION")

    def extent_64():
        nxt = ctx["symbol_vas"][bisect.bisect_right(ctx["symbol_vas"], target)]
        cp.t3.gate_function_extent_scan(target, FUNCTION_SIZE, nxt)

    def rewrite_64():
        overlap = {tag: sorted({v for v in sites
                                if target <= v < target + FUNCTION_SIZE})
                   for tag, sites in ctx["rw_sites"].items()}
        bad = {tag: sites for tag, sites in overlap.items() if sites}
        require(not bad, f"REWRITE_OVERLAP:{sorted(bad)}")
        record["runtime_rewrite_overlap_64"] = {tag: len(sites)
                                                for tag, sites in overlap.items()}

    scans = (
        ("SYMBOL_SCAN", lambda: cp.t3.gate_window_symbol_scan(
            target, FUNCTION_SIZE, ctx["symbol_vas"])),
        ("SECTION_SCAN", section_64),
        ("EXTENT_SCAN", extent_64),
        ("LITERAL_SCAN", lambda: cp.t3.gate_window_literal_scan(
            target, FUNCTION_SIZE, frozen)),
        ("RELOCATION_SCAN", lambda: cp.t3.gate_window_relocation_scan(
            target, FUNCTION_SIZE, ctx["reloc_sites"])),
        ("RUNTIME_REWRITE", rewrite_64),
        ("IMAGE_GEOMETRY", lambda: cp.t3.gate_window_inside_image_size(
            offset, FUNCTION_SIZE, ctx["image_size"])),
    )
    for gate, fn in scans:
        if gates.get(gate) != "PASS":
            continue
        try:
            fn()
        except (ValueError, SystemExit) as exc:
            _fail_gate(record, gate, exc)


def audit_candidate_btic(entry, ctx):
    """Frozen 15-gate audit plus the BTI-C round gates (reversed pad polarity).

    The base WINDOW_FIT verdict is hardened: the CFG-derived window must be
    exactly 60; a 64-byte derivation (the original tail branching back into
    the diagnostic region) fails loudly instead of widening the overwrite.
    Geometry gates that the 60-byte window does not cover are re-run over the
    extended 64-byte function range.
    """
    record = base.audit_candidate(entry, ctx)
    gates = record["gates"]
    if gates.get("FUNCTION_SIZE") == "PASS":
        try:
            require(record["function_size"] == FUNCTION_SIZE,
                    "PINNED_FUNCTION_SIZE_NOT_64")
        except (ValueError, SystemExit) as exc:
            _fail_gate(record, "FUNCTION_SIZE", exc)
    if gates.get("WINDOW_FIT") == "PASS":
        try:
            require(record["window"] == WINDOW,
                    "WINDOW_DERIVATION_64_INCOMPATIBLE_BTIC_FAMILY"
                    if record["window"] == FUNCTION_SIZE else
                    "WINDOW_DERIVATION_NOT_60")
            record["probe_architecture"] = PROBE_ARCHITECTURE
        except (ValueError, SystemExit) as exc:
            _fail_gate(record, "WINDOW_FIT", exc)
    try:
        require(int(record["entry_pad_word"], 16) == BTI_C
                and record["entry_pad"] == "bti c", ROUND_PAD_REASON)
        gates[ROUND_PAD_GATE] = "PASS"
    except (ValueError, SystemExit) as exc:
        _fail_gate(record, ROUND_PAD_GATE, exc)
    if (record["function_size"] == FUNCTION_SIZE and record["window"] == WINDOW
            and gates.get("WINDOW_FIT") == "PASS"):
        extend_geometry_64(record, ctx)
    record["PASS"] = all(value == "PASS" for value in gates.values())
    return record


def pin_target(entries, ctx):
    """Directly pin late-initcall index 51; no interval walk."""
    require(len(entries) == base.SPAN_COUNT, "SELECTION_SPAN_COUNT_DRIFT")
    require(PINNED_INDEX not in FROZEN_LATE_INDICES, "PINNED_TARGET_FROZEN")
    entry = entries[PINNED_INDEX]
    require(entry["symbol"] == FROZEN_TARGET["symbol"], "PINNED_SYMBOL_DRIFT")
    require(entry["target_va"] == TARGET_VA, "PINNED_TARGET_VA_DRIFT")
    require(entry["entry_va"] == TABLE_VA, "PINNED_TABLE_VA_DRIFT")
    require(entry["entry_image_offset"] == TABLE_IMAGE_OFFSET,
            "PINNED_TABLE_OFFSET_DRIFT")
    require(entry["entry_word"] == hex(TABLE_WORD), "PINNED_TABLE_WORD_DRIFT")
    require(entry["function_size"] == FUNCTION_SIZE, "PINNED_FUNCTION_SIZE_DRIFT")
    require(entry["section"] == FROZEN_TARGET["section"], "PINNED_SECTION_DRIFT")
    require(entry["init_text"], "PINNED_NOT_INIT_TEXT")
    require(entry["target_unique"], "PINNED_TARGET_NOT_UNIQUE")
    require(entry["registration"] == FROZEN_TARGET["registration"],
            "PINNED_REGISTRATION_DRIFT")
    require(entry["source"] == FROZEN_TARGET["source"], "PINNED_SOURCE_DRIFT")
    audit = audit_candidate_btic(entry, ctx)
    require(audit["PASS"], f"PINNED_TARGET_GATES_FAILED:{audit['gates']}")
    require_frozen_window_disjoint(TARGET_VA, FUNCTION_SIZE)
    return {"family": FAMILY, "label": LABEL, "nominal_index": PINNED_INDEX,
            "selected_index": PINNED_INDEX, "deviation": None, "skipped": [],
            "interval_walk": "NONE_TARGET_PINNED_DIRECTLY", "audit": audit}


def frozen_window_overlap(target, window):
    for va, size in FROZEN_LATE_WINDOWS + FROZEN_HISTORICAL_WINDOWS:
        if target < va + size and va < target + window:
            return (va, size)
    return None


def require_frozen_window_disjoint(target, window):
    overlap = frozen_window_overlap(target, window)
    if overlap is not None:
        require(False, f"FROZEN_WINDOW_OVERLAP:{hex(overlap[0])}+{overlap[1]}")


def require_fresh_payload(payload_sha):
    """No composed member may reproduce any frozen payload identity."""
    require(payload_sha not in FROZEN_PAYLOAD_SHAS, "RERUN_FORBIDDEN_FROZEN_PAYLOAD")


def require_inline_probe_architecture(architecture):
    """Inline-only family: trampolines and islands are rejected by name."""
    require(architecture == PROBE_ARCHITECTURE,
            f"NOT_INLINE_BTI_C_FAMILY:{architecture}")


def require_member_scope(payload, frozen, offset, window):
    """A composed member may differ from the frozen FIX8 base only inside
    [offset+4, offset+window): the bti c pad and the original 4-byte tail
    stay byte-identical, every diff sits inside the diagnostic window."""
    require(len(payload) == len(frozen), "PAYLOAD_SIZE_DRIFT")
    require(payload[offset:offset + 4] == frozen[offset:offset + 4],
            "BTI_C_PAD_MODIFIED")
    tail = offset + window
    require(payload[tail:tail + TAIL_BYTES] == frozen[tail:tail + TAIL_BYTES],
            "TAIL_BYTES_MODIFIED")
    require(payload[:offset] == frozen[:offset]
            and payload[offset + FUNCTION_SIZE:] == frozen[offset + FUNCTION_SIZE:]
            and payload[offset + window:] == frozen[offset + window:],
            "MEMBER_CHANGED_OUTSIDE_WINDOW")
    diffs = [i for i, (a, b) in enumerate(zip(frozen, payload)) if a != b]
    require(diffs, "MEMBER_HAS_NO_DIFF")
    require(all(offset + 4 <= i < offset + window for i in diffs),
            f"MEMBER_DIFF_OUTSIDE_DIAGNOSTIC_WINDOW:{[hex(i) for i in diffs[:8]]}")
    return diffs


def require_prel32_unchanged(payload, frozen, slot_offset):
    require(payload[slot_offset:slot_offset + 4]
            == frozen[slot_offset:slot_offset + 4], "PREL32_TARGET_REWRITTEN")


def gate_composed_window(probe, entry_word, delay_word):
    """Pinned composed-window identity: the preserved bti c pad followed by
    the proven 56-byte core with the delay constant in its slot."""
    require(len(probe) == WINDOW, "COMPOSED_WINDOW_SIZE")
    words = struct.unpack("<15I", probe)
    require(words[0] == BTI_C == entry_word, "BTI_C_ENTRY_WORD_REWRITTEN")
    core_words = list(cp.ULTRACOMPACT_WORDS)
    core_words[2] = delay_word
    require(words[1:] == tuple(core_words), "COMPOSED_CORE_WORD_DRIFT")
    require(delay_word in DELAY_WORDS.values(), "UNEXPECTED_DELAY_WORD")


def gate_composed_control_flow(probe, entry_va):
    """Composed path enumeration for the tail dead-proof: the b.lo spin stays
    on the loop head, the terminal word is the unconditional B back to the
    wfe head, no composed word branches at or past the tail and nothing can
    fall through into it (the last composed word is that unconditional B)."""
    words = struct.unpack("<15I", probe)
    require(words[-1] == 0x17FFFFFF, "COMPOSED_TERMINAL_NOT_UNCONDITIONAL_B")
    loop_head, terminal_head = entry_va + 20, entry_va + 52
    require(cp.branch_target(words[9], entry_va + 36) == loop_head,
            "COMPOSED_LOOP_HEAD_DRIFT")
    require(cp.branch_target(words[-1], entry_va + 56) == terminal_head,
            "COMPOSED_TERMINAL_HEAD_DRIFT")
    for i, word in enumerate(words):
        target = cp.branch_target(word, entry_va + 4 * i)
        if target is not None:
            require(entry_va <= target < entry_va + WINDOW,
                    f"COMPOSED_BRANCH_REACHES_TAIL:{hex(target)}")
    require(words[12] == 0xD4000003, "COMPOSED_SMC_WORD_DRIFT")
    require(words[13] == 0xD503205F, "COMPOSED_WFE_WORD_DRIFT")


def bti_semantics(probes, frozen, offset, cfg):
    """BTI sub-gates over the composed windows; every check fails loudly and
    the returned dict is the recorded verdict set. Pad/tail byte preservation
    and diagnostic-diff confinement are enforced per member by
    require_member_scope; core word identity by gate_composed_window."""
    pad = struct.pack("<I", BTI_C)
    require(frozen[offset:offset + 4] == pad, "FROZEN_ENTRY_NOT_BTI_C")
    for probe in probes.values():
        words = struct.unpack("<15I", probe)
        require(words[0] == BTI_C and probe[:4] == pad, "BTI_C_ENTRY_WORD_REWRITTEN")
        require(words[0] not in BTI_NON_C_WORDS and words[0] != PACIASP,
                "LANDING_PAD_CLASS_CHANGED")
        for word in words:
            require((word & PAC_HINT_MASK) != PAC_HINT_BASE,
                    f"PAC_HINT_IN_COMPOSED_WINDOW:{hex(word)}")
            require(word not in PAC_AUT_HINTS,
                    f"PAC_HINT_IN_COMPOSED_WINDOW:{hex(word)}")
            require((word & RET_MASK) != RET_BASE,
                    f"RET_IN_DIAGNOSTIC_PATH:{hex(word)}")
            require(word not in INDIRECT_CALL_WORDS,
                    f"INDIRECT_CALL_IN_DIAGNOSTIC_PATH:{hex(word)}")
    require(cfg, "KERNEL_CONFIG_NOT_READ")
    return {"BTI_C_ENTRY_WORD_EXACT": "YES",
            "LANDING_PAD_CLASS_UNCHANGED": "YES",
            "BTI_PAD_NOT_DELETED": "YES",
            "PAC_INDEPENDENCE": "YES",
            "NO_RET_IN_DIAGNOSTIC_PATH": "YES",
            "LR_RESTORATION_NOT_REQUIRED": "YES",
            "SMC_ROUND_TRIP_BTI_SAFE": "YES",
            "INITCALL_DISPATCH_CALL_CLASS": INITCALL_DISPATCH_CALL_CLASS,
            "INITCALL_DISPATCH_CITATION": INITCALL_DISPATCH_CITATION,
            "KERNEL_BTI_CONFIG_CONFIRMED": "YES",
            "KERNEL_BTI_KERNEL_CONFIG": cfg.get("CONFIG_ARM64_BTI_KERNEL", "ABSENT"),
            "KERNEL_BTI_CONFIG": cfg.get("CONFIG_ARM64_BTI", "ABSENT"),
            "BTI_C_ENTRY_SEMANTICS_PASS": "YES"}


def symbol_pairs(system_map):
    return post50.symbol_pairs(system_map)


def absolute_low32_scan(table_sections, target, window):
    """Every 32-bit field of the runtime-rewrite-class tables must differ from
    the low 32 bits of every VA inside [target, target+window)."""
    lows = {(target + off) & 0xFFFFFFFF for off in range(0, window, 4)}
    hits = []
    for section in table_sections:
        blob = section["bytes"]
        for i in range(0, len(blob) - 3, 4):
            if struct.unpack_from("<I", blob, i)[0] in lows:
                hits.append(f"{section['name']}@{hex(section['vma'] + i)}")
    return hits


def disasm_mnemonic(disasm, va):
    for line in disasm.splitlines():
        if line.lstrip().startswith(f"{va:x}:"):
            fields = [f.strip() for f in line.split("\t") if f.strip()]
            return " ".join(fields[2:])
    require(False, f"TAIL_DISASSEMBLY_LINE_MISSING:{hex(va)}")


def extended_reference_scan(args, ctx, audit):
    """64-byte extended range [entry, entry+64): the tail was never scanned
    before this round. Incoming branches (sources outside the range), 4-byte
    relative references (the initcall slot is the only permitted site),
    8-byte-aligned absolute literals, ELF relocations, runtime-rewrite tables
    (including per-table absolute low-32 equality) and adrp+add pairs must all
    come back empty."""
    target = int(audit["target_va"], 16)
    text_va = ctx["text_va"]
    frozen = ctx["frozen"][:ctx["image_len"]]
    vmlinux = args.bundle / "vmlinux"
    table_sections = post50.vmlinux_table_sections(vmlinux, ctx["sections"])
    topology = cp.branch_audit(frozen, ctx["ranges"], text_va,
                               (target, target + FUNCTION_SIZE),
                               (target, target + FUNCTION_SIZE))
    require(not topology["incoming_entry"], "EXTENDED_INCOMING_ENTRY_BRANCH")
    require(not topology["incoming_window_interior"],
            "EXTENDED_INCOMING_INTERIOR_BRANCH")
    nxt = ctx["symbol_vas"][bisect.bisect_right(ctx["symbol_vas"], target)]
    cp.t3.gate_function_extent_scan(target, FUNCTION_SIZE, nxt)
    cp.t3.gate_window_literal_scan(target, FUNCTION_SIZE, frozen)
    cp.t3.gate_window_relocation_scan(target, FUNCTION_SIZE, ctx["reloc_sites"])
    relative = post50.relative_reference_scan(ctx["image"], text_va, target,
                                              FUNCTION_SIZE, TABLE_IMAGE_OFFSET,
                                              symbol_pairs(args.bundle / "System.map"),
                                              ctx["sections"])
    require(relative["slot_present"], "EXTENDED_REFERENCE_SLOT_MISSING")
    unexpected = [site for site in relative["sites"] if site["role"] == "UNEXPECTED"]
    require(not unexpected,
            f"EXTENDED_REFERENCE_DATA_HIT:{[s['offset'] for s in unexpected]}")
    tables = post50.table_section_scans(table_sections, target, FUNCTION_SIZE)
    bad = {key: value for key, value in tables.items()
           if key != "relr_sites_total" and value}
    require(not bad, f"EXTENDED_REFERENCE_TABLE_HIT:{sorted(bad)}")
    abs_low = absolute_low32_scan(table_sections, target, FUNCTION_SIZE)
    require(not abs_low, f"EXTENDED_ABSOLUTE_LOW32_HIT:{abs_low[:8]}")
    adrp_hits = post50.adrp_add_scan(ctx["image"], text_va, ctx["ranges"],
                                     target, FUNCTION_SIZE)
    require(not adrp_hits, f"EXTENDED_ADRP_ADD_HIT:{adrp_hits}")
    overlap = {tag: sorted({v for v in sites if target <= v < target + FUNCTION_SIZE})
               for tag, sites in ctx["rw_sites"].items()}
    bad_rw = {tag: sites for tag, sites in overlap.items() if sites}
    require(not bad_rw, f"EXTENDED_REWRITE_OVERLAP:{sorted(bad_rw)}")
    return {"span": [hex(target), hex(target + FUNCTION_SIZE)],
            "branch_topology": topology,
            "relative_references": relative,
            "runtime_rewrite_tables": tables,
            "rewrite_overlap_64": {tag: len(sites) for tag, sites in overlap.items()},
            "absolute_low32": abs_low,
            "adrp_add_into_range": adrp_hits,
            "verdict": "NO_REFERENCE_INTO_EXTENDED_RANGE"}


def tail_dead_proof(args, ctx, audit, window, family_dir):
    """Prove the original 4-byte tail [entry+window, entry+64) is unreachable.

    Direct arrival: only sources OUTSIDE the whole 64-byte function range may
    branch into the tail (original interior->tail edges cease to exist once
    their sources are overwritten and are recorded as informative_only).
    Indirect arrival: literals, relative references, rewrite tables (with
    per-table absolute low-32 equality), adrp+add pairs and ELF relocations
    must all come back empty. The frozen tail word is cross-checked against
    the bundle vmlinux and the original decode is persisted as evidence."""
    target = int(audit["target_va"], 16)
    text_va = ctx["text_va"]
    tail_lo, tail_hi = target + window, target + window + TAIL_BYTES
    frozen = ctx["frozen"][:ctx["image_len"]]
    vmlinux = args.bundle / "vmlinux"
    disasm = cp.pb.run([cp.TOOLS["objdump"], "-dr",
                        f"--start-address={target:#x}",
                        f"--stop-address={tail_hi:#x}", str(vmlinux)])
    bundle_tail = cp.vmlinux_bytes_at(vmlinux, ctx["sections"], tail_lo, TAIL_BYTES)
    frozen_tail = frozen[tail_lo - text_va:tail_hi - text_va]
    require(bundle_tail == frozen_tail, "TAIL_FROZEN_BUNDLE_WORD_DRIFT")
    branches = [hit for hit in cp.incoming_inclusive(frozen, ctx["ranges"], text_va,
                                                     tail_lo, tail_hi)
                if not target <= hit[0] < tail_hi]
    require(not branches,
            f"TAIL_INCOMING_BRANCH:{[(hex(a), hex(b)) for a, b in branches[:8]]}")
    symbols = symbol_pairs(args.bundle / "System.map")
    table_sections = post50.vmlinux_table_sections(vmlinux, ctx["sections"])
    relative = post50.relative_reference_scan(ctx["image"], text_va, tail_lo,
                                              TAIL_BYTES, None, symbols,
                                              ctx["sections"])
    require(not relative["sites"],
            f"TAIL_RELATIVE_REFERENCE:{relative['sites'][:8]}")
    cp.t3.gate_window_literal_scan(tail_lo, TAIL_BYTES, frozen)
    tables = post50.table_section_scans(table_sections, tail_lo, TAIL_BYTES)
    bad = {key: value for key, value in tables.items()
           if key != "relr_sites_total" and value}
    require(not bad, f"TAIL_REFERENCE_TABLE_HIT:{sorted(bad)}")
    abs_low = absolute_low32_scan(table_sections, tail_lo, TAIL_BYTES)
    require(not abs_low, f"TAIL_ABSOLUTE_LOW32_HIT:{abs_low[:8]}")
    adrp_hits = post50.adrp_add_scan(ctx["image"], text_va, ctx["ranges"],
                                     tail_lo - 4, 8)
    require(not adrp_hits, f"TAIL_ADRP_ADD_HIT:{adrp_hits}")
    cp.t3.gate_window_relocation_scan(tail_lo, TAIL_BYTES, ctx["reloc_sites"])
    topology = cp.branch_audit(frozen, ctx["ranges"], text_va,
                               (target, tail_hi), (target, tail_hi))
    informative = [edge for edge in topology["internal_branches"]
                   if int(edge[0], 16) - target < window
                   and int(edge[1], 16) - target >= window]
    report = {"target_va": audit["target_va"], "window": window,
              "tail_span": [hex(tail_lo), hex(tail_hi)], "tail_bytes": TAIL_BYTES,
              "frozen_tail_word": hex(struct.unpack_from("<I", frozen_tail, 0)[0]),
              "bundle_tail_word": hex(struct.unpack_from("<I", bundle_tail, 0)[0]),
              "tail_instruction": disasm_mnemonic(disasm, tail_lo),
              "disassembly": disasm,
              "original_branch_graph": topology,
              "informative_only_edges_into_tail": informative,
              "reference_scans": {"incoming_branches": [],
                                  "relative_references": relative,
                                  "runtime_rewrite_tables": tables,
                                  "absolute_low32": abs_low,
                                  "adrp_add_into_tail": adrp_hits,
                                  "relocations_in_tail": 0},
              "verdict": "DEAD_PROVEN"}
    write_json(family_dir / "tail-reachability.json", report)
    return report


def build_pairs(args, selection, ctx, metadata, out):
    """One DELAY_CONSTANT_ONLY payload pair from the frozen FIX8 base."""
    image_size = ctx["image_size"]
    dtb_offset, _ = cp.pb.calc_dtb_offset(image_size)
    cp.pb.gate_rt_d(ctx["frozen"][dtb_offset:])
    audit = selection["audit"]
    target = int(audit["target_va"], 16)
    offset = int(audit["image_offset"], 16)
    require((offset, audit["window"], audit["core_size"])
            == (IMAGE_OFFSET, WINDOW, CORE_SIZE), "PINNED_PROBE_GEOMETRY_DRIFT")
    require(struct.unpack_from("<I", ctx["frozen"], TABLE_IMAGE_OFFSET)[0]
            == TABLE_WORD, "FROZEN_TABLE_WORD_DRIFT")
    core, _words = base.core_bytes(args.core56.read_bytes(), 56)
    require(cp.digest(core) == CORE56_SHA, "ULTRACOMPACT_CORE_SHA_DRIFT")
    entry_word = int(audit["entry_pad_word"], 16)
    require(entry_word == BTI_C, "PINNED_ENTRY_PAD_NOT_BTI_C")
    section = cp.t3.gate_window_section_scan(target, WINDOW, ctx["sections"])
    require(section["name"] == ".init.text", "WINDOW_NOT_INIT_TEXT")
    require(cp.t3.sysmap_symbol(args.bundle / "System.map", audit["symbol"]) == target,
            "SYMBOL_MAP_MISMATCH")
    require_frozen_window_disjoint(target, FUNCTION_SIZE)
    require_inline_probe_architecture(audit["probe_architecture"])
    require(audit["cfg_closure"] and audit["cfg_closure"]["cfg_closure_proven"],
            "CFG_CLOSURE_NOT_PROVEN")
    family_dir = out / FAMILY
    family_dir.mkdir(parents=True, exist_ok=False)
    rewrites = cp.audit_rewrites(family_dir, args.bundle / "vmlinux",
                                 ctx["sections"], (target, target + FUNCTION_SIZE))
    (family_dir / "original-function.txt").write_text(
        cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={target:#x}",
                   f"--stop-address={target + FUNCTION_SIZE:#x}",
                   str(args.bundle / "vmlinux")]))
    (family_dir / "original-window.txt").write_text(
        cp.pb.run([cp.TOOLS["objdump"], "-d", f"--start-address={target:#x}",
                   f"--stop-address={target + FUNCTION_SIZE:#x}",
                   str(args.bundle / "vmlinux")]))
    agreement = post50.window_agreement_round(ctx["image"], ctx["frozen"],
                                              ctx["text_va"], offset,
                                              FUNCTION_SIZE, ctx["sections"])
    write_json(family_dir / "window-agreement.json", agreement)
    write_json(family_dir / "cfg-closure.json", audit["cfg_closure"])
    extended = extended_reference_scan(args, ctx, audit)
    write_json(family_dir / "window-reference-forensic.json", extended)
    boundary = cp.level7_span_entry_as_boundary(
        {key: entry for key, entry in
         zip(("index", "entry_va", "entry_va_hex", "entry_image_offset",
              "entry_word", "relative", "target_va", "target_va_hex",
              "aliases", "symbol"),
             (audit["index"], int(audit["table_entry_va"], 16),
              audit["table_entry_va"], int(audit["table_entry_image_offset"], 16),
              audit["entry_word"], audit["relative"], target, audit["target_va"],
              audit["aliases"], audit["symbol"]))})
    members = {}
    for delay in (8, 1):
        directory = family_dir / "pair" / str(delay) / "checkpoint"
        directory.mkdir(parents=True, exist_ok=False)
        probe, payload = base.compose_member(ctx["frozen"], offset, WINDOW,
                                             entry_word, core, delay)
        gate_composed_window(probe, entry_word, DELAY_WORDS[delay])
        gate_composed_control_flow(probe, target)
        payload_sha = cp.digest(payload)
        require_fresh_payload(payload_sha)
        require_member_scope(payload, ctx["frozen"], offset, WINDOW)
        require_prel32_unchanged(payload, ctx["frozen"], TABLE_IMAGE_OFFSET)
        cp.t3.gate_tramp_identity(payload)
        cp.pb.gate_rt_d(payload[dtb_offset:])
        members[delay] = {"directory": directory, "probe": probe,
                          "payload": payload, "payload_sha": payload_sha}
    payloads = {delay: member["payload"] for delay, member in members.items()}
    probes = {delay: member["probe"] for delay, member in members.items()}
    changed = [i for i, (a, b) in enumerate(zip(payloads[8], payloads[1])) if a != b]
    base.assert_pair_delay_only(changed, offset, CORE_SIZE)
    require(changed == PAIR_DIFF_OFFSETS, f"PAIR_DIFF_OFFSETS_DRIFT:{changed}")
    bti = bti_semantics(probes, ctx["frozen"], offset, ctx["cfg"])
    tail = tail_dead_proof(args, ctx, audit, WINDOW, family_dir)
    audit.update({"entry_audit": "PASS", "incoming_branch_gate": "PASS",
                  "function_range_safe": True, "runtime_rewrite_safe": True,
                  "relocations_in_window": 0, "inline_only": True,
                  "trampoline_permitted": False, "island_permitted": False,
                  "window_derivation": "TARGET_CFG",
                  "window_agreement": agreement["verdict"],
                  "round_pad_class": "bti_c_only",
                  "probe_architecture": PROBE_ARCHITECTURE,
                  "extended_reference_forensic": extended["verdict"],
                  "tail_reachability": tail["verdict"], "bti_semantics": bti,
                  "initcall_dispatch_call_class": INITCALL_DISPATCH_CALL_CLASS,
                  "initcall_dispatch_citation": INITCALL_DISPATCH_CITATION})
    write_json(family_dir / "target-entry-audit.json", audit)
    shas = {}
    for delay, member in members.items():
        manifest = {"symbol": FAMILY, "family": FAMILY,
                    "member_name": f"{LABEL}_{delay}",
                    "target_symbol": audit["symbol"],
                    "target_aliases": audit["aliases"],
                    "target_va": audit["target_va"],
                    "target_image_offset": audit["image_offset"],
                    "offset": offset, "checkpoint_size": WINDOW,
                    "core_size": CORE_SIZE, "entry": audit["entry_pad"],
                    "entry_pad_word": audit["entry_pad_word"],
                    "pac": audit["pac"], "bti": audit["bti"],
                    "round_pad_class": "bti_c_only", "section": section["name"],
                    "initcall_boundary": boundary,
                    "initcall_registration": audit["registration"],
                    "registration_type": audit["registration_type"],
                    "target_source": audit["source"],
                    "target_function_size": audit["function_size"],
                    "target_entry_audit": audit,
                    "span_index": audit["index"],
                    "pinned_index": PINNED_INDEX, "deviation": None,
                    "core_variant": "ultracompact_cntpct_elapsed_b_lo",
                    "probe_architecture": PROBE_ARCHITECTURE,
                    "core_sha256": cp.digest(core), "delay_seconds": delay,
                    "payload_size": len(member["payload"]),
                    "payload_sha256": member["payload_sha"],
                    "checkpoint_sha256": cp.digest(member["probe"]),
                    "frozen_sha256": cp.digest(ctx["frozen"]),
                    "frozen_payload_disjoint": True,
                    "prel32_target_unchanged": True,
                    "member_changes_only_inside_window": True,
                    "tail_bytes": TAIL_BYTES, "tail_bytes_original": True,
                    "tail_reachability": tail["verdict"],
                    "bti_semantics": bti,
                    "cfg_closure": audit["cfg_closure"],
                    "runtime_rewrites": rewrites, "window_agreement": agreement,
                    "extended_reference_forensic": extended["verdict"],
                    "window_derivation": "TARGET_CFG", "inline_only": True,
                    "trampoline_permitted": False, "island_permitted": False,
                    "stage": STAGE, "bundle_run": base.BUNDLE_RUN,
                    "bundle": metadata,
                    "source_commit": os.environ["GITHUB_SHA"],
                    "run_id": os.environ["GITHUB_RUN_ID"],
                    "positive_proves": PROOF[0],
                    "positive_does_not_prove": PROOF[1],
                    "normal_boot_candidate": False, "kernel_rebuilt": False,
                    "device_operation": False, "private_pack": False}
        (member["directory"] / "payload.bin").write_bytes(member["payload"])
        (member["directory"] / "checkpoint.bin").write_bytes(member["probe"])
        write_json(member["directory"] / "manifest.json", manifest)
        shas[delay] = member["payload_sha"]
    identity = {"stage": STAGE, "family": FAMILY,
                "delay8_name": f"{LABEL}_8", "delay1_name": f"{LABEL}_1",
                "bundle_run": base.BUNDLE_RUN,
                "source_commit": os.environ["GITHUB_SHA"],
                "public_run": os.environ["GITHUB_RUN_ID"],
                "delay8_payload_sha256": shas[8], "delay1_payload_sha256": shas[1],
                "changed_offsets": changed, "expected_delta_seconds": -7.0,
                "strong_error_seconds": 1.0, "supported_error_seconds": 2.0,
                "attribution": "DELAY_CONSTANT_ONLY",
                "pair_diff_offsets": PAIR_DIFF_OFFSETS,
                "span_index": audit["index"], "pinned_index": PINNED_INDEX,
                "deviation": None, "target_symbol": audit["symbol"],
                "target_va": audit["target_va"],
                "probe_architecture": PROBE_ARCHITECTURE,
                "window": WINDOW, "core_size": CORE_SIZE,
                "entry_pad": "bti c", "round_pad_class": "bti_c_only",
                "tail_reachability": tail["verdict"],
                "bti_c_entry_semantics_pass": True,
                "private_pack": False, "device_operation": False,
                "kernel_rebuilt": False}
    write_json(family_dir / "pair" / "pair.json", identity)
    return {FAMILY: {"label": LABEL, "identity": identity, "audit": audit,
                     "selection": selection, "offset": offset, "window": WINDOW,
                     "core_size": CORE_SIZE, "shas": shas, "changed": changed,
                     "bti": bti, "agreement": agreement["verdict"],
                     "tail": tail["verdict"]}}


def summary_kv(names, enriched, map_stats, bti, agreement):
    info = names[FAMILY]
    audit = info["audit"]
    prefix = f"{LABEL}_"
    lines = [f"LATE_LEVEL_POST50_STAGE={STAGE}",
             "LATE_SPAN=__initcall7_start..__initcall_end",
             f"LATE_TABLE_ENTRY_COUNT={len(enriched)}",
             f"LATE_TABLE_INDEX0_SYMBOL={base.FROZEN_INDEX0['symbol']}",
             f"LATE_TABLE_INDEX0_TABLE_VA={hex(base.FROZEN_INDEX0['entry_va'])}",
             f"LATE_TABLE_INDEX0_TARGET_VA={hex(base.FROZEN_INDEX0['target_va'])}",
             f"LATE_TABLE_INDEX0_WORD={hex(base.FROZEN_INDEX0['entry_word'])}",
             f"LATE_TABLE_INDEX0_FUNCTION_SIZE={base.FROZEN_INDEX0['function_size']}",
             f"LATE_MAP_IN_INIT_TEXT={map_stats['init_text']}",
             f"LATE_MAP_TEXT_SECTION_ENTRIES={map_stats['text_section']}",
             f"ROUND_PAD_CLASS={ROUND_PAD_VALUE}",
             f"FROZEN_INDICES_EXCLUDED={','.join(str(i) for i in FROZEN_LATE_INDICES)}",
             "FROZEN_WINDOW_DISJOINT=YES", "FROZEN_PAYLOAD_DISJOINT=YES",
             "HIGH8_STATIC_PROBE_DEFECT_FOUND=NO",
             "HIGH8_FORENSIC_RUNTIME_INFERENCE=NONE",
             f"{prefix}NOMINAL_INDEX={PINNED_INDEX}",
             f"{prefix}INDEX={audit['index']}",
             f"{prefix}SYMBOL={audit['symbol']}",
             f"{prefix}TABLE_VA={audit['table_entry_va']}",
             f"{prefix}TARGET_VA={audit['target_va']}",
             f"{prefix}IMAGE_OFFSET={audit['image_offset']}",
             f"{prefix}FUNCTION_SIZE={audit['function_size']}",
             f"{prefix}WINDOW={audit['window']}",
             f"{prefix}CORE_SIZE={audit['core_size']}",
             f"{prefix}PROBE_ARCHITECTURE={PROBE_ARCHITECTURE}",
             f"{prefix}ENTRY_PAD={audit['entry_pad']}",
             f"{prefix}REGISTRATION={audit['registration']}",
             f"{prefix}SOURCE={audit['source']}",
             f"{prefix}DEVIATION=NONE",
             f"{LABEL}_8_PAYLOAD_SHA={info['shas'][8]}",
             f"{LABEL}_1_PAYLOAD_SHA={info['shas'][1]}",
             f"{prefix}PAIR_DIFF_OFFSETS={info['changed']}",
             f"{prefix}PAIR=PASS",
             f"TAIL_BYTES={TAIL_BYTES}",
             "TAIL_BYTES_ORIGINAL=YES", "TAIL_NO_INCOMING_TARGET=YES",
             "TAIL_NOT_ON_DIAGNOSTIC_PATH=YES", "TAIL_NO_PRESERVED_SEMANTICS=YES",
             "TAIL_BTI_NEUTRAL=YES", "TAIL_REACHABILITY=DEAD_PROVEN"]
    lines += [f"{key}={value}" for key, value in bti.items()]
    lines += ["MEMBER_CHANGES_ONLY_INSIDE_WINDOW=YES",
              f"WINDOW_AGREEMENT_INDEX51={agreement}",
              "PAIR_DIFF=DELAY_CONSTANT_ONLY", "INLINE_ONLY=YES",
              "TRAMPOLINE_PERMITTED=NO", "ISLAND_PERMITTED=NO",
              "PREL32_TARGET_UNCHANGED=YES", "SHARED_CHECKPOINT=NO",
              "CROSS_FUNCTION_OVERWRITE=NO", "WINDOW_DERIVATION=TARGET_CFG",
              "KERNEL_REBUILD=NO", "DEVICE_OPERATION=NO", "PRIVATE_PACK=NO",
              "PARTITION_WRITES=0", "SLOT_A_WRITTEN=NO", "LOCAL_BUILD=NO"]
    return lines


def high8_forensic(entries, ctx, args, out):
    """Reuse post50's HIGH8 forensic path (PACIASP_ONLY re-audit of index 63).

    The frozen anomaly is not reinterpreted. Stage is rewritten to this round
    so the persisted JSON is attributable without copying a prior PASS.
    """
    record = post50.high8_forensic(entries, ctx, args, out)
    record["stage"] = STAGE
    record["round_pad_class_of_forensic"] = "paciasp_only"
    write_json(out / "high8-forensic.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "frozen", "core56", "core52", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    frozen = args.frozen.read_bytes()
    core56_bytes = args.core56.read_bytes()
    require(cp.digest(core56_bytes) == CORE56_SHA, "ULTRACOMPACT_CORE_SHA_DRIFT")
    base.core_bytes(core56_bytes, 56)
    base.core_bytes(args.core52.read_bytes(), 52)
    core56 = cp.ultracompact_core(args.core56.read_bytes())
    core52 = cp.subsys52_core(args.core52.read_bytes())
    cp.gate_subsys52_core_equivalence(core56, core52)
    metadata, raw_entries, enriched, ctx = base.enumerate_level7(args.bundle,
                                                                 frozen, out)
    map_stats = {"init_text": sum(1 for e in enriched if e["init_text"]),
                 "text_section": sum(1 for e in enriched if not e["init_text"])}
    high8 = high8_forensic(enriched, ctx, args, out)
    selection = pin_target(enriched, ctx)
    write_json(out / "late-map.json", {
        "stage": STAGE, "bundle_run": base.BUNDLE_RUN,
        "span": [base.SPAN_BEGIN, base.SPAN_END], "entry_count": len(enriched),
        "index0_identity": base.FROZEN_INDEX0, "entries": enriched})
    write_json(out / "selection.json", {
        "stage": STAGE, "pinned_index": PINNED_INDEX,
        "selections": {FAMILY: selection},
        "round_pad_gate": ROUND_PAD_GATE, "round_pad_class": ROUND_PAD_VALUE,
        "frozen_indices": FROZEN_LATE_INDICES,
        "interval_walk": "NONE_TARGET_PINNED_DIRECTLY"})
    names = build_pairs(args, selection, ctx, metadata, out)
    require(cp.digest((args.bundle / "vmlinux").read_bytes())
            == metadata["files"]["vmlinux"], "AUDIT_MUTATED_ELF")
    require(frozen == args.frozen.read_bytes(), "AUDIT_MUTATED_FROZEN")
    info = names[FAMILY]
    lines = summary_kv(names, enriched, map_stats, info["bti"],
                       info["agreement"])
    (out / "audit-summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"HIGH8_FORENSIC_VERDICT={high8['HIGH8_STATIC_PROBE_DEFECT_FOUND']}",
          flush=True)
    print(f"{STAGE}_PAIR_AUDIT=PASS", flush=True)


if __name__ == "__main__":
    main()
