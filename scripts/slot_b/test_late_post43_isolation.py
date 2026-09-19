"""Unit tests for the post-43 late safe-advance round.

Pure Python only: synthetic fixtures plus the tracked reference late-table.json
(artifacts/slot-b-post-initcalls-20260919). No kernel build, no binaries.
"""
from __future__ import annotations

import json
import os
import struct
import unittest
from pathlib import Path
from unittest import mock

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import checkpoint as cp
import late_level_isolation as ll
import late_post43_isolation as lp

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
CORE52 = cp.subsys52_core(struct.pack("<13I", *cp.SUBSYS52_WORDS))


def load_reference():
    assert REFERENCE.is_file(), f"missing reference fixture: {REFERENCE}"
    rows = json.loads(REFERENCE.read_text())
    assert len(rows) == 86, f"reference fixture must hold 86 rows, got {len(rows)}"
    return rows


def synth_entry(index, target, size, section=".init.text", registration="late_initcall",
                symbol=None):
    va = ENTRY_BASE_VA + 4 * index
    relative = target - va
    name = symbol or f"late_sym_{index}"
    return {"index": index, "entry_va": va, "entry_va_hex": hex(va),
            "entry_image_offset": va - TEXT_VA, "entry_word": hex(relative & 0xFFFFFFFF),
            "relative": relative, "target_va": target, "target_va_hex": hex(target),
            "aliases": [name], "symbol": name, "function_size": size,
            "section": section, "init_text": section == ".init.text",
            "target_unique": True, "registration_type": registration,
            "registration": f"{registration}({name})", "source": f"drivers/{index}.c",
            "registration_hits": []}


def synth_world(sizes=None, entry_words=None):
    sizes = sizes or {}
    entry_words = entry_words or {}
    offsets = {}
    cursor = 0x1000
    for index in range(ll.SPAN_COUNT):
        offsets[index] = cursor
        cursor += max(sizes.get(index, 100), 64) + 64
    text_region = cursor + 0x1000
    image_len = text_region + 0x8000
    image = bytearray(struct.pack("<I", NOP) * image_len)
    for index in range(ll.SPAN_COUNT):
        size = sizes.get(index, 100)
        struct.pack_into("<I", image, offsets[index], entry_words.get(index, PACIASP))
        struct.pack_into("<I", image, offsets[index] + size - 4, RET)
    targets = {index: TEXT_VA + offsets[index] for index in offsets}
    entries = [synth_entry(index, targets[index], sizes.get(index, 100))
               for index in range(ll.SPAN_COUNT)]
    symbol_vas = sorted(targets.values()) + [TEXT_VA + image_len]
    sections = [{"name": ".init.text", "vma": TEXT_VA, "size": cursor, "code": True,
                 "alloc": True}]
    ctx = {"frozen": bytes(image), "image": bytes(image), "image_len": image_len,
           "text_va": TEXT_VA, "sections": sections, "ranges": [(0, image_len)],
           "symbol_vas": symbol_vas, "text_region": text_region,
           "rw_sites": {tag: [] for _, tag, _ in cp.t3.RUNTIME_REWRITE_SECTIONS},
           "reloc_sites": [], "image_size": image_len, "cfg": {}}
    return entries, ctx, targets, offsets


def move_to_text_region(entries, ctx, index, size):
    target = TEXT_VA + ctx["text_region"]
    entries[index] = synth_entry(index, target, size, section=".text")
    ctx["sections"].append({"name": ".text", "vma": target, "size": 0x8000,
                            "code": True, "alloc": True})
    ctx["symbol_vas"] = sorted(set(ctx["symbol_vas"]) | {target})
    return target


REAL_SIZES = {43: 112, 44: 32, 45: 24, 46: 40, 47: 44, 48: 112, 49: 408, 50: 288,
              51: 64, 52: 48, 53: 32, 54: 492, 55: 128, 56: 40, 57: 912, 58: 64,
              59: 100, 60: 80, 61: 100, 62: 136, 63: 260, 64: 40}
REAL_BTI = (51, 58, 59)


