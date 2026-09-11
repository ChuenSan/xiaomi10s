# Route R3 — thyme copydown / bootshim CI design

Successor (P0 entry-proof CI): `docs/route-r3-p0-shim-entry-proof-ci.md`

Stage: `MAINLINE_V2_R3_THYME_COPYDOWN_BOOTSHIM_CI_DESIGN`

Architecture / CI design only. No device operation. No local build, unpack,
disassembly, or layout validation. No flashable experiment.

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
M5M-B auto-execution this round:   NO
file/directory deletion:           NO
reference repos:                   read-only
```

Final Gate:

```text
R3_THYME_BOOTSHIM_DESIGN_NEEDS_ADDRESS_EVIDENCE
```

Not `READY_FOR_DEVICE`. Not `FLASHABLE_READY`.

---

## 1. M5M-B status reconciliation

Commit under audit:

```text
short:     f75a917
full SHA:  f75a917e155a56c288bfe60c6fdf5717c87537cc
date:      2026-09-11 19:46:19 +0800
author:    ChuenSan <109579119+ChuenSan@users.noreply.github.com>
parent:    fb486b1  (M5M-A true-device result)
next:      d9195dc  (R3 lmi audit; docs only)
files:
  A  docs/route-b-mainline-v2-m5m-b-fixup-with-marker-control.md
  M  docs/route-b-mainline-v2-m5m-target-fixup-marker-factorial.md
M5M-B document: docs/route-b-mainline-v2-m5m-b-fixup-with-marker-control.md
```

The R3 audit, this prompt's freeze, and `f75a917` disagree on paper:

| Claim | Source | Content |
|---|---|---|
| A | R3 audit + this round freeze | M5M-B reserved / not auto-run; Current B = M5M-A |
| B | this round freeze | Current B = exact M5D + M5H + M5M-A; active A |
| C | `f75a917` | M5M-B true-device result; Current B = M5D + M5H + M5M-B |

Classification of `f75a917` content:

```text
TRUE_DEVICE_RESULT
```

Not `CI_PREPARATION`, not `PRE-REGISTERED_TEMPLATE`, not `IMPORTED_RESULT`,
not `STALE/ERRONEOUS_DOC`.

Evidence present in the document (same class as accepted M5M-A `fb486b1`):

```text
device timestamps:   YES  T_REBOOT_CMD_ISO=2026-09-11T11:30:44.416Z
                          T_DISAPPEAR_ISO=2026-09-11T11:30:44.602Z
                          MANUAL_RECOVERY_TIME_ISO=2026-09-11T11:42:39Z
                          (685s delta matches MANUAL_RECOVERY_TIME=685s)
dtbo SHA:            YES  PREWRITE 128bcd31… (Candidate A)
                          POSTWRITE c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
B boot count:        YES  1; SECOND_B_BOOT_FORBIDDEN=YES
Android A recovery:  YES  set_active a; ANDROID_A_RESTORED=YES
runtime observation: YES  CASE=B1 PRIMARY_OBSERVATION=>12s
commit chain:        YES  fb486b1 → f75a917; no later device-doc restore
mem0 record:         NO   mem0 last Current-B memory is 2026-09-10 M5D-CI pending
live re-read:        NO   forbidden this round
```

Internal consistency vs M5M-A (not title-guessing):

```text
M5M-A T_REBOOT 11:15:38Z  battery-voltage=4413  dtbo PRE=L1 POST=A
M5M-B T_REBOOT 11:30:44Z  battery-voltage=4414  dtbo PRE=A  POST=B
PREWRITE boot/vendor SHAs held exact M5D + M5H
ONLY_WRITE=dtbo_b
Candidate A dtbo NOT restored
```

```text
M5M_B_TRUE_DEVICE_RESULT_AUTHORITATIVE=YES
```

Do **not** drop `f75a917` from the factorial runtime. The 2×2 is complete:

```text
T0/M1  L1  target-path="/"      marker PRESENT  4.837s
T0/M0  A   target-path="/"      marker ABSENT   4.834s
T1/M0  L2  target + __fixups__  marker ABSENT   >12s
T1/M1  B   target + __fixups__  marker PRESENT  >12s
```

Why R3 / this freeze still said Current B = M5M-A:

1. The R3 prompt froze M5M-A and forbade auto-running M5M-B. That freeze was
   not updated after `f75a917`.
2. `d9195dc` recorded the contradiction and refused to reconcile by flashing.
3. No later commit restores Candidate A. M5M-B doc: `Candidate A dtbo NOT restored`.
4. mem0 was never updated for M5M-A or M5M-B, so mem0 cannot be used as
   identity. It is stale from M5D CI.

There is no documented restore of the M5M-A artifact after B. This round does
not flash to “align” the freeze.

```text
M5M_B_PENDING=NO
AUTHORITATIVE_M5M_B_STATUS=RUN_AND_VALIDATED
```

---

## 2. Authoritative current B

Last real device identity evidence is M5M-B post-write / post-recovery, not
the document title and not the stale freeze.

```text
AUTHORITATIVE_CURRENT_B=
  exact M5D boot_b prefix 35110912
    SHA256 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
  + M5H board45 single Stock DTB0 vendor_boot_b
    prefix 548864 SHA256 2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9
    remainder SHA256 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52
  + M5M-B target+fixup/with-marker dtbo_b whole
    SHA256 c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
  active: Slot A
  ANDROID_A_RESTORED=YES

