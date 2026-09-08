# Route B verified Pure Stock Slot B control — thyme

Stage: `ROUTE_B_VERIFIED_STOCK_B_CONTROL`  
Date: 2026-09-08  
Parent: `f3a9536` (`route-b-v3`)

Single variable vs previous AVB round: restore official V14.0.6.0.TGACNXM `boot_b` + `vendor_boot_b` + `dtbo_b`.  
Do not rebuild Linux/DTS/images. Do not write `vbmeta_b` / `vbmeta_system_b` / firmware / any `*_a`.

---

## 1. Constraint compliance

```text
Local compilation: NO
Local build: NO
Slot A flashed: NO
Slot A modified: NO
B partitions written: boot_b, vendor_boot_b, dtbo_b
vbmeta_b: NO WRITE (left stock flags=2)
vbmeta_system_b: NO WRITE (stock)
firmware_b: NO WRITE
```

---

## 2. Previous-round close

Committed `docs/route-b-avb-control.md` as `f3a9536` (`docs: record Route B AVB control result`).

---

## 3. Android A preflight

```text
adb:                 41a5627b device  product:thyme
ro.boot.slot_suffix: _a
fingerprint:         Xiaomi/thyme/thyme:13/TKQ1.220829.002/V14.0.6.0.TGACNXM:user/release-keys
root:                uid=0 magisk 26.4-kitsune
sys.boot_completed:  1
verifiedbootstate:   orange
```

---

## 4. Official V14.0.6.0.TGACNXM files (re-hashed this round)

`MIUI14ROM/image/` (git-ignored). SHA256 of the actual files:

