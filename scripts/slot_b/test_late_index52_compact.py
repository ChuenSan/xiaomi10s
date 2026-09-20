"""Unit tests for the late index-52 COMPACT_INLINE_48B probe authorization round.

Pure Python only: synthetic fixtures plus the tracked reference late-table.json
(artifacts/slot-b-post-initcalls-20260919). No kernel build, no binaries.
Runs locally too: checkpoint imports are CI-gated, so the gate environment is
opted in read-only before the imports.

Reversed pad polarity vs the btic51 predecessor: the entry MUST be exactly
`paciasp`; a `bti c`/`bti j`/`bti jc` pad FAILs with a distinct reason token.
The 44-byte DELETE-ONLY core (CORE44) drops `msr daifset`, the loop `isb`, and
the terminal `wfe`; the 4-byte function tail is absorbed because the 48-byte
window IS the whole function (TAIL_BYTES=0).
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
import late_index52_compact as ct

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / ("artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/"
                    "audit/late-table.json")
TEXT_VA = ll.TEXT_VA
ENTRY_BASE_VA = ll.FROZEN_INDEX0["entry_va"]
NOP = 0xD503201F
RET = 0xD65F03C0
PACIASP = 0xD503233F
BTI_C = 0xD503245F
CORE44 = struct.pack("<11I", *ct.CORE44_WORDS_8S)
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
    """World where index 52 carries the frozen identity of
    boot_wait_for_devices (real target VA, image offset and table slot)."""
    image_len = ct.TABLE_IMAGE_OFFSET + 4
    image = bytearray(struct.pack("<I", NOP) * image_len)
    struct.pack_into("<I", image, ct.IMAGE_OFFSET, PACIASP)
    struct.pack_into("<I", image, ct.IMAGE_OFFSET + ct.FUNCTION_SIZE - 4, tail_word)
    struct.pack_into("<I", image, ct.TABLE_IMAGE_OFFSET, ct.TABLE_WORD)
    ctx = {"frozen": bytes(image), "image": bytes(image), "image_len": image_len,
           "text_va": TEXT_VA,
           "sections": [{"name": ".init.text", "vma": TEXT_VA, "size": image_len,
                         "code": True, "alloc": True}],
           "ranges": [(ct.IMAGE_OFFSET - 0x100, ct.IMAGE_OFFSET + 0x100)],
           "symbol_vas": sorted({ct.TARGET_VA, ct.TARGET_VA + ct.FUNCTION_SIZE}),
           "rw_sites": {tag: [] for _, tag, _ in cp.t3.RUNTIME_REWRITE_SECTIONS},
           "reloc_sites": [], "image_size": image_len,
           "cfg": {"CONFIG_ARM64_BTI_KERNEL": "y"}}
    entries = [synth_entry(index, TEXT_VA + 0x100 + 64 * index, 64)
               for index in range(ll.SPAN_COUNT)]
    entries[ct.PINNED_INDEX] = synth_entry(
        ct.PINNED_INDEX, ct.TARGET_VA, ct.FUNCTION_SIZE,
        symbol=ct.FROZEN_TARGET["symbol"], source=ct.FROZEN_TARGET["source"])
    return entries, ctx


def small_frozen():
    """Frozen base with a paciasp entry at SMALL_OFFSET and a ret tail."""
    image = bytearray(struct.pack("<I", NOP) * 0x4000)
    struct.pack_into("<I", image, SMALL_OFFSET, PACIASP)
    struct.pack_into("<I", image, SMALL_OFFSET + ct.WINDOW, RET)
    return bytes(image)


def compose_pair(frozen, offset, entry_word=PACIASP, core=CORE44):
    members = {}
    for delay in (8, 1):
        members[delay] = ct.compose_member_44(frozen, offset, ct.WINDOW, entry_word,
                                              core, delay)
    return members


def probe_for(delay, entry_word=PACIASP, core=CORE44):
    core = bytearray(core)
    struct.pack_into("<I", core, 4, ct.DELAY_WORDS[delay])
    return struct.pack("<I", entry_word) + bytes(core)


def encode_b(src, dst):
    return 0x14000000 | (((dst - src) // 4) & 0x03FFFFFF)


class PinnedIdentity(unittest.TestCase):
    def test_reference_row_52_matches_frozen_identity(self):
        rows = load_reference()
        self.assertEqual(rows[50]["symbol"], "clk_debug_init")
        row = rows[52]
        self.assertEqual(row["symbol"], ct.FROZEN_TARGET["symbol"])
        self.assertEqual(row["entry_va"], ct.TABLE_VA)
        self.assertEqual(row["entry_word"], hex(ct.TABLE_WORD))
        self.assertEqual(row["target_va"], ct.TARGET_VA)
        self.assertEqual(row["target_va"], row["entry_va"] + row["relative"])

    def test_pinned_target_constants(self):
        self.assertEqual(ct.FROZEN_TARGET["image_offset"], hex(ct.IMAGE_OFFSET))
        self.assertEqual(ct.IMAGE_OFFSET, 0x1B87EC8)
        self.assertEqual(ct.TABLE_IMAGE_OFFSET, 0x1D0C3A8)
        self.assertEqual(ct.TABLE_WORD, 0xFFE7BB20)
        self.assertEqual((ct.FUNCTION_SIZE, ct.WINDOW, ct.TAIL_BYTES), (48, 48, 0))
        self.assertEqual(ct.CORE_SIZE, 44)
        self.assertEqual(ct.PROBE_ARCHITECTURE, "COMPACT_INLINE_48B")
        self.assertEqual(ct.DELAY_WORDS, {8: 0xD37DF12A, 1: 0xD340FD2A})
        # pair-diff at byte offsets 9,10 of the window (delay word at window +8)
        self.assertEqual(ct.PAIR_DIFF_OFFSETS,
                         [ct.IMAGE_OFFSET + 8 + 1, ct.IMAGE_OFFSET + 8 + 2])
        self.assertEqual(ct.PAIR_DIFF_OFFSETS, [28868305, 28868306])
        self.assertEqual(ct.FROZEN_LATE_INDICES, (0, 21, 43, 49, 50, 51, 55, 63))
        self.assertEqual(ct.ROUND_PAD_VALUE, "PACIASP_ONLY")
        self.assertEqual(ct.CORE44_SHA,
                         "ecc9dd48420d082cf2cfa0c184d65407e77813069bdfac1a2b117f809389ff7e")
        self.assertEqual(cp.digest(CORE44), ct.CORE44_SHA)
        # 1s variant differs only in the delay word, at exactly two byte offsets
        w8 = struct.pack("<11I", *ct.CORE44_WORDS_8S)
        w1 = struct.pack("<11I", *ct.CORE44_WORDS_1S)
        self.assertEqual(len(w8), 44)
        diffs = [i for i, (a, b) in enumerate(zip(w8, w1)) if a != b]
        # core-only diff sits at core byte offsets 5,6 (delay word at core +4);
        # the composed-payload diff is at window offsets 9,10 (core +4 pad).
        self.assertEqual(diffs, [5, 6])


class FrozenRegistry(unittest.TestCase):
    def test_frozen_registry_covers_post50_additively(self):
        self.assertEqual(len(ct.FROZEN_PAYLOAD_SHAS), 16)
        self.assertEqual(len(ct.FROZEN_PAYLOAD_SHAS) - 4, len(lp.FROZEN_PAYLOAD_SHAS))
        self.assertIn("28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",
                      ct.FROZEN_PAYLOAD_SHAS)
        self.assertIn("aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",
                      ct.FROZEN_PAYLOAD_SHAS)
        self.assertIn("ae437348164e2ccaa47e4ba238576b6ab05bfda23bd63f18bda48f161b3f88ef",
                      ct.FROZEN_PAYLOAD_SHAS)
        self.assertIn("49b9499d2656b7b8b16d39dc9863eb743a1e570a5ee544aea95b6a3a6b4f920e",
                      ct.FROZEN_PAYLOAD_SHAS)
        self.assertEqual(len(ct.FROZEN_LATE_WINDOWS), 9)
        self.assertIn((0xFFFF800081B72F14, 60), ct.FROZEN_LATE_WINDOWS)  # POST50
        self.assertIn((0xFFFF800081B87130, 60), ct.FROZEN_LATE_WINDOWS)  # BTIC51
        self.assertEqual(len(ct.FROZEN_HISTORICAL_WINDOWS), 11)

    def test_frozen_window_overlap_detector(self):
        self.assertIsNotNone(ct.frozen_window_overlap(0xFFFF800081B72F14, 60))
        self.assertIsNotNone(ct.frozen_window_overlap(0xFFFF800081B72F14 + 8, 60))
        self.assertIsNone(ct.frozen_window_overlap(0xFFFF800081B72F14 + 60, 60))
        self.assertIsNone(ct.frozen_window_overlap(ct.TARGET_VA, 48))
        self.assertIsNone(ct.frozen_window_overlap(ct.TARGET_VA + 48, 48))

    def test_target_window_disjoint_from_every_frozen_window(self):
        target = (ct.TARGET_VA, ct.TARGET_VA + ct.FUNCTION_SIZE)
        for va, size in (ct.FROZEN_LATE_WINDOWS + ct.FROZEN_HISTORICAL_WINDOWS):
            self.assertFalse(cp.windows_overlap(target, (va, va + size)),
                             f"overlap with {hex(va)}+{size}")

    def test_frozen_payload_sha_rejected(self):
        for sha in ("28d1af69c6f39bdbe11c2948470cff9c99c758d2c61b0800127a2bfb7a8fa40b",
                    "aa7605ad5ba5dfdd780e0b277fd0ae3d12686dbba6a16b2ebb99f42702fdc821",
                    "1e209f98ba86d03a2c8df65f69152efd8d1f32b575356428d87989a83c306687"):
            with self.assertRaisesRegex(ValueError, "RERUN_FORBIDDEN_FROZEN_PAYLOAD"):
                ct.require_fresh_payload(sha)

    def test_fresh_payload_sha_accepted(self):
        ct.require_fresh_payload("0" * 64)


class RoundPadGate(unittest.TestCase):
    def test_paciasp_candidate_passes_round_gate(self):
        entries, ctx, _, _ = synth_world(sizes={0: 48}, entry_words={0: PACIASP})
        record = ct.audit_candidate_compact(entries[0], ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["gates"][ct.ROUND_PAD_GATE], "PASS")
        self.assertEqual(record["entry_pad"], "paciasp")
        self.assertTrue(record["pac"])
        self.assertFalse(record["bti"])
        self.assertEqual(record["window"], 48)
        self.assertEqual(record["core_size"], 44)
        self.assertEqual(record["probe_architecture"], ct.PROBE_ARCHITECTURE)

    def test_bti_c_candidate_rejected_reversed_polarity(self):
        entries, ctx, _, _ = synth_world(sizes={0: 48}, entry_words={0: BTI_C})
        record = ct.audit_candidate_compact(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"][ct.ROUND_PAD_GATE].startswith("FAIL"))
        self.assertIn("ROUND_PAD_CLASS_BTI_C_EXCLUDED", record["fail_reasons"])
        for gate in ll.GATES:  # the frozen 15 gates themselves stay green
            self.assertEqual(record["gates"][gate], "PASS", gate)

    def test_bti_variant_pads_rejected(self):
        for word in (0xD503241F, 0xD503249F, 0xD50324DF):
            with self.subTest(word=hex(word)):
                entries, ctx, _, _ = synth_world(sizes={0: 48}, entry_words={0: word})
                record = ct.audit_candidate_compact(entries[0], ctx)
                self.assertFalse(record["PASS"])
                self.assertTrue(record["gates"]["ENTRY_PAD"].startswith("FAIL"))
                self.assertTrue(record["gates"][ct.ROUND_PAD_GATE].startswith("FAIL"))
                self.assertFalse(record["bti"])
                self.assertTrue(
                    any(reason.startswith("ROUND_PAD_CLASS_BTI")
                        for reason in record["fail_reasons"]))


class WindowDerivation(unittest.TestCase):
    def test_derived_window_48_accepted(self):
        entries, ctx, _, _ = synth_world(sizes={0: 48}, entry_words={0: PACIASP})
        record = ct.audit_candidate_compact(entries[0], ctx)
        self.assertEqual(record["gates"]["WINDOW_FIT"], "PASS", record["gates"])
        self.assertEqual(record["window"], 48)

    def test_larger_function_rejected_loudly(self):
        # A function larger than 48 derives a >48 window and must FAIL WINDOW_FIT,
        # never silently widen the overwrite nor stay at 48.
        for size in (56, 64):
            with self.subTest(size=size):
                entries, ctx, _, _ = synth_world(sizes={0: size},
                                                 entry_words={0: PACIASP})
                record = ct.audit_candidate_compact(entries[0], ctx)
                self.assertFalse(record["PASS"])
                self.assertEqual(record["gates"]["WINDOW_FIT"],
                                 "FAIL:WINDOW_DERIVATION_NOT_COMPACT48")
                self.assertIn("WINDOW_DERIVATION_NOT_COMPACT48",
                              record["fail_reasons"])
                for gate in ll.GATES:
                    if gate != "WINDOW_FIT":
                        self.assertEqual(record["gates"][gate], "PASS", gate)

    def test_function_too_small_rejected(self):
        expectations = {44: ["FUNCTION_TOO_SMALL_FOR_COMPACT48"],
                        52: ["WINDOW_DERIVATION_NOT_COMPACT48"],
                        60: ["WINDOW_DERIVATION_NOT_COMPACT48"]}
        for size, reasons in expectations.items():
            with self.subTest(size=size):
                entries, ctx, _, _ = synth_world(sizes={0: size},
                                                 entry_words={0: PACIASP})
                record = ct.audit_candidate_compact(entries[0], ctx)
                self.assertFalse(record["PASS"])
                for reason in reasons:
                    self.assertIn(reason, record["fail_reasons"])


class PinnedSelection(unittest.TestCase):
    def test_pinned_target_selects_52_without_walk(self):
        entries, ctx = pinned_world()
        selection = ct.pin_target(entries, ctx)
        self.assertEqual(selection["selected_index"], 52)
        self.assertEqual(selection["nominal_index"], 52)
        self.assertIsNone(selection["deviation"])
        self.assertEqual(selection["interval_walk"], "NONE_TARGET_PINNED_DIRECTLY")
        self.assertEqual(selection["skipped"], [])
        audit = selection["audit"]
        self.assertEqual(audit["index"], 52)
        self.assertEqual(audit["symbol"], "boot_wait_for_devices")
        self.assertEqual(audit["target_va"], hex(ct.TARGET_VA))
        self.assertEqual(audit["table_entry_va"], hex(ct.TABLE_VA))
        self.assertEqual(audit["image_offset"], hex(ct.IMAGE_OFFSET))
        self.assertEqual(audit["entry_pad"], "paciasp")
        self.assertTrue(audit["pac"])
        self.assertFalse(audit["bti"])
        self.assertTrue(audit["PASS"], audit["gates"])
        members = {}
        for delay in (8, 1):
            probe, payload = ct.compose_member_44(ctx["frozen"], ct.IMAGE_OFFSET,
                                                 ct.WINDOW, ct.PACIASP, CORE44, delay)
            ct.gate_composed_window(probe, ct.PACIASP, ct.DELAY_WORDS[delay])
            ct.gate_composed_control_flow(probe, ct.TARGET_VA)
            ct.require_member_scope(payload, ctx["frozen"], ct.IMAGE_OFFSET,
                                    ct.WINDOW)
            ct.require_prel32_unchanged(payload, ctx["frozen"], ct.TABLE_IMAGE_OFFSET)
            members[delay] = (probe, payload)
        changed = [i for i, (a, b) in enumerate(zip(members[8][1], members[1][1]))
                   if a != b]
        ll.assert_pair_delay_only(changed, ct.IMAGE_OFFSET, ct.CORE_SIZE)
        self.assertEqual(changed, ct.PAIR_DIFF_OFFSETS)
        compact = ct.compact44_semantics(
            {delay: members[delay][0] for delay in members},
            ctx["frozen"], ct.IMAGE_OFFSET, ctx["cfg"])
        self.assertEqual(compact["COMPACT52_ENTRY_SEMANTICS_PASS"], "YES")
        self.assertEqual(compact["KERNEL_BTI_KERNEL_CONFIG"], "y")
        self.assertEqual(compact["INITCALL_DISPATCH_CALL_CLASS"], "BLR_CONTROLLED")
        # TAIL_BYTES=0: the window end equals the function end; no tail bytes.
        tail = ct.IMAGE_OFFSET + ct.WINDOW
        self.assertEqual(tail, ct.IMAGE_OFFSET + ct.FUNCTION_SIZE)

    def test_text_target_rejected(self):
        entries, ctx, _, _ = synth_world(sizes={0: 48}, entry_words={0: PACIASP})
        entries[0]["section"] = ".text"
        entries[0]["init_text"] = False
        record = ct.audit_candidate_compact(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["INIT_TEXT"].startswith("FAIL"))
        self.assertTrue(any(reason.startswith("TARGET_NOT_INIT_TEXT")
                            for reason in record["fail_reasons"]))

    def test_frozen_window_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, "FROZEN_WINDOW_OVERLAP"):
            ct.require_frozen_window_disjoint(0xFFFF800081B72F14, 60)
        with self.assertRaisesRegex(ValueError, "FROZEN_WINDOW_OVERLAP"):
            ct.require_frozen_window_disjoint(0xFFFF800081B72F14 + 8, 4)
        ct.require_frozen_window_disjoint(ct.TARGET_VA, ct.FUNCTION_SIZE)

    def test_interior_incoming_target_rejected(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 48},
                                                     entry_words={0: PACIASP})
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, offsets[1] + 4,
                         encode_b(TEXT_VA + offsets[1] + 4, targets[0] + 8))
        ctx["frozen"] = bytes(image)
        record = ct.audit_candidate_compact(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["INCOMING_BRANCH"].startswith("FAIL"))
        self.assertIn("INCOMING_WINDOW_INTERIOR_BRANCH", record["fail_reasons"])

    def test_incoming_into_window_interior_rejected(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 48},
                                                     entry_words={0: PACIASP})
        image = bytearray(ctx["frozen"])
        struct.pack_into("<I", image, offsets[1] + 4,
                         encode_b(TEXT_VA + offsets[1] + 4, targets[0] + 16))
        ctx["frozen"] = bytes(image)
        record = ct.audit_candidate_compact(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertEqual(record["gates"]["WINDOW_FIT"], "PASS")
        self.assertTrue(record["gates"]["INCOMING_BRANCH"].startswith("FAIL"))
        self.assertIn("INCOMING_WINDOW_INTERIOR_BRANCH", record["fail_reasons"])


class ComposedWindow(unittest.TestCase):
    def test_composed_window_identity_and_control_flow(self):
        for delay, word in ct.DELAY_WORDS.items():
            with self.subTest(delay=delay):
                probe = probe_for(delay)
                ct.gate_composed_window(probe, PACIASP, word)
                ct.gate_composed_control_flow(probe, ct.TARGET_VA)
        with self.assertRaisesRegex(ValueError, "COMPOSED_CORE_WORD_DRIFT"):
            ct.gate_composed_window(probe_for(8), PACIASP, ct.DELAY_WORDS[1])

    def test_paciasp_word_rewritten_rejected(self):
        for word in (NOP, BTI_C, RET):
            with self.subTest(word=hex(word)):
                with self.assertRaisesRegex(ValueError,
                                            "PACIASP_ENTRY_WORD_REWRITTEN"):
                    ct.gate_composed_window(probe_for(8, entry_word=word), word,
                                            ct.DELAY_WORDS[8])

    def test_paciasp_missing_rejected(self):
        with self.assertRaisesRegex(ValueError, "PACIASP_ENTRY_WORD_REWRITTEN"):
            ct.gate_composed_window(bytes(ct.WINDOW), 0, ct.DELAY_WORDS[8])
        with self.assertRaisesRegex(ValueError, "COMPOSED_WINDOW_SIZE"):
            ct.gate_composed_window(CORE44, PACIASP, ct.DELAY_WORDS[8])

    def test_pad_class_not_paciasp_rejected(self):
        with self.assertRaisesRegex(ValueError, "PACIASP_ENTRY_WORD_REWRITTEN"):
            ct.gate_composed_window(probe_for(8, entry_word=BTI_C), BTI_C,
                                    ct.DELAY_WORDS[8])

    def test_pac_hint_word_rejected(self):
        probe = bytearray(probe_for(8))
        struct.pack_into("<I", probe, 4, 0xD50323C0)  # PAC/AUT hint class, Rd=0
        self.assertEqual(struct.unpack_from("<I", probe, 4)[0] & ct.PAC_HINT_MASK,
                         ct.PAC_HINT_BASE)
        frozen = small_frozen()
        with self.assertRaisesRegex(ValueError, "PAC_HINT_IN_COMPOSED_WINDOW"):
            ct.compact44_semantics({8: bytes(probe)}, frozen, SMALL_OFFSET,
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
                    ct.compact44_semantics({8: bytes(probe)}, frozen, SMALL_OFFSET,
                                          {"CONFIG_ARM64_BTI_KERNEL": "y"})

    def test_tail_reenters_diagnostic_path_rejected(self):
        entry = ct.TARGET_VA
        cases = [
            ("COMPOSED_TERMINAL_NOT_SELF_BRANCH",
             probe_for(8)[:44] + struct.pack("<I", NOP)),
            ("COMPOSED_TERMINAL_NOT_SELF_BRANCH",
             probe_for(8)[:44] + struct.pack("<I", encode_b(entry + 44, entry + 16))),
            ("COMPOSED_BRANCH_OUTSIDE_WINDOW",
             probe_for(8)[:36] + struct.pack("<I", encode_b(entry + 36, entry + 60))
             + probe_for(8)[40:]),
            ("COMPOSED_LOOP_HEAD_DRIFT",
             probe_for(8)[:28] + struct.pack("<I", encode_b(entry + 28, entry + 24))
             + probe_for(8)[32:]),
        ]
        for reason, probe in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, reason):
                    ct.gate_composed_control_flow(probe, entry)


class PairComposition(unittest.TestCase):
    def test_pair_diff_is_delay_constant_only(self):
        frozen = small_frozen()
        members = compose_pair(frozen, SMALL_OFFSET)
        probe8, payload8 = members[8]
        probe1, payload1 = members[1]
        self.assertEqual(len(probe8), 48)
        self.assertEqual(probe8[:4], struct.pack("<I", PACIASP))
        changed = [i for i, (a, b) in enumerate(zip(payload8, payload1)) if a != b]
        ll.assert_pair_delay_only(changed, SMALL_OFFSET, ct.CORE_SIZE)
        self.assertEqual(changed, [SMALL_OFFSET + 9, SMALL_OFFSET + 10])
        self.assertEqual(struct.unpack_from("<I", payload8, SMALL_OFFSET + 8)[0],
                         0xD37DF12A)
        self.assertEqual(struct.unpack_from("<I", payload1, SMALL_OFFSET + 8)[0],
                         0xD340FD2A)

    def test_extra_pair_diff_rejected(self):
        frozen = small_frozen()
        _, payload1 = compose_pair(frozen, SMALL_OFFSET)[1]
        extra_inside = bytearray(payload1)
        extra_inside[SMALL_OFFSET + 20] ^= 0xFF
        changed = [i for i, (a, b) in enumerate(zip(bytes(extra_inside), payload1))
                   if a != b]
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_CONSTANT_ONLY"):
            ll.assert_pair_delay_only(changed, SMALL_OFFSET, ct.CORE_SIZE)
        outside = bytearray(payload1)
        outside[SMALL_OFFSET + 60] ^= 0xFF
        changed = [i for i, (a, b) in enumerate(zip(bytes(outside), payload1))
                   if a != b]
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_CONSTANT_ONLY"):
            ll.assert_pair_delay_only(changed, SMALL_OFFSET, ct.CORE_SIZE)

    def test_member_changes_only_inside_window(self):
        frozen = small_frozen()
        for probe, payload in compose_pair(frozen, SMALL_OFFSET).values():
            diffs = ct.require_member_scope(payload, frozen, SMALL_OFFSET, ct.WINDOW)
            self.assertTrue(all(SMALL_OFFSET + 4 <= i < SMALL_OFFSET + ct.WINDOW
                                for i in diffs))
            self.assertEqual(payload[:SMALL_OFFSET], frozen[:SMALL_OFFSET])
            self.assertEqual(payload[SMALL_OFFSET + ct.WINDOW:],
                             frozen[SMALL_OFFSET + ct.WINDOW:])

    def test_member_changes_outside_window_rejected(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        bad = bytearray(payload)
        bad[SMALL_OFFSET - 4] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "MEMBER_CHANGED_OUTSIDE_WINDOW"):
            ct.require_member_scope(bytes(bad), frozen, SMALL_OFFSET, ct.WINDOW)
        bad = bytearray(payload)
        bad[SMALL_OFFSET + 2] ^= 0xFF  # pad byte
        with self.assertRaisesRegex(ValueError, "PACIASP_PAD_MODIFIED"):
            ct.require_member_scope(bytes(bad), frozen, SMALL_OFFSET, ct.WINDOW)

    def test_member_changes_outside_window_after_function_rejected(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        bad = bytearray(payload)
        bad[SMALL_OFFSET + ct.WINDOW] ^= 0xFF  # beyond the whole function
        with self.assertRaisesRegex(ValueError,
                                    "MEMBER_CHANGED_OUTSIDE_WINDOW|"
                                    "COMPACT48_WINDOW_NOT_WHOLE_FUNCTION"):
            ct.require_member_scope(bytes(bad), frozen, SMALL_OFFSET, ct.WINDOW)

    def test_prel32_unchanged_accepted(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        ct.require_prel32_unchanged(payload, frozen, 0x300)

    def test_prel32_change_rejected(self):
        frozen = small_frozen()
        _, payload = compose_pair(frozen, SMALL_OFFSET)[1]
        bad = bytearray(payload)
        struct.pack_into("<I", bad, 0x300, 0xFFE7BB20 ^ 0xFFFF)
        with self.assertRaisesRegex(ValueError, "PREL32_TARGET_REWRITTEN"):
            ct.require_prel32_unchanged(bytes(bad), frozen, 0x300)


class InlineArchitecture(unittest.TestCase):
    def test_trampoline_island_rejected(self):
        for architecture in ("ENTRY_TRAMPOLINE", "ISLAND",
                             "INLINE_BTI_C_PLUS_56B_ULTRACOMPACT",
                             "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT"):
            with self.subTest(architecture=architecture):
                with self.assertRaisesRegex(ValueError, "NOT_INLINE_COMPACT_FAMILY"):
                    ct.require_inline_probe_architecture(architecture)
        ct.require_inline_probe_architecture(ct.PROBE_ARCHITECTURE)


class ReferencesAndConfig(unittest.TestCase):
    def test_absolute_low32_scan_detects_tail_va(self):
        vma = TEXT_VA + 0x500000
        tail_hit = struct.pack("<I", (ct.TARGET_VA + 48) & 0xFFFFFFFF)
        benign = struct.pack("<I", 0xFFE7BB20)
        sections = [{"name": "__jump_table", "vma": vma, "bytes": tail_hit + benign}]
        # whole-function span call: the only word of [td, td+48) must be caught
        hits = ct.absolute_low32_scan(sections, ct.TARGET_VA + 48, ct.FUNCTION_SIZE)
        self.assertEqual(hits, [f"__jump_table@{hex(vma)}"])
        # diagnostic window call: benign low-32 values stay clean
        self.assertEqual(ct.absolute_low32_scan(
            [{"name": "__jump_table", "vma": vma, "bytes": benign + benign}],
            ct.TARGET_VA, ct.WINDOW), [])

    def test_compact_config_data_keys(self):
        frozen = small_frozen()
        compact = ct.compact44_semantics({8: probe_for(8)}, frozen, SMALL_OFFSET,
                                        {"CONFIG_ARM64_BTI_KERNEL": "y"})
        self.assertEqual(compact["KERNEL_BTI_KERNEL_CONFIG"], "y")
        self.assertEqual(compact["KERNEL_BTI_CONFIG"], "ABSENT")
        self.assertEqual(compact["KERNEL_CONFIG_CONFIRMED"], "YES")
        self.assertEqual(compact["COMPACT52_ENTRY_SEMANTICS_PASS"], "YES")
        with self.assertRaisesRegex(ValueError, "KERNEL_CONFIG_NOT_READ"):
            ct.compact44_semantics({8: probe_for(8)}, frozen, SMALL_OFFSET, {})


class SummaryKeys(unittest.TestCase):
    def names_fixture(self):
        audit = {"index": 52, "symbol": "boot_wait_for_devices",
                 "table_entry_va": hex(ct.TABLE_VA), "target_va": hex(ct.TARGET_VA),
                 "image_offset": hex(ct.IMAGE_OFFSET), "function_size": 48,
                 "window": 48, "core_size": 44, "entry_pad": "paciasp",
                 "registration": "late_initcall(boot_wait_for_devices)",
                 "source": "drivers/xen/xenbus/xenbus_probe_frontend.c"}
        compact = {"COMPACT52_ENTRY_PAD_PRESERVED": "YES",
                   "PACIASP_LANDING_PAD_COMPATIBLE": "YES",
                   "NO_RET_IN_WINDOW": "YES",
                   "LR_RESTORATION_NOT_REQUIRED": "YES",
                   "SMC_ROUND_TRIP_SAFE": "YES",
                   "INITCALL_DISPATCH_CALL_CLASS": "BLR_CONTROLLED",
                   "INITCALL_DISPATCH_CITATION": ct.INITCALL_DISPATCH_CITATION,
                   "KERNEL_CONFIG_CONFIRMED": "YES",
                   "KERNEL_BTI_KERNEL_CONFIG": "y",
                   "KERNEL_BTI_CONFIG": "ABSENT",
                   "COMPACT52_ENTRY_SEMANTICS_PASS": "YES"}
        return {ct.FAMILY: {"label": "COMPACT52", "audit": audit,
                            "compact": compact, "shas": {8: "a" * 64, 1: "b" * 64},
                            "changed": [28868305, 28868306],
                            "agreement": "EXACT"}}

    def test_summary_contains_compact52_and_tail_absent_gates(self):
        info = self.names_fixture()
        lines = ct.summary_kv(info, list(range(86)),
                             {"init_text": 82, "text_section": 4},
                             info[ct.FAMILY]["compact"], "EXACT")
        text = "\n".join(lines)
        for line in (
                f"LATE_LEVEL_POST50_STAGE={ct.STAGE}",
                "LATE_SPAN=__initcall7_start..__initcall_end",
                "LATE_TABLE_ENTRY_COUNT=86",
                "LATE_TABLE_INDEX0_SYMBOL=kernel_do_mounts_initrd_sysctls_init",
                "LATE_TABLE_INDEX0_TABLE_VA=0xffff800081d0c2d8",
                "LATE_TABLE_INDEX0_TARGET_VA=0xffff800081b32078",
                "LATE_TABLE_INDEX0_WORD=0xffe25da0",
                "ROUND_PAD_CLASS=PACIASP_ONLY",
                "FROZEN_INDICES_EXCLUDED=0,21,43,49,50,51,55,63",
                "FROZEN_WINDOW_DISJOINT=YES", "FROZEN_PAYLOAD_DISJOINT=YES",
                "HIGH8_STATIC_PROBE_DEFECT_FOUND=NO",
                "HIGH8_FORENSIC_RUNTIME_INFERENCE=NONE",
                "COMPACT52_NOMINAL_INDEX=52", "COMPACT52_INDEX=52",
                "COMPACT52_SYMBOL=boot_wait_for_devices",
                "COMPACT52_TABLE_VA=0xffff800081d0c3a8",
                "COMPACT52_TARGET_VA=0xffff800081b87ec8",
                "COMPACT52_IMAGE_OFFSET=0x1b87ec8",
                "COMPACT52_FUNCTION_SIZE=48", "COMPACT52_WINDOW=48",
                "COMPACT52_CORE_SIZE=44",
                "COMPACT52_PROBE_ARCHITECTURE=COMPACT_INLINE_48B",
                "COMPACT52_ENTRY_PAD=paciasp",
                "COMPACT52_REGISTRATION=late_initcall(boot_wait_for_devices)",
                "COMPACT52_SOURCE=drivers/xen/xenbus/xenbus_probe_frontend.c",
                "COMPACT52_DEVIATION=NONE",
                "COMPACT52_8_PAYLOAD_SHA=" + "a" * 64,
                "COMPACT52_1_PAYLOAD_SHA=" + "b" * 64,
                "COMPACT52_PAIR_DIFF_OFFSETS=[28868305, 28868306]",
                "COMPACT52_PAIR=PASS",
                "TAIL_BYTES=0", "TAIL_PRESENT=NO",
                "TAIL_NO_INCOMING_TARGET=YES", "TAIL_NOT_ON_DIAGNOSTIC_PATH=YES",
                "TAIL_NO_PRESERVED_SEMANTICS=YES", "TAIL_BTI_NEUTRAL=YES",
                "TAIL_REACHABILITY=NO_TAIL_WINDOW_IS_WHOLE_FUNCTION",
                "TOTAL_INLINE_FOOTPRINT=48", "TOTAL_WINDOW_LE_48=YES",
                "MAX_CORE_BYTES=44", "ENTRY_PAD_CLASS=PACIASP",
                "WINDOW_END_IS_FUNCTION_END=YES",
                "FAIL_CLOSED_TERMINAL=YES", "TERMINAL_IS_SELF_BRANCH=YES",
                "RESET_ID_WORD=0x84000009",
                "FAMILY_COLLISION_WITH_FROZEN=NO",
                "FROZEN_FAMILIES_UNCHANGED=PACIASP_PLUS_52B,PACIASP_PLUS_56B,BTI_C_PLUS_56B",
                "DEVICE_BOOT=0", "BOOT_WAIT_FOR_DEVICES_ENTRY=NOT_PROVEN",
                "LATEST_PROVEN_LATE_INDEX=51",
                "COMPACT52_ENTRY_PAD_PRESERVED=YES",
                "PACIASP_LANDING_PAD_COMPATIBLE=YES",
                "NO_RET_IN_WINDOW=YES", "LR_RESTORATION_NOT_REQUIRED=YES",
                "SMC_ROUND_TRIP_SAFE=YES",
                "INITCALL_DISPATCH_CALL_CLASS=BLR_CONTROLLED",
                f"INITCALL_DISPATCH_CITATION={ct.INITCALL_DISPATCH_CITATION}",
                "KERNEL_BTI_KERNEL_CONFIG=y",
                "COMPACT52_ENTRY_SEMANTICS_PASS=YES",
                "KERNEL_CONFIG_CONFIRMED=YES",
                "MEMBER_CHANGES_ONLY_INSIDE_WINDOW=YES",
                "COMPACT52_WINDOW_AGREEMENT=EXACT",
                "WINDOW_AGREEMENT_INDEX52=EXACT",
                "PAIR_DIFF=DELAY_CONSTANT_ONLY", "INLINE_ONLY=YES",
                "TRAMPOLINE_PERMITTED=NO", "ISLAND_PERMITTED=NO",
                "PREL32_TARGET_UNCHANGED=YES", "SHARED_CHECKPOINT=NO",
                "CROSS_FUNCTION_OVERWRITE=NO", "WINDOW_DERIVATION=TARGET_CFG",
                "KERNEL_REBUILD=NO", "DEVICE_OPERATION=NO", "PRIVATE_PACK=NO",
                "PARTITION_WRITES=0", "SLOT_A_WRITTEN=NO", "LOCAL_BUILD=NO"):
            self.assertIn(line, text)


if __name__ == "__main__":
    unittest.main()
