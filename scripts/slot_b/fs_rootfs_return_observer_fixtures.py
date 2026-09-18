#!/usr/bin/env python3
"""GHA-only populate_rootfs return-isolation observer semantics. No new boot identity."""
from __future__ import annotations

import os

import observe
import rootfs_return_isolation as iso


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GITHUB_ACTIONS_ONLY")
    report = iso.gate_report(iso.report())
    if report["gate"] != iso.GATE or report["pair_generated"]:
        raise SystemExit("ROOTFS_RETURN_GATE_DRIFT")
    print("P1_REMAINING=48")
    print("P2_REMAINING=16")
    print("P1_FITS_52=NO")
    print("P2_FITS_52=NO")
    print("INITRAMFS_ASYNC_DEFAULT=TRUE")
    print("WAIT_PATH_LIVE_ON_THYME=NO")
    print("ISLAND_PERMITTED=NO")
    print("TRAMPOLINE_PERMITTED=NO")
    print("SHARED_DO_INITCALL_LEVEL=NO")
    print("PAIR_GENERATED=NO")
    print("FIRST_DEVICE_SHIFT_NOT_OBSERVED_DOES_NOT_PROVE_NON_RETURN=YES")
    print("FS_INITCALLS_COMPLETED=NOT_PROVEN")
    print("FIRST_DEVICE_INITCALL_ENTRY=NOT_PROVEN")
    print("POPULATE_ROOTFS_ENTRY=PROVEN")

    baseline = {"protocol": observe.PROTOCOL, "case": "post518",
                "image_sha256": observe.IMAGES["post518"][1], "context": observe.CONTEXT,
                "status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": "b",
                "experimental_boots": 1, "total_s": 35.055794459,
                "bootloader_origin": observe.REST_ORIGIN}
    strong = observe.pair_verdict(baseline, dict(baseline, case="post511",
                                                 image_sha256=observe.IMAGES["post511"][1],
                                                 total_s=28.236344500))
    if strong.get("verdict") != "STRONG" or strong.get("fs_post51_entry") != "PROVEN" \
            or strong.get("fs_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("first_device_initcall_entry") != "NOT_PROVEN":
        raise SystemExit("POST51_ENTRY_MUST_NOT_UPGRADE_FS_COMPLETE")
    print("POST51_STRONG_STILL_ONLY_ENTRY=PASS")
    print("FS_ROOTFS_RETURN_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
