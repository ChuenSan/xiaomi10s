# Route R3 P1B restart-chokepoint RESET8/RESET1 predevice

Round: `MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_READINESS_CI`.
SOURCE AUDIT + PUBLIC GHA PAIR CONSTRUCTION + PAIR IDENTITY / SAFETY.
`DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`,
`LOCAL_BUILD=NO`. `PRIVATE_PACK_RUN=NONE`. `DEVICE_READY=NO`.
Final gate is not `READY_FOR_*_DEVICE_CONTROL`.

Exact tree: linux-6.6.156 `8b73de7da85fde281a385e0b26eda9bffd3ca477`.
Dirty worktree `/Volumes/LinuxDev/thyme-mainline` @ `5550dc2` UNTOUCHED.

## PENTRY pair no-shift

Frozen true-device pair (canonical `panic()` entry, delay-only):

| member | delay | TOTAL | payload SHA |
| --- | --- | --- | --- |
| PENTRY8 | 8s | 26.829s | `1988ee22806cba6129f7c3bb34def9667ec39c60f029c622f60341374cc35469` |
| PENTRY1 | 1s | 26.301s | `5fb893c6f990b23a26fe0aba7439852ff5991b59794f4ee4ab1fa7691b8328ee` |

```
PENTRY_PAIR_DELTA=-0.528
EXPECTED=-7.000
PAIR_ERROR=+6.472
R3_P1B_PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED
PANIC_ENTRY_RUNTIME_STATUS=NOT_PROVEN
PANIC_ENTRY_HYPOTHESIS_PRIORITY=REDUCED
PANIC_ENTRY_DELAY_CONTROL_REFLECTED=NO
NO_LINUX_PANIC=NOT_LICENSED
```

## why restart choke next

C6 / C_DELAY `14.464s` are PROVEN. The unknown interval is after
`calibrate_delay` until the ~26s Android A return.

The alternative reset map (GHA `34966848565`, commit `f714f3c`) is
COMPLETE. `kernel_restart` and `emergency_restart` (including panic-timeout
`emergency_restart`) both enter `machine_restart` on this arm64 config,
before `irq_disable` / `smp_send_stop` / `do_kernel_restart`. That is the
high-coverage Linux software-restart choke.

```
RESET_PAIR_PRIMARY_TARGET=machine_restart
```

`do_kernel_restart` is FALLBACK TARGET only. It is selected only if
`machine_restart` entry overwrite / runtime rewrite / landing-PAC cannot
close. Otherwise the target stays `machine_restart`.

## timing limitation

```
CAN_CAUSE_RESET=SOURCE_PROVEN
CAN_BE_REACHED_AFTER_C_DELAY=SOURCE_SUPPORTED
CAN_EXPLAIN_23_28S_TIMING=UNKNOWN
```

`machine_restart` can cause reset (source body ends in
`do_kernel_restart` + halt-loop). Callers exist after C_DELAY. There is
**no** source timer in `machine_restart`. The ~26s natural return does
**not** license `SOURCE_YES` timing. Restart call time is unknown.
26s timing source: NOT_DERIVED.

## machine_restart exact identity

Re-derived from **this round's** authoritative final vmlinux (not copied
from old docs). Consistency check against previous GHA `34966848565`:

| field | expected |
| --- | --- |
| symbol | `machine_restart` |
| MACHINE_RESTART_LINK_VA | `0xffff80008001849c` |
| MACHINE_RESTART_IMAGE_OFFSET | `0x1849c` |
| MACHINE_RESTART_FILE_OFFSET | `0x1849c` |
| MACHINE_RESTART_SECTION | `.text` |
| MACHINE_RESTART_SECTION_FLAGS | `AX` |
| entry0 | `paciasp` (`0xd503233f`, file bytes `3f2303d5`) |

GHA prints `entry0`..`entry31` and the live size. A VA/offset mismatch
against the previous authoritative vmlinux is a hard fail (pinned
toolchain + frozen FIX8).

## PAC/BTI/landing audit

