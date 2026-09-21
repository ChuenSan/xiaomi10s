"""Actions-only rejection fixtures; shared modules and frozen hashes are never patched."""
import copy
import io
import os
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("GITHUB_ACTIONS_ONLY")

import deferred_after_kfree_probe as d

SOURCE_COMMIT = "a" * 40
PUBLIC_RUN = "12345"
FROZEN = Path(os.environ.get("AFTER_KFREE_FROZEN", "frozen/thyme-r3-p1b-fix8-kernel-payload.bin"))
if os.environ.get("AFTER_KFREE_FIXTURE_REQUIRED") == "true" and not FROZEN.is_file():
    raise RuntimeError("IMMUTABLE_FIX8_TEST_INPUT_REQUIRED")


def changed_byte(data, offset):
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]


def manifest(payload, delay):
    return {**copy.deepcopy(d.SCOPE), "source_commit": SOURCE_COMMIT, "public_run": PUBLIC_RUN,
            "source_files_sha256": {name: d.cp.digest(name.encode()) for name in d.SOURCE_FILES},
            "case": d.CASES[delay], "delay_seconds": delay, "payload_sha256": d.cp.digest(payload),
            "checkpoint_sha256": d.cp.digest(payload[d.OFFSET:d.END])}


def section_map():
    names = (".head.text", ".text", ".rodata.text", ".init.text", ".exit.text")
    rows = [{"name": name, "vma": d.TEXT + lo, "size": hi - lo, "alloc": True, "code": True}
            for name, (lo, hi) in zip(names, d.CODE_RANGES)]
    for name, offset in (("__ex_table", 0x1B0F690), (".altinstructions", 0x1BC6490),
                         (".rela.dyn", 0x1D2C440), (".relr.dyn", 0x1D2C4D0)):
        rows.append({"name": name, "vma": d.TEXT + offset, "size": 12, "alloc": True, "code": False})
    return rows


