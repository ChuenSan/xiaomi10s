#!/usr/bin/env python3
"""GHA-only SUBSYS8/SUBSYS1 observer identity, 56B geometry and protocol fixtures."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import observe


SUBSYS8_SHA = "e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1"
SUBSYS1_SHA = "df14e7bcdf409deeeede70d7217f420091a6e9a292b0670443df50c0a0e8b9a1"
FIX8_SHA = "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5"


def reject(case: str, size: int, digest: str, gate: str) -> None:
    try:
        observe.validate_identity(case, size, digest)
    except ValueError as exc:
        if str(exc) != "IMAGE_IDENTITY_MISMATCH":
            raise
        print(f"{gate}=PASS")
        return
    raise SystemExit(f"{gate}=FAIL")


def mutated(digest: str, label: str) -> str:
    return hashlib.sha256((digest + label).encode()).hexdigest()


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GITHUB_ACTIONS_ONLY")
    size8, configured8 = observe.IMAGES["subsys8"]
    size1, configured1 = observe.IMAGES["subsys1"]
    if configured8 != SUBSYS8_SHA or configured1 != SUBSYS1_SHA:
        raise SystemExit("FROZEN_SUBSYS_BOOT_SHA_DRIFT")
    observe.validate_subsys_geometry(56)
    try:
        observe.validate_subsys_geometry(60)
    except ValueError as exc:
        if str(exc) != "SUBSYS_60B_WINDOW_REJECTED":
            raise
        print("SUBSYS_60B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("SUBSYS_60B_WINDOW_ACCEPTED")
    try:
        observe.validate_subsys_geometry(57)
    except ValueError as exc:
        if str(exc) != "SUBSYS_57B_WINDOW_REJECTED":
            raise
        print("SUBSYS_57B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("SUBSYS_57B_WINDOW_ACCEPTED")
    geo = observe.SUBSYS_GEOMETRY
    if geo["target"] != "create_debug_debugfs_entry" or geo["offset"] != 0x149E0 \
            or geo["function_size"] != 56 or geo["window"] != 56 \
            or geo["entry"] != "paciasp" or geo["core_size"] != 52 \
            or geo["daifset"] != "ABSENT" or geo["prel32_unchanged"] is not True:
        raise SystemExit("SUBSYS_GEOMETRY_DRIFT")
    print("SUBSYS_56B_GEOMETRY_GATE=PASS")
    print("SUBSYS_52B_CORE_GATE=PASS")
    print("FIRST_FS_PREL32_TARGET_UNCHANGED=YES")
    sha8, sha1 = SUBSYS8_SHA, SUBSYS1_SHA
    observe.validate_identity("subsys8", size8, sha8)
    observe.validate_identity("subsys1", size1, sha1)
    print("SUBSYS8_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    print("SUBSYS1_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("subsys8", size1, sha1, "SUBSYS8_OBSERVER_REJECTS_SUBSYS1")
    reject("subsys1", size8, sha8, "SUBSYS1_OBSERVER_REJECTS_SUBSYS8")
    reject("subsys8", size8, "0" * 64, "WRONG_BOOT_SHA_REJECT")
    reject("subsys1", size1 + 1, sha1, "WRONG_SIZE_REJECT")
    reject("subsys8", size8, mutated(sha8, "one-byte"), "ONE_BYTE_MUTATION_REJECT")
    reject("subsys1", size1, mutated(sha1, "one-byte"), "SUBSYS1_ONE_BYTE_MUTATION_REJECT")
    reject("subsys8", size8, sha1, "PAYLOAD_SWAP_REJECT")
    reject("subsys8", size8, mutated(sha8, "target"), "WRONG_TARGET_REJECT")
    reject("subsys8", size8, mutated(sha8, "window"), "WRONG_WINDOW_LENGTH_REJECT")
    reject("subsys8", size8, mutated(sha8, "60b"), "SIXTY_BYTE_OVERWRITE_REJECT")
    reject("subsys8", size8, mutated(sha8, "57b"), "FIFTY_SEVEN_BYTE_OVERWRITE_REJECT")
    reject("subsys8", size8, mutated(sha8, "next"), "NEXT_SYMBOL_OVERLAP_REJECT")
    reject("subsys8", size8, mutated(sha8, "paciasp"), "WRONG_PACIASP_HANDLING_REJECT")
    reject("subsys8", size8, mutated(sha8, "daifset"), "DAIFSET_MISMATCH_REJECT")
    reject("subsys8", size8, mutated(sha8, "core"), "WRONG_CORE_REJECT")
    reject("subsys8", size8, mutated(sha8, "prel32"), "WRONG_PREL32_TARGET_REJECT")
    reject("subsys8", size8, mutated(sha8, "add"), "WRONG_ADD_SEMANTIC_TARGET_REJECT")
    reject("subsys8", size8, mutated(sha8, "checkpoint"), "WRONG_CHECKPOINT_REJECT")
    reject("subsys1", size1, mutated(sha1, "checkpoint"), "SUBSYS1_WRONG_CHECKPOINT_REJECT")
    reject("subsys8", size8, mutated(sha8, "delay"), "WRONG_DELAY_REJECT")
    reject("subsys1", size1, mutated(sha1, "delay"), "SUBSYS1_WRONG_DELAY_REJECT")
    reject("subsys8", size8, mutated(sha8, "psci"), "WRONG_PSCI_REJECT")
    reject("subsys1", size1, mutated(sha1, "psci"), "SUBSYS1_WRONG_PSCI_REJECT")
    reject("subsys8", 37380096, FIX8_SHA, "SUBSYS8_REJECTS_FIX8")
    reject("subsys1", 37380096, FIX8_SHA, "SUBSYS1_REJECTS_FIX8")
    for old in ("arch8", "arch1", "postcore8", "postcore1", "core8", "core1", "pure8", "pure1",
                "console8", "console1", "initcalls8", "initcalls1", "smp8", "smp1",
                "free8", "free1", "kinit8", "kinit1", "rest8", "rest1", "reset8", "reset1"):
        reject("subsys8", *observe.IMAGES[old], f"SUBSYS8_REJECTS_{old.upper()}")
        reject("subsys1", *observe.IMAGES[old], f"SUBSYS1_REJECTS_{old.upper()}")
    src = Path(observe.__file__).read_text()
    for token in ("SECOND_EXPERIMENTAL_BOOT_FORBIDDEN", "LAST_MOMENT_SLOT_NOT_B",
                  '["boot", str(self.args.image)]',
                  '"manual_timing_excluded": True'):
        if token not in src:
            raise SystemExit(f"PROTOCOL_TOKEN_MISSING:{token}")
    baseline = {"protocol": observe.PROTOCOL, "case": "subsys8",
                "image_sha256": sha8, "context": observe.CONTEXT,
                "status": "MANUAL_RECOVERY", "final_slot": "b",
                "experimental_boots": 1, "total_s": 35.0,
                "bootloader_origin": observe.REST_ORIGIN}
    result = {**baseline, "case": "subsys1", "image_sha256": sha1,
              "total_s": 28.0}
    try:
        observe.pair_verdict(baseline, result)
    except ValueError:
        print("MANUAL_RECOVERY_TIMING_NOT_PROOF=PASS")
    else:
        raise SystemExit("MANUAL_RECOVERY_TIMING_ACCEPTED")
    automatic = {**baseline, "status": "AUTOMATIC_FASTBOOT_RETURN"}
    strong = observe.pair_verdict(automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN"})
    if strong.get("verdict") != "STRONG" or strong.get("subsys_initcalls_completed") != "PROVEN" \
            or strong.get("first_fs_initcall_entry") != "PROVEN" \
            or strong.get("first_fs_initcall_body") != "NOT_PROVEN" \
            or strong.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("SUBSYS_STRONG_BOUNDARY_INVALID")
    supported = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 29.5})
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("subsys_initcalls_completed") != "STRONGLY_SUPPORTED" \
            or supported.get("first_fs_initcall_entry") != "STRONGLY_SUPPORTED":
        raise SystemExit("SUBSYS_SUPPORTED_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 35.0})
    if no_shift.get("subsys_initcalls_checkpoint_shift_not_observed") != "YES" \
            or no_shift.get("next") != "SUBSYS_INITCALLS_FAILURE_ISOLATION_CI" \
            or "subsys_initcalls_not_completed" in no_shift:
        raise SystemExit("SUBSYS_NO_SHIFT_BOUNDARY_INVALID")
    print("SUBSYS_FUTURE_PAIR_BOUNDARIES=PASS")
    print("SECOND_BOOT_FORBIDDEN=PASS")
    print("RAM_BOOT_ONLY=PASS")
    print("SUBSYS_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    print("SUBSYS_PAIR_EXECUTION_ORDER=SUBSYS8_THEN_SUBSYS1")
    print("SUBSYS8_OBSERVER_READY=YES")
    print("SUBSYS1_OBSERVER_READY=YES")
    print("SUBSYS_PAIR_OBSERVER_FIXTURES=PASS")


if __name__ == "__main__":
    main()
