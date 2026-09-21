#!/usr/bin/env python3
"""Actions-only terminal PM-tail entry pair with a single frozen worker caller."""
from __future__ import annotations

import argparse
import json
import os
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_audit as entry
import linked_jump_table_audit as linked

prior = entry.prior
cp = prior.cp
need = cp.require
save = prior.save
canonical = prior.canonical
gate_fields = prior.gate_fields
TEXT = prior.TEXT
STAGE = "pm_tail"
PARENT = 0x8DE450
PARENT_SIZE = 100
OFFSET = PARENT + 4
WINDOW = 56
END = OFFSET + WINDOW
CALL = 0x8E84A0
CORE = prior.CORE
CORE_SHA = prior.CORE_SHA
BOOT_SIZE = prior.BOOT_SIZE
BASE_BOOT_SHA = prior.BASE_BOOT_SHA
# The feasibility helper still returns exactly these five identities.
FEASIBILITY_SOURCE_HASHES = {
    "drivers/base/dd.c": "1541264d3103954566e355752d93b212537719a2546e69da5fae2b4a4e9436c6",
    "arch/arm64/include/asm/extable.h": "716acb8bb1c8d7bc2c066bc32c8864914ea7005fd59286484a2e0ad2f8f9bd82",
    "arch/arm64/mm/extable.c": "89c0117326965554e8d3b0fb2ca45a7b495e3773ed72c6fa526306f74f94a9ff",
    "drivers/base/core.c": "82c6bff4a508d9ad1174a97e1e609a24678f0f773c6478c72311fd0049430fb3",
    "drivers/base/base.h": "a6ee79463db989405b03107eb2262b7552257059ebc9cd6f50169127f3971fed",
}
LINKED_IDENTITY = {
    "gate": "LINKED_JUMP_TABLE_PM_WORKER_SAFE", "bundle_run": "35040148509",
    "offset": 0x1A97528, "end": 0x1A9B7B8, "size": 17040, "entries": 1065,
    "section": ".rodata", "sha256": "82b8114fdc566a524c09496766c44f1c6fa804272a379a028c2f1e9248af4733",
    "source_file": "include/linux/jump_label.h",
    "source_sha256": "3da4ded9cccf8a7538348b3aa9309367d01309c03069505b8751931030f7d87d",
    "layout": "S32_CODE_S32_TARGET_S64_KEY_FIELD_RELATIVE", "agreement": "ELF_IMAGE_FIX8_EXACT",
    "protected": [[18446603338377978960, 18446603338377979060],
                  [18446603338378019876, 18446603338378020072]],
    "code_rewrite_overlap": [], "target_entry_overlap": [],
    "candidate_generated": False, "device_operation": False,
}
LINKED_REFERENCE_PATH = (
    "artifacts/slot-b-deferred-pm-tail-20260921/linked-jump-35613385810/"
    "audit/linked-jump/linked-jump-table.json"
)
LINKED_REFERENCE_REPORT = {
    **LINKED_IDENTITY, "source_commit": "00094b32ef511699be7e817cb5f13cdb58558e8a", "public_run": "35613385810",
}
LINKED_REFERENCE = {
    "repository": prior.PUBLIC_REPOSITORY, "report_path": LINKED_REFERENCE_PATH,
    "source_commit": LINKED_REFERENCE_REPORT["source_commit"], "public_run": LINKED_REFERENCE_REPORT["public_run"],
    "canonical_sha256": cp.digest(canonical(LINKED_REFERENCE_REPORT)),
}
SOURCE_HASHES = {**FEASIBILITY_SOURCE_HASHES, LINKED_IDENTITY["source_file"]: LINKED_IDENTITY["source_sha256"]}
SOURCE_FILES = (*prior.SOURCE_FILES, "drivers/base/base.h", "include/linux/jump_label.h")
CASES = {8: "defer_pmtail8", 1: "defer_pmtail1"}
BOOT_NAMES = {8: "defer-pmtail8-boot.img", 1: "defer-pmtail1-boot.img"}
ORIGINAL_WORDS = (
    0xD503233F, 0xA9BE7BFD, 0xA9014FF4, 0x910003FD, 0xAA0003F4,
    0xF000BD80, 0x911C8000, 0x97E0D88D, 0x2A0003F3, 0x94007C44,
    0xAA1403E0, 0x9400000E, 0x94007C4A, 0x71000A7F, 0x54000122,
    0xF000BD80, 0x911C8000, 0x2A1303E1, 0x97E0D8A3, 0xA9414FF4,
    0xA8C27BFD, 0xD50323BF, 0xD65F03C0, 0xD4210000, 0x17FFFFF7,
)
ORIGINAL = struct.pack("<25I", *ORIGINAL_WORDS)
ORIGINAL_SHA = "7956c899bc9f87f119ecbc9c2c216d0bdde7c534ca2a2e47ebcc671de60b0f27"
SCOPE = {
    "stage": STAGE, "parent": entry.NAME, "parent_offset": PARENT,
    "parent_size": PARENT_SIZE, "offset": OFFSET, "window": WINDOW, "window_end": END,
    "section": ".text", "inline_only": True, "normal_boot_candidate": False, "device_ready": False,
    "late_index": None, "activation_initcall_index": 54,
    "positive_proves": "deferred_pm_tail_entry",
    "positive_does_not_prove": "deferred_pm_tail_return",
    "positive_only": ["original_reason_clear_store_executed", "worker_mutex_unlock_returned", "pm_tail_entry"],
    "positive_not_proven": ["persistent_reason_field_state", "srcu_or_pm_lock_acquired", "pm_tail_body_or_return",
                            "pm_list_movement", "first_bus_probe_entered_or_returned", "device_identity_or_name",
                            "get_device_reference_success", "allocation_freed", "driver_probe_body",
                            "culprit_or_root_cause", "late_initcalls_complete", "init_or_userspace", "usb_enablement"],
    "single_direct_caller": CALL, "caller": "deferred_probe_work_func",
    "caller_offset": prior.PARENT, "caller_size": prior.PARENT_SIZE,
    "caller_sha256": cp.digest(prior.ORIGINAL), "caller_unchanged": True,
    "caller_agreement": "ELF_IMAGE_FIX8_EXACT_196B",
    "reason_clear_store": 0x8E8494, "mutex_unlock_call": 0x8E8498,
    "reason_clear_store_executed_before_entry": True, "reason_field_state_at_checkpoint": "NOT_PROVEN",
    "worker_mutex_unlock_return_before_entry": True,
    "first_nonempty_worker_iteration_only": True, "callback_first_activation_only": False,
    "added_pointer_or_name_dereferences": 0, "maximum_delay_seconds": 8,
    "probe_family": "DEFERRED_PM_TAIL_ENTRY_PACIASP_PLUS_56B",
    "terminal_core": "PSCI_SYSTEM_RESET_OR_LOCAL_WFE_LOOP", "terminal_fallthrough": False,
    "original_paciasp_preserved": True, "new_stack_frame": False,
    "outside_window_unchanged": True, "window_agreement": "EXACT",
    "parent_agreement": "ELF_IMAGE_FIX8_EXACT_100B", "parent_literal_exception": [],
    "original_parent_sha256": ORIGINAL_SHA, "core_sha256": CORE_SHA,
    "frozen_payload_sha256": cp.t3.FIX8_PAYLOAD_SHA,
    "bundle_run": prior.BUNDLE_RUN, "bundle": prior.BUNDLE_IDENTITY,
    "linux_base": cp.pb.LINUX_BASE, "patch_queue_sha256": cp.pb.PATCH_QUEUE_SHA,
    "runtime_rewrites": {
        "standalone_sections": prior.RUNTIME_TABLES,
        "standalone_section_absence_is_not_linked_absence": True,
        "linked_jump_table_gate": LINKED_IDENTITY["gate"],
    },
    "linked_jump_reference": LINKED_REFERENCE,
    "exception_fixup_destinations": "CHECKED_FULL_PARENT_AND_WORKER",
    "incoming_entry": [[TEXT + CALL, TEXT + PARENT]], "incoming_interior": [], "incoming_window": [],
    "whole_code_scan": "FROZEN_AND_BUNDLE", "relocation_scan": "RELA_AND_RELR_FULL_PARENT_AND_WORKER",
    "source_reference_set": sorted(entry.SOURCE_REFERENCES),
    "rt_d_sha256": cp.pb.RT_D_SHA, "initramfs_source": "FROZEN_BUILTIN",
    "external_initrd": False, "trailer_unchanged": True,
    "frozen_experiment_rerun": False, "partition_writes": 0, "device_operation": False,
}


