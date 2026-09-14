# Route R3 P1B T4 predevice readiness
# C-stage checkpoint candidate (CI / source audit / artifact preparation only)

Round: CI ONLY. `DEVICE_OPERATION=NO`, `ADB_DEVICE_OPERATION=NO`,
`FASTBOOT_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`.
`LOCAL_BUILD=NO`. mem0 was read at the start of the round.
`MEM0_WRITE_INTERFACE_UNAVAILABLE` is recorded if add_memory is not usable.

This round does **not** execute
`MAINLINE_V2_R3_P1B_T4_TRUE_DEVICE_CONTROL`. The fail-closed opposite of a
completed public+private gate remains `R3_P1B_T4_PREDEVICE_NOT_READY`.
Public GHA + private pack + independent reverify + observer FULL-SHA
fixtures have now closed, so
`READY_FOR_R3_P1B_T4_DEVICE_CONTROL=YES`. WAIT FOR USER APPROVAL.


## 1. T3 true-device proof (frozen predecessor)

`MAINLINE_V2_R3_P1B_T3_REACHABILITY_PROVEN`. Case T3-A STRONG.
`T3_TOTAL=14.238s`, `T2_REFERENCE=14.240s`, `T3_MINUS_T2=-0.002s`.
`T1=14.238s`, `T0=14.252s`.

`START_KERNEL_ADDRESS_REACHED=PROVEN`.
`START_KERNEL_ENTRY_PACIASP_EXECUTED=PROVEN`.
`NORMAL_PRIMARY_SWITCHED_TO_START_KERNEL_PATH_EXECUTED=PROVEN`.
`NORMAL_START_KERNEL_BODY_AFTER_ENTRY=NOT_PROVEN`.

R0–R4 PROVEN. R5 normal start_kernel body NOT_PROVEN. R6/R7 NOT_PROVEN.
E0/E1 PROVEN. E2–E4 NOT_PROVEN. E5 FROZEN.

T3 boot `d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df`.
T3 payload `eff9a4a5b47413ec2c9f071158c7162a3361bf6443cbe58b43db7ccd0787e471`.
T3 window `[0x1b303c0,0x1b30410)` INLINE at start_kernel entry.

## 2. Agent B Early C-stage map provenance

`EARLY_C_STAGE_MAP_SOURCE_BRANCH=route-b-r3-c-stage-map`
`EARLY_C_STAGE_MAP_SOURCE_HEAD=d47bf58`
`EARLY_C_STAGE_MAP_SOURCE_BASE=8393db6`
`EARLY_C_STAGE_MAP_SOURCE_RUN=34842580640`
`EARLY_C_STAGE_MAP_INTEGRATION_METHOD=NO_FF_MERGE`
`EARLY_C_STAGE_MAP_INTEGRATION_COMMIT=00df879`

Integrated B commits: `bb8cbe7` `2179d29` `1b0d396` `0784d1f` `2f65dcd`
`8c9bff9` `84383c1` `d47bf58`. `PATH_OVERLAP=` (empty). Map is SOURCE /
STATIC only: not device proof, not device-ready, not T4 authorization.

Linux 6.6.156 `8b73de7da85fde281a385e0b26eda9bffd3ca477`.
Machine-readable `early-c-stage-map.json` is consumed as planner input
(`T4_MAP_JSON_CONSUMED`) and independently re-derived from this round's
vmlinux (`T4_MAP_CRITICAL_POINTS_REDERIVED`). JSON is not the sole truth.

## 3. parse_early_param corrected ordering

Effective `parse_early_param()` is **inside** arm64 `setup_arch()`
(`PARSE_EARLY_PARAM_EFFECTIVE_INSIDE_SETUP_ARCH=YES`):

C2 setup_arch ENTER → C5 parse_early_param COMPLETE → C3 setup_arch RETURN.

The later `parse_early_param()` in `start_kernel` is a done-guard no-op.
Forbidden planning model: setup_arch RETURN → effective parse_early_param.

`loglevel=` is an early_param (C5). `panic=` is `core_param` (C6).
`rdinit=` is `__setup` via `unknown_bootoption` (C6).
`C6_PANIC_PARAMETER_EFFECTIVE_BY_STAGE=YES`.
`C6_RDINIT_PARAMETER_EFFECTIVE_BY_STAGE=YES`.
`LOGLEVEL_EARLY_PARAMETER_STAGE=C5`.

