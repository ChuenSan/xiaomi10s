"""Populate_rootfs return-isolation geometry. No pair composition."""
from __future__ import annotations

import re
import struct
from pathlib import Path

TEXT_VA = 0xFFFF800080000000
TARGET_VA = 0xFFFF800081B32388
TABLE_VA = 0xFFFF800081D0B1A4
FUNCTION_SIZE = 88
POST_SCHEDULE = 0x28
RETURN_JOIN = 0x48
WAIT_BL = 0x44
ASYNC_BL = 0x24
CBNZ = 0x40
MIN_INLINE_CORE = 52
WORDS = (
    0xD503233F, 0xA9BF7BFD, 0x910003FD, 0x90000000, 0x910F8000,
    0xB0001183, 0x91350063, 0xAA1F03E1, 0x12800002, 0x979630EA,
    0xF00032E8, 0xF9002D00, 0x2A1F03E0, 0x9795E1A6, 0x900008A8,
    0x3944A508, 0x35000048, 0x979388BF, 0x2A1F03E0, 0xA8C17BFD,
    0xD50323BF, 0xD65F03C0,
)
THYME_RUNTIME_BOOTARGS = "rdinit=/init panic=5 loglevel=7"
GATE = "R3_SLOT_B_POPULATE_ROOTFS_RETURN_ISOLATION_NOT_READY"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bind_post51(checkpoint) -> None:
    require(checkpoint.FROZEN_FS_POST51_FUNCTION_SIZE == FUNCTION_SIZE, "POST51_SIZE_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_TARGET_VA == TARGET_VA, "POST51_VA_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_TABLE_VA == TABLE_VA, "POST51_TABLE_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_SYMBOL == "populate_rootfs", "POST51_SYMBOL_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_INDEX == 52, "POST51_INDEX_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_SOURCE == "init/initramfs.c", "POST51_SOURCE_DRIFT")
    require(checkpoint.FROZEN_FS_POST51_REGISTRATION == "rootfs_initcall(populate_rootfs)",
            "POST51_REGISTRATION_DRIFT")


def remaining_after(offset: int) -> int:
    require(0 <= offset < FUNCTION_SIZE and offset % 4 == 0, "RETURN_SITE_UNALIGNED")
    return FUNCTION_SIZE - offset


def report() -> dict:
    p1 = remaining_after(POST_SCHEDULE)
    p2 = remaining_after(RETURN_JOIN)
    require(len(WORDS) == 22 and WORDS[0] == 0xD503233F, "POPULATE_ROOTFS_ENTRY_NOT_PACIASP")
    require(WORDS[ASYNC_BL // 4] == 0x979630EA, "ASYNC_BL_DRIFT")
    require(WORDS[CBNZ // 4] == 0x35000048, "CBNZ_SKIP_WAIT_DRIFT")
    require(WORDS[WAIT_BL // 4] == 0x979388BF, "WAIT_BL_DRIFT")
    require(WORDS[-1] == 0xD65F03C0, "RET_DRIFT")
    require(p1 == 48 and p1 < MIN_INLINE_CORE, "P1_REMAINING_NOT_48")
    require(p2 == 16 and p2 < MIN_INLINE_CORE, "P2_REMAINING_NOT_16")
    require("initramfs_async=" not in THYME_RUNTIME_BOOTARGS, "THYME_SETS_INITRAMFS_ASYNC")
    return {
        "function_size": FUNCTION_SIZE,
        "p1_offset": POST_SCHEDULE,
        "p1_va": hex(TARGET_VA + POST_SCHEDULE),
        "p1_remaining": p1,
        "p2_offset": RETURN_JOIN,
        "p2_va": hex(TARGET_VA + RETURN_JOIN),
        "p2_remaining": p2,
        "min_inline_core": MIN_INLINE_CORE,
        "p1_fits_52": False,
        "p2_fits_52": False,
        "initramfs_async_default": True,
        "wait_path_live_on_thyme": False,
        "island_permitted": False,
        "trampoline_permitted": False,
        "shared_do_initcall_level": False,
        "rewrite_initcall_table": False,
        "cross_function_overwrite": False,
        "pair_generated": False,
        "first_device_shift_not_observed_does_not_prove_non_return": True,
        "fs_initcalls_completed": "NOT_PROVEN",
        "first_device_initcall_entry": "NOT_PROVEN",
        "gate": GATE,
    }


def gate_report(actual: dict) -> dict:
    expected = report()
    for key, value in expected.items():
        require(actual.get(key) == value, f"FS_ROOTFS_RETURN_REJECTED:{key}")
    return actual


def select_return_probe() -> None:
    raise ValueError("POPULATE_ROOTFS_RETURN_INLINE_52B_DOES_NOT_FIT")


def verify_payload_words(payload: bytes) -> dict:
    off = TARGET_VA - TEXT_VA
    require(off == 0x1B32388, "IMAGE_OFFSET_DRIFT")
    require(len(payload) >= off + FUNCTION_SIZE, "PAYLOAD_SHORTER_THAN_FUNCTION")
    words = struct.unpack_from("<22I", payload, off)
    require(words == WORDS, "POPULATE_ROOTFS_BYTES_DRIFT")
    next_word = struct.unpack_from("<I", payload, off + FUNCTION_SIZE)[0]
    require(next_word == 0xD503233F, "DO_POPULATE_ROOTFS_ENTRY_DRIFT")
    return gate_report(report())


def audit_source(linux: Path) -> dict:
    text = (linux / "init/initramfs.c").read_text()
    require("static bool __initdata initramfs_async = true;" in text,
            "INITRAMFS_ASYNC_DEFAULT_NOT_TRUE")
    require('__setup("initramfs_async=", initramfs_async_setup);' in text,
            "INITRAMFS_ASYNC_SETUP_MISSING")
    require(re.search(r"initramfs_cookie\s*=\s*async_schedule_domain\s*\(\s*do_populate_rootfs",
                      text), "POPULATE_ROOTFS_NOT_ASYNC_SCHEDULE_DOMAIN")
    require(re.search(r"if\s*\(\s*!initramfs_async\s*\)\s*wait_for_initramfs\s*\(\s*\)\s*;",
                      text), "WAIT_NOT_GATED_ON_INITRAMFS_ASYNC")
    require("rootfs_initcall(populate_rootfs);" in text, "POPULATE_ROOTFS_NOT_ROOTFS_INITCALL")
    require("usermodehelper_enable();" in text, "UMH_ENABLE_MISSING")
    return {"initramfs_async_default": True, "populate_rootfs_waits_by_default": False}
