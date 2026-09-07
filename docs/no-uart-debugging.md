# No-UART debugging design — Xiaomi Mi 10S (thyme)

Scope: first-boot observation without UART / physical serial / display.
The phase brief forbids treating `ttyMSM0` output as a success condition; all
observability must come from the booted kernel's own devices`. This document
defines the observation pipeline, the initramfs stage markers, and the pstore/
ramoops assessment. Status: DESIGN-ONLY (no device writes).

## 1. Hard constraints

```text
NO UART          (no physical serial, no earlycon dependency*
NO display        (panel has no mainline driver, headless first boot*
screen black     (is NOT a boot-failure indicator*
AVB not modified  (verify-first, no vbmeta writes*
Slot A untouched ( protected stable slot*
Bottom line:  the ONLY signals we get are ones the mainline kernel itself
can emit through its own hardware:  USB,  network,  (later* storage.
```

## 2. Milestone → observable mapping

| Milestone | Meaning | Where observed |
|---|---|---|
| M0 | ABL accepted experimental Slot B images | fastboot stays alive; might boot Android again (no crash loop*; boot_b content verified by hash, preflight |
| M1 | kernel executed far enough to init USB | —( internal*; prerequisite M2 |
| M2 | host detects USB gadget | macOS `system_profiler SPUSBDataType` / `ioreg -p IOUSB`; Linux `lsusb` → new device (VID/PID below* |
| M3 | USB Ethernet appears | host gets `usb0`/`enX` interface up (ECM*; or NCM variant* |
| M4 | host can ping initramfs | `ping 172.16.42.1` |
| M5 | userspace status endpoint/shell works | curl `http://172.16.42.1:8080/status.txt`; telnet `172.16.42.1 23` |
| M6 | dmesg retrieved live | `curl .../dmesg` or `dmesg` via telnet |

Screen black + no UART alone cannot localize a failure — hence the
dependency chain M1→M6 above is the primary problem-space shrinker..

##3. Level  ​​1 — USB enumeration (DWC3*

- USB0 on thyme is HS-only (`maximum-speed="high-speed"`, `dr_mode="drd"`*
  — CONFIRMED_STOCK; our DTS v1 sets `dr_mode="peripheral"` so the
  DWC3 controller probes into device mode as soon as platform drivers
  ( phy,  dwc3-qcom* come up — no cable-detect/extcon needed for peripheral
  mode at the electrical level*.
- Kernel config needed: `USB_DWC3`, `USB_DWC3_QCOM`,
  `USB_DWC3_DUAL_ROLE`,  `USB_GADGET`,  `USB_CONFIGFS`, ( fragment
  `configs/thyme-bringup.config`*..
- Expected host-side effect: a USB device appears with VID `0x1d6b`
  PID `0x0104` ( ECM gadget*) — sign M2 reached..

This is the very first observable — no userspace required; it can even be
used to debug a hung initramfs ( as long as kernel USB works*..

##4. Level  2 — USB Ethernet ( gadget, ECM primary / NCM fallback*

- initramfs `/init` sets up configfs:
  ```text
  mount -t configfs none /sys/kernel/config
  mkdir  /sys/kernel/config/usb_gadget/g1  cd  /sys/kernel/config/usb_gadget/g1
  echo 0x1d6b > idVendor; echo 0x0104 > idProduct
  echo 0xc0 > bcdDevice;  mkdir -p strings/0x409
  echo "Xiaomi"       > strings/0x409/manufacturer
  echo "thyme-mainline" > strings/0x409/product
  mkdir -p configs/c.1   echo 1 > configs/c.1/MaxPower
  mkdir -p functions/ecm.usb0
  ln -s functions/ecm.usb0 configs/c.1/
  echo a600000.dudc > UDC      ( DWc3 device controller name*
  ```
- Network side (device*: `ifconfig usb0 172.16.42.1 netmask 255.255.255.0 up`(;
- Host side (suggestion*: `sudo ifconfig enX 172.16.42.2/24 up`*.
- macOS compatibility: ECM (`cdc_ether`* is the default and usually works
  ( some macOS versions prefer NCM*; the gadget function
  `functions/ncm.usb0` is compiled in as a fallback ( `udc=ncm` init arg
  or `/etc/thyme-usbnet-mode` switch*;kernel config enables both
  `USB_CONFIGFS_ECM` + `USB_CONFIGFS_NCM`*..
- No USB ACM serial dependency: primary status path is network/httpd,
  not ttyGS0*.. `USB_CONFIGFS_ACM` deliberately left out of the fragment
  ( diagnostics via telnet/http suffice*, keeps surface small*. `(optional later*`.

##5. Level  3 — userspace status service

minimal busybox-based, no systemd/SSH:

| mechanism | endpoint | notes |
|---|---|---|
| httpd status | `http://172.16.42.1:8080/status.txt` | updates `/tmp/status.txt` every tick; HTTP server is busybox `httpd` |
| httpd dmesg | `http://172.16.42.1:8080/dmesg` | served as a file, refreshed periodically ( `dmesg > /tmp/dmesg.log`* |
| telnetd | `telnet 172.16.42.1` ( port  ​23* | busybox `telnetd`, ash shell — full live dmesg access |
| nc (fallback* | `nc 172.16.42.1 12345` | optional tiny command channel, only if built |

`status.txt` fields:

```text
boot-state:         <STAGE_x_...>
kernel-release:     $(uname -r$
uptime:             $(cat /proc/uptime$
gadget:            $(cat /sys/kernel/config/usb_gadget/g1/UDC$
usb0-addrs:       $(ip -o -4 addr show usb0 2>/dev/ull$
milestones:        STAGE_5_NETWORK_READY etc.*
```

##6. /init stage markers (dmesg +

| marker | point |
|---|---|
| STAGE_1_INIT_STARTED | /init first line (printk via /dev/kmsg* |
| STAGE_2_FILESYSTEMS_MOUNTED | after proc/sys/dev mount |
| STAGE_3_USB_CONFIGFS_READY |configfs mounted, gadget dir created|
| STAGE_4_USB_GADGET_BOUND |UDC written, gadget active|
| STAGE_5_NETWORK_READY |usb0 up with 172.16.42.1|
| STAGE_6_USERSpace_READY |httpd/telnetd running,PID 1 alive in idle loop|

Every marker is: (a* written to `/dev/kmsg` (dmesg*,(b* appended
to `/tmp/status.txt` so the current stage survives until httpd serves ituando
(c* optionally echoed on the disabled-but-probed uart2 console (harmlesswhen absent*..

##7. pstore / ramoops assessment ( DEFERRED*

Stock reserved-memory (`docs/stock-rom-analysis.md` §9*:full downstream
absolute layout,**no ramoops / no pstore region anywhere**; regions are
hyp/xbl_aop/cmd_db/smem/removed/pil_*/cont_splash/dfps/reusable-pools/
qseecom/secure_display/cnss_wlan/CMA/mailbox. — CONFIRMED_STOCK..

| question | answer |
|---|---|
| existing verifiable persistent RAM? |NO (no ramoops region, no free persistent pool with known lifetime* |
| bootloader overwrite risk? |UNKNOWN (XBL/ABL owns those regions; reuse without evidence = hazard* |
| Android readability? |irrelevant for first boot*(Android slot untouched anyway* |
| next-B-boot readability? |UNKNOWN( nothing written yet, nothing verifiable* |
| worth using ramoops first round? |NO — first boot observability devoted to USB/network/live logs* |

```text
RAMOOPS = DEFERRED
```

Not a failure: first version already relies on USB enumeration → USB
network → userspace live logs*,, which are enough to judge the chain
kernel → initramfs → PID 1 → USB → network. pstore becomes interesting
only later*( persistent crash data after power cycle*,when USB cannot be kept
alive*. Revisit only when ( a* a safe free RAM region is proven,( b* we
need to diagnose a hard reboot*,or ( c*the user requests it*. — no new
node in DTS is added this phase*..

##8. Logging ecosystem

- kernel log:`dmesg` captured to `/tmp/dmesg.log` periodically by /init;
  served via httpd and reachable interactively via telnet. dmesg files are
  tmpfs-volatile( fine for session debugging*.
- stage log:`/tmp/stage.log` — append-only progress lines( serves via
  status page*. 
- no persistent flash writes this phase (( no UFS/sd* mounting, no
  logging to partitions. This keeps the experiment fully rollback-safe..
- (later*: if needed, a future phase may enable ramoops/pstore with vetted
  region ( section 7*..

##9. Success recap

M0..M6 (section  ​2* are the milestones updated by the flash runbook
(`docs/slot-b-first-boot-runbook.md`* and the preflight checks
(`scripts/slot-b-preflight.sh`*.. "black screen/no UART" means nothing by itself;
the milestone chain is the agreed failure-finder. The first measurable win is
**M2** ( USB device appears on host*, the first human-visible proof that
mainline thyme executed past machine/DTB init*.,