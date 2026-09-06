# Xiaomi Mi 10S (thyme) hardware mapping

Project: mainline Linux 6.6 bring-up on Xiaomi Mi 10S (`thyme`, Qualcomm SM8250/kona, arm64).

Status markers: `CONFIRMED_STOCK` (stock merged DT from ROM), `CONFIRMED_DOWNSTREAM`
(vendor kernel source), `CONFIRMED_BOTH`, `INFERRED`, `UNKNOWN`.
Detailed stock-image parsing: `docs/stock-rom-analysis.md`.

## Device identity

| Fact | Value | Source | Status |
|---|---|---|---|
| Model | Xiaomi M2102J2SC (Mi 10S) | task brief | CONFIRMED |
| Codename | thyme | task brief + downstream DTS | CONFIRMED |
| SoC | Qualcomm SM8250 (kona) **v2.1** | stock base DTB `msm-id <0x164 0x20001>` | CONFIRMED_BOTH |
| Stock ROM | V14.0.6.0.TGACNXM (Android 13, SPL 2023-09) | device + ROM AVB props | CONFIRMED_BOTH |
| Android kernel | 4.19.157-perf-g9d90dd04aa7c | device | CONFIRMED |
| Bootloader | **unlocked** (`fastboot getvar unlocked: yes`) | fastboot, 2026-09-06 | CONFIRMED |

## Boot chain / DT layout

| Fact | Value | Source | Status |
|---|---|---|---|
| boot.img | header **v3**, kernel 50.2 MB, ramdisk 18.8 MB gzip, no cmdline | parsed | CONFIRMED_STOCK |
| vendor_boot.img | header **v3**, page 4096, DTB @ 0x1f00000 | parsed | CONFIRMED_STOCK |
| vendor cmdline | `console=ttyMSM0,115200n8 … androidboot.usbcontroller=a600000.dwc3 …` | vendor_boot | CONFIRMED_STOCK |
| Base DTBs in vendor_boot | 4 concatenated FDTs: kona v2.1 / v2 / v1 / empty stub | split script | CONFIRMED_STOCK |
| Selected base DTB | index 0 = kona v2.1 (`dtb_idx=0`) | live device + split | CONFIRMED_BOTH |
| DTBO | `dtbo.img` 29 entries; **entry 21 = xiaomi thyme, board-id `<45 0>`** | mkdtboimg | CONFIRMED_BOTH |
| Overlay merge | fdtoverlay(base0 + entry21) succeeds → runtime-equivalent DT | work/stock-rom | CONFIRMED_STOCK |
| Console UART | stock `serial0` = qup_uart@988000 = mainline **uart2** (geni-debug-uart @ 0x988000) | stock aliases + mainline dtsi | CONFIRMED_BOTH |
| Bootloader state note | `ro.boot.flash.locked=1`/`verifiedbootstate=green` are AVB presentation props; factory vbmeta already carries Flags 2 (verification disabled) — BL is unlocked per fastboot | fastboot + avbtool | CONFIRMED |

## Subsystem mapping

