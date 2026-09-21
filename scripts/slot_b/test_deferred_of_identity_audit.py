#!/usr/bin/env python3
"""CI-only synthetic evidence rejection tests; fixture offsets are not kernel ABI."""
import os
import struct
import unittest

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_of_identity_audit as audit


def synthetic_struct(name, start, members, size=64):
    lines = [f"0x{start:08x}: DW_TAG_structure_type",
             f'              DW_AT_name [DW_FORM_strp] ("{name}")',
             f"              DW_AT_byte_size [DW_FORM_data2] (0x{size:04x})"]
    for index, (member, offset, label) in enumerate(members, 1):
        lines += [f"0x{start + index * 16:08x}:   DW_TAG_member",
                  f'                DW_AT_name [DW_FORM_strp] ("{member}")',
                  f'                DW_AT_type [DW_FORM_ref4] (0x{start + 4096:08x} "{label}")',
                  f"                DW_AT_data_member_location [DW_FORM_data2] (0x{offset:04x})"]
    lines.append(f"0x{start + (len(members) + 1) * 16:08x}:   NULL")
    return "\n".join(lines) + "\n"


DEVICE_MEMBERS = [("parent", 0, "device *"), ("of_node", 32, "device_node *")]
NODE_MEMBERS = [("phandle", 4, "phandle"), ("full_name", 16, "const char *")]
DEVICE = synthetic_struct("device", 0x100, DEVICE_MEMBERS)
NODE = synthetic_struct("device_node", 0x200, NODE_MEMBERS)
DECLARATION = ('0x00005000: DW_TAG_structure_type\n'
               '              DW_AT_name [DW_FORM_strp] ("device")\n'
               '              DW_AT_declaration [DW_FORM_flag_present] (true)\n')


def cell(value):
    return struct.pack(">I", value)


def synthetic_fdt(children):
    names = {key: None for _, props in children for key, _ in props}
    strings = b""
    for name in names:
        names[name] = len(strings)
        strings += name.encode() + b"\0"

    def aligned(data):
        return data + bytes((-len(data)) % 4)

    body = cell(1) + bytes(4)
    for name, props in children:
        body += cell(1) + aligned(name.encode() + b"\0")
        for key, value in props:
            body += struct.pack(">III", 3, len(value), names[key]) + aligned(value)
        body += cell(2)
    body += cell(2) + cell(9)
    off_struct, off_strings = 56, 56 + len(body)
    header = struct.pack(">10I", 0xD00DFEED, off_strings + len(strings), off_struct,
                         off_strings, 40, 17, 16, 0, len(strings), len(body))
    return header + bytes(16) + body + strings


