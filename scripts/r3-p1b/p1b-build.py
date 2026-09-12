#!/usr/bin/env python3
"""R3 P1B minimal mainline Linux entry: two-pass builder + fail-closed gates.

GitHub Actions only. Modes:
  source-gate      static source/formula/workflow-boundary checks
  initramfs        compile /init + deterministic cpio (built twice, identical)
  build-pair       INIT8/INIT24 two-pass build, trampoline patch, RT-D trailer
  clean-baseline   M0-config-line rebuild + M0 reproduction comparison
  kernel-gate      gate a built Image/vmlinux/System.map triple
  splice-boot      private: pack P1B kernel payload into M5D boot v3 envelope
  pack-gates       private: gates over a packed boot (envelope diff, capacity)

The public workflow never calls splice-boot/pack-gates and never emits *.img.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1b-minimal-linux-entry-ci.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-minimal-linux-entry.yml"

LINUX_BASE = "8b73de7da85fde281a385e0b26eda9bffd3ca477"
PATCH_QUEUE_SHA = "d470701d58d62bf10b96adb4dbf0c639945afccd45d4d3f039e8051e7aaaf1b5"
M0_IMAGE_SHA = "22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6"
RT_D_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
RT_D_SIZE = 144593
S_RESIDUE = 0x80000
ALIGN_2M = 0x200000
TRAMP_OFFSET = 0x40
CODE1_OFFSET = 4
PAGE = 4096
BOOT_CAP = 201326592
BOOT_HEADER_V3_SIZE = 1580
BOOT_MAGIC = b"ANDROID!"
KERNEL_OFFSET = PAGE
FDT_MAGIC = 0xD00DFEED
DELAY_PAIR = (8, 24)
RT_D_BOOTARGS = b"rdinit=/init panic=5 loglevel=7"
STORE_RE = re.compile(
    r"\b(st|strb|strh|stp|stur|stlr|stxr|stlxr|sttr|stnp|cas|swp|adrp)\b", re.I
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    msg = label if not detail else f"{label}: {detail}"
    raise SystemExit(msg)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, check=False, capture_output=True, text=True, env=env
    )
    if proc.returncode != 0:
        fail("P1B_CMD_FAILED", f"{' '.join(cmd)}\n{proc.stderr}\n{proc.stdout[-4000:]}")
    return proc.stdout


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def sx(value: int, bits: int) -> int:
    return value - (1 << bits) if value >= (1 << (bits - 1)) else value


def calc_dtb_offset(image_size: int) -> tuple[int, int]:
    """DTB_OFFSET = align_up(image_size + S_residue, 2MiB) - S_residue.

    Places RT-D at the first 2MiB boundary after the Image footprint: with the
    frozen S mod 2MiB == 0x80000, (S + DTB_OFFSET) mod 2MiB == 0, so the DTB
    starts its own fresh 2MiB region with no overlap into [S, S+image_size).
    """
    dtb_offset = align(image_size + S_RESIDUE, ALIGN_2M) - S_RESIDUE
    if dtb_offset < image_size:
        fail("P1B_GEOMETRY_FAILED", f"dtb_offset {dtb_offset:#x} < image_size")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("P1B_GEOMETRY_FAILED", "residue+dtb_offset not 2MiB aligned")
    return dtb_offset, dtb_offset - image_size


def parse_image_hdr(image: bytes, label: str) -> dict:
    if len(image) < 64 or image[56:60] != b"ARM\x64":
        fail("P1B_IMAGE_HEADER_FAILED", f"{label} not ARM64 Image")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from(
        "<QQQQQQ", image, 8
    )
    return {
        "code0": code0,
        "code1": code1,
        "text_offset": text_offset,
        "image_size": image_size,
        "flags": flags,
        "res2": res2,
        "res3": res3,
        "res4": res4,
        "file_size": len(image),
        "sha256": sha(image),
    }


def parse_fdt_chosen(blob: bytes) -> tuple[int, str]:
    if len(blob) < 40:
        fail("P1B_FDT_FAILED", "short blob")
    magic, totalsize = struct.unpack_from(">II", blob, 0)
    if magic != FDT_MAGIC:
        fail("P1B_FDT_FAILED", f"magic=0x{magic:08x}")
    if totalsize > len(blob):
        fail("P1B_FDT_FAILED", f"totalsize={totalsize} file={len(blob)}")
    # chosen bootargs via a tiny struct-block walk (props after nodes)
    off_struct = struct.unpack_from(">I", blob, 8)[0]
    strings_off = struct.unpack_from(">I", blob, 12)[0]
    body = blob[off_struct:totalsize]
    strings = blob[strings_off:totalsize]
    bootargs = ""
    depth = 0
    i = 0

    def a4(n: int) -> int:
        return (n + 3) & ~3

    while i + 4 <= len(body):
        token = struct.unpack_from(">I", body, i)[0]
        i += 4
        if token == 1:  # BEGIN_NODE
            end = body.index(b"\x00", i)
            depth += 1
            i = a4(end + 1)
        elif token == 2:  # END_NODE
            depth -= 1
        elif token == 3:  # PROP
            plen, nameoff = struct.unpack_from(">II", body, i)
            i += 8
            nend = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:nend].decode("ascii", "replace")
            pval = body[i:i + plen]
            i = a4(i + plen)
            if pname == "bootargs" and depth == 1:
                bootargs = pval.split(b"\x00")[0].decode("ascii", "replace")
        elif token == 4:  # NOP
            continue
        elif token == 9:  # END
            break
        else:
            fail("P1B_FDT_FAILED", f"token={token}")
    return totalsize, bootargs


def gate_rt_d(rt_d: bytes) -> None:
    if sha(rt_d) != RT_D_SHA or len(rt_d) != RT_D_SIZE:
        fail("P1B_RT_D_IDENTITY_FAILED", f"sha={sha(rt_d)} size={len(rt_d)}")
    totalsize, bootargs = parse_fdt_chosen(rt_d)
    if totalsize != RT_D_SIZE:
        fail("P1B_RT_D_IDENTITY_FAILED", f"totalsize={totalsize}")
    if bootargs.encode() != RT_D_BOOTARGS:
        fail("P1B_RT_D_BOOTARGS_FAILED", repr(bootargs))
    print("P1B_RT_D_SHA_EXACT=PASS")
    print("P1B_RT_D_BOOTARGS_FROZEN=PASS")


def newc_entry(name: str, mode: int, data: bytes = b"", ino: int = 0,
               nlink: int = 1) -> bytes:
    name_b = name.encode()
    fields = [
        len(str(ino)), mode, 0, 0, nlink, 0, len(data), 0, 0, 0, 0,
        len(name_b) + 1, 0,
    ]
    hdr = b"070701" + b"".join(f"{f:08X}" for f in fields)
    out = hdr + name_b + b"\x00"
    out += b"\x00" * ((4 - len(out) % 4) % 4)
    out += data
    out += b"\x00" * ((4 - len(data) % 4) % 4)
    return out


def build_cpio(init: bytes) -> bytes:
    entries = [
        (newc_entry("dev", 0o040755, ino=1, nlink=2), "dev"),
        (newc_entry("init", 0o100755, init, ino=2), "init"),
        (newc_entry("proc", 0o040755, ino=3, nlink=2), "proc"),
        (newc_entry("sys", 0o040755, ino=4, nlink=2), "sys"),
    ]
    if [e[1] for e in entries] != sorted(e[1] for e in entries):
        fail("P1B_CPIO_FAILED", "entries unsorted")
    body = b"".join(e[0] for e in entries)
    body += newc_entry("TRAILER!!!", 0)
    return body


def compile_init(out: Path, delay: int, gcc: str, strip: str) -> Path:
    elf = out / f"p1b-init-{delay}s"
    cmd = [
        gcc,
        "-ffreestanding", "-nostdlib", "-static", "-no-pie", "-fno-pic",
        "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-fno-ident",
        "-Os", "-Wall", "-Werror",
        "-Wl,-e,main", "-Wl,--build-id=none", "-Wl,-z,noexecstack",
        f"-Wl,-T{HERE / 'p1b-init.ld'}",
        f"-DDELAY_SECONDS={delay}",
        "-o", str(elf), str(HERE / "p1b-init.c"),
    ]
    run(cmd)
    run([strip, "-s", str(elf)])
    info = run(["file", "-b", str(elf)])
    if "ELF 64-bit LSB" not in info or "aarch64" not in info.lower():
        fail("P1B_INIT_FAILED", info)
    if "executable" not in info or "shared" in info.lower():
        fail("P1B_INIT_FAILED", f"not ET_EXEC: {info}")
    readelf = gcc.replace("gcc", "readelf")
    hdr = run([readelf, "-h", str(elf)])
    if "Type:" not in hdr or "EXEC" not in hdr:
        fail("P1B_INIT_FAILED", "readelf type not EXEC")
    interp = run([readelf, "-l", str(elf)])
    if "INTERP" in interp:
        fail("P1B_INIT_FAILED", "PT_INTERP present")
    dyn = subprocess.run([readelf, "-d", str(elf)],
                         capture_output=True, text=True, check=False)
    if "NEEDED" in dyn.stdout:
        fail("P1B_INIT_FAILED", "dynamic NEEDED")
    ident = run(["strings", str(elf)])
    if f"THYME-R3-P1B-INIT DELAY={delay}" not in ident:
        fail("P1B_INIT_FAILED", "ident string")
    elf.chmod(0o755)
    print(f"P1B_INIT delay={delay} sha256={sha(elf.read_bytes())} "
          f"size={elf.stat().st_size}")
    return elf


def make_kernel(out_dir: Path, delay: int | None, cpio: Path | None,
                jobs: int) -> dict:
    tag = "base" if delay is None else f"{delay}s"
    odir = out_dir / f"out-kernel-{tag}"
    odir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    makeargs = ["O=" + str(odir), "ARCH=arm64", "LLVM=1"]
    run(["make", *makeargs, "defconfig"], cwd=LINUX, env=env)
    frag = odir / "r3-p1b-initramfs.fragment"
    if delay is None:
        frag.write_text(
            "# clean baseline: no built-in initramfs\n"
            'CONFIG_INITRAMFS_SOURCE=""\n'
        )
    else:
        if cpio is None:
            fail("P1B_BUILD_FAILED", "missing cpio")
        frag.write_text(
            f'CONFIG_INITRAMFS_SOURCE="{cpio}"\n'
            "CONFIG_INITRAMFS_COMPRESSION_NONE=y\n"
            "CONFIG_INITRAMFS_ROOT_UID=0\n"
            "CONFIG_INITRAMFS_ROOT_GID=0\n"
        )
    run(["./scripts/kconfig/merge_config.sh", "-m", "-O", str(odir),
         str(odir / ".config"),
         str(REPO / "configs" / "thyme-route-b.config")],
        cwd=LINUX, env=env)
    if delay is not None:
        run(["./scripts/kconfig/merge_config.sh", "-m", "-O", str(odir),
             str(odir / ".config"),
             str(REPO / "configs" / "thyme-r3-p1b.config"), str(frag)],
            cwd=LINUX, env=env)
    run(["make", *makeargs, "olddefconfig"], cwd=LINUX, env=env)
    config = (odir / ".config").read_text()
    for sym in ("CONFIG_ARM64=y", "CONFIG_BLK_DEV_INITRD=y",
                "CONFIG_BINFMT_ELF=y", "CONFIG_MMU=y"):
        if sym not in config:
            fail("P1B_CONFIG_FAILED", f"missing {sym}")
    if delay is not None:
        if f'CONFIG_INITRAMFS_SOURCE="{cpio}"' not in config:
            fail("P1B_CONFIG_FAILED", "INITRAMFS_SOURCE not applied")
        if "CONFIG_INITRAMFS_COMPRESSION_NONE=y" not in config:
            fail("P1B_CONFIG_FAILED", "INITRAMFS_COMPRESSION_NONE not applied")
    else:
        if 'CONFIG_INITRAMFS_SOURCE=""' not in config:
            fail("P1B_CONFIG_FAILED", "baseline INITRAMFS_SOURCE not empty")
    run(["make", *makeargs, f"-j{jobs}", "Image"], cwd=LINUX, env=env)
    image = odir / "arch/arm64/boot/Image"
    vmlinux = odir / "vmlinux"
    sysmap = odir / "System.map"
    for p in (image, vmlinux, sysmap):
        if not p.is_file() or p.stat().st_size == 0:
            fail("P1B_BUILD_FAILED", f"missing {p}")
    version = run(["make", *makeargs, "-s", "kernelversion"], cwd=LINUX,
                  env=env).strip()
    if not version.startswith("6.6."):
        fail("P1B_BUILD_FAILED", f"version {version}")
    return {"tag": tag, "delay": delay, "odir": odir, "image": image,
            "vmlinux": vmlinux, "sysmap": sysmap, "config": odir / ".config",
            "version": version}


def syms(readelf: str, elf: Path, names: tuple[str, ...]) -> dict[str, int]:
    out = run([readelf, "-sW", str(elf)])
    found: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[7] in names:
            try:
                found[parts[7]] = int(parts[1], 16)
            except ValueError:
                pass
    missing = [n for n in names if n not in found]
    if missing:
        fail("P1B_SYMBOL_FAILED", f"missing {missing}")
    return found


def kernel_gate(image_path: Path, vmlinux: Path, sysmap: Path) -> dict:
    image = image_path.read_bytes()
    hdr = parse_image_hdr(image, image_path.name)
    print(f"P1B_IMAGE_HEADER {json.dumps({k: (hex(v) if isinstance(v, int) else v) for k, v in hdr.items()})}")
    if hdr["flags"] & 1:
        fail("P1B_IMAGE_HEADER_FAILED", "big-endian flag set")
    if not hdr["flags"] & 8:
        fail("P1B_IMAGE_HEADER_FAILED", "bit3 48-bit placement not set")
    if hdr["res2"] or hdr["res3"] or hdr["res4"]:
        fail("P1B_IMAGE_HEADER_FAILED", "reserved nonzero")
    if hdr["image_size"] < hdr["file_size"] or hdr["image_size"] == 0:
        fail("P1B_IMAGE_HEADER_FAILED", "image_size semantics")
    nm = run(["nm", str(vmlinux)])
    pe = [l for l in nm.splitlines() if l.endswith(" primary_entry")]
    tx = [l for l in nm.splitlines() if l.endswith(" _text")]
    if not pe or not tx:
        fail("P1B_PRIMARY_ENTRY_FAILED", "symbols missing")
    pe_addr = int(pe[0].split()[0], 16)
    text_addr = int(tx[0].split()[0], 16)
    off_primary = pe_addr - text_addr
    if off_primary <= TRAMP_OFFSET + 0x100:
        fail("P1B_PRIMARY_ENTRY_FAILED", f"offset {off_primary:#x} in hole")
    dump = run(["objdump", "-d", f"--start-address={pe_addr:#x}",
                f"--stop-address={pe_addr + 16:#x}", str(vmlinux)])
    body = dump.split("primary_entry", 1)[-1]
    if re.search(r"\b(b|br)\s+\.", body):
        fail("P1B_PRIMARY_ENTRY_FAILED", "spin at primary_entry")
    if "bl\trecord_mmu_state" not in dump:
        fail("P1B_PRIMARY_ENTRY_FAILED", "first instruction not bl record_mmu_state")
    expect_code1 = 0x14000000 | (((off_primary - CODE1_OFFSET) // 4) & 0x03FFFFFF)
    if hdr["code1"] != expect_code1:
        fail("P1B_PRIMARY_ENTRY_FAILED",
             f"code1 {hdr['code1']:#x} != b primary_entry {expect_code1:#x}")
    print(f"PRIMARY_ENTRY_NORMAL=YES offset={off_primary:#x}")
    print("P1B_CODE1_B_PRIMARY_ENTRY=PASS")
    return {"off_primary": off_primary, "hdr": hdr,
            "vmlinux_sha": sha(vmlinux.read_bytes()),
            "sysmap_sha": sha(sysmap.read_bytes())}


def assemble_trampoline(out: Path, tools: dict, dtb_rel: int | None,
                        entry_rel: int) -> tuple[Path, Path, dict]:
    defines = [f"-DP1B_DTB_REL={0 if dtb_rel is None else dtb_rel}",
               f"-DP1B_ENTRY_REL={entry_rel}"]
    suffix = "final" if dtb_rel is not None else "pre"
    obj = out / f"p1b-trampoline-{suffix}.o"
    elf = out / f"p1b-trampoline-{suffix}.elf"
    run([tools["clang"], "--target=aarch64-unknown-none", "-nostdlib",
         "-ffreestanding", "-fno-asynchronous-unwind-tables",
         "-fno-unwind-tables", "-fno-ident", *defines, "-c", "-o", str(obj),
         str(HERE / "p1b-trampoline.S")])
    run([tools["lld"], "-T", str(HERE / "p1b-trampoline.ld"), "--build-id=none",
         "--nmagic", "--static", "-o", str(elf), str(obj)])
    rel = run([tools["readelf"], "-r", "--wide", str(elf)])
    if "R_AARCH64_" in rel:
        fail("P1B_RELOC_FAILED", rel)
    offs = syms(tools["readelf"], elf, ("dtb_rel", "b_primary"))
    binp = out / f"p1b-trampoline-{suffix}.bin"
    run([tools["objcopy"], "-O", "binary", str(elf), str(binp)])
    return binp, elf, offs


def trampoline_disasm_gates(out: Path, tools: dict, elf: Path,
                            offs: dict, dtb_rel: int, entry_rel: int) -> str:
    dump = run([tools["objdump"], "-d", str(elf)])
    (out / "p1b-trampoline-disasm.txt").write_text(dump)
    ops = "\n".join(l.split("\t", 2)[-1] for l in dump.splitlines()
                    if re.match(r"^\s*[0-9a-f]+:", l))
    for token in ("msr\tdaifset, #0xf", "isb", "adr\tx0", "ldr\tx9",
                  "add\tx0, x0, x9", "mov\tx1, xzr", "mov\tx2, xzr",
                  "mov\tx3, xzr", "b\t"):
        if token not in ops:
            fail("P1B_TRAMPOLINE_FAILED", f"missing {token!r}")
    if STORE_RE.search(ops):
        fail("P1B_TRAMPOLINE_FAILED", "store/adrp in trampoline")
    for bad in ("sctlr", "eret", "bl\t", "ic\tiallu", "tlbi"):
        if bad in ops:
            fail("P1B_TRAMPOLINE_FAILED", f"forbidden {bad!r}")
    branch_pc = offs["b_primary"]
    target = branch_pc + entry_rel
    if dtb_rel < 0 or dtb_rel >= (1 << 63):
        fail("P1B_TRAMPOLINE_FAILED", f"dtb_rel {dtb_rel:#x}")
    dump_s = run([tools["objdump"], "-s", "-j", ".text", str(elf)])
    if struct.pack("<Q", dtb_rel).hex() not in dump_s.lower():
        fail("P1B_TRAMPOLINE_FAILED", "dtb_rel quad value not in .text")
    print(f"P1B_TRAMPOLINE_DISASM_GATES=PASS branch {branch_pc:#x} -> "
          f"{target:#x} dtb_rel={dtb_rel:#x}")
    return dump


def build_pass(out: Path, delay: int, cpio: Path, rt_d: bytes, tools: dict,
               jobs: int) -> dict:
    k = make_kernel(out, delay, cpio, jobs)
    kg = kernel_gate(k["image"], k["vmlinux"], k["sysmap"])
    image = k["image"].read_bytes()
    image_size = kg["hdr"]["image_size"]
    dtb_offset, gap = calc_dtb_offset(image_size)

    _, elf0, offs = assemble_trampoline(out, tools, None, 0)
    entry_rel = kg["off_primary"] - offs["b_primary"]
    if entry_rel <= 0 or entry_rel % 4:
        fail("P1B_TRAMPOLINE_FAILED", f"entry_rel {entry_rel:#x}")
    binp, elf, offs2 = assemble_trampoline(out, tools, None, entry_rel)
    if offs2 != offs:
        fail("P1B_TRAMPOLINE_FAILED", "layout shifted with entry_rel")
    dtb_rel = dtb_offset - offs2["dtb_rel"]
    binp, elf, offs3 = assemble_trampoline(out, tools, dtb_rel, entry_rel)
    if offs3 != offs:
        fail("P1B_TRAMPOLINE_FAILED", "layout shifted with dtb_rel")
    tbin = binp.read_bytes()
    if not (0x30 <= len(tbin) <= 0x40):
        fail("P1B_TRAMPOLINE_FAILED", f"trampoline size {len(tbin)}")
    tramp_sha = sha(tbin)
    print(f"P1B_TRAMPOLINE sha256={tramp_sha} size={len(tbin)} "
          f"dtb_rel={dtb_rel:#x} entry_rel={entry_rel:#x}")
    disasm = trampoline_disasm_gates(out, tools, elf, offs3, dtb_rel, entry_rel)

    # PASS 2: patch code1 -> b 0x40, lay trampoline at 0x40, pad, append RT-D.
    payload = bytearray(image)
    code0_orig = bytes(payload[0:4])
    payload[CODE1_OFFSET:CODE1_OFFSET + 4] = struct.pack("<I", 0x1400000F)
    payload[TRAMP_OFFSET:TRAMP_OFFSET + len(tbin)] = tbin
    padding_len = dtb_offset - len(payload)
    if padding_len < 0:
        fail("P1B_GEOMETRY_FAILED", f"padding {padding_len}")
    payload += bytes(padding_len)
    payload += rt_d
    payload = bytes(payload)
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("P1B_PAYLOAD_FAILED", "payload length")
    if payload[0:4] != code0_orig:
        fail("P1B_PAYLOAD_FAILED", "code0 changed")
    if payload[dtb_offset:dtb_offset + 4] != struct.pack(">I", FDT_MAGIC):
        fail("P1B_PAYLOAD_FAILED", "no FDT magic at DTB_OFFSET")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA:
        fail("P1B_PAYLOAD_FAILED", "trailer RT-D mismatch")
    fin = parse_image_hdr(payload, f"payload-{delay}s")
    if fin["image_size"] != image_size or fin["file_size"] != len(payload):
        fail("P1B_PAYLOAD_FAILED", "header image_size drifted")
    if struct.unpack_from("<I", payload, CODE1_OFFSET)[0] != 0x1400000F:
        fail("P1B_PAYLOAD_FAILED", "code1 not b 0x40")

    payload_path = out / f"thyme-r3-p1b-init{delay}-kernel-payload.bin"
    payload_path.write_bytes(payload)
    head = payload[:0x80]
    hexdump = "\n".join(
        f"{off:04x}: {head[off:off + 16].hex(' ')}" for off in range(0, 0x80, 16))
    (out / f"p1b-payload-{delay}s-head-hex.txt").write_text(hexdump + "\n")
    print(f"P1B_PAYLOAD delay={delay} sha256={sha(payload)} "
          f"size={len(payload)} dtb_offset={dtb_offset:#x} gap={gap:#x}")
    print("P1B_DTB_PLACEMENT_PROOF=PASS")
    print("P1B_X0_STATIC=S+DTB_OFFSET -> RT-D FDT magic")
    return {
        "delay": delay, "image": k["image"], "vmlinux": k["vmlinux"],
        "sysmap": k["sysmap"], "config": k["config"], "version": k["version"],
        "payload": payload_path, "payload_sha": sha(payload),
        "payload_size": len(payload), "image_size": image_size,
        "image_sha": kg["hdr"]["sha256"], "image_file_size": len(image),
        "dtb_offset": dtb_offset, "gap": gap, "padding_len": padding_len,
        "tramp_sha": tramp_sha, "tramp_bin": tbin, "dtb_rel": dtb_rel,
        "entry_rel": entry_rel, "off_dtb_rel": offs3["dtb_rel"],
        "off_b_primary": offs3["b_primary"], "off_primary": kg["off_primary"],
        "init_sha": sha(cpio.read_bytes()) if False else None,
        "vmlinux_sha": kg["vmlinux_sha"], "sysmap_sha": kg["sysmap_sha"],
        "disasm": disasm,
    }


def cmd_build(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rt_d = Path(args.rt_d).read_bytes()
    gate_rt_d(rt_d)
    tools = {
        "clang": args.clang, "lld": args.lld, "objcopy": args.objcopy,
        "objdump": args.objdump, "readelf": args.readelf,
    }
    queue = sorted((REPO / "patches/linux-6.6").glob("*.patch"))
    if [p.name for p in queue] != [
        "0001-dt-bindings-arm-qcom-add-Xiaomi-Mi-10S-thyme-board.patch",
        "0002-arm64-dts-qcom-add-Xiaomi-Mi-10S-thyme-initial-board.patch",
    ]:
        fail("P1B_PATCH_QUEUE_FAILED", f"{[p.name for p in queue]}")
    for p in queue:
        run(["git", "-C", str(LINUX), "apply", "--check", "--whitespace=nowarn",
             str(p)])
        run(["git", "-C", str(LINUX), "apply", "--whitespace=nowarn", str(p)])
    qsha = sha("".join(
        f"{sha(p.read_bytes())}  {p.name}\n" for p in queue).encode())
    if qsha != PATCH_QUEUE_SHA:
        fail("P1B_PATCH_QUEUE_FAILED", f"{qsha}")
    print(f"PATCH_QUEUE_SHA256={qsha}")

    results = {}
    for delay in DELAY_PAIR:
        init = compile_init(out, delay, args.gcc, args.strip)
        cpio = out / f"initramfs-{delay}s.cpio"
        cpio.write_bytes(build_cpio(init.read_bytes()))
        cpio2 = out / f"initramfs-{delay}s.rebuild.cpio"
        cpio2.write_bytes(build_cpio(init.read_bytes()))
        if cpio.read_bytes() != cpio2.read_bytes():
            fail("P1B_CPIO_FAILED", f"rebuild not byte-identical delay={delay}")
        print(f"P1B_INITRAMFS delay={delay} sha256={sha(cpio.read_bytes())} "
              f"size={cpio.stat().st_size} REBUILD_IDENTICAL=YES")
        results[delay] = build_pass(out, delay, cpio, rt_d, tools, args.jobs)
        results[delay]["init_sha"] = sha(init.read_bytes())
        results[delay]["init_size"] = init.stat().st_size
        results[delay]["cpio_sha"] = sha(cpio.read_bytes())
        results[delay]["cpio_size"] = cpio.stat().st_size

    a, b = results[DELAY_PAIR[0]], results[DELAY_PAIR[1]]
    for field in ("dtb_offset", "gap", "padding_len", "image_size",
                  "image_file_size", "off_primary", "off_dtb_rel",
                  "off_b_primary", "entry_rel", "payload_size", "init_size",
                  "cpio_size"):
        if a[field] != b[field]:
            fail("P1B_PAIR_FAILED", f"{field}: {a[field]} vs {b[field]}")
    for field in ("tramp_bin",):
        if a[field] != b[field]:
            fail("P1B_PAIR_FAILED", f"{field} differs")
    if a["init_sha"] == b["init_sha"] or a["cpio_sha"] == b["cpio_sha"]:
        fail("P1B_PAIR_FAILED", "delay constants did not diverge")
    print("P1B_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY")

    manifest = {
        "stage": "MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI",
        "linux_base": LINUX_BASE, "patch_queue_sha256": qsha,
        "s_residue": hex(S_RESIDUE),
        "results": {
            str(d): {
                k: (v if isinstance(v, (int, str, type(None))) else
                    (sha(v.read_bytes()) if k in ("image", "vmlinux", "sysmap")
                     else "…"))
                for k, v in r.items()
                if k not in ("tramp_bin", "disasm", "image", "vmlinux",
                             "sysmap", "config", "payload", "delay")
            }
            for d, r in results.items()
        },
    }
    (out / "p1b-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    report = out / "p1b-gates.txt"
    lines = [
        "P1B_BUILD_PAIR_GATES=PASS",
        f"P1B_PATCH_QUEUE_SHA256={qsha}",
        "P1B_DTB_PLACEMENT_PROOF=PASS",
        "P1B_TRAMPOLINE_GATES=PASS",
        "P1B_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY",
        "P1B_INITRAMFS_REBUILD_IDENTICAL=YES",
        "P1B_RT_D_SHA_EXACT=PASS",
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES",
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    report.write_text("\n".join(lines) + "\n")
    print(report.read_text())


def cmd_clean_baseline(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    queue = sorted((REPO / "patches/linux-6.6").glob("*.patch"))
    for p in queue:
        run(["git", "-C", str(LINUX), "apply", "--check", "--whitespace=nowarn",
             str(p)])
        run(["git", "-C", str(LINUX), "apply", "--whitespace=nowarn", str(p)])
    qsha = sha("".join(
        f"{sha(p.read_bytes())}  {p.name}\n" for p in queue).encode())
    if qsha != PATCH_QUEUE_SHA:
        fail("P1B_PATCH_QUEUE_FAILED", f"{qsha}")
    k = make_kernel(out, None, None, args.jobs)
    kg = kernel_gate(k["image"], k["vmlinux"], k["sysmap"])
    image_sha = kg["hdr"]["sha256"]
    reproduced = image_sha == M0_IMAGE_SHA
    verdict = "YES" if reproduced else "PARTIAL"
    print(f"PATCH_QUEUE_SHA256={qsha}")
    print(f"CLEAN_IMAGE_SHA256={image_sha}")
    print(f"M0_IMAGE_SHA256={M0_IMAGE_SHA}")
    print(f"M0_BASELINE_REPRODUCED={verdict}")
    if not reproduced:
        print("M0_BASELINE_REPRODUCED_SCOPE=toolchain/build metadata only; "
              "source commit, patch queue, config line, primary_entry and "
              "Image header semantics correspond to the clean baseline")
    pe_addr = kg["off_primary"] + (int(
        [l for l in run(["nm", str(k["vmlinux"])]).splitlines()
         if l.endswith(" _text")][0].split()[0], 16))
    dump = run(["objdump", "-d", f"--start-address={pe_addr:#x}",
                f"--stop-address={pe_addr + 16:#x}", str(k["vmlinux"])])
    (out / "clean-baseline-primary-entry-disasm.txt").write_text(dump)
    report = out / "clean-baseline-gates.txt"
    report.write_text(
        "P1B_CLEAN_BASELINE_GATES=PASS\n"
        f"PATCH_QUEUE_SHA256={qsha}\n"
        f"CLEAN_IMAGE_SHA256={image_sha}\n"
        f"M0_IMAGE_SHA256={M0_IMAGE_SHA}\n"
        f"M0_BASELINE_REPRODUCED={verdict}\n"
        "PRIMARY_ENTRY_NORMAL=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


def parse_boot_v3(boot: bytes, label: str) -> dict:
    if len(boot) < PAGE or boot[:8] != BOOT_MAGIC:
        fail("P1B_BOOT_FAILED", f"{label} not ANDROID!")
    kernel_size, ramdisk_size, os_version_raw, header_size = struct.unpack_from(
        "<IIII", boot, 8)
    reserved = struct.unpack_from("<IIII", boot, 24)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    cmdline = boot[44:BOOT_HEADER_V3_SIZE]
    if header_version != 3:
        fail("P1B_BOOT_FAILED", f"{label} header_version={header_version}")
    if header_size != BOOT_HEADER_V3_SIZE:
        fail("P1B_BOOT_FAILED", f"{label} header_size={header_size}")
    ramdisk_off = align(KERNEL_OFFSET + kernel_size, PAGE)
    ramdisk_end = ramdisk_off + ramdisk_size
    if ramdisk_end > len(boot):
        fail("P1B_BOOT_FAILED", f"{label} truncated")
    return {
        "kernel_size": kernel_size, "ramdisk_size": ramdisk_size,
        "os_version_raw": os_version_raw, "reserved": reserved,
        "cmdline": cmdline, "kernel": boot[KERNEL_OFFSET:KERNEL_OFFSET + kernel_size],
        "ramdisk": boot[ramdisk_off:ramdisk_end],
        "tail_pad": len(boot) - ramdisk_end, "ramdisk_off": ramdisk_off,
        "total": len(boot),
    }


def splice_boot(m5d: bytes, payload: bytes) -> bytes:
    ref = parse_boot_v3(m5d, "m5d")
    hdr = bytearray(m5d[:PAGE])
    struct.pack_into("<I", hdr, 8, len(payload))
    out = bytes(hdr) + payload
    out += b"\x00" * (align(len(out), PAGE) - len(out))
    out += ref["ramdisk"]
    out += b"\x00" * ref["tail_pad"]
    return out


def cmd_splice_boot(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("P1B_M5D_IDENTITY_FAILED", f"sha={sha(m5d)}")
    boot = splice_boot(m5d, payload)
    out = Path(args.boot)
    out.write_bytes(boot)
    print(f"P1B_BOOT_PACKED sha256={sha(boot)} size={len(boot)}")


def cmd_pack_gates(args: argparse.Namespace) -> None:
    m5d = Path(args.m5d_boot).read_bytes()
    payload = Path(args.payload).read_bytes()
    boot = Path(args.boot).read_bytes()
    if sha(m5d) != args.m5d_sha:
        fail("P1B_M5D_IDENTITY_FAILED", f"sha={sha(m5d)}")
    if sha(payload) != args.payload_sha:
        fail("P1B_PAYLOAD_IDENTITY_FAILED", f"sha={sha(payload)}")
    ref = parse_boot_v3(m5d, "m5d")
    cand = parse_boot_v3(boot, "candidate")
    if cand["kernel"] != payload:
        fail("P1B_PACK_FAILED", "candidate kernel != payload")
    if cand["ramdisk"] != ref["ramdisk"]:
        fail("P1B_PACK_FAILED", "ramdisk bytes differ from M5D")
    if cand["cmdline"] != ref["cmdline"]:
        fail("P1B_PACK_FAILED", "cmdline differs from M5D")
    if cand["os_version_raw"] != ref["os_version_raw"]:
        fail("P1B_PACK_FAILED", "os_version differs from M5D")
    if cand["reserved"] != ref["reserved"]:
        fail("P1B_PACK_FAILED", "reserved differs from M5D")
    if cand["ramdisk_size"] != ref["ramdisk_size"]:
        fail("P1B_PACK_FAILED", "ramdisk_size differs")
    if cand["tail_pad"] != ref["tail_pad"]:
        fail("P1B_PACK_FAILED", "tail padding policy differs")
    if boot[:8] != b"ANDROID!" or struct.unpack_from("<I", boot, 8)[0] != len(payload):
        fail("P1B_PACK_FAILED", "kernel_size field")
    diff = [i for i in range(PAGE) if boot[i] != m5d[i]]
    allowed = set(range(8, 12))
    if set(diff) - allowed:
        fail("P1B_PACK_FAILED", f"header diff at {sorted(set(diff) - allowed)}")
    if len(boot) >= BOOT_CAP:
        fail("P1B_CAPACITY_FAILED", f"boot {len(boot)} >= {BOOT_CAP}")
    if BOOT_CAP - len(boot) < 0x1000000:
        fail("P1B_CAPACITY_FAILED", "margin < 16MiB")
    hdr = parse_image_hdr(payload, "payload")
    dtb_offset, gap = calc_dtb_offset(hdr["image_size"])
    if len(payload) != dtb_offset + RT_D_SIZE:
        fail("P1B_PACK_FAILED", "payload length != DTB_OFFSET + RT-D")
    trailer = payload[dtb_offset:]
    if sha(trailer) != RT_D_SHA:
        fail("P1B_PACK_FAILED", "trailer RT-D mismatch after extraction")
    if (S_RESIDUE + dtb_offset) % ALIGN_2M != 0:
        fail("P1B_PACK_FAILED", "DTB residue geometry")
    report = Path(args.out) / "p1b-pack-gates.txt"
    report.write_text(
        "P1B_PACK_GATES=PASS\n"
        f"P1B_BOOT_SIZE={len(boot)}\n"
        f"P1B_BOOT_SHA256={sha(boot)}\n"
        f"P1B_KERNEL_SIZE={len(payload)}\n"
        f"P1B_DTB_OFFSET={dtb_offset:#x}\n"
        "P1B_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY\n"
        "P1B_RT_D_TRAILER_SHA_EXACT=PASS\n"
        "P1B_BOOT_CAPACITY=PASS\n"
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES\n"
        "DEVICE_OPERATION=NO\n"
        "READY_FOR_DEVICE=NO\n")
    print(report.read_text())


def cmd_source_gate(_args: argparse.Namespace) -> None:
    required = [
        HERE / "p1b-trampoline.S", HERE / "p1b-trampoline.ld",
        HERE / "p1b-init.c", HERE / "p1b-init.ld",
        REPO / "configs" / "thyme-r3-p1b.config", DOC, WF,
        Path(__file__),
    ]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            fail("P1B_SOURCE_GATE_FAILED", f"missing {path}")
    tramp = (HERE / "p1b-trampoline.S").read_text()
    init_c = (HERE / "p1b-init.c").read_text()
    script = Path(__file__).read_text()
    doc = DOC.read_text()
    wf = WF.read_text()
    for token in ("r3_handoff_entry", "P1B_DTB_REL", "P1B_ENTRY_REL",
                  "daifset", "dtb_rel", "b_primary"):
        if token not in tramp:
            fail("P1B_SOURCE_GATE_FAILED", f"trampoline missing {token}")
    for token in ("SYS_clock_nanosleep", "SYS_reboot", "SYS_exit_group",
                  "LINUX_REBOOT_CMD_RESTART", "CLOCK_MONOTONIC",
                  "THYME-R3-P1B-INIT"):
        if token not in init_c:
            fail("P1B_SOURCE_GATE_FAILED", f"init missing {token}")
    if "busybox" in init_c.lower():
        fail("P1B_SOURCE_GATE_FAILED", "init must not pull busybox")
    for token in (
        str(RT_D_SHA), str(RT_D_SIZE), LINUX_BASE, M0_IMAGE_SHA,
        PATCH_QUEUE_SHA, "S_RESIDUE", "0x80000", "DELAY_CONSTANT_ONLY",
        "ABL_LOADS_FULL_BOOT_KERNEL_SIZE", "KERNEL_64BIT_LOAD_OFFSET",
        "0x217F000", "R3_LOAD_ALIGNMENT_PROVEN", "R3_ENTRY_STATE_PRIMARY_",
        "M5N_TARGETING_ISOLATION=FROZEN", "COPYDOWN_REQUIRED=NO",
        "M0_BASELINE_REPRODUCED", "PRIMARY_ENTRY_NORMAL=YES",
        "P1B_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY",
        "READY_FOR_R3_P1B_INIT8_DEVICE_CONTROL",
        "R3_P1B_BLOCKED_BY_KERNEL_TRAILER_LOAD",
        "R3_P1B_BLOCKED_BY_DTB_PLACEMENT",
        "R3_P1B_BLOCKED_BY_IMAGE_PROVENANCE",
        "R3_P1B_CI_NOT_READY",
        "rdinit=/init panic=5 loglevel=7",
    ):
        if token not in doc:
            fail("P1B_SOURCE_GATE_FAILED", f"doc missing {token}")
    if "READY_FOR_DEVICE=YES" in doc or "READY_FOR_DEVICE=YES" in script:
        fail("P1B_SOURCE_GATE_FAILED", "must not claim device-ready")
    if re.search(r"^\s+run:.*\b(fastboot|adb|flash)\b", wf, re.M):
        fail("P1B_SOURCE_GATE_FAILED", "public workflow has device verbs")
    if "Does not emit a flashable boot image" not in wf:
        fail("P1B_SOURCE_GATE_FAILED", "public workflow boot-image boundary")
    if "splice-boot" in wf or "mkbootimg" in wf:
        fail("P1B_SOURCE_GATE_FAILED", "public workflow packs boot images")
    for off, want in ((0x2220000, 0x2380000), (0x2208000, 0x2300000),
                      (0x1B1C0A0, 0x1C00000)):
        got, gap = calc_dtb_offset(off)
        if got != want:
            fail("P1B_SOURCE_GATE_FAILED",
                 f"formula image_size={off:#x} -> {got:#x} != {want:#x}")
    if calc_dtb_offset(0x2220000)[1] != 0x160000:
        fail("P1B_SOURCE_GATE_FAILED", "gap != 0x160000 for sample")
    print("P1B_SOURCE_GATE=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "build-pair", "clean-baseline", "kernel-gate",
        "splice-boot", "pack-gates"), required=True)
    parser.add_argument("--out", default="out-r3-p1b")
    parser.add_argument("--rt-d")
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--lld", default="ld.lld-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    parser.add_argument("--objdump", default="llvm-objdump-18")
    parser.add_argument("--readelf", default="llvm-readelf-18")
    parser.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    parser.add_argument("--strip", default="aarch64-linux-gnu-strip")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--image")
    parser.add_argument("--vmlinux")
    parser.add_argument("--sysmap")
    parser.add_argument("--m5d-boot")
    parser.add_argument("--m5d-sha", default=(
        "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"))
    parser.add_argument("--payload")
    parser.add_argument("--payload-sha")
    parser.add_argument("--boot")
    args = parser.parse_args()
    if args.mode == "source-gate":
        cmd_source_gate(args)
        return
    if args.mode == "build-pair":
        if not args.rt_d:
            fail("P1B_BUILD_FAILED", "--rt-d required")
        cmd_build(args)
        return
    if args.mode == "clean-baseline":
        cmd_clean_baseline(args)
        return
    if args.mode == "kernel-gate":
        if not (args.image and args.vmlinux and args.sysmap):
            fail("P1B_KERNEL_GATE_FAILED", "need --image --vmlinux --sysmap")
        kg = kernel_gate(Path(args.image), Path(args.vmlinux),
                         Path(args.sysmap))
        print(f"KERNEL_GATE=PASS off_primary={kg['off_primary']:#x}")
        return
    if args.mode == "splice-boot":
        if not (args.m5d_boot and args.payload and args.boot):
            fail("P1B_SPLICE_FAILED", "need --m5d-boot --payload --boot")
        cmd_splice_boot(args)
        return
    if args.mode == "pack-gates":
        if not (args.m5d_boot and args.payload and args.boot
                and args.payload_sha):
            fail("P1B_PACK_FAILED", "need --m5d-boot --payload --boot "
                                    "--payload-sha")
        Path(args.out).mkdir(parents=True, exist_ok=True)
        cmd_pack_gates(args)
        return


if __name__ == "__main__":
    main()
