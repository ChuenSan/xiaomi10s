#!/usr/bin/env python3
import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

EXPECTED = {
    "stock_vendor": (100663296, "aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"),
    "stock_dtbo": (33554432, "018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"),
    "m1_vendor": (114688, "29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5"),
    "m1_dtbo": (387, "316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1"),
}
FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, size):
    return (value + size - 1) // size * size


def cstr(data):
    return data.split(b"\0", 1)[0].decode("utf-8", "replace")


def cells(data):
    if len(data) % 4:
        return None
    return list(struct.unpack(f">{len(data) // 4}I", data))


def cell_text(data):
    values = cells(data)
    if values is None:
        return f"[{data.hex()}]"
    return "<" + " ".join(f"0x{x:x}" for x in values) + "> (" + " ".join(str(x) for x in values) + ")"


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
                if not stack:
                    path = "/"
                else:
                    path = stack[-1].rstrip("/") + "/" + name
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
        prop = self.nodes.get(path, {}).get(name)
        return None if prop is None else prop.value

    def root_strings(self, name):
        value = self.prop("/", name)
        return [] if value is None else (strings(value) or [])

    def root_cells(self, name):
        value = self.prop("/", name)
        return None if value is None else cells(value)

    def direct_children(self, path):
        prefix = path.rstrip("/") + "/"
        return [node for node in self.nodes if node.startswith(prefix) and "/" not in node[len(prefix):]]


def prop_text(name, value):
    if name in {"model", "compatible", "device_type", "status", "bootargs", "stdout-path", "target-path"}:
        value_strings = strings(value)
        if value_strings is not None:
            return " | ".join(value_strings)
    value_strings = strings(value)
    if value_strings is not None:
        return " | ".join(value_strings)
    if len(value) % 4 == 0:
        return cell_text(value)
    return "0x" + value.hex()


def root_field(fdt, name):
    value = fdt.prop("/", name)
    return "NONE" if value is None else prop_text(name, value)


def memory_summary(fdt):
    found = []
    for path, props in fdt.nodes.items():
        base = path.rsplit("/", 1)[-1]
        device_type = props.get("device_type")
        root_child = path.startswith("/") and path.count("/") == 1
        if root_child and (base == "memory" or base.startswith("memory@") or (device_type and strings(device_type.value) == ["memory"])):
            fields = []
            for name in ("device_type", "reg", "status"):
                if name in props:
                    fields.append(f"{name}={prop_text(name, props[name].value)}")
            found.append(f"{path}: " + "; ".join(fields))
    return found or ["NONE"]


def chosen_summary(fdt):
    props = fdt.nodes.get("/chosen")
    if props is None:
        return ["NONE"]
    if not props:
        return ["PRESENT_EMPTY"]
    return [f"{name}={prop_text(name, prop.value)}" for name, prop in sorted(props.items())]


def reserved_summary(fdt):
    if "/reserved-memory" not in fdt.nodes:
        return ["NONE"]
    result = []
    root = fdt.nodes["/reserved-memory"]
    result.append("ROOT " + "; ".join(f"{name}={prop_text(name, prop.value)}" for name, prop in sorted(root.items())))
    for path in sorted(fdt.direct_children("/reserved-memory")):
        props = fdt.nodes[path]
        values = []
        for name in ("reg", "size", "alignment", "alloc-ranges", "no-map", "reusable", "compatible", "status"):
            if name in props:
                values.append(f"{name}={prop_text(name, props[name].value)}")
        result.append(f"{path}: " + "; ".join(values))
    return result


def pmic_summary(fdt):
    rows = []
    for path, props in sorted(fdt.nodes.items()):
        for name, prop in sorted(props.items()):
            if "pmic-id" in name or "pmic-revid" in name:
                rows.append(f"{path}:{name}={prop_text(name, prop.value)}")
    return rows or ["NONE"]


