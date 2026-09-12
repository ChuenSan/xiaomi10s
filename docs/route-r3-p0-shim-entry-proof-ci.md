# Route R3 P0 — shim entry-proof CI + A8/A24 timing pair

CI stage: `MAINLINE_V2_R3_P0_SHIM_ENTRY_PROOF_CI` — complete.
A8 device: `MAINLINE_V2_R3_P0_A8_ENTRY_PROOF_TRUE_DEVICE_CONTROL` — complete.
A24 device: `MAINLINE_V2_R3_P0_A24_ENTRY_PROOF_CONFIRMATION` — complete.
Final Gate: `MAINLINE_V2_R3_P0_TIMING_PAIR_ENTRY_PROVEN`

Construct and validate the minimum mechanism that can later prove:

```text
ABL executed the first shim instruction we supplied
```

CI round (§1–17) is source / GHA validation only.
True-device A8 is §18. True-device A24 is §26. P1 was not executed.

CI-round constraints (device A8/A24 are §18 / §26):

```text
mem0 read:                         YES
LOCAL_BUILD:                       NO
LOCAL_VALIDATION:                  NO
LOCAL_VALIDATOR:                   NO
LOCAL_SOURCE_GATE:                 NO
LOCAL_ACTIONLINT:                  NO
LOCAL_BINARY_VALIDATION:           NO
GHA_ONLY:                          YES
DEVICE_OPERATION:                  NO
ADB_DEVICE_CHANGE:                 NO
FASTBOOT:                          NO
FLASH:                             NO
SET_ACTIVE:                        NO
B_BOOT:                            NO
Slot A written:                    NO
M5N auto-execution this round:     NO
P1 binary design this round:       NO
file/directory deletion:           NO
PRIVATE_P0_BUILDER=ChuenSan/thyme-mainline-private-ci
```

Predecessor: `docs/route-r3-thyme-copydown-bootshim-ci-design.md`

---

## 1. Authoritative current device state

mem0 still contains older Current-B rows (M5D / L1 / M5M-A). Those are not
identity. Last true-device document and mem0 M5M-B row agree:

```text
commit:  f75a917e155a56c288bfe60c6fdf5717c87537cc
class:   TRUE_DEVICE_RESULT
runtime: PRIMARY_OBSERVATION=>12s
B boots: 1
ANDROID_A_RESTORED: YES
```

```text
AUTHORITATIVE_M5M_B_STATUS=RUN_AND_VALIDATED
AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B
```

Exact current B (last POSTWRITE / post-recovery; this round does not re-read live):

```text
boot_b prefix 35110912
  SHA256 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
vendor_boot_b prefix 548864
  SHA256 2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9
vendor_boot_b remainder
  SHA256 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52
dtbo_b whole 33554432
  SHA256 c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
active: Slot A
DEVICE_UNCHANGED this round
```

---

## 2. M5M-B reconciliation

`f75a917` is a true-device result, not a template. Factorial 2×2 is complete:

```text
T0/M1  L1  target-path="/"      marker PRESENT  4.837s
T0/M0  A   target-path="/"      marker ABSENT   4.834s
T1/M0  L2  target + __fixups__  marker ABSENT   >12s
T1/M1  B   target + __fixups__  marker PRESENT  >12s
```

```text
TARGET_FIXUP_MECHANISM_EFFECT=STRONGLY_SUPPORTED
MARKER_MAIN_EFFECT=NOT_SUPPORTED
SECONDARY_CAUSAL_ROUTE=M5N_TARGETING_ISOLATION
```

M5N is frozen this round. Primary engineering route is R3 bootshim P0.

---

## 3. Why P0 does not need the ABL physical load address

P0 is not a Linux handoff. It does not copy an Image, does not place a DTB,
does not use a stack, and does not store to RAM.

Execution is PC-relative from whatever address ABL loaded the payload.
`S = ABL physical load address = UNKNOWN` does not affect assembler
correctness.

```text
P0_POSITION_INDEPENDENT=YES
P0_REQUIRES_PHYSICAL_LOAD_ADDRESS=NO
ABL_PHYSICAL_LOAD_ADDRESS=UNKNOWN
```

---

## 4. Why P1 still needs it later

P1 relocates a Mainline Image and/or plants a runtime DTB. Relative copydown
can avoid a numeric `S`, but proving dest vs `align2MB(S)+text_offset` and
non-overlap with reserved RAM still needs either `S` or a proof that a direct
trampoline needs no copy.

```text
P1_BLOCKED_BY_P0_ENTRY_PROOF=YES
P1_RELOCATION_BLOCKED_BY_LOAD_ADDRESS=YES
```

---

## 5. Fastboot boot precedent

```text
THYME_FASTBOOT_BOOT_PRECEDENT=YES
```

At least one completed device experiment used `fastboot boot <boot.img>`
rather than `flash boot_b` + `set_active b`:

```text
experiment:   Route A first RAM-only boot
artifact:     experimental-boot-v2.img
              SHA256 ae32736c59bd21b02abcf0f1263ace2c5b46569c4a387585dd92d34948f5034b
              GHA run 34116449773  commit 29bc752
host command: fastboot boot experimental-boot-v2.img
acceptance:   Sending OKAY, Booting OKAY
              Fastboot USB dropped; protocol later answered
              current-slot remained a
```

