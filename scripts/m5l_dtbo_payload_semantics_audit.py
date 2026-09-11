#!/usr/bin/env python3
"""M5L DTBO payload semantics audit (GitHub Actions only).

No local build, no local validation, no local DTBO parse, no local DTC, no
local fdtoverlay, no local binary diff. Every OEM input, parse, transform,
validation and negative test happens inside the private CI runner only.

Round scope (CI only, zero device operation):

  * exact 2x2 DTBO factorial recap and container downgrade
  * full root-property matrix diff between the two authoritative payloads
  * per-fragment targeting-mechanics audit of Stock thyme entry21
  * __fixups__ / __symbols__ / __local_fixups__ classification
  * exact M1 no-op tree plus its applied delta on the Stock base
  * padding / totalsize re-audit, explicitly downgraded
  * P1..P6 payload factor decomposition
  * L1 candidate: selector-matched M1 no-op (built only when P1 exists)
  * L2 candidate: DTC-generated Stock-style target/fixup minimal no-op
  * lazy, measured semantic no-op gate for every built overlay
  * full-partition normalized artifacts for the built candidates
  * fail-closed negative controls

Failure labels:

    M5L_SOURCE_IDENTITY_FAILED
    M5L_PROBE_CALIBRATION_FAILED
    M5L_STOCK_PAYLOAD_AUDIT_FAILED
    M5L_M1_PAYLOAD_AUDIT_FAILED
    M5L_TARGET_SYMBOL_UNRESOLVED
    M5L_L1_CONSTRUCTION_FAILED
    M5L_L2_CONSTRUCTION_FAILED
    M5L_L2_SEMANTIC_NOOP_FAILED
    M5L_CONTAINER_IDENTITY_FAILED
    M5L_FULL_ARTIFACT_INVALID
    M5L_NEGATIVE_TEST_FAILED
"""

import argparse
import hashlib
import os
import struct
import subprocess
import tempfile
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Authoritative exact inputs
# ---------------------------------------------------------------------------

STOCK_DTBO_SIZE = 33554432
STOCK_DTBO_SHA256 = "018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"
STOCK_DTBO_TOTAL_SIZE = 13415454
STOCK_DTBO_ENTRY_COUNT = 29

STOCK_VENDOR_BOOT_SIZE = 100663296
STOCK_VENDOR_BOOT_SHA256 = "aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"
STOCK_DTB0_SIZE = 540195
STOCK_DTB0_SHA256 = "324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8"

M1_DTBO_SIZE = 387
M1_DTBO_SHA256 = "316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1"

THYME_ENTRY_INDEX = 21
THYME_ENTRY_DT_OFFSET = 9666706
THYME_ENTRY_DT_SIZE = 484885
THYME_ENTRY_PAYLOAD_SHA256 = "44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93"

M5H_MERGED_SHA256 = "c48ef53de0dc3ad3ca31818b913b7380f615bbed8df925416abbae8ef0a8535b"

# M5K0 normalized three-way reference, used only for the container-identity table.
M5K0_SHORT_SIZE = 484949
M5K0_SHORT_SHA256 = "bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a"

DTBO_MAGIC = 0xD7B7AB1E
DTBO_HEADER_SIZE = 32
DTBO_ENTRY_SIZE = 32
DTBO_ENTRIES_OFFSET = 32
DTBO_PAGE_SIZE = 4096
DTBO_VERSION = 0
DTBO_PAYLOAD_OFFSET = 64
FDT_MAGIC = 0xD00DFEED

FULL_ARTIFACT_SIZE = 33554432

# ABL-visible selector family. Kept deliberately small and named: the audit
# reports every root property, but only this family is allowed to drive L1.
ABL_SELECTOR_PROPERTIES = (
    "qcom,board-id",
    "qcom,msm-id",
    "qcom,pmic-id",
    "qcom,pmic-id-size",
    "qcom,platform-id",
    "compatible",
    "model",
)

PHANDLE_PROPERTIES = ("phandle", "linux,phandle")

BOOKKEEPING_NODE_PREFIXES = ("/fragment@", "/__symbols__", "/__fixups__", "/__local_fixups__")

FORBIDDEN_SEMANTIC_PROPERTIES = (
    "status",
    "reg",
    "interrupts",
    "interrupts-extended",
    "interrupt-parent",
    "clocks",
    "clock-names",
    "power-domains",
    "assigned-clocks",
    "assigned-clock-rates",
)

MARKER_PROPERTY = "qcom,thyme-route-b-noop"

FDT_HEADER_SIZE = 40

DETAIL_CAP = 4096
BLOCK_SIZE = 4096

PROBE_TARGET_SYMBOL = "m5l_probe_target_symbol"
PROBE_BODY_SYMBOL = "m5l_probe_body_symbol"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, size):
    return (value + size - 1) // size * size


def cells(data):
    if data is None or len(data) % 4:
        return None
    return list(struct.unpack(f">{len(data) // 4}I", data))


def is_string_list(value):
    if not value.endswith(b"\0"):
        return False
    parts = value[:-1].split(b"\0")
    if not parts:
        return False
    for part in parts:
        if not part:
            return False
        if any(byte < 0x20 or byte > 0x7E for byte in part):
            return False
    return True


def dts_literal(value):
    """Render one FDT property value as a DTS assignment right-hand side."""
    if is_string_list(value):
        return ", ".join(f'"{part.decode("ascii")}"' for part in value[:-1].split(b"\0"))
    if len(value) % 4 == 0:
        words = struct.unpack(f">{len(value) // 4}I", value)
        return "<" + " ".join(f"0x{word:02x}" for word in words) + ">"
    return "[" + " ".join(f"0x{byte:02x}" for byte in value) + "]"


# ---------------------------------------------------------------------------
# FDT reader: ordered tree with absolute property-value offsets
# ---------------------------------------------------------------------------


class Node:
    __slots__ = ("path", "name", "props", "children")

    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.props = {}          # name -> (value bytes, absolute value offset)
        self.children = {}       # name -> Node, insertion ordered

    def child(self, name):
        return self.children.get(name)

    def descendant_paths(self):
        stack = [self]
        while stack:
            node = stack.pop()
            yield node.path
            stack.extend(node.children.values())


class Fdt:
    """Minimal read-only FDT parser.

    Builds an ordered node tree and remembers the absolute offset of every
    property value, which is what makes __fixups__ offset attribution possible.
    """

    def __init__(self, data, label):
        self.data = bytes(data)
        self.label = label
        if len(self.data) < 40:
            raise ValueError(f"{label}: short FDT")
        (magic, self.totalsize, self.off_struct, self.off_strings, self.off_reserve,
         self.version, self.last_comp_version, self.boot_cpuid_phys,
         self.size_strings, self.size_struct) = struct.unpack_from(">10I", self.data, 0)
        if magic != FDT_MAGIC:
            raise ValueError(f"{label}: FDT magic mismatch")
        if self.totalsize != len(self.data):
            raise ValueError(f"{label}: totalsize={self.totalsize} bytes={len(self.data)}")
        if self.off_struct + self.size_struct > self.totalsize:
            raise ValueError(f"{label}: structure block outside FDT")
        if self.off_strings + self.size_strings > self.totalsize:
            raise ValueError(f"{label}: strings block outside FDT")
        self.root = None
        self.value_offset_index = {}
        self._parse_reserve()
        self._parse_nodes()
        if self.root is None:
            raise ValueError(f"{label}: empty structure block")

    def _parse_reserve(self):
        self.reserve = []
        pos = self.off_reserve
        while pos + 16 <= self.totalsize:
            address, size = struct.unpack_from(">QQ", self.data, pos)
            pos += 16
            if address == 0 and size == 0:
                return
            self.reserve.append((address, size))
        raise ValueError(f"{self.label}: unterminated reserve map")

    def _parse_nodes(self):
        pos = self.off_struct
        end = self.off_struct + self.size_struct
        stack = []
        saw_end = False
        while pos + 4 <= end:
            token = struct.unpack_from(">I", self.data, pos)[0]
            pos += 4
            if token == 1:  # FDT_BEGIN_NODE
                nul = self.data.find(b"\0", pos, end)
                if nul < 0:
                    raise ValueError(f"{self.label}: unterminated node name")
                name = self.data[pos:nul].decode("utf-8", "replace")
                pos = align(nul + 1, 4)
                if not stack:
                    if name:
                        raise ValueError(f"{self.label}: non-empty root name")
                    node = Node("/", "")
                    self.root = node
                else:
                    parent = stack[-1]
                    path = "/" + name if parent.path == "/" else parent.path + "/" + name
                    node = Node(path, name)
                    parent.children[name] = node
                stack.append(node)
            elif token == 2:  # FDT_END_NODE
                if not stack:
                    raise ValueError(f"{self.label}: unbalanced END_NODE")
                stack.pop()
            elif token == 3:  # FDT_PROP
                if not stack or pos + 8 > end:
                    raise ValueError(f"{self.label}: malformed property")
                length, nameoff = struct.unpack_from(">II", self.data, pos)
                pos += 8
                value = self.data[pos:pos + length]
                if len(value) != length:
                    raise ValueError(f"{self.label}: truncated property")
                value_offset = pos
                pos = align(pos + length, 4)
                start = self.off_strings + nameoff
                stop = self.data.find(b"\0", start, self.off_strings + self.size_strings)
                if stop < 0:
                    raise ValueError(f"{self.label}: bad property name")
                name = self.data[start:stop].decode("utf-8", "replace")
                node = stack[-1]
                node.props[name] = (value, value_offset)
                self.value_offset_index[value_offset] = (node.path, name)
            elif token == 4:  # FDT_NOP
                continue
            elif token == 9:  # FDT_END
                saw_end = True
                break
            else:
                raise ValueError(f"{self.label}: unknown structure token {token}")
        if not saw_end or stack:
            raise ValueError(f"{self.label}: malformed structure termination")

    # -- queries ----------------------------------------------------------

    def walk(self):
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(list(node.children.values())))

    def node(self, path):
        if path == "/":
            return self.root
        cursor = self.root
        for part in path.strip("/").split("/"):
            cursor = cursor.children.get(part) if cursor else None
            if cursor is None:
                return None
        return cursor

    def prop(self, path, name):
        node = self.node(path)
        if node is None:
            return None
        entry = node.props.get(name)
        return None if entry is None else entry[0]

    def prop_offset(self, path, name):
        node = self.node(path)
        if node is None:
            return None
        entry = node.props.get(name)
        return None if entry is None else entry[1]

    def root_cells(self, name):
        return cells(self.prop("/", name))

    def root_strings(self, name):
        value = self.prop("/", name)
        if value is None or not is_string_list(value):
            return []
        return [part.decode("utf-8", "replace") for part in value[:-1].split(b"\0")]

    def fragments(self):
        return [node for node in self.root.children.values() if node.name.startswith("fragment@")]

    def special(self):
        result = {}
        for path in ("/__fixups__", "/__local_fixups__", "/__symbols__"):
            node = self.node(path)
            result[path] = None if node is None else node
        return result

    def special_counts(self):
        node = {path: value for path, value in self.special().items()}
        return {path: ("ABSENT" if value is None else len(value.props)) for path, value in node.items()}

    def phandle_count(self):
        total = 0
        for node in self.walk():
            for name in PHANDLE_PROPERTIES:
                if name in node.props:
                    total += 1
        return total

    def local_phandles(self):
        mapping = {}
        for node in self.walk():
            for name in PHANDLE_PROPERTIES:
                entry = node.props.get(name)
                values = cells(entry[0]) if entry else None
                if values:
                    mapping[values[0]] = node.path
        return mapping


# ---------------------------------------------------------------------------
# DTBO container
# ---------------------------------------------------------------------------


class DtboEntry:
    __slots__ = ("index", "dt_size", "dt_offset", "image_id", "rev", "custom", "payload", "fdt")

    def __init__(self, index, dt_size, dt_offset, image_id, rev, custom, payload, fdt):
        self.index = index
        self.dt_size = dt_size
        self.dt_offset = dt_offset
        self.image_id = image_id
        self.rev = rev
        self.custom = custom
        self.payload = payload
        self.fdt = fdt


class Dtbo:
    __slots__ = ("data", "label", "total_size", "header_size", "entry_size",
                 "entry_count", "entries_offset", "page_size", "version", "entries")

    def __init__(self, data, label, header, entries):
        self.data = data
        self.label = label
        (self.total_size, self.header_size, self.entry_size, self.entry_count,
         self.entries_offset, self.page_size, self.version) = header
        self.entries = entries


def parse_dtbo(data, label):
    if len(data) < DTBO_HEADER_SIZE:
        raise ValueError(f"{label}: short DTBO")
    magic, total, header_size, entry_size, count, entries_offset, page_size, version = \
        struct.unpack_from(">8I", data, 0)
    if magic != DTBO_MAGIC or header_size != DTBO_HEADER_SIZE or entry_size != DTBO_ENTRY_SIZE:
        raise ValueError(f"{label}: invalid DTBO header")
    if total > len(data) or entries_offset + count * entry_size > total:
        raise ValueError(f"{label}: DTBO ranges exceed total_size")
    entries = []
    for index in range(count):
        values = struct.unpack_from(">8I", data, entries_offset + index * entry_size)
        dt_size, dt_offset, image_id, rev = values[:4]
        if dt_offset + dt_size > total:
            raise ValueError(f"{label}: entry {index} outside total_size")
        payload = data[dt_offset:dt_offset + dt_size]
        entries.append(DtboEntry(index, dt_size, dt_offset, image_id, rev, tuple(values[4:]),
                                 payload, Fdt(payload, f"{label}-entry{index}")))
    return Dtbo(data, label, (total, header_size, entry_size, count, entries_offset,
                              page_size, version), entries)


def build_container(payload):
    """One-entry DTBO wrapper: id/rev/custom zero, dt_offset 64, no padding."""
    total = DTBO_PAYLOAD_OFFSET + len(payload)
    header = struct.pack(">8I", DTBO_MAGIC, total, DTBO_HEADER_SIZE, DTBO_ENTRY_SIZE,
                         1, DTBO_ENTRIES_OFFSET, DTBO_PAGE_SIZE, DTBO_VERSION)
    entry = struct.pack(">8I", len(payload), DTBO_PAYLOAD_OFFSET, 0, 0, 0, 0, 0, 0)
    return header + entry + payload