Independent of the panic-entry landing plan.

- PAC: entry0 `paciasp` is re-emitted verbatim.
- BTI: `CONFIG_ARM64_BTI_KERNEL=y`; no BTI landing claim is made unless
  entry0 is `bti c`.
- SCS / CFI / fentry / patchable-function-entry / stack-protector
  prologue: config-gated OFF (`CONFIG_CFI_CLANG`, `CONFIG_SHADOW_CALL_STACK`,
  `CONFIG_FUNCTION_TRACER`, `CONFIG_DYNAMIC_FTRACE`, `CONFIG_KASAN`,
  `CONFIG_KCOV`, `CONFIG_PATCHABLE_FUNCTION_ENTRY` must not be `y`).
- `machine_restart` is not `EXPORT_SYMBOL`. Address-taken is decided by
  this-round ADRP scan, not by panic's export rule.

```
MACHINE_RESTART_ENTRY_AUDIT=PASS/FAIL (GHA)
```

## caller coverage

This-round Image scan of direct `B`/`BL` and ADRP page refs.

```
MACHINE_RESTART_COVERAGE_NORMAL_RESTART=YES   (kernel_restart)
MACHINE_RESTART_COVERAGE_EMERGENCY_RESTART=YES (emergency_restart, inlined
  machine_emergency_restart -> machine_restart(NULL))
MACHINE_RESTART_COVERAGE_PANIC_TIMEOUT_RESTART=YES (via emergency_restart)
```

Coverage boundary:

- Future pair STRONG only proves the dominant return passed through the
  `machine_restart`-covered Linux software restart chain.
- Future no-shift only lowers that hypothesis. It does **not** exclude
  direct firmware PSCI reset, secure-world reset, PMIC/watchdog
  autonomous reset, or Linux reset that bypasses `machine_restart`.
- Do not write `NO_LINUX_RESTART`.

## do_kernel_restart fallback

Statically audited (VA, section, entry0) as FALLBACK TARGET.
No RESET pair is generated at `do_kernel_restart` unless
`PRIMARY_TARGET_REJECTED_REASON` is set.

## runtime rewrite audit

Window scan: alternatives, jump labels, static calls, ftrace/mcount,
patchable entry, relocations/RELR, exception tables, literal pools,
branch targets into the window, KCFI, SCS.

```
RESTART_CHOKE_RUNTIME_REWRITE_OVERLAP=NONE_IN_WINDOW (required)
RESTART_CHOKE_INLINE_SAFE=YES
```

## probe architecture

```
RESTART_CHOKE_PROBE_ARCHITECTURE=INLINE
```

INLINE at the selected choke entry so the probe runs only if that symbol
is invoked. entry0 `paciasp` is preserved; the 76-byte diagnostic core
follows. External probe is allowed only if mapped, executable, stable,
runtime-rewrite-safe, and in branch range — otherwise PREDEVICE NOT
READY. Unproven padding is forbidden.

## FIX8 baseline

RESET pair is composed from the authoritative FIX8 normal payload.
All historical probes are absent (T0 T1 T2 T3 T4 C_DELAY PENTRY8 PENTRY1).

| identity | SHA |
| --- | --- |
| FIX8 payload | `4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41` |
| trampoline | `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623` |
| RT-D | `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327` |
| /init | `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d` |
| initramfs | `02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3` |

RT-D stays `panic=5` `rdinit=/init`. PANIC30 RT-D is rejected.
`/init` delay stays 8s for **both** pair members.

```
RESET_PAIR_ALL_PRIOR_PROBES_REMOVED=YES
RESET_PAIR_INIT_IDENTICAL=YES
```

## RESET8 design

Programmed diagnostic delay = 8s. INLINE at `machine_restart` entry.
Core: CNTFRQ_EL0 + CNTPCT_EL0, PSCI SYSTEM_RESET FID `0x84000009`
`smc #0`, SMC return → `wfe` forever.
stack=NO, memory reads=NO, memory writes=NO, MMIO=NO, relocations=0,
fall-through=NO, return=NO.

