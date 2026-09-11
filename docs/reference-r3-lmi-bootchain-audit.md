# Reference R3 — lmi bootchain audit

Stage: `THYME_REFERENCE_R3_LMI_BOOTCHAIN_AUDIT`

Source-only / read-only. No local kernel/boot build, no device operation,
no Slot A write, no Route B change, no thyme DTS/bootshim implementation.

Identity of clones: `docs/reference-r3-lmi-repositories.md`.

```text
mem0 read:                    YES
LOCAL_BUILD:                  NO
DEVICE_OPERATION:             NO
Slot A written:               NO
CURRENT_ROUTE_B_CHANGED:      NO
initramfs cloned:             NO
sunflower full cloned:        NO
```

This round is not a transplant of lmi DTS, 7.1 kernel, camera/audio/display,
or a replacement of Route B.

## 1. Repository identity

See `docs/reference-r3-lmi-repositories.md`.

```text
linux-sm8250-xiaomi-lmi     HEAD 3a8409fb1  master  2026-06-17  2.0G  depth=1
sm8250-xiaomi-lmi-boot      HEAD 31e6156    master  2026-05-25  596K  depth=1
sm8250-xiaomi-lmi-initramfs not cloned (ls-remote master ca90a154)
sunflower2333/linux         not cloned (master 8241a920, 7.2.0-rc5)
```

`refs/` was already gitignored. Unchanged.

## 2. Trust / evidence model

| Level | What counts |
|---|---|
| 1 | Source: assembly, pack scripts, DTS, Kconfig fragments, Makefile, lock files, manifest generator |
| 2 | CI / release manifest field names / binary layout rules encoded in scripts |
| 3 | README / ADAPTATION_NOTES / AI-generated docs |

Conflict rule: source wins.

README claims treated as unverified until matched to Level 1/2:

| Claim | Verdict |
|---|---|
| kernel 7.1.0 | YES. `Makefile` VERSION/PATCHLEVEL/SUBLEVEL. Level 1 |
| ~74 commits ahead of torvalds | YES as GitHub `ahead_by=74` vs **current** `torvalds:master`. Also `behind_by=32603`. Not a superset of current linus. Level 2 API |
| UFS boot Ubuntu 26.04 Server | NOT verified here. Kernel has UFS + built-in initramfs (Level 1). Distro success is Level 3 docs |
| copydown bootshim | YES. Default pack script + `linux-copydown-embedded-dtb.S.in`. Level 1 |
| Stock DTB given to ABL | YES. `--dtb $STOCK_DTB` and gzip kernel `cat` with `$STOCK_KERNEL_DTB`. Level 1 |
| separate embedded runtime DTB | YES. `.incbin "@RUNTIME_DTB@"` and `x0=runtime_dtb`. Level 1 |
| non-EFI | YES at config. `lmi/configs/m1.config`: `# CONFIG_EFI is not set`. Level 1 |

Stale lock: both kernel and boot `kernel.lock` still pin `v6.18.30`. HEAD Makefile is 7.1.0. Source tree wins.

## 3. Kernel baseline

```text
version:          7.1.0
NAME:             Baby Opossum Posse
baseline:         torvalds-era 7.1 + lmi commits; not current torvalds master
commits ahead:    74 vs current torvalds:master (GitHub compare)
commits behind:   32603 vs current torvalds:master
verified:         YES (Makefile + compare API)
lock file:        stale v6.18.30
```

First unique commit subject: `添加 lmi 主线内核启动骨架`.
DT selector commit `cd336f5deebe` (`补充 lmi DTB 启动匹配信息`) added
`qcom,kona-mtp/qcom,kona/qcom,mtp` plus msm-id/board-id. No comment in
the DTS itself explaining ABL vs convenience.

## 4. Complete lmi boot chain

Physical addresses that ABL actually uses are **UNKNOWN**. Header fields
are recorded as FROM_IMAGE_HEADER, not as proven copy destinations
(thyme ABL already showed header load addresses are not copy dests).

