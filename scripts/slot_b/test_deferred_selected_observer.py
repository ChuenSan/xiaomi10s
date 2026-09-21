import copy
import json
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import deferred_selected_identity_agreement as agreement
import observe as o

IDENTITY = json.loads(Path(__file__).with_name("deferred_selected_identities.json").read_text())
CASES = ("defer_selected8", "defer_selected1")
PROVEN_FIELDS = ("deferred_worker_device_pointer_loaded", "mutex_acquired", "active_list_nonempty")
UNPROVEN_FIELDS = ("deferred_device_pointer_valid", "deferred_device_name",
                   "deferred_get_device_entered", "deferred_get_device_returned",
                   "deferred_first_bus_probe_entered", "deferred_first_bus_probe_returned",
                   "deferred_culprit_driver", "late_initcalls_completed",
                   "wait_for_initramfs_return", "console_on_rootfs_entry", "init_executed")


class SelectedObserverTests(unittest.TestCase):
    def record(self, case, total):
        return {"protocol": o.PROTOCOL, "case": case, "image_sha256": o.IMAGES[case][1],
                "context": dict(o.CONTEXT), "status": "AUTOMATIC_FASTBOOT_RETURN",
                "bootloader_origin": o.REST_ORIGIN, "final_slot": "b",
                "experimental_boots": 1, "total_s": total, "ci_run": IDENTITY["private_run"]}

    def records(self):
        return self.record(CASES[0], 35.0), self.record(CASES[1], 28.0)

    def observer(self, case):
        return o.Observer(Namespace(serial="fixture", case=case, image=Path("fixture.img")))

    def test_real_frozen_identity_registry_agreement(self):
        agreement.validate_frozen(IDENTITY)
        self.assertEqual(o.PAIRS[CASES[1]],
                         (CASES[0], PROVEN_FIELDS[0], "deferred_first_bus_probe_entered"))
        for delay, identity in IDENTITY["members"].items():
            case = f"defer_selected{delay}"
            self.assertEqual(o.IMAGES[case], (37380096, identity["boot_sha256"]))
            self.assertEqual(identity["boot_size"], IDENTITY["boot_size"])
            self.assertIn(case, o.ORIGIN_CASES)
            o.validate_identity(case, identity["boot_size"], identity["boot_sha256"])

    def test_cross_family_hash_and_size_rejection(self):
        for case in CASES:
            size, digest = o.IMAGES[case]
            for other, identity in o.IMAGES.items():
                if other != case:
                    with self.subTest(case=case, other=other), self.assertRaises(ValueError):
                        o.validate_identity(case, *identity)
            for bad_size, bad_hash in ((size - 1, digest), (size + 1, digest),
                                       (size, "0" * 64), (size, digest[:-1]),
                                       (size, digest.upper())):
                with self.subTest(case=case, size=bad_size, sha=bad_hash), self.assertRaises(ValueError):
                    o.validate_identity(case, bad_size, bad_hash)

    def test_incomplete_freeze_blocks_both_launches_and_verdicts(self):
        records = self.records()
        for excluded in ((CASES[0],), (CASES[1],), CASES):
            images = {case: identity for case, identity in o.IMAGES.items() if case not in excluded}
            with self.subTest(excluded=excluded), patch.dict(o.IMAGES, images, clear=True):
                with self.assertRaisesRegex(ValueError, "SELECTED_IDENTITY_NOT_FROZEN"):
                    o.pair_verdict(*records)
                for case in CASES:
                    identity = IDENTITY["members"][case[-1]]
                    with self.assertRaisesRegex(ValueError, "SELECTED_IDENTITY_NOT_FROZEN"):
                        o.validate_identity(case, identity["boot_size"], identity["boot_sha256"])
                    observer = self.observer(case)
                    with patch.object(observer, "getvar") as getvar, \
                            patch.object(o.subprocess, "Popen") as spawn:
                        with self.assertRaisesRegex(ValueError, "SELECTED_IDENTITY_NOT_FROZEN"):
                            observer.launch()
                        getvar.assert_not_called()
                        spawn.assert_not_called()
                        self.assertEqual(observer.boots, 0)

    def test_corrupt_or_colliding_registration_blocks_launch(self):
        size, digest = o.IMAGES[CASES[0]]
        for identity in ((size - 1, digest), (size, "0" * 64), o.IMAGES[CASES[1]]):
            with self.subTest(identity=identity), patch.dict(o.IMAGES, {CASES[0]: identity}):
                for case in CASES:
                    observer = self.observer(case)
                    with patch.object(observer, "getvar") as getvar, \
                            patch.object(o.subprocess, "Popen") as spawn:
                        with self.assertRaises(ValueError):
                            observer.launch()
                        getvar.assert_not_called()
                        spawn.assert_not_called()

    def test_slot_a_and_second_boot_rejected_before_spawn(self):
        for case in CASES:
            observer = self.observer(case)
            with patch.object(observer, "getvar", return_value="a"), \
                    patch.object(o.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "LAST_MOMENT_SLOT_NOT_B"):
                    observer.launch()
                spawn.assert_not_called()
                self.assertEqual(observer.boots, 0)
            observer.boots = 1
            with patch.object(observer, "getvar") as getvar, patch.object(o.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "SECOND_EXPERIMENTAL_BOOT_FORBIDDEN"):
                    observer.launch()
                getvar.assert_not_called()
                spawn.assert_not_called()

    def test_only_matched_pair_grades_prefix_and_never_later_operations(self):
        baseline, result = self.records()
        for error, verdict, grade in ((0.0, "STRONG", "PROVEN"),
                                      (-1.0, "STRONG", "PROVEN"), (1.0, "STRONG", "PROVEN"),
                                      (-1.0001, "SUPPORTED", "SUPPORTED"), (1.0001, "SUPPORTED", "SUPPORTED"),
                                      (-2.0, "SUPPORTED", "SUPPORTED"), (2.0, "SUPPORTED", "SUPPORTED"),
                                      (-2.0001, "SHIFT_NOT_OBSERVED", "NOT_PROVEN"),
                                      (2.0001, "SHIFT_NOT_OBSERVED", "NOT_PROVEN")):
            with self.subTest(error=error):
                out = o.pair_verdict(baseline, {**result, "total_s": 28.0 + error})
                self.assertEqual(out["verdict"], verdict)
                self.assertEqual(out["expected_delta_s"], -7.0)
                for key in PROVEN_FIELDS:
                    self.assertEqual(out[key], grade)
                for key in UNPROVEN_FIELDS:
                    self.assertEqual(out[key], "NOT_PROVEN")
                self.assertEqual(out["usb"], "FROZEN")
                self.assertEqual(out.get("deferred_selected_shift_not_observed"),
                                 "YES" if verdict == "SHIFT_NOT_OBSERVED" else None)

    def test_negative_return_cluster_does_not_prove_selection(self):
        for first, second in ((48.591122792, 48.346502500), (48.5, 48.5), (35.0, 35.0)):
            out = o.pair_verdict(self.record(CASES[0], first), self.record(CASES[1], second))
            self.assertEqual(out["verdict"], "SHIFT_NOT_OBSERVED")
            for key in PROVEN_FIELDS + UNPROVEN_FIELDS:
                self.assertEqual(out[key], "NOT_PROVEN")
            self.assertNotIn("never_executed", out)

    def test_missing_mismatched_and_reversed_references_rejected(self):
        baseline, result = self.records()
        with self.assertRaises(ValueError):
            o.pair_verdict(result, baseline)
        for side in (0, 1):
            for key in ("protocol", "case", "image_sha256", "bootloader_origin", "context",
                        "status", "final_slot", "experimental_boots", "total_s"):
                records = [dict(baseline), dict(result)]
                records[side] = {name: value for name, value in records[side].items() if name != key}
                with self.subTest(side=side, missing=key), self.assertRaises(ValueError):
                    o.pair_verdict(*records)
            records = [dict(baseline), dict(result)]
            records[side]["case"] = "defer_worker8" if side == 0 else "defer_worker1"
            with self.subTest(side=side, cross_family=True), self.assertRaises(ValueError):
                o.pair_verdict(*records)

    def test_invalid_records_reject_both_members(self):
        mutations = (("protocol", "other"), ("image_sha256", o.IMAGES["defer_worker8"][1]),
                     ("bootloader_origin", "unknown"), ("context", {}), ("final_slot", "a"),
                     ("experimental_boots", 0), ("experimental_boots", 2),
                     ("experimental_boots", True), ("experimental_boots", 1.0),
                     ("status", "NO_RETURN_WITHIN_120S"), ("status", "UNEXPECTED_ADB_RETURN"),
                     ("status", "STOP"), ("status", "MANUAL_FASTBOOT_RETURN"),
                     ("total_s", float("nan")), ("total_s", float("inf")),
                     ("total_s", float("-inf")), ("total_s", True), ("total_s", False),
                     ("total_s", 0), ("total_s", -1), ("total_s", "28"), ("total_s", None))
        for side in (0, 1):
            for key, value in mutations:
                records = list(self.records())
                records[side] = {**records[side], key: value}
                with self.subTest(side=side, key=key, value=value), self.assertRaises(ValueError):
                    o.pair_verdict(*records)

    def test_selected_context_requires_origin_and_verified_protection(self):
        context = {**o.CONTEXT, "bootloader_origin": o.REST_ORIGIN,
                   "slot_a_unchanged": True, "readback_verified": True}
        for case in CASES:
            o.validate_context(context, case)
            for key in context:
                with self.subTest(case=case, key=key), self.assertRaises(ValueError):
                    o.validate_context({**context, key: None}, case)

    def test_reference_validation_precedes_device_commands(self):
        baseline, _ = self.records()
        context = {**o.CONTEXT, "bootloader_origin": o.REST_ORIGIN,
                   "slot_a_unchanged": True, "readback_verified": True}
        for reference in (None, {**baseline, "status": "NO_RETURN_WITHIN_120S"},
                          {**baseline, "case": "defer_worker8"},
                          {**baseline, "image_sha256": o.IMAGES["defer_worker8"][1]}):
            observer = o.Observer(Namespace(serial="fixture", case=CASES[1], image=Path("fixture.img"),
                                            context=Path("context.json"), output=Path("unused-output"),
                                            ci_run=IDENTITY["private_run"],
                                            baseline=Path("reference.json") if reference else None))
            reads = [json.dumps(context), json.dumps(reference)]
            with self.subTest(reference=reference), \
                    patch.object(Path, "read_bytes", return_value=b"fixture"), \
                    patch.object(Path, "read_text", side_effect=reads), \
                    patch.object(Path, "mkdir") as mkdir, patch.object(Path, "write_text"), \
                    patch.object(o, "validate_identity"), patch.object(observer, "getvar") as getvar, \
                    patch.object(o.subprocess, "Popen") as spawn:
                with self.assertRaises(ValueError):
                    observer.run()
                mkdir.assert_not_called()
                getvar.assert_not_called()
                spawn.assert_not_called()

    def test_freeze_geometry_and_authority_mutants_rejected(self):
        for key, value in (("stage", "worker"), ("offset", 0x8E8428), ("window", 96),
                           ("parent_offset", 0x8E7564), ("parent_size", 492),
                           ("boot_size", 37380095), ("source_commit", "HEAD"),
                           ("private_commit", "0" * 40), ("public_run", 1),
                           ("private_run", "0"), ("members", {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                agreement.validate_frozen({**IDENTITY, key: value})
        for delay in ("8", "1"):
            for key, value in (("boot_size", 37380095), ("boot_sha256", "0" * 64),
                               ("payload_sha256", "not-a-sha")):
                frozen = copy.deepcopy(IDENTITY)
                frozen["members"][delay][key] = value
                with self.subTest(delay=delay, key=key), self.assertRaises(ValueError):
                    agreement.validate_frozen(frozen)
        frozen = copy.deepcopy(IDENTITY)
        frozen["members"]["1"]["boot_sha256"] = frozen["members"]["8"]["boot_sha256"]
        with self.assertRaisesRegex(ValueError, "HASH_COLLISION"):
            agreement.validate_frozen(frozen)


if __name__ == "__main__":
    unittest.main()
