#!/usr/bin/env python3
"""GHA-only FS post-39 PUBLIC observer fixtures."""
from __future__ import annotations

import os

import observe


POST398_SHA = "b1ba8335dd671a9d026783e5539547fb2df3d314e7d8757b769b823967d1d4d6"
POST391_SHA = "23a24d95ac8fe17229b3e425d777b3b7938d32c110a8070546836aaba79f6e8f"


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
    post398 = observe.IMAGES["post398"]
    post391 = observe.IMAGES["post391"]
    if post398 != (37380096, POST398_SHA) or post391 != (37380096, POST391_SHA):
        raise SystemExit("FROZEN_POST39_IDENTITY_DRIFT")
    observe.validate_identity("post398", *post398)
    observe.validate_identity("post391", *post391)
    print("POST398_EXACT_FULL_SHA_ACCEPT=PASS")
    print("POST391_EXACT_FULL_SHA_ACCEPT=PASS")
    reject("post398", (post398[0] + 1, post398[1]), "POST39_WRONG_SIZE_REJECT")
    reject("post391", (post391[0], "0" * 64), "POST39_WRONG_SHA_REJECT")
    reject("post398", post391, "POST398_REJECTS_POST391_SWAP")
    reject("post391", post398, "POST391_REJECTS_POST398_SWAP")
    for family in ("upper", "mid", "control", "fs"):
        for member in ("8", "1"):
            old = family + member
            reject("post398", observe.IMAGES[old], f"POST398_REJECTS_{old.upper()}")
            reject("post391", observe.IMAGES[old], f"POST391_REJECTS_{old.upper()}")
    print("POST39_CROSS_IDENTITY_REJECTION=PASS")

    observe.validate_post39_geometry(60)
    try:
        observe.validate_post39_geometry(56)
    except ValueError as exc:
        if str(exc) != "POST39_56B_WINDOW_REJECTED":
            raise
        print("POST39_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("POST39_56B_WINDOW_ACCEPTED")
    observe.validate_post39_table()
    geo, table = observe.POST39_GEOMETRY, observe.POST39_TABLE
    if geo != {"target": "af_unix_init", "va": 0xFFFF800081BAE798,
               "offset": 0x1BAE798, "function_size": 216, "window": 60,
               "core_size": 56, "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
               "entry": "paciasp", "daifset": "PRESENT", "inline_only": True,
               "prel32_unchanged": True}:
        raise SystemExit("POST39_GEOMETRY_DRIFT")
    if table != {"index": 46, "symbol": "af_unix_init", "va": 0xFFFF800081BAE798,
                  "table_va": 0xFFFF800081D0B18C, "offset": 0x1BAE798,
                  "registration": "fs_initcall(af_unix_init)",
                  "source": "net/unix/af_unix.c"}:
        raise SystemExit("POST39_TABLE_DRIFT")
    print("POST39_60B_INLINE_GEOMETRY=PASS")
    print("POST39_INDEX46_TABLE_GATE=PASS")
    print("POST39_PACIASP_56B_ULTRACOMPACT=PASS")
    print("POST39_PREL32_UNCHANGED=PASS")

    baseline = record("post398", 35.0)
    strong = observe.pair_verdict(baseline, record("post391", 28.0))
    if strong.get("verdict") != "STRONG" \
            or strong.get("fs_post39_entry") != "PROVEN" \
            or strong.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or strong.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN":
        raise SystemExit("POST39_STRONG_PROOF_BOUNDARY_INVALID")
    no_shift = observe.pair_verdict(baseline, record("post391", 35.0))
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("fs_post39_entry") != "NOT_PROVEN" \
            or no_shift.get("first_device_initcall_entry") != "NOT_PROVEN" \
            or no_shift.get("post39_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit("POST39_NO_SHIFT_SEMANTICS_INVALID")
    print("POST39_STRONG_PROVES_ONLY_FS_POST39_ENTRY=PASS")
    print("POST39_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print("FS_POST39_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
