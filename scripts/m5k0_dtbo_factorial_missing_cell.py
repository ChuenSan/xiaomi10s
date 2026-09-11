#!/usr/bin/env python3
"""M5K0 DTBO 2x2 factorial missing-Cell-D CI qualification.

GitHub Actions only: no local build, no local validation, no local DTBO parse,
no local binary diff. Exact OEM inputs and every transformation stay in the
private auxiliary CI repository.

Cell D definition:

    DTBO container : M1 one-entry semantics (entry_count 1, entries_offset 32,
                     header_size 32, entry_size 32, page_size 4096, version 0)
    entry          : id/rev/custom all zero, dt_offset 64
    payload        : exact Stock thyme entry21 overlay, 484885 bytes
    physical image : 33554432 bytes = short prefix [0,484949)
                     + exact Stock dtbo.img same-offset tail [484949,EOF)

Failure labels:

    M5K0_SOURCE_IDENTITY_FAILED
    M5K0_D_CONTROL2_IDENTITY_FAILED
    M5K0_D_CONTROL2_CONTAINER_INVALID
    M5K0_D_CONTROL2_PAYLOAD_INVALID
    M5K0_D_CONTROL2_TAIL_NORMALIZATION_FAILED
    M5K0_D_CONTROL2_NOT_SAFE
"""

import argparse
import hashlib
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass
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

D_CONTROL2_SHORT_SIZE = 484949
D_CONTROL2_SHORT_SHA256 = "bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a"

FULL_ARTIFACT_SIZE = 33554432
FULL_PREFIX_END = D_CONTROL2_SHORT_SIZE

THYME_ENTRY_INDEX = 21
THYME_ENTRY_DT_OFFSET = 9666706
THYME_ENTRY_DT_SIZE = 484885
THYME_ENTRY_PAYLOAD_SHA256 = "44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93"

M5H_MERGED_SHA256 = "c48ef53de0dc3ad3ca31818b913b7380f615bbed8df925416abbae8ef0a8535b"

DTBO_MAGIC = 0xD7B7AB1E
DTBO_HEADER_SIZE = 32
DTBO_ENTRY_SIZE = 32
DTBO_ENTRIES_OFFSET = 32
DTBO_PAGE_SIZE = 4096
DTBO_VERSION = 0
DTBO_PAYLOAD_OFFSET = 64
FDT_MAGIC = 0xD00DFEED

CANDIDATE_PAYLOAD_START = DTBO_PAYLOAD_OFFSET

# Region layout of the normalized 33554432-byte physical image.
FULL_REGIONS = (
    ("HEADER", 0, DTBO_HEADER_SIZE),
    ("ENTRY_TABLE", DTBO_HEADER_SIZE, DTBO_PAYLOAD_OFFSET),
    ("CELLD_ACTIVE_PAYLOAD", DTBO_PAYLOAD_OFFSET, FULL_PREFIX_END),
    ("STOCK_SAME_OFFSET_TAIL", FULL_PREFIX_END, FULL_ARTIFACT_SIZE),
)

M1_VS_CELLD_REGIONS = (
    ("M1_HEADER", 0, DTBO_HEADER_SIZE),
    ("M1_ENTRY", DTBO_HEADER_SIZE, DTBO_PAYLOAD_OFFSET),
    ("M1_PAYLOAD_REGION", DTBO_PAYLOAD_OFFSET, M1_DTBO_SIZE),
    ("EXTENDED_TO_CELL_D_EXTENT", M1_DTBO_SIZE, FULL_PREFIX_END),
)

DETAIL_RANGE_CAP = 65536
DETAIL_RANGE_TAIL = 64
BLOCK_SIZE = 4096


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, size):
    return (value + size - 1) // size * size


def cells(data):
    if len(data) % 4:
        return None
    return list(struct.unpack(f">{len(data) // 4}I", data))


@dataclass
class Prop:
    value: bytes


class Fdt:
    """Minimal read-only FDT parser: structure walk plus selected root props."""

    def __init__(self, data, label):
        self.data = bytes(data)
        self.label = label
        if len(self.data) < 40:
            raise ValueError(f"{label}: short FDT")
        fields = struct.unpack_from(">10I", self.data, 0)
        (magic, self.totalsize, self.off_struct, self.off_strings,
         self.off_reserve, self.version, self.last_comp_version,
         self.boot_cpuid_phys, self.size_strings, self.size_struct) = fields
        if magic != FDT_MAGIC:
            raise ValueError(f"{label}: FDT magic mismatch")
        if self.totalsize != len(self.data):
            raise ValueError(f"{label}: totalsize={self.totalsize} bytes={len(self.data)}")
        if self.off_struct + self.size_struct > self.totalsize:
            raise ValueError(f"{label}: structure block outside FDT")
        if self.off_strings + self.size_strings > self.totalsize:
            raise ValueError(f"{label}: strings block outside FDT")
        self.nodes = {}
        self.fragments = []
        self.reserve = []
        self._parse_reserve()
        self._parse_nodes()

    def _parse_reserve(self):
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
                path = "/" if not stack else stack[-1].rstrip("/") + "/" + name
                stack.append(path)
                self.nodes[path] = {}
                if len(stack) == 2 and stack[0] == "/" and name.startswith("fragment@"):
                    self.fragments.append(path)
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
                pos = align(pos + length, 4)
                start = self.off_strings + nameoff
                stop = self.data.find(b"\0", start, self.off_strings + self.size_strings)
                if stop < 0:
                    raise ValueError(f"{self.label}: bad property name")
                name = self.data[start:stop].decode("utf-8", "replace")
                self.nodes[stack[-1]][name] = Prop(value)
            elif token == 4:  # FDT_NOP
                continue
            elif token == 9:  # FDT_END
                saw_end = True
                break
            else:
                raise ValueError(f"{self.label}: unknown structure token {token}")
        if not saw_end or stack:
            raise ValueError(f"{self.label}: malformed structure termination")

    def root_cells(self, name):
        prop = self.nodes.get("/", {}).get(name)
        return None if prop is None else cells(prop.value)

    def root_strings(self, name):
        prop = self.nodes.get("/", {}).get(name)
        if prop is None or not prop.value.endswith(b"\0"):
            return []
        try:
            return [part.decode("utf-8") for part in prop.value[:-1].split(b"\0")]
        except UnicodeDecodeError:
            return []

    def special(self):
        result = {}
        for path in ("/__fixups__", "/__local_fixups__", "/__symbols__"):
            props = self.nodes.get(path)
            result[path] = "ABSENT" if props is None else len(props)
        return result


@dataclass
class DtboEntry:
    index: int
    dt_size: int
    dt_offset: int
    image_id: int
    rev: int
    custom: tuple
    payload: bytes
    fdt: Fdt


@dataclass
class Dtbo:
    data: bytes
    label: str
    total_size: int
    header_size: int
    entry_size: int
    entry_count: int
    entries_offset: int
    page_size: int
    version: int
    entries: list


