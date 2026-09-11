# Route B Mainline V2 — M5L DTBO payload semantics audit (CI only)

Stage id:

```text
MAINLINE_V2_M5L_DTBO_PAYLOAD_SEMANTICS_AUDIT_CI
```

This round is **CI only**. No device operation of any kind was performed. The
exact Stock and M1 inputs, every DT parse, every DTC compilation, every
`fdtoverlay` application, every artifact transformation, every binary diff and
every fail-closed negative test run inside the private GitHub Actions runner.
Nothing OEM-derived leaves private Actions storage.

## 1. Constraints honoured

```text
MEM0_READ_BEFORE_M5L         YES
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
```

Current Slot B is untouched:

```text
M5D boot
+ M5H board45 single Stock DTB0 vendor_boot
+ M5K one-entry Stock-payload dtbo
```

No future true-device control was executed.

## 2. Authoritative DTBO factorial

Held constant across the whole matrix:

```text
boot    exact M5D
vendor  M5H board45 Stock DTB0
```

```text
A  Stock 29-entry table  + exact Stock thyme entry21  ->  >12s    slow
B  Stock 29-entry table  + M1 no-op payload           ->  4.922s  fast (M5J)
C  M1 one-entry table    + M1 no-op payload           ->  4.812s  fast (M5F1)
D  M1 one-entry table    + exact Stock thyme entry21  ->  >12s    slow (M5K)
```

Reading the matrix by variable:

```text
payload held  = Stock thyme entry21 : 29-entry slow, 1-entry slow   -> container irrelevant
payload held  = M1 no-op            : 29-entry fast, 1-entry fast   -> container irrelevant
container held= Stock 29-entry      : Stock slow,  M1 no-op fast
container held= M1 one-entry        : Stock slow,  M1 no-op fast
```

Conclusions:

```text
M1_NOOP_PAYLOAD_SUFFICIENT              YES
M1_NOOP_PAYLOAD_CAUSAL_FAMILY           STRONGLY_SUPPORTED
M1_ONE_ENTRY_CONTAINER_ALONE_SUFFICIENT NO
DTBO_CONTAINER_TABLE_TOPOLOGY           DEPRIORITIZED
```

### 2.1 Why the container is deprioritised

The container hypothesis was that `entry_count` `29 -> 1`, `total_size`
`-> 484949` and the payload relocation to offset 64 were suppressing the 4.7s
return. Cells C and D hold the one-entry container constant and still
reproduce, respectively, the fast and the slow class. Cells A and B hold the
Stock 29-entry table constant and still reproduce both classes. Therefore the
container/table topology flips nothing on its own, and every remaining
question is about the selected overlay payload.

`DTBO_CONTAINER_TABLE_TOPOLOGY` is therefore rejected as the primary cause. It
is **not** claimed to be fully inert: it is only rejected as a *sufficient*
explanatory variable inside this factorial.

## 3. The two authoritative payloads

```text
Stock thyme entry21
  size     484885
  sha256   44ebabe29b0f2a759af0fedcda05674c441465c790f183541164f0721e99bf93
  board-id <45 0>
  compat   qcom,kona-mtp / qcom,kona / qcom,mtp
  fragments 124
  __fixups__ symbols 154
  __symbols__ 386

M1 no-op payload
  size     323
  sha256   37d6855a5930508b0dd349d8ba2bb167f47e415de2b754a7af0fe80d11ee7c96
  board-id <45 0>
  compat   qcom,kona-mtp / qcom,kona / qcom,mtp
  fragments 1
  target-path "/"
  __fixups__ ABSENT
  __symbols__ ABSENT
  marker   qcom,thyme-route-b-noop
```

## 4. What this round does and does not claim

Permitted after M5K:

```text
runtime mainly follows the selected overlay payload
```

Still **not** permitted, and deliberately not claimed by M5L:

```text
target-path="/" is the proven cause
absence of __fixups__ is the proven cause
fragment count is the cause
the no-op marker is the cause
payload size is the cause
padding is the cause
which libfdt entry point ABL fails in
```

M5L therefore decomposes the payload instead of asserting a single cause.

## 5. Payload root property matrix

Requirement: do not compare summaries. Produce a full root property matrix for
both payloads, plus `/chosen`, and flag every ABL-visible selector property
that earlier reports had not listed.