def gate_stage(stage):
    need(stage == STAGE, "UNAUTHORIZED_PM_TAIL_STAGE")


def gate_geometry():
    need((PARENT, PARENT_SIZE, OFFSET, WINDOW, END, CALL) ==
         (0x8DE450, 100, 0x8DE454, 56, 0x8DE48C, 0x8E84A0), "PM_TAIL_WINDOW_GEOMETRY_DRIFT")
    need((entry.PARENT, entry.CALL, entry.WINDOW, prior.PARENT, prior.PARENT_SIZE) ==
         (PARENT, CALL, WINDOW, 0x8E8424, 196), "PM_TAIL_PREREQUISITE_GEOMETRY_DRIFT")


def gate_parent(original):
    gate_geometry()
    need(len(original) == PARENT_SIZE and original == ORIGINAL and cp.digest(original) == ORIGINAL_SHA,
         "PM_TAIL_EXACT_PARENT_DRIFT")


def gate_core(core, delay=8):
    gate_geometry()
    prior.gate_delay(delay)
    need(cp.digest(cp.ultracompact_core(CORE)) == CORE_SHA, "FROZEN_CORE_REFERENCE_DRIFT")
    need(core == cp.delay_core(CORE, delay), "PM_TAIL_CORE_OR_DELAY_DRIFT")
    words = struct.unpack("<14I", core)
    need(cp.branch_target(words[8], OFFSET + 32) == OFFSET + 16 and
         cp.branch_target(words[13], OFFSET + 52) == OFFSET + 48 and
         words[9:] == (0x52800120, 0x72B08000, 0xD4000003, 0xD503205F, 0x17FFFFFF),
         "PM_TAIL_TERMINAL_CLOSURE_DRIFT")
    return core


