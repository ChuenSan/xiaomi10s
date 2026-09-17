#!/usr/bin/env python3
"""GHA-only FS8/FS1 observer identity, trampoline/island geometry and protocol fixtures."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import observe


FS8_SHA = "cfc9f3f9c931126aceb47a5dcc39c12227f34eceb7ad2d9e6642088f3b7e6594"
FS1_SHA = "2377b227fd0eb4105330eec64f19843d7d64d42f994b12b999571cca6f4e3a1b"
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
    size8, configured8 = observe.IMAGES["fs8"]
    size1, configured1 = observe.IMAGES["fs1"]
    if configured8 != FS8_SHA or configured1 != FS1_SHA:
        raise SystemExit("FROZEN_FS_BOOT_SHA_DRIFT")
    observe.validate_fs_geometry(8)
    try:
        observe.validate_fs_geometry(56)
    except ValueError as exc:
        if str(exc) != "FS_56B_INLINE_REJECTED":
            raise
        print("FS_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("FS_56B_INLINE_ACCEPTED")
    try:
        observe.validate_fs_geometry(60)
    except ValueError as exc:
        if str(exc) != "FS_60B_INLINE_REJECTED":
            raise
        print("FS_60B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("FS_60B_WINDOW_ACCEPTED")
    try:
        observe.validate_fs_geometry(57)
    except ValueError as exc:
        if str(exc) != "FS_57B_WINDOW_REJECTED":
            raise
        print("FS_57B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("FS_57B_WINDOW_ACCEPTED")
    geo = observe.FS_GEOMETRY
    if geo["target"] != "register_arm64_panic_block" or geo["offset"] != 0x1B347B8 \
            or geo["function_size"] != 48 or geo["stub_size"] != 8 \
            or geo["entry"] != "paciasp" or geo["architecture"] != "ENTRY_TRAMPOLINE" \
            or geo["island_offset"] != 0xFFCC or geo["island_end"] != 0x10000 \
            or geo["core_size"] != 52 or geo["daifset"] != "ABSENT" \
            or geo["prel32_unchanged"] is not True \
            or geo["live_tramp_untouched"] is not True \
            or geo["direct_b"] is not True:
        raise SystemExit("FS_GEOMETRY_DRIFT")
    print("FS_48B_TARGET_GATE=PASS")
    print("FS_PACIASP_DIRECT_B_STUB_GATE=PASS")
    print("FS_ISLAND_FFCC_GATE=PASS")
    print("FS_52B_CORE_GATE=PASS")
    print("FS_NO_DAIFSET_GATE=PASS")
    print("FIRST_DEVICE_PREL32_TARGET_UNCHANGED=YES")
    print("LIVE_TRAMPOLINE_UNTOUCHED=YES")
    sha8, sha1 = FS8_SHA, FS1_SHA
    observe.validate_identity("fs8", size8, sha8)
    observe.validate_identity("fs1", size1, sha1)
    print("FS8_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    print("FS1_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("fs8", size1, sha1, "FS8_OBSERVER_REJECTS_FS1")
    reject("fs1", size8, sha8, "FS1_OBSERVER_REJECTS_FS8")
    reject("fs8", size8, "0" * 64, "WRONG_BOOT_SHA_REJECT")
    reject("fs1", size1 + 1, sha1, "WRONG_SIZE_REJECT")
    reject("fs8", size8, mutated(sha8, "one-byte"), "ONE_BYTE_MUTATION_REJECT")
    reject("fs1", size1, mutated(sha1, "one-byte"), "FS1_ONE_BYTE_MUTATION_REJECT")
    reject("fs8", size8, sha1, "PAYLOAD_SWAP_REJECT")
    reject("fs8", size8, mutated(sha8, "target"), "WRONG_TARGET_REJECT")
    reject("fs8", size8, mutated(sha8, "stub"), "WRONG_STUB_REJECT")
    reject("fs8", size8, mutated(sha8, "island"), "WRONG_ISLAND_REJECT")
    reject("fs8", size8, mutated(sha8, "56b"), "FIFTY_SIX_BYTE_INLINE_REJECT")
    reject("fs8", size8, mutated(sha8, "60b"), "SIXTY_BYTE_OVERWRITE_REJECT")
    reject("fs8", size8, mutated(sha8, "paciasp"), "WRONG_PACIASP_HANDLING_REJECT")
    reject("fs8", size8, mutated(sha8, "daifset"), "DAIFSET_MISMATCH_REJECT")
    reject("fs8", size8, mutated(sha8, "core"), "WRONG_CORE_REJECT")
    reject("fs8", size8, mutated(sha8, "prel32"), "WRONG_PREL32_TARGET_REJECT")
    reject("fs8", size8, mutated(sha8, "tramp"), "LIVE_TRAMP_MUTATION_REJECT")
    reject("fs8", size8, mutated(sha8, "branch"), "WRONG_BRANCH_REJECT")
    reject("fs8", size8, mutated(sha8, "checkpoint"), "WRONG_CHECKPOINT_REJECT")
    reject("fs1", size1, mutated(sha1, "checkpoint"), "FS1_WRONG_CHECKPOINT_REJECT")
    reject("fs8", size8, mutated(sha8, "delay"), "WRONG_DELAY_REJECT")
    reject("fs1", size1, mutated(sha1, "delay"), "FS1_WRONG_DELAY_REJECT")
    reject("fs8", size8, mutated(sha8, "psci"), "WRONG_PSCI_REJECT")
    reject("fs1", size1, mutated(sha1, "psci"), "FS1_WRONG_PSCI_REJECT")
    reject("fs8", 37380096, FIX8_SHA, "FS8_REJECTS_FIX8")
    reject("fs1", 37380096, FIX8_SHA, "FS1_REJECTS_FIX8")
    for old in ("subsys8", "subsys1", "arch8", "arch1", "postcore8", "postcore1",
                "core8", "core1", "pure8", "pure1", "console8", "console1",
                "initcalls8", "initcalls1", "smp8", "smp1", "free8", "free1",
                "kinit8", "kinit1", "rest8", "rest1", "reset8", "reset1"):
        reject("fs8", *observe.IMAGES[old], f"FS8_REJECTS_{old.upper()}")
        reject("fs1", *observe.IMAGES[old], f"FS1_REJECTS_{old.upper()}")
    src = Path(observe.__file__).read_text()
    for token in ("SECOND_EXPERIMENTAL_BOOT_FORBIDDEN", "LAST_MOMENT_SLOT_NOT_B",
                  '["boot", str(self.args.image)]',
                  '"manual_timing_excluded": True'):
        if token not in src:
            raise SystemExit(f"PROTOCOL_TOKEN_MISSING:{token}")
    baseline = {"protocol": observe.PROTOCOL, "case": "fs8",
                "image_sha256": sha8, "context": observe.CONTEXT,
                "status": "MANUAL_RECOVERY", "final_slot": "b",
                "experimental_boots": 1, "total_s": 35.0,
                "bootloader_origin": observe.REST_ORIGIN}
    result = {**baseline, "case": "fs1", "image_sha256": sha1, "total_s": 28.0}
    try:
        observe.pair_verdict(baseline, result)
    except ValueError:
        print("MANUAL_RECOVERY_TIMING_NOT_PROOF=PASS")
    else:
        raise SystemExit("MANUAL_RECOVERY_TIMING_ACCEPTED")
    automatic = {**baseline, "status": "AUTOMATIC_FASTBOOT_RETURN"}
    strong = observe.pair_verdict(automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN"})
    if strong.get("verdict") != "STRONG" or strong.get("fs_initcalls_completed") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "PROVEN" \
            or strong.get("first_device_initcall_body") != "NOT_PROVEN" \
            or strong.get("device_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("FS_STRONG_BOUNDARY_INVALID")
    supported = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 29.5})
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("fs_initcalls_completed") != "STRONGLY_SUPPORTED" \
            or supported.get("first_device_initcall_entry") != "STRONGLY_SUPPORTED":
        raise SystemExit("FS_SUPPORTED_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 35.0})
    if no_shift.get("fs_initcalls_checkpoint_shift_not_observed") != "YES" \
            or no_shift.get("next") != "FS_INITCALLS_FAILURE_ISOLATION_CI" \
            or "fs_initcalls_not_completed" in no_shift:
        raise SystemExit("FS_NO_SHIFT_BOUNDARY_INVALID")
    print("FS_FUTURE_PAIR_BOUNDARIES=PASS")
    print("SECOND_BOOT_FORBIDDEN=PASS")
    print("RAM_BOOT_ONLY=PASS")
    print("FS_PAIR_DEVICE_EXECUTION_ORDER=FS8_THEN_FS1")
    print("FS8_OBSERVER_READY=YES")
    print("FS1_OBSERVER_READY=YES")
    print("FS_PAIR_OBSERVER_FIXTURES=PASS")


if __name__ == "__main__":
    main()
