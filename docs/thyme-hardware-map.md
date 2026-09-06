# Xiaomi Mi 10S (thyme) hardware mapping

Project: mainline Linux 6.6 bring-up on Xiaomi Mi 10S (`thyme`, Qualcomm SM8250/kona, arm64).

Status markers: `CONFIRMED` (verified from source/device), `INFERRED` (evidence but not proven), `UNKNOWN`.

## Device identity

| Fact | Value | Source | Status |
|---|---|---|---|
| Model | Xiaomi M2102J2SC (Mi 10S) | task brief | CONFIRMED |
| Codename | thyme | task brief + downstream DTS | CONFIRMED |
| SoC | Qualcomm SM8250 (kona) | task brief | CONFIRMED |
| Region variant | GLOBAL, hwlevel MP, hwversion A.9.0 | `ro.boot.hwc/hwlevel/hwversion` | CONFIRMED |
| Stock ROM on device | V14.0.6.0.TGACNXM (Android 13) | `ro.build.version.incremental` | CONFIRMED |
| Android kernel on device | 4.19.157-perf-g9d90dd04aa7c | task brief | CONFIRMED |

## Boot chain / DT layout (downstream)

| Fact | Value | Source | Status |
|---|---|---|---|
| Base DTB | `kona.dtb` (also kona-v2/kona-v2.1 listed in dtbo-base) | `arch/arm64/boot/dts/vendor/qcom/Makefile:29` | CONFIRMED |
| DTBO | `thyme-sm8250-overlay.dtbo` | same, `Makefile:16` | CONFIRMED |
| Board ID | `qcom,board-id = <45 0>` | `thyme-sm8250-overlay.dts` | CONFIRMED |
| Compatible (downstream) | `qcom,kona-mtp`, `qcom,kona`, `qcom,mtp` | `thyme-sm8250-overlay.dts` | CONFIRMED |
| Active DTB index on device | `ro.boot.dtb_idx = 0` | live device | CONFIRMED |
| Active DTBO index on device | `ro.boot.dtbo_idx = 21` | live device | CONFIRMED |
| Boot device | `soc/1d84000.ufshc` (UFS host @ 0x1d84000) | `ro.boot.bootdevice` | CONFIRMED |
| Boot console | `ttyMSM0` | `ro.boot.console` | CONFIRMED |
| Serial console path (mainline) | `serial0` alias exists on live DT; mainline = `uart0` on TLMM | live DT aliases | INFERRED |

⚠️ **Lock-state discrepancy**: `ro.boot.flash.locked=1` and `ro.boot.verifiedbootstate=green` both indicate the bootloader currently reports LOCKED, contradicting the "unlocked" note from the task brief. Verify read-only with `fastboot getvar unlocked` before any flashing milestone. No flashing is planned this round.

## Subsystem mapping

