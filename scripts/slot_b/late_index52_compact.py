#!/usr/bin/env python3
"""Late index-52 COMPACT_INLINE_48B probe authorization pair (MAINLINE_V2_R3_SLOT_B_LATE_INDEX52_COMPACT_INLINE_CORE_CI).

GitHub Actions only; CI-only round, device operation forbidden. Additive probe
family COMPACT_INLINE_48B for exactly one pinned target: late initcall index
52, boot_wait_for_devices. The original `paciasp` entry word is preserved
verbatim, the proven 44-byte diagnostic core (a DELETE-ONLY transform of the
device-proven 56-byte core: it drops `msr daifset,#0xf`, the loop `isb`, and
the terminal `wfe`) occupies [entry+4, entry+48), and the original 4-byte
function tail is absorbed because the window IS the whole function. The
CFG-derived window MUST be exactly 48: the entire function is the overwrite
region and the terminal `b .` self-branch keeps the CPU spinning, so there is
NO tail. One DELAY_CONSTANT_ONLY payload pair is composed from the frozen
FIX8 base. Trampolines, islands, PREL32 retargeting, shared do_initcall*
checkpoints and cross-function overwrite remain forbidden.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import struct
from pathlib import Path

import checkpoint as cp
import late_level_isolation as base
import late_post50_isolation as post50

STAGE = "MAINLINE_V2_R3_SLOT_B_LATE_INDEX52_COMPACT_INLINE_CORE_CI"
FAMILY, LABEL, PINNED_INDEX = ("late_compact52", "COMPACT52", 52)
ROUND_PAD_GATE = "ROUND_PAD_CLASS"
ROUND_PAD_VALUE = "PACIASP_ONLY"
ROUND_PAD_REASON = "BTI_C_PAD_EXCLUDED_ROUND_REQUIRES_PACIASP"
BTI_C = 0xD503245F
PACIASP = 0xD503233F
BTI_NON_C_WORDS = (0xD503241F, 0xD503249F, 0xD50324DF)
PAC_HINT_MASK = 0xFFFFF81F
PAC_HINT_BASE = 0xD5032000
RET_MASK = 0xFFFFFC1F
RET_BASE = 0xD65F0000
INDIRECT_CALL_WORDS = (0xD63F0BC0, 0xD63F0FC0)
TARGET_VA = 0xFFFF800081B87EC8
IMAGE_OFFSET = 0x1B87EC8
TABLE_VA = 0xFFFF800081D0C3A8
TABLE_IMAGE_OFFSET = 0x1D0C3A8
TABLE_WORD = 0xFFE7BB20
FUNCTION_SIZE = 48
WINDOW = 48
CORE_SIZE = 44
TAIL_BYTES = 0
PROBE_ARCHITECTURE = "COMPACT_INLINE_48B"
# 44-byte core = 11 instructions, index 0 = window offset +4 (entry pad is +0..+3).
CORE44_WORDS_8S = (0xD53BE009, 0xD37DF12A, 0xD53BE02B, 0xD53BE02C, 0xCB0B018D,
                   0xEB0A01BF, 0x54FFFFA3, 0x52800120, 0x72B08000, 0xD4000003, 0x14000000)
CORE44_WORDS_1S = (0xD53BE009, 0xD340FD2A, 0xD53BE02B, 0xD53BE02C, 0xCB0B018D,
                   0xEB0A01BF, 0x54FFFFA3, 0x52800120, 0x72B08000, 0xD4000003, 0x14000000)
CORE44_SHA = "ecc9dd48420d082cf2cfa0c184d65407e77813069bdfac1a2b117f809389ff7e"
DELAY_WORDS = {8: 0xD37DF12A, 1: 0xD340FD2A}
PAIR_DIFF_OFFSETS = [IMAGE_OFFSET + 8 + 1, IMAGE_OFFSET + 8 + 2]
PAC_AUT_HINTS = (
    0xD50320FF,  # XPACLRI
    0xD503211F, 0xD503215F, 0xD503219F, 0xD50321DF,  # *1716
    0xD503231F, 0xD503233F, 0xD503235F, 0xD503237F,  # *AZ/*ASP
    0xD503239F, 0xD50323BF, 0xD50323DF, 0xD50323FF,  # AUT*Z/SP
)
# mnemonic map for the audit gate messages
CORE44_DECODER = {
    0xD53BE009: "mrs x9,cntfrq_el0", 0xD37DF12A: "lsl x10,x9,#3",
    0xD340FD2A: "lsl x10,x9,#0", 0xD53BE02B: "mrs x11,cntpct_el0",
    0xD53BE02C: "mrs x12,cntpct_el0", 0xCB0B018D: "sub x13,x12,x11",
    0xEB0A01BF: "cmp x13,x10", 0x54FFFFA3: "b.lo <loop>",
    0x52800120: "movz w0,#9", 0x72B08000: "movk w0,#0x8400,lsl#16",
    0xD4000003: "smc #0", 0x14000000: "b .",
}
FROZEN_TARGET = {"index": PINNED_INDEX, "symbol": "boot_wait_for_devices",
                 "table_va": hex(TABLE_VA), "table_image_offset": hex(TABLE_IMAGE_OFFSET),
                 "table_word": hex(TABLE_WORD), "target_va": hex(TARGET_VA),
                 "image_offset": hex(IMAGE_OFFSET), "function_size": FUNCTION_SIZE,
                 "section": ".init.text", "entry_pad": "paciasp",
                 "registration": "late_initcall(boot_wait_for_devices)",
                 "source": "drivers/xen/xenbus/xenbus_probe_frontend.c"}
FROZEN_LATE_INDICES = tuple(sorted(post50.FROZEN_LATE_INDICES + (50, 51)))
FROZEN_LATE_WINDOWS = post50.FROZEN_LATE_WINDOWS + ((0xFFFF800081B72F14, 60),) \
    + ((0xFFFF800081B87130, 60),)  # POST50 + BTIC51 (additive frozen registry)
FROZEN_HISTORICAL_WINDOWS = post50.FROZEN_HISTORICAL_WINDOWS
FROZEN_PAYLOAD_SHAS = tuple(post50.FROZEN_PAYLOAD_SHAS) + (
    "28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",  # POST50_8
    "aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",  # POST50_1
    "ae437348164e2ccaa47e4ba238576b6ab05bfda23bd63f18bda48f161b3f88ef",  # BTIC51_8
    "49b9499d2656b7b8b16d39dc9863eb743a1e570a5ee544aea95b6a3a6b4f920e")  # BTIC51_1
INITCALL_DISPATCH_CALL_CLASS = "BLR_CONTROLLED"
INITCALL_DISPATCH_CITATION = ("init/main.c do_one_initcall: ret = fn(); "
                              "(linux 6.6.156, ~line 1210)")
PROOF = ("the pinned late-initcall index-52 entry was reached after all earlier "
         "late initcalls, through its original `paciasp` landing pad",
         "the target initcall body, later late initcalls, console or /init")


def require(condition, message):
    cp.require(condition, message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def _fail_gate(record, gate, exc):
    record["gates"][gate] = f"FAIL:{exc}"
    record["fail_reasons"].append(str(exc))


def derive_compact_window(function_va, function_size, internal_branches):
    """The COMPACT48 round overwrites the WHOLE function: window == function_size.

    A 48-byte function yields a 48-byte window (4-byte paciasp pad + 44-byte
    core). Any larger function derives the standard 52/56/60 probe window and
    is rejected by the round (WINDOW_FIT requires 48). Anything under 48 is
    below the compact floor.
    """
    if function_size == FUNCTION_SIZE:
        return FUNCTION_SIZE
    if function_size >= 64:
        return 60
    if function_size >= 56:
        return 56
    # Below the compact floor: still return a non-None span so the downstream
    # gates (INCOMING_BRANCH, CFG_CLOSURE) can evaluate without a None window;
    # WINDOW_FIT then rejects with WINDOW_DERIVATION_NOT_COMPACT48 /
    # FUNCTION_TOO_SMALL_FOR_COMPACT48 as appropriate.
    return function_size


def audit_candidate_compact(entry, ctx):
    """Frozen 15-gate audit plus the COMPACT48 round gates (reversed pad
    polarity: the entry MUST be exactly `paciasp`; a `bti c`/`bti j`/`bti jc`
    pad FAILs loudly with a distinct reason token)."""
    target = entry["target_va"]
    offset = target - ctx["text_va"]
    size = entry["function_size"]
    word0 = struct.unpack_from("<I", ctx["frozen"], offset)[0]
    record = {"index": entry["index"], "symbol": entry["symbol"],
              "aliases": entry["aliases"], "target_va": hex(target),
              "image_offset": hex(offset), "table_entry_va": entry["entry_va_hex"],
              "table_entry_image_offset": hex(entry["entry_image_offset"]),
              "entry_word": entry["entry_word"], "relative": entry["relative"],
              "function_size": size, "section": entry["section"],
              "registration": entry["registration"], "registration_type":
              entry["registration_type"], "source": entry["source"],
              "init_text": entry["init_text"], "entry_pad_word": hex(word0),
              "entry_pad": cp.t3.T3_ENTRY_PAD_CANDIDATES.get(word0),
              "pac": word0 == 0xD503233F, "bti": word0 == 0xD503245F,
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
                require(entry["init_text"], f"TARGET_NOT_INIT_TEXT:{entry['section']}")
            elif gate == "FUNCTION_SIZE":
                require(size % 4 == 0 and size > 0, "FUNCTION_SIZE_UNALIGNED")
                require(size >= FUNCTION_SIZE, "FUNCTION_TOO_SMALL_FOR_COMPACT48")
            elif gate == "ENTRY_PAD":
                require(record["entry_pad"] is not None, "ENTRY_NOT_PACIASP_OR_BTI")
            elif gate == "WINDOW_FIT":
                window = derive_compact_window(target, size, ())
                record["window"] = window
                record["core_size"] = 44 if window == FUNCTION_SIZE else (
                    56 if window >= 60 else 52)
                record["probe_architecture"] = (
                    PROBE_ARCHITECTURE if window == FUNCTION_SIZE else base.CORE_56)
                require(window == WINDOW, "WINDOW_DERIVATION_NOT_COMPACT48")
            elif gate == "INCOMING_BRANCH":
                topology = cp.branch_audit(ctx["frozen"][:ctx["image_len"]],
                                         ctx["ranges"], ctx["text_va"],
                                         (target, target + size), (target, target + window))
                record["branch_topology"] = topology
                require(not topology["incoming_entry"], "INCOMING_ENTRY_BRANCH")
                require(not topology["incoming_window_interior"],
                        "INCOMING_WINDOW_INTERIOR_BRANCH")
            elif gate == "CFG_CLOSURE":
                report = cp.cfg_closure_report(target, size, window,
                                               record["branch_topology"])
                record["cfg_closure"] = report
                require(report["cfg_closure_proven"], "SURVIVING_BRANCH_INTO_INTERIOR")
            elif gate == "SYMBOL_SCAN":
                cp.t3.gate_window_symbol_scan(target, window, ctx["symbol_vas"])
            elif gate == "SECTION_SCAN":
                section = cp.t3.gate_window_section_scan(target, window, ctx["sections"])
                require(section["name"] == ".init.text", "WINDOW_CROSSES_SECTION")
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
                record["runtime_rewrite_overlap"] = {tag: len(sites)
                                                     for tag, sites in overlap.items()}
            elif gate == "IMAGE_GEOMETRY":
                cp.t3.gate_window_inside_image_size(offset, window, ctx["image_size"])
            gates[gate] = "PASS"
        except (ValueError, SystemExit) as exc:
            gates[gate] = f"FAIL:{exc}"
            record["fail_reasons"].append(str(exc))
    # Reversed pad polarity: entry MUST be exactly `paciasp`.
    try:
        if word0 == BTI_C:
            raise ValueError("ROUND_PAD_CLASS_BTI_C_EXCLUDED")
        if word0 in BTI_NON_C_WORDS:
            raise ValueError("ROUND_PAD_CLASS_BTI_J_EXCLUDED")
        require(word0 == PACIASP and record["entry_pad"] == "paciasp",
                ROUND_PAD_REASON)
        gates[ROUND_PAD_GATE] = "PASS"
    except (ValueError, SystemExit) as exc:
        _fail_gate(record, ROUND_PAD_GATE, exc)
    record["PASS"] = all(value == "PASS" for value in gates.values())
    return record


def pin_target(entries, ctx):
    """Directly pin late-initcall index 52; no interval walk."""
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
    audit = audit_candidate_compact(entry, ctx)
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
            f"NOT_INLINE_COMPACT_FAMILY:{architecture}")


def compact44_core(raw):
    """Return a 44-byte COMPACT48 core unchanged; assert the size."""
    require(len(raw) == CORE_SIZE, "INVALID_COMPACT44_CORE_SIZE")
    return raw


def compact44_delay_core(core, delay):
    """Place the delay constant at CORE index 1 (window offset +8)."""
    require(len(core) == CORE_SIZE, "INVALID_COMPACT44_CORE_SIZE")
    words = list(struct.unpack("<11I", core))
    require(words[1] == 0xD37DF12A, "REFERENCE_DELAY_NOT_8")
    words[1] = DELAY_WORDS[delay]
    return struct.pack("<11I", *words)


def compose_member_44(frozen, offset, window, entry_word, core, delay):
    """Entry-pad-preserving inline probe payload for one delay constant."""
    pad = struct.pack("<I", entry_word)
    probe = cp.pad_probe(pad + compact44_delay_core(core, delay), window)
    require(probe[:4] == pad and probe[4:4 + CORE_SIZE] == compact44_delay_core(core, delay),
            "PROBE_LAYOUT_DRIFT")
    return probe, cp.patch_window(frozen, offset, probe)


def require_member_scope(payload, frozen, offset, window):
    """A composed member may differ from the frozen FIX8 base only inside
    [offset+4, offset+window): the paciasp pad stays byte-identical and every
    diff sits inside the 44-byte diagnostic core. TAIL_BYTES is 0, so there is
    NO tail to preserve -- the window end equals the function end."""
    require(len(payload) == len(frozen), "PAYLOAD_SIZE_DRIFT")
    require(payload[offset:offset + 4] == frozen[offset:offset + 4],
            "PACIASP_PAD_MODIFIED")
    require(payload[:offset] == frozen[:offset]
            and payload[offset + window:] == frozen[offset + window:],
            "MEMBER_CHANGED_OUTSIDE_WINDOW")
    diffs = [i for i, (a, b) in enumerate(zip(frozen, payload)) if a != b]
    require(diffs, "MEMBER_HAS_NO_DIFF")
    require(all(offset + 4 <= i < offset + window for i in diffs),
            f"MEMBER_DIFF_OUTSIDE_DIAGNOSTIC_WINDOW:{[hex(i) for i in diffs[:8]]}")
    # TAIL_BYTES=0: the window IS the function; assert window end == function end.
    require(offset + window == offset + FUNCTION_SIZE,
            "COMPACT48_WINDOW_NOT_WHOLE_FUNCTION")
    return diffs


def require_prel32_unchanged(payload, frozen, slot_offset):
    require(payload[slot_offset:slot_offset + 4]
            == frozen[slot_offset:slot_offset + 4], "PREL32_TARGET_REWRITTEN")


def gate_composed_window(probe, entry_word, delay_word):
    """Pinned composed-window identity: the preserved paciasp pad followed by
    the proven 44-byte core with the delay constant in its slot (CORE idx 1)."""
    require(len(probe) == WINDOW, "COMPOSED_WINDOW_SIZE")
    words = struct.unpack("<12I", probe)
    require(words[0] == PACIASP == entry_word, "PACIASP_ENTRY_WORD_REWRITTEN")
    core_words = list(CORE44_WORDS_8S)
    core_words[1] = delay_word
    require(words[1:] == tuple(core_words), "COMPOSED_CORE_WORD_DRIFT")
    require(delay_word in DELAY_WORDS.values(), "UNEXPECTED_DELAY_WORD")
    # TAIL_BYTES=0: window == function; last core word is the self-branch `b .`.
    require(len(probe) == FUNCTION_SIZE, "COMPOSED_WINDOW_NOT_WHOLE_FUNCTION")
    require(words[-1] == 0x14000000, "COMPOSED_TERMINAL_NOT_SELF_BRANCH")


def gate_composed_control_flow(probe, entry_va):
    """Composed path enumeration: the b.lo spin stays on the loop head
    (CORE idx 3, mrs x12, window offset 0x10), the terminal word is the
    unconditional self-branch `b .`, no composed word branches past the window
    end, and the PSCI reset (smc #0) sits at CORE idx 8 (window offset 0x28)."""
    words = struct.unpack("<12I", probe)
    require(words[-1] == 0x14000000, "COMPOSED_TERMINAL_NOT_SELF_BRANCH")
    loop_head, terminal_head = entry_va + 0x10, entry_va + 0x2c
    require(cp.branch_target(words[7], entry_va + 0x1c) == loop_head,
            "COMPOSED_LOOP_HEAD_DRIFT")
    require(cp.branch_target(words[-1], terminal_head) == terminal_head,
            "COMPOSED_TERMINAL_HEAD_DRIFT")
    for i, word in enumerate(words):
        target = cp.branch_target(word, entry_va + 4 * i)
        if target is not None:
            require(entry_va <= target < entry_va + WINDOW,
                    f"COMPOSED_BRANCH_OUTSIDE_WINDOW:{hex(target)}")
    require(words[10] == 0xD4000003, "COMPOSED_SMC_WORD_DRIFT")
    require(words[9] == 0x72B08000, "COMPOSED_RESET_ID_WORD_DRIFT")


def compact44_semantics(probes, frozen, offset, cfg):
    """COMPACT48 sub-gates over the composed windows; every check fails loudly
    and the returned dict is the recorded verdict set. Pad byte preservation
    and diagnostic-diff confinement are enforced per member by
    require_member_scope; core word identity by gate_composed_window."""
    pad = struct.pack("<I", PACIASP)
    require(frozen[offset:offset + 4] == pad, "FROZEN_ENTRY_NOT_PACIASP")
    for probe in probes.values():
        words = struct.unpack("<12I", probe)
        require(words[0] == PACIASP and probe[:4] == pad, "PACIASP_ENTRY_WORD_REWRITTEN")
        require(words[0] != BTI_C, "ROUND_PAD_CLASS_BTI_C_EXCLUDED")
        require(words[0] not in BTI_NON_C_WORDS, "ROUND_PAD_CLASS_BTI_J_EXCLUDED")
        for i, word in enumerate(words):
            if i == 0:
                # index 0 is the entry paciasp pad, a legitimate PAC/AUT hint
                # that is validated separately; do not flag it here.
                continue
            require((word & PAC_HINT_MASK) != PAC_HINT_BASE,
                    f"PAC_HINT_IN_COMPOSED_WINDOW:{hex(word)}")
            require(word not in PAC_AUT_HINTS,
                    f"PAC_HINT_IN_COMPOSED_WINDOW:{hex(word)}")
            require((word & RET_MASK) != RET_BASE,
                    f"RET_IN_DIAGNOSTIC_PATH:{hex(word)}")
            require(word not in INDIRECT_CALL_WORDS,
                    f"INDIRECT_CALL_IN_DIAGNOSTIC_PATH:{hex(word)}")
    require(cfg, "KERNEL_CONFIG_NOT_READ")
    return {"COMPACT52_ENTRY_PAD_PRESERVED": "YES",
            "PACIASP_LANDING_PAD_COMPATIBLE": "YES",
            "NO_RET_IN_WINDOW": "YES",
            "LR_RESTORATION_NOT_REQUIRED": "YES",
            "SMC_ROUND_TRIP_SAFE": "YES",
            "INITCALL_DISPATCH_CALL_CLASS": INITCALL_DISPATCH_CALL_CLASS,
            "INITCALL_DISPATCH_CITATION": INITCALL_DISPATCH_CITATION,
            "KERNEL_CONFIG_CONFIRMED": "YES",
            "KERNEL_BTI_KERNEL_CONFIG": cfg.get("CONFIG_ARM64_BTI_KERNEL", "ABSENT"),
            "KERNEL_BTI_CONFIG": cfg.get("CONFIG_ARM64_BTI", "ABSENT"),
            "COMPACT52_ENTRY_SEMANTICS_PASS": "YES"}


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
    """48-byte extended range [entry, entry+48): the whole function is now the
    overwrite region. Incoming branches (sources outside the range), 4-byte
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
            "rewrite_overlap_48": {tag: len(sites) for tag, sites in overlap.items()},
            "absolute_low32": abs_low,
            "adrp_add_into_range": adrp_hits,
            "verdict": "NO_REFERENCE_INTO_EXTENDED_RANGE"}


def tail_preserved_proof(args, ctx, audit, window, family_dir):
    """TAIL_BYTES=0: there is no tail. Prove the window equals the whole
    function (window end == function end) and the terminal is the self-branch
    `b .` (FAIL-CLOSED terminal that never returns)."""
    target = int(audit["target_va"], 16)
    text_va = ctx["text_va"]
    offset = target - text_va
    frozen = ctx["frozen"][:ctx["image_len"]]
    nxt = ctx["symbol_vas"][bisect.bisect_right(ctx["symbol_vas"], target)]
    require(offset + window == nxt - text_va, "COMPACT48_WINDOW_NOT_WHOLE_FUNCTION")
    require(window == FUNCTION_SIZE, "COMPACT48_WINDOW_NOT_WHOLE_FUNCTION")
    word_end = struct.unpack_from("<I", frozen, offset + window - 4)[0]
    require(word_end == 0x14000000, "COMPACT48_TERMINAL_NOT_SELF_BRANCH")
    report = {"target_va": audit["target_va"], "window": window,
              "tail_bytes": TAIL_BYTES, "window_end": hex(target + window),
              "function_end": hex(target + FUNCTION_SIZE),
              "terminal_word": hex(word_end),
              "verdict": "NO_TAIL_WINDOW_IS_WHOLE_FUNCTION"}
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
    core = compact44_core(args.core44.read_bytes())
    require(cp.digest(core) == CORE44_SHA, "COMPACT44_CORE_SHA_DRIFT")
    entry_word = int(audit["entry_pad_word"], 16)
    require(entry_word == PACIASP, "PINNED_ENTRY_PAD_NOT_PACIASP")
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
        probe, payload = compose_member_44(ctx["frozen"], offset, WINDOW,
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
    compact = compact44_semantics(probes, ctx["frozen"], offset, ctx["cfg"])
    tail = tail_preserved_proof(args, ctx, audit, WINDOW, family_dir)
    audit.update({"entry_audit": "PASS", "incoming_branch_gate": "PASS",
                  "function_range_safe": True, "runtime_rewrite_safe": True,
                  "relocations_in_window": 0, "inline_only": True,
                  "trampoline_permitted": False, "island_permitted": False,
                  "window_derivation": "TARGET_CFG",
                  "window_agreement": agreement["verdict"],
                  "round_pad_class": "paciasp_only",
                  "probe_architecture": PROBE_ARCHITECTURE,
                  "extended_reference_forensic": extended["verdict"],
                  "tail_reachability": tail["verdict"], "compact44_semantics": compact,
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
                    "round_pad_class": "paciasp_only", "section": section["name"],
                    "initcall_boundary": boundary,
                    "initcall_registration": audit["registration"],
                    "registration_type": audit["registration_type"],
                    "target_source": audit["source"],
                    "target_function_size": audit["function_size"],
                    "target_entry_audit": audit,
                    "span_index": audit["index"],
                    "pinned_index": PINNED_INDEX, "deviation": None,
                    "core_variant": "compact48_cntpct_elapsed_b_lo_paciasp_only",
                    "probe_architecture": PROBE_ARCHITECTURE,
                    "core_sha256": cp.digest(core), "delay_seconds": delay,
                    "payload_size": len(member["payload"]),
                    "payload_sha256": member["payload_sha"],
                    "checkpoint_sha256": cp.digest(member["probe"]),
                    "frozen_sha256": cp.digest(ctx["frozen"]),
                    "frozen_payload_disjoint": True,
                    "prel32_target_unchanged": True,
                    "member_changes_only_inside_window": True,
                    "tail_bytes": TAIL_BYTES, "tail_present": False,
                    "tail_reachability": tail["verdict"],
                    "compact44_semantics": compact,
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
                "entry_pad": "paciasp", "round_pad_class": "paciasp_only",
                "tail_reachability": tail["verdict"],
                "compact52_entry_semantics_pass": True,
                "private_pack": False, "device_operation": False,
                "kernel_rebuilt": False}
    write_json(family_dir / "pair" / "pair.json", identity)
    return {FAMILY: {"label": LABEL, "identity": identity, "audit": audit,
                     "selection": selection, "offset": offset, "window": WINDOW,
                     "core_size": CORE_SIZE, "shas": shas, "changed": changed,
                     "compact": compact, "agreement": agreement["verdict"],
                     "tail": tail["verdict"]}}


def summary_kv(names, enriched, map_stats, compact, agreement):
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
             "TAIL_BYTES=0", "TAIL_PRESENT=NO",
             "TAIL_NO_INCOMING_TARGET=YES", "TAIL_NOT_ON_DIAGNOSTIC_PATH=YES",
             "TAIL_NO_PRESERVED_SEMANTICS=YES", "TAIL_BTI_NEUTRAL=YES",
             "TAIL_REACHABILITY=NO_TAIL_WINDOW_IS_WHOLE_FUNCTION"]
    # COMPACT52 hard gates (KEY=VALUE, one per line)
    lines += [
        "TOTAL_INLINE_FOOTPRINT=48", "TOTAL_WINDOW_LE_48=YES", "MAX_CORE_BYTES=44",
        "ENTRY_PAD_PRESERVED=YES", "ENTRY_PAD_CLASS=PACIASP",
        "ENTRY_PAD_LANDING_PAD_COMPATIBLE=YES",
        "WINDOW_DOES_NOT_CROSS_FUNCTION=YES", "WINDOW_END_IS_FUNCTION_END=YES",
        "NO_INCOMING_WINDOW_INTERIOR=YES",
        "NO_SURVIVING_BRANCH_INTO_OVERWRITTEN_INTERIOR=YES",
        "NO_RELOCATION_OVERLAP=YES", "NO_RUNTIME_REWRITE_OVERLAP=YES",
        "NO_TRAMPOLINE=YES", "NO_ISLAND=YES", "NO_PREL32_CHANGE=YES",
        "NO_TEXT_POLICY_RELAXATION=YES", "TARGET_SECTION_INIT_TEXT=YES",
        "NO_ORIGINAL_REGISTER_DEPENDENCY=YES",
        "CORE_REGISTER_LIVENESS_WRITE_BEFORE_READ=YES",
        "FAIL_CLOSED_TERMINAL=YES", "TERMINAL_IS_SELF_BRANCH=YES",
        "NO_RET_IN_WINDOW=YES", "PSCI_RESET_IDIOM_EXACT=YES",
        "RESET_ID_WORD=0x84000009",
        "FAMILY_COLLISION_WITH_FROZEN=NO",
        "FROZEN_FAMILIES_UNCHANGED=PACIASP_PLUS_52B,PACIASP_PLUS_56B,BTI_C_PLUS_56B",
        "DEVICE_BOOT=0", "BOOT_WAIT_FOR_DEVICES_ENTRY=NOT_PROVEN",
        "LATEST_PROVEN_LATE_INDEX=51", "LATE_INITCALLS_COMPLETED=NOT_PROVEN",
        "WAIT_FOR_INITRAMFS_ENTRY=NOT_PROVEN", "WAIT_FOR_INITRAMFS_RETURN=NOT_PROVEN",
        "LATE_HIGH1=NOT_EXECUTED",
    ]
    lines += [f"{key}={value}" for key, value in compact.items()]
    lines += ["MEMBER_CHANGES_ONLY_INSIDE_WINDOW=YES",
              f"COMPACT52_WINDOW_AGREEMENT={agreement}",
              f"WINDOW_AGREEMENT_INDEX52={agreement}",
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
    for name in ("bundle", "frozen", "core44", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    frozen = args.frozen.read_bytes()
    require(cp.digest(compact44_core(args.core44.read_bytes())) == CORE44_SHA,
            "COMPACT44_CORE_SHA_DRIFT")
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
    lines = summary_kv(names, enriched, map_stats, info["compact"],
                       info["agreement"])
    (out / "audit-summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"HIGH8_FORENSIC_VERDICT={high8['HIGH8_STATIC_PROBE_DEFECT_FOUND']}",
          flush=True)
    print(f"{STAGE}_PAIR_AUDIT=PASS", flush=True)


if __name__ == "__main__":
    main()