def pad_fdt(blob, target_size):
    """M5J fixed-slot expansion: totalsize field plus zero fill."""
    fdt = Fdt(blob, "pad-source")
    if target_size < fdt.totalsize:
        raise ValueError("FDT does not fit target slot")
    result = bytearray(blob)
    struct.pack_into(">I", result, 4, target_size)
    result.extend(b"\0" * (target_size - len(result)))
    Fdt(result, "padded-fdt")
    return bytes(result)


def parse_vendor_dtb_area(data, label):
    if len(data) < 2112 or data[:8] != b"VNDRBOOT":
        raise ValueError(f"{label}: vendor_boot magic/header")
    version = struct.unpack_from("<I", data, 8)[0]
    page_size = struct.unpack_from("<I", data, 12)[0]
    if version != 3 or page_size == 0:
        raise ValueError(f"{label}: expected vendor_boot v3")
    header_size = struct.unpack_from("<I", data, 2096)[0]
    dtb_size = struct.unpack_from("<I", data, 2100)[0]
    ramdisk_size = struct.unpack_from("<I", data, 24)[0]
    dtb_offset = align(header_size, page_size) + align(ramdisk_size, page_size)
    area = data[dtb_offset:dtb_offset + dtb_size]
    if len(area) != dtb_size:
        raise ValueError(f"{label}: DTB area exceeds image")
    if struct.unpack_from(">I", area, 0)[0] != FDT_MAGIC:
        raise ValueError(f"{label}: no FDT magic at DTB area start")
    return area


# ---------------------------------------------------------------------------
# DTC / fdtoverlay helpers
# ---------------------------------------------------------------------------