class DwarfEvidenceTests(unittest.TestCase):
    def test_actual_member_locations_not_die_addresses(self):
        rows = audit.inspect_layouts(DEVICE + NODE)
        self.assertEqual(rows["device"]["member_offsets"], {"of_node": 32})
        self.assertEqual(rows["device_node"]["member_offsets"], {"phandle": 4, "full_name": 16})
        self.assertEqual(rows["device"]["layout"]["byte_size"], 64)

    def test_identical_layouts_at_distinct_die_offsets(self):
        other = synthetic_struct("device", 0x300, DEVICE_MEMBERS)
        row = audit.inspect_layouts(DEVICE + other + NODE)["device"]
        self.assertEqual(row["status"], "PROVEN")
        self.assertEqual(row["definition_groups"][0]["count"], 2)

    def test_differing_complete_layouts_never_publish_offsets(self):
        alternatives = [
            synthetic_struct("device", 0x300, [("parent", 0, "device *"), ("of_node", 40, "device_node *")]),
            synthetic_struct("device", 0x300, [("parent", 8, "device *"), ("of_node", 32, "device_node *")]),
            synthetic_struct("device", 0x300, [("parent", 0, "device *"), ("of_node", 32, "void *")]),
            synthetic_struct("device", 0x300, DEVICE_MEMBERS, size=80),
        ]
        for other in alternatives:
            with self.subTest(other=other):
                row = audit.inspect_layouts(DEVICE + other + NODE)["device"]
                self.assertEqual(row["reason"], "CONFLICTING_COMPLETE_DEFINITIONS")
                self.assertNotIn("member_offsets", row)
                self.assertNotIn("layout", row)

    def test_forward_declaration_does_not_supply_or_conflict_with_layout(self):
        self.assertEqual(audit.inspect_layouts(DECLARATION + NODE)["device"]["status"], "UNPROVEN")
        row = audit.inspect_layouts(DECLARATION + DEVICE + NODE)["device"]
        self.assertEqual(row["status"], "PROVEN")
        self.assertEqual(row["declarations"], [0x5000])

    def test_missing_member_or_terminator_is_unproven(self):
        for text in (synthetic_struct("device", 0x100, DEVICE_MEMBERS[:1]),
                     DEVICE.replace("0x00000130:   NULL\n", "")):
            with self.subTest(text=text):
                row = audit.inspect_layouts(text + NODE)["device"]
                self.assertEqual(row["status"], "UNPROVEN")
                self.assertNotIn("member_offsets", row)

    def test_nonconstant_and_negative_offsets_are_rejected(self):
        old = "DW_AT_data_member_location [DW_FORM_data2] (0x0020)"
        for replacement in ("DW_AT_data_member_location [DW_FORM_exprloc] (DW_OP_plus_uconst 0x20)",
                            "DW_AT_data_member_location [DW_FORM_exprloc] (32)",
                            "DW_AT_data_member_location [DW_FORM_sdata] (-1)"):
            with self.subTest(replacement=replacement):
                row = audit.inspect_layouts(DEVICE.replace(old, replacement) + NODE)["device"]
                self.assertEqual(row["status"], "UNPROVEN")
                self.assertNotIn("member_offsets", row)

    def test_location_outside_struct_is_rejected(self):
        bad = synthetic_struct("device", 0x100, [("of_node", 64, "device_node *")])
        self.assertEqual(audit.inspect_layouts(bad + NODE)["device"]["status"], "UNPROVEN")

    def test_duplicate_member_and_die_are_rejected(self):
        duplicate_member = synthetic_struct("device", 0x100, DEVICE_MEMBERS + [DEVICE_MEMBERS[-1]])
        for text in (duplicate_member, DEVICE + DEVICE):
            with self.subTest(text=text):
                self.assertEqual(audit.inspect_layouts(text + NODE)["device"]["status"], "UNPROVEN")

    def test_duplicate_attribute_is_not_silently_overwritten(self):
        line = '              DW_AT_name [DW_FORM_strp] ("device")\n'
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ATTRIBUTE"):
            audit.inspect_layouts(DEVICE.replace(line, line + line) + NODE)

    def test_unexpected_recursion_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CHILD_DEPTH"):
            audit.inspect_layouts(DEVICE.replace(":   DW_TAG_member", ":     DW_TAG_member") + NODE)

    def test_unrelated_name_match_cannot_supply_a_struct(self):
        variable = ('fixture:\tfile format elf64-littleaarch64\n'
                    '0x00007000: DW_TAG_variable\n'
                    '              DW_AT_name [DW_FORM_strp] ("device")\n'
                    '              DW_AT_location [DW_FORM_sec_offset] (0x00000011:\n'
                    '                [0x00, 0x08): DW_OP_reg0)\n')
        self.assertEqual(audit.inspect_layouts(variable + NODE)["device"]["status"], "UNPROVEN")
        self.assertEqual(audit.inspect_layouts(variable + DEVICE + NODE)["device"]["status"], "PROVEN")

    def test_unresolved_type_reference_is_unproven(self):
        bad = DEVICE.replace('0x00001100 "device_node *"', '0x00001100')
        self.assertEqual(audit.inspect_layouts(bad + NODE)["device"]["status"], "UNPROVEN")

    def test_missing_dwarf_is_unproven(self):
        rows = audit.inspect_layouts("fixture: file format elf64-littleaarch64\n")
        self.assertTrue(all(row["status"] == "UNPROVEN" for row in rows.values()))