CURRENT_B_LIVE_RECONFIRMED=NO
CURRENT_B_ASSUMED_FROM_LAST_CONFIRMED_DEVICE_STATE=NO
USER_ROUND_CONSTRAINT_UNCHANGED=M5D+M5H+M5M-A   # no-write freeze only; stale vs last POSTWRITE
IF_USER_RESTORED_A_OFF_RECORD=UNOBSERVABLE
```

This round: device unchanged.

---

## 3. lmi architecture summary (reference, not thyme values)

Level 1 from `refs/sm8250-xiaomi-lmi-boot` default
`linux-copydown-embedded-dtb.S.in` + `scripts/mkboot-linux-copydown-lmi.sh`.

```text
LMI_DTB_DECOUPLING=YES
ABL_DIRECT_ENTRY_OBJECT=copydown bootshim
NOT Linux Image
NOT EFI stub
```

```text
Xiaomi ABL
  → gunzip(boot.img kernel)   [lmi header v2]
  → shim _start (ARM64 Image header at decompressed offset 0)
  → copy Linux Image from _start+0x200000 down onto _start
  → discard ABL x0
  → x0 = embedded runtime DTB
  → x1=x2=x3=0
  → br _start  (now Linux Image)
```

```text
Linux source:        label linux_image, .balign 0x200000
Linux destination:   _start / ABL load
runtime DTB:         after copy_entry, 0x1000-aligned
x0 before:           ABL-provided DT, discarded
x0 after:            embedded runtime DTB
final jump:          branch Linux entry (Image header at dest)
CONFIG_EFI:          is not set
vendor_boot:         unused in success pack
dtbo:                stock left unmodified, not flashed
packaging:           boot header v2 --dtb STOCK_DTB
flash environment:   fastbootd  (not thyme bootloader fastboot + slot B)
```

Physical ABL load on lmi is UNKNOWN (header `kernel_offset=0x8000` is
FROM_IMAGE_HEADER only). Same rule applies to thyme.

### LMI_TO_THYME_ADDRESS_MAPPING

| field | lmi | thyme |
|---|---|---|
| source (Linux Image in payload) | `_start+0x200000` HARDCODED | KNOWN as relative offset G; G not copied; CI-computed |
| destination | `_start` / ABL load | KNOWN relative (`_start`); physical S UNKNOWN |
| runtime DTB | after copy_entry, 0x1000 align | KNOWN relative; must be ≥ image_size from `_start` |
| gap | 0x200000 HARDCODED | NOT_APPLICABLE as a copied constant; candidate only |
| entry after copy | `_start` (Linux header) | KNOWN relative; physical UNKNOWN |
| header kernel_offset | 0x8000 FROM_IMAGE_HEADER | NOT_APPLICABLE in boot v3 (vendor_boot 0x8000 packaging) |
| board-id / UART | 37 / uart12 | NOT_APPLICABLE |

---

## 4. thyme boot v3 differences

```text
LMI_V2_PACKAGING_DIRECTLY_PORTABLE_TO_THYME_V3=NO
```

| Item | lmi success | thyme stock / Route B |
|---|---|---|
| boot header | v2 | v3 |
| pagesize in boot.img | yes (4096) | no; boot v3 page is fixed 4096 pad after 1580 B header |
| kernel_addr in boot.img | yes | **no** (lives in vendor_boot) |
| ramdisk_addr / tags / dtb in boot.img | yes | **no** |
| cmdline in boot.img | yes | empty; vendor cmdline in vendor_boot |
| `--dtb` / v2 DTB field | STOCK_DTB in boot.img | **absent**; DTB is vendor_boot field |
| appended kernel_dtb after gzip | yes | **not** used; kernel field is raw Image |
| vendor_boot | unused | required v3; vendor ramdisk + concatenated DTBs |
| dtbo | stock unmodified | ABL-facing overlay; current factorial variable |
| flash | fastbootd, boot only | bootloader fastboot, explicit `*_b` |
| kernel compression | gzip(shim) | raw Image (stock 4.19 and M0–M5D) |

```text
THYME_ABL_KERNEL_DECOMPRESSION_BEHAVIOR=UNKNOWN  # gzip path untested
THYME_UNCOMPRESSED_IMAGE_KERNEL_FIELD=KNOWN      # stock + M0–M5D accepted
```
Do not select gzip for P0/P1.

AOSP `tools/aosp/mkbootimg.py`: DTB is written to **vendor_boot** when
`header_version in {3,4}`. `write_header_v3_and_above()` has no DTB field.
lmi `--dtb STOCK_DTB` cannot be copied onto thyme `boot.img`.

```text
THYME_ABL_FACING_DTB_SOURCE_HYPOTHESIS=COMBINATION
confidence: HIGH
```

ABL-facing DT is vendor_boot DTB (selected index) **plus** dtbo overlay.
Not boot.img appended DTB. Evidence: stock-rom-analysis, CAF ABL v3
`GetImage("vendor_boot")` + `LoadAndValidateDtboImg`, M5E/M5H/M5K factorial.

---

## 5. Current M5D layout

Authoritative boot reference (CI reports + M0 unpack of the same packaging
lineage; M5B–M5D are in-place Image-header patches, not `mkbootimg` rebuilds):

```text
M5D_BOOT_IMAGE_LAYOUT
  file size:                 35110912
  SHA256:                    4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
  magic:                     ANDROID!
  header version:            3
  header size:               1580          (AOSP BOOT_IMAGE_HEADER_V3_SIZE)
  page size:                 4096          (BOOT_IMAGE_HEADER_V3_PAGESIZE)
  kernel payload offset:     0x1000
  kernel payload size:       35101184
  ramdisk offset:            35106816      (align(0x1000+35101184, 4096))
  ramdisk size:              595
  os version:                13.0.0
  os patch level:            2023-09
  cmdline:                   empty
  DTB field:                 ABSENT (v3)
  second:                    ABSENT
  partition capacity:        201326592     (GPT boot_* / BOARD_BOOTIMAGE_PARTITION_SIZE VAB)
  boot image total size:     35110912  <<  201326592
