#!/usr/bin/env python3
"""R3 load-alignment probe host observer. One fastboot boot, zero partition writes.

Same methodology as the P0 observers (same fastboot stdout line timing), so the
P0 overhead reference 6.1445s stays valid. Primary window 75s. Decoder is
preregistered: buckets 8/24 only; 8 -> ALIGNMENT_MATCH (S mod 2MiB == 0x80000),
24 -> ALIGNMENT_MISMATCH (S is never guessed); STRONG +-0.75s, SUPPORTED
+-1.5s, else INCONCLUSIVE.

Artifact identity comes from the environment:
  R3_PROBE_BOOT_IMG  path to the exact thyme-r3-load-alignment-probe.img
  R3_PROBE_SHA256    expected SHA256 recorded from the private GHA run
Missing or mismatching identity is a hard stop before any boot.
FASTBOOT_BOOT_ONLY=YES, SECOND_BOOT_FORBIDDEN=YES: no flash, no erase,
no set_active, no second probe boot.
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

PROBE = os.environ.get("R3_PROBE_BOOT_IMG", "")
EXPECTED_SHA = os.environ.get("R3_PROBE_SHA256", "")
EXPECTED_SIZE = 35110912
POLL = 0.10
PRIMARY_WINDOW = 75.0
ADB_EXTEND = 120.0
FASTBOOT_STABLE_SECS = 3.0
FASTBOOT = os.environ.get("FASTBOOT", "fastboot")
ADB = os.environ.get("ADB", "adb")
P0_OVERHEAD_REF = 6.1445
LAP_BUCKETS = [8, 24]
ALIGNMENT_BY_DELAY = {8: "ALIGNMENT_MATCH", 24: "ALIGNMENT_MISMATCH"}
STRONG_TOL = 0.75
SUPPORTED_TOL = 1.5

lock = threading.Lock()
events: list[tuple[float, str, str]] = []
stop = threading.Event()
state = {
    "fastboot": False,
    "adb": False,
    "usb": (),
    "t_command_start": None,
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
    "expected_probe_reset_not_observed": False,
    "kernel_host_before": None,
    "kernel_uptime": None,
    "kernel_start": None,
    "slot_suffix": None,
    "uname": None,
    "uid": None,
    "bootreason": None,
}


def iso(ts: float | None = None) -> str:
    t = datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(t.microsecond / 1000):03d}Z"


def fmt_t(value) -> str:
    return iso(value) if value else "NA"


def log(msg: str, ts: float | None = None) -> None:
    ts = time.time() if ts is None else ts
    line = f"{iso(ts)}  {ts:.3f}  {msg}"
    with lock:
        events.append((ts, iso(ts), msg))
    print(line, flush=True)


def run(cmd: list[str], timeout: float = 2.0) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"ERR:{e}"


def usb_snapshot() -> tuple[tuple[int, int, str], ...]:
    out = run(["ioreg", "-p", "IOUSB", "-w0", "-l"], timeout=3.0)
    devices = []
    cur: dict = {}
    for line in out.splitlines():
        if "+-o " in line:
            if cur.get("vid") is not None:
                devices.append(cur)
            cur = {"name": line.split("+-o", 1)[1].strip().split()[0], "vid": None, "pid": None, "serial": ""}
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
        if vid in (0x18D1, 0x2717, 0x05C6, 0x12D1) or pid in (0xD00D, 0x4EE7, 0x4EE1, 0x4EE2, 0x4EE5):
            out_t.append((vid, pid, d.get("serial") or d.get("name") or ""))
    return tuple(sorted(out_t))


def usb_fmt(snap: tuple[tuple[int, int, str], ...]) -> str:
    if not snap:
        return "NONE"
    return ",".join(f"{v:04x}:{p:04x}" for v, p, _s in snap)


def usb_has_fastboot(snap: tuple[tuple[int, int, str], ...]) -> bool:
    return any(vid == 0x18D1 and pid == 0xD00D for vid, pid, _s in snap)


def fastboot_present() -> bool:
    out = run([FASTBOOT, "devices"], timeout=2.0)
    return bool(re.search(r"\sfastboot\s*$", out, re.M)) or ("\tfastboot" in out)


def adb_present() -> bool:
    out = run([ADB, "devices"], timeout=2.0)
    return bool(re.search(r"\tdevice\s*$", out, re.M))


def boot_completed() -> str | None:
    out = run([ADB, "shell", "getprop", "sys.boot_completed"], timeout=3.0).strip()
    if not out or out.startswith("ERR:"):
        return None
    return out.splitlines()[-1].strip()


def capture_android_snapshot(tag: str) -> None:
    host_before = time.time()
    up_out = run([ADB, "shell", "cat", "/proc/uptime"], timeout=3.0)
    host_after = time.time()
    slot = run([ADB, "shell", "getprop", "ro.boot.slot_suffix"], timeout=3.0).strip().splitlines()
    uname = run([ADB, "shell", "uname", "-a"], timeout=3.0).strip().splitlines()
    uid = run([ADB, "shell", "su", "-c", "id"], timeout=5.0).strip().splitlines()
    bc = boot_completed()
    reason = run([ADB, "shell", "getprop", "ro.boot.bootreason"], timeout=3.0).strip().splitlines()
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
        f"{tag}_SNAPSHOT host_before={iso(host_before)} host_after={iso(host_after)} "
        f"proc_uptime={uptime} kernel_start={iso(kernel_start) if kernel_start is not None else 'NA'} "
        f"slot={slot[-1].strip() if slot else 'NA'} uname={uname[-1].strip() if uname else 'NA'} "
        f"uid={uid[-1].strip() if uid else 'NA'} boot_completed={bc} "
        f"bootreason={reason[-1].strip() if reason else 'NA'}"
    )
    t_ok = state.get("t_booting_okay")
    if t_ok is not None and kernel_start is not None:
        total = kernel_start - t_ok
        estimate = total - P0_OVERHEAD_REF
        log(
            f"{tag}_BOOTING_TO_KERNEL_START={total:.3f} "
            f"OBSERVED_TOTAL={total:.3f} P0_OVERHEAD_REF={P0_OVERHEAD_REF:.4f} "
            f"OBSERVED_PROGRAMMED_DELAY={estimate:.3f}"
        )


def decode_alignment(total: float | None, emit=log, st: dict | None = None) -> None:
    if st is None:
        with lock:
            st = dict(state)
    if total is None:
        if st.get("expected_probe_reset_not_observed"):
            emit("SUMMARY DECODE=NO_KERNEL_START EXPECTED_PROBE_RESET_NOT_OBSERVED=YES")
        else:
            emit("SUMMARY DECODE=NO_KERNEL_START")
        return
    estimate = total - P0_OVERHEAD_REF
    nearest = min(LAP_BUCKETS, key=lambda b: abs(estimate - b))
    error = estimate - nearest
    if abs(error) <= STRONG_TOL:
        verdict = "STRONG"
    elif abs(error) <= SUPPORTED_TOL:
        verdict = "SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"
    emit(f"SUMMARY OBSERVED_TOTAL={total:.3f}")
    emit(f"SUMMARY OBSERVED_PROGRAMMED_DELAY={estimate:.3f}")
    emit(f"SUMMARY NEAREST_BUCKET={nearest}s")
    emit(f"SUMMARY TIMING_ERROR={error:+.3f}")
    emit(f"SUMMARY VERDICT={verdict}")
    if verdict == "INCONCLUSIVE":
        emit("SUMMARY R3_LOAD_ALIGNMENT_PROBE_INCONCLUSIVE")
        return
    label = ALIGNMENT_BY_DELAY[nearest]
    emit(f"SUMMARY DECODED_ALIGNMENT={label}")
    if nearest == 8:
        emit("SUMMARY R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M=0x80000")
        emit("SUMMARY MAINLINE_IMAGE_ALIGNMENT_CONTRACT=SUPPORTED_BY_PROBE")
    else:
        emit("SUMMARY R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M_MISMATCH=YES")
        emit("SUMMARY S_NOT_GUESSED=YES")


def recovery_kind(st: dict | None = None) -> str:
    if st is None:
        with lock:
            st = dict(state)
    if st.get("t_boot_completed") is not None:
        return "AUTOMATIC_ANDROID_RETURN"
    if st.get("t_fastboot_stable") is not None:
        return "AUTOMATIC_STABLE_FASTBOOT_RETURN"
    if st.get("expected_probe_reset_not_observed"):
        return "MANUAL_RECOVERY_OR_NO_RETURN"
    return "UNKNOWN"


def emit_summary(emit=log, final_usb: str | None = None, final_fastboot=None,
                 final_adb=None, st: dict | None = None) -> None:
    if st is None:
        with lock:
            st = dict(state)
    usb = st.get("usb") or ()
    emit(f"SUMMARY T_COMMAND_START={fmt_t(st.get('t_command_start'))}")
    emit(f"SUMMARY T_BOOTING_OKAY={fmt_t(st.get('t_booting_okay'))}")
    emit(f"SUMMARY T_FASTBOOT_DISAPPEAR={fmt_t(st.get('t_disappear'))}")
    emit(f"SUMMARY T_USB_NONE={fmt_t(st.get('t_usb_none'))}")
    emit(f"SUMMARY T_USB_FIRST_REENUM={fmt_t(st.get('t_usb_first_reenum'))}")
    emit(f"SUMMARY T_ADB_FIRST_SEEN={fmt_t(st.get('t_adb_first_seen'))}")
    emit(f"SUMMARY T_BOOT_COMPLETED={fmt_t(st.get('t_boot_completed'))}")
    emit(f"SUMMARY FASTBOOT_TRANSIENT={bool(st.get('transient_fastboot'))} "
         f"t={fmt_t(st.get('t_fastboot_transient'))}")
    emit(f"SUMMARY AUTOMATIC_FASTBOOT_AFTER_PROBE={bool(st.get('stable_fastboot'))} "
         f"t={fmt_t(st.get('t_fastboot_stable'))}")
    emit(f"SUMMARY RECOVERY_KIND={recovery_kind(st)}")
    kh = st.get("kernel_host_before")
    ku = st.get("kernel_uptime")
    ks = st.get("kernel_start")
    emit(f"SUMMARY kernel_host_before={fmt_t(kh)} proc_uptime={ku}")
    emit(f"SUMMARY kernel_start={fmt_t(ks)}")
    t_ok = st.get("t_booting_okay")
    total = (ks - t_ok) if (t_ok is not None and ks is not None) else None
    decode_alignment(total, emit, st)
    t_adb = st.get("t_adb_first_seen")
    t_bc = st.get("t_boot_completed")
    t_st = st.get("t_fastboot_stable")
    if t_ok is not None and t_adb is not None:
        emit(f"ELAPSED_BOOTING_TO_ADB={t_adb - t_ok:.3f}")
    if st.get("t_disappear") is not None and t_adb is not None:
        emit(f"ELAPSED_DISAPPEAR_TO_ADB={t_adb - st['t_disappear']:.3f}")
    if t_ok is not None and t_bc is not None:
        emit(f"ELAPSED_BOOTING_TO_BOOT_COMPLETED={t_bc - t_ok:.3f}")
    if t_ok is not None and t_st is not None:
        emit(f"ELAPSED_BOOTING_TO_STABLE_FASTBOOT={t_st - t_ok:.3f}")
    emit(f"FINAL_USB={final_usb if final_usb is not None else usb_fmt(usb_snapshot())}")
    fb_disp = fastboot_present() if final_fastboot is None else final_fastboot
    adb_disp = adb_present() if final_adb is None else final_adb
    emit(f"FINAL_FASTBOOT={fb_disp} FINAL_ADB={adb_disp}")
    emit(f"FINAL_SLOT={st.get('slot_suffix')} UNAME={st.get('uname')} "
         f"UID={st.get('uid')} BOOTREASON={st.get('bootreason')}")


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
                        log("AUTOMATIC_FASTBOOT_AFTER_PROBE=YES STABLE", ts)
                else:
                    fb_stable_since = None
                    if not transient:
                        with lock:
                            state["transient_fastboot"] = True
                            if state["t_fastboot_transient"] is None:
                                state["t_fastboot_transient"] = ts
                        log(
                            f"FASTBOOT_TRANSIENT_ENUMERATION_ONLY=YES usb={usb_fmt(usb)}",
                            ts,
                        )
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


def identity_ok() -> None:
    if not PROBE or not os.path.isfile(PROBE):
        raise SystemExit("R3_PROBE_BOOT_IMG missing or not a file")
    if not re.fullmatch(r"[0-9a-f]{64}", EXPECTED_SHA or ""):
        raise SystemExit("R3_PROBE_SHA256 missing or not a sha256 hex digest")
    st = os.stat(PROBE)
    h = hashlib.sha256()
    with open(PROBE, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if st.st_size != EXPECTED_SIZE or digest != EXPECTED_SHA:
        raise SystemExit(f"ARTIFACT_IDENTITY_FAIL size={st.st_size} sha={digest}")
    log(f"ARTIFACT_IDENTITY MATCH size={st.st_size} sha256={digest}")


def getvar(name: str) -> str:
    out = run([FASTBOOT, "getvar", name], timeout=3.0)
    m = re.search(rf"^{re.escape(name)}:\s*(.*)$", out, re.M)
    return (m.group(1).strip() if m else "").split("\n")[0]


def main() -> int:
    identity_ok()
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
        "slot-retry-count:a": getvar("slot-retry-count:a"),
        "slot-unbootable:a": getvar("slot-unbootable:a"),
        "slot-successful:a": getvar("slot-successful:a"),
        "slot-retry-count:b": getvar("slot-retry-count:b"),
        "slot-unbootable:b": getvar("slot-unbootable:b"),
        "slot-successful:b": getvar("slot-successful:b"),
    }
    for k, v in vals.items():
        log(f"PREFLIGHT {k}={v}")
    if vals["product"] != "thyme" or vals["unlocked"] != "yes" or vals["current-slot"] != "a":
        log("STOP: preflight mismatch; no experimental boot")
        return 3
    if vals["snapshot-update-status"] not in ("none", ""):
        log("STOP: snapshot-update-status not none")
        return 3
    if vals["battery-soc-ok"] not in ("yes", ""):
        log("STOP: battery not soc-ok")
        return 3

    print(
        "\nR3 LOAD ALIGNMENT PROBE\n"
        "ACTIVE SLOT:\nA\n"
        "PARTITION WRITES:\n0\n"
        "SET_ACTIVE:\nNO\n"
        "EXPERIMENTAL BOOTS:\n1\n"
        "ALIGNMENT ENCODING:\n8/24 seconds (ALIGNMENT_MATCH=8s ALIGNMENT_MISMATCH=24s)\n"
        "PRIMARY DECODER:\nBOOTING_OKAY -> STOCK KERNEL START\n"
        "COMMAND: fastboot boot <exact-probe-boot.img>\n"
        "FORBIDDEN: flash erase set_active second probe boot\n",
        flush=True,
    )

    ut = threading.Thread(target=usb_poller, daemon=True)
    pt = threading.Thread(target=poller, daemon=True)
    ut.start()
    pt.start()
    time.sleep(0.4)
    usb_before = state["usb"] or ()
    log(f"USB_BEFORE_BOOT usb={usb_fmt(usb_before)}")

    cmd = [FASTBOOT, "boot", PROBE]
    joined = " ".join(cmd)
    low_parts = [p.lower() for p in cmd]
    if any(tok in joined.lower() for tok in ("erase", "format", "set_active", "oem unlock", "flashing")):
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
    log(f"FASTBOOT_BOOT_EXIT rc={rc} sending_ok={sending_ok} booting_ok={booting_ok} fail={fail}")
    if fail or rc != 0 or not booting_ok:
        log("R3_LOAD_ALIGNMENT_PROBE_BOOT_NOT_ACCEPTED")
        stop.set()
        emit_summary()
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
            log("STABLE_FASTBOOT_STOP_NO_ADB")
            break
        if t_adb is None and elapsed >= PRIMARY_WINDOW:
            with lock:
                state["expected_probe_reset_not_observed"] = True
            log("EXPECTED_PROBE_RESET_NOT_OBSERVED=YES")
            log("OBSERVER_STOP_75S_NO_ANDROID_A_NO_STABLE_FASTBOOT")
            break
        time.sleep(0.2)

    stop.set()
    time.sleep(0.4)
    emit_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
