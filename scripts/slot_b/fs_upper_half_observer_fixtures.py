#!/usr/bin/env python3
"""GHA-only FS upper-half PUBLIC observer fixtures."""
from __future__ import annotations

import os

import observe


UPPER8_SHA = "bae4daac1fff579deaaf81707312373240a01bac7cf4a73b4abeac514d8fe9e9"
UPPER1_SHA = "e68e1786d906258f46d15b66fb70b87e72b499698dca89c337f48d038dd5aa44"


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
    upper8 = observe.IMAGES["upper8"]
    upper1 = observe.IMAGES["upper1"]
    if upper8 != (37380096, UPPER8_SHA) or upper1 != (37380096, UPPER1_SHA):
        raise SystemExit("FROZEN_UPPER_IDENTITY_DRIFT")
    observe.validate_identity("upper8", *upper8)
    observe.validate_identity("upper1", *upper1)
    print("UPPER8_EXACT_FULL_SHA_ACCEPT=PASS")
    print("UPPER1_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("upper8", (upper8[0] + 1, upper8[1]), "UPPER_WRONG_SIZE_REJECT")
    reject("upper1", (upper1[0], "0" * 64), "UPPER_WRONG_SHA_REJECT")
    reject("upper8", upper1, "UPPER8_REJECTS_UPPER1_SWAP")
    reject("upper1", upper8, "UPPER1_REJECTS_UPPER8_SWAP")
    for family in ("mid", "control", "fs"):
        for member in ("8", "1"):
            old = family + member
            reject("upper8", observe.IMAGES[old], f"UPPER8_REJECTS_{old.upper()}")
            reject("upper1", observe.IMAGES[old], f"UPPER1_REJECTS_{old.upper()}")
    print("UPPER_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_upper_geometry(56)
    try:
        observe.validate_upper_geometry(60)
    except ValueError as exc:
        if str(exc) != "UPPER_60B_WINDOW_REJECTED":
            raise
        print("UPPER_60B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("UPPER_60B_WINDOW_ACCEPTED")
    observe.validate_upper_table()
    geo, table = observe.UPPER_GEOMETRY, observe.UPPER_TABLE
    if geo != {"target": "chr_dev_init", "va": 0xFFFF800081B8CD40,
               "offset": 0x1B8CD40, "function_size": 184, "window": 56,
               "core_size": 52, "architecture": "INLINE_PACIASP_PLUS_52B_NO_DAIFSET",
               "entry": "paciasp", "daifset": "ABSENT", "inline_only": True,
               "prel32_unchanged": True}:
        raise SystemExit("UPPER_GEOMETRY_DRIFT")
    if table != {"index": 39, "symbol": "chr_dev_init", "va": 0xFFFF800081B8CD40,
                  "table_va": 0xFFFF800081D0B170, "offset": 0x1B8CD40,
                  "registration": "fs_initcall(chr_dev_init)",
                  "source": "drivers/char/mem.c"}:
        raise SystemExit("UPPER_TABLE_DRIFT")
    print("UPPER_56B_INLINE_GEOMETRY=PASS")
    print("UPPER_INDEX39_TABLE_GATE=PASS")
    print("UPPER_PACIASP_52B_NO_DAIFSET=PASS")
    print("UPPER_PREL32_UNCHANGED=PASS")

    baseline = record("upper8", 35.0)
    strong = observe.pair_verdict(baseline, record("upper1", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("fs_upper_half_entry") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN":
        raise SystemExit("UPPER_STRONG_PROOF_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(baseline, record("upper1", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("fs_upper_half_entry") != "NOT_PROVEN" \
            or no_shift.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("upper_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("UPPER_NO_SHIFT_SEMANTICS_INVALID")
    print("UPPER_STRONG_PROVES_ONLY_FS_UPPER_HALF_ENTRY=PASS")
    print("UPPER_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("FS_UPPER_HALF_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