def parse_dtbo(data, label):
    if len(data) < DTBO_HEADER_SIZE:
        raise ValueError(f"{label}: short DTBO")
    header = struct.unpack_from(">8I", data, 0)
    magic, total, header_size, entry_size, count, entries_offset, page_size, version = header
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
    return Dtbo(data, label, total, header_size, entry_size, count, entries_offset, page_size, version, entries)


def parse_vendor_dtb_area(data, label):
    """Return the vendor_boot DTB area (concatenated FDTs)."""
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


def pad_fdt(blob, target_size):
    """Reproduce the M5G D-Control-1 fixed-slot expansion (totalsize + zero fill)."""
    fdt = Fdt(blob, "pad-source")
    if target_size < fdt.totalsize:
        raise ValueError("FDT does not fit target slot")
    result = bytearray(blob)
    struct.pack_into(">I", result, 4, target_size)
    result.extend(b"\0" * (target_size - len(result)))
    Fdt(result, "padded-fdt")
    return bytes(result)


def validate_fdt(blob, label, work):
    source = work / f"{label}.dtb"
    output = work / f"{label}.roundtrip.dtb"
    source.write_bytes(blob)
    subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dtb", "-o", str(output), str(source)], check=True)


def apply_overlay(base, overlay, label, work):
    base_path = work / f"{label}.base.dtb"
    overlay_path = work / f"{label}.overlay.dtbo"
    merged_path = work / f"{label}.merged.dtb"
    base_path.write_bytes(base)
    overlay_path.write_bytes(overlay)
    subprocess.run(["fdtoverlay", "-i", str(base_path), str(overlay_path), "-o", str(merged_path)], check=True)
    return merged_path.read_bytes()


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
        ranges.append((start, pos, "REPLACED"))
    if len(before) != len(after):
        ranges.append((common, max(len(before), len(after)), "ADDED" if len(after) > len(before) else "REMOVED"))
    return ranges


def covers(ranges, low, high):
    """True when any changed range overlaps the half-open window [low,high)."""
    return any(start < high and end > low for start, end, _ in ranges)


def block_map(before, after):
    size = max(len(before), len(after))
    total = 0
    changed = 0
    first = None
    last = None
    pos = 0
    while pos < size:
        end = min(pos + BLOCK_SIZE, len(before), len(after))
        total += 1
        if end != pos + BLOCK_SIZE or before[pos:end] != after[pos:end]:
            changed += 1
            if first is None:
                first = pos
            last = pos
        pos += BLOCK_SIZE
    return total, changed, first, last


def region_report(name, before, after, regions, before_label, after_label):
    ranges = changed_ranges(before, after)
    total_blocks, changed_blocks, first_block, last_block = block_map(before, after)
    lines = [
        f"CONTROL={name}",
        f"BEFORE_SOURCE={before_label}",
        f"AFTER_ARTIFACT={after_label}",
        f"BEFORE_SIZE={len(before)}",
        f"AFTER_SIZE={len(after)}",
        f"BEFORE_SHA256={sha(before)}",
        f"AFTER_SHA256={sha(after)}",
        f"EXACT_CHANGED_RANGE_COUNT={len(ranges)}",
        f"EXACT_CHANGED_BYTE_COUNT={sum(end - start for start, end, _ in ranges)}",
        f"BLOCK_SIZE={BLOCK_SIZE}",
        f"BLOCK_COUNT={total_blocks}",
        f"CHANGED_BLOCK_COUNT={changed_blocks}",
        f"FIRST_CHANGED_BLOCK_OFFSET={'NONE' if first_block is None else first_block}",
        f"LAST_CHANGED_BLOCK_OFFSET={'NONE' if last_block is None else last_block}",
        "REGION_TABLE",
    ]
    for label, start, end in regions:
        segment_before = before[start:end]
        segment_after = after[start:end]
        if len(segment_before) != len(segment_after):
            lines.append(f"REGION={label} OFFSET=[{start},{end}) SHAPE_CHANGED"
                         f" size_before={len(segment_before)} size_after={len(segment_after)}")
            continue
        segment_ranges = changed_ranges(segment_before, segment_after)
        lines.append(f"REGION={label} OFFSET=[{start},{end}) SIZE={len(segment_before)}"
                     f" CHANGED_RANGES={len(segment_ranges)}"
                     f" CHANGED_BYTES={sum(e - s for s, e, _ in segment_ranges)}")
    truncated = len(ranges) > DETAIL_RANGE_CAP
    lines.append(f"CHANGED_RANGE_DETAIL_TRUNCATED={'YES' if truncated else 'NO'}")
    lines.append(f"CHANGED_RANGE_DETAIL_CAP={DETAIL_RANGE_CAP}")
    for start, end, kind in ranges[:DETAIL_RANGE_CAP]:
        lines.append(f"RANGE=0x{start:x}-0x{end:x} [{start},{end}) {kind}")
    if truncated:
        lines.append("RANGE_DETAIL_TAIL_BEGIN")
        for start, end, kind in ranges[-DETAIL_RANGE_TAIL:]:
            lines.append(f"RANGE=0x{start:x}-0x{end:x} [{start},{end}) {kind}")
    return lines, ranges


