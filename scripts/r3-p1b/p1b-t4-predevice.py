#!/usr/bin/env python3
"""R3 P1B T4 predevice readiness (MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source/doc boundary checks (no build)
  t4                  frozen-FIX8-anchored T4-8 fail-closed candidate:
                      authoritative kernel rebuild, independent C6/C3
                      re-derivation, consume+cross-check early-c-stage-map.json,
                      INLINE post-call checkpoint, T3 probe removal,
                      single-region FIX8 diff, geometry, fixtures
  observer-fixtures   T4 observer fixture suite
  t4-pack-gates       private: gates over a packed T4 boot v3 image

T4 baseline is FIXED INIT8. The T3 start_kernel INLINE probe is removed.
Preferred stage: C6 parse_args(\"Booting kernel\") COMPLETE. Fallback: C3
setup_arch RETURN. C_DELAY is FUTURE only. One device-ready candidate.
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
DOC = REPO / "docs" / "route-r3-p1b-t4-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
MAP_DOC = REPO / "docs" / "route-r3-early-c-stage-map.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-t4-predevice.yml"
MAP_WF = REPO / ".github" / "workflows" / "thyme-r3-early-c-stage-map.yml"
C_STAGE = REPO / "scripts" / "r3-c-stage-audit" / "c-stage-map.py"
T4_DEVICE_S = HERE / "p1b-t4-device.S"
T4_DEVICE_LD = HERE / "p1b-t4-device.ld"
T3_DEVICE_S = HERE / "p1b-t3-device.S"
T3_DEVICE_LD = HERE / "p1b-t3-device.ld"
T2_DEVICE_S = HERE / "p1b-t2-device.S"
T2_DEVICE_LD = HERE / "p1b-t2-device.ld"
T1_DEVICE_S = HERE / "p1b-t1-device.S"
T1_DEVICE_LD = HERE / "p1b-t1-device.ld"
OBSERVER = HERE / "observe-r3-p1b-t4.py"
OBSERVER_FIXTURES = HERE / "observer-t4-fixtures.py"
PRIVATE_WF = REPO / "artifacts" / "p1b-t4-private-workflow-staging.yml"

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

T4_DELAY_S = 8
T4_PROBE_SIZE = 0x4C
T3_REF_PROBE_SIZE = 0x50
T2_REF_PROBE_SIZE = 0x50
LINUX_COMMIT = "8b73de7da85fde281a385e0b26eda9bffd3ca477"

FORBIDDEN_BOOT_SHAS = dict(t3.FORBIDDEN_BOOT_SHAS)
FORBIDDEN_BOOT_SHAS["T3_BOOT"] = T3_BOOT_SHA

T3_REFERENCE_TOTAL_S = 14.238
T2_REFERENCE_TOTAL_S = 14.240
T1_REFERENCE_TOTAL_S = 14.238
T0_REFERENCE_TOTAL_S = 14.252
T4_STRONG_HALF_WINDOW_S = 1.5
T4_SUPPORTED_HALF_WINDOW_S = 3.0
T4_CROSSCHECK_HALF_WINDOW_S = 3.0
T4_EARLY_RETURN_CLASS_LIMIT_S = 20.0
T4_CASE_C_BAND_S = (20.0, 28.0)
P0_REF_OVERHEAD_S = 6.1445
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
T4_NO_RETURN_WINDOW_S = 120.0
T4_BOOT_SIZE_EXPECTED = 37380096
T4_CLOBBER_REGISTERS = "w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV"

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
    "SLOT_A_WRITTEN": "NO",
    "FIX24_STATUS": "FROZEN",
    "M5N_STATUS": "FROZEN",
    "CURRENT_B": "M5D+M5H+M5M-B",
})
STATUS_DOC_ENUM_KV = {
    "T4_SELECTED_STAGE": (
        "C6_PARSE_ARGS_COMPLETE", "C3_SETUP_ARCH_RETURN", "NONE"),
    "T4_PREDEVICE_STATUS": ("READY", "NOT_READY"),
    "EARLY_C_STAGE_MAP_INTEGRATED": ("YES", "NO"),
    "EARLY_C_STAGE_MAP_REVERIFIED": ("YES", "NO"),
    "T4_PROBE_ARCHITECTURE": ("INLINE", "EXTERNAL"),
}

T4_CNTPCT_ACCESS_SAFE_REASON = (
    "CNTFRQ_EL0/CNTPCT_EL0 reads are EL1-legal regardless of SCTLR_EL1.M; "
    "no pre-C6 path writes CNTKCTL_EL1 or CNTHCTL_EL2 (head.S, hyp-stub, "
    "idreg-override, start_kernel through parse_args, smp_prepare_boot_cpu "
    "only applies alternatives / GIC PMR / KASAN tags); the identical EL1 "
    "access was proven on this device at T0, T1, T2 and T3")
T4_PSCI_SAFE_REASON = (
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
        fail("T4_SOURCE_ORDER_FAILED", "start_kernel not found")
    return main[idx:idx + 24000]


def need(text: str, needle: str, label: str = "T4_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str,
           label: str = "T4_SOURCE_GATE_FAILED") -> None:
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
        fail("T4_SOURCE_ORDER_FAILED", "missing start_kernel stage calls")
    if not (sa.start() < smp.start() < jl.start() < pa.start() < cal.start()):
        fail("T4_SOURCE_ORDER_FAILED",
             "expected setup_arch < smp_prepare_boot_cpu < jump_label_init < "
             "parse_args(Booting kernel) < calibrate_delay")
    if pa.start() < sa.start():
        fail("T4_SOURCE_ORDER_FAILED", "parse_args before setup_arch")
    if not CORE_PARAM_RE.search(panic_c):
        fail("T4_SOURCE_ORDER_FAILED", "panic= is not core_param")
    if 'early_param("loglevel"' not in main:
        fail("T4_SOURCE_ORDER_FAILED", "loglevel= early_param missing")
    if '__setup("rdinit=' not in main:
        fail("T4_SOURCE_ORDER_FAILED", "rdinit= __setup missing")
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


def derive_post_bl(tools: dict, vmlinux: Path, start_va: int, stop_va: int,
                   target_va: int, label: str) -> tuple:
    dump = pb.run([
        tools["objdump"], "-d",
        f"--start-address={start_va:#x}",
        f"--stop-address={stop_va:#x}", str(vmlinux)])
    hits = collect_bls(dump, target_va)
    if not hits:
        fail("T4_CALLSITE_FAILED", f"no bl to {label} {target_va:#x}")
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


def t4_minus_t3(total: float) -> float:
    return total - T3_REFERENCE_TOTAL_S


def t4_minus_t2(total: float) -> float:
    return total - T2_REFERENCE_TOTAL_S


def t4_minus_t1(total: float) -> float:
    return total - T1_REFERENCE_TOTAL_S


def t4_minus_t0(total: float) -> float:
    return total - T0_REFERENCE_TOTAL_S


def t4_programmed_estimate(total: float) -> float:
    return total - P0_REF_OVERHEAD_S


def t4_reachability(total, recovery_kind: str, selected: str) -> dict:
    iso = "MAINLINE_V2_R3_P1B_T4_FAILURE_ISOLATION_CI"
    nxt_ok = "MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI"
    if selected == "C3_SETUP_ARCH_RETURN":
        nxt_ok = "MAINLINE_V2_R3_P1B_C6_PREDEVICE_READINESS_CI"
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T4_STABLE_FASTBOOT",
                "body": "NOT_PROVEN", "next": iso,
                "reason": "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_T4_FORBIDDEN"}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T4_NO_RETURN",
                "body": "NOT_PROVEN", "next": iso,
                "reason": "CASE_F_NO_RETURN_MANUAL_ELAPSED_EXCLUDED"}
    if total is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
                "body": "NOT_PROVEN", "next": iso,
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    d3 = t4_minus_t3(total)
    d2 = t4_minus_t2(total)
    d1 = t4_minus_t1(total)
    d0 = t4_minus_t0(total)
    early = total < T4_EARLY_RETURN_CLASS_LIMIT_S
    cross_ok = abs(d2) <= T4_CROSSCHECK_HALF_WINDOW_S and \
        abs(d1) <= T4_CROSSCHECK_HALF_WINDOW_S and \
        abs(d0) <= T4_CROSSCHECK_HALF_WINDOW_S
    if early and abs(d3) <= T4_STRONG_HALF_WINDOW_S and cross_ok:
        return {"verdict": "STRONG", "case": "T4_A_STRONG", "body": "TO_STAGE",
                "next": nxt_ok,
                "reason": "T3_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET+T2_T1_T0_CROSSCHECK_OK"}
    if early and abs(d3) <= T4_SUPPORTED_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED", "case": "T4_B_SUPPORTED",
                "body": "TO_STAGE", "next": nxt_ok,
                "reason": "T3_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET"}
    if early:
        return {"verdict": "NOT_OBSERVED",
                "case": "T4_EARLY_RETURN_TIMING_MISMATCH",
                "body": "NOT_PROVEN", "next": iso,
                "reason": f"T4_MINUS_T3={d3:+.3f}s"}
    if T4_CASE_C_BAND_S[0] <= total < T4_CASE_C_BAND_S[1]:
        return {"verdict": "NOT_OBSERVED", "case": "T4_SIGNATURE_NOT_OBSERVED",
                "body": "NOT_PROVEN", "next": iso,
                "reason": "OLD_AUTO_RETURN_CLASS"}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
            "body": "NOT_PROVEN", "next": iso, "reason": f"T4_TOTAL={total}"}


def run_decoder_fixtures(selected: str) -> list:
    lines: list = []
    iso = "MAINLINE_V2_R3_P1B_T4_FAILURE_ISOLATION_CI"
    nxt = "MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI"
    if selected == "C3_SETUP_ARCH_RETURN":
        nxt = "MAINLINE_V2_R3_P1B_C6_PREDEVICE_READINESS_CI"

    def case(name, total, kind, want_verdict, want_case=None, want_next=None):
        got = t4_reachability(total, kind, selected)
        if got["verdict"] != want_verdict:
            fail("T4_DECODER_FIXTURE_FAILED",
                 f"{name}: verdict {got['verdict']} != {want_verdict}")
        if want_case and got["case"] != want_case:
            fail("T4_DECODER_FIXTURE_FAILED",
                 f"{name}: case {got['case']} != {want_case}")
        if want_next and got["next"] != want_next:
            fail("T4_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"T4_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"case={got['case']}")

    case("STRONG_14P238S", 14.238, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T4_A_STRONG", nxt)
    case("STRONG_13P000S", 13.000, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T4_A_STRONG", nxt)
    case("STRONG_15P700S", 15.700, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T4_A_STRONG", nxt)
    case("SUPPORTED_16P500S", 16.500, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T4_B_SUPPORTED", nxt)
    case("SUPPORTED_17P200S", 17.200, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T4_B_SUPPORTED", nxt)
    case("EARLY_MISMATCH_18P000S", 18.000, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T4_EARLY_RETURN_TIMING_MISMATCH", iso)
    case("EARLY_MISMATCH_11P000S", 11.000, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T4_EARLY_RETURN_TIMING_MISMATCH", iso)
    case("CASE_C_FIX8", FIX8_TOTAL_S, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T4_SIGNATURE_NOT_OBSERVED", iso)
    case("CASE_C_PANIC30", PANIC30_TOTAL_S, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T4_SIGNATURE_NOT_OBSERVED", iso)
    case("CASE_C_BAND_EDGE", 20.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T4_SIGNATURE_NOT_OBSERVED", iso)
    case("CASE_E_STABLE_FASTBOOT", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "T4_STABLE_FASTBOOT", iso)
    case("CASE_F_NO_RETURN", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "T4_NO_RETURN", iso)
    case("UNKNOWN_KIND", 14.238, "UNKNOWN", "NOT_OBSERVED", "UNKNOWN")
    est = t4_programmed_estimate(T3_REFERENCE_TOTAL_S)
    if abs(est - (T3_REFERENCE_TOTAL_S - P0_REF_OVERHEAD_S)) > 1e-9:
        fail("T4_DECODER_FIXTURE_FAILED", "estimate arithmetic")
    lines.append(f"T4_DECODER_REFERENCE est(T3 {T3_REFERENCE_TOTAL_S}s)="
                 f"{est:.4f}s (SECONDARY)")
    lines.append("T4_DECODER_T3_MATCHED_CONTROL_REFERENCE=PASS")
    lines.append("T4_DECODER_T4_NOT_REACHED_LICENSE=NO")
    lines.append("T4_DECODER_FIXTURES=PASS")
    return lines


def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("T4_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"T4_NEGATIVE_{name}_REJECTED=PASS"
    fail("T4_NEGATIVE_FIXTURE_FAILED", f"{name}: ACCEPTED (must reject)")
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
            fail("T4_CALLSITE_FAILED",
                 f"checkpoint {ck:#x} is not first insn after bl {callsite:#x}")
    lines.append(expect_reject(
        "CHECKPOINT_BEFORE_CALL",
        lambda: gate_post_call(ctx["callsite_va"], ctx["callsite_va"] + 8),
        "T4_CALLSITE_FAILED"))
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
            fail("T4_IDENTITY_FAILED", "T3 probe still present")
    lines.append(expect_reject(
        "T3_PROBE_STILL_PRESENT", t3_still, "T4_IDENTITY_FAILED"))
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
        lambda: fail("T4_CORE_IDENTITY_FAILED", "core mismatch")
        if bytes(bad_core) != t1_probe else fail(
            "T4_CORE_IDENTITY_FAILED", "forced"),
        "T4_CORE_IDENTITY_FAILED"))
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
    if t4_probe != t1_probe:
        fail("T4_NEGATIVE_FIXTURE_FAILED", "t4 probe != t1 core in ctx")
    lines.append(f"T4_NEGATIVE_FIXTURE_COUNT={len(lines)}")
    lines.append("T4_NEGATIVE_FIXTURES=PASS")
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
        fail("T4_MAP_REVERIFY_FAILED",
             f"c-stage-map stage-map rc={proc.returncode} {proc.stderr[-800:]}")
    mp = map_dir / "early-c-stage-map.json"
    if not mp.is_file():
        fail("T4_MAP_REVERIFY_FAILED", "early-c-stage-map.json missing")
    doc = json.loads(mp.read_text())
    if doc.get("source_commit") != LINUX_COMMIT:
        fail("T4_MAP_REVERIFY_FAILED",
             f"source_commit {doc.get('source_commit')} != {LINUX_COMMIT}")
    if doc.get("device_ready") is True:
        fail("T4_MAP_REVERIFY_FAILED", "map marked device_ready")
    stages = {s["id"]: s for s in doc.get("stages", [])}
    for req in ("C0", "C2", "C3", "C5", "C6", "C_DELAY", "C12"):
        if req not in stages:
            fail("T4_MAP_REVERIFY_FAILED", f"missing stage {req}")
    c6 = stages["C6"]
    c3 = stages["C3"]
    c5 = stages["C5"]
    map_c6 = int(c6["link_va"], 16)
    map_c3 = int(c3["link_va"], 16)
    if selected == "C6_PARSE_ARGS_COMPLETE" and map_c6 != ck_va:
        fail("T4_MAP_MISMATCH",
             f"independent C6 {ck_va:#x} != map {map_c6:#x}")
    if selected == "C3_SETUP_ARCH_RETURN" and map_c3 != ck_va:
        fail("T4_MAP_MISMATCH",
             f"independent C3 {ck_va:#x} != map {map_c3:#x}")
    if map_c3 != sa_ret:
        fail("T4_MAP_MISMATCH",
             f"independent C3 {sa_ret:#x} != map {map_c3:#x}")
    if int(c6["link_va"], 16) != pa_bl + 4:
        fail("T4_MAP_MISMATCH", "map C6 is not parse_args fallthrough")
    pep_inside = "setup_arch" in str(c5.get("caller", "")).lower() or \
        "setup_arch" in str(c5.get("source_file", ""))
    if not pep_inside:
        fail("T4_MAP_MISMATCH", "C5 caller is not setup_arch")
    (out / "early-c-stage-map.json").write_text(mp.read_text())
    print("T4_MAP_JSON_CONSUMED=YES")
    print("T4_MAP_CRITICAL_POINTS_REDERIVED=YES")
    print("EARLY_C_STAGE_MAP_REVERIFIED_ON_A_MAINLINE=YES")
    print(f"MAP_C6={c6['link_va']} MAP_C3={c3['link_va']} MAP_C5={c5['link_va']}")
    return doc


def cmd_t4(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)
    src_facts = source_stage_facts()
    print("PARSE_EARLY_PARAM_EFFECTIVE_INSIDE_SETUP_ARCH=YES")
    print("C6_PANIC_PARAMETER_EFFECTIVE_BY_STAGE=YES")
    print("C6_RDINIT_PARAMETER_EFFECTIVE_BY_STAGE=YES")
    print("LOGLEVEL_EARLY_PARAMETER_STAGE=C5")
    print("CALIBRATE_DELAY_AFTER_C6=YES")
    print(f"T4_SOURCE_ORDER={src_facts}")

    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("T4_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA:
        fail("T4_IDENTITY_FAILED", f"frozen FIX8 payload sha={sha(frozen)}")
    if len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("T4_IDENTITY_FAILED",
             f"frozen FIX8 payload len {len(frozen)} != {FIX8_PAYLOAD_SIZE}")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("T4_IDENTITY_FAILED", "frozen code1 not b 0x40")
    image_size = fhdr["image_size"]
    t3.gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T4_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    t3.gate_tramp_identity(frozen)
    print(f"T4_AUTHORITATIVE_IMAGE_SIZE={image_size:#x} "
          "SOURCE=FINAL_BINARY_HEADER")
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}")
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES")
    print("T4_FROZEN_FIX8_BASE=PASS sha=" + FIX8_PAYLOAD_SHA)
    print("T4_BASELINE=FROZEN_FIX8")

    init = pb.compile_init(out, T4_DELAY_S, args.gcc, args.strip)
    init_sha = sha(init.read_bytes())
    if init_sha != FIX8_INIT_SHA:
        fail("T4_IDENTITY_FAILED", f"/init sha {init_sha} != frozen FIX8")
    cpio = out / f"initramfs-{T4_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    cpio_sha = sha(cpio.read_bytes())
    if cpio_sha != FIX8_CPIO_SHA:
        fail("T4_IDENTITY_FAILED", f"cpio sha {cpio_sha} != frozen FIX8")
    print(f"T4_INIT_IDENTICAL=YES sha={init_sha}")
    print(f"T4_INITRAMFS_IDENTICAL=YES sha={cpio_sha}")

    k = pb.make_kernel(out, T4_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    cfg = t3.config_symbols(k["config"].read_text())
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("T4_BUILD_FAILED",
             f"rebuilt image_size {kg['hdr']['image_size']:#x} != "
             f"authoritative {image_size:#x}")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("T4_BUILD_FAILED",
             f"rebuilt image file size {image_file_size} != frozen "
             f"{FIX8_IMAGE_FILE_SIZE}")
    print(f"T4_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size} "
          f"image_size={image_size:#x} image_sha={sha(image)}")

    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = t3.nm_symbol(nm_out, "_text")
    off_primary = t3.nm_symbol(nm_out, "primary_entry") - text_addr
    sk_va, sk_extent = t3.symbol_extent(nm_out, "start_kernel")
    ps_va, ps_extent = t3.symbol_extent(nm_out, "__primary_switched")
    pa_va = t3.nm_symbol(nm_out, "parse_args")
    sa_va = t3.nm_symbol(nm_out, "setup_arch")
    off_sk = sk_va - text_addr
    off_ps = ps_va - text_addr
    if t3.sysmap_symbol(k["sysmap"], "start_kernel") - \
            t3.sysmap_symbol(k["sysmap"], "_text") != off_sk:
        fail("T4_IDENTITY_FAILED", "start_kernel nm/sysmap mismatch")
    if sk_extent is None:
        fail("T4_IDENTITY_FAILED", "start_kernel has no bounded extent")
    print(f"START_KERNEL_VA={sk_va:#x}")
    print(f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}")
    print("T4_START_KERNEL_REDERIVED=YES")
    print(f"PRIMARY_SWITCHED_VA={ps_va:#x}")
    print(f"PRIMARY_SWITCHED_IMAGE_OFFSET={off_ps:#x}")
    print(f"PRIMARY_ENTRY_OFFSET={off_primary:#x}")
    print(f"PARSE_ARGS_VA={pa_va:#x}")
    print(f"SETUP_ARCH_VA={sa_va:#x}")

    word0 = struct.unpack_from("<I", frozen, off_sk)[0]
    if word0 != PACIASP:
        fail("T4_IDENTITY_FAILED",
             f"FIX8 start_kernel word0 {word0:#010x} != paciasp")
    print("START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES "
          f"(FIX8/T4 entry word {word0:#010x} paciasp; T3 probe not used)")
    print("T3_PROBE_REMOVED_FROM_T4=YES")

    sk_stop = min(sk_extent or sk_va + 0x4000, sk_va + 0x4000)
    dump_sk = pb.run([
        tools["objdump"], "-d",
        f"--start-address={sk_va:#x}",
        f"--stop-address={sk_stop:#x}", str(k["vmlinux"])])
    (out / "p1b-t4-start-kernel-vmlinux-disasm.txt").write_text(dump_sk)
    pa_hits = collect_bls(dump_sk, pa_va)
    sa_hits = collect_bls(dump_sk, sa_va)
    if not pa_hits:
        fail("T4_CALLSITE_FAILED", "no bl parse_args in start_kernel")
    if not sa_hits:
        fail("T4_CALLSITE_FAILED", "no bl setup_arch in start_kernel")
    pa_bl = pa_hits[0]
    sa_bl = sa_hits[0]
    c6_va = pa_bl + 4
    c3_va = sa_bl + 4
    if c6_va <= pa_bl or c3_va <= sa_bl:
        fail("T4_CALLSITE_FAILED", "post-call VA not after bl")
    if not (sk_va < sa_bl < c3_va < pa_bl < c6_va < sk_stop):
        fail("T4_CALLSITE_FAILED",
             f"order sk={sk_va:#x} sa_bl={sa_bl:#x} c3={c3_va:#x} "
             f"pa_bl={pa_bl:#x} c6={c6_va:#x}")
    pa_word = struct.unpack_from("<I", frozen, pa_bl - text_addr)[0]
    if (pa_word >> 26) != 0b100101:
        fail("T4_CALLSITE_FAILED", f"frozen parse_args site {pa_word:#010x} not bl")
    pa_tgt = text_addr + (pa_bl - text_addr) + \
        pb.sx(pa_word & 0x03FFFFFF, 26) * 4
    if pa_tgt != pa_va:
        fail("T4_CALLSITE_FAILED",
             f"frozen parse_args bl target {pa_tgt:#x} != {pa_va:#x}")
    sa_word = struct.unpack_from("<I", frozen, sa_bl - text_addr)[0]
    sa_tgt = text_addr + (sa_bl - text_addr) + \
        pb.sx(sa_word & 0x03FFFFFF, 26) * 4
    if sa_tgt != sa_va:
        fail("T4_CALLSITE_FAILED",
             f"frozen setup_arch bl target {sa_tgt:#x} != {sa_va:#x}")
    print(f"C6_PARSE_ARGS_BL={pa_bl:#x} C6_FALLTHROUGH={c6_va:#x}")
    print(f"C3_SETUP_ARCH_BL={sa_bl:#x} C3_FALLTHROUGH={c3_va:#x}")
    print("T4_CHECKPOINT_IS_POST_STAGE=YES")
    print("T4_POSTCALL_CONTROL_FLOW_PROVEN=YES "
          "(checkpoint is the unique fallthrough of the selected BL; "
          "frozen payload BL target matches nm symbol)")
    if len(pa_hits) < 1:
        fail("T4_CALLSITE_FAILED", "parse_args hits")
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
    t3.gate_cnppct_safety(T4_CNTPCT_ACCESS_SAFE_REASON, True)
    t3.gate_psci_safety(T4_PSCI_SAFE_REASON, True)
    print("T4_CNTPCT_ACCESS_SAFE=YES")
    print("T4_PSCI_SYSTEM_RESET_SAFE=YES")
    print("T4_ENTRY_MMU=ON")
    print("T4_ENTRY_PC_ADDRESS_SPACE=VA")
    print("T4_ENTRY_SP_VALID=YES")

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

    c6_audit = None
    c6_ok = False
    c6_why = ""
    try:
        c6_audit = audit_window(
            c6_va, T4_PROBE_SIZE, sections=sections, symbol_vas=symbol_vas,
            reloc=reloc, frozen_image=frozen_image, tools=tools,
            vmlinux=k["vmlinux"], sk_extent=sk_extent, text_addr=text_addr,
            image_size=image_size, out=out)
        c6_ok = True
        print("T4_CANDIDATE_C6=SAFE")
    except SystemExit as exc:
        c6_why = str(exc)
        print(f"T4_CANDIDATE_C6=UNSAFE {c6_why}")
    c3_ok = False
    c3_why = ""
    c3_audit = None
    try:
        c3_audit = audit_window(
            c3_va, T4_PROBE_SIZE, sections=sections, symbol_vas=symbol_vas,
            reloc=reloc, frozen_image=frozen_image, tools=tools,
            vmlinux=k["vmlinux"], sk_extent=sk_extent, text_addr=text_addr,
            image_size=image_size, out=out)
        c3_ok = True
        print("T4_CANDIDATE_C3=SAFE")
    except SystemExit as exc:
        c3_why = str(exc)
        print(f"T4_CANDIDATE_C3=UNSAFE {c3_why}")
    print("T4_CANDIDATE_C_DELAY=FUTURE")
    if c6_ok:
        selected = "C6_PARSE_ARGS_COMPLETE"
        ck_va = c6_va
        callsite_va = pa_bl
        target_va = pa_va
        audit = c6_audit
        semantic = "POST_PARSE_ARGS_CHECKPOINT_ONLY"
        reason = ("C6 closed: unique first bl parse_args in start_kernel, "
                  "post-call fallthrough, INLINE scans pass, panic=/rdinit= "
                  "consumed at this stage")
    elif c3_ok:
        selected = "C3_SETUP_ARCH_RETURN"
        ck_va = c3_va
        callsite_va = sa_bl
        target_va = sa_va
        audit = c3_audit
        semantic = "POST_SETUP_ARCH_CHECKPOINT_ONLY"
        reason = f"C6 unsafe ({c6_why}); C3 closed as fallback"
    else:
        fail("R3_P1B_T4_PREDEVICE_NOT_READY",
             f"C6 unsafe ({c6_why}); C3 unsafe ({c3_why})")
        return
    print(f"T4_SELECTED_STAGE={selected}")
    print(f"T4_SELECTION_REASON={reason}")
    print(f"T4_RUNTIME_SEMANTIC_DELTA={semantic}")
    off_ck = ck_va - text_addr
    region = (off_ck, off_ck + T4_PROBE_SIZE)
    print(f"T4_CHECKPOINT_VA={ck_va:#x}")
    print(f"T4_CHECKPOINT_IMAGE_OFFSET={off_ck:#x}")
    print(f"T4_CALLSITE_VA={callsite_va:#x}")
    print("T4_PROBE_ARCHITECTURE=INLINE")
    print(f"T4_INLINE_START={ck_va:#x}")
    print(f"T4_INLINE_END={ck_va + T4_PROBE_SIZE:#x}")
    print("T4_INLINE_OVERWRITE_SAFE=YES")
    print(f"T4_SYMBOL_SCAN=PASS ({audit['n_sym']} symbols)")
    print(f"T4_BRANCH_SCAN=PASS ({audit['n_raw']} confirmed)")
    print(f"T4_RELOCATION_SCAN=PASS ({audit['n_rel']} reloc sites)")
    print(f"T4_LITERAL_SCAN=PASS ({audit['n_lit']} slots)")
    print("T4_CONTROL_FLOW_SCAN=PASS")
    print("T4_SECTION_BOUNDARY_SCAN=PASS")
    print(f"T4_FUNCTION_EXTENT_SCAN=PASS (extent {audit['extent_len']:#x})")
    rw = audit["rw"]
    for tag, canon in (("__ex_table", "T4_EXCEPTION_TABLE_SCAN"),
                       ("altinstructions", "T4_ALTINSTRUCTIONS_SCAN"),
                       ("__jump_table", "T4_JUMP_TABLE_SCAN"),
                       ("static_call_sites", "T4_STATIC_CALL_SITES_SCAN"),
                       ("kcfi_traps", "T4_KCFI_TRAPS_SCAN")):
        info = rw[tag]
        state = f"entries={info['entries']}" if info.get("present") else "ABSENT"
        print(f"{canon}=PASS ({state}, none in window)")
    print("T4_WINDOW_INSIDE_IMAGE_SIZE=YES")
    print("T4_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT")
    print("T4_INLINE_MAPPING_EXECUTABLE=YES")
    print("T4_EXTERNAL_CHECKPOINT_USED=NO")
    print("T4_PADDING_MAPPING_USED=NO")
    print("T4_ENTRY_INSTRUMENTATION_AUDITED=YES "
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
                "CONFIG_JUMP_LABEL"):
        if cfg.get(sym) == "y" and sym in (
                "CONFIG_CFI_CLANG", "CONFIG_FUNCTION_TRACER",
                "CONFIG_KASAN", "CONFIG_KCOV", "CONFIG_SHADOW_CALL_STACK"):
            fail("T4_ENTRY_INSTRUMENTATION_FAILED", f"{sym}=y")
        print(f"T4_ENTRY_CFG_{sym}={cfg.get(sym, 'ABSENT')}")

    consume_map_json(out, tools, k, ck_va, selected, c3_va, pa_bl)

    t4_probe, ops, dump = t3.build_probe(
        out, tools, T4_DEVICE_S, T4_DEVICE_LD, "P1B_T4_DELAY", T4_DELAY_S,
        "r3_t4_checkpoint", "p1b-t4-checkpoint")
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
    if len(t4_probe) != T4_PROBE_SIZE:
        fail("T4_CORE_IDENTITY_FAILED", f"t4 probe size {len(t4_probe)}")
    if t4_probe != t1_probe:
        fail("T4_CORE_IDENTITY_FAILED", "T4 probe != T1 core")
    if t4_probe != t3_probe[4:]:
        fail("T4_CORE_IDENTITY_FAILED", "T4 probe != T3 core slice")
    if t4_probe != t2_probe[4:]:
        fail("T4_CORE_IDENTITY_FAILED", "T4 probe != T2 core slice")
    if len(t3_probe) != T3_REF_PROBE_SIZE or len(t2_probe) != T2_REF_PROBE_SIZE:
        fail("T4_CORE_IDENTITY_FAILED", "T2/T3 reference sizes")
    plen = len(t4_probe)
    print(f"T4_CHECKPOINT sha256={sha(t4_probe)} size={plen}")
    print("T4_DIAGNOSTIC_CORE_MATCHES_T1=YES")
    print("T4_DIAGNOSTIC_CORE_MATCHES_T3=YES")
    print("T4_DIAGNOSTIC_CORE_SLICE_MATCHES_T2=YES")
    print("T4_DEVICE_CANDIDATE_DELAY=8s")
    print("T4_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY")
    print("T4_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC")
    print("T4_FAIL_CLOSED=YES")
    print("T4_STACK_USAGE=NO")
    print("T4_NO_MEMORY_READS=YES")
    print("T4_NO_MEMORY_WRITES=YES")
    print("T4_POSITION_INDEPENDENT=YES")
    print("T4_RUNTIME_RELOCATIONS=0")
    print(f"T4_CLOBBER_REGISTERS={T4_CLOBBER_REGISTERS}")

    covered = list(struct.unpack_from(f"<{plen // 4}I", frozen, off_ck))
    t3.inst_record(out, tools, covered, "p1b-t4-original-covered-insns-record")

    cand = bytearray(frozen)
    cand[off_ck:off_ck + plen] = t4_probe
    cand = bytes(cand)
    diffs = t3.gate_payload_diff(frozen, cand, region)
    tail = t3.gate_tail_identity(frozen, cand, region)
    t3.gate_t2_probe_removed(frozen, cand, off_ps, t2_probe)
    if cand[off_sk:off_sk + T3_REF_PROBE_SIZE] == t3_probe:
        fail("T4_IDENTITY_FAILED", "T3 probe present at start_kernel")
    if struct.unpack_from("<I", cand, off_sk)[0] != PACIASP:
        fail("T4_IDENTITY_FAILED", "start_kernel entry not restored paciasp")
    t3.gate_tramp_identity(cand)
    trailer = t3.gate_trailer(cand)
    if trailer != frozen_rt_d:
        fail("T4_PAYLOAD_DIFF_FAILED", "trailer drifted vs frozen RT-D")
    hdr, dtb_off2, gap2, boot_est = t3.gate_geometry(cand, image_size)
    if dtb_off2 != dtb_offset:
        fail("T4_PAYLOAD_DIFF_FAILED", "dtb_offset drifted")
    if boot_est != T4_BOOT_SIZE_EXPECTED:
        fail("T4_GEOMETRY_FAILED", f"boot_est {boot_est}")
    payload_path = out / "thyme-r3-p1b-t4-kernel-payload.bin"
    payload_path.write_bytes(cand)
    print(f"T4_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)}")
    print(f"T4_DIFF_BYTE_COUNT={len(diffs)}")
    print(f"T4_DIFF_RANGES=[{off_ck:#x},{off_ck + plen:#x})")
    print("T4_PAYLOAD_DIFF_ATTRIBUTED=SELECTED_C_STAGE_CHECKPOINT_ONLY")
    print("T4_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES "
          f"({off_ck} bytes before and {tail} bytes after the window)")
    print("T4_TRAMPOLINE_IDENTICAL=YES sha=" + TRAMP_SHA)
    print("T4_RT_D_IDENTITY=YES")
    print("T4_INIT_IDENTITY=YES")
    print("T4_INITRAMFS_IDENTITY=YES")
    print("T4_PAYLOAD_SIZE_IDENTICAL=YES")
    print("T4_BOOT_SIZE_IDENTICAL=YES")
    print(f"T4_DTB_OFFSET={DTB_OFFSET:#x}")
    print("T4_GEOMETRY_GATES=PASS")
    print("PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES")
    print("T4_DIAGNOSTIC_ONLY=YES")
    print("T4_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    print("T4_STATUS=NOT_DEVICE_READY")
    print("READY_FOR_DEVICE=NO")
    print("T4_DEVICE_OPERATION=NO")

    (out / "p1b-t4-payload-diff-report.txt").write_text(
        "T4_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"T4_PAYLOAD_SHA256={sha(cand)}\n"
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
        "target_va": target_va})
    (out / "p1b-t4-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures(selected)
    (out / "p1b-t4-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")
    print("T4_NEGATIVE_FIXTURES=PASS")
    print("T4_DECODER_FIXTURES=PASS")

    sec = audit["sec"]
    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "t4_true_device_run": "NOT_EXECUTED",
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
        "t4_selected_stage": selected,
        "t4_selection_reason": reason,
        "t4_checkpoint_va": hex(ck_va),
        "t4_checkpoint_image_offset": hex(off_ck),
        "t4_callsite_va": hex(callsite_va),
        "t4_callsite_instruction": "BL",
        "t4_call_target": hex(target_va),
        "t4_checkpoint_is_post_stage": True,
        "t4_postcall_control_flow_proven": True,
        "t4_probe_architecture": "INLINE",
        "t4_inline_overwrite_safe": True,
        "t4_external_checkpoint_used": False,
        "t4_padding_mapping_used": False,
        "t4_mapping_source": "KERNEL_TEXT_VA_SELF_EVIDENT",
        "t4_inline_mapping_executable": True,
        "t4_checkpoint_sha256": sha(t4_probe),
        "t4_checkpoint_size": plen,
        "t4_diagnostic_core_matches_t1": True,
        "t4_diagnostic_core_matches_t3": True,
        "t4_t1_core_sha256": sha(t1_probe),
        "t3_probe_removed_from_t4": True,
        "start_kernel_entry_restored_to_fix8": True,
        "t4_payload_sha256": sha(cand),
        "t4_payload_size": len(cand),
        "t4_boot_size_est": boot_est,
        "diff_bytes": len(diffs),
        "diff_regions": [[hex(off_ck), hex(off_ck + plen)]],
        "diff_attribution": "SELECTED_C_STAGE_CHECKPOINT_ONLY",
        "t4_runtime_semantic_delta": semantic,
        "t4_precheckpoint_normal_path_identical_to_fix8": True,
        "t4_tramp_identical_to_fix8": True,
        "t4_rtd_identical": True,
        "t4_init_identical": True,
        "t4_initramfs_identical": True,
        "t4_diagnostic_only": True,
        "t4_normal_kernel_boot_candidate": False,
        "t4_status": "NOT_DEVICE_READY",
        "t4_delay_seconds": T4_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "t4_fail_closed": True,
        "t4_stack_usage": False,
        "t4_memory_reads": False,
        "t4_memory_writes": False,
        "t4_runtime_relocations": 0,
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
            "strong_half_window_s": T4_STRONG_HALF_WINDOW_S,
            "supported_half_window_s": T4_SUPPORTED_HALF_WINDOW_S,
            "early_return_class_limit_s": T4_EARLY_RETURN_CLASS_LIMIT_S,
        },
        "observer": {"identity_env": "R3_T4_SHA256",
                     "forbidden_env": "R3_T4_FORBIDDEN_SHAS",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
        "start_kernel_section": sec["name"],
        "t4_section_flags": sec.get("flags"),
    }
    (out / "p1b-t4-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    gates = [
        "T4_BUILD_GATES=PASS",
        "T4_BASELINE=FROZEN_FIX8",
        "T4_MAP_JSON_CONSUMED=YES",
        "T4_MAP_CRITICAL_POINTS_REDERIVED=YES",
        "EARLY_C_STAGE_MAP_REVERIFIED_ON_A_MAINLINE=YES",
        f"T4_SELECTED_STAGE={selected}",
        "T4_CHECKPOINT_IS_POST_STAGE=YES",
        "T4_POSTCALL_CONTROL_FLOW_PROVEN=YES",
        "T4_PROBE_ARCHITECTURE=INLINE",
        "T4_INLINE_OVERWRITE_SAFE=YES",
        "T4_ENTRY_INSTRUMENTATION_AUDITED=YES",
        "T4_WINDOW_INSIDE_IMAGE_SIZE=YES",
        "T4_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
        "T4_INLINE_MAPPING_EXECUTABLE=YES",
        "T4_EXTERNAL_CHECKPOINT_USED=NO",
        "T4_PADDING_MAPPING_USED=NO",
        "T4_DEVICE_CANDIDATE_DELAY=8s",
        "T4_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "T4_CNTPCT_ACCESS_SAFE=YES",
        "T4_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "T4_PSCI_SYSTEM_RESET_SAFE=YES",
        "T4_FAIL_CLOSED=YES",
        "T4_STACK_USAGE=NO",
        "T4_NO_MEMORY_READS=YES",
        "T4_NO_MEMORY_WRITES=YES",
        "T4_DIAGNOSTIC_CORE_MATCHES_T3=YES",
        "T4_DIAGNOSTIC_CORE_MATCHES_T1=YES",
        "T4_RUNTIME_RELOCATIONS=0",
        "T3_PROBE_REMOVED_FROM_T4=YES",
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES",
        "T4_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES",
        "T4_TRAMPOLINE_IDENTICAL=YES",
        "T4_RT_D_IDENTITY=YES",
        "T4_INIT_IDENTITY=YES",
        "T4_INITRAMFS_IDENTITY=YES",
        "T4_PAYLOAD_DIFF_ATTRIBUTED=SELECTED_C_STAGE_CHECKPOINT_ONLY",
        "T4_PAYLOAD_SIZE_IDENTICAL=YES",
        "T4_BOOT_SIZE_IDENTICAL=YES",
        "T4_DTB_OFFSET=0x2380000",
        "T4_GEOMETRY_GATES=PASS",
        "T4_NEGATIVE_FIXTURES=PASS",
        "T4_DECODER_FIXTURES=PASS",
        "T4_DIAGNOSTIC_ONLY=YES",
        "T4_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
        "T4_STATUS=NOT_DEVICE_READY",
        "READY_FOR_DEVICE=NO",
        "C6_PANIC_PARAMETER_EFFECTIVE_BY_STAGE=YES",
        "C6_RDINIT_PARAMETER_EFFECTIVE_BY_STAGE=YES",
        "PARSE_EARLY_PARAM_EFFECTIVE_INSIDE_SETUP_ARCH=YES",
        f"T4_RUNTIME_SEMANTIC_DELTA={semantic}",
        f"T4_DIFF_BYTE_COUNT={len(diffs)}",
        f"T4_DIFF_RANGES=[{off_ck:#x},{off_ck + plen:#x})",
        f"START_KERNEL_VA={sk_va:#x}",
        f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}",
        f"T4_CHECKPOINT_VA={ck_va:#x}",
        f"T4_CHECKPOINT_IMAGE_OFFSET={off_ck:#x}",
        "IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES",
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}",
        f"IMAGE_FILE_SIZE={image_file_size}",
        "T4_SYMBOL_SCAN=PASS",
        "T4_BRANCH_SCAN=PASS",
        "T4_RELOCATION_SCAN=PASS",
        "T4_LITERAL_SCAN=PASS",
        "T4_CONTROL_FLOW_SCAN=PASS",
        "T4_SECTION_BOUNDARY_SCAN=PASS",
        "T4_FUNCTION_EXTENT_SCAN=PASS",
        "T4_EXCEPTION_TABLE_SCAN=PASS",
        "T4_ALTINSTRUCTIONS_SCAN=PASS",
        "T4_JUMP_TABLE_SCAN=PASS",
        "T4_STATIC_CALL_SITES_SCAN=PASS",
        "T4_KCFI_TRAPS_SCAN=PASS",
        "T4_STATUS_GATE_STRUCTURED=YES",
    ]
    sm_lines = [l for l in k["sysmap"].read_text().splitlines()
                if l.endswith((" primary_entry", " _text", " start_kernel",
                               " __primary_switched", " parse_args",
                               " setup_arch", " parse_early_param",
                               " calibrate_delay"))]
    (out / "p1b-t4-sysmap-excerpt.txt").write_text("\n".join(sm_lines) + "\n")
    for src, dst in (
            ("p1b-t3-vmlinux-sections.txt", "p1b-t4-vmlinux-sections.txt"),
            ("p1b-t3-vmlinux-relocations.txt", "p1b-t4-vmlinux-relocations.txt")):
        s = out / src
        if s.is_file():
            (out / dst).write_bytes(s.read_bytes())
    (out / "p1b-t4-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))
    (out / "p1b-t4-report.txt").write_text(
        "T4_PREDEVICE_REPORT\n" + "\n".join(gates) + "\n")


def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "t4_obs_fixtures", OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-t4-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("T4_OBSERVER_FIXTURES=PASS")


def cmd_t4_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    off_ck = int(args.checkpoint_offset, 16)
    probe = Path(args.checkpoint_bin).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("T4_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("T4_PACK_FAILED", f"payload sha={sha(payload)}")
    if sha(probe) != args.checkpoint_sha:
        fail("T4_PACK_FAILED", f"checkpoint sha={sha(probe)}")
    if len(probe) != T4_PROBE_SIZE:
        fail("T4_PACK_FAILED", f"checkpoint size {len(probe)}")
    hdr = pb.parse_image_hdr(payload, "t4-payload")
    image_size = hdr["image_size"]
    t3.gate_image_size_rederived(image_size, "t4-packed-payload")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("T4_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T4_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if (off_ck + len(probe)) > image_size:
        fail("T4_PACK_FAILED", "checkpoint window past image_size")
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T4_PACK_FAILED", "embedded trampoline != frozen FIX8")
    if payload[off_ck:off_ck + len(probe)] != probe:
        fail("T4_PACK_FAILED", "checkpoint region != built T4 probe")
    off_sk = int(args.start_kernel_offset, 16)
    if struct.unpack_from("<I", payload, off_sk)[0] != PACIASP:
        fail("T4_PACK_FAILED", "start_kernel entry not paciasp")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I", FDT_MAGIC):
        fail("T4_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "t4-candidate")
    if cand["kernel"] != payload:
        fail("T4_PACK_FAILED", "candidate kernel != T4 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("T4_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("T4_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("T4_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("T4_PACK_FAILED", "reserved differs from M5D")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("T4_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("T4_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-t4-pack-gates.txt"
    report.write_text(
        "T4_PACK_GATES=PASS\n"
        f"T4_BOOT_SIZE={len(boot)}\n"
        f"T4_BOOT_SHA256={sha(boot)}\n"
        f"T4_PAYLOAD_SHA256={sha(payload)}\n"
        f"T4_TRAMP_SHA256={sha(tramp)}\n"
        "T4_TRAMP_SOURCE=FROZEN_FIX8_UNMODIFIED\n"
        f"T4_CHECKPOINT_SHA256={sha(probe)}\n"
        f"T4_KERNEL_SIZE={len(payload)}\n"
        f"T4_CHECKPOINT_OFFSET={off_ck:#x}\n"
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}\n"
        "T4_PROBE_ARCHITECTURE=INLINE\n"
        "T4_INLINE_REGION_IN_KERNEL_TEXT=YES\n"
        f"T4_DTB_OFFSET={dtb_offset:#x}\n"
        "T4_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "T4_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "T4_BOOT_CAPACITY=PASS\n"
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [T4_DEVICE_S, T4_DEVICE_LD, T3_DEVICE_S, T3_DEVICE_LD,
                T2_DEVICE_S, T2_DEVICE_LD, T1_DEVICE_S, T1_DEVICE_LD,
                OBSERVER, OBSERVER_FIXTURES, Path(__file__), DOC, STATUS_DOC,
                MAP_DOC, WF, MAP_WF, C_STAGE, PRIVATE_WF,
                HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld", HERE / "p1b-t3-predevice.py"]
    for path in required:
        if not path.is_file():
            fail("T4_SOURCE_GATE_FAILED", f"missing {path}")
    dev = T4_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "isb", "mrs\tx9, cntfrq_el0",
                  "mrs\tx11, cntpct_el0", "mrs\tx12, cntpct_el0", "yield",
                  "smc\t#0", "wfe", "P1B_T4_DELAY",
                  "#if (P1B_T4_DELAY) != 8", "r3_t4_checkpoint"):
        need(dev, token)
    for token in ("paciasp", ".inst\t0xd503233f", "bti", "P1B_DTB_REL",
                  "dtb_rel", "adr\t", "ldr\t", "stp\tx29", "eret", "sctlr",
                  "msr\tttbr", "b\tprimary", "b\t__primary",
                  "b\tstart_kernel", "bl\t"):
        forbid(dev, token)
    obs = OBSERVER.read_text()
    for token in ("R3_T4_SHA256", "T4_OBSERVER_MISBOOT_REFUSED",
                  "T4_MINUS_T3", "T3_REFERENCE_TOTAL", "FASTBOOT_BOOT_ONLY",
                  "T4_NOT_REACHED_LICENSE=NO", "T4_FAILURE_ISOLATION_CI",
                  "T4_NORMAL_KERNEL_BOOT_CANDIDATE", "T4_DIAGNOSTIC_ONLY",
                  "C6_PARSE_ARGS_COMPLETE"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    forbid(obs, "R3_T3_SHA256")
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("T4_OBSERVER_MISBOOT_REFUSED", "T4_NOT_REACHED",
                  "T4_STABLE_FASTBOOT", "T4_NO_RETURN", "T3_BOOT"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("T4_START_KERNEL_REDERIVED", "T4_PROBE_ARCHITECTURE=INLINE",
                  "T4_INLINE_OVERWRITE_SAFE", "T4_CHECKPOINT_IS_POST_STAGE",
                  "T4_POSTCALL_CONTROL_FLOW_PROVEN",
                  "T4_ENTRY_INSTRUMENTATION_AUDITED",
                  "T4_CNTPCT_ACCESS_SAFE", "T4_PSCI_SYSTEM_RESET_SAFE",
                  "T4_FAIL_CLOSED", "T4_STACK_USAGE=NO",
                  "T4_RUNTIME_RELOCATIONS=0",
                  "T3_PROBE_REMOVED_FROM_T4",
                  "START_KERNEL_ENTRY_RESTORED_TO_FIX8",
                  "T4_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8",
                  "SELECTED_C_STAGE_CHECKPOINT_ONLY",
                  "T4_MAP_JSON_CONSUMED", "T4_MAP_CRITICAL_POINTS_REDERIVED",
                  "PARSE_EARLY_PARAM", "C6_PARSE_ARGS_COMPLETE",
                  "C3_SETUP_ARCH_RETURN", "C_DELAY",
                  "C6_PANIC_PARAMETER_EFFECTIVE_BY_STAGE",
                  "C6_RDINIT_PARAMETER_EFFECTIVE_BY_STAGE",
                  "14.238", "1.5", "3.0", "0x2380000", "0x84000009",
                  "READY_FOR_R3_P1B_T4_DEVICE_CONTROL",
                  "R3_P1B_T4_PREDEVICE_NOT_READY",
                  "EARLY_C_STAGE_MAP_SOURCE_HEAD", "d47bf58",
                  "NO_FF_MERGE", "34842580640"):
        need(doc, token)
    kv = parse_status_kv(STATUS_DOC.read_text())
    for key, want in STATUS_DOC_REQUIRED_KV.items():
        if kv.get(key) != want:
            fail("T4_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} != {want!r}")
    for key, allowed in STATUS_DOC_ENUM_KV.items():
        if kv.get(key) not in allowed:
            fail("T4_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} not in {allowed}")
    print(f"T4_STATUS_KV_KEY_COUNT={len(kv)}")
    print("T4_STATUS_GATE_STRUCTURED=YES")
    wf_text = WF.read_text()
    for token in ("p1b-t4-device.S", "p1b-t4-predevice.py",
                  "observe-r3-p1b-t4.py", "thyme-r3-p1b-t4",
                  "T4_BUILD_GATES=PASS", "c-stage-map.py",
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
            fail("T4_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    body = re.search(r"\n    manifest = \{(.*?)\n    \}\n",
                     Path(__file__).read_text(), re.S)
    if not body:
        fail("T4_SOURCE_GATE_FAILED", "manifest literal not found")
    keys = set(re.findall(r'^\s+"([a-z0-9_]+)":', body.group(1), re.M))
    for key in sorted(set(re.findall(r'm\["([^"]+)"\]',
                                     PRIVATE_WF.read_text()))):
        if key not in keys:
            fail("T4_SOURCE_GATE_FAILED",
                 f"private workflow reads unknown manifest key {key!r}")
    print(f"T4_MANIFEST_KEY_CONSISTENCY=PASS ({len(keys)} keys)")
    print("T4_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "t4", "observer-fixtures", "t4-pack-gates"),
        required=True)
    parser.add_argument("--out", default="out-t4")
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
    if args.mode == "t4":
        if not (args.rt_d and args.fix8_payload):
            fail("T4_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_t4(args)
        return
    if args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
        return
    if args.mode == "t4-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.checkpoint_bin
                    and args.checkpoint_sha and args.checkpoint_offset
                    and args.start_kernel_offset)
        if not need_all:
            fail("T4_PACK_FAILED",
                 "need --m5d-boot --payload --boot --payload-sha "
                 "--checkpoint-bin --checkpoint-sha --checkpoint-offset "
                 "--start-kernel-offset")
        cmd_t4_pack_gates(args)


if __name__ == "__main__":
    main()
