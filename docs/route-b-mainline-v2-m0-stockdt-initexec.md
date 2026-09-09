# Route B Mainline V2 M0 — stock-DT initexec

Status: complete; CI passed and the single authorized device run ended without a timed Fastboot return.

This is an isolated handoff experiment. It changes only the kernel payload in `boot_b`:

```text
Mainline Linux 6.6 Image
+ stock vendor_boot_b / downstream DTB
+ stock dtbo_b
+ known-good static 15s /init proof
```

It does not test USB, NCM, IP, HTTP, Mainline DTS peripherals, or a Mainline DTB.
The CI artifact and one-shot Slot B result are recorded below.

## Control baseline

```text
STOCK_KERNEL_CONTROL_PATH_COMPLETE=YES
Stage4 commit=907467c
branch=route-b-v3
pre-M0 tracked_worktree=clean
Slot A=protected
```

The current worktree also contains pre-existing untracked local artifacts and a Stage3B helper;
they are not part of this M0 change and are not staged or removed.

## Mainline source baseline

```text
linux-6.6 base=8b73de7da85fde281a385e0b26eda9bffd3ca477
kernel line=6.6.y (currently v6.6.156)
patch queue=patches/linux-6.6/*.patch
DTS modified by M0=NO
Mainline DTB included in M0 boot image=NO
```

CI applies and verifies the existing patch queue after checking the pinned submodule commit.
The M0 image is built with the existing `configs/thyme-route-b.config` baseline. Only these
handoff options are gates:

```text
CONFIG_ARM64=y
CONFIG_MMU=y
CONFIG_BINFMT_ELF=y
CONFIG_BLK_DEV_INITRD=y
CONFIG_RD_GZIP=y
CONFIG_PRINTK=y
```

USB options may remain enabled by the reused Route B baseline, but are not an M0 gate.

## CI

Workflow:

```text
.github/workflows/thyme-mainline-v2-m0-stockdt-initexec.yml
```

Validation helper:

```text
scripts/mainline-v2-m0-ci-validate.sh
```

The workflow performs all compilation, initramfs generation, image packing, reverse unpack,
ELF checks, source gates, size gates, and SHA256 generation in GitHub Actions only. It uses the
same `initramfs/init-proof.c` and `initramfs/build-init-proof.sh` source/build logic as the
known-good Stock P15 proof. Exact old-binary reuse is not assumed:

```text
INIT_PROOF_EXACT_REUSE=NO
INIT_PROOF_SOURCE_REBUILD=YES
DELAY=15
RESTART2="bootloader"
```

The rebuilt `/init` must be:

```text
static ARM64 ELF
ET_EXEC
no PT_INTERP
no dynamic NEEDED entries
entry inside executable RX PT_LOAD
PID1 failure path = permanent sleep loop
initramfs contents = /init only
```

## Artifact

Expected artifact name:

```text
thyme-mainline-v2-m0-stockdt-initexec-<sha>
```

Its top-level contents are deliberately limited to:

```text
mainline-v2-m0-stockdt-initexec-boot-v3.img
Image
init-proof
initramfs.cpio.gz
SHA256SUMS
validation-report.txt
unpack-report/
```

No `vendor_boot`, `dtbo`, or `vbmeta` artifact is generated.

CI final gate:

```text
READY_FOR_MAINLINE_V2_M0
```

## Boot image structure

```text
header: Android boot v3
kernel: raw Mainline arch/arm64/boot/Image
ramdisk: gzip newc cpio containing only static /init
DTB in boot image: NO
```

The device-side DT context remains the stock Slot B set:

```text
boot_b (pre-write Stage4 reference) = 6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a
vendor_boot_b = aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
DTB source = stock vendor_boot_b downstream DTB
dtbo_b = 018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
vbmeta_b = 37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c (flags=2)
vbmeta_system_b = 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
```

## Device gate — completed

Read-only Android A baseline captured before any M0 write:

