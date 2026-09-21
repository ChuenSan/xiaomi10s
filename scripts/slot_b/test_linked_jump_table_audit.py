"""Actions-only folded-section and destination-only jump-label regressions."""
import os
import struct
import unittest

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import linked_jump_table_audit as d


class LinkedJumpTests(unittest.TestCase):
    def test_signed_offsets_use_each_field_address(self):
        base = 0x1000
        records = struct.pack("<iiqiiq", -16, 28, 7, 32, -20, -4)
        self.assertEqual(d.decode(records, base), [
            {"record": 0x1000, "code": 0xFF0, "target": 0x1020},
            {"record": 0x1010, "code": 0x1030, "target": 0x1000},
        ])
        for data, address in ((b"", base), (records[:-1], base), (records, base + 4)):
            with self.assertRaisesRegex(ValueError, "RECORD_SIZE_OR_ALIGNMENT"):
                d.decode(data, address)

    def test_instruction_and_target_inclusive_boundaries_are_independent(self):
        protected = ((0x2000, 0x2064), (0x3000, 0x30C4))
        ranges = [(0x1000, 0x4000)]
        d.gate_entries([{"code": 0x1FFC, "target": 0x2064}], protected, ranges)
        d.gate_entries([{"code": 0x2064, "target": 0x30C4}], protected, ranges)
        for lo, hi in protected:
            for address in (lo, lo + 4, hi - 4):
                with self.subTest(code=address), self.assertRaisesRegex(ValueError, "REWRITES_PROTECTED"):
                    d.gate_entries([{"code": address, "target": 0x1800}], protected, ranges)
                with self.subTest(target=address), self.assertRaisesRegex(ValueError, "TARGETS_PROTECTED"):
                    d.gate_entries([{"code": 0x1800, "target": address}], protected, ranges)
        for record in ({"code": 0x1801, "target": 0x1800}, {"code": 0x1800, "target": 0x1801}):
            with self.assertRaisesRegex(ValueError, "UNALIGNED"):
                d.gate_entries([record], protected, ranges)
        for address in (0xFFC, 0x4000):
            for code, target in ((address, 0x1800), (0x1800, address)):
                with self.assertRaisesRegex(ValueError, "OUTSIDE_CODE"):
                    d.gate_entries([{"code": code, "target": target}], protected, ranges)
        with self.assertRaisesRegex(ValueError, "ENTRIES_EMPTY"):
            d.gate_entries([], protected, ranges)

    def test_folded_table_is_found_without_standalone_section(self):
        symbols = "\n".join(f"{d.TEXT + value:016x} D {name}" for name, value in zip(d.SYMBOLS, (d.START, d.END)))
        section = {"name": ".rodata", "vma": d.TEXT + 0x10F0000,
                   "size": 0x9AB7B8, "alloc": True, "code": False}
        self.assertEqual(d.gate_layout(symbols, symbols, [section]), section)
        for index in (0, 1):
            mutated = symbols.replace(f"{d.TEXT + (d.START, d.END)[index]:016x}",
                                      f"{d.TEXT + (d.START, d.END)[index] + 8:016x}")
            for first, second in ((mutated, symbols), (symbols, mutated), (mutated, mutated)):
                with self.assertRaisesRegex(ValueError, "SYMBOL_BOUNDS"):
                    d.gate_layout(first, second, [section])
        for rows in ([], [section, section]):
            with self.assertRaisesRegex(ValueError, "MAPPING_NOT_UNIQUE"):
                d.gate_layout(symbols, symbols, rows)
        for key, value in (("name", ".data"), ("alloc", False), ("code", True)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "FOLDED_SECTION"):
                d.gate_layout(symbols, symbols, [{**section, key: value}])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SECTION"):
            d.gate_layout(symbols, symbols, [section, {"name": "__jump_table", "vma": 0, "size": 0}])

    def test_complete_three_way_table_bytes_must_agree(self):
        data = bytes(d.END - d.START)
        d.gate_bytes(data, data, data)
        for offset in (0, 4, 8, len(data) - 1):
            changed = data[:offset] + b"\x01" + data[offset + 1:]
            for index in range(3):
                copies = [data] * 3
                copies[index] = changed
                with self.subTest(offset=offset, copy=index), self.assertRaisesRegex(ValueError, "DISAGREEMENT"):
                    d.gate_bytes(*copies)
        for size in (0, len(data) - 16, len(data) + 16):
            with self.assertRaisesRegex(ValueError, "DISAGREEMENT"):
                d.gate_bytes(*([bytes(size)] * 3))


HAS_SOURCE = (d.cp.pb.LINUX / d.SOURCE).is_file()
if os.environ.get("LINKED_JUMP_SOURCE_REQUIRED") == "true" and not HAS_SOURCE:
    raise RuntimeError("PINNED_JUMP_LABEL_SOURCE_REQUIRED")


@unittest.skipUnless(HAS_SOURCE, "pinned Linux source unavailable")
class SourceTests(unittest.TestCase):
    def test_relative_abi_and_dynamic_writer_configuration(self):
        source = (d.cp.pb.LINUX / d.SOURCE).read_text()
        config = "\n".join(["CONFIG_JUMP_LABEL=y", "CONFIG_HAVE_ARCH_JUMP_LABEL=y",
                            "CONFIG_HAVE_ARCH_JUMP_LABEL_RELATIVE=y", "# CONFIG_KPROBES is not set",
                            "# CONFIG_FTRACE is not set", "# CONFIG_CFI_CLANG is not set"])
        d.gate_source(source, config)
        for token, replacement in (("s32 code;", "s64 code;"), ("s32 target;", "s64 target;"),
                                    ("&entry->target + entry->target", "&entry->code + entry->target")):
            changed = source.replace(token, replacement)
            self.assertNotEqual(changed, source)
            with self.assertRaisesRegex(ValueError, "SOURCE_ABI"):
                d.gate_source(changed, config)
        for line in config.splitlines():
            with self.subTest(line=line), self.assertRaises(ValueError):
                d.gate_source(source, config.replace(line, ""))
        for line in ("CONFIG_HAVE_STATIC_CALL=y", "CONFIG_HAVE_STATIC_CALL_INLINE=y"):
            with self.assertRaisesRegex(ValueError, "STATIC_CALL"):
                d.gate_source(source, config + "\n" + line)


if __name__ == "__main__":
    unittest.main()
