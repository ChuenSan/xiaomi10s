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

Last device snapshot (user session; this session: no adb/fastboot device).

| Variable | A | B |
|---|---|---|
| current-slot | — | **b** |
| slot-successful | yes | no |
| slot-unbootable | no | no |
| slot-retry-count | 6 | **6** (was 7) |
| snapshot-update-status | none | none |
| is-userspace | no | no |
| kernel | uefi | uefi |
| unlocked | yes | yes |
| secure | yes | yes |
| anti | 1 | 1 |
| Device critical unlocked | true | true |
| Verity mode | true | true |

`has-slot:vbmeta` / `has-slot:vendor_boot` / `has-slot:dtbo` returning **Variable Not Found** does **not** mean the partitions are absent. GPT LUN 4 has `vbmeta_a/b`, `vendor_boot_a/b`, `dtbo_a/b`. `getvar all` already listed them. Xiaomi `has-slot:` is incomplete.

`has-slot:system:no` is Virtual A/B, expected. See §9.

---

## 3. Complete boot-critical B partition map

Physical `_b` partitions that sit on the Qualcomm boot chain or the official firmware train. From GPT + crclist. See map doc for LUN/size.

| Partition | LUN | Official flash target | Stock image | Currently on B |
|---|---|---|---|---|
| `xbl_b` | 2 | `xbl_ab` | `xbl.img` | UNKNOWN |
| `xbl_config_b` | 2 | `xbl_config_ab` | `xbl_config.img` | UNKNOWN |
| `aop_b` | 4 | `aop_ab` | `aop.img` | UNKNOWN |
| `tz_b` | 4 | `tz_ab` | `tz.img` | UNKNOWN |
| `hyp_b` | 4 | `hyp_ab` | `hyp.img` | UNKNOWN |
| `abl_b` | 4 | `abl_ab` | `abl.img` | UNKNOWN |
| `devcfg_b` | 4 | `devcfg_ab` | `devcfg.img` | UNKNOWN |
| `qupfw_b` | 4 | `qupfw_ab` | `qupfw.img` | UNKNOWN |
| `keymaster_b` | 4 | `keymaster_ab` | `keymaster.img` | UNKNOWN |
| `cmnlib_b` | 4 | `cmnlib_ab` | `cmnlib.img` | UNKNOWN |
| `cmnlib64_b` | 4 | `cmnlib64_ab` | `cmnlib64.img` | UNKNOWN |
| `uefisecapp_b` | 4 | `uefisecapp_ab` | `uefisecapp.img` | UNKNOWN |
| `imagefv_b` | 4 | `imagefv_ab` | `imagefv.img` | UNKNOWN |
| `featenabler_b` | 4 | `featenabler_ab` | `featenabler.img` | UNKNOWN |
| `boot_b` | 4 | `boot_ab` | `boot.img` | experimental-boot-v3.img |
| `vendor_boot_b` | 4 | `vendor_boot_ab` | `vendor_boot.img` | experimental-vendor_boot-v3.img |
| `dtbo_b` | 4 | `dtbo_ab` | `dtbo.img` | experimental-dtbo.img |
| `vbmeta_b` | 4 | `vbmeta_ab` | `vbmeta.img` | UNKNOWN (not written this Route B) |
| `vbmeta_system_b` | 0 | `vbmeta_system_ab` | `vbmeta_system.img` | UNKNOWN |

---

## 4. Stock ROM firmware inventory

See map doc §8. All Tier 0/1/2/3 images present in `MIUI14ROM/image/` were hashed this session. `super.img` not hashed (Tier 4, 9.1 GB, not needed for kernel-handoff).

---

## 5. Official flash-script behavior

Project tree has **no** `flash_all.sh`. Official `crclist.txt` / `sparsecrclist.txt` were recovered from the V14.0.6.0 tarball prefix.

Official Fastboot ROM writes **both slots** of every boot-critical firmware image (`*_ab`), plus payload and `super`. LineageOS `fw_update` writes the firmware subset (Tier 0/1/3) the same way.

Implication: a healthy factory/fastboot install has A and B firmware identical. A device that later only OTAs one slot, or that had only `boot_b`/`vendor_boot_b`/`dtbo_b` replaced, can diverge. **Unproven on this unit until hashed.**

---

## 6. A / B / Stock hash status

```text
FASTBOOT_PARTITION_READBACK = UNTESTED_THIS_SESSION
Device attached this session: NO
```

No `fastboot fetch` / oem dump attempted (forbidden undocumented readback). Next gate is Android A + root `sha256sum /dev/block/by-name/*_{a,b}`.

Status vocabulary: `MATCH_STOCK` `MATCH_A` `STALE_OR_DIFFERENT` `UNREADABLE` `UNKNOWN`.