```text
adb device=present
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0
boot_b Stage4 reference=6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a
vendor_boot_b stock=YES
dtbo_b stock=YES
vbmeta_b stock flags=2
vbmeta_system_b stock=YES
```

The pre-write Fastboot checks passed. No partition other than the authorized `boot_b` was
written. The required Android A checks were:

```text
ro.boot.slot_suffix=_a
sys.boot_completed=1
uid=0
```

Re-hash `vendor_boot_b`, `dtbo_b`, `vbmeta_b`, and `vbmeta_system_b` against the known stock
hashes. Preserve dump baselines. Fastboot must report `product=thyme`, `unlocked=yes`,
`current-slot=a`, `snapshot-update-status=none`, and `battery-soc-ok=yes`.

The only permitted write is:

```text
fastboot flash boot_b \
  mainline-v2-m0-stockdt-initexec-boot-v3.img
```

Do not write Slot A, `vendor_boot_b`, `dtbo_b`, `vbmeta_*`, or firmware. Do not start B until
the post-write `boot_b` hash exactly matches the CI artifact and the other B payloads still
match stock.

The one-shot observation must start from `current-slot=a`, then:

```text
fastboot set_active b
fastboot reboot
```

Observe for at least 60 seconds. USB absence, missing NCM, missing IP, and missing HTTP are
not failure conditions in M0.

## Device result

```text
CI run: 34322563307
artifact: thyme-mainline-v2-m0-stockdt-initexec-23a2d6c53dbfb7ed2db7e9fd1aa79d3ae6d3bd01
commit: 23a2d6c
Mainline commit: 8b73de7da85fde281a385e0b26eda9bffd3ca477
Mainline kernel version: 6.6.156
Image SHA256: 22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6
boot SHA256: 378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
init-proof SHA256: aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8
initramfs SHA256: b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
config SHA256: 4ae37ddc7831151b35bb937e2fbc8bf101cac54a5c09b0f6cba3a673b8a3da49

vendor_boot_b stock: YES
dtbo_b stock: YES
vbmeta_b stock: YES, flags=2
vbmeta_system_b stock: YES

retry before flash: 6
after flash: 7
before set_active: 7
after set_active: 7
after boot: 0
unbootable after: YES

Fastboot disappear: +0.433s after fastboot reboot finished
Fastboot automatic reappear: NOT_OBSERVED within 90s
elapsed: automatic Fastboot return not measured
manual key required: NO; Android A later returned automatically

Pstore / dump evidence:
oops before: 9bf22d04d5c046ebd51743ef058a544f39bd27b9960abe56310e6d7984a016b0
oops after: 3d459efa5c9a6ef78ae435d48824dd9f54417547e03387830877d5b2d2713feb
minidump after: 4f00e3599293cb23b4dc9ed5bd97a7740f2c39dc573f99c411bbde68598fb8ef
rawdump after: 080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e
logdump after: 080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e
kernel version: no Mainline 6.6 marker available
Run /init: NOT_OBSERVED for M0
restart command: NOT_OBSERVED for M0
panic: NOT_OBSERVED for M0
PSTORE_MAINLINE_EVIDENCE: NOT_AVAILABLE

MAINLINE_KERNEL_HANDOFF: UNKNOWN
MAINLINE_INITRAMFS_UNPACK: UNKNOWN
MAINLINE_INIT_EXECUTION: NOT_CONFIRMED
Android A restored: YES
Final Gate: MAINLINE_V2_M0_NO_TIMED_RETURN
```

Allowed final gates:

```text
MAINLINE_V2_M0_INITEXEC_CONFIRMED
MAINLINE_V2_M0_INITEXEC_STRONGLY_CONFIRMED
MAINLINE_V2_M0_EARLY_RETURN
MAINLINE_V2_M0_NO_TIMED_RETURN
MAINLINE_V2_M0_KERNEL_PANIC
MAINLINE_V2_M0_INCONCLUSIVE
MAINLINE_V2_M0_NOT_SAFE
```

Regardless of the result, stop after M0 and report before changing `vendor_boot_b`, `dtbo_b`,
or any other partition.
