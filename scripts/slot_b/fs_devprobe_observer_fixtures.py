#!/usr/bin/env python3
"""GHA-only DEVPROBE PUBLIC observer fixtures (level-6 earliest inline target)."""
from __future__ import annotations

import os

import observe

DEVPROBE8_SHA = "94ae6d101ee0e0092d5041367a70747fac95e8eaf5b51d1f79857264b2f64b31"
DEVPROBE1_SHA = "2e8b1f5b313195b86ac8a4de14f3a2eb7bf33c7efa575bb425ddb981d1a2b90f"
PRIOR_FAMILIES = ("fs", "upper", "control", "mid", "post39", "post46", "post49", "post51",
                  "reset", "rest", "kinit", "free", "smp", "initcalls", "console", "pure",
                  "core", "postcore", "arch", "subsys")


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
    devprobe8 = observe.IMAGES["devprobe8"]
    devprobe1 = observe.IMAGES["devprobe1"]
    if devprobe8 != (37380096, DEVPROBE8_SHA) or devprobe1 != (37380096, DEVPROBE1_SHA):
        raise SystemExit("FROZEN_DEVPROBE_IDENTITY_DRIFT")
    observe.validate_identity("devprobe8", *devprobe8)
    observe.validate_identity("devprobe1", *devprobe1)
    print("DEVPROBE8_EXACT_FULL_SHA_ACCEPT=PASS")
    print("DEVPROBE1_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("devprobe8", (devprobe8[0] + 1, devprobe8[1]), "DEVPROBE_WRONG_SIZE_REJECT")
    reject("devprobe1", (devprobe1[0], "0" * 64), "DEVPROBE_WRONG_SHA_REJECT")
    reject("devprobe8", devprobe1, "DEVPROBE8_REJECTS_DEVPROBE1_SWAP")
    reject("devprobe1", devprobe8, "DEVPROBE1_REJECTS_DEVPROBE8_SWAP")
    rejections = 0
    for family in PRIOR_FAMILIES:
        for member in ("8", "1"):
            prior = family + member
            if prior not in observe.IMAGES:
                continue
            reject("devprobe8", observe.IMAGES[prior], f"DEVPROBE8_REJECTS_{prior.upper()}")
            reject("devprobe1", observe.IMAGES[prior], f"DEVPROBE1_REJECTS_{prior.upper()}")
            rejections += 2
    print(f"DEVPROBE_CROSS_IDENTITY_REJECTIONS={rejections}")
    print("DEVPROBE_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_devprobe_geometry(60)
    try:
        observe.validate_devprobe_geometry(56)
    except ValueError as exc:
        if str(exc) != "DEVPROBE_56B_WINDOW_REJECTED":
            raise
        print("DEVPROBE_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("DEVPROBE_56B_WINDOW_ACCEPTED")
    observe.validate_devprobe_table()
    geo, table = observe.DEVPROBE_GEOMETRY, observe.DEVPROBE_TABLE
    if geo != {"target": "cpuinfo_regs_init", "va": 0xFFFF800081B34D8C,
               "offset": 0x1B34D8C, "function_size": 220, "window": 60,
               "core_size": 56, "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
               "entry": "paciasp", "daifset": "PRESENT", "inline_only": True,
               "prel32_unchanged": True, "level6_index": 1}:
        raise SystemExit("DEVPROBE_GEOMETRY_DRIFT")
    if table != {"index": 1, "symbol": "cpuinfo_regs_init", "va": 0xFFFF800081B34D8C,
                 "table_va": 0xFFFF800081D0B1AC, "offset": 0x1B34D8C,
                 "registration": "device_initcall(cpuinfo_regs_init)",
                 "source": "arch/arm64/kernel/cpuinfo.c"}:
        raise SystemExit("DEVPROBE_TABLE_DRIFT")
    print("DEVPROBE_60B_INLINE_GEOMETRY=PASS")
    print("DEVPROBE_INDEX1_TABLE_GATE=PASS")
    print("DEVPROBE_PACIASP_56B_ULTRACOMPACT=PASS")
    print("DEVPROBE_PREL32_UNCHANGED=PASS")

    baseline = record("devprobe8", 35.0)
    strong = observe.pair_verdict(baseline, record("devprobe1", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("fs_initcalls_completed") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "PROVEN" \
            or strong.get("cpuinfo_regs_init_entry") != "PROVEN" \
            or strong.get("device_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("late_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("console_on_rootfs_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("DEVPROBE_STRONG_PROOF_BOUNDARY_INVALID")
    print("DEVPROBE_STRONG_PROVES_FS_AND_FIRST_DEVICE=PASS")
    print("DEVPROBE_DEVICE_AND_LATE_REMAIN_NOT_PROVEN=PASS")

    supported = observe.pair_verdict(baseline, record("devprobe1", 29.5))
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("fs_initcalls_completed") != "SUPPORTED" \
            or supported.get("first_device_initcall_entry") != "SUPPORTED" \
            or supported.get("device_initcalls_completed") != "NOT_PROVEN":
        raise SystemExit("DEVPROBE_SUPPORTED_GRADE_INVALID")
    print("DEVPROBE_SUPPORTED_GRADE=PASS")

    no_shift = observe.pair_verdict(baseline, record("devprobe1", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or no_shift.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("cpuinfo_regs_init_entry") != "NOT_PROVEN" \
            or no_shift.get("level6_inline_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("DEVPROBE_NO_SHIFT_SEMANTICS_INVALID")
    print("DEVPROBE_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("FS_DEVPROBE_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
