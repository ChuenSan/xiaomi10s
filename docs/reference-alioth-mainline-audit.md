# Reference audit — Techuouo520/linux7.2.2-alioth-mainline

Stage: `MAINLINE_V2_R1_ALIOTH_THYME_REFERENCE_AUDIT`

Read-only source inspection of the local depth=1 clone. Image/DTB SHA and
header bytes are GitHub Actions-only (`workflow_dispatch` job `alioth-build`).
This repository does not vendor the clone.

## Identity

```text
local path:   refs/alioth-mainline-7.2.2
remote:       https://github.com/Techuouo520/linux7.2.2-alioth-mainline.git
branch:       main
HEAD:         7a70eaac0d9e7ffbaa9abf5badc82c41b391af59
subject:      Enable reboot to bootloader on alioth
date:         2026-09-02 20:31:38 +0800
kernel:       7.2.2 (VERSION/PATCHLEVEL/SUBLEVEL, NAME=Baby Opossum Posse)
depth:        1 (shallow, .git/shallow == HEAD)
dirty:        clean
unshallow:    NOT PERFORMED
REFERENCE_HISTORY_NEEDED=NONE
```

## How this tree claims to boot

README / README_EN.md / CMakeLists.txt only produce:

```text
build/kernel/arch/arm64/boot/Image
build/kernel/arch/arm64/boot/dts/qcom/sm8250-xiaomi-alioth.dtb
```

CMake sequence: `alioth_defconfig` → `scripts/config --disable EFI_ZBOOT` →
`olddefconfig` → `Image modules dtbs`. GHA reproduces Image+dtbs and skips
modules (`CMAKE_MODULES_SKIPPED=YES`) to stay inside runner disk; the Image
and DTB commands match CMake.

```text
BOOT_PACKAGING_NOT_PRESENT_IN_REPO=YES
```

No `boot.img`, `vendor_boot`, `dtbo`, `mkbootimg`, `dtbTool`, QCDT table,
`vbmeta`, or fastboot flash recipe exists outside generic kernel sources.
How Xiaomi ABL on alioth consumes the DTB is **not evidenced in this repo**.
Do not infer a vendor_boot/dtbo layout from the DTS comment alone.

## Root DT metadata

Source: `arch/arm64/boot/dts/qcom/sm8250-xiaomi-alioth.dts`

Wired as a standalone DTB in `arch/arm64/boot/dts/qcom/Makefile`:

```text
dtb-$(CONFIG_ARCH_QCOM) += sm8250-xiaomi-alioth.dtb
```

Root properties (source):

| Field | Value |
|---|---|
| model | `Xiaomi POCO F3` |
| compatible | `xiaomi,alioth`, `qcom,sm8250` |
| chassis-type | `handset` |
| qcom,msm-id | `<QCOM_ID_SM8250 0x20001>` = `<356 0x20001>` |
| qcom,board-id | `<44 0>` |
| aliases.serial0 | `&uart6` (`serial@998000`) |
| chosen | `#address-cells/<2>`, `#size-cells/<2>`, `ranges` |
| stdout-path | NONE |
| bootargs / earlycon | NONE |
| /memory | NONE |
| root qcom,pmic-id | NONE (only regulator `qcom,pmic-id = "a"` / `"c"`) |

```text
ALIOTH_BOOTLOADER_SELECTOR_PROPERTIES=
  qcom,msm-id = <QCOM_ID_SM8250 0x20001>
  qcom,board-id = <44 0>
ALIOTH_SELECTOR_LOCATION=base DTB root
ALIOTH_SELECTOR_COMMENT=required for bootloader to select correct board
ALIOTH_DTBO=NONE_IN_REPO
```

Both selector properties sit on the **base DTS root**, so they land in the
single `sm8250-xiaomi-alioth.dtb`. There is no overlay fragment and no DTBO
packaging in this tree.

## DTB generation

```text
format:            standalone FDT (dtc via kernel dtbs)
appended DTB:      NO evidence
dtbTool / QCDT:    NO
Qualcomm DT table: NO
dtbo image:        NO
vendor_boot:       NO
output:            raw sm8250-xiaomi-alioth.dtb
```

## Boot/flash keyword search (repo, non-generic)

Hits that are actually about this port: README, CMakeLists.txt, alioth DTS
`qcom,board-id` / `qcom,msm-id`, `alioth_defconfig`, `Image` as KBUILD target.

No packaging-role hits for `boot.img`, `vendor_boot`, `dtboimg`, `mkbootimg`,
`kernel_offset`, `ramdisk_offset`, `tags_offset`, `pagesize`, `vbmeta`,
`fastboot`, `avb`, `dtbTool`, `qcdt`.

## Kernel config (alioth_defconfig + CMake EFI_ZBOOT disable)

