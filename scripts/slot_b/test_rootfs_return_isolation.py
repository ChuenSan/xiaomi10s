import os
import struct
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GITHUB_ACTIONS", "true")

import checkpoint
import rootfs_return_isolation as iso


class RootfsReturnIsolationTests(unittest.TestCase):
    def test_bind_post51_frozen_identity(self):
        iso.bind_post51(checkpoint)

    def test_geometry_not_ready(self):
        report = iso.report()
        iso.gate_report(report)
        self.assertEqual(report["p1_remaining"], 48)
        self.assertEqual(report["p2_remaining"], 16)
        self.assertFalse(report["p1_fits_52"])
        self.assertFalse(report["p2_fits_52"])
        self.assertEqual(report["gate"], iso.GATE)
        self.assertFalse(report["pair_generated"])

    def test_select_return_probe_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            iso.select_return_probe()
        self.assertEqual(str(ctx.exception), "POPULATE_ROOTFS_RETURN_INLINE_52B_DOES_NOT_FIT")

    def test_48b_must_not_fall_back_to_island(self):
        core56 = bytes(56)
        core52 = bytes(52)
        _core, arch, rejected = checkpoint.select_fs_complete_core(48, core56, core52)
        self.assertEqual(arch, "ENTRY_TRAMPOLINE")
        self.assertTrue(rejected)
        report = iso.report()
        self.assertFalse(report["trampoline_permitted"])
        self.assertFalse(report["island_permitted"])

    def test_payload_words_and_adjacent_do_populate_rootfs(self):
        payload = bytearray(0x1B32388 + 92)
        struct.pack_into("<22I", payload, 0x1B32388, *iso.WORDS)
        struct.pack_into("<I", payload, 0x1B323E0, 0xD503233F)
        iso.verify_payload_words(bytes(payload))
        payload[0x1B32388] ^= 1
        with self.assertRaises(ValueError):
            iso.verify_payload_words(bytes(payload))

    def test_source_async_default_and_gated_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            linux = Path(tmp)
            (linux / "init").mkdir()
            (linux / "init/initramfs.c").write_text(
                'static bool __initdata initramfs_async = true;\n'
                'static int __init initramfs_async_setup(char *str) { return 0; }\n'
                '__setup("initramfs_async=", initramfs_async_setup);\n'
                'static int __init populate_rootfs(void)\n{\n'
                '\tinitramfs_cookie = async_schedule_domain(do_populate_rootfs, NULL,\n'
                '\t\t\t\t\t\t &initramfs_domain);\n'
                '\tusermodehelper_enable();\n'
                '\tif (!initramfs_async)\n'
                '\t\twait_for_initramfs();\n'
                '\treturn 0;\n}\n'
                'rootfs_initcall(populate_rootfs);\n')
            self.assertEqual(iso.audit_source(linux)["populate_rootfs_waits_by_default"], False)

    def test_negative_fixtures(self):
        good = iso.report()
        iso.gate_report(good)
        drifts = {
            "p1_fits": ("p1_fits_52", True),
            "p2_fits": ("p2_fits_52", True),
            "p1_remaining": ("p1_remaining", 52),
            "p2_remaining": ("p2_remaining", 52),
            "async_false": ("initramfs_async_default", False),
            "wait_live": ("wait_path_live_on_thyme", True),
            "island": ("island_permitted", True),
            "tramp": ("trampoline_permitted", True),
            "shared_level": ("shared_do_initcall_level", True),
            "rewrite_table": ("rewrite_initcall_table", True),
            "cross_fn": ("cross_function_overwrite", True),
            "pair": ("pair_generated", True),
            "fs_complete": ("fs_initcalls_completed", "PROVEN"),
            "first_device": ("first_device_initcall_entry", "PROVEN"),
            "no_shift_misread": ("first_device_shift_not_observed_does_not_prove_non_return", False),
            "ready_gate": ("gate", "R3_SLOT_B_POPULATE_ROOTFS_POST_SCHEDULE_PROVEN"),
        }
        for name, (key, value) in drifts.items():
            with self.subTest(name=name):
                bad = dict(good)
                bad[key] = value
                with self.assertRaises(ValueError):
                    iso.gate_report(bad)


if __name__ == "__main__":
    unittest.main()
