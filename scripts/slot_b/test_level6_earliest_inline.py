"""Negative fixtures and selection invariants for the level-6 earliest inline target."""
from __future__ import annotations

import os
import struct
import unittest

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import checkpoint

ENTRY_BASE_VA = 0xFFFF800081D0B1A8
TEXT_VA = 0xFFFF800080000000
NOP = 0xD503201F
RET = 0xD65F03C0
PACIASP = 0xD503233F


def span_entry(index, target_va, symbol="device_fn"):
    return {"index": index, "entry_va": ENTRY_BASE_VA + 4 * index,
            "entry_va_hex": hex(ENTRY_BASE_VA + 4 * index), "entry_word": "0x0",
            "relative": 0, "target_va": target_va, "target_va_hex": hex(target_va),
            "aliases": [symbol], "symbol": symbol}


def image_with(function_offset, function_size, branches):
    image = bytearray(struct.pack("<I", NOP) * (function_size + function_offset + 0x1000))
    struct.pack_into("<I", image, function_offset, PACIASP)
    struct.pack_into("<I", image, function_offset + function_size - 4, RET)
    for pc_offset, target_va in branches:
        pc = TEXT_VA + pc_offset
        struct.pack_into("<I", image, pc_offset, checkpoint.encode_b(pc, target_va))
    return bytes(image)


class SelectionInvariants(unittest.TestCase):
    def setUp(self):
        self.entries = [span_entry(0, 0x1000, "too_small"), span_entry(1, 0x2000, "fits"),
                        span_entry(2, 0x3000, "also_fits")]
        self.sizes = {0x1000: 48, 0x2000: 220, 0x3000: 120}
        self.audited = []

    def extent_of(self, target):
        return target + self.sizes[target]

    def audit_ok(self, target, size, min_probe):
        self.audited.append((target, size, min_probe))
        return {"window": min_probe, "min_probe": min_probe,
                "probe_architecture": ("INLINE_PACIASP_PLUS_56B_ULTRACOMPACT" if min_probe >= 60
                                       else "INLINE_PACIASP_PLUS_52B_NO_DAIFSET"),
                "cfg_closure": {"cfg_closure_proven": True}, "topology": {}}

    def test_selects_earliest_entry_after_too_small_prefix(self):
        sel = checkpoint.select_level6_earliest_inline(self.entries, self.extent_of, self.audit_ok)
        self.assertEqual(sel["selected_index"], 1)
        self.assertEqual(sel["selected"]["symbol"], "fits")
        self.assertEqual(sel["function_size"], 220)
        self.assertEqual(sel["min_probe"], 60)
        self.assertEqual(sel["window"], 60)
        self.assertEqual(sel["scanned"], 2)
        self.assertEqual(sel["skipped"], [{"index": 0, "target_va": hex(0x1000),
                                           "function_size": 48, "reason": "TOO_SMALL"}])
        self.assertEqual(self.audited, [(0x2000, 220, 60)])

    def test_52b_core_selected_when_function_is_56_bytes(self):
        entries = [span_entry(0, 0x1000, "too_small"), span_entry(1, 0x2000, "mid")]
        sel = checkpoint.select_level6_earliest_inline(
            entries, lambda target: target + {0x1000: 48, 0x2000: 56}[target], self.audit_ok)
        self.assertEqual(sel["min_probe"], 56)
        self.assertEqual(sel["probe_architecture"], "INLINE_PACIASP_PLUS_52B_NO_DAIFSET")

    def test_cfg_not_closed_advances_to_next_entry(self):
        def audit(target, size, min_probe):
            return None if target == 0x2000 else self.audit_ok(target, size, min_probe)
        sel = checkpoint.select_level6_earliest_inline(self.entries, self.extent_of, audit)
        self.assertEqual(sel["selected_index"], 2)
        self.assertEqual([row["reason"] for row in sel["skipped"]], ["TOO_SMALL", "CFG_NOT_CLOSED"])

    def test_no_safe_target_reports_not_ready(self):
        with self.assertRaisesRegex(ValueError, "LEVEL6_EARLIEST_INLINE_TARGET_NOT_READY"):
            checkpoint.select_level6_earliest_inline(
                [span_entry(0, 0x1000, "tiny")], lambda target: target + 48, self.audit_ok)

    def test_scan_limit_excludes_later_entries(self):
        entries = [span_entry(0, 0x1000), span_entry(1, 0x2000)]
        with self.assertRaisesRegex(ValueError, "LEVEL6_EARLIEST_INLINE_TARGET_NOT_READY"):
            checkpoint.select_level6_earliest_inline(
                entries, lambda target: target + (48 if target == 0x1000 else 220),
                self.audit_ok, scan_limit=1)

    def test_rejects_empty_span_and_zero_scan_limit(self):
        for entries, scan_limit in (([], checkpoint.LEVEL6_SCAN_LIMIT),
                                    (self.entries, 0)):
            with self.assertRaisesRegex(ValueError, "LEVEL6_SELECTION_INPUT_INVALID"):
                checkpoint.select_level6_earliest_inline(entries, self.extent_of, self.audit_ok,
                                                         scan_limit=scan_limit)


