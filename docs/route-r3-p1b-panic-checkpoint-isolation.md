# R3 P1B panic / checkpoint isolation (MAINLINE_V2_R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_CI)

Round type: CI / SOURCE AUDIT ONLY. `DEVICE_OPERATION=NO`, `ADB_DEVICE_OPERATION=NO`,
`FASTBOOT_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`,
`SET_ACTIVE=NO`, `B_BOOT=NO`. All builds (kernel, DTB, initramfs, assembly,
link, objdump/readelf, QEMU, boot image generation, binary validation) run on
GitHub Actions only; nothing is built or validated locally. Current B
(M5D + M5H + M5M-B) is UNCHANGED; M5N, FIX24, USB, UFS/rootfs/network are
FROZEN. PANIC30 and the checkpoint family may reach CI DEVICE-READY /
CI-prototype status at most this round; no device run is approved by this doc.

## 1. Frozen FIXED INIT8 result

| fact | value |
| --- | --- |
| FIXED INIT8 device TOTAL | 23.852 s (private run 34744041027) |
| OLD BROKEN INIT8 device TOTAL | 23.184 s |
| OLD BROKEN INIT24 device TOTAL | 24.570 s |
| old pair delta | 1.386 s (expected 16.000 s, NO_MATCH) |
| FIXED vs BROKEN INIT8 | +0.668 s |
| FIXED /init exact QEMU sleep | 8.003 s (ABI4) |
| classification | NOT_CONSISTENT_WITH_8S_DELAY |
| current reliable conclusion | DEVICE_RETURN_PATH_NOT_OBSERVED_TO_FOLLOW_INIT_SLEEP=YES |

This is not equivalent to "/init definitively never executed". Competing
explanations remain open (sleep syscall runtime failure on device, independent
reset path, pre-init panic, early Linux failure, firmware reset).

Frozen hashes (FIX8, public run 34741153230):

- FIX8 payload `4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41`
- FIX8 final Image `dffce20ec44de65fc7d271b01f6c1b4c39716923aafd4c24fae165e8e8424944`
  (image_size `0x2231000`, file `35166720`)
