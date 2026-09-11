# Route B Mainline V2 M5E — DT context crossover

Status: true-device test complete. Final gate:
`MAINLINE_V2_M5E_STOCK_DT_SUPPRESSES_4P7S`.
Android A restored. Slot B retains exact M5D `boot_b` plus Stock DT context.
M5F was not executed.

This round does not change Linux Image, boot packaging, vbmeta, or firmware.
The only logical variable is the ABL-visible DT context pair
(`vendor_boot_b` + `dtbo_b`).

## Causal basis

```text
M0: exact Mainline boot + Stock DT     no ~4.7s timed Fastboot return
M1: same exact boot + Mainline DT      4.821s automatic return
M2–M5D: same M1 DT, Image-header scans 4.492–4.790s
M5D: exact M5D boot + M1 DT            4.532s automatic return
M5A: Stock 4.19 spin + Stock DT        >12s, but kernel also changed
```

R1 showed Stock vs M1 differ in ABL-visible DT packaging, not just Image
header:

```text
R1_DTB_BOOTLOADER_METADATA_DIFFERENCE_FOUND=YES
R1_DT_PACKAGING_DIFFERENCE_FOUND=YES
R1_ALIOTH_SUCCESS_HEADER_MATCHES_MAINLINE_STYLE=CONFIG_YES_BINARY_PENDING_GHA
R1_NO_DECISIVE_REFERENCE_DIFFERENCE=NO
```

Stock thyme: vendor_boot 4-concat kona-family FDT, dtbo 29 entries,
base board-id `<0 0>`, thyme overlay `<45 0>`.
M1: vendor_boot 1 Mainline DTB, dtbo 1 no-op overlay, base and overlay
both `<45 0>`.

M5E keeps the exact M5D boot and swaps only the DT pair that historically
introduced the 4.7s return.

```text
BOOT_IMAGE_VARIABLE=NO
KERNEL_VARIABLE=NO
IMAGE_HEADER_VARIABLE=NO
PRIMARY_ENTRY_VARIABLE=NO
RAMDISK_VARIABLE=NO
VBMETA_VARIABLE=NO
FIRMWARE_VARIABLE=NO
DT_CONTEXT_PAIR=YES
```

Alioth Image/DTB `workflow_dispatch` is independent reference evidence and
was not a M5E Gate.

## Constraints

```text
MEM0_READ_BEFORE_M5E=YES
MEM0_READ_BEFORE_WRITE=YES
local build / validator / source gate / actionlint / binary validation=NO
GHA-only=YES
new build this round=NO
Slot A flash/erase/format=NO
BOOT_B_WRITE=FORBIDDEN
vbmeta_b / vbmeta_system_b write=NO
firmware write=NO
allowed writes: vendor_boot_b, dtbo_b
B boots: 1
SECOND_B_BOOT_FORBIDDEN=YES
M1 context restore after test=NO
M5F auto-exec=NO
```

## Exact identities

Authoritative M5D private Actions artifact, not regenerated:

```text
run: 34487382191
artifact: thyme-mainline-v2-m5d-pe-offset-zero-1a30f48d5ef86ff2dce7df6f761ca925f60aa9e7
Image SHA256: 5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a
boot SHA256: 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
artifact size: 35110912
header: code0 0x146c7028, code1 0x146c7027, text_offset 0x80000,
        image_size 0x2220000, flags 0xa, PE offset 0x0, primary_entry b .
```

M1 start context (prefix domain, remainder observational for M1 artifact
size; remainder is still an exact Gate for this round):

```text
vendor_boot_b first 114688 SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
vendor_boot_b remainder SHA256=3d6cb7047e6d0b70a764b6dae548a720904378c62f151732d5faaab8ea703a74
dtbo_b first 387 SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
dtbo_b remainder SHA256=0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd
```

Stock V14.0.6.0.TGACNXM files, rehashed read-only, not re-downloaded:

```text
/Volumes/LinuxDev/thyme-mainline/MIUI14ROM/image/vendor_boot.img
  size=100663296
  SHA256=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
/Volumes/LinuxDev/thyme-mainline/MIUI14ROM/image/dtbo.img
  size=33554432
  SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
```

Physical partition sizes equal those files, so Stock identity after write
uses whole-partition SHA256.

## Pre-write Android A

```text
adb device=thyme
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0 magisk
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
M5D_DEVICE_BOOT_PREFIX_MATCH=YES
M5E_START_CONTEXT_M1=YES
vbmeta_b prefix 8192=37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
vbmeta_system_b prefix 4096=3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
xbl_b prefix 3575808=8a170d774226c03d9657883058a512f80e96ea76db0be81ff73c4f6340e6841a
abl_b prefix 208896=1d14cad5e62d963c88e24aa8dab50b577a0f8d0b39323127b5f1677feb2c5cc2
tz_b prefix 3190784=de0adae9c8a27f9ac11722e693f5813afcaaa759a2b0d451b32a812b0eeb437b
```

## Writes

Fastboot preflight: `product=thyme`, `unlocked=yes`, `current-slot=a`,
`snapshot-update-status=none`, `battery-soc-ok=yes`, retry:b=6,
unbootable:b=no.

