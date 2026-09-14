# R3 P1B T1 predevice readiness — MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI

Status: CI / SOURCE AUDIT / ARTIFACT PREPARATION ONLY. `DEVICE_OPERATION=NO`,
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, no boot, no host device interface
used anywhere in this round. Round details: `docs/route-r3-current-status.md`
(current state), `docs/route-r3-p1b-t0-predevice-readiness.md` (T0 candidate +
the true-device T0 record), `docs/route-r3-p1b-panic-checkpoint-isolation.md`
(PANIC30 control), `docs/route-r3-p1b-failure-isolation.md` (history).

## 1. T0 proof (predecessor, frozen)

`MAINLINE_V2_R3_P1B_T0_TRUE_DEVICE_CONTROL` was EXECUTED 2026-09-13 23:09 UTC
with explicit user approval (`EXPERIMENTAL_BOOTS=1`,
`SECOND_BOOT_FORBIDDEN=YES`). Final gate
**`MAINLINE_V2_R3_P1B_T0_REACHABILITY_PROVEN`**, Case T0-A STRONG.

| item | value |
| --- | --- |
| `T0_TOTAL` | **14.252 s** (cross-check 14.266 s) |
| programmed delay | 8.000 s |
| historical P0 reference overhead | 6.1445 s |
| `T0_PROGRAMMED_ESTIMATE` | 8.108 s → error **+0.108 s** → STRONG |
| automatic Android return | YES |
| T0 boot v3 | `8d7648e4…cfdc1`, 37380096 |
| T0 payload | `072c59e9…8fbe`, 37369041 |

Therefore `T0_CHECKPOINT_REACHED=PROVEN`,
`P1B_LARGE_PAYLOAD_TRAMPOLINE_REACHED=PROVEN`,
`TRAMPOLINE_X0_X3_SETUP_PATH_EXECUTED=YES`. This proves the instruction path
executed; it does not prove RT-D parse, primary_entry, head.S, MMU switch,
start_kernel, initramfs or /init.

## 2. Why T1

T0 proved the trampoline's own fail-closed checkpoint executed, i.e. the R1
rung. R2 — that the *unmodified* FIX8 trampoline branch actually delivers
control to the Linux `primary_entry` **address** — is still unproven. T1 is
the unique diagnostic that answers exactly that one question, and nothing
else.

Reachability ladder after this round:

| rung | statement | status |
| --- | --- | --- |
| R0 | ABL controlled payload entry | PROVEN |
| R1 | P1B large-payload trampoline T0 checkpoint | PROVEN |
| R2 | primary_entry ADDRESS reached | NOT_PROVEN |
| R3 | `__primary_switched` | NOT_PROVEN |
| R4 | `start_kernel+` | NOT_PROVEN |
| R5 | built-in initramfs | NOT_PROVEN |
| R6 | `/init` | NOT_PROVEN |

Evidence ladder unchanged: E0 PROVEN, E1 normal unmodified Mainline
`primary_entry` execution NOT_PROVEN, E2 early Mainline boot NOT_PROVEN,
E3 initramfs NOT_PROVEN, E4 `/init` NOT_PROVEN, E5 USB FROZEN.

## 3. Proof boundary

T1 is a **DESTRUCTIVE REACHABILITY DIAGNOSTIC**: it replaces `primary_entry`'s
original first instruction. A future T1 positive therefore proves ONLY
`PRIMARY_ENTRY_ADDRESS_REACHED`. It can never prove that the original
`bl record_mmu_state` was executed, so it can never prove R3, `start_kernel`,
DTB parse, MMU state, initramfs or `/init`. E1 stays NOT_PROVEN by
construction. This boundary is asserted in the source gate, in this document
and in the observer summary; the observer and the CI gates emit
`T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO` and `T1_DIAGNOSTIC_ONLY=YES` on every
path.

## 4. primary_entry re-derivation

T1 does not inherit the historical constant `0x1b1c0a0`. The offset is
re-derived this round from four independent sources that must all agree:

