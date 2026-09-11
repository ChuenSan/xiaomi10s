# Route B Mainline V2 — M5M target/fixup × marker factorial

Stage id (CI):

```text
MAINLINE_V2_M5M_TARGET_FIXUP_MARKER_FACTORIAL_CI
```

Stage id (Candidate A true-device):

```text
MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_TRUE_DEVICE_CONTROL
```

Stage id (Candidate B true-device, this round):

```text
MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_TRUE_DEVICE_CONTROL
```

CI construction of A/B remains private-GHA-only (private run `34591653733`).
Candidate A was the L1→A marker control (`CASE=A2`, 4.834s). Candidate B is
the last factorial cell and has now been flashed once as the L2→B
within-T1 marker control (`CASE=B1`, `PRIMARY_OBSERVATION=>12s`).

## 1. Constraints honoured

```text
MEM0_READ_BEFORE_M5M         YES
LOCAL_BUILD                  NO
LOCAL_VALIDATION             NO
LOCAL_VALIDATOR              NO
LOCAL_SOURCE_GATE            NO
LOCAL_ACTIONLINT             NO
LOCAL_BINARY_VALIDATION      NO
GHA_ONLY                     YES
DEVICE_OPERATION             NO
ADB_DEVICE_CHANGE            NO
FASTBOOT                     NO
FLASH                        NO
ERASE                        NO
FORMAT                       NO
SET_ACTIVE                   NO
B_BOOT                       NO
SLOT_A_WRITTEN               NO
CURRENT_B                    UNCHANGED
BUILD_THIS_ROUND             NO
OEM_DERIVED_ARTIFACT         PRIVATE ONLY
L2_RESTORE                   NO
FUTURE_TRUE_DEVICE_AUTO_EXEC NO
```

Current Slot B is untouched:

```text
exact M5D boot
+ M5H board45 Stock DTB0 vendor
+ M5L-L1 dtbo
```

## 2. Authoritative cells already measured

Held constant across the whole matrix:

```text
boot     exact M5D
vendor   M5H board45 Stock DTB0
vbmeta   stock
firmware stock
model    exact Stock
root     Stock identity / selectors
container one-entry, 1 fragment
```

Historical M1 no-op (reference, not a matrix cell under Stock model):

```text
model     M1
target    target-path="/"
fixups    none
marker    present
runtime   ~4.8–4.9s
```

```text
TM-11 = M5L-L1
  T0  target-path="/"
  M1  marker present
  runtime 4.837s

TM-20 = M5L-L2
  T1  Stock-style target + __fixups__  (mdss_mdp)
  M0  marker absent, empty __overlay__
  runtime PRIMARY_OBSERVATION=>12s
```

L1 result:

```text
ROOT_MODEL_TEXT_EFFECT=NO
STOCK_MODEL_TEXT_ALONE_SUFFICIENT=NO
```

`/model` is frozen at exact Stock for every cell in this factorial. It is not
re-tested.

## 3. Remaining 2×2

```text
Factor T  targeting mechanism
  T0  target-path="/"
  T1  Stock-style target + __fixups__   symbol mdss_mdp
      path /soc/qcom,mdss_mdp@ae00000

Factor M  marker property in the fragment overlay body
  M0  absent, empty __overlay__
  M1  present, qcom,thyme-route-b-noop exact historical value
```

Missing cells constructed this round:

```text
TM-10  Candidate A  M5M_A_TARGET_PATH_NO_MARKER
       T0 + M0
       Stock model, target-path="/", marker absent, empty overlay

TM-21  Candidate B  M5M_B_FIXUP_WITH_MARKER
       T1 + M1
       Stock model, target=<&mdss_mdp>, __fixups__ present, marker present
```

## 4. Why A is first

Current B already is L1: `target-path="/" + marker present → 4.837s`.

A changes only marker presence under that same targeting background:

```text
L1 → A
only payload semantic variable: MARKER_PROPERTY_PRESENCE
```

That is the cleanest single-variable true-device control available. B is
constructed and validated in the same CI run so the factorial is complete, but
it is **not** the recommended next flash.

