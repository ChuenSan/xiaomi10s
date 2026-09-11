# Route B Mainline V2 M5L-L1 — ROOT_MODEL_TEXT true-device control

Stage id:

```text
MAINLINE_V2_M5L_L1_SELECTOR_MATCHED_NOOP_TRUE_DEVICE_CONTROL
```

Historical artifact name `L1_SELECTOR_MATCHED_NOOP` is retained. The causal
variable measured this round is **`ROOT_MODEL_TEXT`**, not strict ABL selector
metadata (`board-id` / `msm-id` / `pmic-id` / `platform-id` / `compatible`).
M5L CI already showed that family is identical.

## 1. Constraints

```text
MEM0_READ_BEFORE_M5L_L1          YES
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
L2 dtbo restore                  NO
file/directory deletion          NO
M5M auto-execution               NO
```

## 2. Why L1 after L2

L2 (`>12s`) proved a Stock-style minimal no-op family can leave the ~4.7s
wall. L2 also changed `/model`, target mechanism, `__fixups__`, and marker
together, so it cannot isolate `ROOT_MODEL_TEXT`.

L1 holds the M1 no-op mechanism constant and changes only `/model` to the
exact Stock entry21 string.

```text
REFERENCE M1 no-op   /model=M1     target-path="/"  marker present   ~4.8-4.9s
TEST L1              /model=Stock  same target-path  same marker      measured below
```

## 3. Authoritative L1 artifact (private run 34585043442)

Downloaded, not regenerated. Identity against the private CI report and
`SHA256SUMS`:

```text
L1_PAYLOAD_SIZE                  331
L1_PAYLOAD_SHA256                64344d59119b253d47b950385fbed1c8dd38bf28003604c2deb7dcf1f1777ca4
L1_ACTIVE_PREFIX_SIZE            395
L1_ACTIVE_PREFIX_SHA256          36f6adbab104053acc1e501f0aae3bf3452f9968cda3c09aec85e6253adfa81b
L1_STOCK_TAIL_OFFSET             395
L1_STOCK_TAIL_SHA256             62c06a96d36bac3084a2b3bf30805095158ba5f437a413f5a2374269ff3cc812
L1_FULL_ARTIFACT_SIZE            33554432
L1_FULL_ARTIFACT_SHA256          61dc3b75d66ff4b6411c6f744b19dc999475959709e8cf1f7882b40e827080d8
L1_FULL_SIZE_EQUALS_DTBO_B       YES
```

CI-reported payload semantics (not re-parsed locally):

```text
fragment count     1
target             target-path="/"
__fixups__         ABSENT
__symbols__        ABSENT
marker             qcom,thyme-route-b-noop PRESENT
compatible         SAME (qcom,kona-mtp / qcom,kona / qcom,mtp)
qcom,board-id      <45 0>
model              "Qualcomm Technologies, Inc. xiaomi thyme"  (exact Stock entry21)
overlay body       marker-only, same as M1 no-op
L1_READY           YES
```

The only source/payload semantic change versus the historical M1 no-op is
`ROOT_MODEL_TEXT`.

## 4. Start context (post-L2)

```text
ANDROID_A  slot_suffix=_a  boot_completed=1  root=uid=0  device=thyme
PREWRITE boot_b[0,35110912)        4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
PREWRITE vendor_boot_b[0,548864)   2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
PREWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
PREWRITE dtbo_b whole              0c66c6097dabaddbe58613a15199c97b06b0d0d706f18d200185f300666854ff MATCH (L2)
PREWRITE vbmeta*/firmware          stock / MATCH L2
M5L_L1_START_L2_CONTEXT_EXACT      YES
```

Fastboot preflight (real variable names):

```text
product=thyme  unlocked=yes  current-slot=a
snapshot-update-status=none  battery-soc-ok=yes
slot-retry-count:b=6  slot-unbootable:b=no
```

## 5. Write and post-write identity

Only `dtbo_b` was written, from private run `34585043442`
`m5l-l1-full-normalized-dtbo.img`. `current-slot` stayed `a`; reboot was to
Android A, not B.

