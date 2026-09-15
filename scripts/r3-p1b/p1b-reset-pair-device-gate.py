#!/usr/bin/env python3
"""RESET pair device-gate source audit. GHA only. No pack, no device."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OBS8 = HERE / "observe-r3-p1b-reset8.py"
OBS1 = HERE / "observe-r3-p1b-reset1.py"
FIX = HERE / "observer-reset-pair-fixtures.py"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-restart-chokepoint-device-gate.yml"
DOC = REPO / "docs" / "route-r3-p1b-restart-chokepoint-predevice-readiness.md"
STATUS = REPO / "docs" / "route-r3-current-status.md"
PRE_WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-restart-chokepoint-predevice.yml"


def fail(msg: str) -> None:
    raise SystemExit(f"RESET_DEVICE_GATE_SOURCE_FAILED {msg}")


def need(text: str, tok: str) -> None:
    if tok not in text:
        fail(f"missing {tok!r}")


def forbid(text: str, tok: str) -> None:
    if tok in text:
        fail(f"forbidden {tok!r}")


def cmd_source_gate(_args: argparse.Namespace) -> None:
    for p in (OBS8, OBS1, FIX, Path(__file__), WF, DOC, STATUS, PRE_WF):
        if not p.is_file():
            fail(f"missing {p}")
    o8 = OBS8.read_text()
    o1 = OBS1.read_text()
    fx = FIX.read_text()
    wf = WF.read_text()
    for src, label in ((o8, "RESET8"), (o1, "RESET1")):
        need(src, "FASTBOOT_BOOT_ONLY")
        need(src, "SECOND_BOOT_FORBIDDEN")
        need(src, "RESET_CALLER_IDENTITY=NOT_PROVEN")
        need(src, "ORIGINAL_MACHINE_RESTART_BODY_EXECUTED=NOT_PROVEN")
        need(src, "DO_KERNEL_RESTART_EXECUTED=NOT_PROVEN")
        need(src, "PSCI_SYS_RESET_EXECUTED=NOT_PROVEN")
        need(src, "NO_LINUX_RESTART=NOT_LICENSED")
        need(src, "RESET_PAIR_DEVICE_EXECUTION_SPLIT")
        need(src, f"R3_{label}_SHA256")
        need(src, f"R3_{label}_BOOT_IMG")
        need(src, "PENTRY8_BOOT")
        need(src, "PENTRY1_BOOT")
        need(src, "C_DELAY_BOOT")
        need(src, "FIX8_BOOT")
        need(src, "PANIC30_BOOT")
        need(src, "MACHINE_RESTART_INLINE")
        forbid(src, "NO_LINUX_RESTART=YES")
    need(o8, "RESET8_MEMBER_A_COMPLETED")
    need(o8, "RESET1_DEVICE_AUTHORIZED=NO")
    need(o8, "ABSOLUTE_TIMING=SECONDARY_ONLY")
    need(o1, "RESET_PAIR_EXPECTED_DELTA")
    need(o1, "RESET1_PAIR_A_STRONG")
    need(o1, "RESTART_CHOKE_DELAY_CONTROL_NOT_REFLECTED")
    if o8.count("MACHINE_RESTART_ENTRY_REACHED=PROVEN") != 1:
        fail("RESET8 must mention PROVEN only as forbidden license")
    need(fx, "RESET_PAIR_OBSERVER_FIXTURES=PASS")
    need(fx, "RESET8_OBSERVER_FULL_SHA_GATE=PASS")
    need(fx, "RESET1_OBSERVER_FULL_SHA_GATE=PASS")
    need(fx, "1BYTE_MUTATED")
    need(fx, "PAYLOAD_SWAP")
    need(fx, "MANUAL_NOT_PROOF")
    need(wf, "observer-reset-pair-fixtures.py")
    need(wf, "RESET_PAIR_OBSERVER_FIXTURES=PASS")
    need(wf, "DEVICE_OPERATION=NO")
    for verb in ("mkbootimg", "splice-boot", "fastboot", "adb "):
        forbid(wf, verb)
    if re.search(r"READY_FOR_R3_P1B_RESTART_CHOKEPOINT_RESET1_DEVICE_CONTROL=YES",
                 wf):
        fail("public workflow authorizes RESET1")
    doc = DOC.read_text()
    need(doc, "DEVICE GATE FINALIZATION")
    need(doc, "RESET_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    need(doc, "RESET_PAIR_EXECUTION_ORDER=RESET8_THEN_RESET1")
    need(doc, "READY_FOR_R3_P1B_RESTART_CHOKEPOINT_RESET8_DEVICE_CONTROL=YES")
    need(doc, "READY_FOR_R3_P1B_RESTART_CHOKEPOINT_RESET1_DEVICE_CONTROL=NO")
    need(doc, "RESET_PROOF_BOUNDARY_AUDITED=PASS")
    need(doc, "PRIVATE_PACK_RUN=NONE")
    st = STATUS.read_text()
    need(st, "RESET8_BOOT_SHA256=1422a187bb82cca1dfd85ec0805e2fcb6b6fdea1d48d1a09f8a8e68c9e825b7f")
    need(st, "RESET1_BOOT_SHA256=43b9737ac02cd4947b2173109cf6f5dc49b85d5291dbc438c8a2945600aa0ae8")
    need(st, "RESET_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    need(st, "READY_FOR_R3_P1B_RESTART_CHOKEPOINT_RESET1_DEVICE_CONTROL=NO")
    print("RESET_DEVICE_GATE_SOURCE=PASS")
    print("RESET_PAIR_DEVICE_EXECUTION_SPLIT=REQUIRED")
    print("RESET_PAIR_EXECUTION_ORDER=RESET8_THEN_RESET1")
    print("DEVICE_OPERATION=NO")
    print("SLOT_A_WRITTEN=NO")
    print("LOCAL_BUILD=NO")
    print("PARTITION_WRITES=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("source-gate",))
    args = ap.parse_args()
    cmd_source_gate(args)


if __name__ == "__main__":
    main()
