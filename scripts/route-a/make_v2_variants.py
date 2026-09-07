#!/usr/bin/env python3
"""GHA-only: pack Route A v2 differential images from already-built products."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_boot_v2 import V2_HEADER_SIZE, parse_v2, sha256_path  # noqa: E402

STOCK_CMDLINE = (
    "console=ttyMSM0,115200n8 androidboot.hardware=qcom "
    "androidboot.console=ttyMSM0 androidboot.memcg=1 lpm_levels.sleep_disabled=1 "
    "video=vfb:640x400,bpp=32,memsize=3072000 msm_rtb.filter=0x237 "
    "service_locator.enable=1 androidboot.usbcontroller=a600000.dwc3 "
    "swiotlb=2048 loop.max_part=7 cgroup.memory=nokmem,nosocket "
    "reboot=panic_warm buildvariant=user"
)
CMDLINE_PROBE = STOCK_CMDLINE + " route_a_cmdline_probe=1"
MKBOOTIMG_ARGS = [
    "--base",
    "0x00000000",
    "--kernel_offset",
    "0x00008000",
    "--ramdisk_offset",
    "0x01000000",
    "--tags_offset",
    "0x00000100",
    "--second_offset",
    "0x00f00000",
    "--pagesize",
    "4096",
    "--header_version",
    "2",
    "--dtb_offset",
    "0x01f00000",
    "--os_version",
    "13.0.0",
    "--os_patch_level",
    "2023-09",
    "--board",
    "thyme",
]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def mkbootimg(mk: Path, kernel: Path, ramdisk: Path, dtb: Path | None, cmdline: str, out: Path) -> None:
    cmd = [
        sys.executable,
        str(mk),
        "--kernel",
        str(kernel),
        "--ramdisk",
        str(ramdisk),
        *MKBOOTIMG_ARGS,
        "--cmdline",
        cmdline,
        "-o",
        str(out),
    ]
    if dtb is not None:
        cmd.extend(["--dtb", str(dtb)])
    run(cmd)


def fdtput(dtb: Path, args: list[str]) -> None:
    run(["fdtput", str(dtb), *args])


def patch_dtb_magic(image: Path) -> None:
    data = bytearray(image.read_bytes())
    parsed = parse_v2(bytes(data))
    off = parsed["layout"]["dtb"]["offset"]
    if data[off : off + 4] != b"\xd0\x0d\xfe\xed":
        raise SystemExit("dtb magic missing before corrupt")
    data[off : off + 4] = b"\x00\x00\x00\x00"
    image.write_bytes(data)


def strip_dtb(image: Path) -> None:
    data = bytearray(image.read_bytes())
    parsed = parse_v2(bytes(data))
    layout = parsed["layout"]
    dtb_off = layout["dtb"]["offset"]
    # dtb_size at header offset 1648, dtb_addr at 1652
    struct.pack_into("<I", data, 1648, 0)
    struct.pack_into("<Q", data, 1652, 0)
    image.write_bytes(bytes(data[:dtb_off]))


def write_report(out_dir: Path, variant: str, image: Path, extra: dict) -> None:
    parsed = parse_v2(image.read_bytes())
    parsed["image_sha256"] = sha256_path(image)
    parsed["variant"] = variant
    parsed.update(extra)
    (out_dir / "headers.json").write_text(json.dumps(parsed["header"], indent=2) + "\n")
    (out_dir / "layout.json").write_text(json.dumps(parsed["layout"], indent=2) + "\n")
    (out_dir / "parse.json").write_text(json.dumps(parsed, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mkbootimg", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--ramdisk", required=True)
    ap.add_argument("--dtb", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    mk = Path(args.mkbootimg)
    kernel, ramdisk, dtb = Path(args.kernel), Path(args.ramdisk), Path(args.dtb)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    control_dir = out / "control"
    control_dir.mkdir(exist_ok=True)
    control_img = control_dir / "experimental-boot-v2.img"
    mkbootimg(mk, kernel, ramdisk, dtb, STOCK_CMDLINE, control_img)
    write_report(control_dir, "control", control_img, {"purpose": "reproducible v2 control"})

    # cmdline-probe: same payloads, marker in header cmdline only
    cmd_dir = out / "cmdline-probe"
    cmd_dir.mkdir(exist_ok=True)
    cmd_img = cmd_dir / "experimental-boot-v2.img"
    mkbootimg(mk, kernel, ramdisk, dtb, CMDLINE_PROBE, cmd_img)
    write_report(cmd_dir, "cmdline-probe", cmd_img, {"purpose": "boot v2 cmdline marker"})

    # marker-dtb
    marker_dtb = out / "marker.dtb"
    shutil.copy2(dtb, marker_dtb)
    fdtput(marker_dtb, ["-t", "s", "/", "model", "Xiaomi Mi 10S Route-A DTB Probe"])
    marker_dir = out / "marker-dtb"
    marker_dir.mkdir(exist_ok=True)
    marker_img = marker_dir / "experimental-boot-v2.img"
    mkbootimg(mk, kernel, ramdisk, marker_dtb, STOCK_CMDLINE, marker_img)
    write_report(marker_dir, "marker-dtb", marker_img, {"purpose": "unique /model in DTB"})

    # qc-ids: msm-id + board-id, no hardware node changes
    ids_dtb = out / "qc-ids.dtb"
    shutil.copy2(dtb, ids_dtb)
    fdtput(ids_dtb, ["-p", "-t", "x", "/", "qcom,msm-id", "0x164", "0x20001"])
    fdtput(ids_dtb, ["-p", "-t", "x", "/", "qcom,board-id", "0x2d", "0x0"])
    ids_dir = out / "qc-ids"
    ids_dir.mkdir(exist_ok=True)
    ids_img = ids_dir / "experimental-boot-v2.img"
    mkbootimg(mk, kernel, ramdisk, ids_dtb, STOCK_CMDLINE, ids_img)
    write_report(
        ids_dir,
        "qc-ids",
        ids_img,
        {"purpose": "add qcom,msm-id <0x164 0x20001> and qcom,board-id <45 0>"},
    )

    # bad-dtb-magic: copy control, corrupt FDT magic
    bad_dir = out / "bad-dtb"
    bad_dir.mkdir(exist_ok=True)
    bad_img = bad_dir / "experimental-boot-v2.img"
    shutil.copy2(control_img, bad_img)
    patch_dtb_magic(bad_img)
    write_report(bad_dir, "bad-dtb", bad_img, {"purpose": "keep dtb_size, invalid FDT magic"})

    # no-dtb: copy control, zero dtb_size, drop payload pages
    nodtb_dir = out / "no-dtb"
    nodtb_dir.mkdir(exist_ok=True)
    nodtb_img = nodtb_dir / "experimental-boot-v2.img"
    shutil.copy2(control_img, nodtb_img)
    strip_dtb(nodtb_img)
    write_report(nodtb_dir, "no-dtb", nodtb_img, {"purpose": "dtb_size=0, no DTB pages"})

    sums = []
    diffs = ["variant vs control (header fields / payload sha)"]
    control_parse = json.loads((control_dir / "parse.json").read_text())
    for name in ["control", "no-dtb", "bad-dtb", "marker-dtb", "qc-ids", "cmdline-probe"]:
        img = out / name / "experimental-boot-v2.img"
        digest = sha256_path(img)
        sums.append(f"{digest}  {name}/experimental-boot-v2.img")
        p = json.loads((out / name / "parse.json").read_text())
        diffs.append(
            f"{name}: size={p['layout']['file_size']} "
            f"dtb_size={p['header']['dtb_size']} "
            f"dtb_sha={p['payloads']['dtb_sha256']} "
            f"cmd_marker={'route_a_cmdline_probe=1' in p['header']['cmdline']}"
        )
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    (out / "image-diff.txt").write_text("\n".join(diffs) + "\n")
    meta = {
        "control_image_sha256": control_parse["image_sha256"],
        "kernel_sha256": sha256_path(kernel),
        "ramdisk_sha256": sha256_path(ramdisk),
        "dtb_sha256": sha256_path(dtb),
        "variants": [s.split()[-1] for s in sums],
    }
    (out / "build-metadata.txt").write_text(json.dumps(meta, indent=2) + "\n")
    print("variants packed", meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
