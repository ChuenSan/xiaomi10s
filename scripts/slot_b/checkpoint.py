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
TARGETS = {"rest_init": 0x10C1F48, "kernel_init": 0x10C2030,
           "kernel_init_freeable": 0x1B3103C, "smp_init": 0x1B466E0}
PROOF_BOUNDARIES = {
    "rest_init": ("rest_init entry and preceding normal start_kernel path",
                  "rest_init body, scheduler, SMP or /init"),
    "kernel_init": ("PID1 initialization task created and scheduled at kernel_init entry",
                    "kthreadd_done wait completed, kernel_init_freeable, SMP or /init"),
    "kernel_init_freeable": ("PID1 kthreadd_done wait completed and kernel_init_freeable entered",
                             "kernel_init_freeable body, SMP, driver initcalls or /init"),
    "smp_init": ("PID1 reached smp_init after pre-SMP initialization",
                 "SMP bring-up completed, driver initcalls, initramfs readiness or /init"),
}
REST8_SHA = "22086188014e015c2aa0c79783a06de1036234e211064415dbd18e896ae04360"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compact_core(core):
    require(len(core) == 76, "INVALID_REFERENCE_CORE_SIZE")
    require(struct.unpack_from("<III", core, 44) == (0x54000062, 0xD503203F, 0x17FFFFFA),
            "REFERENCE_POLL_LOOP_MISMATCH")
    return core[:44] + struct.pack("<I", 0x54FFFF83) + core[56:]


def gate_smp_literal_delta(bundle, frozen, refs):
    require(len(bundle) == len(frozen) == 72, "SMP_LITERAL_WINDOW_SIZE")
    require(bundle[:28] == frozen[:28] and bundle[32:] == frozen[32:],
            "SMP_LITERAL_ADDITIONAL_CODE_DRIFT")
    require(struct.unpack_from("<III", bundle, 24) == (0xD0FFF740, 0x912DC000, 0x97D5CD80)
            and struct.unpack_from("<III", frozen, 24) == (0xD0FFF740, 0x912DE000, 0x97D5CD80),
            "SMP_LITERAL_INSTRUCTION_CONTEXT")
    expected = b"\x016smp: Bringing up secondary CPUs ...\n\0".hex()
    for name, offset in (("bundle", "0x1a30b70"), ("frozen", "0x1a30b78")):
        require(refs[name]["offset"] == offset and refs[name]["bytes_hex"] == expected,
                "SMP_LITERAL_SOURCE_STRING_MISMATCH")


