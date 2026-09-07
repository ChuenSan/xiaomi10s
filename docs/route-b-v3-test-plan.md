# Route B test plan — Xiaomi Mi 10S (thyme)

Stage B0 this round: research + GitHub Actions artifacts. No partition writes.
Stage B1: Slot B flash only after `ROUTE_B_READY_FOR_SLOT_B` **and** explicit user approval.

Slot A is PROTECTED. Every write command uses an explicit `_b` suffix.

---

## Stage B0 (this round)

1. Stock v3 chain re-verified (images, BoardConfig, AOSP, CAF ABL).
2. CI builds and reverse-validates:
   - `experimental-boot-v3.img`
   - `experimental-vendor_boot-v3.img`
   - `experimental-dtbo.img`
3. No local compilation.
4. RAM-only tests are documented below; they are **not** executed until the
   operator records which `vendor_boot`/`dtbo` ABL will pair with the RAM image.

### B0 RAM control (allowed later, not this round)

```bash
fastboot boot MIUI14ROM/image/boot.img
```

If this reaches MIUI: thyme ABL accepts `fastboot boot` of a v3 boot.img.
It still uses flash `vendor_boot_<slot>` + `dtbo_<slot>`.

### B0 RAM experimental (allowed later, not this round)

```bash
fastboot boot experimental-boot-v3.img
```

Record before running:

```text
active-slot:            (getvar)
vendor_boot source:     vendor_boot_<active-slot> from flash
dtbo source:            dtbo_<active-slot> from flash
DTB source:             stock kona concat, NOT mainline
THIS TEST DOES NOT VALIDATE MAINLINE DTB
```

---

## Stage B1 gate

All of these must be PASS in CI:

```text
boot v3 unpack + kernel/ramdisk SHA256 match
vendor_boot v3 header fields + DTB SHA256 == sm8250-xiaomi-thyme.dtb
no-op DTBO fdtoverlay == mainline + marker
dtbo metadata board-id <45 0>
size gates vs partition caps
checkpatch ERROR=0 on thyme DTS/bindings
dtbs_check: no thyme-only notes vs elish
SHA256SUMS present
Slot A never named in any flash command
```

Then stop and wait for user approval. Do not flash.

---

## Future Slot B commands (draft, `_b` only)

Preflight:

```bash
bash scripts/route-b-preflight.sh artifacts/
fastboot getvar product          # thyme
fastboot getvar unlocked         # yes
fastboot getvar current-slot     # record
fastboot getvar slot-count       # 2
fastboot getvar has-slot:boot
fastboot getvar has-slot:vendor_boot
fastboot getvar has-slot:dtbo
fastboot getvar slot-successful:b
fastboot getvar slot-unbootable:b
fastboot getvar slot-retry-count:b
fastboot getvar snapshot-update-status
```

Human-visible:

```text
TARGET SLOT: B
SLOT A: PROTECTED
```

Writes (only after approval):

```bash
fastboot flash boot_b        experimental-boot-v3.img
fastboot flash vendor_boot_b experimental-vendor_boot-v3.img
fastboot flash dtbo_b        experimental-dtbo.img
```

Forbidden: `fastboot flash boot|vendor_boot|dtbo` without `_b`;
any `*_a`; `vbmeta_*`; `super`; `metadata`; `persist`; `modem`; `fsg`; `modemst`.

Rollback (stock images in `MIUI14ROM/image/`):

```bash
fastboot flash boot_b        MIUI14ROM/image/boot.img
fastboot flash vendor_boot_b MIUI14ROM/image/vendor_boot.img
fastboot flash dtbo_b        MIUI14ROM/image/dtbo.img
```

Full rescue ROM is **not** in this tree.

---

## No-UART milestones

| Id | Meaning | Host check |
|---|---|---|
| M0 | ABL accepted Slot B chain | boot attempt / not stuck exclusively in fastboot protocol |
| M1 | USB leaves Fastboot identity `18d1:d00d` | `system_profiler SPUSBDataType` / `ioreg` |
| M2 | gadget enumerates | VID `1d6b` PID `0104`, Manufacturer `thyme-mainline`, Product `Linux 6.6 Route B`, Serial `THYME-MAINLINE-B` |
| M3 | new macOS `enX` | interface appears after M2 |
| M4 | interface-specific net | `ifconfig enX 10.66.73.2/24 up` then `curl --interface enX http://10.66.73.1:8080/status.txt` |
| M5 | Route B HTTP status | body contains `ROUTE=B` and STAGE lines; valid HTTP response |
| M6 | live dmesg | `curl --interface enX http://10.66.73.1:8080/dmesg.log` |

`fastboot devices` still showing `41a5627b fastboot` means Linux did **not** take USB.
Screen blank ≠ failure. Fastboot UI gone ≠ Linux.

Host helper: `scripts/route-b-host-observe.sh`.
