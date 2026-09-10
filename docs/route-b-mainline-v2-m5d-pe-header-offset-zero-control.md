# Route B Mainline V2 M5D — PE header offset zero control

Status: true-device test complete. Final gate:
`MAINLINE_V2_M5D_PE_OFFSET_NO_EFFECT`.
Android A restored; no M5E action was performed.

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

## Completed CI result

The public source audit and private exact-binary workflow passed:

```text
public source commit: 4d9fc57f21b882d59bcb7bd3580395ab91095128
public source-audit run: 34487092827
private workflow commit: 1a30f48d5ef86ff2dce7df6f761ca925f60aa9e7
private CI run: 34487382191
artifact: thyme-mainline-v2-m5d-pe-offset-zero-1a30f48d5ef86ff2dce7df6f761ca925f60aa9e7
CI result: success
```

The exact parser-derived field and calculated deltas were:

```text
PE_HEADER_OFFSET_FIELD_IMAGE_OFFSET=0x3c
PE_HEADER_OFFSET_FIELD_WIDTH=4
PE_HEADER_OFFSET_FIELD_ENDIAN=little-endian
M5C PE offset=0x40
Stock PE offset=0x0
M5D PE offset=0x0
IMAGE_DIFF_BYTE_COUNT=1
IMAGE_DIFF_OFFSETS=0x3c
IMAGE_DIFF_OUTSIDE_PE_OFFSET_FIELD=0
BOOT_KERNEL_PAYLOAD_OFFSET=0x1000
BOOT_DIFF_BYTE_COUNT=1
BOOT_DIFF_OFFSETS=0x103c
BOOT_DIFF_OUTSIDE_PE_OFFSET_FIELD=0
```

All fail-closed, reverse-unpack, header, ramdisk, boot metadata, direct-entry,
primary-spin, and real-PE-region gates passed:

```text
M5D_IMAGE_SHA256=5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a
M5D_BOOT_SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
RAMDISK_SHA256=b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
PRIMARY_ENTRY_IMAGE_OFFSET=0x1b1c0a0
PRIMARY_ENTRY_WORD=0x14000000
PE_REGION_SHA_BEFORE=01a36888696f7d34c98d6c91c74dab3ea6a1fa5acb32730e149cdd73b0af2afd
PE_REGION_SHA_AFTER=01a36888696f7d34c98d6c91c74dab3ea6a1fa5acb32730e149cdd73b0af2afd
FINAL_GATE=READY_FOR_MAINLINE_V2_M5D_PE_OFFSET_ZERO_CONTROL
DEVICE_OPERATION=NO
```

The PE hash domain is the real payload `Image[0x40:validated PE header end]`;
it excludes the pointer metadata field at `0x3c..0x3f`. No runtime conclusion
follows from these static gates.

## Completed true-device result

The approved device phase used the exact GitHub Actions artifact. Mem0 was read
at the start and again immediately before entering Fastboot for the only write.
No local build, validator, source gate, actionlint, binary transformation,
disassembly, or binary validation ran.

Android A baseline passed with `_a`, `boot_completed=1`, and root available.
The downloaded artifact identity was checked before use:

```text
M5D_BOOT_ARTIFACT_SIZE=35110912
M5D_BOOT_SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
```

### Pre-write safety and exact context

The existing `boot_b` first 35110912 bytes matched M5C SHA256
`66a001eb8065f64e879be5a9cef199fae2c8e7a4587f583d2d4581f8429083ec`.
All required read-only context gates passed:

```text
vendor_boot_b first 114688 SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5 MATCH=YES
vendor_boot_b remainder SHA256=3d6cb7047e6d0b70a764b6dae548a720904378c62f151732d5faaab8ea703a74 MATCH=YES
dtbo_b first 387 SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1 MATCH=YES
dtbo_b remainder SHA256=0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd MATCH=YES
vbmeta_b/vbmeta_system_b=stock
xbl_b/abl_b/tz_b prefixes=stock
M1_CONTEXT_EXACT_PRESERVED=YES
```

Fastboot preflight passed with `product=thyme`, `unlocked=yes`,
`current-slot=a`, `snapshot-update-status=none`, and `battery-soc-ok=yes`.
Slot B was retry count 6 and `unbootable=no` before the write.

### Only write and independent readback

The only partition write was the exact M5D artifact to `boot_b`. Slot A,
`vendor_boot_b`, `dtbo_b`, vbmeta, firmware, and every other B partition were
not written. The device remained on Slot A after the write; Slot B became retry
count 7 and remained bootable. Android A independently established:

```text
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
M5D_DEVICE_BOOT_PREFIX_MATCH=YES
boot_b whole-partition SHA256=bbb8a279a15af53a153ab605988311a7d381c22a10b56cecbc41ea68d3ceaab0 (observation only)
M5D_FULL_CONTEXT_VERIFIED=YES
```

The complete M1 prefix/remainder, stock vbmeta, and stock firmware gates were
repeated and remained exact before permitting the B boot.

### Single B boot and timing

Exactly one Slot B boot was issued with retry count 7 and `unbootable=no`.
Only Fastboot USB identity `18d1:d00d` was monitored:

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-10T14:39:36.974Z
FASTBOOT_REAPPEAR_TIMESTAMP=2026-09-10T14:39:41.506Z
AUTOMATIC_FASTBOOT_REAPPEAR=YES
M5D_ELAPSED=4.532s
OBSERVATION_WINDOW=12s
M5C_REFERENCE=4.788s
M5B_REFERENCE=4.492s
M5D_4P7S_RETURN_SUPPRESSED=NO
MANUAL_RECOVERY=NO
SECOND_B_BOOT_FORBIDDEN=YES
```

The automatic return was inside the predefined 4.3–5.3-second band. Post-boot
metadata was `current-slot=b`, retry count 6, and `unbootable=no`. Slot A was
selected immediately and Android A restored with `slot_suffix=_a` and
`boot_completed=1`. Slot B was not booted again and retains M5D `boot_b`.

### Dumps and causal conclusion

```text
pstore entries baseline/post=0/0 UNCHANGED
oops baseline=1aea1fdc585b03b3a70d8b8ea6605032afc93529618c5e13d3f88bdd78536da5
oops post=6da2ec0d26870e7477cdda0c07073d774ca40167ab46c2c0710c4b39b37136c6 CHANGED
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED
```

The changed oops contains Android A stock-kernel `reboot,bootloader` records
and is not Mainline evidence. No new Mainline evidence was found.

Changing only the ARM64 Image PE-header-offset metadata from `0x40` to `0x0`
did not suppress the stable return. The PE payload, EFI stub, code0,
`text_offset`, executable body, ramdisk, and boot metadata were unchanged and
are not the tested variable:

```text
M5D_RUNTIME_CAUSAL_VARIABLE=ARM64_IMAGE_PE_HEADER_OFFSET
PE_OFFSET_HANDOFF_EFFECT=NO
MAINLINE_PE_OFFSET_40_CAUSAL=NOT_SUPPORTED
MAINLINE_PRIMARY_ENTRY=NOT_CONFIRMED
ABL_TO_MAINLINE=NOT_CONFIRMED
ANDROID_A_RESTORED=YES
FINAL_GATE=MAINLINE_V2_M5D_PE_OFFSET_NO_EFFECT
```

The next stage is analysis-only `M5E_HEADER_LOAD_SEMANTICS_AUDIT`, pending
approval. Do not copy Stock's `image_size` into the shorter Mainline payload
without first auditing actual Image length, boot kernel payload size, header
`image_size`, `text_offset`, executable span, loader copy bounds, load base,
and entry semantics.
