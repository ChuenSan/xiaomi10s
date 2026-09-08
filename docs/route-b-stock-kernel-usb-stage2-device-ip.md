# Route B stock-kernel USB Stage2 device static IP — thyme

Stage: `STOCK_KERNEL_USB_STAGE2_DEVICE_STATIC_IP`  
Date: 2026-09-09  
Branch: `route-b-v3`  
Head: `168db55` (docs) / `41685e6` (source)

```text
USB_STAGE2_DEVICE_STATIC_IP_PASS
```

USB0/Stage1B path reused. After `usb0` `IFF_UP`, PID1 does
`SIOCSIFADDR 10.66.73.1` then `SIOCSIFNETMASK 255.255.255.0`,
verified with `SIOCGIFADDR` / `SIOCGIFNETMASK`. No host IPv4. No ping.

Device: `GET_ADDR=10.66.73.1` `GET_NETMASK=255.255.255.0`
`DEVICE_STATIC_IPV4_VERIFIED=YES`.  
`ADMIN_UP=YES` `CARRIER=1` `OPERSTATE=up`.  
Host new `en13` `status: inactive` → `active` (`100baseTX <full-duplex>`).  
`host_addr` matches `en13` MAC.

TEST ONLY identity `1d6b:0104`. NOT PRODUCTION USB IDENTITY.  
Descriptor: Product `Stock Kernel USB Stage2 Device IP`, Serial `THYME-USB2`.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
Slot A flashed:           NO
Only partition written:   boot_b
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
host IPv4 / route / ping / DHCP / HTTP / Mainline / DTS / Android B userspace: NO
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
| boot_b @52670464 | `0885ab73…4da13a8` | Stage1B PASS image |
| vendor_boot_b | `aac7e11f…041972` | MATCH stock |
| dtbo_b | `018fa85c…e64634` | MATCH stock |
| vbmeta_b | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b | `32174550…8b8355` | MATCH stock |

oops 16MiB prefix `e2ceeb1b…`. minidump/rawdump/logdump prefixes unchanged after this boot.

---

## 3. CI

```text
workflow: thyme-stock-kernel-usb-stage2-device-ip
run:      34249415099
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34249415099
commit:   41685e6e9dd97b3a8c1a4a59fa961ece5a365dff
artifact: thyme-stock-kernel-usb-stage2-device-ip-41685e6e9dd97b3a8c1a4a59fa961ece5a365dff
docs CI:  34249737319 (168db55) — source/image gates only, not device PASS
```

```text
STOCK_KERNEL_EXACT              PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
STATIC_INIT                     PASS
ENTRY_IN_RX_LOAD                PASS
USB0_CORE_REUSED                PASS
USB_STAGE1B_CORE_REUSED         PASS
SIOCGIFFLAGS                    PASS
SIOCSIFFLAGS                    PASS
IFF_UP_OR_OLD_FLAGS             PASS
SIOCSIFADDR_PRESENT             PASS
SIOCSIFNETMASK_PRESENT          PASS
SIOCGIFADDR_PRESENT             PASS
SIOCGIFNETMASK_PRESENT          PASS
DEVICE_IP_LITERAL = 10.66.73.1
DEVICE_NETMASK_LITERAL = 255.255.255.0
NO_HOST_IP_LOGIC                PASS
NO_PING_LOGIC                   PASS
NO_HTTP_LOGIC                   PASS
NO_DHCP_LOGIC                   PASS
NO_DEFAULT_ROUTE_LOGIC          PASS
FAILSAFE                        PASS
BOOT_V3                         PASS
REVERSE_UNPACK                  PASS
SIZE_GATE                       PASS  52670464
READY_FOR_USB_STAGE2_DEVICE_IP
```

`READY_FOR_*` is CI/artifact only. Device PASS is this document.

```text
boot SHA256: 88c4d8a5be098a508356120a02bdfb16e78b576b1876aaa98d06e945b7316b49
ELF:         14864B static aarch64 ET_EXEC
```

---

## 4. Flash

Fastboot: `product=thyme` `unlocked=yes` `current-slot=a` `snapshot=none` `battery-soc-ok=yes`.

```text
WRITE: boot_b ONLY
RETRY_BEFORE_FLASH: 6
AFTER_FLASH:        retry:b=7  unbootable:b=no  current=a
```

Post-write Android A hash of `boot_b` @52670464 = `88c4d8a5…316b49` MATCH artifact. Other B payloads still stock.

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

`T0` = `fastboot_reboot_finished_unix=1788885706.466`

