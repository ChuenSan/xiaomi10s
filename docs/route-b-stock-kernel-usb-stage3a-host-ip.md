# Route B stock-kernel USB Stage3A host static IPv4 — thyme

Stage: `STOCK_KERNEL_USB_STAGE3A_HOST_STATIC_IP`
Date: 2026-09-09
Branch: `route-b-v3`
Reused image: Stage2 `boot_b`

```text
USB_STAGE3A_HOST_STATIC_IP_ROUTE_PASS
```

## 1. Scope

```text
reused Stage2 image: YES
build:              NO
flash:              NO
Slot A modified:    NO
ping:               NO
HTTP:               NO
ARP:                NO
manual route add:   NO
persistent host network change: NO
```

The first 11:18:56 run was an invalid observation-only detector run: its
checker queried `ioreg` for a root gadget that macOS exposes through
`system_profiler`. It performed no host IP configuration and is not counted.
This report is the corrected 11:24:15 run.

## 2. Android A and Fastboot preflight

```text
ADB_DEVICE_PRESENT=YES
slot_suffix=_a
boot_completed=1
uid=0 (Magisk)
boot_b prefix bytes: 52670464
boot_b SHA256: 88c4d8a5be098a508356120a02bdfb16e78b576b1876aaa98d06e945b7316b49
expected SHA256:      88c4d8a5be098a508356120a02bdfb16e78b576b1876aaa98d06e945b7316b49
BOOT_B_STAGE2_HASH_MATCH=YES
```

```text
product=thyme
unlocked=yes
current-slot=a
slot-unbootable:b=no
slot-retry-count:b=6
snapshot-update-status=none
battery-soc-ok=yes
```

Host baseline contained `en0`–`en7`; no project IPv4 was present.

```text
PRETEST_ROUTE_INTERFACE=utun4
PREEXISTING_ROUTE_COLLISION=YES
```

`route -n get 10.66.73.1` before the test selected the pre-existing VPN
route `8.0.0.0/5` through `utun4`. The VPN was not changed.

## 3. Dynamic USB identity and interface

Baseline-to-runtime diff selected the new interface; `en13` was not
hard-coded by the detector.

```text
USB_ENUMERATED=YES
VID:PID=1d6b:0104
Manufacturer=thyme-mainline
Product=Stock Kernel USB Stage2 Device IP
Test serial descriptor=THYME-USB2
NEW_IF=en13
HOST_MAC=1e:ee:6a:3b:14:c0
```

The current-run device record was read read-only from `oops`, Index `1178`:

```text
THYME-USB2:HOST_ADDR=1e:ee:6a:3b:14:c0
THYME-USB2:NCM_IFNAME=usb0
```

Therefore the host interface MAC exactly matched the runtime NCM
`host_addr`. The `pstore` mount was empty; the `oops` record supplied the
same read-only correlation without any communication test.

## 4. Host static IPv4

Before configuration:

```text
HOST_LINK_ACTIVE_BEFORE_IP=YES
media: autoselect (100baseTX <full-duplex>)
status: active
HOST_IPV4LL_BEFORE_STATIC=NO
```

Command and result:

```text
sudo ifconfig en13 inet 10.66.73.2 netmask 255.255.255.0
return=0
HOST_STATIC_ADDR_VERIFIED=YES
address=10.66.73.2
netmask=0xffffff00 (/24)
HOST_LINK_ACTIVE_AFTER_IP=YES
```

The interface remained `status: active` after the ephemeral address was set.

## 5. Route verification

`route -n get 10.66.73.1` during the test:

```text
 destination: 10.66.73.0
        mask: 255.255.255.0
   interface: en13
       flags: <UP,DONE,CLONING>
     gateway: NONE
```

```text
ROUTE_INTERFACE=en13
CONNECTED_ROUTE_PRESENT=YES
```

`netstat -rn -f inet` contained:

```text
10.66.73/24        link#26            UC                   en13      !
```

The connected route was created naturally by interface address
configuration. No `route add` was used.

## 6. Lifetime and recovery

```text
fastboot_reboot_finished_unix=1788924275.209
fastboot_disappear_unix=1788924276.046  (+0.837s)
gadget_appear_unix=1788924282.726        (+7.517s)
new_en_appear_unix=1788924282.867        (+7.658s)
new_en_disappear_unix=1788924312.939     (en13 lifetime 30.072s)
gadget_disappear_unix=1788924316.439
fastboot_reappear_unix=1788924316.462
```

```text
RETRY_BEFORE=6
AFTER_SET_ACTIVE=b
RETRY_AFTER_SET_ACTIVE=7
current-slot after Stage2 boot=b
slot-retry-count:b after Stage2 boot=6
slot-unbootable:b after Stage2 boot=no
set_active a: return=0
Android A restored: YES
slot_suffix=_a
boot_completed=1
NEW_IF_AFTER_RECOVERY=DISAPPEARED:en13
```

Routes after recovery returned to the pre-test state:

```text
POSTTEST_ROUTE_INTERFACE=utun4
```

## 7. Gate checklist

```text
USB_ENUMERATED=YES
NEW_IF_FOUND=YES
dynamic interface: en13
NCM host_addr == host interface MAC: YES
HOST_LINK_ACTIVE_BEFORE_IP=YES
HOST_STATIC_IP=10.66.73.2
HOST_NETMASK=/24
HOST_STATIC_ADDR_VERIFIED=YES
HOST_LINK_ACTIVE_AFTER_IP=YES
route interface=en13
CONNECTED_ROUTE_PRESENT=YES
pre-test route interface=utun4
during-test route interface=en13
post-test route interface=utun4
NO_PING_RUN=YES
NO_HTTP_RUN=YES
```

Final Gate: **`USB_STAGE3A_HOST_STATIC_IP_ROUTE_PASS`**

Stop here. The next independent experiment is Stage3B interface-bound ICMP;
it was not run in this stage.