Route A was later `ROUTE_A_REFUTED` as a Linux path. That does not retract
ABL acceptance of `fastboot boot`.

v3 RAM-boot was analysed, not used as the Route B success path
(`docs/route-b-v3-boot-chain.md`, `docs/route-b-v3-final-report.md`).

---

## 6. Active-slot context on temporary fastboot boot

CAF ABL `CmdBoot` + `LoadImageAndAuth` (QcomModulePkg FastbootCmds.c):

```text
downloaded image Name="boot", NumLoadedImages=1
v3+ still loads "vendor_boot" from the current slot
v3+ still loads "dtbo" from the current slot
```

```text
FASTBOOT_BOOT_USES_ACTIVE_SLOT_VENDOR_CONTEXT=YES
  vendor_boot source: vendor_boot_<active-slot>   CONFIRMED_CAF_ABL
  dtbo source:        dtbo_<active-slot>          CONFIRMED_CAF_ABL
  active slot kept A: YES on the Route A RAM boot
  Xiaomi ABL fork:    INFERRED same CmdBoot path
```

If future P0 uses `current-slot=a` + `fastboot boot P0.img`:

```text
ABL-facing = Stock vendor_boot_a + Stock dtbo_a + temporary P0 boot
PARTITION_WRITES=0
set_active: NO
Slot B M5M-B identity retained
```

That is Context S (M5E Stock/Stock already left the 4.7s class).

```text
FASTBOOT_BOOT_CONTEXT_SAFE=STRONGLY_SUPPORTED
P0_FUTURE_EXECUTION_MODE=FASTBOOT_BOOT
```

v3 `fastboot boot` itself is CAF-confirmed, Xiaomi-inferred, not a new
thyme v3 RAM-boot log. Not marked weaker than STRONGLY_SUPPORTED because
the v2 device RAM-boot plus CAF v3 CmdBoot both exist.

P0 future design forbids `set_active b` + timed PSCI reset: that would
risk a second B boot. Not proven that reset enters Fastboot instead of
active B.

---

## 7. PSCI conduit evidence

Do not hard-code both SMC and HVC. Audit:

| source | path | property | value | confidence |
|---|---|---|---|---|
| Mainline SoC DTS | `linux-6.6/arch/arm64/boot/dts/qcom/sm8250.dtsi` `/psci` | `compatible` | `arm,psci-1.0` | HIGH |
| same | same | `method` | `"smc"` | HIGH |
| downstream SoC DTS | `android-kernel-sm8250/arch/arm64/boot/dts/vendor/qcom/kona.dtsi` `/psci` | `compatible` | `arm,psci-1.0` | HIGH |
| same | same | `method` | `"smc"` | HIGH |
| thyme overlay | `thyme-sm8250.dtsi` | `/psci` | not overridden | HIGH |
| DT binding | `linux-6.6/Documentation/devicetree/bindings/arm/psci.yaml` | `method` enum | `smc` / `hvc`; `smc` means SMC #0 | HIGH |
| kernel UAPI | `linux-6.6/include/uapi/linux/psci.h` | `PSCI_0_2_FN_SYSTEM_RESET` | `PSCI_0_2_FN(9)` = `0x84000009` | HIGH |

```text
THYME_PSCI_CONDUIT=SMC
THYME_PSCI_VERSION=1.0
THYME_PSCI_SYSTEM_RESET_SUPPORTED=YES
P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET
```

One conduit, one function. No PSCI_VERSION probe, no HVC fallback.

---

## 8. Generic timer

ARM64 `Documentation/arch/arm64/booting.rst`: CNTFRQ programmed; if the
kernel is entered at EL1, `CNTHCTL_EL2.EL1PCTEN` must be set. That is the
EL1/EL2 access contract ABL already satisfies to boot Linux.

Project M2/M3 used `CNTFRQ_EL0 + CNTPCT_EL0` at `primary_entry`.

```text
P0_TIMER_SOURCE=CNTPCT
```

Read-only: `mrs cntfrq_el0`, `mrs cntpct_el0`. No interrupt, no comparator,
no `msr` to timer control. `isb` before counter reads matches Linux
`arch_timer` ordering.

64-bit wrap: unsigned `elapsed = counter - start` (`b.hs` on `elapsed < target`
inverted). 24 s even at 1 GHz is ~2.4e10 ticks, far below 2^64, so the
test window also does not need extra wrap logic.

---

## 9. No-stack / no-memory-write

```text
NO_STACK=YES
NO_DATA_WRITE=YES
NO_UNKNOWN_MEMORY_ACCESS=YES
P0_X0_POLICY=IGNORE_AND_PRESERVE
```

Leaf A64 only. x0 is not dereferenced. It is overwritten only when loading
the PSCI function ID immediately before `smc #0` (after the timed proof).
No C runtime, BSS, GOT, or literal pool pointing outside the payload.

