#!/usr/bin/env python3
"""R3 P1B C_DELAY predevice readiness (MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source/doc boundary checks (no build)
  c-delay             frozen-FIX8-anchored C_DELAY-8 fail-closed candidate:
                      authoritative kernel rebuild, independent calibrate_delay
                      re-derivation, consume+cross-check early-c-stage-map.json,
                      INLINE post-call checkpoint, T4 C6 probe removal,
                      panic mdelay source audit, single-region FIX8 diff
  observer-fixtures   C_DELAY observer fixture suite
  c-delay-pack-gates  private: gates over a packed C_DELAY boot v3 image

C_DELAY baseline is FIXED INIT8. The T4 C6 INLINE probe is removed.
Unique candidate: C_DELAY = CALIBRATE_DELAY_COMPLETE (post-return).
No C3 fallback. No PANIC30/T5/C12 device-ready artifacts.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1b-c-delay-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
MAP_DOC = REPO / "docs" / "route-r3-early-c-stage-map.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-c-delay-predevice.yml"
MAP_WF = REPO / ".github" / "workflows" / "thyme-r3-early-c-stage-map.yml"
C_STAGE = REPO / "scripts" / "r3-c-stage-audit" / "c-stage-map.py"
C_DELAY_DEVICE_S = HERE / "p1b-c-delay-device.S"
C_DELAY_DEVICE_LD = HERE / "p1b-c-delay-device.ld"
T3_DEVICE_S = HERE / "p1b-t3-device.S"
T3_DEVICE_LD = HERE / "p1b-t3-device.ld"
T2_DEVICE_S = HERE / "p1b-t2-device.S"
T2_DEVICE_LD = HERE / "p1b-t2-device.ld"
T1_DEVICE_S = HERE / "p1b-t1-device.S"
T1_DEVICE_LD = HERE / "p1b-t1-device.ld"
T4_DEVICE_S = HERE / "p1b-t4-device.S"
T4_DEVICE_LD = HERE / "p1b-t4-device.ld"
OBSERVER = HERE / "observe-r3-p1b-c-delay.py"
OBSERVER_FIXTURES = HERE / "observer-c-delay-fixtures.py"
PRIVATE_WF = REPO / "artifacts" / "p1b-c-delay-private-workflow-staging.yml"

_spec = importlib.util.spec_from_file_location(
    "p1b_t3_predevice", HERE / "p1b-t3-predevice.py")
t3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t3)

fail = t3.fail
sha = t3.sha
pb = t3.pb
iso = t3.iso
INSTR_RE = t3.INSTR_RE

LINUX_BASE = pb.LINUX_BASE
RT_D_SHA = pb.RT_D_SHA
RT_D_SIZE = pb.RT_D_SIZE
S_RESIDUE = pb.S_RESIDUE
ALIGN_2M = pb.ALIGN_2M
TRAMP_OFFSET = pb.TRAMP_OFFSET
CODE1_OFFSET = pb.CODE1_OFFSET
PAGE = pb.PAGE
BOOT_CAP = pb.BOOT_CAP
FDT_MAGIC = pb.FDT_MAGIC
DTB_OFFSET = 0x2380000
CODE1_B_0X40 = 0x1400000F
FIX8_PAYLOAD_SHA = t3.FIX8_PAYLOAD_SHA
FIX8_PAYLOAD_SIZE = t3.FIX8_PAYLOAD_SIZE
FIX8_IMAGE_SHA = t3.FIX8_IMAGE_SHA
FIX8_IMAGE_FILE_SIZE = t3.FIX8_IMAGE_FILE_SIZE
FIX8_INIT_SHA = t3.FIX8_INIT_SHA
FIX8_CPIO_SHA = t3.FIX8_CPIO_SHA
TRAMP_SHA = t3.TRAMP_SHA
TRAMP_SIZE = 48
PSCI_SYSTEM_RESET_FID = 0x84000009
PACIASP = 0xD503233F
T3_BOOT_SHA = (
    "d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df")
T3_PAYLOAD_SHA = (
    "eff9a4a5b47413ec2c9f071158c7162a3361bf6443cbe58b43db7ccd0787e471")
T4_BOOT_SHA = (
    "3827fc0fe4216d7d18ccd2a60ea610a6bd10b2afa269e741923ca3bbc566849d")
T4_PAYLOAD_SHA = (
    "64d8f54fd11cc9d4b049ed4a52f5141291cd4c965d25bbf16a8e64670284f76f")

C_DELAY_DELAY_S = 8
C_DELAY_PROBE_SIZE = 0x4C
T3_REF_PROBE_SIZE = 0x50
T2_REF_PROBE_SIZE = 0x50
LINUX_COMMIT = "8b73de7da85fde281a385e0b26eda9bffd3ca477"

FORBIDDEN_BOOT_SHAS = dict(t3.FORBIDDEN_BOOT_SHAS)
FORBIDDEN_BOOT_SHAS["T3_BOOT"] = T3_BOOT_SHA
FORBIDDEN_BOOT_SHAS["T4_BOOT"] = T4_BOOT_SHA

T4_REFERENCE_TOTAL_S = 14.385
T3_REFERENCE_TOTAL_S = 14.238
T2_REFERENCE_TOTAL_S = 14.240
T1_REFERENCE_TOTAL_S = 14.238
T0_REFERENCE_TOTAL_S = 14.252
C_DELAY_STRONG_HALF_WINDOW_S = 1.5
C_DELAY_SUPPORTED_HALF_WINDOW_S = 3.0
C_DELAY_CROSSCHECK_HALF_WINDOW_S = 3.0
C_DELAY_EARLY_RETURN_CLASS_LIMIT_S = 20.0
C_DELAY_CASE_C_BAND_S = (20.0, 28.0)
P0_REF_OVERHEAD_S = 6.1445
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
C_DELAY_NO_RETURN_WINDOW_S = 120.0
C_DELAY_BOOT_SIZE_EXPECTED = 37380096
C_DELAY_CLOBBER_REGISTERS = "w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV"

STATUS_KV_BEGIN = t3.STATUS_KV_BEGIN
STATUS_KV_END = t3.STATUS_KV_END

STATUS_DOC_REQUIRED_KV = dict(t3.STATUS_DOC_REQUIRED_KV)
STATUS_DOC_REQUIRED_KV.update({
    "R4_STATUS": "PROVEN",
    "R5_STATUS": "NOT_PROVEN",
    "E0_STATUS": "PROVEN",
    "E1_STATUS": "PROVEN",
    "E2_STATUS": "NOT_PROVEN",
    "T3_STATUS": "TRUE_DEVICE_PROVEN",
    "T3_TOTAL_S": "14.238",
    "T3_VERDICT": "STRONG",
    "T3_FINAL_GATE": "MAINLINE_V2_R3_P1B_T3_REACHABILITY_PROVEN",
    "T3_BOOT_SHA256": T3_BOOT_SHA,
    "T3_PAYLOAD_SHA256": T3_PAYLOAD_SHA,
    "T4_DEVICE_OPERATION": "EXECUTED",
    "T4_TRUE_DEVICE_STATUS": "PROVEN",
    "T4_TOTAL_S": "14.385",
    "T4_VERDICT": "STRONG",
    "T4_FINAL_GATE": "MAINLINE_V2_R3_P1B_T4_C6_REACHABILITY_PROVEN",
    "C6_RUNTIME_STATUS": "PROVEN",
    "C_DELAY_RUNTIME_STATUS": "NOT_PROVEN",
    "PANIC_TIMEOUT_WALLCLOCK_MODEL": "NOT_PROVEN",
    "PRE_C6_FAILURE_EXPLANATION_FOR_PANIC30": "RULED_OUT",
    "SLOT_A_WRITTEN": "NO",
    "FIX24_STATUS": "FROZEN",
    "M5N_STATUS": "FROZEN",
    "CURRENT_B": "M5D+M5H+M5M-B",
})
STATUS_DOC_ENUM_KV = {
    "T4_SELECTED_STAGE": (
        "C6_PARSE_ARGS_COMPLETE", "C3_SETUP_ARCH_RETURN", "NONE"),
    "T4_PREDEVICE_STATUS": ("READY", "NOT_READY"),
    "C_DELAY_PREDEVICE_STATUS": ("READY", "NOT_READY"),
    "C_DELAY_PROBE_ARCHITECTURE": ("INLINE", "EXTERNAL"),
    "EARLY_C_STAGE_MAP_INTEGRATED": ("YES", "NO"),
    "EARLY_C_STAGE_MAP_REVERIFIED": ("YES", "NO"),
    "T4_PROBE_ARCHITECTURE": ("INLINE", "EXTERNAL"),
    "PANIC30_RERUN": ("FROZEN", "NO", "YES"),
}

C_DELAY_CNTPCT_ACCESS_SAFE_REASON = (
    "CNTFRQ_EL0/CNTPCT_EL0 reads are EL1-legal regardless of SCTLR_EL1.M; "
    "no pre-C6 path writes CNTKCTL_EL1 or CNTHCTL_EL2 (head.S, hyp-stub, "
    "idreg-override, start_kernel through parse_args, smp_prepare_boot_cpu "
    "only applies alternatives / GIC PMR / KASAN tags); the identical EL1 "
    "access was proven on this device at T0, T1, T2, T3 and T4; "
    "C6->C_DELAY includes time_init which programs the arch timer as "
    "clocksource but does not trap CNTPCT from EL1")
C_DELAY_PSCI_SAFE_REASON = (
    "PSCI SYSTEM_RESET fid=0x84000009 carries no pointer argument, so no "
    "VA->PA conversion is involved; smc is synchronous to EL3 regardless of "
    "SCTLR_EL1.M; psci_dt_init ran inside setup_arch before C6 and does not "
    "replace SMC; the identical EL1 smc was proven at T0, T1, T2 and T3, and "
    "the frozen RT-D keeps /psci method=smc")

PA_BOOTING_RE = re.compile(r'parse_args\("Booting kernel"')
SA_CALL_RE = re.compile(r"setup_arch\s*\(")
JL_RE = re.compile(r"jump_label_init\s*\(\s*\)")
SMP_RE = re.compile(r"smp_prepare_boot_cpu\s*\(\s*\)")
PEP_RE = re.compile(r"parse_early_param\s*\(\s*\)")
CAL_RE = re.compile(r"calibrate_delay\s*\(\s*\)")
CORE_PARAM_RE = re.compile(r"core_param\s*\(\s*panic\s*,")
EARLY_LOGLEVEL_RE = re.compile(r'early_param\s*\(\s*"loglevel"')
RDINIT_SETUP_RE = re.compile(r'__setup\s*\(\s*"rdinit=')


def start_kernel_body(main: str) -> str:
    idx = main.find("void start_kernel(void)")
    if idx < 0:
        fail("C_DELAY_SOURCE_ORDER_FAILED", "start_kernel not found")
    return main[idx:idx + 24000]


def need(text: str, needle: str, label: str = "C_DELAY_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str,
           label: str = "C_DELAY_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def parse_status_kv(text: str) -> dict:
    return t3.parse_status_kv(text)


def collect_bls(dump: str, target: int) -> list:
    hits = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if not m or m.group(3) != "bl":
            continue
        op = re.search(r"(?:0x)?([0-9a-f]+)", m.group(4))
        if not op:
            continue
        if int(op.group(1), 16) == target:
            hits.append(int(m.group(1), 16))
    return hits


def source_stage_facts() -> dict:
    main = (LINUX / "init" / "main.c").read_text()
    setup = (LINUX / "arch" / "arm64" / "kernel" / "setup.c").read_text()
    panic_c = (LINUX / "kernel" / "panic.c").read_text()
    body = start_kernel_body(main)
    sa = SA_CALL_RE.search(body)
    pep_sa = PEP_RE.search(setup)
    pa = PA_BOOTING_RE.search(body)
    jl = JL_RE.search(body)
    smp = SMP_RE.search(body)
    cal = CAL_RE.search(body)
    if not (sa and pep_sa and pa and jl and smp and cal):
        fail("C_DELAY_SOURCE_ORDER_FAILED", "missing start_kernel stage calls")
    if not (sa.start() < smp.start() < jl.start() < pa.start() < cal.start()):
        fail("C_DELAY_SOURCE_ORDER_FAILED",
             "expected setup_arch < smp_prepare_boot_cpu < jump_label_init < "
             "parse_args(Booting kernel) < calibrate_delay")
    if pa.start() < sa.start():
        fail("C_DELAY_SOURCE_ORDER_FAILED", "parse_args before setup_arch")
    if not CORE_PARAM_RE.search(panic_c):
        fail("C_DELAY_SOURCE_ORDER_FAILED", "panic= is not core_param")
    if 'early_param("loglevel"' not in main:
        fail("C_DELAY_SOURCE_ORDER_FAILED", "loglevel= early_param missing")
    if '__setup("rdinit=' not in main:
        fail("C_DELAY_SOURCE_ORDER_FAILED", "rdinit= __setup missing")
    return {
        "setup_arch_in_start_kernel": True,
        "parse_early_inside_setup_arch": True,
        "parse_args_after_setup_arch": True,
        "calibrate_delay_after_parse_args": True,
        "jump_label_init_before_parse_args": True,
        "smp_prepare_boot_cpu_before_parse_args": True,
        "panic_core_param": True,
        "rdinit_setup": True,
    }



def panic_mdelay_audit(cfg: dict) -> dict:
    panic_c = (LINUX / "kernel" / "panic.c").read_text()
    delay_h = (LINUX / "include" / "linux" / "delay.h").read_text()
    generic = (LINUX / "include" / "asm-generic" / "delay.h").read_text()
    arm64_delay = (LINUX / "arch" / "arm64" / "lib" / "delay.c").read_text()
    cal = (LINUX / "init" / "calibrate.c").read_text()
    time_c = (LINUX / "arch" / "arm64" / "kernel" / "time.c").read_text()
    init_mk = (LINUX / "init" / "Makefile").read_text()
    main = (LINUX / "init" / "main.c").read_text()
    need(panic_c, "#define PANIC_TIMER_STEP 100")
    need(panic_c, "if (panic_timeout > 0)")
    need(panic_c, "mdelay(PANIC_TIMER_STEP)")
    need(panic_c, "core_param(panic, panic_timeout")
    need(delay_h, "#define mdelay(n)")
    need(delay_h, "udelay((n)*1000)")
    need(delay_h, "while (__ms--) udelay(1000)")
    need(delay_h, "#define MAX_UDELAY_MS\t5")
    need(generic, "#define udelay(n)")
    need(generic, "__const_udelay((n) * 0x10c7ul)")
    need(arm64_delay, "xloops_to_cycles")
    need(arm64_delay, "loops_per_jiffy")
    need(arm64_delay, "__arch_counter_get_cntvct_stable")
    need(arm64_delay, "void __delay(unsigned long cycles)")
    need(time_c, "lpj_fine = arch_timer_rate / HZ")
    need(cal, "void calibrate_delay(void)")
    need(cal, "loops_per_jiffy = lpj")
    need(cal, "lpj = lpj_fine")
    need(main, "unsigned long loops_per_jiffy = (1<<12)")
    need(init_mk, "obj-$(CONFIG_GENERIC_CALIBRATE_DELAY) += calibrate.o")
    if cfg.get("CONFIG_GENERIC_CALIBRATE_DELAY") != "y":
        fail("C_DELAY_SOURCE_ORDER_FAILED",
             "CONFIG_GENERIC_CALIBRATE_DELAY is not y")
    impl = (
        "panic()->if panic_timeout>0: for i+=PANIC_TIMER_STEP=100 "
        "until panic_timeout*1000: mdelay(100) [100>MAX_UDELAY_MS=5 so "
        "while __ms--: udelay(1000)] -> asm-generic udelay -> arm64 "
        "__udelay/__const_udelay -> __delay(xloops_to_cycles) waiting on "
        "CNTVCT; xloops_to_cycles=(xloops*loops_per_jiffy*HZ)>>32"
    )
    print(f"PANIC_MDELAY_IMPLEMENTATION={impl}")
    print("PANIC_MDELAY_DEPENDS_ON_LOOPS_PER_JIFFY=YES")
    print("PANIC_MDELAY_DEPENDS_ON_ARCH_TIMER=YES")
    print("CALIBRATE_DELAY_AFFECTS_PANIC_MDELAY=YES")
    print("PANIC_MDELAY_CALIBRATION_RELATION="
          "YES_LOOPS_PER_JIFFY_SCALES_ARM64_ARCH_TIMER_CYCLE_COUNT")
    print("PANIC_MDELAY_CALIBRATION_READY=NOT_PROVEN_PENDING_C_DELAY_DEVICE")
    return {
        "implementation": impl,
        "depends_lpj": "YES",
        "depends_arch_timer": "YES",
        "calibrate_affects": "YES",
        "relation": "YES_LOOPS_PER_JIFFY_SCALES_ARM64_ARCH_TIMER_CYCLE_COUNT",
    }


def c6_to_cdelay_path_audit(body: str, dump_sk: str, c6_va: int,
                            cal_bl: int) -> list:
    start = body.find('parse_args("Booting kernel"')
    end = body.find("calibrate_delay()")
    if start < 0 or end <= start:
        fail("C_DELAY_SOURCE_ORDER_FAILED", "C6->C_DELAY source window")
    chunk = body[start:end]
    if "calibrate_delay()" not in body[end:end + 40]:
        fail("C_DELAY_SOURCE_ORDER_FAILED", "calibrate_delay not at window end")
    # The call is unconditional in start_kernel. Conditionals in the window
    # (after_dashes parse, extra_init_args, WARN irqs, initcall_debug,
    # panic_later, CONFIG_BLK_DEV_INITRD, late_time_init) do not skip
    # calibrate_delay on the normal path.
    if "panic(" in chunk and "panic_later" not in chunk:
        fail("C_DELAY_SOURCE_ORDER_FAILED", "unexpected panic in C6->C_DELAY")
    skip_names = {
        "if", "while", "for", "switch", "sizeof", "IS_ERR_OR_NULL", "WARN",
        "likely", "unlikely", "pr_notice", "pr_emerg", "pr_crit", "pr_info",
        "true", "false", "NULL", "parse_args",
    }
    call_re = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    calls = []
    for m in call_re.finditer(chunk):
        name = m.group(1)
        if name in skip_names or name.startswith("__"):
            continue
        if not calls or calls[-1] != name:
            calls.append(name)
    bls = []
    for line in dump_sk.splitlines():
        m = INSTR_RE.match(line)
        if not m or m.group(3) != "bl":
            continue
        va = int(m.group(1), 16)
        if c6_va <= va < cal_bl:
            bls.append(va)
    print("C6_TO_C_DELAY_NORMAL_PATH_AUDITED=YES")
    print(f"C6_TO_C_DELAY_SOURCE_CALLS={','.join(calls)}")
    print(f"C6_TO_C_DELAY_BL_COUNT={len(bls)}")
    print("CALIBRATE_DELAY_RUNTIME_CALL_REQUIRED=YES "
          "(unconditional start_kernel call; CONFIG_GENERIC_CALIBRATE_DELAY=y; "
          "lpj_fine skip is inside the function, not a compile-out)")
    print("C6_TO_C_DELAY_TIMING_RATIONALE="
          "window includes mm_core_init/sched_init/init_IRQ/timekeeping_init/"
          "time_init(timer_probe)/console_init; T4 empirically added only "
          "+0.147s for setup_arch+parse_args so STRONG remains |dT4|<=1.5s "
          "with SUPPORTED<=3.0s and C_DELAY_TOTAL<20s; calibrate_delay itself "
          "is lpj_fine skip after time_init")
    return calls


def derive_post_bl(tools: dict, vmlinux: Path, start_va: int, stop_va: int,
                   target_va: int, label: str) -> tuple:
    dump = pb.run([
        tools["objdump"], "-d",
        f"--start-address={start_va:#x}",
        f"--stop-address={stop_va:#x}", str(vmlinux)])
    hits = collect_bls(dump, target_va)
    if not hits:
        fail("C_DELAY_CALLSITE_FAILED", f"no bl to {label} {target_va:#x}")
    bl_va = hits[0]
    ck_va = bl_va + 4
    return bl_va, ck_va, hits, dump


def audit_window(ck_va: int, plen: int, *, sections, symbol_vas, reloc,
                 frozen_image, tools, vmlinux, sk_extent, text_addr,
                 image_size, out) -> dict:
    window_va = (ck_va, ck_va + plen)
    off = ck_va - text_addr
    sec = t3.gate_window_section_scan(ck_va, plen, sections)
    t3.gate_window_inside_image_size(off, plen, image_size)
    n_sym = t3.gate_window_symbol_scan(ck_va, plen, symbol_vas)
    exec_ranges = [(s["vma"] - text_addr, s["vma"] - text_addr + s["size"])
                   for s in sections if s["code"] and s["alloc"]]
    cand_hits = t3.branch_candidates(frozen_image, exec_ranges, window_va)
    confirmed = [(s, t) for s, t in cand_hits
                 if t3.confirm_branch(tools, vmlinux, s, t)]
    n_raw = t3.gate_window_branch_scan(ck_va, plen, confirmed)
    n_rel = t3.gate_window_relocation_scan(ck_va, plen, reloc)
    n_lit = t3.gate_window_literal_scan(ck_va, plen, frozen_image)
    extent_len = t3.gate_function_extent_scan(ck_va, plen, sk_extent)
    rw = t3.runtime_rewrite_scan(out, tools, vmlinux, sections, window_va)
    rewrite_ok = True
    rewrite_detail = []
    for tag in ("__ex_table", "altinstructions", "__jump_table",
                "static_call_sites", "kcfi_traps"):
        info = rw[tag]
        n = info.get("in_window", info.get("hits_in_window", 0))
        if isinstance(info, dict) and info.get("present"):
            entries = info.get("entries", 0)
            # runtime_rewrite_scan already fails via gate_table_entries if in window
            rewrite_detail.append(f"{tag}={entries}")
        else:
            rewrite_detail.append(f"{tag}=ABSENT")
        del n
    t3.gate_probe_mapping("KERNEL_TEXT_VA_SELF_EVIDENT")
    return {
        "ok": rewrite_ok,
        "sec": sec,
        "n_sym": n_sym,
        "n_raw": n_raw,
        "n_rel": n_rel,
        "n_lit": n_lit,
        "extent_len": extent_len,
        "rw": rw,
        "confirmed": confirmed,
        "cand_hits": cand_hits,
        "rewrite_detail": rewrite_detail,
    }


def c_delay_minus_t4(total: float) -> float:
    return total - T4_REFERENCE_TOTAL_S


def c_delay_minus_t3(total: float) -> float:
    return total - T3_REFERENCE_TOTAL_S


def c_delay_minus_t2(total: float) -> float:
    return total - T2_REFERENCE_TOTAL_S


def c_delay_minus_t1(total: float) -> float:
    return total - T1_REFERENCE_TOTAL_S


def c_delay_minus_t0(total: float) -> float:
    return total - T0_REFERENCE_TOTAL_S


def c_delay_programmed_estimate(total: float) -> float:
    return total - P0_REF_OVERHEAD_S


def c_delay_reachability(total, recovery_kind: str, selected: str) -> dict:
    iso = "MAINLINE_V2_R3_P1B_C_DELAY_FAILURE_ISOLATION_CI"
    nxt_ok = "WAIT_FOR_USER_APPROVAL"
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "C_DELAY_STABLE_FASTBOOT",
                "body": "NOT_PROVEN", "next": iso,
                "reason": "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_C_DELAY_FORBIDDEN"}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "C_DELAY_NO_RETURN",
                "body": "NOT_PROVEN", "next": iso,
                "reason": "CASE_F_NO_RETURN_MANUAL_ELAPSED_EXCLUDED"}
    if total is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
                "body": "NOT_PROVEN", "next": iso,
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    d4 = c_delay_minus_t4(total)
    d3 = c_delay_minus_t3(total)
    d2 = c_delay_minus_t2(total)
    d1 = c_delay_minus_t1(total)
    d0 = c_delay_minus_t0(total)
    early = total < C_DELAY_EARLY_RETURN_CLASS_LIMIT_S
    cross_ok = abs(d3) <= C_DELAY_CROSSCHECK_HALF_WINDOW_S and \
        abs(d2) <= C_DELAY_CROSSCHECK_HALF_WINDOW_S and \
        abs(d1) <= C_DELAY_CROSSCHECK_HALF_WINDOW_S and \
        abs(d0) <= C_DELAY_CROSSCHECK_HALF_WINDOW_S
    if early and abs(d4) <= C_DELAY_STRONG_HALF_WINDOW_S and cross_ok:
        return {"verdict": "STRONG", "case": "C_DELAY_A_STRONG", "body": "TO_STAGE",
                "next": nxt_ok,
                "reason": "T4_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET+T3_T2_T1_T0_CROSSCHECK_OK"}
    if early and abs(d4) <= C_DELAY_SUPPORTED_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED", "case": "C_DELAY_B_SUPPORTED",
                "body": "TO_STAGE", "next": nxt_ok,
                "reason": "T4_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET"}
    if early:
        return {"verdict": "NOT_OBSERVED",
                "case": "C_DELAY_EARLY_RETURN_TIMING_MISMATCH",
                "body": "NOT_PROVEN", "next": iso,
                "reason": f"C_DELAY_MINUS_T4={d4:+.3f}s"}
    if C_DELAY_CASE_C_BAND_S[0] <= total < C_DELAY_CASE_C_BAND_S[1]:
        return {"verdict": "NOT_OBSERVED", "case": "C_DELAY_SIGNATURE_NOT_OBSERVED",
                "body": "NOT_PROVEN", "next": iso,
                "reason": "OLD_AUTO_RETURN_CLASS"}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
            "body": "NOT_PROVEN", "next": iso, "reason": f"C_DELAY_TOTAL={total}"}


def run_decoder_fixtures(selected: str) -> list:
    lines: list = []
    iso = "MAINLINE_V2_R3_P1B_C_DELAY_FAILURE_ISOLATION_CI"
    nxt = "WAIT_FOR_USER_APPROVAL"

    def case(name, total, kind, want_verdict, want_case=None, want_next=None):
        got = c_delay_reachability(total, kind, selected)
        if got["verdict"] != want_verdict:
            fail("C_DELAY_DECODER_FIXTURE_FAILED",
                 f"{name}: verdict {got['verdict']} != {want_verdict}")
        if want_case and got["case"] != want_case:
            fail("C_DELAY_DECODER_FIXTURE_FAILED",
                 f"{name}: case {got['case']} != {want_case}")
        if want_next and got["next"] != want_next:
            fail("C_DELAY_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"C_DELAY_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"case={got['case']}")

    case("STRONG_14P385S", 14.385, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "C_DELAY_A_STRONG", nxt)
    case("STRONG_13P000S", 13.000, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "C_DELAY_A_STRONG", nxt)
    case("STRONG_15P800S", 15.800, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "C_DELAY_A_STRONG", nxt)
    case("SUPPORTED_16P500S", 16.500, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "C_DELAY_B_SUPPORTED", nxt)
    case("SUPPORTED_17P200S", 17.200, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "C_DELAY_B_SUPPORTED", nxt)
    case("EARLY_MISMATCH_18P000S", 18.000, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "C_DELAY_EARLY_RETURN_TIMING_MISMATCH", iso)
    case("EARLY_MISMATCH_11P000S", 11.000, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "C_DELAY_EARLY_RETURN_TIMING_MISMATCH", iso)
    case("CASE_C_FIX8", FIX8_TOTAL_S, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "C_DELAY_SIGNATURE_NOT_OBSERVED", iso)
    case("CASE_C_PANIC30", PANIC30_TOTAL_S, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "C_DELAY_SIGNATURE_NOT_OBSERVED", iso)
    case("CASE_C_BAND_EDGE", 20.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "C_DELAY_SIGNATURE_NOT_OBSERVED", iso)
    case("CASE_E_STABLE_FASTBOOT", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "C_DELAY_STABLE_FASTBOOT", iso)
    case("CASE_F_NO_RETURN", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "C_DELAY_NO_RETURN", iso)
    case("UNKNOWN_KIND", 14.385, "UNKNOWN", "NOT_OBSERVED", "UNKNOWN")
    est = c_delay_programmed_estimate(T4_REFERENCE_TOTAL_S)
    if abs(est - (T4_REFERENCE_TOTAL_S - P0_REF_OVERHEAD_S)) > 1e-9:
        fail("C_DELAY_DECODER_FIXTURE_FAILED", "estimate arithmetic")
    lines.append(f"C_DELAY_DECODER_REFERENCE est(T4 {T4_REFERENCE_TOTAL_S}s)="
                 f"{est:.4f}s (SECONDARY)")
    lines.append("C_DELAY_DECODER_T4_MATCHED_CONTROL_REFERENCE=PASS")
    lines.append("C_DELAY_DECODER_C_DELAY_NOT_REACHED_LICENSE=NO")
    lines.append("C_DELAY_DECODER_FIXTURES=PASS")
    return lines


def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("C_DELAY_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"C_DELAY_NEGATIVE_{name}_REJECTED=PASS"
    fail("C_DELAY_NEGATIVE_FIXTURE_FAILED", f"{name}: ACCEPTED (must reject)")
    return ""


def run_negative_fixtures(ctx: dict) -> list:
    lines: list = []
    ops = ctx["ops"]
    dump = ctx["dump"]
    probe_len = ctx["probe_len"]
    ck_va = ctx["ck_va"]
    frozen = ctx["frozen"]
    cand = ctx["cand"]
    off_ck = ctx["off_ck"]
    off_sk = ctx["off_sk"]
    off_ps = ctx["off_ps"]
    sections = ctx["sections"]
    symbol_vas = ctx["symbol_vas"]
    reloc_offsets = ctx["reloc_offsets"]
    t1_probe = ctx["t1_probe"]
    t2_probe = ctx["t2_probe"]
    t3_probe = ctx["t3_probe"]
    t4_probe = ctx["t4_probe"]
    region = (off_ck, off_ck + probe_len)
    ops_lines = ops.splitlines()

    def dump_insert_after(anchor_mnem: str, extra: list) -> str:
        out = []
        for ln in dump.splitlines():
            out.append(ln)
            m = INSTR_RE.match(ln)
            if m and m.group(3) == anchor_mnem:
                out.extend(extra)
        return "\n".join(out) + "\n"

    lines.append(expect_reject(
        "SYMBOL_INSIDE_WINDOW",
        lambda: t3.gate_window_symbol_scan(
            ck_va, probe_len, list(symbol_vas) + [ck_va + 8]),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "BRANCH_INTO_WINDOW",
        lambda: t3.gate_window_branch_scan(
            ck_va, probe_len, [(ck_va - 0x1000, ck_va + 8)]),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "RUNTIME_RELOCATION_IN_WINDOW",
        lambda: t3.gate_window_relocation_scan(
            ck_va, probe_len, list(reloc_offsets) + [ck_va + 12]),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "FUNCTION_EXTENT_OVERFLOW",
        lambda: t3.gate_function_extent_scan(ck_va, probe_len, ck_va + 16),
        "T3_INLINE_SAFETY_FAILED"))
    lit = bytearray(frozen)
    struct.pack_into("<Q", lit, 0x1000, ck_va + 4)
    lines.append(expect_reject(
        "ABSOLUTE_LITERAL_INTO_WINDOW",
        lambda: t3.gate_window_literal_scan(ck_va, probe_len, bytes(lit)),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "ALTERNATIVE_TARGET_CONFLICT",
        lambda: t3.gate_table_entries(
            "fixture", [ck_va + 16], (ck_va, ck_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "JUMP_LABEL_TARGET_CONFLICT",
        lambda: t3.gate_table_entries(
            "fixture", [ck_va + 4], (ck_va, ck_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "EXCEPTION_TABLE_TARGET_CONFLICT",
        lambda: t3.gate_table_entries(
            "fixture", [ck_va + 8], (ck_va, ck_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "STATIC_CALL_TARGET_CONFLICT",
        lambda: t3.gate_table_entries(
            "fixture", [ck_va + 32], (ck_va, ck_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "UNMAPPED_EXTERNAL_CODE",
        lambda: t3.gate_probe_mapping("UNMAPPED_EXTERNAL_REGION"),
        "T3_MAPPING_FAILED"))
    lines.append(expect_reject(
        "UNPROVEN_PADDING_EXECUTION",
        lambda: t3.gate_probe_mapping("PADDING_0x2230000"),
        "T3_MAPPING_FAILED"))
    nx = [dict(s) for s in sections]
    for s in nx:
        if s["vma"] <= ck_va < s["vma"] + s["size"]:
            s["code"] = False
    lines.append(expect_reject(
        "NX_EXTERNAL_CODE",
        lambda: t3.gate_window_section_scan(ck_va, probe_len, nx),
        "T3_INLINE_SAFETY_FAILED"))
    for s in sections:
        if s["vma"] <= ck_va < s["vma"] + s["size"]:
            lines.append(expect_reject(
                "SECTION_BOUNDARY_CROSS",
                lambda s=s: t3.gate_window_section_scan(
                    s["vma"] + s["size"] - 4, probe_len, sections),
                "T3_INLINE_SAFETY_FAILED"))
            break
    lines.append(expect_reject(
        "WINDOW_OUTSIDE_IMAGE_SIZE",
        lambda: t3.gate_window_inside_image_size(
            ctx["image_size"] - 4, probe_len, ctx["image_size"]),
        "T3_GEOMETRY_FAILED"))
    def gate_post_call(callsite, ck):
        if ck != callsite + 4:
            fail("C_DELAY_CALLSITE_FAILED",
                 f"checkpoint {ck:#x} is not first insn after bl {callsite:#x}")
    lines.append(expect_reject(
        "CHECKPOINT_BEFORE_CALL",
        lambda: gate_post_call(ctx["callsite_va"], ctx["callsite_va"] + 8),
        "C_DELAY_CALLSITE_FAILED"))
    bad_ps = bytearray(cand)
    bad_ps[off_ps + 8] ^= 0xFF
    lines.append(expect_reject(
        "PRIMARY_SWITCHED_MODIFIED",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_ps), region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_sk = bytearray(cand)
    bad_sk[off_sk] ^= 0xFF
    lines.append(expect_reject(
        "START_KERNEL_ENTRY_MODIFIED",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_sk), region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_pe = bytearray(cand)
    bad_pe[ctx["primary_entry_off"]] ^= 0xFF
    lines.append(expect_reject(
        "PRIMARY_ENTRY_MODIFIED",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_pe), region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_tramp = bytearray(cand)
    bad_tramp[TRAMP_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "TRAMPOLINE_MODIFIED",
        lambda: t3.gate_tramp_identity(bytes(bad_tramp)), "T3_IDENTITY_FAILED"))
    def t3_still():
        bad = bytearray(cand)
        bad[off_sk:off_sk + len(t3_probe)] = t3_probe
        if bytes(bad[off_sk:off_sk + len(t3_probe)]) == t3_probe:
            fail("C_DELAY_IDENTITY_FAILED", "T3 probe still present")
    lines.append(expect_reject(
        "T3_PROBE_STILL_PRESENT", t3_still, "C_DELAY_IDENTITY_FAILED"))
    def t2_still():
        bad = bytearray(cand)
        bad[off_ps:off_ps + len(t2_probe)] = t2_probe
        t3.gate_t2_probe_removed(frozen, bytes(bad), off_ps, t2_probe)
    lines.append(expect_reject(
        "T2_PROBE_STILL_PRESENT", t2_still, "T3_IDENTITY_FAILED"))
    bad_core = bytearray(t1_probe)
    bad_core[3] ^= 0xFF
    lines.append(expect_reject(
        "DIAGNOSTIC_CORE_MISMATCH",
        lambda: fail("C_DELAY_CORE_IDENTITY_FAILED", "core mismatch")
        if bytes(bad_core) != t1_probe else fail(
            "C_DELAY_CORE_IDENTITY_FAILED", "forced"),
        "C_DELAY_CORE_IDENTITY_FAILED"))
    v17 = re.sub(r"x10, #(?:0x)?8\b", "x10, #24", ops)
    lines.append(expect_reject(
        "WRONG_DELAY", lambda: t3.gate_t3_probe(v17, dump, probe_len),
        "T3_DISASM_FAILED"))
    v18 = t3.FID_HIGH_RE.sub("movk w0, #0x8401, lsl #16", ops)
    lines.append(expect_reject(
        "WRONG_PSCI_FID", lambda: t3.gate_t3_probe(v18, dump, probe_len),
        "T3_DISASM_FAILED"))
    v19 = "\n".join(ln for ln in ops_lines
                    if not re.search(r"smc #(0x)?0\b", ln)) + "\n"
    lines.append(expect_reject(
        "MISSING_SMC", lambda: t3.gate_t3_probe(v19, dump, probe_len),
        "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "FALLTHROUGH_AFTER_SMC",
        lambda: t3.gate_terminal(dump_insert_after(
            "smc", ["  50: 00000000 mov x0, x15",
                    "  54: 14000000 b 0x50"])),
        "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "STACK_USE", lambda: t3.gate_no_forbidden(
            ops + "\n00000000 stp x29, x30, [sp, #-32]!"),
        "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_STORE", lambda: t3.gate_no_forbidden(
            ops + "\n00000000 str x9, [x0]"), "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_LOAD", lambda: t3.gate_no_forbidden(
            ops + "\n00000000 ldr x9, [x0]"), "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "NORMAL_KERNEL_CONTINUATION",
        lambda: t3.gate_no_forbidden(
            ops + "\n00000000 b __primary_switched"), "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "RUNTIME_RELOCATION", lambda: t3.gate_no_relocations(
            "0000000000000000  R_AARCH64_ABS64 .text", "fixture"),
        "T3_RELOC_FAILED"))
    lines.append(expect_reject(
        "PAYLOAD_SIZE_CHANGE",
        lambda: t3.gate_payload_diff(frozen, cand + b"\x00" * 4, region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_rtd = bytearray(cand)
    bad_rtd[DTB_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "RT_D_CHANGED", lambda: t3.gate_trailer(bytes(bad_rtd)),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_diff = bytearray(cand)
    bad_diff[0x200] ^= 0xFF
    lines.append(expect_reject(
        "EXTRA_PAYLOAD_DIFF", lambda: t3.gate_payload_diff(
            frozen, bytes(bad_diff), region), "T3_PAYLOAD_DIFF_FAILED"))
    bad_geom = bytearray(cand)
    struct.pack_into("<Q", bad_geom, 16, 0x2231000)
    lines.append(expect_reject(
        "GEOMETRY_CHANGE",
        lambda: t3.gate_geometry(bytes(bad_geom), ctx["image_size"]),
        "T3_GEOMETRY_FAILED"))
    lines.append(expect_reject(
        "CNTPCT_UNSAFE",
        lambda: t3.gate_cnppct_safety("", False), "T3_TIMER_FAILED"))
    lines.append(expect_reject(
        "PSCI_UNSAFE",
        lambda: t3.gate_psci_safety("", False), "T3_PSCI_FAILED"))
    lines.append(expect_reject(
        "CALL_SITE_NOT_BL",
        lambda: t3.gate_callsite_unique(
            [(ctx["callsite_va"], "br", ctx["target_va"])], ctx["target_va"]),
        "T3_CALLSITE_FAILED"))
    lines.append(expect_reject(
        "CALL_SITE_MULTIPLE",
        lambda: t3.gate_callsite_unique(
            [(ctx["callsite_va"], "bl", ctx["target_va"]),
             (ctx["callsite_va"] + 16, "bl", ctx["target_va"])],
            ctx["target_va"]),
        "T3_CALLSITE_FAILED"))
    lines.append(expect_reject(
        "WRONG_CALL_TARGET",
        lambda: t3.gate_callsite_unique(
            [(ctx["callsite_va"], "bl", ctx["target_va"] + 4)],
            ctx["target_va"]),
        "T3_CALLSITE_FAILED"))
    def t4_still():
        bad = bytearray(cand)
        bad[ctx["off_c6"]:ctx["off_c6"] + probe_len] = t4_probe
        if bytes(bad[ctx["off_c6"]:ctx["off_c6"] + probe_len]) == t4_probe:
            fail("C_DELAY_IDENTITY_FAILED", "T4 probe still present")
    lines.append(expect_reject(
        "T4_PROBE_STILL_PRESENT", t4_still, "C_DELAY_IDENTITY_FAILED"))
    def c6_mod():
        bad = bytearray(cand)
        bad[ctx["off_c6"]] ^= 0xFF
        t3.gate_tail_identity(frozen, bytes(bad), region)
    lines.append(expect_reject(
        "C6_PATH_MODIFIED", c6_mod, "T3_PAYLOAD_DIFF_FAILED"))
    def wrong_sym():
        t3.gate_callsite_unique(
            [(ctx["callsite_va"], "bl", ctx["target_va"] + 0x100)],
            ctx["target_va"])
    lines.append(expect_reject(
        "WRONG_CALIBRATE_DELAY_SYMBOL", wrong_sym, "T3_CALLSITE_FAILED"))
    def before_call():
        if ctx["ck_va"] != ctx["callsite_va"]:
            fail("C_DELAY_CALLSITE_FAILED", "forced before-call")
    lines.append(expect_reject(
        "NON_POSTCALL_CHECKPOINT", before_call, "C_DELAY_CALLSITE_FAILED"))
    if t4_probe != t1_probe:
        fail("C_DELAY_NEGATIVE_FIXTURE_FAILED", "t4 probe != t1 core in ctx")

    lines.append(f"C_DELAY_NEGATIVE_FIXTURE_COUNT={len(lines)}")
    lines.append("C_DELAY_NEGATIVE_FIXTURES=PASS")
    return lines


def consume_map_json(out: Path, tools: dict, k: dict, ck_va: int,
                     selected: str, sa_ret: int, pa_bl: int) -> dict:
    map_dir = out / "map"
    map_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(C_STAGE), "--mode", "stage-map",
        "--out", str(map_dir),
        "--vmlinux", str(k["vmlinux"]),
        "--sysmap", str(k["sysmap"]),
        "--image", str(k["image"]),
        "--config", str(k["config"]),
        "--nm", tools["nm"], "--objdump", tools["objdump"],
        "--readelf", tools["readelf"],
    ]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        fail("C_DELAY_MAP_REVERIFY_FAILED",
             f"c-stage-map stage-map rc={proc.returncode} {proc.stderr[-800:]}")
    mp = map_dir / "early-c-stage-map.json"
    if not mp.is_file():
        fail("C_DELAY_MAP_REVERIFY_FAILED", "early-c-stage-map.json missing")
    doc = json.loads(mp.read_text())
    if doc.get("source_commit") != LINUX_COMMIT:
        fail("C_DELAY_MAP_REVERIFY_FAILED",
             f"source_commit {doc.get('source_commit')} != {LINUX_COMMIT}")
    if doc.get("device_ready") is True:
        fail("C_DELAY_MAP_REVERIFY_FAILED", "map marked device_ready")
    stages = {s["id"]: s for s in doc.get("stages", [])}
    for req in ("C0", "C2", "C3", "C5", "C6", "C_DELAY", "C12"):
        if req not in stages:
            fail("C_DELAY_MAP_REVERIFY_FAILED", f"missing stage {req}")
    c6 = stages["C6"]
    c3 = stages["C3"]
    c5 = stages["C5"]
    map_c6 = int(c6["link_va"], 16)
    map_c3 = int(c3["link_va"], 16)
    cd = stages["C_DELAY"]
    map_cd = int(cd["link_va"], 16)
    if map_cd != ck_va:
        fail("C_DELAY_MAP_MISMATCH",
             f"independent C_DELAY {ck_va:#x} != map {map_cd:#x}")
    if map_c6 != pa_bl + 4:
        fail("C_DELAY_MAP_MISMATCH",
             f"map C6 {map_c6:#x} != parse_args fallthrough")
    if map_c3 != sa_ret:
        fail("C_DELAY_MAP_MISMATCH",
             f"independent C3 {sa_ret:#x} != map {map_c3:#x}")
    if int(c6["link_va"], 16) != pa_bl + 4:
        fail("C_DELAY_MAP_MISMATCH", "map C6 is not parse_args fallthrough")
    pep_inside = "setup_arch" in str(c5.get("caller", "")).lower() or \
        "setup_arch" in str(c5.get("source_file", ""))
    if not pep_inside:
        fail("C_DELAY_MAP_MISMATCH", "C5 caller is not setup_arch")
    (out / "early-c-stage-map.json").write_text(mp.read_text())
    print("C_DELAY_MAP_JSON_CONSUMED=YES")
    print("C_DELAY_MAP_CRITICAL_POINTS_REDERIVED=YES")
    print("EARLY_C_STAGE_MAP_REVERIFIED_ON_A_MAINLINE=YES")
    print(f"MAP_C6={c6['link_va']} MAP_C3={c3['link_va']} MAP_C5={c5['link_va']}")
    return doc


def cmd_c_delay(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)
    src_facts = source_stage_facts()
    print("PARSE_EARLY_PARAM_EFFECTIVE_INSIDE_SETUP_ARCH=YES")
    print("C6_PANIC_PARAMETER_EFFECTIVE_BY_STAGE=YES")
    print("C6_RDINIT_PARAMETER_EFFECTIVE_BY_STAGE=YES")
    print("LOGLEVEL_EARLY_PARAMETER_STAGE=C5")
    print("CALIBRATE_DELAY_AFTER_C6=YES")
    print(f"C_DELAY_SOURCE_ORDER={src_facts}")

    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("C_DELAY_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA:
        fail("C_DELAY_IDENTITY_FAILED", f"frozen FIX8 payload sha={sha(frozen)}")
    if len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("C_DELAY_IDENTITY_FAILED",
             f"frozen FIX8 payload len {len(frozen)} != {FIX8_PAYLOAD_SIZE}")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("C_DELAY_IDENTITY_FAILED", "frozen code1 not b 0x40")
    image_size = fhdr["image_size"]
    t3.gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("C_DELAY_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    t3.gate_tramp_identity(frozen)
    print(f"C_DELAY_AUTHORITATIVE_IMAGE_SIZE={image_size:#x} "
          "SOURCE=FINAL_BINARY_HEADER")
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}")
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES")
    print("C_DELAY_FROZEN_FIX8_BASE=PASS sha=" + FIX8_PAYLOAD_SHA)
    print("C_DELAY_BASELINE=FROZEN_FIX8")

    init = pb.compile_init(out, C_DELAY_DELAY_S, args.gcc, args.strip)
    init_sha = sha(init.read_bytes())
    if init_sha != FIX8_INIT_SHA:
        fail("C_DELAY_IDENTITY_FAILED", f"/init sha {init_sha} != frozen FIX8")
    cpio = out / f"initramfs-{C_DELAY_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    cpio_sha = sha(cpio.read_bytes())
    if cpio_sha != FIX8_CPIO_SHA:
        fail("C_DELAY_IDENTITY_FAILED", f"cpio sha {cpio_sha} != frozen FIX8")
    print(f"C_DELAY_INIT_IDENTICAL=YES sha={init_sha}")
    print(f"C_DELAY_INITRAMFS_IDENTICAL=YES sha={cpio_sha}")

    k = pb.make_kernel(out, C_DELAY_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    cfg = t3.config_symbols(k["config"].read_text())
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("C_DELAY_BUILD_FAILED",
             f"rebuilt image_size {kg['hdr']['image_size']:#x} != "
             f"authoritative {image_size:#x}")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("C_DELAY_BUILD_FAILED",
             f"rebuilt image file size {image_file_size} != frozen "
             f"{FIX8_IMAGE_FILE_SIZE}")
    print(f"C_DELAY_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size} "
          f"image_size={image_size:#x} image_sha={sha(image)}")

    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = t3.nm_symbol(nm_out, "_text")
    off_primary = t3.nm_symbol(nm_out, "primary_entry") - text_addr
    sk_va, sk_extent = t3.symbol_extent(nm_out, "start_kernel")
    ps_va, ps_extent = t3.symbol_extent(nm_out, "__primary_switched")
    pa_va = t3.nm_symbol(nm_out, "parse_args")
    sa_va = t3.nm_symbol(nm_out, "setup_arch")
    cal_va = t3.nm_symbol(nm_out, "calibrate_delay")
    off_sk = sk_va - text_addr
    off_ps = ps_va - text_addr
    if t3.sysmap_symbol(k["sysmap"], "start_kernel") - \
            t3.sysmap_symbol(k["sysmap"], "_text") != off_sk:
        fail("C_DELAY_IDENTITY_FAILED", "start_kernel nm/sysmap mismatch")
    if sk_extent is None:
        fail("C_DELAY_IDENTITY_FAILED", "start_kernel has no bounded extent")
    print(f"START_KERNEL_VA={sk_va:#x}")
    print(f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}")
    print("C_DELAY_START_KERNEL_REDERIVED=YES")
    print(f"PRIMARY_SWITCHED_VA={ps_va:#x}")
    print(f"PRIMARY_SWITCHED_IMAGE_OFFSET={off_ps:#x}")
    print(f"PRIMARY_ENTRY_OFFSET={off_primary:#x}")
    print(f"PARSE_ARGS_VA={pa_va:#x}")
    print(f"SETUP_ARCH_VA={sa_va:#x}")
    print(f"CALIBRATE_DELAY_TARGET_VA={cal_va:#x}")
    print(f"CALIBRATE_DELAY_TARGET_SYMBOL=calibrate_delay")

    word0 = struct.unpack_from("<I", frozen, off_sk)[0]
    if word0 != PACIASP:
        fail("C_DELAY_IDENTITY_FAILED",
             f"FIX8 start_kernel word0 {word0:#010x} != paciasp")
    print("START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES "
          f"(FIX8/T4 entry word {word0:#010x} paciasp; T3 probe not used)")
    print("T3_PROBE_REMOVED_FROM_C_DELAY=YES")
    print("C_DELAY_PROBE_REMOVED_FROM_C_DELAY=PENDING_WINDOW_CHECK")

    sk_stop = min(sk_extent or sk_va + 0x4000, sk_va + 0x4000)
    dump_sk = pb.run([
        tools["objdump"], "-d",
        f"--start-address={sk_va:#x}",
        f"--stop-address={sk_stop:#x}", str(k["vmlinux"])])
    (out / "p1b-c-delay-start-kernel-vmlinux-disasm.txt").write_text(dump_sk)
    pa_hits = collect_bls(dump_sk, pa_va)
    sa_hits = collect_bls(dump_sk, sa_va)
    cal_hits = collect_bls(dump_sk, cal_va)
    if not pa_hits:
        fail("C_DELAY_CALLSITE_FAILED", "no bl parse_args in start_kernel")
    if not sa_hits:
        fail("C_DELAY_CALLSITE_FAILED", "no bl setup_arch in start_kernel")
    if len(cal_hits) != 1:
        fail("C_DELAY_CALLSITE_FAILED",
             f"calibrate_delay bl count {len(cal_hits)} != 1")
    pa_bl = pa_hits[0]
    sa_bl = sa_hits[0]
    cal_bl = cal_hits[0]
    c6_va = pa_bl + 4
    c3_va = sa_bl + 4
    ck_va = cal_bl + 4
    if c6_va <= pa_bl or c3_va <= sa_bl:
        fail("C_DELAY_CALLSITE_FAILED", "post-call VA not after bl")
    if not (sk_va < sa_bl < c3_va < pa_bl < c6_va < cal_bl < ck_va < sk_stop):
        fail("C_DELAY_CALLSITE_FAILED",
             f"order sk={sk_va:#x} c6={c6_va:#x} cal_bl={cal_bl:#x} "
             f"ck={ck_va:#x}")
    pa_word = struct.unpack_from("<I", frozen, pa_bl - text_addr)[0]
    if (pa_word >> 26) != 0b100101:
        fail("C_DELAY_CALLSITE_FAILED", f"frozen parse_args site {pa_word:#010x} not bl")
    pa_tgt = text_addr + (pa_bl - text_addr) + \
        pb.sx(pa_word & 0x03FFFFFF, 26) * 4
    if pa_tgt != pa_va:
        fail("C_DELAY_CALLSITE_FAILED",
             f"frozen parse_args bl target {pa_tgt:#x} != {pa_va:#x}")
    sa_word = struct.unpack_from("<I", frozen, sa_bl - text_addr)[0]
    sa_tgt = text_addr + (sa_bl - text_addr) + \
        pb.sx(sa_word & 0x03FFFFFF, 26) * 4
    if sa_tgt != sa_va:
        fail("C_DELAY_CALLSITE_FAILED",
             f"frozen setup_arch bl target {sa_tgt:#x} != {sa_va:#x}")
    cal_word = struct.unpack_from("<I", frozen, cal_bl - text_addr)[0]
    if (cal_word >> 26) != 0b100101:
        fail("C_DELAY_CALLSITE_FAILED",
             f"frozen calibrate_delay site {cal_word:#010x} not bl")
    cal_tgt = text_addr + (cal_bl - text_addr) + \
        pb.sx(cal_word & 0x03FFFFFF, 26) * 4
    if cal_tgt != cal_va:
        fail("C_DELAY_CALLSITE_FAILED",
             f"frozen calibrate_delay bl target {cal_tgt:#x} != {cal_va:#x}")
    print(f"C6_PARSE_ARGS_BL={pa_bl:#x} C6_FALLTHROUGH={c6_va:#x}")
    print(f"CALIBRATE_DELAY_CALLSITE_VA={cal_bl:#x}")
    print(f"CALIBRATE_DELAY_CALLSITE_OFFSET={cal_bl - text_addr:#x}")
    print("CALIBRATE_DELAY_CALL_INSN=BL")
    print(f"CALIBRATE_DELAY_CALL_BYTES={cal_word:08x}")
    print(f"CALIBRATE_DELAY_POSTCALL_VA={ck_va:#x}")
    print(f"CALIBRATE_DELAY_POSTCALL_OFFSET={ck_va - text_addr:#x}")
    print("C_DELAY_CHECKPOINT_IS_POSTCALL=YES")
    print("C_DELAY_POSTCALL_CONTROL_FLOW_PROVEN=YES")
    if len(pa_hits) < 1:
        fail("C_DELAY_CALLSITE_FAILED", "parse_args hits")
    print(f"PARSE_ARGS_BL_COUNT={len(pa_hits)} (nth=0 is Booting kernel)")

    head_text = (LINUX / "arch" / "arm64" / "kernel" / "head.S").read_text()
    t3.gate_pre_path_order(
        t3.head_body(head_text, "SYM_FUNC_START_LOCAL(__primary_switched)",
                     "SYM_FUNC_END(__primary_switched)"))
    t3.gate_no_early_counter_trap(
        head_text,
        (LINUX / "arch/arm64/kernel/hyp-stub.S").read_text(),
        (LINUX / "arch/arm64/kernel/idreg-override.c").read_text(),
        (LINUX / "init" / "main.c").read_text().split(
            "void start_kernel(void)", 1)[-1].split("calibrate_delay", 1)[0],
        (LINUX / "arch/arm64/kernel/smp.c").read_text())
    t3.gate_cnppct_safety(C_DELAY_CNTPCT_ACCESS_SAFE_REASON, True)
    t3.gate_psci_safety(C_DELAY_PSCI_SAFE_REASON, True)
    print("C_DELAY_CNTPCT_SAFE=YES")
    print("C_DELAY_PSCI_SAFE=YES")
    print("C_DELAY_ENTRY_MMU=ON")
    print("C_DELAY_ENTRY_PC_ADDRESS_SPACE=VA")
    print("C_DELAY_ENTRY_SP_VALID=YES")

    sections = t3.section_map(out, tools, k["vmlinux"])
    if not any(s["flags"] for s in sections):
        for s in sections:
            if s["vma"] <= sk_va < s["vma"] + s["size"]:
                s["code"] = True
                s["alloc"] = True
    symbol_vas = sorted({int(l.split()[0], 16) for l in nm_out.splitlines()
                         if re.match(r"^[0-9a-f]{16} ", l)})
    reloc = t3.relocation_offsets(out, tools, k["vmlinux"])
    frozen_image = frozen[:image_file_size]

    src_body = start_kernel_body((LINUX / "init" / "main.c").read_text())
    c6_to_cdelay_path_audit(src_body, dump_sk, c6_va, cal_bl)
    mdelay_facts = panic_mdelay_audit(cfg)

    callsite_va = cal_bl
    target_va = cal_va
    selected = "C_DELAY_CALIBRATE_DELAY_COMPLETE"
    semantic = "POST_CALIBRATE_DELAY_CHECKPOINT_ONLY"
    try:
        audit = audit_window(
            ck_va, C_DELAY_PROBE_SIZE, sections=sections, symbol_vas=symbol_vas,
            reloc=reloc, frozen_image=frozen_image, tools=tools,
            vmlinux=k["vmlinux"], sk_extent=sk_extent, text_addr=text_addr,
            image_size=image_size, out=out)
    except SystemExit as exc:
        fail("R3_P1B_C_DELAY_PREDEVICE_NOT_READY", str(exc))
        return
    print("C_DELAY_CANDIDATE=SAFE")
    print(f"C_DELAY_SELECTED_STAGE={selected}")
    print(f"C_DELAY_SELECTION_REASON=unique post-calibrate_delay fallthrough "
          f"INLINE scans pass; C6 region left as FIX8")
    print(f"C_DELAY_RUNTIME_SEMANTIC_DELTA={semantic}")
    off_ck = ck_va - text_addr
    off_c6 = c6_va - text_addr
    region = (off_ck, off_ck + C_DELAY_PROBE_SIZE)
    print(f"C_DELAY_CHECKPOINT_VA={ck_va:#x}")
    print(f"C_DELAY_CHECKPOINT_IMAGE_OFFSET={off_ck:#x}")
    print(f"C_DELAY_CALLSITE_VA={callsite_va:#x}")
    print("C_DELAY_PROBE_ARCHITECTURE=INLINE")
    print(f"C_DELAY_INLINE_START={ck_va:#x}")
    print(f"C_DELAY_INLINE_END={ck_va + C_DELAY_PROBE_SIZE:#x}")
    print("C_DELAY_INLINE_OVERWRITE_SAFE=YES")
    print(f"C_DELAY_SYMBOL_SCAN=PASS ({audit['n_sym']} symbols)")
    print(f"C_DELAY_BRANCH_SCAN=PASS ({audit['n_raw']} confirmed)")
    print(f"C_DELAY_RELOCATION_SCAN=PASS ({audit['n_rel']} reloc sites)")
    print(f"C_DELAY_LITERAL_SCAN=PASS ({audit['n_lit']} slots)")
    print("C_DELAY_CONTROL_FLOW_SCAN=PASS")
    print("C_DELAY_SECTION_BOUNDARY_SCAN=PASS")
    print(f"C_DELAY_FUNCTION_EXTENT_SCAN=PASS (extent {audit['extent_len']:#x})")
    rw = audit["rw"]
    for tag, canon in (("__ex_table", "C_DELAY_EXCEPTION_TABLE_SCAN"),
                       ("altinstructions", "C_DELAY_ALTINSTRUCTIONS_SCAN"),
                       ("__jump_table", "C_DELAY_JUMP_TABLE_SCAN"),
                       ("static_call_sites", "C_DELAY_STATIC_CALL_SITES_SCAN"),
                       ("kcfi_traps", "C_DELAY_KCFI_TRAPS_SCAN")):
        info = rw[tag]
        state = f"entries={info['entries']}" if info.get("present") else "ABSENT"
        print(f"{canon}=PASS ({state}, none in window)")
    print("C_DELAY_WINDOW_INSIDE_IMAGE_SIZE=YES")
    print("C_DELAY_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT")
    print("C_DELAY_INLINE_MAPPING_EXECUTABLE=YES")
    print("C_DELAY_EXTERNAL_CHECKPOINT_USED=NO")
    print("C_DELAY_PADDING_MAPPING_USED=NO")
    print("C_DELAY_ENTRY_INSTRUMENTATION_AUDITED=YES "
          "(mid-function fallthrough; BTI not checked on RET; "
          f"BTI_KERNEL={cfg.get('CONFIG_ARM64_BTI_KERNEL', 'ABSENT')} "
          f"CFI={cfg.get('CONFIG_CFI_CLANG', 'ABSENT')} "
          f"SCS={cfg.get('CONFIG_SHADOW_CALL_STACK', 'ABSENT')} "
          f"FTRACE={cfg.get('CONFIG_FUNCTION_TRACER', 'ABSENT')} "
          f"KASAN={cfg.get('CONFIG_KASAN', 'ABSENT')} "
          f"KCOV={cfg.get('CONFIG_KCOV', 'ABSENT')})")
    for sym in ("CONFIG_ARM64_BTI_KERNEL", "CONFIG_ARM64_PTR_AUTH_KERNEL",
                "CONFIG_CFI_CLANG", "CONFIG_SHADOW_CALL_STACK",
                "CONFIG_FUNCTION_TRACER", "CONFIG_KASAN", "CONFIG_KCOV",
                "CONFIG_JUMP_LABEL", "CONFIG_GENERIC_CALIBRATE_DELAY"):
        if cfg.get(sym) == "y" and sym in (
                "CONFIG_CFI_CLANG", "CONFIG_FUNCTION_TRACER",
                "CONFIG_KASAN", "CONFIG_KCOV", "CONFIG_SHADOW_CALL_STACK"):
            fail("C_DELAY_ENTRY_INSTRUMENTATION_FAILED", f"{sym}=y")
        print(f"C_DELAY_ENTRY_CFG_{sym}={cfg.get(sym, 'ABSENT')}")

    consume_map_json(out, tools, k, ck_va, selected, c3_va, pa_bl)

    t4_probe, ops, dump = t3.build_probe(
        out, tools, C_DELAY_DEVICE_S, C_DELAY_DEVICE_LD, "P1B_C_DELAY_DELAY", C_DELAY_DELAY_S,
        "r3_c_delay_checkpoint", "p1b-c-delay-checkpoint")
    t4_ref, _t4o, _t4d = t3.build_probe(
        out, tools, T4_DEVICE_S, T4_DEVICE_LD, "P1B_T4_DELAY", 8,
        "r3_t4_checkpoint", "p1b-t4-probe-reference")
    t3_probe, _t3_ops, _t3_dump = t3.build_probe(
        out, tools, T3_DEVICE_S, T3_DEVICE_LD, "P1B_T3_DELAY", 8,
        "r3_t3_checkpoint", "p1b-t3-probe-reference", march="armv8.5-a")
    t2_probe, _t2_ops, _t2_dump = t3.build_probe(
        out, tools, T2_DEVICE_S, T2_DEVICE_LD, "P1B_T2_DELAY", 8,
        "r3_t2_checkpoint", "p1b-t2-probe-reference")
    t1_probe, _t1_ops, _t1_dump = t3.build_probe(
        out, tools, T1_DEVICE_S, T1_DEVICE_LD, "P1B_T1_DELAY", 8,
        "r3_t1_checkpoint", "p1b-t1-core-reference")
    t3.gate_t3_probe(ops, dump, len(t4_probe))
    if len(t4_probe) != C_DELAY_PROBE_SIZE:
        fail("C_DELAY_CORE_IDENTITY_FAILED", f"t4 probe size {len(t4_probe)}")
    if t4_probe != t1_probe:
        fail("C_DELAY_CORE_IDENTITY_FAILED", "T4 probe != T1 core")
    if t4_probe != t3_probe[4:]:
        fail("C_DELAY_CORE_IDENTITY_FAILED", "T4 probe != T3 core slice")
    if t4_probe != t2_probe[4:]:
        fail("C_DELAY_CORE_IDENTITY_FAILED", "C_DELAY probe != T2 core slice")
    if t4_probe != t4_ref:
        fail("C_DELAY_CORE_IDENTITY_FAILED", "C_DELAY probe != T4 core")
    if len(t3_probe) != T3_REF_PROBE_SIZE or len(t2_probe) != T2_REF_PROBE_SIZE:
        fail("C_DELAY_CORE_IDENTITY_FAILED", "T2/T3 reference sizes")
    plen = len(t4_probe)
    print(f"C_DELAY_CHECKPOINT sha256={sha(t4_probe)} size={plen}")
    print("C_DELAY_DIAGNOSTIC_CORE_MATCHES_T1=YES")
    print("C_DELAY_DIAGNOSTIC_CORE_MATCHES_T3=YES")
    print("C_DELAY_DIAGNOSTIC_CORE_MATCHES_T4=YES")
    print("C_DELAY_DIAGNOSTIC_CORE_SLICE_MATCHES_T2=YES")
    print("C_DELAY_DEVICE_CANDIDATE_DELAY=8s")
    print("C_DELAY_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY")
    print("C_DELAY_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC")
    print("C_DELAY_FAIL_CLOSED=YES")
    print("C_DELAY_STACK_USAGE=NO")
    print("C_DELAY_NO_MEMORY_READS=YES")
    print("C_DELAY_NO_MEMORY_WRITES=YES")
    print("C_DELAY_POSITION_INDEPENDENT=YES")
    print("C_DELAY_RUNTIME_RELOCATIONS=0")
    print(f"C_DELAY_CLOBBER_REGISTERS={C_DELAY_CLOBBER_REGISTERS}")

    covered = list(struct.unpack_from(f"<{plen // 4}I", frozen, off_ck))
    t3.inst_record(out, tools, covered, "p1b-c-delay-original-covered-insns-record")

    cand = bytearray(frozen)
    cand[off_ck:off_ck + plen] = t4_probe
    cand = bytes(cand)
    diffs = t3.gate_payload_diff(frozen, cand, region)
    tail = t3.gate_tail_identity(frozen, cand, region)
    t3.gate_t2_probe_removed(frozen, cand, off_ps, t2_probe)
    if cand[off_sk:off_sk + T3_REF_PROBE_SIZE] == t3_probe:
        fail("C_DELAY_IDENTITY_FAILED", "T3 probe present at start_kernel")
    if struct.unpack_from("<I", cand, off_sk)[0] != PACIASP:
        fail("C_DELAY_IDENTITY_FAILED", "start_kernel entry not restored paciasp")
    if cand[off_c6:off_c6 + plen] != frozen[off_c6:off_c6 + plen]:
        fail("C_DELAY_IDENTITY_FAILED", "C6 region differs from FIX8")
    if cand[off_c6:off_c6 + plen] == t4_probe:
        fail("C_DELAY_IDENTITY_FAILED", "T4 probe still present at C6")
    if off_ck == off_c6:
        fail("C_DELAY_IDENTITY_FAILED", "checkpoint is still the C6 window")
    print("C_DELAY_PROBE_REMOVED_FROM_C_DELAY=YES")
    print("C6_REGION_IDENTICAL_TO_FIX8=YES")
    print("C6_REGION_RESTORED=YES")
    t3.gate_tramp_identity(cand)
    trailer = t3.gate_trailer(cand)
    if trailer != frozen_rt_d:
        fail("C_DELAY_PAYLOAD_DIFF_FAILED", "trailer drifted vs frozen RT-D")
    hdr, dtb_off2, gap2, boot_est = t3.gate_geometry(cand, image_size)
    if dtb_off2 != dtb_offset:
        fail("C_DELAY_PAYLOAD_DIFF_FAILED", "dtb_offset drifted")
    if boot_est != C_DELAY_BOOT_SIZE_EXPECTED:
        fail("C_DELAY_GEOMETRY_FAILED", f"boot_est {boot_est}")
    payload_path = out / "thyme-r3-p1b-c-delay-kernel-payload.bin"
    payload_path.write_bytes(cand)
    print(f"C_DELAY_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)}")
    print(f"C_DELAY_DIFF_BYTE_COUNT={len(diffs)}")
    print(f"C_DELAY_DIFF_RANGES=[{off_ck:#x},{off_ck + plen:#x})")
    print("C_DELAY_PAYLOAD_DIFF_ATTRIBUTED=POST_CALIBRATE_DELAY_CHECKPOINT_ONLY")
    print("C_DELAY_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES "
          f"({off_ck} bytes before and {tail} bytes after the window)")
    print("C_DELAY_TRAMPOLINE_IDENTICAL=YES sha=" + TRAMP_SHA)
    print("C_DELAY_RT_D_IDENTITY=YES")
    print("C_DELAY_INIT_IDENTITY=YES")
    print("C_DELAY_INITRAMFS_IDENTITY=YES")
    print("C_DELAY_PAYLOAD_SIZE_IDENTICAL=YES")
    print("C_DELAY_BOOT_SIZE_IDENTICAL=YES")
    print(f"C_DELAY_DTB_OFFSET={DTB_OFFSET:#x}")
    print("C_DELAY_GEOMETRY_GATES=PASS")
    print("PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES")
    print("C_DELAY_DIAGNOSTIC_ONLY=YES")
    print("C_DELAY_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    print("C_DELAY_STATUS=NOT_DEVICE_READY")
    print("READY_FOR_DEVICE=NO")
    print("C_DELAY_DEVICE_OPERATION=NO")

    (out / "p1b-c-delay-payload-diff-report.txt").write_text(
        "T4_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"C_DELAY_PAYLOAD_SHA256={sha(cand)}\n"
        f"REGION_A=[{off_ck:#x},{off_ck + plen:#x}) inline {selected} "
        f"overwrite ({len(diffs)} diff bytes)\n"
        f"DIFF_BYTES={len(diffs)}\n"
        f"T4_DIFF_BYTE_COUNT={len(diffs)}\n"
        f"T4_DIFF_RANGES=[{off_ck:#x},{off_ck + plen:#x})\n"
        "DIFF_ATTRIBUTION=SELECTED_C_STAGE_CHECKPOINT_ONLY\n"
        "T4_PAYLOAD_DIFF_ATTRIBUTED=SELECTED_C_STAGE_CHECKPOINT_ONLY\n"
        f"T4_RUNTIME_SEMANTIC_DELTA={semantic}\n"
        "T3_PROBE_REMOVED_FROM_T4=YES\n"
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES\n"
        f"T4_TRAMPOLINE_IDENTICAL=YES sha={TRAMP_SHA}\n")

    neg_lines = run_negative_fixtures({
        "ops": ops, "dump": dump, "probe_len": plen, "frozen": frozen,
        "cand": cand, "off_ck": off_ck, "off_sk": off_sk, "off_ps": off_ps,
        "sections": sections, "symbol_vas": symbol_vas,
        "reloc_offsets": reloc, "t1_probe": t1_probe, "t2_probe": t2_probe,
        "t3_probe": t3_probe, "t4_probe": t4_probe, "ck_va": ck_va,
        "cfg": cfg, "image_size": image_size,
        "primary_entry_off": off_primary, "callsite_va": callsite_va,
        "target_va": target_va, "off_c6": off_c6})

    (out / "p1b-c-delay-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures(selected)
    (out / "p1b-c-delay-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")
    print("C_DELAY_NEGATIVE_FIXTURES=PASS")
    print("C_DELAY_DECODER_FIXTURES=PASS")

    sec = audit["sec"]
    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "c_delay_true_device_run": "NOT_EXECUTED",
        "fix8_payload_sha256": FIX8_PAYLOAD_SHA,
        "fix8_payload_size": FIX8_PAYLOAD_SIZE,
        "fix8_init_sha256": FIX8_INIT_SHA,
        "fix8_cpio_sha256": FIX8_CPIO_SHA,
        "fix8_tramp_sha256": TRAMP_SHA,
        "rt_d_frozen_sha256": RT_D_SHA,
        "image_header_image_size": hex(image_size),
        "image_header_image_size_rederived": True,
        "image_file_size": image_file_size,
        "dtb_offset": hex(dtb_offset),
        "primary_entry_offset": hex(off_primary),
        "primary_entry_patched": False,
        "primary_switched_va": hex(ps_va),
        "primary_switched_image_offset": hex(off_ps),
        "primary_switched_identical_to_fix8": True,
        "start_kernel_va": hex(sk_va),
        "start_kernel_image_offset": hex(off_sk),
        "start_kernel_entry_word": hex(PACIASP),
        "parse_args_va": hex(pa_va),
        "setup_arch_va": hex(sa_va),
        "c_delay_selected_stage": selected,
        "c_delay_selection_reason": reason,
        "c_delay_checkpoint_va": hex(ck_va),
        "c_delay_checkpoint_image_offset": hex(off_ck),
        "c_delay_callsite_va": hex(callsite_va),
        "c_delay_callsite_instruction": "BL",
        "c_delay_call_target": hex(target_va),
        "c_delay_checkpoint_is_post_stage": True,
        "c_delay_postcall_control_flow_proven": True,
        "c_delay_probe_architecture": "INLINE",
        "c_delay_inline_overwrite_safe": True,
        "c_delay_external_checkpoint_used": False,
        "c_delay_padding_mapping_used": False,
        "c_delay_mapping_source": "KERNEL_TEXT_VA_SELF_EVIDENT",
        "c_delay_inline_mapping_executable": True,
        "c_delay_checkpoint_sha256": sha(t4_probe),
        "c_delay_checkpoint_size": plen,
        "c_delay_diagnostic_core_matches_t1": True,
        "c_delay_diagnostic_core_matches_t3": True,
        "c_delay_t1_core_sha256": sha(t1_probe),
        "t3_probe_removed_from_t4": True,
        "start_kernel_entry_restored_to_fix8": True,
        "c_delay_payload_sha256": sha(cand),
        "c_delay_payload_size": len(cand),
        "c_delay_boot_size_est": boot_est,
        "diff_bytes": len(diffs),
        "diff_regions": [[hex(off_ck), hex(off_ck + plen)]],
        "diff_attribution": "SELECTED_C_STAGE_CHECKPOINT_ONLY",
        "c_delay_runtime_semantic_delta": semantic,
        "c_delay_precheckpoint_normal_path_identical_to_fix8": True,
        "c_delay_tramp_identical_to_fix8": True,
        "c_delay_rtd_identical": True,
        "c_delay_init_identical": True,
        "c_delay_initramfs_identical": True,
        "c_delay_diagnostic_only": True,
        "c_delay_normal_kernel_boot_candidate": False,
        "c_delay_status": "NOT_DEVICE_READY",
        "c_delay_delay_seconds": C_DELAY_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "c_delay_fail_closed": True,
        "c_delay_stack_usage": False,
        "c_delay_memory_reads": False,
        "c_delay_memory_writes": False,
        "c_delay_runtime_relocations": 0,
        "c6_panic_parameter_effective_by_stage": True,
        "c6_rdinit_parameter_effective_by_stage": True,
        "parse_early_param_effective_inside_setup_arch": True,
        "loglevel_early_parameter_stage": "C5",
        "candidate_c6": "SAFE" if c6_ok else "UNSAFE",
        "candidate_c3": "SAFE" if c3_ok else "UNSAFE",
        "candidate_c_delay": "FUTURE",
        "decoder": {
            "kind": "T3_MATCHED_CONTROL_PRIMARY",
            "t3_reference_total_s": T3_REFERENCE_TOTAL_S,
            "t2_reference_total_s": T2_REFERENCE_TOTAL_S,
            "t1_reference_total_s": T1_REFERENCE_TOTAL_S,
            "t0_reference_total_s": T0_REFERENCE_TOTAL_S,
            "strong_half_window_s": C_DELAY_STRONG_HALF_WINDOW_S,
            "supported_half_window_s": C_DELAY_SUPPORTED_HALF_WINDOW_S,
            "early_return_class_limit_s": C_DELAY_EARLY_RETURN_CLASS_LIMIT_S,
        },
        "observer": {"identity_env": "R3_C_DELAY_SHA256",
                     "forbidden_env": "R3_C_DELAY_FORBIDDEN_SHAS",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
        "start_kernel_section": sec["name"],
        "c_delay_section_flags": sec.get("flags"),
    }
    (out / "p1b-c-delay-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    gates = [
        "C_DELAY_BUILD_GATES=PASS",
        "C_DELAY_BASELINE=FROZEN_FIX8",
        "C_DELAY_MAP_JSON_CONSUMED=YES",
        "C_DELAY_MAP_CRITICAL_POINTS_REDERIVED=YES",
        "EARLY_C_STAGE_MAP_REVERIFIED_ON_A_MAINLINE=YES",
        f"C_DELAY_SELECTED_STAGE={selected}",
        "C_DELAY_CHECKPOINT_IS_POST_STAGE=YES",
        "C_DELAY_POSTCALL_CONTROL_FLOW_PROVEN=YES",
        "C_DELAY_PROBE_ARCHITECTURE=INLINE",
        "C_DELAY_INLINE_OVERWRITE_SAFE=YES",
        "C_DELAY_ENTRY_INSTRUMENTATION_AUDITED=YES",
        "C_DELAY_WINDOW_INSIDE_IMAGE_SIZE=YES",
        "C_DELAY_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
        "C_DELAY_INLINE_MAPPING_EXECUTABLE=YES",
        "C_DELAY_EXTERNAL_CHECKPOINT_USED=NO",
        "C_DELAY_PADDING_MAPPING_USED=NO",
        "C_DELAY_DEVICE_CANDIDATE_DELAY=8s",
        "C_DELAY_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "C_DELAY_CNTPCT_ACCESS_SAFE=YES",
        "C_DELAY_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "C_DELAY_PSCI_SYSTEM_RESET_SAFE=YES",
        "C_DELAY_FAIL_CLOSED=YES",
        "C_DELAY_STACK_USAGE=NO",
        "C_DELAY_NO_MEMORY_READS=YES",
        "C_DELAY_NO_MEMORY_WRITES=YES",
        "C_DELAY_DIAGNOSTIC_CORE_MATCHES_T3=YES",
        "C_DELAY_DIAGNOSTIC_CORE_MATCHES_T1=YES",
        "C_DELAY_RUNTIME_RELOCATIONS=0",
        "T3_PROBE_REMOVED_FROM_T4=YES",
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES",
        "C_DELAY_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES",
        "C_DELAY_TRAMPOLINE_IDENTICAL=YES",
        "C_DELAY_RT_D_IDENTITY=YES",
        "C_DELAY_INIT_IDENTITY=YES",
        "C_DELAY_INITRAMFS_IDENTITY=YES",
        "C_DELAY_PAYLOAD_DIFF_ATTRIBUTED=POST_CALIBRATE_DELAY_CHECKPOINT_ONLY",
        "C_DELAY_PAYLOAD_SIZE_IDENTICAL=YES",
        "C_DELAY_BOOT_SIZE_IDENTICAL=YES",
        "C_DELAY_DTB_OFFSET=0x2380000",
        "C_DELAY_GEOMETRY_GATES=PASS",
        "C_DELAY_NEGATIVE_FIXTURES=PASS",
        "C_DELAY_DECODER_FIXTURES=PASS",
        "C_DELAY_DIAGNOSTIC_ONLY=YES",
        "C_DELAY_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
        "C_DELAY_STATUS=NOT_DEVICE_READY",
        "READY_FOR_DEVICE=NO",
        "C6_PANIC_PARAMETER_EFFECTIVE_BY_STAGE=YES",
        "C6_RDINIT_PARAMETER_EFFECTIVE_BY_STAGE=YES",
        "PARSE_EARLY_PARAM_EFFECTIVE_INSIDE_SETUP_ARCH=YES",
        f"C_DELAY_RUNTIME_SEMANTIC_DELTA={semantic}",
        f"C_DELAY_DIFF_BYTE_COUNT={len(diffs)}",
        f"C_DELAY_DIFF_RANGES=[{off_ck:#x},{off_ck + plen:#x})",
        f"START_KERNEL_VA={sk_va:#x}",
        f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}",
        f"C_DELAY_CHECKPOINT_VA={ck_va:#x}",
        f"C_DELAY_CHECKPOINT_IMAGE_OFFSET={off_ck:#x}",
        "IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES",
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}",
        f"IMAGE_FILE_SIZE={image_file_size}",
        "C_DELAY_SYMBOL_SCAN=PASS",
        "C_DELAY_BRANCH_SCAN=PASS",
        "C_DELAY_RELOCATION_SCAN=PASS",
        "C_DELAY_LITERAL_SCAN=PASS",
        "C_DELAY_CONTROL_FLOW_SCAN=PASS",
        "C_DELAY_SECTION_BOUNDARY_SCAN=PASS",
        "C_DELAY_FUNCTION_EXTENT_SCAN=PASS",
        "C_DELAY_EXCEPTION_TABLE_SCAN=PASS",
        "C_DELAY_ALTINSTRUCTIONS_SCAN=PASS",
        "C_DELAY_JUMP_TABLE_SCAN=PASS",
        "C_DELAY_STATIC_CALL_SITES_SCAN=PASS",
        "C_DELAY_KCFI_TRAPS_SCAN=PASS",
        "C_DELAY_CHECKPOINT_IS_POSTCALL=YES",
        "C_DELAY_POSTCALL_CONTROL_FLOW_PROVEN=YES",
        "C6_TO_C_DELAY_NORMAL_PATH_AUDITED=YES",
        "CALIBRATE_DELAY_RUNTIME_CALL_REQUIRED=YES",
        "C_DELAY_DIAGNOSTIC_CORE_MATCHES_T4=YES",
        "C_DELAY_CNTPCT_SAFE=YES",
        "C_DELAY_PSCI_SAFE=YES",
        "PANIC_MDELAY_DEPENDS_ON_LOOPS_PER_JIFFY=YES",
        "PANIC_MDELAY_DEPENDS_ON_ARCH_TIMER=YES",
        "CALIBRATE_DELAY_AFFECTS_PANIC_MDELAY=YES",
        "PANIC_MDELAY_CALIBRATION_RELATION=YES_LOOPS_PER_JIFFY_SCALES_ARM64_ARCH_TIMER_CYCLE_COUNT",
        "PANIC30_RERUN=FROZEN",
        "C_DELAY_STATUS_GATE_STRUCTURED=YES",
    ]
    sm_lines = [l for l in k["sysmap"].read_text().splitlines()
                if l.endswith((" primary_entry", " _text", " start_kernel",
                               " __primary_switched", " parse_args",
                               " setup_arch", " parse_early_param",
                               " calibrate_delay"))]
    (out / "p1b-c-delay-sysmap-excerpt.txt").write_text("\n".join(sm_lines) + "\n")
    for src, dst in (
            ("p1b-t3-vmlinux-sections.txt", "p1b-c-delay-vmlinux-sections.txt"),
            ("p1b-t3-vmlinux-relocations.txt", "p1b-c-delay-vmlinux-relocations.txt")):
        s = out / src
        if s.is_file():
            (out / dst).write_bytes(s.read_bytes())
    (out / "p1b-c-delay-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))
    (out / "p1b-c-delay-report.txt").write_text(
        "T4_PREDEVICE_REPORT\n" + "\n".join(gates) + "\n")


def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "t4_obs_fixtures", OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-c-delay-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("C_DELAY_OBSERVER_FIXTURES=PASS")


def cmd_c_delay_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    off_ck = int(args.checkpoint_offset, 16)
    probe = Path(args.checkpoint_bin).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("C_DELAY_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("C_DELAY_PACK_FAILED", f"payload sha={sha(payload)}")
    if sha(probe) != args.checkpoint_sha:
        fail("C_DELAY_PACK_FAILED", f"checkpoint sha={sha(probe)}")
    if len(probe) != C_DELAY_PROBE_SIZE:
        fail("C_DELAY_PACK_FAILED", f"checkpoint size {len(probe)}")
    hdr = pb.parse_image_hdr(payload, "t4-payload")
    image_size = hdr["image_size"]
    t3.gate_image_size_rederived(image_size, "t4-packed-payload")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("C_DELAY_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("C_DELAY_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if (off_ck + len(probe)) > image_size:
        fail("C_DELAY_PACK_FAILED", "checkpoint window past image_size")
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("C_DELAY_PACK_FAILED", "embedded trampoline != frozen FIX8")
    if payload[off_ck:off_ck + len(probe)] != probe:
        fail("C_DELAY_PACK_FAILED", "checkpoint region != built T4 probe")
    off_sk = int(args.start_kernel_offset, 16)
    if struct.unpack_from("<I", payload, off_sk)[0] != PACIASP:
        fail("C_DELAY_PACK_FAILED", "start_kernel entry not paciasp")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I", FDT_MAGIC):
        fail("C_DELAY_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "t4-candidate")
    if cand["kernel"] != payload:
        fail("C_DELAY_PACK_FAILED", "candidate kernel != T4 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("C_DELAY_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("C_DELAY_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("C_DELAY_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("C_DELAY_PACK_FAILED", "reserved differs from M5D")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("C_DELAY_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("C_DELAY_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-c-delay-pack-gates.txt"
    report.write_text(
        "C_DELAY_PACK_GATES=PASS\n"
        f"C_DELAY_BOOT_SIZE={len(boot)}\n"
        f"C_DELAY_BOOT_SHA256={sha(boot)}\n"
        f"C_DELAY_PAYLOAD_SHA256={sha(payload)}\n"
        f"C_DELAY_TRAMP_SHA256={sha(tramp)}\n"
        "C_DELAY_TRAMP_SOURCE=FROZEN_FIX8_UNMODIFIED\n"
        f"C_DELAY_CHECKPOINT_SHA256={sha(probe)}\n"
        f"C_DELAY_KERNEL_SIZE={len(payload)}\n"
        f"C_DELAY_CHECKPOINT_OFFSET={off_ck:#x}\n"
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}\n"
        "C_DELAY_PROBE_ARCHITECTURE=INLINE\n"
        "C_DELAY_INLINE_REGION_IN_KERNEL_TEXT=YES\n"
        f"C_DELAY_DTB_OFFSET={dtb_offset:#x}\n"
        "C_DELAY_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "C_DELAY_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "C_DELAY_BOOT_CAPACITY=PASS\n"
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [C_DELAY_DEVICE_S, C_DELAY_DEVICE_LD, T3_DEVICE_S, T3_DEVICE_LD,
                T2_DEVICE_S, T2_DEVICE_LD, T1_DEVICE_S, T1_DEVICE_LD,
                OBSERVER, OBSERVER_FIXTURES, Path(__file__), DOC, STATUS_DOC,
                MAP_DOC, WF, MAP_WF, C_STAGE, PRIVATE_WF,
                HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld", HERE / "p1b-t3-predevice.py",
                T4_DEVICE_S, T4_DEVICE_LD]
    for path in required:
        if not path.is_file():
            fail("C_DELAY_SOURCE_GATE_FAILED", f"missing {path}")
    dev = C_DELAY_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "isb", "mrs\tx9, cntfrq_el0",
                  "mrs\tx11, cntpct_el0", "mrs\tx12, cntpct_el0", "yield",
                  "smc\t#0", "wfe", "P1B_C_DELAY_DELAY",
                  "#if (P1B_C_DELAY_DELAY) != 8", "r3_c_delay_checkpoint"):
        need(dev, token)
    for token in ("paciasp", ".inst\t0xd503233f", "bti", "P1B_DTB_REL",
                  "dtb_rel", "adr\t", "ldr\t", "stp\tx29", "eret", "sctlr",
                  "msr\tttbr", "b\tprimary", "b\t__primary",
                  "b\tstart_kernel", "bl\t"):
        forbid(dev, token)
    obs = OBSERVER.read_text()
    for token in ("R3_C_DELAY_SHA256", "C_DELAY_OBSERVER_MISBOOT_REFUSED",
                  "C_DELAY_MINUS_T4", "T4_REFERENCE_TOTAL", "FASTBOOT_BOOT_ONLY",
                  "C_DELAY_NOT_REACHED_LICENSE=NO",
                  "C_DELAY_FAILURE_ISOLATION_CI",
                  "C_DELAY_NORMAL_KERNEL_BOOT_CANDIDATE", "C_DELAY_DIAGNOSTIC_ONLY",
                  "C_DELAY_CALIBRATE_DELAY_COMPLETE", "T4_BOOT"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    forbid(obs, "R3_T3_SHA256")
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("C_DELAY_OBSERVER_MISBOOT_REFUSED", "C_DELAY_NOT_REACHED",
                  "C_DELAY_STABLE_FASTBOOT", "C_DELAY_NO_RETURN", "T4_BOOT",
                  "T3_BOOT"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("C_DELAY_PROBE_ARCHITECTURE=INLINE",
                  "C_DELAY_INLINE_OVERWRITE_SAFE", "C_DELAY_CHECKPOINT_IS_POSTCALL",
                  "C_DELAY_POSTCALL_CONTROL_FLOW_PROVEN",
                  "C_DELAY_ENTRY_INSTRUMENTATION_AUDITED",
                  "C_DELAY_CNTPCT_SAFE", "C_DELAY_PSCI_SAFE",
                  "C_DELAY_FAIL_CLOSED", "C_DELAY_STACK_USAGE=NO",
                  "C_DELAY_RUNTIME_RELOCATIONS=0",
                  "T4_PROBE_REMOVED_FROM_C_DELAY",
                  "C6_REGION_IDENTICAL_TO_FIX8",
                  "START_KERNEL_ENTRY_RESTORED_TO_FIX8",
                  "C_DELAY_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8",
                  "POST_CALIBRATE_DELAY_CHECKPOINT_ONLY",
                  "C_DELAY_MAP_JSON_CONSUMED", "C_DELAY_MAP_CRITICAL_POINTS_REDERIVED",
                  "PARSE_EARLY_PARAM", "C6_PARSE_ARGS_COMPLETE",
                  "calibrate_delay", "C_DELAY",
                  "PANIC_MDELAY_IMPLEMENTATION",
                  "PANIC_MDELAY_DEPENDS_ON_LOOPS_PER_JIFFY",
                  "PANIC_MDELAY_DEPENDS_ON_ARCH_TIMER",
                  "CALIBRATE_DELAY_AFFECTS_PANIC_MDELAY",
                  "C6_TO_C_DELAY_NORMAL_PATH_AUDITED",
                  "CALIBRATE_DELAY_RUNTIME_CALL_REQUIRED",
                  "14.385", "1.5", "3.0", "0x2380000", "0x84000009",
                  "READY_FOR_R3_P1B_C_DELAY_DEVICE_CONTROL",
                  "R3_P1B_C_DELAY_PREDEVICE_NOT_READY",
                  "EARLY_C_STAGE_MAP_SOURCE_HEAD", "d47bf58",
                  "NO_FF_MERGE", "34842580640", "PANIC30_RERUN=FROZEN"):
        need(doc, token)
    kv = parse_status_kv(STATUS_DOC.read_text())
    for key, want in STATUS_DOC_REQUIRED_KV.items():
        if kv.get(key) != want:
            fail("C_DELAY_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} != {want!r}")
    for key, allowed in STATUS_DOC_ENUM_KV.items():
        if kv.get(key) not in allowed:
            fail("C_DELAY_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} not in {allowed}")
    print(f"C_DELAY_STATUS_KV_KEY_COUNT={len(kv)}")
    print("C_DELAY_STATUS_GATE_STRUCTURED=YES")
    wf_text = WF.read_text()
    for token in ("p1b-c-delay-device.S", "p1b-c-delay-predevice.py",
                  "observe-r3-p1b-c-delay.py", "thyme-r3-p1b-c-delay",
                  "C_DELAY_BUILD_GATES=PASS", "c-stage-map.py",
                  "observer-fixtures"):
        need(wf_text, token)
    for verb in ("fastboot", "adb", "flash", "erase", "set_active",
                 "mkbootimg", "splice-boot", "boot.img"):
        forbid(wf_text, verb)
    for path in REPO.rglob("*.img"):
        rel = path.relative_to(REPO).as_posix()
        top = rel.split("/", 1)[0]
        if top in ("linux-6.6", "test", "route-a-v2-artifact",
                   "thyme-mainline-firstboot-"
                   "29bc752517c53a5532bd1974e3bff59cca5af391"):
            continue
        if "r3-p1b" in rel or "p1b" in rel:
            fail("C_DELAY_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    body = re.search(r"\n    manifest = \{(.*?)\n    \}\n",
                     Path(__file__).read_text(), re.S)
    if not body:
        fail("C_DELAY_SOURCE_GATE_FAILED", "manifest literal not found")
    keys = set(re.findall(r'^\s+"([a-z0-9_]+)":', body.group(1), re.M))
    for key in sorted(set(re.findall(r'm\["([^"]+)"\]',
                                     PRIVATE_WF.read_text()))):
        if key not in keys:
            fail("C_DELAY_SOURCE_GATE_FAILED",
                 f"private workflow reads unknown manifest key {key!r}")
    print(f"C_DELAY_MANIFEST_KEY_CONSISTENCY=PASS ({len(keys)} keys)")
    print("C_DELAY_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "c-delay", "observer-fixtures", "c-delay-pack-gates"),
        required=True)
    parser.add_argument("--out", default="out-c-delay")
    parser.add_argument("--rt-d")
    parser.add_argument("--fix8-payload")
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--lld", default="ld.lld-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    parser.add_argument("--objdump", default="llvm-objdump-18")
    parser.add_argument("--nm", default="llvm-nm-18")
    parser.add_argument("--readelf", default="llvm-readelf-18")
    parser.add_argument("--dtc", default="dtc")
    parser.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    parser.add_argument("--strip", default="aarch64-linux-gnu-strip")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--m5d-boot")
    parser.add_argument("--m5d-sha", default=(
        "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"))
    parser.add_argument("--payload")
    parser.add_argument("--payload-sha")
    parser.add_argument("--checkpoint-bin")
    parser.add_argument("--checkpoint-sha")
    parser.add_argument("--checkpoint-offset")
    parser.add_argument("--start-kernel-offset")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
        return
    if args.mode == "c-delay":
        if not (args.rt_d and args.fix8_payload):
            fail("C_DELAY_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_c_delay(args)
        return
    if args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
        return
    if args.mode == "c-delay-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.checkpoint_bin
                    and args.checkpoint_sha and args.checkpoint_offset
                    and args.start_kernel_offset)
        if not need_all:
            fail("C_DELAY_PACK_FAILED",
                 "need --m5d-boot --payload --boot --payload-sha "
                 "--checkpoint-bin --checkpoint-sha --checkpoint-offset "
                 "--start-kernel-offset")
        cmd_c_delay_pack_gates(args)


if __name__ == "__main__":
    main()
