#!/usr/bin/env python3
"""R3 P1B PANIC_ENTRY-8 host observer. panic() ENTRY reachability round.

Derived from the device-proven R3 P1B T3 observer: same event loop, locking
discipline and fastboot stdout line timing, so the absolute host timeline
stays comparable across rounds. Identity gate is FULL-SHA ONLY and refuses
known wrong boots (T0 / T1 / T2 / T3 / T4 / C_DELAY / FIX8 / PANIC30 /
old INIT8 / entry-state probe) BEFORE any fastboot interaction.

Timing products (preregistered; panic() entry time is unknown, so this is
NOT a C_DELAY ± window):
  PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START  primary (BOOTING_OKAY ->
                                       returned Android kernel start)
  PANIC_ENTRY_MINUS_C_DELAY = PANIC_ENTRY_TOTAL - 14.464  AUXILIARY only
                                       (extra runtime from C_DELAY checkpoint
                                       position to actual panic entry; NOT
                                       required to be ~0)
  STRONG DISTINCTIVE CLASS: AUTOMATIC_ANDROID_RETURN AND
                                       PANIC_ENTRY_TOTAL < 20.000s
  VERY_STRONG_MATCHED subclass: STRONG AND
                                       -0.5s <= PANIC_ENTRY_MINUS_C_DELAY <= +3.0s
                                       (>3s but <20s is still STRONG, never
                                       automatic negative)
  SUPPORTED: AUTOMATIC_ANDROID_RETURN AND 20.000s <= TOTAL < 23.000s
                                       (wider causal window; does NOT overlap
                                       the 23-26s natural class)
  NATURAL 23-26s class: PANIC_ENTRY_SIGNATURE_NOT_OBSERVED
                                       (NEVER NO_LINUX_PANIC / PANIC_NOT_REACHED)
  PANIC_ENTRY_PROGRAMMED_ESTIMATE = PANIC_ENTRY_TOTAL - 6.1445  SECONDARY only
A STRONG PANIC_ENTRY signature proves the audited canonical panic() symbol
was invoked. It does NOT prove panic body, panic_timeout>0 branch, mdelay
loop, or emergency_restart. A negative is
PANIC_ENTRY_SIGNATURE_NOT_OBSERVED: it NEVER licenses NO_LINUX_PANIC
(PANIC_ENTRY_NOT_REACHED_LICENSE=NO always) and routes to
PANIC_ENTRY_FAILURE_ISOLATION_CI. Cases: A STRONG (<20s) / B SUPPORTED
(20-23s) / C natural 23-26s / E stable fastboot / F no return.

Artifact identity comes from the environment:
  R3_PANIC_ENTRY_BOOT_IMG       path to the exact thyme-r3-p1b-panic-entry boot image
  R3_PANIC_ENTRY_SHA256         expected FULL SHA256 recorded from the private run
  R3_PANIC_ENTRY_PAYLOAD_SHA256 expected FULL SHA256 of the P1B payload (hex format
                       checked only)
  R3_PANIC_ENTRY_FORBIDDEN_SHAS optional comma-separated extension of the refusal list
  R3_PANIC_ENTRY_SELECTED_STAGE PANIC_ENTRY_CANONICAL_PANIC
Missing or mismatching identity is a hard stop before any boot.
FASTBOOT_BOOT_ONLY=YES, SECOND_BOOT_FORBIDDEN=YES: no flash, no erase, no
set_active, no second boot; PANIC30/FIX24/M5N NOT AUTHORIZED from this
observer alone.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

BOOT_IMG = os.environ.get("R3_PANIC_ENTRY_BOOT_IMG", "")
EXPECTED_SHA = os.environ.get("R3_PANIC_ENTRY_SHA256", "")
EXPECTED_PAYLOAD_SHA = os.environ.get("R3_PANIC_ENTRY_PAYLOAD_SHA256", "")
EXPECTED_SIZE = 37380096
FORBIDDEN_SHAS = {
    "T0_BOOT":
        "8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1",
    "T1_BOOT":
        "a4fa083f289219facb0a69062749dd6a9d2f667c4aa044b25b78c36b0da7e3df",
    "T2_BOOT":
        "d347cc1907563afd2c8faa0d07cafed5904985514c346434c8a774c14418e925",
    "T3_BOOT":
        "d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df",
    "FIX8_BOOT":
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5",
    "PANIC30_BOOT":
        "ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1",
    "OLD_INIT8_BOOT":
        "e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264",
    "ENTRY_STATE_PROBE_BOOT":
        "cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c",
    "T4_BOOT":
        "3827fc0fe4216d7d18ccd2a60ea610a6bd10b2afa269e741923ca3bbc566849d",
    "C_DELAY_BOOT":
        "d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02",
}
for extra in filter(None, os.environ.get("R3_PANIC_ENTRY_FORBIDDEN_SHAS", "").split(",")):
    FORBIDDEN_SHAS[f"EXTRA_{len(FORBIDDEN_SHAS)}"] = extra.strip()

POLL = 0.10
PRIMARY_WINDOW = 120.0
ADB_EXTEND = 120.0
FASTBOOT_STABLE_SECS = 3.0
FASTBOOT = os.environ.get("FASTBOOT", "fastboot")
ADB = os.environ.get("ADB", "adb")

STAGE_PANIC_ENTRY = "PANIC_ENTRY_CANONICAL_PANIC"
SELECTED_STAGES = (STAGE_PANIC_ENTRY,)

# Preregistered distinctive-early decoder (NOT a C_DELAY ± window).
C_DELAY_REFERENCE_TOTAL_S = 14.464  # AUXILIARY predecessor (C_DELAY_TOTAL)
T4_REFERENCE_TOTAL_S = 14.385  # SECONDARY historical
T3_REFERENCE_TOTAL_S = 14.238  # SECONDARY
T2_REFERENCE_TOTAL_S = 14.240  # SECONDARY
T1_REFERENCE_TOTAL_S = 14.238  # SECONDARY
T0_REFERENCE_TOTAL_S = 14.252  # SECONDARY
PANIC_ENTRY_PROGRAMMED_S = 8.0
PANIC_ENTRY_EARLY_RETURN_CLASS_LIMIT_S = 20.0
PANIC_ENTRY_MATCHED_MINUS_C_DELAY_LO_S = -0.5
PANIC_ENTRY_MATCHED_MINUS_C_DELAY_HI_S = 3.0
PANIC_ENTRY_SUPPORTED_LO_S = 20.0
PANIC_ENTRY_SUPPORTED_HI_S = 23.0
PANIC_ENTRY_NATURAL_LO_S = 23.0
PANIC_ENTRY_NATURAL_HI_S = 28.0
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
P0_REF_OVERHEAD_S = 6.1445  # SECONDARY cross-check only

NEXT_STRONG = "WAIT_FOR_USER_APPROVAL"
NEXT_FAIL = "MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI"

lock = threading.Lock()
events = []
stop = threading.Event()
state = {
    "fastboot": False,
    "adb": False,
    "usb": (),
    "t_command_start": None,
    "t_sending_okay": None,
    "t_booting_okay": None,
    "t_disappear": None,
    "t_usb_none": None,
    "t_usb_first_reenum": None,
    "t_adb_first_seen": None,
    "t_boot_completed": None,
    "t_fastboot_transient": None,
    "t_fastboot_stable": None,
    "transient_fastboot": False,
    "stable_fastboot": False,
    "no_return_window_expired": False,
    "kernel_host_before": None,
    "kernel_uptime": None,
    "kernel_start": None,
    "slot_suffix": None,
    "uname": None,
    "uid": None,
    "bootreason": None,
}


def selected_stage() -> str:
    v = os.environ.get("R3_PANIC_ENTRY_SELECTED_STAGE", STAGE_PANIC_ENTRY)
    if v not in SELECTED_STAGES:
        raise SystemExit(
            f"R3_PANIC_ENTRY_SELECTED_STAGE={v!r} not in {SELECTED_STAGES}")
    return v


def iso(ts=None) -> str:
    t = datetime.fromtimestamp(ts if ts is not None else time.time(),
                               tz=timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(t.microsecond / 1000):03d}Z"


def fmt_t(value) -> str:
    return iso(value) if value else "NA"


def log(msg: str, ts=None) -> None:
    ts = time.time() if ts is None else ts
    line = f"{iso(ts)}  {ts:.3f}  {msg}"
    with lock:
        events.append((ts, iso(ts), msg))
    print(line, flush=True)


def run(cmd: list, timeout: float = 2.0) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"ERR:{e}"


def usb_snapshot() -> tuple:
    out = run(["ioreg", "-p", "IOUSB", "-w0", "-l"], timeout=3.0)
    devices = []
    cur: dict = {}
    for line in out.splitlines():
        if "+-o " in line:
            if cur.get("vid") is not None:
                devices.append(cur)
            cur = {"name": line.split("+-o", 1)[1].strip().split()[0],
                   "vid": None, "pid": None, "serial": ""}
        m = re.search(r'"idVendor"\s*=\s*(\d+)', line)
        if m:
            cur["vid"] = int(m.group(1))
        m = re.search(r'"idProduct"\s*=\s*(\d+)', line)
        if m:
            cur["pid"] = int(m.group(1))
        m = re.search(r'"USB Serial Number"\s*=\s*"([^"]+)"', line)
        if m:
            cur["serial"] = m.group(1)
    if cur.get("vid") is not None:
        devices.append(cur)
    out_t = []
    for d in devices:
        vid = int(d["vid"])
        pid = int(d.get("pid") or 0)
        if vid in (0x18D1, 0x2717, 0x05C6, 0x12D1) or pid in (
                0xD00D, 0x4EE7, 0x4EE1, 0x4EE2, 0x4EE5):
            out_t.append((vid, pid, d.get("serial") or d.get("name") or ""))
    return tuple(sorted(out_t))


def usb_fmt(snap) -> str:
    if not snap:
        return "NONE"
    return ",".join(f"{v:04x}:{p:04x}" for v, p, _s in snap)


def usb_has_fastboot(snap) -> bool:
    return any(vid == 0x18D1 and pid == 0xD00D for vid, pid, _s in snap)


def fastboot_present() -> bool:
    out = run([FASTBOOT, "devices"], timeout=2.0)
    return bool(re.search(r"\sfastboot\s*$", out, re.M)) or ("\tfastboot" in out)


def adb_present() -> bool:
    out = run([ADB, "devices"], timeout=2.0)
    return bool(re.search(r"\tdevice\s*$", out, re.M))


def boot_completed():
    out = run([ADB, "shell", "getprop", "sys.boot_completed"],
              timeout=3.0).strip()
    if not out or out.startswith("ERR:"):
        return None
    return out.splitlines()[-1].strip()


def panic_entry_minus_c_delay(total_s: float) -> float:
    return total_s - C_DELAY_REFERENCE_TOTAL_S


def panic_entry_programmed_estimate(total_s: float) -> float:
    return total_s - P0_REF_OVERHEAD_S  # SECONDARY cross-check only


def panic_entry_matched_subclass(total_s: float) -> bool:
    d = panic_entry_minus_c_delay(total_s)
    return (PANIC_ENTRY_MATCHED_MINUS_C_DELAY_LO_S <= d <=
            PANIC_ENTRY_MATCHED_MINUS_C_DELAY_HI_S)


def panic_entry_reachability(total_s, recovery_kind: str) -> dict:
    """Distinctive-early decoder. A negative NEVER licenses NO_LINUX_PANIC.
    <20s + auto-return is STRONG even if minus C_DELAY > +3s.
    """
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "PANIC_ENTRY_STABLE_FASTBOOT",
                "stage": "NOT_PROVEN", "next": NEXT_FAIL, "subclass": "NONE",
                "reason": "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_PANIC_ENTRY_FORBIDDEN"}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "PANIC_ENTRY_NO_RETURN",
                "stage": "NOT_PROVEN", "next": NEXT_FAIL, "subclass": "NONE",
                "reason": "CASE_F_NO_RETURN_MANUAL_ELAPSED_EXCLUDED"}
    if total_s is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
                "stage": "NOT_PROVEN", "next": NEXT_FAIL, "subclass": "NONE",
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    early = total_s < PANIC_ENTRY_EARLY_RETURN_CLASS_LIMIT_S
    if early:
        matched = panic_entry_matched_subclass(total_s)
        subclass = "VERY_STRONG_MATCHED" if matched else "DISTINCTIVE_EARLY"
        return {"verdict": "STRONG", "case": "PENTRY_A_STRONG",
                "stage": "PROVEN", "next": NEXT_STRONG, "subclass": subclass,
                "reason": "AUTOMATIC_ANDROID_RETURN+DISTINCTIVE_EARLY_<20S"
                          + ("+MATCHED_C_DELAY_SUBCLASS" if matched else
                             "+UNMATCHED_SUBCLASS_STILL_STRONG")}
    if PANIC_ENTRY_SUPPORTED_LO_S <= total_s < PANIC_ENTRY_SUPPORTED_HI_S:
        return {"verdict": "SUPPORTED", "case": "PENTRY_B_SUPPORTED",
                "stage": "STRONGLY_SUPPORTED", "next": NEXT_STRONG,
                "subclass": "WIDER_CAUSAL_20_23",
                "reason": "AUTOMATIC_ANDROID_RETURN+SUPPORTED_20_23_NOT_NATURAL"}
    if PANIC_ENTRY_NATURAL_LO_S <= total_s < PANIC_ENTRY_NATURAL_HI_S:
        return {"verdict": "NOT_OBSERVED",
                "case": "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED",
                "stage": "NOT_PROVEN", "next": NEXT_FAIL, "subclass": "NONE",
                "reason": "CASE_C_NATURAL_23_26_AUTO_RETURN_CLASS"}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
            "stage": "NOT_PROVEN", "next": NEXT_FAIL, "subclass": "NONE",
            "reason": f"PANIC_ENTRY_TOTAL={total_s:.3f}s OUTSIDE_PREREGISTERED_BANDS"}


def panic_entry_total(kernel_start, t_booting_okay):
    if kernel_start is None or t_booting_okay is None:
        return None
    return kernel_start - t_booting_okay


def recovery_kind(st: dict = None) -> str:
    st = st or {}
    if st.get("t_boot_completed") is not None:
        return "AUTOMATIC_ANDROID_RETURN"
    if st.get("t_fastboot_stable") is not None:
        return "AUTOMATIC_STABLE_FASTBOOT_RETURN"
    if st.get("no_return_window_expired"):
        return "MANUAL_RECOVERY_OR_NO_RETURN"
    return "UNKNOWN"


def capture_android_snapshot(tag: str) -> None:
    host_before = time.time()
    up_out = run([ADB, "shell", "cat", "/proc/uptime"], timeout=3.0)
    host_after = time.time()
    slot = run([ADB, "shell", "getprop", "ro.boot.slot_suffix"],
               timeout=3.0).strip().splitlines()
    uname = run([ADB, "shell", "uname", "-a"], timeout=3.0).strip().splitlines()
    uid = run([ADB, "shell", "su", "-c", "id"], timeout=5.0).strip().splitlines()
    bc = boot_completed()
    reason = run([ADB, "shell", "getprop", "ro.boot.bootreason"],
                 timeout=3.0).strip().splitlines()
    uptime = None
    kernel_start = None
    try:
        uptime = float(up_out.strip().split()[0])
        kernel_start = host_before - uptime
    except Exception:
        pass
    with lock:
        if state["kernel_start"] is None and kernel_start is not None:
            state["kernel_host_before"] = host_before
            state["kernel_uptime"] = uptime
            state["kernel_start"] = kernel_start
        if slot:
            state["slot_suffix"] = slot[-1].strip()
        if uname:
            state["uname"] = uname[-1].strip()
        if uid:
            state["uid"] = uid[-1].strip()
        if reason:
            state["bootreason"] = reason[-1].strip()
    log(
        f"{tag}_SNAPSHOT host_before={iso(host_before)} "
        f"host_after={iso(host_after)} proc_uptime={uptime} "
        f"kernel_start={iso(kernel_start) if kernel_start is not None else 'NA'} "
        f"slot={slot[-1].strip() if slot else 'NA'} "
        f"uname={uname[-1].strip() if uname else 'NA'} "
        f"uid={uid[-1].strip() if uid else 'NA'} boot_completed={bc} "
        f"bootreason={reason[-1].strip() if reason else 'NA'}"
    )
    t_ok = state.get("t_booting_okay")
    if t_ok is not None and kernel_start is not None:
        total = kernel_start - t_ok
        log(
            f"RETURNED_ANDROID_KERNEL_START={iso(kernel_start)} "
            f"PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START={total:.3f} "
            f"(primary PANIC_ENTRY timing product; no overhead model applied)"
        )


def _grade(verdict: str) -> str:
    if verdict == "STRONG":
        return "PROVEN"
    if verdict == "SUPPORTED":
        return "STRONGLY_SUPPORTED"
    return "NOT_PROVEN"


def emit_stage_claims(emit, verdict: dict, stage: str) -> None:
    g = _grade(verdict["verdict"])
    emit("SUMMARY C6_PARSE_ARGS_COMPLETE_REACHED=PROVEN")
    emit("SUMMARY CALIBRATE_DELAY_COMPLETE_REACHED=PROVEN")
    emit("SUMMARY PANIC_PARAMETER_PARSED_BY_RUNNING_KERNEL=PROVEN")
    emit("SUMMARY RDINIT_PARAMETER_PARSED_BY_RUNNING_KERNEL=PROVEN")
    emit("SUMMARY PANIC_MDELAY_CALIBRATION_READY=YES")
    if verdict["verdict"] == "STRONG":
        emit(f"SUMMARY PANIC_ENTRY_REACHED={g}")
        emit(f"SUMMARY LINUX_PANIC_FUNCTION_INVOKED={g}")
    elif verdict["verdict"] == "SUPPORTED":
        emit("SUMMARY PANIC_ENTRY_REACHED=STRONGLY_SUPPORTED")
        emit("SUMMARY LINUX_PANIC_FUNCTION_INVOKED=STRONGLY_SUPPORTED")
    else:
        emit("SUMMARY PANIC_ENTRY_REACHED=NOT_PROVEN")
        emit("SUMMARY LINUX_PANIC_FUNCTION_INVOKED=NOT_PROVEN")
        emit("SUMMARY PANIC_ENTRY_SIGNATURE_NOT_OBSERVED=YES")
        emit("SUMMARY NO_LINUX_PANIC=NOT_LICENSED")
        emit("SUMMARY PANIC_NOT_REACHED=NOT_LICENSED")
    emit("SUMMARY PANIC_TIMEOUT_BRANCH_REACHED=NOT_PROVEN")
    emit("SUMMARY PANIC_TIMEOUT_WAIT_LOOP_REACHED=NOT_PROVEN")
    emit("SUMMARY EMERGENCY_RESTART_REACHED=NOT_PROVEN")
    emit("SUMMARY PANIC30_SHOULD_HAVE_SHIFTED=NOT_LICENSED")
    emit("SUMMARY E2_EARLY_MAINLINE_BOOT=NOT_PROVEN")
    emit("SUMMARY R5_NORMAL_START_KERNEL_BODY=NOT_PROVEN")
    emit("SUMMARY R6=NOT_PROVEN")
    emit("SUMMARY R7=NOT_PROVEN")


def emit_summary(emit=log, final_usb=None, final_fastboot=None,
                 final_adb=None, st: dict = None) -> None:
    if st is None:
        with lock:
            st = dict(state)
    stage = selected_stage()
    emit(f"SUMMARY T_COMMAND_START={fmt_t(st.get('t_command_start'))}")
    emit(f"SUMMARY T_SENDING_OKAY={fmt_t(st.get('t_sending_okay'))}")
    emit(f"SUMMARY T_BOOTING_OKAY={fmt_t(st.get('t_booting_okay'))}")
    emit(f"SUMMARY T_FASTBOOT_DISAPPEAR={fmt_t(st.get('t_disappear'))}")
    emit(f"SUMMARY T_USB_NONE={fmt_t(st.get('t_usb_none'))}")
    emit(f"SUMMARY T_USB_FIRST_REENUM={fmt_t(st.get('t_usb_first_reenum'))}")
    emit(f"SUMMARY T_ADB_FIRST_SEEN={fmt_t(st.get('t_adb_first_seen'))}")
    emit(f"SUMMARY T_BOOT_COMPLETED={fmt_t(st.get('t_boot_completed'))}")
    emit(f"SUMMARY RETURNED_ANDROID_KERNEL_START={fmt_t(st.get('kernel_start'))}")
    emit(f"SUMMARY kernel_host_before={fmt_t(st.get('kernel_host_before'))} "
         f"proc_uptime={st.get('kernel_uptime')}")
    emit(f"SUMMARY FASTBOOT_TRANSIENT={bool(st.get('transient_fastboot'))} "
         f"t={fmt_t(st.get('t_fastboot_transient'))}")
    emit(f"SUMMARY P1B_AUTOMATIC_FASTBOOT_RETURN={bool(st.get('stable_fastboot'))} "
         f"t={fmt_t(st.get('t_fastboot_stable'))}")
    kind = recovery_kind(st)
    emit(f"SUMMARY RECOVERY_KIND={kind}")
    emit("SUMMARY PANIC_ENTRY_DIAGNOSTIC_ONLY=YES "
         "PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    emit("SUMMARY PANIC_ENTRY_NOT_REACHED_LICENSE=NO")
    emit(f"SUMMARY PANIC_ENTRY_SELECTED_STAGE={stage}")
    total = panic_entry_total(st.get("kernel_start"), st.get("t_booting_okay"))
    if total is not None:
        dcd = panic_entry_minus_c_delay(total)
        est = panic_entry_programmed_estimate(total)
        verdict = panic_entry_reachability(total, kind)
        emit(f"SUMMARY PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START={total:.3f}")
        emit(f"SUMMARY C_DELAY_REFERENCE_TOTAL={C_DELAY_REFERENCE_TOTAL_S:.3f} "
             f"(AUXILIARY predecessor; NOT a plus-minus window gate)")
        emit(f"SUMMARY PANIC_ENTRY_MINUS_C_DELAY={dcd:+.3f} "
             f"(matched subclass [{PANIC_ENTRY_MATCHED_MINUS_C_DELAY_LO_S:+.1f},"
             f"{PANIC_ENTRY_MATCHED_MINUS_C_DELAY_HI_S:+.1f}]s; NOT a fail gate)")
        emit(f"SUMMARY PANIC_ENTRY_MATCHED_SUBCLASS="
             f"{'YES' if panic_entry_matched_subclass(total) else 'NO'} "
             f"name={verdict.get('subclass')}")
        emit(f"SUMMARY T4_REFERENCE_TOTAL={T4_REFERENCE_TOTAL_S:.3f} "
             f"(SECONDARY historical)")
        emit(f"SUMMARY T3_REFERENCE_TOTAL={T3_REFERENCE_TOTAL_S:.3f} "
             f"(SECONDARY historical)")
        emit(f"SUMMARY T2_REFERENCE_TOTAL={T2_REFERENCE_TOTAL_S:.3f} "
             f"(SECONDARY historical)")
        emit(f"SUMMARY T1_REFERENCE_TOTAL={T1_REFERENCE_TOTAL_S:.3f} "
             f"(SECONDARY historical)")
        emit(f"SUMMARY T0_REFERENCE_TOTAL={T0_REFERENCE_TOTAL_S:.3f} "
             f"(SECONDARY historical)")
        emit(f"SUMMARY PANIC_ENTRY_EARLY_RETURN_CLASS_MATCH="
             f"{'YES' if total < PANIC_ENTRY_EARLY_RETURN_CLASS_LIMIT_S else 'NO'} "
             f"(limit {PANIC_ENTRY_EARLY_RETURN_CLASS_LIMIT_S}s)")
        emit(f"SUMMARY PANIC_ENTRY_PROGRAMMED_ESTIMATE={est:.3f} "
             f"(SECONDARY cross-check; ref overhead {P0_REF_OVERHEAD_S}s; "
             f"expected ~{PANIC_ENTRY_PROGRAMMED_S}s; NOT the primary reference)")
        emit(f"SUMMARY PANIC_ENTRY_REACHABILITY_SIGNATURE={verdict['verdict']} "
             f"case={verdict['case']} subclass={verdict.get('subclass')} "
             f"reason={verdict['reason']}")
        if verdict["verdict"] in ("STRONG", "SUPPORTED"):
            emit_stage_claims(emit, verdict, stage)
            emit(f"SUMMARY PANIC_ENTRY_NEXT_STEP={verdict['next']}")
        else:
            emit("SUMMARY PANIC_ENTRY_SIGNATURE_NOT_OBSERVED=YES "
                 "PANIC_ENTRY_NOT_REACHED_LICENSE=NO "
                 "NO_LINUX_PANIC=NOT_LICENSED "
                 "(a negative never concludes no Linux panic; "
                 "PANIC_ENTRY_FAILURE_ISOLATION_CI required)")
            emit_stage_claims(emit, verdict, stage)
            emit(f"SUMMARY PANIC_ENTRY_NEXT_STEP={verdict['next']}")
    else:
        verdict = panic_entry_reachability(None, kind)
        emit("SUMMARY PANIC_ENTRY_BOOTING_TO_RETURNED_KERNEL_START=NA")
        emit("SUMMARY PANIC_ENTRY_SIGNATURE_NOT_OBSERVED=YES "
             "PANIC_ENTRY_NOT_REACHED_LICENSE=NO "
             "NO_LINUX_PANIC=NOT_LICENSED (no timing product)")
        emit_stage_claims(emit, verdict, stage)
        emit(f"SUMMARY PANIC_ENTRY_NEXT_STEP={verdict['next']}")
    t_st = st.get("t_fastboot_stable")
    t_ok = st.get("t_booting_okay")
    if t_ok is not None and t_st is not None:
        emit(f"ELAPSED_BOOTING_TO_STABLE_FASTBOOT={t_st - t_ok:.3f}")
        emit("PANIC_ENTRY_STABLE_FASTBOOT_OBSERVED=YES (Case E record only; second "
             "boot and next round forbidden)")
    t_adb = st.get("t_adb_first_seen")
    t_bc = st.get("t_boot_completed")
    if t_ok is not None and t_adb is not None:
        emit(f"ELAPSED_BOOTING_TO_ADB={t_adb - t_ok:.3f}")
    if st.get("t_disappear") is not None and t_adb is not None:
        emit(f"ELAPSED_DISAPPEAR_TO_ADB={t_adb - st['t_disappear']:.3f}")
    if t_ok is not None and t_bc is not None:
        emit(f"ELAPSED_BOOTING_TO_BOOT_COMPLETED={t_bc - t_ok:.3f}")
    emit(f"FINAL_USB={final_usb if final_usb is not None else usb_fmt(usb_snapshot())}")
    fb_disp = fastboot_present() if final_fastboot is None else final_fastboot
    adb_disp = adb_present() if final_adb is None else final_adb
    emit(f"FINAL_FASTBOOT={fb_disp} FINAL_ADB={adb_disp}")
    emit(f"FINAL_SLOT={st.get('slot_suffix')} UNAME={st.get('uname')} "
         f"UID={st.get('uid')} BOOTREASON={st.get('bootreason')}")
    if st.get("no_return_window_expired"):
        emit("PANIC_ENTRY_NO_RETURN_CASE_F=YES "
             "MANUAL_RECOVERY_ELAPSED_EXCLUDED_FROM_TIMING=YES "
             "(Case F; next PANIC_ENTRY_FAILURE_ISOLATION_CI)")


def usb_poller() -> None:
    last = None
    while not stop.is_set():
        usb = usb_snapshot()
        ts = time.time()
        with lock:
            t_ok = state["t_booting_okay"]
            t_dis = state["t_disappear"]
            state["usb"] = usb
        if t_ok is not None and last is not None and usb != last:
            if not usb:
                if state["t_usb_none"] is None:
                    with lock:
                        if state["t_usb_none"] is None:
                            state["t_usb_none"] = ts
                    log("T_USB_NONE", ts)
                else:
                    log("USB_CHANGE usb=NONE", ts)
            else:
                if t_dis is not None and state["t_usb_first_reenum"] is None:
                    with lock:
                        if state["t_usb_first_reenum"] is None:
                            state["t_usb_first_reenum"] = ts
                    log(f"T_USB_FIRST_REENUM usb={usb_fmt(usb)}", ts)
                else:
                    log(f"USB_CHANGE usb={usb_fmt(usb)} prev={usb_fmt(last)}", ts)
        last = usb
        time.sleep(0.25)


def poller() -> None:
    saw_fb = True
    fb_stable_since = None
    captured_adb = False
    while not stop.is_set():
        fb = fastboot_present()
        adb = adb_present()
        ts = time.time()
        with lock:
            t_ok = state["t_booting_okay"]
            t_dis = state["t_disappear"]
            usb = state["usb"]
            stable = state["stable_fastboot"]
            transient = state["transient_fastboot"]
        if t_ok is not None and saw_fb and not fb and t_dis is None:
            with lock:
                if state["t_disappear"] is None:
                    state["t_disappear"] = ts
            log("T_FASTBOOT_DISAPPEAR", ts)
            saw_fb = False
            fb_stable_since = None
        if t_ok is not None and fb:
            saw_fb = True
            if t_dis is not None:
                if usb_has_fastboot(usb):
                    if fb_stable_since is None:
                        fb_stable_since = ts
                        log("FASTBOOT_PRESENT_WITH_USB_D00D_START", ts)
                    elif ts - fb_stable_since >= FASTBOOT_STABLE_SECS and not stable:
                        with lock:
                            state["stable_fastboot"] = True
                            if state["t_fastboot_stable"] is None:
                                state["t_fastboot_stable"] = ts
                        log("P1B_AUTOMATIC_FASTBOOT_RETURN=YES STABLE", ts)
                else:
                    fb_stable_since = None
                    if not transient:
                        with lock:
                            state["transient_fastboot"] = True
                            if state["t_fastboot_transient"] is None:
                                state["t_fastboot_transient"] = ts
                        log(f"FASTBOOT_TRANSIENT_ENUMERATION_ONLY=YES "
                            f"usb={usb_fmt(usb)}", ts)
        else:
            fb_stable_since = None
        if t_ok is not None and adb and state["t_adb_first_seen"] is None:
            with lock:
                if state["t_adb_first_seen"] is None:
                    state["t_adb_first_seen"] = ts
            log("T_ADB_FIRST_SEEN", ts)
            if not captured_adb:
                captured_adb = True
                capture_android_snapshot("ADB_FIRST")
        if adb:
            bc = boot_completed()
            if bc == "1" and state["t_boot_completed"] is None:
                with lock:
                    if state["t_boot_completed"] is None:
                        state["t_boot_completed"] = ts
                log("T_BOOT_COMPLETED", ts)
                capture_android_snapshot("BOOT_COMPLETED")
        with lock:
            state["fastboot"] = fb
            state["adb"] = adb
        time.sleep(POLL)


def sha256_file(path: str) -> tuple:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return os.stat(path).st_size, h.hexdigest()


def verify_identity(size: int, digest: str, expected_sha: str,
                    forbidden: dict, expected_payload_sha: str = "") -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha or ""):
        raise SystemExit("R3_PANIC_ENTRY_SHA256 missing or not a full sha256 hex digest")
    if expected_payload_sha and not re.fullmatch(r"[0-9a-f]{64}",
                                                 expected_payload_sha):
        raise SystemExit(
            "R3_PANIC_ENTRY_PAYLOAD_SHA256 missing or not a full sha256 hex digest")
    if size != EXPECTED_SIZE or digest != expected_sha:
        raise SystemExit(f"ARTIFACT_IDENTITY_FAIL size={size} sha={digest}")
    for name, bad in forbidden.items():
        if digest == bad:
            raise SystemExit(
                f"PANIC_ENTRY_OBSERVER_MISBOOT_REFUSED digest matches {name} {bad}; "
                "the PANIC_ENTRY observer only accepts the exact PANIC_ENTRY boot")


def identity_ok() -> None:
    if not BOOT_IMG or not os.path.isfile(BOOT_IMG):
        raise SystemExit("R3_PANIC_ENTRY_BOOT_IMG missing or not a file")
    size, digest = sha256_file(BOOT_IMG)
    verify_identity(size, digest, EXPECTED_SHA, FORBIDDEN_SHAS,
                    EXPECTED_PAYLOAD_SHA)
    log(f"ARTIFACT_IDENTITY MATCH size={size} sha256={digest}")


def getvar(name: str) -> str:
    out = run([FASTBOOT, "getvar", name], timeout=3.0)
    m = re.search(rf"^{re.escape(name)}:\s*(.*)$", out, re.M)
    return (m.group(1).strip() if m else "").split("\n")[0]


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("observer runs only under CI (GITHUB_ACTIONS=true)")
    identity_ok()
    stage = selected_stage()
    if not fastboot_present():
        log("FAIL: fastboot not present")
        return 2
    vals = {
        "product": getvar("product"),
        "unlocked": getvar("unlocked"),
        "current-slot": getvar("current-slot"),
        "snapshot-update-status": getvar("snapshot-update-status"),
        "battery-soc-ok": getvar("battery-soc-ok"),
        "battery-voltage": getvar("battery-voltage"),
        "max-download-size": getvar("max-download-size"),
        "slot-retry-count:a": getvar("slot-retry-count:a"),
        "slot-unbootable:a": getvar("slot-unbootable:a"),
        "slot-successful:a": getvar("slot-successful:a"),
        "slot-retry-count:b": getvar("slot-retry-count:b"),
        "slot-unbootable:b": getvar("slot-unbootable:b"),
        "slot-successful:b": getvar("slot-successful:b"),
    }
    for k, v in vals.items():
        log(f"PREFLIGHT {k}={v}")
    if vals["product"] != "thyme" or vals["unlocked"] != "yes" or \
            vals["current-slot"] != "a":
        log("STOP: preflight mismatch; no experimental boot")
        return 3
    if vals["snapshot-update-status"] not in ("none", ""):
        log("STOP: snapshot-update-status not none")
        return 3
    if vals["battery-soc-ok"] not in ("yes", ""):
        log("STOP: battery not soc-ok")
        return 3

    print(
        "\nR3 P1B PANIC_ENTRY-8 LINUX panic() ENTRY CHECKPOINT\n"
        "ACTIVE SLOT:\nA\n"
        "PARTITION WRITES:\n0\n"
        "SET_ACTIVE:\nNO\n"
        "SLOT_A_WRITTEN:\nNO\n"
        "EXPERIMENTAL BOOTS:\n1\n"
        "SECOND BOOT:\nFORBIDDEN\n"
        "FASTBOOT_BOOT_ONLY:\nYES\n"
        f"SELECTED STAGE:\n{stage}\n"
        "CHECKPOINT:\\ncanonical panic() ENTRY (INLINE; all prior T0-T4/C_DELAY "
        "probes removed; FIX8 normal path until panic is invoked)\\n"
        "DELAY:\\n8s CNTPCT register-only (independent of panic_timeout)\\n"
        "RESET:\\nPSCI SYSTEM_RESET 0x84000009 smc, wfe fail-closed\\n"
        "RUNTIME SEMANTIC DELTA:\\n"
        "PANIC_ENTRY_CHECKPOINT_ONLY\\n"
        "PANIC_ENTRY_DIAGNOSTIC_ONLY:\\nYES (PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE=NO; a "
        "STRONG PANIC_ENTRY proves canonical panic() invoked; panic body / "
        "timeout branch / mdelay loop / emergency_restart stay NOT_PROVEN)\\n"
        "PRIMARY TIMING:\\nAUTOMATIC_ANDROID_RETURN + PANIC_ENTRY_TOTAL < 20s "
        "(distinctive early vs natural 23-26s; NOT a C_DELAY plus-minus window)\\n"
        "MATCHED SUBCLASS:\\n-0.5s <= PANIC_ENTRY_MINUS_C_DELAY <= +3.0s "
        "(auxiliary; >3s but <20s remains STRONG)\\n"
        "SUPPORTED:\\n20s <= TOTAL < 23s\\n"
        "SECONDARY:\\nPANIC_ENTRY_PROGRAMMED_ESTIMATE = PANIC_ENTRY_TOTAL - 6.1445\\n"
        "PANIC_ENTRY_NOT_REACHED_LICENSE:\\nNO (always; never NO_LINUX_PANIC)\\n"
        "COMMAND: fastboot boot <exact-PANIC_ENTRY-boot>\\n"
        "FORBIDDEN: flash erase set_active second boot C_DELAY T4 T3 T2 T1 T0 FIX8 PANIC30 FIX24 M5N\\n",

        flush=True,
    )

    ut = threading.Thread(target=usb_poller, daemon=True)
    pt = threading.Thread(target=poller, daemon=True)
    ut.start()
    pt.start()
    time.sleep(0.4)
    usb_before = state["usb"] or ()
    log(f"USB_BEFORE_BOOT usb={usb_fmt(usb_before)}")

    cmd = [FASTBOOT, "boot", BOOT_IMG]
    joined = " ".join(cmd)
    low_parts = [p.lower() for p in cmd]
    if any(tok in joined.lower() for tok in (
            "erase", "format", "set_active", "oem unlock", "flashing")):
        raise SystemExit("refusing forbidden token")
    if "flash" in low_parts:
        raise SystemExit("refusing flash")
    if cmd[1] != "boot":
        raise SystemExit("only fastboot boot is allowed")

    ts0 = time.time()
    with lock:
        state["t_command_start"] = ts0
    log("T_COMMAND_START", ts0)
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    sending_ok = False
    booting_ok = False
    fail = False
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip("\n")
        ts = time.time()
        log(f"FASTBOOT_OUT {line}", ts)
        low = line.lower()
        if "sending" in low and "okay" in low:
            sending_ok = True
            with lock:
                if state["t_sending_okay"] is None:
                    state["t_sending_okay"] = ts
            log("T_SENDING_OKAY", ts)
        if "booting" in low and "okay" in low:
            booting_ok = True
            with lock:
                state["t_booting_okay"] = ts
            log("T_BOOTING_OKAY", ts)
        if "fail" in low:
            fail = True
            log("FASTBOOT_FAIL_LINE", ts)
    rc = p.wait()
    log(f"FASTBOOT_BOOT_EXIT rc={rc} sending_ok={sending_ok} "
        f"booting_ok={booting_ok} fail={fail}")
    if fail or rc != 0 or not booting_ok:
        log("PANIC_ENTRY_BOOT_NOT_ACCEPTED (Case E-class stop: no image swap retry)")
        stop.set()
        emit_summary(final_usb=usb_fmt(state["usb"] or ()),
                     final_fastboot=False, final_adb=False, st=dict(state))
        return 4

    with lock:
        t0 = state["t_booting_okay"] or time.time()
    while True:
        now = time.time()
        elapsed = now - t0
        with lock:
            t_adb = state["t_adb_first_seen"]
            t_bc = state["t_boot_completed"]
            t_st = state["t_fastboot_stable"]
        if t_bc is not None:
            log("ANDROID_BOOT_COMPLETED_OBSERVED")
            time.sleep(0.5)
            break
        if t_adb is not None and (now - t_adb) >= ADB_EXTEND:
            log("ADB_EXTEND_TIMEOUT")
            break
        if t_adb is None and t_st is not None:
            log("STABLE_FASTBOOT_STOP_NO_ADB (Case E record)")
            break
        if t_adb is None and elapsed >= PRIMARY_WINDOW:
            with lock:
                state["no_return_window_expired"] = True
            log("OBSERVER_STOP_120S_NO_ANDROID_A_NO_STABLE_FASTBOOT")
            log("ENTER_MANUAL_RECOVERY_POLICY elapsed excluded from T4 timing "
                "(Case F; next PANIC_ENTRY_FAILURE_ISOLATION_CI)")
            break
        time.sleep(0.2)

    stop.set()
    time.sleep(0.4)
    emit_summary(final_usb=usb_fmt(state["usb"] or ()), st=dict(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
