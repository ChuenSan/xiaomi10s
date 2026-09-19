"""Unit tests for the late-level MID/LOW/HIGH failure-isolation round.

Pure Python only: synthetic fixtures plus the tracked reference late-table.json
(artifacts/slot-b-post-initcalls-20260919). No kernel build, no binaries.
"""
from __future__ import annotations

import json
import os
import struct
import unittest
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import checkpoint as cp
import late_level_isolation as ll

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
    """The tracked 86-entry decoded table from the prior GHA run (fixture)."""
    assert REFERENCE.is_file(), f"missing reference fixture: {REFERENCE}"
    rows = json.loads(REFERENCE.read_text())
    assert len(rows) == 86, f"reference fixture must hold 86 rows, got {len(rows)}"
    return rows


def reference_span_entries():
    return [{"index": row["index"], "entry_va": row["entry_va"],
             "entry_va_hex": row["entry_va_hex"],
             "entry_image_offset": row["entry_image_offset"],
             "entry_word": row["entry_word"], "relative": row["relative"],
             "target_va": row["target_va"], "target_va_hex": row["target_va_hex"],
             "aliases": list(row["aliases"]), "symbol": row["symbol"]}
            for row in load_reference()]


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
    """86 synthetic late entries over a compact NOP image; returns (entries, ctx)."""
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


def place_branch(ctx, pc_off, target_va):
    ctx["frozen"] = (ctx["frozen"][:pc_off]
                     + struct.pack("<I", cp.encode_b(TEXT_VA + pc_off, target_va))
                     + ctx["frozen"][pc_off + 4:])


def move_to_text_region(entries, ctx, index, size):
    target = TEXT_VA + ctx["text_region"]
    entries[index] = synth_entry(index, target, size, section=".text")
    ctx["sections"].append({"name": ".text", "vma": target, "size": 0x8000,
                            "code": True, "alloc": True})
    ctx["symbol_vas"] = sorted(set(ctx["symbol_vas"]) | {target})
    return target