| File | Bytes | SHA256 |
|---|---:|---|
| boot.img | 134217728 | `9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be` |
| vendor_boot.img | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| dtbo.img | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |
| vbmeta.img | 8192 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` |
| vbmeta_system.img | 4096 | `3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355` |

Matches the historical record. Not trusted from memory alone.

---

## 5. Live Slot B before flash

Android A Magisk root, stock-image-sized prefixes plus experimental-sized prefixes.

| Partition | Expect | Result |
|---|---|---|
| boot_b @36294656 | Route B v3 | `582f5b0c…576484` MATCH experimental-boot-v3 |
| vendor_boot_b @114688 | Route B v3 | `62497ee8…c4b06d` MATCH experimental-vendor_boot-v3 |
| dtbo_b @387 | Route B v3 | `316c12d9…15d9c1` MATCH experimental-dtbo |
| vbmeta_b @8192 | stock flags=2 | `37dfac44…0f9d9c` MATCH, flags byte `02` |
| vbmeta_system_b @4096 | stock | `32174550…8b8355` MATCH |
| xbl_b @3575808 | stock | `8a170d77…e6841a` MATCH |
| abl_b @208896 | stock | `1d14cad5…2c5cc2` MATCH |
| tz_b @3190784 | stock | `de0adae9…eb437b` MATCH |

Firmware A==B==stock unchanged. Not written.

---

## 6. Dump / misc baseline (read-only)

```text
oops      d3a0027e29e43603b707ffcbb9157d866cec2186f5e3376c015120ce2d255e47
minidump  276099a32ae5f3cb2a1f5bfae9f887954c300c7144260892f314879ed689c778
rawdump   254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
logdump   3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
misc 64KiB SHA256  ccfeffb08df638cef3d2e20dd0cb1234ff510d4f13f1e5a97b8977d148770953
misc[0:32] ASCII   bootonce-bootloader
```

`misc` was not written. BCB command field already held `bootonce-bootloader` before this test.

---

## 7. Fastboot preflight (before payload write)

```text
product:                 thyme
unlocked:                yes
current-slot:            a
snapshot-update-status:  none
slot-unbootable:b:       no
slot-retry-count:b:      6
battery-soc-ok:          yes
is-userspace:            no
```

All required checks passed.

---

## 8. Flash result

```text
fastboot flash boot_b        MIUI14ROM/image/boot.img         OKAY
fastboot flash vendor_boot_b MIUI14ROM/image/vendor_boot.img  OKAY
fastboot flash dtbo_b        MIUI14ROM/image/dtbo.img         OKAY
post-flash current-slot:     a
slot-retry-count:b:          7   (was 6 before these writes)
then: fastboot reboot → Android A
NO set_active b yet
```

Writing the three payload partitions bumped retry 6→7 without `set_active`.

---

## 9. Post-write root hash

Android A `sys.boot_completed=1` `ro.boot.slot_suffix=_a`:

| Partition | SHA256 | vs ROM |
|---|---|---|
| boot_b @134217728 | `9d8c12c5…e3e9be` | MATCH |
| vendor_boot_b @100663296 | `aac7e11f…041972` | MATCH |
| dtbo_b @33554432 | `018fa85c…e64634` | MATCH |
| vbmeta_b @8192 | `37dfac44…0f9d9c` flags=2 | MATCH |
| vbmeta_system_b @4096 | `32174550…8b8355` | MATCH |

```text
PURE_STOCK_B_PAYLOAD_VERIFIED: YES
```

Five of five exact-match. Gate to continue: passed.

---

## 10. Retry around set_active (the 6→6 hole)

Second Fastboot preflight after Android A hash:

```text
RETRY_BEFORE_SET_ACTIVE:  7
slot-successful:b:        no
slot-unbootable:b:        no
current-slot:             a
```

`fastboot set_active b` OKAY, then immediately before reboot:

```text
current-slot:             b
slot-successful:b:        no
slot-unbootable:b:        no
RETRY_AFTER_SET_ACTIVE:   7
is-userspace:             no
```

`set_active b` did **not** change retry (already 7). The previous AVB-round net 6→6 is compatible with: reset-to-7 + failed-boot-decrement-to-6, sampled only at the ends.

USB baseline before reboot: `18d1:d00d` Google Android, Location `0x02112000`.

One `fastboot reboot`. No second B start.

---

## 11. USB / host observation (30 s)

Agent has no camera. Logo / boot animation / black screen: **NOT_OBSERVED**. USB/ADB/Fastboot only.

```text
t+0s   fastboot reboot (slot b)
t+2–10s  USB gone; no adb; no fastboot; no 1d6b:0104; no new inet
t+12s  18d1:d00d Google Android serial 41a5627b + fastboot protocol
t+12–30s stays ABL Fastboot; no Android USB; no adb device
```

```text
PURE_STOCK_SLOT_B_BOOT: FAIL
```

---

## 12. Retry after the one B boot

```text
current-slot:           b
slot-successful:b:      no
slot-unbootable:b:      no
RETRY_AFTER_BOOT:       6
is-userspace:           no
```

```text
RETRY_BEFORE_SET_ACTIVE  7
→ RETRY_AFTER_SET_ACTIVE 7
→ RETRY_AFTER_BOOT       6
```

AOSP unsuccessful-slot semantics: the boot was counted. `unbootable:b` still `no`.

Then `fastboot set_active a` → `current-slot:a` → `fastboot reboot`. No `*_a` flash.

Android A recovered: `slot_suffix=_a` `sys.boot_completed=1` Magisk root `Linux 4.19.157-perf-g9d90dd04aa7c`.

---

## 13. Dump / misc after

| Partition | After SHA256 | vs before |
|---|---|---|
| oops | `228d90c9…888ec1` | CHANGED |
| minidump | `276099a3…9c778` | same |
| rawdump | `254bcc3f…53917` | same |
| logdump | `3b6a07d0…21351` | same |
| misc 64KiB | `ccfeffb0…770953` | same, still `bootonce-bootloader` |

```text
NEW_CRASH_DUMP: YES  (oops kmsg only)
                NO   (minidump / rawdump / logdump)