Selector family used (named, not implied):

```text
qcom,board-id  qcom,msm-id  qcom,pmic-id  qcom,pmic-id-size
qcom,platform-id  compatible  model
```

The measured matrix, the `/chosen` matrix and the explicit
`SELECTOR_PROPERTIES_DIFFERING` / `ROOT_PROPERTIES_MISSING_IN_M1` /
`ROOT_PROPERTIES_VALUE_DIFFERENT` sets are produced by
`m5l-payload-root-matrix.txt` in the private artifact. The matrix is decided by
measurement, not by prior knowledge; whatever the audit reports is what drives
the L1 decision below.

## 6. Stock fragment targeting mechanics

Requirement: for each of the 124 Stock fragments, report the target form, the
raw target value, the `__fixups__` symbol if any, the `__overlay__` child and
property counts, local phandle references, and the `__local_fixups__`
dependency. Then aggregate:

```text
STOCK_FRAGMENT_COUNT
STOCK_TARGET_PHANDLE_FRAGMENT_COUNT
STOCK_TARGET_PHANDLE_LOCAL_FRAGMENT_COUNT
STOCK_TARGET_PATH_FRAGMENT_COUNT
STOCK_OTHER_TARGET_FRAGMENT_COUNT
STOCK_FRAGMENTS_WITH_FIXUP_SYMBOL
STOCK_FRAGMENTS_WITHOUT_FIXUP_SYMBOL
```

The point of the exercise: if the overwhelming majority of the Stock fragments
use `target = <phandle> + __fixups__` while the single M1 fragment uses
`target-path = "/"`, then the payload difference is not "no-op vs real
changes" alone — it is also an **overlay targeting and encoding mechanism**
difference, and M5J/M5K cannot separate the two.

### 6.1 How `__fixups__` entries are attributed

A `__fixups__` property name is the unresolved symbol (label) and its value
encodes where the placeholder phandle sits. Two encodings exist in the wild:

```text
STRING_PATH_PROP_INDEX   NUL separated "<node path>:<property>:<index>"
CELL_OFFSET              a list of raw offsets into the overlay blob
```

M5L does not assume either. Three probe overlays (target only, body only, both)
are compiled in the same run with the project's pinned `dtc`, their raw fixup
values are decoded, and the encoding actually produced is the one used for the
OEM payload. In `CELL_OFFSET` mode the offset reference frame is additionally
resolved against a fixed candidate list instead of being assumed. The decision
is recorded as `FIXUP_ENCODING`, with the raw probe values kept as evidence.
Entries that cannot be attributed are counted, never silently dropped.

## 7. Stock overlay generated metadata and fixup classification

Reported:

```text
__fixups__ symbol count
__symbols__ count
__local_fixups__ present / property count / reference count
phandle and linux,phandle property count
```

Every `__fixups__` offset is classified:

```text
TARGET_FIXUP  offset lands on a fragment `target` property
BODY_FIXUP    offset lands inside a fragment __overlay__ body
LOCAL_FIXUP   entry in __local_fixups__ (internal phandle bookkeeping)
```

## 8. M1 no-op exact structure

The complete M1 tree is dumped node by node with every property value, and the
marker location is stated explicitly:

```text
MARKER_PROPERTY                qcom,thyme-route-b-noop
MARKER_HOME_NODE               measured
MARKER_AT_ROOT                 measured
MARKER_IN_OVERLAY_BODY         measured
```

The question "what does the M1 no-op actually modify on the Stock base?" is
answered by applying it: the exact Stock DTB0 plus the M1 payload is merged
with `fdtoverlay`, and the merged tree is compared to the base semantically.
This also serves as the marker audit required by the round.

## 9. Padding / totalsize: downgraded, not promoted

```text
Cell C entry dt_size            323 (self-consistent)
Cell C internal FDT totalsize   323
Cell C slot padding mismatch    none
Cell C runtime                  4.812s -> suppression reproduced
M5J entry dt_size               484885
M5J internal FDT totalsize      323
M5J slot padding                484562 zero bytes
M5J runtime                     4.922s -> suppression reproduced
```

Suppression is reproduced both with and without slot padding, and failure is
reproduced both with and without it. Padding therefore cannot be a *necessary*
condition for either class.

