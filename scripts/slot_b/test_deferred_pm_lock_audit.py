"""Actions-only negative tests for the post-PM-lock 60-byte suffix."""
import copy
import os
import struct
import unittest
from unittest.mock import patch

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_lock_audit as d

HAS_SOURCE = all((d.cp.pb.LINUX / name).is_file() for name in d.SOURCE_FILES)
if os.environ.get("PM_LOCK_SOURCE_REQUIRED") == "true" and not HAS_SOURCE:
    raise RuntimeError("PINNED_PM_LOCK_SOURCE_REQUIRED")


def flip(data, offset):
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]


class BoundaryTests(unittest.TestCase):
    def test_only_60_byte_suffix_ending_at_exact_parent_end_is_accepted(self):
        d.gate_geometry()
        with self.assertRaisesRegex(ValueError, "56B_LEAVES_LIVE_BACKEDGE"):
            d.gate_geometry(d.OFFSET, 56, d.END - 4)
        for offset, window, end in ((d.OFFSET - 4, 64, d.END), (d.OFFSET + 4, 60, d.END + 4),
                                    (d.OFFSET, 64, d.END + 4), (d.OFFSET, 60, d.END - 4),
                                    (d.OFFSET, 60.0, d.END), (d.OFFSET, True, d.END)):
            with self.subTest(offset=offset, window=window, end=end), self.assertRaises(ValueError):
                d.gate_geometry(offset, window, end)
        self.assertEqual((d.PREFIX_SIZE, d.CORE_SIZE, d.PADDING_SIZE), (40, 56, 4))

    def test_full_parent_and_worker_copies_are_exact_including_preserved_prefix(self):
        d.gate_parent(*([d.pm.ORIGINAL] * 3))
        for gate, original in ((d.gate_parent, d.pm.ORIGINAL),
                               (d.prior.gate_parent_agreement, d.prior.ORIGINAL)):
            for offset in range(len(original)):
                mutant = flip(original, offset)
                for index in range(3):
                    copies = [original] * 3
                    copies[index] = mutant
                    with self.subTest(size=len(original), offset=offset, copy=index), self.assertRaises(ValueError):
                        gate(*copies)
                with self.subTest(common_drift=offset, size=len(original)), self.assertRaises(ValueError):
                    gate(*([mutant] * 3))
        for data in (d.pm.ORIGINAL[:-4], d.pm.ORIGINAL + bytes(4), bytes(100)):
            with self.assertRaises(ValueError):
                d.gate_parent(data, data, data)

    def test_original_call_opcodes_and_both_symbol_tables_are_bound(self):
        symbols = "\n".join(f"{d.TEXT + call['target']:016x} T {name}" for name, call in d.CALLS.items()) + "\n"
        d.gate_calls(d.pm.ORIGINAL, symbols, symbols)
        for call in d.CALLS.values():
            mutant = flip(d.pm.ORIGINAL, call["offset"] - d.PARENT)
            with self.assertRaises(ValueError):
                d.gate_calls(mutant, symbols, symbols)
            wrong = symbols.replace(f"{d.TEXT + call['target']:016x}", f"{d.TEXT + call['target'] + 4:016x}")
            for nm, sysmap in ((wrong, symbols), (symbols, wrong), (wrong, wrong)):
                with self.assertRaisesRegex(ValueError, "CALL_TARGET_DRIFT"):
                    d.gate_calls(d.pm.ORIGINAL, nm, sysmap)
        self.assertEqual(d.CALLS["device_pm_lock"]["offset"] + 4, d.OFFSET)

    def image(self):
        data = bytearray(d.pm.CALL + 8)
        data[d.PARENT:d.END] = d.pm.ORIGINAL
        struct.pack_into("<I", data, d.pm.CALL, 0x97FFD7EC)
        return data, [(d.PARENT, d.END), (d.pm.CALL, d.pm.CALL + 8)]

    def test_real_original_backedge_rejects_naive_window_but_not_full_suffix(self):
        data, ranges = self.image()
        report = d.gate_incoming(data, ranges)
        self.assertEqual(report["rejected_56b_incoming"], [[d.TEXT + d.BACKEDGE, d.TEXT + d.BACKEDGE_TARGET]])
        self.assertEqual(report["incoming_suffix"], [])
        self.assertEqual(report["incoming_preserved_prefix"], [])

    def test_external_entry_to_any_suffix_or_prefix_word_is_rejected(self):
        original, ranges = self.image()
        source = d.pm.CALL + 4
        for target in range(d.PARENT + 4, d.END, 4):
            data = bytearray(original)
            struct.pack_into("<I", data, source, 0x14000000 | (((target - source) // 4) & 0x3FFFFFF))
            with self.subTest(target=hex(target)), self.assertRaises(ValueError):
                d.gate_incoming(data, ranges)

    def test_backedge_removal_or_retargeting_cannot_self_authorize_new_geometry(self):
        original, ranges = self.image()
        for word in (0xD503201F, 0x17FFFFF6, 0x17FFFFF8):
            data = bytearray(original)
            struct.pack_into("<I", data, d.BACKEDGE, word)
            with self.assertRaisesRegex(ValueError, "NAIVE_BACKEDGE_IDENTITY"):
                d.gate_incoming(data, ranges)
        edge = [(d.TEXT + d.BACKEDGE, d.TEXT + d.BACKEDGE_TARGET)]
        for naive, suffix, prefix in (([], [], []), (edge * 2, [], []),
                                      (edge, edge, []), (edge, [], edge)):
            with self.assertRaises(ValueError):
                d.gate_incoming_records(naive, suffix, prefix)

    def test_prospective_layout_is_terminal_and_not_an_assembled_candidate(self):
        layout = d.prospective_terminal_layout()
        self.assertEqual(layout["padding_offset"] + layout["padding_size"], d.END)
        self.assertEqual(layout["padding_word"], 0xD503201F)
        self.assertEqual(layout["original_stack_frame_bytes"], 32)
        for key in ("padding_reachable", "terminal_fallthrough", "new_stack_frame", "actual_new_probe_assembled"):
            self.assertIs(layout[key], False)
        self.assertTrue(layout["prospective_layout_only"])
        self.assertTrue(layout["original_frame_left_outstanding_at_terminal"])
        for offset in range(56):
            with patch.object(d.pm, "CORE", flip(d.pm.CORE, offset)), self.assertRaises(ValueError):
                d.prospective_terminal_layout()
        self.assertEqual(d.POSITIVE_LIMIT,
                         ["original_device_links_read_lock_returned", "original_device_pm_lock_returned"])
        for limit in ("persistent_lock_state", "valid_srcu_index", "pm_list_movement", "pm_tail_return",
                      "bus_or_driver_probe", "device_identity", "culprit", "init", "usb"):
            self.assertIn(limit, d.NOT_PROVEN)

    def test_fresh_complete_linked_report_cannot_be_replaced_by_stale_or_partial_metadata(self):
        commit, run = "a" * 40, "12345"
        report = {**copy.deepcopy(d.pm.LINKED_IDENTITY), "source_commit": commit, "public_run": run}
        d.pm.gate_linked_report(report, commit, run)
        for candidate in (d.pm.LINKED_REFERENCE_REPORT, None, {}, d.prior.RUNTIME_TABLES,
                          {**report, "protected": report["protected"][:1]}, {**report, "entries": 1064},
                          {**report, "source_sha256": "0" * 64}, {**report, "extra": True}):
            with self.assertRaises(ValueError):
                d.pm.gate_linked_report(candidate, commit, run)

    def test_full_function_relocation_and_exception_destinations_remain_protected(self):
        table = d.TEXT + 0x1B0F690
        for parent, size in ((d.PARENT, d.PARENT_SIZE), (d.prior.PARENT, d.prior.PARENT_SIZE)):
            lo, hi = d.TEXT + parent, d.TEXT + parent + size
            for site in (lo - 7, lo - 1, lo, hi - 8, hi - 1):
                with self.subTest(relocation=site), self.assertRaises(SystemExit):
                    d.cp.t3.gate_window_relocation_scan(lo - 7, size + 7, [site])
            for target in (lo, lo + 4, hi - 4):
                for fault, fixup in ((target, hi), (lo - 4, target)):
                    record = struct.pack("<iiHH", fault - table, fixup - table - 4, 2, 0)
                    with self.subTest(fault=fault, fixup=fixup), self.assertRaises(ValueError):
                        d.prior.gate_exception_destinations(record, table, (lo, hi))


@unittest.skipUnless(HAS_SOURCE, "pinned Linux source unavailable")
class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = (d.cp.pb.LINUX / "drivers/base/core.c").read_text()
        cls.power = (d.cp.pb.LINUX / d.POWER_SOURCE).read_text()

    def test_original_srcu_and_mutex_wrappers(self):
        d.gate_lock_sources(self.core, self.power)
        self.assertEqual(set(d.SOURCE_FILES), set(d.pm.SOURCE_FILES) | {d.POWER_SOURCE})

    def test_srcu_wrapper_cannot_be_replaced_or_referenced_twice(self):
        changed = self.core.replace("return srcu_read_lock(&device_links_srcu);", "return 0;", 1)
        self.assertNotEqual(changed, self.core)
        for source in (changed, self.core + self.core):
            with self.assertRaisesRegex(ValueError, "SRCU_WRAPPER_SOURCE"):
                d.gate_lock_sources(source, self.power)

    def test_mutex_lock_and_unlock_must_keep_the_original_object_and_order(self):
        for original, replacement in (("mutex_lock(&dpm_list_mtx);", "mutex_unlock(&dpm_list_mtx);"),
                                       ("mutex_unlock(&dpm_list_mtx);", "mutex_unlock(&other);")):
            changed = self.power.replace(original, replacement, 1)
            self.assertNotEqual(changed, self.power)
            with self.assertRaisesRegex(ValueError, "SOURCE_DRIFT"):
                d.gate_lock_sources(self.core, changed)


if __name__ == "__main__":
    unittest.main()
