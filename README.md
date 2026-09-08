# thyme-mainline

Xiaomi Mi 10S (`thyme`, Qualcomm SM8250/kona, arm64) mainline Linux 6.6 port workspace.

## Layout

| Path | Content | Pinned revision |
|---|---|---|
| `linux-6.6/` | Linux 6.6.y stable (kernel.org) | `8b73de7da85f` (v6.6.156) |
| `android-kernel-sm8250/` | Downstream Android 4.19 kernel reference (LineageOS) | `71b13e62f057` (lineage-23.2) |
| `android-device-thyme/` | Xiaomi thyme device tree/config reference (LineageOS) | `896b8ce204e1` (lineage-23.2) |
| `android-device-sm8250-common/` | Xiaomi SM8250 common device config reference (LineageOS) | `da4ba935256a` (lineage-23.2) |

All four source trees are git submodules pinned by SHA. CI builds `linux-6.6` only.

Restore everything on a new machine:

```sh
git submodule update --init --depth 1
```

## linux-6.6 thyme patch queue

`linux-6.6` tracks kernel.org, so the thyme board work cannot be pushed there.
It lives as a commit series on top of the pinned base:

- Submodule branch `linux-6.6.y` (local): `655067623` (dt-bindings: xiaomi,thyme)
  → `185d1abd3` (arm64: dts: qcom: sm8250-xiaomi-thyme).
- The same series is exported to `patches/linux-6.6/`; CI applies it right after
  the submodule checkout, so fresh checkout → submodule update → patch series →
  build is fully reproducible. Regenerate with `git -C linux-6.6 format-patch
  v6.6.156 -o ../patches/linux-6.6` after new submodule commits.

## CI

`.github/workflows/linux-6.6-ci.yml`

- arm64 `defconfig`, out-of-tree (`O=out`), `LLVM=1` (clang/lld)
- Gates: `Image` + `dtbs` build, presence of `sm8250-mtp.dtb`, `sm8250-xiaomi-elish-boe.dtb`,
  `sm8250-xiaomi-elish-csot.dtb`, `sm8250-xiaomi-thyme.dtb`
- Non-blocking baselines: `dtbs_check` (dtschema 2024.4) log; `W=1` build log on `workflow_dispatch`
- Artifacts: `.config`, `Image`,the four SM8250 DTBs, build/dtbs_check logs

## First-boot artifact pipeline ( Slot B)

`.github/workflows/thyme-mainline-boot-artifacts.yml` runs on `workflow_dispatch` only. It
builds, validates,and uploads the complete Slot B experiment set:the Linux
Image + `sm8250-xiaomi-thyme.dtb`,the bring-up kernel config fragment
`configs/thyme-bringup.config`,the BusyBox 1.36.1 static binary
`configs/busybox-thyme.config`,the minimal initramfs `initramfs/`,and
four experimental images:

| artifact | role | boot-chain reference |
|---|---|---|
| `experimental-boot-v2.img` | PRIMARY: header v2, DTB field | `docs/mainline-boot-chain.md` C1/C3 |
| `experimental-boot-v3.img` | FALLBACK: header v3 | C2 |
| `experimental-vendor_boot-v3.img` | FALLBACK: vendor_boot w/ DTB | C2 |
| `experimental-dtbo.img` | FALLBACK: single no-op entry, board-id `<45 0>` | C2 |

CI validates DTB delivery via unpack + compatible check,the no-op dtbo
equivalence via `fdtoverlay`,image sizes against partition caps,and emits
a SHA256SUMS manifest.Trigger:

```sh
gh workflow run thyme-mainline-boot-artifacts
```

Artifacts:`thyme-mainline-firstboot-<sha>`. Flash procedure	is
documented only in `docs/slot-b-first-boot-runbook.md`;this project performs
no device writes.

## Route B (stock-shaped boot v3)

Isolated branch `route-b-v3`, workflow `.github/workflows/thyme-route-b-v3.yml`.
Does **not** replace the v2 primary path. Builds:

| artifact | role |
|---|---|
| `experimental-boot-v3.img` | kernel + Route B initramfs, header v3 |
| `experimental-vendor_boot-v3.img` | stock-compatible v3 header + mainline DTB |
| `experimental-dtbo.img` | single no-op overlay, `qcom,board-id = <45 0>` |

Docs: `docs/route-b-v3-boot-chain.md`, `docs/route-b-v3-test-plan.md`,
`docs/route-b-v3-final-report.md`. Slot B firmware baseline is unverified;
see `docs/slot-b-firmware-baseline.md`. No device writes; Slot A protected.

## Stock kernel + mininit control (Slot B)

Isolated workflow `.github/workflows/thyme-stock-kernel-mininit-control.yml`
(`workflow_dispatch` only). Does **not** build linux-6.6 or any DTS. Reconstructs
a boot v3 image from official V14.0.6.0.TGACNXM `boot.img` with the stock
kernel payload unchanged and the generic ramdisk replaced by BusyBox mininit.

Gadget class is **NCM** (stock `kona-perf` has `CONFIG_USB_CONFIGFS_NCM=y`,
no ECM). Artifact contains only `stock-kernel-mininit-boot-v3.img` plus
initramfs/busybox/reports — no vendor_boot/dtbo.

```sh
gh workflow run thyme-stock-kernel-mininit-control.yml --ref route-b-v3
```

## Docs

- `docs/stock-rom-analysis.md` — stock ROM parse
- `docs/thyme-hardware-map.md` — hardware mapping
- `docs/mainline-boot-chain.md` — Q1/Q2/Q3 decision + evidence
- `docs/route-b-v3-boot-chain.md` — Route B boot v3 / vendor_boot / DTBO
- `docs/route-b-v3-test-plan.md` — Route B B0/B1 gates
- `docs/route-b-v3-final-report.md` — Route B CI gate report
- `docs/thyme-stock-slot-partition-map.md` — official Fastboot ROM → A/B firmware map
- `docs/slot-b-firmware-baseline.md` — Slot B boot-chain baseline forensics
- `docs/no-uart-debugging.md` — USB-first observation design,pstore DEFERRED
- `docs/slot-b-first-boot-runbook.md` — future flash runbook,B-only
- `docs/slot-b-rollback.md` — stock B restore plan
