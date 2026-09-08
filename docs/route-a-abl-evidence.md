# Route A — ABL evidence (thyme LinuxLoader)

Grades: `CONFIRMED_SOURCE` CAF/QcomModulePkg, `CONFIRMED_BINARY` this device's
`MIUI14ROM/image/abl.img`, `CONFIRMED_DEVICE`, `STRONG_INFERENCE`, `UNKNOWN`.

## 1. What the file is

| Item | Result |
|---|---|
| `file abl.img` | ELF 32-bit LSB ARM, statically linked, no section headers |
| SHA256 | `1d14cad5e62d963c88e24aa8dab50b577a0f8d0b39323127b5f1677feb2c5cc2` |
| e_entry | `0x9fa00000` |
| Payload | UEFI FV (`_FVH`) + LZMA at file offset 12408 → 946376 bytes |

LZMA payload build path (CONFIRMED_BINARY):

```
/home/work/mnt/miui_codes1/build_home_rom/bootable/bootloader/edk2/QcomModulePkg/Application/LinuxLoader
.../out/target/product/thyme/obj/ABL_OBJ/.../LinuxLoader.dll
```

`xbl.img` string: `DefaultBDSBootApp = "LinuxLoader"`. CONFIRMED_BINARY.

This is Xiaomi thyme QcomModulePkg ABL, not a random third-party EDK2.

