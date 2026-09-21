#!/usr/bin/env python3
"""Actions-only feasibility audit; never generate a kernel or boot candidate."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_after_kfree_probe as prior

cp = prior.cp
need = cp.require
TEXT = prior.TEXT
NAME = "device_pm_move_to_tail"
PARENT = 0x8DE450
CALL = 0x8E84A0
WINDOW = 56
SOURCE_REFERENCES = {"drivers/base/core.c", "drivers/base/dd.c", "drivers/base/base.h"}
BODY = ("intidx;idx=device_links_read_lock();device_pm_lock();"
        "device_reorder_to_tail(dev,NULL);device_pm_unlock();device_links_read_unlock(idx);")


def gate_sources(sources, config):
    need(set(sources) == SOURCE_REFERENCES, "PM_TAIL_SOURCE_REFERENCE_SET_DRIFT")
    prior.source_contract(sources["drivers/base/dd.c"], sources["drivers/base/core.c"], config)
    code = {name: prior.selected.uncomment(text) for name, text in sources.items()}
    for name, text in code.items():
        need(len(re.findall(r"\b" + NAME + r"\b", text)) == 1, f"PM_TAIL_SOURCE_REFERENCE_COUNT:{name}")
    need(prior.selected.function_body(code["drivers/base/core.c"], NAME) == BODY,
         "PM_TAIL_WRAPPER_SOURCE_ORDER_DRIFT")
    worker = prior.selected.function_body(code["drivers/base/dd.c"], "deferred_probe_work_func")
    need("mutex_unlock(&deferred_probe_mutex);device_pm_move_to_tail(dev);" in worker,
         "PM_TAIL_WORKER_PREDECESSOR_DRIFT")
    need("voiddevice_pm_move_to_tail(structdevice*dev);" in
         re.sub(r"\s+", "", code["drivers/base/base.h"]), "PM_TAIL_DECLARATION_DRIFT")


def gate_parent(elf, image, frozen):
    need(elf == image == frozen, "PM_TAIL_ELF_IMAGE_FIX8_DISAGREEMENT")
    need(60 <= len(frozen) <= 4096 and len(frozen) % 4 == 0, "PM_TAIL_ENTRY_WINDOW_DOES_NOT_FIT")
    need(struct.unpack_from("<I", frozen)[0] == 0xD503233F, "PM_TAIL_PACIASP_ENTRY_DRIFT")


def gate_call(word):
    need(word & 0xFC000000 == 0x94000000 and
         cp.branch_target(word, TEXT + CALL) == TEXT + PARENT, "PM_TAIL_ORIGINAL_BL_DRIFT")


def gate_incoming_records(entry, interior, window):
    need(entry == [(TEXT + CALL, TEXT + PARENT)], "PM_TAIL_NOT_SINGLE_WORKER_CALLER")
    need(not interior, "PM_TAIL_EXTERNAL_INTERIOR_ENTRY")
    need(not window, "PM_TAIL_INCOMING_OVERWRITE_WINDOW")


def audit_sources(config):
    identities = prior.audit_sources(config)
    references = cp.pb.run(["git", "-C", str(cp.pb.LINUX), "grep", "-l", "-w", "--", NAME]).splitlines()
    need(set(references) == SOURCE_REFERENCES, "PM_TAIL_WHOLE_TREE_REFERENCE_SET_DRIFT")
    sources = {}
    for name in sorted(SOURCE_REFERENCES):
        actual = (cp.pb.LINUX / name).read_bytes()
        pinned = cp.pb.run(["git", "-C", str(cp.pb.LINUX), "show", f"{cp.pb.LINUX_BASE}:{name}"]).encode()
        need(actual == pinned, f"PM_TAIL_PINNED_SOURCE_DRIFT:{name}")
        sources[name] = actual.decode()
        identities[name] = cp.digest(actual)
    gate_sources(sources, config)
    return identities


def audit(args):
    prior.gate_actions()
    prior.gate_authority(os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"])
    metadata = json.loads((args.bundle / "bundle.json").read_text())
    files = {name: (args.bundle / name).read_bytes() for name in prior.BUNDLE_FILES}
    prior.gate_bundle(metadata, files)
    frozen = args.frozen.read_bytes()
    prior.gate_frozen(frozen)
    sources = audit_sources(files["kernel.config"].decode())
    args.out.mkdir(parents=True, exist_ok=False)
    elf = args.bundle / "vmlinux"
    nm = cp.pb.run([cp.TOOLS["nm"], str(elf)])
    sysmap = files["System.map"].decode()
    lo, hi = cp.t3.symbol_extent(nm, NAME)
    need(lo == cp.t3.nm_symbol(sysmap, NAME) == TEXT + PARENT, "PM_TAIL_SYMBOL_IDENTITY_DRIFT")
    sections = cp.t3.section_map(args.out, cp.TOOLS, elf)
    ranges = prior.gate_sections(sections, len(files["Image"]))
    section = cp.t3.gate_window_section_scan(lo, hi - lo, sections)
    need(section["name"] == ".text", "PM_TAIL_NOT_EXACT_TEXT_TARGET")
    original = cp.vmlinux_bytes_at(elf, sections, lo, hi - lo)
    gate_parent(original, files["Image"][PARENT:hi - TEXT], frozen[PARENT:hi - TEXT])
    prior.gate_worker(files["Image"][prior.PARENT:prior.PARENT + prior.PARENT_SIZE])
    gate_call(struct.unpack_from("<I", frozen, CALL)[0])
    for binary in (files["Image"], frozen[:len(files["Image"])]):
        gate_incoming_records(cp.incoming_inclusive(binary, ranges, TEXT, lo, lo + 4),
                              cp.incoming_inclusive(binary, ranges, TEXT, lo + 4, hi),
                              cp.incoming_inclusive(binary, ranges, TEXT, lo + 4, lo + 4 + WINDOW))
        cp.t3.gate_window_literal_scan(lo - 1, hi - lo + 1, binary)
    cp.t3.gate_window_symbol_scan(lo, hi - lo, [va for va, _ in cp.t3.symbol_table(nm)])
    cp.t3.gate_function_extent_scan(lo + 4, WINDOW, hi)
    cp.t3.gate_window_relocation_scan(lo - 7, hi - lo + 7, cp.relocation_sites(elf, sections))
    rewrites = cp.audit_rewrites(args.out, elf, sections, (lo, hi))
    need(prior.canonical(rewrites) == prior.canonical(prior.RUNTIME_TABLES), "PM_TAIL_RUNTIME_TABLE_DRIFT")
    ex = next(row for row in sections if row["name"] == "__ex_table")
    prior.gate_exception_destinations(cp.section_bytes(elf, ex), ex["vma"], (lo, hi))
    for name in (NAME, "device_reorder_to_tail", "device_pm_lock", "device_pm_unlock",
                 "device_links_read_lock", "device_links_read_unlock"):
        if not re.search(r"\b" + re.escape(name) + r"$", nm, re.M):
            continue
        begin, end = cp.t3.symbol_extent(nm, name)
        dump = cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={begin:#x}",
                          f"--stop-address={end:#x}", str(elf)])
        (args.out / (name + ".txt")).write_text(dump)
    report = {"gate": "DEFERRED_PM_TAIL_ENTRY_STATIC_FEASIBLE", "name": NAME,
              "source_commit": os.environ["GITHUB_SHA"], "public_run": os.environ["GITHUB_RUN_ID"],
              "bundle_run": prior.BUNDLE_RUN, "bundle": prior.BUNDLE_IDENTITY,
              "source_files_sha256": sources, "parent_offset": PARENT, "parent_size": hi - lo,
              "parent_sha256": cp.digest(original), "parent_words": list(struct.unpack(f"<{len(original)//4}I", original)),
              "offset": PARENT + 4, "window": WINDOW, "section": section["name"],
              "single_direct_caller": CALL, "original_paciasp_preserved": True,
              "worker_unchanged": True, "core_sha256": prior.CORE_SHA,
              "added_pointer_reads": 0, "candidate_generated": False, "device_ready": False,
              "device_operation": False, "partition_writes": 0,
              "future_positive_limit": ["reason_field_cleared", "worker_mutex_unlock_returned", "pm_tail_entry"],
              "not_proven": ["pm_tail_return", "bus_probe_entry", "driver_probe", "culprit", "init", "usb"]}
    prior.save(args.out / "feasibility.json", report)
    print(json.dumps(report, indent=2))
    print("DEFERRED_PM_TAIL_ENTRY_STATIC_FEASIBLE=YES\nCANDIDATE_GENERATED=NO\nDEVICE_READY=NO\nDEVICE_OPERATION=NO")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    audit(parser.parse_args())


if __name__ == "__main__":
    main()
