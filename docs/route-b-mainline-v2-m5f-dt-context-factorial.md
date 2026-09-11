# Route B Mainline V2 M5F1 — DT context factorial Cell C

Status: true-device test complete. Final gate:
`MAINLINE_V2_M5F1_M1_DTBO_RESTORES_4P7S`.
Android A restored. Slot B retains exact M5D `boot_b`, exact Stock
`vendor_boot_b`, and M1 `dtbo_b`. Cell B and M5G were not executed.

This round does not change Linux Image, boot packaging, vendor_boot, vbmeta,
or firmware. The only logical variable is DTBO context.

## Causal basis

```text
M5D: exact M5D boot + M1 vendor_boot + M1 dtbo     4.532s automatic return
M5E: exact M5D boot + Stock vendor_boot + Stock dtbo  >12s, no automatic return
DT_CONTEXT_CROSSOVER_EFFECT=YES
M1_DT_CONTEXT_PAIR_CAUSAL=STRONGLY_SUPPORTED
MAINLINE_IMAGE_HEADER_AS_SOLE_CAUSE=NOT_SUPPORTED
```

M5E flipped the ~4.7s return by swapping the whole DT pair. It did not
separate vendor_boot from dtbo. Cell C is the current minimum change from
the live M5E Slot B: Stock dtbo → M1 dtbo only.

```text
             vendor_boot   dtbo   runtime
A            Stock         Stock  >12s          (M5E)
B            M1            Stock  pending
C            Stock         M1     4.812s        (this round)
D            M1            M1     4.532s        (M5D)
```

```text
BOOT_IMAGE_VARIABLE=NO
KERNEL_VARIABLE=NO
VENDOR_BOOT_VARIABLE=NO
VBMETA_VARIABLE=NO
FIRMWARE_VARIABLE=NO
DTBO_CONTEXT=YES
```

## Constraints

```text
MEM0_READ_BEFORE_M5F1=YES
MEM0_READ_BEFORE_WRITE=YES
local build / validator / source gate / actionlint / binary validation=NO
GHA-only=YES
new build this round=NO
Slot A flash/erase/format=NO
BOOT_B_WRITE=FORBIDDEN
VENDOR_BOOT_B_WRITE=FORBIDDEN
vbmeta* write=NO
firmware write=NO
allowed write: dtbo_b
B boots: 1
SECOND_B_BOOT_FORBIDDEN=YES
Cell B auto-exec=NO
M5G auto-exec=NO
```

## Exact identities

Authoritative M5D boot, not rewritten:

```text
artifact size: 35110912
SHA256: 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
M5F1_M5D_BOOT_EXACT=YES
```

Stock vendor_boot, not rewritten. Physical size equals the Stock file, so
whole-partition SHA is the Stock-domain gate:

```text
physical size: 100663296
whole SHA256: aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
M5F1_STOCK_VENDOR_BOOT_EXACT=YES
```

Start dtbo was exact Stock whole partition:

```text
physical size: 33554432
whole SHA256: 018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
M5F1_START_DTBO_STOCK=YES
```

M1 dtbo authoritative private artifact, not regenerated:

```text
source: private CI run 34338768052  mainline-v2-m1-dtbo.img
size: 387
SHA256: 316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
1-entry no-op overlay, board-id <45 0>, msm-id NONE, target-path "/",
compatible qcom,kona-mtp / qcom,kona / qcom,mtp,
marker qcom,thyme-route-b-noop
```

Hash domain is prefix 387 bytes. Remainder is the historical M1 exact Stock
tail from offset 387:

```text
remainder SHA256: 0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd
```

## Pre-write Android A

```text
device=thyme
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0 magisk
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
vendor_boot_b whole SHA256=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
dtbo_b whole SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
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

```text
MAINLINE V2 M5F1
FACTORIAL CELL C
KEEP: boot_b = exact M5D; vendor_boot_b = exact Stock
CHANGE ONLY: dtbo_b Stock → M1
NO WRITE: boot_b, vendor_boot_b, vbmeta*, firmware, ANY *_a

