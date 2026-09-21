"""Actions-only PM-tail composition, linked provenance and terminal-boundary regressions."""
import argparse
import copy
import io
import json
import os
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_pm_tail_probe as d

COMMIT = "a" * 40
RUN = "12345"
FROZEN = Path(os.environ.get("PM_TAIL_FROZEN", "frozen/thyme-r3-p1b-fix8-kernel-payload.bin"))
HAS_SOURCE = all((d.cp.pb.LINUX / name).is_file() for name in d.SOURCE_FILES)
if os.environ.get("PM_TAIL_FIXTURE_REQUIRED") == "true" and not FROZEN.is_file():
    raise RuntimeError("IMMUTABLE_FIX8_TEST_INPUT_REQUIRED")
if os.environ.get("PM_TAIL_SOURCE_REQUIRED") == "true" and not HAS_SOURCE:
    raise RuntimeError("PINNED_PM_TAIL_AND_LINKED_SOURCE_REQUIRED")


def flip(data, offset):
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]


def linked_report(commit=COMMIT, run=RUN):
    return {**copy.deepcopy(d.LINKED_IDENTITY), "source_commit": commit, "public_run": run}


def manifest(payload, delay, commit=COMMIT, run=RUN):
    report = linked_report(commit, run)
    return {**copy.deepcopy(d.SCOPE), "source_commit": commit, "public_run": run,
            "source_files_sha256": copy.deepcopy(d.SOURCE_HASHES), "linked_jump_report": report,
            "linked_jump_report_canonical_sha256": d.cp.digest(d.canonical(report)),
            "case": d.CASES[delay], "delay_seconds": delay, "payload_sha256": d.cp.digest(payload),
            "checkpoint_sha256": d.cp.digest(payload[d.OFFSET:d.END])}