1. `llvm-nm` on the authoritative rebuilt `vmlinux`
   (`primary_entry − _text`),
2. `System.map` (`primary_entry − _text`),
3. the shared `kernel_gate` derivation,
4. the frozen FIX8 trampoline's own branch algebra: trampoline payload word 8
   at `0x60` decodes to `0x60 + sx(imm26,26)*4`, which must equal the derived
   offset.

Outputs: `PRIMARY_ENTRY_OFFSET=<actual>` and
`T1_PRIMARY_ENTRY_OFFSET_REDERIVED=YES`. If the re-derived value happened to
equal the historical constant it would still be reported as re-derived, never
as inherited. This round the re-derived value is
**`PRIMARY_ENTRY_OFFSET=0x1b1c0a0`** (public run 34796231232,
`PRIMARY_ENTRY_NORMAL=YES offset=0x1b1c0a0`), i.e. numerically equal to the
historical constant — reported as re-derived, and cross-checked against the
frozen trampoline's own branch algebra (`T1_TRAMPOLINE_BRANCH_TARGET`).

## 5. Original first instruction

Confirmed from three sources that must agree:

- **source**: `linux-6.6/arch/arm64/kernel/head.S`,
  `SYM_CODE_START(primary_entry)` first instruction,
- **frozen payload bytes**: the 4 bytes at the derived offset, decoded as a
  BL whose target must equal the re-derived `record_mmu_state` offset,
- **authoritative vmlinux disassembly**: `llvm-objdump -d` over the same
  address, whose first instruction must be BL to `record_mmu_state`.

Reported as `PRIMARY_ENTRY_ORIGINAL_INSN`, `PRIMARY_ENTRY_ORIGINAL_BYTES`
(little-endian hex of the word) and `PRIMARY_ENTRY_ORIGINAL_TARGET`. The gate
`T1_PRIMARY_ENTRY_ORIGINAL_INSN_SOURCES_AGREE=YES` fails the build on any
disagreement. The instruction is never hardcoded as fact.

Measured (public run 34800442025): `bl record_mmu_state`,
`PRIMARY_ENTRY_ORIGINAL_BYTES=65740094` (word `0x65740094`, top six bits
`0b100101` = BL), `PRIMARY_ENTRY_ORIGINAL_TARGET=0x1b39234`
(Image-relative `record_mmu_state`). All three sources agreed, and the
`verify`/build path compares them in one coordinate space — the vmlinux
absolute operand (`0xffff800081b39234`) is checked against `text_addr` and
then reduced to the Image-relative value before comparison.

## 6. Checkpoint placement

The checkpoint is deliberately **not** placed merely after the Image file.
Section 10 requires it outside the Linux `image_size` runtime footprint:

```
padding_base    = max(IMAGE_FILE_SIZE, IMAGE_HEADER_IMAGE_SIZE)
T1_CHECKPOINT_OFFSET = align_up(padding_base, 4)
require  T1_CHECKPOINT_OFFSET + checkpoint_len <= DTB_OFFSET
```

There is **no file_size-only fallback**. If the real geometry cannot satisfy
this, the build STOPS with an explicit reason naming the footprint, the RT-D
offset and the checkpoint size. This is a correction of the previous
prototype, which placed its gap probe at the Image file end and therefore
inside the kernel's own runtime memory footprint.

Measured (public run 34800442025): `T1_CHECKPOINT_OFFSET=0x2230000`, size 76
bytes, end `0x223004c`; `padding_base` `0x2230000` =
`max(IMAGE_FILE_SIZE 0x2189a00, IMAGE_HEADER_IMAGE_SIZE 0x2230000)`.

## 7. Outside-image_size proof

`T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES` is asserted by a gate over the actual
numbers (`checkpoint_offset >= image_size`), and independently re-checked in
the CI `verify` job. `T1_CHECKPOINT_OUTSIDE_IMAGE_FILE=YES`
(`>= IMAGE_FILE_SIZE`) is asserted too, so the checkpoint covers neither the
Image file bytes nor the BSS-bearing runtime footprint.

