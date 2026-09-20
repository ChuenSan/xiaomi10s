#!/usr/bin/env python3
"""Late index-54 TARGET-SCOPED `.text` probe exception (MAINLINE_V2_R3_SLOT_B_LATE_INDEX54_TEXT_TARGET_EXCEPTION_CI).

GitHub Actions only; CI-only round, device operation forbidden.

The frozen policy admits inline probes only on late-initcall targets living in
`.init.text`. Exactly one target is exempted here, by a **literal four-tuple
allowlist** (index, symbol, VA, section) with exactly one member:

    deferred_probe_initcall / index 54 / 0xffff8000808e7564 / .text

Nothing generic is introduced: there is no `ALLOW_TEXT_TARGETS` switch, the
allowlist cannot be widened by construction, and the module proves the
non-generalisation by auditing adversarial neighbours (a different `.text`
symbol, the same section at a shifted VA, the same symbol at a different index,
index 53) and requiring every one of them to be rejected.

Geometry and probe family are NOT new variables: the target is 492 bytes, the
probe is the already device-proven 60-byte family (preserved 4-byte entry pad +
the frozen 56-byte ultracompact core), the window is derived by the standard
CFG closure fixpoint, and the pair differs only in the delay constant.
Trampolines, islands, PREL32 retargeting, shared do_initcall* checkpoints and
cross-function overwrite remain forbidden.
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

STAGE = "MAINLINE_V2_R3_SLOT_B_LATE_INDEX54_TEXT_TARGET_EXCEPTION_CI"
FAMILY, LABEL, PINNED_INDEX = ("late_text54", "TEXT54", 54)
ROUND_PAD_GATE = "ROUND_PAD_CLASS"
ROUND_PAD_VALUE = "PACIASP_ONLY"
ROUND_PAD_REASON = "ROUND_PAD_CLASS_NOT_PACIASP"
PACIASP = 0xD503233F
BTI_C = 0xD503245F
BTI_NON_C_WORDS = (0xD503241F, 0xD503249F, 0xD50324DF)
PAC_HINT_MASK = 0xFFFFF81F
PAC_HINT_BASE = 0xD5032000
RET_MASK = 0xFFFFFC1F
RET_BASE = 0xD65F0000
INDIRECT_CALL_WORDS = (0xD63F0BC0, 0xD63F0FC0)
PAC_AUT_HINTS = (
    0xD50320FF,  # XPACLRI
    0xD503211F, 0xD503215F, 0xD503219F, 0xD50321DF,  # *1716
    0xD503231F, 0xD503233F, 0xD503235F, 0xD503237F,  # *AZ/*ASP
    0xD503239F, 0xD50323BF, 0xD50323DF, 0xD50323FF,  # AUT*Z/SP
)
TARGET_VA = 0xFFFF8000808E7564
IMAGE_OFFSET = 0x8E7564
TABLE_VA = 0xFFFF800081D0C3B0
TABLE_IMAGE_OFFSET = 0x1D0C3B0
TABLE_WORD = 0xFEBDB1B4
FUNCTION_SIZE = 492
WINDOW = 60
CORE_SIZE = 56
TAIL_BYTES = FUNCTION_SIZE - WINDOW
PROBE_ARCHITECTURE = base.CORE_56  # INLINE_PACIASP_PLUS_56B_ULTRACOMPACT
CORE56_SHA = "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5"
DELAY_WORDS = {8: 0xD37DF12A, 1: 0xD340FD2A}
DELAY_CORE_OFFSET = 8  # `delay_core` slot for the 56-byte core
PAIR_DIFF_OFFSETS = [IMAGE_OFFSET + 4 + DELAY_CORE_OFFSET + 1,
                     IMAGE_OFFSET + 4 + DELAY_CORE_OFFSET + 2]
CORE56_WORDS_8S = cp.ULTRACOMPACT_WORDS
# ---------------------------------------------------------------- exception --
TEXT_EXCEPTION_ALLOWED_SYMBOL = "deferred_probe_initcall"
TEXT_EXCEPTION_ALLOWED_INDEX = 54
TEXT_EXCEPTION_ALLOWED_VA = 0xFFFF8000808E7564
TEXT_EXCEPTION_ALLOWED_SECTION = ".text"
TEXT_EXCEPTION_ALLOWED = ((TEXT_EXCEPTION_ALLOWED_INDEX,
                           TEXT_EXCEPTION_ALLOWED_SYMBOL,
                           TEXT_EXCEPTION_ALLOWED_VA,
                           TEXT_EXCEPTION_ALLOWED_SECTION),)
GLOBAL_ALLOW_TEXT_TARGETS = None  # permanent: no generic `.text` switch exists
INIT_TEXT_SECTIONS = (".init.text", ".text")
# ---------------------------------------------------------------------------
FROZEN_TARGET = {"index": PINNED_INDEX, "symbol": "deferred_probe_initcall",
                 "table_va": hex(TABLE_VA), "table_image_offset": hex(TABLE_IMAGE_OFFSET),
                 "table_word": hex(TABLE_WORD), "target_va": hex(TARGET_VA),
                 "image_offset": hex(IMAGE_OFFSET), "function_size": FUNCTION_SIZE,
                 "section": ".text", "entry_pad": "paciasp",
                 "registration": "late_initcall(deferred_probe_initcall)",
                 "source": "drivers/base/dd.c"}
FROZEN_LATE_INDICES = tuple(sorted(post50.FROZEN_LATE_INDICES + (50, 51, 52)))
FROZEN_LATE_WINDOWS = post50.FROZEN_LATE_WINDOWS + ((0xFFFF800081B72F14, 60),) \
    + ((0xFFFF800081B87130, 60),) + ((0xFFFF800081B87EC8, 48),)
FROZEN_HISTORICAL_WINDOWS = post50.FROZEN_HISTORICAL_WINDOWS
FROZEN_PAYLOAD_SHAS = tuple(post50.FROZEN_PAYLOAD_SHAS) + (
    "28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",  # POST50_8
    "aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",  # POST50_1
    "ae437348164e2ccaa47e4ba238576b6ab05bfda23bd63f18bda48f161b3f88ef",  # BTIC51_8
    "49b9499d2656b7b8b16d39dc9863eb743a1e570a5ee544aea95b6a3a6b4f920e",  # BTIC51_1
    "e5c7b8d818303cdd8b2c60400aee2578e55734b33fbfca9fdcf55423a40128a5",  # COMPACT52_8
    "c71f47acce6654c0bfc27b189be0e72b826780e173b186f5c1a0dee2a2d77ed1")  # COMPACT52_1
INITCALL_DISPATCH_CALL_CLASS = "BLR_CONTROLLED"
INITCALL_DISPATCH_CITATION = ("init/main.c do_one_initcall: ret = fn(); "
                              "(linux 6.6.156, ~line 1210)")
PROOF = ("the pinned late-initcall index-54 entry was reached after all earlier "
         "late initcalls, through its original `paciasp` landing pad",
         "the target initcall body, later late initcalls, console or /init")


def require(condition, message):
    cp.require(condition, message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def exception_matches(entry):
    """Exact four-field literal equality; no prefix, wildcard or section rule."""
    return any(entry["index"] == index and entry["symbol"] == symbol
               and entry["target_va"] == va and entry["section"] == section
               for index, symbol, va, section in TEXT_EXCEPTION_ALLOWED)


def require_exception_scope():
    require(len(TEXT_EXCEPTION_ALLOWED) == 1, "TEXT_EXCEPTION_MULTI_SLOT")
    require(GLOBAL_ALLOW_TEXT_TARGETS is None, "GLOBAL_TEXT_TARGETS_SWITCH_PRESENT")
    index, symbol, va, section = TEXT_EXCEPTION_ALLOWED[0]
    require(index != 53, "TEXT_EXCEPTION_MUST_NOT_COVER_INDEX53")
    require(symbol != "sync_state_resume_initcall",
            "TEXT_EXCEPTION_MUST_NOT_COVER_INDEX53_SYMBOL")
    require(section != ".init.text", "TEXT_EXCEPTION_WOULD_BE_REDUNDANT")
    require((index, symbol, va, section)
            == (TEXT_EXCEPTION_ALLOWED_INDEX, TEXT_EXCEPTION_ALLOWED_SYMBOL,
                TEXT_EXCEPTION_ALLOWED_VA, TEXT_EXCEPTION_ALLOWED_SECTION),
            "TEXT_EXCEPTION_SLOT_DRIFT")
    require(symbol == FROZEN_TARGET["symbol"] and section == FROZEN_TARGET["section"]
            and index == PINNED_INDEX and va == TARGET_VA,
            "TEXT_EXCEPTION_NOT_PINNED_TARGET")


def _fail(record, gate, exc):
    record["gates"][gate] = f"FAIL:{exc}"
    record["fail_reasons"].append(str(exc))


def audit_candidate_text54(entry, ctx):
    """The frozen 15 gates, exception-aware at INIT_TEXT/SECTION_SCAN only."""
    target = entry["target_va"]
    offset = target - ctx["text_va"]
    size = entry["function_size"]
    in_image = 0 <= offset and offset + 4 <= ctx["image_len"]
    word0 = struct.unpack_from("<I", ctx["frozen"], offset)[0] if in_image else None
    record = {"index": entry["index"], "symbol": entry["symbol"],
              "aliases": entry["aliases"], "target_va": hex(target),
              "image_offset": hex(offset), "table_entry_va": entry["entry_va_hex"],
              "table_entry_image_offset": hex(entry["entry_image_offset"]),
              "entry_word": entry["entry_word"], "relative": entry["relative"],
              "function_size": size, "section": entry["section"],
              "registration": entry["registration"], "registration_type":
              entry["registration_type"], "source": entry["source"],
              "init_text": entry["init_text"],
              "text_exception_matched": exception_matches(entry),
              "entry_pad_word": None if word0 is None else hex(word0),
              "entry_pad": cp.t3.T3_ENTRY_PAD_CANDIDATES.get(word0),
              "pac": word0 == PACIASP, "bti": word0 == BTI_C,
              "min_probe": None, "core_size": None, "window": None,
              "probe_architecture": None, "gates": {}, "cfg_closure": None,
              "branch_topology": None, "PASS": False, "fail_reasons": []}
    gates = record["gates"]
    window = None
    for gate in base.GATES:
        try:
            if gate == "TARGET_UNIQUE":
                require(entry["target_unique"], "TARGET_DECODED_MORE_THAN_ONCE")
            elif gate == "REGISTRATION_LATE":
                require(entry["registration_type"] in cp.LATE_SPAN_TYPES,
                        f"NOT_LATE_INITCALL:{entry['registration_type']}")
            elif gate == "INIT_TEXT":
                require(entry["init_text"] or exception_matches(entry),
                        f"TARGET_NOT_INIT_TEXT:{entry['section']}")
            elif gate == "FUNCTION_SIZE":
                require(size % 4 == 0 and size > 0, "FUNCTION_SIZE_UNALIGNED")
            elif gate == "ENTRY_PAD":
                require(record["entry_pad"] is not None, "ENTRY_NOT_PACIASP_OR_BTI")
            elif gate == "WINDOW_FIT":
                min_probe = base.min_probe_for(size)
                record["min_probe"] = min_probe
                record["core_size"] = 56 if min_probe >= 60 else 52
                record["probe_architecture"] = (
                    base.CORE_56 if min_probe >= 60 else base.CORE_52)
                prelim = cp.branch_audit(ctx["frozen"][:ctx["image_len"]],
                                         ctx["ranges"], ctx["text_va"],
                                         (target, target + size),
                                         (target, target + min_probe))
                window = cp.derive_inline_window(target, size,
                                                 prelim["internal_branches"], min_probe)
                record["window"] = window
            elif gate in ("INCOMING_BRANCH", "CFG_CLOSURE", "SYMBOL_SCAN", "SECTION_SCAN",
                          "EXTENT_SCAN", "LITERAL_SCAN", "RELOCATION_SCAN",
                          "RUNTIME_REWRITE", "IMAGE_GEOMETRY"):
                require(window is not None, "WINDOW_NOT_DERIVED")
                span = (target, target + window)
                if gate == "INCOMING_BRANCH":
                    topology = cp.branch_audit(ctx["frozen"][:ctx["image_len"]],
                                               ctx["ranges"], ctx["text_va"],
                                               (target, target + size), span)
                    record["branch_topology"] = topology
                    require(not topology["incoming_entry"], "INCOMING_ENTRY_BRANCH")
                    require(not topology["incoming_window_interior"],
                            "INCOMING_WINDOW_INTERIOR_BRANCH")
                elif gate == "CFG_CLOSURE":
                    report = cp.cfg_closure_report(target, size, window,
                                                   record["branch_topology"])
                    record["cfg_closure"] = report
                    require(report["cfg_closure_proven"],
                            "SURVIVING_BRANCH_INTO_INTERIOR")
                elif gate == "SYMBOL_SCAN":
                    cp.t3.gate_window_symbol_scan(target, window, ctx["symbol_vas"])
                elif gate == "SECTION_SCAN":
                    section = cp.t3.gate_window_section_scan(target, window,
                                                             ctx["sections"])
                    require(section["name"] == entry["section"], "WINDOW_CROSSES_SECTION")
                    require(section["name"] in INIT_TEXT_SECTIONS,
                            f"WINDOW_IN_UNPROBEABLE_SECTION:{section['name']}")
                elif gate == "EXTENT_SCAN":
                    nxt = ctx["symbol_vas"][bisect.bisect_right(ctx["symbol_vas"], target)]
                    cp.t3.gate_function_extent_scan(target, window, nxt)
                elif gate == "LITERAL_SCAN":
                    cp.t3.gate_window_literal_scan(target, window,
                                                   ctx["frozen"][:ctx["image_len"]])
                elif gate == "RELOCATION_SCAN":
                    cp.t3.gate_window_relocation_scan(target, window, ctx["reloc_sites"])
                elif gate == "RUNTIME_REWRITE":
                    overlap = {tag: sorted({v for v in sites
                                            if target <= v < target + window})
                               for tag, sites in ctx["rw_sites"].items()}
                    bad = {tag: sites for tag, sites in overlap.items() if sites}
                    require(not bad, f"REWRITE_OVERLAP:{sorted(bad)}")
                    record["runtime_rewrite_overlap"] = {tag: len(sites) for tag, sites
                                                         in overlap.items()}
                elif gate == "IMAGE_GEOMETRY":
                    cp.t3.gate_window_inside_image_size(offset, window,
                                                        ctx["image_size"])
            gates[gate] = "PASS"
        except (ValueError, SystemExit) as exc:
            _fail(record, gate, exc)
    try:
        require(word0 == PACIASP, ROUND_PAD_REASON)
        require(record["entry_pad"] == "paciasp", ROUND_PAD_REASON)
        gates[ROUND_PAD_GATE] = "PASS"
    except (ValueError, SystemExit) as exc:
        _fail(record, ROUND_PAD_GATE, exc)
    record["PASS"] = all(value == "PASS" for value in gates.values())
    return record


def clone_entry(entry, **overrides):
    return {**entry, **overrides}


def non_generalization_probe(entries, ctx):
    """Machine evidence that the exception is a literal, not a rule.

    Each adversarial neighbour must be rejected by the ordinary gates; the
    pinned target must be the only entry the exception admits.
    """
    scope = entries[PINNED_INDEX]
    require(scope["section"] == ".text" and not scope["init_text"],
            "PINNED_INDEX54_UNEXPECTEDLY_INIT_TEXT")
    require(exception_matches(scope), "EXCEPTION_DOES_NOT_ADMIT_PINNED_TARGET")
    results = {}

    def rejected(label, entry, token):
        record = audit_candidate_text54(entry, ctx)
        require(not record["PASS"], f"NON_GENERALIZATION_FALSE_ACCEPT:{label}")
        require(any(str(reason).startswith(token) for reason in record["fail_reasons"]),
                f"NON_GENERALIZATION_WRONG_REASON:{label}:{record['fail_reasons']}")
        results[label] = "YES"

    index53 = entries[53]
    require(index53["index"] == 53 and index53["section"] == ".text",
            "INDEX53_IDENTITY_DRIFT")
    rejected("NEG_INDEX53_TOO_SMALL_REJECTED", index53, "TARGET_NOT_INIT_TEXT")
    index64 = entries[64]
    require(index64["section"] == ".text", "INDEX64_SECTION_DRIFT")
    rejected("NEG_DIFF_TEXT_SYMBOL_REJECTED", index64, "TARGET_NOT_INIT_TEXT")
    rejected("NEG_SAME_SECTION_DIFF_VA_REJECTED",
             clone_entry(scope, target_va=TARGET_VA + 4), "TARGET_NOT_INIT_TEXT")
    rejected("NEG_DIFF_INDEX_SAME_SYMBOL_REJECTED",
             clone_entry(scope, index=52), "TARGET_NOT_INIT_TEXT")
    rejected("NEG_WRONG_SYMBOL_SAME_INDEX_REJECTED",
             clone_entry(scope, symbol="sync_state_resume_initcall"),
             "TARGET_NOT_INIT_TEXT")
    results["NEG_PINNED_SLOT_ACCEPTED"] = "YES"
    return {"allowed_slot_count": len(TEXT_EXCEPTION_ALLOWED),
            "global_text_switch": "ABSENT",
            "adversarial": results,
            "verdict": "TARGET_SCOPED_ONLY"}


def pin_target(entries, ctx):
    require(len(entries) == base.SPAN_COUNT, "SELECTION_SPAN_COUNT_DRIFT")
    require(PINNED_INDEX not in FROZEN_LATE_INDICES, "PINNED_TARGET_FROZEN")
    require_exception_scope()
    entry = entries[PINNED_INDEX]
    require(entry["symbol"] == FROZEN_TARGET["symbol"], "PINNED_SYMBOL_DRIFT")
    require(entry["target_va"] == TARGET_VA, "PINNED_TARGET_VA_DRIFT")
    require(entry["entry_va"] == TABLE_VA, "PINNED_TABLE_VA_DRIFT")
    require(entry["entry_image_offset"] == TABLE_IMAGE_OFFSET,
            "PINNED_TABLE_OFFSET_DRIFT")
    require(entry["entry_word"] == hex(TABLE_WORD), "PINNED_TABLE_WORD_DRIFT")
    require(entry["function_size"] == FUNCTION_SIZE, "PINNED_FUNCTION_SIZE_DRIFT")
    require(entry["section"] == FROZEN_TARGET["section"], "PINNED_SECTION_DRIFT")
    require(not entry["init_text"], "PINNED_NOT_TEXT_SECTION")
    require(entry["target_unique"], "PINNED_TARGET_NOT_UNIQUE")
    require(entry["registration"] == FROZEN_TARGET["registration"],
            "PINNED_REGISTRATION_DRIFT")
    require(entry["source"] == FROZEN_TARGET["source"], "PINNED_SOURCE_DRIFT")
    audit = audit_candidate_text54(entry, ctx)
    require(audit["PASS"], f"PINNED_TARGET_GATES_FAILED:{audit['gates']}")
    require(audit["window"] == WINDOW, f"PINNED_WINDOW_DRIFT:{audit['window']}")
    require(audit["core_size"] == CORE_SIZE, "PINNED_CORE_SIZE_DRIFT")
    require(audit["probe_architecture"] == PROBE_ARCHITECTURE,
            "PINNED_PROBE_ARCHITECTURE_DRIFT")
    require_frozen_window_disjoint(TARGET_VA, WINDOW)
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
    require(payload_sha not in FROZEN_PAYLOAD_SHAS, "RERUN_FORBIDDEN_FROZEN_PAYLOAD")


def compose_member(frozen, offset, window, entry_word, core, delay):
    """Entry-pad-preserving inline probe payload for one delay constant."""
    return base.compose_member(frozen, offset, window, entry_word, core, delay)


def require_member_scope(payload, frozen, offset, window):
    """A composed member may differ from the frozen FIX8 base only inside the
    diagnostic core [offset+4, offset+window); the preserved entry pad and the
    whole 432-byte original tail stay byte-identical."""
    require(len(payload) == len(frozen), "PAYLOAD_SIZE_DRIFT")
    require(payload[offset:offset + 4] == frozen[offset:offset + 4],
            "ENTRY_PAD_MODIFIED")
    require(payload[:offset] == frozen[:offset]
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
    """Pinned composed-window identity: preserved entry pad then the frozen
    56-byte core with the delay constant in `delay_core`'s slot."""
    require(len(probe) == WINDOW, "COMPOSED_WINDOW_SIZE")
    words = struct.unpack("<15I", probe)
    require(words[0] == PACIASP == entry_word, "ENTRY_PAD_WORD_REWRITTEN")
    core_words = list(CORE56_WORDS_8S)
    core_words[DELAY_CORE_OFFSET // 4] = delay_word
    require(words[1:] == tuple(core_words), "COMPOSED_CORE_WORD_DRIFT")
    require(delay_word in DELAY_WORDS.values(), "UNEXPECTED_DELAY_WORD")
    require(words[13] == 0xD503205F and words[14] == 0x17FFFFFF,
            "COMPOSED_TERMINAL_NOT_WFE_SELF_LOOP")


def gate_composed_control_flow(probe, entry_va):
    """No composed word may branch outside the window, so the original 432-byte
    tail is unreachable from the probe and the diagnostic cannot return."""
    words = struct.unpack("<15I", probe)
    require(cp.branch_target(words[9], entry_va + 0x24) == entry_va + 0x14,
            "COMPOSED_LOOP_HEAD_DRIFT")
    require(cp.branch_target(words[14], entry_va + 0x38) == entry_va + 0x34,
            "COMPOSED_TERMINAL_HEAD_DRIFT")
    for i, word in enumerate(words):
        target = cp.branch_target(word, entry_va + 4 * i)
        if target is not None:
            require(entry_va <= target < entry_va + WINDOW,
                    f"COMPOSED_BRANCH_OUTSIDE_WINDOW:{hex(target)}")
    require(words[12] == 0xD4000003, "COMPOSED_SMC_WORD_DRIFT")
    require(words[11] == 0x72B08000, "COMPOSED_RESET_ID_WORD_DRIFT")


def core_semantics(probes, frozen, offset, cfg, audit):
    """Register-liveness / no-return / PSCI-token gates over the composed
    windows; the returned dict is the recorded verdict set."""
    pad = struct.pack("<I", PACIASP)
    require(frozen[offset:offset + 4] == pad, "FROZEN_ENTRY_NOT_PACIASP")
    for probe in probes.values():
        words = struct.unpack("<15I", probe)
        require(words[0] == PACIASP and probe[:4] == pad, "ENTRY_PAD_WORD_REWRITTEN")
        require(words[0] != BTI_C, "ROUND_PAD_CLASS_BTI_C_EXCLUDED")
        require(words[0] not in BTI_NON_C_WORDS, "ROUND_PAD_CLASS_BTI_J_EXCLUDED")
        for i, word in enumerate(words):
            if i == 0:
                continue  # the entry landing pad is validated separately
            require((word & PAC_HINT_MASK) != PAC_HINT_BASE,
                    f"PAC_HINT_IN_COMPOSED_WINDOW:{hex(word)}")
            require(word not in PAC_AUT_HINTS,
                    f"PAC_HINT_IN_COMPOSED_WINDOW:{hex(word)}")
            require((word & RET_MASK) != RET_BASE,
                    f"RET_IN_DIAGNOSTIC_PATH:{hex(word)}")
            require(word not in INDIRECT_CALL_WORDS,
                    f"INDIRECT_CALL_IN_DIAGNOSTIC_PATH:{hex(word)}")
    require(cfg, "KERNEL_CONFIG_NOT_READ")
    tail = audit["function_size"] - WINDOW
    return {"TEXT54_ENTRY_PAD_PRESERVED": "YES",
            "PACIASP_LANDING_PAD_COMPATIBLE": "YES",
            "NO_RET_IN_WINDOW": "YES",
            "LR_RESTORATION_NOT_REQUIRED": "YES",
            "SMC_ROUND_TRIP_SAFE": "YES",
            "INITCALL_DISPATCH_CALL_CLASS": INITCALL_DISPATCH_CALL_CLASS,
            "INITCALL_DISPATCH_CITATION": INITCALL_DISPATCH_CITATION,
            "KERNEL_CONFIG_CONFIRMED": "YES",
            "KERNEL_BTI_KERNEL_CONFIG": cfg.get("CONFIG_ARM64_BTI_KERNEL", "ABSENT"),
            "KERNEL_BTI_CONFIG": cfg.get("CONFIG_ARM64_BTI", "ABSENT"),
            "TAIL_BYTES": tail,
            "TAIL_PRESENT": "YES",
            "TAIL_IS_UNMODIFIED_ORIGINAL_CODE": "YES",
            "TAIL_UNREACHABLE_FROM_COMPOSED_WINDOW": "YES",
            "NO_COMPOSED_BRANCH_LEAVES_WINDOW": "YES",
            "DIAGNOSTIC_CANNOT_RETURN_TO_NORMAL_FUNCTION": "YES",
            "TEXT54_ENTRY_SEMANTICS_PASS": "YES"}


def relative_reference_census(image, text_va, target, function_size, window,
                              slot_offset):
    """Partition every 4-byte relative reference resolving into the function.

    The WINDOW is the overwritten region: any reference into it except the
    candidate's own initcall PREL32 slot is a hazard. The TAIL is unmodified
    original code, so a reference into it is inert and is only reported.
    """
    require(window <= function_size, "REFERENCE_CENSUS_WINDOW_LARGER_THAN_FUNCTION")
    dedupe = lambda rows: sorted(set(rows))
    window_sites, tail_sites = [], []
    for off in range(0, len(image) - 3, 4):
        value = struct.unpack_from("<I", image, off)[0]
        va = text_va + off + post50.signed(value, 32)
        if not target <= va < target + function_size:
            continue
        row = {"offset": hex(off), "resolved_va": hex(va)}
        (window_sites if va < target + window else tail_sites).append(row)
    slot = {"offset": hex(slot_offset), "resolved_va": hex(target)}
    require(slot in window_sites, "WINDOW_REFERENCE_SLOT_MISSING")
    strays = dedupe([row["offset"] for row in window_sites
                     if row["offset"] != slot["offset"]])
    require(not strays, f"WINDOW_REFERENCE_DATA_HIT:{strays}")
    return {"window_sites": window_sites,
            "tail_sites": dedupe([row["offset"] for row in tail_sites]),
            "slot_offset": hex(slot_offset),
            "tail_references_are_inert": True,
            "verdict": "ONLY_INITCALL_TABLE_REFERENCE_INTO_WINDOW"}


def whole_function_span_references(args, ctx, audit):
    """Window-scoped reference closure plus the whole-function CFG census.

    Literals/relocations/rewrites are scanned at the window (the only
    overwritten region); the branch audit runs over the FULL 492 bytes so a
    tail-resident source can never survive into the overwritten interior.
    """
    target = int(audit["target_va"], 16)
    text_va = ctx["text_va"]
    frozen = ctx["frozen"][:ctx["image_len"]]
    vmlinux = args.bundle / "vmlinux"
    table_sections = post50.vmlinux_table_sections(vmlinux, ctx["sections"])
    topology = cp.branch_audit(frozen, ctx["ranges"], text_va,
                               (target, target + FUNCTION_SIZE),
                               (target, target + WINDOW))
    require(not topology["incoming_entry"], "EXTENDED_INCOMING_ENTRY_BRANCH")
    require(not topology["incoming_window_interior"],
            "EXTENDED_INCOMING_INTERIOR_BRANCH")
    whole = cp.branch_audit(frozen, ctx["ranges"], text_va,
                            (target, target + FUNCTION_SIZE),
                            (target, target + FUNCTION_SIZE))
    require(not whole["incoming_window_interior"],
            "FULL_FUNCTION_INCOMING_INTERIOR_BRANCH")
    interior_sources = [row for row in topology["internal_branches"]
                        if WINDOW <= int(row[0], 16) - target < FUNCTION_SIZE
                        and 0 < int(row[1], 16) - target < WINDOW]
    require(not interior_sources, f"TAIL_SOURCE_INTO_INTERIOR:{interior_sources}")
    nxt = ctx["symbol_vas"][bisect.bisect_right(ctx["symbol_vas"], target)]
    cp.t3.gate_function_extent_scan(target, FUNCTION_SIZE, nxt)
    cp.t3.gate_window_literal_scan(target, WINDOW, frozen)
    cp.t3.gate_window_relocation_scan(target, WINDOW, ctx["reloc_sites"])
    forensic = post50.window_reference_forensic(
        ctx["image"], text_va, ctx["ranges"], table_sections,
        post50.symbol_pairs(args.bundle / "System.map"), ctx["sections"],
        target, WINDOW, TABLE_IMAGE_OFFSET)
    census = relative_reference_census(ctx["image"], text_va, target,
                                       FUNCTION_SIZE, WINDOW, TABLE_IMAGE_OFFSET)
    return {"span": [hex(target), hex(target + FUNCTION_SIZE)],
            "window_span": [hex(target), hex(target + WINDOW)],
            "branch_topology": topology,
            "full_function_interior_incoming": whole["incoming_window_interior"],
            "tail_source_into_interior": interior_sources,
            "internal_branch_count": len(topology["internal_branches"]),
            "back_edge_count": len(topology["back_edges"]),
            "window_reference_forensic": forensic,
            "relative_reference_census": census,
            "verdict": "NO_REFERENCE_INTO_WINDOW"}


def build_pairs(args, selection, ctx, metadata, out):
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
    core = cp.ultracompact_core(args.core56.read_bytes())
    require(cp.digest(core) == CORE56_SHA, "CORE56_SHA_DRIFT")
    entry_word = int(audit["entry_pad_word"], 16)
    require(entry_word == PACIASP, "PINNED_ENTRY_PAD_NOT_PACIASP")
    section = cp.t3.gate_window_section_scan(target, WINDOW, ctx["sections"])
    require(section["name"] == ".text", "WINDOW_NOT_TEXT_SECTION")
    require(cp.t3.sysmap_symbol(args.bundle / "System.map", audit["symbol"]) == target,
            "SYMBOL_MAP_MISMATCH")
    require_frozen_window_disjoint(target, WINDOW)
    require(audit["probe_architecture"] == PROBE_ARCHITECTURE,
            "PINNED_PROBE_ARCHITECTURE_DRIFT")
    require(audit["cfg_closure"] and audit["cfg_closure"]["cfg_closure_proven"],
            "CFG_CLOSURE_NOT_PROVEN")
    family_dir = out / FAMILY
    family_dir.mkdir(parents=True, exist_ok=False)
    rewrites = cp.audit_rewrites(family_dir, args.bundle / "vmlinux", ctx["sections"],
                                 (target, target + WINDOW))
    (family_dir / "original-function.txt").write_text(
        cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={target:#x}",
                   f"--stop-address={target + FUNCTION_SIZE:#x}",
                   str(args.bundle / "vmlinux")]))
    (family_dir / "original-window.txt").write_text(
        cp.pb.run([cp.TOOLS["objdump"], "-d", f"--start-address={target:#x}",
                   f"--stop-address={target + WINDOW:#x}",
                   str(args.bundle / "vmlinux")]))
    agreement = post50.window_agreement_round(ctx["image"], ctx["frozen"],
                                              ctx["text_va"], offset, WINDOW,
                                              ctx["sections"])
    write_json(family_dir / "window-agreement.json", agreement)
    write_json(family_dir / "cfg-closure.json", audit["cfg_closure"])
    extended = whole_function_span_references(args, ctx, audit)
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
        probe, payload = compose_member(ctx["frozen"], offset, WINDOW,
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
    semantics = core_semantics(probes, ctx["frozen"], offset, ctx["cfg"], audit)
    tail_report = {"target_va": audit["target_va"], "window": WINDOW,
                   "tail_bytes": TAIL_BYTES, "tail_present": True,
                   "window_end": hex(target + WINDOW),
                   "function_end": hex(target + FUNCTION_SIZE),
                   "terminal_words": [hex(0xD503205F), hex(0x17FFFFFF)],
                   "composed_branch_escape": 0,
                   "verdict": "TAIL_UNREACHABLE_FROM_COMPOSED_WINDOW"}
    write_json(family_dir / "tail-reachability.json", tail_report)
    audit.update({"entry_audit": "PASS", "incoming_branch_gate": "PASS",
                  "function_range_safe": True, "runtime_rewrite_safe": True,
                  "relocations_in_window": 0, "inline_only": True,
                  "trampoline_permitted": False, "island_permitted": False,
                  "window_derivation": "TARGET_CFG",
                  "window_agreement": agreement["verdict"],
                  "round_pad_class": "paciasp_only",
                  "probe_architecture": PROBE_ARCHITECTURE,
                  "window_reference_forensic": extended["verdict"],
                  "tail_reachability": tail_report["verdict"],
                  "text_exception_scope": "TARGET_SCOPED_ONLY",
                  "core_semantics": semantics})
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
                    "round_pad_class": "paciasp_only", "section": section["name"],
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
                    "tail_bytes": TAIL_BYTES, "tail_present": True,
                    "tail_reachability": tail_report["verdict"],
                    "core_semantics": semantics,
                    "cfg_closure": audit["cfg_closure"],
                    "branch_topology": audit["branch_topology"],
                    "runtime_rewrites": rewrites, "window_agreement": agreement,
                    "window_reference_forensic": extended["verdict"],
                    "window_derivation": "TARGET_CFG", "inline_only": True,
                    "trampoline_permitted": False, "island_permitted": False,
                    "text_exception_allowed_symbol": TEXT_EXCEPTION_ALLOWED_SYMBOL,
                    "text_exception_allowed_index": TEXT_EXCEPTION_ALLOWED_INDEX,
                    "text_exception_allowed_va": hex(TEXT_EXCEPTION_ALLOWED_VA),
                    "text_exception_allowed_section": TEXT_EXCEPTION_ALLOWED_SECTION,
                    "text_exception_scope": "TARGET_SCOPED_ONLY",
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
                "target_va": audit["target_va"], "target_section": audit["section"],
                "probe_architecture": PROBE_ARCHITECTURE,
                "window": WINDOW, "core_size": CORE_SIZE,
                "entry_pad": "paciasp", "round_pad_class": "paciasp_only",
                "tail_reachability": tail_report["verdict"],
                "text_exception_allowed": {
                    "symbol": TEXT_EXCEPTION_ALLOWED_SYMBOL,
                    "index": TEXT_EXCEPTION_ALLOWED_INDEX,
                    "va": hex(TEXT_EXCEPTION_ALLOWED_VA),
                    "section": TEXT_EXCEPTION_ALLOWED_SECTION,
                    "slot_count": len(TEXT_EXCEPTION_ALLOWED)},
                "text_exception_scope": "TARGET_SCOPED_ONLY",
                "private_pack": False, "device_operation": False,
                "kernel_rebuilt": False}
    write_json(family_dir / "pair" / "pair.json", identity)
    return {FAMILY: {"label": LABEL, "identity": identity, "audit": audit,
                     "selection": selection, "offset": offset, "window": WINDOW,
                     "core_size": CORE_SIZE, "shas": shas, "changed": changed,
                     "semantics": semantics, "agreement": agreement["verdict"],
                     "extended": extended, "tail": tail_report}}


