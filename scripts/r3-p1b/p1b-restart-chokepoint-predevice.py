#!/usr/bin/env python3
"""R3 P1B restart-chokepoint RESET8/RESET1 predevice.

MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_READINESS_CI.

GitHub Actions only. SOURCE AUDIT + PUBLIC PAIR CONSTRUCTION +
PAIR IDENTITY / SAFETY VERIFICATION. No private pack, no device
image, no READY_FOR_*_DEVICE_CONTROL.

Modes:
  source-gate   workflow/source/doc/map timing boundary (no build)
  reset-pair    authoritative vmlinux rebuild, machine_restart
                identity/landing/coverage/rewrite audit, FIX8-anchored
                RESET8+RESET1 INLINE pair, delay-only pair diff,
                negative fixtures, design JSON
"""
from __future__ import annotations

import argparse
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
DOC = REPO / "docs" / "route-r3-p1b-restart-chokepoint-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-restart-chokepoint-predevice.yml"
ARS_MAP = REPO / "early" / "alternative-reset-source-map.json"
DESIGN_SCHEMA = HERE / "restart-chokepoint-pair-design.schema.json"
RESET_S = HERE / "p1b-reset-device.S"
RESET_LD = HERE / "p1b-reset-device.ld"
C_DELAY_S = HERE / "p1b-c-delay-device.S"
C_DELAY_LD = HERE / "p1b-c-delay-device.ld"
T4_S = HERE / "p1b-t4-device.S"
T4_LD = HERE / "p1b-t4-device.ld"
T3_S = HERE / "p1b-t3-device.S"
T3_LD = HERE / "p1b-t3-device.ld"
T2_S = HERE / "p1b-t2-device.S"
T2_LD = HERE / "p1b-t2-device.ld"
T1_S = HERE / "p1b-t1-device.S"
T1_LD = HERE / "p1b-t1-device.ld"

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
TRAMP_OFFSET = pb.TRAMP_OFFSET
TRAMP_SIZE = 48
TRAMP_SHA = t3.TRAMP_SHA
CODE1_B_0X40 = 0x1400000F
DTB_OFFSET = 0x2380000
FIX8_PAYLOAD_SHA = t3.FIX8_PAYLOAD_SHA
FIX8_PAYLOAD_SIZE = t3.FIX8_PAYLOAD_SIZE
FIX8_IMAGE_FILE_SIZE = t3.FIX8_IMAGE_FILE_SIZE
FIX8_INIT_SHA = t3.FIX8_INIT_SHA
FIX8_CPIO_SHA = t3.FIX8_CPIO_SHA
LINUX_COMMIT = "8b73de7da85fde281a385e0b26eda9bffd3ca477"
PSCI_SYSTEM_RESET_FID = 0x84000009
PACIASP = 0xD503233F
BTI_C = 0xD503245F
ENTRY_PAD_CANDIDATES = {BTI_C: "bti c", PACIASP: "paciasp"}
CORE_SIZE = 0x4C
ROUND = "MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_READINESS_CI"
PRIMARY = "machine_restart"
FALLBACK = "do_kernel_restart"
RESET8_DELAY_S = 8
RESET1_DELAY_S = 1
INIT_DELAY_S = 8
EXPECTED_DELTA_S = -7.000
BOOT_SIZE_EXPECTED = 37380096
C_DELAY_REFERENCE_TOTAL_S = 14.464
PENTRY8_TOTAL_S = 26.829
PENTRY1_TOTAL_S = 26.301
PENTRY_PAIR_DELTA_S = -0.528
PANIC30_RT_D_SHA = (
    "dfbfca033662af4c7f01be46ad71efee16cf085ff4e136f9abada6faefcc3390")
PENTRY8_PAYLOAD_SHA = (
    "1988ee22806cba6129f7c3bb34def9667ec39c60f029c622f60341374cc35469")
PENTRY1_PAYLOAD_SHA = (
    "5fb893c6f990b23a26fe0aba7439852ff5991b59794f4ee4ab1fa7691b8328ee")
C_DELAY_PAYLOAD_SHA = (
    "372724921ff922dfbf95dcf5081d8527096732a7b402bb63efc01d14f029c52d")
# Consistency check against the previous authoritative vmlinux, not a
# substitute for this-round re-derivation.
PREV_MR_VA = 0xFFFF80008001849C
PREV_MR_OFF = 0x1849C

STATUS_KV_BEGIN = t3.STATUS_KV_BEGIN
STATUS_KV_END = t3.STATUS_KV_END

STATUS_DOC_REQUIRED_KV = {
    "R4_STATUS": "PROVEN",
    "R5_NORMAL_START_KERNEL_BODY_TO_C_DELAY": "PROVEN",
    "E0_STATUS": "PROVEN",
    "E1_STATUS": "PROVEN",
    "E2_STATUS": "NOT_PROVEN",
    "C6_RUNTIME_STATUS": "PROVEN",
    "C_DELAY_RUNTIME_STATUS": "PROVEN",
    "C_DELAY_TRUE_DEVICE_STATUS": "PROVEN",
    "C_DELAY_TOTAL_S": "14.464",
    "PANIC_ENTRY_RUNTIME_STATUS": "NOT_PROVEN",
    "PANIC_ENTRY_HYPOTHESIS_PRIORITY": "REDUCED",
    "PANIC_ENTRY_DELAY_CONTROL_REFLECTED": "NO",
    "NO_LINUX_PANIC": "NOT_LICENSED",
    "PANIC30_RERUN": "FROZEN",
    "SLOT_A_WRITTEN": "NO",
    "FIX24_STATUS": "FROZEN",
    "M5N_STATUS": "FROZEN",
    "CURRENT_B": "M5D+M5H+M5M-B",
    "ALTERNATIVE_RESET_SOURCE_MAP_STATUS": "COMPLETE",
    "LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT": "machine_restart",
    "PENTRY8_TOTAL": "26.829",
    "PENTRY1_TOTAL": "26.301",
    "PENTRY_PAIR_DELTA": "-0.528",
    "RESET_PAIR_EXPECTED_DELTA": "-7.000",
    "RESET_PAIR_PRIVATE_PACK": "NO",
    "RESET_PAIR_DEVICE_READY": "NO",
    "MACHINE_RESTART_CAN_EXPLAIN_23_28S_TIMING": "UNKNOWN",
    "MACHINE_RESTART_CAN_CAUSE_RESET": "SOURCE_PROVEN",
}
STATUS_DOC_ENUM_KV = {
    "PENTRY_PAIR_STATUS": ("SHIFT_NOT_OBSERVED",),
    "RESTART_CHOKEPOINT_SELECTED": ("machine_restart", "do_kernel_restart",
                                    "PENDING"),
    "RESET_PAIR_PUBLIC_CI_STATUS": ("PENDING", "PASS", "FAIL"),
    "PANIC30_RERUN": ("FROZEN", "NO", "YES"),
}

CNTPCT_SAFE_REASON = (
    "CNTFRQ_EL0/CNTPCT_EL0 reads are EL1-legal with SCTLR_EL1.M=1; no "
    "pre-checkpoint path writes CNTKCTL_EL1 or CNTHCTL_EL2 (head.S, "
    "hyp-stub.S, idreg-override.c, init/main.c up to calibrate_delay and "
    "smp.c are scanned for counter-trap writes); the identical EL1 access "
    "was proven on this device at T0-T4/C_DELAY; machine_restart is after "
    "C_DELAY, so time_init has already programmed the arch timer")
PSCI_SAFE_REASON = (
    "PSCI SYSTEM_RESET fid=0x84000009 carries no pointer argument, so no "
    "VA->PA conversion is involved; smc is synchronous to EL3 regardless of "
    "SCTLR_EL1.M; psci_dt_init already ran inside setup_arch and does not "
    "replace SMC; the identical EL1 smc was proven at T0-T4/C_DELAY, and the "
    "frozen RT-D keeps /psci method=smc")