`calibrate_delay` is after C6 (`CALIBRATE_DELAY_AFTER_C6=YES`). C_DELAY is
a high-value later boundary for panic timeout / mdelay wall-clock, **not**
this round's device candidate.

## 4. T4 candidate comparison and selection

| stage | meaning | this round |
| --- | --- | --- |
| C2 | setup_arch ENTER | fallback audit only |
| C3 | setup_arch RETURN | SAFE/UNSAFE by GHA INLINE scans; fallback candidate |
| C6 | parse_args("Booting kernel") COMPLETE | preferred if closed |
| C_DELAY | calibrate_delay COMPLETE | FUTURE |
| C12 | run_init_process("/init") | not first T4; span too large |

Preferred: `T4_SELECTED_STAGE=C6_PARSE_ARGS_COMPLETE` iff instrumentation,
FIX8-identical pre-stage path, probe mapping, diff attribution, negative
explainability and matched-control observer all close.

If any C6 patch/control-flow/layout/inline/branch/mapping/alternatives/
relocation/instrumentation scan cannot close: do not force C6; fall back to
`T4_SELECTED_STAGE=C3_SETUP_ARCH_RETURN`. One device-ready candidate only.

C6 positive (future STRONG) proves normal start_kernel body executed through
ordinary argument parse complete, and that `panic=` / `rdinit=` were consumed
for **this** artifact. Highest information for PANIC30 no-shift. Still does
not prove calibrate_delay, panic mdelay wall-clock, rest_init, initramfs, /init.

C3 positive (future STRONG) proves setup_arch return and (because effective
parse_early_param is inside setup_arch) PARSE_EARLY_PARAM_COMPLETE. ordinary
parse_args / panic= / rdinit= remain NOT_PROVEN CONSUMED.

A C6 proof does **not** auto-write `PANIC30 SHOULD HAVE SHIFTED`. Pre-C6
failure would be excluded. C_DELAY would further tighten the panic timeout
model. Static map does not upgrade R/E/C runtime evidence.

## 5. T4 construction from FIX8 (T3 probe removed)

`T4_START_KERNEL_REDERIVED` from this-round vmlinux nm + System.map.
`T3_PROBE_REMOVED_FROM_T4=YES`.
`START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES` (`paciasp` `0xd503233f` at
start_kernel; T3 80-byte window is gone).
`T4_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES`: trampoline →
primary_entry → __primary_switched → start_kernel → selected stage, byte-
identical to FIX8 except the T4 checkpoint itself.

`T4_CHECKPOINT_IS_POST_STAGE=YES`: C6 = first insn after
`bl parse_args`; C3 = first insn after `bl setup_arch`. Never before the call.
`T4_POSTCALL_CONTROL_FLOW_PROVEN=YES` from this-round disassembly + frozen
payload BL decode, not source line numbers.

`T4_PROBE_ARCHITECTURE=INLINE` in `.init.text` AX. Mapping =
`KERNEL_TEXT_VA_SELF_EVIDENT`. `T4_INLINE_MAPPING_EXECUTABLE=YES`.
`T4_EXTERNAL_CHECKPOINT_USED=NO`. `T4_PADDING_MAPPING_USED=NO`.
T1 padding `0x2230000` is not reused (MMU-on C-stage; unproven cave forbidden).

`T4_ENTRY_INSTRUMENTATION_AUDITED=YES`: PAC/BTI/CFI/SCS/fentry/stack
protector/alternatives/static calls/jump labels/KASAN/KCOV on the selected
window. Mid-function fallthrough: BTI not checked on RET. CFI/ftrace/KASAN/
KCOV/SCS must be off. Jump labels and `apply_boot_alternatives` **have
already run** before C6 (`smp_prepare_boot_cpu` + `jump_label_init` in
`start_kernel`); the checkpoint window must contain **zero** rewrite sites.

Diagnostic: 8s CNTPCT + PSCI SYSTEM_RESET `0x84000009` smc #0, fail-closed
wfe. `T4_CNTPCT_ACCESS_SAFE=YES`. `T4_PSCI_SYSTEM_RESET_SAFE=YES`.
`T4_FAIL_CLOSED=YES`. `T4_STACK_USAGE=NO`. memory reads=NO, writes=NO,
MMIO=NO, `T4_RUNTIME_RELOCATIONS=0`.
`T4_DIAGNOSTIC_CORE_MATCHES_T3=YES` (76-byte T1 core = T3[4:80] = T2[4:80]).
No entry pad (not a function entry).

