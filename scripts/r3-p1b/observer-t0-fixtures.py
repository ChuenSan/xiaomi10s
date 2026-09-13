#!/usr/bin/env python3
"""Observer fixtures for the R3 P1B T0-8 true-device round.

Drives the T0 observer's identity/summary paths with synthetic states — no
device, no fastboot/adb calls. Guards:
  - lock/log deadlock regression (AST gate: no lock-wrapped log/emit calls)
  - FULL-SHA identity gate + misboot refusal (FIX8 / PANIC30 / old INIT8 /
    entry-state probe boots must be refused before any fastboot interaction)
  - T0 timing semantics: primary product is
    T0_BOOTING_TO_RETURNED_KERNEL_START with the preregistered supporting
    decoder; a negative NEVER produces T0_NOT_REACHED and always routes to
    T0_FAILURE_ISOLATION_CI; manual-recovery elapsed never yields a timing
    product
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-p1b-t0.py"


def load_observer():
    spec = importlib.util.spec_from_file_location("t0_observer", OBSERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Capture:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, msg: str, ts=None) -> None:
        self.lines.append(msg)

    def has(self, pattern: str) -> bool:
        return any(re.search(pattern, ln) for ln in self.lines)


def template(mod) -> dict:
    return dict(mod.state)


def fail(name: str, detail: str) -> None:
    raise SystemExit(f"OBSERVER_T0_FIXTURE_FAILED {name}: {detail}")


def scenario(lines: list[str], name: str, fn) -> None:
    try:
        fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    except SystemExit as exc:
        fail(name, f"unexpected SystemExit: {exc}")
    lines.append(f"OBSERVER_T0_{name}_CASE=PASS")


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
                "INIT24_BASELINE_SAVED", "P0_OVERHEAD_REF", "NEAREST_BUCKET",
                "ALIGNMENT_MATCH", "ALIGNMENT_MISMATCH"):
        assert tok not in src, f"forbidden token in T0 observer: {tok}"
    for tok in ("R3_T0_SHA256", "T0_OBSERVER_MISBOOT_REFUSED",
                "T0_NOT_REACHED_LICENSE=NO", "T0_FAILURE_ISOLATION_CI",
                "FASTBOOT_BOOT_ONLY"):
        assert tok in src, f"required token missing in T0 observer: {tok}"


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
            lines.append(f"OBSERVER_T0_IDENTITY_{name}_REJECTED=PASS")
            continue
        fail("IDENTITY", f"{name} accepted")
    misboot = dict(forbidden)
    try:
        mod.verify_identity(mod.EXPECTED_SIZE,
                            forbidden["PANIC30_BOOT"],
                            forbidden["PANIC30_BOOT"], misboot)
    except SystemExit as exc:
        assert "T0_OBSERVER_MISBOOT_REFUSED" in str(exc), str(exc)
        lines.append("OBSERVER_T0_IDENTITY_PANIC30_MISBOOT_REFUSED=PASS")
    else:
        fail("IDENTITY", "PANIC30 misboot accepted")
    try:
        mod.verify_identity(mod.EXPECTED_SIZE, forbidden["FIX8_BOOT"],
                            forbidden["FIX8_BOOT"], misboot)
    except SystemExit:
        lines.append("OBSERVER_T0_IDENTITY_FIX8_MISBOOT_REFUSED=PASS")
    else:
        fail("IDENTITY", "FIX8 misboot accepted")
    mod.verify_identity(mod.EXPECTED_SIZE, good_sha, good_sha, misboot)
    lines.append("OBSERVER_T0_IDENTITY_EXACT_MATCH_ACCEPTED=PASS")


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
    assert cap.has(r"SUMMARY T0_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"SUMMARY T0_SIGNATURE_NOT_OBSERVED=YES")
    assert cap.has(r"T0_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"SUMMARY T0_NEXT_STEP=T0_FAILURE_ISOLATION_CI")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert not cap.has(r"T0_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert not cap.has(r"T0_PROGRAMMED_ESTIMATE=[0-9]")
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
    total = 1015.2 - 1001.0
    assert cap.has(rf"T0_BOOTING_TO_RETURNED_KERNEL_START={total:.3f}")
    est = mod.t0_programmed_estimate(total)
    assert abs(est - 8.0555) < 1e-6
    assert cap.has(r"T0_WINDOW=STRONG")
    assert cap.has(r"T0_EARLY_RETURN_CLASS_MATCH=YES")
    assert cap.has(r"SUMMARY T0_REACHABILITY_SIGNATURE=STRONG "
                   r"reason=TIMER_SIGNATURE\+EARLY_RETURN_CLASS\+AUTOMATIC_RESET")
    assert cap.has(r"SUMMARY T0_NEXT_STEP="
                   r"MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN")
    assert cap.has(r"SUMMARY RETURNED_ANDROID_KERNEL_START=")
    assert not cap.has(r"T0_NOT_REACHED_LICENSE=NO")
    assert not cap.has(r"NEAREST_BUCKET")


def s3_supported_signature():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1017.5,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"T0_WINDOW=SUPPORTED")
    assert cap.has(r"SUMMARY T0_REACHABILITY_SIGNATURE=SUPPORTED")
    assert not cap.has(r"T0_NOT_REACHED_LICENSE=NO")


def s4_negative_no_not_reached_license():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1025.0,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"T0_WINDOW=OUTSIDE")
    assert cap.has(r"T0_EARLY_RETURN_CLASS_MATCH=NO")
    assert cap.has(r"SUMMARY T0_REACHABILITY_SIGNATURE=NOT_OBSERVED")
    assert cap.has(r"SUMMARY T0_SIGNATURE_NOT_OBSERVED=YES")
    assert cap.has(r"T0_NOT_REACHED_LICENSE=NO")
    assert cap.has(r"SUMMARY T0_NEXT_STEP=T0_FAILURE_ISOLATION_CI")


def s5_fast_return_alone_insufficient():
    mod = OBS
    st = template(mod)
    st.update({"t_booting_okay": 1001.0, "kernel_start": 1009.0,
               "t_boot_completed": 1041.0})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"T0_EARLY_RETURN_CLASS_MATCH=YES")
    assert cap.has(r"T0_WINDOW=OUTSIDE")
    assert cap.has(r"SUMMARY T0_REACHABILITY_SIGNATURE=NOT_OBSERVED")
    assert cap.has(r"T0_NOT_REACHED_LICENSE=NO")


def s6_stable_fastboot_case_c():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "t_disappear": 1002.0, "stable_fastboot": True,
               "t_fastboot_stable": 1005.7})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                     final_adb=False, st=st)
    assert cap.has(r"T0_STABLE_FASTBOOT_OBSERVED=YES \(Case C record")
    assert cap.has(r"ELAPSED_BOOTING_TO_STABLE_FASTBOOT=4\.700")
    assert cap.has(r"SUMMARY T0_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"T0_NOT_REACHED_LICENSE=NO")


def s7_no_return_manual_excluded():
    mod = OBS
    st = template(mod)
    st.update({"t_command_start": 1000.0, "t_booting_okay": 1001.0,
               "no_return_window_expired": True})
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
    assert cap.has(r"T0_NO_RETURN_CASE_D=YES")
    assert cap.has(r"MANUAL_RECOVERY_ELAPSED_EXCLUDED_FROM_TIMING=YES")
    assert cap.has(r"SUMMARY T0_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert not cap.has(r"T0_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert cap.has(r"T0_NOT_REACHED_LICENSE=NO")


def s8_legacy_state_no_keyerror():
    mod = OBS
    st = {"t_booting_okay": 0.0, "kernel_start": 14.148}
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"T0_BOOTING_TO_RETURNED_KERNEL_START=14\.148")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY T0_REACHABILITY_SIGNATURE=NOT_OBSERVED")
    assert cap.has(r"SUMMARY T_SENDING_OKAY=NA")


OBS = None


def main() -> list[str]:
    global OBS
    lines: list[str] = []
    try:
        ast_deadlock_gate()
        lines.append("OBSERVER_T0_AST_DEADLOCK_GATE=PASS")
        mod = load_observer()
        if not hasattr(mod, "emit_summary") or not hasattr(mod, "t0_total"):
            fail("LOAD", "observer lacks emit_summary/t0_total")
        if not hasattr(mod, "verify_identity"):
            fail("LOAD", "observer lacks verify_identity")
        OBS = mod
        identity_fixtures(lines)
        scenario(lines, "ZERO_EVENT_SUMMARY", s1_zero_event_summary)
        scenario(lines, "STRONG_SIGNATURE", s2_strong_signature)
        scenario(lines, "SUPPORTED_SIGNATURE", s3_supported_signature)
        scenario(lines, "NEGATIVE_NO_NOT_REACHED_LICENSE",
                 s4_negative_no_not_reached_license)
        scenario(lines, "FAST_RETURN_ALONE_INSUFFICIENT",
                 s5_fast_return_alone_insufficient)
        scenario(lines, "STABLE_FASTBOOT_CASE_C", s6_stable_fastboot_case_c)
        scenario(lines, "NO_RETURN_MANUAL_EXCLUDED",
                 s7_no_return_manual_excluded)
        scenario(lines, "LEGACY_STATE_NO_KEYERROR",
                 s8_legacy_state_no_keyerror)
        lines.append("OBSERVER_T0_KEYERROR_GUARDED=YES")
        lines.append("OBSERVER_T0_SUMMARY_FIXTURE=PASS")
    except SystemExit:
        raise
    except Exception as exc:
        fail("UNEXPECTED", repr(exc))
    return lines


if __name__ == "__main__":
    for ln in main():
        print(ln)
    sys.exit(0)