```

Retry 7→6 is **not** stored in misc[0:65536]. Boot-control metadata lives elsewhere.

---

## 14. oops Index 1144 — stock kernel on Slot B

Newest complete-from-t=0 kmsg (`# Index: 1144`, RTC `1974-07-15 12:01:27`, Reason `Restart`).

```text
Build:  #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
        (same banner as working Android A 4.19.157-perf)
Powerup reason=0x800041
Machine model: Qualcomm Technologies, Inc. xiaomi thyme
androidboot.slot_suffix=_b
androidboot.verifiedbootstate=orange
```

No `Kernel panic`. Watchdog initialized, no bark in this record. Uptime of this record: **0.000–1.773 s**.

```text
[    1.736168] Run /init as init process
[    1.740706] init: init first stage started!
[    1.740779] init: Switching root to '/first_stage_ramdisk'
[    1.740895] init: [libfs_mgr]ReadFstabFromDt(): failed to read fstab from dt
[    1.754979] init: [libfs_mgr]check_fs(): mount(/dev/block/by-name/metadata,/metadata,ext4)=-1: No such file or directory
[    1.754991] init: [libfs_mgr]Running /system/bin/e2fsck on /dev/block/sda18
[    1.767007] e2fsck: /dev/block/by-name/metadata: 49/4096 files ...
[    1.769268] EXT4-fs (sda18): mounted filesystem with ordered data mode
[    1.772847] reboot: Restarting system with command 'boot
```

The reboot command string is truncated by the oops wrapper (next bytes are the Logcat fence). It starts with `boot` and the host then sees ABL Fastboot — treated as reboot-to-bootloader, not a panic.

```text
STOCK_KERNEL_HANDOFF: CONFIRMED
```

Slot B/ABL loaded official 4.19, executed it, first-stage init ran, then the kernel rebooted on an explicit command. This is **not** pre-kernel.

---

## 15. What this does and does not prove

Proved:

- Official stock `boot`+`vendor_boot`+`dtbo`+`vbmeta`+`vbmeta_system` on B is a bit-exact ROM match.
- ABL Slot-B path can hand off to the stock kernel.
- Historical “stock core on B immediately Fastboot ⇒ ABL/firmware” is incomplete: Fastboot return can be **post-kernel**.
- `set_active` at retry=7 does not itself decrement; the failed/aborted boot does 7→6.

Not proved (do not start a flash matrix here):

- Why first-stage init rebooted ~3 ms after metadata mounted. Candidates, unseparated:
  - leftover AOSP BCB `bootonce-bootloader` in misc (bytes unchanged across the whole test; Android A also boots with those same bytes, so this is **not** a unique Slot-B explanation by itself)
  - Virtual A/B snapshot / logical `_b` in `super` / missing `androidboot.force_normal_boot`
  - Xiaomi first-stage policy after `/metadata`
- Display contents (not observed).

---

## 16. Final answers

```text
PURE_STOCK_B_PAYLOAD_VERIFIED: YES
RETRY_BEFORE_SET_ACTIVE:       7
RETRY_AFTER_SET_ACTIVE:        7
RETRY_AFTER_BOOT:              6
PURE_STOCK_SLOT_B_BOOT:        FAIL
STOCK_KERNEL_HANDOFF:          CONFIRMED
NEW_CRASH_DUMP:                YES (oops); NO (minidump/rawdump/logdump)
```

---

## 17. Final gate

```text
STOCK_B_CONTROL_FAIL_POST_KERNEL
```

Slot B/ABL base path **works** for official V14.0.6.0.TGACNXM payload. Android userspace did not stay up.

Next stage (do not start in this round): Virtual A/B / first-stage init after `/metadata` / boot-control + BCB vs `super` logical slot B.  
Not this round: Linux/DTS rebuild, Mainline re-flash, firmware_b, `vbmeta_*` rewrite, misc write.

Device recovered to Android A. Stock payload left on B. No Mainline re-flash.
