import copy
import json
import os
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import call, patch

import deferred_after_kfree_identity_agreement as agreement
import observe as o

CASES = ("defer_afterfree8", "defer_afterfree1")
AUTHORITY_FIELDS = ("stage", "source_commit", "public_run", "private_commit", "private_run")
PROVEN_FIELDS = ("deferred_reason_kfree_returned", "mutex_acquired", "active_list_nonempty",
                 "deferred_worker_device_pointer_loaded", "deferred_list_del_init_completed",
                 "deferred_get_device_returned", "deferred_reason_pointer_loads")
UNPROVEN_FIELDS = ("deferred_device_pointer_valid", "deferred_device_name",
                   "deferred_get_device_reference_success", "deferred_reason_nonnull_or_valid",
                   "deferred_allocation_freed", "deferred_reason_field_cleared",
                   "deferred_worker_mutex_unlocked", "deferred_device_pm_move_to_tail_called",
                   "deferred_first_bus_probe_entered", "deferred_first_bus_probe_returned",
                   "deferred_driver_probe_body", "deferred_culprit_driver", "late_initcalls_completed",
                   "wait_for_initramfs_return", "console_on_rootfs_entry", "init_executed")


def observer_for(case, ci_run="unfrozen"):
    return o.Observer(Namespace(serial="fixture", case=case, image=Path("fixture.img"),
                                context=Path("context.json"), output=Path("unused-output"),
                                ci_run=ci_run, baseline=Path("reference.json") if case == CASES[1] else None))


class NoDeviceTests(unittest.TestCase):
    def assert_predevice_rejected(self, observer, action, message=""):
        with patch.object(Path, "read_bytes") as read_image, patch.object(Path, "mkdir") as mkdir, \
                patch.object(Path, "write_text") as write, patch.object(observer, "getvar") as getvar, \
                patch.object(observer, "command") as command, patch.object(o.subprocess, "run") as run, \
                patch.object(o.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, message):
                getattr(observer, action)()
            for operation in (read_image, mkdir, write, getvar, command, run, spawn):
                operation.assert_not_called()
            self.assertEqual(observer.boots, 0)


class UnfrozenAfterKfreeTests(NoDeviceTests):
    def test_required_real_freeze_fails_instead_of_skipping(self):
        with patch.object(Path, "is_file", return_value=False), \
                patch.object(o, "load_afterfree_freeze") as load:
            with patch.dict(os.environ, {"AFTERFREE_FREEZE_REQUIRED": "true"}), \
                    self.assertRaisesRegex(AssertionError, "AFTERFREE_REQUIRED_IDENTITY_MISSING"):
                FrozenAfterKfreeTests.setUpClass()
            with patch.dict(os.environ, {"AFTERFREE_FREEZE_REQUIRED": "false"}), \
                    self.assertRaises(unittest.SkipTest):
                FrozenAfterKfreeTests.setUpClass()
            load.assert_not_called()

    def test_routes_require_the_new_checkpoint_and_origin(self):
        self.assertEqual(o.PAIRS[CASES[1]],
                         (CASES[0], "deferred_reason_kfree_returned", "deferred_first_bus_probe_entered"))
        for case in CASES:
            self.assertIn(case, o.ORIGIN_CASES)

    def test_missing_or_unreadable_freeze_blocks_run_launch_identity_and_pair(self):
        for failure in (FileNotFoundError("missing"), OSError("unreadable"), UnicodeError("invalid text")):
            with self.subTest(failure=type(failure).__name__), \
                    patch.object(Path, "read_text", side_effect=failure):
                for case in CASES:
                    for action in ("run", "launch"):
                        self.assert_predevice_rejected(observer_for(case), action, "AFTERFREE_IDENTITY_NOT_FROZEN")
                    with self.assertRaisesRegex(ValueError, "AFTERFREE_IDENTITY_NOT_FROZEN"):
                        o.validate_identity(case, *o.IMAGES["defer_selected8"])
                with self.assertRaisesRegex(ValueError, "AFTERFREE_IDENTITY_NOT_FROZEN"):
                    o.pair_verdict({}, {"case": CASES[1]})

    def test_bad_json_and_non_mapping_freezes_block_before_image_reads(self):
        for raw in ("", "{broken", "null", "[]", "true", "37", '"after_kfree"'):
            with self.subTest(raw=raw), patch.object(Path, "read_text", return_value=raw):
                for case in CASES:
                    for action in ("run", "launch"):
                        self.assert_predevice_rejected(observer_for(case), action, "AFTERFREE_")


