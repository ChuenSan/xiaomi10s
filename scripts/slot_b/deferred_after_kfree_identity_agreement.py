#!/usr/bin/env python3
"""Actions-only agreement between the after-kfree pair and frozen observer identities."""
import argparse
import hashlib
import json
import os
import re
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GitHub Actions required")

import deferred_after_kfree_probe as probe
import observe

OFFSET = 0x8E848C
WINDOW = 56
PAYLOAD_SIZE = 37369041
BOOT_SIZE = 37380096
PAGE = 4096
BASE_BOOT_SHA = "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5"
PRIVATE_REPOSITORY = "ChuenSan/thyme-mainline-private-ci"
PRIVATE_REPOSITORY_ID = 1362468178
PRIVATE_WORKFLOW = ".github/workflows/thyme-slot-b-deferred-after-kfree.yml"
SOURCE_FILES = ("drivers/base/dd.c", "arch/arm64/include/asm/extable.h",
                "arch/arm64/mm/extable.c", "drivers/base/core.c")
CORE_WORDS = (0xD5034FDF, 0xD53BE009, 0xD37DF12A, 0xD53BE02B,
              0xD5033FDF, 0xD53BE02C, 0xCB0B018D, 0xEB0A01BF,
              0x54FFFF83, 0x52800120, 0x72B08000, 0xD4000003,
              0xD503205F, 0x17FFFFFF)
SCOPE = {
    "stage": "after_kfree", "parent": "deferred_probe_work_func",
    "parent_offset": 0x8E8424, "parent_size": 196,
    "offset": OFFSET, "window": WINDOW, "window_end": 0x8E84C4,
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
    "predecessor": "original_bl_kfree_return", "predecessor_offset": 0x8E8488,
    "original_reason_loads": [[0x8E8480, 0xF9402688], [0x8E8484, 0xF9406100]],
    "get_device_return_value_checked": False, "reason_clear_store": 0x8E8494,
    "reason_field_cleared_at_checkpoint": False, "mutex_held_at_checkpoint": True,
    "added_pointer_or_name_dereferences": 0, "maximum_delay_seconds": 8,
    "probe_family": "FIRST_DEVICE_AFTER_KFREE_TERMINAL_INLINE_56B",
    "frozen_payload_sha256": "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41",
    "core_sha256": "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5",
    "terminal_core": "PSCI_SYSTEM_RESET_OR_LOCAL_WFE_LOOP", "terminal_fallthrough": False,
    "empty_list_branch": [0x8E8454, 0x8E84C8], "empty_list_reaches_probe": False,
    "retained_backedge": [0x8E84C4, 0x8E8460], "retained_backedge_reachable": False,
    "pac_and_frame_preserved": True, "outside_window_unchanged": True,
    "window_agreement": "EXACT", "parent_agreement": "ELF_IMAGE_FIX8_EXACT_196B",
    "parent_literal_exception": [], "incoming": [],
    "prefix_incoming": [[0xFFFF8000808E84C4, 0xFFFF8000808E8460]],
    "first_nonempty_worker_iteration_only": True, "callback_first_activation_only": False,
    "exception_fixup_destinations": "CHECKED_FULL_PARENT",
    "whole_code_scan": "FROZEN_AND_BUNDLE", "relocation_scan": "RELA_AND_RELR_FULL_PARENT",
    "initramfs_source": "FROZEN_BUILTIN", "external_initrd": False, "trailer_unchanged": True,
    "entry_probe_rerun": False, "frozen_experiment_rerun": False,
    "partition_writes": 0, "device_operation": False,
    "runtime_rewrites": {
        "__ex_table": {"entries": 994,
                       "sha256": "e93f6326dba119d9b5091b9c31295e47086ce45813b6f1a62dde0655ca65a9be"},
        "altinstructions": {"entries": 37287,
                            "sha256": "a98a9bc613c12519ea5fd8f1e168ede872af0d8474fa385df6bc1cc17fdc36a6"},
        "__jump_table": "ABSENT", "static_call_sites": "ABSENT", "kcfi_traps": "ABSENT",
    },
}
require = observe.require


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def require_fields(actual, expected, label):
    require(isinstance(actual, dict), label)
    for key, value in expected.items():
        require(key in actual and canonical(actual[key]) == canonical(value), f"{label}:{key}")


