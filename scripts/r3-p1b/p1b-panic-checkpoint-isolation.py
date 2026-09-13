#!/usr/bin/env python3
"""R3 P1B panic/checkpoint isolation (MAINLINE_V2_R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_CI).

GitHub Actions only. Modes:
  source-gate         workflow/source boundary checks (no device, no splice)
  panic-audit         exact-text gates over linux-6.6 panic/cmdline/restart sources
  cmdline-audit       input-config + frozen RT-D bootargs provenance
  panic30             RT-D surgery + semantic diff + FIX8 identity build +
                      PANIC30 payload + geometry + T0/T1 prototypes + T2 audit
  panic30-pack-gates  private: gates over a packed PANIC30 boot v3 image

PANIC30 is a diagnostic control: the ONLY runtime-semantic change vs the frozen
FIXED INIT8 (FIX8) payload is RT-D /chosen/bootargs panic=5 -> panic=30.
The payload base is the frozen FIX8 bytes (Image + trampoline + gap padding
copied verbatim); only the RT-D trailer is rebuilt. The 24s-delay variant is
forbidden this round; the probe delay is 8s everywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1b-panic-checkpoint-isolation.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-panic-checkpoint-isolation.yml"
T0_S = HERE / "p1b-t0-trampoline.S"
T1_S = HERE / "p1b-t1-gap-probe.S"

_spec = importlib.util.spec_from_file_location("p1b_build", HERE / "p1b-build.py")
pb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb)  # p1b-build.py enforces its own CI guard

LINUX_BASE = pb.LINUX_BASE
RT_D_SHA = pb.RT_D_SHA
RT_D_SIZE = pb.RT_D_SIZE
S_RESIDUE = pb.S_RESIDUE
ALIGN_2M = pb.ALIGN_2M
TRAMP_OFFSET = pb.TRAMP_OFFSET
# Trampoline binary length, from the frozen FIX8 layout: off_dtb_rel 40
# (verified in the FIX8 manifest) plus the 8-byte dtb_rel quad = 48.
TRAMP_SIZE = 48
BOOT_CAP = pb.BOOT_CAP
PAGE = pb.PAGE
FDT_MAGIC = pb.FDT_MAGIC
DTB_OFFSET = 0x2380000
FIX8_IMAGE_HEADER_IMAGE_SIZE = 0x2231000
BOOTARGS_OLD = b"rdinit=/init panic=5 loglevel=7"
BOOTARGS_NEW = b"rdinit=/init panic=30 loglevel=7"
FIX8_PAYLOAD_SHA = (
    "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41")
FIX8_IMAGE_SHA = (
    "dffce20ec44de65fc7d271b01f6c1b4c39716923aafd4c24fae165e8e8424944")
FIX8_IMAGE_FILE_SIZE = 35166720
FIX8_INIT_SHA = (
    "f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d")
FIX8_CPIO_SHA = (
    "02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3")
TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
PSCI_SYSTEM_RESET_FID = 0x84000009
PROBE_DELAY = 8


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    raise SystemExit(label if not detail else f"{label}: {detail}")


def run(cmd: list[str], *, cwd: Path | None = None,
        ok: tuple[int, ...] = (0,)) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True,
                          text=True)
    if proc.returncode not in ok:
        fail("P30_CMD_FAILED", f"{' '.join(cmd)}\n{proc.stderr}\n{proc.stdout[-4000:]}")
    return proc.stdout


def src(rel: str) -> str:
    path = LINUX / rel
    if not path.is_file():
        fail("P30_SOURCE_MISSING", rel)
    return path.read_text()


def need(text: str, needle: str, *, label: str = "P30_AUDIT_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str, *, label: str = "P30_AUDIT_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


# ---------------------------------------------------------------- FDT surgery

FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


def fdt_header(blob: bytes) -> dict:
    if len(blob) < 40:
        fail("P30_FDT_FAILED", "short blob")
    magic, totalsize, off_struct, off_strings, off_rsv, version, last_comp, \
        cpuid, sz_strings, sz_struct = struct.unpack_from(">10I", blob, 0)
    if magic != FDT_MAGIC:
        fail("P30_FDT_FAILED", f"magic=0x{magic:08x}")
    if totalsize != len(blob):
        fail("P30_FDT_FAILED", f"totalsize={totalsize} file={len(blob)}")
    return {"totalsize": totalsize, "off_rsv": off_rsv,
            "off_struct": off_struct, "off_strings": off_strings,
            "version": version, "last_comp": last_comp, "cpuid": cpuid,
            "sz_strings": sz_strings, "sz_struct": sz_struct}


def fdt_walk(blob: bytes) -> list[tuple[str, str, bytes, int]]:
    """Full property walk -> (path, name, value, value_offset_in_blob)."""
    hdr = fdt_header(blob)
    off_struct = hdr["off_struct"]
    strings_off = hdr["off_strings"]
    strings = blob[strings_off:strings_off + hdr["sz_strings"]]
    path: list[str] = []
    props: list[tuple[str, str, bytes, int]] = []
    i = off_struct
    while True:
        token = struct.unpack_from(">I", blob, i)[0]
        i += 4
        if token == FDT_BEGIN_NODE:
            end = blob.index(b"\x00", i)
            # Root node name is "" (not "/") so that "/".join yields
            # "/chosen", not "//chosen".
            name = blob[i:end].decode("ascii", "replace") or ""
            path.append(name)
            i = (end + 1 + 3) & ~3
        elif token == FDT_END_NODE:
            path.pop()
        elif token == FDT_PROP:
            plen, nameoff = struct.unpack_from(">II", blob, i)
            i += 8
            nend = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:nend].decode("ascii", "replace")
            value = blob[i:i + plen]
            props.append(("/".join(path) or "/", pname, value, i))
            i = (i + plen + 3) & ~3
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            fail("P30_FDT_FAILED", f"token={token} at {i - 4:#x}")
    if path:
        fail("P30_FDT_FAILED", "unbalanced walk")
    return props


def build_panic30_rt_d(rt_d: bytes) -> bytes:
    """Rewrite /chosen/bootargs panic=5 -> panic=30 via structured FDT surgery.

    The property value grows by one byte; the struct block tail is shifted and
    off_dt_strings/totalsize/size_dt_struct are fixed up. Everything else is
    copied verbatim.
    """
    hdr = fdt_header(rt_d)
    props = fdt_walk(rt_d)
    matches = [p for p in props if p[0] == "/chosen" and p[1] == "bootargs"]
    if len(matches) != 1:
        fail("P30_FDT_FAILED", f"bootargs matches={len(matches)}")
    _, _, value, val_off = matches[0]
    if value != BOOTARGS_OLD + b"\x00":
        fail("P30_FDT_FAILED", f"bootargs={value!r}")
    new_value = BOOTARGS_NEW + b"\x00"
    val_end = val_off + len(value)
    next_tok = (val_end + 3) & ~3
    new_next = (val_off + len(new_value) + 3) & ~3
    delta = new_next - next_tok
    new_struct = bytearray(rt_d[hdr["off_struct"]:val_off] + new_value
                           + b"\x00" * (new_next - val_off - len(new_value))
                           + rt_d[val_end:hdr["off_strings"]])
    # The prop header prefix is copied verbatim, so its plen still reads the
    # old length; patch it (plen word sits 8 bytes before the value).
    struct.pack_into(">I", new_struct, val_off - 8 - hdr["off_struct"],
                     len(new_value))
    if len(new_struct) != hdr["sz_struct"] + delta:
        fail("P30_FDT_FAILED", "struct size algebra")
    out = bytearray(rt_d[:hdr["off_struct"]] + new_struct
                    + rt_d[hdr["off_strings"]:])
    struct.pack_into(">I", out, 4, len(out))
    struct.pack_into(">I", out, 12, hdr["off_struct"] + len(new_struct))
    struct.pack_into(">I", out, 36, len(new_struct))
    return bytes(out)


def fdt_props_flat(blob: bytes) -> dict[str, bytes]:
    return {f"{path}::{name}": value for path, name, value, _ in fdt_walk(blob)}


# ------------------------------------------------------------ semantic diff

def semantic_diff_gates(out: Path, old_rt_d: bytes, new_rt_d: bytes,
                        tools: dict) -> None:
    old_props = fdt_props_flat(old_rt_d)
    new_props = fdt_props_flat(new_rt_d)
    if set(old_props) != set(new_props):
        fail("P30_RTD_DIFF_FAILED", "property key sets differ")
    diff = {k: (old_props[k], new_props[k])
            for k in old_props if old_props[k] != new_props[k]}
    if set(diff) != {"/chosen::bootargs"}:
        fail("P30_RTD_DIFF_FAILED", f"semantic diff keys={sorted(diff)}")
    (old_v, new_v) = diff["/chosen::bootargs"]
    if new_v != old_v.replace(b"panic=5", b"panic=30"):
        fail("P30_RTD_DIFF_FAILED", "bootargs token diff not panic=5->panic=30")
    ho, hn = fdt_header(old_rt_d), fdt_header(new_rt_d)
    for field in ("version", "last_comp", "cpuid", "sz_strings", "off_rsv"):
        if ho[field] != hn[field]:
            fail("P30_RTD_DIFF_FAILED", f"header {field} drifted")
    if old_rt_d[ho["off_rsv"]:ho["off_struct"]] != \
            new_rt_d[hn["off_rsv"]:hn["off_struct"]]:
        fail("P30_RTD_DIFF_FAILED", "mem_rsvmap drifted")
    print(f"PANIC30_RT_D_OLD_SHA256={sha(old_rt_d)} size={len(old_rt_d)}")
    print(f"PANIC30_RT_D_NEW_SHA256={sha(new_rt_d)} size={len(new_rt_d)}")
    print(f"PANIC30_RT_D_PROP_DIFF_KEYS={sorted(diff)}")
    print("PANIC30_RTD_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY")

    # dtc cross-decompile: textual dts diff must be the bootargs line only.
    old_dts, new_dts = out / "rt-d-old.dts", out / "rt-d-new.dts"
    for label, blob in (("old", old_rt_d), ("new", new_rt_d)):
        tmp = out / f"rt-d-{label}.dtb"
        tmp.write_bytes(blob)
        run([tools["dtc"], "-I", "dtb", "-O", "dts", "-q", "-o",
             str(out / f"rt-d-{label}.dts"), str(tmp)])
    dts_diff = [l for l in run(["diff", "-u", str(old_dts), str(new_dts)],
                               ok=(0, 1))
                .splitlines() if l.startswith(("+", "-"))
                and not l.startswith(("+++", "---"))]
    changed = [l for l in dts_diff if "panic=" in l]
    if len(dts_diff) != 2 or len(changed) != 2 or \
            not any("panic=5" in l for l in changed) or \
            not any("panic=30" in l for l in changed):
        fail("P30_RTD_DIFF_FAILED", f"dtc dts diff={dts_diff}")
    (out / "rt-d-dtc-diff.txt").write_text("\n".join(dts_diff) + "\n")
    print("PANIC30_RT_D_DTC_CROSS_CHECK=PASS")


# --------------------------------------------------------- identity fixtures

def scatter_attribution(a: bytes, b: bytes, *, label: str) -> None:
    """Rebuilt-vs-frozen image diff must be IKCONFIG gz avalanche (single
    CONFIG_INITRAMFS_SOURCE path line) plus <=4KiB build-stamp scatter."""
    import zlib
    diffs = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    if len(a) != len(b):
        fail("P30_IDENTITY_FAILED", f"{label} sizes differ")
    if not diffs:
        print(f"PANIC30_REBUILT_VS_FROZEN_{label}=BYTE_IDENTICAL")
        return
    ranges = []
    for i in diffs:
        if ranges and i - ranges[-1][1] <= 16:
            ranges[-1][1] = i
        else:
            ranges.append([i, i])
    ik = a.find(b"IKCFG_ST")
    ike = a.find(b"IKCFG_ED", ik) + 8
    if ik <= 0 or ike <= ik:
        fail("P30_IDENTITY_FAILED", "IKCONFIG markers missing")
    stray = [(s, e) for s, e in ranges if not (ik <= s and e < ike)]
    stray_bytes = sum(e - s + 1 for s, e in stray)
    if stray_bytes > 4096 or any(e - s + 1 > 64 for s, e in stray):
        fail("P30_IDENTITY_FAILED", f"{label} unexplained ranges={stray[:8]}")
    do = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        cfg = do.decompress(a[ik + 8:ike]).decode("utf-8", "replace")
    except Exception as exc:
        fail("P30_IDENTITY_FAILED", f"IKCONFIG decompress {exc}")
    line = [l for l in cfg.splitlines() if l.startswith("CONFIG_INITRAMFS_SOURCE=")]
    if len(line) != 1 or "initramfs-8s.cpio" not in line[0]:
        fail("P30_IDENTITY_FAILED", "IKCONFIG source line unexpected")
    print(f"PANIC30_REBUILT_VS_FROZEN_{label}=BUILD_STAMP_SCATTER_ONLY "
          f"ranges={len(ranges)} stray_bytes={stray_bytes} "
          f"ikconfig_span={ik:#x}..{ike:#x}")


# ------------------------------------------------------------- probe builds

def probe_toolchain(args: argparse.Namespace) -> dict:
    return {"clang": args.clang, "lld": args.lld, "objcopy": args.objcopy,
            "objdump": args.objdump, "readelf": args.readelf,
            "nm": args.nm, "dtc": args.dtc}


def assemble_probe(src_path: Path, ld_path: Path | None, defines: list[str],
                   elf: Path, tools: dict) -> str:
    obj = elf.with_suffix(".o")
    run([tools["clang"], "--target=aarch64-unknown-none", "-nostdlib",
         "-ffreestanding", "-fno-asynchronous-unwind-tables",
         "-fno-unwind-tables", "-fno-ident", *defines, "-c", "-o", str(obj),
         str(src_path)])
    cmd = [tools["lld"]]
    if ld_path is not None:
        cmd += ["-T", str(ld_path)]
    cmd += ["--build-id=none", "--nmagic", "--static", "-o", str(elf),
            str(obj)]
    run(cmd)
    rel = run([tools["readelf"], "-r", "--wide", str(elf)])
    if "R_AARCH64_" in rel:
        fail("P30_PROBE_FAILED", f"relocations in {elf.name}: {rel}")
    dump = run([tools["objdump"], "-d", str(elf)])
    ops = "\n".join(
        re.sub(r"\s+", " ", line.split(":", 1)[-1]).strip().lower()
        for line in dump.splitlines() if re.match(r"^\s*[0-9a-f]+:", line))
    return ops


def check_probe_common(ops: str, elf: Path, out: Path, tools: dict) -> None:
    for token in ("mrs x9, cntfrq_el0", "mrs x11, cntpct_el0", "yield"):
        if token not in ops:
            fail("P30_PROBE_FAILED", f"{elf.name} missing {token!r}")
    # llvm-objdump may print movz through the mov alias and immediates in
    # decimal or hex; accept both printings (CI-proven token style).
    for pat, label in ((r"smc #(0x)?0\b", "smc #0"),
                       (r"(movz|mov) w0, #(0x9|9)\b", "psci fid low"),
                       (r"movk w0, #(0x8400|33792), lsl #16\b",
                        "psci fid high")):
        if not re.search(pat, ops):
            fail("P30_PROBE_FAILED", f"{elf.name} missing {label}")
    if pb.STORE_RE.search(ops):
        fail("P30_PROBE_FAILED", f"{elf.name} has store/adrp")
    for bad in (r"\bbl\b", r"\beret\b", r"\bsctlr\b", r"\bmsr\b\s+daifclr"):
        if re.search(bad, ops):
            fail("P30_PROBE_FAILED", f"{elf.name} forbidden {bad!r}")
    run([tools["objdump"], "-d", str(elf)])  # keep dump in logs
    (out / f"{elf.stem}-disasm.txt").write_text(
        run([tools["objdump"], "-d", str(elf)]))


def build_t0(out: Path, tools: dict, dtb_offset: int, off_primary: int) -> None:
    # Two-pass like the P1B trampoline: entry_rel needs the T0 layout first.
    pre_elf = out / "p1b-t0-pre.elf"
    delay_def = f"-DP1B_PROBE_DELAY={PROBE_DELAY}"
    assemble_probe(T0_S, HERE / "p1b-trampoline.ld",
                   ["-DP1B_DTB_REL=0", "-DP1B_ENTRY_REL=0", delay_def],
                   pre_elf, tools)
    offs0 = probe_syms(tools["readelf"], pre_elf)
    entry_rel = off_primary - (TRAMP_OFFSET + offs0["b_primary"])
    if entry_rel <= 0 or entry_rel % 4:
        fail("P30_T0_FAILED", f"entry_rel {entry_rel:#x}")
    elf1 = out / "p1b-t0-trampoline.elf"
    assemble_probe(T0_S, HERE / "p1b-trampoline.ld",
                   ["-DP1B_DTB_REL=0", f"-DP1B_ENTRY_REL={entry_rel}",
                    delay_def], elf1, tools)
    offs1 = probe_syms(tools["readelf"], elf1)
    if offs1 != offs0:
        fail("P30_T0_FAILED", "layout shifted with entry_rel")
    dtb_rel = dtb_offset - (TRAMP_OFFSET + offs1["dtb_rel"])
    ops = assemble_probe(T0_S, HERE / "p1b-trampoline.ld",
                         [f"-DP1B_DTB_REL={dtb_rel}",
                          f"-DP1B_ENTRY_REL={entry_rel}", delay_def],
                         elf1, tools)
    offs2 = probe_syms(tools["readelf"], elf1)
    if offs2 != offs0:
        fail("P30_T0_FAILED", "layout shifted with dtb_rel")
    binp = out / "p1b-t0-trampoline.bin"
    run([tools["objcopy"], "-O", "binary", str(elf1), str(binp)])
    tbin = binp.read_bytes()
    if not (0x70 <= len(tbin) <= 0xC0):
        fail("P30_T0_FAILED", f"size {len(tbin)}")
    for token in ("msr daifset, #0xf", "adr x0", "ldr x9", "add x0, x0, x9",
                  "mov x1, xzr", "mov x2, xzr", "mov x3, xzr", "mov x15, x0",
                  "mov x0, x15"):
        if token not in ops:
            fail("P30_T0_FAILED", f"missing {token!r}")
    check_probe_common(ops, elf1, out, tools)
    branch_pc = TRAMP_OFFSET + offs2["b_primary"]
    if branch_pc + entry_rel != off_primary:
        fail("P30_T0_FAILED", "branch target != primary_entry")
    x0_static = TRAMP_OFFSET + offs2["dtb_rel"] + dtb_rel
    if x0_static != dtb_offset:
        fail("P30_T0_FAILED", f"x0 algebra {x0_static:#x} != {dtb_offset:#x}")
    dump_s = run([tools["objdump"], "-s", "-j", ".text", str(elf1)])
    if struct.pack("<Q", dtb_rel).hex() not in re.sub(r"\s+", "", dump_s.lower()):
        fail("P30_T0_FAILED", "dtb_rel quad not in .text")
    (out / "p1b-t0-report.txt").write_text(
        f"T0_ENTRY=r3_t0_entry at payload offset {TRAMP_OFFSET:#x}\n"
        f"T0_PROBE_POSITION=after x1=x2=x3=0, before branch primary_entry\n"
        f"T0_DELAY_SECONDS={PROBE_DELAY}\n"
        f"PSCI_FID=0x{PSCI_SYSTEM_RESET_FID:08x} (SYSTEM_RESET, smc #0)\n"
        f"ENTRY_REL={entry_rel:#x} DTB_REL={dtb_rel:#x}\n"
        f"BRANCH {branch_pc:#x} -> {off_primary:#x} (primary_entry)\n"
        f"X0_STATIC={x0_static:#x} (S + {dtb_offset:#x})\n"
        f"FAILSAFE=smc-return -> restore x0/x1/x2/x3 -> fall through to "
        f"primary_entry (normal handoff contract)\n"
        f"TRAMPOLINE_SIZE={len(tbin)}\n")
    print(f"P30_T0 sha256={sha(tbin)} size={len(tbin)} "
          f"entry_rel={entry_rel:#x} dtb_rel={dtb_rel:#x}")
    print("CHECKPOINT_T0_CI=PASS")


def probe_syms(readelf: str, elf: Path) -> dict[str, int]:
    out = run([readelf, "-sW", str(elf)])
    found: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[7] in ("dtb_rel", "b_primary",
                                            "r3_t0_entry", "r3_t1_probe"):
            found[parts[7]] = int(parts[1], 16)
    return found


def build_t1(out: Path, tools: dict, image: bytes, off_primary: int,
             image_file_size: int) -> None:
    probe_elf = out / "p1b-t1-gap-probe.elf"
    ops = assemble_probe(T1_S, HERE / "p1b-t1-gap.ld",
                         [f"-DP1B_PROBE_DELAY={PROBE_DELAY}"], probe_elf, tools)
    probe_syms(tools["readelf"], probe_elf)
    check_probe_common(ops, probe_elf, out, tools)
    for token in ("wfe",):
        if token not in ops:
            fail("P30_T1_FAILED", f"missing {token!r}")
    # register discipline: no writes to x1/x2/x3; x0 written only by the
    # movz/movk FID pair right before smc. ops lines are
    # "<hex encoding> <mnemonic> <operands>" after assemble_probe
    # normalization, so field 2 is the written destination when a register.
    for line in ops.splitlines():
        fields = line.split(" ")
        if len(fields) < 3:
            continue
        dst = fields[2].rstrip(",")
        if not re.fullmatch(r"(x[0-9]+|w[0-9]+|xzr|wzr)", dst):
            continue
        if dst in ("x1", "x2", "x3", "w1", "w2", "w3"):
            fail("P30_T1_FAILED", f"probe clobbers {dst}: {line}")
        if dst in ("x0", "w0") and not (
                re.search(r"(movz|mov) w0, #(0x9|9)\b", line)
                or re.search(r"movk w0, #(0x8400|33792), lsl #16\b", line)):
            fail("P30_T1_FAILED", f"probe clobbers {dst} off-FID: {line}")
    binp = out / "p1b-t1-gap-probe.bin"
    run([tools["objcopy"], "-O", "binary", str(probe_elf), str(binp)])
    probe = binp.read_bytes()
    if not (0x40 <= len(probe) <= 0x80):
        fail("P30_T1_FAILED", f"probe size {len(probe)}")
    gap_off = (image_file_size + 3) & ~3
    delta = gap_off - off_primary
    if delta <= 0 or delta % 4 or delta >= (1 << 27):
        fail("P30_T1_FAILED", f"branch delta {delta:#x}")
    branch = struct.pack("<I", 0x14000000 | ((delta // 4) & 0x03FFFFFF))
    original = image[off_primary:off_primary + 4]
    patched = bytearray(image)
    patched[off_primary:off_primary + 4] = branch
    patched[gap_off:gap_off + len(probe)] = probe
    report = (
        f"T1_PROBE_POSITION=gap at payload offset {gap_off:#x} "
        f"(first free byte after Image file)\n"
        f"T1_INSERTION=primary_entry first instruction at {off_primary:#x}\n"
        f"T1_REPLACED_INSTRUCTION_COUNT=1\n"
        f"T1_REPLACED_INSTRUCTION_BYTES={original.hex()} "
        f"(expected bl record_mmu_state)\n"
        f"T1_PATCH_BYTES={branch.hex()} (b {gap_off:#x})\n"
        f"T1_BRANCH_DELTA={delta:#x}\n"
        f"T1_DELAY_SECONDS={PROBE_DELAY}\n"
        f"PSCI_FID=0x{PSCI_SYSTEM_RESET_FID:08x} smc #0, terminal wfe spin\n"
        f"REGISTER_DISCIPLINE=probe uses x9-x15 only; x0-x3 untouched\n"
        f"T1_PRIMARY_ENTRY_OFFSET={off_primary:#x} "
        f"(derived this round from vmlinux nm)\n")
    (out / "p1b-t1-report.txt").write_text(report)
    print(f"P30_T1 sha256={sha(bytes(patched))} primary_entry={off_primary:#x} "
          f"gap={gap_off:#x} replaced=1 insn")
    print("CHECKPOINT_T1_CI=PASS")


def t2_audit(out: Path, off_t2: int) -> None:
    head = src("arch/arm64/kernel/head.S")
    need(head, "SYM_FUNC_START_LOCAL(__primary_switched)")
    need(head, "adr_l\tx4, init_task")
    need(head, "msr\tvbar_el1, x8")
    need(head, "stp\tx29, x30, [sp, #-16]!")
    need(head, "mov\tx0, x21\t\t\t\t// pass FDT address in x0")
    need(head, "bl\tstart_kernel")
    primary = head.split("SYM_CODE_START(primary_entry)", 1)[1]
    forbid(primary, "msr\tdaifclr")
    forbid(primary, "local_irq_enable")
    # __primary_switched is entered with MMU on via the idmap + kernel map
    # created in __create_page_tables; the gap probe sits inside the kernel
    # map range (Image header image_size covers the gap).
    report = (
        "T2_SOURCE_AUDIT (design only, no artifact this round)\n"
        f"T2_SELECTED_SYMBOL=__primary_switched\n"
        f"T2_SELECTED_OFFSET={off_t2:#x} (derived this round from vmlinux)\n"
        "T2_ENTRY_STATE=\n"
        "  PC/VA: kernel virtual addresses (post __primary_switch MMU-on)\n"
        "  MMU: ON, idmap + kernel map active; gap probe address maps via\n"
        "       the kernel image map (inside image_size footprint)\n"
        "  stack: valid (init_task stack, SP established in __primary_switch)\n"
        "  DAIF: still masked from primary_entry (no daifclr/irq enable on\n"
        "        the primary path before start_kernel)\n"
        "  registers: x20=boot mode x21=FDT ptr live; probe must use\n"
        "             x9-x15 only (same discipline as T0/T1)\n"
        "  CNTPCT: cntpct_el0 readable at EL1; timer not yet taken over\n"
        "          by the clockevents layer at this point\n"
        "  PSCI: smc #0 legal from EL1; RT-D /psci method=smc confirms the\n"
        "        firmware conduit expected by the platform\n"
        "T2_TIMER_RESET_SAFE=YES (conditional on the audit above; MMU-on is\n"
        "  the only environmental difference vs T0/T1 physical-mode probes;\n"
        "  PC-relative-only probe code needs no relocation and no stack)\n"
        "CHECKPOINT_T2_STATUS=DESIGNED\n"
        "T2_PROOF_BOUNDARY=reaching the T2 checkpoint proves execution up to\n"
        "  __primary_switched (idmap/MMU switch done); it does NOT prove\n"
        "  start_kernel entry, cmdline parse, or initramfs.\n")
    (out / "p1b-t2-audit.txt").write_text(report)
    print(f"P30_T2 off={off_t2:#x}")
    print("CHECKPOINT_T2_STATUS=DESIGNED")


# ------------------------------------------------------------------- modes

def cmd_source_gate(_args: argparse.Namespace) -> None:
    for path in (T0_S, T1_S, DOC, STATUS_DOC, WF, Path(__file__)):
        if not path.is_file() or path.stat().st_size == 0:
            fail("P30_SOURCE_GATE_FAILED", f"missing {path}")
    script = Path(__file__).read_text()
    wf = WF.read_text()
    t0 = T0_S.read_text()
    t1 = T1_S.read_text()
    doc = DOC.read_text()
    for token in ("PANIC_TIMEOUT_ONLY", "PANIC30_IMAGE_IDENTICAL_TO_FIXED_INIT8",
                  "PANIC30_NEGATIVE_RESULT_CAN_EXCLUDE_ALL_LINUX_PANIC=NO",
                  "P30-A", "P30-F", "T0", "T1", "T2", FIX8_PAYLOAD_SHA,
                  RT_D_SHA, "panic=30", "READY_FOR_R3_P1B_PANIC30_DEVICE_CONTROL"):
        if token not in doc:
            fail("P30_SOURCE_GATE_FAILED", f"doc missing {token}")
    for token in ("smc", "cntpct_el0", "cntfrq_el0", "yield"):
        if token not in t0 or token not in t1:
            fail("P30_SOURCE_GATE_FAILED", f"probe missing {token}")
    for token in ("P1B_ENTRY_REL", "P1B_DTB_REL", "P1B_PROBE_DELAY"):
        if token not in t0:
            fail("P30_SOURCE_GATE_FAILED", f"t0 missing {token}")
    if "P1B_PROBE_DELAY" not in t1:
        fail("P30_SOURCE_GATE_FAILED", "t1 missing P1B_PROBE_DELAY")
    if re.search(r"fix2[4]|FIX2[4]", script):
        fail("P30_SOURCE_GATE_FAILED", "the 24s-delay variant is forbidden")
    if re.search(r"\b(fastboot|adb|flash|erase|set_active)\b", wf):
        fail("P30_SOURCE_GATE_FAILED", "public workflow has device verbs")
    if "splice-boot" in wf or "mkbootimg" in wf or "boot.img" in wf:
        fail("P30_SOURCE_GATE_FAILED", "public workflow packs boot images")
    if "READY_FOR_DEVICE=" + "YES" in doc or "READY_FOR_DEVICE=" + "YES" in script:
        fail("P30_SOURCE_GATE_FAILED", "must not claim device-ready")
    if pb.calc_dtb_offset(FIX8_IMAGE_HEADER_IMAGE_SIZE)[0] != DTB_OFFSET:
        fail("P30_SOURCE_GATE_FAILED", "dtb_offset algebra for FIX8 image_size")
    print("P30_SOURCE_GATE=PASS")
    print("DEVICE_OPERATION=NO")
    print("READY_FOR_DEVICE=NO")


def cmd_panic_audit(_args: argparse.Namespace) -> None:
    panic_c = src("kernel/panic.c")
    main_c = src("init/main.c")
    mph = src("include/linux/moduleparam.h")
    kdebug = src("lib/Kconfig.debug")
    fdt = src("drivers/of/fdt.c")
    arm64k = src("arch/arm64/Kconfig")
    reboot = src("kernel/reboot.c")
    emerg = src("include/asm-generic/emergency-restart.h")
    process = src("arch/arm64/kernel/process.c")
    psci = src("drivers/firmware/psci/psci.c")
    delay = src("arch/arm64/lib/delay.c")

    need(panic_c, "int panic_timeout = CONFIG_PANIC_TIMEOUT;")
    need(panic_c, "core_param(panic, panic_timeout, int, 0644);")
    need(panic_c, "#define PANIC_TIMER_STEP 100")
    need(panic_c, "if (panic_timeout > 0) {")
    need(panic_c, "Rebooting in %d seconds..")
    need(panic_c, "mdelay(PANIC_TIMER_STEP);")
    need(panic_c, "if (panic_timeout != 0) {")
    need(panic_c, "emergency_restart();")
    need(panic_c, "void panic(const char *fmt, ...)")
    forbid(panic_c, "__noreturn void panic")
    need(mph, '#define core_param(name, var, type, perm)')
    need(mph, '__used __section("__param")')
    need(kdebug, "config PANIC_TIMEOUT")
    need(kdebug, "default 0")
    need(reboot, "void emergency_restart(void)")
    need(reboot, "kmsg_dump(KMSG_DUMP_EMERG);")
    need(reboot, "machine_emergency_restart();")
    need(reboot, "void do_kernel_restart(char *cmd)")
    need(reboot, "atomic_notifier_call_chain(&restart_handler_list, reboot_mode, cmd);")
    need(emerg, "machine_restart(NULL);")
    need(process, "void machine_restart(char *cmd)")
    need(process, "smp_send_stop();")
    need(process, "do_kernel_restart(cmd);")
    need(psci, "static int psci_sys_reset(struct notifier_block *nb, unsigned long action,")
    need(psci, "invoke_psci_fn(PSCI_0_2_FN_SYSTEM_RESET, 0, 0, 0);")
    need(psci, "register_restart_handler(&psci_sys_reset_nb);")
    need(delay, "return (xloops * loops_per_jiffy * HZ) >> 32;")
    need(delay, "__arch_counter_get_cntvct_stable();")

    # start_kernel ordering: setup_arch -> setup_command_line -> notice ->
    # parse_early_param -> parse_args(__start___param) -> calibrate_delay
    idx = {}
    for name, needle in (
            ("setup_arch", "\tsetup_arch(&command_line);"),
            ("setup_command_line", "\tsetup_command_line(command_line);"),
            ("notice", 'pr_notice("Kernel command line: %s\\n", saved_command_line);'),
            ("early", "\tparse_early_param();"),
            ("args", 'after_dashes = parse_args("Booting kernel",'),
            ("param_start", "__start___param"),
            ("calib", "\tcalibrate_delay();"),
            ("lpj", "unsigned long loops_per_jiffy = (1<<12);"),
    ):
        if needle not in main_c:
            fail("P30_AUDIT_FAILED", f"init/main.c missing {needle!r}")
        idx[name] = main_c.index(needle)
    for a, b in (("setup_arch", "setup_command_line"),
                 ("setup_command_line", "notice"), ("notice", "early"),
                 ("early", "args"), ("args", "calib")):
        if idx[a] >= idx[b]:
            fail("P30_AUDIT_FAILED", f"order {a} !< {b}")
    if idx["args"] >= idx["calib"]:
        fail("P30_AUDIT_FAILED", "calibrate_delay must follow parse_args")
    need(main_c, '__setup("rdinit=", rdinit_setup);')

    need(fdt, 'p = of_get_flat_dt_prop(node, "bootargs", &l);')
    need(fdt, 'strscpy(cmdline, p, min(l, COMMAND_LINE_SIZE));')
    need(fdt, "#ifdef CONFIG_CMDLINE")
    need(fdt, "CONFIG_CMDLINE_EXTEND")
    need(fdt, "CONFIG_CMDLINE_FORCE")
    need(arm64k, 'config CMDLINE')
    need(arm64k, 'default ""')
    need(arm64k, "config CMDLINE_FROM_BOOTLOADER")

    print("PANIC_PARAM_REGISTRATION=core_param(panic,panic_timeout) -> __section(__param) NOT early_param")
    print("PANIC_CMDLINE_PARSE_STAGE=START_KERNEL_PARSE_ARGS_BOOTING_KERNEL_AFTER_SETUP_ARCH_AND_PARSE_EARLY_PARAM")
    print("PANIC_TIMEOUT_ACTIVATION_STAGE=PARSE_ARGS_BOOTING_KERNEL_PARAM_SET_INT panic_timeout")
    print("PANIC_SETUP_ARCH_ORDERING=setup_arch BEFORE parse_args; arch early params cannot see panic=")
    print("PANIC_PRE_PARSE_DEFAULT=CONFIG_PANIC_TIMEOUT_DEFAULT_0")
    print("PANIC_PRE_PARSE_PANIC_OBEYS_CMDLINE=NO (panic_timeout==0 skips wait and emergency_restart; panic() returns)")
    print("PANIC_TIMEOUT_WAIT_PATH=PANIC_TIMER_STEP=100ms mdelay loop; mdelay depends on loops_per_jiffy")
    print("PANIC_PRE_CALIBRATE_DELAY_WAIT_ACCURATE=NO (calibrate_delay runs AFTER parse_args; lpj preset 1<<12)")
    print("PANIC_RESTART_PATH=panic->emergency_restart->machine_emergency_restart(asm-generic)->machine_restart->do_kernel_restart->psci_sys_reset->PSCI_0_2_FN_SYSTEM_RESET(0x84000009) smc")
    print("PANIC30_NEGATIVE_RESULT_CAN_EXCLUDE_ALL_LINUX_PANIC=NO")
    print("PANIC_SOURCE_AUDIT_GATES=PASS")
    print("DEVICE_OPERATION=NO")


def cmd_cmdline_audit(args: argparse.Namespace) -> None:
    rt_d = Path(args.rt_d).read_bytes()
    if sha(rt_d) != RT_D_SHA or len(rt_d) != RT_D_SIZE:
        fail("P30_CMDLINE_AUDIT_FAILED", "frozen RT-D identity")
    totalsize, bootargs = pb.parse_fdt_chosen(rt_d)
    if bootargs.encode() != BOOTARGS_OLD:
        fail("P30_CMDLINE_AUDIT_FAILED", repr(bootargs))
    if bootargs.count("panic=") != 1:
        fail("P30_CMDLINE_AUDIT_FAILED", "duplicate panic= in bootargs")
    for frag in ("configs/thyme-route-b.config", "configs/thyme-r3-p1b.config"):
        text = (REPO / frag).read_text()
        for bad in ("CONFIG_CMDLINE=", "CONFIG_CMDLINE_FORCE",
                    "CONFIG_CMDLINE_EXTEND", "CONFIG_PANIC_TIMEOUT"):
            if bad in text:
                fail("P30_CMDLINE_AUDIT_FAILED", f"{frag} sets {bad}")
    print("P1B_FINAL_CMDLINE_SOURCE=RT_D_CHOSEN_BOOTARGS_ONLY")
    print("P1B_CMDLINE_CHAIN=fdt early_init_dt_scan_chosen -> boot_command_line -> static_command_line -> parse_args")
    print("P1B_CMDLINE_OVERRIDE=NONE (CONFIG_CMDLINE empty, FORCE/EXTEND unset, CMDLINE_FROM_BOOTLOADER=y)")
    print("P1B_BOOT_V3_HEADER_CMDLINE=NOT_CONSUMED (trampoline forces x0 to RT-D)")
    print("P1B_RTD_BOOTARGS_EFFECTIVE_BY_DESIGN=YES")
    print("DUPLICATE_PANIC_PARAMETER=NO")
    print("P30_CMDLINE_AUDIT_GATES=PASS")
    print("DEVICE_OPERATION=NO")


def apply_kernel_patches() -> None:
    queue = sorted((REPO / "patches/linux-6.6").glob("*.patch"))
    for p in queue:
        run(["git", "-C", str(LINUX), "apply", "--check", "--whitespace=nowarn",
             str(p)])
        run(["git", "-C", str(LINUX), "apply", "--whitespace=nowarn", str(p)])


def check_merged_config(config: Path) -> None:
    text = config.read_text()
    if 'CONFIG_CMDLINE=""' not in text:
        fail("P30_CONFIG_FAILED", 'merged .config missing CONFIG_CMDLINE=""')
    # With CMDLINE="" the arm64 cmdline choice prompt is hidden
    # (arch/arm64/Kconfig "if CMDLINE != \"\""), so the choice members are
    # omitted from the written .config entirely; the semantic requirement is
    # that neither override symbol is enabled.
    for sym in ("CONFIG_CMDLINE_FORCE=", "CONFIG_CMDLINE_EXTEND="):
        if re.search(rf"^{sym}", text, re.M):
            fail("P30_CONFIG_FAILED", f"cmdline override enabled: {sym}")
    if "CONFIG_PANIC_TIMEOUT=0" not in text:
        fail("P30_CONFIG_FAILED", "merged .config missing CONFIG_PANIC_TIMEOUT=0")
    for kexec_sym in ("CONFIG_KEXEC=y", "CONFIG_KEXEC_FILE=y",
                      "CONFIG_CRASH_DUMP=y"):
        if kexec_sym in text:
            print(f"P30_CONFIG_NOTE={kexec_sym} present: crash_kexec(NULL) is "
                  f"a no-op without a loaded crash kernel (no kexec tooling "
                  f"runs before /init)")
    print("P30_MERGED_CONFIG_GATES=PASS")


def cmd_panic30(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = probe_toolchain(args)
    apply_kernel_patches()

    frozen_rt_d = Path(args.rt_d).read_bytes()
    if sha(frozen_rt_d) != RT_D_SHA or len(frozen_rt_d) != RT_D_SIZE:
        fail("P30_BUILD_FAILED", "frozen RT-D identity")
    frozen_payload = Path(args.fix8_payload).read_bytes()
    if sha(frozen_payload) != FIX8_PAYLOAD_SHA:
        fail("P30_BUILD_FAILED", f"frozen FIX8 payload sha={sha(frozen_payload)}")
    fhdr = pb.parse_image_hdr(frozen_payload, "frozen-fix8-payload")
    image_size = fhdr["image_size"]
    if fhdr["code1"] != 0x1400000F:
        fail("P30_BUILD_FAILED", "frozen payload code1 not b 0x40")
    dtb_offset, gap = pb.calc_dtb_offset(image_size)
    if dtb_offset != DTB_OFFSET:
        fail("P30_BUILD_FAILED", f"dtb_offset {dtb_offset:#x} != {DTB_OFFSET:#x}")
    # The payload kernel region [0, dtb_offset) is the PATCHED Image
    # (code1 -> b 0x40 at offset 4, 48-byte trampoline at 0x40), so it can
    # never equal the raw Image file behind FIX8_IMAGE_SHA. The region is
    # frozen compositionally: sha(payload) == FIX8_PAYLOAD_SHA plus
    # sha(frozen_rt_d) == RT_D_SHA pins payload[:dtb_offset] exactly.
    # Direct spot checks: payload layout and the embedded trampoline.
    if len(frozen_payload) - RT_D_SIZE != dtb_offset:
        fail("P30_BUILD_FAILED", "payload layout: len - RT_D_SIZE != dtb_offset")
    embedded_tramp = frozen_payload[TRAMP_OFFSET:TRAMP_OFFSET + TRAMP_SIZE]
    if sha(embedded_tramp) != TRAMP_SHA:
        fail("P30_BUILD_FAILED", f"embedded trampoline sha={sha(embedded_tramp)}")
    print("PANIC30_FROZEN_FIX8_BASE=PASS")
    print("PANIC30_FROZEN_KERNEL_REGION=COMPOSITIONAL_HASH_ANCHORED")
    print(f"FIX8_IMAGE_SHA256={FIX8_IMAGE_SHA} file_size={FIX8_IMAGE_FILE_SIZE} "
          "(raw Image provenance; payload region is the patched form)")

    # 1. PANIC30 RT-D via structured surgery + dual gates.
    panic30_rt_d = build_panic30_rt_d(frozen_rt_d)
    semantic_diff_gates(out, frozen_rt_d, panic30_rt_d, tools)
    (out / "rt-d-panic30.dtb").write_bytes(panic30_rt_d)
    _ts, p30_bootargs = pb.parse_fdt_chosen(panic30_rt_d)
    if p30_bootargs.encode() != BOOTARGS_NEW:
        fail("P30_BUILD_FAILED", "panic30 bootargs mismatch")
    print(f"PANIC30_RT_D_SHA={sha(panic30_rt_d)}")
    print(f"PANIC30_RT_D_SIZE={len(panic30_rt_d)}")

    # 2. Rebuild the FIXED INIT8 identity fixtures (delay=8 only).
    init = pb.compile_init(out, PROBE_DELAY, args.gcc, args.strip)
    init_sha = sha(init.read_bytes())
    if init_sha != FIX8_INIT_SHA:
        fail("P30_IDENTITY_FAILED", f"/init sha {init_sha} != frozen FIX8")
    cpio = out / f"initramfs-{PROBE_DELAY}s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    cpio_sha = sha(cpio.read_bytes())
    if cpio_sha != FIX8_CPIO_SHA:
        fail("P30_IDENTITY_FAILED", f"cpio sha {cpio_sha} != frozen FIX8")
    print(f"PANIC30_INIT_IDENTICAL=YES sha={init_sha}")
    print(f"PANIC30_INITRAMFS_IDENTICAL=YES sha={cpio_sha}")

    k = pb.make_kernel(out, PROBE_DELAY, cpio, args.jobs)
    check_merged_config(k["config"])
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    image = k["image"].read_bytes()
    if kg["hdr"]["image_size"] != image_size:
        fail("P30_BUILD_FAILED", "rebuilt image_size != frozen")
    if len(image) != FIX8_IMAGE_FILE_SIZE:
        fail("P30_BUILD_FAILED", "rebuilt image file size != frozen")
    off_primary = kg["off_primary"]

    # Trampoline must rebuild byte-identical to the frozen FIX8 one.
    _, pre_elf, offs = pb.assemble_trampoline(out, tools, None, 0)
    entry_rel = off_primary - (TRAMP_OFFSET + offs["b_primary"])
    if entry_rel <= 0 or entry_rel % 4:
        fail("P30_BUILD_FAILED", f"entry_rel {entry_rel:#x}")
    tbin, telf, offs2 = pb.assemble_trampoline(out, tools, None, entry_rel)
    if offs2 != offs:
        fail("P30_BUILD_FAILED", "trampoline layout shifted")
    dtb_rel = dtb_offset - (TRAMP_OFFSET + offs2["dtb_rel"])
    tbin, telf, offs3 = pb.assemble_trampoline(out, tools, dtb_rel, entry_rel)
    tramp = tbin.read_bytes()
    if sha(tramp) != TRAMP_SHA:
        fail("P30_IDENTITY_FAILED", f"trampoline sha {sha(tramp)} != frozen")
    print(f"PANIC30_TRAMPOLINE_IDENTICAL=YES sha={TRAMP_SHA}")
    pb.trampoline_disasm_gates(out, tools, telf, offs3, dtb_rel, entry_rel)

    rebuilt_prefix = bytearray(image)
    rebuilt_prefix[pb.CODE1_OFFSET:pb.CODE1_OFFSET + 4] = \
        struct.pack("<I", 0x1400000F)
    rebuilt_prefix[TRAMP_OFFSET:TRAMP_OFFSET + len(tramp)] = tramp
    rebuilt_prefix += bytes(dtb_offset - len(rebuilt_prefix))
    scatter_attribution(bytes(rebuilt_prefix), frozen_payload[:dtb_offset],
                        label="IMAGE_PREFIX")

    # 3. PANIC30 payload: frozen FIX8 bytes verbatim, RT-D trailer swapped.
    payload = frozen_payload[:dtb_offset] + panic30_rt_d
    if payload[:dtb_offset] != frozen_payload[:dtb_offset]:
        fail("P30_BUILD_FAILED", "payload prefix drifted")
    if payload[dtb_offset:dtb_offset + 4] != struct.pack(">I", FDT_MAGIC):
        fail("P30_BUILD_FAILED", "no FDT magic at DTB_OFFSET")
    if payload[dtb_offset:] != panic30_rt_d:
        fail("P30_BUILD_FAILED", "trailer mismatch")
    phdr = pb.parse_image_hdr(payload, "panic30-payload")
    if (phdr["code0"], phdr["code1"], phdr["image_size"], phdr["flags"]) != \
            (fhdr["code0"], 0x1400000F, image_size, fhdr["flags"]):
        fail("P30_BUILD_FAILED", "payload header drifted")
    payload_path = out / "thyme-r3-p1b-panic30-kernel-payload.bin"
    payload_path.write_bytes(payload)
    print(f"PANIC30_PAYLOAD sha256={sha(payload)} size={len(payload)}")
    print("PANIC30_IMAGE_IDENTICAL_TO_FIXED_INIT8=YES")
    print("PANIC30_INIT_IDENTICAL=YES")
    print("PANIC30_INITRAMFS_IDENTICAL=YES")
    print("PANIC30_TRAMPOLINE_IDENTICAL=YES")
    print("PANIC30_RUNTIME_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY")

    # 4. Geometry gates (re-proven this round, not assumed).
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("P30_GEOMETRY_FAILED", "2MiB residue geometry")
    boot_est = pb.align(PAGE + len(payload), PAGE) + PAGE
    margin = BOOT_CAP - boot_est
    if margin < 0x1000000:
        fail("P30_GEOMETRY_FAILED", f"capacity margin {margin}")
    print(f"PANIC30_DTB_OFFSET={dtb_offset:#x} gap={gap:#x} "
          f"payload_size={len(payload)} boot_size_est={boot_est} "
          f"margin={margin}")

    # 5. Checkpoints: T0/T1 CI prototypes, T2 source audit.
    build_t0(out, tools, dtb_offset, off_primary)
    build_t1(out, tools, image, off_primary, len(image))
    nm = run([tools["nm"], str(k["vmlinux"])])
    t2 = [l for l in nm.splitlines() if l.endswith(" __primary_switched")]
    if not t2:
        fail("P30_T2_FAILED", "__primary_switched missing")
    off_t2 = int(t2[0].split()[0], 16) - kg["text_addr"]
    t2_audit(out, off_t2)

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_CI",
        "linux_base": LINUX_BASE,
        "baseline": "FROZEN_FIX8 (public run 34741153230)",
        "fix8_payload_sha256": FIX8_PAYLOAD_SHA,
        "fix8_image_sha256": FIX8_IMAGE_SHA,
        "fix8_init_sha256": FIX8_INIT_SHA,
        "fix8_cpio_sha256": FIX8_CPIO_SHA,
        "fix8_tramp_sha256": TRAMP_SHA,
        "rt_d_frozen_sha256": RT_D_SHA,
        "rt_d_frozen_size": RT_D_SIZE,
        "panic30_rt_d_sha256": sha(panic30_rt_d),
        "panic30_rt_d_size": len(panic30_rt_d),
        "panic30_payload_sha256": sha(payload),
        "panic30_payload_size": len(payload),
        "panic30_boot_size_est": boot_est,
        "dtb_offset": hex(dtb_offset),
        "gap": hex(gap),
        "image_size": hex(image_size),
        "image_file_size": len(image),
        "primary_entry_offset": hex(off_primary),
        "primary_switched_offset": hex(off_t2),
        "entry_rel": hex(entry_rel),
        "dtb_rel": hex(dtb_rel),
        "probe_delay_seconds": PROBE_DELAY,
        "expected_device_shift_seconds": 25.0,
    }
    (out / "p1b-panic30-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    gates = [
        "P30_BUILD_GATES=PASS",
        "PANIC30_RTD_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY",
        "PANIC30_IMAGE_IDENTICAL_TO_FIXED_INIT8=YES",
        "PANIC30_INIT_IDENTICAL=YES",
        "PANIC30_INITRAMFS_IDENTICAL=YES",
        "PANIC30_TRAMPOLINE_IDENTICAL=YES",
        "PANIC30_RUNTIME_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY",
        "PANIC30_GEOMETRY_GATES=PASS",
        "CHECKPOINT_T0_CI=PASS",
        "CHECKPOINT_T1_CI=PASS",
        "CHECKPOINT_T2_STATUS=DESIGNED",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "p1b-panic30-gates.txt").write_text("\n".join(gates) + "\n")
    print("\n".join(gates))


def cmd_panic30_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    panic30_rt_d = Path(args.rt_d).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("P30_PACK_FAILED", f"m5d sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("P30_PACK_FAILED", f"payload sha={sha(payload)}")
    ref = pb.parse_boot_v3(m5d, "m5d")
    cand = pb.parse_boot_v3(boot, "panic30-candidate")
    if cand["kernel"] != payload:
        fail("P30_PACK_FAILED", "candidate kernel != PANIC30 payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("P30_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("P30_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("P30_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("P30_PACK_FAILED", "reserved differs from M5D")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("P30_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    hdr = pb.parse_image_hdr(payload, "panic30-payload")
    dtb_offset, _ = pb.calc_dtb_offset(hdr["image_size"])
    if dtb_offset != DTB_OFFSET:
        fail("P30_PACK_FAILED", f"dtb_offset {dtb_offset:#x}")
    trailer = payload[dtb_offset:]
    if sha(trailer) != sha(panic30_rt_d) or trailer != panic30_rt_d:
        fail("P30_PACK_FAILED", "trailer != PANIC30 RT-D")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("P30_PACK_FAILED", "DTB residue geometry")
    if len(boot) >= BOOT_CAP or BOOT_CAP - len(boot) < 0x1000000:
        fail("P30_PACK_FAILED", "capacity")
    report = Path(args.out)
    report.mkdir(parents=True, exist_ok=True)
    report = report / "p1b-panic30-pack-gates.txt"
    report.write_text(
        "P30_PACK_GATES=PASS\n"
        f"PANIC30_BOOT_SIZE={len(boot)}\n"
        f"PANIC30_BOOT_SHA256={sha(boot)}\n"
        f"PANIC30_PAYLOAD_SHA256={sha(payload)}\n"
        f"PANIC30_RT_D_SHA256={sha(panic30_rt_d)}\n"
        f"PANIC30_KERNEL_SIZE={len(payload)}\n"
        f"PANIC30_DTB_OFFSET={dtb_offset:#x}\n"
        "PANIC30_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "PANIC30_RUNTIME_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "panic-audit", "cmdline-audit", "panic30",
        "panic30-pack-gates"), required=True)
    parser.add_argument("--out", default="out-p30")
    parser.add_argument("--rt-d")
    parser.add_argument("--fix8-payload")
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--lld", default="ld.lld-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    parser.add_argument("--objdump", default="llvm-objdump-18")
    parser.add_argument("--nm", default="llvm-nm-18")
    parser.add_argument("--readelf", default="llvm-readelf-18")
    parser.add_argument("--dtc", default="dtc")
    parser.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    parser.add_argument("--strip", default="aarch64-linux-gnu-strip")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--m5d-boot")
    parser.add_argument("--m5d-sha", default=(
        "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"))
    parser.add_argument("--payload")
    parser.add_argument("--payload-sha")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
    elif args.mode == "panic-audit":
        cmd_panic_audit(args)
    elif args.mode == "cmdline-audit":
        if not args.rt_d:
            fail("P30_CMDLINE_AUDIT_FAILED", "--rt-d required")
        cmd_cmdline_audit(args)
    elif args.mode == "panic30":
        if not (args.rt_d and args.fix8_payload):
            fail("P30_BUILD_FAILED", "--rt-d and --fix8-payload required")
        cmd_panic30(args)
    elif args.mode == "panic30-pack-gates":
        need_all = (args.m5d_boot and args.payload and args.boot
                    and args.payload_sha and args.rt_d and args.out)
        if not need_all:
            fail("P30_PACK_FAILED", "need --m5d-boot --payload --boot "
                                    "--payload-sha --rt-d --out")
        cmd_panic30_pack_gates(args)


if __name__ == "__main__":
    main()