```text
NEXT_TRUE_DEVICE_CONTROL=M5M_A_TARGET_PATH_NO_MARKER_TRUE_DEVICE_CONTROL
DO_NOT_FLASH_A_AND_B_TOGETHER=YES
```

## 5. Candidate A source design

Basis: exact L1 / M1-noop structure, reproduced in CI and SHA-checked against
the authoritative L1 payload.

```text
L1_PAYLOAD_SHA256  64344d59119b253d47b950385fbed1c8dd38bf28003604c2deb7dcf1f1777ca4
```

Held:

```text
/model              exact Stock
compatible          exact existing value
qcom,board-id       <45 0>
fragment count      1
fragment target     target-path="/"
__fixups__          ABSENT
__symbols__         ABSENT
```

The only deletion:

```text
qcom,thyme-route-b-noop   from /fragment@0/__overlay__
```

After deletion `__overlay__` must be empty. No replacement marker, no
`status`, no dummy property, no extra phandle in the overlay body.

Binary one-byte identity versus L1 is **not** required: deleting a property
shifts FDT totalsize and offsets. The causal variable is marker presence.

## 6. Candidate A merged semantics

`fdtoverlay` of exact Stock DTB0 + A must PASS.

Ideal:

```text
MERGED_SHA == 324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8
```

because `target-path="/" + empty overlay` should be a true semantic no-op.

If the merged blob is not byte-identical, every semantic difference is
reported. Device-semantic differences are forbidden.

```text
A_SEMANTIC_NOOP_CONFIRMED=YES   required for READY
```

## 7. Candidate B source design

Basis: exact L2, reproduced in CI and SHA-checked.

```text
L2_PAYLOAD_SHA256  408e5709d8f772c0759a4d8ef427b49329a41f38a98776571ac7252d1b841740
target symbol      mdss_mdp
Stock target path  /soc/qcom,mdss_mdp@ae00000
fragment count     1
target style       target = <...>
__fixups__         present
overlay            empty
marker             absent
```

B keeps all of the above and adds the exact historical marker into
`fragment __overlay__`. The value is parsed from the authoritative M1/L1
payload. It is not guessed.

## 8. Marker merge-destination interaction

This is not a fully orthogonal factorial on merged location.

```text
L1 marker  target-path="/"           → merges onto base root /
B  marker  target=<&mdss_mdp>        → merges onto /soc/qcom,mdss_mdp@ae00000
```

Factor M is defined as:

```text
MARKER_PROPERTY_PRESENT_IN_FRAGMENT_OVERLAY_BODY
```

It is **not** defined as `MARKER_APPLIED_TO_SAME_BASE_NODE`.

```text
MARKER_APPLIED_TO_SAME_BASE_NODE=NO
FOUR_CELLS_MARKER_MERGED_LOCATION_IDENTICAL=NO
```

B is still a clean within-T1 marker control: L2 is T1/M0 `>12s`; B is T1/M1
with the historical marker restored into the same Stock-style target/fixup
payload.

## 9. Candidate B merged semantics

`fdtoverlay` of Stock DTB0 + B must PASS.

The only allowed device-semantic addition:

```text
qcom,thyme-route-b-noop
at /soc/qcom,mdss_mdp@ae00000
```

Forbidden: status / reg / interrupt / clock / regulator / compatible or any
other device property change.

```text
B_ONLY_MARKER_SEMANTIC_DELTA=YES   required for READY
```

Fixup offset bytes may shift because the overlay body is no longer empty.
That serialization shift is allowed in the B-vs-L2 source diff; the fixup
symbol must remain `mdss_mdp`.

## 10. Future within-background comparisons

Once A (and, only if later approved, B) have true-device runtimes:

```text
MARKER under target-path:
  L1 T0/M1  4.837s
  A  T0/M0  ???

MARKER under target+fixup:
  L2 T1/M0  >12s
  B  T1/M1  ???

TARGET under marker-absent:
  A  T0/M0
  L2 T1/M0

TARGET under marker-present:
  L1 T0/M1
  B  T1/M1
```

That is the complete factorial reading. This CI round does not produce
runtimes.

