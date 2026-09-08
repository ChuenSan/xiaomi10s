# Route B stock-kernel USB enum stage0 — thyme

Stage: `STOCK_KERNEL_USB_ENUM_STAGE0`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Head: `4cd27a2`

```text
USB_ENUM_STAGE0_FAIL_CONFIGFS
```

Custom `/init` ran on stock 4.19. kmsg markers reached `SYSFS_OK` then
`FAIL:CONFIGFS` in 55 µs. Host never saw `1d6b:0104`. `restart2("bootloader")`
returned Fastboot automatically at +16.339s. No key.

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

## 2. Android A read-only USB audit

Device: `41a5627b` `slot_suffix=_a` `sys.boot_completed=1` root Magisk.

```text
ro.boot.usbcontroller: a600000.dwc3
sys.usb.config:        adb
sys.usb.state:         adb
UDC name:              a600000.dwc3
UDC state:             configured
UDC speed:             high-speed / max high-speed
uevent DRIVER:         configfs-gadget
uevent USB_UDC_DRIVER: g1
```

configfs mount: `none on /config type configfs`.  
`/sys/kernel/config/usb_gadget` does **not** exist on Android A.  
Gadget dir: `/config/usb_gadget/g1` bound to `a600000.dwc3`.  
Config name: `configs/b.1` (linked function `ffs.adb` only).  
g1 identity (working Android ADB): `18d1:4ee7` Xiaomi / Mi 10S / `bcdUSB=0x0200`.

Live `/proc/config.gz` (stock 4.19.157-perf):

```text
CONFIG_CONFIGFS_FS=y
CONFIG_USB=y
CONFIG_USB_GADGET=y
CONFIG_USB_LIBCOMPOSITE=y
CONFIG_USB_CONFIGFS=y
# CONFIG_USB_CONFIGFS_ACM is not set
# CONFIG_USB_CONFIGFS_ECM is not set
CONFIG_USB_CONFIGFS_NCM=y
CONFIG_USB_F_NCM=y
CONFIG_USB_DWC3=y
CONFIG_USB_DWC3_DUAL_ROLE=y
CONFIG_USB_DWC3_QCOM=y
CONFIG_USB_DWC3_MSM=y
# CONFIG_DEVTMPFS is not set
```

Chosen built-in function: **ncm** (`functions/ncm.usb0`).  
ACM/ECM gadget are not built-in. `# CONFIG_DEVTMPFS is not set` → PID1 `mknod /dev/kmsg c 1 11`.

---

## 3. CI

```text
workflow: thyme-stock-kernel-usb-enum-stage0
run:      34226181383
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34226181383
commit:   4cd27a2f6e957a7469663e7bd0806f42a7d89fe3
artifact: thyme-stock-kernel-usb-enum-stage0-4cd27a2f6e957a7469663e7bd0806f42a7d89fe3
```

```text
STOCK_KERNEL_EXACT     PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
STATIC_INIT            PASS
ENTRY_IN_RX_LOAD       PASS  entry=0x4004b0 pt_load=0x400000+0xf70 flags=5
CONFIGFS_LOGIC         PASS
UDC_DISCOVERY_LOGIC    PASS
FAILSAFE_RESTART2      PASS
BOOT_V3                PASS
REVERSE_UNPACK         PASS
SIZE_GATE              PASS  52666368
READY_FOR_USB_ENUM_STAGE0
```

```text
boot SHA256: 7a72940279fff37b4c8d52c42b6be07c9b69afd5a2c89159b5923a1e6875cf13
ELF:         4312B static aarch64 ET_EXEC
```

---

## 4. Partition state

Pre-write (Android A): `boot_b` still P15 `133e063b…ea87d34`.  
B firmware stock. oops baseline `970be772…` (P15 Index 1156).

Fastboot preflight: `product=thyme` `unlocked=yes` `current-slot=a` `snapshot=none` `battery-soc-ok=yes`.

```text
BEFORE_FLASH: unbootable:b=no  retry:b=6  current=a
fastboot flash boot_b stock-kernel-usb-enum-stage0-boot-v3.img
Sending 'boot_b' (51432 KB) OKAY
Writing 'boot_b'            OKAY
AFTER_FLASH:  unbootable:b=no  retry:b=7  current=a
```

