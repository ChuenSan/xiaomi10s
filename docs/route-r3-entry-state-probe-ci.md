# Route R3 — Entry State Probe CI (MAINLINE_V2_R3_ENTRY_STATE_PROBE_CI)

Status: **TRUE DEVICE RESULT** — bucket 4s STRONG → EL1, M=0, C=0 →
R3_ENTRY_STATE_PRIMARY_CONTRACT_SATISFIED
Date: 2026-09-12
Branch: route-b-v3

Standing constraints (unchanged, verbatim):

```
LOCAL_BUILD:                       NO
LOCAL_VALIDATION:                  NO
LOCAL_VALIDATOR:                   NO
LOCAL_SOURCE_GATE:                 NO
LOCAL_ACTIONLINT:                  NO
LOCAL_BINARY_VALIDATION:           NO
DEVICE_OPERATION:                  NO
PARTITION_WRITES:                  0
Slot A written:                    NO
```

All assembly, linking, disassembly validation, boot packing, artifact
validation: GitHub Actions only. Public repo audits sources, rebuilds RT-D,
and gates decoder logic; the flashable probe boot is assembled and packed in
private GHA (`ChuenSan/thyme-mainline-private-ci`, pinned public source
commit). No `adb`, no `fastboot`, no flash/erase/set_active this round.
AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B (unchanged). M5N FROZEN. USB FROZEN.

---

## 1. P0 proven baseline

E0 ABL → controlled shim: PROVEN. The P0 timing pair remains the execution
model: Android boot v3 header, `fastboot boot` on active slot A, exact M5D
non-kernel envelope, kernel payload at offset 0, position-independent arm64
assembly, no stack, no RAM write, CNTPCT timer, PSCI SYSTEM_RESET via SMC.

P0 timing pair (frozen):

- A8: programmed 8s → BOOTING_OKAY→kernel_start 14.148s
- A24: programmed 24s → 30.141s; delta 15.993s vs expected 16.000s
- SHIM_ENTRY_PROVEN=YES

E1 shim → normal Mainline: NOT_PROVEN. E2 early Mainline: NOT_PROVEN.
E3 initramfs: NOT_PROVEN. E4 /init: NOT_PROVEN. E5 USB: FROZEN.

## 2. RT-D completed baseline (frozen)

FINAL_GATE_PREVIOUS=R3_RUNTIME_DTB_COMPLETED.

- RT-D DTB SHA256 `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`, 144,593 bytes
- self-contained: YES / memory valid: YES / reserved-memory valid: YES (22 static regions) / overlay-independent: YES
- RAM: 3 banks; M1 raw: SELF_CONTAINED=NO (never a runtime baseline)
- Future P1 runtime DTB baseline = RT-D only (not M1 raw, not Stock DTB, not ABL-merged DTB)
- This round's state probe does NOT use RT-D at all: no embed, no x0
  dereference, no Mainline entry. RT-D stays frozen waiting for P1B
  (trampoline will set x0 to the PC-relative RT-D address, x1=x2=x3=0).

## 3. RAM bank notation reconciliation

Three authoritative sources checked before any new design:

1. Public JSON `scripts/r3-p1/dts/thyme-runtime-memory-evidence.json`
   (SHA256 `0882b617…6bff`, pinned in `entry-state-probe.py`).
2. RT-D source `scripts/r3-p1/dts/sm8250-xiaomi-thyme-runtime.dts`.
3. GHA-built RT-D DTB (SHA256 `4849743205…f327`), re-built byte-identical
   in CI and SHA-asserted (`rt-d.dtb`).

The second ascending RAM bank:

- JSON: base 0xC0000000, size 0x140000000, end-exclusive 0x200000000
- DTS: `<0x0 0xc0000000 0x1 0x40000000>`
- Built DTB: same cells, gate-enforced equal to JSON

