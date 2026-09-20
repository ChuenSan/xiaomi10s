"""Unit tests for the late index-51 BTI c probe authorization round.

Pure Python only: synthetic fixtures plus the tracked reference late-table.json
(artifacts/slot-b-post-initcalls-20260919). No kernel build, no binaries.
Runs locally too: checkpoint imports are CI-gated, so the gate environment is
opted in read-only before the imports.
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
import late_btic51_probe_authorization as bt

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / ("artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/"
                    "audit/late-table.json")
TEXT_VA = ll.TEXT_VA
ENTRY_BASE_VA = ll.FROZEN_INDEX0["entry_va"]
NOP = 0xD503201F
RET = 0xD65F03C0
PACIASP = 0xD503233F
BTI_C = 0xD503245F
CORE56 = cp.ultracompact_core(struct.pack("<14I", *cp.ULTRACOMPACT_WORDS))
SMALL_OFFSET = 0x2000
SMALL_TARGET = TEXT_VA + SMALL_OFFSET


def load_reference():
    assert REFERENCE.is_file(), f"missing reference fixture: {REFERENCE}"
    rows = json.loads(REFERENCE.read_text())
    assert len(rows) == 86, f"reference fixture must hold 86 rows, got {len(rows)}"
    return rows


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


def synth_world(sizes=None, entry_words=None, tail_words=None):
    """86-entry late span on NOP text; optional per-index size/entry/tail words."""
    sizes = sizes or {}
    entry_words = entry_words or {}
    tail_words = tail_words or {}
    offsets = {}
    cursor = 0x1000
    for index in range(ll.SPAN_COUNT):
        offsets[index] = cursor
        cursor += max(sizes.get(index, 100), 64) + 64
    image_len = cursor + 0x8000
    image = bytearray(struct.pack("<I", NOP) * image_len)
    for index in range(ll.SPAN_COUNT):
        size = sizes.get(index, 100)
        struct.pack_into("<I", image, offsets[index], entry_words.get(index, PACIASP))
        struct.pack_into("<I", image, offsets[index] + size - 4,
                         tail_words.get(index, RET))
    targets = {index: TEXT_VA + offsets[index] for index in offsets}
    entries = [synth_entry(index, targets[index], sizes.get(index, 100))
               for index in range(ll.SPAN_COUNT)]
    symbol_vas = sorted(targets.values()) + [TEXT_VA + image_len]
    ctx = {"frozen": bytes(image), "image": bytes(image), "image_len": image_len,
           "text_va": TEXT_VA,
           "sections": [{"name": ".init.text", "vma": TEXT_VA, "size": cursor,
                         "code": True, "alloc": True}],
           "ranges": [(0, image_len)], "symbol_vas": symbol_vas,
           "rw_sites": {tag: [] for _, tag, _ in cp.t3.RUNTIME_REWRITE_SECTIONS},
           "reloc_sites": [], "image_size": image_len,
           "cfg": {"CONFIG_ARM64_BTI_KERNEL": "y"}}
    return entries, ctx, targets, offsets


def pinned_world(tail_word=RET):
    """World where index 51 carries the frozen identity of
    setup_vcpu_hotplug_event (real target VA, image offset and table slot)."""
    image_len = bt.TABLE_IMAGE_OFFSET + 4
    image = bytearray(struct.pack("<I", NOP) * image_len)
    struct.pack_into("<I", image, bt.IMAGE_OFFSET, BTI_C)
    struct.pack_into("<I", image, bt.IMAGE_OFFSET + bt.FUNCTION_SIZE - 4, tail_word)
    struct.pack_into("<I", image, bt.TABLE_IMAGE_OFFSET, bt.TABLE_WORD)
    ctx = {"frozen": bytes(image), "image": bytes(image), "image_len": image_len,
           "text_va": TEXT_VA,
           "sections": [{"name": ".init.text", "vma": TEXT_VA, "size": image_len,
                         "code": True, "alloc": True}],
           "ranges": [(bt.IMAGE_OFFSET - 0x100, bt.IMAGE_OFFSET + 0x100)],
           "symbol_vas": sorted({bt.TARGET_VA, bt.TARGET_VA + bt.FUNCTION_SIZE}),
           "rw_sites": {tag: [] for _, tag, _ in cp.t3.RUNTIME_REWRITE_SECTIONS},
           "reloc_sites": [], "image_size": image_len,
           "cfg": {"CONFIG_ARM64_BTI_KERNEL": "y"}}
    entries = [synth_entry(index, TEXT_VA + 0x100 + 64 * index, 64)
               for index in range(ll.SPAN_COUNT)]
    entries[bt.PINNED_INDEX] = synth_entry(
        bt.PINNED_INDEX, bt.TARGET_VA, bt.FUNCTION_SIZE,
        symbol=bt.FROZEN_TARGET["symbol"], source=bt.FROZEN_TARGET["source"])
    return entries, ctx


def small_frozen():
    """Frozen base with a bti c entry at SMALL_OFFSET and a ret tail."""
    image = bytearray(struct.pack("<I", NOP) * 0x4000)
    struct.pack_into("<I", image, SMALL_OFFSET, BTI_C)
    struct.pack_into("<I", image, SMALL_OFFSET + bt.WINDOW, RET)
    return bytes(image)


def compose_pair(frozen, offset, entry_word=BTI_C, core=CORE56):
    members = {}
    for delay in (8, 1):
        members[delay] = ll.compose_member(frozen, offset, bt.WINDOW, entry_word,
                                           core, delay)
    return members


def probe_for(delay, entry_word=BTI_C, core=CORE56):
    core = bytearray(core)
    struct.pack_into("<I", core, 8, bt.DELAY_WORDS[delay])
    return struct.pack("<I", entry_word) + bytes(core)


def encode_b(src, dst):
    return 0x14000000 | (((dst - src) // 4) & 0x03FFFFFF)


class PinnedIdentity(unittest.TestCase):
    def test_reference_rows_50_and_51_match_frozen_identity(self):
        rows = load_reference()
        self.assertEqual(rows[50]["symbol"], "clk_debug_init")
        row = rows[51]
        self.assertEqual(row["symbol"], bt.FROZEN_TARGET["symbol"])
        self.assertEqual(row["entry_va"], bt.TABLE_VA)
        self.assertEqual(row["entry_word"], hex(bt.TABLE_WORD))
        self.assertEqual(row["target_va"], bt.TARGET_VA)
        self.assertEqual(row["target_va"], row["entry_va"] + row["relative"])

    def test_pinned_target_constants(self):
        self.assertEqual(bt.FROZEN_TARGET["image_offset"], hex(bt.IMAGE_OFFSET))
        self.assertEqual(bt.IMAGE_OFFSET, 0x1B87130)
        self.assertEqual(bt.TABLE_IMAGE_OFFSET, 0x1D0C3A4)
        self.assertEqual(bt.TABLE_WORD, 0xFFE7AD8C)
        self.assertEqual((bt.FUNCTION_SIZE, bt.WINDOW, bt.TAIL_BYTES), (64, 60, 4))
        self.assertEqual(bt.CORE_SIZE, 56)
        self.assertEqual(bt.PROBE_ARCHITECTURE, "BTI_C_PLUS_56B_ULTRACOMPACT")
        self.assertEqual(bt.DELAY_WORDS, {8: 0xD37DF12A, 1: 0xD340FD2A})
        self.assertEqual(bt.PAIR_DIFF_OFFSETS, [28864829, 28864830])
        self.assertEqual(bt.PAIR_DIFF_OFFSETS,
                         [bt.IMAGE_OFFSET + 4 + 8 + 1, bt.IMAGE_OFFSET + 4 + 8 + 2])
        self.assertEqual(bt.FROZEN_LATE_INDICES, (0, 21, 43, 49, 50, 55, 63))
        self.assertEqual(bt.ROUND_PAD_VALUE, "BTI_C_ONLY")
        self.assertEqual(bt.CORE56_SHA,
                         "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5")
        self.assertEqual(cp.digest(CORE56), bt.CORE56_SHA)


class FrozenRegistry(unittest.TestCase):
    def test_frozen_registry_covers_post50_additively(self):
        self.assertEqual(len(bt.FROZEN_PAYLOAD_SHAS), 14)
        self.assertEqual(len(bt.FROZEN_PAYLOAD_SHAS) - 2, len(lp.FROZEN_PAYLOAD_SHAS))
        self.assertIn("28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",
                      bt.FROZEN_PAYLOAD_SHAS)
        self.assertIn("aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",
                      bt.FROZEN_PAYLOAD_SHAS)
        self.assertEqual(len(bt.FROZEN_LATE_WINDOWS), 8)
        self.assertIn((0xFFFF800081B72F14, 60), bt.FROZEN_LATE_WINDOWS)  # POST50
        self.assertEqual(len(bt.FROZEN_HISTORICAL_WINDOWS), 11)

    def test_frozen_window_overlap_detector(self):
        self.assertIsNotNone(bt.frozen_window_overlap(0xFFFF800081B72F14, 60))
        self.assertIsNotNone(bt.frozen_window_overlap(0xFFFF800081B72F14 + 8, 60))
        self.assertIsNone(bt.frozen_window_overlap(0xFFFF800081B72F14 + 60, 60))
        self.assertIsNone(bt.frozen_window_overlap(bt.TARGET_VA, 64))
        self.assertIsNone(bt.frozen_window_overlap(bt.TARGET_VA + 64, 60))

    def test_target_window_disjoint_from_every_frozen_window(self):
        target = (bt.TARGET_VA, bt.TARGET_VA + bt.FUNCTION_SIZE)
        for va, size in (bt.FROZEN_LATE_WINDOWS + bt.FROZEN_HISTORICAL_WINDOWS):
            self.assertFalse(cp.windows_overlap(target, (va, va + size)),
                             f"overlap with {hex(va)}+{size}")

    def test_frozen_payload_sha_rejected(self):
        for sha in ("28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",
                    "aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",
                    "1e209f98ba86d03a2c8df65f69152efd8d1f32b575356428d87989a83c306687"):
            with self.assertRaisesRegex(ValueError, "RERUN_FORBIDDEN_FROZEN_PAYLOAD"):
                bt.require_fresh_payload(sha)

    def test_fresh_payload_sha_accepted(self):
        bt.require_fresh_payload("0" * 64)


class RoundPadGate(unittest.TestCase):
    def test_bti_c_candidate_passes_round_gate(self):
        entries, ctx, _, _ = synth_world(sizes={0: 64}, entry_words={0: BTI_C})
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["gates"][bt.ROUND_PAD_GATE], "PASS")
        self.assertEqual(record["entry_pad"], "bti c")
        self.assertFalse(record["pac"])
        self.assertTrue(record["bti"])
        self.assertEqual(record["window"], 60)
        self.assertEqual(record["core_size"], 56)
        self.assertEqual(record["probe_architecture"], bt.PROBE_ARCHITECTURE)

    def test_paciasp_candidate_rejected_reversed_polarity(self):
        entries, ctx, _, _ = synth_world(sizes={0: 64})
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"][bt.ROUND_PAD_GATE].startswith("FAIL"))
        self.assertIn(bt.ROUND_PAD_REASON, record["fail_reasons"])
        for gate in ll.GATES:  # the frozen 15 gates themselves stay green
            self.assertEqual(record["gates"][gate], "PASS", gate)

    def test_bti_variant_pads_rejected(self):
        for word in (0xD503241F, 0xD503249F, 0xD50324DF):
            with self.subTest(word=hex(word)):
                entries, ctx, _, _ = synth_world(sizes={0: 64}, entry_words={0: word})
                record = bt.audit_candidate_btic(entries[0], ctx)
                self.assertFalse(record["PASS"])
                self.assertTrue(record["gates"]["ENTRY_PAD"].startswith("FAIL"))
                self.assertTrue(record["gates"][bt.ROUND_PAD_GATE].startswith("FAIL"))
                self.assertIn(bt.ROUND_PAD_REASON, record["fail_reasons"])
                self.assertFalse(record["bti"])


class WindowDerivation(unittest.TestCase):
    def test_derived_window_60_accepted(self):
        entries, ctx, _, _ = synth_world(sizes={0: 64}, entry_words={0: BTI_C})
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertEqual(record["gates"]["WINDOW_FIT"], "PASS", record["gates"])
        self.assertEqual(record["window"], 60)

    def test_derived_window_64_rejected_loudly(self):
        # R1: a tail word branching back into [entry+4, entry+60) must fail
        # loudly, never widen the overwrite nor silently stay at 60.
        entries, ctx, targets, offsets = synth_world(sizes={0: 64},
                                                     entry_words={0: BTI_C})
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, offsets[0] + 60,
                         encode_b(targets[0] + 60, targets[0] + 20))
        ctx["frozen"] = bytes(image)
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertEqual(record["gates"]["WINDOW_FIT"],
                         "FAIL:WINDOW_DERIVATION_64_INCOMPATIBLE_BTIC_FAMILY")
        self.assertIn("WINDOW_DERIVATION_64_INCOMPATIBLE_BTIC_FAMILY",
                      record["fail_reasons"])
        for gate in ll.GATES:
            if gate != "WINDOW_FIT":
                self.assertEqual(record["gates"][gate], "PASS", gate)

    def test_function_too_small_rejected(self):
        expectations = {48: ["FUNCTION_TOO_SMALL", "PINNED_FUNCTION_SIZE_NOT_64"],
                        56: ["WINDOW_DERIVATION_NOT_60", "PINNED_FUNCTION_SIZE_NOT_64"],
                        60: ["PINNED_FUNCTION_SIZE_NOT_64"]}
        for size, reasons in expectations.items():
            with self.subTest(size=size):
                entries, ctx, _, _ = synth_world(sizes={0: size}, entry_words={0: BTI_C})
                record = bt.audit_candidate_btic(entries[0], ctx)
                self.assertFalse(record["PASS"])
                for reason in reasons:
                    self.assertIn(reason, record["fail_reasons"])


class PinnedSelection(unittest.TestCase):
    def test_pinned_target_selects_51_without_walk(self):
        entries, ctx = pinned_world()
        selection = bt.pin_target(entries, ctx)
        self.assertEqual(selection["selected_index"], 51)
        self.assertEqual(selection["nominal_index"], 51)
        self.assertIsNone(selection["deviation"])
        self.assertEqual(selection["interval_walk"], "NONE_TARGET_PINNED_DIRECTLY")
        self.assertEqual(selection["skipped"], [])
        audit = selection["audit"]
        self.assertEqual(audit["index"], 51)
        self.assertEqual(audit["symbol"], "setup_vcpu_hotplug_event")
        self.assertEqual(audit["target_va"], hex(bt.TARGET_VA))
        self.assertEqual(audit["table_entry_va"], hex(bt.TABLE_VA))
        self.assertEqual(audit["image_offset"], hex(bt.IMAGE_OFFSET))
        self.assertEqual(audit["entry_pad"], "bti c")
        self.assertFalse(audit["pac"])
        self.assertTrue(audit["bti"])
        self.assertTrue(audit["PASS"], audit["gates"])
        core56 = CORE56
        members = {}
        for delay in (8, 1):
            probe, payload = ll.compose_member(ctx["frozen"], bt.IMAGE_OFFSET,
                                               bt.WINDOW, bt.BTI_C, core56, delay)
            bt.gate_composed_window(probe, bt.BTI_C, bt.DELAY_WORDS[delay])
            bt.gate_composed_control_flow(probe, bt.TARGET_VA)
            bt.require_member_scope(payload, ctx["frozen"], bt.IMAGE_OFFSET,
                                    bt.WINDOW)
            bt.require_prel32_unchanged(payload, ctx["frozen"], bt.TABLE_IMAGE_OFFSET)
            members[delay] = (probe, payload)
        changed = [i for i, (a, b) in enumerate(zip(members[8][1], members[1][1]))
                   if a != b]
        ll.assert_pair_delay_only(changed, bt.IMAGE_OFFSET, bt.CORE_SIZE)
        self.assertEqual(changed, bt.PAIR_DIFF_OFFSETS)
        bti = bt.bti_semantics({delay: members[delay][0] for delay in members},
                               ctx["frozen"], bt.IMAGE_OFFSET, ctx["cfg"])
        self.assertEqual(bti["BTI_C_ENTRY_SEMANTICS_PASS"], "YES")
        self.assertEqual(bti["KERNEL_BTI_KERNEL_CONFIG"], "y")
        self.assertEqual(bti["INITCALL_DISPATCH_CALL_CLASS"], "BLR_CONTROLLED")
        tail = bt.IMAGE_OFFSET + bt.WINDOW
        for _, payload in members.values():
            self.assertEqual(payload[tail:tail + bt.TAIL_BYTES],
                             ctx["frozen"][tail:tail + bt.TAIL_BYTES])
            self.assertEqual(payload[tail:tail + bt.TAIL_BYTES], struct.pack("<I", RET))

    def test_text_target_rejected(self):
        entries, ctx, _, _ = synth_world(sizes={0: 64}, entry_words={0: BTI_C})
        entries[0]["section"] = ".text"
        entries[0]["init_text"] = False
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["INIT_TEXT"].startswith("FAIL"))
        self.assertTrue(any(reason.startswith("TARGET_NOT_INIT_TEXT")
                            for reason in record["fail_reasons"]))

    def test_frozen_window_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, "FROZEN_WINDOW_OVERLAP"):
            bt.require_frozen_window_disjoint(0xFFFF800081B72F14, 60)
        with self.assertRaisesRegex(ValueError, "FROZEN_WINDOW_OVERLAP"):
            bt.require_frozen_window_disjoint(0xFFFF800081B72F14 + 8, 4)
        bt.require_frozen_window_disjoint(bt.TARGET_VA, bt.FUNCTION_SIZE)

    def test_interior_incoming_target_rejected(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 64},
                                                     entry_words={0: BTI_C})
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, offsets[1] + 4,
                         encode_b(TEXT_VA + offsets[1] + 4, targets[0] + 8))
        ctx["frozen"] = bytes(image)
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["INCOMING_BRANCH"].startswith("FAIL"))
        self.assertIn("INCOMING_WINDOW_INTERIOR_BRANCH", record["fail_reasons"])

    def test_incoming_into_unscanned_tail_rejected(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 64},
                                                     entry_words={0: BTI_C})
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, offsets[1] + 4,
                         encode_b(TEXT_VA + offsets[1] + 4, targets[0] + 60))
        ctx["frozen"] = bytes(image)
        record = bt.audit_candidate_btic(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertEqual(record["gates"]["WINDOW_FIT"], "PASS")
        self.assertTrue(record["gates"]["INCOMING_BRANCH"].startswith("FAIL"))
        self.assertIn("INCOMING_WINDOW_INTERIOR_BRANCH", record["fail_reasons"])


class ComposedWindow(unittest.TestCase):
    def test_composed_window_identity_and_control_flow(self):
        for delay, word in bt.DELAY_WORDS.items():
            with self.subTest(delay=delay):
                probe = probe_for(delay)
                bt.gate_composed_window(probe, BTI_C, word)
                bt.gate_composed_control_flow(probe, bt.TARGET_VA)
        with self.assertRaisesRegex(ValueError, "COMPOSED_CORE_WORD_DRIFT"):
            bt.gate_composed_window(probe_for(8), BTI_C, bt.DELAY_WORDS[1])

    def test_bti_c_word_rewritten_rejected(self):
        for word in (NOP, PACIASP, RET):
            with self.subTest(word=hex(word)):
                with self.assertRaisesRegex(ValueError, "BTI_C_ENTRY_WORD_REWRITTEN"):
                    bt.gate_composed_window(probe_for(8, entry_word=word), word,
                                            bt.DELAY_WORDS[8])

    def test_bti_c_missing_rejected(self):
        with self.assertRaisesRegex(ValueError, "BTI_C_ENTRY_WORD_REWRITTEN"):
            bt.gate_composed_window(bytes(bt.WINDOW), 0, bt.DELAY_WORDS[8])
        with self.assertRaisesRegex(ValueError, "COMPOSED_WINDOW_SIZE"):
            bt.gate_composed_window(CORE56, BTI_C, bt.DELAY_WORDS[8])

    def test_pad_class_not_bti_c_rejected(self):
        with self.assertRaisesRegex(ValueError, "BTI_C_ENTRY_WORD_REWRITTEN"):
            bt.gate_composed_window(probe_for(8, entry_word=PACIASP), PACIASP,
                                    bt.DELAY_WORDS[8])

    def test_pac_hint_word_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 4, 0xD50323C0)  # PAC/AUT hint class, Rd=0
        self.assertEqual(struct.unpack_from("<I", probe, 4)[0] & bt.PAC_HINT_MASK,
                         bt.PAC_HINT_BASE)
        frozen = small_frozen()
        with self.assertRaisesRegex(ValueError, "PAC_HINT_IN_COMPOSED_WINDOW"):
            bt.bti_semantics({8: bytes(probe)}, frozen, SMALL_OFFSET,
                             {"CONFIG_ARM64_BTI_KERNEL": "y"})

    def test_ret_in_diagnostic_path_rejected(self):
        frozen = small_frozen()
        for word, reason in ((RET, "RET_IN_DIAGNOSTIC_PATH"),
                             (0xD63F0BC0, "INDIRECT_CALL_IN_DIAGNOSTIC_PATH"),
                             (0xD63F0FC0, "INDIRECT_CALL_IN_DIAGNOSTIC_PATH")):
            with self.subTest(word=hex(word)):
                probe = bytearray(probe_for(8))
                struct.pack_into("<I", probe, 12, word)  # delay slot
                with self.assertRaisesRegex(ValueError, reason):
                    bt.bti_semantics({8: bytes(probe)}, frozen, SMALL_OFFSET,
                                     {"CONFIG_ARM64_BTI_KERNEL": "y"})

    def test_tail_reenters_diagnostic_path_rejected(self):
        entry = bt.TARGET_VA
        cases = [
            ("COMPOSED_TERMINAL_NOT_UNCONDITIONAL_B",
             probe_for(8)[:56] + struct.pack("<I", NOP)),
            ("COMPOSED_TERMINAL_NOT_UNCONDITIONAL_B",
             probe_for(8)[:56] + struct.pack("<I", encode_b(entry + 56, entry + 24))),
            ("COMPOSED_BRANCH_REACHES_TAIL",
             probe_for(8)[:40] + struct.pack("<I", encode_b(entry + 40, entry + 60))
             + probe_for(8)[44:]),
            ("COMPOSED_LOOP_HEAD_DRIFT",
             probe_for(8)[:36] + struct.pack("<I", encode_b(entry + 36, entry + 24))
             + probe_for(8)[40:]),
        ]
        for reason, probe in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, reason):
                    bt.gate_composed_control_flow(probe, entry)


class PairComposition(unittest.TestCase):
    def test_pair_diff_is_delay_constant_only(self):
        frozen = small_frozen()
        members = compose_pair(frozen, SMALL_OFFSET)
        probe8, payload8 = members[8]
        probe1, payload1 = members[1]
        self.assertEqual(len(probe8), 60)
        self.assertEqual(probe8[:4], struct.pack("<I", BTI_C))
        changed = [i for i, (a, b) in enumerate(zip(payload8, payload1)) if a != b]
        ll.assert_pair_delay_only(changed, SMALL_OFFSET, bt.CORE_SIZE)
        self.assertEqual(changed, [SMALL_OFFSET + 13, SMALL_OFFSET + 14])
        self.assertEqual(struct.unpack_from("<I", payload8, SMALL_OFFSET + 12)[0],
                         0xD37DF12A)
        self.assertEqual(struct.unpack_from("<I", payload1, SMALL_OFFSET + 12)[0],
                         0xD340FD2A)

    def test_extra_pair_diff_rejected(self):
        frozen = small_frozen()
        _, payload1 = compose_pair(frozen, SMALL_OFFSET)[1]
        extra_inside = bytearray(payload1)
        extra_inside[SMALL_OFFSET + 20] ^= 0xFF
        changed = [i for i, (a, b) in enumerate(zip(bytes(extra_inside), payload1))
                   if a != b]
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_CONSTANT_ONLY"):
            ll.assert_pair_delay_only(changed, SMALL_OFFSET, bt.CORE_SIZE)
        outside = bytearray(payload1)
        outside[SMALL_OFFSET + 70] ^= 0xFF
        changed = [i for i, (a, b) in enumerate(zip(bytes(outside), payload1))
                   if a != b]
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_CONSTANT_ONLY"):
            ll.assert_pair_delay_only(changed, SMALL_OFFSET, bt.CORE_SIZE)

    def test_member_changes_only_inside_window(self):
        frozen = small_frozen()
        for probe, payload in compose_pair(frozen, SMALL_OFFSET).values():
            diffs = bt.require_member_scope(payload, frozen, SMALL_OFFSET, bt.WINDOW)
            self.assertTrue(all(SMALL_OFFSET + 4 <= i < SMALL_OFFSET + bt.WINDOW
                                for i in diffs))
            self.assertEqual(payload[:SMALL_OFFSET], frozen[:SMALL_OFFSET])
            self.assertEqual(payload[SMALL_OFFSET + bt.WINDOW:],
                             frozen[SMALL_OFFSET + bt.WINDOW:])

    def test_member_changes_outside_window_rejected(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        bad = bytearray(payload)
        bad[SMALL_OFFSET - 4] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "MEMBER_CHANGED_OUTSIDE_WINDOW"):
            bt.require_member_scope(bytes(bad), frozen, SMALL_OFFSET, bt.WINDOW)
        bad = bytearray(payload)
        bad[SMALL_OFFSET + bt.WINDOW] ^= 0xFF  # tail byte
        with self.assertRaisesRegex(ValueError, "TAIL_BYTES_MODIFIED"):
            bt.require_member_scope(bytes(bad), frozen, SMALL_OFFSET, bt.WINDOW)
        bad = bytearray(payload)
        bad[SMALL_OFFSET + 2] ^= 0xFF  # pad byte
        with self.assertRaisesRegex(ValueError, "BTI_C_PAD_MODIFIED"):
            bt.require_member_scope(bytes(bad), frozen, SMALL_OFFSET, bt.WINDOW)

    def test_tail_bytes_original_in_members(self):
        frozen = small_frozen()
        tail = SMALL_OFFSET + bt.WINDOW
        for _, payload in compose_pair(frozen, SMALL_OFFSET).values():
            self.assertEqual(payload[tail:tail + bt.TAIL_BYTES],
                             frozen[tail:tail + bt.TAIL_BYTES])
            self.assertEqual(payload[tail:tail + bt.TAIL_BYTES], struct.pack("<I", RET))

    def test_prel32_unchanged_accepted(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        bt.require_prel32_unchanged(payload, frozen, 0x300)

    def test_prel32_change_rejected(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        bad = bytearray(payload)
        struct.pack_into("<I", bad, 0x300, 0xFFE7AD8C ^ 0xFFFF)
        with self.assertRaisesRegex(ValueError, "PREL32_TARGET_REWRITTEN"):
            bt.require_prel32_unchanged(bytes(bad), frozen, 0x300)


class InlineArchitecture(unittest.TestCase):
    def test_trampoline_island_rejected(self):
        for architecture in ("ENTRY_TRAMPOLINE", "ISLAND", "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT"):
            with self.subTest(architecture=architecture):
                with self.assertRaisesRegex(ValueError, "NOT_INLINE_BTI_C_FAMILY"):
                    bt.require_inline_probe_architecture(architecture)
        bt.require_inline_probe_architecture(bt.PROBE_ARCHITECTURE)


class ReferencesAndConfig(unittest.TestCase):
    def test_absolute_low32_scan_detects_tail_va(self):
        vma = TEXT_VA + 0x500000
        tail_hit = struct.pack("<I", (bt.TARGET_VA + 60) & 0xFFFFFFFF)
        benign = struct.pack("<I", 0xFFE7AD8C)
        sections = [{"name": "__jump_table", "vma": vma, "bytes": tail_hit + benign}]
        # tail span call: the only word of [tail, tail+4) must be caught
        hits = bt.absolute_low32_scan(sections, bt.TARGET_VA + 60, bt.TAIL_BYTES)
        self.assertEqual(hits, [f"__jump_table@{hex(vma)}"])
        # diagnostic window call: benign low-32 values stay clean
        self.assertEqual(bt.absolute_low32_scan(
            [{"name": "__jump_table", "vma": vma, "bytes": benign + benign}],
            bt.TARGET_VA, bt.WINDOW), [])

    def test_bti_config_data_keys(self):
        frozen = small_frozen()
        bti = bt.bti_semantics({8: probe_for(8)}, frozen, SMALL_OFFSET,
                               {"CONFIG_ARM64_BTI_KERNEL": "y"})
        self.assertEqual(bti["KERNEL_BTI_KERNEL_CONFIG"], "y")
        self.assertEqual(bti["KERNEL_BTI_CONFIG"], "ABSENT")
        self.assertEqual(bti["KERNEL_BTI_CONFIG_CONFIRMED"], "YES")
        with self.assertRaisesRegex(ValueError, "KERNEL_CONFIG_NOT_READ"):
            bt.bti_semantics({8: probe_for(8)}, frozen, SMALL_OFFSET, {})


class SummaryKeys(unittest.TestCase):
    def names_fixture(self):
        audit = {"index": 51, "symbol": "setup_vcpu_hotplug_event",
                 "table_entry_va": hex(bt.TABLE_VA), "target_va": hex(bt.TARGET_VA),
                 "image_offset": hex(bt.IMAGE_OFFSET), "function_size": 64,
                 "window": 60, "core_size": 56, "entry_pad": "bti c",
                 "registration": "late_initcall(setup_vcpu_hotplug_event)",
                 "source": "drivers/xen/cpu_hotplug.c"}
        bti = {"BTI_C_ENTRY_WORD_EXACT": "YES", "LANDING_PAD_CLASS_UNCHANGED": "YES",
               "BTI_PAD_NOT_DELETED": "YES", "PAC_INDEPENDENCE": "YES",
               "NO_RET_IN_DIAGNOSTIC_PATH": "YES", "LR_RESTORATION_NOT_REQUIRED": "YES",
               "SMC_ROUND_TRIP_BTI_SAFE": "YES",
               "INITCALL_DISPATCH_CALL_CLASS": "BLR_CONTROLLED",
               "INITCALL_DISPATCH_CITATION": bt.INITCALL_DISPATCH_CITATION,
               "KERNEL_BTI_CONFIG_CONFIRMED": "YES", "KERNEL_BTI_KERNEL_CONFIG": "y",
               "KERNEL_BTI_CONFIG": "ABSENT", "BTI_C_ENTRY_SEMANTICS_PASS": "YES"}
        return {bt.FAMILY: {"label": "BTIC51", "audit": audit, "bti": bti,
                            "shas": {8: "a" * 64, 1: "b" * 64},
                            "changed": [28864829, 28864830],
                            "agreement": "EXACT"}}

    def test_summary_contains_btic51_and_tail_gates(self):
        info = self.names_fixture()
        lines = bt.summary_kv(info, list(range(86)),
                              {"init_text": 82, "text_section": 4},
                              info[bt.FAMILY]["bti"], "EXACT")
        text = "\n".join(lines)
        for line in (
                f"LATE_LEVEL_POST50_STAGE={bt.STAGE}",
                "LATE_SPAN=__initcall7_start..__initcall_end",
                "LATE_TABLE_ENTRY_COUNT=86",
                "LATE_TABLE_INDEX0_SYMBOL=kernel_do_mounts_initrd_sysctls_init",
                "LATE_TABLE_INDEX0_TABLE_VA=0xffff800081d0c2d8",
                "LATE_TABLE_INDEX0_TARGET_VA=0xffff800081b32078",
                "LATE_TABLE_INDEX0_WORD=0xffe25da0",
                "ROUND_PAD_CLASS=BTI_C_ONLY",
                "FROZEN_INDICES_EXCLUDED=0,21,43,49,50,55,63",
                "FROZEN_WINDOW_DISJOINT=YES", "FROZEN_PAYLOAD_DISJOINT=YES",
                "HIGH8_STATIC_PROBE_DEFECT_FOUND=NO",
                "HIGH8_FORENSIC_RUNTIME_INFERENCE=NONE",
                "BTIC51_NOMINAL_INDEX=51", "BTIC51_INDEX=51",
                "BTIC51_SYMBOL=setup_vcpu_hotplug_event",
                "BTIC51_TABLE_VA=0xffff800081d0c3a4",
                "BTIC51_TARGET_VA=0xffff800081b87130",
                "BTIC51_IMAGE_OFFSET=0x1b87130",
                "BTIC51_FUNCTION_SIZE=64", "BTIC51_WINDOW=60",
                "BTIC51_CORE_SIZE=56",
                "BTIC51_PROBE_ARCHITECTURE=BTI_C_PLUS_56B_ULTRACOMPACT",
                "BTIC51_ENTRY_PAD=bti c",
                "BTIC51_REGISTRATION=late_initcall(setup_vcpu_hotplug_event)",
                "BTIC51_SOURCE=drivers/xen/cpu_hotplug.c",
                "BTIC51_DEVIATION=NONE",
                "BTIC51_8_PAYLOAD_SHA=" + "a" * 64,
                "BTIC51_1_PAYLOAD_SHA=" + "b" * 64,
                "BTIC51_PAIR_DIFF_OFFSETS=[28864829, 28864830]",
                "BTIC51_PAIR=PASS",
                "TAIL_BYTES=4", "TAIL_BYTES_ORIGINAL=YES",
                "TAIL_NO_INCOMING_TARGET=YES", "TAIL_NOT_ON_DIAGNOSTIC_PATH=YES",
                "TAIL_NO_PRESERVED_SEMANTICS=YES", "TAIL_BTI_NEUTRAL=YES",
                "TAIL_REACHABILITY=DEAD_PROVEN",
                "BTI_C_ENTRY_WORD_EXACT=YES", "LANDING_PAD_CLASS_UNCHANGED=YES",
                "BTI_PAD_NOT_DELETED=YES", "PAC_INDEPENDENCE=YES",
                "NO_RET_IN_DIAGNOSTIC_PATH=YES", "LR_RESTORATION_NOT_REQUIRED=YES",
                "SMC_ROUND_TRIP_BTI_SAFE=YES",
                "INITCALL_DISPATCH_CALL_CLASS=BLR_CONTROLLED",
                f"INITCALL_DISPATCH_CITATION={bt.INITCALL_DISPATCH_CITATION}",
                "KERNEL_BTI_CONFIG_CONFIRMED=YES", "KERNEL_BTI_KERNEL_CONFIG=y",
                "BTI_C_ENTRY_SEMANTICS_PASS=YES",
                "MEMBER_CHANGES_ONLY_INSIDE_WINDOW=YES",
                "WINDOW_AGREEMENT_INDEX51=EXACT",
                "PAIR_DIFF=DELAY_CONSTANT_ONLY", "INLINE_ONLY=YES",
                "TRAMPOLINE_PERMITTED=NO", "ISLAND_PERMITTED=NO",
                "PREL32_TARGET_UNCHANGED=YES", "SHARED_CHECKPOINT=NO",
                "CROSS_FUNCTION_OVERWRITE=NO", "WINDOW_DERIVATION=TARGET_CFG",
                "KERNEL_REBUILD=NO", "DEVICE_OPERATION=NO", "PRIVATE_PACK=NO",
                "PARTITION_WRITES=0", "SLOT_A_WRITTEN=NO", "LOCAL_BUILD=NO"):
            self.assertIn(line, text)


if __name__ == "__main__":
    unittest.main()
