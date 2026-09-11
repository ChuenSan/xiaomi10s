# Route B Mainline V2 M5I — Mainline base overlay compatibility

Status: CI complete. Final gate: `M5I_SYMBOLIZED_OVERLAY_STILL_INCOMPATIBLE`.
No candidate was generated and no device operation is authorized.

## Question

The M5H auxiliary audit found:

```text
Stock DTB0 + Stock DTBO entry21       fdtoverlay PASS
historical M1 ABL DTB + same entry21  FDT_ERR_NOTFOUND
Stock DTB0 __symbols__                1672
historical M1 __symbols__             ABSENT (0)
entry21 __fixups__ symbols            154
historical M1 resolved/missing        0/154
```

`154/154 missing` does **not** prove that 154 corresponding hardware nodes are
absent. Standard overlay fixups resolve names through the base DTB
`/__symbols__` table. Because the historical M1 binary has no table at all,
every fixup fails before node-level equivalence can be established. M5I first
separates build-metadata absence from source/tree incompatibility.

## Frozen experiment

The baseline is the exact source genealogy that produced Cell B's M1 DTB, not
the current thyme DTS:

```text
public source commit  ff70e7dc807399e68fbebcecab9e6eb23c911d65
Linux submodule       8b73de7da85fde281a385e0b26eda9bffd3ca477 (6.6.156)
patch queue SHA256    d470701d58d62bf10b96adb4dbf0c639945afccd45d4d3f039e8051e7aaaf1b5
config fragment SHA   09d635f7f80f73737e2142adfc181234e21bbd3ea54da92f2f264ddefaf5d0aa
build target          dtbs
DTS target            qcom/sm8250-xiaomi-thyme.dtb
MAKEARGS              O=out ARCH=arm64 LLVM=1
historical runner     ubuntu-24.04 image 20260831.293.1
historical clang      Ubuntu clang 18.1.3
historical system DTC 1.7.0-2build1 / DTC 1.7.0
artifact compiler     Linux in-tree scripts/dtc from the pinned source
```

The private workflow recreates the historical configuration and normal `dtbs`
build first. It must reproduce both binaries byte-for-byte:

```text
raw  a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
ABL  cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0
```

The ABL form uses the historical `fdtput -t u` packaging operation and retains:

```text
qcom,msm-id   <356 0x20001>
qcom,board-id <45 0>
compatible    xiaomi,thyme / qcom,sm8250
```

Any baseline mismatch stops the experiment as
`M5I_M1_SOURCE_REPRODUCTION_FAILED`; no control artifact is generated.

## Overlay-compatible build mode

Inspection of the pinned kernel build system found its supported interface in
`scripts/Makefile.lib`: `DTC_FLAGS` is passed to the in-tree DTC, with per-target
flags appended by `DTC_FLAGS_$(basetarget)`. M5I therefore builds a second,
separate output tree with the same source, configuration, target and toolchain,
changing only:

```text
DTC_FLAGS=-@
```

The result is called `SYMBOLIZED_BASE_BUILD_MODE` or
`OVERLAY_COMPATIBLE_DTC_METADATA`. It is not called a symbol-table-only change:
DTC can add `__symbols__`, `phandle`, `linux,phandle`, change FDT block offsets,
totalsize and serialization.

The artifact is built through the kernel's normal DT build path. M5I does not
decompile/recompile the historical DTB and does not edit DTS source or inject
manual aliases.

## Audits and controls

Private GHA records raw/ABL SHA256 and size, totalsize, synthetic nodes,
`__symbols__`, phandle counts and the full binary changed ranges. After excluding
DTC-generated metadata (`__symbols__`, fixup nodes, `phandle` and
`linux,phandle`), it requires equality of the complete source node/property
tree and explicit equality of model, compatible, memory, chosen,
reserved-memory, status, reg, interrupts, clocks and regulator properties.

The same DTC 1.7.0 `fdtoverlay` implementation and exact Stock entry21 run:

```text
Control A  exact Stock DTB0          + entry21
Control B  exact historical M1 ABL   + entry21
Test C     symbolized historical M1  + entry21
```

The 154 fixups are recalculated against both M1 bases. An exact CPP-preprocessed
historical M1 DTS is also scanned for node labels, distinguishing labels present
in source from downstream-only names. If Test C still fails, CI emits a
conservative A/B/C/D incompatibility matrix and does not create aliases.

If Test C passes, the merged DTB must parse and round-trip, have unique
phandles, no remaining fixup nodes or dangling symbol targets, and structurally
materialize all overlay fragments. This proves standard libfdt compatibility
only; it does not prove Xiaomi ABL uses the same path.

