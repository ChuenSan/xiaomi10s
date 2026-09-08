# Route B AVB single-variable control — thyme

Stage: `ROUTE_B_AVB_SINGLE_VARIABLE_CONTROL`  
Date: 2026-09-08  
Head: `9af1127` (`route-b-v3`)

Single variable: restore `vbmeta_b` from current flags=3 to official V14.0.6.0.TGACNXM `vbmeta.img` (flags=2).  
Do not rebuild Linux/DTS/images. Do not write `boot_b` / `vendor_boot_b` / `dtbo_b` / `vbmeta_system_b` / any `*_a`.

Missing required reads (not guessed):

- `docs/route-a-report.md` — absent
- `docs/route-a-abl-evidence.md` — absent

`bootctl` is absent on this MIUI userspace. Slot identity from `ro.boot.slot_suffix` and Fastboot `getvar`.

---

## 1. Constraint compliance

```text
Local compilation: NO
Local build: NO
Slot A flashed: NO
Slot A modified: NO
Only B partition written: vbmeta_b
```

---

## 2. Android A preflight

```text
adb:                 41a5627b device  product:thyme
ro.boot.slot_suffix: _a
fingerprint:         Xiaomi/thyme/thyme:13/TKQ1.220829.002/V14.0.6.0.TGACNXM:user/release-keys
root:                uid=0 magisk 26.4-kitsune:MAGISK:R
verifiedbootstate:   orange
bootctl:             not present
/metadata/ota/snapshots: empty (no pending snapshot files)
```

---

## 3. Current vbmeta_b analysis

On-device prefix hash (8192 B) and binary-safe `adb pull` of `/data/local/tmp` (not `adb exec-out`; that CRLF-corrupts vbmeta).

```text
vbmeta_b prefix SHA256:  9c632a6074b67539a6597f4b777a149e863f5aa8b14289772ce157e984b2c5c0
flags @0x78:             3
algorithm:               SHA256_RSA2048
rollback index:          0
release:                 avbtool 1.2.0
public key sha1:         b2a02f1e56e366d727a1a8e089762fe0b91bbc84
descriptors:             identical to stock (chain vbmeta_system + hash boot/dtbo/vendor_boot + hashtree mi_ext/odm/vendor)
```

Byte compare vs official `MIUI14ROM/image/vbmeta.img`: **1 byte**.

```text
offset 0x7b  stock=0x02  current=0x03
header except flags: identical
authentication + auxiliary blocks: identical
```

---

## 4. Stock vbmeta analysis

```text
path:     MIUI14ROM/image/vbmeta.img
          copied to work/route-b-avb-control/stock-vbmeta-V14.0.6.0.TGACNXM.img
size:     8192
SHA256:   37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
flags:    2
algorithm SHA256_RSA2048
rollback  0
public key sha1 b2a02f1e56e366d727a1a8e089762fe0b91bbc84
vbmeta_a prefix: MATCH this file
vbmeta_system.img / vbmeta_system_b: 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355 flags=0 MATCH
```

In-tree `work/tools/avbtool.py` (AOSP avbtool 1.3.0, `external/avb 2e2f2f75`):

| flags value in header | header+aux SHA256 vs stored digest |
|---|---|
| 0 | MATCH `b6f507baf2b14fa719b07a59629fdd8dce864130dfec34eafcdd753a8f821d2d` |
| 2 (factory ROM / vbmeta_a) | MISMATCH |
| 3 (current vbmeta_b) | MISMATCH |

So the ROM image was signed at **flags=0**, then the flags field was patched to 2 without re-hash/re-sign. Current B is the same blob patched to 3. `vbmeta_system_*` flags=0 verifies (`verify_vbmeta_signature=True`). Host `verify_image` on stock vbmeta therefore fails at the digest step; that is the flags patch, not an OpenSSL bug.

