import struct
import unittest

import checkpoint as cp
import post_initcalls as post

MAIN = """
static void __init do_basic_setup(void)
{
    driver_init();
    do_initcalls();
}
static noinline void __init kernel_init_freeable(void)
{
    do_basic_setup();
    kunit_run_all_tests();
    wait_for_initramfs();
    console_on_rootfs();
}
for (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++)
"""


def parent_fixture():
    data = bytearray(post.PARENT_END - post.PARENT_VA)
    struct.pack_into('<I', data, 0, 0xD503233F)
    for offset, _, target in post.CALLS:
        word = 0x94000000 | (((target - offset) // 4) & 0x03FFFFFF)
        struct.pack_into('<I', data, offset - 0x1B3103C, word)
    struct.pack_into('<14I', data, 0x1B3113C - 0x1B3103C, *post.EXPECTED_BODY)
    return data


class PostInitcallsTests(unittest.TestCase):
    def test_caller_specific_source_boundary(self):
        result = post.source_contract(MAIN, '# CONFIG_KUNIT is not set\n')
        self.assertFalse(result['global_wait_entry_used'])
        self.assertTrue(result['caller_specific_return_boundary'])

    def test_source_order_mutation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_ORDER'):
            post.source_contract(MAIN.replace('wait_for_initramfs();', 'other_wait();'), '')

    def test_enabled_kunit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'KUNIT_CALL'):
            post.source_contract(MAIN, 'CONFIG_KUNIT=y\n')

    def test_basic_setup_without_initcalls_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BASIC_SETUP'):
            post.source_contract(MAIN.replace('do_initcalls();', 'other_setup();'), '')

    def test_callsite_geometry_stops_before_live_cold_path(self):
        for stage, spec in post.STAGES.items():
            post.gate_geometry(stage, spec['offset'], spec['size'])
            self.assertEqual(post.TEXT_VA + spec['offset'] + spec['size'], post.COLD_VA)

    def test_wait_56_byte_probe_rejected(self):
        with self.assertRaisesRegex(ValueError, 'GEOMETRY'):
            post.gate_geometry('wait_complete', 0x1B31140, 56)

    def test_old_function_entry_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, 'GEOMETRY'):
            post.gate_geometry('late_complete', 0x1B3103C, 56)

    def test_adjacent_bl_sequence_matches_frozen_words(self):
        post.gate_call_sequence(parent_fixture())

    def test_non_linking_predecessor_rejected(self):
        parent = parent_fixture()
        pos = post.CALLS[0][0] - 0x1B3103C
        word = struct.unpack_from('<I', parent, pos)[0] & ~0x80000000
        struct.pack_into('<I', parent, pos, word)
        with self.assertRaisesRegex(ValueError, 'NOT_BL'):
            post.gate_call_sequence(parent)

    def test_wrong_predecessor_callee_rejected(self):
        parent = parent_fixture()
        pos = post.CALLS[0][0] - 0x1B3103C
        struct.pack_into('<I', parent, pos, 0x94000000)
        with self.assertRaisesRegex(ValueError, 'CALL_TARGET'):
            post.gate_call_sequence(parent)

    def test_incoming_at_checkpoint_start_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BYPASS_OR_INTERIOR'):
            post.gate_incoming([(post.PARENT_VA, post.TEXT_VA + 0x1B3113C)])

    def test_incoming_inside_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BYPASS_OR_INTERIOR'):
            post.gate_incoming([(post.PARENT_VA, post.TEXT_VA + 0x1B31148)])

    def test_return_word_mutation_rejected(self):
        parent = parent_fixture()
        struct.pack_into('<I', parent, post.COLD_VA - post.PARENT_VA - 4, 0xD503201F)
        with self.assertRaisesRegex(ValueError, 'TAIL_WORDS'):
            post.gate_call_sequence(parent)

    def test_delay_pair_retains_psci_and_terminal_loop(self):
        for words, slot in ((cp.ULTRACOMPACT_WORDS, 8), (cp.SUBSYS52_WORDS, 4)):
            core = struct.pack('<%dI' % len(words), *words)
            one = cp.delay_core(core, 1)
            self.assertEqual([i for i, (a, b) in enumerate(zip(core, one)) if a != b],
                             [slot + 1, slot + 2])
            self.assertEqual(struct.unpack_from('<III', one, len(one) - 12),
                             (0xD4000003, 0xD503205F, 0x17FFFFFF))


if __name__ == '__main__':
    unittest.main()
