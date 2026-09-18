#!/usr/bin/env python3
"""GHA-only FS post-46 PUBLIC observer fixtures."""
from __future__ import annotations

import os

import observe


POST468_SHA = "4092ceaedb54f94fe6079cdf987fd719620a712465fee30d9fd20b8a3e5dc843"
POST461_SHA = "f0b80158e90f91f8dbbb47cd84f8b92be93d86cad9690514859af3629061ea32"


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
    post468 = observe.IMAGES["post468"]
    post461 = observe.IMAGES["post461"]
    if post468 != (37380096, POST468_SHA) or post461 != (37380096, POST461_SHA):
        raise SystemExit("FROZEN_POST46_IDENTITY_DRIFT")
    observe.validate_identity("post468", *post468)
    observe.validate_identity("post461", *post461)
    print("POST468_EXACT_FULL_SHA_ACCEPT=PASS")
    print("POST461_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("post468", (post468[0] + 1, post468[1]), "POST46_WRONG_SIZE_REJECT")
    reject("post461", (post461[0], "0" * 64), "POST46_WRONG_SHA_REJECT")
    reject("post468", post461, "POST468_REJECTS_POST461_SWAP")
    reject("post461", post468, "POST461_REJECTS_POST468_SWAP")
    for family in ("upper", "mid", "control", "fs", "post39"):
        for member in ("8", "1"):
            old = family + member
            reject("post468", observe.IMAGES[old], f"POST468_REJECTS_{old.upper()}")
            reject("post461", observe.IMAGES[old], f"POST461_REJECTS_{old.upper()}")
    print("POST46_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_post46_geometry(60)
    try:
        observe.validate_post46_geometry(56)
    except ValueError as exc:
        if str(exc) != "POST46_56B_WINDOW_REJECTED":
            raise
        print("POST46_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("POST46_56B_WINDOW_ACCEPTED")
    observe.validate_post46_table()
    geo, table = observe.POST46_GEOMETRY, observe.POST46_TABLE
    if geo != {"target": "vlan_offload_init", "va": 0xFFFF800081BAEDFC,
               "offset": 0x1BAEDFC, "function_size": 60, "window": 60,
               "core_size": 56, "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
               "entry": "paciasp", "daifset": "PRESENT", "inline_only": True,
               "prel32_unchanged": True}:
        raise SystemExit("POST46_GEOMETRY_DRIFT")
    if table != {"index": 49, "symbol": "vlan_offload_init", "va": 0xFFFF800081BAEDFC,
                  "table_va": 0xFFFF800081D0B198, "offset": 0x1BAEDFC,
                  "registration": "fs_initcall(vlan_offload_init)",
                  "source": "net/8021q/vlan_core.c"}:
        raise SystemExit("POST46_TABLE_DRIFT")
    print("POST46_60B_INLINE_GEOMETRY=PASS")
    print("POST46_INDEX49_TABLE_GATE=PASS")
    print("POST46_PACIASP_56B_ULTRACOMPACT=PASS")
    print("POST46_PREL32_UNCHANGED=PASS")

    baseline = record("post468", 35.0)
    strong = observe.pair_verdict(baseline, record("post461", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("fs_post46_entry") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or strong.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN":
        raise SystemExit("POST46_STRONG_PROOF_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(baseline, record("post461", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("fs_post46_entry") != "NOT_PROVEN" \
            or no_shift.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("post46_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("POST46_NO_SHIFT_SEMANTICS_INVALID")
    print("POST46_STRONG_PROVES_ONLY_FS_POST46_ENTRY=PASS")
    print("POST46_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("FS_POST46_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
