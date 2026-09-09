# Route B Mainline V2 M1 — private Mainline-DT initexec

Status: public source only. The OEM-derived M1 build and flashable artifacts are
built and retained in a private auxiliary CI repository. No device operation is
part of this phase.

## M0 / M1 isolation

| Payload/context | M0 | M1 |
|---|---|---|
| `boot_b` | exact Mainline 6.6 + P15 `/init` | exact same M0 payload required |
| kernel | Linux 6.6.156, `8b73de7da85fde281a385e0b26eda9bffd3ca477` | unchanged |
| generic ramdisk | known-good 15 s initexec | unchanged |
| `vendor_boot_b` DTB | stock downstream context | Mainline thyme DTB |
| `vendor_boot_b` ramdisk | stock on device | byte-exact stock input |
| `dtbo_b` | stock | ABL-compatible no-op thyme overlay |
| `vbmeta*` | stock | stock |

M1 changes only `MAINLINE_DT_CONTEXT`. `boot_b` is not rebuilt, packaged, or
flashed.

## Public source repository

```text
ChuenSan/xiaomi10s
```

The public workflow

```text
.github/workflows/thyme-mainline-v2-m1-mainlinedt-initexec.yml
```

is source-only. It does not download stock images, run the M1 builder, or upload
flashable artifacts. The public repository contains no tracked
`vendor_boot.img` or `dtbo.img`.

The reusable validator remains public:

```text
scripts/mainline-v2-m1-ci-validate.sh
```

It is CI-only and is invoked by the private builder after checkout at a fixed
public commit.

## Private builder

The private builder owns:

```text
stock context Release
M1 GitHub Actions workflow
OEM-derived private artifacts
```

It checks out `ChuenSan/xiaomi10s` at one full immutable commit, fetches only
`vendor_boot.img` and `dtbo.img` from its own private Release, verifies SHA256
before unpacking or processing, and stores the resulting flashable artifacts
only in private Actions storage.

Expected stock inputs:

```text
vendor_boot.img = aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
dtbo.img        = 018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
```

The M0 `boot_b` reference remains:

```text
378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
```

## Private CI outputs

```text
mainline-v2-m1-vendor_boot.img
mainline-v2-m1-dtbo.img
mainline-thyme.dtb
mainline-thyme-abl.dtb
SHA256SUMS
vendor-boot-diff-report.txt
dtbo-validation-report.txt
validation-report.txt
```

The private gate is:

```text
READY_FOR_MAINLINE_V2_M1_PRIVATE
```

Required checks include exact stock vendor ramdisk reuse, stock-compatible vendor
boot header fields, Mainline DTB validation, packaging-only ABL metadata, no-op
DTBO equivalence, exact M0 boot reference, and no new boot image.

## Device boundary

This phase performs no `adb`, Fastboot, slot change, partition write, or device
boot. A passing private CI run only prepares the audited M1 artifacts. M1 true
device testing remains a separate approval gate.

## Private CI result

```text
PRIVATE_PROVISIONING_USED=YES
PRIVATE_STOCK_CONTEXT_PROVISIONED=YES
PRIVATE_CI_RUN_ID=34338768052
PRIVATE_CI_RESULT=READY_FOR_MAINLINE_V2_M1_PRIVATE
PUBLIC_M1_SOURCE_COMMIT=ff70e7dc807399e68fbebcecab9e6eb23c911d65
```

Outputs:

```text
mainline-thyme.dtb       a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
mainline-thyme-abl.dtb   cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0
vendor_boot              29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
dtbo                     316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
```

The private artifact was independently downloaded and re-hashed. No flashable
artifact was uploaded to the public repository.
