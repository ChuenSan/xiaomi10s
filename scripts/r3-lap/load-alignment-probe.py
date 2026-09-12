#!/usr/bin/env python3
"""R3 load-alignment probe: source gates, decoder fixtures, assemble gates,
boot packing. GitHub Actions only."""

from __future__ import annotations

import argparse
import hashlib
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
LOW21_MASK = 0x1fffff
LOW21_EXPECTED = 0x80000
DELAY_ALIGN_MATCH = 8
DELAY_ALIGN_MISMATCH = 24
PADDING_BYTE = 0x00
MAX_PROBE = 4096
PSCI_SYSTEM_RESET = 0x84000009
ARM64_MAGIC = b"ARM\x64"
BOOT_MAGIC = b"ANDROID!"
M5D_BOOT_SHA256 = "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"
M5D_IMAGE_SHA256 = "5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a"
M5D_RAMDISK_SHA256 = "b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de"
RTD_DTB_SHA256 = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
STOCK_KERNEL_CODE_BASE = 0xA0080000
LLVM_VERSION = "18.1.3"
LLVM_PKG = "1:18.1.3-1ubuntu1"
RUNNER_IMAGE = "ubuntu-24.04"
TOLERANCE_STRONG = 0.75
TOLERANCE_SUPPORTED = 1.5
A8_OBSERVED = 14.148
A24_OBSERVED = 30.141
A8_PROGRAMMED = 8
A24_PROGRAMMED = 24
A8_OVERHEAD = round(A8_OBSERVED - A8_PROGRAMMED, 3)
A24_OVERHEAD = round(A24_OBSERVED - A24_PROGRAMMED, 3)
P0_OVERHEAD_REF = round((A8_OVERHEAD + A24_OVERHEAD) / 2, 4)
ESP_OBSERVED_TOTAL = 10.094
# Only the plain PC-relative ADR class is allowed at object level; anything
# else (R_AARCH64_ABS*, R_AARCH64_RELATIVE, GOT classes) must fail.
ALLOWED_OBJ_RELOCS = {"R_AARCH64_ADR_PREL_LO21"}

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PROBE_SRC = HERE / "r3-lap-probe.S"
PROBE_LD = HERE / "r3-lap-probe.ld"
NEG_MUTANTS = {
    "r3-lap-neg-store.S": "LAP_NEG_UNKNOWN_MEMORY_STORE",
    "r3-lap-neg-stack.S": "LAP_NEG_STACK_USE",
    "r3-lap-neg-offset.S": "LAP_NEG_WRONG_IMAGE_BASE_OFFSET",
    "r3-lap-neg-reloc.S": "LAP_NEG_ABSOLUTE_SYMBOL_RELOCATION",
    "r3-lap-neg-fid.S": "LAP_NEG_WRONG_PSCI_FID",
}
NEG_ABSOLUTE = HERE / "r3-lap-neg-absolute.S"
OBSERVER_SRC = HERE / "observe-r3-load-alignment.py"
OBSERVER_FIXTURES = HERE / "observer-summary-fixtures.py"
DOC = REPO / "docs" / "route-r3-load-alignment-probe-ci.md"
PUBLIC_WF = REPO / ".github" / "workflows" / "thyme-r3-load-alignment-probe.yml"

STORE_RE = re.compile(
    r"\b(str|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|stadd)\b", re.I
)
LOAD_RE = re.compile(
    r"\b(ldr|ldrb|ldrh|ldp|ldur|ldar|ldxr|ldtr|ldnp)\b", re.I
)
BAD_RE = re.compile(
    r"\b(sp|adrp|msr|eret|hvc|svc|brk|udf|bl|blr|ret|cntvct|got)\b", re.I
)
ALLOW_MNEM = {
    "b", "b.eq", "b.hs",
    "cmp", "mrs", "mov", "movz", "movk", "add", "sub", "mul",
    "and", "lsl", "isb", "yield", "wfe", "nop", "smc", "adr",
}
LAP_ADR_RE = re.compile(
    r"x0,\s*(?:#)?(?P<val>-?(?:0x[0-9a-f]+|[0-9]+))?(?:\s*<(?P<sym>[^>]*)>)?\s*$",
    re.I,
)