RAM_BANK_REPORT_NOTATION_ERROR=YES — the previous round's final report table
(`route-r3-runtime-dtb-completion.md` §6) wrote bank 1 base with a spurious
`1_` high-word prefix (as if the base were 0x1C0000000), inconsistent with
its own size and end columns. The
corrected notation is 0x0_C0000000 (base 0xC0000000; last byte 0x1FFFFFFFF).
RAM_BANK_SEMANTIC_ERROR=NO — all three real sources always agreed; only the
report text was wrong, so only docs (this file + the completion report) and
mem0 wording were corrected. No RT-D with different semantics was built.
CI enforcement: public job `ram-reconciliation` asserts
RAM_RECONCILIATION_JSON_DTS_DTB_EQUAL=YES + RT_D_DTB_SHA256_MATCH=YES.

## 4. Linux 6.6 required entry state (read from exact source)

Re-read for this round from `linux-6.6` (6.6.156, base 8b73de7d…):
`Documentation/arch/arm64/booting.rst` and `arch/arm64/kernel/head.S`.

R3_ENTRY_CONTRACT_REQUIRED_STATE:

| item | requirement | source |
|---|---|---|
| Entry EL | non-secure EL1 or EL2 (EL2 RECOMMENDED) | booting.rst 169-172 |
| PSTATE.DAIF | all interrupts (D/A/I/F) masked | booting.rst 169-170 |
| MMU | must be off (SCTLR_ELx.M = 0) | booting.rst 176 |
| D-cache | boot protocol requires MMU-off state; M=0 is the hard gate, C is audited but only M/C both enter the first probe | booting.rst 174-188 |
| I-cache | may be on or off, no stale entries for the kernel image | booting.rst 178-179 |
| x0-x3 | x0 = DTB physical address, x1=x2=x3=0 | booting.rst 160-165 |
| Timers | CNTFRQ programmed, CNTVOFF consistent, CNTHCTL_EL2.EL1PCTEN=1 if entering at EL1 | booting.rst 190-195 |

Bit positions pinned in CI from the exact Linux source
(`--mode bit-position-pin`): `arch/arm64/include/asm/sysreg.h` —
SCTLR_ELx_M=BIT(0), SCTLR_ELx_C=BIT(2), SCTLR_ELx_I=BIT(12);
`arch/arm64/include/asm/ptrace.h` — CurrentEL_EL1=(1<<2)=4,
CurrentEL_EL2=(2<<2)=8.

## 5. Detection is not permission (unknown inherited state)

`head.S:record_mmu_state` reads CurrentEL and SCTLR_ELx and detects M/C/EE,
and `init_kernel_el` immediately writes INIT_SCTLR_ELx_MMU_OFF at whichever
EL — Linux code can DETECT and normalize inherited state. That does not
widen the bootloader contract: booting.rst still states "The MMU must be
off". The probe observes the inherited state; the contract decides whether
it is acceptable.

Classification of EL2-area state for a future P1B trampoline:

- KERNEL_NORMALIZES: SCTLR M/C/I/EE, HCR_EL2.E2H/VHE flags, SCTLR_EL1 sane value (init_kernel_el / record_mmu_state)
- BOOTLOADER_MUST_SET (only if entering at EL1): CNTHCTL_EL2.EL1PCTEN, CNTVOFF consistency, HCR_EL2.APK/API, ICC_SRE_EL2 (GICv3 v3 mode)
- NOT_APPLICABLE (already satisfied by the working ABL/TZ stack that boots Stock Linux): SCR_EL3.*, CPTR_EL3.*, SMCR_EL3.*

