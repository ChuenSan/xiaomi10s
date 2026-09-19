#!/usr/bin/env python3
"""GHA-only WAITRET PUBLIC observer fixtures (post wait_for_initramfs return boundary)."""
from __future__ import annotations

import os

import observe

WAITRET8_SHA = "2c589a61933d8f657e0ac08374c6038d0624807f11c6acb22fc1851ca0b9cb2a"
WAITRET1_SHA = "0a67761550906d05e602be83afe6b2f5e10cf4d222bdcc3bdc65e24fb950d2c8"
PRIOR_FAMILIES = ("fs", "upper", "control", "mid", "post39", "post46", "post49", "post51",
                  "reset", "rest", "kinit", "free", "smp", "initcalls", "console", "pure",
                  "core", "postcore", "arch", "subsys", "devprobe", "late_devprobe",
                  "waitentry")


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
    waitret8 = observe.IMAGES["waitret8"]
    waitret1 = observe.IMAGES["waitret1"]
    if waitret8 != (37380096, WAITRET8_SHA) or waitret1 != (37380096, WAITRET1_SHA):
        raise SystemExit("FROZEN_WAITRET_IDENTITY_DRIFT")
    observe.validate_identity("waitret8", *waitret8)
    observe.validate_identity("waitret1", *waitret1)
    print("WAITRET8_EXACT_FULL_SHA_ACCEPT=PASS")
    print("WAITRET1_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("waitret8", (waitret8[0] + 1, waitret8[1]), "WAITRET_WRONG_SIZE_REJECT")
    reject("waitret1", (waitret1[0], "0" * 64), "WAITRET_WRONG_SHA_REJECT")
    reject("waitret8", waitret1, "WAITRET8_REJECTS_WAITRET1_SWAP")
    reject("waitret1", waitret8, "WAITRET1_REJECTS_WAITRET8_SWAP")
    rejections = 0
    for family in PRIOR_FAMILIES:
        for member in ("8", "1"):
            prior = family + member
            if prior not in observe.IMAGES:
                continue
            reject("waitret8", observe.IMAGES[prior], f"WAITRET8_REJECTS_{prior.upper()}")
            reject("waitret1", observe.IMAGES[prior], f"WAITRET1_REJECTS_{prior.upper()}")
            rejections += 2
    print(f"WAITRET_CROSS_IDENTITY_REJECTIONS={rejections}")
    print("WAITRET_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_waitret_geometry(52)
    for wrong, token in ((60, "WAITRET_60B_WINDOW_REJECTED"),
                         (56, "WAITRET_56B_WINDOW_REJECTED")):
        try:
            observe.validate_waitret_geometry(wrong)
        except ValueError as exc:
            if str(exc) != token:
                raise
        else:
            raise SystemExit(f"WAITRET_{wrong}B_WINDOW_ACCEPTED")
    print("WAITRET_60B_NEGATIVE_FIXTURE=PASS")
    print("WAITRET_56B_NEGATIVE_FIXTURE=PASS")
    geo = observe.WAITRET_GEOMETRY
    if geo != {"target": "kernel_init_freeable", "va": 0xFFFF800081B31140,
               "offset": 0x1B31140, "caller_va": 0xFFFF800081B3103C,
               "caller_end_va": 0xFFFF800081B311A8, "cold_path_va": 0xFFFF800081B31174,
               "window": 52, "core_size": 52,
               "architecture": "INLINE_CALLSITE_NO_ADDED_LANDING_PAD",
               "predecessor": "wait_for_initramfs", "callsite_only": True,
               "no_paciasp_prefix": True, "daifset": "ABSENT", "inline_only": True,
               "trampoline_permitted": False, "proves": "wait_for_initramfs_return",
               "does_not_prove": "console_on_rootfs_entry"}:
        raise SystemExit("WAITRET_GEOMETRY_DRIFT")
    print("WAITRET_52B_CALLSITE_GEOMETRY=PASS")
    print("WAITRET_CALLSITE_NO_LANDING_PAD=PASS")
    print("WAITRET_AFTER_WAIT_FOR_INITRAMFS_PREDECESSOR=PASS")
    print("WAITRET_TRAMPOLINE_FORBIDDEN=PASS")

    baseline = record("waitret8", 35.0)
    strong = observe.pair_verdict(baseline, record("waitret1", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("wait_for_initramfs_return") != "PROVEN" \
            or strong.get("wait_for_initramfs_entry") != "PROVEN" \
            or strong.get("console_on_rootfs_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("WAITRET_STRONG_PROOF_BOUNDARY_INVALID")
    print("WAITRET_STRONG_PROVES_WAIT_RETURN_AND_ENTRY=PASS")
    print("WAITRET_CONSOLE_INIT_REMAIN_NOT_PROVEN=PASS")

    supported = observe.pair_verdict(baseline, record("waitret1", 29.5))
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("wait_for_initramfs_return") != "SUPPORTED":
        raise SystemExit("WAITRET_SUPPORTED_GRADE_INVALID")
    print("WAITRET_SUPPORTED_GRADE=PASS")

    no_shift = observe.pair_verdict(baseline, record("waitret1", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("wait_for_initramfs_return") != "NOT_PROVEN" \
            or no_shift.get("wait_for_initramfs_entry") != "NOT_PROVEN" \
            or no_shift.get("wait_ret_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("WAITRET_NO_SHIFT_SEMANTICS_INVALID")
    print("WAITRET_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("WAITRET_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