```text
Power on
  EXECUTOR=hardware
  NEXT=XBL

XBL
  EXECUTOR=Qualcomm XBL on SM8250
  NEXT=ABL
  ADDRESS/DTB/X0..X3=UNKNOWN

ABL  (Xiaomi LinuxLoader; product-specific binary not in these repos)
  INPUT=Android boot.img header v2 (locks/mkbootimg.args, device-baseline.lock)
  OUTPUT=decompressed kernel payload at UNKNOWN load address;
         ramdisk loaded; header-v2 DTB selected/merged (UNKNOWN merge details)
  DTB SOURCE=boot.img --dtb STOCK_DTB, plus appended STOCK_KERNEL_DTB after gzip
  NEXT PC=decompressed kernel offset 0 = bootshim _start
  X0 at ABL→shim=UNKNOWN (standard would be ABL-facing FDT; shim ignores it)

Android boot.img
  header_version=2
  pagesize=4096
  kernel_offset=0x8000  ramdisk_offset=0x01000000
  tags_offset=0x100     dtb_offset=0x01f00000
  os_version=16.0.0     os_patch_level=2026-04
  kernel field=gzip(shim_bin) || STOCK_KERNEL_DTB
  ramdisk field=initramfs cpio.gz (also built into Image via CONFIG_INITRAMFS_SOURCE)
  dtb field=STOCK_DTB
  second=empty

bootshim  (_start / shim_entry / copy_entry)
  EXECUTOR=linux-copydown-embedded-dtb.S.in  (default TEMPLATE)
  INPUT=ABL x0 (discarded), embedded linux_image at +0x200000, embedded runtime_dtb
  OUTPUT=Linux Image copied over load address; x0 rewritten
  ADDRESS=PC-relative; linked -Ttext=0x0
  NEXT PC=_start after copy = Linux ARM64 Image header

Linux Image / Image.gz
  KERNEL SOURCE=gunzip of Image.gz, then .incbin uncompressed Image inside shim
  Linux is part of boot.img kernel payload, not ramdisk, not a separate partition
  ENTRY=primary_entry at copied Image (standard ARM64 Image at dest)
  X0=embedded runtime DTB
  X1=0 X2=0 X3=0

runtime DTB
  SOURCE=out/.../sm8250-xiaomi-lmi.dtb  (mainline DTS, not ABL x0, not stock)
  ADDRESS=label runtime_dtb, 0x1000-aligned after copy_entry
  no linux,initrd-* in DTS

kernel entry
  EXECUTOR=Linux 7.1 primary_entry
  DTB=x0 embedded mainline
  initramfs=built-in CONFIG_INITRAMFS_SOURCE (Level 1)
  boot.img ramdisk is packed for ABL; Linux is not handed initrd via x0/x1-x3

initramfs
  INPUT=embedded cpio
  OUTPUT=rootfs discovery / menu / switch_root  (contents Level 3; not cloned)
  UFS=CONFIG_SCSI_UFS_QCOM=y + DTS &ufs_mem_hc/phy okay (Level 1 capability)

UFS rootfs
  claimed /dev/sda34 LABEL=ubuntu-rootfs  (Level 3)
  NEXT=userspace

userspace
  claimed Ubuntu 26.04 Server  (Level 3)
```

Diagnostic shims (reset ladders, EL1 ERET, pstore, jump-without-copy) exist
under `bootshim/` and `scripts/mkboot-linux-*-lmi.sh`. They are experiments.
The published success pack path is `scripts/mkboot-linux-copydown-lmi.sh`
with `stage=M2j`.

Optional later template `linux-copydown-embedded-dtb-reset-panel.S.in`
pokes TLMM GPIO46 before the Linux jump (display). Default TEMPLATE does
not. ADAPTATION_NOTES (Level 3) claims the GPIO reset is used; published
default script (Level 1) does not. Source default wins for “what the
script does unless TEMPLATE is overridden”.

## 5. ABL direct entry

```text
ABL_DIRECT_ENTRY_OBJECT=copydown bootshim
                         (composite ARM64 Image at decompressed kernel start)
NOT Linux Image
NOT EFI stub
NOT a PE/COFF MZ image (CONFIG_EFI is not set; shim PE offset field = 0)
```

