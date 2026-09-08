# Route B stock-kernel init-exec proof — thyme

Stage: `ROUTE_B_STOCK_KERNEL_INIT_EXEC_PROOF`  
Date: 2026-09-08  
Branch: `route-b-v3`

Single question vs mininit FAIL: **does custom `/init` actually run** on the known-good stock 4.19 kernel?

This round does not touch Mainline, DTS, USB gadget, NCM, IP, or HTTP.

---

## 1. Constraint compliance

```text
Local compilation: NO
Local build: NO
Slot A flashed: NO
Only partition written: boot_b (after CI READY + preflight)
vendor_boot_b / dtbo_b / vbmeta_b / firmware: NO WRITE
```

---

## 2. Why not USB

Mininit produced: retry 7→6, no 12s Android `/metadata` reboot, no USB gadget, no t=0 `_b` oops.

That is compatible with either:

- A: `/init` never executed
- B: `/init` ran and USB/configfs/UDC failed

USB work before distinguishing A/B is blind. This round is a timed `restart2("bootloader")` only.

---

## 3. Stock kernel support (reference tree)

`android-kernel-sm8250` `kona-perf_defconfig` / `arch/arm64/configs/defconfig`:

```text
CONFIG_BLK_DEV_INITRD=y     kona-perf + arch defconfig
CONFIG_RD_GZIP              default y (kona-perf only disables RD_XZ / RD_LZO)
CONFIG_DEVTMPFS=y           arch defconfig
CONFIG_DEVTMPFS_MOUNT=y     arch defconfig
```

Proof `/init` does not require proc/sysfs/devtmpfs. Optional `/dev/kmsg` mark is best-effort.

Stock generic ramdisk `/init` is a symlink to `/system/bin/init`. Vendor ramdisk is only `first_stage_ramdisk/fstab.qcom` — it does not overlay `/init`. Replacing the generic ramdisk with an ELF at `/init` is the kernel's default `ramdisk_execute_command`.

Stock `msm-poweroff.c` maps `cmd == "bootloader"` to `PON_RESTART_REASON_BOOTLOADER` / `0x77665500`.

---

## 4. Proof payload

`initramfs/init-proof.c`, freestanding aarch64, no libc, no BusyBox:

1. optional write ident to `/dev/kmsg`
2. `nanosleep(DELAY_SECONDS)`
3. `sync`
4. `reboot(LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2, LINUX_REBOOT_CMD_RESTART2, "bootloader")`
5. idle if reboot returns

Variants: P15 (`DELAY=15`), P30 (`DELAY=30`). First device boot is **P15 only**.

---

## 5. CI

```text
workflow: thyme-stock-kernel-initexec-proof
run:      TBD
URL:      TBD
commit:   TBD
artifact: thyme-stock-kernel-initexec-proof-<sha>
status:   pending
```

Gates (all required):

```text
STOCK_KERNEL_EXACT_MATCH
INIT_PROOF_STATIC_ARM64
BOOT_HEADER_V3
RAMDISK_CONTAINS_INIT
REVERSE_UNPACK
ONLY_RAMDISK_CHANGED
SIZE_GATE
READY_FOR_INIT_EXEC_PROOF
```

First device flash: `stock-kernel-initexec-proof-15s.img` only.

---

## 6. Device protocol (after READY)

1. Android A, `ro.boot.slot_suffix=_a`, Magisk root.
2. Hash `vendor_boot_b` `dtbo_b` `vbmeta_b` `vbmeta_system_b` — must remain stock. `boot_b` is currently mininit; do not require stock.
3. `adb reboot bootloader` → preflight (`scripts/stock-kernel-initexec-proof-preflight.sh`).
4. `fastboot flash boot_b stock-kernel-initexec-proof-15s.img` — no other writes.
5. `fastboot reboot` back to Android A. Prefix-hash `boot_b` must equal P15 SHA. Re-confirm the four stock B images.
6. Fastboot again. Record `slot-retry-count:b` before `set_active b`, after `set_active b`, then one `fastboot reboot` timed by `scripts/stock-kernel-initexec-proof-host-observe.sh` (poll 0.75s, timeout 180s).
7. Do not treat a black screen as failure. Classify by Fastboot reappearance time.

P30 is a follow-up only after P15 is strongly positive **and** explicit approval.

---

## 7. Classification

| Observation | Gate |
|---|---|
| Fastboot returns ~15s + kernel overhead, no key | `INIT_EXECUTION_STRONGLY_SUSPECTED` (P15). P30 shift → `INIT_EXECUTION_CONFIRMED` |
| Return in 2–5s | `INIT_EXECUTION_TEST_FAILED_PRE_INIT` |
| No Fastboot at 3 min, hardware key | `INIT_EXECUTION_NOT_CONFIRMED` |
| Preflight/hash/slot unsafe | `INIT_EXECUTION_TEST_NOT_SAFE` |

Dump (oops/minidump/rawdump/logdump) is auxiliary. Strongest dump line: `Restarting system with command 'bootloader'` plus `slot_suffix=_b` near 15s. Do not wait on dump to classify.

---

## 8. Timing / USB / dump (device, TBD)

```text
retry before set_active:
retry after set_active:
retry after boot:
fastboot disappear:
fastboot reappear:
manual key required:
new oops:
```

---

## 9. Next gate

- If execution confirmed: `STOCK_KERNEL_USB_BRINGUP` in layers (USB-0 enumerate only). Not a full NCM/HTTP stack.
- If not confirmed: ramdisk format / compression / vendor concatenation / `/init` mode — still not USB, still not Mainline DTS.

---

## 10. Final

```text
INIT_EXECUTION_TEST_NOT_SAFE
```

Pending CI `READY_FOR_INIT_EXEC_PROOF` and the P15 timed boot.
