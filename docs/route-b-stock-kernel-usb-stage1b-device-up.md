# Route B stock-kernel USB Stage1B device netdev IFF_UP — thyme

Stage: `STOCK_KERNEL_USB_STAGE1B_DEVICE_NETDEV_UP`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Head: `d73c9df`

```text
USB_STAGE1B_DEVICE_UP_HOST_LINK_PASS
```

USB0 path reused. After `usb0` appears, PID1 does `SIOCGIFFLAGS` then
`SIOCSIFFLAGS` with `old_flags | IFF_UP`. No IP.

Device: `ADMIN_UP=YES` `CARRIER=1` `OPERSTATE=up`.  
Host new `en12` `status: inactive` → `active` (`100baseTX <full-duplex>`).  
`host_addr` matches `en12` MAC.

TEST ONLY identity `1d6b:0104`. NOT PRODUCTION USB IDENTITY.  
Descriptor: Product `Stock Kernel USB Stage1B Device Up`, Serial `THYME-USB1B`.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
Slot A flashed:           NO
Only partition written:   boot_b
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
IP / route / ping / DHCP / HTTP / Mainline / DTS / Android B userspace: NO
```

---

## 2. Android A read-only reference (before flash)

```text
slot_suffix=_a  boot_completed=1  uid=0 (magisk)
sys.usb.config=adb
UDC=a600000.dwc3 state=configured function=g1
g1 18d1:4ee7 configs/b.1 -> ffs.adb
ncm.0 present unlinked; dev_addr/host_addr/ifname ENODEV
/sys/class/net: no usb/ncm/rndis
ANDROID_A_NCM_REFERENCE=NOT_AVAILABLE
setprop: NOT USED
```

B payload before flash:

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @52670464 | `4cc9be7e…797e2912` | Stage1 observe |
| vendor_boot_b | `aac7e11f…041972` | MATCH stock |
| dtbo_b | `018fa85c…e64634` | MATCH stock |
| vbmeta_b | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b | `32174550…8b8355` | MATCH stock |

oops 16MiB prefix `26e3b6a5…`. minidump/rawdump/logdump prefixes unchanged after this boot.

---

## 3. CI

```text
workflow: thyme-stock-kernel-usb-stage1b-device-up
run:      34243845517
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34243845517
commit:   d73c9df129672894855c690277af07713ae01f69
artifact: thyme-stock-kernel-usb-stage1b-device-up-d73c9df129672894855c690277af07713ae01f69
```

```text
STOCK_KERNEL_EXACT              PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
STATIC_INIT                     PASS
ENTRY_IN_RX_LOAD                PASS
USB0_CORE_REUSED                PASS
NETDEV_DISCOVERY                PASS
SIOCGIFFLAGS                    PASS
SIOCSIFFLAGS                    PASS
IFF_UP_OR_OLD_FLAGS             PASS
NO_IP_CONFIGURATION             PASS
FAILSAFE                        PASS
BOOT_V3                         PASS
REVERSE_UNPACK                  PASS
SIZE_GATE                       PASS  52670464
READY_FOR_USB_STAGE1B_DEVICE_UP
```

```text
boot SHA256: 0885ab7392525526ec39a334c0ab0166f737a9a2abb75937b5fd7240e4da13a8
ELF:         12840B static aarch64 ET_EXEC
```

---

## 4. Flash

Fastboot: `product=thyme` `unlocked=yes` `current-slot=a` `snapshot=none` `battery-soc-ok=yes`.

```text
WRITE: boot_b ONLY
RETRY_BEFORE_FLASH: 6
AFTER_FLASH:        retry:b=7  unbootable:b=no  current=a
```

Post-write Android A hash of `boot_b` @52670464 = `0885ab73…4da13a8` MATCH artifact. Other B payloads still stock.

---

## 5. Slot metadata (one B start)

```text
RETRY_BEFORE_SET_ACTIVE: 7  current=a
fastboot set_active b
RETRY_AFTER_SET_ACTIVE:  7  current=b  unbootable:b=no
one fastboot reboot
RETRY_AFTER_BOOT:        6  current=b  unbootable:b=no
then set_active a + reboot → Android A
second B start: NO
manual key:     NO
```

---

## 6. Host

Baseline: `en0`–`en7`. Fastboot `18d1:d00d` Location `0x02112000 / 11`.

`T0` = `fastboot_reboot_finished_unix=1788881086.978`

```text
fastboot disappear:  +0.605s
NEW_IF en12 appear:  +7.765s
gadget appear:       +7.795s
en12 disappear:      +37.308s
gadget disappear:     +37.560s
fastboot reappear:   +41.455s
en12 lifetime:       29.543s
gadget hold:         29.765s
adb fallback:        NONE
manual key:          NO
```

```text
enumerated:    YES
VID:PID:       1d6b:0104
Product:       Stock Kernel USB Stage1B Device Up
Serial:        THYME-USB1B
Manufacturer:  thyme-mainline
new enX:       en12
MAC:           36:9d:f1:2d:0e:9f
MTU:           1500
```

`en12` status timeline (no host `ifconfig up` / inet):

| host T after en12 | flags | media | status |
|---|---|---|---|
| appear | `8822<BROADCAST,SMART,SIMPLEX,MULTICAST>` | autoselect (none) | inactive |
| ~100ms | `8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST>` | 100baseTX full-duplex | active |
| 0.5s–20s | same | 100baseTX full-duplex | active |

No host IPv4 assignment by this test. macOS later self-assigned IPv6 link-local and IPv4LL; ignored. No ping.

---

## 7. Device (oops Index 1170)

oops 16MiB `26e3b6a5…` → `e2ceeb1b…`. New record **Index 1170**.  
minidump / rawdump / logdump 16MiB prefixes **unchanged**.

```text
Reason:  Restart
cmdline: androidboot.slot_suffix=_b
kernel:  4.19.157-perf  #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
```

```text
<6>[    1.603691] Run /init as init process
<12>[    1.603826] THYME-USB1B:INIT
<12>[    1.603835] THYME-USB1B:SIOCGIFFLAGS=YES
<12>[    1.603839] THYME-USB1B:SIOCSIFFLAGS=YES
<12>[    1.603900] THYME-USB1B:MOUNT_CONFIGFS:RET=0:ERRNO=0
<12>[    1.603922] THYME-USB1B:CONFIGFS_OK
<12>[    1.603932] THYME-USB1B:UDC=a600000.dwc3
<12>[    1.604149] THYME-USB1B:NCM_OK
<12>[    1.604203] THYME-USB1B:LINK_OK
<12>[    1.604241] THYME-USB1B:BIND_ATTEMPT:a600000.dwc3
<12>[    1.604412] THYME-USB1B:UDC_BOUND
<12>[    1.604436] THYME-USB1B:NETDEV_FOUND=usb0
<12>[    1.604465] THYME-USB1B:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER_ERRNO=22:MTU=1500
<12>[    1.604490] THYME-USB1B:IF=usb0:MAC=62:5d:fb:0f:3c:33:IDX=8:ADDR_LEN=6:TYPE=1
<12>[    1.604509] THYME-USB1B:FLAGS_BEFORE=0x1002
<12>[    1.604514] THYME-USB1B:IFF_UP_ATTEMPT
<12>[    1.604531] THYME-USB1B:IFF_UP_OK
<12>[    1.604535] THYME-USB1B:FLAGS_AFTER=0x1003
<12>[    1.604540] THYME-USB1B:ADMIN_UP_AFTER=YES
<12>[    1.604543] THYME-USB1B:HOLD
<12>[    1.604559] THYME-USB1B:T=0:FLAGS=0x1003:ADMIN=1:OPER=down:CARRIER=0:UDC=not attached
<12>[    1.704647] THYME-USB1B:T=100:FLAGS=0x1003:ADMIN=1:OPER=down:CARRIER=0:UDC=not attached
<3>[    2.058763] android_work: sent uevent USB_STATE=CONNECTED
<6>[    2.067278] configfs-gadget gadget: high-speed config #1: c
<3>[    2.067375] android_work: sent uevent USB_STATE=CONFIGURED
<12>[    2.104723] THYME-USB1B:UDC_CONFIGURED
<12>[    2.104735] THYME-USB1B:T=500:FLAGS=0x1003:ADMIN=1:OPER=down:CARRIER=0:UDC=configured
<12>[    2.604863] THYME-USB1B:T=1000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured
<12>[    3.605078] THYME-USB1B:T=2000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured
<12>[    6.605301] THYME-USB1B:T=5000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured
<12>[   11.605523] THYME-USB1B:T=10000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured
<12>[   21.605724] THYME-USB1B:T=20000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured
<12>[   31.605921] THYME-USB1B:T=30000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured
<12>[   31.606010] THYME-USB1B:IF=usb0:FLAGS=0x1043:ADMIN_UP=YES:OPER=up:CARRIER=1:MTU=1500
<12>[   31.606239] THYME-USB1B:DEV_ADDR=62:5d:fb:0f:3c:33
<12>[   31.606277] THYME-USB1B:HOST_ADDR=36:9d:f1:2d:0e:9f
<12>[   31.606314] THYME-USB1B:NCM_IFNAME=usb0
<12>[   31.606350] THYME-USB1B:HOLD_DONE
<12>[   31.606368] THYME-USB1B:REBOOT_BOOTLOADER
```

HOLD → HOLD_DONE = **30.0018s**. restart2 after HOLD_DONE. No PID1 return.

`FLAGS_BEFORE=0x1002` = `IFF_BROADCAST|IFF_MULTICAST`.  
`FLAGS_AFTER=0x1003` = plus `IFF_UP`.  
`T=1000` `0x1043` = plus `IFF_RUNNING`.

`CARRIER_ERRNO=22` (`EINVAL`) only while admin-down. After `IFF_UP`: `CARRIER=0` until UDC configured, then `CARRIER=1`.

---

## 8. Correlation

```text
created after:     UDC bind
IFF_UP:            immediately after usb0 appears (before host enum)
device MAC:        62:5d:fb:0f:3c:33  == configfs dev_addr
host MAC:          36:9d:f1:2d:0e:9f  == configfs host_addr == en12
NCM_IFNAME:        usb0
USB lifetime:      en12 29.543s / gadget 29.765s / HOLD 30.002s
```

```text
DEVICE_ADMIN_UP:     YES
DEVICE_OPERSTATE:    up   (from T=1000 through T=30000)
DEVICE_CARRIER:      1    (from T=1000; 0 at T=0/100/500)
HOST_INTERFACE:      en12
HOST_STATUS:         active (from ~100ms after appear through HOLD)
```

---

## 9. Recovery

```text
fastboot set_active a
adb:            device
slot_suffix:    _a
boot_completed: 1
```

---

## 10. Classification

```text
USB0 regression:     NO
device netdev:       YES  usb0
SIOCGIFFLAGS:        PASS  FLAGS_BEFORE=0x1002
SIOCSIFFLAGS:        PASS  errno=0
ADMIN_UP_AFTER:      YES
operstate:           up
carrier:             1
host enX:            en12 active, MAC=host_addr
```

Final gate: **`USB_STAGE1B_DEVICE_UP_HOST_LINK_PASS`**

Stop. Do not configure IP this round.

Next: `STOCK_KERNEL_USB_STAGE2_DEVICE_STATIC_IP` — device `usb0` `10.66.73.1/24` only. Host still no IPv4. No ICMP. No HTTP.