GHA must prove: ELF relocations NONE, unexpected sections NONE, external
symbols NONE, no `str`/`stp`/`ldr` from RAM.

---

## 10. M5D-preserving ARM64 Image

Keep M5D header geometry. Only the kernel payload bytes change.

```text
boot header:          v3
boot size:            35110912
M5D boot SHA256:      4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
kernel payload size:  35101184
M5D Image SHA256:     5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a
ramdisk:              exact M5D, SHA256 b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
cmdline:              empty MATCH
text_offset:          0x80000
image_size:           0x2220000
flags:                0xa
PE offset:            0
pack method:          splice P0 kernel into exact M5D boot at 0x1000
```

code0/code1: `b p0_entry` at payload offset `0x40` (after the 64-byte
header). Not M5D `primary_entry`.

```text
P0_CODE0_TARGET_OFFSET=0x40
```

Padding: byte `0x00` to 35101184. No uninitialised bytes.

---

## 11. A8 / A24 pair

Same source. Only `-DP0_DELAY_SECONDS`.

```text
P0-A8      delay 8s     device candidate after CI
P0-A24     delay 24s    confirmation candidate, later stage
P0-RESET0  delay 0s     CI/reference only, not recommended for device
```

Future true-device: one experimental boot per stage. A8 first, wait for
approval, then A24. Host signature is Android A return moving ~16 s.

A single 8 s return could coincide with a watchdog. The pair isolates the
shim timer.

---

## 12. Position independence

Linked at VMA 0 with PC-relative `b` / `mrs` / `movz` only. Runs at unknown
`S`. Production binaries must not contain DRAM constants such as
`0x80000000` in the shim body.

---

## 13. Boot v3 packaging

No v2 DTB field. Header 1580, page 4096, kernel then ramdisk. Geometry
must match M5D including reserved zeros and empty cmdline.

```text
P0_VS_M5D_DIFF_CLASSIFICATION=KERNEL_PAYLOAD_ONLY
```

---

## 14. Private artifact policy

Public tree: source only (`scripts/r3-p0/*`, this doc, public workflow).

Private GHA downloads exact M5D boot from private run `34487382191`
artifact `thyme-mainline-v2-m5d-pe-offset-zero-1a30f48d5ef86ff2dce7df6f761ca925f60aa9e7`,
assembles with pinned LLVM, splices, validates, uploads:

```text
thyme-r3-p0-a8-entry-proof-boot.img
thyme-r3-p0-a24-entry-proof-boot.img
```

RESET0 and `p0-neg-bad-image-magic.bin` are CI-only. OEM vendor_boot/dtbo
are not uploaded.

Toolchain pin (private runner `ubuntu-24.04`, Ubuntu noble packages):

```text
clang-18=1:18.1.3-1ubuntu1
lld-18=1:18.1.3-1ubuntu1
llvm-18=1:18.1.3-1ubuntu1
LLVM_VERSION=18.1.3
```

---

## 15. Future device safety

```text
future current-slot=a
fastboot boot thyme-r3-p0-a8-entry-proof-boot.img
no flash boot_a / boot_b / vendor_boot / dtbo
no set_active b
PSCI SYSTEM_RESET -> normal active A
```

Second B boot risk: avoided if FASTBOOT_BOOT is used. Slot-B + PSCI reset
is forbidden until reset-to-Fastboot is proven.

CI round: `DEVICE_OPERATION=NO`. A8 later used this exact `fastboot boot` path; see §18.

---

## 16. P1 blockers

```text
P1_BLOCKED_BY_P0_ENTRY_PROOF=YES
P1_RELOCATION_BLOCKED_BY_LOAD_ADDRESS=YES
```

---

## 17. Final Gate

Private CI run [`34615985929`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34615985929)
public source `5382eb77e688a8478be998ecf0a7c148ef684abd`
private wrapper `872918873a6002203178efaa4f4bf16808b532fe`.

```text
PRIVATE_CI_STATUS=PASS
LLVM_VERSION=18.1.3
LLVM_PKG=1:18.1.3-1ubuntu1
P0_A8_DELAY=8
P0_A8_BOOT_SIZE=35110912
P0_A8_BOOT_SHA256=a3c17cd4108ff3ad88aa36291e7dacea584caeea96f17ed4b12881aa3aeef1da
P0_A8_KERNEL_SHA256=b9b8bf52669239288337cf3d249bca0efd74f2dd8bde0d99ba1465fb2476c7c4
P0_A8_SHIM_SHA256=393ba3ff08453843e5d040385eb7991092090ad221d9c3ed794e2a365757c38a
P0_A24_DELAY=24
P0_A24_BOOT_SIZE=35110912
P0_A24_BOOT_SHA256=098481cd1fb5907e15c9256f4c180d69277c0795e479d63d08a77e7dcf6988d3
P0_A24_KERNEL_SHA256=70824f5194601283201f3bbcf94787939c78f9af68120244bb899ca368b697d9
P0_A24_SHIM_SHA256=757e6fe3c7d4070643f1b3cab6a01959ebe0955f200ff35fa7f42bb9004ccd03
A8_A24_DELTA_ISOLATED=YES
A8_A24_KERNEL_OFFSET=73
movz_x2_a8=0xd2800102
movz_x2_a24=0xd2800302
P0_VS_M5D_DIFF_CLASSIFICATION=KERNEL_PAYLOAD_ONLY
FAIL_CLOSED=PASS
```

