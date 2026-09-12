# Route R3 — Runtime DTB Completion (MAINLINE_V2_R3_RUNTIME_DTB_COMPLETION_CI)

Status: **R3_RUNTIME_DTB_COMPLETED** (CI-proven, no device operation)
Date: 2026-09-12
Public HEAD: `a98596cc9be8fe983268359e284e48be55c56a0e` (route-b-v3)

Standing constraints (unchanged, verbatim):
`LOCAL_BUILD=NO LOCAL_VALIDATION=NO LOCAL_VALIDATOR=NO LOCAL_SOURCE_GATE=NO LOCAL_ACTIONLINT=NO LOCAL_BINARY_VALIDATION=NO`
All DTB build, dtc validation, binary parsing validation, artifact generation:
GitHub Actions only. Device: Android A read-only evidence capture only.
`DEVICE_REBOOT=NO PARTITION_WRITES=0 SLOT_A_WRITTEN=NO`.
Current B = M5D + M5H + M5M-B unchanged. M5N FROZEN. USB FROZEN.
P1 true-device entry probe: design only, not advanced.

---

## 1. Scope

Close three R3 items for thyme (Xiaomi Mi 10S, SM8250): (1) actual RAM banks,
(2) runtime reserved-memory, (3) a Linux-runtime-only DTB (RT-D) that is
self-contained for early Linux boot. The R3 trampoline does not consume the
ABL-provided x0 DTB, so the entry state must carry its own memory description;
the M1 raw DTB cannot serve that role (section 2).

## 2. Why the M1 raw DTB cannot serve

M1 raw DTB (SHA `a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40`)
deliberately leaves `/memory` as a placeholder (`reg = <0x0 0x80000000 0x0 0x0>`,
size 0): RAM was unproven, and CI gate `P1_DTB_FALSE_SELF_CONTAINED` forced both
M1 DTBs to be non-self-contained. It relies on ABL patching at boot, which the
R3 trampoline path does not have. This stage keeps RT-A at the placeholder
(`M1_RUNTIME_DTB_SELF_CONTAINED=NO`) and makes RT-D self-contained from
byte-verified runtime evidence.

## 3. Capture methodology (read-only, slot A)

Source device: Stock Android A slot, MIUI `stock-V14.0.6.0.TGACNXM`,
`ro.boot.slot_suffix=_a`, `sys.boot_completed=1`, root adb. Capture script
`scripts/r3-p1/r3-runtime-capture.sh`: baseline checks → evidence dump →
post-capture re-check. Every read is `adb exec-out su -c` (binary-safe, no CRLF
injection). After capture: slot `_a`, boot_completed=1 —
`DEVICE_REBOOT=NO PARTITION_WRITES=0 SLOT_A_WRITTEN=NO`.

Key fix in this stage: toybox tar silently truncates archives built from sysfs
(first capture produced 18 of ~32k entries, `/memory/reg` missing). The capture
now emits one `===FILE <path>` marker plus base64 per file — 32,249 files, all
present, single-file failures degrade to empty props instead of aborting.

Private bundle `stock-android-a-runtime-context-20260912-b` (Release asset
`thyme-stock-android-a-runtime-evidence-20260912-b.tar.gz`,
SHA256 `cc428656bd0dd0b31ec8ecefdc9799b6e5cf0b9869d44b714ba7fa8925b10cf0`,
flat ustar layout — the first v2 packaging nested a `bundle/` directory and
was repacked). OEM binaries stay private; only the numeric summary
`scripts/r3-p1/dts/thyme-runtime-memory-evidence.json` is mirrored public.

## 4. Runtime FDT availability

`RUNTIME_FDT_AVAILABLE=YES`. Both sources captured in the same boot:

- `/sys/firmware/fdt` raw blob: 934,898 bytes,
  SHA256 `7e9e6f8c50b428baf410220d71b05eac77dce56c9b0f4284138271cefd6e700f`
  (identical across capture -a and -b: same boot session, stable).