def feasibility(commit=COMMIT, run=RUN):
    # The unchanged five-source helper's report, including its historical wording.
    return {"gate": "DEFERRED_PM_TAIL_ENTRY_STATIC_FEASIBLE", "name": "device_pm_move_to_tail",
            "source_commit": commit, "public_run": run, "bundle_run": "35040148509",
            "bundle": copy.deepcopy(d.prior.BUNDLE_IDENTITY),
            "source_files_sha256": copy.deepcopy(d.FEASIBILITY_SOURCE_HASHES),
            "parent_offset": 0x8DE450, "parent_size": 100, "parent_sha256": d.ORIGINAL_SHA,
            "parent_words": list(d.ORIGINAL_WORDS), "offset": 0x8DE454, "window": 56, "section": ".text",
            "single_direct_caller": 0x8E84A0, "original_paciasp_preserved": True, "worker_unchanged": True,
            "core_sha256": d.CORE_SHA, "added_pointer_reads": 0, "candidate_generated": False,
            "device_ready": False, "device_operation": False, "partition_writes": 0,
            "future_positive_limit": ["reason_field_cleared", "worker_mutex_unlock_returned", "pm_tail_entry"],
            "not_proven": ["pm_tail_return", "bus_probe_entry", "driver_probe", "culprit", "init", "usb"]}


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
        self.assertEqual(d.prior.SCOPE["stage"], "after_kfree")
        self.assertEqual(set(d.prior.selected.deferred.STAGES), {"prequeue", "postflush", "worker"})

    def test_cli_private_uses_pair_report_and_forbids_audit_injection(self):
        base = ["--stage", "pm_tail", "--frozen", "frozen", "--out", "out"]
        public = ["--bundle", "bundle", "--core", "core"]
        private = ["--mode", "private", "--pair", "pair", "--boot-base", "boot",
                   "--source-commit", COMMIT, "--public-run", RUN]
        for options in ([], ["--mode", "private"], public + ["--linked-report", "linked.json"],
                        private + ["--linked-report", "linked.json"],
                        public + ["--pair", "pair"], public + ["--boot-base", "boot"],
                        public + ["--verify-boots", "boots"], private + ["--bundle", "bundle"],
                        private + ["--core", "core"], private + ["--verify-pair", "pair"]):
            with self.subTest(options=options), patch("sys.argv", ["probe", *base, *options]), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.main()
        for flag in ("--pair", "--boot-base", "--source-commit", "--public-run"):
            index = private.index(flag)
            options = private[:index] + private[index + 2:]
            with self.subTest(missing=flag), patch("sys.argv", ["probe", *base, *options]), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.main()
        # Dispatch-only mocks do not bypass an executed production gate or spoof Actions.
        for mode, options in (("audit", public), ("private", private + ["--verify-boots", "boots"])):
            with patch("sys.argv", ["probe", *base, *options]), patch.object(d, mode) as command:
                d.main()
            command.assert_called_once()
            args = command.call_args.args[0]
            self.assertEqual(args.stage, "pm_tail")
            if mode == "private":
                self.assertEqual(args.pair, Path("pair"))
                self.assertFalse(hasattr(args, "linked_report"))
                self.assertEqual(args.verify_boots, Path("boots"))

    def test_exact_100_byte_parent_and_geometry_are_frozen(self):
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
        for name in ("PARENT", "PARENT_SIZE", "OFFSET", "WINDOW", "END", "CALL"):
            with self.subTest(name=name), patch.object(d, name, getattr(d, name) + 4), \
                    self.assertRaisesRegex(ValueError, "GEOMETRY"):
                d.gate_parent(d.ORIGINAL)

    def test_full_pm_parent_and_worker_equality_includes_every_byte(self):
        d.entry.gate_parent(d.ORIGINAL, d.ORIGINAL, d.ORIGINAL)
        d.prior.gate_parent_agreement(d.prior.ORIGINAL, d.prior.ORIGINAL, d.prior.ORIGINAL)
        for gate, original in ((d.entry.gate_parent, d.ORIGINAL), (d.prior.gate_parent_agreement, d.prior.ORIGINAL)):
            for offset in range(len(original)):
                for index in range(3):
                    copies = [original] * 3
                    copies[index] = flip(original, offset)
                    with self.subTest(size=len(original), offset=offset, copy=index), \
                            self.assertRaisesRegex(ValueError, "DISAGREEMENT"):
                        gate(*copies)
        for offset in range(len(d.prior.ORIGINAL)):
            changed = flip(d.prior.ORIGINAL, offset)
            with self.subTest(worker_offset=offset), self.assertRaises(ValueError):
                d.prior.gate_parent_agreement(changed, changed, changed)
        with self.assertRaisesRegex(ValueError, "WORKER_EXTENT"):
            d.prior.gate_parent_agreement(*([d.prior.ORIGINAL[:-4]] * 3))
        d.entry.gate_call(0x97FFD7EC)
        for word in (0x17FFD7EC, 0x97FFD7EB, 0x97FFD7ED, 0xD63F0000):
            with self.assertRaisesRegex(ValueError, "ORIGINAL_BL"):
                d.entry.gate_call(word)

    def test_terminal_core_all_words_and_delay_are_frozen(self):
        for delay in (8, 1):
            core = d.cp.delay_core(d.CORE, delay)
            self.assertEqual(d.gate_core(core, delay), core)
            words = struct.unpack("<14I", core)
            self.assertEqual(d.cp.branch_target(words[8], d.OFFSET + 32), d.OFFSET + 16)
            self.assertEqual(d.cp.branch_target(words[13], d.OFFSET + 52), d.OFFSET + 48)
            self.assertEqual(words[9:], (0x52800120, 0x72B08000, 0xD4000003, 0xD503205F, 0x17FFFFFF))
            for offset in range(56):
                with self.subTest(delay=delay, offset=offset), self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
                    d.gate_core(flip(core, offset), delay)
            for candidate in (core[:-4], core + bytes(4), bytes(56)):
                with self.assertRaises(ValueError):
                    d.gate_core(candidate, delay)
        for delay in (True, 1.0, "8", 0, 2, 24):
            with self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
                d.gate_core(d.CORE, delay)

    def test_proof_is_store_execution_unlock_return_and_entry_not_persistent_state(self):
        self.assertEqual(d.SCOPE["positive_only"],
                         ["original_reason_clear_store_executed", "worker_mutex_unlock_returned", "pm_tail_entry"])
        self.assertEqual(d.SCOPE["positive_proves"], "deferred_pm_tail_entry")
        self.assertEqual(d.SCOPE["positive_does_not_prove"], "deferred_pm_tail_return")
        self.assertEqual(d.SCOPE["reason_field_state_at_checkpoint"], "NOT_PROVEN")
        self.assertNotIn("reason_field_cleared_at_checkpoint", d.SCOPE)
        for field in ("terminal_fallthrough", "normal_boot_candidate", "device_ready", "new_stack_frame"):
            self.assertIs(d.SCOPE[field], False)
        for item in ("persistent_reason_field_state", "srcu_or_pm_lock_acquired", "pm_tail_body_or_return",
                     "pm_list_movement", "first_bus_probe_entered_or_returned", "driver_probe_body",
                     "device_identity_or_name", "culprit_or_root_cause", "init_or_userspace", "usb_enablement"):
            self.assertIn(item, d.SCOPE["positive_not_proven"])
        self.assertEqual(d.SCOPE["single_direct_caller"], 0x8E84A0)
        self.assertEqual(d.SCOPE["caller_sha256"], d.cp.digest(d.prior.ORIGINAL))
        self.assertEqual(d.SCOPE["caller_agreement"], "ELF_IMAGE_FIX8_EXACT_196B")
        self.assertEqual(d.SCOPE["added_pointer_or_name_dereferences"], 0)
        self.assertEqual(set(d.SOURCE_FILES), set(d.SOURCE_HASHES))

    def test_whole_pm_parent_entry_and_interior_are_protected(self):
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

    def test_worker_interior_cannot_bypass_original_store_unlock_or_caller(self):
        image = d.cp.patch_window(bytes(d.prior.PARENT + d.prior.PARENT_SIZE), d.prior.PARENT, d.prior.ORIGINAL)
        source = d.prior.PARENT - 4
        ranges = [(source, len(image))]
        d.prior.gate_incoming(image, ranges)
        for target in (d.prior.PARENT + 4, d.prior.KFREE_CALL, 0x8E8494, 0x8E8498, d.CALL,
                       d.prior.END, d.prior.PARENT + d.prior.PARENT_SIZE - 4):
            word = 0x14000000 | (((target - source) // 4) & 0x3FFFFFF)
            candidate = d.cp.patch_window(image, source, struct.pack("<I", word))
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "INTERIOR_ENTRY"):
                d.prior.gate_incoming(candidate, ranges)

    def test_absolute_pm_entries_and_crossing_rela_relr_writes_are_rejected(self):
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE
        for target in (lo, lo + 4, d.TEXT + d.END, hi - 4):
            with self.subTest(target=target), self.assertRaises(SystemExit):
                d.cp.t3.gate_window_literal_scan(lo - 1, d.PARENT_SIZE + 1, struct.pack("<Q", target))
        for parent, size in ((d.PARENT, d.PARENT_SIZE), (d.prior.PARENT, d.prior.PARENT_SIZE)):
            lo, hi = d.TEXT + parent, d.TEXT + parent + size
            d.cp.t3.gate_window_relocation_scan(lo - 7, size + 7, [lo - 8, hi])
            for site in (lo - 7, lo - 1, lo, hi - 8, hi - 1):
                with self.subTest(rela_site=site), self.assertRaises(SystemExit):
                    d.cp.t3.gate_window_relocation_scan(lo - 7, size + 7, [site])
            for site in (lo - 4, lo, hi - 8):
                with self.subTest(relr_site=site), self.assertRaises(SystemExit):
                    d.cp.t3.gate_window_relocation_scan(lo - 7, size + 7, d.cp.decode_relr(struct.pack("<Q", site)))
            with self.assertRaises(SystemExit):
                d.cp.t3.gate_window_relocation_scan(lo - 7, size + 7,
                                                   d.cp.decode_relr(struct.pack("<QQ", lo - 12, 3)))

    def test_exception_fault_and_fixup_cover_full_pm_parent_and_worker(self):
        table = d.TEXT + 0x1B0F690
        for parent, size in ((d.PARENT, d.PARENT_SIZE), (d.prior.PARENT, d.prior.PARENT_SIZE)):
            lo, hi = d.TEXT + parent, d.TEXT + parent + size
            for target in (lo, lo + 4, hi - 4):
                for fault, fixup in ((target, hi), (lo - 4, target)):
                    record = struct.pack("<iiHH", fault - table, fixup - table - 4, 2, 0)
                    with self.subTest(fault=fault, fixup=fixup), self.assertRaisesRegex(ValueError, "EXCEPTION"):
                        d.prior.gate_exception_destinations(record, table, (lo, hi))


class LinkedGateTests(unittest.TestCase):
    def test_archived_passing_report_is_exact_and_kept_separate_from_current_provenance(self):
        report = d.read_linked_reference()
        self.assertEqual(report, d.LINKED_REFERENCE_REPORT)
        self.assertEqual((report["offset"], report["end"], report["size"], report["entries"]),
                         (0x1A97528, 0x1A9B7B8, 17040, 1065))
        self.assertEqual(report["protected"], [[d.TEXT + d.PARENT, d.TEXT + d.PARENT + 100],
                                             [d.TEXT + d.prior.PARENT, d.TEXT + d.prior.PARENT + 196]])
        self.assertEqual(report["source_commit"], "00094b32ef511699be7e817cb5f13cdb58558e8a")
        self.assertEqual(report["public_run"], "35613385810")
        self.assertEqual(d.LINKED_REFERENCE["canonical_sha256"], d.cp.digest(d.canonical(report)))
        self.assertEqual(d.SCOPE["runtime_rewrites"]["standalone_sections"]["__jump_table"], "ABSENT")
        self.assertTrue(d.SCOPE["runtime_rewrites"]["standalone_section_absence_is_not_linked_absence"])
        with self.assertRaisesRegex(ValueError, "REPORT_DRIFT:source_commit"):
            d.gate_linked_report(report, COMMIT, RUN)

    def test_linked_report_cannot_be_omitted_replaced_with_absence_or_extended(self):
        report = linked_report()
        d.gate_linked_report(report, COMMIT, RUN)
        for candidate in (None, {}, "ABSENT", d.prior.RUNTIME_TABLES):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                d.gate_linked_report(candidate, COMMIT, RUN)
        for key in report:
            candidate = copy.deepcopy(report)
            del candidate[key]
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                d.gate_linked_report(candidate, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "FIELD_SET"):
            d.gate_linked_report({**report, "waiver": True}, COMMIT, RUN)

    def test_all_linked_identity_geometry_header_table_and_provenance_fields_are_pinned(self):
        report = linked_report()
        for key in report:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                d.gate_linked_report({**report, key: None}, COMMIT, RUN)
        mutations = {"offset": d.linked.START + 8, "end": d.linked.END - 16, "entries": 1064,
                     "size": 17024, "section": "__jump_table", "sha256": "0" * 64,
                     "source_file": "include/linux/other.h", "source_sha256": "0" * 64,
                     "layout": "ABSOLUTE", "agreement": "ELF_IMAGE_ONLY", "bundle_run": "1",
                     "source_commit": "b" * 40, "public_run": "1", "candidate_generated": True,
                     "code_rewrite_overlap": [d.TEXT + d.PARENT], "target_entry_overlap": [d.TEXT + d.CALL]}
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                d.gate_linked_report({**report, key: value}, COMMIT, RUN)
        for index in (0, 1):
            for edge in (0, 1):
                candidate = copy.deepcopy(report)
                candidate["protected"][index][edge] += 4
                with self.subTest(parent=index, edge=edge), self.assertRaisesRegex(ValueError, "protected"):
                    d.gate_linked_report(candidate, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "protected"):
            d.gate_linked_report({**report, "protected": report["protected"][:1]}, COMMIT, RUN)

    def test_saved_report_requires_a_file_and_exact_current_authority(self):
        root = Path(tempfile.mkdtemp(prefix="pm-tail-linked-report-"))
        for path in (None, root / "missing.json"):
            with self.assertRaisesRegex(ValueError, "REPORT_REQUIRED"):
                d.read_linked_report(path, COMMIT, RUN)
        path = root / "report.json"
        d.save(path, linked_report())
        self.assertEqual(d.read_linked_report(path, COMMIT, RUN), linked_report())
        for commit, run in (("b" * 40, RUN), (COMMIT, "9"), ("short", RUN), (COMMIT, "0")):
            with self.assertRaises(ValueError):
                d.read_linked_report(path, commit, run)
        d.save(path, d.LINKED_REFERENCE_REPORT)
        with self.assertRaisesRegex(ValueError, "REPORT_DRIFT"):
            d.read_linked_report(path, COMMIT, RUN)

    def test_five_source_feasibility_contract_is_not_silently_extended(self):
        report = feasibility()
        self.assertEqual(d.gate_feasibility(report, COMMIT, RUN), d.FEASIBILITY_SOURCE_HASHES)
        self.assertEqual(len(d.FEASIBILITY_SOURCE_HASHES), 5)
        self.assertEqual(len(d.SOURCE_HASHES), 6)
        self.assertEqual(set(d.FEASIBILITY_SOURCE_HASHES), set(d.prior.SOURCE_FILES) | {"drivers/base/base.h"})
        for sources in ({}, d.SOURCE_HASHES, {**d.FEASIBILITY_SOURCE_HASHES, "other.c": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "FEASIBILITY_SOURCE_IDENTITIES"):
                d.gate_feasibility({**report, "source_files_sha256": sources}, COMMIT, RUN)
        for name in d.FEASIBILITY_SOURCE_HASHES:
            for value in (None, "0" * 64):
                sources = {**d.FEASIBILITY_SOURCE_HASHES, name: value}
                with self.subTest(path=name), self.assertRaisesRegex(ValueError, "FEASIBILITY_SOURCE_IDENTITIES"):
                    d.gate_feasibility({**report, "source_files_sha256": sources}, COMMIT, RUN)
        for key in report:
            candidate = copy.deepcopy(report)
            del candidate[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                d.gate_feasibility(candidate, COMMIT, RUN)
            with self.subTest(drift=key), self.assertRaises(ValueError):
                d.gate_feasibility({**report, key: None}, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "FIELD_SET"):
            d.gate_feasibility({**report, "extra": True}, COMMIT, RUN)


class PrivateReportTransportTests(unittest.TestCase):
    def reject_before_images(self, root, message):
        for verify in (None, root / "packed"):
            args = argparse.Namespace(stage="pm_tail", pair=root, source_commit=COMMIT,
                                      public_run=RUN, verify_boots=verify)
            # Isolate transport from repository selection; real private jobs retain that guard.
            with patch.object(d.prior, "gate_actions") as repository, \
                    patch.object(Path, "read_bytes") as images, patch.object(Path, "mkdir") as output, \
                    self.assertRaisesRegex(ValueError, message):
                d.private(args)
            repository.assert_called_once_with(private=True)
            images.assert_not_called()
            output.assert_not_called()

    def test_missing_pair_root_report_blocks_pack_and_reverify(self):
        self.reject_before_images(Path(tempfile.mkdtemp(prefix="pm-tail-private-missing-")), "REPORT_REQUIRED")

    def test_stale_or_modified_pair_report_blocks_pack_and_reverify(self):
        root = Path(tempfile.mkdtemp(prefix="pm-tail-private-report-"))
        report = linked_report()
        for candidate in (d.LINKED_REFERENCE_REPORT, {**report, "source_commit": "b" * 40},
                          {**report, "public_run": "9"}, {**report, "sha256": "0" * 64},
                          {**report, "source_sha256": "0" * 64}, {**report, "protected": []},
                          {**report, "extra": True}):
            with self.subTest(candidate=candidate):
                d.save(root / "linked-jump-table.json", candidate)
                self.reject_before_images(root, "LINKED_JUMP_REPORT")


class RuntimeRewriteTests(unittest.TestCase):
    def audit_table(self, name, data, table):
        out = Path(tempfile.mkdtemp(prefix="pm-tail-runtime-table-"))
        binary = out / "input.bin"
        binary.write_bytes(data)
        rows = [{"name": name, "vma": table, "file_off": 0, "size": len(data)}]
        return d.cp.audit_rewrites(out, binary, rows, (d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE))

    def test_standalone_runtime_tables_still_protect_full_pm_parent(self):
        table = d.TEXT + 0x1BC6490
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE
        records = {
            "__ex_table": lambda site: struct.pack("<iiHH", site - table, hi - table - 4, 2, 0),
            ".altinstructions": lambda site: struct.pack("<iiHBB", site - table, hi - table - 4, 0, 4, 4),
            "__jump_table": lambda site: struct.pack("<iiq", site - table, hi - table - 4, 0),
            ".static_call_sites": lambda site: struct.pack("<ii", site - table, 0),
            ".kcfi_traps": lambda site: struct.pack("<ii", site - table, hi - table - 4),
        }
        for name, make in records.items():
            for site in (lo - 4, hi):
                self.assertNotEqual(self.audit_table(name, make(site), table)[name.lstrip(".")], "ABSENT")
            for site in (lo, d.TEXT + d.OFFSET, d.TEXT + d.END, hi - 4):
                with self.subTest(section=name, site=site), self.assertRaises(SystemExit):
                    self.audit_table(name, make(site), table)

    def test_alternative_starting_before_pm_parent_cannot_cross_its_entry(self):
        table = d.TEXT + 0x1BC6490
        lo = d.TEXT + d.PARENT
        self.audit_table(".altinstructions", struct.pack("<iiHBB", lo - 8 - table, 0, 0, 8, 8), table)
        with self.assertRaisesRegex(ValueError, "ALTERNATIVE_OVERLAPS"):
            self.audit_table(".altinstructions", struct.pack("<iiHBB", lo - 4 - table, 0, 0, 8, 8), table)


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Metadata-only fixture. It can never pass the immutable full member gate.
        cls.payload = d.cp.patch_window(bytes(d.PARENT + d.PARENT_SIZE), d.OFFSET, d.CORE)
        cls.metadata = manifest(cls.payload, 8)

    def check(self, metadata, commit=COMMIT, run=RUN):
        d.gate_manifest(self.payload, metadata, 8, commit, run)

    def test_every_manifest_field_is_required_exact_and_unknown_fields_are_rejected(self):
        self.check(self.metadata)
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            d.gate_frozen(self.payload)
        for key, value in self.metadata.items():
            missing = copy.deepcopy(self.metadata)
            del missing[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                self.check(missing)
            with self.subTest(drift=key), self.assertRaises(ValueError):
                self.check({**self.metadata, key: 0 if value is None else None})
        with self.assertRaisesRegex(ValueError, "FIELD_SET"):
            self.check({**self.metadata, "extra": True})
        for commit, run in (("b" * 40, RUN), (COMMIT, "9"), ("short", RUN), (COMMIT, "0")):
            with self.assertRaises(ValueError):
                self.check(self.metadata, commit, run)
        for delay in (True, 1.0, 0, 2, 24, "8"):
            with self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
                d.gate_manifest(self.payload, self.metadata, delay, COMMIT, RUN)

    def test_linked_header_and_source_hashes_cannot_self_authorize(self):
        for name in d.SOURCE_FILES:
            for missing in (False, True):
                sources = copy.deepcopy(d.SOURCE_HASHES)
                if missing:
                    del sources[name]
                else:
                    sources[name] = "0" * 64
                with self.subTest(path=name, missing=missing), self.assertRaisesRegex(ValueError, "SOURCE_IDENTITIES"):
                    self.check({**self.metadata, "source_files_sha256": sources})
        candidate = copy.deepcopy(self.metadata)
        candidate["source_files_sha256"][d.linked.SOURCE] = "0" * 64
        candidate["linked_jump_report"]["source_sha256"] = "0" * 64
        candidate["linked_jump_report_canonical_sha256"] = d.cp.digest(d.canonical(candidate["linked_jump_report"]))
        with self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
            self.check(candidate)
        with self.assertRaisesRegex(ValueError, "SOURCE_IDENTITIES"):
            self.check({**self.metadata, "source_files_sha256": d.FEASIBILITY_SOURCE_HASHES})

    def test_archived_provenance_canonical_hash_and_current_linked_report_are_independent_gates(self):
        for key in d.LINKED_REFERENCE:
            candidate = copy.deepcopy(self.metadata)
            candidate["linked_jump_reference"][key] = None
            with self.subTest(reference=key), self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
                self.check(candidate)
        for key in self.metadata["linked_jump_report"]:
            candidate = copy.deepcopy(self.metadata)
            candidate["linked_jump_report"][key] = None
            candidate["linked_jump_report_canonical_sha256"] = d.cp.digest(d.canonical(candidate["linked_jump_report"]))
            with self.subTest(current=key), self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                self.check(candidate)
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            self.check({**self.metadata, "linked_jump_report_canonical_sha256": "0" * 64})
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            self.check({**self.metadata, "runtime_rewrites": d.prior.RUNTIME_TABLES})

    def test_private_linked_verification_requires_external_report_and_both_member_provenances(self):
        manifests = [copy.deepcopy(self.metadata), manifest(self.payload, 1)]
        report = linked_report()
        self.assertEqual(d.gate_private_linked(manifests, report, COMMIT, RUN), d.linked_binding(report, COMMIT, RUN))
        for external in (None, {}, d.LINKED_REFERENCE_REPORT, {**report, "sha256": "0" * 64},
                         {**report, "source_sha256": "0" * 64}, {**report, "protected": report["protected"][:1]}):
            with self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                d.gate_private_linked(manifests, external, COMMIT, RUN)
        for index in (0, 1):
            for key in ("linked_jump_report", "linked_jump_report_canonical_sha256", "linked_jump_reference",
                        "source_files_sha256", "source_commit", "public_run"):
                for missing in (False, True):
                    candidates = copy.deepcopy(manifests)
                    if missing:
                        del candidates[index][key]
                    else:
                        candidates[index][key] = None
                    with self.subTest(member=index, key=key, missing=missing), \
                            self.assertRaisesRegex(ValueError, "PRIVATE_LINKED_PROVENANCE"):
                        d.gate_private_linked(candidates, report, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "MANIFEST_PAIR_REQUIRED"):
            d.gate_private_linked(manifests[:1], report, COMMIT, RUN)


@unittest.skipUnless(HAS_SOURCE, "pinned Linux source unavailable")
class SourceTests(unittest.TestCase):
    def test_exact_six_sources_include_the_qualified_jump_label_header(self):
        actual = {name: d.cp.digest((d.cp.pb.LINUX / name).read_bytes()) for name in d.SOURCE_FILES}
        self.assertEqual(actual, d.SOURCE_HASHES)
        self.assertEqual(actual[d.linked.SOURCE], d.read_linked_reference()["source_sha256"])
        self.assertEqual({name: actual[name] for name in d.FEASIBILITY_SOURCE_HASHES}, d.FEASIBILITY_SOURCE_HASHES)


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

    def test_exact_members_preserve_worker_paciasp_pm_suffix_and_folded_table(self):
        for delay, payload, metadata in zip((8, 1), self.payloads, self.manifests):
            self.member(payload, metadata, delay=delay)
            self.assertEqual(payload[d.prior.PARENT:d.prior.PARENT + d.prior.PARENT_SIZE], d.prior.ORIGINAL)
            self.assertEqual(payload[d.PARENT:d.OFFSET], d.ORIGINAL[:4])
            self.assertEqual(payload[d.END:d.PARENT + d.PARENT_SIZE], d.ORIGINAL[60:])
            self.assertEqual(d.cp.digest(payload[d.linked.START:d.linked.END]), d.LINKED_IDENTITY["sha256"])
        for offset in (0, d.PARENT, d.END, d.PARENT + 96, d.prior.PARENT, d.prior.OFFSET,
                       0x8E8494, 0x8E8498, d.CALL, d.prior.PARENT + 195, d.linked.START, d.linked.END - 1,
                       len(self.frozen) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "OUTSIDE_PM_TAIL"):
                self.member(payload=flip(self.payloads[0], offset))
        with self.assertRaisesRegex(ValueError, "PAYLOAD_SIZE"):
            self.member(payload=self.payloads[0][:-1])
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            self.member(frozen=flip(self.frozen, 0))

    def test_pair_direction_all_bytes_and_complete_identity_are_bound(self):
        d.gate_pair("pm_tail", self.payloads, self.manifests, self.identity, COMMIT, RUN)
        for key in self.identity:
            missing = copy.deepcopy(self.identity)
            del missing[key]
            for candidate in (missing, {**self.identity, key: None}):
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "PAIR_IDENTITY"):
                    d.gate_pair("pm_tail", self.payloads, self.manifests, candidate, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "PAIR_IDENTITY"):
            d.gate_pair("pm_tail", self.payloads, self.manifests, {**self.identity, "extra": True}, COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            d.gate_pair("pm_tail", list(reversed(self.payloads)), self.manifests, self.identity, COMMIT, RUN)
        payloads = [self.payloads[0], flip(self.payloads[1], 0)]
        metadata = copy.deepcopy(self.manifests)
        metadata[1]["payload_sha256"] = d.cp.digest(payloads[1])
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_ONLY"):
            d.gate_pair("pm_tail", payloads, metadata, d.pair_identity(payloads, metadata, COMMIT, RUN), COMMIT, RUN)
        with self.assertRaisesRegex(ValueError, "PAIR_SIZE"):
            d.gate_pair("pm_tail", self.payloads[:1], self.manifests, self.identity, COMMIT, RUN)

    def test_rehashed_pair_cannot_authorize_linked_drift_or_common_outside_changes(self):
        for key in ("linked_jump_report", "linked_jump_report_canonical_sha256", "linked_jump_reference",
                    "source_files_sha256", "caller_sha256", "caller_agreement", "positive_only"):
            metadata = copy.deepcopy(self.manifests)
            metadata[1][key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                d.gate_pair("pm_tail", self.payloads, metadata, d.pair_identity(self.payloads, metadata, COMMIT, RUN), COMMIT, RUN)
        for delay, payload in zip((8, 1), self.payloads):
            changed = flip(payload, d.CALL)
            with self.assertRaisesRegex(ValueError, "OUTSIDE_PM_TAIL"):
                self.member(payload=changed, metadata=manifest(changed, delay), delay=delay)


@unittest.skipUnless(FROZEN.is_file(), "immutable FIX8 input unavailable")
class AuditExecutionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pm-tail-audit-execution-"))
        (self.root / "core.bin").write_bytes(d.CORE)
        (self.root / "bundle").mkdir()
        (self.root / "bundle/Image").write_bytes(b"auditor-I/O-fixture-only")
        self.commit, self.run = os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"]

    def args(self, name, verify_pair=None):
        return argparse.Namespace(stage="pm_tail", frozen=FROZEN, core=self.root / "core.bin",
                                  bundle=self.root / "bundle", out=self.root / name, verify_pair=verify_pair,
                                  source_commit=None, public_run=None)

    def write_linked(self, args):
        args.out.mkdir()
        report = linked_report(self.commit, self.run)
        d.save(args.out / "linked-jump-table.json", report)
        return report

    def write_feasibility(self, args):
        args.out.mkdir()
        d.save(args.out / "feasibility.json", feasibility(self.commit, self.run))

    def test_audit_and_reaudit_cannot_omit_executed_linked_output(self):
        for index, verify in enumerate((None, self.root / "untrusted-pair")):
            args = self.args(f"omitted-{index}", verify)
            with patch.object(d.linked, "audit", return_value=linked_report(self.commit, self.run)) as gate, \
                    patch.object(d.entry, "audit") as entry_gate, patch.object(d.prior, "audit_binary") as worker_gate, \
                    self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT_REQUIRED"):
                d.audit(args)
            gate.assert_called_once()
            entry_gate.assert_not_called()
            worker_gate.assert_not_called()
            self.assertFalse((args.out / "pair").exists())
            self.assertFalse((args.out / "audit.json").exists())

    def test_executed_report_drift_and_linked_gate_failure_stop_both_modes(self):
        def different_return(args):
            self.write_linked(args)
            return None

        def wrong_table(args):
            report = self.write_linked(args)
            report["sha256"] = "0" * 64
            d.save(args.out / "linked-jump-table.json", report)
            return report

        for index, verify in enumerate((None, self.root / "untrusted-pair")):
            for name, effect, message in (("different", different_return, "EXECUTED_REPORT_DRIFT"),
                                           ("table", wrong_table, "REPORT_DRIFT:sha256"),
                                           ("failed", ValueError("LINKED_GATE_FAILURE"), "LINKED_GATE_FAILURE")):
                args = self.args(f"{name}-{index}", verify)
                with patch.object(d.linked, "audit", side_effect=effect) as gate, \
                        patch.object(d.entry, "audit") as entry_gate, \
                        self.assertRaisesRegex(ValueError, message):
                    d.audit(args)
                gate.assert_called_once()
                entry_gate.assert_not_called()
                self.assertFalse((args.out / "pair").exists())

    def test_full_worker_audit_is_executed_after_linked_and_feasibility_in_both_modes(self):
        for index, verify in enumerate((None, self.root / "untrusted-pair")):
            args = self.args(f"worker-{index}", verify)
            with patch.object(d.linked, "audit", side_effect=self.write_linked) as linked_gate, \
                    patch.object(d.entry, "audit", side_effect=self.write_feasibility) as entry_gate, \
                    patch.object(d.prior, "audit_binary", side_effect=ValueError("FULL_WORKER_FAILURE")) as worker_gate, \
                    self.assertRaisesRegex(ValueError, "FULL_WORKER_FAILURE"):
                d.audit(args)
            linked_gate.assert_called_once()
            entry_gate.assert_called_once()
            worker_gate.assert_called_once()
            self.assertEqual(worker_gate.call_args.args[1], args.bundle / "vmlinux")
            self.assertFalse((args.out / "pair").exists())
            self.assertFalse((args.out / "audit.json").exists())

    def test_five_source_feasibility_cannot_be_replaced_by_an_extended_claim(self):
        def wrong_sources(args):
            args.out.mkdir()
            report = feasibility(self.commit, self.run)
            report["source_files_sha256"] = copy.deepcopy(d.SOURCE_HASHES)
            d.save(args.out / "feasibility.json", report)

        args = self.args("feasibility-drift")
        with patch.object(d.linked, "audit", side_effect=self.write_linked), \
                patch.object(d.entry, "audit", side_effect=wrong_sources), \
                patch.object(d.prior, "audit_binary") as worker_gate, \
                self.assertRaisesRegex(ValueError, "FEASIBILITY_SOURCE_IDENTITIES"):
            d.audit(args)
        worker_gate.assert_not_called()
        self.assertFalse((args.out / "pair").exists())

    def test_composition_and_download_style_reaudit_bind_fresh_reports_before_accepting_pair(self):
        # Only the three auditors' I/O is mocked. Immutable member, core, manifest and pair gates run unchanged.
        # The workflow separately executes all three real binary/source audits on the downloaded bundle.
        compose = self.args("compose")
        verify = self.args("reverify", compose.out / "pair")
        with patch.object(d.linked, "audit", side_effect=self.write_linked) as linked_gate, \
                patch.object(d.entry, "audit", side_effect=self.write_feasibility) as entry_gate, \
                patch.object(d.prior, "audit_binary") as worker_gate, redirect_stdout(io.StringIO()):
            d.audit(compose)
            d.audit(verify)
        self.assertEqual(linked_gate.call_count, 2)
        self.assertEqual(entry_gate.call_count, 2)
        self.assertEqual(worker_gate.call_count, 2)
        first = json.loads((compose.out / "audit.json").read_text())
        second = json.loads((verify.out / "audit.json").read_text())
        self.assertEqual(first, second)
        self.assertEqual(first["source_files_sha256"], d.SOURCE_HASHES)
        self.assertEqual(first["linked_jump_report"], linked_report(self.commit, self.run))
        self.assertEqual(json.loads((compose.out / "pair/linked-jump-table.json").read_text()),
                         first["linked_jump_report"])
        self.assertEqual((compose.out / "verified.json").read_bytes(), (verify.out / "verified.json").read_bytes())
        self.assertFalse((verify.out / "pair").exists())
        path = compose.out / "pair/8/manifest.json"
        changed = json.loads(path.read_text())
        changed["linked_jump_report"]["public_run"] = "1"
        changed["linked_jump_report_canonical_sha256"] = d.cp.digest(d.canonical(changed["linked_jump_report"]))
        d.save(path, changed)
        with patch.object(d.linked, "audit", side_effect=self.write_linked), \
                patch.object(d.entry, "audit", side_effect=self.write_feasibility), \
                patch.object(d.prior, "audit_binary"), self.assertRaisesRegex(ValueError, "REAUDIT_MANIFEST"):
            d.audit(self.args("reject-drift", compose.out / "pair"))

    def test_reaudit_requires_the_transported_report_even_after_fresh_audits_pass(self):
        args = self.args("missing-transport", self.root / "missing-pair")
        with patch.object(d.linked, "audit", side_effect=self.write_linked), \
                patch.object(d.entry, "audit", side_effect=self.write_feasibility), \
                patch.object(d.prior, "audit_binary"), self.assertRaisesRegex(ValueError, "REPORT_REQUIRED"):
            d.audit(args)
        self.assertFalse((args.out / "verified.json").exists())

    def test_matching_transport_and_manifest_corruption_cannot_replace_fresh_audit(self):
        compose = self.args("transport-compose")
        with patch.object(d.linked, "audit", side_effect=self.write_linked), \
                patch.object(d.entry, "audit", side_effect=self.write_feasibility), \
                patch.object(d.prior, "audit_binary"), redirect_stdout(io.StringIO()):
            d.audit(compose)
        root = compose.out / "pair"
        payloads = [(root / str(delay) / "payload.bin").read_bytes() for delay in (8, 1)]
        original = [json.loads((root / str(delay) / "manifest.json").read_text()) for delay in (8, 1)]
        for index, (key, value) in enumerate((("sha256", "0" * 64), ("source_sha256", "0" * 64),
                                             ("source_commit", "b" * 40), ("public_run", "9"))):
            report = {**linked_report(self.commit, self.run), key: value}
            d.save(root / "linked-jump-table.json", report)
            manifests = copy.deepcopy(original)
            for delay, metadata in zip((8, 1), manifests):
                metadata["linked_jump_report"] = report
                metadata["linked_jump_report_canonical_sha256"] = d.cp.digest(d.canonical(report))
                d.save(root / str(delay) / "manifest.json", metadata)
            d.save(root / "pair.json", d.pair_identity(payloads, manifests, self.commit, self.run))
            with self.subTest(key=key), patch.object(d.linked, "audit", side_effect=self.write_linked), \
                    patch.object(d.entry, "audit", side_effect=self.write_feasibility), \
                    patch.object(d.prior, "audit_binary"), self.assertRaisesRegex(ValueError, "LINKED_JUMP_REPORT"):
                d.audit(self.args(f"transport-reject-{index}", root))


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

    def test_envelope_fixture_cannot_bypass_immutable_base_or_frozen_gate(self):
        for payload, boot in zip(self.payloads, self.boots):
            d.gate_boot_bytes(self.frozen, payload, boot, self.base)
            with self.assertRaisesRegex(ValueError, "BASE_BOOT"):
                d.gate_boot("pm_tail", self.frozen, payload, boot, self.base)
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            d.gate_frozen(self.frozen)
        self.assertEqual(d.gate_boot_pair(self.boots), [d.cp.pb.PAGE + d.OFFSET + 9, d.cp.pb.PAGE + d.OFFSET + 10])

    def test_private_header_caller_pm_suffix_linked_table_and_trailer_cannot_change(self):
        for offset in (0, 44, d.cp.pb.PAGE + d.PARENT, d.cp.pb.PAGE + d.END, d.cp.pb.PAGE + d.CALL,
                       d.cp.pb.PAGE + d.linked.START, d.cp.pb.PAGE + d.linked.END - 1,
                       d.cp.pb.PAGE + len(self.frozen), len(self.base) - 1):
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

    def test_independent_private_identity_requires_all_fields_and_linked_provenance(self):
        manifests = [manifest(payload, delay) for delay, payload in zip((8, 1), self.payloads)]
        identity = d.pair_identity(self.payloads, manifests, COMMIT, RUN)
        records = {str(delay): {"case": d.CASES[delay], "boot_sha256": d.cp.digest(boot), "boot_size": len(boot),
                                "payload_sha256": d.cp.digest(payload)}
                   for delay, boot, payload in zip((8, 1), self.boots, self.payloads)}
        expected = d.private_identity(records, d.gate_boot_pair(self.boots), identity, manifests, linked_report(), COMMIT, RUN)
        self.assertEqual(expected["linked_jump_report"], linked_report())
        self.assertEqual(expected["linked_jump_reference"], d.LINKED_REFERENCE)
        self.assertEqual(expected["source_files_sha256"], d.SOURCE_HASHES)
        self.assertEqual(expected["public_pair_sha256"], d.cp.digest(d.canonical(identity)))
        self.assertFalse(expected["device_ready"])
        d.gate_independent_identity(copy.deepcopy(expected), expected)
        for key in expected:
            missing = copy.deepcopy(expected)
            del missing[key]
            for candidate in (missing, {**expected, key: None}):
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "INDEPENDENT_IDENTITY"):
                    d.gate_independent_identity(candidate, expected)
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_IDENTITY"):
            d.gate_independent_identity({**expected, "extra": True}, expected)
        for delay in ("8", "1"):
            for key in records[delay]:
                candidate = copy.deepcopy(expected)
                candidate["members"][delay][key] = None
                with self.subTest(member=delay, key=key), self.assertRaisesRegex(ValueError, "INDEPENDENT_IDENTITY"):
                    d.gate_independent_identity(candidate, expected)
        candidate = copy.deepcopy(expected)
        candidate["linked_jump_report"] = copy.deepcopy(d.LINKED_REFERENCE_REPORT)
        candidate["linked_jump_report_canonical_sha256"] = d.cp.digest(d.canonical(candidate["linked_jump_report"]))
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_IDENTITY"):
            d.gate_independent_identity(candidate, expected)

    def test_public_repository_cannot_enter_oem_private_mode(self):
        if os.environ.get("GITHUB_REPOSITORY") == d.prior.PUBLIC_REPOSITORY:
            with self.assertRaisesRegex(ValueError, "PRIVATE_ONLY"):
                d.private(argparse.Namespace())


if __name__ == "__main__":
    unittest.main()
