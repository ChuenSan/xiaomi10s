# MAINLINE_V2_R3_P1B_T3_PREDEVICE_READINESS_CI — start_kernel ADDRESS
# reachability candidate (CI / source audit / artifact preparation only)

Round: CI ONLY. `DEVICE_OPERATION=NO`, `ADB_DEVICE_OPERATION=NO`,
`FASTBOOT_DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`.
`LOCAL_BUILD=NO`: every kernel build, assembly, link, objdump, readelf, ELF
inspection, payload generation, boot pack and binary validation runs in
GitHub Actions; locally only source reading, text editing and syntax checks
were performed. mem0 was read at the start of the round.

Status: `T3_STATUS=PREDEVICE_READY`, `T3_PREDEVICE_STATUS=READY`.
Final gate: **`READY_FOR_R3_P1B_T3_DEVICE_CONTROL=YES`**.
The alternative token `R3_P1B_T3_PREDEVICE_NOT_READY` is retained as the
fail-closed opposite and is not the current outcome. A T3 true-device run is
**NOT authorized** by this document.

---

## 1. T0 / T1 / T2 proof (frozen predecessors)

| round | total | verdict | proof |
| --- | --- | --- | --- |
| T0 | `T0_TOTAL_S=14.252` | STRONG | `T0_STATUS=TRUE_DEVICE_PROVEN`; R1 |
| T1 | `T1_TOTAL_S=14.238` | STRONG | `T1_STATUS=TRUE_DEVICE_PROVEN`; R2; `T1_MINUS_T0_S=-0.014` |
| T2 | `T2_TOTAL_S=14.240` | STRONG | `T2_STATUS=TRUE_DEVICE_PROVEN`; R3; `T2_MINUS_T1_S=0.002` |

`T2_MINUS_T0_S=-0.012`. Final T2 gate:
`MAINLINE_V2_R3_P1B_T2_REACHABILITY_PROVEN`; `R3_STATUS=PROVEN`,
`E1_STATUS=PROVEN`, `E2_STATUS=NOT_PROVEN`. All three rounds are frozen and
are never re-run by this round (`T2 rerun`, `T1 rerun`, `T0 rerun`, `PANIC30
rerun`, `FIX8 rerun`, `FIX24`, `M5N`, `copydown`, `USB`, `UFS`, `network` are
all forbidden here).

## 2. Why T3

T2 proved that the normal `primary_entry` path reaches
`__primary_switched` with the MMU already on. T2's checkpoint intercepted
**at the `__primary_switched` entry**, so nothing about the normal
continuation was proven. T3 moves the single checkpoint from
`__primary_switched` to the **`start_kernel` function entry**, which is the
last address the arm64 assembly path hands control to C at. The question T3
answers is exactly one:

> If the completely normal, unmodified `__primary_switched` body and the
> normal `__primary_switched` → `start_kernel` sequence are restored, does
> the CPU actually arrive at the `start_kernel` function entry address?

`T3 = START_KERNEL_ADDRESS_REACHABILITY`, not
`START_KERNEL_NORMAL_EXECUTION`. The candidate is a destructive diagnostic:
`T3_DIAGNOSTIC_ONLY=YES`, `T3_NORMAL_KERNEL_BOOT_CANDIDATE=NO` — it can
never continue a normal boot by construction.

## 3. Proof boundary

Reachability ladder used by this round (finer than the older evidence
ladder):

| rung | statement | status |
| --- | --- | --- |
| R0 | ABL controlled payload entry | PROVEN |
| R1 | P1B large-payload trampoline checkpoint | PROVEN |
| R2 | `primary_entry` ADDRESS | PROVEN |
| R3 | `__primary_switched` ADDRESS | PROVEN |
| R4 | `start_kernel` ADDRESS | `NOT_PROVEN` (T3 target) |
| R5 | normal `start_kernel` body / early C init | NOT_PROVEN |
| R6 | built-in initramfs | NOT_PROVEN |
| R7 | `/init` | NOT_PROVEN |

A future T3 STRONG hit may record `START_KERNEL_ADDRESS_REACHED=PROVEN` and
`R4=PROVEN`, plus
`NORMAL_PRIMARY_SWITCHED_TO_START_KERNEL_PATH_EXECUTED=PROVEN` (justified by
`T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES` and by the ordered
control-flow audit of §4). It may **never** claim `R5`, the `start_kernel`
body, `setup_arch`, `parse_args`, the scheduler, initramfs or `/init`. `E2` is
never auto-upgraded: it is re-evaluated only against its frozen definition in
`docs/route-r3-current-status.md`, and if that definition is not satisfied
the correct record is `R4 PROVEN`, `E2 NOT_PROVEN`.

## 4. `__primary_switched` normal path — the only code between T2 and T3

Because the T3 checkpoint is the **first instruction of `start_kernel`**, the
entire range between the T2 checkpoint and the T3 checkpoint is the
`__primary_switched` body (`arch/arm64/kernel/head.S` 473-524), which this
round audits step by step. `T3_PRE_START_KERNEL_CONTROL_FLOW_AUDITED=YES`:

1. `adr_l x4, init_task`; `init_cpu_task x4, x5, x6` — `msr sp_el0`, SP =
   `init_task.stack + THREAD_SIZE - PT_REGS_SIZE`, final frame record,
   `scs_load_current` (empty here), per-CPU offset.
