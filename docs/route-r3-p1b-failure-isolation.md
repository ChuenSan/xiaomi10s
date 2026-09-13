# Route R3 P1B Failure Isolation CI (MAINLINE_V2_R3_P1B_FAILURE_ISOLATION_CI)

Stage: CI / SOURCE AUDIT ONLY. No device operation, no fastboot, no adb, no USB,
no copydown, no M5N, no partition writes (0), Slot A untouched, Current B
unchanged (M5D+M5H+M5M-B), M5N FROZEN. All build/execution/binary inspection
GitHub Actions ONLY. Local: build/validation/binary inspection disabled.

Evidence run: public GHA run **34729573603** (workflow
`thyme-r3-p1b-failure-isolation`, script `scripts/r3-p1b/p1b-failure-isolation.py`),
artifact `thyme-r3-p1b-failure-isolation`. Authoritative binaries from frozen
public run 34696279424.

## 1. Pair failure facts (frozen)

| Fact | Value |
|---|---|
| INIT8_TOTAL | 23.184 s |
| INIT24_TOTAL | 24.570 s |
| PAIR_DELTA | +1.386 s |
| PAIR_EXPECTED | +16.000 s |
| PAIR_ERROR | -14.614 s |
| VERDICT | NO_MATCH (preregistered STRONG 15-17 s / SUPPORTED 14-18 s both missed) |
| Automatic Android A return | YES for both |
| Previous gate | R3_P1B_INIT_TIMING_PAIR_NOT_CONFIRMED |

## 2. Evidence level recalibration (conservative, at round start)

- E0 ABL→controlled payload: PROVEN
- E1 normal Mainline reached: NOT_PROVEN
- E2 early Mainline: NOT_PROVEN
- E3 built-in initramfs: NOT_PROVEN
- E4 /init: NOT_PROVEN
- E5 USB: FROZEN
- P1B_INIT8_PROVISIONAL_SIGNATURE_CONFIRMED=NO (downgraded; the INIT24
  confirmatory pair failed, so the INIT8 provisional signature cannot stand as
  positive /init evidence)

## 3. Hypothesis families

- H-A: /init executes but the delay primitive does not actually wait (wrong
  syscall ABI, wrong arguments, unchecked return, ...).
- H-B: execution never reaches /init (trampoline, primary_entry, head.S, DTB,
  memory init, initramfs unpack, exec /init — panic/reset/firmware return
  earlier).

This round was required not to preselect. The audits below resolve the delay
primitive question (H-A root cause proven at source, pinned-kernel and binary
levels). Whether /init is actually reached on device remains formally open and
is the target of the next control (see §12-§14).

## 4. Exact /init source audit (scripts/r3-p1b/p1b-init.c, line-level)

- Syscall ABI: raw `svc #0`, no libc. `sys3(nr,a0,a1,a2)` sets x8=nr,
  x0..x2 only; `sys4(...)` adds x3.
- `SYS_clock_nanosleep 115` called via **sys3** with
  `(CLOCK_MONOTONIC=1, (long)&req, (long)&rem)` → x0=1, x1=&req, x2=&rem.
  The kernel syscall is 4-arg `clock_nanosleep(which_clock, flags, rqtp,
  rmtp)`: **&req lands in the flags slot, &rem lands in the rqtp slot, rmtp
  (x3) is never initialized.** p1b-init.c:76.
- timespec: `struct ts { long tv_sec; long tv_nsec; }` — 8+8 bytes LP64,
  layout-compatible with `struct __kernel_timespec` on aarch64 (little-endian);
  INIT8 tv_sec=8, INIT24 tv_sec=24 — but the struct is never consumed as the
  sleep spec (see §5).
- Return handling: `while (sys3(...) == -EINTR) req = rem;` — ONLY -EINTR is
  retried; any other return (EINVAL/EFAULT/EPERM/ENOSYS) falls through to
  reboot immediately.
- Reboot: `sys4(SYS_reboot, 0xfee1dead, 672274793, 0x01234567, 0)` — full
  4-arg raw form.
- Exit fallback: `sys3(SYS_exit_group, r, 0, 0)` after reboot returns; then a
  `for(;;)` spin that is unreachable in practice.
- Binary identity: freestanding `-Os -nostdlib -static -no-pie`, entry `main`
  at 0x400000, ident string `THYME-R3-P1B-INIT DELAY=08/24 CMD=restart`.

Verdicts: INIT_CLOCK_NANOSLEEP_ABI=**FAIL_3ARG_CALL**;
INIT_SLEEP_RETURN_CHECKED=**NO**;
P1B_INIT_CONTROL_HAS_UNCHECKED_SLEEP_FAILURE_PATH=**YES**;
INIT_REBOOT_ABI=**PASS**.

