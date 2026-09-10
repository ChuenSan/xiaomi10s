# Route B Mainline V2 M5B — Image header direct-entry control

Status: CI implementation pending. Device operation is forbidden in this stage.

M5B is a binary-level handoff control, not kernel development. It asks whether the
Mainline Image `code0` MZ/EFI-style entry semantics, rather than the unchanged
`primary_entry` body, cause the approximately 4.7-second return.

## Causal basis

M4B used Mainline `efi_signature_nop; b primary_entry`, with `b .` as the first
`primary_entry` instruction, and returned to Fastboot automatically after 4.755s.
M5A used the exact known-good stock Linux 4.19 Image with a direct raw-entry `b .` at
Image offset 0. It did not return automatically during the 12-second window.

```text
M1: 4.821s automatic Fastboot return
M2: 4.598s automatic Fastboot return
M3: 4.790s automatic Fastboot return
M4B: 4.755s automatic Fastboot return
M5A stock spin >12s: YES
UNCONDITIONAL_4P7S_EXTERNAL_WATCHDOG=REFUTED_BY_CONTROL
MAINLINE_PRE_PRIMARY_ENTRY_FAILURE=STRONGLY_SUPPORTED
ABL_REJECTION=NOT_PROVEN
```

The more precise unresolved question is not whether the MZ-compatible instruction
itself faults. Changing `code0` can also change ABL's EFI-versus-raw recognition and
handoff path. M5B therefore treats `code0 / MZ / EFI-vs-raw handoff semantics` as one
intentional variable.

## Exact authoritative M4B input

```text
CI run: 34464472317
commit: ace24d1c4f9537ab8726c551fa0d88155b581f7a
artifact: thyme-mainline-v2-m4b-entry-spin-ace24d1c4f9537ab8726c551fa0d88155b581f7a
Image SHA256: 52e429db5ba7ba411598625f706dc11d3d7c247458a932969e9913db0d1511a2
boot SHA256: 622a09516ddfcda7efad3cc42b92d2c205130ba7b0a8cf8cbba32c26a822b4c0
```

CI must verify both hashes before reading or changing bytes. It resolves
`primary_entry` from the authoritative M4B validation report generated from M4B
symbols, then independently requires M4B `code1` to branch to that same Image
offset. No Mainline kernel, initramfs, or `/init` rebuild is permitted.

## Single transformation

M4B:

```text
Image offset 0: efi_signature_nop
Image offset 4: b primary_entry
primary_entry:  b .
```

M5B:

```text
Image offset 0: b primary_entry       <- only changed instruction word
Image offset 4: b primary_entry       <- byte-exact M4B reuse
primary_entry:  b .                   <- byte-exact M4B reuse
```

CI computes `delta = primary_entry_offset`, requires four-byte alignment and the
signed AArch64 `B imm26` range, and derives the instruction word. It does not use a
preselected branch encoding.

The change intentionally removes the first two `MZ` bytes. The PE-header-offset
field remains byte-exact even though the MZ signature no longer selects EFI-style
semantics.

## CI-only implementation

```text
Workflow: .github/workflows/thyme-mainline-v2-m5b-image-header-direct-entry.yml
Transformer: scripts/mainline-v2-m5b-ci-transform.py
Local build: NO
Local validator/source gate/actionlint: NO
Binary transformation/disassembly/validation: GitHub Actions only
Device operation: NO
```

The strongest boot-image method is used. CI proves that the exact M4B Image equals
the M4B boot v3 kernel payload at offset 4096, then patches the corresponding
`code0` bytes directly in the exact M4B boot artifact. It does not invoke
`mkbootimg`, so boot metadata, ramdisk, padding, and any signature area can differ
only at the mapped kernel `code0` bytes.

Required invariants:

```text
code1 unchanged
primary_entry first word remains 0x14000000 (b .)
text_offset unchanged
image_size unchanged
flags unchanged
reserved fields unchanged
ARM\x64 magic unchanged
PE header offset unchanged
boot v3 header bytes unchanged
kernel size unchanged
ramdisk size and bytes unchanged
cmdline unchanged
all Image diff offsets are within [0,1,2,3]
all boot diff offsets map only to kernel Image code0
```

