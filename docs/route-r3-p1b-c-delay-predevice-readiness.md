# Route R3 P1B C_DELAY predevice readiness
# calibrate_delay COMPLETE candidate (CI / source audit / artifact preparation only)

Round: CI ONLY. `DEVICE_OPERATION=NO`, `ADB_DEVICE_OPERATION=NO`,
`FASTBOOT_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`.
`LOCAL_BUILD=NO`. mem0 was read at the start of the round.

This round does **not** execute
`MAINLINE_V2_R3_P1B_C_DELAY_TRUE_DEVICE_CONTROL`. The fail-closed opposite of
a completed public+private gate remains `R3_P1B_C_DELAY_PREDEVICE_NOT_READY`.
Public GHA + private pack + independent reverify + observer FULL-SHA
fixtures closed. Final gate: `READY_FOR_R3_P1B_C_DELAY_DEVICE_CONTROL=YES`.
WAIT FOR USER APPROVAL.

## 1. T4 proof (frozen predecessor)

`MAINLINE_V2_R3_P1B_T4_C6_REACHABILITY_PROVEN`. Case T4-A STRONG.
`T4_TOTAL=14.385s`, `T3_REFERENCE=14.238s`, `T4_MINUS_T3=+0.147s`.

C2/C5/C3 implied PROVEN. `C6_RUNTIME_STATUS=PROVEN`.
`PANIC_PARAMETER_RUNTIME_STATUS=PROVEN`.
`RDINIT_PARAMETER_RUNTIME_STATUS=PROVEN`.
`NORMAL_START_KERNEL_BODY_TO_C6_EXECUTED=PROVEN`.
`PRE_C6_FAILURE_EXPLANATION_FOR_PANIC30=RULED_OUT`.
`C_DELAY_RUNTIME_STATUS=NOT_PROVEN`.
`PANIC_TIMEOUT_WALLCLOCK_MODEL=NOT_PROVEN`.

T4 boot `3827fc0fe4216d7d18ccd2a60ea610a6bd10b2afa269e741923ca3bbc566849d`.
T4 payload `64d8f54fd11cc9d4b049ed4a52f5141291cd4c965d25bbf16a8e64670284f76f`.
T4 window `[0x1b304a8,0x1b304f4)` INLINE at C6 post-`parse_args`.

## 2. C6 implications

C6 STRONG proves `parse_args("Booting kernel")` COMPLETE on this artifact, so
`panic=` (core_param) and `rdinit=` (`__setup` via `unknown_bootoption`) were
consumed by the running kernel. It does **not** prove `calibrate_delay()`,
panic timeout wall-clock, `rest_init`, initramfs, or `/init`.

## 3. Why C_DELAY

Unique question: after the already-proven C6, does the normal `start_kernel`
path continue and **complete** `calibrate_delay()`, then reach the first safe
post-return checkpoint?

`C_DELAY = CALIBRATE_DELAY_COMPLETE`. Not panic() reached. Not panic timeout
executed. Not panic wallclock exact.

## 4. calibrate_delay source identity

Linux 6.6.156 `8b73de7da85fde281a385e0b26eda9bffd3ca477`.
GHA re-derives from exact source + frozen config + **this round's** final
vmlinux: symbol, callsite, call target, post-call VA, basic block, section,
Image offset, file offset. JSON is planner input only
(`C_DELAY_MAP_JSON_CONSUMED`, `C_DELAY_MAP_CRITICAL_POINTS_REDERIVED`).

`EARLY_C_STAGE_MAP_SOURCE_HEAD=d47bf58`. Source run `34842580640`.
Integration `00df879` `NO_FF_MERGE`. Map reverified on A mainline.

`init/Makefile`: `obj-$(CONFIG_GENERIC_CALIBRATE_DELAY) += calibrate.o`.
Frozen config must have `CONFIG_GENERIC_CALIBRATE_DELAY=y` or the candidate
is `NOT READY`. `calibrate_delay()` in `start_kernel` is unconditional.
`lpj_fine` skip lives **inside** the function after `time_init`; the BL is
still taken. `CALIBRATE_DELAY_RUNTIME_CALL_REQUIRED=YES`.

## 5. C6 → C_DELAY control flow