class DecoderAndIdentity(unittest.TestCase):
    def test_reference_fixture_present(self):
        rows = load_reference()
        self.assertEqual([row["index"] for row in rows], list(range(86)))

    def test_reference_index0_matches_frozen_identity(self):
        row = load_reference()[0]
        self.assertEqual(row["symbol"], ll.FROZEN_INDEX0["symbol"])
        self.assertEqual(row["entry_va"], ll.FROZEN_INDEX0["entry_va"])
        self.assertEqual(row["entry_image_offset"], ll.FROZEN_INDEX0["entry_image_offset"])
        self.assertEqual(row["entry_word"], hex(ll.FROZEN_INDEX0["entry_word"]))
        self.assertEqual(row["relative"], ll.FROZEN_INDEX0["relative"])
        self.assertEqual(row["target_va"], ll.FROZEN_INDEX0["target_va"])

    def test_reference_table_prel32_self_consistent(self):
        for row in load_reference():
            self.assertEqual(row["target_va"], row["entry_va"] + row["relative"])
            self.assertEqual(row["entry_word"], hex(row["relative"] & 0xFFFFFFFF))

    def test_reference_symbols_are_unique_targets(self):
        rows = load_reference()
        targets = [row["target_va"] for row in rows]
        self.assertEqual(len(set(targets)), 86)
        slots = [row["entry_va"] for row in rows]
        self.assertEqual([b - a for a, b in zip(slots, slots[1:])], [4] * 85)

    def test_check_continuity_accepts_reference_table(self):
        entries = ll.check_continuity(reference_span_entries())
        self.assertEqual(len(entries), 86)
        self.assertEqual(entries[0]["symbol"], "kernel_do_mounts_initrd_sysctls_init")

    def test_check_continuity_rejects_hole(self):
        entries = reference_span_entries()
        entries[40]["entry_va"] += 8
        with self.assertRaisesRegex(ValueError, "LATE_TABLE_SLOT_HOLE"):
            ll.check_continuity(entries)

    def test_check_continuity_rejects_wrong_count(self):
        with self.assertRaisesRegex(ValueError, "LATE_TABLE_COUNT_DRIFT"):
            ll.check_continuity(reference_span_entries()[:85])

    def test_check_continuity_rejects_duplicate_target(self):
        entries = reference_span_entries()
        entries[5]["target_va"] = entries[4]["target_va"]
        with self.assertRaisesRegex(ValueError, "LATE_TABLE_TARGET_NOT_UNIQUE"):
            ll.check_continuity(entries)

    def test_check_continuity_rejects_drifted_index0(self):
        entries = reference_span_entries()
        entries[0]["target_va"] += 4
        with self.assertRaisesRegex(ValueError, "LATE_FIRST_TARGET_VA_DRIFT"):
            ll.check_continuity(entries)

    def test_build_map_entries_records_size_section_registration(self):
        target0 = ll.FROZEN_INDEX0["target_va"]
        raw = []
        for index in range(86):
            va = ENTRY_BASE_VA + 4 * index
            target = target0 + 256 * index
            relative = target - va
            name = "kernel_do_mounts_initrd_sysctls_init" if index == 0 else f"sym_{index}"
            raw.append({"index": index, "entry_va": va, "entry_va_hex": hex(va),
                        "entry_image_offset": va - TEXT_VA,
                        "entry_word": hex(relative & 0xFFFFFFFF), "relative": relative,
                        "target_va": target, "target_va_hex": hex(target),
                        "aliases": [name], "symbol": name})
        sections = [{"name": ".init.text", "vma": TEXT_VA, "size": 0x1C00000,
                     "code": True, "alloc": True}]
        registrations = {"kernel_do_mounts_initrd_sysctls_init":
                         [{"macro": "late_initcall", "source": "init/do_mounts_initrd.c"}],
                         **{f"sym_{i}": [{"macro": "late_initcall_sync",
                                          "source": f"d/{i}.c"}] for i in range(1, 86)}}
        entries = ll.build_map_entries(raw, sections, lambda t: t + 60, registrations)
        self.assertEqual(entries[0]["function_size"], 60)
        self.assertEqual(entries[0]["section"], ".init.text")
        self.assertTrue(entries[0]["init_text"])
        self.assertTrue(entries[0]["target_unique"])
        self.assertEqual(entries[0]["registration"],
                         "late_initcall(kernel_do_mounts_initrd_sysctls_init)")
        self.assertEqual(entries[0]["source"], "init/do_mounts_initrd.c")
        self.assertEqual(entries[1]["registration_type"], "late_initcall_sync")
        self.assertTrue(all(entry["target_unique"] for entry in entries))

    def test_candidate_ordering_prefers_nominal_then_lower_index_on_ties(self):
        self.assertEqual(ll.candidate_ordering(2, 6)[:4], [2, 1, 3, 0])
        self.assertEqual(ll.candidate_ordering(64, 86)[:3], [64, 63, 65])
        with self.assertRaisesRegex(ValueError, "NOMINAL_INDEX_OUT_OF_SPAN"):
            ll.candidate_ordering(86, 86)

    def test_index0_runtime_identity_accepts_frozen_shape(self):
        entry = {"function_size": 60, "registration":
                 "late_initcall(kernel_do_mounts_initrd_sysctls_init)",
                 "source": "init/do_mounts_initrd.c", "registration_type": "late_initcall"}
        self.assertIs(ll.check_index0_runtime_identity(entry, 0xD503233F), entry)

    def test_index0_runtime_identity_rejects_drift(self):
        entry = {"function_size": 64, "registration":
                 "late_initcall(kernel_do_mounts_initrd_sysctls_init)",
                 "source": "init/do_mounts_initrd.c", "registration_type": "late_initcall"}
        with self.assertRaisesRegex(ValueError, "LATE_INDEX0_FUNCTION_SIZE_DRIFT"):
            ll.check_index0_runtime_identity(entry, 0xD503233F)
        entry["function_size"] = 60
        with self.assertRaisesRegex(ValueError, "LATE_INDEX0_ENTRY_PAD_DRIFT"):
            ll.check_index0_runtime_identity(entry, 0xD503245F)
        with self.assertRaisesRegex(ValueError, "LATE_INDEX0_REGISTRATION_DRIFT"):
            ll.check_index0_runtime_identity({**entry, "registration": "late_initcall(x)"},
                                             0xD503233F)
        with self.assertRaisesRegex(ValueError, "LATE_INDEX0_SOURCE_DRIFT"):
            ll.check_index0_runtime_identity({**entry, "source": "elsewhere.c"},
                                             0xD503233F)
        with self.assertRaisesRegex(ValueError, "LATE_INDEX0_MACRO_DRIFT"):
            ll.check_index0_runtime_identity(
                {**entry, "registration_type": "late_initcall_sync"}, 0xD503233F)


