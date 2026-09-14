# Route R3 Early C Kernel Execution Stage Map

Agent B parallel task: `MAINLINE_V2_R3_EARLY_C_KERNEL_STAGE_MAP_CI`.

This document is a **source-derived planning map**. It does not prove that the
device has executed any C-stage. Addresses are re-derived in GitHub Actions
from **this round's final P1B vmlinux** (`early-c-stage-map.json`). They are
never copied from historical documents as gate inputs.

Device-ready artifacts, T4/T5 authorization, private boot packaging, Slot A
writes, and `docs/route-r3-current-status.md` modifications are forbidden.

## 1. Scope

Map `start_kernel` → `/init` on exact Linux 6.6.156
(`8b73de7da85fde281a385e0b26eda9bffd3ca477`) with the P1B patchset
(0001+0002 DTS only) and the P1B kconfig/initramfs recipe.

Covered: `start_kernel`, `setup_arch`, command-line construction,
`parse_early_param`, `parse_args("Booting kernel")`, early MM / scheduler /
IRQ / timer / initcalls, `arch_call_rest_init`, `rest_init`, `kernel_init`,
initramfs / `rdinit=/init`, `run_init_process("/init")`, EL0 exec boundary.

Not covered: T3 INLINE probe, device timing, UART, observability (Agent C).

## 2. Independence from T3

`C_STAGE_MAP_DEPENDS_ON_T3_RESULT=NO`.

The map is valid whether T3 is STRONG, FAIL, NO_RETURN, or UNKNOWN. Negative
fixture `T3_RESULT_INDEPENDENCE_FIXTURE` re-runs the source audit under all
four env values and requires byte-identical facts.

Agent B does not modify T3 scripts, T3 workflow, T3 observer, T3 artifacts, or
`docs/route-r3-current-status.md`.

## 3. Frozen predecessor context (task start only)

Context at task start, **not** overwritten if Agent A later updates authority:

| item | value |
|---|---|
| T0_TOTAL | 14.252s STRONG R1 PROVEN |
| T1_TOTAL | 14.238s STRONG R2 PROVEN |
| T2_TOTAL | 14.240s STRONG |
| R0–R3 `__primary_switched` | PROVEN |
| R4 `start_kernel` address | NOT_PROVEN |
| E0 | PROVEN |
| E1 | PROVEN (T2 rule) |
| E2–E4 | NOT_PROVEN |
| E5 | FROZEN |

## 4. Exact source identity

- Linux: 6.6.156
- Commit: `8b73de7da85fde281a385e0b26eda9bffd3ca477` (CI `git rev-parse HEAD`, MATCH required)
- Patches: `patches/linux-6.6/0001-*.patch` + `0002-*.patch` (DTS only)
- Config: arm64 `defconfig` + `configs/thyme-route-b.config` + `configs/thyme-r3-p1b.config` + built-in uncompressed initramfs
- Toolchain: LLVM 18.1.3, `ARCH=arm64 LLVM=1`

Two identities are recorded:

- `UPSTREAM_SOURCE_IDENTITY` = the pinned commit
- `FINAL_P1B_VMLINUX_IDENTITY` = SHA-256 of this round's vmlinux after the P1B recipe

## 5. start_kernel entry

Source: `init/main.c` `void start_kernel(void)` with attributes
`asmlinkage __visible __init __no_sanitize_address __noreturn __no_stack_protector`.

Arrival: `arch/arm64/kernel/head.S` `__primary_switched` ends with
`bl start_kernel` (unique BL). BSS is already zeroed; `init_task` stack is
live; FDT pointer saved to `__fdt_pointer`; MMU is on (swapper).

C0 = `start_kernel` symbol VA. C1 = first non-PAC/BTI body instruction.

Insn0 is **re-derived** this round. With `CONFIG_ARM64_PTR_AUTH_KERNEL=y` and
`CONFIG_ARM64_BTI_KERNEL=y`, a non-address-taken C function commonly starts
with `paciasp` rather than `bti c`. The map records whatever this vmlinux
emits. `CONFIG_FUNCTION_TRACER`, CFI, SCS, fentry are read from `.config` and
from the first 64 instructions.

