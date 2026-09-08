# Thyme stock slot partition map — V14.0.6.0.TGACNXM

Read-only. No flash, no erase, no Slot A writes.

Evidence markers: `CONFIRMED_STOCK` `CONFIRMED_GPT` `CONFIRMED_LINEAGE` `CONFIRMED_AOSP` `INFERRED` `UNKNOWN`.

Source ROM: `thyme_images_V14.0.6.0.TGACNXM_20230904.0000.00_13.0_cn` (MD5 `c97bf99cf1d342cc6a308218dfc734d3`). Project tree has a partial unpack at `MIUI14ROM/image/` (git-ignored). Official `flash_all.sh` / `flash_all.bat` are **not** in the project tree.

This round recovered the official CRC lists and GPT from the tarball prefix (scripts sit after multi-GB images; `flash_all.sh` itself was not extracted).

---

## 1. What the project ROM actually contains

`MIUI14ROM/image/` (CONFIRMED_STOCK listing):

```text
PRESENT     abl aop bluetooth boot cmnlib cmnlib64 cust devcfg dsp dtbo
            featenabler hyp imagefv keymaster modem qupfw super tz
            uefisecapp vbmeta vbmeta_system vendor_boot xbl xbl_config
            root.bat
ABSENT      flash_all.* flash_all_except_storage.* flash_all_lock.*
            gpt_*.bin rawprogram*.xml crclist.txt logo logfs misc
            persist metadata rescue userdata storsec spunvm multiimgoem
            mdtp mdtpsecapp
```

`root.bat` is a Magisk helper, not Xiaomi `flash_all`:

```bat
fastboot flash boot_ab magisk.img   OR   fastboot flash boot_ab boot.img
```

That is the only in-tree proof that this ROM generation uses the Xiaomi `_ab` fastboot alias. CONFIRMED_STOCK.

---

## 2. Official flash inventory (CRC lists)

Recovered from the official tarball `images/crclist.txt` and `images/sparsecrclist.txt` (CONFIRMED_STOCK, file date 2023-09-04).

Xiaomi `flash_all` always flashes `crclist` then `sparsecrclist`, then the partitions named in those lists. Partition names below are the exact `fastboot flash` targets.

### 2.1 `crclist.txt` — non-sparse images

| fastboot target | Slot form | Image in `MIUI14ROM/image/` | Boot-critical class |
|---|---|---|---|
| `xbl_ab` | both | `xbl.img` | Tier 0 |
| `xbl_config_ab` | both | `xbl_config.img` | Tier 0 |
| `aop_ab` | both | `aop.img` | Tier 1 |
| `tz_ab` | both | `tz.img` | Tier 1 |
| `hyp_ab` | both | `hyp.img` | Tier 1 |
| `abl_ab` | both | `abl.img` | Tier 1 |
| `devcfg_ab` | both | `devcfg.img` | Tier 1 |
| `qupfw_ab` | both | `qupfw.img` | Tier 1 |
| `keymaster_ab` | both | `keymaster.img` | Tier 1 |
| `cmnlib_ab` | both | `cmnlib.img` | Tier 1 |
| `cmnlib64_ab` | both | `cmnlib64.img` | Tier 1 |
| `uefisecapp_ab` | both | `uefisecapp.img` | Tier 1 |
| `imagefv_ab` | both | `imagefv.img` | Tier 1 |
| `featenabler_ab` | both | `featenabler.img` | Tier 1 |
| `boot_ab` | both | `boot.img` | Tier 2 |
| `vendor_boot_ab` | both | `vendor_boot.img` | Tier 2 |
| `dtbo_ab` | both | `dtbo.img` | Tier 2 |
| `vbmeta_ab` | both | `vbmeta.img` | Tier 2 |
| `vbmeta_system_ab` | both | `vbmeta_system.img` | Tier 2 |
| `modem_ab` | both | `modem.img` | Tier 3 |
| `bluetooth_ab` | both | `bluetooth.img` | Tier 3 |
| `dsp_ab` | both | `dsp.img` | Tier 3 |
| `multiimgoem_ab` | both | **missing** | firmware metadata, not kernel-handoff |
| `storsec` | none | **missing** | storage security, not kernel-handoff |
| `spunvm` | none | **missing** | UFS helper, not kernel-handoff |
| `misc` | none | **missing** | BCB, not firmware |
| `logfs` | none | **missing** | bootloader log FS |
| `logo` | none | **missing** | splash |

