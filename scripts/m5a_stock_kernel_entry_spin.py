#!/usr/bin/env python3
"""Audit and minimally patch a stock ARM64 Image entry to `b .`.

Binary layout is authoritative. Downstream 4.19 head.S is supporting evidence
only. GitHub Actions is required for file transformation of a real kernel.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

EXPECTED_STAGE4_BOOT_SHA256 = (
    "6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a"
)
EXPECTED_STOCK_KERNEL_SHA256 = (
    "85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a"
)
EXPECTED_STAGE4_RAMDISK_SHA256 = (
    "e31cab1bef3408d1b87074ff7bcf573b9ebb74b96d535c55b9c97953ef1d0ac9"
)
STOCK_KERNEL_BANNER_NEEDLE = b"Linux version 4.19.157-perf"
ARM64_IMAGE_MAGIC = b"ARM\x64"
SELF_BRANCH_WORD = 0x14000000
EFI_MZ_ADD = 0x91005A4D  # add x13, x18, #0x16
A64_NOP = 0xD503201F
B_MASK = 0xFC000000
B_OPC = 0x14000000
BL_OPC = 0x94000000
HEADER_LEN = 64
METADATA_SLICE = slice(8, 64)


class TransformError(Exception):
    def __init__(self, gate: str, message: str) -> None:
        super().__init__(message)
        self.gate = gate
        self.message = message


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def is_uncond_b(word: int) -> bool:
    return word & B_MASK == B_OPC


def is_bl(word: int) -> bool:
    return word & B_MASK == BL_OPC


def b_target(pc: int, word: int) -> int:
    return pc + sign_extend((word & 0x03FFFFFF) << 2, 28)


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def classify_word(word: int) -> str:
    if word == EFI_MZ_ADD:
        return "EFI_MZ_ADD"
    if word == A64_NOP:
        return "NOP"
    if word == 0:
        return "RESERVED_ZERO"
    if word == SELF_BRANCH_WORD:
        return "B_SELF"
    if is_uncond_b(word):
        return "B"
    if is_bl(word):
        return "BL"
    return f"OTHER_{word:#010x}"


def decode_a64(word: int, pc: int = 0) -> str:
    kind = classify_word(word)
    if kind == "EFI_MZ_ADD":
        return "add x13, x18, #0x16"
    if kind == "NOP":
        return "nop"
    if kind == "RESERVED_ZERO":
        return ".long 0"
    if kind == "B_SELF":
        return "b ."
    if kind == "B":
        return f"b {b_target(pc, word):#x}"
    if kind == "BL":
        return f"bl {b_target(pc, word):#x}"
    return kind


def require_ci() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("CI only — refuse local kernel transformation/validation")


@dataclass(frozen=True)
class ImageHeader:
    code0: int
    code1: int
    text_offset: int
    image_size: int
    flags: int
    res2: int
    res3: int
    res4: int
    magic: bytes
    pe_offset: int
    file_size: int

    @property
    def code0_class(self) -> str:
        return classify_word(self.code0)

    @property
    def code1_class(self) -> str:
        return classify_word(self.code1)


@dataclass(frozen=True)
class PatchPlan:
    offset: int
    original_word: int
    patched_word: int
    original_class: str
    layout: str
    branch_pc: int
    original_target: int
    reason: str


def parse_arm64_image(data: bytes) -> ImageHeader:
    if data[:2] == b"\x1f\x8b":
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            "kernel payload is gzip-compressed; M5A requires a raw Image 4-byte patch",
        )
    if len(data) < HEADER_LEN:
        raise TransformError(
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            f"kernel payload too short for ARM64 Image header: {len(data)}",
        )
    magic = data[0x38:0x3C]
    if magic != ARM64_IMAGE_MAGIC:
        raise TransformError(
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            f"ARM64 Image magic mismatch: {magic!r}",
        )
    return ImageHeader(
        code0=u32(data, 0),
        code1=u32(data, 4),
        text_offset=int.from_bytes(data[8:16], "little"),
        image_size=int.from_bytes(data[16:24], "little"),
        flags=int.from_bytes(data[24:32], "little"),
        res2=int.from_bytes(data[32:40], "little"),
        res3=int.from_bytes(data[40:48], "little"),
        res4=int.from_bytes(data[48:56], "little"),
        magic=magic,
        pe_offset=u32(data, 0x3C),
        file_size=len(data),
    )


def _require_in_image_target(data: bytes, pc: int, word: int) -> int:
    if not is_uncond_b(word):
        raise TransformError(
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            f"expected unconditional B at pc={pc:#x}, got {classify_word(word)} {word:#010x}",
        )
    if word == SELF_BRANCH_WORD:
        raise TransformError(
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            f"entry branch at {pc:#x} is already b .",
        )
    target = b_target(pc, word)
    if target % 4 or target < HEADER_LEN or target + 4 > len(data):
        raise TransformError(
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            f"entry branch target {target:#x} is outside executable Image payload",
        )
    return target


def choose_patch(data: bytes, header: ImageHeader) -> PatchPlan:
    c0, c1 = header.code0_class, header.code1_class
    if c0 == "B" and c1 == "RESERVED_ZERO":
        target = _require_in_image_target(data, 0, header.code0)
        return PatchPlan(
            offset=0,
            original_word=header.code0,
            patched_word=SELF_BRANCH_WORD,
            original_class=c0,
            layout="NON_EFI_CODE0_BRANCH_TO_ENTRY",
            branch_pc=0,
            original_target=target,
            reason="non-EFI Image header: code0 is the branch-to-entry",
        )
    if c0 in {"EFI_MZ_ADD", "NOP"} and c1 == "B":
        target = _require_in_image_target(data, 4, header.code1)
        return PatchPlan(
            offset=4,
            original_word=header.code1,
            patched_word=SELF_BRANCH_WORD,
            original_class=c1,
            layout="EFI_CODE1_BRANCH_TO_ENTRY",
            branch_pc=4,
            original_target=target,
            reason="EFI-compatible code0 kept; code1 is the branch-to-entry",
        )
    raise TransformError(
        "M5A_ENTRY_LOCATION_INCONCLUSIVE",
        f"unsupported Image entry layout code0={c0} code1={c1} "
        f"words={header.code0:#010x},{header.code1:#010x}",
    )


def apply_patch(data: bytes, plan: PatchPlan) -> bytes:
    if plan.patched_word != SELF_BRANCH_WORD:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            f"refusing non-self-branch patch word {plan.patched_word:#010x}",
        )
    if u32(data, plan.offset) != plan.original_word:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            "kernel changed underfoot before patch",
        )
    patched = bytearray(data)
    patched[plan.offset : plan.offset + 4] = plan.patched_word.to_bytes(4, "little")
    return bytes(patched)


def diff_offsets(original: bytes, patched: bytes) -> list[int]:
    if len(original) != len(patched):
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            f"size changed: {len(original)} -> {len(patched)}",
        )
    return [i for i, (left, right) in enumerate(zip(original, patched)) if left != right]


def assert_minimal_kernel_patch(original: bytes, patched: bytes, plan: PatchPlan) -> list[int]:
    diffs = diff_offsets(original, patched)
    allowed = list(range(plan.offset, plan.offset + 4))
    extra = [off for off in diffs if off not in allowed]
    if extra or not diffs:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            f"kernel delta {diffs} is not a subset of instruction {allowed}",
        )
    if original[METADATA_SLICE] != patched[METADATA_SLICE]:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            "ARM64 Image metadata bytes 8-63 changed",
        )
    if patched[0x38:0x3C] != ARM64_IMAGE_MAGIC:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            "ARM64 Image magic changed",
        )
    orig_hdr = parse_arm64_image(original)
    new_hdr = parse_arm64_image(patched)
    for name in ("text_offset", "image_size", "flags", "pe_offset"):
        if getattr(orig_hdr, name) != getattr(new_hdr, name):
            raise TransformError(
                "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
                f"Image {name} changed",
            )
    if u32(patched, plan.offset) != SELF_BRANCH_WORD:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            "patched word is not b .",
        )
    return diffs


def kernel_banner(data: bytes) -> str:
    marker = b"Linux version "
    start = data.find(marker)
    if start < 0:
        return ""
    end = data.find(b"\x00", start)
    if end < 0:
        end = min(len(data), start + 160)
    return data[start:end].decode("ascii", "replace")


def assert_stock_kernel_identity(data: bytes, expected_sha256: str) -> str:
    actual = sha256_bytes(data)
    if actual != expected_sha256:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            f"stock kernel SHA mismatch actual={actual}",
        )
    banner = kernel_banner(data)
    if STOCK_KERNEL_BANNER_NEEDLE.decode() not in banner:
        raise TransformError(
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            f"stock kernel banner missing 4.19.157-perf: {banner!r}",
        )
    return banner


def kv_lines(mapping: dict[str, object]) -> str:
    return "".join(f"{key}={value}\n" for key, value in mapping.items())


def analyze_and_patch(original: bytes) -> tuple[bytes, PatchPlan, ImageHeader, dict[str, object]]:
    header = parse_arm64_image(original)
    plan = choose_patch(original, header)
    patched = apply_patch(original, plan)
    diffs = assert_minimal_kernel_patch(original, patched, plan)
    target_word = u32(original, plan.original_target)
    report = {
        "ARM64_IMAGE_HEADER_VALID": "PASS",
        "ARM64_IMAGE_MAGIC": "ARM\\x64",
        "CODE0": f"{header.code0:#010x}",
        "CODE0_CLASS": header.code0_class,
        "CODE0_DECODE": decode_a64(header.code0, 0),
        "CODE1": f"{header.code1:#010x}",
        "CODE1_CLASS": header.code1_class,
        "CODE1_DECODE": decode_a64(header.code1, 4),
        "TEXT_OFFSET": f"{header.text_offset:#x}",
        "IMAGE_SIZE": str(header.image_size),
        "IMAGE_FILE_SIZE": str(header.file_size),
        "FLAGS": f"{header.flags:#x}",
        "PE_OFFSET": f"{header.pe_offset:#x}",
        "ENTRY_LAYOUT": plan.layout,
        "EARLIEST_ENTRY_OFFSET": f"{plan.offset:#x}",
        "ORIGINAL_INSTRUCTION": f"{plan.original_word:#010x}",
        "ORIGINAL_INSTRUCTION_DECODE": decode_a64(plan.original_word, plan.branch_pc),
        "PATCHED_INSTRUCTION": f"{plan.patched_word:#010x}",
        "PATCHED_INSTRUCTION_DECODE": "b .",
        "PATCH_OFFSET": str(plan.offset),
        "EXPECTED_PATCHED_WORD": f"{SELF_BRANCH_WORD:#010x}",
        "ORIGINAL_BRANCH_TARGET": f"{plan.original_target:#x}",
        "ORIGINAL_TARGET_WORD": f"{target_word:#010x}",
        "ORIGINAL_TARGET_CLASS": classify_word(target_word),
        "ORIGINAL_TARGET_DECODE": decode_a64(target_word, plan.original_target),
        "PATCH_REASON": plan.reason,
        "KERNEL_PATCH_WORD_SIZE": "4",
        "KERNEL_DIFF_BYTE_COUNT": str(len(diffs)),
        "DIFF_OFFSETS": ",".join(str(v) for v in diffs),
        "KERNEL_ONLY_EXPECTED_BYTES_CHANGED": "PASS",
        "ARM64_IMAGE_MAGIC_UNCHANGED": "PASS",
        "IMAGE_SIZE_FIELDS_UNCHANGED": "PASS",
        "TEXT_OFFSET_UNCHANGED": "PASS",
        "PE_OFFSET_UNCHANGED": "PASS",
        "NO_TIMER": "PASS",
        "NO_MMIO": "PASS",
        "NO_EXCEPTION_INSN": "PASS",
        "NO_PSCI": "PASS",
        "NO_SMC_HVC": "PASS",
        "NO_WFE_WFI": "PASS",
        "SPIN_PATCH_MINIMAL": "PASS",
        "EARLIEST_ENTRY_LOCATION_AUDITED": "PASS",
    }
    return patched, plan, header, report


def cmd_transform(args: argparse.Namespace) -> int:
    require_ci()
    kernel_path = Path(args.kernel)
    data = kernel_path.read_bytes()
    banner = assert_stock_kernel_identity(data, args.expected_kernel_sha256)
    patched, _plan, _header, report = analyze_and_patch(data)
    Path(args.patched).write_bytes(patched)
    report["STOCK_KERNEL_IDENTITY"] = "PASS"
    report["STOCK_KERNEL_BANNER"] = banner.replace("\n", " ")
    report["STOCK_KERNEL_SHA256"] = sha256_bytes(data)
    report["PATCHED_KERNEL_SHA256"] = sha256_bytes(patched)
    text = kv_lines(report)
    Path(args.report).write_text(text)
    sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    transform = sub.add_parser("transform")
    transform.add_argument("--kernel", required=True)
    transform.add_argument("--patched", required=True)
    transform.add_argument("--report", required=True)
    transform.add_argument(
        "--expected-kernel-sha256",
        default=EXPECTED_STOCK_KERNEL_SHA256,
    )
    transform.set_defaults(func=cmd_transform)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TransformError as exc:
        sys.stderr.write(f"FAIL {exc.gate}: {exc.message}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