def overlay_summary(fdt):
    fragments = [path for path in fdt.direct_children("/") if path.rsplit("/", 1)[-1].startswith("fragment@")]
    targets = []
    for path in sorted(fragments):
        props = fdt.nodes[path]
        if "target-path" in props:
            targets.append(f"{path}:target-path={prop_text('target-path', props['target-path'].value)}")
        elif "target" in props:
            targets.append(f"{path}:target={prop_text('target', props['target'].value)}")
        else:
            targets.append(f"{path}:NO_TARGET")
    special = []
    for path in ("/__fixups__", "/__local_fixups__", "/__symbols__"):
        props = fdt.nodes.get(path)
        if props is None:
            special.append(f"{path}=ABSENT")
        else:
            special.append(f"{path}=PRESENT count={len(props)} names={','.join(sorted(props))}")
    markers = []
    for path, props in sorted(fdt.nodes.items()):
        for name in props:
            if "thyme" in name and name not in {"model", "compatible"}:
                markers.append(f"{path}:{name}")
    return fragments, targets, special, markers


def fdt_detail(fdt, prefix=""):
    fragments, targets, special, markers = overlay_summary(fdt)
    lines = [
        f"{prefix}TOTALSIZE={fdt.totalsize}",
        f"{prefix}SHA256={sha(fdt.data)}",
        f"{prefix}MODEL={root_field(fdt, 'model')}",
        f"{prefix}COMPATIBLE={root_field(fdt, 'compatible')}",
        f"{prefix}MSM_ID={root_field(fdt, 'qcom,msm-id')}",
        f"{prefix}BOARD_ID={root_field(fdt, 'qcom,board-id')}",
        f"{prefix}SOC_REVISION={root_field(fdt, 'qcom,msm-id')}",
        f"{prefix}MEMORY={' || '.join(memory_summary(fdt))}",
        f"{prefix}CHOSEN={' || '.join(chosen_summary(fdt))}",
        f"{prefix}RESERVED_MEMORY_COUNT={max(0, len(reserved_summary(fdt)) - 1)}",
        f"{prefix}RESERVED_MEMORY={' || '.join(reserved_summary(fdt))}",
        f"{prefix}PMIC_SELECTORS={' || '.join(pmic_summary(fdt))}",
        f"{prefix}FRAGMENT_COUNT={len(fragments)}",
        f"{prefix}TARGETS={' || '.join(targets) if targets else 'NONE'}",
        f"{prefix}FIXUPS_SYMBOLS={' || '.join(special)}",
        f"{prefix}MARKERS={' || '.join(markers) if markers else 'NONE'}",
    ]
    return lines


@dataclass
class VendorBoot:
    data: bytes
    label: str
    header_version: int
    page_size: int
    kernel_addr: int
    ramdisk_addr: int
    vendor_ramdisk_size: int
    cmdline: str
    tags_addr: int
    product: str
    header_size: int
    dtb_size: int
    dtb_addr: int
    ramdisk_offset: int
    dtb_offset: int
    image_extent: int
    ramdisk: bytes
    dtb_region: bytes
    dtbs: list


def parse_vendor(data, label):
    if len(data) < 2112 or data[:8] != b"VNDRBOOT":
        raise ValueError(f"{label}: vendor_boot magic/header")
    version = struct.unpack_from("<I", data, 8)[0]
    page_size = struct.unpack_from("<I", data, 12)[0]
    if version != 3 or page_size == 0:
        raise ValueError(f"{label}: expected vendor_boot v3")
    values = {
        "kernel_addr": struct.unpack_from("<I", data, 16)[0],
        "ramdisk_addr": struct.unpack_from("<I", data, 20)[0],
        "vendor_ramdisk_size": struct.unpack_from("<I", data, 24)[0],
        "cmdline": cstr(data[28:2076]),
        "tags_addr": struct.unpack_from("<I", data, 2076)[0],
        "product": cstr(data[2080:2096]),
        "header_size": struct.unpack_from("<I", data, 2096)[0],
        "dtb_size": struct.unpack_from("<I", data, 2100)[0],
        "dtb_addr": struct.unpack_from("<Q", data, 2104)[0],
    }
    ramdisk_offset = align(values["header_size"], page_size)
    dtb_offset = ramdisk_offset + align(values["vendor_ramdisk_size"], page_size)
    image_extent = dtb_offset + align(values["dtb_size"], page_size)
    if image_extent > len(data):
        raise ValueError(f"{label}: sections exceed image")
    ramdisk = data[ramdisk_offset:ramdisk_offset + values["vendor_ramdisk_size"]]
    region = data[dtb_offset:dtb_offset + values["dtb_size"]]
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
    return VendorBoot(data, label, version, page_size, values["kernel_addr"], values["ramdisk_addr"],
                      values["vendor_ramdisk_size"], values["cmdline"], values["tags_addr"], values["product"],
                      values["header_size"], values["dtb_size"], values["dtb_addr"], ramdisk_offset, dtb_offset,
                      image_extent, ramdisk, region, dtbs)