- /init `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d`
- initramfs cpio `02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3`
- trampoline `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`
- RT-D `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
  (size 144593)

## 2. Evidence recalibration

Current formal ladder (conservative; behavioral side-signatures are kept but
never upgrade E1/E2):

| level | statement | status |
| --- | --- | --- |
| E0 | ABL -> controlled payload | PROVEN |
| E1 | normal Mainline Linux entry reached | NOT_PROVEN |
| E2 | early Mainline boot | NOT_PROVEN |
| E3 | built-in initramfs reached | NOT_PROVEN |
| E4 | /init executed | NOT_PROVEN |
| E5 | USB | FROZEN |

`M5_STYLE_4P7S_PATH_NOT_OBSERVED=YES` and
`AUTOMATIC_ANDROID_RETURN_SIGNATURE=YES` remain behavioral side evidence only.
Historical "E1/E2 SUPPORTED" stays a historical observation; no current gate
consumes it.

## 3. Hypothesis families

The round does not preselect a family:

- H0 trampoline/handoff fails before or during handoff
- H1 branch to primary_entry happens but head.S early code fails
- H2 partial head.S, no stable C kernel
- H3 start_kernel / setup_arch neighborhood failure
- H4 panic after command-line-aware stage
- H5 failure before initramfs
- H6 initramfs reached but /init not executed
- H7 /init executes, another independent reset path exists
- H8 firmware / non-Linux reset path

PANIC30 discriminates inside H4 vs the rest; T0/T1/T2 discriminate H0/H1/H2
reachability directly.

## 4. panic= source path (Linux 6.6.156, commit 8b73de7da85fde281a385e0b26eda9bffd3ca477)

- Registration: `kernel/panic.c:781` `core_param(panic, panic_timeout, int, 0644)`
  -> `include/linux/moduleparam.h:327` `__module_param_call` ->
  `__section("__param")`. panic= is a STANDARD boot parameter, NOT an
  early_param.
- Initial value: `kernel/panic.c:66` `int panic_timeout = CONFIG_PANIC_TIMEOUT;`
  with `lib/Kconfig.debug:1002` `config PANIC_TIMEOUT ... default 0`.

## 5. Command-line parse stage

`init/main.c` start_kernel ordering (verified by index gates in CI):

```
setup_arch(&command_line)           # main.c:871, arm64 early FDT scan inside
setup_command_line(command_line)    # main.c:873
pr_notice("Kernel command line…")   # main.c:879
parse_early_param()                 # main.c:882
parse_args("Booting kernel", static_command_line, __start___param, …)  # main.c:883
```

`PANIC_CMDLINE_PARSE_STAGE=START_KERNEL_PARSE_ARGS_BOOTING_KERNEL_AFTER_SETUP_ARCH_AND_PARSE_EARLY_PARAM`.

## 6. panic_timeout activation stage

Activation happens inside `parse_args("Booting kernel")` via
`param_set_int` writing `panic_timeout`. Any Linux panic BEFORE this point
(including setup_arch and early params) still sees `panic_timeout = 0`; with
0, `kernel/panic.c:419` `if (panic_timeout != 0)` is false, so the wait loop
and `emergency_restart()` are skipped and `panic()` returns (it is not
`__noreturn`, `kernel/panic.c:276`).

`PANIC_PRE_PARSE_PANIC_OBEYS_CMDLINE=NO` — a pre-parse Linux panic under the
current config cannot produce a panic-path controlled restart at all.

Wait-accuracy boundary: the delay is `PANIC_TIMER_STEP=100` ms `mdelay` loop
(`kernel/panic.c:41,410`), and arm64 `mdelay -> __udelay -> __const_udelay`
depends on `loops_per_jiffy` (`arch/arm64/lib/delay.c:21-24`); the preset is
`unsigned long loops_per_jiffy = (1<<12)` (`init/main.c:226`) and
`calibrate_delay()` runs at `init/main.c:1011`, AFTER parse_args. Therefore
`PANIC_PRE_CALIBRATE_DELAY_WAIT_ACCURATE=NO`: a panic between cmdline parse
and calibration would NOT wait a wall-clock 30 s even if it reached the
timeout loop.

## 7. Panic restart path

```
panic()  [kernel/panic.c:276]
  -> if (panic_timeout > 0): 100 ms mdelay loop  [panic.c:403-417]
  -> if (panic_timeout != 0): emergency_restart()  [panic.c:419-427]
     -> kmsg_dump(KMSG_DUMP_EMERG) + machine_emergency_restart()
        [kernel/reboot.c:74-80]
     -> machine_restart(NULL)  [include/asm-generic/emergency-restart.h:5]
     -> local_irq_disable + smp_send_stop (+ efi_reboot only if EFI runtime
        services are live; not the case on the ABL direct path)
        [arch/arm64/kernel/process.c:126]
     -> do_kernel_restart(cmd) -> restart_handler chain
        [kernel/reboot.c:216]
     -> psci_sys_reset -> PSCI_0_2_FN_SYSTEM_RESET (0x84000009) via smc
        [drivers/firmware/psci/psci.c:308,628]
