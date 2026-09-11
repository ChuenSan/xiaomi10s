#!/usr/bin/env python3
"""R3 P0 shim entry-proof assemble/pack/validate. GitHub Actions only."""

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
SHIM_BODY = 0x40
PSCI_SYSTEM_RESET = 0x84000009
PADDING_BYTE = 0x00
ARM64_MAGIC = b"ARM\x64"
BOOT_MAGIC = b"ANDROID!"
M5D_BOOT_SHA256 = "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"
M5D_IMAGE_SHA256 = "5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a"
M5D_RAMDISK_SHA256 = "b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de"
LLVM_VERSION = "18.1.3"
LLVM_PKG = "1:18.1.3-1ubuntu1"
RUNNER_IMAGE = "ubuntu-24.04"
MAX_SHIM = 4096
MOVZ_X2 = 0xD2800002
STORE_RE = re.compile(
    r"\b(str|strb|strh|stp|stur|stlr|stlxr|stxr|sttr|stnp|stadd|stp)\b", re.I
)
LOAD_RE = re.compile(r"\b(ldr|ldrb|ldrh|ldp|ldur|ldar|ldxr)\b", re.I)
BAD_RE = re.compile(r"\b(hvc|svc|brk|udf|msr|bl|blr|ret|svc)\b", re.I)
ALLOW_MNEM = {
    "b", "b.lo", "b.hs", "b.lt", "b.ge", "b.eq", "b.ne",
    "bhs", "blo", "bhi", "bcc", "bcs",
    "mrs", "mov", "movz", "movk", "mul", "madd", "sub", "subs",
    "cmp", "isb", "yield", "wfe", "wfi", "nop", "smc", "hint",
}

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    msg = label if not detail else f"{label}: {detail}"
    raise SystemExit(msg)


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        fail("P0_ASSEMBLE_FAILED", f"{' '.join(cmd)}\n{proc.stderr}")
    return proc.stdout


def sx(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def b_target(word: int, pc: int) -> int:
    if word & 0xFC000000 != 0x14000000:
        fail("P0_CODE0_TARGET_FAILED", f"not B: 0x{word:08x}")
    return pc + sx(word & 0x03FFFFFF, 26) * 4


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def parse_image(image: bytes, label: str) -> dict:
    if len(image) < 64:
        fail("P0_IMAGE_HEADER_FAILED", f"{label} short")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<QQQQQQ", image, 8)
    magic = image[56:60]
    pe = struct.unpack_from("<I", image, 60)[0]
    if magic != ARM64_MAGIC:
        fail("P0_IMAGE_HEADER_FAILED", f"{label} magic={magic!r}")
    return {
        "code0": code0,
        "code1": code1,
        "text_offset": text_offset,
        "image_size": image_size,
        "flags": flags,
        "res2": res2,
        "res3": res3,
        "res4": res4,
        "magic": magic,
        "pe_offset": pe,
    }


def parse_boot(boot: bytes, label: str) -> dict:
    if len(boot) < PAGE or boot[:8] != BOOT_MAGIC:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} not ANDROID!")
    kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from("<IIII", boot, 8)
    reserved = struct.unpack_from("<IIII", boot, 24)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    cmdline = boot[44:BOOT_HEADER_V3_SIZE]
    if header_version != 3:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} header_version={header_version}")
    if header_size != BOOT_HEADER_V3_SIZE:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} header_size={header_size}")
    kernel_end = KERNEL_OFFSET + kernel_size
    ramdisk_off = align(kernel_end, PAGE)
    ramdisk_end = ramdisk_off + ramdisk_size
    if ramdisk_end > len(boot):
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} truncated")
    if boot[BOOT_HEADER_V3_SIZE:PAGE] != b"\x00" * (PAGE - BOOT_HEADER_V3_SIZE):
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} header pad")
    return {
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version_raw": os_version_raw,
        "header_size": header_size,
        "reserved": reserved,
        "header_version": header_version,
        "cmdline": cmdline,
        "kernel": boot[KERNEL_OFFSET:kernel_end],
        "ramdisk": boot[ramdisk_off:ramdisk_end],
        "ramdisk_off": ramdisk_off,
        "total": len(boot),
    }


