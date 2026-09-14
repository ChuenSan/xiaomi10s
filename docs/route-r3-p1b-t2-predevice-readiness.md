# R3 P1B T2 predevice readiness — `__primary_switched` reachability

Stage: **`MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI`**
Class: **CI / SOURCE AUDIT / ARTIFACT PREPARATION ONLY — NO DEVICE OPERATION**
Audience: internal route record.

Final gate (this round): either `READY_FOR_R3_P1B_T2_DEVICE_CONTROL` or
`R3_P1B_T2_PREDEVICE_NOT_READY`. A device round is a separate, explicitly
approved stage (`MAINLINE_V2_R3_P1B_T2_TRUE_DEVICE_CONTROL`) and is NEVER
implied by this document.

## Verdict

**`READY_FOR_R3_P1B_T2_DEVICE_CONTROL`** — CI / source audit / artifact
preparation is complete and every gate of §31 passes. A T2 device run is still
**NOT authorized**: it requires its own explicit user approval.

| item | value |
| --- | --- |
| public workflow | `thyme-r3-p1b-t2-predevice` run **34819753692** (source-audit 9 s / t2-build 13 m 36 s / verify 13 s — all green) |
| public commit pin | `a670a33d29575ecdaa3f4444f71695ed9ef3f01a` |
| T2 payload | `c48dc5ce5cc02ea0a51fc6003c4e9e822efca1c1a4e26d17260412f52b19090d`, 37369041 B, diff **72 B** at `[0x1b39534,0x1b39584)` |
| T2 probe | `c78c55fb2fa94b6e16a33e59d7973acc715c212a02a88bad1ed954ecb1ce412a`, 80 B (core `4d792df5…3611` = the T1 checkpoint, byte-identical) |
| private pack | `ChuenSan/thyme-mainline-private-ci` run **34821104997** → T2 boot `d347cc1907563afd2c8faa0d07cafed5904985514c346434c8a774c14418e925`, 37380096 B, `T2_PACK_GATES=PASS`, envelope `KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY` |
| private identity reverify | run **34821289820** → `T2_PRIVATE_IDENTITY_REVERIFY=PASS`, `T2_ARTIFACT_REBUILD_REQUIRED=NO` |


---

## 0. Permanent constraints (unchanged)

```
LOCAL_BUILD=NO            LOCAL_VALIDATION=NO     LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO      LOCAL_ACTIONLINT=NO     LOCAL_BINARY_VALIDATION=NO
DEVICE_OPERATION=NO       ADB_DEVICE_OPERATION=NO
FASTBOOT_DEVICE_OPERATION=NO
PARTITION_WRITES=0        SLOT_A_WRITTEN=NO       SET_ACTIVE=NO
```

Every kernel build, assembly, link, `objdump`, `readelf`, ELF inspection,
page-table/mapping validation, payload generation, boot generation, binary
validation and fixture execution happens **in GitHub Actions only**. Locally
only source reading, text editing and non-project syntax checking are allowed.

Current B stays **M5D+M5H+M5M-B (UNCHANGED)**. `FIX24` FROZEN. `M5N` FROZEN.
`T0`/`T1`/`PANIC30`/`FIX8`/`FIX24`/`M5N`/`T3` are **not** re-run or executed in
this round.

---

## 1. T0 / T1 true-device proof (frozen, unchanged)

| item | value |
| --- | --- |
| `T0_TOTAL` | 14.252 s (`programmed delay` 8.000 s, `programmed estimate` 8.108 s, error **+0.108 s**) |
| `T0` verdict | **STRONG**; `T0 reachability = PROVEN` |
| `T1_TOTAL` | 14.238 s (cross-check 14.214 s) |
| `T1_MINUS_T0` | **−0.014 s**; matched-control verdict **STRONG** |
| `T1` secondary | `programmed estimate` 8.093 s; `automatic Android return = YES` |
| `T1 reachability` | **PROVEN** |
| final gate | `MAINLINE_V2_R3_P1B_T1_REACHABILITY_PROVEN` |

Both rounds were ONE identity-gated `fastboot boot` each, full-SHA verified
before any interaction, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`.

---

## 2. Why T2 exists

The T1 positive proved that the **normal FIX8 trampoline branch** delivered the
CPU to the `primary_entry` **address** (`R2 PROVEN`). It could not prove
anything about normal `primary_entry` execution, because T1 replaced
`primary_entry`'s first instruction (`bl record_mmu_state`) with its own
diagnostic branch. Therefore T1 says nothing about:

* `record_mmu_state` execution,
* `preserve_boot_args` execution,
* `create_idmap` execution,
* the MMU transition (`__enable_mmu`, `SCTLR_EL1.M=1`, TTBR installation),
* arrival at `__primary_switched`.

T2 exists to answer exactly the last item and, through it, the whole
`primary_entry → __primary_switched` head.S path.

---

## 3. T2 proof boundary (what a future T2 positive would and would not prove)

**Answerable by T2** (and therefore the ONLY things this round designs for):

`T2 = __primary_switched ADDRESS REACHABILITY` — the question is whether the
**never-modified normal FIX8 `primary_entry`** executes the exact head.S start
path through the MMU transition and actually arrives at the `__primary_switched`
entry address.

**Explicitly out of scope** — the T2 design must not be extended to
`start_kernel`, DT parsing, built-in initramfs, `/init`, or "the memory
subsystem works". All of those stay `NOT_PROVEN`.

Boundary statement emitted by the CI:
`T2_MMU_PROOF_BOUNDARY=head.S MMU TRANSITION TO THE T2 ADDRESS ONLY`.

---

## 4. Exact head.S path (linux-6.6.156, commit `8b73de7da85fde281a385e0b26eda9bffd3ca477`)

```
primary_entry:                       .head.text
    bl  record_mmu_state             x19 = MMU state at entry (0 when entered with MMU off)
    bl  preserve_boot_args           x21 = FDT; x0..x3 stored into boot_args
    bl  create_idmap                 x22 = idmap VA of the DT blob
    cbz x19, 0f  ... cache clean ...
