# Route R3 P1B — /init control fix (MAINLINE_V2_R3_P1B_INIT_CONTROL_FIX_CI)

CI-only stage. No device operation, no partition writes, Slot A untouched,
Current B (M5D+M5H+M5M-B) unchanged, M5N FROZEN, PANIC30 FROZEN,
checkpoint ladder T0/T1/T2 FROZEN as future fallback only.

Prior gate: `R3_P1B_FAILURE_ISOLATED_TO_INIT_CONTROL` (GHA run 34729573603).
This stage fixes the single confirmed root cause and revalidates the full
P1B geometry. Boot v3 packing is private-GHA only; the public workflow never
splices M5D and never emits a flashable boot image.

## 1. Old root cause (frozen)

CLOCK_NANOSLEEP_ABI: BROKEN_3_ARG (source-audit + pinned-kernel UAPI +
authoritative-binary disassembly + QEMU strace, GHA run 34729573603).

The old P1B /init (public run 34696279424) called `clock_nanosleep` through a
3-arg raw-syscall wrapper. The Linux arm64 ABI for
`sys_clock_nanosleep(which_clock, flags, rqtp, rmtp)` needs four arguments:

| register | required      | old /init actually passed        |
|----------|---------------|----------------------------------|
| x0       | clockid       | CLOCK_MONOTONIC (1)              |
| x1       | flags         | &req  (a stack pointer)          |
| x2       | rqtp          | &rem  (initial all-zero struct)  |
| x3       | rmtp          | uninitialized                    |

`(&req & 1) == 0`, so the pointer in the flags slot decoded as
`TIMING_MODE_RELATIVE`; `rqtp` pointed at the all-zero `rem`; the sleep was
therefore a legal 0-second wait that returned 0 immediately.
`OLD_INIT_DELAY_CONTROL_BROKEN=YES` — `DELAY_SECONDS` was semantically dead.

## 2. Old device pair failure (frozen)

INIT8_TOTAL = 23.184s, INIT24_TOTAL = 24.570s, PAIR_DELTA = +1.386s vs the
expected +16.000s -> preregistered NO_MATCH. QEMU user-mode on the exact old
binaries: INIT8 runtime 0.003s, INIT24 runtime 0.002s, pair delta 0.000s,
verdict FAIL; a 4-arg positive control slept 2s, proving the harness valid.
`OLD_INIT8_24_DEVICE_RESULTS_NOT_INIT_TIMING_PROOF=YES`. The frozen
INIT8/INIT24 artifacts keep their original names; the corrected pair uses
new FIX names and is never mixed with the old ones
(`OLD_BROKEN_INIT8`/`OLD_BROKEN_INIT24` vs `FIXED_INIT8`/`FIXED_INIT24`).

## 3. Corrected syscall ABI (FIXED_4ARG)

`scripts/r3-p1b/p1b-init.c` now uses one 4-arg wrapper only (`sys3` removed):

```
x8 = SYS_clock_nanosleep (115)
x0 = CLOCK_MONOTONIC (1)
x1 = 0            (TIMING_MODE_RELATIVE via explicit zero flags)
x2 = &req         ({DELAY_SECONDS, 0})
x3 = &rem
```

Ident (both variants equal length): `THYME-R3-P1B-INIT ABI4 DELAY=08` /
`THYME-R3-P1B-INIT ABI4 DELAY=24`.

## 4. Return / error handling (fail-closed)

* ret == 0 -> sleep completed -> `reboot(LINUX_REBOOT_CMD_RESTART)`.
* ret == -EINTR -> `req = rem` (remaining interval of the relative sleep),
  retry until the full requested delay has elapsed.
* any other ret < 0 -> `exit_group(111)` so PID 1 dies, the kernel panics and
  RT-D bootargs `panic=5` restore Android A. A sleep failure can no longer
  masquerade as a completed delayed reboot.
* if `reboot()` returns -> `exit_group(112)` (no fall-through).

## 5. Exact UAPI pin (FIXED_INIT_SYSCALL_AUDIT=PASS)

Linux 6.6.156, source commit `8b73de7da85fde281a385e0b26eda9bffd3ca477`,
verified against the pinned tree UAPI: `__NR_clock_nanosleep 115`,
`__NR_reboot 142`, `__NR_exit_group 94` (include/uapi/asm-generic/unistd.h),
`EINTR 4`; `SYSCALL_DEFINE4(clock_nanosleep)` in kernel/time/posix-timers.c
(CONFIG_POSIX_TIMERS=y). Patch queue 0001+0002 only; primary_entry NORMAL.

## 6. Exact fixed binary disassembly

Recorded from GHA run: 34741153230 (job `fixed-init-proof`, gates PASS;
disasm artifacts `fix8-disasm.txt` / `fix24-disasm.txt` in the
`thyme-r3-p1b-init-control-fix-proof` artifact).

Gate results:
- 4-arg block: `mov x0, #0x1` (clockid), `mov x1, xzr` (flags=0),
  `mov/add x2, sp...` (&req), `mov/add x3, sp...` (&rem) before `svc #0`.
