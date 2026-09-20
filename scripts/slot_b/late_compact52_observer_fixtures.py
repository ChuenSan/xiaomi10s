#!/usr/bin/env python3
"""GHA-only COMPACT52 PUBLIC observer fixtures (late index 52 boot_wait_for_devices,
paciasp pad class, 48-byte COMPACT_INLINE_48B architecture).

SELF-CONTAINED: observe.py carries no compact52 plug-in points (it is frozen and
must not be edited), so the four identity SHAs are defined here as deterministic
constants and the module imports only observe's general protocol/identity tables
(observe.IMAGES / PROTOCOL / REST_ORIGIN / CONTEXT) for cross-family rejection.
DEVICE_BOOT=0 for this CI-only round, so the device-validation accept path is
exercised only with synthetic timings in unit tests; the frozen SHA freeze (when
performed) edits only this file's four constants.
"""
from __future__ import annotations

import argparse
import math
import os

import observe

BOOT_SIZE = 37380096
LATE_TABLE_ENTRY_COUNT = 86
EXPECTED_DELTA_SECONDS = -7.0
STRONG_ERROR_SECONDS = 1.0
SUPPORTED_ERROR_SECONDS = 2.0
PACIASP_WORD = "0xd503233f"
# SELF-CONTAINED identity SHAs (observe.py has no compact52 plug-in points).
# Replaced with the real authorization-run payload SHAs at freeze time.
COMPACT52_8_BOOT_SHA256 = "f1a0" + "0" * 60
COMPACT52_1_BOOT_SHA256 = "f1b0" + "0" * 60
COMPACT52_8_PAYLOAD_SHA256 = "e1a0" + "0" * 60
COMPACT52_1_PAYLOAD_SHA256 = "e1b0" + "0" * 60
FROZEN_IDENTITIES = {
    "late_compact52": {"8": COMPACT52_8_BOOT_SHA256, "1": COMPACT52_1_BOOT_SHA256},
}
FROZEN_PAYLOAD_IDENTITIES = {
    "late_compact52": {"8": COMPACT52_8_PAYLOAD_SHA256, "1": COMPACT52_1_PAYLOAD_SHA256},
}
FAMILIES = {
    "late_compact52": {
        "label": "COMPACT52", "index": 52, "nominal_index": 52,
        "target": "boot_wait_for_devices", "va": 0xFFFF800081B87EC8,
        "offset": 0x1B87EC8, "function_size": 48, "window": 48, "core_size": 44,
        "architecture": "COMPACT_INLINE_48B", "entry": "paciasp",
        "paciasp_word": PACIASP_WORD, "tail_size": 0,
        "daifset": "ABSENT", "inline_only": True, "prel32_unchanged": True,
        "table_va": 0xFFFF800081D0C3A8, "prel32_word": "0xffe7bb20",
        "relative": -1590496, "pair_diff": [0x1B87ED1, 0x1B87ED2],
        "deviation": None},
}
MEMBERS = tuple(family + member for family in FAMILIES for member in ("8", "1"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _is_sha256(value):
    return (isinstance(value, str) and len(value) == 64 and
            all(ch in "0123456789abcdef" for ch in value))


def require_frozen():
    for family, members in FROZEN_IDENTITIES.items():
        for member, sha in members.items():
            require(_is_sha256(sha), "COMPACT52_IDENTITY_NOT_FROZEN")
    for family, members in FROZEN_PAYLOAD_IDENTITIES.items():
        for member, sha in members.items():
            require(_is_sha256(sha), "COMPACT52_IDENTITY_NOT_FROZEN")


def member_sha(case):
    family, member = case[:-1], case[-1]
    require(family in FAMILIES, "CASE_NOT_COMPACT52")
    require_frozen()
    return FROZEN_IDENTITIES[family][member]


def member_identity(case):
    return (BOOT_SIZE, member_sha(case))


def validate_member(case, size, digest):
    require(case in MEMBERS, "CASE_NOT_COMPACT52")
    require((size, digest) == (BOOT_SIZE, member_sha(case)), "IMAGE_IDENTITY_MISMATCH")


def validate_geometry(family, window):
    spec, label = FAMILIES[family], FAMILIES[family]["label"]
    require(window != 56, f"{label}_56B_WINDOW_REJECTED")
    require(window == spec["window"], f"{label}_WINDOW_NOT_48")
    require(spec["window"] <= spec["function_size"], f"{label}_WINDOW_EXCEEDS_FUNCTION")
    require(spec["function_size"] == 48, f"{label}_FUNCTION_NOT_48")
    require(spec["core_size"] == 44, f"{label}_CORE_NOT_44")
    require(spec["architecture"] == "COMPACT_INLINE_48B", f"{label}_ARCHITECTURE_DRIFT")
    require(spec["entry"] == "paciasp", f"{label}_ENTRY_NOT_PACIASP")
    require(spec["paciasp_word"] == PACIASP_WORD, f"{label}_PACIASP_WORD_DRIFT")
    require(spec["tail_size"] == 0, f"{label}_TAIL_NOT_0")
    require(spec["daifset"] == "ABSENT", f"{label}_DAIFSET_PRESENT")
    require(spec["inline_only"] is True, f"{label}_NOT_INLINE_ONLY")
    require(spec["prel32_unchanged"] is True, f"{label}_PREL32_CHANGED")


def validate_selection(family):
    spec, label = FAMILIES[family], FAMILIES[family]["label"]
    if spec["index"] == spec["nominal_index"]:
        require(spec["deviation"] is None, f"{label}_UNEXPECTED_DEVIATION")
        return
    deviation = spec["deviation"]
    require(deviation is not None, f"{label}_DEVIATION_UNRECORDED")
    require(deviation.get("chosen_index") == spec["index"]
            and deviation.get("nominal_index") == spec["nominal_index"]
            and deviation.get("distance") == abs(spec["index"] - spec["nominal_index"]),
            f"{label}_DEVIATION_DRIFT")


def validate_table(family):
    spec, label = FAMILIES[family], FAMILIES[family]["label"]
    require(0 <= spec["index"] < LATE_TABLE_ENTRY_COUNT, f"{label}_INDEX_OUT_OF_SPAN")
    require(spec["target"] and spec["va"] == 0xFFFF800080000000 + spec["offset"],
            f"{label}_TARGET_VA_DRIFT")
    require(spec["table_va"] == 0xFFFF800081D0C2D8 + 4 * spec["index"],
            f"{label}_TABLE_VA_DRIFT")
    require(spec["prel32_word"] == f"0x{spec['relative'] & 0xFFFFFFFF:08x}",
            f"{label}_PREL32_WORD_DRIFT")
    require(spec["pair_diff"] == [spec["offset"] + 9, spec["offset"] + 10],
            f"{label}_PAIR_DIFF_DRIFT")


def pair_diff_range(family):
    spec = FAMILIES[family]
    first, second = spec["pair_diff"]
    require(second == first + 1, f"{spec['label']}_PAIR_DIFF_NOT_TWO_BYTES")
    require(spec["offset"] <= first and second < spec["offset"] + spec["window"],
            f"{spec['label']}_PAIR_DIFF_OUTSIDE_WINDOW")
    return [first, second + 1]


def require_pair_diff(family, diffs):
    require(diffs == FAMILIES[family]["pair_diff"],
            f"{FAMILIES[family]['label']}_PAIR_DIFF_MISMATCH")


def compact52_pair_verdict(baseline, result, family):
    spec = FAMILIES[family]
    require(result.get("case") == family + "1", "PAIR_MEMBER_MISMATCH")
    for record, case in zip((baseline, result), (family + "8", family + "1")):
        require(record.get("bootloader_origin") == observe.REST_ORIGIN, "PAIR_ORIGIN_MISMATCH")
        require(record.get("protocol") == observe.PROTOCOL, "PAIR_PROTOCOL_MISMATCH")
        require(record.get("case") == case, "PAIR_MEMBER_MISMATCH")
        require(record.get("image_sha256") == member_sha(case), "PAIR_IDENTITY_MISMATCH")
        require(record.get("status") == "AUTOMATIC_FASTBOOT_RETURN", "PAIR_RETURN_NOT_VALID")
        require(record.get("final_slot") == "b", "PAIR_NOT_SLOT_B")
        require(record.get("experimental_boots") == 1, "PAIR_BOOT_COUNT_INVALID")
        require(record.get("context") == observe.CONTEXT, "PAIR_CONTEXT_MISMATCH")
        require(not isinstance(record.get("total_s"), bool) and
                isinstance(record.get("total_s"), (int, float)) and
                math.isfinite(record["total_s"]) and record["total_s"] > 0,
                "PAIR_TIMING_INVALID")
    delta = result["total_s"] - baseline["total_s"]
    error = delta - EXPECTED_DELTA_SECONDS
    verdict = ("STRONG" if abs(error) <= STRONG_ERROR_SECONDS else
               "SUPPORTED" if abs(error) <= SUPPORTED_ERROR_SECONDS else "SHIFT_NOT_OBSERVED")
    grade = ("PROVEN" if verdict == "STRONG" else
             "STRONGLY_SUPPORTED" if verdict == "SUPPORTED" else "NOT_PROVEN")
    out = {"delta_s": delta, "expected_delta_s": EXPECTED_DELTA_SECONDS, "error_s": error,
           "verdict": verdict, "late_compact52_entry": grade,
           "boot_wait_for_devices_entry": grade,
           "late_initcalls_completed": "NOT_PROVEN",
           "wait_for_initramfs_return": "NOT_PROVEN",
           "console_on_rootfs_entry": "NOT_PROVEN",
           "init_executed": "NOT_PROVEN", "usb": "FROZEN"}
    if verdict == "SHIFT_NOT_OBSERVED":
        out["late_compact52_checkpoint_shift_not_observed"] = "YES"
    return out


def record(case, total):
    return {"protocol": observe.PROTOCOL, "case": case, "image_sha256": member_sha(case),
            "context": observe.CONTEXT, "status": "AUTOMATIC_FASTBOOT_RETURN",
            "final_slot": "b", "experimental_boots": 1, "total_s": total,
            "bootloader_origin": observe.REST_ORIGIN}


def reject(case, identity, gate):
    try:
        validate_member(case, *identity)
    except ValueError as exc:
        if str(exc) != "IMAGE_IDENTITY_MISMATCH":
            raise
        print(f"{gate}=PASS")
        return
    raise SystemExit(f"{gate}=FAIL")


def mutate_one_byte(sha):
    first = "1" if sha[0] != "1" else "2"
    return first + sha[1:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=("compact52",), required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GITHUB_ACTIONS_ONLY")
    family = "late_" + args.family
    spec, label = FAMILIES[family], FAMILIES[family]["label"]
    try:
        require_frozen()
    except ValueError:
        raise SystemExit(f"{label}_IDENTITY_NOT_FROZEN")
    m8, m1 = family + "8", family + "1"
    i8, i1 = member_identity(m8), member_identity(m1)
    if i8[1] == i1[1]:
        raise SystemExit(f"{label}_PAIR_MEMBER_SHA_COLLISION")
    validate_member(m8, *i8)
    validate_member(m1, *i1)
    print(f"{label}8_EXACT_FULL_SHA_ACCEPT=PASS")
    print(f"{label}1_EXACT_FULL_SHA_ACCEPT=PASS")
    reject(m8, (i8[0] + 1, i8[1]), f"{label}_WRONG_SIZE_REJECT")
    reject(m1, (i1[0], "0" * 64), f"{label}_WRONG_SHA_REJECT")
    reject(m8, (i8[0], mutate_one_byte(i8[1])), f"{label}_ONE_BYTE_MUTANT_REJECT")
    reject(m1, (i1[0], mutate_one_byte(i1[1])), f"{label}_ONE_BYTE_MUTANT_REJECT")
    reject(m8, i1, f"{label}8_REJECTS_{m1.upper()}_SWAP")
    reject(m1, i8, f"{label}1_REJECTS_{m8.upper()}_SWAP")
    reject(m8, i1, f"{label}8_WRONG_DELAY_MUTANT_REJECT")
    reject(m1, i8, f"{label}1_WRONG_DELAY_MUTANT_REJECT")
    rejections = 0
    for prior, prior_identity in sorted(observe.IMAGES.items()):
        if prior == "recovery" or prior in MEMBERS:
            continue
        reject(m8, prior_identity, f"{label}8_REJECTS_{prior.upper()}")
        reject(m1, prior_identity, f"{label}1_REJECTS_{prior.upper()}")
        rejections += 2
    print(f"{label}_CROSS_IDENTITY_REJECTIONS={rejections}")
    print(f"{label}_CROSS_IDENTITY_REJECTION=PASS")

    validate_geometry(family, spec["window"])
    for wrong in (56, 52, 64):
        try:
            validate_geometry(family, wrong)
        except ValueError as exc:
            token = (f"{label}_56B_WINDOW_REJECTED" if wrong == 56
                     else f"{label}_WINDOW_NOT_48")
            if str(exc) != token:
                raise
        else:
            raise SystemExit(f"{label}_{wrong}B_WINDOW_ACCEPTED")
    print(f"{label}_48B_INLINE_GEOMETRY=PASS")
    print(f"{label}_56B_NEGATIVE_FIXTURE=PASS")
    print(f"{label}_52B_NEGATIVE_FIXTURE=PASS")
    print(f"{label}_64B_NEGATIVE_FIXTURE=PASS")
    btic_spec = dict(spec, architecture="BTI_C_PLUS_56B_ULTRACOMPACT",
                     entry="bti c")
    saved = FAMILIES[family]
    FAMILIES[family] = btic_spec
    try:
        validate_geometry(family, spec["window"])
    except ValueError as exc:
        if str(exc) != f"{label}_ARCHITECTURE_DRIFT":
            raise
    else:
        raise SystemExit(f"{label}_BTI_C_PAD_CLASS_ACCEPTED")
    finally:
        FAMILIES[family] = saved
    validate_geometry(family, spec["window"])
    print(f"{label}_BTI_C_PAD_CLASS_REJECTED=PASS")
    print(f"{label}_COMPACT_INLINE_48B=PASS")
    validate_selection(family)
    validate_table(family)
    pair_diff_range(family)
    print(f"{label}_INDEX{spec['index']}_TABLE_GATE=PASS")
    print(f"{label}_PREL32_UNCHANGED=PASS")
    print(f"{label}_PAIR_DIFF_DELAY_CONSTANT_ONLY=PASS")
    for wrong in ([spec["offset"] + 8, spec["offset"] + 9],
                  [spec["offset"] + 10, spec["offset"] + 11],
                  [0x1B32085, 0x1B32086]):
        try:
            require_pair_diff(family, wrong)
        except ValueError as exc:
            if str(exc) != f"{label}_PAIR_DIFF_MISMATCH":
                raise
        else:
            raise SystemExit(f"{label}_WRONG_PAIR_DIFF_ACCEPTED")
    print(f"{label}_WRONG_PAIR_DIFF_NEGATIVE_FIXTURE=PASS")

    baseline = record(m8, 35.0)
    strong = compact52_pair_verdict(baseline, record(m1, 28.0), family)
    if strong.get("verdict") != "STRONG" \
            or strong.get("late_compact52_entry") != "PROVEN" \
            or strong.get("boot_wait_for_devices_entry") != "PROVEN" \
            or strong.get("late_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("wait_for_initramfs_return") != "NOT_PROVEN" \
            or strong.get("console_on_rootfs_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit(f"{label}_STRONG_PROOF_BOUNDARY_INVALID")
    print(f"{label}_STRONG_PROVES_TARGET_ENTRY=PASS")
    print(f"{label}_LATER_LATE_CONSOLE_INIT_REMAIN_NOT_PROVEN=PASS")

    supported = compact52_pair_verdict(baseline, record(m1, 29.5), family)
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get("late_compact52_entry") != "STRONGLY_SUPPORTED" \
            or supported.get("boot_wait_for_devices_entry") != "STRONGLY_SUPPORTED":
        raise SystemExit(f"{label}_SUPPORTED_GRADE_INVALID")
    print(f"{label}_SUPPORTED_GRADE=PASS")

    no_shift = compact52_pair_verdict(baseline, record(m1, 35.0), family)
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get("late_compact52_entry") != "NOT_PROVEN" \
            or no_shift.get("boot_wait_for_devices_entry") != "NOT_PROVEN" \
            or no_shift.get("late_compact52_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit(f"{label}_NO_SHIFT_SEMANTICS_INVALID")
    print(f"{label}_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print(f"{label}_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