class PhandleEvidenceTests(unittest.TestCase):
    def test_full_u32_big_endian_and_exact_status(self):
        blob = synthetic_fdt([("soc", [("phandle", cell(0x12345678)),
                                        ("compatible", b"vendor,one\0vendor,two\0"),
                                        ("status", b"disabled\0")])])
        result = audit.phandle_map(audit.fdt_nodes(blob))
        row = result["by_phandle"]["0x12345678"]
        self.assertEqual(row["phandle"], 0x12345678)
        self.assertEqual(row["path"], "/soc")
        self.assertEqual(row["compatible"], ["vendor,one", "vendor,two"])
        self.assertEqual(row["status"], "disabled")
        self.assertEqual(result["missing_phandle_nodes"][0]["path"], "/")

    def test_zero_and_missing_are_recorded_without_identity(self):
        nodes = {"/": {}, "/unlabeled": {"phandle": cell(0)}, "/legacy": {"linux,phandle": cell(7)}}
        result = audit.phandle_map(nodes)
        self.assertEqual(set(result["by_phandle"]), {"0x00000007"})
        self.assertEqual(result["zero_phandle_nodes"][0]["path"], "/unlabeled")
        self.assertIsNone(result["missing_phandle_nodes"][0]["status"])

    def test_matching_phandle_aliases_are_one_identity(self):
        result = audit.phandle_map({"/node": {"phandle": cell(9), "linux,phandle": cell(9)}})
        self.assertEqual(result["nonzero_phandle_count"], 1)
        self.assertEqual(result["by_phandle"]["0x00000009"]["phandle_properties"],
                         {"phandle": 9, "linux,phandle": 9})

    def test_invalid_phandle_lengths(self):
        for key in ("phandle", "linux,phandle"):
            for length in (0, 1, 3, 5, 8):
                with self.subTest(key=key, length=length), self.assertRaisesRegex(ValueError, "PHANDLE_LENGTH"):
                    audit.phandle_map({"/node": {key: bytes(length)}})

    def test_conflicting_zero_and_nonzero_aliases(self):
        for first, second in ((1, 2), (0, 2), (2, 0)):
            with self.subTest(first=first, second=second), self.assertRaisesRegex(ValueError, "CONFLICTING_PHANDLES"):
                audit.phandle_map({"/node": {"phandle": cell(first), "linux,phandle": cell(second)}})

    def test_duplicate_across_property_spellings(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PHANDLE"):
            audit.phandle_map({"/one": {"phandle": cell(5)}, "/two": {"linux,phandle": cell(5)}})

    def test_reserved_phandle(self):
        for key in ("phandle", "linux,phandle"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "RESERVED_PHANDLE"):
                audit.phandle_map({"/node": {key: cell(0xFFFFFFFF)}})

    def test_malformed_strings_are_not_replaced_or_normalized(self):
        cases = ({"compatible": b"unterminated"}, {"compatible": b"one\0\0"},
                 {"compatible": b"\xff\0"}, {"status": b"okay\0disabled\0"}, {"status": b""})
        for props in cases:
            with self.subTest(props=props), self.assertRaises((ValueError, UnicodeError)):
                audit.phandle_map({"/node": props})

    def test_duplicate_raw_property_is_not_hidden_by_dictionary_parser(self):
        blob = synthetic_fdt([("node", [("phandle", cell(1)), ("phandle", cell(2))])])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_EMPTY_PROPERTY"):
            audit.fdt_nodes(blob)

    def test_duplicate_raw_node_path(self):
        blob = synthetic_fdt([("node", [("phandle", cell(1))]), ("node", [("phandle", cell(2))])])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_NODE_PATH"):
            audit.fdt_nodes(blob)

    def test_truncated_fdt_and_overlapping_sections(self):
        blob = synthetic_fdt([("node", [("phandle", cell(1))])])
        with self.assertRaisesRegex(ValueError, "HEADER"):
            audit.fdt_nodes(blob[:-1])
        broken = bytearray(blob)
        struct.pack_into(">I", broken, 12, 56)
        with self.assertRaisesRegex(ValueError, "SECTION_BOUNDS"):
            audit.fdt_nodes(bytes(broken))


if __name__ == "__main__":
    unittest.main()
