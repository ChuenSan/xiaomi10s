# Route R3 P1B PANIC_ENTRY predevice readiness
# canonical panic() ENTRY reachability candidate (CI / source audit / artifact preparation only)

Round: CI ONLY. `DEVICE_OPERATION=NO`, `ADB_DEVICE_OPERATION=NO`,
`FASTBOOT_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`.
`LOCAL_BUILD=NO`. mem0 was read at the start of the round.

This round does **not** execute
`MAINLINE_V2_R3_P1B_PANIC_ENTRY_TRUE_DEVICE_CONTROL`, does **not** re-run
PANIC30, and does **not** probe any timeout loop. The fail-closed opposite of
a completed public+private gate remains
`R3_P1B_PANIC_ENTRY_PREDEVICE_NOT_READY`. Public GHA + private pack +
independent reverify + observer FULL-SHA fixtures must all close. Final gate:
`READY_FOR_R3_P1B_PANIC_ENTRY_DEVICE_CONTROL=YES`. WAIT FOR USER APPROVAL.

## 1. C_DELAY proof (frozen predecessor)

`MAINLINE_V2_R3_P1B_C_DELAY_REACHABILITY_PROVEN`. Case C_DELAY-A STRONG.
`C_DELAY_TOTAL=14.464s`, `T4_REFERENCE=14.385s`, `C_DELAY_MINUS_T4=+0.079s`.
Boot `d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02`,
payload `372724921ff922dfbf95dcf5081d8527096732a7b402bb63efc01d14f029c52d`.
Checkpoint `4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611`
(76 B @ `0x1b30628`).

C2 setup_arch ENTER, C5 effective `parse_early_param`, C3 `setup_arch` RETURN,
C6 `parse_args("Booting kernel")` COMPLETE, `C_DELAY` `calibrate_delay`
COMPLETE: all PROVEN. `PANIC_PARAMETER_PARSED_BY_RUNNING_KERNEL=PROVEN`.
`RDINIT_PARAMETER_PARSED_BY_RUNNING_KERNEL=PROVEN`.
`CALIBRATE_DELAY_RUNTIME_STATUS=PROVEN`.
`PANIC_MDELAY_CALIBRATION_READY=YES`.

Still NOT_PROVEN: `PANIC_ENTRY_REACHED`, `PANIC_TIMEOUT_LOOP_REACHED`,
`PANIC30_EXPECTED_SHIFT`.

## 2. Current panic model (frozen)

From Linux 6.6.156 `8b73de7da85fde281a385e0b26eda9bffd3ca477`
(`kernel/panic.c`, `include/linux/delay.h`, `include/asm-generic/delay.h`,
`arch/arm64/lib/delay.c`):

- `panic_timeout > 0` -> `for (i = 0; i < panic_timeout * 1000;
  i += PANIC_TIMER_STEP)` with `PANIC_TIMER_STEP=100`, each step
  `mdelay(100)`.
- `mdelay` (`100 > MAX_UDELAY_MS=5`) -> `while (__ms--) udelay(1000)` ->
  arm64 `__const_udelay` -> `__delay(xloops_to_cycles)` waiting on the
  architectural counter.
- `xloops_to_cycles = (xloops * loops_per_jiffy * HZ) >> 32`, so
  `loops_per_jiffy` (assigned by `calibrate_delay`) **scales** the wait.
- `panic_timeout != 0` -> `emergency_restart()`.
- `panic_timeout == 0` -> terminal infinite panic loop, no restart.

Hence `PANIC_MDELAY_CALIBRATION_PREREQUISITE=READY`, which says only that IF
the real failure path reaches the panic timeout wait, its delay prerequisite
is satisfied. It does **not** say the real failure path calls `panic()`.

`PANIC_ALTERNATIVE_RESET_PATH_MAP` (section 38, source-level only):

| path | source |
| --- | --- |
| `emergency_restart` | `kernel/reboot.c` |
| `kernel_restart` | `kernel/reboot.c` |
| `orderly_reboot` | `kernel/reboot.c` |
| `do_kernel_restart` | `kernel/reboot.c` |
| `machine_restart` | `arch/arm64/kernel/process.c` |
| PSCI reset | fid `0x84000009`, `smc #0` (already device-proven T0-T4/C_DELAY) |
| `nmi_panic` | `kernel/panic.c` (calls `panic()`) |
| `die` / oops | `arch/arm64/kernel/traps.c` |
| BUG/WARN escalation | `kernel/panic.c` (`panic_on_warn`, `warn_limit`) |
| watchdog / arch reset hooks | source-mapped, NOT device-ready |

