import copy
import struct
import unittest
from unittest.mock import patch

import deferred_probe_checkpoints as d


class DeferredCheckpointTests(unittest.TestCase):
    def test_exact_scoped_windows(self):
        self.assertEqual(set(d.STAGES), {"prequeue", "postflush"})
        self.assertEqual(d.STAGES["prequeue"]["offset"], 0x8E7614)
        self.assertEqual(d.STAGES["postflush"]["offset"], 0x8E76B8)
        for name, spec in d.STAGES.items():
            raw = struct.pack("<14I", *spec["words"])
            d.gate_window(name, spec["offset"], raw)
            with self.assertRaisesRegex(ValueError, "GEOMETRY"):
                d.gate_window(name, spec["offset"] + 4, raw)
            with self.assertRaisesRegex(ValueError, "WINDOW_DRIFT"):
                d.gate_window(name, spec["offset"], bytes(56))
            with self.assertRaisesRegex(ValueError, "GEOMETRY"):
                d.gate_window(name, spec["offset"], raw[:-4])

    def test_frozen_entry_and_alternative_windows_are_disjoint(self):
        excluded = [(d.PARENT, d.PARENT + 60), (0x8E75B4, 0x8E75B8),
                    (0x8E764C, 0x8E7650)]
        for spec in d.STAGES.values():
            for lo, hi in excluded:
                self.assertFalse(d.cp.windows_overlap((spec["offset"], spec["offset"] + 56),
                                                       (lo, hi)))

    def test_unknown_scope_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED"):
            d.gate_window("text54", d.PARENT, bytes(56))

    def test_source_contract_and_negative_fixtures(self):
        source = (d.cp.pb.LINUX / "drivers/base/dd.c").read_text()
        d.source_contract(source, "CONFIG_MODULES=y\n")
        for mutation in (source.replace("initcalls_done = true;", "initcalls_done = false;"),
                         source.replace("late_initcall(deferred_probe_initcall);", ""),
                         source.replace("flush_work(&deferred_probe_work);", "")):
            with self.assertRaises(ValueError):
                d.source_contract(mutation, "CONFIG_MODULES=y\n")
        with self.assertRaisesRegex(ValueError, "MODULES_CONFIG"):
            d.source_contract(source, "# CONFIG_MODULES is not set\n")

    def test_pair_delay_only_and_identity_rejection(self):
        for stage, spec in d.STAGES.items():
            offset = spec["offset"]
            core = struct.pack("<14I", *d.cp.ULTRACOMPACT_WORDS)
            base = bytes(d.cp.t3.FIX8_PAYLOAD_SIZE)
            payloads = [d.cp.patch_window(base, offset, d.cp.delay_core(core, delay))
                        for delay in (8, 1)]
            identity = {"stage": stage, "changed_offsets": [offset + 9, offset + 10],
                        "payload_shas": {str(delay): d.cp.digest(p)
                                         for delay, p in zip((8, 1), payloads)}}
            d.gate_pair(stage, payloads, identity)
            bad = copy.deepcopy(identity)
            bad["payload_shas"]["1"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "PAIR_SHA"):
                d.gate_pair(stage, payloads, bad)
            with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY"):
                d.gate_pair(stage, [payloads[0], b"x" + payloads[1][1:]], identity)

    def test_member_mutations_and_sibling_rejection(self):
        stage = "prequeue"
        offset = d.STAGES[stage]["offset"]
        base = bytes(d.cp.t3.FIX8_PAYLOAD_SIZE)
        core = struct.pack("<14I", *d.cp.ULTRACOMPACT_WORDS)
        payload = d.cp.patch_window(base, offset, core)
        manifest = {"stage": stage, "offset": offset, "window": 56,
                    "parent": "deferred_probe_initcall", "parent_offset": d.PARENT,
                    "parent_size": 492, "section": ".text", "inline_only": True,
                    "normal_boot_candidate": False, "delay_seconds": 8,
                    "frozen_payload_sha256": d.cp.t3.FIX8_PAYLOAD_SHA,
                    "payload_sha256": d.cp.digest(payload),
                    "checkpoint_sha256": d.cp.digest(core)}
        with patch.object(d.cp.t3, "gate_tramp_identity"):
            d.gate_member(stage, base, payload, manifest)
            for key, wrong in (("stage", "postflush"), ("offset", offset + 4),
                               ("window", 60), ("section", ".init.text"),
                               ("payload_sha256", "0" * 64), ("delay_seconds", 1),
                               ("normal_boot_candidate", True)):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    d.gate_member(stage, base, payload, {**manifest, key: wrong})
            with self.assertRaisesRegex(ValueError, "OUTSIDE_CALLSITE"):
                d.gate_member(stage, base, b"x" + payload[1:], manifest)
            with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
                d.gate_member(stage, base, d.cp.patch_window(payload, offset + 52, bytes(4)),
                              manifest)
            with self.assertRaises(ValueError):
                d.gate_member("postflush", base, payload, manifest)

    def test_no_device_commands_or_deletion(self):
        source = d.Path(d.__file__).read_text()
        for token in ("unlink(", "rmtree(", "os.remove(", '"fastboot"', '"adb"'):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
