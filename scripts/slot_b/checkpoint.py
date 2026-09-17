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
_rt_spec = importlib.util.spec_from_file_location("runtime_dtb", ROOT / "scripts/r3-p1/r3-runtime-dtb.py")
rt = importlib.util.module_from_spec(_rt_spec)
_rt_spec.loader.exec_module(rt)
TOOLS = {"nm": "llvm-nm-18", "objdump": "llvm-objdump-18", "readelf": "llvm-readelf-18",
         "objcopy": "llvm-objcopy-18", "clang": "clang-18", "lld": "ld.lld-18"}
CORE_SHA = "4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611"
TARGETS = {"rest_init": 0x10C1F48, "kernel_init": 0x10C2030,
           "kernel_init_freeable": 0x1B3103C, "smp_init": 0x1B466E0,
           "do_basic_setup": 0x1B311A8, "do_initcalls": 0x1B311D0,
           "console_on_rootfs": 0x1B30DA4}
INITCALL_BOUNDARIES = {"pure_complete": "__initcall1_start",
                       "core_complete": "__initcall2_start",
                       "postcore_complete": "__initcall3_start",
                       "arch_complete": "__initcall4_start"}
INITCALL_MACROS = {"pure_complete": "core_initcall", "core_complete": "postcore_initcall",
                   "postcore_complete": "arch_initcall", "arch_complete": "subsys_initcall"}
INITCALL_SOURCE_PREFIX = {"postcore_complete": "arch/arm64/"}
ULTRACOMPACT_SYMBOLS = frozenset({"core_complete", "postcore_complete", "arch_complete"})
INITCALL_BOUNDARY_SYMBOLS = ("__initcall1_start", "__initcall2_start", "__initcall3_start",
                             "__initcall4_start", "__initcall5_start")
INITCALL_TARGET_LABELS = {"pure_complete": "FIRST_CORE", "core_complete": "FIRST_POSTCORE",
                          "postcore_complete": "FIRST_ARCH", "arch_complete": "FIRST_SUBSYS"}
PROOF_BOUNDARIES = {
    "rest_init": ("rest_init entry and preceding normal start_kernel path",
                  "rest_init body, scheduler, SMP or /init"),
    "kernel_init": ("PID1 initialization task created and scheduled at kernel_init entry",
                    "kthreadd_done wait completed, kernel_init_freeable, SMP or /init"),
    "kernel_init_freeable": ("PID1 kthreadd_done wait completed and kernel_init_freeable entered",
                             "kernel_init_freeable body, SMP, driver initcalls or /init"),
    "smp_init": ("PID1 reached smp_init after pre-SMP initialization",
                 "SMP bring-up completed, driver initcalls, initramfs readiness or /init"),
    "do_basic_setup": ("smp_init and subsequent scheduler/workqueue topology setup returned",
                       "secondary CPU count, driver initcalls, initramfs readiness or /init"),
    "do_initcalls": ("SMP/topology and driver-core setup returned before main initcall levels",
                     "secondary CPU count, main initcall levels completed, initramfs readiness or /init"),
    "console_on_rootfs": ("main initcall path and wait_for_initramfs returned before console open",
                          "successful device probes, console open, executable /init or userspace entry"),
    "pure_complete": ("all pure initcalls completed and the first core initcall entry was reached",
                      "the first core initcall body, later initcall levels, initramfs readiness or /init"),
    "core_complete": ("all core initcalls completed and the first postcore initcall entry was reached",
                      "the first postcore initcall body, postcore completion, later levels, console or /init"),
    "postcore_complete": ("all postcore initcalls completed and the first arch initcall entry was reached",
                          "the first arch initcall body, arch completion, later levels, console or /init"),
    "arch_complete": ("all arch initcalls completed and the first subsys initcall entry was reached",
                      "the first subsys initcall body, subsys completion, later levels, console or /init"),
}
REST8_SHA = "22086188014e015c2aa0c79783a06de1036234e211064415dbd18e896ae04360"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def gate_builtin_initramfs_source(chosen):
    require(not {"linux,initrd-start", "linux,initrd-end"}.intersection(chosen),
            "EXTERNAL_INITRD_IN_RUNTIME_DTB")


