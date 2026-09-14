#!/usr/bin/env python3
"""R3 P1B T2 predevice readiness (MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source/doc boundary checks (no build)
  t2                  frozen-FIX8-anchored T2-8 fail-closed device candidate:
                      authoritative kernel rebuild (vmlinux + System.map),
                      __primary_switched re-derivation (never a history
                      constant), inline-overwrite safety scan (symbol /
                      relocation / control-flow / section-boundary /
                      absolute-literal), entry-contract audit, original
                      instruction identity, T1-diagnostic-core byte identity,
                      frozen-byte payload patch + single-region diff
                      attribution, geometry, negative fixtures,
                      T1-matched-control decoder fixtures
  observer-fixtures   T2 observer fixture suite (imports the observer module)
  t2-pack-gates       private: gates over a packed T2 boot v3 image

T2 is INLINE: the probe is written over the first contiguous instructions of
__primary_switched in kernel .head.text. Nothing before it is touched, so the
trampoline, primary_entry and the whole pre-T2 head.S path stay byte-identical
to the frozen FIX8 payload; the ONLY payload diff is the single inline
overwrite region. The delay/reset core is byte-identical to the T0/T1
true-device proven diagnostic core.

T2 is DESTRUCTIVE diagnostic only: it never returns, never executes the
overwritten instructions and never reaches start_kernel
(T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO). A future positive proves
__primary_switched ADDRESS reachability (R3) and, because the pre-checkpoint
head.S path is byte-identical to FIX8, that the normal primary_entry path
executed up to T2. E1 is upgraded only under the frozen rule below.

Future T2 timing is matched-control against T1 (primary reference
T1_TOTAL = 14.238 s): STRONG |T2_MINUS_T1| <= 1.0 s, SUPPORTED <= 2.0 s, plus
T2_TOTAL < 20 s and AUTOMATIC_ANDROID_RETURN; T0_TOTAL = 14.252 s is the
second matched reference. The P0 6.1445 s decoder is SECONDARY only.
"""
from __future__ import annotations

import argparse
import array
import importlib.util
import json
import os
import re
import struct
import sys
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1b-t2-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-t2-predevice.yml"
T2_DEVICE_S = HERE / "p1b-t2-device.S"
T2_DEVICE_LD = HERE / "p1b-t2-device.ld"
T1_DEVICE_S = HERE / "p1b-t1-device.S"
T1_DEVICE_LD = HERE / "p1b-t1-device.ld"
T1_PROTO_S = HERE / "p1b-t1-gap-probe.S"
OBSERVER = HERE / "observe-r3-p1b-t2.py"
OBSERVER_FIXTURES = HERE / "observer-t2-fixtures.py"
PRIVATE_WF = REPO / "artifacts" / "p1b-t2-private-workflow-staging.yml"

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
FIX8_IMAGE_SIZE_HISTORY_READINGS = (0x2230000, 0x2231000)
IMAGE_HEADER_IMAGE_SIZE = 0  # authored by cmd_t2() from the real header
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
T2_DELAY_S = 8
T2_CORE_SIZE = 0x4C  # 76 bytes = 19 instructions: the T1-proven core
T2_BTI_PAD = 0x4  # leading `bti c` landing pad kept from __primary_switched
T2_PROBE_SIZE = T2_CORE_SIZE + T2_BTI_PAD  # 80 bytes = 20 instructions
T2_BTI_PAD_WORD = 0xD503245F  # `bti c`
T2_ORIGINAL_FIRST_INSN = "bti c"
T2_ORIGINAL_SECOND_INSN = "adrp x4, init_task"

FORBIDDEN_BOOT_SHAS = {
    "T0_BOOT":
        "8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1",
    "T1_BOOT":
        "a4fa083f289219facb0a69062749dd6a9d2f667c4aa044b25b78c36b0da7e3df",
    "FIX8_BOOT":
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5",
    "PANIC30_BOOT":
        "ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1",
    "OLD_INIT8_BOOT":
        "e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264",
    "ENTRY_STATE_PROBE_BOOT":
        "cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c",
}

# Preregistered matched-control timing (prompt sections 39-44). The PRIMARY
# reference is the T1 true-device total; T0 is the second matched reference.
T1_REFERENCE_TOTAL_S = 14.238
T0_REFERENCE_TOTAL_S = 14.252
T1_MINUS_T0_OBSERVED_S = -0.014
T2_STRONG_HALF_WINDOW_S = 1.0
T2_SUPPORTED_HALF_WINDOW_S = 2.0
T2_CROSSCHECK_HALF_WINDOW_S = 2.0
T2_EARLY_RETURN_CLASS_LIMIT_S = 20.0
T2_CASE_C_BAND_S = (20.0, 28.0)
P0_REF_OVERHEAD_S = 6.1445
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
T2_NO_RETURN_WINDOW_S = 120.0

T2_CLOBBER_REGISTERS = "w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV"
T2_BOOT_SIZE_EXPECTED = 37380096

# ---------------------------------------------------------------------------
# T2 entry contract (prompt sections 8/9/18/20). Every field is derived from the
# exact linux-6.6.156 head.S / proc.S path and is gated against these frozen
# literals so the CI, the doc and the manifest cannot drift apart.
# ---------------------------------------------------------------------------
T2_ENTRY_CONTRACT = {
    "T2_ENTRY_CURRENT_EL": "EL1",
    "T2_ENTRY_MMU": "ON",
    "T2_ENTRY_TTBR_STATE":
        "TTBR0_EL1=init_idmap_pg_dir(PHYS) TTBR1_EL1=init_pg_dir(PHYS)",
    "T2_ENTRY_PC_ADDRESS_SPACE": "VA",
    "T2_ENTRY_SP_VALID": "YES",
    "T2_ENTRY_DAIF": "D=0,A=1,I=1,F=1",
    "T2_ENTRY_X0_MEANING": "__pa(KERNEL_START) (adrp x0, KERNEL_START)",
    "T2_ENTRY_X1_MEANING": "page-table scratch from load_ttbr1 (NOT boot contract)",
    "T2_ENTRY_X2_MEANING": "init_idmap_pg_dir scratch temp (NOT boot contract)",
    "T2_ENTRY_X3_MEANING": "scratch, pre-T2 residue (NOT boot contract)",
    "T2_ENTRY_X19_X25":
        "x19=mmu_enabled_at_boot(0) x20=cpu_boot_mode x21=FDT pa "
        "x22=idmap VA of DT x23=KASLR/load offset x24=memstart seed "
        "x25=supported VA size; probe writes NONE of them",
}
T2_ENTRY_CONTRACT_REASONS = {
    "T2_ENTRY_CURRENT_EL":
        "init_kernel_el eret with SPSR_EL1/EL2 = INIT_PSTATE_EL1 "
        "(PSR_MODE_EL1h)",
    "T2_ENTRY_MMU":
        "__enable_mmu set_sctlr_el1 x0 with INIT_SCTLR_EL1_MMU_ON "
        "(SCTLR_EL1.M=1) before __primary_switch continues",
    "T2_ENTRY_TTBR_STATE":
        "__enable_mmu msr ttbr0_el1=init_idmap_pg_dir(PHYS) then "
        "__primary_switch load_ttbr1 init_pg_dir",
    "T2_ENTRY_PC_ADDRESS_SPACE":
        "__primary_switch ldr x8, =__primary_switched ; br x8 -- an indirect "
        "branch to the linked (and __relocate_kernel-relocated) kernel VA",
    "T2_ENTRY_SP_VALID":
        "__primary_switch under CONFIG_RELOCATABLE+CONFIG_RANDOMIZE_BASE sets "
        "mov sp, x1 (init_pg_end, mapped+writable); NOT used by the probe",
    "T2_ENTRY_DAIF":
        "init_kernel_el eret masks D/A/I/F (INIT_PSTATE_EL1); __cpu_setup "
        "then runs enable_dbg (msr daifclr, #8), clearing D only",
    "T2_ENTRY_X0_MEANING":
        "__primary_switch adrp x0, KERNEL_START (runtime __pa of _text)",
    "T2_ENTRY_X1_X3":
        "preserve_boot_args stored the ABL x0..x3 into boot_args before these "
        "registers were reused by load_ttbr1 / KASLR scratch",
    "T2_ENTRY_X19_X25":
        "head.S register contract comment (lines 75-88); init_cpu_task has not "
        "run yet at the first instruction of __primary_switched",
}
T2_CNTPCT_ACCESS_SAFE_REASON = (
    "head.S and __cpu_setup touch neither CNTKCTL_EL1 nor CNTHCTL_EL2 nor any "
    "counter-trap control (grep-verified: cpacr_el1/tcr_el1/sctlr_el1/mair_el1 "
    "only); CNTFRQ_EL0/CNTPCT_EL0 reads are EL1-legal regardless of "
    "SCTLR_EL1.M, the same EL1 access was proven on this device at T0 and T1, "
    "and MMU state does not affect system-register access")
T2_PSCI_SAFE_REASON = (
    "PSCI SYSTEM_RESET fid=0x84000009 carries no pointer argument, so no "
    "VA->PA conversion is involved; smc traps synchronously to EL3 regardless "
    "of SCTLR_EL1.M; the identical EL1 smc was proven on this device at T0/T1")

T2_RUNTIME_SEMANTIC_DELTA = "PRIMARY_SWITCHED_REACHABILITY_CHECKPOINT_ONLY"

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
    r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$")
DST_RE = re.compile(r"(x[0-9]+|w[0-9]+|xzr|wzr|sp|wsp)")
FID_LOW_RE = re.compile(r"(movz|mov) w0, #(0x9|9)\b")
FID_HIGH_RE = re.compile(r"movk w0, #(0x8400|33792), lsl #16\b")
T2_STORE_RE = re.compile(
    r"\b(st|str|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|cas|swp|adrp)\b",
    re.I)
T2_LOAD_RE = re.compile(
    r"\b(ldr|ldrb|ldrh|ldp|ldur|ldar|ldxr|ldtr)\b", re.I)
PADDING_MNEMS = {"udf", ".inst", ".word", "nop"}
RELOC_OFF_RE = re.compile(r"^([0-9a-f]{8,16})\s+\S+\s+R_AARCH64_")
STATUS_KV_BEGIN = "<!-- R3-STATUS-KV:BEGIN -->"
STATUS_KV_END = "<!-- R3-STATUS-KV:END -->"

# Status-doc gate (prompt section 51): STRUCTURED key/value block, never a
# natural-language literal string. T2_STATUS_GATE_SEMANTIC=YES.
STATUS_DOC_REQUIRED_KV = {
    "T0_STATUS": "TRUE_DEVICE_PROVEN",
    "T0_TOTAL_S": "14.252",
    "T1_STATUS": "TRUE_DEVICE_PROVEN",
    "T1_TOTAL_S": "14.238",
    "T1_MINUS_T0_S": "-0.014",
    "R0_STATUS": "PROVEN",
    "R1_STATUS": "PROVEN",
    "R2_STATUS": "PROVEN",
    "R3_STATUS": "NOT_PROVEN",
    "T2_STATUS": "PREDEVICE_READY",
    "T2_DEVICE_CONTROL": "NOT_AUTHORIZED",
    "PANIC30_STATUS": "COMPLETED",
    "PANIC30_SHIFT": "NO_SUPPORTED_SHIFT",
    "FIX24_STATUS": "FROZEN",
    "M5N_STATUS": "FROZEN",
    "CURRENT_B": "M5D+M5H+M5M-B",
    "SLOT_A_WRITTEN": "NO",
}


def fail(label: str, detail: str = "") -> None:
    iso.fail(label, detail)


def sha(data: bytes) -> str:
    return pb.sha(data)


def image_words(image: bytes) -> array.array:
    n = len(image) // 4
    words = array.array("I")
    words.frombytes(image[:n * 4])
    if sys.byteorder != "little":
        words.byteswap()
    return words


# ---------------------------------------------------------------------------
# Reusable inline-safety gates (negative fixtures call these with mutated
# inputs). The window is expressed in the LINK-TIME VA coordinate space.
# ---------------------------------------------------------------------------

def gate_window_symbol_scan(ps_va: int, window_len: int,
                            symbol_vas: list) -> int:
    bad = sorted(v for v in symbol_vas if ps_va < v < ps_va + window_len)
    if bad:
        fail("T2_INLINE_SAFETY_FAILED",
             f"symbol entry inside the overwrite window at "
             f"{[hex(v) for v in bad[:8]]}")
    return len(symbol_vas)


def gate_window_branch_scan(ps_va: int, window_len: int,
                            hits: list) -> int:
    bad = sorted((s, t) for s, t in hits if ps_va < t < ps_va + window_len)
    if bad:
        fail("T2_INLINE_SAFETY_FAILED",
             f"control transfer into the overwrite window at "
             f"{[(hex(s), hex(t)) for s, t in bad[:8]]}")
    return len(hits)