Reference source used for control-flow (same package, same strings):
[SHIFTPHONES android_bootable_bootloader_edk2 sos-3.x QcomModulePkg](https://github.com/SHIFTPHONES/android_bootable_bootloader_edk2/blob/sos-3.x/QcomModulePkg/Library/BootLib/BootLinux.c)
plus `LocateDeviceTree.c`, `FastbootCmds.c`, `LinuxLoader.c`.

Thyme ABL contains the same diagnostic strings as that tree (`DTB Image not present`,
`Single appended DTB found`, `qcom,msm-id entry not found`, `Reason:BootLinux Fail`,
`Fastboot boot command is not available in locked device`, …). CONFIRMED_BINARY.

## 2. Fastboot `boot` command

`FastbootCmds.c` `CmdBoot` (CONFIRMED_SOURCE), strings in thyme ABL (CONFIRMED_BINARY):

1. Reject if locked. Device `unlocked: yes`. CONFIRMED_DEVICE.
2. Register USB download as image 0, name `"boot"`, `NumLoadedImages = 1`.
3. Parse header: version ≤ 2 uses v0–v2 layout; newer uses v3.
4. `LoadImageAndAuth` then `BootLinux`.
5. Host already received **Booting OKAY** and USB was stopped **before** `BootLinux` result.
6. On `BootLinux` return: `ResetBootDevImage`, function returns, **no fail string to the host**. Fastboot stays resident.

This matches the first RAM boot: Sending/Booting OKAY, screen black (logo not redrawn), `fastboot devices` still `41a5627b`.

```
Fastboot Boot code path identified: YES
boot v2 parser identified: YES
```

`Booting OKAY` is not kernel-entry proof.

## 3. v2 vs v3 DTB container

`CheckImageHeader` / `DTBImgCheckAndAppendDT` (CONFIRMED_SOURCE + CONFIRMED_BINARY strings):

| Header | DTB buffer | cmdline |
|---|---|---|
| v2 | boot.img dtb pages (`dtb_size` required; `DTB Image not present: DTB Size = %u`) | boot.img cmdline |
| v3+ | vendor_boot dtb pages (`DTB is a part of vendor_boot image`) | vendor cmdline then boot cmdline |

v2 DTB **field is consumed as a size + file offset**, not as `dtb_addr` physical destination.

`dtb_addr` / `kernel_addr` / `ramdisk_addr` are **not** copy destinations. `UpdateBootParams` builds:

- kernel window from UEFI `KernelBaseAddr`/`KernelSize` or `BaseMemory | PCD`
- ramdisk = kernel_end − rounded(ramdisk[+vendor ramdisk]) − page
- DTB = ramdisk − 2MiB − page

```
DTB field consumption (parser): YES (v2 dtb_size + payload pages exist in the image)
DTB field as successful kernel x0: REFUTED (device matrix 2026-09-08)
dtb_addr as x0: NO
```

## 4. DTB selection (the failure fork)

Always: `DtboImgInvalid = LoadAndValidateDtboImg(...)`.

Thyme ABL strings: `BootLinux: failed to get dtbo image`, `Dtbo hdr magic mismatch`, `Error: Board Dtbo blob not found`, `qcom,board-id`, `qcom,msm-id entry not found`, `ERROR: Couldn't find the suitable DTB!`.

`LocateDeviceTree.c`:

- Walk concatenated FDTs from `DtbOffset`.
- `DeviceTreeAppended` / `GetSocDtb` require `qcom,msm-id` (plus board/pmic ranking).
- `GetBoardDtb` matches DTBO entries with `qcom,board-id` (`VARIANT_MATCH`).
- Fallback on the **appended** branch only: if matching fails, a **single** FDT at `DtbOffset` with no second FDT may be copied (`Single appended DTB found` / `Not the single appended DTB`).
- Overlay branch: `GetSocDtb` missing → error, **no** single-FDT fallback. Then `GetDtboNeeded` / `GetBoardDtb` / `ufdt_apply_overlay`. Overlay needs `__symbols__` (`Couldn't find '%s' symbol in main dtb`).

Mainline DTB: no `qcom,msm-id`, no `qcom,board-id`, no `__symbols__`.

Current slot A has a valid stock `dtbo` (29 entries, thyme entry 21). STRONG_INFERENCE: `LoadAndValidateDtboImg` succeeds → overlay path → `GetSocDtb` fails → `BootLinux` error → return to Fastboot.

```
DTBO_A_USED_DURING_FASTBOOT_BOOT = YES
DOWNSTREAM_OVERLAY_CONTAMINATION_RISK = YES
```

If the overlay path is entered, stock thyme overlay cannot apply to mainline; ABL errors rather than silently using a clean mainline DT. Route A cannot claim a self-contained single image while slot A `dtbo_a` remains in the BootLinux path.

U-Boot Qualcomm docs independently say `fastboot erase dtbo` when booting a v2 mainline-style image. This round forbids erase.

## 5. vendor_boot_a on `fastboot boot` v2

`CmdBoot` does not register vendor_boot. `NumLoadedImages = 1`.

v2 `CheckImageHeader` does not require vendor_boot. ABL still has `Invalid vendor_boot partition. Skipping` and `UpdateBootParamsSizeAndCmdLine: Failed to find vendor_boot image` (v3 cmdline path).

```
VENDOR_BOOT_A_USED = UNKNOWN
```

CAF v2 parser: DTB from boot.img pages (`NumLoadedImages = 1`). CAF v3 `fastboot boot` still loads slot `vendor_boot` + `dtbo`. Device four-way matrix is DTB-invariant, so slot vendor_boot cannot be ruled out as the *actual* DT source on this Xiaomi revision. See `docs/route-a-report.md`.

## 6. cmdline

v2: boot.img cmdline (our packed stock vendor cmdline).

ABL then appends generated tokens (strings present): `androidboot.serialno=`, `androidboot.slot_suffix=`, `androidboot.dtbo_idx=`, `androidboot.dtb_idx=`, `androidboot.bootdevice=`, `androidboot.verifiedbootstate=`, `androidboot.vbmeta.*`, cert `M2102J2SC` (Mi 10S).

```
BOOT_V2_CMDLINE_USED = YES
final cmdline = boot v2 cmdline + ABL androidboot.*
```

vendor_boot cmdline is not the v2 source. `/chosen/bootargs` is written later by `UpdateDeviceTree` from that concatenated string (CONFIRMED_SOURCE). Not observable without kernel liveness.

## 7. Kernel jump / x0

After `ShutdownUefiBootServices` + `PreparePlatformHardware`:

```
((LINUX_KERNEL)KernelLoadAddr)(DeviceTreeLoadAddr, 0, 0, 0);
```

```
X0_SOURCE = NOT OBSERVED
x1=x2=x3 = 0   (only if the jump ran)
kernel entry handoff: CONFIRMED_SOURCE for QcomModulePkg;
                      CONFIRMED_BINARY that this ABL is that package;
                      NOT observed on thyme fastboot-boot v2
```

```
X0_POINTS_TO_V2_DTB = REFUTED
```

Device matrix (CONTROL / NO-DTB / BAD-DTB / QC-IDS): all Booting OKAY, Fastboot USB gone ~1–2 s, Fastboot returns, no gadget. The v2 DTB is not a control variable. See `docs/route-a-report.md`.

Direct x0 probe remains deferred: a payload cannot distinguish CLASS A when the jump likely never happens.

## 8. Flow (v2 RAM boot)

```
fastboot boot experimental-boot-v2.img
  → download buffer (OKAY)
  → CmdBoot: image[0]="boot"  (Booting OKAY, USB stop)
  → LoadImageAndAuth (unlocked; vbmeta flags 2)
  → BootLinux
       CheckImageHeader v2 (dtb_size=0 is not a host-visible reject)
       GZip/Image detect (KERNEL64_HDR_MAGIC)
       UpdateBootParams (ignore header addrs as dest)
       copy kernel to KernelLoadAddr
       LoadAndValidateDtboImg  ← dtbo_a
       DTB select from v2 dtb pages via msm-id / single-FDT / overlay
       UpdateCmdLine + UpdateDeviceTree
       ExitBootServices
       kernel(dtb,0,0,0)
  on any error before jump: return to FastbootCmds, protocol lives, display not restored
```

## 9. APPENDED-DTB variant

Not built. After the four-way matrix, another v2 DTB delivery style would not isolate x0. Stop v2 packing; Route B uses vendor_boot DTB.

## 10. Device matrix vs this source map (2026-09-08)

CONFIRMED_DEVICE:

- `Booting OKAY` on CONTROL, NO-DTB (`dtb_size=0`), BAD-DTB (bad magic), QC-IDS (stock msm-id/board-id).
- USB Fastboot missing 1–2 s, then the same Fastboot protocol. No Linux gadget.

This matches §2 (OKAY before `BootLinux` finishes) and the error-return path in §8. It does **not** match a successful jump with the v2 DTB as `x0`.

QC-IDS not diverging refutes “missing msm-id was the only gate”. Remaining forks need slot `vendor_boot` / `dtbo`, which is Route B.