### 2.2 `sparsecrclist.txt` — sparse / userspace

| fastboot target | Slot form | Image | Class |
|---|---|---|---|
| `super` | none (virtual A/B inside) | `super.img` | Tier 4 |
| `cust` | none | `cust.img` | Tier 4 |
| `userdata` | none | **missing** | userdata |
| `rescue` | none | **missing** | rescue |
| `metadata` | none | **missing** | metadata |

`has-slot:system:no` is the expected Virtual A/B shape: `system`/`vendor`/`product`/`odm`/`system_ext` live inside `super`, not as physical `_b` partitions. CONFIRMED_STOCK GPT + CONFIRMED_ANDROID (`PRODUCT_VIRTUAL_AB_OTA` / `TARGET_IS_VAB := true`). Irrelevant to initramfs-only Linux.

---

## 3. `_ab` vs `_a`/`_b` vs unslotted

| Form | Meaning | Evidence |
|---|---|---|
| `foo_ab` | Xiaomi ABL alias: write the same image to `foo_a` **and** `foo_b` | `root.bat`; official `crclist.txt`; LineageOS thyme `fw_update` |
| `foo_a` / `foo_b` | physical slot partition | GPT LUN 1/2/4 (below) |
| no suffix | not A/B-ed | GPT + crclist (`storsec`, `logo`, `super`, dump partitions) |

AOSP `fastboot flash boot --slot all` is a different host-side mechanism. Xiaomi scripts use the bootloader-side `_ab` name. CONFIRMED_STOCK. This project must **never** use `_ab` for experiments: that would write Slot A. Slot B experiments use explicit `*_b` only.

---

## 4. LineageOS firmware-only subset

LineageOS wiki `devices/thyme/fw_update` (CONFIRMED_LINEAGE) flashes only:

```text
abl_ab aop_ab bluetooth_ab cmnlib_ab cmnlib64_ab devcfg_ab dsp_ab
featenabler_ab hyp_ab imagefv_ab keymaster_ab modem_ab qupfw_ab
tz_ab uefisecapp_ab xbl_ab xbl_config_ab
```

That is Tier 0 + Tier 1 + Tier 3. It does **not** flash `boot` / `vendor_boot` / `dtbo` / `vbmeta` / `super`. It is the OEM firmware train, not the Android payload.

Official `flash_all` is a superset: firmware + payload + sparse userspace.

---

## 5. UFS GPT map (CONFIRMED_GPT)

UFS logical sector = **4096** bytes (`rawprogram2.xml` `SECTOR_SIZE_IN_BYTES="4096"`). Parsed from official `gpt_both0.bin` / `gpt_both1.bin` / `gpt_backup4.bin` / `gpt_backup3.bin` / `gpt_both5.bin` / `rawprogram2.xml`.

| UFS LUN | File | Contents |
|---|---|---|
| 0 | `gpt_both0.bin` | `oops` `logdump` `minidump` `rawdump` `persist` `super` `cust` `vbmeta_system_a/b` `metadata` `rescue` `userdata` `misc` `logfs` `splash` … |
| 1 | `gpt_both1.bin` | `xbl_a` `xbl_config_a` |
| 2 | `rawprogram2.xml` | `xbl_b` `xbl_config_b` |
| 3 | `gpt_backup3.bin` | `cdt` `ddr` `mdmddr` (calibration, not payload) |
| 4 | `gpt_backup4.bin` | **all remaining A/B firmware + boot payload** (see table) |
| 5 | `gpt_both5.bin` | `modemst1/2` `fsg` `fsc` modem EFS |