SECONDARY_ENTRY_STATE_UNKNOWN: HCR_EL2.APK/API, CNTHCTL_EL2.EL1PCTEN,
CNTVOFF consistency — all matter only for EL1 entry; the first probe
deliberately does not test them. DAIF is a contract MUST, but a future P1
trampoline can mask interrupts explicitly before entering Linux, so it is
not a first-probe blocker and is not encoded in the delay table. Endianness:
kernel normalizes EE (record_mmu_state CPU_LE path flips EE before C code),
Image flags bit 0 = 0 (LE); not encoded. I-cache: protocol allows on/off
(P0 already proves the instruction path executes), so
ICACHE_RUNTIME_PROBE_REQUIRED=NO.

## 6. Probe architecture

`scripts/r3-p1/p1-entry-state-probe.S` — the P0-proven ARM64 Image header
model: offset 0 valid header (code0/code1 both branch to 0x40), text_offset
0x80000, image_size 0x2220000, flags 0xa, PE offset 0, magic ARM\x64.
code0 branches to `probe_entry`, NOT to Mainline primary_entry. The probe is
register-only: system register reads, integer arithmetic, branches, CNTPCT,
and one PSCI SMC. Nothing else.

Absolute physical S is still not needed: the probe inherits the same
`fastboot boot` placement P0 proved, and never touches memory.

## 7. CurrentEL-safe SCTLR reads

The probe reads CurrentEL FIRST and branches before touching any SCTLR:

- EL1 (x == 4): reads SCTLR_EL1 only
- EL2 (x == 8): reads SCTLR_EL2 only
- anything else (EL0, EL3, unknown encoding): sentinel bucket, no SCTLR read at all

This is strictly more conservative than the kernel's own
`record_mmu_state` (which reads SCTLR_EL1 unconditionally before its EL2
override — safe only under the documented contract). The CI disassembly gate
asserts the exact instruction order and that `mrs …, sctlr_el1` sits inside
the EL1 block, `mrs …, sctlr_el2` inside the EL2 block, and no sctlr read
exists on the unexpected path.

## 8. M/C encoding

From the current-EL SCTLR, the probe extracts only:

- M = SCTLR_ELx bit 0 (SCTLR_ELx_M = BIT(0), sysreg.h:770)
- C = SCTLR_ELx bit 2 (SCTLR_ELx_C = BIT(2), sysreg.h:768)

via `tbz x2, #0` (M) and `tbz x2, #2` (C). The bit numbers are not trusted
from memory: CI re-derives them from the pinned linux-6.6 headers
(`--mode bit-position-pin`) and the disassembly gate asserts the tbz
immediates and the index arithmetic.

## 9. Delay table (preregistered before any device run)

STATE → DELAY mapping, delay = 4 + 4 × (4·[EL==EL2] + 2·M + C):

```
EL1 M0 C0 -> 4s
EL1 M0 C1 -> 8s
EL1 M1 C0 -> 12s
EL1 M1 C1 -> 16s
EL2 M0 C0 -> 20s
EL2 M0 C1 -> 24s
EL2 M1 C0 -> 28s
EL2 M1 C1 -> 32s
unexpected -> 36s
```

4s spacing; one single boot decodes EL, M and C. The mapping is
preregistered here before any true-device run and must not be re-picked
after seeing results. DAIF/I-cache/endianness are deliberately not encoded
(section 5).

## 10. P0 timing calibration (decoder reference only)

- A8 overhead: 6.148s (14.148 − 8)
- A24 overhead: 6.141s (30.141 − 24)
- reference overhead: (6.148 + 6.141) / 2 = 6.1445s

The overhead is a decoder calibration constant, not a claim of permanent
constancy. Future decoding: programmed bucket ≈ (BOOTING_OKAY → kernel_start)
− 6.1445s, using the exact A8/A24 /proc/uptime back-calculation; ADB
first-seen is never the primary decoder.

## 11. Tolerance preregistration

```
TIMING_TOLERANCE_STRONG=0.75
TIMING_TOLERANCE_SUPPORTED=1.5
```