2. `adr_l x8, vectors` / `msr vbar_el1, x8` / `isb` — VBAR_EL1 is **set**
   before `start_kernel`, so a fault at the checkpoint would vector through
   the real kernel vector table.
3. `stp x29, x30, [sp, #-16]!` / `mov x29, sp` — a frame is pushed and later
   popped again at step 11.
4. `str_l x21, __fdt_pointer`; `ldr_l x4, kimage_vaddr`; `sub x4, x4, x0`;
   `str_l x4, kimage_voffset` — the FDT physical pointer and the kernel
   virtual/physical offset are recorded (KASLR-safe).
5. `mov x0, x20`; `bl set_cpu_boot_mode_flag` — boot mode flag.
6. `adr_l x0, __bss_start`; `mov x1, xzr`; `adr_l x2, __bss_stop`;
   `sub x2, x2, x0`; `bl __pi_memset`; `dsb ishst` — **BSS is cleared**.
7. `mov x0, x21`; `bl early_fdt_map` — early FDT mapping.
8. `mov x0, x20`; `bl init_feature_override` — idreg-based feature
   overrides.
9. `bl finalise_el2` — at EL1 with `BOOT_CPU_MODE_EL2` false this is an early
   `ret` (`arch/arm64/kernel/hyp-stub.S:244-258`), so no EL2 state is touched.
10. `ldp x29, x30, [sp], #16` — the frame is popped.
11. `bl start_kernel` — the only entry into C; `ASM_BUG()` follows, which is
    why `T3_ENTRY_RETURN_ASSUMED=NEVER`.

The source order of all 26 steps is asserted in CI against
`arch/arm64/kernel/head.S` (`gate_pre_path_order`), so the audit cannot drift
from the pinned source. `T3_ENTRY_MMU=ON` and
`T3_ENTRY_PC_ADDRESS_SPACE=VA` are carried from T2; `T3_ENTRY_SP_VALID=YES`;
`T3_ENTRY_DAIF` is `D=0,A=1,I=1,F=1`; `T3_ENTRY_BSS=CLEARED`;
`T3_ENTRY_X0_MEANING` is `cpu_boot_mode` (i.e. **not** the DTB pointer — T3
does not consume it).

## 5. `__primary_switched` → `start_kernel` call site

`T3_START_KERNEL_CALLSITE_FOUND=YES`. The CI disassembles the rebuilt
vmlinux from the re-derived `__primary_switched` VA to the next symbol and
requires **exactly one** instruction in that window whose target is the
re-derived `start_kernel` VA, that its mnemonic is `bl`, and that the frozen
payload's word at the same Image offset agrees with the rebuilt Image:

- `START_KERNEL_CALLSITE_VA` / `START_KERNEL_CALLSITE_IMAGE_OFFSET` /
  `START_KERNEL_CALLSITE_BYTES` are emitted as real values.
- `T3_START_KERNEL_CALL_TARGET_EXACT=YES` — the decoded target is exactly
  `start_kernel`. There is no PLT, no veneer, no BTI thunk, no CFI trampoline
  and no indirect branch on this path; a `b`/`br`/indirect arrival is
  rejected outright because it would change the entry register contract.
- `gate_checkpoint_after_callsite` enforces that the checkpoint address is
  strictly after the call site: a checkpoint placed *before* the call would
  not prove `START_KERNEL_REACHED` and is rejected.

## 6. `start_kernel` symbol re-derivation (never a history value)

`T3_START_KERNEL_REDERIVED=YES`. `T3_TARGET_SYMBOL=start_kernel` is
re-derived from **this round's** `llvm-nm` over the freshly rebuilt
`vmlinux` plus `System.map` (two independent sources must agree), and
`START_KERNEL_IMAGE_OFFSET` is computed as `start_kernel - _text`. No
historical address from T0/T1/T2 (`T2_CHECKPOINT_OFFSET_HISTORY`, kept in the
manifest only as a cross-check) is ever used as a gate input.

Values emitted by the build job (authoritative for the frozen candidate):

| field | value |
| --- | --- |
| `start_kernel` VA | `START_KERNEL_VA` |
| Image offset | `START_KERNEL_IMAGE_OFFSET` |
| file offset | `START_KERNEL_FILE_OFFSET` |
| section | `START_KERNEL_SECTION` |
| section flags | `START_KERNEL_SECTION_FLAGS` |
| current symbol extent | `START_KERNEL_SIZE_IF_KNOWN` |
| callsite | `START_KERNEL_CALLSITE_VA` |

The concrete numbers of the frozen candidate are recorded in the round
results block at the end of this document and in
`artifacts/…/p1b-t3-manifest.json`.

## 7. C entry state at the checkpoint

`T3_ENTRY_CURRENT_EL=EL1`, `T3_ENTRY_MMU=ON`, `T3_ENTRY_SCTLR_EL1_M=1`,
`T3_ENTRY_VBAR_EL1=SET_TO_vectors_WITH_ISB`, `T3_ENTRY_X30_MEANING=return
address into __primary_switched`, `T3_ENTRY_CALLED_FROM=__primary_switched
(bl start_kernel)`. `x1/x2/x3` are scratch by this point (the BSS-clear
sequence consumed them) and are recorded as `NOT boot contract`; `x19..x25`
still hold the head.S boot contract and the probe writes **none** of them
(`T3_ENTRY_X19_X25`). The full contract plus a per-field source citation is
emitted as `T3_ENTRY_*` keys and `*_SOURCE=` lines.

