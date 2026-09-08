# Route B stock-kernel + mininit control — thyme

Stage: `ROUTE_B_STOCK_KERNEL_MINIMAL_INITRAMFS_CONTROL`  
Branch: `route-b-v3`

Single variable vs verified Pure Stock B: replace **generic ramdisk only**.
Keep stock kernel, stock vendor_boot_b, stock dtbo_b, stock vbmeta_b (flags=2),
stock vbmeta_system_b, stock firmware_b.

Question: can our BusyBox mininit / USB liveness run on the V14 4.19.157-perf
kernel that already handed off on Slot B?

---

## 1. Constraint compliance (running)

```text
Local compilation: NO
Local build: NO
Slot A flashed: NO
Only partition written: NONE (CI first)
```

---

## 2. Why NCM, not ECM

Stock `android-kernel-sm8250` `vendor/kona-perf_defconfig`:

```text
CONFIG_USB_CONFIGFS=y
CONFIG_USB_CONFIGFS_NCM=y
```

No `CONFIG_USB_CONFIGFS_ECM`. ECM mkdir would fail on this kernel.
VID/PID `0x1d6b:0x0104` Linux Foundation Multifunction Composite Gadget.

Subnet: `10.66.73.1/24` (not `172.16.42.1`).

---

## 3. Image construction

Workflow: `.github/workflows/thyme-stock-kernel-mininit-control.yml`  
(`workflow_dispatch` only; does not build linux-6.6 / DTS / vendor_boot / dtbo)

```text
input:  official V14.0.6.0.TGACNXM boot.img
        SHA256 9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be
kernel: exact unpack payload
ramdisk: BusyBox 1.36.1 static + initramfs/stock-kernel-mininit-init
header: v3, os 13.0.0, SPL 2023-09, cmdline empty (from stock unpack)
```

CI input of `boot.img` (git-ignored, not committed):

1. `workflow_dispatch` `stock_boot_url`
2. repo variable/secret `STOCK_BOOT_IMG_URL`
3. draft release tag `stock-V14.0.6.0.TGACNXM-boot` asset `boot.img`

---

## 4. CI

```text
workflow: thyme-stock-kernel-mininit-control
run:      (pending)
commit:   (pending)
artifact: thyme-stock-kernel-mininit-control-<sha>
```

Gates (all required):

```text
STOCK_BOOT_INPUT_HASH
STOCK_KERNEL_EXACT_MATCH
BOOT_HEADER_V3
INITRAMFS_STRUCTURE
REVERSE_UNPACK
PARTITION_SIZE
ONLY_RAMDISK_CHANGED
```

Image diff: `docs/stock-kernel-mininit-image-diff.md` (filled from CI artifact).

---

## 5. Flash target (after READY gate)

```text
CONTROL:
STOCK KERNEL + MINIMAL INITRAMFS

WRITE TARGET:
boot_b ONLY

vendor_boot_b: STOCK / NO WRITE
dtbo_b:        STOCK / NO WRITE
vbmeta_b:      STOCK / NO WRITE
SLOT A:        NO WRITE
```

Do not restore stock `boot_b` after the test unless asked.

---

## 6. Device result

Pending CI READY gate.

```text
STOCK_KERNEL_MININIT_CONTROL_NOT_SAFE
```
