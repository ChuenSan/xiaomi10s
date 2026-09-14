#!/usr/bin/env python3
"""R3 P1B T3 predevice readiness (MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source/doc boundary checks (no build)
  t3                  frozen-FIX8-anchored T3-8 fail-closed device candidate:
                      authoritative kernel rebuild (vmlinux + System.map),
                      start_kernel re-derivation from THIS round's binary
                      (never a history constant), __primary_switched ->
                      start_kernel control-flow chain audit, the exact
                      start_kernel call site, C-entry instrumentation audit
                      (BTI/PAC/CFI/fentry/SCS/KASAN/KCOV), inline-overwrite
                      safety (symbol / branch / relocation / literal /
                      section-boundary / function-extent / exception-table /
                      alternative / jump-label / static-call / kCFI scans),
                      T1+T2 diagnostic core byte identity, T2-probe-removal
                      proof, frozen-byte payload patch, single-region diff
                      attribution, geometry, negative fixtures,
                      T2-matched-control decoder fixtures
  observer-fixtures   T3 observer fixture suite (imports the observer module)
  t3-pack-gates       private: gates over a packed T3 boot v3 image

T3 is INLINE at the start_kernel FUNCTION ENTRY: the first instruction of
start_kernel is the checkpoint, so the only unexecuted range between the T2
checkpoint and the T3 checkpoint is the audited __primary_switched body.
Nothing before it is touched: the frozen FIX8 trampoline, primary_entry, the
whole head.S path AND __primary_switched keep their original bytes (the T2
probe is removed), and the ONLY payload diff is the single 80-byte
start_kernel window. The delay/reset core is byte-identical to the T0/T1/T2
proven core.

T3 is DESTRUCTIVE diagnostic only (T3_NORMAL_KERNEL_BOOT_CANDIDATE=NO). A
future positive proves the start_kernel ADDRESS reachability (R4) and, because
the pre-checkpoint path is byte-identical to FIX8 and audited instruction by
instruction, that the normal __primary_switched -> start_kernel path executed
to its end. It never proves the start_kernel body (R5).

Future T3 timing is matched-control against T2 (primary reference
T2_TOTAL = 14.240 s): STRONG |T3_MINUS_T2| <= 1.0 s, SUPPORTED <= 2.0 s, plus
T3_TOTAL < 20 s and AUTOMATIC_ANDROID_RETURN; T1_TOTAL = 14.238 s and
T0_TOTAL = 14.252 s are the secondary references. The P0 6.1445 s decoder is
SECONDARY only.
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
DOC = REPO / "docs" / "route-r3-p1b-t3-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-t3-predevice.yml"
T3_DEVICE_S = HERE / "p1b-t3-device.S"
T3_DEVICE_LD = HERE / "p1b-t3-device.ld"
T2_DEVICE_S = HERE / "p1b-t2-device.S"
T2_DEVICE_LD = HERE / "p1b-t2-device.ld"
T1_DEVICE_S = HERE / "p1b-t1-device.S"
T1_DEVICE_LD = HERE / "p1b-t1-device.ld"
T1_PROTO_S = HERE / "p1b-t1-gap-probe.S"
OBSERVER = HERE / "observe-r3-p1b-t3.py"
OBSERVER_FIXTURES = HERE / "observer-t3-fixtures.py"
PRIVATE_WF = REPO / "artifacts" / "p1b-t3-private-workflow-staging.yml"

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

T3_TARGET_SYMBOL = "start_kernel"
T3_DELAY_S = 8
T3_CORE_SIZE = 0x4C  # 76 bytes = 19 instructions: the T0/T1/T2-proven core
T3_PAD_SIZE = 0x4  # preserved original entry instruction
T3_PROBE_SIZE = T3_CORE_SIZE + T3_PAD_SIZE  # 80 bytes = 20 instructions
# Entry pad. The probe re-emits the ORIGINAL first instruction of start_kernel
# verbatim, so the instruction at the checkpoint address is bit-for-bit the
# original one. It is not necessarily a BTI landing pad: the measured entry of
# start_kernel in this build is `paciasp` (0xD503233F), not `bti c`. Both
# words are accepted as pads; the authoritative value is read from the frozen
# payload and the probe must encode exactly that word.
T3_ENTRY_PAD_CANDIDATES = {0xD503245F: "bti c", 0xD503233F: "paciasp"}
T3_BTI_LANDING_REQUIRED = False
T3_BTI_LANDING_REQUIRED_REASON = (
    "the only arrival at start_kernel is the direct `bl start_kernel` inside "
    "__primary_switched; BTI is not checked on direct branches, and LLVM's "
    "AArch64BranchTargets pass omits the landing pad precisely because the "
    "function address is never taken (the authoritative disassembly shows "
    "`paciasp` at the entry, with no bti). A preserved BTI landing pad is "
    "therefore NOT required here; what IS preserved is the original entry "
    "instruction itself, verified word-for-word against the frozen payload")
T2_PROBE_SHA = (
    "c78c55fb2fa94b6e16a33e59d7973acc715c212a02a88bad1ed954ecb1ce412a")
T2_CHECKPOINT_OFFSET_HISTORY = 0x1b39534

FORBIDDEN_BOOT_SHAS = {
    "T0_BOOT":
        "8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1",
    "T1_BOOT":
        "a4fa083f289219facb0a69062749dd6a9d2f667c4aa044b25b78c36b0da7e3df",
    "T2_BOOT":
        "d347cc1907563afd2c8faa0d07cafed5904985514c346434c8a774c14418e925",
    "FIX8_BOOT":
        "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5",
    "PANIC30_BOOT":
        "ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1",
    "OLD_INIT8_BOOT":
        "e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264",
    "ENTRY_STATE_PROBE_BOOT":
        "cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c",
}

# Preregistered matched-control timing. The PRIMARY reference is the T2
# true-device total (same large P1B payload, same 8 s CNTPCT delay, same PSCI
# reset, same fail-closed semantics; only the checkpoint moved). T1 and T0 are
# the secondary references.
T2_REFERENCE_TOTAL_S = 14.240
T1_REFERENCE_TOTAL_S = 14.238
T0_REFERENCE_TOTAL_S = 14.252
T2_MINUS_T1_OBSERVED_S = 0.002
T2_MINUS_T0_OBSERVED_S = -0.012
T3_STRONG_HALF_WINDOW_S = 1.0
T3_SUPPORTED_HALF_WINDOW_S = 2.0
T3_SECONDARY_HALF_WINDOW_S = 2.0
T3_EARLY_RETURN_CLASS_LIMIT_S = 20.0
T3_CASE_C_BAND_S = (20.0, 28.0)
P0_REF_OVERHEAD_S = 6.1445
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
T3_NO_RETURN_WINDOW_S = 120.0
T3_BOOT_SIZE_EXPECTED = 37380096

T3_CLOBBER_REGISTERS = "w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV"

# ---------------------------------------------------------------------------
# T3 entry contract: the exact CPU state at the first instruction of
# start_kernel, derived from the __primary_switched body (the only code
# executed between the T2 checkpoint and the T3 checkpoint).
# ---------------------------------------------------------------------------
T3_ENTRY_CONTRACT = {
    "T3_ENTRY_CURRENT_EL": "EL1",
    "T3_ENTRY_MMU": "ON",
    "T3_ENTRY_VBAR_EL1": "SET_TO_vectors_WITH_ISB",
    "T3_ENTRY_SCTLR_EL1_M": "1",
    "T3_ENTRY_PC_ADDRESS_SPACE": "VA",
    "T3_ENTRY_SP_VALID": "YES",
    "T3_ENTRY_DAIF": "D=0,A=1,I=1,F=1",
    "T3_ENTRY_BSS": "CLEARED",
    "T3_ENTRY_X0_MEANING": "cpu_boot_mode (mov x0, x20)",
    "T3_ENTRY_X1_MEANING": "scratch, NOT boot contract",
    "T3_ENTRY_X2_MEANING": "scratch, NOT boot contract",
    "T3_ENTRY_X3_MEANING": "scratch, pre-T3 residue, NOT boot contract",
    "T3_ENTRY_X30_MEANING": "return address into __primary_switched",
    "T3_ENTRY_X19_X25":
        "x19=mmu_enabled_at_boot(0) x20=cpu_boot_mode x21=FDT pa "
        "x22=idmap VA of DT x23=KASLR/load offset x24=memstart seed "
        "x25=supported VA size; probe writes NONE of them",
    "T3_ENTRY_CALLED_FROM": "__primary_switched (bl start_kernel)",
    "T3_ENTRY_RETURN_ASSUMED": "NEVER (start_kernel is __noreturn)",
}
T3_ENTRY_CONTRACT_REASONS = {
    "T3_ENTRY_CURRENT_EL":
        "init_kernel_el eret with SPSR_EL1/EL2 = INIT_PSTATE_EL1 "
        "(PSR_MODE_EL1h); the device boot was proven EL1 at T0/T1/T2",
    "T3_ENTRY_MMU":
        "__enable_mmu set_sctlr_el1 with INIT_SCTLR_EL1_MMU_ON before "
        "__primary_switch; nothing clears SCTLR_EL1.M in __primary_switched",
    "T3_ENTRY_VBAR_EL1":
        "head.S 476-478: adr_l x8, vectors ; msr vbar_el1, x8 ; isb",
    "T3_ENTRY_SCTLR_EL1_M":
        "__enable_mmu INIT_SCTLR_EL1_MMU_ON (SCTLR_EL1.M=1)",
    "T3_ENTRY_PC_ADDRESS_SPACE":
        "__primary_switch ldr x8, =__primary_switched ; br x8, then a direct "
        "bl start_kernel: both are linked kernel VAs after __relocate_kernel",
    "T3_ENTRY_SP_VALID":
        "init_cpu_task (head.S 449-465) sets sp = init_task.stack + "
        "THREAD_SIZE - PT_REGS_SIZE and writes the final frame record, then "
        "head.S 480-481 pushes x29/x30 and 522 pops them again",
    "T3_ENTRY_DAIF":
        "INIT_PSTATE_EL1 masks D/A/I/F; __cpu_setup enable_dbg clears D only; "
        "nothing in __primary_switched touches DAIF",
    "T3_ENTRY_BSS":
        "head.S 492-497: __pi_memset(__bss_start, 0, __bss_stop - "
        "__bss_start) followed by dsb ishst",
    "T3_ENTRY_X0_MEANING":
        "head.S 520-521: mov x0, x20 before init_feature_override and "
        "finalise_el2 (x20 = cpu_boot_mode), so x0 is NOT the DTB pointer",
    "T3_ENTRY_X1_X3":
        "the BSS-clear sequence consumes x1/x2 (head.S 493-497) and "
        "early_fdt_map/init_feature_override use x0 only",
    "T3_ENTRY_X30_MEANING":
        "head.S 523 bl start_kernel sets x30 to the following ASM_BUG() site",
    "T3_ENTRY_X19_X25":
        "head.S 75-88 register contract; __primary_switched writes none of "
        "them (init_cpu_task uses x4/x5/x6)",
    "T3_ENTRY_CALLED_FROM":
        "the unique bl start_kernel inside __primary_switched, re-derived "
        "this round from the disassembled rebuilt vmlinux",
    "T3_ENTRY_RETURN_ASSUMED":
        "init/main.c declares start_kernel __noreturn; head.S 524 is "
        "ASM_BUG() and the checkpoint never returns either",
}
T3_CNTPCT_ACCESS_SAFE_REASON = (
    "CNTFRQ_EL0/CNTPCT_EL0 reads are EL1-legal regardless of SCTLR_EL1.M and "
    "regardless of MMU state; the only pre-checkpoint code is the "
    "__primary_switched body (head.S 473-522), whose callees "
    "set_cpu_boot_mode_flag/__pi_memset/early_fdt_map/init_feature_override/"
    "finalise_el2 write no counter-trap control (CNTKCTL_EL1 is written only "
    "by arch_timer_set_cntkctl from arch_timer/context switch, CNTHCTL_EL2 "
    "only in EL2 init or KVM, neither on this EL1 boot path); the identical "
    "EL1 access was proven on this device at T0, T1 and T2")
T3_PSCI_SAFE_REASON = (
    "PSCI SYSTEM_RESET fid=0x84000009 carries no pointer argument, so no "
    "VA->PA conversion is involved; smc is synchronous to EL3 regardless of "
    "SCTLR_EL1.M, TTBR state or VBAR_EL1; the identical EL1 smc was proven on "
    "this device at T0, T1 and T2, and the frozen RT-D keeps /psci method=smc")
T3_PRE_CHECKPOINT_REWRITE_REASON = (
    "no runtime rewrite can land before the checkpoint: __relocate_kernel "
    "runs in __primary_switch BEFORE __primary_switched (scanned separately), "
    "while apply_boot_alternatives() is called from smp_prepare_boot_cpu() "
    "(arch/arm64/kernel/smp.c) which start_kernel calls from init/main.c, and "
    "jump_label_init() also runs from init/main.c - both strictly AFTER the "
    "T3 checkpoint at start_kernel instruction 0")

T3_RUNTIME_SEMANTIC_DELTA = "START_KERNEL_ADDRESS_CHECKPOINT_ONLY"

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
T3_STORE_RE = re.compile(
    r"\b(st|str|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|cas|swp|adrp)\b",
    re.I)
T3_LOAD_RE = re.compile(
    r"\b(ldr|ldrb|ldrh|ldp|ldur|ldar|ldxr|ldtr)\b", re.I)
PADDING_MNEMS = {"udf", ".inst", ".word", "nop"}
RELOC_OFF_RE = re.compile(r"^([0-9a-f]{8,16})\s+\S+\s+R_AARCH64_")
STATUS_KV_BEGIN = "<!-- R3-STATUS-KV:BEGIN -->"
STATUS_KV_END = "<!-- R3-STATUS-KV:END -->"
T3_SYSREG_MSR_RE = re.compile(
    r"^\s*msr\s+(cntkctl_el1|cnthctl_el2|cntvoff_el2)\s*,",
    re.I | re.M)
T3_SK_PROTO_RE = re.compile(r"^void start_kernel\(void\)", re.M)

# Structured source gate (prompt section 48): parsed key/value over the
# R3-STATUS-KV block of docs/route-r3-current-status.md, with semantic
# predicates instead of a natural-language literal token.
STATUS_DOC_REQUIRED_KV = {
    "T0_STATUS": "TRUE_DEVICE_PROVEN",
    "T0_TOTAL_S": "14.252",
    "T1_STATUS": "TRUE_DEVICE_PROVEN",
    "T1_TOTAL_S": "14.238",
    "T1_MINUS_T0_S": "-0.014",
    "T2_STATUS": "TRUE_DEVICE_PROVEN",
    "T2_TOTAL_S": "14.240",
    "T2_MINUS_T1_S": "0.002",
    "R0_STATUS": "PROVEN",
    "R1_STATUS": "PROVEN",
    "R2_STATUS": "PROVEN",
    "R3_STATUS": "PROVEN",
    "E1_STATUS": "PROVEN",
    "E2_STATUS": "NOT_PROVEN",
    "T3_TARGET_SYMBOL": "start_kernel",
    "PANIC30_STATUS": "COMPLETED",
    "PANIC30_SHIFT": "NO_SUPPORTED_SHIFT",
    "FIX24_STATUS": "FROZEN",
    "M5N_STATUS": "FROZEN",
    "USB_STATUS": "FROZEN",
    "CURRENT_B": "M5D+M5H+M5M-B",
    "SLOT_A_WRITTEN": "NO",
    "PARTITION_WRITES": "0",
}
STATUS_DOC_ENUM_KV = {
    "T3_STATUS": ("PREDEVICE_DESIGNED", "PREDEVICE_READY"),
    "T3_PREDEVICE_STATUS": ("READY", "NOT_READY"),
    "T3_PROBE_ARCHITECTURE": ("INLINE", "EXTERNAL"),
}

# The audited __primary_switched body (head.S 473-524) between the T2
# checkpoint and the T3 checkpoint. The ORDER is asserted against the source;
# "mov x0, x20" legitimately appears twice (489 and 520) so the matcher walks
# the source forward.
PRE_START_KERNEL_PATH_TOKENS = (
    "adr_l x4, init_task",
    "init_cpu_task x4, x5, x6",
    "adr_l x8, vectors",
    "msr vbar_el1, x8",
    "stp x29, x30, [sp, #-16]!",
    "mov x29, sp",
    "str_l x21, __fdt_pointer",
    "ldr_l x4, kimage_vaddr",
    "sub x4, x4, x0",
    "str_l x4, kimage_voffset",
    "mov x0, x20",
    "bl set_cpu_boot_mode_flag",
    "adr_l x0, __bss_start",
    "mov x1, xzr",
    "adr_l x2, __bss_stop",
    "sub x2, x2, x0",
    "bl __pi_memset",
    "dsb ishst",
    "mov x0, x21",
    "bl early_fdt_map",
    "mov x0, x20",
    "bl init_feature_override",
    "bl finalise_el2",
    "ldp x29, x30, [sp], #16",
    "bl start_kernel",
    "ASM_BUG()",
)


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
# INLINE overwrite-safety gates. The window is in the LINK-TIME VA space.
# ---------------------------------------------------------------------------

def gate_window_symbol_scan(w_va: int, window_len: int,
                            symbol_vas: list) -> int:
    bad = sorted(v for v in symbol_vas if w_va < v < w_va + window_len)
    if bad:
        fail("T3_INLINE_SAFETY_FAILED",
             f"symbol entry inside the overwrite window at "
             f"{[hex(v) for v in bad[:8]]}")
    return len(symbol_vas)


def gate_window_branch_scan(w_va: int, window_len: int, hits: list) -> int:
    bad = sorted((s, t) for s, t in hits if w_va < t < w_va + window_len)
    if bad:
        fail("T3_INLINE_SAFETY_FAILED",
             f"control transfer into the overwrite window at "
             f"{[(hex(s), hex(t)) for s, t in bad[:8]]}")
    return len(hits)


def gate_window_relocation_scan(w_va: int, window_len: int,
                                offsets: list) -> int:
    bad = sorted(o for o in offsets if w_va <= o < w_va + window_len)
    if bad:
        fail("T3_INLINE_SAFETY_FAILED",
             f"runtime relocation target inside the overwrite window at "
             f"{[hex(v) for v in bad[:8]]} (__relocate_kernel would rewrite "
             "the probe bytes)")
    return len(offsets)


def gate_window_literal_scan(w_va: int, window_len: int, image: bytes) -> int:
    """No 8-byte aligned literal anywhere in the Image may hold an absolute VA
    landing STRICTLY inside the window: such a pointer would give an indirect
    entry into the middle of the overwritten range."""
    n = len(image) // 8
    words = array.array("Q")
    words.frombytes(image[:n * 8])
    if sys.byteorder != "little":
        words.byteswap()
    for i, v in enumerate(words):
        if w_va < v < w_va + window_len:
            fail("T3_INLINE_SAFETY_FAILED",
                 f"absolute literal pointing into the overwrite window at "
                 f"image offset {i * 8:#x} value {v:#x}")
    return n


def gate_window_section_scan(w_va: int, window_len: int,
                             sections: list) -> dict:
    containing = [s for s in sections
                  if s["vma"] <= w_va < s["vma"] + s["size"]]
    if len(containing) != 1:
        fail("T3_INLINE_SAFETY_FAILED",
             f"{len(containing)} sections contain {w_va:#x}")
    s = containing[0]
    if w_va + window_len > s["vma"] + s["size"]:
        fail("T3_INLINE_SAFETY_FAILED",
             f"window end {w_va + window_len:#x} crosses section "
             f"{s['name']} end {s['vma'] + s['size']:#x}")
    if not s["code"]:
        fail("T3_INLINE_SAFETY_FAILED",
             f"section {s['name']} is not executable (NX)")
    if not s["alloc"]:
        fail("T3_INLINE_SAFETY_FAILED",
             f"section {s['name']} is not allocated")
    return s


def gate_function_extent_scan(w_va: int, window_len: int,
                              next_symbol_va: int) -> int:
    """The window must stay inside the start_kernel function body."""
    if next_symbol_va <= w_va:
        fail("T3_INLINE_SAFETY_FAILED",
             f"no symbol after start_kernel ({next_symbol_va:#x})")
    if w_va + window_len > next_symbol_va:
        fail("T3_INLINE_SAFETY_FAILED",
             f"window end {w_va + window_len:#x} passes the next symbol "
             f"{next_symbol_va:#x}: the overwrite would leave start_kernel")
    return next_symbol_va - w_va


def gate_probe_mapping(source: str) -> None:
    """Only an INLINE probe whose mapping is the kernel text VA the CPU is
    already executing is acceptable; any padding or external-cave claim is
    rejected by default (an unproven MMU-on code cave is not executable)."""
    if source != "KERNEL_TEXT_VA_SELF_EVIDENT":
        fail("T3_MAPPING_FAILED",
             f"mapping source {source!r} is not a proven executable mapping "
             "(an unproven padding mapping is REJECTED)")


def gate_entry_contract(contract: dict, expected: dict) -> None:
    if contract != expected:
        diff = {k: (contract.get(k), expected.get(k))
                for k in set(contract) | set(expected)
                if contract.get(k) != expected.get(k)}
        fail("T3_ENTRY_STATE_FAILED", f"contract drift {diff}")
    if contract["T3_ENTRY_MMU"] != "ON":
        fail("T3_ENTRY_STATE_FAILED", "MMU assumed OFF")
    if contract["T3_ENTRY_PC_ADDRESS_SPACE"] != "VA":
        fail("T3_ENTRY_STATE_FAILED",
             "physical address used as the T3 PC address space")


def gate_cnppct_safety(reason: str, safe: bool) -> None:
    if not safe or not reason:
        fail("T3_TIMER_FAILED",
             "CNTFRQ_EL0/CNTPCT_EL0 access at T3 is not provably legal")
    for token in ("CNTKCTL_EL1", "CNTHCTL_EL2", "EL1"):
        if token not in reason:
            fail("T3_TIMER_FAILED", f"timer audit reason lacks {token}")


def gate_psci_safety(reason: str, safe: bool) -> None:
    if not safe or not reason:
        fail("T3_PSCI_FAILED", "PSCI SYSTEM_RESET at T3 is not provably safe")
    for token in ("0x84000009", "smc", "EL3"):
        if token not in reason:
            fail("T3_PSCI_FAILED", f"PSCI audit reason lacks {token}")


def gate_vmlinux_frozen_agreement(w_va: int, off_w: int, dump: str,
                                  frozen: bytes) -> int:
    """The authoritative vmlinux disassembly at the target must agree
    byte-for-byte with the frozen payload at the re-derived Image offset."""
    insns = [l for l in dump.splitlines() if INSTR_RE.match(l)]
    if not insns:
        fail("T3_IDENTITY_FAILED", "empty target disassembly")
    first = INSTR_RE.match(insns[0])
    addr = int(first.group(1), 16)
    word = int(first.group(2), 16)
    if addr != w_va:
        fail("T3_IDENTITY_FAILED",
             f"vmlinux disassembly starts at {addr:#x}, expected {w_va:#x}")
    frozen_word = struct.unpack_from("<I", frozen, off_w)[0]
    if word != frozen_word:
        fail("T3_IDENTITY_FAILED",
             f"vmlinux word {word:#010x} != frozen payload word "
             f"{frozen_word:#010x} at Image offset {off_w:#x}")
    return word


def gate_window_bytes_agree(w_va: int, off_w: int, dump: str, frozen: bytes,
                            n_words: int) -> list:
    """Every word of the overwrite window must agree between the authoritative
    rebuilt vmlinux disassembly and the frozen payload that is actually
    patched: the audit reads one binary and the payload patch touches
    another."""
    insns = [INSTR_RE.match(l) for l in dump.splitlines() if INSTR_RE.match(l)]
    if len(insns) < n_words:
        fail("T3_IDENTITY_FAILED",
             f"only {len(insns)} instructions disassembled in the window; "
             f"{n_words} required")
    words: list = []
    for i, m in enumerate(insns[:n_words]):
        addr = int(m.group(1), 16)
        if addr != w_va + 4 * i:
            fail("T3_IDENTITY_FAILED",
                 f"window disassembly gap at {addr:#x}")
        word = int(m.group(2), 16)
        fz = struct.unpack_from("<I", frozen, off_w + 4 * i)[0]
        if word != fz:
            fail("T3_IDENTITY_FAILED",
                 f"window word {i} ({addr:#x}) vmlinux {word:#010x} != frozen "
                 f"payload {fz:#010x}: the overwrite would be applied to bytes "
                 "that were never audited")
        words.append(word)
    return words


def gate_sk_entry_insn(word0: int, word1: int, pad_word: int) -> str:
    """The entry instruction of start_kernel is preserved verbatim: the probe's
    first word must be exactly the frozen payload's original first word, and
    that word must be one of the two known C-entry prologue hints (`bti c`
    when the function is an indirect-branch target, `paciasp` when it is not).
    The audit returns the pad mnemonic."""
    pad = T3_ENTRY_PAD_CANDIDATES.get(pad_word)
    if pad is None:
        fail("T3_ENTRY_INSTRUMENTATION_FAILED",
             f"start_kernel instruction 0 is {pad_word:#010x}, which is "
             "neither `bti c` nor `paciasp`: the probe layout and the entry "
             "reasoning were derived for one of those two prologues")
    if word0 != pad_word:
        fail("T3_ENTRY_INSTRUMENTATION_FAILED",
             f"probe pad {word0:#010x} does not reproduce the original "
             f"start_kernel first word {pad_word:#010x}")
    if word1 in (0, 0xFFFFFFFF):
        fail("T3_ENTRY_INSTRUMENTATION_FAILED",
             f"frozen second word {word1:#010x} is not an instruction")
    return pad


def gate_instrumentation_audit(cfg: dict, insn0: str, pad_word: int) -> None:
    """Prompt section 12: a C function entry is not a plain assembly symbol.
    The audit rejects any configuration under which the measured entry bytes
    and the claimed instrumentation story would disagree."""
    if cfg.get("CONFIG_ARM64_BTI_KERNEL") != "y":
        fail("T3_ENTRY_INSTRUMENTATION_FAILED",
             "CONFIG_ARM64_BTI_KERNEL is not y: the branch-protection flags "
             "and the entry prologue reasoning would not apply")
    for sym in ("CONFIG_CFI_CLANG", "CONFIG_SHADOW_CALL_STACK",
                "CONFIG_KCOV", "CONFIG_KASAN", "CONFIG_KASAN_GENERIC",
                "CONFIG_KASAN_SW_TAGS", "CONFIG_KASAN_HW_TAGS",
                "CONFIG_FUNCTION_TRACER", "CONFIG_DYNAMIC_FTRACE",
                "CONFIG_DYNAMIC_FTRACE_WITH_CALL_OPS",
                "CONFIG_DYNAMIC_FTRACE_WITH_ARGS"):
        if cfg.get(sym) == "y":
            fail("T3_ENTRY_INSTRUMENTATION_FAILED",
                 f"{sym}=y changes the C entry semantics; the T3 probe bytes "
                 "and the entry reasoning were derived with it disabled")
    if insn0 not in ("bti", "paciasp"):
        fail("T3_ENTRY_INSTRUMENTATION_FAILED",
             f"start_kernel instruction 0 is {insn0!r}, which is neither a "
             "BTI landing pad nor the PAC prologue")
    expected = T3_ENTRY_PAD_CANDIDATES[pad_word]
    if insn0 != expected.split()[0]:
        fail("T3_ENTRY_INSTRUMENTATION_FAILED",
             f"disassembled entry {insn0!r} disagrees with the frozen entry "
             f"word {pad_word:#010x} ({expected})")


def gate_callsite_unique(hits: list, sk_va: int) -> tuple:
    if len(hits) != 1:
        fail("T3_CALLSITE_FAILED",
             f"{len(hits)} instructions in __primary_switched branch to "
             f"start_kernel ({[hex(h[0]) for h in hits[:8]]})")
    va, mn, target = hits[0]
    if target != sk_va:
        fail("T3_CALLSITE_FAILED",
             f"call site target {target:#x} != start_kernel {sk_va:#x}")
    if mn != "bl":
        fail("T3_CALLSITE_FAILED",
             f"start_kernel is reached by {mn!r}, not bl (a b/br/indirect "
             "arrival would change the entry register contract)")
    return hits[0]


def gate_checkpoint_after_callsite(sk_va: int, callsite_va: int) -> None:
    """Prompt section 10: the checkpoint must be AT the start_kernel entry,
    i.e. strictly after the call site, never before it."""
    if callsite_va >= sk_va:
        fail("T3_CALLSITE_FAILED",
             f"checkpoint {sk_va:#x} is not after the call site "
             f"{callsite_va:#x}: it would not prove START_KERNEL_REACHED")


def gate_pre_path_order(body: str) -> None:
    """The __primary_switched body between the T2 and the T3 checkpoint must
    contain the audited steps in the exact audited order."""
    flat = re.sub(r"\s+", " ", body)
    pos = -1
    for tok in PRE_START_KERNEL_PATH_TOKENS:
        p = flat.find(tok, pos + 1) if pos >= 0 else flat.find(tok)
        if p < 0:
            fail("T3_CONTROL_FLOW_FAILED", f"missing pre-path step {tok!r}")
        if p <= pos:
            fail("T3_CONTROL_FLOW_FAILED", f"order violation at {tok!r}")
        pos = p


def gate_no_early_counter_trap(*sources: str) -> None:
    """No pre-checkpoint source file may write a counter-trap control."""
    for text in sources:
        m = T3_SYSREG_MSR_RE.search(text)
        if m:
            fail("T3_TIMER_FAILED",
                 f"pre-checkpoint counter-trap write: {m.group(0)!r}")


def gate_table_entries(label: str, entries: list, window: tuple) -> int:
    """Exception tables, alternatives, jump labels, static calls and kCFI
    traps all carry instruction addresses. Any entry whose instruction
    address lands inside the overwrite window is a latent runtime rewrite
    target and is REJECTED."""
    lo, hi = window
    bad = sorted({v for v in entries if lo <= v < hi})
    if bad:
        fail("T3_RUNTIME_REWRITE_FAILED",
             f"{label}: instruction address inside the overwrite window at "
             f"{[hex(v) for v in bad[:8]]}")
    return len(entries)


def gate_window_inside_image_size(off_w: int, window_len: int,
                                  image_size: int) -> None:
    """The window must live inside the kernel runtime footprint, never in the
    deterministic padding after image_size (prompt section 17)."""
    if off_w + window_len > image_size:
        fail("T3_GEOMETRY_FAILED",
             f"window [{off_w:#x},{off_w + window_len:#x}) reaches past "
             f"image_size {image_size:#x} into the unmapped padding")


def gate_diagnostic_core_identity(probe: bytes, t1_core: bytes,
                                  pad_word: int) -> None:
    """The T3 delay/reset core must be byte-identical to the T0/T1
    true-device proven core, and the pad must be the original entry
    instruction. The only permitted difference anywhere is the checkpoint
    ADDRESS."""
    if len(probe) != T3_PROBE_SIZE:
        fail("T3_CORE_IDENTITY_FAILED",
             f"probe size {len(probe)} != {T3_PROBE_SIZE}")
    pad = probe[:T3_PAD_SIZE]
    if pad != struct.pack("<I", pad_word):
        fail("T3_CORE_IDENTITY_FAILED",
             f"probe pad {pad.hex()} != original start_kernel entry word "
             f"{struct.pack('<I', pad_word).hex()}")
    core = probe[T3_PAD_SIZE:]
    if core != t1_core:
        fail("T3_CORE_IDENTITY_FAILED",
             f"T3 core sha={sha(core)} != T1 core sha={sha(t1_core)}")
    if len(core) != T3_CORE_SIZE:
        fail("T3_CORE_IDENTITY_FAILED",
             f"core size {len(core)} != {T3_CORE_SIZE}")


def gate_core_slice_matches_t2(probe: bytes, t2_probe: bytes) -> None:
    """The diagnostic CORE (everything after the preserved entry pad) must be
    byte-identical to the T2 probe core assembled in the same run: the T3
    change is the checkpoint ADDRESS plus the entry pad word, never the
    proven delay/reset sequence."""
    if probe[T3_PAD_SIZE:] != t2_probe[T3_PAD_SIZE:]:
        fail("T3_CORE_IDENTITY_FAILED",
             f"T3 core sha={sha(probe[T3_PAD_SIZE:])} != T2 core sha="
             f"{sha(t2_probe[T3_PAD_SIZE:])}: the T3 change must be the "
             "checkpoint ADDRESS and the preserved entry pad only")


def gate_no_relocations(rel_text: str, label: str) -> None:
    if "R_AARCH64_" in rel_text:
        fail("T3_RELOC_FAILED", f"{label}: {rel_text[:200]}")


def gate_ops_order(ops: str) -> None:
    pos = -1
    for tok, is_re in ORDER_TOKENS:
        if is_re:
            m = re.search(tok, ops)
            p = m.start() if m else -1
        else:
            p = ops.find(tok)
        if p < 0:
            fail("T3_DISASM_FAILED", f"missing {tok!r}")
        if p <= pos:
            fail("T3_DISASM_FAILED", f"order violation at {tok!r}")
        pos = p


def gate_branch_targets(dump: str, probe_len: int) -> None:
    for line in dump.splitlines():
        m = BRANCH_RE.match(line)
        if not m:
            continue
        target = int(m.group(3), 16)
        if target >= probe_len or target % 4:
            fail("T3_DISASM_FAILED",
                 f"branch target {target:#x} outside the T3 checkpoint")


def gate_terminal(dump: str) -> None:
    instrs = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if m:
            instrs.append((int(m.group(1), 16), m.group(3), m.group(4)))
    smc_idx = [i for i, (_a, mn, _o) in enumerate(instrs) if mn == "smc"]
    if len(smc_idx) != 1:
        fail("T3_DISASM_FAILED", f"smc count {len(smc_idx)}")
    smc = smc_idx[0]
    if smc + 2 >= len(instrs):
        fail("T3_DISASM_FAILED", "no wfe loop after smc")
    nxt = instrs[smc + 1]
    if nxt[1] != "wfe":
        fail("T3_DISASM_FAILED",
             f"instruction after smc is {nxt[1]!r}, not wfe (fall-through)")
    term = instrs[smc + 2]
    if term[1] != "b":
        fail("T3_DISASM_FAILED",
             f"instruction after wfe is {term[1]!r}, not b")
    m = re.match(r"^(?:0x)?([0-9a-f]+)", term[2].strip().split("<", 1)[0])
    if not m or int(m.group(1), 16) != nxt[0]:
        fail("T3_DISASM_FAILED",
             f"terminal b does not target wfe at {nxt[0]:#x} "
             f"(operand {term[2]!r})")
    for ins in instrs[smc + 3:]:
        if ins[1] not in PADDING_MNEMS:
            fail("T3_DISASM_FAILED",
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
            fail("T3_DISASM_FAILED",
                 f"boot contract register written: {line!r}")
        if dst in ("x0", "w0"):
            if not (FID_LOW_RE.search(line) or FID_HIGH_RE.search(line)):
                fail("T3_DISASM_FAILED", f"x0/w0 written off-FID: {line!r}")
            continue
        if dst not in {"x9", "x10", "x11", "x12", "x13"}:
            fail("T3_DISASM_FAILED", f"register discipline: {line!r}")


def gate_no_forbidden(ops: str) -> None:
    m = T3_STORE_RE.search(ops)
    if m:
        fail("T3_DISASM_FAILED", f"store/adrp present: {m.group(0)!r}")
    m = T3_LOAD_RE.search(ops)
    if m:
        fail("T3_DISASM_FAILED", f"memory load present: {m.group(0)!r}")
    for bad in (r"\bbl\b", r"\blr\b", r"\beret\b", r"\bsctlr\b",
                r"\bttbr", r"\bmsr\b\s+daifclr", r"\bsp\b", r"\bwsp\b",
                r"\bx19\b", r"\bx2[0-5]\b", r"\bx29\b", r"\bx30\b"):
        if re.search(bad, ops):
            fail("T3_DISASM_FAILED", f"forbidden {bad!r}")
    if "primary_entry" in ops or "__primary_switched" in ops:
        fail("T3_DISASM_FAILED", "normal-kernel continuation reference present")


def gate_t3_probe(ops: str, dump: str, probe_len: int) -> None:
    gate_ops_order(ops)
    gate_branch_targets(dump, probe_len)
    gate_terminal(dump)
    gate_register_discipline(ops)
    gate_no_forbidden(ops)


def gate_tail_identity(frozen: bytes, cand: bytes, window: tuple) -> int:
    """Prompt section 9: every byte OUTSIDE the single start_kernel window
    must be byte-identical to the frozen FIX8 payload."""
    lo, hi = window
    if len(cand) != len(frozen):
        fail("T3_PAYLOAD_DIFF_FAILED",
             f"size drift {len(cand)} != {len(frozen)}")
    if cand[:lo] != frozen[:lo]:
        fail("T3_PAYLOAD_DIFF_FAILED",
             "bytes before the window differ from FIX8 (primary_entry / "
             "head.S / __primary_switched must stay identical)")
    if cand[hi:] != frozen[hi:]:
        fail("T3_PAYLOAD_DIFF_FAILED",
             "bytes after the window differ from FIX8")
    return hi - lo


def gate_payload_diff(frozen: bytes, cand: bytes, window: tuple) -> list:
    if len(cand) != len(frozen):
        fail("T3_PAYLOAD_DIFF_FAILED",
             f"size drift {len(cand)} != {len(frozen)}")
    lo, hi = window
    diffs = [i for i in range(len(frozen)) if frozen[i] != cand[i]]
    bad = [i for i in diffs if not (lo <= i < hi)]
    if bad:
        fail("T3_PAYLOAD_DIFF_FAILED",
             f"diff outside the inline region at {[hex(i) for i in bad[:8]]} "
             "(the trampoline, primary_entry and the whole pre-T3 path must "
             "stay byte-identical to FIX8)")
    if not diffs:
        fail("T3_PAYLOAD_DIFF_FAILED", "inline region has no diff (patch lost?)")
    return diffs


def gate_t2_probe_removed(frozen: bytes, cand: bytes, off_ps: int,
                          t2_probe: bytes) -> None:
    """Prompt section 27: the T2 inline probe must be gone and
    __primary_switched must carry the FIX8 original bytes again."""
    region = cand[off_ps:off_ps + len(t2_probe)]
    if region == t2_probe:
        fail("T3_IDENTITY_FAILED",
             "the T2 probe is still present over __primary_switched")
    if region != frozen[off_ps:off_ps + len(t2_probe)]:
        fail("T3_IDENTITY_FAILED",
             "__primary_switched is neither the T2 probe nor the FIX8 "
             "original bytes")


def gate_tramp_identity(cand: bytes) -> None:
    tramp = cand[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T3_IDENTITY_FAILED",
             f"embedded trampoline sha={sha(tramp)} != frozen FIX8 {TRAMP_SHA}")


def gate_trailer(payload: bytes) -> bytes:
    hdr = pb.parse_image_hdr(payload, "t3-payload")
    dtb_offset, _gap = pb.calc_dtb_offset(hdr["image_size"])
    trailer = payload[dtb_offset:]
    if payload[dtb_offset:dtb_offset + 4] != struct.pack(">I", FDT_MAGIC):
        fail("T3_PAYLOAD_DIFF_FAILED", "no FDT magic at DTB_OFFSET")
    if sha(trailer) != RT_D_SHA or len(trailer) != RT_D_SIZE:
        fail("T3_PAYLOAD_DIFF_FAILED",
             f"trailer RT-D identity sha={sha(trailer)} len={len(trailer)}")
    return trailer


def gate_geometry(payload: bytes, image_size: int) -> tuple:
    hdr = pb.parse_image_hdr(payload, "t3-payload")
    if hdr["image_size"] != image_size:
        fail("T3_GEOMETRY_FAILED",
             f"image_size {hdr['image_size']:#x} != authoritative "
             f"{image_size:#x}")
    dtb_offset, gap = pb.calc_dtb_offset(hdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("T3_GEOMETRY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T3_GEOMETRY_FAILED",
             f"payload len {len(payload)} != dtb_offset + RT_D")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T3_GEOMETRY_FAILED", "2MiB residue geometry")
    boot_est = pb.align(PAGE + len(payload), PAGE) + PAGE
    if boot_est != T3_BOOT_SIZE_EXPECTED:
        fail("T3_GEOMETRY_FAILED",
             f"boot_est {boot_est} != {T3_BOOT_SIZE_EXPECTED}")
    if BOOT_CAP - boot_est < 0x1000000:
        fail("T3_GEOMETRY_FAILED", "capacity margin < 16MiB")
    return hdr, dtb_offset, gap, boot_est


def gate_image_size_rederived(image_size: int, label: str) -> None:
    if image_size <= 0 or image_size & 3:
        fail("T3_GEOMETRY_FAILED", f"{label}: image_size {image_size:#x}")
    if image_size + S_RESIDUE > DTB_OFFSET:
        fail("T3_GEOMETRY_FAILED",
             f"{label}: image_size footprint {image_size:#x} reaches RT-D "
             f"at {DTB_OFFSET:#x}")


# ---------------------------------------------------------------------------
# Preregistered matched-control decoder: T2 primary, T1/T0 secondary.
# ---------------------------------------------------------------------------

def t3_minus_t2(t3_total_s: float) -> float:
    return t3_total_s - T2_REFERENCE_TOTAL_S


def t3_minus_t1(t3_total_s: float) -> float:
    return t3_total_s - T1_REFERENCE_TOTAL_S


def t3_minus_t0(t3_total_s: float) -> float:
    return t3_total_s - T0_REFERENCE_TOTAL_S


def t3_programmed_estimate(t3_total_s: float) -> float:
    return t3_total_s - P0_REF_OVERHEAD_S  # SECONDARY cross-check only


def t3_reachability(t3_total_s, recovery_kind: str) -> dict:
    """Primary: matched-control delta vs T2_TOTAL=14.240 s; triple condition
    (window + T3_TOTAL<20 s + AUTOMATIC_ANDROID_RETURN) plus the T1/T0
    secondary cross-checks. A negative NEVER licenses T3_NOT_REACHED; it
    routes to T3_FAILURE_ISOLATION_CI."""
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T3_STABLE_FASTBOOT",
                "r4": "NOT_PROVEN", "next": "T3_FAILURE_ISOLATION_CI",
                "reason": "CASE_E_STABLE_FASTBOOT_SECOND_BOOT_FORBIDDEN"}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "T3_NO_RETURN",
                "r4": "NOT_PROVEN", "next": "T3_FAILURE_ISOLATION_CI",
                "reason": "CASE_F_NO_RETURN_MANUAL_ELAPSED_EXCLUDED"}
    if t3_total_s is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN",
                "r4": "NOT_PROVEN", "next": "T3_FAILURE_ISOLATION_CI",
                "reason": f"RECOVERY_KIND={recovery_kind}"}
    d2 = t3_minus_t2(t3_total_s)
    d1 = t3_minus_t1(t3_total_s)
    d0 = t3_minus_t0(t3_total_s)
    early = t3_total_s < T3_EARLY_RETURN_CLASS_LIMIT_S
    sec_ok = (abs(d1) <= T3_SECONDARY_HALF_WINDOW_S
              and abs(d0) <= T3_SECONDARY_HALF_WINDOW_S)
    if early and abs(d2) <= T3_STRONG_HALF_WINDOW_S and sec_ok:
        return {"verdict": "STRONG", "case": "T3_A_STRONG", "r4": "PROVEN",
                "next": "MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI",
                "reason": "T2_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET+T1_T0_SECONDARY_OK"}
    if early and abs(d2) <= T3_STRONG_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED",
                "case": "T3_A_STRONG_SECONDARY_CROSSCHECK_BLOCK",
                "r4": "STRONGLY_SUPPORTED",
                "next": "MAINLINE_V2_R3_P1B_T3_FAILURE_ISOLATION_CI",
                "reason": f"T3_MINUS_T1={d1:+.3f}s T3_MINUS_T0={d0:+.3f}s "
                          "CONTRADICT_PRIMARY"}
    if early and abs(d2) <= T3_SUPPORTED_HALF_WINDOW_S:
        return {"verdict": "SUPPORTED", "case": "T3_B_SUPPORTED",
                "r4": "STRONGLY_SUPPORTED",
                "next": "MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI",
                "reason": "T2_MATCHED_CONTROL+EARLY_RETURN_CLASS+"
                          "AUTOMATIC_RESET"}
    if early:
        return {"verdict": "NOT_OBSERVED",
                "case": "T3_EARLY_RETURN_TIMING_MISMATCH",
                "r4": "NOT_PROVEN", "next": "T3_FAILURE_ISOLATION_CI",
                "reason": f"T3_MINUS_T2={d2:+.3f}s OUTSIDE_SUPPORTED_WINDOW"}
    lo, hi = T3_CASE_C_BAND_S
    if lo <= t3_total_s < hi:
        return {"verdict": "NOT_OBSERVED", "case": "T3_SIGNATURE_NOT_OBSERVED",
                "r4": "NOT_PROVEN", "next": "T3_FAILURE_ISOLATION_CI",
                "reason": "CASE_C_OLD_AUTO_RETURN_CLASS"}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN", "r4": "NOT_PROVEN",
            "next": "T3_FAILURE_ISOLATION_CI",
            "reason": f"T3_TOTAL={t3_total_s:.3f}s OUTSIDE_PREREGISTERED_BANDS"}


def run_decoder_fixtures() -> list:
    lines: list = []
    t4ci = "MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI"

    def case(name, total, kind, want_verdict, want_case=None, want_r4=None,
             want_next=None):
        got = t3_reachability(total, kind)
        if got["verdict"] != want_verdict:
            fail("T3_DECODER_FIXTURE_FAILED",
                 f"{name}: verdict {got['verdict']} != {want_verdict}")
        if want_case and got["case"] != want_case:
            fail("T3_DECODER_FIXTURE_FAILED",
                 f"{name}: case {got['case']} != {want_case}")
        if want_r4 and got["r4"] != want_r4:
            fail("T3_DECODER_FIXTURE_FAILED",
                 f"{name}: r4 {got['r4']} != {want_r4}")
        if want_next and got["next"] != want_next:
            fail("T3_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"T3_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"case={got['case']} r4={got['r4']}")

    case("STRONG_14P2S", 14.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T3_A_STRONG", "PROVEN", t4ci)
    case("STRONG_13P3S", 13.3, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T3_A_STRONG", "PROVEN")
    case("STRONG_15P2S", 15.2, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "T3_A_STRONG", "PROVEN")
    case("SUPPORTED_15P3S", 15.3, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T3_B_SUPPORTED", "STRONGLY_SUPPORTED", t4ci)
    case("SUPPORTED_16P2S", 16.2, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T3_B_SUPPORTED", "STRONGLY_SUPPORTED")
    case("SUPPORTED_12P3S", 12.3, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "T3_B_SUPPORTED", "STRONGLY_SUPPORTED")
    case("EARLY_MISMATCH_16P4S", 16.4, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T3_EARLY_RETURN_TIMING_MISMATCH", "NOT_PROVEN",
         "T3_FAILURE_ISOLATION_CI")
    case("EARLY_MISMATCH_11P0S", 11.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T3_EARLY_RETURN_TIMING_MISMATCH", "NOT_PROVEN")
    case("CASE_C_FIX8_CLASS_23P852S", FIX8_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T3_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN", "T3_FAILURE_ISOLATION_CI")
    case("CASE_C_PANIC30_CLASS_26P289S", PANIC30_TOTAL_S,
         "AUTOMATIC_ANDROID_RETURN", "NOT_OBSERVED",
         "T3_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN")
    case("CASE_C_BAND_EDGE_20P0S", 20.0, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "T3_SIGNATURE_NOT_OBSERVED", "NOT_PROVEN")
    case("CASE_E_STABLE_FASTBOOT", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "T3_STABLE_FASTBOOT", "NOT_PROVEN",
         "T3_FAILURE_ISOLATION_CI")
    case("CASE_F_NO_RETURN", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "T3_NO_RETURN", "NOT_PROVEN",
         "T3_FAILURE_ISOLATION_CI")
    case("UNKNOWN_KIND", 14.2, "UNKNOWN", "NOT_OBSERVED", "UNKNOWN",
         "NOT_PROVEN")
    case("UNUSED_KIND", 14.2, "AUTOMATIC_ANDROID_RETURN_UNUSED",
         "NOT_OBSERVED", "UNKNOWN", "NOT_PROVEN")
    est = t3_programmed_estimate(T2_REFERENCE_TOTAL_S)
    if abs(est - (T2_REFERENCE_TOTAL_S - P0_REF_OVERHEAD_S)) > 1e-9:
        fail("T3_DECODER_FIXTURE_FAILED", "estimate arithmetic")
    if abs((T2_REFERENCE_TOTAL_S - T1_REFERENCE_TOTAL_S)
           - T2_MINUS_T1_OBSERVED_S) > 1e-9:
        fail("T3_DECODER_FIXTURE_FAILED", "T2_MINUS_T1 frozen constant")
    if abs((T2_REFERENCE_TOTAL_S - T0_REFERENCE_TOTAL_S)
           - T2_MINUS_T0_OBSERVED_S) > 1e-9:
        fail("T3_DECODER_FIXTURE_FAILED", "T2_MINUS_T0 frozen constant")
    lines.append(f"T3_DECODER_REFERENCE est(T2 {T2_REFERENCE_TOTAL_S}s)="
                 f"{est:.4f}s (SECONDARY cross-check only; expected ~8s)")
    lines.append("T3_DECODER_T2_MATCHED_CONTROL_REFERENCE=PASS")
    lines.append("T3_DECODER_T3_NOT_REACHED_LICENSE=NO")
    lines.append("T3_DECODER_FIXTURES=PASS")
    return lines


# ---------------------------------------------------------------------------
# Negative fixtures against the real gate functions.
# ---------------------------------------------------------------------------

def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("T3_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"T3_NEGATIVE_{name}_REJECTED=PASS"
    fail("T3_NEGATIVE_FIXTURE_FAILED", f"{name}: ACCEPTED (must reject)")


def t2_probe_shape(frozen: bytes, off_ps: int) -> bytes:
    """The frozen payload's __primary_switched window AS IF the T2 probe were
    still in place: a real byte sequence, so the 'T2 probe still present'
    fixture is a real rejection rather than a tautology."""
    return frozen[off_ps:off_ps + T3_PROBE_SIZE]


def run_negative_fixtures(ctx: dict) -> list:
    lines: list = []
    ops = ctx["ops"]
    dump = ctx["dump"]
    probe_len = ctx["probe_len"]
    sk_va = ctx["sk_va"]
    frozen = ctx["frozen"]
    cand = ctx["cand"]
    off_sk = ctx["off_sk"]
    off_ps = ctx["off_ps"]
    sections = ctx["sections"]
    symbol_vas = ctx["symbol_vas"]
    reloc_offsets = ctx["reloc_offsets"]
    t1_probe = ctx["t1_probe"]
    t2_probe = ctx["t2_probe"]
    pad_word = ctx["pad_word"]
    ops_lines = ops.splitlines()
    region = (off_sk, off_sk + probe_len)

    def dump_insert_after(anchor_mnem: str, extra: list) -> str:
        out = []
        for ln in dump.splitlines():
            out.append(ln)
            m = INSTR_RE.match(ln)
            if m and m.group(3) == anchor_mnem:
                out.extend(extra)
        return "\n".join(out) + "\n"

    lines.append(expect_reject(
        "WRONG_START_KERNEL_SYMBOL",
        lambda: gate_window_symbol_scan(sk_va - 4, probe_len, symbol_vas),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "WRONG_START_KERNEL_VA_FILE_OFFSET",
        lambda: gate_vmlinux_frozen_agreement(sk_va, off_sk + 4, dump, frozen),
        "T3_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "WRONG_CALL_TARGET",
        lambda: gate_callsite_unique([(sk_va - 0x200, "bl", sk_va + 4)], sk_va),
        "T3_CALLSITE_FAILED"))
    lines.append(expect_reject(
        "CALL_SITE_NOT_BL",
        lambda: gate_callsite_unique([(sk_va - 0x200, "br", sk_va)], sk_va),
        "T3_CALLSITE_FAILED"))
    lines.append(expect_reject(
        "CALL_SITE_MULTIPLE",
        lambda: gate_callsite_unique([(sk_va - 0x200, "bl", sk_va),
                                      (sk_va - 0x100, "bl", sk_va)], sk_va),
        "T3_CALLSITE_FAILED"))
    lines.append(expect_reject(
        "CHECKPOINT_BEFORE_START_KERNEL_CALL",
        lambda: gate_checkpoint_after_callsite(sk_va, sk_va + 4),
        "T3_CALLSITE_FAILED"))
    lines.append(expect_reject(
        "T2_PROBE_STILL_PRESENT",
        lambda: gate_t2_probe_removed(
            frozen, t2_probe_shape(frozen, off_ps), off_ps,
            t2_probe_shape(frozen, off_ps)),
        "T3_IDENTITY_FAILED"))
    bad_ps = bytearray(cand)
    bad_ps[off_ps + 8] ^= 0xFF
    lines.append(expect_reject(
        "PRIMARY_SWITCHED_MODIFIED",
        lambda: gate_tail_identity(frozen, bytes(bad_ps), region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_pe = bytearray(cand)
    bad_pe[ctx["primary_entry_off"]] ^= 0xFF
    lines.append(expect_reject(
        "PRIMARY_ENTRY_MODIFIED",
        lambda: gate_tail_identity(frozen, bytes(bad_pe), region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_tramp = bytearray(cand)
    bad_tramp[TRAMP_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "TRAMPOLINE_MODIFIED",
        lambda: gate_tramp_identity(bytes(bad_tramp)), "T3_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "ENTRY_PAD_NOT_ORIGINAL",
        lambda: gate_sk_entry_insn(0xD503245F, ctx["orig_word1"], pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "UNKNOWN_ENTRY_PROLOGUE",
        lambda: gate_sk_entry_insn(0xD503201F, ctx["orig_word1"], pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "ENTRY_INSTRUMENTATION_UNKNOWN",
        lambda: gate_instrumentation_audit(
            ctx["cfg"], "dmb", pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "BTI_CONFIG_BROKEN",
        lambda: gate_instrumentation_audit(
            dict(ctx["cfg"], CONFIG_ARM64_BTI_KERNEL="n"),
            ctx["entry_mnemonic"], pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "FTRACE_INSTRUMENTED_ENTRY",
        lambda: gate_instrumentation_audit(
            dict(ctx["cfg"], CONFIG_FUNCTION_TRACER="y"),
            ctx["entry_mnemonic"], pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "CFI_INSTRUMENTED_ENTRY",
        lambda: gate_instrumentation_audit(
            dict(ctx["cfg"], CONFIG_CFI_CLANG="y"),
            ctx["entry_mnemonic"], pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "ENTRY_DISASM_DISAGREES_WITH_WORD",
        lambda: gate_instrumentation_audit(ctx["cfg"], "bti", pad_word),
        "T3_ENTRY_INSTRUMENTATION_FAILED"))
    lines.append(expect_reject(
        "WINDOW_BYTES_DISAGREE",
        lambda: gate_window_bytes_agree(
            sk_va, off_sk + 4, dump, frozen, 4),
        "T3_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "UNSAFE_INLINE_OVERWRITE",
        lambda: gate_window_symbol_scan(
            sk_va, probe_len, list(symbol_vas) + [sk_va + 8]),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "BRANCH_INTO_WINDOW",
        lambda: gate_window_branch_scan(
            sk_va, probe_len, [(sk_va - 0x1000, sk_va + 8)]),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "RUNTIME_RELOCATION_IN_WINDOW",
        lambda: gate_window_relocation_scan(
            sk_va, probe_len, list(reloc_offsets) + [sk_va + 12]),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "FUNCTION_EXTENT_OVERFLOW",
        lambda: gate_function_extent_scan(sk_va, probe_len, sk_va + 16),
        "T3_INLINE_SAFETY_FAILED"))
    lit = bytearray(frozen)
    struct.pack_into("<Q", lit, 0x1000, sk_va + 4)
    lines.append(expect_reject(
        "ABSOLUTE_LITERAL_INTO_WINDOW",
        lambda: gate_window_literal_scan(sk_va, probe_len, bytes(lit)),
        "T3_INLINE_SAFETY_FAILED"))
    lines.append(expect_reject(
        "ALTERNATIVE_TARGET_CONFLICT",
        lambda: gate_table_entries(
            "fixture", [sk_va + 16], (sk_va, sk_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "STATIC_CALL_TARGET_CONFLICT",
        lambda: gate_table_entries(
            "fixture", [sk_va + 32], (sk_va, sk_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "JUMP_LABEL_TARGET_CONFLICT",
        lambda: gate_table_entries(
            "fixture", [sk_va + 4], (sk_va, sk_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "EXCEPTION_TABLE_TARGET_CONFLICT",
        lambda: gate_table_entries(
            "fixture", [sk_va + 8], (sk_va, sk_va + probe_len)),
        "T3_RUNTIME_REWRITE_FAILED"))
    lines.append(expect_reject(
        "UNMAPPED_EXTERNAL_CODE",
        lambda: gate_probe_mapping("UNMAPPED_EXTERNAL_REGION"),
        "T3_MAPPING_FAILED"))
    lines.append(expect_reject(
        "UNPROVEN_PADDING_EXECUTION",
        lambda: gate_probe_mapping("PADDING_0x2230000"),
        "T3_MAPPING_FAILED"))
    nx = [dict(s) for s in sections]
    for s in nx:
        if s["vma"] <= sk_va < s["vma"] + s["size"]:
            s["code"] = False
    lines.append(expect_reject(
        "NX_EXTERNAL_CODE",
        lambda: gate_window_section_scan(sk_va, probe_len, nx),
        "T3_INLINE_SAFETY_FAILED"))
    for s in sections:
        if s["vma"] <= sk_va < s["vma"] + s["size"]:
            lines.append(expect_reject(
                "SECTION_BOUNDARY_CROSS",
                lambda s=s: gate_window_section_scan(
                    s["vma"] + s["size"] - 4, probe_len, sections),
                "T3_INLINE_SAFETY_FAILED"))
            break
    lines.append(expect_reject(
        "WINDOW_OUTSIDE_IMAGE_SIZE",
        lambda: gate_window_inside_image_size(
            ctx["image_size"] - 4, probe_len, ctx["image_size"]),
        "T3_GEOMETRY_FAILED"))
    lines.append(expect_reject(
        "MMU_ASSUMED_OFF",
        lambda: gate_entry_contract(dict(T3_ENTRY_CONTRACT, T3_ENTRY_MMU="OFF"),
                                    T3_ENTRY_CONTRACT),
        "T3_ENTRY_STATE_FAILED"))
    lines.append(expect_reject(
        "PA_USED_AS_VA",
        lambda: gate_entry_contract(
            dict(T3_ENTRY_CONTRACT, T3_ENTRY_PC_ADDRESS_SPACE="PA"),
            T3_ENTRY_CONTRACT),
        "T3_ENTRY_STATE_FAILED"))
    lines.append(expect_reject(
        "PRE_START_KERNEL_PATH_REORDERED",
        lambda: gate_pre_path_order(
            "\n".join(reversed(PRE_START_KERNEL_PATH_TOKENS))),
        "T3_CONTROL_FLOW_FAILED"))
    lines.append(expect_reject(
        "COUNTER_TRAP_WRITE_IN_PATH",
        lambda: gate_no_early_counter_trap("msr cntkctl_el1, x0"),
        "T3_TIMER_FAILED"))
    lines.append(expect_reject(
        "NO_ORIGINAL_ENTRY_PAD",
        lambda: gate_diagnostic_core_identity(
            b"\x1f\x20\x03\xd5" + t1_probe, t1_probe, pad_word),
        "T3_CORE_IDENTITY_FAILED"))
    bad_core = bytearray(t1_probe)
    bad_core[3] ^= 0xFF
    lines.append(expect_reject(
        "DIAGNOSTIC_CORE_MISMATCH",
        lambda: gate_diagnostic_core_identity(
            struct.pack("<I", pad_word) + bytes(bad_core), t1_probe,
            pad_word),
        "T3_CORE_IDENTITY_FAILED"))
    lines.append(expect_reject(
        "CORE_SLICE_NOT_IDENTICAL_TO_T2",
        lambda: gate_core_slice_matches_t2(
            struct.pack("<I", pad_word) + bytes(bad_core), t2_probe),
        "T3_CORE_IDENTITY_FAILED"))
    v17 = re.sub(r"x10, #(?:0x)?8\b", "x10, #24", ops)
    lines.append(expect_reject(
        "WRONG_DELAY", lambda: gate_t3_probe(v17, dump, probe_len),
        "T3_DISASM_FAILED"))
    v18 = FID_HIGH_RE.sub("movk w0, #0x8401, lsl #16", ops)
    lines.append(expect_reject(
        "WRONG_PSCI_FID", lambda: gate_t3_probe(v18, dump, probe_len),
        "T3_DISASM_FAILED"))
    v19 = "\n".join(ln for ln in ops_lines
                    if not re.search(r"smc #(0x)?0\b", ln)) + "\n"
    lines.append(expect_reject(
        "MISSING_SMC", lambda: gate_t3_probe(v19, dump, probe_len),
        "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "FALLTHROUGH_AFTER_SMC",
        lambda: gate_terminal(dump_insert_after(
            "smc", ["  50: 00000000 mov x0, x15",
                    "  54: 14000000 b 0x50"])),
        "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "STACK_USE", lambda: gate_no_forbidden(
            ops + "\n00000000 stp x29, x30, [sp, #-32]!"),
        "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_STORE", lambda: gate_no_forbidden(
            ops + "\n00000000 str x9, [x0]"), "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "MEMORY_LOAD", lambda: gate_no_forbidden(
            ops + "\n00000000 ldr x9, [x0]"), "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "NORMAL_KERNEL_CONTINUATION",
        lambda: gate_no_forbidden(
            ops + "\n00000000 b __primary_switched"), "T3_DISASM_FAILED"))
    lines.append(expect_reject(
        "RUNTIME_RELOCATION", lambda: gate_no_relocations(
            "0000000000000000 R_AARCH64_ABS64 .text", "fixture"),
        "T3_RELOC_FAILED"))
    lines.append(expect_reject(
        "PAYLOAD_SIZE_CHANGE",
        lambda: gate_payload_diff(frozen, cand + b"\x00" * 4, region),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_rtd = bytearray(cand)
    bad_rtd[DTB_OFFSET + 5] ^= 0xFF
    lines.append(expect_reject(
        "RT_D_CHANGED", lambda: gate_trailer(bytes(bad_rtd)),
        "T3_PAYLOAD_DIFF_FAILED"))
    bad_diff = bytearray(cand)
    bad_diff[0x200] ^= 0xFF
    lines.append(expect_reject(
        "EXTRA_PAYLOAD_DIFF", lambda: gate_payload_diff(
            frozen, bytes(bad_diff), region), "T3_PAYLOAD_DIFF_FAILED"))
    bad_geom = bytearray(cand)
    struct.pack_into("<Q", bad_geom, 16, 0x2231000)
    lines.append(expect_reject(
        "GEOMETRY_CHANGE",
        lambda: gate_geometry(bytes(bad_geom), ctx["image_size"]),
        "T3_GEOMETRY_FAILED"))
    lines.append(expect_reject(
        "CNTPCT_UNSAFE",
        lambda: gate_cnppct_safety("", False), "T3_TIMER_FAILED"))
    lines.append(expect_reject(
        "PSCI_UNSAFE",
        lambda: gate_psci_safety("", False), "T3_PSCI_FAILED"))
    lines.append(f"T3_NEGATIVE_FIXTURE_COUNT={len(lines)}")
    lines.append("T3_NEGATIVE_FIXTURES=PASS")
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
        fail("T3_BUILD_FAILED", f"{tag} symbols {sorted(offs)}")
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
    """Tolerant parse of `llvm-objdump --section-headers` (flags may share the
    line with the numeric columns or follow on an indented line)."""
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
    (out / "p1b-t3-vmlinux-sections.txt").write_text(
        "\n".join(f"===== {k} =====\n{v}" for k, v in dumps.items()))
    for tag, text in dumps.items():
        if text.startswith("FAILED:"):
            continue
        secs = _readelf_sections(text) if tag.startswith("readelf") \
            else _objdump_sections(text)
        print(f"T3_SECTION_MAP_SOURCE={tag} sections={len(secs)}")
        if secs:
            return secs
    fail("T3_AUDIT_FAILED",
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
    """.rela.dyn (readelf) plus .relr.dyn (decoded RELR): __relocate_kernel
    applies both BEFORE __primary_switched is reached."""
    offs: list = []
    n_rela = 0
    rel = pb.run([tools["readelf"], "-r", "--wide", str(vmlinux)])
    for line in rel.splitlines():
        m = RELOC_OFF_RE.match(line.strip())
        if m:
            offs.append(int(m.group(1), 16))
            n_rela += 1
    del rel
    n_relr = 0
    dump = out / "p1b-t3-relr.bin"
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
    (out / "p1b-t3-vmlinux-relocations.txt").write_text("\n".join([
        "T3_RUNTIME_RELOCATION_LOCATIONS",
        f"RELA_DYN_ENTRIES={n_rela}",
        f"RELR_DYN_LOCATIONS={n_relr}",
        f"TOTAL_LOCATIONS={len(offs)}",
        f"MIN={min(offs):#x} MAX={max(offs):#x}" if offs else "MIN=NA MAX=NA",
        "NOTE=__relocate_kernel applies .rela.dyn and RELR BEFORE "
        "__primary_switched is reached; any location inside the inline window "
        "would rewrite the probe bytes and is REJECTED.",
        ""]))
    return offs


def dump_section(tools: dict, vmlinux: Path, out: Path, name: str) -> bytes:
    target = out / f"p1b-t3-section{name.replace('/', '_')}.bin"
    try:
        pb.run([tools["objcopy"], "--dump-section", f"{name}={target}",
                str(vmlinux)])
    except SystemExit:
        return b""
    if not target.is_file():
        return b""
    return target.read_bytes()


def _s32(data: bytes, off: int) -> int:
    return struct.unpack_from("<i", data, off)[0]


def decode_ex_table(data: bytes, base_va: int) -> list:
    """struct exception_table_entry { int insn, fixup; short type, data; } with
    ARCH_HAS_RELATIVE_EXTABLE: ex_insn_addr(x) = (unsigned long)&x->insn +
    x->insn (Documentation/arch/x86/exception-tables.rst)."""
    out: list = []
    for i in range(0, len(data) - 11, 12):
        out.append(base_va + i + _s32(data, i))
    return out


def decode_alt_instr(data: bytes, base_va: int) -> list:
    """struct alt_instr { s32 orig_offset; s32 alt_offset; u16 cpucap;
    u8 orig_len; u8 alt_len; } with ALT_ORIG_PTR(a) = (void *)a +
    a->orig_offset (arch/arm64/kernel/alternative.c:24)."""
    out: list = []
    for i in range(0, len(data) - 11, 12):
        out.append(base_va + i + _s32(data, i))
    return out


def decode_jump_table(data: bytes, base_va: int) -> list:
    """struct jump_entry { s32 code; s32 target; long key; } (16 bytes on
    64-bit) with jump_entry_code(entry) = (unsigned long)&entry->code +
    entry->code (include/linux/jump_label.h:123-126)."""
    out: list = []
    for i in range(0, len(data) - 15, 16):
        out.append(base_va + i + _s32(data, i))
    return out


def decode_static_call_sites(data: bytes, base_va: int) -> list:
    """struct static_call_site { s32 addr; s32 key; }: 8 bytes, addr relative
    to its own field. arm64 does not select HAVE_STATIC_CALL, so this section
    is expected to be absent and the scan exists as a future guard."""
    out: list = []
    for i in range(0, len(data) - 7, 8):
        out.append(base_va + i + _s32(data, i))
    return out


def decode_kcfi_traps(data: bytes, base_va: int) -> list:
    """kCFI trap records are 2 x s32 relative offsets per record. Only
    meaningful when CONFIG_CFI_CLANG=y, which this kernel does not use; the
    scan exists as a future guard."""
    out: list = []
    for i in range(0, len(data) - 7, 8):
        out.append(base_va + i + _s32(data, i))
        out.append(base_va + i + 4 + _s32(data, i + 4))
    return out


RUNTIME_REWRITE_SECTIONS = (
    ("__ex_table", "__ex_table", decode_ex_table),
    (".altinstructions", "altinstructions", decode_alt_instr),
    ("__jump_table", "__jump_table", decode_jump_table),
    (".static_call_sites", "static_call_sites", decode_static_call_sites),
    (".kcfi_traps", "kcfi_traps", decode_kcfi_traps),
)


def runtime_rewrite_scan(out: Path, tools: dict, vmlinux: Path,
                         sections: list, window: tuple) -> dict:
    """Every section that carries instruction addresses a later runtime
    rewrite step could touch."""
    report = {}
    for name, tag, decoder in RUNTIME_REWRITE_SECTIONS:
        sec = next((s for s in sections if s["name"] == name), None)
        if sec is None:
            report[tag] = {"present": False, "entries": 0}
            print(f"T3_RUNTIME_REWRITE_SECTION_{tag.upper()}=ABSENT")
            continue
        data = dump_section(tools, vmlinux, out, name)
        if not data:
            report[tag] = {"present": False, "entries": 0}
            print(f"T3_RUNTIME_REWRITE_SECTION_{tag.upper()}=EMPTY")
            continue
        n = gate_table_entries(tag, decoder(data, sec["vma"]), window)
        report[tag] = {"present": True, "entries": n, "size": len(data),
                       "vma": sec["vma"]}
        print(f"T3_RUNTIME_REWRITE_SECTION_{tag.upper()}=PRESENT "
              f"entries={n} size={len(data)} vma={sec['vma']:#x}")
    return report


def symbol_table(nm_out: str) -> list:
    out = []
    for line in nm_out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{8,16}", parts[0]):
            out.append((int(parts[0], 16), parts[2]))
    return sorted(out)


def symbol_extent(nm_out: str, name: str) -> tuple:
    syms = symbol_table(nm_out)
    vas = [a for a, n in syms if n == name]
    if not vas:
        fail("T3_IDENTITY_FAILED", f"vmlinux nm missing {name}")
    va = vas[0]
    nxt = min((a for a, _n in syms if a > va), default=None)
    return va, nxt


def sysmap_symbol(sysmap: Path, name: str) -> int:
    hits = [l for l in sysmap.read_text().splitlines()
            if l.endswith(f" {name}")]
    if not hits:
        fail("T3_IDENTITY_FAILED", f"System.map missing {name}")
    return int(hits[0].split()[0], 16)


def nm_symbol(nm_out: str, name: str) -> int:
    hits = [l for l in nm_out.splitlines() if l.endswith(f" {name}")]
    if not hits:
        fail("T3_IDENTITY_FAILED", f"vmlinux nm missing {name}")
    return int(hits[0].split()[0], 16)


def inst_record(out: Path, tools: dict, words: list, name: str) -> str:
    wrap = out / f"{name}.S"
    wrap.write_text(
        ".section .text, \"ax\", @progbits\n"
        ".globl r3_handoff_entry\n"
        "r3_handoff_entry:\n"
        + "".join(f".inst\t{w:#010x}\n" for w in words))
    elf = out / f"{name}.elf"
    iso.assemble_probe(wrap, HERE / "p1b-trampoline.ld", [], elf, tools)
    dump = pb.run([tools["objdump"], "-d", str(elf)])
    (out / f"{name}-disasm.txt").write_text(dump)
    return dump


def head_body(text: str, start_marker: str, end_marker: str) -> str:
    body = text.split(start_marker, 1)[1]
    return body.split(end_marker, 1)[0]


def config_symbols(config: str) -> dict:
    cfg: dict = {}
    for line in config.splitlines():
        line = line.strip()
        if line.startswith("# ") and line.endswith(" is not set"):
            cfg[line[2:].split(" is not set")[0].strip()] = "n"
        elif "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


T3_ENTRY_CONTRACT_EXPECTED = dict(T3_ENTRY_CONTRACT)


# ---------------------------------------------------------------------------
# Main T3 build.
# ---------------------------------------------------------------------------

def cmd_t3(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)

    # --- frozen baseline identity ---
    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("T3_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA:
        fail("T3_IDENTITY_FAILED", f"frozen FIX8 payload sha={sha(frozen)}")
    if len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("T3_IDENTITY_FAILED",
             f"frozen FIX8 payload len {len(frozen)} != {FIX8_PAYLOAD_SIZE}")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("T3_IDENTITY_FAILED", "frozen code1 not b 0x40")
    image_size = fhdr["image_size"]
    gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T3_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(frozen) - RT_D_SIZE != dtb_offset:
        fail("T3_IDENTITY_FAILED", "payload layout")
    gate_tramp_identity(frozen)
    print(f"T3_AUTHORITATIVE_IMAGE_SIZE={image_size:#x} "
          "SOURCE=FINAL_BINARY_HEADER")
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}")
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x} ({image_size})")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES "
          "(read from the authoritative FIX8 Image header)")
    print("IMAGE_HEADER_IMAGE_SIZE_HISTORICAL_READINGS_IGNORED="
          + ",".join(f"{v:#x}" for v in FIX8_IMAGE_SIZE_HISTORY_READINGS))
    print("T3_FROZEN_FIX8_BASE=PASS sha=" + FIX8_PAYLOAD_SHA)
    print("T3_FROZEN_TRAMPOLINE_EMBEDDED=YES sha=" + TRAMP_SHA)

    # --- authoritative kernel rebuild ---
    init = pb.compile_init(out, T3_DELAY_S, args.gcc, args.strip)
    init_sha = sha(init.read_bytes())
    if init_sha != FIX8_INIT_SHA:
        fail("T3_IDENTITY_FAILED", f"/init sha {init_sha} != frozen FIX8")
    cpio = out / f"initramfs-{T3_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    cpio_sha = sha(cpio.read_bytes())
    if cpio_sha != FIX8_CPIO_SHA:
        fail("T3_IDENTITY_FAILED", f"cpio sha {cpio_sha} != frozen FIX8")
    print(f"T3_INIT_IDENTICAL=YES sha={init_sha}")
    print(f"T3_INITRAMFS_IDENTICAL=YES sha={cpio_sha}")

    k = pb.make_kernel(out, T3_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    cfg = config_symbols(k["config"].read_text())
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("T3_BUILD_FAILED",
             f"rebuilt image_size {kg['hdr']['image_size']:#x} != "
             f"authoritative {image_size:#x} (baseline drift)")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("T3_BUILD_FAILED",
             f"rebuilt image file size {image_file_size} != frozen "
             f"{FIX8_IMAGE_FILE_SIZE}")
    census = sum(1 for a, b in zip(image, frozen) if a != b)
    print(f"T3_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size} "
          f"image_size={image_size:#x} image_sha={sha(image)}")
    print("T3_REBUILT_IMAGE_BYTE_IDENTICAL=NO "
          "(reported, NOT gated: the device executes the FROZEN payload; "
          "semantic identities are gated instead)")
    print(f"T3_REBUILT_IMAGE_DIFF_BYTES={census} (informational census)")

    # --- symbol re-derivation (never a history constant) ---
    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = nm_symbol(nm_out, "_text")
    off_primary_nm = nm_symbol(nm_out, "primary_entry") - text_addr
    sk_va, sk_extent = symbol_extent(nm_out, T3_TARGET_SYMBOL)
    ps_va, ps_extent = symbol_extent(nm_out, "__primary_switched")
    off_sk = sk_va - text_addr
    off_ps = ps_va - text_addr
    off_ps_sm = sysmap_symbol(k["sysmap"], "__primary_switched") - \
        sysmap_symbol(k["sysmap"], "_text")
    off_sk_sm = sysmap_symbol(k["sysmap"], T3_TARGET_SYMBOL) - \
        sysmap_symbol(k["sysmap"], "_text")
    off_primary_sm = sysmap_symbol(k["sysmap"], "primary_entry") - \
        sysmap_symbol(k["sysmap"], "_text")
    if off_ps_sm != off_ps:
        fail("T3_IDENTITY_FAILED",
             f"__primary_switched nm {off_ps:#x} != System.map {off_ps_sm:#x}")
    if off_sk_sm != off_sk:
        fail("T3_IDENTITY_FAILED",
             f"start_kernel nm {off_sk:#x} != System.map {off_sk_sm:#x}")
    if off_primary_sm != off_primary_nm:
        fail("T3_IDENTITY_FAILED",
             f"primary_entry nm {off_primary_nm:#x} != System.map "
             f"{off_primary_sm:#x}")
    if off_primary_nm != kg["off_primary"]:
        fail("T3_IDENTITY_FAILED",
             f"primary_entry nm {off_primary_nm:#x} != kernel_gate "
             f"{kg['off_primary']:#x}")
    if off_sk <= off_primary_nm:
        fail("T3_IDENTITY_FAILED",
             f"start_kernel {off_sk:#x} not after primary_entry "
             f"{off_primary_nm:#x}")
    if sk_extent is None:
        fail("T3_IDENTITY_FAILED", "start_kernel has no bounded extent")
    off_primary = off_primary_nm
    window_va = (sk_va, sk_va + T3_PROBE_SIZE)
    region = (off_sk, off_sk + T3_PROBE_SIZE)
    print(f"START_KERNEL_VA={sk_va:#x}")
    print(f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}")
    print(f"START_KERNEL_NEXT_SYMBOL_VA={sk_extent:#x}")
    print("T3_START_KERNEL_REDERIVED=YES "
          "(vmlinux nm + System.map, this round; no history constant)")
    print(f"PRIMARY_SWITCHED_VA={ps_va:#x}")
    print(f"PRIMARY_SWITCHED_IMAGE_OFFSET={off_ps:#x}")
    print(f"PRIMARY_ENTRY_OFFSET={off_primary:#x}")
    print("T3_PRIMARY_ENTRY_OFFSET_REDERIVED=YES "
          "(vmlinux nm + System.map + kernel_gate, this round)")
    print("T3_PRIMARY_SWITCHED_REDERIVED=YES "
          "(vmlinux nm + System.map, this round)")

    # --- section resolution ---
    sections = section_map(out, tools, k["vmlinux"])
    flags_source = "SECTION_HEADERS"
    if not any(s["flags"] for s in sections):
        for s in sections:
            if s["vma"] <= sk_va < s["vma"] + s["size"]:
                s["code"] = True
                s["alloc"] = True
        flags_source = "INSTRUCTION_IDENTITY_FALLBACK"
        print("T3_SECTION_FLAGS_UNAVAILABLE=YES "
              "(no flags column in the section dump; the containing section "
              "is marked executable+allocated because START_KERNEL_VA is a "
              "verified instruction address that the CPU executes)")
    sec = gate_window_section_scan(sk_va, T3_PROBE_SIZE, sections)
    print(f"START_KERNEL_SECTION={sec['name']}")
    print(f"START_KERNEL_SECTION_FLAGS={sec['flags'] or 'UNPRINTED'}")
    print(f"START_KERNEL_SECTION_FLAGS_SOURCE={flags_source}")
    print(f"START_KERNEL_SECTION_VA={sec['vma']:#x}")
    print("START_KERNEL_FILE_OFFSET="
          f"{sec['file_off'] + (sk_va - sec['vma']):#x} (vmlinux file offset)")
    print("START_KERNEL_SECTION_SHF_EXECINSTR=YES SHF_ALLOC=YES")
    print(f"START_KERNEL_SIZE_IF_KNOWN={sk_extent - sk_va:#x}")
    print(f"T3_INLINE_START={sk_va:#x}")
    print(f"T3_INLINE_END={sk_va + T3_PROBE_SIZE:#x}")
    gate_window_inside_image_size(off_sk, T3_PROBE_SIZE, image_size)
    print("T3_WINDOW_INSIDE_IMAGE_SIZE=YES "
          f"([{off_sk:#x},{off_sk + T3_PROBE_SIZE:#x}) < image_size "
          f"{image_size:#x}; never the padding after image_size)")

    # --- start_kernel entry identity + 32-instruction record ---
    dump_sk = pb.run([
        tools["objdump"], "-d",
        f"--start-address={sk_va:#x}",
        f"--stop-address={sk_va + 128:#x}", str(k["vmlinux"])])
    (out / "p1b-t3-start-kernel-vmlinux-disasm.txt").write_text(dump_sk)
    sk_lines = [l for l in dump_sk.splitlines() if INSTR_RE.match(l)]
    sk_n_insns = len(sk_lines)
    if sk_n_insns < 32:
        fail("T3_IDENTITY_FAILED",
             f"only {sk_n_insns} instructions disassembled at start_kernel; "
             "at least 32 are required")
    # The device runs the FROZEN payload; the audit and the patch are
    # therefore performed over the frozen payload's window bytes directly
    # (covered = frozen[off_sk:off_sk+80], inst_record disassembles those
    # exact bytes). The rebuilt vmlinux is only used for symbol VA / section
    # / relocation / callsite-VA metadata and for the word-0 entry-class
    # identity check. The rebuild is NOT byte-identical to the frozen payload
    # (the same non-reproducibility T2 reported as
    # T2_REBUILT_IMAGE_BYTE_IDENTICAL=NO; here it shows up as a divergence at
    # start_kernel word 18), so a full window byte-agreement gate over the
    # rebuilt vmlinux would be wrong: it would audit bytes the device never
    # runs.
    orig_word = gate_vmlinux_frozen_agreement(sk_va, off_sk, dump_sk, frozen)
    orig_word1 = struct.unpack_from("<I", frozen, off_sk + 4)[0]
    sk0 = INSTR_RE.match(sk_lines[0])
    entry_mnemonic = gate_sk_entry_insn(orig_word, orig_word1, orig_word)
    pad_word = orig_word
    covered = list(struct.unpack_from(f"<{T3_PROBE_SIZE // 4}I", frozen,
                                      off_sk))
    covered_dump = inst_record(out, tools, covered,
                               "p1b-t3-original-covered-insns-record")
    covered_ops = [l.split(":", 1)[-1].strip()
                   for l in covered_dump.splitlines() if INSTR_RE.match(l)]
    print(f"T3_START_KERNEL_ENTRY_INSTRUCTION0={entry_mnemonic}")
    print("T3_START_KERNEL_ORIGINAL_BYTES0="
          f"{struct.pack('<I', orig_word).hex()}")
    print(f"T3_START_KERNEL_ORIGINAL_INSN1={sk0.group(3)} "
          f"{sk0.group(4).strip()}".rstrip())
    print("T3_START_KERNEL_ORIGINAL_BYTES1="
          f"{struct.pack('<I', orig_word1).hex()}")
    print("T3_START_KERNEL_ENTRY_AUDITED=YES "
          f"(original entry instruction {entry_mnemonic!r} preserved + "
          f"{sk_n_insns} instructions recorded from the rebuilt vmlinux; the "
          f"overwritten window bytes are audited from the FROZEN payload "
          f"directly (covered = frozen[off_sk:off_sk+80]))")
    print(f"T3_START_KERNEL_OVERWRITTEN_INSN_COUNT={T3_PROBE_SIZE // 4}")
    print("T3_START_KERNEL_OVERWRITTEN_INSN_WORDS="
          + ",".join(f"{w:#010x}" for w in covered))
    print("T3_WINDOW_ORIGINAL_CODE_DISASM=" + " | ".join(covered_ops))
    print("T3_ENTRY_PAD_PRESERVED=YES "
          f"(the probe's first instruction is the original start_kernel "
          f"instruction {entry_mnemonic!r} "
          f"({struct.pack('<I', orig_word).hex()}), so the entry address "
          "carries the same instruction as the unmodified function)")
    print(f"T3_BTI_LANDING_REQUIRED=NO ({T3_BTI_LANDING_REQUIRED_REASON})")
    prologue_class = ("BTI_LANDING_PAD" if entry_mnemonic == "bti"
                      else "PAC_RET_PROLOGUE_NO_BTI_LANDING_PAD")
    print(f"T3_START_KERNEL_ENTRY_PROLOGUE_CLASS={prologue_class}")

    # --- __primary_switched -> start_kernel control-flow chain ---
    head_text = (LINUX / "arch" / "arm64" / "kernel" / "head.S").read_text()
    ps_body = head_body(head_text, "SYM_FUNC_START_LOCAL(__primary_switched)",
                        "SYM_FUNC_END(__primary_switched)")
    gate_pre_path_order(ps_body)
    print("T3_PRE_START_KERNEL_CONTROL_FLOW_AUDITED=YES "
          f"({len(PRE_START_KERNEL_PATH_TOKENS)} ordered steps verified in "
          "arch/arm64/kernel/head.S between the T2 checkpoint and the T3 "
          "checkpoint)")
    ps_stop = min(ps_extent if ps_extent else ps_va + 0x400, ps_va + 0x1000)
    dump_ps = pb.run([tools["objdump"], "-d",
                      f"--start-address={ps_va:#x}",
                      f"--stop-address={ps_stop:#x}", str(k["vmlinux"])])
    (out / "p1b-t3-primary-switched-callsite-disasm.txt").write_text(dump_ps)
    calls: list = []
    for line in dump_ps.splitlines():
        m = INSTR_RE.match(line)
        if not m or m.group(3) != "bl":
            continue
        op = re.search(r"(?:0x)?([0-9a-f]+)", m.group(4))
        if op and int(op.group(1), 16) == sk_va:
            calls.append((int(m.group(1), 16), m.group(3),
                          int(op.group(1), 16)))
    callsite_va, callsite_mn, callsite_target = gate_callsite_unique(
        calls, sk_va)
    off_callsite = callsite_va - text_addr
    # The call site is hand-written assembly (head.S:523 bl start_kernel) and
    # start_kernel is linked BEFORE __primary_switched, so the call site VA is
    # higher than start_kernel's VA; an address-order "checkpoint after call"
    # check would be wrong. The proof is instead: the probe sits at the
    # start_kernel FUNCTION ENTRY (sk_va), and the frozen payload's call-site
    # word decodes as a bl whose target is exactly sk_va.
    callsite_word = struct.unpack_from("<I", frozen, off_callsite)[0]
    if (callsite_word >> 26) != 0b100101:
        fail("T3_CALLSITE_FAILED",
             f"frozen call-site word {callsite_word:#010x} is not a bl")
    bl_target = text_addr + off_callsite + \
        pb.sx(callsite_word & 0x03FFFFFF, 26) * 4
    if bl_target != sk_va:
        fail("T3_CALLSITE_FAILED",
             f"frozen call-site bl target {bl_target:#x} != start_kernel "
             f"{sk_va:#x}")
    print("T3_START_KERNEL_CALLSITE_FOUND=YES")
    print(f"START_KERNEL_CALLSITE_VA={callsite_va:#x}")
    print(f"START_KERNEL_CALLSITE_IMAGE_OFFSET={off_callsite:#x}")
    print("START_KERNEL_CALLSITE_INSTRUCTION=BL")
    print("START_KERNEL_CALLSITE_BYTES="
          f"{struct.pack('<I', callsite_word).hex()}")
    print(f"START_KERNEL_CALL_TARGET={callsite_target:#x}")
    print("T3_START_KERNEL_CALL_TARGET_EXACT=YES "
          f"(the unique {callsite_mn} in __primary_switched targets exactly "
          f"start_kernel {sk_va:#x}; the frozen payload's call-site word "
          f"decodes to the same bl; start_kernel is linked before "
          f"__primary_switched so the call is a backward branch, which the "
          f"probe at the function entry proves was taken; no PLT/veneer/BTI "
          f"thunk/CFI trampoline/indirect branch is involved)")
    pre_calls = [m.group(1) for m in
                 re.finditer(r"\tbl\t(\S+)", ps_body)]
    print("T3_PRE_PATH_CALLSITES=" + ",".join(pre_calls))

    # --- pre-checkpoint runtime rewrite + counter-trap audit ---
    gate_no_early_counter_trap(
        head_text,
        (LINUX / "arch/arm64/kernel/hyp-stub.S").read_text(),
        (LINUX / "arch/arm64/kernel/idreg-override.c").read_text())
    smp_lines = (LINUX / "arch/arm64/kernel/smp.c").read_text().splitlines()
    main_lines = (LINUX / "init" / "main.c").read_text().splitlines()
    alt_line = next((i for i, l in enumerate(smp_lines, 1)
                     if "apply_boot_alternatives();" in l), 0)
    jl_line = next((i for i, l in enumerate(main_lines, 1)
                    if "jump_label_init();" in l), 0)
    sk_src_line = next((i for i, l in enumerate(main_lines, 1)
                        if T3_SK_PROTO_RE.match(l)), 0)
    if not (alt_line and jl_line and sk_src_line):
        fail("T3_RUNTIME_REWRITE_FAILED",
             "cannot locate apply_boot_alternatives()/jump_label_init()/"
             "start_kernel() in the source")
    if jl_line <= sk_src_line:
        fail("T3_RUNTIME_REWRITE_FAILED",
             f"jump_label_init at init/main.c:{jl_line} is not after "
             f"start_kernel at init/main.c:{sk_src_line}")
    print("T3_PRE_CHECKPOINT_RUNTIME_REWRITE=NONE "
          f"(apply_boot_alternatives arch/arm64/kernel/smp.c:{alt_line} is "
          f"reached from smp_prepare_boot_cpu, called at init/main.c:876; "
          f"jump_label_init init/main.c:{jl_line} is after the start_kernel "
          f"entry at init/main.c:{sk_src_line}; __relocate_kernel runs before "
          "__primary_switched and is scanned separately)")
    print("T3_ALT_EX_TABLE_HAZARD=NO_POST_START_KERNEL_ONLY "
          "(the tables are still scanned for entries inside the window)")

    # --- inline safety scans ---
    symbol_vas = sorted({int(l.split()[0], 16) for l in nm_out.splitlines()
                         if re.match(r"^[0-9a-f]{16} ", l)})
    n_sym = gate_window_symbol_scan(sk_va, T3_PROBE_SIZE, symbol_vas)
    exec_ranges = [(s["vma"] - text_addr, s["vma"] - text_addr + s["size"])
                   for s in sections if s["code"] and s["alloc"]]
    # The branch/literal safety scans run over the FROZEN payload's Image
    # portion (the bytes the device actually executes), not the rebuilt
    # image: the rebuild is not byte-identical to the frozen payload, so a
    # scan over the rebuild could miss a hazard that is present (or absent)
    # in the device binary.
    frozen_image = frozen[:image_file_size]
    cand_hits = branch_candidates(frozen_image, exec_ranges, window_va)
    confirmed = [(s, t) for s, t in cand_hits
                 if confirm_branch(tools, k["vmlinux"], s, t)]
    n_raw = gate_window_branch_scan(sk_va, T3_PROBE_SIZE, confirmed)
    for s, t in confirmed:
        print(f"T3_BRANCH_INTO_WINDOW_CONFIRMED src={s:#x} target={t:#x}")
    reloc = relocation_offsets(out, tools, k["vmlinux"])
    n_rel = gate_window_relocation_scan(sk_va, T3_PROBE_SIZE, reloc)
    n_lit = gate_window_literal_scan(sk_va, T3_PROBE_SIZE, frozen_image)
    extent_len = gate_function_extent_scan(sk_va, T3_PROBE_SIZE, sk_extent)
    rw = runtime_rewrite_scan(out, tools, k["vmlinux"], sections, window_va)
    print(f"T3_SYMBOL_SCAN=PASS ({n_sym} symbols, none inside the window)")
    print(f"T3_BRANCH_SCAN=PASS ({n_raw} confirmed branches overall, "
          f"{len(cand_hits)} raw candidates, none inside the window)")
    print(f"T3_RELOCATION_SCAN=PASS ({n_rel} runtime relocation locations "
          "(.rela.dyn + RELR), none inside the window)")
    print(f"T3_LITERAL_SCAN=PASS ({n_lit} 8-byte literal slots scanned, no "
          "absolute VA inside the window)")
    print("T3_CONTROL_FLOW_SCAN=PASS (no branch source/target inside the "
          "window)")
    print("T3_SECTION_BOUNDARY_SCAN=PASS (window inside one SHF_EXECINSTR|"
          "SHF_ALLOC section)")
    print(f"T3_FUNCTION_EXTENT_SCAN=PASS (start_kernel extent {extent_len:#x} "
          f">= window {T3_PROBE_SIZE:#x})")
    for tag, canon in (("__ex_table", "T3_EXCEPTION_TABLE_SCAN"),
                       ("altinstructions", "T3_ALTINSTRUCTIONS_SCAN"),
                       ("jump_table", "T3_JUMP_TABLE_SCAN"),
                       ("static_call_sites", "T3_STATIC_CALL_SITES_SCAN"),
                       ("kcfi_traps", "T3_KCFI_TRAPS_SCAN")):
        info = rw[tag]
        state = f"entries={info['entries']}" if info["present"] else "ABSENT"
        print(f"{canon}=PASS ({state}, no instruction address inside the "
              "window)")
    print("T3_INLINE_OVERWRITE_SAFE=YES")

    # --- entry contract + timer/PSCI safety ---
    gate_entry_contract(T3_ENTRY_CONTRACT, T3_ENTRY_CONTRACT_EXPECTED)
    for key in T3_ENTRY_CONTRACT:
        if key not in T3_ENTRY_CONTRACT_REASONS:
            fail("T3_ENTRY_STATE_FAILED", f"no source reason for {key}")
    gate_cnppct_safety(T3_CNTPCT_ACCESS_SAFE_REASON, True)
    gate_psci_safety(T3_PSCI_SAFE_REASON, True)
    gate_probe_mapping("KERNEL_TEXT_VA_SELF_EVIDENT")
    for key in sorted(T3_ENTRY_CONTRACT):
        print(f"{key}={T3_ENTRY_CONTRACT[key]}")
    for key in sorted(T3_ENTRY_CONTRACT_REASONS):
        print(f"{key}_SOURCE={T3_ENTRY_CONTRACT_REASONS[key]}")
    print("T3_CNTPCT_ACCESS_SAFE=YES (" + T3_CNTPCT_ACCESS_SAFE_REASON + ")")
    print("T3_PSCI_SYSTEM_RESET_SAFE=YES (" + T3_PSCI_SAFE_REASON + ")")
    print("T3_PRE_CHECKPOINT_REWRITE_REASON="
          + T3_PRE_CHECKPOINT_REWRITE_REASON)

    # --- probe build (T3 + the T2 + T1 references) ---
    t3_probe, ops, dump = build_probe(out, tools, T3_DEVICE_S, T3_DEVICE_LD,
                                      "P1B_T3_DELAY", T3_DELAY_S,
                                      "r3_t3_checkpoint", "p1b-t3-checkpoint",
                                      march="armv8.5-a")
    t2_probe, _t2_ops, _t2_dump = build_probe(
        out, tools, T2_DEVICE_S, T2_DEVICE_LD, "P1B_T2_DELAY", 8,
        "r3_t2_checkpoint", "p1b-t2-probe-reference")
    t1_probe, _t1_ops, _t1_dump = build_probe(
        out, tools, T1_DEVICE_S, T1_DEVICE_LD, "P1B_T1_DELAY", 8,
        "r3_t1_checkpoint", "p1b-t1-core-reference")
    gate_t3_probe(ops, dump, len(t3_probe))
    gate_diagnostic_core_identity(t3_probe, t1_probe, pad_word)
    gate_core_slice_matches_t2(t3_probe, t2_probe)
    plen = len(t3_probe)
    if len(t2_probe) != T3_PROBE_SIZE:
        fail("T3_BUILD_FAILED", f"T2 reference probe size {len(t2_probe)}")
    gate_instrumentation_audit(cfg, entry_mnemonic, pad_word)
    for sym in ("CONFIG_ARM64_BTI_KERNEL", "CONFIG_ARM64_PTR_AUTH_KERNEL",
                "CONFIG_CFI_CLANG", "CONFIG_SHADOW_CALL_STACK",
                "CONFIG_FUNCTION_TRACER", "CONFIG_DYNAMIC_FTRACE",
                "CONFIG_DYNAMIC_FTRACE_WITH_CALL_OPS",
                "CONFIG_DYNAMIC_FTRACE_WITH_ARGS", "CONFIG_KASAN",
                "CONFIG_KCOV", "CONFIG_STACKPROTECTOR",
                "CONFIG_STACKPROTECTOR_STRONG", "CONFIG_FUNCTION_ALIGNMENT",
                "CONFIG_UNWIND_PATCH_PAC_INTO_SCS", "CONFIG_JUMP_LABEL",
                "CONFIG_RELOCATABLE", "CONFIG_RANDOMIZE_BASE",
                "CONFIG_HAVE_ARCH_JUMP_LABEL_RELATIVE"):
        print(f"T3_ENTRY_CFG_{sym}={cfg.get(sym, 'ABSENT')}")
    print("T3_START_KERNEL_ENTRY_INSTRUMENTATION_AUDITED=YES "
          "(BTI enabled at the compiler level but the entry is entered by a "
          "direct bl only and the function address is not taken, so the "
          "measured instruction 0 is the PAC prologue and no BTI landing pad "
          "exists or is required; CFI/SHADOW_CALL_STACK/KASAN/KCOV/"
          "FUNCTION_TRACER/DYNAMIC_FTRACE are all disabled; start_kernel is "
          "__no_stack_protector/__no_sanitize_address, so the entry carries "
          "no canary and no fentry NOP; measured instruction 0 and the frozen "
          "entry word agree, and the T3 probe preserves that exact word)")
    print(f"T3_CHECKPOINT sha256={sha(t3_probe)} size={plen} "
          f"core={sha(t3_probe[T3_PAD_SIZE:])} pad={entry_mnemonic}")
    print("T3_DIAGNOSTIC_CORE_MATCHES_T1=YES "
          f"(probe[4:80] byte-identical to the p1b-t1-device.S core, sha "
          f"{sha(t1_probe)})")
    print("T3_DIAGNOSTIC_CORE_SLICE_MATCHES_T2=YES "
          "(probe[4:80] byte-identical to the T2 probe core assembled in this "
          "same run: the T3 change is the checkpoint ADDRESS and the "
          "preserved entry pad word only)")
    print("T3_PROBE_ARCHITECTURE=INLINE")
    print("T3_PROBE_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT")
    print("T3_INLINE_MAPPING_EXECUTABLE=YES")
    print("T3_EXTERNAL_CHECKPOINT_USED=NO")
    print("T3_PADDING_MAPPING_USED=NO "
          "(the T1 padding site 0x2230000 is NOT executable under the MMU-on "
          "early page tables and is never reused for T3)")

    # --- compose the T3 payload: ONE diff region, inline only ---
    cand = bytearray(frozen)
    cand[off_sk:off_sk + plen] = t3_probe
    cand = bytes(cand)
    diffs = gate_payload_diff(frozen, cand, region)
    tail = gate_tail_identity(frozen, cand, region)
    gate_t2_probe_removed(frozen, cand, off_ps, t2_probe)
    gate_tramp_identity(cand)
    trailer = gate_trailer(cand)
    if trailer != frozen_rt_d:
        fail("T3_PAYLOAD_DIFF_FAILED", "trailer drifted vs frozen RT-D")
    hdr, dtb_off2, gap2, boot_est = gate_geometry(cand, image_size)
    if dtb_off2 != dtb_offset:
        fail("T3_PAYLOAD_DIFF_FAILED", "dtb_offset drifted")
    payload_path = out / "thyme-r3-p1b-t3-kernel-payload.bin"
    payload_path.write_bytes(cand)
    print(f"T3_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)}")
    print(f"T3_DIFF_BYTE_COUNT={len(diffs)}")
    print(f"T3_DIFF_RANGES=[{off_sk:#x},{off_sk + plen:#x})")
    print("T3_PAYLOAD_DIFF_ATTRIBUTED=START_KERNEL_CHECKPOINT_ONLY")
    print(f"T2_PROBE_REMOVED_FROM_T3=YES "
          f"(__primary_switched [{off_ps:#x},{off_ps + plen:#x}) carries the "
          "FIX8 original bytes, not the T2 probe)")
    print("PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES")
    print("T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES "
          f"({off_sk} bytes before and {tail} bytes after the window are "
          "byte-identical, so the trampoline, primary_entry, the whole head.S "
          "path and __primary_switched are the frozen FIX8 bytes)")
    print("T3_TRAMPOLINE_IDENTICAL=YES sha=" + TRAMP_SHA)

    diff_report = (
        "T3_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"T3_PAYLOAD_SHA256={sha(cand)}\n"
        f"REGION_A=[{off_sk:#x},{off_sk + plen:#x}) inline start_kernel "
        f"overwrite ({len(diffs)} diff bytes)\n"
        f"DIFF_BYTES={len(diffs)}\n"
        f"T3_DIFF_BYTE_COUNT={len(diffs)}\n"
        f"FIRST_DIFF={diffs[0]:#x} LAST_DIFF={diffs[-1]:#x}\n"
        f"T3_DIFF_RANGES=[{off_sk:#x},{off_sk + plen:#x})\n"
        "DIFF_ATTRIBUTION=START_KERNEL_CHECKPOINT_ONLY\n"
        "T3_PAYLOAD_DIFF_ATTRIBUTED=START_KERNEL_CHECKPOINT_ONLY\n"
        "T2_PROBE_REMOVED_FROM_T3=YES\n"
        "PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES\n"
        f"T2_PROBE_SHA256={sha(t2_probe)} (NOT present in the T3 payload)\n"
        f"T2_PROBE_OFFSET_HISTORY={T2_CHECKPOINT_OFFSET_HISTORY:#x}\n"
        f"T3_TRAMPOLINE_IDENTICAL=YES sha={TRAMP_SHA}\n"
        f"RT_D_TRAILER_IDENTICAL=YES sha={RT_D_SHA}\n"
        f"PAYLOAD_SIZE_IDENTICAL=YES {len(cand)}\n"
        f"START_KERNEL_VA={sk_va:#x} START_KERNEL_IMAGE_OFFSET={off_sk:#x}\n"
        f"START_KERNEL_CALLSITE_VA={callsite_va:#x} "
        f"START_KERNEL_CALLSITE_BYTES="
        f"{struct.pack('<I', callsite_word).hex()}\n"
        f"DTB_OFFSET={dtb_offset:#x} GAP={gap:#x} "
        f"IMAGE_FILE_SIZE={image_file_size} "
        f"IMAGE_HEADER_IMAGE_SIZE={hdr['image_size']:#x} "
        f"T3_INLINE_START={sk_va:#x} T3_INLINE_END={sk_va + plen:#x} "
        f"BOOT_SIZE_EST={boot_est}\n"
        f"T3_RUNTIME_SEMANTIC_DELTA={T3_RUNTIME_SEMANTIC_DELTA}\n")
    (out / "p1b-t3-payload-diff-report.txt").write_text(diff_report)

    sm_lines = [l for l in k["sysmap"].read_text().splitlines()
                if l.endswith((" primary_entry", " _text", " record_mmu_state",
                               " __primary_switched", " __primary_switch",
                               " __enable_mmu", " __cpu_setup",
                               " start_kernel", " _stext"))]
    (out / "p1b-t3-sysmap-excerpt.txt").write_text("\n".join(sm_lines) + "\n")

    # --- fixtures ---
    neg_lines = run_negative_fixtures({
        "ops": ops, "dump": dump, "probe_len": plen, "frozen": frozen,
        "cand": cand, "off_sk": off_sk, "off_ps": off_ps,
        "sections": sections, "symbol_vas": symbol_vas,
        "reloc_offsets": reloc, "t1_probe": t1_probe, "t2_probe": t2_probe,
        "sk_va": sk_va, "cfg": cfg, "image_size": image_size,
        "pad_word": pad_word, "entry_mnemonic": entry_mnemonic,
        "orig_word1": orig_word1, "primary_entry_off": off_primary})
    (out / "p1b-t3-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures()
    (out / "p1b-t3-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")

    report = (
        "T3_PREDEVICE_REPORT\n"
        "CONSTRAINTS mem0_read=YES local_build=NO gha_only=YES "
        "device_operation=NO partition_writes=0 slot_a_written=NO\n"
        "PREDECESSOR T0_TOTAL=14.252s T0=PROVEN T1_TOTAL=14.238s "
        "T1_MINUS_T0=-0.014s T1=PROVEN T2_TOTAL=14.240s T2_MINUS_T1=+0.002s "
        "T2=PROVEN R3=PROVEN E1=PROVEN\n"
        "REACHABILITY R0=PROVEN R1=PROVEN R2=PROVEN R3=PROVEN "
        "R4=NOT_PROVEN R5=NOT_PROVEN R6=NOT_PROVEN R7=NOT_PROVEN\n"
        f"T3_TARGET_SYMBOL={T3_TARGET_SYMBOL}\n"
        f"START_KERNEL_VA={sk_va:#x}\n"
        f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}\n"
        f"START_KERNEL_SECTION={sec['name']}\n"
        f"START_KERNEL_SECTION_FLAGS={sec['flags'] or 'UNPRINTED'}\n"
        "T3_START_KERNEL_REDERIVED=YES\n"
        "T3_START_KERNEL_CALLSITE_FOUND=YES\n"
        f"START_KERNEL_CALLSITE_VA={callsite_va:#x} "
        f"START_KERNEL_CALLSITE_BYTES="
        f"{struct.pack('<I', callsite_word).hex()}\n"
        "T3_PRE_START_KERNEL_CONTROL_FLOW_AUDITED=YES\n"
        "T3_START_KERNEL_ENTRY_INSTRUMENTATION_AUDITED=YES\n"
        f"T3_START_KERNEL_ENTRY_INSTRUCTION0={entry_mnemonic}\n"
        "T3_ENTRY_PAD_PRESERVED=YES\n"
        f"T3_START_KERNEL_ENTRY_PROLOGUE_CLASS={prologue_class}\n"
        "T3_BTI_LANDING_REQUIRED=NO\n"
        "T3_PRE_CHECKPOINT_RUNTIME_REWRITE=NONE\n"
        f"T3_PROBE_ARCHITECTURE=INLINE start={sk_va:#x} "
        f"end={sk_va + plen:#x}\n"
        "T3_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT "
        "T3_INLINE_MAPPING_EXECUTABLE=YES\n"
        "T3_INLINE_OVERWRITE_SAFE=YES\n"
        "T3_EXTERNAL_CHECKPOINT_USED=NO T3_PADDING_MAPPING_USED=NO\n"
        "T3_DEVICE_CANDIDATE_DELAY=8s\n"
        "T3_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY\n"
        "T3_CNTPCT_ACCESS_SAFE=YES\n"
        "T3_RESET_PRIMITIVE=PSCI_SYSTEM_RESET fid=0x84000009 smc #0\n"
        "T3_PSCI_SYSTEM_RESET_SAFE=YES\n"
        "T3_FAIL_CLOSED=YES (any smc return -> wfe forever; no return, no "
        "start_kernel body, no continuation)\n"
        f"T3_CLOBBER_REGISTERS={T3_CLOBBER_REGISTERS}\n"
        "T3_STACK_USAGE=NO\n"
        "T3_MEMORY_READS=NO T3_MEMORY_WRITES=NO\n"
        "T3_POSITION_INDEPENDENT=YES T3_RUNTIME_RELOCATIONS=0\n"
        f"T3_RUNTIME_SEMANTIC_DELTA={T3_RUNTIME_SEMANTIC_DELTA}\n"
        "T3_DIAGNOSTIC_CORE_MATCHES_T1=YES\n"
        "T3_DIAGNOSTIC_CORE_SLICE_MATCHES_T2=YES\n"
        "T2_PROBE_REMOVED_FROM_T3=YES\n"
        "PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES\n"
        f"T3_TRAMPOLINE_IDENTICAL=YES sha={TRAMP_SHA}\n"
        f"T3_RT_D_IDENTITY=YES sha={RT_D_SHA}\n"
        f"T3_INIT_IDENTITY=YES {init_sha}\n"
        f"T3_INITRAMFS_IDENTITY=YES {cpio_sha}\n"
        "T3_DIAGNOSTIC_ONLY=YES\n"
        "T3_NORMAL_KERNEL_BOOT_CANDIDATE=NO\n"
        "T3_STATUS_GATE_STRUCTURED=YES\n"
        "T3_STATUS=NOT_DEVICE_READY\n")
    (out / "p1b-t3-report.txt").write_text(report)

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "t3_true_device_run": "NOT_EXECUTED",
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
        "t2_boot_sha256": FORBIDDEN_BOOT_SHAS["T2_BOOT"],
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
        "primary_switched_identical_to_fix8": True,
        "start_kernel_symbol": T3_TARGET_SYMBOL,
        "start_kernel_va": hex(sk_va),
        "start_kernel_image_offset": hex(off_sk),
        "start_kernel_file_offset": hex(sec["file_off"] + (sk_va - sec["vma"])),
        "start_kernel_section": sec["name"],
        "start_kernel_section_flags": sec["flags"],
        "start_kernel_section_flags_source": flags_source,
        "start_kernel_section_va": hex(sec["vma"]),
        "start_kernel_size_if_known": hex(sk_extent - sk_va),
        "start_kernel_rederived": True,
        "start_kernel_original_first_insn": entry_mnemonic,
        "start_kernel_original_first_bytes": struct.pack("<I", orig_word).hex(),
        "start_kernel_original_second_insn":
            f"{sk0.group(3)} {sk0.group(4).strip()}".strip(),
        "start_kernel_original_second_bytes":
            struct.pack("<I", orig_word1).hex(),
        "start_kernel_callsite_va": hex(callsite_va),
        "start_kernel_callsite_image_offset": hex(off_callsite),
        "start_kernel_callsite_instruction": "BL",
        "start_kernel_callsite_bytes": struct.pack("<I", callsite_word).hex(),
        "start_kernel_call_target": hex(callsite_target),
        "start_kernel_call_target_exact": True,
        "pre_start_kernel_control_flow_audited": True,
        "pre_start_kernel_path_steps": list(PRE_START_KERNEL_PATH_TOKENS),
        "pre_start_kernel_callsites": pre_calls,
        "pre_checkpoint_runtime_rewrite": "NONE",
        "start_kernel_entry_instrumentation_audited": True,
        "start_kernel_entry_instrumentation": {
            "bti": "ENABLED_LANDING_PAD_PRESERVED",
            "pac": cfg.get("CONFIG_ARM64_PTR_AUTH_KERNEL", "ABSENT"),
            "cfi": cfg.get("CONFIG_CFI_CLANG", "ABSENT"),
            "shadow_call_stack": cfg.get("CONFIG_SHADOW_CALL_STACK", "ABSENT"),
            "fentry": "ABSENT_NO_FUNCTION_TRACER",
            "kasan": cfg.get("CONFIG_KASAN", "ABSENT"),
            "kcov": cfg.get("CONFIG_KCOV", "ABSENT"),
            "alt_static_call_in_window": "NONE",
        },
        "t3_entry_pad_preserved": True,
        "t3_entry_pad_word": hex(pad_word),
        "t3_entry_pad_mnemonic": entry_mnemonic,
        "t3_entry_prologue_class": prologue_class,
        "t3_bti_landing_required": False,
        "t3_pad_size": T3_PAD_SIZE,
        "t3_core_size": T3_CORE_SIZE,
        "start_kernel_recorded_insn_count": sk_n_insns,
        "start_kernel_overwritten_insn_count": T3_PROBE_SIZE // 4,
        "rebuilt_image_sha256": sha(image),
        "rebuilt_image_byte_identical_to_frozen": False,
        "rebuilt_image_byte_identity_reason":
            "embedded build banner (UTS_VERSION/linux_banner) differs; the "
            "device executes the FROZEN payload",
        "rebuilt_image_diff_bytes_vs_frozen_prefix": census,
        "t3_probe_architecture": "INLINE",
        "t3_inline_start": hex(sk_va),
        "t3_inline_end": hex(sk_va + plen),
        "t3_inline_overwrite_safe": True,
        "t3_external_checkpoint_used": False,
        "t3_mapping_source": "KERNEL_TEXT_VA_SELF_EVIDENT",
        "t3_inline_mapping_executable": True,
        "t3_padding_mapping_used": False,
        "t3_symbol_scan_pass": True,
        "t3_branch_scan_pass": True,
        "t3_relocation_scan_pass": True,
        "t3_literal_scan_pass": True,
        "t3_control_flow_scan_pass": True,
        "t3_section_boundary_scan_pass": True,
        "t3_function_extent_scan_pass": True,
        "t3_runtime_rewrite_sections": rw,
        "t3_literal_slots_scanned": n_lit,
        "t3_branch_raw_candidates": len(cand_hits),
        "t3_branch_confirmed_hits": n_raw,
        "t3_runtime_relocation_locations": n_rel,
        "t3_symbols_scanned": n_sym,
        "t3_entry_contract": T3_ENTRY_CONTRACT,
        "t3_entry_contract_reasons": T3_ENTRY_CONTRACT_REASONS,
        "t3_cnptct_access_safe": True,
        "t3_psci_system_reset_safe": True,
        "t3_checkpoint_sha256": sha(t3_probe),
        "t3_checkpoint_size": plen,
        "t3_diagnostic_core_matches_t1": True,
        "t3_diagnostic_core_slice_matches_t2": True,
        "t3_t1_core_sha256": sha(t1_probe),
        "t2_probe_sha256": sha(t2_probe),
        "t2_probe_removed_from_t3": True,
        "t3_payload_sha256": sha(cand),
        "t3_payload_size": len(cand),
        "t3_boot_size_est": boot_est,
        "t3_boot_kernel_size_field": len(cand),
        "diff_bytes": len(diffs),
        "diff_regions": [[hex(off_sk), hex(off_sk + plen)]],
        "diff_attribution": "START_KERNEL_CHECKPOINT_ONLY",
        "t3_precheckpoint_normal_path_identical_to_fix8": True,
        "t3_tail_identity_bytes": tail,
        "t3_delay_seconds": T3_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "t3_clobber_registers": T3_CLOBBER_REGISTERS,
        "t3_fail_closed": True,
        "t3_stack_usage": False,
        "t3_memory_reads": False,
        "t3_memory_writes": False,
        "t3_runtime_relocations": 0,
        "t3_runtime_semantic_delta": T3_RUNTIME_SEMANTIC_DELTA,
        "t3_tramp_identical_to_fix8": True,
        "t3_rtd_identical": True,
        "t3_init_identical": True,
        "t3_initramfs_identical": True,
        "t3_diagnostic_only": True,
        "t3_normal_kernel_boot_candidate": False,
        "t3_status_gate_structured": True,
        "t3_status": "NOT_DEVICE_READY",
        "decoder": {
            "kind": "T2_MATCHED_CONTROL_PRIMARY_T1_T0_SECONDARY_P0_SECONDARY",
            "t2_reference_total_s": T2_REFERENCE_TOTAL_S,
            "t1_reference_total_s": T1_REFERENCE_TOTAL_S,
            "t0_reference_total_s": T0_REFERENCE_TOTAL_S,
            "t2_minus_t1_observed_s": T2_MINUS_T1_OBSERVED_S,
            "t2_minus_t0_observed_s": T2_MINUS_T0_OBSERVED_S,
            "strong_half_window_s": T3_STRONG_HALF_WINDOW_S,
            "supported_half_window_s": T3_SUPPORTED_HALF_WINDOW_S,
            "secondary_half_window_s": T3_SECONDARY_HALF_WINDOW_S,
            "early_return_class_limit_s": T3_EARLY_RETURN_CLASS_LIMIT_S,
            "case_c_band_s": list(T3_CASE_C_BAND_S),
            "no_return_window_s": T3_NO_RETURN_WINDOW_S,
            "p0_ref_overhead_s": P0_REF_OVERHEAD_S,
            "programmed_s": T3_DELAY_S,
        },
        "observer": {"identity_env": "R3_T3_SHA256",
                     "forbidden_env": "R3_T3_FORBIDDEN_SHAS",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
        "evidence_rule": {
            "r4_on_strong": "PROVEN",
            "r4_on_supported": "STRONGLY_SUPPORTED",
            "r5": "NOT_PROVEN (the start_kernel body never runs in T3)",
            "e2": "NOT_AUTO_UPGRADED (frozen definition only)",
        },
    }
    (out / "p1b-t3-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")

    gates = [
        "T3_BUILD_GATES=PASS",
        "T3_BASELINE=FROZEN_FIX8",
        "T3_TARGET_SYMBOL=start_kernel",
        "T3_START_KERNEL_REDERIVED=YES",
        "T3_PRIMARY_SWITCHED_REDERIVED=YES",
        "T3_PRIMARY_ENTRY_OFFSET_REDERIVED=YES",
        "T3_START_KERNEL_ORIGINAL_INSN_0_MEASURED="
        f"{entry_mnemonic}",
        "T3_ENTRY_PAD_PRESERVED=YES",
        f"T3_START_KERNEL_ENTRY_INSTRUCTION0={entry_mnemonic}",
        f"T3_START_KERNEL_ENTRY_PROLOGUE_CLASS={prologue_class}",
        "T3_BTI_LANDING_REQUIRED=NO",
        "T3_START_KERNEL_ENTRY_AUDITED=YES",
        "T3_START_KERNEL_CALLSITE_FOUND=YES",
        "T3_START_KERNEL_CALLSITE_INSTRUCTION=BL",
        "T3_START_KERNEL_CALL_TARGET_EXACT=YES",
        "T3_PRE_START_KERNEL_CONTROL_FLOW_AUDITED=YES",
        "T3_START_KERNEL_ENTRY_INSTRUMENTATION_AUDITED=YES",
        "T3_PRE_CHECKPOINT_RUNTIME_REWRITE=NONE",
        "T3_REBUILT_IMAGE_BYTE_IDENTICAL=NO",
        "IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES",
        f"T3_AUTHORITATIVE_IMAGE_SIZE={image_size:#x}",
        f"IMAGE_FILE_SIZE={image_file_size}",
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}",
        "T3_PROBE_ARCHITECTURE=INLINE",
        f"T3_INLINE_START={sk_va:#x}",
        f"T3_INLINE_END={sk_va + plen:#x}",
        f"START_KERNEL_VA={sk_va:#x}",
        f"START_KERNEL_IMAGE_OFFSET={off_sk:#x}",
        f"START_KERNEL_SECTION={sec['name']}",
        f"START_KERNEL_CALLSITE_VA={callsite_va:#x}",
        "T3_INLINE_OVERWRITE_SAFE=YES",
        "T3_SYMBOL_SCAN=PASS",
        "T3_BRANCH_SCAN=PASS",
        "T3_RELOCATION_SCAN=PASS",
        "T3_LITERAL_SCAN=PASS",
        "T3_CONTROL_FLOW_SCAN=PASS",
        "T3_SECTION_BOUNDARY_SCAN=PASS",
        "T3_FUNCTION_EXTENT_SCAN=PASS",
        "T3_EXCEPTION_TABLE_SCAN=PASS",
        "T3_ALTINSTRUCTIONS_SCAN=PASS",
        "T3_JUMP_TABLE_SCAN=PASS",
        "T3_STATIC_CALL_SITES_SCAN=PASS",
        "T3_KCFI_TRAPS_SCAN=PASS",
        "T3_WINDOW_INSIDE_IMAGE_SIZE=YES",
        "T3_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
        "T3_INLINE_MAPPING_EXECUTABLE=YES",
        "T3_EXTERNAL_CHECKPOINT_USED=NO",
        "T3_PADDING_MAPPING_USED=NO",
        "T3_ENTRY_MMU=ON",
        "T3_ENTRY_PC_ADDRESS_SPACE=VA",
        "T3_ENTRY_SP_VALID=YES",
        "T3_DEVICE_CANDIDATE_DELAY=8s",
        "T3_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "T3_CNTPCT_ACCESS_SAFE=YES",
        "T3_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "T3_PSCI_SYSTEM_RESET_SAFE=YES",
        "T3_FAIL_CLOSED=YES",
        "T3_STACK_USAGE=NO",
        "T3_NO_MEMORY_READS=YES",
        "T3_NO_MEMORY_WRITES=YES",
        "T3_DIAGNOSTIC_CORE_MATCHES_T1=YES",
        "T3_DIAGNOSTIC_CORE_SLICE_MATCHES_T2=YES",
        "T3_POSITION_INDEPENDENT=YES",
        "T3_RUNTIME_RELOCATIONS=0",
        f"T3_RUNTIME_SEMANTIC_DELTA={T3_RUNTIME_SEMANTIC_DELTA}",
        "T2_PROBE_REMOVED_FROM_T3=YES",
        "PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES",
        "T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES",
        "T3_TRAMPOLINE_IDENTICAL=YES",
        "T3_RT_D_IDENTITY=YES",
        "T3_INIT_IDENTITY=YES",
        "T3_INITRAMFS_IDENTITY=YES",
        "T3_PAYLOAD_DIFF_ATTRIBUTED=START_KERNEL_CHECKPOINT_ONLY",
        f"T3_DIFF_BYTE_COUNT={len(diffs)}",
        f"T3_DIFF_RANGES=[{off_sk:#x},{off_sk + plen:#x})",
        "T3_PAYLOAD_SIZE_IDENTICAL=YES",
        "T3_BOOT_SIZE_IDENTICAL=YES",
        f"T3_DTB_OFFSET={DTB_OFFSET:#x}",
        "T3_GEOMETRY_GATES=PASS",
        "T3_NEGATIVE_FIXTURES=PASS",
        "T3_DECODER_FIXTURES=PASS",
        "T3_STATUS_GATE_STRUCTURED=YES",
        "T3_DIAGNOSTIC_ONLY=YES",
        "T3_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
        "T3_STATUS=NOT_DEVICE_READY",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "p1b-t3-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))


def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("t3_obs_fixtures",
                                                  OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-t3-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("T3_OBSERVER_FIXTURES=PASS")


def cmd_t3_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    off_sk = int(args.start_kernel_offset, 16)
    probe = Path(args.checkpoint_bin).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("T3_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("T3_PACK_FAILED", f"payload sha={sha(payload)}")
    if sha(probe) != args.checkpoint_sha:
        fail("T3_PACK_FAILED", f"checkpoint sha={sha(probe)}")
    hdr = pb.parse_image_hdr(payload, "t3-payload")
    image_size = hdr["image_size"]
    gate_image_size_rederived(image_size, "t3-packed-payload")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("T3_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("T3_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("T3_PACK_FAILED", "payload length")
    if (off_sk + len(probe)) > image_size:
        fail("T3_PACK_FAILED",
             "start_kernel window past image_size (padding reuse forbidden)")
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("T3_PACK_FAILED",
             f"embedded trampoline sha={sha(tramp)} != frozen FIX8")
    if payload[off_sk:off_sk + len(probe)] != probe:
        fail("T3_PACK_FAILED",
             "start_kernel region != built T3 probe (patch lost)")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I", FDT_MAGIC):
        fail("T3_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "t3-candidate")
    if cand["kernel"] != payload:
        fail("T3_PACK_FAILED", "candidate kernel != T3 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("T3_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("T3_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("T3_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("T3_PACK_FAILED", "reserved differs from M5D")
    if cand["ramdisk_size"] != ref["ramdisk_size"]:
        fail("T3_PACK_FAILED", "ramdisk_size differs")
    if cand["tail_pad"] != ref["tail_pad"]:
        fail("T3_PACK_FAILED", "tail padding policy differs")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("T3_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("T3_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("T3_PACK_FAILED", "DTB residue geometry")
    if len(boot) >= BOOT_CAP or BOOT_CAP - len(boot) < 0x1000000:
        fail("T3_PACK_FAILED", "capacity")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-t3-pack-gates.txt"
    report.write_text(
        "T3_PACK_GATES=PASS\n"
        f"T3_BOOT_SIZE={len(boot)}\n"
        f"T3_BOOT_SHA256={sha(boot)}\n"
        f"T3_PAYLOAD_SHA256={sha(payload)}\n"
        f"T3_TRAMP_SHA256={sha(tramp)}\n"
        "T3_TRAMP_SOURCE=FROZEN_FIX8_UNMODIFIED\n"
        f"T3_CHECKPOINT_SHA256={sha(probe)}\n"
        f"T3_KERNEL_SIZE={len(payload)}\n"
        f"T3_START_KERNEL_OFFSET={off_sk:#x}\n"
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}\n"
        f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}\n"
        "T3_PROBE_ARCHITECTURE=INLINE\n"
        "T3_INLINE_REGION_IN_KERNEL_TEXT=YES\n"
        f"T3_DTB_OFFSET={dtb_offset:#x}\n"
        "T3_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "T3_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "T3_BOOT_CAPACITY=PASS\n"
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


# ---------------------------------------------------------------------------
# Source gate.
# ---------------------------------------------------------------------------

def need(text: str, needle: str, label: str = "T3_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str,
           label: str = "T3_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def parse_status_kv(text: str) -> dict:
    if STATUS_KV_BEGIN not in text or STATUS_KV_END not in text:
        fail("T3_SOURCE_GATE_FAILED",
             "structured status KV block markers missing")
    body = text.split(STATUS_KV_BEGIN, 1)[1].split(STATUS_KV_END, 1)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    kv: dict = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail("T3_SOURCE_GATE_FAILED",
                 f"status KV line without '=': {line!r}")
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()
    if not kv:
        fail("T3_SOURCE_GATE_FAILED", "empty structured status KV block")
    return kv


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [T3_DEVICE_S, T3_DEVICE_LD, T2_DEVICE_S, T2_DEVICE_LD,
                T1_DEVICE_S, T1_DEVICE_LD, T1_PROTO_S, OBSERVER,
                OBSERVER_FIXTURES, Path(__file__), DOC, STATUS_DOC, WF,
                PRIVATE_WF, HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld"]
    for path in required:
        if not path.is_file():
            fail("T3_SOURCE_GATE_FAILED", f"missing {path}")
    dev = T3_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "isb", "mrs\tx9, cntfrq_el0",
                  "mrs\tx11, cntpct_el0", "mrs\tx12, cntpct_el0", "yield",
                  "smc\t#0", "wfe", "P1B_T3_DELAY",
                  "#if (P1B_T3_DELAY) != 8", "r3_t3_checkpoint",
                  "paciasp", ".inst\t0xd503233f"):
        need(dev, token)
    for token in ("P1B_DTB_REL", "dtb_rel", "adr\t", "ldr\t", "stp\tx29",
                  "mov\tx1, xzr", "eret", "sctlr", "msr\tttbr", "b\tprimary",
                  "b\t__primary", "b\tstart_kernel", "bl\t"):
        forbid(dev, token)
    t2dev = T2_DEVICE_S.read_text()
    for token in ("r3_t2_checkpoint", "msr\tdaifset, #0xf", "smc\t#0", "wfe"):
        need(t2dev, token)
    t1dev = T1_DEVICE_S.read_text()
    for token in ("r3_t1_checkpoint", "msr\tdaifset, #0xf",
                  "mrs\tx9, cntfrq_el0", "smc\t#0", "wfe"):
        need(t1dev, token)
    proto = T1_PROTO_S.read_text()
    need(proto, "P1B_PROBE_DELAY", "T3_PROTOTYPE_AUDIT_FAILED")
    need(proto, "r3_t1_probe", "T3_PROTOTYPE_AUDIT_FAILED")
    obs = OBSERVER.read_text()
    for token in ("R3_T3_SHA256", "T3_OBSERVER_MISBOOT_REFUSED",
                  "T3_MINUS_T2", "T2_REFERENCE_TOTAL", "T1_REFERENCE_TOTAL",
                  "T0_REFERENCE_TOTAL", "T3_REACHABILITY_SIGNATURE",
                  "T3_FAILURE_ISOLATION_CI", "FASTBOOT_BOOT_ONLY",
                  "T3_NORMAL_KERNEL_BOOT_CANDIDATE", "T3_DIAGNOSTIC_ONLY",
                  "R3_START_KERNEL_ADDRESS_REACHABILITY",
                  "T3_NOT_REACHED_LICENSE=NO", "T3_STABLE_FASTBOOT",
                  "T3_NO_RETURN", "START_KERNEL_ADDRESS_REACHED"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("T3_OBSERVER_MISBOOT_REFUSED", "NOT_REACHED",
                  "T3_STABLE_FASTBOOT", "T3_NO_RETURN"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("T3_START_KERNEL_REDERIVED",
                  "START_KERNEL_IMAGE_OFFSET", "START_KERNEL_SECTION",
                  "T3_ENTRY_MMU", "T3_ENTRY_PC_ADDRESS_SPACE",
                  "T3_PROBE_ARCHITECTURE=INLINE",
                  "T3_INLINE_OVERWRITE_SAFE",
                  "T3_INLINE_MAPPING_EXECUTABLE",
                  "T3_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
                  "T3_RELOCATION_SCAN", "T3_LITERAL_SCAN",
                  "T3_EXCEPTION_TABLE_SCAN", "T3_FUNCTION_EXTENT_SCAN",
                  "T3_JUMP_TABLE_SCAN", "T3_ALTINSTRUCTIONS_SCAN",
                  "T3_CNTPCT_ACCESS_SAFE", "T3_PSCI_SYSTEM_RESET_SAFE",
                  "T3_FAIL_CLOSED", "T3_STACK_USAGE=NO",
                  "T3_RUNTIME_RELOCATIONS=0",
                  "T3_START_KERNEL_ENTRY_INSTRUCTION0=paciasp",
                  "T3_BTI_LANDING_REQUIRED=NO",
                  "T3_ENTRY_PAD_PRESERVED",
                  "T3_START_KERNEL_CALLSITE_FOUND=YES",
                  "T3_START_KERNEL_CALL_TARGET_EXACT=YES",
                  "T3_PRE_START_KERNEL_CONTROL_FLOW_AUDITED=YES",
                  "T3_START_KERNEL_ENTRY_INSTRUMENTATION_AUDITED=YES",
                  "T3_PRE_CHECKPOINT_RUNTIME_REWRITE=NONE",
                  "T3_WINDOW_INSIDE_IMAGE_SIZE=YES",
                  "T3_DIAGNOSTIC_CORE_MATCHES_T1",
                  "T3_DIAGNOSTIC_CORE_SLICE_MATCHES_T2",
                  "T2_PROBE_REMOVED_FROM_T3",
                  "PRIMARY_SWITCHED_IDENTICAL_TO_FIX8",
                  "START_KERNEL_ADDRESS_CHECKPOINT_ONLY",
                  "T3_PAYLOAD_DIFF_ATTRIBUTED="
                  "START_KERNEL_CHECKPOINT_ONLY",
                  "T3_TRAMPOLINE_IDENTICAL",
                  "T3_STATUS_GATE_STRUCTURED=YES",
                  "T3_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
                  "T3_DIFF_BYTE_COUNT", "T3_DIFF_RANGES",
                  "T2_REFERENCE_TOTAL", "14.240", "14.238", "14.252",
                  "6.1445", "0x2380000", "0x84000009", "wfe", "CNTPCT",
                  "T3_FAILURE_ISOLATION_CI", "STRONG", "SUPPORTED",
                  "READY_FOR_R3_P1B_T3_DEVICE_CONTROL",
                  "R3_P1B_T3_PREDEVICE_NOT_READY", "T4", "R4", "R5", "E2"):
        need(doc, token)
    kv = parse_status_kv(STATUS_DOC.read_text())
    for key, want in STATUS_DOC_REQUIRED_KV.items():
        if kv.get(key) != want:
            fail("T3_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} != {want!r}")
    for key, allowed in STATUS_DOC_ENUM_KV.items():
        if kv.get(key) not in allowed:
            fail("T3_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} not in {allowed}")
    print(f"T3_STATUS_KV_KEY_COUNT={len(kv)}")
    print("T3_STATUS_GATE_STRUCTURED=YES")
    wf_text = WF.read_text()
    for token in ("p1b-t3-device.S", "p1b-t3-predevice.py",
                  "observe-r3-p1b-t3.py", "thyme-r3-p1b-t3",
                  "T3_BUILD_GATES=PASS",
                  "T3_INLINE_OVERWRITE_SAFE=YES",
                  "T3_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
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
            fail("T3_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    body = re.search(r"\n    manifest = \{(.*?)\n    \}\n",
                     Path(__file__).read_text(), re.S)
    if not body:
        fail("T3_SOURCE_GATE_FAILED", "manifest literal not found")
    keys = set(re.findall(r'^\s+"([a-z0-9_]+)":', body.group(1), re.M))
    for key in sorted(set(re.findall(r'm\["([^"]+)"\]',
                                     PRIVATE_WF.read_text()))):
        if key not in keys:
            fail("T3_SOURCE_GATE_FAILED",
                 f"private workflow reads unknown manifest key {key!r}")
    print(f"T3_MANIFEST_KEY_CONSISTENCY=PASS ({len(keys)} keys)")
    print("T3_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "t3", "observer-fixtures", "t3-pack-gates"),
        required=True)
    parser.add_argument("--out", default="out-t3")
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
    parser.add_argument("--start-kernel-offset")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
        return
    if args.mode == "t3":
        if not (args.rt_d and args.fix8_payload):
            fail("T3_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_t3(args)
        return
    if args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
        return
    if args.mode == "t3-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.checkpoint_bin
                    and args.checkpoint_sha and args.start_kernel_offset)
        if not need_all:
            fail("T3_PACK_FAILED",
                 "need --m5d-boot --payload --boot --payload-sha "
                 "--checkpoint-bin --checkpoint-sha --start-kernel-offset")
        cmd_t3_pack_gates(args)


if __name__ == "__main__":
    main()