STRONG: |observed − expected| ≤ 0.75s. SUPPORTED: ≤ 1.5s. Outside: the run
is INCONCLUSIVE for that bucket — it is NOT evidence that the probe did not
execute (P0 already proved the wrapper executes). With 4s buckets the ±1.5s
windows do not overlap (4 − 3 = 1s margin). Fixtures
(`--mode decoder-fixtures`) lock the mapping, reverse decoding, window
non-overlap, and the calibration math; window re-picking after a device run
is forbidden.

## 12. PSCI reset

Termination is the P0-proven PSCI SYSTEM_RESET, function id 0x84000009,
SMC conduit (`smc #0`), x1=x2=x3=0, then `wfe` spin. THYME_PSCI_CONDUIT=SMC
(sm8250.dtsi/kona.dtsi `arm,psci-1.0`, method="smc"). No watchdog, no PMIC
MMIO, no unknown reset mechanism is reintroduced. P0_TIMER_SOURCE=CNTPCT;
P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET.

## 13. No-stack / no-memory proof

P1_STATE_PROBE_POSITION_INDEPENDENT=YES, NO_STACK=YES, NO_MEMORY_READ=YES,
NO_MEMORY_WRITE=YES, NO_ABSOLUTE_ADDRESS=YES, ELF_RELOCATIONS=0.

Enforcement layers: source gate (forbidden tokens in the .S), disassembly
gate (full ordered instruction sequence check + global reject of str/stp/
ldr-memory/ldp/sp/adrp/msr/eret/bl/cntvct), ELF gates (zero relocations, no
UND symbols, no .data/.bss/.got/.rodata sections), header gate (Image fields
+ code0/code1 both target 0x40), and negative controls that must be
REJECTED: unknown-RAM store, stack use, EL1-path SCTLR_EL2 read, unknown
PSCI function id, absolute-address relocations. CI proves binary semantics,
mapping, layout and position independence only (section 14); the real
CurrentEL/M/C values require the future single device probe.

## 14. GHA validation

Public workflow `.github/workflows/thyme-r3-entry-state-probe.yml`
(branch route-b-v3; assembles the probe for gates but does not splice M5D
and does not emit a boot image):

- `source-audit`: actionlint, py_compile, `--mode source-gate` (doc/workflow/script pins, notation-fix assert), no-tracked-binary boundary
- `ram-reconciliation`: pinned linux-6.6 + 2 DTS patches → RT-D rebuilt byte-identical → `--mode bit-position-pin` + `--mode ram-reconciliation` (JSON vs DTS vs built DTB, SHA-pinned)
- `probe-gates`: pinned LLVM 18.1.3 → `--mode decoder-fixtures` + `--mode assemble-gates` (disassembly sequence gate, EL-safe SCTLR windows, global rejects, negative controls, header fields, mapping table, tolerances, calibration) → text-only artifact, no .img anywhere

Private workflow `ChuenSan/thyme-mainline-private-ci
thyme-r3-entry-state-probe.yml` (workflow_dispatch, pinned public source
commit): downloads the exact M5D boot artifact (run 34487382191,
SHA-pinned 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63),
runs decoder-fixtures + `--mode build` = everything above plus M5D splice,
envelope gates (header v3, ramdisk/cmdline byte-MATCH, diff confined to the
kernel payload, boot size 35110912, kernel payload 35101184, deterministic
0x00 padding), envelope negative fixtures, and uploads
`thyme-r3-entry-state-probe.img` + manifest + SHA256SUMS + DO_NOT_FLASH.txt.
No device operation anywhere.

## 15. Future device safety (design only this round)

If a later stage is approved, it still uses the active slot A with
`fastboot boot` only: no set_active, no flash, no erase —
PARTITION_WRITES=0, SLOT_A_WRITTEN=NO, Current B (M5D+M5H+M5M-B) untouched.
The observer is the A24-improved form: it never stops on USB NONE or
transient events; primary signal BOOTING_OKAY→kernel_start via /proc/uptime
back-calculation, secondary ADB/boot_completed; observation window ≥ 75s
(max bucket 36s + overhead + margin). Exactly ONE probe boot per approval
stage — no repeated probing.