## 8. Compiler instrumentation audit (C function entry)

`T3_START_KERNEL_ENTRY_INSTRUMENTATION_AUDITED=YES`. `start_kernel` is a C
function (`asmlinkage __visible __init __no_sanitize_address __noreturn
__no_stack_protector`, `init/main.c:847-848`), so its entry is *not*
automatically as simple as an assembly symbol. The round therefore reads the
**actual build `.config`** and prints, for each symbol, the value used:

`CONFIG_ARM64_BTI_KERNEL`, `CONFIG_ARM64_PTR_AUTH_KERNEL`,
`CONFIG_CFI_CLANG`, `CONFIG_SHADOW_CALL_STACK`, `CONFIG_FUNCTION_TRACER`,
`CONFIG_DYNAMIC_FTRACE`, `CONFIG_DYNAMIC_FTRACE_WITH_CALL_OPS`,
`CONFIG_DYNAMIC_FTRACE_WITH_ARGS`, `CONFIG_KASAN`, `CONFIG_KCOV`,
`CONFIG_STACKPROTECTOR`, `CONFIG_STACKPROTECTOR_STRONG`,
`CONFIG_FUNCTION_ALIGNMENT`, `CONFIG_UNWIND_PATCH_PAC_INTO_SCS`,
`CONFIG_JUMP_LABEL`, `CONFIG_RELOCATABLE`, `CONFIG_RANDOMIZE_BASE`,
`CONFIG_HAVE_ARCH_JUMP_LABEL_RELATIVE`.

`T3_ENTRY_INSTRUMENTATION_BTI=ENABLED` at the compiler-flag level
(`CONFIG_ARM64_BTI_KERNEL` selects `-mbranch-protection=pac-ret+bti`,
`arch/arm64/Makefile:66-67`), but the **measured** entry of `start_kernel`
carries no BTI landing pad: `T3_START_KERNEL_ENTRY_INSTRUCTION0=paciasp`
(`0xd503233f`), the PAC-return prologue. This is expected and auditable:
LLVM omits the BTI landing pad for a function whose address is never taken,
and `start_kernel` is reached only by the direct `bl start_kernel` inside
`__primary_switched` (a direct branch is never BTI-checked), which the
callsite gate of §5 proves. Therefore `T3_BTI_LANDING_REQUIRED=NO`,
`T3_START_KERNEL_ENTRY_PROLOGUE_CLASS=PAC_RET_PROLOGUE_NO_BTI_LANDING_PAD`,
and `T3_ENTRY_PAD_PRESERVED=YES`: the probe re-emits the original entry
instruction verbatim, so the instruction at the checkpoint address is
bit-for-bit the original one. `T3_ENTRY_INSTRUMENTATION_CFI=DISABLED`,
`_FTRACE=DISABLED`, `_SHADOW_CALL_STACK=DISABLED`, `_KASAN=DISABLED`,
`_KCOV=DISABLED`, `_STACK_PROTECTOR=NOT_AT_ENTRY`
(`__no_stack_protector`, and no `-fpatchable-function-entry` is emitted while
`CONFIG_FUNCTION_TRACER=n`, so there is no fentry NOP either). Any
configuration that would put `__fentry__`/`mcount`/CFI/SCS/KASAN/KCOV bytes
at the entry is a hard failure of `gate_instrumentation_audit`, and so is any
entry word that is neither `bti c` nor `paciasp`, or any disagreement between
the disassembled entry and the frozen entry word.

## 9. Entry pad: PAC / BTI / CFI audit

- Measured entry: `T3_START_KERNEL_ENTRY_INSTRUCTION0=paciasp`,
  `T3_START_KERNEL_ORIGINAL_BYTES0=3f2303d5`. The T3 probe re-emits exactly
  this word as its first instruction (`T3_ENTRY_PAD_PRESERVED=YES`), so the
  instruction at the `start_kernel` entry address is unchanged; the 76-byte
  diagnostic core then occupies the remaining 19 instruction slots.
- `T3_BTI_LANDING_REQUIRED=NO`: the arrival is the single direct
  `bl start_kernel` (BTI is not checked on direct branches) and the compiler
  itself omitted the landing pad because the function address is not taken.
  A wrongly assumed `bti c` pad was in fact **rejected by the first CI run**
  of this round (`T3_ENTRY_INSTRUMENTATION_FAILED: frozen first word
  0xd503233f is not bti c`) — the gate did its job, and the pad is now
  derived from the authoritative binary instead of assumed. The negative
  fixtures keep rejecting an entry word that is neither `bti c` nor
  `paciasp`, a pad that disagrees with the frozen original, and a pad that
  disagrees with the disassembly.
- PAC: `paciasp` signs x30 with SP as an architectural register and performs
  no memory access, so it is consistent with `T3_STACK_USAGE=NO` (no loads,
  no stores). `__no_stack_protector` means no canary load at the entry.
  Diagnostic-boundary closed loop:
  `T3_PACIASP_INTENTIONALLY_REPLACED=YES` (the 80-byte window occupies the
  original `start_kernel` entry including the `paciasp` slot; the original
  C prologue after word0 is overwritten),
  `T3_DIAGNOSTIC_REQUIRES_PACIASP=NO` (the probe never returns, never
  executes `autiasp`, never consumes a signed LR, and WFE-forevers after
  SMC), `T3_NORMAL_START_KERNEL_PROLOGUE_EXECUTED=NOT_PROVEN`.
