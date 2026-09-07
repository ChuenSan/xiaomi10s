# Mainline boot chain analysis — Xiaomi Mi 10S (thyme)

Status: PREPARATION-ONLY (no device writes). Evidence markers:
`CONFIRMED_STOCK` (parsed stock ROM* / `CONFIRMED_ANDROID` (LineageOS build
config* / `CONFIRMED_COMMUNITY` (working mainline port on sibling kona
device* / `INFERRED` / `UNKNOWN`.

Primary deliverable of this document: the **DTB delivery decision** for
`sm8250-xiaomi-thyme.dtb`, feeding sections Q1/Q2/Q3 of the phase brief.

## 1. Answers first

```text
Mainline DTB supplied via:
  PRIMARY  : boot_b.img header v2,  --dtb sm8250-xiaomi-thyme.dtb
             ( DTB section at 0x1f00000,  kona convention)*
  FALLBACK : vendor_boot_b.img header v3,  --dtb <same>  (+experimental dtbo_b*

boot_b         required:  YES
vendor_boot_b  required:  NO   (primary path*,  YES (fallback path*
dtbo_b         required:  NO   (primary path*,  YES (fallback path*
```

Rationale in short: boot image header v2 is the **only container that lets
the board DTB travel inside `boot_b`** (v2 dtb field; v3 drops it into
`vendor_boot` instead). Community-proven on the same Xiaomi/kona ABL
generation ( elish-pmos: `deviceinfo_append_dtb`,  lmi: v2 dtb field/
appended* that `boot_b`-only suffices; the ABL dtbo path falls through
harmlessly ( stock overlay cannot apply to a symbol-free mainline DTB*.
Fallback keeps the stock v3 layout and adds an experimental no-op dtbo_b to
make the ABL dtbo path deterministic..

`UNKNOWN` items (no hardware/ABL source available*: exact behavior of
Xiaomi ABL when (a* a v2-header boot.img is found in `boot_b` of a
virtual-A/B device, (b* dtbo overlay application fails. Both are de-risked
by the trivially reversible write plan ( boot_b only*, flash stock back =
recovery* window..

## 2. Boot chain A — stock (CONFIRMED_STOCK*

Parsed from MIUI V14.0.6.0.TGACNXM (`docs/stock-rom-analysis.md`*:

```text
boot.img        header v3:  kernel (52.65 MB raw arm64 Image*, generic ramdisk (19.73 MB gzip*,
                  NO DTB.
vendor_boot.img header v3:  vendor ramdisk (2.2 KB gzip*, board
                  cmdline*, DTB section = 4 concatenated kona FDTs
dtbo.img       dt_table v0,  29 entries; entry 21+
                  board-id <45 0>, model xiaomi thyme, 484.9 KB
runtime         ro.boot.dtb_idx=0         → kona-v2.1 base DT
                ro.boot.dtbo_idx=21      → thyme overlay
```

ABL (UEFI app, `abl.img` — no readable strings found, treated as a
black box*: selects base DTB from the vendor_boot blob via `qcom,msm-id`
matching `(dtb_idx=0)`, then selects the overlay entry from dtbo via
`qcom,board-id` matching the detected platform `(dtbo_idx=21)` and
applies it, then enters the kernel ( r2 = DTB addr,, r0 = 0*,
r1 = 0* with the merged DT*.



Relevant kernel header facts: stock kernel payload is the raw arm64
`Image` ( header magic `0x644d5241`;text_offset `0x00080000`* — the
same format and handshake the mainline arm64 Image uses.(CONFIRMED_STOCK*..

Critical consequence: the stock base root `compatible = "qcom,kona"`
(and *no* `qcom,sm8250`*. The mainline sm8250 machine table matches
`"qcom,sm8250"` — so a stock/merged DTB **cannot boot a mainline
m8250 kernel** (*machine mismatch*, kernel stops at early boot*. This
is what forces the mainline DTB to be physically delivered to the kernel..

## 3. Boot chain B — LineageOS 22.1/23.2 (CONFIRMED_ANDROID*

`android-device-sm8250-common/BoardConfigCommon.mk`:

```make
PRODUCT_VIRTUAL_AB_OTA   → BOARD_BOOT_HEADER_VERSION := 3
BOARD_INCLUDE_DTB_IN_BOOTIMG    := true
BOARD_KERNEL_SEPARATED_DTBO    := true
BOARD_BOOTIMAGE_PARTITION_SIZE  := 201326592   (VAB*
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_DTBOIMG_PARTITION_SIZE       := 33554432
```

So LineageOS builds keep the stock v3 layout: kernel/ramdisk in `boot`,
DTB+vendor-cmdline in `vendor_boot`,  overlay in `dtbo`. The AOSP
mkbootimg packs the DTB into vendor_boot automatically when
header_version>=3 (and the v1/v2 dtb field is used only when
header_version<3* — verified in `work/tools/mkbootimg.py`: dtb_write
code path guards on `0 < header_version < 3`*. This is the
stock-structure path*(= our FALLBACK*..

## 4. Boot chain C — proposed mainline

### C1 «boot_b-only» (PRIMARY, MINIMUM WRITES*

```text
boot_b:      header v2,  --dtb sm8250-xiaomi-thyme.dtb
            ( dtb_offset 0x01f00000*, pagesize 4096,
              kernel_offset 0x8000, ramdisk_offset 0x1000000,
              tags_offset  0x100, cmdline := stock vendor cmdline*,
              os_version 13.0.0, os_patch_level 2023-09*
vendor_boot_b: untouched (stock*
dtbo_b:        untouched (stock*
```

Why this is expected to work (`CONFIRMED_COMMUNITY`*:

- `lmi` (POCO F2 Pro, kona, 2020*: community mainline boot
  image keeps header **v2** with the mainline DTB at dtb_offset
  `0x1f00000` (or appended*,and boots via `fastboot boot` and later
  via a flashed `boot` partition*; `dtbo`/`vendor_boot` untouched
  (`ccc007ccc/sm8250-xiaomi-lmi-boot`, `locks/mkbootimg.args`*.
- `elish` (Mi Pad 5 Pro, kona, VAB, Android 11*: postmarketOS
  device package `device-xiaomi-elish`: `deviceinfo_append_dtb="true"`,
  `deviceinfo_generate_bootimg="true"`, flash_method fastboot — a v3-platform
  device boots with a single boot.img-style image* (`pmaports`*..
  The community ABL generation accepts v2-layout DTB-in-boot delivery*..

Mechanics: the arm64 kernel is DT-driven; ABL loads the DTB from the
selected container and passes its address in r2 (arm64 boot protocol*,
unaffected by the boot header version used for packaging. The v2 header
keeps DTB + cmdline inside boot.img, both fully under our control,
and both are handled by ABL directly, without involving the vendor_boot/
dtbo DTB path*. If/the ABL dtbo path still engages, the stock entry 21
cannot resolve (* the mainline DTB has **no `__symbols__`** —
`CONFIG_OF_OVERLAY` is not enabled in arm64 defconfig*), which on the lmi
port falls through at worst to an unmodified DTB (community-observed
pattern*..

Thus **minimum possible write set**: `boot_b` only** — and rollback is
a single `fastboot flash boot_b stock-boot.img` ( stock boot.img already
in the project ROM*..

### C2 «vendor_boot_b + dtbo_b»（FALLBACK, stock-v3 layout**

```text
boot_b:         header v3,  mainline Image + mainline initramfs
vendor_boot_b:  header v3,  page 4096,  dtb_offset  ​​0x1f00000,
                   dtb := sm8250-xiaomi-thyme.dtb,
                   vendor ramdisk := stock `vendor_ramdisk` if available,
                   else minimal empty cpio stub,  board cmdline := stock
dtbo_b:          dt_table v0,   single entry{ board-id <45 0>,
                   model "Xiaomi Mi 10S (thyme)",  overlay := no-op
        fragment@0 { target-path="/"; __overlay__ { qcom,thyme-mainline-noop;; }; }; }
```

This is the stock-compatible structure ( the path LineageOS uses*,with
an experimental dtbo_b that makes the ABL overlay application **deterministic**
(see Q2*: matched by board-id, applies cleanly (the fragment targets
path `/` — no base `__symbols__` required*), net effect ≈ 0 (plus one
inert root marker property*..

## 5. Q1 — how does the mainline DTB reach the bootloader/kernel?

```text
ANSWER  (PRIMARY*: by carrying it in the boot_b image DTB field,
header v2.  (CONFIRMED_COMMUNITY on sibling kona ABL*, INFERRED for
thyme's exact ABL rev + VAB device*;de-risked: boot_b-only write*
if this v2 path is rejected by the ABL, boot is visibly short and
recovery = reflash stock boot_b*..

Fallback (if v2 rejected*: vendor_boot_b DTB section, header v3 —
stock-equivalent structure*, CONFIRMED via stock AND LineageOS flows.*
```

Evidence table:

| Option | Stock layout? | Evidence | Verdict |
|---|---|---|---|
| vendor_boot_b DTB (v3* | yes (stock/Lineage* | CONFIRMED_STOCK/ANDROID | **FALLBACK** |
| boot.img dtb field (v2* | no (v3 stock*,  v2 is an ABL-supported legacy format* | CONFIRMED_COMMUNITYon lmi/elish (both kona*, INFERRED for thyme | **PRIMARY (min writes* |
| kernel-appended DTB（`Image`+dtb trailer* | n/a for ABL (ABL selects the container itself* | lmi used it as an alternate packaging*, not selectable by ABL | not chosen (params differ* |
| bootloader-provided（e.g. XBL memory DT* | no control from our side | UNKNOWN | not chosen | 

Root-cause requirement ( why DTB must physically travel*: mainline arm64
machine match needs root `compatible` containing `qcom,sm8250`; stock
base/merged DT root is `qcom,kona` (CONFIRMED_STOCK*, so without a
mainline DTB the kernel cannot find its machine*.. Also v3 boot.img has
**no DTB field at all** (kernel + ramdisk only*, and v3's DTB carrier is
vendor_boot — hencethe "vendor_boot_b or v2-boot_b" dichotomy*..

## 6. Q2 — does the stock dtbo entry 21 get auto-applied to a replaced DTB?

```text
ANSWER  YES, ABL selects dtbo entries by runtime board-id — NOT by
properties of the boot/base DTB. Stock dtbo entry 21 (board-id <45 0>*)
matches thyme's runtime platform ID every boot, regardless of what
sits in boot_b / vendor_boot DTB section. (CONFIRMED_STOCK-derived inequality:
base DTB board-id <0 0>≠overlay board-id <45 0>, yet the overlay
was applied at runtime → matching is vs platform detection,, not vs base.*

Consequence: a mainline DTB in boot_b/vendor_boot_b receives a **failed**
overlay application attempt( `stock entry 21`( `/plugin/` фрагменты
reference kona base `__symbols__` phandles (`thyme-sm8250-overlay.dts`*;
the mainline DTB has no `__symbols__` (`CONFIG_OF_OVERLAY` off in arm64
defconfig*, dtc compiles dtbs without `-@`*), so symbol resolution fails.

Applying a downstream overlay on top of mainline tree is the exact hazard
the phase brief forbids (`mainline DTB + stock thyme downstream Android
overlay → not allowed`*..
```

```text
Primary path (boot_b-only*: NOT need to touch dtbo: the v2-layout
  boot ( stock dtbo untouched* has community precedent on lmi/elish
  ( both kona* where the same broken-application situation exists,and the
  device boots`. Behavior on actual failure is INFERRED from community:
  ABL either skips or falls through to an unmodified DTB*; exact ABL
  rev behavior is UNKNOWN. Recovery trivial ( reflash boot_b*..
Fallback path: ship an experimental dtbo_b with a single **no-op overlay**
  board-id <45 0>, target-path="/" — no base-symbols required»; the
  ABL dtbo path becomes deterministic:matched → applied → net-zero
  delta*. `fdtoverlay(mainline.dtb + noop.dtbo` is CI-validated to be
  mainline-equivalent( plus one inert root marker property*..
```

| dtbo_b content | ABL result | verdict |
|---|---|---|
| stock dtbo_img (current* | matched → apply → fails (no symbols* → UNKNOWN* | not allowed (unknown failure mode* |
| experimental no-op dtbo_img | matched → applies cleanly → ≈no-op | **FALLBACK path only** |
| absent / no matching entry | likely "no overlay" path (Android dtbo convention* | not chosen (unknownon our ABL* |

## 7. Q3 — minimum Slot B writes

```text
ANSWER  PRIMARY:  boot_b                            ONLY  (1 partition*
                 FALLBACK: boot_b + vendor_boot_b + dtbo_b   (3 partitions*
```

Comparison:

| option | partitions | why (evidence* |
|---|---|---|
| boot_b only | 1 | v2 dtb-field delivery suffices (CONFIRMED_COMMUNITY*, working on kona*; dtbo left stock, hazards avoided by the no-symbols wall ( Q2*; cmdline travels in boot ( v2* |
| boot_b + vendor_boot_b | 2 | not needed if v2 path works; vendor_boot only matters in v3 layout （rejected-v2 hypothesis* |
| boot_b + vendor_boot_b + dtbo_b | 3 | stock-v3 fallback structure; dtbo_b is added to make overlay path deterministic( Q2* |

Design rule honored: no partition is added for convenience; every
extra partition is justified by a concrete boot-chain failure mode of the
previous set*..

## 8. Image construction reference ( used by the artifacts CI*

### boot_b(primary**, header v2*

```text
--header_version  2
--base             0x00000000
--kernel_offset    0x00008000
--ramdisk_offset    0x01000000
--tags_offset       0x00000100
--second_offset     0x00f00000      (v2 field*, unused by us*
--pagesize         4096
--dtb              sm8250-xiaomi-thyme.dtb
--dtb_offset       0x01f00000        (kona/elish/lmi convention*
--os_version       13.0.0           (stock values;AVB off*, informational*
--os_patch_level   2023-09
--cmdline          <verbatim stock vendor cmdline>
--board            thyme
```

### boot_b(fallback*, header v3*

```text
--header_version  3
--base             0x00000000
--kernel_offset    0x00008000
--ramdisk_offset    0x01000000
--tags_offset       0x00000100
--pagesize         4096
--os_version       13.0.0
--os_patch_level   2023-09
--board            thyme
```

### vendor_boot_b(fallback*

```text
--header_version  3
--pagesize        4096
--dtb             sm8250-xiaomi-thyme.dtb
--dtb_offset      0x1f00000
--vendor_ramdisk  stock `vendor_ramdisk` (2.2 KB gzip* if supplied*,
                    else minimal empty cpio stub ( irrelevant to mainline kernel*
--vendor_cmdline  <verbatim stock vendor cmdline>
```

### dtbo_b(fallback*

```text
noop.dts (plugin*:  model "Xiaomi Mi 10S (thyme)",  compatible
  "qcom,kona-mtp","qcom,kona","qcom,mtp",  qcom,board-id = <45 0>;
  fragment@0 { target-path="/"; __overlay__ { qcom,thyme-mainline-noop;; }; }; }
dtc -@ -O dtb -o noop.dtbo noop.dts
mkdtboimg.py --version 0 --page_size 4096 -o experimental-dtbo.img  noop.dtbo
```

Note: `mkdtboimg.py` copies entry `qcom,board-id`/`compatible` from the
overlay root into the dt_table entry header — so a dump of the entry must
show board-id `<45 0>` (CI-validated*..

## 9. Markers

```text
CONFIRMED_STOCK      : parsed stock images (dtb_idx/dtbo_idx, base root compatible*, image field layout*
CONFIRMED_ANDROID   : LineageOS BoardConfig (v3/VAB/dtbo layout, partition sizes*
CONFIRMED_COMMUNITY  : lmi + elish working mainline (v2-dtb-carrying boot, dtbo untouched*
INFERRED             : exact thyme ABL rev accepts v2 boot_b;  ABL failure fallthrough*
UNKNOWN               : exact ABL behavior on (a* v2-header boot in VAB boot_b,
                        (b* dtbo application failure; (c* no-matching-dtbo case
```

## 10. References

- `docs/stock-rom-analysis.md`（stock parse*
- `android-device-sm8250-common/BoardConfigCommon.mk`（LineageOS VAB/v3*
- `android-kernel-sm8250/arch/arm64/boot/dts/vendor/qcom/thyme-sm8250-overlay.dts`（downstream /plugin/ overlay*
- `linux-6.6/arch/arm64/boot/dts/qcom/sm8250-xiaomi-thyme.dts`（our board DTS*
- `work/tools/mkbootimg.py`（AOSP*, header-v2 dtb support*
- Community: `ccc007ccc/sm8250-xiaomi-lmi-boot` ( lmi*;
            `postmarketOS/pmaports` device-xiaomi-elish ( elish*..