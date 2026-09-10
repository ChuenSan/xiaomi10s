# Route B Mainline V2 M5D — PE header offset zero control

Status: CI preparation only. No device operation is authorized. Final runtime
result is pending explicit approval for a future true-device test.

M5D directly reuses the exact M5C Image and boot v3 artifact and changes only
the ARM64 Image header's PE/COFF header offset metadata from `0x40` to `0x0`.
The real PE/COFF payload remains present and byte-exact. This stage is therefore
`PE_HEADER_OFFSET_ZERO_CONTROL`, not EFI removal or EFI disablement.

## Causal basis

```text
M4B: EFI/MZ-style code0; primary_entry b .; 4.755s automatic return
M5A: known-good Stock 4.19 raw entry b .; >12s without automatic return
M5B: direct code0 branch; primary_entry b .; 4.492s automatic return
M5C: M5B plus text_offset 0x80000; 4.788s automatic return
UNCONDITIONAL_4P7S_EXTERNAL_WATCHDOG=REFUTED_BY_CONTROL
CODE0_MZ_EFFECT=NO
TEXT_OFFSET_EFFECT=NO
PRIMARY_ENTRY_EXECUTION=NOT_CONFIRMED
```

The decisive issue is not whether a zero PE offset is generally valid. It is
whether thyme's loader changes handoff behavior when only this exact metadata
field changes after code0 is already a raw direct branch. CI can prove binary
identity and isolation, but cannot prove that ABL reads the field.

## Exact inputs

Authoritative M5C private Actions artifact:

```text
run: 34483231020
commit: ee8d447d280efa1edd5d04244505d1c0b849b347
artifact: thyme-mainline-v2-m5c-text-offset-ee8d447d280efa1edd5d04244505d1c0b849b347
Image SHA256: e0f1fa08555a9134f44af62d9f96258fa9903ec49052aa906aac6cb8a1365e35
boot SHA256: 66a001eb8065f64e879be5a9cef199fae2c8e7a4587f583d2d4581f8429083ec
ramdisk SHA256: b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
```

Exact known-good Stock 4.19 reference, fetched only by private Actions:

```text
Stage4 boot SHA256: 6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a
Stock kernel SHA256: 85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
expected Stock PE offset: 0x0
```

Both source identities must pass before parsing. A nonzero value parsed from
the exact Stock kernel stops as `M5D_STOCK_PE_OFFSET_ASSUMPTION_INVALID`.

## Parser-derived field and transformation

The CI parser declares and walks the complete 64-byte ARM64 Image header,
derives each field offset and width from the layout, validates total size,
field adjacency, magic, and the M5C PE signature/PE32+ extent, then reports:

```text
CODE0
CODE1
TEXT_OFFSET
IMAGE_SIZE
FLAGS
RESERVED_FIELDS
MAGIC
PE_HEADER_OFFSET_FIELD_VALUE
PE_HEADER_OFFSET_FIELD_IMAGE_OFFSET
PE_HEADER_OFFSET_FIELD_WIDTH
PE_HEADER_OFFSET_FIELD_ENDIAN
```

Only after this exact-binary layout validation does CI encode zero using the
parser-derived location, width, and endianness. The expected layout yields a
little-endian 32-bit field at Image offset `0x3c`, with `0x40 -> 0x00` expected
to change only byte `0x3c`; actual Image and boot diff sets remain calculated
gates, not assumptions. The exact M5C boot is patched in place. Linux, DTS,
initramfs, and boot packaging are not rebuilt, and `mkbootimg` is not used.

## Header matrix and invariants

```text
             Stock       M5C          M5D
code0        parsed      0x146c7028   exact M5C
code1        parsed      0x146c7027   exact M5C
text_offset  0x80000     0x80000      0x80000
image_size   0x3d0b000   0x2220000    0x2220000
flags        0xa         0xa          0xa
reserved     0           0            0
magic        ARM64       ARM64        ARM64
PE offset    0x0         0x40         0x0
```

The final Image must also preserve:

```text
code0 direct b primary_entry
code1 exact M5C
primary_entry Image offset 0x1b1c0a0, or exact authoritative M5C report value
primary_entry first word 0x14000000, b .
real PE/COFF payload bytes exact M5C
image_size 0x2220000
flags 0xa
all reserved fields zero
ARM64 magic
kernel payload length
boot header v3 metadata, cmdline, padding, and all non-target boot bytes
exact M5C ramdisk
```

