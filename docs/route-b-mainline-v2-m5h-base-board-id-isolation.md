# Route B Mainline V2 M5H — base board-id isolation

Status: CI artifact ready. Final gate:
`READY_FOR_MAINLINE_V2_M5H_BASE_BOARD_ID_CONTROL`.
No device operation. Slot B unchanged. True-device control not executed,
pending explicit approval.

## Question

M5G-V established the family-level result:

```text
Cell B   single-DTB topology + Mainline thyme DTB + Stock dtbo -> 5.008s
M5G-V    single-DTB topology + exact Stock DTB0    + Stock dtbo -> no 4.7s return in 12s
```

`sudden topology change` is not the cause; the vendor DTB payload / metadata /
base-overlay compatibility group carries the causal support. M5G-V swapped the
whole payload and `dtb_size` moved with it, so no single field was attributed.

M5H isolates exactly one field, with everything else byte-identical.

## Design of the single variable

```text
Stock protocol                        M1 protocol
base generic      qcom,board-id <0 0>   base           qcom,board-id <45 0>
overlay selects   qcom,board-id <45 0>  overlay        qcom,board-id <45 0>
```

M5H starts from the exact M5G-V artifact — already validated on device as
suppressing the 4.7s return — and changes only `qcom,board-id` in the base DTB
from `<0 0>` to `<45 0>`.

```text
intentional variable : BASE_QCOM_BOARD_ID
topology             : single DTB            (unchanged)
DTB payload family   : exact Stock DTB0      (unchanged)
DTBO                 : exact Stock           (unchanged, not part of this artifact)
```

## Constraints

```text
MEM0_READ_BEFORE_M5H=YES
LOCAL_BUILD=NO
LOCAL_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
GHA_ONLY=YES
DEVICE_OPERATION=NO
ADB_DEVICE_CHANGE=NO
FASTBOOT=NO
FLASH=NO
SLOT_SWITCH=NO
B_BOOT=NO
SLOT_A_WRITE=FORBIDDEN
OLD_CONTEXT_RESTORE=NO
OEM_DERIVED_ARTIFACT=PRIVATE_ONLY
```

All DT parsing, binary transformation, binary diff, and `fdtoverlay` audit ran
only in GitHub Actions. Local work was limited to artifact identity
confirmation (size and SHA256).

## Source identity

Authoritative source is the artifact that produced the recorded `>12s` device
behavior, re-downloaded, not regenerated, not modified.

```text
private run     34559797694
workflow        thyme-mainline-v2-m5g-private
artifact        m5g-v-single-stock-dtb-vendor_boot.img
size            548864
SHA256          e49e12ad71839bc959237eb8ef6ad6ba7f2f38dffedcf31f3fe36b0845402e83
DTB payload     exact Stock DTB0, SHA256 324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8
vendor ramdisk  UNCHANGED, 2238 bytes, 137c4897aa7adf416706a1668edac96c66fbbf1d232735b1cb7a74f399a14639
```

Independent inputs, all pinned by exact size and SHA256 before use:

```text
Stock vendor_boot.img   aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972  (100663296)
Stock dtbo.img          018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634  (33554432)
M1 vendor_boot          29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5  (114688)
M1 Mainline base DTB    cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0  (106026)
Stock DTBO entry 21     44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93  (484885)
```

## Location of the field

The offset was derived by an FDT parser inside the CI, never hard-coded, and
cross-checked against an independent implementation (`libfdt` / `fdtget`).

```text
BOARD_ID_NODE_PATH=/ 
BOARD_ID_PROPERTY_NAME=qcom,board-id
BOARD_ID_PROPERTY_LENGTH=8
BOARD_ID_PROPERTY_OFFSET_DTB_RELATIVE=224
DTB0_ABSOLUTE_OFFSET_IN_VENDOR_BOOT=8192
BOARD_ID_PROPERTY_OFFSET_IN_VENDOR_BOOT=8416
BOARD_ID_DATA_RANGE_IN_VENDOR_BOOT=[8416,8424)
BEFORE_HEX=0000000000000000
AFTER_HEX=0000002d00000000
```

Only the property value bytes were written. There was no `fdtput`, no
re-serialization, no strings-block or structure-block reshuffle.

## Binary delta

```text
DTB_DIFF_BYTE_COUNT=1
DTB_DIFF_OFFSETS=227
DTB_DIFF_OUTSIDE_BOARD_ID=0
VENDOR_BOOT_DIFF_BYTE_COUNT=1
VENDOR_BOOT_DIFF_OFFSETS=8419
```

Single byte, `0x00 -> 0x2d`, at DTB-relative 227 / vendor_boot 8419 — the
fourth byte of the `qcom,board-id` property value, i.e. big-endian cell 0
becomes `45`. The diff is entirely inside the `qcom,board-id` property data
range, as required.

## Candidate identity

