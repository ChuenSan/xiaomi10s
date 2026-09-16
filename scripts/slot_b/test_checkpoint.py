import struct
import unittest

import checkpoint


class CheckpointTests(unittest.TestCase):
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

    def test_relr_advances_all_63_bitmap_positions(self):
        base = 0xFFFF800081234000
        data = struct.pack('<QQQ', base, 3, 3)
        self.assertEqual(checkpoint.decode_relr(data), [base, base + 8, base + 512])
        self.assertEqual(checkpoint.decode_relr(struct.pack('<QQQ', base, 1, 3)), [base, base + 512])
        with self.assertRaises(ValueError):
            checkpoint.decode_relr(struct.pack('<Q', 3))
        with self.assertRaises(ValueError):
            checkpoint.decode_relr(b'bad')

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