```

M5D Image (kernel payload = exact Image):

```text
type:          uncompressed ARM64 Image  (not Image.gz; M0 CI rejects 1f8b)
size:          35101184
SHA256:        5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a
magic:         ARM\x64
code0:         0x146c7028     b primary_entry
code1:         0x146c7027     b primary_entry (from offset 4)
text_offset:   0x80000
image_size:    0x2220000 = 35782656     (file + ~681472 BSS/reserve)
flags:         0xa   LE, 4K pages, PHYS_BASE=1 (48-bit range, not “near DRAM”)
res2/3/4:      0
PE offset:     0     (M5D); real PE payload still at Image[0x40:0x10000]
primary_entry: Image offset 0x1b1c0a0, first word 0x14000000 (b .)
ramdisk SHA:   b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
```

M5B/M5C/M5D header scans did not change the ~4.7s path under Mainline-ish DT.
They remain layout/entry-contract inputs, not the current DTBO blocker.

---

## 6. Load-address evidence

```text
ABL physical kernel load: UNKNOWN
```

Do not treat vendor_boot `kernel_addr=0x8000` as a copy destination.
R3 already classified that class as FROM_IMAGE_HEADER. Physical 0x8000 is
also implausible for a 35 MiB Image (vector table / low SRAM).

### THYME_LOAD_ADDRESS_EVIDENCE_MATRIX

| SOURCE | VALUE | CONFIDENCE |
|---|---|---|
| android-device-sm8250-common `BoardConfigCommon.mk` `BOARD_KERNEL_BASE` | `0x00000000` | HIGH as mkbootimg `--base`; NOT physical DRAM |
| same `BOARD_KERNEL_PAGESIZE` | 4096 | HIGH |
| same `BOARD_BOOT_HEADER_VERSION` (VAB) | 3 | HIGH |
| M1 validator `--kernel_offset` | `0x00008000` | HIGH as packaging; NOT proven ABL copy dest |
| same `--ramdisk_offset` | `0x01000000` | HIGH as packaging |
| same `--tags_offset` | `0x00000100` | HIGH as packaging |
| same `--dtb_offset` | `0x01f00000` | HIGH as packaging |
| stock vendor_boot unpack | kernel_addr=0x8000 ramdisk_addr=0x01000000 tags=0x100 dtb_addr=0x1f00000 page=4096 header=2112 | HIGH as on-disk header |
| GPT `boot_*` | 201326592 | HIGH |
| Lineage `BOARD_BOOTIMAGE_PARTITION_SIZE` VAB | 201326592 | HIGH |
| Lineage `BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE` | 100663296 | HIGH |
| Lineage `BOARD_DTBOIMG_PARTITION_SIZE` | 33554432 | HIGH |
| stock DTB / hardware map DRAM | `memory@80000000` class | HIGH as DRAM window; NOT kernel load |
| Astide `Makefile.boot` 0x80008000 hits | other arches in the kernel tree | NONE for thyme ABL |
| lmi `mkbootimg.args` kernel_offset 0x8000 | lmi header v2 packaging | NONE as thyme physical |
| ARM64 `text_offset` 0x80000 | Image load offset from 2MB-aligned base | HIGH as protocol; ABL honor = UNKNOWN |
| M5C text_offset 0→0x80000 | no 4.7s change under M1 DT | HIGH as non-effect; does not prove ABL ignores the field on Stock DT |
| ABL binary / LinuxLoader | not in tree | N/A |

Future derivation (device-safe, no Slot A, no firmware write):

1. P0 proves whether ABL jumps to payload offset 0. That defines `S` as
   “decompressed kernel start” without naming a number.
2. P1 uses **PC-relative** copydown, which does not need numeric `S`.
3. If P1 Linux fails after P0 proof, next CI tests dest = `S` vs
   `align2MB(S)+text_offset` as a **relative** pad, still without claiming
   `0x80000000`.
4. Do not use ramdump / serial / Slot A as the address oracle.

---

## 7. Image entry calculation

```text
THYME_MAINLINE_ENTRY_CALCULATION
  boot partition file offset of kernel:     0x1000
  Android kernel payload offset:            0
  ABL physical load S:                      UNKNOWN
  ARM64 Image logical entry:                Image+0  (code0), protocol “call the Image”
  M5D primary_entry file offset:            0x1b1c0a0
  code0 displacement:                       0x146c7028 → PC+0x1b1c0a0
  do NOT enter at text_offset 0x80000
  after copydown onto S:                    Linux code0 at S; primary_entry at S+0x1b1c0a0