## Conditional private candidate

Only after baseline reproduction and Test C pass may private GHA package:

```text
M5I_V_SYMBOLIZED_MAINLINE_DTB_VENDOR_BOOT
format          vendor_boot v3
DTB topology    one DTB
DTB offset      8192
vendor ramdisk  exact M1/Stock value
DTB payload     symbolized historical M1 ABL DTB
board-id        <45 0>
msm-id          <356 0x20001>
```

All header fields except derived `dtb_size` remain unchanged. CI reports exact
artifact extent, DTB end, padding, changed ranges and the SHA256 of exact Stock
`vendor_boot` from that extent to EOF for a future prefix/tail readback gate.
Merged Stock-derived DTBs and hybrid `vendor_boot` images remain private.

## Outputs

```text
m5i-m1-reproduction.txt
m5i-symbolized-dtb-report.txt
m5i-symbol-delta.txt
m5i-fixup-coverage.txt
m5i-overlay-apply-report.txt
m5i-source-label-coverage.txt
m5i-known-symbol-audit.txt
m5i-merged-tree-report.txt                 (PASS only)
m5i-candidate-diff-map.txt                 (candidate only)
m5i-remaining-incompatibility-matrix.txt   (FAIL only)
SHA256SUMS
```

## CI result

Private GHA run `34572191475` passed its bounded audit workflow. The public
source audit run `34572156696` also passed. The private wrapper commit is
`d54fbb7abd7f335fc29a14f5cdfa8b8198fa2533`; the audited public analyzer commit
is `621f25f1f0575d9bdc5ba1e8aceef665a43f69b2`.

### Exact M1 reproduction

The historical normal build and historical ABL packaging operation reproduced
both artifacts byte-for-byte:

```text
M5I_BASELINE_M1_RAW_DTB_REPRODUCED=YES
raw size/SHA       105960  a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
M5I_BASELINE_M1_ABL_DTB_REPRODUCED=YES
ABL size/SHA       106026  cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0
EXACT_HISTORICAL_ARTIFACT_BYTES_MATCH=YES
```

The baseline and symbolized output directories produced the same final config
SHA256:

```text
4ae37ddc7831151b35bb937e2fbc8bf101cac54a5c09b0f6cba3a673b8a3da49
```

Their independently built in-tree DTC executables were also identical:

```text
3d96e33754a9a9ff6b53f090d78422815c26e0d16906846323de1454a6d46dba
```

### Overlay-compatible M1 DTB

```text
build mode                  DTC_FLAGS=-@ through normal kernel dtbs path
symbolized raw size/SHA     143886  aa3a90b05d3bb12e743abbde4d01c9ac856b3484fb1d90edc4769de1b9d7f024
symbolized ABL size/SHA     143952  a0e332bc3a558eaef23ca123b317ae092c5f8659884d61b6693c1945b774a41c
raw size/totalsize delta    +37926 / +37926
__symbols__                 present, 527 entries
phandle properties          242 -> 527
linux,phandle               0 -> 0
__local_fixups__            absent
other synthetic nodes       /__symbols__
qcom,msm-id                 <356 0x20001>
qcom,board-id               <45 0>
compatible                  xiaomi,thyme / qcom,sm8250
```

This is not a symbol-table-only delta: it adds 285 `phandle` properties as well
as 527 symbols and changes serialization/offsets. The private
`m5i-symbol-delta.txt` contains the complete changed-range map.

All semantic invariants passed after excluding generated overlay metadata:

```text
complete raw tree     PASS
complete ABL tree     PASS
model/compatible      PASS
memory/chosen         PASS
reserved-memory       PASS
status/reg            PASS
interrupts/clocks     PASS
regulators            PASS
source node set       PASS
```

### Overlay result and fixup coverage

All three cases used system DTC/fdtoverlay 1.7.0 and exact Stock entry21:

```text
Stock DTB0 + Stock entry21          PASS (rc=0)
historical M1 ABL + Stock entry21   FAIL, FDT_ERR_NOTFOUND
symbolized M1 ABL + Stock entry21   FAIL, FDT_ERR_NOTFOUND
```

The symbolized build changed the fixup diagnosis, but not enough to make the
overlay applicable:

```text
Stock entry21 fixups                154
historical M1 resolved/missing      0 / 154
symbolized base symbols             527
symbolized resolved/missing         11 / 143
resolved with different Stock path  11
Stock-side unresolved               0
source labels present/absent        11 / 143
```