def delay_core(core, delay):
    require(delay in (1, 8) and len(core) in (68, 76), "INVALID_DELAY_CORE")
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
    if args.symbol != "rest_init":
        core = compact_core(core)
        require(args.compact_core is not None and args.compact_core.read_bytes() == core,
                "COMPACT_CORE_ASSEMBLY_MISMATCH")
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
    dump = pb.run([TOOLS["objdump"], "-d", f"--start-address={target_va:#x}",
                   f"--stop-address={target_va + length:#x}", str(vmlinux)])
    (out / "original-window.txt").write_text(dump)
    (out / "original-function.txt").write_text(pb.run(
        [TOOLS["objdump"], "-d", f"--start-address={target_va:#x}",
         f"--stop-address={extent:#x}", str(vmlinux)]))
    differences = [{"offset": hex(i), "bundle": hex(struct.unpack_from("<I", image, i)[0]),
                    "frozen": hex(struct.unpack_from("<I", frozen, i)[0])}
                   for i in range(offset, offset + length, 4)
                   if image[i:i + 4] != frozen[i:i + 4]]
    agreement = {"symbol": args.symbol, "offset": hex(offset), "size": length,
                 "bundle_image_sha256": digest(image), "frozen_payload_sha256": digest(frozen),
                 "differing_words": differences}
    if args.symbol == "smp_init":
        agreement["log_literal_refs"] = {}
        for name, data in (("bundle", image), ("frozen", frozen)):
            add = struct.unpack_from("<I", data, offset + 28)[0]
            literal = 0x1A30000 + ((add >> 10) & 0xFFF)
            end = data.find(b"\0", literal, literal + 128)
            agreement["log_literal_refs"][name] = {
                "offset": hex(literal), "add_word": hex(add),
                "bytes_hex": data[literal:end + 1].hex() if end >= 0 else None,
                "text": data[literal:end].decode("ascii", "backslashreplace") if end >= 0 else None}
    agreement["verdict"] = "EXACT" if not differences else "UNRESOLVED"
    try:
        if differences:
            require(args.symbol == "smp_init", f"TARGET_WINDOW_DIFFERS_FROM_AUDIT_IMAGE:{differences}")
            gate_smp_literal_delta(image[offset:offset + length], frozen[offset:offset + length],
                                   agreement["log_literal_refs"])
            require(branch_target(struct.unpack_from("<I", frozen, offset + 32)[0], target_va + 32)
                    == t3.nm_symbol(nm, "_printk"), "SMP_LITERAL_CALL_NOT_PRINTK")
            agreement["verdict"] = "SMP_PRINTK_LITERAL_ADDRESS_DELTA_VERIFIED"
    finally:
        (out / "window-agreement.json").write_text(json.dumps(agreement, indent=2) + "\n")
    t3.gate_window_bytes_agree(target_va, offset, dump, image, length // 4)
    sections = t3.section_map(out, TOOLS, vmlinux)
    section = t3.gate_window_section_scan(target_va, length, sections)
    t3.gate_function_extent_scan(target_va, length, extent)
    t3.gate_window_symbol_scan(target_va, length, [va for va, _ in t3.symbol_table(nm)])
    window = (target_va, target_va + length)
    ranges = [(s["vma"] - text_va, s["vma"] - text_va + s["size"])
              for s in sections if s["code"] and s["alloc"]]
    incoming = incoming_branches(frozen[:len(image)], ranges, text_va, window)
    require(not incoming, f"BRANCH_INTO_OVERWRITE_INTERIOR:{[(hex(a), hex(b)) for a, b in incoming[:8]]}")
    t3.gate_window_literal_scan(target_va, length, frozen[:len(image)])
    sites = relocation_sites(vmlinux, sections)
    t3.gate_window_relocation_scan(target_va, length, sites)
    rewrites = audit_rewrites(out, vmlinux, sections, window)
    require(digest(vmlinux.read_bytes()) == metadata["files"]["vmlinux"], "AUDIT_MUTATED_VMLINUX")
    image_size = pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    t3.gate_window_inside_image_size(offset, length, image_size)
    candidate = patch_window(frozen, offset, probe)
    reference = patch_window(frozen, offset, probe[:4] + reference_core)
    expected_reference = args.reference_sha or (REST8_SHA if args.symbol == "rest_init" else None)
    require(args.delay == 8 or expected_reference is not None, "MATCHED_8S_REFERENCE_REQUIRED")
    if expected_reference is not None:
        require(digest(reference) == expected_reference, "FROZEN_8S_REFERENCE_MISMATCH")
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
                "core_variant": "original_b_hs" if args.symbol == "rest_init" else "compact_b_lo",
                "pair_reference_sha256": digest(reference),
                "pair_changed_offsets": [offset + 4 + i for i in pair_diff],
                "frozen_sha256": digest(frozen), "changed_bytes": len(changed),
                "outside_window_changed_bytes": 0, "runtime_rewrites": rewrites,
                "window_agreement": agreement,
                "relocation_sites_checked": len(sites), "audit_elf_unchanged": True,
                "source_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                "bundle": metadata, "normal_boot_candidate": False,
                "positive_proves": PROOF_BOUNDARIES[args.symbol][0],
                "positive_does_not_prove": PROOF_BOUNDARIES[args.symbol][1],
                "init_symbols": {name: hex(t3.nm_symbol(nm, name)) for name in
                                 ("rest_init", "kernel_init", "kernel_init_freeable", "smp_init")},
                "device_operation": False}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "SHA256SUMS").write_text("".join(f"{digest((out / n).read_bytes())}  {n}\n"
                                           for n in ("payload.bin", "checkpoint.bin", "manifest.json")))
    print(json.dumps(manifest, indent=2), flush=True)
    print(f"{args.symbol.upper()}_INLINE_AUDIT=PASS\nDEVICE_OPERATION=NO\nLOCAL_BUILD=NO", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--symbol", choices=TARGETS, default="rest_init")
    parser.add_argument("--delay", type=int, choices=(1, 8), default=8)
    parser.add_argument("--reference-sha")
    parser.add_argument("--compact-core", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out-slot-b-checkpoint"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    compose(args, args.bundle or build_bundle(args.out))


if __name__ == "__main__":
    main()
