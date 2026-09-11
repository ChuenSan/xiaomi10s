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

## Vendor_boot decomposition

- V1 topology: Stock has four concatenated FDTs; M1 has one.
- V2 payload: Stock downstream kona family versus Mainline thyme.
- V3 selector placement: Stock separates base selector `<0 0>` from thyme overlay `<45 0>`; M1 places `<45 0>` on its base DTB and no-op overlay.
- V4 compatible: Stock kona pattern versus `xiaomi,thyme` / `qcom,sm8250`.
- V5 `/memory`, `/chosen`, reserved-memory, and other root/tree content.
- V6 DTB-region size, concatenation, extent, and page padding.

The exact private-CI audit must independently re-establish every field. Historical `dtb_idx=0` is evidence, not a substitute for parsing the authoritative image.

### Vendor cross-controls

`V-Control-1` keeps the Stock four-DTB topology and replaces only DTB0 after exact selection. It must remain split into:

- V1A: Mainline payload with M1 base `board-id <45 0>`.
- V1B: Mainline payload with Stock base `board-id <0 0>`.

A fixed DTB0 extent requires valid FDT trailing-space expansion. No V-Control-1 artifact is approved merely from design.

`V-Control-2`, named `V_SINGLE_STOCK_DTB`, keeps M1 single-DTB semantics and uses the exact thyme-relevant Stock base payload. This is the highest-information Vendor control because Stock `dtbo` is already the device background.

## DTBO decomposition

- D1 topology: Stock 29 entries versus M1 one entry.
- D2 container/header: total/header/entry sizes, entries offset, page size, version.
- D3 selected entry: id, rev, custom words, board/msm selector representation.
- D4 payload: Stock thyme overlay versus M1 no-op overlay.
- D5 payload size, offsets, alignment, and padding.

### DTBO cross-controls

`D-Control-1`, named `D_STOCK_TABLE_M1_PAYLOAD`, keeps the complete Stock table and other 28 payloads while replacing only entry 21's payload. Preferred construction expands the valid M1 FDT `totalsize` and zero-fills trailing FDT space to preserve the Stock physical slot. If CI cannot validate that representation, the gate must stop at `FIXED_SLOT_REPLACEMENT_UNSAFE`.

`D-Control-2` keeps M1 one-entry container semantics and substitutes the exact Stock thyme overlay. Its unavoidable deltas are header total size, selected entry size, and artifact extent.

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

## Gate policy

```text
READY_FOR_M5G_V_SINGLE_STOCK_DTB_CONTROL=PENDING_PRIVATE_GHA
READY_FOR_M5G_D_STOCK_TABLE_M1_PAYLOAD_CONTROL=PENDING_PRIVATE_GHA
NEXT_TRUE_DEVICE_CONTROL=PENDING_PRIVATE_GHA
NO_DEVICE_OPERATION=YES
WAIT_FOR_USER_APPROVAL=YES
```

If both controls pass, the default next control is `V_SINGLE_STOCK_DTB`, because the current B context already has Stock `dtbo` and a future test would require only one `vendor_boot_b` context write. This is an ordering recommendation, not device authorization.