def vendor_layout(vendor):
    lines = [
        f"LABEL={vendor.label}", f"FILE_SIZE={len(vendor.data)}", f"SHA256={sha(vendor.data)}",
        "MAGIC=VNDRBOOT", f"HEADER_VERSION={vendor.header_version}", f"HEADER_SIZE={vendor.header_size}",
        f"PAGE_SIZE={vendor.page_size}", f"KERNEL_ADDR=0x{vendor.kernel_addr:x}",
        f"RAMDISK_ADDR=0x{vendor.ramdisk_addr:x}", f"TAGS_ADDR=0x{vendor.tags_addr:x}",
        f"DTB_ADDR=0x{vendor.dtb_addr:x}", f"VENDOR_RAMDISK_OFFSET={vendor.ramdisk_offset}",
        f"VENDOR_RAMDISK_SIZE={vendor.vendor_ramdisk_size}", f"VENDOR_RAMDISK_SHA256={sha(vendor.ramdisk)}",
        f"DTB_AREA_OFFSET={vendor.dtb_offset}", f"DTB_AREA_SIZE={vendor.dtb_size}",
        f"DTB_AREA_PADDED_END={vendor.image_extent}", f"DTB_PAYLOAD_COUNT={len(vendor.dtbs)}",
        f"PRODUCT={vendor.product}", f"CMDLINE={vendor.cmdline}",
    ]
    for index, (offset, fdt) in enumerate(vendor.dtbs):
        lines.extend([f"DTB{index}_RELATIVE_OFFSET={offset}", f"DTB{index}_ABSOLUTE_OFFSET={vendor.dtb_offset + offset}"])
        lines.extend(fdt_detail(fdt, f"DTB{index}_"))
    return lines


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
    if len(data) < 32:
        raise ValueError(f"{label}: short DTBO")
    header = struct.unpack_from(">8I", data, 0)
    magic, total, header_size, entry_size, count, entries_offset, page_size, version = header
    if magic != DTBO_MAGIC or header_size != 32 or entry_size != 32:
        raise ValueError(f"{label}: invalid DTBO header")
    if total > len(data) or entries_offset + count * entry_size > total:
        raise ValueError(f"{label}: DTBO ranges exceed total_size")
    entries = []
    for index in range(count):
        values = struct.unpack_from(">8I", data, entries_offset + index * entry_size)
        dt_size, dt_offset, image_id, rev, *custom = values
        if dt_offset + dt_size > total:
            raise ValueError(f"{label}: entry {index} outside total_size")
        payload = data[dt_offset:dt_offset + dt_size]
        entries.append(DtboEntry(index, dt_size, dt_offset, image_id, rev, tuple(custom), payload,
                                 Fdt(payload, f"{label}-entry{index}")))
    return Dtbo(data, label, total, header_size, entry_size, count, entries_offset, page_size, version, entries)


def dtbo_header(dtbo):
    return [
        f"LABEL={dtbo.label}", f"FILE_SIZE={len(dtbo.data)}", f"SHA256={sha(dtbo.data)}",
        "MAGIC=0xd7b7ab1e", f"TOTAL_SIZE={dtbo.total_size}", f"HEADER_SIZE={dtbo.header_size}",
        f"ENTRY_SIZE={dtbo.entry_size}", f"ENTRY_COUNT={dtbo.entry_count}",
        f"ENTRIES_OFFSET={dtbo.entries_offset}", f"PAGE_SIZE={dtbo.page_size}", f"VERSION={dtbo.version}",
        f"TRAILING_BYTES={len(dtbo.data) - dtbo.total_size}",
        f"TRAILING_SHA256={sha(dtbo.data[dtbo.total_size:])}",
    ]


