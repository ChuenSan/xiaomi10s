"""Actions-only negative fixtures for the PM-tail entry feasibility audit."""
import os
import struct
import unittest

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_audit as d

HAS_SOURCE = all((d.cp.pb.LINUX / name).is_file() for name in d.SOURCE_REFERENCES)
if os.environ.get("PM_TAIL_SOURCE_REQUIRED") == "true" and not HAS_SOURCE:
    raise RuntimeError("PINNED_PM_TAIL_SOURCE_REQUIRED")


class EntryTests(unittest.TestCase):
    def test_exact_parent_geometry_and_entry(self):
        original = struct.pack("<I", 0xD503233F) + bytes(56)
        d.gate_parent(original, original, original)
        for size in (0, 4, 56, 61, 4100):
            candidate = (original + bytes(4100))[:size]
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "DOES_NOT_FIT"):
                d.gate_parent(candidate, candidate, candidate)
        candidate = bytes(60)
        with self.assertRaisesRegex(ValueError, "PACIASP"):
            d.gate_parent(candidate, candidate, candidate)

    def test_three_copies_must_match_through_suffix(self):
        original = struct.pack("<I", 0xD503233F) + bytes(124)
        for position in (0, 4, 59, 60, 127):
            candidate = bytearray(original)
            candidate[position] ^= 1
            for index in range(3):
                copies = [original] * 3
                copies[index] = bytes(candidate)
                with self.subTest(position=position, copy=index), self.assertRaisesRegex(ValueError, "DISAGREEMENT"):
                    d.gate_parent(*copies)

    def test_call_must_be_original_bl_not_a_tail_jump(self):
        d.gate_call(0x97FFD7EC)
        for word in (0x17FFD7EC, 0x97FFD7EB, 0x97FFD7ED, 0xD63F0000, 0xD503201F):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, "ORIGINAL_BL"):
                d.gate_call(word)

    def test_caller_and_every_interior_entry_fail_closed(self):
        entry = [(d.TEXT + d.CALL, d.TEXT + d.PARENT)]
        d.gate_incoming_records(entry, [], [])
        for entries in ([], entry * 2, [(d.TEXT + d.CALL + 4, d.TEXT + d.PARENT)],
                        entry + [(d.TEXT + d.PARENT - 4, d.TEXT + d.PARENT)]):
            with self.assertRaisesRegex(ValueError, "SINGLE_WORKER"):
                d.gate_incoming_records(entries, [], [])
        for target in (d.PARENT + 4, d.PARENT + 8, d.PARENT + 56, d.PARENT + 60):
            hit = [(d.TEXT + d.CALL, d.TEXT + target)]
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "EXTERNAL_INTERIOR"):
                d.gate_incoming_records(entry, hit, [])
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "OVERWRITE_WINDOW"):
                d.gate_incoming_records(entry, [], hit)

    def test_full_code_scanner_includes_entry_and_window_start(self):
        image = bytearray(d.CALL + 8)
        struct.pack_into("<I", image, d.CALL, 0x97FFD7EC)
        ranges = [(d.PARENT, len(image))]
        self.assertEqual(d.cp.incoming_inclusive(image, ranges, d.TEXT, d.TEXT + d.PARENT,
                                                 d.TEXT + d.PARENT + 4),
                         [(d.TEXT + d.CALL, d.TEXT + d.PARENT)])
        source, target = d.CALL + 4, d.PARENT + 4
        word = 0x14000000 | (((target - source) // 4) & 0x3FFFFFF)
        struct.pack_into("<I", image, source, word)
        self.assertEqual(d.cp.incoming_inclusive(image, ranges, d.TEXT, d.TEXT + target,
                                                 d.TEXT + target + d.WINDOW),
                         [(d.TEXT + source, d.TEXT + target)])


@unittest.skipUnless(HAS_SOURCE, "pinned Linux source unavailable")
class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (d.cp.pb.LINUX / name).read_text() for name in d.SOURCE_REFERENCES}

    def test_exact_source_order(self):
        d.gate_sources(self.sources, "CONFIG_MODULES=y\n")

    def test_changed_or_address_taken_references_are_rejected(self):
        for path in d.SOURCE_REFERENCES:
            candidate = dict(self.sources)
            candidate[path] += "\nvoid *extra = device_pm_move_to_tail;\n"
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "REFERENCE_COUNT"):
                d.gate_sources(candidate, "CONFIG_MODULES=y\n")
        with self.assertRaisesRegex(ValueError, "REFERENCE_SET"):
            d.gate_sources({**self.sources, "other.c": ""}, "CONFIG_MODULES=y\n")

    def test_wrapper_calls_and_lock_order_cannot_change(self):
        for original, replacement in (("idx = device_links_read_lock();", "idx = 0;"),
                                       ("device_reorder_to_tail(dev, NULL);", "device_pm_unlock();"),
                                       ("device_links_read_unlock(idx);", "device_links_read_unlock(0);")):
            candidate = dict(self.sources)
            candidate["drivers/base/core.c"] = candidate["drivers/base/core.c"].replace(original, replacement, 1)
            self.assertNotEqual(candidate, self.sources)
            with self.subTest(original=original), self.assertRaisesRegex(ValueError, "SOURCE_ORDER"):
                d.gate_sources(candidate, "CONFIG_MODULES=y\n")


if __name__ == "__main__":
    unittest.main()
