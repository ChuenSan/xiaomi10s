# Slot B first-boot runbook — Xiaomi Mi 10S (thyme

Scope: **documentation only for the upcoming device phase**. THIS phase
writes nothing to the device. Every future write command here is explicit
about the Slot (`_b`) and sits behind a human confirmation gate. The
experiment images are built and validated by the GitHub Actions artifact
pipeline ( `.github/workflows/thyme-mainline-boot-artifacts.yml`*, never
locally*..

Boot-chain design reference: `docs/mainline-boot-chain.md`。 Observation
design reference: `docs/no-uart-debugging.md`. Rollback: `docs/slot-b-rollback.md`.

##1. Read-only preflight (required before ANY write*

```bash
bash scripts/slot-b-preflight.sh
```

The script ( read-only*: verifies product/unlocked/slot-count/has-slot*
set, prints SLOT A PROTECTED, validates the artifact SHA256s, and
refuses to flash anything. Device must be in bootloader(fastboot) Mode.

 Disclaimer: if the device is currently in Android, just leave it
running — no need to enter fastboot for this preparation phase*..

##2. Artifact acquisition

```bash
gh run download <run-id> -n thyme-mainline-firstboot-<gitsha> -D ./artifacts
sha256sum -c ./artifacts/SHA256SUMS
```

Expected files ( see artifact manifest*:

```text
Image                                  linux 6.6 arm64 mainline kernel
sm8250-xiaomi-thyme.dtb              board DTB (the DTB being delivered*
final.config                            merged kernel config
busybox-aarch64-static                BusyBox static binary
initramfs.cpio.gz                     built initramfs ( gzip*
experimental-boot-v2.img            PRIMARY: header v2, DTB field (boot_b only*
experimental-boot-v3.img            FALLBACK: header v3 sported raw image*
experimental-vendor_boot-v3.img     FALLBACK: header v3, DTB + vendor ramdisk*
experimental-dtbo.img                 FALLBACK: dt_table v0, single no-op entry*
unpack-report/                       reverse-parse dumps for every image*
boot-chain-report.md                  this round's decision+evidence*
SHA256SUMS                            artifact hashes
```

##3. Execution gate ( before each and every write*

```text
TARGET SLOT = B
SLOT A WILL NOT BE MODIFIED
fastboot getvar product        ->  thyme
fastboot getvar unlocked       ->  yes
fastboot getvar current-slot    ->  record only
fastboot getvar slot-count      ->  2
fastboot getvar has-slot:boot/vendor_boot/dtbo  ->  yes
```

Only after the human confirms each line may the listed write run.

##4. PRIMARY path ( minimum writes*,  boot_b only*

```bash
fastboot flash boot_b artifacts/experimental-boot-v2.img
fastboot reboot
```

- Expected: ABL loads the v2 boot,, extracts mainline DTB from the field,
  passes it to the mainline kernel ( M0 bootop expects only a boot
  attempt*, then observe the M0..M6 chain ( section 6*..
- If nothing observable happens within ~90s (or device falls back to
  Android/ fastboot*: read the failure mode table ( section 5*..
- Rollback if needed: `fastboot flash boot_b MIUI14ROM/image/boot.img`
  ( docs/slot-b-rollback.md «Scenario 1*..

##5. Failure mode table ( experiment readback primer*

| symptom | probable point | action |
|---|---|---|---|
| fastboot stays alive, no boot attempt | ABL rejected the v2 image ( machine/DTB parse* | record: v2 path rejected; stock untouched; next step = FALLBACK path* |
| instant reboot loop at boot | kernel entry or DTB no machine match | check: machine check / reserved-mem conflict; hint from dmesg unavailable ( no UART*→ rely on USB presence first* |
| USB device never appears ( M2 not reached* | kernel stuck before dwc3 probe ( DTB// debug options* | widen: console via uart2( entitled*; or enable `earlycon`?  no UART anyway*; kernel debug via USB needs USB... which is the deadlock; use dmesg? no UART — so this phase accepts M2==unknown and pivots to FALLBACK structure* |
| USB appears, no usb0 net ( M3 not reached* | gadget/UDC or cdc_ether issue | kernel config check; try NCM mode ( `udc=ncm`*; retry* |
| usb0 up, no ping ( M4 not reached* | addressing or host side | host: `sudo ifconfig enX 172.16.42.2/24 up`; verify link* |
| httpd/telnet down ( M5 not reached* | busybox applet missing | check `/tmp/status.txt` via... needs a net... — circle; assume M2/M3 good,  then M5 usually follows* |
| hard freeze with no USB | kernel panic before USB | fallback: reboot;  retry with `panic=10` in cmdline,  kernel log lost ( no pstore yet* — document and move FALLBACK* |

##6. FALLBACK path ( stock-v3 layout*,  3 partitions*

```bash
fastboot flash boot_b        artifacts/experimental-boot-v3.img
fastboot flash vendor_boot_b artifacts/experimental-vendor_boot-v3.img
fastboot flash dtbo_b       artifacts/experimental-dtbo.img
fastboot reboot
```

Each flash above repeats the execution gate ( section 3*; the order
matches the boot chain ( boot→vendor_boot→dtbo*,   only the needed ones
may be flashed individually if diagnosis narrows it*..

##7. Observation checklist beside the device

| milestone | host-side check |
|---|---|---|
| M0 | device attempted boot ( fastboot left*,  or screen/Android behavior* |
| M2 | `system_profiler SPUSBDataType` (macOS* / `lsusb` (Linux*: VID 0x1d6b |
| M3 | `ifconfig` shows new `usb0`/`enX`  (ECM*;IPv6link-local likely* |
| M4 | `ping 172.16.42.1` |
| M5 | `curl http://172.16.42.1:8080/status.txt` ; `telnet 172.16.42.1` |
| M6 | `curl http://172.16.42.1:8080/dmesg` ( or telnet dmesg* |

`status.txt` exposes boot-state/kernel-release/uptime/gadget/addresses/stage
milestones (`STAGE_1..6`,  `docs/no-uart-debugging.md`*..

##8. Safety rules ( bind from the phase brief*

- Every write command in this runbook already carries `_b`; no bare
  `flash boot`/`vendor_boot`/`dtbo` form is ever used*..
- Re-run `scripts/slot-b-preflight.sh` between every experiment; re-verify
  artifact SHA256s against the release manifest*..
- Do NOT flash/erase/format `*_a`;do NOT `set_active a|b` this rounda
- AVB: not modified now — test whether current unlocked + vbmeta flags 2
  already permits custom B images; revisit only if it blocks*..
- No UART dependency: observability = the M0..M6 chain above*..
- If the device is in Android now,: no need to enter fastboot this phase*.,