#!/usr/bin/env python3
"""Actions-only terminal probe after the first active device pointer load."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

import deferred_probe_checkpoints as deferred

cp = deferred.cp
need = cp.require
save = deferred.save
TEXT = deferred.TEXT
PARENT = 0x8E8424
PARENT_SIZE = 196
OFFSET = 0x8E8468
WINDOW = 56
END = OFFSET + WINDOW
EMPTY_BRANCH = 0x8E8454
EMPTY_TARGET = 0x8E84C8
BACKEDGE = 0x8E84C4
LOOP_TARGET = 0x8E8460
CORE_SHA = deferred.CORE_SHA
BASE_BOOT_SHA = deferred.BASE_BOOT_SHA
BOOT_SIZE = deferred.BOOT_SIZE
PUBLIC_REPOSITORY = "ChuenSan/xiaomi10s"
PRIVATE_REPOSITORY = "ChuenSan/thyme-mainline-private-ci"
BUNDLE_RUN = "35040148509"
PREFIX_WORDS = (
    0xD503233F, 0xA9BD7BFD, 0xF9000BF5, 0xA9024FF4, 0x910003FD,
    0xB000BD40, 0x91300000, 0x941F7BA1, 0xB000BD55, 0x9130C2B5,
    0xF94002A8, 0xEB15011F, 0x540003A0, 0xB000BD53, 0x91300273,
    0xA940250A, 0xF9401114,
)
WINDOW_WORDS = (
    0xAA1403E0, 0xF9000549, 0xF900012A, 0xF9000108, 0xF9000508,
    0x97FFD9D7, 0xF9402688, 0xF9406100, 0x97E57144, 0xF9402688,
    0xAA1303E0, 0xF900611F, 0x941F7BA9, 0xAA1403E0,
)
SUFFIX_WORDS = (
    0x97FFD7EC, 0xAA1403E0, 0x97FFF302, 0xAA1303E0, 0x941F7B85,
    0xAA1403E0, 0x97FFD9FB, 0xF94002A8, 0xEB15011F, 0x54FFFCE1,
    0xB000BD40, 0x91300000, 0x941F7B9B, 0xA9424FF4, 0xF9400BF5,
    0xA8C37BFD, 0xD50323BF, 0xD65F03C0,
)
ORIGINAL = struct.pack("<49I", *(PREFIX_WORDS + WINDOW_WORDS + SUFFIX_WORDS))
CORE = struct.pack("<14I", *cp.ULTRACOMPACT_WORDS)
BUNDLE_FILES = {
    "Image": "43fb1c9128bdf37a2a77eb88cfff234381340b098ebf1aea1eabb2741180cebb",
    "vmlinux": deferred.ELF_SHA,
    "System.map": "e3ed0234692c5dc80188996730bb13f2303fd2ecb573e303134df02b7f61b3ea",
    "kernel.config": "f947a2e44e60f5818e5e63ed3192d5eeca652b45665c6f4b13b3796cea359bfa",
}
BUNDLE_IDENTITY = {
    "linux_base": cp.pb.LINUX_BASE, "patch_queue_sha256": cp.pb.PATCH_QUEUE_SHA,
    "source_commit": "ba870dbdc094bdee08c67e465f229e67c36ac0b6", "run_id": "35036419486",
    "files": BUNDLE_FILES,
    "elf_export_reconciliation": {
        "original_vmlinux_sha256": "42c04b8dc386b2f378e20b2b67bc635e11c681e0e1ba7a3bbe8a076af27ca2ca",
        "archived_vmlinux_sha256": deferred.ELF_SHA,
        "image_reproduction": "EXACT_MATCH", "system_map_entries_matched": 167212,
        "cause": "llvm-objcopy --dump-section without output rewrote ELF container in place",
        "rebuild": False, "run_id": BUNDLE_RUN,
        "source_commit": "ef629df364a592dd63e83743dfc06bf69f15ae5c",
    },
}
SOURCE_FILES = ("drivers/base/dd.c", "arch/arm64/include/asm/extable.h",
                "arch/arm64/mm/extable.c")
CODE_RANGES = ((0, 0x10000), (0x10000, 0x10E4000),
               (0x1B17800, 0x1B1D000), (0x1B30000, 0x1BBB534),
               (0x1BBB534, 0x1BC6490))
RUNTIME_TABLES = {
    "__ex_table": {"entries": 994,
                   "sha256": "e93f6326dba119d9b5091b9c31295e47086ce45813b6f1a62dde0655ca65a9be"},
    "altinstructions": {"entries": 37287,
                        "sha256": "a98a9bc613c12519ea5fd8f1e168ede872af0d8474fa385df6bc1cc17fdc36a6"},
    "__jump_table": "ABSENT", "static_call_sites": "ABSENT", "kcfi_traps": "ABSENT",
}
SCOPE = {
    "stage": "selected", "parent": "deferred_probe_work_func", "parent_offset": PARENT,
    "parent_size": PARENT_SIZE, "offset": OFFSET, "window": WINDOW, "window_end": END,
    "section": ".text", "inline_only": True, "normal_boot_candidate": False,
    "late_index": None, "activation_initcall_index": 54,
    "positive_proves": "deferred_worker_device_pointer_loaded",
    "positive_does_not_prove": "deferred_first_bus_probe_entered",
    "positive_only": ["deferred_probe_mutex_acquired", "active_list_nonempty",
                      "first_active_device_pointer_loaded_into_x20"],
    "positive_not_proven": ["device_pointer_nonnull_or_valid", "device_identity_or_name",
                            "get_device_called", "first_bus_probe_entered_or_returned",
                            "driver_probe_body", "culprit_or_root_cause", "init_or_userspace"],
    "first_nonempty_worker_iteration_only": True, "callback_first_activation_only": False,
    "predecessor": "ldr_x20_from_first_active_entry", "predecessor_offset": OFFSET - 4,
    "mutex_held_at_checkpoint": True, "added_pointer_or_name_dereferences": 0,
    "probe_family": "FIRST_DEVICE_SELECTED_TERMINAL_INLINE_56B",
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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def gate_fields(actual, expected, label):
    need(isinstance(actual, dict), label)
    for key, value in expected.items():
        need(key in actual and canonical(actual[key]) == canonical(value), f"{label}:{key}")


def gate_stage(stage):
    need(stage == "selected", "UNAUTHORIZED_SELECTED_STAGE")


def gate_actions(private=False):
    need(os.environ.get("GITHUB_ACTIONS") == "true", "GITHUB_ACTIONS_REQUIRED")
    repository = PRIVATE_REPOSITORY if private else PUBLIC_REPOSITORY
    need(os.environ.get("GITHUB_REPOSITORY") == repository,
         "OEM_ENVELOPE_PRIVATE_ONLY" if private else "PUBLIC_AUDIT_REPOSITORY_DRIFT")


def gate_authority(source_commit, public_run):
    need(isinstance(source_commit, str) and re.fullmatch(r"[0-9a-f]{40}", source_commit),
         "PUBLIC_COMMIT_INVALID")
    need(isinstance(public_run, str) and re.fullmatch(r"[1-9][0-9]*", public_run),
         "PUBLIC_RUN_INVALID")


def gate_bundle(metadata, files):
    need(canonical(metadata) == canonical(BUNDLE_IDENTITY), "BUNDLE_IDENTITY_DRIFT")
    need(set(files) == set(BUNDLE_FILES), "BUNDLE_FILE_SET_DRIFT")
    for name, expected in BUNDLE_FILES.items():
        need(cp.digest(files[name]) == expected, f"BUNDLE_FILE_IDENTITY:{name}")


def gate_source_identity(head, queue_sha, actual, pinned):
    need(head == cp.pb.LINUX_BASE, "LINUX_SOURCE_PIN_DRIFT")
    need(queue_sha == cp.pb.PATCH_QUEUE_SHA, "PATCH_QUEUE_DRIFT")
    need(set(actual) == set(pinned) == set(SOURCE_FILES), "SOURCE_FILE_SET_DRIFT")
    for name in SOURCE_FILES:
        need(actual[name] == pinned[name], f"PINNED_SOURCE_DRIFT:{name}")


def uncomment(source):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


def function_body(source, name):
    bodies = re.findall(r"^(?:static\s+)?(?:void|int)\s+" + re.escape(name) +
                        r"\([^)]*\)\s*\{(.*?)^\}", source, re.S | re.M)
    need(len(bodies) == 1, f"SOURCE_FUNCTION_MISSING_OR_DUPLICATE:{name}")
    return re.sub(r"\s+", "", bodies[0])


def source_contract(source, config):
    code = uncomment(source)
    deferred.source_contract(code, config)
    compact = re.sub(r"\s+", "", code)
    worker = function_body(code, "deferred_probe_work_func")
    prefix = ("structdevice*dev;structdevice_private*private;"
              "mutex_lock(&deferred_probe_mutex);"
              "while(!list_empty(&deferred_probe_active_list)){"
              "private=list_first_entry(&deferred_probe_active_list,typeof(*dev->p),deferred_probe);"
              "dev=private->device;list_del_init(&private->deferred_probe);get_device(dev);")
    need(worker.startswith(prefix), "WORKER_MUTEX_LIST_DEVICE_ORDER_DRIFT")
    need(compact.count("staticDECLARE_WORK(deferred_probe_work,deferred_probe_work_func);") == 1,
         "WORKER_REGISTRATION_DRIFT")
    need(compact.count("staticbooldriver_deferred_probe_enable;") == 1 and
         len(re.findall(r"\bdriver_deferred_probe_enable\s*=", code)) == 1 and
         compact.count("driver_deferred_probe_enable=true;") == 1,
         "WORKER_ENABLE_ACTIVATION_DRIFT")
    trigger = ("if(!driver_deferred_probe_enable)return;mutex_lock(&deferred_probe_mutex);"
               "atomic_inc(&deferred_trigger_count);"
               "list_splice_tail_init(&deferred_probe_pending_list,&deferred_probe_active_list);"
               "mutex_unlock(&deferred_probe_mutex);"
               "queue_work(system_unbound_wq,&deferred_probe_work);")
    need(function_body(code, "driver_deferred_probe_trigger") == trigger,
         "WORKER_TRIGGER_ACTIVATION_DRIFT")
    need(compact.count("queue_work(system_unbound_wq,&deferred_probe_work);") == 1,
         "WORKER_QUEUE_COUNT_DRIFT")


def gate_exception_abi(header, implementation):
    header = re.sub(r"\s+", "", uncomment(header))
    implementation = re.sub(r"\s+", "", uncomment(implementation))
    need("structexception_table_entry{intinsn,fixup;shorttype,data;};" in header and
         "#defineARCH_HAS_RELATIVE_EXTABLE" in header, "EXCEPTION_TABLE_ABI_DRIFT")
    need("get_ex_fixup(conststructexception_table_entry*ex)"
         "{return((unsignedlong)&ex->fixup+ex->fixup);}" in implementation,
         "EXCEPTION_FIXUP_BASE_DRIFT")


def audit_sources(config):
    head = cp.pb.run(["git", "-C", str(cp.pb.LINUX), "rev-parse", "HEAD"]).strip()
    patches = sorted((cp.ROOT / "patches/linux-6.6").glob("*.patch"))
    queue = "".join(f"{cp.digest(p.read_bytes())}  {p.name}\n" for p in patches).encode()
    actual = {name: (cp.pb.LINUX / name).read_bytes() for name in SOURCE_FILES}
    pinned = {name: cp.pb.run(["git", "-C", str(cp.pb.LINUX), "show",
                               f"{cp.pb.LINUX_BASE}:{name}"]).encode() for name in SOURCE_FILES}
    gate_source_identity(head, cp.digest(queue), actual, pinned)
    for patch in patches:
        cp.pb.run(["git", "-C", str(cp.pb.LINUX), "apply", "--reverse", "--check", str(patch)])
    source_contract(actual[SOURCE_FILES[0]].decode(), config)
    gate_exception_abi(actual[SOURCE_FILES[1]].decode(), actual[SOURCE_FILES[2]].decode())
    return {name: cp.digest(data) for name, data in actual.items()}


def gate_window(stage, offset, original):
    gate_stage(stage)
    need(offset == OFFSET and len(original) == WINDOW and END == 0x8E84A0,
         "SELECTED_WINDOW_GEOMETRY_DRIFT")
    need(struct.unpack("<14I", original) == WINDOW_WORDS, "SELECTED_ORIGINAL_WINDOW_DRIFT")
    need(PARENT + len(PREFIX_WORDS) * 4 == offset and END < PARENT + PARENT_SIZE,
         "SELECTED_PARENT_GEOMETRY_DRIFT")


def gate_worker(original):
    need(len(original) == PARENT_SIZE, "WORKER_EXTENT_DRIFT")
    need(original[:OFFSET - PARENT] == struct.pack("<17I", *PREFIX_WORDS),
         "WORKER_PREFIX_DRIFT")
    gate_window("selected", OFFSET, original[OFFSET - PARENT:END - PARENT])
    need(original[END - PARENT:] == struct.pack("<18I", *SUFFIX_WORDS),
         "WORKER_SUFFIX_OR_BACKEDGE_DRIFT")
    word = lambda off: struct.unpack_from("<I", original, off - PARENT)[0]
    need(cp.branch_target(word(0x8E8440), TEXT + 0x8E8440) == TEXT + 0x10C72C4,
         "MUTEX_LOCK_TARGET_DRIFT")
    need(cp.branch_target(word(EMPTY_BRANCH), TEXT + EMPTY_BRANCH) == TEXT + EMPTY_TARGET,
         "EMPTY_LIST_BRANCH_DRIFT")
    need(word(OFFSET - 4) == 0xF9401114, "SELECTED_X20_LOAD_DRIFT")
    need(cp.branch_target(word(BACKEDGE), TEXT + BACKEDGE) == TEXT + LOOP_TARGET,
         "RETAINED_LOOP_BACKEDGE_DRIFT")


def gate_parent_agreement(elf, image, frozen):
    need(elf == image == frozen, "WORKER_ELF_IMAGE_FIX8_DISAGREEMENT")
    gate_worker(frozen)


def gate_core(core, delay=8):
    need(type(delay) is int and delay in (8, 1), "DELAY_NOT_ALLOWED")
    reference = cp.ultracompact_core(CORE)
    need(cp.digest(reference) == CORE_SHA, "FROZEN_CORE_REFERENCE_DRIFT")
    need(core == cp.delay_core(reference, delay), "SELECTED_CORE_OR_DELAY_DRIFT")
    words = struct.unpack("<14I", core)
    need(cp.branch_target(words[8], OFFSET + 32) == OFFSET + 16 and
         cp.branch_target(words[13], OFFSET + 52) == OFFSET + 48,
         "TERMINAL_CORE_LOCAL_BRANCH_DRIFT")
    need(words[9:14] == (0x52800120, 0x72B08000, 0xD4000003, 0xD503205F, 0x17FFFFFF),
         "TERMINAL_RESET_OR_WFE_CLOSURE_DRIFT")
    if delay == 8:
        need(cp.digest(core) == CORE_SHA, "FROZEN_CORE_DRIFT")
    return core


def gate_frozen(frozen):
    need(len(frozen) == cp.t3.FIX8_PAYLOAD_SIZE and cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA,
         "FROZEN_PAYLOAD_DRIFT")
    gate_worker(frozen[PARENT:PARENT + PARENT_SIZE])
    cp.t3.gate_tramp_identity(frozen)
    image_size = cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    cp.t3.gate_window_inside_image_size(OFFSET, WINDOW, image_size)
    dtb_offset, _ = cp.pb.calc_dtb_offset(image_size)
    need(dtb_offset == cp.t3.DTB_OFFSET, "RT_D_OFFSET_DRIFT")
    cp.pb.gate_rt_d(frozen[dtb_offset:])
    cp.gate_builtin_initramfs_source(cp.rt.parse_fdt(frozen[dtb_offset:])["/chosen"])


def gate_incoming(image, ranges):
    interior = cp.incoming_inclusive(image, ranges, TEXT, TEXT + PARENT + 4,
                                    TEXT + PARENT + PARENT_SIZE)
    window = cp.incoming_inclusive(image, ranges, TEXT, TEXT + OFFSET, TEXT + END)
    prefix = cp.incoming_inclusive(image, ranges, TEXT, TEXT + PARENT + 4, TEXT + OFFSET)
    need(not interior, f"SELECTED_WORKER_INTERIOR_ENTRY:{interior[:8]}")
    need(not window, f"SELECTED_INCOMING_ENTRY:{window[:8]}")
    need(prefix == [(TEXT + BACKEDGE, TEXT + LOOP_TARGET)],
         f"SELECTED_PREFIX_BYPASS:{prefix[:8]}")
    return window, prefix


def gate_sections(sections, image_length):
    names = [s["name"] for s in sections]
    need(len(names) == len(set(names)), "SECTION_NAMES_DUPLICATED")
    need({".text", "__ex_table", ".altinstructions", ".rela.dyn", ".relr.dyn"} <= set(names),
         "AUDIT_SECTION_MISSING")
    ranges = sorted((s["vma"] - TEXT, s["vma"] - TEXT + s["size"])
                    for s in sections if s["alloc"] and s["code"])
    need(tuple(ranges) == CODE_RANGES and all(0 <= lo < hi <= image_length for lo, hi in ranges),
         "WHOLE_CODE_SECTION_COVERAGE_DRIFT")
    section = cp.t3.gate_window_section_scan(TEXT + PARENT, PARENT_SIZE, sections)
    need(section["name"] == ".text", "SELECTED_NOT_FROZEN_TEXT_SECTION")
    return ranges


def gate_exception_destinations(data, base_va, window):
    need(len(data) % 12 == 0, "EXCEPTION_TABLE_RECORD_SIZE_DRIFT")
    lo, hi = window
    for off in range(0, len(data), 12):
        insn, fixup, _, _ = struct.unpack_from("<iiHH", data, off)
        need(not lo <= base_va + off + insn < hi, "EXCEPTION_FAULT_IN_PROTECTED_WORKER")
        need(not lo <= base_va + off + 4 + fixup < hi,
             "EXCEPTION_FIXUP_IN_PROTECTED_WORKER")
    return len(data) // 12


def gate_relocations(vmlinux, sections):
    sites = cp.relocation_sites(vmlinux, sections)
    cp.t3.gate_window_relocation_scan(TEXT + PARENT - 7, PARENT_SIZE + 7, sites)


def audit_binary(out, vmlinux, image, frozen):
    nm = cp.pb.run([cp.TOOLS["nm"], str(vmlinux)])
    sysmap = (vmlinux.parent / "System.map").read_text()
    symbols = {"_text": 0, "deferred_probe_work_func": PARENT,
               "deferred_probe_initcall": deferred.PARENT, "mutex_lock": 0x10C72C4,
               "mutex_unlock": 0x10C733C, "deferred_probe_mutex": 0x2091C00,
               "deferred_probe_active_list": 0x2091C30}
    for name, off in symbols.items():
        need(cp.t3.nm_symbol(nm, name) == cp.t3.nm_symbol(sysmap, name) == TEXT + off,
             f"SELECTED_SYMBOL_IDENTITY:{name}")
    need(cp.t3.symbol_extent(nm, "deferred_probe_work_func") ==
         (TEXT + PARENT, TEXT + PARENT + PARENT_SIZE), "WORKER_EXTENT_DRIFT")
    sections = cp.t3.section_map(out, cp.TOOLS, vmlinux)
    ranges = gate_sections(sections, len(image))
    gate_parent_agreement(cp.vmlinux_bytes_at(vmlinux, sections, TEXT + PARENT, PARENT_SIZE),
                          image[PARENT:PARENT + PARENT_SIZE], frozen[PARENT:PARENT + PARENT_SIZE])
    for binary in (image, frozen[:len(image)]):
        gate_incoming(binary, ranges)
        cp.t3.gate_window_literal_scan(TEXT + PARENT, PARENT_SIZE, binary)
    protected = (TEXT + PARENT, TEXT + PARENT + PARENT_SIZE)
    cp.t3.gate_window_symbol_scan(protected[0], PARENT_SIZE,
                                  [va for va, _ in cp.t3.symbol_table(nm)])
    cp.t3.gate_function_extent_scan(TEXT + OFFSET, WINDOW, protected[1])
    gate_relocations(vmlinux, sections)
    rewrites = cp.audit_rewrites(out, vmlinux, sections, protected)
    need(canonical(rewrites) == canonical(RUNTIME_TABLES), "RUNTIME_TABLE_IDENTITY_DRIFT")
    ex = next(s for s in sections if s["name"] == "__ex_table")
    gate_exception_destinations(cp.section_bytes(vmlinux, ex), ex["vma"], protected)
    start = cp.t3.nm_symbol(nm, "__initcall7_start")
    end = cp.t3.nm_symbol(nm, "__initcall_end")
    entries = cp.decode_initcall_span(vmlinux, sections, nm, start, end)
    need(len(entries) == 86 and entries[54]["symbol"] == "deferred_probe_initcall",
         "LATE_INDEX54_REGISTRATION_DRIFT")
    dump = cp.pb.run([cp.TOOLS["objdump"], "-dr", f"--start-address={protected[0]:#x}",
                      f"--stop-address={protected[1]:#x}", str(vmlinux)])
    (out / "original-function.txt").write_text(dump)


def gate_member(stage, frozen, payload, manifest, delay, source_commit, public_run):
    gate_stage(stage)
    gate_authority(source_commit, public_run)
    need(type(delay) is int and delay in (8, 1), "DELAY_NOT_ALLOWED")
    need(len(payload) == len(frozen) == cp.t3.FIX8_PAYLOAD_SIZE, "PAYLOAD_SIZE_DRIFT")
    need(cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_DRIFT")
    gate_worker(frozen[PARENT:PARENT + PARENT_SIZE])
    need(payload[:OFFSET] == frozen[:OFFSET] and payload[END:] == frozen[END:],
         "CHANGE_OUTSIDE_SELECTED_WINDOW")
    gate_core(payload[OFFSET:END], delay)
    gate_fields(manifest, {**SCOPE, "case": f"defer_selected{delay}", "delay_seconds": delay,
                          "source_commit": source_commit, "public_run": public_run,
                          "payload_sha256": cp.digest(payload),
                          "checkpoint_sha256": cp.digest(payload[OFFSET:END])}, "MANIFEST_DRIFT")
    files = manifest.get("source_files_sha256", {})
    need(isinstance(files, dict) and set(files) == set(SOURCE_FILES) and
         all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
             for value in files.values()), "SOURCE_FILE_IDENTITY_MISSING")
    need(set(manifest) == set(SCOPE) | {"case", "delay_seconds", "source_commit", "public_run",
                                      "payload_sha256", "checkpoint_sha256", "source_files_sha256"},
         "MANIFEST_FIELD_SET_DRIFT")
    cp.t3.gate_tramp_identity(payload)


def pair_identity(payloads, manifests, source_commit, public_run):
    return {"stage": "selected", "source_commit": source_commit, "public_run": public_run,
            "expected_delta_s": -7, "changed_offsets": [OFFSET + 9, OFFSET + 10],
            "cases": ["defer_selected8", "defer_selected1"],
            "payload_shas": {str(d): cp.digest(p) for d, p in zip((8, 1), payloads)},
            "manifest_shas": {str(d): cp.digest(canonical(m)) for d, m in zip((8, 1), manifests)}}


def gate_pair(stage, payloads, manifests, identity, source_commit, public_run):
    gate_stage(stage)
    gate_authority(source_commit, public_run)
    need(len(payloads) == len(manifests) == 2 and
         len(payloads[0]) == len(payloads[1]) == cp.t3.FIX8_PAYLOAD_SIZE,
         "PAIR_SIZE_MISMATCH")
    for delay, payload, manifest in zip((8, 1), payloads, manifests):
        gate_core(payload[OFFSET:END], delay)
        gate_fields(manifest, {"case": f"defer_selected{delay}", "delay_seconds": delay,
                               "source_commit": source_commit, "public_run": public_run,
                               "payload_sha256": cp.digest(payload),
                               "checkpoint_sha256": cp.digest(payload[OFFSET:END])},
                    "PAIR_MEMBER_DRIFT")
    changed = [i for i, (a, b) in enumerate(zip(*payloads)) if a != b]
    need(changed == [OFFSET + 9, OFFSET + 10], "PAIR_NOT_DELAY_ONLY")
    need(cp.digest(payloads[0]) != cp.digest(payloads[1]), "PAIR_FULL_HASH_COLLISION")
    common = [{k: v for k, v in m.items() if k not in
               {"case", "delay_seconds", "payload_sha256", "checkpoint_sha256"}} for m in manifests]
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
    report = {**SCOPE, "source_commit": source_commit, "public_run": public_run,
              "source_files_sha256": sources}
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
            manifest = {**report, "case": f"defer_selected{delay}", "delay_seconds": delay,
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
    print("DEFERRED_SELECTED_CI_READY=YES\nPAIR_DIFF=DELAY_CONSTANT_ONLY\n"
          "LOCAL_BUILD=NO\nKERNEL_REBUILD=NO\nDEVICE_OPERATION=NO")


def gate_boot(stage, frozen, payload, boot, base):
    gate_stage(stage)
    need(cp.digest(base) == BASE_BOOT_SHA and len(base) == BOOT_SIZE, "BASE_BOOT_DRIFT")
    need(cp.pb.parse_boot_v3(base, "FIX8")["kernel"] == frozen, "BASE_PAYLOAD_DRIFT")
    need(len(boot) == BOOT_SIZE, "BOOT_SIZE_DRIFT")
    offset = cp.pb.PAGE + OFFSET
    need(boot[:offset] == base[:offset] and boot[offset + WINDOW:] == base[offset + WINDOW:],
         "BOOT_ENVELOPE_OR_OUTSIDE_WINDOW_DRIFT")
    need(cp.pb.parse_boot_v3(boot, "selected")["kernel"] == payload, "BOOT_PAYLOAD_DRIFT")
    need(boot == base[:cp.pb.PAGE] + payload + base[cp.pb.PAGE + len(payload):],
         "INDEPENDENT_BOOT_BYTES_DRIFT")


def gate_boot_pair(boots):
    need(len(boots) == 2 and len(boots[0]) == len(boots[1]) == BOOT_SIZE,
         "BOOT_PAIR_SIZE_DRIFT")
    changed = [i for i, (a, b) in enumerate(zip(*boots)) if a != b]
    need(changed == [cp.pb.PAGE + OFFSET + 9, cp.pb.PAGE + OFFSET + 10],
         "BOOT_PAIR_NOT_DELAY_ONLY")
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
        name = f"defer-selected{delay}-boot.img"
        expected = base[:cp.pb.PAGE] + payload + base[cp.pb.PAGE + len(payload):]
        boot = (args.verify_boots / name).read_bytes() if args.verify_boots else expected
        gate_boot(args.stage, frozen, payload, boot, base)
        need(boot == expected, "PRIVATE_INDEPENDENT_BOOT_DRIFT")
        payloads.append(payload)
        manifests.append(manifest)
        boots.append(boot)
        records[str(delay)] = {"case": f"defer_selected{delay}", "boot_sha256": cp.digest(boot),
                              "boot_size": len(boot), "payload_sha256": cp.digest(payload)}
    gate_pair(args.stage, payloads, manifests, identity, args.source_commit, args.public_run)
    changed = gate_boot_pair(boots)
    report = {"stage": "selected", "source_commit": args.source_commit, "public_run": args.public_run,
              "members": records, "boot_changed_offsets": changed, "base_boot_sha256": BASE_BOOT_SHA,
              "public_pair_sha256": cp.digest(canonical(identity)),
              "gate": "DEFERRED_SELECTED_PRIVATE_PAIR_VERIFIED", "partition_writes": 0,
              "normal_boot_candidate": False, "device_operation": False}
    if args.verify_boots:
        actual = json.loads((args.verify_boots / "identity.json").read_text())
        need(canonical(report) == canonical(actual), "PRIVATE_INDEPENDENT_IDENTITY_DRIFT")
    args.out.mkdir(parents=True, exist_ok=False)
    if not args.verify_boots:
        for delay, boot in zip((8, 1), boots):
            (args.out / f"defer-selected{delay}-boot.img").write_bytes(boot)
    save(args.out / "identity.json", report)
    print(json.dumps(report, indent=2))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("audit", "private"), default="audit")
    p.add_argument("--stage", choices=("selected",), required=True)
    p.add_argument("--frozen", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name in ("bundle", "core", "verify-pair", "pair", "boot-base", "verify-boots"):
        p.add_argument("--" + name, type=Path)
    p.add_argument("--source-commit")
    p.add_argument("--public-run")
    return p


def main():
    p = parser()
    args = p.parse_args()
    required = ("bundle", "core") if args.mode == "audit" else ("pair", "boot_base", "source_commit", "public_run")
    for name in required:
        if getattr(args, name) is None:
            p.error("--" + name.replace("_", "-") + " is required in " + args.mode + " mode")
    forbidden = ("pair", "boot_base", "verify_boots") if args.mode == "audit" else ("bundle", "core", "verify_pair")
    for name in forbidden:
        if getattr(args, name) is not None:
            p.error("--" + name.replace("_", "-") + " is not accepted in " + args.mode + " mode")
    (audit if args.mode == "audit" else private)(args)


if __name__ == "__main__":
    main()