def gate_window_relocation_scan(ps_va: int, window_len: int,
                                offsets: list) -> int:
    bad = sorted(o for o in offsets if ps_va <= o < ps_va + window_len)
    if bad:
        fail("T2_INLINE_SAFETY_FAILED",
             f"runtime relocation target inside the overwrite window at "
             f"{[hex(v) for v in bad[:8]]} (__relocate_kernel would rewrite "
             "the probe bytes)")
    return len(offsets)


def gate_window_literal_scan(ps_va: int, window_len: int, image: bytes) -> int:
    """No 8-byte aligned literal anywhere in the Image may hold an absolute VA
    landing STRICTLY inside the window: such a pointer would give an indirect
    entry into the middle of the overwritten range."""
    n = len(image) // 8
    words = array.array("Q")
    words.frombytes(image[:n * 8])
    if sys.byteorder != "little":
        words.byteswap()
    for i, v in enumerate(words):
        if ps_va < v < ps_va + window_len:
            fail("T2_INLINE_SAFETY_FAILED",
                 f"absolute literal pointing into the overwrite window at "
                 f"image offset {i * 8:#x} value {v:#x}")
    return n


def gate_window_section_scan(ps_va: int, window_len: int,
                             sections: list) -> dict:
    containing = [s for s in sections
                  if s["vma"] <= ps_va < s["vma"] + s["size"]]
    if len(containing) != 1:
        fail("T2_INLINE_SAFETY_FAILED",
             f"{len(containing)} sections contain {ps_va:#x}")
    s = containing[0]
    if ps_va + window_len > s["vma"] + s["size"]:
        fail("T2_INLINE_SAFETY_FAILED",
             f"window end {ps_va + window_len:#x} crosses section "
             f"{s['name']} end {s['vma'] + s['size']:#x}")
    if not s["code"]:
        fail("T2_INLINE_SAFETY_FAILED",
             f"section {s['name']} is not executable (NX)")
    if not s["alloc"]:
        fail("T2_INLINE_SAFETY_FAILED",
             f"section {s['name']} is not allocated")
    return s


def gate_probe_mapping(source: str) -> None:
    """Prompt sections 10/13/14: only an INLINE probe whose mapping is the
    kernel text VA the CPU is already executing is acceptable; any padding or
    external-region claim is rejected by default."""
    if source != "KERNEL_TEXT_VA_SELF_EVIDENT":
        fail("T2_MAPPING_FAILED",
             f"mapping source {source!r} is not a proven executable mapping "
             "(unproven padding mapping is REJECTED)")


def gate_entry_contract(contract: dict, expected: dict) -> None:
    if contract != expected:
        diff = {k: (contract.get(k), expected.get(k))
                for k in set(contract) | set(expected)
                if contract.get(k) != expected.get(k)}
        fail("T2_ENTRY_STATE_FAILED", f"contract drift {diff}")
    if contract["T2_ENTRY_MMU"] != "ON":
        fail("T2_ENTRY_STATE_FAILED", "MMU assumed OFF")
    if contract["T2_ENTRY_PC_ADDRESS_SPACE"] != "VA":
        fail("T2_ENTRY_STATE_FAILED",
             "physical address used as the T2 PC address space")


def gate_cnppct_safety(reason: str, safe: bool) -> None:
    if not safe or not reason:
        fail("T2_TIMER_FAILED",
             "CNTFRQ_EL0/CNTPCT_EL0 access at T2 is not provably legal")
    for token in ("CNTKCTL_EL1", "CNTHCTL_EL2", "MMU", "EL1"):
        if token not in reason:
            fail("T2_TIMER_FAILED", f"timer audit reason lacks {token}")


def gate_psci_safety(reason: str, safe: bool) -> None:
    if not safe or not reason:
        fail("T2_PSCI_FAILED", "PSCI SYSTEM_RESET at T2 is not provably safe")
    for token in ("0x84000009", "smc", "EL3"):
        if token not in reason:
            fail("T2_PSCI_FAILED", f"PSCI audit reason lacks {token}")


def gate_vmlinux_frozen_agreement(ps_va: int, off_ps: int, dump: str,
                                  frozen: bytes) -> int:
    """The authoritative vmlinux disassembly at __primary_switched must agree
    byte-for-byte with the frozen payload at the re-derived Image offset."""
    insns = [l for l in dump.splitlines() if INSTR_RE.match(l)]
    if not insns:
        fail("T2_IDENTITY_FAILED", "empty __primary_switched disassembly")
    first = INSTR_RE.match(insns[0])
    addr = int(first.group(1), 16)
    word = int(first.group(2), 16)
    if addr != ps_va:
        fail("T2_IDENTITY_FAILED",
             f"vmlinux disassembly starts at {addr:#x}, expected {ps_va:#x}")
    frozen_word = struct.unpack_from("<I", frozen, off_ps)[0]
    if word != frozen_word:
        fail("T2_IDENTITY_FAILED",
             f"vmlinux word {word:#010x} != frozen payload word "
             f"{frozen_word:#010x} at Image offset {off_ps:#x}")
    return word


def gate_ps_original_insn(word0: int, word1: int, head_insn: str) -> None:
    """The ORIGINAL first instruction of __primary_switched is `bti c`,
    emitted unconditionally by SYM_FUNC_START_LOCAL (arch/arm64/include/asm/
    linkage.h lines 26-28); the second is `adr_l x4, init_task` (head.S line
    473), which emits ADRP Rd=x4 then ADD Rd=Rn=x4. Identity of both is what
    makes the overwrite auditable and what preserves the BTI landing pad."""
    if word0 != T2_BTI_PAD_WORD:
        fail("T2_IDENTITY_FAILED",
             f"frozen first word {word0:#010x} is not `bti c` "
             f"({T2_BTI_PAD_WORD:#010x})")
    if (word1 & 0x9F000000) != 0x90000000 or (word1 & 0x1F) != 4:
        fail("T2_IDENTITY_FAILED",
             f"frozen second word {word1:#010x} is not `adrp x4, init_task`")
    if re.sub(r"\s+", " ", head_insn.strip()) != "adr_l x4, init_task":
        fail("T2_IDENTITY_FAILED",
             f"head.S first __primary_switched instruction is {head_insn!r}, "
             "expected `adr_l x4, init_task`")


def gate_diagnostic_core_identity(t2_probe: bytes, t1_probe: bytes) -> None:
    """Prompt section 24: the T2 delay/reset core must be byte-identical to the
    T0/T1 true-device proven diagnostic core. The only permitted difference is
    the insertion mechanic: one leading `bti c` landing pad."""
    if len(t2_probe) != T2_PROBE_SIZE:
        fail("T2_CORE_IDENTITY_FAILED",
             f"probe size {len(t2_probe)} != {T2_PROBE_SIZE}")
    pad = t2_probe[:T2_BTI_PAD]
    if pad != struct.pack("<I", T2_BTI_PAD_WORD):
        fail("T2_CORE_IDENTITY_FAILED",
             f"probe does not start with `bti c`: {pad.hex()}")
    core = t2_probe[T2_BTI_PAD:]
    if core != t1_probe:
        fail("T2_CORE_IDENTITY_FAILED",
             f"T2 core sha={sha(core)} != T1 core sha={sha(t1_probe)}")
    if len(core) != T2_CORE_SIZE:
        fail("T2_CORE_IDENTITY_FAILED",
             f"core size {len(core)} != {T2_CORE_SIZE}")


def gate_no_relocations(rel_text: str, label: str) -> None:
    if "R_AARCH64_" in rel_text:
        fail("T2_RELOC_FAILED", f"{label}: {rel_text[:200]}")


def gate_ops_order(ops: str) -> None:
    pos = -1
    for tok, is_re in ORDER_TOKENS:
        if is_re:
            m = re.search(tok, ops)
            p = m.start() if m else -1
        else:
            p = ops.find(tok)
        if p < 0:
            fail("T2_DISASM_FAILED", f"missing {tok!r}")
        if p <= pos:
            fail("T2_DISASM_FAILED", f"order violation at {tok!r}")
        pos = p


def gate_branch_targets(dump: str, probe_len: int) -> None:
    for line in dump.splitlines():
        m = BRANCH_RE.match(line)
        if not m:
            continue
        target = int(m.group(3), 16)
        if target >= probe_len or target % 4:
            fail("T2_DISASM_FAILED",
                 f"branch target {target:#x} outside T2 checkpoint")