def real_shaped_world():
    entries, ctx, targets, offsets = synth_world(sizes=REAL_SIZES,
                                                 entry_words={i: BTI_C
                                                              for i in REAL_BTI})
    move_to_text_region(entries, ctx, 53, 32)
    move_to_text_region(entries, ctx, 54, 492)
    return entries, ctx, targets, offsets


class DecoderAndIdentity(unittest.TestCase):
    def test_reference_fixture_present(self):
        rows = load_reference()
        self.assertEqual([row["index"] for row in rows], list(range(86)))

    def test_reference_index0_matches_frozen_identity(self):
        row = load_reference()[0]
        self.assertEqual(row["symbol"], ll.FROZEN_INDEX0["symbol"])
        self.assertEqual(row["target_va"], ll.FROZEN_INDEX0["target_va"])

    def test_reference_table_prel32_self_consistent(self):
        for row in load_reference():
            self.assertEqual(row["target_va"], row["entry_va"] + row["relative"])

    def test_frozen_high8_identity_pinned(self):
        row = load_reference()[63]
        self.assertEqual(row["symbol"], lp.HIGH8_SYMBOL)
        self.assertEqual(row["target_va"], lp.HIGH8_TARGET_VA)
        self.assertIn("c9f160597287666b73004db604c1525786eca5daef2e6fc7d43a647d2896be2d",
                      lp.FROZEN_PAYLOAD_SHAS)
        self.assertIn("c4c4115940159c138ee7742473fc09b852eaeb06e7b81c1e208787edb644a67d",
                      lp.FROZEN_PAYLOAD_SHAS)

    def test_frozen_windows_carry_the_four_late_targets(self):
        for index, (va, _size) in zip((0, 21, 43, 63), lp.FROZEN_LATE_WINDOWS):
            row = load_reference()[index]
            self.assertEqual(row["target_va"], va)
        self.assertEqual(load_reference()[0]["function_size"]
                         if "function_size" in load_reference()[0]
                         else ll.FROZEN_INDEX0["function_size"], 60)


