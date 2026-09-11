#!/usr/bin/env python3
"""Audit M5I historical reproduction and overlay-compatible DTB metadata in GHA."""

import argparse
import hashlib
import os
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

RAW_SHA = "a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40"
ABL_SHA = "cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0"
M1_VENDOR_SHA = "29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5"
STOCK_VENDOR_SHA = "aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"
STOCK_DTBO_SHA = "018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"
STOCK_DTB0_SHA = "324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8"
ENTRY21_SHA = "44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93"
EXPECTED_SIZES = {"raw": 105960, "abl": 106026, "m1_vendor": 114688,
                  "stock_vendor": 100663296, "stock_dtbo": 33554432}
FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
TOK_BEGIN, TOK_END_NODE, TOK_PROP, TOK_NOP, TOK_END = 1, 2, 3, 4, 9
SYNTHETIC_ROOTS = ("/__symbols__", "/__fixups__", "/__local_fixups__")
GENERATED_PROPS = {"phandle", "linux,phandle"}
KNOWN_SYMBOLS = ["firmware", "soc", "intc", "pdc", "tlmm", "ufshc_mem",
                 "qupv3_se11_i2c", "cam_cci0", "aw8697_gpio_reset", "clock_rpmh"]
GENERIC_EQUIVALENCE_COMPATIBLES = {"simple-bus", "syscon"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, size):
    return (value + size - 1) // size * size


def cells(data):
    if data is None or len(data) % 4:
        return None
    return list(struct.unpack(f">{len(data) // 4}I", data))


def string_list(data):
    if data is None or not data.endswith(b"\0"):
        return []
    try:
        return [item.decode("utf-8") for item in data[:-1].split(b"\0") if item]
    except UnicodeDecodeError:
        return []


def cell_text(values):
    if values is None:
        return "ABSENT"
    return "<" + " ".join(f"0x{x:x}" for x in values) + "> (" + " ".join(map(str, values)) + ")"


@dataclass(frozen=True)
class Prop:
    value: bytes
    offset: int


class Fdt:
    def __init__(self, data, label):
        self.data = bytes(data)
        self.label = label
        if len(data) < 40:
            raise ValueError(f"{label}: short FDT")
        fields = struct.unpack_from(">10I", data, 0)
        (magic, self.totalsize, self.off_struct, self.off_strings, self.off_reserve,
         self.version, self.last_comp_version, self.boot_cpuid_phys,
         self.size_strings, self.size_struct) = fields
        if magic != FDT_MAGIC or self.totalsize != len(data):
            raise ValueError(f"{label}: invalid magic or totalsize")
        if self.off_struct + self.size_struct > len(data) or self.off_strings + self.size_strings > len(data):
            raise ValueError(f"{label}: FDT block outside totalsize")
        self.nodes = {}
        self.parents = {}
        self._parse()

    def _parse(self):
        pos = self.off_struct
        end = self.off_struct + self.size_struct
        stack = []
        complete = False
        while pos + 4 <= end:
            token = struct.unpack_from(">I", self.data, pos)[0]
            pos += 4
            if token == TOK_BEGIN:
                stop = self.data.find(b"\0", pos, end)
                if stop < 0:
                    raise ValueError(f"{self.label}: unterminated node")
                name = self.data[pos:stop].decode("utf-8", "replace")
                pos = align(stop + 1, 4)
                parent = stack[-1] if stack else None
                path = "/" if parent is None else parent.rstrip("/") + "/" + name
                stack.append(path)
                self.nodes[path] = {}
                self.parents[path] = parent
            elif token == TOK_END_NODE:
                if not stack:
                    raise ValueError(f"{self.label}: unbalanced node")
                stack.pop()
            elif token == TOK_PROP:
                if not stack or pos + 8 > end:
                    raise ValueError(f"{self.label}: malformed property")
                length, nameoff = struct.unpack_from(">II", self.data, pos)
                pos += 8
                value_offset = pos
                value = self.data[pos:pos + length]
                if len(value) != length:
                    raise ValueError(f"{self.label}: truncated property")
                pos = align(pos + length, 4)
                start = self.off_strings + nameoff
                stop = self.data.find(b"\0", start, self.off_strings + self.size_strings)
                if stop < 0:
                    raise ValueError(f"{self.label}: bad property name")
                name = self.data[start:stop].decode("utf-8", "replace")
                self.nodes[stack[-1]][name] = Prop(value, value_offset)
            elif token == TOK_NOP:
                continue
            elif token == TOK_END:
                complete = True
                break
            else:
                raise ValueError(f"{self.label}: unknown token {token}")
        if not complete or stack:
            raise ValueError(f"{self.label}: malformed structure")

    def prop(self, path, name):
        item = self.nodes.get(path, {}).get(name)
        return None if item is None else item.value

    def root_cells(self, name):
        return cells(self.prop("/", name))

    def root_strings(self, name):
        return string_list(self.prop("/", name))

    def table(self, path):
        result = {}
        for name, prop in self.nodes.get(path, {}).items():
            values = string_list(prop.value)
            result[name] = values[0] if values else "?"
        return result

    def symbols(self):
        return self.table("/__symbols__")

    def fixups(self):
        return {name: string_list(prop.value) for name, prop in self.nodes.get("/__fixups__", {}).items()}

    def phandle_map(self):
        result = {}
        for path, props in self.nodes.items():
            for name in ("phandle", "linux,phandle"):
                value = cells(props[name].value) if name in props else None
                if value and len(value) == 1:
                    result.setdefault(value[0], set()).add(path)
        return result


@dataclass
class VendorBoot:
    data: bytes
    version: int
    page_size: int
    header_size: int
    ramdisk_size: int
    dtb_size: int
    dtb_addr: int
    ramdisk_offset: int
    dtb_offset: int
    extent: int
    ramdisk: bytes
    dtb_region: bytes
    dtbs: list


