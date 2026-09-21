#!/usr/bin/env python3
"""Actions-only DWARF offsets and frozen RT-D node associations; no candidate."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_selected_probe as selected

cp = selected.cp
need = cp.require
TARGETS = {"device": ("of_node",), "device_node": ("phandle", "full_name")}
DEBUG_INFO_SIZE = 0xBA72F25
DWARFDUMP = "llvm-dwarfdump-18"
FIX8_RUN = "34741153230"
CONST_FORMS = {"DW_FORM_data1", "DW_FORM_data2", "DW_FORM_data4", "DW_FORM_data8",
               "DW_FORM_udata", "DW_FORM_sdata", "DW_FORM_implicit_const"}
REF_FORMS = {"DW_FORM_ref1", "DW_FORM_ref2", "DW_FORM_ref4", "DW_FORM_ref8",
             "DW_FORM_ref_udata", "DW_FORM_ref_addr"}
DIE_LINE = re.compile(r"^0x([0-9a-fA-F]+): ( *)(DW_TAG_\w+|NULL)\s*$")
ATTRIBUTE = re.compile(r"^\s+(DW_AT_\w+)\s+\[(DW_FORM_\w+)\]\s+\((.*)\)\s*$")
DOCS = ["https://llvm.org/docs/CommandGuide/llvm-dwarfdump.html",
        "https://llvm.org/docs/CommandGuide/llvm-readelf.html",
        "https://github.com/llvm/llvm-project/blob/llvmorg-18.1.8/llvm/tools/"
        "llvm-dwarfdump/llvm-dwarfdump.cpp",
        "https://github.com/llvm/llvm-project/blob/llvmorg-18.1.8/llvm/lib/"
        "DebugInfo/DWARF/DWARFDie.cpp"]
LIMITATIONS = [
    "Compiler offsets and FDT node associations are feasibility evidence only.",
    "Member value widths and actual pointer reads are not qualified by this audit.",
    "dev->of_node may be NULL, shared or reassigned; a phandle is not a unique Linux device.",
    "A valid DT node can have no phandle or a zero phandle.",
    "FDT paths are not observations of a runtime device_node.full_name pointer.",
    "Future pointer-lifetime, channel-separation and cross-boot-coherence proofs are required.",
    "No device identity, culprit, driver probe, init or usable Linux is established here.",
]


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def number(attrs, key):
    need(key in attrs, f"DWARF_ATTRIBUTE_MISSING:{key}")
    form, value = attrs[key]
    need(form in CONST_FORMS and re.fullmatch(r"0x[0-9a-fA-F]+|[0-9]+", value),
         f"DWARF_NONCONSTANT_OR_NEGATIVE:{key}")
    return int(value, 16 if value.startswith("0x") else 10)


def string(attrs, key):
    need(key in attrs, f"DWARF_ATTRIBUTE_MISSING:{key}")
    value = json.loads(attrs[key][1])
    need(isinstance(value, str), f"DWARF_STRING_REQUIRED:{key}")
    return value


def reference(attrs):
    need("DW_AT_type" in attrs, "DWARF_MEMBER_TYPE_MISSING")
    form, value = attrs["DW_AT_type"]
    match = re.fullmatch(r'(0x[0-9a-fA-F]+) ("(?:[^"\\]|\\.)*")', value)
    need(form in REF_FORMS and match is not None, "DWARF_TYPE_REFERENCE_UNRESOLVED")
    label = json.loads(match[2])
    need(bool(label), "DWARF_TYPE_LABEL_EMPTY")
    return {"die_offset": int(match[1], 16), "label": label}


def dwarf_roots(dump):
    """Read LLVM18 --name/--show-form output with exactly one child level."""
    roots, root, current = [], None, None
    for line in dump.splitlines():
        match = DIE_LINE.fullmatch(line)
        if match:
            depth = len(match[2])
            need(depth in (0, 2), "DWARF_UNEXPECTED_CHILD_DEPTH")
            if depth == 0:
                root = {"die_offset": int(match[1], 16), "tag": match[3],
                        "attrs": {}, "children": [], "closed": False}
                roots.append(root)
                current = root
            elif root is not None:
                need(not root["closed"], "DWARF_CHILD_AFTER_TERMINATOR")
                if match[3] == "NULL":
                    root["closed"] = True
                    current = None
                else:
                    current = {"die_offset": int(match[1], 16), "tag": match[3], "attrs": {}}
                    root["children"].append(current)
            else:
                raise ValueError("DWARF_ORPHAN_CHILD")
            continue
        if not line.strip() or re.fullmatch(r".+:\s+file format \S+", line):
            continue
        if root is not None and root["tag"] != "DW_TAG_structure_type":
            continue
        match = ATTRIBUTE.fullmatch(line)
        need(match is not None and current is not None, "DWARF_UNPARSED_LINE")
        need(match[1] not in current["attrs"], f"DWARF_DUPLICATE_ATTRIBUTE:{match[1]}")
        current["attrs"][match[1]] = (match[2], match[3])
    return roots


def is_declaration(attrs):
    if "DW_AT_declaration" not in attrs:
        return False
    form, value = attrs["DW_AT_declaration"]
    need(form in ("DW_FORM_flag", "DW_FORM_flag_present") and
         value in ("true", "false", "0x01", "0x00"), "DWARF_DECLARATION_FLAG_INVALID")
    return value in ("true", "0x01")


def direct_layout(root, name):
    attrs = root["attrs"]
    need(not {"DW_AT_specification", "DW_AT_abstract_origin", "DW_AT_signature"} & attrs.keys(),
         "DWARF_INDIRECT_DEFINITION_UNSUPPORTED")
    size = number(attrs, "DW_AT_byte_size")
    need(size > 0 and root["closed"], "DWARF_INCOMPLETE_DEFINITION")
    members, names, evidence = [], set(), {}
    for child in root["children"]:
        if child["tag"] != "DW_TAG_member":
            need(child["tag"] in ("DW_TAG_structure_type", "DW_TAG_union_type",
                                  "DW_TAG_enumeration_type"), "DWARF_UNSUPPORTED_STRUCT_CHILD")
            continue
        attrs = child["attrs"]
        need(not {"DW_AT_specification", "DW_AT_abstract_origin", "DW_AT_declaration"} & attrs.keys(),
             "DWARF_INDIRECT_MEMBER_UNSUPPORTED")
        member_name = string(attrs, "DW_AT_name") if "DW_AT_name" in attrs else None
        if member_name is not None:
            need(member_name not in names, "DWARF_DUPLICATE_MEMBER")
            names.add(member_name)
        member_type = reference(attrs)
        member = {"name": member_name, "type_label": member_type["label"]}
        for key in ("DW_AT_data_member_location", "DW_AT_data_bit_offset", "DW_AT_bit_offset",
                    "DW_AT_bit_size", "DW_AT_byte_size", "DW_AT_alignment"):
            if key in attrs:
                member[key.removeprefix("DW_AT_")] = number(attrs, key)
        if "bit_size" in member:
            need(member["bit_size"] > 0 and
                 ("data_bit_offset" in member or
                  {"data_member_location", "bit_offset"} <= member.keys()),
                 "DWARF_BITFIELD_LOCATION_INCOMPLETE")
            if "data_bit_offset" in member:
                need(member["data_bit_offset"] + member["bit_size"] <= size * 8,
                     "DWARF_BITFIELD_OUTSIDE_STRUCT")
        else:
            need("data_member_location" in member and
                 not {"bit_offset", "data_bit_offset"} & member.keys(),
                 "DWARF_MEMBER_LOCATION_INCOMPLETE")
        if "data_member_location" in member:
            need(member["data_member_location"] < size, "DWARF_MEMBER_OUTSIDE_STRUCT")
        if member_name in TARGETS[name]:
            need("bit_size" not in member, "DWARF_TARGET_IS_BITFIELD")
            evidence[member_name] = {"member_die_offset": child["die_offset"],
                                     "type_die_offset": member_type["die_offset"]}
        members.append(member)
    need(set(TARGETS[name]) <= names, "DWARF_TARGET_MEMBER_MISSING")
    layout = {"byte_size": size, "direct_members": members}
    if "DW_AT_alignment" in root["attrs"]:
        layout["alignment"] = number(root["attrs"], "DW_AT_alignment")
    origin = {"struct_die_offset": root["die_offset"], "members": evidence}
    if "DW_AT_decl_file" in root["attrs"]:
        origin["decl_file"] = string(root["attrs"], "DW_AT_decl_file")
    if "DW_AT_decl_line" in root["attrs"]:
        origin["decl_line"] = number(root["attrs"], "DW_AT_decl_line")
    return layout, origin


def inspect_layouts(dump):
    roots = dwarf_roots(dump)
    result = {}
    for name, required in TARGETS.items():
        definitions, declarations, rejected, seen = {}, [], [], set()
        for root in roots:
            if root["tag"] != "DW_TAG_structure_type" or string(root["attrs"], "DW_AT_name") != name:
                continue
            offset = root["die_offset"]
            if offset in seen:
                rejected.append({"die_offset": offset, "reason": "DWARF_DUPLICATE_DIE_OFFSET"})
                continue
            seen.add(offset)
            try:
                if is_declaration(root["attrs"]):
                    need(not root["children"] and "DW_AT_byte_size" not in root["attrs"],
                         "DWARF_CONFLICTING_DECLARATION")
                    declarations.append(offset)
                    continue
                layout, origin = direct_layout(root, name)
                signature = cp.digest(selected.canonical(layout))
                group = definitions.setdefault(signature, {"layout": layout, "origins": []})
                group["origins"].append(origin)
            except (ValueError, TypeError) as error:
                rejected.append({"die_offset": offset, "reason": str(error)})
        row = {"status": "UNPROVEN", "declarations": declarations,
               "rejected_definitions": rejected,
               "definition_groups": [{"sha256": key, "count": len(value["origins"])}
                                     for key, value in definitions.items()]}
        if len(definitions) == 1 and not rejected:
            group = next(iter(definitions.values()))
            row.update(status="PROVEN", layout=group["layout"], origins=group["origins"],
                       member_offsets={member["name"]: member["data_member_location"]
                                       for member in group["layout"]["direct_members"]
                                       if member["name"] in required})
        else:
            row["reason"] = ("CONFLICTING_COMPLETE_DEFINITIONS" if len(definitions) > 1 else
                             "INCOMPLETE_OR_REJECTED_DEFINITIONS" if rejected else
                             "NO_COMPLETE_DEFINITION")
        result[name] = row
    return result


def fdt_nodes(blob):
    """Reject duplicate paths/properties before the existing parser builds dictionaries."""
    need(len(blob) >= 40, "FDT_SHORT_HEADER")
    magic, total, off_struct, off_strings, _, version, _, _, strings_size, struct_size = \
        struct.unpack_from(">10I", blob)
    need(magic == cp.rt.FDT_MAGIC and total == len(blob) and version >= 17,
         "FDT_HEADER_UNSUPPORTED")
    need(40 <= off_struct < off_struct + struct_size <= off_strings and
         off_strings + strings_size <= total and off_struct % 4 == 0, "FDT_SECTION_BOUNDS")
    body, strings = blob[off_struct:off_struct + struct_size], blob[off_strings:off_strings + strings_size]
    stack, properties, cursor = [], {}, 0
    while cursor + 4 <= len(body):
        token = struct.unpack_from(">I", body, cursor)[0]
        cursor += 4
        if token == cp.rt.FDT_BEGIN_NODE:
            end = body.find(b"\0", cursor)
            need(end >= cursor, "FDT_NODE_NAME_UNTERMINATED")
            name = body[cursor:end].decode("ascii")
            need("/" not in name and (bool(name) if stack else name == "" and not properties),
                 "FDT_NODE_NAME_INVALID")
            stack.append(name)
            path = "/" + "/".join(stack[1:])
            need(path not in properties, "FDT_DUPLICATE_NODE_PATH")
            properties[path] = set()
            cursor = (end + 4) & ~3
        elif token == cp.rt.FDT_PROP:
            need(stack and cursor + 8 <= len(body), "FDT_PROPERTY_OUTSIDE_NODE")
            length, nameoff = struct.unpack_from(">II", body, cursor)
            cursor += 8
            end = strings.find(b"\0", nameoff)
            need(end >= nameoff and cursor + length <= len(body), "FDT_PROPERTY_BOUNDS")
            name = strings[nameoff:end].decode("ascii")
            path = "/" + "/".join(stack[1:])
            need(name and name not in properties[path], "FDT_DUPLICATE_OR_EMPTY_PROPERTY")
            properties[path].add(name)
            cursor = (cursor + length + 3) & ~3
        elif token == cp.rt.FDT_END_NODE:
            need(bool(stack), "FDT_UNBALANCED_END_NODE")
            stack.pop()
        elif token == cp.rt.FDT_NOP:
            continue
        elif token == cp.rt.FDT_END:
            need(not stack and "/" in properties and not any(body[cursor:]), "FDT_INCOMPLETE_TREE")
            nodes = cp.rt.parse_fdt(blob)
            need(set(nodes) == set(properties) and
                 all(set(nodes[path]) == names for path, names in properties.items()),
                 "FDT_PARSER_DISAGREEMENT")
            return nodes
        else:
            raise ValueError("FDT_UNKNOWN_TOKEN")
    raise ValueError("FDT_END_MISSING")


def property_strings(props, key):
    if key not in props:
        return None
    raw = props[key]
    need(bool(raw) and raw.endswith(b"\0"), f"FDT_STRING_TERMINATOR:{key}")
    parts = raw[:-1].split(b"\0")
    need(all(parts), f"FDT_EMPTY_STRING:{key}")
    return [part.decode("ascii") for part in parts]


def phandle_map(nodes):
    by_handle, missing, zero = {}, [], []
    for path, props in sorted(nodes.items()):
        status = property_strings(props, "status")
        need(status is None or len(status) == 1, f"FDT_STATUS_LENGTH:{path}")
        row = {"path": path, "compatible": property_strings(props, "compatible"),
               "status": status[0] if status is not None else None}
        handles = {}
        for key in ("phandle", "linux,phandle"):
            if key in props:
                need(len(props[key]) == 4, f"FDT_PHANDLE_LENGTH:{path}:{key}")
                handles[key] = struct.unpack(">I", props[key])[0]
        if not handles:
            missing.append(row)
            continue
        need(len(set(handles.values())) == 1, f"FDT_CONFLICTING_PHANDLES:{path}")
        value = next(iter(handles.values()))
        need(value != 0xFFFFFFFF, f"FDT_RESERVED_PHANDLE:{path}")
        row["phandle_properties"] = handles
        if value == 0:
            zero.append(row)
            continue
        need(value not in by_handle, f"FDT_DUPLICATE_PHANDLE:{value:#010x}")
        by_handle[value] = {"phandle": value, **row}
    return {"by_phandle": {f"0x{key:08x}": by_handle[key] for key in sorted(by_handle)},
            "missing_phandle_nodes": missing, "zero_phandle_nodes": zero,
            "node_count": len(nodes), "nonzero_phandle_count": len(by_handle),
            "identity_semantics": "DT_NODE_ASSOCIATION_ONLY"}


def command_text(out, label, argv, commands):
    stdout, stderr = out / f"{label}.stdout.txt", out / f"{label}.stderr.txt"
    receipt = {"argv": argv, "stdout": stdout.name, "stderr": stderr.name,
               "timeout_seconds": 300, "returncode": None}
    commands.append(receipt)
    with stdout.open("xb") as output, stderr.open("xb") as errors:
        try:
            proc = subprocess.run(argv, stdout=output, stderr=errors, check=False, timeout=300,
                                  env={**os.environ, "LC_ALL": "C"})
            receipt["returncode"] = proc.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            receipt["error"] = str(error)
    receipt["stdout_bytes"], receipt["stderr_bytes"] = stdout.stat().st_size, stderr.stat().st_size
    save(out / f"{label}.command.json", receipt)
    need(receipt["returncode"] == 0, f"DWARF_COMMAND_FAILED:{label}")
    need(receipt["stderr_bytes"] == 0, f"DWARF_COMMAND_DIAGNOSTICS:{label}")
    need(receipt["stdout_bytes"] <= 128 * 1024 * 1024, f"DWARF_DUMP_SIZE_LIMIT:{label}")
    return stdout.read_text()


def audit_dwarf(out, elf):
    report = {"status": "UNPROVEN", "commands": [], "documentation": DOCS,
              "layout_scope": "ALL_NAMED_DEFINITIONS_AND_DIRECT_MEMBERS_ONLY",
              "member_value_widths": "UNPROVEN_NOT_EXTRACTED"}
    try:
        version = command_text(out, "dwarfdump-version", [DWARFDUMP, "--version"], report["commands"])
        need(re.search(r"\bversion 18\.", version) is not None, "LLVM_VERSION_DRIFT")
        help_text = command_text(out, "dwarfdump-help", [DWARFDUMP, "--help"], report["commands"])
        for option in ("--name", "--show-children", "--recurse-depth", "--show-form"):
            need(option in help_text, f"DWARF_REQUIRED_OPTION_UNAVAILABLE:{option}")
        raw = command_text(out, "elf-sections", ["llvm-readelf-18", "-S", "--wide", str(elf)],
                           report["commands"])
        sections = cp.t3._readelf_sections(raw)
        names = [section["name"] for section in sections]
        need(len(names) == len(set(names)), "DWARF_DUPLICATE_SECTION_NAME")
        report["debug_sections"] = [section for section in sections if "debug" in section["name"]]
        need({".debug_info", ".debug_abbrev"} <= set(names), "DWARF_REQUIRED_SECTION_MISSING")
        need(next(section["size"] for section in sections if section["name"] == ".debug_info") ==
             DEBUG_INFO_SIZE, "DWARF_DEBUG_INFO_SIZE_DRIFT")
        need(not any(name.startswith((".debug_types", ".zdebug")) or name.endswith(".dwo")
                     for name in names), "DWARF_ALTERNATE_DIE_NAMESPACE_UNSUPPORTED")
        raw = command_text(out, "named-types", [DWARFDUMP, "--name=device", "--name=device_node",
                           "--show-children", "--recurse-depth=1", "--show-form", str(elf)],
                           report["commands"])
        report["types"] = inspect_layouts(raw)
        if all(row["status"] == "PROVEN" for row in report["types"].values()):
            report["status"] = "PROVEN"
        else:
            report["reason"] = "REQUIRED_COMPILER_LAYOUT_UNPROVEN"
    except (ValueError, TypeError, OSError, UnicodeError) as error:
        report["reason"] = str(error)
    return report


def audit(args):
    selected.gate_actions()
    selected.gate_authority(os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"])
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"status": "UNPROVEN", "candidate_generated": False, "device_operation": False,
              "kernel_rebuild": False, "added_pointer_reads": 0, "identity_channel_qualified": False,
              "source_commit": os.environ["GITHUB_SHA"], "public_run": os.environ["GITHUB_RUN_ID"],
              "limitations": LIMITATIONS}
    result = 0
    try:
        metadata = json.loads((args.bundle / "bundle.json").read_text())
        files = {name: (args.bundle / name).read_bytes() for name in selected.BUNDLE_FILES}
        selected.gate_bundle(metadata, files)
        frozen = args.frozen.read_bytes()
        need(len(frozen) == cp.t3.FIX8_PAYLOAD_SIZE and cp.digest(frozen) == cp.t3.FIX8_PAYLOAD_SHA,
             "FIX8_PAYLOAD_IDENTITY_DRIFT")
        image_size = cp.pb.parse_image_hdr(frozen, "FIX8")["image_size"]
        offset, _ = cp.pb.calc_dtb_offset(image_size)
        need(offset == cp.t3.DTB_OFFSET and len(frozen) - offset == cp.pb.RT_D_SIZE,
             "RT_D_TRAILER_GEOMETRY_DRIFT")
        rt_d = frozen[offset:]
        cp.pb.gate_rt_d(rt_d)
        report["inputs"] = {"repository": selected.PUBLIC_REPOSITORY, "bundle_run": selected.BUNDLE_RUN,
                            "bundle_artifact": "thyme-slot-b-kernel-audit-bundle", "bundle": metadata,
                            "fix8_run": FIX8_RUN, "fix8_artifact": "thyme-r3-p1b-fix8-fix24",
                            "fix8_payload_sha256": cp.t3.FIX8_PAYLOAD_SHA, "fix8_payload_size": len(frozen),
                            "rt_d_offset": offset, "rt_d_size": len(rt_d), "rt_d_sha256": cp.pb.RT_D_SHA}
        config = files["kernel.config"].decode().splitlines()
        report["config_evidence"] = [line for line in config if re.match(
            r"(?:# )?CONFIG_(?:OF(?:_DYNAMIC|_OVERLAY)?|DEBUG_INFO(?:_\w+)?)(?:=| )", line)]
        (args.out / "kernel.config").write_bytes(files["kernel.config"])
        mapping = phandle_map(fdt_nodes(rt_d))
        save(args.out / "rt-d-phandles.json", mapping)
        report["rt_d"] = {"status": "PROVEN", "map": "rt-d-phandles.json",
                          "node_count": mapping["node_count"],
                          "nonzero_phandle_count": mapping["nonzero_phandle_count"],
                          "missing_phandle_count": len(mapping["missing_phandle_nodes"]),
                          "zero_phandle_count": len(mapping["zero_phandle_nodes"])}
        report["dwarf"] = audit_dwarf(args.out, args.bundle / "vmlinux")
        if report["dwarf"]["status"] == "PROVEN":
            report["status"] = "COMPILER_OFFSETS_AND_RT_D_MAP_PROVEN"
    except (ValueError, TypeError, OSError, UnicodeError, SystemExit, struct.error) as error:
        report.update(status="REJECTED", error=str(error))
        result = 1
    save(args.out / "report.json", report)
    print(json.dumps({key: report[key] for key in ("status", "candidate_generated", "device_operation",
                                                  "identity_channel_qualified")}, indent=2))
    if "error" in report:
        print(report["error"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return audit(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
