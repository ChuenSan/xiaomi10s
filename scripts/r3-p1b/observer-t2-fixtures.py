#!/usr/bin/env python3
"""Observer fixtures for the R3 P1B T2-8 __primary_switched round.

Drives the T2 observer's identity/decoder/summary paths with synthetic
states — no device, no fastboot/adb calls. Guards:
  - lock/log deadlock regression (AST gate: no lock-wrapped log/emit calls)
  - FULL-SHA identity gate + misboot refusal (T0 / T1 / FIX8 / PANIC30 / old
    INIT8 / entry-state probe boots refused before any fastboot interaction)
  - T2 timing semantics: primary product is
    T2_BOOTING_TO_RETURNED_KERNEL_START decoded against the T1 matched control
    (T1_TOTAL 14.238s; STRONG +-1.0s, SUPPORTED +-2.0s, early class < 20s, old
    class [20,28)s) with the T0 14.252s second cross-check; a negative NEVER
    produces T2_NOT_REACHED and always routes to T2_FAILURE_ISOLATION_CI;
    manual-recovery elapsed never yields a timing product; T2_PROGRAMMED_
    ESTIMATE is SECONDARY only; E2 is never auto-upgraded.
Cases A STRONG / B SUPPORTED / C old auto-return class / D early-return
timing mismatch / E stable fastboot / F no return.
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-p1b-t2.py"


def load_observer():
    spec = importlib.util.spec_from_file_location("t2_observer", OBSERVER)
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
    raise SystemExit(f"OBSERVER_T2_FIXTURE_FAILED {name}: {detail}")


def scenario(lines: list, name: str, fn) -> None:
    try:
        fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    except SystemExit as exc:
        fail(name, f"unexpected SystemExit: {exc}")
    lines.append(f"OBSERVER_T2_{name}_CASE=PASS")


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
    for tok in ("P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START",
                "INIT24_BASELINE_SAVED", "NEAREST_BUCKET",
                "ALIGNMENT_MATCH", "ALIGNMENT_MISMATCH", "T0_WINDOW",
                "T1_MINUS_T0_IS_PRIMARY", "T2_NOT_REACHED_LICENSE=YES"):
        assert tok not in src, f"forbidden token in T2 observer: {tok}"
    for tok in ("R3_T2_SHA256", "T2_OBSERVER_MISBOOT_REFUSED",
                "T2_NOT_REACHED_LICENSE=NO", "T2_FAILURE_ISOLATION_CI",
                "FASTBOOT_BOOT_ONLY", "SECOND_BOOT_FORBIDDEN",
                "T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO", "T2_DIAGNOSTIC_ONLY=YES",
                "T2_MINUS_T1", "T2_MINUS_T0", "T1_REFERENCE_TOTAL",
                "T0_REFERENCE_TOTAL", "T2_PROGRAMMED_ESTIMATE",
                "MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI",
                "E2_EARLY_MAINLINE_BOOT=NOT_PROVEN",
                "R3_PRIMARY_SWITCHED_REACHABILITY",
                "ENTRY_STATE_PROBE_BOOT", "T1_BOOT",
                "T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8"):
        assert tok in src, f"required token missing in T2 observer: {tok}"


def decoder_constants(mod, lines) -> None:
    assert mod.T1_REFERENCE_TOTAL_S == 14.238
    assert mod.T0_REFERENCE_TOTAL_S == 14.252
    assert mod.T1_MINUS_T0_OBSERVED_S == -0.014
    assert mod.T2_STRONG_HALF_WINDOW_S == 1.0
    assert mod.T2_SUPPORTED_HALF_WINDOW_S == 2.0
    assert mod.T2_CROSSCHECK_HALF_WINDOW_S == 2.0
    assert mod.T2_EARLY_RETURN_CLASS_LIMIT_S == 20.0
    assert mod.T2_CASE_C_BAND_S == (20.0, 28.0)
    assert mod.P0_REF_OVERHEAD_S == 6.1445
    assert mod.T2_PROGRAMMED_S == 8.0
    assert mod.EXPECTED_SIZE == 37380096
    assert abs(mod.t2_minus_t1(14.238)) < 1e-9
    assert abs(mod.t2_programmed_estimate(14.238) - 8.0935) < 1e-9
    names = ("T0_BOOT", "T1_BOOT", "FIX8_BOOT", "PANIC30_BOOT",
             "OLD_INIT8_BOOT", "ENTRY_STATE_PROBE_BOOT")
    assert tuple(mod.FORBIDDEN_SHAS) == names, tuple(mod.FORBIDDEN_SHAS)
    assert mod.FORBIDDEN_SHAS["T0_BOOT"] == \
        "8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1"
    assert mod.FORBIDDEN_SHAS["T1_BOOT"] == \
        "a4fa083f289219facb0a69062749dd6a9d2f667c4aa044b25b78c36b0da7e3df"
    assert mod.FORBIDDEN_SHAS["FIX8_BOOT"] == \
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5"
    lines.append("OBSERVER_T2_DECODER_CONSTANTS=PASS")


def identity_fixtures(lines):
    mod = OBS
    forbidden = mod.FORBIDDEN_SHAS
    good_sha = "ab" * 32
    cases = [
        ("NON_HEX_SHA", (mod.EXPECTED_SIZE, good_sha, "xyz", forbidden)),
        ("WRONG_SIZE", (mod.EXPECTED_SIZE + 1, good_sha, good_sha, forbidden)),
        ("WRONG_SHA", (mod.EXPECTED_SIZE, "cd" * 32, good_sha, forbidden)),
    ]
    for name, args in cases:
        try:
            mod.verify_identity(*args)
        except SystemExit:
            lines.append(f"OBSERVER_T2_IDENTITY_{name}_REJECTED=PASS")
            continue
        fail("IDENTITY", f"{name} accepted")
    misboot = dict(forbidden)
    for name in forbidden:
        try:
            mod.verify_identity(mod.EXPECTED_SIZE, forbidden[name],
                                forbidden[name], misboot)
        except SystemExit as exc:
            assert "T2_OBSERVER_MISBOOT_REFUSED" in str(exc), str(exc)
            assert name in str(exc), f"refusal missing label {name}"
            lines.append(f"OBSERVER_T2_IDENTITY_{name}_MISBOOT_REFUSED=PASS")
        else:
            fail("IDENTITY", f"{name} misboot accepted")
    mod.verify_identity(mod.EXPECTED_SIZE, good_sha, good_sha, misboot)
    lines.append("OBSERVER_T2_IDENTITY_EXACT_MATCH_ACCEPTED=PASS")


def decoder_fixtures(lines):
    mod = OBS
    v = mod.t2_reachability(14.2, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "STRONG" and v["r3"] == "PROVEN", v
    assert v["next"] == \
        "MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI", v
    v = mod.t2_reachability(12.3, "AUTOMATIC_ANDROID_RETURN")
    assert v["verdict"] == "SUPPORTED" and v["r3"] == "STRONGLY_SUPPORTED", v
    for t, case in ((16.4, "T2_EARLY_RETURN_TIMING_MISMATCH"),
                    (11.0, "T2_EARLY_RETURN_TIMING_MISMATCH"),
                    (20.0, "T2_SIGNATURE_NOT_OBSERVED"),
                    (mod.FIX8_TOTAL_S, "T2_SIGNATURE_NOT_OBSERVED"),
                    (mod.PANIC30_TOTAL_S, "T2_SIGNATURE_NOT_OBSERVED"),
                    (28.0, "UNKNOWN")):
        v = mod.t2_reachability(t, "AUTOMATIC_ANDROID_RETURN")
        assert v["verdict"] == "NOT_OBSERVED" and v["case"] == case, (t, v)
        assert v["r3"] == "NOT_PROVEN", v
        assert v["next"] == "T2_FAILURE_ISOLATION_CI", v
    v = mod.t2_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "T2_STABLE_FASTBOOT" and \
        "SECOND_BOOT_AND_T3_FORBIDDEN" in v["reason"], v
    v = mod.t2_reachability(None, "MANUAL_RECOVERY_OR_NO_RETURN")
    assert v["case"] == "T2_NO_RETURN", v
    v = mod.t2_reachability(None, "UNKNOWN")
    assert v["verdict"] == "NOT_OBSERVED" and \
        v["next"] == "T2_FAILURE_ISOLATION_CI", v
    lines.append("OBSERVER_T2_DECODER_CASES_A_TO_F=PASS")


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
    assert cap.has(r"SUMMARY T2_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"SUMMARY T2_SIGNATURE_NOT_OBSERVED=YES")
    assert cap.has(r"T2_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"SUMMARY T2_NEXT_STEP=T2_FAILURE_ISOLATION_CI")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY T2_DIAGNOSTIC_ONLY=YES")
    assert cap.has(r"T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    assert cap.has(r"SUMMARY E1_NORMAL_PRIMARY_ENTRY_EXECUTION=NOT_PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(r"SUMMARY R3_PRIMARY_SWITCHED_REACHABILITY=NOT_PROVEN")
    assert not cap.has(r"T2_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert not cap.has(r"T2_PROGRAMMED_ESTIMATE=[0-9]")
    return cap


def s2_strong_signature():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_sending_okay": 1000.5,
        "t_booting_okay": 1001.0, "t_disappear": 1002.0,
        "t_adb_first_seen": 1013.0, "t_boot_completed": 1041.0,
        "kernel_host_before": 1015.2, "kernel_uptime": 0.0,
        "kernel_start": 1015.2, "slot_suffix": "_a",
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    total = mod.t2_total(1015.2, 1001.0)
    assert abs(total - 14.2) < 1e-9
    assert cap.has(rf"T2_BOOTING_TO_RETURNED_KERNEL_START={total:.3f}")
    est = mod.t2_programmed_estimate(total)
    assert abs(est - 8.0555) < 1e-6
    assert cap.has(rf"SUMMARY T2_PROGRAMMED_ESTIMATE={est:.3f} "
                   r"\(SECONDARY cross-check")
    d1 = mod.t2_minus_t1(total)
    d0 = mod.t2_minus_t0(total)
    assert cap.has(rf"SUMMARY T2_MINUS_T1={re.escape(f'{d1:+.3f}')} ")
    assert cap.has(rf"SUMMARY T2_MINUS_T0={re.escape(f'{d0:+.3f}')} ")
    assert cap.has(r"SUMMARY T1_REFERENCE_TOTAL=14\.238 "
                   r"\(PRIMARY matched-control reference\)")
    assert cap.has(r"SUMMARY T0_REFERENCE_TOTAL=14\.252 "
                   r"\(SECOND matched reference")
    assert cap.has(r"SUMMARY T2_EARLY_RETURN_CLASS_MATCH=YES")
    assert cap.has(r"SUMMARY T2_REACHABILITY_SIGNATURE=STRONG "
                   r"case=T2_A_STRONG "
                   r"reason=T1_MATCHED_CONTROL\+EARLY_RETURN_CLASS\+"
                   r"AUTOMATIC_RESET\+T0_CROSSCHECK_OK")
    assert cap.has(r"SUMMARY R3_PRIMARY_SWITCHED_REACHABILITY=PROVEN")
    assert cap.has(r"SUMMARY PRIMARY_SWITCHED_ADDRESS_REACHED=PROVEN")
    assert cap.has(r"SUMMARY E1_NORMAL_PRIMARY_ENTRY_EXECUTION=PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert cap.has(r"SUMMARY T2_NEXT_STEP="
                   r"MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN")
    assert cap.has(r"SUMMARY RETURNED_ANDROID_KERNEL_START=")
    assert cap.has(r"SUMMARY T2_DIAGNOSTIC_ONLY=YES")
    assert cap.has(r"T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    assert not cap.has(r"T2_NOT_REACHED_LICENSE=NO")
    assert not cap.has(r"T2_SIGNATURE_NOT_OBSERVED=YES")


def s3_supported_signature():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1016.3,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    d1 = mod.t2_minus_t1(15.3)
    assert abs(d1 - 1.062) < 1e-9
    assert cap.has(rf"SUMMARY T2_MINUS_T1={re.escape(f'{d1:+.3f}')}")
    assert cap.has(r"SUMMARY T2_REACHABILITY_SIGNATURE=SUPPORTED "
                   r"case=T2_B_SUPPORTED")
    assert cap.has(r"SUMMARY R3_PRIMARY_SWITCHED_REACHABILITY="
                   r"STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY PRIMARY_SWITCHED_ADDRESS_REACHED="
                   r"STRONGLY_SUPPORTED")
    assert cap.has(r"SUMMARY E1_NORMAL_PRIMARY_ENTRY_EXECUTION=NOT_PROVEN")
    assert cap.has(r"SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    assert not cap.has(r"T2_NOT_REACHED_LICENSE=NO")


def s4_early_return_timing_mismatch_case_d():
    mod = OBS
    for total, delta_s in ((16.4, r"\+2\.162"), (11.0, r"-3\.238")):
        st = template(mod)
        st.update({"t_booting_okay": 1001.0,
                   "kernel_start": 1001.0 + total,
                   "t_boot_completed": 1041.0})
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(rf"SUMMARY T2_MINUS_T1={delta_s}"), total
        assert cap.has(r"SUMMARY T2_EARLY_RETURN_CLASS_MATCH=YES"), total
        assert cap.has(r"SUMMARY T2_REACHABILITY_SIGNATURE=NOT_OBSERVED "
                       r"case=T2_EARLY_RETURN_TIMING_MISMATCH "
                       rf"reason=T2_MINUS_T1={delta_s}s "
                       r"OUTSIDE_SUPPORTED_WINDOW"), total
        assert cap.has(r"SUMMARY R3_PRIMARY_SWITCHED_REACHABILITY="
                       r"NOT_PROVEN"), total
        assert cap.has(r"SUMMARY T2_SIGNATURE_NOT_OBSERVED=YES"), total
        assert cap.has(r"T2_NOT_REACHED_LICENSE=NO"), total
        assert cap.has(r"SUMMARY T2_NEXT_STEP=T2_FAILURE_ISOLATION_CI"), total


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
        assert cap.has(r"SUMMARY T2_EARLY_RETURN_CLASS_MATCH=NO"), total
        assert cap.has(r"SUMMARY T2_REACHABILITY_SIGNATURE=NOT_OBSERVED "
                       r"case=T2_SIGNATURE_NOT_OBSERVED "
                       r"reason=CASE_C_OLD_AUTO_RETURN_CLASS"), total
        assert cap.has(r"SUMMARY R3_PRIMARY_SWITCHED_REACHABILITY="
                       r"NOT_PROVEN"), total
        assert cap.has(r"T2_NOT_REACHED_LICENSE=NO"), total


def s6_stable_fastboot_case_e():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "t_disappear": 1002.0, "stable_fastboot": True,
               "t_fastboot_stable": 1005.7})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                     final_adb=False, st=st)
    assert cap.has(r"T2_STABLE_FASTBOOT_OBSERVED=YES \(Case E record only; "
                   r"second boot and T3 forbidden\)")
    assert cap.has(r"ELAPSED_BOOTING_TO_STABLE_FASTBOOT=4\.700")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert cap.has(r"SUMMARY T2_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"T2_NOT_REACHED_LICENSE=NO")
    v = mod.t2_reachability(None, "AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert v["case"] == "T2_STABLE_FASTBOOT"
    assert v["reason"] == \
        "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_T3_FORBIDDEN"
    assert v["next"] == "T2_FAILURE_ISOLATION_CI"


def s7_no_return_manual_excluded():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "no_return_window_expired": True})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
    assert cap.has(r"T2_NO_RETURN_CASE_F=YES")
    assert cap.has(r"MANUAL_RECOVERY_ELAPSED_EXCLUDED_FROM_TIMING=YES")
    assert cap.has(r"SUMMARY T2_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert not cap.has(r"T2_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert cap.has(r"T2_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"SUMMARY T2_NEXT_STEP=T2_FAILURE_ISOLATION_CI")


def s8_timing_without_android_return_insufficient():
    mod = OBS
    st = {"t_booting_okay": 0.0, "kernel_start": 14.148}
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"T2_BOOTING_TO_RETURNED_KERNEL_START=14\.148")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY T2_REACHABILITY_SIGNATURE=NOT_OBSERVED")
    assert cap.has(r"SUMMARY T_SENDING_OKAY=NA")
    assert cap.has(r"T2_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"SUMMARY T2_NEXT_STEP=T2_FAILURE_ISOLATION_CI")


OBS = None


def main() -> list:
    global OBS
    lines: list = []
    try:
        ast_deadlock_gate()
        lines.append("OBSERVER_T2_AST_DEADLOCK_GATE=PASS")
        mod = load_observer()
        for attr in ("emit_summary", "t2_total", "t2_reachability",
                     "t2_minus_t1", "t2_minus_t0", "t2_programmed_estimate"):
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
        lines.append("OBSERVER_T2_KEYERROR_GUARDED=YES")
        lines.append("OBSERVER_T2_SUMMARY_FIXTURE=PASS")
    except SystemExit:
        raise
    except Exception as exc:
        fail("UNEXPECTED", repr(exc))
    return lines


if __name__ == "__main__":
    for ln in main():
        print(ln)
    raise SystemExit(0)
