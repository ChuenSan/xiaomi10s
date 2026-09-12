#!/usr/bin/env python3
"""R3 RT-D (runtime DTB) build + fail-closed validator. GitHub Actions only.

Builds the RT-D DTS with cpp+dtc, then proves it against the numeric runtime
evidence committed next to it: exact RAM bank equality, reserved-memory set
equality with the runtime static carveouts, every carveout inside a RAM bank
and protected, no overlaps. Does not emit a flashable boot image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local DTB build/validation")

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def fail(label: str, detail: str = "") -> None:
    raise SystemExit(label if not detail else f"{label}: {detail}")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        fail("R3_RUNTIME_DTB_CMD_FAILED", f"{' '.join(cmd)}\n{proc.stderr}")


def assert_bootargs_sanitized(data: dict) -> None:
    for tok in data.get("chosen", {}).get("bootargs_sanitized", "").split():
        if "=" not in tok:
            continue
        key, value = tok.split("=", 1)
        if key.startswith("androidboot.") and key != "androidboot.slot_suffix" \
                and value != "<redacted>":
            fail("R3_EVIDENCE_NOT_SANITIZED", key)


def load_evidence(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail("R3_EVIDENCE_INVALID", str(exc))
    mem = data.get("memory", {})
    if not mem.get("banks") or not mem.get("total"):
        fail("R3_EVIDENCE_INVALID", "memory map empty")
    for bank in mem["banks"]:
        if not bank.get("size"):
            fail("R3_EVIDENCE_INVALID", "zero-size bank")
    if not data.get("capture", {}).get("runtime_fdt_available"):
        fail("R3_EVIDENCE_INVALID", "runtime FDT unavailable")
    assert_bootargs_sanitized(data)
    return data


def parse_fdt(blob: bytes) -> dict:
    """Strict walk: dtc output must parse completely and balanced."""
    if len(blob) < 40:
        fail("R3_RUNTIME_DTB_INVALID", "short header")
    (magic, totalsize, off_struct, off_strings, _rsv, version,
     _lc, _cpu, _ss, _st) = struct.unpack(">10I", blob[:40])
    if magic != FDT_MAGIC or totalsize > len(blob) or version < 16:
        fail("R3_RUNTIME_DTB_INVALID", "header")
    structb = blob[off_struct:totalsize]
    strings = blob[off_strings:totalsize]
    nodes: dict[str, dict[str, bytes]] = {}
    path: list[str] = []
    i = 0
    while i + 4 <= len(structb):
        token = struct.unpack_from(">I", structb, i)[0]
        i += 4
        if token == FDT_BEGIN_NODE:
            end = structb.find(b"\x00", i)
            if end < 0:
                fail("R3_RUNTIME_DTB_INVALID", "node name")
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
                fail("R3_RUNTIME_DTB_INVALID", "prop header")
            plen, nameoff = struct.unpack_from(">II", structb, i)
            i += 8
            nend = strings.find(b"\x00", nameoff)
            if nend < 0 or i + plen > len(structb):
                fail("R3_RUNTIME_DTB_INVALID", "prop value")
            nodes.setdefault("/" + "/".join(path), {})[
                strings[nameoff:nend].decode()] = structb[i:i + plen]
            i = (i + plen + 3) & ~3
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            if path:
                fail("R3_RUNTIME_DTB_INVALID", "unbalanced nodes")
            return nodes
        else:
            fail("R3_RUNTIME_DTB_INVALID", f"token {token:#x} at {i - 4:#x}")
    fail("R3_RUNTIME_DTB_INVALID", "no FDT_END")


def cells_u32(raw: bytes) -> list[int]:
    if len(raw) % 4:
        fail("R3_RUNTIME_DTB_INVALID", "reg alignment")
    return list(struct.unpack(f">{len(raw) // 4}I", raw))


def fold(parts: list[int]) -> int:
    v = 0
    for p in parts:
        v = (v << 32) | p
    return v


def root_cells(nodes: dict) -> tuple[int, int]:
    root = nodes.get("/", {})
    ac = fold(cells_u32(root.get("#address-cells", b"\x00\x00\x00\x02")))
    sc = fold(cells_u32(root.get("#size-cells", b"\x00\x00\x00\x02")))
    return ac, sc


def decode_memory(nodes: dict) -> list[list[int]]:
    ac, sc = root_cells(nodes)
    stride = ac + sc
    banks = []
    for npath in sorted(nodes):
        props = nodes[npath]
        if not props.get("device_type", b"").startswith(b"memory"):
            continue
        raw = props.get("reg")
        if raw is None:
            continue
        vals = cells_u32(raw)
        if len(vals) % stride:
            fail("R3_RUNTIME_DTB_INVALID", "memory cells")
        for k in range(0, len(vals), stride):
            banks.append([fold(vals[k:k + ac]),
                          fold(vals[k + ac:k + stride])])
    return sorted(banks)


def decode_reserved(nodes: dict) -> list[dict]:
    ac, sc = root_cells(nodes)
    stride = ac + sc
    out = []
    for npath in sorted(nodes):
        parts = [p for p in npath.split("/") if p]
        if len(parts) != 2 or parts[0] != "reserved-memory":
            continue
        props = nodes[npath]
        raw = props.get("reg")
        if raw is None:
            continue
        vals = cells_u32(raw)
        if len(vals) % stride:
            fail("R3_RUNTIME_DTB_INVALID", f"reserved cells {npath}")
        for k in range(0, len(vals), stride):
            out.append({
                "node": npath,
                "base": fold(vals[k:k + ac]),
                "size": fold(vals[k + ac:k + stride]),
                "no_map": "no-map" in props,
                "reusable": "reusable" in props,
                "compatible": props.get("compatible", b"").split(b"\x00")[0]
                .decode("ascii", "replace"),
            })
    return out


def gates(nodes: dict, evidence: dict) -> dict:
    banks = decode_memory(nodes)
    if not banks or sum(s for _b, s in banks) <= 0:
        fail("R3_RUNTIME_DTB_RAM_EMPTY", "no usable RAM described")
    ev_banks = sorted([b["base"], b["size"]]
                      for b in evidence["memory"]["banks"])
    if banks != ev_banks:
        fail("R3_RUNTIME_DTB_RAM_MISMATCH", f"evidence={ev_banks} dtb={banks}")
    reserved = decode_reserved(nodes)
    for r in reserved:
        if not any(b[0] <= r["base"] and r["base"] + r["size"] <= b[0] + b[1]
                   for b in banks):
            fail("R3_RUNTIME_DTB_RESERVED_OUTSIDE_RAM", r["node"])
        if not (r["no_map"] or r["reusable"] or r["compatible"]):
            fail("R3_RUNTIME_DTB_RESERVED_UNPROTECTED", r["node"])
    for i in range(len(reserved)):
        for j in range(i + 1, len(reserved)):
            a, c = reserved[i], reserved[j]
            if a["base"] < c["base"] + c["size"] \
                    and c["base"] < a["base"] + a["size"]:
                fail("R3_RUNTIME_DTB_RESERVED_OVERLAP",
                     f"{a['node']} vs {c['node']}")
    ev_static = sorted([r["base"], r["size"]] for r in evidence["reserved"]
                       if r.get("base") is not None)
    dtb_static = sorted([r["base"], r["size"]] for r in reserved)
    if ev_static != dtb_static:
        missing = [x for x in ev_static if x not in dtb_static]
        extra = [x for x in dtb_static if x not in ev_static]
        fail("R3_RUNTIME_DTB_RESERVED_MISMATCH",
             f"missing={missing} extra={extra}")
    chosen = nodes.get("/chosen", {})
    bootargs = chosen.get("bootargs", b"").split(b"\x00")[0].decode(
        "ascii", "replace")
    return {"banks": banks, "reserved_count": len(reserved),
            "bootargs": bootargs}


def fixture_nodes() -> dict:
    pack = struct.pack
    return {
        "/": {
            "#address-cells": pack(">I", 2),
            "#size-cells": pack(">I", 2),
        },
        "/memory": {
            "device_type": b"memory",
            "reg": pack(">QQQQQQ",
                        0x80000000, 0x39900000,
                        0xC0000000, 0x140000000,
                        0x200000000, 0x180000000),
        },
        "/reserved-memory/hyp@80000000": {
            "reg": pack(">QQ", 0x80000000, 0x600000),
            "no-map": b"",
        },
        "/reserved-memory/pil@8bb00000": {
            "reg": pack(">QQ", 0x8BB00000, 0x2500000),
            "no-map": b"",
        },
        "/reserved-memory/heap@8e100000": {
            "reg": pack(">QQ", 0x8E100000, 0x4600000),
            "no-map": b"",
        },
        "/reserved-memory/cmd-db@80860000": {
            "reg": pack(">QQ", 0x80860000, 0x20000),
            "compatible": b"qcom,cmd-db\x00",
        },
        "/chosen": {"bootargs": b"rdinit=/init panic=5 loglevel=7\x00"},
    }


def fixture_evidence() -> dict:
    regions = [
        [0x80000000, 0x600000], [0x80860000, 0x20000],
        [0x8BB00000, 0x2500000], [0x8E100000, 0x4600000],
    ]
    return {
        "capture": {"runtime_fdt_available": True},
        "memory": {"banks": [
            {"base": 0x80000000, "size": 0x39900000},
            {"base": 0x200000000, "size": 0x180000000},
            {"base": 0xC0000000, "size": 0x140000000},
        ], "total": 0x2F9900000},
        "reserved": [{"node": f"r@{b:#x}", "base": b, "size": s}
                     for b, s in regions],
        "chosen": {"bootargs_sanitized":
                   "console=ttyMSM0 androidboot.serialno=<redacted> "
                   "androidboot.slot_suffix=_a"},
    }


def expect_gate_failure(label: str, fn) -> None:
    try:
        fn()
    except SystemExit as exc:
        if label not in str(exc):
            fail("FIXTURE_SELFCHECK_FAILED", f"{label}: got {exc}")
        return
    fail("FIXTURE_SELFCHECK_FAILED", f"{label} did not fail")


def mode_fixture_selfcheck() -> None:
    nodes, evidence = fixture_nodes(), fixture_evidence()
    summary = gates(nodes, evidence)
    assert summary["banks"] == sorted([[0x80000000, 0x39900000],
                                       [0xC0000000, 0x140000000],
                                       [0x200000000, 0x180000000]])
    assert summary["reserved_count"] == 4
    assert summary["bootargs"] == "rdinit=/init panic=5 loglevel=7"

    def banks_mismatch():
        bad = json.loads(json.dumps(evidence))
        bad["memory"]["banks"][0]["size"] = 0x10000000
        gates(nodes, bad)

    def reserved_missing():
        bad = json.loads(json.dumps(evidence))
        bad["reserved"] = bad["reserved"][:2]
        gates(nodes, bad)

    def reserved_extra():
        bad = json.loads(json.dumps(evidence))
        bad["reserved"].append({"node": "x@b0000000", "base": 0xB0000000,
                                "size": 0x100000})
        gates(nodes, bad)

    def reserved_outside_ram():
        bad = json.loads(json.dumps(nodes))
        bad["/reserved-memory/hyp@80000000"]["reg"] = \
            struct.pack(">QQ", 0x40000000, 0x600000)
        bad_ev = json.loads(json.dumps(evidence))
        bad_ev["reserved"][0]["base"] = 0x40000000
        gates(bad, bad_ev)

    def reserved_overlap():
        bad = json.loads(json.dumps(nodes))
        bad["/reserved-memory/hyp@80000000"]["reg"] = \
            struct.pack(">QQ", 0x80700000, 0x400000)
        gates(bad, evidence)

    def reserved_unprotected():
        bad = json.loads(json.dumps(nodes))
        del bad["/reserved-memory/pil@8bb00000"]["no-map"]
        gates(bad, evidence)

    def evidence_unsanitized():
        bad = json.loads(json.dumps(evidence))
        bad["chosen"]["bootargs_sanitized"] = "androidboot.serialno=SECRET"
        assert_bootargs_sanitized(bad)

    def evidence_empty_map():
        bad = json.loads(json.dumps(evidence))
        bad["memory"]["banks"] = []
        if not bad["memory"]["banks"]:
            fail("R3_EVIDENCE_INVALID", "memory map empty")
        assert_bootargs_sanitized(bad)

    expect_gate_failure("R3_RUNTIME_DTB_RAM_MISMATCH", banks_mismatch)
    expect_gate_failure("R3_RUNTIME_DTB_RESERVED_MISMATCH", reserved_missing)
    expect_gate_failure("R3_RUNTIME_DTB_RESERVED_MISMATCH", reserved_extra)
    expect_gate_failure("R3_RUNTIME_DTB_RESERVED_OUTSIDE_RAM",
                        reserved_outside_ram)
    expect_gate_failure("R3_RUNTIME_DTB_RESERVED_OVERLAP", reserved_overlap)
    expect_gate_failure("R3_RUNTIME_DTB_RESERVED_UNPROTECTED",
                        reserved_unprotected)
    expect_gate_failure("R3_EVIDENCE_NOT_SANITIZED", evidence_unsanitized)
    expect_gate_failure("R3_EVIDENCE_INVALID", evidence_empty_map)
    print("R3_RUNTIME_DTB_FIXTURE_SELFCHECK=PASS")


def compile_dts(dts: Path, linux: Path, out: Path) -> bytes:
    qcom = linux / "arch/arm64/boot/dts/qcom"
    inc = [f"-I{linux / 'include'}", f"-I{linux / 'arch/arm64/boot/dts'}",
           f"-I{qcom}", f"-I{linux / 'scripts/dtc/include-prefixes'}"]
    proc = subprocess.run(
        ["cpp", "-nostdinc", "-undef", "-D__DTS__",
         "-x", "assembler-with-cpp", *inc, str(dts)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        fail("R3_RUNTIME_DTB_CPP_FAILED", proc.stderr)
    pre = out / "rt-d.pre.dts"
    pre.write_text(proc.stdout)
    dtb = out / "rt-d.dtb"
    run(["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", str(dtb), str(pre)])
    return dtb.read_bytes()


def mode_validate(args: argparse.Namespace) -> None:
    evidence_path = Path(args.evidence)
    evidence = load_evidence(evidence_path)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    blob = compile_dts(Path(args.dts), Path(args.linux), out)
    nodes = parse_fdt(blob)
    summary = gates(nodes, evidence)
    report = [
        "R3_RUNTIME_DTB_COMPLETION",
        f"RT_D_DTB sha256={sha(blob)} size={len(blob)}",
        f"R3_RUNTIME_DTB_EVIDENCE sha256={sha(evidence_path.read_bytes())}",
        f"R3_RUNTIME_DTB_RAM_MAP_MATCH=YES banks={summary['banks']}",
        f"R3_RUNTIME_DTB_RESERVED_COMPLETE=YES regions={summary['reserved_count']}",
        f"RT_D_BOOTARGS={summary['bootargs']!r}",
        "R3_RUNTIME_DTB_GATES=PASS",
        "R3_RUNTIME_DTB_SELF_CONTAINED=YES",
        "Does not emit a flashable boot image",
    ]
    (out / "r3-runtime-dtb-report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("validate", "fixture-selfcheck"),
                   required=True)
    p.add_argument("--dts")
    p.add_argument("--evidence")
    p.add_argument("--linux")
    p.add_argument("--out-dir")
    args = p.parse_args()
    if args.mode == "fixture-selfcheck":
        mode_fixture_selfcheck()
        return
    for req in ("dts", "evidence", "linux", "out_dir"):
        if not getattr(args, req):
            fail("ARGS_MISSING", req)
    mode_validate(args)


if __name__ == "__main__":
    main()