## 8. Zero-padding proof

`T1_CHECKPOINT_PADDING_ZERO=YES` (alias
`T1_CHECKPOINT_PADDING_REGION_SAFE=YES`): every baseline payload byte from
`padding_base` up to `DTB_OFFSET` must be zero, and the count of checked bytes
is reported. The check runs against the frozen FIX8 payload, whose identity is
gated by SHA before anything else, and is repeated independently in the
`verify` job. A negative fixture (`CHECKPOINT_BASELINE_NONZERO`) proves a
non-zero padding region is rejected.

## 9. Branch range

The AArch64 `B` immediate has a ±128 MiB reach. `T1_BRANCH_DISTANCE` is
`checkpoint_offset − primary_entry_offset`, gated to be positive, 4-byte
aligned and `< 2^27`. `T1_BRANCH_IN_RANGE=YES`. Measured: `0x713f60`
(+7,421,792 bytes ≈ 7.08 MiB). The encoded word is
re-disassembled and its operand must equal the checkpoint offset exactly, and
the same target is re-derived independently in the `verify` job from the raw
payload words.

## 10. T1 timer (CNTPCT, register-only)

The delay primitive is the T0 true-device-proven instruction sequence,
instruction-for-instruction: `msr daifset, #0xf` + `isb`, then
`mrs x9, cntfrq_el0` × 8 scaled into `x10`, `cntpct_el0` sampled with `isb`
inside a `yield` poll loop. Register-only: no stack, no memory load, no memory
store, no MMIO, no Linux timer subsystem, no earlycon, no MMU/cache/EL
manipulation. `T1_DEVICE_CANDIDATE_DELAY=8s` is enforced at compile time
(`#if (P1B_T1_DELAY) != 8 #error`).

The reuse is a verified identity, not an assertion: stripping the six
`x0`/`x1`/`x2`/`x3` handoff-setup instructions from `p1b-t0-device.S` yields
the 22-instruction body of `p1b-t1-device.S` **verbatim** (same mnemonics, same
operands, same labels). T1 therefore adds no unproven primitive; it deletes
the handoff setup it must not re-run and keeps the proven delay + reset +
terminal sequence unchanged.

## 11. PSCI reset and fail-closed termination

`movz w0, #0x0009` + `movk w0, #0x8400, lsl #16` → `smc #0`, i.e. PSCI
`SYSTEM_RESET` fid `0x84000009`, the same conduit the corrected panic audit
proved (`emergency_restart → machine_restart → do_kernel_restart → PSCI
SYSTEM_RESET`), closed under RT-D (`/psci method="smc"`). The instruction
after `smc` is `wfe`, followed by `b` back to that `wfe` — a permanent
fail-closed loop. `T1_FAIL_CLOSED_AFTER_SMC=YES`: any `smc` return (unexpected
on a healthy PSCI implementation) spins forever. There is no fall-through, no
`ret`, no branch to `primary_entry`, and no path back into normal Linux.
`gate_terminal` decodes this from the built binary and negative fixtures prove
a post-`smc` `mov`/`b` sequence is rejected.

## 12. Register discipline

`T1_CLOBBER_REGISTERS=w0/x0(PSCI FID),x9,x10,x11,x12,x13,NZCV`. Entering
`primary_entry` the boot contract holds `x0 = DTB pointer`, `x1=x2=x3=0`. T1
never resumes normal execution, so it may clobber scratch registers, but the
gate still enforces: `x1/x2/x3` are **never written**, `x0/w0` only on the two
PSCI-FID lines, and otherwise only `x9..x13`. No SP, no memory stack, no
arbitrary RAM, and **no `x0` dereference** (`T1_NO_X0_DEREFERENCE=YES`) — the
DTB is never read, only its register value is left untouched until the PSCI
FID overwrites `w0`.

## 13. Position independence