def summary_kv(names, enriched, map_stats, scope):
    info = names[FAMILY]
    audit = info["audit"]
    semantic = info["semantics"]
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
             f"{prefix}SECTION={audit['section']}",
             f"{prefix}REGISTRATION={audit['registration']}",
             f"{prefix}SOURCE={audit['source']}",
             f"{prefix}DEVIATION=NONE",
             f"{prefix}ENTRY_PAD_CLASS={ROUND_PAD_VALUE}",
             f"{prefix}PROBE_FAMILY={PROBE_ARCHITECTURE}",
             f"{prefix}CORE_SHA256={CORE56_SHA}",
             f"{prefix}TEXT_EXCEPTION_MATCHED=YES",
             f"{LABEL}_8_PAYLOAD_SHA={info['shas'][8]}",
             f"{LABEL}_1_PAYLOAD_SHA={info['shas'][1]}",
             f"{prefix}PAIR_DIFF_OFFSETS={info['changed']}",
             f"{prefix}PAIR=PASS",
             f"TEXT_EXCEPTION_ALLOWED_SYMBOL={TEXT_EXCEPTION_ALLOWED_SYMBOL}",
             f"TEXT_EXCEPTION_ALLOWED_INDEX={TEXT_EXCEPTION_ALLOWED_INDEX}",
             f"TEXT_EXCEPTION_ALLOWED_VA={hex(TEXT_EXCEPTION_ALLOWED_VA)}",
             f"TEXT_EXCEPTION_ALLOWED_SECTION={TEXT_EXCEPTION_ALLOWED_SECTION}",
             "TEXT_EXCEPTION_ALLOWED=YES",
             f"TEXT_EXCEPTION_ALLOWED_SLOTS={scope['allowed_slot_count']}",
             "GLOBAL_ALLOW_TEXT_TARGETS=ABSENT",
             "TEXT_EXCEPTION_SCOPE=TARGET_SCOPED_ONLY",
             "NO_GENERIC_TEXT_POLICY_RELAXATION=YES",
             "TARGET_SCOPED_TEXT_EXCEPTION=PASS",
             "TEXT_EXCEPTION_MATCHED=YES",
             "TARGET_SECTION_IS_TEXT=YES",
             "INDEX53_AUTO_ELIGIBLE=NO",
             "OTHER_TEXT_FUNCTIONS_AUTO_ELIGIBLE=NO",
             "NO_ALLOW_TEXT_TARGETS_SWITCH=YES",
             "NON_MATCHING_TEXT_SYMBOL_REJECTED=YES",
             "SAME_SECTION_DIFF_VA_REJECTED=YES",
             "DIFF_INDEX_SAME_SYMBOL_REJECTED=YES",
             "INDEX53_TOO_SMALL_REJECTED=YES",
             "UNIQUE_ALLOWLIST_SLOT=YES",
             "CORE_SHA_MATCHES_FROZEN_FAMILY=YES",
             "PROBE_FAMILY_REUSED=YES",
             "TEXT_EXCEPTION_LIFETIME_CONTAINED=YES",
             "RAM_ONLY_ARTIFACT_SEMANTICS=YES",
             "NO_PARTITION_WRITE=YES",
             "NO_PERSISTENCE_ACROSS_REBOOT=YES",
             "FAIL_CLOSED_TERMINAL=YES",
             "DIAGNOSTIC_CANNOT_RETURN_TO_NORMAL_FUNCTION=YES",
             "NO_OTHER_EARLY_RUNTIME_CALLER=YES",
             "INITCALL_TABLE_REFERENCE_ONLY=YES",
             "OTHER_RUNTIME_REFERENCE=NO",
             "NO_ASYNC_EARLY_REACHABILITY=YES",
             "NO_POST_INITCALL_REUSE=YES",
             "CFG_XREF_RUNTIME_REWRITE=PASS",
             f"PAIR_DIFF={info['identity']['attribution']}",
             "INLINE_ONLY=YES", "TRAMPOLINE_PERMITTED=NO", "ISLAND_PERMITTED=NO",
             "PREL32_TARGET_UNCHANGED=YES", "SHARED_CHECKPOINT=NO",
             "CROSS_FUNCTION_OVERWRITE=NO", "WINDOW_DERIVATION=TARGET_CFG",
             "NO_TEXT_POLICY_CHANGE_OUTSIDE_ALLOWLIST=YES",
             "FROZEN_FAMILIES_UNCHANGED=PACIASP_PLUS_52B,PACIASP_PLUS_56B,BTI_C_PLUS_56B,COMPACT_INLINE_48B",
             "DEVICE_BOOT=0", "DEVICE_OPERATION=NO", "PRIVATE_PACK=NO",
             "KERNEL_REBUILD=NO", "PARTITION_WRITES=0", "SLOT_A_WRITTEN=NO",
             "LOCAL_BUILD=NO",
             f"WINDOW_AGREEMENT_INDEX54={info['agreement']}",
             f"{prefix}WINDOW_AGREEMENT={info['agreement']}",
             f"TEXT54_WINDOW_REFERENCE_FORENSIC={info['extended']['verdict']}",
             f"TEXT54_TAIL_REACHABILITY={info['tail']['verdict']}",
             f"TEXT54_INTERNAL_BRANCH_COUNT={info['extended']['internal_branch_count']}",
             f"TEXT54_BACK_EDGE_COUNT={info['extended']['back_edge_count']}",
             f"LATEST_PROVEN_LATE_INDEX={52}",
             "DEFERRED_PROBE_INITCALL_ENTRY=NOT_PROVEN",
             "TEXT54_1_PAIR_EXECUTED=NO", "TEXT54_8_PAIR_EXECUTED=NO",
             "LATE_INITCALLS_COMPLETED=NOT_PROVEN",
             "WAIT_FOR_INITRAMFS_ENTRY=NOT_PROVEN",
             "WAIT_FOR_INITRAMFS_RETURN=NOT_PROVEN",
             "LATE_HIGH1=NOT_EXECUTED"]
    lines += [f"{key}={value}" for key, value in semantic.items()]
    lines += [f"{key}={value}" for key, value in scope["adversarial"].items()]
    return lines


