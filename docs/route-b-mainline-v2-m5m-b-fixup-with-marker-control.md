# Route B Mainline V2 M5M-B — target+fixup with-marker true-device control

Stage id:

```text
MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_TRUE_DEVICE_CONTROL
```

Single source semantic variable versus L2:

```text
MARKER_PROPERTY_PRESENCE_UNDER_TARGET_FIXUP
  L2  qcom,thyme-route-b-noop EMPTY_BOOLEAN length=0  ABSENT
  B   same property                                           PRESENT
```

Held: exact Stock model, fragment count 1, `target=<mdss_mdp>` + `__fixups__`,
target path `/soc/qcom,mdss_mdp@ae00000`, one-entry container, exact M5D boot,
M5H board45 Stock DTB0 vendor.

Factor M is `MARKER_PROPERTY_PRESENT_IN_FRAGMENT_OVERLAY_BODY`, not
`ROOT_MARKER_PRESENT`. L1 marker merges onto `/`; B marker merges onto
`/soc/qcom,mdss_mdp@ae00000`. `MARKER_APPLIED_TO_SAME_BASE_NODE=NO`.

## 1. Constraints

```text
MEM0_READ_BEFORE_M5M_B           YES
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
Candidate A dtbo restore         NO
M5N auto-execution               NO
file/directory deletion          NO
```

## 2. Authoritative Candidate B (private run 34591653733)

Downloaded, not regenerated. Identity against the private CI report and
`SHA256SUMS`:

```text
B_PAYLOAD_SIZE                   391
B_PAYLOAD_SHA256                 5c5b070bf81f55ee68a8bce0c31a625d087aecda89f22e9e69416f89bfca0929
B_ACTIVE_PREFIX_SIZE             455
B_ACTIVE_PREFIX_SHA256           8a3fc0e9f0db7fb21627c983a036d81a664e6924223b6cba53c58236d1968812
B_STOCK_TAIL_OFFSET              455
B_STOCK_TAIL_SHA256              04184621bbba922a3419c1980e0b85750249efd3035ffd35ce5dceced770dbdd
B_FULL_ARTIFACT_SIZE             33554432
B_FULL_ARTIFACT_SHA256           c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
READY_FOR_MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_CONTROL=YES
```

CI-reported payload semantics (not re-parsed locally):

```text
fragment count     1
target             mdss_mdp via __fixups__
target path        /soc/qcom,mdss_mdp@ae00000
__fixups__         PRESENT count=1
marker             PRESENT  qcom,thyme-route-b-noop EMPTY_BOOLEAN length=0
overlay body       marker only
model              exact Stock
qcom,board-id      <45 0>
fdtoverlay         PASS
merged delta       only added /soc/qcom,mdss_mdp@ae00000:qcom,thyme-route-b-noop
B_ONLY_MARKER_SEMANTIC_DELTA=YES
```

## 3. Start context (post-M5M-A)

```text
ANDROID_A  slot_suffix=_a  boot_completed=1  root=uid=0  device=thyme
PREWRITE boot_b[0,35110912)        4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
PREWRITE vendor_boot_b[0,548864)   2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
PREWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
PREWRITE dtbo_b whole              128bcd312769f34b218b809169317ae456ea10350ed5553067eed7f52035633c MATCH (Candidate A)
PREWRITE vbmeta*/firmware          stock / MATCH M5M-A
M5M_B_START_A_CONTEXT_EXACT        YES
```

Fastboot preflight (real variable names):

```text
product=thyme  unlocked=yes  current-slot=a
snapshot-update-status=none  battery-soc-ok=yes  battery-voltage=4414
slot-retry-count:b=6  slot-unbootable:b=no
```

## 4. Write and post-write identity

Only `dtbo_b` was written, from private run `34591653733`
`m5m-b-full-normalized-dtbo.img`. `current-slot` stayed `a`; reboot was to
Android A, not B.

```text
FLASH  Sending 32768 KB OKAY 0.830s / Writing OKAY 0.070s
POSTWRITE dtbo_b whole             c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8 MATCH
POSTWRITE boot_b                   4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
POSTWRITE vendor_boot_b[0,548864)  2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
POSTWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
POSTWRITE vbmeta*/firmware         byte-identical to pre-write
M5M_B_FULL_CONTEXT_VERIFIED        YES
```