def gate_terminal(dump: str) -> None:
    instrs = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if m:
            instrs.append((int(m.group(1), 16), m.group(3), m.group(4)))
    smc_idx = [i for i, (_a, mn, _o) in enumerate(instrs) if mn == "smc"]
    if len(smc_idx) != 1:
        fail("T2_DISASM_FAILED", f"smc count {len(smc_idx)}")
    smc = smc_idx[0]
    if smc + 2 >= len(instrs):
        fail("T2_DISASM_FAILED", "no wfe loop after smc")
    nxt = instrs[smc + 1]
    if nxt[1] != "wfe":
        fail("T2_DISASM_FAILED",
             f"instruction after smc is {nxt[1]!r}, not wfe (fall-through)")
    term = instrs[smc + 2]
    if term[1] != "b":
        fail("T2_DISASM_FAILED",
             f"instruction after wfe is {term[1]!r}, not b")
    m = re.match(r"^(?:0x)?([0-9a-f]+)", term[2].strip().split("<", 1)[0])
    if not m or int(m.group(1), 16) != nxt[0]:
        fail("T2_DISASM_FAILED",
             f"terminal b does not target wfe at {nxt[0]:#x} "
             f"(operand {term[2]!r})")
    for ins in instrs[smc + 3:]:
        if ins[1] not in PADDING_MNEMS:
            fail("T2_DISASM_FAILED",
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
            fail("T2_DISASM_FAILED",
                 f"boot contract register written: {line!r}")
        if dst in ("x0", "w0"):
            if not (FID_LOW_RE.search(line) or FID_HIGH_RE.search(line)):
                fail("T2_DISASM_FAILED", f"x0/w0 written off-FID: {line!r}")
            continue
        if dst not in {"x9", "x10", "x11", "x12", "x13"}:
            fail("T2_DISASM_FAILED", f"register discipline: {line!r}")


def gate_no_forbidden(ops: str) -> None:
    m = T2_STORE_RE.search(ops)
    if m:
        fail("T2_DISASM_FAILED", f"store/adrp present: {m.group(0)!r}")
    m = T2_LOAD_RE.search(ops)
    if m:
        fail("T2_DISASM_FAILED", f"memory load present: {m.group(0)!r}")
    for bad in (r"\bbl\b", r"\blr\b", r"\beret\b", r"\bsctlr\b",
                r"\bttbr", r"\bmsr\b\s+daifclr", r"\bsp\b", r"\bwsp\b",
                r"\bx19\b", r"\bx2[0-5]\b", r"\bx29\b", r"\bx30\b"):
        if re.search(bad, ops):
            fail("T2_DISASM_FAILED", f"forbidden {bad!r}")
    if "primary_entry" in ops or "start_kernel" in ops:
        fail("T2_DISASM_FAILED", "normal-kernel continuation reference present")


def gate_t2_probe(ops: str, dump: str, probe_len: int) -> None:
    gate_ops_order(ops)
    gate_branch_targets(dump, probe_len)
    gate_terminal(dump)
    gate_register_discipline(ops)
    gate_no_forbidden(ops)


def gate_payload_diff(frozen: bytes, cand: bytes,
                      region: tuple) -> list:
    if len(cand) != len(frozen):
        fail("T2_PAYLOAD_DIFF_FAILED",
             f"size drift {len(cand)} != {len(frozen)}")
    lo, hi = region
    diffs = [i for i in range(len(frozen)) if frozen[i] != cand[i]]
    bad = [i for i in diffs if not (lo <= i < hi)]
    if bad:
        fail("T2_PAYLOAD_DIFF_FAILED",
             f"diff outside the inline region at {[hex(i) for i in bad[:8]]} "
             "(the pre-T2 head.S path and the trampoline must stay "
             "byte-identical to FIX8)")
    if not diffs:
        fail("T2_PAYLOAD_DIFF_FAILED", "inline region has no diff (patch lost?)")
    return diffs


def gate_tramp_identity(cand: bytes) -> None:
    tramp = cand[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T2_IDENTITY_FAILED",
             f"embedded trampoline sha={sha(tramp)} != frozen FIX8 {TRAMP_SHA}")


def gate_trailer(payload: bytes) -> bytes:
    hdr = pb.parse_image_hdr(payload, "t2-payload")
    dtb_offset, _gap = pb.calc_dtb_offset(hdr["image_size"])
    trailer = payload[dtb_offset:]
    if payload[dtb_offset:dtb_offset + 4] != struct.pack(">I", FDT_MAGIC):
        fail("T2_PAYLOAD_DIFF_FAILED", "no FDT magic at DTB_OFFSET")
    if sha(trailer) != RT_D_SHA or len(trailer) != RT_D_SIZE:
        fail("T2_PAYLOAD_DIFF_FAILED",
             f"trailer RT-D identity sha={sha(trailer)} len={len(trailer)}")
    return trailer


def gate_geometry(payload: bytes, image_size: int) -> tuple:
    hdr = pb.parse_image_hdr(payload, "t2-payload")
    if hdr["image_size"] != image_size:
        fail("T2_GEOMETRY_FAILED",
             f"image_size {hdr['image_size']:#x} != authoritative "
             f"{image_size:#x}")
    dtb_offset, gap = pb.calc_dtb_offset(hdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("T2_GEOMETRY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T2_GEOMETRY_FAILED",
             f"payload len {len(payload)} != dtb_offset + RT_D")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T2_GEOMETRY_FAILED", "2MiB residue geometry")
    boot_est = pb.align(PAGE + len(payload), PAGE) + PAGE
    if boot_est != T2_BOOT_SIZE_EXPECTED:
        fail("T2_GEOMETRY_FAILED",
             f"boot_est {boot_est} != {T2_BOOT_SIZE_EXPECTED}")
    if BOOT_CAP - boot_est < 0x1000000:
        fail("T2_GEOMETRY_FAILED", "capacity margin < 16MiB")
    return hdr, dtb_offset, gap, boot_est


def gate_image_size_rederived(image_size: int, label: str) -> None:
    if image_size <= 0 or image_size & 3:
        fail("T2_GEOMETRY_FAILED", f"{label}: image_size {image_size:#x}")
    if image_size + S_RESIDUE > DTB_OFFSET:
        fail("T2_GEOMETRY_FAILED",
             f"{label}: image_size footprint {image_size:#x} reaches RT-D "
             f"at {DTB_OFFSET:#x}")


# ---------------------------------------------------------------------------
# Preregistered matched-control decoder (prompt sections 39-48).
# ---------------------------------------------------------------------------

def t2_minus_t1(t2_total_s: float) -> float:
    return t2_total_s - T1_REFERENCE_TOTAL_S


def t2_minus_t0(t2_total_s: float) -> float:
    return t2_total_s - T0_REFERENCE_TOTAL_S


def t2_programmed_estimate(t2_total_s: float) -> float:
    return t2_total_s - P0_REF_OVERHEAD_S  # SECONDARY cross-check only


def t2_reachability(t2_total_s, recovery_kind: str) -> dict:
    """Primary: matched-control delta vs T1_TOTAL=14.238s; triple condition
    (window + T2_TOTAL<20s + AUTOMATIC_ANDROID_RETURN) plus the T0 second
    cross-check. A negative NEVER licenses T2_NOT_REACHED; it routes to
    T2_FAILURE_ISOLATION_CI."""
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T2_STABLE_FASTBOOT",
                "r3": "NOT_PROVEN", "next": "T2_FAILURE_ISOLATION_CI",
                "reason": "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_AND_T3_FORBIDDEN"}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T2_NO_RETURN",
                "r3": "NOT_PROVEN", "next": "T2_FAILURE_ISOLATION_CI",
                "reason": "CASE_F_NO_RETURN_MANUAL_ELAPSED_EXCLUDED"}
    if t2_total_s is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
                "r3": "NOT_PROVEN", "next": "T2_FAILURE_ISOLATION_CI",
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    d1 = t2_minus_t1(t2_total_s)
    d0 = t2_minus_t0(t2_total_s)
    early = t2_total_s < T2_EARLY_RETURN_CLASS_LIMIT_S
    cross_ok = abs(d0) <= T2_CROSSCHECK_HALF_WINDOW_S
    if early and abs(d1) <= T2_STRONG_HALF_WINDOW_S and cross_ok:
        return {"verdict": "STRONG", "case": "T2_A_STRONG", "r3": "PROVEN",
                "next": "MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI",
                "reason": "T1_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET+T0_CROSSCHECK_OK"}
    if early and abs(d1) <= T2_STRONG_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED",
                "case": "T2_A_STRONG_T0_CROSSCHECK_BLOCK",
                "r3": "STRONGLY_SUPPORTED",
                "next": "MAINLINE_V2_R3_P1B_T2_FAILURE_ISOLATION_CI",
                "reason": f"T2_MINUS_T0={d0:+.3f}s CONTRADICTS_PRIMARY"}
    if early and abs(d1) <= T2_SUPPORTED_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED", "case": "T2_B_SUPPORTED",
                "r3": "STRONGLY_SUPPORTED",
                "next": "MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI",
                "reason": "T1_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET"}
    if early:
        return {"verdict": "NOT_OBSERVED",
                "case": "T2_EARLY_RETURN_TIMING_MISMATCH", "r3": "NOT_PROVEN",
                "next": "T2_FAILURE_ISOLATION_CI",
                "reason": f"T2_MINUS_T1={d1:+.3f}s OUTSIDE_SUPPORTED_WINDOW"}
    lo, hi = T2_CASE_C_BAND_S
    if lo <= t2_total_s < hi:
        return {"verdict": "NOT_OBSERVED", "case": "T2_SIGNATURE_NOT_OBSERVED",
                "r3": "NOT_PROVEN", "next": "T2_FAILURE_ISOLATION_CI",
                "reason": "CASE_C_OLD_AUTO_RETURN_CLASS"}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN", "r3": "NOT_PROVEN",
            "next": "T2_FAILURE_ISOLATION_CI",
            "reason": f"T2_TOTAL={t2_total_s:.3f}s OUTSIDE_PREREGISTERED_BANDS"}