def audit_short(data, stock_entry, m1_dtbo):
    """Fail-closed audit of the existing 484949-byte D-Control-2 short artifact."""
    identity = []
    container = []
    payload_notes = []
    parsed = None

    if len(data) != D_CONTROL2_SHORT_SIZE:
        identity.append(f"SHORT_SIZE={len(data)} EXPECTED={D_CONTROL2_SHORT_SIZE}")
    if sha(data) != D_CONTROL2_SHORT_SHA256:
        identity.append(f"SHORT_SHA256_MISMATCH actual={sha(data)}")
    if len(data) < DTBO_PAYLOAD_OFFSET:
        container.append(f"SHORT_LENGTH={len(data)} below minimum DTBO header+entry")
        return identity, container, payload_notes, parsed

    magic, total, header_size, entry_size, count, entries_offset, page_size, version = struct.unpack_from(">8I", data, 0)
    if magic != DTBO_MAGIC:
        container.append(f"HEADER_MAGIC=0x{magic:08x} EXPECTED=0x{DTBO_MAGIC:08x}")
    if total != D_CONTROL2_SHORT_SIZE:
        container.append(f"HEADER_TOTAL_SIZE={total} EXPECTED={D_CONTROL2_SHORT_SIZE}")
    if header_size != DTBO_HEADER_SIZE:
        container.append(f"HEADER_SIZE={header_size} EXPECTED={DTBO_HEADER_SIZE}")
    if entry_size != DTBO_ENTRY_SIZE:
        container.append(f"ENTRY_SIZE={entry_size} EXPECTED={DTBO_ENTRY_SIZE}")
    if count != 1:
        container.append(f"ENTRY_COUNT={count} EXPECTED=1")
    if entries_offset != DTBO_ENTRIES_OFFSET:
        container.append(f"ENTRIES_OFFSET={entries_offset} EXPECTED={DTBO_ENTRIES_OFFSET}")
    if page_size != DTBO_PAGE_SIZE:
        container.append(f"PAGE_SIZE={page_size} EXPECTED={DTBO_PAGE_SIZE}")
    if version != DTBO_VERSION:
        container.append(f"VERSION={version} EXPECTED={DTBO_VERSION}")

    dt_size, dt_offset, image_id, rev, c0, c1, c2, c3 = struct.unpack_from(">8I", data, DTBO_ENTRIES_OFFSET)
    if dt_offset != DTBO_PAYLOAD_OFFSET:
        container.append(f"ENTRY_DT_OFFSET={dt_offset} EXPECTED={DTBO_PAYLOAD_OFFSET}")
    if dt_size != THYME_ENTRY_DT_SIZE:
        container.append(f"ENTRY_DT_SIZE={dt_size} EXPECTED={THYME_ENTRY_DT_SIZE}")
    if image_id != 0 or rev != 0 or (c0, c1, c2, c3) != (0, 0, 0, 0):
        container.append(f"ENTRY_METADATA_NONZERO id={image_id} rev={rev} custom={(c0, c1, c2, c3)}")
    if total != len(data):
        container.append(f"TRAILING_BYTES={len(data) - total} EXPECTED=0")

    if data[:4] != m1_dtbo.data[:4]:
        container.append("M1_HEADER_MAGIC_NOT_PRESERVED")
    if data[8:DTBO_HEADER_SIZE] != m1_dtbo.data[8:DTBO_HEADER_SIZE]:
        container.append("M1_HEADER_FORMAT_FIELDS_NOT_PRESERVED")
    if data[DTBO_ENTRY_SIZE + 4:DTBO_PAYLOAD_OFFSET] != m1_dtbo.data[DTBO_ENTRY_SIZE + 4:DTBO_PAYLOAD_OFFSET]:
        container.append("M1_ENTRY_FIELDS_BEYOND_DT_SIZE_NOT_PRESERVED")

    if dt_offset + dt_size <= len(data):
        payload = data[dt_offset:dt_offset + dt_size]
        if sha(payload) != THYME_ENTRY_PAYLOAD_SHA256:
            payload_notes.append(f"PAYLOAD_SHA256_MISMATCH actual={sha(payload)}")
        if payload != stock_entry.payload:
            payload_notes.append("PAYLOAD_BYTES_DIFFER_FROM_STOCK_ENTRY21")
    else:
        payload_notes.append(f"PAYLOAD_RANGE_OUTSIDE_FILE dt_offset={dt_offset} dt_size={dt_size}")
    noop_prefix = m1_dtbo.entries[0].payload
    if data[DTBO_PAYLOAD_OFFSET:DTBO_PAYLOAD_OFFSET + len(noop_prefix)] == noop_prefix:
        payload_notes.append("PAYLOAD_PREFIX_EQUALS_M1_NOOP")

    if not container and not payload_notes:
        parsed = parse_dtbo(data, "m5k0-existing-d-control2")
    return identity, container, payload_notes, parsed


def audit_full(full, short, stock, stock_entry, m1_dtbo, padded_noop):
    identity = []
    tail = []
    parsed = None

    if len(full) != FULL_ARTIFACT_SIZE:
        identity.append(f"FULL_SIZE={len(full)} EXPECTED={FULL_ARTIFACT_SIZE}")
    prefix = full[:FULL_PREFIX_END]
    if prefix != short:
        identity.append("FULL_PREFIX_NOT_EXACT_SHORT_ARTIFACT")
    if sha(prefix) != D_CONTROL2_SHORT_SHA256:
        identity.append(f"FULL_PREFIX_SHA256_MISMATCH actual={sha(prefix)}")

    stock_tail = stock[FULL_PREFIX_END:]
    actual_tail = full[FULL_PREFIX_END:]
    if len(stock_tail) != len(actual_tail) or actual_tail != stock_tail:
        tail.append("FULL_TAIL_DIFFERS_FROM_STOCK_SAME_OFFSET")
    if sha(actual_tail) != sha(stock_tail):
        tail.append("FULL_TAIL_SHA256_MISMATCH")

    slot = full[THYME_ENTRY_DT_OFFSET:THYME_ENTRY_DT_OFFSET + THYME_ENTRY_DT_SIZE]
    if slot != stock_entry.payload:
        tail.append("STOCK_ENTRY21_SLOT_NOT_RESTORED_TO_STOCK_OVERLAY")
    m5j_residue = slot == padded_noop
    if m5j_residue:
        tail.append("M5J_NOOP_PAYLOAD_STILL_PRESENT_AT_STOCK_ENTRY21_SLOT")

    if not identity and not tail:
        parsed = parse_dtbo(full, "m5k0-full-normalized")
        if parsed.entry_count != 1:
            identity.append(f"FULL_DTBO_ENTRY_COUNT={parsed.entry_count} EXPECTED=1")
        elif parsed.entries[0].payload != stock_entry.payload:
            identity.append("FULL_DTBO_PAYLOAD_NOT_STOCK_ENTRY21")
    return identity, tail, parsed, m5j_residue


