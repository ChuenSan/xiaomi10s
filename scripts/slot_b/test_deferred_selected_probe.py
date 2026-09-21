import argparse
import copy
import io
import json
import os
import struct
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import deferred_selected_probe as d

SOURCE = """static bool driver_deferred_probe_enable;
static void deferred_probe_work_func(struct work_struct *work)
{
    struct device *dev;
    struct device_private *private;
    mutex_lock(&deferred_probe_mutex);
    while (!list_empty(&deferred_probe_active_list)) {
        private = list_first_entry(&deferred_probe_active_list,
                                  typeof(*dev->p), deferred_probe);
        dev = private->device;
        list_del_init(&private->deferred_probe);
        get_device(dev);
        __device_set_deferred_probe_reason(dev, NULL);
        mutex_unlock(&deferred_probe_mutex);
        device_pm_move_to_tail(dev);
        bus_probe_device(dev);
        mutex_lock(&deferred_probe_mutex);
        put_device(dev);
    }
    mutex_unlock(&deferred_probe_mutex);
}
static DECLARE_WORK(deferred_probe_work, deferred_probe_work_func);
void driver_deferred_probe_trigger(void)
{
    if (!driver_deferred_probe_enable)
        return;
    mutex_lock(&deferred_probe_mutex);
    atomic_inc(&deferred_trigger_count);
    list_splice_tail_init(&deferred_probe_pending_list, &deferred_probe_active_list);
    mutex_unlock(&deferred_probe_mutex);
    queue_work(system_unbound_wq, &deferred_probe_work);
}
static int deferred_probe_initcall(void)
{
    driver_deferred_probe_enable = true;
    driver_deferred_probe_trigger();
    flush_work(&deferred_probe_work);
    initcalls_done = true;
    if (!IS_ENABLED(CONFIG_MODULES))
        fw_devlink_drivers_done();
    driver_deferred_probe_trigger();
    flush_work(&deferred_probe_work);
    if (driver_deferred_probe_timeout > 0)
        schedule_delayed_work(&deferred_probe_timeout_work, HZ);
    return 0;
}
late_initcall(deferred_probe_initcall);
"""
EX_HEADER = """struct exception_table_entry {
    int insn, fixup;
    short type, data;
};
#define ARCH_HAS_RELATIVE_EXTABLE
"""
EX_IMPL = """static inline unsigned long
get_ex_fixup(const struct exception_table_entry *ex)
{
    return ((unsigned long)&ex->fixup + ex->fixup);
}
"""
SOURCES = dict(zip(d.SOURCE_FILES, (SOURCE.encode(), EX_HEADER.encode(), EX_IMPL.encode())))
SOURCE_COMMIT = "a" * 40
PUBLIC_RUN = "12345"


def changed_byte(data, offset):
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]


def sections():
    names = (".head.text", ".text", ".rodata.text", ".init.text", ".exit.text")
    result = [{"name": name, "vma": d.TEXT + lo, "size": hi - lo,
               "alloc": True, "code": True} for name, (lo, hi) in zip(names, d.CODE_RANGES)]
    for name, offset in (("__ex_table", 0x1B0F690), (".altinstructions", 0x1BC6490),
                         (".rela.dyn", 0x1D2C440), (".relr.dyn", 0x1D2C4D0)):
        result.append({"name": name, "vma": d.TEXT + offset, "size": 12,
                       "alloc": True, "code": False})
    return result