- Landing from the exact callsite: `__primary_switched` at
  `0xffff800081b395ec` is `bl start_kernel` (`START_KERNEL_CALLSITE_BYTES=75dbff97`),
  `T3_ENTRY_LANDING_REQUIREMENT=DIRECT_BL_NO_BTI_CHECK`. Direct `BL` is not
  BTI-checked. Probe word0 remains `paciasp`, which would also be a legal
  BTI-c landing if the path were indirect; that requirement does not apply.
  `T3_PROBE_LANDING_REQUIREMENT_SATISFIED=YES`.
  `start_kernel` Image offset `0x1b303c0` being less than
  `__primary_switched` `0x1b39534` is symbol layout, not control-flow order.
- CFI: `CONFIG_CFI_CLANG` is unset, so there is no `__cfi_start_kernel`
  prefix landing pad and no kCFI hash check on a direct `bl`.
- `.kcfi_traps` is still scanned as a future guard
  (`T3_KCFI_TRAPS_SCAN=PASS`).
- `T3_DIAGNOSTIC_CORE_SLICE_MATCHES_T2=YES` /
  `T3_DIAGNOSTIC_CORE_MATCHES_T2=YES`: the 76-byte core is byte-identical to
  the T2 probe core; word0 differs because T2 preserved `bti c` and T3
  preserved `paciasp`.

## 10. Inline / external decision

`T3_PROBE_ARCHITECTURE=INLINE` and `T3_EXTERNAL_CHECKPOINT_USED=NO`.

Reasoning, in this order:

1. `start_kernel` lives in kernel text (`START_KERNEL_SECTION`, expect
   `.init.text` with flags `AX`), which the CPU is *already executing* when
   it arrives: the arrival **is** the executable-mapping proof. No padding
   region and no code cave needs to be argued for.
2. T1 could execute its checkpoint from the deterministic zero padding
   because at that point the MMU was still off. T2 and T3 run with the MMU
   on, where that padding is **not** mapped: reusing it would be an unproven
   execution claim. `T3_WINDOW_INSIDE_IMAGE_SIZE=YES` makes the refusal
   explicit — the window must lie inside the kernel runtime footprint, never
   after `image_size`.
3. An EXTERNAL design at `start_kernel` would need a second, independently
   proven MMU-on executable region plus a branch from the function entry,
   i.e. **two** new claims instead of one. It is therefore only considered if
   the INLINE overwrite-safety scan fails; it is not the default and is not
   used here.

## 11. Executable mapping proof

`T3_INLINE_MAPPING_EXECUTABLE=YES`,
`T3_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT`. The checkpoint address is a
`SHF_ALLOC|SHF_EXECINSTR` section member reached by a direct `bl` from
`__primary_switched`, which itself is reached only after `__enable_mmu`
installed `SCTLR_EL1.M=1` and `load_ttbr1` installed `init_pg_dir`. The
mapping claim is therefore exactly "the kernel text VA the CPU is executing",
and nothing more: the normal memory subsystem is not claimed and the claim
does not extend to any other address.

## 12. Overwrite safety

`T3_INLINE_OVERWRITE_SAFE=YES`. Before the patch is composed, CI runs:

- `T3_SYMBOL_SCAN=PASS` — no symbol entry strictly inside the window.
- `T3_BRANCH_SCAN=PASS` — no branch anywhere in the executable Image ranges
  targets the window (raw branch words are decoded and each candidate is
  confirmed against the authoritative disassembly before it counts).
- `T3_RELOCATION_SCAN=PASS` — no `.rela.dyn`/RELR runtime relocation location
  falls inside the window. This matters because `__relocate_kernel` runs in
  `__primary_switch` **before** `__primary_switched` and would otherwise
  rewrite the probe bytes.
- `T3_LITERAL_SCAN=PASS` — no 8-byte aligned absolute literal anywhere in the
  Image points strictly inside the window (which would be an indirect entry
  into the middle of the overwritten range).
- `T3_CONTROL_FLOW_SCAN=PASS` and `T3_SECTION_BOUNDARY_SCAN=PASS` — the
  window lies inside one `SHF_EXECINSTR|SHF_ALLOC` section and does not cross
  its end.
- `T3_FUNCTION_EXTENT_SCAN=PASS` — the window ends before the next symbol, so
  the overwrite stays inside the `start_kernel` body.
- `T3_EXCEPTION_TABLE_SCAN=PASS`, `T3_ALTINSTRUCTIONS_SCAN=PASS`,
  `T3_JUMP_TABLE_SCAN=PASS`, `T3_STATIC_CALL_SITES_SCAN=PASS`,
  `T3_KCFI_TRAPS_SCAN=PASS` — the exception table, the alternatives table,
  the jump-label table, the static-call site table and the kCFI trap table
  are dumped from the ELF and decoded with their exact in-tree record layouts
  (`struct exception_table_entry` with `ARCH_HAS_RELATIVE_EXTABLE`,
  `struct alt_instr` via `ALT_ORIG_PTR`, `struct jump_entry` via
  `jump_entry_code`, static-call sites, kCFI traps); an entry whose
  instruction address lands inside the window is rejected. Every
  interpretation is derived from the pinned source, never guessed.

