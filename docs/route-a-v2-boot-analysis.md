# Route A — experimental-boot-v2.img binary analysis

Status markers: `CONFIRMED_BINARY` (this file), `CONFIRMED_STOCK`, `CONFIRMED_ANDROID`,
`CONFIRMED_SOURCE`, `STRONG_INFERENCE`, `UNKNOWN`.

Parser: `scripts/route-a/parse_boot_v2.py` (read-only). Spec:
[AOSP boot_img_hdr_v2](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/android16-qpr2-release/include/bootimg/bootimg.h).

Artifact: GHA run [34116449773](https://github.com/ChuenSan/xiaomi10s/actions/runs/34116449773)
commit `29bc752517c53a5532bd1974e3bff59cca5af391`.

Image SHA256:

```
ae32736c59bd21b02abcf0f1263ace2c5b46569c4a387585dd92d34948f5034b
```

Size: 36,401,152 bytes. `computed_end == file_size`. Layout PASS.

## 1. Header (boot v2)

| Field | Value | Evidence |
|---|---|---|
| magic | `ANDROID!` | CONFIRMED_BINARY |
| kernel_size | 35101184 | CONFIRMED_BINARY = `Image` |
| kernel_addr | `0x00008000` | CONFIRMED_BINARY |
| ramdisk_size | 1186235 | CONFIRMED_BINARY = `initramfs.cpio.gz` |
| ramdisk_addr | `0x01000000` | CONFIRMED_BINARY |
| second_size / second_addr | 0 / `0x0` | CONFIRMED_BINARY |
| tags_addr | `0x00000100` | CONFIRMED_BINARY |
| page_size | 4096 | CONFIRMED_BINARY |
| header_version | 2 | CONFIRMED_BINARY |
| os_version | 13.0.0 | packed `(os << 11) \| patch` |
| os_patch_level | 2023-09 | same |
| name | `thyme` | CONFIRMED_BINARY |
| cmdline | stock vendor_boot cmdline (see below) | CONFIRMED_BINARY |
| extra_cmdline | empty | CONFIRMED_BINARY |
| recovery_dtbo_size / offset | 0 / 0 | CONFIRMED_BINARY |
| header_size | 1660 | `BOOT_IMAGE_HEADER_V2_SIZE` |
| dtb_size | 105960 | CONFIRMED_BINARY |
| dtb_addr | `0x0000000001f00000` | CONFIRMED_BINARY |

cmdline (verbatim):

```
console=ttyMSM0,115200n8 androidboot.hardware=qcom androidboot.console=ttyMSM0 androidboot.memcg=1 lpm_levels.sleep_disabled=1 video=vfb:640x400,bpp=32,memsize=3072000 msm_rtb.filter=0x237 service_locator.enable=1 androidboot.usbcontroller=a600000.dwc3 swiotlb=2048 loop.max_part=7 cgroup.memory=nokmem,nosocket reboot=panic_warm buildvariant=user
```

Matches stock `vendor_boot` cmdline (`docs/stock-rom-analysis.md` §5). CONFIRMED_STOCK.

## 2. File layout

Spec: header 1 page; then kernel, ramdisk, second, recovery dtbo, dtb; each page-aligned.

| Region | offset | size | padded_end |
|---|---:|---:|---:|
| header | 0 | 1660 | 4096 |
| kernel | 4096 | 35101184 | 35106816 |
| ramdisk | 35106816 | 1186235 | 36294656 |
| second | 36294656 | 0 | 36294656 |
| recovery dtbo | — | 0 | — |
| DTB | 36294656 | 105960 | 36401152 |

`FDT` magic `d00dfeed` occurs **once**, at DTB offset 36294656. No appended DTB on the kernel payload. CONFIRMED_BINARY.

Padding after kernel/ramdisk/DTB is zero. CONFIRMED_BINARY.

## 3. Payload identity

| Payload | SHA256 | Match |
|---|---|---|
| kernel | `359ce45988720f2b48764bde1683d4dcc6689224b97369ca0644c2f983b1e10f` | `Image` YES |
| ramdisk | `3485b221c76cbbfce66208b0eba1020223adc23f0cd0e526b4340595be4fba95` | `initramfs.cpio.gz` YES |
| DTB | `a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40` | `sm8250-xiaomi-thyme.dtb` YES |

`DTB_PAYLOAD_EXACT_MATCH = YES`

FDT totalsize (BE at +4) = 105960 = header.dtb_size. CONFIRMED_BINARY.

## 4. ARM64 Image header (kernel payload)

| Field | experimental v2 | stock boot.img kernel |
|---|---|---|
| starts `MZ` (EFI stub) | YES (`CONFIG_EFI_STUB=y`) | NO |
| text_offset | `0x0` | `0x80000` |
| image_size (incl. BSS) | 35782656 (> file 35101184) | 64008192 |
| flags | `0xa` (4K pages, phys anywhere) | `0xa` |
| magic | `ARM\x64` | `ARM\x64` |

head.S: byte0 is `ccmp` encoding `MZ`, then `b primary_entry`. Entering at Image start with Linux protocol (`x0=FDT`) is a valid ARM64 path. CONFIRMED_SOURCE (`linux-6.6/arch/arm64/kernel/head.S`, `efi-header.S`).

## 5. Why stock is v3 and this experiment is v2

LineageOS `BoardConfigCommon.mk`:

```
ifeq ($(PRODUCT_VIRTUAL_AB_OTA),true)
BOARD_BOOT_HEADER_VERSION := 3
else
BOARD_BOOT_HEADER_VERSION := 2
endif
BOARD_KERNEL_BASE := 0x00000000
BOARD_KERNEL_PAGESIZE := 4096
BOARD_INCLUDE_DTB_IN_BOOTIMG := true
BOARD_KERNEL_SEPARATED_DTBO := true
```

Thyme is Virtual A/B → stock/Lineage **boot v3** (kernel+ramdisk in `boot`, DTB+vendor cmdline in `vendor_boot`). v2 is the only AOSP header that still carries a DTB field inside `boot.img`. That is why the first experiment packed v2: minimum partitions, DTB under our control.

`fastboot boot → OKAY` only proves ABL accepted the download and started `BootLinux`. It does **not** prove v2 DTB handoff. See `docs/route-a-abl-evidence.md`.

v2 is therefore a **supported compatibility header ABL parses**, not a proven DTB/x0 handoff.

## 6. Address comparison

| Parameter | Stock vendor_boot v3 | LineageOS | experimental v2 | Match |
|---|---|---|---|---|
| header version (boot.img) | 3 | 3 if VAB, else 2 | 2 | no (intentional) |
| page_size | 4096 | 4096 | 4096 | yes |
| kernel_addr | `0x8000` | base `0x0` + default offset | `0x8000` | yes |
| ramdisk_addr | `0x01000000` | mkbootimg default | `0x01000000` | yes |
| tags_addr | `0x100` | mkbootimg default | `0x100` | yes |
| dtb_addr | `0x1f00000` | kona convention | `0x1f00000` | yes |
| DTB container | vendor_boot concatenated 4 FDTs | vendor_boot if v3 | boot v2 dtb field, 1 FDT | no |
| cmdline in boot.img | empty | v3 empty | stock vendor cmdline | v2 carries it |
| qcom,msm-id in DTB | `<0x164 0x20001>` on dtb0 | downstream | **absent** | **NO** |
| qcom,board-id in DTB | overlay `<45 0>` | dtbo | **absent** | **NO** |
| `__symbols__` | overlay yes | dtbo | **absent** | **NO** |

LineageOS does not set `BOARD_KERNEL_OFFSET` / `BOARD_DTB_OFFSET` in-tree; CI passed the stock vendor_boot numbers explicitly.

## 7. Physical memory / DTB load safety

If header addrs were copy destinations, kernel `[0x8000, 0x2181a00)` overlaps ramdisk at `0x1000000` and DTB at `0x1f00000`. With DRAM rebase `+0x80000000` the same overlaps remain, and those ranges sit inside stock `hyp`/`removed`.

Stock Android uses the **same** header addresses and boots. ABL therefore does **not** copy to those header fields.

Thyme ABL (`docs/route-a-abl-evidence.md`): `UpdateBootParams` computes Kernel/Ramdisk/DT windows from UEFI `KernelBaseAddr` / PCDs. `dtb_addr` is unused as a destination. DTB is copied to `DeviceTreeLoadAddr` (ramdisk_load − 2MiB − page).

```
DTB_LOAD_ADDRESS_SAFE = YES
```

Meaning: the header `dtb_addr` overlap is not a failure cause. Actual DTB RAM window is ABL-chosen, stock-proven. Do **not** retune `kernel_addr`/`dtb_addr` without a collision report against that ABL window.

Reserved-memory from stock DT (hyp, removed, pil_*, cont_splash) is Linux-after-handoff policy, not ABL copy-dest.

## 8. ARM64 boot protocol vs this image

Linux 6.6 `head.S` requires:

- MMU off, D-cache off
- `x0` = physical address of FDT
- callee-saved path stores `x0..x3` (`x21` = FDT)

ABL AArch64 jump: `kernel(DeviceTreeLoadAddr, 0, 0, 0)`.

| Requirement | experimental v2 vs ABL | Status |
|---|---|---|
| x0 = DTB | only if DTB selection succeeds | NOT_CONFIRMED on device |
| x1=x2=x3=0 | ABL passes zeros | CONFIRMED_SOURCE / CONFIRMED_BINARY strings |
| DTB 8-byte aligned | ABL relocates to its window | STRONG_INFERENCE |
| Image 2MB placement | flags bit3 = anywhere; text_offset 0 | acceptable IF ABL jumps to Image start |
| EFI stub | first insn is MZ/`ccmp` then `b primary_entry` | Linux protocol still valid |

`x1/x2/x3` protocol: compliant **if** the jump happens.

## 9. DTB contents relevant to ABL matching

`sm8250-xiaomi-thyme.dtb`:

- model `Xiaomi Mi 10S (thyme)`
- compatible `xiaomi,thyme` `qcom,sm8250`
- `arm,psci-1.0` `method = smc` (via `sm8250.dtsi`)
- **no** `qcom,msm-id`
- **no** `qcom,board-id`
- **no** `__symbols__`

Stock selection keys (`msm-id` 0x164/0x20001, board-id `<45 0>`) are missing. This is the leading static reason ABL can accept the v2 header and still never jump.
