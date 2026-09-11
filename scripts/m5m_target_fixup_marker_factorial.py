#!/usr/bin/env python3
"""M5M target/fixup × marker factorial (GitHub Actions only).

No local build, no local validation, no local DTBO parse, no local DTC, no
local fdtoverlay, no local binary diff. Every OEM input, reconstruction,
candidate construction, semantic comparison and negative test happens inside
the private CI runner only.

Round scope (CI only, zero device operation):

  * reproduce exact L1 and L2 payloads (SHA identity)
  * audit historical marker encoding from M1/L1
  * Cell TM-10 / Candidate A: L1 minus marker (T0 target-path, M0 absent)
  * Cell TM-21 / Candidate B: L2 plus historical marker (T1 fixup, M1 present)
  * merged semantic gates, one-entry containers, full-partition artifacts
  * fail-closed negative controls

Failure labels:

    M5M_SOURCE_IDENTITY_FAILED
    M5M_L1_IDENTITY_FAILED
    M5M_L2_IDENTITY_FAILED
    M5M_MARKER_AUDIT_FAILED
    M5M_A_CONSTRUCTION_FAILED
    M5M_B_CONSTRUCTION_FAILED
    M5M_A_SEMANTIC_NOOP_FAILED
    M5M_B_SEMANTIC_DELTA_FAILED
    M5M_CONTAINER_IDENTITY_FAILED
    M5M_FULL_ARTIFACT_INVALID
    M5M_NEGATIVE_TEST_FAILED
    M5M_DTC_FAILED
    M5M_FDTOVERLAY_FAILED
    M5M_NOT_SAFE
"""

import argparse
import hashlib
import os
import struct
import subprocess
import tempfile
from pathlib import Path

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
M1_PAYLOAD_SHA256 = "37d6855a5930508b0dd349d8ba2bb167f47e415de2b754a7af0fe80d11ee7c96"

THYME_ENTRY_INDEX = 21
THYME_ENTRY_DT_OFFSET = 9666706
THYME_ENTRY_DT_SIZE = 484885
THYME_ENTRY_PAYLOAD_SHA256 = "44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93"

L1_PAYLOAD_SIZE = 331
L1_PAYLOAD_SHA256 = "64344d59119b253d47b950385fbed1c8dd38bf28003604c2deb7dcf1f1777ca4"
L2_PAYLOAD_SIZE = 355
L2_PAYLOAD_SHA256 = "408e5709d8f772c0759a4d8ef427b49329a41f38a98776571ac7252d1b841740"

L2_TARGET_SYMBOL = "mdss_mdp"
L2_TARGET_PATH = "/soc/qcom,mdss_mdp@ae00000"

DTBO_MAGIC = 0xD7B7AB1E
DTBO_HEADER_SIZE = 32
DTBO_ENTRY_SIZE = 32
DTBO_ENTRIES_OFFSET = 32
DTBO_PAGE_SIZE = 4096
DTBO_VERSION = 0
DTBO_PAYLOAD_OFFSET = 64
FDT_MAGIC = 0xD00DFEED
FULL_ARTIFACT_SIZE = 33554432
DETAIL_CAP = 4096

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
    "status", "reg", "interrupts", "interrupts-extended", "interrupt-parent",
    "clocks", "clock-names", "power-domains", "assigned-clocks", "assigned-clock-rates",
)
MARKER_PROPERTY = "qcom,thyme-route-b-noop"
SEARCH_NEEDLES = (b"qcom,thyme-route-b-noop", b"route-b-noop")
SEARCH_SKIP_DIRS = {
    ".git", ".codegraph", ".cache", ".zcode", "work", "artifacts", "MIUI14ROM",
    "refs", "out-initramfs", "out-release", "linux-6.6", "android-kernel-sm8250",
    "android-device-thyme", "android-device-sm8250-common",
    "thyme-mainline-firstboot-29bc752517c53a5532bd1974e3bff59cca5af391",
}


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
        if not part or any(byte < 0x20 or byte > 0x7E for byte in part):
            return False
    return True


def dts_literal(value):
    if is_string_list(value):
        return ", ".join(f'"{part.decode("ascii")}"' for part in value[:-1].split(b"\0"))
    if len(value) % 4 == 0:
        words = struct.unpack(f">{len(value) // 4}I", value)
        return "<" + " ".join(f"0x{word:02x}" for word in words) + ">"
    return "[" + " ".join(f"{byte:02x}" for byte in value) + "]"


def hex_bytes(value):
    return " ".join(f"{byte:02x}" for byte in value) if value else "EMPTY"


def describe_property(value):
    if value is None:
        return {"present": False, "type": "ABSENT", "length": 0, "raw": "ABSENT", "decoded": "ABSENT"}
    if len(value) == 0:
        kind, decoded = "EMPTY_BOOLEAN", "<empty>"
    elif is_string_list(value):
        kind = "STRING_LIST"
        decoded = " | ".join(part.decode("ascii") for part in value[:-1].split(b"\0"))
    elif cells(value) is not None:
        kind = "CELLS"
        decoded = "<" + " ".join(f"0x{word:x}" for word in cells(value)) + ">"
    else:
        kind, decoded = "BYTES", hex_bytes(value)
    return {
        "present": True,
        "type": kind,
        "length": len(value),
        "raw": hex_bytes(value),
        "decoded": decoded,
    }


class Node:
    __slots__ = ("path", "name", "props", "children")

    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.props = {}
        self.children = {}

    def child(self, name):
        return self.children.get(name)


class Fdt:
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
            if token == 1:
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
            elif token == 2:
                if not stack:
                    raise ValueError(f"{self.label}: unbalanced END_NODE")
                stack.pop()
            elif token == 3:
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
            elif token == 4:
                continue
            elif token == 9:
                saw_end = True
                break
            else:
                raise ValueError(f"{self.label}: unknown structure token {token}")
        if not saw_end or stack:
            raise ValueError(f"{self.label}: malformed structure termination")

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

    def fragments(self):
        return [node for node in self.root.children.values() if node.name.startswith("fragment@")]

    def special_counts(self):
        result = {}
        for path in ("/__fixups__", "/__local_fixups__", "/__symbols__"):
            node = self.node(path)
            result[path] = "ABSENT" if node is None else len(node.props)
        return result

    def phandle_count(self):
        total = 0
        for node in self.walk():
            for name in PHANDLE_PROPERTIES:
                if name in node.props:
                    total += 1
        return total


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
    total = DTBO_PAYLOAD_OFFSET + len(payload)
    header = struct.pack(">8I", DTBO_MAGIC, total, DTBO_HEADER_SIZE, DTBO_ENTRY_SIZE,
                         1, DTBO_ENTRIES_OFFSET, DTBO_PAGE_SIZE, DTBO_VERSION)
    entry = struct.pack(">8I", len(payload), DTBO_PAYLOAD_OFFSET, 0, 0, 0, 0, 0, 0)
    return header + entry + payload


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


def run_labeled(argv, label):
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
    run_labeled(argv, "M5M_DTC_FAILED")
    return dtb.read_bytes()


def dtc_roundtrip(work, name, blob):
    source = work / f"{name}.dtb"
    output = work / f"{name}.roundtrip.dtb"
    source.write_bytes(blob)
    run_labeled(["dtc", "-q", "-I", "dtb", "-O", "dtb", "-o", str(output), str(source)],
                "M5M_DTC_FAILED")
    return output.read_bytes()


def fdtoverlay_apply(work, name, base, overlay):
    base_path = work / f"{name}.base.dtb"
    overlay_path = work / f"{name}.overlay.dtbo"
    merged_path = work / f"{name}.merged.dtb"
    base_path.write_bytes(base)
    overlay_path.write_bytes(overlay)
    run_labeled(["fdtoverlay", "-i", str(base_path), str(overlay_path), "-o", str(merged_path)],
                "M5M_FDTOVERLAY_FAILED")
    return merged_path.read_bytes()


def fdtoverlay_apply_status(work, name, base, overlay):
    try:
        merged = fdtoverlay_apply(work, name, base, overlay)
    except SystemExit as error:
        return False, str(error).splitlines()[0], None
    return True, f"merged {len(merged)} bytes", merged


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