class CandidateGates(unittest.TestCase):
    def audit(self, entries, ctx, index=0):
        return ll.audit_candidate(entries[index], ctx)

    def test_60b_paciasp_function_passes_with_56b_core(self):
        entries, ctx, _, _ = synth_world(sizes={0: 60})
        record = self.audit(entries, ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["window"], 60)
        self.assertEqual(record["core_size"], 56)
        self.assertEqual(record["probe_architecture"], ll.CORE_56)
        self.assertEqual(record["entry_pad"], "paciasp")
        self.assertTrue(record["pac"] and not record["bti"])
        for gate in ll.GATES:
            self.assertEqual(record["gates"][gate], "PASS")

    def test_56b_function_selects_52b_core(self):
        entries, ctx, _, _ = synth_world(sizes={0: 56})
        record = self.audit(entries, ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["window"], 56)
        self.assertEqual(record["core_size"], 52)
        self.assertEqual(record["probe_architecture"], ll.CORE_52)

    def test_interior_incoming_branch_rejects_window(self):
        entries, ctx, targets, offsets = synth_world(sizes={0: 100})
        place_branch(ctx, offsets[10] + 0x800, targets[0] + 0x10)
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["INCOMING_BRANCH"].startswith("FAIL"))
        self.assertTrue(any("INCOMING_WINDOW_INTERIOR_BRANCH" in reason
                            for reason in record["fail_reasons"]))

    def test_incoming_entry_branch_rejects_window(self):
        entries, ctx, targets, _ = synth_world(sizes={0: 100})
        place_branch(ctx, 0x800, targets[0])
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any("INCOMING_ENTRY_BRANCH" in reason
                            for reason in record["fail_reasons"]))

    def test_back_edge_grows_window_like_topology_init(self):
        # 188-byte function with a function-local back-edge +0x9c -> +0x38: the
        # overwritten window must grow from 60 to 160 (topology_init precedent).
        size = 188
        entries, ctx, targets, offsets = synth_world(sizes={0: size})
        src = offsets[0] + 0x9C
        place_branch(ctx, src, targets[0] + 0x38)
        record = self.audit(entries, ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["window"], 160)
        self.assertTrue(record["cfg_closure"]["cfg_closure_proven"])
        self.assertEqual([[int(a, 16), int(b, 16)] for a, b in
                          record["cfg_closure"]["back_edges"]],
                         [[TEXT_VA + src, targets[0] + 0x38]])

    def test_symbol_inside_window_interior_rejects(self):
        entries, ctx, targets, _ = synth_world(sizes={0: 100})
        ctx["symbol_vas"] = sorted(set(ctx["symbol_vas"]) | {targets[0] + 32})
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["SYMBOL_SCAN"].startswith("FAIL"))

    def test_window_crossing_next_symbol_rejects(self):
        # declared size 100 but the next symbol sits at +40: the overwrite would
        # leave the function body (cross-function overwrite is forbidden)
        entries, ctx, targets, _ = synth_world(sizes={0: 100})
        ctx["symbol_vas"] = sorted(set(ctx["symbol_vas"]) | {targets[0] + 40})
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["EXTENT_SCAN"].startswith("FAIL"))

    def test_extable_overlap_rejects(self):
        entries, ctx, targets, _ = synth_world(sizes={0: 100})
        ctx["rw_sites"]["__ex_table"] = [targets[0] + 8]
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["RUNTIME_REWRITE"].startswith("FAIL"))
        self.assertTrue(any("REWRITE_OVERLAP" in reason
                            for reason in record["fail_reasons"]))

    def test_relocation_overlap_rejects(self):
        entries, ctx, targets, _ = synth_world(sizes={0: 100})
        ctx["reloc_sites"] = [targets[0] + 12]
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["RELOCATION_SCAN"].startswith("FAIL"))

    def test_literal_pointer_into_window_rejects(self):
        entries, ctx, targets, _ = synth_world(sizes={0: 100})
        slot = (ctx["image_len"] // 8 - 2) * 8
        ctx["frozen"] = (ctx["frozen"][:slot] + struct.pack("<Q", targets[0] + 8)
                         + ctx["frozen"][slot + 8:])
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["LITERAL_SCAN"].startswith("FAIL"))

    def test_text_section_target_rejects_init_text_gate(self):
        entries, ctx, _t, _o = synth_world(sizes={0: 100})
        move_to_text_region(entries, ctx, 0, 100)
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(record["gates"]["INIT_TEXT"].startswith("FAIL"))
        self.assertTrue(any("TARGET_NOT_INIT_TEXT" in reason
                            for reason in record["fail_reasons"]))

    def test_oversized_entry_pad_rejected(self):
        entries, ctx, _, _ = synth_world(sizes={0: 100}, entry_words={0: NOP})
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any("ENTRY_NOT_PACIASP_OR_BTI" in reason
                            for reason in record["fail_reasons"]))

    def test_bti_entry_accepted_and_recorded(self):
        entries, ctx, _, _ = synth_world(sizes={0: 100}, entry_words={0: BTI_C})
        record = self.audit(entries, ctx)
        self.assertTrue(record["PASS"], record["gates"])
        self.assertEqual(record["entry_pad"], "bti c")
        self.assertTrue(record["bti"] and not record["pac"])

    def test_non_late_registration_rejected(self):
        entries, ctx, _, _ = synth_world(sizes={0: 100})
        entries[0]["registration_type"] = "device_initcall"
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any("NOT_LATE_INITCALL" in reason
                            for reason in record["fail_reasons"]))

    def test_missing_registration_rejected(self):
        entries, ctx, _, _ = synth_world(sizes={0: 100})
        entries[0]["registration_type"] = None
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any("NOT_LATE_INITCALL" in reason
                            for reason in record["fail_reasons"]))

    def test_duplicate_target_rejected(self):
        entries, ctx, _, _ = synth_world(sizes={0: 100})
        entries[0]["target_unique"] = False
        record = self.audit(entries, ctx)
        self.assertFalse(record["PASS"])
        self.assertTrue(any("TARGET_DECODED_MORE_THAN_ONCE" in reason
                            for reason in record["fail_reasons"]))


