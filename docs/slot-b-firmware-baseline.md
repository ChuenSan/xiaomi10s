# Slot B firmware baseline — thyme / SM8250

Read-only forensics. No kernel/DTS/initramfs/image edits. No device writes this round. Slot A protected.

Companion map: `docs/thyme-stock-slot-partition-map.md`.

---

## 1. Route B failure classification

```text
BOOTLOADER_ATTEMPTED_B:          YES
KERNEL_HANDOFF:                  UNKNOWN
CURRENT_CLASSIFICATION:        PRE_KERNEL_SUSPECTED
```

Evidence:

- Before reboot: `slot-retry-count:b = 7`. After: `6`. AOSP boot-control: an unsuccessful slot decrements retry. CONFIRMED_AOSP + CONFIRMED device getvar.
- After: `current-slot:b`, `slot-successful:b:no`, `slot-unbootable:b:no`. Slot B was tried and is still bootable.
- `is-userspace:no` `kernel:uefi` → host is talking to ABL fastboot, not fastbootd. Some XBL+ABL ran.
- No Route-A-style brief black screen; back to Fastboot quickly; no mainline USB gadget. This is **not** proof of a mainline kernel panic. It is also not proof that ABL completed kernel handoff.

Cannot claim “B never started”. Cannot claim “mainline kernel crashed”.

Historical control: matching-stock `boot_b` + `vendor_boot_b` + `dtbo_b` + `vbmeta_b` + `vbmeta_system_b` also returned to Fastboot. Payload-only is not the only variable. `STOCK_BOOT_CORE_ON_B = FAILED historically`.

---

## 2. B slot metadata

Live Fastboot snapshot 2026-09-08 (this session, serial `41a5627b`, `is-userspace:no`). No writes. `set_active` not run this session.

| Variable | A | B |
|---|---|---|
| current-slot | **a** (live) | was **b** after the Route B attempt |
| slot-successful | yes | no |
| slot-unbootable | no | no |
| slot-retry-count | 6 | **6** (was 7 at attempt; still 6) |
| snapshot-update-status | none | none |
| is-userspace | no | no |
| kernel | uefi | uefi |
| unlocked | yes | yes |
| secure | yes | yes |
| anti | 1 | 1 |
| Device critical unlocked | true | true |
| Verity mode | true | true |
| hw-revision | 20001 (kona v2.1) | same |
| variant | SM8 UFS | same |
| logical-block-size | 0x1000 | same |
| get_unlock_ability | 1 | same |

Retry still 6 and `unbootable:b:no` ⇒ this is **not** AOSP retry-exhaust fallback. Returning `current-slot:a` happened by an explicit `set_active a` (user or earlier session), not by burning retries to 0.

`has-slot:boot:yes` `has-slot:modem:yes` `has-slot:system:no`.  
`has-slot:vbmeta` / `vendor_boot` / `dtbo` / `xbl` / `abl` / `tz` / `hyp` / `aop` = **Variable Not Found**. Those partitions **exist**: live `partition-size:*_{a,b}` matches GPT LUN 1/2/4 (CONFIRMED_LIVE). Xiaomi `has-slot:` is incomplete.

`has-slot:system:no` is Virtual A/B, expected. See §9.

### 2.1 Live partition-size vs GPT

All boot-critical `_a`/`_b` names exist. Sizes equal GPT except `xbl_config_*`: GPT 524288 (128 × 4096), ABL getvar `0x7F5000` (8343552). Treat GPT as layout; ABL is reporting LUN remainder after `xbl`. Stock `xbl_config.img` is 102400 B, far below both.

Dump partitions live: `oops` 16 MiB, `logdump` 64 MiB, `minidump` 96 MiB, `rawdump` 128 MiB. Hashed from Android A; see dump section.

---

## 3. Complete boot-critical B partition map

Physical `_b` partitions that sit on the Qualcomm boot chain or the official firmware train. From GPT + crclist. See map doc for LUN/size.