## 16. Future decoder (preregistered)

For observed delta D_obs = kernel_start − T_BOOTING_OKAY:
programmed = D_obs − 6.1445s; classify against the section 9 table with the
section 11 tiers. One boot yields exactly one of the nine buckets. If the
bucket is 4/8/12/16s the entry was EL1; 20/24/28/32s → EL2; 36s → unexpected
EL. Combined M/C decode from the low two bucket bits. ADB/USB events stay
secondary-only.

## 17. Result branches (future, after a single approved device probe)

- EL1 or EL2 with M=0 and C=0 → ENTRY_STATE_PRIMARY_CONTRACT=SATISFIED →
  next stage MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI (normal Image + RT-D
  + built-in /init + x0 trampoline closed together).
- M=1 or C=1 → do NOT go to P1B; enter
  MAINLINE_V2_R3_ENTRY_STATE_NORMALIZATION_CI: identity mapping / physical
  placement must be closed before any SCTLR.M clear (a plain `msr SCTLR,
  clear M` is forbidden while PC may depend on the active mapping).
- CurrentEL not EL1/EL2 → R3_ENTRY_STATE_UNEXPECTED_EL; no Mainline handoff;
  failure/source isolation.
- Timing bucket INCONCLUSIVE → R3_ENTRY_STATE_PROBE_SIGNATURE_INCONCLUSIVE;
  it does NOT mean "probe did not execute" (P0 proved the wrapper);
  proceed to probe failure isolation.

## 18. P1B prerequisites and gate

- P1_CLEAN_IMAGE_REBUILD_PENDING=YES — the clean 6.6.156 Image build stays
  out of this round on purpose (one big variable at a time; state first,
  then normal Linux payload, then built-in /init).
- M5N FROZEN — the current path (ABL shim proven, RAM map complete, RT-D
  complete) makes entry state the highest-value unknown; target/fixup
  dissection stays frozen.
- RT-D frozen at SHA `4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`
  until P1B explicitly approves a new version; M1 raw is never a fallback.

Round gate logic:

- All CI gates green → READY_FOR_R3_ENTRY_STATE_PROBE_DEVICE_CONTROL (still
  no device operation; a separate approval stage is required for the single
  true-device probe).
- Any CI gate red → R3_ENTRY_STATE_PROBE_CI_NOT_READY.
- RAM reconciliation failure (would-be semantic error) →
  R3_ENTRY_STATE_PROBE_BLOCKED_BY_RAM_ERROR. (Actual outcome: docs-only
  notation error, sources correct, gate green.)

## 19. Artifact

Private build (green): run 34678013953
(`ChuenSan/thyme-mainline-private-ci` thyme-r3-entry-state-probe.yml,
public source pin d91ead3149ee355fe0b047debfa853e0eff27b02); artifact
`thyme-r3-entry-state-probe-d91ead3149ee355fe0b047debfa853e0eff27b02`.
`thyme-r3-entry-state-probe.img` 35,110,912 bytes, SHA256
`cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c`;
kernel payload 35,011,184 bytes, SHA256
`d81649685153dd3f666a99b4ce9ef6fb89c223c51f46961c0f48256d8cdb7c10`;
probe code < 4096 bytes, SHA256
`071ef7f71af1dfba37d904d96c480541367921b9c256c10867ba39a52cb064c2` +
deterministic 0x00 padding (35,100,948 bytes, SHA256
`8fff44835e1159de3b42e145bd94b916007f89143474d901b38c1b83e4b923f2`).
Build determinism cross-checked: an independent run reproduced the same
boot/kernel/probe SHAs. `R3_ENTRY_STATE_PROBE_GATES=PASS` recorded in
`p1-entry-state-probe-gates.txt` and `entry-state-probe-manifest.txt`
(artifact) and in mem0; the mapping table and toolchain pin are embedded
in the manifest. No multiple true-device variants exist; negative mutants
are CI-only and never packed as boots.

