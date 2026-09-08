# Route B stock-kernel USB Stage1 host link — thyme

Stage: `STOCK_KERNEL_USB_STAGE1_HOST_LINK`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Parent: `e6249a6` (USB0 PASS)

```text
USB_STAGE1_HOST_LINK_INACTIVE
```

Reuse Stage0 image. No rebuild. No flash. No IPv4. Host observation only.

macOS created `en10` for `THYME-USB0` and tore it down with the gadget.  
`status` stayed `inactive` for the whole ~30s HOLD. No carrier. No address.

TEST ONLY identity `1d6b:0104`. NOT PRODUCTION USB IDENTITY.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
New CI:                    NO
Slot A flashed:            NO
Any partition written:     NO
boot_b:                    reused Stage0 PASS image
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
IPv4 / DHCP / ping / curl / HTTP / Mainline / DTS: NO
```

---

## 2. Reused image

CI run `34232265858` commit `0845875` artifact boot SHA256:

```text
ce4114bee713b75e1b43df07dc18569cc1f3a7d67b4998f9401f5ee5c3380220
```

Android A Magisk root, stock-image-sized prefixes before this boot:

| Partition | Bytes | SHA256 | vs expect |
|---|---:|---|---|
| boot_b | 52666368 | `ce4114bee713b75e1b43df07dc18569cc1f3a7d67b4998f9401f5ee5c3380220` | MATCH Stage0 |
| vendor_boot_b | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` | MATCH stock |
| dtbo_b | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` | MATCH stock |
| vbmeta_b | 8192 flags=2 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` | MATCH stock |
| vbmeta_system_b | 4096 | `3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355` | MATCH stock |

If `boot_b` had drifted: STOP, do not reflash. It matched. Continue.

---

## 3. Slot metadata

```text
RETRY_BEFORE:          6
fastboot set_active b
RETRY_AFTER_SET_ACTIVE: 7   (current=b unbootable:b=no)
one fastboot reboot
RETRY_AFTER_BOOT:       6   (current=b unbootable:b=no)
then set_active a + reboot → Android A
second B start:        NO
manual key:            NO
```

`set_active b` this round raised retry 6→7. Do not treat that as a flash substitute. No partition was written.

---

## 4. Host baselines

Android A and Fastboot both had `en0`–`en7` only. `en7` is the Realtek USB LAN dongle, inactive. No leftover Stage0 NIC.

Fastboot USB: `18d1:d00d` serial `41a5627b` Location ID `0x02112000 / 11`.

NEW_IF is not hardcoded. Detected as `ifconfig -a` `en*` minus Fastboot baseline, timed against `THYME-USB0`.

---

## 5. Host USB / enX

`T0` = `2026-09-08T21:53:40.198` (`fastboot reboot`).

```text
fastboot disappear:        +0.729s
NEW_IF en10 appear:       +7.730s
USB gadget confirmed:    +7.922s
en10 disappear:          +37.536s
USB gadget disappear:     +37.659s
fastboot reappear:        +41.884s
en10 lifetime:            29.806s
adb fallback:             NONE
manual key:               NO
automatic:                YES
```

Timing matches Stage0 (`+0.712 / +7.565 / +37.660 / +41.283`). Not a Stage0 regression.

```text
enumerated:     YES
VID:PID:        1d6b:0104
Manufacturer:    thyme-mainline
Product:        Stock Kernel USB Enum Stage0
Serial:         THYME-USB0
Speed:          480 Mb/s
Location ID:    0x02112000 / 11   (same port as Fastboot)
```

`en10` first dump (only status sample; never changed):

```text
en10: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
	options=404<VLAN_MTU,CHANNEL_IO>
	ether 1a:68:69:38:e0:02
	nd6 options=201<PERFORMNUD,DAD>
	media: autoselect (none)
	status: inactive
```

```text
new interface:          en10
first seen:             T0+7.730s
MAC:                    1a:68:69:38:e0:02
MTU:                    1500
media:                  autoselect (none)
status initially:       inactive
status after 1s:       inactive
status stable:         inactive
first active:           NEVER
IPv4:                   none
IPv6 link-local:        none
```

IOKit class counts (global) while `en10` existed:

```text
AppleUSBNCMControl  0→1
AppleUSBNCMData     0→1
AppleUSBCDCControl   0→1
IOEthernetInterface  8→9
```

On gadget removal: counts reverse, `en10` disappears.  
`LINK_DOWN_ON_GADGET_REMOVAL: YES`.

`ioreg -p IOUSB` showed `IOUSBHostDevice` `Stock Kernel USB Enum Stage0@02112000` (`idVendor=7531` `idProduct=260`). NCM children are not on the IOUSB plane; binding is from the class-count delta plus `en10` lifetime.

No `ifconfig inet`, no `networksetup -setmanual`, no routes.

---

## 6. Recovery

```text
fastboot set_active a
current-slot: a
fastboot reboot
adb:            41a5627b device
slot_suffix:    _a
boot_completed: 1
uid:            0
```

Oops not re-read. Stage0 USB timeline matched. Automatic Fastboot returned.

---

## 7. Classification

```text
USB device enumerated:   YES
new enX:                 YES  en10
status active:           NO   inactive entire HOLD
link down on removal:    YES
Stage0 regression:       NO
host capture:            enough
```

Final gate: **`USB_STAGE1_HOST_LINK_INACTIVE`**

Stop. Do not assign host/device IPv4. Next is device-side NCM carrier / `usb0` operstate, not Stage2 static IP.
