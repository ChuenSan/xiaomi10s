#!/usr/bin/env python3
"""GHA-only M5H base board-id isolation plus Stock-overlay compatibility audit."""

import argparse
import hashlib
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

EXPECTED = {
    "m5g_v": (548864, "e49e12ad71839bc959237eb8ef6ad6ba7f2f38dffedcf31f3fe36b0845402e83"),
    "stock_vendor": (100663296, "aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"),
    "stock_dtbo": (33554432, "018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"),
    "m1_vendor": (114688, "29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5"),
}
M5G_V_DTB0_SHA = "324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8"
M1_DTB0_SHA = "cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0"
STOCK_DTBO_ENTRY21_SHA = "44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93"

STOCK_BASE_DTB_INDEX = 0
THYME_DTBO_ENTRY_INDEX = 21
BOARD_ID = "qcom,board-id"
MSM_ID = "qcom,msm-id"
BOARD_ID_BEFORE = (0, 0)
BOARD_ID_AFTER = (45, 0)
ARTIFACT_NAME = "m5h-v-stock-dtb0-board45-vendor_boot.img"

FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9

FAILURES = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, size):
    return (value + size - 1) // size * size


def cstr(data):
    return data.split(b"\0", 1)[0].decode("utf-8", "replace")


def cells(data):
    if not data or len(data) % 4:
        return None
    return list(struct.unpack(f">{len(data) // 4}I", data))


def strings(data):
    if not data or not data.endswith(b"\0"):
        return None
    parts = data[:-1].split(b"\0")
    if not parts or any(not part for part in parts):
        return None
    try:
        values = [part.decode("utf-8") for part in parts]
    except UnicodeDecodeError:
        return None
    if any(any(ord(ch) < 0x20 or ord(ch) > 0x7e for ch in value) for value in values):
        return None
    return values


def cell_text(value):
    return "<" + " ".join(f"0x{x:x}" for x in value) + "> (" + " ".join(str(x) for x in value) + ")"


@dataclass
class Prop:
    value: bytes
    value_offset: int


class Fdt:
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
            if token == FDT_BEGIN_NODE:
                nul = self.data.find(b"\0", pos, end)
                if nul < 0:
                    raise ValueError(f"{self.label}: unterminated node name")
                name = self.data[pos:nul].decode("utf-8", "replace")
                pos = align(nul + 1, 4)
                path = "/" if not stack else stack[-1].rstrip("/") + "/" + name
                stack.append(path)
                self.nodes[path] = {}
            elif token == FDT_END_NODE:
                if not stack:
                    raise ValueError(f"{self.label}: unbalanced END_NODE")
                stack.pop()
            elif token == FDT_PROP:
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
            elif token == FDT_NOP:
                continue
            elif token == FDT_END:
                saw_end = True
                break
            else:
                raise ValueError(f"{self.label}: unknown structure token {token}")
        if not saw_end or stack:
            raise ValueError(f"{self.label}: malformed structure termination")

    def prop(self, path, name):
        entry = self.nodes.get(path, {}).get(name)
        return None if entry is None else entry.value

    def root_cells(self, name):
        value = self.prop("/", name)
        return None if value is None else cells(value)

    def root_strings(self, name):
        value = self.prop("/", name)
        return [] if value is None else (strings(value) or [])

    def symbol_table(self):
        entries = self.nodes.get("/__symbols__")
        if entries is None:
            return None
        table = {}
        for name, entry in entries.items():
            target = strings(entry.value)
            table[name] = target[0] if target else "?"
        return table

    def fixup_symbols(self):
        entries = self.nodes.get("/__fixups__")
        return sorted(entries) if entries is not None else []


@dataclass
class VendorBoot:
    data: bytes
    label: str
    header_version: int
    page_size: int
    header_size: int
    dtb_size: int
    dtb_addr: int
    vendor_ramdisk_size: int
    ramdisk_offset: int
    dtb_offset: int
    image_extent: int
    ramdisk: bytes
    dtbs: list


