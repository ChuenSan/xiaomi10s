#!/usr/bin/env python3
"""Late (level-7) MID/LOW/HIGH inline failure-isolation pairs (MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION).

GitHub Actions only. Re-derives the 86-entry late span
[__initcall7_start, __initcall_end) from the authoritative bundle vmlinux,
selects the mathematical midpoint (MID=43) with LOW/HIGH bisection children
(21/64) under the full inline probe-safety gate set, and composes one
DELAY_CONSTANT_ONLY kernel payload pair per family from the frozen FIX8 base.
Trampolines, islands, PREL32 retargeting, shared do_initcall* checkpoints and
cross-function overwrite are forbidden.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import struct
from pathlib import Path

import checkpoint as cp

STAGE = "MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION"
BUNDLE_RUN = "35040148509"
TEXT_VA = 0xFFFF800080000000
ELF_SHA = "295bfdb12184052a79c1aea35ce4a93a5833c42bdb7b4bd9173973312ade00ff"
SPAN_BEGIN = "__initcall7_start"
SPAN_END = "__initcall_end"
SPAN_COUNT = cp.FROZEN_LEVEL7_SPAN_COUNT
FAMILIES = (("late_mid", "MID", 43), ("late_low", "LOW", 21), ("late_high", "HIGH", 64))
CORE_56 = "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT"
CORE_52 = "INLINE_PACIASP_PLUS_52B_NO_DAIFSET"
GATES = ("TARGET_UNIQUE", "REGISTRATION_LATE", "INIT_TEXT", "FUNCTION_SIZE", "ENTRY_PAD",
         "WINDOW_FIT", "INCOMING_BRANCH", "CFG_CLOSURE", "SYMBOL_SCAN", "SECTION_SCAN",
         "EXTENT_SCAN", "LITERAL_SCAN", "RELOCATION_SCAN", "RUNTIME_REWRITE",
         "IMAGE_GEOMETRY")
FROZEN_INDEX0 = {"index": 0, "symbol": "kernel_do_mounts_initrd_sysctls_init",
                 "entry_va": 0xFFFF800081D0C2D8, "entry_image_offset": 0x1D0C2D8,
                 "entry_word": 0xFFE25DA0, "relative": -1942112,
                 "target_va": 0xFFFF800081B32078, "target_image_offset": 0x1B32078,
                 "function_size": 60, "entry_pad": "paciasp", "bti": False,
                 "registration": "late_initcall(kernel_do_mounts_initrd_sysctls_init)",
                 "source": "init/do_mounts_initrd.c"}
PROOF = {
    "late_mid": ("the selected level-7 late midpoint initcall entry was reached "
                 "after all earlier late initcalls",
                 "the target late initcall body, later late initcalls, console or /init"),
    "late_low": ("the selected lower-bisection late initcall entry was reached after "
                 "the earlier late initcalls",
                 "the target late initcall body, later late initcalls, console or /init"),
    "late_high": ("the selected upper-bisection late initcall entry was reached after "
                  "the earlier late initcalls",
                  "the target late initcall body, later late initcalls, console or /init"),
}


def require(condition, message):
    cp.require(condition, message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def core_bytes(core, size):
    words = cp.ULTRACOMPACT_WORDS if size == 56 else cp.SUBSYS52_WORDS
    require(len(core) == size, "INVALID_CORE_SIZE")
    return cp.ultracompact_core(core) if size == 56 else cp.subsys52_core(core), words


def min_probe_for(function_size):
    require(function_size > 0 and function_size % 4 == 0, "FUNCTION_SIZE_UNALIGNED")
    require(function_size >= 56, "FUNCTION_TOO_SMALL")
    return 4 + (56 if function_size >= 60 else 52)


def candidate_ordering(nominal, count):
    """Nearest-safe fallback order: minimal index distance, lower index on ties."""
    require(0 <= nominal < count, "NOMINAL_INDEX_OUT_OF_SPAN")
    return sorted(range(count), key=lambda i: (abs(i - nominal), i))


def check_continuity(entries):
    require(len(entries) == SPAN_COUNT, f"LATE_TABLE_COUNT_DRIFT:{len(entries)}")
    for prev, entry in zip(entries, entries[1:]):
        require(entry["entry_va"] - prev["entry_va"] == 4, "LATE_TABLE_SLOT_HOLE")
        require(entry["index"] == prev["index"] + 1, "LATE_TABLE_INDEX_DRIFT")
    targets = [entry["target_va"] for entry in entries]
    duplicates = sorted({t for t in targets if targets.count(t) > 1})
    require(not duplicates, f"LATE_TABLE_TARGET_NOT_UNIQUE:{[hex(v) for v in duplicates]}")
    first = entries[0]
    require(first["symbol"] == FROZEN_INDEX0["symbol"], "LATE_FIRST_ENTRY_SYMBOL_DRIFT")
    require(first["entry_va"] == FROZEN_INDEX0["entry_va"], "LATE_FIRST_TABLE_VA_DRIFT")
    require(first["entry_image_offset"] == FROZEN_INDEX0["entry_image_offset"],
            "LATE_FIRST_TABLE_OFFSET_DRIFT")
    require(first["entry_word"] == hex(FROZEN_INDEX0["entry_word"]), "LATE_FIRST_WORD_DRIFT")
    require(first["relative"] == FROZEN_INDEX0["relative"], "LATE_FIRST_RELATIVE_DRIFT")
    require(first["target_va"] == FROZEN_INDEX0["target_va"], "LATE_FIRST_TARGET_VA_DRIFT")
    return entries


def containing_section(target_va, sections):
    hits = [s for s in sections if s["vma"] <= target_va < s["vma"] + s["size"]]
    require(len(hits) == 1, f"TARGET_SECTION_AMBIGUOUS:{hex(target_va)}")
    return hits[0]


def check_index0_runtime_identity(entry, entry_word0):
    """Frozen identity fields only observable from the binary and source tree."""
    require(entry["function_size"] == FROZEN_INDEX0["function_size"],
            "LATE_INDEX0_FUNCTION_SIZE_DRIFT")
    require(entry_word0 == 0xD503233F, "LATE_INDEX0_ENTRY_PAD_DRIFT")
    require(entry["registration"] == FROZEN_INDEX0["registration"],
            "LATE_INDEX0_REGISTRATION_DRIFT")
    require(entry["source"] == FROZEN_INDEX0["source"], "LATE_INDEX0_SOURCE_DRIFT")
    require(entry["registration_type"] == "late_initcall", "LATE_INDEX0_MACRO_DRIFT")
    return entry


def classify_registration(entry, registrations):
    """Strict late-initcall classification; tolerant record for the map."""
    hits = []
    for alias in entry["aliases"]:
        hits.extend({**rec, "alias": alias} for rec in registrations.get(alias, []))
    if not hits:
        return {"registration_type": None, "registration": None, "source": None,
                "registration_hits": []}
    macros = {hit["macro"] for hit in hits}
    sources = {hit["source"] for hit in hits}
    if len(macros) != 1 or len(sources) != 1:
        return {"registration_type": None, "registration": None, "source": None,
                "registration_hits": sorted({f"{h['macro']}:{h['source']}" for h in hits})}
    chosen = hits[0]
    return {"registration_type": chosen["macro"],
            "registration": f"{chosen['macro']}({chosen['alias']})",
            "source": chosen["source"], "registration_hits": []}


def build_map_entries(entries, sections, extent_of, registrations):
    """Enrich decoded span entries with function size, section, registration."""
    targets = [entry["target_va"] for entry in entries]
    enriched = []
    for entry in entries:
        target = entry["target_va"]
        function_size = extent_of(target) - target
        section = containing_section(target, sections)
        classification = classify_registration(entry, registrations)
        enriched.append({**entry, "function_size": function_size,
                         "section": section["name"],
                         "init_text": section["name"] == ".init.text",
                         "target_unique": targets.count(target) == 1,
                         **classification})
    check_continuity(enriched)
    for entry in enriched:
        require(entry["function_size"] > 0, f"LATE_TARGET_EMPTY:{entry['index']}")
    return enriched


def audit_candidate(entry, ctx):
    """Full probe-safety audit of one late entry; PASS/FAIL per gate."""
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
    for gate in GATES:
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
            elif gate == "ENTRY_PAD":
                require(record["entry_pad"] is not None, "ENTRY_NOT_PACIASP_OR_BTI")
            elif gate == "WINDOW_FIT":
                min_probe = min_probe_for(size)
                record["min_probe"] = min_probe
                record["core_size"] = 56 if min_probe >= 60 else 52
                record["probe_architecture"] = CORE_56 if min_probe >= 60 else CORE_52
                prelim = cp.branch_audit(ctx["frozen"][:ctx["image_len"]], ctx["ranges"],
                                         ctx["text_va"], (target, target + size),
                                         (target, target + min_probe))
                window = cp.derive_inline_window(target, size, prelim["internal_branches"],
                                                 min_probe)
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
                    overlap = {tag: sorted({v for v in sites if target <= v < target + window})
                               for tag, sites in ctx["rw_sites"].items()}
                    bad = {tag: sites for tag, sites in overlap.items() if sites}
                    require(not bad, f"REWRITE_OVERLAP:{sorted(bad)}")
                    record["runtime_rewrite_overlap"] = {tag: len(sites) for tag, sites
                                                         in overlap.items()}
                elif gate == "IMAGE_GEOMETRY":
                    cp.t3.gate_window_inside_image_size(offset, window, ctx["image_size"])
            gates[gate] = "PASS"
        except (ValueError, SystemExit) as exc:
            gates[gate] = f"FAIL:{exc}"
            record["fail_reasons"].append(str(exc))
    record["PASS"] = all(value == "PASS" for value in gates.values())
    return record


def select_targets(entries, ctx):
    """Nominal MID/LOW/HIGH with nearest-safe fallback; deviation reasons recorded."""
    require(len(entries) == SPAN_COUNT, "SELECTION_SPAN_COUNT_DRIFT")
    selections = {}
    for family, label, nominal in FAMILIES:
        skipped = []
        chosen = None
        for index in candidate_ordering(nominal, len(entries)):
            record = audit_candidate(entries[index], ctx)
            if record["PASS"]:
                chosen = record
                break
            skipped.append({"index": index, "symbol": record["symbol"],
                            "function_size": record["function_size"],
                            "section": record["section"], "gates": record["gates"],
                            "reason": (";".join(record["fail_reasons"])
                                       or "GATE_FAILED")})
        require(chosen is not None, f"{label}_NO_SAFE_INLINE_TARGET")
        deviation = None if chosen["index"] == nominal else {
            "nominal_index": nominal, "nominal_symbol": entries[nominal]["symbol"],
            "chosen_index": chosen["index"], "distance": abs(chosen["index"] - nominal),
            "reason": next(row["reason"] for row in skipped if row["index"] == nominal)
            if any(row["index"] == nominal for row in skipped) else "NOMINAL_NOT_AUDITED"}
        selections[family] = {"family": family, "label": label, "nominal_index": nominal,
                              "selected_index": chosen["index"],
                              "deviation": deviation, "skipped": skipped,
                              "audit": chosen}
    cp.require_disjoint_windows(
        [(int(selections[family]["audit"]["target_va"], 16),
          int(selections[family]["audit"]["target_va"], 16)
          + selections[family]["audit"]["window"]) for family, _, _ in FAMILIES])
    return selections


def compose_member(frozen, offset, window, entry_word, core, delay):
    """Entry-pad-preserving inline probe payload for one delay constant."""
    pad = struct.pack("<I", entry_word)
    probe = cp.pad_probe(pad + cp.delay_core(core, delay), window)
    require(probe[:4] == pad and probe[4:4 + len(core)] == cp.delay_core(core, delay),
            "PROBE_LAYOUT_DRIFT")
    return probe, cp.patch_window(frozen, offset, probe)


def assert_pair_delay_only(changed, offset, core_size):
    slot = 8 if core_size == 56 else 4
    require(changed == [offset + 4 + slot + 1, offset + 4 + slot + 2],
            f"PAIR_NOT_DELAY_CONSTANT_ONLY:{changed}")


def window_agreement(image, frozen, text_va, offset, window):
    """Bundle Image vs frozen inside the window: EXACT or proven literal deltas."""
    differences = [{"offset": hex(i), "bundle": hex(struct.unpack_from("<I", image, i)[0]),
                    "frozen": hex(struct.unpack_from("<I", frozen, i)[0])}
                   for i in range(offset, offset + window, 4)
                   if image[i:i + 4] != frozen[i:i + 4]]
    agreement = {"offset": hex(offset), "size": window, "differing_words": differences}
    if not differences:
        agreement["verdict"] = "EXACT"
        return agreement
    agreement["layout_literal_refs"] = cp.prove_fs_complete_window_literals(
        image, frozen, text_va, offset, window)
    agreement["verdict"] = "LAYOUT_LITERAL_ADDRESS_DELTA_VERIFIED"
    return agreement


def build_pairs(args, selections, ctx, metadata, out):
    """One DELAY_CONSTANT_ONLY payload pair per family from the frozen FIX8 base."""
    image_size = ctx["image_size"]
    dtb_offset, _ = cp.pb.calc_dtb_offset(image_size)
    cp.pb.gate_rt_d(ctx["frozen"][dtb_offset:])
    names = {}
    for family, label, _nominal in FAMILIES:
        selection = selections[family]
        audit = selection["audit"]
        target = int(audit["target_va"], 16)
        offset = target - ctx["text_va"]
        window = audit["window"]
        core_size = audit["core_size"]
        require(core_size in (52, 56), "UNEXPECTED_CORE_SIZE")
        core, _words = core_bytes(args.core56.read_bytes(), 56) if core_size == 56 else \
            core_bytes(args.core52.read_bytes(), 52)
        entry_word = int(audit["entry_pad_word"], 16)
        section = cp.t3.gate_window_section_scan(target, window, ctx["sections"])
        require(cp.t3.sysmap_symbol(args.bundle / "System.map", audit["symbol"]) == target,
                "SYMBOL_MAP_MISMATCH")
        family_dir = out / family
        family_dir.mkdir(parents=True, exist_ok=False)
        rewrites = cp.audit_rewrites(family_dir, args.bundle / "vmlinux", ctx["sections"],
                                     (target, target + window))
        (family_dir / "original-function.txt").write_text(
            cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={target:#x}",
                       f"--stop-address={target + audit['function_size']:#x}",
                       str(args.bundle / "vmlinux")]))
        (family_dir / "original-window.txt").write_text(
            cp.pb.run([cp.TOOLS["objdump"], "-d", f"--start-address={target:#x}",
                       f"--stop-address={target + window:#x}",
                       str(args.bundle / "vmlinux")]))
        agreement = window_agreement(ctx["image"], ctx["frozen"], ctx["text_va"],
                                     offset, window)
        write_json(family_dir / "window-agreement.json", agreement)
        audit.update({"entry_audit": "PASS", "incoming_branch_gate": "PASS",
                      "function_range_safe": True, "runtime_rewrite_safe": True,
                      "relocations_in_window": 0, "inline_only": True,
                      "trampoline_permitted": False, "window_derivation": "TARGET_CFG",
                      "window_agreement": agreement["verdict"]})
        write_json(family_dir / "target-entry-audit.json", audit)
        boundary = cp.level7_span_entry_as_boundary(
            {key: entry for key, entry in
             zip(("index", "entry_va", "entry_va_hex", "entry_image_offset", "entry_word",
                  "relative", "target_va", "target_va_hex", "aliases", "symbol"),
                 (audit["index"], int(audit["table_entry_va"], 16),
                  audit["table_entry_va"], int(audit["table_entry_image_offset"], 16),
                  audit["entry_word"], audit["relative"], target, audit["target_va"],
                  audit["aliases"], audit["symbol"]))})
        payloads = {}
        shas = {}
        for delay in (8, 1):
            directory = family_dir / "pair" / str(delay) / "checkpoint"
            directory.mkdir(parents=True, exist_ok=False)
            probe, payload = compose_member(ctx["frozen"], offset, window, entry_word,
                                            core, delay)
            require(payload[:offset] == ctx["frozen"][:offset]
                    and payload[offset + window:] == ctx["frozen"][offset + window:],
                    "MEMBER_CHANGED_OUTSIDE_WINDOW")
            require(payload[offset:offset + window] == probe, "MEMBER_WINDOW_DRIFT")
            cp.t3.gate_tramp_identity(payload)
            cp.pb.gate_rt_d(payload[dtb_offset:])
            table_slot = int(audit["table_entry_image_offset"], 16)
            require(payload[table_slot:table_slot + 4]
                    == ctx["frozen"][table_slot:table_slot + 4], "PREL32_TARGET_REWRITTEN")
            manifest = {"symbol": family, "family": family, "target_symbol": audit["symbol"],
                        "target_aliases": audit["aliases"], "target_va": audit["target_va"],
                        "target_image_offset": audit["image_offset"],
                        "offset": offset, "checkpoint_size": window, "core_size": core_size,
                        "entry": audit["entry_pad"], "entry_pad_word": audit["entry_pad_word"],
                        "pac": audit["pac"], "bti": audit["bti"], "section": section["name"],
                        "initcall_boundary": boundary,
                        "initcall_registration": audit["registration"],
                        "registration_type": audit["registration_type"],
                        "target_source": audit["source"],
                        "target_function_size": audit["function_size"],
                        "target_entry_audit": audit,
                        "span_index": audit["index"],
                        "nominal_index": selection["nominal_index"],
                        "deviation": selection["deviation"],
                        "core_variant": ("ultracompact_cntpct_elapsed_b_lo"
                                         if core_size == 56 else
                                         "subsys52_cntpct_elapsed_b_lo"),
                        "probe_architecture": audit["probe_architecture"],
                        "core_sha256": cp.digest(core), "delay_seconds": delay,
                        "payload_size": len(payload), "payload_sha256": cp.digest(payload),
                        "checkpoint_sha256": cp.digest(probe),
                        "frozen_sha256": cp.digest(ctx["frozen"]),
                        "prel32_target_unchanged": True, "cfg_closure": audit["cfg_closure"],
                        "runtime_rewrites": rewrites, "window_agreement": agreement,
                        "window_derivation": "TARGET_CFG", "inline_only": True,
                        "trampoline_permitted": False, "stage": STAGE,
                        "bundle_run": BUNDLE_RUN, "bundle": metadata,
                        "source_commit": os.environ["GITHUB_SHA"],
                        "run_id": os.environ["GITHUB_RUN_ID"],
                        "positive_proves": PROOF[family][0],
                        "positive_does_not_prove": PROOF[family][1],
                        "normal_boot_candidate": False, "kernel_rebuilt": False,
                        "device_operation": False, "private_pack": False}
            (directory / "payload.bin").write_bytes(payload)
            (directory / "checkpoint.bin").write_bytes(probe)
            write_json(directory / "manifest.json", manifest)
            payloads[delay] = payload
            shas[delay] = cp.digest(payload)
        changed = [i for i, (a, b) in enumerate(zip(payloads[8], payloads[1])) if a != b]
        assert_pair_delay_only(changed, offset, core_size)
        identity = {"stage": STAGE, "family": family,
                    "delay8_name": f"LATE_{label}8", "delay1_name": f"LATE_{label}1",
                    "bundle_run": BUNDLE_RUN, "source_commit": os.environ["GITHUB_SHA"],
                    "public_run": os.environ["GITHUB_RUN_ID"],
                    "delay8_payload_sha256": shas[8], "delay1_payload_sha256": shas[1],
                    "changed_offsets": changed, "expected_delta_seconds": -7.0,
                    "strong_error_seconds": 1.0, "supported_error_seconds": 2.0,
                    "attribution": "DELAY_CONSTANT_ONLY", "span_index": audit["index"],
                    "selected_index": audit["index"], "nominal_index": selection["nominal_index"],
                    "deviation": selection["deviation"], "target_symbol": audit["symbol"],
                    "target_va": audit["target_va"], "probe_architecture":
                    audit["probe_architecture"], "window": window, "core_size": core_size,
                    "private_pack": False, "device_operation": False, "kernel_rebuilt": False}
        write_json(family_dir / "pair" / "pair.json", identity)
        names[family] = {"label": label, "identity": identity, "audit": audit,
                         "selection": selection, "offset": offset, "window": window,
                         "core_size": core_size, "shas": shas, "changed": changed}
    return names


def enumerate_level7(bundle, frozen, out):
    """Re-derive the authoritative late span map from the bundle vmlinux."""
    metadata = json.loads((bundle / "bundle.json").read_text())
    require(metadata["linux_base"] == cp.pb.LINUX_BASE, "BUNDLE_LINUX_PIN_DRIFT")
    require(metadata["patch_queue_sha256"] == cp.pb.PATCH_QUEUE_SHA, "BUNDLE_PATCH_QUEUE_DRIFT")
    require(metadata["files"]["vmlinux"] == ELF_SHA, "BUNDLE_NOT_RECONCILED_ELF")
    for name in ("Image", "vmlinux", "System.map", "kernel.config"):
        require(cp.digest((bundle / name).read_bytes()) == metadata["files"][name],
                f"BUNDLE_IDENTITY_MISMATCH:{name}")
    require(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    image = (bundle / "Image").read_bytes()
    require(len(image) == cp.t3.FIX8_IMAGE_FILE_SIZE, "BUNDLE_IMAGE_SIZE_DRIFT")
    vmlinux = bundle / "vmlinux"
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    require(cp.t3.nm_symbol(nm, "_text") == TEXT_VA, "TEXT_VA_DRIFT")
    require(cp.t3.nm_symbol(nm, SPAN_BEGIN) == FROZEN_INDEX0["entry_va"],
            "LATE_SPAN_BEGIN_VA_DRIFT")
    sections = cp.t3.section_map(out, cp.TOOLS, vmlinux)
    late_start = cp.t3.nm_symbol(nm, SPAN_BEGIN)
    late_end = cp.t3.nm_symbol(nm, SPAN_END)
    require(late_end > late_start and not late_end & 3, "LATE_SPAN_END_INVALID")
    entries = cp.decode_initcall_span(vmlinux, sections, nm, late_start, late_end)
    check_continuity(entries)
    symbol_vas = sorted({va for va, _ in cp.t3.symbol_table(nm)})
    registrations = cp.index_initcall_registrations(cp.pb.LINUX)
    enriched = build_map_entries(entries, sections,
                                 lambda target: symbol_vas[
                                     bisect.bisect_right(symbol_vas, target)],
                                 registrations)
    cfg = cp.t3.config_symbols((bundle / "kernel.config").read_text())
    cp.t3.gate_instrumentation_audit(cfg, "paciasp", 0xD503233F)
    check_index0_runtime_identity(
        enriched[0],
        struct.unpack_from("<I", frozen, FROZEN_INDEX0["target_image_offset"])[0])
    image_size = cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    ranges = [(s["vma"] - TEXT_VA, s["vma"] - TEXT_VA + s["size"])
              for s in sections if s["code"] and s["alloc"]]
    rw_sites = {}
    for name, tag, decoder in cp.t3.RUNTIME_REWRITE_SECTIONS:
        sec = next((s for s in sections if s["name"] == name), None)
        rw_sites[tag] = (decoder(cp.section_bytes(vmlinux, sec), sec["vma"])
                         if sec is not None else [])
    reloc_sites = cp.relocation_sites(vmlinux, sections)
    ctx = {"frozen": frozen, "image": image, "image_len": len(image), "text_va": TEXT_VA,
           "sections": sections, "ranges": ranges, "symbol_vas": symbol_vas,
           "rw_sites": rw_sites, "reloc_sites": reloc_sites, "image_size": image_size,
           "cfg": cfg}
    require(cp.digest(vmlinux.read_bytes()) == metadata["files"]["vmlinux"],
            "AUDIT_MUTATED_ELF")
    return metadata, entries, enriched, ctx


def summary_kv(names, enriched, map_stats):
    lines = [f"LATE_LEVEL_STAGE={STAGE}", "LATE_SPAN=__initcall7_start..__initcall_end",
             f"LATE_TABLE_ENTRY_COUNT={len(enriched)}",
             f"LATE_TABLE_INDEX0_SYMBOL={FROZEN_INDEX0['symbol']}",
             f"LATE_TABLE_INDEX0_TABLE_VA={hex(FROZEN_INDEX0['entry_va'])}",
             f"LATE_TABLE_INDEX0_TARGET_VA={hex(FROZEN_INDEX0['target_va'])}",
             f"LATE_TABLE_INDEX0_WORD={hex(FROZEN_INDEX0['entry_word'])}",
             f"LATE_TABLE_INDEX0_FUNCTION_SIZE={FROZEN_INDEX0['function_size']}",
             f"LATE_MAP_IN_INIT_TEXT={map_stats['init_text']}",
             f"LATE_MAP_TEXT_SECTION_ENTRIES={map_stats['text_section']}"]
    for family, label, nominal in FAMILIES:
        info = names[family]
        audit = info["audit"]
        prefix = f"LATE_{label}"
        lines += [f"{prefix}_NOMINAL_INDEX={nominal}",
                  f"{prefix}_INDEX={audit['index']}",
                  f"{prefix}_SYMBOL={audit['symbol']}",
                  f"{prefix}_TABLE_VA={audit['table_entry_va']}",
                  f"{prefix}_TARGET_VA={audit['target_va']}",
                  f"{prefix}_IMAGE_OFFSET={audit['image_offset']}",
                  f"{prefix}_FUNCTION_SIZE={audit['function_size']}",
                  f"{prefix}_WINDOW={audit['window']}",
                  f"{prefix}_CORE_SIZE={audit['core_size']}",
                  f"{prefix}_PROBE_ARCHITECTURE={audit['probe_architecture']}",
                  f"{prefix}_ENTRY_PAD={audit['entry_pad']}",
                  f"{prefix}_REGISTRATION={audit['registration']}",
                  f"{prefix}_SOURCE={audit['source']}",
                  f"{prefix}_DEVIATION=" + (
                      "NONE" if info["selection"]["deviation"] is None else
                      f"{info['selection']['deviation']['reason']}@distance="
                      f"{info['selection']['deviation']['distance']}"),
                  f"{prefix}8_PAYLOAD_SHA={info['shas'][8]}",
                  f"{prefix}1_PAYLOAD_SHA={info['shas'][1]}",
                  f"{prefix}_PAIR_DIFF_OFFSETS={info['changed']}",
                  f"{prefix}_PAIR=PASS"]
    lines += ["PAIR_DIFF=DELAY_CONSTANT_ONLY", "INLINE_ONLY=YES",
              "TRAMPOLINE_PERMITTED=NO", "ISLAND_PERMITTED=NO",
              "PREL32_TARGET_UNCHANGED=YES", "SHARED_CHECKPOINT=NO",
              "CROSS_FUNCTION_OVERWRITE=NO", "WINDOW_DERIVATION=TARGET_CFG",
              "KERNEL_REBUILD=NO", "DEVICE_OPERATION=NO", "PRIVATE_PACK=NO",
              "PARTITION_WRITES=0", "SLOT_A_WRITTEN=NO", "LOCAL_BUILD=NO"]
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "frozen", "core56", "core52", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    frozen = args.frozen.read_bytes()
    core_bytes(args.core56.read_bytes(), 56)
    core_bytes(args.core52.read_bytes(), 52)
    core56 = cp.ultracompact_core(args.core56.read_bytes())
    core52 = cp.subsys52_core(args.core52.read_bytes())
    cp.gate_subsys52_core_equivalence(core56, core52)
    metadata, raw_entries, enriched, ctx = enumerate_level7(args.bundle, frozen, out)
    map_stats = {"init_text": sum(1 for e in enriched if e["init_text"]),
                 "text_section": sum(1 for e in enriched if not e["init_text"])}
    selections = select_targets(enriched, ctx)
    write_json(out / "late-map.json", {
        "stage": STAGE, "bundle_run": BUNDLE_RUN, "span": [SPAN_BEGIN, SPAN_END],
        "entry_count": len(enriched),
        "index0_identity": FROZEN_INDEX0, "entries": enriched})
    write_json(out / "selection.json", selections)
    names = build_pairs(args, selections, ctx, metadata, out)
    require(cp.digest((args.bundle / "vmlinux").read_bytes()) == metadata["files"]["vmlinux"],
            "AUDIT_MUTATED_ELF")
    require(frozen == args.frozen.read_bytes(), "AUDIT_MUTATED_FROZEN")
    lines = summary_kv(names, enriched, map_stats)
    (out / "audit-summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"{STAGE}_PAIR_AUDIT=PASS", flush=True)


if __name__ == "__main__":
    main()