def gate_checkpoint_design(design, stage):
    boundaries = {
        "core": ("FIRST_POSTCORE_INITCALL_EXACT_ENTRY", "__initcall2_start"),
        "postcore": ("FIRST_ARCH_INITCALL_EXACT_ENTRY", "__initcall3_start"),
        "arch": ("FIRST_SUBSYS_INITCALL_EXACT_ENTRY", "__initcall4_start"),
    }
    require(stage in boundaries, "CHECKPOINT_DESIGN_STAGE_INVALID")
    checkpoint_point, boundary = boundaries[stage]
    expected = {
        "checkpoint_point": checkpoint_point,
        "boundary": boundary, "target_derivation": "TABLE_ENTRY_DECODE",
        "entry_encoding": "PREL32", "cross_function_overwrite": False,
        "function_range_safe": True, "incoming_interior_branches": 0,
        "backedge_conflict": False, "runtime_rewrite_conflict": False,
        "literal_delta": "EXACT_OR_INDEPENDENTLY_PROVEN", "pair_diff": "DELAY_CONSTANT_ONLY",
        "timer": "CNTPCT", "psci_fid": "0x84000009", "timer_algorithm_changed": False,
        "prior_pure_probe": False, "prior_console_probe": False,
        "rt_d_sha256": "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327",
        "init_changed": False, "private_pack": False, "device_operation": False,
    }
    for key, value in expected.items():
        require(design.get(key) == value, f"{stage.upper()}_DESIGN_REJECTED:{key}")
    require(design.get("function_size", 0) >= design.get("probe_size", 1),
            f"{stage.upper()}_DESIGN_REJECTED:function_shorter_than_probe")


def gate_core_checkpoint_design(design):
    gate_checkpoint_design(design, "core")


def gate_postcore_checkpoint_design(design):
    gate_checkpoint_design(design, "postcore")


def gate_arch_checkpoint_design(design):
    gate_checkpoint_design(design, "arch")
    extra = {
        "reuse_core_narrow_gate": False, "reuse_postcore_probe_window": False,
        "prior_core_probe": False, "prior_postcore_probe": False,
        "copied_postcore_probe": False,
    }
    for key, value in extra.items():
        require(design.get(key) == value, f"ARCH_DESIGN_REJECTED:{key}")


def compact_core(core):
    require(len(core) == 76, "INVALID_REFERENCE_CORE_SIZE")
    require(struct.unpack_from("<III", core, 44) == (0x54000062, 0xD503203F, 0x17FFFFFA),
            "REFERENCE_POLL_LOOP_MISMATCH")
    return core[:44] + struct.pack("<I", 0x54FFFF83) + core[56:]


def literal_ref_pair(image, frozen, add_offset, page_offset):
    refs = {}
    for name, data in (("bundle", image), ("frozen", frozen)):
        add = struct.unpack_from("<I", data, add_offset)[0]
        literal = page_offset + ((add >> 10) & 0xFFF)
        end = data.find(b"\0", literal, literal + 128)
        refs[name] = {"offset": hex(literal), "add_word": hex(add),
                      "bytes_hex": data[literal:end + 1].hex() if end >= 0 else None,
                      "text": data[literal:end].decode("ascii", "backslashreplace") if end >= 0 else None}
    return refs


def adrp_add_literal_ref_pair(image, frozen, text_va, adrp_offset, add_offset):
    refs = {}
    for name, data in (("bundle", image), ("frozen", frozen)):
        adrp = struct.unpack_from("<I", data, adrp_offset)[0]
        add = struct.unpack_from("<I", data, add_offset)[0]
        require(adrp & 0x9F000000 == 0x90000000, "LITERAL_ADRP_INVALID")
        require(add & 0xFF000000 == 0x91000000 and not add & (1 << 22),
                "LITERAL_ADD_INVALID")
        imm21 = ((adrp >> 5) & 0x7FFFF) << 2 | ((adrp >> 29) & 3)
        page = ((text_va + adrp_offset) & ~0xFFF) + (pb.sx(imm21, 21) << 12)
        literal = page + ((add >> 10) & 0xFFF) - text_va
        require(0 <= literal < len(data), "LITERAL_OUTSIDE_IMAGE")
        end = data.find(b"\0", literal, literal + 128)
        refs[name] = {"offset": hex(literal), "va": hex(text_va + literal),
                      "adrp_word": hex(adrp), "add_word": hex(add),
                      "bytes_hex": data[literal:end + 1].hex() if end >= 0 else None,
                      "text": data[literal:end].decode("ascii", "backslashreplace") if end >= 0 else None}
    return refs


def gate_console_literal_deltas(bundle, frozen, refs):
    require(len(bundle) == len(frozen) == 72, "CONSOLE_LITERAL_WINDOW_SIZE")
    normalized = bytearray(frozen)
    for off in (20, 48):
        normalized[off:off + 4] = bundle[off:off + 4]
    require(normalized == bundle, "CONSOLE_LITERAL_ADDITIONAL_CODE_DRIFT")
    for off, adrp, old_add, new_add in ((16, 0xD0FFF460, 0x912C3000, 0x912C5000),
                                      (44, 0x90FFF540, 0x91022000, 0x91024000)):
        require(struct.unpack_from("<II", bundle, off) == (adrp, old_add)
                and struct.unpack_from("<II", frozen, off) == (adrp, new_add),
                "CONSOLE_LITERAL_INSTRUCTION_CONTEXT")
    specs = (("path", "0x19beb0c", "0x19beb14", b"/dev/console\0"),
             ("warning", "0x19d8088", "0x19d8090",
              b"\x013Warning: unable to open an initial console.\n\0"))
    for tag, old_offset, new_offset, text in specs:
        for name, expected in (("bundle", old_offset), ("frozen", new_offset)):
            require(refs[tag][name]["offset"] == expected and refs[tag][name]["bytes_hex"] == text.hex(),
                    "CONSOLE_LITERAL_SOURCE_STRING_MISMATCH")


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


