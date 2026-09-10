# Route B Mainline V2 M5A — stock kernel entry spin control

Status: CI artifact ready. Final gate:
`READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL`.
This phase performed no device operation.

M4B placed `b .` at Mainline `primary_entry`. The automatic Fastboot return was
still 4.755s. That does not prove ABL entered Mainline, and it does not prove an
unconditional firmware watchdog. M5A is the known-good control: the exact stock
4.19 kernel that already reached userspace HTTP, with the same earliest-entry
self-branch.

## Hypothesis

```text
Question:
  is the ~4.7s automatic Fastboot return independent of kernel execution?

Control:
  exact Stage4 stock 4.19.157-perf kernel
  + exact Stage4 ramdisk
  + future exact stock vendor_boot/dtbo context
  + one 4-byte entry self-branch
```

M4B already removed timer, MMIO, PSCI, and exception instructions from the
Mainline instrumentation. The remaining ambiguity is whether any executable
kernel payload can remain running past ~4.7s after ABL handoff.

Stock 4.19 is the only kernel whose handoff is already proven on this device.

## Why stock control

Stage4 already proved:

```text
ABL → stock 4.19.157-perf → initramfs → /init → USB → IPv4 → HTTP
USB_STAGE4_HTTP_LIVENESS_PASS
STOCK_KERNEL_CONTROL_PATH_COMPLETE=YES
```

If this same kernel spins at its earliest executable branch and still returns at
~4.7s, an external/firmware reset is strongly supported.

If the same spin lasts >12s, an unconditional 4.7s watchdog is not supported,
and Mainline M4B's 4.755s return is more likely to occur before Mainline
`primary_entry` executes.

## Source boot identity

Do not rebuild stock 4.19. Reuse the exact Stage4 boot image:

```text
boot SHA256:
  6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a

kernel SHA256:
  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a

Stage4 ramdisk SHA256:
  e31cab1bef3408d1b87074ff7bcf573b9ebb74b96d535c55b9c97953ef1d0ac9

kernel: Linux 4.19.157-perf
header: Android boot v3, os 13.0.0, patch 2023-09, empty cmdline
```

If that exact boot image cannot be obtained, stop with
`M5A_STOCK_CONTROL_SOURCE_UNAVAILABLE`. Do not substitute another boot image.

## OEM binary visibility

The Stage4 boot image and extracted stock kernel are OEM-derived. They must not
be uploaded to public Actions artifacts or public Releases.

```text
Public:  ChuenSan/xiaomi10s
         transformation source, validators, hashes, reports, docs

Private: ChuenSan/thyme-mainline-private-ci
         Stage4 boot input, patched kernel, M5A flashable boot.img
```

## Stock DT context, future true-device only

M5A true-device, if later approved, must restore the exact V14.0.6.0.TGACNXM
stock DT context. Do not use the current M1 Mainline DT context.

```text
stock vendor_boot.img SHA:
  aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972

stock dtbo.img SHA:
  018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634

vbmeta_b / vbmeta_system_b: stock
```

This CI phase only records those requirements. It does not write the device and
does not restore B.

## Entry audit

Do not assume Mainline `head.S`. Private CI parses the extracted ARM64 Image
header:

```text
code0, code1, text_offset, image_size, flags, magic, PE offset
```

Supporting downstream source, not a substitute for the binary:

```text
android-kernel-sm8250/arch/arm64/kernel/head.S
  _head:
    CONFIG_EFI:  add x13, x18, #0x16; b stext
    !CONFIG_EFI: b stext; .long 0

kona-perf_defconfig hint:
  # CONFIG_EFI is not set
  CONFIG_BUILD_ARM64_UNCOMPRESSED_KERNEL=y
```

Patch rule, decided by the exact binary:

```text
If code0 is B and code1 is 0:
  patch code0 to b .          (earliest raw Image instruction)

If code0 is EFI MZ/NOP and code1 is B:
  keep code0, patch code1 to b .

Otherwise:
  M5A_ENTRY_LOCATION_INCONCLUSIVE
```