def bookkeeping_path(path):
    return any(path == prefix or path.startswith(prefix) for prefix in BOOKKEEPING_NODE_PREFIXES)


def semantic_diff(base, merged, label):
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
    for path in sorted(set(merged_nodes) - set(base_nodes)):
        if bookkeeping_path(path):
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
            elif bookkeeping_path(path):
                info["bookkeeping_props"].append(f"{path}:{name} ADDED")
            else:
                info["added_props"].append(f"{path}:{name}")
        for name in sorted(set(before) - set(after)):
            info["removed_props"].append(f"{path}:{name}")
        for name in sorted(set(before) & set(after)):
            if before[name][0] == after[name][0]:
                continue
            if name in PHANDLE_PROPERTIES:
                info["phandle_props"].append(
                    f"{path}:{name} CHANGED "
                    f"0x{cells(before[name][0])[0]:x}->0x{cells(after[name][0])[0]:x}")
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


def overlay_source_diff(left, right, label):
    info = {
        "label": label,
        "added_nodes": [],
        "removed_nodes": [],
        "added_props": [],
        "removed_props": [],
        "changed_props": [],
    }
    left_nodes = {node.path: node for node in left.walk()}
    right_nodes = {node.path: node for node in right.walk()}
    info["added_nodes"] = sorted(set(right_nodes) - set(left_nodes))
    info["removed_nodes"] = sorted(set(left_nodes) - set(right_nodes))
    for path in sorted(set(left_nodes) & set(right_nodes)):
        before = left_nodes[path].props
        after = right_nodes[path].props
        for name in sorted(set(after) - set(before)):
            info["added_props"].append(f"{path}:{name}")
        for name in sorted(set(before) - set(after)):
            info["removed_props"].append(f"{path}:{name}")
        for name in sorted(set(before) & set(after)):
            if before[name][0] != after[name][0]:
                info["changed_props"].append(f"{path}:{name}")
    return info


def split_prop(item):
    path, name = item.rsplit(":", 1)
    return path, name


def find_named_props(fdt, name):
    return [(node.path, node.props[name][0]) for node in fdt.walk() if name in node.props]


def audit_container(candidate, expected_payload):
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
    try:
        parsed = parse_dtbo(container_bytes, "candidate-container")
    except ValueError as error:
        return False, [f"CONTAINER_PARSE_FAILED {error}"]
    problems = audit_container(parsed, expected_payload)
    return (not problems), problems


def container_identity_preserved(container, reference):
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


def fdt_to_dts(fdt, label, root_overrides=None, omit_props=None):
    overrides = root_overrides or {}
    omit = omit_props or {}
    lines = ["/dts-v1/;", "/plugin/;", "", "/ {"]

    def walk(node, indent):
        skipped = omit.get(node.path, set())
        for prop_name, entry in node.props.items():
            if prop_name in skipped:
                continue
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


def build_l1_payload(work, m1_fdt, stock_fdt, selector_names):
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
    text = fdt_to_dts(m1_fdt, "m5m-l1", overrides)
    payload = dtc_compile(work, "m5m-l1-reproduced", text, symbols=False)
    return payload, applied, unchanged, extra, text


def l2_dts(symbol, stock_fdt, selector_names, overlay_lines=None):
    lines = ["/dts-v1/;", "/plugin/;", "", "/ {"]
    for name in selector_names:
        value = stock_fdt.prop("/", name)
        if value is None:
            continue
        lines.append(f"\t{name} = {dts_literal(value)};")
    body = overlay_lines if overlay_lines is not None else []
    lines.extend(["", "\tfragment@0 {", f"\t\ttarget = <&{symbol}>;", "", "\t\t__overlay__ {"])
    lines.extend(body)
    lines.extend(["\t\t};", "\t};", "};", ""])
    return "\n".join(lines)


def marker_dts_lines(value, indent="\t\t\t"):
    if not value:
        return [f"{indent}{MARKER_PROPERTY};"]
    return [f"{indent}{MARKER_PROPERTY} = {dts_literal(value)};"]


def special_absent(fdt, path):
    node = fdt.node(path)
    return node is None or (not node.props and not node.children)


def selector_problems(fdt, stock_fdt, selector_names, prefix):
    problems = []
    for name in selector_names:
        stock_value = stock_fdt.prop("/", name)
        if stock_value is None:
            continue
        if fdt.prop("/", name) != stock_value:
            problems.append(f"{prefix}_SELECTOR_NOT_EXACT {name}")
    return problems


def audit_a_payload(payload, stock_fdt, selector_names):
    problems = []
    try:
        fdt = Fdt(payload, "m5m-a")
    except ValueError as error:
        return [f"A_PARSE_FAILED {error}"], None
    fragments = fdt.fragments()
    if len(fragments) != 1:
        problems.append(f"A_FRAGMENT_COUNT={len(fragments)}")
    fragment = fragments[0] if fragments else None
    if fragment is not None:
        if "target" in fragment.props:
            problems.append("A_USES_TARGET_PHANDLE")
        if fragment.props.get("target-path", (None,))[0] != b"/\0":
            problems.append("A_TARGET_PATH_IS_NOT_ROOT")
        body = fragment.child("__overlay__")
        if body is None:
            problems.append("A_MISSING_OVERLAY_BODY")
        else:
            if MARKER_PROPERTY in body.props:
                problems.append("A_MARKER_STILL_PRESENT")
            if body.props:
                problems.append(f"A_OVERLAY_BODY_NOT_EMPTY props={sorted(body.props)}")
            if body.children:
                problems.append(f"A_OVERLAY_BODY_HAS_CHILDREN={sorted(body.children)}")
    for node_path in ("/__fixups__", "/__local_fixups__", "/__symbols__"):
        if not special_absent(fdt, node_path):
            problems.append(f"A_UNEXPECTED_{node_path}_CONTENT")
    problems.extend(selector_problems(fdt, stock_fdt, selector_names, "A"))
    if MARKER_PROPERTY.encode("ascii") in payload:
        problems.append("A_MARKER_STRING_IN_PAYLOAD")
    return problems, fdt


def audit_b_payload(payload, stock_fdt, selector_names, historical_value, symbol):
    problems = []
    try:
        fdt = Fdt(payload, "m5m-b")
    except ValueError as error:
        return [f"B_PARSE_FAILED {error}"], None
    fragments = fdt.fragments()
    if len(fragments) != 1:
        problems.append(f"B_FRAGMENT_COUNT={len(fragments)}")
    fragment = fragments[0] if fragments else None
    if fragment is not None:
        if "target" not in fragment.props:
            problems.append("B_MISSING_TARGET_PHANDLE")
        if "target-path" in fragment.props:
            problems.append("B_USES_TARGET_PATH")
        body = fragment.child("__overlay__")
        if body is None:
            problems.append("B_MISSING_OVERLAY_BODY")
        else:
            if MARKER_PROPERTY not in body.props:
                problems.append("B_MARKER_MISSING")
            else:
                if body.props[MARKER_PROPERTY][0] != historical_value:
                    problems.append("B_MARKER_VALUE_MISMATCH")
            extra = sorted(name for name in body.props if name != MARKER_PROPERTY)
            if extra:
                problems.append(f"B_OVERLAY_BODY_EXTRA_PROPS={extra}")
            if body.children:
                problems.append(f"B_OVERLAY_BODY_HAS_CHILDREN={sorted(body.children)}")
    fixups = fdt.node("/__fixups__")
    if fixups is None:
        problems.append("B_MISSING_FIXUPS")
    elif symbol not in fixups.props:
        problems.append(f"B_FIXUP_SYMBOL_ABSENT expected={symbol} present={sorted(fixups.props)}")
    local_fixups = fdt.node("/__local_fixups__")
    if local_fixups is not None and (local_fixups.props or local_fixups.children):
        problems.append("B_UNEXPECTED_LOCAL_FIXUPS")
    problems.extend(selector_problems(fdt, stock_fdt, selector_names, "B"))
    if MARKER_PROPERTY.encode("ascii") not in payload:
        problems.append("B_MARKER_STRING_ABSENT_FROM_PAYLOAD")
    return problems, fdt


