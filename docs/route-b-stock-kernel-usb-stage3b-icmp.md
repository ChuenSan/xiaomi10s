# Route B stock-kernel USB Stage3B interface-bound ICMP — thyme

Stage: `STOCK_KERNEL_USB_STAGE3B_INTERFACE_BOUND_ICMP`  
Date: `2026-09-09`  
Branch: `route-b-v3`  
Reused image: Stage2 `boot_b`  
Primary run: `work/usb-stage3b-icmp-20260909-122651.log`

```text
USB_STAGE3B_INTERFACE_BOUND_ICMP_PASS
```

A second independent run at `12:24:01` also passed with 4/4 replies. The
`12:26:51` run is used below as the primary record.

## 1. Scope

```text
reused Stage2 image: YES
build:              NO
new CI build:       NO
new artifact:       NO
flash:              NO
persistent host network change: NO
manual route add:   NO
HTTP:               NO
TCP application test: NO
UDP application test: NO
SSH:                NO
Telnet:             NO
```

Only the host temporary IPv4 address and ICMP traffic were added.

## 2. Android A and payload preflight

```text
ADB_DEVICE_PRESENT=YES
slot_suffix=_a
boot_completed=1
uid=0 (root)
product=thyme
unlocked=yes
current-slot=a
slot-successful:b=no
slot-unbootable:b=no
slot-retry-count:b=6
snapshot-update-status=none
battery-soc-ok=yes
```

All read-only payload checks matched the recorded Stage2/stock values:

| Partition | Bytes | SHA256 | Result |
|---|---:|---|---|
| `boot_b` | 52670464 | `88c4d8a5be098a508356120a02bdfb16e78b576b1876aaa98d06e945b7316b49` | Stage2 match |
| `vendor_boot_b` | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` | stock match |
| `dtbo_b` | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` | stock match |
| `vbmeta_b` | 8192 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` | stock match |
| `vbmeta_system_b` | 4096 | `3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355` | stock match |

## 3. USB identity and dynamic interface

Fastboot baseline contained `en0`–`en7`; `en13` was selected only from the
baseline/runtime interface diff.

```text
USB_IDENTITY_MATCHED=YES
VID:PID=1d6b:0104
Manufacturer=thyme-mainline
Product=Stock Kernel USB Stage2 Device IP
Serial=THYME-USB2
NEW_IF=en13
HOST_MAC=ae:db:61:d7:2e:d0
```

`en13` was active before host IPv4 configuration. No IPv4LL address was used.

## 4. Host IPv4 and route gate

```text
address=10.66.73.2
netmask=0xffffff00 (/24)
HOST_STATIC_ADDR_VERIFIED=YES
HOST_LINK_ACTIVE_BEFORE_IP=YES
HOST_LINK_ACTIVE_AFTER_IP=YES
```

The pre-test route deliberately demonstrated the existing VPN collision:

```text
pre-test interface=utun4
```

During the USB window, both route checks selected the THYME NCM interface:

```text
route -n get 10.66.73.1:
  destination: 10.66.73.0
  mask: 255.255.255.0
  interface: en13

connected route:
10.66.73/24  -> en13

ROUTE_COLLISION=NO
```

After the gadget disappeared and Android A was restored, the route returned to
`utun4`, proving that the test-time route came from the USB connected route.

## 5. ICMP data-plane test

macOS help confirmed both required binding options: `-S src_addr` and
Apple-specific `-b boundif`.

Exact command:

```text
ping -n -S 10.66.73.2 -b en13 -c 4 -W 1000 -t 6 10.66.73.1
```

```text
source=10.66.73.2
destination=10.66.73.1
sent=4
received=4
packet loss=0.0%
RTT min/avg/max/stddev=0.784/1.023/1.453/0.255 ms
```

The repeat run produced `0.755/1.000/1.422/0.258 ms`.

## 6. Interface-specific packet capture

```text
tcpdump used: YES
capture interface: en13
filter: arp or icmp
```

The primary capture recorded:

```text
ARP request: 10.66.73.2 -> who-has 10.66.73.1
ARP reply:   10.66.73.1 is-at c2:5b:33:6e:3d:1e
ICMP request: 4 captured, 10.66.73.2 -> 10.66.73.1
ICMP reply:   4 captured, 10.66.73.1 -> 10.66.73.2
packets captured: 10
packets received by filter: 35
packets dropped by kernel: 0
```

This is interface-specific evidence on `en13`; it does not rely on the
`utun4` route or on a bare ping result.

## 7. ARP

```text
neighbor: 10.66.73.1
MAC: c2:5b:33:6e:3d:1e
interface: en13
```

The current run's `DEV_ADDR` was not available through Android A pstore or
`/proc/last_kmsg`. Record the correlation separately; it is not required for
the interface-bound L3 milestone:

```text
ARP_DEV_ADDR_MATCH=UNAVAILABLE
DEV_ADDR_CORRELATION_IN_THIS_RUN=NOT_AVAILABLE
```

## 8. Slot and recovery

```text
RETRY_BEFORE=6
RETRY_AFTER_SET_ACTIVE=7
RETRY_AFTER_BOOT=6
slot-unbootable:b after boot=no
current-slot after Stage2 window=b
set_active a: return=0
Android A restored: YES
slot_suffix=_a
boot_completed=1
NEW_IF_AFTER_RECOVERY=DISAPPEARED:en13
```

## 9. Final gate

```text
USB_STAGE3B_INTERFACE_BOUND_ICMP_PASS
```

```text
USB_NCM_END_TO_END_L3_CONFIRMED=YES
DEV_ADDR_CORRELATION_IN_THIS_RUN=NOT_AVAILABLE
```

The milestone is based on the interface/source-bound 4/4 ICMP exchange and
bidirectional packet capture on `en13`. The unavailable current-run
`ARP MAC == configfs dev_addr` comparison is recorded separately and does not
weaken the L3 conclusion.

No HTTP or other application-layer test was run. Stage4 HTTP liveness is the
next independent gate.

Evidence:

- `work/usb-stage3b-icmp-20260909-122651.log`
- `work/usb-stage3b-icmp-20260909-122651.tcpdump.log`
- `work/usb-stage3b-icmp-20260909-122401.log`
- `work/usb-stage3b-icmp-20260909-122401.tcpdump.log`
