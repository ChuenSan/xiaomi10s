# Xiaomi Mi 10S handoff — PM-lock static feasibility, 2026-09-22

## Stop and reading order

The user requested complete closeout and a conversation switch. Work is
intentionally paused. This is not project completion or device loss. Do not
dispatch CI, boot, or change slots until continuation is explicitly resumed.

Read this document first, then `docs/slot-b-deferred-pm-lock.md` and the top of
`docs/route-r3-current-status.md`. It supersedes the continuation pointer in
`docs/handoff-2026-09-22-pm-tail-entry.md`. Obtain operational Git identities
from live Git and committed CI receipts, not older memory prose.

## Repositories

- Public `ChuenSan/xiaomi10s`:
  `/Volumes/LinuxDev/thyme-mainline-slot-b-continuation`, branch
  `route-b-slot-b-continuation`. Before this documentation closeout, tracked
  HEAD was `bcc71bd1a5d877a73bd8286b7aeccc1e238bc9b1`. This document's commit is
  the closing commit; resolve it with
  `git log -1 --format=%H -- docs/handoff-2026-09-22-pm-lock-static.md`.
- Private `ChuenSan/thyme-mainline-private-ci`:
  `/Volumes/LinuxDev/thyme-mainline-private-ci`, branch `main`, unchanged at
  `4e7c64169ea7ee18ec68eb332d786c256bf01c00`. No private PM-lock workflow exists.
- Existing untracked artifacts and caches were preserved. Nothing was deleted.
- Old `/Volumes/LinuxDev/thyme-mainline` was not touched. No CodeGraph index
  exists here; do not create one or rescan the old root.

## Proven state

Static gate: **DEFERRED_PM_LOCK_RETURN_STATIC_FEASIBLE**. Actions
`35671827755` at `f09a011b39088a61942b4a8a9db67ee3ca099f22` passed 12 new and
70 inherited tests. Full suite `35671827678` passed 713 tests with 36
source/artifact skips. The exact 60-byte suffix at Image `0x8de478`, ending
`0x8de4b4`, is feasible. The 56-byte suffix is rejected because
`0x8de4b0 -> 0x8de48c` enters it. This audit generated no candidate.

Runtime remains **DEFERRED_PM_TAIL_ENTRY_PROVEN** from the completed PMTAIL8/1
pair: 35.580534792 / 28.447709084 seconds, delta -7.132825708, error
-0.132825708, **STRONG**. Proven only through `device_pm_move_to_tail()` entry.
PM-lock return, persistent lock state, PM movement/return, bus/driver identity,
late completion, `/init`, and usable Linux remain **NOT_PROVEN**. USB is frozen.
All twelve completed deferred cases, including PMTAIL8/1, are rerun-forbidden.

## Unfinished drafts — preserved, not qualified

Three untracked files remain in their intended active paths and were not
committed, so this closeout does not dispatch their workflow:

- `scripts/slot_b/deferred_pm_lock_probe.py`, SHA256
  `d3f5a74cd95e364a136622da27b70286e568d708d6737f259e13088b445b454b`
- `scripts/slot_b/test_deferred_pm_lock_probe.py`, SHA256
  `395cdd0f8e8799713613495801ce0f84b1629495bc405b1a040b73608c47fce0`
- `.github/workflows/thyme-slot-b-deferred-pm-lock.yml`, SHA256
  `73dcd24fb85a63ece407d99c5ed7d25778f4fcc9d92a0d881692aab7c9960f25`

They propose `defer_afterlock8` / `defer_afterlock1`: the frozen 56-byte core
plus one unreachable NOP. A fresh-context reviewer
(`fb51d86e-8256-4338-b0b5-e18e579f82ee`, model `any/gpt-6-astra:high`) found no
concrete P1/P2 source defect. That review ran no tests, assembly, Actions, or
device operation. **No pair artifact, private pack, fresh-job reverify,
identity freeze, observer, or device readiness exists.**

## Device closeout

Host `2026-09-22T03:50:51Z`: thyme/M2102J2SC, healthy stock Android A (`_a`,
`boot_completed=1`), root, kernel 4.19.157, empty pstore, battery 100%, 26.2 C.
All 16 boot-chain hashes and the 52,666,368-byte boot_b prefix match the
`2026-09-21T23:26:54Z` baseline. Evidence:
`artifacts/slot-b-deferred-pm-lock-20260922/closeout-20260922T035051Z/`.
This closeout performed no reboot, slot selection, or partition write. Current
B remains stock V14 vendor_boot/dtbo plus proven P15 recovery.

## Next step after an explicit resume

1. Reconfirm the three draft hashes, then qualify them with Actions-only
   composition and fresh re-audit. Do not run local tests or assembly.
2. Only after that passes: private pack plus fresh-job verification, actual
   identity freeze, and public/private observer gates.
3. Only then consider one RAM-only Slot B boot per new member. Reconfirm B
   immediately before each boot, restore healthy untouched A, and compare all
   16 hashes plus the P15 prefix between members.

Reuse bundle `35040148509`, public FIX8 `34741153230`, and private FIX8 boot
`34744041027`. A positive pair could prove the two original calls returned, not
lock persistence, PM movement/return, bus/driver probe, culprit, or `/init`.

## Constraints

All compilation, assembly, image generation, tests, and executable validators
stay in GitHub Actions. Never flash, erase, format, or destructively modify
Slot A, firmware, or protected vbmeta. Parent remains the only device operator.
No deletion, reset, or cleanup of old work. Binary acquisition uses
`adb shell -T`, never `adb exec-out su -c`. No relevant Actions run was left
active by this closeout.