0:  mov x0, x19
    bl  init_kernel_el               w0 = cpu_boot_mode; eret with INIT_PSTATE_EL1
    mov x20, x0
    bl  __cpu_setup                  mair_el1/tcr_el1/cpacr_el1/mdscr_el1; enable_dbg
    b   __primary_switch

__primary_switch:
    adrp x1, reserved_pg_dir
    adrp x2, init_idmap_pg_dir
    bl  __enable_mmu                 phys_to_ttbr x2 -> ttbr0_el1 ; load_ttbr1 ; set_sctlr_el1 (M=1)
    adrp x23, KERNEL_START ...       (CONFIG_RELOCATABLE)
    mov x0, x22 ... bl __pi_kaslr_early_init ...   (CONFIG_RANDOMIZE_BASE)
    mov sp, x1                       x1 = init_pg_end
    bl  clear_page_tables
    bl  create_kernel_mapping
    adrp x1, init_pg_dir
    load_ttbr1 x1, x1, x2            ttbr1_el1 = init_pg_dir
    bl  __relocate_kernel            applies .rela.dyn + RELR in place
    ldr x8, =__primary_switched      indirect branch to the linked kernel VA
    adrp x0, KERNEL_START            x0 = __pa(KERNEL_START)
    br  x8                           ---> *** T2 probe sits HERE ***

__primary_switched:                  .init.text (measured output section, flags AX)
    bti  c                           <- SYM_FUNC_START_LOCAL emits this unconditionally
    adr_l x4, init_task             <- the ORIGINAL first real instruction (ADRP/ADD x4)
    init_cpu_task x4, x5, x6
    ...
```

Two facts drive the whole design:

1. `__primary_switched` has **exactly one** entry edge: the indirect
   `br x8` immediately before it. Patching the bytes **at** `__primary_switched`
   therefore perturbs no branch instruction at all.
2. `__relocate_kernel` runs **before** `__primary_switched`. Any runtime
   relocation whose target lies inside the overwritten window would overwrite
   the probe bytes in memory, so relocation targets must be excluded — this is
   the real hazard, and it is scanned explicitly.

A third, non-obvious fact was discovered by this round's CI and changed the
probe: the **first instruction of `__primary_switched` is `bti c`**
(`0xd503245f`), because arm64's `SYM_FUNC_START_LOCAL` emits a BTI landing pad
unconditionally (`arch/arm64/include/asm/linkage.h` lines 26-28):

```
#define SYM_FUNC_START_LOCAL(name)                     \
        SYM_START(name, SYM_L_LOCAL, SYM_A_ALIGN)      \
        bti c ;