PBL selects XBL from LUN 1 (slot A) or LUN 2 (slot B). XBL then loads TZ/HYP/ABL/boot from LUN 4 using the active slot suffix. CONFIRMED_GPT + CONFIRMED Qualcomm boot chain (PBL → XBL → ABL).

### 5.1 LUN 4 A/B firmware (the boot-critical table)

Sizes are GPT partition caps, not image sizes.

| Partition | GPT bytes | Mate | Official `*_ab` |
|---|---:|---|---|
| `xbl_*` | 8388608 (LUN 1/2) | `xbl.img` 3575808 | yes |
| `xbl_config_*` | 524288 (LUN 1/2) | `xbl_config.img` 102400 | yes |
| `aop_*` | 524288 | `aop.img` 204800 | yes |
| `tz_*` | 4194304 | `tz.img` 3190784 | yes |
| `hyp_*` | 8388608 | `hyp.img` 446464 | yes |
| `abl_*` | 2097152 | `abl.img` 208896 | yes |
| `devcfg_*` | 262144 | `devcfg.img` 57344 | yes |
| `qupfw_*` | 131072 | `qupfw.img` 57344 | yes |
| `keymaster_*` | 1048576 | `keymaster.img` 282624 | yes |
| `cmnlib_*` | 1048576 | `cmnlib.img` 397312 | yes |
| `cmnlib64_*` | 1048576 | `cmnlib64.img` 516096 | yes |
| `uefisecapp_*` | 2097152 | `uefisecapp.img` 126976 | yes |
| `imagefv_*` | 2097152 | `imagefv.img` 2097152 | yes |
| `featenabler_*` | 131072 | `featenabler.img` 90112 | yes |
| `boot_*` | 201326592 | `boot.img` 134217728 | yes |
| `vendor_boot_*` | 100663296 | `vendor_boot.img` 100663296 | yes |
| `dtbo_*` | 33554432 | `dtbo.img` 33554432 | yes |
| `vbmeta_*` | 131072 | `vbmeta.img` 8192 | yes |
| `modem_*` | 469762048 | `modem.img` 307769344 | yes |
| `bluetooth_*` | 1048576 | `bluetooth.img` 421888 | yes |
| `dsp_*` | 67108864 | `dsp.img` 67108864 | yes |
| `vbmeta_system_*` | 131072 (LUN 0) | `vbmeta_system.img` 4096 | yes |
| `mdtp_*` / `mdtpsecapp_*` | present | **no ROM image, not in crclist** | not official fastboot |
| `multiimgoem_*` | 32768 | **missing** | in crclist |
| `vm-linux_*` | 33554432 | not in crclist | not official fastboot |

### 5.2 LUN 0 dump / debug partitions (CONFIRMED_GPT)

| Partition | GPT bytes | Write this round |
|---|---:|---|
| `oops` | 16777216 | **forbidden** |
| `logdump` | 67108864 | **forbidden** |
| `minidump` | 100663296 | **forbidden** |
| `rawdump` | 134217728 | **forbidden** |

`init.qcom.rc` / `ueventd.qcom.rc` also name `ramdump` and `rawdump` as read-facing block nodes. CONFIRMED_ANDROID.

---

## 6. Boot-critical classification (evidence, not names)

Qualcomm cold-boot on SM8250 (Qualcomm Linux Boot Guide + LineageOS “Qualcomm’s Chain of Trust” + stock ELF version strings):

```text
BootROM/PBL  →  XBL (+ xbl_config)  →  TZ + HYP + AOP
             →  ABL (UEFI LinuxLoader, kernel:uefi)
             →  AVB vbmeta
             →  boot + vendor_boot + dtbo
             →  kernel handoff (x0 = FDT)
```

