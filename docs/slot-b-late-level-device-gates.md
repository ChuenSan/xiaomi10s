# Slot B late-level (level-7) MID/LOW/HIGH device gates (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION`. Status: gate
infrastructure authored, GHA runs and device rounds pending. Source round and
selection policy: `docs/slot-b-late-level-isolation.md`; this runbook covers
the private pack, reverify, identity freeze, observer fixtures and the device
split pair for the three families.

## Families and frozen geometry (predicted selections, pending GHA confirmation)

| Family | Members | Nominal index | Selected target | Target VA / offset | Size | Window | Core | Pair diff |
|---|---|---|---|---|---|---|---|---|
| `late_mid` | `LATE_MID8` / `LATE_MID1` | 43 | `integrity_fs_init` | `0xffff800081b5bd1c` / `0x1b5bd1c` | 112 | 60 | 56B ultracompact | `[0x1b5bd29,0x1b5bd2b)` |
| `late_low` | `LATE_LOW8` / `LATE_LOW1` | 21 | `kexec_core_sysctl_init` | `0xffff800081b47510` / `0x1b47510` | 60 | 60 | 56B ultracompact | `[0x1b4751d,0x1b4751f)` |
| `late_high` | `LATE_HIGH8` / `LATE_HIGH1` | 64 | `bpf_kfunc_init` (deviation distance 1) | `0xffff800081baa15c` / `0x1baa15c` | 260 | 60 | 56B ultracompact | `[0x1baa169,0x1baa16b)` |

Nominal 64 `init_subsystem` is rejected (`TARGET_NOT_INIT_TEXT:.text` +
`FUNCTION_TOO_SMALL`, 40B `.text`); the nearest-safe fallback is index 63.
Each pair differs from the frozen FIX8 base in exactly one 60-byte window and
the two members differ from each other in exactly two bytes — the CNTPCT delay
constant, `PAIR_DIFF=DELAY_CONSTANT_ONLY`, expected device `PAIR_DELTA=-7.000s`
(`STRONG |error| <= 1.000s`, `SUPPORTED |error| <= 2.000s`). Any geometry drift
against this table fails the gates closed; it is never adapted silently.

## Gate order (per family; families are independent)

1. Public CI `thyme-slot-b-late-level-isolation.yml` — source tests, late map,
   MID/LOW/HIGH selection, three `DELAY_CONSTANT_ONLY` payload pairs
   (artifact `thyme-late-level-isolation-pairs`, payload-only, no images).
2. Private pack `thyme-slot-b-late-level-{mid,low,high}-private-gate.yml`
   (`reverify_only=false`) — verifies both members against the frozen FIX8
   envelope (`scripts/late-level-pair-private-gates.py`), splices each payload
   into a 37380096-byte boot image (P15/vendor envelope unchanged) and uploads
   `thyme-late-level-{mid,low,high}-private-pair` with `pair-identity.txt`
   (`LATE_<F>8_BOOT_SHA256` / `LATE_<F>1_BOOT_SHA256` / sizes / diff ranges).
3. Independent reverify `reverify_only=true` on the same workflow — re-extracts
   and re-verifies the frozen pair without rebuild or repack.
4. Identity freeze — the round owner commits the six boot SHAs into
   `scripts/slot_b/late_level_observer_fixtures.py` (`LATE_<F>8_SHA` /
   `LATE_<F>1_SHA` plug-in points) and, for the device round, registers the
   members in `scripts/slot_b/observe.py` (`IMAGES`, `PAIRS`, geometry,
   `pair_verdict` routes). A family stays unrunnable until frozen.
5. Observer fixtures `thyme-slot-b-late-level-observer-fixtures.yml`
   (`family=mid|low|high`) — each member observer accepts only its own full
   boot SHA256 (+size+geometry+diff-range) and rejects the sibling member, the
   wrong-delay mutant, every frozen older image (POST51..CONSOLE families) and
   geometry/diff mutants.
6. Device split pair (section below) — one RAM-only boot per member, 8s member
   first.

A family that fails any gate stops; the next family must not start from its
failure.

## Device round (execution split REQUIRED)

Exactly one RAM-only `fastboot boot` per member. Order: `LATE_MID8` then
`LATE_MID1` (analogously `LATE_LOW8` then `LATE_LOW1`, `LATE_HIGH8` then
`LATE_HIGH1`). The two members are booted from the same authorized bootloader
session, separated by the full hard-gate re-check; each member returns through
the proven stock P15 recovery image (`AUTOMATIC_FASTBOOT_RETURN`, Slot B).

Hard gates before EVERY member boot (fail closed, no retry):

- Android A healthy via `adb` (stock 4.19.157, slot `_a`) before entering the
  bootloader; the round starts from healthy Android A, and Android A must be
  healthy again after each member returns.
- Current B 16-chain hashes MATCH and the P15 prefix
  (`133e063b…87d34`) MATCH, verified pre / between / post.
- Partition writes = 0; Slot A untouched (never written, erased or formatted);
  Slot B reached only via `--set-active` (persistent boot state, no image
  write).
- Full boot SHA256 + size identity match against the frozen private identities
  before any fastboot interaction (observer identity gate first).
- Timing is taken only from the observer `total_s` — never from wall-clock
  notes. Hashing only via `adb shell -T` + device-side `sha256sum`; never
  `adb exec-out` binary or hash.

Stop conditions (any one aborts the round, no member boot, no retry):

- artifact or observer mismatch (wrong image, wrong size, wrong SHA, geometry
  or diff-range drift, observer fixture failure);
- `Booting FAIL` from fastboot or a failed/timeout boot acceptance;
- Current B mismatch (16-chain or P15 prefix) at any check point;
- Android A restore failure after a member boot;
- a repack being needed for any reason;
- any probe-mechanism change (trampoline, island, PREL32 retarget, shared
  checkpoint, cross-function overwrite);
- any partition write being needed.

## Evidence semantics

- `STRONG` (`|PAIR_DELTA - (-7.0)| <= 1.0s`) records exactly
  `<TARGET>_ENTRY=PROVEN` for `<TARGET>` ∈ {`LATE_MID`, `LATE_LOW`,
  `LATE_HIGH`} — the selected late initcall entry was reached after all
  earlier late initcalls. It does NOT prove the target body returned, later
  late initcalls, `late_initcalls_completed`, `wait_for_initramfs_return`,
  `console_on_rootfs_entry` or `/init`.
- No shift between the pair members records ONLY
  `<TARGET>_CHECKPOINT_SHIFT_NOT_OBSERVED` (e.g.
  `late_mid_checkpoint_shift_not_observed=YES`). It is NEVER recorded as
  `TARGET_NOT_REACHED`: absence of a shift is not evidence of non-entry, never
  upgrades the frozen `kernel_do_mounts_initrd_sysctls_init_ENTRY=PROVEN`, and
  never contradicts the WAITENTRY `SHIFT_NOT_OBSERVED`.
- Each member is rerun-FORBIDDEN after its single boot, regardless of verdict.
- Adaptive rule: a second family's pair may run in the same authorized round
  only if that family passed ALL gates (public CI, private pack, independent
  reverify, identity freeze, observer fixtures). A family that failed any gate
  waits for a new authorized round after the cause is fixed.

A `late_mid` STRONG together with a `late_low` no-shift localizes the stall
between indices 21 and 43; the next rerun bisects the unproven half (and so on
for quarters). Family results compose only through this bracket logic — no
family's verdict upgrades another's.