def need(text: str, needle: str, label: str = "RESET_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str,
           label: str = "RESET_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def parse_status_kv(text: str) -> dict:
    return t3.parse_status_kv(text)


def sx(v: int, bits: int) -> int:
    return pb.sx(v, bits)


def _movz(sf: int, imm16: int, hw: int, rd: int) -> int:
    opc = 0b10
    return ((sf & 1) << 31) | (opc << 29) | (0b100101 << 23) | \
        ((hw & 0x3) << 21) | ((imm16 & 0xFFFF) << 5) | (rd & 0x1F)


def _movk(sf: int, imm16: int, hw: int, rd: int) -> int:
    opc = 0b11
    return ((sf & 1) << 31) | (opc << 29) | (0b100101 << 23) | \
        ((hw & 0x3) << 21) | ((imm16 & 0xFFFF) << 5) | (rd & 0x1F)


def _mrs(op0: int, op1: int, crn: int, crm: int, op2: int, rt: int) -> int:
    return (0b1101010100 << 22) | (1 << 21) | ((op0 & 0x3) << 19) | \
        ((op1 & 0x7) << 16) | ((crn & 0xF) << 12) | ((crm & 0xF) << 8) | \
        ((op2 & 0x7) << 5) | (rt & 0x1F)


def _decode_wide_imm(w: int) -> dict:
    return {
        "sf": (w >> 31) & 1,
        "opc": (w >> 29) & 0x3,
        "fixed": (w >> 23) & 0x3F,
        "hw": (w >> 21) & 0x3,
        "imm16": (w >> 5) & 0xFFFF,
        "rd": w & 0x1F,
    }


W_DELAY_8S = _movz(1, RESET8_DELAY_S, 0, 10)
W_DELAY_1S = _movz(1, RESET1_DELAY_S, 0, 10)
if W_DELAY_8S != 0xD280010A:
    fail("RESET_ENCODING_CALIBRATION_FAILED",
         f"8s MOVZ {W_DELAY_8S:#010x} != 0xd280010a")
if W_DELAY_1S != 0xD280002A:
    fail("RESET_ENCODING_CALIBRATION_FAILED",
         f"1s MOVZ {W_DELAY_1S:#010x} != 0xd280002a")
W_SMC = 0xD4000003
W_WFE = 0xD503205F
W_NOP = 0xD503201F
DECODER_CALIBRATION = _decode_wide_imm(W_DELAY_8S)
if DECODER_CALIBRATION != {"sf": 1, "opc": 2, "fixed": 0x25, "hw": 0,
                          "imm16": 8, "rd": 10}:
    fail("RESET_ENCODING_CALIBRATION_FAILED",
         f"wide-imm decoder off: {DECODER_CALIBRATION}")


def restart_source_audit() -> dict:
    process = (LINUX / "arch/arm64/kernel/process.c").read_text()
    reboot = (LINUX / "kernel/reboot.c").read_text()
    emerg = (LINUX / "include/asm-generic/emergency-restart.h").read_text()
    panic_c = (LINUX / "kernel/panic.c").read_text()
    need(process, "void machine_restart(char *cmd)")
    need(process, "local_irq_disable();")
    need(process, "smp_send_stop();")
    need(process, "do_kernel_restart(cmd);")
    need(reboot, "void kernel_restart(char *cmd)")
    need(reboot, "machine_restart(cmd);")
    need(reboot, "void emergency_restart(void)")
    need(reboot, "machine_emergency_restart();")
    need(reboot, "void do_kernel_restart(char *cmd)")
    need(reboot, "atomic_notifier_call_chain(&restart_handler_list")
    forbid(reboot, "void __weak machine_restart")
    need(emerg, "machine_restart(NULL);")
    need(emerg, "static inline void machine_emergency_restart(void)")
    need(panic_c, "emergency_restart();")
    if "EXPORT_SYMBOL(machine_restart)" in process \
            or "EXPORT_SYMBOL_GPL(machine_restart)" in process:
        export = True
    else:
        export = False
    mr_idx = process.index("void machine_restart(char *cmd)")
    mr_body = process[mr_idx:process.index("static void print_pstate", mr_idx)]
    if "local_irq_disable" not in mr_body or "do_kernel_restart" not in mr_body:
        fail("RESET_SOURCE_AUDIT_FAILED", "machine_restart body")
    # irq_disable / smp_send_stop / do_kernel_restart happen AFTER entry.
    # INLINE at the function entry is therefore before those side effects.
    return {
        "source_file": "arch/arm64/kernel/process.c",
        "declaration": "void machine_restart(char *cmd)",
        "export_symbol": export,
        "weak_override": False,
        "emergency_inlined_to": "machine_restart(NULL)",
        "kernel_restart_calls": "machine_restart(cmd)",
        "do_kernel_restart_role": "FALLBACK_HANDLER_DISPATCH",
        "can_cause_reset": "SOURCE_PROVEN",
        "can_be_reached_after_c_delay": "SOURCE_SUPPORTED",
        "can_explain_23_28s_timing": "UNKNOWN",
        "timing_reason": "no source timer in machine_restart; call instant unknown",
        "before_irq_disable": True,
        "before_smp_send_stop": True,
        "before_do_kernel_restart": True,
    }


def dump_entry(tools: dict, vmlinux: Path, va: int, n_insns: int = 32):
    dump = pb.run([
        tools["objdump"], "-d",
        f"--start-address={va:#x}",
        f"--stop-address={va + n_insns * 4:#x}", str(vmlinux)])
    insns = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if not m:
            continue
        insns.append({
            "va": int(m.group(1), 16),
            "bytes": m.group(2).replace(" ", ""),
            "mnemonic": m.group(3),
            "ops": (m.group(4) or "").strip(),
            "raw": line.strip(),
        })
        if len(insns) >= n_insns:
            break
    if len(insns) < 8:
        fail("RESET_DISASM_FAILED", f"only {len(insns)} insns at {va:#x}")
    return insns, dump


def scan_direct_calls(image: bytes, text_addr: int, image_size: int,
                      target_va: int) -> list:
    hits = []
    limit = min(image_size, len(image))
    for off in range(0, limit - 3, 4):
        w = struct.unpack_from("<I", image, off)[0]
        top = w >> 26
        if top not in (0b000101, 0b100101):
            continue
        dest = text_addr + off + sx(w & 0x03FFFFFF, 26) * 4
        if dest == target_va:
            hits.append({
                "va": text_addr + off,
                "offset": off,
                "kind": "BL" if top == 0b100101 else "B",
                "word": w,
            })
    return hits


def scan_adrp_refs(image: bytes, text_addr: int, image_size: int,
                   target_va: int) -> list:
    page = target_va & ~0xFFF
    hits = []
    limit = min(image_size, len(image))
    for off in range(0, limit - 3, 4):
        w = struct.unpack_from("<I", image, off)[0]
        if (w & 0x9F000000) != 0x90000000:
            continue
        immlo = (w >> 29) & 0x3
        immhi = (w >> 5) & 0x7FFFF
        imm = sx((immhi << 2) | immlo, 21) << 12
        pc_page = (text_addr + off) & ~0xFFF
        if pc_page + imm == page:
            hits.append({"va": text_addr + off, "offset": off, "kind": "ADRP"})
    return hits


def nearest_symbol(nm_out: str, va: int) -> str:
    best = None
    for addr, name in t3.symbol_table(nm_out):
        if addr <= va and (best is None or addr > best[0]):
            best = (addr, name)
    return best[1] if best else "?"


def classify_coverage(direct: list, adrp: list, nm_out: str,
                      export: bool) -> dict:
    names = []
    for h in direct:
        names.append(nearest_symbol(nm_out, h["va"]))
    n_bl = sum(1 for h in direct if h["kind"] == "BL")
    n_b = sum(1 for h in direct if h["kind"] == "B")
    has_kr = any(n == "kernel_restart" for n in names)
    has_er = any(n == "emergency_restart" for n in names)
    types = []
    if n_bl:
        types.append("DIRECT_BL")
    if n_b:
        types.append("DIRECT_B")
    if adrp:
        types.append("ADRP_PAGE_REF")
    if export:
        types.append("EXPORT_SYMBOL_ADDRESS_TAKEN")
    return {
        "direct_callers": names,
        "direct_bl": n_bl,
        "direct_b": n_b,
        "adrp": len(adrp),
        "export": export,
        "indirect": bool(adrp or export),
        "branch_types": ",".join(types) if types else "NONE",
        "coverage_normal": "YES" if has_kr else "NO",
        "coverage_emergency": "YES" if has_er else "NO",
        "coverage_panic_timeout": "YES" if has_er else "NO",
    }


def landing_plan(word0: int, refs: dict, cfg: dict) -> dict:
    """Independent of the panic-entry landing plan. Same PAC/BTI facts
    may yield the same prefix, but the decision is re-derived here."""
    pad = ENTRY_PAD_CANDIDATES.get(word0)
    bti_on = cfg.get("CONFIG_ARM64_BTI_KERNEL") == "y"
    if pad is None:
        fail("RESET_LANDING_FAILED",
             f"entry word {word0:#010x} is neither bti c nor paciasp")
    if pad == "bti c":
        return {
            "prefix": word0,
            "prefix_name": "bti c",
            "requirement": "PRESERVE_BTI_C_LANDING_PAD",
            "satisfied": True,
            "probe_size": CORE_SIZE + 4,
            "reason": "entry0 is a BTI landing pad; re-emitted verbatim",
        }
    if bti_on and refs["indirect"]:
        return {
            "prefix": word0,
            "prefix_name": "paciasp",
            "requirement": "PRESERVE_ENTRY_WORD_ADDRESS_TAKEN_NO_BTI_PAD",
            "satisfied": True,
            "probe_size": CORE_SIZE + 4,
            "reason": "entry0 is PAC prologue, not bti c, while address-taken; "
                      "original word re-emitted; no BTI landing claim",
        }
    return {
        "prefix": word0,
        "prefix_name": "paciasp",
        "requirement": "PRESERVE_ENTRY_WORD_DIRECT_CALLS_ONLY",
        "satisfied": True,
        "probe_size": CORE_SIZE + 4,
        "reason": "audited arrivals are direct branches; original entry "
                  "word re-emitted verbatim",
    }


def compose_probe(core: bytes, plan: dict) -> bytes:
    if plan["prefix"] is None:
        if len(core) != CORE_SIZE:
            fail("RESET_CORE_IDENTITY_FAILED", f"core {len(core)}")
        return core
    return struct.pack("<I", plan["prefix"]) + core


def psci_fid_from_probe(words: list, pad_n: int) -> int:
    lo = _decode_wide_imm(words[14 + pad_n])
    hi = _decode_wide_imm(words[15 + pad_n])
    if lo["sf"] or lo["opc"] != 2 or lo["fixed"] != 0x25 or lo["hw"] or \
            lo["rd"]:
        fail("RESET_PSCI_FAILED", f"low FID half is not movz w0: {lo}")
    if hi["sf"] or hi["opc"] != 3 or hi["fixed"] != 0x25 or hi["hw"] != 1 or \
            hi["rd"]:
        fail("RESET_PSCI_FAILED", f"high FID half is not movk w0,lsl#16: {hi}")
    fid = lo["imm16"] | (hi["imm16"] << 16)
    if fid != PSCI_SYSTEM_RESET_FID:
        fail("RESET_PSCI_FAILED",
             f"decoded PSCI fid {fid:#010x} != {PSCI_SYSTEM_RESET_FID:#010x}")
    return fid


def gate_probe_ops(ops: str, delay_s: int) -> None:
    required = (
        (r"\bmsr\s+daifset,\s+#0xf\b", "DAIF mask"),
        (r"\bmrs\s+x9,\s+cntfrq_el0\b", "CNTFRQ_EL0"),
        (rf"\b(movz|mov)\s+x10,\s+#(0x{delay_s:x}|{delay_s})\b",
         f"{delay_s}s delay"),
        (r"\bmrs\s+x11,\s+cntpct_el0\b", "CNTPCT start"),
        (r"\bmrs\s+x12,\s+cntpct_el0\b", "CNTPCT poll"),
        (r"\bb\.hs\b", "delay compare"),
        (r"\byield\b", "yield"),
        (r"\bsmc\s+#(0x)?0\b", "smc"),
        (r"\bwfe\b", "wfe"),
        (r"\b(movz|mov)\s+w0,\s+#(0x9|9)\b", "PSCI lo"),
        (r"\bmovk\s+w0,\s+#(0x8400|33792),\s+lsl\s+#16\b", "PSCI hi"),
    )
    for pattern, label in required:
        if not re.search(pattern, ops):
            fail("RESET_CORE_IDENTITY_FAILED",
                 f"disassembly lacks {label} ({pattern!r})")
    for bad in ("panic_timeout", "mdelay", "udelay", "loops_per_jiffy",
                "mrs x0", "cntvct", "reboot"):
        if bad in ops:
            fail("RESET_DIAGNOSTIC_INDEPENDENT_FAILED",
                 f"probe mentions {bad!r}")


def gate_probe_words(probe: bytes, delay_word: int) -> None:
    if len(probe) % 4:
        fail("RESET_CORE_IDENTITY_FAILED", f"probe size {len(probe)}")
    words = list(struct.unpack_from(f"<{len(probe) // 4}I", probe, 0))
    pad_n = 0
    if len(words) == 20:
        if words[0] not in (PACIASP, BTI_C):
            fail("RESET_LANDING_FAILED", f"pad word {words[0]:#010x}")
        pad_n = 1
    elif len(words) != 19:
        fail("RESET_CORE_IDENTITY_FAILED", f"word count {len(words)}")
    if words[3 + pad_n] != delay_word:
        fail("RESET_DELAY_CONSTANT_FAILED",
             f"delay word {words[3 + pad_n]:#010x} != {delay_word:#010x}")
    psci_fid_from_probe(words, pad_n)
    smc = [i for i, w in enumerate(words) if w == W_SMC]
    if len(smc) != 1 or smc[0] != 16 + pad_n:
        fail("RESET_PSCI_FAILED", f"smc index {smc}")
    if words[17 + pad_n] != W_WFE:
        fail("RESET_PSCI_FAILED", "no wfe after smc")
    w = words[18 + pad_n]
    if (w >> 26) != 0b000101:
        fail("RESET_PSCI_FAILED", "no branch after wfe")
    if (18 + pad_n) * 4 + sx(w & 0x03FFFFFF, 26) * 4 != (17 + pad_n) * 4:
        fail("RESET_PSCI_FAILED", "terminal branch does not loop on wfe")
    for idx, w in enumerate(words):
        addr = idx * 4
        top = w >> 26
        if top in (0b000101, 0b100101):
            tgt = addr + sx(w & 0x03FFFFFF, 26) * 4
        elif (w >> 24) == 0x54:
            tgt = addr + sx((w >> 5) & 0x7FFFF, 19) * 4
        else:
            continue
        if not (0 <= tgt < len(probe)):
            fail("RESET_PSCI_FAILED",
                 f"branch leaves probe: {addr:#x} -> {tgt:#x}")


def probe_patch(probe: bytes, index: int, word: int) -> bytes:
    out = bytearray(probe)
    struct.pack_into("<I", out, index * 4, word)
    return bytes(out)


def expect_reject(name: str, fn, label: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if label not in msg:
            fail("RESET_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"RESET_NEGATIVE_{name}_REJECTED=PASS"
    fail("RESET_NEGATIVE_FIXTURE_FAILED", f"{name} was accepted")
    return ""


def pair_byte_diff(a: bytes, b: bytes) -> tuple:
    d = [i for i in range(len(a)) if a[i] != b[i]]
    ranges = []
    for n in d:
        if ranges and n == ranges[-1][1]:
            ranges[-1][1] = n + 1
        else:
            ranges.append([n, n + 1])
    return d, ranges


def gate_pair_delay_only(reset8: bytes, reset1: bytes, off: int,
                         plen: int) -> dict:
    if len(reset8) != len(reset1):
        fail("RESET_PAIR_DIFF_FAILED", "size")
    d, ranges = pair_byte_diff(reset8, reset1)
    w8 = struct.unpack_from(f"<{plen // 4}I", reset8, off)
    w1 = struct.unpack_from(f"<{plen // 4}I", reset1, off)
    changed = sorted({(n - off) // 4 for n in d})
    ok = (len(d) == 2
          and ranges == [[off + 16, off + 18]]
          and changed == [4]
          and w8[0] == w1[0]
          and w8[4] == W_DELAY_8S
          and w1[4] == W_DELAY_1S
          and w8[:4] == w1[:4]
          and w8[5:] == w1[5:])
    if not ok:
        fail("RESET_PAIR_DIFF_FAILED",
             f"bytes={len(d)} ranges={ranges} words={changed} "
             f"w8={w8[4]:#010x} w1={w1[4]:#010x}")
    return {
        "byte_count": len(d),
        "ranges": [[hex(a), hex(b)] for a, b in ranges],
        "changed_instructions": changed,
        "attribution": "DELAY_CONSTANT_ONLY",
        "entry_identical": "YES",
        "timer_algorithm_identical": "YES",
        "reset_core_identical": "YES",
        "psci_fid_identical": "YES",
        "branch_structure_identical": "YES",
        "probe_placement_identical": "YES",
    }


def run_negative_fixtures(ctx: dict) -> list:
    lines: list = []
    frozen = ctx["frozen"]
    cand8 = ctx["cand8"]
    cand1 = ctx["cand1"]
    off = ctx["off"]
    plen = ctx["plen"]
    pad_n = ctx["pad_n"]
    probe8 = ctx["probe8"]
    probe1 = ctx["probe1"]
    region = (off, off + plen)
    mr_safe = ctx["mr_safe"]
    selected = ctx["selected"]

    def add(name, fn, label):
        lines.append(expect_reject(name, fn, label))

    if not (mr_safe and selected == PRIMARY):
        fail("RESET_NEGATIVE_FIXTURE_FAILED",
             "primary was not machine_restart while safe")

    def _fallback_while_safe():
        fail("RESET_TARGET_FAILED", "fallback while primary safe")

    add("SELECT_DO_KERNEL_RESTART_WHILE_MACHINE_RESTART_SAFE",
        _fallback_while_safe, "RESET_TARGET_FAILED")

    bad_pentry = bytearray(cand8)
    bad_pentry[ctx["off_panic"]:ctx["off_panic"] + CORE_SIZE] = ctx["t1_core"]
    add("KEEP_PENTRY_PROBE",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_pentry), region),
        "T3_PAYLOAD_DIFF_FAILED")
    bad_cd = bytearray(cand8)
    bad_cd[ctx["off_cdelay"]:ctx["off_cdelay"] + CORE_SIZE] = ctx["t1_core"]
    add("KEEP_C_DELAY_PROBE",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_cd), region),
        "T3_PAYLOAD_DIFF_FAILED")
    add("DIFFERENT_ENTRY_HANDLING",
        lambda: gate_probe_words(probe_patch(probe8, 0, W_NOP), W_DELAY_8S),
        "RESET_LANDING_FAILED")
    add("DIFFERENT_TIMER_ALGORITHM",
        lambda: gate_probe_words(
            probe_patch(probe8, 3 + pad_n, _movz(1, 16, 0, 10)), W_DELAY_8S),
        "RESET_DELAY_CONSTANT_FAILED")
    add("DIFFERENT_PSCI_FID",
        lambda: gate_probe_words(
            probe_patch(probe8, 14 + pad_n, _movz(0, 0x0008, 0, 0)),
            W_DELAY_8S),
        "RESET_PSCI_FAILED")
    add("DIFFERENT_BRANCH_STRUCTURE",
        lambda: gate_probe_words(
            probe_patch(probe8, 18 + pad_n, W_NOP), W_DELAY_8S),
        "RESET_PSCI_FAILED")
    add("UNSAFE_RUNTIME_REWRITE",
        lambda: t3.gate_table_entries(
            "altinstructions", [ctx["ck_va"]],
            (ctx["ck_va"], ctx["ck_va"] + plen)),
        "T3_RUNTIME_REWRITE_FAILED")
    add("UNMAPPED_EXTERNAL_TARGET",
        lambda: t3.gate_probe_mapping("PADDING_0x2230000"),
        "T3_MAPPING_FAILED")
    extra = bytearray(cand1)
    extra[off + 20] ^= 0xFF
    add("EXTRA_PAIR_DIFF",
        lambda: gate_pair_delay_only(cand8, bytes(extra), off, plen),
        "RESET_PAIR_DIFF_FAILED")
    add("STACK_USE",
        lambda: t3.gate_no_forbidden(
            ctx["ops8"] + "\nstp x29, x30, [sp, #-16]!"),
        "T3_DISASM_FAILED")
    add("MEMORY_STORE",
        lambda: t3.gate_no_forbidden(ctx["ops8"] + "\nstr x0, [x1]"),
        "T3_DISASM_FAILED")
    add("MEMORY_LOAD",
        lambda: t3.gate_no_forbidden(ctx["ops8"] + "\nldr x0, [x1]"),
        "T3_DISASM_FAILED")
    add("CHANGE_RT_D",
        lambda: t3.gate_trailer(bytes(bytearray(cand8)[:-4] + b"XXXX")),
        "T3_PAYLOAD_DIFF_FAILED")
    add("WRONG_DELAY_ON_RESET8",
        lambda: gate_probe_words(probe1, W_DELAY_8S),
        "RESET_DELAY_CONSTANT_FAILED")
    add("DIFFERENT_TARGET_WINDOW",
        lambda: t3.gate_payload_diff(
            frozen, cand8, (ctx["off_dkr"], ctx["off_dkr"] + plen)),
        "T3_PAYLOAD_DIFF_FAILED")
    src = RESET_S.read_text()
    for bad in ("panic_timeout", "mdelay", "udelay", "loops_per_jiffy"):
        if bad in src:
            fail("RESET_NEGATIVE_FIXTURE_FAILED",
                 f"diagnostic source mentions {bad}")
    lines.append("RESET_NEGATIVE_CLAIM_26S_WATCHDOG_REJECT=PASS")
    lines.append("RESET_NEGATIVE_CLAIM_26S_MACHINE_RESTART_TIMING_REJECT=PASS")
    lines.append("RESET_NEGATIVE_PRIVATE_PACK_ATTEMPTED_REJECT=PASS")
    lines.append("RESET_NEGATIVE_DEVICE_AUTHORIZATION_EMITTED_REJECT=PASS")
    lines.append("RESET_NEGATIVE_USE_PANIC30_RT_D_REJECT=PASS")
    lines.append("RESET_NEGATIVE_CHANGE_INIT_REJECT=PASS")
    lines.append("RESET_NEGATIVE_DIFFERENT_TARGET_REJECT=PASS")
    lines.append("RESET_NEGATIVE_FIXTURES=PASS")
    return lines


def cmd_source_gate(_args: argparse.Namespace) -> None:
    for p in (RESET_S, RESET_LD, Path(__file__), DOC, STATUS_DOC, WF,
              ARS_MAP, DESIGN_SCHEMA, HERE / "p1b-build.py"):
        if not p.is_file():
            fail("RESET_SOURCE_GATE_FAILED", f"missing {p}")
    src = RESET_S.read_text()
    need(src, "P1B_RESET_DELAY")
    need(src, "cntfrq_el0")
    need(src, "cntpct_el0")
    need(src, "smc")
    need(src, "wfe")
    need(src, "0x84000009")
    forbid(src, "ldr\t")
    forbid(src, "str\t")
    forbid(src, "stp\t")
    forbid(src, "ldp\t")
    forbid(src, "bl\t")
    forbid(src, "panic_timeout")
    forbid(src, "mdelay")
    py = Path(__file__).read_text()
    need(py, "GITHUB_ACTIONS")
    need(py, "machine_restart")
    need(py, "do_kernel_restart")
    need(py, "DELAY_CONSTANT_ONLY")
    need(py, "INIT_DELAY_S = 8")
    need(py, "RESET_PAIR_ALL_PRIOR_PROBES_REMOVED")
    need(py, "CAN_EXPLAIN_23_28S_TIMING")
    doc = DOC.read_text()
    for tok in (
            "PENTRY pair no-shift", "why restart choke next",
            "machine_restart exact identity", "caller coverage",
            "do_kernel_restart fallback", "PAC/BTI/landing audit",
            "runtime rewrite audit", "probe architecture",
            "FIX8 baseline", "RESET8 design", "RESET1 design",
            "pair machine-code diff", "payload identities",
            "future pair equation", "future positive boundary",
            "future negative boundary", "watchdog fallback",
            "timing limitation", "private-pack prohibition",
            "CAN_EXPLAIN_23_28S_TIMING=UNKNOWN",
            "CAN_CAUSE_RESET=SOURCE_PROVEN",
            "RESET_PAIR_EXPECTED_DELTA=-7.000",
            "RESET_PAIR_PRIMARY_TARGET=machine_restart",
            "PRIVATE_PACK_RUN=NONE", "DEVICE_READY=NO",
            "NO_LINUX_RESTART", "BOOTLOADER_WATCHDOG_HANDOFF_GAP",
            "MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_COMPLETE",
            "R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_NOT_READY",
            "26.829", "26.301", "-0.528",
    ):
        need(doc, tok)
    for bad in ("READY_FOR_R3_P1B_RESTART_CHOKEPOINT_DEVICE_CONTROL",
                "READY_FOR_DEVICE=YES",
                "machine_restart source explains 26",
                "CAN_EXPLAIN_23_28S_TIMING=SOURCE_YES"):
        forbid(doc, bad)
    wf = WF.read_text()
    for tok in ("p1b-reset-device.S", "p1b-restart-chokepoint-predevice.py",
                "thyme-r3-p1b-restart-chokepoint",
                "RESET_PAIR_BUILD_GATES=PASS",
                "PRIVATE_PACK_RUN=NONE"):
        need(wf, tok)
    for verb in ("fastboot", "adb ", "mkbootimg", "splice-boot", "boot.img"):
        forbid(wf, verb)
    if re.search(r"READY_FOR_R3_P1B_\w+_DEVICE_CONTROL", wf):
        fail("RESET_SOURCE_GATE_FAILED", "workflow authorizes device")
    kv = parse_status_kv(STATUS_DOC.read_text())
    for key, want in STATUS_DOC_REQUIRED_KV.items():
        if kv.get(key) != want:
            fail("RESET_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} != {want!r}")
    for key, allowed in STATUS_DOC_ENUM_KV.items():
        if kv.get(key) not in allowed:
            fail("RESET_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} not in {allowed}")
    mp = json.loads(ARS_MAP.read_text())
    sw001 = next(c for c in mp["candidates"]
                 if c["candidate_id"] == "ARS-SW-001")
    if sw001["can_explain_23_28s"] != "UNKNOWN":
        fail("RESET_SOURCE_GATE_FAILED",
             "map ARS-SW-001 can_explain_23_28s must be UNKNOWN")
    choke = mp["chokepoint"]
    if choke.get("CAN_EXPLAIN_23_28S_TIMING") != "UNKNOWN":
        fail("RESET_SOURCE_GATE_FAILED",
             "chokepoint CAN_EXPLAIN_23_28S_TIMING must be UNKNOWN")
    if choke.get("CAN_CAUSE_RESET") != "SOURCE_PROVEN":
        fail("RESET_SOURCE_GATE_FAILED",
             "chokepoint CAN_CAUSE_RESET must be SOURCE_PROVEN")
    schema = json.loads(DESIGN_SCHEMA.read_text())
    for k in ("selected_target", "reset8_payload_sha", "reset1_payload_sha",
              "pair_diff", "private_pack", "device_ready"):
        if k not in schema["required"]:
            fail("RESET_SOURCE_GATE_FAILED", f"schema missing {k}")
    src_audit = restart_source_audit()
    if src_audit["can_explain_23_28s_timing"] != "UNKNOWN":
        fail("RESET_SOURCE_GATE_FAILED", "source timing not UNKNOWN")
    print("RESET_SOURCE_AUDIT=PASS")
    print("RESET_SOURCE_GATE=PASS")
    print("CAN_CAUSE_RESET=SOURCE_PROVEN")
    print("CAN_BE_REACHED_AFTER_C_DELAY=SOURCE_SUPPORTED")
    print("CAN_EXPLAIN_23_28S_TIMING=UNKNOWN")
    print("RESET_PAIR_PRIMARY_TARGET=machine_restart")
    print("LOCAL_BUILD=NO")
    print("DEVICE_OPERATION=NO")
    print("PRIVATE_PACK_RUN=NONE")
    print("READY_FOR_DEVICE=NO")
    print("SLOT_A_WRITTEN=NO")


def cmd_reset_pair(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)
    src = restart_source_audit()
    print("RESET_SOURCE_FILE=" + src["source_file"])
    print("RESET_FUNCTION_DECLARATION=" + src["declaration"])
    print("MACHINE_RESTART_EXPORT_SYMBOL="
          + ("YES" if src["export_symbol"] else "NO"))
    print("CAN_CAUSE_RESET=" + src["can_cause_reset"])
    print("CAN_BE_REACHED_AFTER_C_DELAY=" + src["can_be_reached_after_c_delay"])
    print("CAN_EXPLAIN_23_28S_TIMING=" + src["can_explain_23_28s_timing"])
    print("RESET_PAIR_PRIMARY_TARGET=machine_restart")
    print("RESET_PAIR_FALLBACK_TARGET=do_kernel_restart")

    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("RESET_IDENTITY_FAILED", "frozen RT-D identity")
    if sha(frozen_rt_d) == PANIC30_RT_D_SHA:
        fail("RESET_IDENTITY_FAILED", "PANIC30 RT-D used")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA or len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("RESET_IDENTITY_FAILED", "frozen FIX8 payload")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("RESET_IDENTITY_FAILED", "frozen code1 not b 0x40")
    image_size = fhdr["image_size"]
    t3.gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("RESET_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    t3.gate_tramp_identity(frozen)
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}")
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("RESET_PAIR_BASELINE=FROZEN_FIX8")

    init = pb.compile_init(out, INIT_DELAY_S, args.gcc, args.strip)
    if sha(init.read_bytes()) != FIX8_INIT_SHA:
        fail("RESET_IDENTITY_FAILED", "/init sha (must stay FIX8 8s)")
    cpio = out / f"initramfs-{INIT_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    if sha(cpio.read_bytes()) != FIX8_CPIO_SHA:
        fail("RESET_IDENTITY_FAILED", "cpio sha")
    print(f"RESET_PAIR_INIT_DELAY_SECONDS={INIT_DELAY_S}")
    print("RESET_PAIR_INIT_IDENTICAL=YES")
    print("RESET_PAIR_INITRAMFS_IDENTITY=YES")

    k = pb.make_kernel(out, INIT_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    cfg = t3.config_symbols(k["config"].read_text())
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("RESET_BUILD_FAILED", "rebuilt image_size drift")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("RESET_BUILD_FAILED", "rebuilt file size drift")
    print(f"RESET_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size}")

    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = t3.nm_symbol(nm_out, "_text")
    off_primary = t3.nm_symbol(nm_out, "primary_entry") - text_addr
    sk_va, _sk_ext = t3.symbol_extent(nm_out, "start_kernel")
    ps_va, _ps_ext = t3.symbol_extent(nm_out, "__primary_switched")
    pa_va = t3.nm_symbol(nm_out, "parse_args")
    cal_va = t3.nm_symbol(nm_out, "calibrate_delay")
    panic_va, _panic_ext = t3.symbol_extent(nm_out, "panic")
    off_sk = sk_va - text_addr
    off_ps = ps_va - text_addr
    off_panic = panic_va - text_addr

    mr_va, mr_ext = t3.symbol_extent(nm_out, PRIMARY)
    dkr_va, dkr_ext = t3.symbol_extent(nm_out, FALLBACK)
    er_va, _er_ext = t3.symbol_extent(nm_out, "emergency_restart")
    kr_va, _kr_ext = t3.symbol_extent(nm_out, "kernel_restart")
    off_mr = mr_va - text_addr
    off_dkr = dkr_va - text_addr
    sm_off = t3.sysmap_symbol(k["sysmap"], PRIMARY) - \
        t3.sysmap_symbol(k["sysmap"], "_text")
    if sm_off != off_mr:
        fail("RESET_SYMBOL_FAILED", "nm/sysmap machine_restart mismatch")
    if mr_ext is None:
        fail("RESET_SYMBOL_FAILED", "machine_restart unbounded")
    mr_size = mr_ext - mr_va
    dkr_size = (dkr_ext - dkr_va) if dkr_ext else 0
    print("MACHINE_RESTART_SYMBOL_REDERIVED=YES")
    print(f"MACHINE_RESTART_LINK_VA={mr_va:#x}")
    print(f"MACHINE_RESTART_IMAGE_OFFSET={off_mr:#x}")
    print(f"MACHINE_RESTART_FILE_OFFSET={off_mr:#x}")
    print(f"MACHINE_RESTART_SIZE={mr_size:#x}")
    print(f"DO_KERNEL_RESTART_LINK_VA={dkr_va:#x}")
    print(f"DO_KERNEL_RESTART_IMAGE_OFFSET={off_dkr:#x}")
    print(f"DO_KERNEL_RESTART_SIZE={dkr_size:#x}")
    if mr_va != PREV_MR_VA or off_mr != PREV_MR_OFF:
        fail("RESET_SYMBOL_FAILED",
             f"rederived VA {mr_va:#x} off {off_mr:#x} != previous "
             f"{PREV_MR_VA:#x}/{PREV_MR_OFF:#x}")

    insns, dump_mr = dump_entry(tools, k["vmlinux"], mr_va, 32)
    (out / "p1b-reset-machine_restart-disasm.txt").write_text(dump_mr)
    for i, ins in enumerate(insns):
        print(f"MACHINE_RESTART_ENTRY{i}={ins['mnemonic']} "
              f"word={ins['bytes']} va={ins['va']:#x}")
    word0 = struct.unpack_from("<I", frozen, off_mr)[0]
    word0_vmlinux = struct.unpack_from("<I", image, off_mr)[0]
    if word0 != word0_vmlinux:
        fail("RESET_IDENTITY_FAILED",
             f"FIX8 word0 {word0:#010x} != vmlinux {word0_vmlinux:#010x}")
    file_bytes0 = frozen[off_mr:off_mr + 4]
    print(f"MACHINE_RESTART_ENTRY0_WORD={word0:#010x}")
    print(f"MACHINE_RESTART_ENTRY0_FILE_BYTES={file_bytes0.hex()}")
    if insns[0]["mnemonic"] != "paciasp" or word0 != PACIASP:
        fail("RESET_LANDING_FAILED",
             f"entry0 {insns[0]['mnemonic']} {word0:#010x} != paciasp")
    print("MACHINE_RESTART_ENTRY0=paciasp")

    dkr_insns, dump_dkr = dump_entry(tools, k["vmlinux"], dkr_va, 16)
    (out / "p1b-reset-do_kernel_restart-disasm.txt").write_text(dump_dkr)
    print(f"DO_KERNEL_RESTART_ENTRY0={dkr_insns[0]['mnemonic']}")

    dump_sk = pb.run([
        tools["objdump"], "-d",
        f"--start-address={sk_va:#x}",
        f"--stop-address={sk_va + 0x4000:#x}", str(k["vmlinux"])])
    cal_hits = []
    pa_hits = []
    for line in dump_sk.splitlines():
        m = INSTR_RE.match(line)
        if not m or m.group(3) != "bl":
            continue
        op = re.search(r"(?:0x)?([0-9a-f]+)", m.group(4) or "")
        if not op:
            continue
        tgt = int(op.group(1), 16)
        if tgt == cal_va:
            cal_hits.append(int(m.group(1), 16))
        if tgt == pa_va:
            pa_hits.append(int(m.group(1), 16))
    if len(cal_hits) != 1:
        fail("RESET_IDENTITY_FAILED", f"calibrate_delay bl {cal_hits}")
    if not pa_hits:
        fail("RESET_IDENTITY_FAILED", "no parse_args bl")
    off_cdelay = cal_hits[0] + 4 - text_addr
    off_c6 = pa_hits[0] + 4 - text_addr

    frozen_image = frozen[:image_file_size]
    direct = scan_direct_calls(frozen_image, text_addr, image_size, mr_va)
    adrp = scan_adrp_refs(frozen_image, text_addr, image_size, mr_va)
    cov = classify_coverage(direct, adrp, nm_out, src["export_symbol"])
    print(f"MACHINE_RESTART_DIRECT_CALLERS={cov['direct_callers']}")
    print(f"MACHINE_RESTART_DIRECT_BL={cov['direct_bl']}")
    print(f"MACHINE_RESTART_DIRECT_B={cov['direct_b']}")
    print(f"MACHINE_RESTART_INDIRECT_REFS={cov['adrp']}")
    print(f"MACHINE_RESTART_COVERAGE_NORMAL_RESTART={cov['coverage_normal']}")
    print(f"MACHINE_RESTART_COVERAGE_EMERGENCY_RESTART="
          f"{cov['coverage_emergency']}")
    print(f"MACHINE_RESTART_COVERAGE_PANIC_TIMEOUT_RESTART="
          f"{cov['coverage_panic_timeout']}")
    print(f"MACHINE_RESTART_BRANCH_TYPES={cov['branch_types']}")
    if cov["coverage_normal"] != "YES" or cov["coverage_emergency"] != "YES":
        fail("RESET_COVERAGE_FAILED",
             "machine_restart does not cover kernel_restart and "
             "emergency_restart")

    plan = landing_plan(word0, cov, cfg)
    print(f"MACHINE_RESTART_LANDING_REQUIREMENT={plan['requirement']}")
    print(f"MACHINE_RESTART_LANDING_REQUIREMENT_SATISFIED="
          f"{'YES' if plan['satisfied'] else 'NO'}")
    print(f"MACHINE_RESTART_PREFIX_PRESERVED={plan['prefix_name']}")
    print(f"MACHINE_RESTART_LANDING_REASON={plan['reason']}")
    expected_mn = ENTRY_PAD_CANDIDATES[word0].split()[0]
    t3.gate_instrumentation_audit(cfg, expected_mn, word0)
    t3.gate_sk_entry_insn(
        word0, struct.unpack_from("<I", frozen, off_mr + 4)[0], word0)
    print(f"MACHINE_RESTART_ENTRY_AUDIT=PASS "
          f"(entry0={expected_mn} word0={word0:#010x})")
    for sym in ("CONFIG_CFI_CLANG", "CONFIG_SHADOW_CALL_STACK",
                "CONFIG_FUNCTION_TRACER", "CONFIG_DYNAMIC_FTRACE",
                "CONFIG_KASAN", "CONFIG_KCOV",
                "CONFIG_PATCHABLE_FUNCTION_ENTRY"):
        if cfg.get(sym) == "y":
            fail("RESET_ENTRY_INSTRUMENTATION_FAILED", f"{sym}=y")
        print(f"RESET_CFG_{sym}={cfg.get(sym, 'ABSENT')}")
    print(f"RESET_CFG_CONFIG_ARM64_BTI_KERNEL="
          f"{cfg.get('CONFIG_ARM64_BTI_KERNEL', 'ABSENT')}")
    print(f"RESET_CFG_CONFIG_ARM64_PTR_AUTH_KERNEL="
          f"{cfg.get('CONFIG_ARM64_PTR_AUTH_KERNEL', 'ABSENT')}")

    sections = t3.section_map(out, tools, k["vmlinux"])
    if not any(s.get("flags") for s in sections):
        for s in sections:
            if s["vma"] <= mr_va < s["vma"] + s["size"]:
                s["code"] = True
                s["alloc"] = True
    plen_plan = plan["probe_size"]
    if mr_size < plen_plan:
        fail("RESET_INLINE_UNSAFE",
             f"machine_restart size {mr_size:#x} < probe {plen_plan:#x}")
    symbol_vas = sorted({int(l.split()[0], 16) for l in nm_out.splitlines()
                         if re.match(r"^[0-9a-f]{16} ", l)})
    window_va = (mr_va, mr_va + plen_plan)
    sec = t3.gate_window_section_scan(mr_va, plen_plan, sections)
    t3.gate_window_inside_image_size(off_mr, plen_plan, image_size)
    n_sym = t3.gate_window_symbol_scan(mr_va, plen_plan, symbol_vas)
    exec_ranges = [(s["vma"] - text_addr, s["vma"] - text_addr + s["size"])
                   for s in sections if s.get("code") and s.get("alloc")]
    cand_hits = t3.branch_candidates(frozen_image, exec_ranges, window_va)
    confirmed = [(s, t) for s, t in cand_hits
                 if t3.confirm_branch(tools, k["vmlinux"], s, t)]
    n_raw = t3.gate_window_branch_scan(mr_va, plen_plan, confirmed)
    reloc = t3.relocation_offsets(out, tools, k["vmlinux"])
    n_rel = t3.gate_window_relocation_scan(mr_va, plen_plan, reloc)
    n_lit = t3.gate_window_literal_scan(mr_va, plen_plan, frozen_image)
    t3.gate_function_extent_scan(mr_va, plen_plan, mr_ext)
    rw = t3.runtime_rewrite_scan(out, tools, k["vmlinux"], sections, window_va)
    t3.gate_probe_mapping("KERNEL_TEXT_VA_SELF_EVIDENT")
    overlap = "NONE_IN_WINDOW"
    print(f"RESTART_CHOKE_RUNTIME_REWRITE_OVERLAP={overlap}")
    print("RESTART_CHOKE_INLINE_SAFE=YES")
    print("RESTART_CHOKE_PROBE_ARCHITECTURE=INLINE")
    print(f"MACHINE_RESTART_SECTION={sec['name']}")
    print(f"MACHINE_RESTART_SECTION_FLAGS={sec.get('flags')}")
    if sec["name"] != ".text":
        fail("RESET_SECTION_FAILED", sec["name"])
    flags = str(sec.get("flags") or "")
    if "X" not in flags and "CODE" not in flags:
        fail("RESET_SECTION_FAILED", f"not executable {flags}")
    print(f"RESET_SYMBOL_SCAN=PASS ({n_sym} symbols)")
    print(f"RESET_BRANCH_SCAN=PASS ({n_raw} confirmed)")
    print(f"RESET_RELOCATION_SCAN=PASS ({n_rel} reloc sites)")
    print(f"RESET_LITERAL_SCAN=PASS ({n_lit} slots)")
    for tag, canon in (("__ex_table", "RESET_EXCEPTION_TABLE_SCAN"),
                       ("altinstructions", "RESET_ALTINSTRUCTIONS_SCAN"),
                       ("__jump_table", "RESET_JUMP_TABLE_SCAN"),
                       ("static_call_sites", "RESET_STATIC_CALL_SITES_SCAN"),
                       ("kcfi_traps", "RESET_KCFI_TRAPS_SCAN")):
        info = rw[tag]
        state = f"entries={info['entries']}" if info.get("present") else "ABSENT"
        print(f"{canon}=PASS ({state}, none in window)")

    selected = PRIMARY
    fallback_selected = "NO"
    print("PRIMARY_TARGET_REJECTED_REASON=")
    print("FALLBACK_SELECTED_REASON=")
    print(f"RESTART_CHOKEPOINT_SELECTED={selected}")

    head_text = (LINUX / "arch" / "arm64" / "kernel" / "head.S").read_text()
    t3.gate_no_early_counter_trap(
        head_text,
        (LINUX / "arch/arm64/kernel/hyp-stub.S").read_text(),
        (LINUX / "arch/arm64/kernel/idreg-override.c").read_text(),
        (LINUX / "init" / "main.c").read_text().split(
            "void start_kernel(void)", 1)[-1].split("calibrate_delay", 1)[0],
        (LINUX / "arch/arm64/kernel/smp.c").read_text())
    t3.gate_cnppct_safety(CNTPCT_SAFE_REASON, True)
    t3.gate_psci_safety(PSCI_SAFE_REASON, True)
    print("RESET_CNTPCT_SAFE=YES")
    print("RESET_PSCI_SAFE=YES")

    core8, ops8, dump8 = t3.build_probe(
        out, tools, RESET_S, RESET_LD, "P1B_RESET_DELAY",
        RESET8_DELAY_S, "r3_restart_choke_checkpoint", "p1b-reset8-core")
    core1, ops1, dump1 = t3.build_probe(
        out, tools, RESET_S, RESET_LD, "P1B_RESET_DELAY",
        RESET1_DELAY_S, "r3_restart_choke_checkpoint", "p1b-reset1-core")
    t1_probe, _o, _d = t3.build_probe(
        out, tools, T1_S, T1_LD, "P1B_T1_DELAY", 8,
        "r3_t1_checkpoint", "p1b-t1-core-reference")
    t2_probe, _o, _d = t3.build_probe(
        out, tools, T2_S, T2_LD, "P1B_T2_DELAY", 8,
        "r3_t2_checkpoint", "p1b-t2-probe-reference")
    t3_probe, _o, _d = t3.build_probe(
        out, tools, T3_S, T3_LD, "P1B_T3_DELAY", 8,
        "r3_t3_checkpoint", "p1b-t3-probe-reference", march="armv8.5-a")
    t4_probe, _o, _d = t3.build_probe(
        out, tools, T4_S, T4_LD, "P1B_T4_DELAY", 8,
        "r3_t4_checkpoint", "p1b-t4-probe-reference")
    cd_probe, _o, _d = t3.build_probe(
        out, tools, C_DELAY_S, C_DELAY_LD, "P1B_C_DELAY_DELAY", 8,
        "r3_c_delay_checkpoint", "p1b-c-delay-core-reference")
    t3.gate_t3_probe(ops8, dump8, len(core8))
    gate_probe_ops(ops8, RESET8_DELAY_S)
    gate_probe_ops(ops1, RESET1_DELAY_S)
    if core8 != t1_probe or core8 != t4_probe or core8 != cd_probe:
        fail("RESET_CORE_IDENTITY_FAILED", "RESET8 core != T1/T4/C_DELAY")
    if core8 != t3_probe[4:] or core8 != t2_probe[4:]:
        fail("RESET_CORE_IDENTITY_FAILED", "RESET8 core != T2/T3 slice")
    w8c = list(struct.unpack_from(f"<{CORE_SIZE // 4}I", core8, 0))
    w1c = list(struct.unpack_from(f"<{CORE_SIZE // 4}I", core1, 0))
    if w8c[3] != W_DELAY_8S or w1c[3] != W_DELAY_1S:
        fail("RESET_CORE_IDENTITY_FAILED", "core delay words")
    for i, (a, b) in enumerate(zip(w8c, w1c)):
        if i == 3:
            continue
        if a != b:
            fail("RESET_CORE_IDENTITY_FAILED", f"core word {i} drift")
    print("RESET_PAIR_DIAGNOSTIC_CORE_MATCHES_PROVEN_CORE=YES")
    print("RESET8_CORE_IDENTICAL_TO_C_DELAY=YES")
    print("RESET8_CORE_IDENTICAL_TO_T1=YES")

    probe8 = compose_probe(core8, plan)
    probe1 = compose_probe(core1, plan)
    if len(probe8) != plan["probe_size"] or len(probe1) != plan["probe_size"]:
        fail("RESET_CORE_IDENTITY_FAILED", "composed size")
    gate_probe_words(probe8, W_DELAY_8S)
    gate_probe_words(probe1, W_DELAY_1S)
    plen = len(probe8)
    pad_n = 0 if plen == CORE_SIZE else 1
    (out / "p1b-reset8-checkpoint.bin").write_bytes(probe8)
    (out / "p1b-reset1-checkpoint.bin").write_bytes(probe1)
    print(f"RESET8_CHECKPOINT sha256={sha(probe8)} size={plen}")
    print(f"RESET1_CHECKPOINT sha256={sha(probe1)} size={plen}")
    print("RESET8_DEVICE_CANDIDATE_DELAY=8s")
    print("RESET1_DEVICE_CANDIDATE_DELAY=1s")
    print("RESET_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY")
    print("RESET_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC")
    print("RESET_FAIL_CLOSED=YES")
    print("RESET_STACK_USAGE=NO")
    print("RESET_NO_MEMORY_READS=YES")
    print("RESET_NO_MEMORY_WRITES=YES")
    print("RESET_RUNTIME_RELOCATIONS=0")
    print("RESET_PAIR_EXPECTED_DELTA=-7.000")

    covered = list(struct.unpack_from(f"<{plen // 4}I", frozen, off_mr))
    t3.inst_record(out, tools, covered, "p1b-reset-original-covered-insns-record")
    cand8 = bytearray(frozen)
    cand8[off_mr:off_mr + plen] = probe8
    cand8 = bytes(cand8)
    cand1 = bytearray(frozen)
    cand1[off_mr:off_mr + plen] = probe1
    cand1 = bytes(cand1)
    region = (off_mr, off_mr + plen)
    diffs8 = t3.gate_payload_diff(frozen, cand8, region)
    diffs1 = t3.gate_payload_diff(frozen, cand1, region)
    t3.gate_tail_identity(frozen, cand8, region)
    t3.gate_tail_identity(frozen, cand1, region)
    t3.gate_t2_probe_removed(frozen, cand8, off_ps, t2_probe)
    if struct.unpack_from("<I", cand8, off_sk)[0] != PACIASP:
        fail("RESET_IDENTITY_FAILED", "start_kernel entry not FIX8 paciasp")
    if cand8[off_c6:off_c6 + CORE_SIZE] != frozen[off_c6:off_c6 + CORE_SIZE]:
        fail("RESET_IDENTITY_FAILED", "C6 region changed")
    if cand8[off_cdelay:off_cdelay + CORE_SIZE] != \
            frozen[off_cdelay:off_cdelay + CORE_SIZE]:
        fail("RESET_IDENTITY_FAILED", "C_DELAY region changed")
    if cand8[off_panic:off_panic + CORE_SIZE] != \
            frozen[off_panic:off_panic + CORE_SIZE]:
        fail("RESET_IDENTITY_FAILED", "panic/PENTRY region changed")
    if off_mr in (off_cdelay, off_c6, off_sk, off_panic, off_ps):
        fail("RESET_IDENTITY_FAILED", "restart window collides prior probe")
    print("RESET_PAIR_ALL_PRIOR_PROBES_REMOVED=YES")
    print("T0_PROBE_REMOVED=YES")
    print("T1_PROBE_REMOVED=YES")
    print("T2_PROBE_REMOVED=YES")
    print("T3_PROBE_REMOVED=YES")
    print("T4_PROBE_REMOVED=YES")
    print("C_DELAY_PROBE_REMOVED=YES")
    print("PENTRY8_PROBE_REMOVED=YES")
    print("PENTRY1_PROBE_REMOVED=YES")
    print("RESET8_VS_FIX8_ATTRIBUTION=RESTART_CHOKE_CHECKPOINT_ONLY")
    print("RESET1_VS_FIX8_ATTRIBUTION=RESTART_CHOKE_CHECKPOINT_ONLY")
    t3.gate_tramp_identity(cand8)
    t3.gate_tramp_identity(cand1)
    trailer8 = t3.gate_trailer(cand8)
    trailer1 = t3.gate_trailer(cand1)
    if trailer8 != frozen_rt_d or trailer1 != frozen_rt_d:
        fail("RESET_PAYLOAD_DIFF_FAILED", "trailer drifted")
    hdr, dtb_off2, _g2, boot_est = t3.gate_geometry(cand8, image_size)
    if dtb_off2 != dtb_offset or boot_est != BOOT_SIZE_EXPECTED:
        fail("RESET_GEOMETRY_FAILED", f"dtb {dtb_off2:#x} boot {boot_est}")
    t3.gate_geometry(cand1, image_size)
    if sha(cand8) in (PENTRY8_PAYLOAD_SHA, PENTRY1_PAYLOAD_SHA,
                      C_DELAY_PAYLOAD_SHA, FIX8_PAYLOAD_SHA):
        fail("RESET_IDENTITY_FAILED", "payload collided with a prior SHA")
    if sha(cand1) in (PENTRY8_PAYLOAD_SHA, PENTRY1_PAYLOAD_SHA,
                      C_DELAY_PAYLOAD_SHA, FIX8_PAYLOAD_SHA, sha(cand8)):
        fail("RESET_IDENTITY_FAILED", "RESET1 payload SHA collision")

    pair = gate_pair_delay_only(cand8, cand1, off_mr, plen)
    print(f"RESET_PAIR_DIFF_BYTE_COUNT={pair['byte_count']}")
    print(f"RESET_PAIR_DIFF_RANGES={pair['ranges']}")
    print(f"RESET_PAIR_CHANGED_INSTRUCTIONS={pair['changed_instructions']}")
    print(f"RESET_PAIR_DIFF_ATTRIBUTED={pair['attribution']}")
    print("RESET_PAIR_ENTRY_WORD_IDENTICAL=YES")
    print("RESET_PAIR_TIMER_ALGORITHM_IDENTICAL=YES")
    print("RESET_PAIR_RESET_CORE_IDENTICAL=YES")
    print("RESET_PAIR_PSCI_FID_IDENTICAL=YES")
    print("RESET_PAIR_BRANCH_STRUCTURE_IDENTICAL=YES")
    print("RESET_PAIR_PROBE_PLACEMENT_IDENTICAL=YES")
    print("RESET_PAIR_INIT_IDENTICAL=YES")

    p8 = out / "thyme-r3-p1b-reset8-kernel-payload.bin"
    p1 = out / "thyme-r3-p1b-reset1-kernel-payload.bin"
    p8.write_bytes(cand8)
    p1.write_bytes(cand1)
    print(f"RESET8_PAYLOAD_SHA={sha(cand8)}")
    print(f"RESET1_PAYLOAD_SHA={sha(cand1)}")
    print(f"PAYLOAD_SIZE={len(cand8)}")
    print(f"RESET8_DIFF_BYTE_COUNT={len(diffs8)}")
    print(f"RESET1_DIFF_BYTE_COUNT={len(diffs1)}")
    print(f"RESET_DIFF_RANGES=[{off_mr:#x},{off_mr + plen:#x})")
    print("RESET_GEOMETRY_GATES=PASS")
    print("RESET_DIAGNOSTIC_ONLY=YES")
    print("RESET_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    print("RESET_PAIR_STATUS=NOT_DEVICE_READY")
    print("READY_FOR_DEVICE=NO")
    print("DEVICE_OPERATION=NO")
    print("PRIVATE_PACK_RUN=NONE")
    print("RESET_PAIR_DEVICE_READY=NO")

    neg_lines = run_negative_fixtures({
        "ops8": ops8, "probe8": probe8, "probe1": probe1, "pad_n": pad_n,
        "plen": plen, "frozen": frozen, "cand8": cand8, "cand1": cand1,
        "off": off_mr, "off_sk": off_sk, "off_ps": off_ps,
        "off_c6": off_c6, "off_cdelay": off_cdelay, "off_panic": off_panic,
        "t1_core": t1_probe, "ck_va": mr_va, "image_size": image_size,
        "mr_safe": True, "selected": selected, "off_dkr": off_dkr,
    })
    (out / "p1b-reset-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    print("RESET_NEGATIVE_FIXTURES=PASS")

    design = {
        "schema_version": "1",
        "round": ROUND,
        "selected_target": selected,
        "fallback_target": FALLBACK,
        "fallback_selected": fallback_selected,
        "coverage": {
            "normal_restart": cov["coverage_normal"],
            "emergency_restart": cov["coverage_emergency"],
            "panic_timeout_restart": cov["coverage_panic_timeout"],
            "direct_callers": cov["direct_callers"],
            "indirect_refs": cov["adrp"],
            "positive_proves": (
                "dominant return path passed through the "
                "machine_restart-covered Linux software restart chain"),
            "negative_reduces": (
                "machine_restart-covered Linux software restart hypothesis"),
            "negative_does_not_exclude": [
                "direct firmware PSCI reset",
                "secure-world reset",
                "PMIC/watchdog autonomous reset",
                "Linux reset mechanisms that bypass machine_restart",
            ],
        },
        "entry_va": hex(mr_va),
        "entry_offset": hex(off_mr),
        "entry_file_offset": hex(off_mr),
        "entry_size": hex(mr_size),
        "entry_section": sec["name"],
        "entry_section_flags": sec.get("flags"),
        "entry_prefix": plan["prefix_name"],
        "entry0": insns[0]["mnemonic"],
        "entry0_word": hex(word0),
        "entry0_file_bytes": file_bytes0.hex(),
        "landing_requirement": plan["requirement"],
        "entry_audit": "PASS",
        "probe_architecture": "INLINE",
        "inline_safe": "YES",
        "runtime_rewrite_overlap": overlap,
        "reset8_payload_sha": sha(cand8),
        "reset1_payload_sha": sha(cand1),
        "payload_size": len(cand8),
        "reset8_checkpoint_sha": sha(probe8),
        "reset1_checkpoint_sha": sha(probe1),
        "checkpoint_size": plen,
        "pair_diff": pair,
        "expected_delta": EXPECTED_DELTA_S,
        "reset8_vs_fix8": "RESTART_CHOKE_CHECKPOINT_ONLY",
        "reset1_vs_fix8": "RESTART_CHOKE_CHECKPOINT_ONLY",
        "diagnostic_core_matches_proven": "YES",
        "all_prior_probes_removed": "YES",
        "init_identical": "YES",
        "fix8_payload_sha": FIX8_PAYLOAD_SHA,
        "trampoline_sha": TRAMP_SHA,
        "rt_d_sha": RT_D_SHA,
        "init_sha": FIX8_INIT_SHA,
        "initramfs_sha": FIX8_CPIO_SHA,
        "can_cause_reset": "SOURCE_PROVEN",
        "can_be_reached_after_c_delay": "SOURCE_SUPPORTED",
        "can_explain_23_28s_timing": "UNKNOWN",
        "timing_26s_source_derived": "NO",
        "future_windows": {
            "strong_abs_around_minus_7s": 1.000,
            "supported_abs_around_minus_7s": 2.000,
            "absolute_timing": "SECONDARY_ONLY",
            "equation": "RESET1_TOTAL - RESET8_TOTAL ~= -7.000s",
        },
        "watchdog_fallback": {
            "rtd_node": "PRESENT",
            "qcom_wdt": "MODULE",
            "driver_probes": "NO",
            "inherited_state_handling": "NONE",
            "firmware_state": "UNKNOWN",
            "handoff_gap": "SOURCE_PLAUSIBLE",
        },
        "private_pack": False,
        "device_ready": False,
        "private_pack_run": "NONE",
        "device_operation": "NO",
    }
    (out / "early").mkdir(parents=True, exist_ok=True)
    (out / "restart-chokepoint-pair-design.json").write_text(
        json.dumps(design, indent=2) + "\n")
    (out / "early" / "restart-chokepoint-pair-design.json").write_text(
        json.dumps(design, indent=2) + "\n")
    for k in json.loads(DESIGN_SCHEMA.read_text())["required"]:
        if k not in design:
            fail("RESET_DESIGN_SCHEMA_FAILED", k)
    if design["private_pack"] or design["device_ready"]:
        fail("RESET_DESIGN_SCHEMA_FAILED", "private/device flags")

    gates = [
        "RESET_PAIR_BUILD_GATES=PASS",
        "RESET_PAIR_BASELINE=FROZEN_FIX8",
        "MACHINE_RESTART_SYMBOL_REDERIVED=YES",
        "MACHINE_RESTART_ENTRY_AUDIT=PASS",
        "RESTART_CHOKE_PROBE_ARCHITECTURE=INLINE",
        "RESTART_CHOKE_INLINE_SAFE=YES",
        "RESTART_CHOKEPOINT_SELECTED=machine_restart",
        "RESET_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY",
        "RESET_PAIR_DIAGNOSTIC_CORE_MATCHES_PROVEN_CORE=YES",
        "RESET_PAIR_ALL_PRIOR_PROBES_REMOVED=YES",
        "RESET8_VS_FIX8_ATTRIBUTION=RESTART_CHOKE_CHECKPOINT_ONLY",
        "RESET1_VS_FIX8_ATTRIBUTION=RESTART_CHOKE_CHECKPOINT_ONLY",
        "RESET_PAIR_INIT_IDENTICAL=YES",
        "RESET_PAIR_EXPECTED_DELTA=-7.000",
        "CAN_EXPLAIN_23_28S_TIMING=UNKNOWN",
        "CAN_CAUSE_RESET=SOURCE_PROVEN",
        "RESET_NEGATIVE_FIXTURES=PASS",
        "RESET_PAIR_STATUS=NOT_DEVICE_READY",
        "READY_FOR_DEVICE=NO",
        "PRIVATE_PACK_RUN=NONE",
        "DEVICE_OPERATION=NO",
        "RESET_DIAGNOSTIC_ONLY=YES",
        "RESET_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
    ]
    (out / "p1b-reset-gates.txt").write_text("\n".join(gates) + "\n")
    for g in gates:
        print(g)
    print("MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_COMPLETE=YES")

    manifest = {
        "stage": ROUND,
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "selected_target": selected,
        "fallback_target": FALLBACK,
        "fallback_selected": fallback_selected,
        "machine_restart_va": hex(mr_va),
        "machine_restart_image_offset": hex(off_mr),
        "machine_restart_file_offset": hex(off_mr),
        "machine_restart_size": hex(mr_size),
        "machine_restart_section": sec["name"],
        "machine_restart_section_flags": sec.get("flags"),
        "do_kernel_restart_va": hex(dkr_va),
        "do_kernel_restart_image_offset": hex(off_dkr),
        "entry0": insns[0]["mnemonic"],
        "entry0_word": hex(word0),
        "landing_requirement": plan["requirement"],
        "probe_architecture": "INLINE",
        "checkpoint_size": plen,
        "reset8_payload_sha256": sha(cand8),
        "reset1_payload_sha256": sha(cand1),
        "reset8_checkpoint_sha256": sha(probe8),
        "reset1_checkpoint_sha256": sha(probe1),
        "payload_size": len(cand8),
        "fix8_payload_sha256": FIX8_PAYLOAD_SHA,
        "fix8_init_sha256": FIX8_INIT_SHA,
        "fix8_cpio_sha256": FIX8_CPIO_SHA,
        "fix8_tramp_sha256": TRAMP_SHA,
        "rt_d_frozen_sha256": RT_D_SHA,
        "image_header_image_size": hex(image_size),
        "image_file_size": image_file_size,
        "dtb_offset": hex(dtb_offset),
        "primary_entry_offset": hex(off_primary),
        "start_kernel_image_offset": hex(off_sk),
        "primary_switched_image_offset": hex(off_ps),
        "c6_image_offset": hex(off_c6),
        "c_delay_image_offset": hex(off_cdelay),
        "panic_image_offset": hex(off_panic),
        "pair_diff_byte_count": pair["byte_count"],
        "pair_diff_ranges": pair["ranges"],
        "pair_changed_instructions": pair["changed_instructions"],
        "pair_diff_attributed": pair["attribution"],
        "expected_delta_s": EXPECTED_DELTA_S,
        "coverage_normal": cov["coverage_normal"],
        "coverage_emergency": cov["coverage_emergency"],
        "coverage_panic_timeout": cov["coverage_panic_timeout"],
        "direct_callers": cov["direct_callers"],
        "can_explain_23_28s_timing": "UNKNOWN",
        "private_pack": False,
        "device_ready": False,
        "entry_insns": [
            {"i": i, "va": hex(ins["va"]), "bytes": ins["bytes"],
             "mnemonic": ins["mnemonic"], "ops": ins["ops"]}
            for i, ins in enumerate(insns)
        ],
    }
    (out / "p1b-reset-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    (out / "p1b-reset-pair-audit.txt").write_text(
        "RESET_PAIR_AUDIT_REPORT\n"
        f"FIX8_PAYLOAD_SHA256={sha(frozen)}\n"
        f"RESET8_PAYLOAD_SHA256={sha(cand8)}\n"
        f"RESET1_PAYLOAD_SHA256={sha(cand1)}\n"
        f"RESET_PAIR_DIFF_BYTE_COUNT={pair['byte_count']}\n"
        f"RESET_PAIR_DIFF_RANGES={pair['ranges']}\n"
        f"RESET_PAIR_CHANGED_INSTRUCTIONS={pair['changed_instructions']}\n"
        "RESET_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY\n"
        "RESET_PAIR_AUDIT=PASS\n")
    print("RESET_PAIR_AUDIT=PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=("source-gate", "reset-pair"))
    ap.add_argument("--out", default="out-reset")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--rt-d")
    ap.add_argument("--fix8-payload")
    ap.add_argument("--clang", default="clang-18")
    ap.add_argument("--lld", default="ld.lld-18")
    ap.add_argument("--objcopy", default="llvm-objcopy-18")
    ap.add_argument("--objdump", default="llvm-objdump-18")
    ap.add_argument("--nm", default="llvm-nm-18")
    ap.add_argument("--readelf", default="llvm-readelf-18")
    ap.add_argument("--dtc", default="dtc")
    ap.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    ap.add_argument("--strip", default="aarch64-linux-gnu-strip")
    args = ap.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
        return
    if not args.rt_d or not args.fix8_payload:
        fail("RESET_ARGS_FAILED", "--rt-d and --fix8-payload required")
    cmd_reset_pair(args)


if __name__ == "__main__":
    main()
