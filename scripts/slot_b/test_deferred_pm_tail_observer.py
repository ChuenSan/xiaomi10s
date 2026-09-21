import copy
import json
import math
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import deferred_pm_tail_identity_agreement as agreement
import deferred_pm_tail_runtime as runtime
import observe as o

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "artifacts/slot-b-deferred-pm-tail-20260921"
PAIR = EVIDENCE / "public-audit-35620158321/pm-tail/pair"
PRIVATE_IDENTITY = EVIDENCE / "private-reverify-35621265916-identity.json"


class PMTailObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = runtime.load_freeze(o.IMAGES)
        agreement.validate_frozen(cls.frozen)

    def record(self, case, total):
        return {**runtime.authority(self.frozen), "protocol": o.PROTOCOL, "case": case,
                "image_sha256": o.IMAGES[case][1], "context": dict(o.CONTEXT),
                "status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": "b", "total_s": total,
                "bootloader_origin": o.REST_ORIGIN, "ci_run": self.frozen["private_run"], "b_retries": "6",
                "normal_boot_candidate": False, "slot_a_written": False, "partition_writes": 0,
                "host_boot_commands": 1, "experimental_boots": 1, "recovery_control_boots": 0}

    def records(self):
        return self.record(runtime.CASES[0], 35.0), self.record(runtime.CASES[1], 28.0)

    def context(self):
        return {**o.CONTEXT, "bootloader_origin": o.REST_ORIGIN,
                "slot_a_unchanged": True, "readback_verified": True}

    def observer(self, case):
        return o.Observer(Namespace(case=case, serial="fixture", image=Path("fixture.img"),
                                    context=Path("context.json"), output=Path("unused-output"),
                                    ci_run=self.frozen["private_run"],
                                    baseline=Path("baseline.json") if case == runtime.CASES[1] else None))

    def files(self, baseline, frozen=None, context=None):
        data = {runtime.IDENTITY_PATH: self.frozen if frozen is None else frozen,
                Path("baseline.json"): baseline, Path("context.json"): self.context() if context is None else context}
        return patch.object(Path, "read_text", autospec=True,
                            side_effect=lambda path, *args, **kwargs: json.dumps(data[path]))

    def assert_predevice_rejected(self, observer, action, message=""):
        with patch.object(Path, "read_bytes") as image, patch.object(Path, "mkdir") as mkdir, \
                patch.object(Path, "write_text") as write, patch.object(observer, "getvar") as getvar, \
                patch.object(observer, "command") as command, patch.object(o.subprocess, "run") as run, \
                patch.object(o.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, message):
                getattr(observer, action)()
            for operation in (image, mkdir, write, getvar, command, run, spawn):
                operation.assert_not_called()
            self.assertEqual(observer.boots, 0)

    def test_exact_registry_and_cross_family_rejection(self):
        for case in runtime.CASES:
            o.validate_identity(case, *o.IMAGES[case])
            self.assertIn(case, o.ORIGIN_CASES)
            for other, identity in o.IMAGES.items():
                if other != case:
                    with self.subTest(case=case, other=other), self.assertRaises(ValueError):
                        o.validate_identity(case, *identity)
        self.assertEqual(o.PAIRS[runtime.CASES[1]],
                         (runtime.CASES[0], "deferred_pm_tail_entry", "deferred_pm_tail_return"))

    def test_unreadable_or_invalid_freeze_blocks_all_entry_points(self):
        for content in ("", "null", "[]", "true", "{broken", "37"):
            with self.subTest(content=content), patch.object(Path, "read_text", return_value=content):
                for case in runtime.CASES:
                    for action in ("run", "launch"):
                        self.assert_predevice_rejected(self.observer(case), action, "PMTAIL_")
                    with self.assertRaises(ValueError):
                        o.validate_identity(case, *o.IMAGES[case])
                with self.assertRaises(ValueError):
                    o.pair_verdict({}, {"case": runtime.CASES[1]})
        with patch.object(Path, "read_text", side_effect=FileNotFoundError("missing")):
            self.assert_predevice_rejected(self.observer(runtime.CASES[0]), "run", "IDENTITY_NOT_FROZEN")

    def test_freeze_fields_member_types_and_registry_cannot_drift(self):
        for key in self.frozen:
            for mutant in ({name: value for name, value in self.frozen.items() if name != key},
                           {**self.frozen, key: None}):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    runtime.validate_freeze(mutant, o.IMAGES)
        for delay in ("8", "1"):
            for key, value in (("boot_size", float(self.frozen["boot_size"])), ("boot_sha256", "0" * 64),
                               ("payload_sha256", "0" * 64)):
                mutant = copy.deepcopy(self.frozen)
                mutant["members"][delay][key] = value
                with self.subTest(delay=delay, key=key), self.assertRaises(ValueError):
                    runtime.validate_freeze(mutant, o.IMAGES)
        for case in runtime.CASES:
            images = {name: value for name, value in o.IMAGES.items() if name != case}
            with patch.dict(o.IMAGES, images, clear=True), self.assertRaisesRegex(ValueError, "IDENTITY_NOT_FROZEN"):
                runtime.load_freeze(o.IMAGES)
        mutant = copy.deepcopy(self.frozen)
        mutant["members"]["8"]["boot_sha256"] = o.IMAGES["defer_afterfree8"][1]
        with patch.dict(o.IMAGES, {runtime.CASES[0]: o.IMAGES["defer_afterfree8"]}), \
                self.assertRaisesRegex(ValueError, "FROZEN_EXPERIMENT_REUSED"):
            runtime.validate_freeze(mutant, o.IMAGES)

    def invalid_records(self, record):
        for key in record:
            yield {name: value for name, value in record.items() if name != key}
            yield {**record, key: None}
        for key, value in (("status", "NO_RETURN_WITHIN_120S"), ("status", "MANUAL_FASTBOOT_RETURN"),
                           ("status", "UNEXPECTED_ADB_RETURN"), ("final_slot", "a"),
                           ("experimental_boots", True), ("experimental_boots", 1.0),
                           ("host_boot_commands", 2), ("partition_writes", False), ("slot_a_written", 0),
                           ("recovery_control_boots", True), ("b_retries", "7"), ("b_retries", 6),
                           ("manual_timing_excluded", True), ("manual_timing_excluded", 0),
                           ("total_s", math.nan), ("total_s", math.inf), ("total_s", True), ("total_s", 0)):
            yield {**record, key: value}

    def test_invalid_reference_blocks_before_image_or_device_access(self):
        baseline, _ = self.records()
        for index, invalid in enumerate(self.invalid_records(baseline)):
            with self.subTest(index=index), self.files(invalid):
                for action in ("run", "launch"):
                    self.assert_predevice_rejected(self.observer(runtime.CASES[1]), action)
        for value in (None, [], True, "other"):
            with self.subTest(value=value), self.files(value):
                self.assert_predevice_rejected(self.observer(runtime.CASES[1]), "run", "BASELINE_FORMAT")
        observer = self.observer(runtime.CASES[1])
        observer.args.baseline = None
        self.assert_predevice_rejected(observer, "run", "MATCHED_8S_BASELINE_REQUIRED")

    def test_pair_rejects_invalid_records_on_either_side(self):
        records = self.records()
        for side, record in enumerate(records):
            for index, invalid in enumerate(self.invalid_records(record)):
                candidates = list(records)
                candidates[side] = invalid
                with self.subTest(side=side, index=index), self.assertRaises(ValueError):
                    o.pair_verdict(*candidates)
        with self.assertRaises(ValueError):
            o.pair_verdict(*reversed(records))

    def test_wrong_private_run_and_first_member_baseline_are_rejected(self):
        for case in runtime.CASES:
            for wrong in (None, "0", int(self.frozen["private_run"])):
                observer = self.observer(case)
                observer.args.ci_run = wrong
                self.assert_predevice_rejected(observer, "run", "CI_RUN_MISMATCH")
        observer = self.observer(runtime.CASES[0])
        observer.args.baseline = Path("old.json")
        self.assert_predevice_rejected(observer, "run", "FIRST_MEMBER_BASELINE_FORBIDDEN")

    def test_slot_a_and_second_boot_never_spawn(self):
        baseline, _ = self.records()
        for case in runtime.CASES:
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

    def test_bad_origin_or_unverified_partitions_stop_before_device_commands(self):
        baseline, _ = self.records()
        for case in runtime.CASES:
            for key in self.context():
                observer = self.observer(case)
                context = {**self.context(), key: None}
                with self.subTest(case=case, key=key), self.files(baseline, context=context), \
                        patch.object(Path, "read_bytes", return_value=b"fixture"), patch.object(o, "validate_identity"), \
                        patch.object(Path, "mkdir") as mkdir, patch.object(observer, "getvar") as getvar, \
                        patch.object(o.subprocess, "Popen") as spawn:
                    with self.assertRaises(ValueError):
                        observer.run()
                    mkdir.assert_not_called()
                    getvar.assert_not_called()
                    spawn.assert_not_called()

    def test_grade_boundaries_only_prove_store_unlock_return_and_pm_entry(self):
        baseline, result = self.records()
        for error, verdict, grade in ((0, "STRONG", "PROVEN"), (-1, "STRONG", "PROVEN"),
                                      (1, "STRONG", "PROVEN"), (-1.001, "SUPPORTED", "SUPPORTED"),
                                      (2, "SUPPORTED", "SUPPORTED"), (-2, "SUPPORTED", "SUPPORTED"),
                                      (-2.001, "SHIFT_NOT_OBSERVED", "NOT_PROVEN"),
                                      (2.001, "SHIFT_NOT_OBSERVED", "NOT_PROVEN")):
            with self.subTest(error=error):
                out = o.pair_verdict(baseline, {**result, "total_s": 28.0 + error})
                self.assertEqual(out["verdict"], verdict)
                for key in ("deferred_pm_tail_entry", "original_reason_clear_store_executed", "worker_mutex_unlock_returned"):
                    self.assertEqual(out[key], grade)
                for key in ("persistent_reason_field_state", "srcu_or_pm_lock_acquired", "deferred_pm_tail_return",
                            "pm_list_movement", "deferred_first_bus_probe_entered", "deferred_first_bus_probe_returned",
                            "deferred_device_identity", "deferred_culprit_driver", "late_initcalls_completed", "init_executed"):
                    self.assertEqual(out[key], "NOT_PROVEN")
                self.assertEqual(out["usb"], "FROZEN")
        out = o.pair_verdict(self.record(runtime.CASES[0], 48.5), self.record(runtime.CASES[1], 48.5))
        self.assertEqual(out["verdict"], "SHIFT_NOT_OBSERVED")
        self.assertEqual(out["deferred_pm_tail_entry"], "NOT_PROVEN")
        self.assertFalse(any("never_executed" in key or "not_reached" in key for key in out))

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

        def write(path, text, *args, **kwargs):
            written[path] = json.loads(text)

        with self.files(baseline), patch.object(Path, "read_bytes", return_value=b"fixture"), \
                patch.object(o, "validate_identity"), patch.object(o.hashlib, "sha256") as sha, \
                patch.object(Path, "mkdir"), patch.object(Path, "write_text", autospec=True, side_effect=write), \
                patch.object(observer, "getvar", side_effect=values.__getitem__), \
                patch.object(observer, "launch", side_effect=launch) as launched, \
                patch.object(observer, "observe", return_value=returned), patch.object(observer, "log"), \
                patch.object(observer, "command") as command, patch.object(o.subprocess, "run") as run, \
                patch.object(o.subprocess, "Popen") as spawn:
            sha.return_value.hexdigest.return_value = o.IMAGES[case][1]
            status = observer.run()
            command.assert_not_called()
            run.assert_not_called()
            spawn.assert_not_called()
        return status, written[observer.args.output / "result.json"], launched.call_count

    def returned(self, case):
        return {"status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": "b", "b_retries": "6",
                "total_s": 35.0 if case == runtime.CASES[0] else 28.0}

    def test_success_records_full_authority_and_one_ram_boot(self):
        for case in runtime.CASES:
            status, result, launches = self.run_fixture(case, self.returned(case))
            self.assertEqual((status, launches), (0, 1))
            runtime.validate_record(result, self.frozen)
            for key in runtime.AUTHORITY_FIELDS:
                self.assertEqual(result[key], self.frozen[key])
            if case == runtime.CASES[1]:
                self.assertEqual(result["pair"]["deferred_pm_tail_entry"], "PROVEN")

    def test_initial_retries_and_abnormal_returns_stop_without_retry(self):
        for case in runtime.CASES:
            for retries in ("5", "6", "8"):
                status, result, launches = self.run_fixture(case, self.returned(case), retries)
                self.assertEqual((status, launches, result["status"]), (1, 0, "STOP"))
                self.assertEqual(result["reason"], "PMTAIL_INITIAL_RETRIES_NOT_SEVEN")
            for returned in ({**self.returned(case), "b_retries": "7"},
                             {**self.returned(case), "manual_timing_excluded": True}):
                status, result, launches = self.run_fixture(case, returned)
                self.assertEqual((status, launches, result["status"]), (1, 1, "STOP"))
                self.assertNotIn("pair", result)
            for state in ("NO_RETURN_WITHIN_120S", "UNEXPECTED_ADB_RETURN"):
                status, result, launches = self.run_fixture(case, {"status": state})
                self.assertEqual((status, launches, result["status"]), (1, 1, state))
                self.assertNotIn("pair", result)

    def receipts(self):
        repository = {"id": agreement.PRIVATE_REPOSITORY_ID, "full_name": agreement.PRIVATE_REPOSITORY,
                      "private": True}
        run = {"id": int(self.frozen["private_run"]), "head_sha": self.frozen["private_commit"],
               "status": "completed", "conclusion": "success", "path": agreement.PRIVATE_WORKFLOW,
               "repository": dict(repository), "head_repository": dict(repository)}
        jobs = {"total_count": 2, "jobs": [
            {"id": job_id, "name": name, "run_id": run["id"], "head_sha": run["head_sha"],
             "status": "completed", "conclusion": "success"}
            for job_id, name in ((106404616533, "pack"), (106404913121, "independent-reverify"))]}
        packed = json.loads(PRIVATE_IDENTITY.read_text())
        return {"pair": json.loads((PAIR / "pair.json").read_text()),
                "linked": json.loads((PAIR / "linked-jump-table.json").read_text()),
                "run": run, "jobs": jobs, "packed": packed, "reverified": copy.deepcopy(packed)}

    def test_real_actions_pair_and_private_report_agree(self):
        receipts = self.receipts()
        agreement.validate_private_receipts(self.frozen, **receipts)
        receipts["jobs"]["jobs"].reverse()
        agreement.validate_private_receipts(self.frozen, **receipts)

    def test_private_receipts_require_exact_run_repository_and_two_independent_jobs(self):
        original = self.receipts()
        for key in original["run"]:
            receipts = copy.deepcopy(original)
            receipts["run"].pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                agreement.validate_private_receipts(self.frozen, **receipts)
        for key, value in (("id", str(original["run"]["id"])), ("head_sha", "other"),
                           ("status", "in_progress"), ("conclusion", "failure"), ("path", "other.yml")):
            receipts = copy.deepcopy(original)
            receipts["run"][key] = value
            with self.subTest(run_field=key), self.assertRaises(ValueError):
                agreement.validate_private_receipts(self.frozen, **receipts)
        for key in ("repository", "head_repository"):
            receipts = copy.deepcopy(original)
            receipts["run"][key]["private"] = False
            with self.assertRaises(ValueError):
                agreement.validate_private_receipts(self.frozen, **receipts)
        for jobs in ({"total_count": True, "jobs": original["jobs"]["jobs"]},
                     {"total_count": 1, "jobs": original["jobs"]["jobs"][:1]},
                     {"total_count": 2, "jobs": [original["jobs"]["jobs"][0]] * 2}):
            with self.assertRaises(ValueError):
                agreement.validate_private_receipts(self.frozen, **{**original, "jobs": jobs})
        for index in (0, 1):
            for key, value in (("id", True), ("run_id", 0), ("head_sha", "wrong"),
                               ("status", "queued"), ("conclusion", "skipped"), ("name", "other")):
                receipts = copy.deepcopy(original)
                receipts["jobs"]["jobs"][index][key] = value
                with self.subTest(job=index, field=key), self.assertRaises(ValueError):
                    agreement.validate_private_receipts(self.frozen, **receipts)

    def test_matching_private_report_corruption_and_report_omission_are_rejected(self):
        original = self.receipts()
        for key in original["packed"]:
            for mutant in ({name: value for name, value in original["packed"].items() if name != key},
                           {**original["packed"], key: None}):
                with self.subTest(field=key), self.assertRaises(ValueError):
                    agreement.validate_private_receipts(self.frozen, **{
                        **original, "packed": mutant, "reverified": copy.deepcopy(mutant)})
        for key in ("sha256", "source_sha256", "protected", "public_run", "source_commit"):
            receipts = copy.deepcopy(original)
            receipts["linked"][key] = None
            with self.subTest(linked_field=key), self.assertRaises(ValueError):
                agreement.validate_private_receipts(self.frozen, **receipts)
        receipts = copy.deepcopy(original)
        receipts["reverified"]["members"]["8"]["boot_sha256"] = agreement.digest(b"wrong boot")
        with self.assertRaisesRegex(ValueError, "REVERIFY_IDENTITY_MISMATCH"):
            agreement.validate_private_receipts(self.frozen, **receipts)

    def test_correlated_registry_freeze_corruption_cannot_replace_private_identity(self):
        frozen = copy.deepcopy(self.frozen)
        frozen["members"]["8"]["boot_sha256"] = agreement.digest(b"different boot")
        with patch.dict(o.IMAGES, {runtime.CASES[0]: (frozen["boot_size"], frozen["members"]["8"]["boot_sha256"])}), \
                self.assertRaisesRegex(ValueError, "PRIVATE_IDENTITY:members"):
            agreement.validate_private_receipts(frozen, **self.receipts())


if __name__ == "__main__":
    unittest.main()