`T3_ALT_EX_TABLE_HAZARD=NO_POST_START_KERNEL_ONLY`: in addition to the scan,
no rewriter can run before the checkpoint —
`T3_PRE_CHECKPOINT_RUNTIME_REWRITE=NONE` records that
`apply_boot_alternatives()` is reached from `smp_prepare_boot_cpu()`
(`arch/arm64/kernel/smp.c`) which `start_kernel` calls from
`init/main.c:876`, and `jump_label_init()` runs at `init/main.c:881`; both
are strictly after `start_kernel` instruction 0, and the CI asserts that
`jump_label_init` is textually after the `start_kernel` definition.

## 13. Timer safety

`T3_CNTPCT_ACCESS_SAFE=YES`. The probe reads only `CNTFRQ_EL0` and
`CNTPCT_EL0`, which are EL1-legal irrespective of `SCTLR_EL1.M`, TTBR state
or MMU state. The audit additionally greps the entire pre-checkpoint path
(`arch/arm64/kernel/head.S`, `arch/arm64/kernel/hyp-stub.S`,
`arch/arm64/kernel/idreg-override.c`) for any write to a counter-trap
control (`CNTKCTL_EL1`, `CNTHCTL_EL2`, `CNTVOFF_EL2`) and fails if one
appears: on this EL1 boot path the only `CNTKCTL_EL1` writer is
`arch_timer_set_cntkctl` (arch timer / context switch) and `CNTHCTL_EL2` is
written only in EL2 init or KVM, none of which run before the checkpoint.
The identical EL1 access was proven on this device at T0, T1 and T2.

## 14. PSCI safety

`T3_PSCI_SYSTEM_RESET_SAFE=YES`. The probe issues PSCI `SYSTEM_RESET`
(`0x84000009`) via `smc #0`. The FID carries no pointer argument, so no
VA→PA translation is involved; `smc` is synchronous to EL3 regardless of
`SCTLR_EL1.M`, TTBR state or the newly installed `VBAR_EL1`. The frozen RT-D
keeps `/psci method="smc"`, and the identical EL1 `smc` was proven on this
device at T0, T1 and T2.

## 15. Fail-closed behaviour

`T3_FAIL_CLOSED=YES`. The diagnostic core is: reach →
`msr daifset, #0xf`/`isb` → 8 s `CNTPCT` register-only delay → PSCI
`SYSTEM_RESET` via `smc #0` → on **any** unexpected `smc` return, `wfe` and
branch back to that `wfe` forever. There is no path that restores the
original instructions, no return, and no fall-through into the
`start_kernel` body. CI decodes the raw words to prove the terminal shape
(`smc` at instruction index 17, `wfe` at 18, `b` back to 18 at 19) and every
branch in the probe is proven to stay inside the probe.

## 16. No-stack / no-memory policy

`T3_STACK_USAGE=NO`, `T3_NO_MEMORY_READS=YES`, `T3_NO_MEMORY_WRITES=YES`,
`T3_POSITION_INDEPENDENT=YES`, `T3_RUNTIME_RELOCATIONS=0`. The probe uses
only instruction fetch, architectural system registers, immediates and
`smc`. The disassembly gates reject any store/`adrp`, any load, any `bl`/
`blr`/`ret`, any `msr daifclr`, any SP use and any write to `x1/x2/x3` or
`x19..x30`; `x0`/`w0` may only be written as the PSCI FID. The probe
therefore cannot depend on a valid stack or on any normal C runtime state,
even though at this point SP *is* valid.

## 17. T2 probe removal

`T2_PROBE_REMOVED_FROM_T3=YES`, `PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES`.
The T3 payload is composed by patching the **frozen FIX8 payload**, not the
T2 payload, and the build additionally proves that the
`__primary_switched` window no longer contains the T2 probe while being
byte-identical to FIX8. The independent verify job re-checks the same
property from the uploaded artifact. A payload that still carries the T2
probe is rejected (`T2_PROBE_STILL_PRESENT`).

## 18. Pre-T3 path identity

`T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES`. Every byte before the
`start_kernel` window and every byte after it is byte-identical to the frozen
FIX8 payload (`gate_tail_identity`, a hard gate, not a report): the frozen
trampoline, `primary_entry`, the whole `record_mmu_state`/`create_idmap`/
`init_kernel_el`/`__cpu_setup`/`__enable_mmu`/`__primary_switch` path and
the complete `__primary_switched` body. This is the hard gate that lets a
future positive be upgraded to
`NORMAL_PRIMARY_SWITCHED_TO_START_KERNEL_PATH_EXECUTED=PROVEN`.

## 19. Payload diff

`T3_PAYLOAD_DIFF_ATTRIBUTED=START_KERNEL_CHECKPOINT_ONLY`. The diff versus
the frozen FIX8 payload is one contiguous region:
`T3_DIFF_RANGES=[START_KERNEL_IMAGE_OFFSET, +80)`,
`T3_DIFF_BYTE_COUNT` (76 expected: the window is 80 bytes and its first word
— the preserved original entry instruction `paciasp` — is unchanged), `T3_PAYLOAD_SIZE_IDENTICAL=YES` (37369041) and
`T3_BOOT_SIZE_IDENTICAL=YES` (37380096). `T3_RUNTIME_SEMANTIC_DELTA=START_KERNEL_ADDRESS_CHECKPOINT_ONLY`.