Post-write hash on Android A:

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @52666368 | `7a729402…875cf13` | MATCH USB0 artifact |
| vendor_boot_b @100663296 | `aac7e11f…041972` | MATCH stock |
| dtbo_b @33554432 | `018fa85c…e64634` | MATCH stock |
| vbmeta_b @8192 flags=2 | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b @4096 | `32174550…8b8355` | MATCH stock |

---

## 5. Slot metadata

```text
BEFORE_SET_ACTIVE:  current=a  unbootable:b=no  retry:b=7
fastboot set_active b
AFTER_SET_ACTIVE:   current=b  unbootable:b=no  retry:b=7
AFTER_BOOT:         current=b  unbootable:b=no  retry:b=6
```

Then `fastboot set_active a` + `fastboot reboot` → Android A.

---

## 6. Host USB

Baseline: `18d1:d00d` Fastboot. ifaces `en0…en7`, no extra gadget NIC.

One `fastboot reboot`. No second B start. No key.

```text
fastboot disappear: +0.730s
gadget appear:      NONE
new enX:            NO
adb fallback:       NONE
fastboot reappear:  +16.339s
manual key:         NO
```

No `thyme-mainline` / `Stock Kernel USB Enum Stage0` / `THYME-USB0` / `1d6b:0104`.

16.3s matches fail-path 5s sleep + ABL, **not** the 30s HOLD success path.

---

## 7. oops Index 1159

oops `970be772…` → `f982eaeb…`. New record **Index 1159**.  
minidump / rawdump / logdump 16MiB prefixes **unchanged**.

```text
Reason:     Restart
t=0:        YES
cmdline:    androidboot.slot_suffix=_b
            stock 4.19  Build #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
```

```text
<6>[    1.423812] Run /init as init process
<12>[    1.424111] THYME-USB0:INIT
<12>[    1.424140] THYME-USB0:SYSFS_OK
<12>[    1.424166] THYME-USB0:FAIL:CONFIGFS
<0>[    6.424254] reboot: Restarting system with command 'boot
```

`FAIL:CONFIGFS` → restart2 = **5.000088s**. Fail-safe confirmed.  
kmsg works (P15 could not open `/dev/kmsg`; USB0 `mknod` fixed that).

Never reached: `UDC=` `GADGET_CREATED` `FUNCTION=` `FUNCTION_LINKED` `UDC_BOUND` `HOLD`.

---

## 8. Why CONFIGFS failed (userspace, not “configfs absent”)

Live kernel has `CONFIG_CONFIGFS_FS=y` and `CONFIG_USB_CONFIGFS=y`. Android A mounts configfs at `/config` with `usb_gadget/g1`.

PID1 `is_dir()` used generic `O_DIRECTORY=00200000`. On this aarch64 4.19 that bit is **`O_DIRECT`**, while real `O_DIRECTORY` is `040000` (`arch/arm64/include/uapi/asm/fcntl.h`). Opening configfs with `O_DIRECT` returns `EINVAL`, so `usb_gadget` looks missing even if the mount succeeded.

Elapsed `SYSFS_OK` → `FAIL:CONFIGFS` is 26 µs — consistent with a failed open, not a missing subsystem.

Next USB0 retry should use aarch64 `O_DIRECTORY=040000` (or `O_RDONLY` only) and split markers: mount errno vs `usb_gadget` presence. Still stock 4.19, `boot_b` only. Not Mainline. Not IP/HTTP.

---

## 9. Classification

```text
/init executed:          YES
configfs mounted:        UNKNOWN (FAIL:CONFIGFS; likely false-negative is_dir)
UDC found:               NOT REACHED
gadget created:          NOT REACHED
function created:        NOT REACHED
function linked:         NOT REACHED
UDC bind:                NOT REACHED
last marker:             THYME-USB0:FAIL:CONFIGFS
custom USB enumerated:   NO
new enX:                 NO
manual intervention:     NO
```

Final gate: **`USB_ENUM_STAGE0_FAIL_CONFIGFS`**

Next: stock-kernel USB0 configfs retry (open flags). Not USB1 NCM link, not Mainline.