| Item | Value | Evidence |
|---|---|---|
| source file | `bootshim/linux-copydown-embedded-dtb.S.in` | default TEMPLATE in mkboot-linux-copydown-lmi.sh |
| entry symbol | `_start` then `shim_entry` | `.global _start` / `b shim_entry` |
| binary offset | 0 of decompressed kernel | ARM64 Image header at `_start` |
| load address | UNKNOWN | header kernel_offset 0x8000 is FROM_IMAGE_HEADER only |
| outer header | code0=`b shim_entry`; code1=0; text_offset=0x80000; flags=0xa; magic=`ARM\x64`; PE/res5=0 | same file |
| link | `ld.lld -Ttext=0x0 --entry=_start` | pack script |

Android boot.img kernel field offset 0 on disk is **gzip** of that shim
binary, followed by appended stock kernel DTB. ABL gunzips, then branches
to the Image header.

## 6. Bootshim

Default successful template: `linux-copydown-embedded-dtb.S.in`.

```text
entry symbol:              _start / shim_entry / copy_entry
entry physical address:    UNKNOWN (PC-relative)
ABL x0:                    not saved in the default template
                           (abl-dtb variant does `mov x20, x0`)
Linux source:              label linux_image, .balign 0x200000
Linux destination:         label _start (same address ABL loaded)
copy length:               linux_image_end - linux_image, 8-byte stores,
                           manifest rounds up to 8: (len+7)&~7
copy direction:            forward (ldr [x1],#8 / str [x0],#8)
why "copydown":            source is 2MiB above dest; copy kernel DOWN
                           onto the ABL load address
overlap:                   dest=[load, load+len), src=[load+0x200000, ...)
                           forward copy is the correct memmove direction
                           when dest < src
alignment:                 linux .balign 0x200000; copy 8-byte;
                           copy_entry/runtime_dtb/image_end .balign 0x1000
cache:                     dc cvau over dest range and over runtime DTB,
                           line size from CTR_EL0[DminLine]
barriers:                  dsb ish; ic iallu; dsb ish; isb
MMU:                       no SCTLR write; inherit ABL. dc cvau assumes VA
                           usable or implementation treats it as PA
EL:                        no CurrentEL/ERET in default template; inherit ABL
EL switch:                 NO in default path
runtime DTB:               label runtime_dtb after copy_entry
x0 rewrite:                YES. adrp x0, runtime_dtb
final branch:              br x4  with x4=_start (now Linux Image)
final Linux PC:            load address of decompressed kernel (= _start)
x1 x2 x3:                  zeroed
```

Default-template pseudocode from the assembly (not README):

```text
shim_entry(x0_from_abl):          # x0 ignored
    br copy_entry                 # 0x1000-aligned after linux_image

copy_entry:
    dst = &_start
    src = &linux_image
    end = &linux_image_end
    copy_start = dst
    copy_end = dst + (end - src)
    while src < end:
        *dst++ = *src++           # 8-byte, forward
    line = 4 << CTR_EL0.DminLine
    for p in [copy_start, copy_end): dc cvau, p
    for p in [&runtime_dtb, &runtime_dtb_end): dc cvau, p
    dsb ish
    ic iallu
    dsb ish
    isb
    x0 = &runtime_dtb
    x1 = x2 = x3 = 0
    br &_start                    # Linux Image now lives here
```

Sibling `linux-copydown-abl-dtb.S.in` preserves ABL x0 (`mov x20,x0` /
`mov x0,x20`) and has no embedded runtime DTB. That is **not** the default
M2j pack path.

## 7. Boot payload layout

`BOOT_KERNEL_PAYLOAD_LAYOUT` for the default pack:

On-disk `boot.img` kernel field:

| offset | object | purpose |
|---|---|---|
| 0 | gzip(shim_bin), mtime=0, level=9 | ABL decompresses this |
| len(gzip) | STOCK_KERNEL_DTB (magiskboot `kernel_dtb`) | appended stock DTB for ABL/Android kernel-blob convention |

`shim_bin` after gunzip (linked at VMA 0):