```

RT-D carries `/psci` (`compatible = "arm,psci-1.0"`, `method = "smc"`,
inherited from `sm8250.dtsi:687` through the thyme board DTS), so the kernel
restart chain is closed under RT-D. The terminal
PSCI SYSTEM_RESET -> ABL -> Android A matches the observed
`AUTOMATIC_ANDROID_RETURN_SIGNATURE`.

`PANIC_RESTART_PATH=PANIC->EMERGENCY_RESTART->MACHINE_RESTART->DO_KERNEL_RESTART->PSCI_SYSTEM_RESET_SMC`.

Note: defconfig keeps `CONFIG_KEXEC/CONFIG_KEXEC_FILE/CONFIG_CRASH_DUMP=y`;
`crash_kexec(NULL)` in panic() is a no-op without a loaded crash kernel (no
kexec tooling runs before /init), so the timeout path is taken.

## 8. Final cmdline provenance

- RT-D `/chosen/bootargs = "rdinit=/init panic=5 loglevel=7"` (frozen;
  size-anchored by `parse_fdt_chosen`).
- Assembly: `drivers/of/fdt.c` early_init_dt_scan_chosen copies bootargs into
  `boot_command_line`; the `CONFIG_CMDLINE` block keeps the DT value unless
  `CONFIG_CMDLINE_FORCE` (override) or extends with `CONFIG_CMDLINE_EXTEND`.
- arm64 Kconfig defaults: `CONFIG_CMDLINE=""`, choice default
  `CMDLINE_FROM_BOOTLOADER` (arch/arm64/Kconfig:2342); FORCE/EXTEND unset and
  neither config fragment (`thyme-route-b.config`, `thyme-r3-p1b.config`)
  sets any of them. The merged `.config` is re-checked in CI by semantics:
  `CONFIG_CMDLINE=""`, no `CONFIG_CMDLINE_FORCE=`/`CONFIG_CMDLINE_EXTEND=` =y
  line (the literal "# ... is not set" lines are absent because the cmdline
  choice prompt is hidden when `CMDLINE=""` — arch/arm64/Kconfig:2340 — so
  the choice members are omitted from the written `.config`),
  `CONFIG_PANIC_TIMEOUT=0`.
- The trampoline forces `x0` to the RT-D address, overriding anything ABL
  would pass; the boot v3 header cmdline (M5D envelope, preserved verbatim by
  private pack gates) is not consumed by the kernel.
- `rdinit=` is consumed via `__setup("rdinit=", rdinit_setup)`
  (`init/main.c:577`) in the same parse_args stage; `loglevel=` is an early
  param.

`P1B_FINAL_CMDLINE_SOURCE=RT_D_CHOSEN_BOOTARGS_ONLY`,
`P1B_RTD_BOOTARGS_EFFECTIVE_BY_DESIGN=YES`,
`DUPLICATE_PANIC_PARAMETER=NO`. Because the provenance is closed, PANIC30 is
allowed to reach CI DEVICE-READY; had it been uncertain, PANIC30 would have
been blocked.

## 9. PANIC30 construction

PANIC30 (`P1B-PANIC30`) is a diagnostic control, not a fix. Baseline: exact
FROZEN FIX8. The only intended runtime-semantic change:
RT-D `/chosen/bootargs` `panic=5` -> `panic=30`. Fixed /init stays ABI4
DELAY=8. The 24s-delay variant is FORBIDDEN.

Construction is byte-exact: public CI downloads the frozen FIX8 payload from
public run 34741153230, verifies `4f34eabf…`, and builds
`PANIC30 payload = frozen_payload[0:DTB_OFFSET] + PANIC30_RT_D`. The original
RT-D is never overwritten (`PANIC30_RT_D_SHA` is independent). Frozen RT-D:
`4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327` (144593).

## 10. RT-D structured semantic diff

`PANIC30_RT_D_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY` is proven by:

1. structured FDT surgery: the bootargs property value grows 32 -> 33 bytes,
   the struct block tail is shifted (+4), `off_dt_strings`/`totalsize`/
   `size_dt_struct` are fixed up, everything else is copied verbatim;
2. property-level diff (structured parser walk of both blobs): exactly one
   differing property `/chosen::bootargs`, new value = old value with
   `panic=5` -> `panic=30`;
3. header cross-check: version, last_comp, boot_cpuid, size_dt_strings,
   mem_rsvmap region identical;
4. dtc cross-decompile: `dtc -I dtb -O dts` of both blobs, textual diff is
   exactly the bootargs line pair.

Any other property change FAILS the build.

## 11. Geometry

Re-proven, not assumed (`DTB_OFFSET` expected `0x2380000`):

- image_size unchanged `0x2231000` -> `DTB_OFFSET = align(0x22B1000, 2 MiB) −
  0x80000 = 0x2380000` (CI recomputes from the frozen payload header);
- `(S_residue + DTB_OFFSET) % 2 MiB == 0` (RT-D starts a fresh 2 MiB region);
- payload size = `DTB_OFFSET + len(PANIC30_RT_D)` (RT-D grows by 4 ->
  payload grows by 4);
- boot v3 size = `align4k(4096 + payload) + 4096` tail; the +4 is absorbed by
  the page alignment (est. unchanged 37,380,096-class, exact value in the
  manifest);
- capacity: margin vs `BOOT_CAP = 201326592` >= 16 MiB.

Identity gates:

`PANIC30_IMAGE_IDENTICAL_TO_FIXED_INIT8=YES` (payload prefix
`[0, DTB_OFFSET)` copied verbatim from the frozen FIX8 payload whose kernel
region is hash-anchored compositionally: `sha(payload) == FIX8_PAYLOAD_SHA`
plus `sha(RT-D) == RT_D_SHA` pin `payload[:DTB_OFFSET]` exactly — the region
is the PATCHED Image (code1 -> `b 0x40`, trampoline at 0x40), never the raw
Image file behind `dffce20e…44944`; CI additionally spot-checks the payload
layout and the embedded 48-byte trampoline against `TRAMP_SHA`),
`PANIC30_INIT_IDENTICAL=YES`,
`PANIC30_INITRAMFS_IDENTICAL=YES`, `PANIC30_TRAMPOLINE_IDENTICAL=YES` — the
latter three re-proven by rebuilding /init, the cpio, and the trampoline this
round and requiring byte-identity with the frozen FIX8 hashes. The rebuilt kernel Image is compared to the frozen prefix with a
scatter-attribution gate (the IKCONFIG gz avalanche window — the
`CONFIG_INITRAMFS_SOURCE` path length differs between runs, so the ~62 KiB
compressed config body and the region it shifts downstream differ wholesale —
plus <=64 B per range / <=4 KiB total build-stamp scatter outside that window;
anything wider FAILS — kernel builds are not fully byte-stable, see the
private pair-diff precedent). Only RT-D trailer, payload SHA, and boot
kernel_size/boot SHA change as a consequence of length.
`PANIC30_RUNTIME_SEMANTIC_DELTA=PANIC_TIMEOUT_ONLY` (never
"BYTE_DELTA_ONLY"; all extra byte diffs are attributed).

## 12. Expected +25 s interpretation (pre-registered)

Baseline: FIXED INIT8 TOTAL 23.852 s; panic 5 s -> 30 s; theoretical shift
+25.000 s. If `PANIC30_TOTAL − 23.852` lands in [24.0, 26.0] -> STRONG,
[23.0, 27.0] -> SUPPORTED for `PANIC_TIMEOUT_CONTROLS_RETURN_TIMELINE`.

A future positive result allows:

- `PANIC_TIMEOUT_VALUE_CONSUMED_BY_RUNNING_LINUX=YES`
- `LINUX_PANIC_TIMEOUT_PATH_REACHED=STRONGLY_SUPPORTED` or `PROVEN`
  (depending on exact static proof)
- Linux executed at least to the stage where the panic parameter is parsed
  AND the panic path uses `panic_timeout` — strongly upgrading E1; E2
  PROVEN/STRONGLY_SUPPORTED per the source-stage mapping.

E3/E4 stay NOT_PROVEN: the panic may still occur before initramfs. It is
FORBIDDEN to derive "/init executed" from +25 s. Combined with the wait
accuracy boundary (section 6), a positive shift additionally implies
`calibrate_delay()` had completed, i.e. the panic happened after the
scheduler/clock calibration neighborhood of start_kernel.

## 13. PANIC30 negative-result boundary

If PANIC30 still returns ~23-25 s without a meaningful shift, the ONLY
permitted record is:

`PANIC30_TIMEOUT_NOT_OBSERVED_TO_CONTROL_RETURN_TIMELINE=YES`

Never `NO_LINUX_PANIC`, never `LINUX_NOT_REACHED`: the panic may predate
parameter parsing, the panic path may not reach the timeout wait, the reset
may be non-panic, or the probe may not reach the expected path at all.
`PANIC30_NEGATIVE_RESULT_CAN_EXCLUDE_ALL_LINUX_PANIC=NO`. A negative result
moves the route to the checkpoint ladder (section 22).

## 14. PANIC30 future device classification table

| class | observation | proves | does NOT prove | next |
| --- | --- | --- | --- | --- |
| P30-A | automatic Android return, shift ~ +25 s | panic timeout consumed by running Linux; Linux reached cmdline-aware panic path (E1 strong upgrade) | /init executed; initramfs reached | PANIC SOURCE LOCALIZATION or late checkpoint |
| P30-B | automatic Android return, no meaningful shift | timeout not observed to control the return timeline | nothing about Linux absence | checkpoint ladder, start with T0 |
| P30-C | automatic stable Fastboot | the packed image changed the reset path class | cause | independent classification, STOP and analyze |
| P30-D | no return >120 s | return path broken/changed | cause | STOP; recovery via normal procedure; independent classification |
| P30-E | behavior changed, neither timing class | undefined anomaly | — | STOP; independent classification |
| P30-F | boot not accepted (fastboot reject) | packaging/ABL acceptance issue | — | STOP; packaging forensics |

Each future device run: one approval, one boot; no automatic chaining.

## 15. T0 design (trampoline-internal checkpoint)

- Position: inside the P1B trampoline, after `msr daifset #0xf; isb`, the
  `adr/ldr/add` RT-D address calculation and `x1=x2=x3=0`, BEFORE
  `b primary_entry`.