```text
fastboot disappear:  +0.361s
NEW_IF en13 appear:  +7.405s
gadget appear:       +7.440s
en13 disappear:      +37.193s
gadget disappear:     +37.445s
fastboot reappear:   +41.006s
en13 lifetime:       29.788s
gadget hold:         30.005s
adb fallback:        NONE
manual key:          NO
```

```text
enumerated:    YES
VID:PID:       1d6b:0104
Product:       Stock Kernel USB Stage2 Device IP
Serial:        THYME-USB2
Manufacturer:  thyme-mainline
new enX:       en13
MAC:           92:14:6a:3a:0b:e3
MTU:           1500
```

`en13` status timeline (no host `ifconfig up` / project inet):

| host T after en13 | flags | media | status |
|---|---|---|---|
| appear | `8822<BROADCAST,SMART,SIMPLEX,MULTICAST>` | autoselect (none) | inactive |
| ~100ms | `8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST>` | 100baseTX full-duplex | active |
| 0.5s–20s | same | 100baseTX full-duplex | active |

No host IPv4 assignment by this test. macOS later self-assigned IPv6 link-local and IPv4LL (`169.254.108.183`); ignored. No ping. `HOST_PROJECT_IPV4_CONFIGURED=NO`.

---

## 7. Device (oops Index 1173)

oops 16MiB `4797fd92…` (post-flash Android A) → `76b12777…`. New record **Index 1173**.  
minidump / rawdump / logdump 16MiB prefixes **unchanged**.

```text
Reason:  Restart
cmdline: androidboot.slot_suffix=_b
kernel:  4.19.157-perf  #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
```

```text
<6>[    1.507811] Run /init as init process
<12>[    1.507948] THYME-USB2:INIT
<12>[    1.507956] THYME-USB2:SIOCGIFFLAGS=YES
<12>[    1.507960] THYME-USB2:SIOCSIFFLAGS=YES
<12>[    1.508050] THYME-USB2:MOUNT_CONFIGFS:RET=0:ERRNO=0
<12>[    1.508069] THYME-USB2:CONFIGFS_OK
<12>[    1.508080] THYME-USB2:UDC=a600000.dwc3
<12>[    1.508289] THYME-USB2:NCM_OK
<12>[    1.508337] THYME-USB2:LINK_OK
<12>[    1.508375] THYME-USB2:BIND_ATTEMPT:a600000.dwc3
<12>[    1.508558] THYME-USB2:UDC_BOUND
<12>[    1.508583] THYME-USB2:NETDEV_FOUND=usb0
<12>[    1.508613] THYME-USB2:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER_ERRNO=22:MTU=1500
<12>[    1.508641] THYME-USB2:IF=usb0:MAC=26:17:44:57:ec:e6:IDX=8:ADDR_LEN=6:TYPE=1
<12>[    1.508660] THYME-USB2:FLAGS_BEFORE=0x1002
<12>[    1.508664] THYME-USB2:IFF_UP_ATTEMPT
<12>[    1.508682] THYME-USB2:IFF_UP_OK
<12>[    1.508686] THYME-USB2:FLAGS_AFTER=0x1003
<12>[    1.508690] THYME-USB2:ADMIN_UP_AFTER=YES
<12>[    1.508694] THYME-USB2:EXPECT_ADDR=10.66.73.1
<12>[    1.508698] THYME-USB2:EXPECT_NETMASK=255.255.255.0
<12>[    1.508727] THYME-USB2:SET_ADDR:RET=0:ERRNO=0
<12>[    1.508731] THYME-USB2:ADDR_SET_OK
<12>[    1.508752] THYME-USB2:SET_NETMASK:RET=0:ERRNO=0
<12>[    1.508755] THYME-USB2:NETMASK_SET_OK
<12>[    1.508760] THYME-USB2:GET_ADDR=10.66.73.1
<12>[    1.508764] THYME-USB2:GET_NETMASK=255.255.255.0
<12>[    1.508768] THYME-USB2:DEVICE_IPV4_VERIFIED
<12>[    1.508772] THYME-USB2:DEVICE_STATIC_IPV4_VERIFIED=YES
<12>[    1.508807] THYME-USB2:FIB_LOCAL_ADDR_PRESENT
<12>[    1.508818] THYME-USB2:CONNECTED_ROUTE_PRESENT
<12>[    1.508822] THYME-USB2:HOLD
<12>[    1.508839] THYME-USB2:T=0:FLAGS=0x1003:ADMIN=1:OPER=down:CARRIER=0:UDC=not attached:ADDR=10.66.73.1
<12>[    1.608927] THYME-USB2:T=100:FLAGS=0x1003:ADMIN=1:OPER=down:CARRIER=0:UDC=not attached:ADDR=10.66.73.1
<3>[    1.869956] android_work: sent uevent USB_STATE=CONNECTED
<6>[    1.877922] configfs-gadget gadget: high-speed config #1: c
<3>[    1.878045] android_work: sent uevent USB_STATE=CONFIGURED
<12>[    2.009041] THYME-USB2:UDC_CONFIGURED
<12>[    2.009075] THYME-USB2:T=500:FLAGS=0x1003:ADMIN=1:OPER=down:CARRIER=0:UDC=configured:ADDR=10.66.73.1
<12>[    2.509167] THYME-USB2:T=1000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured:ADDR=10.66.73.1
<12>[    3.509264] THYME-USB2:T=2000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured:ADDR=10.66.73.1
<12>[    6.509452] THYME-USB2:T=5000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured:ADDR=10.66.73.1
<12>[   11.509632] THYME-USB2:T=10000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured:ADDR=10.66.73.1
<12>[   21.509814] THYME-USB2:T=20000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured:ADDR=10.66.73.1
<12>[   31.509998] THYME-USB2:T=30000:FLAGS=0x1043:ADMIN=1:OPER=up:CARRIER=1:UDC=configured:ADDR=10.66.73.1
<12>[   31.510087] THYME-USB2:IF=usb0:FLAGS=0x1043:ADMIN_UP=YES:OPER=up:CARRIER=1:MTU=1500
<12>[   31.510315] THYME-USB2:DEV_ADDR=26:17:44:57:ec:e6
<12>[   31.510352] THYME-USB2:HOST_ADDR=92:14:6a:3a:0b:e3
<12>[   31.510389] THYME-USB2:NCM_IFNAME=usb0
<12>[   31.510424] THYME-USB2:HOLD_DONE
<12>[   31.510442] THYME-USB2:REBOOT_BOOTLOADER
```

