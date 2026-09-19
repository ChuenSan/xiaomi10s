#!/usr/bin/env python3
"""GHA-only WAITENTRY PUBLIC observer fixtures (post-do_initcalls callsite boundary)."""
from __future__ import annotations

import os

import observe

WAITENTRY8_SHA = "66201264f8d7b7f4ba7a4ce8f495e46c6d4d0764863ffa5f49109b3a71944d7d"
WAITENTRY1_SHA = "8b422262aa73809a2258ecb7e8a3e36941eff683ed8cb2b3cce16dd4072d530e"
PRIOR_FAMILIES = ("fs", "upper", "control", "mid", "post39", "post46", "post49", "post51",
                  "reset", "rest", "kinit", "free", "smp", "initcalls", "console", "pure",
                  "core", "postcore", "arch", "subsys", "devprobe", "late_devprobe")


def reject(case: str, identity: tuple[int, str], gate: str) -> None:
    try:
        observe.validate_identity(case, *identity)
    except ValueError as exc:
        if str(exc) != "IMAGE_IDENTITY_MISMATCH":
            raise
        print(f"{gate}=PASS")
        return
    raise SystemExit(f"{gate}=FAIL")


def record(case: str, total: float) -> dict:
    return {"protocol": observe.PROTOCOL, "case": case,
            "image_sha256": observe.IMAGES[case][1], "context": observe.CONTEXT,
            "status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": "b",
            "experimental_boots": 1, "total_s": total,
            "bootloader_origin": observe.REST_ORIGIN}


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GITHUB_ACTIONS_ONLY")
    waitentry8 = observe.IMAGES["waitentry8"]
    waitentry1 = observe.IMAGES["waitentry1"]
    if waitentry8 != (37380096, WAITENTRY8_SHA) or waitentry1 != (37380096, WAITENTRY1_SHA):
        raise SystemExit("FROZEN_WAITENTRY_IDENTITY_DRIFT")
    observe.validate_identity("waitentry8", *waitentry8)
    observe.validate_identity("waitentry1", *waitentry1)
    print("WAITENTRY8_EXACT_FULL_SHA_ACCEPT=PASS")
    print("WAITENTRY1_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("waitentry8", (waitentry8[0] + 1, waitentry8[1]), "WAITENTRY_WRONG_SIZE_REJECT")
    reject("waitentry1", (waitentry1[0], "0" * 64), "WAITENTRY_WRONG_SHA_REJECT")
    reject("waitentry8", waitentry1, "WAITENTRY8_REJECTS_WAITENTRY1_SWAP")
    reject("waitentry1", waitentry8, "WAITENTRY1_REJECTS_WAITENTRY8_SWAP")
    rejections = 0
    for family in PRIOR_FAMILIES:
        for member in ("8", "1"):
            prior = family + member
            if prior not in observe.IMAGES:
                continue
            reject("waitentry8", observe.IMAGES[prior], f"WAITENTRY8_REJECTS_{prior.upper()}")
            reject("waitentry1", observe.IMAGES[prior], f"WAITENTRY1_REJECTS_{prior.upper()}")
            rejections += 2
    print(f"WAITENTRY_CROSS_IDENTITY_REJECTIONS={rejections}")
    print("WAITENTRY_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_waitentry_geometry(56)
    for wrong, token in ((60, "WAITENTRY_60B_WINDOW_REJECTED"),
                         (52, "WAITENTRY_52B_WINDOW_REJECTED")):
        try:
            observe.validate_waitentry_geometry(wrong)
        except ValueError as exc:
            if str(exc) != token:
                raise
        else:
            raise SystemExit(f"WAITENTRY_{wrong}B_WINDOW_ACCEPTED")
    print("WAITENTRY_60B_NEGATIVE_FIXTURE=PASS")
    print("WAITENTRY_52B_NEGATIVE_FIXTURE=PASS")
    geo = observe.WAITENTRY_GEOMETRY
    if geo != {"target": "kernel_init_freeable", "va": 0xFFFF800081B3113C,
               "offset": 0x1B3113C, "caller_va": 0xFFFF800081B3103C,
               "caller_end_va": 0xFFFF800081B311A8, "cold_path_va": 0xFFFF800081B31174,
               "window": 56, "core_size": 56,
               "architecture": "INLINE_CALLSITE_NO_ADDED_LANDING_PAD",
               "predecessor": "do_basic_setup", "callsite_only": True,
               "no_paciasp_prefix": True, "daifset": "PRESENT", "inline_only": True,
               "trampoline_permitted": False, "proves": "late_initcalls_completed",
               "does_not_prove": "wait_for_initramfs_return"}:
        raise SystemExit("WAITENTRY_GEOMETRY_DRIFT")
    print("WAITENTRY_56B_CALLSITE_GEOMETRY=PASS")
    print("WAITENTRY_CALLSITE_NO_LANDING_PAD=PASS")
    print("WAITENTRY_AFTER_DO_BASIC_SETUP_PREDECESSOR=PASS")
    print("WAITENTRY_TRAMPOLINE_FORBIDDEN=PASS")

    baseline = record("waitentry8", 35.0)
    strong = observe.pair_verdict(baseline, record("waitentry1", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("late_initcalls_completed") != "PROVEN" \
            or strong.get("wait_for_initramfs_entry") != "NOT_PROVEN" \
            or strong.get("wait_for_initramfs_return") != "NOT_PROVEN" \
            or strong.get("console_on_rootfs_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("WAITENTRY_STRONG_PROOF_BOUNDARY_INVALID")
    print("WAITENTRY_STRONG_PROVES_LATE_INITCALLS_COMPLETED=PASS")
    print("WAITENTRY_WAIT_RETURN_CONSOLE_INIT_REMAIN_NOT_PROVEN=PASS")

    supported = observe.pair_verdict(baseline, record("waitentry1", 29.5))
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("late_initcalls_completed") != "SUPPORTED":
        raise SystemExit("WAITENTRY_SUPPORTED_GRADE_INVALID")
    print("WAITENTRY_SUPPORTED_GRADE=PASS")

    no_shift = observe.pair_verdict(baseline, record("waitentry1", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("late_initcalls_completed") != "NOT_PROVEN" \
            or no_shift.get("post_initcalls_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("WAITENTRY_NO_SHIFT_SEMANTICS_INVALID")
    print("WAITENTRY_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("WAITENTRY_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
