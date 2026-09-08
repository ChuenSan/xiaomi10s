# Route B stock-kernel USB enum stage0 — thyme

Stage: `STOCK_KERNEL_USB_ENUM_STAGE0_RETRY_CONFIGFS_FIX`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Head: `0845875`

```text
USB_ENUM_STAGE0_PASS
```

Previous round `USB_ENUM_STAGE0_FAIL_CONFIGFS` is reclassified:

```text
USB_ENUM_STAGE0_USERSPACE_CONFIGFS_CHECK_BUG
```

Not `KERNEL_CONFIGFS_FAILURE`. Stock 4.19 already had configfs + NCM. PID1 `is_dir()` used generic `O_DIRECTORY=00200000` (aarch64 `O_DIRECT`).

This retry: `newfstatat` + `S_ISDIR`. configfs mount OK. UDC `a600000.dwc3` bound. Host enumerated. 30s HOLD then automatic Fastboot. No key. No IP.

TEST ONLY identity `1d6b:0104` (Linux Foundation gadget).  
NOT PRODUCTION USB IDENTITY.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
Slot A flashed:           NO
Only partition written:   boot_b
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
Mainline / DTS / IP / HTTP / telnet / ADB gadget / P30: NO
/metadata:                NOT MOUNTED
```

---

## 2. Previous round — userspace false negative

CI `34226181383` commit `4cd27a2` boot `7a729402…`. oops Index 1159:

```text
<6>[    1.423812] Run /init as init process
<12>[    1.424111] THYME-USB0:INIT
<12>[    1.424140] THYME-USB0:SYSFS_OK
<12>[    1.424166] THYME-USB0:FAIL:CONFIGFS
<0>[    6.424254] reboot: Restarting system with command 'boot
```

`SYSFS_OK` → `FAIL:CONFIGFS` = 26 µs. Host never saw `1d6b:0104`. restart2 +5.000s. UDC/gadget/bind not reached.

Cause: `is_dir()` `openat(..., O_RDONLY | O_DIRECTORY)` with `O_DIRECTORY=000200000` (asm-generic). aarch64 UAPI `O_DIRECTORY=040000`, `O_DIRECT=0200000`.

---

## 3. Fix

```text
old directory detection:   openat(O_RDONLY | O_DIRECTORY)  O_DIRECTORY=000200000
new directory detection:   newfstatat(AT_FDCWD, path, &stat, 0) + S_ISDIR(st_mode)
arm64 flag issue removed:  YES — PID1 no longer uses O_DIRECTORY
CI assertions:             aarch64 linux/fcntl.h
                           O_DIRECTORY==040000 O_DIRECT==0200000 newfstatat=79
                           DIRECTORY_CHECK_IMPL=newfstatat/stat
```

Mountpoint `/config`. EBUSY is not fail if `/config/usb_gadget` exists. Per-op errno markers. UDC scanned from `/sys/class/udc`. Function still ncm.

---

## 4. CI

```text
workflow: thyme-stock-kernel-usb-enum-stage0
run:      34232265858
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34232265858
commit:   08458754a70beaf61c6a2a3caf1c6f9b9af75cd5
artifact: thyme-stock-kernel-usb-enum-stage0-fix-08458754a70beaf61c6a2a3caf1c6f9b9af75cd5
```

```text
STOCK_KERNEL_EXACT              PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
STATIC_INIT                     PASS
ENTRY_RX                        PASS  entry=0x400954 pt_load=0x400000+0x1978 flags=5
CONFIGFS_PATH_FIX                PASS
STAT_BASED_DIRECTORY_CHECK      PASS
DIRECTORY_CHECK_NOT_OPEN_ODIRECTORY PASS
CONFIGFS_MOUNTPOINT_IS_CONFIG    PASS
CONFIGFS_STAT_LOGGING           PASS
ERRNO_LOGGING / ERRNO_MARKERS   PASS
UDC_DISCOVERY / UDC_SCAN_LOGIC  PASS
NCM_LOGIC                       PASS
FAILSAFE                        PASS
BOOT_V3                         PASS
REVERSE_UNPACK                  PASS
SIZE_GATE                       PASS  52666368
READY_FOR_USB_ENUM_STAGE0_RETRY
```

```text
boot SHA256: ce4114bee713b75e1b43df07dc18569cc1f3a7d67b4998f9401f5ee5c3380220
ELF:         6880B static aarch64 ET_EXEC
```

---

## 5. Android A preflight / flash

`slot_suffix=_a` `sys.boot_completed=1` Magisk uid=0.

| Partition | SHA256 pre | vs expect |
|---|---|---|
| boot_b @52666368 | `7a729402…875cf13` | old USB0 |
| vendor_boot_b @100663296 | `aac7e11f…041972` | MATCH stock |
| dtbo_b @33554432 | `018fa85c…e64634` | MATCH stock |
| vbmeta_b @8192 flags=2 | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b @4096 | `32174550…8b8355` | MATCH stock |

oops baseline `f982eaeb…` (Index 1159). minidump/rawdump/logdump 16MiB prefixes unchanged after this boot.

Fastboot: `product=thyme` `unlocked=yes` `current-slot=a` `snapshot=none` `battery-soc-ok=yes`.

```text
USB0 CONFIGFS FIX RETRY
WRITE: boot_b ONLY
SLOT A / vendor_boot_b / dtbo_b / vbmeta_b: NO WRITE
```

```text
BEFORE_FLASH: unbootable:b=no  retry:b=6  current=a
fastboot flash boot_b stock-kernel-usb-enum-stage0-boot-v3.img
Sending 'boot_b' (51432 KB) OKAY
Writing 'boot_b'            OKAY
AFTER_FLASH:  unbootable:b=no  retry:b=7  current=a
```

Post-write hash on Android A: `boot_b=ce4114be…380220` MATCH artifact. Other B payloads still stock flags=2.

---

## 6. Slot metadata

```text
BEFORE_SET_ACTIVE:  current=a  unbootable:b=no  retry:b=7
fastboot set_active b
AFTER_SET_ACTIVE:   current=b  unbootable:b=no  retry:b=7
AFTER_BOOT:         current=b  unbootable:b=no  retry:b=6
```

Then `fastboot set_active a` + `fastboot reboot` → Android A. No second B start. No key.

---

## 7. Host USB

Baseline: Fastboot `18d1:d00d`. ifaces through `en7`, no extra gadget NIC.

One `fastboot reboot`. No second B start. No key.

```text
fastboot disappear:        +0.712s
custom gadget appear:     +7.565s
gadget hold:              30.095s
custom gadget disappear:  +37.660s
fastboot reappear:        +41.283s
adb fallback:             NONE
manual key:               NO
automatic:                YES
```

```text
custom enumeration: YES
VID:PID:            1d6b:0104  (PID1 identity; host matcher hit thyme-mainline / Stage0 / THYME-USB0)
Product:            Stock Kernel USB Enum Stage0
Manufacturer:       thyme-mainline
Serial:             THYME-USB0
new enX:            en10   (recorded only; no IP, no route)
```

ioreg dump at appear was truncated by a broad `head`; identity is from `has_gadget()` plus device kmsg `USB_STATE=CONFIGURED`.

---

## 8. oops Index 1162

oops `f982eaeb…` → `93d0afc8…`. New record **Index 1162**.  
minidump / rawdump / logdump 16MiB prefixes **unchanged**.

```text
Reason:     Restart
cmdline:    androidboot.slot_suffix=_b
            stock 4.19  Build #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
