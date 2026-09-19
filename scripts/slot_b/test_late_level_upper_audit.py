#!/usr/bin/env python3
"""Unit tests for the late-level upper-half CFG/geometry auditor.

Layer 1 (hermetic): synthetic functions reproduce the frozen precedent
topologies (index 0 identity, chr_dev_init, topology_init) plus deliberately
broken fixtures; every gate decision is exercised without artifacts.

Layer 2 (artifact-grounded, skipped when the GHA artifacts are absent): the
same evaluator runs against the sha-pinned GHA-produced bundle binaries and
must reproduce every frozen precedent decision.
"""
from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import late_level_upper_audit as ua

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/slot-b-post-initcalls-20260919"
BUNDLE = ROOT / "artifacts/slot-b-level6-inline-20260918/bundle"
PAYLOAD = ROOT / "artifacts/slot-b-level7-20260918/pair/8/checkpoint/payload.bin"
LATE_TABLE = ARTIFACTS / "ci/l7-late-complete/audit/late-table.json"
AUDIT_JSON = ARTIFACTS / "ci/l7-late-complete/audit/audit.json"
WINDOW_TXT = ARTIFACTS / "ci/l7-late-complete/audit/window.txt"

# Synthetic layout: a 4 MiB image, the function at 0x200000, its initcall
# table word far away in a data-like region.
FUNC = 0x200000
FUNC_VA = ua.TEXT_VA + FUNC
TABLE = 0x300000
PATCH_SPOT = 0x1000

NOP = 0xD503201F
RET = 0xD65F03C0


def gate(verdict, name):
    return next(g for g in verdict.gates if g.name == name)


def enc_b(pc_off, dst_off, bl=False):
    imm = (dst_off - pc_off) // 4
    return (0x94000000 if bl else 0x14000000) | (imm & 0x03FFFFFF)


