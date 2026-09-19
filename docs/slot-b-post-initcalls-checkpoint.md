# Slot B post-initcalls caller-side checkpoints — late complete / initramfs wait (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_COMPLETE_AND_INITRAMFS_WAIT_ISOLATION`.
Verdict of the executed pair: `SHIFT_NOT_OBSERVED`. Final gate:
`R3_SLOT_B_INITRAMFS_WAIT_CHECKPOINT_SHIFT_NOT_OBSERVED`.

## Source semantics (Linux 6.6.156, pinned 8b73de7da85fde281a385e0b26eda9bffd3ca477)

- `kernel_init_freeable()` (init/main.c:1521-1530) ends its hot path with
  `do_basic_setup(); kunit_run_all_tests(); wait_for_initramfs(); console_on_rootfs();`
  — no code, branch or early return between the calls. `kunit_run_all_tests()`
  is the empty static inline when `CONFIG_KUNIT` is not builtin; the binary
  shows three adjacent BLs.
- `do_basic_setup()` ends with `do_initcalls()`, which iterates levels 0..7
  (`late` = `[__initcall7_start, __initcall_end)`, 86 entries) with no early
  exit. Returning from `do_basic_setup` therefore implies every late initcall
  was run through `do_one_initcall()`.
- `wait_for_initramfs()` (init/initramfs.c:745-759) guards on
  `initramfs_cookie` then `async_synchronize_cookie_domain`. In-tree call
  sites: `populate_rootfs` (guarded `!initramfs_async`, dead under RT-D),
  `kernel_init_freeable` (unconditional, first on the kernel_init thread),
  `kernel/umh.c:109` and `drivers/base/firmware_loader/main.c:512`
  (data-dependent, other threads). `initramfs_async` defaults to `true`;
  RT-D bootargs `rdinit=/init panic=5 loglevel=7` set no `initramfs_async=`,
  so `populate_rootfs` schedules the unpack asynchronously and returns
  without waiting — no early trigger exists under thyme conditions.

Because a probe inside `wait_for_initramfs` would be a shared checkpoint
covering all four callers (forbidden: shared unconditional checkpoint), both
checkpoints are caller-specific inline windows inside `kernel_init_freeable`
(VA `0xffff800081b3103c..0xffff800081b311a8`, byte-exact against the frozen
FIX8 payload, Image and bundle vmlinux):

- `late_complete` — window `[0x1b3113c, 0x1b31174)` (56 B), the whole hot tail
  from the `bl wait_for_initramfs` to the `ret` at the cold path boundary
  `0x1b31174`. Predecessor `do_basic_setup`. Positive proves
  `late_initcalls_completed`; does not prove `wait_for_initramfs_return`.
- `wait_complete` — window `[0x1b31140, 0x1b31174)` (52 B) preserving the
  `bl wait_for_initramfs`; fires after that call returns. Positive proves
  `wait_for_initramfs_return` (entry follows from the unconditional
  byte-exact BL); does not prove `console_on_rootfs_entry`.

Probe cores are the frozen terminal sequences only: 56 B ultracompact
(daifset + CNTPCT spin + PSCI `0x84000009` + WFE fail-closed) for
`late_complete`, 52 B no-daifset core for `wait_complete`; pair diff is two
bytes at `[0x1b31145,0x1b31147)` in both stages. Trampoline, island and
PREL32 retarget are not used.

## CI chain (GHA only, bundle 35040148509, no kernel rebuild)

| Stage | late_complete | wait_complete |
|---|---|---|
| Public audit-pair | 35414669247 | 35414691058 |
| Private pack | 35415464261 | 35415466451 |
| Private reverify-only | 35415820071 | 35415822001 |
| Observer fixtures | 35416122329 | 35416122288 |

All gates passed, including incoming-branch inclusive scan (empty),
284143 relocation sites, runtime rewrite tables (`__ex_table`,
`.altinstructions`; `__jump_table`/`.static_call_sites`/`.kcfi_traps`
absent), window byte agreement, RT-D DTB and builtin-initramfs `/chosen`
gates. Observer fixtures freeze the four boot identities and reject the
sibling plus all frozen older candidates (88/92 cross rejections); all
previous observer families regressed green at 1624c60.

Frozen identities (37380096 each):

- WAITENTRY8 boot `66201264f8d7b7f4ba7a4ce8f495e46c6d4d0764863ffa5f49109b3a71944d7d`
- WAITENTRY1 boot `8b422262aa73809a2258ecb7e8a3e36941eff683ed8cb2b3cce16dd4072d530e`
- WAITRET8 boot `2c589a61933d8f657e0ac08374c6038d0624807f11c6acb22fc1851ca0b9cb2a`
- WAITRET1 boot `0a67761550906d05e602be83afe6b2f5e10cf4d222bdcc3bdc65e24fb950d2c8`

## Device round (artifacts/slot-b-post-initcalls-20260919/device-round/)

Exactly one RAM-only Slot B boot per member, serial 41a5627b, both
`AUTOMATIC_FASTBOOT_RETURN` with retry 7→6, no manual recovery:

- `WAITENTRY8_TOTAL=45.212251791s` (Sending OKAY 0.928s, Booting OKAY 0.220s)
- `WAITENTRY1_TOTAL=48.412371375s` (Sending OKAY 0.927s, Booting OKAY 0.220s)
- `PAIR_DELTA=+3.200119584s`, expected `-7.000000000s`, error `+10.200119584s`
  → `SHIFT_NOT_OBSERVED`.

Current B 16-chain hashes and the P15 prefix (`133e063b…87d34`) matched
pre/between/post; Android A restored healthy (stock 4.19.157, `_a`);
partition writes 0; Slot A untouched. `WAITRET8/WAITRET1` were NOT
device-executed: the round ladder continues to the return stage only after an
ENTRY STRONG.

No completion or non-completion claim is licensed by a no-shift: only
`CHECKPOINT_SHIFT_NOT_OBSERVED` is recorded. `LATE_INITCALLS_COMPLETED`,
`WAIT_FOR_INITRAMFS_ENTRY`, `WAIT_FOR_INITRAMFS_RETURN`,
`CONSOLE_ON_ROOTFS`, `INIT_EXECUTED` stay `NOT_PROVEN`; the previously
proven boundaries are unchanged; USB stays `FROZEN`. Descriptive note for
the next stage only: both members returned in the same class as the
historical post-initcall no-shift pairs, and the totals sit above the
proven level-7 index-0 entry signature, so the isolation interest is the
late-level span between the proven first late entry and this checkpoint.
`WAITENTRY8/WAITENTRY1` reruns are forbidden.

Next: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION_CI`.