def gate_frozen(frozen):
    prior.gate_frozen(frozen)
    gate_parent(frozen[PARENT:PARENT + PARENT_SIZE])
    entry.gate_call(struct.unpack_from("<I", frozen, CALL)[0])
    cp.t3.gate_window_inside_image_size(OFFSET, WINDOW, cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"])


def gate_linked_report(report, source_commit, public_run):
    prior.gate_authority(source_commit, public_run)
    expected = {**LINKED_IDENTITY, "source_commit": source_commit, "public_run": public_run}
    gate_fields(report, expected, "LINKED_JUMP_REPORT_DRIFT")
    need(set(report) == set(expected), "LINKED_JUMP_REPORT_FIELD_SET_DRIFT")


def read_linked_report(path, source_commit, public_run):
    need(path is not None and path.is_file(), "LINKED_JUMP_REPORT_REQUIRED")
    report = json.loads(path.read_text())
    gate_linked_report(report, source_commit, public_run)
    return report


def read_linked_reference():
    return read_linked_report(cp.ROOT / LINKED_REFERENCE_PATH,
                              LINKED_REFERENCE["source_commit"], LINKED_REFERENCE["public_run"])


def linked_binding(report, source_commit, public_run):
    gate_linked_report(report, source_commit, public_run)
    return {"linked_jump_report": report, "linked_jump_report_canonical_sha256": cp.digest(canonical(report))}


def gate_feasibility(report, source_commit, public_run):
    prior.gate_authority(source_commit, public_run)
    expected = {
        "gate": "DEFERRED_PM_TAIL_ENTRY_STATIC_FEASIBLE", "name": entry.NAME,
        "source_commit": source_commit, "public_run": public_run,
        "parent_offset": PARENT, "parent_size": PARENT_SIZE, "parent_sha256": ORIGINAL_SHA,
        "parent_words": list(ORIGINAL_WORDS), "offset": OFFSET, "window": WINDOW, "section": ".text",
        "single_direct_caller": CALL, "original_paciasp_preserved": True, "worker_unchanged": True,
        "core_sha256": CORE_SHA, "added_pointer_reads": 0, "candidate_generated": False,
        "device_ready": False, "device_operation": False, "partition_writes": 0,
        "bundle_run": prior.BUNDLE_RUN, "bundle": prior.BUNDLE_IDENTITY,
        # Preserve the historical report contract, not its imprecise field-state wording.
        "future_positive_limit": ["reason_field_cleared", "worker_mutex_unlock_returned", "pm_tail_entry"],
        "not_proven": ["pm_tail_return", "bus_probe_entry", "driver_probe", "culprit", "init", "usb"],
    }
    gate_fields(report, expected, "PM_TAIL_FEASIBILITY_DRIFT")
    sources = report.get("source_files_sha256")
    need(canonical(sources) == canonical(FEASIBILITY_SOURCE_HASHES), "PM_TAIL_FEASIBILITY_SOURCE_IDENTITIES_DRIFT")
    need(set(report) == set(expected) | {"source_files_sha256"}, "PM_TAIL_FEASIBILITY_FIELD_SET_DRIFT")
    return sources


def gate_manifest(payload, manifest, delay, source_commit, public_run):
    prior.gate_delay(delay)
    prior.gate_authority(source_commit, public_run)
    need(isinstance(manifest, dict), "PM_TAIL_MANIFEST_DRIFT")
    binding = linked_binding(manifest.get("linked_jump_report"), source_commit, public_run)
    gate_fields(manifest, {**SCOPE, **binding, "case": CASES[delay], "delay_seconds": delay,
                          "source_commit": source_commit, "public_run": public_run,
                          "payload_sha256": cp.digest(payload), "checkpoint_sha256": cp.digest(payload[OFFSET:END])},
                "PM_TAIL_MANIFEST_DRIFT")
    sources = manifest.get("source_files_sha256")
    need(canonical(sources) == canonical(SOURCE_HASHES), "PM_TAIL_SOURCE_IDENTITIES_DRIFT")
    need(set(manifest) == set(SCOPE) | set(binding) | {"case", "delay_seconds", "source_commit", "public_run",
                                                      "payload_sha256", "checkpoint_sha256", "source_files_sha256"},
         "PM_TAIL_MANIFEST_FIELD_SET_DRIFT")


def gate_member(stage, frozen, payload, manifest, delay, source_commit, public_run):
    gate_stage(stage)
    gate_frozen(frozen)
    need(len(payload) == len(frozen), "PAYLOAD_SIZE_DRIFT")
    need(payload[:OFFSET] == frozen[:OFFSET] and payload[END:] == frozen[END:],
         "CHANGE_OUTSIDE_PM_TAIL_WINDOW")
    gate_core(payload[OFFSET:END], delay)
    gate_manifest(payload, manifest, delay, source_commit, public_run)
    cp.t3.gate_tramp_identity(payload)


def pair_identity(payloads, manifests, source_commit, public_run):
    prior.gate_authority(source_commit, public_run)
    need(len(payloads) == len(manifests) == 2, "PAIR_SIZE_MISMATCH")
    return {"stage": STAGE, "source_commit": source_commit, "public_run": public_run,
            "expected_delta_s": -7, "changed_offsets": [OFFSET + 9, OFFSET + 10],
            "cases": [CASES[8], CASES[1]],
            "payload_shas": {str(delay): cp.digest(payload) for delay, payload in zip((8, 1), payloads)},
            "manifest_shas": {str(delay): cp.digest(canonical(manifest))
                              for delay, manifest in zip((8, 1), manifests)}}


def gate_pair(stage, payloads, manifests, identity, source_commit, public_run):
    gate_stage(stage)
    prior.gate_authority(source_commit, public_run)
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
    prior.gate_actions()
    gate_stage(args.stage)
    source_commit, public_run = os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"]
    prior.gate_authority(source_commit, public_run)
    need(args.source_commit in (None, source_commit) and args.public_run in (None, public_run),
         "PUBLIC_AUTHORITY_DRIFT")
    frozen = args.frozen.read_bytes()
    gate_frozen(frozen)
    core = gate_core(args.core.read_bytes())
    read_linked_reference()
    args.out.mkdir(parents=True, exist_ok=False)
    # Always execute, including --verify-pair: a saved ABSENT section result is insufficient.
    executed = linked.audit(argparse.Namespace(bundle=args.bundle, frozen=args.frozen, out=args.out / "linked-jump"))
    linked_report = read_linked_report(args.out / "linked-jump/linked-jump-table.json", source_commit, public_run)
    need(canonical(executed) == canonical(linked_report), "LINKED_JUMP_EXECUTED_REPORT_DRIFT")
    binding = linked_binding(linked_report, source_commit, public_run)
    entry.audit(argparse.Namespace(bundle=args.bundle, frozen=args.frozen, out=args.out / "entry"))
    feasibility = json.loads((args.out / "entry/feasibility.json").read_text())
    sources = {**gate_feasibility(feasibility, source_commit, public_run),
               linked_report["source_file"]: linked_report["source_sha256"]}
    need(canonical(sources) == canonical(SOURCE_HASHES), "PM_TAIL_SOURCE_IDENTITIES_DRIFT")
    worker_out = args.out / "worker"
    worker_out.mkdir()
    # Feasibility alone checks only the Image worker; retain the full ELF/Image/FIX8 worker audit.
    prior.audit_binary(worker_out, args.bundle / "vmlinux", (args.bundle / "Image").read_bytes(), frozen)
    report = {**SCOPE, **binding, "source_commit": source_commit, "public_run": public_run,
              "source_files_sha256": sources}
    save(args.out / "audit.json", report)
    payloads, manifests = [], []
    root = args.verify_pair or args.out / "pair"
    if args.verify_pair:
        transported = read_linked_report(root / "linked-jump-table.json", source_commit, public_run)
        need(canonical(transported) == canonical(linked_report), "PAIR_LINKED_EXECUTED_REPORT_DRIFT")
    for delay in (8, 1):
        if args.verify_pair:
            payload = (root / str(delay) / "payload.bin").read_bytes()
            manifest = json.loads((root / str(delay) / "manifest.json").read_text())
            gate_fields(manifest, report, "REAUDIT_MANIFEST_DRIFT")
        else:
            probe = cp.delay_core(core, delay)
            payload = cp.patch_window(frozen, OFFSET, probe)
            manifest = {**report, "case": CASES[delay], "delay_seconds": delay,
                        "payload_sha256": cp.digest(payload), "checkpoint_sha256": cp.digest(probe)}
        gate_member(args.stage, frozen, payload, manifest, delay, source_commit, public_run)
        payloads.append(payload)
        manifests.append(manifest)
    identity = (json.loads((root / "pair.json").read_text()) if args.verify_pair else
                pair_identity(payloads, manifests, source_commit, public_run))
    gate_pair(args.stage, payloads, manifests, identity, source_commit, public_run)
    if not args.verify_pair:
        for delay, payload, manifest in zip((8, 1), payloads, manifests):
            member = root / str(delay)
            member.mkdir(parents=True, exist_ok=False)
            (member / "payload.bin").write_bytes(payload)
            save(member / "manifest.json", manifest)
        save(root / "pair.json", identity)
        save(root / "linked-jump-table.json", linked_report)
    save(args.out / "verified.json", identity)
    print(json.dumps(identity, indent=2))
    print("DEFERRED_PM_TAIL_PUBLIC_AUDIT_PASSED=YES\nPAIR_DIFF=DELAY_CONSTANT_ONLY\n"
          "KERNEL_REBUILD=NO\nDEVICE_READY=NO\nDEVICE_OPERATION=NO")


def gate_boot_bytes(frozen, payload, boot, base):
    need(cp.pb.parse_boot_v3(base, "FIX8")["kernel"] == frozen, "BASE_PAYLOAD_DRIFT")
    need(len(boot) == len(base) == BOOT_SIZE, "BOOT_SIZE_DRIFT")
    offset = cp.pb.PAGE + OFFSET
    need(boot[:offset] == base[:offset] and boot[offset + WINDOW:] == base[offset + WINDOW:],
         "BOOT_ENVELOPE_OR_OUTSIDE_WINDOW_DRIFT")
    need(cp.pb.parse_boot_v3(boot, STAGE)["kernel"] == payload, "BOOT_PAYLOAD_DRIFT")
    need(boot == base[:cp.pb.PAGE] + payload + base[cp.pb.PAGE + len(payload):], "INDEPENDENT_BOOT_BYTES_DRIFT")


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


def gate_private_linked(manifests, report, source_commit, public_run):
    binding = linked_binding(report, source_commit, public_run)
    need(len(manifests) == 2, "PRIVATE_MANIFEST_PAIR_REQUIRED")
    for manifest in manifests:
        gate_fields(manifest, {**binding, "linked_jump_reference": LINKED_REFERENCE,
                               "source_files_sha256": SOURCE_HASHES, "source_commit": source_commit,
                               "public_run": public_run}, "PRIVATE_LINKED_PROVENANCE_DRIFT")
    return binding


def private_identity(records, changed_offsets, identity, manifests, linked_report, source_commit, public_run):
    binding = gate_private_linked(manifests, linked_report, source_commit, public_run)
    return {"stage": STAGE, "source_commit": source_commit, "public_run": public_run,
            "members": records, "boot_changed_offsets": changed_offsets, "base_boot_sha256": BASE_BOOT_SHA,
            "public_pair_sha256": cp.digest(canonical(identity)), "gate": "DEFERRED_PM_TAIL_PRIVATE_PAIR_VERIFIED",
            **binding, "linked_jump_reference": LINKED_REFERENCE, "source_files_sha256": SOURCE_HASHES,
            "partition_writes": 0, "normal_boot_candidate": False, "device_ready": False, "device_operation": False}


def gate_independent_identity(actual, expected):
    need(canonical(actual) == canonical(expected), "PRIVATE_INDEPENDENT_IDENTITY_DRIFT")


def private(args):
    prior.gate_actions(private=True)
    gate_stage(args.stage)
    prior.gate_authority(args.source_commit, args.public_run)
    read_linked_reference()
    # Downloaded with the authenticated public pair, never inferred from a member.
    linked_report = read_linked_report(args.pair / "linked-jump-table.json", args.source_commit, args.public_run)
    frozen = args.frozen.read_bytes()
    gate_frozen(frozen)
    base = args.boot_base.read_bytes()
    need(cp.digest(base) == BASE_BOOT_SHA and len(base) == BOOT_SIZE, "BASE_BOOT_DRIFT")
    identity = json.loads((args.pair / "pair.json").read_text())
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
    report = private_identity(records, gate_boot_pair(boots), identity, manifests, linked_report,
                              args.source_commit, args.public_run)
    if args.verify_boots:
        gate_independent_identity(json.loads((args.verify_boots / "identity.json").read_text()), report)
    args.out.mkdir(parents=True, exist_ok=False)
    if not args.verify_boots:
        for delay, boot in zip((8, 1), boots):
            (args.out / BOOT_NAMES[delay]).write_bytes(boot)
    save(args.out / "identity.json", report)
    print(json.dumps(report, indent=2))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("audit", "private"), default="audit")
    result.add_argument("--stage", choices=(STAGE,), required=True)
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
    required = (("bundle", "core") if args.mode == "audit" else
                ("pair", "boot_base", "source_commit", "public_run"))
    forbidden = (("pair", "boot_base", "verify_boots") if args.mode == "audit" else
                 ("bundle", "core", "verify_pair"))
    for name in required:
        if getattr(args, name) is None:
            cli.error("--" + name.replace("_", "-") + " is required in " + args.mode + " mode")
    for name in forbidden:
        if getattr(args, name) is not None:
            cli.error("--" + name.replace("_", "-") + " is not accepted in " + args.mode + " mode")
    (audit if args.mode == "audit" else private)(args)


if __name__ == "__main__":
    main()
