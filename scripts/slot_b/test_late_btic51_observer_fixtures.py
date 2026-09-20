"""Unit tests for the BTIC51 public observer fixtures.

Pure Python only: synthetic identities and timings plus the committed unfrozen
plug-in points in observe.py. No kernel build, no binaries, no device access.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import observe
import late_btic51_observer_fixtures as bf

SYNTHETIC_BOOT = {"8": "a" * 64, "1": "b" * 64}
SYNTHETIC_PAYLOAD = {"8": "c" * 64, "1": "d" * 64}
FROZEN_GEOMETRY = {
    "late_btic51": {"label": "BTIC51", "index": 51, "nominal_index": 51,
                    "target": "setup_vcpu_hotplug_event", "va": 0xFFFF800081B87130,
                    "offset": 0x1B87130, "function_size": 64, "window": 60,
                    "core_size": 56, "architecture": "BTI_C_PLUS_56B_ULTRACOMPACT",
                    "entry": "bti c", "bti_c_word": "0xd503245f", "tail_size": 4,
                    "daifset": "PRESENT", "table_va": 0xFFFF800081D0C3A4,
                    "prel32_word": "0xffe7ad8c", "relative": -1593972,
                    "pair_diff": [0x1B8713D, 0x1B8713E], "deviation": None},
}


def synth():
    return (patch.dict(bf.FROZEN_IDENTITIES, {"late_btic51": SYNTHETIC_BOOT}),
            patch.dict(bf.FROZEN_PAYLOAD_IDENTITIES, {"late_btic51": SYNTHETIC_PAYLOAD}))


class FrozenRegistryTests(unittest.TestCase):
    def test_btic51_routes_registered_in_observe(self):
        self.assertEqual(observe.PAIRS["late_btic511"],
                         ("late_btic518", "late_btic51_entry", "late_initcalls_completed"))
        self.assertIn("late_btic518", observe.ORIGIN_CASES)
        self.assertIn("late_btic511", observe.ORIGIN_CASES)
        frozen = all(isinstance(v, str) and len(v) == 64
                     and all(ch in "0123456789abcdef" for ch in v)
                     for v in (observe.BTIC51_8_BOOT_SHA256, observe.BTIC51_1_BOOT_SHA256))
        if frozen:
            self.assertEqual(observe.IMAGES["late_btic518"][1], observe.BTIC51_8_BOOT_SHA256)
            self.assertEqual(observe.IMAGES["late_btic511"][1], observe.BTIC51_1_BOOT_SHA256)
        else:
            self.assertIsNone(observe.BTIC51_8_BOOT_SHA256)
            self.assertIsNone(observe.BTIC51_1_BOOT_SHA256)
            self.assertNotIn("late_btic518", observe.IMAGES)
            self.assertNotIn("late_btic511", observe.IMAGES)

    def test_fixtures_registry_reexports_observe_plugin_points(self):
        self.assertEqual(bf.FROZEN_IDENTITIES,
                         {"late_btic51": {"8": observe.BTIC51_8_BOOT_SHA256,
                                          "1": observe.BTIC51_1_BOOT_SHA256}})
        self.assertEqual(bf.FROZEN_PAYLOAD_IDENTITIES,
                         {"late_btic51": {"8": observe.BTIC51_8_PAYLOAD_SHA256,
                                          "1": observe.BTIC51_1_PAYLOAD_SHA256}})

    def test_committed_state_is_unfrozen_and_rejected(self):
        frozen = all(isinstance(v, str) and len(v) == 64
                     and all(ch in "0123456789abcdef" for ch in v)
                     for v in (observe.BTIC51_8_BOOT_SHA256, observe.BTIC51_1_BOOT_SHA256,
                               observe.BTIC51_8_PAYLOAD_SHA256, observe.BTIC51_1_PAYLOAD_SHA256))
        if frozen:
            bf.require_frozen()
            self.assertEqual(bf.member_sha("late_btic518"), observe.BTIC51_8_BOOT_SHA256)
            return
        with self.assertRaisesRegex(ValueError, "BTIC51_IDENTITY_NOT_FROZEN"):
            bf.require_frozen()
        with self.assertRaisesRegex(ValueError, "BTIC51_IDENTITY_NOT_FROZEN"):
            bf.member_sha("late_btic518")
        boot_frozen, _ = synth()
        with boot_frozen:
            with self.assertRaisesRegex(ValueError, "BTIC51_IDENTITY_NOT_FROZEN"):
                bf.require_frozen()
        _, payload_frozen = synth()
        with payload_frozen:
            with self.assertRaisesRegex(ValueError, "BTIC51_IDENTITY_NOT_FROZEN"):
                bf.require_frozen()
        boots, payloads = synth()
        with boots, payloads:
            bf.require_frozen()
            self.assertEqual(bf.member_sha("late_btic518"), SYNTHETIC_BOOT["8"])

    def test_frozen_gate_rejects_non_hex_and_bad_length(self):
        for bad in ("g" * 64, "a" * 63, None, 37380096):
            with self.subTest(bad=bad):
                _, payloads = synth()
                with patch.dict(bf.FROZEN_IDENTITIES,
                                {"late_btic51": {"8": bad, "1": SYNTHETIC_BOOT["1"]}}), \
                        payloads:
                    with self.assertRaisesRegex(ValueError,
                                                "BTIC51_IDENTITY_NOT_FROZEN"):
                        bf.require_frozen()


class GeometryTests(unittest.TestCase):
    def test_frozen_geometry_literals(self):
        for family, expected in FROZEN_GEOMETRY.items():
            spec = bf.FAMILIES[family]
            for key, value in expected.items():
                self.assertEqual(spec[key], value, f"{family}.{key}")

    def test_geometry_accepts_frozen_window_only(self):
        for family, spec in bf.FAMILIES.items():
            bf.validate_geometry(family, spec["window"])
            with self.assertRaisesRegex(ValueError, f"{spec['label']}_56B_WINDOW_REJECTED"):
                bf.validate_geometry(family, 56)
            for wrong in (52, 64):
                with self.assertRaisesRegex(ValueError, f"{spec['label']}_WINDOW_NOT_60"):
                    bf.validate_geometry(family, wrong)

    def test_selection_policy(self):
        for family in bf.FAMILIES:
            bf.validate_selection(family)
        drifted = dict(bf.FAMILIES["late_btic51"],
                       deviation={"nominal_index": 51, "chosen_index": 51, "distance": 0})
        with patch.dict(bf.FAMILIES, {"late_btic51": drifted}):
            with self.assertRaisesRegex(ValueError, "BTIC51_UNEXPECTED_DEVIATION"):
                bf.validate_selection("late_btic51")

    def test_table_identity(self):
        for family in bf.FAMILIES:
            bf.validate_table(family)
        drifted = dict(bf.FAMILIES["late_btic51"], pair_diff=[0x1B8713C, 0x1B8713D])
        with patch.dict(bf.FAMILIES, {"late_btic51": drifted}):
            with self.assertRaisesRegex(ValueError, "BTIC51_PAIR_DIFF_DRIFT"):
                bf.validate_table("late_btic51")

    def test_table_drift_negatives(self):
        spec = bf.FAMILIES["late_btic51"]
        for key, value, token in (("index", 50, "BTIC51_TABLE_VA_DRIFT"),
                                  ("va", 0xFFFF800081B87131, "BTIC51_TARGET_VA_DRIFT"),
                                  ("prel32_word", "0xffe7ad8d", "BTIC51_PREL32_WORD_DRIFT"),
                                  ("target", "", "BTIC51_TARGET_VA_DRIFT")):
            with self.subTest(key=key):
                drifted = dict(spec, **{key: value})
                with patch.dict(bf.FAMILIES, {"late_btic51": drifted}):
                    with self.assertRaisesRegex(ValueError, token):
                        bf.validate_table("late_btic51")

    def test_pair_diff_range_is_delay_word(self):
        for family, spec in bf.FAMILIES.items():
            self.assertEqual(bf.pair_diff_range(family),
                             [spec["offset"] + 13, spec["offset"] + 15])
            bf.require_pair_diff(family, spec["pair_diff"])
            for wrong in ([spec["offset"] + 12, spec["offset"] + 13],
                          [spec["offset"] + 14, spec["offset"] + 15],
                          [0x1B32085, 0x1B32086]):
                with self.subTest(family=family, wrong=wrong):
                    with self.assertRaisesRegex(ValueError,
                                                f"{spec['label']}_PAIR_DIFF_MISMATCH"):
                        bf.require_pair_diff(family, wrong)

    def test_pad_class_negatives(self):
        spec = bf.FAMILIES["late_btic51"]
        for mutation, token in (
                ({"architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT"},
                 "BTIC51_ARCHITECTURE_DRIFT"),
                ({"entry": "paciasp"}, "BTIC51_ENTRY_NOT_BTI_C"),
                ({"bti_c_word": "0xd5032460"}, "BTIC51_BTI_C_WORD_DRIFT"),
                ({"tail_size": 8}, "BTIC51_TAIL_NOT_4"),
                ({"function_size": 60}, "BTIC51_FUNCTION_NOT_64"),
                ({"daifset": "ABSENT"}, "BTIC51_DAIFSET_ABSENT")):
            with self.subTest(mutation=mutation):
                drifted = dict(spec, **mutation)
                with patch.dict(bf.FAMILIES, {"late_btic51": drifted}):
                    with self.assertRaisesRegex(ValueError, token):
                        bf.validate_geometry("late_btic51", 60)


class IdentityTests(unittest.TestCase):
    def test_exact_identity_only(self):
        boots, payloads = synth()
        with boots, payloads:
            for case in bf.MEMBERS:
                identity = bf.member_identity(case)
                self.assertEqual(identity[0], 37380096)
                bf.validate_member(case, *identity)
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    bf.validate_member(case, identity[0] + 1, identity[1])
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    bf.validate_member(case, identity[0], "0" * 64)
                for sibling in set(bf.MEMBERS) - {case}:
                    with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                        bf.validate_member(case, *bf.member_identity(sibling))

    def test_one_byte_mutants_rejected(self):
        boots, payloads = synth()
        with boots, payloads:
            for case in bf.MEMBERS:
                sha = bf.member_sha(case)
                first = "1" if sha[0] != "1" else "2"
                with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                    bf.validate_member(case, 37380096, first + sha[1:])

    def test_cross_identity_rejection_scale(self):
        boots, payloads = synth()
        rejections = 0
        with boots, payloads:
            for prior, prior_identity in sorted(observe.IMAGES.items()):
                if prior == "recovery" or prior in bf.MEMBERS:
                    continue
                for case in bf.MEMBERS:
                    with self.subTest(case=case, prior=prior), \
                            self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                        bf.validate_member(case, *prior_identity)
                    rejections += 1
        self.assertGreaterEqual(rejections, 100)

    def test_non_btic51_cases_rejected(self):
        for case in ("recovery", "late_post508", "late_post501", "post498", "post431",
                     "post511", "arch8", "core8", "pure8", "console8", "initcalls8",
                     "smp8", "free8", "kinit8", "rest8", "reset8", "late_btic519",
                     "late_btic51"):
            with self.subTest(case=case), \
                    self.assertRaisesRegex(ValueError, "CASE_NOT_BTIC51"):
                bf.validate_member(case, 37380096, "a" * 64)

    def test_named_cross_family_identities_rejected(self):
        named = ("late_post508", "late_post501", "late_post498", "late_post491",
                 "late_post438", "late_post431", "late_mid8", "late_high8",
                 "arch8", "arch1", "core8", "core1", "pure8", "console8",
                 "initcalls8", "smp8", "free8", "kinit8", "rest8", "reset8",
                 "waitentry8", "waitret8", "late_devprobe8", "devprobe8",
                 "post398", "post468", "post498", "post518", "fs8", "upper8")
        boots, payloads = synth()
        with boots, payloads:
            for prior in named:
                with self.subTest(prior=prior):
                    self.assertIn(prior, observe.IMAGES)
                    for case in bf.MEMBERS:
                        with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                            bf.validate_member(case, *observe.IMAGES[prior])


class VerdictTests(unittest.TestCase):
    def records(self):
        return bf.record("late_btic518", 35.0), bf.record("late_btic511", 28.0)

    def test_strong_proves_only_btic51_entry(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline, result = self.records()
            verdict = bf.btic51_pair_verdict(baseline, result, "late_btic51")
            self.assertEqual(verdict["verdict"], "STRONG")
            self.assertEqual(verdict["late_btic51_entry"], "PROVEN")
            self.assertEqual(verdict["setup_vcpu_hotplug_event_entry"], "PROVEN")
            self.assertEqual(verdict["delta_s"], -7.0)
            self.assertEqual(verdict["expected_delta_s"], -7.0)
            self.assertEqual(verdict["error_s"], 0.0)
            self.assertEqual(verdict["late_initcalls_completed"], "NOT_PROVEN")
            self.assertEqual(verdict["wait_for_initramfs_return"], "NOT_PROVEN")
            self.assertEqual(verdict["console_on_rootfs_entry"], "NOT_PROVEN")
            self.assertEqual(verdict["init_executed"], "NOT_PROVEN")
            self.assertEqual(verdict["usb"], "FROZEN")
            self.assertNotIn("late_btic51_checkpoint_shift_not_observed", verdict)
            self.assertFalse(any("not_reached" in key for key in verdict))

    def test_grade_boundaries(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline = bf.record("late_btic518", 35.0)
            for total, verdict, grade in ((27.0, "STRONG", "PROVEN"),
                                          (26.0, "SUPPORTED", "STRONGLY_SUPPORTED"),
                                          (25.9, "SHIFT_NOT_OBSERVED", "NOT_PROVEN"),
                                          (30.0, "SUPPORTED", "STRONGLY_SUPPORTED"),
                                          (30.1, "SHIFT_NOT_OBSERVED", "NOT_PROVEN")):
                with self.subTest(total=total):
                    out = bf.btic51_pair_verdict(
                        baseline, bf.record("late_btic511", total), "late_btic51")
                    self.assertEqual(out["verdict"], verdict)
                    self.assertEqual(out["late_btic51_entry"], grade)
                    self.assertEqual(out["setup_vcpu_hotplug_event_entry"], grade)

    def test_no_shift_records_checkpoint_shift_not_observed_only(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline, _ = self.records()
            out = bf.btic51_pair_verdict(baseline, bf.record("late_btic511", 35.0),
                                         "late_btic51")
            self.assertEqual(out["verdict"], "SHIFT_NOT_OBSERVED")
            self.assertEqual(out["late_btic51_entry"], "NOT_PROVEN")
            self.assertEqual(out["setup_vcpu_hotplug_event_entry"], "NOT_PROVEN")
            self.assertEqual(out["late_btic51_checkpoint_shift_not_observed"], "YES")
            self.assertEqual(out["late_initcalls_completed"], "NOT_PROVEN")
            self.assertFalse(any("not_reached" in key for key in out))

    def broken(self, mutate, message):
        baseline, result = self.records()
        with self.assertRaisesRegex(ValueError, message):
            bf.btic51_pair_verdict(mutate(baseline), result, "late_btic51")

    def test_invalid_records_rejected(self):
        boots, payloads = synth()
        with boots, payloads:
            baseline, result = self.records()
            with self.assertRaisesRegex(ValueError, "PAIR_MEMBER_MISMATCH"):
                bf.btic51_pair_verdict(baseline, {**result, "case": "late_btic518"},
                                       "late_btic51")
            with self.assertRaisesRegex(ValueError, "PAIR_MEMBER_MISMATCH"):
                bf.btic51_pair_verdict(baseline, {**result, "case": "late_post501"},
                                       "late_btic51")
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
                    bf.btic51_pair_verdict(baseline, {**result, "total_s": bad_total},
                                           "late_btic51")


if __name__ == "__main__":
    unittest.main()