| offset | size/align | object | purpose |
|---|---|---|---|
| 0x00 | 64 B | ARM64 Image header | ABL Image protocol |
| 0x40 | ~few insns | `shim_entry`: adrp/br copy_entry | first executed code |
| 0x200000 | Image size, 8-align | uncompressed Linux Image | copy source |
| after linux | 0x1000 align | `copy_entry` | copier + cache + x0 rewrite |
| after copy | 0x1000 align | runtime DTB `.incbin` | Linux x0 |
| after dtb | 0x1000 align | `image_end` | outer image_size |

```text
Linux kernel in boot.img kernel payload: YES (embedded uncompressed Image)
Linux in ramdisk:                        NO as the runnable Image
Linux external partition:                NO
runtime DTB:                             inside shim_bin, not header --dtb
header --dtb:                            STOCK_DTB (ABL-facing)
ramdisk:                                 initramfs cpio.gz (ABL packaging);
                                         Linux uses CONFIG_INITRAMFS_SOURCE
```

`boot.img` also carries `--ramdisk`. Because the shim zeros x1-x3 and the
runtime DTS has no `linux,initrd-*`, that ramdisk is not the Linux initrd
path unless ABL patches the **embedded** DTB (shim does not copy ABL
chosen). Built-in initramfs is the Level 1 Linux path.

## 8. Address map

`LMI_LOAD_ADDRESS_MAP`

| item | value | class |
|---|---|---|
| ABL load address | UNKNOWN | UNKNOWN |
| header kernel_offset | 0x8000 | FROM_IMAGE_HEADER |
| header dtb_offset | 0x01f00000 | FROM_IMAGE_HEADER |
| header ramdisk_offset | 0x01000000 | FROM_IMAGE_HEADER |
| shim executing address | ABL load, PC-relative | UNKNOWN physical |
| Linux source offset | 0x200000 from _start | HARDCODED |
| Linux destination | _start / ABL load | HARDCODED relative |
| Linux entry | same as destination after copy | HARDCODED relative |
| runtime DTB | after copy_entry, 0x1000 align | CALCULATED |
| copy size | 8-aligned Image length | FROM_IMAGE |
| payload end | image_end 0x1000 align | CALCULATED |
| overlap range | dest [0, len) vs src [0x200000, 0x200000+len) | CALCULATED |
| boot partition size | 134217728 | FROM_MANIFEST / device-baseline.lock |
| text_offset in shim hdr | 0x80000 | HARDCODED |
| flags | 0xa (4K page + anywhere) | HARDCODED |

Do **not** copy these into thyme. lmi DRAM map, UART, GPIO, splash, and
2MiB source gap must be re-proven on thyme.

## 9. Manifest safety gates

Generated in `scripts/mkboot-linux-copydown-lmi.sh` (inline Python).
Field names below are the actual keys.

| field | check | why | failure risk |
|---|---|---|---|
| `linux_source_alignment_ok` | `linux_offset == 0x200000` | `.balign 0x200000` must have landed | adrp/copy source wrong; smash copier or DTB |
| `copy_entry_outside_destination` | `copy_entry_offset >= linux_copy_size` | running copier must not sit inside dest `[0,len)` | copy overwrites itself mid-loop |
| `copy_overlap_safe` | `linux_offset > 0` | dest < src so forward copy is valid memmove | `==0` would be in-place nonsense; negative impossible |
| `x0` | `embedded_runtime_dtb` when template has `@RUNTIME_DTB@` | documents Linux x0 | wrong template silently preserves ABL DTB |
| `boot_size_ok` | `boot_img size < 134217728` | boot partition cap | flash would truncate / fail |
| `payload` | `linux-copydown-shim-embedded-runtime-dtb` | stage M2j identity | mixed with preserve-abl-dtb path |
| `stage` | `M2j` | published success label | older diagnostic stages |

`copy_overlap_safe` does **not** check `len <= 0x200000`. It does not need
to: dest is 2MiB behind src, so forward copy never overwrites unread
source. The 2MiB gap is the safety, not “image smaller than 2MiB”.

Missing-file checks (STOCK_DTB, STOCK_KERNEL_DTB, LINUX_GZIP, RAMDISK,
RUNTIME_DTB) are hard `exit 2` before packing.