`T4_RUNTIME_SEMANTIC_DELTA=POST_PARSE_ARGS_CHECKPOINT_ONLY` (C6) or
`POST_SETUP_ARCH_CHECKPOINT_ONLY` (C3). No panic=/rdinit=/RT-D=/init/
initramfs/trampoline/other kernel logic changes.
`T4_PAYLOAD_DIFF_ATTRIBUTED=SELECTED_C_STAGE_CHECKPOINT_ONLY`.
Outside the window: 0 bytes changed.

Frozen identities (all MATCH):
- trampoline `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`
- RT-D `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
- /init `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d`
- initramfs `02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3`

Geometry from FINAL BINARY HEADER (`IMAGE_HEADER_IMAGE_SIZE_REDERIVED`):
authoritative FIX8 `image_size=0x2230000`, file 35166720, `DTB_OFFSET=0x2380000`,
payload 37369041, boot 37380096. Historical `0x2231000` ignored.

## 6. Public / private split, observer, timing

PUBLIC GHA: map reverify, T4 source audit, checkpoint build, ELF / control-flow
audit, payload, diff, negative fixtures, observer fixtures. No OEM boot.img.

PRIVATE GHA: OEM-facing FIX8/M5D envelope + one T4 boot.img. Independent
reverify-only run downloads the frozen T4 boot and does not repack.

Observer is prepared, **not run**. FULL T4 boot SHA gate happens before any
fastboot interaction. Refuses T3/T2/T1/T0/FIX8/PANIC30/other candidates.
`T4_NOT_REACHED_LICENSE=NO`. Failures →
`MAINLINE_V2_R3_P1B_T4_FAILURE_ISOLATION_CI`. STRONG/SUPPORTED next →
`MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI`.

Future timing preregistration (frozen before any device run; not widened to
make a hit easy):

Primary predecessor `T3_TOTAL=14.238s` (same 8s diagnostic core). C3/C6 sit
inside start_kernel after real C-init (`setup_arch` includes FDT/memblock/
paging/`parse_early_param`/`psci_dt_init`; then per-cpu /
`smp_prepare_boot_cpu` / `jump_label_init` / `parse_args`). That work can
add wall time versus T3's start_kernel **entry**. Initial caps:

- STRONG: `|T4_MINUS_T3| <= 1.5`
- SUPPORTED: `<= 3.0`
- `T4_TOTAL < 20s`
- `AUTOMATIC_ANDROID_RETURN=YES`

1.5s STRONG is the recommended initial upper bound, not a hunting window.
Secondary cross-check vs T2=14.240 / T1=14.238 / T0=14.252 within 3.0s.
`T4_PROGRAMMED_ESTIMATE = T4_TOTAL - 6.1445` is SECONDARY only.

## 7. Current evidence (unchanged by this CI-only round)

R0 PROVEN. R1 PROVEN. R2 PROVEN. R3 PROVEN. R4 start_kernel address PROVEN.
R5 normal start_kernel body NOT_PROVEN. E0 PROVEN. E1 PROVEN. E2 NOT_PROVEN.
E3 NOT_PROVEN. E4 NOT_PROVEN. E5 FROZEN.

Current B: M5D+M5H+M5M-B UNCHANGED. FIX24 FROZEN. M5N FROZEN.

`T4_INLINE_OVERWRITE_SAFE`, `T4_FAIL_CLOSED`, `T4_CNTPCT_ACCESS_SAFE`,
`T4_PSCI_SYSTEM_RESET_SAFE`, `T4_STACK_USAGE=NO`, `T4_RUNTIME_RELOCATIONS=0`,
`T4_ENTRY_INSTRUMENTATION_AUDITED` are GHA-gated.

Public path: `.github/workflows/thyme-r3-p1b-t4-predevice.yml`.
Private staging: `artifacts/p1b-t4-private-workflow-staging.yml`.

## 8. Closed identities (this CI round)

Public commit pin `2899ddb00c0b00ca041771620e6f0930cc2c8135`.
Public T4 run `34870647657` (source-gate / map-reverify / t4-build /
independent verify all SUCCESS). Independent map reverify on the
NO-FF merge: `34864074936`. Agent B source run `34842580640` /
HEAD `d47bf58` / integration commit `00df879`.

`T4_SELECTED_STAGE=C6_PARSE_ARGS_COMPLETE`. Candidate C6 SAFE.
Candidate C3 SAFE (unused fallback). Candidate C_DELAY FUTURE.
Callsite `0xffff800081b304a4` `BL parse_args`. Post-call checkpoint
`0xffff800081b304a8` / `0x1b304a8`. `T4_CHECKPOINT_IS_POST_STAGE=YES`.
`T4_POSTCALL_CONTROL_FLOW_PROVEN=YES`. `T4_PROBE_ARCHITECTURE=INLINE`.
`T4_INLINE_OVERWRITE_SAFE=YES`.

T4 payload `64d8f54fd11cc9d4b049ed4a52f5141291cd4c965d25bbf16a8e64670284f76f`
(37369041). Checkpoint 76 B
`4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611`
(byte-identical T1 core / T3[4:] / T2[4:]). Diff 75 bytes, unique
window `[0x1b304a8,0x1b304f4)`,
`T4_PAYLOAD_DIFF_ATTRIBUTED=SELECTED_C_STAGE_CHECKPOINT_ONLY`.
Trampoline / RT-D / `/init` / initramfs MATCH frozen FIX8.

Private pack run `34873775125` SUCCESS. Independent reverify-only
`34873894281` SUCCESS (`T4_PRIVATE_IDENTITY_REVERIFIED=YES`,
`T4_ARTIFACT_REBUILD_REQUIRED=NO`). Frozen T4 boot
`3827fc0fe4216d7d18ccd2a60ea610a6bd10b2afa269e741923ca3bbc566849d`
size 37380096. Envelope `KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY`.
Observer fixtures PASS. Device-round identity env is `R3_T4_SHA256`
equal to that full boot SHA; forbidden set includes T3/T2/T1/T0/
FIX8/PANIC30/OLD_INIT8/ENTRY_STATE_PROBE.

`ORIGINAL_DIRTY_WORKTREE_NOW_BEHIND_REMOTE=YES` (`5550dc2` vs
`route-b-v3`). Original Agent A dirty worktree was not modified.

Recommended next if user approves:
`MAINLINE_V2_R3_P1B_T4_TRUE_DEVICE_CONTROL`.


## 9. TRUE DEVICE T4 C6 RESULT

`MAINLINE_V2_R3_P1B_T4_TRUE_DEVICE_CONTROL` EXECUTED 2026-09-14 22:52 UTC
with explicit user approval. Exactly ONE `fastboot boot` of the frozen T4-C6-8
boot. `SECOND_BOOT_FORBIDDEN=YES`. `PARTITION_WRITES=0`. `SLOT_A_WRITTEN=NO`.
`SET_ACTIVE=NO`. `LOCAL_BUILD=NO`. mem0 read at round start and immediately
before `adb reboot bootloader`.

Case **T4-A STRONG**. Final gate
**`MAINLINE_V2_R3_P1B_T4_C6_REACHABILITY_PROVEN`**.

`T4_TOTAL=14.385s` (cross-check 14.375s). `T3_REFERENCE=14.238s`.
`T4_MINUS_T3=+0.147s` (STRONG `<=1.500s`). `T4_TOTAL<20s=YES`.
`AUTOMATIC_ANDROID_RETURN=YES`. Secondary `T4_MINUS_T2=+0.145s`,
`T4_MINUS_T1=+0.147s`, `T4_MINUS_T0=+0.133s`. Secondary
`T4_PROGRAMMED_ESTIMATE=8.240s` does not override the T4↔T3 verdict.

`T4_TRUE_DEVICE_STATUS=PROVEN`
`C6_RUNTIME_STATUS=PROVEN`
`PANIC_PARAMETER_RUNTIME_STATUS=PROVEN`
`RDINIT_PARAMETER_RUNTIME_STATUS=PROVEN`
`C_DELAY_RUNTIME_STATUS=NOT_PROVEN`
`R5_STATUS=NOT_PROVEN` (full start_kernel body)
`R5_NORMAL_START_KERNEL_BODY_TO_C6=PROVEN`
`NEXT_STAGE=MAINLINE_V2_R3_P1B_C_DELAY_PREDEVICE_READINESS_CI`

C2/C5/C3 implied PROVEN by C6 STRONG. C_DELAY / C12 / R6 / R7 / E2 remain
NOT_PROVEN. `PRE_C6_FAILURE_EXPLANATION_FOR_PANIC30=RULED_OUT`.
`PANIC_TIMEOUT_WALLCLOCK_MODEL=NOT_PROVEN`. C3 fallback / C_DELAY / T5 /
PANIC30 were not executed.

`ANDROID_A_RESTORED=YES`. `CURRENT_B_UNCHANGED_AFTER_T4=YES`.
Device-round record: `artifacts/r3-p1b-t4-34873775125/device-round/`.

