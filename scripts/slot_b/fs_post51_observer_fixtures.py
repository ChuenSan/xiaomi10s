#!/usr/bin/env python3
"""GHA-only FS post-51 PUBLIC observer fixtures."""
from __future__ import annotations

import os

import observe


POST518_SHA = "7d6e527c977b3dd08d9f4896d44648bc7b9020993a8841e91285c84c67cc81ae"
POST511_SHA = "3c825488ba0b41a534369a476f05f3b20c1279f017275212dc52d4761e3d9d1a"


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
    post518 = observe.IMAGES["post518"]
    post511 = observe.IMAGES["post511"]
    if post518 != (37380096, POST518_SHA) or post511 != (37380096, POST511_SHA):
        raise SystemExit("FROZEN_POST51_IDENTITY_DRIFT")
    observe.validate_identity("post518", *post518)
    observe.validate_identity("post511", *post511)
    print("POST518_EXACT_FULL_SHA_ACCEPT=PASS")
    print("POST511_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("post518", (post518[0] + 1, post518[1]), "POST51_WRONG_SIZE_REJECT")
    reject("post511", (post511[0], "0" * 64), "POST51_WRONG_SHA_REJECT")
    reject("post518", post511, "POST518_REJECTS_POST511_SWAP")
    reject("post511", post518, "POST511_REJECTS_POST518_SWAP")
    for family in ("upper", "mid", "control", "fs", "post39", "post46", "post49"):
        for member in ("8", "1"):
            old = family + member
            reject("post518", observe.IMAGES[old], f"POST518_REJECTS_{old.upper()}")
            reject("post511", observe.IMAGES[old], f"POST511_REJECTS_{old.upper()}")
    print("POST51_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_post51_geometry(60)
    try:
        observe.validate_post51_geometry(56)
    except ValueError as exc:
        if str(exc) != "POST51_56B_WINDOW_REJECTED":
            raise
        print("POST51_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("POST51_56B_WINDOW_ACCEPTED")
    observe.validate_post51_table()
    geo, table = observe.POST51_GEOMETRY, observe.POST51_TABLE
    if geo != {"target": "populate_rootfs", "va": 0xFFFF800081B32388,
               "offset": 0x1B32388, "function_size": 88, "window": 60,
               "core_size": 56, "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
               "entry": "paciasp", "daifset": "PRESENT", "inline_only": True,
               "prel32_unchanged": True}:
        raise SystemExit("POST51_GEOMETRY_DRIFT")
    if table != {"index": 52, "symbol": "populate_rootfs", "va": 0xFFFF800081B32388,
                  "table_va": 0xFFFF800081D0B1A4, "offset": 0x1B32388,
                  "registration": "rootfs_initcall(populate_rootfs)",
                  "source": "init/initramfs.c"}:
        raise SystemExit("POST51_TABLE_DRIFT")
    print("POST51_60B_INLINE_GEOMETRY=PASS")
    print("POST51_INDEX52_TABLE_GATE=PASS")
    print("POST51_PACIASP_56B_ULTRACOMPACT=PASS")
    print("POST51_PREL32_UNCHANGED=PASS")

    baseline = record("post518", 35.0)
    strong = observe.pair_verdict(baseline, record("post511", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("fs_post51_entry") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or strong.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN":
        raise SystemExit("POST51_STRONG_PROOF_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(baseline, record("post511", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("fs_post51_entry") != "NOT_PROVEN" \
            or no_shift.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("post51_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("POST51_NO_SHIFT_SEMANTICS_INVALID")
    print("POST51_STRONG_PROVES_ONLY_FS_POST51_ENTRY=PASS")
    print("POST51_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("FS_POST51_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