```

kmsg2() splits prefix and UDC name across printk records. Combined:

```text
<6>[    1.579791] Run /init as init process
<12>[    1.579930] THYME-USB0:INIT
<12>[    1.579964] THYME-USB0:SYSFS_OK
<12>[    1.579976] THYME-USB0:STAT_UDC_CLASS=0:MODE=16877:ERRNO=0
<12>[    1.579983] THYME-USB0:UDC_CLASS_PRESENT
<12>[    1.579997] THYME-USB0:MOUNT_CONFIGFS:RET=0:ERRNO=0
<12>[    1.580001] THYME-USB0:CONFIGFS_MOUNT_OK
<12>[    1.580007] THYME-USB0:STAT_CONFIG=0:ERRNO=0
<12>[    1.580044] THYME-USB0:STAT_USB_GADGET=0:MODE=16877:ERRNO=0
<12>[    1.580049] THYME-USB0:CONFIGFS_OK
<12>[    1.580060] THYME-USB0:UDC=a600000.dwc3
<12>[    1.580096] THYME-USB0:PREBIND_STATE=not attached
<12>[    1.580106] THYME-USB0:MAX_SPEED=high-speed
<12>[    1.580116] THYME-USB0:CURRENT_SPEED=UNKNOWN
<12>[    1.580153] THYME-USB0:GADGET_DIR_OK
<12>[    1.580202] THYME-USB0:STRINGS_OK
<12>[    1.580222] THYME-USB0:CONFIG_OK
<12>[    1.580227] THYME-USB0:GADGET_CREATED
<12>[    1.580245] THYME-USB0:NCM_OK
<12>[    1.580249] THYME-USB0:FUNCTION=ncm
<12>[    1.580258] THYME-USB0:LINK_OK
<12>[    1.580262] THYME-USB0:FUNCTION_LINKED
<12>[    1.580265] THYME-USB0:BIND_ATTEMPT:a600000.dwc3
<12>[    1.580453] THYME-USB0:UDC_BOUND
<12>[    1.580466] THYME-USB0:POSTBIND_STATE=not attached
<12>[    1.580471] THYME-USB0:HOLD
<3>[    1.889866] android_work: sent uevent USB_STATE=CONNECTED
<6>[    1.897313] configfs-gadget gadget: high-speed config #1: c
<3>[    1.897431] android_work: sent uevent USB_STATE=CONFIGURED
<12>[   31.580533] THYME-USB0:HOLD_DONE
<12>[   31.580540] THYME-USB0:REBOOT_BOOTLOADER
<0>[   31.580562] reboot: Restarting system with command 'boot
```

HOLD → HOLD_DONE = **30.000062s**. restart2 after HOLD_DONE.

POSTBIND_STATE was sampled 13 µs after bind (still `not attached`). Host CONFIGURED at 1.897s. No PID1 exit.

---

## 9. Classification

```text
/init executed:          YES
configfs mounted:        YES  RET=0 ERRNO=0  usb_gadget MODE=16877
UDC found:               YES  a600000.dwc3
gadget created:          YES
function created:        YES  ncm
function linked:         YES
UDC bind:                YES
last marker:             THYME-USB0:REBOOT_BOOTLOADER
custom USB enumerated:   YES
new enX:                 en10
manual intervention:     NO
```

Final gate: **`USB_ENUM_STAGE0_PASS`**

Stop. Do not configure NCM IP. Next is `STOCK_KERNEL_USB_STAGE1` (macOS enX link/interface only).
