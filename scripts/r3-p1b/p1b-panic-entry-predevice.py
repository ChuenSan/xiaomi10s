#!/usr/bin/env python3
"""R3 P1B PANIC_ENTRY predevice (MAINLINE_V2_R3_P1B_PANIC_ENTRY_PREDEVICE_READINESS_CI).

GitHub Actions only. Modes:
  source-gate            workflow/source/doc boundary checks (no build)
  panic-entry            frozen-FIX8-anchored PANIC_ENTRY-8 fail-closed candidate
  observer-fixtures      PANIC_ENTRY observer fixture suite
  panic-entry-pack-gates private pack gates over a packed boot v3 image

Baseline is FIXED INIT8. All prior T0-T4/C_DELAY probes are absent.
Unique question: does the current early failure path invoke canonical panic().
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
DOC = REPO / "docs" / "route-r3-p1b-panic-entry-predevice-readiness.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-panic-entry-predevice.yml"
PE_DEVICE_S = HERE / "p1b-panic-entry-device.S"
PE_DEVICE_LD = HERE / "p1b-panic-entry-device.ld"
C_DELAY_DEVICE_S = HERE / "p1b-c-delay-device.S"
C_DELAY_DEVICE_LD = HERE / "p1b-c-delay-device.ld"
T4_DEVICE_S = HERE / "p1b-t4-device.S"
T4_DEVICE_LD = HERE / "p1b-t4-device.ld"
T3_DEVICE_S = HERE / "p1b-t3-device.S"
T3_DEVICE_LD = HERE / "p1b-t3-device.ld"
T2_DEVICE_S = HERE / "p1b-t2-device.S"
T2_DEVICE_LD = HERE / "p1b-t2-device.ld"
T1_DEVICE_S = HERE / "p1b-t1-device.S"
T1_DEVICE_LD = HERE / "p1b-t1-device.ld"
OBSERVER = HERE / "observe-r3-p1b-panic-entry.py"
OBSERVER_FIXTURES = HERE / "observer-panic-entry-fixtures.py"
PRIVATE_WF = REPO / "artifacts" / "p1b-panic-entry-private-workflow-staging.yml"

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
CODE1_OFFSET = pb.CODE1_OFFSET
PAGE = pb.PAGE
FDT_MAGIC = pb.FDT_MAGIC
DTB_OFFSET = 0x2380000
CODE1_B_0X40 = 0x1400000F
FIX8_PAYLOAD_SHA = t3.FIX8_PAYLOAD_SHA
FIX8_PAYLOAD_SIZE = t3.FIX8_PAYLOAD_SIZE
FIX8_IMAGE_FILE_SIZE = t3.FIX8_IMAGE_FILE_SIZE
FIX8_INIT_SHA = t3.FIX8_INIT_SHA
FIX8_CPIO_SHA = t3.FIX8_CPIO_SHA
TRAMP_SHA = t3.TRAMP_SHA
TRAMP_SIZE = 48
PSCI_SYSTEM_RESET_FID = 0x84000009
PACIASP = 0xD503233F
BTI_C = 0xD503245F
ENTRY_PAD_CANDIDATES = {BTI_C: "bti c", PACIASP: "paciasp"}
CORE_SIZE = 0x4C
LINUX_COMMIT = "8b73de7da85fde281a385e0b26eda9bffd3ca477"

C_DELAY_BOOT_SHA = (
    "d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02")
C_DELAY_PAYLOAD_SHA = (
    "372724921ff922dfbf95dcf5081d8527096732a7b402bb63efc01d14f029c52d")
T4_BOOT_SHA = (
    "3827fc0fe4216d7d18ccd2a60ea610a6bd10b2afa269e741923ca3bbc566849d")
T3_BOOT_SHA = (
    "d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df")

FORBIDDEN_BOOT_SHAS = dict(t3.FORBIDDEN_BOOT_SHAS)
FORBIDDEN_BOOT_SHAS["T3_BOOT"] = T3_BOOT_SHA
FORBIDDEN_BOOT_SHAS["T4_BOOT"] = T4_BOOT_SHA
FORBIDDEN_BOOT_SHAS["C_DELAY_BOOT"] = C_DELAY_BOOT_SHA

C_DELAY_REFERENCE_TOTAL_S = 14.464
T4_REFERENCE_TOTAL_S = 14.385
T3_REFERENCE_TOTAL_S = 14.238
T2_REFERENCE_TOTAL_S = 14.240
T1_REFERENCE_TOTAL_S = 14.238
T0_REFERENCE_TOTAL_S = 14.252
PE_DELAY_S = 8
PE_EARLY_LIMIT_S = 20.0
PE_MATCHED_LO_S = -0.5
PE_MATCHED_HI_S = 3.0
PE_SUPPORTED_LO_S = 20.0
PE_SUPPORTED_HI_S = 23.0
PE_NATURAL_LO_S = 23.0
PE_NATURAL_HI_S = 28.0
P0_REF_OVERHEAD_S = 6.1445
FIX8_TOTAL_S = 23.852
PANIC30_TOTAL_S = 26.289
PE_BOOT_SIZE_EXPECTED = 37380096
PE_CLOBBER_REGISTERS = "w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV"

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
    "C_DELAY_VERDICT": "STRONG",
    "C_DELAY_FINAL_GATE": "MAINLINE_V2_R3_P1B_C_DELAY_REACHABILITY_PROVEN",
    "CALIBRATE_DELAY_RUNTIME_STATUS": "PROVEN",
    "PANIC_MDELAY_CALIBRATION_READY": "YES",
    "PANIC_ENTRY_RUNTIME_STATUS": "NOT_PROVEN",
    "PANIC_PARAMETER_RUNTIME_STATUS": "PROVEN",
    "PANIC30_RERUN": "FROZEN",
    "SLOT_A_WRITTEN": "NO",
    "FIX24_STATUS": "FROZEN",
    "M5N_STATUS": "FROZEN",
    "CURRENT_B": "M5D+M5H+M5M-B",
}
STATUS_DOC_ENUM_KV = {
    "PANIC_ENTRY_PREDEVICE_STATUS": ("READY", "NOT_READY"),
    "PANIC_ENTRY_PROBE_ARCHITECTURE": ("INLINE", "EXTERNAL"),
    "PANIC30_RERUN": ("FROZEN", "NO", "YES"),
}

PE_CNTPCT_SAFE_REASON = (
    "CNTFRQ_EL0/CNTPCT_EL0 reads are EL1-legal with SCTLR_EL1.M=1; the "
    "identical access was proven on this device at T0-T4 and C_DELAY; "
    "panic() entry is after calibrate_delay so time_init has run")
PE_PSCI_SAFE_REASON = (
    "PSCI SYSTEM_RESET fid=0x84000009 carries no pointer argument; smc is "
    "synchronous to EL3; psci_dt_init ran inside setup_arch; identical EL1 "
    "smc proven at T0-T4/C_DELAY; frozen RT-D keeps /psci method=smc")


def need(text: str, needle: str, label: str = "PANIC_ENTRY_SOURCE_GATE_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str,
           label: str = "PANIC_ENTRY_SOURCE_GATE_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def parse_status_kv(text: str) -> dict:
    return t3.parse_status_kv(text)


def sx(v: int, bits: int) -> int:
    return pb.sx(v, bits)


def strip_c_comments_and_literals(text: str) -> str:
    """Remove comments, string literals and char literals so that `return` is
    only detected as real code (the SPARC boot-prom message legitimately
    contains the word inside a string)."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i = text.find("*/", i + 2)
            i = n if i < 0 else i + 2
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i + 2)
            i = n if i < 0 else i
            continue
        if c in "\"'":
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def panic_source_audit() -> dict:
    panic_h = (LINUX / "include" / "linux" / "panic.h").read_text()
    panic_c = (LINUX / "kernel" / "panic.c").read_text()
    need(panic_h, "void panic(const char *fmt, ...) __noreturn __cold;")
    need(panic_c, "void panic(const char *fmt, ...)")
    need(panic_c, "This function never returns.")
    need(panic_c, "if (panic_timeout > 0)")
    need(panic_c, "mdelay(PANIC_TIMER_STEP)")
    need(panic_c, "emergency_restart();")
    need(panic_c, "EXPORT_SYMBOL(panic);")
    if panic_c.count("void panic(const char *fmt, ...)") != 1:
        fail("PANIC_ENTRY_CANONICAL_FAILED", "panic() definition count")
    idx = panic_c.index("void panic(const char *fmt, ...)")
    if "never returns" not in panic_c[max(0, idx - 400):idx]:
        fail("PANIC_ENTRY_CANONICAL_FAILED",
             "kernel-doc 'never returns' not attached to the definition")
    body = panic_c[idx:panic_c.index("EXPORT_SYMBOL(panic);")]
    code = strip_c_comments_and_literals(body)
    if re.search(r"\breturn\b", code):
        fail("PANIC_ENTRY_CANONICAL_FAILED",
             "panic() body contains a return statement")
    return {
        "source_file": "kernel/panic.c",
        "declaration": "void panic(const char *fmt, ...) __noreturn __cold;",
        "noreturn": True,
        "cold": True,
        "export_symbol": True,
        "address_taken": True,
    }


