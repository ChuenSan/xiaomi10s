# Route B Mainline V2 M5L-L2 — Stock-style minimal no-op true-device control

Stage id:

```text
MAINLINE_V2_M5L_L2_STOCK_STYLE_MINIMAL_NOOP_TRUE_DEVICE_CONTROL
```

## 0. Pre-outcome order revision (recorded before any L1/L2 device result)

M5L CI originally pre-registered:

```text
P1 selector difference exists and L1 READY  -> L1 first
```

That rule was written before the audit finished measuring the P1 family.
After private run `34585043442` the measured P1 difference is only `/model`
text. Strict ABL selector metadata (`qcom,board-id` / `compatible` / msm-id /
pmic-id family) is already identical between Stock entry21 and the M1 no-op.

L2 simultaneously provides:

- Stock root identity and selector values
- Stock-style `target=<&mdss_mdp>` + `__fixups__`
- truly empty `__overlay__`
- merged tree byte-for-byte equal to exact Stock DTB0

so L2-first has higher information gain than a `/model`-only L1 control.
This reorder is a design change made **before** any L1 or L2 true-device
outcome was observed. It is not a post-hoc choice of experiment.

```text
M5L_TRUE_DEVICE_ORDER_REVISED_PRE_OUTCOME=YES
ORIGINAL_PREREGISTRATION=L1 first
REVISED_TRUE_DEVICE_ORDER=L2 first
L1_AUTO_EXEC=NO
M5M_AUTO_EXEC=NO
```

If L2 `>12s`, a later approved round may run L1 to separate `/model` from
the target/fixup/marker family. If L2 is `~4.7s`, L1 is deprioritised and
the next CI stage is Stock overlay minimisation (M5M). Neither is executed
here.

## 1. Constraints

```text
MEM0_READ_BEFORE_M5L_L2          YES
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
older dtbo restore               NO
file/directory deletion          NO
L1 auto-execution                NO
M5M auto-execution               NO
```

## 2. M5K reference (held constant except dtbo payload)

```text
boot     exact M5D
vendor   M5H board45 single Stock DTB0
dtbo     M5K one-entry + exact Stock thyme entry21
runtime  PRIMARY_OBSERVATION=>12s
         AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO
         MANUAL_RECOVERY=YES
Final    MAINLINE_V2_M5K_ONE_ENTRY_STOCK_PAYLOAD_SUPPRESSES_4P7S
M1_ONE_ENTRY_CONTAINER_ALONE_SUFFICIENT=NO
```

This round keeps the same one-entry container and changes only the selected
payload.

## 3. Authoritative L2 artifact (private run 34585043442)

Downloaded, not regenerated. Identity against the private CI report and
`SHA256SUMS`:

```text
L2_PAYLOAD_SIZE                  355
L2_PAYLOAD_SHA256                408e5709d8f772c0759a4d8ef427b49329a41f38a98776571ac7252d1b841740
L2_ACTIVE_PREFIX_SIZE            419
L2_ACTIVE_PREFIX_SHA256          7822d64e8e399b6ad265800a3addd8c0e79cd9153475e540b21c0106c91c4c15
L2_STOCK_TAIL_OFFSET             419
L2_STOCK_TAIL_SHA256             02b0fc3a443a9ff9bb19eca0683015ab8b1cb67b7a90a46947eb84e4d287c247
L2_FULL_ARTIFACT_SIZE            33554432
L2_FULL_ARTIFACT_SHA256          0c66c6097dabaddbe58613a15199c97b06b0d0d706f18d200185f300666854ff
L2_FULL_SIZE_EQUALS_DTBO_B       YES
```

CI-reported one-entry structure (not re-parsed locally):

```text
magic            0xd7b7ab1e
version          0
header_size      32
entry_size       32
entry_count      1
entries_offset   32
page_size        4096
id/rev/custom    all zero
payload offset   64
payload size     355
total_size       419
target           mdss_mdp  (Stock fragment@71)
target path      /soc/qcom,mdss_mdp@ae00000
__overlay__      EMPTY
marker           NONE
root identity    exact Stock
```

Semantic no-op on exact Stock DTB0 (CI):

```text
STOCK_DTB0_SHA256     324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8
L2_MERGED_SHA256      324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8
byte-for-byte equal   YES
L2_SEMANTIC_NOOP_CONFIRMED=YES
L2_READY=YES
```

## 4. Direct comparison

```text
REFERENCE M5K  one-entry + Stock 124-fragment entry21     -> >12s
TEST L2        same one-entry + Stock-style 1-fragment
               semantic no-op                             -> measured below
```

The container is not the variable. The question is whether a much smaller
ABL-acceptable Stock-style semantic no-op can reproduce M5K's `>12s` class.

## 5. Start context