## 6. start_kernel call graph (6.6.156 order)

Must-run path (arm64, P1B config):

1. `local_irq_disable`; `early_boot_irqs_disabled=true`
2. `setup_arch(&command_line)` — **includes the real `parse_early_param()`**
3. `setup_boot_config()` (empty stub if `CONFIG_BOOT_CONFIG` is not set)
4. `setup_command_line(command_line)`
5. `parse_early_param()` again — **no-op** (`static int done`)
6. `parse_args("Booting kernel", static_command_line, __start___param, …, unknown_bootoption)`
7. `print_unknown_bootoptions`; optional init-arg `parse_args`
8. `mm_core_init` / `sched_init` / IRQ + timer bring-up
9. `early_boot_irqs_disabled=false`; `local_irq_enable`
10. `console_init`
11. `calibrate_delay` (**after** parse_args and `time_init`)
12. `arch_call_rest_init()` → `rest_init()` (arm64 does **not** override)

CONFIG-dependent / possibly skipped:

- `CONFIG_BLK_DEV_INITRD` initrd-below-start check
- `CONFIG_X86` EFI virtual mode (not arm64)
- `late_time_init` if an arch set it
- `prepare_namespace` **skipped** when `ramdisk_execute_command` exists and `eaccess` succeeds (P1B: `rdinit=/init` + built-in initramfs)

IRQ disabled until step 9. Scheduler structures exist after `sched_init` but
preemption/SMP complete later. printk has a buffer from `setup_log_buf`;
normal console after `console_init`. Allocator: memblock in `setup_arch`,
page allocator around `mm_core_init`.

## 7. setup_arch

`arch/arm64/kernel/setup.c` `setup_arch(char **cmdline_p)`:

ENTER: `*cmdline_p = boot_command_line`. DT is **not** yet unflattened.
`boot_args[]` were stored by `preserve_boot_args` in `head.S`. Early fixmap
is initialized here. Console is not up. memblock not yet finished.

Inside: `setup_machine_fdt(__fdt_pointer)` → `early_init_dt_scan` (chosen
bootargs → `boot_command_line`, memory nodes) → `jump_label_init` →
**`parse_early_param()`** → `arm64_memblock_init` → `paging_init` →
`unflatten_device_tree()` (if `acpi_disabled`) → `psci_dt_init`.

RETURN: FDT scanned, early params consumed, linear map up, OF tree unflattened
(DT path), PSCI initialized. `setup_per_cpu_areas` has **not** run yet.

C2 = BL `setup_arch` in `start_kernel`. C3 = instruction after that BL.

## 8. DT parse path

`early_init_dt_scan` (`drivers/of/fdt.c`) → `early_init_dt_scan_nodes` →
`early_init_dt_scan_chosen(boot_command_line)` copies `/chosen/bootargs`.
`unflatten_device_tree` runs later in `setup_arch`.

RT-D frozen bootargs (`rdinit=/init panic=5 loglevel=7`) are a **cross-check
only**. This map does not assume runtime parse succeeded on device.

## 9. command-line construction

Chain:

1. DT `/chosen/bootargs` → `boot_command_line` (`early_init_dt_scan_chosen`)
2. `CONFIG_CMDLINE` (arm64 Kconfig string, default `""`). If empty and DT set
   the line, DT wins. `CONFIG_CMDLINE_FORCE` not selected in P1B fragments.
   arm64 has **no** `CONFIG_CMDLINE_EXTEND` Kconfig option.
3. `CONFIG_BOOT_CONFIG` not set → no extra `kernel.` keys
4. `setup_command_line` copies into `saved_command_line` and
   `static_command_line` (the latter is parsed in place)

`FINAL_CMDLINE_STAGE_MAP=PASS` when this chain is source-proven. C4 = after
`setup_command_line`.

## 10. parse_early_param

**Source-order adjustment:** the requested list placed C5 after C4. On arm64
6.6.156 the **real** `parse_early_param()` is inside `setup_arch`, before
`setup_arch` returns and before `setup_command_line`. The `start_kernel`
call is a no-op due to `static int done`.

Consumes `early_param` / early `__setup` (including `loglevel=`). Does **not**
consume `core_param` (`panic=`) or late `__setup` (`rdinit=`).