The PE hash domain is explicitly the real PE/COFF payload region located from
the M5C offset metadata, beginning at its `PE\0\0` signature and ending at the
validated PE header extent. It excludes the ARM64 metadata field that points to
that region. The required before/after SHA is:

```text
01a36888696f7d34c98d6c91c74dab3ea6a1fa5acb32730e149cdd73b0af2afd
```

Zeroing the pointer does not zero, truncate, rewrite, or remove the PE
signature, optional header, section table, EFI stub code, or any PE payload.

## Fail-closed and reverse gates

CI deliberately corrupts independent candidate copies and proves rejection for
changes to code0, `text_offset`, `image_size`, `primary_entry`, the PE payload,
and a byte outside the PE-offset field. It also reverse-unpacks M5C and M5D and
requires exact kernel and ramdisk payloads.

Required gates include:

```text
M5C_IMAGE_SHA_EXACT=PASS
M5C_BOOT_SHA_EXACT=PASS
M5C_HEADER_PARSED=PASS
STOCK_HEADER_PARSED=PASS
HEADER_LAYOUT_VALIDATED=PASS
M5C_PE_OFFSET_40=PASS
STOCK_PE_OFFSET_ZERO=PASS
M5D_PE_OFFSET_ZERO=PASS
CODE0_EXACT_M5C=PASS
CODE1_EXACT_M5C=PASS
TEXT_OFFSET_80000_PRESERVED=PASS
IMAGE_SIZE_UNCHANGED=PASS
FLAGS_UNCHANGED=PASS
RESERVED_FIELDS_UNCHANGED=PASS
ARM64_MAGIC_UNCHANGED=PASS
PRIMARY_ENTRY_SPIN_PRESERVED=PASS
REAL_PE_REGION_UNCHANGED=PASS
RAMDISK_EXACT_REUSE=PASS
BOOT_METADATA_UNCHANGED=PASS
IMAGE_DIFF_PE_OFFSET_ONLY=PASS
BOOT_DIFF_PE_OFFSET_ONLY=PASS
REVERSE_UNPACK=PASS
FAIL_CLOSED=PASS
READY_FOR_MAINLINE_V2_M5D_PE_OFFSET_ZERO_CONTROL
```

Failure is reported only through the bounded M5D failure gates, including
source identity, header parse, Stock assumption, nonminimal diff, PE region,
primary spin, validation, or not-safe failure. No static gate is a runtime
claim.

## CI-only outputs

```text
Public workflow: .github/workflows/thyme-mainline-v2-m5d-pe-header-offset-zero-control.yml
Transformer: scripts/mainline-v2-m5d-ci-transform.py
Private builder: ChuenSan/thyme-mainline-private-ci
Local build/validator/source gate/actionlint: NO
Binary transformation/disassembly/validation: GitHub Actions only
Device operation: NO
```

The artifact contains only:

```text
mainline-v2-m5d-pe-offset-zero-spin-boot-v3.img
Image
header-before-after-report.txt
binary-diff-report.txt
disassembly-proof.txt
validation-report.txt
SHA256SUMS
```

It contains no Stock binary, `vendor_boot`, `dtbo`, `vbmeta`, or firmware.
Public source, transformation logic, validation logic, hashes, and this document
remain public; the OEM-derived Stock input remains private.

## Future true-device criteria

Current Slot B remains M1 Mainline DT context plus M5C `boot_b`, unchanged.
Slot A is never written. This CI stage performs no ADB change, Fastboot, flash,
erase, format, slot switch, or B boot.

If a later explicitly approved M5D test remains past 12 seconds without an
automatic Fastboot return, record that PE-offset metadata participates in causal
handoff behavior; do not claim the PE header itself crashes the kernel. If the
same 4.3–5.3-second return remains, record
`MAINLINE_V2_M5D_PE_OFFSET_NO_EFFECT` and stop for
`M5E_HEADER_LOAD_SEMANTICS_AUDIT`. Do not copy Stock's `image_size` into the
shorter Mainline payload without first auditing actual Image length, header
size, boot kernel size, loader copy bounds, load base, and entry semantics.