Not "next insn after C6". Between `parse_args("Booting kernel")` COMPLETE and
`calibrate_delay()` the normal path still runs (source-audited, GHA listed):
`print_unknown_bootoptions`, optional extra `parse_args` for init args,
`random_init_early`, `setup_log_buf`, `vfs_caches_init_early`,
`sort_main_extable`, `trap_init`, `mm_core_init`, `poking_init`,
`ftrace_init`, `early_trace_init`, `sched_init`, `radix_tree_init`,
`maple_tree_init`, `housekeeping_init`, `workqueue_init_early`, `rcu_init`,
`trace_init`, `context_tracking_init`, `early_irq_init`, `init_IRQ`,
`tick_init`, `init_timers`, `timekeeping_init`, `time_init` (sets
`lpj_fine = arch_timer_rate / HZ`), `console_init`, optional `panic_later`
(failure path only), `setup_per_cpu_pageset`, `sched_clock_init`.

`C6_TO_C_DELAY_NORMAL_PATH_AUDITED=YES`. Conditionals in this window do not
skip `calibrate_delay` on the normal path. `panic_later` is not the
checkpoint path.

## 6. Callsite

GHA objdump of `start_kernel`: unique `BL calibrate_delay`. Frozen FIX8
payload BL decode must match nm. This round independently re-derived:
`CALIBRATE_DELAY_CALLSITE_VA=0xffff800081b30624`
`CALIBRATE_DELAY_CALLSITE_OFFSET=0x1b30624`
`CALIBRATE_DELAY_CALL_INSN=BL`
`CALIBRATE_DELAY_CALL_BYTES=9793904f`
`CALIBRATE_DELAY_TARGET_VA=0xffff800080014760`
`CALIBRATE_DELAY_TARGET_SYMBOL=calibrate_delay`
`CALIBRATE_DELAY_POSTCALL_VA=0xffff800081b30628`
`CALIBRATE_DELAY_POSTCALL_OFFSET=0x1b30628`.
Map C_DELAY COMPLETE `0xffff800081b30628` MATCHED the independent
re-derivation. `C_DELAY_CHECKPOINT_IS_POSTCALL=YES`.
`C_DELAY_POSTCALL_CONTROL_FLOW_PROVEN=YES`.

## 7. Postcall checkpoint

Checkpoint = first insn after that BL (`callsite+4`). Never before the call.
Never inside `calibrate_delay`. Executing the checkpoint means
`calibrate_delay` has returned.

## 8. Exact panic → mdelay implementation audit

From Linux 6.6.156 + frozen arm64 config (not the historical verbal model):

`panic()` (`kernel/panic.c`): if `panic_timeout > 0`, loop
`for (i = 0; i < panic_timeout * 1000; i += PANIC_TIMER_STEP)` with
`PANIC_TIMER_STEP=100`, each step `mdelay(PANIC_TIMER_STEP)`.
`panic=` is `core_param(panic, panic_timeout, ...)`.

`mdelay` (`include/linux/delay.h`): `PANIC_TIMER_STEP=100 > MAX_UDELAY_MS=5`,
so `{unsigned long __ms=n; while (__ms--) udelay(1000);}`.

`udelay` (`include/asm-generic/delay.h`, arm64 mandatory-y): constant path
`__const_udelay(n * 0x10c7ul)`.

arm64 `arch/arm64/lib/delay.c`: `__const_udelay` → `__delay(xloops_to_cycles)`
where `xloops_to_cycles = (xloops * loops_per_jiffy * HZ) >> 32` and
`__delay` waits on `__arch_counter_get_cntvct_stable()` (CNTVCT).

`PANIC_MDELAY_IMPLEMENTATION=panic()->if panic_timeout>0: for i+=PANIC_TIMER_STEP=100 until panic_timeout*1000: mdelay(100) [100>MAX_UDELAY_MS=5 so while __ms--: udelay(1000)] -> asm-generic udelay -> arm64 __udelay/__const_udelay -> __delay(xloops_to_cycles) waiting on CNTVCT; xloops_to_cycles=(xloops*loops_per_jiffy*HZ)>>32`

## 9. loops_per_jiffy relation

`PANIC_MDELAY_DEPENDS_ON_LOOPS_PER_JIFFY=YES`. Preset
`loops_per_jiffy = (1<<12)` until `calibrate_delay` writes `loops_per_jiffy = lpj`.
arm64 `time_init` sets `lpj_fine = arch_timer_rate / HZ`; `calibrate_delay`
copies `lpj_fine` (skip loop) then assigns `loops_per_jiffy`.

## 10. arch timer relation

