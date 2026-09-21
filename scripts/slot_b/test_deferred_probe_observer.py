import json
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import observe as o

IDENTITY = json.loads(Path(__file__).with_name("deferred_probe_identities.json").read_text())


class DeferredObserverTests(unittest.TestCase):
    def record(self, case, total):
        return {"protocol": o.PROTOCOL, "case": case, "image_sha256": o.IMAGES[case][1],
                "context": o.CONTEXT, "status": "AUTOMATIC_FASTBOOT_RETURN",
                "bootloader_origin": o.REST_ORIGIN, "final_slot": "b",
                "experimental_boots": 1, "total_s": total}

    def test_independent_identity_registry_agreement(self):
        shas = []
        self.assertEqual(IDENTITY["public_run"], "35553769346")
        for stage, spec in IDENTITY["stages"].items():
            for delay, member in spec["members"].items():
                case = f"defer_{stage}{delay}"
                self.assertEqual(o.IMAGES[case], (IDENTITY["boot_size"], member["boot_sha256"]))
                self.assertIn(case, o.ORIGIN_CASES)
                for sha in member.values():
                    self.assertRegex(sha, r"^[0-9a-f]{64}$")
                    self.assertGreater(len(set(sha)), 8)
                    shas.append(sha)
        self.assertEqual(len(set(shas)), 8)

    def test_cross_identity_and_mutant_rejection(self):
        for stage, spec in IDENTITY["stages"].items():
            for delay, member in spec["members"].items():
                case = f"defer_{stage}{delay}"
                o.validate_identity(case, 37380096, member["boot_sha256"])
                for other, identity in o.IMAGES.items():
                    if other != case:
                        with self.subTest(case=case, other=other), self.assertRaises(ValueError):
                            o.validate_identity(case, *identity)
                with self.assertRaises(ValueError):
                    o.validate_identity(case, 37380095, member["boot_sha256"])
                with self.assertRaises(ValueError):
                    o.validate_identity(case, 37380096, "0" * 64)

    def test_strong_and_no_shift_boundaries(self):
        for stage in IDENTITY["stages"]:
            first, second = f"defer_{stage}8", f"defer_{stage}1"
            proof, unproved = o.PAIRS[second][1:]
            baseline = self.record(first, 35.4)
            result = self.record(second, 28.4)
            verdict = o.pair_verdict(baseline, result)
            self.assertEqual(verdict[proof], "PROVEN")
            self.assertEqual(verdict[unproved], "NOT_PROVEN")
            for key in ("init_executed", "late_initcalls_completed", "wait_for_initramfs_return"):
                self.assertEqual(verdict[key], "NOT_PROVEN")
            no_shift = o.pair_verdict(baseline, self.record(second, 35.4))
            self.assertEqual(no_shift[proof], "NOT_PROVEN")
            self.assertEqual(no_shift["verdict"], "SHIFT_NOT_OBSERVED")
            self.assertEqual(no_shift["deferred_callsite_shift_not_observed"], "YES")
            for key, value in (("status", "NO_RETURN_WITHIN_120S"), ("final_slot", "a"),
                               ("experimental_boots", 2), ("total_s", float("nan")),
                               ("bootloader_origin", "unknown"), ("context", {})):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    o.pair_verdict({**baseline, key: value}, result)

    def test_each_new_case_rejects_slot_a_and_second_boot(self):
        for stage in IDENTITY["stages"]:
            for delay in (8, 1):
                observer = o.Observer(Namespace(serial="fixture", case=f"defer_{stage}{delay}",
                                                image=Path("fixture.img")))
                with patch.object(observer, "getvar", return_value="a"), \
                        patch.object(o.subprocess, "Popen") as spawn:
                    with self.assertRaisesRegex(ValueError, "SLOT_NOT_B"):
                        observer.launch()
                    spawn.assert_not_called()
                observer.boots = 1
                with patch.object(o.subprocess, "Popen") as spawn:
                    with self.assertRaisesRegex(ValueError, "SECOND_EXPERIMENTAL_BOOT"):
                        observer.launch()
                    spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
