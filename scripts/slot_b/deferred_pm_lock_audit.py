#!/usr/bin/env python3
"""Actions-only feasibility of the original PM-lock return boundary; no candidate."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_probe as pm

prior, cp, need = pm.prior, pm.cp, pm.need
TEXT, PARENT, PARENT_SIZE = pm.TEXT, pm.PARENT, pm.PARENT_SIZE
OFFSET, WINDOW, END = 0x8DE478, 60, 0x8DE4B4
PREFIX_SIZE, CORE_SIZE, PADDING_SIZE = 40, 56, 4
BACKEDGE, BACKEDGE_TARGET = 0x8DE4B0, 0x8DE48C
POWER_SOURCE = "drivers/base/power/main.c"
SOURCE_FILES = (*pm.SOURCE_FILES, POWER_SOURCE)
CALLS = {
    "__srcu_read_lock": {"offset": 0x8DE46C, "target": 0x1146A0, "word": 0x97E0D88D},
    "device_pm_lock": {"offset": 0x8DE474, "target": 0x8FD584, "word": 0x94007C44},
}
POSITIVE_LIMIT = ["original_device_links_read_lock_returned", "original_device_pm_lock_returned"]
NOT_PROVEN = ["persistent_lock_state", "valid_srcu_index", "pm_list_movement", "pm_tail_return",
              "bus_or_driver_probe", "device_identity", "culprit", "late_initcalls_completed", "init", "usb"]


def gate_geometry(offset=OFFSET, window=WINDOW, end=END):
    need(window != 56, "PM_LOCK_56B_LEAVES_LIVE_BACKEDGE")
    need(all(type(value) is int for value in (offset, window, end)) and
         (offset, window, end, PARENT, PARENT_SIZE, PREFIX_SIZE, CORE_SIZE, PADDING_SIZE) ==
         (0x8DE478, 60, 0x8DE4B4, 0x8DE450, 100, 40, 56, 4), "PM_LOCK_GEOMETRY_DRIFT")
    need(offset == PARENT + PREFIX_SIZE and offset + window == end == PARENT + PARENT_SIZE and
         window == CORE_SIZE + PADDING_SIZE and BACKEDGE == offset + CORE_SIZE and
         BACKEDGE + 4 == end, "PM_LOCK_SUFFIX_OR_BACKEDGE_DRIFT")


def gate_parent(elf, image, frozen):
    gate_geometry()
    pm.entry.gate_parent(elf, image, frozen)
    pm.gate_parent(frozen)
    need(frozen[:PREFIX_SIZE] == pm.ORIGINAL[:PREFIX_SIZE], "PM_LOCK_ORIGINAL_PREFIX_DRIFT")


def gate_calls(original, nm, sysmap):
    pm.gate_parent(original)
    for name, call in CALLS.items():
        word = struct.unpack_from("<I", original, call["offset"] - PARENT)[0]
        need(word == call["word"] and word & 0xFC000000 == 0x94000000 and
             cp.branch_target(word, TEXT + call["offset"]) == TEXT + call["target"] ==
             cp.t3.nm_symbol(nm, name) == cp.t3.nm_symbol(sysmap, name),
             f"PM_LOCK_ORIGINAL_CALL_TARGET_DRIFT:{name}")
    need(CALLS["device_pm_lock"]["offset"] + 4 == OFFSET, "PM_LOCK_NOT_ORIGINAL_RETURN_BOUNDARY")


def gate_incoming_records(naive, suffix, prefix):
    need(naive == [(TEXT + BACKEDGE, TEXT + BACKEDGE_TARGET)], "PM_LOCK_NAIVE_BACKEDGE_IDENTITY_DRIFT")
    need(not suffix, "PM_LOCK_INCOMING_SUFFIX")
    need(not prefix, "PM_LOCK_INCOMING_PRESERVED_PREFIX")


def gate_incoming(binary, ranges):
    records = [cp.incoming_inclusive(binary, ranges, TEXT, TEXT + lo, TEXT + hi) for lo, hi in
               ((OFFSET, OFFSET + CORE_SIZE), (OFFSET, END), (PARENT + 4, OFFSET))]
    gate_incoming_records(*records)
    return {name: [list(edge) for edge in value] for name, value in
            zip(("rejected_56b_incoming", "incoming_suffix", "incoming_preserved_prefix"), records)}


def prospective_terminal_layout():
    gate_geometry()
    core = cp.ultracompact_core(pm.CORE)
    need(cp.digest(core) == pm.CORE_SHA, "PM_LOCK_REFERENCE_CORE_DRIFT")
    words = struct.unpack("<14I", core)
    need(cp.branch_target(words[8], TEXT + OFFSET + 32) == TEXT + OFFSET + 16 and
         cp.branch_target(words[13], TEXT + OFFSET + 52) == TEXT + OFFSET + 48 and
         words[9:] == (0x52800120, 0x72B08000, 0xD4000003, 0xD503205F, 0x17FFFFFF),
         "PM_LOCK_PROSPECTIVE_TERMINAL_CLOSURE_DRIFT")
    return {"core_size": CORE_SIZE, "core_sha256": pm.CORE_SHA, "padding_size": PADDING_SIZE,
            "padding_word": 0xD503201F, "padding_offset": BACKEDGE, "padding_reachable": False,
            "terminal": "PSCI_SYSTEM_RESET_OR_LOCAL_WFE_LOOP", "terminal_fallthrough": False,
            "new_stack_frame": False, "original_stack_frame_bytes": 32,
            "original_frame_left_outstanding_at_terminal": True,
            "actual_new_probe_assembled": False, "prospective_layout_only": True}


def gate_lock_sources(core, power):
    core = re.sub(r"\s+", "", prior.selected.uncomment(core))
    wrapper = ("intdevice_links_read_lock(void)__acquires(&device_links_srcu)"
               "{returnsrcu_read_lock(&device_links_srcu);}")
    need(core.count(wrapper) == 1, "PM_LOCK_SRCU_WRAPPER_SOURCE_DRIFT")
    power = prior.selected.uncomment(power)
    need(prior.selected.function_body(power, "device_pm_lock") == "mutex_lock(&dpm_list_mtx);",
         "PM_LOCK_MUTEX_WRAPPER_SOURCE_DRIFT")
    need(prior.selected.function_body(power, "device_pm_unlock") == "mutex_unlock(&dpm_list_mtx);",
         "PM_LOCK_MUTEX_UNLOCK_SOURCE_DRIFT")


def audit_lock_sources():
    sources = {name: (cp.pb.LINUX / name).read_bytes() for name in ("drivers/base/core.c", POWER_SOURCE)}
    for name, actual in sources.items():
        pinned = cp.pb.run(["git", "-C", str(cp.pb.LINUX), "show", f"{cp.pb.LINUX_BASE}:{name}"]).encode()
        need(actual == pinned, f"PM_LOCK_PINNED_SOURCE_DRIFT:{name}")
    gate_lock_sources(*(sources[name].decode() for name in ("drivers/base/core.c", POWER_SOURCE)))
    return {POWER_SOURCE: cp.digest(sources[POWER_SOURCE])}


def audit(args):
    prior.gate_actions()
    source_commit, public_run = os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"]
    prior.gate_authority(source_commit, public_run)
    gate_geometry()
    files = {name: (args.bundle / name).read_bytes() for name in prior.BUNDLE_FILES}
    prior.gate_bundle(json.loads((args.bundle / "bundle.json").read_text()), files)
    frozen = args.frozen.read_bytes()
    pm.gate_frozen(frozen)
    pm.read_linked_reference()
    args.out.mkdir(parents=True, exist_ok=False)
    executed = pm.linked.audit(argparse.Namespace(bundle=args.bundle, frozen=args.frozen,
                                                 out=args.out / "linked-jump"))
    linked = pm.read_linked_report(args.out / "linked-jump/linked-jump-table.json", source_commit, public_run)
    need(prior.canonical(executed) == prior.canonical(linked), "PM_LOCK_EXECUTED_LINKED_REPORT_DRIFT")
    pm.entry.audit(argparse.Namespace(bundle=args.bundle, frozen=args.frozen, out=args.out / "entry"))
    feasibility = json.loads((args.out / "entry/feasibility.json").read_text())
    sources = {**pm.gate_feasibility(feasibility, source_commit, public_run),
               linked["source_file"]: linked["source_sha256"]}
    need(prior.canonical(sources) == prior.canonical(pm.SOURCE_HASHES), "PM_LOCK_PREREQUISITE_SOURCES_DRIFT")
    sources.update(audit_lock_sources())
    worker_out = args.out / "worker"
    worker_out.mkdir()
    vmlinux = args.bundle / "vmlinux"
    prior.audit_binary(worker_out, vmlinux, files["Image"], frozen)
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    sysmap = files["System.map"].decode()
    lo, hi = cp.t3.symbol_extent(nm, pm.entry.NAME)
    need((lo, hi) == (TEXT + PARENT, TEXT + END), "PM_LOCK_PARENT_EXTENT_DRIFT")
    sections = cp.t3.section_map(args.out, cp.TOOLS, vmlinux)
    ranges = prior.gate_sections(sections, len(files["Image"]))
    section = cp.t3.gate_window_section_scan(TEXT + OFFSET, WINDOW, sections)
    need(section["name"] == ".text", "PM_LOCK_NOT_TEXT")
    original = cp.vmlinux_bytes_at(vmlinux, sections, lo, hi - lo)
    gate_parent(original, files["Image"][PARENT:END], frozen[PARENT:END])
    gate_calls(original, nm, sysmap)
    scans = [gate_incoming(binary, ranges) for binary in (files["Image"], frozen[:len(files["Image"])])]
    need(scans[0] == scans[1], "PM_LOCK_INCOMING_COPY_DISAGREEMENT")
    cp.t3.gate_function_extent_scan(TEXT + OFFSET, WINDOW, hi)
    # The entry and worker audits above protect both complete functions, not only this suffix.
    report = {"gate": "DEFERRED_PM_LOCK_RETURN_STATIC_FEASIBLE", "source_commit": source_commit,
              "public_run": public_run, "bundle_run": prior.BUNDLE_RUN, "bundle": prior.BUNDLE_IDENTITY,
              "source_files_sha256": sources, "parent": pm.entry.NAME, "parent_offset": PARENT,
              "parent_size": PARENT_SIZE, "parent_sha256": pm.ORIGINAL_SHA,
              "prefix_size": PREFIX_SIZE, "prefix_sha256": cp.digest(original[:PREFIX_SIZE]),
              "offset": OFFSET, "window": WINDOW, "window_end": END, "section": section["name"],
              "parent_agreement": "ELF_IMAGE_FIX8_EXACT_100B",
              "worker_agreement": "ELF_IMAGE_FIX8_EXACT_196B", "worker_sha256": cp.digest(prior.ORIGINAL),
              "single_direct_caller": pm.CALL, "original_calls": CALLS, "original_prefix_preserved": True,
              **scans[0], "prospective_terminal_layout": prospective_terminal_layout(),
              **pm.linked_binding(linked, source_commit, public_run), "linked_jump_reference": pm.LINKED_REFERENCE,
              "full_parent_and_worker_gates": ["source", "sections", "symbols", "incoming", "literals",
                                                "RELA", "RELR", "runtime_rewrites", "exception_fault_and_fixup",
                                                "folded_jump_code_and_target"],
              "future_positive_limit": POSITIVE_LIMIT, "not_proven": NOT_PROVEN,
              "added_pointer_reads": 0, "candidate_generated": False, "device_ready": False,
              "device_operation": False, "partition_writes": 0, "kernel_rebuild": False}
    prior.save(args.out / "feasibility.json", report)
    print(json.dumps(report, indent=2))
    print("DEFERRED_PM_LOCK_RETURN_STATIC_FEASIBLE=YES\nCANDIDATE_GENERATED=NO\nDEVICE_READY=NO\nDEVICE_OPERATION=NO")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "frozen", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    audit(parser.parse_args())


if __name__ == "__main__":
    main()