| Subsystem | Stock evidence | Downstream | Mainline 6.6 support | Port status |
|---|---|---|---|---|
| PMIC | spmi: pm8150(0/1), pm8150b(2/3), pm8150l(4/5), pmxprairie(8/9), pm8009(a/b) | kona-pmic-overlay | pm8150.dtsi (covers PM8150A!), pm8150b/pm8150l/pm8009.dtsi; rpmh regulators per `qcom,pmic-id` a/b/c/d | CONFIRMED — include set settled |
| UFS | @1d84000 + ICE, 2 lanes, disable-lpm, vcc=pm8150_l17 2.504–2.95 V, vccq=pm8150_l6 (parent pm8150a_s8), vccq2=pm8150_s4 | ufshc_mem quirks | ufs_mem_hc/phy, same rails as elish | CONFIRMED_BOTH → in DTS v1 |
| USB | usb0 @a600000 HS-only `dr_mode="drd"`; usb1 disabled | usb0 dwc3 HS-only | usb_1 + utmi-as-pipe (elish identical) | CONFIRMED_BOTH → in DTS v1 (dr_mode=peripheral for v1) |
| Console | ttyMSM0 115200n8 = uart2 @0x988000 | serial0 alias | uart2 geni-debug-uart | CONFIRMED_BOTH → in DTS v1 |
| Display | panel family **"xiaomi 42 02 0b"** cmd-mode DSC (J2 DDIC, 6 batch variants), 1080×2340 60/90 Hz, 4-lane, TE pin, DSC 8bpc, 71×154 mm; `oled_panel_id=0B`; runtime panel-id match vs `mi,panel-id <0x4A32 0x00420201>`; default-panel=sim placeholder | dsi-panel-j2*-42-02-0b-*.dtsi | no upstream driver for this panel | needs driver work (panel) — sw43404 assumption disproven |
| Touch | goodix,gt9889 @0x5d on qupv3_se13_i2c (i2c@a94000), reset TLMM38, IRQ TLMM39, fw `goodix_gt9886_fw_J2.bin`, vtouch TLMM69 gpio regulator | thyme-pinctrl | no in-tree GT9889/9886 driver | needs driver work |
| Fingerprint | goodix,fingerprint, IRQ TLMM23, reset TLMM24 | thyme dtsi | none | later |
| Haptics | aw8697_haptic@5A (I2C) | thyme dtsi | no upstream aw8697 | later |
| WLAN | qcom,cnss-qca6390 @b0000000, wlan-en TLMM20, PCIe RC0 | thyme dtsi | ath11k supports QCA6390 | needs DTS later |
| Bluetooth | qca,qca6390, reset TLMM21, sw-ctrl TLMM124; UART transport | thyme dtsi + hci_qca | hci_qca + serdev | needs DTS later |
| BT/WLAN rails | aon=s6a, dig=pm8009_s2, rfa1=s5a, rfa2=s8a, asd=l16a, io=s4a | kona-pmic-overlay | rpmh | needs DTS later |
| Audio | swr0/1/2, bolero macros, wcd938x-class | thyme-audio-overlay | q6/Bolero available | later |
| Modem | **no modem PIL node / no mpss region in stock DT**; mhi-netdev0 on pcie2 | — | mpss pas available | UNKNOWN boot path |
| Remoteproc (adsp/cdsp/slpi/venus) | pil regions in reserved-memory; PIL nodes present | thyme dtsi | pas + mbn | deferred (keep disabled v1) |
| Charging | bq25970-standalone @0x66 se15, IRQ TLMM68; smb1390 | thyme-sm8250.dtsi | bq25970 partial, smb1390 none | later |
| Battery | fg-gen4: alium 3600 mAh / ascent 3450 mAh profiles | fg-gen4 data | simple-battery possible | later |
| Buttons | stock: pon resin + vol keys (unverified mapping) | xiaomi-common | gpio-keys/pon | investigate |
| Camera | sensors in thyme camera dtsi; flashes via pm8150l | camera-sensor dtsi | camss partial | later |
| NFC | nq@64 se15 disabled in thyme dtsi | thyme dtsi | nq-nci exists | UNKNOWN |

## Sources

- Stock ROM parse: `docs/stock-rom-analysis.md`, `work/stock-rom/thyme-stock-merged.dts`
- Downstream DT: `android-kernel-sm8250/arch/arm64/boot/dts/vendor/qcom/` (thyme-*, xiaomi-sm8250-common, kona-*, dsi-panel-j2*-42-02-0b-*)
- Mainline reference: `linux-6.6/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi`, `sm8250-mtp.dts`
- Live device: `ro.boot.*`, fastboot getvar (read-only)

## First-version DTS scope (implemented)

`linux-6.6/arch/arm64/boot/dts/qcom/sm8250-xiaomi-thyme.dts`:
compatible `xiaomi,thyme` + `qcom,sm8250`; includes sm8250 + pm8150 + pm8150l;
regulators: vph_pwr, s4a/l5a/l6a/l9a/l12a/l17a/l2a (pmic-id a), s5a/s6a (pmic a), s8c/bob (pmic c);
UFS + UFS PHY with stock-matched rails; USB1 HS-only (peripheral); uart2 console (aliases serial0, stdout-path).
Deliberately out of scope v1: display, touch, WLAN/BT, audio, camera, modem, remoteproc firmware, buttons, battery/charging.
