"""Unit tests for the LATE_MID/LATE_LOW/LATE_HIGH public observer fixtures.

Pure Python only: synthetic identities and timings plus the committed frozen
registry in observe.py. No kernel build, no binaries, no device access.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import observe
import late_level_observer_fixtures as lf

SYNTHETIC = {
    "late_mid": {"8": "a" * 64, "1": "b" * 64},
    "late_low": {"8": "c" * 64, "1": "d" * 64},
    "late_high": {"8": "e" * 64, "1": "f" * 64},
    "late_post43": {"8": "g" * 64, "1": "h" * 64},
    "late_post49": {"8": "i" * 64, "1": "j" * 64},
}
FROZEN_GEOMETRY = {
    "late_mid": {"label": "LATE_MID", "index": 43, "nominal_index": 43,
                 "target": "integrity_fs_init", "va": 0xFFFF800081B5BD1C,
                 "offset": 0x1B5BD1C, "function_size": 112, "window": 60,
                 "core_size": 56, "table_va": 0xFFFF800081D0C384,
                 "prel32_word": "0xffe4f998", "relative": -1771112,
                 "pair_diff": [0x1B5BD29, 0x1B5BD2A], "deviation": None},
    "late_low": {"label": "LATE_LOW", "index": 21, "nominal_index": 21,
                 "target": "kexec_core_sysctl_init", "va": 0xFFFF800081B47510,
                 "offset": 0x1B47510, "function_size": 60, "window": 60,
                 "core_size": 56, "table_va": 0xFFFF800081D0C32C,
                 "prel32_word": "0xffe3b1e4", "relative": -1855004,
                 "pair_diff": [0x1B4751D, 0x1B4751E], "deviation": None},
    "late_high": {"label": "LATE_HIGH", "index": 63, "nominal_index": 64,
                  "target": "bpf_kfunc_init", "va": 0xFFFF800081BAA15C,
                  "offset": 0x1BAA15C, "function_size": 260, "window": 60,
                  "core_size": 56, "table_va": 0xFFFF800081D0C3D4,
                  "prel32_word": "0xffe9dd88", "relative": -1450616,
                  "pair_diff": [0x1BAA169, 0x1BAA16A],
                  "deviation": {"nominal_index": 64, "chosen_index": 63, "distance": 1}},
    "late_post43": {"label": "POST43", "index": 55, "nominal_index": 53,
                    "target": "genpd_debug_init", "va": 0xFFFF800081B8E964,
                    "offset": 0x1B8E964, "function_size": 128, "window": 60,
                    "core_size": 56, "table_va": 0xFFFF800081D0C3B4,
                    "prel32_word": "0xffe825b0", "relative": -1563216,
                    "pair_diff": [0x1B8E971, 0x1B8E972],
                    "deviation": {"nominal_index": 53, "chosen_index": 55,
                                  "distance": 2}},
    "late_post49": {"label": "POST49", "index": 49, "nominal_index": 49,
                    "target": "bert_init", "va": 0xFFFF800081B7017C,
                    "offset": 0x1B7017C, "function_size": 408, "window": 404,
                    "core_size": 56, "table_va": 0xFFFF800081D0C39C,
                    "prel32_word": "0xffe63de0", "relative": -1688096,
                    "pair_diff": [0x1B70189, 0x1B7018A], "deviation": None},
}


class FrozenRegistryTests(unittest.TestCase):
    def test_frozen_prior_shas_match_observe_registry(self):
        for case, sha in lf.FROZEN_PRIOR_SHAS.items():
            self.assertEqual(observe.IMAGES[case], (37380096, sha))

    def test_prior_families_exist_in_observe_registry(self):
        families = {case[:-1] for case in observe.IMAGES if case != "recovery"}
        self.assertLessEqual(set(lf.PRIOR_FAMILIES),
                             families - {"late_mid", "late_low", "late_high",
                                         "late_post43", "late_post49"})
        for family in lf.PRIOR_FAMILIES:
            self.assertIn(family + "8", observe.IMAGES)
            self.assertIn(family + "1", observe.IMAGES)

    def test_late_level_families_frozen_in_observe_registry(self):
        for case in lf.MEMBERS:
            family, delay = case[:-1], case[-1]
            self.assertEqual(observe.IMAGES[case],
                             (37380096, lf.FROZEN_IDENTITIES[family][delay]))


class GeometryTests(unittest.TestCase):
    def test_frozen_geometry_literals(self):
        for family, expected in FROZEN_GEOMETRY.items():
            spec = lf.FAMILIES[family]
            for key, value in expected.items():
                self.assertEqual(spec[key], value, f"{family}.{key}")
            self.assertEqual(spec["architecture"], "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT")
            self.assertEqual(spec["entry"], "paciasp")
            self.assertTrue(spec["inline_only"])
            self.assertTrue(spec["prel32_unchanged"])

    def test_geometry_accepts_frozen_window_only(self):
        for family, spec in lf.FAMILIES.items():
            lf.validate_geometry(family, spec["window"])
            with self.assertRaisesRegex(ValueError, f"{spec['label']}_56B_WINDOW_REJECTED"):
                lf.validate_geometry(family, 56)
            for wrong in (52, 64):
                with self.assertRaisesRegex(ValueError, f"{spec['label']}_WINDOW_NOT_60"):
                    lf.validate_geometry(family, wrong)

    def test_selection_deviation_policy(self):
        for family in lf.FAMILIES:
            lf.validate_selection(family)
        spec = dict(lf.FAMILIES["late_mid"], deviation={"nominal_index": 43,
                                                        "chosen_index": 43, "distance": 0})
        with patch.dict(lf.FAMILIES, {"late_mid": spec}):
            with self.assertRaisesRegex(ValueError, "LATE_MID_UNEXPECTED_DEVIATION"):
                lf.validate_selection("late_mid")

    def test_table_identity(self):
        for family in lf.FAMILIES:
            lf.validate_table(family)
        drifted = dict(lf.FAMILIES["late_low"], pair_diff=[0x1B4751C, 0x1B4751D])
        with patch.dict(lf.FAMILIES, {"late_low": drifted}):
            with self.assertRaisesRegex(ValueError, "LATE_LOW_PAIR_DIFF_DRIFT"):
                lf.validate_table("late_low")

    def test_pair_diff_range_is_delay_word(self):
        for family, spec in lf.FAMILIES.items():
            self.assertEqual(lf.pair_diff_range(family),
                             [spec["offset"] + 13, spec["offset"] + 15])
            lf.require_pair_diff(family, spec["pair_diff"])
            for wrong in ([spec["offset"] + 12, spec["offset"] + 13],
                          [spec["offset"] + 14, spec["offset"] + 15],
                          [0x1B32085, 0x1B32086]):
                with self.subTest(family=family, wrong=wrong):
                    with self.assertRaisesRegex(ValueError,
                                                f"{spec['label']}_PAIR_DIFF_MISMATCH"):
                        lf.require_pair_diff(family, wrong)


class IdentityTests(unittest.TestCase):
    def test_exact_identity_only(self):
        with patch.dict(lf.FROZEN_IDENTITIES, SYNTHETIC):
            for case in lf.MEMBERS:
                identity = lf.member_identity(case)
                self.assertEqual(identity[0], 37380096)
                lf.validate_member(case, *identity)
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    lf.validate_member(case, identity[0] + 1, identity[1])
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    lf.validate_member(case, identity[0], "0" * 64)
                for sibling in set(lf.MEMBERS) - {case}:
                    with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                        lf.validate_member(case, *lf.member_identity(sibling))

    def test_all_identities_frozen(self):
        for case in lf.MEMBERS:
            family, delay = case[:-1], case[-1]
            self.assertEqual(lf.member_identity(case),
                             (37380096, lf.FROZEN_IDENTITIES[family][delay]))
            self.assertTrue(all(lf.FROZEN_IDENTITIES[f][d]
                                for f in lf.FROZEN_IDENTITIES
                                for d in ("8", "1")))

    def test_non_late_level_cases_rejected(self):
        with patch.dict(lf.FROZEN_IDENTITIES, SYNTHETIC):
            for case in ("recovery", "mid8", "late_mid9", "late_devprobe8", "waitentry8"):
                with self.assertRaisesRegex(ValueError, "CASE_NOT_LATE_LEVEL"):
                    lf.validate_member(case, 37380096, "a" * 64)


class VerdictTests(unittest.TestCase):
    def records(self, family):
        return lf.record(family + "8", 35.0), lf.record(family + "1", 28.0)

    def test_strong_proves_only_target_entry(self):
        with patch.dict(lf.FROZEN_IDENTITIES, SYNTHETIC):
            for family, spec in lf.FAMILIES.items():
                baseline, result = self.records(family)
                verdict = lf.late_level_pair_verdict(baseline, result, family)
                self.assertEqual(verdict["verdict"], "STRONG")
                self.assertEqual(verdict[f"{spec['label']}_ENTRY"], "PROVEN")
                self.assertEqual(verdict["delta_s"], -7.0)
                self.assertEqual(verdict["expected_delta_s"], -7.0)
                self.assertEqual(verdict["error_s"], 0.0)
                self.assertEqual(verdict["late_initcalls_completed"], "NOT_PROVEN")
                self.assertEqual(verdict["wait_for_initramfs_return"], "NOT_PROVEN")
                self.assertEqual(verdict["console_on_rootfs_entry"], "NOT_PROVEN")
                self.assertEqual(verdict["init_executed"], "NOT_PROVEN")
                self.assertEqual(verdict["usb"], "FROZEN")
                self.assertNotIn(f"{family}_checkpoint_shift_not_observed", verdict)
                self.assertFalse(any("not_reached" in key for key in verdict))

    def test_grade_boundaries(self):
        with patch.dict(lf.FROZEN_IDENTITIES, SYNTHETIC):
            for family, spec in lf.FAMILIES.items():
                baseline = lf.record(family + "8", 35.0)
                for total, verdict, grade in ((27.0, "STRONG", "PROVEN"),
                                              (26.0, "SUPPORTED", "SUPPORTED"),
                                              (25.9, "SHIFT_NOT_OBSERVED", "NOT_PROVEN"),
                                              (30.0, "SUPPORTED", "SUPPORTED"),
                                              (30.1, "SHIFT_NOT_OBSERVED", "NOT_PROVEN")):
                    with self.subTest(family=family, total=total):
                        out = lf.late_level_pair_verdict(
                            baseline, lf.record(family + "1", total), family)
                        self.assertEqual(out["verdict"], verdict)
                        self.assertEqual(out[f"{spec['label']}_ENTRY"], grade)

    def test_no_shift_only_records_checkpoint_shift_not_observed(self):
        with patch.dict(lf.FROZEN_IDENTITIES, SYNTHETIC):
            for family, spec in lf.FAMILIES.items():
                baseline, _ = self.records(family)
                out = lf.late_level_pair_verdict(baseline, lf.record(family + "1", 35.0),
                                                 family)
                self.assertEqual(out["verdict"], "SHIFT_NOT_OBSERVED")
                self.assertEqual(out[f"{spec['label']}_ENTRY"], "NOT_PROVEN")
                self.assertEqual(out[f"{family}_checkpoint_shift_not_observed"], "YES")
                self.assertEqual(out["late_initcalls_completed"], "NOT_PROVEN")
                self.assertFalse(any("not_reached" in key for key in out))

    def broken(self, family, mutate, message):
        baseline, result = self.records(family)
        with self.assertRaisesRegex(ValueError, message):
            lf.late_level_pair_verdict(mutate(baseline), result, family)

    def test_invalid_records_rejected(self):
        with patch.dict(lf.FROZEN_IDENTITIES, SYNTHETIC):
            for family in lf.FAMILIES:
                with self.subTest(family=family):
                    self.broken(family, lambda r: {**r, "case": "waitentry8"},
                                "PAIR_MEMBER_MISMATCH")
                    self.broken(family, lambda r: {**r, "bootloader_origin": "OTHER"},
                                "PAIR_ORIGIN_MISMATCH")
                    self.broken(family, lambda r: {**r, "protocol": "other"},
                                "PAIR_PROTOCOL_MISMATCH")
                    self.broken(family, lambda r: {**r, "image_sha256": "0" * 64},
                                "PAIR_IDENTITY_MISMATCH")
                    self.broken(family, lambda r: {**r, "status": "STOP"},
                                "PAIR_RETURN_NOT_VALID")
                    self.broken(family, lambda r: {**r, "final_slot": "a"},
                                "PAIR_NOT_SLOT_B")
                    self.broken(family, lambda r: {**r, "experimental_boots": 2},
                                "PAIR_BOOT_COUNT_INVALID")
                    self.broken(family, lambda r: {**r, "context": {}},
                                "PAIR_CONTEXT_MISMATCH")
                    for bad_total in (True, float("inf"), 0, -1.0):
                        self.broken(family, lambda r, t=bad_total: {**r, "total_s": t},
                                    "PAIR_TIMING_INVALID")
                    result = lf.record(family + "1", 28.0)
                    baseline = lf.record(family + "8", 35.0)
                    with self.assertRaisesRegex(ValueError, "PAIR_MEMBER_MISMATCH"):
                        lf.late_level_pair_verdict(baseline, {**result, "case": "late_mid8"},
                                                   family)


if __name__ == "__main__":
    unittest.main()