```text
FASTBOOT_BOOT_PRECEDENT=YES
FASTBOOT_BOOT_CONTEXT_SAFE=STRONGLY_SUPPORTED
PSCI_CONDUIT=KNOWN (SMC)
PSCI_SYSTEM_RESET_SUPPORTED=YES
P0_POSITION_INDEPENDENT=YES
P0_NO_UNKNOWN_MEMORY_ACCESS=YES
P0_NON_KERNEL_M5D_CONTEXT=MATCH
A8_A24_DELTA_ISOLATED=YES
READY_FOR_R3_P0_A8_ENTRY_PROOF_DEVICE_CONTROL=YES
```

CI round left `READY_FOR_R3_P0_A8_ENTRY_PROOF_DEVICE_CONTROL=YES` without booting.
A8 true-device is §18.

Invalid controls (CI must REJECT): bad ARM64 magic, wrong boot header
version, kernel size mismatch, boot total size mismatch, branch target
outside payload, ELF relocations present, absolute address dependency,
unknown memory store, wrong timer sysreg, PSCI conduit mismatch,
unexpected ramdisk diff, unexpected cmdline diff.

Primary route: R3 bootshim. Secondary: M5N targeting isolation (frozen).

---

## 18. P0-A8 true-device — constraints

Stage: `MAINLINE_V2_R3_P0_A8_ENTRY_PROOF_TRUE_DEVICE_CONTROL`

```text
MEM0_READ_BEFORE_R3_P0_A8=YES
MEM0_READ_BEFORE_FASTBOOT=YES
LOCAL_BUILD=NO
LOCAL_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
GHA_ONLY=YES
artifact regeneration=NO
PARTITION_WRITES=0
Slot A written=NO
Slot B written=NO
set_active=NO
flash/erase/format=NO
EXPERIMENTAL_BOOTS=1
command=fastboot boot <exact P0-A8>
P0-A24=NOT AUTHORIZED / NOT EXECUTED
P1=NOT EXECUTED
M5N/M5M experiments=NOT EXECUTED
file/directory deletion=NO
```

Only question this round:

```text
DOES_ABL_EXECUTE_P0_SHIM_ENTRY?
```

A8 is a **positive** entry-proof attempt, not a negative proof.
A single A8 must not be written as `SHIM_ENTRY_PROVEN`.
Strong pair proof is reserved for A24 (`+16s` shift), which is not authorized here.

---

## 19. Preflight identity

Authoritative current B before A8 (must not change):

```text
commit M5M-B: f75a917e155a56c288bfe60c6fdf5717c87537cc
Current B: exact M5D boot + M5H vendor + M5M-B dtbo
active: Slot A
ANDROID_A_RESTORED before A8: YES
```

Live Android A baseline (read-only):

```text
adb wait-for-device
slot_suffix=_a
boot_completed=1
root=uid=0(magisk)
uptime ~10h54m (post-M5M-B Android A session)
product=thyme
```

Live Current B read-only hashes, then STOP if mismatch:

```text
boot_b[0,35110912)
  4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH M5D
vendor_boot_b[0,548864)
  2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9  MATCH M5H
vendor_boot_b[548864,EOF)
  5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52  MATCH M5H
dtbo_b whole 33554432
  c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8  MATCH M5M-B
R3_P0_A8_PRE_B_CONTEXT_MATCH=YES
```

Authoritative P0-A8 from private run [`34615985929`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34615985929),
artifact `thyme-r3-p0-entry-proof-872918873a6002203178efaa4f4bf16808b532fe`.
Downloaded, not rebuilt. Identity read only (size + SHA256), not local validation:

```text
file: thyme-r3-p0-a8-entry-proof-boot.img
size: 35110912 MATCH
SHA256: a3c17cd4108ff3ad88aa36291e7dacea584caeea96f17ed4b12881aa3aeef1da MATCH
GHA SHA256SUMS / p0-run.txt: same boot/kernel/shim SHAs as §17
A24 image present in the same zip: NOT BOOTED
RESET0 / negatives: NOT BOOTED
```

Fastboot preflight after `adb reboot bootloader`:

```text
product=thyme
unlocked=yes
current-slot=a
snapshot-update-status=none
battery-soc-ok=yes
battery-voltage=4370 (4380 at observer start)
slot-retry-count:b=7
slot-unbootable:b=no
slot-successful:a=yes
slot-successful:b=no
slot-retry-count:a=6
slot-unbootable:a=no
USB before boot: 18d1:d00d
```

`current-slot` was `a`. No `set_active`.

---

## 20. Unique experimental boot

Printed then executed once:

```text
R3 P0-A8 SHIM ENTRY PROOF
ACTIVE SLOT: A
PARTITION WRITES: ZERO
SET_ACTIVE: NO
P0 DELAY: 8s
EXPECTED IF SHIM EXECUTES: timer delay → PSCI SYSTEM_RESET → Android A
```

