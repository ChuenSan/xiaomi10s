# Slot B late index-52 COMPACT_INLINE_48B freeze + device pair (2026-09-20)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_INDEX52_COMPACT_FREEZE_AND_DEVICE_PAIR`.
Device: Xiaomi Mi 10S (thyme / M2102J2SC) serial `41a5627b`, operated serially by
the main agent from healthy Android A. Final gate:
**`R3_SLOT_B_LATE_INDEX52_COMPACT_ENTRY_PROVEN`**.

## Why this round existed

The previous round's CI gate `R3_SLOT_B_LATE_INDEX52_COMPACT_CORE_CI_READY`
published `READY_FOR_LATE_INDEX52_COMPACT_DEVICE_PAIR=YES`, but the family was
**not executable**: the device-side identity freeze had been omitted.
`scripts/slot_b/observe.py` is the only device-round driver and declares
`--case` as `choices=IMAGES`, so an unregistered family dies in argparse before
any device I/O. Because the compact52 fixtures were written "self-contained"
(`"f1a0" + "0" * 60` style constants that are 64 **valid** hex characters), the
green observer-fixtures run `35514833635` was never evidence of a freeze. This
round only completed the missing links - no byte of the frozen pair was
regenerated, repacked or substituted.

## Phase A - identity freeze (`385ab99`)

`observe.py` gained the compact52 plug-in points, mirroring the btic51 pattern
where the authorisation commit leaves the slots and the freeze commit fills them:

- `COMPACT52_{8,1}_{BOOT,PAYLOAD}_SHA256` constants;
- a guarded registration of `IMAGES["late_compact528"]` / `["late_compact521"]`,
  whose guard also requires `len(set(sha)) > 2` so a repeated-nibble sentinel
  can never become an identity;
- `PAIRS["late_compact521"] = ("late_compact528", "late_compact52_entry",
  "late_initcalls_completed")`, which also extends `ORIGIN_CASES`;
- the compact52 pair-verdict route emitting `late_compact52_entry` /
  `boot_wait_for_devices_entry` and `late_compact52_checkpoint_shift_not_observed`.

`IMAGES` grew 63 -> 65 keys; the projected cross-identity rejection count stays
124 because the two new keys are skipped as `MEMBERS`. No frozen family was
modified.

## Phase B - placeholder false-pass closed

The four fixture constants were replaced with the authoritative full SHAs and
the module hardened with `is_placeholder_sha`, `require_authoritative` and
`require_registry_agreement`, each with positive and negative fixtures. The
fixtures deliberately keep **independent literals** rather than importing from
`observe`, so the agreement gate compares two separately transcribed sources
instead of asserting a tautology. A new GHA job `identity-agreement` re-downloads
the frozen public run `35516067282` and proves
`registry == fixtures == pair.json == per-member checkpoint manifest ==
audit-summary.txt`. Pre-freeze run `35514833635` is demoted to a historical
pre-freeze fixture run and is **not** device-authorisation evidence.

## Phase C - artifacts materialized (download only)

Private run `35516663217`, artifact `thyme-late-compact52-private-pair`
(28094917 B). Both images verified at 37380096 B with exact full SHA256, plus
the matching payload SHAs. `KERNEL_REBUILD=NO`, `PARTITION_WRITES=0`.

## Phase D - post-freeze validation

GHA run `35518134233` @ `385ab99`: `observer-fixtures` PASS,
`identity-agreement` PASS, `POST_FREEZE_OBSERVER=PASS`,
`AUTHORITATIVE_SHA_MATCH=PASS` (6 manifest entries), `PLACEHOLDER_SHA_REJECTED=PASS`,
`PAIR_DIFF=DELAY_CONSTANT_ONLY`. Unit tests 25 compact52 + 38 base observer OK.
The same commit triggered 20 workflows and **all 20 succeeded**, including all 16
historical slot-b observer-fixture families - zero regressions.

## Phase E - device preflight (read-only)

`_a` / `sys.boot_completed=1` / `4.19.157-perf-g9d90dd04aa7c`. Current B 16-chain,
`vendor_boot_b`, `dtbo_b` and the P15 prefix
(`133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34`) all MATCH.
Hashing stayed on-device (`adb shell -T` + device-side `sha256sum`); no
`adb exec-out`.

## Phase F - first true-device COMPACT_INLINE_48B pair

| Member | Boot identity (frozen) | Behavior | total_s |
|---|---|---|---|
| `late_compact528` | `64a2ed163029f693f7ffa75b8541f1afed04ac0843cb40c551bdbc5d5e968529` | `AUTOMATIC_FASTBOOT_RETURN`, retry 7->6 | 35.498629292007536 |
| `late_compact521` | `771d29da92c0cef828d2c2da4b61262e85a489049f23764051f7bfc39c2cd100` | `AUTOMATIC_FASTBOOT_RETURN`, retry 7->6 | 28.487913249991834 |

`PAIR_DELTA=-7.010716042015702s` vs expected `-7.000000000s`
(`PAIR_ERROR=-0.010716042015702s`, abs `0.0107 <= 1.000`) -> **`STRONG`**:
`BOOT_WAIT_FOR_DEVICES_ENTRY=PROVEN` / `late_compact52_entry=PROVEN`. Reaching
the index-52 entry proves late entries 0..51 each returned (sequential
`do_initcall_level` contract) -> **`LATEST_PROVEN_LATE_INDEX=52`**,
`NEXT_DIAGNOSTIC_INTERVAL=52..55`.

`NO_RETURN_WITHIN_120S` did not occur; USB disappearance / adb+fastboot dual
loss / transport anomaly did not occur. Android A restored healthy after each
member; Current B 16-chain + P15 prefix MATCH pre / between / post;
`PARTITION_WRITES=0`; `SLOT_A_WRITTEN=NO`; USB `FROZEN`.
`late_compact528` / `late_compact521` are rerun-FORBIDDEN.

## Runtime evidence (otherwise unchanged)

`LATE_INITCALLS_COMPLETED`, `WAIT_FOR_INITRAMFS_ENTRY`,
`WAIT_FOR_INITRAMFS_RETURN`, `CONSOLE_ON_ROOTFS`, `INIT_EXECUTED` stay
`NOT_PROVEN`; `LATE_HIGH1` stays `NOT_EXECUTED`; `.text` policy not relaxed.
Index 53/54/55 were not probed and no new probe was added.

## Evidence

`artifacts/slot-b-late-index52-compact-20260920/` - `device-round/`
(context.json, host logs, observer `result.json`/`events.json`, partition
snapshots pre/between/post, set-active records, bootloader preflights, Android A
records, `final-report.txt`), `private/` (downloaded frozen pair + identity
files), `observer/run-35518134233/` (post-freeze gates + identity agreement).
Dirty worktree `/Volumes/LinuxDev/thyme-mainline` @`5550dc2` untouched.
Local builds 0.
