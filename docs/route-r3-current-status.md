# thyme R3 current status (single source of truth for the current round)

Maintained rule: this file is the ONLY current-state entry. Older docs keep
their historical results and are never rewritten; where an older doc says
"E1/E2 SUPPORTED" or a different "Current B", THIS file wins for current
facts. Last updated: 2026-09-13
(MAINLINE_V2_R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_CI, CI/source-audit round).

## Current Gate

`MAINLINE_V2_R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_CI` — CI / source audit
only, no device operation. Intended final gate:
`READY_FOR_R3_P1B_PANIC30_DEVICE_CONTROL` (CI level; any future device round
still needs separate user approval). Fallbacks:
`R3_P1B_EARLY_CHECKPOINT_REQUIRED` / `R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_INCOMPLETE`.

## Evidence ladder (current, conservative)

| level | statement | status |
| --- | --- | --- |
| E0 | ABL -> controlled payload | PROVEN |
| E1 | normal Mainline Linux entry reached | NOT_PROVEN |
| E2 | early Mainline boot | NOT_PROVEN |
| E3 | built-in initramfs reached | NOT_PROVEN |
| E4 | /init executed | NOT_PROVEN |
| E5 | USB | FROZEN |

Side evidence kept behavioral-only (never upgrades E1/E2):
`M5_STYLE_4P7S_PATH_NOT_OBSERVED=YES`,
`AUTOMATIC_ANDROID_RETURN_SIGNATURE=YES`.

## Frozen device facts

- OLD BROKEN INIT8 TOTAL 23.184 s; OLD BROKEN INIT24 TOTAL 24.570 s; pair
  delta 1.386 s vs expected 16.000 s (NO_MATCH; root cause = 3-arg
  clock_nanosleep ABI bug, since fixed).
- FIXED INIT8 TOTAL 23.852 s; exact QEMU /init sleep 8.003 s (ABI4); delta
  vs broken +0.668 s; classification NOT_CONSISTENT_WITH_8S_DELAY;
  `DEVICE_RETURN_PATH_NOT_OBSERVED_TO_FOLLOW_INIT_SLEEP=YES`.
- Persistent evidence never showed explicit mainline lines (pstore empty,
  rawdump/logdump unchanged); absence is not proof of Linux absence (no
  persistent sink exists).
- Frozen hashes: FIX8 payload `4f34eabf…cceb41`, Image `dffce20e…44944`
  (image_size 0x2231000, file 35166720), /init `f1bc8849…66d`,
  initramfs `02123e98…fff3`, trampoline `362d9c6e…c623`,
  RT-D `48497432…f327` (144593), DTB_OFFSET `0x2380000`,
  Linux base `8b73de7da85fde281a385e0b26eda9bffd3ca477` (6.6.156).

## Current B

`M5D + M5H + M5M-B` — UNCHANGED. Active slot A (stock Android) untouched;
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, no set_active, no B boot.

## Frozen branches / items

- M5N: FROZEN.
- FIX24 (24s-delay /init): FROZEN and FORBIDDEN this round.
- USB stage work: FROZEN.
- UFS / rootfs / network: FROZEN.
- PANIC30: diagnostic control only (panic=5 -> panic=30 on the RT-D
  trailer); CI DEVICE-READY at most this round; no device run approved.
- Checkpoints T0/T1/T2: diagnostic reach-and-reset family; CI prototypes /
  design only this round; never mixed with normal boot candidates.

## Next approved candidate

`P1B-PANIC30` (single future device boot against the FIXED INIT8 23.852 s
baseline; pre-registered interpretation: shift [24.0, 26.0] s STRONG /
[23.0, 27.0] s SUPPORTED for PANIC_TIMEOUT_CONTROLS_RETURN_TIMELINE; no
shift -> `PANIC30_TIMEOUT_NOT_OBSERVED_TO_CONTROL_RETURN_TIMELINE=YES` and
the checkpoint ladder starts at T0). Device execution requires explicit user
approval.

## Not-ready candidates

- Any checkpoint (T0/T1/T2) device run: CI prototype/design only.
- FIX24, M5N, USB bring-up, UFS rootfs, network, drivers: frozen.
- CopyMem forensics: priority LOWERED (re-raises only on T0 failure).
- Persistent logging (pstore/ramoops/UART/USB gadget/earlycon): deferred;
  would break single-variable isolation.

## Panic-audit anchors (this round)

panic= is a standard boot param (`core_param`, `__section("__param")`, not
early); parsed in `parse_args("Booting kernel")` AFTER setup_arch and
`parse_early_param`; `panic_timeout` default 0 (pre-parse panic cannot
restart via the panic path); timeout wait = 100 ms mdelay loop depending on
`loops_per_jiffy` (calibrated only AFTER parse_args -> pre-calibration panics
have unreliable wait wall-clock); restart path = emergency_restart ->
machine_restart -> do_kernel_restart -> PSCI SYSTEM_RESET (0x84000009) smc,
closed under RT-D (`/psci method="smc"`). Cmdline provenance closed:
`P1B_FINAL_CMDLINE_SOURCE=RT_D_CHOSEN_BOOTARGS_ONLY`,
`DUPLICATE_PANIC_PARAMETER=NO`.

Round details: docs/route-r3-p1b-panic-checkpoint-isolation.md
