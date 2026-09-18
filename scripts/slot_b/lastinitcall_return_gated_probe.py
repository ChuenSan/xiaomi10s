"""Last level-5 return gated inline probe geometry. No pair composition."""
from __future__ import annotations

import re
import struct
from pathlib import Path

TEXT_VA = 0xFFFF800080000000
INITCALLS_VA = 0xFFFF800081B311D0
INITCALLS_SIZE = 148
LEVEL_VA = 0xFFFF800081B31264
LEVEL_SIZE = 172
LEVEL_END = 0xFFFF800081B31310
POPULATE_VA = 0xFFFF800081B32388
POPULATE_SIZE = 88
POPULATE_SOURCE = "init/initramfs.c"
ONE_INITCALL_VA = 0xFFFF80008001437C
ONE_INITCALL_SIZE = 536
ONE_INITCALL_END = 0xFFFF800080014594
TABLE5_VA = 0xFFFF800081D0B0D4
TABLE6_VA = 0xFFFF800081D0B1A8
TABLE5_COUNT = 53
LAST_SLOT_VA = 0xFFFF800081D0B1A4
LAST_SLOT_PREL32 = -1936924
LEVEL5 = 5
LEVEL5_NAME = "fs"

LVLTAIL_VA = 0xFFFF800081B312EC
LVLTAIL_BYTES = 36
LVLXIT_VA = 0xFFFF800081B312FC
LVLXIT_BYTES = 20
POSTLVL_VA = 0xFFFF800081B31224
POSTLVL_BYTES = 64
POSTLVL_LIVE_BYTES = 40
POSTLVL_COLD_BYTES = 24
POSTCALL_VA = 0xFFFF800080014458
POSTCALL_BYTES = 104
DOCALL_VA = 0xFFFF800080014454
DOCALL_BYTES = 20
KEYBLK_VA = 0xFFFF80008001454C
KEYBLK_BYTES = 68

CORE_BYTES = 52
GATE_BYTES_REGISTER = 8
GATE_BYTES_ABSOLUTE = 16
MIN_INLINE_FOOTPRINT = GATE_BYTES_REGISTER + CORE_BYTES
ABS_INLINE_FOOTPRINT = GATE_BYTES_ABSOLUTE + CORE_BYTES