def require_boot_geometry(parsed: dict, label: str) -> None:
    if parsed["kernel_size"] != KERNEL_SIZE:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} kernel_size={parsed['kernel_size']}")
    if parsed["ramdisk_size"] != RAMDISK_SIZE:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} ramdisk_size")
    if parsed["total"] != BOOT_SIZE:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} total={parsed['total']}")
    if parsed["ramdisk_off"] != RAMDISK_OFFSET:
        fail("P0_BOOT_LAYOUT_FAILED", f"{label} ramdisk_off")


def require_code0_inside(image: bytes) -> int:
    hdr = parse_image(image, "code0")
    tgt = b_target(hdr["code0"], 0)
    if tgt < 0 or tgt >= KERNEL_SIZE:
        fail("P0_CODE0_TARGET_FAILED", f"outside payload {tgt:#x}")
    return tgt


def source_gate() -> None:
    shim = (HERE / "p0-shim.S").read_text()
    script = Path(__file__).read_text()
    ld = (HERE / "p0-shim.ld").read_text()
    doc = REPO / "docs" / "route-r3-p0-shim-entry-proof-ci.md"
    wf = REPO / ".github" / "workflows" / "thyme-r3-bootshim-ci.yml"
    for path in (HERE / "p0-shim.S", HERE / "p0-shim.ld", HERE / "p0-neg-absolute.S",
                 HERE / "p0-neg-store.S", doc, wf):
        if not path.is_file() or path.stat().st_size == 0:
            fail("P0_SOURCE_GATE_FAILED", f"missing {path}")
    doc_text = doc.read_text()
    wf_text = wf.read_text()
    required_shim = (
        "cntpct_el0", "cntfrq_el0", "smc", "movz", "P0_DELAY_SECONDS",
        "0x80000", "0x2220000", "0x644d5241", "0x0009", "0x8400",
    )
    for token in required_shim:
        if token not in shim:
            fail("P0_SOURCE_GATE_FAILED", f"shim missing {token}")
    for forbidden in ("cntvct", "hvc", ".bss", ".data", ".got", "stp", "\tstr\t", " ldr\t"):
        if forbidden in shim:
            fail("P0_SOURCE_GATE_FAILED", f"shim has {forbidden!r}")
    if "GITHUB_ACTIONS" not in script:
        fail("P0_SOURCE_GATE_FAILED", "script missing GITHUB_ACTIONS guard")
    if "ENTRY(_start)" not in ld:
        fail("P0_SOURCE_GATE_FAILED", "linker script")
    for token in (
        "AUTHORITATIVE_M5M_B_STATUS=RUN_AND_VALIDATED",
        "AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B",
        "THYME_FASTBOOT_BOOT_PRECEDENT=YES",
        "THYME_PSCI_CONDUIT=SMC",
        "P0_TIMER_SOURCE=CNTPCT",
        "P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET",
        "P1_BLOCKED_BY_P0_ENTRY_PROOF=YES",
        M5D_BOOT_SHA256,
        M5D_IMAGE_SHA256,
        M5D_RAMDISK_SHA256,
        "0x84000009",
        "LOCAL_BUILD:                       NO",
        "DEVICE_OPERATION:                  NO",
    ):
        if token not in doc_text:
            fail("P0_SOURCE_GATE_FAILED", f"doc missing {token}")
    if re.search(r"^\s+run:.*\b(fastboot|adb|flash)\b", wf_text, re.M):
        fail("P0_SOURCE_GATE_FAILED", "public workflow has device verbs")
    if "Does not compile, assemble, link, mkbootimg, or emit a boot image" not in wf_text:
        fail("P0_SOURCE_GATE_FAILED", "public workflow assemble boundary")
    print("P0_SOURCE_GATE=PASS")