## 10. ABL-facing DTB

```text
ABL_FACING_DTB=stock captured DTBs, not mainline
source:
  1. mkbootimg --dtb $STOCK_DTB
     default captures/2026-05-15-175516-m0/boot-inspect/magiskboot/dtb
     = header v2 DTB field
  2. cat gzip(shim) $STOCK_KERNEL_DTB
     default .../magiskboot/kernel_dtb
     = appended kernel DTB
```

`device-baseline.lock`:

```text
boot_header_version=2
dtb_delivery=boot-image-dtb-field
dtbo_entry_count=1
dtb_idx=0 dtbo_idx=0
m2_write_boundary=no-fastboot-flash-no-dtbo-write
```

Whether ABL then merges stock dtbo onto that DTB before x0 is **not** in
these repos. `verify-dtb-delivery.sh` still asks that as an open question.
Linux does not consume that x0 on the default path.

Stock DTB is **not** given to Linux as runtime DT.

## 11. Runtime DTB

```text
LINUX_RUNTIME_DTB=embedded mainline sm8250-xiaomi-lmi.dtb
source: RUNTIME_DTB env; docs point at
        out/m1-release/arch/arm64/boot/dts/qcom/sm8250-xiaomi-lmi.dtb
BOOTSHIM_REPLACES_X0=YES
LMI_DTB_DECOUPLING=YES
R3_LMI_DTB_DECOUPLING_REFERENCE=YES
same DTB as ABL-facing: NO
```

## 12. vendor_boot role

```text
LMI_VENDOR_BOOT_ROLE=NOT_USED_IN_SUCCESS_PACKAGING_OR_FLASH
```

Stock lmi lock is **boot header v2 with DTB in boot.img**, not thyme’s
header v3 + vendor_boot DTB. Pack/flash scripts only write `boot`.
`collect-android-baseline.sh` lists vendor_boot for size inventory only.
`extract-current-images.sh` partitions: boot, recovery, dtbo, vbmeta*.
Whether ABL still opens vendor_boot on this device: INCONCLUSIVE.

## 13. dtbo role

```text
LMI_DTBO_ROLE=STOCK_LEFT_UNMODIFIED; NOT FLASHED BY SUCCESS PATH
```

Lock: `m2_write_boundary=no-fastboot-flash-no-dtbo-write`,
`dtbo_entry_count=1`. Inspect/extract scripts exist; pack scripts do not
emit a dtbo. ABL may still apply that one stock overlay to the
ABL-facing stock DTB. Linux x0 is independent, so dtbo merge cannot be
the Linux runtime tree.

```text
LMI_FLASH_ENVIRONMENT=FASTBOOTD
```

README and wrappers require `fastboot getvar is-userspace` → `yes`.
Thyme Route B is bootloader fastboot + slot B. Do not copy lmi flash
flow onto thyme.

## 14. Non-EFI path

Fragments actually used by `lmi/scripts/build-kernel.sh`:

```text
debug:    m1.config
release:  m1.config + m1-release.config
```

```text
CONFIG_EFI:                 is not set   (m1.config)
CONFIG_EFI_STUB:            not in fragments; disabled as EFI dep
CONFIG_EFI_GENERIC_STUB:    not in fragments
CONFIG_EFI_ZBOOT:           not in fragments
```

`m2e-non-efi.config` is a historical extra (`# CONFIG_EFI` / `EFI_STUB` /
`EFI_GENERIC_STUB` / `EFI_ARMSTUB_DTB_LOADER is not set`). Current m1
already turns EFI off. `m1-release.config` does not re-enable EFI.

```text
LMI_NON_EFI_BOOT_CONFIRMED=YES   (config + shim is a raw ARM64 Image)
```

Alioth successful path is the opposite at config level (`CONFIG_EFI=y`,
`CONFIG_EFI_STUB=y`, `CONFIG_EFI_GENERIC_STUB=y`, zboot off).

```text
EFI_STUB_REQUIRED_FOR_XIAOMI_SM8250=NO
EFI_STUB_AS_THYME_CURRENT_CAUSE=DEPRIORITIZED
```

