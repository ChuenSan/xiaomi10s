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

    def test_ultracompact_core_and_literal_delta_are_exact(self):
        words = [0] * 14
        words[2] = 0xD37DF12A
        words[8] = 0x54FFFF83
        words[11:14] = [0xD4000003, 0xD503205F, 0x17FFFFFF]
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
