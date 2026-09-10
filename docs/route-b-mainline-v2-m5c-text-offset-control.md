# Route B Mainline V2 M5C — text_offset 0x80000 control

Status: true-device test complete. Final gate:
`MAINLINE_V2_M5C_TEXT_OFFSET_NO_EFFECT`.
Android A restored; no M5D or M6 action was performed.

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

## Completed true-device result

The approved device phase used GitHub Actions artifacts only. Mem0 was read at
start and again immediately before entering Fastboot for the only write. No
local build, validator, source gate, actionlint, binary conversion,
disassembly, or binary validation ran.

Android A baseline passed with `_a`, `boot_completed=1`, and root available.
The downloaded artifact was checked read-only before use:

```text
M5C_BOOT_ARTIFACT_SIZE=35110912
M5C_BOOT_SHA256=66a001eb8065f64e879be5a9cef199fae2c8e7a4587f583d2d4581f8429083ec
```

### Pre-write safety gates

The fixed prefix-domain verifier proved that the existing Slot B was exactly
M1 Mainline DT context plus M5B boot:

```text
boot_b first 35110912 SHA256=2125ebab7eafc8fdc2c2901138ba41bfe0a61f97d9d898094b9020116937f681
vendor_boot_b first 114688 SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5 MATCH=YES
vendor_boot_b remainder SHA256=3d6cb7047e6d0b70a764b6dae548a720904378c62f151732d5faaab8ea703a74 MATCH=YES
dtbo_b first 387 SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1 MATCH=YES
dtbo_b remainder SHA256=0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd MATCH=YES
M1_CONTEXT_EXACT_PRESERVED=YES
```

Stock prefixes also matched for `vbmeta_b`, `vbmeta_system_b`, `xbl_b`,
`abl_b`, and `tz_b`. Fastboot preflight passed with `product=thyme`,
`unlocked=yes`, `current-slot=a`, `snapshot-update-status=none`, and
`battery-soc-ok=yes`. Slot B metadata before the write was retry count 6 and
`unbootable=no`.

### Only partition write and independent verification

The only partition write was the exact M5C artifact to `boot_b`.
`vendor_boot_b`, `dtbo_b`, vbmeta, firmware, all other B partitions, and every
Slot A partition were untouched. The device remained on Slot A after the write;
Slot B retry count became 7 and remained bootable. Android A then independently
verified:

```text
boot_b first 35110912 SHA256=66a001eb8065f64e879be5a9cef199fae2c8e7a4587f583d2d4581f8429083ec
M5C_DEVICE_BOOT_PREFIX_MATCH=YES
boot_b whole-partition SHA256=73fa2c3beef207f4ab294c9302ed785f56c6e5d140affde1e5aab0957b955503 (observation only)
M5C_FULL_CONTEXT_VERIFIED=YES
```

The complete M1 prefix/remainder, stock vbmeta, and stock firmware gates were
repeated and remained exact before permitting the B boot.

### Single B boot and timing

Slot B was selected with retry count 7 and `unbootable=no`. Exactly one B boot
was issued. Only the Fastboot USB identity `18d1:d00d` was monitored:

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-10T13:51:41.128Z
FASTBOOT_REAPPEAR_TIMESTAMP=2026-09-10T13:51:45.917Z
AUTOMATIC_FASTBOOT_REAPPEAR=YES
M5C_ELAPSED=4.788s
OBSERVATION_WINDOW=12s
M5B_REFERENCE=4.492s
M5C_4P7S_RETURN_SUPPRESSED=NO
MANUAL_RECOVERY=NO
SECOND_B_BOOT_FORBIDDEN=YES
```

The automatic return remained inside the predefined 4.3–5.3-second band.
Post-attempt metadata was `current-slot=b`, retry count 6, and
`unbootable=no`. Slot A was selected immediately and Android A restored with
`slot_suffix=_a` and `boot_completed=1`. Slot B was not booted again and its
M5C content was not restored or replaced.

### Dumps and causal conclusion

```text
pstore entries baseline/post=0/0 UNCHANGED
oops baseline=94eb250aa317fb63ac7ed896c3ad6244a9041f27ae0d8239fbaed9f9f13fb76c
oops post=bff164e3a5fcfaf401fb7e40784a545a7fc39d26d1475b46b21c7c989970a1a3 CHANGED
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED
```

The changed oops contains the Android A stock-kernel
`reboot,bootloader` record and is not Mainline evidence. No new Mainline PC or
log was found.

Changing only the ARM64 Image `text_offset` byte from `0x0` to `0x80000` did
not suppress the stable return. No other header field participates in this
runtime conclusion:

```text
M5C_RUNTIME_CAUSAL_VARIABLE=ARM64_IMAGE_TEXT_OFFSET
TEXT_OFFSET_LOAD_HANDOFF_EFFECT=NO
MAINLINE_TEXT_OFFSET_ZERO_CAUSAL=NOT_SUPPORTED
MAINLINE_PRIMARY_ENTRY_EXECUTION=NOT_CONFIRMED
ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED
ANDROID_A_RESTORED=YES
FINAL_GATE=MAINLINE_V2_M5C_TEXT_OFFSET_NO_EFFECT
```

The next proposed stage is
`MAINLINE_V2_M5D_PE_HEADER_OFFSET_ZERO_CONTROL`, incrementally based on M5C so
that only PE header offset `0x40 -> 0x0` changes. It is not executed and awaits
explicit user approval.
