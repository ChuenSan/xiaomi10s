# Route A report — fastboot boot Android boot image v2

Date: 2026-09-08. Device: Xiaomi Mi 10S (thyme), SM8250, slot A stable MIUI V14.0.6.0.TGACNXM.

This round answers whether ABL takes the v2-image DTB and passes its physical address as `x0`. It is not a “make Linux boot” round.

## 1. Constraint compliance

| Gate | Value |
|---|---|
| Local compilation performed | NO |
| Local build performed | NO |
| Local build validation performed | NO |
| Partition writes performed | NO |
| Slot A modified | NO |
| Slot B modified | NO |

Read-only parse of the existing CI artifact and `abl.img` LZMA payload only. Variant images are GHA-only (`route-a-v2-boot-investigation.yml`). No `fastboot boot` this round: matrix artifacts are not built yet.

## 2. Experimental v2 exact header

From `29bc752` artifact `experimental-boot-v2.img`
SHA256 `ae32736c59bd21b02abcf0f1263ace2c5b46569c4a387585dd92d34948f5034b`.

| Field | Value |
|---|---|
| kernel_size | 35101184 |
| kernel_addr | `0x8000` |
| ramdisk_size | 1186235 |
| ramdisk_addr | `0x1000000` |
| tags_addr | `0x100` |
| page_size | 4096 |
| header_version | 2 |
| header_size | 1660 |
| os_version / SPL | 13.0.0 / 2023-09 |
| name | thyme |
| cmdline | stock vendor_boot cmdline (see analysis doc) |
| extra_cmdline | empty |
| dtb_size | 105960 |
| dtb_addr | `0x1f00000` |
| second / recovery_dtbo | 0 |

## 3. Binary layout

| Region | offset | end |
|---|---:|---:|
| header | 0 | 1660 (page 4096) |
| kernel | 4096 | 35105280 |
| ramdisk | 35106816 | 36293051 |
| DTB | 36294656 | 36400616 |

computed_end = file_size = 36401152. PASS.

`DTB payload exact match: YES`
(`a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40`)

One FDT magic in the whole image, at the v2 DTB field. Kernel has no appended DTB.

## 4. Physical memory layout

Header-claimed ranges overlap (kernel vs ramdisk vs DTB) if treated as destinations. Stock uses the same numbers and boots.

ABL ignores those fields as copy destinations and relocates into UEFI/PCD windows (`docs/route-a-abl-evidence.md`).

```
collision (header-as-dest): YES (irrelevant)
DTB_LOAD_ADDRESS_SAFE: YES
```

Do not retune addresses.

## 5. ABL investigation

| Question | Answer |
|---|---|
| Fastboot Boot code path identified | YES |
| boot v2 parser identified | YES |
| DTB field consumption | YES (`dtb_size` + payload pages) |
| kernel entry handoff | CONFIRMED in QcomModulePkg / this ABL package; not confirmed on this boot |

`abl.img` decompresses to thyme `LinuxLoader` (`product/thyme/.../LinuxLoader.dll`). XBL `DefaultBDSBootApp = "LinuxLoader"`.

## 6. x0 conclusion

```
X0_SOURCE = DeviceTreeLoadAddr after ABL DTB selection (not header dtb_addr)
X0_POINTS_TO_V2_DTB = NOT_CONFIRMED
```

Evidence: AArch64 jump is `kernel(dtb,0,0,0)` in this ABL family. Mainline DTB lacks `qcom,msm-id`. Slot A `dtbo_a` is still loaded. Overlay-path `GetSocDtb` then fails with `qcom,msm-id entry not found` / `ERROR: Couldn't find the suitable DTB!`. Jump likely never happens.

## 7. x1/x2/x3

ABL passes zeros. Compliant **if** the jump runs. Not observed on device.

## 8. cmdline conclusion

```
BOOT_V2_CMDLINE_USED = YES
VENDOR_BOOT_A_USED = NO
```

v2 cmdline is the packed stock vendor cmdline. ABL appends `androidboot.serialno/slot_suffix/dtbo_idx/dtb_idx/bootdevice/vbmeta/...`. vendor_boot is not the v2 DTB or cmdline source (`CmdBoot` loads one RAM `boot` image).

## 9. DTBO conclusion

```
DTBO_A_USED_DURING_FASTBOOT_BOOT = YES
DOWNSTREAM_OVERLAY_CONTAMINATION_RISK = YES
```

`LoadAndValidateDtboImg` runs inside `BootLinux` even for RAM `fastboot boot`. Stock dtbo entry 21 (`board-id <45 0>`) is present on slot A. Overlay apply needs `__symbols__` which mainline lacks. Route A is **not** a self-contained single image while `dtbo_a` remains in that path. Erase/flash dtbo is forbidden this round.

## 10. Differential image matrix