The patched word must be `0x14000000`. Magic, `text_offset`, `image_size`,
flags, and PE offset stay unchanged. No timer, MMIO, WFI/WFE, BRK/UDF, PSCI,
SMC, or HVC is introduced. The patch occupies one 32-bit instruction. The
reported `KERNEL_DIFF_BYTE_COUNT` is the number of bytes that actually differ
inside that word; unchanged immediate bytes are not a failure.

## Public / private split

Public workflow:

```text
.github/workflows/thyme-mainline-v2-m5a-stock-entry-spin-control.yml
```

Source audit only. It does not download the Stage4 boot, unpack OEM kernels, or
upload a flashable image.

Reusable private inputs from this repository:

```text
scripts/m5a_stock_kernel_entry_spin.py
scripts/m5a-stock-kernel-entry-spin-ci-validate.sh
scripts/m5a-stock-kernel-entry-spin-source-gates.py
```

Private workflow:

```text
ChuenSan/thyme-mainline-private-ci
.github/workflows/thyme-stock-kernel-entry-spin-control.yml
```

It checks out this public repository at one immutable commit, fetches the exact
Stage4 boot from the private Release, transforms the kernel, and stores OEM
outputs only in private Actions storage.

## Required private gates

```text
AUTHORITATIVE_STAGE4_BOOT_SHA=PASS
STOCK_KERNEL_EXTRACTED=PASS
STOCK_KERNEL_IDENTITY=PASS
ARM64_IMAGE_HEADER_VALID=PASS
EARLIEST_ENTRY_LOCATION_AUDITED=PASS
SPIN_PATCH_MINIMAL=PASS
KERNEL_ONLY_EXPECTED_BYTES_CHANGED=PASS
ARM64_IMAGE_MAGIC_UNCHANGED=PASS
IMAGE_SIZE_FIELDS_UNCHANGED=PASS
STAGE4_RAMDISK_EXACT_REUSE=PASS
BOOT_HEADER_SEMANTIC_MATCH=PASS
NO_TIMER=PASS
NO_MMIO=PASS
NO_EXCEPTION_INSN=PASS
REVERSE_UNPACK=PASS
PRIVATE_ARTIFACT_ONLY=PASS

Final CI gate:
READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL
```

Allowed terminal gates for this phase:

```text
READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL
M5A_STOCK_CONTROL_SOURCE_UNAVAILABLE
M5A_ENTRY_LOCATION_INCONCLUSIVE
M5A_BINARY_TRANSFORM_VALIDATION_FAILED
M5A_PRIVATE_ARTIFACT_POLICY_FAILED
```

No true-device gate is produced.

## Private CI result

```text
PUBLIC_SOURCE_COMMIT=0accc1bfce8b9c755c14f233e78e421d1d910d2d
PUBLIC_SOURCE_AUDIT_RUN=34472210815
PRIVATE_CI_RUN=34472283836
PRIVATE_CI_COMMIT=6539ebcedf8218747908d88aa8ca73f5a4ec4d77
PRIVATE_CI_RESULT=success
ARTIFACT=thyme-m5a-stock-entry-spin-6539ebcedf8218747908d88aa8ca73f5a4ec4d77
STAGE4_BOOT_TAG=stock-kernel-usb-stage4-http-c780694
SOURCE_STOCK_CONTROL_BOOT_SHA_MATCH=YES
NO_STOCK_KERNEL_REBUILD=PASS
LOCAL_BUILD=NO
DEVICE_OPERATION=NO
FINAL_GATE=READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL
```

Entry audit from the exact extracted stock Image, not from Mainline `head.S`:

```text
ARM64_IMAGE_HEADER_VALID=PASS
MAGIC=ARM\x64
CODE0=0x14a60000          b 0x2980000
CODE1=0x00000000          .long 0
TEXT_OFFSET=0x80000
IMAGE_SIZE=64008192
IMAGE_FILE_SIZE=52654096
FLAGS=0xa
PE_OFFSET=0x0
ENTRY_LAYOUT=NON_EFI_CODE0_BRANCH_TO_ENTRY
RAW_ENTRY=Image offset 0
ORIGINAL_INSTRUCTION=0x14a60000
PATCHED_INSTRUCTION=0x14000000
PATCH_OFFSET=0
ORIGINAL_BRANCH_TARGET=0x2980000
ORIGINAL_TARGET_WORD=0x94000008   BL
OBJDUMP=0: 14000000 b 0x0
```

The binary matches the downstream non-EFI `head.S` path (`b stext; .long 0`)
and `kona-perf` `# CONFIG_EFI is not set`. The first executable instruction is
the branch-to-entry itself, so that is the spin site.

Minimal delta:

```text
KERNEL_PATCH_WORD_SIZE=4
KERNEL_DIFF_BYTE_COUNT=1
KERNEL_DIFF_OFFSETS=2
BOOT_DIFF_BYTE_COUNT=1
BOOT_DIFF_OFFSETS=4098
EXPECTED_PATCHED_WORD=0x14000000
```

Original little-endian code0 is `00 00 a6 14`. Patched is `00 00 00 14`. Only
the immediate byte at kernel offset 2 / boot offset 4098 changes. The 32-bit
instruction word is still the only patched location.

Header invariants:

```text
ARM64 magic unchanged
image_size unchanged
text_offset unchanged
PE offset unchanged
boot v3 / os 13.0.0 / 2023-09 / empty cmdline unchanged
kernel_size 52654096 unchanged
ramdisk SHA e31cab1bef3408d1b87074ff7bcf573b9ebb74b96d535c55b9c97953ef1d0ac9
BOOT_REPACK_IDENTITY=PASS
```

Private artifact hashes:

```text
patched Image SHA:
  6a69ed3f4130e2a9a9357151fb01a586877cfa6e1267dfe90e81291c3a388327
patched boot SHA:
  790ee1265a5c2419e815870d43d6e34c60195e380aba772c55ccc7fa3aa5c141
```

No flashable M5A boot or patched stock kernel was uploaded to the public
repository.

## Device boundary

```text
NO ADB DEVICE CHANGE
NO FASTBOOT
NO FLASH
NO SET_ACTIVE
NO B BOOT
Slot A: not written
current B M1 context: not restored in this phase
```

Even if private CI passes, this round stops at the CI artifact.

## Future true-device matrix, not executed

Restore B to stock DT context, then one B boot of the M5A image:

```text
vendor_boot_b = exact stock V14.0.6.0.TGACNXM
dtbo_b        = exact stock V14.0.6.0.TGACNXM
vbmeta_b      = stock
vbmeta_system_b = stock
boot_b        = M5A stock-entry-spin boot
```

Do not keep the M1 Mainline DT context for this control. A 4.7s return on stock
kernel + Mainline DT would mix two variables.

Timing interpretation, future only:

```text
Case A  >12s, no automatic Fastboot return
  UNCONDITIONAL_EXTERNAL_4P7S_WATCHDOG = REFUTED / NOT SUPPORTED
  STOCK_ENTRY_SPIN_EXECUTION = STRONGLY_CONFIRMED
  with M4B still 4.755s:
    MAINLINE_M4B_ENTRY_EXECUTION = LIKELY_NOT_REACHED
  next: MAINLINE_BOOTLOADER_ACCEPTANCE / RAW IMAGE ENTRY

Case B  still ~4.3-5.3s automatic Fastboot return
  EXTERNAL_4P7S_RESET_WITH_KNOWN_EXECUTABLE_STOCK_KERNEL = SUPPORTED
  next: bootloader/firmware watchdog control
```

## Next

```text
M5A TRUE DEVICE CONTROL
WAIT FOR USER APPROVAL
```