```

`text_offset` is a **placement** field (Image[0] should sit
`text_offset` bytes past a 2MB-aligned base). It is not the branch target.

---

## 8. ARM64 entry contract

From `linux-6.6/Documentation/arch/arm64/booting.rst` and
`arch/arm64/kernel/head.S` (not from the lmi shim).

```text
THYME_SHIM_KERNEL_ENTRY_CONTRACT
  x0:     physical address of DTB in system RAM, 8-byte aligned, ≤2MiB
  x1:     0
  x2:     0
  x3:     0
  EL:     non-secure EL2 recommended, or EL1; DAIF masked
  MMU:    protocol: off. 6.6 head.S record_mmu_state() can disable if on
  D-cache: protocol: kernel image cleaned to PoC; head.S assumes D-cache off
           or handles MMU-on via record_mmu_state
  I-cache: on or off; no stale entries for the loaded image
  interrupts: masked
  Image placement: text_offset from a 2MB-aligned base; ≥image_size bytes free
  DTB:    not in a 2MB block that needs special mapping; not overlapping
          Image[0, image_size)
  initrd: if present, inside a 1GB-aligned ≤32GB window covering the Image
```

`preserve_boot_args` saves x0 into `boot_args` / x21. Wrong x0 is consumed
in `setup_arch`, not before `primary_entry`.

---

## 9. Candidate shim architectures

### A — SHIM_FIRST_COMPOSITE

ABL kernel payload:

```text
[0, H)     ARM64 Image-compatible shim header + trampoline
[H, G)     padding
[G, G+K)   Mainline Image
[D, D+Dlen) runtime DTB
```

Shim copies or jumps, sets x0, branches.

### B — SHIM + APPENDED PAYLOAD (lmi-shaped, thyme geometry recomputed)

```text
[0, 0x40)           ARM64 header (code0 = b shim_entry; PE offset 0)
shim_entry          adrp/br copy_entry
.balign G           linux_image  (.incbin uncompressed Image)
.balign 0x1000      copy_entry   (must sit outside dest [0, Klen))
.balign 0x1000      runtime_dtb
.balign 0x1000      image_end
```

Default lmi success path. G is **not** copied from lmi as a thyme constant;
CI must compute the minimum G that satisfies §13.

### C — MINIMAL TRAMPOLINE

If ABL already loaded the payload at a runnable Image address: do not move
the Image. First executed code only:

```text
set x0 = embedded runtime DTB
x1=x2=x3=0
cache/barrier if any stores
br Mainline Image entry
```

lmi sibling `linux-jump.S.in` is this shape (diagnostic, not the published
success pack).

No candidate is declared “best” from names. Selection is in §11.

---

## 10. Minimal trampoline evaluation

```text
THYME_MINIMAL_TRAMPOLINE_POSSIBLE=LIKELY
```

Why not YES: numeric `S` and 2MB alignment are UNKNOWN; DTB must still sit
outside `image_size`.

Why not NO:

- M5E: exact M5D Image + Stock DT pair → `>12s` (4.7s wall gone). Same Image
  has `primary_entry b .`. That is consistent with ABL jumping into the
  payload, or with ABL hanging. P0 exists to split those.
- M5A: Stock 4.19 `b .` at known-good entry → `>12s`. Kernel-side spin can
  occupy the `>12s` class.
- flags `0xa` PHYS_BASE=1 does not require “near DRAM”.
- P0 does not need a copy.

Why LIKELY rather than YES: M4B `b .` under M1 DT still returned in 4.755s,
so a trampoline under a 4.7s DT context cannot prove entry. Trampoline P0
must use a `>12s` ABL-facing context (Stock/L2 family), not target-path.

---

## 11. Relocation requirement

```text
THYME_REQUIRED_IMAGE_RELOCATION_MODE=UNKNOWN
```

Not COPYDOWN just because lmi’s success template is named copydown.
Not DIRECT just because flags look friendly.

Recommended **implementation sequence** (not a claim that thyme “is copydown”):

```text
P0  DIRECT / Candidate C   entry proof, no Image copy
P1  relative COPYDOWN / Candidate B
    dest = ABL load (_start)
    src  = _start + G
    reason: S-independent; DTB and copy_entry stay outside
            [0, image_size); forward copy is valid for dest < src even if G < Klen