def validate_frozen(frozen):
    require_fields(frozen, {"stage": "after_kfree", "offset": OFFSET, "window": WINDOW,
                           "parent_offset": 0x8E8424, "parent_size": 196,
                           "boot_size": BOOT_SIZE}, "AFTERFREE_FREEZE_GEOMETRY")
    observe.validate_afterfree_freeze(frozen)


def validate_pair_authority(pair, frozen):
    expected = {"stage": "after_kfree", "source_commit": frozen["source_commit"],
                "public_run": frozen["public_run"], "expected_delta_s": -7,
                "changed_offsets": [OFFSET + 9, OFFSET + 10],
                "cases": ["defer_afterfree8", "defer_afterfree1"],
                "payload_shas": {delay: identity["payload_sha256"]
                                 for delay, identity in frozen["members"].items()}}
    require_fields(pair, expected, "AFTERFREE_PAIR_AUTHORITY")
    hashes = pair.get("manifest_shas")
    require(isinstance(hashes, dict) and set(hashes) == {"8", "1"} and
            all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in hashes.values()), "AFTERFREE_PAIR_MANIFEST_IDENTITIES")
    require(set(pair) == set(expected) | {"manifest_shas"}, "AFTERFREE_PAIR_FIELD_SET")


def validate_manifest(manifest, frozen, delay):
    require_fields(manifest, SCOPE, "AFTERFREE_MANIFEST_SCOPE")
    probe.gate_fields(manifest, probe.SCOPE, "AFTERFREE_MANIFEST_SOURCE_SCOPE")
    require_fields(manifest, {"source_commit": frozen["source_commit"],
                              "public_run": frozen["public_run"],
                              "case": f"defer_afterfree{delay}", "delay_seconds": int(delay),
                              "payload_sha256": frozen["members"][delay]["payload_sha256"]},
                   "AFTERFREE_MANIFEST_AUTHORITY")
    require(set(manifest) == set(probe.SCOPE) | {"case", "delay_seconds", "source_commit", "public_run",
                                              "payload_sha256", "checkpoint_sha256", "source_files_sha256"},
            "AFTERFREE_MANIFEST_FIELD_SET")
    sources = manifest.get("source_files_sha256")
    require(tuple(probe.SOURCE_FILES) == SOURCE_FILES and isinstance(sources, dict) and
            set(sources) == set(SOURCE_FILES), "AFTERFREE_MANIFEST_SOURCE_FILES")
    for name, value in sources.items():
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) and
                len(set(value)) > 2, f"AFTERFREE_MANIFEST_SOURCE_HASH:{name}")


def validate_private_receipts(frozen, pair, run, jobs, packed, reverified):
    validate_frozen(frozen)
    validate_pair_authority(pair, frozen)
    run_id = int(frozen["private_run"])
    require_fields(run, {"id": run_id, "head_sha": frozen["private_commit"],
                         "status": "completed", "conclusion": "success", "path": PRIVATE_WORKFLOW},
                   "AFTERFREE_PRIVATE_RUN")
    repository = {"id": PRIVATE_REPOSITORY_ID, "full_name": PRIVATE_REPOSITORY, "private": True}
    for key in ("repository", "head_repository"):
        require_fields(run.get(key), repository, f"AFTERFREE_PRIVATE_RUN:{key}")
    require(isinstance(jobs, dict) and type(jobs.get("total_count")) is int and
            jobs["total_count"] == 2 and isinstance(jobs.get("jobs"), list) and len(jobs["jobs"]) == 2,
            "AFTERFREE_PRIVATE_JOBS")
    entries = jobs["jobs"]
    require(all(isinstance(job, dict) and job.get("name") in ("pack", "independent-reverify")
                for job in entries) and {job["name"] for job in entries} == {"pack", "independent-reverify"},
            "AFTERFREE_PRIVATE_JOB_NAMES")
    for job in entries:
        require(type(job.get("id")) is int and job["id"] > 0, "AFTERFREE_PRIVATE_JOB_ID")
        require_fields(job, {"run_id": run_id, "head_sha": frozen["private_commit"],
                             "status": "completed", "conclusion": "success"},
                       f"AFTERFREE_PRIVATE_JOB:{job['name']}")
    require(entries[0]["id"] != entries[1]["id"], "AFTERFREE_PRIVATE_JOBS_NOT_INDEPENDENT")
    expected = {"stage": "after_kfree", "source_commit": frozen["source_commit"],
                "public_run": frozen["public_run"],
                "members": {delay: {"case": f"defer_afterfree{delay}",
                                     "boot_sha256": frozen["members"][delay]["boot_sha256"],
                                     "boot_size": frozen["members"][delay]["boot_size"],
                                     "payload_sha256": frozen["members"][delay]["payload_sha256"]}
                            for delay in ("8", "1")},
                "boot_changed_offsets": [PAGE + OFFSET + 9, PAGE + OFFSET + 10],
                "base_boot_sha256": BASE_BOOT_SHA, "public_pair_sha256": digest(canonical(pair)),
                "gate": "DEFERRED_AFTER_KFREE_PRIVATE_PAIR_VERIFIED", "partition_writes": 0,
                "normal_boot_candidate": False, "device_operation": False}
    require_fields(packed, expected, "AFTERFREE_PRIVATE_IDENTITY")
    require(set(packed) == set(expected), "AFTERFREE_PRIVATE_IDENTITY_FIELD_SET")
    require(canonical(packed) == canonical(reverified), "AFTERFREE_PRIVATE_REVERIFY_IDENTITY_MISMATCH")


