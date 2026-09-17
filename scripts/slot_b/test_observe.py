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
        for case in observe.ORIGIN_CASES:
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

    def test_pid1_stage_pairs_prove_only_the_selected_entry(self):
        for second, (first, proof, unproved) in observe.PAIRS.items():
            if second in ("reset1", "rest1"):
                continue
            with self.subTest(stage=second):
                baseline = {**self.record(first, 35.4), "bootloader_origin": observe.REST_ORIGIN}
                result = {**self.record(second, 28.5), "bootloader_origin": observe.REST_ORIGIN}
                verdict = observe.pair_verdict(baseline, result)
                self.assertEqual(verdict[proof], "PROVEN")
                self.assertEqual(verdict[unproved], "NOT_PROVEN")
                self.assertEqual(verdict["init_executed"], "NOT_PROVEN")
                self.assertNotIn("rest_init_entry", verdict)
                for invalid in ({**baseline, "bootloader_origin": "P15_RESTART2"},
                                {**baseline, "status": "NO_RETURN_WITHIN_120S"},
                                {**baseline, "final_slot": "a"},
                                {**baseline, "case": "rest8"},
                                {**baseline, "image_sha256": observe.IMAGES["rest8"][1]}):
                    with self.assertRaises(ValueError):
                        observe.pair_verdict(invalid, result)

    def test_core_pair_proof_boundary_and_no_shift_route(self):
        baseline = {**self.record("core8", 35.0),
                    "bootloader_origin": observe.REST_ORIGIN}
        strong = {**self.record("core1", 28.0),
                  "bootloader_origin": observe.REST_ORIGIN}
        verdict = observe.pair_verdict(baseline, strong)
        self.assertEqual(verdict["verdict"], "STRONG")
        self.assertEqual(verdict["core_initcalls_completed"], "PROVEN")
        self.assertEqual(verdict["first_postcore_initcall_entry"], "PROVEN")
        self.assertEqual(verdict["first_postcore_initcall_body"], "NOT_PROVEN")
        self.assertEqual(verdict["postcore_initcalls_completed"], "NOT_PROVEN")
        self.assertEqual(verdict["console_on_rootfs_entry"], "NOT_PROVEN")
        supported = {**self.record("core1", 26.5),
                     "bootloader_origin": observe.REST_ORIGIN}
        supported_verdict = observe.pair_verdict(baseline, supported)
        self.assertEqual(supported_verdict["verdict"], "SUPPORTED")
        self.assertEqual(supported_verdict["core_initcalls_completed"],
                         "STRONGLY_SUPPORTED")
        self.assertEqual(supported_verdict["first_postcore_initcall_entry"],
                         "STRONGLY_SUPPORTED")
        self.assertEqual(supported_verdict["first_postcore_initcall_body"],
                         "NOT_PROVEN")
        no_shift = {**self.record("core1", 35.0),
                    "bootloader_origin": observe.REST_ORIGIN}
        miss = observe.pair_verdict(baseline, no_shift)
        self.assertEqual(miss["core_initcalls_completed"], "NOT_PROVEN")
        self.assertEqual(miss["core_initcalls_checkpoint_shift_not_observed"], "YES")
        self.assertEqual(miss["next"], "CORE_INITCALLS_FAILURE_ISOLATION_CI")
        self.assertNotIn("core_initcalls_completed", baseline)

        with self.assertRaisesRegex(ValueError, "PAIR_TIMING_INVALID"):
            observe.pair_verdict({**baseline, "total_s": True}, strong)
        with self.assertRaisesRegex(ValueError, "PAIR_TIMING_INVALID"):
            observe.pair_verdict(baseline, {**strong, "total_s": False})

    def test_core_member_full_sha_gates_are_distinct(self):
        size8, sha8 = observe.IMAGES["core8"]
        size1, sha1 = observe.IMAGES["core1"]
        self.assertEqual(size8, size1)
        self.assertEqual(sha8, "5d7d5b88668e1925e3a79c677c2b630bb81d66135fec2761016de1da52fd7272")
        self.assertEqual(sha1, "a66c3f7a95e05905f5f65d96cb7f378ccdad9edf33814271425829ce10fe3e6c")
        observe.validate_identity("core8", size8, sha8)
        observe.validate_identity("core1", size1, sha1)
        for case, size, digest in (("core8", size1, sha1),
                                   ("core1", size8, sha8)):
            with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                observe.validate_identity(case, size, digest)

    def test_arch_geometry_rejects_sixty_byte_window(self):
        observe.validate_arch_geometry(160)
        with self.assertRaisesRegex(ValueError, "ARCH_60B_WINDOW_REJECTED"):
            observe.validate_arch_geometry(60)
        with self.assertRaisesRegex(ValueError, "ARCH_WINDOW_NOT_160"):
            observe.validate_arch_geometry(188)
        self.assertEqual(observe.ARCH_GEOMETRY["target"], "topology_init")
        self.assertEqual(observe.ARCH_GEOMETRY["offset"], 0x1B346FC)
        self.assertEqual(observe.ARCH_GEOMETRY["function_size"], 188)
        self.assertEqual(observe.ARCH_GEOMETRY["window"], 160)
        self.assertEqual(observe.ARCH_GEOMETRY["back_edge_src"], 0x9C)

    def test_arch_pair_proof_boundary_and_no_shift_route(self):
        baseline = {**self.record("arch8", 35.0),
                    "bootloader_origin": observe.REST_ORIGIN}
        strong = {**self.record("arch1", 28.0),
                  "bootloader_origin": observe.REST_ORIGIN}
        verdict = observe.pair_verdict(baseline, strong)
        self.assertEqual(verdict["verdict"], "STRONG")
        self.assertEqual(verdict["arch_initcalls_completed"], "PROVEN")
        self.assertEqual(verdict["first_subsys_initcall_entry"], "PROVEN")
        self.assertEqual(verdict["first_subsys_initcall_body"], "NOT_PROVEN")
        self.assertEqual(verdict["subsys_initcalls_completed"], "NOT_PROVEN")
        self.assertEqual(verdict["console_on_rootfs_entry"], "NOT_PROVEN")
        self.assertEqual(verdict["usb"], "FROZEN")
        supported = {**self.record("arch1", 26.5),
                     "bootloader_origin": observe.REST_ORIGIN}
        supported_verdict = observe.pair_verdict(baseline, supported)
        self.assertEqual(supported_verdict["verdict"], "SUPPORTED")
        self.assertEqual(supported_verdict["arch_initcalls_completed"],
                         "STRONGLY_SUPPORTED")
        self.assertEqual(supported_verdict["first_subsys_initcall_entry"],
                         "STRONGLY_SUPPORTED")
        no_shift = {**self.record("arch1", 35.0),
                    "bootloader_origin": observe.REST_ORIGIN}
        miss = observe.pair_verdict(baseline, no_shift)
        self.assertEqual(miss["arch_initcalls_checkpoint_shift_not_observed"], "YES")
        self.assertEqual(miss["next"], "ARCH_INITCALLS_FAILURE_ISOLATION_CI")
        self.assertNotIn("arch_initcalls_not_completed", miss)

    def test_arch_member_full_sha_gates_are_distinct(self):
        size8, sha8 = observe.IMAGES["arch8"]
        size1, sha1 = observe.IMAGES["arch1"]
        self.assertEqual(size8, size1)
        self.assertEqual(sha8, "7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d")
        self.assertEqual(sha1, "f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113")
        observe.validate_identity("arch8", size8, sha8)
        observe.validate_identity("arch1", size1, sha1)
        for case, size, digest in (("arch8", size1, sha1),
                                   ("arch1", size8, sha8),
                                   ("arch8", size8, observe.IMAGES["postcore8"][1])):
            with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                observe.validate_identity(case, size, digest)

    def test_subsys_geometry_rejects_oversize_windows(self):
        observe.validate_subsys_geometry(56)
        with self.assertRaisesRegex(ValueError, "SUBSYS_60B_WINDOW_REJECTED"):
            observe.validate_subsys_geometry(60)
        with self.assertRaisesRegex(ValueError, "SUBSYS_57B_WINDOW_REJECTED"):
            observe.validate_subsys_geometry(57)
        self.assertEqual(observe.SUBSYS_GEOMETRY["target"], "create_debug_debugfs_entry")
        self.assertEqual(observe.SUBSYS_GEOMETRY["offset"], 0x149E0)
        self.assertEqual(observe.SUBSYS_GEOMETRY["function_size"], 56)
        self.assertEqual(observe.SUBSYS_GEOMETRY["window"], 56)
        self.assertEqual(observe.SUBSYS_GEOMETRY["core_size"], 52)
        self.assertEqual(observe.SUBSYS_GEOMETRY["daifset"], "ABSENT")

    def test_subsys_pair_proof_boundary_and_no_shift_route(self):
        baseline = {**self.record("subsys8", 35.0),
                    "bootloader_origin": observe.REST_ORIGIN}
        strong = {**self.record("subsys1", 28.0),
                  "bootloader_origin": observe.REST_ORIGIN}
        verdict = observe.pair_verdict(baseline, strong)
        self.assertEqual(verdict["verdict"], "STRONG")
        self.assertEqual(verdict["subsys_initcalls_completed"], "PROVEN")
        self.assertEqual(verdict["first_fs_initcall_entry"], "PROVEN")
        self.assertEqual(verdict["first_fs_initcall_body"], "NOT_PROVEN")
        self.assertEqual(verdict["fs_initcalls_completed"], "NOT_PROVEN")
        self.assertEqual(verdict["console_on_rootfs_entry"], "NOT_PROVEN")
        self.assertEqual(verdict["usb"], "FROZEN")
        supported = {**self.record("subsys1", 26.5),
                     "bootloader_origin": observe.REST_ORIGIN}
        supported_verdict = observe.pair_verdict(baseline, supported)
        self.assertEqual(supported_verdict["verdict"], "SUPPORTED")
        self.assertEqual(supported_verdict["subsys_initcalls_completed"],
                         "STRONGLY_SUPPORTED")
        self.assertEqual(supported_verdict["first_fs_initcall_entry"],
                         "STRONGLY_SUPPORTED")
        no_shift = {**self.record("subsys1", 35.0),
                    "bootloader_origin": observe.REST_ORIGIN}
        miss = observe.pair_verdict(baseline, no_shift)
        self.assertEqual(miss["subsys_initcalls_checkpoint_shift_not_observed"], "YES")
        self.assertEqual(miss["next"], "SUBSYS_INITCALLS_FAILURE_ISOLATION_CI")
        self.assertNotIn("subsys_initcalls_not_completed", miss)

    def test_subsys_member_full_sha_gates_are_distinct(self):
        size8, sha8 = observe.IMAGES["subsys8"]
        size1, sha1 = observe.IMAGES["subsys1"]
        self.assertEqual(size8, size1)
        self.assertEqual(sha8, "e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1")
        self.assertEqual(sha1, "df14e7bcdf409deeeede70d7217f420091a6e9a292b0670443df50c0a0e8b9a1")
        observe.validate_identity("subsys8", size8, sha8)
        observe.validate_identity("subsys1", size1, sha1)
        for case, size, digest in (("subsys8", size1, sha1),
                                   ("subsys1", size8, sha8),
                                   ("subsys8", size8, observe.IMAGES["arch8"][1])):
            with self.assertRaisesRegex(ValueError, "IMAGE_IDENTITY_MISMATCH"):
                observe.validate_identity(case, size, digest)

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
