#!/usr/bin/env python3
"""Compare frozen observer identities with the authoritative public artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import observe

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GitHub Actions required")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    frozen = json.loads(Path(__file__).with_name("deferred_probe_identities.json").read_text())
    for stage, spec in frozen["stages"].items():
        root = args.root / stage
        pair = json.loads((root / "pair.json").read_text())
        assert pair["stage"] == stage
        source_run = spec.get("public_run", frozen["public_run"])
        source_commit = spec.get("source_commit", frozen["source_commit"])
        assert pair["public_run"] == source_run
        assert pair["source_commit"] == source_commit
        assert pair["changed_offsets"] == [spec["offset"] + 9, spec["offset"] + 10]
        for delay, identity in spec["members"].items():
            manifest = json.loads((root / delay / "manifest.json").read_text())
            payload = (root / delay / "payload.bin").read_bytes()
            assert manifest["source_commit"] == source_commit
            assert manifest["stage"] == stage and manifest["delay_seconds"] == int(delay)
            assert manifest["offset"] == spec["offset"] and manifest["window"] == 56
            assert manifest["parent"] == ("deferred_probe_work_func" if stage == "worker"
                                           else "deferred_probe_initcall")
            assert manifest["section"] == ".text" and manifest["inline_only"] is True
            assert manifest["normal_boot_candidate"] is False
            assert manifest["incoming"] == [] and manifest["window_agreement"] == "EXACT"
            assert hashlib.sha256(payload).hexdigest() == manifest["payload_sha256"] \
                == pair["payload_shas"][delay] == identity["payload_sha256"]
            assert observe.IMAGES[f"defer_{stage}{delay}"] == \
                (frozen["boot_size"], identity["boot_sha256"])
    print("DEFERRED_OBSERVER_IDENTITY_AGREEMENT=PASS")


if __name__ == "__main__":
    main()
