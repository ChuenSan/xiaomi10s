# Route B Mainline V2 M5J — Stock DTBO table + M1 no-op payload control

Status: true-device test complete. Final gate:
`MAINLINE_V2_M5J_NOOP_PAYLOAD_RESTORES_4P7S`.
Android A restored. Slot B retains exact M5D `boot_b`, the M5H `<45 0>`
Stock DTB0 `vendor_boot_b`, and the M5J Stock-table / no-op `dtbo_b`.
Stock dtbo was not restored. M5K was not executed.

## Why M5I alias mapping was paused

M5I symbolized the historical M1 base (`DTC_FLAGS=-@`) and still could not
apply Stock DTBO entry 21:

```text
Stock entry21 fixups:     154
historical M1 resolved:   0
symbolized M1 resolved:   11
symbolized M1 missing:    143
fdtoverlay:               FAIL FDT_ERR_NOTFOUND
```

The remaining 143 names are downstream vs Mainline label / naming / topology
differences. That does not force Mainline to accept the whole Stock
124-fragment overlay. The cleaner alternative is to keep the Stock DTBO
container/table that ABL may require, while not applying the Stock overlay
to a Mainline base:

```text
Stock 29-entry DTBO table
+
M1 no-op thyme payload in the selected entry
```

M5G already built and validated that control. M5J is the true-device test
of that path, not a 143-alias campaign.

## Question

Cell C already showed that M1 dtbo is sufficient for the ~4.7s Fastboot
return on Stock vendor_boot (`4.812s`). It did not split:

```text
one-entry container / table / packaging
versus
no-op overlay payload
```

M5H then gave a clean DTBO baseline on the current B:

```text
M5D boot
+ M5H single Stock DTB0 vendor_boot, base board-id <45 0>
+ exact Stock 29-entry dtbo, Stock thyme entry21
→ PRIMARY_OBSERVATION=>12s
```

M5J keeps that boot and vendor_boot byte-identical and changes only the
selected thyme overlay payload.

```text
intentional variable : SELECTED_THYME_OVERLAY_PAYLOAD
DTBO container       : Stock 29-entry table          (unchanged)
entry_count          : 29                            (unchanged)
table metadata       : exact Stock                   (unchanged)
selector metadata    : exact Stock                   (unchanged)
entry offsets/layout : Stock-compatible              (unchanged)
28 other payloads    : exact Stock                   (unchanged)
entry21 payload      : Stock 124-fragment overlay
                       → padded M1 no-op overlay
```

## Constraints

```text
MEM0_READ_BEFORE_M5J=YES
MEM0_READ_BEFORE_WRITE=YES
LOCAL_BUILD=NO
LOCAL_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
GHA_ONLY=YES
new build this round=NO
SLOT_A_WRITE=FORBIDDEN
only partition write=dtbo_b
boot_b write=NO
vendor_boot_b write=NO
vbmeta* / firmware write=NO
B boots=1
SECOND_B_BOOT_FORBIDDEN=YES
Stock dtbo restore=NO
M5K auto-exec=NO
DTBO semantic validity=private GHA run 34559797694
device stage confirms whole-image SHA only
```

## Candidate identity

Re-downloaded from private run [`34559797694`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34559797694),
not regenerated, not modified. Located by SHA among the run artifacts, not
by guessing the filename. The matching file in that run is
`m5g-d-stock-table-m1-payload-dtbo.img`.

```text
size     33554432
SHA256   31e1c2ff828076c52a2f018f329fe23d7c62e59d3993a53bdf798396a61c7c37
```

Authoritative M5G validation, reused as-is:

```text
entry_count=29
table metadata=exact Stock
thyme selector metadata=exact Stock
28 non-thyme payloads=byte-for-byte exact Stock
bytes outside entry21 slot=exact Stock
entry21=M1 no-op FDT padded into the Stock 484885-byte slot
dtc/fdtoverlay=PASS
FIXED_SLOT_REPLACEMENT_UNSAFE=NO
PRIVATE ARTIFACT ONLY=YES
READY_FOR_M5G_D_STOCK_TABLE_M1_PAYLOAD_CONTROL=YES
```

Device-side DTBO parsing is not a gate. The device confirms only the
whole-image SHA.

## Android A baseline and pre-write context