class SelectionPolicy(unittest.TestCase):
    def test_selects_nominal_mid_low_high(self):
        entries, ctx, _, _ = synth_world()
        selections = ll.select_targets(entries, ctx)
        self.assertEqual([selections[family]["selected_index"]
                          for family, _, _ in ll.FAMILIES], [43, 21, 64])
        for family, _, _ in ll.FAMILIES:
            self.assertIsNone(selections[family]["deviation"])
            self.assertEqual(selections[family]["audit"]["window"], 60)

    def test_high_falls_back_to_nearest_lower_index(self):
        # the real round shape: nominal HIGH 64 (init_subsystem) is a 40-byte
        # .text function, so selection must move one index down
        entries, ctx, _, _ = synth_world(sizes={64: 40})
        move_to_text_region(entries, ctx, 64, 40)
        selections = ll.select_targets(entries, ctx)
        high = selections["late_high"]
        self.assertEqual(high["selected_index"], 63)
        deviation = high["deviation"]
        self.assertEqual(deviation["nominal_index"], 64)
        self.assertEqual(deviation["chosen_index"], 63)
        self.assertEqual(deviation["distance"], 1)
        self.assertIn("TARGET_NOT_INIT_TEXT", deviation["reason"])
        self.assertIn("FUNCTION_TOO_SMALL", deviation["reason"])
        self.assertEqual([row["index"] for row in high["skipped"]], [64])
        self.assertEqual(selections["late_mid"]["selected_index"], 43)
        self.assertEqual(selections["late_low"]["selected_index"], 21)

    def test_tie_prefers_lower_index(self):
        entries, ctx, _, _ = synth_world(sizes={43: 40})
        selections = ll.select_targets(entries, ctx)
        self.assertEqual(selections["late_mid"]["selected_index"], 42)
        self.assertEqual(selections["late_mid"]["deviation"]["distance"], 1)

    def test_no_safe_target_fails_loudly(self):
        entries, ctx, _, _ = synth_world(sizes={index: 40 for index in range(86)})
        with self.assertRaisesRegex(ValueError, "MID_NO_SAFE_INLINE_TARGET"):
            ll.select_targets(entries, ctx)

    def test_selected_windows_are_disjoint(self):
        entries, ctx, _, _ = synth_world()
        selections = ll.select_targets(entries, ctx)
        windows = [(int(selections[family]["audit"]["target_va"], 16),
                    int(selections[family]["audit"]["target_va"], 16)
                    + selections[family]["audit"]["window"])
                   for family, _, _ in ll.FAMILIES]
        for i, left in enumerate(windows):
            for right in windows[i + 1:]:
                self.assertFalse(cp.windows_overlap(left, right))


