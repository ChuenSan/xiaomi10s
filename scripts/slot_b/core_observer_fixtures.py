#!/usr/bin/env python3
"""GHA-only CORE8/CORE1 observer identity and protocol fixtures."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import observe


CORE8_SHA = "5d7d5b88668e1925e3a79c677c2b630bb81d66135fec2761016de1da52fd7272"
CORE1_SHA = "a66c3f7a95e05905f5f65d96cb7f378ccdad9edf33814271425829ce10fe3e6c"
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
    size8, configured8 = observe.IMAGES["core8"]
    size1, configured1 = observe.IMAGES["core1"]
    if configured8 != CORE8_SHA or configured1 != CORE1_SHA:
        raise SystemExit("FROZEN_CORE_BOOT_SHA_DRIFT")
    sha8, sha1 = CORE8_SHA, CORE1_SHA
    observe.validate_identity("core8", size8, sha8)
    observe.validate_identity("core1", size1, sha1)
    print("CORE8_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    print("CORE1_OBSERVER_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("core8", size1, sha1, "CORE8_OBSERVER_REJECTS_CORE1")
    reject("core1", size8, sha8, "CORE1_OBSERVER_REJECTS_CORE8")
    reject("core8", size8, "0" * 64, "WRONG_BOOT_SHA_REJECT")
    reject("core1", size1 + 1, sha1, "WRONG_SIZE_REJECT")
    reject("core8", size8, mutated(sha8, "one-byte"), "ONE_BYTE_MUTATION_REJECT")
    reject("core1", size1, mutated(sha1, "one-byte"), "CORE1_ONE_BYTE_MUTATION_REJECT")
    reject("core8", size8, sha1, "PAYLOAD_SWAP_REJECT")
    reject("core8", size8, mutated(sha8, "checkpoint"), "WRONG_CHECKPOINT_REJECT")
    reject("core1", size1, mutated(sha1, "checkpoint"), "CORE1_WRONG_CHECKPOINT_REJECT")
    reject("core8", size8, mutated(sha8, "delay"), "WRONG_DELAY_REJECT")
    reject("core1", size1, mutated(sha1, "delay"), "CORE1_WRONG_DELAY_REJECT")
    reject("core8", size8, mutated(sha8, "psci"), "WRONG_PSCI_REJECT")
    reject("core1", size1, mutated(sha1, "psci"), "CORE1_WRONG_PSCI_REJECT")
    reject("core8", 37380096, FIX8_SHA, "CORE8_REJECTS_FIX8")
    reject("core1", 37380096, FIX8_SHA, "CORE1_REJECTS_FIX8")
    for old in ("pure8", "pure1", "console8", "console1", "initcalls8",
                "initcalls1", "smp8", "smp1", "free8", "free1",
                "kinit8", "kinit1", "rest8", "rest1", "reset8", "reset1"):
        reject("core8", *observe.IMAGES[old], f"CORE8_REJECTS_{old.upper()}")
        reject("core1", *observe.IMAGES[old], f"CORE1_REJECTS_{old.upper()}")
    src = Path(observe.__file__).read_text()
    for token in ("SECOND_EXPERIMENTAL_BOOT_FORBIDDEN", "LAST_MOMENT_SLOT_NOT_B",
                  '["boot", str(self.args.image)]',
                  '"manual_timing_excluded": True'):
        if token not in src:
            raise SystemExit(f"PROTOCOL_TOKEN_MISSING:{token}")
    baseline = {"protocol": observe.PROTOCOL, "case": "core8",
                "image_sha256": sha8, "context": observe.CONTEXT,
                "status": "MANUAL_RECOVERY", "final_slot": "b",
                "experimental_boots": 1, "total_s": 35.0,
                "bootloader_origin": observe.REST_ORIGIN}
    result = {**baseline, "case": "core1", "image_sha256": sha1,
              "total_s": 28.0}
    try:
        observe.pair_verdict(baseline, result)
    except ValueError:
        print("MANUAL_RECOVERY_TIMING_NOT_PROOF=PASS")
    else:
        raise SystemExit("MANUAL_RECOVERY_TIMING_ACCEPTED")
    print("SECOND_BOOT_FORBIDDEN=PASS")
    print("RAM_BOOT_ONLY=PASS")
    print("CORE_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    print("CORE8_OBSERVER_READY=YES")
    print("CORE1_OBSERVER_READY=YES")
    print("CORE_PAIR_OBSERVER_FIXTURES=PASS")


if __name__ == "__main__":
    main()