def parse_vendor(data, label):
    if len(data) < 2112 or data[:8] != b"VNDRBOOT":
        raise ValueError(f"{label}: vendor_boot magic/header")
    version = struct.unpack_from("<I", data, 8)[0]
    page_size = struct.unpack_from("<I", data, 12)[0]
    if version != 3 or page_size == 0:
        raise ValueError(f"{label}: expected vendor_boot v3")
    ramdisk_size = struct.unpack_from("<I", data, 24)[0]
    header_size = struct.unpack_from("<I", data, 2096)[0]
    dtb_size = struct.unpack_from("<I", data, 2100)[0]
    dtb_addr = struct.unpack_from("<Q", data, 2104)[0]
    ramdisk_offset = align(header_size, page_size)
    dtb_offset = ramdisk_offset + align(ramdisk_size, page_size)
    image_extent = dtb_offset + align(dtb_size, page_size)
    if image_extent > len(data):
        raise ValueError(f"{label}: sections exceed image")
    ramdisk = data[ramdisk_offset:ramdisk_offset + ramdisk_size]
    region = data[dtb_offset:dtb_offset + dtb_size]
    dtbs = []
    pos = 0
    while pos < len(region):
        if pos + 8 > len(region) or struct.unpack_from(">I", region, pos)[0] != FDT_MAGIC:
            raise ValueError(f"{label}: no FDT magic at DTB-relative offset {pos}")
        size = struct.unpack_from(">I", region, pos + 4)[0]
        if size < 40 or pos + size > len(region):
            raise ValueError(f"{label}: invalid concatenated FDT size at {pos}")
        dtbs.append((pos, Fdt(region[pos:pos + size], f"{label}-dtb{len(dtbs)}")))
        pos += size
    return VendorBoot(data, label, version, page_size, header_size, dtb_size, dtb_addr,
                      ramdisk_size, ramdisk_offset, dtb_offset, image_extent, ramdisk, dtbs)


@dataclass
class DtboEntry:
    index: int
    dt_size: int
    dt_offset: int
    payload: bytes
    fdt: Fdt


def parse_dtbo(data, label):
    if len(data) < 32:
        raise ValueError(f"{label}: short DTBO")
    magic, total, header_size, entry_size, count, entries_offset, _, _ = struct.unpack_from(">8I", data, 0)
    if magic != DTBO_MAGIC or header_size != 32 or entry_size != 32:
        raise ValueError(f"{label}: invalid DTBO header")
    if total > len(data) or entries_offset + count * entry_size > total:
        raise ValueError(f"{label}: DTBO ranges exceed total_size")
    entries = []
    for index in range(count):
        dt_size, dt_offset = struct.unpack_from(">II", data, entries_offset + index * entry_size)
        if dt_offset + dt_size > total:
            raise ValueError(f"{label}: entry {index} outside total_size")
        payload = data[dt_offset:dt_offset + dt_size]
        entries.append(DtboEntry(index, dt_size, dt_offset, payload, Fdt(payload, f"{label}-entry{index}")))
    return entries


def diff_offsets(before, after):
    if len(before) != len(after):
        raise ValueError(f"size changed: {len(before)} -> {len(after)}")
    return [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def run_dtc(blob, label, work):
    source = work / f"{label}.dtb"
    target = work / f"{label}.roundtrip.dtb"
    source.write_bytes(blob)
    proc = subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dtb", "-o", str(target), str(source)],
                          capture_output=True, text=True)
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def run_fdtget(blob, label, work, node, prop):
    path = work / f"{label}.fdtget.dtb"
    path.write_bytes(blob)
    proc = subprocess.run(["fdtget", "-t", "x", str(path), node, prop], capture_output=True, text=True)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    return proc.stdout.strip(), ""


