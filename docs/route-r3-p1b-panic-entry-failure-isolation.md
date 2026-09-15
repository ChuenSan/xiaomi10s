# Route R3 P1B PANIC_ENTRY failure isolation / delay-pair redesign

Round: `MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI`.
CI / SOURCE AUDIT / DIAGNOSTIC REDESIGN / ARTIFACT READINESS ONLY.
`DEVICE_OPERATION=NO`, `ADB_DEVICE_OPERATION=NO`,
`FASTBOOT_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`,
`LOCAL_BUILD=NO` (all builds, binary validation and fixtures are GitHub Actions
only). mem0 was read at the start of the round.

This document records the failure-isolation analysis of the PANIC_ENTRY-8
negative and the delay-pair redesign that replaces the old absolute-time
discriminator. It does **not** authorise any device run: the pair candidate
needs its own explicit user approval.

## 1. PENTRY8 true-device result (frozen)

`MAINLINE_V2_R3_P1B_PANIC_ENTRY_TRUE_DEVICE_CONTROL` ran exactly ONE
identity-gated `fastboot boot` of the frozen PANIC_ENTRY-8 boot
`5e92af2f90b86b875f646c451b573044906afe65dfe4a1786b00e1f8a451ecfe` /
`37380096` (payload
`1988ee22806cba6129f7c3bb34def9667ec39c60f029c622f60341374cc35469`).

- `AUTOMATIC_ANDROID_RETURN=YES`
- `PANIC_ENTRY_TOTAL=26.829s`
- `PANIC_ENTRY_MINUS_C_DELAY=+12.365s`
- `PANIC_ENTRY_MATCHED_SUBCLASS=NO`
- observation window 122 s, no stable fastboot, no hang, no manual recovery
- `ANDROID_A_RESTORED=YES`, `CURRENT_B_UNCHANGED_AFTER_PANIC_ENTRY=YES`

## 2. Frozen decoder verdict (authoritative)

The decoder frozen BEFORE the run bands as: STRONG DISTINCTIVE
`AUTOMATIC_ANDROID_RETURN` AND `TOTAL < 20.000s`; SUPPORTED
`20.000s <= TOTAL < 23.000s`; natural `[23.0, 28.0)s`.

`26.829s` lands in the natural band, so the authoritative gate remains

```
PANIC_ENTRY_SIGNATURE_NOT_OBSERVED
R3_P1B_PANIC_ENTRY_SIGNATURE_NOT_OBSERVED
```

Rules are not modified after the result. `PANIC_ENTRY_REACHED=NOT_PROVEN`,
`LINUX_PANIC_FUNCTION_RUNTIME_STATUS=NOT_PROVEN`.

## 3. Prose / decoder boundary mismatch

`PANIC_ENTRY_VERDICT_TEXT_BOUNDARY_MISMATCH=YES`. The human protocol prose
described the natural class as "23-26s"; the operational band frozen in the
observer decoder before the run is `[23.0, 28.0)s`. `26.829s` is inside the
frozen band, and is `+0.540s` above the historical PANIC30 sample (`26.289s`).
Where the two disagree the **decoder frozen values win** and the result is
never reinterpreted. The mismatch is recorded so the prose is corrected here.

## 4. Negative evidence limitation

`PANIC_ENTRY_NOT_REACHED_LICENSE=NO` always. A PENTRY8 negative signature
cannot distinguish a **late** panic entry from **no** panic entry; it never
licenses `NO_LINUX_PANIC` or `PANIC_NOT_REACHED`. The PENTRY8 result is
recorded as

```
PENTRY8_RESULT=SIGNATURE_NOT_OBSERVED
PENTRY8_IDENTIFICATION_POWER=INSUFFICIENT_FOR_LATE_ENTRY
```

Both statements hold at the same time.

## 5. Late-entry aliasing model

If the checkpoint executes, the total is
`Ttotal8 ~= Tpanic + 8s + common reset/observer overhead`. A `Tpanic` near
18-19 s therefore reproduces a 26-27 s total with **no** probe execution
required. Hence `PENTRY8_LATE_ENTRY_ALIASING_POSSIBLE=YES`. This proves only
that the old discriminator has an alias - it does **not** prove panic was
reached. Static source cannot derive `Tpanic`
(`LATE_PANIC_ENTRY_EXACT_TIME=TIMING_NOT_SOURCE_DERIVABLE`); any arithmetic
such as `26.829s - 8.108s = 18.721s` is post-hoc and is not licensed evidence.