| Subsystem | Downstream thyme | Mainline SM8250 support | Reference DTS | Port status |
|---|---|---|---|---|
| SoC | kona.dtsi (Qualcomm vendor tree) | `sm8250.dtsi` complete | sm8250-mtp.dts | known |
| PMIC | pm8150 + pm8150a + pm8150b + pm8009 (`kona-pmic-overlay.dtsi`) | rpmh-regulators for all four | elish-common (`pm8150/pm8150l/pm8009`) | investigate (rail table per panel/pm: `oled_pmic_id=0A`) |
| UFS | `&ufshc_mem` @1d84000, `qcom,disable-lpm`, hsg4_synclength quirk; vcc=pm8150_l17, vccq=pm8150_l6, vccq2=pm8150_s4 | `ufs_mem_hc` + `ufs_mem_phy` (l17a/l6a/s4a — same rails as elish) | elish-common | investigate (quirk flags differ) |
| USB | HS-only: `&usb0` dwc3@a600000 + usb2_phy0, `maximum-speed=high-speed`; usb1/qmp/dp PHY disabled | `usb_1` UTMI-as-pipe, HS-only DWC3 — identical approach works | elish-common (USB 2.0 only) | investigate (mode: peripheral vs OTG) |
| Wi-Fi/BT | `bt_qca6390` (QCA6390 combo): aon=pm8150_s6, dig=pm8009_s2, rfa1=pm8150_s5, rfa2=pm8150a_s8, asd=pm8150_l16; WLAN via cnss + PCIe | ath11k supports QCA6390 via PCIe (pcie0) | elish has no wlan/bt node in-tree | later |
| Display | sw43404 AMOLED DSC family (Mi 10 series panel lib), reset TLMM75, TE TLMM66, bl via DCS; `oled_panel_id=0B` | `mdss_dsi0` (single DSI on thyme) + panel driver upstream? | elish is dual-DSI Mi Pad (NOT applicable directly) | later |
| Touch | Goodix GT9889 `goodix@5d` on I2C, reset=TLMM38, irq=TLMM39; 1080×2340; alt driver ST FTS present in config | mainline has goodix-berlin? no in-tree GT9889 driver | elish has no touch node | later |
| Fingerprint | Goodix FOD (`ro.boot.fpsensor=goodix_fod6`, `TOUCHSCREEN_FOD`) | none | — | later |
| Haptics | AW8697 (`INPUT_AW8697_HAPTIC`), vdd_boost on pm8150b_gpios 5/12 | none (aw8695/8697 drivers not upstream) | — | later |
| Audio | WSA max devs 0, MBHC USB-C audio, micbias 2750 mV, MI2S lines 2/1, sbu_uart_en mux | q6asm/lpass available | elish (sound card) | later |
| Battery/charge | fg-gen4 gauge: alium 3600 mAh / ascent 3450 mAh variants; smb1390 + bq25970 (@I2C qupv3_se15, irq TLMM68) | simple-battery + bq25xxx upstream; smb1390 not upstream | elish uses bq27z561 (different) | later |
| Remoteproc | pil regions on live DT: adsp/cdsp/slpi/spss/video/wlan_fw/camera/cvp/npu/ipa | adsp/cdsp/slpi/venus/mpss all supported | elish enables adsp/cdsp/slpi/venus with mbn | investigate (firmware sourcing) |
| Regulators (boot-critical) | UFS: l17/l6/s4; USB PHY: l5 (0.88), l12 (1.8), l2 (3.1) in elish mapping | pm8150 rpmh rails in sm8250.dtsi apps_rsc | elish-common regulator table | investigate |
| PCIe | 3 domains + mhi-netdev0 alias (modem MHI) | pcie0/1/2 in sm8250.dtsi | elish enables pcie0 (WLAN) | later |
| Camera | flashes via pm8150l; sensors in `thyme-sm8250-camera-sensor-mtp.dtsi` | camss support partial | — | later |
| NFC | `nq@64` on qupv3_se15 disabled in thyme dtsi | nq-nci driver exists | — | UNKNOWN (device variant) |
| Buttons | vol up/down standard kona pon (elish: pm8150_gpios6 vol_up, resin vol_down) | gpio-keys + pon | elish-common | investigate |

## Sources

- Downstream DT: `android-kernel-sm8250/arch/arm64/boot/dts/vendor/qcom/` — `thyme-sm8250.dtsi`, `thyme-sm8250-overlay.dts`, `thyme-pinctrl.dtsi`, `thyme-audio-overlay.dtsi`, `thyme-sm8250-camera-sensor-mtp.dtsi`, `xiaomi-sm8250-common.dtsi`, `kona-sde-display.dtsi`, `kona-pmic-overlay.dtsi`
- Downstream config: `android-kernel-sm8250/arch/arm64/configs/vendor/xiaomi/thyme.config`
- Live device: `adb shell getprop` (ro.boot.*, ro.build.*), `/sys/firmware/devicetree/base` (node names only; file contents shell-denied)
- Mainline reference: `linux-6.6/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-{common,boe,csot}*`

## Open items

1. Bootloader lock state contradiction (see warning above).
2. Stock artifacts (boot.img/vendor_boot.img/dtbo.img/vbmeta.img) not present locally; obtain from V14.0.6.0.TGACNXM fastboot ROM, then parse: header version, page size, cmdline, DTBO index 21 content, panel variant.
3. `/proc/cmdline` unreadable via adb (Permission denied) — recover cmdline from unpacked boot/vendor_boot instead.
4. Exact thyme panel part number (dtbo_idx 21 content will confirm).
5. thyme-specific pinctrl/GPIO map not yet fully extracted (thyme-pinctrl.dtsi).

## First-version DTS scope (decision)

Minimal `sm8250-xiaomi-thyme.dts` targets, driven by the CONFIRMED facts above:

- model/compatible: `xiaomi,thyme`, `qcom,sm8250`
- memory/reserved-memory: start from elish layout, verify against device (9-class pil regions confirmed present)
- PMIC: pm8150 + pm8150l + pm8009 rpmh regulators (pm8150b only if boot needs it)
- UFS: l17a/l6a/s4a supplies (matches both downstream thyme and mainline elish)
- USB: usb_1 HS-only peripheral (matches both downstream and elish)
- remoteproc: defer firmware, keep nodes disabled first revision
- chosen/bootargs: console=ttyMSM0 strategy after boot image parsing

Explicitly out of scope for v1: display, touch, camera, audio, modem, WiFi/BT.