class RoundPadGate(unittest.TestCase):
    def test_paciasp_candidate_passes_round_gate(self):
        entries, ctx, _, _ = synth_world()
        record = lp.audit_candidate_round(entries[0], ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["gates"][lp.ROUND_PAD_GATE], "PASS")
        self.assertEqual(record["entry_pad"], "paciasp")

    def test_bti_c_candidate_rejected_by_round_gate(self):
        entries, ctx, _, _ = synth_world(entry_words={0: BTI_C})
        record = lp.audit_candidate_round(entries[0], ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"][lp.ROUND_PAD_GATE].startswith("FAIL"))
        self.assertIn(lp.ROUND_PAD_REASON, record["fail_reasons"])
        for gate in ll.GATES:
            self.assertEqual(record["gates"][gate], "PASS")


class SelectionPolicy(unittest.TestCase):
    def test_selects_nominal_with_dynamic_children(self):
        entries, ctx, _, _ = synth_world()
        selections, child_nominals = lp.select_targets(entries, ctx)
        self.assertEqual(child_nominals, (48, 58))
        self.assertEqual([selections[family]["selected_index"]
                          for family, _, _ in lp.family_specs()], [53, 48, 58])
        for family, _, _ in lp.family_specs():
            self.assertIsNone(selections[family]["deviation"])
        self.assertEqual(selections["late_post49"]["child_nominal_derivation"]
                         ["formula"], "(43 + target) // 2")
        self.assertEqual(selections["late_post60"]["child_nominal_derivation"]
                         ["target_index"], 53)

    def test_real_shaped_world_selects_55_with_children_49_and_60(self):
        entries, ctx, _, _ = real_shaped_world()
        selections, child_nominals = lp.select_targets(entries, ctx)
        self.assertEqual(selections["late_post43"]["selected_index"], 55)
        self.assertEqual(child_nominals, (49, 59))
        self.assertEqual(selections["late_post49"]["selected_index"], 49)
        self.assertEqual(selections["late_post60"]["selected_index"], 60)
        deviation = selections["late_post43"]["deviation"]
        self.assertEqual(deviation["nominal_index"], 53)
        self.assertEqual(deviation["chosen_index"], 55)
        self.assertEqual(deviation["distance"], 2)
        self.assertIn("TARGET_NOT_INIT_TEXT", deviation["reason"])
        skipped = {row["index"]: row["reason"] for row in
                   selections["late_post43"]["skipped"]}
        self.assertIn(lp.ROUND_PAD_REASON, skipped[51])
        self.assertIn("FUNCTION_TOO_SMALL", skipped[52])
        self.assertIn("TARGET_NOT_INIT_TEXT", skipped[54])
        upper = selections["late_post60"]
        self.assertEqual(upper["deviation"]["nominal_index"], 59)
        upper_skipped = {row["index"]: row["reason"] for row in upper["skipped"]}
        self.assertIn(lp.ROUND_PAD_REASON, upper_skipped[59])
        self.assertIn(lp.ROUND_PAD_REASON, upper_skipped[58])
        audits = {family: selections[family]["audit"] for family, _, _ in
                  lp.family_specs()}
        self.assertEqual([audits[family]["entry_pad"] for family, _, _ in
                          lp.family_specs()], ["paciasp"] * 3)
        self.assertEqual(audits["late_post43"]["symbol"], "late_sym_55")

    def test_frozen_indices_never_selected(self):
        entries, ctx, _, _ = synth_world(sizes={index: 40 for index in
                                                range(43, 63)})
        selection = lp.select_one(entries, ctx, "late_post43", "POST43", 63)
        self.assertEqual(selection["selected_index"], 64)
        skipped = {row["index"]: row["reason"] for row in selection["skipped"]}
        self.assertEqual(skipped.get(63), "FROZEN_TARGET_INDEX")

    def test_post43_target_out_of_interval_fails_loudly(self):
        entries, ctx, _, _ = synth_world(sizes={index: 40 for index in
                                                range(43, 63)})
        with self.assertRaisesRegex(ValueError, "POST43_TARGET_NOT_IN_43_63"):
            lp.select_targets(entries, ctx)

    def test_post60_beyond_63_fails_loudly(self):
        entries, ctx, _, _ = synth_world(sizes={index: 40 for index in
                                                range(52, 65)})
        with self.assertRaisesRegex(ValueError, "POST60_TARGET_NOT_BELOW_63"):
            lp.select_targets(entries, ctx)

    def test_frozen_window_overlap_skips_candidate(self):
        entries, ctx, targets, _ = synth_world()
        with mock.patch.object(lp, "FROZEN_LATE_WINDOWS", ((targets[53], 60),)):
            selections, _ = lp.select_targets(entries, ctx)
        self.assertEqual(selections["late_post43"]["selected_index"], 52)
        skipped = {row["index"]: row["reason"] for row in
                   selections["late_post43"]["skipped"]}
        self.assertIn("FROZEN_WINDOW_OVERLAP", skipped[53])

    def test_frozen_window_overlap_detector(self):
        self.assertIsNotNone(lp.frozen_window_overlap(0xFFFF800081B5BD1C, 60))
        self.assertIsNotNone(lp.frozen_window_overlap(0xFFFF800081B5BD1C + 8, 60))
        self.assertIsNone(lp.frozen_window_overlap(0xFFFF800081B5BD1C + 60, 60))
        self.assertIsNone(lp.frozen_window_overlap(0xFFFF800081B5BD1C - 64, 4))

    def test_selected_windows_are_disjoint(self):
        entries, ctx, _, _ = real_shaped_world()
        selections, _ = lp.select_targets(entries, ctx)
        windows = [(int(selections[family]["audit"]["target_va"], 16),
                    int(selections[family]["audit"]["target_va"], 16)
                    + selections[family]["audit"]["window"])
                   for family, _, _ in lp.family_specs()]
        for i, left in enumerate(windows):
            for right in windows[i + 1:]:
                self.assertFalse(cp.windows_overlap(left, right))


class FrozenPayloadGuard(unittest.TestCase):
    def test_frozen_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "RERUN_FORBIDDEN_FROZEN_PAYLOAD"):
            lp.require_fresh_payload(
                "c9f160597287666b73004db604c1525786eca5daef2e6fc7d43a647d2896be2d")

    def test_fresh_sha_accepted(self):
        lp.require_fresh_payload("0" * 64)


