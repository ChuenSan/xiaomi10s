# Route B Mainline V2 M5G-V — single Stock DTB control

Status: true-device test complete. Final gate:
`MAINLINE_V2_M5G_V_STOCK_DTB_SUPPRESSES_4P7S`.
Android A restored. Slot B retains exact M5D `boot_b` plus the single-DTB
`vendor_boot_b` candidate and exact Stock `dtbo_b`.

## Question

Cell B already proved that M1 `vendor_boot` alone (single-DTB topology +
Mainline thyme DTB) reproduces the ~4.7s Fastboot return on exact Stock
`dtbo` (5.008s). This round keeps the M1 single-DTB topology class and
replaces only the DTB payload with exact Stock DTB0.

```text
Cell B   single-DTB topology + Mainline thyme DTB + Stock dtbo -> 5.008s
M5G-V    single-DTB topology + exact Stock DTB0    + Stock dtbo -> ???
```

The factorization under test is DTB payload / selector / base-overlay
compatibility versus single-DTB topology and layout.

## Constraints

```text
MEM0_READ_BEFORE_M5G_V=YES
MEM0_READ_BEFORE_WRITE=YES
LOCAL_BUILD=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
GHA_ONLY=YES
new build this round=NO
Slot A flash/erase/format=NO
BOOT_B_WRITE=FORBIDDEN
DTBO_B_WRITE=FORBIDDEN
vbmeta* / firmware write=NO
only partition write=vendor_boot_b
B boots=1
SECOND_B_BOOT_FORBIDDEN=YES
old vendor_boot context restore=NO
M5H auto-exec=NO
```

No local build, validator, source gate, actionlint, or binary validation ran.
The only new CI work was a read-only hash probe (below).

## Reference Cell B

```text
boot:         exact M5D, SHA256 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
vendor_boot:  M1 single Mainline thyme DTB
dtbo:         exact Stock
runtime:      5.008s
```

## Candidate identity

Private GHA run [`34559797694`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34559797694).
Artifact re-downloaded, not regenerated, not modified.

```text
artifact: m5g-v-single-stock-dtb-vendor_boot.img
size=548864
SHA256=e49e12ad71839bc959237eb8ef6ad6ba7f2f38dffedcf31f3fe36b0845402e83
vendor ramdisk=UNCHANGED (2238 bytes, 137c4897aa7adf416706a1668edac96c66fbbf1d232735b1cb7a74f399a14639)
header=unchanged except derived dtb_size
DTB topology=SINGLE DTB
DTB payload=exact Stock DTB0 (540195 bytes, 324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8)
```

Intentional logical change: `VENDOR_DTB_PAYLOAD_FAMILY`.
Unavoidable secondary change: `dtb_size` and vendor_boot artifact extent,
because Stock DTB0 (540195) is far larger than the Mainline DTB (106026).
Artifact extent 548864 versus M1 114688. Both deltas are recorded, not hidden.

## Hash domain

The artifact is 548864 bytes but `vendor_boot_b` is 100663296 bytes.
Artifact identity therefore uses the first 548864 bytes only. A whole-partition
SHA is never used as the artifact gate.

The write covers only `[0, 548864)`. The remainder `[548864, EOF)` came from
the exact Stock partition tail and must be verified separately.

