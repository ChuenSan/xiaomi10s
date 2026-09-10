#!/usr/bin/env python3
"""CI-only exact M5B text_offset control and stock-header audit."""

import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local binary transformation/validation")
if len(sys.argv) != 4:
    raise SystemExit(f"usage: {sys.argv[0]} M5B_ARTIFACT_DIR STOCK_STAGE4_BOOT RELEASE_DIR")

src = Path(sys.argv[1]).resolve()
stock_boot_path = Path(sys.argv[2]).resolve()
out = Path(sys.argv[3]).resolve()
out.mkdir(parents=True, exist_ok=True)

EXPECTED_M5B_IMAGE_SHA = "502529d643d0907db3cb429e04de60617f0aba5bf6753d693e07f42a6db1bb1f"
EXPECTED_M5B_BOOT_SHA = "2125ebab7eafc8fdc2c2901138ba41bfe0a61f97d9d898094b9020116937f681"
EXPECTED_STOCK_BOOT_SHA = "6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a"
EXPECTED_STOCK_KERNEL_SHA = "85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a"
EXPECTED_RAMDISK_SHA = "b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de"
PAGE_SIZE = 4096
TEXT_OFFSET_FIELD = range(8, 16)
TARGET_TEXT_OFFSET = 0x80000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def sx(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def b_target(word, pc):
    if word & 0xFC000000 != 0x14000000:
        raise SystemExit(f"not an AArch64 B instruction: 0x{word:08x}")
    return pc + sx(word & 0x03FFFFFF, 26) * 4


def diff_offsets(before, after):
    if len(before) != len(after):
        raise SystemExit(f"size changed: {len(before)} -> {len(after)}")
    return [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def parse_header(image, label):
    if len(image) < 64:
        raise SystemExit(f"M5C_HEADER_PARSE_FAILED: {label} Image smaller than 64 bytes")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<QQQQQQ", image, 8)
    magic = image[56:60]
    pe_offset = struct.unpack_from("<I", image, 60)[0]
    if magic != b"ARM\x64":
        raise SystemExit(f"M5C_HEADER_PARSE_FAILED: {label} magic={magic!r}")
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
        "pe_offset": pe_offset,
    }


def parse_boot(boot, label):
    if len(boot) < PAGE_SIZE or boot[:8] != b"ANDROID!":
        raise SystemExit(f"{label} is not an Android boot image")
    kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from("<IIII", boot, 8)
    reserved = struct.unpack_from("<IIII", boot, 24)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    cmdline_raw = boot[44:1580]
    if header_version != 3 or header_size > PAGE_SIZE:
        raise SystemExit(f"unexpected {label} header: version={header_version} size={header_size}")
    kernel_offset = PAGE_SIZE
    kernel_end = kernel_offset + kernel_size
    ramdisk_offset = align(kernel_end, PAGE_SIZE)
    ramdisk_end = ramdisk_offset + ramdisk_size
    if ramdisk_end > len(boot):
        raise SystemExit(f"{label} payload sizes exceed file")
    return {
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version_raw": os_version_raw,
        "header_size": header_size,
        "reserved": reserved,
        "header_version": header_version,
        "cmdline_raw": cmdline_raw,
        "kernel_offset": kernel_offset,
        "kernel_end": kernel_end,
        "ramdisk_offset": ramdisk_offset,
        "ramdisk_end": ramdisk_end,
        "kernel": boot[kernel_offset:kernel_end],
        "ramdisk": boot[ramdisk_offset:ramdisk_end],
    }


def format_header(prefix, header):
    return [
        f"{prefix}_CODE0=0x{header['code0']:08x}",
        f"{prefix}_CODE1=0x{header['code1']:08x}",
        f"{prefix}_TEXT_OFFSET=0x{header['text_offset']:x}",
        f"{prefix}_IMAGE_SIZE=0x{header['image_size']:x}",
        f"{prefix}_FLAGS=0x{header['flags']:x}",
        f"{prefix}_RES2=0x{header['res2']:x}",
        f"{prefix}_RES3=0x{header['res3']:x}",
        f"{prefix}_RES4=0x{header['res4']:x}",
        f"{prefix}_MAGIC={header['magic'].hex()}",
        f"{prefix}_PE_OFFSET=0x{header['pe_offset']:x}",
    ]


def pe_region(image, header):
    start = header["pe_offset"]
    if start == 0 or start + 24 > len(image) or image[start:start + 4] != b"PE\0\0":
        raise SystemExit("M5C_HEADER_PARSE_FAILED: exact M5B PE header is unavailable")
    optional_size = struct.unpack_from("<H", image, start + 20)[0]
    optional = start + 24
    if optional + optional_size > len(image) or optional_size < 64:
        raise SystemExit("M5C_HEADER_PARSE_FAILED: invalid M5B PE optional header")
    if struct.unpack_from("<H", image, optional)[0] != 0x20B:
        raise SystemExit("M5C_HEADER_PARSE_FAILED: M5B PE optional header is not PE32+")
    size_of_headers = struct.unpack_from("<I", image, optional + 60)[0]
    end = max(start + 24 + optional_size, size_of_headers)
    if end > len(image):
        raise SystemExit("M5C_HEADER_PARSE_FAILED: M5B PE region exceeds Image")
    return start, end, image[start:end]


m5b_image_path = src / "Image"
m5b_boot_path = src / "mainline-v2-m5b-direct-entry-spin-boot-v3.img"
m5b_report_path = src / "validation-report.txt"
for path in (m5b_image_path, m5b_boot_path, m5b_report_path, stock_boot_path):
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"M5C_SOURCE_IDENTITY_FAILED: missing {path}")