## 11. Frozen variables

Not reopened this round:

```text
/model
board-id
container entry count
payload padding
Stock 124-fragment topology
143 downstream aliases
```

The factorization is already reduced to target/fixup × marker.

## 12. One-entry container and full-partition artifact

Both candidates:

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
entry dt_size    exact payload FDT size
total_size       64 + payload size
```

Full artifact, 33554432 bytes:

```text
[0, ACTIVE_PREFIX_SIZE)              one-entry header/table + candidate payload
[ACTIVE_PREFIX_SIZE, 33554432)       exact Stock dtbo.img same offset → EOF
```

Reported per candidate: payload size/SHA, active prefix size/SHA, full size
33554432 and SHA, stock tail offset/SHA.

## 13. Future A interpretation (not executed)

### Case 1 — A `>12s`

```text
L1  target-path + marker present   4.837s
A   same target-path, marker absent >12s

MARKER_PROPERTY_EFFECT_UNDER_TARGET_PATH=YES
MARKER_PRESENT_SUFFICIENT_FOR_4P7S_PATH_UNDER_TARGET_PATH=STRONGLY_SUPPORTED
Final future Gate=MAINLINE_V2_M5M_A_MARKER_REMOVAL_SUPPRESSES_4P7S
```

Engineering consequence: a Stock-style target/fixup overlay is **not**
required to obtain a minimal compatible no-op. `target-path="/" + empty
overlay + no marker` itself may be accepted by the current boot path, and is
simpler than L2.

Do **not** auto-run B. Next CI, after approval:

```text
MAINLINE_V2_M5N_MARKER_CAUSAL_CONFIRMATION_CI
```

inspecting marker name / value / location / unknown-property handling, then
design the final minimal DTBO.

### Case 2 — A `~4.3–5.3s`

```text
MARKER_PROPERTY_EFFECT_UNDER_TARGET_PATH=NO
MARKER_REMOVAL_ALONE_SUFFICIENT=NO
```

Then B becomes the necessary next shot, because:

```text
A  T0/M0  ~4.7
L2 T1/M0  >12
```

already strongly supports a target/fixup mechanism effect under
marker-absent, and B completes the factorial as T1/M1.

## 14. Future B interpretation (only if later approved)

B `>12s` plus A `~4.7`, L1 `~4.7`, L2 `>12`:

```text
TARGET_FIXUP_MECHANISM_EFFECT=STRONGLY_SUPPORTED
```

B `~4.7s` with A `~4.7`, L1 `4.837`, L2 `>12`:

target/fixup and marker-absence interact; the combination is what leaves
the wall.

If A is already `>12s`, B is **not** auto-executed even if its artifact is
READY. Further B true-device work needs a separate approval.

## 15. Marker audit (measured in CI, not guessed)

Required report, from historical M1/L1 payload:

```text
node path
property name
property type
property byte length
raw bytes
decoded value
present in Stock entry21     YES/NO
```

ABL visibility is a fact audit only:

```text
property is in the overlay payload FDT (visible before apply)
property is in the qcom, namespace
Stock entry21 same-name search, expected ABSENT
```

Do **not** claim ABL fails because of an unknown qcom property.

Source-only string search of the public checkout for
`qcom,thyme-route-b-noop` and `route-b-noop` is auxiliary. It is not a gate.
No extra network clone.

## 16. Fail-closed validation

Candidate A:

```text
marker still present              FAIL
target-path not "/"               FAIL
fixups appear                     FAIL
merged tree not semantic no-op    FAIL
```

Candidate B:

```text
marker missing                    FAIL
target/fixup does not match L2    FAIL
marker value/type ≠ historical    FAIL
merged semantic diff exceeds marker FAIL
```

Shared:

```text
wrong model / board-id
entry_count != 1
wrong dt_size / total_size / tail
full artifact size != 33554432
```

Negative tests at minimum:

```text
A marker-present mutant           rejected
A target-fixup mutant             rejected
A nonempty-overlay mutant         rejected
B marker-absent mutant            rejected
B wrong-marker-value mutant       rejected
B target-path mutant              rejected
wrong model                       rejected
wrong board-id                    rejected
wrong full tail                   rejected
wrong full size                   rejected
```

## 17. READY gates

```text
READY_FOR_MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_CONTROL=YES/NO
READY_FOR_MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_CONTROL=YES/NO
```

If A is READY, the recommended next true-device control is:

```text
M5M_A_TARGET_PATH_NO_MARKER_TRUE_DEVICE_CONTROL
```

## 18. Identity of reconstructed L1/L2

A and B are not invented overlays. CI first reproduces L1 and L2 with the
same DTC 1.7.0 path used in M5L and fails closed unless:

```text
reproduced L1 SHA == 64344d59119b253d47b950385fbed1c8dd38bf28003604c2deb7dcf1f1777ca4
reproduced L2 SHA == 408e5709d8f772c0759a4d8ef427b49329a41f38a98776571ac7252d1b841740
```

A is then L1 DTS with the marker property omitted. B is the L2 DTS with the
historical marker inserted into `__overlay__`.

## 19. Measured results (private CI run 34591653733)

Public source commit `4bc0d68dd6d0b78cba37b71efb8cc8462bc598a7`, private
wrapper commit `35e31fe` (pinned), `dtc 1.7.0`, all gates `PASS`,
`FAIL_CLOSED=PASS`, 19/19 negative tests PASS. L1 and L2 payloads reproduced
byte-for-byte before A/B construction.

### 19.1 Historical marker encoding

Parsed from authoritative M1 and reproduced L1 (identical):

```text
path          /fragment@0/__overlay__
name          qcom,thyme-route-b-noop
type          EMPTY_BOOLEAN
byte length   0
raw bytes     EMPTY
decoded       <empty>
M1 present    YES
L1 present    YES
Stock entry21 FDT search    ABSENT
Stock entry21 raw search    ABSENT
qcom namespace              YES
in overlay payload FDT      YES (visible before apply)
ABL unknown-qcom-property failure   NOT_CLAIMED
```

Public-checkout string search for `qcom,thyme-route-b-noop` / `route-b-noop`:
32 hits, all in this experiment's scripts/docs/workflows. No bootloader source
hit. Not a gate.

### 19.2 Candidate A (TM-10, READY)

```text
model              Stock exact
target             target-path="/"
marker             ABSENT
fixups/symbols     ABSENT
fragment count     1
overlay body       empty (0 props, 0 children)
A vs L1 source     only qcom,thyme-route-b-noop removed from overlay
fdtoverlay         PASS
merged SHA         324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8
                   == exact Stock DTB0 (byte-identical)
