#!/usr/bin/env python3
"""CI-only deterministic M4B -> M5B Image/boot transformation."""

import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local binary transformation/validation")

if len(sys.argv) != 3:
    raise SystemExit(f"usage: {sys.argv[0]} M4B_ARTIFACT_DIR RELEASE_DIR")

src = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)

EXPECTED_IMAGE_SHA = "52e429db5ba7ba411598625f706dc11d3d7c247458a932969e9913db0d1511a2"
EXPECTED_BOOT_SHA = "622a09516ddfcda7efad3cc42b92d2c205130ba7b0a8cf8cbba32c26a822b4c0"
EXPECTED_RAMDISK_SHA = "b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de"
EFI_SIGNATURE_NOP_WORD = 0xFA405A4D
PAGE_SIZE = 4096


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


def require_report_gate(text, gate):
    if gate not in text:
        raise SystemExit(f"authoritative M4B report lacks {gate}")


image_path = src / "Image"
boot_path = src / "mainline-v2-m4b-entry-spin-boot-v3.img"
report_path = src / "validation-report.txt"
for path in (image_path, boot_path, report_path):
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"missing exact M4B artifact input: {path}")

m4b_image = image_path.read_bytes()
m4b_boot = boot_path.read_bytes()
m4b_report = report_path.read_text()
if sha(m4b_image) != EXPECTED_IMAGE_SHA:
    raise SystemExit(f"M4B Image SHA mismatch: {sha(m4b_image)}")
if sha(m4b_boot) != EXPECTED_BOOT_SHA:
    raise SystemExit(f"M4B boot SHA mismatch: {sha(m4b_boot)}")

for gate in (
    "PRIMARY_ENTRY_SPIN_FIRST=PASS",
    "PRIMARY_ENTRY_IMAGE_SELF_BRANCH=PASS",
    "M3_TIMER_INSTRUMENTATION_ABSENT=PASS",
    "NO_TIMER_SYSREG=PASS",
    "NO_MMIO=PASS",
    "NO_EXCEPTION_INSTRUCTION=PASS",
    "NO_PSCI_REBOOT=PASS",
    "NO_WFE_WFI=PASS",
    "NO_BRK_UDF=PASS",
    "RAMDISK_EXACT_REUSE=PASS",
    "REVERSE_UNPACK=PASS",
):
    require_report_gate(m4b_report, gate)

matches = re.findall(r"PRIMARY_ENTRY_IMAGE_OFFSET=(0x[0-9a-fA-F]+)", m4b_report)
if len(set(matches)) != 1:
    raise SystemExit(f"ambiguous primary_entry offset in M4B report: {matches}")
primary_offset = int(matches[0], 16)
if primary_offset % 4 or not 0 < primary_offset <= len(m4b_image) - 4:
    raise SystemExit(f"invalid primary_entry Image offset: 0x{primary_offset:x}")

if len(m4b_image) < 64:
    raise SystemExit("M4B Image is smaller than the ARM64 header")
code0, code1 = struct.unpack_from("<II", m4b_image, 0)
text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<QQQQQQ", m4b_image, 8)
magic = m4b_image[56:60]
pe_offset = struct.unpack_from("<I", m4b_image, 60)[0]
if magic != b"ARM\x64":
    raise SystemExit(f"bad ARM64 Image magic: {magic!r}")
if code0 != EFI_SIGNATURE_NOP_WORD or m4b_image[:2] != b"MZ":
    raise SystemExit(
        f"M5B_HEADER_ASSUMPTION_INVALID: bytes={m4b_image[:4].hex()} word=0x{code0:08x}"
    )
if b_target(code1, 4) != primary_offset:
    raise SystemExit(
        f"M4B code1 target 0x{b_target(code1, 4):x} != primary_entry 0x{primary_offset:x}"
    )
primary_word = struct.unpack_from("<I", m4b_image, primary_offset)[0]
if primary_word != 0x14000000 or b_target(primary_word, primary_offset) != primary_offset:
    raise SystemExit(f"M4B primary_entry is not b .: 0x{primary_word:08x}")

delta = primary_offset
if delta % 4:
    raise SystemExit("M5B_BRANCH_ENCODING_FAILED: target is not 4-byte aligned")
imm26 = delta >> 2
if not -(1 << 25) <= imm26 < (1 << 25):
    raise SystemExit("M5B_BRANCH_ENCODING_FAILED: target is outside B imm26 range")
m5b_code0 = 0x14000000 | (imm26 & 0x03FFFFFF)
if b_target(m5b_code0, 0) != primary_offset:
    raise SystemExit("M5B_BRANCH_ENCODING_FAILED: encoded target mismatch")

