# Route B Mainline V2 M5I — Mainline base overlay compatibility

Status: CI implementation prepared; private GHA result pending. No device operation is authorized.

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