def alternative_reset_map() -> dict:
    reboot = (LINUX / "kernel" / "reboot.c").read_text()
    process = (LINUX / "arch" / "arm64" / "kernel" / "process.c").read_text()
    traps = (LINUX / "arch" / "arm64" / "kernel" / "traps.c").read_text()
    panic_c = (LINUX / "kernel" / "panic.c").read_text()
    need(reboot, "void emergency_restart(void)")
    need(reboot, "void kernel_restart(char *cmd)")
    need(reboot, "void orderly_reboot(void)")
    need(reboot, "void do_kernel_restart(char *cmd)")
    need(process, "void machine_restart(char *cmd)")
    need(traps, "void die(const char *str, struct pt_regs *regs, long err)")
    need(panic_c, "void nmi_panic(struct pt_regs *regs, const char *msg)")
    return {
        "emergency_restart": "kernel/reboot.c",
        "kernel_restart": "kernel/reboot.c",
        "orderly_reboot": "kernel/reboot.c",
        "do_kernel_restart": "kernel/reboot.c",
        "machine_restart": "arch/arm64/kernel/process.c",
        "psci_system_reset": "0x84000009 smc (existing T0-T4/C_DELAY proven)",
        "nmi_panic": "kernel/panic.c (calls panic())",
        "die_oops": "arch/arm64/kernel/traps.c",
        "bug_warn_escalation": "kernel/panic.c check_panic_on_warn",
        "watchdog_arch_reset": "SOURCE_MAPPED_NOT_DEVICE_READY",
    }


def nm_panic_symbols(nm_out: str) -> dict:
    """Canonical-entry audit. `panic` must have exactly one definition. Only
    `.isra`/`.constprop` clones create a SECOND entry point; `.cold`/`.part`
    fragments belong to the same canonical function. Symbols merely CONTAINING
    "panic" are never counted as aliases."""
    exact = []
    fragments = []
    clone_entries = []
    aliases = []
    for line in nm_out.splitlines():
        parts = line.split()
        if len(parts) < 3 or not re.fullmatch(r"[0-9a-f]{8,16}", parts[0]):
            continue
        va = int(parts[0], 16)
        kind = parts[1]
        name = parts[-1]
        if name == "panic":
            exact.append((va, kind, name))
        elif re.fullmatch(r"panic\.(cold|part\.[0-9]+)", name):
            fragments.append((va, kind, name))
        elif re.fullmatch(r"panic\.(isra|constprop)\.[0-9]+", name):
            clone_entries.append((va, kind, name))
    if len(exact) != 1:
        fail("PANIC_ENTRY_SYMBOL_FAILED", f"panic nm hits {exact}")
    panic_va = exact[0][0]
    for line in nm_out.splitlines():
        parts = line.split()
        if len(parts) < 3 or not re.fullmatch(r"[0-9a-f]{8,16}", parts[0]):
            continue
        va = int(parts[0], 16)
        name = parts[-1]
        if name in ("panic", "__pfx_panic"):
            continue
        if va == panic_va:
            aliases.append((va, parts[1], name))
    return {"exact": exact, "fragments": fragments,
            "clone_entries": clone_entries, "aliases": aliases}


def dump_panic_entry(tools: dict, vmlinux: Path, va: int, n_insns: int = 32) -> list:
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
    if len(insns) < 3:
        fail("PANIC_ENTRY_DISASM_FAILED", f"only {len(insns)} insns")
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


EXPORT_ADDRESS_TAKEN_METHOD = (
    "EXPORT_SYMBOL(panic) is source-confirmed; a static ADRP page reference to "
    "the panic VA in the frozen Image is scanned as an independent "
    "address-taken witness; relocation targets are not enumerated (only "
    "relocation LOCATIONS inside the window are gated)")


def classify_refs(direct: list, adrp: list, reloc: list,
                  syms: dict, export: bool) -> dict:
    """Section 7: classify every panic reference. `unique` answers only one
    question: do all normal panic calls route into the SAME exact symbol?"""
    n_bl = sum(1 for h in direct if h["kind"] == "BL")
    n_b = sum(1 for h in direct if h["kind"] == "B")
    clone_entries = syms["clone_entries"]
    aliases = syms["aliases"]
    unique = "YES"
    if clone_entries or aliases:
        unique = "PARTIAL"
    types = []
    if n_bl:
        types.append("DIRECT_BL")
    if n_b:
        types.append("DIRECT_B")
    if adrp:
        types.append("ADRP_PAGE_REF")
    if reloc:
        types.append("RELOCATION_IN_WINDOW")
    if export:
        types.append("EXPORT_SYMBOL_ADDRESS_TAKEN")
    return {
        "direct_bl": n_bl,
        "direct_b": n_b,
        "adrp": len(adrp),
        "reloc": len(reloc),
        "fragment_count": len(syms["fragments"]),
        "clone_entry_count": len(clone_entries),
        "alias_count": len(aliases),
        "export": export,
        "unique": unique,
        "branch_types": ",".join(types) if types else "NONE",
        "indirect": bool(adrp or export),
    }


def landing_plan(word0: int, refs: dict, cfg: dict) -> dict:
    """Section 9: decide the preserved prefix from the REAL call/landing
    evidence, fail-closed on an unknown prologue word."""
    pad = ENTRY_PAD_CANDIDATES.get(word0)
    bti_on = cfg.get("CONFIG_ARM64_BTI_KERNEL") == "y"
    if pad is None:
        fail("PANIC_ENTRY_LANDING_FAILED",
             f"panic entry word {word0:#010x} is neither a BTI landing pad nor "
             "the PAC prologue; preserving an unknown instruction could touch "
             "memory/SP, so the INLINE probe is NOT DEVICE READY")
    if pad == "bti c":
        return {
            "prefix": word0,
            "prefix_name": "bti c",
            "requirement": "PRESERVE_BTI_C_LANDING_PAD",
            "satisfied": True,
            "probe_size": CORE_SIZE + 4,
            "reason": "entry0 is a BTI landing pad; it is re-emitted verbatim",
        }
    if bti_on and refs["indirect"]:
        return {
            "prefix": word0,
            "prefix_name": "paciasp",
            "requirement": "PRESERVE_ENTRY_WORD_ADDRESS_TAKEN_NO_BTI_PAD",
            "satisfied": True,
            "probe_size": CORE_SIZE + 4,
            "reason": "entry0 is the PAC prologue, not a BTI pad, while the "
                      "symbol is address-taken (exported): the original entry "
                      "word is re-emitted verbatim; canonical uniqueness is "
                      "reported PARTIAL and no BTI landing claim is made",
        }
    return {
        "prefix": word0,
        "prefix_name": "paciasp",
        "requirement": "PRESERVE_ENTRY_WORD_DIRECT_CALLS_ONLY",
        "satisfied": True,
        "probe_size": CORE_SIZE + 4,
        "reason": "all audited arrivals are direct branches; the original "
                  "entry word is re-emitted verbatim",
    }


def panic_entry_minus_c_delay(total: float) -> float:
    return total - C_DELAY_REFERENCE_TOTAL_S


def panic_entry_reachability(total, recovery_kind: str) -> dict:
    iso_n = "MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI"
    nxt = "WAIT_FOR_USER_APPROVAL"
    if recovery_kind == "AUTOMATIC_STABLE_FASTBOOT_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "PANIC_ENTRY_STABLE_FASTBOOT",
                "next": iso_n}
    if recovery_kind == "MANUAL_RECOVERY_OR_NO_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "PANIC_ENTRY_NO_RETURN",
                "next": iso_n}
    if total is None or recovery_kind != "AUTOMATIC_ANDROID_RETURN":
        return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN", "next": iso_n}
    if total < PE_EARLY_LIMIT_S:
        d = panic_entry_minus_c_delay(total)
        sub = "VERY_STRONG_MATCHED" if PE_MATCHED_LO_S <= d <= PE_MATCHED_HI_S \
            else "DISTINCTIVE_EARLY"
        return {"verdict": "STRONG", "case": "PENTRY_A_STRONG",
                "subclass": sub, "next": nxt}
    if PE_SUPPORTED_LO_S <= total < PE_SUPPORTED_HI_S:
        return {"verdict": "SUPPORTED", "case": "PENTRY_B_SUPPORTED",
                "next": nxt}
    if PE_NATURAL_LO_S <= total < PE_NATURAL_HI_S:
        return {"verdict": "NOT_OBSERVED",
                "case": "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED", "next": iso_n}
    return {"verdict": "NOT_OBSERVED", "case": "UNKNOWN", "next": iso_n}


