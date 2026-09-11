# Route B Mainline V2 M5K0 — DTBO 2x2 factorial missing Cell D (CI qualification)

Status: CI qualification **and** true-device Cell D control — complete.
Final gate template:
`READY_FOR_MAINLINE_V2_M5K_DTBO_ONE_ENTRY_STOCK_PAYLOAD_CONTROL`
(CI stage) → measured stage final gate
`MAINLINE_V2_M5K_ONE_ENTRY_STOCK_PAYLOAD_SUPPRESSES_4P7S` (see §21).
Current Slot B is unchanged in its constituents:
exact M5D `boot_b` + M5H `<45 0>` single Stock DTB0 `vendor_boot_b` +
M5K one-entry / exact-Stock-payload `dtbo_b`.

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
| D | M1 one-entry | Stock thyme entry21 | >12s | measured (M5K, §22) |

The factorial is now complete: see §22 for the measured Cell D result and the
full interpretation.

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
SHA256                                 045fa86dadec5be129554a33289c2d9937df9f0a853473a9a3ffd44a4f22c989
first 484949 bytes SHA256              bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a
[484949,EOF) SHA256                    d23955ce270321bbf3ddefe9beb0d9eea71abea54397fe69236bb9865fb3d5f3
[484949,EOF) == Stock same-range SHA   YES
Stock entry21 slot [9666706,10151591)  == exact Stock thyme overlay payload
Stock entry21 slot SHA256              44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93
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

Authoritative run: private GHA
[`34580065358`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34580065358),
private wrapper commit `4939a9d59d55619e128a19095f9cb3521e065a11`, pinned public
source commit `f6bc9b72e3ceb4a217d692c27c65ab3642ffe69f`.

```text
private run                 34580065358
public source commit        f6bc9b72e3ceb4a217d692c27c65ab3642ffe69f
public source audit         345798...(source commit) PASS
M5K0_FULL_ARTIFACT_SIZE     33554432
M5K0_FULL_ARTIFACT_SHA256   045fa86dadec5be129554a33289c2d9937df9f0a853473a9a3ffd44a4f22c989
prefix [0,484949) SHA256    bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a  MATCH
Stock same-offset tail SHA  d23955ce270321bbf3ddefe9beb0d9eea71abea54397fe69236bb9865fb3d5f3  MATCH
entry_count                 1     (re-audited)
dt_offset                   64    (re-audited)
dt_size                     484885 (re-audited)
entry metadata              all zero (re-audited)
Stock payload exact         YES   (re-audited)
payload fragments/fixups/symbols   124 / 154 / 386  (matches M5G record)
fdtoverlay Stock base       PASS  merged c48ef53de0dc3ad3ca31818b913b7380f615bbed8df925416abbae8ef0a8535b
                            == M5H record, FDTOVERLAY_MERGED_SHA_EQUALS_M5H_RECORD=YES
diff vs M1 changed ranges   33
diff vs Stock changed ranges 50405, changed bytes 368759
Stock same-offset tail changed 0 ranges, 0 bytes
negative tests              11/11 PASS, FAIL_CLOSED=PASS
READY gate                  YES
```

Full gate list is `m5k0-gates.txt` inside the private artifact
`thyme-mainline-v2-m5k0-private-4939a9d...`.

Run history, recorded for transparency:

```text
34579614134  FAILED  M1-vs-CellD range gate was over-strict: the leading zero
                     byte of total_size/dt_size is equal, so the first changed
                     byte is at offset 5 and 33, not at the field start.
34579852041  PASS    superseded: FDT fragment walk counted 0 fragment nodes
                     instead of 124 (root-child depth bug in the report only).
                     The normalized image bytes and every image-level gate were
                     already identical to the authoritative run.
34580065358  PASS    authoritative
```

The executable image identity did not change between `34579852041` and
`34580065358`: `M5K0_FULL_ARTIFACT_SHA256` is identical in both, because the
second fix touched only the FDT report walk and the shape gate.

## 19a. Private artifacts

Only the private auxiliary CI repository stores OEM-derived output. Nothing
below is committed to the public repository.

```text
m5k0-full-normalized-dtbo.img      33554432  045fa86dadec5be129554a33289c2d9937df9f0a853473a9a3ffd44a4f22c989
m5k0-d-control2-short-dtbo.img       484949  bfa80da2032ad016916052f45059cb33c32013bde6789737c553d07f7870390a
m5k0-binary-diff-vs-stock.txt                exact 50405 changed ranges
m5k0-binary-diff-vs-m1.txt                   exact 33 changed ranges
m5k0-negative-tests.txt                      11/11 PASS
m5k0-factor-matrix.md                        corrected matrix and Cell-D design
```