| Tier | Partitions | Why | Evidence |
|---|---|---|---|
| 0 pre-ABL | `xbl` `xbl_config` | PBL authenticates and executes these. Slot-specific LUNs. Wrong-slot XBL is a pre-kernel failure. | Qualcomm boot guide; GPT LUN 1/2; `QC_IMAGE_VERSION_STRING=BOOT.XF.3.2-00304-SM8250-2` |
| 1 secure/boot FW | `aop` `tz` `hyp` `abl` `devcfg` `qupfw` `keymaster` `cmnlib` `cmnlib64` `uefisecapp` `imagefv` `featenabler` | XBL loads TZ/HYP/AOP then ABL. ABL is the fastboot/AVB/DTB loader (`getvar kernel:uefi`). `devcfg`/`cmnlib*`/`keymaster`/`uefisecapp`/`imagefv`/`featenabler` are in both official `crclist` and LineageOS `fw_update`. | crclist; LineageOS fw_update; TZ/HYP `QC_IMAGE_VERSION_STRING=TZ.XF.5.8-00226`; `OEM_enable_bootup_from_a_b_partition` in tz/devcfg |
| 2 payload | `boot` `vendor_boot` `dtbo` `vbmeta` `vbmeta_system` | ABL loads these after firmware. Needed for **stock control** kernel handoff. `vbmeta_system` is userspace-chain; kept here because historical B control flashed it. | stock-rom-analysis; avbtool this session |
| 3 peripheral | `modem` `bluetooth` `dsp` | Slotselect in fstab; not on the ABL→kernel path. Official flash_all writes them; LineageOS fw_update does too. Not required to prove kernel handoff. | fstab_AB.qcom `slotselect`; no modem PIL in stock DT |
| 4 Android dynamic | `super` → system/vendor/product/odm/system_ext + `cust` | Virtual A/B. Initramfs-only Linux does not mount them. | `has-slot:system:no`; BoardConfig `BOARD_SUPER_PARTITION_*`; fstab `logical` |

`mdtp`/`mdtpsecapp` exist as slotted GPT entries and in `getvar all`, but they are **not** in official `crclist` and **not** in LineageOS `fw_update`. They are not part of the official fastboot firmware train. Do not flash them for baseline.

---

## 7. Official `flash_all` reconstructed behavior

`flash_all.sh` was not recovered this round. Behavior below is reconstructed from the CRC lists + GPT + Xiaomi VAB script template. Marked `CONFIRMED_STOCK` where the CRC/GPT names the partition; `INFERRED` for script order.

Official full fastboot ROM **does** write A/B boot-critical firmware, to **both** slots, via `_ab`:

```text
Tier 0  xbl_ab  xbl_config_ab
Tier 1  aop_ab tz_ab hyp_ab abl_ab devcfg_ab qupfw_ab
        keymaster_ab cmnlib_ab cmnlib64_ab uefisecapp_ab
        imagefv_ab featenabler_ab
Tier 2  boot_ab vendor_boot_ab dtbo_ab vbmeta_ab vbmeta_system_ab
Tier 3  modem_ab bluetooth_ab dsp_ab
Tier 4  super cust (+ userdata/metadata/rescue on flash_all, not except_storage)
```

It does **not** (from crclist) flash `mdtp`, `oops`, `logdump`, `minidump`, `rawdump`.

Xiaomi `flash_all` also typically: product check, `anti` vs `anti_version.txt`, `set_active a`, reboot. `INFERRED` from sibling VAB scripts; not executed, not required this round.

---

## 8. Stock image inventory (Tier 0/1/2/3 present files)

SHA256 of `MIUI14ROM/image/` this session. Images were not modified.

