# Route B Mainline V2 M5M-A — target-path="/" no-marker true-device control

Stage id:

```text
MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_TRUE_DEVICE_CONTROL
```

Single source semantic variable versus L1:

```text
MARKER_PROPERTY_PRESENCE
  L1  qcom,thyme-route-b-noop EMPTY_BOOLEAN length=0  PRESENT
  A   same property                                           ABSENT
```

Held: exact Stock model, fragment count 1, `target-path="/"`, `__fixups__`
ABSENT, `__symbols__` ABSENT, one-entry container, exact M5D boot, M5H
board45 Stock DTB0 vendor.

The marker is a zero-length boolean. It is not a string, integer, or
selector.

## 1. Constraints

```text
MEM0_READ_BEFORE_M5M_A           YES
MEM0_READ_BEFORE_WRITE           YES
LOCAL_BUILD                      NO
LOCAL_VALIDATION                 NO
LOCAL_VALIDATOR                  NO
LOCAL_SOURCE_GATE                NO
LOCAL_ACTIONLINT                 NO
LOCAL_BINARY_VALIDATION          NO
GHA_ONLY                         YES
artifact regeneration            NO
artifact modification            NO
ONLY PARTITION WRITE             dtbo_b
boot_b / vendor_boot_b write     NO
vbmeta* / firmware write         NO
ANY *_a write                    NO
B BOOTS                          1
SECOND_B_BOOT_FORBIDDEN          YES
L1 dtbo restore                  NO
Candidate B auto-execution       NO
file/directory deletion          NO
```

## 2. Authoritative Candidate A (private run 34591653733)

Downloaded, not regenerated. Identity against the private CI report and
`SHA256SUMS`:

```text
A_PAYLOAD_SIZE                   295
A_PAYLOAD_SHA256                 55df159d4915746bf294c3b2a723143d7b65480640828a27f9c658552c061b64
A_ACTIVE_PREFIX_SIZE             359
A_ACTIVE_PREFIX_SHA256           3cba896892e0ccdaccbf5daccaa725c04cb81f9085355e9b13cddb897af1246d
A_STOCK_TAIL_OFFSET              359
A_STOCK_TAIL_SHA256              a7e58eea2808e268af37071df9badaec9f06731e6baf11ba72bb1bd01ab4f984
A_FULL_ARTIFACT_SIZE             33554432
A_FULL_ARTIFACT_SHA256           128bcd312769f34b218b809169317ae456ea10350ed5553067eed7f52035633c
READY_FOR_MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_CONTROL=YES
```

CI-reported payload semantics (not re-parsed locally):

```text
fragment count     1
target             target-path="/"
__fixups__         ABSENT
__symbols__        ABSENT
marker             ABSENT
overlay body       EMPTY
model              exact Stock
qcom,board-id      <45 0>
fdtoverlay         PASS
merged SHA         324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8
                   == exact Stock DTB0
A_SEMANTIC_NOOP_CONFIRMED=YES
MERGED_TREE_BYTE_IDENTICAL_TO_STOCK_DTB0=YES
```

Applying A to Stock DTB0 with standard `fdtoverlay` produces a
byte-identical Stock DTB0. That is not “A payload == Stock DTB0”.

## 3. Start context (post-L1)

```text
ANDROID_A  slot_suffix=_a  boot_completed=1  root=uid=0  device=thyme
PREWRITE boot_b[0,35110912)        4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
PREWRITE vendor_boot_b[0,548864)   2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
PREWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
PREWRITE dtbo_b whole              61dc3b75d66ff4b6411c6f744b19dc999475959709e8cf1f7882b40e827080d8 MATCH (L1)
PREWRITE vbmeta*/firmware          stock / MATCH L1
M5M_A_START_L1_CONTEXT_EXACT       YES
```

Fastboot preflight (real variable names):

```text
product=thyme  unlocked=yes  current-slot=a
snapshot-update-status=none  battery-soc-ok=yes  battery-voltage=4413
slot-retry-count:b=6  slot-unbootable:b=no
```

## 4. Write and post-write identity

Only `dtbo_b` was written, from private run `34591653733`
`m5m-a-full-normalized-dtbo.img`. `current-slot` stayed `a`; reboot was to
Android A, not B.