```

COPYUP would be required only if dest > src (not the ABL-load-as-dest model).
`RELOCATE_TO_FIXED_DESTINATION` is forbidden until a physical dest is proven.

---

## 12. Composite payload layout

P0 (entry proof only):

```text
THYME_SHIM_PAYLOAD_LAYOUT_P0
  offset 0:     ARM64 Image header, code0 = b p0_entry, text_offset=0x80000,
                flags=0xa, magic ARM64, PE offset 0, no MZ
  p0_entry:     CNTVCT delay (P0-A 8s / P0-B 24s) then PSCI SYSTEM_RESET
                (SMC 0x84000009 then HVC 0x84000009) then wfe spin
  no Linux Image
  no runtime DTB
  pack: uncompressed kernel field, boot header v3, exact M0 ramdisk reuse
```

P1 (Mainline handoff):

```text
THYME_SHIM_PAYLOAD_LAYOUT_P1
  let Klen   = rebuilt Image file size   (pin vs M5D 35101184 if reused)
  let Isize  = Image header image_size   (pin vs 0x2220000 if reused)
  let Dlen   = runtime DTB size          (M1 raw 105960)
  G          = CI-computed, 0x1000-aligned, ≥ 0x1000
               MUST satisfy §13; 0x200000 is a candidate not a copy from lmi

  offset 0:              shim ARM64 header + shim_entry (br copy_entry)
  offset G:              uncompressed Mainline Image
  offset align(G+Klen, 0x1000): copy_entry
  offset align(copy_end, 0x1000): runtime DTB  (must be ≥ Isize from _start)
  offset align(dtb_end, 0x1000): image_end  → shim hdr image_size