C5 = instruction after the BL in `setup_arch`. Positive: early param
machinery reached. Does not prove `parse_args("Booting kernel")`.

## 11. parse_args("Booting kernel")

Callsite: `init/main.c` immediately after the no-op `parse_early_param()`.
Always reached on the must-run path. Walks `__start___param`…`__stop___param`
(`core_param` / `module_param`). Unknown tokens go to `unknown_bootoption` →
`obsolete_checksetup` (`__setup`, including `rdinit=` / `init=`).

C6 = instruction after the first BL `parse_args` in `start_kernel`.
Future checkpoint value = **VERY HIGH**.

## 12. panic parameter activation

`kernel/panic.c`: `core_param(panic, panic_timeout, int, 0644);`
Not `early_param`. Activation point = C6.

If a **future** C6 probe on a given artifact is PROVEN, then
`PANIC_PARAMETER_PARSE_STAGE_REACHED=PROVEN` for **that** artifact.
A C6 proof on panic=5 does **not** imply the historical PANIC30 payload
reached C6.

## 13. calibrate_delay

Callsite in `start_kernel` **after** `parse_args`, `time_init`,
`local_irq_enable`, and `console_init`. `POST_PARSE_ARGS=YES`.
C_DELAY = instruction after BL `calibrate_delay`. After this,
`mdelay` / `loops_per_jiffy` wall-clock is much more credible.

## 14. scheduler / IRQ / timer

| event | where |
|---|---|
| `local_irq_disable` + `early_boot_irqs_disabled` | start of `start_kernel` |
| `sched_init` | after `parse_args`, IRQs still off |
| `tick_init` / `timekeeping_init` / `time_init` | still IRQs off |
| `local_irq_enable` | after timer init |
| `calibrate_delay` | IRQs on |
| `rest_init` sets `SYSTEM_SCHEDULING` | later |

C7 marks the post-command-line core-init window (`sched_init` … IRQ enable).
Prefer CNTPCT + PSCI primitives; do not assume subsystem safety before the
matching stage.

## 15. console / printk

Early `pr_notice(linux_banner)` uses the printk buffer. `console_init` is
after IRQ enable and before `calibrate_delay`. Normal kernel printk becomes
more observable after C7/`console_init`. This task does not enable UART or
change cmdline.

## 16. arch_call_rest_init

Default in `init/main.c`: weak `__noreturn` function that calls `rest_init()`.
arm64 does not override. C8 = BL from `start_kernel`. High checkpoint value:
almost all of `start_kernel` has run. Does not prove userspace.

## 17. rest_init

Creates pid 1 via `user_mode_thread(kernel_init, …)` then `kthreadd`, sets
`SYSTEM_SCHEDULING`, `schedule_preempt_disabled`, `cpu_startup_entry`.
C9 = `rest_init` ENTER. This is **not** userspace init.

## 18. kernel_init

C10 = `kernel_init` ENTER (pid 1). Then `kernel_init_freeable()`:
SMP, `do_basic_setup()` (initcalls, including `populate_rootfs`),
`wait_for_initramfs()`, `console_on_rootfs()`. After return:
`async_synchronize_full`, `free_initmem`, `mark_readonly`,
`system_state = SYSTEM_RUNNING`, then exec.

## 19. initramfs / rootfs

`populate_rootfs` is `rootfs_initcall`, schedules `do_populate_rootfs` which
`unpack_to_rootfs(__initramfs_start, __initramfs_size)` (built-in), then
optionally an external initrd. `wait_for_initramfs()` in
`kernel_init_freeable` joins that async work.

P1B: built-in initramfs **plus** `rdinit=/init`. If `/init` exists after
unpack, `prepare_namespace()` is **skipped**. C11 = that wait / root
preparation window.

## 20. rdinit=/init

`ramdisk_execute_command` defaults to `"/init"`. `rdinit=` is `__setup`
(`rdinit_setup`), consumed at C6 via `unknown_bootoption`, not as
`early_param` or `core_param`.

`kernel_init` then `run_init_process(ramdisk_execute_command)` which
`kernel_execve`s the path. C12 = that callsite.

