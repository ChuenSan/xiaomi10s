#!/usr/bin/env python3
"""Unit tests for late_level_cfg_audit: frozen-precedent calibration (PASS) and
deliberately broken synthetic fixtures (FAIL)."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import late_level_cfg_audit as la

NOP = 0xD503201F
PACIASP = la.PACIASP

MID_VA = 0xFFFF800081B5BD1C
LOW_VA = 0xFFFF800081B47510
IDX0_VA = 0xFFFF800081B32078
IDX0_ENTRY_VA = 0xFFFF800081D0C2D8

FROZEN_IDX0_WORDS = (0xD503233F, 0xA9BF7BFD, 0x910003FD, 0xD0FFF320, 0x912AC800,
                     0xB0001181, 0x91330021, 0x90FFFAA2, 0x913F6842, 0x52800043,
                     0x94009607, 0x2A1F03E0, 0xA8C17BFD, 0xD50323BF, 0xD65F03C0)


def enc_b(pc: int, target: int, link: bool = False) -> int:
    imm = (target - pc) // 4
    assert -(1 << 25) <= imm < (1 << 25)
    return (0x94000000 if link else 0x14000000) | (imm & 0x03FFFFFF)


def place(words_by_offset: dict) -> bytes:
    size = max(off + 4 for off in words_by_offset)
    image = bytearray(size)
    for off, word in words_by_offset.items():
        struct.pack_into("<I", image, off, word)
    return bytes(image)


def base_evidence(**kw) -> la.Evidence:
    clean = dict(entry_word=PACIASP, relocation_sites=[], literal_refs_into_window=[],
                 extable_insns=[], alt_ranges=[], jump_table_present=False,
                 static_call_present=False, kcfi_present=False)
    clean.update(kw)
    return la.Evidence(**clean)


def gate_by_name(report, name):
    return next(g for g in report["gates"] if g["gate"] == name)


class BranchDecoderTest(unittest.TestCase):
    def test_frozen_index0_bl_roundtrip(self):
        self.assertEqual(la.branch_target(0x94009607, IDX0_VA + 0x28), 0xFFFF800081B578BC)

    def test_b_bl_bcond_cbz_tbz(self):
        pc = 0x1000
        self.assertEqual(la.branch_target(enc_b(pc, pc + 0x40), pc), pc + 0x40)
        self.assertEqual(la.branch_target(enc_b(pc, pc - 0x100, link=True), pc), pc - 0x100)
        bcond = 0x54000000 | (((0x120 - pc) // 4 & 0x7FFFF) << 5) | 0x0
        self.assertEqual(la.branch_target(bcond, pc), 0x120)
        cbz = 0x34000000 | (((pc - 0x80 - pc) // 4 & 0x7FFFF) << 5)
        self.assertEqual(la.branch_target(cbz, pc), pc - 0x80)
        tbz = 0x36000000 | ((((pc + 0x200) - pc) // 4 & 0x3FFF) << 5)
        self.assertEqual(la.branch_target(tbz, pc), pc + 0x200)
        self.assertIsNone(la.branch_target(NOP, pc))
        self.assertIsNone(la.branch_target(la.RET, pc))

    def test_sx(self):
        self.assertEqual(la.sx(0xFFE25DA0 & 0xFFFFFFFF, 32), -1942112)
        self.assertEqual(la.sx(1, 2), 1)
        self.assertEqual(la.sx(3, 2), -1)

    def test_prel32_index0_frozen_decode(self):
        self.assertEqual(IDX0_ENTRY_VA + la.sx(0xFFE25DA0, 32), IDX0_VA)


class ArchitecturePolicyTest(unittest.TestCase):
    def test_prediction_policy(self):
        self.assertEqual(la.predict_inline_architecture(60), (la.ARCH_ULTRACOMPACT, 60))
        self.assertEqual(la.predict_inline_architecture(216), (la.ARCH_ULTRACOMPACT, 60))
        self.assertEqual(la.predict_inline_architecture(112), (la.ARCH_ULTRACOMPACT, 60))
        self.assertEqual(la.predict_inline_architecture(56), (la.ARCH_NO_DAIFSET, 56))
        self.assertEqual(la.predict_inline_architecture(40), (None, None))
        self.assertEqual(la.predict_inline_architecture(12), (None, None))


class FrozenIdentityTest(unittest.TestCase):
    def test_index0_frozen_identity_all_gates_pass(self):
        off = IDX0_VA - la.TEXT_VA
        image = place({off + 4 * i: w for i, w in enumerate(FROZEN_IDX0_WORDS)})
        ranges = [(off, off + 60)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (IDX0_VA, IDX0_VA + 60),
                                           (IDX0_VA, IDX0_VA + 60))
        self.assertEqual(topology["incoming_entry"], [])
        self.assertEqual(topology["incoming_window_interior"], [])
        self.assertEqual(topology["internal_branches"], [])
        self.assertEqual(topology["back_edges"], [])
        report = la.audit_candidate(0, "kernel_do_mounts_initrd_sysctls_init", IDX0_VA, 60,
                                    base_evidence(function_size=60, entry_word=FROZEN_IDX0_WORDS[0],
                                                  topology=topology,
                                                  prel32_entry_word=0xFFE25DA0,
                                                  prel32_entry_va=IDX0_ENTRY_VA))
        self.assertEqual(report["overall"], la.PASS, report)
        self.assertEqual(report["predicted_architecture"], la.ARCH_ULTRACOMPACT)
        self.assertEqual(report["derived_window"], 60)
        self.assertEqual([g["status"] for g in report["gates"]], [la.PASS] * 9)

    def test_index0_window_must_not_exceed_function(self):
        report = la.audit_candidate(0, "kernel_do_mounts_initrd_sysctls_init", IDX0_VA, 64,
                                    base_evidence(function_size=60))
        self.assertEqual(report["overall"], la.FAIL)
        self.assertEqual(gate_by_name(report, "WINDOW_FIT")["status"], la.FAIL)

    def test_index0_window_below_min_probe_rejected(self):
        report = la.audit_candidate(0, "kernel_do_mounts_initrd_sysctls_init", IDX0_VA, 52,
                                    base_evidence(function_size=60))
        self.assertEqual(gate_by_name(report, "WINDOW_FIT")["status"], la.FAIL)


class PrecedentCalibrationTest(unittest.TestCase):
    def test_topology_init_backedge_forces_window_160(self):
        fva = 0xFFFF800081B346FC
        fsize = 188
        off = fva - la.TEXT_VA
        words = {off + 4 * i: NOP for i in range(fsize // 4)}
        words[off + 0x9C] = enc_b(fva + 0x9C, fva + 0x38)
        image = place(words)
        ranges = [(off, off + fsize)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (fva, fva + fsize), (fva, fva + fsize))
        self.assertEqual(len(topology["back_edges"]), 1)
        self.assertEqual(topology["back_edges"], [[hex(fva + 0x9C), hex(fva + 0x38)]])
        derived = la.derive_inline_window(fva, fsize, topology["internal_branches"], 60)
        self.assertEqual(derived, 160)
        ok = la.audit_candidate(None, "topology_init", fva, 160,
                                base_evidence(function_size=fsize, topology=topology,
                                              prel32_entry_word=0xFFE298F0,
                                              prel32_entry_va=0xFFFF800081D0AE0C))
        self.assertEqual(ok["overall"], la.PASS, ok)
        bad = la.audit_candidate(None, "topology_init", fva, 60,
                                 base_evidence(function_size=fsize, topology=topology))
        self.assertEqual(bad["overall"], la.FAIL)
        self.assertIn("minimal closed window 160",
                      gate_by_name(bad, "INTERNAL_BRANCH_CLOSURE")["reason"])

    def test_chr_dev_init_branch_at_window_edge(self):
        fva = 0xFFFF800081B8CD40
        fsize = 184
        off = fva - la.TEXT_VA
        words = {off + 4 * i: NOP for i in range(fsize // 4)}
        words[off + 0x6C] = enc_b(fva + 0x6C, fva + 0x38)
        image = place(words)
        ranges = [(off, off + fsize)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (fva, fva + fsize), (fva, fva + fsize))
        derived = la.derive_inline_window(fva, fsize, topology["internal_branches"], 60)
        self.assertEqual(derived, 112)
        win56 = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                        (fva, fva + fsize), (fva, fva + 56))
        report = la.audit_candidate(None, "chr_dev_init", fva, 56,
                                    base_evidence(function_size=fsize, topology=win56,
                                                  prel32_entry_word=0xFFE81BD0,
                                                  prel32_entry_va=0xFFFF800081D0B170))
        self.assertEqual(report["overall"], la.PASS, report)
        self.assertEqual(gate_by_name(report, "INTERNAL_BRANCH_CLOSURE")["status"], la.PASS)
        win60 = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                        (fva, fva + fsize), (fva, fva + 60))
        bad = la.audit_candidate(None, "chr_dev_init", fva, 60,
                                 base_evidence(function_size=fsize, topology=win60))
        self.assertEqual(gate_by_name(bad, "INTERNAL_BRANCH_CLOSURE")["status"], la.FAIL)

    def test_create_debug_debugfs_entry_56b_no_daifset(self):
        fva = 0xFFFF8000800149E0
        fsize = 56
        off = fva - la.TEXT_VA
        words = {off: PACIASP, off + 4: 0xA9BF7BFD, off + 8: 0x910003FD}
        words.update({off + 4 * i: NOP for i in range(3, fsize // 4)})
        image = place(words)
        ranges = [(off, off + fsize)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (fva, fva + fsize), (fva, fva + 56))
        report = la.audit_candidate(None, "create_debug_debugfs_entry", fva, 56,
                                    base_evidence(function_size=fsize, entry_word=PACIASP,
                                                  topology=topology,
                                                  prel32_entry_word=0xFE30990C,
                                                  prel32_entry_va=0xFFFF800081D0B0D4))
        self.assertEqual(report["overall"], la.PASS, report)
        self.assertEqual(report["predicted_architecture"], la.ARCH_NO_DAIFSET)
        self.assertEqual(report["window"], 56)


class BrokenFixtureTest(unittest.TestCase):
    def test_entry_not_paciasp_fails(self):
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60, entry_word=0xD503201F))
        self.assertEqual(gate_by_name(report, "ENTRY_PACIASP")["status"], la.FAIL)

    def test_incoming_interior_branch_fails(self):
        off = IDX0_VA - la.TEXT_VA
        other = off + 0x100
        other_va = IDX0_VA + 0x100
        image = place({off + 4 * i: NOP for i in range(15)} |
                      {other: enc_b(other_va, IDX0_VA + 0x20)})
        ranges = [(off, off + 60), (other, other + 4)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (IDX0_VA, IDX0_VA + 60),
                                           (IDX0_VA, IDX0_VA + 60))
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60, topology=topology))
        self.assertEqual(gate_by_name(report, "INCOMING_BRANCHES")["status"], la.FAIL)
        self.assertEqual(report["overall"], la.FAIL)

    def test_incoming_entry_branch_fails(self):
        off = IDX0_VA - la.TEXT_VA
        other = off + 0x100
        other_va = IDX0_VA + 0x100
        image = place({off + 4 * i: NOP for i in range(15)} |
                      {other: enc_b(other_va, IDX0_VA)})
        ranges = [(off, off + 60), (other, other + 4)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (IDX0_VA, IDX0_VA + 60),
                                           (IDX0_VA, IDX0_VA + 60))
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60, topology=topology))
        self.assertEqual(gate_by_name(report, "INCOMING_BRANCHES")["status"], la.FAIL)

    def test_extable_hit_inside_window_fails(self):
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60,
                                                  extable_insns=[IDX0_VA + 0x10]))
        self.assertEqual(gate_by_name(report, "EXTABLE_OVERLAP")["status"], la.FAIL)

    def test_altinstructions_overlap_fails(self):
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60,
                                                  alt_ranges=[(IDX0_VA + 0x8, IDX0_VA + 0x18)]))
        self.assertEqual(gate_by_name(report, "RUNTIME_REWRITE_OVERLAP")["status"], la.FAIL)

    def test_jump_table_present_is_pending(self):
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60, jump_table_present=True))
        gate = gate_by_name(report, "RUNTIME_REWRITE_OVERLAP")
        self.assertEqual(gate["status"], la.PENDING)
        self.assertIn("__jump_table", gate["missing"][0])

    def test_initcall_table_overlap_fails(self):
        ev = base_evidence(function_size=60)
        ev.initcall_table_ranges = [(la.LATE_START_VA, la.LATE_END_VA)]
        report = la.audit_candidate(0, "x", la.LATE_START_VA + 8, 60, ev)
        self.assertEqual(gate_by_name(report, "INITCALL_TABLE_OVERLAP")["status"], la.FAIL)

    def test_relocation_in_window_fails(self):
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60,
                                                  relocation_sites=[IDX0_VA + 0x2C]))
        self.assertEqual(gate_by_name(report, "LITERAL_RELOCATION_OVERLAP")["status"], la.FAIL)

    def test_prel32_mismatch_fails(self):
        report = la.audit_candidate(0, "x", IDX0_VA, 60,
                                    base_evidence(function_size=60,
                                                  prel32_entry_word=0xFFE25DA0,
                                                  prel32_entry_va=IDX0_ENTRY_VA + 4))
        self.assertEqual(gate_by_name(report, "PREL32_ENTRY_UNCHANGED")["status"], la.FAIL)

    def test_closure_growth_and_exceeds_function(self):
        fva = 0xFFFF800081B40000
        fsize = 80
        off = fva - la.TEXT_VA
        words = {off + 4 * i: NOP for i in range(fsize // 4)}
        words[off + 0x4C] = enc_b(fva + 0x4C, fva + 0x10)
        image = place(words)
        ranges = [(off, off + fsize)]
        topology = la.scan_branch_topology(image, ranges, la.TEXT_VA,
                                           (fva, fva + fsize), (fva, fva + 60))
        report = la.audit_candidate(None, "x", fva, 60,
                                    base_evidence(function_size=fsize, topology=topology))
        closure = gate_by_name(report, "INTERNAL_BRANCH_CLOSURE")
        self.assertEqual(closure["status"], la.FAIL)
        self.assertIn("minimal closed window 80", closure["reason"])
        self.assertEqual(la.derive_inline_window(fva, fsize, topology["internal_branches"], 60), 80)

    def test_malformed_branch_beyond_function_reports_closure_exceeds(self):
        fva = 0xFFFF800081B40000
        topology = {"incoming_entry": [], "incoming_window_interior": [],
                    "internal_branches": [[hex(fva + 80), hex(fva + 0x10)]],
                    "back_edges": []}
        report = la.audit_candidate(None, "x", fva, 60,
                                    base_evidence(function_size=80, topology=topology))
        self.assertEqual(gate_by_name(report, "INTERNAL_BRANCH_CLOSURE")["status"], la.FAIL)
        self.assertIn("CFG_CLOSURE_EXCEEDS_FUNCTION",
                      gate_by_name(report, "INTERNAL_BRANCH_CLOSURE")["reason"])
        with self.assertRaises(ValueError):
            la.derive_inline_window(fva, 80, topology["internal_branches"], 60)

    def test_too_small_function_fails_window_fit(self):
        report = la.audit_candidate(64, "init_subsystem", 0xFFFF800080F4A804, 60,
                                    base_evidence(function_size=40))
        self.assertEqual(gate_by_name(report, "WINDOW_FIT")["status"], la.FAIL)
        self.assertIn("exceeds function size 40", gate_by_name(report, "WINDOW_FIT")["reason"])


class PendingPolicyTest(unittest.TestCase):
    def test_missing_authoritative_map_is_pending_with_named_items(self):
        report = la.audit_candidate(43, "integrity_fs_init", MID_VA, 60,
                                    la.Evidence(function_size=112,
                                                prel32_entry_word=0xFFE4F998,
                                                prel32_entry_va=0xFFFF800081D0C384))
        self.assertEqual(report["overall"], la.PENDING)
        missing = " ".join(report["missing_authoritative_map"])
        for token in ("first instruction word", "full-image branch scan",
                      "disassembly of the target function", "relocation site list",
                      "__ex_table", ".altinstructions"):
            self.assertIn(token, missing)
        self.assertEqual(gate_by_name(report, "WINDOW_FIT")["status"], la.PASS)
        self.assertEqual(gate_by_name(report, "INITCALL_TABLE_OVERLAP")["status"], la.PASS)
        self.assertEqual(gate_by_name(report, "PREL32_ENTRY_UNCHANGED")["status"], la.PASS)
        self.assertEqual(report["predicted_architecture"], la.ARCH_ULTRACOMPACT)


class ArtifactCalibrationTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def _paths(self):
        late = self.ROOT / "artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/late-table.json"
        smap = self.ROOT / "artifacts/slot-b-level6-inline-20260918/bundle/System.map"
        return late, smap

    def test_system_map_reproduces_all_frozen_precedent_sizes(self):
        _, smap_path = self._paths()
        if not smap_path.is_file():
            self.skipTest("frozen System.map not present")
        symap = la.symbol_map_from_system_map(smap_path)
        frozen = {"kernel_do_mounts_initrd_sysctls_init": 60, "topology_init": 188,
                  "chr_dev_init": 184, "af_unix_init": 216, "vlan_offload_init": 60,
                  "create_debug_debugfs_entry": 56}
        for name, size in frozen.items():
            va = symap["by_name"][name]
            self.assertEqual(symap["by_va"][va]["size"], size, name)

    def setUp(self):
        late, smap = self._paths()
        if not (late.is_file() and smap.is_file()):
            self.skipTest("frozen artifacts not present")
        self.entries = la.load_late_table(late)
        self.symap = la.symbol_map_from_system_map(smap)

    def test_late_table_count_and_frozen_identity(self):
        self.assertEqual(len(self.entries), 86)
        e0 = self.entries[0]
        self.assertEqual(e0["symbol"], "kernel_do_mounts_initrd_sysctls_init")
        self.assertEqual(e0["target_va"], IDX0_VA)
        self.assertEqual(e0["entry_va"], IDX0_ENTRY_VA)

    def test_derived_sizes_for_low_mid_and_neighbors(self):
        by_index = {e["index"]: e for e in self.entries}
        for index, expected in ((0, 60), (21, 60), (43, 112), (22, 40), (19, 40),
                                (42, 36), (44, 32), (64, 40), (20, 60), (41, 92)):
            rec = self.symap["by_va"][by_index[index]["target_va"]]
            self.assertEqual(rec["size"], expected, f"index {index}")

    def test_neighbor_search_low_primary_is_nominal_21(self):
        low = la.search_neighbors(self.entries, 21, lambda e: la.build_evidence(e, self.symap))
        self.assertIsNotNone(low["primary"])
        self.assertEqual(low["primary"]["index"], 21)
        self.assertEqual(low["primary"]["overall"], la.PENDING)
        self.assertEqual(low["primary"]["window"], 60)
        rejected = {r["index"]: r for r in low["rejected"]}
        self.assertIn(22, rejected)
        self.assertIn("TOO_SMALL", rejected[22]["reason"])
        self.assertIn(19, rejected)
        self.assertEqual(low["primary"]["delta"], 0)

    def test_neighbor_search_mid_primary_is_nominal_43(self):
        mid = la.search_neighbors(self.entries, 43, lambda e: la.build_evidence(e, self.symap))
        self.assertIsNotNone(mid["primary"])
        self.assertEqual(mid["primary"]["index"], 43)
        self.assertEqual(mid["primary"]["overall"], la.PENDING)
        self.assertEqual(mid["primary"]["window"], 60)
        rejected = {r["index"]: r for r in mid["rejected"]}
        self.assertIn(42, rejected)
        self.assertIn(44, rejected)
        conditional = [c["index"] for c in mid["conditional_candidates"]]
        self.assertIn(41, conditional)
        self.assertIn(39, conditional)


if __name__ == "__main__":
    unittest.main()
