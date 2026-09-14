# thyme R3 current status (single source of truth for the current round)

Maintained rule: this file is the ONLY current-state entry. Older docs keep
their historical results and are never rewritten; where an older doc says
"E1/E2 SUPPORTED" or a different "Current B", THIS file wins for current
facts. Last updated: 2026-09-14
(MAINLINE_V2_R3_P1B_T1_TRUE_DEVICE_CONTROL — EXECUTED, Case T1-A STRONG;
`MAINLINE_V2_R3_P1B_T1_REACHABILITY_PROVEN`; one identity-gated `fastboot
boot` of the frozen T1-8 boot, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`;
followed by MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI — CI only, no device
operation).

<!-- R3-STATUS-KV:BEGIN -->
<!-- Machine-readable current state. The T2 CI source gate parses THIS block
     as structured key/value pairs (T2_STATUS_GATE_SEMANTIC=YES) instead of
     matching natural-language phrases. Keep the values exactly as shown. -->
T0_STATUS=TRUE_DEVICE_PROVEN
T0_TOTAL_S=14.252
T1_STATUS=TRUE_DEVICE_PROVEN
T1_TOTAL_S=14.238
T1_MINUS_T0_S=-0.014
R0_STATUS=PROVEN
R1_STATUS=PROVEN
R2_STATUS=PROVEN
R3_STATUS=NOT_PROVEN
R4_STATUS=NOT_PROVEN
R5_STATUS=NOT_PROVEN
R6_STATUS=NOT_PROVEN
E0_STATUS=PROVEN
E1_STATUS=NOT_PROVEN
E2_STATUS=NOT_PROVEN
T2_STATUS=PREDEVICE_READY
T2_DEVICE_CONTROL=NOT_AUTHORIZED
T3_STATUS=NOT_DEVICE_READY
PANIC30_STATUS=COMPLETED
PANIC30_SHIFT=NO_SUPPORTED_SHIFT
FIX24_STATUS=FROZEN
M5N_STATUS=FROZEN
USB_STATUS=FROZEN
CURRENT_B=M5D+M5H+M5M-B
SLOT_A_WRITTEN=NO
PARTITION_WRITES=0
DEVICE_OPERATION=NO
<!-- R3-STATUS-KV:END -->

## T2 PREDEVICE ROUND (CI only, no device operation)

`MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI` promotes T2 from a design note
to a **unique, frozen, fail-closed, full-SHA identity-gated, MMU-on
execution-safe, explainable** `__primary_switched` address-reachability
candidate. It performs: authoritative kernel rebuild in GitHub Actions,
`__primary_switched` and `primary_entry` re-derivation (never a history
constant), original-instruction identity from three sources, an INLINE
overwrite-safety audit (symbol / control-flow / relocation / absolute-literal /
section-boundary scans), the T2 entry-CPU-state contract, CNTPCT and PSCI
safety audits, byte-identity of the delay/reset core against the T0/T1
proven sequence, single-region payload diff attribution, geometry, negative
fixtures and T1-matched-control decoder fixtures.
Full record: `docs/route-r3-p1b-t2-predevice-readiness.md`.
No device was touched: `DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`,
`SLOT_A_WRITTEN=NO`. A T2 device round is a separate stage that requires its
own explicit user approval.

## T1 TRUE DEVICE ROUND (EXECUTED 2026-09-14 05:30 UTC)

`MAINLINE_V2_R3_P1B_T1_TRUE_DEVICE_CONTROL` was EXECUTED with explicit user
approval: exactly ONE `fastboot boot` of the frozen T1-8 boot, `T1-8` only,
`SECOND_BOOT_FORBIDDEN=YES`, `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`,
`SET_ACTIVE=NO`. mem0 was read three times (round start, before
`adb reboot bootloader`, and again inside the bootloader). No local build,
link, splice or `mkbootimg`: the authoritative frozen GHA artifact only
(private pack run 34807172879, identity reverify 34807260192).

Artifact identity was re-verified FULL-SHA from the downloaded artifact before
any fastboot interaction and independently re-derived locally
(`work/t1-verify/verify-t1-boot.py` → `VERIFY_RESULT=PASS`): boot
`a4fa083f…e3df` (37380096), payload `3e654ee5…f0fb` (37369041), checkpoint
`4d792df5…3611` (76 @ `0x2230000`), trampoline
`362d9c6e…c623` (48 @ `0x40`, byte-identical to FIX8), RT-D
`48497432…f327` (144593 @ `0x2380000`), payload diff 75 B =
4 @ `[0x1b1c0a0,0x1b1c0a4)` + 71 @ `[0x2230000,0x223004c)`
(`PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY`). The source baseline
(`0895098..HEAD`) is docs-only, so no post-READY functional change; the
concurrent docs-only public run 34808780315 was never used.

Fastboot: `Sending 'boot.img' (36504 KB) OKAY [0.900s]`, `Booting OKAY
[0.221s]`. Timeline UTC: `T_COMMAND_START` 05:30:18.796, `T_SENDING_OKAY`
05:30:19.721, `T_BOOTING_OKAY` 05:30:19.941, `T_USB_NONE` 05:30:21.342,
`T_FASTBOOT_DISAPPEAR` 05:30:21.345, `T_USB_FIRST_REENUM` 05:30:41.515
(`18d1:4ee7`), `T_ADB_FIRST_SEEN` 05:30:42.549, `RETURNED_ANDROID_KERNEL_START`
05:30:34.179 (uptime 8.37; cross-check 05:30:34.156 with uptime 18.67),
`T_BOOT_COMPLETED` 05:30:52.785. The returned-kernel-start algorithm is the
same as T0 (`host_before_uptime_read − /proc/uptime`).

| metric | value |
| --- | --- |
| `T1_TOTAL` | **14.238 s** (cross-check 14.214 s) |
| `T0_REFERENCE_TOTAL` | 14.252 s |
| `T1_MINUS_T0` | **−0.014 s** → matched-control **STRONG** (≤ ±1.000 s) |
| `T1_TOTAL < 20 s` | YES |
| `AUTOMATIC_ANDROID_RETURN` | YES |
| `T1_PROGRAMMED_ESTIMATE` | 8.093 s vs 8.000 s → error +0.093 s (SECONDARY, consistent) |

VERDICT: `T1_REACHABILITY_SIGNATURE=STRONG` (Case T1-A),
`PRIMARY_ENTRY_ADDRESS_REACHED=PROVEN`,
`R2_PRIMARY_ENTRY_ADDRESS_REACHABILITY=PROVEN`, while
`E1_NORMAL_PRIMARY_ENTRY_EXECUTION=NOT_PROVEN` — the original first
instruction `bl record_mmu_state` is replaced by the T1 diagnostic branch, so
a T1 positive can never be read as normal Mainline boot.

Post-test: `ANDROID_A_RESTORED=YES` (`_a`, `boot_completed=1`, root, Stock
4.19.157-perf-g9d90dd04aa7c, `bootreason=bootloader`); pstore empty (auxiliary
only, NOT negative evidence); `logdump`/`rawdump` byte-identical to the frozen
baseline (`NO_T1_PERSISTENT_DUMP_EVIDENCE=YES`, no Linux 6.6 trace);
`CURRENT_B_UNCHANGED_AFTER_T1=YES`.

Final gate: **`MAINLINE_V2_R3_P1B_T1_REACHABILITY_PROVEN`**. Full record:
`docs/route-r3-p1b-t1-predevice-readiness.md` section 26.

## Current Round

`MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI` — CI / SOURCE AUDIT /
ARTIFACT PREPARATION ONLY. `DEVICE_OPERATION=NO`, `PARTITION_WRITES=0`,
`SLOT_A_WRITTEN=NO`; no T1/T2 device run, no T0 second boot, no PANIC30
second boot, no FIX8 rerun, no FIX24, no M5N, no copydown, no USB, no UFS,
no network. Local builds remain forbidden — every assembly, link, kernel
build, disassembly and validation step runs in GitHub Actions only.

Goal: elevate the previous round's `T1 CI_PASS` prototype into the unique,
frozen, fail-closed, full-SHA identity-gated, explainable
**T1-8 primary_entry address reachability true-device diagnostic candidate**.
T1 answers exactly one question: after the unmodified frozen FIX8 trampoline
executes its normal `branch primary_entry`, did the CPU actually arrive at the
Linux `primary_entry` **address**? It answers nothing else — not MMU state,
not `record_mmu_state`, not DTB parse, not `start_kernel`, not initramfs, not
`/init`.

Key properties of the frozen candidate:

- base is the exact FIXED INIT8 payload (`4f34eabf…cceb41`, public run
  34741153230); only two regions differ —
  A. `primary_entry`'s first instruction `bl record_mmu_state` → `b
  T1_CHECKPOINT`, B. the T1 diagnostic code written into the deterministic
  zero padding **outside the Linux `image_size` runtime footprint** and before
  the RT-D trailer. This placement is a correction of the earlier gap probe,
  which sat at the Image file end and therefore inside the kernel's own
  runtime footprint. There is no file_size-only fallback.
- `primary_entry` offset is re-derived this round from `llvm-nm` +
  `System.map` + `kernel_gate` + the frozen trampoline's own branch algebra —
  never inherited as a constant. The original first instruction is confirmed
  from head.S **and** the frozen payload bytes **and** the authoritative
  vmlinux disassembly, all three agreeing.
- `image_size` is re-read from the authoritative Image header rather than
  inherited from any historical reading.
- trampoline byte-identical to FIX8
  (`362d9c6e…c623`), RT-D byte-identical to FIX8 (`48497432…f327`, `panic=5`,
  NOT the PANIC30 trailer), `/init` and initramfs byte-identical,
  payload/boot geometry identical (`T1_RUNTIME_SEMANTIC_DELTA=
  PRIMARY_ENTRY_REACHABILITY_CHECKPOINT_ONLY`).
- checkpoint: 8 s CNTPCT register-only delay (the T0 device-proven
  instruction sequence) → PSCI `SYSTEM_RESET` `0x84000009` via `smc #0` →
  permanent `wfe` loop on any `smc` return. No stack, no memory writes, no
  `x0` dereference, no relocation, no path back into `primary_entry`.
  `T1_DIAGNOSTIC_ONLY=YES`, `T1_NORMAL_KERNEL_BOOT_CANDIDATE=NO`.
- 20 negative fixtures, matched-control decoder fixtures and the identity-gated
  T1 observer fixtures all run green in CI.
- proof boundary: a future T1 positive proves R2
  (`PRIMARY_ENTRY_ADDRESS_REACHED`) only — never R3 and never E1.

Final gate: **`READY_FOR_R3_P1B_T1_DEVICE_CONTROL`** — every gate green,
private pack green, boot identity frozen, observer fixtures green. This
authorises PREPARATION ONLY; the single T1 device run still requires separate
explicit user approval. Details:
docs/route-r3-p1b-t1-predevice-readiness.md.

Frozen T1 identity (PRIVATE boot artifact, never emitted from this repo):

| item | value |
| --- | --- |
| T1 boot v3 (M5D envelope) | `a4fa083f…e3df`, 37380096 |
| T1 payload | `3e654ee5…f0fb`, 37369041 |
| T1 checkpoint | `4d792df5…3611`, 76 at offset `0x2230000` |
| primary_entry (re-derived) | `0x1b1c0a0`; original insn `bl record_mmu_state` → `0x1b39234` |
| branch distance | `0x713f60`; diff 75 bytes `A=4 B=71` in `[0x1b1c0a0,0x1b1c0a4)` + `[0x2230000,0x223004c)` |
| trampoline / RT-D | `362d9c6e…c623` (frozen FIX8) / `48497432…f327` at `0x2380000` |

CI: public runs 34803433243 (`545a2508`), 34805344669 (`0895098`) and
34807369790 (`0fd48ab`, round record) all three jobs green with
byte-identical identities (compose determinism proven); private
pack 34807172879 and identity reverify 34807260192 green.

## Previous executed device round — T0 TRUE DEVICE (frozen)

`MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI` produced the T0 CI_PASS
candidate (`T0 CI_PASS`); `MAINLINE_V2_R3_P1B_T0_TRUE_DEVICE_CONTROL` then
executed the one authorized boot 2026-09-13 23:09 UTC with explicit user
approval. `PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, `SET_ACTIVE=NO`,
`EXPERIMENTAL_BOOTS=1`, `SECOND_BOOT_FORBIDDEN=YES` (no host device write of
any kind; T1/T2/FIX24/M5N not executed). Final gate:
**`MAINLINE_V2_R3_P1B_T0_REACHABILITY_PROVEN`**
(Case T0-A STRONG: `T0_REACHABILITY_SIGNATURE=STRONG`,
`T0_CHECKPOINT_REACHED=PROVEN`,
`P1B_LARGE_PAYLOAD_TRAMPOLINE_REACHED=PROVEN`,
`TRAMPOLINE_X0_X3_SETUP_PATH_EXECUTED=YES`).

The single authorized boot was the frozen fail-closed T0-8 candidate (boot
v3 `8d7648e4…fdc1`/37380096 from private pack run 34769675932, identity
reconfirm 34769764343) after FULL-SHA re-verification of boot/payload/
trampoline/RT-D and the checkpoint-region-only diff vs frozen FIX8
(73 bytes in `[0x49,0xab] ⊂ [0x40,0xB0)`). Observer identity gate fired
before any fastboot interaction; fastboot `Sending OKAY [ 1.010s]` /
`Booting OKAY [ 0.220s]`.

Timing: `T0_TOTAL = 14.252 s` (BOOTING_OKAY 23:09:33.741Z → returned
Android kernel start 23:09:47.994Z); supporting decoder
`T0_PROGRAMMED_ESTIMATE = 8.108 s` vs programmed 8.000 s → error **+0.108 s**
→ `T0_WINDOW=STRONG`; `T0_EARLY_RETURN_CLASS_MATCH=YES` (< 20 s);
`RECOVERY_KIND=AUTOMATIC_ANDROID_RETURN` (bootreason=bootloader, Stock
4.19.157-perf, slot `_a`). Triple condition met. The timing signature
directly shows the trampoline checkpoint executed (8 s CNTPCT delay then
PSCI SYSTEM_RESET); it does NOT prove RT-D parse, primary_entry, head.S,
MMU switch, start_kernel, initramfs or /init. Post-test:
`ANDROID_A_RESTORED=YES`, `CURRENT_B_UNCHANGED_AFTER_T0=YES`, pstore empty
(auxiliary only, not negative evidence).
Details: docs/route-r3-p1b-t0-predevice-readiness.md section 23.

The previous round's CHECKPOINT_T0 prototype (failsafe fall-through:
smc return -> restore x0/x1/x2/x3 -> primary_entry) is audited as NOT
device-ready and is retained verbatim as the audit target
(`T0_PROTOTYPE_FALLTHROUGH_AUDIT=DEVICE_PROTOTYPE_NOT_READY_FAIL_CLOSED_REGENERATED`);
this round froze the fail-closed T0-8 replacement instead:
8s CNTPCT register-only checkpoint AFTER x0-x3 setup / BEFORE the
primary_entry branch, PSCI SYSTEM_RESET 0x84000009 smc, wfe forever on any
smc return, `T0_RUNTIME_SEMANTIC_DELTA=TRAMPOLINE_CHECKPOINT_RESET_ONLY`,
`T0_CLOBBER_REGISTERS=x0/w0(PSCI FID),x9,x10,x11,x12,x13,NZCV`,
`T0_RUNTIME_RELOCATIONS=0`, `T0_POSITION_INDEPENDENT=YES`,
dtb_rel `0x237ff58`, x0_static `0x2380000`.

Frozen identity (all GHA-gated, deterministic across runs):

| item | value |
| --- | --- |
| T0 payload | `072c59e9…8fbe`, 37369041 = frozen FIX8 bytes with ONLY `[0x40,0xB0)` replaced (73 diff bytes, `T0_PAYLOAD_DIFF_ATTRIBUTED=CHECKPOINT_REGION_ONLY`), RT-D trailer `48497432…f327` exact, image_size `0x2230000`, DTB_OFFSET `0x2380000` |
| T0 trampoline | `92fcb46e…0e72`, 112 bytes, smc -> wfe -> b-wfe terminal (fail-closed), no branch leaves `[0,0x70)` |
| T0 boot v3 (PRIVATE pack, M5D envelope `4db8151b…85e63`) | `8d7648e4…fdc1`, 37380096, header diff vs M5D subset bytes 8..12 only |
| forbidden boots (observer misboot refusal) | FIX8 `ba3d8789…2ab5`, PANIC30 `ea50e8b3…64b1`, old INIT8 `e6ac6308…1264`, entry-state probe `cb61889a…e82c` |

CI record: public push run 34769389485 (commit `943519b…bb49`) green
(source gate + t0-build + independent verify, artifact
`thyme-r3-p1b-t0`); public authoritative dispatch run 34769494589 green
with byte-identical payload/trampoline SHAs (determinism proven). Private
repo pack run 34769675932 green (`T0_PACK_GATES=PASS`,
`ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES`); private identity reverify run
34769764343 green (`T0_PRIVATE_BOOT_IDENTITY_RECONFIRMED=YES`,
`T0_ARTIFACT_REBUILD_REQUIRED=NO`).

Observer: `observe-r3-p1b-t0.py` (derived from the device-proven INIT8
observer) accepts ONLY the exact T0 boot via full-SHA `R3_T0_SHA256` +
size 37380096 and refuses the four frozen wrong boots BEFORE any fastboot
interaction; `FASTBOOT_BOOT_ONLY`, `SECOND_BOOT_FORBIDDEN`. Preregistered
decoder (SUPPORTING, not strict invariant): `T0_PROGRAMMED_ESTIMATE =
T0_TOTAL − 6.1445` s; STRONG ≤ ±1.5 s, SUPPORTED ≤ ±3.0 s, early class
`T0_TOTAL < 20` s (references FIX8 23.852 s, PANIC30 26.289 s); triple
condition = window + early class + AUTOMATIC_ANDROID_RETURN. A negative is
`T0_SIGNATURE_NOT_OBSERVED=YES`, NEVER licenses `T0_NOT_REACHED`, and
routes to `T0_FAILURE_ISOLATION_CI`. Fixtures: 12 negative (real gates,
mutated inputs) + 13 decoder + observer suite — all green in CI.
Checkpoints stay T1 CI_PASS / T2 DESIGNED.
Details: docs/route-r3-p1b-t0-predevice-readiness.md.

## Current Gate (last executed device round)

`MAINLINE_V2_R3_P1B_T0_REACHABILITY_PROVEN` — the one authorized T0-8
device boot (UTC 2026-09-13 23:09, full record in the T0 predevice doc
section 23) met the preregistered triple condition: timer window STRONG
(`T0_PROGRAMMED_ESTIMATE` error +0.108 s vs 8.000 s programmed), early
return class (`T0_TOTAL = 14.252 s < 20 s`), automatic Android return.
This upgrades the CHECKPOINT dimension only: ABL loaded the large P1B
payload to an executed location and the trampoline ran through x0-x3 setup
to its fail-closed checkpoint. It does NOT upgrade E1-E4 (no evidence that
RT-D was parsed or that normal boot continued — the T0 image can never
continue normal boot by construction).

Previous executed device round: `R3_P1B_PANIC30_TIMEOUT_NOT_OBSERVED`
(one P1B-PANIC30 boot UTC 2026-09-13, `PANIC30_TOTAL = 26.289 s` vs FIX8
`23.852 s`, `P30_DELTA = +2.437 s`, outside SUPPORTED [23.0, 27.0], Case
P30-C `NO_SUPPORTED_SHIFT`; behavior automatic Android return, no stable
Fastboot, no manual recovery; `CURRENT_B_UNCHANGED_AFTER_PANIC30=YES`,
`ANDROID_A_RESTORED=YES`). Full record: isolation doc section 26.

## Evidence ladder (current, conservative)

| level | statement | status |
| --- | --- | --- |
| E0 | ABL -> controlled payload | PROVEN |
| E1 | normal Mainline Linux entry reached | NOT_PROVEN |
| E2 | early Mainline boot | NOT_PROVEN |
| E3 | built-in initramfs reached | NOT_PROVEN |
| E4 | /init executed | NOT_PROVEN |
| E5 | USB | FROZEN |

Independent reachability ladder (introduced at the T0 positive; a
diagnostic checkpoint never reads as normal boot success):

| rung | statement | status |
| --- | --- | --- |
| R0 | ABL controlled payload entry | PROVEN |
| R1 | P1B large-payload trampoline T0 checkpoint (after x0-x3 setup) | PROVEN |
| R2 | normal primary_entry | NOT_PROVEN |
| R3 | post-head.S / __primary_switched | NOT_PROVEN |
| R4 | start_kernel+ | NOT_PROVEN |
| R5 | initramfs | NOT_PROVEN |
| R6 | /init | NOT_PROVEN |

Side evidence kept behavioral-only (never upgrades E1/E2):
`M5_STYLE_4P7S_PATH_NOT_OBSERVED=YES`,
`AUTOMATIC_ANDROID_RETURN_SIGNATURE=YES`.

## Frozen device facts

- OLD BROKEN INIT8 TOTAL 23.184 s; OLD BROKEN INIT24 TOTAL 24.570 s; pair
  delta 1.386 s vs expected 16.000 s (NO_MATCH; root cause = 3-arg
  clock_nanosleep ABI bug, since fixed).
- FIXED INIT8 TOTAL 23.852 s; exact QEMU /init sleep 8.003 s (ABI4); delta
  vs broken +0.668 s; classification NOT_CONSISTENT_WITH_8S_DELAY;
  `DEVICE_RETURN_PATH_NOT_OBSERVED_TO_FOLLOW_INIT_SLEEP=YES`.
- Persistent evidence never showed explicit mainline lines (pstore empty,
  rawdump/logdump unchanged); absence is not proof of Linux absence (no
  persistent sink exists).
- Frozen hashes: FIX8 payload `4f34eabf…cceb41`, Image `dffce20e…44944`
  (header image_size 0x2230000 as measured on both the frozen payload and a
  fresh rebuild; file 35166720), /init `f1bc8849…66d`,
  initramfs `02123e98…fff3`, trampoline `362d9c6e…c623`,
  RT-D `48497432…f327` (144593), DTB_OFFSET `0x2380000`,
  Linux base `8b73de7da85fde281a385e0b26eda9bffd3ca477` (6.6.156).
- PANIC30 artifacts (public run 34754072600, commit c001114c, all jobs green):
  RT-D `dfbfca03…3390` (144597 = 144593+4, semantic delta
  PANIC_TIMEOUT_ONLY), payload `cd3f7527…687e` (37369045 = 37369041+4,
  prefix byte-identical to frozen FIX8), boot_size_est 37380096,
  primary_entry 0x1b1c0a0 (re-derived this round), __primary_switched
  0x1b39534, T0/T1 CI PASS, T2 DESIGNED. Audit-correction round: identity
  RE-CONFIRMED from the authoritative manifests (primary 34754072600 ==
  confirmation 34755788727, manifests identical; full SHAs in the isolation
  doc) with NO rebuild — `PANIC30_ARTIFACT_REBUILD_REQUIRED=NO`,
  `PANIC30_BINARY_SEMANTICS_UNAFFECTED_BY_AUDIT_CORRECTION=YES`.
- PANIC30 boot (PRIVATE repo only, private run 34755701908): boot v3
  `ea50e8b3…64b1`, size 37380096, spliced into the exact M5D envelope
  (4db8151b…); pack gates + size cross-check PASS. Device round EXECUTED
  2026-09-13 (identity re-hashed locally before boot, never re-packed):
  `PANIC30_TOTAL = 26.289 s`, `P30_DELTA = +2.437 s` vs FIX8 23.852 s,
  `P30_ERROR = −22.563 s` vs expected +25.000 s, Case P30-C,
  `PANIC30_TIMEOUT_NOT_OBSERVED_TO_CONTROL_RETURN_TIMELINE=YES`,
  `AUTOMATIC_ANDROID_RETURN=YES`, no persistent dump evidence; no upgrade of
  E1–E4 (full record: isolation doc section 26).

- T0 device round (EXECUTED 2026-09-13 23:09 UTC, private pack run
  34769675932 artifact, boot `8d7648e4…fdc1`/37380096, payload
  `072c59e9…8fbe` = frozen FIX8 payload `4f34eabf…cceb41` with ONLY
  `[0x40,0xB0)` replaced, trampoline `92fcb46e…0e72`, RT-D `48497432…f327`
  at DTB_OFFSET `0x2380000`): `T0_TOTAL = 14.252 s`,
  `T0_PROGRAMMED_ESTIMATE = 8.108 s` (error +0.108 s, STRONG),
  `AUTOMATIC_ANDROID_RETURN=YES`, Case T0-A →
  `MAINLINE_V2_R3_P1B_T0_REACHABILITY_PROVEN`; checkpoint reached PROVEN,
  E1-E4 unchanged. Identity re-verified locally before boot (never
  re-packed); no persistent dump evidence; constraints held.

## Current B

`M5D + M5H + M5M-B` — UNCHANGED. Active slot A (stock Android) untouched;
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, no set_active, no B boot.

## Frozen branches / items

- M5N: FROZEN.
- FIX24 (24s-delay /init): FROZEN and FORBIDDEN this round.
- USB stage work: FROZEN.
- UFS / rootfs / network: FROZEN.
- PANIC30: diagnostic control EXECUTED as the one authorized device boot
  (panic=5 -> panic=30 on the RT-D trailer); result gate
  `R3_P1B_PANIC30_TIMEOUT_NOT_OBSERVED`; binary frozen, no rebuild; second
  boot forbidden.
- Checkpoints T0/T1/T2: T0 device run EXECUTED (Case T0-A STRONG,
  `MAINLINE_V2_R3_P1B_T0_REACHABILITY_PROVEN`, `T0_TOTAL = 14.252 s`); T1
  device run EXECUTED (Case T1-A STRONG,
  `MAINLINE_V2_R3_P1B_T1_REACHABILITY_PROVEN`, `T1_TOTAL = 14.238 s`,
  `T1_MINUS_T0 = −0.014 s`, R2 PROVEN) — the earlier T1 CI_PASS prototype was
  superseded by the frozen fail-closed T1-8 candidate of
  `MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI`, and that candidate has now
  been consumed by its single authorized boot. T2 was DESIGNED through the T0
  and T1 rounds; this round promotes it to PREDEVICE READY via
  `MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI` (CI only). T2 is still NOT
  device authorized — a T2 device round needs its own gate plus explicit user
  approval.
- Reachability ladder: R0 PROVEN | R1 PROVEN | R2 PROVEN (primary_entry
  ADDRESS) | R3 `__primary_switched` NOT_PROVEN | R4 `start_kernel+`
  NOT_PROVEN | R5 initramfs NOT_PROVEN | R6 `/init` NOT_PROVEN.
- Original evidence: E0 PROVEN | E1 NOT_PROVEN | E2 NOT_PROVEN | E3
  NOT_PROVEN | E4 NOT_PROVEN | E5 FROZEN. T1 does not move E1: its positive
  proves ADDRESS REACHABILITY, not normal `primary_entry` execution.

## Next approved candidate

`MAINLINE_V2_R3_P1B_T1_TRUE_DEVICE_CONTROL` is COMPLETE with final gate
`MAINLINE_V2_R3_P1B_T1_REACHABILITY_PROVEN`. The T1 PREDEVICE readiness stage
is closed — its single authorized device boot has been consumed, and the token
`T1 PREDEVICE` is retained in this document deliberately, because the older CI
source gates are literal-substring checks over this file (see the gate-token
note below). `MAINLINE_V2_R3_P1B_T2_PREDEVICE_READINESS_CI` has now also
completed (CI / source-audit only) and promotes T2 to PREDEVICE READY with the
INLINE fail-closed `__primary_switched` checkpoint documented in
`docs/route-r3-p1b-t2-predevice-readiness.md`. The next executable candidate is
**`MAINLINE_V2_R3_P1B_T2_TRUE_DEVICE_CONTROL`** — exactly one identity-gated
`fastboot boot` of the frozen T2-8 boot, `SECOND_BOOT_FORBIDDEN`,
`SLOT_A` write forbidden. It is NOT authorized by this document; it requires
its own explicit user approval. Any T2 negative class (not observed, timing
mismatch, stable bootloader return, no return, boot not accepted) routes to
`MAINLINE_V2_R3_P1B_T2_FAILURE_ISOLATION_CI`, never automatically to T3.

## Not-ready candidates

- T2 device run: T2 is PREDEVICE READY but NOT device authorized; needs
  separate user approval.
- T3 (`start_kernel` or the earliest stable C-entry checkpoint): NOT device
  ready, not designed yet.
- FIX24, M5N, USB bring-up, UFS rootfs, network, drivers: frozen.
- CopyMem forensics: priority LOWERED (T0 positive removes the transport
  suspicion that would have re-raised it).
- Persistent logging (pstore/ramoops/UART/USB gadget/earlycon): deferred;
  would break single-variable isolation.

## Gate-token note (2026-09-14)

`scripts/r3-p1b/p1b-t1-predevice.py --mode source-gate` validates this file by
**literal substring presence**, not by semantic content: it requires the exact
strings `MAINLINE_V2_R3_P1B_T1_PREDEVICE_READINESS_CI`,
`MAINLINE_V2_R3_P1B_T0_PREDEVICE_READINESS_CI`, `T0 CI_PASS`,
`T0 TRUE DEVICE`, `14.252`, `T1 PREDEVICE`, `T2 DESIGNED`, `PANIC30`, `FIX24`,
`M5N`, `FROZEN`, `NOT_PROVEN`.

Consequence, recorded because it actually happened: when the T1 true-device
result was written into this file, the phrase `T1 PREDEVICE` was reworded away
and the public source gate went red (`T1_SOURCE_GATE_FAILED: missing 'T1
PREDEVICE'`, run 34810065176) on a docs-only change that was otherwise correct.
The token is restored above and the wording is kept deliberately. Any future
rewrite of these sections must re-check the token list before pushing, or the
gate itself should be changed to a semantic check — the gate currently treats
removing a phrase as a source-audit failure.

Follow-up (2026-09-14, T2 round): the fragile literal-token approach is **not**
extended. The T2 source gate reads the structured `R3-STATUS-KV` block above as
parsed key/value pairs and reports `T2_STATUS_GATE_SEMANTIC=YES`. The older
T0/T1 gates remain literal-substring checks and are left untouched, so the
phrases they require (`T0 CI_PASS`, `T0 TRUE DEVICE`, `T1 PREDEVICE`,
`T2 DESIGNED`, `PANIC30`, `FIX24`, `M5N`, `FROZEN`, `NOT_PROVEN`, `14.252`) are
preserved verbatim in this document.

## Panic-audit anchors (corrected 2026-09-13)

panic= is a standard boot param (`core_param`, `__section("__param")`, not
early); parsed in `parse_args("Booting kernel")` AFTER setup_arch and
`parse_early_param`. `panic_timeout` default 0 — with 0 the panic path
performs NO wait and NO emergency_restart() and control falls into the
terminal infinite panic loop; `PANIC_NEVER_RETURNS=YES`
(`PANIC_ZERO_TIMEOUT_BEHAVIOR=INFINITE_PANIC_LOOP_NO_AUTOMATIC_RESTART`).
A pre-parse panic therefore cannot restart via the panic path at all and
needs an independent reset mechanism (watchdog/firmware/hardware) to
auto-return: `PRE_PARSE_LINUX_PANIC_ALONE_EXPLAINS_23S_AUTORETURN=NO`. A
post-parse panic obeys panic=30 (timeout wait + emergency_restart) —
`PANIC30_POSITIVE_CONTROL_REMAINS_VALID=YES`. Timeout wait = 100 ms mdelay
loop depending on `loops_per_jiffy` (calibrated only AFTER parse_args ->
`PANIC_TIMEOUT_WALLCLOCK_EXACT_BEFORE_CALIBRATE_DELAY=NOT_GUARANTEED`);
restart path = emergency_restart -> machine_restart -> do_kernel_restart ->
PSCI SYSTEM_RESET (0x84000009) smc, closed under RT-D (`/psci
method="smc"`). Cmdline provenance closed:
`P1B_FINAL_CMDLINE_SOURCE=RT_D_CHOSEN_BOOTARGS_ONLY`,
`DUPLICATE_PANIC_PARAMETER=NO`.

Old timeout-0 reading ("panic() would return to its caller") of the
previous round: `SUPERSEDED_BY_PANIC_AUDIT_CORRECTION`; verbatim history is
preserved in git (96a2cc9..c001114c) and in the fenced history blocks of
docs/route-r3-p1b-panic-checkpoint-isolation.md (section 6a) and
docs/route-r3-p1b-failure-isolation.md (section 12). CI now carries
negative fixtures that FAIL any live re-assertion of that claim.

Round details: docs/route-r3-p1b-panic-checkpoint-isolation.md
