"""Fail-closed identities and evidence scope for the PM-tail Slot B observer."""
import json
import re
from pathlib import Path

CASES = ("defer_pmtail8", "defer_pmtail1")
IDENTITY_PATH = Path(__file__).with_name("deferred_pm_tail_identities.json")
GEOMETRY = {"stage": "pm_tail", "offset": 0x8DE454, "window": 56,
            "parent_offset": 0x8DE450, "parent_size": 100, "boot_size": 37380096}
AUTHORITY_FIELDS = ("stage", "source_commit", "public_run", "private_commit", "private_run",
                    "linked_jump_report_canonical_sha256", "public_pair_sha256")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_freeze(frozen, images):
    require(isinstance(frozen, dict), "PMTAIL_FREEZE_FORMAT")
    for key, value in GEOMETRY.items():
        require(type(frozen.get(key)) is type(value) and frozen[key] == value,
                f"PMTAIL_FREEZE_GEOMETRY:{key}")
    for key in ("source_commit", "private_commit"):
        value = frozen.get(key)
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) and len(set(value)) > 2,
                f"PMTAIL_FREEZE_AUTHORITY:{key}")
    for key in ("public_run", "private_run"):
        require(isinstance(frozen.get(key), str) and re.fullmatch(r"[1-9][0-9]*", frozen[key]),
                f"PMTAIL_FREEZE_AUTHORITY:{key}")
    for key in ("linked_jump_report_canonical_sha256", "public_pair_sha256"):
        value = frozen.get(key)
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) and len(set(value)) > 2,
                f"PMTAIL_FREEZE_REPORT_HASH:{key}")
    require(set(frozen) == set(GEOMETRY) | set(AUTHORITY_FIELDS) | {"members"}, "PMTAIL_FREEZE_FIELD_SET")
    members = frozen.get("members")
    require(isinstance(members, dict) and set(members) == {"8", "1"}, "PMTAIL_FREEZE_MEMBERS")
    old_boots = {identity[1] for case, identity in images.items() if case not in CASES}
    hashes = []
    for delay, member in members.items():
        require(isinstance(member, dict) and set(member) == {"boot_size", "boot_sha256", "payload_sha256"},
                "PMTAIL_FREEZE_MEMBER_FIELDS")
        require(type(member.get("boot_size")) is int and member["boot_size"] == GEOMETRY["boot_size"],
                "PMTAIL_FREEZE_SIZE")
        for key in ("boot_sha256", "payload_sha256"):
            value = member[key]
            require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) and len(set(value)) > 2,
                    f"PMTAIL_FREEZE_HASH:{delay}:{key}")
            hashes.append(value)
        require(member["boot_sha256"] not in old_boots, "PMTAIL_FROZEN_EXPERIMENT_REUSED")
        require(images.get(f"defer_pmtail{delay}") == (member["boot_size"], member["boot_sha256"]),
                "PMTAIL_IDENTITY_NOT_FROZEN")
    require(len(set(hashes)) == 4, "PMTAIL_FREEZE_HASH_COLLISION")
    return frozen


def load_freeze(images):
    try:
        frozen = json.loads(IDENTITY_PATH.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("PMTAIL_IDENTITY_NOT_FROZEN") from None
    return validate_freeze(frozen, images)


def authority(frozen):
    return {key: frozen[key] for key in AUTHORITY_FIELDS}


def validate_record(record, frozen):
    expected = {**authority(frozen), "ci_run": frozen["private_run"], "normal_boot_candidate": False,
                "slot_a_written": False, "partition_writes": 0, "host_boot_commands": 1,
                "experimental_boots": 1, "recovery_control_boots": 0, "b_retries": "6"}
    for key, value in expected.items():
        require(type(record.get(key)) is type(value) and record[key] == value,
                f"PMTAIL_RECORD_AUTHORITY:{key}")
    require(record.get("manual_timing_excluded", False) is False, "PMTAIL_MANUAL_TIMING_EXCLUDED")


def preflight(args, images, pair_verdict):
    frozen = load_freeze(images)
    require(getattr(args, "ci_run", None) == frozen["private_run"], "PMTAIL_CI_RUN_MISMATCH")
    baseline = None
    if args.case == CASES[1]:
        require(getattr(args, "baseline", None) is not None, "MATCHED_8S_BASELINE_REQUIRED")
        try:
            baseline = json.loads(args.baseline.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError("PMTAIL_BASELINE_UNREADABLE") from None
        require(isinstance(baseline, dict), "PMTAIL_BASELINE_FORMAT")
        pair_verdict(baseline, {**baseline, "case": args.case, "image_sha256": images[args.case][1]})
    else:
        require(args.case == CASES[0] and getattr(args, "baseline", None) is None,
                "PMTAIL_FIRST_MEMBER_BASELINE_FORBIDDEN")
    return frozen, baseline


def proof(grade, verdict):
    result = {"original_reason_clear_store_executed": grade, "worker_mutex_unlock_returned": grade,
              "persistent_reason_field_state": "NOT_PROVEN", "srcu_or_pm_lock_acquired": "NOT_PROVEN",
              "deferred_pm_tail_return": "NOT_PROVEN", "pm_list_movement": "NOT_PROVEN",
              "deferred_first_bus_probe_entered": "NOT_PROVEN", "deferred_first_bus_probe_returned": "NOT_PROVEN",
              "deferred_device_identity": "NOT_PROVEN", "deferred_get_device_reference_success": "NOT_PROVEN",
              "deferred_allocation_freed": "NOT_PROVEN", "deferred_driver_probe_body": "NOT_PROVEN",
              "deferred_culprit_driver": "NOT_PROVEN", "late_initcalls_completed": "NOT_PROVEN",
              "wait_for_initramfs_return": "NOT_PROVEN", "console_on_rootfs_entry": "NOT_PROVEN",
              "init_executed": "NOT_PROVEN", "usb": "FROZEN"}
    if verdict == "SHIFT_NOT_OBSERVED":
        result["deferred_pm_tail_shift_not_observed"] = "YES"
    return result