m5b_image_buf = bytearray(m4b_image)
struct.pack_into("<I", m5b_image_buf, 0, m5b_code0)
m5b_image = bytes(m5b_image_buf)
image_diffs = diff_offsets(m4b_image, m5b_image)
if not image_diffs or any(offset not in range(4) for offset in image_diffs):
    raise SystemExit(f"M5B_NONMINIMAL_BINARY_DIFF: Image offsets={image_diffs}")
if m5b_image[4:] != m4b_image[4:]:
    raise SystemExit("M5B_NONMINIMAL_BINARY_DIFF: Image changed after code0")
if struct.unpack_from("<I", m5b_image, 4)[0] != code1:
    raise SystemExit("M5B_NONMINIMAL_BINARY_DIFF: code1 changed")
if struct.unpack_from("<I", m5b_image, primary_offset)[0] != 0x14000000:
    raise SystemExit("M5B_VALIDATION_FAILED: primary_entry spin changed")
if m5b_image[:2] == b"MZ":
    raise SystemExit("M5B_VALIDATION_FAILED: MZ signature unexpectedly remains")

if len(m4b_boot) < PAGE_SIZE or m4b_boot[:8] != b"ANDROID!":
    raise SystemExit("M4B boot is not an Android boot image")
kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from("<IIII", m4b_boot, 8)
header_version = struct.unpack_from("<I", m4b_boot, 40)[0]
cmdline_raw = m4b_boot[44:1580]
cmdline = cmdline_raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")
if header_version != 3 or header_size > PAGE_SIZE:
    raise SystemExit(f"unexpected boot header: version={header_version} size={header_size}")
kernel_payload_offset = PAGE_SIZE
kernel_end = kernel_payload_offset + kernel_size
ramdisk_offset = align(kernel_end, PAGE_SIZE)
ramdisk_end = ramdisk_offset + ramdisk_size
if ramdisk_end > len(m4b_boot):
    raise SystemExit("boot payload sizes exceed file")
if m4b_boot[kernel_payload_offset:kernel_end] != m4b_image:
    raise SystemExit("M4B Image does not map exactly to boot kernel payload at offset 4096")
if kernel_size != len(m4b_image):
    raise SystemExit("M4B boot kernel_size differs from exact Image size")
m4b_ramdisk = m4b_boot[ramdisk_offset:ramdisk_end]
if sha(m4b_ramdisk) != EXPECTED_RAMDISK_SHA:
    raise SystemExit(f"M4B ramdisk SHA mismatch: {sha(m4b_ramdisk)}")

boot_patch_offset = kernel_payload_offset
m5b_boot_buf = bytearray(m4b_boot)
m5b_boot_buf[boot_patch_offset:boot_patch_offset + 4] = m5b_image[:4]
m5b_boot = bytes(m5b_boot_buf)
boot_diffs = diff_offsets(m4b_boot, m5b_boot)
expected_boot_diffs = [kernel_payload_offset + offset for offset in image_diffs]
if boot_diffs != expected_boot_diffs:
    raise SystemExit(
        f"M5B_NONMINIMAL_BINARY_DIFF: boot offsets={boot_diffs}, expected={expected_boot_diffs}"
    )
if m5b_boot[:kernel_payload_offset] != m4b_boot[:kernel_payload_offset]:
    raise SystemExit("M5B_NONMINIMAL_BINARY_DIFF: boot header changed")
if m5b_boot[kernel_payload_offset:kernel_end] != m5b_image:
    raise SystemExit("M5B boot does not contain the patched Image exactly")
if m5b_boot[ramdisk_offset:ramdisk_end] != m4b_ramdisk:
    raise SystemExit("M5B ramdisk changed")

m5b_image_path = out / "Image"
m5b_boot_path = out / "mainline-v2-m5b-direct-entry-spin-boot-v3.img"
m5b_image_path.write_bytes(m5b_image)
m5b_boot_path.write_bytes(m5b_boot)

proof_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "m5b-proof"
proof_dir.mkdir(parents=True, exist_ok=True)
before_bin = proof_dir / "code-before.bin"
after_bin = proof_dir / "code-after.bin"
primary_bin = proof_dir / "primary-entry.bin"
before_bin.write_bytes(m4b_image[:8])
after_bin.write_bytes(m5b_image[:8])
primary_bin.write_bytes(m5b_image[primary_offset:primary_offset + 8])
objdump = os.environ.get("AARCH64_OBJDUMP", "aarch64-linux-gnu-objdump")