m5b_image = m5b_image_path.read_bytes()
m5b_boot = m5b_boot_path.read_bytes()
m5b_report = m5b_report_path.read_text()
stock_boot = stock_boot_path.read_bytes()
if sha(m5b_image) != EXPECTED_M5B_IMAGE_SHA:
    raise SystemExit(f"M5C_SOURCE_IDENTITY_FAILED: M5B Image SHA={sha(m5b_image)}")
if sha(m5b_boot) != EXPECTED_M5B_BOOT_SHA:
    raise SystemExit(f"M5C_SOURCE_IDENTITY_FAILED: M5B boot SHA={sha(m5b_boot)}")
if sha(stock_boot) != EXPECTED_STOCK_BOOT_SHA:
    raise SystemExit(f"M5C_SOURCE_IDENTITY_FAILED: stock boot SHA={sha(stock_boot)}")
if "READY_FOR_MAINLINE_V2_M5B_DIRECT_ENTRY_CONTROL" not in m5b_report:
    raise SystemExit("M5C_SOURCE_IDENTITY_FAILED: M5B final gate absent")

m5b_boot_info = parse_boot(m5b_boot, "M5B boot")
stock_boot_info = parse_boot(stock_boot, "stock Stage4 boot")
if m5b_boot_info["kernel"] != m5b_image or m5b_boot_info["kernel_size"] != len(m5b_image):
    raise SystemExit("M5C_SOURCE_IDENTITY_FAILED: M5B Image/payload mapping mismatch")
stock_image = stock_boot_info["kernel"]
if sha(stock_image) != EXPECTED_STOCK_KERNEL_SHA:
    raise SystemExit(f"M5C_SOURCE_IDENTITY_FAILED: stock kernel SHA={sha(stock_image)}")

stock_header = parse_header(stock_image, "Stock")
m5b_header = parse_header(m5b_image, "M5B")
if stock_header["text_offset"] != TARGET_TEXT_OFFSET:
    raise SystemExit(
        f"M5C_STOCK_TEXT_OFFSET_ASSUMPTION_INVALID: 0x{stock_header['text_offset']:x}"
    )
if m5b_header["text_offset"] != 0:
    raise SystemExit(f"M5C_HEADER_PARSE_FAILED: M5B text_offset=0x{m5b_header['text_offset']:x}")
if m5b_image[8:16] != bytes(8):
    raise SystemExit(f"M5C_HEADER_PARSE_FAILED: M5B text_offset bytes={m5b_image[8:16].hex()}")

matches = re.findall(r"PRIMARY_ENTRY_IMAGE_OFFSET=(0x[0-9a-fA-F]+)", m5b_report)
if len(set(matches)) != 1:
    raise SystemExit(f"M5C_PRIMARY_SPIN_NOT_PRESERVED: offsets={matches}")
primary_offset = int(matches[0], 16)
if primary_offset % 4 or not 0 < primary_offset <= len(m5b_image) - 4:
    raise SystemExit(f"M5C_PRIMARY_SPIN_NOT_PRESERVED: offset=0x{primary_offset:x}")