fastboot flash dtbo_b <M1 387-byte artifact>  OKAY
current-slot remained a
retry:b remained 6, unbootable:b=no
```

Returned to Android A without selecting B. Host USB dropped after that
reboot (hub port empty; sibling devices stayed). User restored Android A
USB. This is host-path loss, not Cell C runtime.

Independent Android A readback:

```text
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH=YES
vendor_boot_b whole SHA256=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972 MATCH=YES
dtbo_b first 387 SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1 MATCH=YES
dtbo_b remainder SHA256=0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd MATCH=YES
vbmeta_b / vbmeta_system_b / xbl_b / abl_b / tz_b prefixes=stock
M5F1_CELL_C_EXACT_VERIFIED=YES
```

## Pre-runtime matrix

```text
CELL A BASELINE
  boot: M5D
  vendor_boot: STOCK
  dtbo: STOCK
  runtime: >12s

CELL C TEST
  boot: SAME M5D
  vendor_boot: SAME STOCK
  dtbo: M1
  runtime: PENDING
  ONLY_LOGICAL_VARIABLE=DTBO_CONTEXT
```

Dump baseline after the context-write Android A cycle, not cleared:

```text
pstore entries=0
oops=c173cce43884af90e8ec10e8940ca36d100c6d00904f617a11d9b7e8fd792fea
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
```

## Single B boot

Returned to Fastboot on slot A. `set_active b` made `current-slot=b`,
retry:b=7, unbootable:b=no. Exactly one `fastboot reboot`. No second B boot.

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-11T03:12:55.788Z
FASTBOOT_REAPPEAR_TIMESTAMP=2026-09-11T03:13:00.600Z
AUTOMATIC_FASTBOOT_REAPPEAR=YES
FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR=4.812s
OBSERVATION_WINDOW=12s
M5D_REFERENCE=4.532s
CASE=C1
```

USB evidence is Fastboot protocol presence (`18d1:d00d`). Manual recovery
was not required.

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
oops pre-B-boot=c173cce43884af90e8ec10e8940ca36d100c6d00904f617a11d9b7e8fd792fea
oops post=713e2d4bee58f16be2be0fe92f9bd8e4200ddd23428b5a92a49dac502bc71ab7 CHANGED
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED
```

Changed oops contains stock Android `reboot,bootloader` records from
`/system/bin/reboot`. No `Linux version 6.6` / Mainline strings. Not
Mainline evidence.

Post-test B identity, not rewritten:

```text
boot_b first 35110912 = exact M5D
vendor_boot_b whole = stock
dtbo_b first 387 = M1
dtbo remainder = historical M1 Stock tail
vbmeta / firmware prefixes = stock
B_FINAL=M5D boot + Stock vendor_boot + M1 dtbo
```

## Classification

This is Case C1 of the approved matrix.

```text
M5F1_DTBO_ONLY_EFFECT=YES
M1_DTBO_SUFFICIENT_ON_STOCK_VENDOR_BOOT=STRONGLY_SUPPORTED
FINAL_GATE=MAINLINE_V2_M5F1_M1_DTBO_RESTORES_4P7S
```

Exact same M5D boot and exact same Stock vendor_boot:

```text
Stock dtbo:  no automatic Fastboot return in 12s
M1 dtbo:     4.812s automatic Fastboot return
```

The only logical variable that changed runtime behavior is DTBO context.
M1's 1-entry no-op dtbo is sufficient, in a Stock vendor_boot background,
to restore the ~4.7s return.

Do not assert from this round:

- board-id `<45 0>` is the sole cause
- no-op overlay syntax caused it
- ABL crashed
- kernel did not run
- vendor_boot cannot independently trigger the same return

The locked claim is: M1 dtbo artifact / DTBO context is a sufficient causal
factor in Stock vendor_boot background.

## Next, not executed

```text
NEXT=CELL B
  same exact M5D boot
  M1 vendor_boot + Stock dtbo
NO NEXT STAGE EXECUTED=YES
WAIT FOR USER APPROVAL
```
