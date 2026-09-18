#!/usr/bin/env python3
"""GHA-only FS post-49 PUBLIC observer fixtures."""
from __future__ import annotations

import os

import observe


POST498_SHA = "c8ff8dc637d80ef1b0d0a3dbab6869f3879450998a9df546e2af25cea64b2a14"
POST491_SHA = "73c63cf6360a962d7fc555f65281aef23da1864ff185f30dfa693d69e8862a6c"


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
    post498 = observe.IMAGES["post498"]
    post491 = observe.IMAGES["post491"]
    if post498 != (37380096, POST498_SHA) or post491 != (37380096, POST491_SHA):
        raise SystemExit("FROZEN_POST49_IDENTITY_DRIFT")
    observe.validate_identity("post498", *post498)
    observe.validate_identity("post491", *post491)
    print("POST498_EXACT_FULL_SHA_ACCEPT=PASS")
    print("POST491_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("post498", (post498[0] + 1, post498[1]), "POST49_WRONG_SIZE_REJECT")
    reject("post491", (post491[0], "0" * 64), "POST49_WRONG_SHA_REJECT")
    reject("post498", post491, "POST498_REJECTS_POST491_SWAP")
    reject("post491", post498, "POST491_REJECTS_POST498_SWAP")
    for family in ("upper", "mid", "control", "fs", "post39", "post46"):
        for member in ("8", "1"):
            old = family + member
            reject("post498", observe.IMAGES[old], f"POST498_REJECTS_{old.upper()}")
            reject("post491", observe.IMAGES[old], f"POST491_REJECTS_{old.upper()}")
    print("POST49_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_post49_geometry(60)
    try:
        observe.validate_post49_geometry(56)
    except ValueError as exc:
        if str(exc) != "POST49_56B_WINDOW_REJECTED":
            raise
        print("POST49_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("POST49_56B_WINDOW_ACCEPTED")
    observe.validate_post49_table()
    geo, table = observe.POST49_GEOMETRY, observe.POST49_TABLE
    if geo != {"target": "acpi_reserve_resources", "va": 0xFFFF800081B6B2FC,
               "offset": 0x1B6B2FC, "function_size": 256, "window": 60,
               "core_size": 56, "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
               "entry": "paciasp", "daifset": "PRESENT", "inline_only": True,
               "prel32_unchanged": True}:
        raise SystemExit("POST49_GEOMETRY_DRIFT")
    if table != {"index": 51, "symbol": "acpi_reserve_resources", "va": 0xFFFF800081B6B2FC,
                  "table_va": 0xFFFF800081D0B1A0, "offset": 0x1B6B2FC,
                  "registration": "fs_initcall_sync(acpi_reserve_resources)",
                  "source": "drivers/acpi/osl.c"}:
        raise SystemExit("POST49_TABLE_DRIFT")
    print("POST49_60B_INLINE_GEOMETRY=PASS")
    print("POST49_INDEX51_TABLE_GATE=PASS")
    print("POST49_PACIASP_56B_ULTRACOMPACT=PASS")
    print("POST49_PREL32_UNCHANGED=PASS")

    baseline = record("post498", 35.0)
    strong = observe.pair_verdict(baseline, record("post491", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("fs_post49_entry") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or strong.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN":
        raise SystemExit("POST49_STRONG_PROOF_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(baseline, record("post491", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("fs_post49_entry") != "NOT_PROVEN" \
            or no_shift.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("post49_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("POST49_NO_SHIFT_SEMANTICS_INVALID")
    print("POST49_STRONG_PROVES_ONLY_FS_POST49_ENTRY=PASS")
    print("POST49_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("FS_POST49_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