def entry_detail(entry, prefix=""):
    lines = [
        f"{prefix}INDEX={entry.index}", f"{prefix}DT_SIZE={entry.dt_size}",
        f"{prefix}DT_OFFSET={entry.dt_offset}", f"{prefix}ID=0x{entry.image_id:08x}",
        f"{prefix}REV=0x{entry.rev:08x}",
    ]
    for index, value in enumerate(entry.custom):
        lines.append(f"{prefix}CUSTOM{index}=0x{value:08x}")
    lines.extend(fdt_detail(entry.fdt, prefix))
    return lines


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
    return Fdt(merged_path.read_bytes(), f"{label}-merged")


def pad_fdt(blob, target_size):
    fdt = Fdt(blob, "pad-source")
    if target_size < fdt.totalsize:
        raise ValueError("FDT does not fit target slot")
    result = bytearray(blob)
    struct.pack_into(">I", result, 4, target_size)
    result.extend(b"\0" * (target_size - len(result)))
    Fdt(result, "padded-fdt")
    return bytes(result)


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


def diff_section(name, before_name, after_name, before, after, intentional, secondary):
    ranges = changed_ranges(before, after)
    changed = sum(end - start for start, end, _ in ranges)
    lines = [
        f"CONTROL={name}", f"BEFORE_SOURCE={before_name}", f"AFTER_ARTIFACT={after_name}",
        f"BEFORE_SIZE={len(before)}", f"AFTER_SIZE={len(after)}", f"BEFORE_SHA256={sha(before)}",
        f"AFTER_SHA256={sha(after)}", f"EXACT_CHANGED_RANGE_COUNT={len(ranges)}",
        f"EXACT_CHANGED_BYTE_COUNT={changed}", f"INTENTIONAL_VARIABLE={intentional}",
        f"UNAVOIDABLE_SECONDARY_DELTA={secondary}",
    ]
    lines.extend(f"RANGE=0x{start:x}-0x{end:x} [{start},{end}) {kind}" for start, end, kind in ranges)
    lines.append("")
    return lines


def replace_vendor_dtb(source, replacement):
    result = bytearray(source.data[:source.dtb_offset])
    struct.pack_into("<I", result, 2100, len(replacement))
    result.extend(replacement)
    result.extend(b"\0" * (align(len(replacement), source.page_size) - len(replacement)))
    return bytes(result)


