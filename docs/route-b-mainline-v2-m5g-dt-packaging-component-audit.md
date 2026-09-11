# Route B Mainline V2 M5G — DT packaging component audit

## Scope and safety

M5G decomposes both independently sufficient M1 DT-context components into structure versus payload/selector variables. It does not modify Linux `Image` or authorize a device test.

```text
MEM0_READ_BEFORE_M5G=YES
LOCAL_BUILD=NO
LOCAL_BUILD_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
ARTIFACT_TRANSFORMATION=PRIVATE_GHA_ONLY
FORMAL_DT_VALIDATION=PRIVATE_GHA_ONLY
BINARY_DIFF=PRIVATE_GHA_ONLY
DEVICE_OPERATION=NO
ADB_DEVICE_CHANGE=NO
FASTBOOT=NO
FLASH=NO
SLOT_SWITCH=NO
B_BOOT=NO
SLOT_A_WRITTEN=NO
```

Slot B remains exact M5D `boot_b` + M1 `vendor_boot_b` + Stock `dtbo_b`.

Authoritative private GHA run: [`34559797694`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34559797694), success. Public source audit run [`34559781480`](https://github.com/ChuenSan/xiaomi10s/actions/runs/34559781480) also passed. No local validator or binary inspection produced these results.

## Authoritative 2×2 matrix

Exact M5D boot SHA256:

```text
4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
```

| Cell | vendor_boot | dtbo | Runtime |
|---|---|---|---:|
| A | Stock | Stock | >12s |
| B | M1 | Stock | 5.008s |
| C | Stock | M1 | 4.812s |
| D | M1 | M1 | 4.532s |

```text
M1_VENDOR_BOOT_SUFFICIENT_ON_STOCK_DTBO=STRONGLY_SUPPORTED
M1_DTBO_SUFFICIENT_ON_STOCK_VENDOR_BOOT=STRONGLY_SUPPORTED
```

The matrix proves component-level sufficiency, not that the Mainline DTB, single-DTB topology, base `board-id`, no-op overlay, one-entry DTBO table, any ABL function, or kernel entry is the cause. Both components are consumed by ABL before handoff; independent selection/merge/package incompatibilities can therefore converge on the same observable bootloader fallback timer. Similar ~4.7s timing does not prove the same internal failure.

## Exact inputs

| Input | Size | SHA256 |
|---|---:|---|
| Stock `vendor_boot.img` | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| M1 `vendor_boot` artifact | 114688 | `29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5` |
| Stock `dtbo.img` | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |
| M1 `dtbo` artifact | 387 | `316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1` |

M1 artifact identity ends at 114688/387 bytes. Any device remainder is historical Stock partition tail and is not part of either M1 artifact.

## Vendor_boot audit

Both images are vendor_boot v3 with header size 2112, page size 4096, vendor ramdisk offset 4096, DTB offset 8192, and DTB load address `0x1f00000`. The vendor ramdisk is byte-identical: 2238 bytes, SHA256 `137c4897aa7adf416706a1668edac96c66fbbf1d232735b1cb7a74f399a14639`.

| Field | Stock | M1 |
|---|---:|---:|
| File size | 100663296 | 114688 |
| DTB area size | 1613832 | 106026 |
| Parsed FDT count | 4 | 1 |
| Padded image extent | 1626112 | 114688 |

### Exact Stock concatenation

Offsets below are relative to the DTB area; absolute image offset is relative + 8192.

| Index | Offset | Size | Model | msm-id | board-id | SHA256 |
|---:|---:|---:|---|---|---|---|
| 0 | 0 | 540195 | kona v2.1 SoC | `<356 0x20001>` | `<0 0>` | `324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8` |
| 1 | 540195 | 540191 | kona v2 SoC | `<356 0x20000>` | `<0 0>` | `0bd93f077080a6e3bedff5cf384ff97fc863667c59e3379cbbe5bbc165c4168e` |
| 2 | 1080386 | 533273 | kona v1 SoC | `<356 0x10000>` | `<0 0>` | `afc3540645e5a11351532ce2b5384f27acfb412ee0780ff5a57d72301d5ddb52` |
| 3 | 1613659 | 173 | empty stub | none | none | `dbf5e0605a0c053d08260f19bce216935327ab3df7bdf951bf5d736653fb5651` |

The three real bases all use `compatible = "qcom,kona"`, `/memory reg = <0 0 0 0>`, and `/chosen bootargs = "rcupdate.rcu_expedited=1 rcu_nocbs=0-7 kpti=off"`. No root/tree `qcom,pmic-id` or `qcom,pmic-revid` selector was found in these unmerged bases.

```text
THYME_RELEVANT_STOCK_BASE_DTB_INDEX=0
SELECTION_CONFIDENCE=STRONG
VENDOR_BOOT_BASE_DTB_SELECTION_AMBIGUOUS=NO
```

This selection combines exact DTB0 SM8250 v2.1 metadata, exact unique Stock DTBO entry 21 board-id `<45 0>`, successful base0+entry21 overlay validation, and the already recorded runtime `dtb_idx=0`/`dtbo_idx=21`. It does not reuse the old DTB-order inference without checking the artifact.

### Exact M1 DTB

```text
size=106026
sha256=cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0
model=Xiaomi Mi 10S (thyme)
compatible=xiaomi,thyme / qcom,sm8250
msm-id=<356 0x20001>
board-id=<45 0>
/memory@80000000 reg=<0 0x80000000 0 0>
/chosen stdout-path=serial0:115200n8
reserved-memory direct children=18
pmic selectors: regulators-0="a", regulators-1="c"
```

### Vendor factorization and controls

- V1 topology: four concatenated FDTs versus one.
- V2 payload: downstream kona v2.1 versus Mainline thyme.
- V3 selector placement: Stock `<0 0>` on every real base and `<45 0>` on the overlay; M1 `<45 0>` on both base and no-op overlay.
- V4 compatible: `qcom,kona` versus `xiaomi,thyme` / `qcom,sm8250`.
- V5 memory/chosen/reserved-memory: Stock placeholder memory and downstream map versus Mainline zero-size `memory@80000000`, serial stdout, and upstream-derived 18-region map.
- V6 layout: same DTB start but different count, DTB size, image extent, and padding.

V-Control-1 is structurally feasible only as two separately labelled designs: V1A retains M1 base `<45 0>`; V1B uses Stock base `<0 0>`. Fixed DTB0 extent would require valid trailing-space expansion. Neither V-Control-1 variant was emitted, so topology and selector are not falsely presented as one variable.

V-Control-2 was emitted privately as `m5g-v-single-stock-dtb-vendor_boot.img`:

```text
size=548864
sha256=e49e12ad71839bc959237eb8ef6ad6ba7f2f38dffedcf31f3fe36b0845402e83
single-DTB topology preserved=YES
DTB payload=exact Stock DTB0
vendor ramdisk unchanged=YES
header unchanged except derived dtb_size=YES
unavoidable secondary delta=dtb_size + artifact/page-padding extent
```

## DTBO audit

| Header field | Stock | M1 |
|---|---:|---:|
| Magic | `0xd7b7ab1e` | `0xd7b7ab1e` |
| File size | 33554432 | 387 |
| `total_size` | 13415454 | 387 |
| `header_size` | 32 | 32 |
| `entry_size` | 32 | 32 |
| `entry_count` | 29 | 1 |
| `entries_offset` | 32 | 32 |
| `page_size` | 4096 | 4096 |
| version | 0 | 0 |

All 29 Stock entries have id/rev/custom[0..3] equal to zero. `dtbo-stock-entry-matrix.txt` records every entry's exact offset, size, SHA, model, compatible, msm-id, and board-id.

### Exact Stock thyme entry

```text
THYME_STOCK_DTBO_ENTRY_INDEX=21
offset=9666706
size=484885
sha256=44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93
id/rev/custom[0..3]=all zero
model=Qualcomm Technologies, Inc. xiaomi thyme
compatible=qcom,kona-mtp / qcom,kona / qcom,mtp
msm-id=none
board-id=<45 0>
fragment count=124
raw fragment targets=<0xffffffff>, resolved through __fixups__
__fixups__=present, 154 symbols
__local_fixups__ subtree=present
__symbols__=present, 386 symbols
```

Entry 21 is the unique exact Stock entry with root board-id `<45 0>`. Private CI successfully applied it to exact Stock DTB0.

### Exact M1 entry

```text
entry index=0
offset=64
size=323
payload sha256=37d6855a5930508b0dd349d8ba2bb167f47e415de2b754a7af0fe80d11ee7c96
id/rev/custom[0..3]=all zero
model=Xiaomi Mi 10S (thyme) Route B no-op
compatible=qcom,kona-mtp / qcom,kona / qcom,mtp
msm-id=none
board-id=<45 0>
fragment count=1
target-path=/
__fixups__/__local_fixups__/__symbols__=absent
marker=qcom,thyme-route-b-noop
```

### DTBO factorization and controls

- D1 topology: 29 entries versus one.
- D2 header: same format sizes, offset, page size, and version; different total size/count.
- D3 selector metadata: both selected table records are zero; both payload roots use `<45 0>`.
- D4 payload: 124-fragment Stock overlay with external fixups versus one target-path no-op marker.
- D5 layout: Stock entry 21 at 9666706/484885 versus M1 entry 0 at 64/323.

D-Control-1 was emitted privately as `m5g-d-stock-table-m1-payload-dtbo.img`:

```text
size=33554432
sha256=31e1c2ff828076c52a2f018f329fe23d7c62e59d3993a53bdf798396a61c7c37
entry_count=29
table bytes exact Stock=YES
entry 21 metadata exact Stock=YES
other 28 payloads exact Stock=YES
bytes outside entry 21 slot exact Stock=YES
fixed slot valid under dtc + fdtoverlay=YES
FIXED_SLOT_REPLACEMENT_UNSAFE=NO
```

The M1 no-op's FDT `totalsize` is expanded to 484885 and trailing FDT space is zero-filled. This secondary delta is required to preserve every Stock offset and the full physical slot.

D-Control-2 was also emitted privately as `m5g-d-single-table-stock-payload-dtbo.img`, size 484949, SHA256 `bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a`. It preserves M1 one-entry semantics, record metadata, and payload offset; `total_size`, `dt_size`, payload, and artifact extent necessarily change.

## Required private GHA outputs

```text
vendor-boot-stock-layout.txt
vendor-boot-m1-layout.txt
vendor-boot-dtb-matrix.txt
dtbo-stock-header.txt
dtbo-stock-entry-matrix.txt
dtbo-m1-header.txt
dtbo-m1-entry.txt
m5g-factor-decomposition.md
candidate-control-diff-plan.md
binary-diff-map.txt
m5g-gates.txt
SHA256SUMS
```

The private workflow additionally retains any OEM-derived controls. No Stock DTB, Stock overlay, hybrid `vendor_boot`, or hybrid `dtbo` may enter the public repository.

## Binary diff gates

Private GHA emitted exact byte-range maps. Summary:

| Control | Before size | After size | Exact changed ranges | Changed bytes | Secondary delta |
|---|---:|---:|---:|---:|---|
| V single Stock DTB | 114688 | 548864 | 14025 | 502920 | `dtb_size`, length, page padding |
| D Stock table/M1 payload | 33554432 | 33554432 | 65123 | 276205 | padded FDT `totalsize`/zero space inside selected slot |
| D single table/Stock payload | 387 | 484949 | 33 | 484774 | `total_size`, `dt_size`, length |

```text
READY_FOR_M5G_V_SINGLE_STOCK_DTB_CONTROL=YES
READY_FOR_M5G_D_STOCK_TABLE_M1_PAYLOAD_CONTROL=YES
NEXT_TRUE_DEVICE_CONTROL=V_SINGLE_STOCK_DTB
NO_DEVICE_OPERATION=YES
WAIT_FOR_USER_APPROVAL=YES
```

`V_SINGLE_STOCK_DTB` is recommended first because current B already has exact Stock `dtbo`; a future approved test can isolate Vendor payload versus single-DTB structure without a DTBO context write. No device action is authorized by either READY gate.