`PANIC_MDELAY_DEPENDS_ON_ARCH_TIMER=YES`. The wait is CNTVCT cycles.
`CALIBRATE_DELAY_AFFECTS_PANIC_MDELAY=YES` because it updates
`loops_per_jiffy`, which **scales** the cycle count. Name "calibrate_delay"
does not by itself prove panic timeout wall-clock; the audited chain does.

`PANIC_MDELAY_CALIBRATION_RELATION=YES_LOOPS_PER_JIFFY_SCALES_ARM64_ARCH_TIMER_CYCLE_COUNT`.
Future C_DELAY STRONG may write `PANIC_MDELAY_CALIBRATION_READY=YES`. This
round does **not** write `PANIC30 SHOULD HAVE SHIFTED`.
`PANIC30_RERUN=FROZEN`.

## 11. Probe architecture

`C_DELAY_PROBE_ARCHITECTURE=INLINE`. 76-byte T1/T4 diagnostic core over the
post-`calibrate_delay` fallthrough in `.init.text` AX. Mapping
`KERNEL_TEXT_VA_SELF_EVIDENT`. No padding cave. No T1 `0x2230000`.
`C_DELAY_EXTERNAL_CHECKPOINT_USED=NO`. `C_DELAY_PADDING_MAPPING_USED=NO`.

## 12. Rewrite safety

GHA scans: symbols, RELR, alternatives, jump labels, static calls, ftrace,
CFI, SCS, PAC, BTI, exception tables, literal pools, branch targets, runtime
patch sites. `C_DELAY_INLINE_OVERWRITE_SAFE=YES` or NOT READY.
`C_DELAY_ENTRY_INSTRUMENTATION_AUDITED=YES`. Mid-function fallthrough: BTI
not checked on RET. CFI/ftrace/KASAN/KCOV/SCS must be off.

## 13. Timer / PSCI safety

`C_DELAY_CNTPCT_SAFE=YES`. C6→C_DELAY includes `time_init` (arch timer as
clocksource) but does not trap CNTPCT from EL1. Proven at T0–T4.
`C_DELAY_PSCI_SAFE=YES`. Still EL1, SMC conduit, SYSTEM_RESET `0x84000009`
has no pointer argument. `psci_dt_init` already ran in `setup_arch`.

## 14. Fail-closed

8s CNTPCT register-only + PSCI SYSTEM_RESET `0x84000009` via `smc #0`.
SMC return → `wfe` forever. `C_DELAY_FAIL_CLOSED=YES`.
`C_DELAY_STACK_USAGE=NO`. memory reads=NO, writes=NO, MMIO=NO,
`C_DELAY_RUNTIME_RELOCATIONS=0`.
`C_DELAY_DIAGNOSTIC_CORE_MATCHES_T4=YES` (byte-identical 76-byte T1/T4 core).

## 15. T4 probe removal

Baseline is FIXED INIT8, not the T4 diagnostic payload.
`T4_PROBE_REMOVED_FROM_C_DELAY=YES`. C6 window restored to FIX8 bytes.
`C6_REGION_IDENTICAL_TO_FIX8=YES`. `START_KERNEL_ENTRY_RESTORED_TO_FIX8=YES`.

## 16. Normal pre-path identity

`C_DELAY_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES`: trampoline →
primary_entry → `__primary_switched` → `start_kernel` → setup_arch →
`PARSE_EARLY_PARAM` inside setup_arch → C6 `C6_PARSE_ARGS_COMPLETE` →
calibrate_delay post-return. Byte-identical to FIX8 except the C_DELAY
checkpoint itself.

