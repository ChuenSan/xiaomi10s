# Route B final report — thyme Mainline Linux 6.6 boot v3

Branch: `route-b-v3`  
Head: `4f957bfd27dacb51deb99868304c9d7aa078acfa`  
CI: [34145495966](https://github.com/ChuenSan/xiaomi10s/actions/runs/34145495966) **success**

No device writes. Slot A untouched.

---

## 1. Constraint compliance

```text
Local compilation performed: NO
Local build performed: NO
Local build validation performed: NO
Slot A modified: NO
Unauthorized Slot B writes: NO
UART dependency: NO
```

---

## 2. Current device state

Device not attached this session (`fastboot devices` empty, `adb` empty).

Last read-only snapshot (2026-09-06, STALE):

```text
product                 thyme
unlocked                yes
current-slot            a
slot-count              2
serial                  41a5627b
slot-successful:b       not re-read this session
slot-unbootable:b       not re-read this session
retry-count:b           not re-read this session
snapshot status         not re-read this session
```

Re-run `bash scripts/route-b-preflight.sh` before any future write.

---

## 3. Stock Boot v3 chain

```text
ABL
 → boot v3            kernel + generic ramdisk, empty cmdline, NO DTB     CONFIRMED_STOCK
 → vendor_boot v3     page 4096, addrs 0x8000 / 0x01000000 / 0x100 / 0x1f00000
                      vendor ramdisk gzip fstab.qcom only
                      DTB = 4 concatenated kona FDTs, dtb_idx=0 = v2.1    CONFIRMED_STOCK
 → dtbo               29 entries, id/rev/custom=0
                      dtbo_idx=21 board-id <45 0>                         CONFIRMED_STOCK
 → x0 = merged FDT                                                        CONFIRMED_CAF_ABL
```

AOSP: bootloader must read both `boot` and `vendor_boot`; generic ramdisk is concatenated immediately after vendor ramdisk. CONFIRMED_AOSP.

---

## 4. fastboot boot v3 behavior

```text
vendor_boot source: vendor_boot_<active-slot> from flash    CONFIRMED_CAF_ABL
dtbo source:        dtbo_<active-slot> from flash           CONFIRMED_CAF_ABL
DTB source:         vendor_boot DTB (stock kona if slot A)  CONFIRMED
```

CAF `CmdBoot` registers the downloaded image as `boot` only (`NumLoadedImages=1`), then `LoadImageAndAuth` still loads `vendor_boot` and `dtbo` from the current slot. Xiaomi ABL is a proprietary CAF fork: INFERRED same path.

```text
fastboot boot experimental-boot-v3.img
THIS TEST DOES NOT VALIDATE MAINLINE DTB
```

---

## 5. Candidate comparison

| Candidate | DTB source | vendor_boot | dtbo | RAM only | Suitable |
|---|---|---|---|---|---|
| B-RAM-1 | stock kona (flash) | active slot | active slot | yes | NO — control only |
| B-RAM-2 | kernel-appended | still flash | still applied | yes | NO — NOT_PROVEN |
| B-SLOT | vendor_boot_b mainline | experimental | no-op dtbo_b | no | YES |

---

## 6. Recommended Route B architecture

```text
boot_b:
    header v3, Mainline Image, BusyBox initramfs gzip, cmdline empty

vendor_boot_b:
    header v3, page 4096, stock addrs, stock vendor cmdline, empty board name
    DTB = sm8250-xiaomi-thyme.dtb
    vendor ramdisk = minimal gzip stub (marker file only)

dtbo_b:
    dt_table v0, 1 entry, overlay board-id <45 0>,
    compatible qcom,kona-mtp / qcom,kona / qcom,mtp
    marker qcom,thyme-route-b-noop
```

---

## 7. Vendor ramdisk decision

**minimal stub** (gzip newc cpio, 150 B).

Stock vendor ramdisk is only `first_stage_ramdisk/fstab.qcom`. Mixing Android first-stage fstab into a mainline initramfs is unnecessary. ABL requires vendor ramdisk size ≠ 0; stub satisfies that. Generic ramdisk overlays it. Same gzip format as boot ramdisk. CONFIRMED_AOSP concat order.

---

## 8. DTBO result

```text
entry count           1
id/rev/custom         0 (matches stock table style)
overlay board-id      <45 0>  (numeric CI assertion)
marker                qcom,thyme-route-b-noop
offline overlay       fdtoverlay merge == mainline + marker; tree diff empty
selection evidence    stock selects by overlay board-id, not table id
                      CAF GetBoardDtb matches board-id
                      thyme hardware pick: UNKNOWN until Slot B
```

---

## 9. USB/no-UART design

```text
VID/PID          0x1d6b / 0x0104   Linux Foundation Multifunction Composite Gadget
manufacturer     thyme-mainline
product          Linux 6.6 Route B
serial           THYME-MAINLINE-B
ECM/NCM          ECM primary, NCM via udc=ncm
device IP        10.66.73.1/24
host IP          10.66.73.2/24
status endpoint  http://10.66.73.1:8080/status.txt
verify           USB identity + new enX + curl --interface enX
```

Host VPN (`utun4`) swallows unicast IPv4. `ping` via default route is not identity.

---

## 10. GitHub Actions

```text
workflow: thyme-route-b-v3
run ID:   34145495966
run URL:  https://github.com/ChuenSan/xiaomi10s/actions/runs/34145495966
status:   success (all gating steps green)
duration: 16:56:30Z → 18:07:32Z  (~1h 11m)
head:     4f957bfd27dacb51deb99868304c9d7aa078acfa
```

---

## 11. Artifact table

Post-download `shasum -a 256 -c SHA256SUMS`: all OK.

| Artifact | Size | SHA256 |
|---|---:|---|
| experimental-boot-v3.img | 36294656 | `582f5b0c28424dbb6dd31a5ba3bf41bb15349ab785f26f2c266c5cc1af576484` |
| experimental-vendor_boot-v3.img | 114688 | `62497ee8dd044c1f6483a4410a41152ae015319a4d4a4965b2e9e6e6b9c4b06d` |
| experimental-dtbo.img | 387 | `316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1` |
| Image | 35101184 | `d1b01c8e17632ccb321f36cf2389c6072382bd1003ad129f423f5fd5bb62eb6c` |
| sm8250-xiaomi-thyme.dtb | 105960 | `a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40` |
| initramfs.cpio.gz | 1186242 | `134a1a69d4198757aac2a580ed1a1f0198bbbbdbf5165e6163763950c39745af` |
| busybox-aarch64-static | 2171544 | `5f20c9f6b9d790613a373230349636619121e5d276259b6a8e55b1378b10ee1d` |

---

## 12. Reverse validation

```text
boot v3 header / no DTB / kernel SHA256 / ramdisk SHA256     PASS
vendor_boot v3 / page 4096 / addrs / cmdline / DTB SHA256    PASS
dtbo 1 entry / board-id <45 0> / fdtoverlay no-op            PASS
initramfs static (httpd bind, ROUTE=B, serial)               PASS
```

---

## 13. Size gates

```text
boot_b         PASS  36294656 <= 201326592
vendor_boot_b  PASS  114688   <= 100663296
dtbo_b         PASS  387      <= 33554432
```

---

## 14. AVB conclusion

```text
AVB modification required: UNKNOWN
```

Unlocked + stock vbmeta flags=2. Do not touch `vbmeta_*` unless Slot B is rejected.

---

## 15. Virtual A/B conclusion

```text
system_b required for initramfs Linux: NO
```

INFERRED: initramfs-only, no Android first-stage mount. Confirm on device.

---

## 16. Files modified

```text
.github/workflows/thyme-route-b-v3.yml
README.md
configs/thyme-route-b.config
docs/route-b-v3-boot-chain.md
docs/route-b-v3-test-plan.md
docs/route-b-v3-final-report.md
initramfs/route-b-init
scripts/route-b-ci-validate.sh
scripts/route-b-host-observe.sh
scripts/route-b-preflight.sh
```

DTS / kernel patches / Route A workflow: not modified.

---

## 17. Git commits

```text
Route B branch     route-b-v3
root commit SHA    4f957bfd27dacb51deb99868304c9d7aa078acfa
Linux patch SHA    unchanged (patches/linux-6.6 on linux-6.6.156 8b73de7da)
```

---

## 18. Remaining blockers

None for **artifact** readiness.

Still true before a write:

- Phone not connected this session — preflight must be re-run.
- Q6 (ABL actually selects the no-op entry) is UNKNOWN until Slot B boots.
- `fastboot boot experimental-boot-v3.img` does not prove mainline DTB.

---

## 19. Final Gate

```text
ROUTE_B_READY_FOR_SLOT_B
```

---

## Draft Slot B commands — DO NOT RUN until user approval

```text
TARGET SLOT: B
SLOT A: PROTECTED

boot_b         experimental-boot-v3.img         36294656  582f5b0c28424dbb6dd31a5ba3bf41bb15349ab785f26f2c266c5cc1af576484
vendor_boot_b  experimental-vendor_boot-v3.img  114688    62497ee8dd044c1f6483a4410a41152ae015319a4d4a4965b2e9e6e6b9c4b06d
dtbo_b         experimental-dtbo.img            387       316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
```

```bash
bash scripts/route-b-preflight.sh artifacts/local/route-b-v3
fastboot flash boot_b        artifacts/local/route-b-v3/experimental-boot-v3.img
fastboot flash vendor_boot_b artifacts/local/route-b-v3/experimental-vendor_boot-v3.img
fastboot flash dtbo_b        artifacts/local/route-b-v3/experimental-dtbo.img
```

Rollback:

```bash
fastboot flash boot_b        MIUI14ROM/image/boot.img
fastboot flash vendor_boot_b MIUI14ROM/image/vendor_boot.img
fastboot flash dtbo_b        MIUI14ROM/image/dtbo.img
```

Host observe: `bash scripts/route-b-host-observe.sh`

Stopped here. No flash.