```text
FLASH  Sending 32768 KB OKAY 0.810s / Writing OKAY 0.129s
POSTWRITE dtbo_b whole             128bcd312769f34b218b809169317ae456ea10350ed5553067eed7f52035633c MATCH
POSTWRITE boot_b                   4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
POSTWRITE vendor_boot_b[0,548864)  2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
POSTWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
POSTWRITE vbmeta*/firmware         byte-identical to pre-write
M5M_A_FULL_CONTEXT_VERIFIED        YES
```

Whole-partition SHA is a valid identity gate because the artifact size equals
physical `dtbo_b` (33554432).

## 5. Runtime — CASE A2

One Slot B boot only. Host observation is Fastboot USB `18d1:d00d`.

```text
set_active b -> current-slot=b  slot-retry-count:b=7  slot-unbootable:b=no
T_REBOOT_CMD_ISO=2026-09-11T11:15:38.301Z
T_DISAPPEAR_ISO=2026-09-11T11:15:38.641Z
T_REAPPEAR_ISO=2026-09-11T11:15:43.475Z
FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR=4.834
PRIMARY_OBSERVATION=4.834s
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=YES
AUTOMATIC_ELAPSED=4.834
MANUAL_RECOVERY=NO
CASE=A2
SECOND_B_BOOT_FORBIDDEN=YES
```

Immediate recovery from automatic Fastboot: `set_active a` then reboot. No
second B boot.

```text
RECOVERY pre   current-slot=b  slot-retry-count:b=6  slot-unbootable:b=no
RECOVERY action set_active a -> current-slot=a -> reboot
ANDROID_A_RESTORED=YES  slot_suffix=_a  boot_completed=1  root=uid=0
```

## 6. Dumps

Read-only, nothing cleared, nothing deleted.

```text
pstore     0 entries both times
minidump   UNCHANGED  e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump    UNCHANGED  254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump    UNCHANGED  3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
logfs      CHANGED    abf3b52d... -> f154f30d...
oops       CHANGED    be148bd1... -> c316638f...

oops content  stock Android 2023-09-04 records only
              21x reboot,bootloader  7x Reason: Restart
              0x Linux version  0x literal 6.6.  0x mainline
OOPS_MAINLINE_EVIDENCE=NO
```

An Android A reboot / bootloader round-trip is not Mainline evidence.

## 7. Interpretation

```text
MARKER_PROPERTY_EFFECT_UNDER_TARGET_PATH=NO
MARKER_REMOVAL_ALONE_SUFFICIENT=NO
MARKER_PRESENT_SUFFICIENT_FOR_4P7S_PATH_UNDER_TARGET_PATH=NO
Final Gate=MAINLINE_V2_M5M_A_MARKER_REMOVAL_NO_EFFECT
```

Held comparison:

```text
L1  T0/M1  target-path="/"  marker PRESENT  4.837s
A   T0/M0  target-path="/"  marker ABSENT   4.834s
L2  T1/M0  target+__fixups__ marker ABSENT  >12s
```

Removing only `qcom,thyme-route-b-noop` under `target-path="/"` does not
leave the ~4.7s wall. Marker presence is not a sufficient factor in this
controlled target-path no-op context.

This does **not** say ABL ignores that property in every context. It says
removal of the empty-boolean overlay property is not sufficient to flip
runtime when targeting remains `target-path="/"`.

A vs L2, both marker-absent, now isolates the remaining major targeting
difference:

```text
A   T0/M0  target-path="/"          4.834s
L2  T1/M0  target + __fixups__      >12s
TARGET_FIXUP_MECHANISM_EFFECT under marker-absent  STRONGLY_SUPPORTED
```

Complete factorial still needs Candidate B (`T1/M1`) as the last cell.
That artifact is already READY (`c5a355b9…`) and is **not** flashed this
round.

## 8. Final B and next

```text
B_FINAL  exact M5D boot
       + M5H board45 single Stock DTB0 vendor_boot
       + M5M-A target-path/no-marker dtbo
L1 dtbo NOT restored
Slot A active and restored
NO_NEXT_STAGE_EXECUTED=YES
WAIT_FOR_USER_APPROVAL=YES

NEXT  MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_TRUE_DEVICE_CONTROL
      full SHA c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
      NOT auto-executed
```
