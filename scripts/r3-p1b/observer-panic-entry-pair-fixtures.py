#!/usr/bin/env python3
"""Observer fixtures for the R3 P1B PANIC_ENTRY-1 delay-pair round.

Drives the PENTRY1 pair observer identity / pair-decoder / summary paths with
synthetic states - no device, no host device interface calls. Guards:
  - lock/log deadlock regression
  - FULL-SHA identity gate + misboot refusal (PANIC_ENTRY-8 / T0 / T1 / T2 /
    T3 / T4 / C_DELAY / FIX8 / PANIC30 / old INIT8 / entry-state probe)
  - PAIR-FIRST decoder: PRIMARY = PENTRY1_TOTAL - 26.829s vs expected
    -7.000s, STRONG +/-1.000s, SUPPORTED +/-2.000s; absolute < 20.000s is
    SECONDARY only; natural 23-28s with no shift is
    PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED (never NO_LINUX_PANIC)
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-p1b-panic-entry-pair.py"

PROVEN = "MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_PROVEN"
ISO = "MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_FAILURE_ISOLATION_CI"
ALT = "MAINLINE_V2_R3_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI"

# The PENTRY1 boot SHA gate value is supplied by the private run; fixtures use
# a synthetic accepted digest and the real refusal list.
GOOD_SHA = "ab" * 32


def load_observer():
    spec = importlib.util.spec_from_file_location("pentry1_pair_observer",
                                                  OBSERVER)
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
    raise SystemExit(f"OBSERVER_PANIC_ENTRY1_FIXTURE_FAILED {name}: {detail}")


def scenario(lines: list, name: str, fn) -> None:
    try:
        fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    except SystemExit as exc:
        fail(name, f"unexpected SystemExit: {exc}")
    lines.append(f"OBSERVER_PANIC_ENTRY1_{name}_CASE=PASS")


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
                "R3_PANIC_ENTRY_SHA256", "R3_PANIC_ENTRY_BOOT_IMG",
                "R3_PANIC_ENTRY_SELECTED_STAGE",
                "C_DELAY_NOT_REACHED_LICENSE=YES",
                "T3_NOT_REACHED_LICENSE=YES",
                "MAINLINE_V2_R3_P1B_C_DELAY_FAILURE_ISOLATION_CI",
                "C_DELAY_OBSERVER_MISBOOT_REFUSED",
                "NO_LINUX_PANIC=YES", "PANIC_NOT_REACHED=YES",
                "PENTRY_A_STRONG", "PENTRY_B_SUPPORTED"):
        assert tok not in src, f"forbidden token in PENTRY1 observer: {tok}"
    for tok in ("R3_PANIC_ENTRY1_SHA256", "R3_PANIC_ENTRY1_PAYLOAD_SHA256",
                "R3_PANIC_ENTRY1_BOOT_IMG", "R3_PANIC_ENTRY1_SELECTED_STAGE",
                "PANIC_ENTRY_OBSERVER_MISBOOT_REFUSED",
                "PANIC_ENTRY1_NOT_REACHED_LICENSE=NO",
                "MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_PROVEN",
                "MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_FAILURE_ISOLATION_CI",
                "MAINLINE_V2_R3_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI",
                "FASTBOOT_BOOT_ONLY", "SECOND_BOOT_FORBIDDEN",
                "PANIC_ENTRY1_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
                "PANIC_ENTRY1_DIAGNOSTIC_ONLY=YES",
                "PENTRY8_REFERENCE_TOTAL", "PENTRY1_PAIR_EXPECTED_DELTA",
                "PENTRY1_PAIR_DELTA", "PENTRY1_PAIR_TOLERANCE_STRONG",
                "PANIC_ENTRY1_ABSOLUTE_EARLY_SECONDARY",
                "PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED",
                "PENTRY1_PAIR_C_NO_SHIFT", "PENTRY1_PAIR_A_STRONG",
                "PENTRY1_PAIR_B_SUPPORTED", "PENTRY1_PAIR_TIMING_AMBIGUOUS",
                "PENTRY1_BOOT_NOT_ACCEPTED",
                "PANIC_ENTRY1_REACHED", "LINUX_PANIC_FUNCTION_INVOKED",
                "PANIC_TIMEOUT_BRANCH_REACHED=NOT_PROVEN",
                "NO_LINUX_PANIC=NOT_LICENSED",
                "PANIC_ENTRY_CANONICAL_PANIC",
                "PENTRY8_BOOT", "C_DELAY_BOOT", "T4_BOOT", "T3_BOOT",
                "R6=NOT_PROVEN", "R7=NOT_PROVEN",
                "AUTOMATIC_ANDROID_RETURN",
                "PANIC_ENTRY_CHECKPOINT_ONLY",
                "PENTRY1_DELAY_SECONDS"):
        assert tok in src, f"required token missing in PENTRY1 observer: {tok}"


def decoder_constants(mod, lines) -> None:
    assert mod.PENTRY8_TOTAL_S == 26.829
    assert mod.PENTRY8_DELAY_S == 8.0
    assert mod.PENTRY1_DELAY_S == 1.0
    assert mod.PENTRY_PAIR_EXPECTED_DELTA_S == -7.000
    assert mod.PAIR_STRONG_TOL_S == 1.000
    assert mod.PAIR_SUPPORTED_TOL_S == 2.000
    assert mod.C_DELAY_REFERENCE_TOTAL_S == 14.464
    assert mod.PANIC_ENTRY_EARLY_RETURN_CLASS_LIMIT_S == 20.0
    assert mod.PANIC_ENTRY_NATURAL_LO_S == 23.0
    assert mod.PANIC_ENTRY_NATURAL_HI_S == 28.0
    assert mod.EXPECTED_SIZE == 37380096
    assert abs(mod.panic_entry_pair_delta(19.829) + 7.0) < 1e-9
    assert mod.panic_entry_pair_delta(None) is None
    names = ("PENTRY8_BOOT", "T0_BOOT", "T1_BOOT", "T2_BOOT", "T3_BOOT",
             "FIX8_BOOT", "PANIC30_BOOT", "OLD_INIT8_BOOT",
             "ENTRY_STATE_PROBE_BOOT", "T4_BOOT", "C_DELAY_BOOT")
    assert tuple(mod.FORBIDDEN_SHAS) == names, tuple(mod.FORBIDDEN_SHAS)
    assert mod.FORBIDDEN_SHAS["PENTRY8_BOOT"] == (
        "5e92af2f90b86b875f646c451b573044906afe65dfe4a1786b00e1f8a451ecfe")
    assert mod.FORBIDDEN_SHAS["C_DELAY_BOOT"] == (
        "d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02")
    lines.append("OBSERVER_PANIC_ENTRY1_DECODER_CONSTANTS=PASS")


def identity_fixtures(lines):
    mod = OBS
    forbidden = mod.FORBIDDEN_SHAS
    for name, args in [
            ("NON_HEX_SHA", (mod.EXPECTED_SIZE, GOOD_SHA, "xyz", forbidden,
                             mod.EXPECTED_PAYLOAD_SHA)),
            ("WRONG_SIZE", (mod.EXPECTED_SIZE + 1, GOOD_SHA, GOOD_SHA,
                            forbidden, mod.EXPECTED_PAYLOAD_SHA)),
            ("WRONG_SHA", (mod.EXPECTED_SIZE, "cd" * 32, GOOD_SHA, forbidden,
                           mod.EXPECTED_PAYLOAD_SHA))]:
        try:
            mod.verify_identity(*args)
        except SystemExit:
            lines.append(f"OBSERVER_PANIC_ENTRY1_IDENTITY_{name}_REJECTED=PASS")
            continue
        fail("IDENTITY", f"{name} accepted")
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
                f"OBSERVER_PANIC_ENTRY1_IDENTITY_{name}_MISBOOT_REFUSED=PASS")
        else:
            fail("IDENTITY", f"{name} misboot accepted")
    mod.verify_identity(mod.EXPECTED_SIZE, GOOD_SHA, GOOD_SHA, misboot,
                        mod.EXPECTED_PAYLOAD_SHA)
    lines.append("OBSERVER_PANIC_ENTRY1_IDENTITY_EXACT_MATCH_ACCEPTED=PASS")


def pair_decoder_fixtures(lines):
    mod = OBS
    a = "AUTOMATIC_ANDROID_RETURN"
    exact = mod.PENTRY8_TOTAL_S + mod.PENTRY_PAIR_EXPECTED_DELTA_S  # 19.829
    v = mod.panic_entry_reachability(exact, a)
    assert v["verdict"] == "STRONG" and v["stage"] == "PROVEN", v
    assert v["case"] == "PENTRY1_PAIR_A_STRONG" and v["next"] == PROVEN, v
    assert abs(v["pair_delta"] + 7.0) < 1e-9 and abs(v["pair_error"]) < 1e-9, v
    v = mod.panic_entry_reachability(exact - 1.0, a)
    assert v["verdict"] == "STRONG", v
    v = mod.panic_entry_reachability(exact + 1.0, a)
    assert v["verdict"] == "STRONG", v
    v = mod.panic_entry_reachability(exact - 1.9, a)
    assert v["verdict"] == "SUPPORTED" and v["next"] == PROVEN, v
    assert v["case"] == "PENTRY1_PAIR_B_SUPPORTED", v
    v = mod.panic_entry_reachability(exact + 1.9, a)
    assert v["verdict"] == "SUPPORTED", v
    # PENTRY8's own total must never read as a shift
    v = mod.panic_entry_reachability(mod.PENTRY8_TOTAL_S, a)
    assert v["verdict"] == "NOT_OBSERVED", v
    assert v["case"] == "PENTRY1_PAIR_C_NO_SHIFT", v
    assert v["next"] == ALT, v
    for t in (23.0, mod.FIX8_TOTAL_S, mod.PANIC30_TOTAL_S, 27.999):
        v = mod.panic_entry_reachability(t, a)
        assert v["case"] == "PENTRY1_PAIR_C_NO_SHIFT", (t, v)
    for t in (22.0, 29.0):
        v = mod.panic_entry_reachability(t, a)
        assert v["case"] == "PENTRY1_PAIR_TIMING_AMBIGUOUS", (t, v)
        assert v["next"] == ISO, (t, v)
    v = mod.panic_entry_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "PENTRY1_STABLE_FASTBOOT", v
    v = mod.panic_entry_reachability(None, "MANUAL_RECOVERY_OR_NO_RETURN")
    assert v["case"] == "PENTRY1_NO_RETURN", v
    v = mod.panic_entry_reachability(None, "BOOT_NOT_ACCEPTED")
    assert v["case"] == "PENTRY1_BOOT_NOT_ACCEPTED", v
    # absolute <20s is SECONDARY: 14.464s (C_DELAY-like) is NOT a pair shift
    v = mod.panic_entry_reachability(14.464, a)
    assert v["verdict"] == "NOT_OBSERVED", v
    assert v["case"] == "PENTRY1_PAIR_TIMING_AMBIGUOUS", v
    lines.append("OBSERVER_PANIC_ENTRY1_PAIR_DECODER_CASES=PASS")


def s1_zero_event_summary():
    mod = OBS
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=template(mod))
    for key in ("T_COMMAND_START", "T_SENDING_OKAY", "T_BOOTING_OKAY",
                "T_FASTBOOT_DISAPPEAR", "T_ADB_FIRST_SEEN", "T_BOOT_COMPLETED",
                "RETURNED_ANDROID_KERNEL_START"):
        assert cap.has(rf"SUMMARY {key}=NA"), f"missing {key}"
    assert cap.has(r"SUMMARY PANIC_ENTRY1_TOTAL=NA")
    assert cap.has(r"SUMMARY PENTRY1_PAIR_DELTA=NA")
    assert cap.has(r"PANIC_ENTRY1_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"NO_LINUX_PANIC=NOT_LICENSED")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(ISO)}")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"PENTRY1_DELAY_SECONDS=1")
    assert cap.has(rf"SUMMARY PENTRY8_REFERENCE_TOTAL=26\.829")
    assert cap.has(rf"SUMMARY PENTRY1_PAIR_EXPECTED_DELTA=-7\.000")
    assert not cap.has(r"NO_LINUX_PANIC=YES")
    return cap


def s2_pair_a_strong():
    mod = OBS
    total = 19.829
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_sending_okay": 1000.5,
               "t_booting_okay": 1001.0, "t_disappear": 1002.0,
               "t_adb_first_seen": 1005.0, "t_boot_completed": 1030.0,
               "kernel_host_before": 1020.829, "kernel_uptime": 0.0,
               "kernel_start": 1001.0 + total, "slot_suffix": "_a"})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"SUMMARY PANIC_ENTRY1_TOTAL=19\.829")
    assert cap.has(r"SUMMARY PENTRY1_PAIR_DELTA=-7\.000")
    assert cap.has(r"SUMMARY PENTRY1_PAIR_ERROR=0\.000")
    assert cap.has(r"SUMMARY PANIC_ENTRY1_ABSOLUTE_EARLY_SECONDARY=YES")
    assert cap.has(r"SUMMARY PANIC_ENTRY1_DELAY_PAIR_SIGNATURE=STRONG "
                   r"case=PENTRY1_PAIR_A_STRONG")
    assert cap.has(r"SUMMARY PANIC_ENTRY1_REACHED=PROVEN")
    assert cap.has(r"SUMMARY LINUX_PANIC_FUNCTION_INVOKED=PROVEN")
    assert cap.has(r"SUMMARY PANIC_ENTRY1_DELAY_PAIR_SIGNATURE=STRONG")
    assert cap.has(r"SUMMARY PANIC_TIMEOUT_BRANCH_REACHED=NOT_PROVEN")
    assert cap.has(r"SUMMARY PANIC30_SHOULD_HAVE_SHIFTED=NOT_LICENSED")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(PROVEN)}")
    assert cap.has(r"PANIC_ENTRY1_NOT_REACHED_LICENSE=NO")
    assert not cap.has(r"NO_LINUX_PANIC=YES")
    return cap


def s3_pair_b_supported():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1001.0 + 21.629,
               "t_boot_completed": 1041.0, "slot_suffix": "_a"})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"SUMMARY PANIC_ENTRY1_TOTAL=21\.629")
    assert cap.has(r"SUMMARY PENTRY1_PAIR_DELTA=-5\.200")
    assert cap.has(r"SUMMARY PANIC_ENTRY1_DELAY_PAIR_SIGNATURE=SUPPORTED "
                   r"case=PENTRY1_PAIR_B_SUPPORTED")
    assert cap.has(r"SUMMARY PANIC_ENTRY1_REACHED=STRONGLY_SUPPORTED")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(PROVEN)}")
    assert cap.has(r"PANIC_ENTRY1_NOT_REACHED_LICENSE=NO")
    return cap


def s4_pair_c_no_shift():
    mod = OBS
    for total in (23.0, mod.FIX8_TOTAL_S, mod.PANIC30_TOTAL_S,
                  mod.PENTRY8_TOTAL_S):
        st = template(mod)
        st.update({"t_booting_okay": 1001.0, "kernel_start": 1001.0 + total,
                   "t_boot_completed": 1041.0, "slot_suffix": "_a"})
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(r"SUMMARY PANIC_ENTRY1_DELAY_PAIR_SIGNATURE=NOT_OBSERVED "
                       r"case=PENTRY1_PAIR_C_NO_SHIFT"), total
        assert cap.has(r"SUMMARY PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED=YES"), total
        assert cap.has(r"SUMMARY PANIC_ENTRY1_REACHED=NOT_PROVEN"), total
        assert cap.has(r"PANIC_ENTRY1_NOT_REACHED_LICENSE=NO"), total
        assert cap.has(r"NO_LINUX_PANIC=NOT_LICENSED"), total
        assert not cap.has(r"NO_LINUX_PANIC=YES"), total
        assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(ALT)}"), total
        assert cap.has(r"PANIC_ENTRY1_PAIR_NOTE="
                       r"NATURAL_BAND_NO_SHIFT_ALTERNATIVE_RESET_NEXT"), total


def s5_ambiguous():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1001.0 + 22.0,
               "t_boot_completed": 1041.0, "slot_suffix": "_a"})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"PANIC_ENTRY1_PAIR_TIMING_AMBIGUOUS")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(ISO)}")
    assert not cap.has(r"NO_LINUX_PANIC=YES")


def s6_stable_fastboot():
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
    assert cap.has(r"PENTRY1_STABLE_FASTBOOT")
    assert cap.has(r"PANIC_ENTRY1_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(ISO)}")


def s7_no_return():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "no_return_window_expired": True})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
    assert cap.has(r"PANIC_ENTRY_NO_RETURN_CASE_F=YES")
    assert cap.has(r"PENTRY1_NO_RETURN")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(ISO)}")


def s8_boot_not_accepted():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "boot_not_accepted": True})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY RECOVERY_KIND=BOOT_NOT_ACCEPTED")
    assert cap.has(r"PENTRY1_BOOT_NOT_ACCEPTED")
    assert cap.has(r"PENTRY1_PAIR_DELTA=NA")
    assert cap.has(r"PANIC_ENTRY1_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY PANIC_ENTRY1_NEXT_STEP={re.escape(ISO)}")
    assert not cap.has(r"NO_LINUX_PANIC=YES")


OBS = None


def main() -> list:
    global OBS
    lines: list = []
    try:
        ast_deadlock_gate()
        lines.append("OBSERVER_PANIC_ENTRY1_AST_DEADLOCK_GATE=PASS")
        mod = load_observer()
        for attr in ("emit_summary", "panic_entry_total",
                     "panic_entry_reachability", "panic_entry_pair_delta",
                     "panic_entry_programmed_estimate", "panic_entry_minus_c_delay",
                     "EXPECTED_PAYLOAD_SHA", "selected_stage",
                     "PENTRY8_TOTAL_S", "PENTRY_PAIR_EXPECTED_DELTA_S",
                     "PAIR_STRONG_TOL_S", "PAIR_SUPPORTED_TOL_S"):
            if not hasattr(mod, attr):
                fail("LOAD", f"observer lacks {attr}")
        if not hasattr(mod, "verify_identity"):
            fail("LOAD", "observer lacks verify_identity")
        OBS = mod
        decoder_constants(mod, lines)
        identity_fixtures(lines)
        pair_decoder_fixtures(lines)
        scenario(lines, "ZERO_EVENT_SUMMARY", s1_zero_event_summary)
        scenario(lines, "PAIR_A_STRONG", s2_pair_a_strong)
        scenario(lines, "PAIR_B_SUPPORTED", s3_pair_b_supported)
        scenario(lines, "PAIR_C_NO_SHIFT", s4_pair_c_no_shift)
        scenario(lines, "AMBIGUOUS", s5_ambiguous)
        scenario(lines, "STABLE_FASTBOOT", s6_stable_fastboot)
        scenario(lines, "NO_RETURN", s7_no_return)
        scenario(lines, "BOOT_NOT_ACCEPTED", s8_boot_not_accepted)
        lines.append("OBSERVER_PANIC_ENTRY1_KEYERROR_GUARDED=YES")
        lines.append("OBSERVER_PANIC_ENTRY1_SUMMARY_FIXTURE=PASS")
    except SystemExit:
        raise
    except Exception as exc:
        fail("UNEXPECTED", repr(exc))
    return lines


if __name__ == "__main__":
    for ln in main():
        print(ln)
    raise SystemExit(0)
