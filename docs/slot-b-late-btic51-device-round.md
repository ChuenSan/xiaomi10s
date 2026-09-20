# Slot B late index-51 BTI-C device pair (2026-09-20)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_INDEX51_BTIC_DEVICE_PAIR`. Device: Xiaomi
Mi 10S (thyme / M2102J2SC) serial `41a5627b`, operated serially by the main
agent from healthy Android A. Final gate:
**`R3_SLOT_B_LATE_INDEX51_BTIC_ENTRY_PROVEN`**.

## Round intent

First true-device pair for additive family `BTI_C_PLUS_56B_ULTRACOMPACT` on
pinned late index 51 `setup_vcpu_hotplug_event`. Prior CI gate
`R3_SLOT_B_LATE_INDEX51_BTIC_PROBE_CI_READY` /
`READY_FOR_LATE_INDEX51_BTIC_DEVICE_PAIR=YES`. Working interval before this
round: `50..55` (`LATEST_PROVEN_LATE_INDEX=50`, `clk_debug_init` ENTRY=PROVEN).
No other probe family. `LATE_HIGH1` stays `NOT_EXECUTED`. `.text` policy is
not relaxed.

## Frozen identities (full SHA, no truncation / no repack)

| Field | Value |
|---|---|
| Public CI | `35484163146` @ `bcddf53` |
| Private pack | `35484634512` @ private `523614d` |
| Independent reverify | `35484884319` |
| Identity freeze | `00b06c9` |
| Observer fixtures | `35485189370` family `btic51`, 120 cross-identity rejections |
| Payload 8 | `ae437348164e2ccaa47e4ba238576b6ab05bfda23bd63f18bda48f161b3f88ef` |
| Payload 1 | `49b9499d2656b7b8b16d39dc9863eb743a1e570a5ee544aea95b6a3a6b4f920e` |
| Boot 8 | `d0e4cce815132336f0bf03362ceedfb74e4b8169f261b286f86e9d1b057e7796` (37380096) |
| Boot 1 | `5537966445c3bce09f9c51dd2ab85271bec97a1d29a51d67826f2e85ff5994dd` (37380096) |
| Geometry | 64 B `.init.text`, window 60, core 56, entry `bti c` preserved, tail 4 B original `ret` `DEAD_PROVEN` |
| Pair diff | `[0x1b8713d,0x1b8713f)` `DELAY_CONSTANT_ONLY` |

## Device pair (RAM-only Slot B, one boot per member)

| Member | Boot identity (frozen) | Behavior | total_s |
|---|---|---|---|
| `BTIC51_8` | `d0e4cce815132336f0bf03362ceedfb74e4b8169f261b286f86e9d1b057e7796` | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 35.551408125 |
| `BTIC51_1` | `5537966445c3bce09f9c51dd2ab85271bec97a1d29a51d67826f2e85ff5994dd` | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 28.333194917 |

`PAIR_DELTA=-7.218213208s` vs expected `-7.000000000s`
(`PAIR_ERROR=-0.218213208s`) → **`STRONG`**:
`SETUP_VCPU_HOTPLUG_EVENT_ENTRY=PROVEN` / `late_btic51_entry=PROVEN`.
Reaching the index-51 entry proves late entries 0..50 each returned
(sequential `do_initcall_level` contract) → **`LATEST_PROVEN_LATE_INDEX=51`**.
`NO_RETURN_WITHIN_120S` did not occur. USB disappearance / adb+fastboot dual
loss did not occur. Current B 16-chain + P15 prefix
(`133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34`) MATCH
pre / between / post; Android A restored healthy after each member (`_a`,
`4.19.157-perf-g9d90dd04aa7c`, `sys.boot_completed=1`); `PARTITION_WRITES=0`;
`SLOT_A_WRITTEN=NO`; USB `FROZEN`. Hashing used `adb shell -T` + device-side
`sha256sum` only. `late_btic518`/`late_btic511` are rerun-FORBIDDEN.

## Runtime evidence (otherwise unchanged)

`LATE_INITCALLS_COMPLETED`, `WAIT_FOR_INITRAMFS_ENTRY`,
`WAIT_FOR_INITRAMFS_RETURN`, `CONSOLE_ON_ROOTFS`, `INIT_EXECUTED` stay
`NOT_PROVEN`. `LATE_HIGH1` stays `NOT_EXECUTED`. Next diagnostic interval:
**`51..55`**. Next research priority (new authorized round): index 52
`boot_wait_for_devices` 48 B — whether an independent `<=48B` INLINE
diagnostic core can be established. This round does **not** auto-switch to
index 54 `.text`.

## Evidence

`artifacts/slot-b-late-btic51-20260920/` — `ci/map-and-audits`,
`private/pack.log` + `reverify.log` + downloaded frozen pair,
`observer/`, `device-round/` (context.json, host logs, observer
`result.json`/`events.json`, partition snapshots pre/between/post,
set-active records, android-a records, this report). Dirty worktree
`/Volumes/LinuxDev/thyme-mainline` @`5550dc2` untouched. Local builds 0.
