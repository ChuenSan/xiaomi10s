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

## M1 true-device result

The explicit true-device test used private CI Run `34338768052` and only these
writes:

```text
boot_b:         NO
vendor_boot_b:  YES  (once)
dtbo_b:         YES  (once)
vbmeta*:        NO
firmware*:      NO
Slot A:         NO
```

All local artifact hashes matched the private `SHA256SUMS` manifest before use:

```text
M1 vendor_boot SHA256 = 29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
M1 dtbo SHA256        = 316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
Mainline DTB SHA256   = a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
ABL DTB SHA256        = cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0
```

### Device gates and hashes

Android A preflight passed:

```text
ro.boot.slot_suffix = _a
sys.boot_completed  = 1
root                = uid=0
```

The M0 payload was reused byte-for-byte. Hashes are image-sized prefixes where
needed to exclude partition padding:

```text
M0 boot expected:    378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
pre-test boot_b:     378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
post-write boot_b:   378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
post-write vendor:   29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
post-write dtbo:     316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
post-write vbmeta:   37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
post-write vbmeta_system: 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355

M1_BOOT_B_EXACT_M0_REUSE=YES
M1_CONTEXT_POSTWRITE_VERIFIED=YES
```

The B context before the writes was stock:

```text
vendor_boot_b = aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
dtbo_b        = 018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
vbmeta_b      = 37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
vbmeta_system_b = 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
```

The experiment matrix was therefore:

| Payload/context | M0 | M1 |
|---|---|---|
| `boot_b` | exact M0 payload | exact same payload |
| kernel | Linux 6.6.156 | Linux 6.6.156 |
| generic ramdisk | P15 `/init` | P15 `/init` |
| vendor DT | stock | Mainline thyme DTB |
| `dtbo_b` | stock | ABL-compatible no-op |
| `vbmeta*` | stock | stock |

```text
BOOT_B_BYTE_IDENTICAL=YES
```

### Slot metadata

```text
before flash:       current=a, unbootable:b=yes, retry:b=0
after vendor_boot:  current=a, unbootable:b=yes, retry:b=0
after dtbo:         current=a, unbootable:b=yes, retry:b=0
before set_active:  current=a, unbootable:b=yes, retry:b=0
after set_active:   current=b, unbootable:b=no,  retry:b=7
after B boot:       current=b, unbootable:b=no,  retry:b=6
```

`set_active b` cleared the stale M0 retry block without rewriting `boot_b`.

### One-shot B observation

The host observed the ABL Fastboot identity only; no USB gadget test was run.

```text
T_REBOOT_COMMAND          2026-09-09T10:35:50.703Z
T_FASTBOOT_DISAPPEAR      2026-09-09T10:35:50.975Z
T_FASTBOOT_REAPPEAR       2026-09-09T10:35:55.799Z
FASTBOOT_DISAPPEAR_TO_REAPPEAR = 4.821 s
manual intervention       NO
automatic fallback to A   NO
```

The return was far earlier than the P15-compatible delayed return window. It is
classified as an early Fastboot return, not as `/init` execution evidence.

```text
M1_AUTOMATIC_FASTBOOT_RETURN=YES
MAINLINE_V2_M1_EARLY_RETURN
```

### Post-run dump evidence

No Mainline pstore marker was found. The literal `Run /init as init process`
present in the dump belonged to the downstream Android A record and was not
counted as Mainline evidence.

```text
                    baseline                                      post-run
 oops       index 1187  30f91ef22ce1e6c16c4d687dd548ebe3735da40f305fc2a55bc534d7aefc8a98  index 1193  c563e91fedbf4845a08dce1bb44ac3df982f2ce4de1df07325652882a0d9d947
 minidump             e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a             e8caa0f3d96e1329070bd93062d3d728bcb19bc54694df65abe47310fa96d04a
 rawdump              254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917             254bcc3fc4f27172636df4bf32de9f107f620d559b20d760197e452b97453917
 logdump              3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351             3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351
```

```text
MAINLINE_KERNEL_HANDOFF      = UNKNOWN
MAINLINE_INITRAMFS_UNPACK    = UNKNOWN
MAINLINE_INIT_EXECUTION      = NOT_CONFIRMED
DT_CONTEXT_EFFECT            = INCONCLUSIVE
ANDROID_A_RESTORED           = YES
slot_suffix                  = _a
boot_completed               = 1

Final Gate: MAINLINE_V2_M1_EARLY_RETURN
```

No Slot A partition was written, and M1 `vendor_boot_b`/`dtbo_b` were left in
place after recovery; only the active slot was restored to A.
