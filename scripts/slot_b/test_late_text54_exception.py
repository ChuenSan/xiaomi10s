"""Unit tests for the late index-54 TARGET-SCOPED `.text` exception round.

Pure Python only: synthetic fixtures plus two tracked reference artifacts from
the late-level round (the raw `late-table.json` span and the enriched
`late-map.json`). No kernel build, no binaries. Runs locally too: checkpoint
imports are CI-gated, so the gate environment is opted in read-only before the
imports.

The round admits exactly one `.text` target through a literal four-tuple
allowlist (index 54 / `deferred_probe_initcall` / 0xffff8000808e7564 / `.text`).
The negative fixtures prove the allowlist does not generalise: an unmatched
`.text` symbol, a shifted VA, a different index and index 53 all stay rejected,
and no generic `ALLOW_TEXT_TARGETS` switch exists.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("GITHUB_ACTIONS", "true")

import struct
import unittest
from pathlib import Path

import checkpoint as cp
import late_level_isolation as ll
import late_post50_isolation as lp
import late_text54_exception as tx

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_TABLE = ROOT / ("artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/"
                          "audit/late-table.json")
REFERENCE_MAP = ROOT / ("artifacts/slot-b-late-btic51-20260920/ci/map-and-audits/"
                        "late-map.json")
TEXT_VA = ll.TEXT_VA
ENTRY_BASE_VA = ll.FROZEN_INDEX0["entry_va"]
NOP = 0xD503201F
RET = 0xD65F03C0
PACIASP = 0xD503233F
BTI_C = 0xD503245F
CORE56 = struct.pack("<14I", *tx.CORE56_WORDS_8S)
SMALL_OFFSET = 0x2000
SMALL_TARGET = TEXT_VA + SMALL_OFFSET


def load_rows(path, key=None):
    assert path.is_file(), f"missing reference fixture: {path}"
    data = json.loads(path.read_text())
    rows = data[key] if key else data
    assert len(rows) == 86, f"{path.name} must hold 86 rows, got {len(rows)}"
    return rows


def padded_image(length, pivots=((SMALL_OFFSET, PACIASP),)):
    image = bytearray(struct.pack("<I", NOP) * length)
    for offset, word in pivots:
        struct.pack_into("<I", image, offset, word)
    return bytes(image)


def synth_entry(index, target, size, section=".init.text", registration="late_initcall",
                symbol=None, source=None):
    va = ENTRY_BASE_VA + 4 * index
    relative = target - va
    name = symbol or f"late_sym_{index}"
    return {"index": index, "entry_va": va, "entry_va_hex": hex(va),
            "entry_image_offset": va - TEXT_VA, "entry_word": hex(relative & 0xFFFFFFFF),
            "relative": relative, "target_va": target, "target_va_hex": hex(target),
            "aliases": [name], "symbol": name, "function_size": size,
            "section": section, "init_text": section == ".init.text",
            "target_unique": True, "registration_type": registration,
            "registration": f"{registration}({name})",
            "source": source or f"drivers/{index}.c", "registration_hits": []}


def pinned_entry(section=".text", symbol=None, source=None):
    """The exact frozen index-54 entry, including its real table identity."""
    entry = synth_entry(tx.PINNED_INDEX, tx.TARGET_VA, tx.FUNCTION_SIZE,
                        section=section,
                        symbol=symbol or tx.FROZEN_TARGET["symbol"],
                        source=source or tx.FROZEN_TARGET["source"])
    entry.update({"entry_va": tx.TABLE_VA, "entry_va_hex": hex(tx.TABLE_VA),
                  "entry_image_offset": tx.TABLE_IMAGE_OFFSET,
                  "entry_word": hex(tx.TABLE_WORD),
                  "relative": tx.TARGET_VA - tx.TABLE_VA})
    return entry


def pinned_world(entry_word=PACIASP, section=".text", tail_word=RET):
    """Image carrying the real index-54 window geometry inside a 492 B function."""
    image_len = tx.IMAGE_OFFSET + tx.FUNCTION_SIZE + 0x100
    image = bytearray(struct.pack("<I", NOP) * image_len)
    struct.pack_into("<I", image, tx.IMAGE_OFFSET, entry_word)
    struct.pack_into("<I", image, tx.IMAGE_OFFSET + tx.WINDOW, tail_word)
    struct.pack_into("<I", image, tx.IMAGE_OFFSET + tx.FUNCTION_SIZE - 4, tail_word)
    ctx = {"frozen": bytes(image), "image": bytes(image), "image_len": image_len,
           "text_va": TEXT_VA,
           "sections": [{"name": section, "vma": TEXT_VA, "size": image_len,
                         "code": True, "alloc": True}],
           "ranges": [(tx.IMAGE_OFFSET - 0x100, tx.IMAGE_OFFSET + 0x400)],
           "symbol_vas": sorted({tx.TARGET_VA, tx.TARGET_VA + tx.FUNCTION_SIZE}),
           "rw_sites": {tag: [] for _, tag, _ in cp.t3.RUNTIME_REWRITE_SECTIONS},
           "reloc_sites": [], "image_size": image_len,
           "cfg": {"CONFIG_ARM64_BTI_KERNEL": "y", "CONFIG_ARM64_BTI": "y"}}
    entries = [synth_entry(index, TEXT_VA + 0x100 + 1024 * index, 64)
               for index in range(ll.SPAN_COUNT)]
    entries[tx.PINNED_INDEX] = pinned_entry(section=section)
    return entries, ctx


def compose_pair(frozen, offset=tx.IMAGE_OFFSET, entry_word=PACIASP, core=CORE56):
    return {delay: tx.compose_member(frozen, offset, tx.WINDOW, entry_word, core, delay)
            for delay in (8, 1)}


def probe_for(delay, entry_word=PACIASP, core=CORE56):
    core = bytearray(core)
    struct.pack_into("<I", core, tx.DELAY_CORE_OFFSET, tx.DELAY_WORDS[delay])
    return struct.pack("<I", entry_word) + bytes(core)


def encode_b(src, dst):
    return 0x14000000 | (((dst - src) // 4) & 0x03FFFFFF)


def rel32(src_va, target_va):
    return (target_va - src_va) & 0xFFFFFFFF


class PinnedIdentity(unittest.TestCase):
    def test_reference_row_54_matches_frozen_identity(self):
        raw = load_rows(REFERENCE_TABLE)
        self.assertEqual(raw[52]["symbol"], "boot_wait_for_devices")
        self.assertEqual(raw[53]["symbol"], "sync_state_resume_initcall")
        row = raw[54]
        self.assertEqual(row["symbol"], tx.FROZEN_TARGET["symbol"])
        self.assertEqual(row["entry_va"], tx.TABLE_VA)
        self.assertEqual(row["entry_word"], hex(tx.TABLE_WORD))
        self.assertEqual(row["target_va"], tx.TARGET_VA)
        self.assertEqual(row["target_va"], row["entry_va"] + row["relative"])
        self.assertEqual(row["entry_image_offset"], tx.TABLE_IMAGE_OFFSET)

    def test_enriched_map_row_54_is_text_not_init_text(self):
        rows = load_rows(REFERENCE_MAP, key="entries")
        row = rows[54]
        self.assertEqual(row["symbol"], tx.FROZEN_TARGET["symbol"])
        self.assertEqual(row["section"], ".text")
        self.assertIs(row["init_text"], False)
        self.assertEqual(row["function_size"], tx.FUNCTION_SIZE)
        self.assertEqual(row["registration"], tx.FROZEN_TARGET["registration"])
        self.assertEqual(row["source"], tx.FROZEN_TARGET["source"])
        self.assertIs(row["target_unique"], True)
        self.assertEqual(rows[53]["symbol"], "sync_state_resume_initcall")
        self.assertEqual(rows[53]["section"], ".text")

    def test_pinned_target_constants(self):
        self.assertEqual(tx.IMAGE_OFFSET, 0x8E7564)
        self.assertEqual(tx.TABLE_IMAGE_OFFSET, 0x1D0C3B0)
        self.assertEqual(tx.TABLE_WORD, 0xFEBDB1B4)
        self.assertEqual(tx.TARGET_VA, 0xFFFF8000808E7564)
        self.assertEqual(tx.TABLE_VA, 0xFFFF800081D0C3B0)
        self.assertEqual((tx.FUNCTION_SIZE, tx.WINDOW, tx.CORE_SIZE), (492, 60, 56))
        self.assertEqual(tx.TAIL_BYTES, 432)
        self.assertEqual(tx.PROBE_ARCHITECTURE, "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT")
        self.assertEqual(tx.DELAY_WORDS, {8: 0xD37DF12A, 1: 0xD340FD2A})
        self.assertEqual(tx.DELAY_CORE_OFFSET, 8)
        self.assertEqual(tx.PAIR_DIFF_OFFSETS,
                         [tx.IMAGE_OFFSET + 13, tx.IMAGE_OFFSET + 14])
        self.assertEqual(tx.PAIR_DIFF_OFFSETS, [9336177, 9336178])
        self.assertEqual(tx.FROZEN_TARGET["section"], ".text")
        self.assertEqual(tx.ROUND_PAD_VALUE, "PACIASP_ONLY")
        self.assertEqual(tx.CORE56_SHA,
                         "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5")

    def test_frozen_registry_covers_post50_additively(self):
        self.assertEqual(tx.FROZEN_LATE_INDICES, (0, 21, 43, 49, 50, 51, 52, 55, 63))
        self.assertNotIn(tx.PINNED_INDEX, tx.FROZEN_LATE_INDICES)
        self.assertEqual(tx.FROZEN_LATE_WINDOWS[:len(lp.FROZEN_LATE_WINDOWS)],
                         lp.FROZEN_LATE_WINDOWS)
        self.assertEqual(len(tx.FROZEN_PAYLOAD_SHAS),
                         len(lp.FROZEN_PAYLOAD_SHAS) + 6)
        self.assertEqual(tx.FROZEN_HISTORICAL_WINDOWS, lp.FROZEN_HISTORICAL_WINDOWS)

    def test_frozen_window_overlap_detector(self):
        self.assertIsNone(tx.frozen_window_overlap(tx.TARGET_VA, tx.WINDOW))
        self.assertEqual(tx.frozen_window_overlap(0xFFFF800081B87EC8, 48),
                         (0xFFFF800081B87EC8, 48))
        self.assertEqual(tx.frozen_window_overlap(0xFFFF800081B72EF4, 60),
                         (0xFFFF800081B72F14, 60))

    def test_target_window_disjoint_from_every_frozen_window(self):
        tx.require_frozen_window_disjoint(tx.TARGET_VA, tx.WINDOW)
        for va, size in tx.FROZEN_LATE_WINDOWS + tx.FROZEN_HISTORICAL_WINDOWS:
            self.assertFalse(tx.TARGET_VA < va + size and va < tx.TARGET_VA + tx.WINDOW,
                             f"window overlaps frozen {va:#x}+{size}")

    def test_frozen_payload_sha_rejected(self):
        for sha in tx.FROZEN_PAYLOAD_SHAS:
            with self.assertRaises(ValueError) as caught:
                tx.require_fresh_payload(sha)
            self.assertIn("RERUN_FORBIDDEN_FROZEN_PAYLOAD", str(caught.exception))

    def test_fresh_payload_sha_accepted(self):
        tx.require_fresh_payload("0" * 63 + "1")


class ExceptionScope(unittest.TestCase):
    def test_allowlist_is_a_single_literal_slot(self):
        tx.require_exception_scope()
        self.assertEqual(len(tx.TEXT_EXCEPTION_ALLOWED), 1)
        self.assertIsNone(tx.GLOBAL_ALLOW_TEXT_TARGETS)
        self.assertEqual(tx.TEXT_EXCEPTION_ALLOWED[0],
                         (54, "deferred_probe_initcall", 0xFFFF8000808E7564, ".text"))

    def test_allowlist_never_covers_index53_or_init_text(self):
        index, symbol, _va, section = tx.TEXT_EXCEPTION_ALLOWED[0]
        self.assertNotEqual(index, 53)
        self.assertNotEqual(symbol, "sync_state_resume_initcall")
        self.assertNotEqual(section, ".init.text")

    def test_exception_requires_all_four_fields(self):
        base = synth_entry(54, tx.TARGET_VA, tx.FUNCTION_SIZE, section=".text",
                           symbol="deferred_probe_initcall")
        self.assertTrue(tx.exception_matches(base))
        self.assertFalse(tx.exception_matches({**base, "index": 52}))
        self.assertFalse(tx.exception_matches({**base, "index": 53}))
        self.assertFalse(tx.exception_matches({**base, "target_va": tx.TARGET_VA + 4}))
        self.assertFalse(tx.exception_matches({**base, "symbol": "init_subsystem"}))
        self.assertFalse(tx.exception_matches({**base, "section": ".init.text"}))

    def test_multi_slot_allowlist_rejected(self):
        saved = tx.TEXT_EXCEPTION_ALLOWED
        try:
            tx.TEXT_EXCEPTION_ALLOWED = saved + ((53, "sync_state_resume_initcall",
                                                  0xFFFF8000808DF400, ".text"),)
            with self.assertRaises(ValueError) as caught:
                tx.require_exception_scope()
            self.assertIn("TEXT_EXCEPTION_MULTI_SLOT", str(caught.exception))
        finally:
            tx.TEXT_EXCEPTION_ALLOWED = saved

    def test_generic_text_switch_rejected(self):
        saved = tx.GLOBAL_ALLOW_TEXT_TARGETS
        try:
            tx.GLOBAL_ALLOW_TEXT_TARGETS = "YES"
            with self.assertRaises(ValueError) as caught:
                tx.require_exception_scope()
            self.assertIn("GLOBAL_TEXT_TARGETS_SWITCH_PRESENT", str(caught.exception))
        finally:
            tx.GLOBAL_ALLOW_TEXT_TARGETS = saved

    def test_index53_slot_cannot_be_smuggled_in(self):
        saved = tx.TEXT_EXCEPTION_ALLOWED
        try:
            tx.TEXT_EXCEPTION_ALLOWED = ((53, "sync_state_resume_initcall",
                                          0xFFFF8000808DF400, ".text"),)
            with self.assertRaises(ValueError) as caught:
                tx.require_exception_scope()
            self.assertIn("TEXT_EXCEPTION_MUST_NOT_COVER_INDEX53",
                          str(caught.exception))
        finally:
            tx.TEXT_EXCEPTION_ALLOWED = saved


class AuditGates(unittest.TestCase):
    def test_pinned_target_passes_every_gate(self):
        entries, ctx = pinned_world()
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX], ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["window"], tx.WINDOW)
        self.assertEqual(record["core_size"], tx.CORE_SIZE)
        self.assertEqual(record["probe_architecture"], tx.PROBE_ARCHITECTURE)
        self.assertEqual(record["gates"]["INIT_TEXT"], "PASS")
        self.assertEqual(record["gates"]["SECTION_SCAN"], "PASS")
        self.assertIs(record["text_exception_matched"], True)
        self.assertIs(record["pac"], True)
        self.assertIs(record["bti"], False)
        self.assertEqual(set(record["gates"]), set(ll.GATES) | {tx.ROUND_PAD_GATE})

    def test_init_text_target_still_accepted_without_exception(self):
        _entries, ctx = pinned_world(section=".init.text")
        record = tx.audit_candidate_text54(
            pinned_entry(section=".init.text", symbol="late_sym_other"), ctx)
        self.assertEqual(record["gates"]["INIT_TEXT"], "PASS")
        self.assertIs(record["text_exception_matched"], False)

    def test_unmatched_text_symbol_rejected(self):
        entries, ctx = pinned_world()
        record = tx.audit_candidate_text54(
            {**entries[tx.PINNED_INDEX], "symbol": "init_subsystem"}, ctx)
        self.assertFalse(record["PASS"])
        self.assertIn("TARGET_NOT_INIT_TEXT:.text", record["fail_reasons"][0])

    def test_same_section_diff_va_rejected(self):
        entries, ctx = pinned_world()
        record = tx.audit_candidate_text54(
            {**entries[tx.PINNED_INDEX], "target_va": tx.TARGET_VA + 4}, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any(r.startswith("TARGET_NOT_INIT_TEXT")
                            for r in record["fail_reasons"]))

    def test_diff_index_same_symbol_rejected(self):
        entries, ctx = pinned_world()
        record = tx.audit_candidate_text54(
            {**entries[tx.PINNED_INDEX], "index": 52}, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any(r.startswith("TARGET_NOT_INIT_TEXT")
                            for r in record["fail_reasons"]))

    def test_bti_c_and_bti_j_pads_rejected(self):
        entries, _ctx = pinned_world()
        _e, bti_c_ctx = pinned_world(entry_word=BTI_C)
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX], bti_c_ctx)
        self.assertFalse(record["PASS"])
        self.assertIn("ROUND_PAD_CLASS_NOT_PACIASP", record["fail_reasons"])
        _e, j_ctx = pinned_world(entry_word=tx.BTI_NON_C_WORDS[0])
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX], j_ctx)
        self.assertFalse(record["PASS"])
        self.assertIn("ENTRY_NOT_PACIASP_OR_BTI", record["fail_reasons"])

    def test_section_window_cross_rejected(self):
        entries, ctx = pinned_world()
        sections = [{"name": ".text", "vma": TEXT_VA, "size": tx.IMAGE_OFFSET,
                     "code": True, "alloc": True},
                    {"name": ".text", "vma": TEXT_VA + tx.IMAGE_OFFSET,
                     "size": tx.WINDOW // 2, "code": True, "alloc": True}]
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX],
                                           {**ctx, "sections": sections})
        self.assertFalse(record["PASS"])
        self.assertFalse(record["gates"]["SECTION_SCAN"].startswith("PASS"))

    def test_interior_incoming_branch_rejected(self):
        entries, ctx = pinned_world()
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, tx.IMAGE_OFFSET - 4,
                         encode_b(TEXT_VA + tx.IMAGE_OFFSET - 4, tx.TARGET_VA + 8))
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX],
                                           {**ctx, "frozen": bytes(image),
                                            "image": bytes(image)})
        self.assertFalse(record["PASS"])
        self.assertTrue(any(r.startswith("INCOMING_WINDOW_INTERIOR")
                            for r in record["fail_reasons"]))

    def test_entry_incoming_branch_rejected(self):
        entries, ctx = pinned_world()
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, tx.IMAGE_OFFSET - 4,
                         encode_b(TEXT_VA + tx.IMAGE_OFFSET - 4, tx.TARGET_VA))
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX],
                                           {**ctx, "frozen": bytes(image),
                                            "image": bytes(image)})
        self.assertFalse(record["PASS"])
        self.assertIn("INCOMING_ENTRY_BRANCH", record["fail_reasons"])

    def test_runtime_rewrite_overlap_rejected(self):
        entries, ctx = pinned_world()
        rw = {tag: ([tx.TARGET_VA + 4] if tag == "altinstructions" else [])
              for _, tag, _ in cp.t3.RUNTIME_REWRITE_SECTIONS}
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX],
                                           {**ctx, "rw_sites": rw})
        self.assertFalse(record["PASS"])
        self.assertTrue(any(r.startswith("REWRITE_OVERLAP")
                            for r in record["fail_reasons"]))

    def test_symbol_inside_window_rejected(self):
        entries, ctx = pinned_world()
        ctx = {**ctx, "symbol_vas": sorted({tx.TARGET_VA, tx.TARGET_VA + 8,
                                            tx.TARGET_VA + tx.FUNCTION_SIZE})}
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX], ctx)
        self.assertFalse(record["PASS"])
        self.assertFalse(record["gates"]["SYMBOL_SCAN"].startswith("PASS"))

    def test_window_past_function_end_rejected(self):
        entries, ctx = pinned_world()
        ctx = {**ctx, "symbol_vas": [tx.TARGET_VA, tx.TARGET_VA + tx.FUNCTION_SIZE]}
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX], ctx)
        self.assertTrue(record["PASS"], record["gates"])
        ctx = {**ctx, "symbol_vas": [tx.TARGET_VA, tx.TARGET_VA + 32]}
        record = tx.audit_candidate_text54(entries[tx.PINNED_INDEX], ctx)
        self.assertFalse(record["PASS"])
        self.assertFalse(record["gates"]["EXTENT_SCAN"].startswith("PASS"))


class PinDrift(unittest.TestCase):
    def test_pinned_slot_must_be_text_section(self):
        entries, ctx = pinned_world(section=".init.text")
        with self.assertRaises(ValueError) as caught:
            tx.pin_target(entries, ctx)
        self.assertIn("PINNED_SECTION_DRIFT", str(caught.exception))

    def test_pinned_function_size_drift_rejected(self):
        entries, ctx = pinned_world()
        broken = list(entries)
        broken[tx.PINNED_INDEX] = {**broken[tx.PINNED_INDEX], "function_size": 48}
        with self.assertRaises(ValueError) as caught:
            tx.pin_target(broken, ctx)
        self.assertIn("PINNED_FUNCTION_SIZE_DRIFT", str(caught.exception))

    def test_pinned_table_word_drift_rejected(self):
        entries, ctx = pinned_world()
        broken = list(entries)
        broken[tx.PINNED_INDEX] = {**broken[tx.PINNED_INDEX], "entry_word": "0xdeadbeef"}
        with self.assertRaises(ValueError) as caught:
            tx.pin_target(broken, ctx)
        self.assertIn("PINNED_TABLE_WORD_DRIFT", str(caught.exception))

    def test_pinned_target_va_drift_rejected(self):
        entries, ctx = pinned_world()
        broken = list(entries)
        broken[tx.PINNED_INDEX] = {**broken[tx.PINNED_INDEX],
                                   "target_va": tx.TARGET_VA + 4}
        with self.assertRaises(ValueError) as caught:
            tx.pin_target(broken, ctx)
        self.assertIn("PINNED_TARGET_VA_DRIFT", str(caught.exception))

    def test_pinned_target_passes_and_reports_window(self):
        entries, ctx = pinned_world()
        selection = tx.pin_target(entries, ctx)
        self.assertEqual(selection["selected_index"], 54)
        self.assertIsNone(selection["deviation"])
        self.assertEqual(selection["audit"]["window"], tx.WINDOW)
        self.assertEqual(selection["interval_walk"], "NONE_TARGET_PINNED_DIRECTLY")


class NonGeneralization(unittest.TestCase):
    def probe_world(self):
        entries, ctx = pinned_world()
        entries[53] = synth_entry(53, TEXT_VA + 0x8000, 32, section=".text",
                                  symbol="sync_state_resume_initcall")
        entries[64] = synth_entry(64, TEXT_VA + 0xC000, 40, section=".text",
                                  symbol="init_subsystem")
        return entries, ctx

    def test_probe_rejects_every_adversarial_neighbour(self):
        entries, ctx = self.probe_world()
        scope = tx.non_generalization_probe(entries, ctx)
        self.assertEqual(scope["allowed_slot_count"], 1)
        self.assertEqual(scope["global_text_switch"], "ABSENT")
        self.assertEqual(scope["verdict"], "TARGET_SCOPED_ONLY")
        for key in ("NEG_INDEX53_TOO_SMALL_REJECTED", "NEG_DIFF_TEXT_SYMBOL_REJECTED",
                    "NEG_SAME_SECTION_DIFF_VA_REJECTED",
                    "NEG_DIFF_INDEX_SAME_SYMBOL_REJECTED",
                    "NEG_WRONG_SYMBOL_SAME_INDEX_REJECTED",
                    "NEG_PINNED_SLOT_ACCEPTED"):
            self.assertEqual(scope["adversarial"][key], "YES", key)

    def test_probe_fails_when_pinned_slot_is_not_text(self):
        entries, ctx = pinned_world(section=".init.text")
        with self.assertRaises(ValueError) as caught:
            tx.non_generalization_probe(entries, ctx)
        self.assertIn("PINNED_INDEX54_UNEXPECTEDLY_INIT_TEXT", str(caught.exception))


class Composition(unittest.TestCase):
    def test_composed_window_identity_and_control_flow(self):
        for delay in (8, 1):
            tx.gate_composed_window(probe_for(delay), PACIASP, tx.DELAY_WORDS[delay])
            tx.gate_composed_control_flow(probe_for(delay), SMALL_TARGET)

    def test_entry_pad_rewritten_rejected(self):
        probe = probe_for(8)
        bad = struct.pack("<I", BTI_C) + probe[4:]
        with self.assertRaises(ValueError) as caught:
            tx.gate_composed_window(bad, PACIASP, tx.DELAY_WORDS[8])
        self.assertIn("ENTRY_PAD_WORD_REWRITTEN", str(caught.exception))

    def test_core_word_drift_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 16, NOP)
        with self.assertRaises(ValueError) as caught:
            tx.gate_composed_window(bytes(probe), PACIASP, tx.DELAY_WORDS[8])
        self.assertIn("COMPOSED_CORE_WORD_DRIFT", str(caught.exception))

    def test_terminal_word_corruption_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 56, RET)
        with self.assertRaises(ValueError) as caught:
            tx.gate_composed_window(bytes(probe), PACIASP, tx.DELAY_WORDS[8])
        self.assertIn("COMPOSED_CORE_WORD_DRIFT", str(caught.exception))

    def test_composed_branch_outside_window_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 16,
                         encode_b(SMALL_TARGET + 16, SMALL_TARGET + 0x400))
        with self.assertRaises(ValueError) as caught:
            tx.gate_composed_control_flow(bytes(probe), SMALL_TARGET)
        self.assertIn("COMPOSED_BRANCH_OUTSIDE_WINDOW", str(caught.exception))

    def test_loop_head_drift_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 36, encode_b(SMALL_TARGET + 36,
                                                   SMALL_TARGET + 16))
        with self.assertRaises(ValueError) as caught:
            tx.gate_composed_control_flow(bytes(probe), SMALL_TARGET)
        self.assertIn("COMPOSED_LOOP_HEAD_DRIFT", str(caught.exception))

    def _semantics_error(self, words):
        frozen = padded_image(0x4000)
        with self.assertRaises(ValueError) as caught:
            tx.core_semantics({8: words}, frozen, SMALL_OFFSET,
                              {"CONFIG_ARM64_BTI": "y"},
                              {"function_size": tx.FUNCTION_SIZE})
        return str(caught.exception)

    def test_pac_hint_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 16, PACIASP)
        self.assertIn("PAC_HINT_IN_COMPOSED_WINDOW", self._semantics_error(bytes(probe)))

    def test_ret_in_diagnostic_path_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 16, RET)
        self.assertIn("RET_IN_DIAGNOSTIC_PATH", self._semantics_error(bytes(probe)))

    def test_indirect_call_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 16, tx.INDIRECT_CALL_WORDS[0])
        self.assertIn("INDIRECT_CALL_IN_DIAGNOSTIC_PATH",
                      self._semantics_error(bytes(probe)))

    def test_frozen_entry_not_paciasp_rejected(self):
        frozen = bytes(struct.pack("<I", NOP) * 0x4000)
        with self.assertRaises(ValueError) as caught:
            tx.core_semantics({8: probe_for(8)}, frozen, SMALL_OFFSET,
                              {"CONFIG_ARM64_BTI": "y"},
                              {"function_size": tx.FUNCTION_SIZE})
        self.assertIn("FROZEN_ENTRY_NOT_PACIASP", str(caught.exception))

    def test_semantics_tokens_record_tail_containment(self):
        frozen = padded_image(0x4000)
        semantics = tx.core_semantics({8: probe_for(8), 1: probe_for(1)}, frozen,
                                      SMALL_OFFSET, {"CONFIG_ARM64_BTI": "y"},
                                      {"function_size": tx.FUNCTION_SIZE})
        self.assertEqual(semantics["TAIL_BYTES"], tx.TAIL_BYTES)
        self.assertEqual(semantics["TAIL_PRESENT"], "YES")
        self.assertEqual(semantics["TAIL_IS_UNMODIFIED_ORIGINAL_CODE"], "YES")
        self.assertEqual(semantics["TAIL_UNREACHABLE_FROM_COMPOSED_WINDOW"], "YES")
        self.assertEqual(semantics["NO_COMPOSED_BRANCH_LEAVES_WINDOW"], "YES")
        self.assertEqual(
            semantics["DIAGNOSTIC_CANNOT_RETURN_TO_NORMAL_FUNCTION"], "YES")
        self.assertEqual(semantics["NO_RET_IN_WINDOW"], "YES")


class PairSemantics(unittest.TestCase):
    def test_pair_diff_is_delay_constant_only(self):
        frozen = padded_image(0x4000)
        members = compose_pair(frozen, offset=SMALL_OFFSET)
        changed = [i for i, (a, b) in enumerate(zip(members[8][1], members[1][1]))
                   if a != b]
        self.assertEqual(changed, [SMALL_OFFSET + 13, SMALL_OFFSET + 14])
        tx.base.assert_pair_delay_only(changed, SMALL_OFFSET, tx.CORE_SIZE)

    def test_live_geometry_pair_diff_offsets(self):
        frozen = padded_image(0x4000)
        changed = [tx.IMAGE_OFFSET + 13, tx.IMAGE_OFFSET + 14]
        tx.base.assert_pair_delay_only(changed, tx.IMAGE_OFFSET, tx.CORE_SIZE)
        self.assertEqual(changed, tx.PAIR_DIFF_OFFSETS)

    def test_extra_pair_diff_rejected(self):
        with self.assertRaises(ValueError):
            tx.base.assert_pair_delay_only(
                tx.PAIR_DIFF_OFFSETS + [tx.IMAGE_OFFSET + 40], tx.IMAGE_OFFSET,
                tx.CORE_SIZE)

    def test_delay_word_slot_matches_frozen_core(self):
        self.assertEqual(struct.unpack_from("<I", CORE56, tx.DELAY_CORE_OFFSET)[0],
                         0xD37DF12A)
        self.assertEqual(tx.DELAY_WORDS[8], 0xD37DF12A)
        self.assertEqual(tx.DELAY_WORDS[1], 0xD340FD2A)

    def test_member_changes_only_inside_window(self):
        base = padded_image(0x4000)
        _probe, payload = tx.compose_member(base, SMALL_OFFSET, tx.WINDOW,
                                            PACIASP, CORE56, 8)
        diffs = tx.require_member_scope(payload, base, SMALL_OFFSET, tx.WINDOW)
        self.assertTrue(diffs)
        self.assertTrue(all(SMALL_OFFSET + 4 <= i < SMALL_OFFSET + tx.WINDOW
                            for i in diffs))
        self.assertEqual(payload[SMALL_OFFSET + tx.WINDOW:],
                         base[SMALL_OFFSET + tx.WINDOW:])
        self.assertEqual(payload[:SMALL_OFFSET], base[:SMALL_OFFSET])
        self.assertEqual(payload[SMALL_OFFSET:SMALL_OFFSET + 4],
                         base[SMALL_OFFSET:SMALL_OFFSET + 4])

    def test_member_changes_outside_window_rejected(self):
        base = padded_image(0x4000)
        _probe, payload = tx.compose_member(base, SMALL_OFFSET, tx.WINDOW,
                                            PACIASP, CORE56, 8)
        mutated = bytearray(payload)
        mutated[SMALL_OFFSET + tx.WINDOW + 4] = 0x41
        with self.assertRaises(ValueError) as caught:
            tx.require_member_scope(bytes(mutated), base, SMALL_OFFSET, tx.WINDOW)
        self.assertIn("MEMBER_CHANGED_OUTSIDE_WINDOW", str(caught.exception))

    def test_entry_pad_modification_rejected(self):
        base = bytes(struct.pack("<I", NOP) * 0x4000)
        _probe, payload = tx.compose_member(base, SMALL_OFFSET, tx.WINDOW,
                                            PACIASP, CORE56, 8)
        with self.assertRaises(ValueError) as caught:
            tx.require_member_scope(payload, base, SMALL_OFFSET, tx.WINDOW)
        self.assertIn("ENTRY_PAD_MODIFIED", str(caught.exception))

    def test_prel32_change_rejected_and_unchanged_accepted(self):
        frozen = bytes(struct.pack("<I", NOP) * 0x3000)
        tx.require_prel32_unchanged(frozen, frozen, 0x2000)
        mutated = bytearray(frozen)
        struct.pack_into("<I", mutated, 0x2000, 0xDEADBEEF)
        with self.assertRaises(ValueError) as caught:
            tx.require_prel32_unchanged(bytes(mutated), frozen, 0x2000)
        self.assertIn("PREL32_TARGET_REWRITTEN", str(caught.exception))

    def test_inline_only_payload_has_no_branch_leaving_the_window(self):
        for delay in (8, 1):
            probe = probe_for(delay)
            self.assertEqual(len(probe), tx.WINDOW)
            self.assertEqual(struct.unpack_from("<I", probe, 0)[0], PACIASP)
            branches = [(i, cp.branch_target(struct.unpack_from("<I", probe, 4 * i)[0],
                                             SMALL_TARGET + 4 * i))
                        for i in range(15)]
            inside = [(i, t) for i, t in branches if t is not None]
            self.assertTrue(inside)
            for index, target in inside:
                self.assertTrue(SMALL_TARGET <= target < SMALL_TARGET + tx.WINDOW,
                                f"word {index} branches to {target:#x}")


class ReferenceClosure(unittest.TestCase):
    SOURCE_VA = TEXT_VA + 0x2800
    TAIL_SOURCE_VA = TEXT_VA + 0x3000

    def census_image(self, extra=None):
        length = 0x8000
        image = bytearray(struct.pack("<I", NOP) * length)
        pivots = [(0x7000, rel32(TEXT_VA + 0x7000, tx.TARGET_VA)),
                  (0x3000, rel32(self.TAIL_SOURCE_VA, tx.TARGET_VA + 100)),
                  (0x3800, rel32(TEXT_VA + 0x3800, tx.TARGET_VA + 200))]
        if extra:
            pivots.append(extra)
        for offset, word in pivots:
            struct.pack_into("<I", image, offset, word)
        return bytes(image)

    def test_relative_reference_census_partitions_window_and_tail(self):
        census = tx.relative_reference_census(self.census_image(), TEXT_VA,
                                              tx.TARGET_VA, tx.FUNCTION_SIZE,
                                              tx.WINDOW, 0x7000)
        self.assertEqual([row["offset"] for row in census["window_sites"]], ["0x7000"])
        self.assertEqual(census["tail_sites"], ["0x3000", "0x3800"])
        self.assertIs(census["tail_references_are_inert"], True)
        self.assertEqual(census["verdict"],
                         "ONLY_INITCALL_TABLE_REFERENCE_INTO_WINDOW")

    def test_extra_window_reference_rejected(self):
        image = self.census_image(extra=(0x2800, rel32(self.SOURCE_VA,
                                                       tx.TARGET_VA + 8)))
        with self.assertRaises(ValueError) as caught:
            tx.relative_reference_census(image, TEXT_VA, tx.TARGET_VA,
                                         tx.FUNCTION_SIZE, tx.WINDOW, 0x7000)
        self.assertIn("WINDOW_REFERENCE_DATA_HIT", str(caught.exception))

    def test_missing_slot_rejected(self):
        image = bytes(struct.pack("<I", NOP) * 0x3000)
        with self.assertRaises(ValueError) as caught:
            tx.relative_reference_census(image, TEXT_VA, tx.TARGET_VA,
                                         tx.FUNCTION_SIZE, tx.WINDOW, 0x2000)
        self.assertIn("WINDOW_REFERENCE_SLOT_MISSING", str(caught.exception))

    def test_window_larger_than_function_rejected(self):
        image = bytes(struct.pack("<I", NOP) * 0x3000)
        with self.assertRaises(ValueError) as caught:
            tx.relative_reference_census(image, TEXT_VA, tx.TARGET_VA,
                                         tx.WINDOW, tx.WINDOW + 4, 0x2000)
        self.assertIn("REFERENCE_CENSUS_WINDOW_LARGER_THAN_FUNCTION",
                      str(caught.exception))


class SummarySurface(unittest.TestCase):
    SOURCE = None

    @classmethod
    def setUpClass(cls):
        cls.SOURCE = (ROOT / "scripts/slot_b/late_text54_exception.py").read_text()

    def test_summary_literal_gates_present(self):
        for token in ("TEXT_EXCEPTION_ALLOWED=YES", "GLOBAL_ALLOW_TEXT_TARGETS=ABSENT",
                      "TEXT_EXCEPTION_SCOPE=TARGET_SCOPED_ONLY",
                      "NO_GENERIC_TEXT_POLICY_RELAXATION=YES",
                      "TARGET_SCOPED_TEXT_EXCEPTION=PASS",
                      "TEXT_EXCEPTION_LIFETIME_CONTAINED=YES",
                      "NO_OTHER_EARLY_RUNTIME_CALLER=YES",
                      "INITCALL_TABLE_REFERENCE_ONLY=YES", "OTHER_RUNTIME_REFERENCE=NO",
                      "CFG_XREF_RUNTIME_REWRITE=PASS", "INDEX53_AUTO_ELIGIBLE=NO",
                      "NO_ALLOW_TEXT_TARGETS_SWITCH=YES", "UNIQUE_ALLOWLIST_SLOT=YES",
                      "CORE_SHA_MATCHES_FROZEN_FAMILY=YES", "PROBE_FAMILY_REUSED=YES",
                      "DEVICE_BOOT=0", "LATE_INITCALLS_COMPLETED=NOT_PROVEN",
                      "LATE_HIGH1=NOT_EXECUTED",
                      "DEFERRED_PROBE_INITCALL_ENTRY=NOT_PROVEN",
                      "PARTITION_WRITES=0", "SLOT_A_WRITTEN=NO", "LOCAL_BUILD=NO"):
            self.assertIn(token, self.SOURCE, token)

    def test_summary_keys_emitted_dynamically(self):
        for token in ("TEXT_EXCEPTION_ALLOWED_SYMBOL", "TEXT_EXCEPTION_ALLOWED_INDEX",
                      "TEXT_EXCEPTION_ALLOWED_VA", "TEXT_EXCEPTION_ALLOWED_SECTION",
                      "LATEST_PROVEN_LATE_INDEX", "TEXT54_WINDOW_REFERENCE_FORENSIC",
                      "TEXT54_TAIL_REACHABILITY", "WINDOW_AGREEMENT_INDEX54",
                      "ENTRY_PAD_CLASS", "PROBE_FAMILY", "CORE_SHA256",
                      "TEXT_EXCEPTION_MATCHED"):
            self.assertIn(token, self.SOURCE, token)

    def test_frozen_families_unmodified_token(self):
        self.assertIn("FROZEN_FAMILIES_UNCHANGED=PACIASP_PLUS_52B,PACIASP_PLUS_56B,"
                      "BTI_C_PLUS_56B,COMPACT_INLINE_48B", self.SOURCE)

    def test_no_delete_calls_anywhere(self):
        for banned in ("shutil.rmtree", "os.remove", "unlink("):
            self.assertNotIn(banned, self.SOURCE, banned)


if __name__ == "__main__":
    unittest.main()