`m5k0-d-control2-short-dtbo.img` is a byte-identical re-emission of the audited
private run `34559797694` artifact, so the future device round has a single
verified artifact set.

## 20. Next, not executed (superseded by §21)

```text
NEXT=M5K DTBO MISSING CELL TRUE DEVICE CONTROL
WAIT FOR USER APPROVAL
NO NEXT STAGE EXECUTED=YES
```

---

# Part II — MAINLINE_V2_M5K_DTBO_MISSING_CELL_TRUE_DEVICE_CONTROL (measured)

## 21. Round constraints and scope

```text
MEM0_READ_BEFORE_M5K            YES
MEM0_READ_BEFORE_WRITE          YES
LOCAL_BUILD                     NO
LOCAL_VALIDATION                NO
LOCAL_VALIDATOR                 NO
LOCAL_SOURCE_GATE               NO
LOCAL_ACTIONLINT                NO
LOCAL_BINARY_VALIDATION         NO
GHA_ONLY                        YES
new build this round            NO
artifact regeneration           NO
artifact modification           NO
ONLY PARTITION WRITE            dtbo_b
boot_b / vendor_boot_b write    NO
vbmeta* / firmware write        NO
ANY *_a write                   NO
B BOOTS                         1
SECOND_B_BOOT_FORBIDDEN         YES
older dtbo restore              NO
file/directory deletion         NO
M5L auto-execution              NO
```

The only intended logical variable of this round is the DTBO container/table
topology. Boot, vendor, vbmeta and firmware are held byte-identical to the
Reference Cell A context, and the selected overlay payload is the *same exact*
Stock thyme entry21 that Cell A uses.

## 22. Cell D true-device result — CASE K1

```text
CASE                            K1
T_REBOOT_CMD                    2026-09-11T08:50:03.333Z
T_DISAPPEAR                     1789116603.651
T_DISAPPEAR_ISO                 2026-09-11T08:50:03.651Z
PRIMARY_OBSERVATION             >12s
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S   NO
AUTOMATIC_ELAPSED               N/A
MANUAL_RECOVERY                 YES
MANUAL_RECOVERY_TIME            211s
MANUAL_RECOVERY_TIME_ISO        2026-09-11T08:54:13Z
```

The host observation window is 12 seconds and watches for the fastboot USB
device to disappear and return. It did not return inside the window, so the
observation is recorded as `PRIMARY_OBSERVATION=>12s`.

Manual recovery semantics: Fastboot was restored by a physical user action,
not by the device itself. The elapsed time is therefore recorded only as
`MANUAL_RECOVERY_TIME`. It is explicitly **not** recorded as `T_REAPPEAR`,
`AUTOMATIC_RETURN_TIME` or `NATURAL_RETURN_TIME`, because those labels would
falsely assert an automatic return inside the window.

## 23. Pre-write and post-write device identity

```text
PREFLIGHT  product=thyme unlocked=yes current-slot=a
           snapshot-update-status=none battery-soc-ok=yes
           slot-retry-count:b=6 slot-unbootable:b=no
BASELINE   slot_suffix=_a boot_completed=1 root=uid=0 device=thyme

PREWRITE boot_b[0,35110912)      4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH
PREWRITE vendor_boot_b[0,548864) 2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9  MATCH
PREWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
PREWRITE dtbo_b whole            31e1c2ff828076c52a2f018f329fe23d7c62e59d3993a53bdf798396a61c7c37  MATCH (M5J)
PREWRITE vbmeta_b[0,8192)        37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c  stock
PREWRITE vbmeta_system_b[0,4096) 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355  stock
PREWRITE abl/xbl/xbl_config/tz    prefixes MATCH M5H record
M5K_START_M5J_CONTEXT_EXACT      YES

FLASH     fastboot flash dtbo_b  OKAY (32768 KB sent, 0.805s / 0.072s write)
POST_FLASH_CURRENT_SLOT          a          (reboot to Android A, not B)

POSTWRITE dtbo_b whole           045fa86dadec5be129554a33289c2d9937df9f0a853473a9a3ffd44a4f22c989  MATCH
POSTWRITE boot_b                 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH
POSTWRITE vendor_boot_b[0,548864) 2d58ef94802e3aaac3115a9ee1c3d69199b054e04f181e39a55a7e75b60564d9 MATCH
POSTWRITE vendor_boot_b[548864,EOF) 5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52 MATCH
POSTWRITE vbmeta*/firmware       byte-identical to pre-write
M5K_FULL_CONTEXT_VERIFIED        YES
```

The written artifact size (`33554432`) equals the physical `dtbo_b` partition
size, so the whole-partition SHA is a valid authoritative gate for the write:
the partition reads back exactly the artifact SHA.

## 24. Recovery and Slot A restoration

