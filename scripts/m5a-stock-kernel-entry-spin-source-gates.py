#!/usr/bin/env python3
"""Public source gates for M5A stock-kernel entry spin. CI only. No OEM binary."""
from __future__ import annotations

import importlib.util
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def pass_(message: str) -> None:
    print(f"PASS {message}")


def require_ci() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        fail("CI only — refuse local source-gate execution")


def load_transform():
    path = ROOT / "scripts" / "m5a_stock_kernel_entry_spin.py"
    spec = importlib.util.spec_from_file_location("m5a_stock_kernel_entry_spin", path)
    if spec is None or spec.loader is None:
        fail("cannot load m5a_stock_kernel_entry_spin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_image(code0: int, code1: int, payload: bytes, pe: int = 0) -> bytes:
    image_size = 64 + len(payload)
    hdr = struct.pack(
        "<IIQQQQQQ",
        code0,
        code1,
        0,
        image_size,
        0xA,
        0,
        0,
        0,
    )
    hdr += b"ARM\x64"
    hdr += struct.pack("<I", pe)
    if len(hdr) != 64:
        fail(f"synthetic header size {len(hdr)}")
    return hdr + payload


def b_imm(pc: int, target: int) -> int:
    delta = target - pc
    if delta % 4:
        fail("synthetic branch not aligned")
    imm26 = (delta >> 2) & 0x03FFFFFF
    return 0x14000000 | imm26


def read(rel: str) -> str:
    return (ROOT / rel).read_text()


def main() -> int:
    require_ci()
    transform_src = read("scripts/m5a_stock_kernel_entry_spin.py")
    validate_src = read("scripts/m5a-stock-kernel-entry-spin-ci-validate.sh")
    workflow_src = read(
        ".github/workflows/thyme-mainline-v2-m5a-stock-entry-spin-control.yml"
    )
    docs_src = read("docs/route-b-mainline-v2-m5a-stock-entry-spin-control.md")

    need = {
        "scripts/m5a_stock_kernel_entry_spin.py": [
            "EXPECTED_STAGE4_BOOT_SHA256",
            "6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a",
            "85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a",
            "e31cab1bef3408d1b87074ff7bcf573b9ebb74b96d535c55b9c97953ef1d0ac9",
            "Linux version 4.19.157-perf",
            "SELF_BRANCH_WORD = 0x14000000",
            "NON_EFI_CODE0_BRANCH_TO_ENTRY",
            "EFI_CODE1_BRANCH_TO_ENTRY",
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            "GITHUB_ACTIONS",
        ],
        "scripts/m5a-stock-kernel-entry-spin-ci-validate.sh": [
            "GITHUB_ACTIONS",
            "AUTHORITATIVE_STAGE4_BOOT_SHA",
            "STAGE4_RAMDISK_EXACT_REUSE",
            "BOOT_HEADER_SEMANTIC_MATCH",
            "KERNEL_ONLY_EXPECTED_BYTES_CHANGED",
            "PRIVATE_ARTIFACT_ONLY",
            "READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL",
            "M5A_STOCK_CONTROL_SOURCE_UNAVAILABLE",
            "M5A_ENTRY_LOCATION_INCONCLUSIVE",
            "M5A_BINARY_TRANSFORM_VALIDATION_FAILED",
            "M5A_PRIVATE_ARTIFACT_POLICY_FAILED",
            "aarch64-linux-gnu-objdump",
            "NO_TIMER",
            "NO_MMIO",
            "NO_EXCEPTION_INSN",
        ],
        ".github/workflows/thyme-mainline-v2-m5a-stock-entry-spin-control.yml": [
            "Public source audit",
            "No OEM",
            "PRIVATE",
        ],
        "docs/route-b-mainline-v2-m5a-stock-entry-spin-control.md": [
            "ChuenSan/thyme-mainline-private-ci",
            "6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a",
            "READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL",
            "NO ADB",
            "WAIT FOR USER APPROVAL",
            "aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972",
            "018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634",
        ],
    }
    texts = {
        "scripts/m5a_stock_kernel_entry_spin.py": transform_src,
        "scripts/m5a-stock-kernel-entry-spin-ci-validate.sh": validate_src,
        ".github/workflows/thyme-mainline-v2-m5a-stock-entry-spin-control.yml": workflow_src,
        "docs/route-b-mainline-v2-m5a-stock-entry-spin-control.md": docs_src,
    }
    for path, tokens in need.items():
        text = texts[path]
        for token in tokens:
            if token not in text:
                fail(f"missing {token!r} in {path}")
        pass_(f"SOURCE_TOKENS {path}")

    if "PATCH_OFFSET = 4" in transform_src or "patch_offset = 4" in transform_src:
        fail("transformer hardcodes offset=4")
    if "SELF_BRANCH_WORD = 0x14000000" not in transform_src:
        fail("transformer missing self-branch word")
    if "0xD4000003" in transform_src or "0xD503205F" in transform_src:
        fail("transformer contains SMC/WFI encodings")
    pass_("NO_HARDCODED_OFFSET4")
    pass_("SELF_BRANCH_ONLY_PATCH_WORD")

    forbidden_public = [
        "stock-kernel-usb-stage4-http-boot-v3.img",
        "unpack_bootimg.py",
        "mkbootimg.py",
        "upload-artifact",
        "actions/download-artifact",
    ]
    for token in forbidden_public:
        if token in workflow_src:
            fail(f"public workflow contains OEM/builder token {token}")
    pass_("PUBLIC_WORKFLOW_NO_OEM_BUILD")

    if "m5a-stock-entry-spin-boot-v3.img" in workflow_src:
        fail("public workflow references flashable M5A boot image")
    pass_("PUBLIC_WORKFLOW_NO_FLASHABLE_OUTPUT")

    mod = load_transform()
    payload = b"\x00" * 192
    target = 0x40
    non_efi = make_image(b_imm(0, target), 0, payload)
    patched, plan, header, report = mod.analyze_and_patch(non_efi)
    if plan.offset != 0 or plan.layout != "NON_EFI_CODE0_BRANCH_TO_ENTRY":
        fail(f"non-EFI plan mismatch {plan}")
    if patched[:4] != (0x14000000).to_bytes(4, "little"):
        fail("non-EFI patched code0 is not b .")
    if non_efi[4:] != patched[4:]:
        fail("non-EFI patch touched bytes after code0")
    if header.magic != b"ARM\x64":
        fail("synthetic magic lost")
    if report["SPIN_PATCH_MINIMAL"] != "PASS":
        fail("synthetic non-EFI minimal patch failed")
    pass_("SYNTHETIC_NON_EFI_CODE0_SPIN")

    efi_target = 0x80
    efi = make_image(mod.EFI_MZ_ADD, b_imm(4, efi_target), payload, pe=0x40)
    patched_efi, plan_efi, _, _ = mod.analyze_and_patch(efi)
    if plan_efi.offset != 4 or plan_efi.layout != "EFI_CODE1_BRANCH_TO_ENTRY":
        fail(f"EFI plan mismatch {plan_efi}")
    if patched_efi[4:8] != (0x14000000).to_bytes(4, "little"):
        fail("EFI patched code1 is not b .")
    if efi[:4] != patched_efi[:4] or efi[8:] != patched_efi[8:]:
        fail("EFI patch touched bytes other than code1")
    pass_("SYNTHETIC_EFI_CODE1_SPIN")

    bad = make_image(mod.A64_NOP, mod.A64_NOP, payload)
    try:
        mod.analyze_and_patch(bad)
    except mod.TransformError as exc:
        if exc.gate != "M5A_ENTRY_LOCATION_INCONCLUSIVE":
            fail(f"unexpected gate for bad layout: {exc.gate}")
        pass_("SYNTHETIC_INCONCLUSIVE_LAYOUT")
    else:
        fail("inconclusive layout was accepted")

    gzip = b"\x1f\x8b" + b"\x00" * 80
    try:
        mod.parse_arm64_image(gzip)
    except mod.TransformError as exc:
        if "gzip" not in exc.message:
            fail(f"gzip rejection mismatch: {exc.message}")
        pass_("SYNTHETIC_GZIP_REJECTED")
    else:
        fail("gzip Image was accepted")

    head_s = ROOT / "android-kernel-sm8250/arch/arm64/kernel/head.S"
    kona = ROOT / "android-kernel-sm8250/arch/arm64/configs/vendor/kona-perf_defconfig"
    if head_s.is_file():
        text = head_s.read_text()
        for token in ("b\tstext", "add\tx13, x18, #0x16", "__HEAD", "_head:"):
            if token not in text:
                fail(f"downstream head.S missing {token!r}")
        pass_("DOWNSTREAM_HEAD_S_LAYOUT")
    else:
        print("DOWNSTREAM_HEAD_S=NOT_CHECKED_OUT")
    if kona.is_file():
        text = kona.read_text()
        if "# CONFIG_EFI is not set" not in text:
            fail("kona-perf_defconfig does not leave CONFIG_EFI unset")
        if "CONFIG_BUILD_ARM64_UNCOMPRESSED_KERNEL=y" not in text:
            fail("kona-perf_defconfig missing uncompressed Image")
        pass_("DOWNSTREAM_KONA_PERF_NON_EFI_UNCOMPRESSED")
    else:
        print("DOWNSTREAM_KONA_PERF=NOT_CHECKED_OUT")

    print("PUBLIC_M5A_SOURCE_GATES=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
