# thyme R3 current status (single source of truth for the current round)

Maintained rule: this file is the ONLY current-state entry. Older docs keep
their historical results and are never rewritten; where an older doc says
"E1/E2 SUPPORTED" or a different "Current B", THIS file wins for current
facts. Last updated: 2026-09-13
(MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI, CI/source-audit-only round;
the last EXECUTED device round remains the one-boot PANIC30 control).

## Current Round

`MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI` — CI / SOURCE AUDIT /
ARTIFACT PREPARATION ONLY, `DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`,
`SLOT_A_WRITTEN=NO`. Goal: freeze the previous round's CHECKPOINT_T0
prototype (whose failsafe fall-through makes it NOT device-ready) into the
unique, frozen, explainable, identity-gateable T0-8 FAIL-CLOSED true-device
diagnostic candidate: 8s CNTPCT register-only checkpoint AFTER x0-x3 setup /
BEFORE the primary_entry branch, PSCI SYSTEM_RESET 0x84000009 smc, wfe
forever on any smc return (no primary_entry continuation),
`T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY`, payload
composed from frozen FIX8 bytes with only the trampoline checkpoint region
[0x40, 0xB0) replaced (`T0_PAYLOAD_DIFF_ATTRIBUTED=CHECKPOINT_REGION_ONLY`,
DTB_OFFSET 0x2380000, payload/boot geometry identical to FIX8). Identity-
gated host observer refuses FIX8/PANIC30/old-INIT8/entry-state-probe boots.
No device operation is authorized by this round. Final gate:
`READY_FOR_R3_P1B_T0_DEVICE_CONTROL` or `R3_P1B_T0_PREDEVICE_NOT_READY`.
Details: docs/route-r3-p1b-t0-predevice-readiness.md.

## Current Gate (last executed device round)