A_SEMANTIC_NOOP_CONFIRMED=YES
A_MERGED_SHA_EQUALS_STOCK_DTB0=YES

PAYLOAD_SIZE / SHA256          295 / 55df159d4915746bf294c3b2a723143d7b65480640828a27f9c658552c061b64
ACTIVE_PREFIX_SIZE / SHA256    359 / 3cba896892e0ccdaccbf5daccaa725c04cb81f9085355e9b13cddb897af1246d
STOCK_TAIL_OFFSET / SHA256     359 / a7e58eea2808e268af37071df9badaec9f06731e6baf11ba72bb1bd01ab4f984
FULL_ARTIFACT_SIZE / SHA256    33554432 / 128bcd312769f34b218b809169317ae456ea10350ed5553067eed7f52035633c
READY_FOR_MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_CONTROL=YES
```

`target-path="/" + empty overlay` is a true semantic no-op on exact Stock DTB0.

### 19.3 Candidate B (TM-21, READY)

```text
model              Stock exact
target             mdss_mdp via __fixups__
target path        /soc/qcom,mdss_mdp@ae00000
marker             PRESENT (exact historical empty boolean)
fragment count     1
fixups count       1
overlay body       marker only
B vs L2 source     only qcom,thyme-route-b-noop added to overlay
                   (no fixup-offset shift observed)
fdtoverlay         PASS
merged delta       only added /soc/qcom,mdss_mdp@ae00000:qcom,thyme-route-b-noop
B_ONLY_MARKER_SEMANTIC_DELTA=YES
B_MARKER_MERGED_TARGET=/soc/qcom,mdss_mdp@ae00000
MARKER_APPLIED_TO_SAME_BASE_NODE=NO

