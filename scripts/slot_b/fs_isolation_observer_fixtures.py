#!/usr/bin/env python3
"""GHA-only FS isolation CONTROL/MID geometry fixtures. Boot identity binds after private pack."""
from __future__ import annotations

import os

import observe


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GITHUB_ACTIONS_ONLY")
    observe.validate_control_geometry(8)
    try:
        observe.validate_control_geometry(56)
    except ValueError as exc:
        if str(exc) != "CONTROL_56B_INLINE_REJECTED":
            raise
        print("CONTROL_56B_NEGATIVE_FIXTURE=PASS")
    else:
        raise SystemExit("CONTROL_56B_INLINE_ACCEPTED")
    geo = observe.CONTROL_GEOMETRY
    if geo["target"] != "create_debug_debugfs_entry" or geo["offset"] != 0x149E0 \
            or geo["function_size"] != 56 or geo["stub_size"] != 8 \
            or geo["architecture"] != "ENTRY_TRAMPOLINE" \
            or geo["island_offset"] != 0xFFCC or geo["core_size"] != 52 \
            or geo["daifset"] != "ABSENT" or geo["prel32_unchanged"] is not True \
            or geo["live_tramp_untouched"] is not True or geo["direct_b"] is not True \
            or geo["force_trampoline"] is not True:
        raise SystemExit("CONTROL_GEOMETRY_DRIFT")
    print("CONTROL_KNOWN_REACHED_TARGET_GATE=PASS")
    print("CONTROL_PACIASP_DIRECT_B_STUB_GATE=PASS")
    print("CONTROL_ISLAND_FFCC_GATE=PASS")
    print("CONTROL_52B_CORE_GATE=PASS")
    print("CONTROL_NO_DAIFSET_GATE=PASS")
    print("CONTROL_PREL32_UNCHANGED=YES")
    print("CONTROL_LIVE_TRAMPOLINE_UNTOUCHED=YES")
    print("CONTROL_FORCE_TRAMPOLINE=YES")
    observe.validate_mid_table()
    mid = observe.MID_TABLE
    if mid["index"] != 26 or mid["symbol"] != "proc_meminfo_init" \
            or mid["va"] != 0xFFFF800081B5770C \
            or mid["registration"] != "fs_initcall(proc_meminfo_init)":
        raise SystemExit("MID_TABLE_DRIFT")
    print("MID_INDEX_GATE=PASS")
    print("MID_SYMBOL_GATE=PASS")
    print("MID_UNIQUE_TABLE_TARGET_GATE=PASS")
    print("CONTROL_OBSERVER_IDENTITY=DEFERRED_UNTIL_PRIVATE_PACK")
    print("MID_OBSERVER_IDENTITY=DEFERRED_UNTIL_PRIVATE_PACK")
    print("FS_ISOLATION_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