class WindowReferenceForensic(unittest.TestCase):
    def make_sections(self, extra=()):
        sections = [{"name": name, "vma": vma, "bytes": blob}
                    for name, vma, blob in extra]
        return sections

    def test_relr_decode(self):
        blob = struct.pack("<QQQ", 0x1000, 0b11, 0b101)
        self.assertEqual(lp.relr_sites(blob, 0), [0x1000, 0x1008, 0x1010])

    def test_adrp_add_into_interior_detected(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 100})
        target = targets[0]
        pc_off = offsets[10] + 0x800
        pc = TEXT_VA + pc_off
        addr = target + 8
        delta = ((addr & ~0xFFF) - (pc & ~0xFFF)) >> 12
        enc = delta & 0x1FFFFF
        adrp = 0x90000000 | ((enc & 0x3) << 29) | (((enc >> 2) & 0x7FFFF) << 5) | 9
        imm12 = addr & 0xFFF
        add = 0x91000000 | (imm12 << 10) | (9 << 5) | 9
        ctx["image"] = (ctx["image"][:pc_off] + struct.pack("<II", adrp, add)
                        + ctx["image"][pc_off + 8:])
        hits = lp.adrp_add_scan(ctx["image"], TEXT_VA, ctx["ranges"], target, 60)
        self.assertEqual(hits, [hex(addr)])
        with self.assertRaisesRegex(ValueError, "WINDOW_REFERENCE_ADRP_ADD_HIT"):
            lp.window_reference_forensic(
                ctx["image"], TEXT_VA, ctx["ranges"], self.make_sections(),
                [(0, "_text"), (TEXT_VA + 0x400000, "_end")],
                [{"name": ".init.text", "vma": TEXT_VA, "size": 0x800000}],
                target, 60, ENTRY_BASE_VA - TEXT_VA)

    def test_relative_reference_slot_allowed_kallsyms_excluded(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 100})
        target = targets[0]
        slot_off = 0x200
        koff = 0x20000
        image = bytearray(ctx["image"])
        struct.pack_into("<I", image, slot_off,
                         (target - (TEXT_VA + slot_off)) & 0xFFFFFFFF)
        stray = 0x28000
        struct.pack_into("<I", image, stray,
                         (target - (TEXT_VA + stray)) & 0xFFFFFFFF)
        ksym = koff + 0x40
        struct.pack_into("<I", image, ksym,
                         (target - (TEXT_VA + ksym)) & 0xFFFFFFFF)
        symbols = [(0, "_text"), (TEXT_VA + koff, "kallsyms_offsets"),
                   (TEXT_VA + koff + 0x200, "kallsyms_names"),
                   (TEXT_VA + koff + 0x400, "_stext"),
                   (TEXT_VA + 0x31000, "linux_banner"), (TEXT_VA + 0x40000, "_end")]
        sections = [{"name": ".init.text", "vma": TEXT_VA, "size": 0x30000},
                    {"name": ".rodata", "vma": TEXT_VA + 0x30000, "size": 0x8000}]
        banner = 0x32000
        struct.pack_into("<I", image, banner,
                         (target - (TEXT_VA + banner)) & 0xFFFFFFFF)
        result = lp.relative_reference_scan(bytes(image), TEXT_VA, target, 60,
                                            slot_off, symbols, sections)
        roles = {site["role"] for site in result["sites"]}
        self.assertIn("initcall_table_slot", roles)
        self.assertIn("UNEXPECTED", roles)
        self.assertTrue(result["slot_present"])
        excluded = {site["enclosing_symbol"]: site for site in
                    result["excluded_stream_data"]}
        self.assertEqual(excluded["kallsyms_offsets"]["section"], ".init.text")
        self.assertEqual(excluded["linux_banner"]["section"], ".rodata")
        with self.assertRaisesRegex(ValueError, "WINDOW_REFERENCE_DATA_HIT"):
            lp.window_reference_forensic(
                bytes(image), TEXT_VA, [(0, len(image))], self.make_sections(),
                symbols, sections, target, 60, slot_off)
        clean = bytearray(ctx["image"])
        struct.pack_into("<I", clean, slot_off,
                         (target - (TEXT_VA + slot_off)) & 0xFFFFFFFF)
        struct.pack_into("<I", clean, banner,
                         (target - (TEXT_VA + banner)) & 0xFFFFFFFF)
        forensic = lp.window_reference_forensic(
            bytes(clean), TEXT_VA, [(0, len(clean))], self.make_sections(),
            symbols, sections, target, 60, slot_off)
        self.assertEqual(forensic["verdict"], "NO_REFERENCE_INTO_WINDOW")
        self.assertEqual(forensic["residual_not_scanned"],
                         ["unaligned_8byte_absolute_pointers"])

    def test_table_scans_catch_fixup_and_alt_alt_fields(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 100})
        target = targets[0]
        vma = TEXT_VA + 0x500000
        ex_insn = struct.pack("<i", (target + 0x200) - (vma + 0))
        ex_fixup = struct.pack("<i", (target + 12) - (vma + 4))
        alt_orig = struct.pack("<i", (target + 0x300) - (vma + 0x100))
        alt_alt = struct.pack("<i", (target + 16) - (vma + 0x100))
        sections = self.make_sections((
            ("__ex_table", vma, ex_insn + ex_fixup + struct.pack("<ii", 4, 4)),
            (".altinstructions", vma + 0x100,
             alt_orig + alt_alt + struct.pack("<i", 4))),
        )
        hits = lp.table_section_scans(sections, target, 60)
        self.assertEqual(hits["ex_table"], [hex(target + 12)])
        self.assertIn(hex(target + 16), hits["altinstructions_alt"])
        self.assertEqual(hits["ex_table"], [hex(target + 12)])
        with self.assertRaisesRegex(ValueError, "WINDOW_REFERENCE_TABLE_HIT"):
            lp.window_reference_forensic(
                ctx["image"], TEXT_VA, ctx["ranges"], sections,
                [(0, "_text")], [{"name": ".init.text", "vma": TEXT_VA,
                                  "size": 0x800000}], target, 60, 0x200)