Device: NO OPERATION this round. Current B (M5D + M5H + M5M-B) UNCHANGED.
Next if READY: MAINLINE_V2_R3_ENTRY_STATE_PROBE_TRUE_DEVICE — WAIT FOR USER
APPROVAL.

---

## 20. TRUE DEVICE RESULT (MAINLINE_V2_R3_ENTRY_STATE_PROBE_TRUE_DEVICE, 2026-09-12)

### 20.1 Constraints

```
mem0 read:                          YES (start + before bootloader)
local build:                        NO
GHA-only artifact:                  YES (downloaded, never rebuilt)
partition writes:                   0
Slot A written:                     NO
set_active:                         NO
flash/erase:                        NO
experimental boots:                 1 (single fastboot boot)
```

### 20.2 Artifact identity (full SHA check before execution)

Authoritative artifact from private run 34678013953, downloaded from GHA
(archive 10293405077) and re-hashed locally; manifest values asserted equal:

```
boot   size 35110912           MATCH (manifest ESP_BOOT_SIZE=35110912)
boot   SHA256 cb61889af66ec41b5a1cb61c1db84049c46d3e197446ab8bced11313adbee82c   MATCH
kernel SHA256 d81649685153dd3f666a99b4ce9ef6fb89c223c51f46961c0f48256d8cdb7c10   MATCH
probe  SHA256 071ef7f71af1dfba37d904d96c480541367921b9c256c10867ba39a52cb064c2   MATCH
```

### 20.3 Android A baseline (pre)

`slot_suffix=_a`, `boot_completed=1`, root uid=0 (magisk), Stock
`4.19.157-perf-g9d90dd04aa7c`.

### 20.4 Current B pre-test (read-only, zero writes)

```
boot_b[0,35110912)        4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH  (M5D)
vendor_boot_b[0,548864)   2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH  (M5H)
vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
dtbo_b whole              c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8 MATCH  (M5M-B)
```

### 20.5 Fastboot preflight

`adb reboot bootloader` → fastboot present. `product=thyme`,
`unlocked=yes`, `current-slot=a`, `snapshot-update-status=none`,
`battery-soc-ok=yes` (4377 mV),
`slot-retry-count:a=6 slot-unbootable:a=no slot-successful:a=yes`,
`slot-retry-count:b=7 slot-unbootable:b=no slot-successful:b=no`.
current-slot=a confirmed; no set_active.

### 20.6 Timeline (host observer, ISO UTC)

```
T_COMMAND_START      2026-09-12T06:46:42.213Z
T_SENDING_OKAY       2026-09-12T06:46:43.094Z   Sending OKAY [0.833s]
T_BOOTING_OKAY       2026-09-12T06:46:43.315Z   Booting OKAY [0.221s], rc=0
T_USB_NONE           2026-09-12T06:46:44.715Z
T_FASTBOOT_DISAPPEAR 2026-09-12T06:46:44.718Z
T_USB_FIRST_REENUM   2026-09-12T06:47:01.421Z   usb=18d1:4ee7
T_ADB_FIRST_SEEN     2026-09-12T06:47:02.288Z
kernel_start         2026-09-12T06:46:53.408Z   (primary, ADB_FIRST snapshot)
T_BOOT_COMPLETED     2026-09-12T06:47:11.506Z   boot_completed=1, bootreason=bootloader
```

Fastboot acceptance: Sending OKAY + Booting OKAY. The observer never stopped
on USB NONE / transient events; no stable Fastboot return occurred
(AUTOMATIC_FASTBOOT_AFTER_PROBE=NO, FASTBOOT_TRANSIENT_ENUMERATION_ONLY=NO).
Observer note: the summary print aborted after all event capture
(post-observation script KeyError); every primary event and both ADB
snapshots were logged before that point, so no observation data was lost.

