#!/usr/bin/env python3
"""Read-only Android boot image v2 parser. No compilation."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


BOOT_MAGIC = b"ANDROID!"
V2_HEADER_SIZE = 1660
ARM64_MAGIC = 0x644D5241
FDT_MAGIC = b"\xd0\x0d\xfe\xed"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zstr(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("ascii", "replace")


def page_align(n: int, page: int) -> int:
    return (n + page - 1) // page * page


def decode_os_version_patch(raw: int) -> tuple[str, str]:
    os_version = raw >> 11
    patch = raw & ((1 << 11) - 1)
    a, b, c = os_version >> 14, (os_version >> 7) & 0x7F, os_version & 0x7F
    year, month = 2000 + (patch >> 4), patch & 0xF
    return f"{a}.{b}.{c}", f"{year:04d}-{month:02d}"


def parse_v2(image: bytes) -> dict:
    if image[:8] != BOOT_MAGIC:
        raise ValueError(f"bad magic {image[:8]!r}")
    off = 8
    (
        kernel_size,
        kernel_addr,
        ramdisk_size,
        ramdisk_addr,
        second_size,
        second_addr,
        tags_addr,
        page_size,
        header_version,
    ) = struct.unpack_from("<9I", image, off)
    off += 36
    (os_raw,) = struct.unpack_from("<I", image, off)
    off += 4
    name = image[off : off + 16]
    off += 16
    cmdline = image[off : off + 512]
    off += 512
    img_id = image[off : off + 32]
    off += 32
    extra = image[off : off + 1024]
    off += 1024
    (recovery_dtbo_size,) = struct.unpack_from("<I", image, off)
    off += 4
    (recovery_dtbo_offset,) = struct.unpack_from("<Q", image, off)
    off += 8
    (header_size,) = struct.unpack_from("<I", image, off)
    off += 4
    (dtb_size,) = struct.unpack_from("<I", image, off)
    off += 4
    (dtb_addr,) = struct.unpack_from("<Q", image, off)
    off += 8
    if off != V2_HEADER_SIZE:
        raise ValueError(f"parsed header end {off} != {V2_HEADER_SIZE}")
    os_version, os_patch = decode_os_version_patch(os_raw)
    ps = page_size
    kernel_off = ps
    kernel_pad = page_align(kernel_size, ps)
    ramdisk_off = kernel_off + kernel_pad
    ramdisk_pad = page_align(ramdisk_size, ps)
    second_off = ramdisk_off + ramdisk_pad
    second_pad = page_align(second_size, ps) if second_size else 0
    rec_off = second_off + second_pad
    rec_pad = page_align(recovery_dtbo_size, ps) if recovery_dtbo_size else 0
    dtb_off = rec_off + rec_pad
    dtb_pad = page_align(dtb_size, ps) if dtb_size else 0
    computed_end = dtb_off + dtb_pad
    kernel = image[kernel_off : kernel_off + kernel_size]
    ramdisk = image[ramdisk_off : ramdisk_off + ramdisk_size]
    dtb = image[dtb_off : dtb_off + dtb_size] if dtb_size else b""
    fdt_offsets = []
    start = 0
    while True:
        i = image.find(FDT_MAGIC, start)
        if i < 0:
            break
        fdt_offsets.append(i)
        start = i + 1
    text_offset = image_size = flags = arm64_magic = None
    if len(kernel) >= 64:
        text_offset, image_size, flags = struct.unpack_from("<QQQ", kernel, 8)
        (arm64_magic,) = struct.unpack_from("<I", kernel, 56)
    osv, patch = os_version, os_patch
    return {
        "header": {
            "magic": zstr(image[:8]),
            "kernel_size": kernel_size,
            "kernel_addr": kernel_addr,
            "kernel_addr_hex": hex(kernel_addr),
            "ramdisk_size": ramdisk_size,
            "ramdisk_addr": ramdisk_addr,
            "ramdisk_addr_hex": hex(ramdisk_addr),
            "second_size": second_size,
            "second_addr": second_addr,
            "second_addr_hex": hex(second_addr),
            "tags_addr": tags_addr,
            "tags_addr_hex": hex(tags_addr),
            "page_size": page_size,
            "header_version": header_version,
            "os_version_raw": os_raw,
            "os_version": osv,
            "os_patch_level": patch,
            "name": zstr(name),
            "cmdline": zstr(cmdline),
            "extra_cmdline": zstr(extra),
            "id_sha1_hex": img_id[:20].hex(),
            "recovery_dtbo_size": recovery_dtbo_size,
            "recovery_dtbo_offset": recovery_dtbo_offset,
            "header_size": header_size,
            "dtb_size": dtb_size,
            "dtb_addr": dtb_addr,
            "dtb_addr_hex": hex(dtb_addr),
        },
        "layout": {
            "header": {"offset": 0, "size": header_size, "page": ps},
            "kernel": {
                "offset": kernel_off,
                "size": kernel_size,
                "end": kernel_off + kernel_size,
                "padded_end": kernel_off + kernel_pad,
            },
            "ramdisk": {
                "offset": ramdisk_off,
                "size": ramdisk_size,
                "end": ramdisk_off + ramdisk_size,
                "padded_end": ramdisk_off + ramdisk_pad,
            },
            "second": {"offset": second_off, "size": second_size, "padded": second_pad},
            "recovery_dtbo": {
                "offset": rec_off,
                "size": recovery_dtbo_size,
                "padded": rec_pad,
            },
            "dtb": {
                "offset": dtb_off,
                "size": dtb_size,
                "end": dtb_off + dtb_size,
                "padded_end": dtb_off + dtb_pad,
            },
            "computed_end": computed_end,
            "file_size": len(image),
            "computed_offsets_eq_file": computed_end == len(image),
        },
        "payloads": {
            "kernel_sha256": sha256_bytes(kernel) if kernel_size else None,
            "ramdisk_sha256": sha256_bytes(ramdisk) if ramdisk_size else None,
            "dtb_sha256": sha256_bytes(dtb) if dtb_size else None,
            "dtb_magic_hex": dtb[:4].hex() if dtb else "",
            "fdt_magic_offsets": fdt_offsets,
            "kernel_starts_mz": kernel[:2] == b"MZ" if kernel else False,
            "arm64_text_offset": text_offset,
            "arm64_text_offset_hex": hex(text_offset) if text_offset is not None else None,
            "arm64_image_size": image_size,
            "arm64_flags": flags,
            "arm64_flags_hex": hex(flags) if flags is not None else None,
            "arm64_magic_ok": arm64_magic == ARM64_MAGIC,
        },
    }


def overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def memory_map(header: dict) -> dict:
    k0, ksz = header["kernel_addr"], header["kernel_size"]
    r0, rsz = header["ramdisk_addr"], header["ramdisk_size"]
    d0, dsz = header["dtb_addr"], header["dtb_size"]
    dram = 0x80000000
    return {
        "raw": {
            "kernel": [k0, k0 + ksz],
            "ramdisk": [r0, r0 + rsz],
            "dtb": [d0, d0 + dsz],
            "kernel_ramdisk_overlap": overlap(k0, k0 + ksz, r0, r0 + rsz),
            "kernel_dtb_overlap": overlap(k0, k0 + ksz, d0, d0 + dsz),
            "ramdisk_dtb_overlap": overlap(r0, r0 + rsz, d0, d0 + dsz),
        },
        "plus_dram_base_0x80000000": {
            "kernel": [dram + k0, dram + k0 + ksz],
            "ramdisk": [dram + r0, dram + r0 + rsz],
            "dtb": [dram + d0, dram + d0 + dsz],
            "kernel_ramdisk_overlap": overlap(
                dram + k0, dram + k0 + ksz, dram + r0, dram + r0 + rsz
            ),
            "kernel_dtb_overlap": overlap(
                dram + k0, dram + k0 + ksz, dram + d0, dram + d0 + dsz
            ),
        },
        "note": (
            "Header load addresses overlap if treated as absolute destinations. "
            "Qualcomm ABL does not use header kernel_addr/ramdisk_addr/dtb_addr "
            "as copy destinations; it relocates into UEFI/PCD windows."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--dtb-ref", help="expected DTB file for exact-match")
    ap.add_argument("--kernel-ref")
    ap.add_argument("--ramdisk-ref")
    ap.add_argument("--json-out")
    ap.add_argument("--require-v2", action="store_true")
    args = ap.parse_args()
    path = Path(args.image)
    parsed = parse_v2(path.read_bytes())
    parsed["image_sha256"] = sha256_path(path)
    hdr = parsed["header"]
    pay = parsed["payloads"]
    layout = parsed["layout"]
    parsed["memory_map"] = memory_map(hdr)
    flags = []
    if args.require_v2 and hdr["header_version"] != 2:
        flags.append("FAIL header_version")
    if hdr["header_size"] != V2_HEADER_SIZE:
        flags.append("FAIL header_size")
    if not layout["computed_offsets_eq_file"]:
        flags.append("FAIL computed_end != file_size")
    if args.dtb_ref:
        ref = sha256_path(Path(args.dtb_ref))
        parsed["dtb_ref_sha256"] = ref
        parsed["DTB_PAYLOAD_EXACT_MATCH"] = pay["dtb_sha256"] == ref
        if not parsed["DTB_PAYLOAD_EXACT_MATCH"]:
            flags.append("FAIL DTB_PAYLOAD_EXACT_MATCH")
    if args.kernel_ref and pay["kernel_sha256"] != sha256_path(Path(args.kernel_ref)):
        flags.append("FAIL kernel payload")
    if args.ramdisk_ref and pay["ramdisk_sha256"] != sha256_path(Path(args.ramdisk_ref)):
        flags.append("FAIL ramdisk payload")
    parsed["gates"] = flags or ["PASS"]
    text = json.dumps(parsed, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n")
    print(text)
    return 1 if any(x.startswith("FAIL") for x in parsed["gates"]) else 0


if __name__ == "__main__":
    sys.exit(main())