- Runtime OF tree `/sys/firmware/devicetree/base` — the tree the Stock kernel
  actually unflattened and serves — per-file base64 dump,
  SHA256 `26ef1ff27dfd1163e2739b3aca46bc2340a23e8729dd33d66bc1b7499d44a832`.

The OF tree is the PRIMARY evidence source; the raw blob contributes only the
header and memreserve table (section 9).

## 5. ABL runtime FDT blob forensics (malformed, documented, not trusted)

The raw blob fails modern tooling, independently confirmed:

- `dtc -I dtb -O dts`: `FATAL ERROR: Invalid opcode word 00000000 in device
  tree blob` (recorded as DTC_RUNTIME_FDT=FAIL evidence, private run logs).
- Header: magic ok, version 17, totalsize field 0xE3ED6 (933,590) < file size
  934,898; `size_dt_struct` = 860,028 overlaps the strings block by 64 bytes.
- Lenient structure walk dies at struct-relative offset 0x370 (inside
  `/aliases`), consistent with a 1-byte misalignment; `/memory` is not reached
  before the stop, so blob-vs-livetree reg comparison is reported as
  unavailable (`verdict=LIVETREE_PRIMARY`, walk truncated).
- memreserve table at [0x28, 0x38) holds exactly one `(0,0)` entry: zero real
  entries, properly terminated (`FDT_MEMRESERVE_ENTRIES=0 terminated=True`).

How the Stock 4.19 kernel accepted this blob is an open question (possible
libfdt-version-tolerant layout or post-boot in-place modification of the
shared DTB memory). It does not block R3: the unflattened tree is fully
readable and internally consistent, and every number used downstream is taken
from it, never from the blob.

## 6. /memory/reg decode (big-endian cells, parsed in GHA)

`/sys/firmware/devicetree/base/memory/reg`: 48 bytes,
SHA256 `daa111a2dbed74ff6aeb6234ea0c3fa64523965c23689a4753349dad8c9eb10a`,
12 cells (root `#address-cells=2`, `#size-cells=2`), 3 banks:

| bank | base | size | end |
|---|---|---|---|
| 0 | 0x0_80000000 | 0x0_39900000 | 0x0_B98FFFFF |
| 1 | 0x0_C0000000 | 0x1_40000000 | 0x1_FFFFFFFF |
| 2 | 0x2_00000000 | 0x1_80000000 | 0x3_7FFFFFFF |

Total described: 0x2F9900000 = 12,477,440 kB = 11.899 GiB (12 GB class
device; the 0xB9900000–0xC0000000 DDR hole below is ABL-excluded).

Notation correction (2026-09-12, see `route-r3-entry-state-probe-ci.md`):
bank 1 base was previously mis-notated here as `0x1_C0000000` (report-only
error — the JSON, DTS, and built DTB always encoded `0x0_C0000000` =
0xC0000000 with size 0x140000000, end-exclusive 0x200000000).

## 7. /proc/iomem cross-check

Seven `System RAM` regions, all fully covered by the union of the three banks,
zero orphans:

```
80894000-808fffff   85e00000-861fffff   8681c000-868fffff
92700000-b03fffff   b1400000-b98fffff   c0000000-ffbfffff
ffc20000-37fffffff
```

`ffc20000-37fffffff` spans banks 1 and 2 (contiguous at 0x200000000): the
kernel merges contiguous multi-bank RAM into one resource, so orphan
detection must use union coverage, not per-bank containment (this exact case
was a gate false-positive during bring-up and is now fixture-locked).

Kernel code `a0080000-a29fffff`: base mod 2 MiB = 0x80000 —
`LOAD_ALIGNMENT_SUPPORTING_EVIDENCE_ONLY` for the S mod 2M entry contract.
Not System RAM (ABL-hidden DDR, kernel never maps it): `b9900000-c0000000`
(108 MiB) and `ffc00000-ffc1ffff` (128 KiB). RT-D reproduces Stock behavior
by simply not describing them.

