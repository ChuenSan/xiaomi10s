# R3 P1B T0 predevice readiness — MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI

Status: CI / SOURCE AUDIT / ARTIFACT PREPARATION ONLY. `DEVICE_OPERATION=NO`,
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, no boot, no fastboot/adb anywhere
in this round. Round details: `docs/route-r3-current-status.md` (current
state), `docs/route-r3-p1b-panic-checkpoint-isolation.md` (PANIC30 control),
`docs/route-r3-p1b-failure-isolation.md` (history).

## 1. Round identity and goal

`MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI` elevates the previous round's
`CHECKPOINT_T0_CI=PASS` prototype (public run 34754072600) into the unique,
frozen, explainable, identity-gateable **T0-8 true-device diagnostic
candidate**. The deliverable is a CI-green artifact set + a host observer
ready for a future single authorized device boot; the device round itself is
NOT part of this round and requires separate user approval.

## 2. Scope and forbidden operations

Forbidden this round: T0/T1/T2 true-device boots, PANIC30 second boot, FIX8
rerun, FIX24, M5N, copydown, USB, UFS, network, any partition write, any
slot-A touch. Local builds are forbidden (`GITHUB_ACTIONS != "true"` guard in
every builder); all assembly/link/inspection/validation runs in GitHub
Actions only. Boot v3 packing is private-GHA-only; the public workflow never
emits `*.img`.

## 3. Inputs and frozen identity (no kernel rebuild)

| item | value |
| --- | --- |
| frozen FIX8 payload | `4f34eabf…cceb41`, 37369041 bytes (public run 34741153230) |
| frozen RT-D trailer | `48497432…f327`, 144593 bytes (public run 34678001413) |
| frozen FIX8 trampoline | `362d9c6e…c623`, 48 bytes at payload [0x40, 0x70) |
| frozen FIX8 boot (forbidden) | `ba3d8789…2ab5`, 37380096 |
| PANIC30 boot (forbidden) | `ea50e8b3…64b1`, 37380096 |
| old INIT8 boot (forbidden) | `e6ac6308…1264` |
| entry-state probe boot (forbidden) | `cb61889a…e82c` |
| Linux base | `8b73de7da85fde281a385e0b26eda9bffd3ca477` (6.6.156) |
| image header `image_size` | `0x2230000`; DTB_OFFSET `0x2380000` |
| primary_entry (frozen payload) | `0x1b1c0a0` |

The T0 payload is COMPOSED, not rebuilt: frozen FIX8 payload bytes with ONLY
the trampoline checkpoint region `[0x40, 0x40+112)` replaced. The kernel
Image, initramfs, /init and RT-D trailer bytes are bit-identical to FIX8, so
`T0_PAYLOAD_SIZE_IDENTICAL=YES`, `T0_BOOT_KERNEL_SIZE_IDENTICAL=YES`,
`T0_BOOT_SIZE_IDENTICAL=YES` (37380096) hold by construction and are re-gated
in CI.

## 4. Prototype fall-through audit (mandatory, section 14)

The prior CI prototype `scripts/r3-p1b/p1b-t0-trampoline.S` HAS a failsafe
fall-through path: on smc return it restores `x0/x1/x2/x3` and branches to
primary_entry (`mov x15, x0` / `mov x0, x15` / `b_primary`). It is therefore
NOT device-ready. This round regenerates a fail-closed T0 instead. The
prototype source is deliberately RETAINED unchanged so the audit stays
verifiable: the source gate asserts its fall-through tokens remain, and the
device source gate FORBIDS them (`T0_PROTOTYPE_FALLTHROUGH_AUDIT=
DEVICE_PROTOTYPE_NOT_READY_FAIL_CLOSED_REGENERATED`).

## 5. Fail-closed T0 device candidate (`p1b-t0-device.S`)