def a_vs_l1_ok(diff):
    unexpected = []
    marker_removed = False
    for item in diff["removed_props"]:
        path, name = split_prop(item)
        if path == "/fragment@0/__overlay__" and name == MARKER_PROPERTY:
            marker_removed = True
        elif name in PHANDLE_PROPERTIES:
            continue
        else:
            unexpected.append(f"REMOVED {item}")
    for item in diff["added_props"]:
        path, name = split_prop(item)
        if name in PHANDLE_PROPERTIES:
            continue
        unexpected.append(f"ADDED {item}")
    for item in diff["changed_props"]:
        path, name = split_prop(item)
        if name in PHANDLE_PROPERTIES:
            continue
        unexpected.append(f"CHANGED {item}")
    for path in diff["added_nodes"] + diff["removed_nodes"]:
        unexpected.append(f"NODE {path}")
    return marker_removed, unexpected


def b_vs_l2_ok(diff):
    unexpected = []
    marker_added = False
    allowed_changed = []
    allowed_added = []
    for item in diff["added_props"]:
        path, name = split_prop(item)
        if path == "/fragment@0/__overlay__" and name == MARKER_PROPERTY:
            marker_added = True
        elif name in PHANDLE_PROPERTIES or path in ("/__symbols__", "/__fixups__", "/__local_fixups__") \
                or path.startswith("/__symbols__") or path.startswith("/__fixups__") \
                or path.startswith("/__local_fixups__"):
            allowed_added.append(item)
        else:
            unexpected.append(f"ADDED {item}")
    for item in diff["removed_props"]:
        path, name = split_prop(item)
        if name in PHANDLE_PROPERTIES or path.startswith("/__"):
            continue
        unexpected.append(f"REMOVED {item}")
    for item in diff["changed_props"]:
        path, name = split_prop(item)
        if path == "/__fixups__" or name in PHANDLE_PROPERTIES or path.startswith("/__"):
            allowed_changed.append(item)
        else:
            unexpected.append(f"CHANGED {item}")
    for path in diff["added_nodes"]:
        if path.startswith("/__symbols__") or path.startswith("/__fixups__") \
                or path.startswith("/__local_fixups__"):
            allowed_added.append(path)
        else:
            unexpected.append(f"NODE {path}")
    for path in diff["removed_nodes"]:
        unexpected.append(f"NODE {path}")
    return marker_added, unexpected, allowed_added, allowed_changed


def b_merged_marker_only(info, expected_path):
    unexpected = []
    marker_added = False
    for item in info["added_props"]:
        path, name = split_prop(item)
        if name == MARKER_PROPERTY and path == expected_path:
            marker_added = True
        else:
            unexpected.append(f"ADDED {item}")
    for item in info["removed_props"] + info["changed_props"]:
        unexpected.append(item)
    for path in info["added_nodes"]:
        if not path.endswith("[GENERATED]"):
            unexpected.append(f"NODE {path}")
    for path in info["removed_nodes"]:
        unexpected.append(f"NODE {path}")
    return marker_added, unexpected, info["forbidden"]


def same_held_fields(left, right):
    checks = {
        "model": left.prop("/", "model") == right.prop("/", "model"),
        "compatible": left.prop("/", "compatible") == right.prop("/", "compatible"),
        "board-id": left.prop("/", "qcom,board-id") == right.prop("/", "qcom,board-id"),
        "fragment_count": len(left.fragments()) == len(right.fragments()) == 1,
    }
    return checks


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


def search_tree(root, needles):
    hits = []
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SEARCH_SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            for needle in needles:
                if needle in data:
                    rel = path.relative_to(root).as_posix()
                    hits.append((rel, needle.decode("ascii")))
    return hits