def disassemble(path, adjust):
    result = subprocess.run(
        [objdump, "-D", "-b", "binary", "-m", "aarch64", f"--adjust-vma={adjust}", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout


before_disasm = disassemble(before_bin, 0)
after_disasm = disassemble(after_bin, 0)
primary_disasm = disassemble(primary_bin, primary_offset)
(out / "disassembly-proof.txt").write_text(
    "M4B CODE0/CODE1\n"
    + before_disasm
    + "\nM5B CODE0/CODE1\n"
    + after_disasm
    + "\nM5B primary_entry\n"
    + primary_disasm
    + f"\nM4B_CODE0_WORD=0x{code0:08x}\n"
    + f"M4B_CODE1_WORD=0x{code1:08x}\n"
    + "M4B_CODE0_DISASM=ccmp x18, #0, #0xd, pl\n"
    + f"M4B_CODE1_DISASM=b 0x{primary_offset:x}\n"
    + f"M5B_CODE0_WORD=0x{m5b_code0:08x}\n"
    + f"M5B_CODE0_DISASM=b 0x{primary_offset:x}\n"
    + f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}\n"
    + "PRIMARY_ENTRY_DISASM=b .\n"
)

header_after = (
    struct.unpack_from("<Q", m5b_image, 8)[0],
    struct.unpack_from("<Q", m5b_image, 16)[0],
    struct.unpack_from("<Q", m5b_image, 24)[0],
    struct.unpack_from("<QQQ", m5b_image, 32),
    m5b_image[56:60],
    struct.unpack_from("<I", m5b_image, 60)[0],
)
header_before = (text_offset, image_size, flags, (res2, res3, res4), magic, pe_offset)
if header_after != header_before:
    raise SystemExit("M5B_NONMINIMAL_BINARY_DIFF: ARM64 header invariant changed")

(out / "Image-header-before-after-report.txt").write_text(
    f"M4B_CODE0_BYTES={m4b_image[:4].hex()}\n"
    f"M4B_CODE0_WORD=0x{code0:08x}\n"
    f"M4B_CODE0_DISASM=ccmp x18, #0, #0xd, pl\n"
    f"M4B_CODE1_BYTES={m4b_image[4:8].hex()}\n"
    f"M4B_CODE1_WORD=0x{code1:08x}\n"
    f"M4B_CODE1_DISASM=b 0x{primary_offset:x}\n"
    f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}\n"
    f"TEXT_OFFSET=0x{text_offset:x}\n"
    f"IMAGE_SIZE=0x{image_size:x}\n"
    f"FLAGS=0x{flags:x}\n"
    f"RESERVED_FIELDS=0x{res2:x},0x{res3:x},0x{res4:x}\n"
    f"MAGIC={magic.decode('ascii')}\n"
    f"PE_HEADER_OFFSET=0x{pe_offset:x}\n"
    "M4B_EFI_SIGNATURE_NOP_CONFIRMED=YES\n"
    "MZ_SIGNATURE_PRESENT_BEFORE=YES\n"
    f"M5B_CODE0_BYTES={m5b_image[:4].hex()}\n"
    f"M5B_CODE0_WORD=0x{m5b_code0:08x}\n"
    f"M5B_CODE0_DISASM=b 0x{primary_offset:x}\n"
    "MZ_SIGNATURE_PRESENT_AFTER=NO\n"
    f"PE_HEADER_OFFSET_BEFORE=0x{pe_offset:x}\n"
    f"PE_HEADER_OFFSET_AFTER=0x{header_after[5]:x}\n"
)

(out / "binary-diff-report.txt").write_text(
    f"DIFF_BYTE_COUNT={len(image_diffs)}\n"
    f"IMAGE_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in image_diffs)}\n"
    "IMAGE_DIFF_OUTSIDE_CODE0=0\n"
    f"KERNEL_PAYLOAD_OFFSET=0x{kernel_payload_offset:x}\n"
    f"BOOT_KERNEL_CODE0_OFFSET=0x{boot_patch_offset:x}\n"
    f"BOOT_DIFF_BYTE_COUNT={len(boot_diffs)}\n"
    f"BOOT_DIFF_OFFSETS={','.join(f'0x{x:x}' for x in boot_diffs)}\n"
    "BOOT_DIFF_OUTSIDE_KERNEL_CODE0=0\n"
)

reverse = proof_dir / "reverse"
reverse.mkdir(exist_ok=True)
root = Path(__file__).resolve().parents[1]
unpack = root / "tools/aosp/unpack_bootimg.py"
for label, boot in (("m4b", boot_path), ("m5b", m5b_boot_path)):
    target = reverse / label
    target.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, str(unpack), "--boot_img", str(boot), "--out", str(target)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
if (reverse / "m4b/kernel").read_bytes() != m4b_image:
    raise SystemExit("M4B reverse-unpacked kernel mismatch")
if (reverse / "m5b/kernel").read_bytes() != m5b_image:
    raise SystemExit("M5B reverse-unpacked kernel mismatch")
if (reverse / "m4b/ramdisk").read_bytes() != m4b_ramdisk:
    raise SystemExit("M4B reverse-unpacked ramdisk mismatch")
if (reverse / "m5b/ramdisk").read_bytes() != m4b_ramdisk:
    raise SystemExit("M5B reverse-unpacked ramdisk mismatch")