| Partition | Stock SHA256 | Slot A | Slot B | A==Stock | B==Stock | A==B | Boot-critical | Status |
|---|---|---|---|---|---|---|---|---|
| xbl | `8a170d77…e6841a` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| xbl_config | `55d0220e…8fa567` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| aop | `1b160112…d52898` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| tz | `de0adae9…eb437b` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| hyp | `ad836145…5b7e44` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| abl | `1d14cad5…2c5cc2` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| devcfg | `9d2fd053…4a8800` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| qupfw | `a92a8e1d…059c1a` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| keymaster | `56467ce4…02d9b2` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| cmnlib | `fe0cbc87…9d2411` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| cmnlib64 | `377b9450…2c1d83` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| uefisecapp | `7ab0dffb…30d501` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| imagefv | `f4da4349…9ca07d` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| featenabler | `3426036b…edd57b` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| boot | `9d8c12c5…e3e9be` | UNKNOWN | `582f5b0c…576484` (experimental-boot-v3) | UNKNOWN | **no** | UNKNOWN | yes | B = STALE_OR_DIFFERENT vs stock (experiment) |
| vendor_boot | `aac7e11f…041972` | UNKNOWN | `62497ee8…c4b06d` (experimental-vendor_boot-v3) | UNKNOWN | **no** | UNKNOWN | yes | B = STALE_OR_DIFFERENT vs stock (experiment) |
| dtbo | `018fa85c…e64634` | UNKNOWN | `316c12d9…15d9c1` (experimental-dtbo) | UNKNOWN | **no** | UNKNOWN | yes | B = STALE_OR_DIFFERENT vs stock (experiment) |
| vbmeta | `37dfac44…0f9d9c` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |
| vbmeta_system | `32174550…8b8355` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | yes | UNKNOWN |

Different hash is **not** automatically “corrupt”. Experimental payload hashes are expected. Firmware `UNKNOWN` is the hole this audit exists to close.

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
- If B still holds an older XBL than the fused ARB while A has the current train, `set_active b` can fail **before** kernel: PBL rejects `xbl_b` or XBL refuses TZ/ABL. That is compatible with “immediate Fastboot” and with historical stock-payload-on-B failure.

Reached ABL fastboot with `current-slot:b` means **some** XBL+ABL executed. Whether that was `xbl_b`/`abl_b` or a fallback to A is UNKNOWN without hashes or bootloader logs.

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

Stock `vbmeta` **does** contain hash descriptors over `boot` / `dtbo` / `vendor_boot`. Route B experimental images **do not** match those digests. If ABL honors Flags=2, those descriptors are not used → experimental payload is not an AVB pre-kernel reject. If Xiaomi ABL ignores Flags=2, experimental payload **would** be rejected.

Historical stock-matching `boot_b`+`vendor_boot_b`+`dtbo_b`+`vbmeta_b` **also** failed. Those images **match** the descriptors. So AVB hash mismatch **cannot** be the explanation of `STOCK_BOOT_CORE_ON_B`.

```text
AVB_PRE_KERNEL_BLOCKER: POSSIBLE
```

POSSIBLE for the current experimental payload if ABL ignores Flags=2. UNLIKELY as the cause of the stock-core-on-B failure. Not CONFIRMED, not REFUTED. This round does not modify vbmeta.

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

This round did not produce a kernel-handoff. Changing Linux will not fix an unverified B firmware baseline. No Route B matrix (Mainline/Stock combinations) until `SLOT_B_FIRMWARE_BASELINE` is hashed.

---

## 11. Recommended B normalization set — DESIGN ONLY, do not flash

```text
STOCK_B_NORMALIZATION  is not authorized this round.
No partition list below is a flash command.
```

**Gate before any write:** Android A, root, read-only SHA256 of every row in §6. Flash **only** rows where B ≠ Stock, and only `*_b`. Never `*_a`. Never `*_ab`.

If hashes later show B firmware already equals this ROM, the set is **empty**. Do not flash “just in case”.

If hashes show B firmware ≠ this ROM, the **minimum same-ROM set** for a kernel-handoff control (not Android desktop) is:

