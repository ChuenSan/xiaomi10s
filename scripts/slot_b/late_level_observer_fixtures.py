#!/usr/bin/env python3
"""GHA-only LATE_MID/LATE_LOW/LATE_HIGH PUBLIC observer fixtures (late-level failure isolation)."""
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
# Frozen boot identities (37380096 each). Plug-in points: fill from the private
# pack run pair-identity.txt (LATE_<F><D>_BOOT_SHA256) before the observer
# fixtures or the device round run; a family stays unrunnable until frozen.
LATE_MID8_SHA = ""
LATE_MID1_SHA = ""
LATE_LOW8_SHA = ""
LATE_LOW1_SHA = ""
LATE_HIGH8_SHA = ""
LATE_HIGH1_SHA = ""
FROZEN_IDENTITIES = {
    "late_mid": {"8": LATE_MID8_SHA, "1": LATE_MID1_SHA},
    "late_low": {"8": LATE_LOW8_SHA, "1": LATE_LOW1_SHA},
    "late_high": {"8": LATE_HIGH8_SHA, "1": LATE_HIGH1_SHA},
}
FROZEN_PRIOR_SHAS = {
    "late_devprobe8": "44e5001fab6f7c662e1847972b886d1aa4f7a51e3f969b4dce834ae34b60fe8f",
    "late_devprobe1": "0d24156eeb37f31aceac314fe7df78a9dfaffd162134c3b5d7aa029d2e512453",
    "waitentry8": "66201264f8d7b7f4ba7a4ce8f495e46c6d4d0764863ffa5f49109b3a71944d7d",
    "waitentry1": "8b422262aa73809a2258ecb7e8a3e36941eff683ed8cb2b3cce16dd4072d530e",
    "waitret8": "2c589a61933d8f657e0ac08374c6038d0624807f11c6acb22fc1851ca0b9cb2a",
    "waitret1": "0a67761550906d05e602be83afe6b2f5e10cf4d222bdcc3bdc65e24fb950d2c8",
}
PRIOR_FAMILIES = ("fs", "upper", "control", "mid", "post39", "post46", "post49", "post51",
                  "reset", "rest", "kinit", "free", "smp", "initcalls", "console", "pure",
                  "core", "postcore", "arch", "subsys", "devprobe", "late_devprobe",
                  "waitentry", "waitret")