- `DELAY_CONSTANT_IS_LIVE=YES`: `mov #0x8`/`#0x18` stored into `req.tv_sec`
  on the stack.
- EINTR retry: `cmn x0, #4` branch back into the sleep call.
- Fail-closed exits: `exit_group(111)` (sleep failure) and
  `exit_group(112)` (reboot returned) materialized as immediates.
- Reboot ABI unchanged: 0xfee1dead / 0x28121969 / 0x01234567 / x3=0.

FIX8 init SHA256: f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d
FIX24 init SHA256: cd3290faa184f4fa951566d25c0a3bfcc811b7c3c4b5217a2feb1cb8cb34ebd0

## 7. QEMU strace FIX8 (exact binary, pinned qemu-aarch64 8.x)

Expected and gated line shape:

```
clock_nanosleep(CLOCK_MONOTONIC,0,{tv_sec = 8,tv_nsec = 0},...) = 0
reboot(4276215469,672274793,19088743,0,0,0) = -1 errno=1 (Operation not permitted)
exit_group(112)
```

flags slot must be `0` (never `&req`), rqtp must be `tv_sec = 8` (never the
zeroed rem). Recorded (run 34741153230, exact binary `p1b-init-fix8`):
strace line matched verbatim, `reboot = -1 errno=1 (Operation not permitted)`,
`exit_group(112)`, runtime 8.003s rc=112, all five-way gates PASS.

## 8. QEMU strace FIX24

Same shape with `tv_sec = 24`, return 0, reboot EPERM, `exit_group(112)`.
Recorded (run 34741153230, exact binary `p1b-init-fix24`): strace line matched
verbatim, runtime 24.004s rc=112, all five-way gates PASS.

## 9. QEMU timing pair (preregistered)

Per-binary wallclock bands: FIX8 in [6.5, 9.5]s, FIX24 in [22.5, 25.5]s.
Pair delta bands (preregistered in the failure-isolation stage and reused):
STRONG 15.5-16.5s, SUPPORTED 15.0-17.0s, else FAIL
(`R3_P1B_INIT_CONTROL_FIX_FAILED`, no further packaging).

QEMU_FIX8_RUNTIME: 8.003s (rc=112)
QEMU_FIX24_RUNTIME: 24.004s (rc=112)
QEMU_FIXED_PAIR_DELTA: 16.000s
Verdict: STRONG (inside preregistered 15.5-16.5s band)

The gate is five-way (strace ABI + requested duration + syscall return +
wallclock + pair delta); wallclock alone is never sufficient. An EINTR
interruption fixture (ITIMER_REAL SIGALRM 1s into a 4s relative sleep,
raw rt_sigaction 134 with SA_RESTORER 0x04000000, sigsetsize 8, setitimer
103) must observe `-EINTR` with the remaining interval and complete the full
delay after retry.

## 10. Fixed initramfs

Deterministic newc cpio per delay (dev/init/proc/sys, /init mode 0755 uid=0
gid=0), built twice byte-identical, archive /init byte-exact to the compiled
binary, each Image embeds exactly its own cpio uncompressed.

initramfs-fix8.cpio SHA256: 02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3
initramfs-fix24.cpio SHA256: 2ae6fbf23601e6a04bd53a8651c1ccf52451cfa9530bef413ce7c882cc08f420

## 11. Rebuilt Image geometry

The fixed /init changes the kernel Image; geometry is recomputed from the
FIXED final Image, never inherited
(no reuse of image_size=0x2230000 / DTB_OFFSET=0x2380000 unless re-measured):

FIXED_IMAGE_SIZE (header image_size): 0x2231000 (35848192, +0x1000 vs the old
broken pair; pair identical)
FIX8/FIX24 Image file size: 0x2187000 (35166720) (pair identical)

## 12. Recalculated DTB_OFFSET

`D = align_up(I + 0x80000, 0x200000) - 0x80000` with the proven
`S mod 2MiB = 0x80000`; verified `D >= I` and `(0x80000 + D) mod 0x200000 = 0`.

FIXED_DTB_OFFSET: 0x2380000 (37224448; equals the old value by recomputation:
align_up(0x2231000 + 0x80000, 0x200000) - 0x80000 = 0x2380000, not inherited)
Placement proof: P1B_DTB_PLACEMENT_PROOF=PASS (GHA-gated)

## 13. Trampoline revalidation

Two-pass assembly with recomputed `entry_rel`/`dtb_rel`, DAIF mask, x0 =
S + DTB_OFFSET, x1=x2=x3=0, branch to normal primary_entry, no copydown, no
MMU/cache/EL writes, relocations 0, payload-address algebra gate re-run.

Trampoline SHA (FIX8 == FIX24, must be identical):
362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623
Algebra gate: P1B_TRAMPOLINE_GATES=PASS (GHA-gated)

## 14. RT-D identity (frozen)

RT-D SHA256 `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
(144593 bytes, bootargs `rdinit=/init panic=5 loglevel=7`) embedded verbatim
as the payload trailer, trailer SHA re-verified after packaging.

## 15. Fixed pair semantic delta

FIX8 vs FIX24 differ only in the requested sleep duration (8 -> 24):
ident constant 08/24 plus the `mov #0x8`/`#0x18` immediate; control flow,
syscall ABI, error handling and reboot path identical.
`P1B_FIXED_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY`.

