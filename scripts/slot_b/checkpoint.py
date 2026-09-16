#!/usr/bin/env python3
"""GHA-only FIX8 checkpoint composition with a reusable kernel audit bundle."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GitHub Actions required; no local build or composition")

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("checkpoint_t3", ROOT / "scripts/r3-p1b/p1b-t3-predevice.py")
t3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t3)
pb = t3.pb
TOOLS = {"nm": "llvm-nm-18", "objdump": "llvm-objdump-18", "readelf": "llvm-readelf-18",
         "objcopy": "llvm-objcopy-18", "clang": "clang-18", "lld": "ld.lld-18"}
CORE_SHA = "4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611"
TARGETS = {"rest_init": 0x10C1F48}
REST8_SHA = "22086188014e015c2aa0c79783a06de1036234e211064415dbd18e896ae04360"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def delay_core(core, delay):
    require(delay in (1, 8) and len(core) == 76, "INVALID_DELAY_CORE")
    require(struct.unpack_from("<I", core, 12)[0] == 0xD280010A, "REFERENCE_DELAY_NOT_8")
    return core[:12] + struct.pack("<I", 0xD280000A | (delay << 5)) + core[16:]


def branch_target(word, pc):
    if word & 0x7C000000 == 0x14000000:  # B / BL
        return pc + pb.sx(word & 0x03FFFFFF, 26) * 4
    if word & 0xFF000010 == 0x54000000:  # B.cond
        return pc + pb.sx((word >> 5) & 0x7FFFF, 19) * 4
    if word & 0x7E000000 == 0x34000000:  # CBZ / CBNZ
        return pc + pb.sx((word >> 5) & 0x7FFFF, 19) * 4
    if word & 0x7E000000 == 0x36000000:  # TBZ / TBNZ
        return pc + pb.sx((word >> 5) & 0x3FFF, 14) * 4
    return None


def incoming_branches(image, ranges, text_va, window):
    lo, hi = window
    hits = []
    for begin, end in ranges:
        for off in range(max(0, begin), min(len(image), end) - 3, 4):
            pc = text_va + off
            target = branch_target(struct.unpack_from("<I", image, off)[0], pc)
            if target is not None and lo < target < hi and not lo <= pc < hi:
                hits.append((pc, target))
    return hits


def patch_window(frozen, offset, probe):
    require(0 <= offset and offset + len(probe) <= len(frozen), "WINDOW_OUT_OF_BOUNDS")
    return frozen[:offset] + probe + frozen[offset + len(probe):]


def build_bundle(out):
    require(pb.run(["git", "-C", str(pb.LINUX), "rev-parse", "HEAD"]).strip() == pb.LINUX_BASE,
            "LINUX_SOURCE_PIN_MISMATCH")
    patches = sorted((ROOT / "patches/linux-6.6").glob("*.patch"))
    queue_sha = digest("".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in patches).encode())
    require(queue_sha == pb.PATCH_QUEUE_SHA, "PATCH_QUEUE_MISMATCH")
    for patch in patches:
        pb.run(["git", "-C", str(pb.LINUX), "apply", "--check", str(patch)])
        pb.run(["git", "-C", str(pb.LINUX), "apply", str(patch)])
    init = pb.compile_init(out, 8, "aarch64-linux-gnu-gcc", "aarch64-linux-gnu-strip")
    require(digest(init.read_bytes()) == t3.FIX8_INIT_SHA, "INIT_NOT_FROZEN_FIX8")
    cpio = out / "initramfs.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    require(digest(cpio.read_bytes()) == t3.FIX8_CPIO_SHA, "CPIO_NOT_FROZEN_FIX8")
    kernel = pb.make_kernel(out, 8, cpio, os.cpu_count() or 2)
    pb.kernel_gate(kernel["image"], kernel["vmlinux"], kernel["sysmap"], TOOLS)
    bundle = out / "kernel-bundle"
    bundle.mkdir()
    for key, name in (("image", "Image"), ("vmlinux", "vmlinux"),
                      ("sysmap", "System.map"), ("config", "kernel.config")):
        shutil.copyfile(kernel[key], bundle / name)
    manifest = {"linux_base": pb.LINUX_BASE, "patch_queue_sha256": queue_sha,
                "source_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                "files": {name: digest((bundle / name).read_bytes())
                          for name in ("Image", "vmlinux", "System.map", "kernel.config")}}
    (bundle / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("KERNEL_AUDIT_BUNDLE_PRESERVED=YES", flush=True)
    return bundle


def section_bytes(vmlinux, section):
    with vmlinux.open("rb") as stream:
        stream.seek(section["file_off"])
        data = stream.read(section["size"])
    require(len(data) == section["size"], f"INCOMPLETE_SECTION:{section['name']}")
    return data


def decode_relr(data):
    require(len(data) % 8 == 0, "INVALID_RELR_SIZE")
    where = None
    sites = []
    for (entry,) in struct.iter_unpack("<Q", data):
        if not entry & 1:
            sites.append(entry)
            where = entry + 8
        else:
            require(where is not None, "RELR_BITMAP_WITHOUT_BASE")
            sites.extend(where + bit * 8 for bit in range(63) if entry & (1 << (bit + 1)))
            where += 63 * 8
    return sites


def relocation_sites(vmlinux, sections):
    text = pb.run([TOOLS["readelf"], "-r", "--wide", str(vmlinux)])
    sites = [int(match.group(1), 16) for line in text.splitlines()
             if (match := t3.RELOC_OFF_RE.match(line.strip()))]
    relr = next((s for s in sections if s["name"] == ".relr.dyn"), None)
    if relr is not None:
        sites.extend(decode_relr(section_bytes(vmlinux, relr)))
    return sorted(set(sites))


def audit_rewrites(out, vmlinux, sections, window):
    report = {}
    for name, tag, decoder in t3.RUNTIME_REWRITE_SECTIONS:
        section = next((s for s in sections if s["name"] == name), None)
        if section is None:
            report[tag] = "ABSENT"
            continue
        path = out / ("table-" + tag + ".bin")
        data = section_bytes(vmlinux, section)
        path.write_bytes(data)
        entries = decoder(data, section["vma"])
        t3.gate_table_entries(tag, entries, window)
        if name == ".altinstructions":
            for off in range(0, len(data) - 11, 12):
                start = section["vma"] + off + struct.unpack_from("<i", data, off)[0]
                end = start + data[off + 10]
                require(end <= window[0] or start >= window[1], "ALTERNATIVE_OVERLAPS_WINDOW")
        report[tag] = {"entries": len(entries), "sha256": digest(data)}
    return report


def compose(args, bundle):
    out = args.out / "checkpoint"
    out.mkdir()
    metadata = json.loads((bundle / "bundle.json").read_text())
    require(metadata["linux_base"] == pb.LINUX_BASE, "BUNDLE_SOURCE_MISMATCH")
    require(metadata["patch_queue_sha256"] == pb.PATCH_QUEUE_SHA, "BUNDLE_PATCH_QUEUE_MISMATCH")
    for name, expected in metadata["files"].items():
        require(digest((bundle / name).read_bytes()) == expected, f"BUNDLE_HASH_MISMATCH:{name}")
    frozen = args.frozen.read_bytes()
    core = args.core.read_bytes()
    require(digest(frozen) == t3.FIX8_PAYLOAD_SHA, "FROZEN_PAYLOAD_MISMATCH")
    require(len(core) == 76 and digest(core) == CORE_SHA, "CHECKPOINT_CORE_MISMATCH")
    reference_core = core
    core = delay_core(core, args.delay)
    image = (bundle / "Image").read_bytes()
    require(len(image) == t3.FIX8_IMAGE_FILE_SIZE, "AUDIT_IMAGE_SIZE_DRIFT")
    vmlinux = bundle / "vmlinux"
    nm = pb.run([TOOLS["nm"], str(vmlinux)])
    text_va = t3.nm_symbol(nm, "_text")
    target_va, extent = t3.symbol_extent(nm, args.symbol)
    offset = target_va - text_va
    require(offset == TARGETS[args.symbol], "TARGET_OFFSET_DIFFERS_FROM_FROZEN_MAP")
    require(t3.sysmap_symbol(bundle / "System.map", args.symbol) == target_va, "SYMBOL_MAP_MISMATCH")
    cfg = t3.config_symbols((bundle / "kernel.config").read_text())
    word0, word1 = struct.unpack_from("<II", frozen, offset)
    pad = t3.gate_sk_entry_insn(word0, word1, word0)
    t3.gate_instrumentation_audit(cfg, pad.split()[0], word0)
    probe = frozen[offset:offset + 4] + core
    length = len(probe)
    require(image[offset:offset + length] == frozen[offset:offset + length],
            "TARGET_WINDOW_DIFFERS_FROM_AUDIT_IMAGE")
    dump = pb.run([TOOLS["objdump"], "-d", f"--start-address={target_va:#x}",
                   f"--stop-address={target_va + length:#x}", str(vmlinux)])
    (out / "original-window.txt").write_text(dump)
    t3.gate_window_bytes_agree(target_va, offset, dump, frozen, length // 4)
    sections = t3.section_map(out, TOOLS, vmlinux)
    section = t3.gate_window_section_scan(target_va, length, sections)
    t3.gate_function_extent_scan(target_va, length, extent)
    t3.gate_window_symbol_scan(target_va, length, [va for va, _ in t3.symbol_table(nm)])
    window = (target_va, target_va + length)
    ranges = [(s["vma"] - text_va, s["vma"] - text_va + s["size"])
              for s in sections if s["code"] and s["alloc"]]
    incoming = incoming_branches(frozen[:len(image)], ranges, text_va, window)
    require(not incoming, f"BRANCH_INTO_OVERWRITE_INTERIOR:{incoming[:8]}")
    t3.gate_window_literal_scan(target_va, length, frozen[:len(image)])
    sites = relocation_sites(vmlinux, sections)
    t3.gate_window_relocation_scan(target_va, length, sites)
    rewrites = audit_rewrites(out, vmlinux, sections, window)
    require(digest(vmlinux.read_bytes()) == metadata["files"]["vmlinux"], "AUDIT_MUTATED_VMLINUX")
    image_size = pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    t3.gate_window_inside_image_size(offset, length, image_size)
    candidate = patch_window(frozen, offset, probe)
    reference = patch_window(frozen, offset, probe[:4] + reference_core)
    require(digest(reference) == REST8_SHA, "FROZEN_REST8_REFERENCE_MISMATCH")
    pair_diff = [i for i, (a, b) in enumerate(zip(reference_core, core)) if a != b]
    require(pair_diff == ([12, 13] if args.delay == 1 else []), "PAIR_NOT_DELAY_ONLY")
    t3.gate_tail_identity(frozen, candidate, (offset, offset + length))
    changed = t3.gate_payload_diff(frozen, candidate, (offset, offset + length))
    t3.gate_tramp_identity(candidate)
    dtb_offset, _ = pb.calc_dtb_offset(image_size)
    pb.gate_rt_d(candidate[dtb_offset:])
    (out / "payload.bin").write_bytes(candidate)
    (out / "checkpoint.bin").write_bytes(probe)
    manifest = {"symbol": args.symbol, "target_va": hex(target_va), "offset": offset,
                "checkpoint_size": length, "entry": pad, "section": section["name"],
                "payload_sha256": digest(candidate), "payload_size": len(candidate),
                "checkpoint_sha256": digest(probe), "core_sha256": digest(core),
                "reference_core_sha256": CORE_SHA, "delay_seconds": args.delay,
                "pair_reference_sha256": REST8_SHA,
                "pair_changed_offsets": [offset + 4 + i for i in pair_diff],
                "frozen_sha256": digest(frozen), "changed_bytes": len(changed),
                "outside_window_changed_bytes": 0, "runtime_rewrites": rewrites,
                "relocation_sites_checked": len(sites), "audit_elf_unchanged": True,
                "source_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                "bundle": metadata, "normal_boot_candidate": False,
                "positive_proves": "rest_init entry and preceding normal start_kernel path",
                "positive_does_not_prove": "rest_init body, scheduler, SMP or /init",
                "device_operation": False}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "SHA256SUMS").write_text("".join(f"{digest((out / n).read_bytes())}  {n}\n"
                                           for n in ("payload.bin", "checkpoint.bin", "manifest.json")))
    print(json.dumps(manifest, indent=2), flush=True)
    print("REST_INIT_INLINE_AUDIT=PASS\nDEVICE_OPERATION=NO\nLOCAL_BUILD=NO", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--symbol", choices=TARGETS, default="rest_init")
    parser.add_argument("--delay", type=int, choices=(1, 8), default=8)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out-slot-b-checkpoint"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    compose(args, args.bundle or build_bundle(args.out))


if __name__ == "__main__":
    main()
