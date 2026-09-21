#!/usr/bin/env python3
"""Actions-only audit of the linker-folded arm64 jump-label table."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_audit as pm

prior = pm.prior
cp = prior.cp
need = cp.require
TEXT = prior.TEXT
START = 0x1A97528
END = 0x1A9B7B8
COUNT = 1065
SOURCE = "include/linux/jump_label.h"
SYMBOLS = ("__start___jump_table", "__stop___jump_table")
PROTECTED = ((TEXT + pm.PARENT, TEXT + pm.PARENT + 100),
             (TEXT + prior.PARENT, TEXT + prior.PARENT + prior.PARENT_SIZE))


def gate_source(source, config):
    code = re.sub(r"\s+", "", prior.selected.uncomment(source))
    for token in ("structjump_entry{s32code;s32target;longkey;};",
                  "return(unsignedlong)&entry->code+entry->code;",
                  "return(unsignedlong)&entry->target+entry->target;"):
        need(token in code, "LINKED_JUMP_SOURCE_ABI_DRIFT")
    for name in ("JUMP_LABEL", "HAVE_ARCH_JUMP_LABEL", "HAVE_ARCH_JUMP_LABEL_RELATIVE"):
        need(re.search(r"^CONFIG_" + name + r"=y$", config, re.M), "LINKED_JUMP_CONFIG_DRIFT:" + name)
    for name in ("KPROBES", "FTRACE", "CFI_CLANG"):
        need(re.search(r"^# CONFIG_" + name + r" is not set$", config, re.M),
             "UNQUALIFIED_DYNAMIC_TEXT_WRITER:" + name)
    need(not re.search(r"^CONFIG_HAVE_STATIC_CALL(?:_INLINE)?=y$", config, re.M),
         "UNQUALIFIED_STATIC_CALL_TABLE")


def gate_layout(nm, sysmap, sections):
    values = [cp.t3.nm_symbol(nm, name) for name in SYMBOLS]
    need(values == [cp.t3.nm_symbol(sysmap, name) for name in SYMBOLS] == [TEXT + START, TEXT + END],
         "LINKED_JUMP_SYMBOL_BOUNDS_DRIFT")
    lo, hi = values
    need(lo % 8 == 0 and hi - lo == COUNT * 16, "LINKED_JUMP_RECORD_GEOMETRY_DRIFT")
    mappings = [s for s in sections if s["vma"] <= lo and hi <= s["vma"] + s["size"]]
    need(len(mappings) == 1, "LINKED_JUMP_MAPPING_NOT_UNIQUE")
    section = mappings[0]
    need(section["name"] == ".rodata" and section["alloc"] and not section["code"],
         "LINKED_JUMP_FOLDED_SECTION_DRIFT")
    need(not any(s["name"] == "__jump_table" for s in sections), "LINKED_JUMP_DUPLICATE_SECTION")
    return section


def decode(data, base):
    need(data and len(data) % 16 == 0 and base % 8 == 0, "LINKED_JUMP_RECORD_SIZE_OR_ALIGNMENT")
    return [{"record": base + index * 16, "code": base + index * 16 + code,
             "target": base + index * 16 + 4 + target}
            for index, (code, target, _key) in enumerate(struct.iter_unpack("<iiq", data))]


def gate_entries(entries, protected, ranges):
    need(entries, "LINKED_JUMP_ENTRIES_EMPTY")
    for record in entries:
        code, target = record["code"], record["target"]
        need(code % 4 == target % 4 == 0, "LINKED_JUMP_UNALIGNED_CODE_OR_TARGET")
        need(all(any(lo <= address and address + 4 <= hi for lo, hi in ranges)
                 for address in (code, target)), "LINKED_JUMP_ADDRESS_OUTSIDE_CODE")
        for lo, hi in protected:
            need(code + 4 <= lo or code >= hi, f"LINKED_JUMP_REWRITES_PROTECTED:{code:#x}")
            need(not lo <= target < hi, f"LINKED_JUMP_TARGETS_PROTECTED:{target:#x}")
    return len(entries)


def gate_bytes(elf, image, frozen):
    need(len(elf) == END - START == COUNT * 16 and elf == image == frozen,
         "LINKED_JUMP_ELF_IMAGE_FIX8_DISAGREEMENT")


def audit(args):
    prior.gate_actions()
    prior.gate_authority(os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"])
    files = {name: (args.bundle / name).read_bytes() for name in prior.BUNDLE_FILES}
    prior.gate_bundle(json.loads((args.bundle / "bundle.json").read_text()), files)
    frozen = args.frozen.read_bytes()
    prior.gate_frozen(frozen)
    need(cp.pb.run(["git", "-C", str(cp.pb.LINUX), "rev-parse", "HEAD"]).strip() == cp.pb.LINUX_BASE,
         "LINKED_JUMP_SOURCE_PIN_DRIFT")
    source = (cp.pb.LINUX / SOURCE).read_bytes()
    pinned = cp.pb.run(["git", "-C", str(cp.pb.LINUX), "show", f"{cp.pb.LINUX_BASE}:{SOURCE}"]).encode()
    need(source == pinned, "LINKED_JUMP_PINNED_SOURCE_DRIFT")
    gate_source(source.decode(), files["kernel.config"].decode())
    args.out.mkdir(parents=True, exist_ok=False)
    vmlinux = args.bundle / "vmlinux"
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    sections = cp.t3.section_map(args.out, cp.TOOLS, vmlinux)
    ranges = [(TEXT + lo, TEXT + hi) for lo, hi in prior.gate_sections(sections, len(files["Image"]))]
    section = gate_layout(nm, files["System.map"].decode(), sections)
    table = cp.vmlinux_bytes_at(vmlinux, sections, TEXT + START, END - START)
    gate_bytes(table, files["Image"][START:END], frozen[START:END])
    entries = decode(table, TEXT + START)
    need(gate_entries(entries, PROTECTED, ranges) == COUNT, "LINKED_JUMP_COUNT_DRIFT")
    cp.t3.gate_window_relocation_scan(TEXT + START - 7, END - START + 7,
                                     cp.relocation_sites(vmlinux, sections))
    report = {"gate": "LINKED_JUMP_TABLE_PM_WORKER_SAFE", "source_commit": os.environ["GITHUB_SHA"],
              "public_run": os.environ["GITHUB_RUN_ID"], "bundle_run": prior.BUNDLE_RUN,
              "offset": START, "end": END, "size": END - START, "entries": COUNT,
              "section": section["name"], "sha256": cp.digest(table),
              "source_file": SOURCE, "source_sha256": cp.digest(source),
              "layout": "S32_CODE_S32_TARGET_S64_KEY_FIELD_RELATIVE",
              "agreement": "ELF_IMAGE_FIX8_EXACT", "protected": [list(span) for span in PROTECTED],
              "code_rewrite_overlap": [], "target_entry_overlap": [],
              "candidate_generated": False, "device_operation": False}
    prior.save(args.out / "linked-jump-table.json", report)
    prior.save(args.out / "linked-jump-entries.json", entries)
    print(json.dumps(report, indent=2))
    print("LINKED_JUMP_TABLE_PM_WORKER_SAFE=YES\nCANDIDATE_GENERATED=NO\nDEVICE_OPERATION=NO")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    audit(parser.parse_args())


if __name__ == "__main__":
    main()
