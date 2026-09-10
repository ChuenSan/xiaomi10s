# Route B Mainline V2 M5C — text_offset 0x80000 control

Status: CI artifact ready. Final gate:
`READY_FOR_MAINLINE_V2_M5C_TEXT_OFFSET_CONTROL`.
No device operation is authorized or was performed.

M5C isolates one ARM64 Image header field. It reuses the exact M5B Image and
boot v3 artifact, changes `text_offset` from `0` to `0x80000`, and changes no
other byte. This tests a load/handoff-contract hypothesis; CI cannot establish
how Xiaomi thyme's exact ABL interprets the field.

## Causal basis

M5A used the known-good Stock 4.19 Image with its first raw Image instruction
changed to `b .`. It remained past the 12-second observation window. M5B changed
Mainline M4B `code0` from the EFI/MZ pseudo-NOP to a direct branch to the
unchanged spinning `primary_entry`; Fastboot still returned automatically after
4.492s.

```text
M4B: EFI/MZ code0; primary_entry b .; 4.755s automatic return
M5A: Stock code0 b .; Stock DT context; >12s without automatic return
M5B: direct b primary_entry; primary_entry b .; 4.492s automatic return
UNCONDITIONAL_4P7S_EXTERNAL_WATCHDOG=REFUTED_BY_CONTROL
CODE0_MZ_EFI_VS_RAW_ALONE=NOT_SUPPORTED_AS_CAUSE
MAINLINE_PRIMARY_ENTRY=NOT_CONFIRMED
```

The unasked but decisive issue is not whether `0x80000` is generally valid. It
is whether changing only that exact encoded field changes this bootloader's
handoff behavior. Therefore PE offset, PE content, `image_size`, flags, DT,
ramdisk, and kernel body remain exact M5B.

## Exact inputs

M5B public Actions artifact:

```text
run: 34478750866
commit: c71fd8c19c127725f5cfbe4b007c81fcf9312cc3
artifact: thyme-mainline-v2-m5b-direct-entry-c71fd8c19c127725f5cfbe4b007c81fcf9312cc3
Image SHA256: 502529d643d0907db3cb429e04de60617f0aba5bf6753d693e07f42a6db1bb1f
boot SHA256: 2125ebab7eafc8fdc2c2901138ba41bfe0a61f97d9d898094b9020116937f681
ramdisk SHA256: b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
```

Stock authoritative Stage4 source, fetched only inside private Actions:

```text
boot SHA256: 6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a
kernel SHA256: 85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
private release tag: stock-kernel-usb-stage4-http-c780694
```

The private job must parse that exact stock kernel and prove
`STOCK_TEXT_OFFSET=0x80000`. A documented value is not accepted as a gate. If
the binary differs, it stops with `M5C_STOCK_TEXT_OFFSET_ASSUMPTION_INVALID`.
No OEM Stock binary is committed or uploaded in the M5C artifact.

## One-field transformation

The ARM64 Image parser reads all first-64-byte fields before patching:

```text
0x00 u32 code0
0x04 u32 code1
0x08 u64 text_offset
0x10 u64 image_size
0x18 u64 flags
0x20 u64 res2
0x28 u64 res3
0x30 u64 res4
0x38 ARM\x64 magic
0x3c u32 PE header offset
```

The exact M5B binary must encode eight zero bytes at `0x08..0x0f`. CI writes the
little-endian u64 value `0x0000000000080000`:

```text
before: 00 00 00 00 00 00 00 00
after:  00 00 08 00 00 00 00 00
expected Image byte delta: 0x0a, 00 -> 08
```

The expected delta is not trusted in advance. CI calculates every Image and
boot diff and requires the actual sets to be exactly `{0x0a}` and `{0x100a}`
after independently proving the boot v3 kernel payload starts at `0x1000`.
The exact M5B boot is patched directly; `mkbootimg` is not used.

## Required invariants

```text
M5B code0 = 0x146c7028, direct b primary_entry
M5B code1 byte-exact
primary_entry offset = exact authoritative M5B report
primary_entry first word = 0x14000000, b .
image_size unchanged
flags unchanged
res2/res3/res4 unchanged
ARM64 magic unchanged
PE offset unchanged
parsed PE region SHA unchanged
kernel payload length unchanged
boot header and all bytes outside mapped text_offset unchanged
ramdisk exact M5B reuse
reverse-unpacked kernels and ramdisks exact
```

The direct `B imm26` remains PC-relative and the `b .` self-loop remains
position-independent. These are static instruction properties, not evidence of
real ABL placement or execution.

## CI-only implementation

```text
Public workflow: .github/workflows/thyme-mainline-v2-m5c-text-offset-control.yml
Transformer: scripts/mainline-v2-m5c-ci-transform.py
Private builder: ChuenSan/thyme-mainline-private-ci
Local build: NO
Local validator/source gate/actionlint: NO
Binary transformation/disassembly/validation: GitHub Actions only
Kernel rebuild: NO
Device operation: NO
```

Private execution is required because the exact Stock source is OEM-derived.
The output contains only the Mainline-derived M5C Image/boot and text reports:

```text
mainline-v2-m5c-text-offset-80000-spin-boot-v3.img
Image
header-before-after.txt
stock-vs-mainline-header-matrix.txt
binary-diff-report.txt
validation-report.txt
SHA256SUMS
```

