#!/usr/bin/env python3
"""Actions-only, fixed callsite probes inside deferred_probe_initcall."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

import checkpoint as cp

TEXT = 0xFFFF800080000000
PARENT = 0x8E7564
PARENT_SIZE = 492
ELF_SHA = "295bfdb12184052a79c1aea35ce4a93a5833c42bdb7b4bd9173973312ade00ff"
BASE_BOOT_SHA = "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5"
BOOT_SIZE = 37380096
CORE_SHA = "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5"
STAGES = {
    "prequeue": {
        "offset": 0x8E7614, "predecessor": "mutex_unlock", "callee": 0x10C733C,
        "proof": "deferred_first_trigger_prequeue_reached",
        "unproved": "deferred_first_work_queued",
        "words": (0xD000A397, 0xD000BD54, 0x91310294, 0xF94486E1,
                  0x52802000, 0xAA1403E2, 0x97DF1032, 0xAA1403E0,
                  0x97DF1518, 0xB000C908, 0x52800029, 0xAA1303E0,
                  0x3931E509, 0x941F7F1F),
    },
    "postflush": {
        "offset": 0x8E76B8, "predecessor": "flush_work", "callee": 0xACA94,
        "proof": "deferred_second_flush_returned",
        "unproved": "deferred_probe_initcall_returned",
        "words": (0xD000BD48, 0xB94C6108, 0x7100051F, 0x5400014B,
                  0x52801F49, 0xD000BD42, 0x9131A042, 0x1B097D08,
                  0xD000A389, 0x52802000, 0xF9447521, 0x93407D03,
                  0x97DF1194, 0xA9434FF4),
    },
}
need = cp.require


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def source_contract(source, config):
    body = re.search(r"static int deferred_probe_initcall\(void\)\s*\{(.*?)^\}",
                     source, re.S | re.M)
    need(body is not None, "DEFERRED_PARENT_SOURCE_MISSING")
    need("late_initcall(deferred_probe_initcall);" in source, "REGISTRATION_DRIFT")
    need("CONFIG_MODULES=y" in config.splitlines(), "MODULES_CONFIG_DRIFT")
    code = re.sub(r"/\*.*?\*/", "", body[1], flags=re.S)
    need(re.search(r"driver_deferred_probe_enable = true;\s*"
                   r"driver_deferred_probe_trigger\(\);\s*"
                   r"flush_work\(&deferred_probe_work\);\s*initcalls_done = true;", code),
         "FIRST_TRIGGER_FLUSH_ORDER_DRIFT")
    need(code.count("driver_deferred_probe_trigger();") == 2 and
         code.count("flush_work(&deferred_probe_work);") == 2, "TRIGGER_FLUSH_COUNT_DRIFT")
    need(code.rfind("flush_work(&deferred_probe_work);") <
         code.index("schedule_delayed_work("), "SECOND_FLUSH_ORDER_DRIFT")


def gate_window(stage, offset, original):
    need(stage in STAGES, "UNAUTHORIZED_CALLSITE")
    spec = STAGES[stage]
    need(offset == spec["offset"] and len(original) == 56, "CALLSITE_GEOMETRY_DRIFT")
    need(struct.unpack("<14I", original) == spec["words"], "ORIGINAL_WINDOW_DRIFT")
    need(PARENT + 60 <= offset < offset + 56 <= PARENT + PARENT_SIZE,
         "FROZEN_ENTRY_OVERLAP_OR_PARENT_ESCAPE")


def gate_member(stage, frozen, payload, manifest):
    spec = STAGES[stage]
    offset = spec["offset"]
    delay = manifest["delay_seconds"]
    need(delay in (8, 1), "DELAY_NOT_ALLOWED")
    need(len(payload) == len(frozen) == cp.t3.FIX8_PAYLOAD_SIZE, "PAYLOAD_SIZE_DRIFT")
    need(payload[:offset] == frozen[:offset] and payload[offset + 56:] == frozen[offset + 56:],
         "CHANGE_OUTSIDE_CALLSITE")
    core = struct.pack("<14I", *cp.ULTRACOMPACT_WORDS)
    need(payload[offset:offset + 56] == cp.delay_core(core, delay), "CORE_OR_DELAY_DRIFT")
    for key, value in {"stage": stage, "offset": offset, "window": 56,
                       "parent": "deferred_probe_initcall", "parent_offset": PARENT,
                       "parent_size": PARENT_SIZE, "section": ".text",
                       "inline_only": True, "normal_boot_candidate": False,
                       "frozen_payload_sha256": cp.t3.FIX8_PAYLOAD_SHA,
                       "payload_sha256": cp.digest(payload)}.items():
        need(manifest.get(key) == value, f"MANIFEST_DRIFT:{key}")
    need(manifest.get("checkpoint_sha256") == cp.digest(payload[offset:offset + 56]),
         "CHECKPOINT_IDENTITY_DRIFT")
    cp.t3.gate_tramp_identity(payload)


def gate_pair(stage, payloads, identity):
    offset = STAGES[stage]["offset"]
    changed = [i for i, (a, b) in enumerate(zip(*payloads)) if a != b]
    need(len(payloads[0]) == len(payloads[1]), "PAIR_SIZE_MISMATCH")
    need(changed == [offset + 9, offset + 10], "PAIR_NOT_DELAY_ONLY")
    need(identity["stage"] == stage and identity["changed_offsets"] == changed,
         "PAIR_MANIFEST_DRIFT")
    need(identity["payload_shas"] == {str(d): cp.digest(p) for d, p in zip((8, 1), payloads)},
         "PAIR_SHA_DRIFT")


def audit(args):
    args.out.mkdir(parents=True, exist_ok=False)
    bundle = args.bundle
    metadata = json.loads((bundle / "bundle.json").read_text())
    need(metadata["linux_base"] == cp.pb.LINUX_BASE, "BUNDLE_LINUX_PIN_DRIFT")
    need(metadata["patch_queue_sha256"] == cp.pb.PATCH_QUEUE_SHA, "PATCH_QUEUE_DRIFT")
    need(metadata["files"]["vmlinux"] == ELF_SHA, "BUNDLE_ELF_DRIFT")
    for name in ("Image", "vmlinux", "System.map", "kernel.config"):
        need(cp.digest((bundle / name).read_bytes()) == metadata["files"][name],
             f"BUNDLE_IDENTITY:{name}")
    frozen = args.frozen.read_bytes()
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    core = cp.ultracompact_core(args.core.read_bytes())
    need(cp.digest(core) == CORE_SHA, "FROZEN_CORE_DRIFT")
    image = (bundle / "Image").read_bytes()
    vmlinux = bundle / "vmlinux"
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    need(cp.t3.nm_symbol(nm, "_text") == TEXT, "TEXT_VA_DRIFT")
    need(cp.t3.symbol_extent(nm, "deferred_probe_initcall") ==
         (TEXT + PARENT, TEXT + PARENT + PARENT_SIZE), "PARENT_EXTENT_DRIFT")
    sections = cp.t3.section_map(args.out, cp.TOOLS, vmlinux)
    source_contract((cp.pb.LINUX / "drivers/base/dd.c").read_text(),
                    (bundle / "kernel.config").read_text())
    need(image[PARENT:PARENT + PARENT_SIZE] == cp.vmlinux_bytes_at(
        vmlinux, sections, TEXT + PARENT, PARENT_SIZE), "PARENT_ELF_IMAGE_DISAGREEMENT")
    literals = cp.prove_fs_complete_window_literals(image, frozen, TEXT, PARENT, PARENT_SIZE)
    need(len(literals) == 1 and literals[0]["word_offset"] == 0x1C and
         literals[0]["layout_delta"] == 8, "PARENT_LITERAL_EXCEPTION_DRIFT")
    start = cp.t3.nm_symbol(nm, "__initcall7_start")
    end = cp.t3.nm_symbol(nm, "__initcall_end")
    entries = cp.decode_initcall_span(vmlinux, sections, nm, start, end)
    need(len(entries) == 86 and entries[54]["symbol"] == "deferred_probe_initcall",
         "LATE_INDEX54_REGISTRATION_DRIFT")
    spec = STAGES[args.stage]
    offset = spec["offset"]
    gate_window(args.stage, offset, frozen[offset:offset + 56])
    need(image[offset - 4:offset + 56] == frozen[offset - 4:offset + 56],
         "CALLSITE_NOT_BYTE_EXACT")
    word = struct.unpack_from("<I", frozen, offset - 4)[0]
    need(word & 0xFC000000 == 0x94000000 and
         cp.branch_target(word, TEXT + offset - 4) == TEXT + spec["callee"],
         "PREDECESSOR_CALL_DRIFT")
    need(cp.t3.nm_symbol(nm, spec["predecessor"]) == TEXT + spec["callee"],
         "PREDECESSOR_SYMBOL_DRIFT")
    window = (TEXT + offset, TEXT + offset + 56)
    ranges = [(s["vma"] - TEXT, s["vma"] - TEXT + s["size"])
              for s in sections if s["alloc"] and s["code"]]
    incoming = cp.incoming_inclusive(frozen[:len(image)], ranges, TEXT, *window)
    need(not incoming, f"CALLSITE_BYPASS_OR_INTERIOR_ENTRY:{incoming[:8]}")
    cp.t3.gate_window_symbol_scan(window[0], 56, [va for va, _ in cp.t3.symbol_table(nm)])
    cp.t3.gate_window_section_scan(window[0], 56, sections)
    cp.t3.gate_function_extent_scan(window[0], 56, TEXT + PARENT + PARENT_SIZE)
    cp.t3.gate_window_literal_scan(window[0] - 1, 57, frozen[:len(image)])
    cp.t3.gate_window_relocation_scan(window[0], 56, cp.relocation_sites(vmlinux, sections))
    rewrites = cp.audit_rewrites(args.out, vmlinux, sections, window)
    dump = cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={TEXT + PARENT:#x}",
                      f"--stop-address={TEXT + PARENT + PARENT_SIZE:#x}", str(vmlinux)])
    (args.out / "original-function.txt").write_text(dump)
    image_size = cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    cp.t3.gate_window_inside_image_size(offset, 56, image_size)
    dtb_offset, _ = cp.pb.calc_dtb_offset(image_size)
    cp.pb.gate_rt_d(frozen[dtb_offset:])
    cp.gate_builtin_initramfs_source(cp.rt.parse_fdt(frozen[dtb_offset:])["/chosen"])
    report = {"stage": args.stage, "source_commit": os.environ["GITHUB_SHA"],
              "parent": "deferred_probe_initcall", "parent_offset": PARENT,
              "parent_size": PARENT_SIZE, "section": ".text", "late_index": 54,
              "offset": offset, "window": 56, "inline_only": True,
              "normal_boot_candidate": False, "positive_proves": spec["proof"],
              "positive_does_not_prove": spec["unproved"],
              "frozen_payload_sha256": cp.t3.FIX8_PAYLOAD_SHA,
              "entry_probe_rerun": False, "predecessor": spec["predecessor"],
              "incoming": incoming, "runtime_rewrites": rewrites,
              "parent_literal_exception": literals, "window_agreement": "EXACT",
              "probe_family": "INLINE_CALLSITE_56B_NO_ADDED_PAD",
              "core_sha256": CORE_SHA, "partition_writes": 0}
    save(args.out / "audit.json", report)
    payloads = []
    root = args.verify_pair if args.verify_pair else args.out / "pair"
    for delay in (8, 1):
        member = root / str(delay)
        if args.verify_pair:
            payload = (member / "payload.bin").read_bytes()
            manifest = json.loads((member / "manifest.json").read_text())
            for key, value in report.items():
                need(manifest.get(key) == value, f"REAUDIT_MANIFEST_DRIFT:{key}")
        else:
            member.mkdir(parents=True, exist_ok=False)
            probe = cp.delay_core(core, delay)
            payload = cp.patch_window(frozen, offset, probe)
            manifest = {**report, "delay_seconds": delay, "payload_sha256": cp.digest(payload),
                        "checkpoint_sha256": cp.digest(probe)}
            (member / "payload.bin").write_bytes(payload)
            save(member / "manifest.json", manifest)
        gate_member(args.stage, frozen, payload, manifest)
        payloads.append(payload)
    identity = {"stage": args.stage, "source_commit": os.environ["GITHUB_SHA"],
                "public_run": os.environ["GITHUB_RUN_ID"], "expected_delta_s": -7,
                "changed_offsets": [offset + 9, offset + 10],
                "payload_shas": {str(d): cp.digest(p) for d, p in zip((8, 1), payloads)}}
    if args.verify_pair:
        actual = json.loads((root / "pair.json").read_text())
        gate_pair(args.stage, payloads, actual)
        need(actual == identity, "REVERIFY_PAIR_IDENTITY_DRIFT")
    else:
        gate_pair(args.stage, payloads, identity)
        save(root / "pair.json", identity)
    save(args.out / "verified.json", identity)
    print(json.dumps(identity, indent=2))
    print("DEFERRED_CALLSITE_CI_READY=YES\nPAIR_DIFF=DELAY_CONSTANT_ONLY\n"
          "LOCAL_BUILD=NO\nKERNEL_REBUILD=NO\nDEVICE_OPERATION=NO")


def gate_boot(stage, frozen, payload, boot, base):
    offset = 4096 + STAGES[stage]["offset"]
    need(cp.digest(base) == BASE_BOOT_SHA and len(base) == BOOT_SIZE, "BASE_BOOT_DRIFT")
    need(cp.pb.parse_boot_v3(base, "FIX8")["kernel"] == frozen, "BASE_PAYLOAD_DRIFT")
    need(len(boot) == BOOT_SIZE, "BOOT_SIZE_DRIFT")
    need(boot[:offset] == base[:offset] and boot[offset + 56:] == base[offset + 56:],
         "BOOT_CHANGE_OUTSIDE_CALLSITE")
    need(cp.pb.parse_boot_v3(boot, "candidate")["kernel"] == payload, "BOOT_PAYLOAD_DRIFT")


def private(args):
    need(os.environ.get("GITHUB_REPOSITORY") == "ChuenSan/thyme-mainline-private-ci",
         "OEM_ENVELOPE_PRIVATE_ONLY")
    frozen = args.frozen.read_bytes()
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    base = args.boot_base.read_bytes()
    need(cp.digest(base) == BASE_BOOT_SHA, "BASE_BOOT_DRIFT")
    identity = json.loads((args.pair / "pair.json").read_text())
    need(identity["source_commit"] == args.source_commit, "PUBLIC_COMMIT_DRIFT")
    need(identity["public_run"] == args.public_run, "PUBLIC_RUN_DRIFT")
    args.out.mkdir(parents=True, exist_ok=False)
    payloads, boots, records = [], [], {}
    for delay in (8, 1):
        member = args.pair / str(delay)
        payload = (member / "payload.bin").read_bytes()
        manifest = json.loads((member / "manifest.json").read_text())
        need(manifest["source_commit"] == args.source_commit and
             manifest["delay_seconds"] == delay, "MEMBER_SOURCE_OR_DELAY_DRIFT")
        gate_member(args.stage, frozen, payload, manifest)
        name = f"defer-{args.stage}{delay}-boot.img"
        if args.verify_boots:
            boot = (args.verify_boots / name).read_bytes()
        else:
            boot = base[:4096] + payload + base[4096 + len(payload):]
        gate_boot(args.stage, frozen, payload, boot, base)
        if not args.verify_boots:
            (args.out / name).write_bytes(boot)
        records[str(delay)] = {"boot_sha256": cp.digest(boot), "boot_size": len(boot),
                              "payload_sha256": cp.digest(payload)}
        payloads.append(payload)
        boots.append(boot)
    gate_pair(args.stage, payloads, identity)
    changed = [i for i, (a, b) in enumerate(zip(*boots)) if a != b]
    need(changed == [4096 + i for i in identity["changed_offsets"]], "BOOT_PAIR_NOT_DELAY_ONLY")
    report = {"stage": args.stage, "source_commit": args.source_commit,
              "public_run": args.public_run, "members": records,
              "boot_changed_offsets": changed, "base_boot_sha256": BASE_BOOT_SHA,
              "gate": "DEFERRED_PRIVATE_PAIR_VERIFIED", "partition_writes": 0}
    if args.verify_boots:
        need(report == json.loads((args.verify_boots / "identity.json").read_text()),
             "PRIVATE_INDEPENDENT_IDENTITY_DRIFT")
    save(args.out / "identity.json", report)
    print(json.dumps(report, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("audit", "private"), default="audit")
    p.add_argument("--stage", choices=STAGES, required=True)
    p.add_argument("--frozen", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name in ("bundle", "core", "verify-pair", "pair", "boot-base", "verify-boots"):
        p.add_argument("--" + name, type=Path)
    p.add_argument("--source-commit")
    p.add_argument("--public-run")
    args = p.parse_args()
    (audit if args.mode == "audit" else private)(args)


if __name__ == "__main__":
    main()