## 8. /proc/meminfo sanity

MemTotal 11,875,576 kB vs banks 12,477,440 kB → headroom 4.82% (< 40% gate).
MemFree 4,426,076 kB, MemAvailable 8,977,640 kB, CmaTotal 356,352 kB.
kB-vs-kB units (an earlier kB-vs-bytes comparison was a fixture bug, fixed).

## 9. FDT memreserve table

Raw blob memreserve: 0 entries, terminated (section 5). All early carveouts
are `/reserved-memory` nodes, which the RT-D replicates explicitly (section 11).

## 10. memory sysfs fallback and dmesg

`/sys/devices/system/memory`: block_size absent, 0 blocks — the Stock kernel
has no memory hotplug (`CONFIG_MEMORY_HOTPLUG=n`), so the sysfs sector-size
fallback is unusable (`usable=False`). dmesg ring buffer has wrapped (boot-time
`Memory:` line unrecoverable; pstore empty) — recorded, not blocking: iomem +
MemTotal + runtime OF tree are sufficient corroboration.

## 11. Runtime reserved-memory map (LEVEL 1 evidence)

22 static regions (explicit `reg` in the runtime tree), 349,184 KiB
(0x155B0000) total; 12 dynamic containers without `reg` (adsp_region,
cdsp_region, cnss_wlan_region, mailbox_region, mem_dump_region, linux,cma,
qseecom_region, qseecom_ta_region, sdsp_region, secure_display_region,
sp_region, user_contig_region) need no DT entries for early boot.

| region | base | size | flags |
|---|---|---|---|
| hyp_region | 0x80000000 | 0x600000 | no-map |
| xbl_aop_region | 0x80600000 | 0x260000 | no-map |
| cmd-db (reserved-memory@80860000) | 0x80860000 | 0x20000 | no-map, qcom,cmd-db |
| res_xbl_uefi_log_region | 0x80880000 | 0x14000 | no-map, removed-dma-pool |
| smem_region | 0x80900000 | 0x200000 | no-map |
| removed_region | 0x80b00000 | 0x5300000 | no-map |
| pil_camera_region | 0x86200000 | 0x500000 | no-map, removed-dma-pool |
| pil_wlan_fw_region | 0x86700000 | 0x100000 | no-map, removed-dma-pool |
| pil_ipa_fw_region | 0x86800000 | 0x10000 | no-map, removed-dma-pool |
| pil_ipa_gsi_region | 0x86810000 | 0xA000 | no-map, removed-dma-pool |
| pil_gpu_region | 0x8681a000 | 0x2000 | no-map, removed-dma-pool |
| pil_npu_region | 0x86900000 | 0x500000 | no-map, removed-dma-pool |
| pil_video_region | 0x86e00000 | 0x500000 | no-map, removed-dma-pool |
| pil_cvp_region | 0x87300000 | 0x500000 | no-map, removed-dma-pool |
| pil_cdsp_region | 0x87800000 | 0x1400000 | no-map, removed-dma-pool |
| pil_slpi_region | 0x88c00000 | 0x2f00000 | no-map, removed-dma-pool |
| pil_adsp_region | 0x8bb00000 | 0x2500000 | no-map, removed-dma-pool |
| pil_spss_region | 0x8e000000 | 0x100000 | no-map, removed-dma-pool |
| cdsp_secure_heap | 0x8e100000 | 0x4600000 | no-map, removed-dma-pool |
| cont_splash_region | 0x9c000000 | 0x2300000 | (unprotected in runtime tree) |
| dfps_data_region | 0x9e300000 | 0x100000 | (unprotected in runtime tree) |
| disp_rdump_region | 0xb0400000 | 0x1000000 | no-map, removed-dma-pool |