```

Boot v3 pack:

```text
mkbootimg --header_version 3 --pagesize 4096
          --kernel shim_bin          # uncompressed
          --ramdisk exact M0 cpio.gz # 595 B, SHA b7d39494…
          --os_version 13.0.0 --os_patch_level 2023-09
          --cmdline ""
# no --dtb
```

ABL-facing DT stays in vendor_boot + dtbo, not in this boot.img.

---

## 13. Layout constraints / overlap proof

```text
S     = ABL load base                         UNKNOWN
H     = shim size before linux_image          < G
Ksrc  = S + G
Kdst  = S
Klen  = Image file size
Isize = image_size field
D     = S + runtime_dtb_offset
Dlen  = DTB size
```

Must hold (all PC-relative; numeric S not required):

```text
G > 0
copy direction: forward (dest < src)
copy_entry_offset >= Klen          # PC not in dest [0, Klen)
runtime_dtb_offset >= Isize        # DTB not in Linux BSS/reserve
runtime_dtb_offset % 8 == 0
Dlen <= 2MiB
copy_entry_offset % 0x1000 == 0
linux_image offset == G            # adrp target
boot_size <= 201326592
header_version == 3
Image SHA / DTB SHA pin
entry of Linux after copy = Kdst + 0  (code0), and code0 lands in Image
x0 == D and FDT magic d00dfeed at D
```

Worked check on **current** M5D sizes if G=0x200000 (candidate, not assumed):

```text
Klen=35101184  Isize=35782656  G=2097152
copy_entry ≥ G+Klen = 37198336 > Klen          PASS (PC outside dest)
37198336 > Isize=35782656                      PASS (DTB outside image_size)
dest [0, Klen) overlaps src [G, G+Klen)
  but dest < src → forward copy is valid memmove   PASS
shim at 0 is overwritten by Linux after copy;
  copy_entry is not at 0                           PASS
stack: none (no stack in P1 copy loop)             N/A
```

```text
Overlap proof (relative copy + DTB vs image_size): PASS for that G
Overlap proof (physical 2MB+text_offset placement of S): UNKNOWN
THYME_BOOTSHIM_LAYOUT_CONSTRAINTS overall: UNKNOWN until S alignment is known
```

That is why the stage Gate is `NEEDS_ADDRESS_EVIDENCE`, not `NOT_SAFE`
(relative copy is safe) and not `FEASIBLE` as a full P1 Linux placement.

---

## 14. Runtime DTB baseline

Candidates:

| | kernel usability | source fidelity | overlay independence | size | known state |
|---|---|---|---|---|---|
| A historical M1 raw | unknown `/memory` | HIGH (pinned DTS build) | YES if shim drops ABL x0 | 105960 | SHA a91a512d… |
| A' M1 ABL metadata | same + msm-id/board-id | packaging-only fdtput | YES for Linux | 106026 | SHA cefafcca… |
| B M5I symbolized | worse (phandles/__symbols__) | same DTS + DTC `-@` | N/A (overlay still fails) | 143886 | `M5I_SYMBOLIZED_OVERLAY_STILL_INCOMPATIBLE` |
| C future cleaned runtime-only | intended | not built | YES | unknown | does not exist |

```text
R3_RUNTIME_DTB_BASELINE=historical M1 raw
SHA256=a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
size=105960
```

Reason: Linux must not consume Stock DTB0, Stock merged DT, or M5M overlay
output. M5I symbolization exists to feed Stock entry21, which a shim
bypasses. ABL metadata (`qcom,msm-id` / `qcom,board-id`) is ABL-facing, not
a Linux requirement. Future C (real `/memory` from stock map, no ABL
selectors) is the P1.1 DTB, not the first pin.

Known P1 gap: public thyme DTS has no `/memory` size. Do not invent
`0x80000000` ranges in this design. Flag `RUNTIME_DTB_MEMORY_MAP=UNRESOLVED`.

---

## 15. Runtime DTB placement

```text
THYME_RUNTIME_DTB_PLACEMENT_REQUIREMENTS
  8-byte alignment
  not inside [Kdst, Kdst+Isize)
  in RAM Linux can see (described later or inherited)
  not overlapping reserved-memory once a map exists
  still valid at early boot (not overwritten by copy or BSS)
  not overlapping shim PC during copy
  FDT totalsize ≤ 2MiB
  no 2MB block that must be mapped with special attributes
