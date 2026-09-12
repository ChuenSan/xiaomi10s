#!/usr/bin/env python3
"""Observer summary-path fixtures for the R3 load-alignment probe.

Drives the observer's summary and decode paths with synthetic states — no
device, no fastboot/adb calls. Guards the fixed uninitialized-state-key bug
(transient_fastboot KeyError at summary time) and every return path:
transient present/absent, automatic Android return, stable Fastboot return,
manual recovery/no return.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVER = HERE / "observe-r3-load-alignment.py"


def load_observer():
    spec = importlib.util.spec_from_file_location("lap_observer", OBSERVER)
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


def scenario(name: str, fn) -> None:
    try:
        cap = fn()
    except KeyError as exc:
        fail(name, f"KeyError still present: {exc}")
    except AssertionError as exc:
        fail(name, f"assertion {exc}")
    print(f"OBSERVER_{name}_CASE=PASS")
    return cap


def fail(name: str, detail: str) -> None:
    raise SystemExit(f"OBSERVER_SUMMARY_FIXTURE_FAILED {name}: {detail}")


def main() -> None:
    mod = load_observer()
    if not hasattr(mod, "emit_summary") or not hasattr(mod, "decode_alignment"):
        fail("LOAD", "observer lacks emit_summary/decode_alignment")

    def s1_transient_present():
        st = template(mod)
        st.update({
            "t_command_start": 1000.0, "t_booting_okay": 1001.0,
            "t_disappear": 1002.0, "transient_fastboot": True,
            "t_fastboot_transient": 1003.0,
        })
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=False, st=st)
        assert cap.has(r"SUMMARY FASTBOOT_TRANSIENT=True")
        assert not cap.has(r"SUMMARY FASTBOOT_TRANSIENT=False")
        assert cap.has(r"SUMMARY AUTOMATIC_FASTBOOT_AFTER_PROBE=False")
        assert cap.has(r"SUMMARY DECODE=NO_KERNEL_START")
        assert not cap.has(r"ALIGNMENT_MISMATCH")
        return cap

    def s2_transient_absent():
        st = template(mod)
        st.update({
            "t_command_start": 1000.0, "t_booting_okay": 1001.0,
            "t_disappear": 1002.0,
        })
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=False, st=st)
        assert cap.has(r"SUMMARY FASTBOOT_TRANSIENT=False")
        assert cap.has(r"SUMMARY DECODE=NO_KERNEL_START")
        return cap

    def s3_android_return_match():
        st = template(mod)
        st.update({
            "t_command_start": 0.0, "t_booting_okay": 0.0,
            "t_disappear": 1.0, "t_adb_first_seen": 12.0,
            "t_boot_completed": 20.0, "kernel_start": 14.148,
            "kernel_host_before": 14.148, "kernel_uptime": 0.0,
            "slot_suffix": "_a",
        })
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=True, st=st)
        assert cap.has(r"SUMMARY FASTBOOT_TRANSIENT=False")
        assert cap.has(r"SUMMARY AUTOMATIC_FASTBOOT_AFTER_PROBE=False")
        assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN")
        assert cap.has(r"SUMMARY NEAREST_BUCKET=8s")
        assert cap.has(r"SUMMARY VERDICT=STRONG")
        assert cap.has(r"SUMMARY DECODED_ALIGNMENT=ALIGNMENT_MATCH")
        assert cap.has(r"SUMMARY R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M=0x80000")
        assert cap.has(r"MAINLINE_IMAGE_ALIGNMENT_CONTRACT=SUPPORTED_BY_PROBE")
        return cap

    def s4_stable_fastboot_return():
        st = template(mod)
        st.update({
            "t_command_start": 1000.0, "t_booting_okay": 1001.0,
            "t_disappear": 1002.0, "stable_fastboot": True,
            "t_fastboot_stable": 1008.0,
        })
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=True,
                         final_adb=False, st=st)
        assert cap.has(r"SUMMARY AUTOMATIC_FASTBOOT_AFTER_PROBE=True")
        assert cap.has(r"SUMMARY RECOVERY_KIND=AUTOMATIC_STABLE_FASTBOOT_RETURN")
        assert cap.has(r"SUMMARY DECODE=NO_KERNEL_START")
        assert not cap.has(r"ALIGNMENT_MISMATCH")
        return cap

    def s5_manual_recovery_no_return():
        st = template(mod)
        st.update({
            "t_command_start": 1000.0, "t_booting_okay": 1001.0,
            "expected_probe_reset_not_observed": True,
        })
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=False, st=st)
        assert cap.has(r"EXPECTED_PROBE_RESET_NOT_OBSERVED=YES")
        assert cap.has(r"SUMMARY RECOVERY_KIND=MANUAL_RECOVERY_OR_NO_RETURN")
        assert cap.has(r"SUMMARY DECODE=NO_KERNEL_START")
        assert not cap.has(r"ALIGNMENT_MISMATCH")
        assert not cap.has(r"ALIGNMENT_MATCH")
        return cap

    def s6_decode_mismatch():
        st = template(mod)
        st.update({"t_booting_okay": 0.0, "kernel_start": 30.141})
        cap = Capture()
        mod.decode_alignment(30.141, emit=cap, st=st)
        assert cap.has(r"SUMMARY NEAREST_BUCKET=24s")
        assert cap.has(r"SUMMARY VERDICT=STRONG")
        assert cap.has(r"SUMMARY DECODED_ALIGNMENT=ALIGNMENT_MISMATCH")
        assert cap.has(r"SUMMARY R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M_MISMATCH=YES")
        assert cap.has(r"SUMMARY S_NOT_GUESSED=YES")
        assert not cap.has(r"R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M=0x80000")
        return cap

    def s7_decode_inconclusive():
        st = template(mod)
        st.update({"t_booting_okay": 0.0, "kernel_start": 10.094})
        cap = Capture()
        mod.decode_alignment(10.094, emit=cap, st=st)
        assert cap.has(r"SUMMARY VERDICT=INCONCLUSIVE")
        assert cap.has(r"SUMMARY R3_LOAD_ALIGNMENT_PROBE_INCONCLUSIVE")
        assert not cap.has(r"DECODED_ALIGNMENT")
        return cap

    def s8_legacy_state_no_keyerror():
        st = {"t_booting_okay": 0.0, "kernel_start": 14.148}
        cap = Capture()
        mod.emit_summary(emit=cap, final_usb="NONE", final_fastboot=False,
                         final_adb=False, st=st)
        assert cap.has(r"SUMMARY FASTBOOT_TRANSIENT=False")
        assert cap.has(r"SUMMARY AUTOMATIC_FASTBOOT_AFTER_PROBE=False")
        assert cap.has(r"SUMMARY RECOVERY_KIND=UNKNOWN")
        assert cap.has(r"SUMMARY NEAREST_BUCKET=8s")
        return cap

    def s9_decode_supported():
        st = template(mod)
        st.update({"t_booting_okay": 0.0, "kernel_start": 15.4445})
        cap = Capture()
        mod.decode_alignment(15.4445, emit=cap, st=st)
        assert cap.has(r"SUMMARY NEAREST_BUCKET=8s")
        assert cap.has(r"SUMMARY VERDICT=SUPPORTED")
        assert cap.has(r"SUMMARY DECODED_ALIGNMENT=ALIGNMENT_MATCH")
        return cap

    scenario("TRANSIENT_PRESENT", s1_transient_present)
    scenario("TRANSIENT_ABSENT", s2_transient_absent)
    scenario("ANDROID_RETURN", s3_android_return_match)
    scenario("STABLE_FASTBOOT_RETURN", s4_stable_fastboot_return)
    scenario("MANUAL_RECOVERY_NO_RETURN", s5_manual_recovery_no_return)
    scenario("DECODE_MATCH", s3_android_return_match)
    scenario("DECODE_MISMATCH", s6_decode_mismatch)
    scenario("DECODE_INCONCLUSIVE", s7_decode_inconclusive)
    scenario("LEGACY_STATE_NO_KEYERROR", s8_legacy_state_no_keyerror)
    scenario("DECODE_SUPPORTED", s9_decode_supported)
    print("OBSERVER_KEYERROR_FIXED=YES")
    print("OBSERVER_SUMMARY_FIXTURE=PASS")


if __name__ == "__main__":
    main()