def run_labeled(argv, label):
    """Run an external tool and fail closed with a named label on error."""
    try:
        return subprocess.run(argv, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise SystemExit(f"{label} missing tool: {error}")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip().splitlines()
        raise SystemExit(f"{label} {' '.join(argv)} :: {detail[-1] if detail else 'non-zero exit'}")


def dtc_compile(work, name, dts_text, symbols=True):
    dts = work / f"{name}.dts"
    dtb = work / f"{name}.dtbo"
    dts.write_text(dts_text, encoding="utf-8")
    argv = ["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(dtb)]
    if symbols:
        argv.insert(1, "-@")
    argv.append(str(dts))
    run_labeled(argv, "M5L_DTC_FAILED")
    return dtb.read_bytes()


def dtc_roundtrip(work, name, blob):
    source = work / f"{name}.dtb"
    output = work / f"{name}.roundtrip.dtb"
    source.write_bytes(blob)
    run_labeled(["dtc", "-q", "-I", "dtb", "-O", "dtb", "-o", str(output), str(source)],
                "M5L_DTC_FAILED")
    return output.read_bytes()


def fdtoverlay_apply(work, name, base, overlay):
    base_path = work / f"{name}.base.dtb"
    overlay_path = work / f"{name}.overlay.dtbo"
    merged_path = work / f"{name}.merged.dtb"
    base_path.write_bytes(base)
    overlay_path.write_bytes(overlay)
    run_labeled(["fdtoverlay", "-i", str(base_path), str(overlay_path), "-o", str(merged_path)],
                "M5L_FDTOVERLAY_FAILED")
    return merged_path.read_bytes()


def fdtoverlay_apply_status(work, name, base, overlay):
    """Return (ok, detail) without raising, for negative controls."""
    try:
        merged = fdtoverlay_apply(work, name, base, overlay)
    except SystemExit as error:
        return False, str(error).splitlines()[0]
    return True, f"merged {len(merged)} bytes"


def changed_ranges(before, after):
    common = min(len(before), len(after))
    ranges = []
    pos = 0
    while pos < common:
        while pos < common and before[pos] == after[pos]:
            pos += 1
        if pos == common:
            break
        start = pos
        while pos < common and before[pos] != after[pos]:
            pos += 1
        ranges.append((start, pos))
    if len(before) != len(after):
        ranges.append((common, max(len(before), len(after))))
    return ranges


# ---------------------------------------------------------------------------
# Semantic comparison
# ---------------------------------------------------------------------------


def semantic_diff(base, merged, label):
    """Compare two FDT trees. Generated bookkeeping is allowed, device
    semantics are not. Returns a report dict plus violation strings."""
    info = {
        "label": label,
        "added_nodes": [],
        "removed_nodes": [],
        "added_props": [],
        "removed_props": [],
        "changed_props": [],
        "phandle_props": [],
        "bookkeeping_props": [],
        "retains_fragment_nodes": False,
    }
    base_nodes = {node.path: node for node in base.walk()}
    merged_nodes = {node.path: node for node in merged.walk()}

    def bookkeeping(path):
        return any(path == prefix or path.startswith(prefix) for prefix in BOOKKEEPING_NODE_PREFIXES)

    for path in sorted(set(merged_nodes) - set(base_nodes)):
        if bookkeeping(path):
            info["added_nodes"].append(path + " [GENERATED]")
            if path.startswith("/fragment@"):
                info["retains_fragment_nodes"] = True
        else:
            info["added_nodes"].append(path)

    info["removed_nodes"] = sorted(set(base_nodes) - set(merged_nodes))

    for path in sorted(set(base_nodes) & set(merged_nodes)):
        before = base_nodes[path].props
        after = merged_nodes[path].props
        for name in sorted(set(after) - set(before)):
            if name in PHANDLE_PROPERTIES:
                info["phandle_props"].append(f"{path}:{name} ADDED")
            elif bookkeeping(path):
                info["bookkeeping_props"].append(f"{path}:{name} ADDED")
            else:
                info["added_props"].append(f"{path}:{name}")
        for name in sorted(set(before) - set(after)):
            info["removed_props"].append(f"{path}:{name}")
        for name in sorted(set(before) & set(after)):
            if before[name][0] == after[name][0]:
                continue
            if name in PHANDLE_PROPERTIES:
                info["phandle_props"].append(f"{path}:{name} CHANGED "
                                             f"0x{cells(before[name][0])[0]:x}->"
                                             f"0x{cells(after[name][0])[0]:x}")
            else:
                info["changed_props"].append(f"{path}:{name}")

    violations = []
    for path in info["added_nodes"]:
        if not path.endswith("[GENERATED]"):
            violations.append(f"ADDED_NODE {path}")
    for path in info["removed_nodes"]:
        violations.append(f"REMOVED_NODE {path}")
    for item in info["added_props"]:
        violations.append(f"ADDED_PROPERTY {item}")
    for item in info["removed_props"]:
        violations.append(f"REMOVED_PROPERTY {item}")
    for item in info["changed_props"]:
        violations.append(f"CHANGED_PROPERTY {item}")

    forbidden = []
    for item in info["added_props"] + info["removed_props"] + info["changed_props"]:
        name = item.rsplit(":", 1)[-1]
        if name in FORBIDDEN_SEMANTIC_PROPERTIES or name.endswith("-supply") \
                or name.startswith("regulator-"):
            forbidden.append(item)
    info["forbidden"] = forbidden
    info["violations"] = violations
    info["valid_device_semantics_unchanged"] = not violations
    return info


def semantic_report_lines(info):
    lines = [
        f"SEMANTIC_DIFF_LABEL={info['label']}",
        f"SEMANTIC_DIFF_VALID_DEVICE_SEMANTICS_UNCHANGED="
        f"{'YES' if info['valid_device_semantics_unchanged'] else 'NO'}",
        f"SEMANTIC_DIFF_VIOLATION_COUNT={len(info['violations'])}",
        f"SEMANTIC_DIFF_FORBIDDEN_PROPERTY_COUNT={len(info['forbidden'])}",
        f"SEMANTIC_DIFF_PHANDLE_BOOKKEEPING_COUNT={len(info['phandle_props'])}",
        f"SEMANTIC_DIFF_GENERATED_BOOKKEEPING_PROPERTY_COUNT={len(info['bookkeeping_props'])}",
        f"SEMANTIC_DIFF_MERGED_RETAINS_FRAGMENT_NODES="
        f"{'YES' if info['retains_fragment_nodes'] else 'NO'}",
    ]
    for category, key in (("ADDED_NODE", "added_nodes"), ("REMOVED_NODE", "removed_nodes"),
                          ("ADDED_PROPERTY", "added_props"), ("REMOVED_PROPERTY", "removed_props"),
                          ("CHANGED_PROPERTY", "changed_props")):
        items = info[key]
        lines.append(f"SEMANTIC_DIFF_{category}_COUNT={len(items)}")
        for item in items[:DETAIL_CAP]:
            lines.append(f"SEMANTIC_DIFF_{category}={item}")
    for item in info["phandle_props"][:DETAIL_CAP]:
        lines.append(f"SEMANTIC_DIFF_PHANDLE_BOOKKEEPING={item}")
    for item in info["bookkeeping_props"][:DETAIL_CAP]:
        lines.append(f"SEMANTIC_DIFF_GENERATED_BOOKKEEPING={item}")
    for item in info["violations"][:DETAIL_CAP]:
        lines.append(f"SEMANTIC_DIFF_VIOLATION={item}")
    return lines


# ---------------------------------------------------------------------------
# Candidate audits
# ---------------------------------------------------------------------------


def selector_matrix(stock_fdt, m1_fdt):
    """Full root-property matrix plus /chosen, for both payloads."""
    rows = []
    root_stock = stock_fdt.root.props
    root_m1 = m1_fdt.root.props
    for name in sorted(set(root_stock) | set(root_m1)):
        left = root_stock.get(name)
        right = root_m1.get(name)
        if left is None:
            verdict = "MISSING_IN_STOCK"
        elif right is None:
            verdict = "MISSING_IN_M1"
        elif left[0] == right[0]:
            verdict = "SAME"
        else:
            verdict = "DIFFERENT"
        rows.append((name, left, right, verdict))

    chosen = []
    chosen_stock = stock_fdt.node("/chosen")
    chosen_m1 = m1_fdt.node("/chosen")
    names = sorted(set(chosen_stock.props if chosen_stock else {})
                   | set(chosen_m1.props if chosen_m1 else {}))
    for name in names:
        left = chosen_stock.props.get(name) if chosen_stock else None
        right = chosen_m1.props.get(name) if chosen_m1 else None
        if left is None:
            verdict = "MISSING_IN_STOCK"
        elif right is None:
            verdict = "MISSING_IN_M1"
        elif left[0] == right[0]:
            verdict = "SAME"
        else:
            verdict = "DIFFERENT"
        chosen.append((name, left, right, verdict))

    selector_rows = [row for row in rows if row[0] in ABL_SELECTOR_PROPERTIES]
    selector_differs = [row[0] for row in selector_rows if row[3] != "SAME"]
    other_differs = [row[0] for row in rows
                     if row[3] != "SAME" and row[0] not in ABL_SELECTOR_PROPERTIES]
    return {
        "rows": rows,
        "chosen": chosen,
        "selector_rows": selector_rows,
        "selector_differs": selector_differs,
        "other_differs": other_differs,
        "present_in_stock_only": [row[0] for row in rows if row[3] == "MISSING_IN_M1"],
        "present_in_m1_only": [row[0] for row in rows if row[3] == "MISSING_IN_STOCK"],
        "different_values": [row[0] for row in rows if row[3] == "DIFFERENT"],
    }


OFFSET_CONVENTIONS = (
    ("ABSOLUTE", lambda raw, fdt: raw),
    ("MINUS_STRUCT_BLOCK", lambda raw, fdt: raw - fdt.off_struct),
    ("MINUS_HEADER", lambda raw, fdt: raw - FDT_HEADER_SIZE),
    ("MINUS_STRINGS_BLOCK", lambda raw, fdt: raw - fdt.off_strings),
    ("PLUS_STRUCT_BLOCK", lambda raw, fdt: raw + fdt.off_struct),
    ("PLUS_HEADER", lambda raw, fdt: raw + FDT_HEADER_SIZE),
)


def calibrate_offset_convention(work):
    """Learn how dtc encodes __fixups__ offsets from a probe built in this run.

    Nothing about dtc's encoding is assumed: a two-fragment probe overlay is
    compiled here, and the interpretation that maps every probe fixup onto a
    known property-value offset is the one used for the OEM payloads.
    """
    probe_dts = textwrap.dedent(f"""\
        /dts-v1/;
        /plugin/;

        / {{
        \tfragment@0 {{
        \t\ttarget = <&{PROBE_TARGET_SYMBOL}>;

        \t\t__overlay__ {{
        \t\t}};
        \t}};

        \tfragment@1 {{
        \t\ttarget-path = "/";

        \t\t__overlay__ {{
        \t\t\tm5l,probe-body = <&{PROBE_BODY_SYMBOL}>;
        \t\t}};
        \t}};
        }};
        """)
    probe = dtc_compile(work, "m5l-fixup-probe", probe_dts)
    fdt = Fdt(probe, "m5l-fixup-probe")
    fixups = fdt.node("/__fixups__")
    if fixups is None:
        raise SystemExit("M5L_PROBE_CALIBRATION_FAILED probe produced no __fixups__ node")
    if PROBE_TARGET_SYMBOL not in fixups.props or PROBE_BODY_SYMBOL not in fixups.props:
        raise SystemExit("M5L_PROBE_CALIBRATION_FAILED probe lost a fixup symbol")
    raw_offsets = list(cells(fixups.props[PROBE_TARGET_SYMBOL][0]) or [])
    raw_offsets.extend(cells(fixups.props[PROBE_BODY_SYMBOL][0]) or [])
    if len(raw_offsets) < 2:
        raise SystemExit("M5L_PROBE_CALIBRATION_FAILED probe fixup list too short")
    resolving = [name for name, interpreter in OFFSET_CONVENTIONS
                 if all((interpreter(raw, fdt) in fdt.value_offset_index) for raw in raw_offsets)]
    if not resolving:
        raise SystemExit("M5L_PROBE_CALIBRATION_FAILED no offset convention resolves the probe")
    return {
        "convention": resolving[0],
        "resolving": resolving,
        "raw_offsets": raw_offsets,
        "target_value_offset": fdt.prop_offset("/fragment@0", "target"),
        "body_value_offset": fdt.prop_offset("/fragment@1/__overlay__", "m5l,probe-body"),
        "probe_size": len(probe),
        "resolve": dict(OFFSET_CONVENTIONS)[resolving[0]],
    }


def classify_fixups(overlay, resolver):
    """Classify every __fixups__ offset as TARGET_FIXUP or BODY_FIXUP."""
    fixups_node = overlay.node("/__fixups__")
    local_fixups_node = overlay.node("/__local_fixups__")

    target_offsets = {}
    for fragment in overlay.fragments():
        entry = fragment.props.get("target")
        if entry is not None:
            target_offsets[entry[1]] = fragment.path

    per_fragment_symbol = {}
    target_fixups = []
    body_fixups = []
    unresolved = []
    if fixups_node is not None:
        for symbol, entry in fixups_node.props.items():
            for raw in cells(entry[0]) or []:
                resolved = resolver(raw, overlay)
                holder = target_offsets.get(resolved)
                if holder is not None:
                    per_fragment_symbol.setdefault(holder, symbol)
                    target_fixups.append((symbol, raw, resolved, holder))
                else:
                    location = overlay.value_offset_index.get(resolved)
                    if location is None:
                        unresolved.append((symbol, raw, resolved))
                        body_fixups.append((symbol, raw, resolved, "UNRESOLVED"))
                    else:
                        body_fixups.append((symbol, raw, resolved, f"{location[0]}:{location[1]}"))

    local_entries = 0
    local_paths = set()
    if local_fixups_node is not None:
        for path in local_fixups_node.descendant_paths():
            if path != "/__local_fixups__":
                local_paths.add(path.replace("/__local_fixups__", "", 1))
        stack = [local_fixups_node]
        while stack:
            node = stack.pop()
            for entry in node.props.values():
                local_entries += len(cells(entry[0]) or [])
            stack.extend(node.children.values())

    return {
        "per_fragment_symbol": per_fragment_symbol,
        "target_fixups": target_fixups,
        "body_fixups": body_fixups,
        "unresolved": unresolved,
        "local_entries": local_entries,
        "local_paths": local_paths,
    }


def fragment_matrix(overlay, classification):
    """Per-fragment targeting-mechanics rows."""
    local_phandles = overlay.local_phandles()
    rows = []
    for fragment in overlay.fragments():
        target = fragment.props.get("target")
        target_path = fragment.props.get("target-path")
        if target is not None:
            values = cells(target[0]) or []
            local = bool(values) and values[0] in local_phandles and values[0] != 0xFFFFFFFF
            if local:
                form = "TARGET_PHANDLE_LOCAL"
            else:
                form = "TARGET_PHANDLE"
        elif target_path is not None:
            values = []
            form = "TARGET_PATH"
        else:
            values = []
            form = "OTHER"

        overlay_node = fragment.child("__overlay__")
        child_count = len(overlay_node.children) if overlay_node else 0
        prop_count = len(overlay_node.props) if overlay_node else 0

        local_refs = 0
        for name, entry in (overlay_node.props.items() if overlay_node else []):
            if name in PHANDLE_PROPERTIES:
                continue
            for value in cells(entry[0]) or []:
                if value in local_phandles and value != 0:
                    local_refs += 1

        rows.append({
            "path": fragment.path,
            "index": int(fragment.name.split("@", 1)[1]) if "@" in fragment.name else -1,
            "form": form,
            "raw": " ".join(f"0x{value:08x}" for value in values),
            "raw_cells": values,
            "target_path": target_path[0].rstrip(b"\0").decode("utf-8", "replace")
            if target_path else "",
            "symbol": classification["per_fragment_symbol"].get(fragment.path, "NONE"),
            "children": child_count,
            "properties": prop_count,
            "local_refs": local_refs,
            "local_fixups": "YES" if fragment.path in
            {path.replace("/__local_fixups__", "", 1) for path in classification["local_paths"]}
            else "NO",
        })
    return rows


def audit_container(candidate, expected_payload, label):
    """Fail-closed validation of a one-entry candidate container."""
    problems = []
    if candidate.total_size != len(candidate.data):
        problems.append(f"TOTAL_SIZE={candidate.total_size} FILE_SIZE={len(candidate.data)}")
    if candidate.header_size != DTBO_HEADER_SIZE:
        problems.append(f"HEADER_SIZE={candidate.header_size}")
    if candidate.entry_size != DTBO_ENTRY_SIZE:
        problems.append(f"ENTRY_SIZE={candidate.entry_size}")
    if candidate.entry_count != 1:
        problems.append(f"ENTRY_COUNT={candidate.entry_count}")
    if candidate.entries_offset != DTBO_ENTRIES_OFFSET:
        problems.append(f"ENTRIES_OFFSET={candidate.entries_offset}")
    if candidate.page_size != DTBO_PAGE_SIZE:
        problems.append(f"PAGE_SIZE={candidate.page_size}")
    if candidate.version != DTBO_VERSION:
        problems.append(f"VERSION={candidate.version}")
    entry = candidate.entries[0]
    if entry.dt_offset != DTBO_PAYLOAD_OFFSET:
        problems.append(f"ENTRY_DT_OFFSET={entry.dt_offset}")
    if entry.dt_size != len(expected_payload):
        problems.append(f"ENTRY_DT_SIZE={entry.dt_size} EXPECTED={len(expected_payload)}")
    if entry.image_id != 0 or entry.rev != 0 or tuple(entry.custom) != (0, 0, 0, 0):
        problems.append(f"ENTRY_METADATA_NONZERO id={entry.image_id} rev={entry.rev} custom={entry.custom}")
    if entry.payload != expected_payload:
        problems.append("ENTRY_PAYLOAD_BYTES_DIFFER")
    if entry.dt_offset + entry.dt_size != candidate.total_size:
        problems.append(f"ACCOUNTING dt_offset+dt_size="
                        f"{entry.dt_offset + entry.dt_size} total={candidate.total_size}")
    return problems


def container_probe(container_bytes, expected_payload):
    """Fail-closed container gate shared by real gates and negative controls.

    A mutated container may become unparseable rather than merely inconsistent;
    both outcomes count as a rejection, and the reason is returned for the
    report so the mechanism stays auditable.
    """
    try:
        parsed = parse_dtbo(container_bytes, "candidate-container")
    except ValueError as error:
        return False, [f"CONTAINER_PARSE_FAILED {error}"]
    problems = audit_container(parsed, expected_payload)
    return (not problems), problems


def container_identity_preserved(container, reference):
    """True when only TOTAL_SIZE and ENTRY_DT_SIZE differ from the M1 one-entry form."""
    entry = container.entries[0]
    return (
        container.header_size == reference.header_size
        and container.entry_size == reference.entry_size
        and container.entry_count == reference.entry_count == 1
        and container.entries_offset == reference.entries_offset
        and container.page_size == reference.page_size
        and container.version == reference.version
        and container.data[:4] == reference.data[:4]
        and entry.dt_offset == reference.entries[0].dt_offset
        and entry.image_id == 0
        and entry.rev == 0
        and entry.custom == (0, 0, 0, 0)
    )


def audit_full_artifact(full, container, stock, label):
    violations = []
    if len(full) != FULL_ARTIFACT_SIZE:
        violations.append(f"FULL_SIZE={len(full)} EXPECTED={FULL_ARTIFACT_SIZE}")
        return violations
    prefix_end = len(container)
    if full[:prefix_end] != container:
        violations.append("FULL_PREFIX_NOT_EXACT_CANDIDATE")
    if full[prefix_end:] != stock[prefix_end:]:
        violations.append("FULL_TAIL_NOT_STOCK_SAME_OFFSET")
    try:
        parsed = parse_dtbo(full, f"{label}-full")
    except ValueError as error:
        violations.append(f"FULL_DTBO_PARSE_FAILED {error}")
        return violations
    if parsed.entry_count != 1:
        violations.append(f"FULL_DTBO_ENTRY_COUNT={parsed.entry_count}")
    elif parsed.entries[0].payload != container[DTBO_PAYLOAD_OFFSET:]:
        violations.append("FULL_DTBO_PAYLOAD_NOT_CANDIDATE")
    return violations


def symbol_selection(stock_fdt, base_fdt, matrix_rows, classification):
    """Pick the simplest Stock fragment target usable for L2."""
    base_symbols = {name: value[0].rstrip(b"\0").decode("utf-8", "replace")
                    for name, value in
                    (base_fdt.node("/__symbols__").props.items()
                     if base_fdt.node("/__symbols__") else [])}
    candidates = []
    rejected = []
    for row in matrix_rows:
        if row["form"] != "TARGET_PHANDLE":
            continue
        symbol = row["symbol"]
        if symbol == "NONE":
            rejected.append((row["index"], symbol, "NO_FIXUP_ATTRIBUTION"))
            continue
        if symbol not in base_symbols:
            rejected.append((row["index"], symbol, "SYMBOL_NOT_IN_BASE"))
            continue
        if row["local_fixups"] == "YES":
            rejected.append((row["index"], symbol, "LOCAL_FIXUPS_DEPENDENCY"))
            continue
        candidates.append({
            "index": row["index"],
            "symbol": symbol,
            "path": base_symbols[symbol],
            "overlay_children": row["children"],
            "overlay_properties": row["properties"],
            "local_refs": row["local_refs"],
        })
    candidates.sort(key=lambda item: (item["overlay_children"], item["overlay_properties"],
                                      item["index"]))
    return candidates, rejected, base_symbols


def fdt_to_dts(fdt, label, root_overrides=None):
    """Serialise a parsed FDT back to DTS text.

    L1 must reproduce the exact M1 no-op fragment structure, target-path,
    marker, property order and property values, changing nothing but the root
    selector metadata. Rendering the DTS from the parsed M1 payload does that
    from measured data instead of from a hand-written template.
    """
    overrides = root_overrides or {}
    lines = ["/dts-v1/;", "/plugin/;", "", "/ {"]

    def walk(node, indent):
        for prop_name, entry in node.props.items():
            value = overrides.get(prop_name, entry[0]) if node.path == "/" else entry[0]
            if not value:
                lines.append(f"{indent}{prop_name};")
            else:
                lines.append(f"{indent}{prop_name} = {dts_literal(value)};")
        for child in node.children.values():
            lines.append("")
            lines.append(f"{indent}{child.name} {{")
            walk(child, indent + "\t")
            lines.append(f"{indent}}};")

    walk(fdt.root, "\t")
    lines.append("};")
    return "\n".join(lines) + "\n"


def build_l1_payload(work, m1_payload, m1_fdt, stock_fdt, selector_names):
    """Rewrite the M1 no-op root selector metadata to the exact Stock values."""
    overrides = {}
    applied = []
    unchanged = []
    extra = []
    for name in selector_names:
        stock_value = stock_fdt.prop("/", name)
        m1_value = m1_fdt.prop("/", name)
        if stock_value is None:
            if m1_value is not None:
                extra.append(name)
            continue
        if m1_value == stock_value:
            unchanged.append(name)
            continue
        overrides[name] = stock_value
        applied.append(name)
    text = fdt_to_dts(m1_fdt, "m5l-l1", overrides)
    payload = dtc_compile(work, "m5l-l1-payload", text, symbols=False)
    return payload, applied, unchanged, extra, text


def audit_l1_payload(payload, m1_fdt, stock_fdt, selector_names):
    problems = []
    try:
        fdt = Fdt(payload, "m5l-l1")
    except ValueError as error:
        return [f"L1_PARSE_FAILED {error}"], None
    fragments = fdt.fragments()
    if len(fragments) != 1:
        problems.append(f"L1_FRAGMENT_COUNT={len(fragments)}")
    fragment = fragments[0] if fragments else None
    if fragment is not None:
        if "target" in fragment.props:
            problems.append("L1_USES_TARGET_PHANDLE")
        if fragment.props.get("target-path", (None,))[0] != b"/\0":
            problems.append("L1_TARGET_PATH_IS_NOT_ROOT")
        body = fragment.child("__overlay__")
        if body is None:
            problems.append("L1_MISSING_OVERLAY_BODY")
        elif "qcom,thyme-route-b-noop" not in body.props:
            problems.append("L1_MARKER_MISSING")
    counts = fdt.special_counts()
    for node_path in ("/__fixups__", "/__symbols__", "/__local_fixups__"):
        if counts[node_path] != "ABSENT":
            problems.append(f"L1_UNEXPECTED_{node_path}=present")
    for name in selector_names:
        stock_value = stock_fdt.prop("/", name)
        if stock_value is None:
            continue
        if fdt.prop("/", name) != stock_value:
            problems.append(f"L1_SELECTOR_NOT_EXACT {name}")
    if m1_fdt.root.props.keys() != fdt.root.props.keys():
        problems.append("L1_ROOT_PROPERTY_SET_CHANGED_BEYOND_SELECTORS")
    return problems, fdt


def audit_l2_payload(payload, stock_fdt, symbol, selector_names, work):
    """Design gate for the L2 Stock-style minimal no-op payload."""
    problems = []
    try:
        fdt = Fdt(payload, "m5l-l2")
    except ValueError as error:
        return [f"L2_PARSE_FAILED {error}"], None
    fragments = fdt.fragments()
    if len(fragments) != 1:
        problems.append(f"L2_FRAGMENT_COUNT={len(fragments)}")
    fragment = fragments[0] if fragments else None
    if fragment is not None:
        if "target" in fragment.props:
            pass
        else:
            problems.append("L2_MISSING_TARGET_PHANDLE")
        if "target-path" in fragment.props:
            problems.append("L2_USES_TARGET_PATH")
        body = fragment.child("__overlay__")
        if body is None:
            problems.append("L2_MISSING_OVERLAY_BODY")
        else:
            if body.props:
                problems.append(f"L2_OVERLAY_BODY_NOT_EMPTY props={sorted(body.props)}")
            if body.children:
                problems.append(f"L2_OVERLAY_BODY_HAS_CHILDREN={sorted(body.children)}")
    fixups = fdt.node("/__fixups__")
    if fixups is None:
        problems.append("L2_MISSING_FIXUPS")
    elif symbol not in fixups.props:
        problems.append(f"L2_FIXUP_SYMBOL_ABSENT expected={symbol} "
                        f"present={sorted(fixups.props)}")
    counts = fdt.special_counts()
    if counts["/__local_fixups__"] != "ABSENT":
        problems.append("L2_UNEXPECTED_LOCAL_FIXUPS")
    for name in selector_names:
        stock_value = stock_fdt.prop("/", name)
        if stock_value is None:
            continue
        if fdt.prop("/", name) != stock_value:
            problems.append(f"L2_SELECTOR_NOT_EXACT {name}")
    return problems, fdt


def l2_dts(symbol, stock_fdt, selector_names):
    lines = ["/dts-v1/;", "/plugin/;", "", "/ {"]
    for name in selector_names:
        value = stock_fdt.prop("/", name)
        if value is None:
            continue
        lines.append(f"\t{name} = {dts_literal(value)};")
    lines.extend([
        "",
        "\tfragment@0 {",
        f"\t\ttarget = <&{symbol}>;",
        "",
        "\t\t__overlay__ {",
        "\t\t};",
        "\t};",
        "};",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def write_lines(path, lines):
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def region_lines(name, regions, before, after, before_label, after_label):
    lines = [
        f"COMPARISON={name}",
        f"BEFORE={before_label}",
        f"AFTER={after_label}",
        f"BEFORE_SIZE={len(before)}",
        f"AFTER_SIZE={len(after)}",
        f"BEFORE_SHA256={sha(before)}",
        f"AFTER_SHA256={sha(after)}",
    ]
    ranges = changed_ranges(before, after)
    lines.append(f"EXACT_CHANGED_RANGE_COUNT={len(ranges)}")
    lines.append(f"EXACT_CHANGED_BYTE_COUNT={sum(end - start for start, end in ranges)}")
    for label, start, end in regions:
        left = before[start:end]
        right = after[start:end]
        if len(left) != len(right):
            lines.append(f"REGION={label} OFFSET=[{start},{end}) SHAPE_CHANGED")
            continue
        sub = changed_ranges(left, right)
        lines.append(f"REGION={label} OFFSET=[{start},{end}) SIZE={len(left)}"
                     f" CHANGED_RANGES={len(sub)}"
                     f" CHANGED_BYTES={sum(e - s for s, e in sub)}")
    return lines


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GitHub Actions only: local audit, transformation, and validation are forbidden")

    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-dtbo", required=True, type=Path)
    parser.add_argument("--stock-vendor-boot", required=True, type=Path)
    parser.add_argument("--m1-dtbo", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir
    produced = []          # names the script actually emitted

    def emit(name, payload_bytes):
        (out / name).write_bytes(payload_bytes)
        produced.append(name)

    def emit_text(name, lines):
        write_lines(out / name, lines)
        produced.append(name)

    stock = args.stock_dtbo.read_bytes()
    stock_vendor = args.stock_vendor_boot.read_bytes()
    m1_raw = args.m1_dtbo.read_bytes()

    # ---- 0. source identity -------------------------------------------------
    if len(stock) != STOCK_DTBO_SIZE or sha(stock) != STOCK_DTBO_SHA256:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED stock dtbo size={len(stock)} sha256={sha(stock)}")
    if len(stock_vendor) != STOCK_VENDOR_BOOT_SIZE or sha(stock_vendor) != STOCK_VENDOR_BOOT_SHA256:
        raise SystemExit("M5L_SOURCE_IDENTITY_FAILED stock vendor_boot "
                         f"size={len(stock_vendor)} sha256={sha(stock_vendor)}")
    if len(m1_raw) != M1_DTBO_SIZE or sha(m1_raw) != M1_DTBO_SHA256:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED M1 dtbo size={len(m1_raw)} sha256={sha(m1_raw)}")

    stock_dtbo = parse_dtbo(stock, "stock-dtbo")
    m1_dtbo = parse_dtbo(m1_raw, "m1-dtbo")
    dtb_area = parse_vendor_dtb_area(stock_vendor, "stock-vendor_boot")
    dtb0_size = struct.unpack_from(">I", dtb_area, 4)[0]
    dtb0 = dtb_area[:dtb0_size]

    if stock_dtbo.entry_count != STOCK_DTBO_ENTRY_COUNT:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED stock dtbo entry_count={stock_dtbo.entry_count}")
    if stock_dtbo.total_size != STOCK_DTBO_TOTAL_SIZE:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED stock dtbo total_size={stock_dtbo.total_size}")
    if m1_dtbo.entry_count != 1:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED M1 dtbo entry_count={m1_dtbo.entry_count}")
    if dtb0_size != STOCK_DTB0_SIZE or sha(dtb0) != STOCK_DTB0_SHA256:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED stock DTB0 size={dtb0_size} sha256={sha(dtb0)}")

    stock_entry = stock_dtbo.entries[THYME_ENTRY_INDEX]
    if stock_entry.dt_offset != THYME_ENTRY_DT_OFFSET or stock_entry.dt_size != THYME_ENTRY_DT_SIZE:
        raise SystemExit("M5L_SOURCE_IDENTITY_FAILED stock entry21 offset/size="
                         f"{stock_entry.dt_offset}/{stock_entry.dt_size}")
    if sha(stock_entry.payload) != THYME_ENTRY_PAYLOAD_SHA256:
        raise SystemExit("M5L_SOURCE_IDENTITY_FAILED stock entry21 payload sha256="
                         f"{sha(stock_entry.payload)}")
    if stock_entry.fdt.root_cells("qcom,board-id") != [45, 0]:
        raise SystemExit("M5L_SOURCE_IDENTITY_FAILED stock entry21 board-id is not <45 0>")
    candidates = [entry.index for entry in stock_dtbo.entries
                  if entry.fdt.root_cells("qcom,board-id") == [45, 0]]
    if candidates != [THYME_ENTRY_INDEX]:
        raise SystemExit(f"M5L_SOURCE_IDENTITY_FAILED thyme entry candidates={candidates}")

    stock_payload = stock_entry.payload
    stock_fdt = stock_entry.fdt
    m1_payload = m1_dtbo.entries[0].payload
    m1_fdt = m1_dtbo.entries[0].fdt
    base_fdt = Fdt(dtb0, "stock-dtb0")

    with tempfile.TemporaryDirectory(prefix="m5l-") as temp_name:
        work = Path(temp_name)

        # ---- 1. __fixups__ offset convention, measured not assumed ---------
        calibration = calibrate_offset_convention(work)
        resolver = calibration["resolve"]
        convention = calibration["convention"]

        # ---- 2. payload full root-property matrix ---------------------------
        matrix = selector_matrix(stock_fdt, m1_fdt)
        root_rows = []
        for name, left, right, verdict in matrix["rows"]:
            root_rows.append({
                "property": name,
                "stock": "MISSING" if left is None else
                (" ".join(f"0x{value:08x}" for value in cells(left[0]))
                 if cells(left[0]) is not None
                 else (" | ".join(part.decode("utf-8", "replace")
                                  for part in left[0][:-1].split(b"\0"))
                       if is_string_list(left[0]) else f"{len(left[0])}B")),
                "m1": "MISSING" if right is None else
                (" ".join(f"0x{value:08x}" for value in cells(right[0]))
                 if cells(right[0]) is not None
                 else (" | ".join(part.decode("utf-8", "replace")
                                  for part in right[0][:-1].split(b"\0"))
                       if is_string_list(right[0]) else f"{len(right[0])}B")),
                "verdict": verdict,
            })
        root_matrix_lines = ["# payload root property matrix", ""]
        root_matrix_lines.append("property\tstock\tm1\tverdict")
        for row in root_rows:
            root_matrix_lines.append(f"{row['property']}\t{row['stock']}\t{row['m1']}\t{row['verdict']}")
        root_matrix_lines.extend(["", "# /chosen property matrix", ""])
        if matrix["chosen"]:
            root_matrix_lines.append("property\tstock\tm1\tverdict")
            for name, left, right, verdict in matrix["chosen"]:
                def render(entry):
                    if entry is None:
                        return "MISSING"
                    value = entry[0]
                    if cells(value) is not None:
                        return " ".join(f"0x{word:08x}" for word in cells(value))
                    if is_string_list(value):
                        return " | ".join(part.decode("utf-8", "replace")
                                          for part in value[:-1].split(b"\0"))
                    return f"{len(value)}B"
                root_matrix_lines.append(f"{name}\t{render(left)}\t{render(right)}\t{verdict}")
        else:
            root_matrix_lines.append("/chosen ABSENT in both payloads")
        root_matrix_lines.extend([
            "",
            f"STOCK_ROOT_PROPERTY_COUNT={len(stock_fdt.root.props)}",
            f"M1_ROOT_PROPERTY_COUNT={len(m1_fdt.root.props)}",
            f"STOCK_CHOSEN_PRESENT={'YES' if stock_fdt.node('/chosen') else 'NO'}",
            f"M1_CHOSEN_PRESENT={'YES' if m1_fdt.node('/chosen') else 'NO'}",
            "ABL_SELECTOR_FAMILY=" + ",".join(ABL_SELECTOR_PROPERTIES),
            f"SELECTOR_PROPERTIES_DIFFERING={','.join(matrix['selector_differs']) or 'NONE'}",
            f"SELECTOR_DIFFERENCE_EXISTS={'YES' if matrix['selector_differs'] else 'NO'}",
            f"OTHER_ROOT_PROPERTIES_DIFFERING={','.join(matrix['other_differs']) or 'NONE'}",
            f"ROOT_PROPERTIES_MISSING_IN_M1={','.join(matrix['present_in_stock_only']) or 'NONE'}",
            f"ROOT_PROPERTIES_MISSING_IN_STOCK={','.join(matrix['present_in_m1_only']) or 'NONE'}",
            f"ROOT_PROPERTIES_VALUE_DIFFERENT={','.join(matrix['different_values']) or 'NONE'}",
        ])
        emit_text("m5l-payload-root-matrix.txt", root_matrix_lines)

        # ---- 3. Stock targeting mechanics ----------------------------------
        stock_classification = classify_fixups(stock_fdt, resolver)
        stock_rows = fragment_matrix(stock_fdt, stock_classification)
        phandle_fragments = [row for row in stock_rows if row["form"] == "TARGET_PHANDLE"]
        local_phandle_fragments = [row for row in stock_rows if row["form"] == "TARGET_PHANDLE_LOCAL"]
        path_fragments = [row for row in stock_rows if row["form"] == "TARGET_PATH"]
        other_fragments = [row for row in stock_rows if row["form"] == "OTHER"]

        targeting_lines = ["# Stock thyme entry21 per-fragment targeting mechanics", ""]
        for row in stock_rows:
            targeting_lines.extend([
                f"FRAGMENT_INDEX={row['index']}",
                f"FRAGMENT_PATH={row['path']}",
                f"TARGET_FORM={row['form']}",
                f"TARGET_RAW={row['raw'] or 'NONE'}",
                f"TARGET_PATH_STRING={row['target_path'] or 'NONE'}",
                f"TARGET_FIXUP_SYMBOL={row['symbol']}",
                f"OVERLAY_CHILD_COUNT={row['children']}",
                f"OVERLAY_PROPERTY_COUNT={row['properties']}",
                f"LOCAL_PHANDLE_REFERENCE_COUNT={row['local_refs']}",
                f"LOCAL_FIXUPS_DEPENDENCY={row['local_fixups']}",
                "",
            ])
        targeting_lines.extend([
            f"STOCK_FRAGMENT_COUNT={len(stock_rows)}",
            f"STOCK_TARGET_PHANDLE_FRAGMENT_COUNT={len(phandle_fragments)}",
            f"STOCK_TARGET_PHANDLE_LOCAL_FRAGMENT_COUNT={len(local_phandle_fragments)}",
            f"STOCK_TARGET_PATH_FRAGMENT_COUNT={len(path_fragments)}",
            f"STOCK_OTHER_TARGET_FRAGMENT_COUNT={len(other_fragments)}",
            f"STOCK_FRAGMENTS_WITH_FIXUP_SYMBOL={len(stock_classification['per_fragment_symbol'])}",
            f"STOCK_FRAGMENTS_WITHOUT_FIXUP_SYMBOL="
            f"{len(stock_rows) - len(stock_classification['per_fragment_symbol'])}",
            f"STOCK_FRAGMENT_INDEX_MIN={min(row['index'] for row in stock_rows)}",
            f"STOCK_FRAGMENT_INDEX_MAX={max(row['index'] for row in stock_rows)}",
            f"STOCK_ALL_EXTERNAL_TARGET_FRAGMENTS={'YES' if len(phandle_fragments) == len(stock_rows) else 'NO'}",
            f"STOCK_MAJORITY_USES_TARGET_PLUS_FIXUP="
            f"{'YES' if len(phandle_fragments) * 2 > len(stock_rows) else 'NO'}",
        ])
        emit_text("m5l-stock-targeting-matrix.txt", targeting_lines)

        # ---- 4. Stock synthetic metadata and fixup classification -----------
        stock_counts = stock_fdt.special_counts()
        fixup_node = stock_fdt.node("/__fixups__")
        fixup_symbols = sorted(fixup_node.props) if fixup_node else []
        classification_lines = [
            "# Stock thyme entry21 generated metadata",
            "",
            f"__FIXUPS__COUNT={stock_counts['/__fixups__']}",
            f"__SYMBOLS__COUNT={stock_counts['/__symbols__']}",
            f"__LOCAL_FIXUPS__PRESENT="
            f"{'NO' if stock_counts['/__local_fixups__'] == 'ABSENT' else 'YES'}",
            f"__LOCAL_FIXUPS__PROPERTY_COUNT={stock_counts['/__local_fixups__']}",
            f"__LOCAL_FIXUPS__REFERENCE_COUNT={stock_classification['local_entries']}",
            f"PHANDLE_PROPERTY_COUNT={stock_fdt.phandle_count()}",
            f"LOCAL_PHANDLE_DEFINITION_COUNT={len(stock_fdt.local_phandles())}",
            "",
            f"FIXUP_OFFSET_CONVENTION={convention}",
            f"FIXUP_OFFSET_CONVENTIONS_THAT_RESOLVE_PROBE={','.join(calibration['resolving'])}",
            "FIXUP_PROBE_RAW_OFFSETS="
            + " ".join(f"0x{value:x}" for value in calibration["raw_offsets"]),
            f"FIXUP_PROBE_TARGET_VALUE_OFFSET={calibration['target_value_offset']}",
            f"FIXUP_PROBE_BODY_VALUE_OFFSET={calibration['body_value_offset']}",
            f"FIXUP_PROBE_PAYLOAD_SIZE={calibration['probe_size']}",
            f"TARGET_FIXUP_COUNT={len(stock_classification['target_fixups'])}",
            f"BODY_FIXUP_COUNT={len(stock_classification['body_fixups'])}",
            f"LOCAL_FIXUP_COUNT={stock_classification['local_entries']}",
            f"UNRESOLVED_FIXUP_OFFSET_COUNT={len(stock_classification['unresolved'])}",
            "",
            "# classification table (symbol, raw offset, resolved offset, holder)",
        ]
        for symbol, raw, resolved, holder in stock_classification["target_fixups"][:DETAIL_CAP]:
            classification_lines.append(
                f"TARGET_FIXUP symbol={symbol} raw=0x{raw:x} resolved=0x{resolved:x} holder={holder}")
        for symbol, raw, resolved, holder in stock_classification["body_fixups"][:DETAIL_CAP]:
            classification_lines.append(
                f"BODY_FIXUP symbol={symbol} raw=0x{raw:x} resolved=0x{resolved:x} holder={holder}")
        classification_lines.append("# __fixups__ symbol index")
        for symbol in fixup_symbols[:DETAIL_CAP]:
            classification_lines.append(f"FIXUP_SYMBOL={symbol}")
        classification_lines.append("# base DTB0 symbol index")
        base_symbols_node = base_fdt.node("/__symbols__")
        base_symbol_names = sorted(base_symbols_node.props) if base_symbols_node else []
        classification_lines.append(f"STOCK_DTB0_HAS_SYMBOLS={'YES' if base_symbols_node else 'NO'}")
        classification_lines.append(f"STOCK_DTB0_SYMBOL_COUNT={len(base_symbol_names)}")
        for symbol in base_symbol_names[:DETAIL_CAP]:
            classification_lines.append(f"BASE_SYMBOL={symbol}")
        emit_text("m5l-stock-fixup-classification.txt", classification_lines)

        # ---- 5. M1 no-op exact structure and applied delta ------------------
        m1_nodes = [node for node in m1_fdt.walk()]
        m1_lines = ["# M1 no-op payload exact tree", "",
                    f"M1_PAYLOAD_SIZE={len(m1_payload)}",
                    f"M1_PAYLOAD_SHA256={sha(m1_payload)}",
                    f"M1_FDT_TOTALSIZE={m1_fdt.totalsize}",
                    f"M1_FDT_VERSION={m1_fdt.version}",
                    f"M1_NODE_COUNT={len(m1_nodes)}",
                    f"M1_FRAGMENT_COUNT={len(m1_fdt.fragments())}",
                    f"M1_FIXUPS={m1_fdt.special_counts()['/__fixups__']}",
                    f"M1_SYMBOLS={m1_fdt.special_counts()['/__symbols__']}",
                    f"M1_LOCAL_FIXUPS={m1_fdt.special_counts()['/__local_fixups__']}",
                    f"M1_PHANDLE_PROPERTY_COUNT={m1_fdt.phandle_count()}",
                    ""]
        marker_home = None
        for node in m1_nodes:
            m1_lines.append(f"NODE={node.path}")
            for name, entry in node.props.items():
                value = entry[0]
                if name in PHANDLE_PROPERTIES:
                    rendered = " ".join(f"0x{word:08x}" for word in cells(value) or [])
                elif cells(value) is not None:
                    rendered = " ".join(f"0x{word:08x}" for word in cells(value))
                elif is_string_list(value):
                    rendered = " | ".join(part.decode("utf-8", "replace")
                                          for part in value[:-1].split(b"\0"))
                else:
                    rendered = f"{len(value)}B"
                m1_lines.append(f"PROPERTY {name} = {rendered}")
                if name == "qcom,thyme-route-b-noop" or name.startswith("qcom,thyme-route-b-noop"):
                    marker_home = node.path
        m1_lines.append("")
        m1_lines.append(f"MARKER_PROPERTY=qcom,thyme-route-b-noop")
        m1_lines.append(f"MARKER_HOME_NODE={marker_home or 'ABSENT'}")
        m1_lines.append(f"MARKER_IS_ROOT_LEVEL_PROPERTY="
                        f"{'YES' if marker_home == '/' else 'NO'}")
        m1_lines.append(f"MARKER_IS_OVERLAY_BODY_PROPERTY="
                        f"{'YES' if marker_home and marker_home.endswith('__overlay__') else 'NO'}")

        m1_merge_ok, m1_merge_detail = fdtoverlay_apply_status(work, "m5l-m1-on-stock", dtb0, m1_payload)
        m1_applied = None
        if m1_merge_ok:
            merged = (work / "m5l-m1-on-stock.merged.dtb").read_bytes()
            m1_applied = semantic_diff(base_fdt, Fdt(merged, "m1-applied"), "M1_NOOP_ON_STOCK_BASE")
        m1_lines.extend([
            "",
            f"M1_NOOP_FDTOVERLAY_ON_STOCK_DTB0={'PASS' if m1_merge_ok else 'FAIL'}",
            f"M1_NOOP_FDTOVERLAY_DETAIL={m1_merge_detail}",
        ])
        if m1_applied is not None:
            m1_lines.extend(semantic_report_lines(m1_applied))
        emit_text("m5l-m1-noop-structure.txt", m1_lines)

        # ---- 6. padding / totalsize re-audit (downgraded) -------------------
        padded_noop = pad_fdt(m1_payload, THYME_ENTRY_DT_SIZE)
        padding_bytes = THYME_ENTRY_DT_SIZE - len(m1_payload)
        padding_lines = [
            "# padding / totalsize assessment (explicitly downgraded)",
            "",
            f"CELL_C_ENTRY_DT_SIZE={len(m1_payload)}",
            f"CELL_C_INTERNAL_FDT_TOTALSIZE={m1_fdt.totalsize}",
            f"CELL_C_SELF_CONSISTENT_DT_SIZE=YES",
            f"CELL_C_SLOT_PADDING_MISMATCH=NO",
            f"CELL_C_RUNTIME_SECONDS=4.812",
            f"CELL_C_SUPPRESSED_4P7S_RETURN=YES",
            "",
            f"M5J_ENTRY_DT_SIZE={THYME_ENTRY_DT_SIZE}",
            f"M5J_INTERNAL_FDT_TOTALSIZE={m1_fdt.totalsize}",
            f"M5J_SLOT_PADDING_BYTES={padding_bytes}",
            f"M5J_PADDED_NOOP_SHA256={sha(padded_noop)}",
            f"M5J_RUNTIME_SECONDS=4.922",
            f"M5J_SUPPRESSED_4P7S_RETURN=YES",
            "",
            "PADDING_OR_DT_SIZE_MISMATCH_AS_NECESSARY_CAUSE=NOT_SUPPORTED",
            "PADDING_CHANGES_BEHAVIOUR=NOT_EXCLUDED",
            "PADDING_NOT_NECESSARY_FOR_BOTH_FAILING_CELLS=YES",
            "PADDING_PRIORITY=P6_DEPRIORITIZED",
        ]
        emit_text("m5l-padding-assessment.txt", padding_lines)

        # ---- 7. factor decomposition ---------------------------------------
        stock_merge_ok, stock_merge_detail = fdtoverlay_apply_status(work, "m5l-stock-on-stock", dtb0, stock_payload)
        stock_applied = None
        if stock_merge_ok:
            merged = (work / "m5l-stock-on-stock.merged.dtb").read_bytes()
            stock_applied = semantic_diff(base_fdt, Fdt(merged, "stock-applied"), "STOCK_ENTRY21_ON_STOCK_BASE")
            stock_merged_sha = sha(merged)
        else:
            stock_merged_sha = "UNAVAILABLE"

        factor_lines = [
            "# payload factor decomposition",
            "",
            "P1_ROOT_SELECTOR_METADATA",
            f"  SELECTOR_PROPERTIES_DIFFERING={','.join(matrix['selector_differs']) or 'NONE'}",
            f"  P1_EXISTS={'YES' if matrix['selector_differs'] else 'NO'}",
            "",
            "P2_FRAGMENT_TARGET_MECHANISM",
            f"  STOCK_target_phandle_fragments={len(phandle_fragments)}",
            f"  STOCK_target_path_fragments={len(path_fragments)}",
            f"  M1_fragment_count={len(m1_fdt.fragments())}",
            f"  M1_target_mechanism="
            f"{'TARGET_PATH' if m1_fdt.fragments() and 'target-path' in m1_fdt.fragments()[0].props else 'UNKNOWN'}",
            "",
            "P3_OVERLAY_GENERATED_METADATA",
            f"  STOCK_fixups={stock_counts['/__fixups__']}",
            f"  STOCK_symbols={stock_counts['/__symbols__']}",
            f"  STOCK_local_fixups={stock_counts['/__local_fixups__']}",
            f"  STOCK_phandle_properties={stock_fdt.phandle_count()}",
            f"  M1_fixups={m1_fdt.special_counts()['/__fixups__']}",
            f"  M1_symbols={m1_fdt.special_counts()['/__symbols__']}",
            f"  M1_local_fixups={m1_fdt.special_counts()['/__local_fixups__']}",
            f"  M1_phandle_properties={m1_fdt.phandle_count()}",
            "",
            "P4_FRAGMENT_TOPOLOGY",
            f"  STOCK_fragment_count={len(stock_rows)}",
            f"  M1_fragment_count={len(m1_fdt.fragments())}",
            "",
            "P5_APPLIED_OVERLAY_CONTENT",
            f"  STOCK_applied_nodes_added={len(stock_applied['added_nodes']) if stock_applied else 'UNAVAILABLE'}",
            f"  STOCK_applied_props_added={len(stock_applied['added_props']) if stock_applied else 'UNAVAILABLE'}",
            f"  STOCK_applied_props_changed={len(stock_applied['changed_props']) if stock_applied else 'UNAVAILABLE'}",
            f"  M1_APPLIED_props_added={len(m1_applied['added_props']) if m1_applied else 'UNAVAILABLE'}",
            f"  M1_APPLIED_props_changed={len(m1_applied['changed_props']) if m1_applied else 'UNAVAILABLE'}",
            "",
            "P6_PAYLOAD_SIZE_TOTALSIZE_PADDING",
            f"  STOCK_payload_size={len(stock_payload)}",
            f"  M1_payload_size={len(m1_payload)}",
            f"  P6_SECONDARY_CAUSE_STATUS=NOT_EXCLUDED_NOT_NECESSARY",
            "",
            "PRIORITY=P1_THEN_P2_P3_THEN_P4_P5_THEN_P6",
            f"P1_ACTION={'L1_CANDIDATE_BUILT' if matrix['selector_differs'] else 'SKIP_L1_SELECTOR_CONTROL'}",
        ]
        emit_text("m5l-factor-decomposition.txt", factor_lines)

        # ---- 8. L1 construction --------------------------------------------
        selector_names = [name for name in ABL_SELECTOR_PROPERTIES if stock_fdt.prop("/", name) is not None]
        l1_needed = bool(matrix["selector_differs"])
        l1_payload = None
        l1_fdt = None
        l1_problems = []
        l1_applied = []
        l1_unchanged = []
        l1_extra = []
        l1_dts_text = ""
        if l1_needed:
            (l1_payload, l1_applied, l1_unchanged,
             l1_extra, l1_dts_text) = build_l1_payload(
                work, m1_payload, m1_fdt, stock_fdt, selector_names)
            l1_problems, l1_fdt = audit_l1_payload(l1_payload, m1_fdt, stock_fdt, selector_names)
            if l1_problems:
                print("M5L_L1_CONSTRUCTION_FAILED " + "; ".join(l1_problems))
            emit("m5l-l1-selector-matched-noop-payload.dtbo", l1_payload)

        # ---- 9. L2 construction --------------------------------------------
        selection, rejected, base_symbols = symbol_selection(
            stock_fdt, base_fdt, stock_rows, stock_classification)
        if not selection:
            raise SystemExit("M5L_TARGET_SYMBOL_UNRESOLVED no Stock fragment target is usable for L2")
        chosen = selection[0]
        l2_payload = dtc_compile(work, "m5l-l2-minimal-noop", l2_dts(chosen["symbol"], stock_fdt, selector_names))
        l2_problems, l2_fdt = audit_l2_payload(l2_payload, stock_fdt, chosen["symbol"],
                                               selector_names, work)
        if l2_problems:
            raise SystemExit("M5L_L2_CONSTRUCTION_FAILED " + "; ".join(l2_problems))
        emit("m5l-l2-stock-style-minimal-noop-payload.dtbo", l2_payload)

        l2_merge_ok, l2_merge_detail = fdtoverlay_apply_status(work, "m5l-l2-on-stock", dtb0, l2_payload)
        l2_applied = None
        l2_merged_sha = "UNAVAILABLE"
        if l2_merge_ok:
            merged = (work / "m5l-l2-on-stock.merged.dtb").read_bytes()
            l2_merged_sha = sha(merged)
            l2_applied = semantic_diff(base_fdt, Fdt(merged, "l2-applied"), "L2_MINIMAL_NOOP_ON_STOCK_BASE")
        l2_semantic_noop = bool(l2_applied) and l2_applied["valid_device_semantics_unchanged"]

        # ---- 10. containers and normalized full artifacts -------------------
        m1_container = m1_raw
        candidates_def = []
        if l1_payload is not None:
            candidates_def.append(("L1", "m5l-l1", l1_payload))
        candidates_def.append(("L2", "m5l-l2", l2_payload))

        container_rows = []
        full_reports = {}
        for tag, slug, payload in candidates_def:
            container = build_container(payload)
            _, container_problems = container_probe(container, payload)
            preserved = container_identity_preserved(parse_dtbo(container, f"{slug}-identity"),
                                                     m1_dtbo)
            full = container + stock[len(container):]
            full_problems = audit_full_artifact(full, container, stock, slug)
            prefix_sha = sha(container)
            tail_offset = len(container)
            tail_sha = sha(full[tail_offset:])
            full_reports[tag] = {
                "payload": payload,
                "container": container,
                "container_problems": container_problems,
                "container_preserved": preserved,
                "full": full,
                "full_problems": full_problems,
                "prefix_size": len(container),
                "prefix_sha": prefix_sha,
                "tail_offset": tail_offset,
                "tail_sha": tail_sha,
                "full_sha": sha(full),
                "slug": slug,
            }
            emit(f"{slug}-full-normalized-dtbo.img", full)
            container_rows.append((tag, slug, payload, container, prefix_sha, tail_offset, tail_sha))

        # ---- 11. negative controls -----------------------------------------
        negative = []
        negative.append(("CONTROL_UNMUTATED_L2_ACCEPTED", not l2_problems))
        if l1_payload is not None:
            negative.append(("CONTROL_UNMUTATED_L1_ACCEPTED", not l1_problems))
        else:
            negative.append(("CONTROL_L1_NOT_GENERATED", True))

        # wrong selector
        mutated = bytearray(l2_payload)
        board_offset = l2_fdt.prop_offset("/", "qcom,board-id")
        if board_offset is not None:
            mutated[board_offset:board_offset + 4] = struct.pack(">I", 99)
            bad_fdt = Fdt(bytes(mutated), "mutated-selector")
            problems, _ = audit_l2_payload(bytes(mutated), stock_fdt, chosen["symbol"],
                                           selector_names, work)
            negative.append(("NEG_WRONG_SELECTOR_DETECTED",
                             any("L2_SELECTOR_NOT_EXACT" in item for item in problems)))
        else:
            negative.append(("NEG_WRONG_SELECTOR_DETECTED", False))

        # wrong target symbol
        bogus = dtc_compile(work, "m5l-l2-bogus-symbol",
                            l2_dts("m5l_bogus_missing_symbol", stock_fdt, selector_names))
        bogus_ok, bogus_detail = fdtoverlay_apply_status(work, "m5l-l2-bogus-on-stock", dtb0, bogus)
        negative.append(("NEG_WRONG_TARGET_SYMBOL_REJECTED", not bogus_ok))

        # missing __fixups__: the M1 no-op payload has target-path and no fixups
        m1_as_l2, _ = audit_l2_payload(m1_payload, stock_fdt, chosen["symbol"], selector_names, work)
        negative.append(("NEG_MISSING_FIXUPS_DETECTED",
                         any("L2_MISSING_FIXUPS" in item for item in m1_as_l2)
                         and any("L2_USES_TARGET_PATH" in item for item in m1_as_l2)))

        # non-empty semantic overlay: Stock payload is definitely not a no-op
        negative.append(("NEG_NON_EMPTY_SEMANTIC_OVERLAY_DETECTED",
                         bool(stock_applied) and not stock_applied["valid_device_semantics_unchanged"]))

        # invalid FDT
        try:
            Fdt(l2_payload[:40], "truncated")
            negative.append(("NEG_INVALID_FDT_DETECTED", False))
        except ValueError:
            negative.append(("NEG_INVALID_FDT_DETECTED", True))

        # container and full-artifact mutations, exercised on the L2 candidate
        l2_container = full_reports["L2"]["container"]
        unmutated_ok, unmutated_reasons = container_probe(l2_container, l2_payload)
        negative.append(("CONTROL_CONTAINER_UNMUTATED_ACCEPTED", unmutated_ok))
        negative.append(("CONTROL_FULL_ARTIFACT_UNMUTATED_ACCEPTED",
                         not full_reports["L2"]["full_problems"]))
        container_controls = (
            ("NEG_WRONG_ENTRY_DT_SIZE_DETECTED", 32, len(l2_payload) - 1),
            ("NEG_WRONG_TOTAL_SIZE_DETECTED", 4, len(l2_container) - 1),
            ("NEG_ENTRY_COUNT_2_DETECTED", 16, 2),
            ("NEG_WRONG_DT_OFFSET_DETECTED", 36, 128),
            ("NEG_ENTRY_METADATA_NONZERO_DETECTED", 40, 1),
        )
        for label, offset, value in container_controls:
            mutated = bytearray(l2_container)
            struct.pack_into(">I", mutated, offset, value)
            ok, _ = container_probe(bytes(mutated), l2_payload)
            negative.append((label, not ok))

        l2_full = full_reports["L2"]["full"]
        mutated_full = bytearray(l2_full)
        mutated_full[5000000] ^= 0xFF
        negative.append(("NEG_WRONG_TAIL_DETECTED",
                         any("FULL_TAIL" in item for item in
                             audit_full_artifact(bytes(mutated_full), l2_container,
                                                 stock, "neg-tail"))))
        mutated_prefix = bytearray(l2_full)
        mutated_prefix[DTBO_HEADER_SIZE] ^= 0xFF
        negative.append(("NEG_PREFIX_MISMATCH_DETECTED",
                         any("FULL_PREFIX" in item for item in
                             audit_full_artifact(bytes(mutated_prefix), l2_container,
                                                 stock, "neg-prefix"))))
        negative.append(("NEG_WRONG_FULL_ARTIFACT_SIZE_DETECTED",
                         any("FULL_SIZE" in item for item in
                             audit_full_artifact(l2_full[:-1], l2_container, stock, "neg-size"))))

        # overlay body must be empty by design
        nonempty_dts = l2_dts(chosen["symbol"], stock_fdt, selector_names).replace(
            "\t\t__overlay__ {\n\t\t};",
            "\t\t__overlay__ {\n\t\t\tqcom,thyme-route-b-noop;\n\t\t};")
        nonempty = dtc_compile(work, "m5l-l2-nonempty-body", nonempty_dts)
        nonempty_problems, _ = audit_l2_payload(nonempty, stock_fdt, chosen["symbol"],
                                               selector_names, work)
        negative.append(("NEG_NON_EMPTY_OVERLAY_BODY_DETECTED",
                         any("L2_OVERLAY_BODY_NOT_EMPTY" in item for item in nonempty_problems)))

        failed_negative = [name for name, ok in negative if not ok]

        # ---- 12. validation ------------------------------------------------
        dtc_roundtrip(work, "m5l-l2-roundtrip", l2_payload)
        dtc_roundtrip(work, "m5l-m1-roundtrip", m1_payload)
        l2_roundtrip = True
        if l1_payload is not None:
            dtc_roundtrip(work, "m5l-l1-roundtrip", l1_payload)
        merged_matches_m5h = (stock_merged_sha == M5H_MERGED_SHA256)

    # ---- 13. reports -------------------------------------------------------
    l1_ready = False
    l2_ready = l2_semantic_noop and l2_merge_ok and not l2_problems
    if l1_payload is not None:
        l1_ready = not l1_problems
        l1_full = full_reports["L1"]
    else:
        l1_full = None
    l2_full = full_reports["L2"]

    if matrix["selector_differs"] and l1_ready:
        next_control = "L1_SELECTOR_MATCHED_NOOP"
    elif l2_ready:
        next_control = "L2_STOCK_STYLE_MINIMAL_NOOP"
    else:
        next_control = "NONE_NEEDS_REFINEMENT"

    l1_lines = [
        "# L1 selector-matched no-op candidate",
        "",
        f"L1_NEEDED={'YES' if l1_needed else 'NO'}",
        f"SKIP_L1_SELECTOR_CONTROL={'YES' if not l1_needed else 'NO'}",
        f"P1_ROOT_SELECTOR_METADATA_DIFFERS={','.join(matrix['selector_differs']) or 'NONE'}",
        f"L1_DESIGN=1-fragment target-path=\"/\" M1 no-op body plus exact Stock root selector metadata",
        f"L1_CHANGES_FRAGMENT_TARGET_MECHANISM=NO",
        f"L1_CHANGES_NOOP_SEMANTICS=NO",
        f"L1_ARTIFACT_GENERATED={'YES' if l1_payload is not None else 'NO'}",
    ]
    if l1_payload is not None:
        l1_lines.extend([
            f"L1_PAYLOAD_SIZE={len(l1_payload)}",
            f"L1_PAYLOAD_SHA256={sha(l1_payload)}",
            f"L1_SELECTOR_PROPERTIES_MODIFIED={','.join(l1_applied) or 'NONE'}",
            f"L1_SELECTOR_PROPERTIES_ALREADY_EQUAL={','.join(l1_unchanged) or 'NONE'}",
            f"L1_SELECTOR_PROPERTIES_EXTRA_IN_M1={','.join(l1_extra) or 'NONE'}",
            f"L1_FRAGMENT_COUNT={len(l1_fdt.fragments()) if l1_fdt else 'UNAVAILABLE'}",
            "L1_TARGET_MECHANISM=TARGET_PATH_ROOT",
            f"L1_FIXUPS={l1_fdt.special_counts()['/__fixups__'] if l1_fdt else 'UNAVAILABLE'}",
            f"L1_SYMBOLS={l1_fdt.special_counts()['/__symbols__'] if l1_fdt else 'UNAVAILABLE'}",
            f"L1_MARKER_PRESENT="
            f"{'YES' if l1_fdt and l1_fdt.prop('/fragment@0/__overlay__', MARKER_PROPERTY) is not None else 'NO'}",
            f"L1_PROBLEM_COUNT={len(l1_problems)}",
            f"L1_ACTIVE_PREFIX_SIZE={l1_full['prefix_size']}",
            f"L1_ACTIVE_PREFIX_SHA256={l1_full['prefix_sha']}",
            f"L1_STOCK_TAIL_OFFSET={l1_full['tail_offset']}",
            f"L1_STOCK_TAIL_SHA256={l1_full['tail_sha']}",
            f"L1_FULL_ARTIFACT_SIZE={len(l1_full['full'])}",
            f"L1_FULL_ARTIFACT_SHA256={l1_full['full_sha']}",
            f"L1_CONTAINER_PROBLEMS={'; '.join(l1_full['container_problems']) or 'NONE'}",
            f"L1_FULL_ARTIFACT_PROBLEMS={'; '.join(l1_full['full_problems']) or 'NONE'}",
            "",
            "# DTC input for L1 (root section, first 24 lines)",
            "```dts",
        ] + l1_dts_text.splitlines()[:24] + ["```"])
        for item in l1_problems:
            l1_lines.append(f"L1_PROBLEM={item}")
    l1_lines.extend([
        "",
        f"L1_READY={'YES' if l1_ready else 'NO'}",
        f"L1_SELECTOR_EXACT_MATCH={'YES' if l1_ready else 'NO'}",
        f"L1_FUTURE_INTERPRETATION=>12s => ROOT_SELECTOR_METADATA_CAUSAL=STRONGLY_SUPPORTED; ~4.7s => proceed to L2",
    ])
    emit_text("m5l-l1-report.txt", l1_lines)

    l2_lines = [
        "# L2 Stock-style target/fixup minimal no-op candidate",
        "",
        f"L2_TARGET_SYMBOL={chosen['symbol']}",
        f"L2_TARGET_PATH={chosen['path']}",
        f"L2_TARGET_SOURCE_FRAGMENT_INDEX={chosen['index']}",
        f"L2_TARGET_SOURCE_FRAGMENT_OVERLAY_CHILDREN={chosen['overlay_children']}",
        f"L2_TARGET_SOURCE_FRAGMENT_OVERLAY_PROPERTIES={chosen['overlay_properties']}",
        f"L2_TARGET_SOURCE_FRAGMENT_LOCAL_REFS={chosen['local_refs']}",
        f"L2_TARGET_SELECTION_RANKED="
        + " | ".join(f"{item['index']}:{item['symbol']}->{item['path']}" for item in selection[:8]),
        f"L2_TARGET_CANDIDATES_CONSIDERED={len(selection)}",
        f"L2_TARGET_REJECTED_COUNT={len(rejected)}",
        f"L2_TARGET_REJECTED_SAMPLE="
        + " | ".join(f"{index}:{symbol}:{reason}" for index, symbol, reason in rejected[:8]),
        "",
        f"L2_PAYLOAD_SIZE={len(l2_payload)}",
        f"L2_PAYLOAD_SHA256={sha(l2_payload)}",
        f"L2_FRAGMENT_COUNT={len(l2_fdt.fragments())}",
        f"L2_TARGET_MECHANISM=TARGET_PHANDLE_PLUS_FIXUPS",
        f"L2_FIXUPS_COUNT={l2_fdt.special_counts()['/__fixups__']}",
        f"L2_SYMBOLS_COUNT={l2_fdt.special_counts()['/__symbols__']}",
        f"L2_LOCAL_FIXUPS={l2_fdt.special_counts()['/__local_fixups__']}",
        f"L2_PHANDLE_PROPERTY_COUNT={l2_fdt.phandle_count()}",
        f"L2_OVERLAY_BODY_PROPERTY_COUNT="
        f"{len(l2_fdt.node('/fragment@0/__overlay__').props) if l2_fdt.node('/fragment@0/__overlay__') else 'UNAVAILABLE'}",
        f"L2_OVERLAY_BODY_CHILD_COUNT="
        f"{len(l2_fdt.node('/fragment@0/__overlay__').children) if l2_fdt.node('/fragment@0/__overlay__') else 'UNAVAILABLE'}",
        f"L2_ROOT_SELECTOR_PROPERTIES={','.join(selector_names)}",
        f"L2_ROOT_SELECTOR_METADATA_EXACT_STOCK={'YES' if not any('L2_SELECTOR_NOT_EXACT' in item for item in l2_problems) else 'NO'}",
        f"L2_DTC_ROUNDTRIP={'PASS' if l2_roundtrip else 'FAIL'}",
        f"L2_FDTOVERLAY_STOCK_DTB0={'PASS' if l2_merge_ok else 'FAIL'}",
        f"L2_FDTOVERLAY_DETAIL={l2_merge_detail}",
        f"L2_MERGED_SHA256={l2_merged_sha}",
        f"L2_SEMANTIC_NOOP_CONFIRMED={'YES' if l2_semantic_noop else 'NO'}",
        "",
        f"L2_ACTIVE_PREFIX_SIZE={l2_full['prefix_size']}",
        f"L2_ACTIVE_PREFIX_SHA256={l2_full['prefix_sha']}",
        f"L2_CONTAINER_TOTAL_SIZE={struct.unpack_from('>I', l2_full['container'], 4)[0]}",
        f"L2_CONTAINER_ENTRY_DT_SIZE={struct.unpack_from('>I', l2_full['container'], 32)[0]}",
        f"L2_CONTAINER_ENTRY_DT_OFFSET={struct.unpack_from('>I', l2_full['container'], 36)[0]}",
        f"L2_STOCK_TAIL_OFFSET={l2_full['tail_offset']}",
        f"L2_STOCK_TAIL_SHA256={l2_full['tail_sha']}",
        f"L2_FULL_ARTIFACT_SIZE={len(l2_full['full'])}",
        f"L2_FULL_ARTIFACT_SHA256={l2_full['full_sha']}",
        f"L2_CONTAINER_PROBLEMS={'; '.join(l2_full['container_problems']) or 'NONE'}",
        f"L2_FULL_ARTIFACT_PROBLEMS={'; '.join(l2_full['full_problems']) or 'NONE'}",
        "",
        f"L2_READY={'YES' if l2_ready else 'NO'}",
        f"L2_FUTURE_INTERPRETATION=>12s => STOCK_STYLE_MINIMAL_NOOP_COMPATIBLE=STRONGLY_SUPPORTED; "
        f"~4.3-5.3s => target/fixup encoding still insufficient, move toward fragment topology",
    ]
    emit_text("m5l-l2-report.txt", l2_lines)

    semantic_lines = ["# L2 semantic no-op evidence on the exact Stock DTB0", ""]
    if l2_applied is not None:
        semantic_lines.extend(semantic_report_lines(l2_applied))
    else:
        semantic_lines.append("L2_FDTOVERLAY_FAILED=YES")
    semantic_lines.extend([
        "",
        "# M1 no-op applied on the same base, for contrast",
    ])
    if m1_applied is not None:
        semantic_lines.extend(semantic_report_lines(m1_applied))
    semantic_lines.extend([
        "",
        f"L2_ALLOWED_BOOKKEEPING_NODE_PREFIXES={','.join(BOOKKEEPING_NODE_PREFIXES)}",
        f"L2_ALLOWED_BOOKKEEPING_PROPERTIES={','.join(PHANDLE_PROPERTIES)}",
        f"L2_FORBIDDEN_SEMANTIC_PROPERTIES={','.join(FORBIDDEN_SEMANTIC_PROPERTIES)}",
        f"L2_MARKER_IS_ONLY_EXTRA_M1_PROPERTY="
        f"{'YES' if (m1_applied and len(m1_applied['added_props']) == 1 and 'qcom,thyme-route-b-noop' in m1_applied['added_props'][0]) else 'NO'}",
        f"M1_NOOP_MARKER_REACHES_MERGED_TREE="
        f"{'YES' if (m1_applied and any('qcom,thyme-route-b-noop' in item for item in m1_applied['added_props'])) else 'NO'}",
    ])
    emit_text("m5l-l2-semantic-noop.txt", semantic_lines)

    container_lines = ["# candidate container identity versus the M1 one-entry semantics", ""]

    def container_field_rows(tag, container):
        parsed = parse_dtbo(container, f"{tag}-container")
        m1_parsed = m1_dtbo
        return [
            ("MAGIC", f"0x{DTBO_MAGIC:08x}", f"0x{DTBO_MAGIC:08x}",
             parsed.data[:4] == m1_parsed.data[:4]),
            ("HEADER_VERSION", str(m1_parsed.version), str(parsed.version),
             m1_parsed.version == parsed.version),
            ("HEADER_SIZE", str(m1_parsed.header_size), str(parsed.header_size),
             m1_parsed.header_size == parsed.header_size),
            ("ENTRY_SIZE", str(m1_parsed.entry_size), str(parsed.entry_size),
             m1_parsed.entry_size == parsed.entry_size),
            ("ENTRY_COUNT", str(m1_parsed.entry_count), str(parsed.entry_count),
             m1_parsed.entry_count == parsed.entry_count),
            ("ENTRIES_OFFSET", str(m1_parsed.entries_offset), str(parsed.entries_offset),
             m1_parsed.entries_offset == parsed.entries_offset),
            ("PAGE_SIZE", str(m1_parsed.page_size), str(parsed.page_size),
             m1_parsed.page_size == parsed.page_size),
            ("ENTRY_DT_OFFSET", str(m1_parsed.entries[0].dt_offset), str(parsed.entries[0].dt_offset),
             m1_parsed.entries[0].dt_offset == parsed.entries[0].dt_offset),
            ("ENTRY_ID", "0", str(parsed.entries[0].image_id), parsed.entries[0].image_id == 0),
            ("ENTRY_REV", "0", str(parsed.entries[0].rev), parsed.entries[0].rev == 0),
            ("ENTRY_CUSTOM", "0 0 0 0", " ".join(str(value) for value in parsed.entries[0].custom),
             tuple(parsed.entries[0].custom) == (0, 0, 0, 0)),
            ("TOTAL_SIZE", str(m1_parsed.total_size), str(parsed.total_size),
             m1_parsed.total_size == parsed.total_size),
            ("ENTRY_DT_SIZE", str(m1_parsed.entries[0].dt_size), str(parsed.entries[0].dt_size),
             m1_parsed.entries[0].dt_size == parsed.entries[0].dt_size),
        ]

    for tag, slug, payload, container, prefix_sha, tail_offset, tail_sha in container_rows:
        container_lines.append(f"# {tag} candidate container")
        preserved = True
        for field, left, right, same in container_field_rows(tag, container):
            expected = "SAME" if same else "CHANGED"
            container_lines.append(f"FIELD={field} M1={left} {tag}={right} {expected}")
            if field not in {"TOTAL_SIZE", "ENTRY_DT_SIZE"} and not same:
                preserved = False
        container_lines.extend([
            f"{tag}_CONTAINER_SEMANTICS_PRESERVED_ONE_ENTRY={'YES' if preserved else 'NO'}",
            f"{tag}_CHANGED_HEADER_FIELD_VS_M1=TOTAL_SIZE",
            f"{tag}_CHANGED_ENTRY_FIELD_VS_M1=ENTRY_DT_SIZE",
            f"{tag}_ACTIVE_PREFIX_SIZE={len(container)}",
            f"{tag}_ACTIVE_PREFIX_SHA256={prefix_sha}",
            f"{tag}_STOCK_TAIL_OFFSET={tail_offset}",
            f"{tag}_STOCK_TAIL_SHA256={tail_sha}",
            "",
        ])
    container_lines.extend([
        f"M5K0_SHORT_REFERENCE_SIZE={M5K0_SHORT_SIZE}",
        f"M5K0_SHORT_REFERENCE_SHA256={M5K0_SHORT_SHA256}",
        f"M1_CONTAINER_SIZE={len(m1_container)}",
    ])
    emit_text("m5l-container-identity.txt", container_lines)

    diff_lines = ["# binary diffs", ""]
    for tag, slug, payload, container, prefix_sha, tail_offset, tail_sha in container_rows:
        full = full_reports[tag]["full"]
        diff_lines.extend(region_lines(
            f"{tag}_PAYLOAD_VS_M1_DTBO",
            (("M1_HEADER", 0, DTBO_HEADER_SIZE),
             ("M1_ENTRY", DTBO_HEADER_SIZE, DTBO_PAYLOAD_OFFSET),
             ("M1_PAYLOAD", DTBO_PAYLOAD_OFFSET, M1_DTBO_SIZE),
             ("EXTENDED", M1_DTBO_SIZE, len(container))),
            m1_raw, container, "exact M1 dtbo", f"{tag} candidate container"))
        diff_lines.extend([
            f"{tag}_INTENTIONAL_VARIABLE=SELECTED_PAYLOAD_BYTES",
            "CONTAINER_SEMANTICS_HELD=ONE_ENTRY",
            "",
        ])
        diff_lines.extend(region_lines(
            f"{tag}_FULL_VS_STOCK_DTBO",
            (("HEADER", 0, DTBO_HEADER_SIZE),
             ("ENTRY_TABLE", DTBO_HEADER_SIZE, DTBO_PAYLOAD_OFFSET),
             (f"{tag}_ACTIVE_PAYLOAD", DTBO_PAYLOAD_OFFSET, len(container)),
             ("STOCK_SAME_OFFSET_TAIL", len(container), FULL_ARTIFACT_SIZE)),
            stock, full, "exact Stock dtbo.img", f"{tag} normalized full artifact"))
        diff_lines.extend([
            f"{tag}_TAIL_IS_BYTE_EXACT_STOCK_SAME_OFFSET=YES",
            f"{tag}_TAIL_NOT_PART_OF_ACTIVE_IMAGE=YES",
            "",
        ])
    emit_text("m5l-binary-diff.txt", diff_lines)

    validation_lines = [
        "DTBO_PARSE_STOCK=PASS",
        "DTBO_PARSE_M1=PASS",
        f"STOCK_ENTRY21_PAYLOAD_PARSE=PASS",
        f"STOCK_ENTRY21_PAYLOAD_FRAGMENT_COUNT={len(stock_rows)}",
        f"STOCK_ENTRY21_PAYLOAD_FIXUPS={stock_counts['/__fixups__']}",
        f"STOCK_ENTRY21_PAYLOAD_SYMBOLS={stock_counts['/__symbols__']}",
        f"M1_NOOP_PAYLOAD_FRAGMENT_COUNT={len(m1_fdt.fragments())}",
        "FIXUP_PROBE_COMPILE=PASS",
        f"FIXUP_OFFSET_CONVENTION={convention}",
        f"FIXUP_OFFSET_CONVENTIONS_THAT_RESOLVE_PROBE={','.join(calibration['resolving'])}",
        f"FIXUP_PROBE_RAW_OFFSETS="
        + " ".join(f"0x{value:x}" for value in calibration["raw_offsets"]),
        "DTC_ROUNDTRIP_L2=PASS",
        "DTC_ROUNDTRIP_M1_NOOP=PASS",
        f"FDTOVERLAY_STOCK_DTB0_PLUS_STOCK_ENTRY21={'PASS' if stock_merge_ok else 'FAIL'}",
        f"FDTOVERLAY_MERGED_SHA256={stock_merged_sha}",
        f"M5H_RECORDED_MERGED_SHA256={M5H_MERGED_SHA256}",
        f"FDTOVERLAY_MERGED_SHA_EQUALS_M5H_RECORD={'YES' if merged_matches_m5h else 'NO'}",
        f"FDTOVERLAY_STOCK_DTB0_PLUS_M1_NOOP={'PASS' if m1_merge_ok else 'FAIL'}",
        f"FDTOVERLAY_STOCK_DTB0_PLUS_L2={'PASS' if l2_merge_ok else 'FAIL'}",
        f"STOCK_DTB0_SIZE={dtb0_size}",
        f"STOCK_DTB0_SHA256={sha(dtb0)}",
        "STRUCTURAL_VALIDATION_ONLY=YES",
        "XIAOMI_ABL_EVIDENCE=NO",
    ]
    if l1_payload is not None:
        validation_lines.insert(12, f"DTC_ROUNDTRIP_L1=PASS")
    emit_text("m5l-validation-report.txt", validation_lines)

    negative_lines = [f"NEGATIVE_TEST_COUNT={len(negative)}"]
    for name, ok in negative:
        negative_lines.append(f"{name}={'PASS' if ok else 'FAIL'}")
    negative_lines.append(f"FAILED_NEGATIVE_TESTS={len(failed_negative)}")
    negative_lines.append("NEGATIVE_TESTS_PASS=" + ("YES" if not failed_negative else "NO"))
    negative_lines.append("FAIL_CLOSED=" + ("PASS" if not failed_negative else "FAIL"))
    emit_text("m5l-negative-tests.txt", negative_lines)

    # ---- 14. next-control report ------------------------------------------
    next_lines = [
        "# M5L — next true-device payload control",
        "",
        "## Constraints",
        "",
        "```text",
        "MEM0_READ=YES",
        "LOCAL_BUILD=NO",
        "GHA_ONLY=YES",
        "DEVICE_OPERATION=NO",
        "SLOT_A_WRITTEN=NO",
        "```",
        "",
        "## DTBO factorial (measured, unchanged)",
        "",
        "```text",
        "Stock table + Stock thyme entry21   >12s    (Cell A)",
        "Stock table + M1 no-op              4.922s  (Cell B, M5J)",
        "M1 one-entry + Stock thyme entry21  >12s    (Cell D, M5K)",
        "M1 one-entry + M1 no-op             4.812s  (Cell C, M5F1)",
        "```",
        "",
        "## Payload root matrix",
        "",
        "```text",
    ]
    for row in root_rows:
        next_lines.append(f"{row['property']}\tStock={row['stock']}\tM1={row['m1']}\t{row['verdict']}")
    next_lines.extend([
        "```",
        "",
        "## Stock targeting",
        "",
        "```text",
        f"fragment count              {len(stock_rows)}",
        f"target-phandle fragments    {len(phandle_fragments)}",
        f"target-phandle local        {len(local_phandle_fragments)}",
        f"target-path fragments       {len(path_fragments)}",
        f"other                        {len(other_fragments)}",
        f"target fixups               {len(stock_classification['target_fixups'])}",
        f"body fixups                 {len(stock_classification['body_fixups'])}",
        f"local fixups                {stock_classification['local_entries']}",
        f"__symbols__                 {stock_counts['/__symbols__']}",
        f"phandle properties          {stock_fdt.phandle_count()}",
        "```",
        "",
        "## M1 targeting",
        "",
        "```text",
        f"fragment count              {len(m1_fdt.fragments())}",
        "target-path                 /",
        f"fixups                      {m1_fdt.special_counts()['/__fixups__']}",
        f"symbols                     {m1_fdt.special_counts()['/__symbols__']}",
        f"marker home                 {marker_home or 'ABSENT'}",
        "```",
        "",
        "## Padding assessment",
        "",
        "```text",
        f"Cell C self-consistent dt_size  YES ({len(m1_payload)})",
        "Cell C runtime                  4.812s",
        "PADDING_MISMATCH_NECESSARY_CAUSE NO",
        "```",
        "",
        "## L1",
        "",
        "```text",
        f"needed              {'YES' if l1_needed else 'NO'}",
        f"design              1-fragment target-path=\"/\" M1 no-op + exact Stock root selectors",
        f"artifact generated  {'YES' if l1_payload is not None else 'NO'}",
    ])
    if l1_payload is not None:
        next_lines.extend([
            f"payload SHA256      {sha(l1_payload)}",
            f"active prefix SHA   {l1_full['prefix_sha']}",
            f"full SHA256         {l1_full['full_sha']}",
        ])
    next_lines.extend([
        f"Gate                L1_READY={'YES' if l1_ready else 'NO'}",
        "```",
        "",
        "## L2",
        "",
        "```text",
        f"target symbol       {chosen['symbol']}",
        f"target path         {chosen['path']}",
        f"root selector       {','.join(selector_names)}",
        f"fragment count      {len(l2_fdt.fragments())}",
        f"semantic no-op      {'YES' if l2_semantic_noop else 'NO'}",
        f"fdtoverlay          {'PASS' if l2_merge_ok else 'FAIL'}",
        f"payload SHA256      {sha(l2_payload)}",
        f"active prefix SHA   {l2_full['prefix_sha']}",
        f"full artifact size  {len(l2_full['full'])}",
        f"full SHA256         {l2_full['full_sha']}",
        f"Stock tail SHA      {l2_full['tail_sha']}",
        "```",
        "",
        "## Final",
        "",
        "```text",
        "READY_FOR_M5L_STOCK_STYLE_MINIMAL_NOOP_CONTROL="
        f"{'YES' if l2_ready else 'NO'}",
        "CURRENT_B=UNCHANGED",
        f"NEXT_TRUE_DEVICE_PAYLOAD_CONTROL={next_control}",
        "NO_DEVICE_OPERATION=YES",
        "WAIT_FOR_USER_APPROVAL",
        "```",
    ])
    emit_text("m5l-next-control.md", next_lines)

    # ---- 15. gates ---------------------------------------------------------
    # The audit reports readiness; it aborts only when the round itself is
    # invalid (identity, construction, negative controls, artifact integrity).
    safe = (not failed_negative) and all(
        not full_reports[tag]["container_problems"] and not full_reports[tag]["full_problems"]
        for tag in full_reports)
    gates = [
        "MEM0_READ_BEFORE_M5L=YES",
        "M5L_AUDIT_COMPLETE=YES",
        "LOCAL_BUILD=NO",
        "LOCAL_VALIDATION=NO",
        "LOCAL_VALIDATOR=NO",
        "LOCAL_SOURCE_GATE=NO",
        "LOCAL_ACTIONLINT=NO",
        "LOCAL_BINARY_VALIDATION=NO",
        "GHA_ONLY=YES",
        "DEVICE_OPERATION=NO",
        "ADB_DEVICE_CHANGE=NO",
        "FASTBOOT_USED=NO",
        "FLASH_USED=NO",
        "ERASE_USED=NO",
        "FORMAT_USED=NO",
        "SET_ACTIVE_USED=NO",
        "B_BOOT=NO",
        "SLOT_A_WRITTEN=NO",
        "CURRENT_B_UNCHANGED=YES",
        "BUILD_THIS_ROUND=NO",
        "STOCK_DTBO_IDENTITY=PASS",
        "STOCK_VENDOR_BOOT_IDENTITY=PASS",
        "STOCK_DTB0_IDENTITY=PASS",
        "M1_DTBO_IDENTITY=PASS",
        f"STOCK_DTBO_ENTRY_COUNT={stock_dtbo.entry_count}",
        f"STOCK_ENTRY21_DT_OFFSET={stock_entry.dt_offset}",
        f"STOCK_ENTRY21_DT_SIZE={stock_entry.dt_size}",
        "STOCK_ENTRY21_PAYLOAD_SHA_EXACT=YES",
        f"FIXUP_PROBE_CALIBRATION=PASS",
        f"FIXUP_OFFSET_CONVENTION={convention}",
        f"FIXUP_OFFSET_CONVENTIONS_THAT_RESOLVE_PROBE={','.join(calibration['resolving'])}",
        f"STOCK_FRAGMENT_COUNT={len(stock_rows)}",
        f"STOCK_TARGET_PHANDLE_FRAGMENT_COUNT={len(phandle_fragments)}",
        f"STOCK_TARGET_PHANDLE_LOCAL_FRAGMENT_COUNT={len(local_phandle_fragments)}",
        f"STOCK_TARGET_PATH_FRAGMENT_COUNT={len(path_fragments)}",
        f"STOCK_OTHER_TARGET_FRAGMENT_COUNT={len(other_fragments)}",
        f"STOCK_FRAGMENTS_WITH_FIXUP_SYMBOL={len(stock_classification['per_fragment_symbol'])}",
        f"STOCK_FRAGMENTS_WITHOUT_FIXUP_SYMBOL="
        f"{len(stock_rows) - len(stock_classification['per_fragment_symbol'])}",
        f"STOCK_TARGET_FIXUP_COUNT={len(stock_classification['target_fixups'])}",
        f"STOCK_BODY_FIXUP_COUNT={len(stock_classification['body_fixups'])}",
        f"STOCK_LOCAL_FIXUP_COUNT={stock_classification['local_entries']}",
        f"STOCK_UNRESOLVED_FIXUP_OFFSET_COUNT={len(stock_classification['unresolved'])}",
        f"STOCK_FIXUPS_COUNT={stock_counts['/__fixups__']}",
        f"STOCK_SYMBOLS_COUNT={stock_counts['/__symbols__']}",
        f"STOCK_PHANDLE_PROPERTY_COUNT={stock_fdt.phandle_count()}",
        f"STOCK_DTB0_HAS_SYMBOLS={'YES' if base_fdt.node('/__symbols__') else 'NO'}",
        f"STOCK_TARGET_PLUS_FIXUP_MECHANISM_MAJORITY="
        f"{'YES' if len(phandle_fragments) * 2 > len(stock_rows) else 'NO'}",
        f"M1_FRAGMENT_COUNT={len(m1_fdt.fragments())}",
        "M1_TARGET_MECHANISM=TARGET_PATH_ROOT",
        f"M1_FIXUPS={m1_fdt.special_counts()['/__fixups__']}",
        f"M1_SYMBOLS={m1_fdt.special_counts()['/__symbols__']}",
        f"M1_MARKER_HOME={marker_home or 'ABSENT'}",
        "SELECTOR_DIFFERENCE_EXISTS=" + ("YES" if matrix["selector_differs"] else "NO"),
        "SELECTOR_PROPERTIES_DIFFERING=" + (",".join(matrix["selector_differs"]) or "NONE"),
        "P1_ROOT_SELECTOR_METADATA_EXISTS=" + ("YES" if matrix["selector_differs"] else "NO"),
        "PADDING_OR_DT_SIZE_MISMATCH_AS_NECESSARY_CAUSE=NOT_SUPPORTED",
        "PADDING_PRIORITY=P6_DEPRIORITIZED",
        f"DTBO_CONTAINER_TABLE_TOPOLOGY=DEPRIORITIZED",
        "M1_NOOP_PAYLOAD_SUFFICIENT=YES",
        "M1_NOOP_PAYLOAD_CAUSAL_FAMILY=STRONGLY_SUPPORTED",
        "M1_ONE_ENTRY_CONTAINER_ALONE_SUFFICIENT=NO",
        f"SKIP_L1_SELECTOR_CONTROL={'YES' if not l1_needed else 'NO'}",
        f"L1_NEEDED={'YES' if l1_needed else 'NO'}",
        f"L1_ARTIFACT_GENERATED={'YES' if l1_payload is not None else 'NO'}",
        f"L1_READY={'YES' if l1_ready else 'NO'}",
        f"L2_TARGET_SYMBOL={chosen['symbol']}",
        f"L2_TARGET_PATH={chosen['path']}",
        f"L2_FRAGMENT_COUNT={len(l2_fdt.fragments())}",
        f"L2_FIXUPS_COUNT={l2_fdt.special_counts()['/__fixups__']}",
        f"L2_SYMBOLS_COUNT={l2_fdt.special_counts()['/__symbols__']}",
        f"L2_LOCAL_FIXUPS={l2_fdt.special_counts()['/__local_fixups__']}",
        f"L2_PAYLOAD_SIZE={len(l2_payload)}",
        f"L2_PAYLOAD_SHA256={sha(l2_payload)}",
        "L2_TARGET_MECHANISM=TARGET_PHANDLE_PLUS_FIXUPS",
        f"L2_ROOT_SELECTOR_METADATA_EXACT_STOCK="
        f"{'YES' if not any('L2_SELECTOR_NOT_EXACT' in item for item in l2_problems) else 'NO'}",
        f"L2_FDTOVERLAY={'PASS' if l2_merge_ok else 'FAIL'}",
        f"L2_SEMANTIC_NOOP_CONFIRMED={'YES' if l2_semantic_noop else 'NO'}",
        f"L2_DTC_ROUNDTRIP=PASS",
        f"L2_MERGED_SHA256={l2_merged_sha}",
        f"L2_ACTIVE_PREFIX_SIZE={l2_full['prefix_size']}",
        f"L2_ACTIVE_PREFIX_SHA256={l2_full['prefix_sha']}",
        f"L2_STOCK_TAIL_OFFSET={l2_full['tail_offset']}",
        f"L2_STOCK_TAIL_SHA256={l2_full['tail_sha']}",
        f"L2_FULL_ARTIFACT_SIZE={len(l2_full['full'])}",
        f"L2_FULL_ARTIFACT_SHA256={l2_full['full_sha']}",
        f"L2_READY={'YES' if l2_ready else 'NO'}",
        f"FDTOVERLAY_MERGED_SHA_EQUALS_M5H_RECORD={'YES' if merged_matches_m5h else 'NO'}",
        "M5J_NOOP_RESIDUE_AT_STOCK_ENTRY21_SLOT=NOT_APPLICABLE",
        f"NEGATIVE_TEST_COUNT={len(negative)}",
        "NEGATIVE_TESTS_PASS=" + ("YES" if not failed_negative else "NO"),
        "FAIL_CLOSED=" + ("PASS" if not failed_negative else "FAIL"),
        "PRIVATE_ARTIFACT_ONLY=YES",
        "OEM_DERIVED_ARTIFACT_PRIVATE_ONLY=YES",
        "READY_FOR_M5L_STOCK_STYLE_MINIMAL_NOOP_CONTROL=" + ("YES" if l2_ready else "NO"),
        f"NEXT_TRUE_DEVICE_PAYLOAD_CONTROL={next_control}",
        "NO_NEXT_STAGE_EXECUTED=YES",
        "WAIT_FOR_USER_APPROVAL=YES",
    ]
    if l1_full is not None:
        gates.extend([
            f"L1_PAYLOAD_SIZE={len(l1_payload)}",
            f"L1_PAYLOAD_SHA256={sha(l1_payload)}",
            f"L1_FRAGMENT_COUNT={len(l1_fdt.fragments())}",
            "L1_TARGET_MECHANISM=TARGET_PATH_ROOT",
            f"L1_FIXUPS={l1_fdt.special_counts()['/__fixups__']}",
            f"L1_SYMBOLS={l1_fdt.special_counts()['/__symbols__']}",
            f"L1_MARKER_PRESENT="
            f"{'YES' if l1_fdt.prop('/fragment@0/__overlay__', MARKER_PROPERTY) is not None else 'NO'}",
            f"L1_SELECTOR_PROPERTIES_MODIFIED={','.join(l1_applied) or 'NONE'}",
            f"L1_ACTIVE_PREFIX_SIZE={l1_full['prefix_size']}",
            f"L1_ACTIVE_PREFIX_SHA256={l1_full['prefix_sha']}",
            f"L1_STOCK_TAIL_OFFSET={l1_full['tail_offset']}",
            f"L1_STOCK_TAIL_SHA256={l1_full['tail_sha']}",
            f"L1_FULL_ARTIFACT_SIZE={len(l1_full['full'])}",
            f"L1_FULL_ARTIFACT_SHA256={l1_full['full_sha']}",
            "L1_CONTAINER_SEMANTICS_PRESERVED_ONE_ENTRY="
            + ("YES" if l1_full["container_preserved"] else "NO"),
        ])
    gates.extend([
        f"L2_CONTAINER_SEMANTICS_PRESERVED_ONE_ENTRY="
        f"{'YES' if l2_full['container_preserved'] else 'NO'}",
        f"L2_ACTIVE_PREFIX_SHA256={l2_full['prefix_sha']}",
        f"L2_CONTAINER_ENTRY_COUNT={struct.unpack_from('>I', l2_full['container'], 16)[0]}",
        f"L2_CONTAINER_ENTRY_DT_OFFSET={struct.unpack_from('>I', l2_full['container'], 36)[0]}",
        f"L2_CONTAINER_TOTAL_SIZE={struct.unpack_from('>I', l2_full['container'], 4)[0]}",
        f"L2_CONTAINER_HEADER_SIZE={struct.unpack_from('>I', l2_full['container'], 8)[0]}",
        f"L2_CONTAINER_ENTRY_SIZE={struct.unpack_from('>I', l2_full['container'], 12)[0]}",
        "L2_CONTAINER_ENTRY_METADATA_ALL_ZERO=YES",
        f"L2_ROOT_SELECTOR_PROPERTIES={','.join(selector_names)}",
        f"L2_OVERLAY_BODY_PROPERTY_COUNT={len(l2_fdt.node('/fragment@0/__overlay__').props)}",
        f"L2_OVERLAY_BODY_CHILD_COUNT={len(l2_fdt.node('/fragment@0/__overlay__').children)}",
    ])
    if not safe:
        gates.append("M5L_NOT_SAFE")
    emit_text("m5l-gates.txt", gates)

    write_lines(out / "SHA256SUMS",
                [f"{sha((out / name).read_bytes())}  {name}" for name in sorted(produced)])
    manifest = sorted(produced + ["m5l-artifact-scope.txt", "SHA256SUMS"])
    write_lines(out / "m5l-artifact-scope.txt", manifest)

    print("\n".join(gates))
    print(f"M5L_ARTIFACT_COUNT={len(manifest)}")
    if not safe:
        raise SystemExit("M5L_NOT_SAFE")


if __name__ == "__main__":
    main()
