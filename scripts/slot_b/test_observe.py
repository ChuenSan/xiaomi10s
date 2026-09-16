import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import observe


class SafetyTests(unittest.TestCase):
    def values(self):
        return {"product": "thyme", "unlocked": "yes", "current-slot": "b",
                "slot-count": "2", "snapshot-update-status": "none",
                "battery-soc-ok": "yes", "slot-unbootable:b": "no",
                "slot-successful:a": "yes", "slot-retry-count:b": "7",
                "max-download-size": "0x10000000"}

    def record(self, case, total):
        return {"protocol": observe.PROTOCOL, "case": case,
                "image_sha256": observe.IMAGES[case][1], "context": observe.CONTEXT,
                "status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": "b",
                "experimental_boots": 1, "total_s": total}

    def test_exact_images_only(self):
        for case, identity in observe.IMAGES.items():
            observe.validate_identity(case, *identity)
            with self.assertRaises(ValueError):
                observe.validate_identity(case, identity[0] + 1, identity[1])
            with self.assertRaises(ValueError):
                observe.validate_identity(case, identity[0], "0" * 64)
            for sibling in set(observe.IMAGES) - {case}:
                with self.assertRaises(ValueError):
                    observe.validate_identity(case, *observe.IMAGES[sibling])

    def test_slot_b_preflight(self):
        observe.validate_preflight(self.values(), observe.IMAGES["reset8"][0])
        bad_values = {"product": "other", "unlocked": "no", "current-slot": "a",
                      "slot-count": "1", "snapshot-update-status": "merging",
                      "battery-soc-ok": "no", "slot-unbootable:b": "yes",
                      "slot-successful:a": "no", "slot-retry-count:b": "1",
                      "max-download-size": "0"}
        for key, value in bad_values.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                observe.validate_preflight({**self.values(), key: value}, 37380096)
        for key in self.values():
            values = self.values()
            values.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                observe.validate_preflight(values, 37380096)

    def test_slot_a_never_launches(self):
        observer = observe.Observer(Namespace(serial="test-device", case="reset8", image=Path("boot.img")))
        with patch.object(observer, "getvar", return_value="a"), patch.object(observe.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "SLOT_NOT_B"):
                observer.launch()
            spawn.assert_not_called()
            self.assertEqual(observer.boots, 0)

    def test_second_boot_never_launches(self):
        observer = observe.Observer(Namespace(serial="test-device", case="reset8", image=Path("boot.img")))
        observer.boots = 1
        with patch.object(observe.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "SECOND_EXPERIMENTAL_BOOT"):
                observer.launch()
            spawn.assert_not_called()

    def test_recovery_is_not_an_experimental_boot(self):
        for case in observe.IMAGES:
            observer = observe.Observer(Namespace(serial="test-device", case=case))
            self.assertEqual(observer.boot_counts()["host_boot_commands"], 0)
            observer.boots = 1
            counts = observer.boot_counts()
            self.assertEqual(counts["host_boot_commands"], 1)
            self.assertEqual(counts["experimental_boots"], 0 if case == "recovery" else 1)
            self.assertEqual(counts["recovery_control_boots"], 1 if case == "recovery" else 0)

    def test_no_return_blocks_reset1(self):
        for status in ("NO_RETURN_WITHIN_120S", "UNEXPECTED_ADB_RETURN", "STOP"):
            baseline = {**self.record("reset8", 50.0), "status": status}
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "PAIR_RETURN_NOT_VALID"):
                observe.pair_verdict(baseline, self.record("reset1", 43.0))

    def test_context_requires_readback_and_a_protection(self):
        context = {**observe.CONTEXT, "readback_verified": True, "slot_a_unchanged": True}
        observe.validate_context(context)
        for key in context:
            with self.subTest(key=key), self.assertRaises(ValueError):
                observe.validate_context({**context, key: None})

    def test_rest_origin_must_be_recorded(self):
        context = {**observe.CONTEXT, "readback_verified": True, "slot_a_unchanged": True}
        for case in ("rest8", "rest1"):
            with self.assertRaisesRegex(ValueError, "ORIGIN_MISMATCH"):
                observe.validate_context(context, case)
            observe.validate_context({**context, "bootloader_origin": observe.REST_ORIGIN}, case)

    def test_rest_pair_proves_entry_only(self):
        baseline = {**self.record("rest8", 35.4), "bootloader_origin": observe.REST_ORIGIN}
        result = {**self.record("rest1", 28.5), "bootloader_origin": observe.REST_ORIGIN}
        verdict = observe.pair_verdict(baseline, result)
        self.assertEqual(verdict["rest_init_entry"], "PROVEN")
        self.assertEqual(verdict["rest_init_body"], "NOT_PROVEN")
        self.assertEqual(verdict["init_executed"], "NOT_PROVEN")
        self.assertNotIn("machine_restart_entry", verdict)
        for invalid in ({**baseline, "bootloader_origin": "P15_RESTART2"},
                        {**baseline, "status": "NO_RETURN_WITHIN_120S"},
                        self.record("reset8", 35.4)):
            with self.assertRaises(ValueError):
                observe.pair_verdict(invalid, result)

    def test_pair_delta_not_old_slot_a_absolute_timing(self):
        baseline = self.record("reset8", 50.0)
        strong = observe.pair_verdict(baseline, self.record("reset1", 43.1))
        self.assertEqual(strong["verdict"], "STRONG")
        self.assertEqual(strong["machine_restart_entry"], "PROVEN")
        self.assertEqual(strong["original_restart_body"], "NOT_PROVEN")
        self.assertEqual(strong["init_executed"], "NOT_PROVEN")
        self.assertEqual(observe.pair_verdict(baseline, self.record("reset1", 44.5))["verdict"], "SUPPORTED")
        self.assertEqual(observe.pair_verdict(baseline, self.record("reset1", 49.8))["verdict"], "SHIFT_NOT_OBSERVED")

    def test_invalid_pair_never_proves_entry(self):
        baseline = self.record("reset8", 50.0)
        invalid = {"protocol": "old-slot-a", "case": "reset8", "image_sha256": "0" * 64,
                   "context": {}, "status": "MANUAL_RECOVERY", "final_slot": "a",
                   "experimental_boots": 2, "total_s": float("nan")}
        for key, value in invalid.items():
            result = {**self.record("reset1", 43.0), key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                observe.pair_verdict(baseline, result)
        with self.assertRaises(ValueError):
            observe.pair_verdict({**baseline, "total_s": None}, self.record("reset1", 43.0))


if __name__ == "__main__":
    unittest.main()