## 5. Syscall numbers from the exact Linux UAPI pin

Tree: linux-6.6 @ `8b73de7da85fde281a385e0b26eda9bffd3ca477` (6.6.156, verified
`git rev-parse` locally and in GHA). `include/uapi/asm-generic/unistd.h`:

- `__NR_exit_group 94` (line 260)
- `__NR_clock_nanosleep 115` (line 322)
- `__NR_reboot 142` (line 392)

All three match p1b-init.c defines. INIT_SYSCALL_NUMBER_AUDIT=**PASS**
(also proven in the final binaries' disassembly, §7).

## 6. Pinned-kernel clock_nanosleep semantics (what the device kernel does)

`kernel/time/posix-timers.c` @ pin, SYSCALL_DEFINE4(clock_nanosleep) (line
1374) with the reconstructed P1B config (CONFIG_POSIX_TIMERS=y):

1. `kc = clockid_to_kclock(1)` → clock_monotonic (`.nsleep =
   common_nsleep_timens`) — passes.
2. `get_timespec64(&t, rqtp)` with rqtp = x2 = **&rem** → t = {0,0}.
3. `timespec64_valid({0,0})` → valid.
4. `flags & TIMER_ABSTIME`: flags = x1 = **&req**, a 16-byte-aligned stack
   address → bit0 = 0 → not ABSTIME → relative mode.
5. `kc->nsleep` → `hrtimer_nanosleep(texp=0, HRTIMER_MODE_REL, CLOCK_MONOTONIC)`
   → **returns 0 after zero wait**.

So on the exact pinned kernel the delay primitive does not error out — it
succeeds with duration 0. The `while == -EINTR` loop never loops; execution
reaches `reboot(RESTART)` immediately. The DELAY_SECONDS constant only feeds
the (stack-stored, unused) `req` and the ident string.

## 7. Authoritative binary disassembly (GHA objdump, run 34729573603)

INIT8 clock_nanosleep call block (init24 identical except the constant):

```
sub  sp, sp, #0x20
mov  x0, #0x8            ; DELAY constant
stp  x0, xzr, [sp]       ; req = {8, 0}
stp  xzr, xzr, [sp, #16] ; rem = {0, 0}
mov  x1, sp              ; x1 = &req  -> FLAGS slot
add  x2, sp, #0x10       ; x2 = &rem  -> RQTP slot
mov  x8, #0x73           ; 115 clock_nanosleep
mov  x0, #0x1            ; CLOCK_MONOTONIC
svc  #0                  ; no x3 write anywhere in the block
```

- Syscall immediates 115/142/94 present in both binaries.
- Reboot constants present in both: movz/movk 0xdead|0xfee1 (magic1),
  0x1969|0x2812 (magic2), 0x4567|0x123 lsl 16 (cmd), x3 zeroed (arg).
- INIT_BINARY_SEMANTIC_DELTA=**DELAY_CONSTANT_ONLY**: exactly ONE instruction
  differs between the pair — `mov x0, #0x8` vs `mov x0, #0x18` (plus the rodata
  ident string). The earlier CI conclusion stands structurally, with the
  correction that the differing constant is **semantically dead** (stored into
  the unused `req`).

## 8. Authoritative QEMU user-mode execution (run 34729573603)

Pinned emulator: `qemu-aarch64 version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)`
on ubuntu-24.04. Exact binaries from public run 34696279424, SHAs verified
against the frozen pins (INIT8 4c1491b2…135f, INIT24 b5eb44c8…7f55). No
recompilation for the guest; a separately compiled positive control validates
the harness only.

Positive control (correct 4-arg ABI, 2 s sleep):

```
clock_nanosleep(CLOCK_MONOTONIC,0,{tv_sec = 2,tv_nsec = 0},{tv_sec = 0,tv_nsec = 0}) = 0
exit_group(0)          ; wallclock ≈ 2 s → QEMU_HARNESS_POSITIVE_CONTROL=PASS
```

Authoritative binaries, `-strace` (both runs identical in shape):

```
clock_nanosleep(CLOCK_MONOTONIC,16774864,{tv_sec = 0,tv_nsec = 0},NULL) = 0
reboot(4276215469,672274793,19088743,0) = -1 errno=1 (Operation not permitted)
exit_group(-1)
```

- flags slot = 16774864 = &req (bit0 = 0 → relative); rqtp reads &rem = {0,0};
  rmtp = NULL-printed stale slot; return **0** — success with zero duration.
- reboot args are exactly magic1 0xfee1dead / magic2 672274793 / cmd
  0x01234567 / 0; on the runner it returns EPERM (no CAP_SYS_BOOT) — the
  expected safe condition; on the device PID 1 holds CAP_SYS_BOOT in the init
  namespace, so the reboot is real.
- exit_group(-1) → exit status 255.

Timings (wallclock, preregistered bands STRONG 15.5-16.5 s / SUPPORTED
15.0-17.0 s):

| Metric | Value |
|---|---|
| QEMU_INIT8_RUNTIME | 0.003 s |
| QEMU_INIT24_RUNTIME | 0.002 s |
| QEMU_PAIR_DELTA | 0.000 s |
| QEMU_PAIR_VERDICT | **FAIL** (neither band) |

## 9. Built-in initramfs inclusion (authoritative artifacts)

From public run 34696279424 pair artifact (SHA256SUMS re-verified in
34729573603):

- cpio newc, entries exactly `dev, init, proc, sys, TRAILER!!!`;
  /init entry mode 0100755, uid=0, gid=0, data byte-identical to the standalone
  authoritative /init binary (BUILTIN_INITRAMFS_CPIO_FIELDS=PASS).
- Each payload Image embeds exactly its own delay's cpio uncompressed and
  byte-exact (INIT8 payload contains the 8 s cpio exactly once and not the
  24 s one; vice versa) — BUILTIN_INITRAMFS_EMBED=PASS.
- PAIR_GEOMETRY_IDENTICAL=YES: payload 37369041 B both, RT-D trailer SHA
  4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327, trampoline
  SHA 362d9c6e…c623 at 0x40, code1 = `b 0x40`, bootargs
  `rdinit=/init panic=5 loglevel=7`.

## 10. rdinit kernel path (pinned source)

init/main.c @ pin:

- `static char *ramdisk_execute_command = "/init";` (line 160) — default is
  already /init; cmdline `rdinit=/init` (rdinit_setup, line 567) sets it
  explicitly.
- kernel_init_freeable (line 1536): `init_eaccess("/init") != 0` →
  `ramdisk_execute_command = NULL; prepare_namespace();` — with no `root=`
  in RT-D bootargs prepare_namespace cannot mount anything → kernel panic →
  with panic=5 → automatic reboot. So if the built-in initramfs had NOT been
  unpacked, the device would still auto-return to Android A; the timing pair
  alone cannot separate this from /init-reached.
- kernel_init (line 1440): `run_init_process("/init")` → binfmt_elf → the P1B
  binary as PID 1.

BUILTIN_INITRAMFS_RDINIT_PATH_VALID=**YES** (kernel semantics), with the
built-in initramfs presence on device itself still at E3=NOT_PROVEN.

## 11. Kernel config audit (reconstructed in GHA, run 34729573603)

Config reconstructed with the exact recipe of p1b-build.py (defconfig +
configs/thyme-route-b.config + configs/thyme-r3-p1b.config + initramfs
fragment, merge_config.sh -m + olddefconfig) on the pinned tree. Symbol-level
authoritative; only the INITRAMFS_SOURCE path string differs from the
build-time value.

| Symbol | Value | Consequence |
|---|---|---|
| CONFIG_ARM64 / CONFIG_MMU | y | aarch64 target |
| CONFIG_BINFMT_ELF | y | /init (ET_EXEC ELF) executable |
| CONFIG_BLK_DEV_INITRD | y | initramfs machinery |
| CONFIG_INITRAMFS_SOURCE | 8 s cpio | built-in initramfs |
| CONFIG_INITRAMFS_COMPRESSION_NONE | y | uncompressed cpio |
| CONFIG_POSIX_TIMERS | y | posix-timers.c path of §6 compiled |
| CONFIG_HIGH_RES_TIMERS / GENERIC_CLOCKEVENTS(_BROADCAST) | y | hrtimer infrastructure |
| CONFIG_PANIC_TIMEOUT | 0 | timeout comes solely from cmdline panic=5 |
| CONFIG_PANIC_ON_OOPS(_VALUE) | n / 0 | oops alone does not panic by config |
| CONFIG_PANIC_ON_WARN | n | warns do not panic |

P1B_CLOCK_NANOSLEEP_KERNEL_SUPPORT=**YES** (the syscall is fully present — the
bug is purely the caller's ABI misuse).

## 12. panic=5 competing path (modeling, not fact)

kernel/panic.c @ pin: `core_param(panic, panic_timeout, ...)` (line 781);
`panic()`: `if (panic_timeout > 0) { pr_emerg("Rebooting in %d seconds..");
mdelay loop timeout*1000 ms }` then `emergency_restart()` (lines 403-427).
RT-D bootargs carry `panic=5`, so **any** early kernel panic (including the
no-root panic of §10 or a PID 1 death, which panics via
"Attempted to kill init") produces a delay-independent automatic Android A
return with a constant +5 s. EARLY_PANIC_CAN_AUTO_REBOOT_WITH_PANIC_5=**YES**.

Status: PRE_INIT_PANIC_RESET_CLASS is a HYPOTHESIS, not fact. Both candidate
return paths (H-A zero-sleep-then-reboot, H-B early panic + 5 s) are
delay-independent and consistent with 23.184 s / 24.570 s / delta 1.386 s.

## 13. Failure isolation verdict

Root cause of the pair failure is PROVEN at three independent levels:

1. Source: p1b-init.c calls the 4-arg clock_nanosleep through sys3 (3 args).
2. Pinned kernel 6.6.156: with those registers the syscall returns 0 after
   zero wait (relative mode, rqtp=&rem={0,0}).
3. Authoritative binaries under pinned qemu-aarch64: disassembly block proves
   the register layout; strace proves `= 0` immediately; runtimes 0.003 s /
   0.002 s, pair delta 0.000 s vs preregistered 15.0-17.0 s → FAIL; positive
   control proves the harness measures real sleeps.

ROOT CAUSE FAMILY = **INIT CONTROL** (the delay primitive in /init never
waits). This fully explains why INIT8_TOTAL and INIT24_TOTAL differ by only
1.386 s: whatever the ~23-25 s path is, it contains no 8 s/24 s sleep, so the
pair collapses to run-to-run variance. Whether the ~23-25 s return is driven
by /init's immediate reboot (H-A) or by an earlier panic (H-B) is NOT yet
proven on device.

Case A of the decision tree applies: Final Gate
**R3_P1B_FAILURE_ISOLATED_TO_INIT_CONTROL**; next stage
MAINLINE_V2_R3_P1B_INIT_CONTROL_FIX_CI.

## 14. Next control: fixed /init timing pair (design note for next stage)

Minimal single-variable fix in p1b-init.c: call clock_nanosleep via sys4 with
flags=0 — `sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0, (long)&req,
(long)&rem)` (optionally also retry on errors, not only -EINTR). The rebuilt
pair must be re-gated (geometry identical, DELAY_CONSTANT_ONLY). Device
interpretation once run:

- PAIR_DELTA ≈ 16 s → /init executed on device → E3/E4 proven, panic path
  refuted as the return source.
- Still ~23-25 s constant → the return is pre-init (panic class) → escalate
  to PANIC30 / checkpoint ladder below.

## 15. PANIC30 control design (NOT built this round)

Per the decision tree, PANIC30 is only constructed when the /init QEMU audit
passes; it did not, so no PANIC30 candidate was generated (Case A). Design
recorded for future use:

- Baseline: INIT8 /init; sole boot-semantic variable: RT-D bootargs
  `panic=5` → `panic=30`. Requires a NEW RT-D (bootargs live in RT-D), so it
  touches frozen RT-D material — user approval required, and RT-D SHA changes.
- All else identical: kernel, trampoline, geometry, RAM, reserved-memory, DTB
  structure, initramfs, /init binary (INIT8 SHA unchanged).
- P1B_PANIC_CONTROL_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY.
- Theoretical criterion: if the auto-return comes from panic+5, PANIC30 TOTAL
  shifts by ≈ +25 s (≈ 48.184 s); if it stays ≈ 23-25 s, the panic timeout is
  not the return driver.
- P1B_PANIC30_CANDIDATE=**NOT_READY**.

## 16. Checkpoint ladder design (design only; NOT device ready)

All checkpoints: register-only, CNTPCT_EL0 read + spin, PSCI reset
(SMCCC 32-bit SMC function 0x84000009, conduit per DT), NO stack, NO
arbitrary memory, NO UART; each supports the 8 s/24 s delay pair for a
controlled proof; one approval, one boot.

- **T0 trampoline** (`scripts/r3-p1b/p1b-trampoline.S`, at r3_handoff_entry
  before b_primary): insert CNTPCT delay + PSCI reset. Proves large payload
  transport, trampoline execution, DTB address calculation path. Does NOT
  prove Linux primary_entry. Note: current trampoline gates forbid smc/BL;
  checkpoint builds need their own gate set.
- **T1 primary_entry**: patch the first instruction of primary_entry
  (`bl record_mmu_state`) to branch to a checkpoint payload appended after the
  existing trampoline region (branch range 0x40 → 0x1b1c0a0 ≈ 27 MB, within
  ±128 MB). T1a: delay → PSCI reset (arrival proof). T1b: delay → execute the
  displaced `bl record_mmu_state` → `b primary_entry+4` (continue-through;
  x0-x3 DTB state preserved; x30 semantics identical to the unpatched flow).
  Proves the trampoline branch actually reaches normal Linux entry.
- **T2 post-head.S**: symbol located only this round: `__primary_switched`
  (arch/arm64/kernel/head.S) — sets sp/init_task, then `b start_kernel`.
  Post-MMU branch to the 0x40 region is not PC-relative-encodable (VA gap),
  so a T2 checkpoint needs an absolute-register jump (multi-instruction patch
  in head.S text) — design open point; requires its own gate. Separates
  head.S early startup from C start_kernel.

Checkpoint ladder status: T0/T1 DESIGNED, T2 SYMBOL LOCATED (design only).
Default NOT DEVICE READY (PANIC30 route not proven worthless — Case A makes
the fixed-pair control the next step).

## 17. CopyMem priority update

INIT8 and INIT24 are same-size large artifacts, both fastboot-accepted, both
reaching an identical ~23-25 s delay-independent return. CopyMem/staging is
therefore no longer the primary failure candidate:
COPYMEM_FAILURE_PRIORITY=**LOWERED** (revisit only if a future T0 checkpoint
fails).

## 18. RT-D and historical signature status

- RT-D_STRUCTURALLY_COMPLETE=YES; RT_D_RUNTIME_FUNCTIONALITY=NOT_PROVEN
  (pair failed; do not write "RT-D functional").
- M5_STYLE_4P7S_PATH_NOT_OBSERVED=YES (neither P1B run showed the 4.7 s
  fastboot return; this does not imply normal Mainline was reached).

## 19. Decision tree recap and stage gate

- Case A (QEMU exact /init pair FAIL) → ROOT CAUSE FAMILY: INIT CONTROL →
  next: P1B_INIT_CONTROL_FIX_CI — **applies (taken)**.
- Case B (pair PASS) → PANIC30 candidate — not reached.
- Case C (QEMU PASS + panic statically excluded) → EARLY_CHECKPOINT_CI — not
  reached.

FINAL_GATE=R3_P1B_FAILURE_ISOLATED_TO_INIT_CONTROL

Recommended next: MAINLINE_V2_R3_P1B_INIT_CONTROL_FIX_CI
(§14 design; CI-only until the user separately approves any device round).

## 20. Final report (stage constraints)

```
mem0 read:            YES (round start)
local build:          NO
GHA-only execution:   YES (run 34729573603)
device operation:     NO
Slot A written:       NO
Partition writes:     0
Current B:            M5D+M5H+M5M-B UNCHANGED
M5N:                  FROZEN
```

Frozen device facts: INIT8_TOTAL=23.184 s, INIT24_TOTAL=24.570 s,
PAIR_DELTA=1.386 s, PAIR_EXPECTED=16.000 s, PAIR=NO_MATCH.
Evidence reset: E0 PROVEN, E1-E4 NOT_PROVEN, E5 FROZEN.
/init ABI: clock sleep syscall clock_nanosleep 115 (4-arg kernel ABI); syscall
numbers 115/94/142 PASS; arguments x0=1, x1=&req(flags slot!), x2=&rem(rqtp
slot!), x3 unset; timespec layout 8+8 B valid but unused as spec; return
checked: NO (EINTR only; actual return 0 zero-duration); reboot syscall
142 PASS (magic1/magic2/cmd/arg all correct); exit fallback exit_group.
Kernel support: POSIX timers y, clock_nanosleep YES, ELF y, built-in
initramfs y, rdinit path YES.
Authoritative QEMU test: INIT8 SHA 4c1491b2…135f runtime 0.003 s sleep
return 0; INIT24 SHA b5eb44c8…7f55 runtime 0.002 s sleep return 0;
QEMU_PAIR_DELTA 0.000 s verdict FAIL.
Root cause family: INIT CONTROL. Next: P1B_INIT_CONTROL_FIX_CI.
Panic model: panic cmdline current 5 s; panic auto reboot possible YES;
PANIC30 candidate NOT_READY; semantic delta PANIC_TIMEOUT_ONLY (design only).
Checkpoint ladder: T0 DESIGNED, T1 DESIGNED, T2 post-head.S SYMBOL LOCATED.
CopyMem priority: LOWERED. RT-D: structurally complete YES, runtime
functional NOT_PROVEN.

WAIT FOR USER APPROVAL