Do not over-read this as “thyme 4.7s is unrelated to Image header”. It
only proves SM8250 Xiaomi **can** boot mainline without EFI stub.

Reweight:

| experiment | vs lmi | weight on current ~4.7s overlay blocker |
|---|---|---|
| M5B code0 / MZ | lmi code0 is `b shim_entry`, no MZ | deprioritized as required |
| M5C text_offset | lmi shim hdr text_offset=0x80000 | not a unique thyme cause |
| M5D PE offset 0 | lmi PE/res5=0 | matches; not the current DTBO-class blocker |

## 15. lmi root DTS

File: `arch/arm64/boot/dts/qcom/sm8250-xiaomi-lmi.dts`

```text
model:         Xiaomi Redmi K30 Pro / POCO F2 Pro (lmi)
compatible:    xiaomi,lmi, qcom,sm8250, qcom,kona-mtp, qcom,kona, qcom,mtp
qcom,msm-id:   <0x164 0x20001>   = <356 0x20001>   VERIFIED
qcom,board-id: <0x25 0x00>       = <37 0>          VERIFIED
memory:        static three-range:
               0x80000000+0x3bb00000,
               0xc0000000+0xc0000000,
               0x180000000 size 0x100000000
               (overrides sm8250.dtsi placeholder size-0)
reserved-memory:
               SoC dtsi map + lmi overrides:
               xbl_aop, slpi, adsp, spss, cdsp_secure_heap resized
               plus xbl_uefi_log, cont_splash @0x9c000000+0x2300000,
               dfps, ramoops @0xb0000000, disp_rdump
chosen:        stdout-path=serial0:115200n8
               bootargs=... earlycon=msm_geni_serial,0xa90000 console=tty0 ...
               framebuffer0 simple-framebuffer @0x9c000000 1080x2400
serial:        aliases serial0=&uart12 (serial@a90000)
               stock cmdline earlycon also 0xa90000
simple-framebuffer / cont_splash: YES, same 0x9c000000 region;
               &mdss memory-region=<&cont_splash_memory>
```

`compatible` originally `"xiaomi,lmi","qcom,sm8250"` (skeleton).
`cd336f5deebe` added kona-mtp/kona/mtp + msm-id/board-id with subject
“启动匹配信息”. No DTS comment. Classification:

```text
kona-mtp strings:  empirically retained for ABL/stock matching
                   NOT proven as the unique required ABL key
                   NOT a reason to add the same strings to thyme blindly
board-id 37:       lmi-specific. thyme stock overlay is <45 0>. DO NOT COPY
```

simple-framebuffer / cont_splash are **display continuity**, not the
mechanism that decouples ABL DT from Linux DT. Low relevance to the
current DTBO/x0 blocker. GPIO46 reset shim is also display-only and
lmi-specific.

`/memory` and reserved-memory are **static in DTS**, not filled by the
bootshim. sm8250.dtsi still says “bootloader to fill in the size”; lmi
overrides with a real map. Origin of the numbers is not further sourced
here (likely M0 capture / stock). Do not copy addresses onto thyme.

## 16. lmi vs thyme vs alioth vs stock thyme

`ROOT_BOOTSTRAP_DTS_MATRIX`

| field | lmi mainline | thyme current (public DTS / M1 ABL DTB) | alioth ref | Stock thyme DTB0 + overlay |
|---|---|---|---|---|
| model | Xiaomi Redmi K30 Pro / POCO F2 Pro (lmi) | Xiaomi Mi 10S (thyme) | Xiaomi POCO F3 | overlay: Qualcomm Technologies, Inc. xiaomi thyme |
| compatible | xiaomi,lmi + qcom,sm8250 + kona-mtp/kona/mtp | xiaomi,thyme + qcom,sm8250 (M1 ABL DTB same; no-op dtbo has kona-mtp) | xiaomi,alioth + qcom,sm8250 | overlay qcom,kona-mtp/kona/mtp |
| msm-id | <356 0x20001> on **base** | public DTS absent; M1 ABL DTB injects <356 0x20001> | <356 0x20001> on **base** | <356 0x20001> on **base** DTB0 |
| board-id | <37 0> on **base** | public DTS absent; M1 ABL DTB <45 0> on base | <44 0> on **base** | base <0 0>; overlay <45 0> |
| /memory | static 3-range | public DTS none; M1 ABL DTB memory@80000000 size 0 | none | stock map / placeholder |
| reserved-memory | SoC + lmi splash/ramoops/adsp overrides | public: sm8250.dtsi; M1 ABL DTB 18 children | rebuilt stock-like | stock map |
| chosen | stdout + bootargs + simplefb | stdout serial0 | chosen cells/ranges, no stdout | no stdout-path |
| simple-framebuffer | YES @0x9c000000 | no in public DTS | no | cont_splash in reserved-memory |
| serial | uart12 @0xa90000 | uart2 @0x988000 | uart6 @0x998000 | uart2 @0x988000 |