## 6. Why a delay pair

The unknown `Tpanic` cancels in a difference between two candidates that share
everything except the programmed diagnostic delay. The old absolute `< 20s`
gate does not control `Tpanic`; the pair delta does.

## 7. Why 1s and not 0s

`1s` keeps the `CNTFRQ_EL0` / `CNTPCT_EL0` read path, the polling control-flow
shape, the compare semantics and the reset primitive identical to
PANIC_ENTRY-8, so the pair stays a true delay-only comparison. A `0s`
immediate-reset variant would change the structure and is not used
automatically.

## 8. Pair causal model

```
PENTRY_PAIR_EXPECTED_DELTA = 1s - 8s = -7.000s
```

The delta is independent of `Tpanic` and of the observer/reset overhead, which
cancels as well if both members are measured the same way.

## 9. PENTRY1 binary identity

Built from scratch from the authoritative FIX8 normal payload - never by
patching the packed PENTRY8 image. Same symbol, same placement.

- canonical symbol `panic`, `kernel/panic.c`, `__noreturn` `__cold`,
  `EXPORT_SYMBOL`
- link VA `0xffff8000810b99bc`, Image/file offset `0x10b99bc`, section `.text`
  flags `AX`, size `0x344`
- probe window `[0x10b99bc, 0x10b9a0c)`, 80 bytes, entry word0 `paciasp`
  (`0xd503233f`) emitted verbatim
- `PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE`,
  `PENTRY1_PACIASP_HANDLING_IDENTICAL_TO_PENTRY8=YES`
- only intentional variable: `movz x10, #1` (`0xd280002a`) instead of
  `movz x10, #8` (`0xd280010a`)
- `PENTRY1_TIMER_ALGORITHM_IDENTICAL_TO_PENTRY8=YES`,
  `PENTRY1_RESET_CORE_IDENTICAL_TO_PENTRY8=YES`
  (PSCI `SYSTEM_RESET` fid `0x84000009`, `smc #0`, `wfe` forever on any return)
- `PENTRY1_INDEPENDENT_OF_PANIC_TIMEOUT=YES`: no `panic_timeout` read, no
  `mdelay`/`udelay`, no `loops_per_jiffy`, no stack, no loads, no stores, no
  MMIO, `PANIC_ENTRY_RUNTIME_RELOCATIONS=0`, `PANIC_ENTRY_FAIL_CLOSED`,
  `PANIC_ENTRY_STACK_USAGE=NO`
- `PENTRY1_ONLY_ACTIVE_DIAGNOSTIC=YES`: `ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED`
  (T0/T1/T2/T3/T4/C_DELAY windows byte-identical to FIX8),
  `PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8`

## 9a. Inherited frozen diagnostic gates (unchanged by the pair)

The PENTRY1 candidate re-applies the whole PANIC_ENTRY-8 gate set verbatim;
the pair changes the delay immediate only.

- `PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE`
- `PANIC_ENTRY_INLINE_OVERWRITE_SAFE=YES` (and `PENTRY1_INLINE_OVERWRITE_SAFE=YES`)
- `PANIC_ENTRY_LANDING_REQUIREMENT=PRESERVE_ENTRY_WORD_ADDRESS_TAKEN_NO_BTI_PAD`
  (entry word re-emitted verbatim, no unproven `bti c` claim)
- `PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_OF_PANIC_TIMEOUT=YES`
- `PANIC_ENTRY_CNTPCT_SAFE=YES` (EL1-legal `CNTFRQ_EL0`/`CNTPCT_EL0` reads,
  no counter-trap write on the pre-checkpoint path)
- `PANIC_ENTRY_PSCI_SAFE=YES` (`SYSTEM_RESET` fid `0x84000009` carries no
  pointer argument; `smc` is synchronous to EL3)