class PairComposition(unittest.TestCase):
    OFFSET = 0x2000
    ENTRY_WORD = PACIASP

    def compose(self, core, delay, size=60):
        frozen = bytearray(struct.pack("<I", NOP) * 0x4000)
        struct.pack_into("<I", frozen, self.OFFSET, self.ENTRY_WORD)
        struct.pack_into("<I", frozen, self.OFFSET + size - 4, RET)
        frozen = bytes(frozen)
        probe, payload = lp.compose_member(frozen, self.OFFSET, size,
                                           self.ENTRY_WORD, core, delay)
        return frozen, probe, payload

    def test_pair_diff_is_delay_constant_only_56b_core(self):
        frozen, probe8, payload8 = self.compose(CORE56, 8)
        _, probe1, payload1 = self.compose(CORE56, 1)
        changed = [i for i, (a, b) in enumerate(zip(payload8, payload1)) if a != b]
        ll.assert_pair_delay_only(changed, self.OFFSET, 56)
        self.assertEqual(changed, [self.OFFSET + 13, self.OFFSET + 14])
        self.assertEqual(struct.unpack_from("<I", payload8, self.OFFSET + 12)[0],
                         0xD37DF12A)
        self.assertEqual(struct.unpack_from("<I", payload1, self.OFFSET + 12)[0],
                         0xD340FD2A)
        self.assertEqual(probe8[:4], struct.pack("<I", self.ENTRY_WORD))
        self.assertEqual(len(probe8), 60)

    def test_pair_diff_is_delay_constant_only_52b_core(self):
        frozen, probe8, payload8 = self.compose(CORE52, 8, size=56)
        _, probe1, payload1 = self.compose(CORE52, 1, size=56)
        changed = [i for i, (a, b) in enumerate(zip(payload8, payload1)) if a != b]
        ll.assert_pair_delay_only(changed, self.OFFSET, 52)
        self.assertEqual(changed, [self.OFFSET + 9, self.OFFSET + 10])

    def test_member_changes_only_inside_window(self):
        frozen, probe, payload = self.compose(CORE56, 1)
        diffs = [i for i, (a, b) in enumerate(zip(frozen, payload)) if a != b]
        self.assertTrue(diffs)
        self.assertTrue(all(self.OFFSET <= i < self.OFFSET + 60 for i in diffs))
        self.assertEqual(payload[:self.OFFSET], frozen[:self.OFFSET])
        self.assertEqual(payload[self.OFFSET + 60:], frozen[self.OFFSET + 60:])