def gate_initcall_literal_delta(bundle, frozen, refs):
    require(len(bundle) == len(frozen) == 72, "INITCALL_LITERAL_WINDOW_SIZE")
    require(bundle[:40] == frozen[:40] and bundle[44:] == frozen[44:],
            "INITCALL_LITERAL_ADDITIONAL_CODE_DRIFT")
    require(struct.unpack_from("<II", bundle, 36) == (0xB0FFF061, 0x913B7421)
            and struct.unpack_from("<II", frozen, 36) == (0xB0FFF061, 0x913B9421),
            "INITCALL_LITERAL_INSTRUCTION_CONTEXT")
    expected = b"arm64/fpsimd:dead\0".hex()
    for name, offset in (("bundle", "0x1940edd"), ("frozen", "0x1940ee5")):
        require(refs[name]["offset"] == offset and refs[name]["bytes_hex"] == expected,
                "INITCALL_LITERAL_SOURCE_STRING_MISMATCH")


def ultracompact_core(core):
    require(len(core) == 56, "INVALID_ULTRACOMPACT_CORE_SIZE")
    words = struct.unpack("<14I", core)
    expected = (0xD5034FDF, 0xD53BE009, 0xD37DF12A, 0xD53BE02B,
                0xD5033FDF, 0xD53BE02C, 0xCB0B018D, 0xEB0A01BF,
                0x54FFFF83, 0x52800120, 0x72B08000, 0xD4000003,
                0xD503205F, 0x17FFFFFF)
    require(words == expected, "ULTRACOMPACT_INSTRUCTION_SEQUENCE_MISMATCH")
    require(branch_target(words[8], 8 * 4) == 4 * 4, "ULTRACOMPACT_TIMER_LOOP_MISMATCH")
    return core


def gate_core_initcall_literal_delta(bundle, frozen, refs):
    require(len(bundle) == len(frozen) == 60, "CORE_INITCALL_LITERAL_WINDOW_SIZE")
    require(bundle[:16] == frozen[:16] and bundle[20:] == frozen[20:],
            "CORE_INITCALL_LITERAL_ADDITIONAL_CODE_DRIFT")
    require(struct.unpack_from("<II", bundle, 12) == (0x90FFF781, 0x91329421)
            and struct.unpack_from("<II", frozen, 12) == (0x90FFF781, 0x9132B421),
            "CORE_INITCALL_LITERAL_INSTRUCTION_CONTEXT")
    expected = b"arm64/debug_monitors:starting\0".hex()
    require(refs["bundle"]["bytes_hex"] == refs["frozen"]["bytes_hex"] == expected,
            "CORE_INITCALL_LITERAL_SOURCE_STRING_MISMATCH")
    require(refs["frozen"]["offset"] == hex(int(refs["bundle"]["offset"], 16) + 8),
            "CORE_INITCALL_LITERAL_LAYOUT_DELTA_NOT_EIGHT")


def delay_core(core, delay):
    require(delay in (1, 8) and len(core) in (56, 68, 76), "INVALID_DELAY_CORE")
    if len(core) == 56:
        require(struct.unpack_from("<I", core, 8)[0] == 0xD37DF12A, "REFERENCE_DELAY_NOT_8")
        word = 0xD37DF12A if delay == 8 else 0xD340FD2A
        return core[:8] + struct.pack("<I", word) + core[12:]
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