| Partition | LUN | Official flash target | Stock image | Currently on B |
|---|---|---|---|---|
| `xbl_b` | 2 | `xbl_ab` | `xbl.img` | MATCH_STOCK |
| `xbl_config_b` | 2 | `xbl_config_ab` | `xbl_config.img` | MATCH_STOCK |
| `aop_b` | 4 | `aop_ab` | `aop.img` | MATCH_STOCK |
| `tz_b` | 4 | `tz_ab` | `tz.img` | MATCH_STOCK |
| `hyp_b` | 4 | `hyp_ab` | `hyp.img` | MATCH_STOCK |
| `abl_b` | 4 | `abl_ab` | `abl.img` | MATCH_STOCK |
| `devcfg_b` | 4 | `devcfg_ab` | `devcfg.img` | MATCH_STOCK |
| `qupfw_b` | 4 | `qupfw_ab` | `qupfw.img` | MATCH_STOCK |
| `keymaster_b` | 4 | `keymaster_ab` | `keymaster.img` | MATCH_STOCK |
| `cmnlib_b` | 4 | `cmnlib_ab` | `cmnlib.img` | MATCH_STOCK |
| `cmnlib64_b` | 4 | `cmnlib64_ab` | `cmnlib64.img` | MATCH_STOCK |
| `uefisecapp_b` | 4 | `uefisecapp_ab` | `uefisecapp.img` | MATCH_STOCK |
| `imagefv_b` | 4 | `imagefv_ab` | `imagefv.img` | MATCH_STOCK |
| `featenabler_b` | 4 | `featenabler_ab` | `featenabler.img` | MATCH_STOCK |
| `boot_b` | 4 | `boot_ab` | `boot.img` | experimental-boot-v3 CONFIRMED |
| `vendor_boot_b` | 4 | `vendor_boot_ab` | `vendor_boot.img` | experimental-vendor_boot-v3 CONFIRMED |
| `dtbo_b` | 4 | `dtbo_ab` | `dtbo.img` | experimental-dtbo CONFIRMED |
| `vbmeta_b` | 4 | `vbmeta_ab` | `vbmeta.img` | flags=3, not stock |
| `vbmeta_system_b` | 0 | `vbmeta_system_ab` | `vbmeta_system.img` | MATCH_STOCK |

---

## 4. Stock ROM firmware inventory

See map doc §8. All Tier 0/1/2/3 images present in `MIUI14ROM/image/` were hashed this session. `super.img` not hashed (Tier 4, 9.1 GB, not needed for kernel-handoff).

---

## 5. Official flash-script behavior

Project tree has **no** `flash_all.sh`. Official `crclist.txt` / `sparsecrclist.txt` were recovered from the V14.0.6.0 tarball prefix.

Official Fastboot ROM writes **both slots** of every boot-critical firmware image (`*_ab`), plus payload and `super`. LineageOS `fw_update` writes the firmware subset (Tier 0/1/3) the same way.

Implication: a healthy factory/fastboot install has A and B firmware identical. **This unit: live Android-A root hashes show Tier 0/1 firmware A == B == V14.0.6.0.TGACNXM stock.** Stale-B-firmware as the Route B pre-kernel cause is **REFUTED**.

---

## 6. A / B / Stock hash status

```text
FASTBOOT_PARTITION_READBACK = UNSUPPORTED
ANDROID_A_ROOT_HASH = DONE  (2026-09-08, Magisk 26.4-kitsune, slot_suffix=_a, fingerprint V14.0.6.0.TGACNXM)
```

Method: `sha256sum` of the whole block device (A==B), plus `dd count=1 bs=<stock_image_size> | sha256sum` (vs ROM). Stock images are smaller than GPT except `imagefv` / `vendor_boot` / `dtbo`. Full-partition hash ≠ file hash when padding exists; prefix hash is the ROM comparison.

Status vocabulary: `MATCH_STOCK` `MATCH_A` `STALE_OR_DIFFERENT` `UNREADABLE` `UNKNOWN`.

Hashes below are **stock-image-sized prefixes** except where noted. Raw logs: `work/slot-b-baseline/android-a/` (git-ignored).