def split_fdts(region, label):
    result = []
    pos = 0
    while pos < len(region):
        if pos + 8 > len(region) or struct.unpack_from(">I", region, pos)[0] != FDT_MAGIC:
            raise ValueError(f"{label}: no FDT at relative offset {pos}")
        size = struct.unpack_from(">I", region, pos + 4)[0]
        if size < 40 or pos + size > len(region):
            raise ValueError(f"{label}: bad FDT size at {pos}")
        result.append((pos, Fdt(region[pos:pos + size], f"{label}-dtb{len(result)}")))
        pos += size
    return result


def parse_vendor(data, label):
    if len(data) < 2112 or data[:8] != b"VNDRBOOT":
        raise ValueError(f"{label}: invalid vendor_boot")
    version = struct.unpack_from("<I", data, 8)[0]
    page_size = struct.unpack_from("<I", data, 12)[0]
    ramdisk_size = struct.unpack_from("<I", data, 24)[0]
    header_size = struct.unpack_from("<I", data, 2096)[0]
    dtb_size = struct.unpack_from("<I", data, 2100)[0]
    dtb_addr = struct.unpack_from("<Q", data, 2104)[0]
    ramdisk_offset = align(header_size, page_size)
    dtb_offset = ramdisk_offset + align(ramdisk_size, page_size)
    extent = dtb_offset + align(dtb_size, page_size)
    if version != 3 or page_size != 4096 or extent > len(data):
        raise ValueError(f"{label}: unsupported header or extent")
    ramdisk = data[ramdisk_offset:ramdisk_offset + ramdisk_size]
    region = data[dtb_offset:dtb_offset + dtb_size]
    return VendorBoot(data, version, page_size, header_size, ramdisk_size, dtb_size,
                      dtb_addr, ramdisk_offset, dtb_offset, extent, ramdisk, region,
                      split_fdts(region, label))


def parse_dtbo(data, label):
    if len(data) < 32:
        raise ValueError(f"{label}: short DTBO")
    magic, total, header, entry_size, count, entries, _, _ = struct.unpack_from(">8I", data, 0)
    if magic != DTBO_MAGIC or header != 32 or entry_size != 32 or total > len(data):
        raise ValueError(f"{label}: invalid DTBO header")
    result = []
    for index in range(count):
        size, offset = struct.unpack_from(">II", data, entries + index * entry_size)
        payload = data[offset:offset + size]
        if len(payload) != size:
            raise ValueError(f"{label}: entry {index} outside image")
        result.append((payload, Fdt(payload, f"{label}-entry{index}")))
    return result


def metadata_free_tree(fdt):
    result = {}
    for path, props in fdt.nodes.items():
        if any(path == root or path.startswith(root + "/") for root in SYNTHETIC_ROOTS):
            continue
        result[path] = {name: prop.value for name, prop in props.items() if name not in GENERATED_PROPS}
    return result


def subtree(fdt, root):
    return {path: {name: prop.value for name, prop in props.items() if name not in GENERATED_PROPS}
            for path, props in fdt.nodes.items()
            if (path == root or path.startswith(root.rstrip("/") + "/"))
            and not any(path == synthetic or path.startswith(synthetic + "/") for synthetic in SYNTHETIC_ROOTS)}


def selected_properties(fdt, predicate):
    return {(path, name): prop.value for path, props in fdt.nodes.items()
            if not any(path == root or path.startswith(root + "/") for root in SYNTHETIC_ROOTS)
            for name, prop in props.items() if predicate(name)}


def synthetic_nodes(fdt):
    return sorted(path for path in fdt.nodes if path != "/" and path.split("/", 2)[1].startswith("__"))


def phandle_counts(fdt):
    return (sum("phandle" in props for props in fdt.nodes.values()),
            sum("linux,phandle" in props for props in fdt.nodes.values()))


def ranges(before, after):
    limit = max(len(before), len(after))
    changed = [i for i in range(limit) if i >= len(before) or i >= len(after) or before[i] != after[i]]
    if not changed:
        return []
    output = []
    start = previous = changed[0]
    for value in changed[1:]:
        if value != previous + 1:
            output.append((start, previous + 1))
            start = value
        previous = value
    output.append((start, previous + 1))
    return output


def run_tool(command):
    proc = subprocess.run(command, capture_output=True, text=True)
    text = (proc.stderr or proc.stdout).strip().replace("\n", " | ")
    return proc.returncode, text


def apply_overlay(base, overlay, label, work):
    base_path = work / f"{label}.base.dtb"
    overlay_path = work / f"{label}.dtbo"
    merged_path = work / f"{label}.merged.dtb"
    base_path.write_bytes(base)
    overlay_path.write_bytes(overlay)
    rc, text = run_tool(["fdtoverlay", "-i", str(base_path), str(overlay_path), "-o", str(merged_path)])
    merged = merged_path.read_bytes() if rc == 0 and merged_path.exists() else b""
    return rc == 0, rc, text or "NONE", merged


def parse_source_labels(text):
    labels = set()
    pattern = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?=[A-Za-z_&/])")
    labels.update(pattern.findall(text))
    return labels


def node_compatible(fdt, path):
    return string_list(fdt.prop(path, "compatible"))


def node_status(fdt, path):
    values = string_list(fdt.prop(path, "status"))
    return values[0] if values else "okay(default)"


def basename(path):
    return path.rsplit("/", 1)[-1].split("@", 1)[0]


