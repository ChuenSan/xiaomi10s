import os
import struct
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GITHUB_ACTIONS", "true")

import checkpoint
import lastinitcall_return_gated_probe as lrp

MAIN_FAKE = (
    'static initcall_entry_t *initcall_levels[] __initdata = {\n'
    '\t__initcall0_start,\n\t__initcall1_start,\n\t__initcall2_start,\n'
    '\t__initcall3_start,\n\t__initcall4_start,\n\t__initcall5_start,\n'
    '\t__initcall6_start,\n\t__initcall7_start,\n\t__initcall_end,\n};\n'
    'static const char *initcall_level_names[] __initdata = {\n'
    '\t"pure",\n\t"core",\n\t"postcore",\n\t"arch",\n'
    '\t"subsys",\n\t"fs",\n\t"device",\n\t"late",\n};\n'
    'static void __init do_initcall_level(int level, char *command_line)\n'
    '{\n\tinitcall_entry_t *fn;\n'
    '\tfor (fn = initcall_levels[level]; fn < initcall_levels[level+1]; fn++)\n'
    '\t\tdo_one_initcall(initcall_from_entry(fn));\n}\n'
    'static void __init do_initcalls(void)\n{\n\tint level;\n'
    '\tfor (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++) {\n'
    '\t\tdo_initcall_level(level, command_line);\n\t}\n}\n'
    'int __init_or_module do_one_initcall(initcall_t fn)\n{\n\treturn 0;\n}\n'
)
INIT_H_FAKE = (
    '#define fs_initcall(fn)\t\t__define_initcall(fn, 5)\n'
    '#define rootfs_initcall(fn)\t\t__define_initcall(fn, rootfs)\n'
)
LDS_FAKE = (
    '#define INIT_CALLS\t\t\t\t\t\t\\\n'
    '\t\tINIT_CALLS_LEVEL(5)\t\t\t\t\\\n'
    '\t\tINIT_CALLS_LEVEL(rootfs)\t\t\t\t\\\n'
    '\t\tINIT_CALLS_LEVEL(6)\t\t\t\t\\\n'
    '\t\t__initcall_end = .;\n'
)
INITRAMFS_FAKE = (
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
    'rootfs_initcall(populate_rootfs);\n'
)


def source_tree():
    tmp = tempfile.TemporaryDirectory()
    linux = Path(tmp.name)
    (linux / "init").mkdir()
    (linux / "include/linux").mkdir(parents=True)
    (linux / "include/asm-generic").mkdir(parents=True)
    (linux / "init/main.c").write_text(MAIN_FAKE)
    (linux / "init/initramfs.c").write_text(INITRAMFS_FAKE)
    (linux / "include/linux/init.h").write_text(INIT_H_FAKE)
    (linux / "include/asm-generic/vmlinux.lds.h").write_text(LDS_FAKE)
    return tmp, linux