def enc_bcond(pc_off, dst_off, cond=0):
    return 0x54000000 | cond | (((dst_off - pc_off) // 4 & 0x7FFFF) << 5)


def enc_cbz(pc_off, dst_off):
    return 0x34000000 | (((dst_off - pc_off) // 4 & 0x7FFFF) << 5)


def synth_late_table(targets=None):
    """Two synthetic table entries; targets default to the candidate entry."""
    if targets is None:
        targets = (FUNC_VA, FUNC_VA + 60)
    return tuple(
        ua.Candidate(index=i, symbol=f"synth_{i}", target_va=va,
                     entry_va=ua.INITCALL7_START_VA + 4 * i,
                     entry_image_offset=TABLE + 4 * i,
                     entry_word=0xFFE25DA0 + i, relative=-1942112 + i,
                     aliases=(f"synth_{i}",))
        for i, va in enumerate(targets))


def synth_map(words, *, relocs=(), ex_insns=(), alts=(), extra_symbols=(),
              late_table=None, size=60):
    image = bytearray(0x400000)
    for i, w in enumerate(words):
        struct.pack_into("<I", image, FUNC + 4 * i, w)
    symbol_vas = {FUNC_VA, FUNC_VA + size} | set(extra_symbols)
    return ua.AuthoritativeMap(
        image=bytes(image), image_evidence="synthetic", image_sha_expected=None,
        exec_ranges=((0, len(image)),), symbol_vas=tuple(sorted(symbol_vas)),
        symbol_st_size={FUNC_VA: size}, reloc_sites=tuple(sorted(set(relocs))),
        ex_table_insns=tuple(sorted(set(ex_insns))), alt_ranges=tuple(alts),
        late_table=late_table if late_table is not None
        else synth_late_table(targets=(FUNC_VA, FUNC_VA + size)))


def synth_candidate(size=60):
    return ua.Candidate(index=0, symbol="synth_0", target_va=FUNC_VA,
                        entry_va=ua.INITCALL7_START_VA, entry_image_offset=TABLE,
                        entry_word=0xFFE25DA0, relative=-1942112,
                        aliases=("synth_0",))


def straight_line_words(n_pad=12):
    """Index-0 identity shape: paciasp + straight line + one external BL + ret."""
    return ([ua.PACIASP] + [NOP] * n_pad
            + [enc_b((n_pad + 1) * 4, 0x10000, bl=True), RET])


# ---------------------------------------------------------------------------
# Layer 1: synthetic fixtures
# ---------------------------------------------------------------------------

class SyntheticIndex0Identity(unittest.TestCase):
    def test_identity_selects_window_60_and_passes(self):
        ctx = synth_map(straight_line_words())
        v = ua.evaluate(ctx, synth_candidate())
        self.assertEqual(v.derived_window, 60)
        self.assertEqual(v.window, 60)
        self.assertEqual(v.core, "56B_ULTRACOMPACT")
        self.assertTrue(v.passed, v.reasons())
        self.assertEqual(v.topology["back_edges"], [])
        self.assertEqual(v.topology["internal_branches"], [])
        self.assertEqual(v.topology["surviving_into_interior"], [])

    def test_forced_window_60_passes(self):
        v = ua.evaluate(synth_map(straight_line_words()), synth_candidate(),
                        window=60)
        self.assertTrue(v.passed, v.reasons())

    def test_core_mapping(self):
        self.assertEqual(ua.core_for_window(60), ("56B_ULTRACOMPACT", 60))
        self.assertEqual(ua.core_for_window(160), ("56B_ULTRACOMPACT", 60))
        self.assertEqual(ua.core_for_window(56), ("52B_NO_DAIFSET", 56))
        for bad in (58, 52, 61):
            with self.assertRaises(ua.AuditError):
                ua.core_for_window(bad)


def chr_like_words():
    """chr_dev_init topology: back-edge +0x6c->+0x38 (target == 56B window
    end), second back-edge +0xb4->+0x48, forward CBZ/B.cond edges."""
    words = [ua.PACIASP] + [NOP] * 45 + [RET]
    words[0x34 // 4] = enc_cbz(0x34, 0x5c)
    words[0x44 // 4] = enc_cbz(0x44, 0x70)
    words[0x6c // 4] = enc_b(0x6c, 0x38)
    words[0x88 // 4] = enc_cbz(0x88, 0xa4)
    words[0xac // 4] = enc_bcond(0xac, 0x84)
    words[0xb4 // 4] = enc_b(0xb4, 0x48)
    return words


class SyntheticChrDevInit(unittest.TestCase):
    def test_frozen_56b_window_configuration_passes(self):
        ctx = synth_map(chr_like_words(), size=184)
        v = ua.evaluate(ctx, synth_candidate(184), window=56)
        self.assertEqual(v.core, "52B_NO_DAIFSET")
        self.assertTrue(v.passed, v.reasons())

    def test_60b_configuration_is_rejected_by_closure(self):
        ctx = synth_map(chr_like_words(), size=184)
        v = ua.evaluate(ctx, synth_candidate(184), window=60)
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "CFG_CLOSURE").status, ua.FAIL)
        self.assertEqual(v.topology["surviving_into_interior"],
                         [[hex(FUNC_VA + 0x6c), hex(FUNC_VA + 0x38)]])

    def test_60b_preference_derives_full_function(self):
        ctx = synth_map(chr_like_words(), size=184)
        v = ua.evaluate(ctx, synth_candidate(184))
        self.assertEqual(v.derived_window, 184)
        steps = v.topology["growth_steps"]
        self.assertEqual((steps[0]["window"], steps[0]["grew_to"]), (60, 112))
        self.assertEqual(steps[-1]["grew_to"], 184)


def topo_like_words():
    """topology_init topology: back-edge +0x9c->+0x38 forces window 160."""
    words = [ua.PACIASP] + [NOP] * 46 + [RET]
    words[0x54 // 4] = enc_bcond(0x54, 0xa0)
    words[0x64 // 4] = enc_cbz(0x64, 0x80)
    words[0x6c // 4] = enc_cbz(0x6c, 0x7c)
    words[0x78 // 4] = enc_b(0x78, 0x80)
    words[0x9c // 4] = enc_b(0x9c, 0x38)
    return words


class SyntheticTopologyInit(unittest.TestCase):
    def test_selection_requires_160(self):
        ctx = synth_map(topo_like_words(), size=188)
        v = ua.evaluate(ctx, synth_candidate(188))
        self.assertEqual(v.derived_window, 160)
        self.assertTrue(v.passed, v.reasons())
        self.assertEqual(v.topology["growth_steps"][0],
                         {"window": 60, "grew_to": 160,
                          "surviving": [[hex(FUNC_VA + 0x9c), hex(FUNC_VA + 0x38)]]})

    def test_smaller_windows_fail_closure(self):
        ctx = synth_map(topo_like_words(), size=188)
        for forced in (60, 112, 144):
            v = ua.evaluate(ctx, synth_candidate(188), window=forced)
            self.assertFalse(v.passed, f"window={forced}")
            self.assertEqual(gate(v, "CFG_CLOSURE").status, ua.FAIL)
        self.assertTrue(ua.evaluate(ctx, synth_candidate(188), window=160).passed)


class SyntheticBrokenFixtures(unittest.TestCase):
    def test_too_small_function_rejected(self):
        ctx = synth_map([ua.PACIASP] + [NOP] * 8 + [RET], size=40)
        v = ua.evaluate(ctx, synth_candidate(40))
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "MIN_WINDOW").status, ua.FAIL)
        self.assertIn("40", gate(v, "MIN_WINDOW").detail)

    def test_non_paciasp_entry_rejected(self):
        ctx = synth_map([0xD503245F] + [NOP] * 13 + [RET])  # bti c entry
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "PACIASP_ENTRY").status, ua.FAIL)
        self.assertTrue(v.topology["bti"])

    def patch_external_branch(self, words, size, dst_off):
        """Place a branch from outside the function into the image."""
        ctx = synth_map(words, size=size)
        image = bytearray(ctx.image)
        struct.pack_into("<I", image, PATCH_SPOT,
                         enc_b(PATCH_SPOT, FUNC + dst_off))
        return ua.AuthoritativeMap(
            image=bytes(image), image_evidence="synthetic",
            image_sha_expected=None, exec_ranges=ctx.exec_ranges,
            symbol_vas=ctx.symbol_vas, symbol_st_size=ctx.symbol_st_size,
            reloc_sites=ctx.reloc_sites, ex_table_insns=ctx.ex_table_insns,
            alt_ranges=ctx.alt_ranges, late_table=ctx.late_table)

    def test_incoming_interior_branch_rejected(self):
        ctx = self.patch_external_branch(straight_line_words(), 60, 0x30)
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "INCOMING_WINDOW_INTERIOR").status, ua.FAIL)
        self.assertEqual(gate(v, "INCOMING_WINDOW_INTERIOR").detail,
                         str([[hex(ua.TEXT_VA + PATCH_SPOT),
                               hex(FUNC_VA + 0x30)]]))

    def test_incoming_entry_branch_rejected(self):
        ctx = self.patch_external_branch(straight_line_words(), 60, 0)
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "INCOMING_ENTRY_BRANCH").status, ua.FAIL)

    def test_relocation_overlap_rejected(self):
        ctx = synth_map(straight_line_words(), relocs=(FUNC + 0x20,))
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "RELOCATION_OVERLAP").status, ua.FAIL)
        self.assertIn("1 sites", gate(v, "RELOCATION_OVERLAP").detail)

    def test_literal_overlap_rejected(self):
        ctx = synth_map(straight_line_words())
        image = bytearray(ctx.image)
        struct.pack_into("<Q", image, PATCH_SPOT, FUNC_VA + 0x28)
        ctx2 = ua.AuthoritativeMap(
            image=bytes(image), image_evidence="synthetic",
            image_sha_expected=None, exec_ranges=ctx.exec_ranges,
            symbol_vas=ctx.symbol_vas, symbol_st_size=ctx.symbol_st_size,
            reloc_sites=ctx.reloc_sites, ex_table_insns=ctx.ex_table_insns,
            alt_ranges=ctx.alt_ranges, late_table=ctx.late_table)
        v = ua.evaluate(ctx2, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "LITERAL_OVERLAP").status, ua.FAIL)
        self.assertEqual(gate(v, "LITERAL_OVERLAP").detail,
                         "1 absolute literals into window")

    def test_extable_overlap_rejected(self):
        ctx = synth_map(straight_line_words(), ex_insns=(FUNC + 0x10,))
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "EXTABLE_OVERLAP").status, ua.FAIL)

    def test_alternatives_overlap_rejected(self):
        ctx = synth_map(straight_line_words(), alts=((FUNC + 0x08, FUNC + 0x14),))
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "ALTERNATIVES_OVERLAP").status, ua.FAIL)

    def test_initcall_table_target_interior_rejected(self):
        ctx = synth_map(straight_line_words(),
                        late_table=synth_late_table(targets=(FUNC_VA + 0x30,
                                                             FUNC_VA + 60)))
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "INITCALL_TABLE_OVERLAP").status, ua.FAIL)

    def test_initcall_table_word_in_window_rejected(self):
        table = synth_late_table()
        shifted = (ua.Candidate(**{**table[0].__dict__,
                                   "entry_image_offset": FUNC + 0x20}), table[1])
        ctx = synth_map(straight_line_words(), late_table=shifted)
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "INITCALL_TABLE_OVERLAP").status, ua.FAIL)

    def test_interior_symbol_rejected(self):
        ctx = synth_map(straight_line_words(), extra_symbols=(FUNC_VA + 0x20,))
        v = ua.evaluate(ctx, synth_candidate())
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "NO_CROSS_FUNCTION_OVERWRITE").status, ua.FAIL)

    def test_window_crossing_function_end_rejected(self):
        ctx = synth_map(straight_line_words())
        v = ua.evaluate(ctx, synth_candidate(), window=64)
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "WINDOW_FIT").status, ua.FAIL)


