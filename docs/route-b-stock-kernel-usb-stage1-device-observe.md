# Route B stock-kernel USB Stage1 device-netdev observe — thyme

Stage: `STOCK_KERNEL_USB_STAGE1_DEVICE_NETDEV_OBSERVE`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Head: `d8c4422`

```text
USB_STAGE1_DEVICE_ADMIN_DOWN
```

USB0 path reused. Device NCM netdev `usb0` appears after UDC bind.  
`SIOCGIFFLAGS` has no `IFF_UP` for the whole 30s HOLD.  
`operstate=down`. sysfs `carrier` unread (`NOT_PRESENT`) while admin-down.  
macOS `en11` MAC matches configfs `host_addr`. Host `status: inactive`.

TEST ONLY identity `1d6b:0104`. NOT PRODUCTION USB IDENTITY.  
Descriptor-only vs USB0: Product `Stock Kernel USB Stage1 Device Observe`, Serial `THYME-USB1DEV`.

No `SIOCSIFFLAGS`. No IFF_UP. No IP. No Stage1B this round.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
Slot A flashed:           NO
Only partition written:   boot_b
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
IFF_UP / IP / route / ping / DHCP / HTTP / Mainline / DTS / Stage1B: NO
```

---

## 2. Android A read-only reference (before flash)

```text
slot_suffix=_a  boot_completed=1  uid=0
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
| boot_b @52666368 | `ce4114be…380220` | Stage0 PASS image |
| vendor_boot_b | `aac7e11f…041972` | MATCH stock |
| dtbo_b | `018fa85c…e64634` | MATCH stock |
| vbmeta_b | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b | `32174550…8b8355` | MATCH stock |

oops 16MiB prefix `5addd7f4…`. minidump/rawdump/logdump prefixes unchanged after this boot.

---

## 3. CI

```text
workflow: thyme-stock-kernel-usb-stage1-device-observe
run:      34239964653
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34239964653
commit:   d8c4422d7ccf2b7f1604f0a6d4183a8a4e663f3a
artifact: thyme-stock-kernel-usb-stage1-device-observe-d8c4422d7ccf2b7f1604f0a6d4183a8a4e663f3a
```

```text
STOCK_KERNEL_EXACT              PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
STATIC_INIT                     PASS
ENTRY_RX                        PASS
USB0_REGRESSION_CHECK           PASS
NETDEV_DIFF_LOGIC               PASS
SIOCGIFFLAGS_ONLY               PASS
NO_SIOCSIFFLAGS                 PASS
NO_IP_LOGIC                     PASS
FAILSAFE                        PASS
BOOT_V3                         PASS
REVERSE_UNPACK                  PASS
SIZE_GATE                       PASS  52670464
READY_FOR_USB_STAGE1_DEVICE_OBSERVE
```

```text
boot SHA256: 4cc9be7e7344ffe69d8b4ab7bee8a948bb91302358f551cbe76d19bb797e2912
ELF:         12088B static aarch64 ET_EXEC
```

DESCRIPTOR_ONLY_CHANGE: product/serial.

---

## 4. Flash

Fastboot: `product=thyme` `unlocked=yes` `current-slot=a` `snapshot=none` `battery-soc-ok=yes`.

```text
WRITE: boot_b ONLY
RETRY_BEFORE_FLASH: 6
AFTER_FLASH:        retry:b=7  unbootable:b=no  current=a
```

Post-write Android A hash of `boot_b` @52670464 = `4cc9be7e…797e2912` MATCH artifact. Other B payloads still stock.

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

`T0` = `fastboot_reboot_finished_unix=1788878988.037`

```text
fastboot disappear:  +0.801s
NEW_IF en11 appear:  +7.291s
gadget appear:       +7.324s
en11 disappear:      +37.492s
gadget disappear:    +37.517s
fastboot reappear:   +41.209s
en11 lifetime:       30.201s
gadget hold:         30.193s
adb fallback:        NONE
manual key:          NO
```

```text
enumerated:    YES
VID:PID:       1d6b:0104  (PID1 identity; host matcher THYME-USB1DEV / Stage1 Device Observe / thyme-mainline)
Product:       Stock Kernel USB Stage1 Device Observe
Serial:        THYME-USB1DEV
new enX:       en11
MAC:           32:25:d0:3a:19:22
MTU:           1500
media:         autoselect (none)
status:        inactive entire HOLD
first active:  NEVER
IPv4/IPv6:     none
host flags:    8822<BROADCAST,SMART,SIMPLEX,MULTICAST>  (no UP)
```

No host `ifconfig up`, inet, or route.

---

## 7. Device (oops Index 1167)

oops 16MiB `5addd7f4…` → `26e3b6a5…`. New record **Index 1167**.  
minidump / rawdump / logdump 16MiB prefixes **unchanged**.

```text
Reason:  Restart
cmdline: androidboot.slot_suffix=_b
kernel:  4.19.157-perf  #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023
```

