# Route B — Android Boot v3 chain (thyme / SM8250)

Route B studies whether Xiaomi thyme can boot Mainline Linux 6.6 with a
stock-shaped Android 13 boot chain:

```text
boot v3 + vendor_boot v3 + mainline DTB + no-op DTBO
```

Evidence markers: `CONFIRMED_STOCK` `CONFIRMED_ANDROID` `CONFIRMED_AOSP`
`CONFIRMED_CAF_ABL` `CONFIRMED_COMMUNITY` `INFERRED` `UNKNOWN`.

This document does not authorize device writes.

---

## 1. Answers first

```text
Q1  fastboot boot <boot-v3.img> loads vendor_boot_<active-slot>
    YES   CONFIRMED_CAF_ABL  (Xiaomi ABL is a proprietary CAF fork: INFERRED same path)

Q2  it also loads dtbo_<active-slot>
    YES   CONFIRMED_CAF_ABL + CONFIRMED_COMMUNITY  (thyme has dtbo; RB3 log skips only when absent)

Q3  most reliable mainline DTB delivery for Route B
    vendor_boot DTB field   CONFIRMED_STOCK / CONFIRMED_AOSP / CONFIRMED_CAF_ABL
    kernel-appended DTB     NOT_PROVEN for thyme (fallback only; stock Image has none)

Q4  real Route B first boot needs
    boot_b + vendor_boot_b + dtbo_b

Q5  stock DTBO pollutes mainline DT if left in place
    YES it is selected (board-id), apply result UNKNOWN / forbidden to test

Q6  no-op DTBO selected?
    metadata matches stock entry 21 (board-id <45 0>) — CONFIRMED_STOCK selection rule
    ABL actually picking it on thyme hardware: UNKNOWN until Slot B test

Q7  missing *_b mapper blocks initramfs-only Linux?
    NO expected  (initramfs does not mount system/vendor) — INFERRED, verify on device

Q8  system_b / vendor_b required for Route B initramfs Linux?
    NO expected — INFERRED, verify on device

Q9  AVB modification required this phase?
    UNKNOWN  (unlocked + stock vbmeta flags=2; do not change vbmeta until a real reject)

Q10 READY_FOR_SLOT_B?
    only after GitHub Actions PASS on this branch (see final report)
```

---

## 2. Stock chain (CONFIRMED_STOCK)

MIUI V14.0.6.0.TGACNXM, re-hashed this round:

| Image | Size | SHA256 |
|---|---:|---|
| boot.img | 134217728 | `9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be` |
| vendor_boot.img | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| dtbo.img | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |
| vbmeta.img | 8192 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` |

```text
ABL
 ↓
boot v3          kernel 52654096 B + generic ramdisk 19729764 B gzip, cmdline empty, NO DTB
 ↓
vendor_boot v3   page 4096, header 2112
                 kernel_addr=0x8000 ramdisk_addr=0x01000000 tags_addr=0x100 dtb_addr=0x1f00000
                 vendor ramdisk 2238 B gzip (fstab.qcom only)
                 DTB 1613832 B = 4 concatenated FDTs; runtime dtb_idx=0 = kona v2.1
 ↓
dtbo             dt_table v0, 29 entries, page 4096, id/rev/custom all 0
                 runtime dtbo_idx=21, overlay qcom,board-id = <45 0>
 ↓
merged FDT in x0 (arm64: LinuxKernel(dt, 0, 0, 0) in CAF ABL)
```

LineageOS thyme: `TARGET_IS_VAB := true` → `BOARD_BOOT_HEADER_VERSION := 3`,
`BOARD_INCLUDE_DTB_IN_BOOTIMG := true`, `BOARD_KERNEL_SEPARATED_DTBO := true`,
`BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 100663296`,
`BOARD_BOOTIMAGE_PARTITION_SIZE := 201326592` (VAB),
`BOARD_DTBOIMG_PARTITION_SIZE := 33554432`. CONFIRMED_ANDROID.

AOSP: v3 boot.img has no DTB; "the bootloader must access both the boot and
vendor boot partitions"; generic ramdisk is concatenated immediately after
the vendor ramdisk (same compression). CONFIRMED_AOSP.

---

## 3. RAM `fastboot boot` v3

Fastboot client only downloads `boot.img` and sends `boot`. CONFIRMED_AOSP.

CAF ABL `CmdBoot` (QcomModulePkg FastbootCmds.c):

```text
Images[0] = downloaded payload, Name = "boot"
NumLoadedImages = 1
LoadImageAndAuth(&Info)
BootLinux(&Info)
```

`LoadImageAndAuth` does **not** reload `boot` when `NumLoadedImages==1`.
For header v3+ it still loads `"vendor_boot"` from the current slot, then
tries `"dtbo"` the same way. CONFIRMED_CAF_ABL.

`BootLinux` for v3+:

```text
GetImage("boot")          → kernel + generic ramdisk
GetImage("vendor_boot")   → page size, addrs, vendor ramdisk, cmdline, DTB
vendor ramdisk first, generic ramdisk immediately after
LoadAndValidateDtboImg()  → ufdt overlay
x0 = merged FDT
```

CONFIRMED_CAF_ABL. Xiaomi thyme ABL is not published; same generation as
SM8250 CAF ABL → INFERRED identical for these steps.

Linaro RB3 `fastboot boot` log: ABL still looks up dtbo ("No dtbo partition
is found, Skip dtbo") and then appended DTB. CONFIRMED_COMMUNITY that
dtbo is consulted on the RAM-boot path.

```text
fastboot boot experimental-boot-v3.img
        +