class FrozenAfterKfreeTests(NoDeviceTests):
    @classmethod
    def setUpClass(cls):
        if not o.AFTERFREE_IDENTITY_PATH.is_file():
            if os.environ.get("AFTERFREE_FREEZE_REQUIRED") == "true":
                raise AssertionError("AFTERFREE_REQUIRED_IDENTITY_MISSING")
            raise unittest.SkipTest("Real CI after-kfree identities required")
        cls.identity = o.load_afterfree_freeze()
        agreement.validate_frozen(cls.identity)

    def record(self, case, total):
        return {"protocol": o.PROTOCOL, "case": case, "image_sha256": o.IMAGES[case][1],
                "context": dict(o.CONTEXT), "status": "AUTOMATIC_FASTBOOT_RETURN",
                "bootloader_origin": o.REST_ORIGIN, "final_slot": "b", "total_s": total,
                "ci_run": self.identity["private_run"], "b_retries": "6",
                "normal_boot_candidate": False, "slot_a_written": False, "partition_writes": 0,
                "host_boot_commands": 1, "experimental_boots": 1, "recovery_control_boots": 0,
                **{key: self.identity[key] for key in AUTHORITY_FIELDS}}

    def records(self):
        return self.record(CASES[0], 35.0), self.record(CASES[1], 28.0)

    def context(self):
        return {**o.CONTEXT, "bootloader_origin": o.REST_ORIGIN,
                "slot_a_unchanged": True, "readback_verified": True}

    def observer(self, case):
        return observer_for(case, self.identity["private_run"])

    def files(self, baseline, frozen=None, context=None):
        contents = {o.AFTERFREE_IDENTITY_PATH: json.dumps(self.identity if frozen is None else frozen),
                    Path("reference.json"): json.dumps(baseline),
                    Path("context.json"): json.dumps(self.context() if context is None else context)}
        return patch.object(Path, "read_text", autospec=True,
                            side_effect=lambda path, *args, **kwargs: contents[path])

    def invalid_records(self, record):
        for key in record:
            yield f"missing:{key}", {name: value for name, value in record.items() if name != key}
        changes = (("stage", "selected"), ("source_commit", "HEAD"), ("public_run", "0"),
                   ("private_commit", "HEAD"), ("private_run", "0"), ("ci_run", "0"),
                   ("ci_run", int(self.identity["private_run"])), ("protocol", "other"),
                   ("case", "defer_selected8"), ("image_sha256", o.IMAGES["defer_selected8"][1]),
                   ("bootloader_origin", "unknown"), ("context", {}), ("final_slot", "a"),
                   ("status", "NO_RETURN_WITHIN_120S"), ("status", "UNEXPECTED_ADB_RETURN"),
                   ("status", "STOP"), ("status", "MANUAL_FASTBOOT_RETURN"),
                   ("normal_boot_candidate", True), ("normal_boot_candidate", 0),
                   ("slot_a_written", True), ("slot_a_written", 0), ("partition_writes", 1),
                   ("partition_writes", False), ("host_boot_commands", 0), ("host_boot_commands", 2),
                   ("host_boot_commands", True), ("experimental_boots", 0), ("experimental_boots", 2),
                   ("experimental_boots", True), ("experimental_boots", 1.0),
                   ("recovery_control_boots", 1), ("recovery_control_boots", False),
                   ("b_retries", 6), ("b_retries", "5"), ("b_retries", "7"),
                   ("manual_timing_excluded", True), ("manual_timing_excluded", "false"),
                   ("manual_timing_excluded", 0), ("total_s", float("nan")),
                   ("total_s", float("inf")), ("total_s", float("-inf")),
                   ("total_s", True), ("total_s", False), ("total_s", 0),
                   ("total_s", -1), ("total_s", "28"), ("total_s", None))
        for key, value in changes:
            yield f"invalid:{key}:{value}", {**record, key: value}

    def test_real_frozen_registry_and_cross_family_rejection(self):
        self.assertEqual(o.afterfree_authority(self.identity),
                         {key: self.identity[key] for key in AUTHORITY_FIELDS})
        for case in CASES:
            identity = self.identity["members"][case[-1]]
            size, digest = o.IMAGES[case]
            self.assertEqual((size, digest), (identity["boot_size"], identity["boot_sha256"]))
            o.validate_identity(case, size, digest)
            for other, value in o.IMAGES.items():
                if other != case:
                    with self.subTest(case=case, other=other), self.assertRaises(ValueError):
                        o.validate_identity(case, *value)
            for bad_size, bad_hash in ((size - 1, digest), (size + 1, digest),
                                       (size, digest[:-1]), (size, digest.upper()), (size, "0" * 64)):
                with self.subTest(case=case, size=bad_size, sha=bad_hash), self.assertRaises(ValueError):
                    o.validate_identity(case, bad_size, bad_hash)

    def test_missing_partial_or_corrupt_registry_blocks_all_entry_points(self):
        records = self.records()
        size, digest = o.IMAGES[CASES[0]]
        registries = [{case: identity for case, identity in o.IMAGES.items() if case not in excluded}
                      for excluded in ((CASES[0],), (CASES[1],), CASES)]
        registries.extend({**o.IMAGES, CASES[0]: identity} for identity in
                          ((size - 1, digest), (size, digest[:-1]), o.IMAGES[CASES[1]]))
        for index, registry in enumerate(registries):
            with self.subTest(registry=index), patch.dict(o.IMAGES, registry, clear=True), self.files(records[0]):
                with self.assertRaisesRegex(ValueError, "AFTERFREE_IDENTITY_NOT_FROZEN"):
                    o.pair_verdict(*records)
                for case in CASES:
                    identity = self.identity["members"][case[-1]]
                    with self.assertRaisesRegex(ValueError, "AFTERFREE_IDENTITY_NOT_FROZEN"):
                        o.validate_identity(case, identity["boot_size"], identity["boot_sha256"])
                    for action in ("run", "launch"):
                        self.assert_predevice_rejected(self.observer(case), action, "AFTERFREE_IDENTITY_NOT_FROZEN")

    def test_old_deferred_experiments_cannot_be_registered_as_after_kfree(self):
        baseline, _ = self.records()
        old = {case: identity for case, identity in o.IMAGES.items()
               if case.startswith("defer_") and case not in CASES}
        for case, identity in old.items():
            frozen = copy.deepcopy(self.identity)
            frozen["members"]["8"]["boot_sha256"] = identity[1]
            with self.subTest(old=case), patch.dict(o.IMAGES, {CASES[0]: identity}), \
                    self.files(baseline, frozen=frozen):
                for member in CASES:
                    for action in ("run", "launch"):
                        self.assert_predevice_rejected(self.observer(member), action,
                                                       "AFTERFREE_FROZEN_EXPERIMENT_REUSED")

    def test_wrong_private_run_is_rejected_before_any_device_command(self):
        baseline, _ = self.records()
        for ci_run in (None, "", "0", int(self.identity["private_run"]), self.identity["private_run"] + "0"):
            with self.subTest(ci_run=ci_run), self.files(baseline):
                for case in CASES:
                    for action in ("run", "launch"):
                        observer = self.observer(case)
                        observer.args.ci_run = ci_run
                        self.assert_predevice_rejected(observer, action, "AFTERFREE_CI_RUN_MISMATCH")

    def test_second_member_requires_a_readable_mapping_reference(self):
        baseline, _ = self.records()
        with self.files(baseline):
            for action in ("run", "launch"):
                observer = self.observer(CASES[1])
                observer.args.baseline = None
                self.assert_predevice_rejected(observer, action, "MATCHED_8S_BASELINE_REQUIRED")
        for reference in (None, [], True, "selected"):
            with self.subTest(reference=reference), self.files(reference):
                for action in ("run", "launch"):
                    self.assert_predevice_rejected(self.observer(CASES[1]), action, "AFTERFREE_BASELINE_FORMAT")
        for failure in (FileNotFoundError("missing"), UnicodeError("invalid"), "{broken"):
            def read(path, *args, **kwargs):
                if path == o.AFTERFREE_IDENTITY_PATH:
                    return json.dumps(self.identity)
                if isinstance(failure, Exception):
                    raise failure
                return failure
            with self.subTest(failure=str(failure)), patch.object(Path, "read_text", autospec=True, side_effect=read):
                for action in ("run", "launch"):
                    self.assert_predevice_rejected(self.observer(CASES[1]), action, "AFTERFREE_BASELINE_UNREADABLE")

    def test_every_invalid_reference_is_rejected_before_launch_or_image_reads(self):
        baseline, _ = self.records()
        for label, reference in self.invalid_records(baseline):
            with self.subTest(mutation=label), self.files(reference):
                for action in ("run", "launch"):
                    self.assert_predevice_rejected(self.observer(CASES[1]), action)

    def test_pair_rejects_invalid_records_on_either_side_and_reversed_members(self):
        baseline, result = self.records()
        with self.assertRaises(ValueError):
            o.pair_verdict(result, baseline)
        for side, record in enumerate((baseline, result)):
            for label, invalid in self.invalid_records(record):
                records = [baseline, result]
                records[side] = invalid
                with self.subTest(side=side, mutation=label), self.assertRaises(ValueError):
                    o.pair_verdict(*records)
        o.pair_verdict({**baseline, "manual_timing_excluded": False}, result)

    def test_exact_error_boundaries_grade_only_completed_prefix_operations(self):
        baseline, result = self.records()
        for error, verdict, grade in ((0.0, "STRONG", "PROVEN"),
                                      (-1.0, "STRONG", "PROVEN"), (1.0, "STRONG", "PROVEN"),
                                      (-1.0001, "SUPPORTED", "SUPPORTED"), (1.0001, "SUPPORTED", "SUPPORTED"),
                                      (-2.0, "SUPPORTED", "SUPPORTED"), (2.0, "SUPPORTED", "SUPPORTED"),
                                      (-2.0001, "SHIFT_NOT_OBSERVED", "NOT_PROVEN"),
                                      (2.0001, "SHIFT_NOT_OBSERVED", "NOT_PROVEN")):
            with self.subTest(error=error):
                out = o.pair_verdict(baseline, {**result, "total_s": 28.0 + error})
                self.assertEqual(out["verdict"], verdict)
                self.assertEqual(out["expected_delta_s"], -7.0)
                for key in PROVEN_FIELDS:
                    self.assertEqual(out[key], grade)
                for key in UNPROVEN_FIELDS:
                    self.assertEqual(out[key], "NOT_PROVEN")
                self.assertEqual(out["usb"], "FROZEN")
                self.assertEqual(out.get("deferred_after_kfree_shift_not_observed"),
                                 "YES" if verdict == "SHIFT_NOT_OBSERVED" else None)

    def test_old_return_cluster_does_not_prove_reachability_or_nonexecution(self):
        for first, second in ((48.591122792, 48.346502500), (48.5, 48.5), (35.0, 35.0)):
            out = o.pair_verdict(self.record(CASES[0], first), self.record(CASES[1], second))
            self.assertEqual(out["verdict"], "SHIFT_NOT_OBSERVED")
            for key in PROVEN_FIELDS + UNPROVEN_FIELDS:
                self.assertEqual(out[key], "NOT_PROVEN")
            self.assertFalse(any("not_reached" in key or "never_executed" in key for key in out))

    def test_slot_a_and_second_launch_are_rejected_before_spawn(self):
        baseline, _ = self.records()
        for case in CASES:
            observer = self.observer(case)
            with self.files(baseline), patch.object(observer, "getvar", return_value="a"), \
                    patch.object(o.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "LAST_MOMENT_SLOT_NOT_B"):
                    observer.launch()
                spawn.assert_not_called()
                self.assertEqual(observer.boots, 0)
            observer.boots = 1
            with patch.object(Path, "read_text") as read, patch.object(observer, "getvar") as getvar, \
                    patch.object(o.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "SECOND_EXPERIMENTAL_BOOT_FORBIDDEN"):
                    observer.launch()
                read.assert_not_called()
                getvar.assert_not_called()
                spawn.assert_not_called()

    def test_origin_context_and_slot_a_protection_are_checked_before_device_commands(self):
        baseline, _ = self.records()
        context = self.context()
        for case in CASES:
            o.validate_context(context, case)
            for key in context:
                invalid = {**context, key: None}
                with self.subTest(case=case, key=key), self.assertRaises(ValueError):
                    o.validate_context(invalid, case)
                observer = self.observer(case)
                with self.files(baseline, context=invalid), patch.object(Path, "read_bytes", return_value=b"fixture"), \
                        patch.object(o, "validate_identity"), patch.object(Path, "mkdir") as mkdir, \
                        patch.object(observer, "getvar") as getvar, patch.object(o.subprocess, "Popen") as spawn:
                    with self.assertRaises(ValueError):
                        observer.run()
                    mkdir.assert_not_called()
                    getvar.assert_not_called()
                    spawn.assert_not_called()

    def run_fixture(self, case, returned, retries="7"):
        observer = self.observer(case)
        baseline, _ = self.records()
        values = {"product": "thyme", "unlocked": "yes", "current-slot": "b", "slot-count": "2",
                  "snapshot-update-status": "none", "battery-soc-ok": "yes", "slot-unbootable:b": "no",
                  "slot-successful:a": "yes", "slot-retry-count:b": retries, "max-download-size": "0x10000000"}
        written = {}

        def launch():
            observer.boots += 1
            return 100.0

        def write(path, content, *args, **kwargs):
            written[path] = json.loads(content)

        with self.files(baseline), patch.object(Path, "read_bytes", return_value=b"fixture"), \
                patch.object(o, "validate_identity"), patch.object(o.hashlib, "sha256") as sha256, \
                patch.object(Path, "mkdir"), \
                patch.object(Path, "write_text", autospec=True, side_effect=write), \
                patch.object(observer, "getvar", side_effect=values.__getitem__), \
                patch.object(observer, "launch", side_effect=launch) as launched, \
                patch.object(observer, "observe", return_value=returned), patch.object(observer, "log"), \
                patch.object(observer, "command") as command, patch.object(o.subprocess, "run") as run, \
                patch.object(o.subprocess, "Popen") as spawn:
            sha256.return_value.hexdigest.return_value = o.IMAGES[case][1]
            status = observer.run()
            command.assert_not_called()
            run.assert_not_called()
            spawn.assert_not_called()
        return status, written[observer.args.output / "result.json"], launched.call_count

    def automatic_return(self, case):
        return {"status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": "b", "b_retries": "6",
                "total_s": 35.0 if case == CASES[0] else 28.0}

    def test_results_record_the_exact_frozen_authority_and_one_boot(self):
        for case in CASES:
            status, result, launches = self.run_fixture(case, self.automatic_return(case))
            self.assertEqual((status, launches), (0, 1))
            for key in AUTHORITY_FIELDS:
                self.assertEqual(result[key], self.identity[key])
            self.assertEqual(result["ci_run"], self.identity["private_run"])
            o.validate_afterfree_record(result, self.identity)
            if case == CASES[1]:
                self.assertEqual(result["pair"]["deferred_reason_kfree_returned"], "PROVEN")

    def test_both_members_stop_immediately_on_bad_return_retries_or_manual_timing(self):
        for case in CASES:
            returned = self.automatic_return(case)
            invalid = [{key: value for key, value in returned.items() if key != "b_retries"},
                       *({**returned, "b_retries": value} for value in (6, "5", "7")),
                       {**returned, "manual_timing_excluded": True}]
            for value in invalid:
                with self.subTest(case=case, returned=value):
                    status, result, launches = self.run_fixture(case, value)
                    self.assertEqual((status, launches, result["status"]), (1, 1, "STOP"))
                    self.assertIn("AFTERFREE_", result["reason"])
                    self.assertNotIn("pair", result)

    def test_after_kfree_requires_seven_initial_retries(self):
        for case in CASES:
            for retries in ("5", "6", "8"):
                status, result, launches = self.run_fixture(case, self.automatic_return(case), retries)
                self.assertEqual((status, launches, result["status"]), (1, 0, "STOP"))
                self.assertEqual(result["reason"], "AFTERFREE_INITIAL_RETRIES_NOT_SEVEN")

    def private_receipts(self):
        pair = {"stage": "after_kfree", "source_commit": self.identity["source_commit"],
                "public_run": self.identity["public_run"], "expected_delta_s": -7,
                "changed_offsets": [9340053, 9340054], "cases": list(CASES),
                "payload_shas": {delay: member["payload_sha256"]
                                 for delay, member in self.identity["members"].items()},
                "manifest_shas": {
                    "8": "7a04a20d909b34aebe3b10881a5f731aa4d3183be617fb2ef071c19afd0e685c",
                    "1": "fd563a45a77e23431627fbc703296d426cd42b477c8d27e8c5761b2bac6b7efa"}}
        repository = {"id": 1362468178, "full_name": "ChuenSan/thyme-mainline-private-ci", "private": True}
        run = {"id": int(self.identity["private_run"]), "head_sha": self.identity["private_commit"],
               "status": "completed", "conclusion": "success",
               "path": ".github/workflows/thyme-slot-b-deferred-after-kfree.yml",
               "repository": dict(repository), "head_repository": dict(repository)}
        jobs = {"total_count": 2, "jobs": [
            {"id": job_id, "name": name, "run_id": run["id"], "head_sha": run["head_sha"],
             "status": "completed", "conclusion": "success"}
            for job_id, name in ((106272834146, "pack"), (106272978091, "independent-reverify"))]}
        packed = {"stage": "after_kfree", "source_commit": self.identity["source_commit"],
                  "public_run": self.identity["public_run"],
                  "members": {delay: {"case": f"defer_afterfree{delay}", **copy.deepcopy(member)}
                              for delay, member in self.identity["members"].items()},
                  "boot_changed_offsets": [9344149, 9344150],
                  "base_boot_sha256": "ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5",
                  "public_pair_sha256": "9924d52fa0a86cef9154bda96690ac87e76c1d7d75b1676fbc0a650f780e6cfa",
                  "gate": "DEFERRED_AFTER_KFREE_PRIVATE_PAIR_VERIFIED", "partition_writes": 0,
                  "normal_boot_candidate": False, "device_operation": False}
        return {"pair": pair, "run": run, "jobs": jobs, "packed": packed, "reverified": copy.deepcopy(packed)}

    def test_private_receipts_accept_canonical_json_and_independent_job_order(self):
        receipts = self.private_receipts()
        receipts["jobs"]["jobs"].reverse()
        receipts["reverified"] = dict(reversed(list(receipts["reverified"].items())))
        agreement.validate_private_receipts(self.identity, **receipts)

    def test_well_formed_wrong_frozen_private_authority_is_rejected(self):
        for key, value in (("private_commit", agreement.digest(b"other private commit")[:40]),
                           ("private_run", str(int(self.identity["private_run"]) + 1))):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_RUN"):
                agreement.validate_private_receipts({**self.identity, key: value}, **self.private_receipts())

    def test_matching_freeze_and_registry_boot_corruption_cannot_replace_private_receipts(self):
        for delay in ("8", "1"):
            frozen = copy.deepcopy(self.identity)
            member = frozen["members"][delay]
            member["boot_sha256"] = agreement.digest(f"corrupt boot {delay}".encode())
            with self.subTest(delay=delay), patch.dict(o.IMAGES, {
                    f"defer_afterfree{delay}": (member["boot_size"], member["boot_sha256"])}):
                agreement.validate_frozen(frozen)
                with self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_IDENTITY:members"):
                    agreement.validate_private_receipts(frozen, **self.private_receipts())

    def test_private_run_receipt_requires_exact_authority_workflow_and_repository(self):
        original = self.private_receipts()["run"]
        mutants = [{key: value for key, value in original.items() if key != missing} for missing in original]
        mutants.extend({**original, key: value} for key, value in (
            ("id", original["id"] + 1), ("id", str(original["id"])), ("id", float(original["id"])),
            ("id", True), ("head_sha", agreement.digest(b"wrong private source")[:40]),
            ("status", "in_progress"), ("conclusion", "failure"), ("conclusion", "skipped"),
            ("path", ".github/workflows/thyme-slot-b-deferred-selected.yml"),
            ("repository", None), ("head_repository", [])))
        for key in ("repository", "head_repository"):
            for field, value in (("id", 1362468179), ("id", 1362468178.0), ("private", False),
                                 ("private", 1), ("full_name", "ChuenSan/xiaomi10s")):
                mutant = copy.deepcopy(original)
                mutant[key][field] = value
                mutants.append(mutant)
            for missing in original[key]:
                mutant = copy.deepcopy(original)
                mutant[key] = {field: value for field, value in mutant[key].items() if field != missing}
                mutants.append(mutant)
        for index, run in enumerate(mutants):
            receipts = {**self.private_receipts(), "run": run}
            with self.subTest(mutant=index), self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_RUN"):
                agreement.validate_private_receipts(self.identity, **receipts)

    def test_private_jobs_require_distinct_successful_pack_and_reverify(self):
        original = self.private_receipts()["jobs"]
        mutants = [None, [], {"jobs": original["jobs"]}, {"total_count": 2},
                   {**original, "total_count": 2.0}, {**original, "total_count": True},
                   {"total_count": 1, "jobs": original["jobs"][:1]},
                   {"total_count": 2, "jobs": original["jobs"][:1]},
                   {"total_count": 2, "jobs": [original["jobs"][0]] * 2},
                   {"total_count": 2, "jobs": [original["jobs"][0], None]}]
        for index in (0, 1):
            job = original["jobs"][index]
            changes = (("id", original["jobs"][1 - index]["id"]), ("id", True), ("id", 0),
                       ("id", float(job["id"])), ("run_id", job["run_id"] + 1),
                       ("run_id", True), ("run_id", float(job["run_id"])),
                       ("head_sha", agreement.digest(b"wrong job source")[:40]),
                       ("name", "other"), ("status", "queued"), ("status", "in_progress"),
                       ("conclusion", "failure"), ("conclusion", "skipped"), ("conclusion", "cancelled"))
            for key, value in changes:
                mutant = copy.deepcopy(original)
                mutant["jobs"][index][key] = value
                mutants.append(mutant)
            for missing in job:
                mutant = copy.deepcopy(original)
                mutant["jobs"][index] = {key: value for key, value in job.items() if key != missing}
                mutants.append(mutant)
        for index, jobs in enumerate(mutants):
            with self.subTest(mutant=index), self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_JOB"):
                agreement.validate_private_receipts(self.identity, **{**self.private_receipts(), "jobs": jobs})

    def test_matching_private_report_corruption_is_rejected(self):
        original = self.private_receipts()["packed"]
        mutants = [{key: value for key, value in original.items() if key != missing} for missing in original]
        mutants.extend({**original, key: value} for key, value in (
            ("stage", "selected"), ("source_commit", agreement.digest(b"wrong public source")[:40]),
            ("public_run", str(int(self.identity["public_run"]) + 1)),
            ("public_run", int(self.identity["public_run"])), ("boot_changed_offsets", [9340053, 9340054]),
            ("boot_changed_offsets", [9344149.0, 9344150.0]),
            ("base_boot_sha256", agreement.digest(b"wrong base")),
            ("public_pair_sha256", agreement.digest(b"wrong pair")), ("gate", "PASS"),
            ("partition_writes", 1), ("partition_writes", False), ("normal_boot_candidate", True),
            ("normal_boot_candidate", 0), ("device_operation", True), ("device_operation", 0),
            ("members", {}), ("unexpected", True)))
        for delay in ("8", "1"):
            member = original["members"][delay]
            for key, value in (("case", CASES[1 if delay == "8" else 0]),
                               ("boot_sha256", agreement.digest(b"wrong boot")),
                               ("payload_sha256", agreement.digest(b"wrong payload")),
                               ("boot_size", member["boot_size"] + 1),
                               ("boot_size", float(member["boot_size"])), ("boot_size", True),
                               ("unexpected", 0)):
                mutant = copy.deepcopy(original)
                mutant["members"][delay][key] = value
                mutants.append(mutant)
            mutant = copy.deepcopy(original)
            mutant["members"] = {key: value for key, value in mutant["members"].items() if key != delay}
            mutants.append(mutant)
            for missing in member:
                mutant = copy.deepcopy(original)
                mutant["members"][delay] = {key: value for key, value in member.items() if key != missing}
                mutants.append(mutant)
        for index, packed in enumerate(mutants):
            receipts = {**self.private_receipts(), "packed": packed, "reverified": copy.deepcopy(packed)}
            with self.subTest(mutant=index), self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_IDENTITY"):
                agreement.validate_private_receipts(self.identity, **receipts)

    def test_private_reports_reject_member_mismatch_and_boolean_integer_aliases(self):
        for delay in ("8", "1"):
            receipts = self.private_receipts()
            receipts["reverified"]["members"][delay]["boot_sha256"] = agreement.digest(b"different boot")
            with self.subTest(delay=delay), \
                    self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_REVERIFY_IDENTITY_MISMATCH"):
                agreement.validate_private_receipts(self.identity, **receipts)
        for key, value in (("partition_writes", False), ("normal_boot_candidate", 0), ("device_operation", 0)):
            receipts = self.private_receipts()
            receipts["reverified"][key] = value
            with self.subTest(key=key), \
                    self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_REVERIFY_IDENTITY_MISMATCH"):
                agreement.validate_private_receipts(self.identity, **receipts)

    def test_private_reports_bind_the_canonical_public_pair_digest(self):
        receipts = self.private_receipts()
        receipts["pair"]["manifest_shas"]["8"] = agreement.digest(b"different valid manifest identity")
        with self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_IDENTITY:public_pair_sha256"):
            agreement.validate_private_receipts(self.identity, **receipts)

    def test_public_cli_cannot_claim_private_provenance(self):
        pair = self.private_receipts()["pair"]
        with patch("sys.argv", ["agreement", "--root", "pair"]), \
                patch.dict(os.environ, {"GITHUB_REPOSITORY": "ChuenSan/xiaomi10s"}), \
                patch.object(o, "load_afterfree_freeze", return_value=self.identity), \
                patch.object(agreement, "verify", return_value=pair) as public, \
                patch.object(agreement, "validate_private_receipts") as private, patch("builtins.print") as printed:
            agreement.main()
            public.assert_called_once_with(Path("pair"), self.identity)
            private.assert_not_called()
            printed.assert_called_once_with("DEFERRED_AFTER_KFREE_OBSERVER_IDENTITY_AGREEMENT=PASS")

    def test_private_cli_requires_the_private_execution_repository(self):
        for repository in ("", "ChuenSan/xiaomi10s", "other/thyme-mainline-private-ci"):
            with self.subTest(repository=repository), \
                    patch("sys.argv", ["agreement", "--root", "pair", "--private-receipts", "receipts"]), \
                    patch.dict(os.environ, {"GITHUB_REPOSITORY": repository}), \
                    patch.object(o, "load_afterfree_freeze", return_value=self.identity), \
                    patch.object(agreement, "verify", return_value=self.private_receipts()["pair"]) as public, \
                    patch.object(Path, "read_text") as read, patch("builtins.print") as printed:
                with self.assertRaisesRegex(ValueError, "AFTERFREE_PRIVATE_EXECUTION_REPOSITORY"):
                    agreement.main()
                public.assert_called_once_with(Path("pair"), self.identity)
                read.assert_not_called()
                printed.assert_not_called()

    def test_private_cli_binds_all_receipts_after_public_pair_verification(self):
        receipts = self.private_receipts()
        paths = {Path("receipts") / name: json.dumps(receipts[key]) for name, key in (
            ("private-run.json", "run"), ("private-jobs.json", "jobs"),
            ("packed/identity.json", "packed"), ("reverified/identity.json", "reverified"))}
        with patch("sys.argv", ["agreement", "--root", "pair", "--private-receipts", "receipts"]), \
                patch.dict(os.environ, {"GITHUB_REPOSITORY": "ChuenSan/thyme-mainline-private-ci"}), \
                patch.object(o, "load_afterfree_freeze", return_value=self.identity), \
                patch.object(agreement, "verify", return_value=receipts["pair"]) as public, \
                patch.object(Path, "read_text", autospec=True, side_effect=lambda path: paths[path]) as read, \
                patch("builtins.print") as printed:
            agreement.main()
            public.assert_called_once_with(Path("pair"), self.identity)
            self.assertEqual(read.call_count, 4)
            self.assertEqual(printed.call_args_list, [
                call("DEFERRED_AFTER_KFREE_OBSERVER_IDENTITY_AGREEMENT=PASS"),
                call("DEFERRED_AFTER_KFREE_PRIVATE_OBSERVER_PROVENANCE=PASS")])
            public.side_effect = ValueError("PUBLIC_PAIR_REJECTED")
            read.reset_mock()
            printed.reset_mock()
            with self.assertRaisesRegex(ValueError, "PUBLIC_PAIR_REJECTED"):
                agreement.main()
            read.assert_not_called()
            printed.assert_not_called()

    def test_freeze_geometry_authority_and_member_mutants_are_rejected(self):
        changes = (("stage", "selected"), ("offset", 0x8E8468), ("window", 60),
                   ("parent_offset", 0x8E7564), ("parent_size", 492), ("boot_size", 37380095),
                   ("source_commit", "HEAD"), ("private_commit", "0" * 40),
                   ("public_run", 1), ("public_run", "0"), ("private_run", "0"),
                   ("private_run", int(self.identity["private_run"])), ("members", {}))
        for key, value in changes:
            for validator in (o.validate_afterfree_freeze, agreement.validate_frozen):
                with self.subTest(key=key, validator=validator.__name__), self.assertRaises(ValueError):
                    validator({**self.identity, key: value})
        for delay in ("8", "1"):
            for key, value in (("boot_size", 37380096.0), ("boot_sha256", "0" * 64),
                               ("payload_sha256", "not-a-sha")):
                frozen = copy.deepcopy(self.identity)
                frozen["members"][delay][key] = value
                with self.subTest(delay=delay, key=key), self.assertRaises(ValueError):
                    agreement.validate_frozen(frozen)
        frozen = copy.deepcopy(self.identity)
        frozen["members"]["1"]["payload_sha256"] = frozen["members"]["8"]["payload_sha256"]
        with self.assertRaisesRegex(ValueError, "AFTERFREE_FREEZE_HASH_COLLISION"):
            agreement.validate_frozen(frozen)

    def test_independent_manifest_scope_rejects_matching_producer_mutants(self):
        changes = (("stage", "selected"), ("offset", 0x8E8468), ("window_end", 0x8E84A0),
                   ("positive_only", []), ("positive_not_proven", []), ("predecessor_offset", 0x8E8484),
                   ("original_reason_loads", []), ("get_device_return_value_checked", True),
                   ("reason_field_cleared_at_checkpoint", True), ("mutex_held_at_checkpoint", False),
                   ("added_pointer_or_name_dereferences", 1), ("maximum_delay_seconds", 9),
                   ("terminal_fallthrough", True), ("empty_list_reaches_probe", True),
                   ("retained_backedge_reachable", True), ("callback_first_activation_only", True),
                   ("parent_agreement", "UNCHECKED"), ("runtime_rewrites", {}),
                   ("whole_code_scan", "BUNDLE_ONLY"), ("relocation_scan", "NONE"),
                   ("exception_fixup_destinations", "NONE"), ("normal_boot_candidate", True))
        for key, value in changes:
            scope = {**copy.deepcopy(agreement.probe.SCOPE), key: value}
            with self.subTest(key=key), patch.object(agreement.probe, "SCOPE", scope), \
                    self.assertRaisesRegex(ValueError, f"AFTERFREE_MANIFEST_SCOPE:{key}"):
                agreement.validate_manifest(scope, self.identity, "8")
        for key in ("bundle", "original_calls", "original_parent_sha256"):
            scope = {**copy.deepcopy(agreement.probe.SCOPE), key: None}
            with self.subTest(key=key), \
                    self.assertRaisesRegex(ValueError, f"AFTERFREE_MANIFEST_SOURCE_SCOPE:{key}"):
                agreement.validate_manifest(scope, self.identity, "8")


if __name__ == "__main__":
    unittest.main()
