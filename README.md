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

## CI

`.github/workflows/linux-6.6-ci.yml`

- arm64 `defconfig`, out-of-tree (`O=out`), `LLVM=1` (clang/lld)
- Gates: `Image` + `dtbs` build, presence of `sm8250-mtp.dtb`, `sm8250-xiaomi-elish-boe.dtb`, `sm8250-xiaomi-elish-csot.dtb`
- Non-blocking baselines: `dtbs_check` (dtschema 2024.4) log; `W=1` build log on `workflow_dispatch`
- Artifacts: `.config`, `Image`, the three SM8250 DTBs, build/dtbs_check logs