No device-ready artifact is generated for any of these paths this round.

## 3. Why PANIC_ENTRY

The one open question after C_DELAY is whether the early failure path that
currently ends in an automatic Android return actually invokes the canonical
Linux `panic()`. This round prepares a candidate that answers exactly
`PANIC_ENTRY_REACHED` — not the panic body, not the `panic_timeout > 0`
branch, not the mdelay loop, not `emergency_restart`.

## 4. Exact panic symbol

GHA re-derives from the exact source + frozen config + **this round's**
vmlinux (never a history constant): symbol VAs from `llvm-nm` cross-checked
against `System.map`; link VA, Image/file offset, section, section flags,
function size and the entry instruction words are all recomputed. JSON is
planner input only.

Outputs: `PANIC_SYMBOL_REDERIVED=YES`, `PANIC_LINK_VA`,
`PANIC_IMAGE_OFFSET`, `PANIC_FILE_OFFSET`, `PANIC_SECTION`,
`PANIC_SECTION_FLAGS`, `PANIC_SIZE`.

## 5. Canonical-entry audit

Source (`PANIC_SOURCE_FILE=kernel/panic.c`):
`PANIC_FUNCTION_DECLARATION=void panic(const char *fmt, ...) __noreturn __cold;`
(`include/linux/panic.h`), `PANIC_NORETURN=YES`, `PANIC_COLD=YES`,
`EXPORT_SYMBOL(panic)`. The body has no `return`.

Alias / clone audit on the final vmlinux:
`PANIC_FRAGMENT_COUNT` (`.cold` / `.part` fragments of the same canonical
function), `PANIC_CLONE_ENTRY_COUNT` (`.isra` / `.constprop` — these WOULD be
a second entry point), `PANIC_ALIAS_COUNT` (symbols sharing the `panic` VA).

`PANIC_CANONICAL_ENTRY_UNIQUE=YES|PARTIAL|NO`. A `PARTIAL` result is reported,
not hidden: if the audit cannot statically close uniqueness, a later negative
result must still never be written as `NO_LINUX_PANIC`.

## 6. Callsite / reference classification

Scan of the frozen Image plus relocation data:
`PANIC_DIRECT_CALLSITE_COUNT` (direct `BL`), `PANIC_DIRECT_B_COUNT`,
`PANIC_ADRP_PAGE_REF_COUNT` (independent address-taken witness),
`PANIC_INDIRECT_REFERENCE_COUNT`, `PANIC_ALIAS_COUNT`,
`PANIC_ENTRY_BRANCH_TYPES`.

`PANIC_ADDRESS_TAKEN_METHOD` states the method verbatim: `EXPORT_SYMBOL` is
source-confirmed; a static ADRP page reference is scanned as an independent
witness; relocation **targets** are not enumerated (only relocation
**locations** inside the window are gated). Finding one callsite is never
written up as "all panic paths".

## 7. Entry instructions

At least 32 instructions are dumped from the final vmlinux and frozen as
`PANIC_ENTRY_INSN_0..2` / `PANIC_ENTRY_BYTES_0..2`, plus the original word
`PANIC_ENTRY_ORIGINAL_WORD0`. The frozen FIX8 payload word0 must equal the
freshly rebuilt vmlinux word0 or the round fails.

## 8. PAC / BTI / CFI audit

`PANIC_ENTRY_LANDING_REQUIREMENT` is derived from the REAL evidence:
entry word0 plus the audited arrival set.

- entry0 `bti c` -> `PRESERVE_BTI_C_LANDING_PAD` (re-emitted verbatim).
- entry0 `paciasp` with an address-taken symbol -> 
  `PRESERVE_ENTRY_WORD_ADDRESS_TAKEN_NO_BTI_PAD`; the original word is
  re-emitted, uniqueness is reported `PARTIAL`, and **no** BTI landing claim
  is made.
- entry0 `paciasp` with direct-only arrivals ->
  `PRESERVE_ENTRY_WORD_DIRECT_CALLS_ONLY`.
- entry0 neither `bti c` nor `paciasp` -> `PANIC_ENTRY_LANDING_FAILED`
  (fail-closed: preserving an unknown prologue could touch SP/memory).