The 11 automatically exposed labels are:

```text
intc mdss_dsi0 mdss_dsi1 mdss_mdp pcie1 pdc sdhc_2 soc spmi_bus tlmm xbl_aop_mem
```

Therefore the old `154/154 missing` result contained an 11-symbol build-mode
artifact, but its dominant cause was not metadata absence: 143 Stock fixup
labels are absent from the exact preprocessed historical Mainline source. Some
of those nodes still have differently named Mainline equivalents, so this is a
label/naming/tree incompatibility result, not proof that 143 hardware blocks
are absent.

The conservative remaining matrix is:

```text
A  same label + compatible-equivalent node        4
B  different label + strong equivalent node       1
C  node/topology candidate, not equivalent enough 17
D  no automated Mainline equivalent               132
```

No alias was generated. The only current class-B high-confidence alias research
candidate is `ufshc_mem`:

```text
Stock     /soc/ufshc@1d84000       qcom,ufshc
Mainline  /soc@0/ufshc@1d84000     qcom,sm8250-ufshc / qcom,ufshc / jedec,ufs-2.0
status    okay
```

Selected required examples:

| Symbol | Stock DTB path | Mainline label/path or conservative candidate | Result |
|---|---|---|---|
| `firmware` | `/firmware` | path exists but no source label | C / medium |
| `soc` | `/soc` | label `soc` -> `/soc@0` | A / medium |
| `intc` | `/soc/interrupt-controller@17a00000` | `/soc@0/interrupt-controller@17a00000` | A / high |
| `pdc` | `/soc/interrupt-controller@b220000` | `/soc@0/interrupt-controller@b220000` | C / low |
| `tlmm` | `/soc/pinctrl@f000000` | `/soc@0/pinctrl@f100000` | C / low |
| `ufshc_mem` | `/soc/ufshc@1d84000` | `/soc@0/ufshc@1d84000`, different label | B / high |
| `qupv3_se11_i2c` | `/soc/i2c@a8c000` | probable `/soc@0/geniqup@ac0000/i2c@a94000`, disabled | C / low |
| `cam_cci0` | `/soc/qcom,cci@ac4f000` | none | D |
| `aw8697_gpio_reset` | `/soc/pinctrl@f000000/aw8697_gpio_reset` | none | D |
| `clock_rpmh` | `/soc/rsc@18200000/qcom,rpmhclk` | none | D |

Stock source paths were unavailable in the private inputs; the report marks
them `NOT_AVAILABLE_BINARY_DERIVED` rather than inventing source genealogy.

### Candidate decision

Test C failed, so CI correctly produced neither a merged-tree report nor a
hybrid vendor_boot candidate:

```text
OVERLAY_BUILD_METADATA_SUFFICIENT_FOR_LIBFDT_COMPAT=NO
CANDIDATE_GENERATED=NO
EXPECTED_STOCK_VENDOR_TAIL_SHA_FROM_M5I_EXTENT=NOT_APPLICABLE
FAIL_CLOSED_TESTS=PASS
READY_FOR_MAINLINE_V2_M5I_SYMBOLIZED_BASE_CONTROL=NO
FINAL_GATE=M5I_SYMBOLIZED_OVERLAY_STILL_INCOMPATIBLE
```

No future true-device M5I stage is available from this result. The next bounded
CI investigation should start from the incompatibility matrix, validate only
high-confidence semantic equivalents, and must not synthesize all 143 missing
labels or fake downstream-only hardware nodes.

## Boundaries

```text
MEM0_READ_BEFORE_M5I=YES
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
SET_ACTIVE=NO
B_BOOT=NO
SLOT_A_WRITE=FORBIDDEN
REFERENCE_REPOS_MODIFIED=NO
DTBO_TRACK_FROZEN=YES
FUTURE_TRUE_DEVICE_AUTO_EXEC=NO
```

Current B remains exact M5D `boot_b` + M5H board45 Stock DTB0 `vendor_boot_b` +
exact Stock `dtbo_b`.

## Gates

Exactly one result is recorded:

```text
READY_FOR_MAINLINE_V2_M5I_SYMBOLIZED_BASE_CONTROL
M5I_M1_SOURCE_REPRODUCTION_FAILED
M5I_SYMBOLIZED_OVERLAY_STILL_INCOMPATIBLE
M5I_SYMBOLIZED_BUILD_SEMANTICS_CHANGED
M5I_CANDIDATE_NOT_SAFE
```

A ready candidate still requires a separate explicit approval before any future
device operation. No future M5I true-device phase starts automatically.