class FrozenCoreWords(unittest.TestCase):
    """Cross-check the independent ARM64 decoder against the frozen probe
    cores' internal loop encodings (re-declared here, not imported)."""

    def test_ultracompact_core56(self):
        w = ua.ULTRACOMPACT_CORE56_WORDS
        self.assertEqual(len(w), 14)
        self.assertEqual(w[2], 0xD37DF12A)  # 8s delay word
        self.assertEqual(ua.branch_target(w[8], 8 * 4), (4 * 4, "B.cond"))
        self.assertEqual(ua.branch_target(w[11], 11 * 4), None)  # hvc #0

    def test_subsys52_core(self):
        self.assertEqual(ua.SUBSYS52_CORE_WORDS, ua.ULTRACOMPACT_CORE56_WORDS[1:])
        w = ua.SUBSYS52_CORE_WORDS
        self.assertEqual(len(w), 13)
        self.assertEqual(w[1], 0xD37DF12A)
        self.assertEqual(ua.branch_target(w[7], 7 * 4), (3 * 4, "B.cond"))
        self.assertEqual(ua.branch_target(w[12], 12 * 4), (11 * 4, "B"))

    def test_pair_diff_matches_frozen_facts(self):
        # Index-0 frozen pair diff [0x1b32085, 0x1b32087).
        self.assertEqual(ua.pair_diff(0x1B32078, 60), (0x1B32085, 0x1B32087))
        # late_complete frozen caller pair diff [0x1b31145, 0x1b31147).
        self.assertEqual(ua.pair_diff(0x1B3113C, 56), (0x1B31145, 0x1B31147))

    def test_decoder_shapes(self):
        self.assertEqual(ua.branch_target(enc_b(0, 0x100), 0), (0x100, "B"))
        self.assertEqual(ua.branch_target(enc_b(0, 0x100, bl=True), 0),
                         (0x100, "BL"))
        self.assertEqual(ua.branch_target(enc_b(0x1000, 0x800), 0x1000),
                         (0x800, "B"))
        self.assertEqual(ua.branch_target(enc_cbz(0, 0x40), 0), (0x40, "CBZ"))
        self.assertEqual(ua.branch_target(enc_bcond(0, 0x40, cond=3), 0),
                         (0x40, "B.cond"))
        self.assertEqual(ua.branch_target(NOP, 0), None)


