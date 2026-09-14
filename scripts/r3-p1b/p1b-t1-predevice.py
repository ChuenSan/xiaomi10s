#!/usr/bin/env python3
"""R3 P1B T1 predevice readiness (MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source/doc boundary checks (no build)
  t1                  frozen-FIX8-anchored T1-8 fail-closed device candidate:
                      kernel rebuild (authoritative vmlinux + System.map),
                      primary_entry re-derivation (never a history constant),
                      original first-instruction confirmation, checkpoint
                      placement from the padding map, checkpoint build + gates,
                      frozen-byte payload patch + diff attribution, geometry,
                      negative fixtures, T0-matched-control decoder fixtures
  observer-fixtures   T1 observer fixture suite (imports the observer module)
  t1-pack-gates       private: gates over a packed T1 boot v3 image

T1 baseline is the exact frozen FIXED INIT8 payload (public run 34741153230).
The ONLY changes vs those frozen bytes:
  A. primary_entry's first instruction (bl record_mmu_state) is replaced by
     "b T1_CHECKPOINT" — the T1 checkpoint is reached through the REAL,
     byte-identical FIX8 trampoline branch;
  B. the T1 diagnostic checkpoint bytes, written into the deterministic zero
     padding after the Image file and before the RT-D trailer.
The trampoline, RT-D, Image bytes, /init, initramfs, payload size, boot
envelope geometry are all identical to FIX8. T1 is a DESTRUCTIVE diagnostic:
it never returns to primary_entry and never continues normal Linux
(T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO); a future positive proves ONLY
PRIMARY_ENTRY_ADDRESS_REACHABILITY (R2), never E1.

Future T1 timing is matched-control against T0 (primary reference
T0_TOTAL = 14.252 s): STRONG |T1_MINUS_T0| <= 1.0 s, SUPPORTED <= 2.0 s, plus
T1_TOTAL < 20 s and AUTOMATIC_ANDROID_RETURN. The P0 6.1445 s decoder is
SECONDARY cross-check only.
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
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1b-t1-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-t1-predevice.yml"
T1_DEVICE_S = HERE / "p1b-t1-device.S"
T1_DEVICE_LD = HERE / "p1b-t1-device.ld"
T1_PROTO_S = HERE / "p1b-t1-gap-probe.S"
OBSERVER = HERE / "observe-r3-p1b-t1.py"
OBSERVER_FIXTURES = HERE / "observer-t1-fixtures.py"

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
CODE1_OFFSET = pb.CODE1_OFFSET
PAGE = pb.PAGE
BOOT_CAP = pb.BOOT_CAP
FDT_MAGIC = pb.FDT_MAGIC
DTB_OFFSET = 0x2380000
# Section 11: image_size is ALWAYS re-read from the authoritative Image header
# of the artifact under test (the frozen FIX8 payload first, the rebuilt Image
# as the independent second source) and reported verbatim. The two historical
# readings below are audit context only and gate nothing.
FIX8_IMAGE_SIZE_HISTORY_READINGS = (0x2230000, 0x2231000)
IMAGE_HEADER_IMAGE_SIZE = 0  # authored by cmd_t1() from the real header
CODE1_B_0X40 = 0x1400000F
FIX8_PAYLOAD_SHA = (
    "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41")
FIX8_PAYLOAD_SIZE = DTB_OFFSET + RT_D_SIZE  # 37369041
FIX8_IMAGE_SHA = iso.FIX8_IMAGE_SHA
FIX8_IMAGE_FILE_SIZE = iso.FIX8_IMAGE_FILE_SIZE
FIX8_INIT_SHA = iso.FIX8_INIT_SHA
FIX8_CPIO_SHA = iso.FIX8_CPIO_SHA
TRAMP_SHA = iso.TRAMP_SHA
TRAMP_SIZE = 48
PSCI_SYSTEM_RESET_FID = 0x84000009
T1_DELAY_S = 8
# Misboot refusal list for the T1 observer (prompt section 30): boots that
# must NEVER run through the T1 observer, refused BEFORE any fastboot
# interaction.
FORBIDDEN_BOOT_SHAS = {
    "T0_BOOT":
        "8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1",
    "FIX8_BOOT":
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5",
    "PANIC30_BOOT":
        "ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1",
    "OLD_INIT8_BOOT":
        "e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264",
    "ENTRY_STATE_PROBE_BOOT":
        "cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c",
}
# Preregistered matched-control timing (prompt sections 31-34): the PRIMARY
# reference is the T0 true-device total (same payload class, same 8s CNTPCT,
# same PSCI reset; only the checkpoint moved trampoline-end -> primary_entry).
T0_REFERENCE_TOTAL_S = 14.252
T1_STRONG_HALF_WINDOW_S = 1.0
T1_SUPPORTED_HALF_WINDOW_S = 2.0
T1_EARLY_RETURN_CLASS_LIMIT_S = 20.0
T1_CASE_C_BAND_S = (20.0, 28.0)  # old auto-return class (FIX8 23.852 / P30 26.289)
P0_REF_OVERHEAD_S = 6.1445
T1_CLOBBER_REGISTERS = "w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV"
T1_BOOT_SIZE_EXPECTED = 37380096
FIX8_TOTAL_S = 23.852  # old INIT8 auto-return class reference
PANIC30_TOTAL_S = 26.289  # PANIC30 auto-return class reference

ORDER_TOKENS = [
    ("msr daifset, #0xf", False),
    ("isb", False),
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
T1_STORE_RE = re.compile(
    r"\b(st|str|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|cas|swp|adrp)\b",
    re.I)
T1_LOAD_RE = re.compile(
    r"\b(ldr|ldrb|ldrh|ldp|ldur|ldar|ldxr|ldtr)\b", re.I)
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
        fail("T1_RELOC_FAILED", f"{label}: {rel_text[:200]}")


def gate_ops_order(ops: str) -> None:
    pos = -1
    for tok, is_re in ORDER_TOKENS:
        if is_re:
            m = re.search(tok, ops)
            p = m.start() if m else -1
        else:
            p = ops.find(tok)
        if p < 0:
            fail("T1_DISASM_FAILED", f"missing {tok!r}")
        if p <= pos:
            fail("T1_DISASM_FAILED", f"order violation at {tok!r}")
        pos = p


def gate_branch_targets(dump: str, probe_len: int) -> None:
    for line in dump.splitlines():
        m = BRANCH_RE.match(line)
        if not m:
            continue
        target = int(m.group(3), 16)
        if target >= probe_len or target % 4:
            fail("T1_DISASM_FAILED",
                 f"branch target {target:#x} outside T1 checkpoint")


def gate_terminal(dump: str) -> None:
    instrs = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if m:
            instrs.append((int(m.group(1), 16), m.group(2), m.group(3)))
    smc_idx = [i for i, (_a, mn, _o) in enumerate(instrs) if mn == "smc"]
    if len(smc_idx) != 1:
        fail("T1_DISASM_FAILED", f"smc count {len(smc_idx)}")
    smc = smc_idx[0]
    if smc + 2 >= len(instrs):
        fail("T1_DISASM_FAILED", "no wfe loop after smc")
    nxt = instrs[smc + 1]
    if nxt[1] != "wfe":
        fail("T1_DISASM_FAILED",
             f"instruction after smc is {nxt[1]!r}, not wfe (fall-through)")
    term = instrs[smc + 2]
    if term[1] != "b":
        fail("T1_DISASM_FAILED",
             f"instruction after wfe is {term[1]!r}, not b")
    m = re.match(r"^(?:0x)?([0-9a-f]+)", term[2].strip().split("<", 1)[0])
    if not m or int(m.group(1), 16) != nxt[0]:
        fail("T1_DISASM_FAILED",
             f"terminal b does not target wfe at {nxt[0]:#x} "
             f"(operand {term[2]!r})")
    for ins in instrs[smc + 3:]:
        if ins[1] not in PADDING_MNEMS:
            fail("T1_DISASM_FAILED",
                 f"instruction after terminal loop: {ins!r}")


def gate_register_discipline(ops: str) -> None:
    for line in ops.splitlines():
        fields = line.split(" ")
        if len(fields) < 3:
            continue
        dst = fields[2].rstrip(",")
        if not DST_RE.fullmatch(dst):
            continue
        if dst in ("x1", "x2", "x3", "w1", "w2", "w3"):
            fail("T1_DISASM_FAILED",
                 f"boot contract register written: {line!r}")
        if dst in ("x0", "w0"):
            if not (FID_LOW_RE.search(line) or FID_HIGH_RE.search(line)):
                fail("T1_DISASM_FAILED", f"x0/w0 written off-FID: {line!r}")
            continue
        if dst not in {"x9", "x10", "x11", "x12", "x13"}:
            fail("T1_DISASM_FAILED", f"register discipline: {line!r}")


def gate_no_forbidden(ops: str) -> None:
    m = T1_STORE_RE.search(ops)
    if m:
        fail("T1_DISASM_FAILED", f"store/adrp present: {m.group(0)!r}")
    m = T1_LOAD_RE.search(ops)
    if m:
        fail("T1_DISASM_FAILED",
             f"memory load present (no x0 dereference allowed): {m.group(0)!r}")
    for bad in (r"\bbl\b", r"\blr\b", r"\beret\b", r"\bsctlr\b",
                r"\bmsr\b\s+daifclr", r"\bsp\b", r"\bwsp\b",
                r"\bx29\b", r"\bx30\b"):
        if re.search(bad, ops):
            fail("T1_DISASM_FAILED", f"forbidden {bad!r}")
    if "primary_entry" in ops:
        fail("T1_DISASM_FAILED", "primary_entry reference in T1 checkpoint")


def gate_t1_probe(ops: str, dump: str, probe_len: int) -> None:
    gate_ops_order(ops)
    gate_branch_targets(dump, probe_len)
    gate_terminal(dump)
    gate_register_discipline(ops)
    gate_no_forbidden(ops)


def gate_original_insn(word: int, off_primary: int,
                       off_record_mm: int) -> int:
    if (word >> 26) != 0b100101:
        fail("T1_IDENTITY_FAILED",
             f"frozen word at primary_entry {word:#010x} is not BL")
    target = off_primary + pb.sx(word & 0x03FFFFFF, 26) * 4
    if target != off_record_mm:
        fail("T1_IDENTITY_FAILED",
             f"BL target {target:#x} != record_mmu_state {off_record_mm:#x}")
    return target


def gate_vmlinux_original_insn(pe_dump: str, off_primary: int,
                               off_record_mm: int, text_addr: int) -> int:
    """Section 7: the authoritative vmlinux disassembly must show the SAME
    first instruction the frozen payload bytes and head.S do."""
    insns = [l for l in pe_dump.splitlines() if re.match(r"^\s*[0-9a-f]+:", l)]
    if not insns:
        fail("T1_IDENTITY_FAILED", "empty primary_entry disassembly")
    first = insns[0]
    addr = int(re.match(r"^\s*([0-9a-f]+):", first).group(1), 16)
    if addr != text_addr + off_primary:
        fail("T1_IDENTITY_FAILED",
             f"vmlinux disasm starts at {addr:#x}, expected "
             f"{text_addr + off_primary:#x}")
    if not re.search(r"\sbl\s", first):
        fail("T1_IDENTITY_FAILED",
             f"vmlinux primary_entry first instruction not BL: {first!r}")
    ann = re.search(r"<([^>]+)>", first)
    if ann and ann.group(1) != "record_mmu_state":
        fail("T1_IDENTITY_FAILED",
             f"vmlinux BL annotation {ann.group(1)!r} != record_mmu_state")
    op = re.search(r"\sbl\s+(?:0x)?([0-9a-f]+)", first)
    if not op:
        fail("T1_IDENTITY_FAILED", f"no BL operand: {first!r}")
    want = text_addr + off_record_mm
    if int(op.group(1), 16) != want:
        fail("T1_IDENTITY_FAILED",
             f"vmlinux BL operand {int(op.group(1), 16):#x} != "
             f"record_mmu_state {want:#x}")
    # Return the Image-relative target, i.e. the same coordinate space the
    # frozen payload decode and the derived offsets use. The absolute address
    # is only meaningful against text_addr.
    return off_record_mm


def gate_branch_patch(word: int, off_primary: int,
                      checkpoint_off: int) -> int:
    if (word >> 26) != 0b000101:
        fail("T1_BRANCH_FAILED", f"patched word {word:#010x} is not B")
    target = off_primary + pb.sx(word & 0x03FFFFFF, 26) * 4
    if target != checkpoint_off:
        fail("T1_BRANCH_FAILED",
             f"branch target {target:#x} != checkpoint {checkpoint_off:#x}")
    return target


def gate_branch_range(delta: int) -> None:
    if delta <= 0 or delta % 4:
        fail("T1_BRANCH_FAILED", f"delta {delta:#x}")
    if delta >= (1 << 27):
        fail("T1_BRANCH_FAILED",
             f"delta {delta:#x} outside AArch64 B +-128MiB range")


def gate_tramp_branch_target(frozen: bytes, off_primary: int) -> int:
    w = struct.unpack_from("<I", frozen, TRAMP_OFFSET + 0x20)[0]
    if (w >> 26) != 0b000101:
        fail("T1_IDENTITY_FAILED", f"trampoline word[8] not B: {w:#010x}")
    target = TRAMP_OFFSET + 0x20 + pb.sx(w & 0x03FFFFFF, 26) * 4
    if target != off_primary:
        fail("T1_IDENTITY_FAILED",
             f"frozen trampoline branch target {target:#x} != "
             f"re-derived primary_entry {off_primary:#x}")
    return target


def gate_image_size_rederived(image_size: int, label: str) -> None:
    """Section 11: the value must come from a real Image header and be sane —
    positive, 4-byte aligned, and its runtime footprint must not reach the
    RT-D trailer."""
    if image_size <= 0 or image_size & 3:
        fail("T1_GEOMETRY_FAILED", f"{label}: image_size {image_size:#x}")
    if image_size + S_RESIDUE > DTB_OFFSET:
        fail("T1_GEOMETRY_FAILED",
             f"{label}: image_size footprint {image_size:#x} reaches RT-D "
             f"at {DTB_OFFSET:#x}")


def gate_checkpoint_placement(ck: int, image_file_size: int, image_size: int,
                              plen: int, dtb_offset: int) -> None:
    """Sections 10/12: the checkpoint must sit in the deterministic padding
    AFTER the Linux image_size runtime footprint — not merely after the Image
    file — and stay clear of the RT-D trailer."""
    if ck % 4:
        fail("T1_CHECKPOINT_FAILED", f"checkpoint offset {ck:#x} unaligned")
    if not (0x40 <= plen <= 0x80):
        fail("T1_CHECKPOINT_FAILED", f"checkpoint size {plen}")
    if ck < image_file_size:
        fail("T1_CHECKPOINT_FAILED",
             f"checkpoint {ck:#x} inside the Image FILE (end "
             f"{image_file_size:#x})")
    if ck < image_size:
        fail("T1_CHECKPOINT_FAILED",
             f"checkpoint {ck:#x} inside the Linux image_size runtime "
             f"footprint (end {image_size:#x})")
    if ck + plen > dtb_offset:
        fail("T1_CHECKPOINT_FAILED",
             f"checkpoint end {ck + plen:#x} overlaps RT-D at {dtb_offset:#x}")


def gate_padding_zero(frozen: bytes, base: int, dtb_offset: int) -> int:
    """Section 12: every baseline byte from the placement base up to the RT-D
    trailer must be deterministic zero padding."""
    if base > dtb_offset:
        fail("T1_CHECKPOINT_FAILED", f"padding base {base:#x} past RT-D")
    pad = frozen[base:dtb_offset]
    nonzero = [base + i for i, b in enumerate(pad) if b]
    if nonzero:
        fail("T1_CHECKPOINT_FAILED",
             f"padding region [{base:#x},{dtb_offset:#x}) is not deterministic "
             f"zero at {[hex(o) for o in nonzero[:8]]} "
             f"({len(nonzero)} nonzero bytes)")
    return len(pad)


def gate_tramp_identity(cand: bytes) -> None:
    tramp = cand[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T1_IDENTITY_FAILED",
             f"embedded trampoline sha={sha(tramp)} != frozen FIX8 "
             f"(T1 must keep the real FIX8 trampoline branch intact)")


def gate_payload_diff(frozen: bytes, cand: bytes,
                      regions: list[tuple[int, int]]) -> list[int]:
    if len(cand) != len(frozen):
        fail("T1_PAYLOAD_DIFF_FAILED",
             f"size drift {len(cand)} != {len(frozen)}")
    diffs = [i for i in range(len(frozen)) if frozen[i] != cand[i]]
    bad = [i for i in diffs
           if not any(lo <= i < hi for lo, hi in regions)]
    if bad:
        fail("T1_PAYLOAD_DIFF_FAILED",
             f"diff outside allowed regions at {bad[:8]:#x}")
    for lo, hi in regions:
        if not any(lo <= i < hi for i in diffs):
            fail("T1_PAYLOAD_DIFF_FAILED",
                 f"allowed region [{lo:#x},{hi:#x}) has no diff (patch lost?)")
    return diffs


def gate_trailer(payload: bytes) -> bytes:
    hdr = pb.parse_image_hdr(payload, "t1-payload")
    dtb_offset, _gap = pb.calc_dtb_offset(hdr["image_size"])
    trailer = payload[dtb_offset:]
    if payload[dtb_offset:dtb_offset + 4] != struct.pack(">I", FDT_MAGIC):
        fail("T1_PAYLOAD_DIFF_FAILED", "no FDT magic at DTB_OFFSET")
    if sha(trailer) != RT_D_SHA or len(trailer) != RT_D_SIZE:
        fail("T1_PAYLOAD_DIFF_FAILED", f"trailer RT-D identity "
             f"sha={sha(trailer)} len={len(trailer)}")
    return trailer


def gate_geometry(payload: bytes, image_size: int) -> tuple[dict, int, int, int]:
    hdr = pb.parse_image_hdr(payload, "t1-payload")
    if hdr["image_size"] != image_size:
        fail("T1_GEOMETRY_FAILED",
             f"image_size {hdr['image_size']:#x} != authoritative "
             f"{image_size:#x}")
    dtb_offset, gap = pb.calc_dtb_offset(hdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("T1_GEOMETRY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T1_GEOMETRY_FAILED",
             f"payload len {len(payload)} != dtb_offset + RT_D")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T1_GEOMETRY_FAILED", "2MiB residue geometry")
    boot_est = pb.align(PAGE + len(payload), PAGE) + PAGE
    if boot_est != T1_BOOT_SIZE_EXPECTED:
        fail("T1_GEOMETRY_FAILED",
             f"boot_est {boot_est} != {T1_BOOT_SIZE_EXPECTED}")
    if BOOT_CAP - boot_est < 0x1000000:
        fail("T1_GEOMETRY_FAILED", "capacity margin < 16MiB")
    return hdr, dtb_offset, gap, boot_est


# ---------------------------------------------------------------------------
# Preregistered matched-control decoder (prompt sections 31-40).
# ---------------------------------------------------------------------------

def t1_minus_t0(t1_total_s: float) -> float:
    return t1_total_s - T0_REFERENCE_TOTAL_S


def t1_programmed_estimate(t1_total_s: float) -> float:
    return t1_total_s - P0_REF_OVERHEAD_S  # SECONDARY cross-check only


def t1_reachability(t1_total_s: float | None, recovery_kind: str) -> dict:
    """Primary: matched-control delta vs T0_TOTAL=14.252s; triple condition
    (window + T1_TOTAL<20s + AUTOMATIC_ANDROID_RETURN). A negative NEVER
    licenses T1_NOT_REACHED (T1_NOT_REACHED_LICENSE=NO); it routes to
    T1_FAILURE_ISOLATION_CI."""
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T1_STABLE_FASTBOOT",
                "r2": "NOT_PROVEN", "next": "T1_FAILURE_ISOLATION_CI",
                "reason": "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_T2_FORBIDDEN"}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T1_NO_RETURN",
                "r2": "NOT_PROVEN", "next": "T1_FAILURE_ISOLATION_CI",
                "reason": "CASE_F_NO_RETURN_MANUAL_ELAPSED_EXCLUDED"}
    if t1_total_s is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
                "r2": "NOT_PROVEN", "next": "T1_FAILURE_ISOLATION_CI",
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    delta = t1_minus_t0(t1_total_s)
    early = t1_total_s < T1_EARLY_RETURN_CLASS_LIMIT_S
    if early and abs(delta) <= T1_STRONG_HALF_WINDOW_S:
        return {"verdict": "STRONG", "case": "T1_A_STRONG",
                "r2": "PROVEN",
                "next": "MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI",
                "reason": "T0_MATCHED_CONTROL+EARLY_RETURN_CLASS+AUTOMATIC_RESET"}
    if early and abs(delta) <= T1_SUPPORTED_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED", "case": "T1_B_SUPPORTED",
                "r2": "STRONGLY_SUPPORTED",
                "next": "MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI",
                "reason": "T0_MATCHED_CONTROL+EARLY_RETURN_CLASS+AUTOMATIC_RESET"}
    if early:
        return {"verdict": "NOT_OBSERVED", "case": "T1_EARLY_RETURN_TIMING_MISMATCH",
                "r2": "NOT_PROVEN", "next": "T1_FAILURE_ISOLATION_CI",
                "reason": f"T1_MINUS_T0={delta:+.3f}s OUTSIDE_SUPPORTED_WINDOW"}
    lo, hi = T1_CASE_C_BAND_S
    if lo <= t1_total_s < hi:
        return {"verdict": "NOT_OBSERVED", "case": "T1_SIGNATURE_NOT_OBSERVED",
                "r2": "NOT_PROVEN", "next": "T1_FAILURE_ISOLATION_CI",
                "reason": "CASE_C_OLD_AUTO_RETURN_CLASS"}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
            "r2": "NOT_PROVEN", "next": "T1_FAILURE_ISOLATION_CI",
            "reason": f"T1_TOTAL={t1_total_s:.3f}s OUTSIDE_PREREGISTERED_BANDS"}


def run_decoder_fixtures() -> list[str]:
    lines = []

    def case(name, total, kind, want_verdict, want_case=None, want_r2=None,
             want_next=None):
        got = t1_reachability(total, kind)
        if got["verdict"] != want_verdict:
            fail("T1_DECODER_FIXTURE_FAILED",
                 f"{name}: verdict {got['verdict']} != {want_verdict}")
        if want_case and got["case"] != want_case:
            fail("T1_DECODER_FIXTURE_FAILED",
                 f"{name}: case {got['case']} != {want_case}")
        if want_r2 and got["r2"] != want_r2:
            fail("T1_DECODER_FIXTURE_FAILED",
                 f"{name}: r2 {got['r2']} != {want_r2}")
        if want_next and got["next"] != want_next:
            fail("T1_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"T1_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"case={got['case']} r2={got['r2']}")

    t2ci = "MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI"
    # Case A STRONG: T0-matched window.
    case("STRONG_14P2S", 14.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T1_A_STRONG", "PROVEN", t2ci)
    case("STRONG_13P3S", 13.3, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T1_A_STRONG", "PROVEN")
    case("STRONG_15P2S", 15.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T1_A_STRONG", "PROVEN")
    # Case B SUPPORTED.
    case("SUPPORTED_15P3S", 15.3, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T1_B_SUPPORTED", "STRONGLY_SUPPORTED", t2ci)
    case("SUPPORTED_16P2S", 16.2, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T1_B_SUPPORTED", "STRONGLY_SUPPORTED")
    case("SUPPORTED_12P3S", 12.3, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T1_B_SUPPORTED", "STRONGLY_SUPPORTED")
    # Case D: early return but outside the matched-control window.
    case("EARLY_MISMATCH_16P4S", 16.4, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T1_EARLY_RETURN_TIMING_MISMATCH", "NOT_PROVEN",
         "T1_FAILURE_ISOLATION_CI")
    case("EARLY_MISMATCH_11P0S", 11.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T1_EARLY_RETURN_TIMING_MISMATCH", "NOT_PROVEN")
    # Case C: old auto-return class (~23-26s); T0 proven means the focus
    # narrows to trampoline-end -> primary_entry, but never T1_NOT_REACHED.
    case("CASE_C_FIX8_CLASS_23P852S", FIX8_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T1_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN", "T1_FAILURE_ISOLATION_CI")
    case("CASE_C_PANIC30_CLASS_26P289S", PANIC30_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T1_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN")
    case("CASE_C_BAND_EDGE_20P0S", 20.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T1_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN")
    # Cases E/F: non-Android returns.
    case("CASE_E_STABLE_FASTBOOT", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "T1_STABLE_FASTBOOT", "NOT_PROVEN",
         "T1_FAILURE_ISOLATION_CI")
    case("CASE_F_NO_RETURN", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "T1_NO_RETURN", "NOT_PROVEN",
         "T1_FAILURE_ISOLATION_CI")
    case("UNKNOWN_KIND", 14.2, "UNKNOWN", "NOT_OBSERVED", "UNKNOWN",
         "NOT_PROVEN")
    est = t1_programmed_estimate(T0_REFERENCE_TOTAL_S)
    if abs(est - (T0_REFERENCE_TOTAL_S - P0_REF_OVERHEAD_S)) > 1e-9:
        fail("T1_DECODER_FIXTURE_FAILED", "estimate arithmetic")
    lines.append(f"T1_DECODER_REFERENCE est(T0 {T0_REFERENCE_TOTAL_S}s)="
                 f"{est:.4f}s (SECONDARY cross-check only; expected ~8s)")
    lines.append("T1_DECODER_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# Negative fixtures (prompt section 29) against the real gate functions.
# ---------------------------------------------------------------------------

def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("T1_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"T1_NEGATIVE_{name}_REJECTED=PASS"
    fail("T1_NEGATIVE_FIXTURE_FAILED", f"{name}: ACCEPTED (must reject)")


def run_negative_fixtures(ops: str, dump: str, probe_len: int, frozen: bytes,
                          cand: bytes, off_primary: int, off_record_mm: int,
                          checkpoint_off: int, image_file_size: int,
                          image_size: int, padding_base: int,
                          original_word: int, branch_word: int) -> list[str]:
    lines: list[str] = []
    regions = [(off_primary, off_primary + 4),
               (checkpoint_off, checkpoint_off + probe_len)]
    ops_lines = ops.splitlines()

    def dump_insert_after(anchor_mnem: str, extra: list[str]) -> str:
        out = []
        for ln in dump.splitlines():
            out.append(ln)
            m = INSTR_RE.match(ln)
            if m and m.group(2) == anchor_mnem:
                out.extend(extra)
        return "\n".join(out) + "\n"

    # 1. wrong primary_entry offset (not the trampoline-branch target).
    lines.append(expect_reject(
        "WRONG_PRIMARY_ENTRY_OFFSET",
        lambda: gate_tramp_branch_target(frozen, off_primary + 4),
        "T1_IDENTITY_FAILED"))
    # 2. wrong original instruction (NOP instead of bl record_mmu_state).
    lines.append(expect_reject(
        "WRONG_ORIGINAL_INSTRUCTION",
        lambda: gate_original_insn(0xD503201F, off_primary, off_record_mm),
        "T1_IDENTITY_FAILED"))
    # 3. trampoline modified.
    bad_tramp = bytearray(cand)
    bad_tramp[TRAMP_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "TRAMPOLINE_MODIFIED",
        lambda: gate_tramp_identity(bytes(bad_tramp)), "T1_IDENTITY_FAILED"))
    # 4. checkpoint overlaps the Image file.
    lines.append(expect_reject(
        "CHECKPOINT_OVERLAPS_IMAGE",
        lambda: gate_checkpoint_placement(
            image_file_size - 0x100, image_file_size, image_size, probe_len,
            DTB_OFFSET),
        "T1_CHECKPOINT_FAILED"))
    # 4b. checkpoint clear of the Image file but INSIDE the image_size runtime
    # footprint (the defect the previous prototype had).
    inside_footprint = ((image_file_size + image_size) // 2) & ~3
    lines.append(expect_reject(
        "CHECKPOINT_INSIDE_IMAGE_SIZE",
        lambda: gate_checkpoint_placement(
            inside_footprint, image_file_size, image_size, probe_len,
            DTB_OFFSET),
        "T1_CHECKPOINT_FAILED"))
    # 4c. checkpoint region is not deterministic zero padding.
    nonzero_pad = bytearray(frozen)
    nonzero_pad[padding_base + 4] = 0xAB
    lines.append(expect_reject(
        "CHECKPOINT_BASELINE_NONZERO",
        lambda: gate_padding_zero(bytes(nonzero_pad), padding_base, DTB_OFFSET),
        "T1_CHECKPOINT_FAILED"))
    # 5. checkpoint overlaps the RT-D trailer.
    lines.append(expect_reject(
        "CHECKPOINT_OVERLAPS_RT_D",
        lambda: gate_checkpoint_placement(
            DTB_OFFSET - probe_len + 4, image_file_size, image_size, probe_len,
            DTB_OFFSET),
        "T1_CHECKPOINT_FAILED"))
    # 6. wrong branch target.
    lines.append(expect_reject(
        "WRONG_BRANCH_TARGET",
        lambda: gate_branch_patch(0x14000000 | (((checkpoint_off - off_primary)
                                                 // 4 + 1) & 0x03FFFFFF),
                                  off_primary, checkpoint_off),
        "T1_BRANCH_FAILED"))
    # 7. branch out of range.
    lines.append(expect_reject(
        "BRANCH_OUT_OF_RANGE",
        lambda: gate_branch_range(1 << 27), "T1_BRANCH_FAILED"))
    # 8. wrong delay constant.
    v8 = re.sub(r"x10, #(?:0x)?8\b", "x10, #24", ops)
    lines.append(expect_reject(
        "WRONG_DELAY", lambda: gate_t1_probe(v8, dump, probe_len),
        "T1_DISASM_FAILED"))
    # 9. wrong PSCI FID high half.
    v9 = FID_HIGH_RE.sub("movk w0, #0x8401, lsl #16", ops)
    lines.append(expect_reject(
        "WRONG_PSCI_FID", lambda: gate_t1_probe(v9, dump, probe_len),
        "T1_DISASM_FAILED"))
    # 10. missing smc.
    v10 = "\n".join(ln for ln in ops_lines
                    if not re.search(r"smc #(0x)?0\b", ln)) + "\n"
    lines.append(expect_reject(
        "MISSING_SMC", lambda: gate_t1_probe(v10, dump, probe_len),
        "T1_DISASM_FAILED"))
    # 11. fall-through after smc return.
    lines.append(expect_reject(
        "FALLTHROUGH_AFTER_SMC",
        lambda: gate_terminal(dump_insert_after(
            "smc", ["  50: 00000000 mov x0, x15",
                    "  54: 14000000 b 0x50"])),
        "T1_DISASM_FAILED"))
    # 12/13/14. stack / memory store / x0 dereference / relocations.
    lines.append(expect_reject(
        "STACK_USE", lambda: gate_no_forbidden(
            ops + "\n00000000 stp x29, x30, [sp, #-32]!"),
        "T1_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_STORE", lambda: gate_no_forbidden(
            ops + "\n00000000 str x9, [x0]"), "T1_DISASM_FAILED"))
    lines.append(expect_reject(
        "X0_DEREFERENCE", lambda: gate_no_forbidden(
            ops + "\n00000000 ldr x9, [x0]"), "T1_DISASM_FAILED"))
    lines.append(expect_reject(
        "RELOCATIONS", lambda: gate_no_relocations(
            "0000000000000000 R_AARCH64_ABS64 .text", "fixture"),
        "T1_RELOC_FAILED"))
    # 15. payload size change.
    lines.append(expect_reject(
        "PAYLOAD_SIZE_CHANGE",
        lambda: gate_payload_diff(frozen, cand + b"\x00" * 4, regions),
        "T1_PAYLOAD_DIFF_FAILED"))
    # 16. RT-D change.
    bad_rtd = bytearray(cand)
    bad_rtd[DTB_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "RT_D_CHANGED", lambda: gate_trailer(bytes(bad_rtd)),
        "T1_PAYLOAD_DIFF_FAILED"))
    # 17. extra payload diff outside the two allowed regions.
    bad_diff = bytearray(cand)
    bad_diff[0x200] ^= 0xFF
    lines.append(expect_reject(
        "EXTRA_PAYLOAD_DIFF",
        lambda: gate_payload_diff(frozen, bytes(bad_diff), regions),
        "T1_PAYLOAD_DIFF_FAILED"))
    lines.append(f"T1_NEGATIVE_FIXTURE_COUNT={len(lines)}")
    lines.append("T1_NEGATIVE_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# T1 checkpoint build + payload composition.
# ---------------------------------------------------------------------------

def checkpoint_syms(readelf: str, elf: Path) -> dict[str, int]:
    out = pb.run([readelf, "-sW", str(elf)])
    found: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[7] == "r3_t1_checkpoint":
            found[parts[7]] = int(parts[1], 16)
    return found


def build_t1_checkpoint(out: Path, tools: dict) -> tuple[bytes, str, str]:
    elf = out / "p1b-t1-checkpoint.elf"
    ops = iso.assemble_probe(T1_DEVICE_S, T1_DEVICE_LD,
                             [f"-DP1B_T1_DELAY={T1_DELAY_S}"], elf, tools)
    offs = checkpoint_syms(tools["readelf"], elf)
    if set(offs) != {"r3_t1_checkpoint"} or offs["r3_t1_checkpoint"] != 0:
        fail("T1_BUILD_FAILED", f"symbols {sorted(offs)}")
    binp = out / "p1b-t1-checkpoint.bin"
    pb.run([tools["objcopy"], "-O", "binary", str(elf), str(binp)])
    probe = binp.read_bytes()
    if not (0x40 <= len(probe) <= 0x80):
        fail("T1_BUILD_FAILED", f"checkpoint size {len(probe)}")
    dump = pb.run([tools["objdump"], "-d", str(elf)])
    (out / "p1b-t1-checkpoint-disasm.txt").write_text(dump)
    gate_t1_probe(ops, dump, len(probe))
    rel = pb.run([tools["readelf"], "-r", "--wide", str(elf)])
    gate_no_relocations(rel, "t1-checkpoint")
    print(f"T1_CHECKPOINT sha256={sha(probe)} size={len(probe)}")
    return probe, ops, dump


def inst_record(out: Path, tools: dict, words: list[int],
                name: str) -> tuple[str, str]:
    """Literal-.inst-word ELF disassembly record (the proven encoding path)."""
    wrap = out / f"{name}.S"
    wrap.write_text(
        ".section .text, \"ax\", @progbits\n"
        ".globl r3_handoff_entry\n"
        "r3_handoff_entry:\n"
        + "".join(f".inst\t{w:#010x}\n" for w in words))
    elf = out / f"{name}.elf"
    ops = iso.assemble_probe(wrap, HERE / "p1b-trampoline.ld", [], elf, tools)
    dump = pb.run([tools["objdump"], "-d", str(elf)])
    (out / f"{name}-disasm.txt").write_text(dump)
    return ops, dump


def sysmap_symbol(sysmap: Path, name: str) -> int:
    hits = [l for l in sysmap.read_text().splitlines()
            if l.endswith(f" {name}")]
    if not hits:
        fail("T1_IDENTITY_FAILED", f"System.map missing {name}")
    return int(hits[0].split()[0], 16)


def nm_symbol(nm_out: str, name: str) -> int:
    hits = [l for l in nm_out.splitlines() if l.endswith(f" {name}")]
    if not hits:
        fail("T1_IDENTITY_FAILED", f"vmlinux nm missing {name}")
    return int(hits[0].split()[0], 16)


def cmd_t1(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)

    # --- frozen baseline identity (exact FIXED INIT8; no kernel rebuild for
    # the payload itself) ---
    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("T1_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA:
        fail("T1_IDENTITY_FAILED", f"frozen FIX8 payload sha={sha(frozen)}")
    if len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("T1_IDENTITY_FAILED",
             f"frozen FIX8 payload len {len(frozen)} != {FIX8_PAYLOAD_SIZE}")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("T1_IDENTITY_FAILED", "frozen code1 not b 0x40")
    # Section 11: re-read image_size from the authoritative FIX8 Image header;
    # never inherit a history/doc constant.
    image_size = fhdr["image_size"]
    gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T1_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(frozen) - RT_D_SIZE != dtb_offset:
        fail("T1_IDENTITY_FAILED", "payload layout: len - RT_D_SIZE != dtb_offset")
    gate_tramp_identity(frozen)
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE} "
          "(frozen reference; re-derived from the rebuilt Image length below "
          "and required to match)")
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x} ({image_size})")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES "
          f"(read from the authoritative FIX8 Image header, payload sha "
          f"{FIX8_PAYLOAD_SHA})")
    print("IMAGE_HEADER_IMAGE_SIZE_HISTORICAL_READINGS_IGNORED="
          + ",".join(f"{v:#x}" for v in FIX8_IMAGE_SIZE_HISTORY_READINGS))
    print("T1_FROZEN_FIX8_BASE=PASS sha=" + FIX8_PAYLOAD_SHA)
    print("T1_FROZEN_TRAMPOLINE_EMBEDDED=YES sha=" + TRAMP_SHA)

    # --- authoritative kernel rebuild (vmlinux + System.map identity) ---
    init = pb.compile_init(out, T1_DELAY_S, args.gcc, args.strip)
    init_sha = sha(init.read_bytes())
    if init_sha != FIX8_INIT_SHA:
        fail("T1_IDENTITY_FAILED", f"/init sha {init_sha} != frozen FIX8")
    cpio = out / f"initramfs-{T1_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    cpio_sha = sha(cpio.read_bytes())
    if cpio_sha != FIX8_CPIO_SHA:
        fail("T1_IDENTITY_FAILED", f"cpio sha {cpio_sha} != frozen FIX8")
    print(f"T1_INIT_IDENTICAL=YES sha={init_sha}")
    print(f"T1_INITRAMFS_IDENTICAL=YES sha={cpio_sha}")

    k = pb.make_kernel(out, T1_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("T1_BUILD_FAILED",
             f"rebuilt image_size {kg['hdr']['image_size']:#x} != "
             f"authoritative frozen payload header {image_size:#x} "
             "(baseline drift)")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("T1_BUILD_FAILED",
             f"rebuilt image file size {image_file_size} != frozen "
             f"{FIX8_IMAGE_FILE_SIZE}")
    # The rebuild exists to re-derive symbols/offsets and to confirm the
    # original instruction from a real disassembly; the device executes the
    # FROZEN payload, never the rebuild. Byte-level identity of a rebuilt Image
    # is therefore NOT gated (the embedded build banner and other build-stamp
    # dependent regions legitimately differ). The identities that ARE gated are
    # semantic and are checked below: header geometry, offset agreement across
    # llvm-nm / System.map / kernel_gate, and the disassembled first instruction
    # at primary_entry. The byte statistics are reported for the record.
    census = sum(1 for a, b in zip(image, frozen) if a != b)
    print(f"T1_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size} "
          f"image_size={image_size:#x} image_sha={sha(image)}")
    print("T1_REBUILT_IMAGE_BYTE_IDENTICAL=NO "
          "(reported, NOT gated: the device executes the FROZEN payload; "
          "semantic identities are gated instead. "
          f"frozen FIX8 Image reference {FIX8_IMAGE_SHA})")
    print(f"T1_REBUILT_IMAGE_DIFF_BYTES={census} "
          "(informational census vs the frozen payload Image prefix)")

    # --- primary_entry re-derivation (never a history constant) ---
    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = nm_symbol(nm_out, "_text")
    off_primary_nm = nm_symbol(nm_out, "primary_entry") - text_addr
    off_record_mm_nm = nm_symbol(nm_out, "record_mmu_state") - text_addr
    pe_sm = sysmap_symbol(k["sysmap"], "primary_entry")
    tx_sm = sysmap_symbol(k["sysmap"], "_text")
    rm_sm = sysmap_symbol(k["sysmap"], "record_mmu_state")
    off_primary_sm = pe_sm - tx_sm
    off_record_mm_sm = rm_sm - tx_sm
    if off_primary_sm != off_primary_nm:
        fail("T1_IDENTITY_FAILED",
             f"primary_entry nm {off_primary_nm:#x} != System.map "
             f"{off_primary_sm:#x}")
    if off_record_mm_sm != off_record_mm_nm:
        fail("T1_IDENTITY_FAILED",
             f"record_mmu_state nm {off_record_mm_nm:#x} != System.map "
             f"{off_record_mm_sm:#x}")
    off_primary = off_primary_nm
    if off_primary != kg["off_primary"]:
        fail("T1_IDENTITY_FAILED",
             f"primary_entry nm {off_primary:#x} != kernel_gate "
             f"{kg['off_primary']:#x}")
    head = (LINUX / "arch" / "arm64" / "kernel" / "head.S").read_text()
    prim_body = head.split("SYM_CODE_START(primary_entry)", 1)[1]
    first_insn = next(l for l in prim_body.splitlines() if l.startswith("\t"))
    if re.sub(r"\s+", " ", first_insn.strip()) != "bl record_mmu_state":
        fail("T1_IDENTITY_FAILED",
             f"head.S first primary_entry instruction not "
             f"bl record_mmu_state: {first_insn!r}")
    print(f"PRIMARY_ENTRY_OFFSET={off_primary:#x}")
    print("T1_PRIMARY_ENTRY_OFFSET_REDERIVED=YES "
          "(vmlinux nm + System.map + head.S + kernel_gate, this round)")

    # --- frozen trampoline branch algebra must agree with the derivation ---
    tramp_target = gate_tramp_branch_target(frozen, off_primary)
    print(f"T1_TRAMPOLINE_BRANCH_TARGET={tramp_target:#x} == primary_entry")

    # --- section 27: show the frozen FIX8 trampoline verbatim (unchanged).
    # The literal-word record is linked at 0, so its branch operand is the
    # frozen target shifted down by the trampoline's payload offset.
    tramp_bytes = frozen[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp_bytes) != TRAMP_SHA:
        fail("T1_IDENTITY_FAILED", "frozen trampoline slice sha")
    (out / "p1b-t1-frozen-fix8-trampoline.bin").write_bytes(tramp_bytes)
    tramp_ops, _tramp_dump = inst_record(
        out, tools, list(struct.unpack(f"<{TRAMP_SIZE // 4}I", tramp_bytes)),
        "p1b-t1-frozen-fix8-trampoline")
    m = re.search(r"\bb\s+(?:0x)?([0-9a-f]+)", tramp_ops)
    if not m or int(m.group(1), 16) != off_primary - TRAMP_OFFSET:
        fail("T1_IDENTITY_FAILED",
             f"frozen trampoline record branch operand {tramp_ops!r} != "
             f"{off_primary - TRAMP_OFFSET:#x} (primary_entry - TRAMP_OFFSET)")
    print("T1_TRAMPOLINE_UNCHANGED_RECORD=YES "
          f"(48 bytes, sha {TRAMP_SHA}, still branches to primary_entry)")

    # --- original first instruction (frozen bytes at the derived offset) ---
    original_word = struct.unpack_from("<I", frozen, off_primary)[0]
    insn_target = gate_original_insn(original_word, off_primary,
                                     off_record_mm_nm)
    insn_ops, _ = inst_record(out, tools, [original_word],
                              "p1b-t1-original-insn-record")
    if "bl" not in insn_ops:
        fail("T1_IDENTITY_FAILED",
             f"original instruction record did not disassemble as BL: "
             f"{insn_ops!r}")
    print("PRIMARY_ENTRY_ORIGINAL_INSN=bl record_mmu_state")
    print(f"PRIMARY_ENTRY_ORIGINAL_BYTES={struct.pack('<I', original_word).hex()}")
    print(f"PRIMARY_ENTRY_ORIGINAL_TARGET={insn_target:#x} (record_mmu_state)")

    # Section 7: the authoritative vmlinux disassembly of the SAME address must
    # agree with the frozen payload bytes and with head.S.
    pe_dump_path = out / "p1b-t1-primary-entry-vmlinux-disasm.txt"
    pe_dump = pb.run([
        tools["objdump"], "-d",
        f"--start-address={text_addr + off_primary:#x}",
        f"--stop-address={text_addr + off_primary + 16:#x}",
        str(k["vmlinux"])])
    pe_dump_path.write_text(pe_dump)
    disasm_target = gate_vmlinux_original_insn(
        pe_dump, off_primary, off_record_mm_nm, text_addr)
    if disasm_target != insn_target:
        fail("T1_IDENTITY_FAILED",
             f"vmlinux BL target {disasm_target:#x} (Image-relative) != "
             f"frozen payload BL target {insn_target:#x} (Image-relative)")
    print("PRIMARY_ENTRY_ORIGINAL_INSN_SOURCES_AGREE=YES "
          "(head.S + frozen payload bytes + vmlinux disassembly)")

    # Byte-level diff census of the rebuild vs the frozen payload, split around
    # the patched address. Reported for the record; the semantic identities
    # (offsets + disassembled instruction) are what is gated.
    first_diff = next(i for i, (a, b) in enumerate(zip(image, frozen))
                      if a != b)
    diffs_before = sum(1 for i in range(off_primary) if image[i] != frozen[i])
    diffs_from = sum(1 for i in range(off_primary, len(image))
                     if image[i] != frozen[i])
    insn_identical = (image[off_primary:off_primary + 16]
                      == frozen[off_primary:off_primary + 16])
    print("T1_REBUILT_IMAGE_CODE_IDENTITY_AT_PRIMARY_ENTRY="
          f"{'YES' if insn_identical else 'NO'} (16 bytes, informational)")
    print(f"T1_REBUILT_IMAGE_FIRST_DIFF_OFFSET={first_diff:#x} "
          f"DIFF_BEFORE_PRIMARY_ENTRY={diffs_before} "
          f"DIFF_FROM_PRIMARY_ENTRY={diffs_from} (informational)")

    # --- checkpoint placement from the padding map (re-selected this round) ---
    probe, probe_ops, probe_dump = build_t1_checkpoint(out, tools)
    plen = len(probe)
    # Section 10: the checkpoint goes after BOTH the Image file and the Linux
    # image_size runtime footprint, in the deterministic zero padding before
    # the RT-D trailer. There is no file_size-only fallback: if the geometry
    # cannot satisfy this, the build STOPS with the reason below.
    padding_base = max(image_file_size, image_size)
    checkpoint_off = (padding_base + 3) & ~3
    if checkpoint_off + plen > dtb_offset:
        fail("T1_CHECKPOINT_FAILED",
             f"geometry: no deterministic zero-padding region outside the "
             f"image_size footprint {image_size:#x} and before RT-D "
             f"{dtb_offset:#x} can hold a {plen}-byte checkpoint "
             f"(base {checkpoint_off:#x}); file_size-only placement is NOT "
             "an allowed fallback")
    gate_checkpoint_placement(checkpoint_off, image_file_size, image_size,
                              plen, dtb_offset)
    padding_len = gate_padding_zero(frozen, padding_base, dtb_offset)
    print(f"T1_CHECKPOINT_OFFSET={checkpoint_off:#x} size={plen} "
          f"(base max(IMAGE_FILE_SIZE {image_file_size:#x}, "
          f"IMAGE_HEADER_IMAGE_SIZE {image_size:#x}))")
    print(f"T1_CHECKPOINT_OUTSIDE_IMAGE_FILE=YES (>= {image_file_size:#x})")
    print(f"T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES (>= {image_size:#x})")
    print(f"T1_CHECKPOINT_BEFORE_RTD=YES "
          f"(end {checkpoint_off + plen:#x} <= {dtb_offset:#x})")
    print(f"T1_CHECKPOINT_PADDING_ZERO=YES "
          f"([{padding_base:#x},{dtb_offset:#x}) all zero, {padding_len} bytes)")
    print("T1_CHECKPOINT_PADDING_REGION_SAFE=YES")

    # --- branch encoding + range ---
    delta = checkpoint_off - off_primary
    gate_branch_range(delta)
    branch_word = 0x14000000 | ((delta // 4) & 0x03FFFFFF)
    gate_branch_patch(branch_word, off_primary, checkpoint_off)
    patch_ops, _ = inst_record(out, tools, [branch_word],
                               "p1b-t1-branch-patch-record")
    m = re.search(r"\bb\s+(?:0x)?([0-9a-f]+)", patch_ops)
    if not m or int(m.group(1), 16) != delta:
        fail("T1_BRANCH_FAILED",
             f"branch record did not disassemble to {delta:#x}: {patch_ops!r}")
    print(f"T1_BRANCH_DISTANCE={delta:#x} (+{delta} bytes)")
    print("T1_BRANCH_IN_RANGE=YES (AArch64 B +-128MiB)")

    # --- compose the T1 payload from the frozen FIX8 bytes ---
    cand = bytearray(frozen)
    cand[off_primary:off_primary + 4] = struct.pack("<I", branch_word)
    cand[checkpoint_off:checkpoint_off + plen] = probe
    cand = bytes(cand)
    regions = [(off_primary, off_primary + 4),
               (checkpoint_off, checkpoint_off + plen)]
    diffs = gate_payload_diff(frozen, cand, regions)
    gate_tramp_identity(cand)
    trailer = gate_trailer(cand)
    if trailer != frozen_rt_d:
        fail("T1_PAYLOAD_DIFF_FAILED", "trailer drifted vs frozen RT-D")
    hdr, dtb_off2, gap2, boot_est = gate_geometry(cand, image_size)
    if dtb_off2 != dtb_offset:
        fail("T1_PAYLOAD_DIFF_FAILED", "dtb_offset drifted")
    payload_path = out / "thyme-r3-p1b-t1-kernel-payload.bin"
    payload_path.write_bytes(cand)
    diff_bytes_a = sum(1 for i in diffs if off_primary <= i < off_primary + 4)
    diff_bytes_b = sum(1 for i in diffs
                       if checkpoint_off <= i < checkpoint_off + plen)
    diff_report = (
        "T1_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"T1_PAYLOAD_SHA256={sha(cand)}\n"
        f"REGION_A=[{off_primary:#x},{off_primary + 4:#x}) "
        f"primary_entry first instruction bl record_mmu_state -> "
        f"b T1_CHECKPOINT ({diff_bytes_a} diff bytes)\n"
        f"REGION_B=[{checkpoint_off:#x},{checkpoint_off + plen:#x}) "
        f"T1 checkpoint in deterministic zero padding "
        f"({diff_bytes_b} diff bytes)\n"
        f"DIFF_BYTES={len(diffs)} (A={diff_bytes_a} B={diff_bytes_b})\n"
        f"T1_DIFF_BYTE_COUNT={len(diffs)}\n"
        f"FIRST_DIFF={diffs[0]:#x} LAST_DIFF={diffs[-1]:#x}\n"
        f"DIFF_RANGES=[{', '.join(f'[{lo:#x},{hi:#x})' for lo, hi in regions)}]\n"
        f"T1_DIFF_RANGES=[{', '.join(f'[{lo:#x},{hi:#x})' for lo, hi in regions)}]\n"
        f"DIFF_ATTRIBUTION=PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY\n"
        f"T1_PAYLOAD_DIFF_ATTRIBUTED="
        f"PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY\n"
        f"T1_TRAMPOLINE_IDENTICAL_TO_FIX8=YES sha={TRAMP_SHA}\n"
        f"RT_D_TRAILER_IDENTICAL=YES sha={RT_D_SHA}\n"
        f"PAYLOAD_SIZE_IDENTICAL=YES {len(cand)}\n"
        f"DTB_OFFSET={dtb_offset:#x} GAP={gap:#x} "
        f"IMAGE_FILE_SIZE={image_file_size} "
        f"IMAGE_HEADER_IMAGE_SIZE={hdr['image_size']:#x} "
        f"T1_CHECKPOINT_OFFSET={checkpoint_off:#x} "
        f"T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES BOOT_SIZE_EST={boot_est}\n"
        "T1_RUNTIME_SEMANTIC_DELTA=PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY\n")
    (out / "p1b-t1-payload-diff-report.txt").write_text(diff_report)
    print(f"T1_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)} A={diff_bytes_a} B={diff_bytes_b}")
    print(f"T1_DIFF_BYTE_COUNT={len(diffs)} "
          f"T1_DIFF_RANGES=[{', '.join(f'[{lo:#x},{hi:#x})' for lo, hi in regions)}]")
    print("T1_PAYLOAD_DIFF_ATTRIBUTED="
          "PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY")

    # --- supporting records (explainability) ---
    sm_lines = [l for l in k["sysmap"].read_text().splitlines()
                if l.endswith((" primary_entry", " _text",
                               " record_mmu_state",
                               " __primary_switched"))]
    (out / "p1b-t1-sysmap-excerpt.txt").write_text("\n".join(sm_lines) + "\n")

    # --- fixtures ---
    neg_lines = run_negative_fixtures(
        probe_ops, probe_dump, plen, frozen, cand, off_primary,
        off_record_mm_nm, checkpoint_off, image_file_size, image_size,
        padding_base, original_word, branch_word)
    (out / "p1b-t1-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures()
    (out / "p1b-t1-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")

    # --- report + manifest + gates ---
    report = (
        "T1_PREDEVICE_REPORT\n"
        f"T1_ENTRY=r3_t1_checkpoint at payload offset {checkpoint_off:#x}\n"
        "T1_REACH_PATH=ABL -> code1 b 0x40 -> UNMODIFIED FIX8 trampoline "
        "(sha " + TRAMP_SHA + ", branch word[8] intact) -> primary_entry -> "
        "b T1_CHECKPOINT (replaces bl record_mmu_state)\n"
        f"T1_PRIMARY_ENTRY_OFFSET={off_primary:#x} REDERIVED=YES\n"
        "T1_PRIMARY_ENTRY_ORIGINAL_INSN=bl record_mmu_state\n"
        f"T1_PRIMARY_ENTRY_ORIGINAL_TARGET={insn_target:#x}\n"
        f"T1_CHECKPOINT_OFFSET={checkpoint_off:#x} "
        f"(>= Image file end {image_file_size:#x}, end "
        f"{checkpoint_off + plen:#x} <= DTB_OFFSET {dtb_offset:#x}, "
        "deterministic zero padding)\n"
        f"T1_DEVICE_CANDIDATE_DELAY={T1_DELAY_S}s\n"
        "T1_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY (T0-proven instruction "
        "sequence; no stack/memory/timer subsystem/MMIO)\n"
        f"T1_RESET_PRIMITIVE=PSCI_SYSTEM_RESET fid=0x{PSCI_SYSTEM_RESET_FID:08x} "
        "smc #0\n"
        "T1_FAIL_CLOSED=YES (any smc return -> wfe forever; no return to "
        "primary_entry, no record_mmu_state compensation, no normal Linux)\n"
        f"T1_CLOBBER_REGISTERS={T1_CLOBBER_REGISTERS} (x1/x2/x3 never "
        "written; x0/w0 written only by the PSCI FID pair; no x0 dereference)\n"
        "T1_POSITION_INDEPENDENT=YES (PC-relative branches only, no absolute "
        "S, no load address, no loads/stores)\n"
        "T1_RUNTIME_RELOCATIONS=0\n"
        "T1_RUNTIME_SEMANTIC_DELTA=PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY\n"
        f"T1_TRAMPOLINE_IDENTICAL_TO_FIX8=YES sha={TRAMP_SHA}\n"
        f"T1_RT_D_IDENTITY=YES sha={RT_D_SHA}\n"
        f"T1_INITRAMFS_IDENTITY=YES /init {FIX8_INIT_SHA} cpio {FIX8_CPIO_SHA}\n"
        "T1_DIAGNOSTIC_ONLY=YES\n"
        "T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO\n"
        "T2_STATUS=DESIGNED (MMU-on environment audit still required; not "
        "upgraded this round)\n")
    (out / "p1b-t1-report.txt").write_text(report)

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "fix8_payload_sha256": FIX8_PAYLOAD_SHA,
        "fix8_payload_size": FIX8_PAYLOAD_SIZE,
        "fix8_image_sha256": FIX8_IMAGE_SHA,
        "fix8_image_file_size": FIX8_IMAGE_FILE_SIZE,
        "fix8_init_sha256": FIX8_INIT_SHA,
        "fix8_cpio_sha256": FIX8_CPIO_SHA,
        "fix8_tramp_sha256": TRAMP_SHA,
        "fix8_boot_sha256": FORBIDDEN_BOOT_SHAS["FIX8_BOOT"],
        "t0_boot_sha256": FORBIDDEN_BOOT_SHAS["T0_BOOT"],
        "panic30_boot_sha256": FORBIDDEN_BOOT_SHAS["PANIC30_BOOT"],
        "rt_d_frozen_sha256": RT_D_SHA,
        "rt_d_frozen_size": RT_D_SIZE,
        "t1_primary_entry_offset": hex(off_primary),
        "t1_primary_entry_offset_rederived": True,
        "t1_primary_entry_original_insn": "bl record_mmu_state",
        "t1_primary_entry_original_bytes":
            struct.pack("<I", original_word).hex(),
        "t1_primary_entry_original_target": hex(insn_target),
        "t1_record_mmu_state_offset": hex(off_record_mm_nm),
        "t1_primary_entry_original_insn_sources_agree": True,
        "rebuilt_image_sha256": sha(image),
        "rebuilt_image_byte_identical_to_frozen": False,
        "rebuilt_image_byte_identity_reason":
            "embedded build banner (UTS_VERSION/linux_banner) differs and "
            "shifts later bytes; the device executes the frozen payload",
        "rebuilt_image_diff_bytes_vs_frozen_prefix": census,
        "rebuilt_image_first_diff_offset": hex(first_diff),
        "rebuilt_image_diff_bytes_before_primary_entry": diffs_before,
        "rebuilt_image_diff_bytes_from_primary_entry": diffs_from,
        "rebuilt_image_code_identity_at_primary_entry": insn_identical,
        "image_header_image_size": hex(image_size),
        "image_header_image_size_rederived": True,
        "image_size_historical_readings_ignored":
            [hex(v) for v in FIX8_IMAGE_SIZE_HISTORY_READINGS],
        "t1_checkpoint_offset": hex(checkpoint_off),
        "t1_checkpoint_size": plen,
        "t1_checkpoint_sha256": sha(probe),
        "t1_checkpoint_outside_image_size": True,
        "t1_checkpoint_outside_image_file": True,
        "t1_checkpoint_before_rtd": True,
        "t1_checkpoint_padding_zero": True,
        "t1_padding_region": [hex(padding_base), hex(dtb_offset)],
        "t1_padding_region_zero_bytes": padding_len,
        "t1_branch_distance": delta,
        "t1_branch_in_range": True,
        "t1_payload_sha256": sha(cand),
        "t1_payload_size": len(cand),
        "t1_boot_size_est": boot_est,
        "t1_boot_kernel_size_field": len(cand),
        "dtb_offset": hex(dtb_offset),
        "gap": hex(gap),
        "image_size": hex(hdr["image_size"]),
        "image_file_size": image_file_size,
        "diff_bytes": len(diffs),
        "diff_bytes_region_a": diff_bytes_a,
        "diff_bytes_region_b": diff_bytes_b,
        "diff_regions": [[hex(lo), hex(hi)] for lo, hi in regions],
        "diff_attribution":
            "PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY",
        "t1_delay_seconds": T1_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "t1_clobber_registers": T1_CLOBBER_REGISTERS,
        "t1_fail_closed": True,
        "t1_runtime_relocations": 0,
        "t1_runtime_semantic_delta":
            "PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY",
        "t1_tramp_identical_to_fix8": True,
        "t1_rtd_identical": True,
        "t1_diagnostic_only": True,
        "t1_normal_kernel_boot_candidate": False,
        "decoder": {
            "kind": "T0_MATCHED_CONTROL_PRIMARY_P0_SECONDARY",
            "t0_reference_total_s": T0_REFERENCE_TOTAL_S,
            "strong_half_window_s": T1_STRONG_HALF_WINDOW_S,
            "supported_half_window_s": T1_SUPPORTED_HALF_WINDOW_S,
            "early_return_class_limit_s": T1_EARLY_RETURN_CLASS_LIMIT_S,
            "case_c_band_s": list(T1_CASE_C_BAND_S),
            "p0_ref_overhead_s": P0_REF_OVERHEAD_S,
            "programmed_s": T1_DELAY_S,
        },
        "observer": {"identity_env": "R3_T1_SHA256",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
        "t2_status": "DESIGNED",
    }
    (out / "p1b-t1-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")

    gates = [
        "T1_BUILD_GATES=PASS",
        "T1_BASELINE=FROZEN_FIX8",
        "T1_PRIMARY_ENTRY_OFFSET_REDERIVED=YES",
        f"PRIMARY_ENTRY_OFFSET={off_primary:#x}",
        "T1_PRIMARY_ENTRY_ORIGINAL_INSN=bl record_mmu_state",
        "T1_PRIMARY_ENTRY_ORIGINAL_INSN_SOURCES_AGREE=YES",
        "T1_REBUILT_IMAGE_BYTE_IDENTICAL=NO",
        "IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES",
        f"IMAGE_FILE_SIZE={image_file_size}",
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}",
        f"T1_CHECKPOINT_OFFSET={checkpoint_off:#x}",
        "T1_CHECKPOINT_OUTSIDE_IMAGE_FILE=YES",
        "T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES",
        "T1_CHECKPOINT_BEFORE_RTD=YES",
        "T1_CHECKPOINT_PADDING_ZERO=YES",
        "T1_CHECKPOINT_PADDING_REGION_SAFE=YES",
        f"T1_BRANCH_DISTANCE={delta:#x}",
        "T1_BRANCH_IN_RANGE=YES",
        f"T1_DEVICE_CANDIDATE_DELAY={T1_DELAY_S}s",
        "T1_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "T1_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "T1_FAIL_CLOSED=YES",
        "T1_NO_STACK=YES",
        "T1_NO_MEMORY_WRITES=YES",
        "T1_NO_MEMORY_READS=YES",
        "T1_NO_X0_DEREFERENCE=YES",
        "T1_POSITION_INDEPENDENT=YES",
        "T1_RUNTIME_RELOCATIONS=0",
        "T1_RUNTIME_SEMANTIC_DELTA=PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY",
        "T1_TRAMPOLINE_IDENTICAL_TO_FIX8=YES",
        "T1_RT_D_IDENTITY=YES",
        "T1_INIT_IDENTITY=YES",
        "T1_INITRAMFS_IDENTITY=YES",
        "T1_PAYLOAD_DIFF_ATTRIBUTED="
        "PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY",
        f"T1_DIFF_BYTE_COUNT={len(diffs)}",
        "T1_PAYLOAD_SIZE_IDENTICAL=YES",
        "T1_BOOT_SIZE_IDENTICAL=YES",
        f"T1_DTB_OFFSET={DTB_OFFSET:#x}",
        "T1_GEOMETRY_GATES=PASS",
        "T1_NEGATIVE_FIXTURES=PASS",
        "T1_DECODER_FIXTURES=PASS",
        "T1_DIAGNOSTIC_ONLY=YES",
        "T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
        "T2_STATUS=DESIGNED",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "p1b-t1-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))


# ---------------------------------------------------------------------------
# Observer fixture mode.
# ---------------------------------------------------------------------------

def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("t1_obs_fixtures",
                                                  OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-t1-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("T1_OBSERVER_FIXTURES=PASS")


# ---------------------------------------------------------------------------
# Private pack gates.
# ---------------------------------------------------------------------------

def cmd_t1_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    off_primary = int(args.primary_entry_offset, 16)
    checkpoint_off = int(args.checkpoint_offset, 16)
    probe = Path(args.checkpoint_bin).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("T1_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("T1_PACK_FAILED", f"payload sha={sha(payload)}")
    if sha(probe) != args.checkpoint_sha:
        fail("T1_PACK_FAILED", f"checkpoint sha={sha(probe)}")
    hdr = pb.parse_image_hdr(payload, "t1-payload")
    image_size = hdr["image_size"]
    gate_image_size_rederived(image_size, "t1-packed-payload")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("T1_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T1_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T1_PACK_FAILED", "payload length")
    gate_checkpoint_placement(checkpoint_off, FIX8_IMAGE_FILE_SIZE, image_size,
                              len(probe), dtb_offset)
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T1_PACK_FAILED",
             f"embedded trampoline sha={sha(tramp)} != frozen FIX8")
    # Primary_entry patch present and correct.
    branch_word = struct.unpack_from("<I", payload, off_primary)[0]
    gate_branch_patch(branch_word, off_primary, checkpoint_off)
    # Checkpoint region bytes present.
    ck = payload[checkpoint_off:checkpoint_off + len(probe)]
    if ck != probe:
        fail("T1_PACK_FAILED", "checkpoint region != built T1 checkpoint")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I", FDT_MAGIC):
        fail("T1_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "t1-candidate")
    if cand["kernel"] != payload:
        fail("T1_PACK_FAILED", "candidate kernel != T1 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("T1_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("T1_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("T1_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("T1_PACK_FAILED", "reserved differs from M5D")
    if cand["ramdisk_size"] != ref["ramdisk_size"]:
        fail("T1_PACK_FAILED", "ramdisk_size differs")
    if cand["tail_pad"] != ref["tail_pad"]:
        fail("T1_PACK_FAILED", "tail padding policy differs")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("T1_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("T1_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T1_PACK_FAILED", "DTB residue geometry")
    if len(boot) >= BOOT_CAP or BOOT_CAP - len(boot) < 0x1000000:
        fail("T1_PACK_FAILED", "capacity")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-t1-pack-gates.txt"
    report.write_text(
        "T1_PACK_GATES=PASS\n"
        f"T1_BOOT_SIZE={len(boot)}\n"
        f"T1_BOOT_SHA256={sha(boot)}\n"
        f"T1_PAYLOAD_SHA256={sha(payload)}\n"
        f"T1_TRAMP_SHA256={sha(tramp)} (frozen FIX8 trampoline, unmodified)\n"
        f"T1_CHECKPOINT_SHA256={sha(probe)}\n"
        f"T1_KERNEL_SIZE={len(payload)}\n"
        f"T1_PRIMARY_ENTRY_OFFSET={off_primary:#x}\n"
        f"T1_CHECKPOINT_OFFSET={checkpoint_off:#x}\n"
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}\n"
        f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}\n"
        "T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES\n"
        f"T1_DTB_OFFSET={dtb_offset:#x}\n"
        "T1_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "T1_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "T1_BOOT_CAPACITY=PASS\n"
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


# ---------------------------------------------------------------------------
# Source gate.
# ---------------------------------------------------------------------------

def need(text: str, needle: str, label: str = "T1_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str, label: str = "T1_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [T1_DEVICE_S, T1_DEVICE_LD, T1_PROTO_S, OBSERVER,
                OBSERVER_FIXTURES, Path(__file__), DOC, STATUS_DOC, WF,
                HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld"]
    for path in required:
        if not path.is_file():
            fail("T1_SOURCE_GATE_FAILED", f"missing {path}")
    dev = T1_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "isb", "mrs\tx9, cntfrq_el0",
                  "mrs\tx11, cntpct_el0", "mrs\tx12, cntpct_el0", "yield",
                  "smc\t#0", "wfe", "P1B_T1_DELAY",
                  "#if (P1B_T1_DELAY) != 8", "r3_t1_checkpoint"):
        need(dev, token)
    # Fail-closed + no handoff replication: no x0/DTB setup, no loads, no
    # primary_entry continuation of any kind.
    for token in ("P1B_DTB_REL", "dtb_rel", "adr\t", "ldr\t",
                  "mov\tx1, xzr", "mov\tx2, xzr", "mov\tx3, xzr",
                  "eret", "sctlr", "b\tprimary"):
        forbid(dev, token)
    # The CI prototype (p1b-t1-gap-probe.S) stays retained verbatim.
    proto = T1_PROTO_S.read_text()
    need(proto, "P1B_PROBE_DELAY", "T1_PROTOTYPE_AUDIT_FAILED")
    need(proto, "r3_t1_probe", "T1_PROTOTYPE_AUDIT_FAILED")
    obs = OBSERVER.read_text()
    for token in ("R3_T1_SHA256", "T1_OBSERVER_MISBOOT_REFUSED",
                  "T1_BOOTING_TO_RETURNED_KERNEL_START", "T1_MINUS_T0",
                  "T0_REFERENCE_TOTAL_S", "T1_REACHABILITY_SIGNATURE",
                  "T1_FAILURE_ISOLATION_CI", "FASTBOOT_BOOT_ONLY",
                  "T1_NORMAL_KERNEL_BOOT_CANDIDATE", "T1_DIAGNOSTIC_ONLY",
                  "MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("T1_OBSERVER_MISBOOT_REFUSED", "NOT_REACHED",
                  "T1_STABLE_FASTBOOT", "T1_NO_RETURN"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("T1_PRIMARY_ENTRY_OFFSET_REDERIVED",
                  "PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY",
                  "T1_TRAMPOLINE_IDENTICAL_TO_FIX8",
                  "T1_CHECKPOINT_PADDING_REGION_SAFE",
                  "T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE",
                  "IMAGE_HEADER_IMAGE_SIZE",
                  "T1_DIFF_BYTE_COUNT", "T1_DIFF_RANGES",
                  "T0_REFERENCE_TOTAL", "14.252", "6.1445", "0x2380000",
                  "0x84000009", "wfe", "CNTPCT",
                  "T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
                  "T1_FAILURE_ISOLATION", "STRONG", "SUPPORTED",
                  "READY_FOR_R3_P1B_T1_DEVICE_CONTROL",
                  "R3_P1B_T1_PREDEVICE_NOT_READY", "T2", "E1"):
        need(doc, token)
    status = STATUS_DOC.read_text()
    for token in ("MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI",
                  "MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI",
                  "T0 CI_PASS", "T0 TRUE DEVICE", "14.252", "T1 PREDEVICE",
                  "T2 DESIGNED", "PANIC30", "FIX24", "M5N", "FROZEN",
                  "NOT_PROVEN"):
        need(status, token)
    wf_text = WF.read_text()
    for token in ("p1b-t1-device.S", "p1b-t1-predevice.py",
                  "thyme-r3-p1b-t1", "T1_BUILD_GATES=PASS",
                  "T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES",
                  "observer-fixtures"):
        need(wf_text, token)
    for verb in ("fastboot", "adb", "flash", "erase", "set_active",
                 "mkbootimg", "splice-boot", "boot.img"):
        forbid(wf_text, verb)
    for path in REPO.rglob("*.img"):
        rel = path.relative_to(REPO).as_posix()
        top = rel.split("/", 1)[0]
        if top in ("linux-6.6", "test", "route-a-v2-artifact",
                   "thyme-mainline-firstboot-29bc752517c53a5532bd1974e3bff59cca5af391"):
            continue
        if "r3-p1b" in rel or "p1b" in rel:
            fail("T1_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    print("T1_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "t1", "observer-fixtures", "t1-pack-gates"),
        required=True)
    parser.add_argument("--out", default="out-t1")
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
    parser.add_argument("--primary-entry-offset")
    parser.add_argument("--checkpoint-offset")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
    elif args.mode == "t1":
        if not (args.rt_d and args.fix8_payload):
            fail("T1_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_t1(args)
    elif args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
    elif args.mode == "t1-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.checkpoint_bin
                    and args.checkpoint_sha and args.primary_entry_offset
                    and args.checkpoint_offset and args.out)
        if not need_all:
            fail("T1_PACK_FAILED",
                 "need --m5d-boot --payload --boot --payload-sha "
                 "--checkpoint-bin --checkpoint-sha --primary-entry-offset "
                 "--checkpoint-offset --out")
        cmd_t1_pack_gates(args)


if __name__ == "__main__":
    main()