- Probe: reach-and-reset — controlled CNTPCT delay (8 s, `cntfrq_el0`-scaled)
  -> PSCI SYSTEM_RESET `0x84000009` via `smc #0` -> on smc return, restore
  `x0/x1/x2/x3` and fall through to `primary_entry` (fail-safe: the normal
  handoff contract is restored bit for bit).
- Discipline: register-only (x9-x15), position independent, no stack, no
  memory write, no arbitrary memory read (the literal-pool `ldr` is
  PC-relative), relocations = 0; framework reused from the P0 / entry-state /
  alignment probes.
- Constants are re-derived THIS round from the final artifact
  (`entry_rel`, `dtb_rel` recomputed in CI); historical offsets are not
  copied.
- CI gates: symbol/offset algebra, disassembly tokens (daifset, cntfrq,
  cntpct, movz/movk FID, smc), no store/adrp, no forbidden ops, branch target
  == primary_entry, x0 static algebra == DTB_OFFSET, dtb_rel quad present.

`T0阳性` proves only: the large P1B artifact was loaded by ABL to an
executable location, `code0 -> 0x40 trampoline` executes, the trampoline
reaches the pre-branch point, and timer/PSCI remain usable. T0 does NOT
prove RT-D trailer consumption by Linux, primary_entry execution, or a
normal Linux boot. `CHECKPOINT_T0_CI=PASS` this round (prototype).