```text
fastboot boot thyme-r3-p0-a8-entry-proof-boot.img
Sending 'boot.img' (34288 KB)  OKAY [  0.824s]
Booting                        OKAY [  0.220s]
Finished. Total time: 1.052s
rc=0
FASTBOOT_BOOT_ACCEPTED=YES
```

No second `fastboot boot`. No A24. No partition write.

---

## 21. Host timeline

Host clocks are UTC. Experimental t0 is `T_BOOTING_OKAY`, not Android boot time.

```text
T_COMMAND_START         2026-09-12T00:18:10.695Z  1789172290.696
T_SENDING_OKAY          2026-09-12T00:18:11.555Z  1789172291.556
T_BOOTING_OKAY          2026-09-12T00:18:11.773Z  1789172291.774
T_FASTBOOT_DISAPPEAR    2026-09-12T00:18:11.793Z  1789172291.793  +0.020s
```

Observer defect (documented, not a 4.7s path):

```text
+0.190s  fastboot devices flickered true (USB drop glitch)
+1.374s  USB=NONE
+2.244s  observer stopped: FINAL_USB=NONE FINAL_FASTBOOT=false FINAL_ADB=false
         device had left Fastboot and had not returned to Fastboot or ADB
```

That sub-second flicker is **not** `P0_A8_4P7S_PATH_OBSERVED`.
Observation continued without a second boot.

Continuation / reconstruction:

```text
T_ADB_FIRST_SEEN (first confirmed)
  2026-09-12T00:18:46.004Z  +34.231s from T_BOOTING_OKAY
  USB=18d1:4ee7  adb=device  fastboot=absent
  lower bound: +2.244s USB NONE / no adb (gap 00:18:14Z–00:18:46Z)
T_BOOT_COMPLETED (first confirmed already=1)
  2026-09-12T00:19:41.807Z  +90.034s
  first moment unknown; do not treat 90s as shim delay
KERNEL_START (host clock − /proc/uptime, tight pair)
  host_before 2026-09-12T00:20:39.092Z  proc_uptime=133.19
  kernel_start 2026-09-12T00:18:25.922Z
  BOOTING_OKAY → kernel_start = 14.148s
  DISAPPEAR → kernel_start = 14.129s
```

Elapsed (do not rename Android userspace time as shim delay):

```text
BOOTING_OKAY → first confirmed ADB            34.231s
DISAPPEAR → first confirmed ADB               34.212s
BOOTING_OKAY → kernel_start                   14.148s
BOOTING_OKAY → boot_completed first confirmed ≤90.034s
```

~14.1s to stock Android kernel start is in the same class as:
programmed 8s delay + firmware/ABL/kernel bring-up after PSCI.
It is **not** a CNTPCT loop measurement.

---

## 22. Android A auto-return and Current B post-test

After the ram-boot, userspace was Stock Android A, not Fastboot, not Mainline:

```text
slot_suffix=_a
boot_completed=1
root=uid=0
uname=Linux 4.19.157-perf-g9d90dd04aa7c #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
sys.boot.reason=bootloader
ro.boot.bootreason=bootloader
ACTIVE_A_PRESERVED_ACROSS_P0_RESET=YES
ANDROID_A_AUTO_RETURNED=YES
AUTOMATIC_FASTBOOT_AFTER_P0=NO
MANUAL_RECOVERY=NO
ANDROID_A_RESTORED=YES
```

`fastboot boot` of the P0 payload cannot become Slot A userspace without a reset.
Automatic Android A return is therefore an automatic reset observation.

Post-test Current B, read-only, zero writes:

```text
boot_b[0,35110912)        4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
vendor_boot_b[0,548864)   2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
dtbo_b whole              c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8 MATCH
CURRENT_B_UNCHANGED_AFTER_P0=YES
```

---

## 23. Dumps

Read-only, nothing cleared. Shim has no persistent log before PSCI reset.

```text
pstore     0 entries
minidump   CHANGED  e8caa0f3… (M5M-B) → e9af8b600da5b61cd1f160854f85e978d862577d69afee624ad2ab3e183e92dc
rawdump    UNCHANGED 254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump    UNCHANGED 3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
logfs      CHANGED   3e5ace76bdd364ecd2b79880855e2a16a9feb79c05c17d91aa743fb2e7d27540
oops       CHANGED   9be27d95bd44c9067e2072d494d3157cf32c9070eb916f6d7bd3188afd7cee8a
NO_P0_PERSISTENT_DUMP_EVIDENCE=YES
```

minidump/oops/logfs deltas are not shim evidence. No 6.6 / mainline kernel ran
(`uname` is Stock 4.19.157-perf).

---

## 24. Causal boundary

Observed:

```text
FASTBOOT_BOOT_ACCEPTED=YES
P0_A8_AUTOMATIC_RESET_OBSERVED=YES
ANDROID_A_AUTO_RETURNED=YES
ACTIVE_A_PRESERVED_ACROSS_P0_RESET=YES
P0_A8_4P7S_PATH_OBSERVED=NO
P0_A8_EXPECTED_RESET_NOT_OBSERVED=NO
P0_A8_ENTRY_SIGNATURE=SUPPORTED
PROVISIONAL_SHIM_ENTRY_EVIDENCE=YES
SHIM_ENTRY_PROVEN=NO
```