`R3_P1B_PANIC30_TIMEOUT_NOT_OBSERVED` — the single authorized P1B-PANIC30
device boot (UTC 2026-09-13, run record in the isolation doc section 26)
returned automatically to Android A with `PANIC30_TOTAL = 26.289 s` vs the
frozen `FIX8_TOTAL = 23.852 s` baseline: `P30_DELTA = +2.437 s`, far outside
the preregistered SUPPORTED window [23.0, 27.0] (expected +25.000 s,
`P30_ERROR = −22.563 s`) — `NO_SUPPORTED_SHIFT` of the control-return
timeline (Case P30-C:
`PANIC30_TIMEOUT_NOT_OBSERVED_TO_CONTROL_RETURN_TIMELINE=YES`). This does NOT
license `NO_LINUX_PANIC` / `NO_LINUX_ENTRY` / `LINUX_NOT_REACHED`. Behavior:
automatic Android return, no stable Fastboot, no 4.7 s path, no hang, no
manual recovery. Artifact identity fully re-verified before boot (boot
`ea50e8b3…64b1`/37380096, payload `cd3f7527…687e`, RT-D `dfbfca03…3390`,
RT-D semantic delta = bootargs `panic=5` -> `panic=30` only). Constraints
held: `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `SET_ACTIVE=NO`,
`EXPERIMENTAL_BOOTS=1`, `SECOND_BOOT_FORBIDDEN=YES`, T0/T1/T2/FIX24/M5N not
executed. `CURRENT_B_UNCHANGED_AFTER_PANIC30=YES`, `ANDROID_A_RESTORED=YES`.
Checkpoints stay T0 CI_PASS (prototype, superseded by the fail-closed T0-8
candidate this round) / T1 CI_PASS / T2 DESIGNED.

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
  (header image_size 0x2230000 as measured on both the frozen payload and a
  fresh rebuild; file 35166720), /init `f1bc8849…66d`,
  initramfs `02123e98…fff3`, trampoline `362d9c6e…c623`,
  RT-D `48497432…f327` (144593), DTB_OFFSET `0x2380000`,
  Linux base `8b73de7da85fde281a385e0b26eda9bffd3ca477` (6.6.156).
- PANIC30 artifacts (public run 34754072600, commit c001114c, all jobs green):
  RT-D `dfbfca03…3390` (144597 = 144593+4, semantic delta
  PANIC_TIMEOUT_ONLY), payload `cd3f7527…687e` (37369045 = 37369041+4,
  prefix byte-identical to frozen FIX8), boot_size_est 37380096,
  primary_entry 0x1b1c0a0 (re-derived this round), __primary_switched
  0x1b39534, T0/T1 CI PASS, T2 DESIGNED. Audit-correction round: identity
  RE-CONFIRMED from the authoritative manifests (primary 34754072600 ==
  confirmation 34755788727, manifests identical; full SHAs in the isolation
  doc) with NO rebuild — `PANIC30_ARTIFACT_REBUILD_REQUIRED=NO`,
  `PANIC30_BINARY_SEMANTICS_UNAFFECTED_BY_AUDIT_CORRECTION=YES`.
- PANIC30 boot (PRIVATE repo only, private run 34755701908): boot v3
  `ea50e8b3…64b1`, size 37380096, spliced into the exact M5D envelope
  (4db8151b…); pack gates + size cross-check PASS. Device round EXECUTED
  2026-09-13 (identity re-hashed locally before boot, never re-packed):
  `PANIC30_TOTAL = 26.289 s`, `P30_DELTA = +2.437 s` vs FIX8 23.852 s,
  `P30_ERROR = −22.563 s` vs expected +25.000 s, Case P30-C,
  `PANIC30_TIMEOUT_NOT_OBSERVED_TO_CONTROL_RETURN_TIMELINE=YES`,
  `AUTOMATIC_ANDROID_RETURN=YES`, no persistent dump evidence; no upgrade of
  E1–E4 (full record: isolation doc section 26).

## Current B

`M5D + M5H + M5M-B` — UNCHANGED. Active slot A (stock Android) untouched;
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, no set_active, no B boot.

## Frozen branches / items

- M5N: FROZEN.
- FIX24 (24s-delay /init): FROZEN and FORBIDDEN this round.
- USB stage work: FROZEN.
- UFS / rootfs / network: FROZEN.
- PANIC30: diagnostic control EXECUTED as the one authorized device boot
  (panic=5 -> panic=30 on the RT-D trailer); result gate
  `R3_P1B_PANIC30_TIMEOUT_NOT_OBSERVED`; binary frozen, no rebuild; second
  boot forbidden.
- Checkpoints T0/T1/T2: T0/T1 CI PASS, T2 DESIGNED; no checkpoint device run
  executed.

## Next approved candidate

`MAINLINE_V2_R3_P1B_T0_TRUE_DEVICE_CONTROL` — the T0-8 FAIL-CLOSED candidate
frozen this round (identity-gated boot v3 from the private pack; observer
refuses every known wrong boot) as the next single device boot per the
preregistered Case P30-C recommendation; NOT executed this round; the
predevice round can only end at `READY_FOR_R3_P1B_T0_DEVICE_CONTROL`
(prep complete) — the boot itself still requires separate user approval. Per
the frozen interpretation, a T0 positive (triple condition: timer window +
early-return class + automatic Android return) would prove only that the
large P1B artifact was loaded by ABL to an executed location (checkpoint
evidence); it does not by itself upgrade E3/E4. A negative NEVER licenses
T0_NOT_REACHED; it routes to T0_FAILURE_ISOLATION_CI.

## Not-ready candidates

- Any checkpoint (T0/T1/T2) device run: CI prototype/design only.
- FIX24, M5N, USB bring-up, UFS rootfs, network, drivers: frozen.
- CopyMem forensics: priority LOWERED (re-raises only on T0 failure).
- Persistent logging (pstore/ramoops/UART/USB gadget/earlycon): deferred;
  would break single-variable isolation.

## Panic-audit anchors (corrected 2026-09-13)

panic= is a standard boot param (`core_param`, `__section("__param")`, not
early); parsed in `parse_args("Booting kernel")` AFTER setup_arch and
`parse_early_param`. `panic_timeout` default 0 — with 0 the panic path
performs NO wait and NO emergency_restart() and control falls into the
terminal infinite panic loop; `PANIC_NEVER_RETURNS=YES`
(`PANIC_ZERO_TIMEOUT_BEHAVIOR=INFINITE_PANIC_LOOP_NO_AUTOMATIC_RESTART`).
A pre-parse panic therefore cannot restart via the panic path at all and
needs an independent reset mechanism (watchdog/firmware/hardware) to
auto-return: `PRE_PARSE_LINUX_PANIC_ALONE_EXPLAINS_23S_AUTORETURN=NO`. A
post-parse panic obeys panic=30 (timeout wait + emergency_restart) —
`PANIC30_POSITIVE_CONTROL_REMAINS_VALID=YES`. Timeout wait = 100 ms mdelay
loop depending on `loops_per_jiffy` (calibrated only AFTER parse_args ->
`PANIC_TIMEOUT_WALLCLOCK_EXACT_BEFORE_CALIBRATE_DELAY=NOT_GUARANTEED`);
restart path = emergency_restart -> machine_restart -> do_kernel_restart ->
PSCI SYSTEM_RESET (0x84000009) smc, closed under RT-D (`/psci
method="smc"`). Cmdline provenance closed:
`P1B_FINAL_CMDLINE_SOURCE=RT_D_CHOSEN_BOOTARGS_ONLY`,
`DUPLICATE_PANIC_PARAMETER=NO`.

Old timeout-0 reading ("panic() would return to its caller") of the
previous round: `SUPERSEDED_BY_PANIC_AUDIT_CORRECTION`; verbatim history is
preserved in git (96a2cc9..c001114c) and in the fenced history blocks of
docs/route-r3-p1b-panic-checkpoint-isolation.md (section 6a) and
docs/route-r3-p1b-failure-isolation.md (section 12). CI now carries
negative fixtures that FAIL any live re-assertion of that claim.

Round details: docs/route-r3-p1b-panic-checkpoint-isolation.md