class BoundaryBracketSynthetic(unittest.TestCase):
    def test_completion_rule(self):
        self.assertEqual(ua.completion_claim("late_complete", -7.0)["claim"],
                         "LATE_INITCALLS_COMPLETED=PROVEN")
        self.assertEqual(ua.completion_claim("late_complete", -7.9)["claim"],
                         "LATE_INITCALLS_COMPLETED=PROVEN")
        self.assertEqual(ua.completion_claim("late_complete", -6.1)["claim"],
                         "LATE_INITCALLS_COMPLETED=PROVEN")
        self.assertEqual(ua.completion_claim("wait_complete", -7.0)["claim"],
                         "LATE_INITCALLS_COMPLETED=PROVEN")
        self.assertEqual(
            ua.completion_claim("late_complete", -4.0)["claim"],
            "NO_UPGRADE (pair not STRONG; no completion claim either way)")
        self.assertEqual(
            ua.completion_claim("late_complete", -9.0)["claim"],
            "NO_UPGRADE (pair not STRONG; no completion claim either way)")

    def test_interior_entries_never_imply_completion(self):
        for index in (0, 28, 63, 64, 85):
            claim = ua.completion_claim(f"late_entry_{index}", -7.0)
            self.assertEqual(claim["claim"], "INVALID_CHECKPOINT")
        self.assertIn("index 85",
                      ua.LEVEL7_COMPLETION_CHECKPOINT["negative_rules"][0])
        self.assertIn("does NOT license",
                      ua.LEVEL7_COMPLETION_CHECKPOINT["negative_rules"][2])

    def test_waitentry_no_shift_implies_nothing(self):
        strong = abs(ua.WAITENTRY_PAIR_DELTA_S - ua.EXPECTED_PAIR_DELTA_S) \
            <= ua.STRONG_TOLERANCE_S
        self.assertFalse(strong)
        self.assertIn("neither completion nor non-completion",
                      ua.LEVEL7_COMPLETION_CHECKPOINT["negative_rules"][1])
        self.assertIn("rerun-FORBIDDEN",
                      ua.LEVEL7_COMPLETION_CHECKPOINT["negative_rules"][1])


