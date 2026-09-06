#!/usr/bin/env python3
"""Split a concatenated DTB blob (vendor_boot dtb section) into individual FDTs.

Read-only: walks the blob using the FDT magic (0xd00dfeed) and the
totalsize field of each DTB header; never guesses boundaries.

Usage: split-concatenated-dtb.py INPUT [OUTPUT_DIR]
Output files: <OUTPUT_DIR>/dtb-<index>.dtb, each printed with SHA256
and verified parseable by `dtc` if available.
"""
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

FDT_MAGIC = 0xD00DFEED


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    data = src.read_bytes()
    blobs = []
    off = 0
    while off < len(data):
        if len(data) - off < 8:
            print(f"trailing {len(data)-off} bytes after last FDT", file=sys.stderr)
            break
        magic = struct.unpack_from(">I", data, off)[0]
        if magic != FDT_MAGIC:
            sys.exit(f"error: no FDT magic at offset 0x{off:x}")
        (total,) = struct.unpack_from(">I", data, off + 4)
        if total < 40 or off + total > len(data):
            sys.exit(f"error: bad totalsize {total} at offset 0x{off:x}")
        blobs.append(data[off:off + total])
        off += total

    dtc = shutil.which("dtc")
    for i, blob in enumerate(blobs):
        dest = out_dir / f"dtb-{i}.dtb"
        dest.write_bytes(blob)
        sha = hashlib.sha256(blob).hexdigest()
        size = len(blob)
        check = "ok"
        if dtc:
            r = subprocess.run([dtc, "-I", "dtb", "-O", "dts", "-o", "/dev/null",
                                str(dest)], capture_output=True, text=True)
            check = "ok" if r.returncode == 0 else f"dtc FAILED: {r.stderr.strip()}"
        print(f"[{i}] {dest} size={size} sha256={sha} dtc={check}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
