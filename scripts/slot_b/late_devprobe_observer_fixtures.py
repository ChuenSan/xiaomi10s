#!/usr/bin/env python3
"""GHA-only LATE_DEVPROBE PUBLIC observer fixtures (level-7 earliest inline target)."""
from __future__ import annotations

import os

import observe

LATE_DEVPROBE8_SHA = "44e5001fab6f7c662e1847972b886d1aa4f7a51e3f969b4dce834ae34b60fe8f"
LATE_DEVPROBE1_SHA = "0d24156eeb37f31aceac314fe7df78a9dfaffd162134c3b5d7aa029d2e512453"
PRIOR_FAMILIES = ("fs", "upper", "control", "mid", "post39", "post46", "post49", "post51",
                  "reset", "rest", "kinit", "free", "smp", "initcalls", "console", "pure",
                  "core", "postcore", "arch", "subsys", "devprobe")


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
    late_devprobe8 = observe.IMAGES["late_devprobe8"]
    late_devprobe1 = observe.IMAGES["late_devprobe1"]
    if late_devprobe8 != (37380096, LATE_DEVPROBE8_SHA) or late_devprobe1 != (37380096, LATE_DEVPROBE1_SHA):
        raise SystemExit("FROZEN_LATE_DEVPROBE_IDENTITY_DRIFT")
    observe.validate_identity("late_devprobe8", *late_devprobe8)
    observe.validate_identity("late_devprobe1", *late_devprobe1)
    print("LATE_DEVPROBE8_EXACT_FULL_SHA_ACCEPT=PASS")
    print("LATE_DEVPROBE1_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("late_devprobe8", (late_devprobe8[0] + 1, late_devprobe8[1]), "LATE_DEVPROBE_WRONG_SIZE_REJECT")
    reject("late_devprobe1", (late_devprobe1[0], "0" * 64), "LATE_DEVPROBE_WRONG_SHA_REJECT")
    reject("late_devprobe8", late_devprobe1, "LATE_DEVPROBE8_REJECTS_LATE_DEVPROBE1_SWAP")
    reject("late_devprobe1", late_devprobe8, "LATE_DEVPROBE1_REJECTS_LATE_DEVPROBE8_SWAP")
    rejections = 0
    for family in PRIOR_FAMILIES:
        for member in ("8", "1"):
            prior = family + member
            if prior not in observe.IMAGES:
                continue
            reject("late_devprobe8", observe.IMAGES[prior], f"LATE_DEVPROBE8_REJECTS_{prior.upper()}")
            reject("late_devprobe1", observe.IMAGES[prior], f"LATE_DEVPROBE1_REJECTS_{prior.upper()}")
            rejections += 2
    print(f"LATE_DEVPROBE_CROSS_IDENTITY_REJECTIONS={rejections}")
    print("LATE_DEVPROBE_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_late_devprobe_geometry(60)
    try:
        observe.validate_late_devprobe_geometry(56)
    except ValueError as exc:
        if str(exc) != "LATE_DEVPROBE_56B_WINDOW_REJECTED":
            raise
        print("LATE_DEVPROBE_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("LATE_DEVPROBE_56B_WINDOW_ACCEPTED")
    observe.validate_late_devprobe_table()
    geo, table = observe.LATE_DEVPROBE_GEOMETRY, observe.LATE_DEVPROBE_TABLE
    if geo != {"target": "kernel_do_mounts_initrd_sysctls_init", "va": 0xFFFF800081B32078,
               "offset": 0x1B32078, "function_size": 60, "window": 60,
               "core_size": 56, "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
               "entry": "paciasp", "daifset": "PRESENT", "inline_only": True,
               "prel32_unchanged": True, "level7_index": 0}:
        raise SystemExit("LATE_DEVPROBE_GEOMETRY_DRIFT")
    if table != {"index": 0, "symbol": "kernel_do_mounts_initrd_sysctls_init",
                 "va": 0xFFFF800081B32078, "table_va": 0xFFFF800081D0C2D8,
                 "offset": 0x1B32078,
                 "registration": "late_initcall(kernel_do_mounts_initrd_sysctls_init)",
                 "source": "init/do_mounts_initrd.c"}:
        raise SystemExit("LATE_DEVPROBE_TABLE_DRIFT")
    print("LATE_DEVPROBE_60B_INLINE_GEOMETRY=PASS")
    print("LATE_DEVPROBE_INDEX0_TABLE_GATE=PASS")
    print("LATE_DEVPROBE_PACIASP_56B_ULTRACOMPACT=PASS")
    print("LATE_DEVPROBE_PREL32_UNCHANGED=PASS")

    baseline = record("late_devprobe8", 35.0)
    strong = observe.pair_verdict(baseline, record("late_devprobe1", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("device_initcalls_completed") != "PROVEN" \
            or strong.get("first_late_initcall_entry") != "PROVEN" \
            or strong.get("kernel_do_mounts_initrd_sysctls_init_entry") != "PROVEN" \
            or strong.get("late_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("console_on_rootfs_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit("LATE_DEVPROBE_STRONG_PROOF_BOUNDARY_INVALID")
    print("LATE_DEVPROBE_STRONG_PROVES_DEVICE_AND_FIRST_LATE=PASS")
    print("LATE_DEVPROBE_LATE_CONSOLE_INIT_REMAIN_NOT_PROVEN=PASS")

    supported = observe.pair_verdict(baseline, record("late_devprobe1", 29.5))
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("device_initcalls_completed") != "SUPPORTED":
        raise SystemExit("LATE_DEVPROBE_SUPPORTED_GRADE_INVALID")
    print("LATE_DEVPROBE_SUPPORTED_GRADE=PASS")

    no_shift = observe.pair_verdict(baseline, record("late_devprobe1", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("device_initcalls_completed") != "NOT_PROVEN" \
            or no_shift.get("first_late_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("kernel_do_mounts_initrd_sysctls_init_entry") != "NOT_PROVEN" \
            or no_shift.get("level7_inline_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("LATE_DEVPROBE_NO_SHIFT_SEMANTICS_INVALID")
    print("LATE_DEVPROBE_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("LATE_DEVPROBE_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