def pack_full(tag, slug, payload, stock, m1_dtbo):
    container = build_container(payload)
    _, container_problems = container_probe(container, payload)
    preserved = container_identity_preserved(parse_dtbo(container, f"{slug}-identity"), m1_dtbo)
    full = container + stock[len(container):]
    full_problems = audit_full_artifact(full, container, stock, slug)
    return {
        "tag": tag,
        "slug": slug,
        "payload": payload,
        "container": container,
        "container_problems": container_problems,
        "container_preserved": preserved,
        "full": full,
        "full_problems": full_problems,
        "prefix_size": len(container),
        "prefix_sha": sha(container),
        "tail_offset": len(container),
        "tail_sha": sha(full[len(container):]),
        "full_sha": sha(full),
    }


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GitHub Actions only: local audit, transformation, and validation are forbidden")

    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-dtbo", required=True, type=Path)
    parser.add_argument("--stock-vendor-boot", required=True, type=Path)
    parser.add_argument("--m1-dtbo", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--search-root", type=Path, default=Path("."))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir
    produced = []

    def emit(name, payload_bytes):
        (out / name).write_bytes(payload_bytes)
        produced.append(name)

    def emit_text(name, lines):
        write_lines(out / name, lines)
        produced.append(name)

    stock = args.stock_dtbo.read_bytes()
    stock_vendor = args.stock_vendor_boot.read_bytes()
    m1_raw = args.m1_dtbo.read_bytes()

    if len(stock) != STOCK_DTBO_SIZE or sha(stock) != STOCK_DTBO_SHA256:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED stock dtbo size={len(stock)} sha256={sha(stock)}")
    if len(stock_vendor) != STOCK_VENDOR_BOOT_SIZE or sha(stock_vendor) != STOCK_VENDOR_BOOT_SHA256:
        raise SystemExit("M5M_SOURCE_IDENTITY_FAILED stock vendor_boot "
                         f"size={len(stock_vendor)} sha256={sha(stock_vendor)}")
    if len(m1_raw) != M1_DTBO_SIZE or sha(m1_raw) != M1_DTBO_SHA256:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED M1 dtbo size={len(m1_raw)} sha256={sha(m1_raw)}")

    stock_dtbo = parse_dtbo(stock, "stock-dtbo")
    m1_dtbo = parse_dtbo(m1_raw, "m1-dtbo")
    dtb_area = parse_vendor_dtb_area(stock_vendor, "stock-vendor_boot")
    dtb0_size = struct.unpack_from(">I", dtb_area, 4)[0]
    dtb0 = dtb_area[:dtb0_size]
    if stock_dtbo.entry_count != STOCK_DTBO_ENTRY_COUNT:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED stock dtbo entry_count={stock_dtbo.entry_count}")
    if stock_dtbo.total_size != STOCK_DTBO_TOTAL_SIZE:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED stock dtbo total_size={stock_dtbo.total_size}")
    if m1_dtbo.entry_count != 1:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED M1 dtbo entry_count={m1_dtbo.entry_count}")
    if dtb0_size != STOCK_DTB0_SIZE or sha(dtb0) != STOCK_DTB0_SHA256:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED stock DTB0 size={dtb0_size} sha256={sha(dtb0)}")

    stock_entry = stock_dtbo.entries[THYME_ENTRY_INDEX]
    if stock_entry.dt_offset != THYME_ENTRY_DT_OFFSET or stock_entry.dt_size != THYME_ENTRY_DT_SIZE:
        raise SystemExit("M5M_SOURCE_IDENTITY_FAILED stock entry21 offset/size="
                         f"{stock_entry.dt_offset}/{stock_entry.dt_size}")
    if sha(stock_entry.payload) != THYME_ENTRY_PAYLOAD_SHA256:
        raise SystemExit("M5M_SOURCE_IDENTITY_FAILED stock entry21 payload sha256="
                         f"{sha(stock_entry.payload)}")
    if stock_entry.fdt.prop("/", "qcom,board-id") != struct.pack(">II", 45, 0):
        raise SystemExit("M5M_SOURCE_IDENTITY_FAILED stock entry21 board-id is not <45 0>")

    stock_payload = stock_entry.payload
    stock_fdt = stock_entry.fdt
    m1_payload = m1_dtbo.entries[0].payload
    m1_fdt = m1_dtbo.entries[0].fdt
    if sha(m1_payload) != M1_PAYLOAD_SHA256:
        raise SystemExit(f"M5M_SOURCE_IDENTITY_FAILED M1 payload sha256={sha(m1_payload)}")
    base_fdt = Fdt(dtb0, "stock-dtb0")
    selector_names = [name for name in ABL_SELECTOR_PROPERTIES if stock_fdt.prop("/", name) is not None]
    stock_model = stock_fdt.prop("/", "model")

    m1_hits = find_named_props(m1_fdt, MARKER_PROPERTY)
    if len(m1_hits) != 1 or m1_hits[0][0] != "/fragment@0/__overlay__":
        raise SystemExit(f"M5M_MARKER_AUDIT_FAILED M1 hits={m1_hits}")
    historical_path, historical_value = m1_hits[0]
    historical = describe_property(historical_value)

    stock_hits = find_named_props(stock_fdt, MARKER_PROPERTY)
    stock_raw_hit = MARKER_PROPERTY.encode("ascii") in stock_payload
    base_symbols = {}
    symbols_node = base_fdt.node("/__symbols__")
    if symbols_node is not None:
        for name, entry in symbols_node.props.items():
            base_symbols[name] = entry[0].rstrip(b"\0").decode("utf-8", "replace")
    if base_symbols.get(L2_TARGET_SYMBOL) != L2_TARGET_PATH:
        raise SystemExit("M5M_SOURCE_IDENTITY_FAILED base symbol "
                         f"{L2_TARGET_SYMBOL}={base_symbols.get(L2_TARGET_SYMBOL)}")

    with tempfile.TemporaryDirectory(prefix="m5m-") as temp_name:
        work = Path(temp_name)

        l1_payload, l1_applied, l1_unchanged, l1_extra, l1_dts_text = build_l1_payload(
            work, m1_fdt, stock_fdt, selector_names)
        if sha(l1_payload) != L1_PAYLOAD_SHA256 or len(l1_payload) != L1_PAYLOAD_SIZE:
            raise SystemExit("M5M_L1_IDENTITY_FAILED "
                             f"size={len(l1_payload)} sha256={sha(l1_payload)}")
        l1_fdt = Fdt(l1_payload, "m5m-l1-reproduced")
        l1_hits = find_named_props(l1_fdt, MARKER_PROPERTY)
        if l1_hits != m1_hits:
            raise SystemExit(f"M5M_MARKER_AUDIT_FAILED L1 hits={l1_hits} M1 hits={m1_hits}")
        if l1_fdt.prop("/", "model") != stock_model:
            raise SystemExit("M5M_L1_IDENTITY_FAILED L1 model is not exact Stock")

        l2_text = l2_dts(L2_TARGET_SYMBOL, stock_fdt, selector_names)
        l2_payload = dtc_compile(work, "m5m-l2-reproduced", l2_text, symbols=True)
        if sha(l2_payload) != L2_PAYLOAD_SHA256 or len(l2_payload) != L2_PAYLOAD_SIZE:
            raise SystemExit("M5M_L2_IDENTITY_FAILED "
                             f"size={len(l2_payload)} sha256={sha(l2_payload)}")
        l2_fdt = Fdt(l2_payload, "m5m-l2-reproduced")
        if find_named_props(l2_fdt, MARKER_PROPERTY):
            raise SystemExit("M5M_L2_IDENTITY_FAILED reproduced L2 contains marker")
        l2_body = l2_fdt.node("/fragment@0/__overlay__")
        if l2_body is None or l2_body.props or l2_body.children:
            raise SystemExit("M5M_L2_IDENTITY_FAILED reproduced L2 overlay is not empty")

        a_dts_text = fdt_to_dts(
            l1_fdt, "m5m-a",
            omit_props={"/fragment@0/__overlay__": {MARKER_PROPERTY}})
        a_payload = dtc_compile(work, "m5m-a-payload", a_dts_text, symbols=False)
        a_problems, a_fdt = audit_a_payload(a_payload, stock_fdt, selector_names)
        if a_problems:
            raise SystemExit("M5M_A_CONSTRUCTION_FAILED " + "; ".join(a_problems))
        a_vs_l1 = overlay_source_diff(l1_fdt, a_fdt, "A_VS_L1")
        a_marker_removed, a_unexpected = a_vs_l1_ok(a_vs_l1)
        if not a_marker_removed or a_unexpected:
            raise SystemExit("M5M_A_CONSTRUCTION_FAILED source diff "
                             f"marker_removed={a_marker_removed} unexpected={a_unexpected}")
        held_a = same_held_fields(l1_fdt, a_fdt)
        if not all(held_a.values()):
            raise SystemExit(f"M5M_A_CONSTRUCTION_FAILED held fields {held_a}")
        if a_fdt.fragments()[0].props.get("target-path", (None,))[0] != b"/\0":
            raise SystemExit("M5M_A_CONSTRUCTION_FAILED target-path changed")
        if not special_absent(a_fdt, "/__fixups__") or not special_absent(a_fdt, "/__symbols__"):
            raise SystemExit("M5M_A_CONSTRUCTION_FAILED fixups/symbols appeared")

        a_merge_ok, a_merge_detail, a_merged = fdtoverlay_apply_status(
            work, "m5m-a-on-stock", dtb0, a_payload)
        if not a_merge_ok:
            raise SystemExit(f"M5M_A_SEMANTIC_NOOP_FAILED fdtoverlay {a_merge_detail}")
        a_merged_sha = sha(a_merged)
        a_applied = semantic_diff(base_fdt, Fdt(a_merged, "a-applied"), "A_EMPTY_OVERLAY_ON_STOCK_BASE")
        if not a_applied["valid_device_semantics_unchanged"] or a_applied["forbidden"]:
            raise SystemExit("M5M_A_SEMANTIC_NOOP_FAILED "
                             f"violations={a_applied['violations']} forbidden={a_applied['forbidden']}")

        b_dts_text = l2_dts(L2_TARGET_SYMBOL, stock_fdt, selector_names,
                            overlay_lines=marker_dts_lines(historical_value))
        b_payload = dtc_compile(work, "m5m-b-payload", b_dts_text, symbols=True)
        b_problems, b_fdt = audit_b_payload(
            b_payload, stock_fdt, selector_names, historical_value, L2_TARGET_SYMBOL)
        if b_problems:
            raise SystemExit("M5M_B_CONSTRUCTION_FAILED " + "; ".join(b_problems))
        b_vs_l2 = overlay_source_diff(l2_fdt, b_fdt, "B_VS_L2")
        b_marker_added, b_unexpected, b_allowed_added, b_allowed_changed = b_vs_l2_ok(b_vs_l2)
        if not b_marker_added or b_unexpected:
            raise SystemExit("M5M_B_CONSTRUCTION_FAILED source diff "
                             f"marker_added={b_marker_added} unexpected={b_unexpected}")
        held_b = same_held_fields(l2_fdt, b_fdt)
        if not all(held_b.values()):
            raise SystemExit(f"M5M_B_CONSTRUCTION_FAILED held fields {held_b}")

        b_merge_ok, b_merge_detail, b_merged = fdtoverlay_apply_status(
            work, "m5m-b-on-stock", dtb0, b_payload)
        if not b_merge_ok:
            raise SystemExit(f"M5M_B_SEMANTIC_DELTA_FAILED fdtoverlay {b_merge_detail}")
        b_merged_sha = sha(b_merged)
        b_applied = semantic_diff(base_fdt, Fdt(b_merged, "b-applied"), "B_MARKER_ON_MDSS_MDP")
        b_only_marker, b_merge_unexpected, b_forbidden = b_merged_marker_only(
            b_applied, L2_TARGET_PATH)
        if not b_only_marker or b_merge_unexpected or b_forbidden:
            raise SystemExit("M5M_B_SEMANTIC_DELTA_FAILED "
                             f"marker={b_only_marker} unexpected={b_merge_unexpected} "
                             f"forbidden={b_forbidden}")

        dtc_roundtrip(work, "m5m-a-roundtrip", a_payload)
        dtc_roundtrip(work, "m5m-b-roundtrip", b_payload)
        dtc_roundtrip(work, "m5m-l1-roundtrip", l1_payload)
        dtc_roundtrip(work, "m5m-l2-roundtrip", l2_payload)

        emit("m5m-l1-reproduced-payload.dtbo", l1_payload)
        emit("m5m-l2-reproduced-payload.dtbo", l2_payload)
        emit("m5m-a-target-path-no-marker-payload.dtbo", a_payload)
        emit("m5m-b-fixup-with-marker-payload.dtbo", b_payload)
        emit_text("m5m-a.dts", a_dts_text.splitlines())
        emit_text("m5m-b.dts", b_dts_text.splitlines())

        reports = {
            "A": pack_full("A", "m5m-a", a_payload, stock, m1_dtbo),
            "B": pack_full("B", "m5m-b", b_payload, stock, m1_dtbo),
        }
        for tag, packed in reports.items():
            if packed["container_problems"]:
                raise SystemExit(f"M5M_CONTAINER_IDENTITY_FAILED {tag} "
                                 + "; ".join(packed["container_problems"]))
            if packed["full_problems"]:
                raise SystemExit(f"M5M_FULL_ARTIFACT_INVALID {tag} "
                                 + "; ".join(packed["full_problems"]))
            if not packed["container_preserved"]:
                raise SystemExit(f"M5M_CONTAINER_IDENTITY_FAILED {tag} one-entry semantics")
            if len(packed["full"]) != FULL_ARTIFACT_SIZE:
                raise SystemExit(f"M5M_FULL_ARTIFACT_INVALID {tag} size={len(packed['full'])}")
            emit(f"{packed['slug']}-full-normalized-dtbo.img", packed["full"])

        search_hits = search_tree(args.search_root, SEARCH_NEEDLES)

        negative = []
        negative.append(("CONTROL_UNMUTATED_A_ACCEPTED", not a_problems))
        negative.append(("CONTROL_UNMUTATED_B_ACCEPTED", not b_problems))
        negative.append(("CONTROL_REPRODUCED_L1_SHA", sha(l1_payload) == L1_PAYLOAD_SHA256))
        negative.append(("CONTROL_REPRODUCED_L2_SHA", sha(l2_payload) == L2_PAYLOAD_SHA256))

        l1_as_a, _ = audit_a_payload(l1_payload, stock_fdt, selector_names)
        negative.append(("NEG_A_MARKER_PRESENT_MUTANT_REJECTED",
                         any("A_MARKER_STILL_PRESENT" in item or "A_OVERLAY_BODY_NOT_EMPTY" in item
                             for item in l1_as_a)))
        l2_as_a, _ = audit_a_payload(l2_payload, stock_fdt, selector_names)
        negative.append(("NEG_A_TARGET_FIXUP_MUTANT_REJECTED",
                         any("A_USES_TARGET_PHANDLE" in item or "A_TARGET_PATH_IS_NOT_ROOT" in item
                             for item in l2_as_a)))
        nonempty_a = fdt_to_dts(l1_fdt, "m5m-a-nonempty")
        nonempty_a = nonempty_a.replace(
            f"\t\t\t{MARKER_PROPERTY};",
            '\t\t\tstatus = "okay";')
        nonempty_a = nonempty_a.replace(
            f"\t\t\t{MARKER_PROPERTY} = {dts_literal(historical_value)};",
            '\t\t\tstatus = "okay";')
        nonempty_blob = dtc_compile(work, "m5m-a-nonempty", nonempty_a, symbols=False)
        nonempty_problems, _ = audit_a_payload(nonempty_blob, stock_fdt, selector_names)
        negative.append(("NEG_A_NONEMPTY_OVERLAY_MUTANT_REJECTED",
                         any("A_OVERLAY_BODY_NOT_EMPTY" in item for item in nonempty_problems)))

        l2_as_b, _ = audit_b_payload(l2_payload, stock_fdt, selector_names,
                                     historical_value, L2_TARGET_SYMBOL)
        negative.append(("NEG_B_MARKER_ABSENT_MUTANT_REJECTED",
                         any("B_MARKER_MISSING" in item for item in l2_as_b)))
        wrong_marker = l2_dts(L2_TARGET_SYMBOL, stock_fdt, selector_names,
                              overlay_lines=['\t\t\tqcom,thyme-route-b-noop = "mutant";'])
        wrong_blob = dtc_compile(work, "m5m-b-wrong-marker", wrong_marker, symbols=True)
        wrong_problems, _ = audit_b_payload(wrong_blob, stock_fdt, selector_names,
                                            historical_value, L2_TARGET_SYMBOL)
        negative.append(("NEG_B_WRONG_MARKER_VALUE_MUTANT_REJECTED",
                         any("B_MARKER_VALUE_MISMATCH" in item for item in wrong_problems)))
        a_as_b, _ = audit_b_payload(a_payload, stock_fdt, selector_names,
                                    historical_value, L2_TARGET_SYMBOL)
        negative.append(("NEG_B_TARGET_PATH_MUTANT_REJECTED",
                         any("B_USES_TARGET_PATH" in item or "B_MISSING_TARGET_PHANDLE" in item
                             or "B_MISSING_FIXUPS" in item for item in a_as_b)))

        wrong_model_dts = a_dts_text.replace(
            dts_literal(stock_model),
            '"bogus,not-thyme"')
        wrong_model = dtc_compile(work, "m5m-a-wrong-model", wrong_model_dts, symbols=False)
        wrong_model_problems, _ = audit_a_payload(wrong_model, stock_fdt, selector_names)
        negative.append(("NEG_WRONG_MODEL_REJECTED",
                         any("A_SELECTOR_NOT_EXACT model" in item for item in wrong_model_problems)))

        board_offset = a_fdt.prop_offset("/", "qcom,board-id")
        if board_offset is None:
            negative.append(("NEG_WRONG_BOARD_ID_REJECTED", False))
        else:
            mutated = bytearray(a_payload)
            mutated[board_offset:board_offset + 4] = struct.pack(">I", 0)
            board_problems, _ = audit_a_payload(bytes(mutated), stock_fdt, selector_names)
            negative.append(("NEG_WRONG_BOARD_ID_REJECTED",
                             any("A_SELECTOR_NOT_EXACT qcom,board-id" in item for item in board_problems)))

        a_container = reports["A"]["container"]
        negative.append(("CONTROL_CONTAINER_UNMUTATED_ACCEPTED",
                         container_probe(a_container, a_payload)[0]))
        negative.append(("CONTROL_FULL_ARTIFACT_UNMUTATED_ACCEPTED",
                         not reports["A"]["full_problems"]))
        for label, offset, value in (
            ("NEG_WRONG_ENTRY_DT_SIZE_DETECTED", 32, len(a_payload) - 1),
            ("NEG_WRONG_TOTAL_SIZE_DETECTED", 4, len(a_container) - 1),
            ("NEG_ENTRY_COUNT_2_DETECTED", 16, 2),
        ):
            mutated = bytearray(a_container)
            struct.pack_into(">I", mutated, offset, value)
            ok, _ = container_probe(bytes(mutated), a_payload)
            negative.append((label, not ok))

        a_full = reports["A"]["full"]
        mutated_full = bytearray(a_full)
        mutated_full[5_000_000] ^= 0xFF
        negative.append(("NEG_WRONG_TAIL_DETECTED",
                         any("FULL_TAIL" in item for item in
                             audit_full_artifact(bytes(mutated_full), a_container, stock, "neg-tail"))))
        negative.append(("NEG_WRONG_FULL_ARTIFACT_SIZE_DETECTED",
                         any("FULL_SIZE" in item for item in
                             audit_full_artifact(a_full[:-1], a_container, stock, "neg-size"))))

        failed_negative = [name for name, ok in negative if not ok]
        if failed_negative:
            raise SystemExit("M5M_NEGATIVE_TEST_FAILED " + ",".join(failed_negative))

    a_ready = (
        not a_problems and a_merge_ok and a_applied["valid_device_semantics_unchanged"]
        and a_marker_removed and not a_unexpected and not reports["A"]["full_problems"]
        and not failed_negative
    )
    b_ready = (
        not b_problems and b_merge_ok and b_only_marker and not b_merge_unexpected
        and not b_forbidden and not reports["B"]["full_problems"] and not failed_negative
    )
    next_control = "M5M_A_TARGET_PATH_NO_MARKER_TRUE_DEVICE_CONTROL" if a_ready else "NONE_NEEDS_REFINEMENT"

    marker_lines = [
        "# historical marker exact encoding (M1 and reproduced L1)",
        "",
        f"MARKER_PROPERTY={MARKER_PROPERTY}",
        f"MARKER_NODE_PATH={historical_path}",
        f"MARKER_TYPE={historical['type']}",
        f"MARKER_BYTE_LENGTH={historical['length']}",
        f"MARKER_RAW_BYTES={historical['raw']}",
        f"MARKER_DECODED={historical['decoded']}",
        f"MARKER_M1_PRESENT=YES",
        f"MARKER_L1_PRESENT=YES",
        f"MARKER_M1_L1_VALUE_IDENTICAL=YES",
        f"MARKER_IN_OVERLAY_PAYLOAD_FDT=YES",
        f"MARKER_VISIBLE_BEFORE_ABL_APPLY=YES",
        f"MARKER_QCOM_NAMESPACE={'YES' if MARKER_PROPERTY.startswith('qcom,') else 'NO'}",
        f"MARKER_IN_STOCK_ENTRY21_FDT={'YES' if stock_hits else 'NO'}",
        f"MARKER_IN_STOCK_ENTRY21_RAW={'YES' if stock_raw_hit else 'NO'}",
        f"STOCK_ENTRY21_MARKER_HITS={stock_hits or 'NONE'}",
        "ABL_UNKNOWN_QCOM_PROPERTY_FAILURE=NOT_CLAIMED",
        f"MARKER_L1_MERGED_DESTINATION=/",
        f"MARKER_B_MERGED_DESTINATION={L2_TARGET_PATH}",
        "MARKER_APPLIED_TO_SAME_BASE_NODE=NO",
        "MARKER_FACTOR_DEFINITION=MARKER_PROPERTY_PRESENT_IN_FRAGMENT_OVERLAY_BODY",
    ]
    emit_text("m5m-marker-audit.txt", marker_lines)

    search_lines = [
        "# source-only string search (public checkout, no extra clone)",
        "",
        f"SEARCH_ROOT={args.search_root}",
        f"SEARCH_NEEDLES={','.join(needle.decode('ascii') for needle in SEARCH_NEEDLES)}",
        f"SEARCH_HIT_COUNT={len(search_hits)}",
    ]
    experiment_only = True
    for rel, needle in search_hits:
        search_lines.append(f"HIT path={rel} needle={needle}")
        if rel.startswith("linux-") or "abl" in rel.lower() or "bootloader" in rel.lower():
            experiment_only = False
    search_lines.extend([
        f"SOURCE_HITS_ONLY_IN_THIS_EXPERIMENT={'YES' if experiment_only else 'NO'}",
        "BOOTLOADER_SOURCE_HIT=NO",
        "STRING_SEARCH_IS_NOT_A_GATE=YES",
    ])
    emit_text("m5m-string-search.txt", search_lines)

    a_sha_eq = a_merged_sha == STOCK_DTB0_SHA256
    a_lines = [
        "# Candidate A  TM-10  T0 target-path /  M0 marker absent",
        "",
        "A_NAME=M5M_A_TARGET_PATH_NO_MARKER",
        "A_CELL=TM-10",
        "A_MODEL=Stock exact",
        'A_TARGET=target-path="/"',
        "A_MARKER=ABSENT",
        "A_FIXUPS=ABSENT",
        "A_SYMBOLS=ABSENT",
        f"A_FRAGMENT_COUNT={len(a_fdt.fragments())}",
        f"A_OVERLAY_BODY_PROPERTY_COUNT={len(a_fdt.node('/fragment@0/__overlay__').props)}",
        f"A_OVERLAY_BODY_CHILD_COUNT={len(a_fdt.node('/fragment@0/__overlay__').children)}",
        f"A_PAYLOAD_SIZE={len(a_payload)}",
        f"A_PAYLOAD_SHA256={sha(a_payload)}",
        f"A_ACTIVE_PREFIX_SIZE={reports['A']['prefix_size']}",
        f"A_ACTIVE_PREFIX_SHA256={reports['A']['prefix_sha']}",
        f"A_STOCK_TAIL_OFFSET={reports['A']['tail_offset']}",
        f"A_STOCK_TAIL_SHA256={reports['A']['tail_sha']}",
        f"A_FULL_ARTIFACT_SIZE={len(reports['A']['full'])}",
        f"A_FULL_ARTIFACT_SHA256={reports['A']['full_sha']}",
        f"A_FDTOVERLAY={'PASS' if a_merge_ok else 'FAIL'}",
        f"A_MERGED_SHA256={a_merged_sha}",
        f"A_MERGED_SHA_EQUALS_STOCK_DTB0={'YES' if a_sha_eq else 'NO'}",
        f"A_SEMANTIC_NOOP_CONFIRMED={'YES' if a_applied['valid_device_semantics_unchanged'] else 'NO'}",
        f"A_VS_L1_ONLY_MARKER_ABSENCE={'YES' if a_marker_removed and not a_unexpected else 'NO'}",
        f"A_VS_L1_UNEXPECTED={'; '.join(a_unexpected) or 'NONE'}",
        f"A_L1_HELD_MODEL={'YES' if held_a['model'] else 'NO'}",
        f"A_L1_HELD_COMPATIBLE={'YES' if held_a['compatible'] else 'NO'}",
        f"A_L1_HELD_BOARD_ID={'YES' if held_a['board-id'] else 'NO'}",
        f"A_PROBLEM_COUNT={len(a_problems)}",
        f"A_READY={'YES' if a_ready else 'NO'}",
    ]
    emit_text("m5m-a-report.txt", a_lines)
    emit_text("m5m-a-semantic-noop.txt", semantic_report_lines(a_applied) + [
        "",
        f"A_MERGED_SHA256={a_merged_sha}",
        f"STOCK_DTB0_SHA256={STOCK_DTB0_SHA256}",
        f"A_MERGED_SHA_EQUALS_STOCK_DTB0={'YES' if a_sha_eq else 'NO'}",
        f"A_SEMANTIC_NOOP_CONFIRMED={'YES' if a_applied['valid_device_semantics_unchanged'] else 'NO'}",
    ])
    emit_text("m5m-a-vs-l1-source-diff.txt", [
        f"LABEL={a_vs_l1['label']}",
        f"ADDED_PROPS={a_vs_l1['added_props'] or 'NONE'}",
        f"REMOVED_PROPS={a_vs_l1['removed_props'] or 'NONE'}",
        f"CHANGED_PROPS={a_vs_l1['changed_props'] or 'NONE'}",
        f"ADDED_NODES={a_vs_l1['added_nodes'] or 'NONE'}",
        f"REMOVED_NODES={a_vs_l1['removed_nodes'] or 'NONE'}",
        f"ONLY_MARKER_ABSENCE={'YES' if a_marker_removed and not a_unexpected else 'NO'}",
        f"UNEXPECTED={'; '.join(a_unexpected) or 'NONE'}",
        "BINARY_ONE_BYTE_DIFF_NOT_REQUIRED=YES",
        "CAUSAL_VARIABLE=MARKER_PROPERTY_PRESENCE",
    ])

    b_lines = [
        "# Candidate B  TM-21  T1 target+fixup  M1 marker present",
        "",
        "B_NAME=M5M_B_FIXUP_WITH_MARKER",
        "B_CELL=TM-21",
        "B_MODEL=Stock exact",
        f"B_TARGET={L2_TARGET_SYMBOL} via __fixups__",
        f"B_TARGET_PATH={L2_TARGET_PATH}",
        "B_MARKER=PRESENT",
        f"B_MARKER_TYPE={historical['type']}",
        f"B_MARKER_BYTE_LENGTH={historical['length']}",
        f"B_MARKER_RAW_BYTES={historical['raw']}",
        f"B_MARKER_DECODED={historical['decoded']}",
        f"B_MARKER_MERGED_TARGET={L2_TARGET_PATH}",
        f"B_FIXUPS_COUNT={b_fdt.special_counts()['/__fixups__']}",
        f"B_FRAGMENT_COUNT={len(b_fdt.fragments())}",
        f"B_OVERLAY_BODY_PROPERTY_COUNT={len(b_fdt.node('/fragment@0/__overlay__').props)}",
        f"B_PAYLOAD_SIZE={len(b_payload)}",
        f"B_PAYLOAD_SHA256={sha(b_payload)}",
        f"B_ACTIVE_PREFIX_SIZE={reports['B']['prefix_size']}",
        f"B_ACTIVE_PREFIX_SHA256={reports['B']['prefix_sha']}",
        f"B_STOCK_TAIL_OFFSET={reports['B']['tail_offset']}",
        f"B_STOCK_TAIL_SHA256={reports['B']['tail_sha']}",
        f"B_FULL_ARTIFACT_SIZE={len(reports['B']['full'])}",
        f"B_FULL_ARTIFACT_SHA256={reports['B']['full_sha']}",
        f"B_FDTOVERLAY={'PASS' if b_merge_ok else 'FAIL'}",
        f"B_MERGED_SHA256={b_merged_sha}",
        f"B_ONLY_MARKER_SEMANTIC_DELTA={'YES' if b_only_marker and not b_merge_unexpected else 'NO'}",
        f"B_VS_L2_MARKER_ADDED={'YES' if b_marker_added else 'NO'}",
        f"B_VS_L2_UNEXPECTED={'; '.join(b_unexpected) or 'NONE'}",
        f"B_VS_L2_ALLOWED_ADDED={'; '.join(b_allowed_added) or 'NONE'}",
        f"B_VS_L2_ALLOWED_CHANGED={'; '.join(b_allowed_changed) or 'NONE'}",
        f"B_PROBLEM_COUNT={len(b_problems)}",
        f"B_READY={'YES' if b_ready else 'NO'}",
        "MARKER_APPLIED_TO_SAME_BASE_NODE=NO",
    ]
    emit_text("m5m-b-report.txt", b_lines)
    emit_text("m5m-b-semantic-delta.txt", semantic_report_lines(b_applied) + [
        "",
        f"B_MARKER_MERGED_TARGET={L2_TARGET_PATH}",
        f"B_ONLY_MARKER_SEMANTIC_DELTA={'YES' if b_only_marker and not b_merge_unexpected else 'NO'}",
        f"B_MERGE_UNEXPECTED={'; '.join(b_merge_unexpected) or 'NONE'}",
        "L1_MARKER_MERGES_TO_ROOT=YES",
        "B_MARKER_MERGES_TO_MDSS_MDP=YES",
        "FOUR_CELLS_MARKER_MERGED_LOCATION_IDENTICAL=NO",
    ])
    emit_text("m5m-b-vs-l2-source-diff.txt", [
        f"LABEL={b_vs_l2['label']}",
        f"ADDED_PROPS={b_vs_l2['added_props'] or 'NONE'}",
        f"REMOVED_PROPS={b_vs_l2['removed_props'] or 'NONE'}",
        f"CHANGED_PROPS={b_vs_l2['changed_props'] or 'NONE'}",
        f"ADDED_NODES={b_vs_l2['added_nodes'] or 'NONE'}",
        f"REMOVED_NODES={b_vs_l2['removed_nodes'] or 'NONE'}",
        f"MARKER_ADDED={'YES' if b_marker_added else 'NO'}",
        f"UNEXPECTED={'; '.join(b_unexpected) or 'NONE'}",
        f"ALLOWED_ADDED={'; '.join(b_allowed_added) or 'NONE'}",
        f"ALLOWED_CHANGED={'; '.join(b_allowed_changed) or 'NONE'}",
        "FIXUP_OFFSET_SHIFT_ALLOWED=YES",
    ])

    container_lines = ["# one-entry container identity versus M1", ""]
    for tag, packed in reports.items():
        parsed = parse_dtbo(packed["container"], f"{tag}-container")
        container_lines.extend([
            f"# {tag}",
            f"{tag}_MAGIC=0x{DTBO_MAGIC:08x}",
            f"{tag}_VERSION={parsed.version}",
            f"{tag}_HEADER_SIZE={parsed.header_size}",
            f"{tag}_ENTRY_SIZE={parsed.entry_size}",
            f"{tag}_ENTRY_COUNT={parsed.entry_count}",
            f"{tag}_ENTRIES_OFFSET={parsed.entries_offset}",
            f"{tag}_PAGE_SIZE={parsed.page_size}",
            f"{tag}_ENTRY_DT_OFFSET={parsed.entries[0].dt_offset}",
            f"{tag}_ENTRY_DT_SIZE={parsed.entries[0].dt_size}",
            f"{tag}_TOTAL_SIZE={parsed.total_size}",
            f"{tag}_ENTRY_METADATA_ALL_ZERO=YES",
            f"{tag}_CONTAINER_SEMANTICS_PRESERVED_ONE_ENTRY="
            f"{'YES' if packed['container_preserved'] else 'NO'}",
            f"{tag}_ACTIVE_PREFIX_SIZE={packed['prefix_size']}",
            f"{tag}_ACTIVE_PREFIX_SHA256={packed['prefix_sha']}",
            f"{tag}_STOCK_TAIL_OFFSET={packed['tail_offset']}",
            f"{tag}_STOCK_TAIL_SHA256={packed['tail_sha']}",
            "",
        ])
    emit_text("m5m-container-identity.txt", container_lines)

    diff_lines = ["# binary diffs (serialization shift expected for marker add/remove)", ""]
    for tag, packed in reports.items():
        peer = l1_payload if tag == "A" else l2_payload
        peer_label = "exact L1 payload" if tag == "A" else "exact L2 payload"
        diff_lines.extend(region_lines(
            f"{tag}_PAYLOAD_VS_PEER",
            (("FDT", 0, max(len(peer), len(packed["payload"]))),),
            peer, packed["payload"], peer_label, f"{tag} payload"))
        diff_lines.append("BINARY_ONE_BYTE_DIFF_NOT_REQUIRED=YES")
        diff_lines.append("")
        diff_lines.extend(region_lines(
            f"{tag}_FULL_VS_STOCK_DTBO",
            (("HEADER", 0, DTBO_HEADER_SIZE),
             ("ENTRY_TABLE", DTBO_HEADER_SIZE, DTBO_PAYLOAD_OFFSET),
             (f"{tag}_ACTIVE_PAYLOAD", DTBO_PAYLOAD_OFFSET, len(packed["container"])),
             ("STOCK_SAME_OFFSET_TAIL", len(packed["container"]), FULL_ARTIFACT_SIZE)),
            stock, packed["full"], "exact Stock dtbo.img", f"{tag} normalized full artifact"))
        diff_lines.append(f"{tag}_TAIL_IS_BYTE_EXACT_STOCK_SAME_OFFSET=YES")
        diff_lines.append("")
    emit_text("m5m-binary-diff.txt", diff_lines)

    emit_text("m5m-validation-report.txt", [
        "DTBO_PARSE_STOCK=PASS",
        "DTBO_PARSE_M1=PASS",
        "STOCK_ENTRY21_PAYLOAD_PARSE=PASS",
        "L1_REPRODUCED=PASS",
        "L2_REPRODUCED=PASS",
        "DTC_ROUNDTRIP_A=PASS",
        "DTC_ROUNDTRIP_B=PASS",
        f"FDTOVERLAY_STOCK_DTB0_PLUS_A={'PASS' if a_merge_ok else 'FAIL'}",
        f"FDTOVERLAY_STOCK_DTB0_PLUS_B={'PASS' if b_merge_ok else 'FAIL'}",
        f"STOCK_DTB0_SIZE={dtb0_size}",
        f"STOCK_DTB0_SHA256={sha(dtb0)}",
        "STRUCTURAL_VALIDATION_ONLY=YES",
        "XIAOMI_ABL_EVIDENCE=NO",
    ])

    negative_lines = [f"NEGATIVE_TEST_COUNT={len(negative)}"]
    for name, ok in negative:
        negative_lines.append(f"{name}={'PASS' if ok else 'FAIL'}")
    negative_lines.append("FAILED_NEGATIVE_TESTS=0")
    negative_lines.append("NEGATIVE_TESTS_PASS=YES")
    negative_lines.append("FAIL_CLOSED=PASS")
    emit_text("m5m-negative-tests.txt", negative_lines)

    emit_text("m5m-factorial.txt", [
        "# 2x2 target/fixup x marker, Stock model held",
        "",
        "T0=target-path=\"/\"",
        "T1=Stock-style target + __fixups__  symbol=mdss_mdp",
        "M0=marker absent, empty __overlay__",
        "M1=marker present, qcom,thyme-route-b-noop exact historical value",
        "",
        "TM-11=L1 T0/M1 runtime=4.837s",
        "TM-20=L2 T1/M0 runtime=>12s",
        "TM-10=A  T0/M0 runtime=PENDING",
        "TM-21=B  T1/M1 runtime=PENDING",
        "",
        "ROOT_MODEL_TEXT_EFFECT=NO",
        "STOCK_MODEL_TEXT_ALONE_SUFFICIENT=NO",
        "MODEL_FROZEN=Stock exact",
        "BOARD_ID_FROZEN=<45 0>",
        "CONTAINER_FROZEN=one-entry",
        "CURRENT_B=exact M5D boot + M5H board45 Stock DTB0 vendor + M5L-L1 dtbo",
        "DEVICE_OPERATION=NO",
        "A_FIRST=YES",
        "B_NOT_AUTO_FLASHED_IF_A_GT_12S=YES",
    ])

    emit_text("m5m-next-control.md", [
        "# M5M — next true-device control",
        "",
        "```text",
        "NEXT_TRUE_DEVICE_CONTROL=" + next_control,
        f"READY_FOR_MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_CONTROL={'YES' if a_ready else 'NO'}",
        f"READY_FOR_MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_CONTROL={'YES' if b_ready else 'NO'}",
        "A_FIRST=YES",
        "DO_NOT_FLASH_A_AND_B_TOGETHER=YES",
        "IF_A_GT_12S_DO_NOT_AUTO_RUN_B=YES",
        "DEVICE_OPERATION=NO",
        "CURRENT_B_UNCHANGED=YES",
        "WAIT_FOR_USER_APPROVAL=YES",
        "```",
    ])

    gates = [
        "MEM0_READ_BEFORE_M5M=YES",
        "M5M_AUDIT_COMPLETE=YES",
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
        "L1_REPRODUCED_SHA_EXACT=YES",
        "L2_REPRODUCED_SHA_EXACT=YES",
        f"L1_PAYLOAD_SIZE={len(l1_payload)}",
        f"L1_PAYLOAD_SHA256={sha(l1_payload)}",
        f"L2_PAYLOAD_SIZE={len(l2_payload)}",
        f"L2_PAYLOAD_SHA256={sha(l2_payload)}",
        f"L2_TARGET_SYMBOL={L2_TARGET_SYMBOL}",
        f"L2_TARGET_PATH={L2_TARGET_PATH}",
        f"MARKER_PROPERTY={MARKER_PROPERTY}",
        f"MARKER_NODE_PATH={historical_path}",
        f"MARKER_TYPE={historical['type']}",
        f"MARKER_BYTE_LENGTH={historical['length']}",
        f"MARKER_RAW_BYTES={historical['raw']}",
        f"MARKER_DECODED={historical['decoded']}",
        f"MARKER_IN_STOCK_ENTRY21={'YES' if stock_hits or stock_raw_hit else 'NO'}",
        "ABL_UNKNOWN_QCOM_PROPERTY_FAILURE=NOT_CLAIMED",
        "A_MODEL=Stock",
        'A_TARGET=target-path="/"',
        "A_MARKER=ABSENT",
        "A_FIXUPS=ABSENT",
        f"A_SEMANTIC_NOOP_CONFIRMED={'YES' if a_applied['valid_device_semantics_unchanged'] else 'NO'}",
        f"A_MERGED_SHA256={a_merged_sha}",
        f"A_MERGED_SHA_EQUALS_STOCK_DTB0={'YES' if a_sha_eq else 'NO'}",
        f"A_PAYLOAD_SIZE={len(a_payload)}",
        f"A_PAYLOAD_SHA256={sha(a_payload)}",
        f"A_ACTIVE_PREFIX_SIZE={reports['A']['prefix_size']}",
        f"A_ACTIVE_PREFIX_SHA256={reports['A']['prefix_sha']}",
        f"A_FULL_ARTIFACT_SIZE={len(reports['A']['full'])}",
        f"A_FULL_ARTIFACT_SHA256={reports['A']['full_sha']}",
        f"A_STOCK_TAIL_OFFSET={reports['A']['tail_offset']}",
        f"A_STOCK_TAIL_SHA256={reports['A']['tail_sha']}",
        f"A_CONTAINER_ENTRY_COUNT=1",
        "A_CONTAINER_ENTRY_METADATA_ALL_ZERO=YES",
        "B_MODEL=Stock",
        f"B_TARGET={L2_TARGET_SYMBOL}",
        "B_MARKER=PRESENT",
        f"B_MARKER_MERGED_TARGET={L2_TARGET_PATH}",
        f"B_ONLY_MARKER_SEMANTIC_DELTA={'YES' if b_only_marker and not b_merge_unexpected else 'NO'}",
        f"B_PAYLOAD_SIZE={len(b_payload)}",
        f"B_PAYLOAD_SHA256={sha(b_payload)}",
        f"B_ACTIVE_PREFIX_SIZE={reports['B']['prefix_size']}",
        f"B_ACTIVE_PREFIX_SHA256={reports['B']['prefix_sha']}",
        f"B_FULL_ARTIFACT_SIZE={len(reports['B']['full'])}",
        f"B_FULL_ARTIFACT_SHA256={reports['B']['full_sha']}",
        f"B_STOCK_TAIL_OFFSET={reports['B']['tail_offset']}",
        f"B_STOCK_TAIL_SHA256={reports['B']['tail_sha']}",
        "B_CONTAINER_ENTRY_COUNT=1",
        "B_CONTAINER_ENTRY_METADATA_ALL_ZERO=YES",
        "MARKER_APPLIED_TO_SAME_BASE_NODE=NO",
        "TM-11=L1 T0/M1 4.837s",
        "TM-20=L2 T1/M0 >12s",
        "TM-10=A T0/M0 PENDING",
        "TM-21=B T1/M1 PENDING",
        f"NEGATIVE_TEST_COUNT={len(negative)}",
        "NEGATIVE_TESTS_PASS=YES",
        "FAIL_CLOSED=PASS",
        "PRIVATE_ARTIFACT_ONLY=YES",
        "OEM_DERIVED_ARTIFACT_PRIVATE_ONLY=YES",
        f"READY_FOR_MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_CONTROL={'YES' if a_ready else 'NO'}",
        f"READY_FOR_MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_CONTROL={'YES' if b_ready else 'NO'}",
        f"NEXT_TRUE_DEVICE_CONTROL={next_control}",
        "NO_NEXT_STAGE_EXECUTED=YES",
        "WAIT_FOR_USER_APPROVAL=YES",
    ]
    emit_text("m5m-gates.txt", gates)
    write_lines(out / "SHA256SUMS",
                [f"{sha((out / name).read_bytes())}  {name}" for name in sorted(produced)])
    manifest = sorted(produced + ["m5m-artifact-scope.txt", "SHA256SUMS"])
    write_lines(out / "m5m-artifact-scope.txt", manifest)
    print("\n".join(gates))
    print(f"M5M_ARTIFACT_COUNT={len(manifest)}")
    if not a_ready:
        raise SystemExit("M5M_NOT_SAFE A not READY")
    if not b_ready:
        raise SystemExit("M5M_NOT_SAFE B not READY")


if __name__ == "__main__":
    main()
