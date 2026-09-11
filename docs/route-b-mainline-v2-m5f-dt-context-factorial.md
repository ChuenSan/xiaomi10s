# Route B Mainline V2 M5F — DT context factorial

Status: 2×2 true-device factorial complete. Final gate:
`MAINLINE_V2_M5F2_M1_VENDOR_BOOT_RESTORES_4P7S`.
Android A restored. Slot B retains exact M5D `boot_b`, M1 `vendor_boot_b`,
and exact Stock `dtbo_b`. M5G was not executed.

## M5F1 — dtbo-only factorial Cell C

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

## M5F2 — vendor_boot-only factorial Cell B

M5F2 completed the missing Cell B while preserving the same exact M5D boot.
It first reconstructed static Cell A without booting B, then changed only
`vendor_boot_b` to M1, returned to Android A for independent readback, and
performed one final B boot.

### Constraints

```text
MEM0_READ_BEFORE_M5F2=YES
MEM0_READ_BEFORE_EACH_DEVICE_WRITE=YES
local build / validator / source gate / actionlint / binary validation=NO
GHA-only=YES
new build this round=NO
Slot A flash/erase/format=NO
BOOT_B_WRITE=FORBIDDEN
vbmeta* write=NO
firmware write=NO
allowed writes: dtbo_b, vendor_boot_b
B boots: 1
SECOND_B_BOOT_FORBIDDEN=YES
M5G auto-exec=NO
```

The existing private M1 artifact was used without regeneration:

```text
mainline-v2-m1-vendor_boot.img
size=114688
SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
```

The authoritative Stock dtbo was rehashed read-only:

```text
MIUI14ROM/image/dtbo.img
size=33554432
SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
```

### Start Cell C gate

Android A was `_a`, boot completed, and root was available. The live B
identity matched the M5F1 final state:

```text
boot_b first 35110912=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
vendor_boot_b whole=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
dtbo_b first 387=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
dtbo_b remainder=0a0549ee65b90de9843c37d92ff337add3c848c21cf68ca9b90e8064e40dffdd
vbmeta_b / vbmeta_system_b / xbl_b / abl_b / tz_b prefixes=stock
M5F2_START_CELL_C_EXACT=YES
M5F2_M5D_BOOT_EXACT=YES
```

### Phase 1 — static Cell A reconstruction

Fastboot preflight was `product=thyme`, `unlocked=yes`, `current-slot=a`,
`snapshot-update-status=none`, `battery-soc-ok=yes`, retry:b=6,
unbootable:b=no.

```text
CHANGE ONLY: dtbo_b M1 → Stock
fastboot flash dtbo_b MIUI14ROM/image/dtbo.img  OKAY
boot_b / vendor_boot_b / vbmeta* / firmware / *_a write=NO
```

The device returned directly to Android A. Independent readback matched:

```text
boot_b first 35110912=exact M5D
vendor_boot_b whole=exact Stock
dtbo_b whole=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
vbmeta / firmware prefixes=stock
M5F2_STATIC_CELL_A_RECONSTRUCTED=YES
CELL_A_B_BOOT=NO
```

Cell A was static only; its `>12s` runtime remains the M5E result and was not
retested.

### Phase 2 — exact Cell B construction

After another mem0 read, Fastboot again matched `thyme`, unlocked, slot A,
no snapshot update, battery OK, retry:b=6, and unbootable:b=no.

```text
CHANGE ONLY: vendor_boot_b Stock → M1
fastboot flash vendor_boot_b <existing exact M1 artifact>  OKAY
dtbo_b / boot_b / vbmeta* / firmware / *_a write=NO
```

The device again returned to Android A before any B boot. Independent Cell B
readback matched every gate:

```text
boot_b first 35110912=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
vendor_boot_b first 114688=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
vendor_boot_b remainder=3d6cb7047e6d0b70a764b6dae548a720904378c62f151732d5faaab8ea703a74
dtbo_b whole=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
vbmeta / firmware prefixes=stock
M5F2_CELL_B_EXACT_VERIFIED=YES
```

Dump baseline was read-only and not cleared:

```text
pstore entries=0
oops=ee27c5c34f2f66dca9031b8a8493634c195f7ad48c281d8a9a9d4374a21cc7d2
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
```

### Single B boot

Before the sole B boot, slot B had retry=6 and unbootable=no. `set_active b`
produced slot B, retry=7, unbootable=no. Exactly one `fastboot reboot` was
issued.

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-11T03:26:33.558Z
FASTBOOT_REAPPEAR_TIMESTAMP=2026-09-11T03:26:38.567Z
AUTOMATIC_FASTBOOT_REAPPEAR=YES
FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR=5.008s
OBSERVATION_WINDOW=12s
MANUAL_RECOVERY_REQUIRED=NO
SECOND_B_BOOT_FORBIDDEN=YES
```

Post-attempt metadata was slot B, retry=6, unbootable=no. Recovery selected A
from Fastboot and rebooted once to Android A. No second B boot occurred.

```text
ANDROID_A_RESTORED=YES
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0
B_FINAL=M5D boot + M1 vendor_boot + Stock dtbo
```

Post-test identity remained exact. Dump comparison:

```text
pstore entries baseline/post=0/0 UNCHANGED
oops baseline=ee27c5c34f2f66dca9031b8a8493634c195f7ad48c281d8a9a9d4374a21cc7d2
oops post=c31867564f670a18e66f51293af0b82b201d55de7571c351af6696149db816b3 CHANGED
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED
```

The changed oops contains Stock Android `reboot,bootloader` records from
`/system/bin/reboot`; no Linux 6.6/Mainline marker was found. It is not used
as Mainline evidence.

## Complete factorial matrix

```text
             vendor_boot   dtbo    runtime
A            Stock         Stock   >12s
B            M1            Stock   5.008s
C            Stock         M1      4.812s
D            M1            M1      4.532s
```

The controlled Cell A→B comparison kept the exact same M5D boot and exact
same Stock dtbo. Its only logical runtime variable was `VENDOR_BOOT_CONTEXT`.
The controlled A→C comparison kept the same boot and Stock vendor_boot; its
only logical runtime variable was `DTBO_CONTEXT`.

```text
M5F2_VENDOR_BOOT_ONLY_EFFECT=YES
M1_VENDOR_BOOT_SUFFICIENT_ON_STOCK_DTBO=STRONGLY_SUPPORTED
M1_DTBO_SUFFICIENT_ON_STOCK_VENDOR_BOOT=STRONGLY_SUPPORTED
FINAL_GATE=MAINLINE_V2_M5F2_M1_VENDOR_BOOT_RESTORES_4P7S
```

Both M1 DT-context components are independently sufficient, while the other
component is Stock, to trigger the same approximate 4.7-second return. This
strongly supports either at least two independent ABL-visible compatibility
problems or distinct structural characteristics that independently reach a
shared bootloader fallback/reset path. The matrix does not identify or prove
a specific ABL implementation or function.

## Next, not executed

```text
NEXT=MAINLINE_V2_M5G_DT_PACKAGING_COMPONENT_AUDIT
AUDIT vendor_boot: 4-concat Stock vs 1 Mainline DTB, board-id, compatible,
                   memory placeholder, DTB concatenation/layout
AUDIT dtbo: Stock 29-entry vs M1 1-entry, header, entry metadata, board-id,
            overlay payload
NO NEXT STAGE EXECUTED=YES
WAIT FOR USER APPROVAL
```