```text
FLASH  Sending 32768 KB OKAY 0.819s / Writing OKAY 0.066s
POSTWRITE dtbo_b whole             61dc3b75d66ff4b6411c6f744b19dc999475959709e8cf1f7882b40e827080d8 MATCH
POSTWRITE boot_b                   4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
POSTWRITE vendor_boot_b[0,548864)  2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
POSTWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
POSTWRITE vbmeta*/firmware         byte-identical to pre-write
M5L_L1_FULL_CONTEXT_VERIFIED       YES
```

Whole-partition SHA is a valid identity gate because the artifact size equals
physical `dtbo_b` (33554432).

## 6. Runtime — CASE L1-B

One Slot B boot only.

```text
set_active b -> current-slot=b  slot-retry-count:b=7  slot-unbootable:b=no
T_REBOOT_CMD_ISO=2026-09-11T10:22:59.607Z
T_DISAPPEAR_ISO=2026-09-11T10:22:59.948Z
T_REAPPEAR_ISO=2026-09-11T10:23:04.784Z
FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR=4.837
PRIMARY_OBSERVATION=4.837s
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=YES
AUTOMATIC_ELAPSED=4.837
MANUAL_RECOVERY=NO
CASE=L1-B
SECOND_B_BOOT_FORBIDDEN=YES
```

Immediate recovery from automatic Fastboot: `set_active a` then reboot. No
second B boot.

```text
RECOVERY pre   current-slot=b  slot-retry-count:b=6  slot-unbootable:b=no
RECOVERY action set_active a -> current-slot=a -> reboot
ANDROID_A_RESTORED=YES  slot_suffix=_a  boot_completed=1  root=uid=0
```

## 7. Dumps

Read-only, nothing cleared, nothing deleted.

```text
pstore     0 entries both times
minidump   UNCHANGED  e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump    UNCHANGED  254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump    UNCHANGED  3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
logfs      CHANGED    a01bc555... -> 6f24430b...
oops       CHANGED    f3db5796... -> 28a15ade...

oops content  stock Android 2023-09-04 records only
              21x reboot,bootloader  7x Reason: Restart
              0x Linux version  0x literal 6.6.  0x mainline
OOPS_MAINLINE_EVIDENCE=NO
```

An Android A reboot / bootloader round-trip is not Mainline evidence.

## 8. Interpretation

```text
ROOT_MODEL_TEXT_EFFECT=NO
STOCK_MODEL_TEXT_ALONE_SUFFICIENT=NO
Final Gate=MAINLINE_V2_M5L_L1_STOCK_MODEL_NO_EFFECT
```

Held comparison:

```text
M1 no-op   /model=M1     target-path="/"  marker present        ~4.8-4.9s
L1         /model=Stock  target-path="/"  marker present        4.837s
L2         /model=Stock  target+__fixups__  marker absent       >12s
```

Changing only `ROOT_MODEL_TEXT` to the exact Stock string does not leave the
~4.7s wall. `/model` is deprioritised as a stand-alone cause in this
one-entry / `target-path="/"` / marker-present no-op context.

This does **not** say ABL ignores `/model` in every context. It says the
string is not a sufficient ABL-visible flip given the other M1 no-op
semantics held here.

Remaining variables, with Stock model now held:

```text
T  target-path="/"     vs  Stock-style target+__fixups__
M  marker present      vs  marker absent
```

Already measured:

```text
T=target-path     M=present   = L1   ~4.837s
T=target+fixup    M=absent    = L2   >12s
```

Missing cells are CI-only until approved:

```text
T=target-path     M=absent
T=target+fixup    M=present
```

Do not scan other root fields. Do not claim `target-path="/"` or marker
alone until those cells exist.

## 9. Final B and next

```text
B_FINAL  exact M5D boot
       + M5H board45 single Stock DTB0 vendor_boot
       + L1 ROOT_MODEL_TEXT no-op dtbo
L2 dtbo NOT restored
Slot A active and restored
NO_NEXT_STAGE_EXECUTED=YES
WAIT_FOR_USER_APPROVAL=YES

NEXT  MAINLINE_V2_M5M_TARGET_FIXUP_MARKER_FACTORIAL_CI
      (construct the two missing 2x2 cells READY; do not flash this round)
```