| Partition | Stock SHA256 | Slot A prefix | Slot B prefix | A==Stock | B==Stock | A==B (full part.) | Boot-critical | Status |
|---|---|---|---|---|---|---|---|---|
| xbl | `8a170d77…e6841a` | `8a170d77…e6841a` | `8a170d77…e6841a` | yes | yes | yes | yes | MATCH_STOCK |
| xbl_config | `55d0220e…8fa567` | `55d0220e…8fa567` | `55d0220e…8fa567` | yes | yes | yes | yes | MATCH_STOCK |
| aop | `1b160112…d52898` | `1b160112…d52898` | `1b160112…d52898` | yes | yes | yes | yes | MATCH_STOCK |
| tz | `de0adae9…eb437b` | `de0adae9…eb437b` | `de0adae9…eb437b` | yes | yes | yes | yes | MATCH_STOCK |
| hyp | `ad836145…5b7e44` | `ad836145…5b7e44` | `ad836145…5b7e44` | yes | yes | yes | yes | MATCH_STOCK |
| abl | `1d14cad5…2c5cc2` | `1d14cad5…2c5cc2` | `1d14cad5…2c5cc2` | yes | yes | yes | yes | MATCH_STOCK |
| devcfg | `9d2fd053…4a8800` | `9d2fd053…4a8800` | `9d2fd053…4a8800` | yes | yes | yes | yes | MATCH_STOCK |
| qupfw | `a92a8e1d…059c1a` | `a92a8e1d…059c1a` | `a92a8e1d…059c1a` | yes | yes | yes | yes | MATCH_STOCK |
| keymaster | `56467ce4…02d9b2` | `56467ce4…02d9b2` | `56467ce4…02d9b2` | yes | yes | yes | yes | MATCH_STOCK |
| cmnlib | `fe0cbc87…9d2411` | `fe0cbc87…9d2411` | `fe0cbc87…9d2411` | yes | yes | yes | yes | MATCH_STOCK |
| cmnlib64 | `377b9450…2c1d83` | `377b9450…2c1d83` | `377b9450…2c1d83` | yes | yes | yes | yes | MATCH_STOCK |
| uefisecapp | `7ab0dffb…30d501` | `7ab0dffb…30d501` | `7ab0dffb…30d501` | yes | yes | yes | yes | MATCH_STOCK |
| imagefv | `f4da4349…9ca07d` | `f4da4349…9ca07d` | `f4da4349…9ca07d` | yes | yes | yes | yes | MATCH_STOCK |
| featenabler | `3426036b…edd57b` | `3426036b…edd57b` | `3426036b…edd57b` | yes | yes | yes | yes | MATCH_STOCK |
| boot | `9d8c12c5…e3e9be` | `653cd225…4c7f2e` (Magisk 26.4-kitsune) | exp `582f5b0c…576484` at 36294656 B | no | no | no | yes | A Magisk; B experimental-boot-v3 CONFIRMED |
| vendor_boot | `aac7e11f…041972` | `aac7e11f…041972` | exp `62497ee8…c4b06d` at 114688 B | yes | no | no | yes | A MATCH_STOCK; B experimental CONFIRMED |
| dtbo | `018fa85c…e64634` | `018fa85c…e64634` | exp `316c12d9…15d9c1` at 387 B | yes | no | no | yes | A MATCH_STOCK; B experimental CONFIRMED |
| vbmeta | `37dfac44…0f9d9c` | `37dfac44…0f9d9c` flags=**2** | `9c632a60…b2c5c0` flags=**3** | yes | no | no | yes | A MATCH_STOCK; B STALE_OR_DIFFERENT |
| vbmeta_system | `32174550…8b8355` | `32174550…8b8355` flags=0 | `32174550…8b8355` flags=0 | yes | yes | yes | yes | MATCH_STOCK |

`xbl_b` lives on `sdc1` (LUN 2), `xbl_a` on `sdb1` (LUN 1). Content still identical.

Different hash is not “corrupt”: Magisk `boot_a` and Route B experimental images are expected. **vbmeta_b flags=3** is `HASHTREE_DISABLED|VERIFICATION_DISABLED` (Magisk/`--disable-verity --disable-verification` style). Stock is flags=2 only. Patching the signed header likely invalidates the RSA signature. AOSP libavb still skips descriptors if bit 1 is set; Xiaomi ABL may still reject a broken signature. Historical stock-core-on-B flashed stock vbmeta (flags=2) and still failed — so flags=3 is a current-B difference, not the explanation of that older control.

---

## 7. Firmware-version consistency