```text
CONFIG_EFI=y
CONFIG_EFI_STUB=y
CONFIG_EFI_GENERIC_STUB=y
# CONFIG_EFI_ZBOOT is not set   (defconfig and CMake)
CONFIG_RELOCATABLE=y
CONFIG_RANDOMIZE_BASE=y
CONFIG_SERIAL_EARLYCON=y
CONFIG_SERIAL_QCOM_GENI=y
CONFIG_SERIAL_QCOM_GENI_CONSOLE=y
CONFIG_QCOM_GENI_SE=y
CONFIG_USB_DWC3=y / DWC3_QCOM=y / DWC3_DUAL_ROLE=y
CONFIG_USB_GADGET=y
CONFIG_USB_CONFIGFS=m (+ NCM/ECM/RNDIS)
CONFIG_SCSI_UFS_QCOM=y
CONFIG_PHY_QCOM_QMP_UFS=y
CONFIG_PCIE_QCOM=y
CONFIG_ATH11K_PCI=m
```

```text
ALIOTH_SUCCESS_WITH_EFI_STUB_CONFIG=YES
```

This lowers the priority of “Mainline EFI/PE header is incompatible with ABL”
to a config-level deprecation. Binary confirmation is the GHA Image header
(`CODE0_MZ`, `PE_OFFSET`). Not a thyme causal proof.

## UART

```text
aliases serial0 = &uart6          # serial@998000, not thyme's uart2@988000
&uart6 status = okay              # QCA6390 Bluetooth child
stdout-path = NONE
earlycon bootarg = NONE
console= bootarg = NONE
```

Console is not specified in DTS. Do not assume ABL or userspace used UART
because the node exists.

## reserved-memory (POST-HANDOFF REFERENCE)

Alioth deletes five upstream `sm8250.dtsi` nodes and rebuilds them:

| node | upstream sm8250.dtsi | alioth override |
|---|---|---|
| xbl_aop_mem | `0x80700000 + 0x160000` | `0x80600000 + 0x260000` |
| slpi_mem | `0x88c00000 + 0x1500000` | `0x88c00000 + 0x2f00000` |
| adsp_mem | `0x8a100000 + 0x1d00000` | `0x8bb00000 + 0x2500000` |
| spss_mem | `0x8be00000 + 0x100000` | `0x8e000000 + 0x100000` |
| cdsp_secure_heap | `0x8bf00000 + 0x4600000` | `0x8e100000 + 0x4600000` |

Stock thyme reconstructed DT uses the **alioth override addresses**, not the
upstream ones. Current Mainline thyme DTS does not delete/replace these nodes,
so it inherits upstream. Class B only; not treated as the 4.7s pre-entry cause.

## USB / UFS / network (record, do not port)

| Block | Alioth DTS |
|---|---|
| USB | `&usb_1` HS-only, `dr_mode=otg`, `usb-role-switch`, phys=`usb_1_hsphy` only |
| Type-C | `&pm8150b_typec` + `fcs,fsa4480` SBU mux |
| UFS | `&ufs_mem_hc` vcc=`l17a_3p0` vccq=`l6a_1p2` vccq2=`s4a_1p8`; phy okay |
| Wi-Fi | `&pcie0` + `qca6390-pmu` + `pci17cb,1101` |
| firmware-name | `qcom/sm8250/xiaomi/alioth/{adsp,cdsp,slpi,venus,a650_zap}.mbn` |

Board-specific GPIO/PMIC/panel/touch must not be copied onto thyme.

## Image header (GHA)

Committed here as pending. Formal values come from Actions artifact
`r1-alioth-image-dtb`:

```text
ALIOTH_IMAGE_SHA=PENDING_GHA
ALIOTH_DTB_SHA=PENDING_GHA
code0 / MZ / text_offset / image_size / flags / PE offset = PENDING_GHA
```

Source-level expectation: EFI stub Image (`CONFIG_EFI_STUB=y`, zboot off),
so MZ-style `code0` and a non-zero PE offset are the likely binary shape.

## Five questions

1. Does the successful alioth Mainline Image still have EFI stub / PE?
   Config: YES. Binary: PENDING_GHA.
2. Board-selection metadata on the DTB: `qcom,msm-id <356 0x20001>` and
   `qcom,board-id <44 0>` on the **base DTB root**.
3. How Xiaomi boot chain consumes that DTB: **unknown in this repo**
   (`BOOT_PACKAGING_NOT_PRESENT_IN_REPO`).
4. Most important difference vs thyme M1: see
   `docs/route-b-r1-boot-handoff-reference-matrix.md`. Selector *values* on
   the packaged M1 ABL DTB follow this alioth-on-base pattern (with board-id
   45). Stock/Astide thyme use a split base+DTBO protocol instead.
5. Reusable later for thyme server goals: UART GENI console, USB DWC3 HS +
   configfs gadget, UFS QCOM + QMP, ATH11K/QCA6390 on PCIe — after handoff,
   not as the current Gate.