- `PANIC_ENTRY_FAIL_CLOSED=YES`, `PANIC_ENTRY_STACK_USAGE=NO`,
  `PANIC_ENTRY_RUNTIME_RELOCATIONS=0`
- `ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=YES`,
  `PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8=YES`,
  `PANIC_ENTRY_RUNTIME_SEMANTIC_DELTA=PANIC_ENTRY_CHECKPOINT_ONLY`

Reference values carried forward unchanged: `C_DELAY_TOTAL=14.464`,
early class limit `20.000`, `DTB_OFFSET=0x2380000`, PSCI fid `0x84000009`.

## 10. Pair byte diff (gate)

Expected pair forensic product, asserted by the pair-audit CI job:

```
PENTRY_PAIR_DIFF_BYTE_COUNT=2
PENTRY_PAIR_DIFF_RANGES=[0x10b99cc, 0x10b99ce)
PENTRY_PAIR_CHANGED_INSTRUCTIONS=[4]
PENTRY_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY
```

Any other difference (PSCI FID, `smc`, fail-closed branch, entry word, probe
placement, timer algorithm) is a hard failure. The payload attribution gates
are `PENTRY1_VS_FIX8_ATTRIBUTION=PANIC_ENTRY_CHECKPOINT_ONLY` and
`PENTRY1_VS_PENTRY8_ATTRIBUTION=DELAY_CONSTANT_ONLY`.

## 11. Runtime rewrite re-verification

Re-confirmed for the PENTRY1 payload: no `alternatives`, jump-label,
static-call, `ftrace`, relocation, `__ex_table` or kcfi target overlaps the
window; no branch target enters it. `PENTRY1_INLINE_OVERWRITE_SAFE=YES`. The
window lies inside `IMAGE_HEADER_IMAGE_SIZE=0x2230000`; geometry is read from
the FINAL BINARY HEADER (`IMAGE_FILE_SIZE=35166720`, `DTB_OFFSET=0x2380000`,
payload `37369041`, boot `37380096`).

## 12. Canonical panic audit re-check

Still valid: `PANIC_CANONICAL_ENTRY_UNIQUE` holds (0 aliases, 0
`.isra`/`.constprop` clones, 0 fragments), 204 direct `BL` callsites, 0 direct
`B`, 1 address-taken reference from `EXPORT_SYMBOL`.
`PANIC_CANONICAL_ENTRY_AUDIT_STILL_VALID=YES`.

## 13. Alternative reset path map (source only)

`PANIC_ALTERNATIVE_RESET_PATH_MAP`. Source map only; **no** artifact is
generated for these paths this round and firmware behaviour is never asserted
as fact. Evidence classes: `SOURCE_SUPPORTED`, `INFERRED`, `UNKNOWN`.

| path | source | stage | after C_DELAY | calls panic | could explain 23-28 s |
| --- | --- | --- | --- | --- | --- |
| `emergency_restart` | `kernel/reboot.c` | any | YES | NO | YES |
| `kernel_restart` | `kernel/reboot.c` | any | YES | NO | YES |
| `do_kernel_restart` | `kernel/reboot.c` | any | YES | NO | YES |
| `machine_restart` | `arch/arm64/kernel/process.c` | any | YES | NO | YES |
| PSCI `SYSTEM_RESET` callers | `drivers/firmware/psci/psci.c` | any | YES | NO | YES (primitive already device-proven) |
| `orderly_reboot` | `kernel/reboot.c` | post-init | YES | NO | INFERRED |
| `nmi_panic` | `kernel/panic.c` | any | YES | YES | YES (through `panic()`) |
| `die` / oops | `arch/arm64/kernel/traps.c` | any | YES | conditional | YES |
| BUG / WARN escalation | `kernel/panic.c` | any | YES | conditional | YES |
| `reboot_notifier_list` | `kernel/reboot.c` | any | YES | NO | INFERRED |
| `__weak machine_restart` hook | `kernel/reboot.c` | any | YES | NO | INFERRED |
| arch reset hooks / `machine_shutdown` | `arch/arm64/kernel/process.c` | any | YES | NO | INFERRED |
| Linux-visible watchdog | `kernel/watchdog.c` | post-init | PARTIAL | config-dependent | INFERRED |
| Qualcomm watchdog / APCS | in-tree DT + vendor driver | firmware/EL3 | UNKNOWN | NO | UNKNOWN |
| EL3 / ABL reset | outside the kernel image | firmware | UNKNOWN | NO | UNKNOWN |

