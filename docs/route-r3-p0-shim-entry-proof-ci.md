# Route R3 P0 — shim entry-proof CI

Stage: `MAINLINE_V2_R3_P0_SHIM_ENTRY_PROOF_CI`

Construct and validate the minimum mechanism that can later prove:

```text
ABL executed the first shim instruction we supplied
```

This round is CI / source validation only. No device operation.

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
kernel payload size:  35101184
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
clang-18=1:18.1.3-1
lld-18=1:18.1.3-1
llvm-18=1:18.1.3-1
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

This round: `DEVICE_OPERATION=NO`. Even if READY, do not `fastboot boot`.

---

## 16. P1 blockers

```text
P1_BLOCKED_BY_P0_ENTRY_PROOF=YES
P1_RELOCATION_BLOCKED_BY_LOAD_ADDRESS=YES
```

---

## 17. Final Gate

Binary identity (A8/A24 SHA) is filled after private CI. Until then:

```text
PRIVATE_CI_STATUS=PENDING
P0_A8_BOOT_SHA256=PENDING_PRIVATE_CI
P0_A24_BOOT_SHA256=PENDING_PRIVATE_CI
```

Evidence already in-tree for the non-binary READY inputs:

```text
FASTBOOT_BOOT_PRECEDENT=YES
FASTBOOT_BOOT_CONTEXT_SAFE=STRONGLY_SUPPORTED
PSCI_CONDUIT=KNOWN (SMC)
PSCI_SYSTEM_RESET_SUPPORTED=YES
```

After private CI `BINARY_GATES=PASS`:

```text
READY_FOR_R3_P0_A8_ENTRY_PROOF_DEVICE_CONTROL=PENDING_PRIVATE_CI
```

Invalid controls (CI must REJECT): bad ARM64 magic, wrong boot header
version, kernel size mismatch, boot total size mismatch, branch target
outside payload, ELF relocations present, absolute address dependency,
unknown memory store, wrong timer sysreg, PSCI conduit mismatch,
unexpected ramdisk diff, unexpected cmdline diff.

Primary route: R3 bootshim. Secondary: M5N targeting isolation (frozen).
