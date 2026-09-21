#!/usr/bin/env python3
"""Actions-only, read-only first deferred-device name timing channel."""
import argparse
import json
import os
import re
import struct
from pathlib import Path

import deferred_probe_checkpoints as d

cp = d.cp
need = cp.require
OFFSET = 0x8E8468
SIZE = 96
PARENT = 0x8E8424
PARENT_SIZE = 196
VARIANTS = {"ref8": (0, 0), "ref1": (1, 0), "b0lo": (2, 0),
            "b0hi": (3, 0), "b1lo": (2, 1), "b1hi": (3, 1)}
SELECTORS = (0xD28000E8, 0xD2800008, 0xD3400D08, 0xD3441D08)


def core_words(variant):
    kind, index = VARIANTS[variant]
    return (0xD5034FDF, 0xB4000114, 0xF9400288, 0xB40000C8,
            0x39400109, 0x34000089, 0x39400108 | (index << 10), SELECTORS[kind],
            0x14000002, 0xD2800208, 0x91000508, 0xD53BE009, 0x9B087D2A,
            *cp.ULTRACOMPACT_WORDS[3:])


def gate_core(variant, core):
    need(len(core) == SIZE, "NAME_CORE_SIZE_DRIFT")
    need(struct.unpack("<24I", core) == core_words(variant), "NAME_CORE_OPCODE_DRIFT")
    for word_index in (1, 3, 5):
        word = struct.unpack_from("<I", core, word_index * 4)[0]
        need(cp.branch_target(word, word_index * 4) == 36, "NULL_GUARD_TARGET_DRIFT")
    need(cp.branch_target(struct.unpack_from("<I", core, 32)[0], 32) == 40,
         "VALID_NAME_BRANCH_DRIFT")
    need(core[52:] == struct.pack("<11I", *cp.ULTRACOMPACT_WORDS[3:]),
         "PROVEN_TIMER_RESET_TAIL_DRIFT")


def source_contract(linux, config):
    device = (linux / "include/linux/device.h").read_text()
    kobject = (linux / "include/linux/kobject.h").read_text()
    need(re.search(r"struct device\s*\{\s*struct kobject\s+kobj;", device),
         "DEVICE_KOBJECT_FIRST_MEMBER_DRIFT")
    need(re.search(r"struct kobject\s*\{\s*const char\s*\*name;", kobject),
         "KOBJECT_NAME_FIRST_MEMBER_DRIFT")
    need("CONFIG_RANDSTRUCT_NONE=y" in config.splitlines(), "RANDOMIZED_LAYOUT_REJECTED")
    source = (linux / "drivers/base/dd.c").read_text()
    d.source_contract(source, config)
    need("static DECLARE_WORK(deferred_probe_work, deferred_probe_work_func);" in source,
         "WORKER_REGISTRATION_DRIFT")
    body = re.search(r"static void deferred_probe_work_func\([^)]*\)\s*\{(.*?)^\}",
                     source, re.S | re.M)
    need(body is not None, "WORKER_SOURCE_MISSING")
    sequence = ["mutex_lock(&deferred_probe_mutex)", "while (!list_empty(",
                "dev = private->device", "list_del_init(", "get_device(dev)",
                "mutex_unlock(&deferred_probe_mutex)", "bus_probe_device(dev)"]
    positions = [body[1].index(item) for item in sequence]
    need(positions == sorted(positions), "DEVICE_LIFETIME_LOCK_ORDER_DRIFT")


def gate_member(variant, frozen, payload, manifest):
    need(len(payload) == len(frozen) == cp.t3.FIX8_PAYLOAD_SIZE, "NAME_PAYLOAD_SIZE_DRIFT")
    need(payload[:OFFSET] == frozen[:OFFSET] and payload[OFFSET + SIZE:] == frozen[OFFSET + SIZE:],
         "NAME_CHANGE_OUTSIDE_WINDOW")
    gate_core(variant, payload[OFFSET:OFFSET + SIZE])
    expected = {"variant": variant, "offset": OFFSET, "window": SIZE,
                "parent": "deferred_probe_work_func", "parent_offset": PARENT,
                "parent_size": PARENT_SIZE, "section": ".text", "device_register": "x20",
                "name_offset": VARIANTS[variant][1], "code_kind": VARIANTS[variant][0],
                "payload_sha256": cp.digest(payload), "normal_boot_candidate": False}
    for key, value in expected.items():
        need(manifest.get(key) == value, f"NAME_MANIFEST_DRIFT:{key}")
    cp.t3.gate_tramp_identity(payload)