`PANIC_ALTERNATIVE_RESET_PATH_HIGH_PRIORITY=emergency_restart,kernel_restart,do_kernel_restart,machine_restart,psci_system_reset_callers`
- these are the paths that can end the boot after the C_DELAY checkpoint
**without** entering `panic()`, and are therefore the primary competing
explanation for the 23-28 s automatic return.

## 14. Watchdog / firmware audit (strict evidence split)

`WATCHDOG_LINUX_VISIBLE_REGISTRATION_PROVEN=NO` in the current boot path and
`FIRMWARE_RESET_BEHAVIOUR_CLAIMED_AS_FACT=NO`. Any Qualcomm/EL3 watchdog or
ABL automatic fallback that is not provable from the in-tree source stays in
the `UNKNOWN` class; it is never promoted to a fact by inference.

## 15. oops/die escalation map

`OOPS_DIE_PANIC_ESCALATION_MAP_COMPLETE=YES`.
`oops_enter`, `die`, `bug_handler` and warn escalation call `panic()` only
conditionally (`panic_on_oops`, `panic_on_warn`, `warn_limit`);
`OOPS_DIE_PANIC_ESCALATION_PANIC_CONDITIONAL_ONLY=YES`. No in-tree oops/die
path restarts the machine directly
(`OOPS_DIE_DIRECT_RESTART_WITHOUT_PANIC=NO_IN_TREE`): in-tree they hang or wait
for an external/firmware reset.

## 16. Possible failure interval after C_DELAY

`PANIC_AFTER_C_DELAY_POSSIBLE=YES`: `panic()` is reachable from `rest_init`,
`kernel_init`, the initramfs `/init` path and from any later call site, so a
late panic entry is source-plausible
(`LATE_PANIC_ENTRY_HYPOTHESIS_SOURCE_PLAUSIBLE=YES`). The exact instant is
`LATE_PANIC_ENTRY_EXACT_TIME=TIMING_NOT_SOURCE_DERIVABLE` - no time estimate
is fabricated here.

## 17. PENTRY8 reinterpretation discipline

`26.829s` is NOT reinterpreted as a positive. Both of these hold:

```
PENTRY8_RESULT=SIGNATURE_NOT_OBSERVED
PENTRY8_IDENTIFICATION_POWER=INSUFFICIENT_FOR_LATE_ENTRY
```

## 18. Private packaging, reverify and observer (this round)

- PRIVATE: ONE PENTRY1 boot v3 image packed from the public PENTRY1 payload in
  the exact M5D envelope. No PENTRY8 repack, no PANIC30 artifact, no
  timeout-branch artifact.
- PRIVATE reverify: a second, independent reverify-only run over the pack
  artifact - boot SHA, payload extraction, panic window, the 1s delay encoding,
  the PENTRY8/PENTRY1 pair diff, RT-D, trampoline, `/init`, initramfs, geometry
  and envelope. `PENTRY1_PRIVATE_IDENTITY_REVERIFIED=YES`.
- Observer: a PENTRY1-specific observer with a FULL PENTRY1 boot SHA gate
  BEFORE any fastboot interaction, refusing PENTRY8 / C_DELAY / T0 / T1 / T2 /
  T3 / T4 / FIX8 / PANIC30 / old INIT8 / entry-state probe. Prepared, **not
  run**.
