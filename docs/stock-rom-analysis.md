# Stock ROM analysis — Xiaomi Mi 10S (thyme)

Source: MIUI V14.0.6.0.TGACNXM (Android 13) fastboot ROM, unpacked at `MIUI14ROM/image/`
(git-ignored). All analysis is read-only. Parse artifacts live in `work/stock-rom/`
(also git-ignored); committed outputs are limited to this doc and `scripts/split-concatenated-dtb.py`.

## 1. Inventory

Key images present: `boot.img`, `vendor_boot.img`, `dtbo.img`, `vbmeta.img`,
`vbmeta_system.img`, plus `abl/aop/bluetooth/cmnlib/cmnlib64/cust/devcfg/dsp/featenabler/
hyp/imagefv/keymaster/modem/qupfw/super/tz/uefisecapp/xbl_config/xbl.img` and `root.bat`.
No `flash_all.*` scripts shipped with this package. **ROM materials sufficient: YES.**

## 2. Image hashes

| File | Size (bytes) | SHA256 |
|---|---|---|
| boot.img | 134217728 | `9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be` |
| vendor_boot.img | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| dtbo.img | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |
| vbmeta.img | 8192 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` |
| vbmeta_system.img | 4096 | `3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355` |

## 3. Tools

| Tool | Version / revision | Source |
|---|---|---|
| dtc/fdtdump/fdtget/fdtoverlay | DTC 1.8.1 | Homebrew device-tree-compiler |
| unpack_bootimg.py, mkbootimg.py | AOSP mkbootimg `c45163bf1cdb731e3bdd90d69d54c8e92004d673` | android.googlesource.com platform/system/tools/mkbootimg |
| avbtool.py (avbtool 1.3.0) | AOSP `2e2f2f75063678175bce7566d3ac344c0485343d` | platform/external/avb |
| mkdtboimg.py | AOSP libufdt `4f5784f8f46b38bd0e0249c3b1d0ce4b4faf36a8` | platform/system/libufdt utils/src |
| split-concatenated-dtb.py | project script | `scripts/` |

## 4. boot.img

- Header version **3** (boot v3: no cmdline, no page size, no load tags, no DTB here)
- kernel 52,654,096 bytes (arm64 Image), ramdisk 19,729,764 bytes (gzip cpio)
- OS version 13.0.0, SPL 2023-09
- cmdline: empty (lives in vendor_boot)
- AVB footer v1.0: original image 72,392,704 B, embedded vbmeta @ 72,392,704 (Algorithm NONE,
  carries hash descriptor mirroring vbmeta.img)

## 5. vendor_boot.img

- Header version **3**, page size 0x1000, header size 2112
- kernel addr 0x8000, ramdisk addr 0x01000000, tags 0x100, **DTB addr 0x1f00000**
- vendor ramdisk: 2,238 bytes (gzip, 9,216 B unpacked)
- vendor cmdline:
  `console=ttyMSM0,115200n8 androidboot.hardware=qcom androidboot.console=ttyMSM0 androidboot.memcg=1 lpm_levels.sleep_disabled=1 video=vfb:640x400,bpp=32,memsize=3072000 msm_rtb.filter=0x237 service_locator.enable=1 androidboot.usbcontroller=a600000.dwc3 swiotlb=2048 loop.max_part=7 cgroup.memory=nokmem,nosocket reboot=panic_warm buildvariant=user`
- DTB section: 1,613,832 bytes = **4 concatenated FDTs** (split by
  `scripts/split-concatenated-dtb.py`, all dtc-verified):

| Index | Size (B) | Content | SHA256 |
|---|---|---|---|
| 0 | 540,195 | kona **v2.1** SoC (`qcom,msm-id <0x164 0x20001>`, board-id <0 0>) | `324049d746aaa16ada3b425ea5eed30f6d49a90c9d63d5e57ea5a632c27becb8` |
| 1 | 540,191 | kona v2 SoC (`<0x164 0x20000>`) | `0bd93f077080a6e3bedff5cf384ff97fc863667c59e3379cbbe5bbc165c4168e` |
| 2 | 533,273 | kona v1 SoC (`<0x164 0x10000>`) | `afc3540645e5a11351532ce2b5384f27acfb412ee0780ff5a57d72301d5ddb52` |
| 3 | 173 | empty stub FDT | `dbf5e0605a0c053d08260f19bce216935327ab3df7bdf951bf5d736653fb5651` |

Runtime `ro.boot.dtb_idx=0` selects the kona v2.1 base DTB.

## 6. dtbo.img

- dt_table v0: 29 entries, page size 4096, all entries id/rev/custom = 0
- Selection is by the bootloader matching the overlay root `qcom,board-id` against runtime
  board detection. **Entry 21**: 484,885 B, model `Qualcomm Technologies, Inc. xiaomi thyme`,
  compatible `qcom,kona-mtp qcom,kona qcom,mtp`, **board-id `<45 0>`** — exactly matches
  runtime `ro.boot.dtbo_idx=21` and downstream `thyme-sm8250-overlay.dts`.
- Full table dump: `work/stock-rom/dtbo-dump.txt`, per-entry DTBs: `work/stock-rom/dtbo-entries/`
  (family pack: alioth, munch, cmi, elish, psyche, cas, urd, verthandi, umi, skuld, enuma, lmi,
  thyme, apollo, dagu, pipa, poussin, kona reference boards).

## 7. Runtime DT reconstruction

`fdtoverlay` (base = vendor_boot dtb index 0, overlay = dtbo entry 21) **succeeded without
modification**: `work/stock-rom/thyme-stock-merged.dtb` (967,256 B) →
`thyme-stock-merged.dts` (41,667 lines). fdtoverlay applies only the overlay's fragment
children; the merged root keeps the base SoC identity (base `<0 0>`), because the bootloader
selects the overlay via its root board-id — this is expected QC/AOSP behaviour, not a merge
failure.

## 8. AVB (read-only)

- `vbmeta.img`: SHA256_RSA2048, Rollback Index 0, **Flags 2 = VBMETA_FLAGS_VERIFICATION_DISABLED**
  (Xiaomi ships the fastboot-ROM vbmeta this way), release `avbtool 1.2.0`. Chain descriptor →
  `vbmeta_system` (rollback index location 2). Hash descriptors: boot, dtbo, vendor_boot.
  Hashtree descriptors: mi_ext, odm, vendor.
- `vbmeta_system.img`: SHA256_RSA2048, Rollback Index 1693526400 (= 2023-09-01), hashtrees for
  system, product, system_ext.
- boot/vendor_boot/dtbo carry AVB footers with embedded NONE-algorithm vbmeta headers whose hash
  descriptors match vbmeta.img.
- Implication for future experiments: with BL unlocked and a factory vbmeta already carrying
  flag 2, a locally rebuilt boot/vendor_boot/dtbo will not be verified — but no AVB modification
  is performed or planned this phase.

## 9. Hardware facts extracted from the merged stock DT

Markers: `CONFIRMED_STOCK` (stock merged DT), `CONFIRMED_DOWNSTREAM` (vendor kernel source),
`INFERRED`.

### Identity / boot
- Root: `qcom,msm-id <0x164 0x20001>` (SM8250 v2.1); overlay carries board-id `<45 0>`.
- aliases: `serial0 = /soc/qcom,qup_uart@988000` → mainline `uart2` @ 0x988000
  (geni-debug-uart) is the stock console UART (`console=ttyMSM0,115200n8`) — CONFIRMED_STOCK.
- `ufshc1`, `sdhc2`, `pci-domain0/1/2` (@1c00000/1c08000/1c10000), `mhi-netdev0` on pcie2_rp
  (modem MHI), `swr0/1/2` audio SoundWire.

### Memory
- Bootloader fills `/memory` (reg placeholder 0). RAM starts at 0x80000000.
- reserved-memory (CONFIRMED_STOCK, downstream absolute layout — record only, do not port
  verbatim): hyp 0x80000000+0x600000; xbl_aop 0x80600000+0x260000; cmd_db 0x80860000+0x20000;
  xbl uefi log 0x80880000+0x14000; smem 0x80900000+0x200000; removed 0x80b00000+0x5300000;
  pil_camera 0x86200000+0x500000; wlan_fw 0x86700000+0x100000; ipa_fw/gsi, gpu; npu
  0x86900000+0x500000; video 0x86e00000+0x500000; cvp 0x87300000+0x500000; cdsp
  0x87800000+0x1400000; slpi 0x88c00000+0x2f00000; adsp 0x8bb00000+0x2500000; spss
  0x8e000000+0x100000; cdsp_secure_heap 0x8e100000+0x4600000; cont_splash 0x9c000000+0x2300000;
  dfps 0x9e300000+0x100000; reusable pools (adsp/sdsp/cdsp/sp/user_contig/mem_dump 0x2800000,
  qseecom, qseecom_ta, secure_display, cnss_wlan, CMA, mailbox).
- **No ramoops/pstore region**. **No modem PIL node and no mpss memory region in the stock DT**
  (adsp/cdsp/slpi/spss/venus/ipa PIL nodes exist) — modem boot path on this device is
  bootloader/HYP-managed; treat modem bring-up as UNKNOWN for mainline.

### PMIC / regulators
- SPMI PMICs: pm8150 (sid 0/1), pm8150b (sid 2/3), pm8150l (sid 4/5), `pmxprairie` (sid 8/9),
  pm8009 (sid 0xa/0xb) — CONFIRMED_STOCK. Mainline equivalents: `pm8150.dtsi` (PM8150/PM8150A —
  there is no `pm8150a.dtsi` upstream), `pm8150b.dtsi`, `pm8150l.dtsi`, `pm8009.dtsi`;
  RPMh regulator blocks use `qcom,pmic-id` "a"/"b"/"c"/"d".
- UFS rails: vcc=pm8150_l17 (2.504–2.95 V), vccq=pm8150_l6 (parent pm8150a_s8), vccq2=pm8150_s4.
- WLAN/BT: aon=pm8150_s6, dig=pm8009_s2, rfa1=pm8150_s5, rfa2=pm8150a_s8, asd=pm8150_l16,
  io=pm8150_s4.
- USB HS PHY (downstream/elish mapping): vdda-pll=pm8150_l5 (0.88), vdda18=pm8150_l12 (1.8),
  vdda33=pm8150_l2 (3.072–3.1).

### UFS
- `qcom,ufshc` @1d84000 + ICE, 2 lanes per direction, freq 37.5/300 MHz, `qcom,disable-lpm`,
  vcc-low-voltage-sup — CONFIRMED_STOCK (matches downstream `ufshc_mem`).

### USB
- `usb0` ssusb@a600000 (dwc3 @a600000): `maximum-speed = "high-speed"`, `dr_mode = "drd"`,
  extcon-driven — CONFIRMED_STOCK HS-only, matches vendor cmdline `usbcontroller=a600000.dwc3`.
  `usb1` @a800000: disabled. QMP/USB3 PHY unused.

### Display
- Stock DT contains the shared kona panel zoo; thyme's real panel family is the Xiaomi
  **"xiaomi 42 02 0b"** cmd-mode DSC panels (nodes `dsi_j2_42_02_0b_dsc_cmd` and batch variants
  j1u / j2 / j2-mp / j2-p1 / j2-p2-1 / j2s-mp): 1080×2340, 60/90 Hz, 4-lane, burst mode,
  TE pin + DCS TE, DSC 8bpc, physical 71×154 mm, HDR, peak brightness 4,200,000,
  reset sequence <1 1> <0 1> <1 10>. CONFIRMED_STOCK.
- Runtime selection matches the DDIC ID against `mi,panel-id = <0x4A32 0x00420201>` triple
  ("J2" family, id bytes 42 02 0b) in `dsi_panel_mi.c`; `ro.boot.oled_panel_id=0B` agrees.
  `dsi-default-panel` in the thyme overlay is the `dsi_sim_vid` placeholder — the panel id match
  overrides it at runtime. Earlier "sw43404 family" assumption is **disproven** (those are base
  kona panels). Exact batch variant (j2 vs j2s-mp vs …) is runtime-DDIC dependent — same family,
  no mainline impact.

### Touch / fingerprint / haptics
- Touch: `goodix,gt9889` @ I2C 0x5d on `qupv3_se13_i2c` (i2c@a94000), reset TLMM 38
  (0x26), IRQ TLMM 39 (0x27), panel 1080×2340, firmware `goodix_gt9886_fw_J2.bin`
  (gt9886 DDIC = same J2 panel family), vtouch via TLMM 69 GPIO fixed regulator
  `disp_vddio_vreg`, alt driver `st,fts` present — CONFIRMED_STOCK.
- Fingerprint: `goodix,fingerprint` GPIO device, IRQ TLMM 23, reset TLMM 24.
- Haptics: `aw8697_haptic@5A` (I2C 0x5A).

### WLAN / Bluetooth
- WLAN: `qcom,cnss-qca6390` @b0000000, wlan-en TLMM 20, bt-en TLMM 21, sw-ctrl TLMM 124,
  PCIe RC 0 — CONFIRMED_STOCK.
- BT: `qca,qca6390` node with reset TLMM 21 / sw-ctrl TLMM 124; UART transport (downstream
  hci_qca over qupv3 UART) — CONFIRMED_DOWNSTREAM for transport.

### Charging / battery
- bq25970-standalone @I2C 0x66 on qupv3_se15, IRQ TLMM 68; smb1390 (therm @0xe);
  battery fg-gen4 profiles: alium 3600 mAh / ascent 3450 mAh — CONFIRMED_STOCK.

## 10. Where the parse outputs live

- `work/stock-rom/boot/`, `work/stock-rom/vendor_boot/` — unpack_bootimg output
- `work/stock-rom/vendor_boot-dtbs/` — split base DTBs (dtb-0..3)
- `work/stock-rom/dtbo-entries/` — 29 overlay DTBs (entry-21 = thyme)
- `work/stock-rom/thyme-stock-merged.dtb/.dts` — runtime-equivalent merged DT
- `work/stock-rom/*.txt` — tool outputs (boot-info, dtbo-dump, avb-*)
- `work/tools/` — AOSP Python tools + `REVISIONS.txt` (git-ignored)
