# Route B Mainline V2 M5K0 — DTBO 2x2 factorial missing Cell D (CI qualification)

Status: CI qualification / artifact preparation only. No device operation.
Final gate template:
`READY_FOR_MAINLINE_V2_M5K_DTBO_ONE_ENTRY_STOCK_PAYLOAD_CONTROL`.
Current Slot B is unchanged:
exact M5D `boot_b` + M5H `<45 0>` single Stock DTB0 `vendor_boot_b` +
M5J Stock-table / no-op `dtbo_b`.

## 0. Correcting the current conclusion boundary

M5J established:

```text
M1_NOOP_PAYLOAD_SUFFICIENT_ON_STOCK_TABLE=STRONGLY_SUPPORTED
```

That result does **not** license:

```text
ONE_ENTRY_CONTAINER_NOT_CAUSAL        <- withdrawn, not measurable yet
```

The fourth factorial cell was never measured. What is permitted today is only
"the M1 no-op payload is sufficient on the Stock 29-entry table". "Payload
sufficient" is not the same statement as "container innocent", and the latter
must not be written until Cell D exists.

Current DTBO matrix:

| cell | DTBO container/table | selected thyme payload | runtime | status |
| --- | --- | --- | --- | --- |
| A | Stock 29-entry | Stock thyme entry21 | >12s | measured |
| B | Stock 29-entry | M1 no-op | 4.922s | measured (M5J) |
| C | M1 one-entry | M1 no-op | 4.812s | measured (M5F1) |
| D | M1 one-entry | Stock thyme entry21 | UNKNOWN | artifact prepared this round |

## 1. Existing D-Control-2 short artifact

Private GHA run [`34559797694`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34559797694)
already emitted a `484949`-byte candidate:

```text
file    m5g-d-single-table-stock-payload-dtbo.img
size    484949
SHA256  bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a
```

This round **re-audits** that artifact. It is not assumed READY. The audit
re-derives the size, the whole-file SHA, every header field, the entry fields,
the entry metadata, the trailing-byte count and the payload SHA, and only then
declares `EXISTING_D_CONTROL2_READY=YES`.

## 2. Cell D logical design

```text
DTBO header/container:
  magic          0xd7b7ab1e
  version        0
  header_size    32
  entry_size     32
  entry_count    1
  entries_offset 32
  page_size      4096
  total_size     484949

entry:
  id             0
  rev            0
  custom[0..3]   0 0 0 0
  dt_offset      64
  dt_size        484885

payload:
  exact Stock thyme entry21
  484885 bytes
  SHA256 44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93
  root board-id  <45 0>
  compatible     qcom,kona-mtp | qcom,kona | qcom,mtp
  fragments      124
  fixups         154
  symbols        386

physical size:
  64 + 484885 = 484949   == existing short artifact size
```

## 3. What this cell actually tests

```text
Cell A  Stock 29-entry table + Stock thyme entry21  -> >12s
Cell D  M1 one-entry table   + SAME Stock entry21   -> ???
```

The single primary variable is `DTBO_CONTAINER_TABLE_TOPOLOGY`:
`entry_count`, the table bytes, `total_size`, and the payload
offset/layout. The overlay payload content is held byte-identical.

This is the necessary experiment for deciding whether one-entry packaging is
independently sufficient.

## 4. Why the payload semantics audit cannot start yet

Known today: the M1 no-op payload is sufficient. Unknown: whether the M1
one-entry container is *also* independently sufficient. Skipping Cell D would
let "payload sufficient" be misreported as "container innocent". That
over-claim is forbidden.

## 5. Short artifact validation

```text
SHA exact                    bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a
magic                        0xd7b7ab1e
version                      0
header_size                  32
entry_size                   32
entry_count                  1
entries_offset               32
page_size                    4096
total_size                   484949
trailing bytes               0
entry dt_offset              64
entry dt_size                484885
entry id/rev/custom          all zero
payload SHA                  44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93
EXACT_STOCK_ENTRY21_PAYLOAD  YES
```

## 6. Why the short artifact is not enough

The current `dtbo_b` is the M5J artifact: Stock 29-entry table with a padded M1
no-op at the Stock entry21 slot. Flashing only the `484949`-byte short image
would leave the M5J tail bytes in place even though DTBO `total_size` semantics
say those bytes are not part of the active image. That residue would be an
uncontrolled explanatory variable.