class LastReturnGatedProbeTests(unittest.TestCase):
    def test_bind_post51_frozen_identity(self):
        lrp.bind_post51(checkpoint)

    def test_geometry_not_ready(self):
        report = lrp.report()
        lrp.gate_report(report)
        self.assertEqual(report["level5_entries"], 53)
        self.assertEqual(report["last_slot_va"], "0xffff800081d0b1a4")
        self.assertEqual(report["last_slot_target"], "0xffff800081b32388")
        self.assertTrue(report["populate_rootfs_is_last_level5_entry"])
        self.assertEqual(report["min_inline_footprint"], 60)
        self.assertEqual(report["lvlxit_bytes"], 20)
        self.assertEqual(report["postlvl_bytes"], 64)
        self.assertEqual(report["postcall_bytes"], 104)
        self.assertEqual(report["keyblk_bytes"], 68)
        self.assertFalse(report["keyblk_provably_dead"])
        self.assertEqual(report["min_inline_deficit_bytes"], 60)
        self.assertEqual(report["gate"], lrp.GATE)
        self.assertFalse(report["pair_generated"])

    def test_select_last_return_probe_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            lrp.select_last_return_probe()
        self.assertEqual(str(ctx.exception), "LAST_RETURN_INLINE_GATED_60B_DOES_NOT_FIT")

    def test_20b_window_would_require_trampoline(self):
        _core, arch, rejected = checkpoint.select_fs_complete_core(lrp.LVLXIT_BYTES, bytes(56),
                                                                  bytes(52))
        self.assertEqual(arch, "ENTRY_TRAMPOLINE")
        self.assertTrue(rejected)
        report = lrp.report()
        self.assertFalse(report["trampoline_permitted"])
        self.assertFalse(report["island_permitted"])
        self.assertFalse(report["code_cave_permitted"])

    def test_payload_words_windows(self):
        end = max(lrp.KEYBLK_VA - lrp.TEXT_VA + lrp.KEYBLK_BYTES,
                  lrp.LVLTAIL_VA - lrp.TEXT_VA + lrp.LVLTAIL_BYTES,
                  lrp.LAST_SLOT_VA - lrp.TEXT_VA + 4)
        payload = bytearray(end)
        for va, words, _drift in (
            (lrp.LVLTAIL_VA, lrp.LVLTAIL_WORDS, ""),
            (lrp.POSTLVL_VA, lrp.POSTLVL_WORDS, ""),
            (lrp.DOCALL_VA, lrp.DOCALL_WORDS, ""),
            (lrp.KEYBLK_VA, lrp.KEYBLK_WORDS, ""),
        ):
            struct.pack_into("<%dI" % len(words), payload, va - lrp.TEXT_VA, *words)
        struct.pack_into("<i", payload, lrp.LAST_SLOT_VA - lrp.TEXT_VA, lrp.LAST_SLOT_PREL32)
        for va in (lrp.LEVEL_VA, lrp.ONE_INITCALL_VA, lrp.ONE_INITCALL_END):
            struct.pack_into("<I", payload, va - lrp.TEXT_VA, 0xD503233F)
        lrp.verify_payload_words(bytes(payload))
        for off in (lrp.LVLTAIL_VA - lrp.TEXT_VA, lrp.POSTLVL_VA - lrp.TEXT_VA,
                    lrp.DOCALL_VA - lrp.TEXT_VA, lrp.KEYBLK_VA - lrp.TEXT_VA,
                    lrp.LAST_SLOT_VA - lrp.TEXT_VA):
            with self.subTest(off=hex(off)):
                bad = bytearray(payload)
                bad[off] ^= 1
                with self.assertRaises(ValueError):
                    lrp.verify_payload_words(bytes(bad))

    def test_source_chain(self):
        tmp, linux = source_tree()
        try:
            src = lrp.audit_source(linux)
        finally:
            tmp.cleanup()
        self.assertEqual(src["initcall_levels_count"], 9)
        self.assertEqual(src["level_loop_bound"], 8)
        self.assertEqual(src["level5_name"], "fs")
        self.assertTrue(src["rootfs_between_level5_and_level6"])
        self.assertTrue(src["populate_rootfs_is_last_level5_entry"])
        self.assertTrue(src["level5_return_implies_fs_complete"])
        self.assertTrue(src["initramfs_async_default"])
        self.assertFalse(src["populate_rootfs_waits_by_default"])

    def test_last_return_negative_fixtures(self):
        good = lrp.report()
        lrp.gate_report(good)
        drifts = {
            "uncond_shared_caller": ("unconditional_shared_caller_rejected", False),
            "shared_caller_required": ("shared_caller_required", False),
            "non_unique_level": ("level5", 4),
            "non_unique_index52": ("last_slot_va", "0xffff800081d0b1a0"),
            "index52_target": ("last_slot_target", "0xffff800081b6b2fc"),
            "not_last_entry": ("populate_rootfs_is_last_level5_entry", False),
            "fires_pre_return": ("checkpoint_fires_before_populate_rootfs_return", True),
            "pre_return_rejected": ("probe_before_return_rejected", False),
            "non_target_iter_changed": ("non_target_iteration_changed", True),
            "loop_increment": ("loop_increment_preserved_impossible", False),
            "boundary_check": ("boundary_check_preserved_impossible", False),
            "prel32_table": ("prel32_table_modified", True),
            "table_ordering": ("table_ordering_modified", True),
            "trampoline": ("trampoline_permitted", True),
            "island": ("island_permitted", True),
            "code_cave": ("code_cave_permitted", True),
            "cross_fn": ("cross_function_overwrite", True),
            "runtime_rewrite": ("runtime_rewrite", True),
            "incoming_branch": ("incoming_branch_conflict", True),
            "extra_pair_diff": ("extra_pair_diff", True),
            "reemit_required": ("reemit_required", False),
            "footprint": ("min_inline_footprint", 52),
            "deficit": ("min_inline_deficit_bytes", 0),
            "lvlxit_spare": ("lvlxit_spare", 20),
            "postlvl_spare": ("postlvl_spare", 24),
            "postcall_spare": ("postcall_spare", 104),
            "keyblk_dead": ("keyblk_provably_dead", True),
            "pair": ("pair_generated", True),
            "lastret8": ("lastret8_generated", True),
            "lastret1": ("lastret1_generated", True),
            "device": ("device_operation", True),
            "rebuild": ("kernel_rebuild", True),
            "partition": ("partition_writes", 1),
            "slot_a": ("slot_a_written", "YES"),
            "populate_return": ("populate_rootfs_return", "PROVEN"),
            "fs_complete": ("fs_initcalls_completed", "PROVEN"),
            "first_device": ("first_device_initcall_entry", "PROVEN"),
            "shift": ("last_level5_return_checkpoint_shift", "OBSERVED"),
            "async_false": ("initramfs_async_default", False),
            "wait_live": ("wait_path_live_on_thyme", True),
            "ready_gate": ("gate", "R3_SLOT_B_FS_INITCALLS_COMPLETED_PROVEN"),
        }
        for name, (key, value) in drifts.items():
            with self.subTest(name=name):
                bad = dict(good)
                bad[key] = value
                with self.assertRaises(ValueError):
                    lrp.gate_report(bad)


if __name__ == "__main__":
    unittest.main()
