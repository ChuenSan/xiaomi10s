# Route R3 P1B alternative reset-source isolation

Round: `MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI`.
SOURCE AUDIT / STATIC RESET-PATH MAP / NEXT-DIAGNOSTIC DESIGN ONLY.
`DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`,
`LOCAL_BUILD=NO`. No private pack, no device-ready boot, no `*.img`.
Final gate cannot be `READY_FOR_*_DEVICE_CONTROL`.
DEVICE READY = NO.

Exact tree: linux-6.6.156 `8b73de7da85fde281a385e0b26eda9bffd3ca477`.
Machine-readable map: GHA artifact
`early/alternative-reset-source-map.json`
(schema `scripts/r3-p1b/alternative-reset-source-map.schema.json`).

## 1. PENTRY pair result

Frozen true-device pair (FIX8 baseline, panic-entry probe delay only):

| member | delay | TOTAL | payload SHA |
| --- | --- | --- | --- |
| PENTRY8 | 8s | 26.829s | `1988ee22806cba6129f7c3bb34def9667ec39c60f029c622f60341374cc35469` |
| PENTRY1 | 1s | 26.301s | `5fb893c6f990b23a26fe0aba7439852ff5991b59794f4ee4ab1fa7691b8328ee` |

PENTRY1 boot SHA
`370bc83f746b8e9459022effb07caf6e1a01fb17b1dd33b07c8b8f286f74f2c6`.

```
PAIR_DELTA = -0.528s
EXPECTED_DELTA = -7.000s
PAIR_ERROR = +6.472s
R3_P1B_PANIC_ENTRY_DELAY_PAIR_SHIFT_NOT_OBSERVED
```

## 2. pair evidence boundary

```
PANIC_ENTRY_DELAY_CONTROL_REFLECTED=NO
PANIC_ENTRY_REACHED=NOT_PROVEN
PANIC_ENTRY_HYPOTHESIS_PRIORITY=REDUCED
NO_LINUX_PANIC=NOT_LICENSED
```

The pair negative applies to the **current dominant ~26s return path**.
It does **not** license: panic never happens; Linux panic does not exist;
all panic callsites are unreachable.

## 3. C_DELAY lower bound

Proven: `primary_entry` → `__primary_switched` → `start_kernel` →
`setup_arch` → effective `parse_early_param` → `parse_args("Booting kernel")`
→ C6 → post-C6 kernel work → `calibrate_delay` complete.

`C_DELAY_TOTAL=14.464s`. Reset-source investigation is **after C_DELAY**
until the ~26s Android A return.

## 4. reset source taxonomy

| class | meaning |
| --- | --- |
| A | Linux explicit software restart (`kernel_restart` / `emergency_restart`) |
| B | Linux watchdog expiration (driver-visible) |
| C | bootloader / firmware / secure-world watchdog |
| D | die / oops / BUG non-canonical-panic outcomes |
| E | architecture / PSCI restart |
| F | other source-supported reset |
| Z | diagnostic PSCI (not a natural source) |

No prior that "it must be a watchdog".

## 5. kernel restart chain

`KERNEL_RESTART_CHAIN_AUDITED=YES`.

`kernel_restart(cmd)` (`kernel/reboot.c`): `kernel_restart_prepare` (reboot
notifiers, `device_shutdown`) → `do_kernel_restart_prepare` →
`migrate_to_reboot_cpu` → `syscore_shutdown` → `machine_restart(cmd)`.

Userspace `reboot(LINUX_REBOOT_CMD_RESTART)` and `orderly_reboot` fallback
enter here. `/init` is NOT_PROVEN, so userspace reboot is inference-only.

## 6. emergency restart chain

`EMERGENCY_RESTART_CHAIN_AUDITED=YES`.

`emergency_restart()`: `kmsg_dump` → `machine_emergency_restart()`.
On arm64, `machine_emergency_restart` is **not** a vmlinux symbol: it is
the asm-generic static inline `machine_restart(NULL)`
(`include/asm-generic/emergency-restart.h`, `mandatory-y`).
`__weak machine_restart` is **ABSENT** in 6.6.156 `kernel/reboot.c`.