AOSP `avb_slot_verify` (external/avb): signature/hash of vbmeta is checked **before** flags. On mismatch, unlocked path may continue with `ALLOW_VERIFICATION_ERROR`. Bit 1 (`VERIFICATION_DISABLED`) then skips descriptor parse. Bit 0 (`HASHTREE_DISABLED`) only changes dm-verity cmdline. Slot A already boots Magisk with this factory flags=2 image, so unlocked ABL on this unit accepts that patched blob for slot A. Whether flags=3 is fatal is the experiment, not a prior conclusion.

---

## 5. Exact differences

| Field | Stock vbmeta / vbmeta_a | Current vbmeta_b | Difference | Potential boot impact |
|---|---|---|---|---|
| SHA256 (8192 B) | `37dfac44…0f9d9c` | `9c632a60…b2c5c0` | yes | identity |
| flags | 2 = VERIFICATION_DISABLED | 3 = HASHTREE_DISABLED\|VERIFICATION_DISABLED | bit 0 extra | AOSP: both skip hash descriptors (bit 1). Extra bit is hashtree/cmdline. Xiaomi ABL policy: UNKNOWN |
| header hash vs stored digest | mismatch (signed as flags=0) | mismatch (same stored digest) | computed digest differs | if ABL requires digest match, **both** fail the same way; if ABL keys off flags after unlock, flags=3 is the remaining delta |
| algorithm | SHA256_RSA2048 | same | no | |
| rollback index | 0 | 0 | no | |
| public key | sha1 `b2a02f1e…bbc84` | same | no | |
| descriptors | boot/dtbo/vendor_boot hashes + vendor/odm/mi_ext hashtrees + chain vbmeta_system | same bytes | no | unsigned experimental payload is not a new AVB descriptor change |
| signature / auth block | unchanged from flags=0 signing | identical to stock | no extra rewrite | header-only flags patch |

Distinct getvars (not interchangeable): `unlocked=yes` (AVB allow-error path), `secure=yes` (Qualcomm PBL/XBL), `Verity mode=true` (userspace dm-verity presentation).

---

## 6. Stock vbmeta SHA256

```text
37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
```

Live payload prefixes still Route B v3 (unchanged this round):

```text
boot_b        36294656  582f5b0c28424dbb6dd31a5ba3bf41bb15349ab785f26f2c266c5cc1af576484
vendor_boot_b 114688    62497ee8dd044c1f6483a4410a41152ae015319a4d4a4965b2e9e6e6b9c4b06d
dtbo_b        387       316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
```

Firmware A==B==stock: unchanged from `docs/slot-b-firmware-baseline.md` (this round did not re-flash firmware).

---

## 7. Fastboot preflight

Before write (current-slot must be `a`):

```text
product:                   thyme
unlocked:                  yes
current-slot:              a
snapshot-update-status:    none
slot-unbootable:b:         no
slot-successful:b:         no
slot-retry-count:b:        6
battery-soc-ok:            yes
is-userspace:              no
Device unlocked:           true
Device critical unlocked:  true
Verity mode:               true
```

Human-visible:

```text
TARGET WRITE: vbmeta_b ONLY
SLOT A WRITE: FORBIDDEN
boot_b: NO WRITE
vendor_boot_b: NO WRITE
dtbo_b: NO WRITE
vbmeta_system_b: NO WRITE
```

Second preflight before Slot B test: same values. `PRE_TEST_RETRY_B=6`.

---

## 8. Flash result

```text
fastboot flash vbmeta_b work/route-b-avb-control/stock-vbmeta-V14.0.6.0.TGACNXM.img
Sending 'vbmeta_b' (8 KB)   OKAY
Writing 'vbmeta_b'          OKAY
post-flash current-slot:    a
then: fastboot reboot → Android A
```

VBMETA_B_STOCK_RESTORE: PASS

---

## 9. Post-write root hash verification

Android A `sys.boot_completed=1` `ro.boot.slot_suffix=_a`, Magisk root:

```text
vbmeta_b 8192     37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c  MATCH stock
vbmeta_b flags    2
vbmeta_a 8192     37dfac44…0f9d9c  unchanged
vbmeta_system_b   32174550…8b8355  MATCH stock
boot_b            582f5b0c…576484  experimental-boot-v3 unchanged
vendor_boot_b     62497ee8…c4b06d  experimental-vendor_boot-v3 unchanged
dtbo_b            316c12d9…15d9c1  experimental-dtbo unchanged
```