def probable_equivalent(stock, mainline, stock_path):
    stock_compat = set(node_compatible(stock, stock_path)) - GENERIC_EQUIVALENCE_COMPATIBLES
    candidates = []
    for path in mainline.nodes:
        score = 0
        compat = set(node_compatible(mainline, path)) - GENERIC_EQUIVALENCE_COMPATIBLES
        if stock_compat and compat and stock_compat.intersection(compat):
            score += 100 + len(stock_compat.intersection(compat))
        if basename(path) == basename(stock_path):
            score += 20
        if score:
            candidates.append((score, path))
    candidates.sort(reverse=True)
    if not candidates:
        return "NONE", "NONE"
    if len(candidates) == 1 or candidates[0][0] > candidates[1][0]:
        return candidates[0][1], "HIGH" if candidates[0][0] >= 100 else "MEDIUM"
    return candidates[0][1], "LOW"


def fragment_targets(overlay):
    targets = {}
    for symbol, locations in overlay.fixups().items():
        for location in locations:
            match = re.fullmatch(r"(/fragment@[^:]+):target:0", location)
            if match:
                targets[match.group(1)] = symbol
    for path, props in overlay.nodes.items():
        if path.count("/") == 1 and path.startswith("/fragment@") and "target-path" in props:
            values = string_list(props["target-path"].value)
            if values:
                targets[path] = "PATH:" + values[0]
    return targets


def fragment_audit(base, overlay, merged):
    targets = fragment_targets(overlay)
    fragments = sorted(path for path in overlay.nodes if path.count("/") == 1 and path.startswith("/fragment@"))
    applied = 0
    unresolved = []
    symbols = base.symbols()
    for fragment in fragments:
        marker = targets.get(fragment)
        if marker is None:
            unresolved.append(fragment + ":NO_TARGET")
            continue
        target = marker[5:] if marker.startswith("PATH:") else symbols.get(marker)
        if target is None or target not in merged.nodes:
            unresolved.append(fragment + ":TARGET_ABSENT")
            continue
        overlay_root = fragment + "/__overlay__"
        ok = overlay_root in overlay.nodes
        for path, props in overlay.nodes.items():
            if path != overlay_root and not path.startswith(overlay_root + "/"):
                continue
            suffix = path[len(overlay_root):]
            merged_path = target.rstrip("/") + suffix if target != "/" else "/" + suffix.lstrip("/")
            if merged_path not in merged.nodes:
                ok = False
                break
            for name in props:
                if name in GENERATED_PROPS:
                    continue
                if name not in merged.nodes[merged_path]:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            applied += 1
        else:
            unresolved.append(fragment + ":CONTENT_MISMATCH")
    return len(fragments), applied, unresolved