`panic()` with `panic_timeout != 0` calls `emergency_restart()` after the
timeout wait. That path **passes canonical panic()** and is
`DEPRIORITIZED_BY_PENTRY_PAIR=YES` for the current dominant return.

## 7. common choke point analysis

`ARM64_RESTART_CHAIN_AUDITED=YES`.

```
emergency_restart → [inline machine_emergency_restart]
                 → machine_restart(NULL)
kernel_restart   → machine_restart(cmd)
machine_restart  → local_irq_disable + smp_send_stop
                 → optional efi_reboot (runtime-conditional)
                 → do_kernel_restart(cmd)
                 → halt-loop if handlers return
do_kernel_restart → atomic_notifier_call_chain(restart_handler_list)
```

```
LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT=machine_restart
handler_dispatch=do_kernel_restart
```

Coverage of `machine_restart`:

```
NORMAL_RESTART: YES
EMERGENCY_RESTART: YES
PANIC_TIMEOUT_RESTART: YES
OTHER_RESTART_HANDLER_CALLERS: psci_sys_reset (prio 129);
  msm pshold (prio 128, if probed); watchdog .restart ops (if probed)
```

`RESTART_CHOKEPOINT_INSTRUMENTABLE=YES` (GHA `34966848565`).

| symbol | VA | Image offset | section | landing | BL callers |
| --- | --- | --- | --- | --- | --- |
| `machine_restart` | `0xffff80008001849c` | `0x1849c` | `.text AX` | `paciasp` | 3 |
| `do_kernel_restart` | `0xffff8000800bd474` | `0xbd474` | `.text AX` | `paciasp` | 1 (from `machine_restart`) |
| `emergency_restart` | `0xffff8000800bd28c` | `0xbd28c` | `.text AX` | `paciasp` | 2 (incl. inside `panic`) |
| `kernel_restart` | `0xffff8000800bd534` | `0xbd534` | `.text AX` | `paciasp` | 5 |
| `psci_sys_reset` | `0xffff800080e18f90` | `0xe18f90` | `.text AX` | `bti c` | 0 (notifier, not BL) |

`FIX8_MACHINE_RESTART_PROLOGUE_MATCH=YES`. `machine_emergency_restart`
has no vmlinux symbol (inlined). This round only **designs** a future
probe. No device-ready artifact.

Future pair (DESIGN only): same choke, RESET8 vs RESET1, programmed
diagnostic delay 8s vs 1s, expected delta `-7.000s`, register-only CNTPCT,
PSCI `SYSTEM_RESET` `0x84000009`, fail-closed, reuse the device-proven
core. PAC/BTI handled per current panic/T3 discipline. No private pack.

If that future pair hits `-7s`, the dominant return goes through the Linux
software-reset choke. If it still shows no shift, Linux explicit restart
API priority drops and external watchdog / firmware reset rises. That is
the next causal fork.

## 8. PSCI restart chain

`PSCI_RESTART_CHAIN_AUDITED=YES`.
`PSCI_RESET_PATH_CLASSES_COMPLETE=YES`.

| class | what | natural ~26s? |
| --- | --- | --- |
| A | diagnostic probe direct PSCI SYSTEM_RESET | NO (pair no-shift; FIX8 is the analysis baseline) |
| B | Linux restart framework → `psci_sys_reset` | plausible if software restart |
| C | secure firmware autonomous reset | UNKNOWN, SOURCE_NOT_OBSERVABLE |

Must not merge A/B/C. `psci_sys_reset` is a restart_handler at priority
129, registered from `psci_0_2_set_functions` via `psci_dt_init` if a
`/psci` node is available (before C_DELAY).

## 9. watchdog config

`WATCHDOG_CONFIG_AUDIT_COMPLETE=YES`.

Frozen merge: arm64 `defconfig` + `configs/thyme-route-b.config` +
`configs/thyme-r3-p1b.config` + `olddefconfig`. Live classes
(BUILTIN / MODULE / ABSENT) are recorded in the JSON. Fragments do not
set watchdog symbols; defconfig currently has `CONFIG_WATCHDOG=y`,
`CONFIG_QCOM_WDT=m`, `CONFIG_PM8916_WATCHDOG=m`,
`CONFIG_ARM_SMC_WATCHDOG=y`, `CONFIG_POWER_RESET_MSM=y`. Modules cannot
load in this boot (`/init` does not insmod).

