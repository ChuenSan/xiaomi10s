#!/usr/bin/env python3
"""R3 P1 Linux boot-contract source gate and GHA prototype. GitHub Actions only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local assemble/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1-linux-boot-contract.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1-linux-boot-contract.yml"
EVIDENCE = HERE / "dts" / "thyme-runtime-memory-evidence.json"
LLVM_VERSION = "18.1.3"
LINUX_BASE = "8b73de7da85fde281a385e0b26eda9bffd3ca477"
M0_IMAGE_SHA = "22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6"
M1_RAW_DTB_SHA = "a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40"
M5D_IMAGE_SHA = "5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a"
M5D_BOOT_SHA = "4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63"
ARM64_MAGIC = b"ARM\x64"
FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9
STORE_RE = re.compile(
    r"\b(str|strb|strh|stp|stur|stlr|stlxr|stxr|sttr|stnp|stadd)\b", re.I
)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    msg = label if not detail else f"{label}: {detail}"
    raise SystemExit(msg)


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        fail("P1_CMD_FAILED", f"{' '.join(cmd)}\n{proc.stderr}")
    return proc.stdout


def load_runtime_evidence() -> dict | None:
    """Numeric RAM evidence from the R3 runtime capture, or None pre-R3."""
    if not EVIDENCE.is_file():
        return None
    try:
        data = json.loads(EVIDENCE.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        fail("P1_RUNTIME_EVIDENCE_INVALID", str(exc))
    banks = data.get("memory", {}).get("banks") or []
    if not banks or not data.get("memory", {}).get("total"):
        fail("P1_RUNTIME_EVIDENCE_INVALID", "memory map empty")
    if not data.get("capture", {}).get("runtime_fdt_available"):
        fail("P1_RUNTIME_EVIDENCE_INVALID", "runtime FDT unavailable")
    for bank in banks:
        if not bank.get("size"):
            fail("P1_RUNTIME_EVIDENCE_INVALID", "zero-size bank")
    return data


def source_gate() -> None:
    required = [
        HERE / "p1-trampoline.S",
        HERE / "p1-trampoline.ld",
        HERE / "p1-init.c",
        HERE / "p1-init.ld",
        HERE / "p1-state-probe.S",
        HERE / "dts" / "sm8250-xiaomi-thyme-runtime.dts",
        REPO / "configs" / "thyme-r3-p1.config",
        DOC,
        WF,
    ]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            fail("P1_SOURCE_GATE_FAILED", f"missing {path}")
    tramp = (HERE / "p1-trampoline.S").read_text()
    probe = (HERE / "p1-state-probe.S").read_text()
    init_c = (HERE / "p1-init.c").read_text()
    dts = (HERE / "dts" / "sm8250-xiaomi-thyme-runtime.dts").read_text()
    script = Path(__file__).read_text()
    doc = DOC.read_text()
    wf = WF.read_text()
    for token in (
        "P1_DTB_REL", "P1_ENTRY_REL", "p1_entry", "cntpct_el0",
    ):
        if token == "cntpct_el0":
            if token not in probe:
                fail("P1_SOURCE_GATE_FAILED", f"probe missing {token}")
            continue
        if token not in tramp:
            fail("P1_SOURCE_GATE_FAILED", f"trampoline missing {token}")
    if STORE_RE.search(tramp) or STORE_RE.search(probe):
        fail("P1_SOURCE_GATE_FAILED", "store mnemonic in trampoline/probe")
    for blob, label in ((tramp, "trampoline"), (probe, "probe")):
        for forbidden in ("sctlr_el", "msr\t", "eret", "0x80000000", ".bss", ".got"):
            if forbidden in blob and not (
                label == "probe" and forbidden == "sctlr_el"
            ):
                if label == "probe" and forbidden == "sctlr_el":
                    continue
                fail("P1_SOURCE_GATE_FAILED", f"{label} has {forbidden!r}")
    if "mrs	x2, sctlr_el1" not in probe or "msr" in probe:
        fail("P1_SOURCE_GATE_FAILED", "probe must read SCTLR and never write it")
    for token in (
        "THYME-R3-P1-INIT", "DELAY_SECONDS", "SYS_mount", "SYS_reboot",
        "LINUX_REBOOT_CMD_RESTART", "/proc/uptime", "/proc/cmdline",
        "/proc/device-tree/model",
    ):
        if token not in init_c:
            fail("P1_SOURCE_GATE_FAILED", f"init missing {token}")
    if "busybox" in init_c.lower():
        fail("P1_SOURCE_GATE_FAILED", "init must not pull busybox")
    for token in (
        "rdinit=/init panic=5 loglevel=7",
        "/delete-node/ &xbl_aop_mem",
        "0x80600000",
        "0x88c00000",
        "0x8bb00000",
        "0x8e000000",
        "0x9c000000",
    ):
        if token not in dts:
            fail("P1_SOURCE_GATE_FAILED", f"runtime dts missing {token}")
    if load_runtime_evidence() is None:
        if "0x3bb00000" in dts or "0xc0000000" in dts:
            fail("P1_SOURCE_GATE_FAILED", "runtime dts must not invent lmi RAM banks")
    else:
        if "0x3bb00000" in dts:
            fail("P1_SOURCE_GATE_FAILED", "runtime dts must not invent lmi RAM banks")
    if "GITHUB_ACTIONS" not in script:
        fail("P1_SOURCE_GATE_FAILED", "script missing GITHUB_ACTIONS guard")
    for token in (
        "MAINLINE_V2_R3_P0_TIMING_PAIR_ENTRY_PROVEN",
        "M5D_IS_FULL_LINUX_BOOT_BASELINE=NO",
        "M1_RAW_DTB_IS_FULL_RUNTIME_BASELINE=NO",
        "M1_RUNTIME_DTB_SELF_CONTAINED=NO",
        "R3_P1_ABL_CONTEXT_BASELINE=ACTIVE_A_STOCK",
        "M5N_TARGETING_ISOLATION=FROZEN",
        "ENTRY_MMU_REQUIRED_STATE=off",
        "ENTRY_DCACHE_REQUIRED_STATE=off",
        "DIRECT_PATH_NEEDS_ABSOLUTE_S=NO",
        "S_MOD_2M_REQUIRED=YES",
        "BUILT_IN_INITRAMFS=YES",
        "LINUX_INIT_TIMING_SIGNATURE",
        "R3_P1_BOOT_CONTRACT_INCOMPLETE",
        "R3_RUNTIME_DTB_COMPLETION_CI",
        "Primary blocker=RAM_MAP",
        LINUX_BASE,
        M0_IMAGE_SHA,
        M1_RAW_DTB_SHA,
        M5D_IMAGE_SHA,
        "LOCAL_BUILD:                       NO",
        "DEVICE_OPERATION:                  NO",
        "READY_FOR_DEVICE",
    ):
        if token not in doc:
            fail("P1_SOURCE_GATE_FAILED", f"doc missing {token}")
    if "READY_FOR_DEVICE=YES" in doc or "FLASHABLE_READY=YES" in doc:
        fail("P1_SOURCE_GATE_FAILED", "doc must not claim device-ready")
    if re.search(r"^\s+run:.*\b(fastboot|adb|flash)\b", wf, re.M):
        fail("P1_SOURCE_GATE_FAILED", "public workflow has device verbs")
    if "Does not emit a flashable boot image" not in wf:
        fail("P1_SOURCE_GATE_FAILED", "public workflow boot-image boundary")
    print("P1_SOURCE_GATE=PASS")


def parse_fdt(blob: bytes) -> dict:
    if len(blob) < 40:
        fail("P1_DTB_PARSE_FAILED", "short")
    magic, totalsize, off_struct, off_strings, _rsv, version, _lc, _cpu, _ss, _st = (
        struct.unpack(">10I", blob[:40])
    )
    if magic != FDT_MAGIC:
        fail("P1_DTB_PARSE_FAILED", f"magic=0x{magic:08x}")
    if totalsize > len(blob) or totalsize < 40:
        fail("P1_DTB_PARSE_FAILED", f"totalsize={totalsize} file={len(blob)}")
    if version < 16:
        fail("P1_DTB_PARSE_FAILED", f"version={version}")
    strings = blob[off_strings:totalsize]
    structb = blob[off_struct:totalsize]
    nodes: dict[str, dict[str, bytes]] = {}
    path: list[str] = []
    i = 0

    def align4(n: int) -> int:
        return (n + 3) & ~3

    while i + 4 <= len(structb):
        token = struct.unpack_from(">I", structb, i)[0]
        i += 4
        if token == FDT_BEGIN_NODE:
            end = structb.index(b"\x00", i)
            name = structb[i:end].decode("ascii", "replace")
            i = align4(end + 1)
            path.append(name)
            nodes["/".join(path)] = {}
        elif token == FDT_END_NODE:
            if path:
                path.pop()
        elif token == FDT_PROP:
            plen, nameoff = struct.unpack_from(">II", structb, i)
            i += 8
            nend = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:nend].decode("ascii", "replace")
            pval = structb[i:i + plen]
            i = align4(i + plen)
            nodes.setdefault("/".join(path), {})[pname] = pval
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            fail("P1_DTB_PARSE_FAILED", f"token={token}")
    return {"totalsize": totalsize, "nodes": nodes, "size": len(blob)}


def cells(prop: bytes, n: int) -> list[int]:
    if n <= 0 or len(prop) % (4 * n) != 0:
        return []
    out = []
    for i in range(0, len(prop), 4 * n):
        v = 0
        for w in struct.unpack(">" + "I" * n, prop[i:i + 4 * n]):
            v = (v << 32) | w
        out.append(v)
    return out


def audit_dtb(blob: bytes, label: str) -> dict:
    fdt = parse_fdt(blob)
    nodes = fdt["nodes"]
    root = nodes.get("", {}) or nodes.get("/", {})
    compatible = root.get("compatible", b"").split(b"\x00")
    compatible_s = [c.decode() for c in compatible if c]
    model = root.get("model", b"").split(b"\x00")[0].decode("ascii", "replace")
    acells = cells(root.get("#address-cells", b"\x00\x00\x00\x02"), 1)
    scells = cells(root.get("#size-cells", b"\x00\x00\x00\x02"), 1)
    addr_cells = acells[0] if acells else 2
    size_cells = scells[0] if scells else 2
    mem_nodes = []
    for path, props in nodes.items():
        leaf = path.split("/")[-1]
        if props.get("device_type", b"").startswith(b"memory") or leaf.startswith("memory"):
            if leaf in ("memory",) or leaf.startswith("memory@"):
                mem_nodes.append((path, props))
    banks = []
    mem_nonzero = False
    for path, props in mem_nodes:
        if not props.get("device_type", b"").startswith(b"memory"):
            continue
        raw = props.get("reg", b"")
        stride = addr_cells + size_cells
        vals = cells(raw, 1)
        for i in range(0, len(vals) - stride + 1, stride):
            addr_parts = vals[i:i + addr_cells]
            size_parts = vals[i + addr_cells:i + stride]
            addr = 0
            size = 0
            for p in addr_parts:
                addr = (addr << 32) | p
            for p in size_parts:
                size = (size << 32) | p
            banks.append((addr, size))
            if size:
                mem_nonzero = True
    reserved = [p for p in nodes if "reserved-memory" in p.split("/") and p.split("/")[-1] not in ("", "reserved-memory")]
    leaves = {p.split("/")[-1] for p in nodes}
    has_cpus = "cpus" in leaves or any("/cpus/" in f"/{p.strip('/')}/" for p in nodes)
    has_psci = "psci" in leaves
    has_timer = "timer" in leaves or any(l.startswith("timer@") for l in leaves)
    has_gic = any("interrupt-controller@" in p for p in nodes)
    chosen = nodes.get("chosen", {}) or nodes.get("/chosen", {})
    bootargs = chosen.get("bootargs", b"").split(b"\x00")[0].decode("ascii", "replace")
    self_contained = bool(
        mem_nonzero and has_cpus and has_psci and has_timer and has_gic and reserved
    )
    report = {
        "label": label,
        "size": fdt["size"],
        "totalsize": fdt["totalsize"],
        "sha256": sha(blob),
        "model": model,
        "compatible": compatible_s,
        "memory_banks": banks,
        "memory_nonzero": mem_nonzero,
        "reserved_children": len(reserved),
        "cpus": has_cpus,
        "psci": has_psci,
        "timer": has_timer,
        "gic": has_gic,
        "bootargs": bootargs,
        "self_contained": self_contained,
    }
    print(f"DTB_AUDIT label={label}")
    print(f"  size={report['size']} totalsize={report['totalsize']}")
    print(f"  sha256={report['sha256']}")
    print(f"  model={model!r} compatible={compatible_s}")
    print(f"  banks={[(hex(a), hex(s)) for a, s in banks]}")
    print(f"  memory_nonzero={mem_nonzero} reserved_children={len(reserved)}")
    print(f"  cpus={has_cpus} psci={has_psci} timer={has_timer} gic={has_gic}")
    print(f"  bootargs={bootargs!r}")
    print(f"  self_contained={self_contained}")
    return report


def compile_init(out: Path, delay: int) -> Path:
    elf = out / f"p1-init-{delay}s"
    cmd = [
        "aarch64-linux-gnu-gcc",
        "-ffreestanding", "-nostdlib", "-static", "-no-pie", "-fno-pic",
        "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-fno-ident",
        "-Os", "-Wall", "-Werror",
        "-Wl,-e,main", "-Wl,--build-id=none", "-Wl,-z,noexecstack",
        f"-Wl,-T{HERE / 'p1-init.ld'}",
        f"-DDELAY_SECONDS={delay}",
        "-o", str(elf), str(HERE / "p1-init.c"),
    ]
    run(cmd)
    run(["aarch64-linux-gnu-strip", "-s", str(elf)])
    info = run(["file", "-b", str(elf)])
    if "ELF 64-bit LSB" not in info or "aarch64" not in info.lower():
        fail("P1_INIT_FAILED", info)
    interp = run(["aarch64-linux-gnu-readelf", "-l", str(elf)])
    if "INTERP" in interp:
        fail("P1_INIT_FAILED", "PT_INTERP present")
    dyn = subprocess.run(
        ["aarch64-linux-gnu-readelf", "-d", str(elf)],
        capture_output=True, text=True, check=False,
    )
    if "NEEDED" in dyn.stdout:
        fail("P1_INIT_FAILED", "dynamic NEEDED")
    ident = run(["strings", str(elf)])
    if f"THYME-R3-P1-INIT DELAY={delay}" not in ident:
        fail("P1_INIT_FAILED", "ident string")
    if not (elf.stat().st_mode & 0o111):
        elf.chmod(0o755)
    print(f"P1_INIT delay={delay} sha256={sha(elf.read_bytes())} size={elf.stat().st_size}")
    return elf


def tool(*names: str) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    fail("P1_TOOLCHAIN_FAILED", " ".join(names))
    raise AssertionError


def assemble_bin(src: Path, out_bin: Path, defines: list[str]) -> None:
    clang = tool("clang-18", "clang")
    lld = tool("ld.lld-18", "ld.lld")
    objcopy = tool("llvm-objcopy-18", "llvm-objcopy", "objcopy")
    readelf = tool("llvm-readelf-18", "llvm-readelf", "readelf")
    obj = out_bin.with_suffix(".o")
    elf = out_bin.with_suffix(".elf")
    cmd = [
        clang, "--target=aarch64-unknown-none", "-nostdlib", "-ffreestanding",
        "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fno-ident",
        *defines, "-c", "-o", str(obj), str(src),
    ]
    run(cmd)
    run([
        lld, "-T", str(HERE / "p1-trampoline.ld"), "--build-id=none", "--nmagic",
        "--static", "-o", str(elf), str(obj),
    ])
    rel = run([readelf, "-r", "--wide", str(elf)])
    if "R_AARCH64_" in rel:
        fail("P1_RELOC_FAILED", rel)
    run([objcopy, "-O", "binary", str(elf), str(out_bin)])


def prototype(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    init8 = compile_init(out, 8)
    init24 = compile_init(out, 24)
    if sha(init8.read_bytes()) == sha(init24.read_bytes()):
        fail("P1_INIT_FAILED", "8s == 24s")
    tramp = out / "p1-trampoline.bin"
    assemble_bin(
        HERE / "p1-trampoline.S",
        tramp,
        ["-DP1_DTB_REL=4096", "-DP1_ENTRY_REL=0x1b1c060"],
    )
    tbytes = tramp.read_bytes()
    if tbytes[56:60] != ARM64_MAGIC:
        fail("P1_TRAMPOLINE_FAILED", "ARM64 magic")
    if len(tbytes) < 0x50:
        fail("P1_TRAMPOLINE_FAILED", f"size={len(tbytes)}")
    print(f"P1_TRAMPOLINE sha256={sha(tbytes)} size={len(tbytes)}")
    probe = out / "p1-state-probe.bin"
    assemble_bin(HERE / "p1-state-probe.S", probe, [])
    print(f"P1_STATE_PROBE sha256={sha(probe.read_bytes())} size={probe.stat().st_size}")
    dtb_reports = []
    if (LINUX / "arch/arm64/boot/dts/qcom/sm8250-xiaomi-thyme.dts").is_file():
        dtb_reports = compile_and_audit_dts(out)
    else:
        print("P1_DTS_SKIP=linux thyme dts not applied in this job")
    evidence = load_runtime_evidence()
    report = out / "contract-report.txt"
    lines = [
        "R3_P1_LINUX_BOOT_CONTRACT=INCOMPLETE",
        "Final Gate=R3_P1_BOOT_CONTRACT_INCOMPLETE",
        "Primary blocker=RAM_MAP" if evidence is None
        else "Primary blocker=P1_TRUE_DEVICE_ENTRY_VALIDATION",
        "M1_RUNTIME_DTB_SELF_CONTAINED=NO",
        f"RT_D_RUNTIME_DTB_SELF_CONTAINED={'YES' if evidence else 'NO'}",
        "M5D_IS_FULL_LINUX_BOOT_BASELINE=NO",
        "DEVICE_READY=NO",
        f"INIT_8_SHA256={sha(init8.read_bytes())}",
        f"INIT_24_SHA256={sha(init24.read_bytes())}",
        f"TRAMPOLINE_SHA256={sha(tbytes)}",
        f"PROBE_SHA256={sha(probe.read_bytes())}",
    ]
    for r in dtb_reports:
        lines.append(
            f"DTB {r['label']} self_contained={r['self_contained']} "
            f"memory_nonzero={r['memory_nonzero']} sha256={r['sha256']}"
        )
    report.write_text("\n".join(lines) + "\n")
    print(report.read_text())
    print("P1_PROTOTYPE=PASS")
    print("READY_FOR_DEVICE=NO")


def compile_and_audit_dts(out: Path) -> list[dict]:
    qcom = LINUX / "arch/arm64/boot/dts/qcom"
    inc = [
        f"-I{LINUX / 'include'}",
        f"-I{LINUX / 'arch/arm64/boot/dts'}",
        f"-I{qcom}",
        f"-I{LINUX / 'scripts/dtc/include-prefixes'}",
    ]
    reports = []
    for label, src in (
        ("RT-A-m1-source", qcom / "sm8250-xiaomi-thyme.dts"),
        ("RT-D-runtime", HERE / "dts" / "sm8250-xiaomi-thyme-runtime.dts"),
    ):
        pre = out / f"{label}.pre.dts"
        dtb = out / f"{label}.dtb"
        cpp = [
            "cpp", "-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp",
            *inc, str(src),
        ]
        proc = subprocess.run(cpp, capture_output=True, check=False)
        if proc.returncode != 0:
            fail("P1_DTS_CPP_FAILED", proc.stderr.decode())
        pre.write_bytes(proc.stdout)
        run(["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", str(dtb), str(pre)])
        reports.append(audit_dtb(dtb.read_bytes(), label))
    evidence = load_runtime_evidence()
    if evidence is None:
        if reports[0]["self_contained"] or reports[1]["self_contained"]:
            fail("P1_DTB_FALSE_SELF_CONTAINED", "RAM size is unproven; DTB must not pass")
        print("M1_RUNTIME_DTB_SELF_CONTAINED=NO")
        print("RT_D_RUNTIME_DTB_SELF_CONTAINED=NO")
        return reports
    # Evidence present: RT-A must keep the ABL-patched placeholder RAM;
    # RT-D must be self-contained with exactly the evidence banks.
    if reports[0]["self_contained"]:
        fail("P1_DTB_FALSE_SELF_CONTAINED", "RT-A must keep placeholder RAM")
    if not reports[1]["self_contained"]:
        fail("R3_RUNTIME_DTB_NOT_SELF_CONTAINED", json.dumps(reports[1]))
    ev_banks = sorted([b["base"], b["size"]] for b in evidence["memory"]["banks"])
    rt_banks = sorted([list(b) for b in reports[1]["memory_banks"]])
    if ev_banks != rt_banks:
        fail("R3_RUNTIME_DTB_BANKS_MISMATCH",
             f"evidence={ev_banks} dtb={rt_banks}")
    print("M1_RUNTIME_DTB_SELF_CONTAINED=NO")
    print("RT_D_RUNTIME_DTB_SELF_CONTAINED=YES")
    print("RT_D_BANKS_PROVENANCE=THYME_RUNTIME_MEMORY_EVIDENCE")
    return reports


def parse_image(image: bytes) -> dict:
    if len(image) < 64 or image[56:60] != ARM64_MAGIC:
        fail("P1_IMAGE_HEADER_FAILED", "not ARM64 Image")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<QQQQQQ", image, 8)
    pe = struct.unpack_from("<I", image, 60)[0]
    return {
        "size": len(image),
        "sha256": sha(image),
        "code0": code0,
        "code1": code1,
        "text_offset": text_offset,
        "image_size": image_size,
        "flags": flags,
        "res2": res2,
        "res3": res3,
        "res4": res4,
        "pe_offset": pe,
    }


def kernel_gate(image: Path, vmlinux: Path, sysmap: Path) -> None:
    hdr = parse_image(image.read_bytes())
    print("CLEAN_IMAGE_HEADER", hdr)
    if hdr["text_offset"] != 0x80000:
        fail("P1_IMAGE_HEADER_FAILED", f"text_offset={hdr['text_offset']:#x}")
    if hdr["flags"] & 1:
        fail("P1_IMAGE_HEADER_FAILED", "big-endian")
    if hdr["res2"] or hdr["res3"] or hdr["res4"]:
        fail("P1_IMAGE_HEADER_FAILED", "reserved")
    nm = run(["nm", str(vmlinux)])
    pe_line = [ln for ln in nm.splitlines() if ln.endswith(" primary_entry")]
    if not pe_line:
        fail("P1_PRIMARY_ENTRY_FAILED", "symbol missing")
    addr = int(pe_line[0].split()[0], 16)
    text_line = [ln for ln in nm.splitlines() if ln.endswith(" _text") or ln.endswith(" _head")]
    print(f"primary_entry vaddr={addr:#x} nm={pe_line[0]}")
    dump = run(["objdump", "-d", f"--start-address={addr:#x}", f"--stop-address={addr + 16:#x}",
                str(vmlinux)])
    print(dump)
    if re.search(r"\tb\s+\.", dump) or "14000000" in dump.split("primary_entry", 1)[-1][:80]:
        first = dump
        if re.search(r"<primary_entry>:\s*\n\s*[0-9a-f]+:\s+00 00 00 14", first, re.I):
            fail("P1_PRIMARY_ENTRY_FAILED", "b . spin")
    if "bl" not in dump and "adr" not in dump:
        fail("P1_PRIMARY_ENTRY_FAILED", "unexpected first instructions")
    print("PRIMARY_ENTRY_NORMAL=YES")
    print("M5D_SPIN_CONTROL_EXCLUDED=YES")
    print(f"System.map sha256={sha(sysmap.read_bytes())}")
    print(f"vmlinux sha256={sha(vmlinux.read_bytes())}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("source-gate", "prototype", "kernel-gate"),
                        required=True)
    parser.add_argument("--out", default="out-r3-p1")
    parser.add_argument("--image")
    parser.add_argument("--vmlinux")
    parser.add_argument("--sysmap")
    args = parser.parse_args()
    if args.mode == "source-gate":
        source_gate()
        return
    if args.mode == "prototype":
        source_gate()
        prototype(Path(args.out))
        return
    if not args.image or not args.vmlinux or not args.sysmap:
        fail("P1_KERNEL_GATE_FAILED", "need --image --vmlinux --sysmap")
    kernel_gate(Path(args.image), Path(args.vmlinux), Path(args.sysmap))


if __name__ == "__main__":
    main()
