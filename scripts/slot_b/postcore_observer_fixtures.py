#!/usr/bin/env python3
"""GHA-only POSTCORE8/POSTCORE1 observer identity and protocol fixtures."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import observe


POSTCORE8_SHA = "141d67931f8792036119c131d93ffa74649af2c6c44d086b489851230075355c"
POSTCORE1_SHA = "4762a9fd29e109affb1c8864247887334508d9af2d6b183b7bf0200a05b697f1"
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
    size8, configured8 = observe.IMAGES["postcore8"]
    size1, configured1 = observe.IMAGES["postcore1"]
    if configured8 != POSTCORE8_SHA or configured1 != POSTCORE1_SHA:
        raise SystemExit("FROZEN_POSTCORE_BOOT_SHA_DRIFT")
    sha8, sha1 = POSTCORE8_SHA, POSTCORE1_SHA
    observe.validate_identity("postcore8", size8, sha8)
    observe.validate_identity("postcore1", size1, sha1)
    print("POSTCORE8_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    print("POSTCORE1_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("postcore8", size1, sha1, "POSTCORE8_OBSERVER_REJECTS_POSTCORE1")
    reject("postcore1", size8, sha8, "POSTCORE1_OBSERVER_REJECTS_POSTCORE8")
    reject("postcore8", size8, "0" * 64, "WRONG_BOOT_SHA_REJECT")
    reject("postcore1", size1 + 1, sha1, "WRONG_SIZE_REJECT")
    reject("postcore8", size8, mutated(sha8, "one-byte"), "ONE_BYTE_MUTATION_REJECT")
    reject("postcore1", size1, mutated(sha1, "one-byte"), "POSTCORE1_ONE_BYTE_MUTATION_REJECT")
    reject("postcore8", size8, sha1, "PAYLOAD_SWAP_REJECT")
    reject("postcore8", size8, mutated(sha8, "checkpoint"), "WRONG_CHECKPOINT_REJECT")
    reject("postcore1", size1, mutated(sha1, "checkpoint"), "POSTCORE1_WRONG_CHECKPOINT_REJECT")
    reject("postcore8", size8, mutated(sha8, "delay"), "WRONG_DELAY_REJECT")
    reject("postcore1", size1, mutated(sha1, "delay"), "POSTCORE1_WRONG_DELAY_REJECT")
    reject("postcore8", size8, mutated(sha8, "psci"), "WRONG_PSCI_REJECT")
    reject("postcore1", size1, mutated(sha1, "psci"), "POSTCORE1_WRONG_PSCI_REJECT")
    reject("postcore8", 37380096, FIX8_SHA, "POSTCORE8_REJECTS_FIX8")
    reject("postcore1", 37380096, FIX8_SHA, "POSTCORE1_REJECTS_FIX8")
    for old in ("core8", "core1", "pure8", "pure1", "console8", "console1",
                "initcalls8", "initcalls1", "smp8", "smp1", "free8", "free1",
                "kinit8", "kinit1", "rest8", "rest1", "reset8", "reset1"):
        reject("postcore8", *observe.IMAGES[old], f"POSTCORE8_REJECTS_{old.upper()}")
        reject("postcore1", *observe.IMAGES[old], f"POSTCORE1_REJECTS_{old.upper()}")
    src = Path(observe.__file__).read_text()
    for token in ("SECOND_EXPERIMENTAL_BOOT_FORBIDDEN", "LAST_MOMENT_SLOT_NOT_B",
                  '["boot", str(self.args.image)]',
                  '"manual_timing_excluded": True'):
        if token not in src:
            raise SystemExit(f"PROTOCOL_TOKEN_MISSING:{token}")
    baseline = {"protocol": observe.PROTOCOL, "case": "postcore8",
                "image_sha256": sha8, "context": observe.CONTEXT,
                "status": "MANUAL_RECOVERY", "final_slot": "b",
                "experimental_boots": 1, "total_s": 35.0,
                "bootloader_origin": observe.REST_ORIGIN}
    result = {**baseline, "case": "postcore1", "image_sha256": sha1,
              "total_s": 28.0}
    try:
        observe.pair_verdict(baseline, result)
    except ValueError:
        print("MANUAL_RECOVERY_TIMING_NOT_PROOF=PASS")
    else:
        raise SystemExit("MANUAL_RECOVERY_TIMING_ACCEPTED")
    automatic = {**baseline, "status": "AUTOMATIC_FASTBOOT_RETURN"}
    strong = observe.pair_verdict(automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN"})
    if strong.get("verdict") != "STRONG" or strong.get("postcore_initcalls_completed") != "PROVEN" \
            or strong.get("first_arch_initcall_entry") != "PROVEN" \
            or strong.get("first_arch_initcall_body") != "NOT_PROVEN" \
            or strong.get("arch_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("POSTCORE_STRONG_BOUNDARY_INVALID")
    supported = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 29.5})
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("postcore_initcalls_completed") != "STRONGLY_SUPPORTED" \
            or supported.get("first_arch_initcall_entry") != "STRONGLY_SUPPORTED":
        raise SystemExit("POSTCORE_SUPPORTED_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 35.0})
    if no_shift.get("postcore_initcalls_checkpoint_shift_not_observed") != "YES" \
            or no_shift.get("next") != "POSTCORE_INITCALLS_FAILURE_ISOLATION_CI" \
            or "postcore_initcalls_not_completed" in no_shift:
        raise SystemExit("POSTCORE_NO_SHIFT_BOUNDARY_INVALID")
    print("POSTCORE_FUTURE_PAIR_BOUNDARIES=PASS")
    print("SECOND_BOOT_FORBIDDEN=PASS")
    print("RAM_BOOT_ONLY=PASS")
    print("POSTCORE_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    print("POSTCORE_PAIR_EXECUTION_ORDER=POSTCORE8_THEN_POSTCORE1")
    print("POSTCORE8_OBSERVER_READY=YES")
    print("POSTCORE1_OBSERVER_READY=YES")
    print("POSTCORE_PAIR_OBSERVER_FIXTURES=PASS")


if __name__ == "__main__":
    main()
