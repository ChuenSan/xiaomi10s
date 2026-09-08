# Route B stock-kernel + mininit control — thyme

Stage: `ROUTE_B_STOCK_KERNEL_MINIMAL_INITRAMFS_CONTROL`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Head: `a191713`

Single variable vs verified Pure Stock B: replace **generic ramdisk only**.

---

## 1. Constraint compliance

```text
Local compilation: NO
Local build: NO
Slot A flashed: NO
Only partition written: boot_b
vendor_boot_b / dtbo_b / vbmeta_b / firmware: NO WRITE
```

---

## 2. Why NCM

Stock `kona-perf_defconfig`: `CONFIG_USB_CONFIGFS_NCM=y`, no ECM.
VID/PID `0x1d6b:0x0104` Linux Foundation Multifunction Composite Gadget.
Subnet `10.66.73.1/24`.

---

## 3. CI

```text
workflow: thyme-stock-kernel-mininit-control
run:      34211533140
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34211533140
commit:   a191713d2b80c812bd98dfefdd9a0214e6b7eede
artifact: thyme-stock-kernel-mininit-control-a191713d2b80c812bd98dfefdd9a0214e6b7eede
status:   success
```

Stock boot.img input SHA256 (re-verified in CI):

```text
9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be
```

Gates:

```text
STOCK_BOOT_INPUT_HASH     PASS
STOCK_KERNEL_EXACT_MATCH  PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
BOOT_HEADER_V3            PASS
INITRAMFS_STRUCTURE       PASS
REVERSE_UNPACK            PASS
PARTITION_SIZE            PASS  53850112 <= 201326592
ONLY_RAMDISK_CHANGED      PASS
READY_FOR_STOCK_KERNEL_MININIT_CONTROL
```

Image:

```text
stock kernel SHA:    85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
control boot SHA:    d5849d43ce9ccb1242d9615173660d31c88bbc7e344ed01a81053d2a1ab09e0f
kernel exact match:  YES
only ramdisk changed: YES
```

See `docs/stock-kernel-mininit-image-diff.md`.

---

## 4. B baseline before write (Android A root)

```text
boot_b @134217728          9d8c12c5…e3e9be  MATCH stock
vendor_boot_b @100663296   aac7e11f…041972  MATCH stock
dtbo_b @33554432           018fa85c…e64634  MATCH stock
vbmeta_b @8192             37dfac44…0f9d9c  MATCH stock flags=2
vbmeta_system_b @4096      32174550…8b8355  MATCH stock
```

Dump / misc baseline (read-only, no erase):

```text
oops @16MiB      228d90c9622059e53b72f52ec02168d0f5f9d54fad3d56fa3dfe970e62888ec1
                 (same as post stock-B-control Index 1144)
minidump 16MiB   42031494de918bcea128393b204b33846e1a33a6cebf84166ee2b9b272917cc7
rawdump 16MiB    080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e
logdump 16MiB    080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e
misc 64KiB       ccfeffb08df638cef3d2e20dd0cb1234ff510d4f13f1e5a97b8977d148770953
misc[0:32]       bootonce-bootloader
```

---

## 5. Fastboot preflight (manual getvar; script stderr parse is a known miss)

```text
product:                 thyme
unlocked:                yes
current-slot:            a
snapshot-update-status:  none
slot-unbootable:b:       no
slot-successful:b:       no
slot-retry-count:b:      6
battery-soc-ok:          yes
is-userspace:            no
```

```text
CONTROL:
STOCK KERNEL + MINIMAL INITRAMFS

WRITE TARGET:
boot_b ONLY

vendor_boot_b: STOCK / NO WRITE
dtbo_b:        STOCK / NO WRITE
vbmeta_b:      STOCK / NO WRITE
SLOT A:        NO WRITE
```

---

## 6. Flash

```text
fastboot flash boot_b stock-kernel-mininit-boot-v3.img
Sending 'boot_b' (52588 KB) OKAY
Writing 'boot_b'            OKAY
post-flash current-slot:    a
slot-retry-count:b:         7   (6 → 7 from the write, same as prior stock flash)
then: fastboot reboot → Android A
NO set_active b yet
```

