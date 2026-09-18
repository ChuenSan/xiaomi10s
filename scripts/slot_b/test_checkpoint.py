import struct
import tempfile
import unittest
from pathlib import Path

import checkpoint


class CheckpointTests(unittest.TestCase):
    def test_runtime_dtb_cannot_advertise_an_external_initrd(self):
        checkpoint.gate_builtin_initramfs_source({'bootargs': b'rdinit=/init'})
        for key in ('linux,initrd-start', 'linux,initrd-end'):
            with self.subTest(property=key), self.assertRaises(ValueError):
                checkpoint.gate_builtin_initramfs_source({key: bytes(8)})

    def test_all_direct_branch_families_use_virtual_pc(self):
        pc = 0xFFFF800080001000
        for word in (0x14000002, 0x94000002, 0x54000040, 0xB4000040, 0x35000040, 0x36000040):
            with self.subTest(word=hex(word)):
                self.assertEqual(checkpoint.branch_target(word, pc), pc + 8)
        self.assertEqual(checkpoint.branch_target(0x17FFFFFF, pc), pc - 4)
        self.assertEqual(checkpoint.branch_target(0x97FFFFFF, pc), pc - 4)
        self.assertIsNone(checkpoint.branch_target(0xD503201F, pc))

    def test_interior_entry_from_outside_is_rejected_in_va_space(self):
        base = 0xFFFF800080000000
        image = bytearray(struct.pack('<I', 0xD503201F) * 16)
        struct.pack_into('<I', image, 0, 0x94000009)
        window = (base + 32, base + 48)
        self.assertEqual(checkpoint.incoming_branches(image, [(0, 64)], base, window), [(base, base + 36)])
        struct.pack_into('<I', image, 0, 0x14000008)  # entry is preserved
        struct.pack_into('<I', image, 32, 0x14000001)  # overwritten source is gone
        self.assertEqual(checkpoint.incoming_branches(image, [(0, 64)], base, window), [])
        struct.pack_into('<I', image, 60, 0x14000000 | (-5 & 0x03FFFFFF))
        self.assertEqual(checkpoint.incoming_branches(image, [(0, 64)], base, window), [(base + 60, base + 40)])

    def test_compact_poll_preserves_timer_and_terminal_reset(self):
        core = bytearray(range(76))
        struct.pack_into('<III', core, 44, 0x54000062, 0xD503203F, 0x17FFFFFA)
        compact = checkpoint.compact_core(bytes(core))
        self.assertEqual(len(compact), 68)
        self.assertEqual(compact[:44], core[:44])
        self.assertEqual(compact[48:], core[56:])
        word = struct.unpack_from('<I', compact, 44)[0]
        self.assertEqual(word & 15, 3)  # unsigned LO is the complement of HS
        self.assertEqual(checkpoint.branch_target(word, 44), 28)
        self.assertEqual(checkpoint.branch_target(0x54000062, 44), 56)
        self.assertEqual(checkpoint.branch_target(0x17FFFFFA, 52), 28)
        for elapsed in (0, 1, 8, 0xFFFFFFFFFFFFFFFF):
            for limit in (1, 8, 0xFFFFFFFFFFFFFFFF):
                self.assertEqual(not elapsed >= limit, elapsed < limit)
        for bad in (bytes(76), bytes(68)):
            with self.assertRaises(ValueError):
                checkpoint.compact_core(bad)

    def test_compact_window_preserves_real_kernel_init_branch_landing(self):
        base = 0xFFFF8000810C2030
        image = bytearray(struct.pack('<I', 0xD503201F) * 100)
        struct.pack_into('<I', image, 0x16C, 0x17FFFFB7)
        ranges = [(0, len(image))]
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 80)),
                         [(base + 0x16C, base + 0x48)])
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 72)), [])

    def test_literal_reference_collection_keeps_each_image_address(self):
        bundle, frozen = bytearray(128), bytearray(128)
        struct.pack_into('<I', bundle, 0, 0x91010000)
        struct.pack_into('<I', frozen, 0, 0x91012000)
        text = b'/dev/console\0'
        bundle[64:64 + len(text)] = text
        frozen[72:72 + len(text)] = text
        refs = checkpoint.literal_ref_pair(bundle, frozen, 0, 0)
        self.assertEqual(refs['bundle']['offset'], '0x40')
        self.assertEqual(refs['frozen']['offset'], '0x48')
        self.assertEqual(refs['bundle']['bytes_hex'], text.hex())
        self.assertEqual(refs['frozen']['bytes_hex'], text.hex())

    def test_adrp_add_literal_collection_derives_each_linked_address(self):
        bundle, frozen = bytearray(512), bytearray(512)
        struct.pack_into('<II', bundle, 0x100, 0x90000000, 0x91010000)
        struct.pack_into('<II', frozen, 0x100, 0x90000000, 0x91012000)
        bundle[0x40:0x45] = b'core\0'
        frozen[0x48:0x4d] = b'core\0'
        refs = checkpoint.adrp_add_literal_ref_pair(
            bundle, frozen, 0x10000000, 0x100, 0x104)
        self.assertEqual(refs['bundle']['offset'], '0x40')
        self.assertEqual(refs['frozen']['offset'], '0x48')
        self.assertEqual(refs['bundle']['bytes_hex'], b'core\0'.hex())
        self.assertEqual(refs['frozen']['bytes_hex'], b'core\0'.hex())

    def test_console_literal_deltas_are_two_exact_source_references_only(self):
        bundle = bytearray(72)
        struct.pack_into('<II', bundle, 16, 0xD0FFF460, 0x912C3000)
        struct.pack_into('<II', bundle, 44, 0x90FFF540, 0x91022000)
        frozen = bytearray(bundle)
        struct.pack_into('<I', frozen, 20, 0x912C5000)
        struct.pack_into('<I', frozen, 48, 0x91024000)
        refs = {}
        for tag, a, b, text in (
                ('path', '0x19beb0c', '0x19beb14', b'/dev/console\0'),
                ('warning', '0x19d8088', '0x19d8090',
                 b'\x013Warning: unable to open an initial console.\n\0')):
            refs[tag] = {'bundle': {'offset': a, 'bytes_hex': text.hex()},
                         'frozen': {'offset': b, 'bytes_hex': text.hex()}}
        checkpoint.gate_console_literal_deltas(bundle, frozen, refs)
        for off in (0, 16, 20, 32, 44, 48, 52, 68):
            changed = bytearray(frozen)
            changed[off] ^= 1
            with self.subTest(offset=off), self.assertRaises(ValueError):
                checkpoint.gate_console_literal_deltas(bundle, changed, refs)
        for tag in refs:
            for name in refs[tag]:
                for key in ('offset', 'bytes_hex'):
                    changed = {t: {n: dict(v) for n, v in images.items()} for t, images in refs.items()}
                    changed[tag][name][key] = 'wrong'
                    with self.subTest(tag=tag, image=name, field=key), self.assertRaises(ValueError):
                        checkpoint.gate_console_literal_deltas(bundle, frozen, changed)

    def test_initcall_literal_delta_requires_exact_code_and_source_text(self):
        bundle = bytearray(72)
        struct.pack_into('<II', bundle, 36, 0xB0FFF061, 0x913B7421)
        frozen = bytearray(bundle)
        struct.pack_into('<I', frozen, 40, 0x913B9421)
        text = b'arm64/fpsimd:dead\0'.hex()
        refs = {'bundle': {'offset': '0x1940edd', 'bytes_hex': text},
                'frozen': {'offset': '0x1940ee5', 'bytes_hex': text}}
        checkpoint.gate_initcall_literal_delta(bundle, frozen, refs)
        for off in (0, 36, 40, 44, 68):
            changed = bytearray(frozen)
            changed[off] ^= 1
            with self.subTest(offset=off), self.assertRaises(ValueError):
                checkpoint.gate_initcall_literal_delta(bundle, changed, refs)
        for name in refs:
            for key in ('offset', 'bytes_hex'):
                changed = {n: dict(value) for n, value in refs.items()}
                changed[name][key] = 'wrong'
                with self.subTest(image=name, field=key), self.assertRaises(ValueError):
                    checkpoint.gate_initcall_literal_delta(bundle, frozen, changed)

    def test_smp_literal_delta_requires_exact_code_and_source_text(self):
        bundle = bytearray(72)
        struct.pack_into('<III', bundle, 24, 0xD0FFF740, 0x912DC000, 0x97D5CD80)
        frozen = bytearray(bundle)
        struct.pack_into('<I', frozen, 28, 0x912DE000)
        text = b'\x016smp: Bringing up secondary CPUs ...\n\0'.hex()
        refs = {'bundle': {'offset': '0x1a30b70', 'bytes_hex': text},
                'frozen': {'offset': '0x1a30b78', 'bytes_hex': text}}
        checkpoint.gate_smp_literal_delta(bundle, frozen, refs)
        for off in (0, 4, 24, 28, 32, 68):
            changed = bytearray(frozen)
            changed[off] ^= 1
            with self.subTest(offset=off), self.assertRaises(ValueError):
                checkpoint.gate_smp_literal_delta(bundle, changed, refs)
        for name in refs:
            for key in ('offset', 'bytes_hex'):
                changed = {n: dict(value) for n, value in refs.items()}
                changed[name][key] = 'wrong'
                with self.subTest(image=name, field=key), self.assertRaises(ValueError):
                    checkpoint.gate_smp_literal_delta(bundle, frozen, changed)
        with self.assertRaises(ValueError):
            checkpoint.gate_smp_literal_delta(bundle[:-4], frozen[:-4], refs)

    def test_relr_advances_all_63_bitmap_positions(self):
        base = 0xFFFF800081234000
        data = struct.pack('<QQQ', base, 3, 3)
        self.assertEqual(checkpoint.decode_relr(data), [base, base + 8, base + 512])
        self.assertEqual(checkpoint.decode_relr(struct.pack('<QQQ', base, 1, 3)), [base, base + 512])
        with self.assertRaises(ValueError):
            checkpoint.decode_relr(struct.pack('<Q', 3))
        with self.assertRaises(ValueError):
            checkpoint.decode_relr(b'bad')

    def test_initcall_boundary_resolves_unique_prel32_target(self):
        base = 0x10000000
        target = 0x10000100
        data = bytearray(0x200)
        for index, resolved in enumerate((base + 0x80, target, base + 0x180)):
            struct.pack_into('<i', data, index * 4, resolved - (base + index * 4))
        nm = '\n'.join((
            f'{base:016x} T _text',
            f'{base:016x} d __initcall_start',
            f'{base + 4:016x} d __initcall1_start',
            f'{base + 12:016x} d __initcall_end',
            f'{target:016x} t first_core_init',
            f'{target + 0x80:016x} t next_function',
        ))
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'vmlinux'
            image.write_bytes(data)
            result = checkpoint.resolve_initcall_boundary(
                image, [{'name': '.init.data', 'vma': base, 'size': len(data), 'file_off': 0}], nm,
                '__initcall1_start')
        self.assertEqual(result['target_va'], target)
        self.assertEqual(result['target_aliases'], ['first_core_init'])
        self.assertEqual(result['table_entries_checked'], 3)
        duplicate = bytearray(data)
        struct.pack_into('<i', duplicate, 8, target - (base + 8))
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'vmlinux'
            image.write_bytes(duplicate)
            with self.assertRaises(ValueError):
                checkpoint.resolve_initcall_boundary(
                    image, [{'name': '.init.data', 'vma': base, 'size': len(data), 'file_off': 0}], nm,
                    '__initcall1_start')

    def test_core_checkpoint_negative_fixtures(self):
        valid = {
            'checkpoint_point': 'FIRST_POSTCORE_INITCALL_EXACT_ENTRY',
            'boundary': '__initcall2_start', 'target_derivation': 'TABLE_ENTRY_DECODE',
            'entry_encoding': 'PREL32', 'cross_function_overwrite': False,
            'function_range_safe': True, 'function_size': 60, 'probe_size': 60,
            'incoming_interior_branches': 0, 'backedge_conflict': False,
            'runtime_rewrite_conflict': False,
            'literal_delta': 'EXACT_OR_INDEPENDENTLY_PROVEN',
            'pair_diff': 'DELAY_CONSTANT_ONLY', 'timer': 'CNTPCT',
            'psci_fid': '0x84000009', 'timer_algorithm_changed': False,
            'prior_pure_probe': False, 'prior_console_probe': False,
            'rt_d_sha256': '4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327',
            'init_changed': False, 'private_pack': False, 'device_operation': False,
        }
        checkpoint.gate_core_checkpoint_design(valid)
        postcore = dict(valid, checkpoint_point='FIRST_ARCH_INITCALL_EXACT_ENTRY',
                        boundary='__initcall3_start')
        checkpoint.gate_postcore_checkpoint_design(postcore)
        arch = dict(valid, checkpoint_point='FIRST_SUBSYS_INITCALL_EXACT_ENTRY',
                    boundary='__initcall4_start', reuse_core_narrow_gate=False,
                    reuse_postcore_probe_window=False, prior_core_probe=False,
                    prior_postcore_probe=False, copied_postcore_probe=False)
        checkpoint.gate_arch_checkpoint_design(arch)
        with self.assertRaises(ValueError):
            checkpoint.gate_postcore_checkpoint_design(valid)
        with self.assertRaises(ValueError):
            checkpoint.gate_core_checkpoint_design(postcore)
        with self.assertRaises(ValueError):
            checkpoint.gate_arch_checkpoint_design(postcore)
        with self.assertRaises(ValueError):
            checkpoint.gate_arch_checkpoint_design(valid)
        fixtures = {
            'shared_loop': ('checkpoint_point', 'SHARED_DO_INITCALLS_LOOP'),
            'wrong_boundary': ('boundary', '__initcall1_start'),
            'wrong_target': ('checkpoint_point', 'WRONG_POSTCORE_TARGET'),
            'symbol_order_guess': ('target_derivation', 'SYSTEM_MAP_ORDER_GUESS'),
            'before_entry': ('checkpoint_point', 'BEFORE_FIRST_POSTCORE_ENTRY'),
            'cross_function': ('cross_function_overwrite', True),
            'short_function': ('function_size', 56),
            'incoming_branch': ('incoming_interior_branches', 1),
            'backedge': ('backedge_conflict', True),
            'runtime_rewrite': ('runtime_rewrite_conflict', True),
            'unproved_literal_delta': ('literal_delta', 'UNPROVEN'),
            'extra_pair_diff': ('pair_diff', 'EXTRA_BYTES'),
            'timer_change': ('timer_algorithm_changed', True),
            'psci_change': ('psci_fid', '0x84000008'),
            'pure_probe_remains': ('prior_pure_probe', True),
            'console_probe_remains': ('prior_console_probe', True),
            'rt_d_changed': ('rt_d_sha256', '0' * 64),
            'init_changed': ('init_changed', True),
            'private_pack': ('private_pack', True),
            'device_operation': ('device_operation', True),
        }
        for name, (key, value) in fixtures.items():
            bad = dict(valid)
            bad[key] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_core_checkpoint_design(bad)
            postcore_bad = dict(postcore)
            postcore_bad[key] = value
            with self.subTest(name='postcore_' + name), self.assertRaises(ValueError):
                checkpoint.gate_postcore_checkpoint_design(postcore_bad)
            arch_bad = dict(arch)
            arch_bad[key] = value
            with self.subTest(name='arch_' + name), self.assertRaises(ValueError):
                checkpoint.gate_arch_checkpoint_design(arch_bad)
        arch_fixtures = {
            'use_initcall3_start': ('boundary', '__initcall3_start'),
            'shared_do_initcalls': ('checkpoint_point', 'SHARED_DO_INITCALLS_LOOP'),
            'wrong_first_subsys_target': ('checkpoint_point', 'WRONG_FIRST_SUBSYS_TARGET'),
            'system_map_guess': ('target_derivation', 'SYSTEM_MAP_ORDER_GUESS'),
            'before_entry': ('checkpoint_point', 'BEFORE_FIRST_SUBSYS_ENTRY'),
            'reuse_core_narrow_gate': ('reuse_core_narrow_gate', True),
            'reuse_postcore_probe': ('reuse_postcore_probe_window', True),
            'copied_postcore_probe': ('copied_postcore_probe', True),
            'prior_core_probe': ('prior_core_probe', True),
            'prior_postcore_probe': ('prior_postcore_probe', True),
        }
        for name, (key, value) in arch_fixtures.items():
            bad = dict(arch)
            bad[key] = value
            with self.subTest(name='arch_extra_' + name), self.assertRaises(ValueError):
                checkpoint.gate_arch_checkpoint_design(bad)

    def test_arch_checkpoint_negative_fixtures(self):
        arch = {
            'checkpoint_point': 'FIRST_SUBSYS_INITCALL_EXACT_ENTRY',
            'boundary': '__initcall4_start', 'target_derivation': 'TABLE_ENTRY_DECODE',
            'entry_encoding': 'PREL32', 'cross_function_overwrite': False,
            'function_range_safe': True, 'function_size': 60, 'probe_size': 60,
            'incoming_interior_branches': 0, 'backedge_conflict': False,
            'runtime_rewrite_conflict': False,
            'literal_delta': 'EXACT_OR_INDEPENDENTLY_PROVEN',
            'pair_diff': 'DELAY_CONSTANT_ONLY', 'timer': 'CNTPCT',
            'psci_fid': '0x84000009', 'timer_algorithm_changed': False,
            'prior_pure_probe': False, 'prior_console_probe': False,
            'reuse_core_narrow_gate': False, 'reuse_postcore_probe_window': False,
            'prior_core_probe': False, 'prior_postcore_probe': False,
            'copied_postcore_probe': False,
            'rt_d_sha256': '4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327',
            'init_changed': False, 'private_pack': False, 'device_operation': False,
        }
        checkpoint.gate_arch_checkpoint_design(arch)
        with self.assertRaises(ValueError):
            checkpoint.gate_arch_checkpoint_design(dict(arch, boundary='__initcall3_start'))
        with self.assertRaises(ValueError):
            checkpoint.gate_arch_checkpoint_design(dict(arch, function_size=56))
        with self.assertRaises(ValueError):
            checkpoint.gate_core_checkpoint_design(arch)

    def test_subsys_checkpoint_negative_fixtures(self):
        subsys = {
            'checkpoint_point': 'FIRST_FS_INITCALL_EXACT_ENTRY',
            'boundary': '__initcall5_start', 'target_derivation': 'TABLE_ENTRY_DECODE',
            'entry_encoding': 'PREL32', 'cross_function_overwrite': False,
            'function_range_safe': True, 'function_size': 56, 'probe_size': 56,
            'incoming_interior_branches': 0, 'backedge_conflict': False,
            'runtime_rewrite_conflict': False, 'cfg_closure_proven': True,
            'window_derivation': 'TARGET_CFG', 'reuse_arch_160b': False,
            'copied_arch_probe': False, 'prior_arch_probe': False,
            'prior_core_probe': False, 'prior_postcore_probe': False,
            'probe_architecture': 'INLINE_56B_TOTAL', 'diagnostic_core_size': 52,
            'paciasp_preserved': True, 'cntpct_elapsed': True,
            'subsys_60b_inline_rejected': True, 'prel32_target_unchanged': True,
            'fixed_iteration_delay': False,
            'literal_delta': 'EXACT_OR_INDEPENDENTLY_PROVEN',
            'pair_diff': 'DELAY_CONSTANT_ONLY', 'timer': 'CNTPCT',
            'psci_fid': '0x84000009', 'timer_algorithm_changed': False,
            'prior_pure_probe': False, 'prior_console_probe': False,
            'rt_d_sha256': '4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327',
            'init_changed': False, 'private_pack': False, 'device_operation': False,
        }
        checkpoint.gate_subsys_checkpoint_design(subsys)
        with self.assertRaises(ValueError):
            checkpoint.gate_subsys_checkpoint_design(dict(subsys, boundary='__initcall4_start'))
        with self.assertRaises(ValueError):
            checkpoint.gate_arch_checkpoint_design(subsys)
        with self.assertRaises(ValueError):
            checkpoint.gate_subsys_checkpoint_design(dict(subsys, function_size=52))
        fixtures = {
            'use_initcall4_start': ('boundary', '__initcall4_start'),
            'shared_loop': ('checkpoint_point', 'SHARED_DO_INITCALLS_LOOP'),
            'wrong_first_fs_target': ('checkpoint_point', 'WRONG_FIRST_FS_TARGET'),
            'symbol_order_guess': ('target_derivation', 'SYSTEM_MAP_ORDER_GUESS'),
            'before_entry': ('checkpoint_point', 'BEFORE_FIRST_FS_ENTRY'),
            'cross_function': ('cross_function_overwrite', True),
            'short_function': ('function_size', 52),
            'sixty_byte_inline': ('subsys_60b_inline_rejected', False),
            'drop_paciasp': ('paciasp_preserved', False),
            'core_53b': ('diagnostic_core_size', 53),
            'fixed_iteration': ('fixed_iteration_delay', True),
            'prel32_retarget': ('prel32_target_unchanged', False),
            'trampoline_instead': ('probe_architecture', 'ENTRY_TRAMPOLINE'),
            'blind_reuse_arch_160b': ('reuse_arch_160b', True),
            'copied_arch_window': ('window_derivation', 'COPIED_ARCH_160B'),
            'copied_arch_probe': ('copied_arch_probe', True),
            'incoming_branch': ('incoming_interior_branches', 1),
            'backedge_source_live': ('backedge_conflict', True),
            'cfg_not_closed': ('cfg_closure_proven', False),
            'runtime_rewrite': ('runtime_rewrite_conflict', True),
            'unproved_literal_delta': ('literal_delta', 'UNPROVEN'),
            'extra_pair_diff': ('pair_diff', 'EXTRA_BYTES'),
            'timer_change': ('timer_algorithm_changed', True),
            'psci_change': ('psci_fid', '0x84000008'),
            'arch_probe_remains': ('prior_arch_probe', True),
            'postcore_probe_remains': ('prior_postcore_probe', True),
            'core_probe_remains': ('prior_core_probe', True),
            'pure_probe_remains': ('prior_pure_probe', True),
            'console_probe_remains': ('prior_console_probe', True),
            'rt_d_changed': ('rt_d_sha256', '0' * 64),
            'init_changed': ('init_changed', True),
            'private_pack': ('private_pack', True),
            'device_operation': ('device_operation', True),
        }
        for name, (key, value) in fixtures.items():
            bad = dict(subsys)
            bad[key] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_subsys_checkpoint_design(bad)
        self.assertNotIn('subsys_complete', checkpoint.EXPANDED_WINDOWS)
        self.assertIn('subsys_complete', checkpoint.CFG_DERIVED_WINDOWS)

    def test_subsys_window_is_derived_from_target_cfg_not_arch_160b(self):
        base = 0xFFFF800081B00000
        self.assertEqual(checkpoint.derive_inline_window(base, 188, [], 60), 60)
        self.assertEqual(
            checkpoint.derive_inline_window(base, 188, [[hex(base + 0x9C), hex(base + 0x38)]], 60),
            0xA0)
        self.assertEqual(checkpoint.derive_inline_window(base, 56, [], 56), 56)
        with self.assertRaises(ValueError):
            checkpoint.derive_inline_window(base, 56, [], 60)
        with self.assertRaises(ValueError):
            checkpoint.derive_inline_window(base, 56, [], 57)
        with self.assertRaises(ValueError):
            checkpoint.derive_inline_window(base, 80, [[hex(base + 0x9C), hex(base + 0x38)]], 60)
        report = checkpoint.cfg_closure_report(
            base, 188, 0xA0,
            {'internal_branches': [[hex(base + 0x9C), hex(base + 0x38)]],
             'back_edges': [[hex(base + 0x9C), hex(base + 0x38)]],
             'incoming_window_interior': []})
        self.assertTrue(report['cfg_closure_proven'])
        self.assertEqual(report['window_derivation'], 'TARGET_CFG')
        self.assertEqual(report['candidate_window_length'], 0xA0)
        live = checkpoint.cfg_closure_report(
            base, 188, 60,
            {'internal_branches': [[hex(base + 0x9C), hex(base + 0x38)]],
             'back_edges': [[hex(base + 0x9C), hex(base + 0x38)]],
             'incoming_window_interior': [[hex(base + 0x9C), hex(base + 0x38)]]})
        self.assertFalse(live['cfg_closure_proven'])
        self.assertEqual(live['surviving_sources'][0]['source_offset'], '0x9c')

    def test_subsys_fs_literal_delta_requires_exact_debug_enabled_string(self):
        bundle = bytearray(56)
        struct.pack_into('<II', bundle, 12, 0x9000D0E0, 0x91019000)
        frozen = bytearray(bundle)
        struct.pack_into('<I', frozen, 16, 0x9101B000)
        text = b'debug_enabled\0'.hex()
        refs = {'bundle': {'offset': '0x100', 'bytes_hex': text},
                'frozen': {'offset': '0x108', 'bytes_hex': text}}
        checkpoint.gate_subsys_fs_literal_delta(bundle, frozen, refs)
        for off in (0, 12, 16, 20, 52):
            changed = bytearray(frozen)
            changed[off] ^= 1
            with self.subTest(offset=off), self.assertRaises(ValueError):
                checkpoint.gate_subsys_fs_literal_delta(bundle, changed, refs)
        wrong = {'bundle': {'offset': '0x100', 'bytes_hex': text},
                 'frozen': {'offset': '0x108', 'bytes_hex': b'nope\0'.hex()}}
        with self.assertRaises(ValueError):
            checkpoint.gate_subsys_fs_literal_delta(bundle, frozen, wrong)

    def test_subsys52_core_is_proven_56_without_daifset(self):
        old = struct.pack('<14I', *checkpoint.ULTRACOMPACT_WORDS)
        new = struct.pack('<13I', *checkpoint.SUBSYS52_WORDS)
        self.assertEqual(checkpoint.ultracompact_core(old), old)
        self.assertEqual(checkpoint.subsys52_core(new), new)
        checkpoint.gate_subsys52_core_equivalence(old, new)
        self.assertEqual(old[4:], new)
        self.assertNotIn('subsys_complete', checkpoint.ULTRACOMPACT_SYMBOLS)
        self.assertIn('subsys_complete', checkpoint.SUBSYS52_SYMBOLS)
        short = checkpoint.delay_core(new, 1)
        self.assertEqual([i for i, (a, b) in enumerate(zip(new, short)) if a != b], [5, 6])
        self.assertEqual(struct.unpack_from('<I', short, 4)[0], 0xD340FD2A)
        with self.assertRaises(ValueError):
            checkpoint.subsys52_core(old)
        with self.assertRaises(ValueError):
            checkpoint.gate_subsys52_core_equivalence(old, old[8:])

    def test_ultracompact_core_and_literal_delta_are_exact(self):
        words = (0xD5034FDF, 0xD53BE009, 0xD37DF12A, 0xD53BE02B,
                 0xD5033FDF, 0xD53BE02C, 0xCB0B018D, 0xEB0A01BF,
                 0x54FFFF83, 0x52800120, 0x72B08000, 0xD4000003,
                 0xD503205F, 0x17FFFFFF)
        core = struct.pack('<14I', *words)
        self.assertEqual(checkpoint.ultracompact_core(core), core)
        short = checkpoint.delay_core(core, 1)
        self.assertEqual([i for i, (a, b) in enumerate(zip(core, short)) if a != b], [9, 10])
        self.assertEqual(struct.unpack_from('<I', short, 8)[0], 0xD340FD2A)
        bundle = bytearray(60)
        struct.pack_into('<II', bundle, 12, 0x90FFF781, 0x91329421)
        frozen = bytearray(bundle)
        struct.pack_into('<I', frozen, 16, 0x9132B421)
        text = b'arm64/debug_monitors:starting\0'.hex()
        refs = {'bundle': {'offset': '0x100', 'bytes_hex': text},
                'frozen': {'offset': '0x108', 'bytes_hex': text}}
        checkpoint.gate_core_initcall_literal_delta(bundle, frozen, refs)
        for off in (0, 12, 16, 20, 56):
            changed = bytearray(frozen)
            changed[off] ^= 1
            with self.subTest(offset=off), self.assertRaises(ValueError):
                checkpoint.gate_core_initcall_literal_delta(bundle, changed, refs)

    def test_pair_changes_only_delay_immediate(self):
        core = bytearray(76)
        struct.pack_into('<I', core, 12, 0xD280010A)
        self.assertEqual(checkpoint.delay_core(bytes(core), 8), core)
        short = checkpoint.delay_core(bytes(core), 1)
        self.assertEqual([i for i, (a, b) in enumerate(zip(core, short)) if a != b], [12, 13])
        self.assertEqual(struct.unpack_from('<I', short, 12)[0], 0xD280002A)
        for bad in (0, 2, 24):
            with self.assertRaises(ValueError):
                checkpoint.delay_core(bytes(core), bad)
        with self.assertRaises(ValueError):
            checkpoint.delay_core(bytes(76), 1)

    def test_arch_prefix_covers_topology_backedge_without_ignoring_external_entries(self):
        base = 0xFFFF800081B346FC
        image = bytearray(struct.pack('<I', 0xD503201F) * 50)
        struct.pack_into('<I', image, 0x9C, 0x17FFFFE7)
        ranges = [(0, len(image))]
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 60)),
                         [(base + 0x9C, base + 0x38)])
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 160)), [])
        struct.pack_into('<I', image, 0xA4, 0x14000000 | ((0x38 - 0xA4) // 4 & 0x3FFFFFF))
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 160)),
                         [(base + 0xA4, base + 0x38)])
        probe = bytes(60)
        self.assertEqual(len(checkpoint.pad_probe(probe, 160)), 160)

    def test_initcall_prefix_covers_backedge_without_ignoring_external_entries(self):
        base = 0xFFFF800081B311D0
        image = bytearray(struct.pack('<I', 0xD503201F) * 40)
        struct.pack_into('<I', image, 0x5C, 0x54FFFF01)
        ranges = [(0, len(image))]
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 72)),
                         [(base + 0x5C, base + 0x3C)])
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 96)), [])
        struct.pack_into('<I', image, 0x98, 0x14000000 | ((0x3C - 0x98) // 4 & 0x3FFFFFF))
        self.assertEqual(checkpoint.incoming_branches(image, ranges, base, (base, base + 96)),
                         [(base + 0x98, base + 0x3C)])
        probe = bytes(72)
        self.assertEqual(checkpoint.pad_probe(probe, 96), probe + struct.pack('<I', 0xD503201F) * 6)
        for bad in (68, 73):
            with self.assertRaises(ValueError):
                checkpoint.pad_probe(probe, bad)
        with self.assertRaises(ValueError):
            checkpoint.pad_probe(bytes(73), 96)


    def test_fs_complete_core_prefers_proven_56_when_function_fits(self):
        old = struct.pack('<14I', *checkpoint.ULTRACOMPACT_WORDS)
        new = struct.pack('<13I', *checkpoint.SUBSYS52_WORDS)
        core, arch, rejected = checkpoint.select_fs_complete_core(188, old, new)
        self.assertEqual(core, old)
        self.assertEqual(arch, 'INLINE_PACIASP_PLUS_56B_ULTRACOMPACT')
        self.assertFalse(rejected)
        core, arch, rejected = checkpoint.select_fs_complete_core(56, old, new)
        self.assertEqual(core, new)
        self.assertEqual(arch, 'INLINE_PACIASP_PLUS_52B_NO_DAIFSET')
        self.assertTrue(rejected)
        self.assertEqual(checkpoint.select_fs_complete_core(60, old, new)[0], old)
        core, arch, rejected = checkpoint.select_fs_complete_core(48, old, new)
        self.assertEqual(core, new)
        self.assertEqual(arch, 'ENTRY_TRAMPOLINE')
        self.assertTrue(rejected)
        core, arch, rejected = checkpoint.select_fs_complete_core(52, old, new)
        self.assertEqual(core, new)
        self.assertEqual(arch, 'ENTRY_TRAMPOLINE')
        with self.assertRaises(ValueError):
            checkpoint.select_fs_complete_core(4, old, new)
        self.assertIn('fs_complete', checkpoint.CFG_DERIVED_WINDOWS)
        self.assertNotIn('fs_complete', checkpoint.EXPANDED_WINDOWS)
        self.assertNotIn('fs_complete', checkpoint.ULTRACOMPACT_SYMBOLS)
        self.assertNotIn('fs_complete', checkpoint.SUBSYS52_SYMBOLS)
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_complete'], '__initcall6_start')
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_trampoline_control'], '__initcall5_start')
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_midpoint'], '__initcall5_start')
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_upper_half'], '__initcall5_start')
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_post39'], '__initcall5_start')
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_post46'], '__initcall5_start')
        self.assertEqual(checkpoint.INITCALL_BOUNDARIES['fs_post49'], '__initcall5_start')
        self.assertIn('fs_post49', checkpoint.PROOF_BOUNDARIES)
        self.assertEqual(checkpoint.FS_SPAN_SYMBOLS,
                         frozenset({'fs_complete', 'fs_trampoline_control', 'fs_midpoint',
                                    'fs_upper_half', 'fs_post39', 'fs_post46', 'fs_post49'}))

    def test_fs_complete_literal_delta_accepts_same_string_add_only(self):
        image, frozen = bytearray(512), bytearray(512)
        struct.pack_into('<II', image, 0x100, 0x90000000, 0x91010000)
        struct.pack_into('<II', frozen, 0x100, 0x90000000, 0x91012000)
        image[0x40:0x45] = b'core\0'
        frozen[0x48:0x4d] = b'core\0'
        refs = checkpoint.prove_fs_complete_window_literals(image, frozen, 0x10000000, 0x100, 8)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['bundle']['text'], 'core')
        self.assertEqual(refs[0]['frozen']['text'], 'core')
        self.assertEqual(refs[0]['layout_delta'], 8)
        mutated = bytearray(frozen)
        struct.pack_into('<I', mutated, 0x100, 0x14000001)
        with self.assertRaises(ValueError):
            checkpoint.prove_fs_complete_window_literals(image, mutated, 0x10000000, 0x100, 8)
        wrong = bytearray(frozen)
        wrong[0x48:0x4d] = b'nope\0'
        with self.assertRaises(ValueError):
            checkpoint.prove_fs_complete_window_literals(image, wrong, 0x10000000, 0x100, 8)

    def _write_fake_linux(self, root, linker_order=None, levels=None):
        order = linker_order or ['0', '1', '2', '3', '4', '5', 'rootfs', '6', '7']
        level_syms = levels or ['__initcall0_start', '__initcall1_start', '__initcall2_start',
                                '__initcall3_start', '__initcall4_start', '__initcall5_start',
                                '__initcall6_start', '__initcall7_start', '__initcall_end']
        (root / 'init').mkdir(parents=True, exist_ok=True)
        (root / 'include/linux').mkdir(parents=True, exist_ok=True)
        (root / 'include/asm-generic').mkdir(parents=True, exist_ok=True)
        (root / 'arch/arm64/kernel').mkdir(parents=True, exist_ok=True)
        nl, tab, cont = chr(10), chr(9), ' ' + chr(92) + chr(10)
        calls = ''.join(tab + tab + 'INIT_CALLS_LEVEL(' + item + ')' + cont for item in order)
        lds = (
            '#define INIT_CALLS_LEVEL(level)' + cont +
            tab + tab + '__initcall##level##_start = .;' + cont +
            tab + tab + 'KEEP(*(.initcall##level##.init))' + cont +
            tab + tab + 'KEEP(*(.initcall##level##s.init))' + cont + nl +
            '#define INIT_CALLS' + cont +
            tab + tab + '__initcall_start = .;' + cont +
            tab + tab + 'KEEP(*(.initcallearly.init))' + cont +
            calls +
            tab + tab + '__initcall_end = .;' + nl
        )
        (root / 'include/asm-generic/vmlinux.lds.h').write_text(lds)
        (root / 'include/linux/init.h').write_text(nl.join([
            '#ifdef CONFIG_HAVE_ARCH_PREL32_RELOCATIONS',
            'typedef int initcall_entry_t;',
            'static inline initcall_t initcall_from_entry(initcall_entry_t *entry)',
            '{ return offset_to_ptr(entry); }',
            'asm(".long " __stringify(__stub) " - .");',
            '#endif',
            'extern initcall_entry_t __initcall0_start[];',
            'extern initcall_entry_t __initcall5_start[];',
            'extern initcall_entry_t __initcall6_start[];',
            'extern initcall_entry_t __initcall7_start[];',
            'void __init init_rootfs(void);',
            '#define arch_initcall(fn)\t\t__define_initcall(fn, 3)',
            '#define subsys_initcall(fn)\t\t__define_initcall(fn, 4)',
            '#define fs_initcall(fn)\t\t\t__define_initcall(fn, 5)',
            '#define fs_initcall_sync(fn)\t\t__define_initcall(fn, 5s)',
            '#define rootfs_initcall(fn)\t\t__define_initcall(fn, rootfs)',
            '#define device_initcall(fn)\t\t__define_initcall(fn, 6)',
            '#define __initcall(fn) device_initcall(fn)',
            ''
        ]).replace('\\t', tab))
        (root / 'init/main.c').write_text(
            'static initcall_entry_t *initcall_levels[] __initdata = {' + nl +
            ''.join(tab + name + ',' + nl for name in level_syms) +
            '};' + nl +
            'static const char *initcall_level_names[] __initdata = {' + nl +
            tab + '"pure",' + nl + tab + '"core",' + nl + tab + '"postcore",' + nl +
            tab + '"arch",' + nl + tab + '"subsys",' + nl + tab + '"fs",' + nl +
            tab + '"device",' + nl + tab + '"late",' + nl + '};' + nl +
            'static void __init do_initcall_level(int level, char *command_line)' + nl +
            '{' + nl + tab + 'initcall_entry_t *fn;' + nl +
            tab + 'for (fn = initcall_levels[level]; fn < initcall_levels[level+1]; fn++)' + nl +
            tab + tab + 'do_one_initcall(initcall_from_entry(fn));' + nl + '}' + nl +
            'static void __init do_initcalls(void)' + nl +
            '{' + nl + tab + 'int level;' + nl +
            tab + 'for (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++) {' + nl +
            tab + tab + 'do_initcall_level(level, command_line);' + nl + tab + '}' + nl + '}' + nl)
        (root / 'init/initramfs.c').write_text('rootfs_initcall(populate_rootfs);' + nl)
        (root / 'arch/arm64/kernel/vmlinux.lds.S').write_text(tab + tab + 'INIT_CALLS' + nl)
        (root / 'arch/arm64/Kconfig').write_text(tab + 'select HAVE_ARCH_PREL32_RELOCATIONS' + nl)

    def test_fs_source_semantics_include_rootfs_in_level5(self):
        with tempfile.TemporaryDirectory() as tmp:
            linux = Path(tmp)
            self._write_fake_linux(linux)
            result = checkpoint.audit_initcall_source(linux)
            self.assertEqual(result['fs'], '__initcall5_start..__initcall6_start')
            self.assertEqual(result['device'], '__initcall6_start..__initcall7_start')
            self.assertEqual(result['fs_next_linker_boundary'], '__initcallrootfs_start')
            self.assertEqual(result['rootfs_start_symbol'], '__initcallrootfs_start')
            self.assertEqual(result['do_initcall_level_5_begin'], '__initcall5_start')
            self.assertEqual(result['do_initcall_level_5_end'], '__initcall6_start')
            self.assertFalse(result['rootfs_has_separate_runtime_pass'])
            self.assertTrue(result['rootfs_included_in_level5_traversal'])
            self.assertTrue(result['rootfs_start_is_marker_only'])
            self.assertTrue(result['first_device_entry_implies_fs_complete'])
            self.assertEqual(result['fs_complete_causal_boundary'], '__initcall6_start')
            self.assertEqual(result['linker_order'],
                             ['0', '1', '2', '3', '4', '5', 'rootfs', '6', '7'])
            self._write_fake_linux(linux, linker_order=['0', '1', '2', '3', '4', '5', '6', '7'])
            with self.assertRaises(ValueError):
                checkpoint.audit_initcall_source(linux)
            self._write_fake_linux(linux, levels=['__initcall0_start', '__initcall1_start',
                                                  '__initcall2_start', '__initcall3_start',
                                                  '__initcall4_start', '__initcall5_start',
                                                  '__initcallrootfs_start', '__initcall6_start',
                                                  '__initcall7_start', '__initcall_end'])
            with self.assertRaises(ValueError):
                checkpoint.audit_initcall_source(linux)

    def test_fs_checkpoint_negative_fixtures(self):
        fs = {
            'checkpoint_point': 'FIRST_DEVICE_INITCALL_EXACT_ENTRY',
            'boundary': '__initcall6_start', 'target_derivation': 'TABLE_ENTRY_DECODE',
            'entry_encoding': 'PREL32', 'cross_function_overwrite': False,
            'function_range_safe': True, 'function_size': 80, 'probe_size': 60,
            'incoming_interior_branches': 0, 'backedge_conflict': False,
            'runtime_rewrite_conflict': False, 'cfg_closure_proven': True,
            'window_derivation': 'TARGET_CFG', 'reuse_arch_160b': False,
            'reuse_subsys_56b': False, 'copied_arch_probe': False, 'copied_subsys_probe': False,
            'prior_subsys_probe': False, 'prior_arch_probe': False, 'prior_core_probe': False,
            'prior_postcore_probe': False, 'probe_architecture': 'INLINE_PACIASP_PLUS_56B_ULTRACOMPACT',
            'diagnostic_core_size': 56, 'sixty_byte_inline_rejected': False,
            'paciasp_preserved': True, 'cntpct_elapsed': True, 'prel32_target_unchanged': True,
            'fixed_iteration_delay': False, 'rootfs_has_separate_runtime_pass': False,
            'rootfs_included_in_level5': True, 'first_device_entry_implies_fs_complete': True,
            'rootfs_start_is_marker_only': True, 'rewrite_initcall_table': False,
            'treat_rootfs_marker_as_callable': False,
            'literal_delta': 'EXACT_OR_INDEPENDENTLY_PROVEN',
            'pair_diff': 'DELAY_CONSTANT_ONLY', 'timer': 'CNTPCT',
            'psci_fid': '0x84000009', 'timer_algorithm_changed': False,
            'prior_pure_probe': False, 'prior_console_probe': False,
            'rt_d_sha256': '4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327',
            'init_changed': False, 'private_pack': False, 'device_operation': False,
        }
        checkpoint.gate_fs_checkpoint_design(fs)
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_checkpoint_design(dict(fs, boundary='__initcall5_start'))
        with self.assertRaises(ValueError):
            checkpoint.gate_subsys_checkpoint_design(fs)
        tramp = dict(fs, probe_architecture='ENTRY_TRAMPOLINE', function_size=48, probe_size=8,
                     diagnostic_core_size=52, island_size=52, island_kind='RESERVED_EFI_HOLE',
                     sixty_byte_inline_rejected=True, direct_b=True, prel32_retarget_to_island=False,
                     live_tramp_intact=True, veneer=False, stub_branch='B', live_tramp_overlap=False)
        checkpoint.gate_fs_checkpoint_design(tramp)
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_checkpoint_design(dict(tramp, stub_branch='BL'))
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_checkpoint_design(dict(tramp, live_tramp_overlap=True))
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_checkpoint_design(dict(tramp, veneer=True))
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_checkpoint_design(dict(tramp, prel32_retarget_to_island=True))
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_checkpoint_design(dict(tramp, island_kind='RANDOM_CAVE'))
        fixtures = {
            'assume_initcall6_without_audit': ('boundary', '__initcall5_start'),
            'ignore_rootfs_start': ('rootfs_start_is_marker_only', False),
            'treat_marker_callable': ('treat_rootfs_marker_as_callable', True),
            'claim_separate_rootfs_pass': ('rootfs_has_separate_runtime_pass', True),
            'claim_rootfs_not_in_level5': ('rootfs_included_in_level5', False),
            'select_device_before_ordering': ('first_device_entry_implies_fs_complete', False),
            'wrong_causal_target': ('checkpoint_point', 'WRONG_FIRST_DEVICE_TARGET'),
            'shared_do_initcalls': ('checkpoint_point', 'SHARED_DO_INITCALLS_LOOP'),
            'shared_do_initcall_level': ('checkpoint_point', 'SHARED_DO_INITCALL_LEVEL'),
            'before_level5_complete': ('checkpoint_point', 'BEFORE_LEVEL5_COMPLETE'),
            'rewrite_table': ('rewrite_initcall_table', True),
            'cross_function': ('cross_function_overwrite', True),
            'blind_reuse_subsys_56b': ('reuse_subsys_56b', True),
            'blind_reuse_arch_160b': ('reuse_arch_160b', True),
            'copied_subsys_window': ('window_derivation', 'COPIED_SUBSYS_56B'),
            'incoming_branch': ('incoming_interior_branches', 1),
            'backedge_source_live': ('backedge_conflict', True),
            'cfg_not_closed': ('cfg_closure_proven', False),
            'runtime_rewrite': ('runtime_rewrite_conflict', True),
            'unproved_literal_delta': ('literal_delta', 'UNPROVEN'),
            'extra_pair_diff': ('pair_diff', 'EXTRA_BYTES'),
            'timer_change': ('timer_algorithm_changed', True),
            'psci_change': ('psci_fid', '0x84000008'),
            'subsys_probe_remains': ('prior_subsys_probe', True),
            'arch_probe_remains': ('prior_arch_probe', True),
            'postcore_probe_remains': ('prior_postcore_probe', True),
            'core_probe_remains': ('prior_core_probe', True),
            'pure_probe_remains': ('prior_pure_probe', True),
            'console_probe_remains': ('prior_console_probe', True),
            'rt_d_changed': ('rt_d_sha256', '0' * 64),
            'init_changed': ('init_changed', True),
            'private_pack': ('private_pack', True),
            'device_operation': ('device_operation', True),
            'short_function': ('function_size', 4),
            'fixed_iteration': ('fixed_iteration_delay', True),
            'prel32_retarget': ('prel32_target_unchanged', False),
            'drop_paciasp': ('paciasp_preserved', False),
        }
        for name, (key, value) in fixtures.items():
            bad = dict(fs)
            bad[key] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_fs_checkpoint_design(bad)


    def test_fs_encode_b_roundtrip_and_range_fail(self):
        pc = 0xFFFF800081B347BC
        target = 0xFFFF80008000FFCC
        word = checkpoint.encode_b(pc, target)
        self.assertEqual(word & checkpoint.B_OP_MASK, checkpoint.B_OP)
        self.assertEqual(checkpoint.branch_target(word, pc), target)
        self.assertEqual(checkpoint.encode_b(pc, pc + 8), 0x14000002)
        self.assertEqual(checkpoint.encode_b(pc, pc - 4), 0x17FFFFFF)
        with self.assertRaises(ValueError):
            checkpoint.encode_b(pc, pc + (1 << 27))
        with self.assertRaises(ValueError):
            checkpoint.encode_b(pc, pc + 2)
        with self.assertRaises(ValueError):
            checkpoint.encode_b(pc + 1, target)

    def test_fs_island_selector_rejects_live_tramp_overlap(self):
        tramp = (checkpoint.t3.TRAMP_OFFSET, checkpoint.LIVE_TRAMP_END)
        self.assertTrue(checkpoint.windows_overlap(tramp, (0x40, 0x40 + 52)))
        self.assertTrue(checkpoint.windows_overlap(tramp, (0x50, 0x50 + 52)))
        self.assertTrue(checkpoint.windows_overlap(tramp, (0x3C, 0x3C + 52)))
        self.assertFalse(checkpoint.windows_overlap(tramp, (0x70, 0x70 + 52)))
        self.assertTrue(checkpoint.windows_overlap((0x1B347B8, 0x1B347C0), (0x1B347B8, 0x1B347B8 + 52)))
        frozen = bytearray(0x20000)
        image = bytearray(0x20000)
        self.assertEqual(checkpoint.select_reserved_efi_island(frozen, image), 0x10000 - 52)
        filled = bytearray(b'\xff' * 0x20000)
        image = bytearray(filled)
        frozen = bytearray(filled)
        frozen[0x80:0x80 + 52] = bytes(52)
        image[0x80:0x80 + 52] = bytes(52)
        self.assertEqual(checkpoint.select_reserved_efi_island(frozen, image), 0x80)
        frozen[0x80:0x80 + 52] = b'\xff' * 52
        image[0x80:0x80 + 52] = b'\xff' * 52
        self.assertEqual(checkpoint.select_reserved_efi_island(frozen, image), 0x10000 - 52)
        image[0x70:0x10000] = bytes(0x10000 - 0x70)
        with self.assertRaises(ValueError):
            checkpoint.select_reserved_efi_island(frozen, image)

    def test_fs_patch_windows_are_disjoint(self):
        base = bytes(range(100))
        out = checkpoint.patch_windows(base, ((10, b'AB'), (50, b'CD')))
        self.assertEqual(out[10:12], b'AB')
        self.assertEqual(out[50:52], b'CD')
        self.assertEqual(out[:10], base[:10])
        with self.assertRaises(ValueError):
            checkpoint.patch_windows(base, ((10, bytes(20)), (20, bytes(8))))
        stub = (0x1B347B8, 0x1B347C0)
        island = (0x70, 0x70 + 52)
        checkpoint.require_disjoint_windows([stub, island])
        with self.assertRaises(ValueError):
            checkpoint.require_disjoint_windows([stub, (0x1B347B8, 0x1B347B8 + 52)])


    def test_fs_isolation_control_and_midpoint_gates(self):
        pc = 0xFFFF8000800149E4
        island = 0xFFFF80008000FFCC
        word = checkpoint.encode_b(pc, island)
        self.assertEqual(word & checkpoint.B_OP_MASK, checkpoint.B_OP)
        self.assertEqual(checkpoint.branch_target(word, pc), island)
        failed_pc = 0xFFFF800081B347BC
        self.assertEqual(checkpoint.encode_b(failed_pc, island), 0x17936E04)
        entries = [{'index': i, 'target_va': 0x1000 + i} for i in range(53)]
        self.assertEqual(checkpoint.select_fs_midpoint_index(entries), 26)
        with self.assertRaises(ValueError):
            checkpoint.select_fs_midpoint_index(entries[:-1])
        control = {
            'checkpoint_point': 'KNOWN_REACHED_FIRST_FS_ENTRY_TRAMPOLINE_CONTROL',
            'boundary': '__initcall5_start', 'target_derivation': 'TABLE_ENTRY_DECODE',
            'entry_encoding': 'PREL32', 'cross_function_overwrite': False,
            'function_range_safe': True, 'function_size': 56, 'probe_size': 8,
            'incoming_interior_branches': 0, 'backedge_conflict': False,
            'runtime_rewrite_conflict': False, 'cfg_closure_proven': True,
            'window_derivation': 'TARGET_CFG', 'reuse_arch_160b': False, 'reuse_subsys_56b': False,
            'copied_arch_probe': False, 'copied_subsys_probe': False, 'prior_subsys_probe': False,
            'prior_arch_probe': False, 'prior_core_probe': False, 'prior_postcore_probe': False,
            'paciasp_preserved': True, 'cntpct_elapsed': True, 'prel32_target_unchanged': True,
            'fixed_iteration_delay': False, 'rootfs_has_separate_runtime_pass': False,
            'rootfs_included_in_level5': True, 'first_device_entry_implies_fs_complete': True,
            'rootfs_start_is_marker_only': True, 'rewrite_initcall_table': False,
            'treat_rootfs_marker_as_callable': False,
            'literal_delta': 'EXACT_OR_INDEPENDENTLY_PROVEN', 'pair_diff': 'DELAY_CONSTANT_ONLY',
            'timer': 'CNTPCT', 'psci_fid': '0x84000009', 'timer_algorithm_changed': False,
            'prior_pure_probe': False, 'prior_console_probe': False,
            'rt_d_sha256': '4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327',
            'init_changed': False, 'private_pack': False, 'device_operation': False,
            'known_reached_target': 'create_debug_debugfs_entry',
            'force_trampoline_despite_inline_fit': True, 'probe_architecture': 'ENTRY_TRAMPOLINE',
            'diagnostic_core_size': 52, 'island_size': 52, 'island_kind': 'RESERVED_EFI_HOLE',
            'island_offset': 0xffcc, 'direct_b': True, 'veneer': False, 'stub_branch': 'B',
            'live_tramp_overlap': False, 'live_tramp_intact': True,
            'prel32_retarget_to_island': False, 'sixty_byte_inline_rejected': True,
        }
        checkpoint.gate_fs_trampoline_control_design(control)
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_trampoline_control_design(dict(control, island_offset=0x70))
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_trampoline_control_design(
                dict(control, known_reached_target='register_arm64_panic_block'))
        mid = dict(control, checkpoint_point='FS_LEVEL_RUNTIME_MIDPOINT_ENTRY',
                   boundary='__initcall5_index_26',
                   target_derivation='RUNTIME_TABLE_MIDPOINT_INDEX', midpoint_index=26,
                   entry_count=53, name_guess=False, function_size=80, probe_size=8)
        checkpoint.gate_fs_midpoint_design(mid)
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_midpoint_design(dict(mid, midpoint_index=0))
        with self.assertRaises(ValueError):
            checkpoint.gate_fs_midpoint_design(dict(mid, name_guess=True))
        stub = (0x149E0, 0x149E8)
        island_span = (0xFFCC, 0x10000)
        live = (0x40, 0x70)
        first_device = (0x1B347B8, 0x1B347C0)
        checkpoint.require_disjoint_windows([stub, island_span, live, first_device])

    def test_fs_upper_half_design_negative_fixtures(self):
        entries = [{'index': i, 'target_va': 0x1000 + i} for i in range(53)]
        self.assertEqual(checkpoint.select_fs_upper_half_index(entries), 39)
        with self.assertRaises(ValueError):
            checkpoint.select_fs_upper_half_index(entries[:-1])
        design = checkpoint._isolation_design_base(
            'FS_LEVEL_UPPER_HALF_MIDPOINT_ENTRY', '__initcall5_index_39')
        design.update({
            'target_derivation': 'PROVEN_UPPER_HALF_MIDPOINT_FLOOR',
            'lower_index': 26, 'first_device_index': 53, 'midpoint_index': 39,
            'entry_count': 53, 'name_guess': False, 'target_symbol': 'chr_dev_init',
            'table_entry_va': 0xffff800081d0b170, 'target_va': 0xffff800081b8cd40,
            'target_source': 'drivers/char/mem.c',
            'initcall_registration': 'fs_initcall(chr_dev_init)',
            'probe_architecture': 'INLINE_PACIASP_PLUS_52B_NO_DAIFSET',
            'diagnostic_core_size': 52, 'function_size': 184, 'probe_size': 56,
            'sixty_byte_inline_rejected': True, 'inline_only': True,
            'trampoline_permitted': False,
        })
        checkpoint.gate_fs_upper_half_design(design)
        drifts = {
            'index': ('midpoint_index', 38), 'span': ('entry_count', 52),
            'architecture': ('probe_architecture', 'ENTRY_TRAMPOLINE'),
            'core': ('diagnostic_core_size', 56), 'window': ('probe_size', 60),
            'name_guess': ('name_guess', True),
            'table_identity': ('table_entry_va', 0xffff800081d0b174),
        }
        for name, (key, value) in drifts.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_fs_upper_half_design(dict(design, **{key: value}))

    def test_fs_post39_design_negative_fixtures(self):
        entries = [{'index': i, 'target_va': 0x1000 + i} for i in range(53)]
        self.assertEqual(checkpoint.select_fs_post39_index(entries), 46)
        with self.assertRaises(ValueError):
            checkpoint.select_fs_post39_index(entries[:-1])
        design = checkpoint._isolation_design_base(
            'FS_LEVEL_POST39_MIDPOINT_ENTRY', '__initcall5_index_46')
        design.update({
            'target_derivation': 'PROVEN_POST39_MIDPOINT_FLOOR',
            'lower_index': 39, 'first_device_index': 53, 'midpoint_index': 46,
            'entry_count': 53, 'name_guess': False, 'target_symbol': 'af_unix_init',
            'table_entry_va': 0xffff800081d0b18c, 'target_va': 0xffff800081bae798,
            'target_source': 'net/unix/af_unix.c',
            'initcall_registration': 'fs_initcall(af_unix_init)',
            'probe_architecture': 'INLINE_PACIASP_PLUS_56B_ULTRACOMPACT',
            'diagnostic_core_size': 56, 'function_size': 216, 'probe_size': 60,
            'sixty_byte_inline_rejected': False, 'inline_only': True,
            'trampoline_permitted': False,
        })
        checkpoint.gate_fs_post39_design(design)
        drifts = {
            'index': ('midpoint_index', 45), 'span': ('entry_count', 52),
            'architecture': ('probe_architecture', 'ENTRY_TRAMPOLINE'),
            'core': ('diagnostic_core_size', 52), 'window': ('probe_size', 56),
            'name_guess': ('name_guess', True),
            'table_identity': ('table_entry_va', 0xffff800081d0b190),
            'sixty': ('sixty_byte_inline_rejected', True),
        }
        for name, (key, value) in drifts.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_fs_post39_design(dict(design, **{key: value}))

    def test_fs_post46_design_negative_fixtures(self):
        entries = [{'index': i, 'target_va': 0x1000 + i} for i in range(53)]
        self.assertEqual(checkpoint.select_fs_post46_index(entries), 49)
        with self.assertRaises(ValueError):
            checkpoint.select_fs_post46_index(entries[:-1])
        design = checkpoint._isolation_design_base(
            'FS_LEVEL_POST46_MIDPOINT_ENTRY', '__initcall5_index_49')
        design.update({
            'target_derivation': 'PROVEN_POST46_MIDPOINT_FLOOR',
            'lower_index': 46, 'first_device_index': 53, 'midpoint_index': 49,
            'entry_count': 53, 'name_guess': False, 'target_symbol': 'vlan_offload_init',
            'table_entry_va': 0xffff800081d0b198, 'target_va': 0xffff800081baedfc,
            'target_source': 'net/8021q/vlan_core.c',
            'initcall_registration': 'fs_initcall(vlan_offload_init)',
            'probe_architecture': 'INLINE_PACIASP_PLUS_56B_ULTRACOMPACT',
            'diagnostic_core_size': 56, 'function_size': 60, 'probe_size': 60,
            'sixty_byte_inline_rejected': False, 'inline_only': True,
            'trampoline_permitted': False,
        })
        checkpoint.gate_fs_post46_design(design)
        drifts = {
            'index': ('midpoint_index', 48), 'span': ('entry_count', 52),
            'architecture': ('probe_architecture', 'ENTRY_TRAMPOLINE'),
            'core': ('diagnostic_core_size', 52), 'window': ('probe_size', 56),
            'name_guess': ('name_guess', True),
            'table_identity': ('table_entry_va', 0xffff800081d0b19c),
            'sixty': ('sixty_byte_inline_rejected', True),
        }
        for name, (key, value) in drifts.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_fs_post46_design(dict(design, **{key: value}))

    def test_fs_post49_design_negative_fixtures(self):
        entries = [{'index': i, 'target_va': 0x1000 + i} for i in range(53)]
        self.assertEqual(checkpoint.select_fs_post49_index(entries), 51)
        with self.assertRaises(ValueError):
            checkpoint.select_fs_post49_index(entries[:-1])
        design = checkpoint._isolation_design_base(
            'FS_LEVEL_POST49_MIDPOINT_ENTRY', '__initcall5_index_51')
        design.update({
            'target_derivation': 'PROVEN_POST49_MIDPOINT_FLOOR',
            'lower_index': 49, 'first_device_index': 53, 'midpoint_index': 51,
            'entry_count': 53, 'name_guess': False, 'target_symbol': 'acpi_reserve_resources',
            'table_entry_va': 0xffff800081d0b1a0, 'target_va': 0xffff800081b6b2fc,
            'target_source': 'drivers/acpi/osl.c',
            'initcall_registration': 'fs_initcall_sync(acpi_reserve_resources)',
            'probe_architecture': 'INLINE_PACIASP_PLUS_56B_ULTRACOMPACT',
            'diagnostic_core_size': 56, 'function_size': 6408, 'probe_size': 60,
            'sixty_byte_inline_rejected': False, 'inline_only': True,
            'trampoline_permitted': False,
        })
        checkpoint.gate_fs_post49_design(design)
        drifts = {
            'index': ('midpoint_index', 50), 'span': ('entry_count', 52),
            'architecture': ('probe_architecture', 'ENTRY_TRAMPOLINE'),
            'core': ('diagnostic_core_size', 52), 'window': ('probe_size', 56),
            'name_guess': ('name_guess', True),
            'table_identity': ('table_entry_va', 0xffff800081d0b1a4),
            'sixty': ('sixty_byte_inline_rejected', True),
        }
        for name, (key, value) in drifts.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                checkpoint.gate_fs_post49_design(dict(design, **{key: value}))

    def test_composition_changes_only_authorized_window(self):
        before = bytes(range(100))
        after = checkpoint.patch_window(before, 20, b'ABCD')
        self.assertEqual(after[:20], before[:20])
        self.assertEqual(after[20:24], b'ABCD')
        self.assertEqual(after[24:], before[24:])
        for offset in (-1, 99):
            with self.assertRaises(ValueError):
                checkpoint.patch_window(before, offset, b'ABCD')


if __name__ == '__main__':
    unittest.main()