class BoundaryTests(unittest.TestCase):
    def test_geometry_and_cli_cannot_select_frozen_stages(self):
        self.assertEqual((d.PARENT, d.PARENT_SIZE, d.OFFSET, d.WINDOW, d.END),
                         (0x8E8424, 196, 0x8E848C, 56, 0x8E84C4))
        self.assertEqual(d.END, d.BACKEDGE)
        self.assertEqual(d.OFFSET, d.KFREE_CALL + 4)
        argv = ["--frozen", "frozen", "--out", "out", "--stage", "after_kfree"]
        self.assertEqual(d.parser().parse_args(argv).stage, "after_kfree")
        for stage in ("selected", "worker", "prequeue", "postflush", "defer_selected8",
                      "defer_selected1", "defer_worker8", "defer_worker1", "defer_prequeue8",
                      "defer_prequeue1", "defer_postflush8", "defer_postflush1", "afterfree", None):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "UNAUTHORIZED"):
                d.gate_stage(stage)
            if stage is not None:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    d.parser().parse_args(argv[:-1] + [stage])
        self.assertEqual(d.selected.OFFSET, 0x8E8468)
        self.assertEqual(d.selected.SCOPE["stage"], "selected")
        self.assertEqual(set(d.selected.deferred.STAGES), {"prequeue", "postflush", "worker"})

    def test_new_window_and_every_original_worker_word_are_frozen(self):
        original = struct.pack("<14I", *d.WINDOW_WORDS)
        d.gate_window("after_kfree", d.OFFSET, original)
        d.gate_worker(d.ORIGINAL)
        for offset, blob in ((d.OFFSET - 4, original), (d.OFFSET + 4, original),
                             (d.OFFSET, original[:-4]), (d.OFFSET, original + bytes(4))):
            with self.subTest(offset=offset, size=len(blob)), self.assertRaisesRegex(ValueError, "GEOMETRY"):
                d.gate_window("after_kfree", offset, blob)
        for index in range(14):
            with self.subTest(window_word=index), self.assertRaisesRegex(ValueError, "ORIGINAL_WINDOW"):
                d.gate_window("after_kfree", d.OFFSET, changed_byte(original, index * 4))
        for index in range(49):
            with self.subTest(worker_word=index), self.assertRaises(ValueError):
                d.gate_worker(changed_byte(d.ORIGINAL, index * 4))
        with self.assertRaises(ValueError):
            d.gate_worker(d.ORIGINAL[:-4])

    def test_full_parent_agreement_includes_both_sides_of_window(self):
        d.gate_parent_agreement(d.ORIGINAL, d.ORIGINAL, d.ORIGINAL)
        for position in (0, d.KFREE_CALL - d.PARENT, d.END - d.PARENT, d.PARENT_SIZE - 4):
            for copy_index in range(3):
                items = [d.ORIGINAL] * 3
                items[copy_index] = changed_byte(items[copy_index], position)
                with self.subTest(position=position, copy=copy_index), self.assertRaisesRegex(ValueError, "DISAGREEMENT"):
                    d.gate_parent_agreement(*items)

    def test_original_calls_require_bl_targets_in_both_symbol_sources(self):
        symbols = {name: value["target"] for name, value in d.CALL_TARGETS.items()}

        def render(values):
            return "\n".join(f"{address:016x} T {name}" for name, address in values.items())

        original = render(symbols)
        d.gate_call_targets(d.ORIGINAL, original, original)
        for name in symbols:
            changed = render({**symbols, name: symbols[name] + 4})
            for first, second in ((changed, original), (original, changed), (changed, changed)):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "CALL_TARGET"):
                    d.gate_call_targets(d.ORIGINAL, first, second)
        with self.assertRaises(ValueError):
            d.gate_call_targets(changed_byte(d.ORIGINAL, d.KFREE_CALL - d.PARENT), original, original)

    def test_core_delay_and_terminal_control_flow_are_exact(self):
        for delay in (8, 1):
            core = d.cp.delay_core(d.CORE, delay)
            self.assertEqual(d.gate_core(core, delay), core)
            for index in range(14):
                with self.subTest(delay=delay, word=index), self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
                    d.gate_core(changed_byte(core, index * 4), delay)
            for invalid in (core[:-4], core + bytes(4), bytes(56)):
                with self.assertRaises(ValueError):
                    d.gate_core(invalid, delay)
        for delay in (True, 1.0, 0, 2, 9, 24, "8"):
            with self.subTest(delay=delay), self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
                d.gate_core(d.CORE, delay)
        self.assertEqual(d.SCOPE["positive_proves"], "deferred_reason_kfree_returned")
        self.assertIn("get_device_reference_success", d.SCOPE["positive_not_proven"])
        self.assertIn("deferred_reason_field_cleared", d.SCOPE["positive_not_proven"])
        self.assertFalse(d.SCOPE["terminal_fallthrough"])
        self.assertFalse(d.SCOPE["retained_backedge_reachable"])

    def test_incoming_targets_cannot_bypass_new_prefix_or_enter_window(self):
        image = d.cp.patch_window(bytes(d.PARENT + d.PARENT_SIZE), d.PARENT, d.ORIGINAL)
        ranges = [(d.PARENT - 0x20, len(image))]
        self.assertEqual(d.gate_incoming(image, ranges), ([], [(d.TEXT + d.BACKEDGE, d.TEXT + d.LOOP_TARGET)]))

        def branch(source, target):
            return d.cp.patch_window(image, source, struct.pack("<I", 0x14000000 | (((target - source) // 4) & 0x3FFFFFF)))

        for target in (d.PARENT + 4, d.GET_DEVICE_CALL, d.KFREE_CALL, d.OFFSET,
                       d.OFFSET + 4, d.END - 4, d.END, d.EMPTY_TARGET):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "INTERIOR_ENTRY"):
                d.gate_incoming(branch(d.PARENT - 0x20, target), ranges)
        d.gate_incoming(branch(d.PARENT - 0x20, d.PARENT), ranges)
        with self.assertRaisesRegex(ValueError, "INCOMING_ENTRY"):
            d.gate_incoming(branch(d.EMPTY_BRANCH, d.OFFSET), ranges)
        without_loop = d.cp.patch_window(image, d.BACKEDGE, struct.pack("<I", 0xD503201F))
        with self.assertRaisesRegex(ValueError, "PREFIX_BYPASS"):
            d.gate_incoming(without_loop, ranges)

    def test_exception_fault_and_fixup_protect_complete_parent(self):
        table = d.TEXT + 0x1B0F690
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE

        def entry(fault, fixup):
            return struct.pack("<iiHH", fault - table, fixup - table - 4, 2, 0)

        self.assertEqual(d.gate_exception_destinations(entry(lo - 4, hi), table, (lo, hi)), 1)
        for offset in (d.PARENT, d.GET_DEVICE_CALL, d.KFREE_CALL, d.OFFSET,
                       d.REASON_CLEAR_STORE, d.END, d.PARENT + d.PARENT_SIZE - 4):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "EXCEPTION_FIXUP"):
                d.gate_exception_destinations(entry(lo - 4, d.TEXT + offset), table, (lo, hi))
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "EXCEPTION_FAULT"):
                d.gate_exception_destinations(entry(d.TEXT + offset, hi), table, (lo, hi))

    def test_section_coverage_and_unique_parent_mapping_are_required(self):
        original = section_map()
        self.assertEqual(d.gate_sections(original, 0x2380000), list(d.CODE_RANGES))
        for name in (".text", ".exit.text", "__ex_table", ".altinstructions", ".rela.dyn", ".relr.dyn"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                d.gate_sections([row for row in original if row["name"] != name], 0x2380000)
        for field, value in (("code", False), ("alloc", False), ("size", 0x10D3FFC), ("vma", d.TEXT)):
            rows = copy.deepcopy(original)
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "COVERAGE"):
                d.gate_sections(rows, 0x2380000)
        with self.assertRaisesRegex(ValueError, "DUPLICATED"):
            d.gate_sections(original + [original[0]], 0x2380000)
        with self.assertRaisesRegex(ValueError, "COVERAGE"):
            d.gate_sections(original, d.PARENT + d.PARENT_SIZE)
        overlap = {"name": ".unexpected", "vma": d.TEXT + d.PARENT, "size": d.PARENT_SIZE,
                   "alloc": False, "code": False}
        with self.assertRaises(SystemExit):
            d.gate_sections(original + [overlap], 0x2380000)

    def test_rela_relr_and_writes_crossing_parent_start_are_rejected(self):
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE
        self.assertEqual(d.gate_relocation_sites([lo - 8, hi]), 2)
        for site in (lo - 7, lo - 1, lo, d.TEXT + d.KFREE_CALL, d.TEXT + d.OFFSET,
                     d.TEXT + d.END, hi - 1):
            line = f"{site:016x} 0000000000000403 R_AARCH64_RELATIVE 0"
            match = d.cp.t3.RELOC_OFF_RE.match(line)
            self.assertIsNotNone(match)
            with self.subTest(rela_site=site), self.assertRaises(SystemExit):
                d.gate_relocation_sites([int(match.group(1), 16)])
        safe = struct.pack("<QQ", lo - 12, hi)
        self.assertEqual(d.gate_relocation_sites(d.cp.decode_relr(safe)), 2)
        for site in (lo - 4, d.TEXT + d.KFREE_CALL, d.TEXT + d.OFFSET + 4, hi - 8):
            with self.subTest(relr_site=site), self.assertRaises(SystemExit):
                d.gate_relocation_sites(d.cp.decode_relr(struct.pack("<Q", site)))
        bitmap = d.cp.decode_relr(struct.pack("<QQ", lo - 12, 3))
        self.assertEqual(bitmap, [lo - 12, lo - 4])
        with self.assertRaises(SystemExit):
            d.gate_relocation_sites(bitmap)
        for invalid in (bytes(7), struct.pack("<Q", 3)):
            with self.assertRaises(ValueError):
                d.cp.decode_relr(invalid)

    def test_bundle_metadata_and_files_cannot_self_authorize(self):
        files = {name: b"untrusted" for name in d.BUNDLE_FILES}
        for key, value in (("linux_base", "b" * 40), ("patch_queue_sha256", "0" * 64),
                           ("source_commit", "b" * 40), ("run_id", "1"), ("extra", True)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "BUNDLE_IDENTITY"):
                d.gate_bundle({**copy.deepcopy(d.BUNDLE_IDENTITY), key: value}, files)
        for key, value in (("run_id", "1"), ("rebuild", True), ("image_reproduction", "UNCHECKED"),
                           ("original_vmlinux_sha256", "0" * 64), ("source_commit", "b" * 40)):
            metadata = copy.deepcopy(d.BUNDLE_IDENTITY)
            metadata["elf_export_reconciliation"][key] = value
            with self.subTest(reconciliation=key), self.assertRaisesRegex(ValueError, "BUNDLE_IDENTITY"):
                d.gate_bundle(metadata, files)
        metadata = copy.deepcopy(d.BUNDLE_IDENTITY)
        metadata["files"] = {name: d.cp.digest(value) for name, value in files.items()}
        with self.assertRaisesRegex(ValueError, "BUNDLE_IDENTITY"):
            d.gate_bundle(metadata, files)
        with self.assertRaisesRegex(ValueError, "BUNDLE_FILE_SET"):
            d.gate_bundle(d.BUNDLE_IDENTITY, {})
        with self.assertRaisesRegex(ValueError, "BUNDLE_FILE_IDENTITY"):
            d.gate_bundle(d.BUNDLE_IDENTITY, files)

    def test_public_authority_rejects_short_or_noncanonical_identifiers(self):
        d.gate_authority(SOURCE_COMMIT, PUBLIC_RUN)
        for commit, run in ((None, PUBLIC_RUN), ("abc1234", PUBLIC_RUN), ("A" * 40, PUBLIC_RUN),
                            (SOURCE_COMMIT, 12345), (SOURCE_COMMIT, "0"), (SOURCE_COMMIT, "")):
            with self.subTest(commit=commit, run=run), self.assertRaises(ValueError):
                d.gate_authority(commit, run)
        if os.environ.get("GITHUB_REPOSITORY") == d.PUBLIC_REPOSITORY:
            with self.assertRaisesRegex(ValueError, "PRIVATE_ONLY"):
                d.gate_actions(private=True)


class RuntimeRewriteTests(unittest.TestCase):
    def audit_table(self, name, data, table):
        out = Path(tempfile.mkdtemp(prefix="after-kfree-table-"))
        binary = out / "input.bin"
        binary.write_bytes(data)
        rows = [{"name": name, "vma": table, "file_off": 0, "size": len(data)}]
        return d.cp.audit_rewrites(out, binary, rows,
                                   (d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE))

    def test_runtime_instruction_tables_protect_prefix_window_and_suffix(self):
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
                report = self.audit_table(name, make(site), table)
                self.assertNotEqual(report[name.lstrip(".")], "ABSENT")
            for site in (lo, d.TEXT + d.GET_DEVICE_CALL, d.TEXT + d.KFREE_CALL,
                         d.TEXT + d.OFFSET, d.TEXT + d.END, hi - 4):
                with self.subTest(section=name, site=site), self.assertRaises(SystemExit):
                    self.audit_table(name, make(site), table)

    def test_alternative_start_before_parent_cannot_overlap_it(self):
        table = d.TEXT + 0x1BC6490
        lo = d.TEXT + d.PARENT
        safe = struct.pack("<iiHBB", lo - 8 - table, 0, 0, 8, 8)
        self.audit_table(".altinstructions", safe, table)
        overlap = struct.pack("<iiHBB", lo - 4 - table, 0, 0, 8, 8)
        with self.assertRaisesRegex(ValueError, "ALTERNATIVE_OVERLAPS"):
            self.audit_table(".altinstructions", overlap, table)


@unittest.skipUnless(all((d.cp.pb.LINUX / name).is_file() for name in d.SOURCE_FILES), "pinned Linux source unavailable")
class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (d.cp.pb.LINUX / "drivers/base/dd.c").read_text()
        cls.core = (d.cp.pb.LINUX / "drivers/base/core.c").read_text()

    def test_pinned_worker_get_device_reason_and_unlock_order(self):
        d.source_contract(self.source, self.core, "CONFIG_MODULES=y\n")
        variants = [
            self.source.replace("get_device(dev);", "get_device(dev); mutex_unlock(&deferred_probe_mutex);", 1),
            self.source.replace("__device_set_deferred_probe_reason(dev, NULL);", "", 1),
            self.source.replace("kfree(dev->p->deferred_probe_reason);", "kvfree(dev->p->deferred_probe_reason);", 1),
            self.source.replace("kfree(dev->p->deferred_probe_reason);", "dev->p->deferred_probe_reason = NULL; kfree(dev->p->deferred_probe_reason);", 1),
            self.source.replace("dev->p->deferred_probe_reason = reason;", "", 1),
        ]
        for source in variants:
            self.assertNotEqual(source, self.source)
            with self.assertRaises(ValueError):
                d.source_contract(source, self.core, "CONFIG_MODULES=y\n")
        changed = self.core.replace("return dev ? kobj_to_dev(kobject_get(&dev->kobj)) : NULL;", "return dev;", 1)
        self.assertNotEqual(changed, self.core)
        with self.assertRaisesRegex(ValueError, "GET_DEVICE_SOURCE"):
            d.source_contract(self.source, changed, "CONFIG_MODULES=y\n")


@unittest.skipUnless(FROZEN.is_file(), "immutable FIX8 input unavailable")
class PayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = FROZEN.read_bytes()
        d.gate_frozen(cls.frozen)
        cls.payloads = [d.cp.patch_window(cls.frozen, d.OFFSET, d.cp.delay_core(d.CORE, delay)) for delay in (8, 1)]
        cls.manifests = [manifest(payload, delay) for delay, payload in zip((8, 1), cls.payloads)]
        cls.identity = d.pair_identity(cls.payloads, cls.manifests, SOURCE_COMMIT, PUBLIC_RUN)

    def member(self, payload=None, metadata=None, frozen=None, delay=8, commit=SOURCE_COMMIT, run=PUBLIC_RUN):
        d.gate_member("after_kfree", self.frozen if frozen is None else frozen,
                      self.payloads[0] if payload is None else payload,
                      self.manifests[0] if metadata is None else metadata, delay, commit, run)

    def test_exact_members_and_complete_manifest_authority(self):
        for delay, payload, metadata in zip((8, 1), self.payloads, self.manifests):
            self.member(payload, metadata, delay=delay)
        mutations = (("stage", "selected"), ("case", "defer_selected8"), ("offset", d.OFFSET - 4),
                     ("window", 60), ("window_end", d.END + 4), ("parent_size", 200), ("section", ".init.text"),
                     ("source_commit", "b" * 40), ("public_run", "12346"), ("delay_seconds", True),
                     ("payload_sha256", "0" * 64), ("checkpoint_sha256", "0" * 64),
                     ("positive_proves", "reference_acquired"), ("positive_not_proven", []),
                     ("reason_field_cleared_at_checkpoint", True), ("get_device_return_value_checked", True),
                     ("maximum_delay_seconds", 24), ("predecessor_offset", d.GET_DEVICE_CALL),
                     ("original_calls", {}), ("original_reason_loads", []), ("reason_clear_store", d.OFFSET - 4),
                     ("added_pointer_or_name_dereferences", 1), ("terminal_fallthrough", True),
                     ("empty_list_reaches_probe", True), ("retained_backedge_reachable", True),
                     ("normal_boot_candidate", True), ("runtime_rewrites", {}), ("source_files_sha256", {}))
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.member(metadata={**self.manifests[0], key: value})
        with self.assertRaisesRegex(ValueError, "FIELD_SET"):
            self.member(metadata={**self.manifests[0], "culprit": "unsupported"})
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            self.member(commit="b" * 40)
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            self.member(run="12346")

    def test_every_boundary_and_frozen_identity_is_preserved(self):
        for offset in (0, d.PARENT, d.selected.OFFSET, d.KFREE_CALL, d.END,
                       d.EMPTY_TARGET, d.PARENT + d.PARENT_SIZE - 4, len(self.frozen) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "OUTSIDE_AFTER_KFREE"):
                self.member(payload=changed_byte(self.payloads[0], offset))
        with self.assertRaisesRegex(ValueError, "PAYLOAD_SIZE"):
            self.member(payload=self.payloads[0][:-1])
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            self.member(payload=changed_byte(self.payloads[0], d.OFFSET + 52))
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            self.member(frozen=changed_byte(self.frozen, 0), payload=changed_byte(self.payloads[0], 0))
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            d.gate_frozen(self.frozen[:-1])
        with self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
            self.member(delay=True)

    def test_pair_binds_direction_all_bytes_and_complete_case_identity(self):
        d.gate_pair("after_kfree", self.payloads, self.manifests, self.identity, SOURCE_COMMIT, PUBLIC_RUN)
        for key, value in (("stage", "selected"), ("cases", ["defer_selected8", "defer_selected1"]),
                           ("source_commit", "b" * 40), ("public_run", "9"), ("expected_delta_s", 7),
                           ("changed_offsets", [d.OFFSET + 8]), ("payload_shas", {}), ("manifest_shas", {})):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "PAIR_IDENTITY"):
                d.gate_pair("after_kfree", self.payloads, self.manifests, {**self.identity, key: value}, SOURCE_COMMIT, PUBLIC_RUN)
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            d.gate_pair("after_kfree", list(reversed(self.payloads)), self.manifests, self.identity, SOURCE_COMMIT, PUBLIC_RUN)
        payloads = [self.payloads[0], changed_byte(self.payloads[1], 0)]
        manifests = copy.deepcopy(self.manifests)
        manifests[1]["payload_sha256"] = d.cp.digest(payloads[1])
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_ONLY"):
            d.gate_pair("after_kfree", payloads, manifests, d.pair_identity(payloads, manifests, SOURCE_COMMIT, PUBLIC_RUN), SOURCE_COMMIT, PUBLIC_RUN)
        manifests = copy.deepcopy(self.manifests)
        manifests[1]["source_files_sha256"]["drivers/base/core.c"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "PAIR_AUDIT_METADATA"):
            d.gate_pair("after_kfree", self.payloads, manifests, d.pair_identity(self.payloads, manifests, SOURCE_COMMIT, PUBLIC_RUN), SOURCE_COMMIT, PUBLIC_RUN)
        with self.assertRaisesRegex(ValueError, "PAIR_SIZE"):
            d.gate_pair("after_kfree", self.payloads[:1], self.manifests, self.identity, SOURCE_COMMIT, PUBLIC_RUN)