```

The T2 probe therefore re-emits `bti c` as its own first instruction
(`T2_BTI_LANDING_PAD_PRESERVED=YES`) and only repurposes the 19 instructions
that follow it. See §7a.

---

## 5. primary_entry normal-path identity

T2 does **not** patch `primary_entry`. `T2_PRIMARY_ENTRY_PATCHED=NO`. The T1
approach (replacing `bl record_mmu_state` with a branch) is deliberately
abandoned here. Consequently everything from `primary_entry` up to (but not
including) the first byte of `__primary_switched` is **byte-identical** to the
frozen FIX8 payload:

```
T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8=YES
```

---

## 6. `__primary_switched` re-derivation

Never taken from history. The CI re-derives, in this round, from the
authoritative rebuilt `vmlinux` plus its `System.map`:

```
PRIMARY_SWITCHED_VA             = 0xffff800081b39534
PRIMARY_SWITCHED_IMAGE_OFFSET   = 0x1b39534   (VA - VA(_text), Image is flat)
PRIMARY_SWITCHED_FILE_OFFSET    = 0x1b39534   (vmlinux section offset + delta)
PRIMARY_SWITCHED_SECTION        = .init.text
PRIMARY_SWITCHED_SECTION_FLAGS  = AX          (SHF_ALLOC | SHF_EXECINSTR)
PRIMARY_SWITCHED_SECTION_VA     = 0xffff800081b30000
T2_PRIMARY_SWITCHED_REDERIVED   = YES
```

(The numbers above are the deterministic CI measurements of this round; the
section is the linker's merged output section that carries the head.S code at
this layout. It is still mapped and executable at T2 entry and is only freed
after `start_kernel` — which T2 never reaches.)

Section headers are read with a multi-strategy parser (`llvm-readelf -S
--wide` first, `llvm-objdump --section-headers` / `-h` as fallbacks, each with
a tolerant field/flags layout parser and a diagnostic dump on failure); the
LLVM 18 `llvm-objdump` section-header layout produced no parseable records in
this environment, so the readelf source is the one this round reports as
`PRIMARY_SWITCHED_SECTION_FLAGS_SOURCE=SECTION_HEADERS`.

Cross-checks enforced: `llvm-nm` value == `System.map` value; `primary_entry`
offset agrees across `llvm-nm`, `System.map` and the existing `kernel_gate`
code-island check; the historical reference `0x1b39534` is used **only** as a
sanity cross-check and gates nothing — it happened to reproduce exactly.

`T2_PRIMARY_ENTRY_OFFSET_REDERIVED=YES` likewise (historical reference
`0x1b1c0a0` is context only).

---

## 7. Original instruction identity

```
T2_PRIMARY_SWITCHED_ORIGINAL_INSN1=bti c
T2_PRIMARY_SWITCHED_ORIGINAL_INSN2=adrp x4, init_task
T2_PRIMARY_SWITCHED_ORIGINAL_FIRST_BYTES=   (0xd503245f, `bti c`)
T2_PRIMARY_SWITCHED_ORIGINAL_SECOND_BYTES=   (ADRP Rd=x4)
T2_PRIMARY_SWITCHED_ORIGINAL_INSN_SOURCES_AGREE=YES
T2_BTI_LANDING_PAD_PRESERVED=YES
```

Four independent sources must agree:

1. `arch/arm64/include/asm/linkage.h` lines 26-28 (`SYM_FUNC_START_LOCAL`
   appends `bti c`),
2. `arch/arm64/kernel/head.S` line 473 (`adr_l x4, init_task` after
   `SYM_FUNC_START_LOCAL(__primary_switched)`),
3. the **frozen FIX8 payload bytes** at the re-derived Image offset,
4. the **authoritative `vmlinux` disassembly** at `PRIMARY_SWITCHED_VA`.

The gate is not a symbol name: word[0] must be exactly `bti c`, word[1] must
decode as `ADRP` with `Rd = x4`, and the frozen words must equal the
disassembled words. At least **32** original instructions are disassembled and
recorded (`p1b-t2-primary-switched-vmlinux-disasm.txt`), and all
`T2_PROBE_SIZE/4 = 20` overwritten words are printed verbatim. A
literal-`.inst`-word re-assembly record of the overwritten words is kept as an
independent encoding path.

### 7a. BTI landing pad (why the probe re-emits `bti c`)

`__primary_switched` is entered by `br x8`, an **indirect** branch, and arm64
marks every `SYM_FUNC_START*` entry with a `bti c` landing pad. Overwriting
that word with a non-BTI instruction would, **if** guarded control flow were
ever enforced at that point, turn a working indirect entry into a BTI fault.
Whether it is enforced today is debatable — `SCTLR_EL1.BT0/BT1` is programmed
by `cpu_enable_bti()` well after `start_kernel`, and the normal FIX8 boot
demonstrably passes through this exact `br x8 → bti c` edge — but T2 does not
need to win that argument:

* the probe's first instruction **is** `bti c`, byte-identical to the original;
* the BTI landing-pad property of the entry is therefore preserved by
  construction;
* the runtime semantic change is confined to the 19 instructions **after** the
  landing pad.

This is the one permitted deviation from "byte-identical T1 core" allowed by
the round brief ("branch/insertion mechanics"), and it is recorded explicitly
(`T2_DIAGNOSTIC_CORE_SLICE_MATCHES_T1=YES` plus
`T2_BTI_LANDING_PAD_PRESERVED=YES`).

---

## 8. T2 entry CPU state (T2 entry contract)

Derived from the exact source path, not from assumption; every field is
source-backed and the CI asserts that a reason exists for each key.

| field | value | source |
| --- | --- | --- |
| `T2_ENTRY_CURRENT_EL` | `EL1` | `init_kernel_el` `eret` with `SPSR = INIT_PSTATE_EL1` (`PSR_MODE_EL1h`) |
| `T2_ENTRY_MMU` | `ON` | `__enable_mmu` `set_sctlr_el1 x0` with `INIT_SCTLR_EL1_MMU_ON` |
| `T2_ENTRY_TTBR_STATE` | `TTBR0_EL1=init_idmap_pg_dir(PHYS) TTBR1_EL1=init_pg_dir(PHYS)` | `phys_to_ttbr` + `load_ttbr1` |
| `T2_ENTRY_PC_ADDRESS_SPACE` | `VA` | `ldr x8, =__primary_switched ; br x8` |
| `T2_ENTRY_SP_VALID` | `YES` | `mov sp, x1` (`init_pg_end`) |
| `T2_ENTRY_DAIF` | `D=0,A=1,I=1,F=1` | `INIT_PSTATE_EL1` masks all four; `__cpu_setup` `enable_dbg` clears `D` |
| `T2_ENTRY_X0_MEANING` | `__pa(KERNEL_START)` | `adrp x0, KERNEL_START` |
| `T2_ENTRY_X1_MEANING` | page-table scratch (`load_ttbr1`), NOT boot contract | `preserve_boot_args` had already saved the ABL x0..x3 |
| `T2_ENTRY_X2_MEANING` | `init_idmap_pg_dir` scratch temp, NOT boot contract | ditto |
| `T2_ENTRY_X3_MEANING` | scratch, pre-T2 residue, NOT boot contract | ditto |
| `T2_ENTRY_X19_X25` | `x19`=mmu_enabled_at_boot(0), `x20`=cpu_boot_mode, `x21`=FDT pa, `x22`=idmap VA of DT, `x23`=KASLR/load offset, `x24`=memstart seed, `x25`=supported VA size | head.S register contract comment |

The probe writes **none** of `x1,x2,x3,x19..x25`; it clobbers only
`w0/x0(PSCI FID), x9..x13, NZCV`.

**Residual risk recorded honestly:** at `__primary_switched` entry,
`DAIF.D = 0` (debug exceptions unmasked by `__cpu_setup`) while `VBAR_EL1` has
not yet been programmed — the normal path only does that at instruction 6 of
`__primary_switched`. T2's probe therefore re-masks DAIF at its **first**
instruction, i.e. strictly earlier than the normal path does anything about
it, so T2 is not weaker than normal boot on this axis.

---

## 9. MMU state and the implied transition

Because `__primary_switched` is reachable **only** through
`__primary_switch`'s `ldr x8, =__primary_switched ; br x8`, which runs after
`__enable_mmu` set `SCTLR_EL1.M = 1` and after `load_ttbr1` installed
`init_pg_dir`:

```
T2_REACH_IMPLIES_MMU_ENABLE_PATH_EXECUTED=YES
```

This is a claim about the **head.S MMU transition only**. It does **not**
establish that the memory subsystem, caches, mapping attributes, or anything
after `__primary_switched` work. Full normal-Mainline-memory success is not
claimed.

---

## 10. TTBR / VA semantics

At T2 entry the active translation regime is the early one: `TTBR0_EL1` holds
the physical address of `init_idmap_pg_dir`, `TTBR1_EL1` holds the physical
address of `init_pg_dir`, and the CPU executes at the linked kernel VA that
`create_kernel_mapping` mapped. `PC` is a **VA**, never a physical address:
`PA_AS_VA_CONFUSION` is a registered negative fixture and is REJECTed.

---

## 11. Probe architecture — INLINE (selected)

```
T2_PROBE_ARCHITECTURE=INLINE
T2_INLINE_START = PRIMARY_SWITCHED_VA        (0xffff800081b39534)
T2_INLINE_END   = PRIMARY_SWITCHED_VA + 80   (0xffff800081b39580)
```

The 80-byte (20-instruction) fail-closed diagnostic is written directly
over the first 20 instruction slots of `__primary_switched` in kernel text
(measured output section `.init.text`, flags `AX`): one `bti c` landing pad
preserved verbatim, then the 76-byte (19-instruction) T1-proven core.

Rationale, in order of weight:

1. The probe executes at the **same VA the CPU just branched to**. The
   executable-mapping proof is therefore the arrival itself —
   `T2_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT`, `T2_MAPPING_EXECUTABLE=YES`.
2. No branch instruction is modified (indirect `br x8` entry), so no branch
   re-encoding, no branch-range question, no re-derivation of an entry edge.
3. The payload diff collapses to a **single contiguous region**, which is the
   cleanest possible attribution.

---

## 12. Why not EXTERNAL (and the padding prohibition)

Section 14 of the round brief is honoured strictly:

* T1's checkpoint lived at `0x2230000`, in the deterministic zero padding
  **after** the Image file (end `0x2189A00`) and after the Linux `image_size`
  runtime footprint (`0x2230000`), before the RT-D trailer (`0x2380000`).
* That placement was proven under **MMU-off** execution. It says nothing about
  whether that VA has an executable mapping under the MMU-on early page tables
  built by `create_kernel_mapping`, which maps the kernel image (`_text` ..
  `_end`), not the padding beyond it.
* Therefore the same address is **never** reused. `T2_EXTERNAL_CHECKPOINT_USED=NO`
  and `T2_PADDING_MAPPING_USED=NO`.
* Registered negative fixtures: `T2_UNPROVEN_PADDING_MAPPING` → REJECT,
  `CHECKPOINT_IN_UNMAPPED_REGION` → REJECT, `CHECKPOINT_IN_NX_REGION` → REJECT.

---

## 13. Inline overwrite safety (the central audit)

Window = `[PRIMARY_SWITCHED_VA, PRIMARY_SWITCHED_VA + 80)`. Six scans run over
the authoritative rebuild; any hit is a hard stop
(`T2_INLINE_OVERWRITE_SAFE=YES` is required, otherwise the artifact is
rejected):

| scan | what it rejects | gate token |
| --- | --- | --- |
| symbol | any symbol VA strictly inside the window (a real entry into the middle) | `T2_SYMBOL_SCAN=PASS` |
| control flow | any branch anywhere in an executable section whose target lands strictly inside the window (raw word candidates are **confirmed** against the `vmlinux` disassembly before rejection) | `T2_BRANCH_SCAN=PASS`, `T2_CONTROL_FLOW_SCAN=PASS` |
| relocation | any `.rela.dyn` / RELR runtime relocation **target** inside the window — `__relocate_kernel` would rewrite the probe bytes | `T2_RELOCATION_SCAN=PASS` |
| absolute literal | any 8-byte aligned literal in the Image equal to a VA strictly inside the window (an indirect entry or pointer into the middle) | `T2_LITERAL_SCAN=PASS` |
| section boundary | the window must lie entirely inside exactly one `SHF_ALLOC|SHF_EXECINSTR` section and must not touch a section end | `T2_SECTION_BOUNDARY_SCAN=PASS` |
| alternatives / exception tables | reported, not hazardous: `apply_alternatives` and exception-table consumption happen **after** `start_kernel`, which T2 never reaches | `T2_ALT_EX_TABLE_HAZARD=NO_POST_START_KERNEL_ONLY` |

The expected shape of the original window content is one BTI landing pad
followed by pure straight-line code:

```
bti c ;
adrp/add x4, init_task ; msr sp_el0,x4 ; ldr x5,[x4,#TSK_STACK] ;
add sp,x5,#THREAD_SIZE ; sub sp,sp,#PT_REGS_SIZE ; stp xzr,xzr,[sp,...] ;
add x29,sp,... ; adrp/add x5,__per_cpu_offset ; ldr w6,[x4,#TSK_TI_CPU] ;
ldr x5,[x5,x6,lsl#3] ; msr tpidr_el1/el2 (alternative pair) ;
adrp/add x8, vectors ; msr vbar_el1,x8 ; isb ; stp x29,x30,[sp,#-16]!
```

no branch instruction, no internal label, no literal pool. The scans confirm
this rather than assume it.

Measured coverage in this round (public run 34819753692):

```
T2_SYMBOL_SCAN      183010 symbols,  none inside the window
T2_BRANCH_SCAN      0 raw candidates and 0 confirmed hits landing in the window
T2_RELOCATION_SCAN  568280 runtime relocation locations (.rela.dyn + RELR),
                    none inside the window
T2_LITERAL_SCAN     4395840 8-byte slots, no absolute VA inside the window
T2_INLINE_OVERWRITE_SAFE=YES
```

---

## 14. Original overwritten instructions

`T2_PRIMARY_SWITCHED_OVERWRITTEN_INSN_COUNT=20` and the full word list is
printed as `T2_PRIMARY_SWITCHED_OVERWRITTEN_INSN_WORDS=` plus saved as a
literal-word re-assembly record. The first word identity is enforced as an
ADRP-class check (see §7) — a symbol name alone is never accepted as evidence.

---

## 15. CNTPCT safety under MMU-on

```
T2_CNTPCT_ACCESS_SAFE=YES
```

Audit: `arch/arm64/kernel/head.S` and `__cpu_setup` (`arch/arm64/mm/proc.S`)
touch **neither** `CNTKCTL_EL1` **nor** `CNTHCTL_EL2`, and introduce no counter
trap. Grep-verified writes are limited to `cpacr_el1`, `tcr_el1`, `sctlr_el1`,
`sctlr_el2`, `mair_el1`, `mdscr_el1`. `CNTFRQ_EL0`/`CNTPCT_EL0` reads are legal
at EL1 regardless of `SCTLR_EL1.M`, the same EL1 access was already proven on
this device at T0 and T1, and the MMU state does not affect system-register
access. Timer primitive is `CNTPCT_REGISTER_ONLY`: `cntfrq_el0 × 8` polled
against `cntpct_el0`.

---

## 16. PSCI reset safety under MMU-on

```
T2_PSCI_SYSTEM_RESET_SAFE=YES
```

PSCI `SYSTEM_RESET` (`fid=0x84000009`) takes **no pointer argument**, so no
VA→PA conversion is involved and no mapping is required. `smc` traps
synchronously to EL3 regardless of `SCTLR_EL1.M`; EL3's PSCI implementation
does not inspect the caller's PC. The identical EL1 `smc` returned on this
device in the T0 and T1 rounds, which is direct evidence that the EL1 `smc`
conduit itself is live.

---

## 17. Fail-closed semantics

```
T2_FAIL_CLOSED=YES
```

```
msr daifset, #0xf ; isb
mrs x9, cntfrq_el0 ; movz x10, #8 ; mul x10, x9, x10 ; isb
mrs x11, cntpct_el0
1: isb ; mrs x12, cntpct_el0 ; sub x13,x12,x11 ; cmp x13,x10 ; b.hs 2f ; yield ; b 1b
2: movz w0, #0x9 ; movk w0, #0x8400, lsl #16 ; smc #0
3: wfe ; b 3b
```

If the `smc` returns for any reason, control reaches `wfe` and loops there
forever. There is **no** register restore, **no** return, **no** fall-through,
**no** path to the overwritten `__primary_switched` instructions and **no**
path to `start_kernel`. The disassembly gates enforce this structurally
(exactly one `smc`, `wfe` immediately after it, terminal `b` targeting that
`wfe`, nothing but padding after the loop).

---

## 18. Register discipline

| category | registers | rule |
| --- | --- | --- |
| clobbered | `w0/x0` (PSCI FID pair only), `x9,x10,x11,x12,x13`, `NZCV` | allowed |
| never written | `x1,x2,x3` | hard gate — boot contract |
| never written | `x19..x25` | callee-saved head.S contract |
| never written | `sp/wsp`, `x29`, `x30` | hard gate — `T2_STACK_USAGE=NO` |

`x0/w0` may only be written by the `movz w0,#9` + `movk w0,#0x8400,lsl#16`
pair.

---

## 19. No stack, no memory access

```
T2_STACK_USAGE=NO
T2_MEMORY_READS=NO
T2_MEMORY_WRITES=NO
```

The probe is register-only: no stack, no load, no store, no MMIO, no scheduler,
no kernel timer infrastructure — only instruction fetch. `SP` is valid at T2
entry but is deliberately **not** used, so the T2 result depends only on
reachability, the architectural counter, and PSCI. `adrp`/`adr` are forbidden
because they are store-class/memory-address-class in the existing gate
discipline; the T2 core needs neither.

---

## 20. Position independence / runtime relocations

```
T2_POSITION_INDEPENDENT=YES
T2_RUNTIME_RELOCATIONS=0
```

PC-relative branches only; no hardcoded physical `S`, no bootloader load
address, no absolute address. In INLINE mode no absolute address is needed at
all. Registered negative fixture `PA_AS_VA_CONFUSION` → REJECT.

---

## 21. Diagnostic core identity vs T1

```
T2_DIAGNOSTIC_CORE_MATCHES_T1=YES
T2_DIAGNOSTIC_CORE_SLICE_MATCHES_T1=YES
```

The CI assembles **both** `scripts/r3-p1b/p1b-t2-device.S` and the frozen
`scripts/r3-p1b/p1b-t1-device.S` in the same job and requires the two output
cores to be **byte-identical** (76 bytes each) after the T2 probe's leading
`bti c` landing pad. The delay/reset core is therefore literally the T0/T1
true-device proven instruction sequence. The only permitted differences are
insertion mechanics: the T1 predecessor branched in from `primary_entry`,
whereas T2 is entered at the natural `__primary_switched` entry and must keep
the `bti c` landing pad (§7a).

---

## 22. Payload diff attribution

```
T2_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_SWITCHED_CHECKPOINT_ONLY
T2_RUNTIME_SEMANTIC_DELTA=PRIMARY_SWITCHED_REACHABILITY_CHECKPOINT_ONLY
T2_DIFF_BYTE_COUNT=72
T2_DIFF_RANGES=[0x1b39534,0x1b39584)
```

Exactly **one** contiguous diff region against the frozen FIX8 payload:
`[PRIMARY_SWITCHED_IMAGE_OFFSET, +80)`. Zero bytes change anywhere else.
Concretely enforced:

* trampoline (48 B @ `0x40`) byte-identical → `T2_TRAMPOLINE_IDENTICAL_TO_FIX8`;
* `primary_entry` unpatched (`T2_PRIMARY_ENTRY_PATCHED=NO`);
* the entire pre-T2 prefix `frozen[0:off_ps]` byte-identical;
* RT-D trailer byte-identical; payload size identical; boot envelope geometry
  identical.

Registered negative fixtures: `EXTRA_PAYLOAD_DIFF`, `PRIMARY_ENTRY_MODIFIED`,
`TRAMPOLINE_MODIFIED`, `RT_D_CHANGED`, `PAYLOAD_SIZE_CHANGE` → all REJECT.

---

## 23. Trampoline identity

```
T2_TRAMPOLINE_IDENTICAL_TO_FIX8=YES
sha256 = 362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623
```

The frozen FIX8 48-byte trampoline at `0x40` is preserved verbatim, and its
`word[8]` branch target is re-checked against the **re-derived** `primary_entry`
offset in the Image-relative coordinate space.

---

## 24. RT-D / `/init` / initramfs identity

```
RT-D  sha256 = 4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327 (144593 B, panic=5)
/init      = f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d
initramfs  = 02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3
```

T2 never executes them, but single-variable discipline keeps them byte-identical
anyway. The PANIC30 RT-D is forbidden.

---

## 25. Geometry

```
DTB_OFFSET                = 0x2380000
IMAGE_HEADER_IMAGE_SIZE   = 0x2230000   (re-read from the authoritative binary header)
IMAGE_FILE_SIZE           = 35166720    (0x2189A00)
payload size              = 37369041
boot size                 = 37380096
```

The historical reading ambiguity (`0x2230000` vs `0x2231000`) is resolved by
rule: only the value **actually read from the final authoritative Image header**
counts. `T2_AUTHORITATIVE_IMAGE_SIZE` is printed with
`SOURCE=FINAL_BINARY_HEADER`; the two historical readings are listed as ignored
context and gate nothing. Any drift in geometry FAILs the round.

---

## 26. Private packaging

The private GHA wrapper takes the public T2 payload, splices it into the
**exact FIX8 known-good M5D boot v3 envelope** (only the kernel payload is
replaced), packs boot v3 and re-validates:

* `kernel_size` field == payload size; header diff confined to bytes `8..12`;
* ramdisk / `cmdline` / `os_version` / `reserved` / tail-padding policy all
  MATCH the M5D reference;
* the inline region inside the packed kernel equals the built T2 probe
  (`T2_PACK_FAILED: inline region != built T2 probe` otherwise);
* capacity margin ≥ 16 MiB; RT-D trailer SHA exact.

PUBLIC: source audit, ELF/mapping audit, T2 assembly, binary patch proof,
`objdump`/`readelf` output, raw payload, diff report, fixtures, observer
fixtures. PRIVATE ONLY: the OEM envelope and the T2 boot image.

Measured this round (private pack run 34821104997):

```
T2_BOOT_SHA256          = d347cc1907563afd2c8faa0d07cafed5904985514c346434c8a774c14418e925
T2_BOOT_SIZE            = 37380096
T2_KERNEL_SIZE          = 37369041
T2_ENVELOPE_VS_M5D      = KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY
T2_RT_D_TRAILER_SHA_EXACT = PASS
T2_BOOT_CAPACITY        = PASS
T2_INLINE_REGION_IN_KERNEL_TEXT = YES
T2_PRIVATE_INLINE_WINDOW = [0x1b39534,0x1b39584)
T2_PACK_GATES           = PASS
```

Identity re-verified without any rebuild in run 34821289820
(`T2_PRIVATE_IDENTITY_REVERIFY=PASS`, `T2_ARTIFACT_REBUILD_REQUIRED=NO`).
`DEVICE_OPERATION=NO` in every step.

---

## 27. T2 observer (prepared, NOT executed)

`scripts/r3-p1b/observe-r3-p1b-t2.py`, derived from the T1 observer so the host
timeline stays comparable. Identity gate is **FULL-SHA only** and refuses
T0 / T1 / FIX8 / PANIC30 / old-INIT8 / entry-state-probe boots **before any
interaction with the device interface**. `FASTBOOT_BOOT_ONLY=YES`,
`SECOND_BOOT_FORBIDDEN=YES`, no flash, no erase, no `set_active`, no second
boot. `T2_NOT_REACHED_LICENSE=NO` is structural: a negative outcome can never
conclude "not reached" and always routes to `T2_FAILURE_ISOLATION`.

---

## 28. Timing windows (preregistered)

Primary reference is **T1**, because T1 and T2 share the same large P1B
payload, the same 8 s CNTPCT primitive, the same PSCI reset and the same
fail-closed diagnostic; they differ only in where the checkpoint sits
(`primary_entry` address → `__primary_switched` address).

```
T1_REFERENCE_TOTAL = 14.238 s        (PRIMARY matched-control reference)
T2_MINUS_T1 = T2_TOTAL − 14.238
  STRONG     |T2_MINUS_T1| <= 1.000 s
  SUPPORTED  |T2_MINUS_T1| <= 2.000 s
T0_REFERENCE_TOTAL = 14.252 s        (SECOND matched reference)
T2_MINUS_T0 = T2_TOTAL − 14.252      cross-check |.| <= 2.000 s
early-return class:  T2_TOTAL < 20.000 s            (required)
AUTOMATIC_ANDROID_RETURN                            (required)
SECONDARY only: T2_PROGRAMMED_ESTIMATE = T2_TOTAL − 6.1445  (expected ~8 s)
```

Note on the cross-check: because the observed `T1_MINUS_T0` is only −0.014 s,
a primary STRONG result (|T2_MINUS_T1| ≤ 1.0 s) mathematically implies
|T2_MINUS_T0| ≤ 1.014 s, i.e. the T0 cross-check cannot contradict a primary
STRONG verdict. The CI still evaluates it explicitly and has a dedicated
`T2_A_STRONG_T0_CROSSCHECK_BLOCK` outcome should that ever change.

Outcome classes:

| case | condition | recording |
| --- | --- | --- |
| A | primary STRONG + early class + automatic Android return (+ cross-check ok) | `T2_REACHABILITY_SIGNATURE=STRONG` |
| B | 1.0 s < \|T2_MINUS_T1\| ≤ 2.0 s, early class, automatic return | `SUPPORTED` |
| C | T2 total back in the old ~23–26 s auto-return class (band `[20,28)`) | `T2_SIGNATURE_NOT_OBSERVED` |
| D | `T2_TOTAL < 20 s` but outside the matched-control window | `T2_EARLY_RETURN_TIMING_MISMATCH` |
| E | stable bootloader return instead of Android | `T2_STABLE_FASTBOOT` |
| F | > 120 s with neither Android nor stable bootloader return | `T2_NO_RETURN` (manual elapsed excluded from timing) |

---

## 29. Evidence-upgrade rule (frozen now, so it cannot be relaxed later)

If a future T2 run is STRONG **and**
`T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8=YES` holds:

* `R3 = PROVEN` (`PRIMARY_SWITCHED_ADDRESS_REACHABILITY`).
* `R2` is strengthened from "address reachable" to "the **normal**
  `primary_entry` path executed up to T2"
  (`NORMAL_PRIMARY_ENTRY_PATH_TO_T2_EXECUTED=PROVEN`).
* `E1` may be upgraded to `PROVEN` — **only** because the static diff gate
  proves `primary_entry → T2` byte-identical to FIX8.
* `E2` is **NOT** auto-upgraded. `E2` is upgraded only if the project's frozen
  `E2` definition is explicitly equivalent to a successful head.S/MMU
  transition. Under the current frozen definition it is not, so `E2` stays
  `NOT_PROVEN`, and this document records that `R3` is `PROVEN` while `E2` is
  **not yet satisfied**. Evidence inflation is prohibited.

If the future T2 result is B/SUPPORTED, `R3` is at most `STRONGLY_SUPPORTED`
and `E1` is at most `STRONGLY_SUPPORTED`. If it is C/D/E/F,
`T2_SIGNATURE_NOT_OBSERVED` / the corresponding class is recorded and the
recommended next stage is `MAINLINE_V2_R3_P1B_T2_FAILURE_ISOLATION_CI`
(`record_mmu_state`, boot mode, `preserve_boot_args`, idmap creation,
`__cpu_setup`, MMU enable, VA transition, branch target, instrumentation
mapping) — never a jump to `start_kernel`.

---

## 30. Negative limitations and next layers

* The T2 design deliberately does **not** answer anything past the
  `__primary_switched` entry address. `T3` is **NOT DEVICE READY**
  (`T3_STATUS=NOT_DEVICE_READY`); its recommended scope is
  `start_kernel` ADDRESS reachability or the earliest stable C-entry checkpoint
  after an exact source audit.
* The register-only probe discards the ability to observe anything about
  kernel state; that is the price of keeping the result dependent only on
  reachability, the architectural timer and PSCI.
* Alternatives / exception tables touching the window are reported, not
  hypothesised away; the reason they are harmless (post-`start_kernel`
  application) is recorded above.
* The `T2_STATUS_GATE_SEMANTIC=YES` structured status-document gate replaces
  the fragile literal-token gate for **this** round's status check; the older
  T0/T1 source gates still use literal substring checks and are left untouched.

---

## 31. Gate summary (CI-printed, all required)

```
T2_PRIMARY_SWITCHED_REDERIVED=YES
T2_PRIMARY_SWITCHED_ORIGINAL_INSN1=bti c
T2_PRIMARY_SWITCHED_ORIGINAL_INSN2=adrp x4, init_task
T2_BTI_LANDING_PAD_PRESERVED=YES
T2_ENTRY_MMU=ON
T2_ENTRY_PC_ADDRESS_SPACE=VA
T2_PROBE_ARCHITECTURE=INLINE
T2_INLINE_OVERWRITE_SAFE=YES
T2_MAPPING_SOURCE=KERNEL_TEXT_VA_SELF_EVIDENT
T2_RELOCATION_SCAN=PASS   T2_LITERAL_SCAN=PASS
T2_CNTPCT_ACCESS_SAFE=YES T2_PSCI_SYSTEM_RESET_SAFE=YES
T2_FAIL_CLOSED=YES        T2_STACK_USAGE=NO
T2_RUNTIME_RELOCATIONS=0  T2_DIAGNOSTIC_CORE_MATCHES_T1=YES
T2_DIAGNOSTIC_CORE_SLICE_MATCHES_T1=YES
T2_PRECHECKPOINT_HEADS_PATH_IDENTICAL_TO_FIX8=YES
T2_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_SWITCHED_CHECKPOINT_ONLY
T2_TRAMPOLINE_IDENTICAL_TO_FIX8=YES
T2_DIAGNOSTIC_ONLY=YES    T2_NORMAL_KERNEL_BOOT_CANDIDATE=NO
T2_STATUS_GATE_SEMANTIC=YES
READY_FOR_R3_P1B_T2_DEVICE_CONTROL  /  R3_P1B_T2_PREDEVICE_NOT_READY
```

`E1` stays `NOT_PROVEN`, `E2` stays `NOT_PROVEN`, `R3` stays `NOT_PROVEN`
until a future STRONG device round under §29.

Result of this round: **`READY_FOR_R3_P1B_T2_DEVICE_CONTROL`** (the
alternative outcome token is `R3_P1B_T2_PREDEVICE_NOT_READY`).
`DEVICE_OPERATION=NO`. `WAIT FOR USER APPROVAL`.