Allowed wording: behavior matches A8 shim execution; provisional entry evidence;
timing signature observed (~14.1s to kernel start vs 8s programmed delay).

Forbidden from A8 alone: ABL definitely executed the shim; CNTPCT definitely
ran; PSCI definitely returned on the intended path; P0 fully proven.

Not proven from A8 alone: Mainline kernel, runtime DTB, x0 handoff, copydown,
physical load address, P1.

A24 confirmation is §26. Same path, delay 8→24, host kernel-start timeline
shifted +15.993s versus the frozen A8 14.148s baseline (expected +16.000s).

```text
P1_BLOCKED_BY_P0_ENTRY_PROOF=YES     (A8-only; A24 timing pair is §26)
P1_RELOCATION_BLOCKED_BY_LOAD_ADDRESS=YES
physical load address=UNKNOWN
```

---

## 25. True-device Final Gate

```text
FASTBOOT_BOOT_ACCEPTED=YES
P0_A8_ENTRY_SIGNATURE=SUPPORTED
PROVISIONAL_SHIM_ENTRY_EVIDENCE=YES
CURRENT_B_UNCHANGED_AFTER_P0=YES
ANDROID_A_RESTORED=YES
A24 executed=NO
P1 executed=NO
PARTITION_WRITES=0
EXPERIMENTAL_BOOTS=1
Final Gate=MAINLINE_V2_R3_P0_A8_SIGNATURE_OBSERVED
Next=MAINLINE_V2_R3_P0_A24_ENTRY_PROOF_CONFIRMATION
Device final=Android A
WAIT FOR USER APPROVAL=YES
```

A8 gate above is frozen. A24 confirmation follows.

---

## 26. P0-A24 confirmation — constraints

Stage: `MAINLINE_V2_R3_P0_A24_ENTRY_PROOF_CONFIRMATION`

```text
MEM0_READ_BEFORE_R3_P0_A24=YES
MEM0_READ_BEFORE_FASTBOOT=YES
LOCAL_BUILD=NO
LOCAL_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
GHA_ONLY=YES
artifact regeneration=NO
assemble/link/pack A24=NO
PARTITION_WRITES=0
Slot A written=NO
Slot B written=NO
set_active=NO
flash/erase/format=NO
EXPERIMENTAL_BOOTS=1
command=fastboot boot <exact P0-A24>
P0-A8 re-boot=NO
P1=NOT EXECUTED
M5N/M5M experiments=NOT EXECUTED
RESET0=NOT BOOTED
failure-isolation=NOT EXECUTED
file/directory deletion=NO
```

Only question this round:

```text
DOES_THE_A8_A24_DELAY_CONSTANT_SHIFT_KERNEL_START_BY_~16s?
```

Frozen A8 differential reference (do not re-interpret):

```text
T_BOOTING_OKAY_A8           2026-09-12T00:18:11.773Z
T_FASTBOOT_DISAPPEAR_A8     2026-09-12T00:18:11.793Z
kernel_start_A8             2026-09-12T00:18:25.922Z
BOOTING_OKAY → kernel_start 14.148s
programmed delay            8s
```

Primary metric is Stock Android kernel_start from host wallclock − `/proc/uptime`.
ADB first-seen and boot_completed are secondary (USB enum / userspace variance).

Preregistered tolerance (before the boot, not after):

```text
EXPECTED_TIMING_DELTA=16.000s
STRONG_MATCH     OBSERVED_TIMING_DELTA in 14.5s .. 17.5s
SUPPORTED_MATCH  OBSERVED_TIMING_DELTA in 13.0s .. 19.0s
NO_MATCH         <13s or >19s
```

---

## 27. A24 artifact identity

Authoritative private run [`34615985929`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34615985929).
Downloaded, not rebuilt. Identity read only (size + SHA256):

```text
file: thyme-r3-p0-a24-entry-proof-boot.img
size: 35110912 MATCH
SHA256: 098481cd1fb5907e15c9256f4c180d69277c0795e479d63d08a77e7dcf6988d3 MATCH
kernel SHA256: 70824f5194601283201f3bbcf94787939c78f9af68120244bb899ca368b697d9
shim SHA256:   757e6fe3c7d4070643f1b3cab6a01959ebe0955f200ff35fa7f42bb9004ccd03
delay: 24s
```

GHA A8 vs A24 semantic delta remains DELAY CONSTANT ONLY:

```text
kernel offset 73
A8  movz x2, #0x8   encoding 0xd2800102
A24 movz x2, #0x18  encoding 0xd2800302
```

---

## 28. Android A baseline and Current B (read-only)

Before reboot bootloader:

```text
adb wait-for-device
slot_suffix=_a
boot_completed=1
root=uid=0(magisk)
uname=Linux 4.19.157-perf-g9d90dd04aa7c
uptime=902.16  (same Android A session that auto-returned from A8)
product=thyme
```