## 16. T1 design (primary_entry checkpoint)

- Target: normal Linux `primary_entry`, earliest safe point = its first
  instruction (`bl record_mmu_state`, `arch/arm64/kernel/head.S`). Placing
  the checkpoint literally at the first instruction is possible because the
  probe needs no state except PC-relative code and x9-x15.
- Symbol offset re-derived this round from the built `vmlinux` (`nm`); the
  historical `0x1b1c0a0` is NOT a gate constant (equality is reported as
  information only).
- Artifact: the first instruction is patched to `b <gap>` where `<gap>` is
  the first free byte after the Image file (payload gap, loaded and
  executable per `ABL_LOADS_FULL_BOOT_KERNEL_SIZE`); the gap probe runs the
  same reach-and-reset body (CNTPCT delay 8 s -> PSCI SMC) and terminates in
  a `wfe` spin. It does not continue Linux.
- Register discipline: x9-x15 only; x0-x3 untouched (boot protocol state
  preserved); no stores; relocations = 0.
- Replaced-instruction accounting: exactly ONE instruction replaced, original
  bytes recorded in the T1 report and asserted to be `bl record_mmu_state`
  via the existing kernel gate.
- Negative boundary: a missing T1 signature does NOT immediately prove
  "primary_entry never reached"; T1 CI is fail-closed on its own
  instrumentation (branch patch algebra, replaced-instruction check, probe
  disasm, timer/PSCI tokens).

`CHECKPOINT_T1_CI=PASS` this round (prototype on the rebuilt Image;
`DIAGNOSTIC ONLY`, never a "normal P1B boot candidate").

## 17. T2 source audit (__primary_switched)

- Selected symbol: `__primary_switched` (`arch/arm64/kernel/head.S:472`),
  offset derived this round from `vmlinux`.
- Entry state (source-audited): MMU ON (post `__primary_switch`), PC in
  kernel VA space, SP valid (init_task stack), DAIF still masked (no
  daifclr/irq-enable on the primary path before `start_kernel`), x20 (boot
  mode) and x21 (FDT pointer) live, `x0` reused for FDT pass.
- Environment deltas vs T0/T1: MMU-on is the only relevant difference for a
  PC-relative, store-free probe; the gap probe address lies inside the kernel
  image map (within `image_size`); `cntpct_el0` remains readable at EL1 and
  the clockevents layer has not taken the timer yet; `smc #0` from EL1 is
  legal (RT-D `/psci method="smc"` confirms the conduit).