vendor_boot source: vendor_boot_<active-slot> from flash     CONFIRMED_CAF_ABL
        +
dtbo source:        dtbo_<active-slot> from flash            CONFIRMED_CAF_ABL
        +
DTB source:         vendor_boot DTB (stock kona concat)      CONFIRMED
```

If current-slot is A (last known), this is **stock kona DTB + stock thyme overlay**.
It does **not** deliver `sm8250-xiaomi-thyme.dtb`.

```text
THIS TEST DOES NOT VALIDATE MAINLINE DTB
```

---

## 4. Candidate comparison

| Candidate | DTB source | vendor_boot | dtbo | RAM only | Suitable as final Route B |
|---|---|---|---|---|---|
| B-RAM-1 | stock vendor_boot DTB (kona) | flash active slot | flash active slot | yes | NO — control only |
| B-RAM-2 | kernel-appended DTB | flash active slot still loaded | flash dtbo still applied | yes | NO — NOT_PROVEN; dtbo path wins when dtbo exists |
| B-SLOT | vendor_boot_b mainline DTB | experimental vendor_boot_b | experimental no-op dtbo_b | no | YES — recommended |

Appended-DTB: CAF `DeviceTreeAppended()` is a **fallback** when the DTBO path
is not taken. Thyme **has** dtbo, so the overlay path is taken. Stock kernel
payload is a raw arm64 `Image` with no appended FDT. ARM64 Linux does not
scan a trailer itself; x0 must be filled by ABL. Marker: `NOT_PROVEN`.

---

## 5. Recommended Route B architecture (B-SLOT)

```text
boot_b:
    Android boot header v3
    Mainline Linux Image
    BusyBox initramfs (gzip cpio)
    cmdline empty (stock)

vendor_boot_b:
    Android vendor_boot header v3
    page_size=4096
    kernel_addr=0x8000 ramdisk_addr=0x01000000 tags_addr=0x100 dtb_addr=0x1f00000
    product name empty (stock)
    vendor cmdline = stock vendor cmdline (verbatim)
    DTB = sm8250-xiaomi-thyme.dtb  (single FDT, not kona concat)
    vendor ramdisk = minimal gzip cpio stub (see §6)

dtbo_b:
    dt_table v0, page 4096, one no-op overlay
    overlay root: compatible qcom,kona-mtp / qcom,kona / qcom,mtp
                  qcom,board-id = <45 0>
    fragment target-path="/" marker qcom,thyme-route-b-noop
```

x0 is the mainline FDT after a no-op overlay (marker property only).

---

## 6. Vendor ramdisk decision

Stock vendor ramdisk (CONFIRMED_STOCK, re-parsed):

```text
first_stage_ramdisk/
first_stage_ramdisk/fstab.qcom   (8712 B)
```

AOSP concatenation: vendor first, generic overlays; both must be gzip.
CAF ABL copies vendor ramdisk then generic ramdisk. CONFIRMED_AOSP + CONFIRMED_CAF_ABL.

| Option | What | Verdict |
|---|---|---|
| stock vendor ramdisk + mainline DTB | closest to stock | rejected: Android `fstab.qcom` in a mainline initramfs is unnecessary risk |
| empty/minimal gzip cpio + mainline DTB | clean; size ≠ 0 (ABL requires vendor ramdisk) | **chosen** |

Chosen: **minimal gzip newc cpio** containing only
`thyme-route-b-vendor-ramdisk` (marker file). Generic `/init` overlays it.

---

## 7. DTBO selection

Stock dt_table id/rev/custom are all 0. Runtime `ro.boot.dtbo_idx=21` matches
the overlay whose root `qcom,board-id` is `<45 0>`. CONFIRMED_STOCK.

CAF ABL `GetBoardDtb()` matches board-id, then `ApplyOverlay()`.
CONFIRMED_CAF_ABL.

Route B no-op entry copies that board-id and the stock overlay compatible
list so ABL can select it. Hardware confirmation = Slot B test (UNKNOWN until then).

Offline: `fdtoverlay(mainline DTB, no-op)` must equal the mainline tree aside
from the marker property. CI-gated.

Forbidden: mainline DTB + stock dtbo entry 21.

---

## 8. USB / no-UART

```text
VID/PID        0x1d6b / 0x0104     Linux Foundation Multifunction Composite Gadget
                                   (linux-usb.org; kernel gadget-configfs examples)
Manufacturer   thyme-mainline
Product        Linux 6.6 Route B
Serial         THYME-MAINLINE-B
Function       ECM primary, NCM fallback (cmdline udc=ncm)
Device IP      10.66.73.1/24
Host IP        10.66.73.2/24
Status         http://10.66.73.1:8080/status.txt
Verify         USB enumeration identity + new enX + curl --interface enX
```

Host default route is a full-tunnel VPN (`utun4` swallows unicast IPv4 except
LAN `192.168.0.0/24`). `ping 10.66.73.1` via the default route is **not**
evidence. Interface-bound curl is.

---

## 9. Virtual A/B / AVB / system_b

Initramfs-only Linux needs ABL + kernel + DTB + initramfs. It does not mount
`system`/`vendor`/`product`. Missing `*_b` dm-user mapper is an Android
userspace concern, not a Linux initramfs blocker. INFERRED until device test.

AVB: BL unlocked, stock vbmeta flags=2 (verification disabled). Do not touch
`vbmeta_*` unless Slot B is explicitly rejected. UNKNOWN until that test.

Ramoops: no stock region. `RAMOOPS = DEFERRED`. Display/modem: DEFERRED.
UART: may stay in DTS; never a pass/fail signal.