The M5G private report did not contain a Stock tail SHA for that offset, so a
read-only private GHA probe was added and dispatched
([`34566194209`](https://github.com/ChuenSan/thyme-mainline-private-ci/actions/runs/34566194209)):

```text
workflow: m5g-v-tail-sha.yml  (read-only; no flash artifact; no device operation)
input: exact Stock vendor_boot.img, sha256 aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
range: [548864, 100663296)
EXPECTED_STOCK_VENDOR_TAIL_SHA=5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52
```

## Pre-write state

Android A baseline:

```text
adb device=41a5627b
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0 magisk
```

Cell B identity, all independent Android A readbacks:

```text
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH
vendor_boot_b first 114688 SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5  MATCH
vendor_boot_b [114688,EOF) SHA256=3d6cb7047e6d0b70a764b6dae548a720904378c62f151732d5faaab8ea703a74  MATCH
dtbo_b whole SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634  MATCH
vendor_boot_b [548864,EOF) SHA256=5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52  == expected tail
vbmeta_b [0,8192)=37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c  stock
vbmeta_system_b [0,4096)=3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355  stock
M5G_V_START_CELL_B_EXACT=YES
```

Fastboot preflight:

```text
product=thyme
unlocked=yes
current-slot=a
snapshot-update-status=none
battery-soc-ok=yes
slot-retry-count:b=6
slot-unbootable:b=no
```

## Writes

Exactly one partition write.

```text
fastboot flash vendor_boot_b m5g-v-single-stock-dtb-vendor_boot.img   OKAY
NO WRITE: boot_b, dtbo_b, vbmeta*, firmware, ANY *_a
current-slot remained a; reboot went to Android A, not B
```

Independent post-write readback on slot A:

```text
vendor_boot_b first 548864 SHA256=e49e12ad71839bc959237eb8ef6ad6ba7f2f38dffedcf31f3fe36b0845402e83  MATCH
vendor_boot_b [548864,EOF) SHA256=5d98f207def3af98517cb4c74dc5befaee5a2b62209e32cd13b4c181bb374e52  MATCH
boot_b first 35110912 SHA256=4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63  MATCH
dtbo_b whole SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634  MATCH
vbmeta_b / vbmeta_system_b=stock
abl_b / xbl_b / xbl_config_b / tz_b=byte-identical to pre-write
M5G_V_FULL_CONTEXT_VERIFIED=YES
```

## Single B boot

```text
pre : current-slot=a, retry:b=6, unbootable:b=no
fastboot set_active b -> current-slot=b, retry:b=7, unbootable:b=no
exactly one fastboot reboot
SECOND_B_BOOT_FORBIDDEN=YES
```

USB evidence is Fastboot protocol presence (`18d1:d00d`) only.

```text
FASTBOOT_DISAPPEAR_TIMESTAMP=2026-09-11T05:34:20.563Z
FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED
OBSERVATION_WINDOW=12s
AUTOMATIC_FASTBOOT_REAPPEAR=NO
M5G_V_4P7S_RETURN_SUPPRESSED=YES
V_SINGLE_STOCK_DTB_EFFECT=YES
CASE=V1
```

Fastboot did **not** return automatically within the 12s primary observation
window, and the device stayed stuck afterwards. Fastboot only became reachable
at `2026-09-11T05:35:39.905Z` (79.343s after disappear) because the user
performed a **manual physical Fastboot recovery** (Volume-Down + Power).

The 79.343s value is therefore only the time at which manual recovery happened.
It is not an automatic return time and must not be cited as evidence about the
boot chain, a watchdog, an ABL fallback, or any boot timeout. The following
labels are withdrawn as wrong: `AUTOMATIC_FASTBOOT_REAPPEAR_AT_79P343S`,
`NATURAL_RETURN_TIME_79P343S`. The agent itself pressed no keys and issued no
ordinary reboot on slot B.

```text
AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO
M5G_V_4P7S_RETURN_SUPPRESSED=YES
MANUAL_FASTBOOT_RECOVERY_AFTER_WINDOW=YES
MANUAL_RECOVERY=YES
PRIMARY_OBSERVATION=>12s
```

For every future >12s case, record only `PRIMARY_OBSERVATION=>12s` plus
`MANUAL_RECOVERY=YES/NO`. Never record a manual recovery time as an automatic
return time.

## Recovery

```text
post-attempt metadata before recovery: current-slot=b, retry:b=6, unbootable:b=no, successful:b=no
fastboot set_active a -> current-slot=a
fastboot reboot
ANDROID_A_RESTORED=YES
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0
no second B boot
no old vendor_boot context restored
```

## Dumps

Read-only, not cleared.

```text
pstore entries baseline/post=0/0 UNCHANGED
minidump=e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a UNCHANGED
rawdump=254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917 UNCHANGED
logdump=3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351 UNCHANGED
logfs=50ca65c818a07f2ffc17d51c7e92587b3811eda1c60272f035ae01eb472151f5 -> 637b6560c42a1e528a58ae51d77aa0abecd6e9e1e282d7e15625f317c523afe9 CHANGED
oops=M5F2 c31867564f670a18e66f51293af0b82b201d55de7571c351af6696149db816b3 -> 391d686d237b840c978581c531e0087ca3d3bd63631c0c3130457d6c71da6322 CHANGED
```

The changed `oops` image contains only pre-existing 2023-09-04 stock Android
records (7 records, `Reason: Restart`), zero records dated 2026, zero
`Linux version` strings, zero `6.6.x` / `mainline` markers, and 21
`reboot,bootloader` records. It is not Mainline evidence; the same
`reboot,bootloader` attribution was established in M5E.

Limitation, recorded honestly: a same-round pre-write `oops` baseline was not
captured — the baseline pass covered `minidump` / `rawdump` / `logdump` /
`logfs` only. The `oops` comparison therefore uses the M5F2 final value, which
is confounded by the Android A -> bootloader -> A cycles this round performed.
Conclusion for `oops` rests on content inspection, not on the numeric delta.

## Classification

```text
M5G_V_4P7S_RETURN_SUPPRESSED=YES
V_SINGLE_STOCK_DTB_EFFECT=YES
SINGLE_DTB_TOPOLOGY_ALONE_SUFFICIENT=NO
M1_MAINLINE_BASE_DTB_CAUSAL_FAMILY=STRONGLY_SUPPORTED
FINAL_GATE=MAINLINE_V2_M5G_V_STOCK_DTB_SUPPRESSES_4P7S
```

Same exact M5D boot, same exact Stock `dtbo`, same single-DTB topology class:

```text
M1 Mainline DTB payload: 5.008s automatic Fastboot return
exact Stock DTB0 payload: no automatic Fastboot return in 12s
```

Because the topology stayed single-DTB while behavior flipped from 5.008s to
suppressed, "only one DTB" does not by itself explain the failure. The
vendor DTB payload / metadata / base-overlay compatibility group carries the
strong causal support.

Do not assert from this round:

- that board-id `<45 0>` alone is the cause
- that `compatible` alone is the cause
- that the `/memory` node alone is the cause
- that overlay fixup failure is proven
- that ABL's DTB selection algorithm is the cause

This round replaced the whole DTB payload and `dtb_size` moved with it, so the
claim stays at the family level, not at a single field.

Post-test Slot B identity, not rewritten:

```text
boot_b first 35110912 = exact M5D
vendor_boot_b first 548864 = V_SINGLE_STOCK_DTB candidate; tail = exact Stock
dtbo_b whole = exact Stock
vbmeta / firmware = stock, byte-identical
B_FINAL=M5D boot + single Stock DTB vendor_boot + Stock dtbo
```

## Next, not executed

```text
NEXT=MAINLINE_V2_M5H_MAINLINE_DTB_COMPATIBILITY_ISOLATION
focus: make the Mainline DTB compatible with Stock ABL + Stock DTBO chain
variable order, CI/control design first, no auto true-device:
  1. base board-id <45 0> -> <0 0>
  2. root compatible / downstream selector compatibility
  3. symbols / target nodes / fixup compatibility required by Stock entry 21
  4. /memory placeholder
audit Stock entry 21's 154 fixups for resolvability against the Mainline DTB first
NO NEXT STAGE EXECUTED=YES
WAIT FOR USER APPROVAL
```
