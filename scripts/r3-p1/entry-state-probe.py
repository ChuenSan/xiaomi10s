#!/usr/bin/env python3
"""R3 P1 entry-state probe: assemble/gate/reconcile/pack. GitHub Actions only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local assemble/pack/binary validation")

PAGE = 4096
BOOT_HEADER_V3_SIZE = 1580
KERNEL_OFFSET = PAGE
KERNEL_SIZE = 35101184
BOOT_SIZE = 35110912
RAMDISK_SIZE = 595
RAMDISK_OFFSET = 35106816
TEXT_OFFSET = 0x80000
IMAGE_SIZE_FIELD = 0x2220000
FLAGS = 0xA
PE_OFFSET = 0
PROBE_BODY = 0x40
PADDING_BYTE = 0x00
MAX_PROBE = 4096
PSCI_SYSTEM_RESET = 0x84000009
ARM64_MAGIC = b"ARM\x64"
BOOT_MAGIC = b"ANDROID!"
M5D_BOOT_SHA256 = "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"
M5D_IMAGE_SHA256 = "5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a"
M5D_RAMDISK_SHA256 = "b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de"
RTD_DTB_SHA256 = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
EVIDENCE_JSON_SHA256 = "0882b617174665ffd7fb01ba2b3155920a79cc5f9d3e27d7d9426cab60f46bff"
LLVM_VERSION = "18.1.3"
LLVM_PKG = "1:18.1.3-1ubuntu1"
RUNNER_IMAGE = "ubuntu-24.04"
EL1_ENCODING = 4
EL2_ENCODING = 8
M_BIT = 0
C_BIT = 2
DELAY_BASE = 4
DELAY_STEP = 4
SENTINEL_INDEX = 8
TOLERANCE_STRONG = 0.75
TOLERANCE_SUPPORTED = 1.5
A8_OBSERVED = 14.148
A24_OBSERVED = 30.141
A8_PROGRAMMED = 8
A24_PROGRAMMED = 24
A8_OVERHEAD = round(A8_OBSERVED - A8_PROGRAMMED, 3)
A24_OVERHEAD = round(A24_OBSERVED - A24_PROGRAMMED, 3)
A_OVERHEAD_REF = round((A8_OVERHEAD + A24_OVERHEAD) / 2, 4)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PROBE_SRC = HERE / "p1-entry-state-probe.S"
PROBE_LD = HERE / "p1-entry-state-probe.ld"
NEG_MUTANTS = {
    "p1-esp-neg-store.S": "ESP_NEG_UNKNOWN_MEMORY_STORE",
    "p1-esp-neg-stack.S": "ESP_NEG_STACK_USE",
    "p1-esp-neg-sctlr-el2.S": "ESP_NEG_EL1_READS_SCTLR_EL2",
    "p1-esp-neg-fid.S": "ESP_NEG_UNKNOWN_PSCI_FID",
}
NEG_ABSOLUTE = HERE / "p1-esp-neg-absolute.S"
DOC = REPO / "docs" / "route-r3-entry-state-probe-ci.md"
PUBLIC_WF = REPO / ".github" / "workflows" / "thyme-r3-entry-state-probe.yml"

STORE_RE = re.compile(
    r"\b(str|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|stadd)\b", re.I
)
LOAD_RE = re.compile(
    r"\b(ldr|ldrb|ldrh|ldp|ldur|ldar|ldxr|ldtr|ldnp)\b", re.I
)
BAD_RE = re.compile(
    r"\b(sp|adrp|adr|msr|eret|hvc|svc|brk|udf|bl|blr|ret|cntvct|got)\b", re.I
)
ALLOW_MNEM = {
    "b", "b.eq", "b.ne", "b.hs", "b.lo", "b.lt", "b.ge", "b.gt", "b.le",
    "b.cs", "b.cc",
    "cmp", "mrs", "mov", "movz", "movk", "add", "sub", "mul",
    "tbz", "tbnz", "isb", "yield", "wfe", "wfi", "nop", "smc",
    "orr", "eor", "and", "bic", "csel", "hint",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    msg = label if not detail else f"{label}: {detail}"
    raise SystemExit(msg)


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        fail("ESP_ASSEMBLE_FAILED", f"{' '.join(cmd)}\n{proc.stderr}")
    return proc.stdout


def sx(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def b_target(word: int, pc: int) -> int:
    if word & 0xFC000000 != 0x14000000:
        fail("ESP_CODE0_TARGET_FAILED", f"not B: 0x{word:08x}")
    return pc + sx(word & 0x03FFFFFF, 26) * 4


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def parse_image(image: bytes, label: str) -> dict:
    if len(image) < 64:
        fail("ESP_IMAGE_HEADER_FAILED", f"{label} short")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<QQQQQQ", image, 8)
    magic = image[56:60]
    pe = struct.unpack_from("<I", image, 60)[0]
    if magic != ARM64_MAGIC:
        fail("ESP_IMAGE_HEADER_FAILED", f"{label} magic={magic!r}")
    return {
        "code0": code0, "code1": code1, "text_offset": text_offset,
        "image_size": image_size, "flags": flags, "res2": res2,
        "res3": res3, "res4": res4, "magic": magic, "pe_offset": pe,
    }


def parse_boot(boot: bytes, label: str) -> dict:
    if len(boot) < PAGE or boot[:8] != BOOT_MAGIC:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} not ANDROID!")
    kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from("<IIII", boot, 8)
    reserved = struct.unpack_from("<IIII", boot, 24)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    cmdline = boot[44:BOOT_HEADER_V3_SIZE]
    if header_version != 3:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} header_version={header_version}")
    if header_size != BOOT_HEADER_V3_SIZE:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} header_size={header_size}")
    kernel_end = KERNEL_OFFSET + kernel_size
    ramdisk_off = align(kernel_end, PAGE)
    ramdisk_end = ramdisk_off + ramdisk_size
    if ramdisk_end > len(boot):
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} truncated")
    if boot[BOOT_HEADER_V3_SIZE:PAGE] != b"\x00" * (PAGE - BOOT_HEADER_V3_SIZE):
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} header pad")
    return {
        "kernel_size": kernel_size, "ramdisk_size": ramdisk_size,
        "os_version_raw": os_version_raw, "header_size": header_size,
        "reserved": reserved, "header_version": header_version,
        "cmdline": cmdline, "kernel": boot[KERNEL_OFFSET:kernel_end],
        "ramdisk": boot[ramdisk_off:ramdisk_end], "ramdisk_off": ramdisk_off,
        "total": len(boot),
    }


def require_boot_geometry(parsed: dict, label: str) -> None:
    if parsed["kernel_size"] != KERNEL_SIZE:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} kernel_size={parsed['kernel_size']}")
    if parsed["ramdisk_size"] != RAMDISK_SIZE:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} ramdisk_size")
    if parsed["total"] != BOOT_SIZE:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} total={parsed['total']}")
    if parsed["ramdisk_off"] != RAMDISK_OFFSET:
        fail("ESP_BOOT_LAYOUT_FAILED", f"{label} ramdisk_off")


def require_code0_inside(image: bytes) -> int:
    hdr = parse_image(image, "code0")
    tgt = b_target(hdr["code0"], 0)
    if tgt < 0 or tgt >= KERNEL_SIZE:
        fail("ESP_CODE0_TARGET_FAILED", f"outside payload {tgt:#x}")
    return tgt


def state_index(el: int, m: int, c: int) -> int:
    if el == 1:
        return 2 * m + c
    if el == 2:
        return 4 + 2 * m + c
    return SENTINEL_INDEX


def index_delay(idx: int) -> int:
    return DELAY_STEP * idx + DELAY_BASE


def expected_mapping() -> list[tuple[str, int]]:
    rows = []
    for el in (1, 2):
        for m in (0, 1):
            for c in (0, 1):
                rows.append((f"EL{el} M{m} C{c}", index_delay(state_index(el, m, c))))
    rows.append(("unexpected", index_delay(state_index(0, 0, 0))))
    return rows


def require_unique_delays(delays: list[int]) -> None:
    if len(delays) != len(set(delays)):
        fail("ESP_DECODER_FIXTURE_FAILED", f"duplicate delay bucket {sorted(delays)}")


def tolerance_windows(delays: list[int], tol: float) -> list[tuple[float, float]]:
    return [(d - tol, d + tol) for d in delays]


def require_no_overlap(windows: list[tuple[float, float]]) -> None:
    ordered = sorted(windows)
    for (lo_a, hi_a), (lo_b, hi_b) in zip(ordered, ordered[1:]):
        if hi_a >= lo_b:
            fail("ESP_DECODER_FIXTURE_FAILED",
                 f"bucket windows overlap [{lo_a},{hi_a}] [{lo_b},{hi_b}]")


def decode_observed(delta_s: float) -> tuple[int, str]:
    programmed = delta_s - A_OVERHEAD_REF
    for label, delay in expected_mapping():
        err = abs(programmed - delay)
        if err <= TOLERANCE_STRONG:
            return delay, "STRONG"
        if err <= TOLERANCE_SUPPORTED:
            return delay, "SUPPORTED"
    fail("ESP_DECODER_INCONCLUSIVE", f"delta {delta_s} matches no bucket")


def expect_reject(fn, label: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        text = str(exc)
        if label in text or text.startswith("ESP_"):
            print(f"NEG_{label}=REJECT")
            return
        fail("ESP_NEGATIVE_TEST_FAILED", f"{label} wrong fail {text}")
    fail("ESP_NEGATIVE_TEST_FAILED", f"{label} accepted")


def require_llvm(path: str, needle: str) -> str:
    out = run([path, "--version"])
    if needle not in out.splitlines()[0] and needle not in out:
        fail("ESP_TOOLCHAIN_PIN_FAILED", f"{path}: {out.splitlines()[0] if out else 'empty'}")
    return out.splitlines()[0]


def assemble(clang: str, lld: str, objcopy: str, src: Path,
             out_elf: Path, out_bin: Path) -> None:
    obj = out_elf.with_suffix(".o")
    run([
        clang, "--target=aarch64-unknown-none", "-nostdlib", "-ffreestanding",
        "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fno-ident",
        "-c", "-o", str(obj), str(src),
    ])
    run([
        lld, "-T", str(PROBE_LD), "--build-id=none", "--nmagic",
        "--static", "-o", str(out_elf), str(obj),
    ])
    run([objcopy, "-O", "binary", str(out_elf), str(out_bin)])


def relocs(readelf: str, obj: Path) -> str:
    out = run([readelf, "-r", "--wide", str(obj)])
    if "R_AARCH64_" in out or "Relocation section" in out:
        fail("ESP_RELOCATION_FAILED", out)
    return out


def symbols(readelf: str, elf: Path) -> None:
    out = run([readelf, "-s", "--wide", str(elf)])
    for line in out.splitlines():
        if re.search(r"\sUND\s+\S+$", line):
            fail("ESP_ELF_SYMBOL_FAILED", line)


def sections(objdump: str, elf: Path) -> None:
    out = run([objdump, "-h", str(elf)])
    for bad in (".data", ".bss", ".got", ".rodata"):
        if re.search(rf"\b{re.escape(bad)}\b", out):
            fail("ESP_ELF_SECTION_FAILED", bad)


def disasm(objdump: str, elf: Path) -> str:
    return run([objdump, "-d", "--no-show-raw-insn", str(elf)])


INS_RE = re.compile(r"\s*([0-9a-f]+):\s+(\S+)\s*(.*)$")


def parse_ins(dump: str, min_addr: int) -> list[tuple[int, str, str]]:
    body = []
    for line in dump.splitlines():
        m = INS_RE.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        if addr < min_addr:
            continue
        body.append((addr, m.group(2).lower(), m.group(3).split("//")[0].strip()))
    return body


# Ordered (mnemonic, operand-regex) expectation of the whole probe body in
# address order. Operand regexes accept both hex and decimal objdump prints.
SEQUENCE = [
    ("isb", r"(sy|#0x?f)?$"),
    ("mrs", r"x1, CurrentEL$"),
    ("cmp", r"x1, #0x?8$"),
    ("b.eq", r"0x?(?P<t_el2>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("cmp", r"x1, #0x?4$"),
    ("b.eq", r"0x?(?P<t_el1>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("b", r"0x?(?P<t_unexp>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x5, #0x?0$"),
    ("mrs", r"x2, sctlr_el1$"),
    ("b", r"0x?(?P<t_dec1>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x5, #0x?4$"),
    ("mrs", r"x2, sctlr_el2$"),
    ("b", r"0x?(?P<t_dec2>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x5, #0x?8$"),
    ("b", r"0x?(?P<t_enc>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x6, #0x?0$"),
    ("tbz", r"x2, #0x?0, 0x?(?P<l1>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x6, #0x?2$"),
    ("tbz", r"x2, #0x?2, 0x?(?P<l2>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("add", r"x6, x6, #0x?1$"),
    ("add", r"x5, x5, x6$"),
    ("add", r"x5, x5, x5$"),
    ("add", r"x5, x5, x5$"),
    ("add", r"x5, x5, #0x?4$"),
    ("mrs", r"x6, cntfrq_el0$"),
    ("mul", r"x5, x6, x5$"),
    ("isb", r"(sy|#0x?f)?$"),
    ("mrs", r"x7, cntpct_el0$"),
    ("isb", r"(sy|#0x?f)?$"),
    ("mrs", r"x8, cntpct_el0$"),
    ("sub", r"x9, x8, x7$"),
    ("cmp", r"x9, x5$"),
    ("b.hs", r"0x?(?P<t_done>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("yield", r"$^"),
    ("b", r"0x?(?P<t_loop>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"w0, #0x?(?P<fid_lo>[0-9a-f]+)$"),
    ("movk", r"w0, #0x?8400, lsl #0x?16$"),
    ("mov", r"x1, (xzr|#0x?0)$"),
    ("mov", r"x2, (xzr|#0x?0)$"),
    ("mov", r"x3, (xzr|#0x?0)$"),
    ("smc", r"#0x?0$"),
    ("wfe", r"$^"),
    ("b", r"0x?(?P<t_spin>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
]

# SEQUENCE element indices the captured branch targets must land on.
TARGET_BY_INDEX = {
    "t_el2": 10,   # el2_state: movz x5, #4
    "t_el1": 7,    # el1_state: movz x5, #0
    "t_unexp": 13,  # unexpected_el: movz x5, #8
    "t_dec1": 15,  # decode_state: movz x6, #0
    "t_dec2": 15,
    "t_enc": 21,   # encode_delay: add x5, x5, x5
    "l1": 18,      # tbz x2, #2 (C bit test)
    "l2": 20,      # add x5, x5, x6 (index merge)
    "t_done": 35,  # movz w0, #0x9 (PSCI fid low)
    "t_loop": 28,  # loop-head isb
    "t_spin": 41,  # wfe
}
IDX_SCTLR_EL1 = 8
IDX_SCTLR_EL2 = 11


def line_txt(addr: int, mnem: str, ops: str) -> str:
    return f"{addr:#x}: {mnem} {ops}"


def check_probe_sequence(dump: str) -> dict[str, int]:
    body = parse_ins(dump, PROBE_BODY)
    groups: dict[str, int] = {}
    addr_by_idx: dict[int, int] = {}
    i = 0
    for idx, (mnem_re, ops_re) in enumerate(SEQUENCE):
        if i >= len(body):
            fail("ESP_DISASM_FAILED", f"sequence truncated at element {idx}")
        addr, mnem, ops = body[i]
        if not re.fullmatch(mnem_re, mnem):
            fail("ESP_DISASM_FAILED",
                 f"element {idx}: expected {mnem_re!r}, got {line_txt(addr, mnem, ops)}")
        m = re.fullmatch(ops_re, ops, re.I)
        if not m:
            fail("ESP_DISASM_FAILED",
                 f"element {idx}: ops {ops!r} !~ {ops_re!r}")
        for key, val in (m.groupdict() if m else {}).items():
            if val is not None:
                groups[key] = int(val, 16)
        addr_by_idx[idx] = addr
        i += 1
    if i != len(body):
        addr, mnem, ops = body[i]
        fail("ESP_DISASM_FAILED", f"unexpected tail {line_txt(addr, mnem, ops)}")
    for key, idx in TARGET_BY_INDEX.items():
        if groups.get(key) != addr_by_idx[idx]:
            fail("ESP_DISASM_FAILED",
                 f"{key}={groups.get(key, -1):#x} does not target element {idx} "
                 f"at {addr_by_idx[idx]:#x}")
    if addr_by_idx[IDX_SCTLR_EL1] != addr_by_idx[TARGET_BY_INDEX["t_el1"]] + 4:
        fail("ESP_DISASM_FAILED", "sctlr_el1 read not second instruction of EL1 block")
    if addr_by_idx[IDX_SCTLR_EL2] != addr_by_idx[TARGET_BY_INDEX["t_el2"]] + 4:
        fail("ESP_DISASM_FAILED", "sctlr_el2 read not second instruction of EL2 block")
    if groups.get("fid_lo") != 0x9:
        fail("ESP_DISASM_FAILED", f"PSCI function id low {groups.get('fid_lo'):#x}")
    return groups


def global_rejects(dump: str) -> None:
    body = parse_ins(dump, PROBE_BODY)
    if not body:
        fail("ESP_DISASM_FAILED", "empty body")
    for addr, mnem, ops in body:
        text = f"{mnem} {ops}"
        if STORE_RE.search(text):
            fail("ESP_STORE_REJECT_FAILED", line_txt(addr, mnem, ops))
        if LOAD_RE.search(text):
            fail("ESP_DISASM_FAILED", f"memory load {line_txt(addr, mnem, ops)}")
        if BAD_RE.search(text):
            fail("ESP_DISASM_FAILED", f"forbidden {line_txt(addr, mnem, ops)}")
        if mnem not in ALLOW_MNEM:
            fail("ESP_DISASM_FAILED", f"unexpected mnemonic {line_txt(addr, mnem, ops)}")


def check_header_fields(raw: bytes) -> dict:
    hdr = parse_image(raw, "probe")
    if hdr["text_offset"] != TEXT_OFFSET or hdr["image_size"] != IMAGE_SIZE_FIELD:
        fail("ESP_IMAGE_HEADER_FAILED", "text_offset/image_size")
    if hdr["flags"] != FLAGS or hdr["pe_offset"] != PE_OFFSET:
        fail("ESP_IMAGE_HEADER_FAILED", "flags/pe")
    if hdr["res2"] or hdr["res3"] or hdr["res4"]:
        fail("ESP_IMAGE_HEADER_FAILED", "reserved")
    t0 = b_target(hdr["code0"], 0)
    t1 = b_target(hdr["code1"], 4)
    if t0 != PROBE_BODY or t1 != PROBE_BODY:
        fail("ESP_CODE0_TARGET_FAILED", f"{t0:#x} {t1:#x}")
    if t0 >= KERNEL_SIZE:
        fail("ESP_CODE0_TARGET_FAILED", "outside payload")
    return hdr


def pad_kernel(raw: bytes) -> bytes:
    if len(raw) > KERNEL_SIZE or len(raw) > MAX_PROBE:
        fail("ESP_SIZE_FAILED", f"probe {len(raw)}")
    if len(raw) < PROBE_BODY + 4:
        fail("ESP_SIZE_FAILED", f"probe {len(raw)}")
    return raw + bytes([PADDING_BYTE]) * (KERNEL_SIZE - len(raw))


def splice(m5d: bytes, kernel: bytes) -> bytes:
    if len(m5d) != BOOT_SIZE:
        fail("ESP_M5D_IDENTITY_FAILED", f"size {len(m5d)}")
    if len(kernel) != KERNEL_SIZE:
        fail("ESP_SIZE_FAILED", f"kernel {len(kernel)}")
    out = bytearray(m5d)
    out[KERNEL_OFFSET:KERNEL_OFFSET + KERNEL_SIZE] = kernel
    return bytes(out)


def diff_offsets(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        fail("ESP_DELTA_FAILED", f"len {len(a)} vs {len(b)}")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def load_r3_module():
    path = HERE / "r3-runtime-dtb.py"
    spec = importlib.util.spec_from_file_location("r3_runtime_dtb_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def json_memory_banks(evidence_path: Path) -> list[list[int]]:
    data = json.loads(evidence_path.read_text())
    banks = [
        [int(b["base"]), int(b["size"])]
        for b in data["memory"]["banks"]
        if b.get("base") is not None and b.get("size") is not None
    ]
    return sorted(banks)


def dts_memory_banks(dts_path: Path) -> list[list[int]]:
    text = dts_path.read_text()
    node = re.search(r"memory@[0-9a-f]+\s*\{(.*?)\};", text, re.S)
    if not node:
        fail("ESP_RAM_RECONCILIATION_FAILED", "no /memory node in DTS")
    reg = re.search(r"reg\s*=\s*(.*?);", node.group(1), re.S)
    if not reg:
        fail("ESP_RAM_RECONCILIATION_FAILED", "no reg in /memory node")
    cells = []
    for group in re.findall(r"<([0-9a-fx\s]+)>", reg.group(1)):
        cells.extend(int(tok, 16) for tok in group.split())
    if len(cells) != 12:
        fail("ESP_RAM_RECONCILIATION_FAILED", f"/memory cells {len(cells)} != 12")
    banks = []
    for k in range(0, 12, 4):
        banks.append([(cells[k] << 32) | cells[k + 1],
                      (cells[k + 2] << 32) | cells[k + 3]])
    return sorted(banks)


def dtb_memory_banks(dtb_path: Path) -> list[list[int]]:
    mod = load_r3_module()
    nodes = mod.parse_fdt(dtb_path.read_bytes())
    return sorted([int(b[0]), int(b[1])] for b in mod.decode_memory(nodes))


def fmt_bank(bank: list[int]) -> str:
    base, size = bank
    return f"base=0x{base:x} size=0x{size:x} end_excl=0x{base + size:x}"


def mode_bit_position_pin(args: argparse.Namespace) -> None:
    linux = Path(args.linux)
    sysreg = linux / "arch/arm64/include/asm/sysreg.h"
    ptrace = linux / "arch/arm64/include/asm/ptrace.h"
    for path in (sysreg, ptrace):
        if not path.is_file():
            fail("ESP_BIT_POSITION_PIN_FAILED", f"missing {path}")
    sysreg_text = sysreg.read_text()
    ptrace_text = ptrace.read_text()
    m_bit = re.search(r"#define\s+SCTLR_ELx_M\s+\(BIT\((\d+)\)\)", sysreg_text)
    c_bit = re.search(r"#define\s+SCTLR_ELx_C\s+\(BIT\((\d+)\)\)", sysreg_text)
    i_bit = re.search(r"#define\s+SCTLR_ELx_I\s+\(BIT\((\d+)\)\)", sysreg_text)
    el1 = re.search(r"#define\s+CurrentEL_EL1\s+\((\d+)\s*<<\s*2\)", ptrace_text)
    el2 = re.search(r"#define\s+CurrentEL_EL2\s+\((\d+)\s*<<\s*2\)", ptrace_text)
    for name, match in (("SCTLR_ELx_M", m_bit), ("SCTLR_ELx_C", c_bit),
                        ("SCTLR_ELx_I", i_bit), ("CurrentEL_EL1", el1),
                        ("CurrentEL_EL2", el2)):
        if not match:
            fail("ESP_BIT_POSITION_PIN_FAILED", f"{name} define not found")
    got = {
        "M_BIT": int(m_bit.group(1)),
        "C_BIT": int(c_bit.group(1)),
        "I_BIT": int(i_bit.group(1)),
        "EL1_ENCODING": int(el1.group(1)) << 2,
        "EL2_ENCODING": int(el2.group(1)) << 2,
    }
    want = {
        "M_BIT": M_BIT, "C_BIT": C_BIT,
        "EL1_ENCODING": EL1_ENCODING, "EL2_ENCODING": EL2_ENCODING,
    }
    for key, value in want.items():
        if got[key] != value:
            fail("ESP_BIT_POSITION_PIN_FAILED",
                 f"{key}: linux says {got[key]}, probe uses {value}")
    print(f"ESP_BIT_POSITION_LINUX_I_BIT={got['I_BIT']}")
    print("ESP_BIT_POSITION_PIN=PASS")


def mode_ram_reconciliation(args: argparse.Namespace) -> None:
    evidence_path = Path(args.evidence)
    dts_path = Path(args.dts)
    dtb_path = Path(args.dtb)
    if sha(evidence_path.read_bytes()) != EVIDENCE_JSON_SHA256:
        fail("ESP_RAM_RECONCILIATION_FAILED", "evidence JSON sha drift")
    if sha(dtb_path.read_bytes()) != RTD_DTB_SHA256:
        fail("ESP_RAM_RECONCILIATION_FAILED", f"RT-D DTB sha != pinned {RTD_DTB_SHA256}")
    j = json_memory_banks(evidence_path)
    d = dts_memory_banks(dts_path)
    b = dtb_memory_banks(dtb_path)
    for name, banks in (("JSON", j), ("DTS", d), ("DTB", b)):
        if len(banks) != 3:
            fail("ESP_RAM_RECONCILIATION_FAILED", f"{name} banks {len(banks)} != 3")
    if j != d or d != b:
        fail("ESP_RAM_RECONCILIATION_FAILED", f"JSON={j} DTS={d} DTB={b}")
    print(f"RAM_RECONCILIATION_JSON_BANKS={len(j)}")
    print(f"RAM_RECONCILIATION_DTS_BANKS={len(d)}")
    print(f"RAM_RECONCILIATION_DTB_BANKS={len(b)}")
    for i, bank in enumerate(j):
        print(f"RAM_RECONCILIATION_BANK{i}_HEX={fmt_bank(bank)}")
    print("RAM_RECONCILIATION_JSON_DTS_DTB_EQUAL=YES")
    print(f"RT_D_DTB_SHA256={RTD_DTB_SHA256}")
    print("RT_D_DTB_SHA256_MATCH=YES")
    print("RAM_BANK_SEMANTIC_ERROR=NO")


def mode_decoder_fixtures() -> None:
    rows = expected_mapping()
    delays = [d for _, d in rows]
    if len(rows) != 9:
        fail("ESP_DECODER_FIXTURE_FAILED", f"rows {len(rows)}")
    require_unique_delays(delays)
    if delays != [4, 8, 12, 16, 20, 24, 28, 32, 36]:
        fail("ESP_DECODER_FIXTURE_FAILED", f"delays {delays}")
    reverse: dict[int, str] = {}
    for label, delay in rows:
        if delay in reverse:
            fail("ESP_DECODER_FIXTURE_FAILED", f"reverse collision {delay}")
        reverse[delay] = label
    for a, b in zip(delays, delays[1:]):
        if b - a != DELAY_STEP:
            fail("ESP_DECODER_FIXTURE_FAILED", f"gap {a}->{b}")
    require_no_overlap(tolerance_windows(delays, TOLERANCE_STRONG))
    require_no_overlap(tolerance_windows(delays, TOLERANCE_SUPPORTED))
    if state_index(1, 0, 0) != 0 or state_index(2, 1, 1) != 7:
        fail("ESP_DECODER_FIXTURE_FAILED", "index composition")
    if state_index(0, 0, 0) != SENTINEL_INDEX or state_index(3, 1, 1) != SENTINEL_INDEX:
        fail("ESP_DECODER_FIXTURE_FAILED", "sentinel not uniform")
    if abs(A8_OVERHEAD - 6.148) > 1e-9 or abs(A24_OVERHEAD - 6.141) > 1e-9:
        fail("ESP_DECODER_FIXTURE_FAILED", f"overhead {A8_OVERHEAD} {A24_OVERHEAD}")
    if abs(A_OVERHEAD_REF - 6.1445) > 1e-9:
        fail("ESP_DECODER_FIXTURE_FAILED", f"reference overhead {A_OVERHEAD_REF}")
    for observed, programmed in ((A8_OBSERVED, A8_PROGRAMMED),
                                 (A24_OBSERVED, A24_PROGRAMMED)):
        delay, tier = decode_observed(observed)
        if delay != programmed or tier != "STRONG":
            fail("ESP_DECODER_FIXTURE_FAILED",
                 f"observed {observed} -> {delay}/{tier}, want {programmed}/STRONG")

    def dup_fixture():
        require_unique_delays([4, 4, 12, 16, 20, 24, 28, 32, 36])

    def overlap_fixture():
        require_no_overlap(
            tolerance_windows([4, 8, 12, 16, 20, 24, 28, 32, 36], 2.5))

    def count_fixture():
        delays_short = [4, 8, 12, 16, 20, 24, 28, 32]
        if len(delays_short) != 9:
            fail("ESP_BUCKET_COUNT", f"rows {len(delays_short)} != 9")

    def fid_fixture():
        fid = 0x8400000f
        if fid != PSCI_SYSTEM_RESET:
            fail("ESP_UNKNOWN_PSCI_FID", f"fid {fid:#x} is not SYSTEM_RESET")

    expect_reject(dup_fixture, "ESP_DUPLICATE_DELAY_BUCKET")
    expect_reject(overlap_fixture, "ESP_BUCKET_WINDOW_OVERLAP")
    expect_reject(count_fixture, "ESP_BUCKET_COUNT")
    expect_reject(fid_fixture, "ESP_UNKNOWN_PSCI_FID")
    print("ESP_DECODER_FIXTURES=PASS")


def source_gate_tokens() -> None:
    for path in (PROBE_SRC, PROBE_LD, NEG_ABSOLUTE, DOC, PUBLIC_WF,
                 *(HERE / name for name in NEG_MUTANTS)):
        if not path.is_file() or path.stat().st_size == 0:
            fail("ESP_SOURCE_GATE_FAILED", f"missing {path}")
    src = PROBE_SRC.read_text()
    for token in (
        "CurrentEL", "sctlr_el1", "sctlr_el2", "cntfrq_el0", "cntpct_el0",
        "smc", "0x80000", "0x2220000", "0x644d5241", "movz\tx5, #8",
        "movz\tw0, #0x0009", "movk\tw0, #0x8400, lsl #16",
    ):
        if token not in src:
            fail("ESP_SOURCE_GATE_FAILED", f"probe missing {token}")
    for pattern in (
        r"\bstr\b", r"\bstp\b", r"\bldr\b", r"\bldp\b", r"\badrp\b",
        r"\bmsr\b", r"\beret\b", r"\bhvc\b", r"\bsvc\b", r"\bbl\b",
        r"\bblr\b", r"\bret\b", r"\bsp\b", r"\bcntvct\b", r"\bcntv_off\b",
        r"\.data\b", r"\.bss\b", r"\.got\b",
    ):
        if re.search(pattern, src, re.I):
            fail("ESP_SOURCE_GATE_FAILED", f"probe source has {pattern}")
    script = Path(__file__).read_text()
    for token in (
        "GITHUB_ACTIONS", "0x84000009", RTD_DTB_SHA256, EVIDENCE_JSON_SHA256,
        M5D_BOOT_SHA256, M5D_IMAGE_SHA256, M5D_RAMDISK_SHA256,
        "thyme-r3-entry-state-probe.img", "TOLERANCE_STRONG", "A_OVERHEAD_REF",
        "SENTINEL_INDEX",
    ):
        if token not in script:
            fail("ESP_SOURCE_GATE_FAILED", f"script missing {token}")
    doc_text = DOC.read_text()
    for token in (
        "FINAL_GATE_PREVIOUS=R3_RUNTIME_DTB_COMPLETED",
        RTD_DTB_SHA256,
        "RAM_BANK_REPORT_NOTATION_ERROR=YES",
        "RAM_BANK_SEMANTIC_ERROR=NO",
        "0x0_C0000000",
        M5D_BOOT_SHA256,
        "THYME_PSCI_CONDUIT=SMC",
        "P0_TIMER_SOURCE=CNTPCT",
        "P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET",
        "SHIM_ENTRY_PROVEN=YES",
        "E5 USB: FROZEN",
        "M5N FROZEN",
        "P1_CLEAN_IMAGE_REBUILD_PENDING=YES",
        "ICACHE_RUNTIME_PROBE_REQUIRED=NO",
        "SECONDARY_ENTRY_STATE_UNKNOWN",
        "TIMING_TOLERANCE_STRONG=0.75",
        "TIMING_TOLERANCE_SUPPORTED=1.5",
        "A8 overhead: 6.148s",
        "A24 overhead: 6.141s",
        "READY_FOR_R3_ENTRY_STATE_PROBE_DEVICE_CONTROL",
        "R3_ENTRY_STATE_PROBE_CI_NOT_READY",
        "R3_ENTRY_STATE_PROBE_BLOCKED_BY_RAM_ERROR",
        "LOCAL_BUILD:                       NO",
        "LOCAL_BINARY_VALIDATION:           NO",
        "DEVICE_OPERATION:                  NO",
        "PARTITION_WRITES:                  0",
        "Slot A written:                    NO",
        "AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B",
        "EL1 M0 C0 -> 4s",
        "EL1 M0 C1 -> 8s",
        "EL1 M1 C0 -> 12s",
        "EL1 M1 C1 -> 16s",
        "EL2 M0 C0 -> 20s",
        "EL2 M0 C1 -> 24s",
        "EL2 M1 C0 -> 28s",
        "EL2 M1 C1 -> 32s",
        "unexpected -> 36s",
    ):
        if token not in doc_text:
            fail("ESP_SOURCE_GATE_FAILED", f"doc missing {token!r}")
    if "0x1_C0000000" in doc_text:
        fail("ESP_SOURCE_GATE_FAILED", "doc still has mis-notated bank base")
    wf_text = PUBLIC_WF.read_text()
    if "Does not splice M5D and does not emit a boot image" not in wf_text:
        fail("ESP_SOURCE_GATE_FAILED", "public workflow boundary missing")
    if re.search(r"^\s+run:.*\b(fastboot|adb|flash)\b", wf_text, re.M):
        fail("ESP_SOURCE_GATE_FAILED", "public workflow has device verbs")
    print("ESP_SOURCE_GATE=PASS")
    print("RAM_BANK_REPORT_NOTATION_ERROR=YES")
    print("RAM_BANK_SEMANTIC_ERROR=NO")


def build_gates(args: argparse.Namespace) -> tuple[dict, bytes]:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    clang, lld = args.clang, args.lld
    objcopy, objdump, readelf = args.objcopy, args.objdump, args.readelf
    for path, needle in ((clang, LLVM_VERSION), (lld, LLVM_VERSION),
                         (objdump, LLVM_VERSION)):
        require_llvm(path, needle)
    print(f"TOOLCHAIN_LLVM_VERSION={LLVM_VERSION}")
    print(f"TOOLCHAIN_PKG={LLVM_PKG}")
    print(f"TOOLCHAIN_RUNNER={RUNNER_IMAGE}")

    elf = out / "p1-entry-state-probe.elf"
    bin_path = out / "p1-entry-state-probe.bin"
    assemble(clang, lld, objcopy, PROBE_SRC, elf, bin_path)
    relocs(readelf, elf.with_suffix(".o"))
    symbols(readelf, elf)
    sections(objdump, elf)
    raw = bin_path.read_bytes()
    check_header_fields(raw)
    dump = disasm(objdump, elf)
    (out / "p1-entry-state-probe-disasm.txt").write_text(dump, encoding="utf-8")
    check_probe_sequence(dump)
    global_rejects(dump)
    print("ESP_DISASM_GATES=PASS")
    print("ESP_EL_SAFE_SCTLR_ACCESS=PASS")
    print("ESP_NO_MEMORY_ACCESS=PASS")
    print("ESP_NO_STACK=PASS")
    print("ESP_RELOCATIONS=0")

    for name, label in NEG_MUTANTS.items():
        stem = name[:-2]
        m_elf = out / f"{stem}.elf"
        m_bin = out / f"{stem}.bin"
        assemble(clang, lld, objcopy, HERE / name, m_elf, m_bin)
        m_dump = disasm(objdump, m_elf)
        (out / f"{stem}-disasm.txt").write_text(m_dump, encoding="utf-8")
        expect_reject(lambda d=m_dump: check_probe_sequence(d), label)
        if label in ("ESP_NEG_UNKNOWN_MEMORY_STORE", "ESP_NEG_STACK_USE"):
            expect_reject(lambda d=m_dump: global_rejects(d), label)
    abs_obj = out / "p1-esp-neg-absolute.o"
    run([clang, "--target=aarch64-unknown-none", "-nostdlib", "-ffreestanding",
         "-c", "-o", str(abs_obj), str(NEG_ABSOLUTE)])
    expect_reject(lambda: relocs(readelf, abs_obj), "ESP_NEG_ABSOLUTE_ADDRESS")
    print("ESP_NEG_ABSOLUTE_ADDRESS=REJECT")

    kernel = pad_kernel(raw)
    return {"probe_sha": sha(raw), "kernel_sha": sha(kernel), "raw_len": len(raw)}, kernel


def mode_assemble_gates(args: argparse.Namespace) -> None:
    probe_report, _ = build_gates(args)
    out = Path(args.out).resolve()
    pad_len = KERNEL_SIZE - probe_report["raw_len"]
    lines = [
        "R3_ENTRY_STATE_PROBE_ASSEMBLE_GATES",
        "P1_STATE_PROBE_POSITION_INDEPENDENT=YES",
        "P1_STATE_PROBE_NO_STACK=YES",
        "P1_STATE_PROBE_NO_MEMORY_READ=YES",
        "P1_STATE_PROBE_NO_MEMORY_WRITE=YES",
        "P1_STATE_PROBE_NO_ABSOLUTE_ADDRESS=YES",
        "ELF_RELOCATIONS=0",
        f"ESP_PROBE_SHA256={probe_report['probe_sha']}",
        f"ESP_PROBE_SIZE={probe_report['raw_len']}",
        f"ESP_PADDING_BYTE=0x{PADDING_BYTE:02x}",
        f"ESP_PADDING_LEN={pad_len}",
        f"ESP_PADDING_SHA256={sha(bytes([PADDING_BYTE]) * pad_len)}",
        "ESP_TIMER_SOURCE=CNTPCT",
        f"ESP_PSCI_FUNCTION_ID=0x{PSCI_SYSTEM_RESET:08x}",
        "ESP_DISASM_GATES=PASS",
        "ESP_EL_SAFE_SCTLR_ACCESS=PASS",
        "ESP_NO_MEMORY_ACCESS=PASS",
        "ESP_NO_STACK=PASS",
        "ESP_RELOCATIONS=0",
        "ESP_NEG_ABSOLUTE_ADDRESS=REJECT",
        "FAIL_CLOSED=PASS",
        "NEGATIVE_TESTS_PASS=YES",
        "DEVICE_OPERATION=NO",
    ]
    for label, delay in expected_mapping():
        lines.append(f"STATE_{label.replace(' ', '_').upper()}_DELAY={delay}")
    lines += [
        f"TIMING_TOLERANCE_STRONG={TOLERANCE_STRONG}",
        f"TIMING_TOLERANCE_SUPPORTED={TOLERANCE_SUPPORTED}",
        f"P0_A8_OVERHEAD={A8_OVERHEAD}",
        f"P0_A24_OVERHEAD={A24_OVERHEAD}",
        f"P0_RESET_BOOT_OVERHEAD_REF={A_OVERHEAD_REF}",
        "Does not splice M5D and does not emit a boot image",
    ]
    (out / "p1-entry-state-probe-gates.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        print(line)
    print("R3_ENTRY_STATE_PROBE_ASSEMBLE_GATES=PASS")


def mode_build(args: argparse.Namespace) -> None:
    if not args.m5d_boot:
        fail("ESP_NOT_SAFE", "build requires --m5d-boot")
    probe_report, kernel = build_gates(args)
    out = Path(args.out).resolve()
    m5d_path = Path(args.m5d_boot).resolve()
    m5d = m5d_path.read_bytes()
    if sha(m5d) != M5D_BOOT_SHA256:
        fail("ESP_M5D_IDENTITY_FAILED", "boot sha")
    m5d_boot = parse_boot(m5d, "M5D")
    require_boot_geometry(m5d_boot, "M5D")
    if m5d_boot["kernel_size"] != KERNEL_SIZE or sha(m5d_boot["kernel"]) != M5D_IMAGE_SHA256:
        fail("ESP_M5D_IDENTITY_FAILED", "kernel")
    if m5d_boot["ramdisk_size"] != RAMDISK_SIZE or sha(m5d_boot["ramdisk"]) != M5D_RAMDISK_SHA256:
        fail("ESP_RAMDISK_FAILED", "M5D ramdisk")
    if m5d_boot["cmdline"].rstrip(b"\x00") != b"":
        fail("ESP_CMDLINE_FAILED", "M5D cmdline")
    if any(m5d_boot["reserved"]):
        fail("ESP_BOOT_LAYOUT_FAILED", "reserved")

    boot = splice(m5d, kernel)
    packed = parse_boot(boot, "probe")
    require_boot_geometry(packed, "probe")
    if packed["header_version"] != 3 or packed["header_size"] != BOOT_HEADER_V3_SIZE:
        fail("ESP_BOOT_LAYOUT_FAILED", "probe boot header")
    if packed["cmdline"] != m5d_boot["cmdline"]:
        fail("ESP_CMDLINE_FAILED", "probe cmdline")
    if packed["ramdisk"] != m5d_boot["ramdisk"]:
        fail("ESP_RAMDISK_FAILED", "probe ramdisk")
    if packed["os_version_raw"] != m5d_boot["os_version_raw"]:
        fail("ESP_BOOT_LAYOUT_FAILED", "os_version")

    m5d_boot_diff = diff_offsets(m5d, boot)
    if not m5d_boot_diff or min(m5d_boot_diff) < KERNEL_OFFSET:
        fail("ESP_DELTA_FAILED", "header changed vs M5D")
    if max(m5d_boot_diff) >= KERNEL_OFFSET + KERNEL_SIZE:
        fail("ESP_RAMDISK_FAILED", "non-kernel diff vs M5D")
    if boot[:KERNEL_OFFSET] != m5d[:KERNEL_OFFSET]:
        fail("ESP_BOOT_LAYOUT_FAILED", "v3 header vs M5D")
    if boot[RAMDISK_OFFSET:] != m5d[RAMDISK_OFFSET:]:
        fail("ESP_RAMDISK_FAILED", "tail vs M5D")
    print("ESP_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_ONLY")
    print("ESP_NON_KERNEL_M5D_CONTEXT=MATCH")

    def ramdisk_must_match(blob: bytes) -> None:
        parsed = parse_boot(blob, "neg-rd")
        if parsed["ramdisk"] != m5d_boot["ramdisk"]:
            fail("ESP_RAMDISK_FAILED", "unexpected ramdisk diff")

    def cmdline_must_match(blob: bytes) -> None:
        parsed = parse_boot(blob, "neg-cmd")
        if parsed["cmdline"] != m5d_boot["cmdline"]:
            fail("ESP_CMDLINE_FAILED", "unexpected cmdline diff")

    bad_magic = bytearray(boot)
    bad_magic[56:60] = b"XXXX"
    expect_reject(lambda: parse_image(bytes(bad_magic), "neg-magic-file"),
                  "ESP_IMAGE_HEADER")
    bad_ver = bytearray(boot)
    struct.pack_into("<I", bad_ver, 40, 2)
    expect_reject(lambda: parse_boot(bytes(bad_ver), "neg-v2"), "ESP_BOOT_LAYOUT")
    bad_ksize = bytearray(boot)
    struct.pack_into("<I", bad_ksize, 8, 123)
    expect_reject(
        lambda: require_boot_geometry(
            parse_boot(bytes(bad_ksize), "neg-ksize"), "neg-ksize"),
        "ESP_BOOT_LAYOUT")
    expect_reject(
        lambda: require_boot_geometry(
            parse_boot(boot[:BOOT_SIZE - 1], "neg-short"), "neg-short"),
        "ESP_BOOT_LAYOUT")
    bad_rd = bytearray(boot)
    bad_rd[RAMDISK_OFFSET] ^= 0xFF
    expect_reject(lambda: ramdisk_must_match(bytes(bad_rd)), "ESP_RAMDISK")
    bad_cmd = bytearray(boot)
    bad_cmd[44] = 0x41
    expect_reject(lambda: cmdline_must_match(bytes(bad_cmd)), "ESP_CMDLINE")

    boot_name = "thyme-r3-entry-state-probe.img"
    (out / boot_name).write_bytes(boot)
    (out / "Image-entry-state-probe").write_bytes(kernel)
    pad_len = KERNEL_SIZE - probe_report["raw_len"]
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    run_sha = os.environ.get("GITHUB_SHA", "unknown")
    mapping_lines = [f"STATE_{label.replace(' ', '_').upper()}_DELAY={delay}"
                     for label, delay in expected_mapping()]
    lines = [
        "R3_ENTRY_STATE_PROBE_CI",
        "P1_STATE_PROBE_POSITION_INDEPENDENT=YES",
        "P1_STATE_PROBE_NO_STACK=YES",
        "P1_STATE_PROBE_NO_MEMORY_READ=YES",
        "P1_STATE_PROBE_NO_MEMORY_WRITE=YES",
        "P1_STATE_PROBE_NO_ABSOLUTE_ADDRESS=YES",
        "ELF_RELOCATIONS=0",
        "ESP_DISASM_GATES=PASS",
        "ESP_EL_SAFE_SCTLR_ACCESS=PASS",
        "ESP_NO_MEMORY_ACCESS=PASS",
        "ESP_NO_STACK=PASS",
        "ESP_RELOCATIONS=0",
        "ESP_HEADER_GATES=PASS",
        "ESP_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_ONLY",
        "ESP_NON_KERNEL_M5D_CONTEXT=MATCH",
        "BOOT_HEADER=v3",
        f"ESP_KERNEL_PAYLOAD_SIZE={KERNEL_SIZE}",
        f"IMAGE_TEXT_OFFSET=0x{TEXT_OFFSET:x}",
        f"IMAGE_IMAGE_SIZE=0x{IMAGE_SIZE_FIELD:x}",
        f"IMAGE_FLAGS=0x{FLAGS:x}",
        "IMAGE_PE_OFFSET=0x0",
        "RAMDISK=MATCH",
        "CMDLINE=MATCH",
        f"ESP_PADDING_BYTE=0x{PADDING_BYTE:02x}",
        f"ESP_PADDING_LEN={pad_len}",
        f"ESP_PADDING_SHA256={sha(bytes([PADDING_BYTE]) * pad_len)}",
        f"ESP_PROBE_SHA256={probe_report['probe_sha']}",
        f"ESP_KERNEL_SHA256={probe_report['kernel_sha']}",
        f"ESP_BOOT_SHA256={sha(boot)}",
        f"ESP_BOOT_SIZE={len(boot)}",
        "ESP_TIMER_SOURCE=CNTPCT",
        f"ESP_PSCI_FUNCTION_ID=0x{PSCI_SYSTEM_RESET:08x}",
        "ESP_PSCI_CONDUIT=SMC",
        *mapping_lines,
        f"TIMING_TOLERANCE_STRONG={TOLERANCE_STRONG}",
        f"TIMING_TOLERANCE_SUPPORTED={TOLERANCE_SUPPORTED}",
        f"P0_A8_OVERHEAD={A8_OVERHEAD}",
        f"P0_A24_OVERHEAD={A24_OVERHEAD}",
        f"P0_RESET_BOOT_OVERHEAD_REF={A_OVERHEAD_REF}",
        f"RT_D_DTB_SHA256={RTD_DTB_SHA256}",
        "P1_CLEAN_IMAGE_REBUILD_PENDING=YES",
        "M5N_FROZEN=YES",
        "USB_FROZEN=YES",
        "DEVICE_OPERATION=NO",
        "PARTITION_WRITES=0",
        "SLOT_A_WRITTEN=NO",
        "FAIL_CLOSED=PASS",
        "NEGATIVE_TESTS_PASS=YES",
        f"GITHUB_RUN_ID={run_id}",
        f"GITHUB_SHA={run_sha}",
        f"TOOLCHAIN_LLVM_VERSION={LLVM_VERSION}",
        f"TOOLCHAIN_PKG={LLVM_PKG}",
        f"TOOLCHAIN_RUNNER={RUNNER_IMAGE}",
    ]
    (out / "p1-entry-state-probe-gates.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    (out / "entry-state-probe-manifest.txt").write_text(
        "\n".join(["R3_ENTRY_STATE_PROBE_MANIFEST", *lines]) + "\n",
        encoding="utf-8")
    sums = []
    for name in (boot_name, "Image-entry-state-probe", "p1-entry-state-probe.bin",
                 "p1-entry-state-probe-gates.txt",
                 "entry-state-probe-manifest.txt",
                 "p1-entry-state-probe-disasm.txt"):
        path = out / name
        if path.is_file():
            sums.append(f"{sha(path.read_bytes())}  {name}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (out / "DO_NOT_FLASH.txt").write_text("\n".join([
        "thyme-r3-entry-state-probe.img",
        "DEVICE_OPERATION=NO",
        "PARTITION_WRITES=0",
        "FASTBOOT_BOOT_ONLY=YES",
        "WAIT_FOR_USER_APPROVAL=YES",
    ]) + "\n", encoding="utf-8")
    for line in lines:
        print(line)
    print("R3_ENTRY_STATE_PROBE_GATES=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=(
        "source-gate", "bit-position-pin", "ram-reconciliation",
        "decoder-fixtures", "assemble-gates", "build"))
    parser.add_argument("--out")
    parser.add_argument("--m5d-boot")
    parser.add_argument("--dts")
    parser.add_argument("--evidence")
    parser.add_argument("--dtb")
    parser.add_argument("--linux")
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--lld", default="ld.lld-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    parser.add_argument("--objdump", default="llvm-objdump-18")
    parser.add_argument("--readelf", default="llvm-readelf-18")
    args = parser.parse_args()
    if args.mode == "source-gate":
        source_gate_tokens()
    elif args.mode == "bit-position-pin":
        if not args.linux:
            fail("ESP_NOT_SAFE", "bit-position-pin requires --linux")
        mode_bit_position_pin(args)
    elif args.mode == "ram-reconciliation":
        for req in ("dts", "evidence", "dtb"):
            if not getattr(args, req):
                fail("ESP_NOT_SAFE", f"ram-reconciliation requires --{req}")
        mode_ram_reconciliation(args)
    elif args.mode == "decoder-fixtures":
        mode_decoder_fixtures()
    elif args.mode == "assemble-gates":
        if not args.out:
            fail("ESP_NOT_SAFE", "assemble-gates requires --out")
        mode_assemble_gates(args)
    elif args.mode == "build":
        if not args.out:
            fail("ESP_NOT_SAFE", "build requires --out")
        mode_build(args)


if __name__ == "__main__":
    main()
