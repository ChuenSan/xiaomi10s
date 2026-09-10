# Route B Mainline V2 M5A — stock kernel entry spin control

Status: complete. Final gate:
`MAINLINE_V2_M5A_STOCK_SPIN_SUPPRESSES_4P7S`.
CI produced the private stock-entry-spin boot. True-device control restored
exact stock DT on B, flashed that boot once, and observed one Slot B boot.

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

## Device boundary used by the true-device run

```text
LOCAL_BUILD=NO
LOCAL_VALIDATOR=NO
GHA_ONLY=YES
Slot A: NO WRITE / no flash / no erase / no format
B writes: vendor_boot_b, dtbo_b, boot_b
vbmeta_b / vbmeta_system_b / firmware: not written
B boots: 1
SECOND_B_BOOT_FORBIDDEN=YES
OEM artifact: private only
```

Hash domain:

```text
stock vendor_boot.img size == vendor_boot_b == 100663296
  STOCK_VENDOR_BOOT_FULL_PARTITION_DOMAIN=YES
stock dtbo.img size == dtbo_b == 33554432
  STOCK_DTBO_FULL_PARTITION_DOMAIN=YES
M5A boot artifact size N=52674560
boot_b partition size=201326592
  device boot identity = first N bytes, not whole partition SHA
```

## Completed true-device control

Pre-write B was still the M1 Mainline DT context plus the M4B boot prefix:

```text
MEM0_READ_BEFORE_M5A=YES
MEM0_READ_BEFORE_TRUE_DEVICE_WRITE=YES
Android A: slot_suffix=_a boot_completed=1 root uid=0
boot_b prefix 35110912 = 622a09516ddfcda7efad3cc42b92d2c205130ba7b0a8cf8cbba32c26a822b4c0  (M4B)
vendor_boot_b prefix 114688 = 29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5  (M1)
vendor_boot_b whole = 3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614
dtbo_b prefix 387 = 316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1  (M1)
dtbo_b whole = b8127f44ea27080ea2852dc806a58dd5c3ae47616a6c0d50bfe83b3972fd001a
vbmeta_b prefix 8192 = 37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
vbmeta_system_b prefix 4096 = 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
xbl_b/abl_b/tz_b prefixes = stock
```

Local stock ROM files were rehashed, not re-downloaded:

```text
vendor_boot.img size=100663296 SHA=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
dtbo.img size=33554432 SHA=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
```

Private M5A boot, not regenerated:

```text
filename=m5a-stock-entry-spin-boot-v3.img
M5A_BOOT_ARTIFACT_SIZE=52674560
SHA256=790ee1265a5c2419e815870d43d6e34c60195e380aba772c55ccc7fa3aa5c141
```

Phase 1 restored stock DT only, then returned to Android A without booting B:

```text
fastboot: product=thyme unlocked=yes current-slot=a snapshot=none battery-soc-ok=yes
retry:b before=6 unbootable:b=no
WRITE: vendor_boot_b, dtbo_b
DO NOT WRITE: boot_b, vbmeta*, firmware, *_a
post-phase1 Android A:
  vendor_boot_b whole = aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
  dtbo_b whole = 018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
  boot_b still M4B prefix
  vbmeta*/firmware still stock
M5A_STOCK_DT_CONTEXT_VERIFIED=YES
```

Phase 2 wrote only `boot_b`, then returned to Android A again:

```text
retry:b after boot flash=7 unbootable:b=no current-slot=a
boot_b first 52674560 = 790ee1265a5c2419e815870d43d6e34c60195e380aba772c55ccc7fa3aa5c141
M5A_DEVICE_BOOT_PREFIX_MATCH=YES
whole boot_b = 1e44f7e823e4f680d4db92706b31f2e90569a4ff81aed4bc71bb945978e2d585  (observation only)
vendor_boot_b / dtbo_b / vbmeta* / firmware still stock
M5A_FULL_CONTROL_CONTEXT_VERIFIED=YES
```

Dump baseline immediately before the B boot, not cleared:

```text
oops=52ce2f2c6a13f5736b752df3ac901e75e44ebdd4244bf8005ada9c778491f783
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
pstore_entries=0
```

One B boot only:

```text
set_active b: current-slot=b unbootable=no retry=7
fastboot reboot: once
SECOND_B_BOOT_FORBIDDEN=YES
USB evidence: 18d1:d00d Fastboot identity only
T_DISAPPEAR=2026-09-10T12:17:30.788Z
HARD_WINDOW=12s
T_REAPPEAR within 12s=NOT_OBSERVED
AUTOMATIC_FASTBOOT_REAPPEAR=NO
M1/M2/M3/M4B cluster 4.598-4.821s, M4B=4.755s: SUPPRESSED
```

Fastboot was reachable after the hard window. The agent did not press keys and
did not issue an ordinary reboot on slot B. Recovery was `set_active a` from
Fastboot, then one reboot to Android A.

```text
after B attempt: current-slot=b retry:b=6 unbootable:b=no
set_active a: current-slot=a
Android A restored: slot_suffix=_a boot_completed=1 root uid=0
B not restored to M1 context
NO M5B EXECUTED=YES
```

Post-test dumps:

```text
oops=9357ee68bf56669bbaf4a930829b107a745a7ca9717b075618f87726cfa1a9db  CHANGED
minidump/rawdump/logdump = unchanged vs pre-B-boot and vs M4B
pstore_entries=0
Linux 6.6 / mainline / watchdog strings: none
oops reboot,bootloader records: stock Android init `/system/bin/reboot`
  (Android A `adb reboot bootloader` / recovery reboot), not a kernel watchdog
```

## Classification

This is Case A of the approved matrix.

```text
STOCK_SPIN_BASELINE_RETURN_SUPPRESSED=YES
STOCK_ENTRY_SPIN_CONTROL_FLOW_EFFECT=YES
STOCK_RAW_ENTRY_EXECUTION=STRONGLY_CONFIRMED
UNCONDITIONAL_KERNEL_INDEPENDENT_4P7S_WATCHDOG=REFUTED_BY_CONTROL
UNCONDITIONAL_4P7S_EXTERNAL_WATCHDOG=REFUTED_BY_CONTROL
MAINLINE_PRE_ENTRY_OR_HANDOFF_FAILURE_HYPOTHESIS=STRONGLY_SUPPORTED
ABL_REJECTED_MAINLINE_IMAGE=NOT_ASSERTED
```

The known-good Stock 4.19 Image, already proven through ABL to userspace HTTP,
remained past 12s after its first instruction was replaced with `b .`. The
Mainline M4B `b .` at `primary_entry` still returned at 4.755s. There is no
single mechanism that sends every payload back to Fastboot at ~4.7s regardless
of kernel execution.

That does not prove ABL rejected the Mainline Image. The remaining range is
pre-`primary_entry` / handoff: Image header compatibility, EFI/PE layout,
entry address, decompression/relocation, or bootloader validation.

## Next

```text
NEXT=MAINLINE_V2_M5B_IMAGE_HEADER_HANDOFF_CONTROL
NOT=EXTERNAL_WATCHDOG_CHARACTERIZATION
NO M5B EXECUTED=YES
```

Compare Stock 4.19 Image header (`code0` direct `b stext`, `code1=0`, PE=0,
`CONFIG_EFI` off) with Mainline 6.6 (`efi_signature_nop`, `b primary_entry`,
EFI/PE layout). Change only Mainline header/handoff compatibility. Do not
change the kernel body in M5B unless a later gate says so.