```text
<6>[    1.419748] Run /init as init process
<12>[    1.419884] THYME-USB1DEV:INIT
<12>[    1.419893] THYME-USB1DEV:DEVICE_NETDEV_OBSERVE=YES
<12>[    1.419897] THYME-USB1DEV:SIOCGIFFLAGS=YES
<12>[    1.419901] THYME-USB1DEV:READ_ONLY_NETDEV_OBSERVATION=YES
<12>[    1.419931] THYME-USB1DEV:SYSFS_OK
<12>[    1.419965] THYME-USB1DEV:MOUNT_CONFIGFS:RET=0:ERRNO=0
<12>[    1.419986] THYME-USB1DEV:CONFIGFS_OK
<12>[    1.419997] THYME-USB1DEV:UDC=a600000.dwc3
<12>[    1.420058] THYME-USB1DEV:PREBIND_STATE=not attached
<12>[    1.420095] THYME-USB1DEV:PREBIND_NETS=lo,dummy0,ip6tnl0,ip_vti0,bond0,sit0,ip6_vti0
<12>[    1.420111] THYME-USB1DEV:SOCK_OK
<12>[    1.420236] THYME-USB1DEV:NCM_OK
<12>[    1.420249] THYME-USB1DEV:DEV_ADDR=NOT_PRESENT
<12>[    1.420258] THYME-USB1DEV:HOST_ADDR=NOT_PRESENT
<12>[    1.420266] THYME-USB1DEV:NCM_IFNAME=NOT_PRESENT
<12>[    1.420274] THYME-USB1DEV:NETDEV_AFTER_FUNCTION=lo,dummy0,ip6tnl0,ip_vti0,bond0,sit0,ip6_vti0
<12>[    1.420288] THYME-USB1DEV:FUNCTION_LINKED
<12>[    1.420324] THYME-USB1DEV:NETDEV_AFTER_LINK=lo,dummy0,ip6tnl0,ip_vti0,bond0,sit0,ip6_vti0
<12>[    1.420328] THYME-USB1DEV:BIND_ATTEMPT:a600000.dwc3
<12>[    1.420498] THYME-USB1DEV:UDC_BOUND
<12>[    1.420519] THYME-USB1DEV:NETDEV_AFTER_BIND=usb0,lo,dummy0,ip6tnl0,ip_vti0,bond0,sit0,ip6_vti0
<12>[    1.420523] THYME-USB1DEV:NETDEV_FOUND=usb0
<12>[    1.420553] THYME-USB1DEV:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT:MTU=1500
<12>[    1.420580] THYME-USB1DEV:IF=usb0:MAC=42:91:86:b0:8a:dd:IDX=8:ADDR_LEN=6:TYPE=1
<12>[    1.420594] THYME-USB1DEV:IF=usb0:SYSFLAGS=0x1002:CARRIER_CHANGES=1
<12>[    1.420598] THYME-USB1DEV:HOLD
<12>[    1.420606] THYME-USB1DEV:T=0:UDC_STATE=not attached
<12>[    1.420618] THYME-USB1DEV:T=0:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[    1.520695] THYME-USB1DEV:T=100:UDC_STATE=not attached
<3>[    1.734431] android_work: sent uevent USB_STATE=CONNECTED
<6>[    1.743520] configfs-gadget gadget: high-speed config #1: c
<3>[    1.743613] android_work: sent uevent USB_STATE=CONFIGURED
<12>[    1.920809] THYME-USB1DEV:T=500:UDC_STATE=configured
<12>[    1.920819] THYME-USB1DEV:UDC_CONFIGURED
<12>[    2.421014] THYME-USB1DEV:T=1000:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[    3.421217] THYME-USB1DEV:T=2000:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[    6.421444] THYME-USB1DEV:T=5000:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[   11.421669] THYME-USB1DEV:T=10000:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[   21.421867] THYME-USB1DEV:T=20000:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[   31.422066] THYME-USB1DEV:T=30000:IF=usb0:FLAGS=0x1002:ADMIN_UP=NO:OPER=down:CARRIER=NOT_PRESENT
<12>[   31.422316] THYME-USB1DEV:IF=usb0:SYSFLAGS=0x1002:CARRIER_CHANGES=2
<12>[   31.422369] THYME-USB1DEV:DEV_ADDR=42:91:86:b0:8a:dd
<12>[   31.422407] THYME-USB1DEV:HOST_ADDR=32:25:d0:3a:19:22
<12>[   31.422443] THYME-USB1DEV:NCM_IFNAME=usb0
<12>[   31.422481] THYME-USB1DEV:HOLD_DONE
<12>[   31.422499] THYME-USB1DEV:REBOOT_BOOTLOADER
```

HOLD → HOLD_DONE = **30.0019s**. restart2 after HOLD_DONE. No PID1 return.

`FLAGS=0x1002` = `IFF_BROADCAST|IFF_MULTICAST`. No `IFF_UP`.

sysfs `carrier` is `NOT_PRESENT` while admin-down (not sampled as 0). Do not treat that as a physical-link measurement.

---

## 8. Correlation

```text
created after:     UDC bind (not function mkdir, not config symlink)
device MAC:        42:91:86:b0:8a:dd  == configfs dev_addr (readable after bind/hold)
host MAC:          32:25:d0:3a:19:22  == configfs host_addr
NCM_IFNAME:        usb0
USB lifetime:      en11 30.201s / gadget 30.193s / HOLD 30.002s
```

```text
ADMIN_UP:     NO
CARRIER:      NOT_PRESENT (sysfs while admin-down)
OPERSTATE:    down
HOST_STATUS:  inactive
```

---

## 9. Recovery

```text
fastboot set_active a
adb:            device
slot_suffix:    _a
boot_completed: 1
uid:            0
```

---

## 10. Classification

```text
USB0 regression:     NO
device netdev:       YES  usb0
created after:       BIND
IFF_UP:              NO  (0x1002 entire HOLD, including after UDC_CONFIGURED)
operstate:           down
carrier sysfs:       NOT_PRESENT
host enX:            en11 inactive, MAC=host_addr
```

Final gate: **`USB_STAGE1_DEVICE_ADMIN_DOWN`**

Stop. Do not set `IFF_UP` in this round. Next is `STOCK_KERNEL_USB_STAGE1B_DEVICE_NETDEV_UP` (`SIOCSIFFLAGS` / `old_flags | IFF_UP` only). Still no IP.