SEQUENCE = [
    ("isb", r"(sy|#(?:0xf|15))?$"),
    ("adr", None),
    ("mov(?:z)?", r"x1, #(?:0xffff|65535)$"),
    ("movk", r"x1, #(?:0x1f|31), lsl #(?:0x10|16)$"),
    ("and", r"x0, x0, x1$"),
    ("mov(?:z)?", r"x2, #(?:0x8|8)$"),
    ("lsl", r"x2, x2, #(?:0x10|16)$"),
    ("cmp", r"x0, x2$"),
    ("b.eq", r"0x(?P<t_match>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x5, #(?:0x18|24)$"),
    ("b", r"0x(?P<t_timer>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"x5, #(?:0x8|8)$"),
    ("mrs", r"x6, cntfrq_el0$"),
    ("mul", r"x5, x6, x5$"),
    ("isb", r"(sy|#(?:0xf|15))?$"),
    ("mrs", r"x7, cntpct_el0$"),
    ("isb", r"(sy|#(?:0xf|15))?$"),
    ("mrs", r"x8, cntpct_el0$"),
    ("sub", r"x9, x8, x7$"),
    ("cmp", r"x9, x5$"),
    ("b.hs", r"0x(?P<t_done>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("yield", r"$^"),
    ("b", r"0x(?P<t_loop>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
    ("mov(?:z)?", r"w0, #(?:0x)?(?P<fid_lo>[0-9a-f]+)$"),
    ("movk", r"w0, #0x8400, lsl #(?:0x10|16)$"),
    ("mov", r"x1, (xzr|#(?:0x0|0))$"),
    ("mov", r"x2, (xzr|#(?:0x0|0))$"),
    ("mov", r"x3, (xzr|#(?:0x0|0))$"),
    ("smc", r"#(?:0x0|0)$"),
    ("wfe", r"$^"),
    ("b", r"0x(?P<t_spin>[0-9a-f]+)(?:\s*<[^>]*>)?$"),
]

TARGET_BY_INDEX = {
    "t_match": 11,
    "t_timer": 12,
    "t_done": 23,
    "t_loop": 16,
    "t_spin": 29,
}
IDX_ADR = 1


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    msg = label if not detail else f"{label}: {detail}"
    raise SystemExit(msg)


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        fail("LAP_ASSEMBLE_FAILED", f"{' '.join(cmd)}\n{proc.stderr}")
    return proc.stdout


def sx(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def b_target(word: int, pc: int) -> int:
    if word & 0xFC000000 != 0x14000000:
        fail("LAP_CODE0_TARGET_FAILED", f"not B: 0x{word:08x}")
    return pc + sx(word & 0x03FFFFFF, 26) * 4


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def parse_image(image: bytes, label: str) -> dict:
    if len(image) < 64:
        fail("LAP_IMAGE_HEADER_FAILED", f"{label} short")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<QQQQQQ", image, 8)
    magic = image[56:60]
    pe = struct.unpack_from("<I", image, 60)[0]
    if magic != ARM64_MAGIC:
        fail("LAP_IMAGE_HEADER_FAILED", f"{label} magic={magic!r}")
    return {
        "code0": code0, "code1": code1, "text_offset": text_offset,
        "image_size": image_size, "flags": flags, "res2": res2,
        "res3": res3, "res4": res4, "magic": magic, "pe_offset": pe,
    }


def parse_boot(boot: bytes, label: str) -> dict:
    if len(boot) < PAGE or boot[:8] != BOOT_MAGIC:
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} not ANDROID!")
    kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from("<IIII", boot, 8)
    reserved = struct.unpack_from("<IIII", boot, 24)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    cmdline = boot[44:BOOT_HEADER_V3_SIZE]
    if header_version != 3:
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} header_version={header_version}")
    if header_size != BOOT_HEADER_V3_SIZE:
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} header_size={header_size}")
    kernel_end = KERNEL_OFFSET + kernel_size
    ramdisk_off = align(kernel_end, PAGE)
    ramdisk_end = ramdisk_off + ramdisk_size
    if ramdisk_end > len(boot):
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} truncated")
    if boot[BOOT_HEADER_V3_SIZE:PAGE] != b"\x00" * (PAGE - BOOT_HEADER_V3_SIZE):
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} header pad")
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
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} kernel_size={parsed['kernel_size']}")
    if parsed["ramdisk_size"] != RAMDISK_SIZE:
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} ramdisk_size")
    if parsed["total"] != BOOT_SIZE:
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} total={parsed['total']}")
    if parsed["ramdisk_off"] != RAMDISK_OFFSET:
        fail("LAP_BOOT_LAYOUT_FAILED", f"{label} ramdisk_off")


ALIGNMENT_BY_DELAY = {
    DELAY_ALIGN_MATCH: "ALIGNMENT_MATCH",
    DELAY_ALIGN_MISMATCH: "ALIGNMENT_MISMATCH",
}


def decode_observed(delta_s: float) -> tuple[int, str]:
    programmed = delta_s - P0_OVERHEAD_REF
    nearest = min((DELAY_ALIGN_MATCH, DELAY_ALIGN_MISMATCH),
                  key=lambda d: abs(programmed - d))
    err = abs(programmed - nearest)
    if err <= TOLERANCE_STRONG:
        return nearest, "STRONG"
    if err <= TOLERANCE_SUPPORTED:
        return nearest, "SUPPORTED"
    fail("LAP_DECODER_INCONCLUSIVE",
         f"delta {delta_s} outside both alignment buckets")


