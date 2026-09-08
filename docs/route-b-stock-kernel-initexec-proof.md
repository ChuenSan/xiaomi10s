# Route B stock-kernel init-exec proof — thyme

Stage: `ROUTE_B_INIT_EXEC_PROOF_P15_RETRY`  
Date: 2026-09-08  
Branch: `route-b-v3`

```text
INITRAMFS_UNPACK            CONFIRMED
KERNEL_EXEC_/INIT           CONFIRMED
OLD_INIT_ELF_VALID          NO
OLD_INIT_LOGIC_REACHED      NO
FIXED_INIT_LOGIC_REACHED    CONFIRMED
INIT_EXECUTION_CONFIRMED
```

Do **not** read this as “/init 是否执行仍未知”. Stock 4.19 already printed `Run /init as init process` on the bad ELF; the retry proves the fixed ELF ran its own logic.

---

## 1. Constraint compliance

```text
Local compilation / pack: NO
Slot A flashed:           NO
Only partition written:   boot_b
vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b / firmware: NO WRITE
P30:                      NOT FLASHED
USB gadget / Mainline / DTS: NOT TOUCHED
```

---

## 2. Round 1 — malformed ELF (CI 34215541753 / `1e15ccb`)

```text
P15 SHA:  a615f2b7d89b612594d47cb55a9efba0c3e61718fd75e87c1087870ce4406bf7
e_entry:  0x30   (not inside any PT_LOAD)
PT_LOAD:  PF_R only
```

Kernel on `_b` (oops 1149–1152, Reason: Kernel Panic):

```text
Run /init as init process
Kernel panic - not syncing: Attempted to kill init! exitcode=0x0000000b
PID 1 Comm: init
```

CAUSE = `MALFORMED_INIT_ELF`. Custom sleep/restart2 never ran. `reboot=panic_warm` then burned retry 7→0, `slot-unbootable:b=yes`.

---

## 3. Round 2 — fixed ELF (CI 34217537211 / `101eaa3`)

```text
workflow: thyme-stock-kernel-initexec-proof
run:      34217537211
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34217537211
commit:   101eaa36bff0627030ecd3a7e09a76793fa686d5
artifact: thyme-stock-kernel-initexec-proof-101eaa36bff0627030ecd3a7e09a76793fa686d5
```

```text
STOCK_KERNEL_EXACT_MATCH  PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
INIT_PROOF_STATIC_ARM64   PASS
BOOT_HEADER_V3            PASS
ONLY_RAMDISK_CHANGED      PASS
SIZE_GATE                 PASS  52666368
READY_FOR_INIT_EXEC_PROOF
```

```text
P15 image SHA: 133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34
ELF:           920B  entry=0x4000e0  PT_LOAD vaddr=0x400000 memsz=0x234 flags=5 (RX)
```

P30 image exists in the same artifact (`eee48f10…`) and was **not** flashed.

---

## 4. Device pre-write (Android A)

```text
adb:                 41a5627b device
ro.boot.slot_suffix: _a
sys.boot_completed:  1
root:                uid=0 magisk
```

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @52666368 | `a615f2b7…406bf7` | old bad P15 |
| vendor_boot_b @100663296 | `aac7e11f…041972` | MATCH stock |
| dtbo_b @33554432 | `018fa85c…e64634` | MATCH stock |
| vbmeta_b @8192 flags=2 | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b @4096 | `32174550…8b8355` | MATCH stock |

Dump baseline: oops `7ce3ba16…`, minidump `ac6d95af…` (rawdump/logdump unchanged later).

---

## 5. Flash `boot_b` only

Fastboot preflight: `product=thyme` `unlocked=yes` `current-slot=a` `snapshot=none` `battery-soc-ok=yes`.

```text
BEFORE_BOOT_B_FLASH:  unbootable:b=yes  retry:b=0  current=a
fastboot flash boot_b stock-kernel-initexec-proof-15s.img
Sending 'boot_b' (51432 KB) OKAY
Writing 'boot_b'            OKAY
AFTER_BOOT_B_FLASH:   unbootable:b=no   retry:b=7  current=a
```

**`flash boot_b` itself cleared unbootable and restored retry=7.** `set_active` was not involved.

Reboot to Android A (still current-slot=a). Post-write hash:

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @52666368 | `133e063b…ea87d34` | MATCH fixed P15 |
| vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b | stock flags=2 | still stock |

---

## 6. `set_active b` then one timed reboot

```text
BEFORE_SET_ACTIVE:  unbootable:b=no  retry:b=7  current=a
fastboot set_active b  OKAY
AFTER_SET_ACTIVE:   unbootable:b=no  retry:b=7  current=b
```

`set_active` only switched `current-slot`. Retry was already 7 from the flash.

USB baseline: `18d1:d00d` Fastboot. One `fastboot reboot`. No second B start. No key for 60s.

Host (poll 0.75s, timeout 60s):

```text
fastboot disappear:  +0.915s
fastboot reappear:   +26.708s
adb fallback:        NONE
manual key:          NO
USB after:           18d1:d00d serial 41a5627b
```

```text
AFTER_BOOT:  current=b  unbootable:b=no  retry:b=6
```

One attempt consumed (7→6). No panic_warm retry storm.

Then `fastboot set_active a` + `fastboot reboot` → Android A (`slot_suffix=_a`, `boot_completed=1`).

---

## 7. Dump (oops Index 1156)

minidump / rawdump / logdump hashes **unchanged** (no new crash dump).

oops `7ce3ba16…` → `970be772…`. New record **Index 1156**:

```text
Reason:     Restart          (not Kernel Panic)
t=0:        YES
cmdline:    androidboot.slot_suffix=_b
            stock 4.19.157-perf  (Build #1 SMP PREEMPT Mon Sep 4 10:51:57 UTC 2023)
<6>[    1.576106] Run /init as init process
<0>[   16.576287] reboot: Restarting system with command 'boot
```

kmsg slot truncated at `'boot` (buffer ended). Command is `bootloader`: the P15 ELF string is `bootloader`, and ABL enumerated Fastboot.

Kernel dt: `16.576287 − 1.576106 = 15.000181 s` = designed DELAY=15.

No `Attempted to kill init` in 1156 Kmsg. No `THYME-INITEXEC-PROOF` on `/dev/kmsg` (open of `/dev/kmsg` from the tiny ramdisk likely failed). Not required: restart2 ran.

1150–1152 remain the round-1 panics in the ring. 1153–1155 are Android A `reboot,bootloader` from this session’s `adb reboot bootloader`.

---

## 8. Classification

```text
P15_TIMED_REBOOT              PASS
CUSTOM_INIT_LOGIC_REACHED     CONFIRMED
INIT_EXECUTION_CONFIRMED
```

Host 26.7s = ABL + stock 4.19 bring-up + 15s sleep + restart2("bootloader").

P30 is unnecessary for this gate. Next stage is **not** full NCM+IP+HTTP:

```text
STOCK_KERNEL_USB_ENUM_STAGE0
  USB0  UDC enumeration / descriptors only
  USB1  simplest enumerable function
  USB2  NCM
  USB3  IP
  USB4  HTTP
```

Prove DWC3 gadget bind first. Do not flash xbl/abl/tz. Slot A stays protected. Fixed P15 remains on `boot_b`. B is bootable (`unbootable=no`, retry=6).