| partition_b | image | size | SHA256 | reason | risk |
|---|---|---:|---|---|---|
| `xbl_b` | `xbl.img` | 3575808 | `8a170d77…e6841a` | PBL slot-B XBL | **high** — wrong XBL can fail before ABL; A remains rescue only if PBL falls back to LUN1. External rescue ROM required. |
| `xbl_config_b` | `xbl_config.img` | 102400 | `55d0220e…8fa567` | paired with XBL | high, with xbl_b |
| `aop_b` | `aop.img` | 204800 | `1b160112…d52898` | AOP same train | medium |
| `tz_b` | `tz.img` | 3190784 | `de0adae9…eb437b` | TZ/HYP coupling | **high** |
| `hyp_b` | `hyp.img` | 446464 | `ad836145…5b7e44` | with TZ | **high** |
| `abl_b` | `abl.img` | 208896 | `1d14cad5…2c5cc2` | ABL is the loader | medium-high |
| `devcfg_b` | `devcfg.img` | 57344 | `9d2fd053…4a8800` | TZ config | medium |
| `qupfw_b` | `qupfw.img` | 57344 | `a92a8e1d…059c1a` | official firmware train | low-medium |
| `keymaster_b` | `keymaster.img` | 282624 | `56467ce4…02d9b2` | official train | medium |
| `cmnlib_b` | `cmnlib.img` | 397312 | `fe0cbc87…9d2411` | QSEE libs | medium |
| `cmnlib64_b` | `cmnlib64.img` | 516096 | `377b9450…2c1d83` | QSEE libs | medium |
| `uefisecapp_b` | `uefisecapp.img` | 126976 | `7ab0dffb…30d501` | UEFI security | medium |
| `imagefv_b` | `imagefv.img` | 2097152 | `f4da4349…9ca07d` | XBL FV | medium |
| `featenabler_b` | `featenabler.img` | 90112 | `3426036b…edd57b` | official train | low-medium |

Do **not** include by default: `modem_b` `bluetooth_b` `dsp_b` `super` `mdtp_*` `vbmeta_*` (vbmeta only if hash says B is not the stock Flags=2 image). Payload restore (`boot_b`/`vendor_boot_b`/`dtbo_b` stock) is a **separate** control after firmware matches, to distinguish PRE_KERNEL_FAILURE from ANDROID_USERSPACE_FAILURE.

Historical stock payload on B already failed. Firmware hash is the missing control. Do not restore stock payload again until firmware hashes exist.

Observation for a future stock-B boot (no UART):

| Signal | PRE_KERNEL | KERNEL_HANDOFF / userspace |
|---|---|---|
| retry decrements, immediate Fastboot, no USB change | compatible | — |
| Android USB / charging UI / boot animation | — | kernel at least started |
| `minidump`/`rawdump` magic `Raw_Dmp!` after attempt | maybe XBL/HLOS crash dump | kernel/subsystem dump |
| `logdump`/`oops` non-zero vs previous hash | possible ABL/XBL log | possible kernel oops |

---

## 12. Remaining blockers

1. Slot B (and A) firmware SHA256 unknown. Device not attached. `set_active a` not approved this round.
2. `KERNEL_HANDOFF` still UNKNOWN.
3. External full rescue ROM is off-tree. Do not flash XBL/TZ/HYP/ABL until that is confirmed accessible.
4. `fastboot fetch` untested; do not hunt undocumented readback.

Not blockers: Virtual A/B mapper; need to change kernel/DTS; need to modify vbmeta this round; UART.

---

## 13. Final gate

```text
NOT_READY_FOR_STOCK_B_NORMALIZATION_TEST
```

Next gate (needs explicit user approval, still no `*_a` flash):

```text
1. fastboot set_active a          # metadata only; Slot A is the stable slot
2. reboot into Android A
3. su -c sha256sum /dev/block/by-name/{xbl,xbl_config,aop,tz,hyp,abl,devcfg,qupfw,keymaster,cmnlib,cmnlib64,uefisecapp,imagefv,featenabler,boot,vendor_boot,dtbo,vbmeta,vbmeta_system}_{a,b}
4. optional read-only dump inspect:
     hexdump -C -n 64 /dev/block/by-name/{oops,logdump,minidump,rawdump}
     sha256sum those four
     look for Raw_Dmp!; do not erase/format/dd-to-block
5. fill §6; only then decide a minimum *_b flash set
```

---

## Dump partitions — safe read (future)

| Name | GPT size | How to read | How to interpret |
|---|---:|---|---|
| `oops` | 16 MiB | `sha256sum` + first 64 bytes | empty/zero vs ramoops-like text |
| `logdump` | 64 MiB | same | bootloader/kernel log sink on some OEM builds |
| `minidump` | 96 MiB | same; parser: Qualcomm minidump / `Raw_Dmp!` | selected RAM regions after crash |
| `rawdump` | 128 MiB | same | larger ramdump; `persist.vendor.sys.rawdump_copy` only copies, this round must not set it if that writes |

`init.qcom.rc` already `chown`s `by-name/ramdump` and gates `emmc_dload` on `persist.vendor.sys.rawdump_copy`. Reading the block device is enough. Do not enable dload, do not format.

A pre-kernel ABL reject may write **nothing** here. Still the best no-UART artifact after an attempt.

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
CI added: NO (static analysis only)
```
