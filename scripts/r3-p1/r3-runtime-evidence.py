#!/usr/bin/env python3
"""R3 RUNTIME_DTB_COMPLETION_CI evidence parser. GitHub Actions only.

Primary evidence source is the Stock Android A runtime OF tree dump
(captured from /sys/firmware/devicetree/base — the tree the Stock kernel
actually unflattened and serves — as a per-file `===FILE <path>` + base64
stream, because toybox tar silently truncates archives on sysfs). The
captured /sys/firmware/fdt binary is
used for the FDT header and the memreserve table, plus a lenient structure
walk for cross-checking: the thyme ABL blob is misaligned inside /aliases
(a one-byte shift around struct offset 0x370 and size_dt_struct overlapping
the strings block), so a strict walk cannot be trusted and truncation is
detected and reported instead.

/proc/iomem, /proc/meminfo, the memory sysfs fallback, filtered dmesg and the
raw Stock DTB0 provide the remaining cross-sources. Sensitive properties
(seeds/serials/MACs) are never emitted: presence only. bootargs are
token-sanitized. The OEM binaries never leave the private repository; only
this numeric summary may be mirrored to the public repo.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import struct
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
    "androidboot.slot_suffix",
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


def parse_fdt_header(blob: bytes) -> dict:
    if len(blob) < 40:
        fail("FDT_INVALID", "short header")
    (magic, totalsize, off_struct, off_strings, off_rsv,
     version, _lc, _cpu, size_strings, size_struct) = struct.unpack(
        ">10I", blob[:40])
    if magic != FDT_MAGIC:
        fail("FDT_INVALID", f"magic=0x{magic:08x}")
    if totalsize > len(blob) or totalsize < 40:
        fail("FDT_INVALID", f"totalsize={totalsize} file={len(blob)}")
    if version < 16:
        fail("FDT_INVALID", f"version={version}")
    if not (0 < off_rsv < totalsize and 0 < off_struct <= totalsize
            and 0 < off_strings <= totalsize and off_rsv < off_struct):
        fail("FDT_INVALID", "header offsets out of range")
    memreserve = []
    i = off_rsv
    while i + 16 <= off_struct:
        addr, size = struct.unpack_from(">QQ", blob, i)
        i += 16
        if addr == 0 and size == 0:
            return {"magic": magic, "totalsize": totalsize,
                    "off_struct": off_struct, "off_strings": off_strings,
                    "off_rsv": off_rsv, "version": version,
                    "size_strings": size_strings, "size_struct": size_struct,
                    "memreserve": memreserve, "memreserve_terminated": True}
        memreserve.append({"base": addr, "size": size})
    return {"magic": magic, "totalsize": totalsize, "off_struct": off_struct,
            "off_strings": off_strings, "off_rsv": off_rsv,
            "version": version, "size_strings": size_strings,
            "size_struct": size_struct, "memreserve": memreserve,
            "memreserve_terminated": False}


def walk_fdt_struct(blob: bytes, header: dict) -> dict:
    """Lenient structure walk for cross-checking only.

    Stops at the first invalid token (the thyme runtime blob misaligns
    inside /aliases). The caller must treat a walk that never reached
    FDT_END as truncated and must not trust its node set.
    """
    structb = blob[header["off_struct"]:header["totalsize"]]
    strings = blob[header["off_strings"]:header["totalsize"]]
    nodes: dict[str, dict[str, bytes]] = {}
    path: list[str] = []
    i = 0
    truncated_at = None
    while i + 4 <= len(structb):
        token = struct.unpack_from(">I", structb, i)[0]
        i += 4
        if token == FDT_BEGIN_NODE:
            end = structb.find(b"\x00", i)
            if end < 0:
                truncated_at = i
                break
            name = structb[i:end].decode("ascii", "replace")
            i = (end + 4) & ~3
            if path or name:
                path.append(name)
            nodes["/" + "/".join(path)] = {}
        elif token == FDT_END_NODE:
            if path:
                path.pop()
        elif token == FDT_PROP:
            if i + 8 > len(structb):
                truncated_at = i
                break
            plen, nameoff = struct.unpack_from(">II", structb, i)
            i += 8
            nend = strings.find(b"\x00", nameoff)
            if nend < 0 or i + plen > len(structb):
                truncated_at = i
                break
            pname = strings[nameoff:nend].decode("ascii", "replace")
            nodes.setdefault("/" + "/".join(path), {})[pname] = \
                structb[i:i + plen]
            i = (i + plen + 3) & ~3
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            return {"nodes": nodes, "complete": True, "truncated_at": None}
        else:
            truncated_at = i - 4
            break
    return {"nodes": nodes, "complete": False, "truncated_at": truncated_at}


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


def evidence_from_nodes(nodes: dict) -> dict:
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


def parse_livetree_dump(data: bytes) -> tuple[dict, dict]:
    """Parse the per-file `===FILE <path>` + base64 dump of the runtime OF tree.

    Every entry carries an explicit marker so a single unreadable sysfs file
    degrades to an empty property instead of aborting the whole capture the
    way toybox tar silently did.
    """
    prefix = "/sys/firmware/devicetree/base/"
    pending: dict[str, dict[str, list[str]]] = {}
    cur: list[str] | None = None
    file_markers = 0
    for line in data.decode("ascii", "strict").splitlines():
        if line.startswith("===FILE "):
            rel = line[len("===FILE "):].strip()
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
            *node_parts, prop = rel.split("/")
            npath = "/" + "/".join(node_parts)
            cur = pending.setdefault(npath, {}).setdefault(prop, [])
            file_markers += 1
        elif cur is not None and line:
            cur.append(line.strip())
    nodes = {npath: {p: base64.b64decode("".join(v))
                     for p, v in props.items()}
             for npath, props in pending.items()}
    if "/" not in nodes and "" in nodes:
        nodes["/"] = nodes.pop("")
    if not nodes.get("/memory", {}).get("reg"):
        fail("EVIDENCE_PARSE_FAILED", "runtime dump lacks /memory/reg")
    return nodes, {"file_markers": file_markers}


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


def fdt_walk_crosscheck(fdt_bytes: bytes, header: dict, tree_nodes: dict) -> dict:
    walk = walk_fdt_struct(fdt_bytes, header)
    tree_reg = tree_nodes.get("/memory", {}).get("reg")
    walk_reg = walk["nodes"].get("/memory", {}).get("reg")
    banks_match = (walk_reg is not None and tree_reg is not None
                   and walk_reg == tree_reg)
    walk_reserved = len([
        p for p in walk["nodes"]
        if len([x for x in p.split("/") if x]) == 2
        and p.split("/")[1] == "reserved-memory"]) if walk["complete"] else None
    tree_reserved = len([
        p for p in tree_nodes
        if len([x for x in p.split("/") if x]) == 2
        and p.split("/")[1] == "reserved-memory"])
    return {
        "struct_walk_complete": walk["complete"],
        "struct_walk_truncated_at": walk["truncated_at"],
        "walked_memory_reg_matches_livetree": banks_match,
        "walked_reserved_children": walk_reserved,
        "livetree_reserved_children": tree_reserved,
        "verdict": "LIVETREE_PRIMARY"
        if not walk["complete"] else
        ("MATCH" if banks_match else "MISMATCH"),
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
    overlapping_banks = []
    for i in range(len(banks)):
        for j in range(i + 1, len(banks)):
            a, c = banks[i], banks[j]
            if a["base"] <= c["end"] and c["base"] <= a["end"]:
                overlapping_banks.append([a["base"], c["base"]])
    # The kernel merges contiguous multi-bank RAM into one iomem resource,
    # so orphan detection must use union coverage, not per-bank containment.
    def covered(r: dict) -> int:
        total = 0
        for b in banks:
            lo = max(r["base"], b["base"])
            hi = min(r["end"], b["end"])
            if hi >= lo:
                total += hi - lo + 1
        return total
    orphans = [r for r in ram
               if covered(r) != r["end"] - r["base"] + 1]
    total = rep["memory"]["total"] // 1024
    memtotal = meminfo.get("MemTotal", 0)
    sanity = None
    if total and memtotal:
        headroom_pct = (total - memtotal) * 100.0 / total
        sanity = {
            "total_banks_kb": total, "memtotal_kb": memtotal,
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
        "overlapping_banks": overlapping_banks,
        "iomem_orphans_outside_banks": orphans,
        "iomem_status": "CONFLICT" if orphans and not iomem["redacted"] else "OK",
        "meminfo_sanity": sanity, "stock_kernel_alignment": align,
    }


def gate(rep: dict, matrix: dict, crosscheck: dict | None) -> None:
    mem = rep["memory"]
    if mem["bank_count"] <= 0 or mem["total"] <= 0:
        fail("RAM_MAP_EMPTY", "runtime OF tree describes no usable RAM")
    for b in mem["banks"]:
        if b["size"] <= 0:
            fail("RAM_MAP_EMPTY", f"zero-size bank base={b['base']:#x}")
        if b["base"] + b["size"] <= b["base"]:
            fail("RAM_MAP_OVERFLOW", f"base={b['base']:#x} size={b['size']:#x}")
    if matrix.get("overlapping_banks"):
        fail("R3_RUNTIME_DTB_EVIDENCE_CONFLICT",
             f"memory banks overlap: {matrix['overlapping_banks']}")
    if matrix.get("iomem_status") == "CONFLICT":
        fail("R3_RUNTIME_DTB_EVIDENCE_CONFLICT",
             "iomem System RAM outside FDT-described banks")
    sanity = matrix.get("meminfo_sanity")
    if sanity and not sanity["pass"]:
        fail("MEMINFO_SANITY_FAIL", json.dumps(sanity))
    if crosscheck and crosscheck["verdict"] == "MISMATCH":
        fail("FDT_VS_LIVETREE_MISMATCH", "memory/reg disagrees")
    outside = [r for r in rep["reserved"] if r.get("base") is not None
               and not any(b["base"] <= r["base"] and r["end"] <= b["end"]
                           for b in mem["banks"])]
    if outside:
        fail("RESERVED_OUTSIDE_RAM_BANKS", ",".join(r["node"] for r in outside))
    print("R3_RUNTIME_EVIDENCE_GATES=PASS")


def mode_parse(args: argparse.Namespace) -> None:
    if not args.devicetree_dump:
        fail("ARGS_MISSING", "devicetree-dump (primary evidence source)")
    dump_path = Path(args.devicetree_dump)
    dump_bytes = dump_path.read_bytes()
    tree_nodes, dump_meta = parse_livetree_dump(dump_bytes)
    rep = evidence_from_nodes(tree_nodes)
    fdt_bytes = Path(args.fdt).read_bytes() if args.fdt else b""
    header = parse_fdt_header(fdt_bytes) if fdt_bytes else None
    crosscheck = None
    if header:
        crosscheck = fdt_walk_crosscheck(fdt_bytes, header, tree_nodes)
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
    stock_summary = None
    if args.stock_dtb:
        stock_blob = Path(args.stock_dtb).read_bytes()
        stock_header = parse_fdt_header(stock_blob)
        stock_walk = walk_fdt_struct(stock_blob, stock_header)
        if not stock_walk["complete"]:
            fail("STOCK_DTB0_WALK_TRUNCATED",
                 f"at {stock_walk['truncated_at']:#x}")
        stock = evidence_from_nodes(stock_walk["nodes"])
        stock["memreserve"] = stock_header["memreserve"]
        stock_summary = compare_stock(stock, rep)
    matrix = build_matrix(rep, iomem, meminfo) if iomem_text else {}
    gate(rep, matrix, crosscheck)
    out = {
        "capture": {
            "bundle_sha256": args.capture_sha or "",
            "fdt_sha256": sha(fdt_bytes) if fdt_bytes else "",
            "fdt_size": len(fdt_bytes),
            "runtime_fdt_available": bool(fdt_bytes),
            "devicetree_dump_sha256": sha(dump_bytes),
            "devicetree_dump_file_markers": dump_meta["file_markers"],
            "evidence_primary_source": "RUNTIME_OF_TREE_DUMP",
        },
        "fdt_header": header,
        "fdt_struct_walk_crosscheck": crosscheck,
        **rep,
        "iomem": iomem, "meminfo": meminfo, "memory_sysfs": sysfs,
        "dmesg": {"filtered_lines": dmesg_lines,
                  "ring_wrapped": args.dmesg is not None and dmesg_lines == 0},
        "stock_dtb0_comparison": stock_summary,
        "matrix": matrix,
    }
    Path(args.out_json).write_text(json.dumps(out, indent=2, default=str) + "\n")
    report = [
        "THYME_RUNTIME_MEMORY_EVIDENCE",
        "primary source=RUNTIME_OF_TREE_DUMP (/sys/firmware/devicetree/base)",
        f"devicetree_dump sha256={out['capture']['devicetree_dump_sha256']}"
        f" file_markers={out['capture']['devicetree_dump_file_markers']}",
    ]
    if header:
        report.append(
            f"fdt sha256={out['capture']['fdt_sha256']}"
            f" size={out['capture']['fdt_size']}"
            f" totalsize={header['totalsize']:#x} version={header['version']}")
        report.append(f"FDT_MEMRESERVE_ENTRIES={len(header['memreserve'])}"
                      f" terminated={header['memreserve_terminated']}")
        for e in header["memreserve"]:
            report.append(f"  memreserve base={e['base']:#x} size={e['size']:#x}")
    if crosscheck:
        report.append(f"fdt_struct_walk={json.dumps(crosscheck)}")
    report.append(
        f"root cells={rep['root']['address_cells']}/{rep['root']['size_cells']}"
        f" model={rep['root']['model']!r}"
        f" msm_id={hex(rep['root']['msm_id']) if rep['root']['msm_id'] is not None else None}"
        f" board_id={hex(rep['root']['board_id']) if rep['root']['board_id'] is not None else None}")
    report.append(f"MEMORY_REG_RAW_SIZE={rep['memory']['reg_raw_size']}"
                  f" CELL_COUNT={rep['memory']['cell_count']}"
                  f" BANK_COUNT={rep['memory']['bank_count']}")
    for b in rep["memory"]["banks"]:
        report.append(f"  bank node={b['node']} base={b['base']:#x}"
                      f" size={b['size']:#x} end={b['end']:#x}")
    report.append(f"total described={rep['memory']['total']:#x}"
                  f" ({rep['memory']['total'] / (1 << 30):.3f} GiB)")
    report.append(f"RUNTIME_RESERVED_MEMORY_MAP ({len(rep['reserved'])} nodes)")
    for r in rep["reserved"]:
        if r.get("base") is None:
            report.append(f"  {r['node']} reg=absent")
            continue
        flags = ("no-map" if r["no_map"] else "") + \
                (" reusable" if r["reusable"] else "")
        report.append(f"  {r['node']} base={r['base']:#x} size={r['size']:#x}"
                      f" end={r['end']:#x} {flags} compatible={r['compatible']!r}")
    report.append(f"chosen bootargs(sanitized)={rep['chosen']['bootargs_sanitized']!r}")
    report.append("sensitive props present (values withheld): "
                  + json.dumps(rep["chosen"]["sensitive_props_present"]))
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
    if stock_summary:
        report.append(f"stock_dtb0_comparison={json.dumps(stock_summary)}")
    if matrix:
        report.append(f"matrix={json.dumps(matrix, indent=1)}")
    Path(args.out_report).write_text("\n".join(report) + "\n")
    print("\n".join(report))


def build_fixture_tree() -> dict:
    return {
        "/": {
            "#address-cells": struct.pack(">I", 2),
            "#size-cells": struct.pack(">I", 2),
            "model": b"fixture\x00",
            "compatible": b"fixture,dev\x00",
            "kaslr-seed": b"\x11" * 8,
        },
        "/memory": {
            "device_type": b"memory",
            "reg": struct.pack(
                ">QQQQQQ",
                0x80000000, 0x39900000,
                0xC0000000, 0x140000000,
                0x200000000, 0x180000000),
        },
        "/reserved-memory": {},
        "/reserved-memory/carveout@88000000": {
            "reg": struct.pack(">QQ", 0x88000000, 0x1000000),
            "no-map": b"",
        },
        "/reserved-memory/dynamic_region": {
            "compatible": b"qcom,dynamic-pil\x00",
        },
        "/chosen": {
            "bootargs": b"console=ttyMSM0,115200n8 "
                         b"androidboot.serialno=SECRET "
                         b"androidboot.slot_suffix=_a loglevel=7",
        },
    }


def write_fixture_dump(nodes: dict, path: Path) -> None:
    lines = []
    for npath in sorted(nodes):
        base = "/sys/firmware/devicetree/base" + \
            ("" if npath == "/" else npath)
        for pname in sorted(nodes[npath]):
            lines.append(f"===FILE {base}/{pname}")
            lines.append(base64.b64encode(nodes[npath][pname]).decode("ascii"))
    path.write_text("\n".join(lines) + "\n")


def mode_fixture_selfcheck(tmpdir: Path) -> None:
    rep = evidence_from_nodes(build_fixture_tree())
    assert rep["memory"]["bank_count"] == 3, rep["memory"]
    assert rep["memory"]["banks"][0]["base"] == 0x80000000
    assert rep["memory"]["banks"][0]["size"] == 0x39900000
    assert rep["memory"]["banks"][1]["base"] == 0xC0000000
    assert rep["memory"]["banks"][1]["size"] == 0x140000000
    assert rep["memory"]["banks"][2]["base"] == 0x200000000
    assert rep["memory"]["banks"][2]["size"] == 0x180000000
    assert rep["memory"]["total"] == 0x2F9900000
    assert rep["memory"]["cell_count"] == 12 and rep["memory"]["reg_raw_size"] == 48
    assert len(rep["reserved"]) == 2
    assert rep["reserved"][0]["no_map"] is True
    assert rep["reserved"][1]["base"] is None
    assert "SECRET" not in rep["chosen"]["bootargs_sanitized"]
    assert "androidboot.serialno=<redacted>" in rep["chosen"]["bootargs_sanitized"]
    assert "androidboot.slot_suffix=_a" in rep["chosen"]["bootargs_sanitized"]
    assert "kaslr-seed" in rep["chosen"]["sensitive_props_present"]
    assert rep["root"]["address_cells"] == 2 and rep["root"]["size_cells"] == 2

    dump_path = tmpdir / "fixture-devicetree-dump.txt"
    write_fixture_dump(build_fixture_tree(), dump_path)
    dump_nodes, dump_meta = parse_livetree_dump(dump_path.read_bytes())
    assert dump_meta["file_markers"] == sum(
        len(p) for p in build_fixture_tree().values())
    dump_rep = evidence_from_nodes(dump_nodes)
    assert dump_rep["memory"]["total"] == rep["memory"]["total"]
    assert dump_rep["reserved"][0]["no_map"] is True
    assert dump_rep["reserved"][1]["base"] is None

    blob = build_fixture_fdt()
    header = parse_fdt_header(blob)
    assert header["memreserve"] == [{"base": 0xB0000000, "size": 0x100000}]
    assert header["memreserve_terminated"] is True
    walk = walk_fdt_struct(blob, header)
    assert walk["complete"] is True
    assert walk["nodes"]["/memory"]["reg"] == \
        build_fixture_tree()["/memory"]["reg"]
    cross = fdt_walk_crosscheck(blob, header, dump_nodes)
    assert cross["verdict"] == "MATCH" and cross["struct_walk_complete"]

    iomem = parse_iomem(
        "00000000-ffffffff : PCI Bus 0000:00\n"
        "80894000-808fffff : System RAM\n"
        "92700000-b03fffff : System RAM\n"
        "\t9c000000-9e3fffff : reserved\n"
        "\ta0080000-a29fffff : Kernel code\n"
        "\t8a000000-8bffffff : CMA\n"
        "c0000000-ffbfffff : System RAM\n"
        "ffc20000-37fffffff : System RAM\n")
    assert len(iomem["system_ram"]) == 4
    assert iomem["kernel"]["Kernel code"]["base"] == 0xa0080000
    assert iomem["reserved_children"] == 1 and len(iomem["cma"]) == 1
    matrix = build_matrix(rep, iomem, {"MemTotal": 11875576})
    assert matrix["banks"][0]["status"] == "CONFIRMED"
    assert matrix["banks"][1]["status"] == "SUPPORTED"
    assert matrix["banks"][2]["status"] == "SUPPORTED"
    assert matrix["overlapping_banks"] == []
    assert matrix["iomem_orphans_outside_banks"] == []
    assert matrix["iomem_status"] == "OK"
    assert matrix["meminfo_sanity"]["pass"] is True
    assert matrix["meminfo_sanity"]["memtotal_kb"] == 11875576
    assert matrix["stock_kernel_alignment"]["mod_2m"] == 0x80000
    orphan_matrix = build_matrix(
        rep, parse_iomem("40000000-4fffffff : System RAM\n"), {})
    assert orphan_matrix["iomem_status"] == "CONFLICT"
    try:
        gate(rep, {**matrix,
                   "overlapping_banks": [[0x80000000, 0x90000000]]}, None)
    except SystemExit:
        pass
    else:
        fail("FIXTURE_SELFCHECK_FAILED", "bank overlap did not fail")
    try:
        gate(rep, build_matrix(
            rep, iomem, {"MemTotal": 0x2F9900000 // 1024 + 1}), None)
    except SystemExit:
        pass
    else:
        fail("FIXTURE_SELFCHECK_FAILED", "meminfo sanity did not fail")

    broken = bytearray(blob)
    at = header["off_struct"] + (header["off_strings"]
                                 - header["off_struct"]) - 4
    broken[at:at] = b"\x00"
    bad_walk = walk_fdt_struct(bytes(broken), header)
    assert bad_walk["complete"] is False, bad_walk
    print("R3_RUNTIME_EVIDENCE_FIXTURE_SELFCHECK=PASS")


def build_fixture_fdt() -> bytes:
    nodes = build_fixture_tree()
    order = ["/", "/memory", "/reserved-memory",
             "/reserved-memory/carveout@88000000", "/chosen"]
    struct_block = b""
    strings = b"\x00"
    offsets = {"": 0}

    def add_str(s: str) -> int:
        nonlocal strings
        if s in offsets:
            return offsets[s]
        off = len(strings)
        strings += s.encode() + b"\x00"
        offsets[s] = off
        return off

    def parent_of(npath: str) -> str:
        parent = npath.rsplit("/", 1)[0]
        return parent or "/"

    def emit(npath: str) -> None:
        nonlocal struct_block
        name = npath.rsplit("/", 1)[-1]
        nameb = name.encode() + b"\x00"
        nameb += b"\x00" * ((4 - len(nameb) % 4) % 4)
        struct_block += struct.pack(">I", FDT_BEGIN_NODE) + nameb
        for pname in sorted(nodes[npath]):
            value = nodes[npath][pname]
            struct_block += struct.pack(">III", FDT_PROP, len(value),
                                        add_str(pname))
            struct_block += value + b"\x00" * ((4 - len(value) % 4) % 4)
        for child in order:
            if child != npath and parent_of(child) == npath:
                emit(child)
        struct_block += struct.pack(">I", FDT_END_NODE)

    emit("/")
    struct_block += struct.pack(">I", FDT_END)
    while len(strings) % 4:
        strings += b"\x00"
    off_rsv = 40
    rsv = struct.pack(">QQ", 0xB0000000, 0x100000) + struct.pack(">QQ", 0, 0)
    off_struct = off_rsv + len(rsv)
    off_strings = off_struct + len(struct_block)
    totalsize = off_strings + len(strings)
    header = struct.pack(">10I", FDT_MAGIC, totalsize, off_struct,
                         off_strings, off_rsv, 17, 0, 0,
                         len(strings), len(struct_block))
    return header + rsv + struct_block + strings


def mode_debug(path: Path) -> None:
    blob = path.read_bytes()
    header = parse_fdt_header(blob)
    print(f"DEBUG file={path.name} size={len(blob)} totalsize={header['totalsize']:#x}"
          f" off_struct={header['off_struct']:#x}"
          f" off_strings={header['off_strings']:#x}"
          f" off_rsv={header['off_rsv']:#x} version={header['version']}"
          f" size_strings={header['size_strings']}"
          f" size_struct={header['size_struct']}"
          f" memreserve={header['memreserve']}"
          f" memreserve_terminated={header['memreserve_terminated']}")
    structb = blob[header["off_struct"]:header["totalsize"]]
    names = {1: "BEGIN_NODE", 2: "END_NODE", 3: "PROP", 4: "NOP", 9: "END"}
    i = 0
    n = 0
    while i + 4 <= len(structb) and n < 64:
        token = struct.unpack_from(">I", structb, i)[0]
        label = names.get(token, "UNKNOWN")
        print(f"DEBUG token[{n}] rel={i:#x} abs={header['off_struct'] + i:#x}"
              f" {token:#010x} {label} bytes={structb[i:i + 16].hex()}")
        n += 1
        i += 4
        if token == FDT_BEGIN_NODE:
            end = structb.find(b"\x00", i)
            if end < 0:
                break
            print(f"DEBUG   node name={structb[i:end]!r}")
            i = (end + 4) & ~3
        elif token == FDT_PROP:
            if i + 8 > len(structb):
                break
            plen, nameoff = struct.unpack_from(">II", structb, i)
            i += 8
            nend = blob[header["off_strings"]:header["totalsize"]].find(
                b"\x00", nameoff)
            pname = blob[header["off_strings"] + nameoff:
                         header["off_strings"] + nend].decode("ascii", "replace")
            print(f"DEBUG   prop name={pname!r} plen={plen} nameoff={nameoff:#x}")
            i = (i + plen + 3) & ~3
        elif token == FDT_END:
            print("DEBUG   reached FDT_END")
            return
    print(f"DEBUG WALK_STOPPED rel={i:#x}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode",
                   choices=("parse", "fixture-selfcheck", "debug"), required=True)
    p.add_argument("--fdt")
    p.add_argument("--devicetree-dump")
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
        mode_fixture_selfcheck(Path(os.environ.get("RUNNER_TEMP", "/tmp")))
        return
    if args.mode == "debug":
        if not args.fdt:
            fail("ARGS_MISSING", "fdt")
        mode_debug(Path(args.fdt))
        return
    for req in ("fdt", "out_json", "out_report"):
        if not getattr(args, req):
            fail("ARGS_MISSING", req)
    mode_parse(args)


if __name__ == "__main__":
    main()