# ---------------------------------------------------------------------------
# Layer 2: artifact-grounded calibration
# ---------------------------------------------------------------------------

@unittest.skipUnless(LATE_TABLE.exists() and PAYLOAD.exists() and BUNDLE.exists(),
                     "GHA artifacts not present")
class ArtifactGrounded(unittest.TestCase):
    """Run the evaluator against the sha-pinned GHA-produced binaries."""

    @classmethod
    def setUpClass(cls):
        cls.payload_ctx = ua.build_context(
            image_path=PAYLOAD,
            image_sha_expected=ua.LEVEL7_DEVPROBE8_PAYLOAD_SHA,
            vmlinux_path=BUNDLE / "vmlinux", late_table_path=LATE_TABLE,
            patched_windows=((0x1B32078, 0x1B32078 + 60),)).verified()
        cls.image_ctx = ua.build_context(
            image_path=BUNDLE / "Image",
            image_sha_expected=ua.FROZEN_BUNDLE_IMAGE_SHA,
            vmlinux_path=BUNDLE / "vmlinux", late_table_path=LATE_TABLE,
            patched_windows=()).verified()

    def test_late_table_frozen_facts(self):
        table = self.payload_ctx.late_table
        self.assertEqual(len(table), 86)
        self.assertEqual(table[0].symbol, "kernel_do_mounts_initrd_sysctls_init")
        self.assertEqual(table[0].target_va, 0xFFFF800081B32078)
        self.assertEqual(table[0].entry_image_offset, 30458584)
        self.assertEqual(table[0].entry_word, 0xFFE25DA0)
        self.assertEqual(table[64].symbol, "init_subsystem")
        self.assertEqual(table[64].target_va, 0xFFFF800080F4A804)
        self.assertEqual(table[64].entry_image_offset, 30458840)
        self.assertEqual(table[64].entry_word, 0xFF23E42C)
        self.assertEqual(table[85].symbol, "alsa_sound_last_init")
        self.assertEqual(table[0].entry_va, ua.INITCALL7_START_VA)
        self.assertEqual(table[85].entry_va + 4, ua.INITCALL_END_VA)

    def test_nominal_64_is_too_small(self):
        v = ua.evaluate(self.payload_ctx, self.payload_ctx.late_table[64])
        self.assertFalse(v.passed)
        self.assertEqual(gate(v, "MIN_WINDOW").status, ua.FAIL)
        self.assertIn("40", gate(v, "MIN_WINDOW").detail)

    def test_neighbor_order_from_nominal_64(self):
        self.assertEqual(ua.neighbor_order(86, 64)[:6], [64, 63, 65, 62, 66, 61])

    def test_first_passable_neighbor_is_63(self):
        first, verdicts, order = ua.select_upper_child(self.payload_ctx)
        self.assertEqual(first.candidate.index, 63)
        self.assertEqual(first.candidate.symbol, "bpf_kfunc_init")
        self.assertEqual(first.function_size, 260)
        self.assertEqual(first.window, 60)
        self.assertEqual(first.core, "56B_ULTRACOMPACT")
        self.assertTrue(first.geometry_passed, first.reasons())
        self.assertEqual(gate(first, "PACIASP_ENTRY").detail, "entry=paciasp")
        self.assertEqual(first.topology["back_edges"], [])
        # Rejections flanking the first passable neighbor.
        rejected = {v.candidate.index: v for v in verdicts}
        self.assertIn("40", gate(rejected[64], "MIN_WINDOW").detail)
        for index, size in ((65, 40), (66, 52)):
            v = ua.evaluate(self.payload_ctx, self.payload_ctx.late_table[index])
            self.assertEqual(gate(v, "MIN_WINDOW").detail, f"function_size={size} < 56"
                             " (trampoline forbidden, INLINE only)")
        for index in (62, 61):
            v = ua.evaluate(self.payload_ctx, self.payload_ctx.late_table[index])
            self.assertEqual(gate(v, "PACIASP_ENTRY").status, ua.FAIL)
            self.assertIn("bti", gate(v, "PACIASP_ENTRY").detail)

    def test_precedent_index0_identity(self):
        v = ua.evaluate(self.image_ctx, self.image_ctx.late_table[0])
        self.assertEqual(v.function_size, 60)
        self.assertEqual(v.derived_window, 60)
        self.assertEqual(v.core, "56B_ULTRACOMPACT")
        self.assertTrue(v.passed, v.reasons())
        self.assertEqual(v.topology["internal_branches"], [])

    def test_precedent_chr_dev_init(self):
        cand = ua.Candidate(index=39, symbol="chr_dev_init",
                            target_va=0xFFFF800081B8CD40,
                            entry_va=0xFFFF800081D0B170,
                            entry_image_offset=0x1D0B170, entry_word=0xFFE81BD0,
                            relative=-1565744, aliases=("chr_dev_init",))
        v56 = ua.evaluate(self.payload_ctx, cand, window=56)
        self.assertTrue(v56.passed, v56.reasons())
        self.assertEqual(v56.core, "52B_NO_DAIFSET")
        v60 = ua.evaluate(self.payload_ctx, cand, window=60)
        self.assertFalse(v60.passed)
        self.assertEqual(gate(v60, "CFG_CLOSURE").status, ua.FAIL)
        self.assertEqual(v60.topology["surviving_into_interior"],
                         [[hex(0xFFFF800081B8CDAC), hex(0xFFFF800081B8CD78)]])

    def test_precedent_topology_init_requires_160(self):
        cand = ua.Candidate(index=0, symbol="topology_init",
                            target_va=0xFFFF800081B346FC,
                            entry_va=0xFFFF800081D0AE0C,
                            entry_image_offset=0x1D0AE0C, entry_word=0xFFE298F0,
                            relative=-1926924, aliases=("topology_init",))
        v = ua.evaluate(self.payload_ctx, cand)
        self.assertEqual(v.derived_window, 160)
        self.assertTrue(v.passed, v.reasons())
        for forced in (60, 112, 144):
            self.assertFalse(
                ua.evaluate(self.payload_ctx, cand, window=forced).passed,
                f"window={forced} must fail")
        self.assertTrue(ua.evaluate(self.payload_ctx, cand, window=160).passed)

    def test_precedent_af_unix_vlan_create_debug(self):
        af_unix = ua.Candidate(index=46, symbol="af_unix_init",
                               target_va=0xFFFF800081BAE798,
                               entry_va=0xFFFF800081D0B18C,
                               entry_image_offset=0x1D0B18C,
                               entry_word=0xFFEA360C, relative=-1427956,
                               aliases=("af_unix_init",))
        v = ua.evaluate(self.payload_ctx, af_unix)
        self.assertEqual((v.function_size, v.window, v.core),
                         (216, 60, "56B_ULTRACOMPACT"))
        self.assertTrue(v.passed, v.reasons())
        vlan = ua.Candidate(index=49, symbol="vlan_offload_init",
                            target_va=0xFFFF800081BAEDFC,
                            entry_va=0xFFFF800081D0B198,
                            entry_image_offset=0x1D0B198, entry_word=0xFFEA3C64,
                            relative=-1426332, aliases=("vlan_offload_init",))
        v = ua.evaluate(self.payload_ctx, vlan)
        self.assertEqual((v.function_size, v.window, v.core),
                         (60, 60, "56B_ULTRACOMPACT"))
        self.assertTrue(v.passed, v.reasons())
        create_debug = ua.Candidate(
            index=0, symbol="create_debug_debugfs_entry",
            target_va=0xFFFF8000800149E0, entry_va=0xFFFF800081D0B0D4,
            entry_image_offset=0x1D0B0D4, entry_word=0xFE30990C,
            relative=-30369524, aliases=("create_debug_debugfs_entry",))
        v = ua.evaluate(self.payload_ctx, create_debug)
        self.assertEqual((v.function_size, v.window, v.core),
                         (56, 56, "52B_NO_DAIFSET"))
        self.assertTrue(v.passed, v.reasons())

    def test_boundary_bracket_against_frozen_audit(self):
        verdict = ua.verify_boundary_bracket(json.loads(AUDIT_JSON.read_text()),
                                             WINDOW_TXT.read_text())
        self.assertTrue(verdict["verified"])
        self.assertFalse(verdict["strong"])
        self.assertEqual(verdict["verdict_label"], "SHIFT_NOT_OBSERVED")
        self.assertEqual(verdict["observed_delta_s"], 3.200119584)
        self.assertEqual(verdict["expected_delta_s"], -7.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