class PairComposition(unittest.TestCase):
    OFFSET = 0x2000
    ENTRY_WORD = PACIASP

    def compose(self, core, delay, size=60):
        frozen = bytearray(struct.pack("<I", NOP) * 0x4000)
        struct.pack_into("<I", frozen, self.OFFSET, self.ENTRY_WORD)
        struct.pack_into("<I", frozen, self.OFFSET + size - 4, RET)
        frozen = bytes(frozen)
        probe, payload = ll.compose_member(frozen, self.OFFSET, size, self.ENTRY_WORD,
                                           core, delay)
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

    def test_assert_pair_delay_only_rejects_other_diffs(self):
        for changed in ([self.OFFSET + 13], [self.OFFSET + 13, self.OFFSET + 15],
                        [self.OFFSET + 9, self.OFFSET + 10]):
            with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_CONSTANT_ONLY"):
                ll.assert_pair_delay_only(changed, self.OFFSET, 56)

    def test_window_agreement_exact(self):
        frozen, _probe, _payload = self.compose(CORE56, 8)
        agreement = ll.window_agreement(frozen, frozen, TEXT_VA, self.OFFSET, 60)
        self.assertEqual(agreement["verdict"], "EXACT")
        self.assertEqual(agreement["differing_words"], [])

    def test_window_agreement_proves_layout_literal_delta(self):
        frozen = bytearray(struct.pack("<I", NOP) * 0x4000)
        struct.pack_into("<I", frozen, self.OFFSET, PACIASP)
        image = bytearray(frozen)
        adrp = 0x90000000  # imm21 = 0: the ADRP's own 4 KiB page
        struct.pack_into("<I", image, self.OFFSET + 4, adrp)
        struct.pack_into("<I", frozen, self.OFFSET + 4, adrp)
        base_imm = 0x100
        struct.pack_into("<I", image, self.OFFSET + 8, 0x91000000 | (base_imm << 10))
        struct.pack_into("<I", frozen, self.OFFSET + 8,
                         0x91000000 | ((base_imm + 8) << 10))
        page_off = (self.OFFSET + 4) & ~0xFFF
        for blob, imm in ((image, base_imm), (frozen, base_imm + 8)):
            blob[page_off + imm:page_off + imm + 7] = b"kernel\0"
        agreement = ll.window_agreement(bytes(image), bytes(frozen), TEXT_VA,
                                        self.OFFSET, 60)
        self.assertEqual(agreement["verdict"], "LAYOUT_LITERAL_ADDRESS_DELTA_VERIFIED")
        self.assertEqual(len(agreement["layout_literal_refs"]), 1)
        self.assertEqual(agreement["layout_literal_refs"][0]["bundle"]["text"], "kernel")

    def test_real_core_assembly_word_layout(self):
        self.assertEqual(len(CORE56), 56)
        self.assertEqual(len(CORE52), 52)
        self.assertEqual(CORE52, CORE56[4:])
        cp.gate_subsys52_core_equivalence(CORE56, CORE52)


class SummaryKeys(unittest.TestCase):
    def names_fixture(self, deviation=None):
        audit = {"index": 43, "symbol": "integrity_fs_init",
                 "table_entry_va": "0xffff800081d0c384",
                 "target_va": "0xffff800081b5bd1c", "image_offset": "0x1b5bd1c",
                 "function_size": 112, "window": 60, "core_size": 56,
                 "probe_architecture": ll.CORE_56, "entry_pad": "paciasp",
                 "registration": "late_initcall(integrity_fs_init)",
                 "source": "security/integrity/iint.c"}
        return {family: {"label": label, "audit": audit,
                         "selection": {"deviation": deviation},
                         "shas": {8: "a" * 64, 1: "b" * 64}, "changed": [13, 14]}
                for family, label, _ in ll.FAMILIES}

    def test_summary_contains_stage_and_pair_gates(self):
        lines = ll.summary_kv(self.names_fixture(), list(range(86)),
                              {"init_text": 82, "text_section": 4})
        text = "\n".join(lines)
        self.assertIn(f"LATE_LEVEL_STAGE={ll.STAGE}", text)
        self.assertIn("LATE_TABLE_ENTRY_COUNT=86", text)
        self.assertIn("PAIR_DIFF=DELAY_CONSTANT_ONLY", text)
        self.assertIn("TRAMPOLINE_PERMITTED=NO", text)
        self.assertIn("PREL32_TARGET_UNCHANGED=YES", text)
        self.assertIn("LATE_MID_SYMBOL=integrity_fs_init", text)
        self.assertIn("LATE_MID_PAIR=PASS", text)
        self.assertIn("LATE_HIGH_NOMINAL_INDEX=64", text)

    def test_summary_records_deviation(self):
        deviation = {"nominal_index": 64, "nominal_symbol": "init_subsystem",
                     "chosen_index": 63, "distance": 1, "reason": "TARGET_NOT_INIT_TEXT"}
        lines = ll.summary_kv(self.names_fixture(deviation), [],
                              {"init_text": 82, "text_section": 4})
        text = "\n".join(lines)
        self.assertIn("LATE_HIGH_DEVIATION=TARGET_NOT_INIT_TEXT@distance=1", text)


if __name__ == "__main__":
    unittest.main()