```text
PADDING_OR_DT_SIZE_MISMATCH_AS_NECESSARY_CAUSE  NOT_SUPPORTED
PADDING_CHANGES_BEHAVIOUR                       NOT_EXCLUDED
PADDING_PRIORITY                                P6 (deprioritised)
PADDING_NOT_NEXT_EXPERIMENT                     YES
```

It remains possible that padding perturbs timing or ABL-side behaviour. It is
simply not the explanation of the two failing cells, so it is not the next
shot.

## 10. Payload factor decomposition

```text
P1  ROOT_SELECTOR_METADATA      ABL-visible root selector properties
P2  FRAGMENT_TARGET_MECHANISM   target-path="/" vs target=<phandle>+fixup
P3  OVERLAY_GENERATED_METADATA  __fixups__ / __symbols__ / phandles / local fixups
P4  FRAGMENT_TOPOLOGY           1 vs 124 fragments
P5  APPLIED_OVERLAY_CONTENT     marker-only vs real downstream modifications
P6  PAYLOAD_SIZE / PADDING      size, totalsize, slot padding
```

Priority: **P1**, then **P2/P3**, then **P4/P5**, then **P6**. The order is
data-driven: if the exact audit shows P1 does not exist, L1 is skipped and the
round moves straight to P2/P3.

## 11. L1 candidate — selector-matched no-op

Built **only if** the audit finds a real ABL-visible selector difference.

```text
container   one-entry, entry_count 1, id/rev/custom zero, dt_offset 64
payload     M1 no-op semantics preserved:
            1 fragment, target-path="/", marker body,
            no __fixups__, no __symbols__,
            root selector metadata patched to the exact Stock entry21 values
```

Hard rules:

```text
L1_CHANGES_FRAGMENT_TARGET_MECHANISM  NO
L1_CHANGES_NOOP_SEMANTICS             NO
```

L1 is the smaller of the two changes, so if it exists it is tested first. If
L1 does not exist, `SKIP_L1_SELECTOR_CONTROL=YES` and no meaningless artifact
is produced.

## 12. L2 candidate — Stock-style target/fixup minimal no-op

This is the round's most important construction.

Goal: a **one-fragment, semantically no-op** payload that nevertheless uses the
Stock overlay **targeting and encoding mechanics**.

Rules applied:

```text
no target-path="/"
target = <&symbol>, resolved through the DTC overlay fixup mechanism
__fixups__ must be present
the overlay body must be empty
no marker, no status, no compatible, no reg, no device property in the body
```

The target symbol is **selected from the exact Stock entry21**, not invented:
the audit enumerates the Stock fragments whose `target` is an external phandle,
requires the symbol to exist in the base DTB0 `__symbols__`, requires no
`__local_fixups__` dependency, and then picks the simplest candidate by
overlay child count, overlay property count and fragment index. The chosen
symbol, its base path and the full ranked candidate list are recorded.

The DTS is generated programmatically and compiled by the project's pinned
`dtc` in Actions. No DTS wording is hand-assumed.

Root selector metadata is emitted from the exact Stock entry21 values, so L2
isolates the encoding/target mechanism rather than a selector difference.

### 12.1 L2 semantic no-op gate

`fdtoverlay` of the exact Stock DTB0 plus the L2 payload must succeed, and the
merged tree must be compared to the base **semantically**:

allowed:

```text
phandle / linux,phandle numbering
generated bookkeeping nodes and properties
(__symbols__, __fixups__, __local_fixups__, retained /fragment@N subtrees)
```

not allowed:

```text
status / reg / interrupt* / clock* / *-supply / regulator-* change
any added or removed device property
any added or removed device node
new marker property
device enable or disable
```

`L2_SEMANTIC_NOOP_CONFIRMED` is measured, never asserted.

### 12.2 L2 readiness

```text
L2_READY requires ALL of:
  fdtoverlay PASS
  measured semantic no-op
  exact Stock root selector metadata
  one-entry container identity preserved
  binary validation of the normalized artifact
  fail-closed negative controls PASS
```

`fdtoverlay PASS` alone is explicitly **not** evidence: M5J already proved
that a `fdtoverlay`-clean payload can be rejected by Xiaomi ABL.

## 13. Candidate container and normalized artifact

Both candidates use the M1 one-entry container, because M5K proved the
one-entry container alone is not sufficient — keeping it constant removes an
irrelevant variable.