`PANIC_ENTRY_PREFIX_PRESERVED` and
`PANIC_ENTRY_LANDING_REQUIREMENT_SATISFIED=YES` are printed, together with
`PANIC_ENTRY_ENTRY_INSTRUMENTATION_AUDITED=YES`. `CONFIG_ARM64_BTI_KERNEL`
must be `y`; `CONFIG_CFI_CLANG`, `CONFIG_SHADOW_CALL_STACK`,
`CONFIG_FUNCTION_TRACER`, `CONFIG_DYNAMIC_FTRACE`, `CONFIG_KASAN`,
`CONFIG_KCOV` must all be absent, else the round fails.

## 9. Runtime rewrite audit

The boot path already ran alternatives, jump-label init, static-call
initialisation and (by exact config) no ftrace. The probe window is therefore
gated against `__ex_table`, `.altinstructions`, `__jump_table`,
`.static_call_sites`, `.kcfi_traps`, plus symbol entries, confirmed branch
targets, relocation locations, literal pools and function extents. Any entry
landing inside the window is `T3_RUNTIME_REWRITE_FAILED`.

`PANIC_ENTRY_RUNTIME_REWRITE_TARGETS=NONE_IN_WINDOW` and
`PANIC_ENTRY_INLINE_OVERWRITE_SAFE=YES` are required before DEVICE READY. If
any active runtime rewrite could overwrite the probe, INLINE is NOT device
ready and the round records `PANIC_ENTRY_PREDEVICE_STATUS=NOT_READY`.

## 10. Probe architecture

`PANIC_ENTRY_PROBE_ARCHITECTURE=INLINE`. panic text is already mapped and
executable, and the checkpoint executes only if the audited canonical panic
symbol is invoked. No prior-round padding, no unproven external cave.
`PANIC_ENTRY_EXTERNAL_CHECKPOINT_USED=NO`,
`PANIC_ENTRY_PADDING_MAPPING_USED=NO`,
`PANIC_ENTRY_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT`.

## 11. Diagnostic independence from panic_timeout

Hard gate. The diagnostic core never reads the timeout variable, never calls
the panic body, and never uses a calibrated busy-wait. It uses only the 8 s
CNTPCT architectural timer, then PSCI `SYSTEM_RESET` (`0x84000009`, `smc #0`),
then `wfe` forever.

`PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_OF_PANIC_TIMEOUT=YES` is enforced twice:
statically (the probe source must not contain the timeout variable name, the
calibrated delay helper names, or `loops_per_jiffy`) and at word level
(`gate_probe_words`). A positive signature therefore proves
`PANIC_ENTRY_REACHED`, not the timeout mechanism.

## 12. Timer / PSCI safety

`PANIC_ENTRY_CNTPCT_SAFE=YES`: `CNTFRQ_EL0`/`CNTPCT_EL0` reads are EL1-legal
with `SCTLR_EL1.M=1`; the identical access was proven on this device at
T0-T4/C_DELAY; panic entry is after `calibrate_delay`, so `time_init` already
ran.
`PANIC_ENTRY_PSCI_SAFE=YES`: `SYSTEM_RESET` fid `0x84000009` carries no
pointer argument; `smc` is synchronous to EL3; `psci_dt_init` already ran in
`setup_arch`; the frozen RT-D keeps `/psci` `method=smc`.

## 13. Fail-closed core

8 s CNTPCT register-only + PSCI `SYSTEM_RESET` `0x84000009` via `smc #0`.
Any `smc` return -> `wfe` forever.
`PANIC_ENTRY_FAIL_CLOSED=YES`, `PANIC_ENTRY_STACK_USAGE=NO`,
`PANIC_ENTRY_NO_MEMORY_READS=YES`, `PANIC_ENTRY_NO_MEMORY_WRITES=YES`,
`PANIC_ENTRY_RUNTIME_RELOCATIONS=0`.
`PANIC_ENTRY_DIAGNOSTIC_CORE_MATCHES_C_DELAY=YES` (byte-identical 76-byte
core) and `PANIC_ENTRY_DIAGNOSTIC_CORE_MATCHES_T1=YES`.

## 14. Prior probe removal

Baseline is FIXED INIT8, not the C_DELAY diagnostic payload.

`ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=YES`,
`T4_PROBE_REMOVED_FROM_PANIC_ENTRY=YES`,
`C_DELAY_PROBE_REMOVED_FROM_PANIC_ENTRY=YES`,
`T3_PROBE_REMOVED_FROM_PANIC_ENTRY=YES`,
`T2_PROBE_REMOVED_FROM_PANIC_ENTRY=YES`. The C6/T4 window and the
post-`calibrate_delay` window are restored to FIX8 bytes
(`C6_REGION_IDENTICAL_TO_FIX8=YES`,
`C_DELAY_REGION_IDENTICAL_TO_FIX8=YES`), `start_kernel` entry returns to the
FIX8 `paciasp` word (`START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES`), and the
trampoline stays byte-identical.

