#!/usr/bin/env python3
"""CI-only deterministic M5C PE-header-offset zero control."""

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
    raise SystemExit(f"usage: {sys.argv[0]} M5C_ARTIFACT_DIR STOCK_STAGE4_BOOT RELEASE_DIR")

src = Path(sys.argv[1]).resolve()
stock_boot_path = Path(sys.argv[2]).resolve()
out = Path(sys.argv[3]).resolve()
out.mkdir(parents=True, exist_ok=True)

EXPECTED_M5C_IMAGE_SHA = "e0f1fa08555a9134f44af62d9f96258fa9903ec49052aa906aac6cb8a1365e35"
EXPECTED_M5C_BOOT_SHA = "66a001eb8065f64e879be5a9cef199fae2c8e7a4587f583d2d4581f8429083ec"
EXPECTED_STOCK_BOOT_SHA = "6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a"
EXPECTED_STOCK_KERNEL_SHA = "85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a"
EXPECTED_RAMDISK_SHA = "b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de"
EXPECTED_PE_REGION_SHA = "01a36888696f7d34c98d6c91c74dab3ea6a1fa5acb32730e149cdd73b0af2afd"
PAGE_SIZE = 4096
TARGET_PE_OFFSET = 0

# The parser derives every offset and width from this declarative layout.
HEADER_LAYOUT = (
    ("code0", "I"),
    ("code1", "I"),
    ("text_offset", "Q"),
    ("image_size", "Q"),
    ("flags", "Q"),
    ("res2", "Q"),
    ("res3", "Q"),
    ("res4", "Q"),
    ("magic", "4s"),
    ("pe_offset", "I"),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def sx(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def b_target(word, pc):
    if word & 0xFC000000 != 0x14000000:
        raise ValueError(f"not an AArch64 B instruction: 0x{word:08x}")
    return pc + sx(word & 0x03FFFFFF, 26) * 4


def diff_offsets(before, after):
    if len(before) != len(after):
        raise ValueError(f"size changed: {len(before)} -> {len(after)}")
    return [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def derive_header_layout():
    offsets = {}
    cursor = 0
    for name, fmt in HEADER_LAYOUT:
        width = struct.calcsize("<" + fmt)
        offsets[name] = (cursor, width, "little-endian")
        cursor += width
    if cursor != 64:
        raise SystemExit(f"M5D_HEADER_PARSE_FAILED: derived header size={cursor}")
    pe_start, pe_width, endian = offsets["pe_offset"]
    magic_start, magic_width, _ = offsets["magic"]
    if magic_start + magic_width != pe_start or pe_start + pe_width != cursor:
        raise SystemExit("M5D_HEADER_PARSE_FAILED: PE-offset layout is not terminal after magic")
    return offsets, cursor, endian


FIELD_LAYOUT, HEADER_SIZE, HEADER_ENDIAN = derive_header_layout()
PE_FIELD_START, PE_FIELD_WIDTH, _ = FIELD_LAYOUT["pe_offset"]
PE_FIELD_RANGE = range(PE_FIELD_START, PE_FIELD_START + PE_FIELD_WIDTH)


def parse_header(image, label):
    if len(image) < HEADER_SIZE:
        raise SystemExit(f"M5D_HEADER_PARSE_FAILED: {label} Image smaller than derived header")
    values = {}
    for name, fmt in HEADER_LAYOUT:
        offset, width, _ = FIELD_LAYOUT[name]
        if struct.calcsize("<" + fmt) != width:
            raise SystemExit("M5D_HEADER_PARSE_FAILED: inconsistent field width")
        values[name] = struct.unpack_from("<" + fmt, image, offset)[0]
    if values["magic"] != b"ARM\x64":
        raise SystemExit(f"M5D_HEADER_PARSE_FAILED: {label} magic={values['magic']!r}")
    if image[FIELD_LAYOUT["magic"][0]:PE_FIELD_START] != b"ARM\x64":
        raise SystemExit("M5D_HEADER_PARSE_FAILED: exact magic-to-PE-offset layout mismatch")
    return values


def parse_boot(boot, label):
    if len(boot) < PAGE_SIZE or boot[:8] != b"ANDROID!":
        raise SystemExit(f"M5D_HEADER_PARSE_FAILED: {label} is not Android boot")
    kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from("<IIII", boot, 8)
    reserved = struct.unpack_from("<IIII", boot, 24)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    cmdline_raw = boot[44:1580]
    if header_version != 3 or header_size > PAGE_SIZE:
        raise SystemExit(f"M5D_HEADER_PARSE_FAILED: {label} version={header_version} size={header_size}")
    kernel_offset = PAGE_SIZE
    kernel_end = kernel_offset + kernel_size
    ramdisk_offset = align(kernel_end, PAGE_SIZE)
    ramdisk_end = ramdisk_offset + ramdisk_size
    if ramdisk_end > len(boot):
        raise SystemExit(f"M5D_HEADER_PARSE_FAILED: {label} payload exceeds file")
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


def locate_real_pe_region(image, header):
    start = header["pe_offset"]
    if start == 0 or start + 24 > len(image) or image[start:start + 4] != b"PE\0\0":
        raise SystemExit("M5D_HEADER_PARSE_FAILED: M5C metadata does not locate PE signature")
    optional_size = struct.unpack_from("<H", image, start + 20)[0]
    optional = start + 24
    if optional_size < 64 or optional + optional_size > len(image):
        raise SystemExit("M5D_HEADER_PARSE_FAILED: invalid PE optional header extent")
    if struct.unpack_from("<H", image, optional)[0] != 0x20B:
        raise SystemExit("M5D_HEADER_PARSE_FAILED: PE optional header is not PE32+")
    size_of_headers = struct.unpack_from("<I", image, optional + 60)[0]
    end = max(start + 24 + optional_size, size_of_headers)
    if end > len(image):
        raise SystemExit("M5D_HEADER_PARSE_FAILED: PE payload region exceeds Image")
    return start, end


def format_header(prefix, header):
    return [
        f"{prefix}_CODE0=0x{header['code0']:08x}",
        f"{prefix}_CODE1=0x{header['code1']:08x}",
        f"{prefix}_TEXT_OFFSET=0x{header['text_offset']:x}",
        f"{prefix}_IMAGE_SIZE=0x{header['image_size']:x}",
        f"{prefix}_FLAGS=0x{header['flags']:x}",
        f"{prefix}_RESERVED_FIELDS=0x{header['res2']:x},0x{header['res3']:x},0x{header['res4']:x}",
        f"{prefix}_MAGIC={header['magic'].decode('ascii')}",
        f"{prefix}_PE_HEADER_OFFSET=0x{header['pe_offset']:x}",
    ]


m5c_image_path = src / "Image"
m5c_boot_path = src / "mainline-v2-m5c-text-offset-80000-spin-boot-v3.img"
m5c_report_path = src / "validation-report.txt"
for path in (m5c_image_path, m5c_boot_path, m5c_report_path, stock_boot_path):
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"M5D_SOURCE_IDENTITY_FAILED: missing {path}")

m5c_image = m5c_image_path.read_bytes()
m5c_boot = m5c_boot_path.read_bytes()
m5c_report = m5c_report_path.read_text()
stock_boot = stock_boot_path.read_bytes()
if sha(m5c_image) != EXPECTED_M5C_IMAGE_SHA:
    raise SystemExit(f"M5D_SOURCE_IDENTITY_FAILED: M5C Image SHA={sha(m5c_image)}")
if sha(m5c_boot) != EXPECTED_M5C_BOOT_SHA:
    raise SystemExit(f"M5D_SOURCE_IDENTITY_FAILED: M5C boot SHA={sha(m5c_boot)}")
if sha(stock_boot) != EXPECTED_STOCK_BOOT_SHA:
    raise SystemExit(f"M5D_SOURCE_IDENTITY_FAILED: Stock boot SHA={sha(stock_boot)}")
if "READY_FOR_MAINLINE_V2_M5C_TEXT_OFFSET_CONTROL" not in m5c_report:
    raise SystemExit("M5D_SOURCE_IDENTITY_FAILED: M5C final gate absent")

m5c_boot_info = parse_boot(m5c_boot, "M5C boot")
stock_boot_info = parse_boot(stock_boot, "Stock boot")
if m5c_boot_info["kernel"] != m5c_image or m5c_boot_info["kernel_size"] != len(m5c_image):
    raise SystemExit("M5D_SOURCE_IDENTITY_FAILED: M5C Image/payload mismatch")
stock_image = stock_boot_info["kernel"]
if sha(stock_image) != EXPECTED_STOCK_KERNEL_SHA:
    raise SystemExit(f"M5D_SOURCE_IDENTITY_FAILED: Stock kernel SHA={sha(stock_image)}")

m5c_header = parse_header(m5c_image, "M5C")
stock_header = parse_header(stock_image, "Stock")
if m5c_header["pe_offset"] != 0x40:
    raise SystemExit(f"M5D_HEADER_PARSE_FAILED: M5C PE offset=0x{m5c_header['pe_offset']:x}")
if stock_header["pe_offset"] != 0:
    raise SystemExit(f"M5D_STOCK_PE_OFFSET_ASSUMPTION_INVALID: 0x{stock_header['pe_offset']:x}")
if m5c_header["code0"] != 0x146C7028:
    raise SystemExit(f"M5D_VALIDATION_FAILED: M5C code0=0x{m5c_header['code0']:08x}")
if m5c_header["text_offset"] != 0x80000 or m5c_header["image_size"] != 0x2220000:
    raise SystemExit("M5D_VALIDATION_FAILED: M5C incremental header baseline mismatch")
if m5c_header["flags"] != 0xA or any(m5c_header[key] for key in ("res2", "res3", "res4")):
    raise SystemExit("M5D_VALIDATION_FAILED: M5C flags/reserved mismatch")

matches = re.findall(r"PRIMARY_ENTRY_IMAGE_OFFSET=(0x[0-9a-fA-F]+)", m5c_report)
if len(set(matches)) != 1:
    raise SystemExit(f"M5D_PRIMARY_SPIN_NOT_PRESERVED: offsets={matches}")
primary_offset = int(matches[0], 16)
if primary_offset % 4 or not 0 < primary_offset <= len(m5c_image) - 4:
    raise SystemExit(f"M5D_PRIMARY_SPIN_NOT_PRESERVED: offset=0x{primary_offset:x}")
primary_word = struct.unpack_from("<I", m5c_image, primary_offset)[0]
try:
    code0_target = b_target(m5c_header["code0"], 0)
    primary_target = b_target(primary_word, primary_offset)
except ValueError as exc:
    raise SystemExit(f"M5D_PRIMARY_SPIN_NOT_PRESERVED: {exc}") from exc
if code0_target != primary_offset or primary_word != 0x14000000 or primary_target != primary_offset:
    raise SystemExit("M5D_PRIMARY_SPIN_NOT_PRESERVED: direct entry/spin mismatch")

pe_start, pe_end = locate_real_pe_region(m5c_image, m5c_header)
pe_before = m5c_image[pe_start:pe_end]
if sha(pe_before) != EXPECTED_PE_REGION_SHA:
    raise SystemExit(f"M5D_PE_REGION_CHANGED: M5C real PE region SHA={sha(pe_before)}")

before_field = m5c_image[PE_FIELD_START:PE_FIELD_START + PE_FIELD_WIDTH]
if before_field != struct.pack("<I", m5c_header["pe_offset"]):
    raise SystemExit("M5D_HEADER_PARSE_FAILED: parser field bytes disagree with parsed value")
m5d_buf = bytearray(m5c_image)
struct.pack_into("<I", m5d_buf, PE_FIELD_START, TARGET_PE_OFFSET)
m5d_image = bytes(m5d_buf)
m5d_header = parse_header(m5d_image, "M5D")


class CandidateRejected(Exception):
    pass


def validate_candidate(candidate):
    try:
        header = parse_header(candidate, "candidate")
    except SystemExit as exc:
        raise CandidateRejected(str(exc)) from exc
    for key in ("code0", "code1", "text_offset", "image_size", "flags", "res2", "res3", "res4", "magic"):
        if header[key] != m5c_header[key]:
            raise CandidateRejected(f"immutable header field changed: {key}")
    if header["pe_offset"] != TARGET_PE_OFFSET:
        raise CandidateRejected("PE offset is not zero")
    if struct.unpack_from("<I", candidate, primary_offset)[0] != 0x14000000:
        raise CandidateRejected("primary_entry is not b .")
    if candidate[pe_start:pe_end] != pe_before:
        raise CandidateRejected("real PE payload changed")
    diffs = diff_offsets(m5c_image, candidate)
    if not diffs or any(offset not in PE_FIELD_RANGE for offset in diffs):
        raise CandidateRejected(f"diff outside PE-offset field: {diffs}")
    return diffs


try:
    image_diffs = validate_candidate(m5d_image)
except (CandidateRejected, ValueError) as exc:
    raise SystemExit(f"M5D_NONMINIMAL_BINARY_DIFF: {exc}") from exc
if image_diffs != [PE_FIELD_START]:
    raise SystemExit(f"M5D_NONMINIMAL_BINARY_DIFF: Image offsets={image_diffs}")
if m5d_image[pe_start:pe_end] != pe_before:
    raise SystemExit("M5D_PE_REGION_CHANGED")
pe_after = m5d_image[pe_start:pe_end]

# Prove the validator fails closed for each required corruption class.
def expect_rejected(label, offset, replacement):
    damaged = bytearray(m5d_image)
    damaged[offset:offset + len(replacement)] = replacement
    try:
        validate_candidate(bytes(damaged))
    except (CandidateRejected, ValueError):
        return
    raise SystemExit(f"M5D_VALIDATION_FAILED: negative test accepted {label}")


expect_rejected("code0", FIELD_LAYOUT["code0"][0], b"\x00\x00\x00\x00")
expect_rejected("text_offset", FIELD_LAYOUT["text_offset"][0], b"\x00" * 8)
expect_rejected("image_size", FIELD_LAYOUT["image_size"][0], b"\x00" * 8)
expect_rejected("primary_entry", primary_offset, b"\x1f\x20\x03\xd5")
expect_rejected("PE_payload", pe_start, b"PX\x00\x00")
expect_rejected("outside_field", HEADER_SIZE + 0x40, bytes([m5d_image[HEADER_SIZE + 0x40] ^ 0xFF]))

kernel_payload_offset = m5c_boot_info["kernel_offset"]
if kernel_payload_offset != 0x1000:
    raise SystemExit(f"M5D_HEADER_PARSE_FAILED: boot kernel offset=0x{kernel_payload_offset:x}")
boot_field_start = kernel_payload_offset + PE_FIELD_START
m5d_boot_buf = bytearray(m5c_boot)
m5d_boot_buf[boot_field_start:boot_field_start + PE_FIELD_WIDTH] = m5d_image[PE_FIELD_START:PE_FIELD_START + PE_FIELD_WIDTH]
m5d_boot = bytes(m5d_boot_buf)
boot_diffs = diff_offsets(m5c_boot, m5d_boot)
expected_boot_diffs = [kernel_payload_offset + offset for offset in image_diffs]
if boot_diffs != expected_boot_diffs:
    raise SystemExit(f"M5D_NONMINIMAL_BINARY_DIFF: boot offsets={boot_diffs}")

m5d_boot_info = parse_boot(m5d_boot, "M5D boot")
if m5d_boot_info["kernel"] != m5d_image:
    raise SystemExit("M5D_VALIDATION_FAILED: final boot kernel payload mismatch")
if m5d_boot_info["ramdisk"] != m5c_boot_info["ramdisk"]:
    raise SystemExit("M5D_VALIDATION_FAILED: ramdisk changed")
if sha(m5d_boot_info["ramdisk"]) != EXPECTED_RAMDISK_SHA:
    raise SystemExit(f"M5D_VALIDATION_FAILED: ramdisk SHA={sha(m5d_boot_info['ramdisk'])}")
for key in ("kernel_size", "ramdisk_size", "os_version_raw", "header_size", "reserved", "header_version", "cmdline_raw", "kernel_offset", "ramdisk_offset"):
    if m5d_boot_info[key] != m5c_boot_info[key]:
        raise SystemExit(f"M5D_VALIDATION_FAILED: boot metadata changed: {key}")
if any(index not in expected_boot_diffs for index in diff_offsets(m5c_boot, m5d_boot)):
    raise SystemExit("M5D_NONMINIMAL_BINARY_DIFF: boot diff outside mapped PE-offset field")

m5d_image_path = out / "Image"
m5d_boot_path = out / "mainline-v2-m5d-pe-offset-zero-spin-boot-v3.img"
m5d_image_path.write_bytes(m5d_image)
m5d_boot_path.write_bytes(m5d_boot)

proof_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "m5d-proof"
proof_dir.mkdir(parents=True, exist_ok=True)
code_path = proof_dir / "code.bin"
primary_path = proof_dir / "primary.bin"
code_path.write_bytes(m5d_image[:8])
primary_path.write_bytes(m5d_image[primary_offset:primary_offset + 4])
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
if f"0x{primary_offset:x}" not in code_disasm or f"0x{primary_offset:x}" not in primary_disasm:
    raise SystemExit("M5D_PRIMARY_SPIN_NOT_PRESERVED: disassembly proof mismatch")
(out / "disassembly-proof.txt").write_text(
    "M5D CODE0/CODE1\n" + code_disasm
    + "\nM5D primary_entry\n" + primary_disasm
    + f"\nCODE0_WORD=0x{m5d_header['code0']:08x}\n"
    + f"CODE0_DISASM=b 0x{primary_offset:x}\n"
    + f"CODE1_WORD=0x{m5d_header['code1']:08x}\n"
    + f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}\n"
    + f"PRIMARY_ENTRY_WORD=0x{primary_word:08x}\n"
    + "PRIMARY_ENTRY_DISASM=b .\n"
)

reverse = proof_dir / "reverse"
reverse.mkdir(exist_ok=True)
root = Path(__file__).resolve().parents[1]
unpack = root / "tools/aosp/unpack_bootimg.py"
for label, boot_path in (("m5c", m5c_boot_path), ("m5d", m5d_boot_path)):
    target = reverse / label
    target.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, str(unpack), "--boot_img", str(boot_path), "--out", str(target)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
if (reverse / "m5c/kernel").read_bytes() != m5c_image or (reverse / "m5d/kernel").read_bytes() != m5d_image:
    raise SystemExit("M5D_VALIDATION_FAILED: reverse-unpacked kernel mismatch")
if (reverse / "m5c/ramdisk").read_bytes() != m5c_boot_info["ramdisk"] or (reverse / "m5d/ramdisk").read_bytes() != m5c_boot_info["ramdisk"]:
    raise SystemExit("M5D_VALIDATION_FAILED: reverse-unpacked ramdisk mismatch")

matrix_lines = format_header("STOCK", stock_header) + format_header("M5C", m5c_header) + format_header("M5D", m5d_header)
(out / "header-before-after-report.txt").write_text(
    "\n".join(
        [
            f"ARM64_HEADER_LAYOUT_SIZE=0x{HEADER_SIZE:x}",
            f"PE_HEADER_OFFSET_FIELD_IMAGE_OFFSET=0x{PE_FIELD_START:x}",
            f"PE_HEADER_OFFSET_FIELD_WIDTH={PE_FIELD_WIDTH}",
            f"PE_HEADER_OFFSET_FIELD_ENDIAN={HEADER_ENDIAN}",
            f"PE_HEADER_OFFSET_FIELD_BYTE_RANGE=0x{PE_FIELD_START:x}..0x{PE_FIELD_START + PE_FIELD_WIDTH - 1:x}",
            f"PE_HEADER_OFFSET_FIELD_VALUE_BEFORE=0x{m5c_header['pe_offset']:x}",
            f"PE_HEADER_OFFSET_FIELD_VALUE_AFTER=0x{m5d_header['pe_offset']:x}",
            f"PE_HEADER_OFFSET_BEFORE_BYTES={before_field.hex()}",
            f"PE_HEADER_OFFSET_AFTER_BYTES={m5d_image[PE_FIELD_START:PE_FIELD_START + PE_FIELD_WIDTH].hex()}",
            *matrix_lines,
            f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}",
            f"PRIMARY_ENTRY_WORD=0x{primary_word:08x}",
            "PRIMARY_ENTRY_DISASM=b .",
            f"REAL_PE_REGION_HASH_DOMAIN=Image[0x{pe_start:x}:0x{pe_end:x}]",
            "REAL_PE_REGION_EXCLUDES_ARM64_PE_OFFSET_METADATA_FIELD=YES",
            f"PE_REGION_SHA_BEFORE={sha(pe_before)}",
            f"PE_REGION_SHA_AFTER={sha(pe_after)}",
            f"STOCK_ACTUAL_KERNEL_PAYLOAD_BYTES={len(stock_image)}",
            f"STOCK_HEADER_IMAGE_SIZE={stock_header['image_size']}",
            f"STOCK_PAYLOAD_MINUS_HEADER_IMAGE_SIZE={len(stock_image) - stock_header['image_size']}",
            f"M5C_ACTUAL_KERNEL_PAYLOAD_BYTES={len(m5c_image)}",
            f"M5C_HEADER_IMAGE_SIZE={m5c_header['image_size']}",
            f"M5C_PAYLOAD_MINUS_HEADER_IMAGE_SIZE={len(m5c_image) - m5c_header['image_size']}",
            "SIZE_COMPARISON_CLASS=ANALYSIS_METADATA",
        ]
    ) + "\n"
)
(out / "binary-diff-report.txt").write_text(
    f"IMAGE_DIFF_BYTE_COUNT={len(image_diffs)}\n"
    f"IMAGE_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in image_diffs)}\n"
    "IMAGE_DIFF_OUTSIDE_PE_OFFSET_FIELD=0\n"
    f"BOOT_KERNEL_PAYLOAD_OFFSET=0x{kernel_payload_offset:x}\n"
    f"BOOT_PE_OFFSET_FIELD_IMAGE_MAPPING=0x{boot_field_start:x}\n"
    f"BOOT_DIFF_BYTE_COUNT={len(boot_diffs)}\n"
    f"BOOT_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in boot_diffs)}\n"
    "BOOT_DIFF_OUTSIDE_PE_OFFSET_FIELD=0\n"
)