Frozen identities MATCH:
- trampoline `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`
- RT-D `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
- /init `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d`
- initramfs `02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3`

RT-D keeps `panic=5` `rdinit=/init`.

## 17. Diff attribution

`C_DELAY_RUNTIME_SEMANTIC_DELTA=POST_CALIBRATE_DELAY_CHECKPOINT_ONLY`.
`C_DELAY_PAYLOAD_DIFF_ATTRIBUTED=POST_CALIBRATE_DELAY_CHECKPOINT_ONLY`.
This round: `C_DELAY_DIFF_BYTE_COUNT=73` in `[0x1b30628,0x1b30674)`.
C6 window `[0x1b304a8,0x1b304f4)` identical to FIX8 (T4 probe removed).
Outside the checkpoint window: 0 changed bytes.

Geometry from FINAL BINARY HEADER (`IMAGE_HEADER_IMAGE_SIZE_REDERIVED`):
authoritative FIX8 `image_size=0x2230000`, file 35166720, `DTB_OFFSET=0x2380000`,
payload 37369041, boot 37380096.

## 18. Private packaging

PUBLIC GHA run `34913482023` commit `35f976f7dd4f816524ce43c69b999b5468b98c40`:
source audit, panic mdelay chain, checkpoint, CFG, diff, negative fixtures,
observer fixtures. No OEM boot.img.
`C_DELAY_PAYLOAD_SHA256=372724921ff922dfbf95dcf5081d8527096732a7b402bb63efc01d14f029c52d`
`C_DELAY_CHECKPOINT_SHA256=4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611`
(byte-identical T1/T4 76-byte core).

PRIVATE GHA pack run `34915314009`: FIX8/M5D envelope + ONE C_DELAY boot.img.
`C_DELAY_BOOT_SHA256=d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02`
`C_DELAY_BOOT_SIZE=37380096`.
Staging: `artifacts/p1b-c-delay-private-workflow-staging.yml`.

## 19. Reverify

Independent private reverify-only run `34915464385`: no repack. Boot SHA,
payload extract SHA, checkpoint bytes, T4 probe removed, RT-D, geometry,
envelope. `C_DELAY_PRIVATE_IDENTITY_REVERIFIED=YES`.

## 20. Observer

Prepared, **not run**. FULL C_DELAY boot SHA
`d9f01bff4a7ff0d2fe580867a72a47c4a3d15930c388a99f2402835912847b02`
before any fastboot. Fixtures PASS (refuses T4/T3/T2/T1/T0/FIX8/PANIC30/
old INIT8/entry-state probe). `C_DELAY_NOT_REACHED_LICENSE=NO`. Failures →
`MAINLINE_V2_R3_P1B_C_DELAY_FAILURE_ISOLATION_CI`. Never auto PANIC30.

## 21. Future timing window

Primary predecessor `T4_TOTAL=14.385s`.
`C_DELAY_MINUS_T4 = C_DELAY_TOTAL - 14.385`.

Preregistered (frozen before any device run):
- STRONG: `|C_DELAY_TOTAL - 14.385| <= 1.5s`
- SUPPORTED: `<= 3.0s`
- `C_DELAY_TOTAL < 20s`
- `AUTOMATIC_ANDROID_RETURN=YES`

Rationale for keeping 1.5/3.0: C6→C_DELAY includes `mm_core_init` /
`console_init` / `time_init`, but T4 showed `setup_arch`+`parse_args` added
only +0.147s on this device; `calibrate_delay` itself is an `lpj_fine` skip.
Not a hunting window. Results must not retune the window.

## 22. Positive boundary

If future STRONG:
`CALIBRATE_DELAY_COMPLETE_REACHED=PROVEN`
`NORMAL_START_KERNEL_BODY_TO_C_DELAY_EXECUTED=PROVEN`
C6 / panic= parsed / rdinit= parsed remain PROVEN.
Update `PANIC_MDELAY_CALIBRATION_STATE` from section 9.
Must **not** auto-upgrade `panic() reached`.

## 23. Negative boundary

Missing signature ≠ `calibrate_delay not reached`. Possible instrumentation /
timer / checkpoint / normal C path failure. Enter
`C_DELAY_FAILURE_ISOLATION_CI`. No automatic PANIC30 rerun.

## 24. PANIC30 implications

C_DELAY STRONG would make panic-timeout mdelay calibration **ready**
(loops_per_jiffy assigned). It still does not prove the failure path entered
`panic()` with `panic_timeout > 0`. `PANIC30_RERUN=FROZEN`.

Negative fixtures include: wrong calibrate_delay symbol, wrong callsite,
checkpoint before call, non-postcall, T4 probe still present, C6 path
modified, pre-C_DELAY path modified, unsafe inline, rewrite conflict,
unmapped external, wrong delay, wrong PSCI FID, missing smc, fall-through,
stack, memory read/write, relocations, RT-D change, extra payload diff,
geometry mismatch.

Public path: `.github/workflows/thyme-r3-p1b-c-delay-predevice.yml`.
Current B: M5D+M5H+M5M-B UNCHANGED. FIX24 FROZEN. M5N FROZEN.
Final gate: `READY_FOR_R3_P1B_C_DELAY_DEVICE_CONTROL=YES`.