PAYLOAD_SIZE / SHA256          391 / 5c5b070bf81f55ee68a8bce0c31a625d087aecda89f22e9e69416f89bfca0929
ACTIVE_PREFIX_SIZE / SHA256    455 / 8a3fc0e9f0db7fb21627c983a036d81a664e6924223b6cba53c58236d1968812
STOCK_TAIL_OFFSET / SHA256     455 / 04184621bbba922a3419c1980e0b85750249efd3035ffd35ce5dceced770dbdd
FULL_ARTIFACT_SIZE / SHA256    33554432 / c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
READY_FOR_MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_CONTROL=YES
```

### 19.4 Complete factorial after B true-device

```text
T0/M1  L1  4.837s     measured
T0/M0  A   4.834s     measured  CASE=A2
T1/M0  L2  >12s       measured
T1/M1  B   >12s       measured this round  CASE=B1
```

Runtime groups entirely by Factor T: `target-path="/"` → ~4.8s;
`target+__fixups__` → >12s. Marker presence does not change category
under either targeting background.

### 19.5 Gate summary after B true-device

```text
READY_FOR_MAINLINE_V2_M5M_A_TARGET_PATH_NO_MARKER_CONTROL=YES
READY_FOR_MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_CONTROL=YES
A_TRUE_DEVICE=YES  CASE=A2  PRIMARY_OBSERVATION=4.834s
B_TRUE_DEVICE=YES  CASE=B1  PRIMARY_OBSERVATION=>12s
MARKER_PROPERTY_EFFECT_UNDER_TARGET_PATH=NO
MARKER_PROPERTY_EFFECT_UNDER_TARGET_FIXUP=NO
MARKER_PROPERTY_MAIN_EFFECT=NOT_SUPPORTED
TARGET_FIXUP_MECHANISM_EFFECT=STRONGLY_SUPPORTED
TARGETING_MECHANISM_IS_DOMINANT_CAUSAL_FAMILY=STRONGLY_SUPPORTED
TARGET_MARKER_INTERACTION=NOT_SUPPORTED
Final Gate A=MAINLINE_V2_M5M_A_MARKER_REMOVAL_NO_EFFECT
Final Gate B=MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_SUPPRESSES_4P7S
NO_NEXT_STAGE_EXECUTED=YES
WAIT_FOR_USER_APPROVAL=YES
```

## 20. Candidate A true-device result

Full write-up: `docs/route-b-mainline-v2-m5m-a-target-path-no-marker-control.md`.

L1→A single-variable relation:

```text
boot     exact M5D           held
vendor   M5H board45 DTB0    held
model    Stock exact         held
fragment 1                   held
target   target-path="/"     held
fixups   ABSENT              held
symbols  ABSENT              held
marker   PRESENT → ABSENT   only source semantic delta
runtime  4.837s → 4.834s
```

```text
T_DISAPPEAR_ISO=2026-09-11T11:15:38.641Z
T_REAPPEAR_ISO=2026-09-11T11:15:43.475Z
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=YES
AUTOMATIC_ELAPSED=4.834
MANUAL_RECOVERY=NO
B boots=1
SECOND_B_BOOT_FORBIDDEN=YES
SLOT_A_WRITTEN=NO
ONLY_WRITE=dtbo_b
```

Dumps: pstore 0; minidump/rawdump/logdump UNCHANGED; logfs and oops CHANGED.
oops holds only 2023-09-04 stock Android records
(`OOPS_MAINLINE_EVIDENCE=NO`).

Marker removal under `target-path="/"` does not leave the ~4.7s wall.
A vs L2 (both marker-absent) therefore isolates targeting mechanism:

```text
A   T0/M0  target-path="/"      4.834s
L2  T1/M0  target + __fixups__  >12s
TARGET_FIXUP_MECHANISM_EFFECT under marker-absent  STRONGLY_SUPPORTED
```

Candidate B (`T1/M1`) was the last factorial cell. It is recorded in §22.

## 21. Current B after A (historical, superseded by §22)

After A, Slot B was exact M5D + M5H + M5M-A dtbo. L1 was not restored. B
was READY and waited for a separate approval; it was not auto-run.

## 22. Candidate B true-device result

Full write-up: `docs/route-b-mainline-v2-m5m-b-fixup-with-marker-control.md`.

L2→B single-variable relation:

```text
boot     exact M5D           held
vendor   M5H board45 DTB0    held
model    Stock exact         held
fragment 1                   held
target   mdss_mdp + __fixups__  held
marker   ABSENT → PRESENT   only source semantic delta
runtime  >12s → >12s
```

```text
T_DISAPPEAR_ISO=2026-09-11T11:30:44.602Z
PRIMARY_OBSERVATION=>12s
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO
MANUAL_RECOVERY=YES
MANUAL_RECOVERY_TIME=685s
MANUAL_RECOVERY_TIME_ISO=2026-09-11T11:42:39Z
B boots=1
SECOND_B_BOOT_FORBIDDEN=YES
SLOT_A_WRITTEN=NO
ONLY_WRITE=dtbo_b
```

`MANUAL_RECOVERY_TIME` is not `T_REAPPEAR` / `NATURAL_RETURN_TIME` /
`AUTOMATIC_RETURN_TIME`.

Dumps: pstore 0; minidump/rawdump/logdump UNCHANGED; logfs and oops CHANGED.
oops holds only 2023-09-04 stock Android records
(`OOPS_MAINLINE_EVIDENCE=NO`).

## 23. Complete 2×2 and merged-tree bound

```text
T0/M1  L1  target-path="/"      marker PRESENT  4.837s
T0/M0  A   target-path="/"      marker ABSENT   4.834s
T1/M0  L2  target + __fixups__  marker ABSENT   >12s
T1/M1  B   target + __fixups__  marker PRESENT  >12s
```

```text
MARKER_PROPERTY_EFFECT_UNDER_TARGET_PATH=NO
MARKER_PROPERTY_EFFECT_UNDER_TARGET_FIXUP=NO
MARKER_PROPERTY_MAIN_EFFECT=NOT_SUPPORTED
TARGET_FIXUP_MECHANISM_EFFECT=STRONGLY_SUPPORTED
TARGETING_MECHANISM_IS_DOMINANT_CAUSAL_FAMILY=STRONGLY_SUPPORTED
TARGET_MARKER_INTERACTION=NOT_SUPPORTED
Final Gate=MAINLINE_V2_M5M_B_FIXUP_WITH_MARKER_SUPPRESSES_4P7S
```

A and L2, under standard `fdtoverlay`/libfdt, both merge to byte-identical
exact Stock DTB0
`324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8`
and still differ in runtime (4.834s vs >12s).
`STANDARD_LIBFDT_FINAL_MERGED_TREE_CONTENT` alone cannot explain the
observed split. That does **not** say Xiaomi ABL's final merged tree is the
same, that ABL inspects the overlay before merge, or that ABL does not use
the final DTB.

L1 vs B, with the marker present in both overlay bodies, still category-flips
with targeting mechanism. Combined with A vs L2, this more strongly supports
raw overlay targeting representation / ABL-specific overlay application
mechanics, rather than merged device-configuration content, as the causal
family. Specific ABL source-code behaviour is not claimed.

Do not continue marker research. `/model`, padding, container, and board-id
are already deprioritised.

## 24. Current B and wait

```text
ANDROID_A_RESTORED=YES
CURRENT_B=exact M5D boot + M5H board45 Stock DTB0 vendor + M5M-B dtbo
Candidate A dtbo NOT restored
NEXT=MAINLINE_V2_M5N_TARGETING_MECHANISM_ISOLATION_CI
      split target/fixup family internally:
        target-path property
        target phandle encoding
        __fixups__ node presence
        external symbol string
        placeholder 0xffffffff
        target symbol choice
      find the minimal ABL-compatible targeting representation
NO_NEXT_STAGE_EXECUTED=YES
WAIT_FOR_USER_APPROVAL=YES
```
