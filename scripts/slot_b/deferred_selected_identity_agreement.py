#!/usr/bin/env python3
"""Actions-only agreement between the selected pair and frozen observer identities."""
import argparse
import hashlib
import json
import os
import re
import struct
from pathlib import Path

import observe

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GitHub Actions required")

import deferred_selected_probe as selected

OFFSET = 0x8E8468
WINDOW = 56
PAYLOAD_SIZE = 37369041
BOOT_SIZE = 37380096
CORE_WORDS = (0xD5034FDF, 0xD53BE009, 0xD37DF12A, 0xD53BE02B,
              0xD5033FDF, 0xD53BE02C, 0xCB0B018D, 0xEB0A01BF,
              0x54FFFF83, 0x52800120, 0x72B08000, 0xD4000003,
              0xD503205F, 0x17FFFFFF)
SCOPE = {
    "stage": "selected", "parent": "deferred_probe_work_func",
    "parent_offset": 0x8E8424, "parent_size": 196,
    "offset": OFFSET, "window": WINDOW, "window_end": 0x8E84A0,
    "section": ".text", "inline_only": True, "normal_boot_candidate": False,
    "positive_proves": "deferred_worker_device_pointer_loaded",
    "positive_does_not_prove": "deferred_first_bus_probe_entered",
    "frozen_payload_sha256": "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41",
    "core_sha256": "8b90e4c5ba8817ed23414b0d41e94bc376021d2839889b6a87c6023aa5e259b5",
    "terminal_core": "PSCI_SYSTEM_RESET_OR_LOCAL_WFE_LOOP", "terminal_fallthrough": False,
    "empty_list_branch": [0x8E8454, 0x8E84C8], "empty_list_reaches_probe": False,
    "retained_backedge": [0x8E84C4, 0x8E8460], "retained_backedge_reachable": False,
    "pac_and_frame_preserved": True, "outside_window_unchanged": True,
    "window_agreement": "EXACT", "parent_agreement": "ELF_IMAGE_FIX8_EXACT_196B",
    "parent_literal_exception": [], "incoming": [],
    "prefix_incoming": [[0xFFFF8000808E84C4, 0xFFFF8000808E8460]],
    "first_nonempty_worker_iteration_only": True, "callback_first_activation_only": False,
    "added_pointer_or_name_dereferences": 0, "mutex_held_at_checkpoint": True,
    "exception_fixup_destinations": "CHECKED_FULL_PARENT", "partition_writes": 0,
    "runtime_rewrites": {
        "__ex_table": {"entries": 994,
                       "sha256": "e93f6326dba119d9b5091b9c31295e47086ce45813b6f1a62dde0655ca65a9be"},
        "altinstructions": {"entries": 37287,
                            "sha256": "a98a9bc613c12519ea5fd8f1e168ede872af0d8474fa385df6bc1cc17fdc36a6"},
        "__jump_table": "ABSENT", "static_call_sites": "ABSENT", "kcfi_traps": "ABSENT",
    },
}
require = observe.require


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def require_fields(actual, expected, label):
    require(isinstance(actual, dict), label)
    for key, value in expected.items():
        require(key in actual and canonical(actual[key]) == canonical(value), f"{label}:{key}")


def validate_frozen(frozen):
    require_fields(frozen, {"stage": "selected", "offset": OFFSET, "window": WINDOW,
                           "parent_offset": 0x8E8424, "parent_size": 196,
                           "boot_size": BOOT_SIZE}, "SELECTED_FREEZE_GEOMETRY")
    for key in ("source_commit", "private_commit"):
        value = frozen.get(key)
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) and
                len(set(value)) > 2, f"SELECTED_FREEZE_AUTHORITY:{key}")
    for key in ("public_run", "private_run"):
        require(isinstance(frozen.get(key), str) and
                re.fullmatch(r"[1-9][0-9]*", frozen[key]), f"SELECTED_FREEZE_AUTHORITY:{key}")
    members = frozen.get("members")
    require(isinstance(members, dict) and set(members) == {"8", "1"}, "SELECTED_FREEZE_MEMBERS")
    hashes = []
    for delay, identity in members.items():
        require_fields(identity, {"boot_size": BOOT_SIZE}, f"SELECTED_FREEZE_SIZE:{delay}")
        for key in ("boot_sha256", "payload_sha256"):
            value = identity.get(key)
            require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) and
                    len(set(value)) > 2, f"SELECTED_FREEZE_HASH:{delay}:{key}")
            hashes.append(value)
    require(len(set(hashes)) == 4, "SELECTED_FREEZE_HASH_COLLISION")