## 20. RT-D / init / initramfs identity

`T3_RT_D_IDENTITY=YES` — the RT-D trailer is byte-identical to the frozen
`4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327` (144593
bytes, `panic=5`, `rdinit=/init`; the PANIC30 trailer is never used).
`T3_INIT_IDENTITY=YES` (`/init`) and `T3_INITRAMFS_IDENTITY=YES` (the
deterministic uncompressed cpio) are re-derived by rebuilding both in CI and
comparing against the frozen hashes; `T3_TRAMPOLINE_IDENTICAL=YES` — the
embedded trampoline is byte-identical to FIX8.

## 21. Geometry

Re-read from the final binary header, never inherited:
`IMAGE_FILE_SIZE`, `IMAGE_HEADER_IMAGE_SIZE` (expected `0x2230000`),
`DTB_OFFSET` (`0x2380000`), payload size (37369041), boot size (37380096),
with `T3_DTB_OFFSET=0x2380000`, `T3_GEOMETRY_GATES=PASS`, and the boot
capacity margin checked (`>16 MiB`). Historical conflicting readings are
ignored and recorded as ignored.

## 22. Private packaging

The private repository packs the frozen public payload into the exact FIX8
known-good OEM boot v3 envelope, replacing only the kernel payload
(`T3_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY`), and re-verifies
the M5D envelope SHA, the payload SHA, the checkpoint SHA, the non-presence
of the probe at `__primary_switched`, the presence of `bti c` at
`start_kernel`, the RT-D trailer and the boot size. The private workflow
(`artifacts/p1b-t3-private-workflow-staging.yml`) never touches a device:
`DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`,
`READY_FOR_DEVICE=NO`. The boot artifact is **private only** and is never
emitted from the public repository.

## 23. Observer

`scripts/r3-p1b/observe-r3-p1b-t3.py` is derived from the T2 observer and
keeps `FASTBOOT_BOOT_ONLY` and `SECOND_BOOT_FORBIDDEN=YES`. Its identity gate
is a **FULL-SHA** gate: it requires `R3_T3_SHA256` and
`R3_T3_PAYLOAD_SHA256` to be full digests and refuses, before any fastboot
interaction, every other frozen boot — T2, T1, T0, FIX8, PANIC30, the old
INIT8 image and the entry-state probe — with
`T3_OBSERVER_MISBOOT_REFUSED`. The refusal list is also extendable through
`R3_T3_FORBIDDEN_SHAS`. The fixture suite
(`scripts/r3-p1b/observer-t3-fixtures.py`) exercises the real observer
functions, including the AST self-deadlock gate
(`OBSERVER_T3_AST_DEADLOCK_GATE=PASS`), one misboot case per frozen boot
(including `OBSERVER_T3_IDENTITY_T2_BOOT_MISBOOT_REFUSED=PASS`), the
exact-match acceptance, the decoder cases A-F and the summary fixture. No
device run happens this round.

## 24. T2 matched-control reference

The primary matched control for T3 is **T2**, `T2_REFERENCE_TOTAL=14.240` s,
because T2 and T3 share the same large P1B payload size, the same 8 s
`CNTPCT` delay, the same PSCI reset and the same fail-closed semantics; the
only difference is the checkpoint address
(`__primary_switched` → `start_kernel`). `T3_MINUS_T2` is therefore the
quantity that isolates the checkpoint move. T1 (`14.238` s) and T0
(`14.252` s) are secondary references only.

## 25. Timing windows (preregistered, never changed after a result)

| quantity | rule |
| --- | --- |
| `T3_MINUS_T2` STRONG | `abs(<=)1.000 s` |
| `T3_MINUS_T2` SUPPORTED | `<=2.000 s` |
| early-return class | `T3_TOTAL < 20.000 s` |
| automatic return | `AUTOMATIC_ANDROID_RETURN` required |
| `T3_MINUS_T1`, `T3_MINUS_T0` | `abs(<=)2.000 s` secondary cross-check |
| P0 decoder | SECONDARY only, `T3_PROGRAMMED_ESTIMATE = T3_TOTAL - 6.1445` |

Case classes: STRONG (`T3_A_STRONG`, `R4=PROVEN`), SUPPORTED
(`T3_B_SUPPORTED`, `R4=STRONGLY_SUPPORTED` — never `PROVEN` without extra
evidence), a secondary cross-check contradiction downgrades to
STRONGLY_SUPPORTED, `T3_EARLY_RETURN_TIMING_MISMATCH` for an early total
outside the supported band, `T3_SIGNATURE_NOT_OBSERVED` for a total back in
the old 20-28 s class, `T3_STABLE_FASTBOOT` and `T3_NO_RETURN` for the two
abnormal recovery classes. Every negative routes to
`MAINLINE_V2_R3_P1B_T3_FAILURE_ISOLATION_CI` and records
`T3_NOT_REACHED_LICENSE=NO`: an early return is **not** evidence that
`start_kernel` was not reached.