## RESET1 design

Same target, same placement, same entry handling, same timer algorithm,
same PSCI FID, same branch structure. Only the programmed delay is 1s.

## pair machine-code diff

```
RESET8_TOTAL ≈ Trestart + 8s + common overhead
RESET1_TOTAL ≈ Trestart + 1s + common overhead
RESET_PAIR_EXPECTED_DELTA=-7.000
```

Unknown `Trestart` cancels. Allowed pair difference: the 8s→1s timer
constant only.

```
RESET_PAIR_DIFF_ATTRIBUTED=DELAY_CONSTANT_ONLY
```

Any entry / branch / PSCI / SMC / WFE / placement difference is FAIL.

Diagnostic core is byte-identical to the T0/T1/T2/T3/T4/C_DELAY proven
core except RESET1's delay immediate.

```
RESET8_VS_FIX8_ATTRIBUTION=RESTART_CHOKE_CHECKPOINT_ONLY
RESET1_VS_FIX8_ATTRIBUTION=RESTART_CHOKE_CHECKPOINT_ONLY
```

Window-outside changed bytes: 0.

## payload identities

Filled by this round's public GHA (not guessed):

```
RESET8_PAYLOAD_SHA= (GHA)
RESET1_PAYLOAD_SHA= (GHA)
PAYLOAD_SIZE=37369041
```

## future pair equation

Primary: `RESET_PAIR_DELTA = RESET1_TOTAL - RESET8_TOTAL`.
EXPECTED `-7.000s`.
STRONG: `abs(RESET_PAIR_DELTA + 7.000) <= 1.000s`.
SUPPORTED: `<= 2.000s`.
Absolute time is secondary only. This round does not run the device.

## future positive boundary

If future pair STRONG: `MACHINE_RESTART_PATH_REACHED=PROVEN` and
`LINUX_SOFTWARE_RESET_CHOKE_EXECUTED=PROVEN` for the dominant return.
Does **not** prove who called `kernel_restart` vs `emergency_restart`,
that `/init` was reached, or that the panic-timeout branch ran.

## future negative boundary

If no ~-7s shift: `RESTART_CHOKE_DELAY_CONTROL_NOT_REFLECTED` and
`MACHINE_RESTART_COVERED_RESET_HYPOTHESIS=PRIORITY_REDUCED`. Next
fallback is watchdog / firmware handoff. Still do not write
`NO_LINUX_RESTART`.

## watchdog fallback

```
CONFIG_WATCHDOG=BUILTIN
CONFIG_QCOM_WDT=MODULE
RT-D qcom,kpss-wdt node=PRESENT
QCOM_WDT_DRIVER_WOULD_PROBE=NO
inherited watchdog handling=NONE
FIRMWARE_WATCHDOG_STATE=UNKNOWN
BOOTLOADER_WATCHDOG_HANDOFF_GAP=SOURCE_PLAUSIBLE
```

This round does not refine watchdog to MMIO.

## private-pack prohibition

```
PRIVATE_PACK_RUN=NONE
DEVICE_READY=NO
```

Public GHA never emits `*.img`, never calls mkbootimg, never splices a
boot v3. Accidental private pack is a protocol violation and does not
authorize a device.

## Final Gate

If `machine_restart` / fallback cannot be instrumented safely, or the
pair is not delay-only:

```
R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_NOT_READY
```

If source/binary audit closes and RESET8/RESET1 are delay-only:

```
MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_COMPLETE
```

This COMPLETE is **not** device ready.

Recommended next if COMPLETE:
`MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_DEVICE_GATE_FINALIZATION_CI`.

Recommended next if NOT_READY:
`MAINLINE_V2_R3_P1B_WATCHDOG_HANDOFF_PREDEVICE_READINESS_CI`.

`PANIC_TIMEOUT_BRANCH` NOT AUTHORIZED. `PANIC30` FROZEN. `FIX24` FROZEN.
`M5N` FROZEN. WAIT FOR USER APPROVAL.