def validate_pair_authority(pair, frozen):
    require_fields(pair, {"stage": "selected", "source_commit": frozen["source_commit"],
                          "public_run": frozen["public_run"], "expected_delta_s": -7,
                          "changed_offsets": [OFFSET + 9, OFFSET + 10],
                          "cases": ["defer_selected8", "defer_selected1"],
                          "payload_shas": {delay: identity["payload_sha256"]
                                           for delay, identity in frozen["members"].items()}},
                   "SELECTED_PAIR_AUTHORITY")
    require(isinstance(pair.get("manifest_shas"), dict) and
            set(pair["manifest_shas"]) == {"8", "1"}, "SELECTED_PAIR_MANIFEST_IDENTITIES")


def validate_manifest(manifest, frozen, delay):
    require_fields(manifest, SCOPE, "SELECTED_MANIFEST_SCOPE")
    selected.gate_fields(manifest, selected.SCOPE, "SELECTED_MANIFEST_SOURCE_SCOPE")
    require_fields(manifest, {"source_commit": frozen["source_commit"],
                              "public_run": frozen["public_run"],
                              "case": f"defer_selected{delay}", "delay_seconds": int(delay),
                              "payload_sha256": frozen["members"][delay]["payload_sha256"]},
                   "SELECTED_MANIFEST_AUTHORITY")
    sources = manifest.get("source_files_sha256")
    require(isinstance(sources, dict) and set(sources) == set(selected.SOURCE_FILES),
            "SELECTED_MANIFEST_SOURCE_FILES")
    for name, value in sources.items():
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) and
                len(set(value)) > 2, f"SELECTED_MANIFEST_SOURCE_HASH:{name}")


def verify(root, frozen):
    validate_frozen(frozen)
    pair = json.loads((root / "pair.json").read_text())
    validate_pair_authority(pair, frozen)
    payloads, manifests = [], []
    for delay in ("8", "1"):
        member = root / delay
        manifest = json.loads((member / "manifest.json").read_text())
        payload = (member / "payload.bin").read_bytes()
        identity = frozen["members"][delay]
        validate_manifest(manifest, frozen, delay)
        require(digest(canonical(manifest)) == pair["manifest_shas"][delay],
                "SELECTED_MANIFEST_DIGEST_MISMATCH")
        require(len(payload) == PAYLOAD_SIZE, "SELECTED_PAYLOAD_SIZE_MISMATCH")
        require(digest(payload) == identity["payload_sha256"], "SELECTED_PAYLOAD_IDENTITY_MISMATCH")
        words = list(CORE_WORDS)
        if delay == "1":
            words[2] = 0xD340FD2A
        core = payload[OFFSET:OFFSET + WINDOW]
        require(core == struct.pack("<14I", *words), "SELECTED_CORE_OR_DELAY_MISMATCH")
        require(digest(core) == manifest.get("checkpoint_sha256"), "SELECTED_CORE_IDENTITY_MISMATCH")
        case = f"defer_selected{delay}"
        observe.validate_identity(case, identity["boot_size"], identity["boot_sha256"])
        require(case in observe.ORIGIN_CASES, "SELECTED_ORIGIN_GATE_MISSING")
        payloads.append(payload)
        manifests.append(manifest)
    changed = [index for index, (first, second) in enumerate(zip(*payloads)) if first != second]
    require(changed == [OFFSET + 9, OFFSET + 10], "SELECTED_PAIR_NOT_DELAY_ONLY")
    common = [{key: value for key, value in manifest.items() if key not in
               {"case", "delay_seconds", "payload_sha256", "checkpoint_sha256"}}
              for manifest in manifests]
    require(canonical(common[0]) == canonical(common[1]), "SELECTED_PAIR_METADATA_DRIFT")
    require(observe.PAIRS.get("defer_selected1") ==
            ("defer_selected8", "deferred_worker_device_pointer_loaded", "deferred_first_bus_probe_entered"),
            "SELECTED_OBSERVER_PROOF_DRIFT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads(Path(__file__).with_name("deferred_selected_identities.json").read_text())
    verify(args.root, frozen)
    print("DEFERRED_SELECTED_OBSERVER_IDENTITY_AGREEMENT=PASS")


if __name__ == "__main__":
    main()
