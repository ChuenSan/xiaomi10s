# Route B stock-kernel USB Stage1 device-netdev observe — thyme

Stage: `STOCK_KERNEL_USB_STAGE1_DEVICE_NETDEV_OBSERVE`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Parent: `4c9364a` (`USB_STAGE1_HOST_LINK_INACTIVE`)

Device test pending CI.

TEST ONLY identity `1d6b:0104`. NOT PRODUCTION USB IDENTITY.

Descriptor-only change vs USB0: Product `Stock Kernel USB Stage1 Device Observe`, Serial `THYME-USB1DEV`.

No `SIOCSIFFLAGS`. No IFF_UP. No IP. No Stage1B.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
Slot A flashed:           NO
Only partition written:   boot_b (after CI; pending)
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
IFF_UP / IP / route / ping / DHCP / HTTP / Mainline / DTS: NO
```

---

## 2. Android A read-only reference

```text
slot_suffix=_a
boot_completed=1
uid=0 (Magisk)
sys.usb.config=adb
UDC=a600000.dwc3 state=configured function=g1
g1 VID:PID=18d1:4ee7 configs/b.1 -> ffs.adb
functions include ncm.0 (unlinked)
ncm.0 dev_addr/host_addr/ifname: ENODEV (function not bound)
/sys/class/net: no usb/ncm/rndis
ANDROID_A_NCM_REFERENCE=NOT_AVAILABLE
setprop sys.usb.config: NOT USED
```

---

## 3. Helper

Reuse USB0: `/config` configfs, `newfstatat`+`S_ISDIR`, NCM `ncm.usb0`, UDC scan, bind, 30s HOLD, `restart2("bootloader")`.

Added:

```text
PREBIND_NETS baseline-diff of /sys/class/net
NETDEV_AFTER_FUNCTION / LINK / BIND
SIOCGIFFLAGS via socket(AF_INET,SOCK_DGRAM,0) (read only)
T=0,100,500,1000,2000,5000,10000,20000,30000
UDC_STATE + UDC_CONFIGURED
compact kmsg THYME-USB1DEV:
```

---

## 4. CI / device results

Pending.