def audit(args):
    args.out.mkdir(parents=True, exist_ok=False)
    bundle = args.bundle
    metadata = json.loads((bundle / "bundle.json").read_text())
    need(metadata["files"]["vmlinux"] == d.ELF_SHA, "BUNDLE_ELF_DRIFT")
    need(metadata["linux_base"] == cp.pb.LINUX_BASE and
         metadata["patch_queue_sha256"] == cp.pb.PATCH_QUEUE_SHA, "BUNDLE_SOURCE_DRIFT")
    for name in ("Image", "vmlinux", "System.map", "kernel.config"):
        need(cp.digest((bundle / name).read_bytes()) == metadata["files"][name],
             f"BUNDLE_IDENTITY:{name}")
    frozen = args.frozen.read_bytes()
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    image = (bundle / "Image").read_bytes()
    elf = bundle / "vmlinux"
    nm = cp.pb.run([cp.TOOLS["nm"], str(elf)])
    sections = cp.t3.section_map(args.out, cp.TOOLS, elf)
    need(cp.t3.symbol_extent(nm, "deferred_probe_work_func") ==
         (d.TEXT + PARENT, d.TEXT + PARENT + PARENT_SIZE), "WORKER_EXTENT_DRIFT")
    need(image[PARENT:PARENT + PARENT_SIZE] == frozen[PARENT:PARENT + PARENT_SIZE] ==
         cp.vmlinux_bytes_at(elf, sections, d.TEXT + PARENT, PARENT_SIZE),
         "WORKER_NOT_BYTE_EXACT")
    need(struct.unpack_from("<I", frozen, OFFSET - 4)[0] == 0xF9401114,
         "X20_DEVICE_LOAD_DRIFT")
    need(OFFSET + SIZE == 0x8E84C8 and OFFSET > PARENT + 60,
         "EMPTY_EXIT_OR_FROZEN_ENTRY_OVERLAP")
    source_contract(cp.pb.LINUX, (bundle / "kernel.config").read_text())
    window = d.TEXT + OFFSET, d.TEXT + OFFSET + SIZE
    ranges = [(s["vma"] - d.TEXT, s["vma"] - d.TEXT + s["size"])
              for s in sections if s["alloc"] and s["code"]]
    incoming = cp.incoming_inclusive(frozen[:len(image)], ranges, d.TEXT, *window)
    need(not incoming, f"NAME_WINDOW_INTERIOR_ENTRY:{incoming[:8]}")
    cp.t3.gate_window_symbol_scan(window[0], SIZE, [va for va, _ in cp.t3.symbol_table(nm)])
    cp.t3.gate_window_section_scan(window[0], SIZE, sections)
    cp.t3.gate_function_extent_scan(window[0], SIZE, d.TEXT + PARENT + PARENT_SIZE)
    cp.t3.gate_window_literal_scan(window[0] - 1, SIZE + 1, frozen[:len(image)])
    cp.t3.gate_window_relocation_scan(window[0], SIZE, cp.relocation_sites(elf, sections))
    rewrites = cp.audit_rewrites(args.out, elf, sections, window)
    report = {"source_commit": os.environ["GITHUB_SHA"], "public_run": os.environ["GITHUB_RUN_ID"],
              "offset": OFFSET, "window": SIZE, "parent": "deferred_probe_work_func",
              "parent_offset": PARENT, "parent_size": PARENT_SIZE, "section": ".text",
              "device_register": "x20", "device_kobject_offset": 0, "kobject_name_offset": 0,
              "source_lifetime": "DEFERRED_MUTEX_HELD_BEFORE_LIST_REMOVAL",
              "empty_list_exit_preserved": True, "invalid_pointer_delay_s": 17,
              "normal_boot_candidate": False, "memory_writes": False,
              "incoming": incoming, "runtime_rewrites": rewrites}
    d.save(args.out / "audit.json", report)
    root = args.verify_pair if args.verify_pair else args.out / "pair"
    records = {}
    for variant, (kind, index) in VARIANTS.items():
        core = (args.core / f"{variant}.bin").read_bytes()
        gate_core(variant, core)
        member = root / variant
        if args.verify_pair:
            payload = (member / "payload.bin").read_bytes()
            manifest = json.loads((member / "manifest.json").read_text())
            for key, value in report.items():
                need(manifest.get(key) == value, f"NAME_REVERIFY_METADATA:{key}")
        else:
            member.mkdir(parents=True, exist_ok=False)
            payload = cp.patch_window(frozen, OFFSET, core)
            manifest = {**report, "variant": variant, "name_offset": index, "code_kind": kind,
                        "payload_sha256": cp.digest(payload)}
            (member / "payload.bin").write_bytes(payload)
            d.save(member / "manifest.json", manifest)
        gate_member(variant, frozen, payload, manifest)
        records[variant] = manifest["payload_sha256"]
    identity = {"stage": "name", "source_commit": report["source_commit"],
                "public_run": report["public_run"], "offset": OFFSET, "window": SIZE,
                "payload_shas": records}
    if args.verify_pair:
        need(identity == json.loads((root / "pair.json").read_text()), "NAME_PAIR_IDENTITY_DRIFT")
    else:
        d.save(root / "pair.json", identity)
    d.save(args.out / "verified.json", identity)
    print(json.dumps(identity, indent=2))
    print("NAME_CHANNEL_CI_READY=YES\nDEVICE_OPERATION=NO\nLOCAL_BUILD=NO")


