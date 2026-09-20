"""Unit tests for the COMPACT52 public observer fixtures.

Pure Python only: synthetic identities and timings. observe.py now carries the
compact52 plug-in points and is the registry the device round drives, while the
fixtures keep their own independent identity literals so the registry-agreement
gate compares two separately transcribed sources. No kernel build, no binaries,
no device access.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import observe
import late_compact52_observer_fixtures as of

SYNTHETIC_BOOT = {"8": "a" * 64, "1": "b" * 64}
SYNTHETIC_PAYLOAD = {"8": "c" * 64, "1": "d" * 64}
FROZEN_GEOMETRY = {
    "late_compact52": {"label": "COMPACT52", "index": 52, "nominal_index": 52,
                       "target": "boot_wait_for_devices", "va": 0xFFFF800081B87EC8,
                       "offset": 0x1B87EC8, "function_size": 48, "window": 48,
                       "core_size": 44, "architecture": "COMPACT_INLINE_48B",
                       "entry": "paciasp", "paciasp_word": "0xd503233f", "tail_size": 0,
                       "daifset": "ABSENT", "table_va": 0xFFFF800081D0C3A8,
                       "prel32_word": "0xffe7bb20", "relative": -1590496,
                       "pair_diff": [0x1B87ED1, 0x1B87ED2], "deviation": None},
}


def synth():
    return (patch.dict(of.FROZEN_IDENTITIES, {"late_compact52": SYNTHETIC_BOOT}),
            patch.dict(of.FROZEN_PAYLOAD_IDENTITIES, {"late_compact52": SYNTHETIC_PAYLOAD}))


class FrozenRegistryTests(unittest.TestCase):
    def test_compact52_registered_in_observe(self):
        self.assertEqual(observe.IMAGES["late_compact528"],
                         (37380096, of.COMPACT52_8_BOOT_SHA256))
        self.assertEqual(observe.IMAGES["late_compact521"],
                         (37380096, of.COMPACT52_1_BOOT_SHA256))
        self.assertEqual(observe.PAIRS["late_compact521"],
                         ("late_compact528", "late_compact52_entry",
                          "late_initcalls_completed"))
        self.assertIn("late_compact528", observe.ORIGIN_CASES)
        self.assertIn("late_compact521", observe.ORIGIN_CASES)

    def test_fixtures_registry_matches_observe(self):
        self.assertEqual(of.FROZEN_IDENTITIES,
                         {"late_compact52": {"8": of.COMPACT52_8_BOOT_SHA256,
                                             "1": of.COMPACT52_1_BOOT_SHA256}})
        self.assertEqual(of.FROZEN_PAYLOAD_IDENTITIES,
                         {"late_compact52": {"8": of.COMPACT52_8_PAYLOAD_SHA256,
                                              "1": of.COMPACT52_1_PAYLOAD_SHA256}})
        of.require_registry_agreement()

    def test_identity_is_frozen_shape_and_not_a_placeholder(self):
        of.require_authoritative()
        for value in (of.COMPACT52_8_BOOT_SHA256, of.COMPACT52_1_BOOT_SHA256,
                      of.COMPACT52_8_PAYLOAD_SHA256, of.COMPACT52_1_PAYLOAD_SHA256):
            with self.subTest(value=value):
                self.assertTrue(of._is_sha256(value))
                self.assertFalse(of.is_placeholder_sha(value))


class PlaceholderRejectionTests(unittest.TestCase):
    """A well-formed 64-hex string must not be able to pass as an identity."""

    def test_valid_hex_placeholders_and_sentinels_rejected(self):
        for decoy in ("f1a0" + "0" * 60, "f1b0" + "0" * 60, "e1a0" + "0" * 60,
                      "e1b0" + "0" * 60, "0" * 64, "a" * 64, "f" * 64,
                      of.COMPACT52_8_BOOT_SHA256[0] * 64):
            with self.subTest(decoy=decoy):
                self.assertTrue(of._is_sha256(decoy))
                self.assertTrue(of.is_placeholder_sha(decoy))

    def test_malformed_and_non_string_rejected(self):
        for decoy in ("z" * 64, "0" * 63 + "g", "0" * 63, "0" * 65, 37380096,
                      None, "", b"0" * 64):
            with self.subTest(decoy=decoy):
                self.assertTrue(of.is_placeholder_sha(decoy))

    def test_authoritative_identity_survives_the_predicate(self):
        of.require_authoritative()

    def test_require_authoritative_refuses_a_placeholder_constant(self):
        for name in ("COMPACT52_8_BOOT_SHA256", "COMPACT52_1_BOOT_SHA256",
                     "COMPACT52_8_PAYLOAD_SHA256", "COMPACT52_1_PAYLOAD_SHA256"):
            with self.subTest(field=name):
                with patch.object(of, name, "e1a0" + "0" * 60):
                    with self.assertRaisesRegex(ValueError,
                                                "COMPACT52_PLACEHOLDER_SHA_REJECTED"):
                        of.require_authoritative()

    def test_registry_disagreement_is_refused(self):
        saved = observe.IMAGES["late_compact528"]
        observe.IMAGES["late_compact528"] = (37380096, "0" * 63 + "1")
        try:
            with self.assertRaisesRegex(ValueError,
                                        "COMPACT52_REGISTRY_AGREEMENT_MISMATCH"):
                of.require_registry_agreement()
        finally:
            observe.IMAGES["late_compact528"] = saved
        of.require_registry_agreement()
        of.require_frozen()
        self.assertEqual(of.member_sha("late_compact528"), of.COMPACT52_8_BOOT_SHA256)

    def test_frozen_gate_rejects_non_hex_and_bad_length(self):
        for bad in ("g" * 64, "a" * 63, None, 37380096):
            with self.subTest(bad=bad):
                _, payloads = synth()
                with patch.dict(of.FROZEN_IDENTITIES,
                                {"late_compact52": {"8": bad, "1": SYNTHETIC_BOOT["1"]}}), \
                        payloads:
                    with self.assertRaisesRegex(ValueError,
                                                "COMPACT52_IDENTITY_NOT_FROZEN"):
                        of.require_frozen()


class GeometryTests(unittest.TestCase):
    def test_frozen_geometry_literals(self):
        for family, expected in FROZEN_GEOMETRY.items():
            spec = of.FAMILIES[family]
            for key, value in expected.items():
                self.assertEqual(spec[key], value, f"{family}.{key}")

    def test_geometry_accepts_frozen_window_only(self):
        for family, spec in of.FAMILIES.items():
            of.validate_geometry(family, spec["window"])
            with self.assertRaisesRegex(ValueError, f"{spec['label']}_56B_WINDOW_REJECTED"):
                of.validate_geometry(family, 56)
            for wrong in (52, 64):
                with self.assertRaisesRegex(ValueError, f"{spec['label']}_WINDOW_NOT_48"):
                    of.validate_geometry(family, wrong)

    def test_selection_policy(self):
        for family in of.FAMILIES:
            of.validate_selection(family)
        drifted = dict(of.FAMILIES["late_compact52"],
                       deviation={"nominal_index": 52, "chosen_index": 52, "distance": 0})
        with patch.dict(of.FAMILIES, {"late_compact52": drifted}):
            with self.assertRaisesRegex(ValueError, "COMPACT52_UNEXPECTED_DEVIATION"):
                of.validate_selection("late_compact52")

    def test_table_identity(self):
        for family in of.FAMILIES:
            of.validate_table(family)
        drifted = dict(of.FAMILIES["late_compact52"], pair_diff=[0x1B87ED0, 0x1B87ED1])
        with patch.dict(of.FAMILIES, {"late_compact52": drifted}):
            with self.assertRaisesRegex(ValueError, "COMPACT52_PAIR_DIFF_DRIFT"):
                of.validate_table("late_compact52")

    def test_table_drift_negatives(self):
        spec = of.FAMILIES["late_compact52"]
        for key, value, token in (("index", 51, "COMPACT52_TABLE_VA_DRIFT"),
                                  ("va", 0xFFFF800081B87EC9, "COMPACT52_TARGET_VA_DRIFT"),
                                  ("prel32_word", "0xffe7bb21", "COMPACT52_PREL32_WORD_DRIFT"),
                                  ("target", "", "COMPACT52_TARGET_VA_DRIFT")):
            with self.subTest(key=key):
                drifted = dict(spec, **{key: value})
                with patch.dict(of.FAMILIES, {"late_compact52": drifted}):
                    with self.assertRaisesRegex(ValueError, token):
                        of.validate_table("late_compact52")

    def test_pair_diff_range_is_delay_word(self):
        for family, spec in of.FAMILIES.items():
            self.assertEqual(of.pair_diff_range(family),
                             [spec["offset"] + 9, spec["offset"] + 11])
            of.require_pair_diff(family, spec["pair_diff"])
            for wrong in ([spec["offset"] + 8, spec["offset"] + 9],
                          [spec["offset"] + 10, spec["offset"] + 11],
                          [0x1B32085, 0x1B32086]):
                with self.subTest(family=family, wrong=wrong):
                    with self.assertRaisesRegex(ValueError,
                                                f"{spec['label']}_PAIR_DIFF_MISMATCH"):
                        of.require_pair_diff(family, wrong)

    def test_pad_class_negatives(self):
        spec = of.FAMILIES["late_compact52"]
        for mutation, token in (
                ({"architecture": "BTI_C_PLUS_56B_ULTRACOMPACT"},
                 "COMPACT52_ARCHITECTURE_DRIFT"),
                ({"entry": "bti c"}, "COMPACT52_ENTRY_NOT_PACIASP"),
                ({"paciasp_word": "0xd5032460"}, "COMPACT52_PACIASP_WORD_DRIFT"),
                ({"tail_size": 8}, "COMPACT52_TAIL_NOT_0"),
                ({"function_size": 60}, "COMPACT52_FUNCTION_NOT_48"),
                ({"daifset": "PRESENT"}, "COMPACT52_DAIFSET_PRESENT")):
            with self.subTest(mutation=mutation):
                drifted = dict(spec, **mutation)
                with patch.dict(of.FAMILIES, {"late_compact52": drifted}):
                    with self.assertRaisesRegex(ValueError, token):
                        of.validate_geometry("late_compact52", 48)


class IdentityTests(unittest.TestCase):
    def test_exact_identity_only(self):
        boots, payloads = synth()
        with boots, payloads:
            for case in of.MEMBERS:
                identity = of.member_identity(case)
                self.assertEqual(identity[0], 37380096)
                of.validate_member(case, *identity)
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    of.validate_member(case, identity[0] + 1, identity[1])
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    of.validate_member(case, identity[0], "0" * 64)
                for sibling in set(of.MEMBERS) - {case}:
                    with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                        of.validate_member(case, *of.member_identity(sibling))

    def test_one_byte_mutants_rejected(self):
        boots, payloads = synth()
        with boots, payloads:
            for case in of.MEMBERS:
                sha = of.member_sha(case)
                first = "1" if sha[0] != "1" else "2"
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    of.validate_member(case, 37380096, first + sha[1:])

    def test_cross_identity_rejection_scale(self):
        boots, payloads = synth()
        rejections = 0
        with boots, payloads:
            for prior, prior_identity in sorted(observe.IMAGES.items()):
                if prior == "recovery" or prior in of.MEMBERS:
                    continue
                for case in of.MEMBERS:
                    with self.subTest(case=case, prior=prior), \
                            self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                        of.validate_member(case, *prior_identity)
                    rejections += 1
        self.assertGreaterEqual(rejections, 100)

    def test_non_compact52_cases_rejected(self):
        for case in ("recovery", "late_compact529", "late_compact52", "late_btic518",
                     "late_btic511", "late_post508", "arch8", "core8", "pure8",
                     "console8", "initcalls8", "smp8", "free8", "kinit8", "rest8",
                     "reset8"):
            with self.subTest(case=case), \
                    self.assertRaisesRegex(ValueError, "CASE_NOT_COMPACT52"):
                of.validate_member(case, 37380096, "a" * 64)

    def test_named_cross_family_identities_rejected(self):
        named = ("late_post508", "late_post501", "late_post498", "late_post491",
                 "late_post438", "late_post431", "late_mid8", "late_high8",
                 "arch8", "arch1", "core8", "core1", "pure8", "console8",
                 "initcalls8", "smp8", "free8", "kinit8", "rest8", "reset8",
                 "waitentry8", "waitret8", "late_devprobe8", "devprobe8",
                 "post398", "post468", "post498", "post518", "fs8", "upper8",
                 "late_btic518", "late_btic511", "subsys8", "subsys1")
        boots, payloads = synth()
        with boots, payloads:
            for prior in named:
                with self.subTest(prior=prior):
                    self.assertIn(prior, observe.IMAGES)
                    for case in of.MEMBERS:
                        with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                            of.validate_member(case, *observe.IMAGES[prior])


class VerdictTests(unittest.TestCase):
    def records(self):
        return of.record("late_compact528", 35.0), of.record("late_compact521", 28.0)

    def test_strong_proves_only_compact52_entry(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline, result = self.records()
            verdict = of.compact52_pair_verdict(baseline, result, "late_compact52")
            self.assertEqual(verdict["verdict"], "STRONG")
            self.assertEqual(verdict["late_compact52_entry"], "PROVEN")
            self.assertEqual(verdict["boot_wait_for_devices_entry"], "PROVEN")
            self.assertEqual(verdict["delta_s"], -7.0)
            self.assertEqual(verdict["expected_delta_s"], -7.0)
            self.assertEqual(verdict["error_s"], 0.0)
            self.assertEqual(verdict["late_initcalls_completed"], "NOT_PROVEN")
            self.assertEqual(verdict["wait_for_initramfs_return"], "NOT_PROVEN")
            self.assertEqual(verdict["console_on_rootfs_entry"], "NOT_PROVEN")
            self.assertEqual(verdict["init_executed"], "NOT_PROVEN")
            self.assertEqual(verdict["usb"], "FROZEN")
            self.assertNotIn("late_compact52_checkpoint_shift_not_observed", verdict)
            self.assertFalse(any("not_reached" in key for key in verdict))

    def test_grade_boundaries(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline = of.record("late_compact528", 35.0)
            for total, verdict, grade in ((27.0, "STRONG", "PROVEN"),
                                          (26.0, "SUPPORTED", "STRONGLY_SUPPORTED"),
                                          (25.9, "SHIFT_NOT_OBSERVED", "NOT_PROVEN"),
                                          (30.0, "SUPPORTED", "STRONGLY_SUPPORTED"),
                                          (30.1, "SHIFT_NOT_OBSERVED", "NOT_PROVEN")):
                with self.subTest(total=total):
                    out = of.compact52_pair_verdict(
                        baseline, of.record("late_compact521", total), "late_compact52")
                    self.assertEqual(out["verdict"], verdict)
                    self.assertEqual(out["late_compact52_entry"], grade)
                    self.assertEqual(out["boot_wait_for_devices_entry"], grade)

    def test_no_shift_records_checkpoint_shift_not_observed_only(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline, _ = self.records()
            out = of.compact52_pair_verdict(baseline, of.record("late_compact521", 35.0),
                                           "late_compact52")
            self.assertEqual(out["verdict"], "SHIFT_NOT_OBSERVED")
            self.assertEqual(out["late_compact52_entry"], "NOT_PROVEN")
            self.assertEqual(out["boot_wait_for_devices_entry"], "NOT_PROVEN")
            self.assertEqual(out["late_compact52_checkpoint_shift_not_observed"], "YES")
            self.assertEqual(out["late_initcalls_completed"], "NOT_PROVEN")
            self.assertFalse(any("not_reached" in key for key in out))

    def broken(self, mutate, message):
        baseline, result = self.records()
        with self.assertRaisesRegex(ValueError, message):
            of.compact52_pair_verdict(mutate(baseline), result, "late_compact52")

    def test_invalid_records_rejected(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline, result = self.records()
            with self.assertRaisesRegex(ValueError, "PAIR_MEMBER_MISMATCH"):
                of.compact52_pair_verdict(baseline, {**result, "case": "late_compact528"},
                                          "late_compact52")
            with self.assertRaisesRegex(ValueError, "PAIR_MEMBER_MISMATCH"):
                of.compact52_pair_verdict(baseline, {**result, "case": "late_post501"},
                                          "late_compact52")
            self.broken(lambda r: {**r, "bootloader_origin": "OTHER"},
                        "PAIR_ORIGIN_MISMATCH")
            self.broken(lambda r: {**r, "protocol": "other"}, "PAIR_PROTOCOL_MISMATCH")
            self.broken(lambda r: {**r, "image_sha256": "0" * 64}, "PAIR_IDENTITY_MISMATCH")
            self.broken(lambda r: {**r, "image_sha256": observe.IMAGES["late_post508"][1]},
                        "PAIR_IDENTITY_MISMATCH")
            self.broken(lambda r: {**r, "status": "STOP"}, "PAIR_RETURN_NOT_VALID")
            self.broken(lambda r: {**r, "final_slot": "a"}, "PAIR_NOT_SLOT_B")
            self.broken(lambda r: {**r, "experimental_boots": 2}, "PAIR_BOOT_COUNT_INVALID")
            self.broken(lambda r: {**r, "context": {}}, "PAIR_CONTEXT_MISMATCH")
            for bad_total in (True, float("inf"), 0, -1.0):
                with self.subTest(bad_total=bad_total), \
                        self.assertRaisesRegex(ValueError, "PAIR_TIMING_INVALID"):
                    of.compact52_pair_verdict(baseline, {**result, "total_s": bad_total},
                                              "late_compact52")


if __name__ == "__main__":
    unittest.main()