`T1_POSITION_INDEPENDENT=YES`: no hardcoded `S`, no absolute physical load
address, internal branches are PC-relative only, the timer uses system
registers, PSCI uses register arguments only. Readelf must show
`T1_RUNTIME_RELOCATIONS=0` (no `R_AARCH64_*`, no GOT, no ABS, no dynamic
relocations). T1 carries no data literal at all (unlike T0, which needed the
`dtb_rel` quad), so its layout is trivially invariant.

## 14. Trampoline identity (hard gate)

The T1 payload keeps the FIX8 trampoline byte-identical:
`T1_TRAMPOLINE_IDENTICAL_TO_FIX8=YES`,
sha256 `362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623`.
Both the frozen payload slice and the composed T1 payload are hashed, the
branch word 8 is decoded and must still target `primary_entry`, and a
literal-word disassembly record of the 48 frozen bytes is emitted. The real
T1 execution chain is therefore:

```
ABL -> FIX8 code0 -> FIX8 trampoline -> FIX8 normal branch
    -> primary_entry address -> T1 diagnostic branch -> T1 checkpoint
```

A modified trampoline is a hard NO DEVICE READY (fixture
`TRAMPOLINE_MODIFIED`).

## 15. RT-D identity

`T1_RT_D_IDENTITY=YES`: the trailer at `DTB_OFFSET` `0x2380000` is the frozen
FIX8 RT-D,
sha256 `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`,
144593 bytes, FDT magic `d00dfeed`, `panic=5`. The PANIC30 RT-D (`panic=30`)
is NOT used. The trailer is re-hashed from the composed payload and compared
byte-for-byte with the frozen download.

## 16. `/init` and initramfs identity

Even though T1 can never reach them (its first checkpointed action is a
branch away from normal execution), single-variable discipline is kept:
`/init` `f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d`
and initramfs
`02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3` are
byte-identical to the frozen FIX8 pair, gated as
`T1_INIT_IDENTITY=YES` / `T1_INITRAMFS_IDENTITY=YES` against a fresh build
from the pinned Linux base `8b73de7da85fde281a385e0b26eda9bffd3ca477`
(6.6.156).

## 17. image_size re-read

Historical material recorded both `0x2230000` and `0x2231000`. This round
inherits neither. `IMAGE_HEADER_IMAGE_SIZE` is read from the authoritative
FIX8 Image header — the frozen payload's own header field, over bytes whose
SHA is gated against `4f34eabf…cceb41` — and cross-checked against the freshly
rebuilt Image header, which must agree (otherwise: baseline drift, STOP).

Measured this round (public run 34796231232): `IMAGE_FILE_SIZE = 35166720`
(`0x2189a00`), `IMAGE_HEADER_IMAGE_SIZE = 0x2230000` (35848192),
`DTB_OFFSET = 0x2380000`. The rebuilt Image header reads `code0 0xfa405a4d`,
`code1 0x146c7027`, `text_offset 0x0`, `image_size 0x2230000`,
`flags 0xa`, `file_size 0x2189a00`. All three tokens
(`IMAGE_FILE_SIZE`, `IMAGE_HEADER_IMAGE_SIZE`, `DTB_OFFSET`) are printed
before any checkpoint offset is chosen, and the `verify` job re-reads the
header independently from the uploaded payload.

**Rebuilt-Image byte identity is explicitly NOT claimed and NOT gated.**
`T1_REBUILT_IMAGE_BYTE_IDENTICAL=NO`. Measured (public run 34797876016): the
rebuilt Image and the frozen payload's Image prefix differ in **6,767,112**
bytes (`T1_REBUILT_IMAGE_DIFF_BYTES`) out of 35,166,720 — while `image_size`
(`0x2230000`), `file_size` (`35166720`) and the `primary_entry` offset
(`0x1b1c0a0`) are all identical. `6,767,112` is within ~26.8 KB of
`file_size − primary_entry` (`6,740,320`), i.e. the divergence is essentially
the whole region from just below `primary_entry` to the end of the Image.