Every static region lies inside a RAM bank. RT-D marks cont-splash/dfps
no-map (safer for early boot than the runtime tree's unprotected form);
base/size are byte-identical.

## 12. Stock downstream / DTB0 comparison (ABL mutations proven)

Stock DTB0 (vendor_boot @8192, 540,195 bytes,
SHA256 `324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8`)
ships `/memory` = [[0, 0]] — a placeholder ABL patches at boot. Runtime
mutations proven by direct comparison: `xbl_aop` 0x80700000+0x160000 (DTB0) →
0x80600000+0x260000 (runtime); `disp_rdump` reg moved; bootargs fully
rewritten. Mainline `sm8250.dtsi` defaults differ from this device's runtime
map in the same five regions RT-D already deletes and re-adds: xbl_aop,
slpi (0x1500000 → 0x2f00000), adsp (0x8a100000+0x1d00000 → 0x8bb00000+0x2500000),
spss (0x8be00000 → 0x8e000000), cdsp_secure_heap (0x8bf00000 → 0x8e100000).
Conclusion: only the runtime values are authoritative; the RT-D uses exactly
those.

## 13. RAM evidence matrix (per bank)

| bank | base | size | iomem status |
|---|---|---|---|
| 0 | 0x80000000 | 0x39900000 | CONFIRMED (5 System RAM regions fully inside) |
| 1 | 0x200000000 | 0x180000000 | SUPPORTED (spanning merged resource) |
| 2 | 0xC0000000 | 0x140000000 | SUPPORTED (one region fully inside + spanning) |

Banks are non-overlapping (gate-enforced). Union coverage of all System RAM
is exact; meminfo sanity passes; no orphan regions. Bank 0 is directly
confirmed by fully-contained iomem regions; banks 1–2 are corroborated by the
contiguous spanning resource plus MemTotal agreement. No evidence source
disagrees with any bank boundary.

## 14. Selected banks and reserved set for RT-D

Selected `/memory`: exactly the three runtime banks, ascending:
`<0x0 0x80000000 0x0 0x39900000>`, `<0x0 0xc0000000 0x1 0x40000000>`,
`<0x2 0x0 0x1 0x80000000>`. Selected reserved-memory: the 22 static runtime
regions of section 11 — 18 carried by mainline `sm8250.dtsi` (five re-pinned
to runtime addresses) plus 4 device-specific additions (xbl-uefi-log,
cont-splash, dfps-data, disp-rdump). Nothing invented, nothing guessed: every
number traces to the runtime OF tree and cross-checks in sections 7–8.

## 15. RT-D architecture and delta

`scripts/r3-p1/dts/sm8250-xiaomi-thyme-runtime.dts`
(SHA256 `5c054b025ae8de94dd1520a76f31cab098de5970d7cef1bdb64756f8c25b0acc`)
includes the thyme board DTS and changes exactly: `/memory` filled with the
verified banks; `/chosen` bootargs `rdinit=/init panic=5 loglevel=7` +
stdout-path; five `/delete-node/` + re-adds at runtime addresses; four added
carveouts. ABL-facing msm-id/board-id/__symbols__ intentionally absent.
Delta vs RT-A (M1): RAM map filled from evidence instead of placeholder; RT-A
stays at the placeholder by design.

Validated artifact: RT-D DTB SHA256
`4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327`,
144,593 bytes, `R3_RUNTIME_DTB_SELF_CONTAINED=YES` — two independent CI
builds (P1 contract workflow and RT-D completion workflow) produced the
byte-identical DTB.

## 16. GHA validation pipeline (all green, GHA only)

Private (OEM inputs never leave it): run 34672184547
(`r3-runtime-dtb-evidence.yml`) — bundle SHA verify, Stock DTB0 extraction,
dtc forensic probe, parser `fixture-selfcheck` + `parse` with fail-closed
gates, numeric JSON artifact.

Public (`ChuenSan/xiaomi10s`, branch route-b-v3):

- `thyme-r3-p1-linux-boot-contract` runs 34672832279 and 34673255508:
  source gate (now evidence-conditional), prototype, DTB audits —
  `RT_D_RUNTIME_DTB_SELF_CONTAINED=YES`, `RT_D_RUNTIME_DTB_BANKS_MISMATCH`
  gate armed, `M1_RUNTIME_DTB_SELF_CONTAINED=NO`.
- `thyme-r3-runtime-dtb-completion` run 34673255565 (new workflow):
  parser + validator fixture selfchecks, RT-D build, and fail-closed gates —
  `R3_RUNTIME_DTB_RAM_MAP_MATCH=YES`,
  `R3_RUNTIME_DTB_RESERVED_COMPLETE=YES regions=22`,
  `R3_RUNTIME_DTB_GATES=PASS`.

Gate set enforced by `scripts/r3-p1/r3-runtime-dtb.py`: RAM banks equal
evidence exactly; every reserved region inside a RAM bank and protected
(no-map/reusable/compatible); no reserved overlaps; reserved set equals the
evidence static set (no missing, no extra); evidence sanitization
(androidboot.* redacted except slot_suffix); strict FDT structure walk.
`dtbs_check` is not applicable: the thyme board DTS is not upstream and the
overlay carries vendor bindings; structural gates above substitute.

Failure chain fixed on the way (all fixture-locked now): toybox tar sysfs
truncation → per-file base64 dump; nested bundle directory → flat repack;
per-bank orphan false positive → union coverage; two-space iomem indent from
the su/toybox path → depth fix; bytes-in-JSON fixture → fresh python fixtures.

## 17. Evidence provenance and sensitive-data policy

Public numeric summary:
`scripts/r3-p1/dts/thyme-runtime-memory-evidence.json`
(SHA256 `0882b617174665ffd7fb01ba2b3155920a79cc5f9d3e27d7d9426cab60f46bff`)
— RAM banks, reserved map, iomem System RAM ranges, kernel ranges, meminfo,
sanitized bootargs (every `androidboot.*` value redacted except
`slot_suffix=_a`), sensitive properties recorded as presence-only
(`kaslr-seed`, `token`, `use-nv-mac` — values never leave the device/private
repo). No serial, cpuid, MAC, IMEI, seed, or token value is stored anywhere
public. Runtime FDT binary, full raw iomem, and the full tree dump remain
private. The Stock runtime FDT is never used as the Mainline runtime DTB.

## 18. Unresolved conflicts and open items

- ABL blob malformation root cause (section 5) — documented, bypassed via
  live-tree-primary design; no impact on any number used.
- dmesg boot-time memory lines unrecoverable (ring wrapped), pstore empty —
  mitigated by iomem/MemTotal/runtime-tree agreement.
- Banks 1–2 are SUPPORTED (spanning merged iomem resource) rather than
  CONFIRMED per-bank; three independent sources agree on every boundary and
  the union is exact, so no stronger evidence is required by the gate design.
- Device-level effect of RT-D (actual Linux boot with this DTB) is
  intentionally NOT tested this stage: no reboot, no slot writes.

## 19. Final gate and next stage

`FINAL_GATE=R3_RUNTIME_DTB_COMPLETED`

- Runtime FDT available and parsed: YES (live tree primary)
- Verified RAM banks: 3 (section 6), provenance = runtime OF tree + iomem +
  MemTotal, zero conflicts
- Runtime reserved-memory: 22 static regions, byte-exact
- RT-D: self-contained, evidence-equal, CI-reproducible (section 15)
- M1 raw DTB: still not a runtime baseline (by design)
- Stock kernel alignment supporting evidence: Kernel code base mod 2 MiB =
  0x80000
- Current B (M5D + M5H + M5M-B): unchanged; M5N FROZEN; USB FROZEN
- Device: untouched (`SLOT_A_WRITTEN=NO PARTITION_WRITES=0 DEVICE_REBOOT=NO`)

Recommended next stage (requires user approval; nothing executed): design the
next entry-state stage on top of RT-D — carry RT-D (not the ABL x0 DTB) into
the trampoline entry contract, then plan the P1 true-device entry probe
against the M5D baseline. P1 true-device advancement remains gated and is not
part of this stage.