validation_lines = [
    "MEM0_POLICY_ACKNOWLEDGED=PASS",
    "GHA_ONLY=PASS",
    "LOCAL_BUILD=NO",
    "M5B_MAINLINE_SOURCE_REBUILD=NO",
    "M5B_KERNEL_BODY_CHANGE=NO",
    "M5B_DTS_CHANGE=NO",
    "M5B_CONFIG_CHANGE=NO",
    "M5B_RAMDISK_CHANGE=NO",
    "M4B_IMAGE_SHA_EXACT=PASS",
    "M4B_BOOT_SHA_EXACT=PASS",
    "M4B_EFI_CODE0_IDENTIFIED=PASS",
    "PRIMARY_ENTRY_OFFSET_RESOLVED=PASS",
    "DIRECT_BRANCH_ENCODING_VALID=PASS",
    "M5B_CODE0_DIRECT_TO_PRIMARY_ENTRY=PASS",
    "CODE1_UNCHANGED=PASS",
    "PRIMARY_ENTRY_SPIN_PRESERVED=PASS",
    "IMAGE_DIFF_CODE0_ONLY=PASS",
    "MZ_SIGNATURE_CHANGE_INTENTIONAL=PASS",
    "ARM64_MAGIC_UNCHANGED=PASS",
    "TEXT_OFFSET_UNCHANGED=PASS",
    "IMAGE_SIZE_UNCHANGED=PASS",
    "FLAGS_UNCHANGED=PASS",
    "RESERVED_FIELDS_UNCHANGED=PASS",
    "PE_HEADER_OFFSET_UNCHANGED=PASS",
    "M4B_RAMDISK_EXACT_REUSE=PASS",
    "BOOT_HEADER_VERSION_UNCHANGED=PASS",
    "BOOT_OS_VERSION_UNCHANGED=PASS",
    "BOOT_PATCH_LEVEL_UNCHANGED=PASS",
    "BOOT_KERNEL_SIZE_UNCHANGED=PASS",
    "BOOT_RAMDISK_SIZE_UNCHANGED=PASS",
    "BOOT_CMDLINE_UNCHANGED=PASS",
    "BOOT_SIGNATURE_PADDING_UNCHANGED=PASS",
    "BOOT_DIFF_KERNEL_CODE0_ONLY=PASS",
    "REVERSE_UNPACK=PASS",
    "NO_TIMER_INSTRUMENTATION=PASS",
    "NO_MMIO=PASS",
    "NO_PSCI_SMC_HVC=PASS",
    "NO_WFE_WFI=PASS",
    "NO_BRK_UDF=PASS",
    "NO_VENDOR_BOOT_ARTIFACT=PASS",
    "NO_DTBO_ARTIFACT=PASS",
    f"M4B_IMAGE_SHA256={sha(m4b_image)}",
    f"M4B_BOOT_SHA256={sha(m4b_boot)}",
    f"M5B_IMAGE_SHA256={sha(m5b_image)}",
    f"M5B_BOOT_SHA256={sha(m5b_boot)}",
    f"M4B_CODE0_WORD=0x{code0:08x}",
    f"M4B_CODE1_WORD=0x{code1:08x}",
    f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}",
    f"M5B_CODE0_WORD=0x{m5b_code0:08x}",
    f"BOOT_HEADER_VERSION={header_version}",
    f"BOOT_HEADER_SIZE={header_size}",
    f"BOOT_KERNEL_SIZE={kernel_size}",
    f"BOOT_RAMDISK_SIZE={ramdisk_size}",
    f"BOOT_OS_VERSION_RAW=0x{os_version_raw:08x}",
    f"BOOT_CMDLINE={cmdline}",
    f"RAMDISK_SHA256={sha(m4b_ramdisk)}",
    "READY_FOR_MAINLINE_V2_M5B_DIRECT_ENTRY_CONTROL",
]
(out / "validation-report.txt").write_text("\n".join(validation_lines) + "\n")

sums = []
for name in (
    "mainline-v2-m5b-direct-entry-spin-boot-v3.img",
    "Image",
    "binary-diff-report.txt",
    "Image-header-before-after-report.txt",
    "disassembly-proof.txt",
    "validation-report.txt",
):
    data = (out / name).read_bytes()
    sums.append(f"{sha(data)}  {name}")
(out / "SHA256SUMS").write_text("\n".join(sums) + "\n")

print("\n".join(validation_lines))
print(f"IMAGE_DIFF_BYTE_COUNT={len(image_diffs)}")
print(f"IMAGE_DIFF_OFFSETS={image_diffs}")
print(f"BOOT_DIFF_BYTE_COUNT={len(boot_diffs)}")
print(f"BOOT_DIFF_OFFSETS={boot_diffs}")