HOLD → HOLD_DONE = **30.0016s**. restart2 after HOLD_DONE. No PID1 return. No `FAIL:` / `IPV4_MISMATCH`.

`FLAGS_BEFORE=0x1002` = `IFF_BROADCAST|IFF_MULTICAST`.  
`FLAGS_AFTER=0x1003` = plus `IFF_UP`.  
`T=1000` `0x1043` = plus `IFF_RUNNING`.

`ADDR=10.66.73.1` from T=0 through T=30000.

---

## 8. Correlation

```text
created after:     UDC bind
IFF_UP + IPv4:     immediately after usb0 appears (before host enum)
device MAC:        26:17:44:57:ec:e6  == configfs dev_addr
host MAC:          92:14:6a:3a:0b:e3  == configfs host_addr == en13
NCM_IFNAME:        usb0
USB lifetime:      en13 29.788s / gadget 30.005s / HOLD 30.002s
```

```text
SIOCSIFADDR:             PASS  RET=0 ERRNO=0
SIOCSIFNETMASK:          PASS  RET=0 ERRNO=0
SIOCGIFADDR:             10.66.73.1
SIOCGIFNETMASK:          255.255.255.0
DEVICE_ADMIN_UP:         YES
DEVICE_OPERSTATE:        up   (from T=1000 through T=30000)
DEVICE_CARRIER:          1    (from T=1000; 0 at T=0/100/500)
HOST_INTERFACE:          en13
HOST_STATUS:             active (from ~100ms after appear through HOLD)
HOST_PROJECT_IPV4:       NO
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
Stage1B regression:  NO
device netdev:       YES  usb0
SIOCGIFFLAGS:        PASS  FLAGS_BEFORE=0x1002
SIOCSIFFLAGS:        PASS  FLAGS_AFTER=0x1003 then 0x1043
SIOCSIFADDR:         PASS  errno=0
SIOCSIFNETMASK:      PASS  errno=0
SIOCGIFADDR:         10.66.73.1
SIOCGIFNETMASK:      255.255.255.0
ADMIN_UP_AFTER:      YES
operstate:           up
carrier:             1
host enX:            en13 active, MAC=host_addr
host IPv4:           NO (IPv4LL ignored)
```

Final gate: **`USB_STAGE2_DEVICE_STATIC_IP_PASS`**

Stop. Do not configure host IPv4 this round. Do not ping. Do not HTTP.

Next: host-side `10.66.73.2/24` only, still no ICMP / HTTP.