The decisive point is that **the layout did not move**: `image_size`,
`file_size`, `primary_entry` and `record_mmu_state` are all unchanged, and the
rebuilt Image's own `code1` branch algebra still lands exactly on
`0x1b1c0a0` (`P1B_CODE1_B_PRIMARY_ENTRY=PASS`). A byte shift would have moved
those; nothing moved. The differing bytes are therefore in build-stamp
dependent data, not in relocated code.

Because a byte-level comparison cannot be stated as an invariant for a rebuilt
kernel, T1 gates **semantic identity instead of byte identity**:

- header `image_size` and file size equality (`0x2230000` / `35166720`),
- `primary_entry` and `record_mmu_state` offsets agreeing across `llvm-nm`,
  `System.map`, `kernel_gate`, and the frozen payload's own BL decode,
- `T1_PRIMARY_ENTRY_ORIGINAL_INSN_SOURCES_AGREE=YES` — the disassembled first
  instruction at `primary_entry` in the authoritative `vmlinux` is BL to
  `record_mmu_state` at the same address the frozen bytes and head.S give.

The byte statistics (`T1_REBUILT_IMAGE_FIRST_DIFF_OFFSET`,
`T1_REBUILT_IMAGE_DIFF_BYTES`, split into
`DIFF_BEFORE_PRIMARY_ENTRY` / `DIFF_FROM_PRIMARY_ENTRY`, and the 16-byte
`T1_REBUILT_IMAGE_CODE_IDENTITY_AT_PRIMARY_ENTRY` probe) are **reported, never
gated**.

This is exactly why T1 is COMPOSED from frozen bytes rather than rebuilt: the
frozen payload is the only artefact whose bytes can be gated, and the rebuild's
sole job is derivation plus semantic confirmation.

## 18. Payload geometry and composition

T1 is COMPOSED, not rebuilt from scratch: the frozen FIX8 payload bytes with
exactly two regions replaced. Length, `DTB_OFFSET`, RT-D offset, boot
`kernel_size` and boot size are identical to FIX8
(`T1_PAYLOAD_SIZE_IDENTICAL=YES`, `T1_BOOT_SIZE_IDENTICAL=YES`,
`T1_GEOMETRY_GATES=PASS`, expected boot 37380096).

## 19. Payload diff attribution

`T1_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY`.
The byte-diff gate allows exactly two families and rejects everything else,
and also rejects an *empty* diff in either region (a lost patch):

- region A — the 4 bytes at `primary_entry` (`bl record_mmu_state` →
  `b T1_CHECKPOINT`),
- region B — the T1 checkpoint bytes in the zero padding.

`T1_DIFF_BYTE_COUNT` and `T1_DIFF_RANGES` are reported, and the byte budget is
asserted to equal `A + B` in the private pack job. Measured (public run
34800442025): `T1_DIFF_BYTE_COUNT=75` (`A=4`, `B=71`),
`T1_DIFF_RANGES=[[0x1b1c0a0,0x1b1c0a4), [0x2230000,0x223004c)]`,
`T1_PAYLOAD` `3e654ee5…f0fb`, 37369041 bytes — size identical to the frozen
FIX8 payload. `T1_TRAMPOLINE_IDENTICAL_TO_FIX8`
and `RT_D_TRAILER_IDENTICAL=YES` are re-asserted over the composed payload.

## 20. Runtime semantic delta

Exactly two runtime semantic changes versus the frozen FIX8 candidate:

A. `primary_entry`'s original first instruction becomes `b T1_CHECKPOINT`,
B. the original deterministic zero padding gains the T1 diagnostic code.

Everything else is identical. `T1_RUNTIME_SEMANTIC_DELTA=
PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY`. T1 is
`T1_DIAGNOSTIC_ONLY=YES` and `T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO`; a future
T1 positive must never be reported as "Mainline booted normally".

## 21. Private packaging and public/private split