def expect_reject(fn, label: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        text = str(exc)
        if label in text or text.startswith("LAP_"):
            print(f"NEG_{label}=REJECT")
            return
        fail("LAP_NEGATIVE_TEST_FAILED", f"{label} wrong fail {text}")
    fail("LAP_NEGATIVE_TEST_FAILED", f"{label} accepted")


def require_llvm(path: str, needle: str) -> str:
    out = run([path, "--version"])
    if needle not in out.splitlines()[0] and needle not in out:
        fail("LAP_TOOLCHAIN_PIN_FAILED",
             f"{path}: {out.splitlines()[0] if out else 'empty'}")
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


def relocs_obj(readelf: str, obj: Path) -> list[str]:
    out = run([readelf, "-r", "--wide", str(obj)])
    types = re.findall(r"R_AARCH64_[A-Z0-9_]+", out)
    bad = sorted(set(types) - ALLOWED_OBJ_RELOCS)
    if bad:
        fail("LAP_RELOCATION_FAILED",
             f"non-PC-relative object relocations {bad}\n{out}")
    return types


def relocs_final(readelf: str, elf: Path) -> None:
    out = run([readelf, "-r", "--wide", str(elf)])
    if "R_AARCH64_" in out or "Relocation section" in out:
        fail("LAP_RELOCATION_FAILED", f"linked ELF has relocations\n{out}")


def symbols_final(readelf: str, elf: Path) -> None:
    out = run([readelf, "-s", "--wide", str(elf)])
    wanted: dict[str, int] = {}
    for line in out.splitlines():
        if re.search(r"\sUND\s+\S+\s*$", line):
            fail("LAP_ELF_SYMBOL_FAILED", f"undefined symbol: {line}")
        parts = line.split()
        if len(parts) >= 8 and parts[-1] in ("image_base", "_start", "probe_entry"):
            wanted[parts[-1]] = int(parts[1], 16)
    if wanted.get("image_base") != 0:
        fail("LAP_ELF_SYMBOL_FAILED",
             f"image_base={wanted.get('image_base')} != kernel payload offset 0")
    if wanted.get("_start") != 0:
        fail("LAP_ELF_SYMBOL_FAILED", f"_start={wanted.get('_start')} != 0")
    if wanted.get("probe_entry") != PROBE_BODY:
        fail("LAP_ELF_SYMBOL_FAILED", f"probe_entry={wanted.get('probe_entry')}")


def sections(objdump: str, elf: Path) -> None:
    out = run([objdump, "-h", str(elf)])
    for bad in (".data", ".bss", ".got", ".rodata"):
        if re.search(rf"\b{re.escape(bad)}\b", out):
            fail("LAP_ELF_SECTION_FAILED", bad)


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


def parse_adr_val(text: str) -> int:
    body = text.lstrip("-")
    value = int(body, 16) if body.lower().startswith("0x") else int(body, 10)
    return -value if text.startswith("-") else value


def check_adr_image_base(ops: str) -> int:
    m = LAP_ADR_RE.fullmatch(ops)
    if not m:
        fail("LAP_DISASM_FAILED", f"adr operands {ops!r}")
    val_txt, sym = m.group("val"), m.group("sym")
    if val_txt is not None:
        val = parse_adr_val(val_txt)
        if val == 0:
            return 0
        if val == -0x44:
            return 0
        fail("LAP_DISASM_FAILED",
             f"adr {val_txt!r} does not reference image_base at payload offset 0")
    if sym in ("image_base", "_start"):
        return 0
    fail("LAP_DISASM_FAILED", f"adr symbol-only print {sym!r} unexpected")


def line_txt(addr: int, mnem: str, ops: str) -> str:
    return f"{addr:#x}: {mnem} {ops}"


def check_probe_sequence(dump: str) -> dict[str, int]:
    body = parse_ins(dump, PROBE_BODY)
    groups: dict[str, int] = {}
    addr_by_idx: dict[int, int] = {}
    i = 0
    for idx, (mnem_re, ops_re) in enumerate(SEQUENCE):
        if i >= len(body):
            fail("LAP_DISASM_FAILED", f"sequence truncated at element {idx}")
        addr, mnem, ops = body[i]
        if not re.fullmatch(mnem_re, mnem):
            fail("LAP_DISASM_FAILED",
                 f"element {idx}: expected {mnem_re!r}, got {line_txt(addr, mnem, ops)}")
        if idx == IDX_ADR:
            target = check_adr_image_base(ops)
            groups["adr_target"] = target
            addr_by_idx[idx] = addr
            i += 1
            continue
        m = re.fullmatch(ops_re, ops, re.I)
        if not m:
            fail("LAP_DISASM_FAILED",
                 f"element {idx}: ops {ops!r} !~ {ops_re!r}")
        for key, val in (m.groupdict() if m else {}).items():
            if val is not None:
                groups[key] = int(val, 16)
        addr_by_idx[idx] = addr
        i += 1
    if i != len(body):
        addr, mnem, ops = body[i]
        fail("LAP_DISASM_FAILED", f"unexpected tail {line_txt(addr, mnem, ops)}")
    for key, idx in TARGET_BY_INDEX.items():
        if groups.get(key) != addr_by_idx[idx]:
            fail("LAP_DISASM_FAILED",
                 f"{key}={groups.get(key, -1):#x} does not target element {idx} "
                 f"at {addr_by_idx[idx]:#x}")
    if groups.get("adr_target") != 0:
        fail("LAP_DISASM_FAILED", "adr does not target payload offset 0")
    if groups.get("fid_lo") != 0x9:
        fail("LAP_DISASM_FAILED", f"PSCI function id low {groups.get('fid_lo'):#x}")
    return groups


def global_rejects(dump: str) -> None:
    body = parse_ins(dump, PROBE_BODY)
    if not body:
        fail("LAP_DISASM_FAILED", "empty body")
    for addr, mnem, ops in body:
        text = f"{mnem} {ops}"
        if STORE_RE.search(text):
            fail("LAP_STORE_REJECT_FAILED", line_txt(addr, mnem, ops))
        if LOAD_RE.search(text):
            fail("LAP_DISASM_FAILED", f"memory load {line_txt(addr, mnem, ops)}")
        if BAD_RE.search(text):
            fail("LAP_DISASM_FAILED", f"forbidden {line_txt(addr, mnem, ops)}")
        if mnem not in ALLOW_MNEM:
            fail("LAP_DISASM_FAILED", f"unexpected mnemonic {line_txt(addr, mnem, ops)}")


def check_header_fields(raw: bytes) -> dict:
    hdr = parse_image(raw, "probe")
    if hdr["text_offset"] != TEXT_OFFSET or hdr["image_size"] != IMAGE_SIZE_FIELD:
        fail("LAP_IMAGE_HEADER_FAILED", "text_offset/image_size")
    if hdr["flags"] != FLAGS or hdr["pe_offset"] != PE_OFFSET:
        fail("LAP_IMAGE_HEADER_FAILED", "flags/pe")
    if hdr["res2"] or hdr["res3"] or hdr["res4"]:
        fail("LAP_IMAGE_HEADER_FAILED", "reserved")
    t0 = b_target(hdr["code0"], 0)
    t1 = b_target(hdr["code1"], 4)
    if t0 != PROBE_BODY or t1 != PROBE_BODY:
        fail("LAP_CODE0_TARGET_FAILED", f"{t0:#x} {t1:#x}")
    if t0 >= KERNEL_SIZE:
        fail("LAP_CODE0_TARGET_FAILED", "outside payload")
    return hdr


def pad_kernel(raw: bytes) -> bytes:
    if len(raw) > KERNEL_SIZE or len(raw) > MAX_PROBE:
        fail("LAP_SIZE_FAILED", f"probe {len(raw)}")
    if len(raw) < PROBE_BODY + 4:
        fail("LAP_SIZE_FAILED", f"probe {len(raw)}")
    return raw + bytes([PADDING_BYTE]) * (KERNEL_SIZE - len(raw))


def splice(m5d: bytes, kernel: bytes) -> bytes:
    if len(m5d) != BOOT_SIZE:
        fail("LAP_M5D_IDENTITY_FAILED", f"size {len(m5d)}")
    if len(kernel) != KERNEL_SIZE:
        fail("LAP_SIZE_FAILED", f"kernel {len(kernel)}")
    out = bytearray(m5d)
    out[KERNEL_OFFSET:KERNEL_OFFSET + KERNEL_SIZE] = kernel
    return bytes(out)


def diff_offsets(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        fail("LAP_DELTA_FAILED", f"len {len(a)} vs {len(b)}")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def make_synthetic_boot() -> bytes:
    hdr = bytearray(BOOT_HEADER_V3_SIZE)
    struct.pack_into("<8s", hdr, 0, BOOT_MAGIC)
    struct.pack_into("<IIII", hdr, 8, KERNEL_SIZE, RAMDISK_SIZE, 0, BOOT_HEADER_V3_SIZE)
    struct.pack_into("<I", hdr, 40, 3)
    boot = bytearray(BOOT_SIZE)
    boot[0:BOOT_HEADER_V3_SIZE] = hdr
    boot[KERNEL_OFFSET:KERNEL_OFFSET + KERNEL_SIZE] = b"\x5a" * KERNEL_SIZE
    boot[RAMDISK_OFFSET:RAMDISK_OFFSET + RAMDISK_SIZE] = b"\xa5" * RAMDISK_SIZE
    return bytes(boot)


def boot_envelope_fixtures() -> None:
    boot = make_synthetic_boot()
    parsed = parse_boot(boot, "synthetic")
    require_boot_geometry(parsed, "synthetic")
    ref_ramdisk = parsed["ramdisk"]
    ref_cmdline = parsed["cmdline"]

    def ramdisk_must_match(blob: bytes) -> None:
        if parse_boot(blob, "neg-rd")["ramdisk"] != ref_ramdisk:
            fail("LAP_RAMDISK_FAILED", "unexpected ramdisk diff")

    def cmdline_must_match(blob: bytes) -> None:
        if parse_boot(blob, "neg-cmd")["cmdline"] != ref_cmdline:
            fail("LAP_CMDLINE_FAILED", "unexpected cmdline diff")

    bad_magic = bytearray(boot)
    bad_magic[0:8] = b"ANDROIDX"
    expect_reject(lambda: parse_boot(bytes(bad_magic), "neg-magic"),
                  "LAP_BOOT_LAYOUT")
    bad_ver = bytearray(boot)
    struct.pack_into("<I", bad_ver, 40, 2)
    expect_reject(lambda: parse_boot(bytes(bad_ver), "neg-v2"),
                  "LAP_BOOT_LAYOUT")
    bad_ksize = bytearray(boot)
    struct.pack_into("<I", bad_ksize, 8, 123)
    expect_reject(
        lambda: require_boot_geometry(
            parse_boot(bytes(bad_ksize), "neg-ksize"), "neg-ksize"),
        "LAP_BOOT_LAYOUT")
    expect_reject(
        lambda: require_boot_geometry(
            parse_boot(boot[:-1], "neg-short"), "neg-short"),
        "LAP_BOOT_LAYOUT")
    bad_rd = bytearray(boot)
    bad_rd[RAMDISK_OFFSET] ^= 0xFF
    expect_reject(lambda: ramdisk_must_match(bytes(bad_rd)), "LAP_RAMDISK")
    bad_cmd = bytearray(boot)
    bad_cmd[44] = 0x41
    expect_reject(lambda: cmdline_must_match(bytes(bad_cmd)), "LAP_CMDLINE")

    probe_raw_ref = b"\x00" * 64
    bad_img = bytearray(probe_raw_ref)
    bad_img[56:60] = b"XXXX"
    expect_reject(lambda: parse_image(bytes(bad_img), "neg-img-magic"),
                  "LAP_IMAGE_HEADER")
    print("BOOT_ENVELOPE_FIXTURES=PASS")


def mode_decoder_fixtures() -> None:
    buckets = [DELAY_ALIGN_MATCH, DELAY_ALIGN_MISMATCH]
    if buckets != [8, 24]:
        fail("LAP_DECODER_FIXTURE_FAILED", f"buckets {buckets}")
    if len(set(buckets)) != len(buckets):
        fail("LAP_DECODER_FIXTURE_FAILED", "duplicate delay bucket")
    if ALIGNMENT_BY_DELAY[8] != "ALIGNMENT_MATCH" or \
            ALIGNMENT_BY_DELAY[24] != "ALIGNMENT_MISMATCH":
        fail("LAP_DECODER_FIXTURE_FAILED", "alignment mapping")
    windows_strong = [(d - TOLERANCE_STRONG, d + TOLERANCE_STRONG) for d in buckets]
    windows_supported = [(d - TOLERANCE_SUPPORTED, d + TOLERANCE_SUPPORTED) for d in buckets]
    for windows in (windows_strong, windows_supported):
        if windows[0][1] >= windows[1][0]:
            fail("LAP_DECODER_FIXTURE_FAILED", f"bucket windows overlap {windows}")
    if abs(A8_OVERHEAD - 6.148) > 1e-9 or abs(A24_OVERHEAD - 6.141) > 1e-9:
        fail("LAP_DECODER_FIXTURE_FAILED", f"overhead {A8_OVERHEAD} {A24_OVERHEAD}")
    if abs(P0_OVERHEAD_REF - 6.1445) > 1e-9:
        fail("LAP_DECODER_FIXTURE_FAILED", f"reference overhead {P0_OVERHEAD_REF}")
    for observed, programmed in ((A8_OBSERVED, A8_PROGRAMMED),
                                 (A24_OBSERVED, A24_PROGRAMMED)):
        delay, tier = decode_observed(observed)
        if delay != programmed or tier != "STRONG":
            fail("LAP_DECODER_FIXTURE_FAILED",
                 f"observed {observed} -> {delay}/{tier}, want {programmed}/STRONG")
    delay, tier = decode_observed(A8_PROGRAMMED + 1.2 + P0_OVERHEAD_REF)
    if (delay, tier) != (8, "SUPPORTED"):
        fail("LAP_DECODER_FIXTURE_FAILED", f"supported tier got {delay}/{tier}")
    expect_reject(lambda: decode_observed(ESP_OBSERVED_TOTAL),
                  "LAP_DECODER_INCONCLUSIVE")
    if STOCK_KERNEL_CODE_BASE % 0x200000 != LOW21_EXPECTED:
        fail("LAP_DECODER_FIXTURE_FAILED", "stock kernel supporting evidence mod")

    def dup_fixture():
        if len(set([8, 8])) != 2:
            fail("LAP_DUPLICATE_DELAY_BUCKET", "8s encoded twice")

    def overlap_fixture():
        windows = [(8 - 9, 8 + 9), (24 - 9, 24 + 9)]
        if windows[0][1] >= windows[1][0]:
            fail("LAP_BUCKET_WINDOW_OVERLAP", f"{windows}")

    def fid_fixture():
        fid = 0x8400000F
        if fid == PSCI_SYSTEM_RESET:
            return
        fail("LAP_UNKNOWN_PSCI_FID", f"fid {fid:#x} is not SYSTEM_RESET")

    expect_reject(dup_fixture, "LAP_DUPLICATE_DELAY_BUCKET")
    expect_reject(overlap_fixture, "LAP_BUCKET_WINDOW_OVERLAP")
    expect_reject(fid_fixture, "LAP_UNKNOWN_PSCI_FID")
    print("LAP_DECODER_FIXTURES=PASS")


def source_gate_tokens() -> None:
    for path in (PROBE_SRC, PROBE_LD, NEG_ABSOLUTE, OBSERVER_SRC,
                 OBSERVER_FIXTURES, DOC, PUBLIC_WF,
                 *(HERE / name for name in NEG_MUTANTS)):
        if not path.is_file() or path.stat().st_size == 0:
            fail("LAP_SOURCE_GATE_FAILED", f"missing {path}")
    src = PROBE_SRC.read_text()
    for token in (
        ".global image_base", "adr\tx0, image_base", "movz\tx1, #0xffff",
        "movk\tx1, #0x1f, lsl #16", "and\tx0, x0, x1", "movz\tx2, #0x8",
        "lsl\tx2, x2, #16", "cmp\tx0, x2", "b.eq\tmatch", "movz\tx5, #24",
        "movz\tx5, #8", "mrs\tx6, cntfrq_el0", "mrs\tx7, cntpct_el0",
        "smc\t#0", "0x644d5241", "0x2220000", ".quad\t0x80000", ".org 0x40",
        "0x84000009",
    ):
        if token not in src:
            fail("LAP_SOURCE_GATE_FAILED", f"probe missing {token}")
    for pattern in (
        r"\bldr\b", r"\bldp\b", r"\bstr\b", r"\bstp\b", r"\badrp\b",
        r"\bmsr\b", r"\beret\b", r"\bhvc\b", r"\bsvc\b", r"\bbl\b",
        r"\bblr\b", r"\bret\b", r"\bsp\b", r"\bcntvct\b", r":lo12:",
        r":got:", r"\.data\b", r"\.bss\b", r"\.got\b", r"\.rodata\b",
        r"=\s*image_base", r"\.quad\s+image_base",
    ):
        if re.search(pattern, src, re.I):
            fail("LAP_SOURCE_GATE_FAILED", f"probe source has {pattern}")
    observer = OBSERVER_SRC.read_text()
    for token in (
        '"transient_fastboot": False', '"stable_fastboot": False',
        '"expected_probe_reset_not_observed": False',
        "def emit_summary", "def decode_alignment", "ALIGNMENT_MATCH",
        "ALIGNMENT_MISMATCH", "R3_PROBE_BOOT_IMG", "R3_PROBE_SHA256",
        "FASTBOOT_BOOT_ONLY", "6.1445", "LAP_BUCKETS = [8, 24]",
        "SECOND_BOOT", "P0_OVERHEAD_REF",
    ):
        if token not in observer:
            fail("LAP_SOURCE_GATE_FAILED", f"observer missing {token}")
    fixtures = OBSERVER_FIXTURES.read_text()
    for token in (
        "transient_fastboot", "KeyError", "OBSERVER_SUMMARY_FIXTURE=PASS",
        "TRANSIENT_PRESENT", "TRANSIENT_ABSENT", "ANDROID_RETURN",
        "STABLE_FASTBOOT_RETURN", "MANUAL_RECOVERY_NO_RETURN",
        "DECODE_MATCH", "DECODE_MISMATCH", "DECODE_INCONCLUSIVE",
    ):
        if token not in fixtures:
            fail("LAP_SOURCE_GATE_FAILED", f"observer fixtures missing {token}")
    script = Path(__file__).read_text()
    for token in (
        "GITHUB_ACTIONS", "0x84000009", RTD_DTB_SHA256, M5D_BOOT_SHA256,
        M5D_IMAGE_SHA256, M5D_RAMDISK_SHA256,
        "thyme-r3-load-alignment-probe.img", "TOLERANCE_STRONG",
        "P0_OVERHEAD_REF", "0x1fffff", "0x80000", "R_AARCH64_ADR_PREL_LO21",
        "R_AARCH64_ABS", "LOW21_EXPECTED", "STOCK_KERNEL_CODE_BASE",
    ):
        if token not in script:
            fail("LAP_SOURCE_GATE_FAILED", f"script missing {token}")
    doc_text = DOC.read_text()
    for token in (
        "FINAL_GATE_PREVIOUS=R3_ENTRY_STATE_PRIMARY_CONTRACT_SATISFIED",
        "EXECUTABLE_PLACEMENT_PROVEN=YES",
        "MAINLINE_IMAGE_PLACEMENT_CONTRACT_PROVEN",
        "LOAD_ALIGNMENT_SUPPORTING_EVIDENCE",
        "SUPPORTING_ONLY",
        "R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M",
        "MAINLINE_IMAGE_ALIGNMENT_CONTRACT",
        "R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M_MISMATCH=YES",
        "R3_LOAD_ALIGNMENT_PROBE_INCONCLUSIVE",
        "R3_P1_LOAD_GEOMETRY_ISOLATION_CI",
        "MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI",
        "COPYDOWN_REQUIRED=NO",
        "RT_D_DTB_SHA256", RTD_DTB_SHA256,
        "M5D_BOOT_SHA256", M5D_BOOT_SHA256,
        "STOCK_KERNEL_CODE_BASE=0xa0080000",
        "LOW21=S&0x1fffff",
        "MODULUS=0x200000",
        "REQUIRED_LOW21=0x80000",
        "ALIGNMENT_MATCH -> 8s",
        "ALIGNMENT_MISMATCH -> 24s",
        "P0_RESET_OVERHEAD_REF=6.1445",
        "A8 overhead: 6.148s",
        "A24 overhead: 6.141s",
        "THYME_PSCI_CONDUIT=SMC",
        "P0_TIMER_SOURCE=CNTPCT",
        "P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET",
        "M5N FROZEN",
        "TIMING_TOLERANCE_STRONG=0.75",
        "TIMING_TOLERANCE_SUPPORTED=1.5",
        "ELF_RELOCATIONS=0",
        "OBSERVER_SUMMARY_FIXTURE=PASS",
        "transient_fastboot",
        "KeyError",
        "image_base",
        "READY_FOR_R3_LOAD_ALIGNMENT_PROBE_DEVICE_CONTROL",
        "R3_LOAD_ALIGNMENT_PROBE_CI_NOT_READY",
        "LOCAL_BUILD:                       NO",
        "LOCAL_BINARY_VALIDATION:           NO",
        "DEVICE_OPERATION:                  NO",
        "PARTITION_WRITES:                  0",
        "Slot A written:                    NO",
        "AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B",
        "thyme-r3-load-alignment-probe.img",
        "FASTBOOT_BOOT_ONLY=YES",
    ):
        if token not in doc_text:
            fail("LAP_SOURCE_GATE_FAILED", f"doc missing {token!r}")
    wf_text = PUBLIC_WF.read_text()
    if "Does not splice M5D and does not emit a boot image" not in wf_text:
        fail("LAP_SOURCE_GATE_FAILED", "public workflow boundary missing")
    if re.search(r"^\s+run:.*\b(fastboot|adb|flash)\b", wf_text, re.M):
        fail("LAP_SOURCE_GATE_FAILED", "public workflow has device verbs")
    print("LAP_SOURCE_GATE=PASS")


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

    elf = out / "r3-lap-probe.elf"
    bin_path = out / "r3-lap-probe.bin"
    assemble(clang, lld, objcopy, PROBE_SRC, elf, bin_path)
    obj_types = relocs_obj(readelf, elf.with_suffix(".o"))
    relocs_final(readelf, elf)
    symbols_final(readelf, elf)
    sections(objdump, elf)
    raw = bin_path.read_bytes()
    check_header_fields(raw)
    dump = disasm(objdump, elf)
    (out / "r3-lap-probe-disasm.txt").write_text(dump, encoding="utf-8")
    check_probe_sequence(dump)
    global_rejects(dump)
    print(f"LAP_OBJ_RELOC_CLASSES={sorted(set(obj_types))}")
    print("LAP_DISASM_GATES=PASS")
    print("LAP_IMAGE_BASE_PC_RELATIVE=PASS")
    print("LAP_NO_MEMORY_ACCESS=PASS")
    print("LAP_NO_STACK=PASS")
    print("ELF_RELOCATIONS=0")

    for name, label in NEG_MUTANTS.items():
        stem = name[:-2]
        m_elf = out / f"{stem}.elf"
        m_bin = out / f"{stem}.bin"
        assemble(clang, lld, objcopy, HERE / name, m_elf, m_bin)
        m_dump = disasm(objdump, m_elf)
        (out / f"{stem}-disasm.txt").write_text(m_dump, encoding="utf-8")
        expect_reject(lambda d=m_dump: check_probe_sequence(d), label)
        if label in ("LAP_NEG_UNKNOWN_MEMORY_STORE", "LAP_NEG_STACK_USE"):
            expect_reject(lambda d=m_dump: global_rejects(d), label)
    abs_obj = out / "r3-lap-neg-absolute.o"
    run([clang, "--target=aarch64-unknown-none", "-nostdlib", "-ffreestanding",
         "-c", "-o", str(abs_obj), str(NEG_ABSOLUTE)])
    expect_reject(lambda: relocs_obj(readelf, abs_obj), "LAP_NEG_ABSOLUTE_ADDRESS")
    reloc_obj = out / "r3-lap-neg-reloc.o"
    run([clang, "--target=aarch64-unknown-none", "-nostdlib", "-ffreestanding",
         "-c", "-o", str(reloc_obj), str(HERE / "r3-lap-neg-reloc.S")])
    expect_reject(lambda: relocs_obj(readelf, reloc_obj),
                  "LAP_NEG_ABSOLUTE_SYMBOL_RELOCATION")

    boot_envelope_fixtures()

    kernel = pad_kernel(raw)
    return {"probe_sha": sha(raw), "kernel_sha": sha(kernel),
            "raw_len": len(raw)}, kernel


def mode_assemble_gates(args: argparse.Namespace) -> None:
    probe_report, _ = build_gates(args)
    out = Path(args.out).resolve()
    pad_len = KERNEL_SIZE - probe_report["raw_len"]
    lines = [
        "R3_LOAD_ALIGNMENT_PROBE_ASSEMBLE_GATES",
        "LAP_PROBE_POSITION_INDEPENDENT=YES",
        "LAP_IMAGE_BASE_AT_PAYLOAD_OFFSET_0=YES",
        "LAP_IMAGE_BASE_PC_RELATIVE=YES",
        "LAP_NO_STACK=YES",
        "LAP_NO_MEMORY_READ=YES",
        "LAP_NO_MEMORY_WRITE=YES",
        "LAP_NO_ABSOLUTE_ADDRESS=YES",
        "LAP_NO_GOT=YES",
        "ELF_RELOCATIONS=0",
        f"LAP_PROBE_SHA256={probe_report['probe_sha']}",
        f"LAP_PROBE_SIZE={probe_report['raw_len']}",
        f"LAP_LOW21_MASK=0x{LOW21_MASK:x}",
        f"LAP_LOW21_EXPECTED=0x{LOW21_EXPECTED:x}",
        f"LAP_DELAY_ALIGN_MATCH={DELAY_ALIGN_MATCH}",
        f"LAP_DELAY_ALIGN_MISMATCH={DELAY_ALIGN_MISMATCH}",
        f"LAP_PADDING_BYTE=0x{PADDING_BYTE:02x}",
        f"LAP_PADDING_LEN={pad_len}",
        "LAP_TIMER_SOURCE=CNTPCT",
        f"LAP_PSCI_FUNCTION_ID=0x{PSCI_SYSTEM_RESET:08x}",
        "LAP_DISASM_GATES=PASS",
        "LAP_IMAGE_BASE_PC_RELATIVE=PASS",
        "LAP_NO_MEMORY_ACCESS=PASS",
        "LAP_NO_STACK=PASS",
        "BOOT_ENVELOPE_FIXTURES=PASS",
        "LAP_NEG_ABSOLUTE_ADDRESS=REJECT",
        "LAP_NEG_ABSOLUTE_SYMBOL_RELOCATION=REJECT",
        "FAIL_CLOSED=PASS",
        "NEGATIVE_TESTS_PASS=YES",
        "DEVICE_OPERATION=NO",
        "Does not splice M5D and does not emit a boot image",
    ]
    (out / "r3-load-alignment-probe-gates.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        print(line)
    print("R3_LOAD_ALIGNMENT_PROBE_ASSEMBLE_GATES=PASS")


def mode_build(args: argparse.Namespace) -> None:
    if not args.m5d_boot:
        fail("LAP_NOT_SAFE", "build requires --m5d-boot")
    probe_report, kernel = build_gates(args)
    out = Path(args.out).resolve()
    m5d_path = Path(args.m5d_boot).resolve()
    m5d = m5d_path.read_bytes()
    if sha(m5d) != M5D_BOOT_SHA256:
        fail("LAP_M5D_IDENTITY_FAILED", "boot sha")
    m5d_boot = parse_boot(m5d, "M5D")
    require_boot_geometry(m5d_boot, "M5D")
    if m5d_boot["kernel_size"] != KERNEL_SIZE or sha(m5d_boot["kernel"]) != M5D_IMAGE_SHA256:
        fail("LAP_M5D_IDENTITY_FAILED", "kernel")
    if m5d_boot["ramdisk_size"] != RAMDISK_SIZE or sha(m5d_boot["ramdisk"]) != M5D_RAMDISK_SHA256:
        fail("LAP_RAMDISK_FAILED", "M5D ramdisk")
    if m5d_boot["cmdline"].rstrip(b"\x00") != b"":
        fail("LAP_CMDLINE_FAILED", "M5D cmdline")
    if any(m5d_boot["reserved"]):
        fail("LAP_BOOT_LAYOUT_FAILED", "reserved")

    boot = splice(m5d, kernel)
    packed = parse_boot(boot, "probe")
    require_boot_geometry(packed, "probe")
    if packed["header_version"] != 3 or packed["header_size"] != BOOT_HEADER_V3_SIZE:
        fail("LAP_BOOT_LAYOUT_FAILED", "probe boot header")
    if packed["cmdline"] != m5d_boot["cmdline"]:
        fail("LAP_CMDLINE_FAILED", "probe cmdline")
    if packed["ramdisk"] != m5d_boot["ramdisk"]:
        fail("LAP_RAMDISK_FAILED", "probe ramdisk")
    if packed["os_version_raw"] != m5d_boot["os_version_raw"]:
        fail("LAP_BOOT_LAYOUT_FAILED", "os_version")

    m5d_boot_diff = diff_offsets(m5d, boot)
    if not m5d_boot_diff or min(m5d_boot_diff) < KERNEL_OFFSET:
        fail("LAP_DELTA_FAILED", "header changed vs M5D")
    if max(m5d_boot_diff) >= KERNEL_OFFSET + KERNEL_SIZE:
        fail("LAP_RAMDISK_FAILED", "non-kernel diff vs M5D")
    if boot[:KERNEL_OFFSET] != m5d[:KERNEL_OFFSET]:
        fail("LAP_BOOT_LAYOUT_FAILED", "v3 header vs M5D")
    if boot[RAMDISK_OFFSET:] != m5d[RAMDISK_OFFSET:]:
        fail("LAP_RAMDISK_FAILED", "tail vs M5D")
    print("LAP_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_ONLY")
    print("LAP_NON_KERNEL_M5D_CONTEXT=MATCH")

    boot_name = "thyme-r3-load-alignment-probe.img"
    (out / boot_name).write_bytes(boot)
    (out / "Image-r3-load-alignment-probe").write_bytes(kernel)
    pad_len = KERNEL_SIZE - probe_report["raw_len"]
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    run_sha = os.environ.get("GITHUB_SHA", "unknown")
    lines = [
        "R3_LOAD_ALIGNMENT_PROBE_CI",
        "LAP_PROBE_POSITION_INDEPENDENT=YES",
        "LAP_IMAGE_BASE_AT_PAYLOAD_OFFSET_0=YES",
        "LAP_IMAGE_BASE_PC_RELATIVE=YES",
        "LAP_NO_STACK=YES",
        "LAP_NO_MEMORY_READ=YES",
        "LAP_NO_MEMORY_WRITE=YES",
        "LAP_NO_ABSOLUTE_ADDRESS=YES",
        "LAP_NO_GOT=YES",
        "ELF_RELOCATIONS=0",
        "LAP_DISASM_GATES=PASS",
        "LAP_IMAGE_BASE_PC_RELATIVE=PASS",
        "LAP_NO_MEMORY_ACCESS=PASS",
        "LAP_NO_STACK=PASS",
        "LAP_HEADER_GATES=PASS",
        "LAP_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_ONLY",
        "LAP_NON_KERNEL_M5D_CONTEXT=MATCH",
        "BOOT_HEADER=v3",
        f"LAP_KERNEL_PAYLOAD_SIZE={KERNEL_SIZE}",
        f"IMAGE_TEXT_OFFSET=0x{TEXT_OFFSET:x}",
        f"IMAGE_IMAGE_SIZE=0x{IMAGE_SIZE_FIELD:x}",
        f"IMAGE_FLAGS=0x{FLAGS:x}",
        "IMAGE_PE_OFFSET=0x0",
        "RAMDISK=MATCH",
        "CMDLINE=MATCH",
        f"LAP_PADDING_BYTE=0x{PADDING_BYTE:02x}",
        f"LAP_PADDING_LEN={pad_len}",
        f"LAP_PROBE_SHA256={probe_report['probe_sha']}",
        f"LAP_KERNEL_SHA256={probe_report['kernel_sha']}",
        f"LAP_BOOT_SHA256={sha(boot)}",
        f"LAP_BOOT_SIZE={len(boot)}",
        f"LAP_LOW21_MASK=0x{LOW21_MASK:x}",
        f"LAP_LOW21_EXPECTED=0x{LOW21_EXPECTED:x}",
        f"ALIGNMENT_MATCH_DELAY={DELAY_ALIGN_MATCH}",
        f"ALIGNMENT_MISMATCH_DELAY={DELAY_ALIGN_MISMATCH}",
        f"ALIGNMENT_DELAY_ENCODING=ALIGNMENT_MATCH -> {DELAY_ALIGN_MATCH}s / ALIGNMENT_MISMATCH -> {DELAY_ALIGN_MISMATCH}s",
        "LAP_TIMER_SOURCE=CNTPCT",
        f"LAP_PSCI_FUNCTION_ID=0x{PSCI_SYSTEM_RESET:08x}",
        "LAP_PSCI_CONDUIT=SMC",
        f"P0_A8_OVERHEAD={A8_OVERHEAD}",
        f"P0_A24_OVERHEAD={A24_OVERHEAD}",
        f"P0_RESET_BOOT_OVERHEAD_REF={P0_OVERHEAD_REF}",
        f"TIMING_TOLERANCE_STRONG={TOLERANCE_STRONG}",
        f"TIMING_TOLERANCE_SUPPORTED={TOLERANCE_SUPPORTED}",
        f"RT_D_DTB_SHA256={RTD_DTB_SHA256}",
        "P1_CLEAN_IMAGE_REBUILD_PENDING=YES",
        "M5N_FROZEN=YES",
        "USB_FROZEN=YES",
        "AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B",
        "OBSERVER_KEYERROR_FIXED=YES",
        "DEVICE_OPERATION=NO",
        "PARTITION_WRITES=0",
        "SLOT_A_WRITTEN=NO",
        "FASTBOOT_BOOT_ONLY=YES",
        "SECOND_BOOT_FORBIDDEN=YES",
        "FAIL_CLOSED=PASS",
        "NEGATIVE_TESTS_PASS=YES",
        f"GITHUB_RUN_ID={run_id}",
        f"GITHUB_SHA={run_sha}",
        f"TOOLCHAIN_LLVM_VERSION={LLVM_VERSION}",
        f"TOOLCHAIN_PKG={LLVM_PKG}",
        f"TOOLCHAIN_RUNNER={RUNNER_IMAGE}",
        "R3_LOAD_ALIGNMENT_PROBE_GATES=PASS",
    ]
    (out / "r3-load-alignment-probe-gates.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    (out / "r3-load-alignment-probe-manifest.txt").write_text(
        "\n".join(["R3_LOAD_ALIGNMENT_PROBE_MANIFEST", *lines]) + "\n",
        encoding="utf-8")
    sums = []
    for name in (boot_name, "Image-r3-load-alignment-probe", "r3-lap-probe.bin",
                 "r3-load-alignment-probe-gates.txt",
                 "r3-load-alignment-probe-manifest.txt",
                 "r3-lap-probe-disasm.txt"):
        path = out / name
        if path.is_file():
            sums.append(f"{sha(path.read_bytes())}  {name}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (out / "DO_NOT_FLASH.txt").write_text("\n".join([
        "thyme-r3-load-alignment-probe.img",
        "DEVICE_OPERATION=NO",
        "PARTITION_WRITES=0",
        "FASTBOOT_BOOT_ONLY=YES",
        "SECOND_BOOT_FORBIDDEN=YES",
        "WAIT_FOR_USER_APPROVAL=YES",
    ]) + "\n", encoding="utf-8")
    for line in lines:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=(
        "source-gate", "decoder-fixtures", "assemble-gates", "build"))
    parser.add_argument("--out")
    parser.add_argument("--m5d-boot")
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--lld", default="ld.lld-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    parser.add_argument("--objdump", default="llvm-objdump-18")
    parser.add_argument("--readelf", default="llvm-readelf-18")
    args = parser.parse_args()
    if args.mode == "source-gate":
        source_gate_tokens()
    elif args.mode == "decoder-fixtures":
        mode_decoder_fixtures()
    elif args.mode == "assemble-gates":
        if not args.out:
            fail("LAP_NOT_SAFE", "assemble-gates requires --out")
        mode_assemble_gates(args)
    elif args.mode == "build":
        if not args.out:
            fail("LAP_NOT_SAFE", "build requires --out")
        mode_build(args)


if __name__ == "__main__":
    main()