def verify(root, frozen):
    validate_frozen(frozen)
    require(canonical(frozen) == canonical(observe.load_afterfree_freeze()), "AFTERFREE_FREEZE_FILE_MISMATCH")
    pair = json.loads((root / "pair.json").read_text())
    validate_pair_authority(pair, frozen)
    payloads, manifests = [], []
    for delay in ("8", "1"):
        member = root / delay
        manifest = json.loads((member / "manifest.json").read_text())
        payload = (member / "payload.bin").read_bytes()
        identity = frozen["members"][delay]
        validate_manifest(manifest, frozen, delay)
        require(digest(canonical(manifest)) == pair["manifest_shas"][delay],
                "AFTERFREE_MANIFEST_DIGEST_MISMATCH")
        require(len(payload) == PAYLOAD_SIZE, "AFTERFREE_PAYLOAD_SIZE_MISMATCH")
        require(digest(payload) == identity["payload_sha256"], "AFTERFREE_PAYLOAD_IDENTITY_MISMATCH")
        words = list(CORE_WORDS)
        if delay == "1":
            words[2] = 0xD340FD2A
        core = payload[OFFSET:OFFSET + WINDOW]
        require(core == struct.pack("<14I", *words), "AFTERFREE_CORE_OR_DELAY_MISMATCH")
        require(digest(core) == manifest.get("checkpoint_sha256"), "AFTERFREE_CORE_IDENTITY_MISMATCH")
        case = f"defer_afterfree{delay}"
        observe.validate_identity(case, identity["boot_size"], identity["boot_sha256"])
        require(case in observe.ORIGIN_CASES, "AFTERFREE_ORIGIN_GATE_MISSING")
        payloads.append(payload)
        manifests.append(manifest)
    changed = [index for index, (first, second) in enumerate(zip(*payloads)) if first != second]
    require(changed == [OFFSET + 9, OFFSET + 10], "AFTERFREE_PAIR_NOT_DELAY_ONLY")
    common = [{key: value for key, value in manifest.items() if key not in
               {"case", "delay_seconds", "payload_sha256", "checkpoint_sha256"}}
              for manifest in manifests]
    require(canonical(common[0]) == canonical(common[1]), "AFTERFREE_PAIR_METADATA_DRIFT")
    require(observe.PAIRS.get("defer_afterfree1") ==
            ("defer_afterfree8", "deferred_reason_kfree_returned", "deferred_first_bus_probe_entered"),
            "AFTERFREE_OBSERVER_PROOF_DRIFT")
    return pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--private-receipts", type=Path)
    args = parser.parse_args()
    frozen = observe.load_afterfree_freeze()
    pair = verify(args.root, frozen)
    if args.private_receipts is not None:
        require(os.environ.get("GITHUB_REPOSITORY") == PRIVATE_REPOSITORY,
                "AFTERFREE_PRIVATE_EXECUTION_REPOSITORY")
        receipts = [json.loads((args.private_receipts / name).read_text()) for name in
                    ("private-run.json", "private-jobs.json", "packed/identity.json", "reverified/identity.json")]
        validate_private_receipts(frozen, pair, *receipts)
    print("DEFERRED_AFTER_KFREE_OBSERVER_IDENTITY_AGREEMENT=PASS")
    if args.private_receipts is not None:
        print("DEFERRED_AFTER_KFREE_PRIVATE_OBSERVER_PROVENANCE=PASS")


if __name__ == "__main__":
    main()