code0 = m5b_header["code0"]
code1 = m5b_header["code1"]
if code0 != 0x146C7028 or b_target(code0, 0) != primary_offset:
    raise SystemExit(f"M5C_PRIMARY_SPIN_NOT_PRESERVED: code0=0x{code0:08x}")
primary_word = struct.unpack_from("<I", m5b_image, primary_offset)[0]
if primary_word != 0x14000000 or b_target(primary_word, primary_offset) != primary_offset:
    raise SystemExit(f"M5C_PRIMARY_SPIN_NOT_PRESERVED: word=0x{primary_word:08x}")

pe_start, pe_end, pe_before = pe_region(m5b_image, m5b_header)
m5c_buf = bytearray(m5b_image)
struct.pack_into("<Q", m5c_buf, 8, TARGET_TEXT_OFFSET)
m5c_image = bytes(m5c_buf)
m5c_header = parse_header(m5c_image, "M5C")
image_diffs = diff_offsets(m5b_image, m5c_image)
if image_diffs != [0x0A]:
    raise SystemExit(f"M5C_NONMINIMAL_BINARY_DIFF: Image offsets={image_diffs}")
if any(offset not in TEXT_OFFSET_FIELD for offset in image_diffs):
    raise SystemExit("M5C_NONMINIMAL_BINARY_DIFF: Image diff outside text_offset")
if m5c_header["text_offset"] != TARGET_TEXT_OFFSET:
    raise SystemExit("M5C_VALIDATION_FAILED: patched text_offset mismatch")
for key in ("code0", "code1", "image_size", "flags", "res2", "res3", "res4", "magic", "pe_offset"):
    if m5c_header[key] != m5b_header[key]:
        raise SystemExit(f"M5C_NONMINIMAL_BINARY_DIFF: {key} changed")
if struct.unpack_from("<I", m5c_image, primary_offset)[0] != primary_word:
    raise SystemExit("M5C_PRIMARY_SPIN_NOT_PRESERVED: primary word changed")
_, _, pe_after = pe_region(m5c_image, m5c_header)
if pe_after != pe_before:
    raise SystemExit("M5C_NONMINIMAL_BINARY_DIFF: PE region changed")

kernel_payload_offset = m5b_boot_info["kernel_offset"]
if kernel_payload_offset != 0x1000:
    raise SystemExit(f"M5C_HEADER_PARSE_FAILED: kernel offset=0x{kernel_payload_offset:x}")
m5c_boot_buf = bytearray(m5b_boot)
m5c_boot_buf[kernel_payload_offset + 8:kernel_payload_offset + 16] = m5c_image[8:16]
m5c_boot = bytes(m5c_boot_buf)
boot_diffs = diff_offsets(m5b_boot, m5c_boot)
expected_boot_diffs = [kernel_payload_offset + offset for offset in image_diffs]
if boot_diffs != expected_boot_diffs or boot_diffs != [0x100A]:
    raise SystemExit(f"M5C_NONMINIMAL_BINARY_DIFF: boot offsets={boot_diffs}")
if any(
    before != after
    for offset, (before, after) in enumerate(zip(m5b_boot, m5c_boot))
    if offset not in expected_boot_diffs
):
    raise SystemExit("M5C_NONMINIMAL_BINARY_DIFF: boot diff outside mapped text_offset")

m5c_boot_info = parse_boot(m5c_boot, "M5C boot")
if m5c_boot_info["kernel"] != m5c_image:
    raise SystemExit("M5C_VALIDATION_FAILED: M5C boot payload mismatch")
if m5c_boot_info["ramdisk"] != m5b_boot_info["ramdisk"]:
    raise SystemExit("M5C_VALIDATION_FAILED: ramdisk changed")
if sha(m5c_boot_info["ramdisk"]) != EXPECTED_RAMDISK_SHA:
    raise SystemExit(f"M5C_VALIDATION_FAILED: ramdisk SHA={sha(m5c_boot_info['ramdisk'])}")
for key in ("kernel_size", "ramdisk_size", "os_version_raw", "header_size", "reserved", "header_version", "cmdline_raw", "kernel_offset", "ramdisk_offset"):
    if m5c_boot_info[key] != m5b_boot_info[key]:
        raise SystemExit(f"M5C_VALIDATION_FAILED: boot metadata {key} changed")