class WindowAuditInvariants(unittest.TestCase):
    FUNCTION_OFFSET = 0x100
    FUNCTION_SIZE = 0x100
    FUNCTION_VA = TEXT_VA + FUNCTION_OFFSET

    def audit(self, branches, min_probe=60):
        image = image_with(self.FUNCTION_OFFSET, self.FUNCTION_SIZE, branches)
        return checkpoint.level6_window_audit(image, [(0, len(image))], TEXT_VA,
                                              self.FUNCTION_VA, self.FUNCTION_SIZE, min_probe)

    def test_cfg_closed_window_accepts_60_bytes(self):
        verdict = self.audit([])
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict["window"], 60)
        self.assertTrue(verdict["cfg_closure"]["cfg_closure_proven"])

    def test_incoming_interior_branch_rejects_window(self):
        verdict = self.audit([(0x800, self.FUNCTION_VA + 0x10)])
        self.assertIsNone(verdict)

    def test_incoming_entry_branch_rejects_window(self):
        verdict = self.audit([(0x800, self.FUNCTION_VA)])
        self.assertIsNone(verdict)

    def test_backward_branch_grows_window_to_cover_source(self):
        verdict = self.audit([(self.FUNCTION_OFFSET + 0x80, self.FUNCTION_VA + 0x08)])
        self.assertIsNotNone(verdict)
        self.assertGreater(verdict["window"], 60)
        self.assertTrue(verdict["cfg_closure"]["cfg_closure_proven"])


class RegistryContract(unittest.TestCase):
    def test_symbol_registered_everywhere_fs_complete_is(self):
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES["level6_earliest"], "__initcall6_start")
        self.assertEqual(checkpoint.INITCALL_MACROS["level6_earliest"], "device_initcall")
        self.assertEqual(checkpoint.INITCALL_TARGET_LABELS["level6_earliest"], "LEVEL6_EARLIEST")
        self.assertIn("level6_earliest", checkpoint.FS_SPAN_SYMBOLS)
        self.assertIn("level6_earliest", checkpoint.CFG_DERIVED_WINDOWS)
        self.assertIn("level6_earliest", checkpoint.PROOF_BOUNDARIES)
        self.assertIn("level6_earliest",
                      tuple(checkpoint.TARGETS) + tuple(checkpoint.INITCALL_BOUNDARIES))

    def test_inline_only_never_permits_a_trampoline(self):
        self.assertEqual(checkpoint.LEVEL6_MIN_INLINE_PROBE, 56)
        self.assertGreaterEqual(checkpoint.LEVEL6_SCAN_LIMIT, 2)
        self.assertNotIn("level6_earliest", checkpoint.EXPANDED_WINDOWS)

    def test_existing_fs_complete_contract_is_untouched(self):
        self.assertEqual(checkpoint.INITCALL_TARGET_LABELS["fs_complete"], "FIRST_DEVICE")
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES["fs_complete"], "__initcall6_start")
        self.assertEqual(checkpoint.INITCALL_MACROS["fs_complete"], "device_initcall")
        for size, expected in ((48, "ENTRY_TRAMPOLINE"), (56, "INLINE_PACIASP_PLUS_52B_NO_DAIFSET"),
                               (60, "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT"),
                               (220, "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT")):
            self.assertEqual(checkpoint.select_fs_complete_core(size, b"56", b"52")[1], expected)


if __name__ == "__main__":
    unittest.main()
