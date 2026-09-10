# Route B Mainline V2 M5B — Image header direct-entry control

Status: true-device test complete. Final gate: `MAINLINE_V2_M5B_DIRECT_ENTRY_NO_EFFECT`.
Android A restored; no M5C action was performed.

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

## True-device constraints

```text
MEM0_READ_BEFORE_M5B=YES
MEM0_READ_BEFORE_EACH_WRITE_PHASE=YES
LOCAL_BUILD_OR_VALIDATION=NO
GITHUB_ACTIONS_ONLY=YES
SLOT_A_WRITE=NO
SLOT_B_BOOTS=1
SECOND_B_BOOT_FORBIDDEN=YES
VBMETA_OR_FIRMWARE_WRITE=NO
```

The approved test restored the private M1 context, wrote the exact M5B CI boot,
and performed one Slot B boot. Slot A remained protected throughout.

## Completed CI result

```text
CI_COMMIT=c71fd8c19c127725f5cfbe4b007c81fcf9312cc3
CI_RUN=34478750866
ARTIFACT=thyme-mainline-v2-m5b-direct-entry-c71fd8c19c127725f5cfbe4b007c81fcf9312cc3
CI_RESULT=success

M4B_CODE0_BYTES=4d5a40fa
M4B_CODE0_WORD=0xfa405a4d
M4B_CODE0_DISASM=ccmp x18, #0, #0xd, pl
M4B_EFI_SIGNATURE_NOP_CONFIRMED=YES
M4B_CODE1_WORD=0x146c7027
M4B_CODE1_DISASM=b 0x1b1c0a0
PRIMARY_ENTRY_IMAGE_OFFSET=0x1b1c0a0
PRIMARY_ENTRY_INSTRUCTION=b .
PRIMARY_ENTRY_SPIN_PRESERVED=PASS

TEXT_OFFSET=0x0
IMAGE_SIZE=0x2220000
FLAGS=0xa
MAGIC=ARMd (ARM\\x64 bytes)
PE_HEADER_OFFSET=0x40
MZ_SIGNATURE_PRESENT_BEFORE=YES

M5B_CODE0_WORD=0x146c7028
M5B_CODE0_DISASM=b 0x1b1c0a0
MZ_SIGNATURE_PRESENT_AFTER=NO

IMAGE_DIFF_BYTE_COUNT=4
IMAGE_DIFF_OFFSETS=0x0,0x1,0x2,0x3
IMAGE_DIFF_OUTSIDE_CODE0=0
BOOT_KERNEL_CODE0_OFFSET=0x1000
BOOT_DIFF_BYTE_COUNT=4
BOOT_DIFF_OFFSETS=0x1000,0x1001,0x1002,0x1003
BOOT_DIFF_OUTSIDE_KERNEL_CODE0=0

RAMDISK_SHA256=b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
M5B_IMAGE_SHA256=502529d643d0907db3cb429e04de60617f0aba5bf6753d693e07f42a6db1bb1f
M5B_BOOT_SHA256=2125ebab7eafc8fdc2c2901138ba41bfe0a61f97d9d898094b9020116937f681
FINAL_GATE=READY_FOR_MAINLINE_V2_M5B_DIRECT_ENTRY_CONTROL
DEVICE_OPERATION=NO
```

All required ARM64 header, boot metadata, ramdisk, reverse-unpack, minimal-diff,
and artifact-scope gates passed in GitHub Actions.

## Completed true-device result

Android A baseline passed with `_a`, `boot_completed=1`, and root available. The
pre-write B state matched the M5A end state:

```text
boot_b whole SHA256=1e44f7e823e4f680d4db92706b31f2e90569a4ff81aed4bc71bb945978e2d585
vendor_boot_b whole SHA256=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
dtbo_b whole SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
vbmeta_b prefix=37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
vbmeta_system_b prefix=3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
```

The downloaded M5B artifact was read-only checked before use:

```text
M5B_BOOT_ARTIFACT_SIZE=35110912
M5B_BOOT_SHA256=2125ebab7eafc8fdc2c2901138ba41bfe0a61f97d9d898094b9020116937f681
```

### M1 context restoration

Phase 1 preflight passed: `product=thyme`, `unlocked=yes`, `current-slot=a`,
`snapshot-update-status=none`, and `battery-soc-ok=yes`. Only `vendor_boot_b` and
`dtbo_b` were flashed from private M1 run 34338768052. The device then returned
to Android A before independent verification:

```text
vendor_boot_b partition size=100663296
vendor_boot_b first 114688 SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5 MATCH=YES
vendor_boot_b remainder SHA256=3d6cb7047e6d0b70a764b6dae548a720904378c62f151732d5faaab8ea703a74 MATCH=YES
dtbo_b partition size=33554432
dtbo_b first 387 SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1 MATCH=YES
dtbo_b remainder SHA256=0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd MATCH=YES
M1_CONTEXT_EXACT_RECONSTRUCTED=YES
```

Stock prefixes for `vbmeta_b`, `vbmeta_system_b`, `xbl_b`, `abl_b`, and `tz_b`
all matched. Phase 2 again passed the Fastboot product, unlock, and Slot A gates;
only `boot_b` was flashed. After another return to Android A:

```text
boot_b first 35110912 SHA256=2125ebab7eafc8fdc2c2901138ba41bfe0a61f97d9d898094b9020116937f681
M5B_DEVICE_BOOT_PREFIX_MATCH=YES
M5B_FULL_CONTEXT_VERIFIED=YES
```

### Single B boot and timing

Immediately before the boot, Slot B was bootable with retry count 7. Exactly one
`fastboot reboot` was issued after selecting B. Only the Fastboot USB identity was
observed:

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-10T13:07:02.427Z
FASTBOOT_REAPPEAR_TIMESTAMP=2026-09-10T13:07:06.919Z
AUTOMATIC_FASTBOOT_REAPPEAR=YES
ELAPSED=4.492s
OBSERVATION_WINDOW=12s
M4B_REFERENCE=4.755s
M5B_BASELINE_4P7S_RETURN_SUPPRESSED=NO
MANUAL_RECOVERY=NO
```

The automatic return was inside the defined 4.3–5.3-second historical band. Slot
metadata after the attempt was `current-slot=b`, retry count 6, and
`unbootable=no`. Slot A was selected immediately, with no second B boot, and
Android restored as `_a`, `boot_completed=1`.

### Dumps and conclusion

```text
baseline oops=36734fcec8fdc29ec90aebfaca96b48777c91e92101b43ff08ab2b71f2afea5d
post oops=f000538f9ab29f1578d6e5e50baa668c948cea7b2ad0dfb63ee1fcc5fb38a4a4 CHANGED
pstore entries baseline/post=0/0
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED

M5B_CODE0_HANDOFF_EFFECT=NO
MAINLINE_CODE0_MZ_EFI_VS_RAW_HANDOFF_CAUSAL=NOT_SUPPORTED
MAINLINE_PRIMARY_ENTRY_EXECUTION=NOT_CONFIRMED
ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED
FINAL_GATE=MAINLINE_V2_M5B_DIRECT_ENTRY_NO_EFFECT
```

The four-byte `code0`/MZ change was not sufficient to alter the 4.7-second return.
No claim is made about a `ccmp` crash or ABL rejecting EFI. The next proposed stage
is `MAINLINE_V2_M5C_IMAGE_HEADER_FIELD_ISOLATION`, focused on remaining Image
header/load semantics. M5C awaits explicit approval and was not executed.