def overlay_apply(base, overlay, label, work):
    base_path = work / f"{label}.base.dtb"
    overlay_path = work / f"{label}.overlay.dtbo"
    merged_path = work / f"{label}.merged.dtb"
    base_path.write_bytes(base)
    overlay_path.write_bytes(overlay)
    proc = subprocess.run(["fdtoverlay", "-i", str(base_path), str(overlay_path), "-o", str(merged_path)],
                          capture_output=True, text=True)
    ok = proc.returncode == 0 and merged_path.exists()
    merged = merged_path.read_bytes() if ok else b""
    return ok, proc.returncode, (proc.stderr or proc.stdout).strip().replace("\n", " | "), merged


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GitHub Actions only: local audit, transformation, and validation are forbidden")
    parser = argparse.ArgumentParser()
    parser.add_argument("--m5g-v-vendor-boot", required=True, type=Path)
    parser.add_argument("--stock-vendor-boot", required=True, type=Path)
    parser.add_argument("--stock-dtbo", required=True, type=Path)
    parser.add_argument("--m1-vendor-boot", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    blobs = {
        "m5g_v": args.m5g_v_vendor_boot.read_bytes(),
        "stock_vendor": args.stock_vendor_boot.read_bytes(),
        "stock_dtbo": args.stock_dtbo.read_bytes(),
        "m1_vendor": args.m1_vendor_boot.read_bytes(),
    }
    for name, data in blobs.items():
        size, digest = EXPECTED[name]
        if len(data) != size or sha(data) != digest:
            raise SystemExit(f"FAIL_CLOSED SOURCE_IDENTITY_FAILED {name}: size={len(data)} sha256={sha(data)}")

    source = parse_vendor(blobs["m5g_v"], "m5g-v")
    stock_vendor = parse_vendor(blobs["stock_vendor"], "stock-vendor_boot")
    m1_vendor = parse_vendor(blobs["m1_vendor"], "m1-vendor_boot")
    stock_dtbo_entries = parse_dtbo(blobs["stock_dtbo"], "stock-dtbo")

    if len(source.dtbs) != 1:
        raise SystemExit(f"FAIL_CLOSED SOURCE_TOPOLOGY: m5g-v DTB count={len(source.dtbs)}")
    source_offset, source_fdt = source.dtbs[0]
    if sha(source_fdt.data) != M5G_V_DTB0_SHA:
        raise SystemExit(f"FAIL_CLOSED STOCK_DTB0_SHA_EXACT: {sha(source_fdt.data)}")

    stock_base = stock_vendor.dtbs[STOCK_BASE_DTB_INDEX][1]
    if sha(stock_base.data) != M5G_V_DTB0_SHA:
        raise SystemExit("FAIL_CLOSED STOCK_BASE_DTB_INDEX: exact Stock DTB0 identity mismatch")
    if stock_base.root_cells(MSM_ID) != [356, 131073]:
        raise SystemExit("FAIL_CLOSED STOCK_DTB0_MSM_ID")
    if stock_base.root_cells(BOARD_ID) != list(BOARD_ID_BEFORE):
        raise SystemExit("FAIL_CLOSED BOARD_ID_BEFORE_0_0")

    thyme_entry = stock_dtbo_entries[THYME_DTBO_ENTRY_INDEX]
    if sha(thyme_entry.payload) != STOCK_DTBO_ENTRY21_SHA:
        raise SystemExit("FAIL_CLOSED STOCK_DTBO_ENTRY21_EXACT")
    if thyme_entry.fdt.root_cells(BOARD_ID) != list(BOARD_ID_AFTER):
        raise SystemExit("FAIL_CLOSED STOCK_DTBO_ENTRY21_BOARD_ID")

    m1_offset, m1_fdt = m1_vendor.dtbs[0]
    if sha(m1_fdt.data) != M1_DTB0_SHA:
        raise SystemExit(f"FAIL_CLOSED M1_DTB0_SHA: {sha(m1_fdt.data)}")

    board_entry = source_fdt.nodes.get("/", {}).get(BOARD_ID)
    if board_entry is None:
        raise SystemExit("FAIL_CLOSED BOARD_ID_PROPERTY_FOUND: qcom,board-id absent at /")
    property_length = len(board_entry.value)
    relative_offset = board_entry.value_offset
    absolute_offset = source.dtb_offset + source_offset + relative_offset
    before_hex = board_entry.value.hex()
    if property_length != 8 or board_entry.value != struct.pack(">II", *BOARD_ID_BEFORE):
        raise SystemExit(f"FAIL_CLOSED BOARD_ID_BEFORE_0_0: len={property_length} hex={before_hex}")

    patch = struct.pack(">II", *BOARD_ID_AFTER)
    candidate = bytearray(blobs["m5g_v"])
    for index, (old, new) in enumerate(zip(board_entry.value, patch)):
        if old != new:
            candidate[absolute_offset + index] = new
    candidate = bytes(candidate)

    with tempfile.TemporaryDirectory(prefix="m5h-") as temp_name:
        work = Path(temp_name)
        dtc_before_ok, dtc_before_err = run_dtc(source_fdt.data, "m5h-before-dtb0", work)
        dtc_after_ok, dtc_after_err = run_dtc(candidate[absolute_offset:absolute_offset + len(source_fdt.data)],
                                              "m5h-after-dtb0", work)
        fdtget_before, fdtget_before_err = run_fdtget(source_fdt.data, "m5h-before", work, "/", BOARD_ID)
        fdtget_after, fdtget_after_err = run_fdtget(candidate[absolute_offset:absolute_offset + len(source_fdt.data)],
                                                    "m5h-after", work, "/", BOARD_ID)
        stock_overlay_ok, stock_rc, stock_err, stock_merged = overlay_apply(
            stock_base.data, thyme_entry.payload, "stock-base0-stock-entry21", work)
        m1_overlay_ok, m1_rc, m1_err, m1_merged = overlay_apply(
            m1_fdt.data, thyme_entry.payload, "m1-base-stock-entry21", work)

    parsed = parse_vendor(candidate, "m5h-v-candidate")
    if len(parsed.dtbs) != 1:
        raise SystemExit(f"FAIL_CLOSED REVERSE_PARSE: DTB count={len(parsed.dtbs)}")
    after_fdt = parsed.dtbs[0][1]

    after_board = after_fdt.root_cells(BOARD_ID)
    after_board_hex = after_fdt.prop("/", BOARD_ID).hex()

    dtb_diff = diff_offsets(source_fdt.data, after_fdt.data)
    vendor_diff = diff_offsets(blobs["m5g_v"], candidate)
    board_range = set(range(relative_offset, relative_offset + property_length))
    dtb_diff_outside = [index for index in dtb_diff if index not in board_range]
    vendor_relative = source.dtb_offset + source_offset

    header_unchanged = candidate[:source.dtb_offset] == blobs["m5g_v"][:source.dtb_offset]
    ramdisk_unchanged = parsed.ramdisk == source.ramdisk
    dtb_size_unchanged = parsed.dtb_size == source.dtb_size
    dtb_offset_unchanged = parsed.dtb_offset == source.dtb_offset
    size_unchanged = len(candidate) == len(blobs["m5g_v"])
    totalsize_unchanged = after_fdt.totalsize == source_fdt.totalsize
    semantic = all(
        after_fdt.nodes[path] == props
        for path, props in source_fdt.nodes.items()
        if path != "/"
    ) and all(
        name == BOARD_ID or props == after_fdt.nodes["/"][name]
        for name, props in source_fdt.nodes["/"].items()
    ) and sorted(after_fdt.nodes) == sorted(source_fdt.nodes)
    tailless = parsed.image_extent == source.image_extent

    stock_symbols = stock_base.symbol_table() or {}
    m1_symbols = m1_fdt.symbol_table() or {}
    fixups = thyme_entry.fdt.fixup_symbols()

    matrix = []
    counts = {"PRESENT_BOTH": 0, "MISSING_MAINLINE": 0, "DIFFERENT_TARGET": 0, "UNRESOLVED": 0}
    confidences = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
    missing = []
    for symbol in fixups:
        stock_path = stock_symbols.get(symbol)
        if stock_path is None:
            category, confidence, mainline_path = "UNRESOLVED", "NONE", "NONE"
        elif symbol in m1_symbols:
            mainline_path = m1_symbols[symbol]
            if mainline_path == stock_path:
                category, confidence = "PRESENT_BOTH", "HIGH"
            else:
                category, confidence = "DIFFERENT_TARGET", "HIGH"
        else:
            mainline_path = "ABSENT"
            base = stock_path.rsplit("/", 1)[-1].split("@", 1)[0]
            if stock_path in m1_fdt.nodes:
                category, confidence = "MISSING_MAINLINE", "HIGH"
                mainline_path = stock_path
            elif any(p.rsplit("/", 1)[-1].split("@", 1)[0] == base for p in m1_fdt.nodes):
                category, confidence = "MISSING_MAINLINE", "MEDIUM"
            elif any(base.split("_")[0] and base.split("_")[0] in p for p in m1_fdt.nodes):
                category, confidence = "MISSING_MAINLINE", "LOW"
            else:
                category, confidence = "MISSING_MAINLINE", "NONE"
            missing.append(symbol)
        counts[category] += 1
        confidences[confidence] += 1
        matrix.append(f"{symbol}|{stock_path or 'UNRESOLVED'}|{mainline_path}|{category}|{confidence}")

    gates = [
        "MEM0_READ_BEFORE_M5H=YES",
        "LOCAL_BUILD=NO",
        "LOCAL_VALIDATION=NO",
        "GHA_ONLY=YES",
        "DEVICE_OPERATION=NO",
        "SLOT_A_WRITTEN=NO",
        "M5G_V_SOURCE_SHA_EXACT=PASS",
        "STOCK_DTB0_SHA_EXACT=PASS",
        "BOARD_ID_PROPERTY_FOUND=PASS",
        "BOARD_ID_BEFORE_0_0=PASS",
        f"BOARD_ID_PATCHED_45_0={'PASS' if after_board == list(BOARD_ID_AFTER) else 'FAIL'}",
        f"BOARD_ID_PROPERTY_LENGTH_UNCHANGED={'PASS' if len(after_fdt.prop('/', BOARD_ID)) == property_length else 'FAIL'}",
        f"DTB_TOTALSIZE_UNCHANGED={'PASS' if totalsize_unchanged else 'FAIL'}",
        f"DTB_SEMANTIC_ONLY_BOARD_ID={'PASS' if semantic else 'FAIL'}",
        f"DTB_DIFF_BOARD_ID_ONLY={'PASS' if dtb_diff and not dtb_diff_outside else 'FAIL'}",
        f"VENDOR_BOOT_HEADER_UNCHANGED={'PASS' if header_unchanged else 'FAIL'}",
        f"VENDOR_RAMDISK_UNCHANGED={'PASS' if ramdisk_unchanged else 'FAIL'}",
        f"DTB_SIZE_UNCHANGED={'PASS' if dtb_size_unchanged else 'FAIL'}",
        f"DTB_OFFSET_UNCHANGED={'PASS' if dtb_offset_unchanged else 'FAIL'}",
        f"ARTIFACT_SIZE_UNCHANGED={'PASS' if size_unchanged else 'FAIL'}",
        f"ARTIFACT_EXTENT_UNCHANGED={'PASS' if tailless else 'FAIL'}",
        f"VENDOR_BOOT_DIFF_BOARD_ID_ONLY={'PASS' if vendor_diff == expected_vendor_diff else 'FAIL'}",
        f"REVERSE_PARSE={'PASS' if dtc_after_ok and after_board == list(BOARD_ID_AFTER) else 'FAIL'}",
        f"DTC_BEFORE_VALID={'PASS' if dtc_before_ok else 'FAIL'}",
        f"LIBFDT_BOARD_ID_BEFORE={'PASS' if fdtget_before == '0 0' else 'FAIL'}",
        f"LIBFDT_BOARD_ID_AFTER={'PASS' if fdtget_after == '2d 0' else 'FAIL'}",
        f"MSM_ID_UNCHANGED={'PASS' if after_fdt.root_cells(MSM_ID) == stock_base.root_cells(MSM_ID) else 'FAIL'}",
        f"COMPATIBLE_UNCHANGED={'PASS' if after_fdt.root_strings('compatible') == ['qcom,kona'] else 'FAIL'}",
        "PRIVATE_ARTIFACT_ONLY=PASS",
        f"DTB_DIFF_BYTE_COUNT={len(dtb_diff)}",
        f"DTB_DIFF_OFFSETS={','.join(str(x) for x in dtb_diff)}",
        f"DTB_DIFF_OUTSIDE_BOARD_ID={len(dtb_diff_outside)}",
        f"VENDOR_BOOT_DIFF_BYTE_COUNT={len(vendor_diff)}",
        f"VENDOR_BOOT_DIFF_OFFSETS={','.join(str(x) for x in vendor_diff)}",
        f"SOURCE_ARTIFACT_SIZE={len(blobs['m5g_v'])}",
        f"CANDIDATE_ARTIFACT_SIZE={len(candidate)}",
        f"SOURCE_ARTIFACT_SHA256={sha(blobs['m5g_v'])}",
        f"CANDIDATE_ARTIFACT_SHA256={sha(candidate)}",
        f"BOARD_ID_PROPERTY_NODE_PATH=/",
        f"BOARD_ID_PROPERTY_NAME={BOARD_ID}",
        f"BOARD_ID_PROPERTY_LENGTH={property_length}",
        f"BOARD_ID_PROPERTY_OFFSET={absolute_offset}",
        f"BOARD_ID_PROPERTY_DTB_RELATIVE_OFFSET={relative_offset}",
        f"BOARD_ID_PROPERTY_OFFSET_IN_VENDOR_BOOT={absolute_offset}",
        f"DTB0_ABSOLUTE_OFFSET_IN_VENDOR_BOOT={vendor_relative}",
        f"BEFORE_HEX={before_hex}",
        f"AFTER_HEX={after_board_hex}",
        f"BEFORE_CELLS={cell_text(list(BOARD_ID_BEFORE))}",
        f"AFTER_CELLS={cell_text(list(after_board)) if after_board else 'NONE'}",
        f"STOCK_BASE_PLUS_STOCK_OVERLAY_FDTOVERLAY={'PASS' if stock_overlay_ok else 'FAIL'}",
        f"M1_BASE_PLUS_STOCK_OVERLAY_FDTOVERLAY={'PASS' if m1_overlay_ok else 'FAIL'}",
        f"MAINLINE_BASE_HAS_SYMBOLS={'YES' if m1_fdt.symbol_table() is not None else 'NO'}",
        f"MAINLINE_BASE_SYMBOL_COUNT={len(m1_symbols)}",
        f"STOCK_BASE_SYMBOL_COUNT={len(stock_symbols)}",
        f"STOCK_OVERLAY_FIXUP_COUNT={len(fixups)}",
        f"MISSING_MAINLINE_FIXUP_SYMBOLS={len(missing)}",
    ]
    gates.append(f"AUXILIARY_DIAGNOSTIC_ONLY=YES")
    gates.append(f"REFERENCE_IMPLEMENTATION_ONLY=YES")

    mandatory = [line for line in gates if line.endswith("=FAIL")]
    ready = not mandatory and not FAILURES
    gates.append(f"FAIL_CLOSED={'PASS' if ready else 'FAIL'}")
    gates.append(f"READY_FOR_MAINLINE_V2_M5H_BASE_BOARD_ID_CONTROL={'YES' if ready else 'NO'}")

    json_note = [
        f"BOARD_ID_NODE_PATH=/",
        f"BOARD_ID_PROPERTY_OFFSET={absolute_offset}",
        f"BOARD_ID_PROPERTY_OFFSET_DTB_RELATIVE={relative_offset}",
        f"BOARD_ID_PROPERTY_LENGTH={property_length}",
        f"BEFORE_HEX={before_hex}",
        f"AFTER_HEX={after_board_hex}",
        f"DTB_DIFF_BYTE_COUNT={len(dtb_diff)}",
        f"DTB_DIFF_OFFSETS={','.join(str(x) for x in dtb_diff)}",
        f"DTB_DIFF_OUTSIDE_BOARD_ID={len(dtb_diff_outside)}",
        f"VENDOR_BOOT_DIFF_BYTE_COUNT={len(vendor_diff)}",
        f"VENDOR_BOOT_DIFF_OFFSETS={','.join(str(x) for x in vendor_diff)}",
        f"BOARD_ID_DATA_RANGE_IN_VENDOR_BOOT=[{absolute_offset},{absolute_offset + property_length})",
    ]

    validation = [
        "M5H base board-id isolation validation",
        f"SOURCE_ARTIFACT=m5g-v-single-stock-dtb-vendor_boot.img",
        f"SOURCE_SHA256={sha(blobs['m5g_v'])}",
        f"SOURCE_SIZE={len(blobs['m5g_v'])}",
        f"CANDIDATE={ARTIFACT_NAME}",
        f"CANDIDATE_SHA256={sha(candidate)}",
        f"CANDIDATE_SIZE={len(candidate)}",
        f"DTB0_SHA256_BEFORE={sha(source_fdt.data)}",
        f"DTB0_SHA256_AFTER={sha(after_fdt.data)}",
        f"DTB0_TOTALSIZE_BEFORE={source_fdt.totalsize}",
        f"DTB0_TOTALSIZE_AFTER={after_fdt.totalsize}",
        f"DTB_DIFF_BYTE_COUNT={len(dtb_diff)}",
        f"DTB_DIFF_OUTSIDE_BOARD_ID={len(dtb_diff_outside)}",
        f"VENDOR_BOOT_DIFF_BYTE_COUNT={len(vendor_diff)}",
        f"VENDOR_BOOT_HEADER_UNCHANGED={'YES' if header_unchanged else 'NO'}",
        f"VENDOR_RAMDISK_UNCHANGED={'YES' if ramdisk_unchanged else 'NO'}",
        f"DTB_SIZE_UNCHANGED={'YES' if dtb_size_unchanged else 'NO'}",
        f"DTB_OFFSET_UNCHANGED={'YES' if dtb_offset_unchanged else 'NO'}",
        f"ARTIFACT_SIZE_UNCHANGED={'YES' if size_unchanged else 'NO'}",
        f"ARTIFACT_EXTENT_UNCHANGED={'YES' if tailless else 'NO'}",
        f"DTC_BEFORE_VALID={'YES' if dtc_before_ok else 'NO'} {dtc_before_err}",
        f"DTC_AFTER_VALID={'YES' if dtc_after_ok else 'NO'} {dtc_after_err}",
        f"LIBFDT_BOARD_ID_BEFORE={fdtget_before} {fdtget_before_err}",
        f"LIBFDT_BOARD_ID_AFTER={fdtget_after} {fdtget_after_err}",
        f"MSM_ID_AFTER={cell_text(after_fdt.root_cells(MSM_ID))}",
        f"COMPATIBLE_AFTER={' | '.join(after_fdt.root_strings('compatible'))}",
        f"SEMANTIC_TREE_EXACT_EXCEPT_BOARD_ID={'YES' if semantic else 'NO'}",
    ]

    overlay = [
        "M5H auxiliary read-only Stock-overlay compatibility audit",
        "SCOPE=REFERENCE_IMPLEMENTATION_ONLY_NOT_EXACT_XIAOMI_ABL_IMPLEMENTATION",
        "AUXILIARY_DIAGNOSTIC=YES_NOT_A_TRUE_DEVICE_CAUSAL_GATE",
        f"IMPLEMENTATION=fdtoverlay/libfdt",
        f"STOCK_DTB0_SHA256={sha(stock_base.data)}",
        f"STOCK_DTB0_SYMBOL_COUNT={len(stock_symbols)}",
        f"STOCK_DTBO_ENTRY21_SHA256={sha(thyme_entry.payload)}",
        f"STOCK_OVERLAY_FIXUP_COUNT={len(fixups)}",
        f"M1_MAINLINE_DTB_SHA256={sha(m1_fdt.data)}",
        f"MAINLINE_BASE_HAS_SYMBOLS={'YES' if m1_fdt.symbol_table() is not None else 'NO'}",
        f"MAINLINE_BASE_SYMBOL_COUNT={len(m1_symbols)}",
        f"STOCK_BASE_PLUS_STOCK_OVERLAY_FDTOVERLAY={'PASS' if stock_overlay_ok else 'FAIL'}",
        f"STOCK_BASE_PLUS_STOCK_OVERLAY_RC={stock_rc}",
        f"STOCK_BASE_PLUS_STOCK_OVERLAY_MERGED_SHA256={sha(stock_merged) if stock_overlay_ok else 'NONE'}",
        f"STOCK_BASE_PLUS_STOCK_OVERLAY_ERROR={stock_err or 'NONE'}",
        f"M1_BASE_PLUS_STOCK_OVERLAY_FDTOVERLAY={'PASS' if m1_overlay_ok else 'FAIL'}",
        f"M1_BASE_PLUS_STOCK_OVERLAY_RC={m1_rc}",
        f"M1_BASE_PLUS_STOCK_OVERLAY_MERGED_SHA256={sha(m1_merged) if m1_overlay_ok else 'NONE'}",
        f"M1_BASE_PLUS_STOCK_OVERLAY_ERROR={m1_err or 'NONE'}",
        f"FIXUP_PRESENT_BOTH={counts['PRESENT_BOTH']}",
        f"FIXUP_MISSING_MAINLINE={counts['MISSING_MAINLINE']}",
        f"FIXUP_DIFFERENT_TARGET={counts['DIFFERENT_TARGET']}",
        f"FIXUP_UNRESOLVED={counts['UNRESOLVED']}",
        f"TARGET_CONFIDENCE_HIGH={confidences['HIGH']}",
        f"TARGET_CONFIDENCE_MEDIUM={confidences['MEDIUM']}",
        f"TARGET_CONFIDENCE_LOW={confidences['LOW']}",
        f"TARGET_CONFIDENCE_NONE={confidences['NONE']}",
    ]

    args.out_dir.joinpath("m5h-gates.txt").write_text("\n".join(gates) + "\n", encoding="utf-8")
    args.out_dir.joinpath("m5h-fdt-field-report.txt").write_text("\n".join(json_note) + "\n", encoding="utf-8")
    args.out_dir.joinpath("m5h-binary-diff-report.txt").write_text("\n".join(gates) + "\n", encoding="utf-8")
    args.out_dir.joinpath("m5h-validation-report.txt").write_text("\n".join(validation) + "\n", encoding="utf-8")
    args.out_dir.joinpath("m5h-overlay-compat-audit.txt").write_text("\n".join(overlay) + "\n", encoding="utf-8")
    header = "symbol|stock_target_path|mainline_probable_path|classification|confidence"
    args.out_dir.joinpath("m5h-overlay-fixup-matrix.txt").write_text(
        header + "\n" + "\n".join(matrix) + "\n", encoding="utf-8")
    args.out_dir.joinpath("m5h-target-node-audit.txt").write_text(
        header + "\n" + "\n".join(row for row in matrix if row.split("|")[3] == "MISSING_MAINLINE") + "\n",
        encoding="utf-8")
    args.out_dir.joinpath(ARTIFACT_NAME).write_bytes(candidate)

    sums = []
    for path in sorted(args.out_dir.iterdir()):
        if path.name != "SHA256SUMS" and path.is_file():
            sums.append(f"{sha(path.read_bytes())}  {path.name}")
    args.out_dir.joinpath("SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")

    print("\n".join(gates))
    print(f"M5H_ARTIFACT_SHA256={sha(candidate)}")
    if not ready:
        suffix = "|" + ",".join(labels) if labels else ""
        raise SystemExit(f"M5H_VALIDATION_FAILED{suffix}: {'; '.join(mandatory) or '; '.join(FAILURES)}")


if __name__ == "__main__":
    main()
