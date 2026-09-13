#!/usr/bin/env python3
"""R3 P1B T0 predevice readiness (MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source/doc boundary checks (no build)
  t0                  frozen-FIX8-anchored T0-8 fail-closed device candidate:
                      FIX8 identity re-verification from the authoritative
                      run (no kernel rebuild), frozen trampoline disassembly
                      + branch algebra, T0 device trampoline build + gates,
                      payload patch + diff attribution, geometry, negative
                      fixtures, decoder fixtures
  observer-fixtures   T0 observer fixture suite (imports the observer module)
  t0-pack-gates       private: gates over a packed T0 boot v3 image

T0 baseline is the exact frozen FIXED INIT8 payload (public run 34741153230):
the ONLY change is the trampoline checkpoint region [0x40, 0x40+T0_LEN),
where the frozen handoff's final "branch primary_entry" is REPLACED by
reach -> 8s CNTPCT delay -> PSCI SYSTEM_RESET (smc #0) -> wfe forever.
The prior-round CI prototype (p1b-t0-trampoline.S) is NOT device-ready: it
has a failsafe fall-through (smc return -> restore x0/x1/x2/x3 ->
primary_entry); this round regenerates a fail-closed T0 instead.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOC = REPO / "docs" / "route-r3-p1b-t0-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-t0-predevice.yml"
T0_DEVICE_S = HERE / "p1b-t0-device.S"
T0_DEVICE_LD = HERE / "p1b-t0-device.ld"
T0_PROTO_S = HERE / "p1b-t0-trampoline.S"
OBSERVER = HERE / "observe-r3-p1b-t0.py"
OBSERVER_FIXTURES = HERE / "observer-t0-fixtures.py"

_spec = importlib.util.spec_from_file_location("p1b_build", HERE / "p1b-build.py")
pb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb)  # p1b-build.py enforces its own CI guard
_iso_spec = importlib.util.spec_from_file_location(
    "p30_iso", HERE / "p1b-panic-checkpoint-isolation.py")
iso = importlib.util.module_from_spec(_iso_spec)
_iso_spec.loader.exec_module(iso)

LINUX_BASE = pb.LINUX_BASE
RT_D_SHA = pb.RT_D_SHA
RT_D_SIZE = pb.RT_D_SIZE
S_RESIDUE = pb.S_RESIDUE
ALIGN_2M = pb.ALIGN_2M
TRAMP_OFFSET = pb.TRAMP_OFFSET
PAGE = pb.PAGE
BOOT_CAP = pb.BOOT_CAP
DTB_OFFSET = 0x2380000
FIX8_IMAGE_HEADER_IMAGE_SIZE = 0x2230000
CODE1_B_0X40 = 0x1400000F
FIX8_PAYLOAD_SHA = (
    "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41")
FIX8_PAYLOAD_SIZE = DTB_OFFSET + RT_D_SIZE  # 37369041
FIX8_BOOT_SIZE_EXPECTED = 37380096
TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
TRAMP_SIZE = 48
OFF_PRIMARY_FROZEN = 0x1B1C0A0
PSCI_SYSTEM_RESET_FID = 0x84000009
T0_DELAY_S = 8
T0_TRAMP_SIZE = 112  # 0x70: 28 instructions + align pad + dtb_rel quad
# Misboot refusal list for the T0 observer: boots that must NEVER be run
# through the T0 observer (full SHAs; prompt section 26).
FORBIDDEN_BOOT_SHAS = {
    "FIX8_BOOT":
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5",
    "PANIC30_BOOT":
        "ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1",
    "OLD_INIT8_BOOT":
        "e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264",
    "ENTRY_STATE_PROBE_BOOT":
        "cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c",
}
# Preregistered supporting decoder (prompt sections 27-29): NOT a strict
# invariant — T0 is the full 37 MiB-class P1B payload, so the windows are
# wider than the P0 probe's ±0.75s.
P0_REF_OVERHEAD_S = 6.1445
STRONG_HALF_WINDOW_S = 1.5
SUPPORTED_HALF_WINDOW_S = 3.0
EARLY_RETURN_CLASS_LIMIT_S = 20.0
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
T0_CLOBBER_REGISTERS = "x0/w0(PSCI FID),x9,x10,x11,x12,x13,NZCV"

ORDER_TOKENS = [
    ("msr daifset, #0xf", False),
    ("isb", False),
    ("adr x0", False),
    ("ldr x9", False),
    ("add x0, x0, x9", False),
    ("mov x1, xzr", False),
    ("mov x2, xzr", False),
    ("mov x3, xzr", False),
    ("mrs x9, cntfrq_el0", False),
    (r"(movz|mov) x10, #(0x8|8)\b", True),
    ("mul x10, x9, x10", False),
    ("mrs x11, cntpct_el0", False),
    ("mrs x12, cntpct_el0", False),
    ("yield", False),
    (r"(movz|mov) w0, #(0x9|9)\b", True),
    (r"movk w0, #(0x8400|33792), lsl #16\b", True),
    (r"smc #(0x)?0\b", True),
    ("wfe", False),
]
BRANCH_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(b|b\.\w+)\s+(?:0x)?([0-9a-f]+)", re.I)
INSTR_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(\S+)\s*(.*)$")
DST_RE = re.compile(r"(x[0-9]+|w[0-9]+|xzr|wzr|sp|wsp)")
FID_LOW_RE = re.compile(r"(movz|mov) w0, #(0x9|9)\b")
FID_HIGH_RE = re.compile(r"movk w0, #(0x8400|33792), lsl #16\b")
# Superset of pb.STORE_RE: adds plain str (P1B probes never stored, the
# negative fixture must prove the gate catches one).
T0_STORE_RE = re.compile(
    r"\b(st|str|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|cas|swp|adrp)\b",
    re.I)
# "nop": code-section .p2align padding (frozen FIX8 has one at trampoline
# 0x24; the T0 terminal loop is followed by one at 0x64).
PADDING_MNEMS = {"udf", ".inst", ".word", "nop"}


def fail(label: str, detail: str = "") -> None:
    iso.fail(label, detail)


def sha(data: bytes) -> str:
    return pb.sha(data)


def ops_from_dump(dump: str, code_end: int | None = None) -> str:
    lines = []
    for line in dump.splitlines():
        m = re.match(r"^\s*([0-9a-f]+):", line)
        if not m:
            continue
        if code_end is not None and int(m.group(1), 16) >= code_end:
            continue
        lines.append(re.sub(r"\s+", " ", line.split(":", 1)[-1])
                     .strip().lower())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reusable gates (negative fixtures call these with mutated inputs).
# ---------------------------------------------------------------------------

def gate_no_relocations(rel_text: str, label: str) -> None:
    if "R_AARCH64_" in rel_text:
        fail("T0_RELOC_FAILED", f"{label}: {rel_text[:200]}")


def gate_ops_order(ops: str) -> None:
    pos = -1
    for tok, is_re in ORDER_TOKENS:
        if is_re:
            m = re.search(tok, ops)
            p = m.start() if m else -1
        else:
            p = ops.find(tok)
        if p < 0:
            fail("T0_DISASM_FAILED", f"missing {tok!r}")
        if p <= pos:
            fail("T0_DISASM_FAILED", f"order violation at {tok!r}")
        pos = p


def gate_branch_targets(dump: str, t0_len: int) -> None:
    for line in dump.splitlines():
        m = BRANCH_RE.match(line)
        if not m:
            continue
        target = int(m.group(3), 16)
        if target >= t0_len or target % 4:
            fail("T0_DISASM_FAILED",
                 f"branch target {target:#x} outside T0 trampoline")


def gate_terminal(dump: str, code_end: int) -> None:
    instrs = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        if addr < code_end:
            instrs.append((addr, m.group(2), m.group(3)))
    if len(instrs) < 4:
        fail("T0_DISASM_FAILED", "trampoline code region too short")
    smc_idx = [i for i, (_a, mn, _o) in enumerate(instrs) if mn == "smc"]
    if len(smc_idx) != 1:
        fail("T0_DISASM_FAILED", f"smc count {len(smc_idx)}")
    smc = smc_idx[0]
    if smc + 2 >= len(instrs):
        fail("T0_DISASM_FAILED", "no wfe loop after smc")
    nxt = instrs[smc + 1]
    if nxt[1] != "wfe":
        fail("T0_DISASM_FAILED",
             f"instruction after smc is {nxt[1]!r}, not wfe (fall-through)")
    term = instrs[smc + 2]
    if term[1] != "b":
        fail("T0_DISASM_FAILED",
             f"instruction after wfe is {term[1]!r}, not b")
    m = re.match(r"^(?:0x)?([0-9a-f]+)$", term[2].strip())
    if not m or int(m.group(1), 16) != nxt[0]:
        fail("T0_DISASM_FAILED",
             f"terminal b does not target wfe at {nxt[0]:#x}")
    for ins in instrs[smc + 3:]:
        if ins[1] not in PADDING_MNEMS:
            fail("T0_DISASM_FAILED",
                 f"instruction after terminal loop: {ins!r}")


def gate_register_discipline(ops: str) -> None:
    cp = ops.find("mov x3, xzr")
    if cp < 0:
        fail("T0_DISASM_FAILED", "x0-x3 setup missing")
    pos = 0
    for line in ops.splitlines():
        start = pos
        pos += len(line) + 1
        fields = line.split(" ")
        if len(fields) < 3:
            continue
        dst = fields[2].rstrip(",")
        if not DST_RE.fullmatch(dst):
            continue
        if start <= cp:  # boundary line (mov x3, xzr) belongs to the setup
            allowed = {"x0", "x1", "x2", "x3", "x9"}
        else:
            allowed = {"x9", "x10", "x11", "x12", "x13"}
            if dst in ("w0", "x0") and (FID_LOW_RE.search(line)
                                        or FID_HIGH_RE.search(line)):
                continue
        if dst not in allowed:
            fail("T0_DISASM_FAILED", f"register discipline: {line!r}")


def gate_no_forbidden(ops: str) -> None:
    m = T0_STORE_RE.search(ops)
    if m:
        fail("T0_DISASM_FAILED", f"store/adrp present: {m.group(0)!r}")
    for bad in (r"\bbl\b", r"\blr\b", r"\beret\b", r"\bsctlr\b",
                r"\bmsr\b\s+daifclr", r"\bsp\b", r"\bwsp\b",
                r"\bx29\b", r"\bx30\b"):
        if re.search(bad, ops):
            fail("T0_DISASM_FAILED", f"forbidden {bad!r}")
    if hex(OFF_PRIMARY_FROZEN) in ops or "primary_entry" in ops:
        fail("T0_DISASM_FAILED", "primary_entry reference in T0 device trampoline")


def gate_t0_device_gates(ops: str, dump: str, t0_len: int,
                         code_end: int) -> None:
    gate_ops_order(ops)
    gate_branch_targets(dump, t0_len)
    gate_terminal(dump, code_end)
    gate_register_discipline(ops)
    gate_no_forbidden(ops)


def gate_payload_diff(frozen: bytes, cand: bytes, t0_len: int) -> list[int]:
    if len(cand) != len(frozen):
        fail("T0_PAYLOAD_DIFF_FAILED",
             f"size drift {len(cand)} != {len(frozen)}")
    diffs = [i for i in range(len(frozen)) if frozen[i] != cand[i]]
    lo, hi = TRAMP_OFFSET, TRAMP_OFFSET + t0_len
    bad = [i for i in diffs if not lo <= i < hi]
    if bad:
        fail("T0_PAYLOAD_DIFF_FAILED",
             f"diff outside checkpoint region at {bad[:8]}")
    if not diffs:
        fail("T0_PAYLOAD_DIFF_FAILED", "no checkpoint diff (patch lost?)")
    return diffs


def gate_trailer(payload: bytes) -> bytes:
    hdr = pb.parse_image_hdr(payload, "t0-payload")
    dtb_offset, _gap = pb.calc_dtb_offset(hdr["image_size"])
    trailer = payload[dtb_offset:]
    if payload[dtb_offset:dtb_offset + 4] != struct.pack(">I", pb.FDT_MAGIC):
        fail("T0_PAYLOAD_DIFF_FAILED", "no FDT magic at DTB_OFFSET")
    if sha(trailer) != RT_D_SHA or len(trailer) != RT_D_SIZE:
        fail("T0_PAYLOAD_DIFF_FAILED", f"trailer RT-D identity "
             f"sha={sha(trailer)} len={len(trailer)}")
    return trailer


def gate_geometry(payload: bytes) -> tuple[dict, int, int, int]:
    hdr = pb.parse_image_hdr(payload, "t0-payload")
    if hdr["image_size"] != FIX8_IMAGE_HEADER_IMAGE_SIZE:
        fail("T0_GEOMETRY_FAILED",
             f"image_size {hdr['image_size']:#x} != "
             f"{FIX8_IMAGE_HEADER_IMAGE_SIZE:#x}")
    dtb_offset, gap = pb.calc_dtb_offset(hdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("T0_GEOMETRY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T0_GEOMETRY_FAILED",
             f"payload len {len(payload)} != dtb_offset + RT_D")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T0_GEOMETRY_FAILED", "2MiB residue geometry")
    boot_est = pb.align(PAGE + len(payload), PAGE) + PAGE
    if boot_est != FIX8_BOOT_SIZE_EXPECTED:
        fail("T0_GEOMETRY_FAILED",
             f"boot_est {boot_est} != {FIX8_BOOT_SIZE_EXPECTED}")
    if BOOT_CAP - boot_est < 0x1000000:
        fail("T0_GEOMETRY_FAILED", "capacity margin < 16MiB")
    return hdr, dtb_offset, gap, boot_est


# ---------------------------------------------------------------------------
# Preregistered supporting decoder (prompt sections 27-29).
# ---------------------------------------------------------------------------

def t0_programmed_estimate(t0_total_s: float) -> float:
    return t0_total_s - P0_REF_OVERHEAD_S


def t0_window(est: float) -> str:
    d = abs(est - T0_DELAY_S)
    if d <= STRONG_HALF_WINDOW_S:
        return "STRONG"
    if d <= SUPPORTED_HALF_WINDOW_S:
        return "SUPPORTED"
    return "OUTSIDE"


def early_return_class(t0_total_s: float) -> bool:
    return t0_total_s < EARLY_RETURN_CLASS_LIMIT_S


def t0_reachability(t0_total_s: float | None, recovery_kind: str) -> dict:
    """Triple condition: timer window + early-return class + automatic reset.
    A negative NEVER licenses T0_NOT_REACHED; it routes to failure isolation.
    """
    if t0_total_s is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED",
                "next": "T0_FAILURE_ISOLATION_CI",
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    est = t0_programmed_estimate(t0_total_s)
    window = t0_window(est)
    early = early_return_class(t0_total_s)
    if window in ("STRONG", "SUPPORTED") and early:
        return {"verdict": window,
                "next": "MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI",
                "reason": "TIMER_SIGNATURE+EARLY_RETURN_CLASS+AUTOMATIC_RESET"}
    return {"verdict": "NOT_OBSERVED",
            "next": "T0_FAILURE_ISOLATION_CI",
            "reason": f"WINDOW={window} "
                      f"EARLY_RETURN_CLASS_MATCH={'YES' if early else 'NO'}"}


def run_decoder_fixtures() -> list[str]:
    lines = []

    def case(name, total, kind, want_verdict, want_next=None):
        got = t0_reachability(total, kind)
        if got["verdict"] != want_verdict:
            fail("T0_DECODER_FIXTURE_FAILED",
                 f"{name}: verdict {got['verdict']} != {want_verdict}")
        if want_next and got["next"] != want_next:
            fail("T0_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"T0_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"reason={got['reason']}")

    case("STRONG_14P2S", 14.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI")
    case("STRONG_12P7S", 12.7, "AUTOMATIC_ANDROID_RETURN", "STRONG")
    case("SUPPORTED_16P5S", 16.5, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED")
    case("SUPPORTED_17P1S", 17.1, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED")
    case("SUPPORTED_11P2S", 11.2, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED")
    case("OUTSIDE_17P2S", 17.2, "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T0_FAILURE_ISOLATION_CI")
    case("OUTSIDE_11P0S", 11.0, "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED")
    # Early class alone is NOT sufficient (prompt section 28).
    case("EARLY_BUT_OUTSIDE_8P0S", 8.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T0_FAILURE_ISOLATION_CI")
    # Old auto-return class: no timer signature, no NOT_REACHED license.
    case("LATE_24P0S", 24.0, "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T0_FAILURE_ISOLATION_CI")
    case("LATE_PANIC30_CLASS_26P289S", PANIC30_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED")
    # Non-Android returns / no timing product.
    case("STABLE_FASTBOOT_CASE_C", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "T0_FAILURE_ISOLATION_CI")
    case("NO_RETURN_CASE_D", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "T0_FAILURE_ISOLATION_CI")
    case("UNKNOWN_KIND", 14.2, "UNKNOWN", "NOT_OBSERVED")
    est = t0_programmed_estimate(FIX8_TOTAL_S)
    if abs(est - (FIX8_TOTAL_S - P0_REF_OVERHEAD_S)) > 1e-9:
        fail("T0_DECODER_FIXTURE_FAILED", "estimate arithmetic")
    lines.append(f"T0_DECODER_REFERENCE est(FIX8 {FIX8_TOTAL_S}s)={est:.4f}s "
                 f"window={t0_window(est)} (reference record only)")
    lines.append("T0_DECODER_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# Negative fixtures (prompt section 25) against the real gate functions.
# ---------------------------------------------------------------------------

def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("T0_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"T0_NEGATIVE_{name}_REJECTED=PASS"
    fail("T0_NEGATIVE_FIXTURE_FAILED", f"{name}: ACCEPTED (must reject)")


def run_negative_fixtures(ops: str, dump: str, t0_len: int, code_end: int,
                          cand: bytes) -> list[str]:
    lines: list[str] = []
    ops_lines = ops.splitlines()

    def idx(text: str) -> int:
        for i, ln in enumerate(ops_lines):
            if text in ln:
                return i
        fail("T0_NEGATIVE_FIXTURE_FAILED", f"line {text!r} not found")

    def dump_insert_after(anchor_mnem: str, extra: list[str]) -> str:
        out = []
        for ln in dump.splitlines():
            out.append(ln)
            m = INSTR_RE.match(ln)
            if m and m.group(2) == anchor_mnem:
                out.extend(extra)
        return "\n".join(out) + "\n"

    # 1. checkpoint moved BEFORE the x0-x3 setup -> order gate.
    v1 = list(ops_lines)
    v1.insert(idx("mov x3, xzr"), v1.pop(idx("mrs x9, cntfrq_el0")))
    # 2. primary_entry branch present (frozen FIX8 layout shape) -> branch
    #    target gate.
    v2 = list(ops_lines)
    v2.insert(idx("mrs x9, cntfrq_el0"), "00000000 b 0x1b1c0a0")
    # 3. wrong delay constant (24s); llvm-objdump may print #8 or #0x8.
    v3 = re.sub(r"x10, #(?:0x)?8\b", "x10, #24", ops)
    # 4. wrong PSCI FID high half.
    v4 = FID_HIGH_RE.sub("movk w0, #0x8401, lsl #16", ops)
    # 5. missing smc.
    v5 = "\n".join(ln for ln in ops_lines
                   if not re.search(r"smc #(0x)?0\b", ln)) + "\n"
    # 6. prototype-style fall-through after smc return.
    v6 = ops.replace(
        [ln for ln in ops_lines if re.search(r"smc #(0x)?0\b", ln)][0],
        "00000000 smc #0\n00000000 mov x0, x15\n00000000 mov x1, xzr\n"
        "00000000 mov x2, xzr\n00000000 mov x3, xzr\n00000000 b 0x1b1c0a0")

    chain = [
        ("T0_BEFORE_X0_SETUP", "\n".join(v1) + "\n", dump),
        ("T0_AFTER_PRIMARY_ENTRY", "\n".join(v2) + "\n",
         dump_insert_after("wfe", ["  70: 14000000 b 0x1b1c0a0"])),
        ("WRONG_DELAY", v3, dump),
        ("WRONG_PSCI_FID", v4, dump),
        ("MISSING_SMC", v5, dump),
        ("FALLTHROUGH_AFTER_SMC", v6,
         dump_insert_after("smc", ["  70: 00000000 mov x0, x15",
                                   "  74: 00000000 mov x1, xzr",
                                   "  78: 00000000 mov x2, xzr",
                                   "  7c: 00000000 mov x3, xzr",
                                   "  80: 14000000 b 0x1b1c0a0"])),
    ]
    for name, v, d in chain:
        lines.append(expect_reject(
            name,
            lambda vv=v, dd=d: gate_t0_device_gates(vv, dd, t0_len, code_end),
            "T0_DISASM_FAILED"))
    lines.append(expect_reject(
        "STACK_USE", lambda: gate_no_forbidden(
            ops + "\n00000000 stp x29, x30, [sp, #-32]!"),
        "T0_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_STORE", lambda: gate_no_forbidden(
            ops + "\n00000000 str x9, [x0]"), "T0_DISASM_FAILED"))
    lines.append(expect_reject(
        "ABSOLUTE_ADDRESS", lambda: gate_no_forbidden(
            ops + "\n00000000 adrp x9, 0x2300000"), "T0_DISASM_FAILED"))
    lines.append(expect_reject(
        "RELOCATIONS", lambda: gate_no_relocations(
            "0000000000000000 R_AARCH64_ABS64 dtb_rel", "fixture"),
        "T0_RELOC_FAILED"))
    lines.append(expect_reject(
        "GEOMETRY_CHANGED", lambda: gate_geometry(cand + b"\x00" * 4),
        "T0_GEOMETRY_FAILED"))
    bad = bytearray(cand)
    bad[DTB_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "RT_D_CHANGED", lambda: gate_trailer(bytes(bad)),
        "T0_PAYLOAD_DIFF_FAILED"))
    lines.append("T0_NEGATIVE_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# T0 device trampoline build + payload patch.
# ---------------------------------------------------------------------------

def probe_syms(readelf: str, elf: Path) -> dict[str, int]:
    out = pb.run([readelf, "-sW", str(elf)])
    found: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[7] in ("r3_t0_device_entry", "dtb_rel"):
            found[parts[7]] = int(parts[1], 16)
    return found


def build_t0_device(out: Path, tools: dict,
                    dtb_offset: int) -> tuple[bytes, str, str, dict]:
    defines_base = ["-DP1B_T0_DELAY=8"]
    pre_elf = out / "p1b-t0-device-pre.elf"
    iso.assemble_probe(T0_DEVICE_S, T0_DEVICE_LD,
                       ["-DP1B_DTB_REL=0", *defines_base], pre_elf, tools)
    offs0 = probe_syms(tools["readelf"], pre_elf)
    if set(offs0) != {"r3_t0_device_entry", "dtb_rel"}:
        fail("T0_BUILD_FAILED", f"symbols {sorted(offs0)}")
    if offs0["r3_t0_device_entry"] != 0:
        fail("T0_BUILD_FAILED", "entry not at ELF 0")
    dtb_rel = dtb_offset - (TRAMP_OFFSET + offs0["dtb_rel"])
    if dtb_rel <= 0:
        fail("T0_BUILD_FAILED", f"dtb_rel {dtb_rel:#x}")
    elf = out / "p1b-t0-device-trampoline.elf"
    iso.assemble_probe(T0_DEVICE_S, T0_DEVICE_LD,
                       [f"-DP1B_DTB_REL={dtb_rel}", *defines_base],
                       elf, tools)
    offs1 = probe_syms(tools["readelf"], elf)
    if offs1 != offs0:
        fail("T0_BUILD_FAILED", "layout shifted with dtb_rel")
    binp = out / "p1b-t0-device-trampoline.bin"
    pb.run([tools["objcopy"], "-O", "binary", str(elf), str(binp)])
    tbin = binp.read_bytes()
    if not (0x60 <= len(tbin) <= 0x80):
        fail("T0_BUILD_FAILED", f"size {len(tbin)}")
    code_end = offs1["dtb_rel"]
    if code_end % 4 or code_end < 0x60:
        fail("T0_BUILD_FAILED", f"code_end {code_end:#x}")
    dump = pb.run([tools["objdump"], "-d", str(elf)])
    (out / "p1b-t0-device-trampoline-disasm.txt").write_text(dump)
    ops = ops_from_dump(dump, code_end)
    gate_t0_device_gates(ops, dump, len(tbin), code_end)
    x0_static = TRAMP_OFFSET + offs1["dtb_rel"] + dtb_rel
    if x0_static != dtb_offset:
        fail("T0_BUILD_FAILED", f"x0 algebra {x0_static:#x} != {dtb_offset:#x}")
    dump_s = pb.run([tools["objdump"], "-s", "-j", ".text", str(elf)])
    if struct.pack("<Q", dtb_rel).hex() not in re.sub(r"\s+", "",
                                                      dump_s.lower()):
        fail("T0_BUILD_FAILED", "dtb_rel quad not in .text")
    print(f"T0_DEVICE_TRAMPOLINE sha256={sha(tbin)} size={len(tbin)} "
          f"dtb_rel={dtb_rel:#x} x0_static={x0_static:#x}")
    return tbin, ops, dump, {"dtb_rel": dtb_rel, "x0_static": x0_static,
                             "code_end": code_end}


def frozen_tramp_record(out: Path, tools: dict, frozen: bytes) -> dict:
    """Authoritative frozen FIX8 trampoline: extract, disassemble via an
    literal-.inst-word ELF, re-derive the primary_entry branch by algebra."""
    tramp = frozen[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T0_IDENTITY_FAILED", f"embedded trampoline sha={sha(tramp)}")
    binp = out / "frozen-fix8-trampoline.bin"
    binp.write_bytes(tramp)
    # Reassemble the frozen 48 bytes as literal .inst words (the proven
    # encoding path in this repo) and disassemble that ELF — byte-identical
    # to the embedded trampoline, no file-include dependency.
    words = struct.unpack_from(f"<{TRAMP_SIZE // 4}I", frozen, TRAMP_OFFSET)
    wrap = out / "frozen-fix8-trampoline-wrap.S"
    wrap.write_text(
        ".section .text, \"ax\", @progbits\n"
        ".globl r3_handoff_entry\n"
        "r3_handoff_entry:\n"
        + "".join(f".inst\t{w:#010x}\n" for w in words))
    elf = out / "frozen-fix8-trampoline.elf"
    ops = iso.assemble_probe(wrap, HERE / "p1b-trampoline.ld", [], elf, tools)
    dump = pb.run([tools["objdump"], "-d", str(elf)])
    (out / "frozen-fix8-trampoline-disasm.txt").write_text(dump)
    missing = [t for t in ("msr daifset, #0xf", "isb", "adr x0", "ldr x9",
                           "add x0, x0, x9", "mov x1, xzr", "mov x2, xzr",
                           "mov x3, xzr") if t not in ops]
    has_b = re.search(r"\bb\b", ops)
    if missing or not has_b:
        fail("T0_IDENTITY_FAILED",
             f"frozen trampoline disasm tokens missing={missing} "
             f"b={'yes' if has_b else 'no'}; dump:\n{dump}")
    w_b = words[8]  # b_primary at trampoline offset 0x20
    if (w_b >> 26) != 0b000101:
        fail("T0_IDENTITY_FAILED", f"trampoline word[8] not B: {w_b:#010x}")
    target = TRAMP_OFFSET + 0x20 + pb.sx(w_b & 0x03FFFFFF, 26) * 4
    if target != OFF_PRIMARY_FROZEN:
        fail("T0_IDENTITY_FAILED",
             f"frozen branch target {target:#x} != primary_entry "
             f"{OFF_PRIMARY_FROZEN:#x}")
    w_c1 = struct.unpack_from("<I", frozen, pb.CODE1_OFFSET)[0]
    if w_c1 != CODE1_B_0X40:
        fail("T0_IDENTITY_FAILED", f"code1 {w_c1:#010x} != b 0x40")
    print(f"T0_FROZEN_TRAMPOLINE_IDENTITY=PASS sha={TRAMP_SHA} "
          f"branch {TRAMP_OFFSET + 0x20:#x} -> {target:#x} (primary_entry)")
    return {"target": target}


def cmd_t0(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)

    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("T0_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA:
        fail("T0_IDENTITY_FAILED", f"frozen FIX8 payload sha={sha(frozen)}")
    if len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("T0_IDENTITY_FAILED",
             f"frozen FIX8 payload len {len(frozen)} != {FIX8_PAYLOAD_SIZE}")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["image_size"] != FIX8_IMAGE_HEADER_IMAGE_SIZE:
        fail("T0_IDENTITY_FAILED", f"frozen image_size {fhdr['image_size']:#x}")
    dtb_offset, gap = pb.calc_dtb_offset(fhdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("T0_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(frozen) - RT_D_SIZE != dtb_offset:
        fail("T0_IDENTITY_FAILED",
             "payload layout: len - RT_D_SIZE != dtb_offset")
    print("T0_FROZEN_FIX8_BASE=PASS sha=" + FIX8_PAYLOAD_SHA)
    print("T0_FROZEN_KERNEL_REGION=COMPOSITIONAL_HASH_ANCHORED")

    frec = frozen_tramp_record(out, tools, frozen)
    tbin, ops, dump, tinfo = build_t0_device(out, tools, dtb_offset)
    code_end = tinfo["code_end"]

    # Setup-words identity: only the two PC-relative dtb_rel references
    # (adr word[2], ldr-literal word[3]) may differ from the frozen trampoline.
    f_words = struct.unpack_from("<8I", frozen, TRAMP_OFFSET)
    t_words = struct.unpack_from("<8I", tbin, 0)
    diff_idx = [i for i in range(8) if f_words[i] != t_words[i]]
    if diff_idx != [2, 3]:
        fail("T0_BUILD_FAILED",
             f"setup words differ at {diff_idx}, expected [2, 3] only")
    print("T0_SETUP_WORDS_DIFFER_ONLY_IN_DTB_REL_PC_REFS=YES")

    # T0 payload: frozen bytes, trampoline checkpoint region replaced.
    cand = bytearray(frozen)
    cand[TRAMP_OFFSET:TRAMP_OFFSET + len(tbin)] = tbin
    cand = bytes(cand)
    diffs = gate_payload_diff(frozen, cand, len(tbin))
    trailer = gate_trailer(cand)
    hdr, dtb_off2, gap2, boot_est = gate_geometry(cand)
    if dtb_off2 != dtb_offset or trailer != frozen_rt_d:
        fail("T0_PAYLOAD_DIFF_FAILED", "trailer drifted vs frozen RT-D")
    payload_path = out / "thyme-r3-p1b-t0-kernel-payload.bin"
    payload_path.write_bytes(cand)
    diff_report = (
        "T0_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"T0_PAYLOAD_SHA256={sha(cand)}\n"
        f"PATCH_REGION=[{TRAMP_OFFSET:#x},{TRAMP_OFFSET + len(tbin):#x})\n"
        f"DIFF_BYTES={len(diffs)}\n"
        f"FIRST_DIFF={diffs[0]:#x} LAST_DIFF={diffs[-1]:#x}\n"
        f"DIFF_ATTRIBUTION=CHECKPOINT_REGION_ONLY\n"
        f"SETUP_WORDS_DIFF_INDICES={diff_idx} (adr/ldr PC-relative dtb_rel)\n"
        f"RT_D_TRAILER_IDENTICAL=YES sha={RT_D_SHA}\n"
        f"PAYLOAD_SIZE_IDENTICAL=YES {len(cand)}\n"
        f"DTB_OFFSET={dtb_offset:#x} GAP={gap:#x} "
        f"IMAGE_SIZE={hdr['image_size']:#x} BOOT_SIZE_EST={boot_est}\n"
        "T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY\n")
    (out / "t0-payload-diff-report.txt").write_text(diff_report)
    print(f"T0_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)} region=[{TRAMP_OFFSET:#x},"
          f"{TRAMP_OFFSET + len(tbin):#x})")

    neg_lines = run_negative_fixtures(ops, dump, len(tbin), code_end, cand)
    (out / "p1b-t0-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures()
    (out / "p1b-t0-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")

    report = (
        "T0_PREDEVICE_REPORT\n"
        f"T0_ENTRY=r3_t0_device_entry at payload offset {TRAMP_OFFSET:#x}\n"
        "T0_CHECKPOINT_POSITION=after DAIF mask + x0=S+DTB_OFFSET + "
        "x1=x2=x3=0; the frozen handoff's final 'branch primary_entry' slot "
        "is REPLACED by the checkpoint (no primary_entry branch exists)\n"
        "T0_AFTER_X0_X3_SETUP=YES\n"
        "T0_BEFORE_PRIMARY_ENTRY_BRANCH=YES\n"
        f"T0_BEFORE_PRIMARY_ENTRY_EVIDENCE=frozen b_primary at payload "
        f"{TRAMP_OFFSET + 0x20:#x} decoded target {frec['target']:#x} == "
        f"primary_entry; T0 contains no branch leaving "
        f"[{TRAMP_OFFSET:#x},{TRAMP_OFFSET + len(tbin):#x})\n"
        f"T0_DEVICE_CANDIDATE_DELAY={T0_DELAY_S}s\n"
        "T0_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY (cntfrq_el0 + cntpct_el0, "
        "poll loop, yield; no stack/memory/timer subsystem)\n"
        f"T0_RESET_PRIMITIVE=PSCI_SYSTEM_RESET "
        f"fid=0x{PSCI_SYSTEM_RESET_FID:08x} smc #0\n"
        "T0_FAIL_CLOSED_AFTER_RESET_RETURN=YES (smc return -> wfe forever; "
        "no restore, no primary_entry continuation)\n"
        f"T0_CLOBBER_REGISTERS={T0_CLOBBER_REGISTERS}\n"
        "T0_POSITION_INDEPENDENT=YES (PC-relative only, no absolute S, "
        "no load address)\n"
        "T0_RUNTIME_RELOCATIONS=0\n"
        "T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY\n"
        f"T0_TRAMPOLINE_SIZE={len(tbin)} dtb_rel={tinfo['dtb_rel']:#x} "
        f"x0_static={tinfo['x0_static']:#x} code_end={code_end:#x}\n"
        "T0_PROTOTYPE_FALLTHROUGH_AUDIT=p1b-t0-trampoline.S HAS smc-return "
        "-> restore -> primary_entry path; NOT device-ready; fail-closed T0 "
        "regenerated this round\n")
    (out / "p1b-t0-report.txt").write_text(report)

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "fix8_payload_sha256": FIX8_PAYLOAD_SHA,
        "fix8_payload_size": FIX8_PAYLOAD_SIZE,
        "fix8_tramp_sha256": TRAMP_SHA,
        "fix8_image_header_image_size": hex(FIX8_IMAGE_HEADER_IMAGE_SIZE),
        "fix8_primary_entry_offset": hex(OFF_PRIMARY_FROZEN),
        "fix8_boot_sha256": FORBIDDEN_BOOT_SHAS["FIX8_BOOT"],
        "panic30_boot_sha256": FORBIDDEN_BOOT_SHAS["PANIC30_BOOT"],
        "rt_d_frozen_sha256": RT_D_SHA,
        "rt_d_frozen_size": RT_D_SIZE,
        "t0_tramp_sha256": sha(tbin),
        "t0_tramp_size": len(tbin),
        "t0_tramp_dtb_rel": hex(tinfo["dtb_rel"]),
        "t0_payload_sha256": sha(cand),
        "t0_payload_size": len(cand),
        "t0_boot_size_est": boot_est,
        "t0_boot_kernel_size_field": len(cand),
        "dtb_offset": hex(dtb_offset),
        "gap": hex(gap),
        "image_size": hex(hdr["image_size"]),
        "patch_region": f"[{TRAMP_OFFSET:#x},{TRAMP_OFFSET + len(tbin):#x})",
        "diff_bytes": len(diffs),
        "t0_delay_seconds": T0_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "t0_clobber_registers": T0_CLOBBER_REGISTERS,
        "t0_fail_closed_after_reset_return": True,
        "t0_runtime_relocations": 0,
        "t0_runtime_semantic_delta": "TRAMPOLINE_CHECKPOINT_RESET_ONLY",
        "t0_payload_diff_attribution": "CHECKPOINT_REGION_ONLY",
        "decoder": {
            "kind": "SUPPORTING_DECODER_NOT_STRICT_INVARIANT",
            "ref_overhead_s": P0_REF_OVERHEAD_S,
            "programmed_s": T0_DELAY_S,
            "strong_half_window_s": STRONG_HALF_WINDOW_S,
            "supported_half_window_s": SUPPORTED_HALF_WINDOW_S,
            "early_return_class_limit_s": EARLY_RETURN_CLASS_LIMIT_S,
            "reference_totals_s": {"FIX8": FIX8_TOTAL_S,
                                   "PANIC30": PANIC30_TOTAL_S},
        },
        "observer": {"identity_env": "R3_T0_SHA256",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
        "prototype_fallthrough_audit":
            "p1b-t0-trampoline.S NOT device-ready; fail-closed T0 regenerated",
    }
    (out / "p1b-t0-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")

    gates = [
        "T0_BUILD_GATES=PASS",
        "T0_BASELINE=FROZEN_FIX8",
        "T0_AFTER_X0_X3_SETUP=YES",
        "T0_BEFORE_PRIMARY_ENTRY_BRANCH=YES",
        f"T0_DEVICE_CANDIDATE_DELAY={T0_DELAY_S}s",
        "T0_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "T0_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "T0_FAIL_CLOSED_AFTER_RESET_RETURN=YES",
        "T0_NO_STACK=YES",
        "T0_NO_MEMORY_WRITES=YES",
        "T0_POSITION_INDEPENDENT=YES",
        "T0_RUNTIME_RELOCATIONS=0",
        "T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY",
        "T0_PAYLOAD_DIFF_ATTRIBUTED=CHECKPOINT_REGION_ONLY",
        "T0_PAYLOAD_SIZE_IDENTICAL=YES",
        "T0_BOOT_KERNEL_SIZE_IDENTICAL=YES",
        "T0_BOOT_SIZE_IDENTICAL=YES",
        f"T0_DTB_OFFSET={DTB_OFFSET:#x}",
        "T0_RT_D_IDENTITY=YES",
        "T0_GEOMETRY_GATES=PASS",
        "T0_NEGATIVE_FIXTURES=PASS",
        "T0_DECODER_FIXTURES=PASS",
        "T0_PROTOTYPE_FALLTHROUGH_AUDIT="
        "DEVICE_PROTOTYPE_NOT_READY_FAIL_CLOSED_REGENERATED",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "p1b-t0-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))


# ---------------------------------------------------------------------------
# Observer fixture mode.
# ---------------------------------------------------------------------------

def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("t0_obs_fixtures",
                                                  OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-t0-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("T0_OBSERVER_FIXTURES=PASS")


# ---------------------------------------------------------------------------
# Private pack gates.
# ---------------------------------------------------------------------------

def cmd_t0_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("T0_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("T0_PACK_FAILED", f"payload sha={sha(payload)}")
    hdr = pb.parse_image_hdr(payload, "t0-payload")
    if hdr["image_size"] != FIX8_IMAGE_HEADER_IMAGE_SIZE:
        fail("T0_PACK_FAILED", f"image_size {hdr['image_size']:#x}")
    if struct.unpack_from("<I", payload, pb.CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("T0_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(hdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("T0_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T0_PACK_FAILED", "payload length")
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + T0_TRAMP_SIZE]
    if sha(tramp) != args.tramp_sha:
        fail("T0_PACK_FAILED", f"embedded trampoline sha={sha(tramp)}")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I",
                                                              pb.FDT_MAGIC):
        fail("T0_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "t0-candidate")
    if cand["kernel"] != payload:
        fail("T0_PACK_FAILED", "candidate kernel != T0 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("T0_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("T0_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("T0_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("T0_PACK_FAILED", "reserved differs from M5D")
    if cand["ramdisk_size"] != ref["ramdisk_size"]:
        fail("T0_PACK_FAILED", "ramdisk_size differs")
    if cand["tail_pad"] != ref["tail_pad"]:
        fail("T0_PACK_FAILED", "tail padding policy differs")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("T0_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("T0_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T0_PACK_FAILED", "DTB residue geometry")
    if len(boot) >= BOOT_CAP or BOOT_CAP - len(boot) < 0x1000000:
        fail("T0_PACK_FAILED", "capacity")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-t0-pack-gates.txt"
    report.write_text(
        "T0_PACK_GATES=PASS\n"
        f"T0_BOOT_SIZE={len(boot)}\n"
        f"T0_BOOT_SHA256={sha(boot)}\n"
        f"T0_PAYLOAD_SHA256={sha(payload)}\n"
        f"T0_TRAMP_SHA256={sha(tramp)}\n"
        f"T0_KERNEL_SIZE={len(payload)}\n"
        f"T0_DTB_OFFSET={dtb_offset:#x}\n"
        "T0_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "T0_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "T0_BOOT_CAPACITY=PASS\n"
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


# ---------------------------------------------------------------------------
# Source gate.
# ---------------------------------------------------------------------------

def need(text: str, needle: str, label: str = "T0_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str, label: str = "T0_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [T0_DEVICE_S, T0_DEVICE_LD, T0_PROTO_S, OBSERVER,
                OBSERVER_FIXTURES, Path(__file__), DOC, STATUS_DOC, WF,
                HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld"]
    for path in required:
        if not path.is_file():
            fail("T0_SOURCE_GATE_FAILED", f"missing {path}")
    dev = T0_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "adr\tx0, dtb_rel", "ldr\tx9, dtb_rel",
                  "mov\tx1, xzr", "mov\tx2, xzr", "mov\tx3, xzr",
                  "mrs\tx9, cntfrq_el0", "mrs\tx11, cntpct_el0",
                  "mrs\tx12, cntpct_el0", "yield", "smc\t#0", "wfe",
                  "P1B_DTB_REL", "P1B_T0_DELAY", ".quad\tP1B_DTB_REL",
                  "#if (P1B_T0_DELAY) != 8"):
        need(dev, token)
    # Fail-closed: no primary_entry continuation of any kind.
    for token in ("P1B_ENTRY_REL", "b_primary", "x15", "eret", "sctlr",
                  "b\tprimary", "fall through"):
        forbid(dev, token)
    # Prototype fall-through audit truth (prompt section 14): the CI
    # prototype must retain its failsafe path so the audit stays verifiable.
    proto = T0_PROTO_S.read_text()
    for token in ("mov\tx15, x0", "mov\tx0, x15", "P1B_ENTRY_REL",
                  "b_primary"):
        need(proto, token, "T0_PROTOTYPE_AUDIT_FAILED")
    obs = OBSERVER.read_text()
    for token in ("R3_T0_SHA256", "T0_OBSERVER_MISBOOT_REFUSED",
                  "T0_BOOTING_TO_RETURNED_KERNEL_START",
                  "T0_PROGRAMMED_ESTIMATE", "T0_REACHABILITY_SIGNATURE",
                  "T0_FAILURE_ISOLATION_CI", "FASTBOOT_BOOT_ONLY"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("T0_OBSERVER_MISBOOT_REFUSED", "NOT_REACHED"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("T0_AFTER_X0_X3_SETUP=YES",
                  "T0_BEFORE_PRIMARY_ENTRY_BRANCH=YES",
                  "TRAMPOLINE_CHECKPOINT_RESET_ONLY", "wfe",
                  "CHECKPOINT_REGION_ONLY", "0x2380000", "0x84000009",
                  "T0_FAILURE_ISOLATION", "STRONG", "SUPPORTED",
                  "6.1445", "READY_FOR_R3_P1B_T0_DEVICE_CONTROL",
                  "R3_P1B_T0_PREDEVICE_NOT_READY"):
        need(doc, token)
    status = STATUS_DOC.read_text()
    for token in ("MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI",
                  "NO_SUPPORTED_SHIFT", "T0 CI_PASS", "T2 DESIGNED",
                  "NOT_PROVEN", "FROZEN"):
        need(status, token)
    wf_text = WF.read_text()
    for token in ("p1b-t0-device.S", "p1b-t0-predevice.py",
                  "thyme-r3-p1b-t0", "T0_BUILD_GATES=PASS",
                  "observer-fixtures"):
        need(wf_text, token)
    for path in REPO.rglob("*.img"):
        rel = path.relative_to(REPO).as_posix()
        top = rel.split("/", 1)[0]
        if top in ("linux-6.6", "test", "route-a-v2-artifact",
                   "thyme-mainline-firstboot-29bc752517c53a5532bd1974e3bff59cca5af391"):
            continue
        if "r3-p1b" in rel or "p1b" in rel:
            fail("T0_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    print("T0_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "t0", "observer-fixtures", "t0-pack-gates"),
        required=True)
    parser.add_argument("--out", default="out-t0")
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
    parser.add_argument("--m5d-boot")
    parser.add_argument("--m5d-sha", default=(
        "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"))
    parser.add_argument("--payload")
    parser.add_argument("--payload-sha")
    parser.add_argument("--tramp-sha")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
    elif args.mode == "t0":
        if not (args.rt_d and args.fix8_payload):
            fail("T0_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_t0(args)
    elif args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
    elif args.mode == "t0-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.tramp_sha and args.out)
        if not need_all:
            fail("T0_PACK_FAILED", "need --m5d-boot --payload --boot "
                                    "--payload-sha --tramp-sha --out")
        cmd_t0_pack_gates(args)


if __name__ == "__main__":
    main()
