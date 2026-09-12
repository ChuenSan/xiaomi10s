#!/usr/bin/env python3
"""R3 RUNTIME_DTB_COMPLETION_CI evidence parser. GitHub Actions only.

Parses the Stock Android A runtime FDT (/sys/firmware/fdt), the runtime
OF-tree tar, /proc/iomem, /proc/meminfo, the memory sysfs fallback, filtered
dmesg, and the raw Stock DTB0, then emits the numeric
THYME_RUNTIME_MEMORY_EVIDENCE JSON. Sensitive properties (seeds/serials/MACs)
are never emitted: presence only. bootargs are token-sanitized. The OEM
binaries never leave the private repository; only this numeric summary may be
mirrored to the public repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import tarfile
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local parsing/validation")

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9
DENYLIST_EXACT = {
    "serial-number", "kaslr-seed", "rng-seed", "random-seed",
    "linux,kaslr-seed", "linux,rng-seed", "mac-address", "local-mac-address",
    "bluetooth-local-bd-address", "wifi-mac-address", "imei", "cpuid",
    "device-serial", "token",
}
DENYLIST_SUBSTR = ("kaslr", "rng-seed", "random-seed", "serial-number", "imei")
BOOTARGS_ALLOW = {
    "console", "earlycon", "rdinit", "init", "root", "rootwait", "rw", "ro",
    "loglevel", "panic", "quiet", "ignore_loglevel",
}


def fail(label: str, detail: str = "") -> None:
    msg = label if not detail else f"{label}: {detail}"
    raise SystemExit(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cells_u32(prop: bytes) -> list[int]:
    if len(prop) % 4:
        fail("EVIDENCE_PARSE_FAILED", f"reg not 4-byte aligned: {len(prop)}")
    return list(struct.unpack(f">{len(prop) // 4}I", prop))


def fold(parts: list[int]) -> int:
    v = 0
    for p in parts:
        v = (v << 32) | p
    return v


def parse_fdt(blob: bytes) -> dict:
    if len(blob) < 40:
        fail("FDT_INVALID", "short header")
    (magic, totalsize, off_struct, off_strings, off_rsv,
     version, _lc, _cpu, _ss, _st) = struct.unpack(">10I", blob[:40])
    if magic != FDT_MAGIC:
        fail("FDT_INVALID", f"magic=0x{magic:08x}")
    if totalsize > len(blob) or totalsize < 40:
        fail("FDT_INVALID", f"totalsize={totalsize} file={len(blob)}")
    if version < 16:
        fail("FDT_INVALID", f"version={version}")
    memreserve = []
    i = off_rsv
    while i + 16 <= len(blob):
        addr, size = struct.unpack_from(">QQ", blob, i)
        i += 16
        if addr == 0 and size == 0:
            break
        memreserve.append({"base": addr, "size": size})
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
            if path or name:
                path.append(name)
            nodes["/" + "/".join(path)] = {}
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
            nodes.setdefault("/" + "/".join(path), {})[pname] = pval
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            fail("FDT_INVALID", f"token={token}")
    return {
        "totalsize": totalsize, "version": version,
        "memreserve": memreserve, "nodes": nodes, "size": len(blob),
    }


def prop_text(props: dict, name: str) -> str:
    raw = props.get(name)
    if raw is None:
        return ""
    return raw.split(b"\x00")[0].decode("ascii", "replace")


def sensitive_name(name: str) -> bool:
    if name in DENYLIST_EXACT:
        return True
    return any(s in name for s in DENYLIST_SUBSTR) or name.endswith("-mac")


def sanitize_bootargs(raw: bytes) -> tuple[str, int]:
    text = raw.split(b"\x00")[0].decode("ascii", "replace")
    out = []
    for tok in text.split():
        if "=" in tok:
            key, _ = tok.split("=", 1)
            out.append(tok if key in BOOTARGS_ALLOW else f"{key}=<redacted>")
        else:
            out.append(tok)
    return " ".join(out), len(out)


def decode_banks(nodes: dict, addr_cells: int, size_cells: int) -> tuple[list, int, int]:
    banks = []
    raw_size = 0
    cell_count = 0
    for npath in sorted(nodes):
        props = nodes[npath]
        if not props.get("device_type", b"").startswith(b"memory"):
            continue
        raw = props.get("reg")
        if raw is None:
            continue
        raw_size += len(raw)
        vals = cells_u32(raw)
        cell_count += len(vals)
        stride = addr_cells + size_cells
        if stride <= 0 or len(vals) % stride:
            fail("MEMORY_REG_INVALID", f"{npath} cells={len(vals)} stride={stride}")
        for k in range(0, len(vals), stride):
            base = fold(vals[k:k + addr_cells])
            size = fold(vals[k + addr_cells:k + stride])
            banks.append({"node": npath, "base": base, "size": size,
                          "end": base + size - 1})
    return banks, raw_size, cell_count


def collect_reserved(nodes: dict, addr_cells: int, size_cells: int) -> list:
    out = []
    for npath in sorted(nodes):
        parts = [p for p in npath.split("/") if p]
        if len(parts) != 2 or parts[0] != "reserved-memory":
            continue
        props = nodes[npath]
        raw = props.get("reg")
        if raw is None:
            out.append({"node": npath, "base": None})
            continue
        vals = cells_u32(raw)
        stride = addr_cells + size_cells
        if len(vals) % stride or stride <= 0:
            fail("RESERVED_REG_INVALID", npath)
        for k in range(0, len(vals), stride):
            base = fold(vals[k:k + addr_cells])
            size = fold(vals[k + addr_cells:k + stride])
            out.append({
                "node": npath, "base": base, "size": size,
                "end": base + size - 1 if size else base,
                "no_map": "no-map" in props, "reusable": "reusable" in props,
                "compatible": prop_text(props, "compatible"),
            })
    return out


def collect_sensitive(nodes: dict) -> list:
    present = set()
    for _npath, props in nodes.items():
        for pname in props:
            if sensitive_name(pname):
                present.add(pname)
    return sorted(present)


def evidence_from_fdt(fdt: dict) -> dict:
    nodes = fdt["nodes"]
    root = nodes.get("/", {})
    raw_ac = root.get("#address-cells")
    raw_sc = root.get("#size-cells")
    addr_cells = fold(cells_u32(raw_ac)) if raw_ac else 2
    size_cells = fold(cells_u32(raw_sc)) if raw_sc else 2
    if (addr_cells, size_cells) != (2, 2):
        fail("ROOT_CELLS_UNEXPECTED", f"{addr_cells}/{size_cells}")
    banks, raw_size, cell_count = decode_banks(nodes, addr_cells, size_cells)
    reserved = collect_reserved(nodes, addr_cells, size_cells)
    chosen_raw = nodes.get("/chosen", {})
    bootargs, ntok = sanitize_bootargs(chosen_raw.get("bootargs", b""))
    return {
        "root": {
            "address_cells": addr_cells, "size_cells": size_cells,
            "model": prop_text(root, "model"),
            "compatible": [c.decode() for c in
                           root.get("compatible", b"").split(b"\x00") if c],
            "msm_id": fold(cells_u32(root["qcom,msm-id"]))
            if "qcom,msm-id" in root else None,
            "board_id": fold(cells_u32(root["qcom,board-id"]))
            if "qcom,board-id" in root else None,
        },
        "memory": {
            "reg_raw_size": raw_size, "cell_count": cell_count,
            "bank_count": len(banks), "banks": banks,
            "total": sum(b["size"] for b in banks),
        },
        "memreserve": fdt["memreserve"],
        "reserved": reserved,
        "chosen": {
            "bootargs_sanitized": bootargs, "bootargs_tokens": ntok,
            "stdout_path": prop_text(chosen_raw, "stdout-path"),
            "usable_memory_range": fold(cells_u32(
                chosen_raw["linux,usable-memory-range"]))
            if "linux,usable-memory-range" in chosen_raw else None,
            "initrd_present": "linux,initrd-start" in chosen_raw,
            "sensitive_props_present": collect_sensitive(nodes),
        },
    }


def parse_iomem(text: str) -> dict:
    redacted = False
    system_ram = []
    kernel = {}
    reserved_children = 0
    cma = []
    last_ram_depth = None
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^([0-9a-f]+)-([0-9a-f]+) : (.+)$", stripped)
        if not m:
            continue
        start = int(m.group(1), 16)
        end = int(m.group(2), 16)
        label = m.group(3).strip()
        if start == 0 and end == 0:
            redacted = True
        raw_indent = line[: len(line) - len(line.lstrip())]
        depth = raw_indent.count("\t") or (1 if raw_indent.strip() else 0)
        if label == "System RAM":
            system_ram.append({"base": start, "end": end})
            last_ram_depth = depth
            continue
        if last_ram_depth is None or depth <= last_ram_depth:
            last_ram_depth = None if depth == 0 else last_ram_depth
            continue
        if label.startswith("Kernel "):
            kernel[label] = {"base": start, "end": end}
        if label == "reserved":
            reserved_children += 1
        if "cma" in label.lower():
            cma.append({"base": start, "end": end, "label": label})
    return {
        "redacted": redacted, "system_ram": system_ram, "kernel": kernel,
        "reserved_children": reserved_children, "cma": cma,
    }


def parse_meminfo(text: str) -> dict:
    want = ("MemTotal", "MemFree", "MemAvailable", "CmaTotal", "CmaFree")
    out = {}
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) == 2 and parts[0].strip() in want:
            out[parts[0].strip()] = int(re.sub(r"[^0-9]", "", parts[1]) or 0)
    missing = [w for w in ("MemTotal", "MemFree", "MemAvailable") if w not in out]
    if missing:
        fail("MEMINFO_INCOMPLETE", ",".join(missing))
    return out


def parse_memory_sysfs(block_size_text: str, phys_index_text: str) -> dict:
    m = re.search(r"0x([0-9a-f]+)", block_size_text)
    block_size = int(m.group(1), 16) if m else 0
    blocks = sorted(int(v, 16) for v in
                    re.findall(r"^\s*([0-9a-f]+)\s*$", phys_index_text, re.M))
    return {"block_size": block_size, "blocks": blocks,
            "usable": bool(block_size)}


def tar_probe(tar_path: Path, banks: list) -> dict:
    try:
        with tarfile.open(tar_path) as tf:
            names = [n.lstrip("./") for n in tf.getnames()]
            memory_reg = None
            for n in names:
                if n == "memory/reg" or re.match(r"^memory[^/]*/reg$", n):
                    memory_reg = tf.extractfile("./" + n).read()
                    break
            children = set()
            for n in names:
                if n.startswith("reserved-memory/"):
                    rest = n[len("reserved-memory/"):]
                    if rest:
                        children.add(rest.split("/")[0])
    except (tarfile.TarError, OSError) as exc:
        fail("TAR_PARSE_FAILED", str(exc))
    match = None
    if memory_reg is not None and banks:
        want = b"".join(struct.pack(">QQ", b["base"], b["size"]) for b in banks)
        match = memory_reg == want
    return {
        "memory_reg_present": memory_reg is not None,
        "memory_reg_matches_fdt": match,
        "reserved_children": len(children),
    }


def compare_stock(stock: dict, runtime: dict) -> dict:
    def bank_set(rep: dict) -> list:
        return [[b["base"], b["size"]] for b in rep["memory"]["banks"]]

    def res_map(rep: dict) -> dict:
        return {r["node"].rsplit("/", 1)[-1]: [r.get("base"), r.get("size")]
                for r in rep["reserved"] if r.get("base") is not None}

    s_res, r_res = res_map(stock), res_map(runtime)
    return {
        "memory_banks_stock": bank_set(stock),
        "memory_banks_runtime": bank_set(runtime),
        "memory_mutated": bank_set(stock) != bank_set(runtime),
        "reserved_added": sorted(set(r_res) - set(s_res)),
        "reserved_removed": sorted(set(s_res) - set(r_res)),
        "reserved_changed": sorted(
            n for n in set(s_res) & set(r_res) if s_res[n] != r_res[n]),
        "chosen_bootargs_mutated":
            stock["chosen"]["bootargs_sanitized"]
            != runtime["chosen"]["bootargs_sanitized"],
    }


def build_matrix(rep: dict, iomem: dict, meminfo: dict) -> dict:
    banks = rep["memory"]["banks"]
    ram = iomem["system_ram"]
    per_bank = []
    for b in banks:
        inside = [r for r in ram if r["base"] >= b["base"] and r["end"] <= b["end"]]
        overlap = [r for r in ram if r["base"] <= b["end"] and r["end"] >= b["base"]]
        if inside and len(overlap) == len(inside):
            status = "CONFIRMED"
        elif overlap:
            status = "SUPPORTED"
        else:
            status = "UNKNOWN"
        per_bank.append({"base": b["base"], "size": b["size"], "status": status})
    orphans = [r for r in ram if not any(
        b["base"] <= r["base"] and r["end"] <= b["end"] for b in banks)]
    total = rep["memory"]["total"]
    memtotal = meminfo.get("MemTotal", 0)
    sanity = None
    if total and memtotal:
        headroom_pct = (total - memtotal) * 100.0 / total
        sanity = {
            "total_banks_kb": total // 1024, "memtotal_kb": memtotal,
            "headroom_pct": round(headroom_pct, 2),
            "pass": total > memtotal and headroom_pct < 40.0,
        }
    kernel_code = iomem["kernel"].get("Kernel code")
    align = None
    if kernel_code:
        s = kernel_code["base"]
        align = {
            "stock_kernel_code_base": s, "mod_2m": s % 0x200000,
            "role": "LOAD_ALIGNMENT_SUPPORTING_EVIDENCE_ONLY",
        }
    return {
        "banks": per_bank,
        "iomem_orphans_outside_banks": orphans,
        "iomem_status": "CONFLICT" if orphans and not iomem["redacted"] else "OK",
        "meminfo_sanity": sanity, "stock_kernel_alignment": align,
    }


def gate(rep: dict, matrix: dict, tar_check: dict | None) -> None:
    mem = rep["memory"]
    if mem["bank_count"] <= 0 or mem["total"] <= 0:
        fail("RAM_MAP_EMPTY", "runtime FDT describes no usable RAM")
    for b in mem["banks"]:
        if b["size"] <= 0:
            fail("RAM_MAP_EMPTY", f"zero-size bank base={b['base']:#x}")
        if b["base"] + b["size"] <= b["base"]:
            fail("RAM_MAP_OVERFLOW", f"base={b['base']:#x} size={b['size']:#x}")
    if matrix.get("iomem_status") == "CONFLICT":
        fail("R3_RUNTIME_DTB_EVIDENCE_CONFLICT",
             "iomem System RAM outside FDT-described banks")
    sanity = matrix.get("meminfo_sanity")
    if sanity and not sanity["pass"]:
        fail("MEMINFO_SANITY_FAIL", json.dumps(sanity))
    if tar_check and tar_check.get("memory_reg_matches_fdt") is False:
        fail("FDT_VS_LIVETREE_MISMATCH", "memory/reg differs from OF tree")
    outside = [r for r in rep["reserved"] if r.get("base") is not None
               and not any(b["base"] <= r["base"] and r["end"] <= b["end"]
                           for b in mem["banks"])]
    if outside:
        fail("RESERVED_OUTSIDE_RAM_BANKS", ",".join(r["node"] for r in outside))
    print("R3_RUNTIME_EVIDENCE_GATES=PASS")


def mode_parse(args: argparse.Namespace) -> None:
    fdt_bytes = Path(args.fdt).read_bytes()
    fdt = parse_fdt(fdt_bytes)
    rep = evidence_from_fdt(fdt)
    iomem_text = Path(args.iomem).read_text(errors="replace") if args.iomem else ""
    iomem = parse_iomem(iomem_text) if iomem_text else {"redacted": None}
    meminfo = parse_meminfo(Path(args.meminfo).read_text(errors="replace")) \
        if args.meminfo else {}
    sysfs = parse_memory_sysfs(
        Path(args.mem_block_size).read_text(errors="replace"),
        Path(args.mem_phys_index).read_text(errors="replace")) \
        if args.mem_block_size and args.mem_phys_index else {"usable": False}
    dmesg_lines = 0
    if args.dmesg:
        dmesg_lines = len(Path(args.dmesg).read_text(
            errors="replace").splitlines())
    tar_check = tar_probe(Path(args.devicetree_tar), rep["memory"]["banks"]) \
        if args.devicetree_tar else None
    stock_summary = None
    if args.stock_dtb:
        stock = evidence_from_fdt(parse_fdt(Path(args.stock_dtb).read_bytes()))
        stock_summary = compare_stock(stock, rep)
    matrix = build_matrix(rep, iomem, meminfo) if iomem_text else {}
    gate(rep, matrix, tar_check)
    out = {
        "capture": {
            "bundle_sha256": args.capture_sha or "",
            "fdt_sha256": sha(fdt_bytes), "fdt_size": len(fdt_bytes),
            "fdt_totalsize": fdt["totalsize"], "fdt_version": fdt["version"],
            "runtime_fdt_available": True,
        },
        **rep,
        "iomem": iomem, "meminfo": meminfo, "memory_sysfs": sysfs,
        "dmesg": {"filtered_lines": dmesg_lines,
                  "ring_wrapped": args.dmesg is not None and dmesg_lines == 0},
        "fdt_vs_livetree": tar_check,
        "stock_dtb0_comparison": stock_summary,
        "matrix": matrix,
    }
    Path(args.out_json).write_text(json.dumps(out, indent=2) + "\n")
    report = [
        "THYME_RUNTIME_MEMORY_EVIDENCE",
        f"fdt sha256={out['capture']['fdt_sha256']}"
        f" size={out['capture']['fdt_size']}",
        f"root cells={out['root']['address_cells']}/{out['root']['size_cells']}"
        f" model={out['root']['model']!r}"
        f" msm_id={hex(out['root']['msm_id']) if out['root']['msm_id'] is not None else None}"
        f" board_id={hex(out['root']['board_id']) if out['root']['board_id'] is not None else None}",
        f"MEMORY_REG_RAW_SIZE={out['memory']['reg_raw_size']}"
        f" CELL_COUNT={out['memory']['cell_count']}"
        f" BANK_COUNT={out['memory']['bank_count']}",
    ]
    for b in out["memory"]["banks"]:
        report.append(f"  bank node={b['node']} base={b['base']:#x}"
                      f" size={b['size']:#x} end={b['end']:#x}")
    report.append(f"total described={out['memory']['total']:#x}"
                  f" ({out['memory']['total'] / (1 << 30):.3f} GiB)")
    report.append(f"FDT_MEMRESERVE_ENTRIES={len(out['memreserve'])}")
    for e in out["memreserve"]:
        report.append(f"  memreserve base={e['base']:#x} size={e['size']:#x}")
    report.append(f"RUNTIME_RESERVED_MEMORY_MAP ({len(out['reserved'])} nodes)")
    for r in out["reserved"]:
        if r.get("base") is None:
            report.append(f"  {r['node']} reg=absent")
            continue
        flags = ("no-map" if r["no_map"] else "") + \
                (" reusable" if r["reusable"] else "")
        report.append(f"  {r['node']} base={r['base']:#x} size={r['size']:#x}"
                      f" end={r['end']:#x} {flags} compatible={r['compatible']!r}")
    report.append(f"chosen bootargs(sanitized)={out['chosen']['bootargs_sanitized']!r}")
    report.append("sensitive props present (values withheld): "
                  + json.dumps(out["chosen"]["sensitive_props_present"]))
    if iomem_text:
        report.append(f"PROC_IOMEM_REDACTED={iomem['redacted']}")
        for r in iomem["system_ram"]:
            report.append(f"  iomem System RAM {r['base']:#x}-{r['end']:#x}")
        report.append(f"  iomem kernel={iomem['kernel']}")
        report.append(f"  iomem reserved_children={iomem['reserved_children']}"
                      f" cma={iomem['cma']}")
    if meminfo:
        report.append(f"meminfo={meminfo}")
    report.append(f"memory_sysfs={sysfs}")
    report.append(f"dmesg={out['dmesg']}")
    if tar_check:
        report.append(f"fdt_vs_livetree={tar_check}")
    if stock_summary:
        report.append(f"stock_dtb0_comparison={json.dumps(stock_summary)}")
    if matrix:
        report.append(f"matrix={json.dumps(matrix, indent=1)}")
    Path(args.out_report).write_text("\n".join(report) + "\n")
    print("\n".join(report))


def build_fixture_fdt() -> bytes:
    struct_block = b""
    strings = b"\x00"
    names = [""]

    def add_str(s: str) -> int:
        nonlocal strings
        if s in names:
            return names.index(s)
        off = len(strings) - 1 if len(strings) > 1 else 0
        strings += s.encode() + b"\x00"
        names.append(s)
        return off

    def prop(name: str, value: bytes) -> None:
        nonlocal struct_block
        struct_block += struct.pack(">III", FDT_PROP, len(value), add_str(name))
        struct_block += value + b"\x00" * ((4 - len(value) % 4) % 4)

    def begin(name: str) -> None:
        nonlocal struct_block
        struct_block += struct.pack(">I", FDT_BEGIN_NODE)
        struct_block += name.encode() + b"\x00"

    def end() -> None:
        nonlocal struct_block
        struct_block += struct.pack(">I", FDT_END_NODE)

    begin("")
    prop("#address-cells", struct.pack(">I", 2))
    prop("#size-cells", struct.pack(">I", 2))
    prop("model", b"fixture")
    prop("compatible", b"fixture,dev\x00")
    prop("kaslr-seed", b"\x11" * 8)
    begin("memory")
    prop("device_type", b"memory")
    prop("reg", struct.pack(">QQQQ", 0x80000000, 0x10000000,
                            0x90000000, 0x08000000))
    end()
    begin("reserved-memory")
    begin("carveout@88000000")
    prop("reg", struct.pack(">QQ", 0x88000000, 0x1000000))
    prop("no-map", b"")
    end()
    end()
    begin("chosen")
    prop("bootargs",
         b"console=ttyMSM0,115200n8 androidboot.serialno=SECRET loglevel=7")
    end()
    end()
    struct_block += struct.pack(">I", FDT_END)
    while len(strings) % 4:
        strings += b"\x00"
    off_struct = 40
    off_strings = off_struct + len(struct_block)
    off_rsv = off_strings + len(strings)
    rsv = struct.pack(">QQ", 0xB0000000, 0x100000) + struct.pack(">QQ", 0, 0)
    totalsize = off_rsv + len(rsv)
    header = struct.pack(">10I", FDT_MAGIC, totalsize, off_struct,
                         off_strings, off_rsv, 17, 0, 0,
                         len(strings), len(struct_block))
    blob = bytearray(header + struct_block + strings + rsv)
    return bytes(blob)


def mode_fixture_selfcheck() -> None:
    fdt = parse_fdt(build_fixture_fdt())
    rep = evidence_from_fdt(fdt)
    assert rep["memory"]["bank_count"] == 2, rep["memory"]
    assert rep["memory"]["banks"][0]["base"] == 0x80000000
    assert rep["memory"]["banks"][0]["size"] == 0x10000000
    assert rep["memory"]["banks"][1]["size"] == 0x08000000
    assert rep["memory"]["total"] == 0x18000000
    assert rep["memory"]["cell_count"] == 8 and rep["memory"]["reg_raw_size"] == 32
    assert rep["memreserve"] == [{"base": 0xB0000000, "size": 0x100000}]
    assert len(rep["reserved"]) == 1 and rep["reserved"][0]["no_map"] is True
    assert "SECRET" not in rep["chosen"]["bootargs_sanitized"]
    assert "androidboot.serialno=<redacted>" in rep["chosen"]["bootargs_sanitized"]
    assert "kaslr-seed" in rep["chosen"]["sensitive_props_present"]
    assert rep["root"]["address_cells"] == 2 and rep["root"]["size_cells"] == 2
    iomem = parse_iomem(
        "00000000-ffffffff : PCI Bus 0000:00\n"
        "80000000-8fffffff : System RAM\n"
        "\t80080000-802fffff : Kernel code\n"
        "\t88000000-88ffffff : reserved\n"
        "\t89000000-89ffffff : CMA\n"
        "90000000-97ffffff : System RAM\n")
    assert len(iomem["system_ram"]) == 2
    assert iomem["system_ram"][0] == {"base": 0x80000000, "end": 0x8fffffff}
    assert iomem["kernel"]["Kernel code"]["base"] == 0x80080000
    assert iomem["reserved_children"] == 1 and len(iomem["cma"]) == 1
    matrix = build_matrix(rep, iomem, {"MemTotal": 0x18000000 // 1024 - 1000})
    assert matrix["banks"][0]["status"] == "CONFIRMED"
    assert matrix["banks"][1]["status"] == "CONFIRMED"
    assert matrix["iomem_status"] == "OK"
    assert matrix["meminfo_sanity"]["pass"] is True
    assert matrix["stock_kernel_alignment"]["mod_2m"] == 0x80000
    try:
        gate(rep, build_matrix(
            rep, iomem, {"MemTotal": 0x18000000 // 1024 + 1}), None)
    except SystemExit:
        pass
    else:
        fail("FIXTURE_SELFCHECK_FAILED", "meminfo sanity did not fail")
    print("R3_RUNTIME_EVIDENCE_FIXTURE_SELFCHECK=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("parse", "fixture-selfcheck"), required=True)
    p.add_argument("--fdt")
    p.add_argument("--devicetree-tar")
    p.add_argument("--iomem")
    p.add_argument("--meminfo")
    p.add_argument("--mem-block-size")
    p.add_argument("--mem-phys-index")
    p.add_argument("--dmesg")
    p.add_argument("--stock-dtb")
    p.add_argument("--capture-sha")
    p.add_argument("--out-json")
    p.add_argument("--out-report")
    args = p.parse_args()
    if args.mode == "fixture-selfcheck":
        mode_fixture_selfcheck()
        return
    for req in ("fdt", "out_json", "out_report"):
        if not getattr(args, req):
            fail("ARGS_MISSING", req)
    mode_parse(args)


if __name__ == "__main__":
    main()