| File | Size | SHA256 |
|---|---:|---|
| `xbl.img` | 3575808 | `8a170d774226c03d9657883058a512f80e96ea76db0be81ff73c4f6340e6841a` |
| `xbl_config.img` | 102400 | `55d0220ea5e22b3fcf3e9db0e6fbec1aa575d23b6ce6ad53f1af2b61078fa567` |
| `aop.img` | 204800 | `1b1601129a56465cbfd3264582639894859aadcbba4c434ab7ac1648a3d52898` |
| `tz.img` | 3190784 | `de0adae9c8a27f9ac11722e693f5813afcaaa759a2b0d451b32a812b0eeb437b` |
| `hyp.img` | 446464 | `ad836145e9b04ce482aeabba6140506facaf97653d85429c2503d1d0655b7e44` |
| `abl.img` | 208896 | `1d14cad5e62d963c88e24aa8dab50b577a0f8d0b39323127b5f1677feb2c5cc2` |
| `devcfg.img` | 57344 | `9d2fd053ddf024e887b506a074643e8559e42fd7b8a7f447c1944fecf04a8800` |
| `qupfw.img` | 57344 | `a92a8e1d836b90c328f1d6ae1c6be3b9741140058a371a3cea692679ad059c1a` |
| `keymaster.img` | 282624 | `56467ce45b7a5add2f347ee16e67abc6c44e6f3df89ba400201a52030e02d9b2` |
| `cmnlib.img` | 397312 | `fe0cbc87a1cc72a2ef3b6ee7dd81e06a8c444f04bb3ab1db63f810536f9d2411` |
| `cmnlib64.img` | 516096 | `377b94503b57397aef7ef4dc8b402ac94f9da1d9e76a3032b0b81c678a2c1d83` |
| `uefisecapp.img` | 126976 | `7ab0dffbe048f3bb142fbc1d1ebed8fa9d1dd81abdde092b6d94ca8da930d501` |
| `imagefv.img` | 2097152 | `f4da43497158ff49de61e3b65bccc6a42f4abc51262b1b1214cf1d87da9ca07d` |
| `featenabler.img` | 90112 | `3426036bce03fcfbcc0924ef4f5724f5862720eb305bfec2fb3f739452edd57b` |
| `boot.img` | 134217728 | `9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be` |
| `vendor_boot.img` | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| `dtbo.img` | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |
| `vbmeta.img` | 8192 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` |
| `vbmeta_system.img` | 4096 | `3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355` |
| `modem.img` | 307769344 | `6c762fa267d12f7011a9ba6170532e5e3c1bb35c8324a522a8f892e54ee85f8f` |
| `bluetooth.img` | 421888 | `c23fd3fa5557c59452e3faf635b35af0266bef55e33d086d9076299ba0e17196` |
| `dsp.img` | 67108864 | `ad87cad498de7992803941869fa0db29afc9f824946dea351694a66618979ae7` |

Firmware version strings (CONFIRMED_STOCK ELF):

```text
xbl   QC=BOOT.XF.3.2-00304-SM8250-2  also embeds TZ.XF.5.8-00032
      OEM=pangu-build-bp-15713-thg85-17ntf-g2sn2  UUID=20230904_1009
aop   QC=AOP.HO.2.0-00187  same OEM build  UUID=20230904_0959
tz    QC=TZ.XF.5.8-00226
hyp   QC=TZ.XF.5.8-00226   (same TZ train as tz.img)
```

XBL carrying `TZ.XF.5.8-00032` while `tz.img`/`hyp.img` are `TZ.XF.5.8-00226` is in-image coupling metadata, not proof of mismatch on device. It does show XBL and TZ are version-coupled on this platform. CONFIRMED_STOCK strings.

---

## 9. Answer: what does official fastboot ROM write?

When Xiaomi updates thyme with this Fastboot ROM, it writes **all Tier 0/1/2/3 slotted firmware to both A and B**, plus `super`/`cust` and (on `flash_all`) userdata/metadata/rescue.

It does **not** leave Slot B’s XBL/ABL/TZ as “whatever was there”. A device that only ever received OTA to Slot A, or that had Slot B payload replaced without firmware, can have **stale B firmware**. That hypothesis is now the first thing to hash, not to guess.