```text
slot_suffix=_a
boot_completed=1
root=uid=0 magisk
device=thyme
build_fingerprint=Xiaomi/thyme/thyme:13/TKQ1.220829.002/V14.0.6.0.TGACNXM:user/release-keys
```

Independent Android A `dd | sha256sum` readbacks, no binary pulled to the
host for hashing:

```text
boot_b first 35110912                     4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH
vendor_boot_b first 548864                2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9  MATCH
vendor_boot_b [548864,EOF)                5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52  MATCH
dtbo_b whole                              018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634  MATCH
vbmeta_b [0,8192)                          37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c  stock
vbmeta_system_b [0,4096)                   3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355  stock
abl_b / xbl_b / xbl_config_b / tz_b        byte-identical to the M5H record
M5J_START_M5H_CONTEXT_EXACT=YES
```

Fastboot preflight:

```text
product=thyme   unlocked=yes   current-slot=a
snapshot-update-status=none    battery-soc-ok=yes
slot-retry-count:b=6   slot-unbootable:b=no
```

## Write

```text
fastboot flash dtbo_b m5g-d-stock-table-m1-payload-dtbo.img   OKAY
NO WRITE: boot_b, vendor_boot_b, vbmeta*, firmware, ANY *_a
current-slot remained a; reboot went to Android A, not B
```

Post-write readback on Android A:

```text
dtbo_b whole                              31e1c2ff828076c52a2f018f329fe23d7c62e59d3993a53bdf798396a61c7c37  MATCH
boot_b first 35110912                     4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH
vendor_boot_b first 548864                2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9  MATCH
vendor_boot_b [548864,EOF)                5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52  MATCH
vbmeta / firmware                         stock, byte-identical to pre-write
M5J_FULL_CONTEXT_VERIFIED=YES
```

## Direct comparison

```text
REFERENCE M5H
boot:     exact M5D
vendor:   M5H single Stock DTB0, board-id <45 0>
dtbo:     Stock 29-entry, Stock thyme entry21
runtime:  PRIMARY_OBSERVATION=>12s

M5J
boot:     same exact M5D
vendor:   same exact M5H vendor
dtbo:     same Stock 29-entry table / metadata / layout
entry21:  padded M1 no-op overlay
runtime:  4.922s automatic Fastboot return
```

Pre-registered thresholds:

```text
~4.3-5.3s automatic Fastboot return  -> MAINLINE_V2_M5J_NOOP_PAYLOAD_RESTORES_4P7S
>12s, no automatic return            -> MAINLINE_V2_M5J_STOCK_TABLE_NOOP_SUPPRESSES_4P7S
5.3-12s                              -> MAINLINE_V2_M5J_DTBO_CONTROL_INCONCLUSIVE
```

## Single B boot

```text
pre : current-slot=a, retry:b=6, unbootable:b=no
fastboot set_active b -> current-slot=b, retry:b=7, unbootable:b=no
exactly one fastboot reboot
SECOND_B_BOOT_FORBIDDEN=YES
```