- `T2_TIMER_RESET_SAFE=YES` (conditional on the audit above). A T2 prototype
  artifact is NOT generated this round (design only; no device candidate).
- T2 positive boundary: primary_entry early path + idmap/MMU switch executed
  up to `__primary_switched`; does NOT prove `start_kernel` entry. T3
  (start_kernel / setup_arch / cmdline) is explicitly OUT OF SCOPE this
  round.

`CHECKPOINT_T2_STATUS=DESIGNED`.

## 18. Checkpoint evidence boundaries

Checkpoints are reach-and-reset diagnostics that deliberately terminate the
normal path: a checkpoint timing positive is
`CHECKPOINT_REACHABILITY_PROOF`, never `BOOT_SUCCESS`. Proof ladder:

- T0: trampoline executed to pre-branch; timer/PSCI alive.
- T1: trampoline branch target correct; `primary_entry` executed to the
  checkpoint. Does not prove record_mmu_state/completion, create_idmap, MMU
  switch, start_kernel, DTB parse, initramfs.
- T2: idmap/MMU-switch path executed to `__primary_switched`; does not prove
  `start_kernel`.

## 19. Checkpoint safety gates (CI)

- T0: symbol/offset, disassembly, timer code, PSCI FID, no stack, no memory
  write, relocations = 0, branch path algebra.
- T1: all of the above + exact primary_entry insertion + replaced-instruction
  accounting + register preservation (x0-x3 untouched).
- T2: all of the above + MMU state + VA/PA semantics + stack + timer access +
  PSCI safety (audit this round).

Missing any item -> corresponding checkpoint NOT_READY. Checkpoint timing
pairs (8 s / 24 s) may be designed later; this round only proves encoding.
Future device use: one approval, one boot, single signature first, separate
approval for any pair confirmation; checkpoints are never mixed with the
normal boot path (different workflow, artifact, SHA, docs, approval).

## 20. CopyMem priority

`COPYMEM_PRIORITY=LOWERED`. Three same-scale P1B artifacts (broken INIT8,
broken INIT24, fixed INIT8) were all fastboot-accepted and entered the same
23-25 s return class; CopyMem is not the primary suspect. Only a T0
reachability failure raises `COPYMEM_PRIORITY` again.

## 21. RT-D status

`RT_D_STRUCTURALLY_COMPLETE=YES` (RAM map and reserved-memory validated).
Runtime minimal-boot functional: `NOT_PROVEN`. If a future PANIC30 shift
~ +25 s appears, upgrade to
`RT_D_BOOTARGS_CONSUMED_BY_RUNNING_LINUX=YES`; never
`ALL_RT_D_HARDWARE_FUNCTIONAL`. No new persistent logging (ramoops/pstore/
UART/USB gadget/earlycon/new reserved-memory) is added this round — single
variable isolation; empty pstore remains non-evidence of Linux absence.

## 22. Decision tree

```
PANIC30 (if device-approved later)
  shift ≈ +25s -> Linux reached cmdline-aware panic path
                   -> PANIC SOURCE LOCALIZATION or late-stage checkpoint
  no shift      -> T0
                   T0 + -> T1
                   T0 - -> raise COPYMEM_PRIORITY, load-path forensics
                          T1 + -> T2
                          T1 - -> T1 instrumentation forensics (fail-closed)
                                 T2 + -> start_kernel / setup_arch / cmdline /
                                         initramfs / exec /init studies (T3+)
```

## 23. Current-state summary

- Baseline FIXED INIT8: 23.852 s, delay not reflected (+0.668 s vs broken).
- Evidence ladder: E0 PROVEN; E1/E2/E3/E4 NOT_PROVEN; E5 FROZEN.
- panic audit: closed (registration/parse/activation/restart path above).
- cmdline provenance: closed; PANIC30 permitted to CI DEVICE-READY.
- PANIC30: built on frozen FIX8 bytes; `PANIC30_RUNTIME_SEMANTIC_DELTA=
  PANIC_TIMEOUT_ONLY`; identity + geometry gates this round.
- Checkpoints: T0/T1 CI prototypes PASS; T2 DESIGNED.
- CopyMem priority LOWERED. Current B UNCHANGED (M5D+M5H+M5M-B). FIX24, M5N,
  USB frozen. No device operation.