```text
anti:1     Xiaomi/Qualcomm anti-rollback index on device. Do not change it.
secure:yes SoC secure-boot capable/enabled (PBL verifies XBL). Not the same as AVB.
unlocked:yes  bootloader unlock. Allows unsigned payload; does not disable PBL→XBL auth.
```

Version coupling (CONFIRMED_STOCK strings + Qualcomm chain):

- XBL, TZ, HYP, AOP from this ROM share Xiaomi build `pangu-build-bp-15713-thg85-17ntf-g2sn2` / date 20230904.
- TZ and HYP are the same QC train `TZ.XF.5.8-00226`.
- XBL image also contains `TZ.XF.5.8-00032` — XBL/TZ are coupled; mixing trains is a known Qualcomm/OEM brick class.
- Xiaomi `flash_all` refuses to flash if device `anti` > ROM `anti_version.txt`. Flashing **older** firmware than the device anti-index is rejected. Flashing **matching** V14.0.6.0 onto B is the intended control, not a downgrade, **if** A already runs that ROM.
- If B still holds an older XBL than the fused ARB while A has the current train, `set_active b` can fail **before** kernel. **Live hashes: B XBL/TZ/HYP/ABL == A == this ROM. That hypothesis is REFUTED on this unit.**

Reached ABL fastboot with `current-slot:b` means **some** XBL+ABL executed. Given `xbl_b==xbl_a` and `abl_b==abl_a`, slot-B firmware train is the same as the working Slot A train.

Do not modify anti-rollback fuses.

---

## 8. AVB analysis

Re-run this session (`python3 work/tools/avbtool.py info_image`):

```text
vbmeta.img
  Algorithm: SHA256_RSA2048
  Rollback Index: 0
  Flags: 2
  Chain: vbmeta_system (rollback location 2)
  Hash descriptors: boot, dtbo, vendor_boot
  Hashtree: mi_ext, odm, vendor

vbmeta_system.img
  Flags: 0
  Rollback Index: 1693526400
  Hashtree: product, system, system_ext
```

`work/tools/avbtool.py` (AOSP avbtool 1.3.0 in-tree):

```text
AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED = 1        # bit 0
AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED = 2   # bit 1
```

AOSP `avb_slot_verify.c` (android.googlesource.com/platform/external/avb):

```text
if (vbmeta_header.flags & AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED) {
    /* VERIFICATION_DISABLED bit is set.
       load_requested_partitions() without parsing descriptors.
       goto out; */
}
```

Flag **2** means: do **not** parse hash/hashtree/chain descriptors for verification. It is **not** “hashtree disabled” (that is flag 1) and **not** “flags 3” (both bits, LineageOS `BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 3`).

Distinct getvar concepts:

| Variable | Meaning |
|---|---|
| `secure:yes` | Qualcomm secure boot (PBL/XBL). Independent of AVB flags. |
| `unlocked:yes` | Bootloader unlock. AVB `allow_verification_error` path. |
| `Device critical unlocked=true` | critical-partition unlock, not vbmeta flags |
| `Verity mode=true` | dm-verity policy presentation; `vbmeta_system` flags=0 still carries hashtrees. Userspace. |
| vbmeta Flags=2 | libavb: skip descriptor verification |

Live on-device (xxd offset 0x78, 2026-09-08):

```text
vbmeta_a flags = 2     MATCH stock ROM   signed flags=2
vbmeta_b flags = 3     NOT stock         HASHTREE_DISABLED|VERIFICATION_DISABLED
vbmeta_system_a/b flags = 0  MATCH stock
ro.boot.verifiedbootstate = orange   (unlocked)
```

Flags=3 still has bit 1, so AOSP libavb still skips descriptors. Changing flags inside a signed header typically **breaks the RSA signature**. Unlocked ABL may still load; Xiaomi ABL may reject the vbmeta image before reading flags. That is a current-B-only difference.

Historical `STOCK_BOOT_CORE_ON_B` claimed stock `vbmeta_b` (flags=2) and still Fastboot. Hash mismatch of experimental payload therefore **cannot** explain that older control. It **can** still matter for the current experimental images sitting next to flags=3 vbmeta_b.

```text
AVB_PRE_KERNEL_BLOCKER: POSSIBLE
```

Firmware-stale is no longer the leading hypothesis. Do not modify vbmeta this round.