def write_lines(path, lines):
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GitHub Actions only: local audit, transformation, and validation are forbidden")
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-vendor-boot", required=True, type=Path)
    parser.add_argument("--stock-dtbo", required=True, type=Path)
    parser.add_argument("--m1-vendor-boot", required=True, type=Path)
    parser.add_argument("--m1-dtbo", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    blobs = {
        "stock_vendor": args.stock_vendor_boot.read_bytes(), "stock_dtbo": args.stock_dtbo.read_bytes(),
        "m1_vendor": args.m1_vendor_boot.read_bytes(), "m1_dtbo": args.m1_dtbo.read_bytes(),
    }
    for name, data in blobs.items():
        size, digest = EXPECTED[name]
        if len(data) != size or sha(data) != digest:
            raise SystemExit(f"{name}: authoritative identity mismatch: size={len(data)} sha256={sha(data)}")

    stock_vendor = parse_vendor(blobs["stock_vendor"], "stock-vendor_boot")
    m1_vendor = parse_vendor(blobs["m1_vendor"], "m1-vendor_boot")
    stock_dtbo = parse_dtbo(blobs["stock_dtbo"], "stock-dtbo")
    m1_dtbo = parse_dtbo(blobs["m1_dtbo"], "m1-dtbo")
    if len(stock_vendor.dtbs) != 4 or len(m1_vendor.dtbs) != 1:
        raise SystemExit("vendor_boot DTB topology mismatch")
    if stock_vendor.ramdisk != m1_vendor.ramdisk:
        raise SystemExit("M1 vendor ramdisk is not exact Stock")
    if stock_dtbo.entry_count != 29 or m1_dtbo.entry_count != 1:
        raise SystemExit("DTBO entry topology mismatch")

    stock_base_index = 0
    thyme_entry_index = 21
    stock_base = stock_vendor.dtbs[stock_base_index][1]
    thyme_entry = stock_dtbo.entries[thyme_entry_index]
    if stock_base.root_cells("qcom,msm-id") != [356, 131073]:
        raise SystemExit("stock DTB0 is not SM8250 v2.1")
    if stock_base.root_cells("qcom,board-id") != [0, 0]:
        raise SystemExit("stock DTB0 board-id is not <0 0>")
    if thyme_entry.fdt.root_cells("qcom,board-id") != [45, 0]:
        raise SystemExit("stock DTBO entry 21 board-id is not <45 0>")
    candidates = [entry.index for entry in stock_dtbo.entries if entry.fdt.root_cells("qcom,board-id") == [45, 0]]
    if candidates != [21]:
        raise SystemExit(f"VENDOR_BOOT_BASE_DTB_SELECTION_AMBIGUOUS: thyme DTBO candidates={candidates}")

    with tempfile.TemporaryDirectory(prefix="m5g-") as temp_name:
        work = Path(temp_name)
        for index, (_, fdt) in enumerate(stock_vendor.dtbs):
            validate_fdt(fdt.data, f"stock-vendor-dtb{index}", work)
        validate_fdt(m1_vendor.dtbs[0][1].data, "m1-vendor-dtb0", work)
        for entry in stock_dtbo.entries:
            validate_fdt(entry.payload, f"stock-dtbo-entry{entry.index}", work)
        validate_fdt(m1_dtbo.entries[0].payload, "m1-dtbo-entry0", work)
        apply_overlay(stock_base.data, thyme_entry.payload, "stock-base0-thyme21", work)
        apply_overlay(stock_base.data, m1_dtbo.entries[0].payload, "stock-base0-m1-noop", work)

        v_name = "m5g-v-single-stock-dtb-vendor_boot.img"
        v_control = replace_vendor_dtb(m1_vendor, stock_base.data)
        v_parsed = parse_vendor(v_control, "m5g-v-single-stock-dtb")
        if len(v_parsed.dtbs) != 1 or v_parsed.dtbs[0][1].data != stock_base.data:
            raise SystemExit("V control did not preserve single exact Stock DTB payload")
        if v_control[:2100] != m1_vendor.data[:2100] or v_control[2104:m1_vendor.dtb_offset] != m1_vendor.data[2104:m1_vendor.dtb_offset]:
            raise SystemExit("V control changed header/ramdisk bytes outside dtb_size")
        if v_parsed.ramdisk != m1_vendor.ramdisk:
            raise SystemExit("V control changed vendor ramdisk")
        validate_fdt(v_parsed.dtbs[0][1].data, "v-control-stock-base0", work)
        (args.out_dir / v_name).write_bytes(v_control)

        d_name = "m5g-d-stock-table-m1-payload-dtbo.img"
        padded_noop = pad_fdt(m1_dtbo.entries[0].payload, thyme_entry.dt_size)
        d_control = bytearray(stock_dtbo.data)
        selected_start = thyme_entry.dt_offset
        selected_end = selected_start + thyme_entry.dt_size
        d_control[selected_start:selected_end] = padded_noop
        d_control = bytes(d_control)
        d_parsed = parse_dtbo(d_control, "m5g-d-stock-table-m1-payload")
        if d_control[:selected_start] != stock_dtbo.data[:selected_start] or d_control[selected_end:] != stock_dtbo.data[selected_end:]:
            raise SystemExit("D control changed bytes outside thyme payload slot")
        if d_control[:stock_dtbo.entries_offset + stock_dtbo.entry_count * stock_dtbo.entry_size] != stock_dtbo.data[:stock_dtbo.entries_offset + stock_dtbo.entry_count * stock_dtbo.entry_size]:
            raise SystemExit("D control changed table metadata")
        for index, entry in enumerate(stock_dtbo.entries):
            if index != thyme_entry_index and d_parsed.entries[index].payload != entry.payload:
                raise SystemExit(f"D control changed non-thyme entry {index}")
        validate_fdt(d_parsed.entries[thyme_entry_index].payload, "d-control-padded-noop", work)
        merged_noop = apply_overlay(stock_base.data, d_parsed.entries[thyme_entry_index].payload, "d-control-base0", work)
        if not any("qcom,thyme-route-b-noop" in props for props in merged_noop.nodes.values()):
            raise SystemExit("D control no-op marker missing after overlay")
        (args.out_dir / d_name).write_bytes(d_control)

        d2_name = "m5g-d-single-table-stock-payload-dtbo.img"
        d2_control = bytearray(m1_dtbo.data[:m1_dtbo.entries[0].dt_offset])
        struct.pack_into(">I", d2_control, 4, m1_dtbo.entries[0].dt_offset + thyme_entry.dt_size)
        struct.pack_into(">I", d2_control, m1_dtbo.entries_offset, thyme_entry.dt_size)
        d2_control.extend(thyme_entry.payload)
        d2_control = bytes(d2_control)
        d2_parsed = parse_dtbo(d2_control, "m5g-d-single-table-stock-payload")
        if d2_parsed.entry_count != 1 or d2_parsed.entries[0].payload != thyme_entry.payload:
            raise SystemExit("D2 control payload/topology mismatch")
        validate_fdt(d2_parsed.entries[0].payload, "d2-control-stock-thyme", work)
        apply_overlay(stock_base.data, d2_parsed.entries[0].payload, "d2-control-base0", work)
        (args.out_dir / d2_name).write_bytes(d2_control)

    write_lines(args.out_dir / "vendor-boot-stock-layout.txt", vendor_layout(stock_vendor))
    write_lines(args.out_dir / "vendor-boot-m1-layout.txt", vendor_layout(m1_vendor))
    matrix = [
        "THYME_RELEVANT_STOCK_BASE_DTB_INDEX=0",
        "SELECTION_CONFIDENCE=STRONG_EXACT_ARTIFACT_PLUS_RECORDED_RUNTIME_DTB_IDX_0_AND_SUCCESSFUL_ENTRY21_MERGE",
        "VENDOR_BOOT_BASE_DTB_SELECTION_AMBIGUOUS=NO",
        "",
    ]
    for index, (offset, fdt) in enumerate(stock_vendor.dtbs):
        matrix.extend([f"[DTB{index}]", f"RELATIVE_OFFSET={offset}", f"ABSOLUTE_OFFSET={stock_vendor.dtb_offset + offset}"])
        matrix.extend(fdt_detail(fdt))
        matrix.append("")
    write_lines(args.out_dir / "vendor-boot-dtb-matrix.txt", matrix)
    write_lines(args.out_dir / "dtbo-stock-header.txt", dtbo_header(stock_dtbo))
    entries = []
    for entry in stock_dtbo.entries:
        entries.append(f"[ENTRY{entry.index}]")
        entries.extend(entry_detail(entry))
        entries.append("")
    write_lines(args.out_dir / "dtbo-stock-entry-matrix.txt", entries)
    write_lines(args.out_dir / "dtbo-m1-header.txt", dtbo_header(m1_dtbo))
    write_lines(args.out_dir / "dtbo-m1-entry.txt", entry_detail(m1_dtbo.entries[0]))

    stock_fragments, stock_targets, stock_special, _ = overlay_summary(thyme_entry.fdt)
    m1_fragments, m1_targets, m1_special, m1_markers = overlay_summary(m1_dtbo.entries[0].fdt)
    stock_all_board_ids = [fdt.root_cells("qcom,board-id") for _, fdt in stock_vendor.dtbs]
    factors = f"""# M5G factor decomposition

## Causal boundary

The complete 2×2 matrix proves that M1 `vendor_boot` and M1 `dtbo` are each sufficient in the other component's Stock background. It does not identify an ABL function, prove kernel entry, or attribute either effect to payload alone.

The common ~4.7s observable is consistent with two independently ABL-consumed DT-context changes converging on one fallback/reset path. Similar timing does not prove the same internal failure.

## Vendor_boot

- V1 topology: Stock `{len(stock_vendor.dtbs)}` concatenated FDTs; M1 `{len(m1_vendor.dtbs)}` FDT.
- V2 payload: Stock downstream kona family; M1 Mainline thyme.
- V3 selector placement: Stock base board-id values `{stock_all_board_ids}` with thyme board-id `<45 0>` in DTBO entry 21; M1 base board-id `{m1_vendor.dtbs[0][1].root_cells('qcom,board-id')}`.
- V4 compatible: Stock candidate `{stock_base.root_strings('compatible')}`; M1 `{m1_vendor.dtbs[0][1].root_strings('compatible')}`.
- V5 memory: Stock `{' || '.join(memory_summary(stock_base))}`; M1 `{' || '.join(memory_summary(m1_vendor.dtbs[0][1]))}`.
- V6 DTB area: Stock offset `{stock_vendor.dtb_offset}`, size `{stock_vendor.dtb_size}`, padded end `{stock_vendor.image_extent}`; M1 offset `{m1_vendor.dtb_offset}`, size `{m1_vendor.dtb_size}`, padded end `{m1_vendor.image_extent}`.

`THYME_RELEVANT_STOCK_BASE_DTB_INDEX=0` is strongly selected by exact DTB0 `<356 0x20001>/<0 0>`, exact entry 21 `<45 0>`, successful base0+entry21 merge, and the previously recorded runtime `dtb_idx=0`/`dtbo_idx=21`.

V-Control-1 is structurally feasible only as two separately labelled variants: V1A keeps M1 base board-id `<45 0>`; V1B changes it to Stock base `<0 0>`. Fixed DTB0 extent requires valid FDT trailing-space expansion, which is an unavoidable secondary delta. No V-Control-1 artifact is emitted this round.

V-Control-2 is emitted as `{v_name}`: M1 single-DTB semantics and byte-exact ramdisk/header fields, with exact Stock DTB0 payload. Its unavoidable deltas are `dtb_size`, artifact extent/page padding, and payload bytes.

## DTBO

- D1 container topology: Stock `{stock_dtbo.entry_count}` entries; M1 `{m1_dtbo.entry_count}` entry.
- D2 table/header: Stock total/header/entry/offset/page/version `{stock_dtbo.total_size}/{stock_dtbo.header_size}/{stock_dtbo.entry_size}/{stock_dtbo.entries_offset}/{stock_dtbo.page_size}/{stock_dtbo.version}`; M1 `{m1_dtbo.total_size}/{m1_dtbo.header_size}/{m1_dtbo.entry_size}/{m1_dtbo.entries_offset}/{m1_dtbo.page_size}/{m1_dtbo.version}`.
- D3 selected metadata: Stock entry 21 id/rev/custom `{thyme_entry.image_id}/{thyme_entry.rev}/{thyme_entry.custom}`; M1 entry 0 `{m1_dtbo.entries[0].image_id}/{m1_dtbo.entries[0].rev}/{m1_dtbo.entries[0].custom}`.
- D4 payload: Stock thyme overlay `{thyme_entry.dt_size}` bytes, `{len(stock_fragments)}` fragments, targets `{stock_targets}`, metadata `{stock_special}`; M1 no-op `{m1_dtbo.entries[0].dt_size}` bytes, `{len(m1_fragments)}` fragment, targets `{m1_targets}`, metadata `{m1_special}`, marker `{m1_markers}`.
- D5 payload/layout: Stock selected offset/size `{thyme_entry.dt_offset}/{thyme_entry.dt_size}`; M1 `{m1_dtbo.entries[0].dt_offset}/{m1_dtbo.entries[0].dt_size}`.

D-Control-1 is emitted as `{d_name}`. The 29-entry table, all selector metadata, all offsets, all 28 non-thyme payloads, full partition size, and bytes outside entry 21's slot are exact Stock. The M1 no-op FDT is expanded to the Stock slot size by increasing FDT `totalsize` and zero-filling trailing FDT space. This is a valid fixed-slot FDT and the only unavoidable secondary delta.

D-Control-2 is emitted as `{d2_name}`. M1 one-entry header/table semantics and entry metadata remain M1; only header `total_size`, entry `dt_size`, artifact extent, and payload necessarily change for the exact Stock thyme overlay.
"""
    (args.out_dir / "m5g-factor-decomposition.md").write_text(factors, encoding="utf-8")

    diff_lines = []
    diff_lines.extend(diff_section("V_SINGLE_STOCK_DTB", "exact M1 vendor_boot", v_name,
                                   m1_vendor.data, v_control, "single DTB payload: M1 Mainline -> exact Stock DTB0",
                                   "header dtb_size; artifact length; DTB page padding"))
    diff_lines.extend(diff_section("D_STOCK_TABLE_M1_PAYLOAD", "exact Stock dtbo", d_name,
                                   stock_dtbo.data, d_control, "entry 21 overlay content: Stock thyme -> M1 no-op",
                                   "M1 FDT totalsize expansion and zero padding to exact Stock slot extent"))
    diff_lines.extend(diff_section("D_SINGLE_TABLE_STOCK_PAYLOAD", "exact M1 dtbo", d2_name,
                                   m1_dtbo.data, d2_control, "single entry payload: M1 no-op -> exact Stock thyme overlay",
                                   "header total_size; entry dt_size; artifact length"))
    write_lines(args.out_dir / "binary-diff-map.txt", diff_lines)

    diff_plan = f"""# Candidate control diff plan

## V_SINGLE_STOCK_DTB

- Before: exact M1 vendor_boot `{EXPECTED['m1_vendor'][1]}`.
- After: `{v_name}` `{sha(v_control)}`.
- Intentional variable: single DTB payload becomes exact Stock DTB0 `{sha(stock_base.data)}`.
- Preserved: vendor_boot v3, single-DTB topology, all header bytes except derived `dtb_size`, vendor ramdisk bytes, load addresses, cmdline.
- Unavoidable secondary delta: `dtb_size`, final artifact/page-padding extent.
- Gate: `READY_FOR_M5G_V_SINGLE_STOCK_DTB_CONTROL=YES`.

## D_STOCK_TABLE_M1_PAYLOAD

- Before: exact Stock dtbo `{EXPECTED['stock_dtbo'][1]}`.
- After: `{d_name}` `{sha(d_control)}`.
- Intentional variable: entry 21 payload becomes the M1 no-op overlay content.
- Preserved: 29-entry table byte-for-byte, entry 21 Stock metadata, all offsets, other 28 payloads, bytes outside the selected slot, full partition extent.
- Unavoidable secondary delta: no-op FDT `totalsize` and zero trailing FDT space fill the fixed `{thyme_entry.dt_size}`-byte slot.
- `FIXED_SLOT_REPLACEMENT_UNSAFE=NO` after `dtc` and `fdtoverlay` validation.
- Gate: `READY_FOR_M5G_D_STOCK_TABLE_M1_PAYLOAD_CONTROL=YES`.

## D_SINGLE_TABLE_STOCK_PAYLOAD

- Before: exact M1 dtbo `{EXPECTED['m1_dtbo'][1]}`.
- After: `{d2_name}` `{sha(d2_control)}`.
- Preserved: one-entry topology, header format fields, entries offset, page size, version, id/rev/custom, payload offset.
- Unavoidable secondary delta: table `total_size`, entry `dt_size`, artifact extent.

Exact byte ranges are in `binary-diff-map.txt`.
"""
    (args.out_dir / "candidate-control-diff-plan.md").write_text(diff_plan, encoding="utf-8")

    gates = [
        "MEM0_READ_BEFORE_M5G=YES", "LOCAL_BUILD=NO", "LOCAL_VALIDATION=NO", "GHA_ONLY=YES",
        "DEVICE_OPERATION=NO", "SLOT_A_WRITTEN=NO", "THYME_RELEVANT_STOCK_BASE_DTB_INDEX=0",
        "VENDOR_BOOT_BASE_DTB_SELECTION_AMBIGUOUS=NO", "STOCK_VENDOR_BOOT_DTB_COUNT=4",
        "M1_VENDOR_BOOT_DTB_COUNT=1", "STOCK_DTBO_ENTRY_COUNT=29", "THYME_STOCK_DTBO_ENTRY_INDEX=21",
        "M1_DTBO_ENTRY_COUNT=1", "FIXED_SLOT_REPLACEMENT_UNSAFE=NO",
        "READY_FOR_M5G_V_SINGLE_STOCK_DTB_CONTROL=YES",
        "READY_FOR_M5G_D_STOCK_TABLE_M1_PAYLOAD_CONTROL=YES",
        "NEXT_TRUE_DEVICE_CONTROL=V_SINGLE_STOCK_DTB", "NO_DEVICE_OPERATION=YES", "WAIT_FOR_USER_APPROVAL=YES",
    ]
    write_lines(args.out_dir / "m5g-gates.txt", gates)

    sums = []
    for path in sorted(args.out_dir.iterdir()):
        if path.name != "SHA256SUMS" and path.is_file():
            sums.append(f"{sha(path.read_bytes())}  {path.name}")
    write_lines(args.out_dir / "SHA256SUMS", sums)
    print("\n".join(gates))
    print(f"V_CONTROL_SHA256={sha(v_control)}")
    print(f"D_CONTROL_SHA256={sha(d_control)}")
    print(f"D2_CONTROL_SHA256={sha(d2_control)}")


if __name__ == "__main__":
    main()