## 26. Positive boundary (a future T3 STRONG hit)

May record: `T3_REACHABILITY_SIGNATURE=STRONG`,
`START_KERNEL_ADDRESS_REACHED=PROVEN`, `R4=PROVEN`, and
`NORMAL_PRIMARY_SWITCHED_TO_START_KERNEL_PATH_EXECUTED=PROVEN`.
Must not record: `R5`, any `start_kernel` body execution, `setup_arch`,
`parse_args`, scheduler init, initramfs or `/init`; `E2` only under its
frozen definition. Even after a T3 STRONG the next stage is **not** T4
device execution: the next CI stage is
`MAINLINE_V2_R3_P1B_T4_PREDEVICE_READINESS_CI`.

## 27. Negative limitations

A T3 negative (not observed, mismatch, stable bootloader return, no return,
boot rejected) proves **only** that the preregistered timing signature was
not observed. It is never `start_kernel` non-reachability. The isolation
round it routes to must examine: the `__primary_switched` normal
continuation, the stack, `BSS`/init state, `VBAR_EL1`, boot-argument
recovery, the call site, the C entry ABI and the entry instrumentation.

## 28. Future T4 route

If T3 becomes STRONG, the assembly-to-C hand-off is proven and the next
informative checkpoint should be chosen from the exact source inside
`start_kernel` — preferentially a stage boundary such as `setup_arch()`
return or the completion of the "Booting kernel" command-line parse. That
choice is a **design note only** in this round: T4 is not device-ready and
`READY_FOR_DEVICE=NO`.

---

## 29. DEVICE GATE FINALIZATION

This section closes `T3_PREDEVICE_READINESS_CI_VERDICT=CI_PASS` into
`READY_FOR_R3_P1B_T3_DEVICE_CONTROL=YES`. No device operation.

`PREVIOUS_READY_FOR_DEVICE_NO_REASON=PREDEVICE_WORKFLOW_DEFAULT_FORBID + PRIVATE_BOOT_NOT_PACKED + PRIVATE_REVERIFY_NOT_DONE + T3_BOOT_SHA_NOT_FROZEN + PACIASP_DIAGNOSTIC_BOUNDARY_NOT_EXPLICIT`.

| gate | value |
| --- | --- |
| `T3_PUBLIC_CI_PASS` | YES (run `34850631688`, commit `e2b54b4`) |
| `T3_PRIVATE_PACK_PASS` | YES (run `34856507744`) |
| `T3_PRIVATE_REVERIFY_PASS` | YES (run `34856735790`) |
| `T3_ARTIFACT_IDENTITY_FROZEN` | YES |
| `T3_OBSERVER_READY` | YES |
| `T3_OBSERVER_FIXTURES` | PASS |
| `T3_PACIASP_AUDIT` | PASS |
| `T3_ENTRY_LANDING_AUDIT` | PASS |
| `T3_PREPATH_IDENTITY` | PASS |
| `T3_DEVICE_OPERATION` | NO |

Public payload `eff9a4a5b47413ec2c9f071158c7162a3361bf6443cbe58b43db7ccd0787e471`
size 37369041, 75 diff bytes, `[0x1b303c0,0x1b30410)`,
`START_KERNEL_CHECKPOINT_ONLY`. Private boot
`d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df`
size 37380096, envelope `KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY`. Independent
reverify extracted the kernel from that boot (no repack) and re-matched
payload SHA, inline window, trampoline, RT-D, geometry.

Observer FULL-SHA gate uses `R3_T3_SHA256=<T3 boot SHA>` before any
fastboot interaction; T2/T1/T0/FIX8/PANIC30/old INIT8/entry-state and
mutated T3 are refused. `FASTBOOT_BOOT_ONLY=YES`,
`SECOND_BOOT_FORBIDDEN=YES`. Observer is frozen, not executed.

Future timing (frozen, never changed after a result): T2 reference 14.240 s,
STRONG `|T3-14.240|<=1.000s`, SUPPORTED `<=2.000s`, `T3_TOTAL<20s`,
`AUTOMATIC_ANDROID_RETURN=YES`; secondary `|T3-T1|<=2s`, `|T3-T0|<=2s`.

Future STRONG may record `START_KERNEL_ADDRESS_REACHED=PROVEN`, `R4=PROVEN`,
`NORMAL_PRIMARY_SWITCHED_TO_START_KERNEL_PATH_EXECUTED=PROVEN`. Must keep
`R5` / normal `start_kernel` body `NOT_PROVEN` because original `paciasp`
prologue is diagnostically occupied. Must not claim `setup_arch`, cmdline
parse, initramfs, or `/init`. Evidence ladder is not upgraded this round.

---

## Round results (filled from the CI run)

Design iteration record: the first CI run (public run `34829584767`, commit
`2d11968`) passed the source gate on its first attempt and then failed
**by design** at the entry-instrumentation gate with
`T3_ENTRY_INSTRUMENTATION_FAILED: frozen first word 0xd503233f is not bti c`.
Authoritative public run is `34850631688` at `e2b54b4`.

- Public: `T3_PUBLIC_RUN=34850631688`, `T3_PUBLIC_COMMIT=e2b54b4`,
  source-audit PASS, T3 build PASS, independent verify PASS,
  `T3_PREDEVICE_READINESS_CI_VERDICT=CI_PASS`.