FAMILIES = {
    "late_mid": {
        "label": "LATE_MID", "index": 43, "nominal_index": 43,
        "target": "integrity_fs_init", "va": 0xFFFF800081B5BD1C, "offset": 0x1B5BD1C,
        "function_size": 112, "window": 60, "core_size": 56,
        "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT", "entry": "paciasp",
        "daifset": "PRESENT", "inline_only": True, "prel32_unchanged": True,
        "table_va": 0xFFFF800081D0C384, "prel32_word": "0xffe4f998", "relative": -1771112,
        "pair_diff": [0x1B5BD29, 0x1B5BD2A], "deviation": None},
    "late_low": {
        "label": "LATE_LOW", "index": 21, "nominal_index": 21,
        "target": "kexec_core_sysctl_init", "va": 0xFFFF800081B47510, "offset": 0x1B47510,
        "function_size": 60, "window": 60, "core_size": 56,
        "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT", "entry": "paciasp",
        "daifset": "PRESENT", "inline_only": True, "prel32_unchanged": True,
        "table_va": 0xFFFF800081D0C32C, "prel32_word": "0xffe3b1e4", "relative": -1855004,
        "pair_diff": [0x1B4751D, 0x1B4751E], "deviation": None},
    "late_high": {
        "label": "LATE_HIGH", "index": 63, "nominal_index": 64,
        "target": "bpf_kfunc_init", "va": 0xFFFF800081BAA15C, "offset": 0x1BAA15C,
        "function_size": 260, "window": 60, "core_size": 56,
        "architecture": "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT", "entry": "paciasp",
        "daifset": "PRESENT", "inline_only": True, "prel32_unchanged": True,
        "table_va": 0xFFFF800081D0C3D4, "prel32_word": "0xffe9dd88", "relative": -1450616,
        "pair_diff": [0x1BAA169, 0x1BAA16A],
        "deviation": {"nominal_index": 64, "chosen_index": 63, "distance": 1}},
}
MEMBERS = tuple(family + member for family in FAMILIES for member in ("8", "1"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def member_sha(case):
    family, member = case[:-1], case[-1]
    require(family in FAMILIES, "CASE_NOT_LATE_LEVEL")
    sha = FROZEN_IDENTITIES[family][member]
    require(bool(sha), "LATE_LEVEL_IDENTITY_NOT_FROZEN")
    return sha


def member_identity(case):
    return (BOOT_SIZE, member_sha(case))


def validate_member(case, size, digest):
    require(case in MEMBERS, "CASE_NOT_LATE_LEVEL")
    require((size, digest) == (BOOT_SIZE, member_sha(case)), "IMAGE_IDENTITY_MISMATCH")


def validate_geometry(family, window):
    spec, label = FAMILIES[family], FAMILIES[family]["label"]
    require(window != 56, f"{label}_56B_WINDOW_REJECTED")
    require(window == spec["window"], f"{label}_WINDOW_NOT_60")
    require(spec["window"] <= spec["function_size"], f"{label}_WINDOW_EXCEEDS_FUNCTION")
    require(spec["core_size"] == 56, f"{label}_CORE_NOT_56")
    require(spec["architecture"] == "INLINE_PACIASP_PLUS_56B_ULTRACOMPACT",
            f"{label}_ARCHITECTURE_DRIFT")
    require(spec["entry"] == "paciasp", f"{label}_ENTRY_NOT_PACIASP")
    require(spec["daifset"] == "PRESENT", f"{label}_DAIFSET_ABSENT")
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
    require(spec["pair_diff"] == [spec["offset"] + 13, spec["offset"] + 14],
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


def late_level_pair_verdict(baseline, result, family):
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
    error = delta + 7.0
    verdict = ("STRONG" if abs(error) <= STRONG_ERROR_SECONDS else
               "SUPPORTED" if abs(error) <= SUPPORTED_ERROR_SECONDS else "SHIFT_NOT_OBSERVED")
    grade = ("PROVEN" if verdict == "STRONG" else
             "SUPPORTED" if verdict == "SUPPORTED" else "NOT_PROVEN")
    out = {"delta_s": delta, "expected_delta_s": EXPECTED_DELTA_SECONDS, "error_s": error,
           "verdict": verdict, f"{spec['label']}_ENTRY": grade,
           "late_initcalls_completed": "NOT_PROVEN",
           "wait_for_initramfs_return": "NOT_PROVEN",
           "console_on_rootfs_entry": "NOT_PROVEN",
           "init_executed": "NOT_PROVEN", "usb": "FROZEN"}
    if verdict == "SHIFT_NOT_OBSERVED":
        out[f"{family}_checkpoint_shift_not_observed"] = "YES"
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=("mid", "low", "high"), required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("GITHUB_ACTIONS_ONLY")
    family = "late_" + args.family
    spec, label = FAMILIES[family], FAMILIES[family]["label"]
    for case, sha in FROZEN_PRIOR_SHAS.items():
        if observe.IMAGES.get(case) != (BOOT_SIZE, sha):
            raise SystemExit(f"FROZEN_{case.upper()}_IDENTITY_DRIFT")
    if not all(FROZEN_IDENTITIES[family].values()):
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
    reject(m8, i1, f"{label}8_REJECTS_{m1.upper()}_SWAP")
    reject(m1, i8, f"{label}1_REJECTS_{m8.upper()}_SWAP")
    reject(m8, i1, f"{label}8_WRONG_DELAY_MUTANT_REJECT")
    reject(m1, i8, f"{label}1_WRONG_DELAY_MUTANT_REJECT")
    rejections = 0
    for prior_family in PRIOR_FAMILIES:
        for member in ("8", "1"):
            prior = prior_family + member
            if prior not in observe.IMAGES:
                continue
            reject(m8, observe.IMAGES[prior], f"{label}8_REJECTS_{prior.upper()}")
            reject(m1, observe.IMAGES[prior], f"{label}1_REJECTS_{prior.upper()}")
            rejections += 2
    for other in FAMILIES:
        if other == family:
            continue
        for member in ("8", "1"):
            other_case = other + member
            try:
                other_identity = member_identity(other_case)
            except ValueError as exc:
                if str(exc) != "LATE_LEVEL_IDENTITY_NOT_FROZEN":
                    raise
                continue
            reject(m8, other_identity, f"{label}8_REJECTS_{other_case.upper()}")
            reject(m1, other_identity, f"{label}1_REJECTS_{other_case.upper()}")
            rejections += 2
    print(f"{label}_CROSS_IDENTITY_REJECTIONS={rejections}")
    print(f"{label}_CROSS_IDENTITY_REJECTION=PASS")

    validate_geometry(family, spec["window"])
    for wrong in (56, 52, 64):
        try:
            validate_geometry(family, wrong)
        except ValueError as exc:
            token = (f"{label}_56B_WINDOW_REJECTED" if wrong == 56
                     else f"{label}_WINDOW_NOT_60")
            if str(exc) != token:
                raise
        else:
            raise SystemExit(f"{label}_{wrong}B_WINDOW_ACCEPTED")
    print(f"{label}_60B_INLINE_GEOMETRY=PASS")
    print(f"{label}_56B_NEGATIVE_FIXTURE=PASS")
    print(f"{label}_52B_NEGATIVE_FIXTURE=PASS")
    print(f"{label}_64B_NEGATIVE_FIXTURE=PASS")
    validate_selection(family)
    validate_table(family)
    pair_diff_range(family)
    print(f"{label}_INDEX{spec['index']}_TABLE_GATE=PASS")
    print(f"{label}_PACIASP_56B_ULTRACOMPACT=PASS")
    print(f"{label}_PREL32_UNCHANGED=PASS")
    print(f"{label}_PAIR_DIFF_DELAY_CONSTANT_ONLY=PASS")
    for wrong in ([spec["offset"] + 12, spec["offset"] + 13],
                  [spec["offset"] + 14, spec["offset"] + 15],
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
    strong = late_level_pair_verdict(baseline, record(m1, 28.0), family)
    if strong.get("verdict") != "STRONG" \
            or strong.get(f"{label}_ENTRY") != "PROVEN" \
            or strong.get("late_initcalls_completed") != "NOT_PROVEN" \
            or strong.get("wait_for_initramfs_return") != "NOT_PROVEN" \
            or strong.get("console_on_rootfs_entry") != "NOT_PROVEN" \
            or strong.get("init_executed") != "NOT_PROVEN" \
            or strong.get("usb") != "FROZEN":
        raise SystemExit(f"{label}_STRONG_PROOF_BOUNDARY_INVALID")
    print(f"{label}_STRONG_PROVES_TARGET_ENTRY=PASS")
    print(f"{label}_LATER_LATE_CONSOLE_INIT_REMAIN_NOT_PROVEN=PASS")

    supported = late_level_pair_verdict(baseline, record(m1, 29.5), family)
    if supported.get("verdict") != "SUPPORTED" \
            or supported.get(f"{label}_ENTRY") != "SUPPORTED":
        raise SystemExit(f"{label}_SUPPORTED_GRADE_INVALID")
    print(f"{label}_SUPPORTED_GRADE=PASS")

    no_shift = late_level_pair_verdict(baseline, record(m1, 35.0), family)
    if no_shift.get("verdict") != "SHIFT_NOT_OBSERVED" \
            or no_shift.get(f"{label}_ENTRY") != "NOT_PROVEN" \
            or no_shift.get(f"{family}_checkpoint_shift_not_observed") != "YES" \
            or any("not_reached" in key for key in no_shift):
        raise SystemExit(f"{label}_NO_SHIFT_SEMANTICS_INVALID")
    print(f"{label}_NO_SHIFT_DOES_NOT_CLAIM_NOT_REACHED=PASS")
    print(f"{label}_OBSERVER_FIXTURES=PASS")
    print("DEVICE_OPERATION=NO")


if __name__ == "__main__":
    main()