### 20.7 kernel_start calculation (P0 formula, unchanged)

kernel_start = host_wallclock_before_uptime_read − /proc/uptime.

- Primary (ADB_FIRST): host_before 2026-09-12T06:47:02.288Z − uptime 8.88s
  → kernel_start 2026-09-12T06:46:53.408Z
- Consistency (BOOT_COMPLETED): host_before 06:47:11.547Z − 18.16s →
  2026-09-12T06:46:53.387Z (21 ms spread, same second)

### 20.8 Timing decode

```
OBSERVED_TOTAL (BOOTING_OKAY→kernel_start, primary)  10.094s
reference overhead (P0 A8/A24 mean)                   6.1445s
OBSERVED_PROGRAMMED_DELAY = 10.094 − 6.1445           3.949s
BOOT_COMPLETED consistency: 10.072 − 6.1445           3.928s
nearest bucket                                        4s
ERROR = 3.949 − 4                                     −0.051s
verdict (|ERROR| ≤ 0.75)                              STRONG
```

### 20.9 Decoded state (frozen section 7/9 table, applied as registered)

```
CurrentEL: EL1
SCTLR_EL1.M = 0
SCTLR_EL1.C = 0
```

Entry contract:

```
ENTRY_EL_ALLOWED=YES (EL1 is contract-legal; EL2 RECOMMENDED not required)
ENTRY_MMU_OFF=YES
ENTRY_DCACHE_OFF=YES
ENTRY_STATE_PRIMARY_CONTRACT=SATISFIED
FULL_ARM64_ENTRY_CONTRACT_PROVEN=NO (DAIF, I-cache coherency, EL2 ancillary
state remain source-audit / future-requirement items; not this round's claim)
```

### 20.10 Recovery

Automatic reset observed (probe → PSCI SYSTEM_RESET → Android A).
`fastboot reboot` not needed; no manual recovery (MANUAL_RECOVERY=NO).
Android A restored: `slot_suffix=_a`, `boot_completed=1`, root uid=0, Stock
`4.19.157-perf-g9d90dd04aa7c`, `bootreason=bootloader`.
ANDROID_A_RESTORED=YES.

### 20.11 Current B post-test (read-only, zero writes)

Identical four hashes as §20.4 — all MATCH.
CURRENT_B_UNCHANGED_AFTER_STATE_PROBE=YES.

### 20.12 Dumps (read-only, nothing cleared)

```
pstore     0 entries
logdump    UNCHANGED  3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
rawdump    UNCHANGED  254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
minidump   REWRITTEN  8fd35ac81a70d214615751243a28287f73ce5403515fbc4bccb94b453de773cd (boot-time dump, not state evidence)
oops       REWRITTEN  b0a2f1ac7100a06eeedee5c028771bd4a8527a9424a5714e2ec37f8eb11e16b6 (boot-time delta, not state evidence)
```

NO_STATE_PROBE_PERSISTENT_DUMP_EVIDENCE=YES — the probe has no persistent
log design; minidump/oops deltas are not state evidence and are not
interpreted further.

### 20.13 Causal boundary

Only CurrentEL, M, C are claimed from this run. No inference of I-cache
state, DAIF, CNTVOFF, CNTHCTL, or Mainline entry-readiness follows from
probe success; those stay source-audit / future requirements (§4, §5).

### 20.14 Final gate and next branch

```
R3_ENTRY_STATE_PRIMARY_CONTRACT_SATISFIED
P1B executed: NO
M5N: FROZEN
Device final: Android A (active slot A preserved)
```

Recommended next (requires explicit user approval, no automatic device run):
MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI — clean normal 6.6.156 Image
build, RT-D frozen at `4849743…f327`, deterministic built-in /init,
PC-relative x0 trampoline, geometry validation; no true-device run in that
CI stage.