## 10. RT-D watchdog nodes

`RUNTIME_DTB_WATCHDOG_AUDIT_COMPLETE=YES`.

Frozen RT-D SHA
`4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`.
The CI enumerates `watchdog` / `wdt` / `timer-reset` / `restart` / PSCI /
power-reset nodes from **this** blob only. Stock DT presence is never
used. Missing nodes are recorded `ABSENT`.

Live (GHA `34966848565`):

| path | compatible | status |
| --- | --- | --- |
| `/psci` | `arm,psci-1.0` | okay |
| `/soc@0/watchdog@17c10000` | `qcom,apss-wdt-sm8250`, `qcom,kpss-wdt` | okay (reg/irq/clocks PRESENT) |
| `.../pmic@0/pon@800` | `qcom,pm8998-pon` | okay |
| `.../pmic@4/pon@800` | `qcom,pm8916-pon` | disabled |
| `qcom,pshold` | — | ABSENT |
| `arm,smc-wdt` | — | ABSENT |

`QCOM_WDT_RTD_NODE_PRESENT=YES` `PSCI_RTD_NODE_PRESENT=YES`
`QCOM_PSHOLD_RTD_NODE_PRESENT=NO`.

## 11. Qualcomm watchdog

In-tree `drivers/watchdog/qcom-wdt.c` is present.
Compatibles: `qcom,kpss-timer`, `qcom,scss-timer`, `qcom,kpss-wdt`.
`module_platform_driver`; probe requires a DT node.
If already running at probe: stop, reprogram default **30s** (or
`timeout-sec`), set `WDOG_HW_RUNNING` so the core pets.
If no probe: inherited state is untouched.

```
QCOM_WDT_DRIVER_PRESENT=YES
QCOM_WDT_RTD_NODE_PRESENT=YES
QCOM_WDT_DRIVER_WOULD_PROBE=NO
CONFIG_QCOM_WDT=MODULE
```

The DT node is present and `okay`, but the driver is a module and this
boot never loads modules, so probe does not run and inherited WDT is
not taken over.

The 30s figure is **not** a timeout identity for the current boot unless
probe is proven. Seeing ~26s does **not** license "30s watchdog".

## 12. PMIC/secure watchdog

`pm8916_wdt.c` exists (default 32s **if** probe). Depends on
`MFD_SPMI_PMIC` + DT. SCM/SMC watchdog controls are not a documented
Linux API in `qcom_scm.c` for this tree.

```
FIRMWARE_WATCHDOG_STATE=UNKNOWN
```

Never write DISABLED / ARMED / TIMEOUT=… without direct evidence.

## 13. inherited watchdog handoff

Mainline takeover of a bootloader-armed APSS WDT happens **only** inside
`qcom_wdt_probe`. If RT-D lacks the node, or the driver is `m` and never
loaded, Linux does not pet/disable/reprogram that WDT.

```
BOOTLOADER_WATCHDOG_HANDOFF_GAP=SOURCE_PLAUSIBLE
```

SOURCE_PLAUSIBLE only. Not PROVEN.

## 14. timeout-source discipline

Natural cluster ~26s (PENTRY8 26.829, PENTRY1 26.301) is recorded as a
cluster, not as a watchdog timeout.

```
WATCHDOG_TIMEOUT_SOURCE_DERIVABLE=NO
TIMEOUT=UNKNOWN
```

## 15. oops/die/BUG map

`OOPS_DIE_RESET_MAP_COMPLETE=YES`.

- `die`: panic if `in_interrupt` or `panic_on_oops`; else
  `make_task_dead(SIGSEGV)`. No in-tree direct restart.
- WARN/BUG: panic only via `panic_on_warn` / warn_limit.
- Paths that **must** enter canonical `panic()`:
  `DEPRIORITIZED_BY_PENTRY_PAIR=YES` for the current dominant return.
- Hang-then-firmware-reset remains possible (class C), not proven.

## 16. PID1/init failure semantics