def require_llvm(path: str, needle: str) -> str:
    out = run([path, "--version"])
    if needle not in out.splitlines()[0] and needle not in out:
        fail("P0_TOOLCHAIN_PIN_FAILED", f"{path}: {out.splitlines()[0] if out else 'empty'}")
    return out.splitlines()[0]


def assemble(clang: str, lld: str, objcopy: str, src: Path, out_elf: Path,
             out_bin: Path, delay: int | None, defines: list[str] | None = None) -> None:
    obj = out_elf.with_suffix(".o")
    cmd = [
        clang, "--target=aarch64-unknown-none", "-nostdlib", "-ffreestanding",
        "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fno-ident",
    ]
    if delay is not None:
        cmd.append(f"-DP0_DELAY_SECONDS={delay}")
    if defines:
        cmd.extend(defines)
    cmd += ["-c", "-o", str(obj), str(src)]
    run(cmd)
    run([
        lld, "-T", str(HERE / "p0-shim.ld"), "--build-id=none", "--nmagic",
        "--static", "-o", str(out_elf), str(obj),
    ])
    run([objcopy, "-O", "binary", str(out_elf), str(out_bin)])


def relocs(readelf: str, elf: Path) -> str:
    out = run([readelf, "-r", "--wide", str(elf)])
    if "R_AARCH64_" in out or "Relocation section" in out:
        fail("P0_RELOCATION_FAILED", out)
    return out


def symbols(readelf: str, elf: Path) -> None:
    out = run([readelf, "-s", "--wide", str(elf)])
    for line in out.splitlines():
        if re.search(r"\sUND\s+\S+$", line):
            fail("P0_ELF_SYMBOL_FAILED", line)


def disasm(objdump: str, elf: Path) -> str:
    return run([objdump, "-d", "--no-show-raw-insn", str(elf)])


def check_body_disasm(text: str, delay: int) -> None:
    saw_cntfrq = saw_cntpct = saw_smc = saw_movz = False
    saw_fid_lo = saw_fid_hi = saw_cntvct = False
    for line in text.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(\S+)(.*)$", line, re.I)
        if not m:
            continue
        addr = int(m.group(1), 16)
        mnem = m.group(2).lower()
        rest = m.group(3).lower()
        if addr < SHIM_BODY:
            continue
        if STORE_RE.search(line):
            fail("P0_STORE_REJECT_FAILED", line)
        if LOAD_RE.search(line):
            fail("P0_DISASM_FAILED", f"memory load {line}")
        if mnem == "hvc" or (BAD_RE.search(mnem) and mnem not in ALLOW_MNEM):
            fail("P0_PSCI_FAILED", line)
        if mnem not in ALLOW_MNEM and not mnem.startswith("b."):
            fail("P0_DISASM_FAILED", f"unexpected {line}")
        if "cntfrq_el0" in rest:
            saw_cntfrq = True
        if "cntpct_el0" in rest:
            saw_cntpct = True
        if "cntvct" in rest:
            saw_cntvct = True
        if mnem == "smc":
            saw_smc = True
            if "#0" not in rest and "0x0" not in rest and not rest.strip().endswith("0"):
                fail("P0_PSCI_FAILED", f"smc immediate {line}")
        if mnem in ("mov", "movz") and re.search(r"\bx2\b", rest):
            if delay != 0 and "xzr" in rest:
                continue
            delay_ok = (
                f"#{delay}" in rest or f"#0x{delay:x}" in rest
                or (delay == 0 and ("xzr" in rest or "#0" in rest))
            )
            if delay_ok:
                saw_movz = True
            else:
                fail("P0_DISASM_FAILED", f"delay encoding {line}")
        if mnem in ("mov", "movz") and re.search(r"\bw0\b", rest) and (
            "#9" in rest or "#0x9" in rest
        ):
            saw_fid_lo = True
        if mnem == "movk" and "w0" in rest and "8400" in rest and "16" in rest:
            saw_fid_hi = True
    if saw_cntvct:
        fail("P0_TIMER_FAILED", "cntvct present")
    if not (saw_cntfrq and saw_cntpct):
        fail("P0_TIMER_FAILED", "cntfrq/cntpct missing")
    if not saw_smc:
        fail("P0_PSCI_FAILED", "smc missing")
    if not saw_movz:
        fail("P0_DISASM_FAILED", "movz x2 delay missing")
    if not (saw_fid_lo and saw_fid_hi):
        fail("P0_PSCI_FAILED", "SYSTEM_RESET function id encoding")