def identity(data, size, digest):
    return len(data) == size and sha(data) == digest


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GitHub Actions only: local build and validation are forbidden")
    parser = argparse.ArgumentParser()
    for name in ("baseline_raw", "baseline_abl", "historical_raw", "historical_abl",
                 "symbolized_raw", "symbolized_abl", "stock_vendor_boot", "stock_dtbo",
                 "m1_vendor_boot", "preprocessed_dts", "provenance", "out_dir"):
        parser.add_argument("--" + name.replace("_", "-"), required=True, type=Path)
    parser.add_argument("--candidate-vendor-boot", type=Path)
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    baseline_raw_data = args.baseline_raw.read_bytes()
    baseline_abl_data = args.baseline_abl.read_bytes()
    historical_raw_data = args.historical_raw.read_bytes()
    historical_abl_data = args.historical_abl.read_bytes()
    symbolized_raw_data = args.symbolized_raw.read_bytes()
    symbolized_abl_data = args.symbolized_abl.read_bytes()
    stock_vendor_data = args.stock_vendor_boot.read_bytes()
    stock_dtbo_data = args.stock_dtbo.read_bytes()
    m1_vendor_data = args.m1_vendor_boot.read_bytes()
    provenance = args.provenance.read_text(encoding="utf-8")

    raw_reproduced = (identity(baseline_raw_data, EXPECTED_SIZES["raw"], RAW_SHA)
                      and baseline_raw_data == historical_raw_data)
    abl_reproduced = (identity(baseline_abl_data, EXPECTED_SIZES["abl"], ABL_SHA)
                      and baseline_abl_data == historical_abl_data)
    private_inputs = (identity(m1_vendor_data, EXPECTED_SIZES["m1_vendor"], M1_VENDOR_SHA)
                      and identity(stock_vendor_data, EXPECTED_SIZES["stock_vendor"], STOCK_VENDOR_SHA)
                      and identity(stock_dtbo_data, EXPECTED_SIZES["stock_dtbo"], STOCK_DTBO_SHA))

    reproduction = [
        "M5I M1 exact historical reproduction",
        "DEVICE_OPERATION=NO", "SLOT_A_WRITTEN=NO", "LOCAL_BUILD=NO", "LOCAL_VALIDATION=NO",
        "GHA_ONLY=YES", "MEM0_READ_BEFORE_M5I=YES",
        f"M1_EXPECTED_RAW_DTB_SIZE={EXPECTED_SIZES['raw']}",
        f"M1_BASELINE_RAW_DTB_SIZE={len(baseline_raw_data)}",
        f"M1_EXPECTED_RAW_DTB_SHA256={RAW_SHA}",
        f"M1_BASELINE_RAW_DTB_SHA256={sha(baseline_raw_data)}",
        f"M5I_BASELINE_M1_RAW_DTB_REPRODUCED={'YES' if raw_reproduced else 'NO'}",
        f"M1_EXPECTED_ABL_DTB_SIZE={EXPECTED_SIZES['abl']}",
        f"M1_BASELINE_ABL_DTB_SIZE={len(baseline_abl_data)}",
        f"M1_EXPECTED_ABL_DTB_SHA256={ABL_SHA}",
        f"M1_BASELINE_ABL_DTB_SHA256={sha(baseline_abl_data)}",
        f"M5I_BASELINE_M1_ABL_DTB_REPRODUCED={'YES' if abl_reproduced else 'NO'}",
        f"EXACT_HISTORICAL_ARTIFACT_BYTES_MATCH={'YES' if raw_reproduced and abl_reproduced else 'NO'}",
        f"PRIVATE_INPUT_IDENTITIES={'PASS' if private_inputs else 'FAIL'}",
        provenance.rstrip(),
    ]
    out.joinpath("m5i-m1-reproduction.txt").write_text("\n".join(reproduction) + "\n", encoding="utf-8")

    if not raw_reproduced or not abl_reproduced or not private_inputs:
        final = ["M5I_M1_SOURCE_REPRODUCTION_FAILED", "READY_FOR_MAINLINE_V2_M5I_SYMBOLIZED_BASE_CONTROL=NO",
                 "CANDIDATE_GENERATED=NO", "DEVICE_OPERATION=NO"]
        out.joinpath("m5i-final-gates.txt").write_text("\n".join(final) + "\n", encoding="utf-8")
        for name in ("m5i-symbolized-dtb-report.txt", "m5i-symbol-delta.txt", "m5i-fixup-coverage.txt",
                     "m5i-overlay-apply-report.txt", "m5i-source-label-coverage.txt"):
            out.joinpath(name).write_text("STOP=M5I_M1_SOURCE_REPRODUCTION_FAILED\n", encoding="utf-8")
        emit_sums(out)
        print("\n".join(reproduction + final))
        return

    baseline_raw = Fdt(baseline_raw_data, "baseline-raw")
    baseline_abl = Fdt(baseline_abl_data, "baseline-abl")
    symbolized_raw = Fdt(symbolized_raw_data, "symbolized-raw")
    symbolized_abl = Fdt(symbolized_abl_data, "symbolized-abl")
    stock_vendor = parse_vendor(stock_vendor_data, "stock-vendor")
    m1_vendor = parse_vendor(m1_vendor_data, "m1-vendor")
    stock_entries = parse_dtbo(stock_dtbo_data, "stock-dtbo")
    stock_base = stock_vendor.dtbs[0][1]
    overlay_data, overlay = stock_entries[21]
    if sha(stock_base.data) != STOCK_DTB0_SHA or sha(overlay_data) != ENTRY21_SHA:
        raise SystemExit("M5I private Stock component identity failure")
    if len(m1_vendor.dtbs) != 1 or m1_vendor.dtbs[0][1].data != historical_abl_data:
        raise SystemExit("M5I historical M1 vendor_boot payload mismatch")

    raw_semantic_same = metadata_free_tree(baseline_raw) == metadata_free_tree(symbolized_raw)
    abl_semantic_same = metadata_free_tree(baseline_abl) == metadata_free_tree(symbolized_abl)
    source_nodes_same = set(metadata_free_tree(baseline_raw)) == set(metadata_free_tree(symbolized_raw))
    model_same = baseline_raw.prop("/", "model") == symbolized_raw.prop("/", "model")
    compatible_same = baseline_raw.prop("/", "compatible") == symbolized_raw.prop("/", "compatible")
    memory_same = {p: v for p, v in metadata_free_tree(baseline_raw).items() if basename(p) == "memory"} == \
                  {p: v for p, v in metadata_free_tree(symbolized_raw).items() if basename(p) == "memory"}
    chosen_same = subtree(baseline_raw, "/chosen") == subtree(symbolized_raw, "/chosen")
    reserved_same = subtree(baseline_raw, "/reserved-memory") == subtree(symbolized_raw, "/reserved-memory")
    status_same = selected_properties(baseline_raw, lambda n: n == "status") == selected_properties(symbolized_raw, lambda n: n == "status")
    reg_same = selected_properties(baseline_raw, lambda n: n == "reg") == selected_properties(symbolized_raw, lambda n: n == "reg")
    interrupts_same = selected_properties(baseline_raw, lambda n: n in ("interrupts", "interrupts-extended")) == selected_properties(symbolized_raw, lambda n: n in ("interrupts", "interrupts-extended"))
    clocks_same = selected_properties(baseline_raw, lambda n: n in ("clocks", "clock-names")) == selected_properties(symbolized_raw, lambda n: n in ("clocks", "clock-names"))
    regulators_same = selected_properties(baseline_raw, lambda n: "regulator" in n or n.endswith("-supply")) == selected_properties(symbolized_raw, lambda n: "regulator" in n or n.endswith("-supply"))
    semantic_ok = all((raw_semantic_same, abl_semantic_same, source_nodes_same, model_same,
                       compatible_same, memory_same, chosen_same, reserved_same, status_same,
                       reg_same, interrupts_same, clocks_same, regulators_same))

    before_phandle, before_linux = phandle_counts(baseline_raw)
    after_phandle, after_linux = phandle_counts(symbolized_raw)
    base_symbols = baseline_abl.symbols()
    symbolized_symbols = symbolized_abl.symbols()
    stock_symbols = stock_base.symbols()
    fixups = sorted(overlay.fixups())
    source_labels = parse_source_labels(args.preprocessed_dts.read_text(encoding="utf-8", errors="replace"))
    resolved = [name for name in fixups if name in symbolized_symbols]
    missing = [name for name in fixups if name not in symbolized_symbols]
    different = [name for name in resolved if stock_symbols.get(name) != symbolized_symbols.get(name)]
    unresolved = [name for name in fixups if name not in stock_symbols]
    label_present = [name for name in fixups if name in source_labels]
    label_absent = [name for name in fixups if name not in source_labels]

    report = [
        "M5I symbolized Mainline DTB audit",
        "LOGICAL_VARIABLE=OVERLAY_COMPATIBLE_DTC_METADATA",
        "BUILD_MODE=SYMBOLIZED_BASE_BUILD_MODE",
        "SYMBOL_TABLE_ONLY_CLAIM=NO",
        f"BASELINE_RAW_DTB_SHA256={sha(baseline_raw_data)}",
        f"SYMBOLIZED_RAW_DTB_SHA256={sha(symbolized_raw_data)}",
        f"BASELINE_RAW_DTB_SIZE={len(baseline_raw_data)}",
        f"SYMBOLIZED_RAW_DTB_SIZE={len(symbolized_raw_data)}",
        f"BASELINE_RAW_DTB_TOTALSIZE={baseline_raw.totalsize}",
        f"SYMBOLIZED_RAW_DTB_TOTALSIZE={symbolized_raw.totalsize}",
        f"M5I_SYMBOLIZED_M1_DTB_SHA={sha(symbolized_abl_data)}",
        f"M5I_SYMBOLIZED_M1_DTB_SIZE={len(symbolized_abl_data)}",
        f"QCOM_MSM_ID={cell_text(symbolized_abl.root_cells('qcom,msm-id'))}",
        f"QCOM_BOARD_ID={cell_text(symbolized_abl.root_cells('qcom,board-id'))}",
        f"COMPATIBLE={' / '.join(symbolized_abl.root_strings('compatible'))}",
        f"SYMBOLS_PRESENT={'YES' if '/__symbols__' in symbolized_abl.nodes else 'NO'}",
        f"SYMBOL_COUNT={len(symbolized_symbols)}",
        f"PHANDLE_PROPERTY_COUNT_BEFORE={before_phandle}",
        f"PHANDLE_PROPERTY_COUNT_AFTER={after_phandle}",
        f"LINUX_PHANDLE_PROPERTY_COUNT_BEFORE={before_linux}",
        f"LINUX_PHANDLE_PROPERTY_COUNT_AFTER={after_linux}",
        f"LOCAL_FIXUPS_PRESENT={'YES' if '/__local_fixups__' in symbolized_abl.nodes else 'NO'}",
        f"OTHER_SYNTHETIC_NODES={' | '.join(synthetic_nodes(symbolized_abl)) or 'NONE'}",
    ]
    invariants = [
        f"SEMANTIC_TREE_UNCHANGED_EXCLUDING_DTC_METADATA={'PASS' if semantic_ok else 'FAIL'}",
        f"RAW_SEMANTIC_TREE_UNCHANGED={'PASS' if raw_semantic_same else 'FAIL'}",
        f"ABL_SEMANTIC_TREE_UNCHANGED={'PASS' if abl_semantic_same else 'FAIL'}",
        f"MODEL_SAME={'PASS' if model_same else 'FAIL'}", f"COMPATIBLE_SAME={'PASS' if compatible_same else 'FAIL'}",
        f"MEMORY_SAME={'PASS' if memory_same else 'FAIL'}", f"CHOSEN_SAME={'PASS' if chosen_same else 'FAIL'}",
        f"RESERVED_MEMORY_SAME={'PASS' if reserved_same else 'FAIL'}",
        f"DEVICE_STATUS_PROPERTIES_SAME={'PASS' if status_same else 'FAIL'}",
        f"REG_PROPERTIES_SAME={'PASS' if reg_same else 'FAIL'}",
        f"INTERRUPTS_PROPERTIES_SAME={'PASS' if interrupts_same else 'FAIL'}",
        f"CLOCK_PROPERTIES_SAME={'PASS' if clocks_same else 'FAIL'}",
        f"REGULATOR_PROPERTIES_SAME={'PASS' if regulators_same else 'FAIL'}",
        f"SOURCE_NODES_SAME={'PASS' if source_nodes_same else 'FAIL'}",
    ]
    out.joinpath("m5i-symbolized-dtb-report.txt").write_text("\n".join(report + invariants) + "\n", encoding="utf-8")

    delta = [
        "M5I raw DTB binary delta",
        "DELTA_NAME=OVERLAY_COMPATIBLE_DTC_METADATA",
        f"CHANGED_RANGES={';'.join(f'[{a},{b})' for a, b in ranges(baseline_raw_data, symbolized_raw_data)) or 'NONE'}",
        f"SIZE_DELTA={len(symbolized_raw_data) - len(baseline_raw_data)}",
        f"TOTALSIZE_DELTA={symbolized_raw.totalsize - baseline_raw.totalsize}",
        f"SYMBOL_COUNT_DELTA={len(symbolized_raw.symbols()) - len(baseline_raw.symbols())}",
        f"PHANDLE_COUNT_DELTA={after_phandle - before_phandle}",
        f"LINUX_PHANDLE_COUNT_DELTA={after_linux - before_linux}",
        f"SYNTHETIC_NODES_BEFORE={' | '.join(synthetic_nodes(baseline_raw)) or 'NONE'}",
        f"SYNTHETIC_NODES_AFTER={' | '.join(synthetic_nodes(symbolized_raw)) or 'NONE'}",
        "SERIALIZATION_AND_BLOCK_OFFSETS_MAY_CHANGE=YES",
    ]
    out.joinpath("m5i-symbol-delta.txt").write_text("\n".join(delta) + "\n", encoding="utf-8")

    coverage = [
        "M5I Stock entry21 fixup coverage",
        f"FIXUP_SYMBOL_COUNT={len(fixups)}", f"HISTORICAL_BASE_SYMBOL_COUNT={len(base_symbols)}",
        f"HISTORICAL_FIXUPS_RESOLVED={sum(name in base_symbols for name in fixups)}",
        f"HISTORICAL_FIXUPS_MISSING={sum(name not in base_symbols for name in fixups)}",
        f"SYMBOLIZED_BASE_SYMBOL_COUNT={len(symbolized_symbols)}",
        f"FIXUPS_RESOLVED={len(resolved)}", f"FIXUPS_MISSING={len(missing)}",
        f"FIXUPS_DIFFERENT_TARGET={len(different)}", f"FIXUPS_UNRESOLVED={len(unresolved)}",
        f"MISSING_NAMES={','.join(missing) or 'NONE'}",
        f"DIFFERENT_TARGET_NAMES={','.join(different) or 'NONE'}",
    ]
    out.joinpath("m5i-fixup-coverage.txt").write_text("\n".join(coverage) + "\n", encoding="utf-8")

    source_rows = ["symbol|source_label_present|symbolized_dtb_symbol_present|symbolized_target_path"]
    source_rows.extend(f"{name}|{'YES' if name in source_labels else 'NO'}|{'YES' if name in symbolized_symbols else 'NO'}|{symbolized_symbols.get(name, 'ABSENT')}" for name in fixups)
    source_coverage = [
        "M5I exact preprocessed Mainline source label coverage",
        "SOURCE_LABEL_INPUT=CPP_PREPROCESSED_EXACT_HISTORICAL_M1_SOURCE",
        f"MAINLINE_SOURCE_LABEL_COUNT={len(source_labels)}",
        f"FIXUP_SYMBOL_PRESENT_AS_MAINLINE_SOURCE_LABEL={len(label_present)}",
        f"FIXUP_SYMBOL_ABSENT_FROM_MAINLINE_SOURCE={len(label_absent)}",
        f"SOURCE_LABEL_PRESENT_NAMES={','.join(label_present) or 'NONE'}",
        f"SOURCE_LABEL_ABSENT_NAMES={','.join(label_absent) or 'NONE'}",
        "",
    ] + source_rows
    out.joinpath("m5i-source-label-coverage.txt").write_text("\n".join(source_coverage) + "\n", encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="m5i-") as temp:
        work = Path(temp)
        stock_ok, stock_rc, stock_error, stock_merged = apply_overlay(stock_base.data, overlay_data, "stock", work)
        historical_ok, historical_rc, historical_error, historical_merged = apply_overlay(baseline_abl_data, overlay_data, "historical", work)
        symbolized_ok, symbolized_rc, symbolized_error, merged_data = apply_overlay(symbolized_abl_data, overlay_data, "symbolized", work)
        dtc_rc = roundtrip_rc = 1
        dtc_error = roundtrip_error = "NOT_RUN"
        if symbolized_ok:
            merged_path = work / "m5i-merged.dtb"
            roundtrip_path = work / "m5i-merged-roundtrip.dtb"
            dts_path = work / "m5i-merged.dts"
            merged_path.write_bytes(merged_data)
            dtc_rc, dtc_error = run_tool(["dtc", "-I", "dtb", "-O", "dts", "-o", str(dts_path), str(merged_path)])
            roundtrip_rc, roundtrip_error = run_tool(["dtc", "-I", "dtb", "-O", "dtb", "-o", str(roundtrip_path), str(merged_path)])

    overlay_report = [
        "M5I fdtoverlay/libfdt compatibility",
        "SCOPE=STANDARD_LIBFDT_REFERENCE_IMPLEMENTATION_NOT_XIAOMI_ABL_PROOF",
        "SAME_FDTOVERLAY_IMPLEMENTATION_FOR_ALL_CASES=YES",
        f"STOCK_DTB0_PLUS_STOCK_ENTRY21={'PASS' if stock_ok else 'FAIL'}",
        f"STOCK_CONTROL_RC={stock_rc}", f"STOCK_CONTROL_ERROR={stock_error}",
        f"HISTORICAL_M1_ABL_PLUS_STOCK_ENTRY21={'PASS' if historical_ok else 'FAIL'}",
        f"HISTORICAL_CONTROL_RC={historical_rc}", f"HISTORICAL_CONTROL_ERROR={historical_error}",
        f"M5I_SYMBOLIZED_MAINLINE_OVERLAY_APPLY={'PASS' if symbolized_ok else 'FAIL'}",
        f"SYMBOLIZED_TEST_RC={symbolized_rc}", f"SYMBOLIZED_TEST_ERROR={symbolized_error}",
        f"OVERLAY_BUILD_METADATA_SUFFICIENT_FOR_LIBFDT_COMPAT={'YES' if symbolized_ok else 'NO'}",
    ]
    out.joinpath("m5i-overlay-apply-report.txt").write_text("\n".join(overlay_report) + "\n", encoding="utf-8")

    candidate_exists = args.candidate_vendor_boot is not None and args.candidate_vendor_boot.exists()
    candidate_ok = False
    tail_sha = "NONE"
    merged_ok = False
    if symbolized_ok:
        merged = Fdt(merged_data, "merged")
        fragment_count, applied_count, fragment_errors = fragment_audit(symbolized_abl, overlay, merged)
        phandles = merged.phandle_map()
        duplicates = {value: paths for value, paths in phandles.items() if len(paths) != 1}
        dangling_symbols = {name: path for name, path in merged.symbols().items() if path not in merged.nodes}
        synthetic_fixups_left = any(path in merged.nodes for path in ("/__fixups__", "/__local_fixups__"))
        merged_ok = (dtc_rc == 0 and roundtrip_rc == 0 and not duplicates and not dangling_symbols
                     and not synthetic_fixups_left and applied_count == fragment_count)
        merged_report = [
            "M5I merged tree validation", f"MERGED_SHA256={sha(merged_data)}", f"MERGED_SIZE={len(merged_data)}",
            f"DTC_PARSE={'PASS' if dtc_rc == 0 else 'FAIL'}", f"DTC_PARSE_ERROR={dtc_error}",
            f"ROUND_TRIP={'PASS' if roundtrip_rc == 0 else 'FAIL'}", f"ROUND_TRIP_ERROR={roundtrip_error}",
            f"PHANDLE_UNIQUE={'PASS' if not duplicates else 'FAIL'}", f"DUPLICATE_PHANDLE_COUNT={len(duplicates)}",
            f"DANGLING_SYMBOL_TARGET_COUNT={len(dangling_symbols)}",
            f"UNRESOLVED_SYNTHETIC_FIXUP_NODES={1 if synthetic_fixups_left else 0}",
            f"FRAGMENT_COUNT={fragment_count}", f"FRAGMENTS_APPLIED={applied_count}",
            f"FRAGMENT_AUDIT_ERRORS={' | '.join(fragment_errors) or 'NONE'}",
            f"ROOT_MODEL={' / '.join(merged.root_strings('model')) or 'ABSENT'}",
            f"ROOT_COMPATIBLE={' / '.join(merged.root_strings('compatible'))}",
            f"ROOT_BOARD_ID={cell_text(merged.root_cells('qcom,board-id'))}",
            f"MEMORY_NODE_COUNT={sum(basename(path) == 'memory' for path in merged.nodes)}",
            f"CHOSEN_PRESENT={'YES' if '/chosen' in merged.nodes else 'NO'}",
            f"MERGED_TREE_VALID={'PASS' if merged_ok else 'FAIL'}",
        ]
        out.joinpath("m5i-merged-tree-report.txt").write_text("\n".join(merged_report) + "\n", encoding="utf-8")
        out.joinpath("m5i-merged-stock-derived.dtb").write_bytes(merged_data)

    if candidate_exists:
        candidate_data = args.candidate_vendor_boot.read_bytes()
        candidate = parse_vendor(candidate_data, "candidate")
        header_diffs = [i for i, pair in enumerate(zip(m1_vendor.data[:4096], candidate.data[:4096])) if pair[0] != pair[1]]
        header_ok = all(2100 <= value < 2104 for value in header_diffs)
        ramdisk_ok = candidate.ramdisk == m1_vendor.ramdisk
        topology_ok = len(candidate.dtbs) == 1 and candidate.dtbs[0][1].data == symbolized_abl_data
        ids_ok = (candidate.dtbs[0][1].root_cells("qcom,msm-id") == [356, 131073]
                  and candidate.dtbs[0][1].root_cells("qcom,board-id") == [45, 0])
        offset_ok = candidate.dtb_offset == 8192 == m1_vendor.dtb_offset
        extent_ok = candidate.extent == len(candidate_data)
        padding = align(candidate.dtb_size, candidate.page_size) - candidate.dtb_size
        padding_zero = candidate.data[candidate.dtb_offset + candidate.dtb_size:candidate.extent] == bytes(padding)
        tail_sha = sha(stock_vendor_data[candidate.extent:])
        candidate_ok = all((symbolized_ok, merged_ok, semantic_ok, header_ok, ramdisk_ok, topology_ok,
                            ids_ok, offset_ok, extent_ok, padding_zero))
        diff_map = [
            "M5I candidate binary report",
            "LOGICAL_VARIABLE=OVERLAY_COMPATIBLE_BASE_DTB_BUILD_METADATA",
            f"BASELINE_M1_VENDOR_BOOT_SHA256={sha(m1_vendor_data)}",
            f"CANDIDATE_SHA256={sha(candidate_data)}", f"ARTIFACT_SIZE={len(candidate_data)}",
            f"DTB_SIZE={candidate.dtb_size}", f"DTB_OFFSET={candidate.dtb_offset}",
            f"DTB_END={candidate.dtb_offset + candidate.dtb_size}", f"PADDING={padding}",
            f"CHANGED_RANGES={';'.join(f'[{a},{b})' for a, b in ranges(m1_vendor_data, candidate_data))}",
            f"HEADER_CHANGED_FIELDS={'dtb_size' if header_diffs else 'NONE'}",
            f"HEADER_DIFF_OFFSETS={','.join(map(str, header_diffs)) or 'NONE'}",
            f"VENDOR_BOOT_HEADER_UNCHANGED_EXCEPT_DTB_SIZE={'PASS' if header_ok else 'FAIL'}",
            f"VENDOR_RAMDISK_UNCHANGED={'PASS' if ramdisk_ok else 'FAIL'}",
            f"SINGLE_DTB_TOPOLOGY_UNCHANGED={'PASS' if topology_ok else 'FAIL'}",
            f"DTB_OFFSET_8192={'PASS' if offset_ok else 'FAIL'}",
            f"QCOM_IDS_UNCHANGED={'PASS' if ids_ok else 'FAIL'}",
            f"ARTIFACT_EXTENT_EXACT={'PASS' if extent_ok else 'FAIL'}",
            f"PADDING_ZERO={'PASS' if padding_zero else 'FAIL'}",
            "NEW_METADATA=__symbols__ plus DTC-generated phandle metadata",
            "UNAVOIDABLE_DELTA=dtb_size,artifact_extent,padding,DTB_serialization",
            f"EXPECTED_STOCK_VENDOR_TAIL_SHA_FROM_M5I_EXTENT={tail_sha}",
            f"PRIVATE_ARTIFACT_VALID={'PASS' if candidate_ok else 'FAIL'}",
        ]
        out.joinpath("m5i-candidate-diff-map.txt").write_text("\n".join(diff_map) + "\n", encoding="utf-8")
        out.joinpath("m5i-v-symbolized-mainline-dtb-vendor_boot.img").write_bytes(candidate_data)

    if not symbolized_ok:
        matrix = ["symbol|stock_target_path|mainline_source_label_exists|symbolized_dtb_symbol_exists|mainline_target_path|stock_compatible|mainline_compatible|mainline_status|semantic_candidate|class"]
        for name in fixups:
            stock_path = stock_symbols.get(name, "UNRESOLVED")
            mainline_path = symbolized_symbols.get(name)
            probable, confidence = probable_equivalent(stock_base, symbolized_abl, stock_path) if stock_path != "UNRESOLVED" else ("NONE", "NONE")
            target = mainline_path or probable
            stock_compat = ",".join(node_compatible(stock_base, stock_path)) if stock_path in stock_base.nodes else "NONE"
            mainline_compat = ",".join(node_compatible(symbolized_abl, target)) if target in symbolized_abl.nodes else "NONE"
            status = node_status(symbolized_abl, target) if target in symbolized_abl.nodes else "ABSENT"
            stock_compat_set = set(node_compatible(stock_base, stock_path)) if stock_path in stock_base.nodes else set()
            mainline_compat_set = set(node_compatible(symbolized_abl, target)) if target in symbolized_abl.nodes else set()
            if name in source_labels and mainline_path and stock_compat_set.intersection(mainline_compat_set):
                category = "A"
            elif probable != "NONE" and confidence == "HIGH":
                category = "B"
            elif mainline_path or probable != "NONE":
                category = "C"
            else:
                category = "D"
            matrix.append(f"{name}|{stock_path}|{'YES' if name in source_labels else 'NO'}|{'YES' if mainline_path else 'NO'}|{target or 'NONE'}|{stock_compat}|{mainline_compat}|{status}|{confidence}|{category}")
        out.joinpath("m5i-remaining-incompatibility-matrix.txt").write_text("\n".join(matrix) + "\n", encoding="utf-8")

    known = ["symbol|stock_source_path|stock_dtb_path|mainline_source_label_path|symbolized_dtb_symbol_path|mainline_probable_equivalent_path|equivalence_confidence|mainline_source_label_present|stock_compatible|mainline_compatible|mainline_status"]
    for name in KNOWN_SYMBOLS:
        stock_path = stock_symbols.get(name, "ABSENT")
        mainline_symbol_path = symbolized_symbols.get(name, "ABSENT")
        probable, confidence = probable_equivalent(stock_base, symbolized_abl, stock_path) if stock_path in stock_base.nodes else ("NONE", "NONE")
        target = mainline_symbol_path if mainline_symbol_path != "ABSENT" else probable
        known.append(f"{name}|NOT_AVAILABLE_BINARY_DERIVED|{stock_path}|"
                     f"{mainline_symbol_path if name in source_labels else 'ABSENT'}|{mainline_symbol_path}|"
                     f"{probable}|{confidence}|{'YES' if name in source_labels else 'NO'}|"
                     f"{','.join(node_compatible(stock_base, stock_path)) if stock_path in stock_base.nodes else 'NONE'}|"
                     f"{','.join(node_compatible(symbolized_abl, target)) if target in symbolized_abl.nodes else 'NONE'}|"
                     f"{node_status(symbolized_abl, target) if target in symbolized_abl.nodes else 'ABSENT'}")
    out.joinpath("m5i-known-symbol-audit.txt").write_text("\n".join(known) + "\n", encoding="utf-8")

    selftest = True
    try:
        Fdt(b"bad", "negative")
        selftest = False
    except ValueError:
        pass
    selftest = selftest and metadata_free_tree(baseline_raw) != metadata_free_tree(stock_base)
    ready = all((raw_reproduced, abl_reproduced, private_inputs, semantic_ok, stock_ok,
                 not historical_ok, symbolized_ok, not missing, not unresolved, merged_ok,
                 candidate_exists, candidate_ok, tail_sha != "NONE", selftest))
    if not semantic_ok:
        final_gate = "M5I_SYMBOLIZED_BUILD_SEMANTICS_CHANGED"
    elif not symbolized_ok:
        final_gate = "M5I_SYMBOLIZED_OVERLAY_STILL_INCOMPATIBLE"
    elif not ready:
        final_gate = "M5I_CANDIDATE_NOT_SAFE"
    else:
        final_gate = "READY_FOR_MAINLINE_V2_M5I_SYMBOLIZED_BASE_CONTROL"
    final = [
        f"FAIL_CLOSED_TESTS={'PASS' if selftest else 'FAIL'}",
        f"CANDIDATE_GENERATED={'YES' if candidate_exists else 'NO'}",
        f"READY_FOR_MAINLINE_V2_M5I_SYMBOLIZED_BASE_CONTROL={'YES' if ready else 'NO'}",
        f"FINAL_GATE={final_gate}", "DEVICE_OPERATION=NO", "SLOT_A_WRITTEN=NO",
        "CURRENT_B=M5D_BOOT+M5H_BOARD45_STOCK_DTB0_VENDOR_BOOT+STOCK_DTBO_UNCHANGED",
        "FUTURE_TRUE_DEVICE_AUTO_EXEC=NO",
    ]
    out.joinpath("m5i-final-gates.txt").write_text("\n".join(final) + "\n", encoding="utf-8")
    emit_sums(out)
    print("\n".join(reproduction + report + invariants + coverage + overlay_report + final))
    if symbolized_ok:
        print(out.joinpath("m5i-merged-tree-report.txt").read_text(encoding="utf-8"), end="")
    if candidate_exists:
        print(out.joinpath("m5i-candidate-diff-map.txt").read_text(encoding="utf-8"), end="")


def emit_sums(out):
    lines = []
    for path in sorted(out.iterdir()):
        if path.name != "SHA256SUMS" and path.is_file():
            lines.append(f"{sha(path.read_bytes())}  {path.name}")
    out.joinpath("SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