LVLTAIL_WORDS = (
    0x97938C24, 0xEB1402BF, 0x91001273, 0x54FFFF63, 0xA9424FF4,
    0xF9400BF5, 0xA8C37BFD, 0xD50323BF, 0xD65F03C0,
)
LVLXIT_WORDS = LVLTAIL_WORDS[4:]
POSTLVL_WORDS = (
    0x11000694, 0x7100229F, 0x54FFFF01, 0xAA1303E0, 0x979C4DD9,
    0xA9424FF4, 0xF9400BF5, 0xA8C37BFD, 0xD50323BF, 0xD65F03C0,
    0xB0FFF1A0, 0x91086400, 0x90FFF921, 0x910B4C21, 0xAA1403E2,
    0x97D621D7,
)
DOCALL_WORDS = (0xD63F0260, 0x39401288, 0x2A0003F4, 0x35000768, 0x390023FF)
KEYBLK_WORDS = (
    0x940484E6, 0xB0010BE8, 0xD29EF9E9, 0xAA1303E1, 0xF9401508,
    0xF2BC6A69, 0x2A1403E2, 0xF2D374A9, 0xCB080008, 0xF2E41889,
    0xB000D2C0, 0x91304400, 0x9B497D08, 0x9347FD09, 0x8B48FD23,
    0x944295DE, 0x17FFFFB6,
)
THYME_RUNTIME_BOOTARGS = "rdinit=/init panic=5 loglevel=7"
GATE = "R3_SLOT_B_FS_LAST_RETURN_GATED_PROBE_NOT_READY"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bind_post51(checkpoint) -> None:
    require(checkpoint.FROZEN_FS_POST51_FUNCTION_SIZE == POPULATE_SIZE, "POST51_SIZE_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_TARGET_VA == POPULATE_VA, "POST51_VA_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_TABLE_VA == LAST_SLOT_VA, "POST51_TABLE_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_SYMBOL == "populate_rootfs", "POST51_SYMBOL_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_INDEX == 52, "POST51_INDEX_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_SOURCE == POPULATE_SOURCE, "POST51_SOURCE_DRIFT")


def window_report() -> dict:
    require(TABLE6_VA - TABLE5_VA == 4 * TABLE5_COUNT, "LEVEL5_SPAN_DRIFT")
    require(LAST_SLOT_VA + 4 == TABLE6_VA, "LAST_SLOT_NOT_AT_LEVEL5_END")
    require(LAST_SLOT_VA + LAST_SLOT_PREL32 == POPULATE_VA, "LAST_SLOT_TARGET_DRIFT")
    require(INITCALLS_VA + INITCALLS_SIZE == LEVEL_VA, "INITCALLS_LEVEL_NOT_ADJACENT")
    require(LEVEL_VA + LEVEL_SIZE == LEVEL_END, "LEVEL_SIZE_DRIFT")
    require(POSTLVL_LIVE_BYTES + POSTLVL_COLD_BYTES == POSTLVL_BYTES, "POSTLVL_SPLIT_DRIFT")
    require(len(LVLTAIL_WORDS) * 4 == LVLTAIL_BYTES, "LVLTAIL_WORDS_DRIFT")
    require(LVLXIT_WORDS == LVLTAIL_WORDS[4:], "LVLXIT_WORDS_DRIFT")
    require(len(POSTLVL_WORDS) * 4 == POSTLVL_BYTES, "POSTLVL_WORDS_DRIFT")
    require(len(DOCALL_WORDS) * 4 == DOCALL_BYTES, "DOCALL_WORDS_DRIFT")
    require(DOCALL_VA + 4 == POSTCALL_VA, "DOCALL_NOT_IMMEDIATELY_BEFORE_TAIL")
    require(len(KEYBLK_WORDS) * 4 == KEYBLK_BYTES, "KEYBLK_WORDS_DRIFT")
    require(LVLXIT_VA + LVLXIT_BYTES == LEVEL_END, "LVLXIT_NOT_AT_FUNCTION_END")
    require(POSTLVL_VA + POSTLVL_BYTES == LEVEL_VA, "POSTLVL_NOT_AT_FUNCTION_END")
    require(MIN_INLINE_FOOTPRINT == 60 and ABS_INLINE_FOOTPRINT == 68, "FOOTPRINT_DRIFT")
    return {
        "lvlxit_bytes": LVLXIT_BYTES,
        "lvlxit_spare": 0,
        "postlvl_bytes": POSTLVL_BYTES,
        "postlvl_live_bytes": POSTLVL_LIVE_BYTES,
        "postlvl_cold_bytes": POSTLVL_COLD_BYTES,
        "postlvl_spare": 0,
        "postcall_bytes": POSTCALL_BYTES,
        "postcall_spare": 0,
        "keyblk_bytes": KEYBLK_BYTES,
        "keyblk_provably_dead": False,
    }


def report() -> dict:
    require("initramfs_async=" not in THYME_RUNTIME_BOOTARGS, "THYME_SETS_INITRAMFS_ASYNC")
    out = {
        "level5": LEVEL5,
        "level5_name": LEVEL5_NAME,
        "level5_entries": TABLE5_COUNT,
        "table5_va": hex(TABLE5_VA),
        "table6_va": hex(TABLE6_VA),
        "last_slot_va": hex(LAST_SLOT_VA),
        "last_slot_prel32": LAST_SLOT_PREL32,
        "last_slot_target": hex(POPULATE_VA),
        "populate_rootfs_is_last_level5_entry": True,
        "do_initcalls_va": hex(INITCALLS_VA),
        "do_initcalls_size": INITCALLS_SIZE,
        "do_initcall_level_va": hex(LEVEL_VA),
        "do_initcall_level_size": LEVEL_SIZE,
        "do_one_initcall_va": hex(ONE_INITCALL_VA),
        "do_one_initcall_size": ONE_INITCALL_SIZE,
        "populate_rootfs_size": POPULATE_SIZE,
        "core_bytes": CORE_BYTES,
        "gate_bytes_register": GATE_BYTES_REGISTER,
        "gate_bytes_absolute": GATE_BYTES_ABSOLUTE,
        "min_inline_footprint": MIN_INLINE_FOOTPRINT,
        "abs_inline_footprint": ABS_INLINE_FOOTPRINT,
        "min_inline_deficit_bytes": MIN_INLINE_FOOTPRINT,
        "reemit_required": True,
        "shared_caller_required": True,
        "unconditional_shared_caller_rejected": True,
        "loop_increment_preserved_impossible": True,
        "boundary_check_preserved_impossible": True,
        "probe_before_return_rejected": True,
        "cross_function_overwrite": False,
        "trampoline_permitted": False,
        "island_permitted": False,
        "code_cave_permitted": False,
        "runtime_rewrite": False,
        "prel32_table_modified": False,
        "table_ordering_modified": False,
        "non_target_iteration_changed": False,
        "extra_pair_diff": False,
        "incoming_branch_conflict": False,
        "checkpoint_fires_before_populate_rootfs_return": False,
        "pair_generated": False,
        "lastret8_generated": False,
        "lastret1_generated": False,
        "initramfs_async_default": True,
        "wait_path_live_on_thyme": False,
        "populate_rootfs_entry": "PROVEN",
        "populate_rootfs_return": "NOT_PROVEN",
        "fs_initcalls_completed": "NOT_PROVEN",
        "first_device_initcall_entry": "NOT_PROVEN",
        "last_level5_return_checkpoint_shift": "NOT_OBSERVED",
        "device_operation": False,
        "kernel_rebuild": False,
        "partition_writes": 0,
        "slot_a_written": "NO",
        "gate": GATE,
    }
    out.update(window_report())
    return out


def gate_report(actual: dict) -> dict:
    expected = report()
    for key, value in expected.items():
        require(actual.get(key) == value, f"FS_LAST_RETURN_REJECTED:{key}")
    return actual


def select_last_return_probe() -> None:
    raise ValueError("LAST_RETURN_INLINE_GATED_60B_DOES_NOT_FIT")


def verify_payload_words(payload: bytes) -> dict:
    windows = (
        (LVLTAIL_VA, LVLTAIL_WORDS, "LVLTAIL_WORDS_DRIFT"),
        (POSTLVL_VA, POSTLVL_WORDS, "POSTLVL_WORDS_DRIFT"),
        (DOCALL_VA, DOCALL_WORDS, "DOCALL_WORDS_DRIFT"),
        (KEYBLK_VA, KEYBLK_WORDS, "KEYBLK_WORDS_DRIFT"),
    )
    for va, words, drift in windows:
        off = va - TEXT_VA
        require(len(payload) >= off + len(words) * 4, "PAYLOAD_SHORTER_THAN_WINDOW")
        require(struct.unpack_from("<%dI" % len(words), payload, off) == words, drift)
    require(struct.unpack_from("<i", payload, LAST_SLOT_VA - TEXT_VA)[0] == LAST_SLOT_PREL32,
            "LAST_SLOT_PREL32_DRIFT")
    require(struct.unpack_from("<I", payload, LEVEL_VA - TEXT_VA)[0] == 0xD503233F,
            "DO_INITCALL_LEVEL_ENTRY_DRIFT")
    require(struct.unpack_from("<I", payload, ONE_INITCALL_VA - TEXT_VA)[0] == 0xD503233F,
            "DO_ONE_INITCALL_ENTRY_DRIFT")
    require(struct.unpack_from("<I", payload, ONE_INITCALL_END - TEXT_VA)[0] == 0xD503233F,
            "DO_ONE_INITCALL_END_DRIFT")
    return gate_report(report())


def audit_source(linux: Path) -> dict:
    main = (linux / "init/main.c").read_text()
    init_h = (linux / "include/linux/init.h").read_text()
    lds = (linux / "include/asm-generic/vmlinux.lds.h").read_text()
    initramfs = (linux / "init/initramfs.c").read_text()

    require(re.search(r"static initcall_entry_t \*initcall_levels\[\] __initdata = \{"
                      r"(?:\s*__initcall\d_start,){8}\s*__initcall_end,\s*\};",
                      main), "INITCALL_LEVELS_SHAPE_DRIFT")
    require("for (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++)" in main,
            "LEVEL_LOOP_BOUND_DRIFT")
    require(re.search(r'static const char \*initcall_level_names\[\] __initdata = \{'
                      r'(?:\s*"[a-z]+",){8}\s*\};', main), "LEVEL_NAMES_SHAPE_DRIFT")
    names = re.findall(r'"([a-z]+)"',
                       re.search(r'initcall_level_names\[\] __initdata = \{(.*?)\};',
                                 main, re.S).group(1))
    require(len(names) == 8 and names[LEVEL5] == LEVEL5_NAME, "LEVEL5_NAME_DRIFT")
    require(re.search(r"for \(fn = initcall_levels\[level\]; fn < initcall_levels\[level\+1\]; fn\+\+\)"
                      r"\s*\n\s*do_one_initcall\(initcall_from_entry\(fn\)\);", main),
            "LEVEL_LOOP_SHAPE_DRIFT")
    require(re.search(r"int __init_or_module do_one_initcall\(initcall_t fn\)", main),
            "DO_ONE_INITCALL_SIGNATURE_DRIFT")
    require(re.search(r"#define fs_initcall\(fn\)\s+__define_initcall\(fn, 5\)", init_h),
            "FS_INITCALL_LEVEL_DRIFT")
    require(re.search(r"#define rootfs_initcall\(fn\)\s+__define_initcall\(fn, rootfs\)", init_h),
            "ROOTFS_INITCALL_LEVEL_DRIFT")
    require(re.search(r"INIT_CALLS_LEVEL\(5\)\s*\\\s*\n\s*INIT_CALLS_LEVEL\(rootfs\)\s*\\\s*\n"
                      r"\s*INIT_CALLS_LEVEL\(6\)", lds), "ROOTFS_NOT_LAST_IN_LEVEL5")
    require("static bool __initdata initramfs_async = true;" in initramfs,
            "INITRAMFS_ASYNC_DEFAULT_NOT_TRUE")
    require('__setup("initramfs_async=", initramfs_async_setup);' in initramfs,
            "INITRAMFS_ASYNC_SETUP_MISSING")
    require(re.search(r"if\s*\(\s*!initramfs_async\s*\)\s*wait_for_initramfs\s*\(\s*\)\s*;",
                      initramfs), "WAIT_NOT_GATED_ON_INITRAMFS_ASYNC")
    require("rootfs_initcall(populate_rootfs);" in initramfs, "POPULATE_ROOTFS_NOT_ROOTFS_INITCALL")
    return {
        "initcall_levels_count": 9,
        "level_loop_bound": 8,
        "level5_name": LEVEL5_NAME,
        "rootfs_between_level5_and_level6": True,
        "populate_rootfs_is_last_level5_entry": True,
        "level5_return_implies_fs_complete": True,
        "first_device_entry_implies_fs_complete": True,
        "initramfs_async_default": True,
        "populate_rootfs_waits_by_default": False,
    }