```

---

## 16. ABL-facing context baseline

Bootshim is not “ignore ABL”. ABL must still accept vendor_boot+dtbo and
branch. Linux then drops that x0.

```text
>12s ≠ shim execution ≠ kernel execution ≠ boot success
```

Known runtimes with exact M5D boot held:

| Context | vendor_boot | dtbo | runtime |
|---|---|---|---|
| S  Stock/Stock (M5E) | stock 4-concat | stock 29-entry | >12s |
| M5H | single Stock DTB0 board-id 45 | stock (then later overlays) | >12s with stock dtbo |
| M5K Cell D | M1 one-entry | stock entry21 | >12s |
| L2 | M5H | target+fixups empty overlay | >12s |
| M5M-B | M5H | target+fixups + marker | >12s |
| target-path family (M1/L1/M5M-A) | Mainline-ish / one-entry | target-path="/" | ~4.8s |

```text
R3_ABL_FACING_CONTEXT_BASELINE=Context S
  exact Stock vendor_boot
  + exact Stock dtbo
reason:
  highest Stock fidelity
  M5E already showed this pair suppresses the 4.7s wall with the exact
  M5D Image that a shim would replace
  matches lmi’s idea: ABL sees stock DT, Linux does not
  does not depend on explaining target-path vs __fixups__
```

L2 / M5K are backups if Stock dtbo is later shown to block the **jump**
(today that is not proven; `>12s` is untyped). Do not pick them by guess.

```text
ABL_FACING_CONTEXT_REQUIREMENT=
  a DT pair with which ABL has historically left the 4.7s class
  (Stock/Stock or other >12s Stock-DTB0 family)
  plus a P0 checkpoint that is not “>12s”
```

DTBO still matters: ABL may have to apply it before branching. Shim discards
the merge for Linux. M5M-B remains research for ABL overlay encoding, not a
P0 dependency.

---

## 17. vendor_boot and dtbo roles

```text
vendor_boot: ABL-facing DTB + vendor ramdisk + page/addr/cmdline
dtbo:        ABL-facing overlay; Linux x0 after shim is independent
```

Public CI: source-only. Stock vendor_boot / dtbo stay in **private** CI.
Do not upload OEM binaries.

---

## 18. Cache maintenance

lmi:

```text
dc cvau over dest and over DTB   (line size from CTR_EL0.DminLine)
dsb ish
ic iallu
dsb ish
isb
```

thyme plan — same **sequence class**, not a paste of lmi addresses:

```text
THYME_SHIM_CACHE_MAINTENANCE_PLAN
  P0: no Image stores. If only GPRs change: isb before delay/SMC is enough.
      If P0 writes a marker: clean that VA to PoC.
  P1: after copy, clean [Kdst, Kdst+Klen) and [D, D+Dlen) to PoC by VA
      (dc cvau / cvac), dsb ish, ic iallu, dsb ish, isb.
  why: booting.rst requires the loaded kernel image cleaned to PoC and no
       stale I-cache. Shim is the bootloader for Linux after ABL.
  dc cvau with MMU off is implementation-defined; inherit ABL. Do not add
       set/way walks in P0/P1.
```

---

## 19. EL / MMU policy

```text
THYME_SHIM_EL_POLICY=PRESERVE
THYME_SHIM_ENTRY_MODE=DIRECT_ARM64_IMAGE
```

Unknown until proven: exact EL, SCTLR, whether MMU is on. 6.6 `head.S`
already records MMU state. Do not ERET, do not write SCTLR, do not emulate
EFI. `CONFIG_EFI` of the **formal** kernel config is not changed this
design; P1 Image may keep the current M5D binary (PE payload present,
PE offset 0, code0 raw branch).

---

## 20. P0 shim checkpoint

`b .` is not proof (M4B 4.755s). Checkpoint must sit at ABL direct-entry
offset 0 and produce **two** controlled host outcomes.

```text
SHIM_EXECUTION_CHECKPOINT=TIMED_PSCI_RESET_PAIR
```

```text
P0-A  CNTVCT delay ~8s  then PSCI SYSTEM_RESET (0x84000009 SMC, then HVC), else wfe
P0-B  CNTVCT delay ~24s then same reset
NEG  invalid ARM64 magic / kernel_size too small  (ABL should not enter shim)
```

Expected, under Context S, 12s+ observation:

| Artifact | If ABL enters shim and PSCI works | If ABL never enters | If enters but PSCI dead |
|---|---|---|---|
| NEG | not 8s/24s band | 4.7s or >12s hang | n/a |
| P0-A | Fastboot ~8s+overhead | same as NEG | >12s |
| P0-B | Fastboot ~24s+overhead | same as NEG | >12s |

```text
SHIM_ENTRY=YES  iff P0-A and P0-B land in distinct programmed bands
                and NEG does not