## 24. Next stage

1. This round's public CI + private PANIC30 pack (boot.img, private repo
   only, no flash).
2. Await user approval; if approved, the next device round is ONE boot of
   P1B-PANIC30 against the FIXED INIT8 baseline (23.852 s) with the
   pre-registered classification table (section 14).
3. P30-B (no shift) -> T0 device round (separate approval).
4. Persistent observability (pstore/ramoops/UART) and driver bring-up remain
   deferred until E1-E4 close.

`READY_FOR_R3_P1B_PANIC30_DEVICE_CONTROL` is the intended final gate of this
round when all CI gates pass; `R3_P1B_EARLY_CHECKPOINT_REQUIRED` if PANIC30
loses discriminating power statically; `R3_P1B_PANIC_OR_CHECKPOINT_ISOLATION_INCOMPLETE`
if the checkpoint architecture stays incomplete.

## 25. Round CI record

Public CI (ChuenSan/xiaomi10s, run 34754072600, commit c001114c, all 4 jobs
green — audit / source-gate / panic30-build+gates / independent
re-verification):

- `PANIC30_RT_D_SHA256 = dfbfca033662af4c7f01be46ad71efee16cf085ff4e136f9abada6faefcc3390`
  (144597 = frozen 144593 + 4);
- `PANIC30_PAYLOAD_SHA256 = cd3f75279b9b2335c4a16594452fb6b0ac68224eb720320c99f07da60ca3687e`
  (37369045 = frozen 37369041 + 4); `panic30_boot_size_est = 37380096`;
- header image_size of the frozen payload AND the fresh rebuild:
  `0x2230000` (file size 0x2189a00 both). Note: the FIX8 manifest json
  records `image_size: 35848192` (0x2231000) which disagrees with both
  measured headers; both values land on the same `DTB_OFFSET = 0x2380000`,
  so geometry is unaffected. The header-measured value is authoritative;
- `primary_entry = 0x1b1c0a0` re-derived this round from vmlinux (matches
  the historical value — re-derived, not inherited); `__primary_switched =
  0x1b39534`; rebuilt-vs-frozen Image diff attributed to the IKCONFIG gz
  avalanche window (path-length shift) + 71 bytes of legitimate build-stamp
  scatter in 7 ranges (each <= 20 B);
- dtc cross-decompile diff: exactly the bootargs line pair;
- T0: 128-byte trampoline, branch 0xb0 -> 0x1b1c0a0, `X0_STATIC=0x2380000`,
  `PSCI_FID=0x84000009`, `CHECKPOINT_T0_CI=PASS`;
- T1: gap probe at 0x2189a00, replaces exactly `bl record_mmu_state`
  (0x1b1c0a0) with `b 0x2189a00`, register discipline x9-x15 only,
  `CHECKPOINT_T1_CI=PASS`;
- T2: `CHECKPOINT_T2_STATUS=DESIGNED`, `T2_TIMER_RESET_SAFE=YES` (MMU-on
  conditional audit, section 17).

Private CI (ChuenSan/thyme-mainline-private-ci, PANIC30 pack): inputs
`public_source_commit=c001114cf6854ecc41fc15f670b337f6c26475a7`,
`public_run_id=34754072600`, payload/RT-D SHAs as above. First dispatch
(run 34755574064) passed every pack gate but was tripped by the final
no-`*.img` assertion counting the DOWNLOADED M5D input; after exempting
`./m5d-artifact/*` the re-dispatch run 34755701908 is fully green:
`PRIVATE_REPO_VISIBILITY=PRIVATE`, `M5D_BOOT_SHA_EXACT=PASS` (envelope
4db8151b…), `P30_PACK_GATES=PASS`, `PANIC30_BOOT_SIZE=37380096` (matches the
public manifest estimate), `PANIC30_BOOT_SHA256 =
ea50e8b344219f39bde317503b9e238af88080ca7e55b9a14b5b0b825a8664b1`,
payload/RT-D SHAs re-verified identical to the public run, boot size
cross-check PASS. The boot.img exists ONLY as a private-repo artifact
(`thyme-r3-p1b-panic30-boot`). No flash, no device operation,
`READY_FOR_DEVICE=NO`.