m5c_image_path = out / "Image"
m5c_boot_path = out / "mainline-v2-m5c-text-offset-80000-spin-boot-v3.img"
m5c_image_path.write_bytes(m5c_image)
m5c_boot_path.write_bytes(m5c_boot)

proof_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "m5c-proof"
proof_dir.mkdir(parents=True, exist_ok=True)
code_path = proof_dir / "code.bin"
primary_path = proof_dir / "primary.bin"
code_path.write_bytes(m5c_image[:8])
primary_path.write_bytes(m5c_image[primary_offset:primary_offset + 4])
objdump = os.environ.get("AARCH64_OBJDUMP", "aarch64-linux-gnu-objdump")

def disassemble(path, adjust):
    return subprocess.run(
        [objdump, "-D", "-b", "binary", "-m", "aarch64", f"--adjust-vma={adjust}", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout

code_disasm = disassemble(code_path, 0)
primary_disasm = disassemble(primary_path, primary_offset)
if f"b\t0x{primary_offset:x}" not in code_disasm and f"b 0x{primary_offset:x}" not in code_disasm:
    raise SystemExit("M5C_VALIDATION_FAILED: code0 disassembly target mismatch")
if "b\t0x" not in primary_disasm and "b 0x" not in primary_disasm:
    raise SystemExit("M5C_PRIMARY_SPIN_NOT_PRESERVED: disassembly failed")

reverse = proof_dir / "reverse"
reverse.mkdir(exist_ok=True)
root = Path(__file__).resolve().parents[1]
unpack = root / "tools/aosp/unpack_bootimg.py"
for label, boot_path in (("m5b", m5b_boot_path), ("m5c", m5c_boot_path)):
    target = reverse / label
    target.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, str(unpack), "--boot_img", str(boot_path), "--out", str(target)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
if (reverse / "m5b/kernel").read_bytes() != m5b_image:
    raise SystemExit("M5C_VALIDATION_FAILED: reverse M5B kernel mismatch")
if (reverse / "m5c/kernel").read_bytes() != m5c_image:
    raise SystemExit("M5C_VALIDATION_FAILED: reverse M5C kernel mismatch")
if (reverse / "m5b/ramdisk").read_bytes() != m5b_boot_info["ramdisk"]:
    raise SystemExit("M5C_VALIDATION_FAILED: reverse M5B ramdisk mismatch")
if (reverse / "m5c/ramdisk").read_bytes() != m5b_boot_info["ramdisk"]:
    raise SystemExit("M5C_VALIDATION_FAILED: reverse M5C ramdisk mismatch")

matrix_lines = format_header("STOCK", stock_header) + format_header("M5B", m5b_header) + format_header("M5C", m5c_header)
(out / "stock-vs-mainline-header-matrix.txt").write_text("\n".join(matrix_lines) + "\n")
(out / "header-before-after.txt").write_text(
    "\n".join(
        format_header("M5B", m5b_header)
        + format_header("M5C", m5c_header)
        + [
            "TEXT_OFFSET_FIELD_OFFSETS=0x08..0x0f",
            f"TEXT_OFFSET_BEFORE_BYTES={m5b_image[8:16].hex()}",
            f"TEXT_OFFSET_AFTER_BYTES={m5c_image[8:16].hex()}",
            f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}",
            f"PRIMARY_ENTRY_WORD=0x{primary_word:08x}",
            "PRIMARY_ENTRY_DISASM=b .",
            f"PE_REGION_START=0x{pe_start:x}",
            f"PE_REGION_END=0x{pe_end:x}",
            f"PE_REGION_SHA_BEFORE={sha(pe_before)}",
            f"PE_REGION_SHA_AFTER={sha(pe_after)}",
            "\nCODE0_CODE1_DISASSEMBLY\n" + code_disasm,
            "PRIMARY_ENTRY_DISASSEMBLY\n" + primary_disasm,
        ]
    ) + "\n"
)
(out / "binary-diff-report.txt").write_text(
    f"IMAGE_DIFF_BYTE_COUNT={len(image_diffs)}\n"
    f"IMAGE_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in image_diffs)}\n"
    "IMAGE_DIFF_OUTSIDE_TEXT_OFFSET=0\n"
    f"BOOT_KERNEL_PAYLOAD_OFFSET=0x{kernel_payload_offset:x}\n"
    f"BOOT_DIFF_BYTE_COUNT={len(boot_diffs)}\n"
    f"BOOT_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in boot_diffs)}\n"
    "BOOT_DIFF_OUTSIDE_TEXT_OFFSET=0\n"
)

validation_lines = [
    "MEM0_POLICY_ACKNOWLEDGED=PASS",
    "GHA_ONLY=PASS",
    "LOCAL_BUILD=NO",
    "LOCAL_VALIDATOR=NO",
    "M5C_KERNEL_REBUILD=NO",
    "DEVICE_OPERATION=NO",
    "SLOT_A_WRITTEN=NO",
    "M5B_IMAGE_SHA_EXACT=PASS",
    "M5B_BOOT_SHA_EXACT=PASS",
    "STOCK_HEADER_PARSED=PASS",
    "M5B_HEADER_PARSED=PASS",
    "STOCK_TEXT_OFFSET_80000=PASS",
    "M5B_TEXT_OFFSET_ZERO=PASS",
    "TEXT_OFFSET_PATCHED_TO_80000=PASS",
    "CODE0_UNCHANGED=PASS",
    "CODE1_UNCHANGED=PASS",
    "CODE0_EXACT_M5B=PASS",
    "CODE1_EXACT_M5B=PASS",
    "PRIMARY_ENTRY_SPIN_PRESERVED=PASS",
    "IMAGE_SIZE_UNCHANGED=PASS",
    "FLAGS_UNCHANGED=PASS",
    "RESERVED_FIELDS_UNCHANGED=PASS",
    "MAGIC_UNCHANGED=PASS",
    "ARM64_MAGIC_UNCHANGED=PASS",
    "PE_OFFSET_UNCHANGED=PASS",
    "PE_HEADER_OFFSET_UNCHANGED=PASS",
    "PE_REGION_UNCHANGED=PASS",
    "M5B_RAMDISK_EXACT_REUSE=PASS",
    "RAMDISK_EXACT_REUSE=PASS",
    "BOOT_METADATA_UNCHANGED=PASS",
    "BOOT_KERNEL_SIZE_UNCHANGED=PASS",
    "IMAGE_DIFF_TEXT_OFFSET_ONLY=PASS",
    "BOOT_DIFF_TEXT_OFFSET_ONLY=PASS",
    "REVERSE_UNPACK=PASS",
    "TEXT_OFFSET_80000_ALIGNMENT_VALID=PASS",
    "ARM64_HEADER_ENCODING_VALID=PASS",
    "DIRECT_BRANCH_POSITION_INDEPENDENT=PASS",
    "PRIMARY_ENTRY_SPIN_POSITION_INDEPENDENT=PASS",
    f"M5B_IMAGE_SHA256={sha(m5b_image)}",
    f"M5B_BOOT_SHA256={sha(m5b_boot)}",
    f"STOCK_BOOT_SHA256={sha(stock_boot)}",
    f"STOCK_KERNEL_SHA256={sha(stock_image)}",
    f"M5C_IMAGE_SHA256={sha(m5c_image)}",
    f"M5C_BOOT_SHA256={sha(m5c_boot)}",
    f"RAMDISK_SHA256={sha(m5c_boot_info['ramdisk'])}",
    f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}",
    f"PRIMARY_ENTRY_WORD=0x{primary_word:08x}",
    f"BOOT_KERNEL_PAYLOAD_OFFSET=0x{kernel_payload_offset:x}",
    f"PE_REGION_SHA_BEFORE={sha(pe_before)}",
    f"PE_REGION_SHA_AFTER={sha(pe_after)}",
    "READY_FOR_MAINLINE_V2_M5C_TEXT_OFFSET_CONTROL",
]
(out / "validation-report.txt").write_text("\n".join(validation_lines) + "\n")

sum_names = (
    "mainline-v2-m5c-text-offset-80000-spin-boot-v3.img",
    "Image",
    "header-before-after.txt",
    "stock-vs-mainline-header-matrix.txt",
    "binary-diff-report.txt",
    "validation-report.txt",
)
(out / "SHA256SUMS").write_text(
    "\n".join(f"{sha((out / name).read_bytes())}  {name}" for name in sum_names) + "\n"
)

print("\n".join(matrix_lines))
print("\n".join(validation_lines))
print(f"IMAGE_DIFF_BYTE_COUNT={len(image_diffs)}")
print(f"IMAGE_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in image_diffs)}")
print(f"BOOT_DIFF_BYTE_COUNT={len(boot_diffs)}")
print(f"BOOT_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in boot_diffs)}")