PUBLIC (this repository, CI-gated, no device image ever emitted): source
audit, assembly, ELF, disassembly records, raw T1 payload, diff report,
fixtures, observer fixtures. PRIVATE (repo `ChuenSan/thyme-mainline-private-ci`
only): the OEM-derived M5D boot v3 envelope and the final T1 boot image. The
private pack job splices the public T1 payload into the exact M5D envelope
(`4db8151b…85e63`, private run 34487382191) via `p1b-build.py --mode
splice-boot`, which rewrites ONLY the `kernel_size` header field (bytes
8..12), then runs `--mode t1-pack-gates` and re-verifies identity without
re-packing.

## 22. Observer, negative results, timing windows and the T2 route

**Observer.** `scripts/r3-p1b/observe-r3-p1b-t1.py` (derived from the
device-proven T0 observer) accepts ONLY the exact T1 boot by full-SHA
`R3_T1_SHA256` plus size 37380096 and refuses the frozen wrong boots
(T0 `8d7648e4…`, FIX8 `ba3d8789…`, PANIC30 `ea50e8b3…`, old broken INIT8,
entry-state probe) with `T1_OBSERVER_MISBOOT_REFUSED` **before any device
interaction**, with no image substitution and no retry.
`observer-t1-fixtures.py` proves the AST deadlock gate, every misboot refusal,
the exact-match accept path, decoder cases A–F and the summary path — all
green in CI. Fixture coverage: 12 negative fixtures against the real gate
functions.

**Matched-control baseline.** The primary reference is the T0 true-device
total: `T0_REFERENCE_TOTAL = 14.252 s`. Both rounds carry a 37 MiB-class P1B
payload, the same 8 s CNTPCT delay and the same PSCI reset; the only
difference is the checkpoint position (trampoline end vs primary_entry
address). T1-vs-T0 is therefore a strictly better control than the P0
overhead decoder.

**Primary metric.** `T1_TOTAL = RETURNED_ANDROID_KERNEL_START − T_BOOTING_OKAY`
and `T1_MINUS_T0 = T1_TOTAL − 14.252 s`. Triple condition required together:

- STRONG: `|T1_MINUS_T0| <= 1.000 s`, or SUPPORTED: `<= 2.000 s`,
- `T1_TOTAL < 20.000 s`,
- `AUTOMATIC_ANDROID_RETURN=YES`.

`T1_PROGRAMMED_ESTIMATE = T1_TOTAL − 6.1445 s` (expected ≈ 8 s) is a
**SECONDARY** cross-check only; it never replaces the matched control.

**Meanings.** STRONG records `T1_REACHABILITY_SIGNATURE=STRONG`,
`PRIMARY_ENTRY_ADDRESS_REACHED=PROVEN`, `R2=PROVEN`, while still recording
`NORMAL_PRIMARY_ENTRY_FIRST_INSTRUCTION_EXECUTED=NOT_PROVEN` and E1
NOT_PROVEN. SUPPORTED records `R2=STRONGLY_SUPPORTED` — never PROVEN without
additional independent direct evidence.

**Negative-result boundary.** A 23–26 s automatic return records
`T1_SIGNATURE_NOT_OBSERVED` and narrows the investigation to the interval
after T0 and before the primary_entry checkpoint; it must NOT be written as
"primary_entry not reached". An early return outside the supported window
records `T1_EARLY_RETURN_TIMING_MISMATCH` — an early return alone never proves
primary_entry was reached. Stable Fastboot records `T1_STABLE_FASTBOOT`;
> 120 s without return records `T1_NO_RETURN`; manual recovery elapsed time is
never timing evidence. Every negative sets `T1_NOT_REACHED_LICENSE=NO` and
routes to `T1_FAILURE_ISOLATION_CI` — never automatically to T2.

**Success route.** T2 stays `DESIGNED` and is NOT device ready this round. A
T1 STRONG (or sufficiently supported) result routes to
`MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI`, which must separately audit
MMU state, VA/PA, stack, timer access, PSCI and checkpoint placement.

## 23. CI structure, gates and final gate