## 15. Normal path identity

`PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8=YES`: trampoline ->
`primary_entry` -> `__primary_switched` -> `start_kernel` -> `setup_arch` ->
`parse_early_param` inside `setup_arch` -> C6 `parse_args("Booting kernel")`
-> `calibrate_delay` -> every instruction up to the moment the kernel itself
calls the canonical panic symbol. Byte-identical to FIX8 except the single
panic-entry window.

Frozen identities MATCH:
- trampoline `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`
- RT-D `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
  keeping `panic=5` and `rdinit=/init` (NOT the PANIC30 trailer)
- /init `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d`
- initramfs `02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3`

## 16. Payload diff attribution

`PANIC_ENTRY_RUNTIME_SEMANTIC_DELTA=PANIC_ENTRY_CHECKPOINT_ONLY` and
`PANIC_ENTRY_PAYLOAD_DIFF_ATTRIBUTED=PANIC_ENTRY_CHECKPOINT_ONLY`: one
contiguous window at the canonical panic entry, `0` changed bytes outside it.

## 17. Geometry

Re-read from the FINAL BINARY HEADER only:
`IMAGE_HEADER_IMAGE_SIZE=0x2230000`, `IMAGE_FILE_SIZE=35166720`,
`DTB_OFFSET=0x2380000`, payload 37369041, boot 37380096. Historical
conflicting readings are ignored.

## 18. Private packaging

PUBLIC GHA run: source audit, canonical-symbol audit, callsite classes,
entry instrumentation, runtime rewrite scan, probe build, payload diff,
negative fixtures, observer fixtures. No OEM-derived boot and no flashable
image is ever emitted from the public repository.

PRIVATE GHA pack: ONE PANIC_ENTRY boot, recorded as
`PANIC_ENTRY_PRIVATE_PACK_RUN`, `PANIC_ENTRY_BOOT_SHA`,
`PANIC_ENTRY_BOOT_SIZE`, `PANIC_ENTRY_PAYLOAD_SHA`. Device: NO OPERATION.

## 19. Reverify

A second, independent private run re-verifies only — it never repacks —
covering boot full SHA, extracted payload SHA, the panic-entry window, prior
probe removal (T0-T4/C_DELAY), RT-D, `/init`, initramfs, geometry and
envelope. `PANIC_ENTRY_PRIVATE_IDENTITY_REVERIFIED=YES`.

## 20. Observer

A PANIC_ENTRY-specific observer is prepared, not run. FULL boot SHA gate
happens strictly before any fastboot interaction, and it refuses C_DELAY,
T4, T3, T2, T1, T0, FIX8, PANIC30, old INIT8 and the entry-state probe.
`PANIC_ENTRY_NOT_REACHED_LICENSE=NO` (always): a negative never licenses
`NO_LINUX_PANIC`. Failures route to
`PANIC_ENTRY_FAILURE_ISOLATION_CI`; PANIC30 is never auto-rerun.

## 21. Natural return baseline

`FIXED_INIT8_TOTAL=23.852s`, `PANIC30_TOTAL=26.289s`; the un-located
automatic-return class is ~23-26 s.

## 22. Timing classification rationale

The panic-entry instant is currently unknown, so this round does **not** use
`|PANIC_ENTRY_TOTAL - C_DELAY_TOTAL| <= 1.5s` as the device-ready gate.
C_DELAY 14.464 s only shows the normal kernel reaches `calibrate_delay`
complete; panic may happen later. If the probe executes, it resets
`8 s` after panic entry, so an early panic entry must shift the total into a
clearly controlled early class well before the natural 23-26 s class.

Preregistered (frozen before any device run):

- STRONG DISTINCTIVE: `AUTOMATIC_ANDROID_RETURN=YES` AND
  `PANIC_ENTRY_TOTAL < 20.000s`.
- VERY_STRONG_MATCHED subclass:
  `-0.5s <= PANIC_ENTRY_MINUS_C_DELAY <= +3.0s` (auxiliary only; a value
  above +3 s but below 20 s is still STRONG, never an automatic negative).
- SUPPORTED: `AUTOMATIC_ANDROID_RETURN=YES` AND `20.000s <= TOTAL < 23.000s`
  (wider causal window that does not overlap the natural class).
- Natural 23-26 s -> `PANIC_ENTRY_SIGNATURE_NOT_OBSERVED`, never
  `NO_LINUX_PANIC`.

`PANIC_ENTRY_MINUS_C_DELAY` is recorded but is not required to be ~0: it
approximately contains the extra normal runtime between the C_DELAY
checkpoint and the actual panic entry.

## 23. Positive and negative boundaries

If a future run is STRONG: `PANIC_ENTRY_REACHABILITY_SIGNATURE=STRONG`,
`PANIC_ENTRY_REACHED=PROVEN`,
`LINUX_PANIC_FUNCTION_INVOKED=PROVEN` for the exact audited canonical
symbol, final gate `MAINLINE_V2_R3_P1B_PANIC_ENTRY_REACHABILITY_PROVEN`.
`PANIC_TIMEOUT_BRANCH_REACHED`, `PANIC_TIMEOUT_WAIT_LOOP_REACHED` and
`EMERGENCY_RESTART_REACHED` stay NOT_PROVEN.

A SUPPORTED run records
`PANIC_ENTRY_REACHABILITY_SIGNATURE=SUPPORTED` and
`PANIC_ENTRY=STRONGLY_SUPPORTED`, and must not be written as PROVEN without
additional direct evidence.

A run that stays in the natural 23-26 s class records
`PANIC_ENTRY_SIGNATURE_NOT_OBSERVED` and must not be written as
`PANIC_NOT_REACHED`. Instrumentation failure, an unexpected rewrite, observer
ambiguity, an alternative reset path and an incomplete canonical-entry audit
all remain possible; the verdict comes from artifact causality **plus**
behaviour class, never from a bare time threshold. Stable-fastboot and
no-return outcomes are recorded separately as
`PANIC_ENTRY_STABLE_FASTBOOT` / `PANIC_ENTRY_NO_RETURN`, both forbidding a
second boot and a PANIC30 rerun.

If this round cannot freeze a reliable pre-device verdict, it records
`PANIC_ENTRY_PREDEVICE_NOT_READY` rather than widening the window to force a
hit.

## 24. Next route

If PANIC_ENTRY is PROVEN, the next stage is
`MAINLINE_V2_R3_P1B_PANIC_TIMEOUT_BRANCH_PREDEVICE_READINESS_CI` (checkpoint
the timeout branch instead of re-running PANIC30). If PANIC_ENTRY is not
observed, the next stage is
`MAINLINE_V2_R3_P1B_PANIC_ENTRY_FAILURE_ISOLATION_CI`, which starts from the
alternative reset map above.

## 25. Negative fixtures (fail-closed)

`WRONG_PANIC_SYMBOL`, `WRONG_CANONICAL_SYMBOL`, `WRONG_ENTRY_OFFSET`,
`LANDING_REQUIREMENT_BROKEN`, `PAC_BTI_RULE_BROKEN`,
`RUNTIME_REWRITE_TARGET_OVERLAP`, `UNSAFE_INLINE_OVERWRITE`, `STACK_USE`,
`MEMORY_STORE`, `MEMORY_LOAD`, `WRONG_8S_CONSTANT`, `WRONG_PSCI_FID`,
`MISSING_SMC`, `FALL_THROUGH`, `RUNTIME_RELOCATION`, `EXTRA_PAYLOAD_DIFF`,
`RT_D_PANIC_CHANGED`, `PRIOR_C_DELAY_PROBE_REMAINS`, `T4_PROBE_REMAINS`,
`NORMAL_PATH_MODIFIED`, `GEOMETRY_MISMATCH`, plus
`PANIC_ENTRY_NEGATIVE_PANIC_TIMEOUT_READ_BY_DIAGNOSTIC_REJECT` and
`PANIC_ENTRY_NEGATIVE_MDELAY_USED_BY_DIAGNOSTIC_REJECT`. All must be rejected
by the real gates.

Public path: `.github/workflows/thyme-r3-p1b-panic-entry-predevice.yml`.
Private staging: `artifacts/p1b-panic-entry-private-workflow-staging.yml`.
Current B: `M5D+M5H+M5M-B` UNCHANGED. `PANIC30_RERUN=FROZEN`,
`FIX24_STATUS=FROZEN`, `M5N_STATUS=FROZEN`.
Final gate: `READY_FOR_R3_P1B_PANIC_ENTRY_DEVICE_CONTROL=YES`
(or `R3_P1B_PANIC_ENTRY_PREDEVICE_NOT_READY`).