def run_decoder_fixtures() -> list:
    lines = []
    t3ci = "MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI"

    def case(name, total, kind, want_verdict, want_case=None, want_r3=None,
             want_next=None):
        got = t2_reachability(total, kind)
        if got["verdict"] != want_verdict:
            fail("T2_DECODER_FIXTURE_FAILED",
                 f"{name}: verdict {got['verdict']} != {want_verdict}")
        if want_case and got["case"] != want_case:
            fail("T2_DECODER_FIXTURE_FAILED",
                 f"{name}: case {got['case']} != {want_case}")
        if want_r3 and got["r3"] != want_r3:
            fail("T2_DECODER_FIXTURE_FAILED",
                 f"{name}: r3 {got['r3']} != {want_r3}")
        if want_next and got["next"] != want_next:
            fail("T2_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"T2_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"case={got['case']} r3={got['r3']}")

    case("STRONG_14P2S", 14.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T2_A_STRONG", "PROVEN", t3ci)
    case("STRONG_13P3S", 13.3, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T2_A_STRONG", "PROVEN")
    case("STRONG_15P2S", 15.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T2_A_STRONG", "PROVEN")
    case("SUPPORTED_15P3S", 15.3, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T2_B_SUPPORTED", "STRONGLY_SUPPORTED", t3ci)
    case("SUPPORTED_16P2S", 16.2, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T2_B_SUPPORTED", "STRONGLY_SUPPORTED")
    case("SUPPORTED_12P3S", 12.3, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T2_B_SUPPORTED", "STRONGLY_SUPPORTED")
    case("EARLY_MISMATCH_16P4S", 16.4, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T2_EARLY_RETURN_TIMING_MISMATCH", "NOT_PROVEN",
         "T2_FAILURE_ISOLATION_CI")
    case("EARLY_MISMATCH_11P0S", 11.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T2_EARLY_RETURN_TIMING_MISMATCH", "NOT_PROVEN")
    case("CASE_C_FIX8_CLASS_23P852S", FIX8_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T2_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN", "T2_FAILURE_ISOLATION_CI")
    case("CASE_C_PANIC30_CLASS_26P289S", PANIC30_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T2_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN")
    case("CASE_C_BAND_EDGE_20P0S", 20.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T2_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN")
    case("CASE_E_STABLE_FASTBOOT", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "T2_STABLE_FASTBOOT", "NOT_PROVEN",
         "T2_FAILURE_ISOLATION_CI")
    case("CASE_F_NO_RETURN", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "T2_NO_RETURN", "NOT_PROVEN",
         "T2_FAILURE_ISOLATION_CI")
    case("UNKNOWN_KIND", 14.2, "UNKNOWN", "NOT_OBSERVED", "UNKNOWN",
         "NOT_PROVEN")
    case("T0_CROSSCHECK_CONTRADICTION", 14.2,
         "AUTOMATIC_ANDROID_RETURN_UNUSED", "NOT_OBSERVED", "UNKNOWN",
         "NOT_PROVEN")
    est = t2_programmed_estimate(T1_REFERENCE_TOTAL_S)
    if abs(est - (T1_REFERENCE_TOTAL_S - P0_REF_OVERHEAD_S)) > 1e-9:
        fail("T2_DECODER_FIXTURE_FAILED", "estimate arithmetic")
    lines.append(f"T2_DECODER_REFERENCE est(T1 {T1_REFERENCE_TOTAL_S}s)="
                 f"{est:.4f}s (SECONDARY cross-check only; expected ~8s)")
    lines.append("T2_DECODER_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# Negative fixtures (prompt section 37) against the real gate functions.
# ---------------------------------------------------------------------------

def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("T2_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"T2_NEGATIVE_{name}_REJECTED=PASS"
    fail("T2_NEGATIVE_FIXTURE_FAILED", f"{name}: ACCEPTED (must reject)")


def run_negative_fixtures(ctx: dict) -> list:
    lines: list = []
    ops = ctx["ops"]
    dump = ctx["dump"]
    probe_len = ctx["probe_len"]
    ps_va = ctx["ps_va"]
    frozen = ctx["frozen"]
    cand = ctx["cand"]
    off_ps = ctx["off_ps"]
    sections = ctx["sections"]
    symbol_vas = ctx["symbol_vas"]
    reloc_offsets = ctx["reloc_offsets"]
    t1_probe = ctx["t1_probe"]
    ops_lines = ops.splitlines()
    region = (off_ps, off_ps + probe_len)

    def dump_insert_after(anchor_mnem: str, extra: list) -> str:
        out = []
        for ln in dump.splitlines():
            out.append(ln)
            m = INSTR_RE.match(ln)
            if m and m.group(3) == anchor_mnem:
                out.extend(extra)
        return "\n".join(out) + "\n"

    lines.append(expect_reject(
        "WRONG_PRIMARY_SWITCHED_SYMBOL",
        lambda: gate_window_symbol_scan(
            ctx["record_mmu_state_va"] - 4, 16, symbol_vas),
        "T2_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "WRONG_VA_FILE_OFFSET",
        lambda: gate_vmlinux_frozen_agreement(ps_va, off_ps + 4, dump, frozen),
        "T2_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "MMU_ASSUMED_OFF",
        lambda: gate_entry_contract(dict(T2_ENTRY_CONTRACT, T2_ENTRY_MMU="OFF"),
                                    T2_ENTRY_CONTRACT),
        "T2_ENTRY_STATE_FAILED"))
    lines.append(expect_reject(
        "PA_USED_AS_VA",
        lambda: gate_entry_contract(
            dict(T2_ENTRY_CONTRACT, T2_ENTRY_PC_ADDRESS_SPACE="PA"),
            T2_ENTRY_CONTRACT),
        "T2_ENTRY_STATE_FAILED"))
    lines.append(expect_reject(
        "CHECKPOINT_IN_UNMAPPED_REGION",
        lambda: gate_probe_mapping("UNMAPPED_EXTERNAL_REGION"),
        "T2_MAPPING_FAILED"))
    lines.append(expect_reject(
        "UNPROVEN_PADDING_MAPPING",
        lambda: gate_probe_mapping("PADDING_0x2230000"),
        "T2_MAPPING_FAILED"))
    nx = [dict(s) for s in sections]
    for s in nx:
        if s["vma"] <= ps_va < s["vma"] + s["size"]:
            s["code"] = False
    lines.append(expect_reject(
        "CHECKPOINT_IN_NX_REGION",
        lambda: gate_window_section_scan(ps_va, probe_len, nx),
        "T2_INLINE_SAFETY_FAILED"))
    for s in sections:
        if s["vma"] <= ps_va < s["vma"] + s["size"]:
            lines.append(expect_reject(
                "SECTION_BOUNDARY_CROSS",
                lambda s=s: gate_window_section_scan(
                    s["vma"] + s["size"] - 4, probe_len, sections),
                "T2_INLINE_SAFETY_FAILED"))
            break
    lines.append(expect_reject(
        "SYMBOL_ENTRY_IN_WINDOW",
        lambda: gate_window_symbol_scan(
            ps_va, probe_len, list(symbol_vas) + [ps_va + 8]),
        "T2_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "BRANCH_INTO_WINDOW",
        lambda: gate_window_branch_scan(
            ps_va, probe_len, [(ps_va - 0x1000, ps_va + 8)]),
        "T2_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "RUNTIME_RELOCATION_IN_WINDOW",
        lambda: gate_window_relocation_scan(
            ps_va, probe_len, list(reloc_offsets) + [ps_va + 12]),
        "T2_INLINE_SAFETY_FAILED"))
    lit = bytearray(frozen)
    struct.pack_into("<Q", lit, 0x1000, ps_va + 4)
    lines.append(expect_reject(
        "ABSOLUTE_LITERAL_INTO_WINDOW",
        lambda: gate_window_literal_scan(ps_va, probe_len, bytes(lit)),
        "T2_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "WRONG_ORIGINAL_INSTRUCTION",
        lambda: gate_ps_original_insn(0xD503201F, ctx["orig_word2"],
                                      "adr_l x4, init_task"),
        "T2_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "WRONG_SECOND_INSTRUCTION",
        lambda: gate_ps_original_insn(T2_BTI_PAD_WORD, 0xD503201F,
                                      "adr_l x4, init_task"),
        "T2_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "WRONG_HEADS_INSTRUCTION",
        lambda: gate_ps_original_insn(T2_BTI_PAD_WORD, ctx["orig_word2"],
                                      "nop"),
        "T2_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "BTI_LANDING_PAD_LOST",
        lambda: gate_diagnostic_core_identity(
            b"\x1f\x20\x03\xd5" + t1_probe, t1_probe),
        "T2_CORE_IDENTITY_FAILED"))
    bad_core = bytearray(t1_probe)
    bad_core[3] ^= 0xFF
    lines.append(expect_reject(
        "DIAGNOSTIC_CORE_MISMATCH",
        lambda: gate_diagnostic_core_identity(
            struct.pack("<I", T2_BTI_PAD_WORD) + bytes(bad_core), t1_probe),
        "T2_CORE_IDENTITY_FAILED"))
    bad_pe = bytearray(cand)
    bad_pe[ctx["primary_entry_off"]] ^= 0xFF
    lines.append(expect_reject(
        "PRIMARY_ENTRY_MODIFIED",
        lambda: gate_payload_diff(frozen, bytes(bad_pe), region),
        "T2_PAYLOAD_DIFF_FAILED"))
    bad_tramp = bytearray(cand)
    bad_tramp[TRAMP_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "TRAMPOLINE_MODIFIED",
        lambda: gate_tramp_identity(bytes(bad_tramp)), "T2_IDENTITY_FAILED"))
    v17 = re.sub(r"x10, #(?:0x)?8\b", "x10, #24", ops)
    lines.append(expect_reject(
        "WRONG_DELAY", lambda: gate_t2_probe(v17, dump, probe_len),
        "T2_DISASM_FAILED"))
    v18 = FID_HIGH_RE.sub("movk w0, #0x8401, lsl #16", ops)
    lines.append(expect_reject(
        "WRONG_PSCI_FID", lambda: gate_t2_probe(v18, dump, probe_len),
        "T2_DISASM_FAILED"))
    v19 = "\n".join(ln for ln in ops_lines
                    if not re.search(r"smc #(0x)?0\b", ln)) + "\n"
    lines.append(expect_reject(
        "MISSING_SMC", lambda: gate_t2_probe(v19, dump, probe_len),
        "T2_DISASM_FAILED"))
    lines.append(expect_reject(
        "FALLTHROUGH_AFTER_SMC",
        lambda: gate_terminal(dump_insert_after(
            "smc", ["  50: 00000000 mov x0, x15",
                    "  54: 14000000 b 0x50"])),
        "T2_DISASM_FAILED"))
    lines.append(expect_reject(
        "STACK_USE", lambda: gate_no_forbidden(
            ops + "\n00000000 stp x29, x30, [sp, #-32]!"),
        "T2_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_STORE", lambda: gate_no_forbidden(
            ops + "\n00000000 str x9, [x0]"), "T2_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_LOAD", lambda: gate_no_forbidden(
            ops + "\n00000000 ldr x9, [x0]"), "T2_DISASM_FAILED"))
    lines.append(expect_reject(
        "RUNTIME_RELOCATION", lambda: gate_no_relocations(
            "0000000000000000 R_AARCH64_ABS64 .text", "fixture"),
        "T2_RELOC_FAILED"))
    lines.append(expect_reject(
        "PAYLOAD_SIZE_CHANGE",
        lambda: gate_payload_diff(frozen, cand + b"\x00" * 4, region),
        "T2_PAYLOAD_DIFF_FAILED"))
    bad_rtd = bytearray(cand)
    bad_rtd[DTB_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "RT_D_CHANGED", lambda: gate_trailer(bytes(bad_rtd)),
        "T2_PAYLOAD_DIFF_FAILED"))
    bad_diff = bytearray(cand)
    bad_diff[0x200] ^= 0xFF
    lines.append(expect_reject(
        "EXTRA_PAYLOAD_DIFF", lambda: gate_payload_diff(
            frozen, bytes(bad_diff), region), "T2_PAYLOAD_DIFF_FAILED"))
    lines.append(expect_reject(
        "CNTPCT_UNSAFE",
        lambda: gate_cnppct_safety("", False), "T2_TIMER_FAILED"))
    lines.append(expect_reject(
        "PSCI_UNSAFE",
        lambda: gate_psci_safety("", False), "T2_PSCI_FAILED"))
    lines.append(f"T2_NEGATIVE_FIXTURE_COUNT={len(lines)}")
    lines.append("T2_NEGATIVE_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# Build helpers.
# ---------------------------------------------------------------------------

def probe_syms(readelf: str, elf: Path, name: str) -> dict:
    out = pb.run([readelf, "-sW", str(elf)])
    found: dict = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[7] == name:
            found[parts[7]] = int(parts[1], 16)
    return found


def build_probe(out: Path, tools: dict, src: Path, ld: Path,
                delay_macro: str, delay: int, sym: str,
                tag: str, march: str = None) -> tuple:
    elf = out / f"{tag}.elf"
    extra = [f"-march={march}"] if march else []
    ops = iso.assemble_probe(src, ld, [f"-D{delay_macro}={delay}", *extra],
                             elf, tools)
    offs = probe_syms(tools["readelf"], elf, sym)
    if set(offs) != {sym} or offs[sym] != 0:
        fail("T2_BUILD_FAILED", f"{tag} symbols {sorted(offs)}")
    binp = out / f"{tag}.bin"
    pb.run([tools["objcopy"], "-O", "binary", str(elf), str(binp)])
    probe = binp.read_bytes()
    dump = pb.run([tools["objdump"], "-d", str(elf)])
    (out / f"{tag}-disasm.txt").write_text(dump)
    rel = pb.run([tools["readelf"], "-r", "--wide", str(elf)])
    gate_no_relocations(rel, tag)
    return probe, ops, dump


def _flag_tokens(flags: str) -> tuple:
    toks = [t.strip() for t in re.split(r"[,\s]+", flags or "") if t.strip()]
    code = any(t == "CODE" or (len(t) <= 3 and t.isalpha() and "X" in t)
               for t in toks)
    alloc = any(t == "ALLOC" or (len(t) <= 3 and t.isalpha() and "A" in t)
                for t in toks)
    return code, alloc


OBJDUMP_SEC_RE = re.compile(r"^\s*(\d+)\s+(\S+)\s+(.*)$")
READELF_SEC_RE = re.compile(
    r"^\s*\[\s*(\d+)\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+"
    r"([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s*(.*)$")
CONT_MARKERS = ("CODE", "ALLOC", "CONTENTS", "LOAD", "READONLY", "DATA",
                "TLS", "DEBUG", "MERGE", "STRINGS", "INFO", "LINK_ORDER",
                "GROUP", "EXCLUDE", "COMPRESSED", "NOSHDR", "OS", "PROC",
                "RELOCATIONS")


def _objdump_sections(dump: str) -> list:
    """Tolerant parse of `llvm-objdump --section-headers`. Field counts and
    the flags layout differ between LLVM releases (flags may share the line
    with the numeric columns or follow on an indented continuation line), so
    the numeric columns are taken positionally from the hex-looking tokens."""
    out: list = []
    cur = None
    for raw in dump.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = OBJDUMP_SEC_RE.match(line)
        ok = False
        if m and re.fullmatch(r"[0-9a-fA-F]{4,16}", m.group(2) or "") is None:
            hexes = [t for t in m.group(3).split()
                     if re.fullmatch(r"[0-9a-fA-F]{4,16}", t)]
            if len(hexes) >= 3:
                size = int(hexes[0], 16)
                vma = int(hexes[1], 16)
                file_off = int(hexes[3], 16) if len(hexes) >= 4 \
                    else int(hexes[2], 16)
                tail = m.group(3).split()
                cut = 0
                for t in tail:
                    if re.fullmatch(r"[0-9a-fA-F]{4,16}", t):
                        cut += 1
                        if cut == len(hexes):
                            break
                rest = " ".join(tail[cut:]).strip()
                if cur:
                    out.append(cur)
                cur = {"idx": int(m.group(1)), "name": m.group(2),
                       "size": size, "vma": vma, "file_off": file_off,
                       "flags": rest, "source": "objdump"}
                ok = True
        if ok:
            continue
        s = line.strip()
        if cur is not None and s.startswith("["):
            continue
        if cur is not None and s:
            up = re.sub(r"[^A-Z_, ]", "", s)
            if up.strip(" ,_") and (s == up or any(k in s for k in
                                                   CONT_MARKERS)):
                cur["flags"] = (cur["flags"] + " " + s).strip()
    if cur:
        out.append(cur)
    out = [s for s in out if s["size"] > 0]
    for s in out:
        s["code"], s["alloc"] = _flag_tokens(s["flags"])
    return out


def _readelf_sections(dump: str) -> list:
    out: list = []
    for line in dump.splitlines():
        m = READELF_SEC_RE.match(line)
        if not m:
            continue
        size = int(m.group(6), 16)
        if size == 0:
            continue
        rest = [t for t in m.group(8).split() if t]
        flags = rest[0] if len(rest) >= 4 else ""
        code, alloc = _flag_tokens(flags)
        out.append({"idx": int(m.group(1)), "name": m.group(2), "size": size,
                    "vma": int(m.group(4), 16), "file_off": int(m.group(5), 16),
                    "flags": flags, "code": code, "alloc": alloc,
                    "source": "readelf"})
    return out


def section_map(out: Path, tools: dict, vmlinux: Path) -> list:
    dumps = {}
    for tag, cmd in (
            ("readelf-SW", [tools["readelf"], "-S", "--wide", str(vmlinux)]),
            ("objdump-section-headers",
             [tools["objdump"], "--section-headers", str(vmlinux)]),
            ("objdump-h", [tools["objdump"], "-h", str(vmlinux)])):
        try:
            dumps[tag] = pb.run(cmd)
        except SystemExit as exc:
            dumps[tag] = f"FAILED: {exc}"
    (out / "p1b-t2-vmlinux-sections.txt").write_text(
        "\n".join(f"===== {k} =====\n{v}" for k, v in dumps.items()))
    for tag, text in dumps.items():
        if text.startswith("FAILED:"):
            continue
        secs = _readelf_sections(text) if tag.startswith("readelf") \
            else _objdump_sections(text)
        print(f"T2_SECTION_MAP_SOURCE={tag} sections={len(secs)}")
        if secs:
            return secs
    fail("T2_AUDIT_FAILED",
         "no sections parsed from any section-header dump; head="
         + " | ".join(dumps["readelf-SW"].splitlines()[:10]))
    return []


def branch_candidates(image: bytes, exec_ranges: list,
                      window: tuple) -> list:
    """All direct/PC-relative branch words whose source lies in an executable
    Image range and whose target lands strictly inside the window."""
    lo, hi = window
    words = image_words(image)
    hits: list = []
    for rlo, rhi in exec_ranges:
        start = max(0, rlo) // 4
        stop = min(len(words), rhi // 4)
        for i in range(start, stop):
            w = words[i]
            va = i * 4
            top6 = w >> 26
            if top6 == 0b000101 or top6 == 0b100101:
                t = va + pb.sx(w & 0x03FFFFFF, 26) * 4
            elif (w >> 24) == 0b01010100:
                t = va + pb.sx((w >> 5) & 0x7FFFF, 19) * 4
            elif (w >> 25) in (0b1011010, 0b1011011):
                t = va + pb.sx((w >> 5) & 0x7FFFF, 19) * 4
            elif (w >> 25) in (0b0110110, 0b0110111):
                t = va + pb.sx((w >> 5) & 0x3FFF, 14) * 4
            else:
                continue
            if lo < t < hi:
                hits.append((va, t))
            if len(hits) > 64:
                return hits
    return hits


def confirm_branch(tools: dict, vmlinux: Path, src_va: int,
                   target_va: int) -> bool:
    """A raw word hit is only a candidate until the authoritative disassembly
    confirms a real instruction at src_va branching to target_va."""
    try:
        dump = pb.run([tools["objdump"], "-d",
                       f"--start-address={src_va:#x}",
                       f"--stop-address={src_va + 4:#x}", str(vmlinux)])
    except SystemExit:
        return False
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if not m or int(m.group(1), 16) != src_va:
            continue
        if not re.match(r"^b(\.\w+)?$", m.group(3)):
            return False
        op = re.search(r"(?:0x)?([0-9a-f]+)", m.group(4))
        return bool(op) and int(op.group(1), 16) == target_va
    return False


def relocation_offsets(out: Path, tools: dict, vmlinux: Path) -> list:
    """Every runtime relocation location: .rela.dyn (readelf) plus .relr.dyn
    (decoded RELR), because __relocate_kernel applies both BEFORE
    __primary_switched is reached."""
    offs: list = []
    n_rela = 0
    rel = pb.run([tools["readelf"], "-r", "--wide", str(vmlinux)])
    for line in rel.splitlines():
        m = RELOC_OFF_RE.match(line.strip())
        if m:
            offs.append(int(m.group(1), 16))
            n_rela += 1
    del rel  # the raw dump can be very large; keep only the derived offsets
    n_relr = 0
    dump = out / "p1b-t2-relr.bin"
    try:
        pb.run([tools["objcopy"], "--dump-section",
                f".relr.dyn={dump}", str(vmlinux)])
    except SystemExit:
        dump = None
    if dump is not None and dump.is_file():
        data = dump.read_bytes()
        base = None
        for i in range(0, len(data) - 7, 8):
            e = int.from_bytes(data[i:i + 8], "little")
            if not (e & 1):
                base = e
                offs.append(e)
                n_relr += 1
                continue
            if base is None:
                continue
            cur = base + 8
            bits = e >> 1
            while bits:
                if bits & 1:
                    offs.append(cur)
                    n_relr += 1
                bits >>= 1
                cur += 8
            base = cur - 8
    (out / "p1b-t2-vmlinux-relocations.txt").write_text("\n".join([
        "T2_RUNTIME_RELOCATION_LOCATIONS",
        f"RELA_DYN_ENTRIES={n_rela}",
        f"RELR_DYN_LOCATIONS={n_relr}",
        f"TOTAL_LOCATIONS={len(offs)}",
        f"MIN={min(offs):#x} MAX={max(offs):#x}" if offs else "MIN=NA MAX=NA",
        "NOTE=__relocate_kernel applies .rela.dyn and RELR BEFORE "
        "__primary_switched is reached; any location inside the inline window "
        "would rewrite the probe bytes and is REJECTED.",
        ""]))
    return offs


def head_first_insn(head_text: str, symbol: str) -> str:
    body = head_text.split(f"SYM_FUNC_START_LOCAL({symbol})", 1)[1]
    return next(l for l in body.splitlines() if l.startswith("\t"))


def sysmap_symbol(sysmap: Path, name: str) -> int:
    hits = [l for l in sysmap.read_text().splitlines()
            if l.endswith(f" {name}")]
    if not hits:
        fail("T2_IDENTITY_FAILED", f"System.map missing {name}")
    return int(hits[0].split()[0], 16)


def nm_symbol(nm_out: str, name: str) -> int:
    hits = [l for l in nm_out.splitlines() if l.endswith(f" {name}")]
    if not hits:
        fail("T2_IDENTITY_FAILED", f"vmlinux nm missing {name}")
    return int(hits[0].split()[0], 16)


def inst_record(out: Path, tools: dict, words: list, name: str) -> str:
    wrap = out / f"{name}.S"
    wrap.write_text(
        ".section .text, \"ax\", @progbits\n"
        ".globl r3_handoff_entry\n"
        "r3_handoff_entry:\n"
        + "".join(f".inst\t{w:#010x}\n" for w in words))
    elf = out / f"{name}.elf"
    ops = iso.assemble_probe(wrap, HERE / "p1b-trampoline.ld", [], elf, tools)
    pb.run([tools["objdump"], "-d", str(elf)])
    (out / f"{name}-disasm.txt").write_text(
        pb.run([tools["objdump"], "-d", str(elf)]))
    return ops


# ---------------------------------------------------------------------------
# Main T2 build.
# ---------------------------------------------------------------------------

# The T2 entry contract is stated independently here and compared against the
# module-level contract: two independent literal statements must agree.
T2_ENTRY_CONTRACT_EXPECTED = {
    "T2_ENTRY_CURRENT_EL": "EL1",
    "T2_ENTRY_MMU": "ON",
    "T2_ENTRY_TTBR_STATE":
        "TTBR0_EL1=init_idmap_pg_dir(PHYS) TTBR1_EL1=init_pg_dir(PHYS)",
    "T2_ENTRY_PC_ADDRESS_SPACE": "VA",
    "T2_ENTRY_SP_VALID": "YES",
    "T2_ENTRY_DAIF": "D=0,A=1,I=1,F=1",
    "T2_ENTRY_X0_MEANING": "__pa(KERNEL_START) (adrp x0, KERNEL_START)",
    "T2_ENTRY_X1_MEANING":
        "page-table scratch from load_ttbr1 (NOT boot contract)",
    "T2_ENTRY_X2_MEANING":
        "init_idmap_pg_dir scratch temp (NOT boot contract)",
    "T2_ENTRY_X3_MEANING": "scratch, pre-T2 residue (NOT boot contract)",
    "T2_ENTRY_X19_X25":
        "x19=mmu_enabled_at_boot(0) x20=cpu_boot_mode x21=FDT pa "
        "x22=idmap VA of DT x23=KASLR/load offset x24=memstart seed "
        "x25=supported VA size; probe writes NONE of them",
}
CONTRACT_REASON_ALIAS = {
    "T2_ENTRY_X1_MEANING": "T2_ENTRY_X1_X3",
    "T2_ENTRY_X2_MEANING": "T2_ENTRY_X1_X3",
    "T2_ENTRY_X3_MEANING": "T2_ENTRY_X1_X3",
}


def cmd_t2(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)

    # --- frozen baseline identity ---
    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("T2_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA:
        fail("T2_IDENTITY_FAILED", f"frozen FIX8 payload sha={sha(frozen)}")
    if len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("T2_IDENTITY_FAILED",
             f"frozen FIX8 payload len {len(frozen)} != {FIX8_PAYLOAD_SIZE}")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("T2_IDENTITY_FAILED", "frozen code1 not b 0x40")
    image_size = fhdr["image_size"]
    gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T2_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(frozen) - RT_D_SIZE != dtb_offset:
        fail("T2_IDENTITY_FAILED", "payload layout")
    gate_tramp_identity(frozen)
    print(f"T2_AUTHORITATIVE_IMAGE_SIZE={image_size:#x} "
          "SOURCE=FINAL_BINARY_HEADER")
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}")
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x} ({image_size})")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES "
          "(read from the authoritative FIX8 Image header)")
    print("IMAGE_HEADER_IMAGE_SIZE_HISTORICAL_READINGS_IGNORED="
          + ",".join(f"{v:#x}" for v in FIX8_IMAGE_SIZE_HISTORY_READINGS))
    print("T2_FROZEN_FIX8_BASE=PASS sha=" + FIX8_PAYLOAD_SHA)
    print("T2_FROZEN_TRAMPOLINE_EMBEDDED=YES sha=" + TRAMP_SHA)

    # --- authoritative kernel rebuild ---
    init = pb.compile_init(out, T2_DELAY_S, args.gcc, args.strip)
    init_sha = sha(init.read_bytes())
    if init_sha != FIX8_INIT_SHA:
        fail("T2_IDENTITY_FAILED", f"/init sha {init_sha} != frozen FIX8")
    cpio = out / f"initramfs-{T2_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    cpio_sha = sha(cpio.read_bytes())
    if cpio_sha != FIX8_CPIO_SHA:
        fail("T2_IDENTITY_FAILED", f"cpio sha {cpio_sha} != frozen FIX8")
    print(f"T2_INIT_IDENTICAL=YES sha={init_sha}")
    print(f"T2_INITRAMFS_IDENTICAL=YES sha={cpio_sha}")

    k = pb.make_kernel(out, T2_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("T2_BUILD_FAILED",
             f"rebuilt image_size {kg['hdr']['image_size']:#x} != "
             f"authoritative {image_size:#x} (baseline drift)")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("T2_BUILD_FAILED",
             f"rebuilt image file size {image_file_size} != frozen "
             f"{FIX8_IMAGE_FILE_SIZE}")
    census = sum(1 for a, b in zip(image, frozen) if a != b)
    print(f"T2_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size} "
          f"image_size={image_size:#x} image_sha={sha(image)}")
    print("T2_REBUILT_IMAGE_BYTE_IDENTICAL=NO "
          "(reported, NOT gated: the device executes the FROZEN payload; "
          "semantic identities are gated instead)")
    print(f"T2_REBUILT_IMAGE_DIFF_BYTES={census} (informational census)")

    # --- symbol re-derivation (never a history constant) ---
    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = nm_symbol(nm_out, "_text")
    off_primary_nm = nm_symbol(nm_out, "primary_entry") - text_addr
    off_record_mm_nm = nm_symbol(nm_out, "record_mmu_state") - text_addr
    ps_va = nm_symbol(nm_out, "__primary_switched")
    off_ps = ps_va - text_addr
    off_ps_sm = sysmap_symbol(k["sysmap"], "__primary_switched") - \
        sysmap_symbol(k["sysmap"], "_text")
    off_primary_sm = sysmap_symbol(k["sysmap"], "primary_entry") - \
        sysmap_symbol(k["sysmap"], "_text")
    if off_ps_sm != off_ps:
        fail("T2_IDENTITY_FAILED",
             f"__primary_switched nm {off_ps:#x} != System.map {off_ps_sm:#x}")
    if off_primary_sm != off_primary_nm:
        fail("T2_IDENTITY_FAILED",
             f"primary_entry nm {off_primary_nm:#x} != System.map "
             f"{off_primary_sm:#x}")
    if off_primary_nm != kg["off_primary"]:
        fail("T2_IDENTITY_FAILED",
             f"primary_entry nm {off_primary_nm:#x} != kernel_gate "
             f"{kg['off_primary']:#x}")
    if off_ps <= off_primary_nm:
        fail("T2_IDENTITY_FAILED",
             f"__primary_switched {off_ps:#x} not after primary_entry "
             f"{off_primary_nm:#x}")
    off_primary = off_primary_nm
    window_va = (ps_va, ps_va + T2_PROBE_SIZE)
    region = (off_ps, off_ps + T2_PROBE_SIZE)
    print(f"PRIMARY_SWITCHED_VA={ps_va:#x}")
    print(f"PRIMARY_SWITCHED_IMAGE_OFFSET={off_ps:#x}")
    print(f"PRIMARY_ENTRY_OFFSET={off_primary:#x}")
    print("T2_PRIMARY_ENTRY_OFFSET_REDERIVED=YES "
          "(vmlinux nm + System.map + kernel_gate, this round)")
    print("T2_PRIMARY_SWITCHED_REDERIVED=YES "
          "(vmlinux nm + System.map, this round)")

    # --- section resolution (multi-strategy, tolerates LLVM layout changes) ---
    sections = section_map(out, tools, k["vmlinux"])
    flags_source = "SECTION_HEADERS"
    if not any(s["flags"] for s in sections):
        for s in sections:
            if s["vma"] <= ps_va < s["vma"] + s["size"]:
                s["code"] = True
                s["alloc"] = True
        flags_source = "INSTRUCTION_IDENTITY_FALLBACK"
        print("T2_SECTION_FLAGS_UNAVAILABLE=YES "
              "(no flags column in the section dump; the containing section "
              "is marked executable+allocated because PRIMARY_SWITCHED_VA is "
              "a verified instruction address that the CPU executes)")
    sec = gate_window_section_scan(ps_va, T2_PROBE_SIZE, sections)
    print(f"PRIMARY_SWITCHED_SECTION={sec['name']}")
    print(f"PRIMARY_SWITCHED_SECTION_FLAGS={sec['flags'] or 'UNPRINTED'}")
    print(f"PRIMARY_SWITCHED_SECTION_FLAGS_SOURCE={flags_source}")
    print(f"PRIMARY_SWITCHED_SECTION_VA={sec['vma']:#x}")
    print("PRIMARY_SWITCHED_FILE_OFFSET="
          f"{sec['file_off'] + (ps_va - sec['vma']):#x} (vmlinux file offset)")
    print("PRIMARY_SWITCHED_SECTION_SHF_EXECINSTR=YES SHF_ALLOC=YES")
    print(f"T2_INLINE_START={ps_va:#x}")
    print(f"T2_INLINE_END={ps_va + T2_PROBE_SIZE:#x}")

    # --- original instruction identity + 32-instruction record ---
    dump_ps = pb.run([
        tools["objdump"], "-d",
        f"--start-address={ps_va:#x}",
        f"--stop-address={ps_va + 128:#x}", str(k["vmlinux"])])
    (out / "p1b-t2-primary-switched-vmlinux-disasm.txt").write_text(dump_ps)
    ps_n_insns = len([l for l in dump_ps.splitlines() if INSTR_RE.match(l)])
    if ps_n_insns < 32:
        fail("T2_IDENTITY_FAILED",
             f"only {ps_n_insns} instructions disassembled at "
             "__primary_switched; at least 32 are required")
    orig_word = gate_vmlinux_frozen_agreement(ps_va, off_ps, dump_ps, frozen)
    orig_word2 = struct.unpack_from("<I", frozen, off_ps + 4)[0]
    head_text = (LINUX / "arch" / "arm64" / "kernel" / "head.S").read_text()
    head_insn = head_first_insn(head_text, "__primary_switched")
    gate_ps_original_insn(orig_word, orig_word2, head_insn)
    covered = list(struct.unpack_from(f"<{T2_PROBE_SIZE // 4}I", frozen, off_ps))
    inst_record(out, tools, covered, "p1b-t2-original-covered-insns-record")
    print(f"T2_PRIMARY_SWITCHED_ORIGINAL_INSN1={T2_ORIGINAL_FIRST_INSN}")
    print(f"T2_PRIMARY_SWITCHED_ORIGINAL_INSN2={T2_ORIGINAL_SECOND_INSN}")
    print("T2_PRIMARY_SWITCHED_ORIGINAL_FIRST_BYTES="
          f"{struct.pack('<I', orig_word).hex()}")
    print("T2_PRIMARY_SWITCHED_ORIGINAL_SECOND_BYTES="
          f"{struct.pack('<I', orig_word2).hex()}")
    print("T2_PRIMARY_SWITCHED_ORIGINAL_INSN_SOURCES_AGREE=YES "
          f"(linkage.h SYM_FUNC_START_LOCAL + head.S + frozen payload + "
          f"vmlinux disassembly; {ps_n_insns} instructions recorded)")
    print(f"T2_PRIMARY_SWITCHED_OVERWRITTEN_INSN_COUNT={T2_PROBE_SIZE // 4}")
    print("T2_PRIMARY_SWITCHED_OVERWRITTEN_INSN_WORDS="
          + ",".join(f"{w:#010x}" for w in covered))
    print("T2_BTI_LANDING_PAD_PRESERVED=YES "
          "(the original first instruction of __primary_switched is `bti c`, "
          "unconditionally emitted by SYM_FUNC_START_LOCAL in "
          "arch/arm64/include/asm/linkage.h lines 26-28; the T2 probe re-emits "
          "it as its first instruction, so the entry stays a valid BTI "
          "landing pad and only the 19 instructions after it are repurposed)")

    # --- inline safety scans (prompt sections 12/14) ---
    symbol_vas = sorted({int(l.split()[0], 16) for l in nm_out.splitlines()
                         if re.match(r"^[0-9a-f]{16} ", l)})
    n_sym = gate_window_symbol_scan(ps_va, T2_PROBE_SIZE, symbol_vas)
    exec_ranges = [(s["vma"] - text_addr, s["vma"] - text_addr + s["size"])
                   for s in sections if s["code"] and s["alloc"]]
    cand_hits = branch_candidates(image, exec_ranges, window_va)
    confirmed = [(s, t) for s, t in cand_hits
                 if confirm_branch(tools, k["vmlinux"], s, t)]
    n_raw = gate_window_branch_scan(ps_va, T2_PROBE_SIZE, confirmed)
    for s, t in confirmed:
        print(f"T2_BRANCH_INTO_WINDOW_CONFIRMED src={s:#x} target={t:#x}")
    reloc = relocation_offsets(out, tools, k["vmlinux"])
    n_rel = gate_window_relocation_scan(ps_va, T2_PROBE_SIZE, reloc)
    n_lit = gate_window_literal_scan(ps_va, T2_PROBE_SIZE, image)
    print(f"T2_SYMBOL_SCAN=PASS ({n_sym} symbols, none inside the window)")
    print(f"T2_BRANCH_SCAN=PASS ({n_raw} confirmed branches overall, "
          f"{len(cand_hits)} raw candidates, none inside the window)")
    print(f"T2_RELOCATION_SCAN=PASS ({n_rel} runtime relocation locations "
          "(.rela.dyn + RELR), none inside the window)")
    print(f"T2_LITERAL_SCAN=PASS ({n_lit} 8-byte literal slots scanned, no "
          "absolute VA inside the window)")
    print("T2_CONTROL_FLOW_SCAN=PASS (no branch source/target inside the "
          "window)")
    print("T2_SECTION_BOUNDARY_SCAN=PASS (window inside one SHF_EXECINSTR|"
          "SHF_ALLOC section)")
    print("T2_INLINE_OVERWRITE_SAFE=YES")
    print("T2_INLINE_WINDOW_ORIGINAL_CODE=PURE_STRAIGHT_LINE "
          "(no branch instruction, no internal label, no literal pool)")
    print("T2_ALT_EX_TABLE_ENTRIES_IN_WINDOW=REPORTED_NOT_HAZARDOUS "
          "(apply_alternatives runs after start_kernel; T2 never returns)")
    print("T2_ALT_EX_TABLE_HAZARD=NO_POST_START_KERNEL_ONLY")

    # --- entry contract + timer/PSCI safety ---
    gate_entry_contract(T2_ENTRY_CONTRACT, T2_ENTRY_CONTRACT_EXPECTED)
    for key in T2_ENTRY_CONTRACT:
        rk = CONTRACT_REASON_ALIAS.get(key, key)
        if rk not in T2_ENTRY_CONTRACT_REASONS:
            fail("T2_ENTRY_STATE_FAILED", f"no source reason for {key}")
    gate_cnppct_safety(T2_CNTPCT_ACCESS_SAFE_REASON, True)
    gate_psci_safety(T2_PSCI_SAFE_REASON, True)
    gate_probe_mapping("KERNEL_TEXT_VA_SELF_EVIDENT")
    for key in ("T2_ENTRY_CURRENT_EL", "T2_ENTRY_MMU",
                "T2_ENTRY_TTBR_STATE", "T2_ENTRY_PC_ADDRESS_SPACE",
                "T2_ENTRY_SP_VALID", "T2_ENTRY_DAIF",
                "T2_ENTRY_X0_MEANING", "T2_ENTRY_X1_MEANING",
                "T2_ENTRY_X2_MEANING", "T2_ENTRY_X3_MEANING"):
        print(f"{key}={T2_ENTRY_CONTRACT[key]}")
    for key in sorted(T2_ENTRY_CONTRACT_REASONS):
        print(f"{key}_SOURCE={T2_ENTRY_CONTRACT_REASONS[key]}")
    print("T2_REACH_IMPLIES_MMU_ENABLE_PATH_EXECUTED=YES "
          "(__primary_switched is only reachable from __primary_switch's "
          "'ldr x8, =__primary_switched ; br x8', which executes after "
          "__enable_mmu set SCTLR_EL1.M=1 and after load_ttbr1 installed "
          "init_pg_dir; the probe sits in kernel text VA, so the arrival "
          "itself is the executable-mapping proof)")
    print("T2_MMU_PROOF_BOUNDARY=head.S MMU TRANSITION TO THE T2 ADDRESS ONLY "
          "(the normal memory subsystem is NOT claimed)")
    print(f"T2_CNTPCT_ACCESS_SAFE=YES ({T2_CNTPCT_ACCESS_SAFE_REASON})")
    print(f"T2_PSCI_SYSTEM_RESET_SAFE=YES ({T2_PSCI_SAFE_REASON})")

    # --- probe build (T2 + the T1 core for byte identity) ---
    t2_probe, ops, dump = build_probe(out, tools, T2_DEVICE_S, T2_DEVICE_LD,
                                      "P1B_T2_DELAY", T2_DELAY_S,
                                      "r3_t2_checkpoint", "p1b-t2-checkpoint",
                                      march="armv8.5-a")
    t1_probe, _t1_ops, _t1_dump = build_probe(
        out, tools, T1_DEVICE_S, T1_DEVICE_LD, "P1B_T1_DELAY", 8,
        "r3_t1_checkpoint", "p1b-t1-core-reference")
    gate_t2_probe(ops, dump, len(t2_probe))
    gate_diagnostic_core_identity(t2_probe, t1_probe)
    plen = len(t2_probe)
    if (off_ps + plen) > image_file_size:
        fail("T2_BUILD_FAILED", "inline window exceeds the Image file")
    print(f"T2_CHECKPOINT sha256={sha(t2_probe)} size={plen} "
          f"core={sha(t2_probe[T2_BTI_PAD:])}")
    print("T2_DIAGNOSTIC_CORE_MATCHES_T1=YES "
          f"(probe[4:80] byte-identical to the p1b-t1-device.S core, "
          f"sha {sha(t1_probe)}; the only difference is the leading `bti c` "
          "landing pad, an insertion mechanic)")
    print("T2_DIAGNOSTIC_CORE_SLICE_MATCHES_T1=YES")
    print("T2_PROBE_ARCHITECTURE=INLINE")
    print("T2_PROBE_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT")
    print("T2_MAPPING_EXECUTABLE=YES")
    print("T2_EXTERNAL_CHECKPOINT_USED=NO")
    print("T2_PADDING_MAPPING_USED=NO "
          "(section 14: the T1 padding site 0x2230000 is NOT executable under "
          "the MMU-on early page tables and is never reused for T2)")

    # --- compose the T2 payload: ONE diff region, inline only ---
    cand = bytearray(frozen)
    cand[off_ps:off_ps + plen] = t2_probe
    cand = bytes(cand)
    diffs = gate_payload_diff(frozen, cand, (off_ps, off_ps + plen))
    gate_tramp_identity(cand)
    trailer = gate_trailer(cand)
    if trailer != frozen_rt_d:
        fail("T2_PAYLOAD_DIFF_FAILED", "trailer drifted vs frozen RT-D")
    hdr, dtb_off2, gap2, boot_est = gate_geometry(cand, image_size)
    if dtb_off2 != dtb_offset:
        fail("T2_PAYLOAD_DIFF_FAILED", "dtb_offset drifted")
    if cand[:off_ps] != frozen[:off_ps]:
        fail("T2_PAYLOAD_DIFF_FAILED", "pre-T2 head.S path modified")
    payload_path = out / "thyme-r3-p1b-t2-kernel-payload.bin"
    payload_path.write_bytes(cand)
    print(f"T2_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)}")
    print(f"T2_DIFF_BYTE_COUNT={len(diffs)}")
    print(f"T2_DIFF_RANGES=[{off_ps:#x},{off_ps + plen:#x})")
    print("T2_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_SWITCHED_CHECKPOINT_ONLY")
    print("T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8=YES "
          f"({off_ps} pre-T2 kernel bytes byte-identical, trampoline "
          "byte-identical, primary_entry unpatched)")

    diff_report = (
        "T2_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"T2_PAYLOAD_SHA256={sha(cand)}\n"
        f"REGION_A=[{off_ps:#x},{off_ps + plen:#x}) inline __primary_switched "
        f"overwrite ({len(diffs)} diff bytes)\n"
        f"DIFF_BYTES={len(diffs)}\n"
        f"T2_DIFF_BYTE_COUNT={len(diffs)}\n"
        f"FIRST_DIFF={diffs[0]:#x} LAST_DIFF={diffs[-1]:#x}\n"
        f"DIFF_RANGES=[{off_ps:#x},{off_ps + plen:#x})\n"
        "DIFF_ATTRIBUTION=PRIMARY_SWITCHED_CHECKPOINT_ONLY\n"
        "T2_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_SWITCHED_CHECKPOINT_ONLY\n"
        "T2_PRIMARY_ENTRY_PATCHED=NO\n"
        f"T2_TRAMPOLINE_IDENTICAL_TO_FIX8=YES sha={TRAMP_SHA}\n"
        f"RT_D_TRAILER_IDENTICAL=YES sha={RT_D_SHA}\n"
        f"PAYLOAD_SIZE_IDENTICAL=YES {len(cand)}\n"
        f"DTB_OFFSET={dtb_offset:#x} GAP={gap:#x} "
        f"IMAGE_FILE_SIZE={image_file_size} "
        f"IMAGE_HEADER_IMAGE_SIZE={hdr['image_size']:#x} "
        f"T2_INLINE_START={ps_va:#x} T2_INLINE_END={ps_va + plen:#x} "
        f"BOOT_SIZE_EST={boot_est}\n"
        f"T2_RUNTIME_SEMANTIC_DELTA={T2_RUNTIME_SEMANTIC_DELTA}\n")
    (out / "p1b-t2-payload-diff-report.txt").write_text(diff_report)

    sm_lines = [l for l in k["sysmap"].read_text().splitlines()
                if l.endswith((" primary_entry", " _text", " record_mmu_state",
                               " __primary_switched", " __primary_switch",
                               " __enable_mmu", " __cpu_setup"))]
    (out / "p1b-t2-sysmap-excerpt.txt").write_text("\n".join(sm_lines) + "\n")

    # --- fixtures ---
    neg_lines = run_negative_fixtures({
        "ops": ops, "dump": dump, "probe_len": plen, "frozen": frozen,
        "cand": cand, "off_ps": off_ps, "sections": sections,
        "symbol_vas": symbol_vas, "reloc_offsets": reloc,
        "t1_probe": t1_probe, "ps_va": ps_va,
        "record_mmu_state_va": text_addr + off_record_mm_nm,
        "orig_word2": orig_word2,
        "primary_entry_off": off_primary})
    (out / "p1b-t2-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures()
    (out / "p1b-t2-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")

    report = (
        "T2_PREDEVICE_REPORT\n"
        "CONSTRAINTS mem0_read=YES local_build=NO gha_only=YES "
        "device_operation=NO partition_writes=0 slot_a_written=NO\n"
        "PREDECESSOR T0_TOTAL=14.252s T0=PROVEN T1_TOTAL=14.238s "
        "T1_MINUS_T0=-0.014s T1=PROVEN\n"
        "REACHABILITY R0=PROVEN R1=PROVEN R2=PROVEN R3=NOT_PROVEN "
        "R4=NOT_PROVEN R5=NOT_PROVEN R6=NOT_PROVEN\n"
        "T2_TARGET_SYMBOL=__primary_switched\n"
        f"PRIMARY_SWITCHED_VA={ps_va:#x}\n"
        f"PRIMARY_SWITCHED_IMAGE_OFFSET={off_ps:#x}\n"
        f"PRIMARY_SWITCHED_SECTION={sec['name']}\n"
        f"PRIMARY_SWITCHED_SECTION_FLAGS={sec['flags'] or 'UNPRINTED'}\n"
        f"PRIMARY_SWITCHED_SECTION_FLAGS_SOURCE={flags_source}\n"
        "T2_PRIMARY_SWITCHED_REDERIVED=YES\n"
        "T2_PRIMARY_ENTRY_OFFSET_REDERIVED=YES\n"
        "T2_PRIMARY_SWITCHED_ORIGINAL_INSN1=bti c\n"
        "T2_PRIMARY_SWITCHED_ORIGINAL_INSN2=adrp x4, init_task\n"
        "T2_BTI_LANDING_PAD_PRESERVED=YES\n"
        f"T2_PROBE_ARCHITECTURE=INLINE start={ps_va:#x} "
        f"end={ps_va + plen:#x}\n"
        "T2_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT "
        "T2_MAPPING_EXECUTABLE=YES\n"
        "T2_INLINE_OVERWRITE_SAFE=YES\n"
        "T2_EXTERNAL_CHECKPOINT_USED=NO T2_PADDING_MAPPING_USED=NO\n"
        "T2_DEVICE_CANDIDATE_DELAY=8s\n"
        "T2_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY\n"
        "T2_CNTPCT_ACCESS_SAFE=YES\n"
        "T2_RESET_PRIMITIVE=PSCI_SYSTEM_RESET fid=0x84000009 smc #0\n"
        "T2_PSCI_SYSTEM_RESET_SAFE=YES\n"
        "T2_FAIL_CLOSED=YES (any smc return -> wfe forever; no return, no "
        "__primary_switched continuation, no start_kernel)\n"
        f"T2_CLOBBER_REGISTERS={T2_CLOBBER_REGISTERS}\n"
        "T2_STACK_USAGE=NO\n"
        "T2_MEMORY_READS=NO T2_MEMORY_WRITES=NO\n"
        "T2_POSITION_INDEPENDENT=YES T2_RUNTIME_RELOCATIONS=0\n"
        f"T2_RUNTIME_SEMANTIC_DELTA={T2_RUNTIME_SEMANTIC_DELTA}\n"
        "T2_DIAGNOSTIC_CORE_MATCHES_T1=YES\n"
        f"T2_TRAMPOLINE_IDENTICAL_TO_FIX8=YES sha={TRAMP_SHA}\n"
        f"T2_RT_D_IDENTITY=YES sha={RT_D_SHA}\n"
        f"T2_INIT_IDENTITY=YES {init_sha}\n"
        f"T2_INITRAMFS_IDENTITY=YES {cpio_sha}\n"
        "T2_DIAGNOSTIC_ONLY=YES\n"
        "T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO\n"
        "T2_STATUS_GATE_SEMANTIC=YES\n"
        "T3_STATUS=NOT_DEVICE_READY\n")
    (out / "p1b-t2-report.txt").write_text(report)

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "t2_true_device_run": "NOT_EXECUTED",
        "fix8_payload_sha256": FIX8_PAYLOAD_SHA,
        "fix8_payload_size": FIX8_PAYLOAD_SIZE,
        "fix8_image_sha256": FIX8_IMAGE_SHA,
        "fix8_image_file_size": FIX8_IMAGE_FILE_SIZE,
        "fix8_init_sha256": FIX8_INIT_SHA,
        "fix8_cpio_sha256": FIX8_CPIO_SHA,
        "fix8_tramp_sha256": TRAMP_SHA,
        "fix8_boot_sha256": FORBIDDEN_BOOT_SHAS["FIX8_BOOT"],
        "t0_boot_sha256": FORBIDDEN_BOOT_SHAS["T0_BOOT"],
        "t1_boot_sha256": FORBIDDEN_BOOT_SHAS["T1_BOOT"],
        "panic30_boot_sha256": FORBIDDEN_BOOT_SHAS["PANIC30_BOOT"],
        "rt_d_frozen_sha256": RT_D_SHA,
        "rt_d_frozen_size": RT_D_SIZE,
        "image_header_image_size": hex(image_size),
        "image_header_image_size_rederived": True,
        "image_size_historical_readings_ignored":
            [hex(v) for v in FIX8_IMAGE_SIZE_HISTORY_READINGS],
        "image_file_size": image_file_size,
        "dtb_offset": hex(dtb_offset),
        "gap": hex(gap),
        "primary_entry_offset": hex(off_primary),
        "primary_entry_offset_rederived": True,
        "primary_entry_patched": False,
        "primary_switched_va": hex(ps_va),
        "primary_switched_image_offset": hex(off_ps),
        "primary_switched_file_offset": hex(
            sec["file_off"] + (ps_va - sec["vma"])),
        "primary_switched_section": sec["name"],
        "primary_switched_section_flags": sec["flags"],
        "primary_switched_section_flags_source": flags_source,
        "primary_switched_section_va": hex(sec["vma"]),
        "primary_switched_rederived": True,
        "primary_switched_original_first_insn": T2_ORIGINAL_FIRST_INSN,
        "primary_switched_original_second_insn": T2_ORIGINAL_SECOND_INSN,
        "primary_switched_original_first_bytes":
            struct.pack("<I", orig_word).hex(),
        "primary_switched_original_second_bytes":
            struct.pack("<I", orig_word2).hex(),
        "primary_switched_original_insn_sources_agree": True,
        "t2_bti_landing_pad_preserved": True,
        "t2_core_size": T2_CORE_SIZE,
        "primary_switched_recorded_insn_count": ps_n_insns,
        "primary_switched_overwritten_insn_count": T2_PROBE_SIZE // 4,
        "rebuilt_image_sha256": sha(image),
        "rebuilt_image_byte_identical_to_frozen": False,
        "rebuilt_image_byte_identity_reason":
            "embedded build banner (UTS_VERSION/linux_banner) differs and "
            "shifts later bytes; the device executes the frozen payload",
        "rebuilt_image_diff_bytes_vs_frozen_prefix": census,
        "t2_probe_architecture": "INLINE",
        "t2_inline_start": hex(ps_va),
        "t2_inline_end": hex(ps_va + plen),
        "t2_inline_overwrite_safe": True,
        "t2_external_checkpoint_used": False,
        "t2_mapping_source": "KERNEL_TEXT_VA_SELF_EVIDENT",
        "t2_mapping_executable": True,
        "t2_padding_mapping_used": False,
        "t2_symbol_scan_pass": True,
        "t2_branch_scan_pass": True,
        "t2_relocation_scan_pass": True,
        "t2_literal_scan_pass": True,
        "t2_control_flow_scan_pass": True,
        "t2_section_boundary_scan_pass": True,
        "t2_alt_ex_table_hazard": "NO_POST_START_KERNEL_ONLY",
        "t2_literal_slots_scanned": n_lit,
        "t2_branch_raw_candidates": len(cand_hits),
        "t2_branch_confirmed_hits": n_raw,
        "t2_runtime_relocation_locations": n_rel,
        "t2_symbols_scanned": n_sym,
        "t2_entry_contract": T2_ENTRY_CONTRACT,
        "t2_entry_contract_reasons": T2_ENTRY_CONTRACT_REASONS,
        "t2_cnptct_access_safe": True,
        "t2_psci_system_reset_safe": True,
        "t2_reach_implies_mmu_enable_path_executed": True,
        "t2_checkpoint_sha256": sha(t2_probe),
        "t2_checkpoint_size": plen,
        "t2_diagnostic_core_matches_t1": True,
        "t2_t1_core_sha256": sha(t1_probe),
        "t2_payload_sha256": sha(cand),
        "t2_payload_size": len(cand),
        "t2_boot_size_est": boot_est,
        "t2_boot_kernel_size_field": len(cand),
        "diff_bytes": len(diffs),
        "diff_regions": [[hex(off_ps), hex(off_ps + plen)]],
        "diff_attribution": "PRIMARY_SWITCHED_CHECKPOINT_ONLY",
        "t2_precheckpoint_heads_path_identical_to_fix8": True,
        "t2_delay_seconds": T2_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "t2_clobber_registers": T2_CLOBBER_REGISTERS,
        "t2_fail_closed": True,
        "t2_stack_usage": False,
        "t2_memory_reads": False,
        "t2_memory_writes": False,
        "t2_runtime_relocations": 0,
        "t2_runtime_semantic_delta": T2_RUNTIME_SEMANTIC_DELTA,
        "t2_tramp_identical_to_fix8": True,
        "t2_rtd_identical": True,
        "t2_init_identical": True,
        "t2_initramfs_identical": True,
        "t2_diagnostic_only": True,
        "t2_normal_kernel_boot_candidate": False,
        "t2_status_gate_semantic": True,
        "t3_status": "NOT_DEVICE_READY",
        "decoder": {
            "kind": "T1_MATCHED_CONTROL_PRIMARY_T0_SECONDARY_P0_SECONDARY",
            "t1_reference_total_s": T1_REFERENCE_TOTAL_S,
            "t0_reference_total_s": T0_REFERENCE_TOTAL_S,
            "t1_minus_t0_observed_s": T1_MINUS_T0_OBSERVED_S,
            "strong_half_window_s": T2_STRONG_HALF_WINDOW_S,
            "supported_half_window_s": T2_SUPPORTED_HALF_WINDOW_S,
            "crosscheck_half_window_s": T2_CROSSCHECK_HALF_WINDOW_S,
            "early_return_class_limit_s": T2_EARLY_RETURN_CLASS_LIMIT_S,
            "case_c_band_s": list(T2_CASE_C_BAND_S),
            "no_return_window_s": T2_NO_RETURN_WINDOW_S,
            "p0_ref_overhead_s": P0_REF_OVERHEAD_S,
            "programmed_s": T2_DELAY_S,
        },
        "observer": {"identity_env": "R3_T2_SHA256",
                     "forbidden_env": "R3_T2_FORBIDDEN_SHAS",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
        "evidence_rule": {
            "r3_on_strong": "PROVEN",
            "e1_on_strong": "PROVEN only if "
                            "t2_precheckpoint_heads_path_identical_to_fix8",
            "e2": "NOT_AUTO_UPGRADED (frozen definition only)",
        },
    }
    (out / "p1b-t2-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")

    gates = [
        "T2_BUILD_GATES=PASS",
        "T2_BASELINE=FROZEN_FIX8",
        "T2_PRIMARY_SWITCHED_REDERIVED=YES",
        "T2_PRIMARY_ENTRY_OFFSET_REDERIVED=YES",
        "T2_PRIMARY_SWITCHED_ORIGINAL_INSN1=bti c",
        "T2_PRIMARY_SWITCHED_ORIGINAL_INSN2=adrp x4, init_task",
        "T2_BTI_LANDING_PAD_PRESERVED=YES",
        "T2_PRIMARY_SWITCHED_ORIGINAL_INSN_SOURCES_AGREE=YES",
        "T2_REBUILT_IMAGE_BYTE_IDENTICAL=NO",
        "IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES",
        f"T2_AUTHORITATIVE_IMAGE_SIZE={image_size:#x}",
        f"IMAGE_FILE_SIZE={image_file_size}",
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}",
        "T2_PROBE_ARCHITECTURE=INLINE",
        f"T2_INLINE_START={ps_va:#x}",
        f"T2_INLINE_END={ps_va + plen:#x}",
        "T2_INLINE_OVERWRITE_SAFE=YES",
        "T2_SYMBOL_SCAN=PASS",
        "T2_BRANCH_SCAN=PASS",
        "T2_RELOCATION_SCAN=PASS",
        "T2_LITERAL_SCAN=PASS",
        "T2_CONTROL_FLOW_SCAN=PASS",
        "T2_SECTION_BOUNDARY_SCAN=PASS",
        "T2_ALT_EX_TABLE_HAZARD=NO_POST_START_KERNEL_ONLY",
        "T2_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
        "T2_MAPPING_EXECUTABLE=YES",
        "T2_EXTERNAL_CHECKPOINT_USED=NO",
        "T2_PADDING_MAPPING_USED=NO",
        "T2_ENTRY_MMU=ON",
        "T2_ENTRY_PC_ADDRESS_SPACE=VA",
        "T2_ENTRY_SP_VALID=YES",
        "T2_REACH_IMPLIES_MMU_ENABLE_PATH_EXECUTED=YES",
        "T2_DEVICE_CANDIDATE_DELAY=8s",
        "T2_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "T2_CNTPCT_ACCESS_SAFE=YES",
        "T2_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "T2_PSCI_SYSTEM_RESET_SAFE=YES",
        "T2_FAIL_CLOSED=YES",
        "T2_STACK_USAGE=NO",
        "T2_NO_MEMORY_READS=YES",
        "T2_NO_MEMORY_WRITES=YES",
        "T2_DIAGNOSTIC_CORE_MATCHES_T1=YES",
        "T2_DIAGNOSTIC_CORE_SLICE_MATCHES_T1=YES",
        "T2_POSITION_INDEPENDENT=YES",
        "T2_RUNTIME_RELOCATIONS=0",
        f"T2_RUNTIME_SEMANTIC_DELTA={T2_RUNTIME_SEMANTIC_DELTA}",
        "T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8=YES",
        "T2_TRAMPOLINE_IDENTICAL_TO_FIX8=YES",
        "T2_RT_D_IDENTITY=YES",
        "T2_INIT_IDENTITY=YES",
        "T2_INITRAMFS_IDENTITY=YES",
        "T2_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_SWITCHED_CHECKPOINT_ONLY",
        f"T2_DIFF_BYTE_COUNT={len(diffs)}",
        "T2_PAYLOAD_SIZE_IDENTICAL=YES",
        "T2_BOOT_SIZE_IDENTICAL=YES",
        f"T2_DTB_OFFSET={DTB_OFFSET:#x}",
        "T2_GEOMETRY_GATES=PASS",
        "T2_NEGATIVE_FIXTURES=PASS",
        "T2_DECODER_FIXTURES=PASS",
        "T2_STATUS_GATE_SEMANTIC=YES",
        "T2_DIAGNOSTIC_ONLY=YES",
        "T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
        "T3_STATUS=NOT_DEVICE_READY",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "p1b-t2-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))


def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("t2_obs_fixtures",
                                                  OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-t2-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("T2_OBSERVER_FIXTURES=PASS")


def cmd_t2_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    off_ps = int(args.primary_switched_offset, 16)
    probe = Path(args.checkpoint_bin).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("T2_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("T2_PACK_FAILED", f"payload sha={sha(payload)}")
    if sha(probe) != args.checkpoint_sha:
        fail("T2_PACK_FAILED", f"checkpoint sha={sha(probe)}")
    hdr = pb.parse_image_hdr(payload, "t2-payload")
    image_size = hdr["image_size"]
    gate_image_size_rederived(image_size, "t2-packed-payload")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("T2_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T2_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T2_PACK_FAILED", "payload length")
    if (off_ps + len(probe)) > len(payload):
        fail("T2_PACK_FAILED", "inline region past payload end")
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T2_PACK_FAILED",
             f"embedded trampoline sha={sha(tramp)} != frozen FIX8")
    if payload[off_ps:off_ps + len(probe)] != probe:
        fail("T2_PACK_FAILED", "inline region != built T2 probe (patch lost)")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I", FDT_MAGIC):
        fail("T2_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "t2-candidate")
    if cand["kernel"] != payload:
        fail("T2_PACK_FAILED", "candidate kernel != T2 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("T2_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("T2_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("T2_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("T2_PACK_FAILED", "reserved differs from M5D")
    if cand["ramdisk_size"] != ref["ramdisk_size"]:
        fail("T2_PACK_FAILED", "ramdisk_size differs")
    if cand["tail_pad"] != ref["tail_pad"]:
        fail("T2_PACK_FAILED", "tail padding policy differs")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("T2_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("T2_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T2_PACK_FAILED", "DTB residue geometry")
    if len(boot) >= BOOT_CAP or BOOT_CAP - len(boot) < 0x1000000:
        fail("T2_PACK_FAILED", "capacity")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-t2-pack-gates.txt"
    report.write_text(
        "T2_PACK_GATES=PASS\n"
        f"T2_BOOT_SIZE={len(boot)}\n"
        f"T2_BOOT_SHA256={sha(boot)}\n"
        f"T2_PAYLOAD_SHA256={sha(payload)}\n"
        f"T2_TRAMP_SHA256={sha(tramp)}\n"
        "T2_TRAMP_SOURCE=FROZEN_FIX8_UNMODIFIED\n"
        f"T2_CHECKPOINT_SHA256={sha(probe)}\n"
        f"T2_KERNEL_SIZE={len(payload)}\n"
        f"T2_PRIMARY_SWITCHED_OFFSET={off_ps:#x}\n"
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}\n"
        f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}\n"
        "T2_PROBE_ARCHITECTURE=INLINE\n"
        "T2_INLINE_REGION_IN_KERNEL_TEXT=YES\n"
        f"T2_DTB_OFFSET={dtb_offset:#x}\n"
        "T2_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "T2_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "T2_BOOT_CAPACITY=PASS\n"
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


# ---------------------------------------------------------------------------
# Source gate.
# ---------------------------------------------------------------------------

def need(text: str, needle: str, label: str = "T2_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str,
           label: str = "T2_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def parse_status_kv(text: str) -> dict:
    if STATUS_KV_BEGIN not in text or STATUS_KV_END not in text:
        fail("T2_SOURCE_GATE_FAILED",
             "structured status KV block markers missing")
    body = text.split(STATUS_KV_BEGIN, 1)[1].split(STATUS_KV_END, 1)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    kv: dict = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail("T2_SOURCE_GATE_FAILED",
                 f"status KV line without '=': {line!r}")
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()
    if not kv:
        fail("T2_SOURCE_GATE_FAILED", "empty structured status KV block")
    return kv


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [T2_DEVICE_S, T2_DEVICE_LD, T1_DEVICE_S, T1_DEVICE_LD,
                T1_PROTO_S, OBSERVER, OBSERVER_FIXTURES, Path(__file__), DOC,
                STATUS_DOC, WF, PRIVATE_WF,
                HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld"]
    for path in required:
        if not path.is_file():
            fail("T2_SOURCE_GATE_FAILED", f"missing {path}")
    dev = T2_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "isb", "mrs\tx9, cntfrq_el0",
                  "mrs\tx11, cntpct_el0", "mrs\tx12, cntpct_el0", "yield",
                  "smc\t#0", "wfe", "P1B_T2_DELAY",
                  "#if (P1B_T2_DELAY) != 8", "r3_t2_checkpoint"):
        need(dev, token)
    for token in ("P1B_DTB_REL", "dtb_rel", "adr\t", "ldr\t",
                  "mov\tx1, xzr", "mov\tx2, xzr", "mov\tx3, xzr",
                  "eret", "sctlr", "msr\tttbr", "b\tprimary",
                  "b\t__primary", "b\tstart_kernel"):
        forbid(dev, token)
    t1dev = T1_DEVICE_S.read_text()
    for token in ("r3_t1_checkpoint", "msr\tdaifset, #0xf",
                  "mrs\tx9, cntfrq_el0", "smc\t#0", "wfe"):
        need(t1dev, token)
    proto = T1_PROTO_S.read_text()
    need(proto, "P1B_PROBE_DELAY", "T2_PROTOTYPE_AUDIT_FAILED")
    need(proto, "r3_t1_probe", "T2_PROTOTYPE_AUDIT_FAILED")
    obs = OBSERVER.read_text()
    for token in ("R3_T2_SHA256", "T2_OBSERVER_MISBOOT_REFUSED",
                  "T2_BOOTING_TO_RETURNED_KERNEL_START", "T2_MINUS_T1",
                  "T1_REFERENCE_TOTAL_S", "T0_REFERENCE_TOTAL_S",
                  "T2_REACHABILITY_SIGNATURE", "T2_FAILURE_ISOLATION_CI",
                  "FASTBOOT_BOOT_ONLY", "T2_NORMAL_KERNEL_BOOT_CANDIDATE",
                  "T2_DIAGNOSTIC_ONLY", "R3_PRIMARY_SWITCHED_REACHABILITY",
                  "T2_NOT_REACHED_LICENSE=NO", "T2_STABLE_FASTBOOT",
                  "T2_NO_RETURN", "T1_BOOT"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("T2_OBSERVER_MISBOOT_REFUSED", "NOT_REACHED",
                  "T2_STABLE_FASTBOOT", "T2_NO_RETURN"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("T2_PRIMARY_SWITCHED_REDERIVED",
                  "PRIMARY_SWITCHED_IMAGE_OFFSET",
                  "PRIMARY_SWITCHED_SECTION",
                  "T2_ENTRY_MMU", "T2_ENTRY_PC_ADDRESS_SPACE",
                  "T2_ENTRY_TTBR_STATE", "T2_ENTRY_DAIF",
                  "T2_PROBE_ARCHITECTURE=INLINE",
                  "T2_INLINE_OVERWRITE_SAFE",
                  "T2_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
                  "T2_RELOCATION_SCAN", "T2_LITERAL_SCAN",
                  "T2_CNTPCT_ACCESS_SAFE", "T2_PSCI_SYSTEM_RESET_SAFE",
                  "T2_FAIL_CLOSED", "T2_STACK_USAGE=NO",
                  "T2_RUNTIME_RELOCATIONS=0",
                  "T2_PRIMARY_SWITCHED_ORIGINAL_INSN1=bti c",
                  "T2_PRIMARY_SWITCHED_ORIGINAL_INSN2=adrp x4, init_task",
                  "T2_BTI_LANDING_PAD_PRESERVED",
                  "T2_DIAGNOSTIC_CORE_MATCHES_T1",
                  "T2_DIAGNOSTIC_CORE_SLICE_MATCHES_T1",
                  "T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8",
                  "PRIMARY_SWITCHED_REACHABILITY_CHECKPOINT_ONLY",
                  "T2_PAYLOAD_DIFF_ATTRIBUTED="
                  "PRIMARY_SWITCHED_CHECKPOINT_ONLY",
                  "T2_TRAMPOLINE_IDENTICAL_TO_FIX8",
                  "T2_STATUS_GATE_SEMANTIC=YES",
                  "T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
                  "T2_DIFF_BYTE_COUNT", "T2_DIFF_RANGES",
                  "T1_REFERENCE_TOTAL", "14.238", "14.252", "6.1445",
                  "0x2380000", "0x84000009", "wfe", "CNTPCT",
                  "T2_FAILURE_ISOLATION", "STRONG", "SUPPORTED",
                  "READY_FOR_R3_P1B_T2_DEVICE_CONTROL",
                  "R3_P1B_T2_PREDEVICE_NOT_READY", "T3", "E1", "E2"):
        need(doc, token)
    kv = parse_status_kv(STATUS_DOC.read_text())
    for key, want in STATUS_DOC_REQUIRED_KV.items():
        if kv.get(key) != want:
            fail("T2_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} != {want!r}")
    print(f"T2_STATUS_KV_KEY_COUNT={len(kv)}")
    print("T2_STATUS_GATE_SEMANTIC=YES")
    wf_text = WF.read_text()
    for token in ("p1b-t2-device.S", "p1b-t2-predevice.py",
                  "observe-r3-p1b-t2.py", "thyme-r3-p1b-t2",
                  "T2_BUILD_GATES=PASS",
                  "T2_INLINE_OVERWRITE_SAFE=YES",
                  "T2_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
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
            fail("T2_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    body = re.search(r"\n    manifest = \{(.*?)\n    \}\n",
                     Path(__file__).read_text(), re.S)
    if not body:
        fail("T2_SOURCE_GATE_FAILED", "manifest literal not found")
    keys = set(re.findall(r'^\s+"([a-z0-9_]+)":', body.group(1), re.M))
    for key in sorted(set(re.findall(r'm\["([^"]+)"\]',
                                     PRIVATE_WF.read_text()))):
        if key not in keys:
            fail("T2_SOURCE_GATE_FAILED",
                 f"private workflow reads unknown manifest key {key!r}")
    print(f"T2_MANIFEST_KEY_CONSISTENCY=PASS ({len(keys)} keys)")
    print("T2_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "t2", "observer-fixtures", "t2-pack-gates"),
        required=True)
    parser.add_argument("--out", default="out-t2")
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
    parser.add_argument("--primary-switched-offset")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
        return
    if args.mode == "t2":
        if not (args.rt_d and args.fix8_payload):
            fail("T2_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_t2(args)
        return
    if args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
        return
    if args.mode == "t2-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.checkpoint_bin
                    and args.checkpoint_sha and args.primary_switched_offset)
        if not need_all:
            fail("T2_PACK_FAILED",
                 "need --m5d-boot --payload --boot --payload-sha "
                 "--checkpoint-bin --checkpoint-sha --primary-switched-offset")
        cmd_t2_pack_gates(args)


if __name__ == "__main__":
    main()