`INIT_FAILURE_RESET_SEMANTICS_AUDITED=YES`. `requires_panic=PARTIAL`.

| event | outcome |
| --- | --- |
| `rdinit=` exec fails | `pr_err`, fall through (not panic) |
| `init=` exec fails | `panic` |
| no working init | `panic` |
| PID1 death | `panic("Attempted to kill init!")` |
| P1B `/init` sleep failure (exit 111) | PID1 death → panic |
| P1B `/init` `SYS_reboot` | `kernel_restart` (does **not** pass panic) |

`/init` reached is still NOT_PROVEN. The reboot-syscall path is covered
by the restart choke pair. Panic-required init failures are
`DEPRIORITIZED_BY_PENTRY_PAIR=YES`.

## 17. persistent evidence limitations

pstore empty and logdump/rawdump identical-to-baseline remain
**auxiliary**. They do not exclude panic, watchdog, or firmware reset.
Empty pstore is not negative hard evidence.

## 18. bootreason limitation

Historical Android A `bootreason=bootloader` is observed after automatic
return. Stock ABL/Android generation of that field is not statically
proven here.

```
ANDROID_BOOTREASON_SOURCE_DIAGNOSTIC=NO
```

Do not treat `bootreason=bootloader` as reset-source identity.

## 19. ranked candidate table

Ranking uses source evidence **and** the pair result: a panic-required
candidate cannot outrank an equal-evidence panic-bypassing candidate.
Pair negative does **not** auto-rank watchdog first.

Live table is in `early/alternative-reset-source-map.json` (GHA
`34966848565`). Top rows:

| rank | candidate | passes panic | can explain ~26s |
| --- | --- | --- | --- |
| 1 | ARS-SW-001 `machine_restart` / `do_kernel_restart` | NO | SOURCE_YES |
| 2 | ARS-SW-003 `kernel_restart` | NO | SOURCE_YES |
| 3 | ARS-SW-005 `psci_sys_reset` | NO | SOURCE_YES |
| 4 | ARS-SW-002 `emergency_restart` (non-panic callers) | NO | INFERRED |
| 8 | ARS-WD-001 qcom-wdt (DT yes, driver `m`, would-probe NO) | NO | UNKNOWN |
| 12 | ARS-EXT-001 inherited APSS WDT | NO | UNKNOWN |
| 15 | ARS-PANIC-TO panic→emergency_restart | YES | INFERRED (`DEPRIORITIZED_BY_PENTRY_PAIR`) |

Source-supported order of the dominant-path question:

1. Linux software restart through `machine_restart` / `do_kernel_restart`
   / PSCI handler (panic-bypassing, reachable after C_DELAY,
   `can_explain_23_28s=SOURCE_YES`).
2. `/init` reboot syscall (subset of 1; `/init` NOT_PROVEN; INFERRED).
3. Inherited firmware/APSS/PMIC watchdog with Linux handoff gap
   (`SOURCE_PLAUSIBLE`, timeout UNKNOWN).
4. Panic-required paths (init death, panic_timeout, oops+panic_on_oops):
   `DEPRIORITIZED_BY_PENTRY_PAIR=YES`.
5. Diagnostic PSCI: **not** a natural source.

## 20. next causal experiment decision

Case A — high-coverage Linux software-reset choke exists and source
supports it can explain the current path:

```
NEXT = MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_READINESS_CI
```

Design RESET8 / RESET1 matched-delay pair at `machine_restart`.
Do **not** pack this round.

Case B — only if that choke is `NONE` and the watchdog handoff gap is
the highest source-supported priority:

`MAINLINE_V2_R3_P1B_WATCHDOG_HANDOFF_PREDEVICE_READINESS_CI`.

Case C — otherwise:
`MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_DIAGNOSTIC_DESIGN_CI`.

No blind device. No invented MMIO. No PANIC30 rerun
(`PANIC30_RERUN=FROZEN`). Timeout-branch stays
`PANIC_TIMEOUT_BRANCH_PRIORITY=LOW_UNTIL_PANIC_ENTRY_EVIDENCE`.

WAIT FOR USER APPROVAL before any PREDEVICE packing or device run.