Post-write Android A root hash:

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @53850112 | `d5849d43…b09e0f` | MATCH control image |
| vendor_boot_b | `aac7e11f…041972` | still stock |
| dtbo_b | `018fa85c…e64634` | still stock |
| vbmeta_b flags=2 | `37dfac44…0f9d9c` | still stock |
| vbmeta_system_b | `32174550…8b8355` | still stock |

---

## 7. Retry around the one B boot

```text
RETRY_BEFORE_SET_ACTIVE:  7
fastboot set_active b     OKAY
current-slot:             b
RETRY_AFTER_SET_ACTIVE:   7
is-userspace:             no
USB baseline:             18d1:d00d Google Android serial 41a5627b
one fastboot reboot. No second B start.
```

---

## 8. USB / host observation (≥30 s, then extra wait to ~3 min)

Agent has no camera. Screen: NOT_OBSERVED.

```text
t+0s     fastboot reboot (slot b)
t+2–33s  USB gone; no adb; no fastboot; no 1d6b:0104;
         no thyme-mainline / Stock Kernel MinInit Control / THYME-STOCKK-MININIT
         no new enX; ifconfig en* set unchanged (en0 LAN + en7 Realtek dock)
t+~3min  still no phone USB of any kind
```

Contrast with Pure Stock B (Android ramdisk): USB drop then ABL Fastboot at ~12 s,
oops showed first-stage `reboot ... boot`.

This round **did not** return to ABL Fastboot in the observe window.

```text
custom descriptor: NO
new enX:           NO
HTTP status:       NO
stage reached:     UNKNOWN (no host liveness)
```

---

## 9. Recovery

Hardware Vol-Down+Power → Fastboot (no second `set_active b`).

```text
RETRY_AFTER_BOOT:     6
current-slot:         b
slot-successful:b:    no
slot-unbootable:b:    no
then: fastboot set_active a → reboot → Android A Magisk root
Linux 4.19.157-perf-g9d90dd04aa7c slot _a sys.boot_completed=1
boot_b prefix still MATCH control image (not restored)
```

---

## 10. Dump after recovery

```text
oops 16MiB     ecaeb104435427260f708a5ceefd5f84b74d1f914edde4d0342d87a43220dbb6  CHANGED
minidump 16MiB 42031494…917cc7  same
rawdump 16MiB  080acf35…19643e  same
logdump 16MiB  080acf35…19643e  same
misc 64KiB     ccfeffb0…770953  same, still bootonce-bootloader
```

New kmsg records: Index **1145** and **1146**. Both are stock 4.19
`#1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023`, Reason Restart.

| Index | From t=0? | slot_suffix | contents |
|---|---|---|---|
| 1144 | YES | `_b` | previous Pure Stock B Android first-stage; `Run /init`; reboot `boot` at 1.77 s |
| 1145 | NO (starts ~2678 s) | (Android A) | mid-life A → `reboot ... boot` at 3535 s |
| 1146 | NO (starts ~8 s) | (Android userspace) | Android A-class session; reboot `boot` at 53 s |

Entire oops image: **no** `thyme-mininit`, `STAGE_*`, `STOCK_KERNEL_MININIT`,
`THYME-STOCKK`, `No working init`. The only `slot_suffix=_b` + t=0 banner
is still Index 1144 (previous round).

The mininit Slot B session **did not snapshot a t=0 kmsg**. Compatible with
PID 1 sitting in the idle loop (no panic, no `reboot`) until hard Fastboot,
or an early hang that never flushed ramoops. `reboot=panic_warm` is on the
stock vendor cmdline; a panic would usually dump. Absence of a t=0 `_b`
record argues against a completed panic dump.

---

## 11. Interpretation

Proved:

- Control image = exact stock kernel + our ramdisk only (CI + on-device hash).
- ABL counted the B attempt (retry 7→6, still bootable).
- Android first-stage `/metadata` reboot path did **not** repeat (no 12 s
  Fastboot return, no new 1144-style t=0 `_b` first-stage log).

Not proved:

- `/init` (BusyBox) executed
- configfs / NCM bound
- DWC3 in device mode

USB liveness failed. Next work is stock-4.19 ramdisk/USB (role switch,
NCM bind, `/init` evidence), not Mainline DTS.

---

## 12. Final gate

```text
STOCK_KERNEL_MININIT_CONTROL_FAIL
```

Do not restore stock `boot_b` unless asked. Slot A is the stable Android.