```text
ANDROID_A  slot_suffix=_a  boot_completed=1  root=uid=0  device=thyme
PREWRITE boot_b[0,35110912)       4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
PREWRITE vendor_boot_b[0,548864)  2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
PREWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
PREWRITE dtbo_b whole             045fa86dadec5be129554a33289c2d9937df9f0a853473a9a3ffd44a4f22c989 MATCH (M5K)
PREWRITE vbmeta*/firmware         stock / MATCH M5H
M5L_L2_START_M5K_CONTEXT_EXACT    YES
```

Fastboot preflight (real variable names):

```text
product=thyme  unlocked=yes  current-slot=a
snapshot-update-status=none  battery-soc-ok=yes
slot-retry-count:b=6  slot-unbootable:b=no
```

## 6. Write and post-write identity

Only `dtbo_b` was written, from private run `34585043442`
`m5l-l2-full-normalized-dtbo.img`. `current-slot` stayed `a`; reboot was to
Android A, not B.

```text
FLASH  Sending 32768 KB OKAY 0.797s / Writing OKAY 0.108s
POSTWRITE dtbo_b whole            0c66c6097dabaddbe58613a15199c97b06b0d0d706f18d200185f300666854ff MATCH
POSTWRITE boot_b                  4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63 MATCH
POSTWRITE vendor_boot_b[0,548864) 2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
POSTWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
POSTWRITE vbmeta*/firmware        byte-identical to pre-write
M5L_L2_FULL_CONTEXT_VERIFIED      YES
```

Whole-partition SHA is a valid identity gate because the artifact size equals
physical `dtbo_b` (33554432).

## 7. Runtime — CASE L2-A

One Slot B boot only.

```text
set_active b -> current-slot=b  slot-retry-count:b=7  slot-unbootable:b=no
T_REBOOT_CMD_ISO=2026-09-11T10:07:05.189Z
T_DISAPPEAR_ISO=2026-09-11T10:07:05.537Z
PRIMARY_OBSERVATION=>12s
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO
AUTOMATIC_ELAPSED=N/A
CASE=L2-A
SECOND_B_BOOT_FORBIDDEN=YES
```

Manual physical Fastboot recovery; elapsed time is recovery-operation time
only, not an automatic return.

```text
MANUAL_RECOVERY=YES
MANUAL_RECOVERY_TIME=45s
MANUAL_RECOVERY_TIME_ISO=2026-09-11T10:08:26Z
RECOVERY pre   current-slot=b  slot-retry-count:b=6  slot-unbootable:b=no
RECOVERY action set_active a -> current-slot=a -> reboot
ANDROID_A_RESTORED=YES  slot_suffix=_a  boot_completed=1  root=uid=0
```

`T_REAPPEAR` / `NATURAL_RETURN_TIME` are not recorded.

## 8. Dumps

Read-only, nothing cleared, nothing deleted.

```text
pstore     0 entries both times
minidump   UNCHANGED  e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
rawdump    UNCHANGED  254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump    UNCHANGED  3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
logfs      CHANGED    659b83e4... -> e2736b6a...
oops       CHANGED    447202d5... -> 070fc8c8...

oops content  stock Android 2023-09-04 records only
              21x reboot,bootloader  7x Reason: Restart
              0x Linux version  0x literal 6.6.  0x mainline
OOPS_MAINLINE_EVIDENCE=NO
```

An Android A reboot / bootloader round-trip is not Mainline evidence.

## 9. Interpretation

```text
L2_MINIMAL_NOOP_EFFECT=YES
STOCK_STYLE_MINIMAL_NOOP_COMPATIBLE=STRONGLY_SUPPORTED
Final Gate=MAINLINE_V2_M5L_L2_MINIMAL_NOOP_SUPPRESSES_4P7S
```

Contrast:

```text
M1 no-op   target-path="/"  no fixups  marker     ~4.8-4.9s
L2         Stock-style target+fixup  empty overlay
           Stock root identity                      >12s
M5K        same one-entry + Stock 124-fragment      >12s
```

A much smaller ABL-acceptable Stock-style semantic no-op exists and does not
trip the current ~4.7s wall. This round also changed `/model`, target
mechanism, fixup metadata and marker removal together, so `target-path="/"`
is **not** proven as the single root cause.

## 10. Final B and next

```text
B_FINAL  exact M5D boot
       + M5H board45 single Stock DTB0 vendor_boot
       + L2 Stock-style minimal-noop dtbo
M5K dtbo NOT restored
Slot A active and restored
NO_NEXT_STAGE_EXECUTED=YES
WAIT_FOR_USER_APPROVAL=YES

NEXT  L1_SELECTOR_MATCHED_NOOP_TRUE_DEVICE
      (only after approval; not executed here)
      L1 >12s -> ROOT_MODEL_TEXT_EFFECT=STRONGLY_SUPPORTED
      L1 ~4.7s -> /model alone insufficient;
                  Stock-style target/fixup and/or marker-removal family
M5M not indicated while L2 is >12s
```