```text
private run     34567840377
workflow        thyme-mainline-v2-m5h-private
artifact        m5h-v-stock-dtb0-board45-vendor_boot.img
size            548864                      UNCHANGED vs source
SHA256          2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9
DTB0 SHA after  b5620dc2496f2c0866adabe59fe79ca3ac23863c033b30b2b6dfa1b248e20116
```

The artifact is deterministic: an earlier run of the same source (which failed
only on the review script's own validation slice, never on the artifact) emitted
the identical SHA256.

```text
M5H vendor_boot = M5G-V vendor_boot + board-id value bytes only
```

## Gates

```text
M5G_V_SOURCE_SHA_EXACT=PASS
STOCK_DTB0_SHA_EXACT=PASS
BOARD_ID_PROPERTY_FOUND=PASS
BOARD_ID_BEFORE_0_0=PASS
BOARD_ID_PATCHED_45_0=PASS
BOARD_ID_PROPERTY_LENGTH_UNCHANGED=PASS
DTB_TOTALSIZE_UNCHANGED=PASS
DTB_SEMANTIC_ONLY_BOARD_ID=PASS
DTB_DIFF_BOARD_ID_ONLY=PASS
VENDOR_BOOT_HEADER_UNCHANGED=PASS
VENDOR_RAMDISK_UNCHANGED=PASS
DTB_SIZE_UNCHANGED=PASS
DTB_OFFSET_UNCHANGED=PASS
ARTIFACT_SIZE_UNCHANGED=PASS
ARTIFACT_EXTENT_UNCHANGED=PASS
VENDOR_BOOT_DIFF_BOARD_ID_ONLY=PASS
REVERSE_PARSE=PASS
DTC_BEFORE_VALID=PASS
LIBFDT_BOARD_ID_BEFORE=PASS
LIBFDT_BOARD_ID_AFTER=PASS
MSM_ID_UNCHANGED=PASS
COMPATIBLE_UNCHANGED=PASS
PRIVATE_ARTIFACT_ONLY=PASS
FAIL_CLOSED=PASS
READY_FOR_MAINLINE_V2_M5H_BASE_BOARD_ID_CONTROL=YES
```

Payload semantics preserved and re-read from the patched image:

```text
qcom,msm-id   <0x164 0x20001> (356 131073)   required value, unchanged
qcom,board-id <0x2d 0x0> (45 0)              patched
compatible    qcom,kona                      unchanged
totalsize     540195                         unchanged
/  memory  chosen  reserved-memory  __symbols__  node tree   unchanged
```

`REVERSE_PARSE` is not a re-serialization check. It re-parses the written image
and asserts the whole node/property tree is identical to the source except
`qcom,board-id`, together with an `fdtget` cross-read of `0 0 -> 2d 0` from the
independent `libfdt` implementation.

## Classification

This round is artifact preparation only. It establishes that a pure
`BASE_QCOM_BOARD_ID` control artifact exists, is minimal, and is byte-auditable.
It does not establish any runtime effect.

```text
BASE_BOARD_ID_PLACEMENT_EFFECT=UNTESTED
M1_BASE_BOARD_ID_45_SUFFICIENT=UNTESTED
DEVICE_OPERATION=NONE
```

## Companion read-only diagnostic — Stock overlay on Mainline base

Run in the same private CI as a separate, auxiliary, non-blocking record. It is
a reference-implementation result, not Xiaomi ABL, and it is not a true-device
causal gate. It cannot block, and did not block, the board-id artifact.

```text
IMPLEMENTATION=fdtoverlay/libfdt
STOCK_BASE_PLUS_STOCK_OVERLAY_FDTOVERLAY=PASS
STOCK_BASE_PLUS_STOCK_OVERLAY_RC=0
STOCK_BASE_PLUS_STOCK_OVERLAY_MERGED_SHA256=c48ef53de0dc3ad3ca31818b913b7380f615bbed8df925416abbae8ef0a8535b
STOCK_BASE_PLUS_STOCK_OVERLAY_ERROR=NONE

M1_BASE_PLUS_STOCK_OVERLAY_FDTOVERLAY=FAIL
M1_BASE_PLUS_STOCK_OVERLAY_RC=1
M1_BASE_PLUS_STOCK_OVERLAY_ERROR=Failed to apply '.../m1-base-stock-entry21.overlay.dtbo': FDT_ERR_NOTFOUND
```

Fixup matrix, exact, over the whole 154-symbol set:

```text
STOCK_DTB0_SYMBOL_COUNT=1672
MAINLINE_BASE_HAS_SYMBOLS=NO
MAINLINE_BASE_SYMBOL_COUNT=0
STOCK_OVERLAY_FIXUP_COUNT=154
FIXUP_PRESENT_BOTH=0
FIXUP_DIFFERENT_TARGET=0
FIXUP_UNRESOLVED=0
MISSING_MAINLINE_FIXUP_SYMBOLS=154
TARGET_CONFIDENCE_HIGH=1
TARGET_CONFIDENCE_MEDIUM=14
TARGET_CONFIDENCE_LOW=35
TARGET_CONFIDENCE_NONE=104
```

`FIXUP_UNRESOLVED=0` is consistent with the positive control: all 154 symbols do
exist in the Stock base. The Mainline base exposes an empty `__symbols__`, so
every overlay fixup is unresolvable there.

### overlay-fixup-compatibility appendix

Target-node heuristic (symbol name and identifier match only; not a semantic
compatibility proof):

```text
firmware   /firmware                          /firmware          HIGH
soc        /soc                               /soc@0             MEDIUM
intc       /soc/interrupt-controller@17a00000 (basename only)    MEDIUM
pdc        /soc/interrupt-controller@b220000  (basename only)    MEDIUM
tlmm       /soc/pinctrl@f000000               (basename only)    MEDIUM
ufshc_mem  /soc/ufshc@1d84000                 (basename only)    MEDIUM
kona_snd   /soc/qcom,msm-audio-apr/.../sound  (basename only)    MEDIUM
qupv3_se*  /soc/i2c@*  /soc/spi@*             (basename only)    MEDIUM
thermal_zones /soc/thermal-zones              (basename only)    MEDIUM
```

Only one symbol (`firmware`) targets a path that exists verbatim in the Mainline
DTB. The 14 MEDIUM rows are basename-level matches and most are a different node
naming scheme, e.g. Stock `/soc` versus Mainline `/soc@0`. The remaining 139
(`LOW` 35, `NONE` 104) have no clear counterpart by name.

Conclusions are held at the evidence level:

```text
MAINLINE_BASE_LACKS_ALL_STOCK_OVERLAY_FIXUP_SYMBOLS=YES
MAINLINE_BASE_NODE_NAMING_DIFFERS_FROM_STOCK_SCHEME=STRONGLY_SUPPORTED
SYMBOL_NAME_PRESENCE_IS_NOT_TARGET_SEMANTIC_COMPATIBILITY=YES
```

Backfilling all 154 symbols into the Mainline DTB was explicitly not attempted
this round: a symbol name is not evidence that the underlying target node is
semantically compatible.

## Future true-device control

Any device operation requires separate approval. When approved, the only
required write is one `vendor_boot_b` from this artifact, onto the current Slot B
which already holds the M5G-V candidate and exact Stock `dtbo`.

```text
Reference M5G-V   base board-id <0 0>   same single topology, same Stock DTB0, same Stock dtbo -> >12s
M5H               base board-id <45 0>  everything else identical                              -> ???
```

The only runtime variable is `BASE_QCOM_BOARD_ID`.

```text
~4.3-5.3s automatic Fastboot return  -> MAINLINE_V2_M5H_BASE_BOARD_ID_RESTORES_4P7S
>12s, no automatic return            -> MAINLINE_V2_M5H_BASE_BOARD_ID_NO_EFFECT
5.3-12s                              -> INCONCLUSIVE
```

Case H1 — if `<45 0>` restores the ~4.7s return:

```text
BASE_BOARD_ID_PLACEMENT_EFFECT=YES
M1_BASE_BOARD_ID_45_SUFFICIENT=STRONGLY_SUPPORTED
```

The permitted statement is then: with the current exact Stock DTBO background,
changing only the base board-id from `<0 0>` to `<45 0>` flips the runtime
behavior. The permitted statement is *not* "ABL requires base board-id 0" —
selection and merge internals remain unobserved.

The first vendor-track compatibility fix would then be: bring the Mainline base
DTB `qcom,board-id` back to the Stock-style generic `<0 0>`, and continue with
the remaining payload differences. The M1 `dtbo` problem still needs its own
resolution, since Cell C proved M1 `dtbo` is independently sufficient.

Case H2 — if it stays suppressed:

```text
BASE_BOARD_ID_PLACEMENT_EFFECT=NO
M1_BASE_BOARD_ID_45_ALONE_SUFFICIENT=NO
```

Then the next priority is decided by the appendix above rather than by field
scanning: because the Mainline base resolves none of the 154 overlay fixups
(`FDT_ERR_NOTFOUND`), a
`M5I_MAINLINE_BASE_OVERLAY_COMPATIBILITY_CI` pass is better justified than a
blind `compatible` sweep. If the overlay audit had passed, root
metadata isolation would be the next variable. `/memory` is explicitly not the
next target.

The DTBO track stays frozen this round; `D_CONTROL` is not run.

## Doc and CI record

```text
public source commit     5c8329bfd166173bdd608c37661e2ee79818544d
private wrapper commit   6ba7562ced0721415712853bcfdbbca8f928e9e3
public source audit     34567640406   PASS
private M5H run         34567840377   PASS
OEM_DERIVED_ARTIFACT=PRIVATE_ONLY
DEVICE_OPERATION=NO
```

## Next, not executed

```text
NEXT=MAINLINE_V2_M5H_BASE_BOARD_ID_TRUE_DEVICE_CONTROL
required: user approval, then one vendor_boot_b write
Slot A untouched, no slot switch, no second B boot, no old context restore
WAIT_FOR_USER_APPROVAL=YES
NO NEXT STAGE EXECUTED=YES
```