---

## 9. Virtual A/B conclusion

```text
dynamic *_b mapper relevance to current pre-kernel failure: NONE
```

`has-slot:system:no` is normal. `snapshot-update-status:none` — no pending snapshot merge. Initramfs-only path is ABL → Image → DTB → initramfs. It does not mount `system`/`vendor`/`product`. Do not use `/dev/block/mapper` absence as a pre-kernel explanation.

---

## 10. Mainline conclusion

```text
Evidence that kernel/DTS must change: NO
```

This round did not produce a kernel-handoff. Tier 0/1 firmware on B **matches stock**. Changing Linux/DTS still has no evidence. Do not run a Mainline/Stock matrix to paper over ABL/AVB.

---

## 11. Recommended B normalization set — DESIGN ONLY, do not flash

```text
STOCK_B_FIRMWARE_FLASH_SET = empty
Do not flash xbl_b/tz_b/hyp_b/abl_b/… — they already MATCH_STOCK.
Never *_a. Never *_ab.
```

Optional **payload/AVB control** (not firmware), only if later approved:

| partition_b | image | size | SHA256 | reason | risk |
|---|---|---:|---|---|---|
| `vbmeta_b` | `vbmeta.img` | 8192 | `37dfac44…0f9d9c` | restore flags=2 signed stock; current flags=3 | medium — AVB control, Slot A untouched |
| `boot_b` | `boot.img` | 134217728 | `9d8c12c5…e3e9be` | stock payload control on proven firmware | low-medium |
| `vendor_boot_b` | `vendor_boot.img` | 100663296 | `aac7e11f…041972` | with boot_b | low-medium |
| `dtbo_b` | `dtbo.img` | 33554432 | `018fa85c…e64634` | with boot_b | low-medium |

That is a **stock payload re-control**, not firmware normalization. Historical STOCK_BOOT_CORE_ON_B already failed; it is only worth repeating now that firmware hashes exist. Do not execute this round.

---

## 12. Remaining blockers

1. `KERNEL_HANDOFF` still UNKNOWN. No mainline USB, no mainline dump.
2. `vbmeta_b` is flags=3, not stock flags=2. AVB still POSSIBLE for the current experiment.
3. Historical stock payload-on-B failure is unexplained by firmware (firmware now proven matching). ABL slot-B policy still open.
4. `oops`/`minidump` only contain **stock 4.19** kernel on slot `_a`, not mainline.

Not blockers: stale XBL/TZ/HYP/ABL on B (REFUTED); Virtual A/B mapper; kernel/DTS change; UART; flashing firmware “just in case”.

---

## 13. Final gate

```text
NOT_READY_FOR_STOCK_B_NORMALIZATION_TEST
```

Firmware on B already matches V14.0.6.0.TGACNXM. A firmware-flash “normalization” would be unjustified. Next experiment, if any, is a **payload/vbmeta_b control**, and only after explicit approval.

---

## Dump partitions — live read 2026-09-08

Read-only. No erase/format/dload enable.

| Name | Header | Full SHA256 | Interpretation |
|---|---|---|---|
| `oops` | stock kmsg, Index 1137, Reason Restart, **2026-09-08 08:37:22**, `slot_suffix=_a`, kernel 4.19.157-perf | `3a45d146…a7b1aa` | Android A reboot after Fastboot, not mainline |
| `logdump` | first 64 B zero | `3b6a07d0…421351` | not empty overall; no mainline string in header |
| `minidump` | `cigamgol` / `Raw_Dmp!` | `276099a3…89c778` | Qualcomm minidump of **stock** `Linux version 4.19.157-perf-g9d90dd04aa7c` thyme, not 6.6 |
| `rawdump` | first 64 B zero | `254bcc3f…453917` | not parsed further |

`init.qcom.rc` `chown`s `by-name/ramdump`. Reading is enough. Do not set `persist.vendor.sys.rawdump_copy`.

---

## Constraint log this round

```text
Local compilation: NO
Local build: NO
Kernel/DTS/initramfs/Route B image modified: NO
Slot A flash/erase/format: NO
Slot B write: NO
vbmeta write: NO
UART used: NO
CI added: NO
Android A root read: YES (sha256sum / xxd / strings only)
```
