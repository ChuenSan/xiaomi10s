#!/usr/bin/env python3
"""CI-only ARM64 Image header parser. No local validation."""

import os
from pathlib import Path
import struct
import sys

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local Image header parse")

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
ARM64_MAGIC = b"ARM\x64"
MZ = 0x5A4D


def derive_layout():
    offsets = {}
    cursor = 0
    for name, fmt in HEADER_LAYOUT:
        width = struct.calcsize("<" + fmt)
        offsets[name] = (cursor, width, fmt)
        cursor += width
    if cursor != 64:
        raise SystemExit(f"HEADER_LAYOUT_INVALID size={cursor}")
    return offsets


def parse(image: bytes):
    if len(image) < 64:
        raise SystemExit(f"IMAGE_TOO_SHORT n={len(image)}")
    offsets = derive_layout()
    fields = {}
    for name, fmt in HEADER_LAYOUT:
        off, width, _ = offsets[name]
        (value,) = struct.unpack_from("<" + fmt, image, off)
        fields[name] = value
        fields[f"{name}_offset"] = off
        fields[f"{name}_width"] = width
    if fields["magic"] != ARM64_MAGIC:
        raise SystemExit(f"ARM64_MAGIC_MISMATCH {fields['magic']!r}")
    return fields


def emit(fields, image, out):
    code0 = fields["code0"]
    pe = fields["pe_offset"]
    mz = (code0 & 0xFFFF) == MZ
    pe_sig = "NONE"
    if pe != 0 and pe + 4 <= len(image):
        pe_sig = image[pe:pe + 4].decode("ascii", "replace")
    lines = [
        f"IMAGE_SIZE_BYTES={len(image)}",
        f"CODE0=0x{code0:08x}",
        f"CODE0_BYTES={image[0:4].hex()}",
        f"CODE0_MZ={'YES' if mz else 'NO'}",
        f"CODE1=0x{fields['code1']:08x}",
        f"TEXT_OFFSET=0x{fields['text_offset']:x}",
        f"IMAGE_SIZE_FIELD=0x{fields['image_size']:x}",
        f"FLAGS=0x{fields['flags']:x}",
        f"RES2=0x{fields['res2']:x}",
        f"RES3=0x{fields['res3']:x}",
        f"RES4=0x{fields['res4']:x}",
        f"MAGIC=ARM64",
        f"PE_OFFSET=0x{pe:x}",
        f"PE_OFFSET_FIELD_IMAGE_OFFSET=0x{fields['pe_offset_offset']:x}",
        f"PE_SIGNATURE_AT_OFFSET={pe_sig}",
        f"EFI_STUB_HEADER_STYLE={'YES' if mz or pe_sig.startswith('PE') else 'NO'}",
    ]
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    if out is not None:
        Path(out).write_text(text, encoding="utf-8")


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(f"usage: {sys.argv[0]} IMAGE [REPORT]")
    image = Path(sys.argv[1]).read_bytes()
    out = sys.argv[2] if len(sys.argv) == 3 else None
    emit(parse(image), image, out)


if __name__ == "__main__":
    main()