class BootEnvelopeTests(unittest.TestCase):
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

    def test_only_byte_envelope_fixture_bypasses_no_frozen_hash_gate(self):
        for payload, boot in zip(self.payloads, self.boots):
            d.gate_boot_bytes(self.frozen, payload, boot, self.base)
            with self.assertRaisesRegex(ValueError, "BASE_BOOT"):
                d.gate_boot("after_kfree", self.frozen, payload, boot, self.base)
        self.assertEqual(d.gate_boot_pair(self.boots), [d.cp.pb.PAGE + d.OFFSET + 9, d.cp.pb.PAGE + d.OFFSET + 10])

    def test_header_payload_prefix_backedge_and_trailer_cannot_change(self):
        for offset in (0, 44, d.cp.pb.PAGE + d.PARENT, d.cp.pb.PAGE + d.KFREE_CALL,
                       d.cp.pb.PAGE + d.END, d.cp.pb.PAGE + len(self.frozen), len(self.base) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "ENVELOPE_OR_OUTSIDE"):
                d.gate_boot_bytes(self.frozen, self.payloads[0], changed_byte(self.boots[0], offset), self.base)
        with self.assertRaisesRegex(ValueError, "BOOT_PAYLOAD"):
            d.gate_boot_bytes(self.frozen, self.payloads[0], self.boots[1], self.base)
        with self.assertRaisesRegex(ValueError, "BOOT_SIZE"):
            d.gate_boot_bytes(self.frozen, self.payloads[0], self.boots[0][:-1], self.base)
        for boots in ([self.boots[0], self.boots[0]], [self.boots[0], changed_byte(self.boots[1], 0)]):
            with self.assertRaisesRegex(ValueError, "BOOT_PAIR_NOT_DELAY"):
                d.gate_boot_pair(boots)
        with self.assertRaisesRegex(ValueError, "BOOT_PAIR_SIZE"):
            d.gate_boot_pair(self.boots[:1])


if __name__ == "__main__":
    unittest.main()