- Frozen inputs reused unchanged: RT-D
  `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
  (`panic=5`, `rdinit=/init`; the PANIC30 RT-D is forbidden), trampoline
  `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`,
  `/init` `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d`,
  initramfs `02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3`.

## 19. Pair verdict windows (frozen before any PENTRY1 device run)

| key | value |
| --- | --- |
| `PENTRY1_DELAY_SECONDS` | `1` |
| `PENTRY_PAIR_EXPECTED_DELTA` | `-7.000s` |
| PAIR STRONG | `abs(PAIR_DELTA + 7.000s) <= 1.000s` |
| PAIR SUPPORTED | `<= 2.000s` |
| absolute `TOTAL < 20.000s` | SECONDARY supporting signature only |
| natural `23-28s` | secondary-negative-supporting class |

Case PAIR-A STRONG: `PANIC_ENTRY_DELAY_PAIR_SIGNATURE=STRONG`,
`PANIC_ENTRY_REACHED=PROVEN`, `LINUX_PANIC_FUNCTION_INVOKED=PROVEN`, final gate
`MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_PROVEN`. The PENTRY1 absolute time
is **not** required to be exactly 19.829 s; the pair delta governs.

Case PAIR-B SUPPORTED: `STRONGLY_SUPPORTED` only, never `PROVEN` without extra
direct evidence.

Case PAIR-C no shift: `PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED`, next stage
`MAINLINE_V2_R3_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI`.

Other pair outcomes (ambiguous timing, stable fastboot, no return, boot
rejected) route to
`MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_FAILURE_ISOLATION_CI`.

## 20. PANIC30 and timeout-branch discipline

`PANIC30_RERUN=FROZEN`: the delay pair is strictly more controlled than a
`panic=` value difference, so PANIC30 is not re-run. The
`panic_timeout > 0` branch stays `NOT_AUTHORIZED` (and
`PANIC_TIMEOUT_BRANCH_RUNTIME_STATUS=NOT_PROVEN`) until panic entry itself is
identified, because checkpointing the timeout branch while the entry question
is open risks a null experiment.

A pair candidate that cannot be made delay-only, or whose private identity
cannot close, fails closed to
`R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_NOT_READY` - the deliberate opposite of
the per-candidate readiness gates
`READY_FOR_R3_P1B_PANIC_ENTRY_DEVICE_CONTROL` /
`R3_P1B_PANIC_ENTRY_PREDEVICE_NOT_READY`, which belonged to the PANIC_ENTRY-8
round and are not reused here.

`NO_LINUX_PANIC` is never a licensed conclusion from this round or the next
one. WAIT FOR USER APPROVAL.

## 21. CI / artifact readiness result (this round, all gates closed)

`DEVICE_OPERATION=NO` throughout; `PARTITION_WRITES=0`; `SLOT_A_WRITTEN=NO`;
`LOCAL_BUILD=NO` (every build, binary check and fixture ran in GitHub Actions
only). mem0 read at the start of the round.

Public pair CI `34953614443` (attempt 2) on commit
`f23bb8fe5e6b26b8601f1e5695399efba72eaceb`:

| job | result |
| --- | --- |
| `source-audit` (workflow/source/doc gate + isolation audits) | PASS |
| `panic-entry1-build` (PENTRY1 + pair audit + all fixtures) | PASS |
| `independent re-verification` | PASS |

PENTRY1 candidate identity (built from the frozen FIX8 payload, never by
patching the packed PENTRY8 image):

| key | value |
| --- | --- |
| payload | `5fb893c6f990b23a26fe0aba7439852ff5991b59794f4ee4ab1fa7691b8328ee` / `37369041` |
| checkpoint | `61b963d460568edd8ae2e3be9b99badde8d2c96cf863fdd5bf9154c99e1df260` / `80 B` |
| window | `[0x10b99bc, 0x10b9a0c)`, entry0 `paciasp` preserved |
| vs FIX8 | `74` diff bytes, all inside the window, `0` outside → `PANIC_ENTRY_CHECKPOINT_ONLY` |
| vs PENTRY8 | `2` bytes at `[0x10b99cc, 0x10b99ce)`, one instruction (index 4), `0xd280010a -> 0xd280002a` → `DELAY_CONSTANT_ONLY` |
| timer / reset / entry / branch / placement | all identical to PENTRY8 |
| `/init` + initramfs | frozen FIX8 identity (`DELAY_SECONDS=8`) - a second, unintended variable was explicitly rejected |
| `PANIC_CANONICAL_ENTRY_UNIQUE` / aliases / direct `BL` | `YES` / `0` / `204` (`PANIC_CANONICAL_ENTRY_AUDIT_STILL_VALID=YES`) |
| geometry | `IMAGE_FILE_SIZE=35166720`, `IMAGE_HEADER_IMAGE_SIZE=0x2230000`, `DTB_OFFSET=0x2380000`, boot `37380096` |

Private packaging (ONE PENTRY1 boot v3 image, no PENTRY8 repack, no PANIC30 and
no timeout-branch artifact): pack run `34956313932`,
`PENTRY1_PRIVATE_PACK_GATES=PASS`,
`PANIC_ENTRY_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY`,
`PANIC_ENTRY_RT_D_TRAILER_SHA_EXACT=PASS`,
`PANIC_ENTRY_PRIVATE_CORE_DELAY_ONLY_DIFF=PASS`:

```
PENTRY1_BOOT_SHA256=370bc83f746b8e9459022effb07caf6e1a01fb17b1dd33b07c8b8f286f74f2c6
PENTRY1_BOOT_SIZE=37380096
```

Independent private reverify-only run `34956416465` (no repack, no rebuild):
`PANIC_ENTRY_PRIVATE_IDENTITY_REVERIFIED=YES`,
`PANIC_ENTRY_PRIVATE_BOOT_IDENTITY_RECONFIRMED=YES`,
`PANIC_ENTRY_ARTIFACT_REBUILD_REQUIRED=NO`,
`PANIC_ENTRY_PAYLOAD_EXTRACTED_SHA256` = the frozen payload SHA,
`PANIC_ENTRY_INLINE_WINDOW=[0x10b99bc,0x10b9a0c)`,
`PANIC_ENTRY_RT_D_TRAILER_SHA256=4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`,
`PANIC_ENTRY_TRAMP_SHA256=362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`,
`PANIC_ENTRY_GEOMETRY_GATES=PASS`.

Observer `observe-r3-p1b-panic-entry-pair.py` is prepared and its FULL-SHA
identity gate plus misboot refusal list (`PENTRY8` / `C_DELAY` / `T0` / `T1` /
`T2` / `T3` / `T4` / `FIX8` / `PANIC30` / old INIT8 / entry-state probe) pass
their fixtures. It was **not run**.

Final gate:

```
READY_FOR_R3_P1B_PANIC_ENTRY_DELAY_PAIR_DEVICE_CONTROL=YES
```

(fail-closed opposite: `R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_NOT_READY`).
`PANIC_TIMEOUT_BRANCH=NOT_AUTHORIZED`, `PANIC30_RERUN=NO/FROZEN`,
`FIX24_STATUS=FROZEN`, `M5N_STATUS=FROZEN`. Recommended next:
`MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_TRUE_DEVICE_CONTROL` - WAIT FOR
USER APPROVAL.

## 22. Delay-pair TRUE DEVICE result (EXECUTED 2026-09-15 11:20 UTC)

The CI-round text above is frozen. This section records the subsequent
authorised device round. It does not reinterpret PENTRY8.

`MAINLINE_V2_R3_P1B_PANIC_ENTRY_DELAY_PAIR_TRUE_DEVICE_CONTROL` ran exactly
ONE identity-gated `fastboot boot` of frozen PENTRY1
(`370bc83f746b8e9459022effb07caf6e1a01fb17b1dd33b07c8b8f286f74f2c6` /
`37380096`). `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `SET_ACTIVE=NO`,
`SECOND_BOOT_FORBIDDEN=YES`, `PANIC30_RERUN=NO`.

- `AUTOMATIC_ANDROID_RETURN=YES`
- `PENTRY1_TOTAL=26.301s`
- `PAIR_DELTA=-0.528s` vs expected `-7.000s`
- `PAIR_ERROR=+6.472s` (`abs=6.472s` > 2.000s)
- absolute `<20s` SECONDARY=`NO`; natural 23–28=`YES`
- Case PAIR-C: `PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED`
- `PANIC_ENTRY_REACHED=NOT_PROVEN` (never `NO_LINUX_PANIC`)
- panic-entry hypothesis `PRIORITY_REDUCED`
- `ANDROID_A_RESTORED=YES`, `CURRENT_B_UNCHANGED_AFTER_PENTRY1=YES`

Final gate: `R3_P1B_PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED`.
Recommended next: `MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI`.
`PANIC30_RERUN=NO`. WAIT FOR USER APPROVAL.