def run_decoder_fixtures() -> list:
    lines = []
    nxt = "WAIT_FOR_USER_APPROVAL"
    iso_n = "MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI"

    def case(name, total, kind, want_v, want_c=None, want_next=None):
        got = panic_entry_reachability(total, kind)
        if got["verdict"] != want_v:
            fail("PANIC_ENTRY_DECODER_FIXTURE_FAILED",
                 f"{name}: {got['verdict']} != {want_v}")
        if want_c and got["case"] != want_c:
            fail("PANIC_ENTRY_DECODER_FIXTURE_FAILED",
                 f"{name}: case {got['case']} != {want_c}")
        if want_next and got["next"] != want_next:
            fail("PANIC_ENTRY_DECODER_FIXTURE_FAILED",
                 f"{name}: next {got['next']} != {want_next}")
        lines.append(f"PANIC_ENTRY_DECODER_{name}=PASS verdict={got['verdict']} "
                     f"case={got['case']}")

    case("STRONG_14P464S", 14.464, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "PENTRY_A_STRONG", nxt)
    case("STRONG_16P000S", 16.000, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "PENTRY_A_STRONG", nxt)
    case("STRONG_17P464S", 17.464, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "PENTRY_A_STRONG", nxt)
    case("STRONG_18P500S", 18.500, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "PENTRY_A_STRONG", nxt)
    case("STRONG_19P999S", 19.999, "AUTOMATIC_ANDROID_RETURN", "STRONG",
         "PENTRY_A_STRONG", nxt)
    case("SUPPORTED_21P000S", 21.000, "AUTOMATIC_ANDROID_RETURN", "SUPPORTED",
         "PENTRY_B_SUPPORTED", nxt)
    case("CASE_C_FIX8", FIX8_TOTAL_S, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED", iso_n)
    case("CASE_C_PANIC30", PANIC30_TOTAL_S, "AUTOMATIC_ANDROID_RETURN",
         "NOT_OBSERVED", "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED", iso_n)
    case("CASE_E", None, "AUTOMATIC_STABLE_FASTBOOT_RETURN",
         "NOT_OBSERVED", "PANIC_ENTRY_STABLE_FASTBOOT", iso_n)
    case("CASE_F", None, "MANUAL_RECOVERY_OR_NO_RETURN",
         "NOT_OBSERVED", "PANIC_ENTRY_NO_RETURN", iso_n)
    got = panic_entry_reachability(18.500, "AUTOMATIC_ANDROID_RETURN")
    if got.get("subclass") == "VERY_STRONG_MATCHED":
        fail("PANIC_ENTRY_DECODER_FIXTURE_FAILED", "18.5s should be unmatched")
    got = panic_entry_reachability(16.000, "AUTOMATIC_ANDROID_RETURN")
    if got.get("subclass") != "VERY_STRONG_MATCHED":
        fail("PANIC_ENTRY_DECODER_FIXTURE_FAILED", "16s should be matched")
    lines.append("PANIC_ENTRY_DECODER_C_DELAY_NOT_SYMMETRIC_WINDOW=PASS")
    lines.append("PANIC_ENTRY_DECODER_NO_LINUX_PANIC_LICENSE=NO")
    lines.append("PANIC_ENTRY_DECODER_FIXTURES=PASS")
    return lines


def _movz(sf: int, imm16: int, hw: int, rd: int) -> int:
    """ARM64 MOVZ encoding (pure arithmetic, no toolchain involved)."""
    opc = 0b10
    return ((sf & 1) << 31) | (opc << 29) | (0b100101 << 23) | \
        ((hw & 0x3) << 21) | ((imm16 & 0xFFFF) << 5) | (rd & 0x1F)


def _movk(sf: int, imm16: int, hw: int, rd: int) -> int:
    """ARM64 MOVK encoding."""
    opc = 0b11
    return ((sf & 1) << 31) | (opc << 29) | (0b100101 << 23) | \
        ((hw & 0x3) << 21) | ((imm16 & 0xFFFF) << 5) | (rd & 0x1F)


def _mrs(op0: int, op1: int, crn: int, crm: int, op2: int, rt: int) -> int:
    """ARM64 MRS encoding."""
    return (0b1101010100 << 22) | (1 << 21) | ((op0 & 0x3) << 19) | \
        ((op1 & 0x7) << 16) | ((crn & 0xF) << 12) | ((crm & 0xF) << 8) | \
        ((op2 & 0x7) << 5) | (rt & 0x1F)


W_DELAY_8S = _movz(1, 8, 0, 10)
if W_DELAY_8S != 0xD280010A:
    fail("PANIC_ENTRY_ENCODING_CALIBRATION_FAILED",
         f"MOVZ encoder off: {W_DELAY_8S:#010x} != 0xd280010a "
         "(the 8s delay word published by the T0-T4/C_DELAY verify jobs)")
W_CNTFRQ_X9 = _mrs(3, 3, 14, 0, 0, 9)
W_CNTPCT_X11 = _mrs(3, 3, 14, 0, 1, 11)
W_CNTPCT_X12 = _mrs(3, 3, 14, 0, 1, 12)
W_SMC = 0xD4000003
W_WFE = 0xD503205F
W_NOP = 0xD503201F


def _decode_wide_imm(w: int) -> dict:
    """Decode a MOVZ/MOVK-class word. The field positions are CALIBRATED at
    import against the published 8s delay word, so this decoder is an
    independent witness for the PSCI FID words (not a re-encode)."""
    return {
        "sf": (w >> 31) & 1,
        "opc": (w >> 29) & 0x3,
        "fixed": (w >> 23) & 0x3F,
        "hw": (w >> 21) & 0x3,
        "imm16": (w >> 5) & 0xFFFF,
        "rd": w & 0x1F,
    }


DECODER_CALIBRATION = _decode_wide_imm(W_DELAY_8S)
if DECODER_CALIBRATION != {"sf": 1, "opc": 2, "fixed": 0x25, "hw": 0,
                          "imm16": 8, "rd": 10}:
    fail("PANIC_ENTRY_ENCODING_CALIBRATION_FAILED",
         f"wide-immediate decoder off: {DECODER_CALIBRATION}")


def psci_fid_from_probe(words: list, pad_n: int) -> int:
    lo = _decode_wide_imm(words[14 + pad_n])
    hi = _decode_wide_imm(words[15 + pad_n])
    if lo["sf"] or lo["opc"] != 2 or lo["fixed"] != 0x25 or lo["hw"] or \
            lo["rd"]:
        fail("PANIC_ENTRY_PSCI_FAILED", f"low FID half is not movz w0: {lo}")
    if hi["sf"] or hi["opc"] != 3 or hi["fixed"] != 0x25 or hi["hw"] != 1 or \
            hi["rd"]:
        fail("PANIC_ENTRY_PSCI_FAILED", f"high FID half is not movk w0,lsl#16: {hi}")
    fid = lo["imm16"] | (hi["imm16"] << 16)
    if fid != PSCI_SYSTEM_RESET_FID:
        fail("PANIC_ENTRY_PSCI_FAILED",
             f"decoded PSCI fid {fid:#010x} != {PSCI_SYSTEM_RESET_FID:#010x}")
    return fid

# Authoritative semantics check on the DISASSEMBLY, independent of the word
# encoders above (llvm-objdump produced these strings from the same bytes).
PROBE_OPS_REQUIRED = (
    "msr daifset, #0xf",
    "mrs x9, cntfrq_el0",
    "movz x10, #8",
    "mrs x11, cntpct_el0",
    "mrs x12, cntpct_el0",
    "b.hs",
    "yield",
    "smc #0",
    "wfe",
)
PROBE_OPS_FID_RE = (
    re.compile(r"\bmovz\s+w0,\s+#(0x9|9)\b"),
    re.compile(r"\bmovk\s+w0,\s+#(0x8400|33792),\s+lsl\s+#16\b"),
)


def gate_probe_ops_semantics(ops: str) -> None:
    for tok in PROBE_OPS_REQUIRED:
        if tok not in ops:
            fail("PANIC_ENTRY_CORE_IDENTITY_FAILED",
                 f"probe disassembly lacks {tok!r}")
    for rx in PROBE_OPS_FID_RE:
        if not rx.search(ops):
            fail("PANIC_ENTRY_PSCI_FAILED",
                 f"probe disassembly lacks PSCI FID half {rx.pattern!r}")
    for bad in ("panic_timeout", "mdelay", "udelay", "loops_per_jiffy",
                "mrs x0", "cntvct"):
        if bad in ops:
            fail("PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_FAILED",
                 f"probe disassembly mentions {bad!r}")


def gate_probe_words(probe: bytes) -> None:
    """Word-level fail-closed gates on the composed probe. Rejects any
    deviation from the T0-T4/C_DELAY proven core semantics."""
    if len(probe) % 4:
        fail("PANIC_ENTRY_CORE_IDENTITY_FAILED", f"probe size {len(probe)}")
    words = list(struct.unpack_from(f"<{len(probe) // 4}I", probe, 0))
    pad_n = 0
    if len(words) == 20:
        if words[0] not in (PACIASP, BTI_C):
            fail("PANIC_ENTRY_LANDING_FAILED", f"pad word {words[0]:#010x}")
        pad_n = 1
    elif len(words) != 19:
        fail("PANIC_ENTRY_CORE_IDENTITY_FAILED", f"word count {len(words)}")
    if words[3 + pad_n] != W_DELAY_8S:
        fail("PANIC_ENTRY_DELAY_CONSTANT_FAILED",
             f"8s delay word {words[3 + pad_n]:#010x} != {W_DELAY_8S:#010x}")
    psci_fid_from_probe(words, pad_n)
    smc = [i for i, w in enumerate(words) if w == W_SMC]
    if len(smc) != 1 or smc[0] != 16 + pad_n:
        fail("PANIC_ENTRY_PSCI_FAILED", f"smc index {smc}")
    if words[17 + pad_n] != W_WFE:
        fail("PANIC_ENTRY_PSCI_FAILED", "no wfe after smc (fall-through risk)")
    w = words[18 + pad_n]
    if (w >> 26) != 0b000101:
        fail("PANIC_ENTRY_PSCI_FAILED", "no branch after wfe")
    if (18 + pad_n) * 4 + sx(w & 0x03FFFFFF, 26) * 4 != (17 + pad_n) * 4:
        fail("PANIC_ENTRY_PSCI_FAILED", "terminal branch does not loop on wfe")
    for idx, w in enumerate(words):
        addr = idx * 4
        top = w >> 26
        if top in (0b000101, 0b100101):
            t = addr + sx(w & 0x03FFFFFF, 26) * 4
        elif (w >> 24) == 0x54:
            t = addr + sx((w >> 5) & 0x7FFFF, 19) * 4
        else:
            continue
        if not (0 <= t < len(probe)):
            fail("PANIC_ENTRY_PSCI_FAILED",
                 f"branch leaves probe: {addr:#x} -> {t:#x}")


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
            fail("PANIC_ENTRY_NEGATIVE_FIXTURE_FAILED",
                 f"{name}: rejected with {msg!r}, expected {label!r}")
        return f"PANIC_ENTRY_NEGATIVE_{name}_REJECTED=PASS"
    fail("PANIC_ENTRY_NEGATIVE_FIXTURE_FAILED", f"{name} was accepted")
    return ""


def run_negative_fixtures(ctx: dict) -> list:
    lines: list = []
    frozen = ctx["frozen"]
    cand = ctx["cand"]
    off_ck = ctx["off_ck"]
    plen = ctx["probe_len"]
    pad_n = ctx["pad_n"]
    probe = ctx["probe"]
    region = (off_ck, off_ck + plen)

    def add(name, fn, label):
        lines.append(expect_reject(name, fn, label))

    add("WRONG_PANIC_SYMBOL",
        lambda: t3.nm_symbol("0000000000000000 T not_panic\n", "panic"),
        "T3_IDENTITY_FAILED")
    add("WRONG_CANONICAL_SYMBOL",
        lambda: nm_panic_symbols(
            "ffff8000802b1b18 T panic\nffff8000802b1c00 T panic\n"),
        "PANIC_ENTRY_SYMBOL_FAILED")
    add("WRONG_ENTRY_OFFSET",
        lambda: t3.gate_window_inside_image_size(
            ctx["image_size"] - 8, plen, ctx["image_size"]),
        "T3_GEOMETRY_FAILED")
    add("LANDING_REQUIREMENT_BROKEN",
        lambda: landing_plan(0xD503201F, {"indirect": True},
                             {"CONFIG_ARM64_BTI_KERNEL": "y"}),
        "PANIC_ENTRY_LANDING_FAILED")
    add("PAC_BTI_RULE_BROKEN",
        lambda: gate_probe_words(probe_patch(probe, 0, W_NOP)),
        "PANIC_ENTRY_LANDING_FAILED")
    add("RUNTIME_REWRITE_TARGET_OVERLAP",
        lambda: t3.gate_table_entries(
            "altinstructions", [ctx["ck_va"]], (ctx["ck_va"], ctx["ck_va"] + plen)),
        "T3_RUNTIME_REWRITE_FAILED")
    add("UNSAFE_INLINE_OVERWRITE",
        lambda: t3.gate_probe_mapping("PADDING_0x2230000"),
        "T3_MAPPING_FAILED")
    add("STACK_USE",
        lambda: t3.gate_no_forbidden(ctx["ops"] + "\nstp x29, x30, [sp, #-16]!"),
        "T3_DISASM_FAILED")
    add("MEMORY_STORE",
        lambda: t3.gate_no_forbidden(ctx["ops"] + "\nstr x0, [x1]"),
        "T3_DISASM_FAILED")
    add("MEMORY_LOAD",
        lambda: t3.gate_no_forbidden(ctx["ops"] + "\nldr x0, [x1]"),
        "T3_DISASM_FAILED")
    add("WRONG_8S_CONSTANT",
        lambda: gate_probe_words(probe_patch(probe, 3 + pad_n, _movz(1, 16, 0, 10))),
        "PANIC_ENTRY_DELAY_CONSTANT_FAILED")
    add("WRONG_PSCI_FID",
        lambda: gate_probe_words(probe_patch(probe, 14 + pad_n, _movz(0, 0x0008, 0, 0))),
        "PANIC_ENTRY_PSCI_FAILED")
    add("MISSING_SMC",
        lambda: gate_probe_words(probe_patch(probe, 16 + pad_n, W_NOP)),
        "PANIC_ENTRY_PSCI_FAILED")
    add("FALL_THROUGH",
        lambda: gate_probe_words(probe_patch(probe, 18 + pad_n, W_NOP)),
        "PANIC_ENTRY_PSCI_FAILED")
    add("RUNTIME_RELOCATION",
        lambda: t3.gate_no_relocations(
            "Relocation section with R_AARCH64_ABS64", "probe"),
        "T3_RELOC_FAILED")
    add("EXTRA_PAYLOAD_DIFF",
        lambda: t3.gate_payload_diff(frozen, cand + b"\x00", region),
        "T3_PAYLOAD_DIFF_FAILED")
    add("RT_D_PANIC_CHANGED",
        lambda: t3.gate_trailer(bytes(bytearray(cand)[:-4] + b"XXXX")),
        "T3_PAYLOAD_DIFF_FAILED")
    bad_cd = bytearray(cand)
    off_cd = ctx["off_cdelay"]
    bad_cd[off_cd:off_cd + CORE_SIZE] = ctx["t1_core"]
    add("PRIOR_C_DELAY_PROBE_REMAINS",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_cd), region),
        "T3_PAYLOAD_DIFF_FAILED")
    bad_t4 = bytearray(cand)
    off_c6 = ctx["off_c6"]
    bad_t4[off_c6:off_c6 + CORE_SIZE] = ctx["t1_core"]
    add("T4_PROBE_REMAINS",
        lambda: t3.gate_tail_identity(frozen, bytes(bad_t4), region),
        "T3_PAYLOAD_DIFF_FAILED")
    add("NORMAL_PATH_MODIFIED",
        lambda: t3.gate_tramp_identity(
            b"\x00" * TRAMP_SIZE + cand[TRAMP_OFFSET + TRAMP_SIZE:]),
        "T3_IDENTITY_FAILED")
    add("GEOMETRY_MISMATCH",
        lambda: t3.gate_geometry(
            bytes(cand[:16] + b"\x00" * 8 + cand[24:]), ctx["image_size"]),
        "T3_GEOMETRY_FAILED")
    src = PE_DEVICE_S.read_text()
    for bad in ("panic_timeout", "mdelay", "udelay", "loops_per_jiffy"):
        if bad in src:
            fail("PANIC_ENTRY_NEGATIVE_FIXTURE_FAILED",
                 f"diagnostic source mentions {bad}")
    lines.append("PANIC_ENTRY_NEGATIVE_PANIC_TIMEOUT_READ_BY_DIAGNOSTIC_REJECT=PASS")
    lines.append("PANIC_ENTRY_NEGATIVE_MDELAY_USED_BY_DIAGNOSTIC_REJECT=PASS")
    lines.append("PANIC_ENTRY_NEGATIVE_FIXTURES=PASS")
    return lines