Whole-partition SHA is a valid identity gate because the artifact size equals
physical `dtbo_b` (33554432).

## 5. Runtime — CASE B1

One Slot B boot only. Host observation is Fastboot USB `18d1:d00d`.

```text
set_active b -> current-slot=b  slot-retry-count:b=7  slot-unbootable:b=no
T_REBOOT_CMD_ISO=2026-09-11T11:30:44.416Z
T_DISAPPEAR_ISO=2026-09-11T11:30:44.602Z
PRIMARY_OBSERVATION=>12s
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO
MANUAL_RECOVERY=YES
MANUAL_RECOVERY_TIME=685s
MANUAL_RECOVERY_TIME_ISO=2026-09-11T11:42:39Z
CASE=B1
SECOND_B_BOOT_FORBIDDEN=YES
```

`MANUAL_RECOVERY_TIME` is only the human physical-recovery interval. It is
not `T_REAPPEAR`, `NATURAL_RETURN_TIME`, or `AUTOMATIC_RETURN_TIME`.

Recovery from manual Fastboot: `set_active a` then reboot. No second B boot.

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
logfs      CHANGED    56a3ef2d... -> 4b9c11ac...
oops       CHANGED    545e297c... -> b1c1a803...

oops content  stock Android 2023-09-04 records only
              21x reboot,bootloader  7x Reason: Restart
              0x Linux version  0x literal 6.6.  0x mainline
OOPS_MAINLINE_EVIDENCE=NO
```

An Android A reboot / bootloader round-trip is not Mainline evidence.

## 7. Interpretation

```text
MARKER_PROPERTY_EFFECT_UNDER_TARGET_FIXUP=NO
TARGET_FIXUP_MECHANISM_EFFECT_WITH_MARKER_PRESENT=STRONGLY_SUPPORTED
TARGET_FIXUP_MECHANISM_EFFECT=STRONGLY_SUPPORTED
MARKER_PROPERTY_MAIN_EFFECT=NOT_SUPPORTED
TARGETING_MECHANISM_IS_DOMINANT_CAUSAL_FAMILY=STRONGLY_SUPPORTED
TARGET_MARKER_INTERACTION=NOT_SUPPORTED
Final Gate=MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_SUPPRESSES_4P7S
```

Complete 2×2:

```text
T0/M1  L1  target-path="/"      marker PRESENT  4.837s
T0/M0  A   target-path="/"      marker ABSENT   4.834s
T1/M0  L2  target + __fixups__  marker ABSENT   >12s
T1/M1  B   target + __fixups__  marker PRESENT  >12s
```

Runtime groups entirely by Factor T. Marker presence does not change
category under either targeting background.

A vs L2, both marker-absent, already isolated targeting under M0. L1 vs B,
both marker-present, now isolates the same targeting split under M1:

```text
L1  T0/M1  target-path="/"      4.837s
B   T1/M1  target + __fixups__  >12s
```

Standard `fdtoverlay`/libfdt merged-tree content cannot explain the A/L2
runtime split: both merge to byte-identical Stock DTB0
`324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8`.
That is an upper bound on what the standard library merge proves. It does
not say Xiaomi ABL's final merged tree is the same, that ABL inspects the
overlay before merge, or that ABL does not use the final DTB.

The supported causal family is:

```text
raw overlay representation /
targeting-fixup encoding /
ABL-specific overlay processing path
```

Do not claim a specific ABL source-code behaviour.

Do not continue marker research. `/model`, padding, container, and board-id
remain deprioritised.

## 8. Final B and next

```text
B_FINAL  exact M5D boot
       + M5H board45 single Stock DTB0 vendor_boot
       + M5M-B target+fixup/with-marker dtbo
Candidate A dtbo NOT restored
Slot A active and restored
NO_NEXT_STAGE_EXECUTED=YES
WAIT_FOR_USER_APPROVAL=YES

NEXT  MAINLINE_V2_M5N_TARGETING_MECHANISM_ISOLATION_CI
      split the target/fixup family:
        target-path property
        target phandle encoding
        __fixups__ node presence
        external symbol string
        placeholder 0xffffffff
        target symbol choice
      find the minimal ABL-compatible targeting representation
      NOT auto-executed
```