class SelectedBoundaryTests(unittest.TestCase):
    def test_scope_and_cli_exclude_every_frozen_stage(self):
        self.assertEqual(set(d.deferred.STAGES), {"prequeue", "postflush", "worker"})
        self.assertEqual((d.PARENT, d.PARENT_SIZE, d.OFFSET, d.WINDOW, d.END),
                         (0x8E8424, 196, 0x8E8468, 56, 0x8E84A0))
        argv = ["--frozen", "frozen", "--out", "out", "--stage", "selected"]
        self.assertEqual(d.parser().parse_args(argv).stage, "selected")
        for stage in ("worker", "prequeue", "postflush", "selected8", "text54"):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "UNAUTHORIZED"):
                d.gate_stage(stage)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.parser().parse_args(argv[:-1] + [stage])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            d.parser().parse_args(argv[:-2])

    def test_original_window_and_every_opcode_are_frozen(self):
        original = struct.pack("<14I", *d.WINDOW_WORDS)
        d.gate_window("selected", d.OFFSET, original)
        for offset, blob in ((d.OFFSET - 4, original), (d.OFFSET + 4, original),
                             (d.OFFSET, original[:-4]), (d.OFFSET, original + bytes(4))):
            with self.subTest(offset=offset, size=len(blob)), self.assertRaisesRegex(ValueError, "GEOMETRY"):
                d.gate_window("selected", offset, blob)
        for word in range(14):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, "ORIGINAL_WINDOW"):
                d.gate_window("selected", d.OFFSET, changed_byte(original, word * 4))

    def test_pac_frame_mutex_empty_branch_and_device_load_are_exact(self):
        d.gate_worker(d.ORIGINAL)
        for word in range(17):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, "PREFIX"):
                d.gate_worker(changed_byte(d.ORIGINAL, word * 4))
        for word in range(31, 49):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, "SUFFIX_OR_BACKEDGE"):
                d.gate_worker(changed_byte(d.ORIGINAL, word * 4))
        with self.assertRaisesRegex(ValueError, "EXTENT"):
            d.gate_worker(d.ORIGINAL[:-4])
        self.assertEqual(d.cp.branch_target(d.PREFIX_WORDS[7], d.TEXT + 0x8E8440),
                         d.TEXT + 0x10C72C4)
        self.assertEqual(d.cp.branch_target(d.PREFIX_WORDS[12], d.TEXT + d.EMPTY_BRANCH),
                         d.TEXT + d.EMPTY_TARGET)
        self.assertEqual(d.cp.branch_target(d.SUFFIX_WORDS[9], d.TEXT + d.BACKEDGE),
                         d.TEXT + d.LOOP_TARGET)

    def test_whole_parent_agreement_is_required_even_outside_window(self):
        d.gate_parent_agreement(d.ORIGINAL, d.ORIGINAL, d.ORIGINAL)
        for part in range(3):
            items = [d.ORIGINAL] * 3
            items[part] = changed_byte(items[part], 0)
            with self.subTest(part=part), self.assertRaisesRegex(ValueError, "DISAGREEMENT"):
                d.gate_parent_agreement(*items)
        mutated = changed_byte(d.ORIGINAL, d.PARENT_SIZE - 4)
        with self.assertRaisesRegex(ValueError, "SUFFIX_OR_BACKEDGE"):
            d.gate_parent_agreement(mutated, mutated, mutated)

    def test_proven_core_has_no_terminal_escape_or_extra_dereference(self):
        for delay in (8, 1):
            core = d.cp.delay_core(d.CORE, delay)
            self.assertEqual(d.gate_core(core, delay), core)
            for word in range(14):
                with self.subTest(delay=delay, word=word), self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
                    d.gate_core(changed_byte(core, word * 4), delay)
            for blob in (core[:-4], core + bytes(4), bytes(56)):
                with self.assertRaises(ValueError):
                    d.gate_core(blob, delay)
        for delay in (True, 1.0, 0, 2, 24, "8"):
            with self.subTest(delay=delay), self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
                d.gate_core(d.CORE, delay)
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            d.gate_core(d.CORE, 1)
        self.assertEqual(d.SCOPE["positive_only"], ["deferred_probe_mutex_acquired", "active_list_nonempty",
                                                  "first_active_device_pointer_loaded_into_x20"])
        self.assertFalse(d.SCOPE["callback_first_activation_only"])

    def test_source_requires_mutex_nonempty_first_entry_load_before_get(self):
        d.source_contract(SOURCE, "CONFIG_MODULES=y\n")
        mutations = (
            SOURCE.replace("mutex_lock(&deferred_probe_mutex);", "", 1),
            SOURCE.replace("while (!list_empty", "while (list_empty", 1),
            SOURCE.replace("dev = private->device;", "dev = NULL;", 1),
            SOURCE.replace("dev = private->device;", "dev_name(dev); dev = private->device;", 1),
            SOURCE.replace("dev = private->device;", "get_device(dev); dev = private->device;", 1),
            SOURCE.replace("dev = private->device;\n        list_del_init(&private->deferred_probe);",
                           "list_del_init(&private->deferred_probe);\n        dev = private->device;", 1),
            SOURCE.replace("typeof(*dev->p), deferred_probe", "typeof(*dev->p), other_list", 1),
            SOURCE.replace("static DECLARE_WORK(deferred_probe_work, deferred_probe_work_func);", ""),
            SOURCE.replace("static DECLARE_WORK", "static DECLARE_DELAYED_WORK", 1),
            SOURCE.replace("static bool driver_deferred_probe_enable;", "static bool driver_deferred_probe_enable = true;"),
            SOURCE.replace("driver_deferred_probe_enable = true;", "driver_deferred_probe_enable = false;"),
            SOURCE.replace("if (!driver_deferred_probe_enable)\n        return;", ""),
            SOURCE.replace("queue_work(system_unbound_wq", "queue_work(system_wq", 1),
            SOURCE.replace("atomic_inc(&deferred_trigger_count);", "return; atomic_inc(&deferred_trigger_count);", 1),
            SOURCE.replace("late_initcall(deferred_probe_initcall);", "device_initcall(deferred_probe_initcall);"),
            SOURCE.replace("flush_work(&deferred_probe_work);", "", 1),
        )
        for i, source in enumerate(mutations):
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                d.source_contract(source, "CONFIG_MODULES=y\n")
        with self.assertRaisesRegex(ValueError, "MODULES_CONFIG"):
            d.source_contract(SOURCE, "# CONFIG_MODULES is not set\n")

    def test_source_and_queue_identity_cannot_be_self_attested(self):
        d.gate_source_identity(d.cp.pb.LINUX_BASE, d.cp.pb.PATCH_QUEUE_SHA, SOURCES, SOURCES)
        for head, queue, files in (("b" * 40, d.cp.pb.PATCH_QUEUE_SHA, SOURCES),
                                   (d.cp.pb.LINUX_BASE, "0" * 64, SOURCES),
                                   (d.cp.pb.LINUX_BASE, d.cp.pb.PATCH_QUEUE_SHA,
                                    {**SOURCES, d.SOURCE_FILES[0]: SOURCE.replace("dev =", "device =").encode()}),
                                   (d.cp.pb.LINUX_BASE, d.cp.pb.PATCH_QUEUE_SHA, {})):
            with self.assertRaises(ValueError):
                d.gate_source_identity(head, queue, files, SOURCES)

    def test_bundle_freezes_every_file_and_reconciled_provenance(self):
        files = {name: name.encode() for name in d.BUNDLE_FILES}
        hashes = {name.encode(): value for name, value in d.BUNDLE_FILES.items()}
        with patch.object(d.cp, "digest", side_effect=lambda value: hashes.get(value, "0" * 64)):
            d.gate_bundle(copy.deepcopy(d.BUNDLE_IDENTITY), files)
            for name in files:
                with self.subTest(file=name), self.assertRaisesRegex(ValueError, "BUNDLE_FILE_IDENTITY"):
                    d.gate_bundle(d.BUNDLE_IDENTITY, {**files, name: b"mutated"})
        for key, value in (("linux_base", "b" * 40), ("patch_queue_sha256", "0" * 64),
                           ("source_commit", "b" * 40), ("run_id", "1")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "BUNDLE_IDENTITY"):
                d.gate_bundle({**d.BUNDLE_IDENTITY, key: value}, files)
        for key, value in (("run_id", "1"), ("rebuild", True), ("image_reproduction", "UNCHECKED")):
            metadata = copy.deepcopy(d.BUNDLE_IDENTITY)
            metadata["elf_export_reconciliation"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "BUNDLE_IDENTITY"):
                d.gate_bundle(metadata, files)
        metadata = copy.deepcopy(d.BUNDLE_IDENTITY)
        metadata["files"]["Image"] = d.cp.digest(b"mutated")
        with self.assertRaisesRegex(ValueError, "BUNDLE_IDENTITY"):
            d.gate_bundle(metadata, {**files, "Image": b"mutated"})

    def test_whole_executable_section_coverage_cannot_silently_shrink(self):
        original = sections()
        self.assertEqual(d.gate_sections(original, 0x2380000), list(d.CODE_RANGES))
        for name in (".text", ".exit.text", "__ex_table", ".rela.dyn", ".relr.dyn"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                d.gate_sections([s for s in original if s["name"] != name], 0x2380000)
        for field, value in (("code", False), ("alloc", False), ("size", 0x10D3FFC)):
            rows = copy.deepcopy(original)
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                d.gate_sections(rows, 0x2380000)
        with self.assertRaisesRegex(ValueError, "DUPLICATED"):
            d.gate_sections(original + [original[0]], 0x2380000)
        with self.assertRaisesRegex(ValueError, "COVERAGE"):
            d.gate_sections(original, d.END)

    def test_incoming_scan_rejects_prefix_window_and_tail_bypasses(self):
        image = d.cp.patch_window(bytes(d.PARENT + d.PARENT_SIZE), d.PARENT, d.ORIGINAL)
        ranges = [(d.PARENT - 0x20, len(image))]
        d.gate_incoming(image, ranges)
        source = d.PARENT - 0x20
        for target in (d.PARENT + 4, d.OFFSET - 4, d.OFFSET, d.OFFSET + 4,
                       d.END, d.EMPTY_TARGET, d.BACKEDGE):
            word = 0x14000000 | (((target - source) // 4) & 0x3FFFFFF)
            mutated = d.cp.patch_window(image, source, struct.pack("<I", word))
            with self.subTest(target=hex(target)), self.assertRaisesRegex(ValueError, "INTERIOR_ENTRY"):
                d.gate_incoming(mutated, ranges)
        word = 0x94000000 | (((d.PARENT - source) // 4) & 0x3FFFFFF)
        d.gate_incoming(d.cp.patch_window(image, source, struct.pack("<I", word)), ranges)
        with self.assertRaisesRegex(ValueError, "PREFIX_BYPASS"):
            d.gate_incoming(d.cp.patch_window(image, d.BACKEDGE, struct.pack("<I", 0xD503201F)), ranges)
        word = 0x14000000 | (((d.OFFSET - d.EMPTY_BRANCH) // 4) & 0x3FFFFFF)
        with self.assertRaisesRegex(ValueError, "INCOMING_ENTRY"):
            d.gate_incoming(d.cp.patch_window(image, d.EMPTY_BRANCH, struct.pack("<I", word)), ranges)

    def test_exception_abi_uses_its_own_fixup_field(self):
        d.gate_exception_abi(EX_HEADER, EX_IMPL)
        for header in (EX_HEADER.replace("int insn, fixup;", "long insn, fixup;"),
                       EX_HEADER.replace("int insn, fixup;", "int fixup, insn;"),
                       EX_HEADER.replace("short type, data;", "int type, data;"),
                       EX_HEADER.replace("#define ARCH_HAS_RELATIVE_EXTABLE", "")):
            with self.assertRaisesRegex(ValueError, "ABI"):
                d.gate_exception_abi(header, EX_IMPL)
        for implementation in (EX_IMPL.replace("&ex->fixup", "&ex->insn"),
                               EX_IMPL.replace("+ ex->fixup", "+ ex->fixup + 4")):
            with self.assertRaisesRegex(ValueError, "FIXUP_BASE"):
                d.gate_exception_abi(EX_HEADER, implementation)

    def test_exception_fixup_destination_closes_shared_fault_only_gap(self):
        table = d.TEXT + 0x1B0F690
        lo, hi = d.TEXT + d.PARENT, d.TEXT + d.PARENT + d.PARENT_SIZE
        def entry(fault, fixup, index=0):
            base = table + index * 12
            return struct.pack("<iiHH", fault - base, fixup - base - 4, 2, 0)
        safe = entry(lo - 4, hi)
        self.assertEqual(d.gate_exception_destinations(safe, table, (lo, hi)), 1)
        for address in (lo, d.TEXT + d.OFFSET - 4, d.TEXT + d.OFFSET,
                        d.TEXT + d.END - 4, hi - 4):
            fixup = entry(lo - 4, address)
            self.assertEqual(d.cp.t3.decode_ex_table(fixup, table), [lo - 4])
            with self.subTest(fixup=hex(address)), self.assertRaisesRegex(ValueError, "EXCEPTION_FIXUP"):
                d.gate_exception_destinations(fixup, table, (lo, hi))
            with self.subTest(fault=hex(address)), self.assertRaisesRegex(ValueError, "EXCEPTION_FAULT"):
                d.gate_exception_destinations(entry(address, hi), table, (lo, hi))
        with self.assertRaisesRegex(ValueError, "EXCEPTION_FIXUP"):
            d.gate_exception_destinations(safe + entry(lo - 4, lo, 1), table, (lo, hi))
        for data in (safe[:-1], safe + b"x", bytes(4)):
            with self.assertRaisesRegex(ValueError, "RECORD_SIZE"):
                d.gate_exception_destinations(data, table, (lo, hi))

    def test_rela_relr_and_relocation_writes_straddling_prefix_are_rejected(self):
        rows = [{"name": ".relr.dyn"}]
        safe_relr = struct.pack("<Q", d.TEXT + 0x1000)
        def rela(site):
            return f"{site:016x} 0000000000000403 R_AARCH64_RELATIVE 0\n"
        with patch.object(d.cp, "section_bytes", return_value=safe_relr):
            with patch.object(d.cp.pb, "run", return_value=rela(d.TEXT + d.PARENT - 8)):
                d.gate_relocations(Path("vmlinux"), rows)
            for site in (d.PARENT - 7, d.PARENT, d.OFFSET - 4, d.OFFSET,
                         d.END - 1, d.BACKEDGE):
                with self.subTest(site=site), patch.object(d.cp.pb, "run", return_value=rela(d.TEXT + site)), \
                     self.assertRaises(SystemExit):
                    d.gate_relocations(Path("vmlinux"), rows)
        bitmap = struct.pack("<QQ", d.TEXT + d.PARENT - 8, 3)
        with patch.object(d.cp.pb, "run", return_value=""), \
             patch.object(d.cp, "section_bytes", return_value=bitmap), self.assertRaises(SystemExit):
            d.gate_relocations(Path("vmlinux"), rows)

    def test_actions_repository_and_authority_guards(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": d.PUBLIC_REPOSITORY}):
            d.gate_actions()
            with self.assertRaisesRegex(ValueError, "PRIVATE_ONLY"):
                d.gate_actions(private=True)
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "GITHUB_REPOSITORY": d.PRIVATE_REPOSITORY}):
            with self.assertRaisesRegex(ValueError, "ACTIONS_REQUIRED"):
                d.gate_actions(private=True)
        d.gate_authority(SOURCE_COMMIT, PUBLIC_RUN)
        for commit, run in ((None, PUBLIC_RUN), ("abc1234", PUBLIC_RUN),
                            ("A" * 40, PUBLIC_RUN), (SOURCE_COMMIT, 12345),
                            (SOURCE_COMMIT, "0"), (SOURCE_COMMIT, "")):
            with self.assertRaises(ValueError):
                d.gate_authority(commit, run)


class SelectedPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = d.cp.patch_window(bytes(d.cp.t3.FIX8_PAYLOAD_SIZE), d.PARENT, d.ORIGINAL)
        cls.frozen_sha = d.cp.digest(cls.frozen)
        cls.payloads = [d.cp.patch_window(cls.frozen, d.OFFSET, d.cp.delay_core(d.CORE, delay))
                        for delay in (8, 1)]
        cls.manifests = [{**copy.deepcopy(d.SCOPE), "source_commit": SOURCE_COMMIT, "public_run": PUBLIC_RUN,
                          "source_files_sha256": {name: d.cp.digest(data) for name, data in SOURCES.items()},
                          "case": f"defer_selected{delay}", "delay_seconds": delay,
                          "payload_sha256": d.cp.digest(payload),
                          "checkpoint_sha256": d.cp.digest(payload[d.OFFSET:d.END])}
                         for delay, payload in zip((8, 1), cls.payloads)]
        cls.identity = d.pair_identity(cls.payloads, cls.manifests, SOURCE_COMMIT, PUBLIC_RUN)
        header = bytearray(d.cp.pb.PAGE)
        header[:8] = b"ANDROID!"
        struct.pack_into("<IIII", header, 8, len(cls.frozen), 0, 0, d.cp.pb.BOOT_HEADER_V3_SIZE)
        struct.pack_into("<I", header, 40, 3)
        cls.base = bytes(header) + cls.frozen + bytes(d.BOOT_SIZE - len(header) - len(cls.frozen))
        cls.base_sha = d.cp.digest(cls.base)
        cls.boots = [cls.base[:d.cp.pb.PAGE] + payload + cls.base[d.cp.pb.PAGE + len(payload):]
                     for payload in cls.payloads]

    def setUp(self):
        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)
        self.mocks.enter_context(patch.object(d.cp.t3, "FIX8_PAYLOAD_SHA", self.frozen_sha))
        self.mocks.enter_context(patch.object(d.cp.t3, "gate_tramp_identity"))
        self.mocks.enter_context(patch.object(d, "BASE_BOOT_SHA", self.base_sha))

    def member(self, payload=None, manifest=None, frozen=None, delay=8, commit=SOURCE_COMMIT, run=PUBLIC_RUN):
        d.gate_member("selected", self.frozen if frozen is None else frozen,
                      self.payloads[0] if payload is None else payload,
                      self.manifests[0] if manifest is None else manifest, delay, commit, run)

    def test_members_are_exact_and_metadata_cannot_overstate_proof(self):
        for delay, payload, manifest in zip((8, 1), self.payloads, self.manifests):
            self.member(payload, manifest, delay=delay)
        mutations = (("stage", "worker"), ("case", "defer_worker8"), ("offset", d.OFFSET + 4),
                     ("window", 60), ("window_end", d.END + 4), ("parent_size", 200),
                     ("section", ".init.text"), ("delay_seconds", 1), ("delay_seconds", True),
                     ("source_commit", "b" * 40), ("public_run", "12346"),
                     ("payload_sha256", "0" * 64), ("checkpoint_sha256", "0" * 64),
                     ("normal_boot_candidate", True), ("positive_proves", "deferred_first_bus_probe_entered"),
                     ("positive_not_proven", []), ("callback_first_activation_only", True),
                     ("terminal_fallthrough", True), ("retained_backedge_reachable", True),
                     ("empty_list_reaches_probe", True), ("added_pointer_or_name_dereferences", 1),
                     ("pac_and_frame_preserved", False), ("runtime_rewrites", {}),
                     ("exception_fixup_destinations", "UNCHECKED"), ("source_files_sha256", {}))
        for key, value in mutations:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.member(manifest={**self.manifests[0], key: value})
        with self.assertRaisesRegex(ValueError, "FIELD_SET"):
            self.member(manifest={**self.manifests[0], "culprit": "unproved-device"})
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            self.member(commit="b" * 40)
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            self.member(run="12346")

    def test_baseline_pac_tail_and_envelope_mutations_fail(self):
        for offset in (0, d.PARENT, d.OFFSET - 4, d.END, d.BACKEDGE, len(self.frozen) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "OUTSIDE_SELECTED"):
                self.member(payload=changed_byte(self.payloads[0], offset))
        with self.assertRaisesRegex(ValueError, "PAYLOAD_SIZE"):
            self.member(payload=self.payloads[0][:-1])
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            self.member(payload=changed_byte(self.payloads[0], d.OFFSET + 52))
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            self.member(frozen=changed_byte(self.frozen, 0), payload=changed_byte(self.payloads[0], 0))
        with self.assertRaisesRegex(ValueError, "DELAY_NOT_ALLOWED"):
            self.member(delay=True)

    def test_frozen_gate_rejects_wrong_hash_size_and_external_initrd(self):
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            d.gate_frozen(self.frozen[:-1])
        with self.assertRaisesRegex(ValueError, "FROZEN_PAYLOAD"):
            d.gate_frozen(changed_byte(self.frozen, 0))
        with patch.object(d.cp.pb, "parse_image_hdr", return_value={"image_size": 0x2231000}), \
             patch.object(d.cp.pb, "gate_rt_d"), \
             patch.object(d.cp.rt, "parse_fdt", return_value={"/chosen": {}}):
            d.gate_frozen(self.frozen)
            with patch.object(d.cp.rt, "parse_fdt", return_value={"/chosen": {"linux,initrd-start": b"x"}}), \
                 self.assertRaisesRegex(ValueError, "EXTERNAL_INITRD"):
                d.gate_frozen(self.frozen)
            with patch.object(d.cp.pb, "calc_dtb_offset", return_value=(d.cp.t3.DTB_OFFSET + 4, 0)), \
                 self.assertRaisesRegex(ValueError, "RT_D_OFFSET"):
                d.gate_frozen(self.frozen)

    def test_pair_binds_delay_direction_all_bytes_and_manifest_authority(self):
        d.gate_pair("selected", self.payloads, self.manifests, self.identity, SOURCE_COMMIT, PUBLIC_RUN)
        for key, value in (("source_commit", "b" * 40), ("public_run", "9"), ("stage", "worker"),
                           ("expected_delta_s", 7), ("changed_offsets", [d.OFFSET + 8]),
                           ("payload_shas", {}), ("manifest_shas", {})):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "PAIR_IDENTITY"):
                d.gate_pair("selected", self.payloads, self.manifests,
                            {**self.identity, key: value}, SOURCE_COMMIT, PUBLIC_RUN)
        with self.assertRaisesRegex(ValueError, "CORE_OR_DELAY"):
            d.gate_pair("selected", list(reversed(self.payloads)), self.manifests,
                        self.identity, SOURCE_COMMIT, PUBLIC_RUN)
        bad = [self.payloads[0], changed_byte(self.payloads[1], 0)]
        manifests = copy.deepcopy(self.manifests)
        manifests[1]["payload_sha256"] = d.cp.digest(bad[1])
        with self.assertRaisesRegex(ValueError, "PAIR_NOT_DELAY_ONLY"):
            d.gate_pair("selected", bad, manifests,
                        d.pair_identity(bad, manifests, SOURCE_COMMIT, PUBLIC_RUN), SOURCE_COMMIT, PUBLIC_RUN)
        manifests = copy.deepcopy(self.manifests)
        manifests[1]["source_files_sha256"][d.SOURCE_FILES[0]] = "0" * 64
        with self.assertRaisesRegex(ValueError, "PAIR_AUDIT_METADATA"):
            d.gate_pair("selected", self.payloads, manifests,
                        d.pair_identity(self.payloads, manifests, SOURCE_COMMIT, PUBLIC_RUN),
                        SOURCE_COMMIT, PUBLIC_RUN)
        with self.assertRaisesRegex(ValueError, "PAIR_SIZE"):
            d.gate_pair("selected", self.payloads[:1], self.manifests, self.identity, SOURCE_COMMIT, PUBLIC_RUN)

    def test_boot_gates_preserve_header_ramdisk_trailer_and_full_hash_pair(self):
        for payload, boot in zip(self.payloads, self.boots):
            d.gate_boot("selected", self.frozen, payload, boot, self.base)
        self.assertEqual(d.gate_boot_pair(self.boots),
                         [d.cp.pb.PAGE + d.OFFSET + 9, d.cp.pb.PAGE + d.OFFSET + 10])
        for offset in (0, 44, d.cp.pb.PAGE + d.PARENT, d.cp.pb.PAGE + d.END,
                       d.cp.pb.PAGE + len(self.frozen), len(self.base) - 1):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "ENVELOPE_OR_OUTSIDE"):
                d.gate_boot("selected", self.frozen, self.payloads[0],
                            changed_byte(self.boots[0], offset), self.base)
        with self.assertRaisesRegex(ValueError, "BOOT_PAYLOAD"):
            d.gate_boot("selected", self.frozen, self.payloads[0], self.boots[1], self.base)
        with self.assertRaisesRegex(ValueError, "BASE_BOOT"):
            d.gate_boot("selected", self.frozen, self.payloads[0], self.boots[0], changed_byte(self.base, 0))
        with self.assertRaisesRegex(ValueError, "BOOT_SIZE"):
            d.gate_boot("selected", self.frozen, self.payloads[0], self.boots[0][:-1], self.base)
        with self.assertRaisesRegex(ValueError, "BOOT_PAIR_NOT_DELAY"):
            d.gate_boot_pair([self.boots[0], self.boots[0]])
        with self.assertRaisesRegex(ValueError, "BOOT_PAIR_NOT_DELAY"):
            d.gate_boot_pair([self.boots[0], changed_byte(self.boots[1], 0)])

    def private_fixture(self):
        args = argparse.Namespace(stage="selected", frozen=Path("/fixture/frozen"),
                                  boot_base=Path("/fixture/base"), pair=Path("/fixture/pair"),
                                  verify_boots=None, out=Path("/fixture/packed"),
                                  source_commit=SOURCE_COMMIT, public_run=PUBLIC_RUN)
        files = {args.frozen: self.frozen, args.boot_base: self.base,
                 args.pair / "pair.json": d.canonical(self.identity)}
        for delay, payload, manifest in zip((8, 1), self.payloads, self.manifests):
            files[args.pair / str(delay) / "payload.bin"] = payload
            files[args.pair / str(delay) / "manifest.json"] = d.canonical(manifest)
        written = {}
        def write(path, data):
            written[path] = data.encode() if isinstance(data, str) else data
            return len(data)
        self.mocks.enter_context(patch.object(Path, "read_bytes", lambda path: files[path]))
        self.mocks.enter_context(patch.object(Path, "read_text", lambda path: files[path].decode()))
        self.mocks.enter_context(patch.object(Path, "write_bytes", write))
        self.mocks.enter_context(patch.object(Path, "write_text", write))
        self.mocks.enter_context(patch.object(Path, "mkdir"))
        self.mocks.enter_context(patch.object(d, "gate_frozen"))
        self.mocks.enter_context(patch.dict(os.environ, {"GITHUB_REPOSITORY": d.PRIVATE_REPOSITORY}))
        self.mocks.enter_context(redirect_stdout(io.StringIO()))
        return args, files, written

    def test_private_pack_and_independent_download_agree_exactly(self):
        args, files, written = self.private_fixture()
        d.private(args)
        self.assertEqual(set(written), {args.out / "defer-selected8-boot.img",
                                        args.out / "defer-selected1-boot.img", args.out / "identity.json"})
        self.assertEqual(written[args.out / "defer-selected8-boot.img"], self.boots[0])
        self.assertEqual(written[args.out / "defer-selected1-boot.img"], self.boots[1])
        identity = written[args.out / "identity.json"]
        files.update(written)
        verify = argparse.Namespace(**{**vars(args), "verify_boots": args.out, "out": Path("/fixture/reverify")})
        d.private(verify)
        self.assertEqual(written[verify.out / "identity.json"], identity)
        self.assertNotIn(verify.out / "defer-selected8-boot.img", written)
        report = json.loads(identity)
        self.assertEqual(report["gate"], "DEFERRED_SELECTED_PRIVATE_PAIR_VERIFIED")
        self.assertNotEqual(report["members"]["8"]["boot_sha256"], report["members"]["1"]["boot_sha256"])

    def test_private_rejects_untrusted_repository_source_and_run_before_writes(self):
        args, files, written = self.private_fixture()
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": d.PUBLIC_REPOSITORY}), \
             self.assertRaisesRegex(ValueError, "PRIVATE_ONLY"):
            d.private(args)
        for key, value in (("source_commit", "b" * 40), ("public_run", "12346")):
            bad = argparse.Namespace(**{**vars(args), key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "PUBLIC_AUTHORITY"):
                d.private(bad)
        files[args.boot_base] = changed_byte(self.base, 0)
        with self.assertRaisesRegex(ValueError, "BASE_BOOT"):
            d.private(args)
        self.assertEqual(written, {})

    def test_private_rejects_member_metadata_forgery_before_any_boot_output(self):
        args, files, written = self.private_fixture()
        path = args.pair / "1/manifest.json"
        manifest = {**self.manifests[1], "public_run": "12346"}
        files[path] = d.canonical(manifest)
        with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
            d.private(args)
        self.assertEqual(written, {})

    def test_private_independent_download_rejects_boot_and_identity_mutations(self):
        args, files, written = self.private_fixture()
        d.private(args)
        files.update(written)
        verify = argparse.Namespace(**{**vars(args), "verify_boots": args.out, "out": Path("/fixture/reverify")})
        boot_path = args.out / "defer-selected1-boot.img"
        files[boot_path] = changed_byte(files[boot_path], len(self.base) - 1)
        with self.assertRaisesRegex(ValueError, "ENVELOPE_OR_OUTSIDE"):
            d.private(verify)
        self.assertNotIn(verify.out / "identity.json", written)
        files[boot_path] = self.boots[1]
        identity = json.loads(files[args.out / "identity.json"])
        identity["members"]["1"]["boot_sha256"] = "0" * 64
        files[args.out / "identity.json"] = d.canonical(identity)
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_IDENTITY"):
            d.private(verify)
        self.assertNotIn(verify.out / "identity.json", written)


if __name__ == "__main__":
    unittest.main()
