#!/usr/bin/env python3
"""Actions-only terminal checkpoint after the worker's original kfree returns."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_selected_probe as selected

cp = selected.cp
need = cp.require
save = selected.save
canonical = selected.canonical
gate_fields = selected.gate_fields
gate_actions = selected.gate_actions
gate_authority = selected.gate_authority
gate_bundle = selected.gate_bundle
gate_sections = selected.gate_sections
gate_exception_destinations = selected.gate_exception_destinations
TEXT = selected.TEXT
PARENT = 0x8E8424
PARENT_SIZE = 196
OFFSET = 0x8E848C
WINDOW = 56
END = 0x8E84C4
EMPTY_BRANCH = 0x8E8454
EMPTY_TARGET = 0x8E84C8
BACKEDGE = 0x8E84C4
LOOP_TARGET = 0x8E8460
GET_DEVICE_CALL = 0x8E847C
KFREE_CALL = 0x8E8488
REASON_CLEAR_STORE = 0x8E8494
ORIGINAL = selected.ORIGINAL
CORE = selected.CORE
CORE_SHA = selected.CORE_SHA
BASE_BOOT_SHA = selected.BASE_BOOT_SHA
BOOT_SIZE = selected.BOOT_SIZE
PUBLIC_REPOSITORY = selected.PUBLIC_REPOSITORY
PRIVATE_REPOSITORY = selected.PRIVATE_REPOSITORY
BUNDLE_RUN = selected.BUNDLE_RUN
BUNDLE_FILES = selected.BUNDLE_FILES
BUNDLE_IDENTITY = selected.BUNDLE_IDENTITY
CODE_RANGES = selected.CODE_RANGES
RUNTIME_TABLES = selected.RUNTIME_TABLES
SOURCE_FILES = (*selected.SOURCE_FILES, "drivers/base/core.c")
CASES = {8: "defer_afterfree8", 1: "defer_afterfree1"}
BOOT_NAMES = {8: "defer-afterfree8-boot.img", 1: "defer-afterfree1-boot.img"}
WINDOW_WORDS = (
    0xF9402688, 0xAA1303E0, 0xF900611F, 0x941F7BA9, 0xAA1403E0,
    0x97FFD7EC, 0xAA1403E0, 0x97FFF302, 0xAA1303E0, 0x941F7B85,
    0xAA1403E0, 0x97FFD9FB, 0xF94002A8, 0xEB15011F,
)
REASON_LOADS = {0x8E8480: 0xF9402688, 0x8E8484: 0xF9406100}
CALL_TARGETS = {
    name: {"call_offset": offset, "target": cp.branch_target(
        struct.unpack_from("<I", ORIGINAL, offset - PARENT)[0], TEXT + offset)}
    for name, offset in (("get_device", GET_DEVICE_CALL), ("kfree", KFREE_CALL))
}
SCOPE = {
    "stage": "after_kfree", "parent": "deferred_probe_work_func", "parent_offset": PARENT,
    "parent_size": PARENT_SIZE, "offset": OFFSET, "window": WINDOW, "window_end": END,
    "section": ".text", "inline_only": True, "normal_boot_candidate": False,
    "late_index": None, "activation_initcall_index": 54,
    "positive_proves": "deferred_reason_kfree_returned",
    "positive_does_not_prove": "deferred_first_bus_probe_entered",
    "positive_only": ["deferred_probe_mutex_acquired", "active_list_nonempty",
                      "first_active_device_pointer_loaded_into_x20", "list_del_init_completed",
                      "get_device_returned", "reason_pointer_loads", "kfree_returned"],
    "positive_not_proven": ["device_pointer_nonnull_or_valid", "device_identity_or_name",
                            "get_device_reference_success", "deferred_reason_nonnull_or_valid",
                            "allocation_freed", "deferred_reason_field_cleared", "worker_mutex_unlocked",
                            "device_pm_move_to_tail_called", "first_bus_probe_entered_or_returned",
                            "driver_probe_body", "culprit_or_root_cause", "late_initcalls_complete",
                            "init_or_userspace", "usb_enablement"],
    "first_nonempty_worker_iteration_only": True, "callback_first_activation_only": False,
    "predecessor": "original_bl_kfree_return", "predecessor_offset": KFREE_CALL,
    "original_calls": CALL_TARGETS,
    "original_reason_loads": [[offset, word] for offset, word in REASON_LOADS.items()],
    "get_device_return_value_checked": False, "reason_clear_store": REASON_CLEAR_STORE,
    "reason_field_cleared_at_checkpoint": False, "mutex_held_at_checkpoint": True,
    "added_pointer_or_name_dereferences": 0, "maximum_delay_seconds": 8,
    "probe_family": "FIRST_DEVICE_AFTER_KFREE_TERMINAL_INLINE_56B",
    "terminal_core": "PSCI_SYSTEM_RESET_OR_LOCAL_WFE_LOOP", "terminal_fallthrough": False,
    "retained_backedge": [BACKEDGE, LOOP_TARGET], "retained_backedge_reachable": False,
    "empty_list_branch": [EMPTY_BRANCH, EMPTY_TARGET], "empty_list_reaches_probe": False,
    "pac_and_frame_preserved": True, "outside_window_unchanged": True,
    "window_agreement": "EXACT", "parent_agreement": "ELF_IMAGE_FIX8_EXACT_196B",
    "parent_literal_exception": [], "original_parent_sha256": cp.digest(ORIGINAL),
    "core_sha256": CORE_SHA, "frozen_payload_sha256": cp.t3.FIX8_PAYLOAD_SHA,
    "bundle_run": BUNDLE_RUN, "bundle": BUNDLE_IDENTITY,
    "linux_base": cp.pb.LINUX_BASE, "patch_queue_sha256": cp.pb.PATCH_QUEUE_SHA,
    "runtime_rewrites": RUNTIME_TABLES, "exception_fixup_destinations": "CHECKED_FULL_PARENT",
    "incoming": [], "prefix_incoming": [[TEXT + BACKEDGE, TEXT + LOOP_TARGET]],
    "whole_code_scan": "FROZEN_AND_BUNDLE", "relocation_scan": "RELA_AND_RELR_FULL_PARENT",
    "rt_d_sha256": cp.pb.RT_D_SHA, "initramfs_source": "FROZEN_BUILTIN",
    "external_initrd": False, "trailer_unchanged": True,
    "entry_probe_rerun": False, "frozen_experiment_rerun": False,
    "partition_writes": 0, "device_operation": False,
}


def gate_stage(stage):
    need(stage == "after_kfree", "UNAUTHORIZED_AFTER_KFREE_STAGE")


def gate_delay(delay):
    need(type(delay) is int and delay in (8, 1), "DELAY_NOT_ALLOWED")


def source_contract(source, core_source, config):
    selected.source_contract(source, config)
    code = selected.uncomment(source)
    worker = selected.function_body(code, "deferred_probe_work_func")
    boundary = ("list_del_init(&private->deferred_probe);get_device(dev);"
                "__device_set_deferred_probe_reason(dev,NULL);"
                "mutex_unlock(&deferred_probe_mutex);device_pm_move_to_tail(dev);")
    need(boundary in worker and worker.count("__device_set_deferred_probe_reason(") == 1,
         "AFTER_KFREE_WORKER_SOURCE_ORDER_DRIFT")
    reason = selected.function_body(code, "__device_set_deferred_probe_reason")
    need(reason == "kfree(dev->p->deferred_probe_reason);dev->p->deferred_probe_reason=reason;",
         "KFREE_BEFORE_REASON_CLEAR_SOURCE_DRIFT")
    bodies = re.findall(r"^struct\s+device\s*\*\s*get_device\(struct\s+device\s*\*\s*dev\)"
                        r"\s*\{(.*?)^\}", selected.uncomment(core_source), re.S | re.M)
    need(len(bodies) == 1 and re.sub(r"\s+", "", bodies[0]) ==
         "returndev?kobj_to_dev(kobject_get(&dev->kobj)):NULL;", "GET_DEVICE_SOURCE_SEMANTICS_DRIFT")


def audit_sources(config):
    sources = selected.audit_sources(config)
    name = "drivers/base/core.c"
    actual = (cp.pb.LINUX / name).read_bytes()
    pinned = cp.pb.run(["git", "-C", str(cp.pb.LINUX), "show", f"{cp.pb.LINUX_BASE}:{name}"]).encode()
    need(actual == pinned, "PINNED_GET_DEVICE_SOURCE_DRIFT")
    source_contract((cp.pb.LINUX / "drivers/base/dd.c").read_text(), actual.decode(), config)
    return {**sources, name: cp.digest(actual)}


def gate_window(stage, offset, original):
    gate_stage(stage)
    need(offset == OFFSET and len(original) == WINDOW and offset + WINDOW == END == BACKEDGE and
         offset == KFREE_CALL + 4 and PARENT + 26 * 4 == offset and END + 9 * 4 == PARENT + PARENT_SIZE,
         "AFTER_KFREE_WINDOW_GEOMETRY_DRIFT")
    need(struct.unpack("<14I", original) == WINDOW_WORDS, "AFTER_KFREE_ORIGINAL_WINDOW_DRIFT")


def gate_worker(original):
    selected.gate_worker(original)
    gate_window("after_kfree", OFFSET, original[OFFSET - PARENT:END - PARENT])
    for offset, word in {GET_DEVICE_CALL: 0x97FFD9D7, KFREE_CALL: 0x97E57144,
                         REASON_CLEAR_STORE: 0xF900611F, **REASON_LOADS}.items():
        need(struct.unpack_from("<I", original, offset - PARENT)[0] == word,
             "ORIGINAL_GET_DEVICE_REASON_KFREE_ABI_DRIFT")


def gate_parent_agreement(elf, image, frozen):
    need(elf == image == frozen, "WORKER_ELF_IMAGE_FIX8_DISAGREEMENT")
    gate_worker(frozen)


def gate_call_targets(original, nm, sysmap):
    gate_worker(original)
    for name, expected in CALL_TARGETS.items():
        word = struct.unpack_from("<I", original, expected["call_offset"] - PARENT)[0]
        need(word & 0xFC000000 == 0x94000000, f"ORIGINAL_CALL_NOT_BL:{name}")
        need(cp.branch_target(word, TEXT + expected["call_offset"]) == expected["target"] ==
             cp.t3.nm_symbol(nm, name) == cp.t3.nm_symbol(sysmap, name),
             f"ORIGINAL_CALL_TARGET_DRIFT:{name}")


def gate_core(core, delay=8):
    gate_delay(delay)
    reference = cp.ultracompact_core(CORE)
    need(cp.digest(reference) == CORE_SHA, "FROZEN_CORE_REFERENCE_DRIFT")
    need(core == cp.delay_core(reference, delay), "AFTER_KFREE_CORE_OR_DELAY_DRIFT")
    words = struct.unpack("<14I", core)
    need(cp.branch_target(words[8], OFFSET + 32) == OFFSET + 16 and
         cp.branch_target(words[13], OFFSET + 52) == OFFSET + 48,
         "TERMINAL_CORE_LOCAL_BRANCH_DRIFT")
    need(words[9:14] == (0x52800120, 0x72B08000, 0xD4000003, 0xD503205F, 0x17FFFFFF),
         "TERMINAL_RESET_OR_WFE_CLOSURE_DRIFT")
    return core


def gate_frozen(frozen):
    selected.gate_frozen(frozen)
    gate_worker(frozen[PARENT:PARENT + PARENT_SIZE])
    cp.t3.gate_window_inside_image_size(OFFSET, WINDOW, cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"])


def gate_incoming(image, ranges):
    interior = cp.incoming_inclusive(image, ranges, TEXT, TEXT + PARENT + 4, TEXT + PARENT + PARENT_SIZE)
    window = cp.incoming_inclusive(image, ranges, TEXT, TEXT + OFFSET, TEXT + END)
    prefix = cp.incoming_inclusive(image, ranges, TEXT, TEXT + PARENT + 4, TEXT + OFFSET)
    need(not interior, f"AFTER_KFREE_WORKER_INTERIOR_ENTRY:{interior[:8]}")
    need(not window, f"AFTER_KFREE_INCOMING_ENTRY:{window[:8]}")
    need(prefix == [(TEXT + BACKEDGE, TEXT + LOOP_TARGET)], f"AFTER_KFREE_PREFIX_BYPASS:{prefix[:8]}")
    return window, prefix


def gate_relocation_sites(sites):
    return cp.t3.gate_window_relocation_scan(TEXT + PARENT - 7, PARENT_SIZE + 7, sites)


def gate_relocations(vmlinux, sections):
    gate_relocation_sites(cp.relocation_sites(vmlinux, sections))


def audit_binary(out, vmlinux, image, frozen):
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    sysmap = (vmlinux.parent / "System.map").read_text()
    symbols = {"_text": 0, "deferred_probe_work_func": PARENT,
               "deferred_probe_initcall": selected.deferred.PARENT, "mutex_lock": 0x10C72C4,
               "mutex_unlock": 0x10C733C, "deferred_probe_mutex": 0x2091C00,
               "deferred_probe_active_list": 0x2091C30}
    for name, offset in symbols.items():
        need(cp.t3.nm_symbol(nm, name) == cp.t3.nm_symbol(sysmap, name) == TEXT + offset,
             f"AFTER_KFREE_SYMBOL_IDENTITY:{name}")
    need(cp.t3.symbol_extent(nm, "deferred_probe_work_func") ==
         (TEXT + PARENT, TEXT + PARENT + PARENT_SIZE), "WORKER_EXTENT_DRIFT")
    sections = cp.t3.section_map(out, cp.TOOLS, vmlinux)
    ranges = gate_sections(sections, len(image))
    original = cp.vmlinux_bytes_at(vmlinux, sections, TEXT + PARENT, PARENT_SIZE)
    gate_parent_agreement(original, image[PARENT:PARENT + PARENT_SIZE], frozen[PARENT:PARENT + PARENT_SIZE])
    gate_call_targets(original, nm, sysmap)
    save(out / "original-call-targets.json", CALL_TARGETS)
    for binary in (image, frozen[:len(image)]):
        gate_incoming(binary, ranges)
        cp.t3.gate_window_literal_scan(TEXT + PARENT, PARENT_SIZE, binary)
    protected = (TEXT + PARENT, TEXT + PARENT + PARENT_SIZE)
    cp.t3.gate_window_symbol_scan(protected[0], PARENT_SIZE, [va for va, _ in cp.t3.symbol_table(nm)])
    cp.t3.gate_function_extent_scan(TEXT + OFFSET, WINDOW, protected[1])
    gate_relocations(vmlinux, sections)
    rewrites = cp.audit_rewrites(out, vmlinux, sections, protected)
    need(canonical(rewrites) == canonical(RUNTIME_TABLES), "RUNTIME_TABLE_IDENTITY_DRIFT")
    ex = next(section for section in sections if section["name"] == "__ex_table")
    gate_exception_destinations(cp.section_bytes(vmlinux, ex), ex["vma"], protected)
    start, end = (cp.t3.nm_symbol(nm, name) for name in ("__initcall7_start", "__initcall_end"))
    entries = cp.decode_initcall_span(vmlinux, sections, nm, start, end)
    need(len(entries) == 86 and entries[54]["symbol"] == "deferred_probe_initcall",
         "LATE_INDEX54_REGISTRATION_DRIFT")
    dump = cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={protected[0]:#x}",
                      f"--stop-address={protected[1]:#x}", str(vmlinux)])
    (out / "original-function.txt").write_text(dump)


def gate_manifest(payload, manifest, delay, source_commit, public_run):
    gate_delay(delay)
    gate_authority(source_commit, public_run)
    gate_fields(manifest, {**SCOPE, "case": CASES[delay], "delay_seconds": delay,
                          "source_commit": source_commit, "public_run": public_run,
                          "payload_sha256": cp.digest(payload),
                          "checkpoint_sha256": cp.digest(payload[OFFSET:END])}, "MANIFEST_DRIFT")
    files = manifest.get("source_files_sha256", {})
    need(isinstance(files, dict) and set(files) == set(SOURCE_FILES) and
         all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in files.values()),
         "SOURCE_FILE_IDENTITY_MISSING")
    need(set(manifest) == set(SCOPE) | {"case", "delay_seconds", "source_commit", "public_run",
                                      "payload_sha256", "checkpoint_sha256", "source_files_sha256"},
         "MANIFEST_FIELD_SET_DRIFT")


def gate_member(stage, frozen, payload, manifest, delay, source_commit, public_run):
    gate_stage(stage)
    gate_delay(delay)
    gate_authority(source_commit, public_run)
    need(len(payload) == len(frozen) == cp.t3.FIX8_PAYLOAD_SIZE, "PAYLOAD_SIZE_DRIFT")
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    gate_worker(frozen[PARENT:PARENT + PARENT_SIZE])
    need(payload[:OFFSET] == frozen[:OFFSET] and payload[END:] == frozen[END:],
         "CHANGE_OUTSIDE_AFTER_KFREE_WINDOW")
    gate_core(payload[OFFSET:END], delay)
    gate_manifest(payload, manifest, delay, source_commit, public_run)
    cp.t3.gate_tramp_identity(payload)


def pair_identity(payloads, manifests, source_commit, public_run):
    gate_authority(source_commit, public_run)
    need(len(payloads) == len(manifests) == 2, "PAIR_SIZE_MISMATCH")
    return {"stage": "after_kfree", "source_commit": source_commit, "public_run": public_run,
            "expected_delta_s": -7, "changed_offsets": [OFFSET + 9, OFFSET + 10],
            "cases": [CASES[8], CASES[1]],
            "payload_shas": {str(delay): cp.digest(payload) for delay, payload in zip((8, 1), payloads)},
            "manifest_shas": {str(delay): cp.digest(canonical(manifest))
                              for delay, manifest in zip((8, 1), manifests)}}


def gate_pair(stage, payloads, manifests, identity, source_commit, public_run):
    gate_stage(stage)
    gate_authority(source_commit, public_run)
    need(len(payloads) == len(manifests) == 2 and
         len(payloads[0]) == len(payloads[1]) == cp.t3.FIX8_PAYLOAD_SIZE, "PAIR_SIZE_MISMATCH")
    for delay, payload, manifest in zip((8, 1), payloads, manifests):
        gate_core(payload[OFFSET:END], delay)
        gate_manifest(payload, manifest, delay, source_commit, public_run)
    changed = [index for index, (first, second) in enumerate(zip(*payloads)) if first != second]
    need(changed == [OFFSET + 9, OFFSET + 10], "PAIR_NOT_DELAY_ONLY")
    need(cp.digest(payloads[0]) != cp.digest(payloads[1]), "PAIR_FULL_HASH_COLLISION")
    common = [{key: value for key, value in manifest.items() if key not in
               {"case", "delay_seconds", "payload_sha256", "checkpoint_sha256"}} for manifest in manifests]
    need(canonical(common[0]) == canonical(common[1]), "PAIR_AUDIT_METADATA_DRIFT")
    need(canonical(identity) == canonical(pair_identity(payloads, manifests, source_commit, public_run)),
         "PAIR_IDENTITY_DRIFT")


def audit(args):
    gate_actions()
    gate_stage(args.stage)
    source_commit, public_run = os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"]
    gate_authority(source_commit, public_run)
    need(args.source_commit in (None, source_commit), "PUBLIC_COMMIT_DRIFT")
    need(args.public_run in (None, public_run), "PUBLIC_RUN_DRIFT")
    metadata = json.loads((args.bundle / "bundle.json").read_text())
    files = {name: (args.bundle / name).read_bytes() for name in BUNDLE_FILES}
    gate_bundle(metadata, files)
    frozen = args.frozen.read_bytes()
    gate_frozen(frozen)
    core = gate_core(args.core.read_bytes())
    sources = audit_sources(files["kernel.config"].decode())
    args.out.mkdir(parents=True, exist_ok=False)
    audit_binary(args.out, args.bundle / "vmlinux", files["Image"], frozen)
    report = {**SCOPE, "source_commit": source_commit, "public_run": public_run, "source_files_sha256": sources}
    save(args.out / "audit.json", report)
    payloads, manifests = [], []
    root = args.verify_pair or args.out / "pair"
    for delay in (8, 1):
        member = root / str(delay)
        if args.verify_pair:
            payload = (member / "payload.bin").read_bytes()
            manifest = json.loads((member / "manifest.json").read_text())
            gate_fields(manifest, report, "REAUDIT_MANIFEST_DRIFT")
        else:
            probe = cp.delay_core(core, delay)
            payload = cp.patch_window(frozen, OFFSET, probe)
            manifest = {**report, "case": CASES[delay], "delay_seconds": delay,
                        "payload_sha256": cp.digest(payload), "checkpoint_sha256": cp.digest(probe)}
        gate_member(args.stage, frozen, payload, manifest, delay, source_commit, public_run)
        payloads.append(payload)
        manifests.append(manifest)
    identity = pair_identity(payloads, manifests, source_commit, public_run)
    if args.verify_pair:
        identity = json.loads((root / "pair.json").read_text())
    gate_pair(args.stage, payloads, manifests, identity, source_commit, public_run)
    if not args.verify_pair:
        for delay, payload, manifest in zip((8, 1), payloads, manifests):
            member = root / str(delay)
            member.mkdir(parents=True, exist_ok=False)
            (member / "payload.bin").write_bytes(payload)
            save(member / "manifest.json", manifest)
        save(root / "pair.json", identity)
    save(args.out / "verified.json", identity)
    print(json.dumps(identity, indent=2))
    print("DEFERRED_AFTER_KFREE_CI_READY=YES\nPAIR_DIFF=DELAY_CONSTANT_ONLY\n"
          "LOCAL_BUILD=NO\nKERNEL_REBUILD=NO\nDEVICE_OPERATION=NO")


def gate_boot_bytes(frozen, payload, boot, base):
    need(cp.pb.parse_boot_v3(base, "FIX8")["kernel"] == frozen, "BASE_PAYLOAD_DRIFT")
    need(len(boot) == len(base) == BOOT_SIZE, "BOOT_SIZE_DRIFT")
    offset = cp.pb.PAGE + OFFSET
    need(boot[:offset] == base[:offset] and boot[offset + WINDOW:] == base[offset + WINDOW:],
         "BOOT_ENVELOPE_OR_OUTSIDE_WINDOW_DRIFT")
    need(cp.pb.parse_boot_v3(boot, "after_kfree")["kernel"] == payload, "BOOT_PAYLOAD_DRIFT")
    need(boot == base[:cp.pb.PAGE] + payload + base[cp.pb.PAGE + len(payload):],
         "INDEPENDENT_BOOT_BYTES_DRIFT")


def gate_boot(stage, frozen, payload, boot, base):
    gate_stage(stage)
    need(cp.digest(base) == BASE_BOOT_SHA and len(base) == BOOT_SIZE, "BASE_BOOT_DRIFT")
    gate_boot_bytes(frozen, payload, boot, base)


def gate_boot_pair(boots):
    need(len(boots) == 2 and len(boots[0]) == len(boots[1]) == BOOT_SIZE, "BOOT_PAIR_SIZE_DRIFT")
    changed = [index for index, (first, second) in enumerate(zip(*boots)) if first != second]
    need(changed == [cp.pb.PAGE + OFFSET + 9, cp.pb.PAGE + OFFSET + 10], "BOOT_PAIR_NOT_DELAY_ONLY")
    need(cp.digest(boots[0]) != cp.digest(boots[1]), "BOOT_PAIR_FULL_HASH_COLLISION")
    return changed


def private(args):
    gate_actions(private=True)
    gate_stage(args.stage)
    gate_authority(args.source_commit, args.public_run)
    frozen = args.frozen.read_bytes()
    gate_frozen(frozen)
    base = args.boot_base.read_bytes()
    need(cp.digest(base) == BASE_BOOT_SHA and len(base) == BOOT_SIZE, "BASE_BOOT_DRIFT")
    identity = json.loads((args.pair / "pair.json").read_text())
    gate_fields(identity, {"source_commit": args.source_commit, "public_run": args.public_run},
                "PUBLIC_AUTHORITY_DRIFT")
    payloads, manifests, boots, records = [], [], [], {}
    for delay in (8, 1):
        member = args.pair / str(delay)
        payload = (member / "payload.bin").read_bytes()
        manifest = json.loads((member / "manifest.json").read_text())
        gate_member(args.stage, frozen, payload, manifest, delay, args.source_commit, args.public_run)
        expected = base[:cp.pb.PAGE] + payload + base[cp.pb.PAGE + len(payload):]
        boot = (args.verify_boots / BOOT_NAMES[delay]).read_bytes() if args.verify_boots else expected
        gate_boot(args.stage, frozen, payload, boot, base)
        need(boot == expected, "PRIVATE_INDEPENDENT_BOOT_DRIFT")
        payloads.append(payload)
        manifests.append(manifest)
        boots.append(boot)
        records[str(delay)] = {"case": CASES[delay], "boot_sha256": cp.digest(boot),
                              "boot_size": len(boot), "payload_sha256": cp.digest(payload)}
    gate_pair(args.stage, payloads, manifests, identity, args.source_commit, args.public_run)
    report = {"stage": "after_kfree", "source_commit": args.source_commit, "public_run": args.public_run,
              "members": records, "boot_changed_offsets": gate_boot_pair(boots), "base_boot_sha256": BASE_BOOT_SHA,
              "public_pair_sha256": cp.digest(canonical(identity)),
              "gate": "DEFERRED_AFTER_KFREE_PRIVATE_PAIR_VERIFIED", "partition_writes": 0,
              "normal_boot_candidate": False, "device_operation": False}
    if args.verify_boots:
        actual = json.loads((args.verify_boots / "identity.json").read_text())
        need(canonical(report) == canonical(actual), "PRIVATE_INDEPENDENT_IDENTITY_DRIFT")
    args.out.mkdir(parents=True, exist_ok=False)
    if not args.verify_boots:
        for delay, boot in zip((8, 1), boots):
            (args.out / BOOT_NAMES[delay]).write_bytes(boot)
    save(args.out / "identity.json", report)
    print(json.dumps(report, indent=2))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("audit", "private"), default="audit")
    result.add_argument("--stage", choices=("after_kfree",), required=True)
    result.add_argument("--frozen", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    for name in ("bundle", "core", "verify-pair", "pair", "boot-base", "verify-boots"):
        result.add_argument("--" + name, type=Path)
    result.add_argument("--source-commit")
    result.add_argument("--public-run")
    return result


def main():
    cli = parser()
    args = cli.parse_args()
    required = ("bundle", "core") if args.mode == "audit" else ("pair", "boot_base", "source_commit", "public_run")
    for name in required:
        if getattr(args, name) is None:
            cli.error("--" + name.replace("_", "-") + " is required in " + args.mode + " mode")
    forbidden = ("pair", "boot_base", "verify_boots") if args.mode == "audit" else ("bundle", "core", "verify_pair")
    for name in forbidden:
        if getattr(args, name) is not None:
            cli.error("--" + name.replace("_", "-") + " is not accepted in " + args.mode + " mode")
    (audit if args.mode == "audit" else private)(args)


if __name__ == "__main__":
    main()