Boot packaging matrix (handoff, not DTS):

| | lmi | thyme-current | alioth | astide |
|---|---|---|---|---|
| SoC | SM8250 | SM8250 | SM8250 | SM8250 |
| ABL | Xiaomi (header v2 device) | Xiaomi thyme LinuxLoader | Xiaomi (packaging not in repo) | n/a (downstream kernel only) |
| boot header | v2 | v3 + vendor_boot v3 | UNKNOWN in repo | n/a |
| kernel payload | gzip(shim+Image+rt-dtb)+stock kdtb | Mainline Image (M5D) | Image only in tree | 4.19 |
| first executed | copydown bootshim | Linux Image (or EFI-ish header on older cells) | UNKNOWN | n/a |
| Image dest | copydown onto ABL load | ABL load | UNKNOWN | n/a |
| ABL-facing DTB | captured stock | vendor_boot DTB + dtbo merge | UNKNOWN | kona base + overlay |
| runtime DTB | embedded mainline | ABL x0 (merged) | UNKNOWN | n/a |
| x0 at Linux | embedded mainline DTB | ABL merged FDT | UNKNOWN | n/a |
| vendor_boot | unused in success path | required v3 DTB | not in repo | not in repo |
| dtbo | stock unmodified, not flashed | the current ~4.7s variable | none in repo | overlay build |
| EFI | disabled | deprioritized | enabled stub | disabled |
| initramfs | built-in + packed ramdisk | BusyBox initramfs in boot | not in repo | Android |

lmi architecture: give ABL a stock-compatible DT **context**, then the
shim sets `x0 = mainline DTB` and copies Linux into place.

## 17. Build reproducibility

```text
LMI_PUBLIC_TREE_DTB_BUILD_WIRING_COMPLETE=NO
```

`arch/arm64/boot/dts/qcom/Makefile` lists elish/pipa, **not**
`sm8250-xiaomi-lmi.dtb`. Thyme’s own patch **does** add
`sm8250-xiaomi-thyme.dtb` to that Makefile.

`lmi/scripts/build-kernel.sh` still runs:

```text
make ... Image.gz qcom/sm8250-xiaomi-lmi.dtb
```

`scripts/Makefile.dtbs` has a `%.dtb: %.dts` pattern, so an explicit
target **might** still build. Not locally verified.

```text
scripts consistent: PARTIAL
  pack script, TEMPLATE, and manifest agree
  qcom/Makefile vs build-kernel.sh do not
  kernel.lock 6.18.30 vs Makefile 7.1.0 do not
```

Reproducibility risk only. No local build this round.

## 18. sunflower provenance

```text
SUNFLOWER_RELATIONSHIP=NO_EVIDENCE of direct source from/to ccc lmi
classification:   RELATED_QCOM_TREE / GENERIC_REFERENCE (torvalds fork)
evidence:         fork of torvalds; 7.2.0-rc5; Xiaomi SM8250 DTS are
                  umi/elish/pipa only; 0 code-search hits for lmi;
                  0 matching branches/tags; 0 ccc commits mention sunflower
current value:    LOW
```

Stop. No shallow clone, no patch-id.

## 19. Relevance to M5M blocker

Already on thyme:

```text
L1     target-path="/"     marker present   4.837s
M5M-A  target-path="/"     marker absent    4.834s
L2     target+__fixups__   marker absent    >12s
```