The exact M4B ramdisk expected by both reverse unpacking paths is:

```text
b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
```

## Required CI gates

```text
MEM0_POLICY_ACKNOWLEDGED=PASS
M4B_IMAGE_SHA_EXACT=PASS
M4B_BOOT_SHA_EXACT=PASS
M4B_EFI_CODE0_IDENTIFIED=PASS
PRIMARY_ENTRY_OFFSET_RESOLVED=PASS
DIRECT_BRANCH_ENCODING_VALID=PASS
M5B_CODE0_DIRECT_TO_PRIMARY_ENTRY=PASS
CODE1_UNCHANGED=PASS
PRIMARY_ENTRY_SPIN_PRESERVED=PASS
IMAGE_DIFF_CODE0_ONLY=PASS
MZ_SIGNATURE_CHANGE_INTENTIONAL=PASS
ARM64_MAGIC_UNCHANGED=PASS
TEXT_OFFSET_UNCHANGED=PASS
IMAGE_SIZE_UNCHANGED=PASS
FLAGS_UNCHANGED=PASS
PE_HEADER_OFFSET_UNCHANGED=PASS
M4B_RAMDISK_EXACT_REUSE=PASS
BOOT_DIFF_KERNEL_CODE0_ONLY=PASS
REVERSE_UNPACK=PASS
NO_VENDOR_BOOT_ARTIFACT=PASS
NO_DTBO_ARTIFACT=PASS
READY_FOR_MAINLINE_V2_M5B_DIRECT_ENTRY_CONTROL
```

## Artifact scope

```text
mainline-v2-m5b-direct-entry-spin-boot-v3.img
Image
binary-diff-report.txt
Image-header-before-after-report.txt
disassembly-proof.txt
SHA256SUMS
validation-report.txt
```

No `vendor_boot`, `dtbo`, `vbmeta`, or firmware artifact is emitted.

## Current device state — do not change

```text
B context: exact stock vendor_boot + exact stock dtbo + M5A boot_b
Slot A: permanently protected
NO ADB DEVICE CHANGE
NO FASTBOOT
NO FLASH
NO ERASE / FORMAT
NO SLOT SWITCH
NO B BOOT
NO PARTITION OPERATION
```

CI success does not authorize a true-device test and does not restore M1 context.

## Future true-device context — plan only

A future M5B test requires separate user approval and restoration of the exact M1
Mainline DT context before writing or booting M5B:

```text
vendor_boot_b first 114688 bytes SHA256:
29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5

dtbo_b first 387 bytes SHA256:
316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1

vbmeta_b: stock
vbmeta_system_b: stock
boot_b: exact M5B CI artifact
```

### Future Case A

If no automatic Fastboot return occurs within 12 seconds while `primary_entry`
remains `b .`:

```text
MAINLINE_PRIMARY_ENTRY_EXECUTION=STRONGLY_CONFIRMED
MAINLINE_IMAGE_CODE0_OR_EFI_HANDOFF_PATH_CAUSAL=YES
```

This does not isolate an instruction fault. It isolates Image `code0 / MZ /
EFI-vs-raw handoff semantics` as causal.

### Future Case B

If the approximately 4.3–5.3-second automatic return remains:

```text
MAINLINE_CODE0_DIRECT_BRANCH_EFFECT=NO
NEXT=MAINLINE_V2_M5C_HEADER_FIELD_ISOLATION
```

M5C is not implemented or executed in this stage. `primary_entry` must remain
unchanged.

## CI result record

Populate only from the successful GitHub Actions artifact:

```text
CI_COMMIT=PENDING
CI_RUN=PENDING
ARTIFACT=PENDING
M4B_CODE0_WORD=PENDING
M4B_CODE1_WORD=PENDING
PRIMARY_ENTRY_IMAGE_OFFSET=PENDING
M5B_CODE0_WORD=PENDING
M5B_IMAGE_SHA256=PENDING
M5B_BOOT_SHA256=PENDING
FINAL_GATE=PENDING
```