def private(args):
    need(os.environ.get("GITHUB_REPOSITORY") == "ChuenSan/thyme-mainline-private-ci",
         "OEM_ENVELOPE_PRIVATE_ONLY")
    frozen, base = args.frozen.read_bytes(), args.boot_base.read_bytes()
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    need(cp.digest(base) == d.BASE_BOOT_SHA and len(base) == d.BOOT_SIZE, "BASE_BOOT_DRIFT")
    need(cp.pb.parse_boot_v3(base, "FIX8")["kernel"] == frozen, "BASE_PAYLOAD_DRIFT")
    identity = json.loads((args.pair / "pair.json").read_text())
    need(identity["source_commit"] == args.source_commit and
         identity["public_run"] == args.public_run and identity["stage"] == "name",
         "PUBLIC_AUTHORITY_DRIFT")
    args.out.mkdir(parents=True, exist_ok=False)
    records = {}
    for variant in VARIANTS:
        member = args.pair / variant
        manifest = json.loads((member / "manifest.json").read_text())
        payload = (member / "payload.bin").read_bytes()
        need(manifest["source_commit"] == args.source_commit and
             manifest["public_run"] == args.public_run, "MEMBER_AUTHORITY_DRIFT")
        gate_member(variant, frozen, payload, manifest)
        need(cp.digest(payload) == identity["payload_shas"][variant], "PAYLOAD_AUTHORITY_DRIFT")
        name = f"defer-name-{variant}-boot.img"
        boot = ((args.verify_boots / name).read_bytes() if args.verify_boots else
                base[:4096] + payload + base[4096 + len(payload):])
        offset = 4096 + OFFSET
        need(len(boot) == d.BOOT_SIZE and boot[:offset] == base[:offset] and
             boot[offset + SIZE:] == base[offset + SIZE:], "BOOT_ENVELOPE_DRIFT")
        need(cp.pb.parse_boot_v3(boot, "name")["kernel"] == payload, "BOOT_PAYLOAD_DRIFT")
        if not args.verify_boots:
            (args.out / name).write_bytes(boot)
        records[variant] = {"boot_sha256": cp.digest(boot), "boot_size": len(boot),
                            "payload_sha256": cp.digest(payload)}
    report = {"stage": "name", "source_commit": args.source_commit, "public_run": args.public_run,
              "members": records, "gate": "NAME_PRIVATE_IDENTITIES_VERIFIED",
              "partition_writes": 0}
    if args.verify_boots:
        need(report == json.loads((args.verify_boots / "identity.json").read_text()),
             "PRIVATE_INDEPENDENT_IDENTITY_DRIFT")
    d.save(args.out / "identity.json", report)
    print(json.dumps(report, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("audit", "private"), default="audit")
    p.add_argument("--stage", choices=("name",), required=True)
    for name in ("frozen", "out", "bundle", "core", "verify-pair", "pair", "boot-base", "verify-boots"):
        p.add_argument("--" + name, type=Path)
    p.add_argument("--source-commit")
    p.add_argument("--public-run")
    args = p.parse_args()
    (audit if args.mode == "audit" else private)(args)


if __name__ == "__main__":
    main()