def pad_probe(probe, length):
    require(len(probe) % 4 == 0 and len(probe) <= length and length % 4 == 0,
            "INVALID_PROBE_WINDOW_LENGTH")
    return probe + struct.pack("<I", 0xD503201F) * ((length - len(probe)) // 4)


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


def vmlinux_bytes_at(vmlinux, sections, va, size):
    section = next((s for s in sections if s["vma"] <= va and va + size <= s["vma"] + s["size"]), None)
    require(section is not None, "VMLINUX_ADDRESS_OUTSIDE_SECTION")
    with vmlinux.open("rb") as stream:
        stream.seek(section["file_off"] + va - section["vma"])
        data = stream.read(size)
    require(len(data) == size, "VMLINUX_ADDRESS_READ_SHORT")
    return data


def resolve_initcall_boundary(vmlinux, sections, nm, boundary):
    entry_va = t3.nm_symbol(nm, boundary)
    relative = struct.unpack("<i", vmlinux_bytes_at(vmlinux, sections, entry_va, 4))[0]
    target_va = entry_va + relative
    aliases = sorted(name for va, name in t3.symbol_table(nm) if va == target_va)
    require(aliases, "INITCALL_TARGET_SYMBOL_MISSING")
    start = t3.nm_symbol(nm, "__initcall_start")
    end = t3.nm_symbol(nm, "__initcall_end")
    require(start <= entry_va < end and not (start | entry_va | end) & 3,
            "INITCALL_TABLE_BOUNDARY_INVALID")
    entries = []
    for va in range(start, end, 4):
        rel = struct.unpack("<i", vmlinux_bytes_at(vmlinux, sections, va, 4))[0]
        entries.append(va + rel)
    require(entries.count(target_va) == 1, "INITCALL_TARGET_NOT_UNIQUE_IN_TABLE")
    section = next(s for s in sections if s["vma"] <= entry_va < s["vma"] + s["size"])
    return {"boundary_symbol": boundary, "entry_va": entry_va,
            "entry_image_offset": entry_va - t3.nm_symbol(nm, "_text"),
            "entry_section": section["name"], "entry_size": 4,
            "entry_encoding": "PREL32", "relative": relative,
            "entry_word": hex(relative & 0xffffffff), "target_va": target_va,
            "target_aliases": aliases, "table_entries_checked": len(entries)}


def audit_initcall_source(linux):
    main = (linux / "init/main.c").read_text()
    linker = (linux / "include/asm-generic/vmlinux.lds.h").read_text()
    init_h = (linux / "include/linux/init.h").read_text()
    levels = re.search(r"initcall_levels\[\].*?=\s*\{(.*?)\};", main, re.S)
    names = re.search(r"initcall_level_names\[\].*?=\s*\{(.*?)\};", main, re.S)
    require(levels is not None and re.findall(r"__initcall(?:\d+|_end)_start|__initcall_end",
            levels.group(1)) == ["__initcall0_start", "__initcall1_start", "__initcall2_start",
                                  "__initcall3_start", "__initcall4_start", "__initcall5_start",
                                  "__initcall6_start", "__initcall7_start", "__initcall_end"],
            "INITCALL_LEVEL_ARRAY_SOURCE_MISMATCH")
    require(names is not None and re.findall(r'"([a-z]+)"', names.group(1)) ==
            ["pure", "core", "postcore", "arch", "subsys", "fs", "device", "late"],
            "INITCALL_LEVEL_NAMES_SOURCE_MISMATCH")
    require(re.search(r"for\s*\(fn\s*=\s*initcall_levels\[level\];\s*"
                      r"fn\s*<\s*initcall_levels\[level\+1\];\s*fn\+\+\)", main),
            "INITCALL_ITERATION_SOURCE_MISMATCH")
    linker_levels = re.search(r"#define INIT_CALLS\b.*?__initcall_end\s*=\s*\.;", linker, re.S)
    require(linker_levels is not None and re.findall(r"INIT_CALLS_LEVEL\(([^)]+)\)",
            linker_levels.group(0)) == ["0", "1", "2", "3", "4", "5", "rootfs", "6", "7"],
            "INITCALL_LINKER_ORDER_SOURCE_MISMATCH")
    require("#ifdef CONFIG_HAVE_ARCH_PREL32_RELOCATIONS" in init_h and
            "typedef int initcall_entry_t;" in init_h and
            re.search(r'\.long.*__stringify\(__stub\).*" - \.', init_h, re.S),
            "INITCALL_PREL32_SOURCE_MISMATCH")
    require(re.search(r"#define\s+arch_initcall\s*\(\s*fn\s*\)\s*__define_initcall\s*\(\s*fn\s*,\s*3\s*\)",
                      init_h), "ARCH_INITCALL_LEVEL_MACRO_MISMATCH")
    require(re.search(r"#define\s+subsys_initcall\s*\(\s*fn\s*\)\s*__define_initcall\s*\(\s*fn\s*,\s*4\s*\)",
                      init_h), "SUBSYS_INITCALL_LEVEL_MACRO_MISMATCH")
    kconfig = (linux / "arch/arm64/Kconfig").read_text()
    require(re.search(r"^\s*select\s+HAVE_ARCH_PREL32_RELOCATIONS\b", kconfig, re.M),
            "ARM64_PREL32_KCONFIG_MISSING")
    return {"pure": "__initcall0_start..__initcall1_start",
            "core": "__initcall1_start..__initcall2_start",
            "postcore": "__initcall2_start..__initcall3_start",
            "arch": "__initcall3_start..__initcall4_start",
            "subsys": "__initcall4_start..__initcall5_start",
            "pure_level_boundary": "__initcall1_start",
            "core_level_boundary": "__initcall2_start",
            "postcore_level_boundary": "__initcall3_start",
            "arch_level_boundary": "__initcall4_start",
            "subsys_level_boundary": "__initcall5_start",
            "core_complete_boundary_source_proven": True,
            "postcore_complete_boundary_source_proven": True,
            "arch_complete_boundary_source_proven": True,
            "first_subsys_entry_implies_arch_complete": True,
            "entry_encoding_source": "CONFIG_HAVE_ARCH_PREL32_RELOCATIONS => s32 .long target-."}


def find_initcall_source(linux, aliases, macro, source_prefix=None):
    hits = []
    patterns = [re.compile(rf"\b{re.escape(macro)}(?:_sync)?\s*\(\s*{re.escape(name)}\s*\)")
                for name in aliases]
    for path in linux.rglob("*"):
        if path.suffix not in (".c", ".h") or not path.is_file():
            continue
        relative = str(path.relative_to(linux))
        if source_prefix is not None and not relative.startswith(source_prefix):
            continue
        text = path.read_text(errors="replace")
        if any(pattern.search(text) for pattern in patterns):
            hits.append(relative)
    require(len(hits) == 1, f"INITCALL_SOURCE_NOT_UNIQUE:{hits}")
    return hits[0]


def branch_audit(image, ranges, text_va, function, window):
    f_lo, f_hi = function
    w_lo, w_hi = window
    incoming_entry, incoming_interior, internal, back_edges = [], [], [], []
    for begin, end in ranges:
        for off in range(max(0, begin), min(len(image), end) - 3, 4):
            pc = text_va + off
            target = branch_target(struct.unpack_from("<I", image, off)[0], pc)
            if target is None:
                continue
            if not f_lo <= pc < f_hi and target == f_lo:
                incoming_entry.append((pc, target))
            if not w_lo <= pc < w_hi and w_lo < target < w_hi:
                incoming_interior.append((pc, target))
            if f_lo <= pc < f_hi and f_lo <= target < f_hi:
                internal.append((pc, target))
                if target < pc:
                    back_edges.append((pc, target))
    hx = lambda rows: [[hex(a), hex(b)] for a, b in rows]
    return {"incoming_entry": hx(incoming_entry), "incoming_window_interior": hx(incoming_interior),
            "internal_branches": hx(internal), "back_edges": hx(back_edges)}


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
    image_size = pb.parse_image_hdr(frozen, "FIX8")["image_size"]
    dtb_offset, _ = pb.calc_dtb_offset(image_size)
    pb.gate_rt_d(frozen[dtb_offset:])
    chosen = rt.parse_fdt(frozen[dtb_offset:])["/chosen"]
    gate_builtin_initramfs_source(chosen)
    (out / "initramfs-source.json").write_text(json.dumps(
        {"external_initrd_advertised": False, "chosen_properties": sorted(chosen),
         "rt_d_sha256": digest(frozen[dtb_offset:])}, indent=2) + "\n")
    require(len(core) == 76 and digest(core) == CORE_SHA, "CHECKPOINT_CORE_MISMATCH")
    if args.symbol in ULTRACOMPACT_SYMBOLS:
        require(args.ultracompact_core is not None, "ULTRACOMPACT_CORE_REQUIRED")
        core = ultracompact_core(args.ultracompact_core.read_bytes())
    elif args.symbol != "rest_init":
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
    sections = t3.section_map(out, TOOLS, vmlinux)
    initcall_boundary = None
    if args.symbol in INITCALL_BOUNDARIES:
        source_audit = audit_initcall_source(pb.LINUX)
        initcall_boundaries = {name: resolve_initcall_boundary(vmlinux, sections, nm, name)
                               for name in INITCALL_BOUNDARY_SYMBOLS}
        initcall_boundary = initcall_boundaries[INITCALL_BOUNDARIES[args.symbol]]
        target_va = initcall_boundary["target_va"]
        target_symbol = initcall_boundary["target_aliases"][0]
        next_va = min(va for va, _ in t3.symbol_table(nm) if va > target_va)
        extent = next_va
        initcall_source = find_initcall_source(
            pb.LINUX, initcall_boundary["target_aliases"],
            INITCALL_MACROS[args.symbol], INITCALL_SOURCE_PREFIX.get(args.symbol))
        initcall_registration = f"{INITCALL_MACROS[args.symbol]}({target_symbol})"
        require(t3.sysmap_symbol(bundle / "System.map", target_symbol) == target_va,
                "SYMBOL_MAP_MISMATCH")
    else:
        source_audit = initcall_boundaries = initcall_source = initcall_registration = None
        target_symbol = args.symbol
        target_va, extent = t3.symbol_extent(nm, target_symbol)
        require(target_va - text_va == TARGETS[args.symbol],
                "TARGET_OFFSET_DIFFERS_FROM_FROZEN_MAP")
        require(t3.sysmap_symbol(bundle / "System.map", target_symbol) == target_va,
                "SYMBOL_MAP_MISMATCH")
    offset = target_va - text_va
    cfg = t3.config_symbols((bundle / "kernel.config").read_text())
    word0, word1 = struct.unpack_from("<II", frozen, offset)
    pad = t3.gate_sk_entry_insn(word0, word1, word0)
    t3.gate_instrumentation_audit(cfg, pad.split()[0], word0)
    probe = frozen[offset:offset + 4] + core
    probe = pad_probe(probe, 96 if args.symbol == "do_initcalls" else len(probe))
    length = len(probe)
    dump = pb.run([TOOLS["objdump"], "-d", f"--start-address={target_va:#x}",
                   f"--stop-address={target_va + length:#x}", str(vmlinux)])
    (out / "original-window.txt").write_text(dump)
    function_dump = pb.run([TOOLS["objdump"], "-dr", f"--start-address={target_va:#x}",
                            f"--stop-address={extent:#x}", str(vmlinux)])
    (out / "original-function.txt").write_text(function_dump)
    ranges = [(s["vma"] - text_va, s["vma"] - text_va + s["size"])
              for s in sections if s["code"] and s["alloc"]]
    topology = branch_audit(frozen[:len(image)], ranges, text_va,
                            (target_va, extent), (target_va, target_va + length))
    target_section = next(s for s in sections if s["vma"] <= target_va < s["vma"] + s["size"])
    entry_words = [hex(struct.unpack_from("<I", frozen, offset + i)[0])
                   for i in range(0, min(128, extent - target_va), 4)]
    target_audit = {"symbol": target_symbol,
                    "aliases": initcall_boundary["target_aliases"] if initcall_boundary else [target_symbol],
                    "source": initcall_source, "registration": initcall_registration,
                    "target_va": hex(target_va),
                    "image_offset": hex(offset), "section": target_section["name"],
                    "function_size": extent - target_va, "entry_instruction": pad,
                    "entry_bytes": frozen[offset:offset + 4].hex(),
                    "first_32_instruction_words": entry_words,
                    "pac": pad.startswith("paciasp"), "bti": pad.startswith("bti"),
                    "scs": cfg.get("CONFIG_SHADOW_CALL_STACK") == "y",
                    "cfi": cfg.get("CONFIG_CFI_CLANG") == "y",
                    "fentry": cfg.get("CONFIG_FUNCTION_TRACER") == "y",
                    "stack_frame_in_window": any("stp\tx29, x30" in line for line in dump.splitlines()),
                    "branch_topology": topology,
                    "literal_load_words": [word for word in entry_words
                        if int(word, 16) & 0x3b000000 == 0x18000000]}
    (out / "target-entry-audit.json").write_text(json.dumps(target_audit, indent=2) + "\n")
    print(INITCALL_TARGET_LABELS.get(args.symbol, args.symbol.upper()) +
          "_TARGET_PRELIMINARY=" + json.dumps(target_audit, sort_keys=True), flush=True)
    differences = [{"offset": hex(i), "bundle": hex(struct.unpack_from("<I", image, i)[0]),
                    "frozen": hex(struct.unpack_from("<I", frozen, i)[0])}
                   for i in range(offset, offset + length, 4)
                   if image[i:i + 4] != frozen[i:i + 4]]
    agreement = {"symbol": args.symbol, "offset": hex(offset), "size": length,
                 "bundle_image_sha256": digest(image), "frozen_payload_sha256": digest(frozen),
                 "differing_words": differences}
    if args.symbol == "smp_init":
        agreement["log_literal_refs"] = literal_ref_pair(image, frozen, offset + 28, 0x1A30000)
    elif args.symbol == "console_on_rootfs":
        agreement["console_literal_refs"] = {
            "path": literal_ref_pair(image, frozen, offset + 20, 0x19BE000),
            "warning": literal_ref_pair(image, frozen, offset + 48, 0x19D8000)}
    elif args.symbol == "pure_complete":
        agreement["initcall_name_literal_refs"] = adrp_add_literal_ref_pair(
            image, frozen, text_va, offset + 36, offset + 40)
    elif args.symbol == "core_complete":
        agreement["core_initcall_name_literal_refs"] = adrp_add_literal_ref_pair(
            image, frozen, text_va, offset + 12, offset + 16)
    agreement["verdict"] = "EXACT" if not differences else "UNRESOLVED"
    try:
        if differences and args.symbol == "smp_init":
            gate_smp_literal_delta(image[offset:offset + length], frozen[offset:offset + length],
                                   agreement["log_literal_refs"])
            require(branch_target(struct.unpack_from("<I", frozen, offset + 32)[0], target_va + 32)
                    == t3.nm_symbol(nm, "_printk"), "SMP_LITERAL_CALL_NOT_PRINTK")
            agreement["verdict"] = "SMP_PRINTK_LITERAL_ADDRESS_DELTA_VERIFIED"
        elif differences and args.symbol == "console_on_rootfs":
            gate_console_literal_deltas(image[offset:offset + length], frozen[offset:offset + length],
                                        agreement["console_literal_refs"])
            for call_offset, callee in ((32, "filp_open"), (52, "_printk")):
                require(branch_target(struct.unpack_from("<I", frozen, offset + call_offset)[0],
                                      target_va + call_offset) == t3.nm_symbol(nm, callee),
                        "CONSOLE_LITERAL_CALL_TARGET_MISMATCH")
            agreement["verdict"] = "CONSOLE_LITERAL_ADDRESS_DELTAS_VERIFIED"
        elif differences and args.symbol == "pure_complete":
            gate_initcall_literal_delta(image[offset:offset + length], frozen[offset:offset + length],
                                        agreement["initcall_name_literal_refs"])
            require(branch_target(struct.unpack_from("<I", frozen, offset + 68)[0], target_va + 68)
                    == t3.nm_symbol(nm, "__cpuhp_setup_state"),
                    "INITCALL_LITERAL_CALL_TARGET_MISMATCH")
            agreement["verdict"] = "INITCALL_NAME_LITERAL_ADDRESS_DELTA_VERIFIED"
        elif differences and args.symbol == "core_complete":
            gate_core_initcall_literal_delta(
                image[offset:offset + length], frozen[offset:offset + length],
                agreement["core_initcall_name_literal_refs"])
            require(branch_target(struct.unpack_from("<I", frozen, offset + 44)[0], target_va + 44)
                    == t3.nm_symbol(nm, "__cpuhp_setup_state"),
                    "CORE_INITCALL_LITERAL_CALL_TARGET_MISMATCH")
            agreement["verdict"] = "CORE_INITCALL_NAME_LITERAL_ADDRESS_DELTA_VERIFIED"
        else:
            require(not differences, f"TARGET_WINDOW_DIFFERS_FROM_AUDIT_IMAGE:{differences}")
    finally:
        (out / "window-agreement.json").write_text(json.dumps(agreement, indent=2) + "\n")
    t3.gate_window_bytes_agree(target_va, offset, dump, image, length // 4)
    section = t3.gate_window_section_scan(target_va, length, sections)
    t3.gate_function_extent_scan(target_va, length, extent)
    t3.gate_window_symbol_scan(target_va, length, [va for va, _ in t3.symbol_table(nm)])
    window = (target_va, target_va + length)
    incoming = incoming_branches(frozen[:len(image)], ranges, text_va, window)
    require(not incoming, f"BRANCH_INTO_OVERWRITE_INTERIOR:{[(hex(a), hex(b)) for a, b in incoming[:8]]}")
    t3.gate_window_literal_scan(target_va, length, frozen[:len(image)])
    sites = relocation_sites(vmlinux, sections)
    t3.gate_window_relocation_scan(target_va, length, sites)
    rewrites = audit_rewrites(out, vmlinux, sections, window)
    target_audit.update({"incoming_branch_gate": "PASS", "function_range_safe": True,
                         "relocations_in_window": 0, "runtime_rewrites": rewrites,
                         "runtime_rewrite_safe": True, "entry_audit": "PASS"})
    (out / "target-entry-audit.json").write_text(json.dumps(target_audit, indent=2) + "\n")
    require(digest(vmlinux.read_bytes()) == metadata["files"]["vmlinux"], "AUDIT_MUTATED_VMLINUX")
    t3.gate_window_inside_image_size(offset, length, image_size)
    candidate = patch_window(frozen, offset, probe)
    reference = patch_window(frozen, offset, probe[:4] + reference_core + probe[4 + len(core):])
    expected_reference = args.reference_sha or (REST8_SHA if args.symbol == "rest_init" else None)
    require(args.delay == 8 or expected_reference is not None, "MATCHED_8S_REFERENCE_REQUIRED")
    if expected_reference is not None:
        require(digest(reference) == expected_reference, "FROZEN_8S_REFERENCE_MISMATCH")
    pair_diff = [i for i, (a, b) in enumerate(zip(reference_core, core)) if a != b]
    expected_pair_diff = [9, 10] if len(core) == 56 else [12, 13]
    require(pair_diff == (expected_pair_diff if args.delay == 1 else []), "PAIR_NOT_DELAY_ONLY")
    t3.gate_tail_identity(frozen, candidate, (offset, offset + length))
    changed = t3.gate_payload_diff(frozen, candidate, (offset, offset + length))
    t3.gate_tramp_identity(candidate)
    pb.gate_rt_d(candidate[dtb_offset:])
    (out / "payload.bin").write_bytes(candidate)
    (out / "checkpoint.bin").write_bytes(probe)
    manifest = {"symbol": args.symbol, "target_symbol": target_symbol,
                "target_va": hex(target_va), "offset": offset,
                "checkpoint_size": length, "entry": pad, "section": section["name"],
                "initcall_boundary": initcall_boundary,
                "initcall_boundaries": initcall_boundaries,
                "initcall_source_audit": source_audit,
                "target_source": initcall_source, "target_aliases": target_audit["aliases"],
                "target_function_size": extent - target_va,
                "target_entry_audit": target_audit,
                "core_size": len(core), "terminal_nop_padding_size": length - 4 - len(core),
                "payload_sha256": digest(candidate), "payload_size": len(candidate),
                "checkpoint_sha256": digest(probe), "core_sha256": digest(core),
                "reference_core_sha256": CORE_SHA, "delay_seconds": args.delay,
                "initcall_registration": initcall_registration,
                "core_variant": ("original_b_hs" if args.symbol == "rest_init" else
                                 "ultracompact_cntpct_elapsed_b_lo" if args.symbol in
                                 ULTRACOMPACT_SYMBOLS else "compact_b_lo"),
                "pair_reference_sha256": digest(reference),
                "pair_changed_offsets": [offset + 4 + i for i in pair_diff],
                "frozen_sha256": digest(frozen), "changed_bytes": len(changed),
                "outside_window_changed_bytes": 0, "runtime_rewrites": rewrites,
                "window_agreement": agreement,
                "relocation_sites_checked": len(sites), "audit_elf_unchanged": True,
                "source_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                "bundle": metadata, "normal_boot_candidate": False,
                "runtime_dtb_external_initrd": False, "chosen_properties": sorted(chosen),
                "positive_proves": PROOF_BOUNDARIES[args.symbol][0],
                "positive_does_not_prove": PROOF_BOUNDARIES[args.symbol][1],
                "init_symbols": {name: hex(t3.nm_symbol(nm, name)) for name in
                                 ("rest_init", "kernel_init", "kernel_init_freeable", "smp_init")},
                "device_operation": False}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "SHA256SUMS").write_text("".join(f"{digest((out / n).read_bytes())}  {n}\n"
                                           for n in ("payload.bin", "checkpoint.bin", "manifest.json")))
    print(json.dumps(manifest, indent=2), flush=True)
    if args.symbol == "core_complete":
        print("CORE_CHECKPOINT_SOURCE_AUDIT=PASS\nCORE_CHECKPOINT_BINARY_AUDIT=PASS\n"
              "FIRST_POSTCORE_ENTRY_AUDIT=PASS\nCORE_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES\n"
              "CORE_CHECKPOINT_DIAGNOSTIC_SAFE=YES\nCORE_ALL_PRIOR_STAGE_PROBES_REMOVED=YES",
              flush=True)
    elif args.symbol == "postcore_complete":
        print("POSTCORE_CHECKPOINT_SOURCE_AUDIT=PASS\nPOSTCORE_CHECKPOINT_BINARY_AUDIT=PASS\n"
              "FIRST_ARCH_ENTRY_AUDIT=PASS\nPOSTCORE_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES\n"
              "POSTCORE_CHECKPOINT_DIAGNOSTIC_SAFE=YES\nPOSTCORE_ALL_PRIOR_STAGE_PROBES_REMOVED=YES",
              flush=True)
    elif args.symbol == "arch_complete":
        print("ARCH_CHECKPOINT_SOURCE_AUDIT=PASS\nARCH_CHECKPOINT_BINARY_AUDIT=PASS\n"
              "FIRST_SUBSYS_ENTRY_AUDIT=PASS\nARCH_CHECKPOINT_RUNTIME_REWRITE_SAFE=YES\n"
              "ARCH_CHECKPOINT_DIAGNOSTIC_SAFE=YES\nARCH_ALL_PRIOR_STAGE_PROBES_REMOVED=YES",
              flush=True)
    print(f"{args.symbol.upper()}_INLINE_AUDIT=PASS\nDEVICE_OPERATION=NO\nLOCAL_BUILD=NO", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--symbol", choices=tuple(TARGETS) + tuple(INITCALL_BOUNDARIES),
                        default="rest_init")
    parser.add_argument("--delay", type=int, choices=(1, 8), default=8)
    parser.add_argument("--reference-sha")
    parser.add_argument("--compact-core", type=Path)
    parser.add_argument("--ultracompact-core", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out-slot-b-checkpoint"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    compose(args, args.bundle or build_bundle(args.out))


if __name__ == "__main__":
    main()