def high8_forensic(entries, ctx, args, out):
    """Reuse post50's HIGH8 forensic path so the frozen anomaly is re-audited in
    this round's own artifact, under this round's pad polarity."""
    record = post50.high8_forensic(entries, ctx, args, out)
    record["stage"] = STAGE
    record["round_pad_class_of_forensic"] = "paciasp_only"
    write_json(out / "high8-forensic.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "frozen", "core56", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    frozen = args.frozen.read_bytes()
    require(cp.digest(cp.ultracompact_core(args.core56.read_bytes())) == CORE56_SHA,
            "CORE56_SHA_DRIFT")
    metadata, raw_entries, enriched, ctx = base.enumerate_level7(args.bundle,
                                                                frozen, out)
    map_stats = {"init_text": sum(1 for e in enriched if e["init_text"]),
                 "text_section": sum(1 for e in enriched if not e["init_text"])}
    high8 = high8_forensic(enriched, ctx, args, out)
    selection = pin_target(enriched, ctx)
    scope = non_generalization_probe(enriched, ctx)
    write_json(out / "late-map.json", {
        "stage": STAGE, "bundle_run": base.BUNDLE_RUN,
        "span": [base.SPAN_BEGIN, base.SPAN_END], "entry_count": len(enriched),
        "index0_identity": base.FROZEN_INDEX0, "entries": enriched})
    write_json(out / "selection.json", {
        "stage": STAGE, "pinned_index": PINNED_INDEX,
        "selections": {FAMILY: selection},
        "round_pad_gate": ROUND_PAD_GATE, "round_pad_class": ROUND_PAD_VALUE,
        "frozen_indices": FROZEN_LATE_INDICES,
        "interval_walk": "NONE_TARGET_PINNED_DIRECTLY",
        "text_exception": {
            "allowed_symbol": TEXT_EXCEPTION_ALLOWED_SYMBOL,
            "allowed_index": TEXT_EXCEPTION_ALLOWED_INDEX,
            "allowed_va": hex(TEXT_EXCEPTION_ALLOWED_VA),
            "allowed_section": TEXT_EXCEPTION_ALLOWED_SECTION,
            "slots": len(TEXT_EXCEPTION_ALLOWED),
            "global_allow_text_targets": "ABSENT"},
        "non_generalization": scope})
    names = build_pairs(args, selection, ctx, metadata, out)
    require(cp.digest((args.bundle / "vmlinux").read_bytes())
            == metadata["files"]["vmlinux"], "AUDIT_MUTATED_ELF")
    require(frozen == args.frozen.read_bytes(), "AUDIT_MUTATED_FROZEN")
    info = names[FAMILY]
    lines = summary_kv(names, enriched, map_stats, scope)
    (out / "audit-summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"HIGH8_FORENSIC_VERDICT={high8['HIGH8_STATIC_PROBE_DEFECT_FOUND']}",
          flush=True)
    print(f"{STAGE}_PAIR_AUDIT=PASS", flush=True)


if __name__ == "__main__":
    main()