This round therefore also emits a normalized full-partition artifact:

```text
M5K0_FULL_ARTIFACT_SIZE=33554432

[0,484949)      exact D-Control-2 short artifact
[484949,EOF)    exact Stock dtbo.img same-offset tail bytes
```

i.e. `ONE_ENTRY_STOCK_PAYLOAD_PREFIX + EXACT_STOCK_SAME_OFFSET_TAIL`.

## 7. Why the Stock same-offset tail

The historical M1 short-dtbo experiment also used a small active DTBO prefix
plus a Stock-derived remainder. Using the exact Stock tail:

- removes the M5J no-op entry21 residue
- makes the tail deterministic and gives a whole-partition SHA
- prevents "the short flash did not clear the old data" from becoming an
  explanation

Explicit limitation, recorded: under standard DTBO `total_size` semantics the
tail is **not** part of the active one-entry image. It is physical-partition
normalization only.

## 8. Full artifact verification

```text
size                                   33554432
SHA256                                 computed in GitHub Actions
first 484949 bytes SHA256              bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a
[484949,EOF) SHA256                    == exact Stock dtbo.img same-range SHA
Stock entry21 slot [9666706,10151591)  == exact Stock thyme overlay payload
M5J no-op residue in tail              NO
```

The no-op residue test does not rely only on construction. The audit rebuilds
the M5J padded no-op blob and checks that the Stock entry21 slot in the
normalized image is **not** that blob, then additionally requires the slot to
equal the exact Stock overlay bytes.

## 9. Binary comparison against Stock dtbo

```text
BEFORE  exact Stock dtbo.img     33554432 bytes
AFTER   Cell-D normalized image  33554432 bytes
```

Changed ranges are reported exactly, with a per-region table:

```text
HEADER                  [0,32)
ENTRY_TABLE             [32,64)
CELLD_ACTIVE_PAYLOAD    [64,484949)
STOCK_SAME_OFFSET_TAIL  [484949,33554432)
```

The change is large by construction: the active one-entry image sits at the
partition front, while Stock carried a 29-entry table and payloads there. This
round does **not** claim a single-field delta. The logical variable is
`CONTAINER/TABLE TOPOLOGY`; the payload is exact Stock entry21.

The `STOCK_SAME_OFFSET_TAIL` region is required to report zero changed bytes.

## 10. Binary comparison against M1 dtbo

```text
BEFORE  exact M1 dtbo                 387 bytes
AFTER   Cell-D short artifact     484949 bytes
```

Purpose: confirm that container/header semantics stay `one-entry` and that the
primary payload variable moved from `M1 no-op` to `exact Stock thyme entry21`.

```text
unchanged  [0,4) magic
unchanged  [8,32) header_size entry_size entry_count entries_offset page_size version
unchanged  [36,64) dt_offset id rev custom[0..3]
changed    a sub-range of [4,8) header total_size 387 -> 484949
changed    a sub-range of [32,36) entry dt_size 323 -> 484885
changed    the payload bytes inside [64,387)
added      [387,484949)
```

The changed sub-ranges inside `[4,8)` and `[32,36)` need not start on the field
boundary: both `387`/`484949` and `323`/`484885` share their leading zero byte,
so the first differing byte can sit at offset 5 and offset 33 respectively. The
gate is therefore containment plus "nothing changed outside the two integer
fields in `[0,64)`", not a hard-coded start offset.

The measured `DIFF_VS_M1_EXACT_CHANGED_RANGE_COUNT` is `33`: the FDT header and
structure block of the two payloads differ in many places, so the exact range
count is recorded rather than assumed. What is asserted is that every changed
byte lies in `[4,8)`, `[32,36)`, `[64,387)`, and that the only range at or after
`387` is `ADDED [387,484949)`.

## 11. libfdt / dtbo parser validation

```text
DTBO parse                          PASS
entry_count                         1
selected payload parse              PASS
selected payload SHA                == exact Stock entry21
dtc round trip (payload, no-op)     PASS
fdtoverlay  exact Stock DTB0 + Cell-D extracted payload   PASS
merged SHA256                       recorded
```

The merged SHA is also compared with the M5H record
`c48ef53de0dc3ad3ca31818b913b7380f615bbed8df925416abbae8ef0a8535b`. This is
structural validation only and is explicitly not Xiaomi ABL evidence.

## 12. Fail-closed negative tests

Each of the following must be detected by the same verifier used for the
positive check:

```text
wrong payload byte            -> detected
entry_count != 1              -> detected
dt_offset != 64               -> detected
dt_size != 484885             -> detected
entry metadata nonzero        -> detected
header total_size wrong       -> detected
full artifact size wrong      -> detected
tail differs from Stock       -> detected
M5J no-op residue in slot     -> detected
```

Nine mutation cases plus two unmutated control cases make
`NEGATIVE_TEST_COUNT=11`. The unmutated artifacts must produce zero violations,
so the checks are demonstrably reachable rather than vacuous.

## 13. Final READY gate

```text
READY_FOR_MAINLINE_V2_M5K_DTBO_ONE_ENTRY_STOCK_PAYLOAD_CONTROL=YES
```

Failure labels:

```text
M5K0_D_CONTROL2_IDENTITY_FAILED
M5K0_D_CONTROL2_CONTAINER_INVALID
M5K0_D_CONTROL2_PAYLOAD_INVALID
M5K0_D_CONTROL2_TAIL_NORMALIZATION_FAILED
M5K0_D_CONTROL2_NOT_SAFE
```

## 14. Future true-device context

```text
current B
  boot    exact M5D
  vendor  M5H single Stock DTB0, base board-id <45 0>
  dtbo    M5J Stock 29-entry table / padded M1 no-op entry21

future Cell D
  boot    SAME M5D                      (unchanged)
  vendor  SAME M5H                      (unchanged)
  dtbo    M1 one-entry + exact Stock thyme overlay
```

Only `dtbo_b` would be written, and only after explicit user approval.

## 15. Future runtime interpretation

If Cell D returns `>12s`:

```text
Stock table + Stock payload   >12s
Stock table + M1 no-op        4.922s
M1 table    + Stock payload   >12s
M1 table    + M1 no-op        4.812s

M1_NOOP_PAYLOAD=SUFFICIENT
ONE_ENTRY_CONTAINER_ALONE_SUFFICIENT=NO
PAYLOAD_CAUSAL_FAMILY=STRONGLY_SUPPORTED
-> next stage DTBO_PAYLOAD_SEMANTICS_AUDIT
```

If Cell D returns `~4.3-5.3s`:

```text
Stock/Stock   >12s
Stock/M1      4.922s
M1/Stock      ~4.7s
M1/M1         4.812s

M1_NOOP_PAYLOAD independently sufficient
AND
M1_ONE_ENTRY_CONTAINER independently sufficient
-> both questions must be fixed, not payload alone
```

## 16. Inconclusive band

`5.3-12s` is `INCONCLUSIVE`. It must not be forced into either class.

## 17. Device state

```text
DEVICE_OPERATION=NO
Current B unchanged:
  M5D boot
  + M5H Stock DTB0 board45 vendor_boot
  + M5J Stock-table / no-op dtbo
NO ADB DEVICE CHANGE / NO FASTBOOT / NO FLASH / NO SET_ACTIVE / NO B BOOT
```

## 18. Constraints observed

```text
MEM0_READ_BEFORE_M5K0=YES
LOCAL_BUILD=NO
LOCAL_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
GHA_ONLY=YES
new build this round=NO
SLOT_A flash/erase/format=FORBIDDEN
OEM-derived artifact = PRIVATE ONLY
no automatic true-device stage
```

All artifact transformation, DTBO parse, binary diff, libfdt/fdtoverlay and
fail-closed validation run only in GitHub Actions. The public repository stores
source, workflow and documentation only, never an OEM-derived image.

## 19. GitHub Actions results

Filled from the private M5K0 run; see the workflow log and `m5k0-gates.txt`.

```text
private run                 PENDING
M5K0_FULL_ARTIFACT_SIZE     33554432 (expected)
M5K0_FULL_ARTIFACT_SHA256   PENDING
prefix match                PENDING
Stock same-offset tail      PENDING
entry_count                 1 (re-audited)
dt_offset                   64 (re-audited)
dt_size                     484885 (re-audited)
entry metadata              all zero (re-audited)
Stock payload exact         YES (re-audited)
fdtoverlay Stock base       PENDING
negative tests              PENDING
READY gate                  PENDING
```

## 20. Next, not executed

```text
NEXT=M5K DTBO MISSING CELL TRUE DEVICE CONTROL
WAIT FOR USER APPROVAL
NO NEXT STAGE EXECUTED=YES
```