```text
RECOVERY pre      current-slot=b slot-retry-count:b=6 slot-unbootable:b=no
RECOVERY action   fastboot set_active a  ->  current-slot=a  ->  fastboot reboot
ANDROID_A_RESTORED YES  slot_suffix=_a  boot_completed=1  root=uid=0
SECOND_B_BOOT_FORBIDDEN YES
```

No ordinary reboot was issued while the device was in the suppressed state.

## 25. Dumps (read-only, nothing cleared, nothing deleted)

```text
pstore               0 entries
minidump             UNCHANGED
rawdump              UNCHANGED
logdump              UNCHANGED
logfs                CHANGED
oops                 CHANGED

oops pre-boot baseline  2b4ea0ee3859a4eb791f2e65185a2d459189169f649811da5ed506fd916df735
oops post               6d32c40d86fa67ba5f148ae345ccf9abd938d456e29d49a5fed9c59b017200d0
oops content            stock Android 2023-09-04 records only
                        21x "reboot,bootloader", 7x "Reason: Restart"
                        0x "Linux version", 0x literal "6.6.", 0x mainline markers
OOPS_MAINLINE_EVIDENCE  NO
```

An Android-A reboot and a bootloader round trip are not Mainline evidence, and
the changed `oops`/`logfs` region contains only dated stock-Android records.

## 26. Complete DTBO 2x2 factorial

| cell | DTBO container/table | selected thyme payload | runtime | round |
| --- | --- | --- | --- | --- |
| A | Stock 29-entry | exact Stock thyme entry21 | **>12s** | M5G/M5D |
| B | Stock 29-entry | M1 no-op | **4.922s** | M5J |
| C | M1 one-entry | M1 no-op | **4.812s** | M5F1 |
| D | M1 one-entry | exact Stock thyme entry21 | **>12s** | M5K |

Reading the matrix column-wise:

```text
payload dimension   Stock payload  -> A >12s, D >12s   (return suppressed)
                    M1 no-op       -> B 4.922s, C 4.812s (return restored)

container dimension Stock table    -> A >12s, B 4.922s  (payload-determined)
                    M1 one-entry   -> D >12s, C 4.812s  (payload-determined)
```

The runtime tracks the **payload** in both container contexts and does not
track the container. With the payload held at the exact Stock overlay, the
one-entry container reproduces the Reference Cell A behaviour (`>12s`), so the
container alone is not the cause.

## 27. Interpretation

```text
M5K_ONE_ENTRY_CONTAINER_EFFECT            NO
M1_ONE_ENTRY_CONTAINER_ALONE_SUFFICIENT   NO
M1_NOOP_PAYLOAD_SUFFICIENT                YES
M1_NOOP_PAYLOAD_CAUSAL_FAMILY             STRONGLY_SUPPORTED

OVERLAY_PAYLOAD_VARIABLE   NO
BOOT_VARIABLE              NO
VENDOR_VARIABLE            NO
VBMETA_VARIABLE            NO
FIRMWARE_VARIABLE          NO

PRIMARY_LOGICAL_VARIABLE   DTBO_CONTAINER_TABLE_TOPOLOGY
                           (entry_count / total_size / payload offset /
                            one-entry image structure)
                           -> rejected as the main cause
```

The DTBO container/table topology is downgraded as a primary cause: changing
`entry_count` `29 -> 1`, `total_size` `-> 484949` and the payload layout while
keeping the exact Stock overlay payload does **not** shorten the suppressed
return. The M1 no-op overlay payload is the sufficient compatibility factor
inside the DTBO track, in both the Stock 29-entry table (M5J) and the M1
one-entry table (M5K).

Not claimed by this round: any per-field statement about *why* the Stock
overlay payload is incompatible with the M1 Mainline base DTB. The next stage
must open the payload itself.

Final gate:

```text
MAINLINE_V2_M5K_ONE_ENTRY_STOCK_PAYLOAD_SUPPRESSES_4P7S
```

## 28. Final state and next direction

```text
B_FINAL  exact M5D boot
       + M5H <45 0> single Stock DTB0 vendor_boot
       + M5K one-entry / exact-Stock-payload dtbo
Stock / M5J dtbo NOT restored
Slot A active and restored
NO_NEXT_STAGE_EXECUTED=YES

NEXT  MAINLINE_V2_M5K_DTBO_PAYLOAD_SEMANTICS_AUDIT_CI
      (payload fragment structure, target paths, board-id placement,
       overlay symbols/fixups, payload totalsize/padding)
      because Cell D is >12s: the container is not the primary cause and the
      overlay payload itself must be decomposed.
```

`MAINLINE_V2_M5K_DTBO_DUAL_FACTOR_AUDIT_CI` is **not** the next stage, because
the dual-factor branch required a ~4.7s Cell D. `MAINLINE_V2_M5L` was not
executed and awaits user approval.