USB evidence is Fastboot protocol presence (`18d1:d00d`) only.

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-11T08:03:45.691Z
FASTBOOT_REAPPEAR_TIMESTAMP=2026-09-11T08:03:50.613Z
FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR=4.922
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=YES
PRIMARY_OBSERVATION=4.922s
MANUAL_RECOVERY=NO
CASE=J2
```

## Result

The realized case is J2. Replacing only the selected thyme overlay payload
with the padded M1 no-op restores the ~4.7s automatic Fastboot return on an
otherwise M5H context that had held for >12s.

```text
M5J_NOOP_PAYLOAD_EFFECT=YES
M1_NOOP_PAYLOAD_ALONE_SUFFICIENT=YES
M1_NOOP_PAYLOAD_SUFFICIENT_ON_STOCK_TABLE=STRONGLY_SUPPORTED
STOCK_DTBO_CONTAINER_WITH_NOOP_PAYLOAD_COMPATIBLE=NOT_SUPPORTED
ONE_ENTRY_DTBO_PACKAGING_CAUSAL_FAMILY=NOT_ESTABLISHED
FINAL_GATE=MAINLINE_V2_M5J_NOOP_PAYLOAD_RESTORES_4P7S
```

Permitted statement: on this exact M5H boot/vendor background, the M1 no-op
entry21 replacement — including the required FDT `totalsize` expansion and
zero padding into the Stock 484885-byte slot — is sufficient to restore the
~4.7s wall. The Stock 29-entry container/table is not enough to suppress
that return when the selected payload is this no-op.

Not permitted, and not claimed:

- that one-entry DTBO packaging caused Cell C `4.812s`
- that ABL rejects every no-op overlay, versus this padded FDT / target-path
  / missing-symbols / slot-fill construction
- that libfdt `fdtoverlay PASS` equals Xiaomi ABL success
- that the kernel executed
- that Mainline booted
- that Stock table + a differently structured overlay would also fail

Private GHA already applied this padded no-op with `dtc` / `fdtoverlay`
successfully. The device still returned in `4.922s`. The next split is
payload semantics, not another vendor_boot topology test.

Because J2 occurred, the previously hoped Mainline packaging

```text
Stock ABL-compatible 29-entry table
+
current M1 no-op thyme overlay
```

is not a path through the ~4.7s wall. Do not proceed to
`MAINLINE_V2_M5K_MAINLINE_BASE_PLUS_STOCK_TABLE_NOOP_DTBO` on this payload.

## Recovery

Automatic Fastboot was already present after `4.922s`. No second B boot.
No ordinary reboot from a stuck state. No physical recovery.

```text
pre-recovery: current-slot=b, retry:b=6, unbootable:b=no, successful:b=no
fastboot set_active a -> current-slot=a
fastboot reboot
ANDROID_A_RESTORED=YES
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0
```

## Dumps

Read-only, not cleared. Pre-write hashes still match the M5H post-test
image. The B-boot comparison baseline is the post-write / pre-B-boot
capture taken after the Android A reboot that followed the `dtbo_b`
write. That Android A reboot is not Mainline evidence.

```text
pstore entries            0 / 0 / 0                      UNCHANGED
minidump                  e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a  UNCHANGED
rawdump                   254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917  UNCHANGED
logdump                   3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351  UNCHANGED
logfs pre-write           20045266ddf9f1c2158c85449caabaf85d846ceaa83f24133ed325516fc21e2a
logfs pre-B-boot          aaf0c99a8d2067c63ec6c4e0f3efa625129fabeaae37e39283756a5e657eeecb
logfs post-test           88b92f8c8f47f2a4ee52eb996319e7b1327a10c41a2d478d55448c38fd129d7a  CHANGED
oops pre-write            0c14499d01fa6924c1e629c4f5981fe0eda0fcaee463930e8cbd94f39f250bec
oops pre-B-boot           6a97f92786db40b617f25760a602ea56eddcba57b36ae6f51403a71759d53bb1
oops post-test            7ed99bce6843bf09237e171b2ed453a69733a2503f8e9e769f1dc6858a3fdf36  CHANGED
```

`oops` changed, so it is judged at content level. Post-test `strings`:

```text
Linux version banners            0
literal "6.6." kernel strings    0
mainline / 6.6.x markers         0
"Unable to handle kernel"        0
"Kernel panic"                   0
"Call trace" / "pc :"            0
reboot,bootloader records        21
Reason: Restart lines            7
calendar dates                   2023-09-04 (device clock)
```

Apparent `2026` hits are dmesg timestamps such as `[ 2026.049786]`, not
calendar year 2026. Android A `reboot,bootloader` records are not Mainline
evidence.

```text
OOPS_MAINLINE_EVIDENCE=NO
```

## B final state

Stock dtbo was not restored.

```text
boot_b:         exact M5D
vendor_boot_b:  exact M5H board45 Stock DTB0
dtbo_b:         M5J Stock 29-entry table / padded M1 no-op entry21
active slot:    A
```

## Next, not executed

```text
NEXT=MAINLINE_V2_M5K_DTBO_PAYLOAD_SEMANTICS_AUDIT_CI
focus:
  no-op fragment structure
  target-path="/"
  board-id placement
  overlay symbols/fixups absence
  payload totalsize / padding into the Stock slot
not a Vendor Track continuation
not MAINLINE_V2_M5K_MAINLINE_BASE_PLUS_STOCK_TABLE_NOOP_DTBO
WAIT_FOR_USER_APPROVAL=YES
NO NEXT STAGE EXECUTED=YES
```