- `START_KERNEL_LINK_VA=0xffff800081b303c0`
- `START_KERNEL_IMAGE_OFFSET=0x1b303c0`
- `START_KERNEL_FILE_OFFSET=0x1b303c0`
- `START_KERNEL_SECTION=.init.text`
- `START_KERNEL_SECTION_FLAGS=AX`
- `START_KERNEL_ENTRY0=paciasp`
- `START_KERNEL_ENTRY0_BYTES=3f2303d5`
- callsite `0xffff800081b395ec` `75dbff97` DIRECT `BL`
- `T3_ENTRY_LANDING_REQUIREMENT=DIRECT_BL_NO_BTI_CHECK`
- `T3_PROBE_LANDING_REQUIREMENT_SATISFIED=YES`
- `T3_PACIASP_INTENTIONALLY_REPLACED=YES`
- `T3_DIAGNOSTIC_REQUIRES_PACIASP=NO`
- `T3_NORMAL_START_KERNEL_PROLOGUE_EXECUTED=NOT_PROVEN`
- `T3_BUILD_GATES=PASS`, `T3_NEGATIVE_FIXTURES=PASS`,
  `T3_DECODER_FIXTURES=PASS`, `T3_STATUS_GATE_STRUCTURED=YES`.
- `T3_PAYLOAD_SHA256=eff9a4a5b47413ec2c9f071158c7162a3361bf6443cbe58b43db7ccd0787e471`
- `T3_PAYLOAD_SIZE=37369041`
- `T3_CHECKPOINT_SHA256=dbeb828e753ba18d3e451551cd9a59eeff705831425ad5d2b0f5e11aa05edad8`
- `T3_CHECKPOINT_SIZE=80`
- `T3_PROBE_ARCHITECTURE=INLINE`, `T3_INLINE_OVERWRITE_SAFE=YES`,
  `T3_INLINE_MAPPING_EXECUTABLE=YES`,
  `T3_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT`,
  `T3_RELOCATION_SCAN=PASS`, `T3_LITERAL_SCAN=PASS`,
  `T3_EXCEPTION_TABLE_SCAN=PASS`, `T3_FUNCTION_EXTENT_SCAN=PASS`,
  `T3_JUMP_TABLE_SCAN=PASS`, `T3_ALTINSTRUCTIONS_SCAN=PASS`,
  `T3_DIAGNOSTIC_CORE_MATCHES_T1=YES`,
  `T3_DIAGNOSTIC_CORE_MATCHES_T2=YES`,
  `T2_PROBE_REMOVED_FROM_T3=YES`,
  `PRIMARY_SWITCHED_IDENTICAL_TO_FIX8=YES`,
  `T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8=YES`,
  `T3_PAYLOAD_DIFF_ATTRIBUTED=START_KERNEL_CHECKPOINT_ONLY`,
  `T3_DIFF_BYTE_COUNT=75`, `T3_DIFF_RANGES=[0x1b303c0,0x1b30410)`.
- `T3_START_KERNEL_REDERIVED=YES`,
  `T3_START_KERNEL_CALLSITE_FOUND=YES`,
  `T3_START_KERNEL_CALL_TARGET_EXACT=YES`,
  `T3_START_KERNEL_ENTRY_INSTRUCTION0=paciasp`,
  `T3_ENTRY_PAD_PRESERVED=YES`,
  `T3_BTI_LANDING_REQUIRED=NO`,
  `T3_PRE_START_KERNEL_CONTROL_FLOW_AUDITED=YES`,
  `T3_START_KERNEL_ENTRY_INSTRUMENTATION_AUDITED=YES`,
  `T3_PRE_CHECKPOINT_RUNTIME_REWRITE=NONE`,
  `T3_WINDOW_INSIDE_IMAGE_SIZE=YES`,
  `T3_CNTPCT_ACCESS_SAFE=YES`, `T3_PSCI_SYSTEM_RESET_SAFE=YES`,
  `T3_FAIL_CLOSED=YES`, `T3_STACK_USAGE=NO`, `T3_RUNTIME_RELOCATIONS=0`,
  `T3_TRAMPOLINE_IDENTICAL=YES`.
- `IMAGE_FILE_SIZE=35166720`, `IMAGE_HEADER_IMAGE_SIZE=0x2230000`,
  `DTB_OFFSET=0x2380000`, `payload_size=37369041`,
  `boot_size_expected=37380096`.
- Private: `T3_PRIVATE_PACK_RUN=34856507744`,
  `T3_PRIVATE_REVERIFY_RUN=34856735790`,
  `T3_BOOT_SHA256=d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df`,
  `T3_BOOT_SIZE=37380096`, `T3_PRIVATE_IDENTITY_REVERIFIED=YES`.
- Observer: `T3_OBSERVER_FULL_SHA_GATE=PASS`, `T3_OBSERVER_FIXTURES=PASS`.
- Final gate: **`READY_FOR_R3_P1B_T3_DEVICE_CONTROL=YES`**.
  Alternative token `R3_P1B_T3_PREDEVICE_NOT_READY` is not the current
  outcome. `T3_DEVICE_OPERATION=NO`. The T3 device run needs its own
  explicit user approval. Recommended next:
  `MAINLINE_V2_R3_P1B_T3_TRUE_DEVICE_CONTROL`.