```text
entry_count     1
id/rev/custom   all zero
payload offset  64
entry dt_size   exact candidate FDT size
total_size      64 + candidate payload size
```

The future true-device artifact is a normalized full partition:

```text
size 33554432
[0, prefix_end)          one-entry candidate DTBO
[prefix_end, 33554432)   exact Stock dtbo.img at the same offset to EOF
```

reported with `ACTIVE_PREFIX_SIZE`, `ACTIVE_PREFIX_SHA256`,
`FULL_ARTIFACT_SHA256`, `STOCK_TAIL_OFFSET`, `STOCK_TAIL_SHA256`.

The normalized tail is physical-partition determinism only. Under DTBO
`total_size` semantics it is not part of the active one-entry image.

Reference for comparison is Cell D:

```text
one-entry container + exact Stock payload          -> >12s
one-entry container + minimal Stock-style no-op    -> measured in a future round
```

That comparison is what asks the real question: *can an ABL-acceptable minimal
no-op overlay be constructed at all?* — which matters more than the paused
143-alias mapping.

## 14. Fail-closed controls

At minimum:

```text
unmutated L1 / L2 / container accepted
wrong selector                       -> rejected
wrong target symbol                  -> fdtoverlay rejected
missing __fixups__                   -> design gate rejected
non-empty semantic overlay           -> semantic-noop gate rejected
non-empty overlay body               -> design gate rejected
invalid FDT                          -> parser rejected
wrong entry dt_size                  -> rejected
wrong total_size                     -> rejected
wrong dt_offset                      -> rejected
wrong entry_count                    -> rejected
non-zero entry metadata              -> rejected
wrong tail                           -> rejected
wrong prefix                         -> rejected
wrong full artifact size             -> rejected
```

`FAIL_CLOSED` is `PASS` only when every control behaves.

## 15. Pre-registered interpretation

### 15.1 L1 (only if it exists)

```text
L1 >12s   -> ROOT_SELECTOR_METADATA_CAUSAL = STRONGLY_SUPPORTED
             no need to test L2 first
L1 ~4.7s  -> selector metadata is not sufficient, proceed to L2
```

### 15.2 L2

```text
L2 PRIMARY_OBSERVATION >12s
  -> STOCK_STYLE_MINIMAL_NOOP_COMPATIBLE = STRONGLY_SUPPORTED
  -> the M1 no-op failure is not about no-op semantics
  -> it is the M1 payload encoding / target-path / missing fixup-style
     overlay metadata causal family
  -> a realistic Mainline bridge exists:
     Mainline base + ABL-compatible minimal no-op DTBO

L2 ~4.3-5.3s
  -> Stock-style target/fixup encoding is still not sufficient
  -> move toward fragment topology and required Stock overlay content
  -> do NOT immediately fall back to the 143-alias mapping
```

### 15.3 Marker

The marker is audited for whether it reaches the merged tree, and for whether
it is the only extra property relative to a minimal overlay. It is not promoted
to a device test unless it is the sole distinguishing property.

### 15.4 Board-id

`qcom,board-id` is **not** re-tested this round. M5H already proved that a base
`board-id` `0 -> 45` change alone does not flip the 4.7s return, and both
payloads already carry `<45 0>`.

## 16. Evidence boundary

```text
fdtoverlay PASS  == standard libfdt compatibility
fdtoverlay PASS  != Xiaomi ABL accepts the payload
```

This boundary is unchanged from M5J and is restated in every report this
round.

## 17. Single recommended next control

Exactly one of:

```text
L1_SELECTOR_MATCHED_NOOP
L2_STOCK_STYLE_MINIMAL_NOOP
NONE_NEEDS_REFINEMENT
```

Selection rule:

```text
P1 selector difference exists and L1 READY  -> L1 first
selectors already equivalent                -> L2 first
```

Several payloads are never tested on device at once.

## 18. Not claimed

- no device operation, no flash, no slot change, no B boot this round
- structural `dtc` / `fdtoverlay` validation is not Xiaomi ABL evidence
- the container topology is rejected as the primary cause, not proven inert
- the M1 no-op marker is not promoted without measurement
- padding is not excluded as a perturbation, only as a necessary cause
- no claim is made about which libfdt entry point fails inside ABL
