#!/usr/bin/env python3
"""Observer fixtures for the R3 P1B INIT8 true-device round.

Drives the INIT8 observer's summary/total paths with synthetic states — no
device, no fastboot/adb calls. Guards:
  - lock/log deadlock regression (AST gate: no lock-wrapped log/emit calls)
  - every summary return path with all keys initialized (no KeyError)
  - INIT8 timing semantics: only P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START,
    never a P0-overhead bucket decode, and manual-recovery elapsed never
    produces a timing product
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-p1b-init8.py"


def load_observer():
    spec = importlib.util.spec_from_file_location("init8_observer", OBSERVER)
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
    raise SystemExit(f"OBSERVER_INIT8_FIXTURE_FAILED {name}: {detail}")


def scenario(name: str, fn) -> None:
    try:
        fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    print(f"OBSERVER_INIT8_{name}_CASE=PASS")


def ast_deadlock_gate() -> None:
    src = OBSERVER.read_text()
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id in (
                        "log", "emit_summary", "capture_android_snapshot",
                    )
                ):
                    offenders.append(f"line {sub.lineno}: {sub.func.id}()")
    assert not offenders, f"lock-wrapped emit calls: {offenders}"
    forbidden = ("P0_OVERHEAD_REF", "NEAREST_BUCKET", "ALIGNMENT_MATCH",
                 "ALIGNMENT_MISMATCH", "OBSERVED_PROGRAMMED_DELAY")
    for tok in forbidden:
        assert tok not in src, f"forbidden P0-bucket token in INIT8 observer: {tok}"


def s1_zero_event_summary():
    mod = OBS
    st = template(mod)
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    for key in ("T_COMMAND_START", "T_SENDING_OKAY", "T_BOOTING_OKAY",
                "T_FASTBOOT_DISAPPEAR", "T_USB_FIRST_REENUM", "T_ADB_FIRST_SEEN",
                "T_BOOT_COMPLETED", "RETURNED_ANDROID_KERNEL_START"):
        assert cap.has(rf"SUMMARY {key}=NA"), f"missing {key}"
    assert cap.has(r"SUMMARY P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert cap.has(r"INIT24_BASELINE_SAVED=NO")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert not cap.has(r"P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    return cap


def s2_android_return_init8_total():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_sending_okay": 1000.5,
        "t_booting_okay": 1001.0, "t_disappear": 1002.0,
        "t_adb_first_seen": 1013.0, "t_boot_completed": 1041.0,
        "kernel_host_before": 1014.148, "kernel_uptime": 0.0,
        "kernel_start": 1014.148, "slot_suffix": "_a",
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=True, st=st)
    assert cap.has(r"P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=13\.148")
    assert cap.has(r"INIT24_BASELINE_SAVED=YES")
    assert cap.has(r"SUMMARY RETURNED_ANDROID_KERNEL_START=")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN")
    assert cap.has(r"ELAPSED_BOOTING_TO_ADB=12\.000")
    assert cap.has(r"ELAPSED_BOOTING_TO_BOOT_COMPLETED=40\.000")
    assert not cap.has(r"OBSERVED_PROGRAMMED_DELAY")
    assert not cap.has(r"NEAREST_BUCKET")
    assert not cap.has(r"ALIGNMENT")


def s3_total_helper_exact():
    mod = OBS
    assert abs(mod.p1b_init8_total(1014.148, 1001.0) - 13.148) < 1e-6
    assert mod.p1b_init8_total(None, 1001.0) is None
    assert mod.p1b_init8_total(1014.148, None) is None


def s4_stable_fastboot_4p7_candidate():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_booting_okay": 1001.0,
        "t_disappear": 1002.0, "stable_fastboot": True,
        "t_fastboot_stable": 1005.7,
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY P1B_AUTOMATIC_FASTBOOT_RETURN=True")
    assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_STABLE_FASTBOOT_RETURN")
    assert cap.has(r"ELAPSED_BOOTING_TO_STABLE_FASTBOOT=4\.700")
    assert cap.has(r"P1B_4P7S_PATH_OBSERVED=YES \(record only")
    assert cap.has(r"SUMMARY P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert not cap.has(r"NEAREST_BUCKET")


def s5_no_return_manual_recovery_excluded():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_booting_okay": 1001.0,
        "no_return_window_expired": True,
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
    assert cap.has(r"MANUAL_RECOVERY_ELAPSED_EXCLUDED_FROM_TIMING=YES")
    assert cap.has(r"SUMMARY P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=NA")
    assert not cap.has(r"P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=[0-9]")
    assert not cap.has(r"NEAREST_BUCKET")


def s6_slow_stable_fastboot_not_4p7():
    mod = OBS
    st = template(mod)
    st.update({
        "t_command_start": 1000.0, "t_booting_okay": 1001.0,
        "t_disappear": 1002.0, "stable_fastboot": True,
        "t_fastboot_stable": 1009.0,
    })
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                     final_adb=False, st=st)
    assert cap.has(r"ELAPSED_BOOTING_TO_STABLE_FASTBOOT=8\.000")
    assert not cap.has(r"P1B_4P7S_PATH_OBSERVED=YES")


def s7_legacy_state_no_keyerror():
    mod = OBS
    st = {"t_booting_okay": 0.0, "kernel_start": 14.148}
    cap = Capture()
    mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                     final_adb=False, st=st)
    assert cap.has(r"P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START=14\.148")
    assert cap.has(r"INIT24_BASELINE_SAVED=YES")
    assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
    assert cap.has(r"SUMMARY T_SENDING_OKAY=NA")


OBS = None


def main() -> None:
    global OBS
    try:
        ast_deadlock_gate()
        print("OBSERVER_INIT8_AST_DEADLOCK_GATE=PASS")
        mod = load_observer()
        if not hasattr(mod, "emit_summary") or not hasattr(mod, "p1b_init8_total"):
            fail("LOAD", "observer lacks emit_summary/p1b_init8_total")
        OBS = mod
        scenario("ZERO_EVENT_SUMMARY", s1_zero_event_summary)
        scenario("ANDROID_RETURN_INIT8_TOTAL", s2_android_return_init8_total)
        scenario("TOTAL_HELPER_EXACT", s3_total_helper_exact)
        scenario("STABLE_FASTBOOT_4P7_CANDIDATE", s4_stable_fastboot_4p7_candidate)
        scenario("NO_RETURN_MANUAL_EXCLUDED", s5_no_return_manual_recovery_excluded)
        scenario("SLOW_STABLE_NOT_4P7", s6_slow_stable_fastboot_not_4p7)
        scenario("LEGACY_STATE_NO_KEYERROR", s7_legacy_state_no_keyerror)
        print("OBSERVER_INIT8_KEYERROR_FIXED=YES")
        print("OBSERVER_INIT8_SUMMARY_FIXTURE=PASS")
    except SystemExit:
        raise
    except Exception as exc:
        fail("UNEXPECTED", repr(exc))


if __name__ == "__main__":
    main()