C12 proves the kernel is about to exec `/init`. It does **not** prove EL0
retired the first `/init` instruction.

## 21. exec / userspace transition

`run_init_process` → `kernel_execve` (`fs/exec.c`) → `bprm_execve` →
`load_elf_binary` (`fs/binfmt_elf.c`) → `START_THREAD(…, elf_entry, …)`
→ ERET to EL0 at the ELF `e_entry` of `/init`.

`/init` `e_entry` lives in the initramfs ELF, **not** in vmlinux. C13 uses
`kernel_execve` as the kernel-side boundary. A future proof of `/init`
executed needs an EL0-side or post-ERET observation. This round generates
**no probe**.

## 22. checkpoint candidate matrix

Ranking is static (information gain + implementation risk). **Not** ordered
by T3 result.

| rank | stage | info | impl risk | contamination | matched timing | why |
|---|---|---|---|---|---|---|
| 1 | C0 `start_kernel` ADDRESS | HIGH | LOW | LOW | YES | unique BL; first C-stage |
| 2 | C6 `parse_args` COMPLETE | HIGH | MEDIUM | MEDIUM | YES | only proof that `panic=` was consumed |
| 3 | C3 `setup_arch` RETURN | HIGH | MEDIUM | MEDIUM | YES | implies C5; FDT+early_param+paging |
| 4 | C_DELAY `calibrate_delay` | HIGH | HIGH | HIGH | YES | panic timeout / mdelay map |
| 5 | C12 `run_init_process("/init")` | HIGH | HIGH | HIGH | YES | kernel-side /init exec; not EL0 |

C1 is a small increment over C0. C5 is implied by C3. C8/C9 are high value
but later than C6 for the panic question. C13 is not a kernel-text INLINE
candidate.

Candidate comparison (A–F from the task):

- A C0: failure after this is **inside** `start_kernel` or later
- B C3: failure after this is post-`setup_arch` (not FDT scan / early_param)
- C C6: failure after this cannot be "panic= never parsed" for **this** artifact
- D C_DELAY: failure after this is post-timer calibration
- E C9: failure after this is in pid1 / initcalls / exec
- F C12: failure after this is exec/EL0, not kernel prep

## 23. evidence semantics

A positive C-stage proves reachability of **that** callsite/symbol on **that**
artifact. It does not prove later stages, does not upgrade E2–E4, and does
not rewrite historical PANIC30 / T0 / T1 / T2 results.

Negatives cannot exclude a hang on the next instruction.

## 24. future probe safety

Allowed later (mainline Agent A decision only): INLINE CNTPCT+PSCI at a
chosen C-stage, fail-closed, no device-ready mark from this task.

This round: **no** probe binary, **no** boot.img, **no**
`READY_FOR_*_DEVICE_CONTROL`, **no** private OEM packaging.

`CNTPCT_DIRECT_PROBE_SAFE` / `PSCI_SYSTEM_RESET_DIRECT_SAFE` are
`SOURCE_YES_DEVICE_NOT_PROVEN_HERE` at C0+: source says EL1 MMU-on continues
from `__primary_switched`; device proof remains T2-local.

## 25. machine-readable map

CI artifact `early-c-stage-map.json` (public, source-derived symbols/addresses
only; no OEM private binary).

Required fields per stage include `id`, `name`, `symbol`, `link_va`,
`image_offset`, `file_offset`, `section`, `source`, `line`, `cmdline_state`,
`panic_parsed`, `checkpoint_value`, `device_ready=false`.

Addresses are filled only after this round's vmlinux build. Until then treat
VAs in discussion as `CI_DERIVED`.

## 26. conclusion

If CI prints `MAINLINE_V2_R3_EARLY_C_STAGE_MAP_COMPLETE`, the source chain
`start_kernel` → `/init` is mapped, `parse_args` / `panic=` / `calibrate_delay`
ordering is source-proven, negative fixtures and T3-independence pass, and
Agent A files are untouched.

This result may be consumed after T3 regardless of T3 STRONG / FAIL /
NO_RETURN. It must **not** independently authorize T4/T5 device execution.

WAIT FOR USER / MAINLINE AGENT DECISION.