class SummaryKeys(unittest.TestCase):
    def names_fixture(self, deviation=None):
        audit = {"index": 55, "symbol": "genpd_debug_init",
                 "table_entry_va": "0xffff800081d0c3b4",
                 "target_va": "0xffff800081b8e964", "image_offset": "0x1b8e964",
                 "function_size": 128, "window": 60, "core_size": 56,
                 "probe_architecture": ll.CORE_56, "entry_pad": "paciasp",
                 "registration": "late_initcall(genpd_debug_init)",
                 "source": "drivers/base/power/domain.c"}
        return {family: {"label": label, "audit": audit,
                         "selection": {"deviation": deviation,
                                       "nominal_index": 53},
                         "shas": {8: "a" * 64, 1: "b" * 64}, "changed": [13, 14]}
                for family, label, _ in lp.family_specs()}

    def test_summary_contains_stage_and_pair_gates(self):
        lines = lp.summary_kv(self.names_fixture(), list(range(86)),
                              {"init_text": 82, "text_section": 4}, {})
        text = "\n".join(lines)
        self.assertIn(f"LATE_LEVEL_POST43_STAGE={lp.STAGE}", text)
        self.assertIn("LATE_TABLE_ENTRY_COUNT=86", text)
        self.assertIn("PAIR_DIFF=DELAY_CONSTANT_ONLY", text)
        self.assertIn("TRAMPOLINE_PERMITTED=NO", text)
        self.assertIn("PREL32_TARGET_UNCHANGED=YES", text)
        self.assertIn("ROUND_PAD_CLASS=PACIASP_ONLY", text)
        self.assertIn("FROZEN_INDICES_EXCLUDED=0,21,43,63", text)
        self.assertIn("FROZEN_PAYLOAD_DISJOINT=YES", text)
        self.assertIn("HIGH8_STATIC_PROBE_DEFECT_FOUND=NO", text)
        self.assertIn("POST43_NOMINAL_INDEX=53", text)
        self.assertIn("POST43_SYMBOL=genpd_debug_init", text)
        self.assertIn("POST43_PAIR=PASS", text)
        self.assertIn("POST49_PAIR=PASS", text)
        self.assertIn("POST60_PAIR=PASS", text)
        self.assertIn("POST43_8_PAYLOAD_SHA=" + "a" * 64, text)
        self.assertIn("POST43_1_PAYLOAD_SHA=" + "b" * 64, text)

    def test_summary_records_deviation(self):
        deviation = {"nominal_index": 53, "nominal_symbol": "sync_state_resume_initcall",
                     "chosen_index": 55, "distance": 2,
                     "reason": "TARGET_NOT_INIT_TEXT:.text;FUNCTION_TOO_SMALL"}
        lines = lp.summary_kv(self.names_fixture(deviation), [],
                              {"init_text": 82, "text_section": 4}, {})
        text = "\n".join(lines)
        self.assertIn("POST43_DEVIATION=TARGET_NOT_INIT_TEXT:.text;"
                      "FUNCTION_TOO_SMALL@distance=2", text)


if __name__ == "__main__":
    unittest.main()