Negative fixtures (regression guard, all REJECTED by the same checkers):
old sys3 3-arg ABI, flags slot holding &req, rqtp=&rem without req
(disasm-clean, caught by the runtime band only), unchecked sleep return.

## 16. Private boot identity

Private GHA (ChuenSan/thyme-mainline-private-ci, workflow
`thyme-r3-p1b-init-control-fix.yml`) splices the public FIX payloads into the
authoritative M5D boot v3 envelope
(4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63):
`thyme-r3-p1b-fix8-boot.img` / `thyme-r3-p1b-fix24-boot.img`, envelope diff
kernel-payload-and-kernel-size only, capacity < 201326592, RT-D trailer
re-verified. The public artifact `thyme-r3-p1b-fix8-fix24` never contains a
boot image. Old INIT8/INIT24 boot artifacts remain untouched.

Private run: 34744041027 (conclusion success; the first attempt 34743081369
correctly failed its then-preregistered raw byte-count gate and is superseded
by the attribution gate below)
FIX8 boot size/SHA256: 37380096 /
ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5
FIX24 boot size/SHA256: 37380096 /
20d5523361ac2c524bd72d8e16396e176374b9d48957a8b1501957db0aa573df
FIX8 payload SHA256: 4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41
FIX24 payload SHA256: 8d2e36e043bf891a680f879a045aab14d1decf80a897246584cc38d2d1d03439

Payload-level pair diff provenance (private precheck): the raw pair diff is
59767 bytes, fully attributed without weakening identity. CONFIG_IKCONFIG=y
embeds the gzipped kernel config between the `IKCFG_ST`/`IKCFG_ED` markers;
the two pair builds differ in exactly one config line
(`CONFIG_INITRAMFS_SOURCE` path `initramfs-8s.cpio` vs `initramfs-24s.cpio`),
so the deflate stream avalanches (spans 62075/62078 bytes, end marker shifts
+3). All remaining diffs are 76 bytes of build-stamp scatter (kernel banner /
UTS_VERSION) plus the 3-byte cpio delay delta. Gates:
`FIXED_PAIR_INIT_IDENT_ANCHOR=PASS`,
`FIXED_PAIR_IKCONFIG_SINGLE_LINE_DIFF=PASS`,
`FIXED_PAIR_GEOMETRY_IDENTICAL=YES`,
`P1B_FIXED_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY`.

## 17. Future device plan

Even if every CI gate is green, the next device stage is
`MAINLINE_V2_R3_P1B_FIXED_INIT8_TRUE_DEVICE_CONTROL`: FIXED INIT8 only, one
experimental boot, explicit user approval, no FIXED INIT24 in the same
approval. The true-device observer identity-gates on the FIXED INIT8 SHA only.

## 18. Evidence boundary

A FIXED INIT8 automatic return to Android A yields only
`FIXED_INIT8_PROVISIONAL_SIGNATURE` (panic=5 remains a competing path). Only
`FIX24_TOTAL - FIX8_TOTAL ~= +16s` proves that the /init delay controls the
true-device timeline (E1-E4 PROVEN, RT_D_FUNCTIONAL_FOR_MINIMAL_BOOT=YES).
Until then E1-E4 stay NOT_PROVEN, E0 PROVEN, E5 (USB) FROZEN.

## 19. PANIC / checkpoint fallback

PANIC30 stays NOT EXECUTED / NOT CURRENT NEXT and is re-enabled only if the
fixed exact /init + QEMU pair are correct but a future fixed device pair still
fails. Checkpoint ladder T0 trampoline / T1 primary_entry / T2
__primary_switched remains a future fallback; no device-ready checkpoints are
generated in this stage.

## Final gate

`READY_FOR_R3_P1B_FIXED_INIT8_DEVICE_CONTROL=YES` only when all of the
following PASS: fixed init source ABI, syscall numbers, 4-arg mapping, return
handling, EINTR handling, exact-binary QEMU trace, exact-binary runtime, QEMU
pair delta, delay constant live, initramfs identity, normal Image,
primary_entry normal, fixed pair geometry, DTB offset, trampoline algebra,
RT-D identity, private boot packaging, capacity. Otherwise
`R3_P1B_INIT_CONTROL_FIX_FAILED` or `R3_P1B_FIXED_PAIR_CI_NOT_READY`.

Recorded final gate (public run 34741153230 + private run 34744041027, both
conclusion success): all listed gates PASS, verdict
`READY_FOR_R3_P1B_FIXED_INIT8_DEVICE_CONTROL=YES`. Device operation remains NO
until the user approves
`MAINLINE_V2_R3_P1B_FIXED_INIT8_TRUE_DEVICE_CONTROL` (FIXED INIT8 only).
E1-E4 remain NOT_PROVEN until the true-device pair proof; PANIC30 FROZEN;
M5N FROZEN; Current B (M5D+M5H+M5M-B) UNCHANGED; Slot A untouched.
