#!/usr/bin/env python3
"""Post-43 late (level-7) safe-advance inline pairs (MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_POST43_SAFE_ADVANCE_CI).

GitHub Actions only. Re-derives the 86-entry late span from the authoritative
bundle vmlinux, selects the post-43 safe-advance target (nominal 53 = (43+63)//2)
plus its two dynamically derived bisection children under the full inline
probe-safety gate set and the round pad-class gate (paciasp entries only: bti c
pads have no device-proven precedent), re-audits the frozen LATE_HIGH8 target
(index 63) with the extended window-reference forensic, and composes one
DELAY_CONSTANT_ONLY kernel payload pair per family from the frozen FIX8 base.
Frozen late targets (0/21/43/63), all frozen probe windows and all frozen
payload identities are excluded. Trampolines, islands, PREL32 retargeting,
shared do_initcall* checkpoints and cross-function overwrite remain forbidden.
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

STAGE = "MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_POST43_SAFE_ADVANCE_CI"
NOMINAL_POST43 = 53  # (43 + 63) // 2, user-frozen round nominal
TARGET_FAMILY = ("late_post43", "POST43", NOMINAL_POST43)
CHILD_FAMILIES = (("late_post49", "POST49"), ("late_post60", "POST60"))
ROUND_PAD_GATE = "ROUND_PAD_CLASS"
ROUND_PAD_REASON = "BTI_C_PAD_EXCLUDED_ROUND_REQUIRES_PACIASP"
FROZEN_LATE_INDICES = (0, 21, 43, 63)
FROZEN_LATE_WINDOWS = ((0xFFFF800081B32078, 60), (0xFFFF800081B47510, 60),
                       (0xFFFF800081B5BD1C, 60), (0xFFFF800081BAA15C, 60))
FROZEN_HISTORICAL_WINDOWS = (
    (0xFFFF800081B346FC, 160),  # ARCH topology_init
    (0xFFFF8000800149E0, 56),   # SUBSYS create_debug_debugfs_entry
    (0xFFFF800081B347B8, 8),    # FS register_arm64_panic_block entry word
    (0xFFFF800081B8CD40, 56),   # UPPER chr_dev_init
    (0xFFFF800081BAE798, 60),   # POST39 af_unix_init
    (0xFFFF800081BAEDFC, 60),   # POST46
    (0xFFFF800081B6B2FC, 60),   # POST49 (fs level)
    (0xFFFF800081B32388, 60),   # POST51
    (0xFFFF800081B34D8C, 60),   # DEVPROBE cpuinfo_regs_init
    (0xFFFF800081B3113C, 56),   # WAITENTRY late_complete
    (0xFFFF800081B31140, 52),   # WAITRET
)
FROZEN_PAYLOAD_SHAS = (
    "8cfc9150534e4cb1e6e0ff9dbe2f346014b321e9d1a41eba547efcc8c6fa563a",
    "cc1e67f408044da6673cb94628abfa911e065ce3af95ef9a86aab21a4b26b247",
    "a36cf28fc9cd8a4d1bdfe93ad31c403bfd1d7fbfaa2a9abf9142c331d28b659d",
    "40b71779527dc2ae03cd900f3c6ad8a81d841c04144abfcc96a7652b12d96fb1",
    "c9f160597287666b73004db604c1525786eca5daef2e6fc7d43a647d2896be2d",
    "c4c4115940159c138ee7742473fc09b852eaeb06e7b81c1e208787edb644a67d",
)
HIGH8_INDEX = 63
HIGH8_SYMBOL = "bpf_kfunc_init"
HIGH8_TARGET_VA = 0xFFFF800081BAA15C
PROOF = {
    "late_post43": ("the selected post-43 safe-advance late initcall entry was "
                    "reached after all earlier late initcalls",
                    "the target late initcall body, later late initcalls, "
                    "console or /init"),
    "late_post49": ("the lower-bisection child late initcall entry was reached "
                    "after the earlier late initcalls",
                    "the target late initcall body, later late initcalls, "
                    "console or /init"),
    "late_post60": ("the upper-bisection child late initcall entry was reached "
                    "after the earlier late initcalls",
                    "the target late initcall body, later late initcalls, "
                    "console or /init"),
}


def require(condition, message):
    cp.require(condition, message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def audit_candidate_round(entry, ctx):
    """The frozen 15-gate audit plus the round pad-class gate (paciasp only)."""
    record = base.audit_candidate(entry, ctx)
    try:
        require(record["entry_pad"] == "paciasp", ROUND_PAD_REASON)
        record["gates"][ROUND_PAD_GATE] = "PASS"
    except (ValueError, SystemExit) as exc:
        record["gates"][ROUND_PAD_GATE] = f"FAIL:{exc}"
        record["fail_reasons"].append(str(exc))
    record["PASS"] = record["PASS"] and record["gates"][ROUND_PAD_GATE] == "PASS"
    return record


def frozen_window_overlap(target, window):
    for va, size in FROZEN_LATE_WINDOWS + FROZEN_HISTORICAL_WINDOWS:
        if target < va + size and va < target + window:
            return (va, size)
    return None


def select_one(entries, ctx, family, label, nominal):
    """Nearest-safe fallback under frozen-index/frozen-window exclusions."""
    require(0 <= nominal < len(entries), "NOMINAL_INDEX_OUT_OF_SPAN")
    skipped = []
    chosen = None
    for index in base.candidate_ordering(nominal, len(entries)):
        if index in FROZEN_LATE_INDICES:
            skipped.append({"index": index, "symbol": entries[index]["symbol"],
                            "function_size": entries[index]["function_size"],
                            "section": entries[index]["section"], "gates": {},
                            "reason": "FROZEN_TARGET_INDEX"})
            continue
        record = audit_candidate_round(entries[index], ctx)
        overlap = None
        if record["PASS"]:
            overlap = frozen_window_overlap(int(record["target_va"], 16),
                                            record["window"])
        if record["PASS"] and overlap is None:
            chosen = record
            break
        if overlap is not None:
            record["gates"][ROUND_PAD_GATE] = record["gates"].get(ROUND_PAD_GATE, "PASS")
            record["fail_reasons"].append(
                f"FROZEN_WINDOW_OVERLAP:{hex(overlap[0])}+{overlap[1]}")
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
    return {"family": family, "label": label, "nominal_index": nominal,
            "selected_index": chosen["index"], "deviation": deviation,
            "skipped": skipped, "audit": chosen}


def select_targets(entries, ctx):
    """POST43 target then its two dynamically derived bisection children."""
    require(len(entries) == base.SPAN_COUNT, "SELECTION_SPAN_COUNT_DRIFT")
    selections = {}
    selections[TARGET_FAMILY[0]] = select_one(entries, ctx, *TARGET_FAMILY)
    selected = selections[TARGET_FAMILY[0]]["selected_index"]
    require(43 < selected < HIGH8_INDEX, "POST43_TARGET_NOT_IN_43_63")
    child_nominals = ((43 + selected) // 2, (selected + HIGH8_INDEX) // 2)
    for (family, label), nominal in zip(CHILD_FAMILIES, child_nominals):
        selections[family] = select_one(entries, ctx, family, label, nominal)
        selections[family]["child_nominal_derivation"] = {
            "target_index": selected, "bound": "lower" if family == "late_post49"
            else "upper", "formula": ("(43 + target) // 2" if family == "late_post49"
                                      else "(target + 63) // 2")}
    require(43 < selections["late_post49"]["selected_index"] < selected,
            "POST49_TARGET_NOT_IN_LOWER_HALF")
    require(selected < selections["late_post60"]["selected_index"] < HIGH8_INDEX,
            "POST60_TARGET_NOT_BELOW_63")
    cp.require_disjoint_windows(
        [(int(selections[family]["audit"]["target_va"], 16),
          int(selections[family]["audit"]["target_va"], 16)
          + selections[family]["audit"]["window"]) for family, _, _ in family_specs()])
    return selections, child_nominals


def require_fresh_payload(payload_sha):
    """No composed member may reproduce any frozen payload identity."""
    require(payload_sha not in FROZEN_PAYLOAD_SHAS, "RERUN_FORBIDDEN_FROZEN_PAYLOAD")


def family_specs():
    return (TARGET_FAMILY,) + tuple((family, label, 0)
                                    for family, label in CHILD_FAMILIES)


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def relr_sites(blob, vma):
    """Decode SHT_RELR relocation sites (even=address, odd=bitmap of next 63)."""
    sites = []
    addr = None
    for i in range(0, len(blob) - 7, 8):
        word = struct.unpack_from("<Q", blob, i)[0]
        if word & 1:
            require(addr is not None, "RELR_BITMAP_BEFORE_BASE")
            for bit in range(63):
                if (word >> 1) & (1 << bit):
                    sites.append(addr + 8 + 8 * bit)
        else:
            addr = word
            sites.append(addr)
    return sites


def table_section_scans(table_sections, target, window):
    """Extended runtime-rewrite fields (G1/G2/G3/G6/G7).

    Every 32-bit field is resolved under BOTH the field-relative and the
    enclosing-entry-relative base conventions (a conservative superset: the
    expected result is zero hits under either interpretation)."""
    hits = {name: [] for name in ("ex_table", "altinstructions_orig",
                                  "altinstructions_alt", "bug_table", "got",
                                  "got_plt", "init_array", "rela_dyn_offset",
                                  "rela_dyn_addend", "jump_table",
                                  "static_call_sites", "kcfi_traps",
                                  "patchable_function_entries", "mcount_loc",
                                  "relr_dyn")}
    relr_total = 0

    def field_hit(base, word):
        va = base + signed(word, 32)
        return hex(va) if target <= va < target + window else None

    for section in table_sections:
        name, vma, blob = section["name"], section["vma"], section["bytes"]
        if not blob:
            continue
        if name == "__ex_table":
            for i in range(0, len(blob) - 11, 12):
                for at in (i, i + 4, i + 8):
                    hit = field_hit(vma + at, struct.unpack_from("<I", blob, at)[0])
                    if hit:
                        hits["ex_table"].append(hit)
        elif name == ".altinstructions":
            for i in range(0, len(blob) - 11, 12):
                for tag, at, bases in (("altinstructions_orig", i, (vma + i,)),
                                       ("altinstructions_alt", i + 4,
                                        (vma + i + 4, vma + i))):
                    for base in bases:
                        hit = field_hit(base, struct.unpack_from("<I", blob, at)[0])
                        if hit:
                            hits[tag].append(hit)
        elif name in ("__bug_table", "__jump_table", ".static_call_sites",
                      ".kcfi_traps", "__patchable_function_entries",
                      "__mcount_loc"):
            tag = name.lstrip("_").lstrip(".")
            for i in range(0, len(blob) - 3, 4):
                word = struct.unpack_from("<I", blob, i)[0]
                for base in (vma + i, vma + (i & ~7)):
                    hit = field_hit(base, word)
                    if hit:
                        hits[tag].append(hex(vma + i) + ":" + hit)
                if word & 0xFFFFFFFF in (target & 0xFFFFFFFF,
                                         (target + window - 1) & 0xFFFFFFFF):
                    hits[tag].append(hex(vma + i) + ":abs")
        elif name in (".got", ".got.plt", ".init_array"):
            tag = name.lstrip(".")
            for i in range(0, len(blob) - 7, 8):
                va = struct.unpack_from("<Q", blob, i)[0]
                if target <= va < target + window:
                    hits[tag].append(hex(va))
        elif name == ".rela.dyn":
            for i in range(0, len(blob) - 23, 24):
                offset, _info, addend = struct.unpack_from("<QQq", blob, i)
                if target <= offset < target + window:
                    hits["rela_dyn_offset"].append(hex(offset))
                if target <= addend < target + window:
                    hits["rela_dyn_addend"].append(hex(addend))
        elif name == ".relr.dyn":
            sites = relr_sites(blob, vma)
            relr_total = len(sites)
            hits["relr_dyn"] = [hex(va) for va in sites
                                if target <= va < target + window]
    hits["relr_sites_total"] = relr_total
    return hits


def adrp_add_scan(image, text_va, ranges, target, window):
    """G5: surviving adrp(+add) pairs forming an address inside the window."""
    hits = []
    interior = (target + 4, target + window)
    for lo, hi in ranges:
        hi = min(hi, len(image) - 7)
        for off in range(lo, hi, 4):
            pc = text_va + off
            if target <= pc < target + window:
                continue
            word = struct.unpack_from("<I", image, off)[0]
            if (word >> 24) & 0x9F != 0x90:
                continue
            immlo = (word >> 29) & 0x3
            immhi = (word >> 5) & 0x7FFFF
            imm = signed((immhi << 2) | immlo, 21)
            page = (pc & ~0xFFF) + (imm << 12)
            rd = word & 0x1F
            nxt = struct.unpack_from("<I", image, off + 4)[0]
            if (nxt >> 24) != 0x91 or (nxt & 0x1F) != rd \
                    or ((nxt >> 5) & 0x1F) != rd:
                continue
            imm12 = (nxt >> 10) & 0xFFF
            if (nxt >> 22) & 1:
                imm12 <<= 12
            addr = page + imm12
            if interior[0] <= addr < interior[1]:
                hits.append(hex(addr))
    return hits


def relative_reference_scan(image, text_va, target, window, slot_offset,
                            symbols):
    """G4: 4-byte data references resolving into the window.

    The candidate's own initcall PREL32 slot must be the only non-kallsyms
    site; kallsyms_* regions hold compressed data whose words may coincidentally
    resolve anywhere and are recorded as excluded, never silently dropped.
    """
    sites, excluded = [], []
    for off in range(0, len(image) - 3, 4):
        value = struct.unpack_from("<I", image, off)[0]
        va = text_va + off + signed(value, 32)
        if target <= va < target + window:
            sites.append(off)
    kept, slot_present = [], False
    for off in sites:
        if off == slot_offset:
            slot_present = True
            kept.append({"offset": hex(off), "role": "initcall_table_slot"})
            continue
        site_va = text_va + off
        idx = bisect.bisect_right([va for va, _ in symbols], site_va) - 1
        enclosing = symbols[idx][1] if idx >= 0 else "<none>"
        if enclosing.startswith("kallsyms_"):
            excluded.append({"offset": hex(off), "enclosing_symbol": enclosing})
            continue
        kept.append({"offset": hex(off), "enclosing_symbol": enclosing,
                     "role": "UNEXPECTED"})
    return {"sites": kept, "excluded_kallsyms": excluded,
            "slot_present": slot_present}


def window_reference_forensic(image, text_va, ranges, table_sections, symbols,
                              target, window, slot_offset):
    """Extended window-reference audit closing the HIGH8 gap classes G1-G7."""
    tables = table_section_scans(table_sections, target, window)
    bad_tables = {key: value for key, value in tables.items()
                  if key != "relr_sites_total" and value}
    require(not bad_tables, f"WINDOW_REFERENCE_TABLE_HIT:{sorted(bad_tables)}")
    adrp_hits = adrp_add_scan(image, text_va, ranges, target, window)
    require(not adrp_hits, f"WINDOW_REFERENCE_ADRP_ADD_HIT:{adrp_hits}")
    relative = relative_reference_scan(image, text_va, target, window,
                                       slot_offset, symbols)
    require(relative["slot_present"], "WINDOW_REFERENCE_SLOT_MISSING")
    unexpected = [site for site in relative["sites"]
                  if site["role"] == "UNEXPECTED"]
    require(not unexpected,
            f"WINDOW_REFERENCE_DATA_HIT:{[s['offset'] for s in unexpected]}")
    return {"target_va": hex(target), "window": window, "slot_offset": hex(slot_offset),
            "table_scans": tables, "adrp_add_into_interior": adrp_hits,
            "relative_references": relative,
            "residual_not_scanned": ["unaligned_8byte_absolute_pointers"],
            "verdict": "NO_REFERENCE_INTO_WINDOW"}


def vmlinux_table_sections(vmlinux, sections):
    """Extract the runtime-rewrite-class sections from the bundle vmlinux."""
    wanted = ("__ex_table", ".altinstructions", "__bug_table", "__jump_table",
              ".static_call_sites", ".kcfi_traps", "__patchable_function_entries",
              "__mcount_loc", ".got", ".got.plt", ".init_array", ".rela.dyn",
              ".relr.dyn")
    out = []
    for name in wanted:
        section = next((s for s in sections if s["name"] == name), None)
        out.append({"name": name, "vma": section["vma"] if section else 0,
                    "bytes": cp.section_bytes(vmlinux, section)
                    if section is not None else b""})
    return out


def symbol_pairs(system_map):
    symbols = []
    for line in Path(system_map).read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                symbols.append((int(parts[0], 16), parts[2]))
            except ValueError:
                continue
    symbols.sort()
    return symbols


def high8_forensic(entries, ctx, args, out):
    """Re-audit the frozen LATE_HIGH8 target; the frozen anomaly is NOT reinterpreted."""
    entry = entries[HIGH8_INDEX]
    require(entry["symbol"] == HIGH8_SYMBOL, "HIGH8_SYMBOL_DRIFT")
    require(entry["target_va"] == HIGH8_TARGET_VA, "HIGH8_TARGET_VA_DRIFT")
    audit = audit_candidate_round(entry, ctx)
    failed = {gate: verdict for gate, verdict in audit["gates"].items()
              if verdict != "PASS"}
    require(not failed, f"HIGH8_REAUDIT_GATE_DRIFT:{failed}")
    slot = int(audit["table_entry_image_offset"], 16)
    forensic = window_reference_forensic(
        ctx["image"], ctx["text_va"], ctx["ranges"],
        vmlinux_table_sections(args.bundle / "vmlinux", ctx["sections"]),
        symbol_pairs(args.bundle / "System.map"), HIGH8_TARGET_VA,
        audit["window"], slot)
    record = {"stage": STAGE, "index": HIGH8_INDEX, "symbol": HIGH8_SYMBOL,
              "target_va": audit["target_va"], "function_size": audit["function_size"],
              "window": audit["window"], "gates": audit["gates"],
              "frozen_anomaly": "DEVICE_BEHAVIOR_ANOMALY_NOT_REINTERPRETED",
              "runtime_inference": "NONE_LICENSED",
              "forensic": forensic,
              "HIGH8_STATIC_PROBE_DEFECT_FOUND": "NO"}
    write_json(out / "high8-forensic.json", record)
    return record


def compose_member(frozen, offset, window, entry_word, core, delay):
    return base.compose_member(frozen, offset, window, entry_word, core, delay)


def build_pairs(args, selections, ctx, metadata, out):
    """One DELAY_CONSTANT_ONLY payload pair per family from the frozen FIX8 base."""
    image_size = ctx["image_size"]
    dtb_offset, _ = cp.pb.calc_dtb_offset(image_size)
    cp.pb.gate_rt_d(ctx["frozen"][dtb_offset:])
    names = {}
    for family, label, _nominal in family_specs():
        selection = selections[family]
        audit = selection["audit"]
        target = int(audit["target_va"], 16)
        offset = target - ctx["text_va"]
        window = audit["window"]
        core_size = audit["core_size"]
        require(core_size in (52, 56), "UNEXPECTED_CORE_SIZE")
        core, _words = base.core_bytes(args.core56.read_bytes(), 56) \
            if core_size == 56 else base.core_bytes(args.core52.read_bytes(), 52)
        entry_word = int(audit["entry_pad_word"], 16)
        require(audit["entry_pad"] == "paciasp", ROUND_PAD_REASON)
        section = cp.t3.gate_window_section_scan(target, window, ctx["sections"])
        require(cp.t3.sysmap_symbol(args.bundle / "System.map", audit["symbol"])
                == target, "SYMBOL_MAP_MISMATCH")
        family_dir = out / family
        family_dir.mkdir(parents=True, exist_ok=False)
        rewrites = cp.audit_rewrites(family_dir, args.bundle / "vmlinux",
                                     ctx["sections"], (target, target + window))
        (family_dir / "original-function.txt").write_text(
            cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={target:#x}",
                       f"--stop-address={target + audit['function_size']:#x}",
                       str(args.bundle / "vmlinux")]))
        (family_dir / "original-window.txt").write_text(
            cp.pb.run([cp.TOOLS["objdump"], "-d", f"--start-address={target:#x}",
                       f"--stop-address={target + window:#x}",
                       str(args.bundle / "vmlinux")]))
        agreement = base.window_agreement(ctx["image"], ctx["frozen"],
                                          ctx["text_va"], offset, window)
        write_json(family_dir / "window-agreement.json", agreement)
        forensic = window_reference_forensic(
            ctx["image"], ctx["text_va"], ctx["ranges"],
            vmlinux_table_sections(args.bundle / "vmlinux", ctx["sections"]),
            symbol_pairs(args.bundle / "System.map"), target, window,
            int(audit["table_entry_image_offset"], 16))
        write_json(family_dir / "window-reference-forensic.json", forensic)
        audit.update({"entry_audit": "PASS", "incoming_branch_gate": "PASS",
                      "function_range_safe": True, "runtime_rewrite_safe": True,
                      "relocations_in_window": 0, "inline_only": True,
                      "trampoline_permitted": False, "window_derivation": "TARGET_CFG",
                      "window_agreement": agreement["verdict"],
                      "round_pad_class": "paciasp_only",
                      "window_reference_forensic": forensic["verdict"]})
        write_json(family_dir / "target-entry-audit.json", audit)
        boundary = cp.level7_span_entry_as_boundary(
            {key: entry for key, entry in
             zip(("index", "entry_va", "entry_va_hex", "entry_image_offset",
                  "entry_word", "relative", "target_va", "target_va_hex",
                  "aliases", "symbol"),
                 (audit["index"], int(audit["table_entry_va"], 16),
                  audit["table_entry_va"], int(audit["table_entry_image_offset"], 16),
                  audit["entry_word"], audit["relative"], target, audit["target_va"],
                  audit["aliases"], audit["symbol"]))})
        payloads = {}
        shas = {}
        for delay in (8, 1):
            directory = family_dir / "pair" / str(delay) / "checkpoint"
            directory.mkdir(parents=True, exist_ok=False)
            probe, payload = compose_member(ctx["frozen"], offset, window,
                                            entry_word, core, delay)
            payload_sha = cp.digest(payload)
            require_fresh_payload(payload_sha)
            require(payload[:offset] == ctx["frozen"][:offset]
                    and payload[offset + window:] == ctx["frozen"][offset + window:],
                    "MEMBER_CHANGED_OUTSIDE_WINDOW")
            require(payload[offset:offset + window] == probe, "MEMBER_WINDOW_DRIFT")
            cp.t3.gate_tramp_identity(payload)
            cp.pb.gate_rt_d(payload[dtb_offset:])
            table_slot = int(audit["table_entry_image_offset"], 16)
            require(payload[table_slot:table_slot + 4]
                    == ctx["frozen"][table_slot:table_slot + 4],
                    "PREL32_TARGET_REWRITTEN")
            manifest = {"symbol": family, "family": family,
                        "member_name": f"{label}_{delay}",
                        "target_symbol": audit["symbol"],
                        "target_aliases": audit["aliases"],
                        "target_va": audit["target_va"],
                        "target_image_offset": audit["image_offset"],
                        "offset": offset, "checkpoint_size": window,
                        "core_size": core_size, "entry": audit["entry_pad"],
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
                        "nominal_index": selection["nominal_index"],
                        "deviation": selection["deviation"],
                        "child_nominal_derivation":
                            selection.get("child_nominal_derivation"),
                        "core_variant": ("ultracompact_cntpct_elapsed_b_lo"
                                         if core_size == 56 else
                                         "subsys52_cntpct_elapsed_b_lo"),
                        "probe_architecture": audit["probe_architecture"],
                        "core_sha256": cp.digest(core), "delay_seconds": delay,
                        "payload_size": len(payload), "payload_sha256": payload_sha,
                        "checkpoint_sha256": cp.digest(probe),
                        "frozen_sha256": cp.digest(ctx["frozen"]),
                        "frozen_payload_disjoint": True,
                        "prel32_target_unchanged": True,
                        "cfg_closure": audit["cfg_closure"],
                        "runtime_rewrites": rewrites, "window_agreement": agreement,
                        "window_derivation": "TARGET_CFG", "inline_only": True,
                        "trampoline_permitted": False, "stage": STAGE,
                        "bundle_run": base.BUNDLE_RUN, "bundle": metadata,
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
            shas[delay] = payload_sha
        changed = [i for i, (a, b) in enumerate(zip(payloads[8], payloads[1]))
                   if a != b]
        base.assert_pair_delay_only(changed, offset, core_size)
        identity = {"stage": STAGE, "family": family,
                    "delay8_name": f"{label}_8", "delay1_name": f"{label}_1",
                    "bundle_run": base.BUNDLE_RUN,
                    "source_commit": os.environ["GITHUB_SHA"],
                    "public_run": os.environ["GITHUB_RUN_ID"],
                    "delay8_payload_sha256": shas[8],
                    "delay1_payload_sha256": shas[1],
                    "changed_offsets": changed, "expected_delta_seconds": -7.0,
                    "strong_error_seconds": 1.0, "supported_error_seconds": 2.0,
                    "attribution": "DELAY_CONSTANT_ONLY",
                    "span_index": audit["index"],
                    "selected_index": audit["index"],
                    "nominal_index": selection["nominal_index"],
                    "deviation": selection["deviation"],
                    "target_symbol": audit["symbol"],
                    "target_va": audit["target_va"],
                    "probe_architecture": audit["probe_architecture"],
                    "window": window, "core_size": core_size,
                    "round_pad_class": "paciasp_only",
                    "private_pack": False, "device_operation": False,
                    "kernel_rebuilt": False}
        write_json(family_dir / "pair" / "pair.json", identity)
        names[family] = {"label": label, "identity": identity, "audit": audit,
                         "selection": selection, "offset": offset, "window": window,
                         "core_size": core_size, "shas": shas, "changed": changed}
    return names


def summary_kv(names, enriched, map_stats, selections):
    lines = [f"LATE_LEVEL_POST43_STAGE={STAGE}",
             "LATE_SPAN=__initcall7_start..__initcall_end",
             f"LATE_TABLE_ENTRY_COUNT={len(enriched)}",
             f"LATE_TABLE_INDEX0_SYMBOL={base.FROZEN_INDEX0['symbol']}",
             f"LATE_TABLE_INDEX0_TABLE_VA={hex(base.FROZEN_INDEX0['entry_va'])}",
             f"LATE_TABLE_INDEX0_TARGET_VA={hex(base.FROZEN_INDEX0['target_va'])}",
             f"LATE_TABLE_INDEX0_WORD={hex(base.FROZEN_INDEX0['entry_word'])}",
             f"LATE_TABLE_INDEX0_FUNCTION_SIZE={base.FROZEN_INDEX0['function_size']}",
             f"LATE_MAP_IN_INIT_TEXT={map_stats['init_text']}",
             f"LATE_MAP_TEXT_SECTION_ENTRIES={map_stats['text_section']}",
             f"ROUND_PAD_CLASS=PACIASP_ONLY",
             f"FROZEN_INDICES_EXCLUDED={','.join(str(i) for i in FROZEN_LATE_INDICES)}",
             "FROZEN_WINDOW_DISJOINT=YES", "FROZEN_PAYLOAD_DISJOINT=YES",
             "HIGH8_STATIC_PROBE_DEFECT_FOUND=NO",
             "HIGH8_FORENSIC_RUNTIME_INFERENCE=NONE"]
    for family, label, _nominal in family_specs():
        info = names[family]
        audit = info["audit"]
        prefix = f"{label}_"
        lines += [f"{prefix}NOMINAL_INDEX={info['selection']['nominal_index']}",
                  f"{prefix}INDEX={audit['index']}",
                  f"{prefix}SYMBOL={audit['symbol']}",
                  f"{prefix}TABLE_VA={audit['table_entry_va']}",
                  f"{prefix}TARGET_VA={audit['target_va']}",
                  f"{prefix}IMAGE_OFFSET={audit['image_offset']}",
                  f"{prefix}FUNCTION_SIZE={audit['function_size']}",
                  f"{prefix}WINDOW={audit['window']}",
                  f"{prefix}CORE_SIZE={audit['core_size']}",
                  f"{prefix}PROBE_ARCHITECTURE={audit['probe_architecture']}",
                  f"{prefix}ENTRY_PAD={audit['entry_pad']}",
                  f"{prefix}REGISTRATION={audit['registration']}",
                  f"{prefix}SOURCE={audit['source']}",
                  f"{prefix}DEVIATION=" + (
                      "NONE" if info["selection"]["deviation"] is None else
                      f"{info['selection']['deviation']['reason']}@distance="
                      f"{info['selection']['deviation']['distance']}"),
                  f"{label}_8_PAYLOAD_SHA={info['shas'][8]}",
                  f"{label}_1_PAYLOAD_SHA={info['shas'][1]}",
                  f"{prefix}PAIR_DIFF_OFFSETS={info['changed']}",
                  f"{prefix}PAIR=PASS"]
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
    base.core_bytes(args.core56.read_bytes(), 56)
    base.core_bytes(args.core52.read_bytes(), 52)
    core56 = cp.ultracompact_core(args.core56.read_bytes())
    core52 = cp.subsys52_core(args.core52.read_bytes())
    cp.gate_subsys52_core_equivalence(core56, core52)
    metadata, raw_entries, enriched, ctx = base.enumerate_level7(args.bundle,
                                                                 frozen, out)
    map_stats = {"init_text": sum(1 for e in enriched if e["init_text"]),
                 "text_section": sum(1 for e in enriched if not e["init_text"])}
    high8 = high8_forensic(enriched, ctx, args, out)
    selections, child_nominals = select_targets(enriched, ctx)
    write_json(out / "late-map.json", {
        "stage": STAGE, "bundle_run": base.BUNDLE_RUN,
        "span": [base.SPAN_BEGIN, base.SPAN_END], "entry_count": len(enriched),
        "index0_identity": base.FROZEN_INDEX0, "entries": enriched})
    write_json(out / "selection.json", {
        "stage": STAGE, "selections": selections,
        "child_nominals": dict(zip(("late_post49", "late_post60"), child_nominals)),
        "round_pad_gate": ROUND_PAD_GATE,
        "frozen_indices": FROZEN_LATE_INDICES})
    names = build_pairs(args, selections, ctx, metadata, out)
    require(cp.digest((args.bundle / "vmlinux").read_bytes())
            == metadata["files"]["vmlinux"], "AUDIT_MUTATED_ELF")
    require(frozen == args.frozen.read_bytes(), "AUDIT_MUTATED_FROZEN")
    lines = summary_kv(names, enriched, map_stats, selections)
    (out / "audit-summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"HIGH8_FORENSIC_VERDICT={high8['HIGH8_STATIC_PROBE_DEFECT_FOUND']}",
          flush=True)
    print(f"{STAGE}_PAIR_AUDIT=PASS", flush=True)


if __name__ == "__main__":
    main()
