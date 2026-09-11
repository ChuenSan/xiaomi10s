# Reference audit — AstideLabs/android_kernel_xiaomi_sm8250

Stage: `MAINLINE_V2_R1_ALIOTH_THYME_REFERENCE_AUDIT`

Read-only source inspection of the local depth=1 clone. Secondary reference
for thyme downstream hardware and DT overlay / board-id protocol. Not a
drop-in replacement for Mainline 6.6.

## Identity

```text
local path:   refs/astidelabs-sm8250
remote:       https://github.com/AstideLabs/android_kernel_xiaomi_sm8250.git
branch:       android17-aptusitu
HEAD:         e0993b7c0638fd168fbc62044589bfd22387de83
subject:      Merge branch 'android17-base' into android17-aptusitu
date:         2026-08-24 23:21:29 +0800
kernel:       4.19.325 (NAME="People's Front")
depth:        1
dirty:        clean
unshallow:    NOT PERFORMED
REFERENCE_HISTORY_NEEDED=NONE
```

README states the tree is based on LineageOS `android_kernel_qcom_sm8250`,
plus Strawing / UtsavBalar1231 / LineageOS `android_kernel_xiaomi_sm8250`
community work. Releases target MIUI/HyperOS and AOSP Android 11–17.

## Device support (not from the title)

Present in this HEAD:

| Device | Overlay | dtsi | defconfig |
|---|---|---|---|
| thyme | `arch/arm64/boot/dts/vendor/qcom/thyme-sm8250-overlay.dts` (duplicate under `vendor/xiaomi/`) | `thyme-sm8250.dtsi` | `thyme_defconfig`, `thyme_stock-defconfig` |
| alioth | `alioth-sm8250-overlay.dts` (+ `vendor/xiaomi/`) | `alioth-sm8250.dtsi` | `alioth_defconfig`, `alioth_stock-defconfig` |

```text
CONFIG_MACH_XIAOMI_THYME=y          # thyme_defconfig
CONFIG_BUILD_ARM64_DT_OVERLAY=y     # thyme_defconfig / alioth_defconfig
# CONFIG_EFI is not set             # thyme_defconfig
```

`thyme_stock-defconfig` has `# CONFIG_BUILD_ARM64_DT_OVERLAY is not set`.
The live overlay build path is the non-stock defconfig + vendor Makefile.

## DT / DTBO structure

`arch/arm64/boot/dts/vendor/qcom/Makefile`:

```text
dtbo-$(CONFIG_MACH_XIAOMI_THYME) += thyme-sm8250-overlay.dtbo
thyme-sm8250-overlay.dtbo-base := kona.dtb kona-v2.dtb kona-v2.1.dtb

dtbo-$(CONFIG_MACH_XIAOMI_ALIOTH) += alioth-sm8250-overlay.dtbo
alioth-sm8250-overlay.dtbo-base := kona.dtb kona-v2.dtb kona-v2.1.dtb
```

This is kernel DT overlay generation (`scripts/Makefile.dtbo`,
`scripts/mkdtboimg.py`), **not** Android `vendor_boot.img` / `boot.img`
packaging. No `mkbootimg`, `kernel_offset`, or `BOARD_KERNEL_*` in this
kernel tree. Those live in device repos, not here.

### Base SoC DTBs (ABL-visible msm-id)

| File | qcom,msm-id | qcom,board-id |
|---|---|---|
| `kona.dtsi` | `<356 0x10000>` | (via `kona.dts`) `<0 0>` |
| `kona-v2.dtsi` | `<356 0x20000>` | `<0 0>` |
| `kona-v2.1.dtsi` | `<356 0x20001>` | `<0 0>` |

Runtime stock thyme uses `dtb_idx=0` = kona v2.1.

### Overlay root (ABL-visible board-id)

`thyme-sm8250-overlay.dts`:

```text
model       = "Qualcomm Technologies, Inc. xiaomi thyme"
compatible  = "qcom,kona-mtp", "qcom,kona", "qcom,mtp"
qcom,board-id = <45 0>
```

`alioth-sm8250-overlay.dts`: same compatible family, `qcom,board-id = <44 0>`.

The overlay is `/plugin/`; board-id lives on the overlay root, not on the
kona base. This matches stock `dtbo` entry 21 and the M1 no-op DTBO recipe.

## What is kernel source vs packaging

| Item | In this repo? |
|---|---|
| thyme/alioth DTS/DTSI/overlay | YES (kernel source) |
| `CONFIG_BUILD_ARM64_DT_OVERLAY` | YES |
| `mkdtboimg.py` / `Makefile.dtbo` | YES (kernel DTBO image) |
| dtbTool / QCDT | NO (beyond generic dtc) |
| vendor_boot / boot.img / mkbootimg | NO |
| BOARD_KERNEL_* offsets | NO |

## thyme overlay contents (CLASS C / hardware)

`thyme-sm8250.dtsi` is a Xiaomi board overlay body: UFS `ufshc_mem` with
`qcom,disable-lpm`, display/DSI, USB1 extcon, FG/charger (bq25970),
firmware/vbmeta/fstab android nodes. UART aliases are not in this file;
stock merged DT maps `serial0` to `qup_uart@988000` (mainline `uart2`).

Do not copy GPIO/panel/touch/camera from this file onto Mainline thyme.

## reserved-memory / PMIC / UFS / USB

Use stock reconstructed DT (`docs/stock-rom-analysis.md`) as the thyme
authority. Astide confirms the split kona-base + thyme-overlay protocol and
board-id `<45 0>`. It does not by itself explain the M0→M1 4.7s flip; it
explains what ABL *expected* on thyme:

```text
vendor_boot DTB:  concatenated kona v2.1/v2/v1 + stub, msm-id, board-id <0 0>
dtbo:             overlay board-id <45 0>, compatible qcom,kona-mtp/kona/mtp
```

## Five questions

1. Downstream thyme DT metadata: kona v2.1 `msm-id <356 0x20001>` +
   `board-id <0 0>` on the base; overlay `board-id <45 0>`, compatible
   `qcom,kona-mtp / qcom,kona / qcom,mtp`.
2. thyme/alioth share the same kona base DTBs and overlay compatible family.
   They differ by overlay board-id 45 vs 44 and board dtsi contents.
3. DTBO identification: overlay root `qcom,board-id`, built as
   `*-sm8250-overlay.dtbo` against three kona bases.
4. reserved-memory / PMIC / UFS / USB: usable as a map against stock DT;
   not a Mainline source to copy.
5. M0 vs M1: Astide shows the **stock split protocol**. M1 replaced the
   concatenated kona table with one Mainline DTB (ABL-injected ids) and
   replaced the 29-entry family dtbo with a 1-entry no-op that still uses
   board-id `<45 0>`. That is a packaging/selector-structure difference,
   not a missing thyme board-id value on the no-op overlay.
