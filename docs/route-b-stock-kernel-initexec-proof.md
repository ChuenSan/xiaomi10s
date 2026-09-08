# Route B stock-kernel init-exec proof — thyme

Stage: `ROUTE_B_STOCK_KERNEL_INIT_EXEC_PROOF`  
Date: 2026-09-08  
Branch: `route-b-v3`  
Head (P15 test): `1e15ccb`

Question vs mininit FAIL: **does custom `/init` actually run** on stock 4.19?

---

## 1. Constraint compliance

```text
Local compilation: NO
Local build: NO
Slot A flashed: NO
Only partition written: boot_b
vendor_boot_b / dtbo_b / vbmeta_b / firmware: NO WRITE
```

---

## 2. CI (first artifact, the one flashed)

```text
workflow: thyme-stock-kernel-initexec-proof
run:      34215541753
URL:      https://github.com/ChuenSan/xiaomi10s/actions/runs/34215541753
commit:   1e15ccbdf30b1c0a4c8b3e80eca911984aee289f
artifact: thyme-stock-kernel-initexec-proof-1e15ccbdf30b1c0a4c8b3e80eca911984aee289f
status:   success
```

```text
STOCK_KERNEL_EXACT_MATCH  PASS  85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a
INIT_PROOF_STATIC_ARM64   PASS  (file(1) only — see ELF hole below)
BOOT_HEADER_V3            PASS
RAMDISK_CONTAINS_INIT     PASS
REVERSE_UNPACK            PASS
ONLY_RAMDISK_CHANGED      PASS
SIZE_GATE                 PASS  52666368
READY_FOR_INIT_EXEC_PROOF
```

```text
P15 image SHA: a615f2b7d89b612594d47cb55a9efba0c3e61718fd75e87c1087870ce4406bf7
P30 image SHA: 14ac643b7a2e7c2d6896b5b3e260034b5d43795acf91fd15f25768e01f6d5ac2
ELF:           536B  "ELF 64-bit LSB executable, ARM aarch64, statically linked, stripped"
ramdisk P15:   312B gzip newc, /init only, no BusyBox
```

CI did **not** assert `e_entry` inside an RX `PT_LOAD`. That hole is the P15 crash.

---

## 3. Device pre-write (Android A)

```text
adb:                 41a5627b device
ro.boot.slot_suffix: _a
root:                Magisk 26.4-kitsune
sys.boot_completed:  1
```

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @53850112 | `d5849d43…b09e0f` | MATCH mininit |
| vendor_boot_b @100663296 | `aac7e11f…041972` | MATCH stock |
| dtbo_b @33554432 | `018fa85c…e64634` | MATCH stock |
| vbmeta_b @8192 flags=2 | `37dfac44…0f9d9c` | MATCH stock |
| vbmeta_system_b @4096 | `32174550…8b8355` | MATCH stock |

---

## 4. Flash

```text
fastboot flash boot_b stock-kernel-initexec-proof-15s.img
Sending 'boot_b' (51432 KB) OKAY
current-slot: a  (unchanged)
slot-retry-count:b: 6 → 7
then fastboot reboot → Android A
NO set_active b yet
```

Post-write Android A:

| Partition | SHA256 | vs expect |
|---|---|---|
| boot_b @52666368 | `a615f2b7…406bf7` | MATCH P15 |
| vendor_boot_b / dtbo_b / vbmeta_b / vbmeta_system_b | stock | still stock |

---

## 5. Timed P15 boot

```text
RETRY_BEFORE_SET_ACTIVE:  7
fastboot set_active b     OKAY
current-slot:             b
RETRY_AFTER_SET_ACTIVE:   7
is-userspace:             no
one fastboot reboot. No second intentional B start.
```

Host (poll fastboot only, 0.75s, timeout 180s):

```text
fastboot disappear:  +0.774s
fastboot reappear:   NONE
manual Fastboot key: not used
```

After the 180s window the phone was **Android A** (`slot_suffix=_a`, `bootreason=bootloader`), not Fastboot. Host was not watching `adb devices`, so A fallback time is unknown inside the 180s.

Post-boot Fastboot:

```text
current-slot:         a
slot-retry-count:b:   0
slot-unbootable:b:    yes
slot-successful:b:    no
slot-successful:a:    yes
```

Four panic_warm B attempts exhausted retry. Slot B is unbootable until the next `set_active b`. Slot A is the running system. P15 image is still on `boot_b`.

---

## 6. Dump

Before B boot: oops `fa53e3c4…`, minidump `42031494…` (unchanged since mininit).

After:

```text
oops      022db46f2274d25a96455a00cff3dcd9e9cab4b58966b6aa044f3b035c764ba9  CHANGED
minidump  4f00e3599293cb23b4dc9ed5bd97a7740f2c39dc573f99c411bbde68598fb8ef  CHANGED
rawdump   080acf35…19643e  same
logdump   080acf35…19643e  same
misc      ccfeffb0…770953  same, still bootonce-bootloader
```

New oops **1149–1152**. All four:

```text
Reason:     Kernel Panic
t=0:        YES
cmdline:    androidboot.slot_suffix=_b
            stock 4.19.157-perf-g9d90dd04aa7c
<6>[ ~1.42–1.59] Run /init as init process
<0>[ +0.0001s ] Kernel panic - not syncing: Attempted to kill init! exitcode=0x0000000b
             CPU: 7 PID: 1 Comm: init
no thyme-initexec / DELAY=15 / Restarting system with command 'bootloader'
```

RTC 1974-07-15 13:43:47 / 13:44:26 / 13:45:05 / 13:45:43 (~40s apart) = four automatic B retries after `reboot=panic_warm`.

No ident on `/dev/kmsg`: PID 1 died before `kmsg_mark()`.

---

## 7. ELF hole (P15 binary)

`init-proof-15s` from run 34215541753:

```text
e_type=ET_EXEC  e_machine=EM_AARCH64
e_entry=0x30          not inside any PT_LOAD
PT_LOAD[0] vaddr=0x400000 filesz=0xf8 flags=PF_R   (no PF_X)
```

`ld -static -e _start` without a linker script produced a non-executable load segment and an entry in the ELF header. Kernel `execve("/init")` then jumps to 0x30 → SIGSEGV (11 = 0xb) → `Attempted to kill init`.

That is why mininit had no t=0 `_b` oops (BusyBox ELF was a real RX binary) while this proof dumped four t=0 `_b` panics.

Fix (next CI, not yet flashed): `initramfs/init-proof.ld` (`ENTRY(_start)` at 0x400000) plus `verify-init-proof-elf.py` requiring `e_entry` inside RX `PT_LOAD`.

---

## 8. Classification

Timed 15s Fastboot return: **NO**.

Kernel unpacked the generic ramdisk and executed `/init`: **YES** (four t=0 `_b` `Run /init` lines).

`/init` reached `restart2("bootloader")`: **NO** (SIGSEGV in ~100µs).

```text
INIT_EXECUTION_NOT_CONFIRMED
```

Dump answer to the original unknown: custom `/init` **was** PID 1, then died. Next work is a loadable ELF, not USB, not Mainline DTS, not ramdisk format.

Do not flash P30. Do not restore stock `boot_b` unless asked. Next P15 needs `set_active b` because B is currently unbootable.

---

## 9. Final

```text
INIT_EXECUTION_NOT_CONFIRMED
```