It emits no `vendor_boot`, `dtbo`, `vbmeta`, firmware, or Stock binary.

## Final CI gate

Required gates include:

```text
M5B_IMAGE_SHA_EXACT=PASS
M5B_BOOT_SHA_EXACT=PASS
STOCK_HEADER_PARSED=PASS
M5B_HEADER_PARSED=PASS
STOCK_TEXT_OFFSET_80000=PASS
M5B_TEXT_OFFSET_ZERO=PASS
TEXT_OFFSET_PATCHED_TO_80000=PASS
CODE0_EXACT_M5B=PASS
CODE1_EXACT_M5B=PASS
PRIMARY_ENTRY_SPIN_PRESERVED=PASS
IMAGE_SIZE_UNCHANGED=PASS
FLAGS_UNCHANGED=PASS
RESERVED_FIELDS_UNCHANGED=PASS
ARM64_MAGIC_UNCHANGED=PASS
PE_HEADER_OFFSET_UNCHANGED=PASS
PE_REGION_UNCHANGED=PASS
RAMDISK_EXACT_REUSE=PASS
BOOT_METADATA_UNCHANGED=PASS
BOOT_KERNEL_SIZE_UNCHANGED=PASS
IMAGE_DIFF_TEXT_OFFSET_ONLY=PASS
BOOT_DIFF_TEXT_OFFSET_ONLY=PASS
REVERSE_UNPACK=PASS
DIRECT_BRANCH_POSITION_INDEPENDENT=PASS
PRIMARY_ENTRY_SPIN_POSITION_INDEPENDENT=PASS
READY_FOR_MAINLINE_V2_M5C_TEXT_OFFSET_CONTROL
```

## Completed CI result

The public source audit and private exact-binary workflow both passed:

```text
public source commit: 901dd1cf7c8fdcef6196b8399a379e6403811068
public source-audit run: 34483036008
private workflow commit: ee8d447d280efa1edd5d04244505d1c0b849b347
private CI run: 34483231020
artifact: thyme-mainline-v2-m5c-text-offset-ee8d447d280efa1edd5d04244505d1c0b849b347
CI result: success
```

Both source identities were exact before parsing or transformation. The exact
Stock binary confirmed the assumption rather than relying on prior notes:

```text
Stock:
  code0=0x14a60000
  code1=0x00000000
  text_offset=0x80000
  image_size=0x3d0b000
  flags=0xa
  res2=0x0 res3=0x0 res4=0x0
  magic=41524d64 (ARM\x64)
  PE offset=0x0

M5B:
  code0=0x146c7028
  code1=0x146c7027
  text_offset=0x0
  image_size=0x2220000
  flags=0xa
  res2=0x0 res3=0x0 res4=0x0
  magic=41524d64 (ARM\x64)
  PE offset=0x40

M5C:
  code0=0x146c7028
  code1=0x146c7027
  text_offset=0x80000
  image_size=0x2220000
  flags=0xa
  res2=0x0 res3=0x0 res4=0x0
  magic=41524d64 (ARM\x64)
  PE offset=0x40
```

The actual calculated delta matched the one-byte prediction:

```text
IMAGE_DIFF_BYTE_COUNT=1
IMAGE_DIFF_OFFSETS=0x0a
IMAGE_DIFF_OUTSIDE_TEXT_OFFSET=0
BOOT_KERNEL_PAYLOAD_OFFSET=0x1000
BOOT_DIFF_BYTE_COUNT=1
BOOT_DIFF_OFFSETS=0x100a
BOOT_DIFF_OUTSIDE_TEXT_OFFSET=0
```

All non-target header fields, the boot metadata, kernel size, ramdisk, and PE
region remained exact. Reverse unpacking passed. The direct branch still targets
`primary_entry` at Image offset `0x1b1c0a0`; its first instruction remains
`0x14000000` (`b .`).

```text
PE_REGION_SHA_BEFORE=01a36888696f7d34c98d6c91c74dab3ea6a1fa5acb32730e149cdd73b0af2afd
PE_REGION_SHA_AFTER=01a36888696f7d34c98d6c91c74dab3ea6a1fa5acb32730e149cdd73b0af2afd
RAMDISK_SHA256=b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
M5C_IMAGE_SHA256=e0f1fa08555a9134f44af62d9f96258fa9903ec49052aa906aac6cb8a1365e35
M5C_BOOT_SHA256=66a001eb8065f64e879be5a9cef199fae2c8e7a4587f583d2d4581f8429083ec
FINAL_GATE=READY_FOR_MAINLINE_V2_M5C_TEXT_OFFSET_CONTROL
DEVICE_OPERATION=NO
```

No runtime conclusion follows from these static gates.

## Future true-device criteria — not authorized

Current Slot B remains:

```text
M1 Mainline DT context + M5B boot_b
```

M5C CI does not inspect or change the device. Slot A is permanently protected.
No ADB change, Fastboot, flash, erase, format, slot switch, or Slot B boot is
permitted.

If a later, separately approved M5C device phase occurs, it keeps M1
`vendor_boot_b` and `dtbo_b`, Stock vbmeta and firmware, writes only the exact
M5C `boot_b`, and performs one B boot. More than 12 seconds without automatic
Fastboot return would strongly support a `text_offset` handoff effect; a return
inside the historical 4.3–5.3-second band would classify the field change as no
effect. Neither result has occurred.
