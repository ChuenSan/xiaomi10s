#!/usr/bin/env python3
"""Observer fixtures for the R3 P1B PANIC_ENTRY-8 panic() ENTRY round.

Drives the PANIC_ENTRY observer identity/decoder/summary paths with synthetic
states - no device, no fastboot/adb calls. Guards:
  - lock/log deadlock regression
  - FULL-SHA identity gate + misboot refusal (T0 / T1 / T2 / T3 / T4 /
    C_DELAY / FIX8 / PANIC30 / old INIT8 / entry-state probe)
  - distinctive-early decoder: STRONG = auto-return AND TOTAL < 20s;
    VERY_STRONG_MATCHED subclass -0.5..+3.0 vs C_DELAY 14.464s is auxiliary;
    >3s but <20s stays STRONG; SUPPORTED = 20..23; natural 23-26 =
    PANIC_ENTRY_SIGNATURE_NOT_OBSERVED (never NO_LINUX_PANIC)
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-p1b-panic-entry.py"

NEXT_OK = "WAIT_FOR_USER_APPROVAL"
ISO = "MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI"


def load_observer():
    spec = importlib.util.spec_from_file_location("panic_entry_observer", OBSERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Capture:
    def __init__(self) -> None:
        self.lines: list = []

    def __call__(self, msg: str, ts=None) -> None:
        self.lines.append(msg)

    def has(self, pattern: str) -> bool:
        return any(re.search(pattern, ln) for ln in self.lines)


def template(mod) -> dict:
    return dict(mod.state)


def fail(name: str, detail: str) -> None:
    raise SystemExit(f"OBSERVER_PANIC_ENTRY_FIXTURE_FAILED {name}: {detail}")


def scenario(lines: list, name: str, fn) -> None:
    try:
        fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    except SystemExit as exc:
        fail(name, f"unexpected SystemExit: {exc}")
    lines.append(f"OBSERVER_PANIC_ENTRY_{name}_CASE=PASS")


def ast_deadlock_gate() -> None:
    src = OBSERVER.read_text()
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
    assert not offenders, f"lock-wrapped emit calls: {offenders}"
    for tok in ("R3_C_DELAY_SHA256", "R3_T4_SHA256", "R3_T3_SHA256",
                "C_DELAY_NOT_REACHED_LICENSE=YES",
                "T3_NOT_REACHED_LICENSE=YES",
                "MAINLINE_V2_R3_P1B_C_DELAY_FAILURE_ISOLATION_CI",
                "C_DELAY_OBSERVER_MISBOOT_REFUSED",
                "NO_LINUX_PANIC=YES", "PANIC_NOT_REACHED=YES"):
        assert tok not in src, f"forbidden token in PANIC_ENTRY observer: {tok}"
    for tok in ("R3_PANIC_ENTRY_SHA256", "R3_PANIC_ENTRY_PAYLOAD_SHA256",
                "R3_PANIC_ENTRY_BOOT_IMG", "R3_PANIC_ENTRY_SELECTED_STAGE",
                "PANIC_ENTRY_OBSERVER_MISBOOT_REFUSED",
                "PANIC_ENTRY_NOT_REACHED_LICENSE=NO",
                "MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI",
                "WAIT_FOR_USER_APPROVAL",
                "FASTBOOT_BOOT_ONLY", "SECOND_BOOT_FORBIDDEN",
                "PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
                "PANIC_ENTRY_DIAGNOSTIC_ONLY=YES",
                "PANIC_ENTRY_MINUS_C_DELAY", "C_DELAY_REFERENCE_TOTAL",
                "PANIC_ENTRY_PROGRAMMED_ESTIMATE",
                "E2_EARLY_MAINLINE_BOOT=NOT_PROVEN",
                "PANIC_ENTRY_REACHED", "LINUX_PANIC_FUNCTION_INVOKED",
                "PANIC_TIMEOUT_BRANCH_REACHED=NOT_PROVEN",
                "NO_LINUX_PANIC=NOT_LICENSED",
                "PANIC_ENTRY_CANONICAL_PANIC",
                "C_DELAY_BOOT", "T4_BOOT", "T3_BOOT",
                "R6=NOT_PROVEN", "R7=NOT_PROVEN",
                "AUTOMATIC_ANDROID_RETURN",
                "PANIC_ENTRY_CHECKPOINT_ONLY"):
        assert tok in src, f"required token missing in PANIC_ENTRY observer: {tok}"


def decoder_constants(mod, lines) -> None:
    assert mod.C_DELAY_REFERENCE_TOTAL_S == 14.464
    assert mod.T4_REFERENCE_TOTAL_S == 14.385
    assert mod.T3_REFERENCE_TOTAL_S == 14.238
    assert mod.T2_REFERENCE_TOTAL_S == 14.240
    assert mod.T1_REFERENCE_TOTAL_S == 14.238
    assert mod.T0_REFERENCE_TOTAL_S == 14.252
    assert mod.PANIC_ENTRY_EARLY_RETURN_CLASS_LIMIT_S == 20.0
    assert mod.PANIC_ENTRY_MATCHED_MINUS_C_DELAY_LO_S == -0.5
    assert mod.PANIC_ENTRY_MATCHED_MINUS_C_DELAY_HI_S == 3.0
    assert mod.PANIC_ENTRY_SUPPORTED_LO_S == 20.0
    assert mod.PANIC_ENTRY_SUPPORTED_HI_S == 23.0
    assert mod.PANIC_ENTRY_NATURAL_LO_S == 23.0
    assert mod.PANIC_ENTRY_NATURAL_HI_S == 28.0
    assert mod.P0_REF_OVERHEAD_S == 6.1445
    assert mod.PANIC_ENTRY_PROGRAMMED_S == 8.0
    assert mod.EXPECTED_SIZE == 37380096
    assert abs(mod.panic_entry_minus_c_delay(14.464)) < 1e-9
    names = ("T0_BOOT", "T1_BOOT", "T2_BOOT", "T3_BOOT", "FIX8_BOOT",
             "PANIC30_BOOT", "OLD_INIT8_BOOT", "ENTRY_STATE_PROBE_BOOT",
             "T4_BOOT", "C_DELAY_BOOT")
    assert tuple(mod.FORBIDDEN_SHAS) == names, tuple(mod.FORBIDDEN_SHAS)
    assert mod.FORBIDDEN_SHAS["C_DELAY_BOOT"] == (
        "d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02")
    assert mod.FORBIDDEN_SHAS["T4_BOOT"] == (
        "3827fc0fe4216d7d18ccd2a60ea610a6bd10b2afa269e741923ca3bbc566849d")
    lines.append("OBSERVER_PANIC_ENTRY_DECODER_CONSTANTS=PASS")


def identity_fixtures(lines):
    mod = OBS
    forbidden = mod.FORBIDDEN_SHAS
    good_sha = "ab" * 32
    cases = [
        ("NON_HEX_SHA", (mod.EXPECTED_SIZE, good_sha, "xyz", forbidden,
                         mod.EXPECTED_PAYLOAD_SHA)),
        ("WRONG_SIZE", (mod.EXPECTED_SIZE + 1, good_sha, good_sha, forbidden,
                        mod.EXPECTED_PAYLOAD_SHA)),
        ("WRONG_SHA", (mod.EXPECTED_SIZE, "cd" * 32, good_sha, forbidden,
                       mod.EXPECTED_PAYLOAD_SHA)),
    ]
    for name, args in cases:
        try:
            mod.verify_identity(*args)
        except SystemExit:
            lines.append(f"OBSERVER_PANIC_ENTRY_IDENTITY_{name}_REJECTED=PASS")
            continue
        fail("IDENTITY", f"{name} accepted")
    mutated = good_sha[:-1] + ("0" if good_sha[-1] != "0" else "1")
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, mutated, good_sha, forbidden,
                            mod.EXPECTED_PAYLOAD_SHA)
    except SystemExit:
        lines.append("OBSERVER_PANIC_ENTRY_IDENTITY_MUTATED_REJECTED=PASS")
    else:
        fail("IDENTITY", "mutated PANIC_ENTRY accepted")
    misboot = dict(forbidden)
    for name in forbidden:
        try:
            mod.verify_identity(mod.EXPECTED_SIZE, forbidden[name],
                                forbidden[name], misboot,
                                mod.EXPECTED_PAYLOAD_SHA)
        except SystemExit as exc:
            assert "PANIC_ENTRY_OBSERVER_MISBOOT_REFUSED" in str(exc), str(exc)
            assert name in str(exc), f"refusal missing label {name}"
            lines.append(
                f"OBSERVER_PANIC_ENTRY_IDENTITY_{name}_MISBOOT_REFUSED=PASS")
        else:
            fail("IDENTITY", f"{name} misboot accepted")
    mod.verify_identity(mod.EXPECTED_SIZE, good_sha, good_sha, misboot,
                        mod.EXPECTED_PAYLOAD_SHA)
    lines.append("OBSERVER_PANIC_ENTRY_IDENTITY_EXACT_MATCH_ACCEPTED=PASS")


def decoder_fixtures(lines):
    mod = OBS
    v = mod.panic_entry_reachability(14.464, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["stage"] == "PROVEN", v
    assert v["case"] == "PENTRY_A_STRONG" and v["next"] == NEXT_OK, v
    assert v["subclass"] == "VERY_STRONG_MATCHED", v
    v = mod.panic_entry_reachability(16.000, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["subclass"] == "VERY_STRONG_MATCHED", v
    v = mod.panic_entry_reachability(17.464, "AUTOMATIC_ANDROID_RETURN")
    assert abs(mod.panic_entry_minus_c_delay(17.464) - 3.0) < 1e-9
    assert v["verdict"] == "STRONG" and v["subclass"] == "VERY_STRONG_MATCHED", v
    v = mod.panic_entry_reachability(18.500, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["stage"] == "PROVEN", v
    assert v["subclass"] == "DISTINCTIVE_EARLY", v
    v = mod.panic_entry_reachability(19.999, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["subclass"] == "DISTINCTIVE_EARLY", v
    v = mod.panic_entry_reachability(21.000, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "SUPPORTED" and v["stage"] == "STRONGLY_SUPPORTED", v
    assert v["case"] == "PENTRY_B_SUPPORTED" and v["next"] == NEXT_OK, v
    for t, case in (
            (20.0, "PENTRY_B_SUPPORTED"),
            (22.999, "PENTRY_B_SUPPORTED"),
            (23.0, "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED"),
            (mod.FIX8_TOTAL_S, "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED"),
            (mod.PANIC30_TOTAL_S, "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED"),
            (28.0, "UNKNOWN")):
        v = mod.panic_entry_reachability(t, "AUTOMATIC_ANDROID_RETURN")
        if case == "PENTRY_B_SUPPORTED":
            assert v["verdict"] == "SUPPORTED" and v["case"] == case, (t, v)
        else:
            assert v["verdict"] == "NOT_OBSERVED" and v["case"] == case, (t, v)
            assert v["stage"] == "NOT_PROVEN" and v["next"] == ISO, v
    v = mod.panic_entry_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "PANIC_ENTRY_STABLE_FASTBOOT"
    v = mod.panic_entry_reachability(None, "MANUAL_RECOVERY_OR_NO_RETURN")
    assert v["case"] == "PANIC_ENTRY_NO_RETURN"
    v = mod.panic_entry_reachability(None, "UNKNOWN")
    assert v["verdict"] == "NOT_OBSERVED" and v["next"] == ISO, v
    lines.append("OBSERVER_PANIC_ENTRY_DECODER_CONSTANTS=PASS")
    lines.append("OBSERVER_PANIC_ENTRY_DECODER_CASES_A_TO_F=PASS")


def s1_zero_event_summary():
    mod = OBS
    st = template(mod)
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    for key in ("T_COMMAND_START", "T_SENDING_OKAY", "T_BOOTING_OKAY",
                "T_FASTBOOT_DISAPPEAR", "T_ADB_FIRST_SEEN",
                "T_BOOT_COMPLETED", "RETURNED_ANDROID_KERNEL_START"):
        assert cap.has(rf"SUMMARY {key}=NA"), f"missing {key}"
    assert cap.has(r"SUMMARY PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"SUMMARY PANIC_ENTRY_SIGNATURE_NOT_OBSERVED=YES")
    assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"NO_LINUX_PANIC=NOT_LICENSED")
    assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(ISO)}")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY PANIC_ENTRY_DIAGNOSTIC_ONLY=YES")
    assert cap.has(r"PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    assert cap.has(r"SUMMARY PANIC_ENTRY_SELECTED_STAGE=PANIC_ENTRY_CANONICAL_PANIC")
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHED=NOT_PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(r"SUMMARY R6=NOT_PROVEN")
    assert cap.has(r"SUMMARY R7=NOT_PROVEN")
    assert not cap.has(r"PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert not cap.has(r"NO_LINUX_PANIC=YES")
    return cap


def s2_strong_signature():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_sending_okay": 1000.5,
        "t_booting_okay": 1001.0, "t_disappear": 1002.0,
        "t_adb_first_seen": 1013.0, "t_boot_completed": 1041.0,
        "kernel_host_before": 1015.464, "kernel_uptime": 0.0,
        "kernel_start": 1015.464, "slot_suffix": "_a",
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    total = mod.panic_entry_total(1015.464, 1001.0)
    assert abs(total - 14.464) < 1e-9
    assert cap.has(rf"PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START={total:.3f}")
    dcd = mod.panic_entry_minus_c_delay(total)
    assert abs(dcd) < 1e-9
    assert cap.has(rf"SUMMARY PANIC_ENTRY_MINUS_C_DELAY={re.escape(f'{dcd:+.3f}')} ")
    assert cap.has(r"SUMMARY C_DELAY_REFERENCE_TOTAL=14\.464")
    assert cap.has(r"SUMMARY PANIC_ENTRY_EARLY_RETURN_CLASS_MATCH=YES")
    assert cap.has(r"SUMMARY PANIC_ENTRY_MATCHED_SUBCLASS=YES name=VERY_STRONG_MATCHED")
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHABILITY_SIGNATURE=STRONG "
                   r"case=PENTRY_A_STRONG")
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHED=PROVEN")
    assert cap.has(r"SUMMARY LINUX_PANIC_FUNCTION_INVOKED=PROVEN")
    assert cap.has(r"SUMMARY PANIC_TIMEOUT_BRANCH_REACHED=NOT_PROVEN")
    assert cap.has(r"SUMMARY PANIC30_SHOULD_HAVE_SHIFTED=NOT_LICENSED")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(r"SUMMARY R6=NOT_PROVEN")
    assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(NEXT_OK)}")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN")
    assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO")
    assert not cap.has(r"NO_LINUX_PANIC=YES")
    assert not cap.has(r"SUMMARY PANIC_ENTRY_SIGNATURE_NOT_OBSERVED=YES")


def s2b_strong_unmatched_still_strong():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1019.5,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert abs(mod.panic_entry_minus_c_delay(18.5) - 4.036) < 1e-9
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHABILITY_SIGNATURE=STRONG "
                   r"case=PENTRY_A_STRONG subclass=DISTINCTIVE_EARLY")
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHED=PROVEN")
    assert cap.has(r"SUMMARY PANIC_ENTRY_MATCHED_SUBCLASS=NO name=DISTINCTIVE_EARLY")
    assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(NEXT_OK)}")
    assert not cap.has(r"SUMMARY PANIC_ENTRY_SIGNATURE_NOT_OBSERVED=YES")


def s3_supported_signature():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1022.0,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHABILITY_SIGNATURE=SUPPORTED "
                   r"case=PENTRY_B_SUPPORTED")
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHED=STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY LINUX_PANIC_FUNCTION_INVOKED=STRONGLY_SUPPORTED")
    assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(NEXT_OK)}")
    assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO")


def s5_old_auto_return_class_case_c():
    mod = OBS
    for total in (23.0, mod.FIX8_TOTAL_S, mod.PANIC30_TOTAL_S):
        st = template(mod)
        st.update({"t_booting_okay": 1001.0,
                   "kernel_start": 1001.0 + total,
                   "t_boot_completed": 1041.0})
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(r"SUMMARY PANIC_ENTRY_EARLY_RETURN_CLASS_MATCH=NO"), total
        assert cap.has(r"SUMMARY PANIC_ENTRY_REACHABILITY_SIGNATURE=NOT_OBSERVED "
                       r"case=PANIC_ENTRY_SIGNATURE_NOT_OBSERVED"), total
        assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO"), total
        assert cap.has(r"NO_LINUX_PANIC=NOT_LICENSED"), total
        assert not cap.has(r"NO_LINUX_PANIC=YES"), total
        assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(ISO)}"), total


def s6_stable_fastboot_case_e():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "t_disappear": 1002.0, "stable_fastboot": True,
               "t_fastboot_stable": 1005.7})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                     final_adb=False, st=st)
    assert cap.has(r"PANIC_ENTRY_STABLE_FASTBOOT_OBSERVED=YES")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert cap.has(r"SUMMARY PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO")
    v = mod.panic_entry_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "PANIC_ENTRY_STABLE_FASTBOOT"
    assert v["next"] == ISO


def s7_no_return_manual_excluded():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "no_return_window_expired": True})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
    assert cap.has(r"PANIC_ENTRY_NO_RETURN_CASE_F=YES")
    assert cap.has(r"SUMMARY PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(ISO)}")


def s8_timing_without_android_return_insufficient():
    mod = OBS
    st = {"t_booting_okay": 0.0, "kernel_start": 14.464}
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START=14\.464")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY PANIC_ENTRY_REACHABILITY_SIGNATURE=NOT_OBSERVED")
    assert cap.has(r"PANIC_ENTRY_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY PANIC_ENTRY_NEXT_STEP={re.escape(ISO)}")


OBS = None


def main() -> list:
    global OBS
    lines: list = []
    try:
        ast_deadlock_gate()
        lines.append("OBSERVER_PANIC_ENTRY_AST_DEADLOCK_GATE=PASS")
        mod = load_observer()
        for attr in ("emit_summary", "panic_entry_total",
                     "panic_entry_reachability",
                     "panic_entry_minus_c_delay",
                     "panic_entry_programmed_estimate",
                     "EXPECTED_PAYLOAD_SHA", "selected_stage"):
            if not hasattr(mod, attr):
                fail("LOAD", f"observer lacks {attr}")
        if not hasattr(mod, "verify_identity"):
            fail("LOAD", "observer lacks verify_identity")
        OBS = mod
        decoder_constants(mod, lines)
        identity_fixtures(lines)
        decoder_fixtures(lines)
        scenario(lines, "ZERO_EVENT_SUMMARY", s1_zero_event_summary)
        scenario(lines, "STRONG_SIGNATURE", s2_strong_signature)
        scenario(lines, "STRONG_UNMATCHED_STILL_STRONG",
                 s2b_strong_unmatched_still_strong)
        scenario(lines, "SUPPORTED_SIGNATURE", s3_supported_signature)
        scenario(lines, "OLD_AUTO_RETURN_CLASS_CASE_C",
                 s5_old_auto_return_class_case_c)
        scenario(lines, "STABLE_FASTBOOT_CASE_E", s6_stable_fastboot_case_e)
        scenario(lines, "NO_RETURN_MANUAL_EXCLUDED",
                 s7_no_return_manual_excluded)
        scenario(lines, "TIMING_WITHOUT_ANDROID_RETURN_INSUFFICIENT",
                 s8_timing_without_android_return_insufficient)
        lines.append("OBSERVER_PANIC_ENTRY_KEYERROR_GUARDED=YES")
        lines.append("OBSERVER_PANIC_ENTRY_SUMMARY_FIXTURE=PASS")
    except SystemExit:
        raise
    except Exception as exc:
        fail("UNEXPECTED", repr(exc))
    return lines


if __name__ == "__main__":
    for ln in main():
        print(ln)
    raise SystemExit(0)