validation_lines = [
    "MEM0_POLICY_ACKNOWLEDGED=PASS",
    "GHA_ONLY=PASS",
    "LOCAL_BUILD=NO",
    "LOCAL_VALIDATOR=NO",
    "DEVICE_OPERATION=NO",
    "SLOT_A_WRITTEN=NO",
    "M5C_IMAGE_SHA_EXACT=PASS",
    "M5C_BOOT_SHA_EXACT=PASS",
    "M5C_HEADER_PARSED=PASS",
    "STOCK_HEADER_PARSED=PASS",
    "HEADER_LAYOUT_VALIDATED=PASS",
    "M5C_PE_OFFSET_40=PASS",
    "STOCK_PE_OFFSET_ZERO=PASS",
    "M5D_PE_OFFSET_ZERO=PASS",
    "CODE0_UNCHANGED=PASS",
    "CODE1_UNCHANGED=PASS",
    "CODE0_EXACT_M5C=PASS",
    "CODE1_EXACT_M5C=PASS",
    "TEXT_OFFSET_80000_PRESERVED=PASS",
    "IMAGE_SIZE_UNCHANGED=PASS",
    "FLAGS_UNCHANGED=PASS",
    "RESERVED_FIELDS_UNCHANGED=PASS",
    "MAGIC_UNCHANGED=PASS",
    "ARM64_MAGIC_UNCHANGED=PASS",
    "PRIMARY_ENTRY_SPIN_PRESERVED=PASS",
    "REAL_PE_REGION_UNCHANGED=PASS",
    "RAMDISK_EXACT_REUSE=PASS",
    "BOOT_METADATA_UNCHANGED=PASS",
    "IMAGE_DIFF_PE_OFFSET_ONLY=PASS",
    "BOOT_DIFF_PE_OFFSET_ONLY=PASS",
    "REVERSE_UNPACK=PASS",
    "FAIL_CLOSED=PASS",
    f"M5C_IMAGE_SHA256={sha(m5c_image)}",
    f"M5C_BOOT_SHA256={sha(m5c_boot)}",
    f"STOCK_BOOT_SHA256={sha(stock_boot)}",
    f"STOCK_KERNEL_SHA256={sha(stock_image)}",
    f"M5D_IMAGE_SHA256={sha(m5d_image)}",
    f"M5D_BOOT_SHA256={sha(m5d_boot)}",
    f"RAMDISK_SHA256={sha(m5d_boot_info['ramdisk'])}",
    f"PE_HEADER_OFFSET_FIELD_IMAGE_OFFSET=0x{PE_FIELD_START:x}",
    f"PE_HEADER_OFFSET_FIELD_WIDTH={PE_FIELD_WIDTH}",
    f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}",
    f"PRIMARY_ENTRY_WORD=0x{primary_word:08x}",
    f"BOOT_KERNEL_PAYLOAD_OFFSET=0x{kernel_payload_offset:x}",
    f"PE_REGION_SHA_BEFORE={sha(pe_before)}",
    f"PE_REGION_SHA_AFTER={sha(pe_after)}",
    "READY_FOR_MAINLINE_V2_M5D_PE_OFFSET_ZERO_CONTROL",
]
(out / "validation-report.txt").write_text("\n".join(validation_lines) + "\n")

sum_names = (
    "mainline-v2-m5d-pe-offset-zero-spin-boot-v3.img",
    "Image",
    "header-before-after-report.txt",
    "binary-diff-report.txt",
    "disassembly-proof.txt",
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