Live Current B, then STOP if mismatch:

```text
boot_b[0,35110912)
  4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH M5D
vendor_boot_b[0,548864)
  2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9  MATCH M5H
vendor_boot_b[548864,EOF)
  5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52  MATCH M5H
dtbo_b whole 33554432
  c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8  MATCH M5M-B
R3_P0_A24_PRE_B_CONTEXT_MATCH=YES
```

---

## 29. Fastboot preflight and unique experimental boot

`adb reboot bootloader` at `2026-09-12T00:34:08.305Z`. mem0 re-read immediately before.
`current-slot` was `a`. No `set_active`.

```text
product=thyme
unlocked=yes
current-slot=a
snapshot-update-status=none
battery-soc-ok=yes
battery-voltage=4374 (4385 at observer start)
slot-retry-count:b=7
slot-unbootable:b=no
slot-successful:a=yes
slot-successful:b=no
USB before boot: 18d1:d00d
```

Printed then executed once:

```text
R3 P0-A24 SHIM ENTRY CONFIRMATION
ACTIVE SLOT: A
PARTITION WRITES: 0
SET_ACTIVE: NO
PROGRAMMED DELAY: 24s
REFERENCE A8: 8s
EXPECTED DIFFERENTIAL: +16s
```

```text
fastboot boot thyme-r3-p0-a24-entry-proof-boot.img
Sending 'boot.img' (34288 KB)  OKAY [  0.824s]
Booting                        OKAY [  0.221s]
Finished. Total time: 1.053s
rc=0
FASTBOOT_BOOT_ACCEPTED=YES
```

No second `fastboot boot`. No A8 re-boot. No partition write.

---

## 30. Observer improvements versus A8

A8 observer treated a +0.190s `fastboot devices` flicker as
`FASTBOOT_REAPPEAR_STABLE` and stopped at +2.244s with USB NONE.
That gap is not a 4.7s path; it is an observer defect.

A24 observer:

```text
continue through USB NONE and transient fastboot enumeration
FASTBOOT_TRANSIENT: USB not 18d1:d00d, or present <3s then gone
STABLE FASTBOOT: USB 18d1:d00d AND fastboot_present ≥3s
minimum observe 45s; if no ADB, continue to 60s
stop early only on ADB+boot_completed, stable Fastboot, or 60s empty
on first ADB: immediately host_before + /proc/uptime + slot + uname
```

A24 did not stop on USB NONE. ADB and boot_completed were captured in-window.

---

## 31. A24 host timeline

Host clocks are UTC. Experimental t0 is `T_BOOTING_OKAY`.
Primary kernel_start uses the first ADB tight pair (same formula as A8):

```text
kernel_start = host_before − /proc/uptime
```

```text
T_COMMAND_START         2026-09-12T00:34:34.029Z  1789173274.029
T_SENDING_OKAY          2026-09-12T00:34:34.883Z  1789173274.884
T_BOOTING_OKAY          2026-09-12T00:34:35.104Z  1789173275.104
T_FASTBOOT_DISAPPEAR    2026-09-12T00:34:36.455Z  1789173276.455  +1.351s
T_USB_NONE              2026-09-12T00:34:36.584Z  1789173276.584  +1.480s
T_USB_FIRST_REENUM      2026-09-12T00:35:12.428Z  usb=18d1:4ee7   +37.324s
T_ADB_FIRST_SEEN        2026-09-12T00:35:13.035Z                  +37.931s
T_BOOT_COMPLETED        2026-09-12T00:35:23.501Z                  +48.397s
```

First ADB tight pair (authoritative kernel_start):

```text
host_before  2026-09-12T00:35:13.035Z
proc_uptime  7.79
kernel_start 2026-09-12T00:35:05.245Z
slot_suffix  _a
uname        Linux 4.19.157-perf-g9d90dd04aa7c
root         uid=0(magisk)
boot_completed at first ADB: not yet 1
```

BOOT_COMPLETED tight pair (secondary, not the gate):

```text
host_before  2026-09-12T00:35:23.532Z
proc_uptime  18.3
kernel_start 2026-09-12T00:35:05.232Z
boot_completed=1
```

13 ms kernel_start difference between the two pairs is host/uptime sampling.
Primary remains the first ADB pair.

```text
FASTBOOT_TRANSIENT_ENUMERATION_ONLY=NO
AUTOMATIC_FASTBOOT_AFTER_P0=NO
P0_A24_4P7S_PATH_OBSERVED=NO
MANUAL_RECOVERY=NO
```

---

## 32. A8/A24 differential

```text
                    A8                         A24
programmed delay    8s                         24s
T_BOOTING_OKAY      2026-09-12T00:18:11.773Z   2026-09-12T00:34:35.104Z
kernel_start        2026-09-12T00:18:25.922Z   2026-09-12T00:35:05.245Z
BOOTING → kernel    14.148s                    30.141s
BOOTING → ADB       34.231s (gap)              37.931s
BOOTING → boot_completed  ≤90.034s (late check) 48.397s
```