| Variant | Purpose | SHA256 | Fastboot accepts? | Time to return | USB | Observed |
|---|---|---|---|---|---|---|
| V2-CONTROL | baseline | (GHA pending) | first boot: YES OKAY | n/a | fastboot 18d1:d00d remained | black screen, no Linux gadget |
| V2-NO-DTB | dtb_size=0 | pending | not run | | | |
| V2-BAD-DTB | bad FDT magic | pending | not run | | | |
| V2-MARKER-DTB | unique `/model` | pending | not run | | | |
| V2-QC-IDS | msm-id + board-id | pending | not run | | | |
| V2-CMDLINE-PROBE | `route_a_cmdline_probe=1` | pending | not run | | | |

First-boot row is the already-run 29bc752 CONTROL. New matrix must come from the new workflow. RAM-only tests wait for that workflow green.

APPENDED-DTB-to-kernel not selected (v2 already uses the dtb field).

## 11. USB observations

| Item | Value |
|---|---|
| Fastboot VID/PID | `18d1:d00d` serial `41a5627b` |
| Linux USB gadget | not found |
| Linux USB network | not found |

```
172.16.42.1 previous observation: NOT VALID THYME EVIDENCE
```

Host VPN/utun still answers that address after unplug. Liveness requires USB identity + new iface, then IP.

## 12. x0 probe

Not run. `DIRECT_X0_PROBE_DEFERRED`.

Static evidence already says the likely failure is pre-jump DTB match. A PSCI-reset probe cannot distinguish CLASS A. `psci.method = smc` is in `sm8250.dtsi` but unused until a jump is plausible.

## 13. Failure classification

```
CLASS A: ABL accepts image but never enters kernel.
Confidence: MEDIUM
```

Supports: Booting OKAY is issued before `BootLinux` finishes; `BootLinux` errors return to Fastboot with USB restart and no logo redraw; mainline DTB has no `qcom,msm-id`; dtbo_a is in the path.

Does not fully exclude a watchdog return from a microseconds-long kernel (CLASS C) because there is no UART. Differential NO-DTB / BAD-DTB / QC-IDS is the next discriminator.

Not CLASS D/E: no USB gadget, no proof of init.

## 14. GitHub Actions

| Item | Value |
|---|---|
| Existing firstboot | `thyme-mainline-boot-artifacts` run 34116449773, commit 29bc752, success |
| New workflow | `.github/workflows/route-a-v2-boot-investigation.yml` |
| New run | not dispatched until this commit is on the remote |
| Artifacts | `thyme-route-a-v2-<sha>` (control/no-dtb/bad-dtb/marker-dtb/qc-ids/cmdline-probe) |

## 15. Files changed

- `docs/route-a-v2-boot-analysis.md`
- `docs/route-a-abl-evidence.md`
- `docs/route-a-report.md`
- `configs/route-a/variants.md`
- `scripts/route-a/parse_boot_v2.py`
- `scripts/route-a/make_v2_variants.py`
- `.github/workflows/route-a-v2-boot-investigation.yml`
- `README.md`

No change to `sm8250-xiaomi-thyme.dts` or the long-term patch queue.

## 16. mem0 updates

Long-term facts to store: v2 header/offsets; DTB exact match; ABL is thyme LinuxLoader; header addrs not copy dest; dtbo_a still used on fastboot boot; vendor_boot_a not the v2 DTB source; no msm-id on mainline DTB; 172.16.42.1 is not liveness; CLASS A MEDIUM; x0 NOT_CONFIRMED; Route A not confirmed as self-contained.

## 17. Route A final conclusion

```
ROUTE_A_BLOCKED_BY_MISSING_EVIDENCE
```

v2 is a real ABL compatibility header (parser + Booting OKAY). It is not shown that the v2 DTB becomes `x0`. Leading blocker: ABL DTB match (`qcom,msm-id`) plus slot A dtbo overlay path. Until QC-IDS / NO-DTB / BAD-DTB RAM boots exist, do not treat black screen as a mainline DTS bug and do not switch the whole project to Route B solely on this boot.

If QC-IDS still returns immediately to fastboot, overlay-on-dtbo_a is the remaining v2 blocker and Route A as “single-image self-contained” is then refuted without touching dtbo (forbidden here).

## 18. Recommended next action

1. Dispatch `route-a-v2-boot-investigation` and wait for green artifacts.
2. RAM-only, one variant at a time, `fastboot boot` CONTROL then NO-DTB then BAD-DTB then QC-IDS. Record USB VID/PID/serial/location and whether Fastboot returns without a gadget.
3. Decision:
   - NO-DTB/BAD-DTB change time-to-return vs CONTROL → ABL is parsing the v2 DTB field (expected).
   - QC-IDS uniquely proceeds (USB gadget or much longer hang) → msm-id was the gate; still must reason about dtbo overlay.
   - All four identical to first boot → still CLASS A, but selection hypothesis weakens.
4. Do not flash, `set_active`, or erase dtbo.
5. Do not debug display/USB/initramfs until x0/DTB selection is settled.
