#!/usr/bin/env python3
"""Assert the frozen TEXT54 registry equals the frozen public CI manifests.

Run after materializing the frozen public run's map-and-audits artifact:

  gh run download 35520679000 -R ChuenSan/xiaomi10s \
    -n thyme-late-text54-map-and-audits -D <root>

Three sources are compared, so agreement is not a tautology:
  observe's registry (what the device round actually drives),
  the fixtures' independent literals, and
  the frozen artifact's pair.json / per-member checkpoint manifest /
  audit-summary.txt.
This is what catches a mistranscribed SHA - the failure mode that put a wrong
payload8 value (...40128a1) into mem0 metadata while the artifacts said
...40128a5. GHA-only.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe
import late_text54_observer_fixtures as of

EXPECTED_RUN = "35520679000"
EXPECTED_OFFSETS = [9336177, 9336178]
EXPECTED_ATTRIBUTION = "DELAY_CONSTANT_ONLY"


def load_manifests(root):
    """-> {source_label: payload sha} read straight from the frozen artifact."""
    pair = json.loads((root / "late_text54" / "pair" / "pair.json").read_text())
    observed = {"pair.json:delay8": pair["delay8_payload_sha256"],
                "pair.json:delay1": pair["delay1_payload_sha256"]}
    for member, name in (("8", "TEXT54_8"), ("1", "TEXT54_1")):
        manifest = json.loads((root / "late_text54" / "pair" / member /
                               "checkpoint" / "manifest.json").read_text())
        observed[f"manifest:{name}"] = manifest["payload_sha256"]
    summary = {}
    for line in (root / "audit-summary.txt").read_text().splitlines():
        if "=" in line and (line.startswith("TEXT54_") or line.startswith("PAIR_DIFF=")):
            key, value = line.split("=", 1)
            summary[key] = value
    observed["audit-summary:TEXT54_8"] = summary["TEXT54_8_PAYLOAD_SHA"]
    observed["audit-summary:TEXT54_1"] = summary["TEXT54_1_PAYLOAD_SHA"]
    for label, value in sorted(observed.items()):
        assert len(value) == 64 and not of.is_placeholder_sha(value), f"{label}={value}"
    assert summary["PAIR_DIFF"] == EXPECTED_ATTRIBUTION, summary["PAIR_DIFF"]
    assert summary["TEXT54_PAIR_DIFF_OFFSETS"] == "[9336177, 9336178]", summary
    assert pair["public_run"] == EXPECTED_RUN, pair["public_run"]
    assert pair["attribution"] == EXPECTED_ATTRIBUTION, pair["attribution"]
    assert pair["changed_offsets"] == EXPECTED_OFFSETS, pair["changed_offsets"]
    assert pair["pair_diff_offsets"] == EXPECTED_OFFSETS, pair["pair_diff_offsets"]
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    # Registry side. observe.py is the authority the observer drives.
    of.require_authoritative()
    of.require_registry_agreement()
    registry = {"pair.json:delay8": observe.TEXT54_8_PAYLOAD_SHA256,
                "pair.json:delay1": observe.TEXT54_1_PAYLOAD_SHA256,
                "manifest:TEXT54_8": observe.TEXT54_8_PAYLOAD_SHA256,
                "manifest:TEXT54_1": observe.TEXT54_1_PAYLOAD_SHA256,
                "audit-summary:TEXT54_8": observe.TEXT54_8_PAYLOAD_SHA256,
                "audit-summary:TEXT54_1": observe.TEXT54_1_PAYLOAD_SHA256}
    observed = load_manifests(args.root)
    disagreements = sorted(label for label, sha in observed.items() if registry[label] != sha)
    for label in disagreements:
        print(f"TEXT54_MANIFEST_DISAGREEMENT={label}")
    if disagreements:
        raise SystemExit("TEXT54_PUBLIC_MANIFEST_AGREEMENT=FAIL")
    print("TEXT54_PUBLIC_MANIFEST_AGREEMENT=PASS")
    print(f"TEXT54_PUBLIC_MANIFEST_ENTRIES={len(observed)}")
    print("TEXT54_PUBLIC_PAIR_DIFF=DELAY_CONSTANT_ONLY")
    print("TEXT54_FROZEN_PUBLIC_RUN=" + EXPECTED_RUN)
    print("PARTITION_WRITES=0")
    print("SLOT_A_WRITTEN=NO")
    print("DEVICE_OPERATION=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
