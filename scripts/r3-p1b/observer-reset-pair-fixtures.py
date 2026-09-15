#!/usr/bin/env python3
"""Observer fixtures for RESET8 / RESET1 device-gate identities.

GHA only. No device. Guards FULL-SHA identity, sibling refusal, historical
misboot refusal, pair decoder, member-A no-solo-proof, and protocol tokens.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBS8 = HERE / "observe-r3-p1b-reset8.py"
OBS1 = HERE / "observe-r3-p1b-reset1.py"

PROVEN = "MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_DELAY_PAIR_PROVEN"
ISO = "MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_FAILURE_ISOLATION_CI"
WD = "MAINLINE_V2_R3_P1B_WATCHDOG_HANDOFF_PREDEVICE_READINESS_CI"
GOOD_SHA = "ab" * 32
GOOD_SHA2 = "cd" * 32
RESET8_FIXTURE_TOTAL = 26.000


def fail(name: str, detail: str) -> None:
    raise SystemExit(f"OBSERVER_RESET_PAIR_FIXTURE_FAILED {name}: {detail}")


class Capture:
    def __init__(self) -> None:
        self.lines: list = []

    def __call__(self, msg: str, ts=None) -> None:
        self.lines.append(msg)

    def has(self, pattern: str) -> bool:
        return any(re.search(pattern, ln) for ln in self.lines)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def template(mod) -> dict:
    return dict(mod.state)


def ast_deadlock_gate(path: Path, label: str) -> None:
    src = path.read_text()
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id in ("log", "emit_summary",
                                            "capture_android_snapshot")):
                    offenders.append(f"line {sub.lineno}: {sub.func.id}()")
    assert not offenders, f"{label} lock-wrapped emit calls: {offenders}"
    for tok in ("R3_C_DELAY_SHA256", "R3_T4_SHA256", "R3_PANIC_ENTRY_SHA256",
                "NO_LINUX_RESTART=YES", "MACHINE_RESTART_ENTRY_REACHED=PROVEN",
                "TRUE_DEVICE_CONTROL"):
        if label == "RESET8" and tok == "MACHINE_RESTART_ENTRY_REACHED=PROVEN":
            # allowed only in the "must NEVER license" docstring
            if src.count(tok) != 1:
                raise AssertionError(f"{label} unexpected {tok} count {src.count(tok)}")
            continue
        if label == "RESET1" and tok == "MACHINE_RESTART_ENTRY_REACHED=PROVEN":
            continue
        assert tok not in src, f"{label} forbidden token {tok}"
    for tok in ("FASTBOOT_BOOT_ONLY", "SECOND_BOOT_FORBIDDEN",
                "RESET_PAIR_DEVICE_EXECUTION_SPLIT",
                "RESET_CALLER_IDENTITY=NOT_PROVEN",
                "ORIGINAL_MACHINE_RESTART_BODY_EXECUTED=NOT_PROVEN",
                "DO_KERNEL_RESTART_EXECUTED=NOT_PROVEN",
                "PSCI_SYS_RESET_EXECUTED=NOT_PROVEN",
                "NO_LINUX_RESTART=NOT_LICENSED"):
        assert tok in src, f"{label} missing {tok}"


def identity_cases(mod, label: str, lines: list, sibling_name: str,
                   accept_sha: str) -> None:
    forbidden = dict(mod.FORBIDDEN_SHAS)
    payload = getattr(mod, "EXPECTED_PAYLOAD_SHA", accept_sha)
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, accept_sha, "xyz", forbidden,
                            payload)
    except SystemExit:
        lines.append(f"OBSERVER_{label}_IDENTITY_NON_HEX_SHA_REJECTED=PASS")
    else:
        fail("IDENTITY", f"{label} NON_HEX accepted")
    try:
        mod.verify_identity(mod.EXPECTED_SIZE + 1, accept_sha, accept_sha,
                            forbidden, payload)
    except SystemExit:
        lines.append(f"OBSERVER_{label}_IDENTITY_WRONG_SIZE_REJECTED=PASS")
    else:
        fail("IDENTITY", f"{label} WRONG_SIZE accepted")
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, "ee" * 32, accept_sha,
                            forbidden, payload)
    except SystemExit:
        lines.append(f"OBSERVER_{label}_IDENTITY_WRONG_SHA_REJECTED=PASS")
    else:
        fail("IDENTITY", f"{label} WRONG_SHA accepted")
    mutated = "01" + accept_sha[2:]
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, mutated, accept_sha,
                            forbidden, payload)
    except SystemExit:
        lines.append(f"OBSERVER_{label}_IDENTITY_1BYTE_MUTATED_BOOT_REJECTED=PASS")
    else:
        fail("IDENTITY", f"{label} mutated accepted")
    misboot = dict(forbidden)
    required = ("T0_BOOT", "T1_BOOT", "T2_BOOT", "T3_BOOT", "T4_BOOT",
                "C_DELAY_BOOT", "FIX8_BOOT", "PANIC30_BOOT",
                "PENTRY8_BOOT", "PENTRY1_BOOT")
    for name in required:
        assert name in misboot, f"{label} missing forbidden {name}"
        try:
            mod.verify_identity(mod.EXPECTED_SIZE, misboot[name],
                                misboot[name], misboot, payload)
        except SystemExit as exc:
            assert f"{label}_OBSERVER_MISBOOT_REFUSED" in str(exc), str(exc)
            assert name in str(exc), f"{label} refusal missing {name}"
            lines.append(
                f"OBSERVER_{label}_IDENTITY_{name}_MISBOOT_REFUSED=PASS")
        else:
            fail("IDENTITY", f"{label} {name} accepted")
    assert sibling_name in misboot, f"{label} missing sibling {sibling_name}"
    sib = misboot[sibling_name]
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, sib, sib, misboot, payload)
    except SystemExit as exc:
        assert f"{label}_OBSERVER_MISBOOT_REFUSED" in str(exc), str(exc)
        assert sibling_name in str(exc), str(exc)
        lines.append(f"OBSERVER_{label}_IDENTITY_{sibling_name}_MISBOOT_REFUSED=PASS")
        lines.append(f"OBSERVER_{label}_IDENTITY_PAYLOAD_SWAP_REJECTED=PASS")
    else:
        fail("IDENTITY", f"{label} sibling accepted")
    mod.verify_identity(mod.EXPECTED_SIZE, accept_sha, accept_sha, misboot,
                        payload)
    lines.append(f"OBSERVER_{label}_IDENTITY_EXACT_MATCH_ACCEPTED=PASS")


def scenario(lines, name, fn) -> None:
    try:
        fn()
    except Exception as exc:
        fail(name, repr(exc))
    lines.append(f"OBSERVER_RESET_PAIR_{name}_CASE=PASS")


def main() -> list:
    lines: list = []
    os.environ["R3_RESET8_TOTAL"] = f"{RESET8_FIXTURE_TOTAL:.3f}"
    os.environ["R3_RESET8_SHA256"] = GOOD_SHA
    os.environ["R3_RESET1_SHA256"] = GOOD_SHA2
    os.environ.pop("R3_RESET8_FORBIDDEN_SHAS", None)
    os.environ.pop("R3_RESET1_FORBIDDEN_SHAS", None)

    ast_deadlock_gate(OBS8, "RESET8")
    ast_deadlock_gate(OBS1, "RESET1")
    lines.append("OBSERVER_RESET8_AST_DEADLOCK_GATE=PASS")
    lines.append("OBSERVER_RESET1_AST_DEADLOCK_GATE=PASS")

    mod8 = load(OBS8, "reset8_obs")
    mod1 = load(OBS1, "reset1_obs")
    assert mod8.EXPECTED_SIZE == 37380096
    assert mod1.EXPECTED_SIZE == 37380096
    assert mod1.RESET_PAIR_EXPECTED_DELTA_S == -7.000
    assert mod1.PAIR_STRONG_TOL_S == 1.000
    assert mod1.PAIR_SUPPORTED_TOL_S == 2.000
    assert abs(mod1.RESET8_TOTAL_S - RESET8_FIXTURE_TOTAL) < 1e-9
    lines.append("OBSERVER_RESET_PAIR_DECODER_CONSTANTS=PASS")

    identity_cases(mod8, "RESET8", lines, "RESET1_BOOT", GOOD_SHA)
    identity_cases(mod1, "RESET1", lines, "RESET8_BOOT", GOOD_SHA2)
    lines.append("RESET8_OBSERVER_FULL_SHA_GATE=PASS")
    lines.append("RESET1_OBSERVER_FULL_SHA_GATE=PASS")

    def s_reset8_accept():
        st = template(mod8)
        st.update({"t_booting_okay": 1001.0, "kernel_start": 1001.0 + 26.0,
                   "t_boot_completed": 1040.0, "slot_suffix": "_a"})
        cap = Capture()
        mod8.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=True, st=st)
        assert cap.has(r"SUMMARY RESET8_TOTAL=26\.000"), cap.lines
        assert cap.has(r"SUMMARY RESET8_MEMBER_A_COMPLETED=YES")
        assert cap.has(r"SUMMARY MACHINE_RESTART_ENTRY_REACHED=NOT_PROVEN")
        assert cap.has(r"SUMMARY ABSOLUTE_TIMING=SECONDARY_ONLY")
        assert cap.has(r"SUMMARY FASTBOOT_BOOT_ONLY=YES")
        assert cap.has(r"SUMMARY SECOND_BOOT_FORBIDDEN=YES")
        assert cap.has(r"SUMMARY RESET1_DEVICE_AUTHORIZED=NO")
        assert not cap.has(r"MACHINE_RESTART_ENTRY_REACHED=PROVEN")
        assert cap.has(r"NO_LINUX_RESTART=NOT_LICENSED")

    def s_reset8_manual():
        st = template(mod8)
        st.update({"t_booting_okay": 1001.0, "no_return_window_expired": True})
        cap = Capture()
        mod8.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=False, st=st)
        assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
        assert cap.has(r"SUMMARY RESET8_MEMBER_A_COMPLETED=NO")
        assert cap.has(r"MANUAL_RECOVERY_TIMING_NOT_PROOF=YES")
        assert cap.has(r"SUMMARY MACHINE_RESTART_ENTRY_REACHED=NOT_PROVEN")

    def s_reset1_strong():
        exact = RESET8_FIXTURE_TOTAL - 7.000
        st = template(mod1)
        st.update({"t_booting_okay": 1001.0, "kernel_start": 1001.0 + exact,
                   "t_boot_completed": 1030.0, "slot_suffix": "_a"})
        cap = Capture()
        mod1.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=True, st=st)
        assert cap.has(r"SUMMARY RESET1_TOTAL=19\.000"), cap.lines
        assert cap.has(r"SUMMARY RESET_PAIR_DELTA=-7\.000")
        assert cap.has(r"SUMMARY RESET_PAIR_ERROR=0\.000")
        assert cap.has(r"SUMMARY RESET_PAIR_SIGNATURE=STRONG "
                       r"case=RESET1_PAIR_A_STRONG")
        assert cap.has(r"SUMMARY MACHINE_RESTART_ENTRY_REACHED=PROVEN")
        assert cap.has(r"SUMMARY RESET_CALLER_IDENTITY=NOT_PROVEN")
        assert cap.has(r"SUMMARY ORIGINAL_MACHINE_RESTART_BODY_EXECUTED=NOT_PROVEN")
        assert cap.has(r"SUMMARY DO_KERNEL_RESTART_EXECUTED=NOT_PROVEN")
        assert cap.has(r"SUMMARY PSCI_SYS_RESET_EXECUTED=NOT_PROVEN")
        assert cap.has(r"SUMMARY ABSOLUTE_TIMING=SECONDARY_ONLY")
        assert cap.has(rf"SUMMARY RESET1_NEXT_STEP={re.escape(PROVEN)}")

    def s_reset1_supported():
        st = template(mod1)
        st.update({"t_booting_okay": 1001.0,
                   "kernel_start": 1001.0 + (RESET8_FIXTURE_TOTAL - 5.200),
                   "t_boot_completed": 1041.0, "slot_suffix": "_a"})
        cap = Capture()
        mod1.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=True, st=st)
        assert cap.has(r"SUMMARY RESET_PAIR_SIGNATURE=SUPPORTED "
                       r"case=RESET1_PAIR_B_SUPPORTED")
        assert cap.has(r"SUMMARY MACHINE_RESTART_ENTRY_REACHED=STRONGLY_SUPPORTED")
        assert cap.has(r"SUMMARY RESET_CALLER_IDENTITY=NOT_PROVEN")

    def s_reset1_no_shift():
        st = template(mod1)
        st.update({"t_booting_okay": 1001.0,
                   "kernel_start": 1001.0 + RESET8_FIXTURE_TOTAL,
                   "t_boot_completed": 1041.0, "slot_suffix": "_a"})
        cap = Capture()
        mod1.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=True, st=st)
        assert cap.has(r"case=RESET1_PAIR_C_NO_SHIFT")
        assert cap.has(r"SUMMARY RESTART_CHOKE_DELAY_CONTROL_NOT_REFLECTED=YES")
        assert cap.has(r"SUMMARY MACHINE_RESTART_ENTRY_REACHED=NOT_PROVEN")
        assert cap.has(r"NO_LINUX_RESTART=NOT_LICENSED")
        assert cap.has(rf"SUMMARY RESET1_NEXT_STEP={re.escape(WD)}")

    def s_reset1_manual():
        st = template(mod1)
        st.update({"t_booting_okay": 1001.0, "no_return_window_expired": True})
        cap = Capture()
        mod1.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=False, st=st)
        assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
        assert cap.has(r"MANUAL_RECOVERY_ELAPSED_EXCLUDED_FROM_TIMING=YES")
        assert cap.has(r"SUMMARY MACHINE_RESTART_ENTRY_REACHED=NOT_PROVEN")
        assert cap.has(rf"SUMMARY RESET1_NEXT_STEP={re.escape(ISO)}")

    def s_reset1_boot_reject():
        st = template(mod1)
        st.update({"t_command_start": 1000.0, "boot_not_accepted": True})
        cap = Capture()
        mod1.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=False, st=st)
        assert cap.has(r"SUMMARY RECOVERY_KIND=BOOT_NOT_ACCEPTED")
        assert cap.has(r"RESET1_BOOT_NOT_ACCEPTED")
        assert cap.has(r"RESET_PAIR_DELTA=NA")

    def s_zero():
        cap = Capture()
        mod8.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                          final_adb=False, st=template(mod8))
        assert cap.has(r"SUMMARY T_COMMAND_START=NA")
        assert cap.has(r"SUMMARY RESET8_TOTAL=NA")
        cap1 = Capture()
        mod1.emit_summary(emit=cap1, final_usb="NONE", final_fastboot=False,
                          final_adb=False, st=template(mod1))
        assert cap1.has(r"SUMMARY RESET1_TOTAL=NA")
        assert cap1.has(r"SUMMARY RESET_PAIR_DELTA=NA")

    scenario(lines, "RESET8_ACCEPT", s_reset8_accept)
    scenario(lines, "RESET8_MANUAL_NOT_PROOF", s_reset8_manual)
    scenario(lines, "RESET1_PAIR_A_STRONG", s_reset1_strong)
    scenario(lines, "RESET1_PAIR_B_SUPPORTED", s_reset1_supported)
    scenario(lines, "RESET1_PAIR_C_NO_SHIFT", s_reset1_no_shift)
    scenario(lines, "RESET1_MANUAL_NOT_PROOF", s_reset1_manual)
    scenario(lines, "RESET1_BOOT_NOT_ACCEPTED", s_reset1_boot_reject)
    scenario(lines, "ZERO_EVENT_SUMMARY", s_zero)
    lines.append("RESET_PAIR_OBSERVER_FIXTURES=PASS")
    lines.append("OBSERVER_RESET_PAIR_SUMMARY_FIXTURE=PASS")
    return lines


if __name__ == "__main__":
    os.environ.setdefault("GITHUB_ACTIONS", "true")
    for ln in main():
        print(ln)
    raise SystemExit(0)
