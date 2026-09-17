#!/usr/bin/env python3
"""GHA-only ARCH8/ARCH1 observer identity, 160B geometry and protocol fixtures."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import observe


ARCH8_SHA = "7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d"
ARCH1_SHA = "f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113"
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
    size8, configured8 = observe.IMAGES["arch8"]
    size1, configured1 = observe.IMAGES["arch1"]
    if configured8 != ARCH8_SHA or configured1 != ARCH1_SHA:
        raise SystemExit("FROZEN_ARCH_BOOT_SHA_DRIFT")
    observe.validate_arch_geometry(160)
    try:
        observe.validate_arch_geometry(60)
    except ValueError as exc:
        if str(exc) != "ARCH_60B_WINDOW_REJECTED":
            raise
        print("ARCH_60B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("ARCH_60B_WINDOW_ACCEPTED")
    geo = observe.ARCH_GEOMETRY
    if geo["target"] != "topology_init" or geo["offset"] != 0x1B346FC \
            or geo["function_size"] != 188 or geo["window"] != 160 \
            or geo["entry"] != "paciasp" or geo["back_edge_src"] != 0x9C:
        raise SystemExit("ARCH_GEOMETRY_DRIFT")
    print("ARCH_160B_GEOMETRY_GATE=PASS")
    sha8, sha1 = ARCH8_SHA, ARCH1_SHA
    observe.validate_identity("arch8", size8, sha8)
    observe.validate_identity("arch1", size1, sha1)
    print("ARCH8_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    print("ARCH1_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("arch8", size1, sha1, "ARCH8_OBSERVER_REJECTS_ARCH1")
    reject("arch1", size8, sha8, "ARCH1_OBSERVER_REJECTS_ARCH8")
    reject("arch8", size8, "0" * 64, "WRONG_BOOT_SHA_REJECT")
    reject("arch1", size1 + 1, sha1, "WRONG_SIZE_REJECT")
    reject("arch8", size8, mutated(sha8, "one-byte"), "ONE_BYTE_MUTATION_REJECT")
    reject("arch1", size1, mutated(sha1, "one-byte"), "ARCH1_ONE_BYTE_MUTATION_REJECT")
    reject("arch8", size8, sha1, "PAYLOAD_SWAP_REJECT")
    reject("arch8", size8, mutated(sha8, "target"), "WRONG_TARGET_REJECT")
    reject("arch8", size8, mutated(sha8, "window"), "WRONG_WINDOW_LENGTH_REJECT")
    reject("arch8", size8, mutated(sha8, "60b"), "SIXTY_BYTE_TOPOLOGY_PROBE_REJECT")
    reject("arch8", size8, mutated(sha8, "paciasp"), "WRONG_PACIASP_HANDLING_REJECT")
    reject("arch8", size8, mutated(sha8, "backedge"), "BACKEDGE_SOURCE_LEFT_LIVE_REJECT")
    reject("arch8", size8, mutated(sha8, "checkpoint"), "WRONG_CHECKPOINT_REJECT")
    reject("arch1", size1, mutated(sha1, "checkpoint"), "ARCH1_WRONG_CHECKPOINT_REJECT")
    reject("arch8", size8, mutated(sha8, "delay"), "WRONG_DELAY_REJECT")
    reject("arch1", size1, mutated(sha1, "delay"), "ARCH1_WRONG_DELAY_REJECT")
    reject("arch8", size8, mutated(sha8, "psci"), "WRONG_PSCI_REJECT")
    reject("arch1", size1, mutated(sha1, "psci"), "ARCH1_WRONG_PSCI_REJECT")
    reject("arch8", 37380096, FIX8_SHA, "ARCH8_REJECTS_FIX8")
    reject("arch1", 37380096, FIX8_SHA, "ARCH1_REJECTS_FIX8")
    for old in ("postcore8", "postcore1", "core8", "core1", "pure8", "pure1",
                "console8", "console1", "initcalls8", "initcalls1", "smp8", "smp1",
                "free8", "free1", "kinit8", "kinit1", "rest8", "rest1", "reset8", "reset1"):
        reject("arch8", *observe.IMAGES[old], f"ARCH8_REJECTS_{old.upper()}")
        reject("arch1", *observe.IMAGES[old], f"ARCH1_REJECTS_{old.upper()}")
    src = Path(observe.__file__).read_text()
    for token in ("SECOND_EXPERIMENTAL_BOOT_FORBIDDEN", "LAST_MOMENT_SLOT_NOT_B",
                  '["boot", str(self.args.image)]',
                  '"manual_timing_excluded": True'):
        if token not in src:
            raise SystemExit(f"PROTOCOL_TOKEN_MISSING:{token}")
    baseline = {"protocol": observe.PROTOCOL, "case": "arch8",
                "image_sha256": sha8, "context": observe.CONTEXT,
                "status": "MANUAL_RECOVERY", "final_slot": "b",
                "experimental_boots": 1, "total_s": 35.0,
                "bootloader_origin": observe.REST_ORIGIN}
    result = {**baseline, "case": "arch1", "image_sha256": sha1,
              "total_s": 28.0}
    try:
        observe.pair_verdict(baseline, result)
    except ValueError:
        print("MANUAL_RECOVERY_TIMING_NOT_PROOF=PASS")
    else:
        raise SystemExit("MANUAL_RECOVERY_TIMING_ACCEPTED")
    automatic = {**baseline, "status": "AUTOMATIC_FASTBOOT_RETURN"}
    strong = observe.pair_verdict(automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN"})
    if strong.get("verdict") != "STRONG" or strong.get("arch_initcalls_completed") != "PROVEN" \
            or strong.get("first_subsys_initcall_entry") != "PROVEN" \
            or strong.get("first_subsys_initcall_body") != "NOT_PROVEN" \
            or strong.get("subsys_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("ARCH_STRONG_BOUNDARY_INVALID")
    supported = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 29.5})
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("arch_initcalls_completed") != "STRONGLY_SUPPORTED" \
            or supported.get("first_subsys_initcall_entry") != "STRONGLY_SUPPORTED":
        raise SystemExit("ARCH_SUPPORTED_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(
        automatic, {**result, "status": "AUTOMATIC_FASTBOOT_RETURN", "total_s": 35.0})
    if no_shift.get("arch_initcalls_checkpoint_shift_not_observed") != "YES" \
            or no_shift.get("next") != "ARCH_INITCALLS_FAILURE_ISOLATION_CI" \
            or "arch_initcalls_not_completed" in no_shift:
        raise SystemExit("ARCH_NO_SHIFT_BOUNDARY_INVALID")
    print("ARCH_FUTURE_PAIR_BOUNDARIES=PASS")
    print("SECOND_BOOT_FORBIDDEN=PASS")
    print("RAM_BOOT_ONLY=PASS")
    print("ARCH_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    print("ARCH_PAIR_EXECUTION_ORDER=ARCH8_THEN_ARCH1")
    print("ARCH8_OBSERVER_READY=YES")
    print("ARCH1_OBSERVER_READY=YES")
    print("ARCH_PAIR_OBSERVER_FIXTURES=PASS")


if __name__ == "__main__":
    main()