Only two partition writes, then reboot to Android A without selecting B:

```text
fastboot flash vendor_boot_b MIUI14ROM/image/vendor_boot.img  OKAY
fastboot flash dtbo_b        MIUI14ROM/image/dtbo.img         OKAY
current-slot remained a
retry:b remained 6, unbootable:b=no
NO WRITE: boot_b, vbmeta*, firmware, ANY *_a
```

Independent Android A readback:

```text
vendor_boot_b size=100663296 SHA256=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972 MATCH=YES
dtbo_b        size=33554432  SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634 MATCH=YES
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH=YES
vbmeta_b / vbmeta_system_b / xbl_b / abl_b / tz_b prefixes=stock
M5E_CROSSOVER_CONTEXT_VERIFIED=YES
```

## Pre-runtime matrix

```text
REFERENCE M5D:
  boot:         M5D
  vendor_boot:  M1
  dtbo:         M1
  elapsed:      4.532s

TEST M5E:
  boot:         SAME EXACT M5D
  vendor_boot:  STOCK
  dtbo:         STOCK
  runtime:      PENDING
```

Dump baseline after the context-write Android A cycle, not cleared:

```text
pstore entries=0
oops=77895884a644b298bf67947a9c9b375e62cb3ff7eeaccf1b4ebb21d122cef120
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
```

## Single B boot

Returned to Fastboot on slot A. `set_active b` made `current-slot=b`,
retry:b=7, unbootable:b=no. A host-side `getvar` parse abort then stopped
before reboot; the device remained in Fastboot on B. Exactly one
`fastboot reboot` followed. No second B boot.

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-11T02:15:34.029Z
FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED
AUTOMATIC_FASTBOOT_REAPPEAR=NO
OBSERVATION_WINDOW=12s
M5D_REFERENCE=4.532s
M5E_4P7S_RETURN_SUPPRESSED=YES
DT_CONTEXT_CROSSOVER_EFFECT=YES
CASE=A
```

USB evidence is Fastboot protocol presence (`18d1:d00d`). Fastboot became
reachable again at `2026-09-11T02:18:03.193Z` (149.164s after disappear) only
because of the **user's manual physical Fastboot recovery**, not an automatic
return. The agent did not press keys and did not issue an ordinary reboot on
slot B. The 149.164s value is a manual-recovery time, not boot-chain,
watchdog, ABL-fallback or timeout evidence.

```text
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO
MANUAL_FASTBOOT_RECOVERY_AFTER_WINDOW=YES
MANUAL_RECOVERY=YES
PRIMARY_OBSERVATION=>12s
```

Post-attempt metadata before recovery:

```text
current-slot=b
retry:b=6
unbootable:b=no
```

Recovery: `fastboot set_active a`, confirm `current-slot=a`, `fastboot reboot`.

```text
ANDROID_A_RESTORED=YES
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0
SECOND_B_BOOT_FORBIDDEN=YES
```

## Dumps

```text
pstore entries baseline/post=0/0 UNCHANGED
oops pre-B-boot=77895884a644b298bf67947a9c9b375e62cb3ff7eeaccf1b4ebb21d122cef120
oops post=3b939ce82a26b2cbfc65bf163627e6fe5ff64e8ba50aa89eb08df06c17cccf7c CHANGED
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED
```

Changed oops contains stock Android 4.19 `reboot,bootloader` records from
`/system/bin/reboot`. No Linux 6.6.156 / Mainline strings. Not Mainline
evidence.

Post-test B identity, not rewritten:

```text
boot_b first 35110912 = exact M5D
vendor_boot_b whole = stock
dtbo_b whole = stock
vbmeta / firmware prefixes = stock
B_FINAL=M5D boot + Stock DT context
```

## Classification

This is Case A of the approved matrix.

```text
M1_DT_CONTEXT_PAIR_CAUSAL=STRONGLY_SUPPORTED
MAINLINE_IMAGE_HEADER_AS_SOLE_CAUSE=NOT_SUPPORTED
FINAL_GATE=MAINLINE_V2_M5E_STOCK_DT_SUPPRESSES_4P7S
```

Exact same M5D boot:

```text
M1 DT context:  4.532s automatic Fastboot return
Stock DT context: no automatic Fastboot return in 12s
```

The only logical variable that changed runtime behavior is
`vendor_boot`/`dtbo` context pair.

Do not assert from this round:

- vendor_boot alone caused it
- dtbo alone caused it
- board-id base placement necessarily caused it
- Linux failed to parse DTB
- a specific ABL function is buggy

The locked claim is: DT_CONTEXT_PAIR / ABL-visible DT packaging is a strong
causal variable for the ~4.7s return.

## Next, not executed

```text
NEXT=MAINLINE_V2_M5F_DT_CONTEXT_FACTORIAL_ISOLATION
2x2, always exact SAME M5D boot:
  A Stock vendor_boot + Stock dtbo     (this round)
  B M1 vendor_boot + Stock dtbo
  C Stock vendor_boot + M1 dtbo
  D M1 vendor_boot + M1 dtbo           (M5D reference)
NO NEXT STAGE EXECUTED=YES
WAIT FOR USER APPROVAL
```