def compose_probe(core: bytes, plan: dict) -> bytes:
    if plan["prefix"] is None:
        if len(core) != CORE_SIZE:
            fail("PANIC_ENTRY_CORE_IDENTITY_FAILED", f"core {len(core)}")
        return core
    return struct.pack("<I", plan["prefix"]) + core


def cmd_panic_entry(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = iso.probe_toolchain(args)
    src = panic_source_audit()
    altmap = alternative_reset_map()
    print("PANIC_SOURCE_FILE=" + src["source_file"])
    print("PANIC_FUNCTION_DECLARATION=" + src["declaration"])
    print("PANIC_NORETURN=YES")
    print("PANIC_COLD=YES")
    print("PANIC_EXPORT_SYMBOL=YES")
    print("PANIC_ALTERNATIVE_RESET_PATH_MAP=YES")
    for k, v in altmap.items():
        print(f"PANIC_ALT_RESET_{k.upper()}={v}")

    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "frozen RT-D identity")
    frozen = Path(args.fix8_payload).read_bytes()
    if sha(frozen) != FIX8_PAYLOAD_SHA or len(frozen) != FIX8_PAYLOAD_SIZE:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "frozen FIX8 payload")
    fhdr = pb.parse_image_hdr(frozen, "frozen-fix8-payload")
    if fhdr["code1"] != CODE1_B_0X40:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "frozen code1 not b 0x40")
    image_size = fhdr["image_size"]
    t3.gate_image_size_rederived(image_size, "frozen-fix8-payload")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("PANIC_ENTRY_IDENTITY_FAILED", f"dtb_offset {dtb_offset:#x}")
    t3.gate_tramp_identity(frozen)
    print(f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}")
    print(f"IMAGE_FILE_SIZE={FIX8_IMAGE_FILE_SIZE}")
    print(f"DTB_OFFSET={dtb_offset:#x}")
    print("IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES")
    print("PANIC_ENTRY_BASELINE=FROZEN_FIX8")

    init = pb.compile_init(out, PE_DELAY_S, args.gcc, args.strip)
    if sha(init.read_bytes()) != FIX8_INIT_SHA:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "/init sha")
    cpio = out / f"initramfs-{PE_DELAY_S}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    if sha(cpio.read_bytes()) != FIX8_CPIO_SHA:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "cpio sha")
    print("PANIC_ENTRY_INIT_IDENTITY=YES")
    print("PANIC_ENTRY_INITRAMFS_IDENTITY=YES")

    k = pb.make_kernel(out, PE_DELAY_S, cpio, args.jobs)
    iso.check_merged_config(k["config"])
    cfg = t3.config_symbols(k["config"].read_text())
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    image_file_size = len(image)
    if kg["hdr"]["image_size"] != image_size:
        fail("PANIC_ENTRY_BUILD_FAILED", "rebuilt image_size drift")
    if image_file_size != FIX8_IMAGE_FILE_SIZE:
        fail("PANIC_ENTRY_BUILD_FAILED", "rebuilt file size drift")
    print(f"PANIC_ENTRY_REBUILT_IMAGE_IDENTITY=YES file_size={image_file_size}")

    nm_out = pb.run([tools["nm"], str(k["vmlinux"])])
    text_addr = t3.nm_symbol(nm_out, "_text")
    off_primary = t3.nm_symbol(nm_out, "primary_entry") - text_addr
    sk_va, _sk_ext = t3.symbol_extent(nm_out, "start_kernel")
    ps_va, _ps_ext = t3.symbol_extent(nm_out, "__primary_switched")
    pa_va = t3.nm_symbol(nm_out, "parse_args")
    cal_va = t3.nm_symbol(nm_out, "calibrate_delay")
    off_sk = sk_va - text_addr
    off_ps = ps_va - text_addr
    panic_syms = nm_panic_symbols(nm_out)
    panic_va, panic_kind, _n = panic_syms["exact"][0]
    panic_va2, panic_extent = t3.symbol_extent(nm_out, "panic")
    if panic_va2 != panic_va:
        fail("PANIC_ENTRY_SYMBOL_FAILED", "extent va mismatch")
    off_panic = panic_va - text_addr
    sm_off = t3.sysmap_symbol(k["sysmap"], "panic") - \
        t3.sysmap_symbol(k["sysmap"], "_text")
    if sm_off != off_panic:
        fail("PANIC_ENTRY_SYMBOL_FAILED", "nm/sysmap panic mismatch")
    print("PANIC_SYMBOL_REDERIVED=YES")
    print(f"PANIC_LINK_VA={panic_va:#x}")
    print(f"PANIC_IMAGE_OFFSET={off_panic:#x}")
    print(f"PANIC_FILE_OFFSET={off_panic:#x}")
    print(f"PANIC_NM_TYPE={panic_kind}")
    if panic_extent is None:
        fail("PANIC_ENTRY_SYMBOL_FAILED", "panic unbounded")
    panic_size = panic_extent - panic_va
    print(f"PANIC_SIZE={panic_size:#x}")
    print(f"PANIC_FRAGMENT_COUNT={len(panic_syms['fragments'])}")
    print(f"PANIC_CLONE_ENTRY_COUNT={len(panic_syms['clone_entries'])}")
    print(f"PANIC_ALIAS_COUNT={len(panic_syms['aliases'])}")

    insns, dump_panic = dump_panic_entry(tools, k["vmlinux"], panic_va, 32)
    (out / "p1b-panic-entry-vmlinux-disasm.txt").write_text(dump_panic)
    for i, ins in enumerate(insns[:8]):
        print(f"PANIC_ENTRY_INSN_{i}={ins['mnemonic']}")
        print(f"PANIC_ENTRY_BYTES_{i}={ins['bytes']}")
    word0 = struct.unpack_from("<I", frozen, off_panic)[0]
    word0_vmlinux = struct.unpack_from("<I", image, off_panic)[0]
    if word0 != word0_vmlinux:
        fail("PANIC_ENTRY_IDENTITY_FAILED",
             f"FIX8 panic word0 {word0:#010x} != vmlinux {word0_vmlinux:#010x}")
    print(f"PANIC_ENTRY_ORIGINAL_WORD0={word0:#010x}")

    dump_sk = pb.run([
        tools["objdump"], "-d",
        f"--start-address={sk_va:#x}",
        f"--stop-address={sk_va + 0x4000:#x}", str(k["vmlinux"])])
    cal_hits = []
    for line in dump_sk.splitlines():
        m = INSTR_RE.match(line)
        if not m or m.group(3) != "bl":
            continue
        op = re.search(r"(?:0x)?([0-9a-f]+)", m.group(4) or "")
        if op and int(op.group(1), 16) == cal_va:
            cal_hits.append(int(m.group(1), 16))
    if len(cal_hits) != 1:
        fail("PANIC_ENTRY_IDENTITY_FAILED", f"calibrate_delay bl {cal_hits}")
    off_cdelay = cal_hits[0] + 4 - text_addr
    pa_hits = []
    for line in dump_sk.splitlines():
        m = INSTR_RE.match(line)
        if not m or m.group(3) != "bl":
            continue
        op = re.search(r"(?:0x)?([0-9a-f]+)", m.group(4) or "")
        if op and int(op.group(1), 16) == pa_va:
            pa_hits.append(int(m.group(1), 16))
    if not pa_hits:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "no parse_args bl")
    off_c6 = pa_hits[0] + 4 - text_addr

    frozen_image = frozen[:image_file_size]
    direct = scan_direct_calls(frozen_image, text_addr, image_size, panic_va)
    adrp = scan_adrp_refs(frozen_image, text_addr, image_size, panic_va)
    reloc = t3.relocation_offsets(out, tools, k["vmlinux"])
    reloc_hits = [r for r in reloc if panic_va <= r < panic_va + CORE_SIZE + 4]
    refs = classify_refs(direct, adrp, reloc_hits, panic_syms,
                         src["export_symbol"])
    refs["method"] = EXPORT_ADDRESS_TAKEN_METHOD
    print(f"PANIC_DIRECT_CALLSITE_COUNT={refs['direct_bl']}")
    print(f"PANIC_DIRECT_B_COUNT={refs['direct_b']}")
    print(f"PANIC_INDIRECT_REFERENCE_COUNT={refs['adrp'] + int(refs['export'])}")
    print(f"PANIC_ADRP_PAGE_REF_COUNT={refs['adrp']}")
    print(f"PANIC_ALIAS_COUNT={refs['alias_count']}")
    print(f"PANIC_ENTRY_BRANCH_TYPES={refs['branch_types']}")
    print(f"PANIC_ADDRESS_TAKEN_METHOD={refs['method']}")
    print(f"PANIC_CANONICAL_ENTRY_UNIQUE={refs['unique']}")

    plan = landing_plan(word0, refs, cfg)
    print(f"PANIC_ENTRY_LANDING_REQUIREMENT={plan['requirement']}")
    print(f"PANIC_ENTRY_LANDING_REQUIREMENT_SATISFIED="
          f"{'YES' if plan['satisfied'] else 'NO'}")
    print(f"PANIC_ENTRY_PREFIX_PRESERVED={plan['prefix_name']}")
    print(f"PANIC_ENTRY_LANDING_REASON={plan['reason']}")
    expected_mn = ENTRY_PAD_CANDIDATES[word0].split()[0]
    t3.gate_instrumentation_audit(cfg, expected_mn, word0)
    t3.gate_sk_entry_insn(
        word0,
        struct.unpack_from("<I", frozen, off_panic + 4)[0],
        word0)
    print(f"PANIC_ENTRY_ENTRY_INSTRUMENTATION_AUDITED=YES "
          f"(entry0={expected_mn} word0={word0:#010x})")
    for sym in ("CONFIG_CFI_CLANG", "CONFIG_SHADOW_CALL_STACK",
                "CONFIG_FUNCTION_TRACER", "CONFIG_DYNAMIC_FTRACE",
                "CONFIG_KASAN", "CONFIG_KCOV"):
        if cfg.get(sym) == "y":
            fail("PANIC_ENTRY_ENTRY_INSTRUMENTATION_FAILED", f"{sym}=y")
        print(f"PANIC_ENTRY_CFG_{sym}={cfg.get(sym, 'ABSENT')}")
    print(f"PANIC_ENTRY_CFG_CONFIG_ARM64_BTI_KERNEL="
          f"{cfg.get('CONFIG_ARM64_BTI_KERNEL', 'ABSENT')}")
    print(f"PANIC_ENTRY_CFG_CONFIG_ARM64_PTR_AUTH_KERNEL="
          f"{cfg.get('CONFIG_ARM64_PTR_AUTH_KERNEL', 'ABSENT')}")

    sections = t3.section_map(out, tools, k["vmlinux"])
    if not any(s.get("flags") for s in sections):
        for s in sections:
            if s["vma"] <= panic_va < s["vma"] + s["size"]:
                s["code"] = True
                s["alloc"] = True
    plen_plan = plan["probe_size"]
    symbol_vas = sorted({int(l.split()[0], 16) for l in nm_out.splitlines()
                         if re.match(r"^[0-9a-f]{16} ", l)})
    window_va = (panic_va, panic_va + plen_plan)
    sec = t3.gate_window_section_scan(panic_va, plen_plan, sections)
    t3.gate_window_inside_image_size(off_panic, plen_plan, image_size)
    n_sym = t3.gate_window_symbol_scan(panic_va, plen_plan, symbol_vas)
    exec_ranges = [(s["vma"] - text_addr, s["vma"] - text_addr + s["size"])
                   for s in sections if s.get("code") and s.get("alloc")]
    cand_hits = t3.branch_candidates(frozen_image, exec_ranges, window_va)
    confirmed = [(s, t) for s, t in cand_hits
                 if t3.confirm_branch(tools, k["vmlinux"], s, t)]
    n_raw = t3.gate_window_branch_scan(panic_va, plen_plan, confirmed)
    n_rel = t3.gate_window_relocation_scan(panic_va, plen_plan, reloc)
    n_lit = t3.gate_window_literal_scan(panic_va, plen_plan, frozen_image)
    t3.gate_function_extent_scan(panic_va, plen_plan, panic_extent)
    rw = t3.runtime_rewrite_scan(out, tools, k["vmlinux"], sections, window_va)
    t3.gate_probe_mapping("KERNEL_TEXT_VA_SELF_EVIDENT")
    print("PANIC_ENTRY_RUNTIME_REWRITE_TARGETS=NONE_IN_WINDOW")
    print("PANIC_ENTRY_INLINE_OVERWRITE_SAFE=YES")
    print("PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE")
    print(f"PANIC_ENTRY_SECTION={sec['name']}")
    print(f"PANIC_ENTRY_SECTION_FLAGS={sec.get('flags')}")
    print(f"PANIC_ENTRY_SYMBOL_SCAN=PASS ({n_sym} symbols)")
    print(f"PANIC_ENTRY_BRANCH_SCAN=PASS ({n_raw} confirmed)")
    print(f"PANIC_ENTRY_RELOCATION_SCAN=PASS ({n_rel} reloc sites)")
    print(f"PANIC_ENTRY_LITERAL_SCAN=PASS ({n_lit} slots)")
    for tag, canon in (("__ex_table", "PANIC_ENTRY_EXCEPTION_TABLE_SCAN"),
                       ("altinstructions", "PANIC_ENTRY_ALTINSTRUCTIONS_SCAN"),
                       ("__jump_table", "PANIC_ENTRY_JUMP_TABLE_SCAN"),
                       ("static_call_sites", "PANIC_ENTRY_STATIC_CALL_SITES_SCAN"),
                       ("kcfi_traps", "PANIC_ENTRY_KCFI_TRAPS_SCAN")):
        info = rw[tag]
        state = f"entries={info['entries']}" if info.get("present") else "ABSENT"
        print(f"{canon}=PASS ({state}, none in window)")

    head_text = (LINUX / "arch" / "arm64" / "kernel" / "head.S").read_text()
    t3.gate_no_early_counter_trap(
        head_text,
        (LINUX / "arch/arm64/kernel/hyp-stub.S").read_text())
    t3.gate_cnppct_safety(PE_CNTPCT_SAFE_REASON, True)
    t3.gate_psci_safety(PE_PSCI_SAFE_REASON, True)
    print("PANIC_ENTRY_CNTPCT_SAFE=YES")
    print("PANIC_ENTRY_PSCI_SAFE=YES")

    core, ops, dump = t3.build_probe(
        out, tools, PE_DEVICE_S, PE_DEVICE_LD, "P1B_PANIC_ENTRY_DELAY",
        PE_DELAY_S, "r3_panic_entry_checkpoint", "p1b-panic-entry-core")
    t1_probe, _o, _d = t3.build_probe(
        out, tools, T1_DEVICE_S, T1_DEVICE_LD, "P1B_T1_DELAY", 8,
        "r3_t1_checkpoint", "p1b-t1-core-reference")
    t2_probe, _o, _d = t3.build_probe(
        out, tools, T2_DEVICE_S, T2_DEVICE_LD, "P1B_T2_DELAY", 8,
        "r3_t2_checkpoint", "p1b-t2-probe-reference")
    t3_probe, _o, _d = t3.build_probe(
        out, tools, T3_DEVICE_S, T3_DEVICE_LD, "P1B_T3_DELAY", 8,
        "r3_t3_checkpoint", "p1b-t3-probe-reference", march="armv8.5-a")
    t4_probe, _o, _d = t3.build_probe(
        out, tools, T4_DEVICE_S, T4_DEVICE_LD, "P1B_T4_DELAY", 8,
        "r3_t4_checkpoint", "p1b-t4-probe-reference")
    cd_probe, _o, _d = t3.build_probe(
        out, tools, C_DELAY_DEVICE_S, C_DELAY_DEVICE_LD, "P1B_C_DELAY_DELAY", 8,
        "r3_c_delay_checkpoint", "p1b-c-delay-core-reference")
    t3.gate_t3_probe(ops, dump, len(core))
    gate_probe_ops_semantics(ops)
    if core != t1_probe or core != t4_probe or core != cd_probe:
        fail("PANIC_ENTRY_CORE_IDENTITY_FAILED", "core != T1/T4/C_DELAY")
    if core != t3_probe[4:] or core != t2_probe[4:]:
        fail("PANIC_ENTRY_CORE_IDENTITY_FAILED", "core != T2/T3 slice")
    src_s = PE_DEVICE_S.read_text()
    for bad in ("panic_timeout", "mdelay", "udelay", "loops_per_jiffy",
                "ldr\t", "str\t", "stp\t", "ldp\t", "bl\t"):
        forbid(src_s, bad, "PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_FAILED")
    print("PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_OF_PANIC_TIMEOUT=YES")
    print("PANIC_ENTRY_DIAGNOSTIC_CORE_MATCHES_C_DELAY=YES")
    print("PANIC_ENTRY_DIAGNOSTIC_CORE_MATCHES_T1=YES")
    probe = compose_probe(core, plan)
    plen = len(probe)
    if plen != plan["probe_size"]:
        fail("PANIC_ENTRY_CORE_IDENTITY_FAILED", f"probe {plen}")
    gate_probe_words(probe)
    pad_n = 0 if plen == CORE_SIZE else 1
    print(f"PANIC_ENTRY_PREFIX_WORD={probe[:4].hex()}")
    print(f"PANIC_ENTRY_PROBE_WORD_COUNT={plen // 4}")
    ckbin = out / "p1b-panic-entry-checkpoint.bin"
    ckbin.write_bytes(probe)
    print(f"PANIC_ENTRY_CHECKPOINT sha256={sha(probe)} size={plen}")
    print("PANIC_ENTRY_DEVICE_CANDIDATE_DELAY=8s")
    print("PANIC_ENTRY_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY")
    print("PANIC_ENTRY_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC")
    print("PANIC_ENTRY_FAIL_CLOSED=YES")
    print("PANIC_ENTRY_STACK_USAGE=NO")
    print("PANIC_ENTRY_NO_MEMORY_READS=YES")
    print("PANIC_ENTRY_NO_MEMORY_WRITES=YES")
    print("PANIC_ENTRY_RUNTIME_RELOCATIONS=0")

    covered = list(struct.unpack_from(f"<{plen // 4}I", frozen, off_panic))
    t3.inst_record(out, tools, covered, "p1b-panic-entry-original-covered-insns-record")
    cand = bytearray(frozen)
    cand[off_panic:off_panic + plen] = probe
    cand = bytes(cand)
    region = (off_panic, off_panic + plen)
    diffs = t3.gate_payload_diff(frozen, cand, region)
    tail = t3.gate_tail_identity(frozen, cand, region)
    t3.gate_t2_probe_removed(frozen, cand, off_ps, t2_probe)
    if struct.unpack_from("<I", cand, off_sk)[0] != PACIASP:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "start_kernel entry not FIX8 paciasp")
    if cand[off_c6:off_c6 + CORE_SIZE] != frozen[off_c6:off_c6 + CORE_SIZE]:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "C6/T4 region changed")
    if cand[off_cdelay:off_cdelay + CORE_SIZE] != \
            frozen[off_cdelay:off_cdelay + CORE_SIZE]:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "C_DELAY region changed")
    if cand[off_cdelay:off_cdelay + CORE_SIZE] == core:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "C_DELAY probe still present")
    if off_panic == off_cdelay or off_panic == off_c6 or off_panic == off_sk:
        fail("PANIC_ENTRY_IDENTITY_FAILED", "panic window collides prior probe")
    print("ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=YES")
    print("T4_PROBE_REMOVED_FROM_PANIC_ENTRY=YES")
    print("C_DELAY_PROBE_REMOVED_FROM_PANIC_ENTRY=YES")
    print("T3_PROBE_REMOVED_FROM_PANIC_ENTRY=YES")
    print("T2_PROBE_REMOVED_FROM_PANIC_ENTRY=YES")
    print("PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8=YES")
    t3.gate_tramp_identity(cand)
    trailer = t3.gate_trailer(cand)
    if trailer != frozen_rt_d:
        fail("PANIC_ENTRY_PAYLOAD_DIFF_FAILED", "trailer drifted")
    hdr, dtb_off2, _g2, boot_est = t3.gate_geometry(cand, image_size)
    if dtb_off2 != dtb_offset or boot_est != PE_BOOT_SIZE_EXPECTED:
        fail("PANIC_ENTRY_GEOMETRY_FAILED", f"dtb {dtb_off2:#x} boot {boot_est}")
    payload_path = out / "thyme-r3-p1b-panic-entry-kernel-payload.bin"
    payload_path.write_bytes(cand)
    print(f"PANIC_ENTRY_PAYLOAD sha256={sha(cand)} size={len(cand)} "
          f"diff_bytes={len(diffs)}")
    print(f"PANIC_ENTRY_DIFF_BYTE_COUNT={len(diffs)}")
    print(f"PANIC_ENTRY_DIFF_RANGES=[{off_panic:#x},{off_panic + plen:#x})")
    print("PANIC_ENTRY_PAYLOAD_DIFF_ATTRIBUTED=PANIC_ENTRY_CHECKPOINT_ONLY")
    print("PANIC_ENTRY_RUNTIME_SEMANTIC_DELTA=PANIC_ENTRY_CHECKPOINT_ONLY")
    print(f"PANIC_ENTRY_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES "
          f"({off_panic} bytes before and {tail} bytes after the window)")
    print("PANIC_ENTRY_TRAMPOLINE_IDENTICAL=YES")
    print("PANIC_ENTRY_RT_D_IDENTITY=YES")
    print("PANIC_ENTRY_RT_D_PANIC5=YES")
    print("PANIC_ENTRY_GEOMETRY_GATES=PASS")
    print("PANIC_ENTRY_DIAGNOSTIC_ONLY=YES")
    print("PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE=NO")
    print("PANIC_ENTRY_STATUS=NOT_DEVICE_READY")
    print("READY_FOR_DEVICE=NO")
    print("PANIC_ENTRY_DEVICE_OPERATION=NO")

    (out / "p1b-panic-entry-payload-diff-report.txt").write_text(
        "PANIC_ENTRY_PAYLOAD_DIFF_REPORT\n"
        f"FROZEN_FIX8_PAYLOAD_SHA256={FIX8_PAYLOAD_SHA}\n"
        f"PANIC_ENTRY_PAYLOAD_SHA256={sha(cand)}\n"
        f"DIFF_BYTES={len(diffs)}\n"
        f"PANIC_ENTRY_DIFF_RANGES=[{off_panic:#x},{off_panic + plen:#x})\n"
        "DIFF_ATTRIBUTION=PANIC_ENTRY_CHECKPOINT_ONLY\n"
        "ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=YES\n")

    neg_lines = run_negative_fixtures({
        "ops": ops, "dump": dump, "probe": probe, "pad_n": pad_n,
        "probe_len": plen, "frozen": frozen,
        "cand": cand, "off_ck": off_panic, "off_sk": off_sk, "off_ps": off_ps,
        "off_c6": off_c6, "off_cdelay": off_cdelay, "t1_core": t1_probe,
        "ck_va": panic_va, "image_size": image_size,
    })
    (out / "p1b-panic-entry-negative-fixtures.txt").write_text(
        "\n".join(neg_lines) + "\n")
    dec_lines = run_decoder_fixtures()
    (out / "p1b-panic-entry-decoder-fixtures.txt").write_text(
        "\n".join(dec_lines) + "\n")
    print("PANIC_ENTRY_NEGATIVE_FIXTURES=PASS")
    print("PANIC_ENTRY_DECODER_FIXTURES=PASS")

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_PANIC_ENTRY_PREDEVICE_READINESS_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "panic_entry_true_device_run": "NOT_EXECUTED",
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
        "start_kernel_va": hex(sk_va),
        "start_kernel_image_offset": hex(off_sk),
        "c6_image_offset": hex(off_c6),
        "c_delay_image_offset": hex(off_cdelay),
        "panic_va": hex(panic_va),
        "panic_image_offset": hex(off_panic),
        "panic_file_offset": hex(off_panic),
        "panic_section": sec["name"],
        "panic_section_flags": sec.get("flags"),
        "panic_size": hex(panic_size),
        "panic_noreturn": True,
        "panic_cold": True,
        "panic_canonical_entry_unique": refs["unique"],
        "panic_direct_callsite_count": refs["direct_bl"],
        "panic_direct_branch_count": refs["direct_b"],
        "panic_indirect_reference_count": refs["adrp"] + int(refs["export"]),
        "panic_adrp_page_ref_count": refs["adrp"],
        "panic_alias_count": refs["alias_count"],
        "panic_fragment_count": refs["fragment_count"],
        "panic_clone_entry_count": refs["clone_entry_count"],
        "panic_address_taken_method": refs["method"],
        "panic_entry_branch_types": refs["branch_types"],
        "panic_entry_insn0": insns[0]["mnemonic"],
        "panic_entry_bytes0": insns[0]["bytes"],
        "panic_entry_insn1": insns[1]["mnemonic"],
        "panic_entry_bytes1": insns[1]["bytes"],
        "panic_entry_landing_requirement": plan["requirement"],
        "panic_entry_landing_reason": plan["reason"],
        "panic_entry_landing_requirement_satisfied": True,
        "panic_entry_prefix_preserved": plan["prefix_name"],
        "panic_entry_prefix_word": probe[:4].hex(),
        "panic_entry_entry_word0": hex(word0),
        "panic_entry_selected_stage": "PANIC_ENTRY_CANONICAL_PANIC",
        "panic_entry_probe_architecture": "INLINE",
        "panic_entry_inline_overwrite_safe": True,
        "panic_entry_checkpoint_va": hex(panic_va),
        "panic_entry_checkpoint_image_offset": hex(off_panic),
        "panic_entry_checkpoint_sha256": sha(probe),
        "panic_entry_checkpoint_size": plen,
        "panic_entry_core_sha256": sha(core),
        "panic_entry_diagnostic_core_matches_c_delay": True,
        "panic_entry_diagnostic_independent_of_panic_timeout": True,
        "all_prior_diagnostic_probes_removed": True,
        "panic_entry_baseline_normal_path_identical_to_fix8": True,
        "panic_entry_payload_sha256": sha(cand),
        "panic_entry_payload_size": len(cand),
        "panic_entry_boot_size_est": boot_est,
        "diff_bytes": len(diffs),
        "diff_regions": [[hex(off_panic), hex(off_panic + plen)]],
        "diff_attribution": "PANIC_ENTRY_CHECKPOINT_ONLY",
        "panic_entry_runtime_semantic_delta": "PANIC_ENTRY_CHECKPOINT_ONLY",
        "panic_entry_diagnostic_only": True,
        "panic_entry_normal_kernel_boot_candidate": False,
        "panic_entry_status": "NOT_DEVICE_READY",
        "panic_entry_delay_seconds": PE_DELAY_S,
        "psci_fid": hex(PSCI_SYSTEM_RESET_FID),
        "panic_entry_fail_closed": True,
        "panic_entry_stack_usage": False,
        "panic_entry_memory_reads": False,
        "panic_entry_memory_writes": False,
        "panic_entry_runtime_relocations": 0,
        "decoder": {
            "kind": "DISTINCTIVE_EARLY_NOT_C_DELAY_SYMMETRIC",
            "c_delay_reference_total_s": C_DELAY_REFERENCE_TOTAL_S,
            "strong_early_limit_s": PE_EARLY_LIMIT_S,
            "matched_minus_c_delay_lo_s": PE_MATCHED_LO_S,
            "matched_minus_c_delay_hi_s": PE_MATCHED_HI_S,
            "supported_lo_s": PE_SUPPORTED_LO_S,
            "supported_hi_s": PE_SUPPORTED_HI_S,
            "natural_lo_s": PE_NATURAL_LO_S,
            "natural_hi_s": PE_NATURAL_HI_S,
        },
        "observer": {"identity_env": "R3_PANIC_ENTRY_SHA256",
                     "forbidden_env": "R3_PANIC_ENTRY_FORBIDDEN_SHAS",
                     "misboot_refusal": sorted(FORBIDDEN_BOOT_SHAS)},
    }
    (out / "p1b-panic-entry-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    gates = [
        "PANIC_ENTRY_BUILD_GATES=PASS",
        "PANIC_ENTRY_BASELINE=FROZEN_FIX8",
        "PANIC_SYMBOL_REDERIVED=YES",
        "PANIC_CANONICAL_ENTRY_UNIQUE=" + refs["unique"],
        "PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE",
        "PANIC_ENTRY_INLINE_OVERWRITE_SAFE=YES",
        "PANIC_ENTRY_LANDING_REQUIREMENT_SATISFIED=YES",
        "PANIC_ENTRY_PREFIX_PRESERVED=" + plan["prefix_name"],
        "PANIC_ENTRY_ENTRY_INSTRUMENTATION_AUDITED=YES",
        "PANIC_ENTRY_WINDOW_INSIDE_IMAGE_SIZE=YES",
        "PANIC_ENTRY_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT",
        "PANIC_ENTRY_INLINE_MAPPING_EXECUTABLE=YES",
        "PANIC_ENTRY_EXTERNAL_CHECKPOINT_USED=NO",
        "PANIC_ENTRY_PADDING_MAPPING_USED=NO",
        "PANIC_ENTRY_DEVICE_CANDIDATE_DELAY=8s",
        "PANIC_ENTRY_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY",
        "PANIC_ENTRY_CNTPCT_SAFE=YES",
        "PANIC_ENTRY_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC",
        "PANIC_ENTRY_PSCI_SAFE=YES",
        "PANIC_ENTRY_FAIL_CLOSED=YES",
        "PANIC_ENTRY_STACK_USAGE=NO",
        "PANIC_ENTRY_NO_MEMORY_READS=YES",
        "PANIC_ENTRY_NO_MEMORY_WRITES=YES",
        "PANIC_ENTRY_DIAGNOSTIC_CORE_MATCHES_C_DELAY=YES",
        "PANIC_ENTRY_DIAGNOSTIC_CORE_MATCHES_T1=YES",
        "PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_OF_PANIC_TIMEOUT=YES",
        "PANIC_ENTRY_RUNTIME_RELOCATIONS=0",
        "ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=YES",
        "T4_PROBE_REMOVED_FROM_PANIC_ENTRY=YES",
        "C_DELAY_PROBE_REMOVED_FROM_PANIC_ENTRY=YES",
        "PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8=YES",
        "PANIC_ENTRY_TRAMPOLINE_IDENTICAL=YES",
        "PANIC_ENTRY_RT_D_IDENTITY=YES",
        "PANIC_ENTRY_INIT_IDENTITY=YES",
        "PANIC_ENTRY_INITRAMFS_IDENTITY=YES",
        "PANIC_ENTRY_PAYLOAD_DIFF_ATTRIBUTED=PANIC_ENTRY_CHECKPOINT_ONLY",
        "PANIC_ENTRY_PAYLOAD_SIZE_IDENTICAL=YES",
        "PANIC_ENTRY_BOOT_SIZE_IDENTICAL=YES",
        f"PANIC_ENTRY_DTB_OFFSET={DTB_OFFSET:#x}",
        "PANIC_ENTRY_GEOMETRY_GATES=PASS",
        "PANIC_ENTRY_NEGATIVE_FIXTURES=PASS",
        "PANIC_ENTRY_DECODER_FIXTURES=PASS",
        "PANIC_ENTRY_DIAGNOSTIC_ONLY=YES",
        "PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE=NO",
        "PANIC_ENTRY_STATUS=NOT_DEVICE_READY",
        "READY_FOR_DEVICE=NO",
        "PANIC_ENTRY_RUNTIME_SEMANTIC_DELTA=PANIC_ENTRY_CHECKPOINT_ONLY",
        "C6_REGION_IDENTICAL_TO_FIX8=YES",
        "C_DELAY_REGION_IDENTICAL_TO_FIX8=YES",
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES",
    ]
    (out / "p1b-panic-entry-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))
    (out / "p1b-panic-entry-report.txt").write_text(
        "PANIC_ENTRY_PREDEVICE_REPORT\n" + "\n".join(gates) + "\n")


def cmd_observer_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "pe_obs_fixtures", OBSERVER_FIXTURES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.main() or []
    (out / "p1b-panic-entry-observer-fixtures.txt").write_text(
        "\n".join(lines) + "\n")
    print("PANIC_ENTRY_OBSERVER_FIXTURES=PASS")


def cmd_panic_entry_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    off_ck = int(args.checkpoint_offset, 16)
    probe = Path(args.checkpoint_bin).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("PANIC_ENTRY_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("PANIC_ENTRY_PACK_FAILED", f"payload sha={sha(payload)}")
    if sha(probe) != args.checkpoint_sha:
        fail("PANIC_ENTRY_PACK_FAILED", f"checkpoint sha={sha(probe)}")
    hdr = pb.parse_image_hdr(payload, "panic-entry-payload")
    image_size = hdr["image_size"]
    t3.gate_image_size_rederived(image_size, "panic-entry-packed-payload")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != CODE1_B_0X40:
        fail("PANIC_ENTRY_PACK_FAILED", "code1 not b 0x40")
    dtb_offset, _gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("PANIC_ENTRY_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    if (off_ck + len(probe)) > image_size:
        fail("PANIC_ENTRY_PACK_FAILED", "checkpoint window past image_size")
    tramp = payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(tramp) != TRAMP_SHA:
        fail("PANIC_ENTRY_PACK_FAILED", "embedded trampoline != frozen FIX8")
    if payload[off_ck:off_ck + len(probe)] != probe:
        fail("PANIC_ENTRY_PACK_FAILED", "checkpoint region != built probe")
    off_sk = int(args.start_kernel_offset, 16)
    if struct.unpack_from("<I", payload, off_sk)[0] != PACIASP:
        fail("PANIC_ENTRY_PACK_FAILED", "start_kernel entry not paciasp")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA or trailer[:4] != struct.pack(">I", FDT_MAGIC):
        fail("PANIC_ENTRY_PACK_FAILED", "trailer != frozen RT-D")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "panic-entry-candidate")
    if cand["kernel"] != payload:
        fail("PANIC_ENTRY_PACK_FAILED", "candidate kernel != payload")
    if cand["ramdisk"] != ref["ramdisk"] or cand["cmdline"] != ref["cmdline"]:
        fail("PANIC_ENTRY_PACK_FAILED", "envelope fields differ from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"] or \
            cand["reserved"] != ref["reserved"]:
        fail("PANIC_ENTRY_PACK_FAILED", "os/reserved differ from M5D")
    if boot[:8] != b"ANDROID!" or \
            struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("PANIC_ENTRY_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    if set(diff) - set(range(8, 12)):
        fail("PANIC_ENTRY_PACK_FAILED", f"header diff at {sorted(set(diff)-set(range(8,12)))}")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-panic-entry-pack-gates.txt"
    report.write_text(
        "PANIC_ENTRY_PACK_GATES=PASS\n"
        f"PANIC_ENTRY_BOOT_SIZE={len(boot)}\n"
        f"PANIC_ENTRY_BOOT_SHA256={sha(boot)}\n"
        f"PANIC_ENTRY_PAYLOAD_SHA256={sha(payload)}\n"
        f"PANIC_ENTRY_TRAMP_SHA256={sha(tramp)}\n"
        "PANIC_ENTRY_TRAMP_SOURCE=FROZEN_FIX8_UNMODIFIED\n"
        f"PANIC_ENTRY_CHECKPOINT_SHA256={sha(probe)}\n"
        f"PANIC_ENTRY_KERNEL_SIZE={len(payload)}\n"
        f"PANIC_ENTRY_CHECKPOINT_OFFSET={off_ck:#x}\n"
        f"IMAGE_HEADER_IMAGE_SIZE={image_size:#x}\n"
        "PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE\n"
        "PANIC_ENTRY_INLINE_REGION_IN_KERNEL_TEXT=YES\n"
        f"PANIC_ENTRY_DTB_OFFSET={dtb_offset:#x}\n"
        "PANIC_ENTRY_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "PANIC_ENTRY_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "PANIC_ENTRY_BOOT_CAPACITY=PASS\n"
        "START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [PE_DEVICE_S, PE_DEVICE_LD, T3_DEVICE_S, T3_DEVICE_LD,
                T2_DEVICE_S, T2_DEVICE_LD, T1_DEVICE_S, T1_DEVICE_LD,
                C_DELAY_DEVICE_S, C_DELAY_DEVICE_LD, T4_DEVICE_S, T4_DEVICE_LD,
                OBSERVER, OBSERVER_FIXTURES, Path(__file__), DOC, STATUS_DOC,
                WF, PRIVATE_WF, HERE / "p1b-build.py", HERE / "p1b-trampoline.S",
                HERE / "p1b-trampoline.ld", HERE / "p1b-t3-predevice.py"]
    for path in required:
        if not path.is_file():
            fail("PANIC_ENTRY_SOURCE_GATE_FAILED", f"missing {path}")
    dev = PE_DEVICE_S.read_text()
    for token in ("msr\tdaifset, #0xf", "isb", "mrs\tx9, cntfrq_el0",
                  "mrs\tx11, cntpct_el0", "mrs\tx12, cntpct_el0", "yield",
                  "smc\t#0", "wfe", "P1B_PANIC_ENTRY_DELAY",
                  "#if (P1B_PANIC_ENTRY_DELAY) != 8",
                  "r3_panic_entry_checkpoint"):
        need(dev, token)
    for token in ("panic_timeout", "mdelay", "udelay", "loops_per_jiffy",
                  "paciasp", ".inst\t0xd503233f", "bti", "P1B_DTB_REL",
                  "dtb_rel", "adr\t", "ldr\t", "stp\tx29", "eret", "sctlr",
                  "msr\tttbr", "b\tprimary", "b\t__primary",
                  "b\tstart_kernel", "bl\t"):
        forbid(dev, token)
    obs = OBSERVER.read_text()
    for token in ("R3_PANIC_ENTRY_SHA256", "PANIC_ENTRY_OBSERVER_MISBOOT_REFUSED",
                  "PANIC_ENTRY_MINUS_C_DELAY", "C_DELAY_REFERENCE_TOTAL",
                  "FASTBOOT_BOOT_ONLY", "PANIC_ENTRY_NOT_REACHED_LICENSE=NO",
                  "PANIC_ENTRY_FAILURE_ISOLATION_CI",
                  "PANIC_ENTRY_NORMAL_KERNEL_BOOT_CANDIDATE",
                  "PANIC_ENTRY_DIAGNOSTIC_ONLY", "PANIC_ENTRY_CANONICAL_PANIC",
                  "C_DELAY_BOOT", "NO_LINUX_PANIC=NOT_LICENSED"):
        need(obs, token)
    for token in FORBIDDEN_BOOT_SHAS.values():
        need(obs, token)
    forbid(obs, "R3_C_DELAY_SHA256")
    fix = OBSERVER_FIXTURES.read_text()
    for token in ("PANIC_ENTRY_OBSERVER_MISBOOT_REFUSED",
                  "PANIC_ENTRY_NOT_REACHED", "PANIC_ENTRY_STABLE_FASTBOOT",
                  "PANIC_ENTRY_NO_RETURN", "C_DELAY_BOOT", "T4_BOOT"):
        need(fix, token)
    doc = DOC.read_text()
    for token in ("PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE",
                  "PANIC_ENTRY_INLINE_OVERWRITE_SAFE",
                  "PANIC_ENTRY_LANDING_REQUIREMENT",
                  "PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_OF_PANIC_TIMEOUT=YES",
                  "PANIC_ENTRY_CNTPCT_SAFE", "PANIC_ENTRY_PSCI_SAFE",
                  "PANIC_ENTRY_FAIL_CLOSED", "PANIC_ENTRY_STACK_USAGE=NO",
                  "PANIC_ENTRY_RUNTIME_RELOCATIONS=0",
                  "ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED",
                  "PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8",
                  "PANIC_ENTRY_CHECKPOINT_ONLY",
                  "PANIC_CANONICAL_ENTRY_UNIQUE",
                  "14.464", "20.000", "0x2380000", "0x84000009",
                  "READY_FOR_R3_P1B_PANIC_ENTRY_DEVICE_CONTROL",
                  "R3_P1B_PANIC_ENTRY_PREDEVICE_NOT_READY",
                  "PANIC_ENTRY_SIGNATURE_NOT_OBSERVED",
                  "NO_LINUX_PANIC", "PANIC30_RERUN=FROZEN",
                  "PANIC_ALTERNATIVE_RESET_PATH_MAP"):
        need(doc, token)
    kv = parse_status_kv(STATUS_DOC.read_text())
    for key, want in STATUS_DOC_REQUIRED_KV.items():
        if kv.get(key) != want:
            fail("PANIC_ENTRY_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} != {want!r}")
    for key, allowed in STATUS_DOC_ENUM_KV.items():
        if kv.get(key) not in allowed:
            fail("PANIC_ENTRY_SOURCE_GATE_FAILED",
                 f"status KV {key}={kv.get(key)!r} not in {allowed}")
    print(f"PANIC_ENTRY_STATUS_KV_KEY_COUNT={len(kv)}")
    print("PANIC_ENTRY_STATUS_GATE_STRUCTURED=YES")
    wf_text = WF.read_text()
    for token in ("p1b-panic-entry-device.S", "p1b-panic-entry-predevice.py",
                  "observe-r3-p1b-panic-entry.py", "thyme-r3-p1b-panic-entry",
                  "PANIC_ENTRY_BUILD_GATES=PASS", "observer-fixtures"):
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
            fail("PANIC_ENTRY_SOURCE_GATE_FAILED", f"tracked p1b flashable: {rel}")
    body = re.search(r"\n    manifest = \{(.*?)\n    \}\n",
                     Path(__file__).read_text(), re.S)
    if not body:
        fail("PANIC_ENTRY_SOURCE_GATE_FAILED", "manifest literal not found")
    keys = set(re.findall(r'^\s+"([a-z0-9_]+)":', body.group(1), re.M))
    for key in sorted(set(re.findall(r'm\["([^"]+)"\]',
                                     PRIVATE_WF.read_text()))):
        if key not in keys:
            fail("PANIC_ENTRY_SOURCE_GATE_FAILED",
                 f"private workflow reads unknown manifest key {key!r}")
    print(f"PANIC_ENTRY_MANIFEST_KEY_CONSISTENCY=PASS ({len(keys)} keys)")
    print("PANIC_ENTRY_SOURCE_GATE=PASS")
    print("LOCAL_BUILD=NO GHA_ONLY=YES DEVICE_OPERATION=NO "
          "ADB_DEVICE_OPERATION=NO FASTBOOT_DEVICE_OPERATION=NO "
          "PARTITION_WRITES=0 SLOT_A_WRITTEN=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "panic-entry", "observer-fixtures",
        "panic-entry-pack-gates"), required=True)
    parser.add_argument("--out", default="out-panic-entry")
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
    if args.mode == "panic-entry":
        if not (args.rt_d and args.fix8_payload):
            fail("PANIC_ENTRY_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_panic_entry(args)
        return
    if args.mode == "observer-fixtures":
        cmd_observer_fixtures(args)
        return
    if args.mode == "panic-entry-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.checkpoint_bin
                    and args.checkpoint_sha and args.checkpoint_offset
                    and args.start_kernel_offset)
        if not need_all:
            fail("PANIC_ENTRY_PACK_FAILED",
                 "need --m5d-boot --payload --boot --payload-sha "
                 "--checkpoint-bin --checkpoint-sha --checkpoint-offset "
                 "--start-kernel-offset")
        cmd_panic_entry_pack_gates(args)


if __name__ == "__main__":
    main()