POST_WRITE_HASH_MATCH: YES

---

## 10. Route B retry before/after

One `fastboot set_active b` (current-slot confirmed `b`) then `fastboot reboot`. No second B reboot.

```text
PRE_TEST_RETRY_B (before set_active): 6
POST_TEST_RETRY_B:                    6
current-slot after return:            b
slot-successful:b:                    no
slot-unbootable:b:                    no
is-userspace:                         no
```

Retry was not sampled between `set_active b` and reboot. AOSP `setActiveBootSlot` often resets retry to 7; a 7→6 attempt would net to 6. Do not treat net 6→6 as “B was not tried”.

USB left Fastboot for ~4–6 s, then ABL Fastboot returned. `BOOTLOADER_ATTEMPTED_B: YES`.

---

## 11. USB behavior

Baseline Fastboot: `18d1:d00d` Manufacturer Google Product Android.

```text
t+0s   reboot B
t+2s   no fastboot, no Android USB
t+6s   41a5627b fastboot + IOUSB Android@02112000
t+24s  still 18d1:d00d Google Android; no 1d6b:0104
```

No `thyme-mainline` / `Linux 6.6 Route B` / `THYME-MAINLINE-B`. No new `enX`, no `10.66.73.0/24`. Host still has `utun4` VPN; default-route ping is not evidence.

MAINLINE_USB_ENUM: NO

---

## 12. Kernel handoff classification

```text
KERNEL_HANDOFF: UNKNOWN
CURRENT_CLASSIFICATION: PRE_KERNEL_SUSPECTED
LINUX_KERNEL_CRASH_CONFIRMED: no
```

No mainline gadget, no userspace evidence. Fastboot UI/protocol return is not a kernel panic proof.

---

## 13. AVB conclusion

```text
VBMETA_B_STOCK_RESTORE:           PASS
POST_WRITE_HASH_MATCH:            YES
BOOTLOADER_ATTEMPTED_B:           YES
RETRY_BEFORE:                     6
RETRY_AFTER:                      6
MAINLINE_USB_ENUM:                NO
KERNEL_HANDOFF:                   UNKNOWN
AVB_FLAGS3_WAS_SOLE_BLOCKER:      NO
CURRENT_STOCK_VBMETA_B_CONTROL:   FAILED
```

Stock vbmeta_b (flags=2, hash-verified) + Route B boot/vendor_boot/dtbo still returned to Fastboot with no mainline USB. flags=3 is not the unique cause of the current Route B failure.

AOSP: flags=2 and flags=3 both have `VERIFICATION_DISABLED`; both skip hash descriptors. The live delta was one flags bit (and therefore a different invalid header digest). Unlocked Slot A already boots Magisk against the same factory flags=2 blob, so “unsigned payload vs hash descriptors” was never a sufficient explanation.

Historical `STOCK_BOOT_CORE_ON_B` also used stock vbmeta and Fastboot’d. That fact is consistent with this result. It does **not** by itself prove the Mainline images are the defect.

---

## 14. Device recovered to Android A

```text
fastboot set_active a  → current-slot a
fastboot reboot
adb: device, sys.boot_completed=1, ro.boot.slot_suffix=_a, magisk root
vbmeta_b still stock flags=2 (left as written; not reverted)
NO *_a flash
```

Device recovered to Android A: YES

---

## 15. Remaining blocker

```text
PRE_KERNEL_SUSPECTED
```

Not this round: Linux/DTS rebuild, firmware_b flash, `vbmeta_system_b`, payload rewrite, Virtual A/B mapper.

Next research (do not start here):

- ABL Slot-B policy
- boot/vendor_boot authentication/loading
- DTBO selection
- kernel handoff instrumentation
- boot-control metadata (retry reset vs decrement)
- historical stock-B failure

---

## 16. Final gate

```text
ROUTE_B_AVB_FLAGS3_NOT_SOLE_BLOCKER
```
