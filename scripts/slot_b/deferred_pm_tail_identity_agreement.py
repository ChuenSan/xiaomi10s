#!/usr/bin/env python3
"""Actions-only PM-tail observer agreement with public and private receipts."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_probe as probe
import deferred_pm_tail_runtime as runtime
import observe

require = observe.require
OFFSET, WINDOW, PAGE = 0x8DE454, 56, 4096
PAYLOAD_SIZE, BOOT_SIZE = 37369041, 37380096
PRIVATE_REPOSITORY = "ChuenSan/thyme-mainline-private-ci"
PRIVATE_REPOSITORY_ID = 1362468178
PRIVATE_WORKFLOW = ".github/workflows/thyme-slot-b-deferred-pm-tail.yml"
EXPECTED_SCOPE = {
    "stage": "pm_tail", "parent": "device_pm_move_to_tail", "parent_offset": 0x8DE450,
    "parent_size": 100, "offset": OFFSET, "window": WINDOW, "window_end": 0x8DE48C,
    "caller": "deferred_probe_work_func", "caller_offset": 0x8E8424, "caller_size": 196,
    "single_direct_caller": 0x8E84A0, "caller_unchanged": True,
    "positive_only": ["original_reason_clear_store_executed", "worker_mutex_unlock_returned", "pm_tail_entry"],
    "reason_field_state_at_checkpoint": "NOT_PROVEN", "terminal_fallthrough": False,
    "added_pointer_or_name_dereferences": 0, "normal_boot_candidate": False,
    "device_ready": False, "original_paciasp_preserved": True, "new_stack_frame": False,
    "outside_window_unchanged": True, "parent_agreement": "ELF_IMAGE_FIX8_EXACT_100B",
    "caller_agreement": "ELF_IMAGE_FIX8_EXACT_196B", "partition_writes": 0, "device_operation": False,
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def require_fields(actual, expected, label):
    require(isinstance(actual, dict), label)
    for key, value in expected.items():
        require(key in actual and canonical(actual[key]) == canonical(value), f"{label}:{key}")


def validate_frozen(frozen):
    runtime.validate_freeze(frozen, observe.IMAGES)
    require_fields(frozen, {"stage": "pm_tail", "offset": OFFSET, "window": WINDOW,
                            "parent_offset": 0x8DE450, "parent_size": 100, "boot_size": BOOT_SIZE},
                   "PMTAIL_FREEZE_GEOMETRY")


def validate_pair_authority(pair, frozen):
    expected = {"stage": "pm_tail", "source_commit": frozen["source_commit"], "public_run": frozen["public_run"],
                "expected_delta_s": -7, "changed_offsets": [OFFSET + 9, OFFSET + 10],
                "cases": list(runtime.CASES),
                "payload_shas": {delay: member["payload_sha256"] for delay, member in frozen["members"].items()}}
    require_fields(pair, expected, "PMTAIL_PAIR_AUTHORITY")
    hashes = pair.get("manifest_shas")
    require(isinstance(hashes, dict) and set(hashes) == {"8", "1"} and
            all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()),
            "PMTAIL_PAIR_MANIFEST_IDENTITIES")
    require(set(pair) == set(expected) | {"manifest_shas"}, "PMTAIL_PAIR_FIELD_SET")
    require(digest(canonical(pair)) == frozen["public_pair_sha256"], "PMTAIL_PAIR_DIGEST")


def verify(root, frozen):
    validate_frozen(frozen)
    require(canonical(frozen) == canonical(runtime.load_freeze(observe.IMAGES)), "PMTAIL_FREEZE_FILE_MISMATCH")
    pair = json.loads((root / "pair.json").read_text())
    validate_pair_authority(pair, frozen)
    linked = probe.read_linked_report(root / "linked-jump-table.json", frozen["source_commit"], frozen["public_run"])
    require(digest(canonical(linked)) == frozen["linked_jump_report_canonical_sha256"], "PMTAIL_LINKED_DIGEST")
    payloads, manifests = [], []
    for delay in ("8", "1"):
        member = root / delay
        payload = (member / "payload.bin").read_bytes()
        manifest = json.loads((member / "manifest.json").read_text())
        identity = frozen["members"][delay]
        require(len(payload) == PAYLOAD_SIZE and digest(payload) == identity["payload_sha256"],
                "PMTAIL_PAYLOAD_IDENTITY")
        require(digest(canonical(manifest)) == pair["manifest_shas"][delay], "PMTAIL_MANIFEST_DIGEST")
        require_fields(manifest, EXPECTED_SCOPE, "PMTAIL_MANIFEST_SCOPE")
        probe.gate_manifest(payload, manifest, int(delay), frozen["source_commit"], frozen["public_run"])
        probe.gate_core(payload[OFFSET:OFFSET + WINDOW], int(delay))
        require(canonical(manifest["linked_jump_report"]) == canonical(linked), "PMTAIL_TRANSPORTED_REPORT")
        case = f"defer_pmtail{delay}"
        observe.validate_identity(case, identity["boot_size"], identity["boot_sha256"])
        require(case in observe.ORIGIN_CASES, "PMTAIL_ORIGIN_GATE_MISSING")
        payloads.append(payload)
        manifests.append(manifest)
    probe.gate_pair("pm_tail", payloads, manifests, pair, frozen["source_commit"], frozen["public_run"])
    require(observe.PAIRS.get(runtime.CASES[1]) ==
            (runtime.CASES[0], "deferred_pm_tail_entry", "deferred_pm_tail_return"), "PMTAIL_OBSERVER_PROOF")
    return pair, linked


def validate_private_receipts(frozen, pair, linked, run, jobs, packed, reverified):
    validate_frozen(frozen)
    validate_pair_authority(pair, frozen)
    probe.gate_linked_report(linked, frozen["source_commit"], frozen["public_run"])
    require(digest(canonical(linked)) == frozen["linked_jump_report_canonical_sha256"], "PMTAIL_LINKED_DIGEST")
    run_id = int(frozen["private_run"])
    require_fields(run, {"id": run_id, "head_sha": frozen["private_commit"], "status": "completed",
                         "conclusion": "success", "path": PRIVATE_WORKFLOW}, "PMTAIL_PRIVATE_RUN")
    repository = {"id": PRIVATE_REPOSITORY_ID, "full_name": PRIVATE_REPOSITORY, "private": True}
    for key in ("repository", "head_repository"):
        require_fields(run.get(key), repository, f"PMTAIL_PRIVATE_RUN:{key}")
    require(isinstance(jobs, dict) and type(jobs.get("total_count")) is int and jobs["total_count"] == 2 and
            isinstance(jobs.get("jobs"), list) and len(jobs["jobs"]) == 2, "PMTAIL_PRIVATE_JOBS")
    entries = jobs["jobs"]
    require(all(isinstance(job, dict) and job.get("name") in ("pack", "independent-reverify") for job in entries) and
            {job["name"] for job in entries} == {"pack", "independent-reverify"}, "PMTAIL_PRIVATE_JOB_NAMES")
    for job in entries:
        require(type(job.get("id")) is int and job["id"] > 0, "PMTAIL_PRIVATE_JOB_ID")
        require_fields(job, {"run_id": run_id, "head_sha": frozen["private_commit"],
                             "status": "completed", "conclusion": "success"}, "PMTAIL_PRIVATE_JOB")
    require(entries[0]["id"] != entries[1]["id"], "PMTAIL_PRIVATE_JOBS_NOT_INDEPENDENT")
    expected = {"stage": "pm_tail", "source_commit": frozen["source_commit"], "public_run": frozen["public_run"],
                "members": {delay: {"case": f"defer_pmtail{delay}", **member}
                            for delay, member in frozen["members"].items()},
                "boot_changed_offsets": [PAGE + OFFSET + 9, PAGE + OFFSET + 10],
                "base_boot_sha256": probe.BASE_BOOT_SHA, "public_pair_sha256": frozen["public_pair_sha256"],
                "gate": "DEFERRED_PM_TAIL_PRIVATE_PAIR_VERIFIED", "linked_jump_report": linked,
                "linked_jump_report_canonical_sha256": frozen["linked_jump_report_canonical_sha256"],
                "linked_jump_reference": probe.LINKED_REFERENCE, "source_files_sha256": probe.SOURCE_HASHES,
                "partition_writes": 0, "normal_boot_candidate": False, "device_ready": False, "device_operation": False}
    require_fields(packed, expected, "PMTAIL_PRIVATE_IDENTITY")
    require(set(packed) == set(expected), "PMTAIL_PRIVATE_IDENTITY_FIELD_SET")
    require(canonical(packed) == canonical(reverified), "PMTAIL_PRIVATE_REVERIFY_IDENTITY_MISMATCH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--private-receipts", type=Path)
    args = parser.parse_args()
    frozen = runtime.load_freeze(observe.IMAGES)
    pair, linked = verify(args.root, frozen)
    if args.private_receipts is not None:
        require(os.environ.get("GITHUB_REPOSITORY") == PRIVATE_REPOSITORY, "PMTAIL_PRIVATE_EXECUTION_REPOSITORY")
        receipts = [json.loads((args.private_receipts / name).read_text()) for name in
                    ("private-run.json", "private-jobs.json", "packed/identity.json", "reverified/identity.json")]
        validate_private_receipts(frozen, pair, linked, *receipts)
    print("DEFERRED_PM_TAIL_OBSERVER_IDENTITY_AGREEMENT=PASS")
    if args.private_receipts is not None:
        print("DEFERRED_PM_TAIL_PRIVATE_OBSERVER_PROVENANCE=PASS")


if __name__ == "__main__":
    main()