Public `thyme-r3-p1b-t1-predevice.yml`: source-audit (actionlint +
py_compile + source gate + constraints) → t1-build (LLVM 18.1.3, pinned
Linux base, frozen RT-D run 34678001413 and FIX8 payload run 34741153230 with
pinned SHAs, authoritative rebuild, primary_entry re-derivation, original
instruction confirmation, image_size re-read, checkpoint build + placement +
padding gates, frozen-byte patch + diff attribution, negative fixtures,
matched-control decoder fixtures, observer fixtures) → verify (independent
re-read of the uploaded artifact: SHA recheck, image_size re-read from the
header, checkpoint-outside-image_size, padding-zero in the frozen baseline,
diff attribution, trampoline byte identity, branch target algebra, fail-closed
terminal decode, RT-D identity, geometry). No `*.img` may exist anywhere in
this repository.
Private workflow (staged at `artifacts/p1b-t1-private-workflow-staging.yml`):
`t1-pack` (M5D splice + pack gates + size cross-check + boot SHA record) and
`t1-identity-reverify` (re-hash only, never re-pack).

Gate set (all must be green): `T1_BUILD_GATES=PASS`,
`T1_BASELINE=FROZEN_FIX8`, `T1_PRIMARY_ENTRY_OFFSET_REDERIVED=YES`,
`T1_PRIMARY_ENTRY_ORIGINAL_INSN=bl record_mmu_state`,
`T1_PRIMARY_ENTRY_ORIGINAL_INSN_SOURCES_AGREE=YES`,
`IMAGE_HEADER_IMAGE_SIZE_REDERIVED=YES`,
`T1_CHECKPOINT_OUTSIDE_IMAGE_FILE=YES`,
`T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE=YES`, `T1_CHECKPOINT_BEFORE_RTD=YES`,
`T1_CHECKPOINT_PADDING_ZERO=YES`, `T1_CHECKPOINT_PADDING_REGION_SAFE=YES`,
`T1_BRANCH_IN_RANGE=YES`, `T1_DEVICE_CANDIDATE_DELAY=8s`,
`T1_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY`,
`T1_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC`, `T1_FAIL_CLOSED=YES`,
`T1_NO_STACK=YES`, `T1_NO_MEMORY_WRITES=YES`, `T1_NO_X0_DEREFERENCE=YES`,
`T1_POSITION_INDEPENDENT=YES`, `T1_RUNTIME_RELOCATIONS=0`,
`T1_RUNTIME_SEMANTIC_DELTA=PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY`,
`T1_TRAMPOLINE_IDENTICAL_TO_FIX8=YES`, `T1_RT_D_IDENTITY=YES`,
`T1_INIT_IDENTITY=YES`, `T1_INITRAMFS_IDENTITY=YES`,
`T1_PAYLOAD_DIFF_ATTRIBUTED=PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY`,
`T1_PAYLOAD_SIZE_IDENTICAL=YES`, `T1_BOOT_SIZE_IDENTICAL=YES`,
`T1_GEOMETRY_GATES=PASS`, `T1_NEGATIVE_FIXTURES=PASS`,
`T1_DECODER_FIXTURES=PASS`, `T1_OBSERVER_FIXTURES=PASS`,
`T1_DIAGNOSTIC_ONLY=YES`, `T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO`,
`READY_FOR_DEVICE=NO`.

## 24. Final gate and approval semantics

- `READY_FOR_R3_P1B_T1_DEVICE_CONTROL` — every gate above green, private pack
  green, T1 boot identity frozen and recorded, observer fixtures green. This
  authorises PREPARATION ONLY. The single T1 device run remains forbidden
  until the user separately approves
  `MAINLINE_V2_R3_P1B_T1_TRUE_DEVICE_CONTROL`.
- `R3_P1B_T1_PREDEVICE_NOT_READY` — any gate red; route back to
  `T1_FAILURE_ISOLATION_CI` for the failing dimension.

T2 remains `DESIGNED` and is not device ready. `T1_TOTAL` / `T1_MINUS_T0`
windows are preregistered above and must not be widened after observing data.