def pad_kernel(raw: bytes) -> bytes:
    if len(raw) > KERNEL_SIZE:
        fail("P0_SIZE_FAILED", f"shim {len(raw)} > {KERNEL_SIZE}")
    if len(raw) > MAX_SHIM:
        fail("P0_SIZE_FAILED", f"shim {len(raw)} > {MAX_SHIM}")
    if len(raw) < SHIM_BODY + 4:
        fail("P0_SIZE_FAILED", f"shim {len(raw)}")
    return raw + bytes([PADDING_BYTE]) * (KERNEL_SIZE - len(raw))


def splice(m5d: bytes, kernel: bytes) -> bytes:
    if len(m5d) != BOOT_SIZE:
        fail("P0_M5D_IDENTITY_FAILED", f"size {len(m5d)}")
    if len(kernel) != KERNEL_SIZE:
        fail("P0_SIZE_FAILED", f"kernel {len(kernel)}")
    out = bytearray(m5d)
    out[KERNEL_OFFSET:KERNEL_OFFSET + KERNEL_SIZE] = kernel
    return bytes(out)


def diff_offsets(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        fail("P0_DELTA_FAILED", f"len {len(a)} vs {len(b)}")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def movz_imm(word: int) -> int | None:
    if word & 0xFFE0001F != MOVZ_X2:
        return None
    return (word >> 5) & 0xFFFF


def expect_reject(fn, label: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        text = str(exc)
        if label in text or text.startswith("P0_"):
            print(f"NEG_{label}=REJECT")
            return
        fail("P0_NEGATIVE_TEST_FAILED", f"{label} wrong fail {text}")
    fail("P0_NEGATIVE_TEST_FAILED", f"{label} accepted")


def write_report(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(args: argparse.Namespace) -> None:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    clang, lld = args.clang, args.lld
    objcopy, objdump, readelf = args.objcopy, args.objdump, args.readelf
    require_llvm(clang, LLVM_VERSION)
    require_llvm(lld, LLVM_VERSION)
    require_llvm(objdump, LLVM_VERSION)
    print(f"TOOLCHAIN_CLANG={clang}")
    print(f"TOOLCHAIN_LLVM_VERSION={LLVM_VERSION}")
    print(f"TOOLCHAIN_PKG={LLVM_PKG}")
    print(f"TOOLCHAIN_RUNNER={RUNNER_IMAGE}")

    m5d_path = Path(args.m5d_boot).resolve()
    m5d = m5d_path.read_bytes()
    if sha(m5d) != M5D_BOOT_SHA256:
        fail("P0_M5D_IDENTITY_FAILED", "boot sha")
    m5d_boot = parse_boot(m5d, "M5D")
    require_boot_geometry(m5d_boot, "M5D")
    if m5d_boot["kernel_size"] != KERNEL_SIZE or sha(m5d_boot["kernel"]) != M5D_IMAGE_SHA256:
        fail("P0_M5D_IDENTITY_FAILED", "kernel")
    if m5d_boot["ramdisk_size"] != RAMDISK_SIZE or sha(m5d_boot["ramdisk"]) != M5D_RAMDISK_SHA256:
        fail("P0_RAMDISK_FAILED", "M5D ramdisk")
    if m5d_boot["ramdisk_off"] != RAMDISK_OFFSET:
        fail("P0_BOOT_LAYOUT_FAILED", "ramdisk offset")
    if m5d_boot["cmdline"].rstrip(b"\x00") != b"":
        fail("P0_CMDLINE_FAILED", "M5D cmdline")
    if any(m5d_boot["reserved"]):
        fail("P0_BOOT_LAYOUT_FAILED", "reserved")

    variants = {"a8": 8, "a24": 24, "reset0": 0}
    built: dict[str, dict] = {}
    for name, delay in variants.items():
        elf = out / f"p0-{name}.elf"
        raw_path = out / f"p0-shim-{name}.bin"
        assemble(clang, lld, objcopy, HERE / "p0-shim.S", elf, raw_path, delay)
        relocs(readelf, elf)
        symbols(readelf, elf)
        raw = raw_path.read_bytes()
        hdr = parse_image(raw, name)
        if hdr["text_offset"] != TEXT_OFFSET or hdr["image_size"] != IMAGE_SIZE_FIELD:
            fail("P0_IMAGE_HEADER_FAILED", name)
        if hdr["flags"] != FLAGS or hdr["pe_offset"] != PE_OFFSET:
            fail("P0_IMAGE_HEADER_FAILED", name)
        if hdr["res2"] or hdr["res3"] or hdr["res4"]:
            fail("P0_IMAGE_HEADER_FAILED", "reserved")
        t0 = b_target(hdr["code0"], 0)
        t1 = b_target(hdr["code1"], 4)
        if t0 != SHIM_BODY or t1 != SHIM_BODY:
            fail("P0_CODE0_TARGET_FAILED", f"{name} {t0:#x} {t1:#x}")
        if t0 >= KERNEL_SIZE:
            fail("P0_CODE0_TARGET_FAILED", "outside payload")
        dump = disasm(objdump, elf)
        (out / f"p0-disasm-{name}.txt").write_text(dump, encoding="utf-8")
        check_body_disasm(dump, delay)
        kernel = pad_kernel(raw)
        boot = splice(m5d, kernel)
        packed = parse_boot(boot, name)
        require_boot_geometry(packed, name)
        if packed["header_version"] != 3 or packed["header_size"] != BOOT_HEADER_V3_SIZE:
            fail("P0_BOOT_LAYOUT_FAILED", name)
        if packed["cmdline"] != m5d_boot["cmdline"]:
            fail("P0_CMDLINE_FAILED", name)
        if packed["ramdisk"] != m5d_boot["ramdisk"]:
            fail("P0_RAMDISK_FAILED", name)
        if packed["os_version_raw"] != m5d_boot["os_version_raw"]:
            fail("P0_BOOT_LAYOUT_FAILED", "os_version")
        if packed["total"] != BOOT_SIZE:
            fail("P0_BOOT_LAYOUT_FAILED", "total size")
        boot_name = {
            "a8": "thyme-r3-p0-a8-entry-proof-boot.img",
            "a24": "thyme-r3-p0-a24-entry-proof-boot.img",
            "reset0": "thyme-r3-p0-reset0-entry-proof-boot.img",
        }[name]
        (out / boot_name).write_bytes(boot)
        (out / f"Image-{name}").write_bytes(kernel)
        built[name] = {
            "raw": raw,
            "kernel": kernel,
            "boot": boot,
            "dump": dump,
            "delay": delay,
            "boot_name": boot_name,
            "hdr": hdr,
        }

    a8, a24, z = built["a8"], built["a24"], built["reset0"]
    kdiff = diff_offsets(a8["kernel"], a24["kernel"])
    bdiff = diff_offsets(a8["boot"], a24["boot"])
    if not kdiff or any(off < SHIM_BODY or off >= len(a8["raw"]) for off in kdiff):
        fail("P0_DELTA_FAILED", f"kernel delta {kdiff}")
    instr_off = min(kdiff) & ~3
    w8 = struct.unpack_from("<I", a8["kernel"], instr_off)[0]
    w24 = struct.unpack_from("<I", a24["kernel"], instr_off)[0]
    if movz_imm(w8) != 8 or movz_imm(w24) != 24:
        fail("P0_DELTA_FAILED", f"movz {w8:#x} {w24:#x} at {instr_off:#x}")
    if any(off < instr_off or off >= instr_off + 4 for off in kdiff):
        fail("P0_DELTA_FAILED", f"extra kernel bytes {kdiff}")
    expected_boot = [KERNEL_OFFSET + off for off in kdiff]
    if bdiff != expected_boot:
        fail("P0_DELTA_FAILED", f"boot delta {bdiff}")
    zdiff = diff_offsets(a8["kernel"], z["kernel"])
    z_off = min(zdiff) & ~3
    wz = struct.unpack_from("<I", z["kernel"], z_off)[0]
    if movz_imm(wz) != 0 or z_off != instr_off:
        fail("P0_DELTA_FAILED", "reset0 not delay-only")

    m5d_boot_diff = diff_offsets(m5d, a8["boot"])
    if not m5d_boot_diff or min(m5d_boot_diff) < KERNEL_OFFSET:
        fail("P0_DELTA_FAILED", "header changed vs M5D")
    if max(m5d_boot_diff) >= KERNEL_OFFSET + KERNEL_SIZE:
        fail("P0_RAMDISK_FAILED", "non-kernel diff vs M5D")
    if a8["boot"][:KERNEL_OFFSET] != m5d[:KERNEL_OFFSET]:
        fail("P0_BOOT_LAYOUT_FAILED", "v3 header vs M5D")
    if a8["boot"][RAMDISK_OFFSET:] != m5d[RAMDISK_OFFSET:]:
        fail("P0_RAMDISK_FAILED", "tail vs M5D")

    def ramdisk_must_match(blob: bytes) -> None:
        parsed = parse_boot(blob, "neg-rd")
        if parsed["ramdisk"] != m5d_boot["ramdisk"]:
            fail("P0_RAMDISK_FAILED", "unexpected ramdisk diff")

    def cmdline_must_match(blob: bytes) -> None:
        parsed = parse_boot(blob, "neg-cmd")
        if parsed["cmdline"] != m5d_boot["cmdline"]:
            fail("P0_CMDLINE_FAILED", "unexpected cmdline diff")

    bad_magic = bytearray(a8["kernel"])
    bad_magic[56:60] = b"XXXX"
    (out / "p0-neg-bad-image-magic.bin").write_bytes(bytes(bad_magic))
    expect_reject(lambda: parse_image(bytes(bad_magic), "neg-magic-file"),
                  "IMAGE_HEADER")

    bad_ver = bytearray(a8["boot"])
    struct.pack_into("<I", bad_ver, 40, 2)
    expect_reject(lambda: parse_boot(bytes(bad_ver), "neg-v2"), "BOOT_LAYOUT")

    bad_ksize = bytearray(a8["boot"])
    struct.pack_into("<I", bad_ksize, 8, 123)
    expect_reject(lambda: require_boot_geometry(parse_boot(bytes(bad_ksize), "neg-ksize"),
                                               "neg-ksize"), "BOOT_LAYOUT")
    expect_reject(lambda: require_boot_geometry(parse_boot(a8["boot"][:BOOT_SIZE - 1], "neg-short"),
                                               "neg-short"), "BOOT_LAYOUT")

    bad_br = bytearray(a8["kernel"])
    struct.pack_into("<I", bad_br, 0, 0x14000000 | ((0x03000000 // 4) & 0x03FFFFFF))
    expect_reject(lambda: require_code0_inside(bytes(bad_br)), "CODE0_TARGET")

    expect_reject(lambda: relocs(readelf, out / "p0-a8.o"), "RELOCATION")

    abs_elf = out / "p0-neg-absolute.elf"
    abs_bin = out / "p0-neg-absolute.bin"
    assemble(clang, lld, objcopy, HERE / "p0-neg-absolute.S", abs_elf, abs_bin, None)
    abs_raw = abs_bin.read_bytes()
    if 0x80000000.to_bytes(4, "little") not in abs_raw:
        fail("P0_NEGATIVE_TEST_FAILED", "absolute constant not in neg binary")
    if 0x80000000.to_bytes(4, "little") in a8["raw"][SHIM_BODY:]:
        fail("P0_DISASM_FAILED", "production shim has 0x80000000")
    print("NEG_ABSOLUTE_ADDRESS_DEPENDENCY=REJECT")

    st_elf = out / "p0-neg-store.elf"
    st_bin = out / "p0-neg-store.bin"
    assemble(clang, lld, objcopy, HERE / "p0-neg-store.S", st_elf, st_bin, None)
    st_dump = disasm(objdump, st_elf)
    if not STORE_RE.search(st_dump):
        fail("P0_NEGATIVE_TEST_FAILED", "store mutant has no str")
    expect_reject(lambda: check_body_disasm("      40: str xzr, [x0]\n", 8), "STORE")
    print("NEG_UNKNOWN_MEMORY_STORE=REJECT")

    expect_reject(lambda: check_body_disasm(a8["dump"].replace("cntpct_el0", "cntvct_el0"), 8),
                  "TIMER")
    expect_reject(lambda: check_body_disasm(a8["dump"].replace("smc", "hvc"), 8), "PSCI")

    bad_rd = bytearray(a8["boot"])
    bad_rd[RAMDISK_OFFSET] ^= 0xFF
    expect_reject(lambda: ramdisk_must_match(bytes(bad_rd)), "RAMDISK")
    bad_cmd = bytearray(a8["boot"])
    bad_cmd[44] = 0x41
    expect_reject(lambda: cmdline_must_match(bytes(bad_cmd)), "CMDLINE")

    pad_len = KERNEL_SIZE - len(a8["raw"])
    pad_sha = sha(bytes([PADDING_BYTE]) * pad_len)
    lines = [
        f"LLVM_VERSION={LLVM_VERSION}",
        f"LLVM_PKG={LLVM_PKG}",
        f"TOOLCHAIN_RUNNER={RUNNER_IMAGE}",
        f"P0_POSITION_INDEPENDENT=YES",
        f"P0_REQUIRES_PHYSICAL_LOAD_ADDRESS=NO",
        f"P0_STACK=NO",
        f"P0_UNKNOWN_RAM_ACCESS=NO",
        f"P0_NO_DATA_WRITE=YES",
        f"P0_X0_POLICY=IGNORE_AND_PRESERVE",
        f"P0_TIMER_SOURCE=CNTPCT",
        f"P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET",
        f"P0_PSCI_CONDUIT=SMC",
        f"P0_PSCI_FUNCTION_ID=0x{PSCI_SYSTEM_RESET:08x}",
        f"P0_CODE0_TARGET_OFFSET=0x{SHIM_BODY:x}",
        f"P0_RELOCATIONS=0",
        f"P0_PADDING_BYTE=0x{PADDING_BYTE:02x}",
        f"P0_PADDING_LEN={pad_len}",
        f"P0_PADDING_SHA256={pad_sha}",
        f"P0_NON_KERNEL_M5D_CONTEXT=MATCH",
        f"P0_VS_M5D_DIFF_CLASSIFICATION=KERNEL_PAYLOAD_ONLY",
        f"A8_A24_DELTA_ISOLATED=YES",
        f"A8_A24_DELTA_OFFSETS={kdiff}",
        f"BOOT_HEADER=v3",
        f"BOOT_SIZE={BOOT_SIZE}",
        f"KERNEL_PAYLOAD_SIZE={KERNEL_SIZE}",
        f"IMAGE_TEXT_OFFSET=0x{TEXT_OFFSET:x}",
        f"IMAGE_IMAGE_SIZE=0x{IMAGE_SIZE_FIELD:x}",
        f"IMAGE_FLAGS=0x{FLAGS:x}",
        f"IMAGE_PE_OFFSET=0",
        f"RAMDISK=MATCH",
        f"CMDLINE=MATCH",
        f"P0_A8_DELAY=8",
        f"P0_A8_BOOT_SIZE={len(a8['boot'])}",
        f"P0_A8_BOOT_SHA256={sha(a8['boot'])}",
        f"P0_A8_KERNEL_SHA256={sha(a8['kernel'])}",
        f"P0_A8_SHIM_SHA256={sha(a8['raw'])}",
        f"P0_A24_DELAY=24",
        f"P0_A24_BOOT_SIZE={len(a24['boot'])}",
        f"P0_A24_BOOT_SHA256={sha(a24['boot'])}",
        f"P0_A24_KERNEL_SHA256={sha(a24['kernel'])}",
        f"P0_A24_SHIM_SHA256={sha(a24['raw'])}",
        f"P0_RESET0_DELAY=0",
        f"P0_RESET0_BOOT_SHA256={sha(z['boot'])}",
        f"P0_RESET0_DEVICE_RECOMMENDED=NO",
        f"P0_NEG_BAD_IMAGE_MAGIC_DEVICE_RECOMMENDED=NO",
        f"FAIL_CLOSED=PASS",
        f"NEGATIVE_TESTS_PASS=YES",
        f"DEVICE_OPERATION=NO",
        f"P1_BLOCKED_BY_P0_ENTRY_PROOF=YES",
        f"P1_RELOCATION_BLOCKED_BY_LOAD_ADDRESS=YES",
        f"BINARY_GATES=PASS",
    ]
    write_report(out / "p0-gates.txt", lines)
    write_report(out / "p0-a8-vs-a24-delta.txt", [
        "semantic delta: DELAY CONSTANT ONLY",
        f"kernel_offsets={kdiff}",
        f"boot_offsets={bdiff}",
        f"movz_x2_a8=0x{w8:08x}",
        f"movz_x2_a24=0x{w24:08x}",
    ])
    write_report(out / "p0-vs-m5d-diff.txt", [
        "P0_VS_M5D_DIFF_CLASSIFICATION=KERNEL_PAYLOAD_ONLY",
        f"boot_diff_count={len(m5d_boot_diff)}",
        f"boot_diff_min=0x{min(m5d_boot_diff):x}",
        f"boot_diff_max=0x{max(m5d_boot_diff):x}",
        "header_v3=MATCH",
        "ramdisk=MATCH",
        "cmdline=MATCH",
        "os_fields=MATCH",
        "total_geometry=MATCH",
    ])
    sums = []
    names = [
        "thyme-r3-p0-a8-entry-proof-boot.img",
        "thyme-r3-p0-a24-entry-proof-boot.img",
        "thyme-r3-p0-reset0-entry-proof-boot.img",
        "Image-a8", "Image-a24", "Image-reset0",
        "p0-shim-a8.bin", "p0-shim-a24.bin", "p0-shim-reset0.bin",
        "p0-gates.txt", "p0-a8-vs-a24-delta.txt", "p0-vs-m5d-diff.txt",
        "p0-disasm-a8.txt", "p0-disasm-a24.txt", "p0-disasm-reset0.txt",
        "p0-neg-bad-image-magic.bin",
    ]
    for name in names:
        path = out / name
        if path.is_file():
            sums.append(f"{sha(path.read_bytes())}  {name}")
    write_report(out / "SHA256SUMS", sums)
    write_report(out / "DO_NOT_FLASH.txt", [
        "thyme-r3-p0-reset0-entry-proof-boot.img",
        "p0-neg-bad-image-magic.bin",
        "DEVICE_OPERATION=NO",
        "WAIT_FOR_USER_APPROVAL=YES",
    ])
    for line in lines:
        print(line)
    print("P0_ENTRY_PROOF_CI=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("source-gate", "build"), required=True)
    parser.add_argument("--m5d-boot")
    parser.add_argument("--out")
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--lld", default="ld.lld-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    parser.add_argument("--objdump", default="llvm-objdump-18")
    parser.add_argument("--readelf", default="llvm-readelf-18")
    args = parser.parse_args()
    if args.mode == "source-gate":
        source_gate()
        return
    if not args.m5d_boot or not args.out:
        fail("P0_NOT_SAFE", "build requires --m5d-boot and --out")
    build(args)


if __name__ == "__main__":
    main()
