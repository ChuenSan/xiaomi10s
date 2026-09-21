"""Actions-only PM-tail composition, provenance and terminal-boundary regressions."""
import copy
import io
import os
import struct
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_probe as d

COMMIT = "a" * 40
RUN = "12345"
FROZEN = Path(os.environ.get("PM_TAIL_FROZEN", "frozen/thyme-r3-p1b-fix8-kernel-payload.bin"))
if os.environ.get("PM_TAIL_FIXTURE_REQUIRED") == "true" and not FROZEN.is_file():
    raise RuntimeError("IMMUTABLE_FIX8_TEST_INPUT_REQUIRED")


def flip(data, offset):
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]


def manifest(payload, delay):
    return {**copy.deepcopy(d.SCOPE), "source_commit": COMMIT, "public_run": RUN,
            "source_files_sha256": copy.deepcopy(d.SOURCE_HASHES),
            "case": d.CASES[delay], "delay_seconds": delay, "payload_sha256": d.cp.digest(payload),
            "checkpoint_sha256": d.cp.digest(payload[d.OFFSET:d.END])}


class BoundaryTests(unittest.TestCase):
    def test_cli_requires_new_stage_and_rejects_old_experiments(self):
        argv = ["--stage", "pm_tail", "--frozen", "frozen", "--out", "out"]
        self.assertEqual(d.parser().parse_args(argv).stage, "pm_tail")
        for stage in (None, "after_kfree", "selected", "worker", "prequeue", "postflush", "pm-tail", "defer_pmtail8"):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "UNAUTHORIZED"):
                d.gate_stage(stage)
            if stage is not None:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    d.parser().parse_args(["--stage", stage, *argv[2:]])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            d.parser().parse_args(argv[2:])
        for extra in ([], ["--mode", "private"], ["--pair", "pair", "--bundle", "bundle", "--core", "core"]):
            with patch("sys.argv", ["probe", *argv, *extra]), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.main()
        self.assertEqual(d.prior.SCOPE["stage"], "after_kfree")
        self.assertEqual(set(d.prior.selected.deferred.STAGES), {"prequeue", "postflush", "worker"})

    def test_exact_100_byte_parent_and_pac_preserved(self):
        self.assertEqual((d.PARENT, d.PARENT_SIZE, d.OFFSET, d.WINDOW, d.END),
                         (0x8DE450, 100, 0x8DE454, 56, 0x8DE48C))
        self.assertEqual(d.ORIGINAL_WORDS[0], 0xD503233F)
        d.gate_parent(d.ORIGINAL)
        for offset in range(d.PARENT_SIZE):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "EXACT_PARENT"):
                d.gate_parent(flip(d.ORIGINAL, offset))
        for candidate in (d.ORIGINAL[:-4], d.ORIGINAL + bytes(4), bytes(100)):
            with self.assertRaisesRegex(ValueError, "EXACT_PARENT"):
                d.gate_parent(candidate)

    def test_terminal_core_all_words_and_delay_are_frozen(self):
        for delay in (8, 1):
            core = d.cp.delay_core(d.CORE, delay)
            self.assertEqual(d.gate_core(core, delay), core)
            for offset in range(0, 56, 4):
                with self.subTest(delay=delay, offset=offset), self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
                    d.gate_core(flip(core, offset), delay)
            for candidate in (core[:-4], core + bytes(4), bytes(56)):
                with self.assertRaises(ValueError):
                    d.gate_core(candidate, delay)
        for delay in (True, 1.0, "8", 0, 2, 24):
            with self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
                d.gate_core(d.CORE, delay)

    def test_proof_stops_before_wrapper_body_and_driver_probe(self):
        self.assertEqual(d.SCOPE["positive_only"],
                         ["deferred_reason_field_cleared", "worker_mutex_unlock_returned", "pm_tail_entry"])
        self.assertEqual(d.SCOPE["positive_proves"], "deferred_pm_tail_entry")
        self.assertEqual(d.SCOPE["positive_does_not_prove"], "deferred_pm_tail_return")
        for field in ("terminal_fallthrough", "normal_boot_candidate", "new_stack_frame", "worker_mutex_held_at_checkpoint"):
            self.assertIs(d.SCOPE[field], False)
        self.assertEqual(d.SCOPE["single_direct_caller"], 0x8E84A0)
        self.assertEqual(d.SCOPE["caller_sha256"], d.cp.digest(d.prior.ORIGINAL))
        self.assertIn("first_bus_probe_entered_or_returned", d.SCOPE["positive_not_proven"])
        self.assertIn("init_or_userspace", d.SCOPE["positive_not_proven"])
        self.assertEqual(set(d.SOURCE_FILES), set(d.SOURCE_HASHES))

    def test_whole_parent_entry_and_interior_are_protected(self):
        image = bytearray(d.CALL + 8)
        image[d.PARENT:d.PARENT + d.PARENT_SIZE] = d.ORIGINAL
        struct.pack_into("<I", image, d.CALL, 0x97FFD7EC)
        ranges = [(d.PARENT, len(image))]

        def records(binary):
            return [d.cp.incoming_inclusive(binary, ranges, d.TEXT, lo, hi) for lo, hi in
                    ((d.TEXT + d.PARENT, d.TEXT + d.OFFSET),
                     (d.TEXT + d.OFFSET, d.TEXT + d.PARENT + d.PARENT_SIZE),
                     (d.TEXT + d.OFFSET, d.TEXT + d.END))]

        d.entry.gate_incoming_records(*records(image))
        for target in (d.PARENT, d.OFFSET, d.END - 4, d.END, d.PARENT + d.PARENT_SIZE - 4):
            candidate = bytearray(image)
            source = d.CALL + 4
            struct.pack_into("<I", candidate, source, 0x14000000 | (((target - source) // 4) & 0x3FFFFFF))
            with self.subTest(target=target), self.assertRaises(ValueError):
                d.entry.gate_incoming_records(*records(candidate))

    def test_indirect_absolute_entries_and_crossing_relocations_are_rejected(self):
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE
        for target in (lo, lo + 4, d.TEXT + d.END, hi - 4):
            with self.subTest(target=target), self.assertRaises(SystemExit):
                d.cp.t3.gate_window_literal_scan(lo - 1, d.PARENT_SIZE + 1, struct.pack("<Q", target))
        for site in (lo - 7, lo - 1, lo, d.TEXT + d.END, hi - 1):
            with self.subTest(site=site), self.assertRaises(SystemExit):
                d.cp.t3.gate_window_relocation_scan(lo - 7, d.PARENT_SIZE + 7, [site])
        d.cp.t3.gate_window_relocation_scan(lo - 7, d.PARENT_SIZE + 7, [lo - 8, hi])

    def test_exception_fault_and_fixup_cover_full_pm_parent(self):
        table = d.TEXT + 0x1B0F690
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE
        for target in (lo, lo + 4, d.TEXT + d.END, hi - 4):
            for fault, fixup in ((target, hi), (lo - 4, target)):
                record = struct.pack("<iiHH", fault - table, fixup - table - 4, 2, 0)
                with self.subTest(fault=fault, fixup=fixup), self.assertRaisesRegex(ValueError, "EXCEPTION"):
                    d.prior.gate_exception_destinations(record, table, (lo, hi))


@unittest.skipUnless(FROZEN.is_file(), "immutable FIX8 input unavailable")
class PayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = FROZEN.read_bytes()
        d.gate_frozen(cls.frozen)
        cls.payloads = [d.cp.patch_window(cls.frozen, d.OFFSET, d.cp.delay_core(d.CORE, delay)) for delay in (8, 1)]
        cls.manifests = [manifest(payload, delay) for delay, payload in zip((8, 1), cls.payloads)]
        cls.identity = d.pair_identity(cls.payloads, cls.manifests, COMMIT, RUN)

    def member(self, payload=None, metadata=None, frozen=None, delay=8, commit=COMMIT, run=RUN):
        d.gate_member("pm_tail", self.frozen if frozen is None else frozen,
                      self.payloads[0] if payload is None else payload,
                      self.manifests[0] if metadata is None else metadata, delay, commit, run)

    def test_exact_members_preserve_worker_and_complete_pm_suffix(self):
        for delay, payload, metadata in zip((8, 1), self.payloads, self.manifests):
            self.member(payload, metadata, delay=delay)
            self.assertEqual(payload[d.prior.PARENT:d.prior.PARENT + d.prior.PARENT_SIZE], d.prior.ORIGINAL)
            self.assertEqual(payload[d.PARENT:d.OFFSET], d.ORIGINAL[:4])
            self.assertEqual(payload[d.END:d.PARENT + d.PARENT_SIZE], d.ORIGINAL[60:])
        for offset in (0, d.PARENT, d.END, d.PARENT + 96, d.prior.PARENT,
                       d.prior.OFFSET, 0x8E8494, 0x8E8498, d.CALL, len(self.frozen) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "OUTSIDE_PM_TAIL"):
                self.member(payload=flip(self.payloads[0], offset))
        with self.assertRaisesRegex(ValueError, "PAYLOAD_SIZE"):
            self.member(payload=self.payloads[0][:-1])
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            self.member(frozen=flip(self.frozen, 0))

    def test_full_scope_and_authority_cannot_self_authorize(self):
        changes = {"stage": "after_kfree", "case": "defer_afterfree8", "source_commit": "b" * 40,
                   "public_run": "9", "parent_offset": d.PARENT + 4, "parent_size": 104,
                   "offset": d.OFFSET - 4, "window": 60, "window_end": d.END + 4,
                   "delay_seconds": True, "source_files_sha256": {}, "checkpoint_sha256": "0" * 64,
                   "single_direct_caller": d.CALL + 4, "caller_unchanged": False,
                   "caller_sha256": "0" * 64, "positive_proves": "driver_probe_complete",
                   "positive_only": [], "positive_not_proven": [], "incoming_entry": [],
                   "incoming_interior": [[1, 2]], "terminal_fallthrough": True,
                   "maximum_delay_seconds": 24, "new_stack_frame": True,
                   "runtime_rewrites": {}, "parent_literal_exception": ["waived"], "normal_boot_candidate": True}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.member(metadata={**self.manifests[0], key: value})
        for path in d.SOURCE_FILES:
            sources = {**d.SOURCE_HASHES, path: "0" * 64}
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "SOURCE_IDENTITIES"):
                self.member(metadata={**self.manifests[0], "source_files_sha256": sources})
        with self.assertRaisesRegex(ValueError, "FIELD_SET"):
            self.member(metadata={**self.manifests[0], "extra": True})
        for commit, run in (("b" * 40, RUN), (COMMIT, "9"), ("short", RUN), (COMMIT, "0")):
            with self.assertRaises(ValueError):
                self.member(commit=commit, run=run)

    def test_pair_direction_all_bytes_and_metadata_are_bound(self):
        d.gate_pair("pm_tail", self.payloads, self.manifests, self.identity, COMMIT, RUN)
        for key, value in (("stage", "after_kfree"), ("expected_delta_s", 7), ("cases", []),
                           ("source_commit", "b" * 40), ("public_run", "9"), ("changed_offsets", []),
                           ("payload_shas", {}), ("manifest_shas", {}), ("extra", True)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "PAIR_IDENTITY"):
                d.gate_pair("pm_tail", self.payloads, self.manifests, {**self.identity, key: value}, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            d.gate_pair("pm_tail", list(reversed(self.payloads)), self.manifests, self.identity, COMMIT, RUN)
        payloads = [self.payloads[0], flip(self.payloads[1], 0)]
        metadata = copy.deepcopy(self.manifests)
        metadata[1]["payload_sha256"] = d.cp.digest(payloads[1])
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_ONLY"):
            d.gate_pair("pm_tail", payloads, metadata, d.pair_identity(payloads, metadata, COMMIT, RUN), COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "PAIR_SIZE"):
            d.gate_pair("pm_tail", self.payloads[:1], self.manifests, self.identity, COMMIT, RUN)


class EnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = d.cp.patch_window(bytes(d.cp.t3.FIX8_PAYLOAD_SIZE), d.PARENT, d.ORIGINAL)
        cls.payloads = [d.cp.patch_window(cls.frozen, d.OFFSET, d.cp.delay_core(d.CORE, delay)) for delay in (8, 1)]
        header = bytearray(d.cp.pb.PAGE)
        header[:8] = b"ANDROID!"
        struct.pack_into("<IIII", header, 8, len(cls.frozen), 0, 0, d.cp.pb.BOOT_HEADER_V3_SIZE)
        struct.pack_into("<I", header, 40, 3)
        cls.base = bytes(header) + cls.frozen + bytes(d.BOOT_SIZE - len(header) - len(cls.frozen))
        cls.boots = [cls.base[:d.cp.pb.PAGE] + payload + cls.base[d.cp.pb.PAGE + len(payload):] for payload in cls.payloads]

    def test_byte_envelope_fixture_does_not_bypass_immutable_frozen_gate(self):
        for payload, boot in zip(self.payloads, self.boots):
            d.gate_boot_bytes(self.frozen, payload, boot, self.base)
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            d.gate_frozen(self.frozen)
        self.assertEqual(d.gate_boot_pair(self.boots), [d.cp.pb.PAGE + d.OFFSET + 9, d.cp.pb.PAGE + d.OFFSET + 10])

    def test_header_caller_suffix_trailer_and_identity_cannot_change(self):
        for offset in (0, 44, d.cp.pb.PAGE + d.PARENT, d.cp.pb.PAGE + d.END,
                       d.cp.pb.PAGE + d.CALL, d.cp.pb.PAGE + len(self.frozen), len(self.base) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "ENVELOPE_OR_OUTSIDE"):
                d.gate_boot_bytes(self.frozen, self.payloads[0], flip(self.boots[0], offset), self.base)
        with self.assertRaisesRegex(ValueError, "BOOT_PAYLOAD"):
            d.gate_boot_bytes(self.frozen, self.payloads[0], self.boots[1], self.base)
        with self.assertRaisesRegex(ValueError, "BOOT_SIZE"):
            d.gate_boot_bytes(self.frozen, self.payloads[0], self.boots[0][:-1], self.base)
        for boots in ([self.boots[0], self.boots[0]], [self.boots[0], flip(self.boots[1], 0)]):
            with self.assertRaisesRegex(ValueError, "BOOT_PAIR_NOT_DELAY"):
                d.gate_boot_pair(boots)
        with self.assertRaisesRegex(ValueError, "BOOT_PAIR_SIZE"):
            d.gate_boot_pair(self.boots[:1])


if __name__ == "__main__":
    unittest.main()