```

No Slot A write, no firmware write, no USB, no GPIO, no memory-marker
readback. CNTFRQ is assumed programmed by ABL (protocol); if both delays
collapse, that is a failed checkpoint, not a Linux conclusion.

Do not ship P0 and P1 as one artifact.

---

## 21. P1 Mainline handoff

Only after P0 `SHIM_ENTRY=YES`.

```text
ABL → shim (already proven) → copy Image if using Candidate B
  x0 = embedded M1 raw DTB
  x1=x2=x3=0
  br Linux code0 at dest
  Linux primary_entry at dest+0x1b1c0a0 (or rebuilt equivalent)
```

Success ladder, not Ubuntu:

1. kernel executes (new checkpoint, not `>12s`)
2. known initramfs (reuse P15 `/init`, 15s then `reboot,bootloader`)
3. later USB gadget / NCM / `10.66.73.1` (stock-kernel control already
   proved that userspace path; do not port lmi Ubuntu/systemd/Docker)

---

## 22. CI workflow design

Public file (this round, source-audit only):

```text
.github/workflows/thyme-r3-bootshim-ci.yml
```

This round’s public job must **not** assemble a boot image, must **not**
emit a flashable artifact, must **not** touch a device.

Future private builder (`ChuenSan/thyme-mainline-private-ci`), after a
separate approval:

1. pin linux `8b73de7da85fde281a385e0b26eda9bffd3ca477` (6.6.156)
2. pin patch queue `d470701d58d62bf10b96adb4dbf0c639945afccd45d4d3f039e8051e7aaaf1b5`
3. build Image (or reuse exact M5D Image SHA for P0)
4. build runtime DTB (M1 raw pin)
5. assemble shim (GHA only)
6. construct composite payload
7. pack boot v3 (no `--dtb`)
8. validate layout / entry / x0 / overlap / partition / header version
9. if using Stock vendor_boot/dtbo identity: private-only compare
10. emit **private** artifacts, split:

```text
R3-P0 entry-proof boot image
R3-P1 Mainline-handoff boot image
```

OEM binaries: private CI only. Public tree stays source-only.

---

## 23. Fail-closed gates

```text
wrong Image SHA                         FAIL
wrong DTB SHA                           FAIL
shim overlaps destination               FAIL
runtime DTB overlaps Image/Isize        FAIL
runtime DTB outside allowed region      FAIL
Linux entry outside Image               FAIL
x0 not DTB / bad FDT magic              FAIL
partition overflow (>201326592)         FAIL
wrong boot header version (≠3)          FAIL
gzip kernel selected without evidence   FAIL
lmi physical addresses hardcoded        FAIL
copied board-id 37 / UART12 / 0x200000 without CI proof  FAIL
unexpected vendor_boot identity         FAIL  (private)
unexpected dtbo identity                FAIL  (private)
READY_FOR_DEVICE emitted from this stage FAIL
```

---

## 24. Unresolved unknowns

```text
ABL physical kernel load S
whether S is 2MB-aligned
whether ABL honors text_offset
whether ABL gunzips the kernel field
EL and SCTLR at ABL→payload
whether Stock/Stock >12s is jump-to-payload or ABL hang
runtime DTB /memory map
CNTFRQ usable for P0 delay
PSCI SYSTEM_RESET available at shim EL
```

---

## 25. Route recommendation

```text
PRIMARY_ENGINEERING_ROUTE=ROUTE_BS_BOOTSHIM
  next: MAINLINE_V2_R3_P0_SHIM_ENTRY_PROOF_CI   (GHA; no device in that CI)
SECONDARY_CAUSAL_RESEARCH_ROUTE=M5N_TARGETING_MECHANISM_ISOLATION
  M5M-B is complete; targeting reverse-engineering is not a P0 blocker
```

Bootshim is primary because lmi proves ABL-DT / Linux-DT decoupling on the
same SoC vendor, and thyme’s remaining 4.7s class is DT-handoff shaped.
M5M-B answered the marker cell; it does not need to be re-run.

```text
DEVICE_STATE=UNCHANGED
NO_DEVICE_OPERATION=YES
WAIT_FOR_USER_APPROVAL=YES
```