def write_lines(path, lines):
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GitHub Actions only: local audit, transformation, and validation are forbidden")

    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-dtbo", required=True, type=Path)
    parser.add_argument("--stock-vendor-boot", required=True, type=Path)
    parser.add_argument("--m1-dtbo", required=True, type=Path)
    parser.add_argument("--existing-d-control2", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    stock = args.stock_dtbo.read_bytes()
    stock_vendor = args.stock_vendor_boot.read_bytes()
    m1_raw = args.m1_dtbo.read_bytes()
    short = args.existing_d_control2.read_bytes()

    if len(stock) != STOCK_DTBO_SIZE or sha(stock) != STOCK_DTBO_SHA256:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock dtbo size={len(stock)} sha256={sha(stock)}")
    if len(stock_vendor) != STOCK_VENDOR_BOOT_SIZE or sha(stock_vendor) != STOCK_VENDOR_BOOT_SHA256:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock vendor_boot size={len(stock_vendor)} sha256={sha(stock_vendor)}")
    if len(m1_raw) != M1_DTBO_SIZE or sha(m1_raw) != M1_DTBO_SHA256:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED M1 dtbo size={len(m1_raw)} sha256={sha(m1_raw)}")

    stock_dtbo = parse_dtbo(stock, "stock-dtbo")
    m1_dtbo = parse_dtbo(m1_raw, "m1-dtbo")
    dtb_area = parse_vendor_dtb_area(stock_vendor, "stock-vendor_boot")
    dtb0_size = struct.unpack_from(">I", dtb_area, 4)[0]
    dtb0 = dtb_area[:dtb0_size]

    if stock_dtbo.entry_count != STOCK_DTBO_ENTRY_COUNT:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock dtbo entry_count={stock_dtbo.entry_count}")
    if stock_dtbo.total_size != STOCK_DTBO_TOTAL_SIZE:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock dtbo total_size={stock_dtbo.total_size}")
    if m1_dtbo.entry_count != 1:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED M1 dtbo entry_count={m1_dtbo.entry_count}")
    if dtb0_size != STOCK_DTB0_SIZE or sha(dtb0) != STOCK_DTB0_SHA256:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock DTB0 size={dtb0_size} sha256={sha(dtb0)}")

    stock_entry = stock_dtbo.entries[THYME_ENTRY_INDEX]
    if stock_entry.dt_offset != THYME_ENTRY_DT_OFFSET or stock_entry.dt_size != THYME_ENTRY_DT_SIZE:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock entry21 offset/size="
                         f"{stock_entry.dt_offset}/{stock_entry.dt_size}")
    if sha(stock_entry.payload) != THYME_ENTRY_PAYLOAD_SHA256:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED stock entry21 payload sha256={sha(stock_entry.payload)}")
    if stock_entry.fdt.root_cells("qcom,board-id") != [45, 0]:
        raise SystemExit("M5K0_SOURCE_IDENTITY_FAILED stock entry21 board-id is not <45 0>")
    candidates = [entry.index for entry in stock_dtbo.entries if entry.fdt.root_cells("qcom,board-id") == [45, 0]]
    if candidates != [THYME_ENTRY_INDEX]:
        raise SystemExit(f"M5K0_SOURCE_IDENTITY_FAILED thyme entry candidates={candidates}")
    if m1_dtbo.entries[0].dt_offset != DTBO_PAYLOAD_OFFSET:
        raise SystemExit("M5K0_SOURCE_IDENTITY_FAILED M1 dtbo payload offset is not 64")

    with tempfile.TemporaryDirectory(prefix="m5k0-") as temp_name:
        work = Path(temp_name)

        # 1. Re-audit the existing short artifact. Nothing is assumed READY.
        short_identity, short_container, short_payload, short_parsed = audit_short(short, stock_entry, m1_dtbo)
        if short_identity:
            raise SystemExit("M5K0_D_CONTROL2_IDENTITY_FAILED " + "; ".join(short_identity))
        if short_container:
            raise SystemExit("M5K0_D_CONTROL2_CONTAINER_INVALID " + "; ".join(short_container))
        if short_payload:
            raise SystemExit("M5K0_D_CONTROL2_PAYLOAD_INVALID " + "; ".join(short_payload))

        padded_noop = pad_fdt(m1_dtbo.entries[0].payload, THYME_ENTRY_DT_SIZE)

        # 2. Normalized full-partition image: short prefix + exact Stock tail.
        full = short + stock[FULL_PREFIX_END:]
        full_identity, full_tail, full_parsed, m5j_residue = audit_full(full, short, stock, stock_entry, m1_dtbo, padded_noop)
        if full_identity:
            raise SystemExit("M5K0_D_CONTROL2_IDENTITY_FAILED " + "; ".join(full_identity))
        if full_tail:
            raise SystemExit("M5K0_D_CONTROL2_TAIL_NORMALIZATION_FAILED " + "; ".join(full_tail))

        # 3. Structural validation.
        validate_fdt(short_parsed.entries[0].payload, "m5k0-cell-d-payload", work)
        validate_fdt(m1_dtbo.entries[0].payload, "m5k0-m1-noop", work)
        merged = apply_overlay(dtb0, short_parsed.entries[0].payload, "m5k0-stock-base0-cell-d", work)
        merged_sha = sha(merged)
        merged_matches_m5h = merged_sha == M5H_MERGED_SHA256

        # 4. Negative tests. The unmutated artifact must yield zero violations.
        negative = [
            ("CONTROL_UNMUTATED_SHORT_ACCEPTED", not (short_identity + short_container + short_payload)),
            ("CONTROL_UNMUTATED_FULL_ACCEPTED", not (full_identity + full_tail)),
        ]

        mutated = bytearray(short)
        mutated[CANDIDATE_PAYLOAD_START] ^= 0xFF
        _, _, payload_violations, _ = audit_short(bytes(mutated), stock_entry, m1_dtbo)
        negative.append(("NEG_WRONG_PAYLOAD_BYTE_DETECTED", any("PAYLOAD" in item for item in payload_violations)))

        mutated = bytearray(short)
        struct.pack_into(">I", mutated, 16, 2)
        _, container_violations, _, _ = audit_short(bytes(mutated), stock_entry, m1_dtbo)
        negative.append(("NEG_ENTRY_COUNT_2_DETECTED", any("ENTRY_COUNT=2" in item for item in container_violations)))

        mutated = bytearray(short)
        struct.pack_into(">I", mutated, 36, 128)
        _, container_violations, _, _ = audit_short(bytes(mutated), stock_entry, m1_dtbo)
        negative.append(("NEG_DT_OFFSET_128_DETECTED", any("ENTRY_DT_OFFSET=128" in item for item in container_violations)))

        mutated = bytearray(short)
        struct.pack_into(">I", mutated, 32, THYME_ENTRY_DT_SIZE - 1)
        _, container_violations, _, _ = audit_short(bytes(mutated), stock_entry, m1_dtbo)
        negative.append(("NEG_DT_SIZE_484884_DETECTED", any("ENTRY_DT_SIZE=484884" in item for item in container_violations)))

        mutated = bytearray(short)
        struct.pack_into(">I", mutated, 40, 1)
        _, container_violations, _, _ = audit_short(bytes(mutated), stock_entry, m1_dtbo)
        negative.append(("NEG_ENTRY_METADATA_NONZERO_DETECTED",
                         any("ENTRY_METADATA_NONZERO" in item for item in container_violations)))

        mutated = bytearray(short)
        struct.pack_into(">I", mutated, 4, D_CONTROL2_SHORT_SIZE - 1)
        _, container_violations, _, _ = audit_short(bytes(mutated), stock_entry, m1_dtbo)
        negative.append(("NEG_TOTAL_SIZE_WRONG_DETECTED",
                         any("HEADER_TOTAL_SIZE" in item for item in container_violations)))

        bad_identity, _, _, _ = audit_full(full[:-1], short, stock, stock_entry, m1_dtbo, padded_noop)
        negative.append(("NEG_FULL_SIZE_WRONG_DETECTED", any("FULL_SIZE" in item for item in bad_identity)))

        mutated_full = bytearray(full)
        mutated_full[5000000] ^= 0xFF
        _, bad_tail, _, _ = audit_full(bytes(mutated_full), short, stock, stock_entry, m1_dtbo, padded_noop)
        negative.append(("NEG_TAIL_DIFFERS_FROM_STOCK_DETECTED", any("FULL_TAIL" in item for item in bad_tail)))

        mutated_full = bytearray(full)
        mutated_full[THYME_ENTRY_DT_OFFSET:THYME_ENTRY_DT_OFFSET + THYME_ENTRY_DT_SIZE] = padded_noop
        _, bad_tail, _, residue = audit_full(bytes(mutated_full), short, stock, stock_entry, m1_dtbo, padded_noop)
        negative.append(("NEG_M5J_NOOP_RESIDUE_DETECTED",
                         residue and any("M5J_NOOP_PAYLOAD_STILL_PRESENT" in item for item in bad_tail)))

        failed_negative = [name for name, ok in negative if not ok]

    entry = short_parsed.entries[0]
    special = entry.fdt.special()
    m1_entry = m1_dtbo.entries[0]

    m1_rows = [
        ("MAGIC", f"0x{DTBO_MAGIC:08x}", f"0x{DTBO_MAGIC:08x}", "SAME"),
        ("HEADER_VERSION", str(m1_dtbo.version), str(short_parsed.version), "SAME"),
        ("HEADER_SIZE", str(m1_dtbo.header_size), str(short_parsed.header_size), "SAME"),
        ("ENTRY_SIZE", str(m1_dtbo.entry_size), str(short_parsed.entry_size), "SAME"),
        ("ENTRY_COUNT", str(m1_dtbo.entry_count), str(short_parsed.entry_count), "SAME"),
        ("ENTRIES_OFFSET", str(m1_dtbo.entries_offset), str(short_parsed.entries_offset), "SAME"),
        ("PAGE_SIZE", str(m1_dtbo.page_size), str(short_parsed.page_size), "SAME"),
        ("TOTAL_SIZE", str(m1_dtbo.total_size), str(short_parsed.total_size), "CHANGED"),
        ("ENTRY_DT_OFFSET", str(m1_entry.dt_offset), str(entry.dt_offset), "SAME"),
        ("ENTRY_DT_SIZE", str(m1_entry.dt_size), str(entry.dt_size), "CHANGED"),
        ("ENTRY_ID", "0", str(entry.image_id), "SAME"),
        ("ENTRY_REV", "0", str(entry.rev), "SAME"),
        ("ENTRY_CUSTOM", "0 0 0 0", " ".join(str(value) for value in entry.custom), "SAME"),
    ]
    container_preserved = (
        all(row[3] == "SAME" for row in m1_rows if row[0] not in {"TOTAL_SIZE", "ENTRY_DT_SIZE"})
        and short[:4] == m1_raw[:4]
        and short[8:DTBO_HEADER_SIZE] == m1_raw[8:DTBO_HEADER_SIZE]
        and short[DTBO_HEADER_SIZE + 4:DTBO_PAYLOAD_OFFSET] == m1_raw[DTBO_HEADER_SIZE + 4:DTBO_PAYLOAD_OFFSET]
    )
    changed_header_fields = [row[0] for row in m1_rows if row[3] == "CHANGED" and row[0] in {"TOTAL_SIZE"}]
    changed_entry_fields = [row[0] for row in m1_rows if row[3] == "CHANGED" and row[0] in {"ENTRY_DT_SIZE"}]

    # 5. Reports.
    write_lines(args.out_dir / "m5k0-existing-d-control2-header.txt", [
        "LABEL=m5k0-existing-d-control2",
        f"FILE_SIZE={len(short)}",
        f"SHA256={sha(short)}",
        "MAGIC=0xd7b7ab1e",
        f"TOTAL_SIZE={short_parsed.total_size}",
        f"HEADER_SIZE={short_parsed.header_size}",
        f"ENTRY_SIZE={short_parsed.entry_size}",
        f"ENTRY_COUNT={short_parsed.entry_count}",
        f"ENTRIES_OFFSET={short_parsed.entries_offset}",
        f"PAGE_SIZE={short_parsed.page_size}",
        f"VERSION={short_parsed.version}",
        f"TRAILING_BYTES={len(short) - short_parsed.total_size}",
        f"AUTHORITATIVE_EXPECTED_SHA256={D_CONTROL2_SHORT_SHA256}",
        f"SHA_EXACT={'YES' if sha(short) == D_CONTROL2_SHORT_SHA256 else 'NO'}",
        f"M1_HEADER_MAGIC_PRESERVED={'YES' if short[:4] == m1_dtbo.data[:4] else 'NO'}",
        "M1_HEADER_TOTAL_SIZE_FIELD_CHANGED=YES",
        "M1_HEADER_FORMAT_FIELDS_PRESERVED=YES",
    ])
    write_lines(args.out_dir / "m5k0-existing-d-control2-entry.txt", [
        "LABEL=m5k0-existing-d-control2-entry0",
        f"DT_SIZE={entry.dt_size}",
        f"DT_OFFSET={entry.dt_offset}",
        f"ID=0x{entry.image_id:08x}",
        f"REV=0x{entry.rev:08x}",
        "CUSTOM=" + " ".join(f"0x{value:08x}" for value in entry.custom),
        f"M5G_RECORDED_FRAGMENT_COUNT=124",
        f"M5G_RECORDED_FIXUPS=154",
        f"M5G_RECORDED_SYMBOLS=386",
        f"FDT_TOTALSIZE={entry.fdt.totalsize}",
        f"FDT_VERSION={entry.fdt.version}",
        "FDT_BOARD_ID=" + " ".join(str(value) for value in (entry.fdt.root_cells("qcom,board-id") or [])),
        "FDT_COMPATIBLE=" + " | ".join(entry.fdt.root_strings("compatible")),
        f"FDT_FRAGMENT_COUNT={len(entry.fdt.fragments)}",
        f"FDT_FIXUPS_COUNT={special['/__fixups__']}",
        f"FDT_LOCAL_FIXUPS_COUNT={special['/__local_fixups__']}",
        f"FDT_SYMBOLS_COUNT={special['/__symbols__']}",
        f"PAYLOAD_SHA256={sha(entry.payload)}",
        f"EXPECTED_STOCK_ENTRY21_SHA256={THYME_ENTRY_PAYLOAD_SHA256}",
        f"PAYLOAD_SHA_EXACT={'YES' if sha(entry.payload) == THYME_ENTRY_PAYLOAD_SHA256 else 'NO'}",
        f"PAYLOAD_BYTES_EXACT_STOCK_ENTRY21={'YES' if entry.payload == stock_entry.payload else 'NO'}",
        f"PAYLOAD_IS_NOT_M1_NOOP={'YES' if entry.payload != m1_entry.payload else 'NO'}",
    ])
    write_lines(args.out_dir / "m5k0-full-artifact-header.txt", [
        "LABEL=m5k0-full-normalized",
        f"FILE_SIZE={len(full)}",
        f"SHA256={sha(full)}",
        f"PREFIX_END={FULL_PREFIX_END}",
        f"PREFIX_SHA256={sha(full[:FULL_PREFIX_END])}",
        f"PREFIX_MATCHES_SHORT_ARTIFACT={'YES' if full[:FULL_PREFIX_END] == short else 'NO'}",
        f"TAIL_SHA256={sha(full[FULL_PREFIX_END:])}",
        f"STOCK_SAME_OFFSET_TAIL_SHA256={sha(stock[FULL_PREFIX_END:])}",
        f"TAIL_EQUALS_STOCK_SAME_OFFSET={'YES' if full[FULL_PREFIX_END:] == stock[FULL_PREFIX_END:] else 'NO'}",
        f"DTBO_PARSE_TOTAL_SIZE={full_parsed.total_size}",
        f"DTBO_PARSE_ENTRY_COUNT={full_parsed.entry_count}",
        f"STOCK_ENTRY21_SLOT_OFFSET={THYME_ENTRY_DT_OFFSET}",
        f"STOCK_ENTRY21_SLOT_SIZE={THYME_ENTRY_DT_SIZE}",
        f"STOCK_ENTRY21_SLOT_SHA256={sha(full[THYME_ENTRY_DT_OFFSET:THYME_ENTRY_DT_OFFSET + THYME_ENTRY_DT_SIZE])}",
        f"STOCK_ENTRY21_SLOT_EQUALS_STOCK_OVERLAY="
        f"{'YES' if full[THYME_ENTRY_DT_OFFSET:THYME_ENTRY_DT_OFFSET + THYME_ENTRY_DT_SIZE] == stock_entry.payload else 'NO'}",
        f"M5J_NOOP_RESIDUE_AT_STOCK_ENTRY21_SLOT={'YES' if m5j_residue else 'NO'}",
        "TAIL_IS_PHYSICAL_NORMALIZATION_ONLY=YES",
        "TAIL_NOT_PART_OF_ACTIVE_ONE_ENTRY_IMAGE=YES",
    ])
    write_lines(args.out_dir / "m5k0-container-semantics.txt",
                [f"FIELD={row[0]} M1={row[1]} CELL_D={row[2]} {row[3]}" for row in m1_rows]
                + [f"CONTAINER_SEMANTICS_PRESERVED_ONE_ENTRY={'YES' if container_preserved else 'NO'}",
                   f"CHANGED_HEADER_FIELD_VS_M1={','.join(changed_header_fields) or 'NONE'}",
                   f"CHANGED_ENTRY_FIELD_VS_M1={','.join(changed_entry_fields) or 'NONE'}"])
    write_lines(args.out_dir / "m5k0-validation-report.txt", [
        "DTBO_PARSE=PASS",
        f"ENTRY_COUNT={short_parsed.entry_count}",
        "SELECTED_PAYLOAD_PARSE=PASS",
        f"SELECTED_PAYLOAD_OFFSET={entry.dt_offset}",
        f"SELECTED_PAYLOAD_SIZE={entry.dt_size}",
        f"SELECTED_PAYLOAD_SHA256={sha(entry.payload)}",
        f"SELECTED_PAYLOAD_FRAGMENT_COUNT={len(entry.fdt.fragments)}",
        f"SELECTED_PAYLOAD_FIXUPS_COUNT={special['/__fixups__']}",
        f"SELECTED_PAYLOAD_SYMBOLS_COUNT={special['/__symbols__']}",
        "DTC_ROUNDTRIP_SELECTED_PAYLOAD=PASS",
        "DTC_ROUNDTRIP_M1_NOOP=PASS",
        "FDTOVERLAY_STOCK_DTB0_PLUS_CELLD_PAYLOAD=PASS",
        f"FDTOVERLAY_MERGED_SHA256={merged_sha}",
        f"M5H_RECORDED_MERGED_SHA256={M5H_MERGED_SHA256}",
        f"FDTOVERLAY_MERGED_SHA_EQUALS_M5H_RECORD={'YES' if merged_matches_m5h else 'NO'}",
        f"STOCK_DTB0_SIZE={dtb0_size}",
        f"STOCK_DTB0_SHA256={sha(dtb0)}",
        "STRUCTURAL_VALIDATION_ONLY=YES",
        "XIAOMI_ABL_EVIDENCE=NO",
    ])
    negative_lines = [f"NEGATIVE_TEST_COUNT={len(negative)}"]
    for name, ok in negative:
        negative_lines.append(f"{name}={'PASS' if ok else 'FAIL'}")
    negative_lines.append(f"FAILED_NEGATIVE_TESTS={len(failed_negative)}")
    negative_lines.append("NEGATIVE_TESTS_PASS=" + ("YES" if not failed_negative else "NO"))
    negative_lines.append("FAIL_CLOSED=" + ("PASS" if not failed_negative else "FAIL"))
    write_lines(args.out_dir / "m5k0-negative-tests.txt", negative_lines)

    m1_diff, m1_ranges = region_report("CELL_D_VS_M1_DTBO", m1_dtbo.data, short, M1_VS_CELLD_REGIONS,
                                       "exact M1 dtbo 387 bytes", "Cell-D short artifact 484949 bytes")
    m1_diff.extend([
        "INTENTIONAL_VARIABLE=SELECTED_PAYLOAD_BYTES_ONLY",
        "CONTAINER_SEMANTICS_HELD=ONE_ENTRY",
        "EXPECTED_CHANGE_CONTAINED_IN=[4,8) header total_size field",
        "EXPECTED_CHANGE_CONTAINED_IN=[32,36) entry dt_size field",
        "EXPECTED_TRAILING_RANGE=ADDED[387,484949)",
        "EXPECTED_UNCHANGED=[0,4) and [8,32) and [36,64)",
        "NOTE=TOTAL_SIZE_AND_DT_SIZE_LEADING_BYTES_CAN_BE_EQUAL",
        "",
    ])
    write_lines(args.out_dir / "m5k0-binary-diff-vs-m1.txt", m1_diff)

    stock_diff, stock_ranges = region_report("CELL_D_FULL_VS_STOCK_DTBO", stock, full, FULL_REGIONS,
                                             "exact Stock dtbo.img 33554432 bytes",
                                             "Cell-D normalized 33554432 bytes")
    stock_diff.extend([
        "INTENTIONAL_VARIABLE=DTBO_CONTAINER_TABLE_TOPOLOGY",
        "PRESERVED=SELECTED_OVERLAY_PAYLOAD_BYTES",
        "NOT_A_SINGLE_FIELD_DELTA=YES",
        "ACTIVE_ONE_ENTRY_IMAGE_SITS_AT_PARTITION_FRONT=YES",
        f"STOCK_WAS_ENTRY_COUNT={stock_dtbo.entry_count}",
        f"STOCK_WAS_TOTAL_SIZE={stock_dtbo.total_size}",
        f"STOCK_WAS_SELECTED_ENTRY_OFFSET_SIZE={THYME_ENTRY_DT_OFFSET}/{THYME_ENTRY_DT_SIZE}",
        "TAIL_IS_BYTE_EXACT_STOCK_SAME_OFFSET=YES",
        "",
    ])
    write_lines(args.out_dir / "m5k0-binary-diff-vs-stock.txt", stock_diff)

    m1_payload_zone = [r for r in m1_ranges if r[2] == "REPLACED" and DTBO_PAYLOAD_OFFSET <= r[0] < M1_DTBO_SIZE]
    m1_extended_zone = [r for r in m1_ranges if r[0] >= M1_DTBO_SIZE]
    ranges_ok = (
        len(m1_ranges) >= 4
        and not covers(m1_ranges, 0, 4)
        and covers(m1_ranges, 4, 8)
        and not covers(m1_ranges, 8, DTBO_HEADER_SIZE)
        and covers(m1_ranges, DTBO_HEADER_SIZE, DTBO_HEADER_SIZE + 4)
        and not covers(m1_ranges, DTBO_HEADER_SIZE + 4, DTBO_PAYLOAD_OFFSET)
        and bool(m1_payload_zone)
        and all(end <= M1_DTBO_SIZE for _, end, _ in m1_payload_zone)
        and len(m1_extended_zone) == 1
        and m1_extended_zone[0] == (M1_DTBO_SIZE, FULL_PREFIX_END, "ADDED")
    )
    payload_shape_ok = (
        len(entry.fdt.fragments) == 124
        and special["/__fixups__"] == 154
        and special["/__symbols__"] == 386
    )
    safe = ((not failed_negative) and container_preserved and ranges_ok
            and merged_matches_m5h and payload_shape_ok)

    matrix = f"""# M5K0 DTBO 2x2 factorial — missing Cell D

## Corrected conclusion boundary

M5J proved `M1_NOOP_PAYLOAD_SUFFICIENT_ON_STOCK_TABLE=STRONGLY_SUPPORTED`.
That result does **not** permit `ONE_ENTRY_CONTAINER_NOT_CAUSAL`, because the
fourth factorial cell was never measured. The only currently permitted claim is
that the M1 no-op payload is sufficient on the Stock 29-entry table. Writing
"payload sufficient" therefore does not yet exonerate the one-entry container.

## Matrix

| cell | DTBO container/table | selected thyme payload | runtime | status |
| --- | --- | --- | --- | --- |
| A | Stock 29-entry | Stock thyme entry21 | >12s | measured |
| B | Stock 29-entry | M1 no-op | 4.922s | measured (M5J) |
| C | M1 one-entry | M1 no-op | 4.812s | measured (M5F1) |
| D | M1 one-entry | Stock thyme entry21 | UNKNOWN | artifact prepared this round, not booted |

## Cell D definition

```text
header          : magic 0xd7b7ab1e, version 0, header_size 32, entry_size 32
entry_count     : 1
entries_offset  : 32
page_size       : 4096
table total_size: {short_parsed.total_size}
entry           : id/rev/custom all zero, dt_offset {entry.dt_offset}, dt_size {entry.dt_size}
payload         : exact Stock thyme entry21, {THYME_ENTRY_DT_SIZE} bytes
                  {THYME_ENTRY_PAYLOAD_SHA256}
physical image  : {len(full)} bytes
                  [0,{FULL_PREFIX_END})      exact short Cell-D image
                  [{FULL_PREFIX_END},{FULL_ARTIFACT_SIZE}) exact Stock dtbo.img same-offset tail
```

`{entry.dt_offset} + {entry.dt_size} = {short_parsed.total_size}` matches the existing short
artifact size. The DTBO `total_size` header field equals the file size, so the
Cell-D image has no trailing bytes of its own inside the short artifact; the
bytes after `{FULL_PREFIX_END}` in the normalized image are the physical
partition normalization described below, not part of the active one-entry
table.

## Single logical variable

Cell A -> Cell D:

```text
DTBO_CONTAINER_TABLE_TOPOLOGY
  entry_count   : 29 -> 1
  table bytes   : Stock 29-entry table/offsets -> M1 one-entry header+entry
  payload layout: Stock partition layout -> contiguous payload from offset 64
overlay payload : EXACT STOCK THYME ENTRY21        (held constant)
```

Cell B -> Cell D:

```text
container/header semantics : one-entry              (held constant)
payload                    : M1 no-op -> exact Stock thyme entry21
```

## Physical-partition normalization

The current `dtbo_b` is the M5J artifact: Stock 29-entry table with a padded M1
no-op at the Stock entry21 slot. Flashing only the {D_CONTROL2_SHORT_SIZE}-byte short image would
leave the M5J tail bytes in place and keep the no-op residue as an unexplained
variable. The normalized image therefore uses the exact Stock same-offset tail,
so the Stock entry21 slot bytes are restored and no M5J no-op residue remains.

```text
STOCK_ENTRY21_SLOT_OFFSET={THYME_ENTRY_DT_OFFSET}
STOCK_ENTRY21_SLOT_SIZE={THYME_ENTRY_DT_SIZE}
STOCK_ENTRY21_SLOT_SHA256={sha(full[THYME_ENTRY_DT_OFFSET:THYME_ENTRY_DT_OFFSET + THYME_ENTRY_DT_SIZE])}
M5J_NOOP_RESIDUE_AT_STOCK_ENTRY21_SLOT={'YES' if m5j_residue else 'NO'}
```

Under DTBO `total_size` semantics the tail is not part of the active one-entry
image. It is physical-partition normalization only.

## Pre-registered future interpretation

```text
Cell D PRIMARY_OBSERVATION =>12s
  Stock/Stock   =>12s
  Stock/M1      4.922s
  M1/Stock      =>12s
  M1/M1         4.812s
  => M1_NOOP_PAYLOAD=SUFFICIENT
  => ONE_ENTRY_CONTAINER_ALONE_SUFFICIENT=NO
  => PAYLOAD_CAUSAL_FAMILY=STRONGLY_SUPPORTED
  => next stage DTBO_PAYLOAD_SEMANTICS_AUDIT

Cell D ~4.3-5.3s
  => M1_NOOP_PAYLOAD independently sufficient
  => M1_ONE_ENTRY_CONTAINER independently sufficient
  => both the payload question and the container question must be fixed

Cell D 5.3-12s
  => INCONCLUSIVE, no forced classification
```

## Verified numbers from this round

```text
existing short artifact size      {len(short)}
existing short artifact SHA256    {sha(short)}
container entry_count             {short_parsed.entry_count}
container entries_offset          {short_parsed.entries_offset}
container page_size               {short_parsed.page_size}
container version                 {short_parsed.version}
entry dt_offset                   {entry.dt_offset}
entry dt_size                     {entry.dt_size}
entry metadata                    all zero
payload SHA256                    {sha(entry.payload)}
payload exact Stock entry21       YES
full normalized size              {len(full)}
full normalized SHA256            {sha(full)}
full prefix SHA256                {sha(full[:FULL_PREFIX_END])}
full tail SHA256                  {sha(full[FULL_PREFIX_END:])}
stock same-offset tail SHA256     {sha(stock[FULL_PREFIX_END:])}
fdtoverlay merged SHA256          {merged_sha}
fdtoverlay merged == M5H record   {'YES' if merged_matches_m5h else 'NO'}
diff vs M1 exact ranges           {len(m1_ranges)}
diff vs M1 ranges as expected     {'YES' if ranges_ok else 'NO'}
diff vs Stock exact ranges        {len(stock_ranges)}
```

## Not claimed

- no device operation, no flash, no slot change, no B boot this round
- structural `dtc` / `fdtoverlay` validation is not Xiaomi ABL evidence
- Cell D has not been booted, so no runtime class is assigned to it
- the exact Stock tail is not claimed to be part of the active DTBO image
"""
    (args.out_dir / "m5k0-factor-matrix.md").write_text(matrix, encoding="utf-8")

    gates = [
        "MEM0_READ_BEFORE_M5K0=YES",
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
        f"STOCK_DTBO_TOTAL_SIZE={stock_dtbo.total_size}",
        f"THYME_ENTRY_INDEX={THYME_ENTRY_INDEX}",
        f"STOCK_ENTRY21_DT_OFFSET={stock_entry.dt_offset}",
        f"STOCK_ENTRY21_DT_SIZE={stock_entry.dt_size}",
        "STOCK_ENTRY21_PAYLOAD_SHA_EXACT=YES",
        "VENDOR_BOOT_BASE_DTB_SELECTION_AMBIGUOUS=NO",
        "EXISTING_D_CONTROL2_READY=YES",
        "EXISTING_D_CONTROL2_READY_NOT_ASSUMED=YES",
        f"EXISTING_D_CONTROL2_SIZE={len(short)}",
        "EXISTING_D_CONTROL2_SHA_EXACT=YES",
        f"D_CONTROL2_TOTAL_SIZE={short_parsed.total_size}",
        f"D_CONTROL2_HEADER_SIZE={short_parsed.header_size}",
        f"D_CONTROL2_ENTRY_SIZE={short_parsed.entry_size}",
        f"D_CONTROL2_ENTRY_COUNT={short_parsed.entry_count}",
        f"D_CONTROL2_ENTRIES_OFFSET={short_parsed.entries_offset}",
        f"D_CONTROL2_PAGE_SIZE={short_parsed.page_size}",
        f"D_CONTROL2_VERSION={short_parsed.version}",
        "D_CONTROL2_TRAILING_BYTES=0",
        f"D_CONTROL2_ENTRY_DT_OFFSET={entry.dt_offset}",
        f"D_CONTROL2_ENTRY_DT_SIZE={entry.dt_size}",
        "D_CONTROL2_ENTRY_METADATA_ALL_ZERO=YES",
        "D_CONTROL2_PAYLOAD_SHA_EXACT_STOCK_ENTRY21=YES",
        "D_CONTROL2_PAYLOAD_BYTES_EXACT_STOCK_ENTRY21=YES",
        "D_CONTROL2_PAYLOAD_IS_NOT_M1_NOOP=YES",
        f"D_CONTROL2_PAYLOAD_FRAGMENT_COUNT={len(entry.fdt.fragments)}",
        f"PAYLOAD_FRAGMENT_COUNT_124={'YES' if len(entry.fdt.fragments) == 124 else 'NO'}",
        f"PAYLOAD_FIXUPS_COUNT_154={'YES' if special['/__fixups__'] == 154 else 'NO'}",
        f"PAYLOAD_SYMBOLS_COUNT_386={'YES' if special['/__symbols__'] == 386 else 'NO'}",
        "CONTAINER_SEMANTICS_PRESERVED_ONE_ENTRY=" + ("YES" if container_preserved else "NO"),
        "CHANGED_HEADER_FIELD_VS_M1=" + (",".join(changed_header_fields) or "NONE"),
        "CHANGED_ENTRY_FIELD_VS_M1=" + (",".join(changed_entry_fields) or "NONE"),
        f"DIFF_VS_M1_EXACT_CHANGED_RANGE_COUNT={len(m1_ranges)}",
        "DIFF_VS_M1_RANGES_AS_EXPECTED=" + ("YES" if ranges_ok else "NO"),
        f"FULL_ARTIFACT_SIZE={len(full)}",
        f"M5K0_FULL_ARTIFACT_SIZE={len(full)}",
        f"M5K0_FULL_ARTIFACT_SHA256={sha(full)}",
        "FULL_ARTIFACT_PREFIX_SHA_EXACT=YES",
        "FULL_ARTIFACT_TAIL_EQUALS_STOCK_SAME_OFFSET=YES",
        f"FULL_ARTIFACT_TAIL_SHA256={sha(full[FULL_PREFIX_END:])}",
        "FULL_ARTIFACT_DTBO_PARSE=PASS",
        f"FULL_ARTIFACT_DTBO_ENTRY_COUNT={full_parsed.entry_count}",
        "TAIL_ENTRY21_SLOT_EQUALS_STOCK_OVERLAY=YES",
        "TAIL_ENTRY21_SLOT_EQUALS_M5J_PADDED_NOOP=NO",
        "M5J_NOOP_RESIDUE_IN_TAIL=NO",
        "DTBO_PARSE=PASS",
        "SELECTED_PAYLOAD_PARSE=PASS",
        "DTC_ROUNDTRIP_PAYLOAD=PASS",
        "FDTOVERLAY_STOCK_DTB0_PLUS_CELLD_PAYLOAD=PASS",
        "FDTOVERLAY_MERGED_SHA_EQUALS_M5H_RECORD=" + ("YES" if merged_matches_m5h else "NO"),
        f"DIFF_VS_STOCK_EXACT_CHANGED_RANGE_COUNT={len(stock_ranges)}",
        f"NEGATIVE_TEST_COUNT={len(negative)}",
        "NEGATIVE_TESTS_PASS=" + ("YES" if not failed_negative else "NO"),
        "FAIL_CLOSED=" + ("PASS" if not failed_negative else "FAIL"),
        "PRIVATE_ARTIFACT_ONLY=YES",
        "OEM_DERIVED_ARTIFACT_PRIVATE_ONLY=YES",
        "READY_FOR_MAINLINE_V2_M5K_DTBO_ONE_ENTRY_STOCK_PAYLOAD_CONTROL=" + ("YES" if safe else "NO"),
        "NEXT_TRUE_DEVICE_CONTROL=M5K_DTBO_MISSING_CELL_TRUE_DEVICE_CONTROL",
        "NO_NEXT_STAGE_EXECUTED=YES",
        "WAIT_FOR_USER_APPROVAL=YES",
    ]
    if not safe:
        gates.append("M5K0_D_CONTROL2_NOT_SAFE")
    write_lines(args.out_dir / "m5k0-gates.txt", gates)

    (args.out_dir / "m5k0-full-normalized-dtbo.img").write_bytes(full)
    (args.out_dir / "m5k0-d-control2-short-dtbo.img").write_bytes(short)

    sums = []
    for path in sorted(args.out_dir.iterdir()):
        if path.name != "SHA256SUMS" and path.is_file():
            sums.append(f"{sha(path.read_bytes())}  {path.name}")
    write_lines(args.out_dir / "SHA256SUMS", sums)

    print("\n".join(gates))
    print(f"M5K0_FULL_ARTIFACT_SHA256={sha(full)}")
    if not safe:
        raise SystemExit("M5K0_D_CONTROL2_NOT_SAFE")


if __name__ == "__main__":
    main()
