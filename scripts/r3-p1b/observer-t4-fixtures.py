#!/usr/bin/env python3
"""Observer fixtures for the R3 P1B T4-8 post-stage C round.

Drives the T4 observer's identity/decoder/summary paths with synthetic
states - no device, no fastboot/adb calls. Guards:
  - lock/log deadlock regression (AST gate: no lock-wrapped log/emit calls)
  - FULL-SHA identity gate + misboot refusal (T0 / T1 / T2 / T3 / FIX8 /
    PANIC30 / old INIT8 / entry-state probe boots refused before any
    fastboot interaction)
  - T4 timing semantics: primary product is
    T4_BOOTING_TO_RETURNED_KERNEL_START decoded against the T3 matched
    control (T3_TOTAL 14.238s; STRONG +-1.5s, SUPPORTED +-3.0s, early class
    < 20s, old class [20,28)s) with the T2 14.240s, T1 14.238s and T0
    14.252s secondary cross-checks (each <= 3.0s); a negative NEVER
    produces T4_NOT_REACHED (T4_NOT_REACHED_LICENSE=NO always) and always
    routes to T4_FAILURE_ISOLATION_CI; STRONG/SUPPORTED next is
    C_DELAY predevice; E2/R6/R7 never auto-upgraded; R5 full body stays
    NOT_PROVEN.
Cases A STRONG / B SUPPORTED / C old auto-return class / D early-return
timing mismatch / E stable fastboot / F no return.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-p1b-t4.py"

C_DELAY = "MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI"
ISO = "MAINLINE_V2_R3_P1B_T4_FAILURE_ISOLATION_CI"


def load_observer():
    spec = importlib.util.spec_from_file_location("t4_observer", OBSERVER)
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
    raise SystemExit(f"OBSERVER_T4_FIXTURE_FAILED {name}: {detail}")


def scenario(lines: list, name: str, fn) -> None:
    try:
        fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    except SystemExit as exc:
        fail(name, f"unexpected SystemExit: {exc}")
    lines.append(f"OBSERVER_T4_{name}_CASE=PASS")


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
    for tok in ("R3_T3_SHA256", "R3_T3_BOOT_IMG", "R3_T3_PAYLOAD_SHA256",
                "R3_T3_FORBIDDEN_SHAS",
                "P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START",
                "INIT24_BASELINE_SAVED", "NEAREST_BUCKET",
                "ALIGNMENT_MATCH", "ALIGNMENT_MISMATCH", "T0_WINDOW",
                "T1_MINUS_T0_IS_PRIMARY", "T4_NOT_REACHED_LICENSE=YES",
                "T3_NOT_REACHED_LICENSE=YES",
                "MAINLINE_V2_R3_P1B_T3_FAILURE_ISOLATION_CI",
                "T3_OBSERVER_MISBOOT_REFUSED"):
        assert tok not in src, f"forbidden token in T4 observer: {tok}"
    for tok in ("R3_T4_SHA256", "R3_T4_PAYLOAD_SHA256", "R3_T4_BOOT_IMG",
                "R3_T4_SELECTED_STAGE",
                "T4_OBSERVER_MISBOOT_REFUSED",
                "T4_NOT_REACHED_LICENSE=NO",
                "MAINLINE_V2_R3_P1B_T4_FAILURE_ISOLATION_CI",
                "MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI",
                "FASTBOOT_BOOT_ONLY", "SECOND_BOOT_FORBIDDEN",
                "T4_NORMAL_KERNEL_BOOT_CANDIDATE=NO", "T4_DIAGNOSTIC_ONLY=YES",
                "T4_MINUS_T3", "T4_MINUS_T2", "T4_MINUS_T1", "T4_MINUS_T0",
                "T3_REFERENCE_TOTAL", "T2_REFERENCE_TOTAL",
                "T1_REFERENCE_TOTAL", "T0_REFERENCE_TOTAL",
                "T4_PROGRAMMED_ESTIMATE",
                "E2_EARLY_MAINLINE_BOOT=NOT_PROVEN",
                "C6_PARSE_ARGS_COMPLETE_REACHED",
                "NORMAL_START_KERNEL_BODY_TO_C6_EXECUTED",
                "PANIC_PARAMETER_PARSED_BY_RUNNING_KERNEL",
                "RDINIT_PARAMETER_PARSED_BY_RUNNING_KERNEL",
                "SETUP_ARCH_RETURN_REACHED",
                "PARSE_EARLY_PARAM_COMPLETE",
                "C6_PARSE_ARGS_COMPLETE", "C3_SETUP_ARCH_RETURN",
                "ENTRY_STATE_PROBE_BOOT", "T1_BOOT", "T2_BOOT", "T3_BOOT",
                "R5_NORMAL_START_KERNEL_BODY=", "R6=NOT_PROVEN",
                "R7=NOT_PROVEN", "AUTOMATIC_ANDROID_RETURN"):
        assert tok in src, f"required token missing in T4 observer: {tok}"


def decoder_constants(mod, lines) -> None:
    assert mod.T3_REFERENCE_TOTAL_S == 14.238
    assert mod.T2_REFERENCE_TOTAL_S == 14.240
    assert mod.T1_REFERENCE_TOTAL_S == 14.238
    assert mod.T0_REFERENCE_TOTAL_S == 14.252
    assert mod.T4_STRONG_HALF_WINDOW_S == 1.5
    assert mod.T4_SUPPORTED_HALF_WINDOW_S == 3.0
    assert mod.T4_CROSSCHECK_HALF_WINDOW_S == 3.0
    assert mod.T4_EARLY_RETURN_CLASS_LIMIT_S == 20.0
    assert mod.T4_CASE_C_BAND_S == (20.0, 28.0)
    assert mod.P0_REF_OVERHEAD_S == 6.1445
    assert mod.T4_PROGRAMMED_S == 8.0
    assert mod.EXPECTED_SIZE == 37380096
    assert abs(mod.t4_minus_t3(14.238)) < 1e-9
    assert abs(mod.t4_programmed_estimate(14.238) - 8.0935) < 1e-9
    names = ("T0_BOOT", "T1_BOOT", "T2_BOOT", "T3_BOOT", "FIX8_BOOT",
             "PANIC30_BOOT", "OLD_INIT8_BOOT", "ENTRY_STATE_PROBE_BOOT")
    assert tuple(mod.FORBIDDEN_SHAS) == names, tuple(mod.FORBIDDEN_SHAS)
    assert mod.FORBIDDEN_SHAS["T0_BOOT"] == \
        "8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1"
    assert mod.FORBIDDEN_SHAS["T1_BOOT"] == \
        "a4fa083f289219facb0a69062749dd6a9d2f667c4aa044b25b78c36b0da7e3df"
    assert mod.FORBIDDEN_SHAS["T2_BOOT"] == \
        "d347cc1907563afd2c8faa0d07cafed5904985514c346434c8a774c14418e925"
    assert mod.FORBIDDEN_SHAS["T3_BOOT"] == \
        "d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df"
    assert mod.FORBIDDEN_SHAS["FIX8_BOOT"] == \
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5"
    assert mod.FORBIDDEN_SHAS["PANIC30_BOOT"] == \
        "ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1"
    assert mod.FORBIDDEN_SHAS["OLD_INIT8_BOOT"] == \
        "e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264"
    assert mod.FORBIDDEN_SHAS["ENTRY_STATE_PROBE_BOOT"] == \
        "cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c"
    lines.append("OBSERVER_T4_DECODER_CONSTANTS=PASS")


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
            lines.append(f"OBSERVER_T4_IDENTITY_{name}_REJECTED=PASS")
            continue
        fail("IDENTITY", f"{name} accepted")
    mutated = good_sha[:-1] + ("0" if good_sha[-1] != "0" else "1")
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, mutated, good_sha, forbidden,
                            mod.EXPECTED_PAYLOAD_SHA)
    except SystemExit:
        lines.append("OBSERVER_T4_IDENTITY_MUTATED_T4_REJECTED=PASS")
    else:
        fail("IDENTITY", "mutated T4 accepted")
    misboot = dict(forbidden)
    for name in forbidden:
        try:
            mod.verify_identity(mod.EXPECTED_SIZE, forbidden[name],
                                forbidden[name], misboot,
                                mod.EXPECTED_PAYLOAD_SHA)
        except SystemExit as exc:
            assert "T4_OBSERVER_MISBOOT_REFUSED" in str(exc), str(exc)
            assert name in str(exc), f"refusal missing label {name}"
            lines.append(f"OBSERVER_T4_IDENTITY_{name}_MISBOOT_REFUSED=PASS")
        else:
            fail("IDENTITY", f"{name} misboot accepted")
    mod.verify_identity(mod.EXPECTED_SIZE, good_sha, good_sha, misboot,
                        mod.EXPECTED_PAYLOAD_SHA)
    lines.append("OBSERVER_T4_IDENTITY_EXACT_MATCH_ACCEPTED=PASS")


def decoder_fixtures(lines):
    mod = OBS
    v = mod.t4_reachability(14.238, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["stage"] == "PROVEN", v
    assert v["case"] == "T4_A_STRONG" and v["next"] == C_DELAY, v
    v = mod.t4_reachability(12.738, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["stage"] == "PROVEN", v
    v = mod.t4_reachability(15.738, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["stage"] == "PROVEN", v
    v = mod.t4_reachability(16.5, "AUTOMATIC_ANDROID_RETURN")
    assert abs(mod.t4_minus_t3(16.5) - 2.262) < 1e-9
    assert v["verdict"] == "SUPPORTED" and v["stage"] == "STRONGLY_SUPPORTED", v
    assert v["case"] == "T4_B_SUPPORTED" and v["next"] == C_DELAY, v
    for t, case, next_ in (
            (17.5, "T4_EARLY_RETURN_TIMING_MISMATCH", ISO),
            (11.0, "T4_EARLY_RETURN_TIMING_MISMATCH", ISO),
            (20.0, "T4_SIGNATURE_NOT_OBSERVED", ISO),
            (mod.FIX8_TOTAL_S, "T4_SIGNATURE_NOT_OBSERVED", ISO),
            (mod.PANIC30_TOTAL_S, "T4_SIGNATURE_NOT_OBSERVED", ISO),
            (28.0, "UNKNOWN", ISO)):
        v = mod.t4_reachability(t, "AUTOMATIC_ANDROID_RETURN")
        assert v["verdict"] == "NOT_OBSERVED" and v["case"] == case, (t, v)
        assert v["stage"] == "NOT_PROVEN", v
        assert v["next"] == next_, v
    v = mod.t4_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "T4_STABLE_FASTBOOT" and \
        "SECOND_BOOT_AND_T4_FORBIDDEN" in v["reason"], v
    v = mod.t4_reachability(None, "MANUAL_RECOVERY_OR_NO_RETURN")
    assert v["case"] == "T4_NO_RETURN", v
    v = mod.t4_reachability(None, "UNKNOWN")
    assert v["verdict"] == "NOT_OBSERVED" and v["next"] == ISO, v
    assert mod.T3_REFERENCE_TOTAL_S == 14.238, mod.T3_REFERENCE_TOTAL_S
    assert mod.T4_STRONG_HALF_WINDOW_S == 1.5, mod.T4_STRONG_HALF_WINDOW_S
    assert mod.T4_SUPPORTED_HALF_WINDOW_S == 3.0, mod.T4_SUPPORTED_HALF_WINDOW_S
    assert mod.T4_CROSSCHECK_HALF_WINDOW_S == 3.0, mod.T4_CROSSCHECK_HALF_WINDOW_S
    assert mod.T4_EARLY_RETURN_CLASS_LIMIT_S == 20.0, \
        mod.T4_EARLY_RETURN_CLASS_LIMIT_S
    assert mod.T4_CASE_C_BAND_S == (20.0, 28.0), mod.T4_CASE_C_BAND_S
    assert mod.T4_PROGRAMMED_S == 8.0, mod.T4_PROGRAMMED_S
    assert mod.P0_REF_OVERHEAD_S == 6.1445, mod.P0_REF_OVERHEAD_S
    for bad in ({"verdict": "STRONG", "stage": "NOT_PROVEN"},
                {"verdict": "SUPPORTED", "stage": "PROVEN"}):
        got = mod.t4_reachability(
            14.238 if bad["verdict"] == "STRONG" else 16.5,
            "AUTOMATIC_ANDROID_RETURN")["stage"]
        if got == bad["stage"]:
            fail("DECODER",
                 f"stage grading lost for {bad['verdict']}: {got}")
    lines.append("OBSERVER_T4_DECODER_CONSTANTS=PASS")
    lines.append("OBSERVER_T4_DECODER_CASES_A_TO_F=PASS")


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
    assert cap.has(r"SUMMARY T4_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"SUMMARY T4_SIGNATURE_NOT_OBSERVED=YES")
    assert cap.has(r"T4_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(ISO)}")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY T4_DIAGNOSTIC_ONLY=YES")
    assert cap.has(r"T4_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    assert cap.has(r"SUMMARY T4_SELECTED_STAGE=C6_PARSE_ARGS_COMPLETE")
    assert cap.has(r"SUMMARY R5_NORMAL_START_KERNEL_BODY=NOT_PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(r"SUMMARY R6=NOT_PROVEN")
    assert cap.has(r"SUMMARY R7=NOT_PROVEN")
    assert not cap.has(r"T4_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert not cap.has(r"T4_PROGRAMMED_ESTIMATE=[0-9]")
    return cap


def s2_strong_signature():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_sending_okay": 1000.5,
        "t_booting_okay": 1001.0, "t_disappear": 1002.0,
        "t_adb_first_seen": 1013.0, "t_boot_completed": 1041.0,
        "kernel_host_before": 1015.238, "kernel_uptime": 0.0,
        "kernel_start": 1015.238, "slot_suffix": "_a",
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    total = mod.t4_total(1015.238, 1001.0)
    assert abs(total - 14.238) < 1e-9
    assert cap.has(rf"T4_BOOTING_TO_RETURNED_KERNEL_START={total:.3f}")
    est = mod.t4_programmed_estimate(total)
    assert abs(est - 8.0935) < 1e-6
    assert cap.has(rf"SUMMARY T4_PROGRAMMED_ESTIMATE={est:.3f} "
                   r"\(SECONDARY cross-check")
    d3 = mod.t4_minus_t3(total)
    d2 = mod.t4_minus_t2(total)
    d1 = mod.t4_minus_t1(total)
    d0 = mod.t4_minus_t0(total)
    assert abs(d3) < 1e-9
    assert abs(d2 - (-0.002)) < 1e-9
    assert abs(d1) < 1e-9
    assert abs(d0 - (-0.014)) < 1e-9
    assert cap.has(rf"SUMMARY T4_MINUS_T3={re.escape(f'{d3:+.3f}')} ")
    assert cap.has(rf"SUMMARY T4_MINUS_T2={re.escape(f'{d2:+.3f}')} ")
    assert cap.has(rf"SUMMARY T4_MINUS_T1={re.escape(f'{d1:+.3f}')} ")
    assert cap.has(rf"SUMMARY T4_MINUS_T0={re.escape(f'{d0:+.3f}')} ")
    assert cap.has(r"SUMMARY T3_REFERENCE_TOTAL=14\.238 "
                   r"\(PRIMARY matched-control reference")
    assert cap.has(r"SUMMARY T2_REFERENCE_TOTAL=14\.240 "
                   r"\(SECONDARY matched reference\)")
    assert cap.has(r"SUMMARY T1_REFERENCE_TOTAL=14\.238 "
                   r"\(SECONDARY matched reference\)")
    assert cap.has(r"SUMMARY T0_REFERENCE_TOTAL=14\.252 "
                   r"\(SECONDARY matched reference\)")
    assert cap.has(r"SUMMARY T4_EARLY_RETURN_CLASS_MATCH=YES")
    assert cap.has(r"SUMMARY T4_REACHABILITY_SIGNATURE=STRONG "
                   r"case=T4_A_STRONG "
                   r"reason=T3_MATCHED_CONTROL\+EARLY_RETURN_CLASS\+"
                   r"AUTOMATIC_RESET\+T2_T1_T0_CROSSCHECK_OK")
    assert cap.has(r"SUMMARY C6_PARSE_ARGS_COMPLETE_REACHED=PROVEN")
    assert cap.has(r"SUMMARY NORMAL_START_KERNEL_BODY_TO_C6_EXECUTED=PROVEN")
    assert cap.has(r"SUMMARY PANIC_PARAMETER_PARSED_BY_RUNNING_KERNEL=PROVEN")
    assert cap.has(r"SUMMARY RDINIT_PARAMETER_PARSED_BY_RUNNING_KERNEL=PROVEN")
    assert cap.has(r"SUMMARY CALIBRATE_DELAY=NOT_PROVEN")
    assert cap.has(r"SUMMARY REST_INIT=NOT_PROVEN")
    assert cap.has(r"SUMMARY INITRAMFS=NOT_PROVEN")
    assert cap.has(r"SUMMARY INIT_EXEC=/init=NOT_PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(r"SUMMARY R5_NORMAL_START_KERNEL_BODY=NOT_PROVEN")
    assert cap.has(r"SUMMARY R6=NOT_PROVEN")
    assert cap.has(r"SUMMARY R7=NOT_PROVEN")
    assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(C_DELAY)}")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN")
    assert cap.has(r"SUMMARY T4_SELECTED_STAGE=C6_PARSE_ARGS_COMPLETE")
    assert cap.has(r"SUMMARY T4_DIAGNOSTIC_ONLY=YES")
    assert cap.has(r"T4_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    assert cap.has(r"T4_NOT_REACHED_LICENSE=NO")
    assert not cap.has(r"T4_SIGNATURE_NOT_OBSERVED=YES")


def s2b_c3_fallback_strong():
    mod = OBS
    old = os.environ.get("R3_T4_SELECTED_STAGE")
    os.environ["R3_T4_SELECTED_STAGE"] = "C3_SETUP_ARCH_RETURN"
    try:
        st = template(mod)
        st.update({"t_booting_okay": 1001.0, "kernel_start": 1015.238,
                   "t_boot_completed": 1041.0})
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(r"SUMMARY T4_SELECTED_STAGE=C3_SETUP_ARCH_RETURN")
        assert cap.has(r"SUMMARY T4_REACHABILITY_SIGNATURE=STRONG")
        assert cap.has(r"SUMMARY SETUP_ARCH_RETURN_REACHED=PROVEN")
        assert cap.has(r"SUMMARY PARSE_EARLY_PARAM_COMPLETE=PROVEN")
        assert cap.has(r"SUMMARY C6_PARSE_ARGS_COMPLETE_REACHED=NOT_PROVEN")
        assert cap.has(r"SUMMARY PARSE_ARGS=NOT_PROVEN")
        assert cap.has(r"SUMMARY PANIC_PARAMETER_PARSED_BY_RUNNING_KERNEL="
                       r"NOT_PROVEN")
        assert cap.has(r"SUMMARY RDINIT_PARAMETER_PARSED_BY_RUNNING_KERNEL="
                       r"NOT_PROVEN")
        assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(C_DELAY)}")
    finally:
        if old is None:
            os.environ.pop("R3_T4_SELECTED_STAGE", None)
        else:
            os.environ["R3_T4_SELECTED_STAGE"] = old


def s3_supported_signature():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1017.5,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    d3 = mod.t4_minus_t3(16.5)
    assert abs(d3 - 2.262) < 1e-9
    assert cap.has(rf"SUMMARY T4_MINUS_T3={re.escape(f'{d3:+.3f}')}")
    assert cap.has(r"SUMMARY T4_REACHABILITY_SIGNATURE=SUPPORTED "
                   r"case=T4_B_SUPPORTED")
    assert cap.has(r"SUMMARY C6_PARSE_ARGS_COMPLETE_REACHED="
                   r"STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY NORMAL_START_KERNEL_BODY_TO_C6_EXECUTED="
                   r"STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY PANIC_PARAMETER_PARSED_BY_RUNNING_KERNEL="
                   r"STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY RDINIT_PARAMETER_PARSED_BY_RUNNING_KERNEL="
                   r"STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY R5_NORMAL_START_KERNEL_BODY=NOT_PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(C_DELAY)}")
    assert cap.has(r"T4_NOT_REACHED_LICENSE=NO")


def s4_early_return_timing_mismatch_case_d():
    mod = OBS
    for total, delta_s in ((17.5, r"\+3\.262"), (11.0, r"-3\.238")):
        st = template(mod)
        st.update({"t_booting_okay": 1001.0,
                   "kernel_start": 1001.0 + total,
                   "t_boot_completed": 1041.0})
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(rf"SUMMARY T4_MINUS_T3={delta_s}"), total
        assert cap.has(r"SUMMARY T4_EARLY_RETURN_CLASS_MATCH=YES"), total
        assert cap.has(r"SUMMARY T4_REACHABILITY_SIGNATURE=NOT_OBSERVED "
                       r"case=T4_EARLY_RETURN_TIMING_MISMATCH "
                       rf"reason=T4_MINUS_T3={delta_s}s "
                       r"OUTSIDE_SUPPORTED_WINDOW"), total
        assert cap.has(r"SUMMARY T4_SIGNATURE_NOT_OBSERVED=YES"), total
        assert cap.has(r"T4_NOT_REACHED_LICENSE=NO"), total
        assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(ISO)}"), total


def s5_old_auto_return_class_case_c():
    mod = OBS
    for total in (20.0, mod.FIX8_TOTAL_S, mod.PANIC30_TOTAL_S):
        st = template(mod)
        st.update({"t_booting_okay": 1001.0,
                   "kernel_start": 1001.0 + total,
                   "t_boot_completed": 1041.0})
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(r"SUMMARY T4_EARLY_RETURN_CLASS_MATCH=NO"), total
        assert cap.has(r"SUMMARY T4_REACHABILITY_SIGNATURE=NOT_OBSERVED "
                       r"case=T4_SIGNATURE_NOT_OBSERVED "
                       r"reason=CASE_C_OLD_AUTO_RETURN_CLASS"), total
        assert cap.has(r"T4_NOT_REACHED_LICENSE=NO"), total
        assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(ISO)}"), total


def s6_stable_fastboot_case_e():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "t_disappear": 1002.0, "stable_fastboot": True,
               "t_fastboot_stable": 1005.7})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                     final_adb=False, st=st)
    assert cap.has(r"T4_STABLE_FASTBOOT_OBSERVED=YES \(Case E record only; "
                   r"second boot and next round forbidden\)")
    assert cap.has(r"ELAPSED_BOOTING_TO_STABLE_FASTBOOT=4\.700")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert cap.has(r"SUMMARY T4_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"T4_NOT_REACHED_LICENSE=NO")
    v = mod.t4_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "T4_STABLE_FASTBOOT"
    assert v["reason"] == \
        "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_T4_FORBIDDEN"
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
    assert cap.has(r"T4_NO_RETURN_CASE_F=YES")
    assert cap.has(r"MANUAL_RECOVERY_ELAPSED_EXCLUDED_FROM_TIMING=YES")
    assert cap.has(r"SUMMARY T4_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert not cap.has(r"T4_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert cap.has(r"T4_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(ISO)}")


def s8_timing_without_android_return_insufficient():
    mod = OBS
    st = {"t_booting_okay": 0.0, "kernel_start": 14.238}
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"T4_BOOTING_TO_RETURNED_KERNEL_START=14\.238")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY T4_REACHABILITY_SIGNATURE=NOT_OBSERVED")
    assert cap.has(r"SUMMARY T_SENDING_OKAY=NA")
    assert cap.has(r"T4_NOT_REACHED_LICENSE=NO")
    assert cap.has(rf"SUMMARY T4_NEXT_STEP={re.escape(ISO)}")


OBS = None


def main() -> list:
    global OBS
    lines: list = []
    try:
        ast_deadlock_gate()
        lines.append("OBSERVER_T4_AST_DEADLOCK_GATE=PASS")
        mod = load_observer()
        for attr in ("emit_summary", "t4_total", "t4_reachability",
                     "t4_minus_t3", "t4_minus_t2", "t4_minus_t1",
                     "t4_minus_t0", "t4_programmed_estimate",
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
        scenario(lines, "C3_FALLBACK_STRONG", s2b_c3_fallback_strong)
        scenario(lines, "SUPPORTED_SIGNATURE", s3_supported_signature)
        scenario(lines, "EARLY_RETURN_TIMING_MISMATCH_CASE_D",
                 s4_early_return_timing_mismatch_case_d)
        scenario(lines, "OLD_AUTO_RETURN_CLASS_CASE_C",
                 s5_old_auto_return_class_case_c)
        scenario(lines, "STABLE_FASTBOOT_CASE_E", s6_stable_fastboot_case_e)
        scenario(lines, "NO_RETURN_MANUAL_EXCLUDED",
                 s7_no_return_manual_excluded)
        scenario(lines, "TIMING_WITHOUT_ANDROID_RETURN_INSUFFICIENT",
                 s8_timing_without_android_return_insufficient)
        lines.append("OBSERVER_T4_KEYERROR_GUARDED=YES")
        lines.append("OBSERVER_T4_SUMMARY_FIXTURE=PASS")
    except SystemExit:
        raise
    except Exception as exc:
        fail("UNEXPECTED", repr(exc))
    return lines


if __name__ == "__main__":
    for ln in main():
        print(ln)
    raise SystemExit(0)
