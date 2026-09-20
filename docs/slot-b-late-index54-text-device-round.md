# Slot B late index-54 TARGET-SCOPED `.text` device pair (2026-09-20)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_INDEX54_TEXT_DEVICE_PAIR`.
Device: Xiaomi Mi 10S (thyme / M2102J2SC) serial `41a5627b`, operated serially by
the main agent from healthy Android A. Final gate:
**`R3_SLOT_B_LATE_INDEX54_TEXT_ENTRY_PROVEN`**.

## Why this round existed

The CI gate `R3_SLOT_B_LATE_INDEX54_TEXT_EXCEPTION_CI_READY` published
`READY_FOR_LATE_INDEX54_TEXT_DEVICE_PAIR=YES` with a literal four-tuple
allowlist of one member (`index 54`, `deferred_probe_initcall`,
`0xffff8000808e7564`, `.text`). This round is the first true-device pair of
that target-scoped exception. It does **not** create `ALLOW_TEXT_TARGETS`,
does not reuse the exception on index 53, and does not change the frozen
`INLINE_PACIASP_PLUS_56B_ULTRACOMPACT` family.

## Frozen identities (full SHA, no truncation / no repack)

| Field | Value |
|---|---|
| Public CI | `35520679000` @ `8f0aad8` |
| Private pack | `35521176700` @ private `528a9f1` |
| Independent reverify | `35521361359` |
| Identity freeze | `5ef67e2` |
| Observer + identity-agreement | `35521787570` @ `b2b121b` |
| Payload 8 | `972be7455da70f7dece9ce299c326d1a6cdba2d77c1a809946a3c1ea15dff2ae` |
| Payload 1 | `afbeb6c213ee438cfef5e3b1b7662a599d1f58abbdbb8313e3d640789c21e485` |
| Boot 8 | `ea286b201d0e6f22b1ed48d6c8e7b8e1811b51507ca02f39316c3d7d4d2ca4b5` (37380096) |
| Boot 1 | `3dd0ae7cd5ea71ef5531f4969926283971ec1c125a97fb43fccb59268e231124` (37380096) |
| Geometry | 492 B `.text`, window 60, core 56, entry `paciasp` preserved, tail 432 B original unreachable |
| Pair diff | `[0x8e7571,0x8e7573)` `DELAY_CONSTANT_ONLY` |

The frozen pair was **downloaded only** from private run `35521176700`
artifact `thyme-late-text54-private-pair`. Host SHA256 of both images MATCH.
`KERNEL_REBUILD=NO`.

## Device pair (RAM-only Slot B, one boot per member)

| Member | Boot identity (frozen) | Behavior | total_s |
|---|---|---|---|
| `late_text548` | `ea286b201d0e6f22b1ed48d6c8e7b8e1811b51507ca02f39316c3d7d4d2ca4b5` | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 35.225727583 |
| `late_text541` | `3dd0ae7cd5ea71ef5531f4969926283971ec1c125a97fb43fccb59268e231124` | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 28.495911209000003 |

`PAIR_DELTA=-6.7298163739999985s` vs expected `-7.000000000s`
(`PAIR_ERROR=+0.27018362600000145s`, abs `0.270 <= 1.000`) → **`STRONG`**:
`DEFERRED_PROBE_INITCALL_ENTRY=PROVEN` / `late_text54_entry=PROVEN`. Reaching
the index-54 entry proves late entries 0..53 each returned (sequential
`do_initcall_level` contract) so **`LATEST_PROVEN_LATE_INDEX=54`** and
`NEXT_DIAGNOSTIC_INTERVAL=54..55`. Index 53 is recorded only as that order
implication; it was not directly probed.

`NO_RETURN_WITHIN_120S` did not occur; USB disappearance / adb+fastboot dual
loss / transport anomaly did not occur. Android A restored healthy after each
member; Current B 16-chain + P15 prefix MATCH pre / between / post;
`PARTITION_WRITES=0`; `SLOT_A_WRITTEN=NO`; USB `FROZEN`.
`late_text548` / `late_text541` are rerun-FORBIDDEN.

## Runtime evidence (otherwise unchanged)

`LATE_INITCALLS_COMPLETED`, `WAIT_FOR_INITRAMFS_ENTRY`,
`WAIT_FOR_INITRAMFS_RETURN`, `CONSOLE_ON_ROOTFS`, `INIT_EXECUTED` stay
`NOT_PROVEN`; `LATE_HIGH1` stays `NOT_EXECUTED`. Index 55 remains frozen
`CHECKPOINT_SHIFT_NOT_OBSERVED` and is **not** reread as "did not execute".
No global `.text` allowlist.

## Evidence

`artifacts/slot-b-late-text54-20260920/` — `device-round/` (context.json, host
logs, observer `result.json`/`events.json`, partition snapshots
pre/between/post, set-active records, bootloader preflights, Android A
records, `final-report.txt`), `private/` (downloaded frozen pair + identity
files, not rebuilt). Dirty worktree `/Volumes/LinuxDev/thyme-mainline`
@`5550dc2` untouched. Local builds 0.
