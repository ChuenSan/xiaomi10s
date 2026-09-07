# Thyme (Mi 10S)  Mainline Slot-B First-Boot Artifact Pipeline: Final Report

Project: `thyme-mainline` ( repo: ChuenSan/xiaomi10s, branch `main`
Commit under test: `29bc752517c53a5532bd1974e3bff59cca5af391`
CI run: [34116449773](https://github.com/ChuenSan/xiaomi10s/actions/runs/34116449773)  **conclusion: success** ( all 25 steps green )

## 1. Scope and hard constraints

This round builds and validates, **on GitHub Actions only**, every artifact needed for an experimental first boot of Linux 6.6 mainline on the thyme ( Mi 10S ( via **Slot B only**, with:

- **Zero writes to the device** this round ( nothing flashed;the device is untouched (.
- **No dependency on UART**  observation is planned though USB gadget ( ECM/NCM ( + HTTP status + telnetd, see [no-uart-debugging.md](no-uart-debugging.md(.
- **vbmeta untouched**  no re-signing, no dtbo/vbmeta partition modifications planned..
- **Read-only host-side** Slot-B preflight script, AVB research, Slot-B `set_active` research  see [slot-b-preflight.sh](../scripts/slot-b-preflight.sh(, [mainline-boot-chain.md](mainline-boot-chain.md(, [slot-b-rollback.md](slot-b-rollback.md(.

Boot-chain delivery plan, documented in [mainline-boot-chain.md](mainline-boot-chain.md(:

- PRIMARY: `boot_b`  AOSP boot header **v2**, DTB carried in the **dtb field** ( `--dtb`, `--dtb_offset 0x01f00000` (  matches the stock split-concatenated-DTB delivery ( `dtb_idx=0` picks the mainline single-FDT golden.
- FALLBACK: `vendor_boot_b`  header **v3** + experimental **no-op `dtbo_b`** entry with board-id `<45 0>`;the no-op overlay merges a marker property `qcom,thyme-mainline-noop` at root so boot side effects can be distinguished from no-boot.



## 2. Artifact inventory ( verified locally post-download (

| artifact | bytes | SHA256 ( prefix 16 (
|---|---:|---:|---:|
| `Image` | 35,101,184 | `359ce45988720f2b...` |
| `sm8250-xiaomi-thyme.dtb` | 105,960 | `a91a512d4d8699dc...` |
| `final.config` | 287,158 | `4ae37ddc7831151b...` |
| `busybox-aarch64-static` | 2,171,544 | `5f20c9f6b9d7906...` |
| `initramfs.cpio.gz` | 1,186,235 | `3485b221c76cbbfc...` |
| `experimental-boot-v2.img` | 36,401,152 | `ae32736c59bd21b0...` |
| `experimental-boot-v3.img` | 36,294,656 | `823d399e19a7e302...` |
| `experimental-vendor_boot-v3.img` | 114,688 | `e033332adf3dfbc76...` |
| `experimental-dtbo.img` | 376 | `bd6ecf5b1b8e5b0...` |

Full `SHA256SUMS` verified with `shasum -a 256 -c`  **all OK** ( post-download re-check (..



## 3. Partition size gates ( re-verified post-download (

| image | size | partition cap | result |
|---|---:|---:|---:|
| `experimental-boot-v2.img` | 36,401,152 | 201,326,592 ( `BOOT` ( | OK |
| `experimental-boot-v3.img` | 36,294,656 |201,326,592 ( `BOOT` ( | OK |
| `experimental-vendor_boot-v3.img` | 114,688 |100,663,296 ( `VENDOR_BOOT` ( | OK |
| `experimental-dtbo.img` | 376 |33,554,432 ( `DTBO` ( | OK |



## 4. CI in-pipeline hard gates( all passed on run 34116449773 (

1. Kernel products:`make Image` + `make dtbs`;`fdtget ... /compatible` contains `qcom,sm8250` ( CI-verified (..
2. Initramfs: BusyBox **1.36.1** static aarch64  `CONFIG_STATIC=y` ( enforced post-defconfig via sed (; self-checks: static link, `/init` executable, applet availability across `bin|sbin|usr/(s)bin` ( cat, mount, ifconfig, telnetd, httpd, dmesg, sh (..
3. Boot image assertions:
   - `experimental-boot-v2.img` unpacks w/ **dtb field payload** whose `/compatible` = `qcom,sm8250`;v2 is the PRIMARY chain carrier..
   - `experimental-boot-v3.img` unpacks **without** dtb field (  v3 carries DTB in vendor_boot instead(..
   - `experimental-vendor_boot-v3.img` unpacks w/ dtb payload, compatible OK..
4. DTBO equivalence( fallback chain (: 1 entry, page 4096, payload decompiles to the no-op overlay (`/plugin/`, `qcom,kona-mtp`;`qcom,board-id = <45 0>`; numeric assertion `== [45, 0]`  hex/dec robust ( (, contains the marker `qcom,thyme-mainline-noop`;`fdtoverlay` merge of mainline DTB + no-op dtbo succeeds, merged tree still carries the marker,and the rest of the tree diffs empty versus plain mainline( and the the no-op overlay changes nothing but the marker node..
5. Artifact size gates vs partition caps( table above (..
6. `SHA256SUMS` generated overthe 9 artifacts;`shasum -c` pristine..



## 5. Engineering notes( busybox bring-up path (

- busybox.net TLS endpoint unusable from GitHub runners; pinned GitHub mirror tag `1_36_1` ( highest real tag (..
- kconfig persistence: full `make defconfig`( zero NEW-symbol prompts( + sed flips is the stable routethrough GitHub-actions no-TTY land; text-sed must handlethe kconfig comment-out form `# CONFIG_X is not set` as well as `CONFIG_X=n`.
- `CONFIG_TC` disabled: BusyBox `networking/tc.o` references CBQ uapi constants dropped from modern Ubuntu libc-dev kernels headers..



## 6. Known unknowns for the first-boot attempt( see runbook (

- Stock A/B + slot-switch exact semantics on thyme firmware( UFS-backed virt-A/B(  *read-only* research done, flashed-boot behavior remains unexplored(..
- Console: none; primary liveness signal = USB gadget network endpoint + `http://172.16.42.1:8080/status.txt` etc(`/init` writes progress through STAGE_1..6; pstore deferred(..
- Kernel peripheral bring-up minimal: only USB2( peripheral(, UFS, uart2(UART wiring unverified  do not rely on it(;enough storage plumbing for the initramfs; display/touch/WiFi/BT/audio/battery deferred..



##  7. Next phase actual first boot( outside this round(

Follow [slot-b-first-boot-runbook.md](slot-b-first-boot-runbook.md(, preamble [slot-b-preflight.sh](../scripts/slot-b-preflight.sh(, rollback [slot-b-rollback.md](slot-b-rollback.md(, observation [no-uart-debugging.md](no-uart-debugging.md(..

Minimum flash set( write phase(: `experimental-boot-v2.img`  **`boot_b`** only. Fallback images(**boot_b** retry w/ `experimental-boot-v3.img` + `experimental-vendor_boot-v3.img` + `experimental-dtbo.img`( only if the primary path shows bootloader-side failure modes. `vbmeta` partitions must stay untouched.. 

## Gate

**`READY_FOR_SLOT_B_TEST`**  all artifacts built, all CI hard gates green, SHA256SUMS and partition-size gates re-verified post-download on 2026-09-07. No writes performed;device untouched..