```text
A24_BOOTING_TO_KERNEL_START = 30.141s
A8_BOOTING_TO_KERNEL_START  = 14.148s
OBSERVED_TIMING_DELTA       = 15.993s
EXPECTED_TIMING_DELTA       = 16.000s
error                       = −0.007s
```

ADB first-seen delta is only +3.700s. That is why kernel_start is primary:
USB enumeration / host polling / adb daemon swamp the 16s delay in ADB-seen.
boot_completed A8 was an upper bound from the observer gap; A24 captured it live.

---

## 33. Pair verdict

Preregistered STRONG window: 14.5s .. 17.5s. Observed 15.993s.

```text
P0_TIMING_PAIR_MATCH=STRONG
P0_A8_ENTRY_SIGNATURE=SUPPORTED
P0_A24_ENTRY_SIGNATURE=SUPPORTED
SHIM_ENTRY_PROVEN_BY_TIMING_PAIR=YES
SHIM_ENTRY_PROVEN=YES
P0_A24_AUTOMATIC_RESET_OBSERVED=YES
ANDROID_A_AUTO_RETURNED=YES
ACTIVE_A_PRESERVED_ACROSS_P0_RESET=YES
```

Allowed: ABL executed the controlled payload entry; the shim timer-controlled
path executed; the programmed delay affected reset timing.

Still forbidden: P1 proven; runtime DTB proven; copydown proven; Mainline
kernel proven; physical load address known.

`fastboot boot` of the P0 payload cannot become Slot A userspace without a
reset. Automatic Android A return is therefore an automatic reset observation.

---

## 34. Android A auto-return and Current B post-test

```text
slot_suffix=_a
boot_completed=1
root=uid=0
uname=Linux 4.19.157-perf-g9d90dd04aa7c #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
sys.boot.reason=bootloader
ro.boot.bootreason=bootloader
ANDROID_A_AUTO_RETURNED=YES
ACTIVE_A_PRESERVED_ACROSS_P0_RESET=YES
AUTOMATIC_FASTBOOT_AFTER_P0=NO
MANUAL_RECOVERY=NO
ANDROID_A_RESTORED=YES
```

Post-test Current B, read-only, zero writes:

```text
boot_b[0,35110912)        4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
vendor_boot_b[0,548864)   2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
dtbo_b whole              c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8 MATCH
CURRENT_B_UNCHANGED_AFTER_A24=YES
```

---

## 35. Dumps

Read-only, nothing cleared. Shim has no persistent log before PSCI reset.

```text
pstore     0 entries
minidump   CHANGED  A8 e9af8b60… → eca37b75a24b035aa081595dd8f153ba533a489d45576758cd36cbb950c523c4
rawdump    UNCHANGED 254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump    UNCHANGED 3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
logfs      CHANGED   babe73bced3c9e218c72c6e021528e2f93bc475548db4f835da6eebc1a0a9efe
oops       CHANGED   bd7ae2f0f4ec3c829a3c7766b61d8f3da3fd9126dd6f0159142423861041e400
NO_P0_PERSISTENT_DUMP_EVIDENCE=YES
```

minidump/oops/logfs deltas are not shim evidence. No 6.6 / mainline kernel ran.

---

## 36. What P0 proven does not buy

Entry is proven. Safe Mainline jump is not.

```text
ABL_KERNEL_PHYSICAL_LOAD_ADDRESS=UNKNOWN   (now P1 highest-priority unknown)
runtime DTB physical placement=UNKNOWN
Image entry physical address=UNKNOWN
overlap vs reserved RAM=UNPROVEN
relocation required?=UNKNOWN
```

Do not jump from this gate to a full lmi copydown. Split:

```text
R3-P1A  LOAD ADDRESS / HANDOFF GEOMETRY CI
R3-P1B  MINIMAL X0 TRAMPOLINE CI
copydown only if geometry allows
```

Primary future route: R3 bootshim handoff.
Secondary: M5N targeting reverse engineering (not executed).
M5M factorial remains complete (T0/M1 4.837s, T0/M0 4.834s, T1/M0 >12s,
T1/M1 >12s); `TARGET_FIXUP_MECHANISM_EFFECT=STRONGLY_SUPPORTED` is an
ABL-facing research line, not this boot path.

---

## 37. A24 Final Gate

```text
FASTBOOT_BOOT_ACCEPTED=YES
P0_A8_ENTRY_SIGNATURE=SUPPORTED
P0_A24_ENTRY_SIGNATURE=SUPPORTED
P0_TIMING_PAIR_MATCH=STRONG
SHIM_ENTRY_PROVEN_BY_TIMING_PAIR=YES
SHIM_ENTRY_PROVEN=YES
CURRENT_B_UNCHANGED_AFTER_A24=YES
ANDROID_A_RESTORED=YES
P1 executed=NO
M5N executed=NO
PARTITION_WRITES=0
EXPERIMENTAL_BOOTS=1
Final Gate=MAINLINE_V2_R3_P0_TIMING_PAIR_ENTRY_PROVEN
Next=MAINLINE_V2_R3_P1_HANDOFF_GEOMETRY_CI
Device final=Android A
WAIT FOR USER APPROVAL=YES
```
