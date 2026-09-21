import struct
import unittest
from unittest.mock import patch

import deferred_name_probe as n


class NameProbeTests(unittest.TestCase):
    def test_window_ends_at_empty_exit_and_preserves_worker_entry(self):
        self.assertEqual(n.OFFSET, 0x8E8468)
        self.assertEqual(n.SIZE, 96)
        self.assertEqual(n.OFFSET + n.SIZE, 0x8E84C8)
        self.assertGreater(n.OFFSET, n.PARENT + 60)
        self.assertLessEqual(n.OFFSET + n.SIZE, n.PARENT + n.PARENT_SIZE)

    def test_core_variants_and_one_word_selectors(self):
        cores = {name: struct.pack('<24I', *n.core_words(name)) for name in n.VARIANTS}
        for name, core in cores.items():
            n.gate_core(name, core)
            self.assertEqual(core[52:], struct.pack('<11I', *n.cp.ULTRACOMPACT_WORDS[3:]))
            for other in cores:
                if name != other:
                    with self.assertRaises(ValueError):
                        n.gate_core(other, core)
        self.assertEqual([i for i, (a, b) in enumerate(zip(cores['ref8'], cores['ref1'])) if a != b], [28])
        for name in ('b0lo', 'b0hi', 'b1lo', 'b1hi'):
            changed = [i for i, (a, b) in enumerate(zip(cores['ref8'], cores[name])) if a != b]
            self.assertTrue(all(24 <= i < 32 for i in changed))

    def test_every_instruction_mutation_rejected(self):
        for name in n.VARIANTS:
            core = struct.pack('<24I', *n.core_words(name))
            for off in range(0, len(core), 4):
                bad = bytearray(core)
                bad[off] ^= 1
                with self.subTest(variant=name, offset=off), self.assertRaises(ValueError):
                    n.gate_core(name, bytes(bad))

    def test_unsigned_nibbles_roundtrip_and_invalid_marker_disjoint(self):
        for byte in range(256):
            low, high = (byte & 15) + 1, (byte >> 4) + 1
            self.assertTrue(1 <= low <= 16 and 1 <= high <= 16)
            self.assertEqual(((high - 1) << 4) | (low - 1), byte)
            self.assertNotIn(17, (low, high))
        self.assertEqual({index for _, index in n.VARIANTS.values()}, {0, 1})

    def test_pointer_layout_and_randomization_rejection(self):
        dev = 'struct device { struct kobject kobj; };'
        obj = 'struct kobject { const char *name; };'
        dd = '''static DECLARE_WORK(deferred_probe_work, deferred_probe_work_func);
static void deferred_probe_work_func(struct work_struct *work)
{
    mutex_lock(&deferred_probe_mutex);
    while (!list_empty(&deferred_probe_active_list)) {
        dev = private->device;
        list_del_init(&private->deferred_probe);
        get_device(dev);
        mutex_unlock(&deferred_probe_mutex);
        bus_probe_device(dev);
    }
}
'''
        with patch.object(n.d, 'source_contract'):
            with patch.object(n.Path, 'read_text', side_effect=[dev, obj, dd]):
                n.source_contract(n.Path('fixture'), 'CONFIG_RANDSTRUCT_NONE=y\n')
            for bad_dev, bad_obj, cfg in ((dev.replace('struct kobject kobj;', 'int pad; struct kobject kobj;'), obj, 'CONFIG_RANDSTRUCT_NONE=y'),
                                          (dev, obj.replace('const char *name;', 'int pad; const char *name;'), 'CONFIG_RANDSTRUCT_NONE=y'),
                                          (dev, obj, 'CONFIG_RANDSTRUCT_FULL=y')):
                with patch.object(n.Path, 'read_text', side_effect=[bad_dev, bad_obj, dd]):
                    with self.assertRaises(ValueError):
                        n.source_contract(n.Path('fixture'), cfg)


if __name__ == '__main__':
    unittest.main()
