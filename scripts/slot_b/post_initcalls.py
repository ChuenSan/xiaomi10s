#!/usr/bin/env python3
"""Actions-only, caller-specific checkpoints after initcalls and initramfs wait."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

import checkpoint as cp

TEXT_VA = 0xFFFF800080000000
PARENT_VA = TEXT_VA + 0x1B3103C
PARENT_END = TEXT_VA + 0x1B311A8
COLD_VA = TEXT_VA + 0x1B31174
CALLS = (
    (0x1B31138, "do_basic_setup", 0x1B311A8),
    (0x1B3113C, "wait_for_initramfs", 0x146C8),
    (0x1B31140, "console_on_rootfs", 0x1B30DA4),
)
STAGES = {
    "late_complete": {"offset": 0x1B3113C, "size": 56, "predecessor": "do_basic_setup",
                      "proof": "late_initcalls_completed", "unproved": "wait_for_initramfs_return"},
    "wait_complete": {"offset": 0x1B31140, "size": 52, "predecessor": "wait_for_initramfs",
                      "proof": "wait_for_initramfs_return", "unproved": "console_on_rootfs_entry"},
}
ELF_SHA = "295bfdb12184052a79c1aea35ce4a93a5833c42bdb7b4bd9173973312ade00ff"
EXPECTED_BODY = (
    0x97938D63, 0x97FFFF19, 0xD0001193, 0xF9455660, 0x9400941B,
    0x34000060, 0xF905567F, 0x940002D5, 0x9400AAEE, 0xA9424FF4,
    0xF9400BF5, 0xA8C37BFD, 0xD50323BF, 0xD65F03C0,
)


def need(condition, reason):
    cp.require(condition, reason)


def source_contract(main, config):
    match = re.search(r"static noinline void __init kernel_init_freeable\(void\)\s*\{(.*?)^\}",
                      main, re.S | re.M)
    need(match is not None, "CALLER_SOURCE_MISSING")
    body = re.sub(r"/\*.*?\*/", "", match[1], flags=re.S)
    need(re.search(r"do_basic_setup\(\);\s*kunit_run_all_tests\(\);\s*"
                   r"wait_for_initramfs\(\);\s*console_on_rootfs\(\);", body),
         "POST_INITCALL_SOURCE_ORDER_DRIFT")
    need(not re.search(r"^CONFIG_KUNIT=[ym]$", config, re.M), "KUNIT_CALL_NOT_EXCLUDED")
    setup = re.search(r"static void __init do_basic_setup\(void\)\s*\{(.*?)^\}",
                      main, re.S | re.M)
    need(setup is not None and re.search(r"do_initcalls\(\);\s*$", setup[1]),
         "BASIC_SETUP_NOT_ENDING_IN_INITCALLS")
    need("for (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++)" in main,
         "INITCALL_LEVEL_LOOP_DRIFT")
    return {"caller": "kernel_init_freeable", "source": "init/main.c",
            "sequence": [name for _, name, _ in CALLS], "kunit_compiled_out": True,
            "global_wait_entry_used": False, "caller_specific_return_boundary": True}


def gate_geometry(stage, offset, size):
    need(stage in STAGES, "UNKNOWN_POST_INITCALL_STAGE")
    spec = STAGES[stage]
    need(offset == spec["offset"] and size == spec["size"], "CALLSITE_GEOMETRY_DRIFT")
    need(PARENT_VA < TEXT_VA + offset < COLD_VA < PARENT_END, "CALLSITE_OUTSIDE_PARENT")
    need(TEXT_VA + offset + size == COLD_VA, "CALLSITE_CROSSES_LIVE_COLD_PATH")


def gate_call_sequence(parent, parent_offset=0x1B3103C):
    need(len(parent) == PARENT_END - PARENT_VA, "CALLER_SIZE_DRIFT")
    need(struct.unpack_from("<I", parent)[0] == 0xD503233F, "CALLER_PACIASP_DRIFT")
    for offset, name, target in CALLS:
        word = struct.unpack_from("<I", parent, offset - parent_offset)[0]
        need(word & 0xFC000000 == 0x94000000, f"CALLSITE_NOT_BL:{name}")
        need(cp.branch_target(word, TEXT_VA + offset) == TEXT_VA + target,
             f"CALL_TARGET_DRIFT:{name}")
    start = CALLS[1][0] - parent_offset
    need(struct.unpack_from("<14I", parent, start) == EXPECTED_BODY, "CALLER_TAIL_WORDS_DRIFT")


def gate_incoming(hits):
    need(not hits, f"CALLSITE_HAS_BYPASS_OR_INTERIOR_ENTRY:{hits[:8]}")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def audit(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    bundle = args.bundle
    metadata = json.loads((bundle / "bundle.json").read_text())
    need(metadata["linux_base"] == cp.pb.LINUX_BASE, "BUNDLE_LINUX_PIN_DRIFT")
    need(metadata["patch_queue_sha256"] == cp.pb.PATCH_QUEUE_SHA, "BUNDLE_PATCH_QUEUE_DRIFT")
    need(metadata["files"]["vmlinux"] == ELF_SHA, "BUNDLE_NOT_RECONCILED_ELF")
    for name in ("Image", "vmlinux", "System.map", "kernel.config"):
        need(cp.digest((bundle / name).read_bytes()) == metadata["files"][name],
             f"BUNDLE_IDENTITY_MISMATCH:{name}")
    frozen = args.frozen.read_bytes()
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    need(cp.digest(args.proven_core.read_bytes()) == cp.CORE_SHA, "PROVEN_CORE_DRIFT")
    core56 = cp.ultracompact_core(args.core56.read_bytes())
    core52 = cp.subsys52_core(args.core52.read_bytes())
    cp.gate_subsys52_core_equivalence(core56, core52)
    image = (bundle / "Image").read_bytes()
    need(len(image) == cp.t3.FIX8_IMAGE_FILE_SIZE, "BUNDLE_IMAGE_SIZE_DRIFT")
    vmlinux = bundle / "vmlinux"
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    need(cp.t3.nm_symbol(nm, "_text") == TEXT_VA, "TEXT_VA_DRIFT")
    need(cp.t3.symbol_extent(nm, "kernel_init_freeable") == (PARENT_VA, PARENT_END),
         "CALLER_EXTENT_DRIFT")
    sections = cp.t3.section_map(out, cp.TOOLS, vmlinux)
    source = source_contract((cp.pb.LINUX / "init/main.c").read_text(),
                             (bundle / "kernel.config").read_text())
    source["initcall_levels"] = cp.audit_initcall_source(cp.pb.LINUX)
    for offset, name, target in CALLS:
        need(cp.t3.nm_symbol(nm, name) == TEXT_VA + target, f"CALLEE_SYMBOL_DRIFT:{name}")
        need(cp.t3.sysmap_symbol(bundle / "System.map", name) == TEXT_VA + target,
             f"CALLEE_SYSTEM_MAP_DRIFT:{name}")
    lo, hi = PARENT_VA - TEXT_VA, PARENT_END - TEXT_VA
    parent = frozen[lo:hi]
    need(parent == image[lo:hi] == cp.vmlinux_bytes_at(vmlinux, sections, PARENT_VA, hi - lo),
         "CALLER_NOT_BYTE_EXACT")
    gate_call_sequence(parent)
    basic_va, basic_end = cp.t3.symbol_extent(nm, "do_basic_setup")
    basic = frozen[basic_va - TEXT_VA:basic_end - TEXT_VA]
    need(basic == image[basic_va - TEXT_VA:basic_end - TEXT_VA], "BASIC_SETUP_NOT_BYTE_EXACT")
    need(cp.branch_target(struct.unpack_from("<I", basic, 24)[0], basic_va + 24)
         == cp.t3.nm_symbol(nm, "do_initcalls"), "BASIC_SETUP_INITCALLS_CALL_DRIFT")
    late_start = cp.t3.nm_symbol(nm, "__initcall7_start")
    late_end = cp.t3.nm_symbol(nm, "__initcall_end")
    late = cp.decode_initcall_span(vmlinux, sections, nm, late_start, late_end)
    need(len(late) == 86, "LATE_TABLE_COUNT_DRIFT")
    need(late[0]["symbol"] == "kernel_do_mounts_initrd_sysctls_init", "LATE_FIRST_ENTRY_DRIFT")
    offset, size = (STAGES[args.symbol][key] for key in ("offset", "size"))
    gate_geometry(args.symbol, offset, size)
    window = (TEXT_VA + offset, TEXT_VA + offset + size)
    ranges = [(s["vma"] - TEXT_VA, s["vma"] - TEXT_VA + s["size"])
              for s in sections if s["alloc"] and s["code"]]
    incoming = cp.incoming_inclusive(frozen[:len(image)], ranges, TEXT_VA, *window)
    gate_incoming(incoming)
    cp.t3.gate_window_symbol_scan(window[0], size, [va for va, _ in cp.t3.symbol_table(nm)])
    cp.t3.gate_window_section_scan(window[0], size, sections)
    cp.t3.gate_function_extent_scan(window[0], size, PARENT_END)
    cp.t3.gate_window_literal_scan(window[0] - 1, size + 1, frozen[:len(image)])
    sites = cp.relocation_sites(vmlinux, sections)
    cp.t3.gate_window_relocation_scan(window[0], size, sites)
    rewrites = cp.audit_rewrites(out, vmlinux, sections, window)
    for name, start, end in (("caller", PARENT_VA, PARENT_END),
                             ("basic-setup", basic_va, basic_end),
                             ("initcalls", *cp.t3.symbol_extent(nm, "do_initcalls")),
                             ("window", *window)):
        dump = cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={start:#x}",
                          f"--stop-address={end:#x}", str(vmlinux)])
        (out / f"{name}.txt").write_text(dump)
        if name == "window":
            cp.t3.gate_window_bytes_agree(window[0], offset, dump, frozen, size // 4)
    image_size = cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    cp.t3.gate_window_inside_image_size(offset, size, image_size)
    dtb_offset, _ = cp.pb.calc_dtb_offset(image_size)
    cp.pb.gate_rt_d(frozen[dtb_offset:])
    chosen = cp.rt.parse_fdt(frozen[dtb_offset:])["/chosen"]
    cp.gate_builtin_initramfs_source(chosen)
    need(cp.digest(vmlinux.read_bytes()) == ELF_SHA, "AUDIT_MUTATED_ELF")
    report = {"symbol": args.symbol, "source_commit": os.environ["GITHUB_SHA"],
              "bundle_run": "35040148509", "bundle": metadata,
              "target_symbol": "kernel_init_freeable", "target_va": hex(window[0]),
              "offset": offset, "checkpoint_size": size, "core_size": size,
              "parent_va": hex(PARENT_VA), "parent_end": hex(PARENT_END),
              "cold_path_va": hex(COLD_VA), "caller_byte_exact": True,
              "predecessor": STAGES[args.symbol]["predecessor"],
              "source_contract": source, "late_entry_count": len(late),
              "probe_architecture": "INLINE_CALLSITE_NO_ADDED_LANDING_PAD",
              "window_agreement": "EXACT", "incoming_inclusive": incoming,
              "relocation_sites_checked": len(sites), "runtime_rewrites": rewrites,
              "audit_elf_unchanged": True, "inline_only": True,
              "trampoline_permitted": False, "prel32_target_unchanged": True,
              "runtime_dtb_external_initrd": False, "init_executed": "NOT_PROVEN",
              "normal_boot_candidate": False, "kernel_rebuilt": False,
              "device_operation": False, "positive_proves": STAGES[args.symbol]["proof"],
              "positive_does_not_prove": STAGES[args.symbol]["unproved"]}
    write_json(out / "audit.json", report)
    write_json(out / "late-table.json", late)
    return frozen, core56 if size == 56 else core52, report


def check_member(payload, frozen, core, report, manifest, delay):
    offset, size = report["offset"], report["checkpoint_size"]
    need(len(payload) == len(frozen) == manifest["payload_size"], "MEMBER_SIZE_DRIFT")
    need(payload[:offset] == frozen[:offset] and payload[offset + size:] == frozen[offset + size:],
         "MEMBER_CHANGED_OUTSIDE_WINDOW")
    need(payload[offset:offset + size] == cp.delay_core(core, delay), "MEMBER_CORE_OR_DELAY_DRIFT")
    need(cp.digest(payload) == manifest["payload_sha256"], "MEMBER_SHA_DRIFT")
    need(manifest["delay_seconds"] == delay, "MEMBER_DELAY_MANIFEST_DRIFT")
    need(manifest["checkpoint_sha256"] == cp.digest(payload[offset:offset + size]),
         "MEMBER_CHECKPOINT_SHA_DRIFT")
    for key, value in report.items():
        need(manifest.get(key) == value, f"MEMBER_AUDIT_DRIFT:{key}")
    cp.t3.gate_tramp_identity(payload)


def process_pair(args, frozen, core, report):
    root = args.verify_pair if args.verify_pair else args.out / "pair"
    shas = {}
    payloads = []
    for delay in (8, 1):
        directory = root / str(delay) / "checkpoint"
        if args.verify_pair:
            payload = (directory / "payload.bin").read_bytes()
            manifest = json.loads((directory / "manifest.json").read_text())
        else:
            directory.mkdir(parents=True, exist_ok=False)
            probe = cp.delay_core(core, delay)
            payload = cp.patch_window(frozen, report["offset"], probe)
            manifest = {**report, "run_id": os.environ["GITHUB_RUN_ID"],
                        "delay_seconds": delay, "payload_size": len(payload),
                        "payload_sha256": cp.digest(payload), "checkpoint_sha256": cp.digest(probe)}
            (directory / "payload.bin").write_bytes(payload)
            (directory / "checkpoint.bin").write_bytes(probe)
            write_json(directory / "manifest.json", manifest)
        check_member(payload, frozen, core, report, manifest, delay)
        shas[str(delay)] = cp.digest(payload)
        payloads.append(payload)
    changed = [i for i, (a, b) in enumerate(zip(*payloads)) if a != b]
    delta_slot = 8 if len(core) == 56 else 4
    need(changed == [report["offset"] + delta_slot + 1, report["offset"] + delta_slot + 2],
         "PAIR_NOT_DELAY_ONLY")
    identity = {"symbol": args.symbol, "source_commit": os.environ["GITHUB_SHA"],
                "bundle_run": "35040148509", "payload_shas": shas, "changed_offsets": changed,
                "expected_delta_s": -7, "device_operation": False, "kernel_rebuilt": False}
    if args.verify_pair:
        actual = json.loads((root / "pair.json").read_text())
        for key, value in identity.items():
            need(actual.get(key) == value, f"PAIR_IDENTITY_DRIFT:{key}")
    else:
        identity["public_run"] = os.environ["GITHUB_RUN_ID"]
        write_json(root / "pair.json", identity)
    write_json(args.out / "verification.json", identity)
    print(json.dumps(identity, indent=2), flush=True)
    print("POST_INITCALLS_INDEPENDENT_REVERIFY=PASS" if args.verify_pair else
          "POST_INITCALLS_PAIR_AUDIT=PASS", flush=True)
    print("PAIR_DIFF=DELAY_CONSTANT_ONLY\nKERNEL_REBUILD=NO\nDEVICE_OPERATION=NO", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=STAGES, required=True)
    for name in ("bundle", "frozen", "proven-core", "core56", "core52", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--verify-pair", type=Path)
    args = parser.parse_args()
    frozen, core, report = audit(args)
    process_pair(args, frozen, core, report)


if __name__ == "__main__":
    main()