```text
TARGET_FIXUP_MECHANISM_EFFECT_UNDER_MARKER_ABSENT=STRONGLY_SUPPORTED
standard libfdt merged-tree equality does NOT explain runtime
```

lmi does **not** explain why target-path vs `__fixups__` diverge. It
offers a different architecture: **do not use ABL’s merged DT as Linux
x0**.

The ~4.7s class already means ABL **did jump** and Fastboot returned.
That is exactly the window a bootshim can intercept: after ABL branch,
before Linux `setup_arch` consumes x0.

The >12s class may be ABL stuck in overlay **or** a later hang. A
bootshim cannot run if ABL never branches. Keep M5M-B as overlay-causality
research; do not treat it as obsolete.

```text
Does lmi decouple ABL DT from Linux runtime DT?  YES
CAN_LMI_BOOTSHIM_ARCHITECTURE_BYPASS_THYME_CURRENT_DTB_HANDOFF_BLOCKER=YES
```

YES is **architecture applicability**, not a thyme success prediction.
Must not copy lmi physical addresses, board-id 37, UART12, splash, GPIO46,
or the 0x200000 gap without a thyme-specific layout proof.

Header mismatch: lmi success is **boot v2 + DTB-in-boot**. thyme Route B
is **boot v3 + vendor_boot DTB**. A thyme copydown would still need an
ABL-facing stock-compatible DT **somewhere** ABL will accept (likely
still vendor_boot + a jump-friendly dtbo), plus a shim in `boot_b`.

## 20. Route recommendation

```text
M5M_B_RECOMMENDATION=RUN_IN_PARALLEL_WITH_BOOTSHIM_RESEARCH
Recommended route=ROUTE_3_HYBRID
priority:
  1. MAINLINE_V2_R3_THYME_COPYDOWN_BOOTSHIM_CI_DESIGN   (design only)
  2. M5M-B as already planned, not auto-run this round
```

Why not ROUTE_2-only: overlay factorial still answers a different
question (what ABL does to DTBO). Why not ROUTE_1-only: lmi shows a
direct bypass of the x0/merged-DT problem the 4.7s class is stuck in.

This round did **not** generate a thyme shim, did not pack/flash boot,
did not edit thyme DTS.

Future design (not this round) must study on thyme:

- ABL load address (not header 0x8000)
- M5D boot payload layout
- Linux source/destination/overlap
- runtime DTB placement
- x0 replacement
- primary_entry
- stock-facing DT context (vendor_boot/dtbo, not lmi v2)
- boot partition size
- non-EFI compatibility with current M5D Image

```text
CURRENT_ROUTE_B_CHANGED=NO
DEVICE_OPERATION=NO
```

User-stated Slot B for this round:

```text
exact M5D boot
+ M5H board45 Stock DTB0 vendor
+ M5M-A target-path/no-marker dtbo
```

In-repo last device-doc commit is `f75a917` (M5M-B result). This audit
does not reconcile that by flashing or by declaring M5M-B meaningless.

## Reference value ranking

Current boot blocker:

1. ccc lmi boot + copydown (DTB decoupling, proven non-EFI SM8250 path)
2. thyme own M5* factorial (what ABL overlay actually does)
3. Alioth mainline (selector-on-base DTB; EFI-on success; no pack recipe)
4. Astide downstream (stock overlay protocol; 4.19)

Post-boot bring-up:

1. ccc lmi DTS/drivers (UFS, display, USB, touch, GPU, …) — HIGH after handoff
2. Alioth mainline DTS
3. Astide thyme dtsi/overlay
4. sunflower2333/linux — LOW

```text
POST_BOOT_REFERENCE_VALUE=HIGH   (lmi hardware, frozen this round)
camera/audio/modem/panel/sensor/charging: not audited
```

## Next stage

```text
MAINLINE_V2_R3_THYME_COPYDOWN_BOOTSHIM_CI_DESIGN
```

Design only, GHA-only if any artifact work is later approved. No device
operation in that design stage unless a later prompt says so.

WAIT FOR USER APPROVAL.