Single runtime semantic change
`T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY`:

    reach T0 (ABL executed payload offset 0x40, code1 = b 0x40)
      -> DAIF mask + isb
      -> x0 = S + 0x2380000 (RT-D trailer), x1 = x2 = x3 = 0
      -> 8s delay, CNTPCT register-only
      -> PSCI SYSTEM_RESET (fid 0x84000009, smc #0)
      -> on ANY smc return: wfe loop forever (NO restore, NO
         primary_entry continuation, no fall-through path exists)

## 6. Checkpoint position

`T0_AFTER_X0_X3_SETUP=YES` and `T0_BEFORE_PRIMARY_ENTRY_BRANCH=YES`. The
checkpoint runs after the full handoff setup (DAIF mask, `adr/ldr/add` x0 ->
RT-D, `x1=x2=x3=0`) and replaces the frozen handoff's final `branch
primary_entry` slot; no branch to primary_entry exists in the T0 device
source. Evidence: the frozen `b_primary` word at payload `0x60` is decoded
by algebra (word[8] of the frozen trampoline, target `0x60 + sx(imm26,26)*4
== 0x1b1c0a0`) from the frozen payload bytes themselves, plus a literal-.inst-word
ELF disassembly record (frozen 48 bytes reassembled as .inst words,
byte-identical, disassembled by the pinned llvm-objdump); the T0 device trampoline contains no branch leaving
`[0x40, 0xB0)`.

## 7. Timer primitive: CNTPCT register-only

`cntfrq_el0` scaled into `x10` (8 s), `cntpct_el0` sampled with `isb` before
and inside a `yield`-poll loop. No stack, no memory writes, no timer
subsystem, no earlycon, no MMU/cache/EL manipulation
(`T0_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY`, `T0_NO_STACK=YES`,
`T0_NO_MEMORY_WRITES=YES`). `T0_DEVICE_CANDIDATE_DELAY=8s` is enforced at
compile time (`#if (P1B_T0_DELAY) != 8 #error`).

## 8. Reset primitive: PSCI SYSTEM_RESET, fail-closed

`movz w0, #0x0009; movk w0, #0x8400, lsl #16` -> `smc #0` — the same
conduit the corrected panic audit proved for panic=30 restarts
(`emergency_restart -> machine_restart -> do_kernel_restart -> PSCI
SYSTEM_RESET`), closed under RT-D (`/psci method="smc"`).
`T0_FAIL_CLOSED_AFTER_RESET_RETURN=YES`: the instruction after `smc` is
`wfe`, followed by `b` back to that `wfe` (decoded from the built binary by
`gate_terminal`; negative fixtures prove a post-smc `mov` sequence is
rejected). There is no restore, no primary_entry continuation.

## 9. Register discipline

`T0_CLOBBER_REGISTERS=x0/w0(PSCI FID),x9,x10,x11,x12,x13,NZCV`. The gate
enforces: before the `mov x3, xzr` boundary only `x0,x1,x2,x3,x9` are
written; after it only `x9..x13`, plus `w0` exclusively on the two PSCI-FID
lines. `x1/x2/x3` hold the boot contract values into the checkpoint and are
never re-written. Stores (any `str*`/`stp*`/`adrp`), `bl/blr`, `eret`,
`sctlr`, `daifclr`, stack pointer and `x29/x30` are all forbidden and
negatively fixture-tested.

## 10. Position independence and relocations

`T0_POSITION_INDEPENDENT=YES`: PC-relative only (`adr`/`ldr`-literal to the
`dtb_rel` literal inside the same region), no absolute S reference, no load
address assumption. Two-pass assembly (dtb_rel=0 then real value) proves the
layout is invariant; `T0_RUNTIME_RELOCATIONS=0` is gated on readelf output
(no `R_AARCH64_*`). The `x0` algebra is re-proven per build:
`S + 0xA8 + dtb_rel(0x237FF58) == S + 0x2380000`.

## 11. Composition method (frozen-byte payload patch)

`cmd t0` in `scripts/r3-p1b/p1b-t0-predevice.py`: re-verify frozen FIX8
payload/RT-D identity from the authoritative artifacts -> build the 112-byte
T0 trampoline -> patch it into payload bytes `[0x40, 0xB0)` -> full gate
suite -> emit `thyme-r3-p1b-t0-kernel-payload.bin` + diff report + fixtures
+ report + manifest + gates. The setup-words gate proves the first 8
trampoline words differ from the frozen ones ONLY at indices `[2, 3]` (the
two PC-relative `dtb_rel` references).

## 12. Payload diff attribution

`T0_PAYLOAD_DIFF_ATTRIBUTED=CHECKPOINT_REGION_ONLY`: the byte-diff gate
rejects any differing byte outside `[0x40, 0xB0)`, and rejects an empty diff
(lost patch). `DIFF_ATTRIBUTION=CHECKPOINT_REGION_ONLY` is recorded in
`t0-payload-diff-report.txt` with first/last diff offsets and the RT-D
trailer re-hash.

## 13. Geometry identity

`T0_DTB_OFFSET=0x2380000` (from `image_size 0x2230000`, independent formula
re-derived in the verify job), payload 37369041, boot size estimate
37380096, 2 MiB residue rule, 16 MiB capacity margin — all identical to
frozen FIX8 (`T0_GEOMETRY_GATES=PASS`); `RT-D` trailer sha/size exact
(`T0_RT_D_IDENTITY=YES`).

## 14. Boot v3 pack (private GHA only)

The private workflow (staged at
`artifacts/p1b-t0-private-workflow-staging.yml`) splices the public T0
payload into the exact M5D envelope (boot `4db8151b…85e63`, private run
34487382191) via `p1b-build.py --mode splice-boot` (rewrites ONLY the
`kernel_size` header field, bytes 8..12) and validates with `--mode
t0-pack-gates`: kernel == T0 payload, ramdisk/cmdline/os_version/reserved ==
M5D, header diff subset `bytes 8..12`, embedded trampoline sha exact, RT-D
trailer exact, geometry + capacity. Artifact: `thyme-r3-p1b-t0-boot`; boot
SHA256 recorded in the run summary and frozen into the round record.

## 15. T0 observer (identity-gated host observer)

`scripts/r3-p1b/observe-r3-p1b-t0.py` derives from the device-proven INIT8
observer (same event loop, locking, fastboot stdout timing). Identity gate:
`R3_T0_BOOT_IMG` + full-SHA `R3_T0_SHA256` (size 37380096) — misboot
refusal `T0_OBSERVER_MISBOOT_REFUSED` against the four frozen wrong boots
(FIX8 / PANIC30 / old INIT8 / entry-state probe) BEFORE any fastboot
interaction. `FASTBOOT_BOOT_ONLY`, `SECOND_BOOT_FORBIDDEN`; no flash, no
erase, no set_active. Observer fixtures (`observer-t0-fixtures.py`) prove
the AST deadlock gate, the misboot refusals, and all summary scenarios
including the no-KeyError legacy state.

## 16. Preregistered supporting decoder

Primary timing product `T0_BOOTING_TO_RETURNED_KERNEL_START` (BOOTING_OKAY
-> returned Android kernel start). Supporting decoder (NOT a strict
invariant — T0 carries the full 37 MiB-class payload, so windows are wider
than the P0 probe's ±0.75 s): `T0_PROGRAMMED_ESTIMATE = T0_TOTAL − 6.1445`
(P0 reference overhead `6.1445` s); `T0_WINDOW`: STRONG ≤ ±1.5 s, SUPPORTED
≤ ±3.0 s, else OUTSIDE; `T0_EARLY_RETURN_CLASS`: `T0_TOTAL < 20.0` s
(references: frozen `FIX8_TOTAL 23.852 s`, `PANIC30_TOTAL 26.289 s`).
Triple condition for a positive
(`T0_REACHABILITY_SIGNATURE=STRONG|SUPPORTED`): timer window AND early
return class AND `RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN`. A positive routes
to `MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI` (still CI-only; no
checkpoint device run is authorized by it).

## 17. Negative result semantics

A negative is `T0_SIGNATURE_NOT_OBSERVED=YES` and NEVER licenses
`T0_NOT_REACHED` / `NO_LINUX_ENTRY` (the T0 checkpoint may simply not have
been reached — absence of the signature is not evidence about entry).
`T0_NOT_REACHED_LICENSE=NO` is emitted on every negative and every
non-timing path; the mandated next step is `T0_FAILURE_ISOLATION_CI`.
Recovery classes: automatic Android return (the only positive path),
stable fastboot (Case C, record only), no-return/manual recovery (Case D,
elapsed excluded from timing), boot-not-accepted (Case E, stop, no image
swap retry).

## 18. Negative fixtures (12)

`T0_BEFORE_X0_SETUP`, `T0_AFTER_PRIMARY_ENTRY`, `WRONG_DELAY`,
`WRONG_PSCI_FID`, `MISSING_SMC`, `FALLTHROUGH_AFTER_SMC`, `STACK_USE`,
`MEMORY_STORE`, `ABSOLUTE_ADDRESS`, `RELOCATIONS`, `GEOMETRY_CHANGED`,
`RT_D_CHANGED` — every fixture feeds a mutated input to the REAL gate
functions and must be REJECTED with the expected label
(`T0_NEGATIVE_FIXTURES=PASS`).

## 19. Decoder fixtures (13)

STRONG 14.2 s / 12.7 s; SUPPORTED 16.5 / 17.1 / 11.2 s; OUTSIDE 17.2 / 11.0
s; `EARLY_BUT_OUTSIDE_8P0S` proves the early-return class alone does NOT
equal T0 reached; LATE 24.0 s and the PANIC30-class 26.289 s; non-Android
returns (stable fastboot, no-return) and UNKNOWN kind all yield
NOT_OBSERVED with `T0_FAILURE_ISOLATION_CI` next
(`T0_DECODER_FIXTURES=PASS`).

## 20. CI workflow structure

Public `thyme-r3-p1b-t0-predevice.yml`: source-audit (actionlint +
py_compile + source gate + constraints) -> t0-build (pinned LLVM 18.1.3;
downloads frozen RT-D run 34678001413 + FIX8 payload run 34741153230 with
pinned SHAs; builds T0; runs gates + negative + decoder + observer fixtures;
uploads `thyme-r3-p1b-t0`) -> verify (independent re-verification: artifact
sha recheck, checkpoint-region-only diff vs frozen FIX8, RT-D trailer
identity, fail-closed terminal structure decoded from raw words, branch
containment, geometry). Private workflow: pack + identity reverify jobs as
in section 14.

## 21. Gate verdicts

CI gate set (all required green): `T0_BUILD_GATES=PASS`,
`T0_BASELINE=FROZEN_FIX8`, `T0_AFTER_X0_X3_SETUP=YES`,
`T0_BEFORE_PRIMARY_ENTRY_BRANCH=YES`, `T0_DEVICE_CANDIDATE_DELAY=8s`,
`T0_TIMER_PRIMITIVE=CNTPCT_REGISTER_ONLY`,
`T0_RESET_PRIMITIVE=PSCI_SYSTEM_RESET_0x84000009_SMC`,
`T0_FAIL_CLOSED_AFTER_RESET_RETURN=YES`, `T0_NO_STACK=YES`,
`T0_NO_MEMORY_WRITES=YES`, `T0_POSITION_INDEPENDENT=YES`,
`T0_RUNTIME_RELOCATIONS=0`,
`T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY`,
`T0_PAYLOAD_DIFF_ATTRIBUTED=CHECKPOINT_REGION_ONLY`,
`T0_PAYLOAD_SIZE_IDENTICAL=YES`, `T0_BOOT_KERNEL_SIZE_IDENTICAL=YES`,
`T0_BOOT_SIZE_IDENTICAL=YES`, `T0_RT_D_IDENTITY=YES`,
`T0_GEOMETRY_GATES=PASS`, `T0_NEGATIVE_FIXTURES=PASS`,
`T0_DECODER_FIXTURES=PASS`, `T0_PROTOTYPE_FALLTHROUGH_AUDIT=
DEVICE_PROTOTYPE_NOT_READY_FAIL_CLOSED_REGENERATED`, `READY_FOR_DEVICE=NO`.

## 22. Final gate and approval semantics

- `READY_FOR_R3_P1B_T0_DEVICE_CONTROL` — every gate above green, private
  pack green, T0 boot identity frozen and recorded, observer fixtures green.
  This authorizes PREPARATION ONLY; the actual single T0 device boot remains
  forbidden until the user separately approves
  `MAINLINE_V2_R3_P1B_T0_TRUE_DEVICE_CONTROL`.
- `R3_P1B_T0_PREDEVICE_NOT_READY` — any gate red; route back to
  `T0_FAILURE_ISOLATION_CI` for the failing dimension.
- Evidence ladder unchanged by this round: E0 PROVEN; E1 normal entry,
  E2 early boot, E3 initramfs reached, E4 /init executed all NOT_PROVEN;
  E5 USB FROZEN. A future T0 positive (STRONG/SUPPORTED) would upgrade the
  checkpoint dimension only (ABL loaded and executed the large P1B payload
  at its entry point) and would NOT by itself upgrade E3/E4.

## 23. TRUE DEVICE T0 RESULT (EXECUTED 2026-09-13 UTC)

`MAINLINE_V2_R3_P1B_T0_TRUE_DEVICE_CONTROL` EXECUTED with explicit user
approval (the one authorized `fastboot boot`, `EXPERIMENTAL_BOOTS=1`,
`SECOND_BOOT_FORBIDDEN=YES`). mem0 read at round start and again before
`adb reboot bootloader`. Final gate: **`MAINLINE_V2_R3_P1B_T0_REACHABILITY_PROVEN`**
(Case T0-A STRONG).

Artifact identity re-verified from the authoritative private pack run
34769675932 (`thyme-r3-p1b-t0-boot`, identity reconfirm 34769764343;
public commit `943519bab0a985a3e667d0971d0c35109256bb49`, round record
`b5d854b`) BEFORE any device interaction. Full-SHA table all MATCH:

| item | value |
| --- | --- |
| T0 boot v3 | `8d7648e4c2713aab8bf27b9f53ffad861b21ff593a23c684631598f62e2cfdc1`, 37380096 |
| T0 payload | `072c59e9d65f3c8a7ff83b50254774275d3e94479c80213afbf8eb38ac328fbe`, 37369041 |
| T0 trampoline (embedded `[0x40,0xB0)`) | `92fcb46ebae2c8985d5b55b136a544b288ae7d23805d86934c92097b005d0e72`, 112 |
| RT-D trailer at DTB_OFFSET | `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`, 144593, FDT magic `d00dfeed` |
| DTB_OFFSET | `0x2380000` |
| vs frozen FIX8 payload `4f34eabf…cceb41` | size identical, RT-D byte-identical, diff = 73 bytes all inside `[0x49,0xab] ⊂ [0x40,0xB0)` → `T0_PAYLOAD_DIFF_ATTRIBUTED=CHECKPOINT_REGION_ONLY` |

Checkpoint semantics re-confirmed from the embedded words before boot:
w0 `msr daifset,#0xf`, w1 `isb`, w2/w3 `adr x0,dtb_rel` / `ldr x9,dtb_rel`
(PC-relative, quad `0x237ff58`), w4 `add x0,x0,x9` (x0 = S + `0x2380000`),
w5-w7 `mov x1/x2/x3,xzr` — then w8+ checkpoint (`mrs cntfrq_el0`,
`movz x10,#8`, CNTPCT poll, `movz w0,#9` + `movk w0,#0x8400,lsl#16` =
PSCI `0x84000009`, `smc #0`, `wfe; b wfe` fail-closed, `dtb_rel` quad
`0x237ff58:00000000`). `T0_AFTER_X0_X3_SETUP=YES`,
`T0_BEFORE_PRIMARY_ENTRY=YES`, no primary_entry branch exists
(FIX8 word8 `b 0x1b1c0a0` slot replaced), `T0_FAIL_CLOSED=YES`,
relocations 0.

Preflight: Android A (`slot_suffix=_a`, `boot_completed=1`, root magisk
uid=0, Stock 4.19.157-perf); Current B read-only hashes M5D `4db8151b…85e63`
/ M5H `2d58ef94…` + `5d98f207…` / M5M-B dtbo `c5a355b9…aba8` ALL MATCH.
Bootloader: product=thyme, unlocked=yes, current-slot=a,
snapshot-update-status=none, battery-soc-ok=yes (4360 mV); slot a
retry=6/unbootable=no/successful=yes. Observer identity gate
`ARTIFACT_IDENTITY MATCH` fired before any fastboot interaction.

Fastboot acceptance: `Sending 'boot.img' (36504 KB) OKAY [ 1.010s]`,
`Booting OKAY [ 0.220s]`. Timeline (UTC):

| event | time |
| --- | --- |
| T_COMMAND_START | 2026-09-13T23:09:32.484Z |
| T_SENDING_OKAY | 2026-09-13T23:09:33.521Z |
| T_BOOTING_OKAY | 2026-09-13T23:09:33.741Z |
| T_FASTBOOT_DISAPPEAR | 2026-09-13T23:09:35.172Z |
| T_USB_NONE | 2026-09-13T23:09:35.295Z |
| T_USB_FIRST_REENUM | 2026-09-13T23:09:55.173Z |
| T_ADB_FIRST_SEEN | 2026-09-13T23:09:55.474Z |
| RETURNED_ANDROID_KERNEL_START | 2026-09-13T23:09:47.994Z (uptime 7.48; cross-check 23:09:48.007) |
| T_BOOT_COMPLETED | 2026-09-13T23:10:06.056Z |

Timing: primary `T0_TOTAL` = `T0_BOOTING_TO_RETURNED_KERNEL_START` =
**14.252 s** (cross-check 14.266 s). Supporting decoder:
`T0_PROGRAMMED_ESTIMATE = 14.252 − 6.1445 = 8.108 s` vs programmed 8.000 s
→ error **+0.108 s** → `T0_WINDOW=STRONG` (≤ ±1.5 s);
`T0_EARLY_RETURN_CLASS_MATCH=YES` (14.252 < 20);
`RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN` (bootreason=bootloader, slot `_a`,
Stock 4.19.157-perf, no stable Fastboot, no transient, no manual recovery).
Triple condition met → **Case T0-A STRONG**:
`T0_REACHABILITY_SIGNATURE=STRONG`, `T0_CHECKPOINT_REACHED=PROVEN`,
`P1B_LARGE_PAYLOAD_TRAMPOLINE_REACHED=PROVEN`,
`TRAMPOLINE_X0_X3_SETUP_PATH_EXECUTED=YES`. This proves the instruction
path executed; it does NOT prove RT-D parse, primary_entry, head.S
completion, MMU switch, start_kernel, initramfs or /init — E1-E4 remain
NOT_PROVEN. Elapsed: BOOTING→ADB 21.732 s, BOOTING→boot_completed 32.315 s.

Post-test: `ANDROID_A_RESTORED=YES`; pstore empty (auxiliary only, NOT
negative evidence — the T0 proof is the timing signature);
`CURRENT_B_UNCHANGED_AFTER_T0=YES` (post-test hashes identical to pre-test).
Constraints held: `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `SET_ACTIVE=NO`,
no flash/erase/format, T1/T2/FIX24/M5N not executed.

Reachability ladder after this round: R0 ABL controlled payload entry
PROVEN; R1 P1B large-payload trampoline T0 checkpoint PROVEN; R2 normal
primary_entry NOT_PROVEN; R3 post-head.S/__primary_switched NOT_PROVEN;
R4 start_kernel+ NOT_PROVEN; R5 initramfs NOT_PROVEN; R6 /init NOT_PROVEN.
Original evidence ladder unchanged: E0 PROVEN, E1-E4 NOT_PROVEN, E5 FROZEN.

Recommended next: `MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI` (predevice
readiness CI only — a T1 device run is NOT authorized by this result).
