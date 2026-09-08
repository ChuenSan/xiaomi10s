# Route A final report — fastboot boot Android boot image v2

Date: 2026-09-08. Device: Xiaomi Mi 10S (`thyme`, SM8250), Slot A = MIUI V14.0.6.0.TGACNXM.

```
ROUTE_A_REFUTED
```

Route A asked whether this ABL, on `fastboot boot` of a **single** Android boot image v2, takes **that image's** mainline thyme DTB and passes its physical address as Linux `x0`.

It does not do so in any way we can verify. Mutating the v2 DTB field does not change the failure. Do not build more v2 variants. Next architecture is Route B (stock-shaped v3 + vendor_boot + DTBO) on Slot B only.

This round: no flash, no `set_active`, no UART, no local compile.

## 1. Constraint compliance

| Gate | Value |
|---|---|
| Local compilation performed | NO |
| Local build performed | NO |
| Local build validation performed | NO |
| Partition writes performed | NO |
| Slot A modified | NO |
| Slot B modified | NO |
| Additional RAM boots this close-out | NO |

Matrix images: GHA run [34142844651](https://github.com/ChuenSan/xiaomi10s/actions/runs/34142844651) (`b588c04`), success.

## 2. Device matrix (RAM-only `fastboot boot`)

Host always: Sending OKAY, Booting OKAY, Finished. Fastboot VID/PID `18d1:d00d`, serial `41a5627b`, `unlocked=yes`, `current-slot=a`. No Linux gadget. Screen: Fastboot UI gone, black.

USB samples are 1 Hz. “Offline” is missing `fastboot` rows.

| Variant | Image SHA256 (prefix) | Sending | USB offline | Fastboot returns | Linux gadget | vs CONTROL |
|---|---|---|---|---|---|---|
| CONTROL | `a88f97fa…` | 35548 KB OKAY | 08:31:45 fb → 46 missing → 47 fb (~1 s) | YES | NO | baseline |
| NO-DTB (`dtb_size=0`) | `23d3dcd8…` | 35444 KB OKAY | 08:34:46 fb → 47–48 missing → 49 fb (~2 s) | YES | NO | same class; +1 s sample |
| BAD-DTB (FDT magic zeroed) | `ca705fd7…` | OKAY | 08:37:55 fb → 56 missing → 57 fb (~1 s) | YES | NO | identical |
| QC-IDS (`msm-id` `<0x164 0x20001>`, `board-id` `<45 0>`) | `e5459c78…` | OKAY | 08:40:06 fb → 07 missing → 08 fb (~1 s) | YES | NO | identical |

marker-dtb / cmdline-probe **not run**. They only matter if Linux runs far enough to expose `/model` or `/proc/cmdline`. The 1–2 s return gives no such channel.

First 29bc752 CONTROL (`ae32736c…`) was the same class (OKAY, black, Fastboot protocol lives). New CONTROL uses a later Image (`658543c5…`); DTB SHA still `a91a512d…`.

```
172.16.42.1 previous observation: NOT VALID THYME EVIDENCE
```

Unplug the phone: ping still 0% loss, :8080/:23 still connect (host VPN/utun). Liveness requires USB identity, then iface, then IP.

## 3. What the four variants mean

### 3.1 NO-DTB — `dtb_size=0` still Booting OKAY

`Booting OKAY` is sent in `CmdBoot` **before** `BootLinux` returns (`docs/route-a-abl-evidence.md` §2). CONFIRMED_SOURCE + CONFIRMED_DEVICE.

So OKAY does **not** mean:

- ABL required a v2 DTB; or
- ABL used a v2 DTB; or
- the kernel ran.

`dtb_size=0` is **not** a host-visible reject. ABL still takes the download, says OKAY, drops USB ~2 s, comes back to Fastboot.

Implication for “ABL uses the v2 DTB field”:

- The field is **not a gate on the USB command**.
- ABL may still *look at* `dtb_size` internally (`DTB Image not present`) and fail the same way CONTROL fails.
- This variant does **not** prove the v2 payload is the kernel DT.

### 3.2 BAD-DTB — invalid FDT magic ≈ CONTROL

Same size, magic not `d00dfeed`. Same ~1 s path as CONTROL (valid magic).

If ABL were successfully parsing and adopting that payload, CONTROL (walk `compatible` / `msm-id`) and BAD-DTB (`fdt_check_header` fail) would be different code. Both return in one USB sample.

This is **strong evidence that v2 DTB *content* is not what this attempt’s observable outcome depends on**.

It is not, by itself, a proof that ABL never maps the bytes (both errors can finish in <1 s). Together with QC-IDS, it is enough to reject “x0 is this v2 DTB”.

### 3.3 QC-IDS — stock `msm-id` / `board-id`, no change

CI DTB: `qcom,msm-id = <356 131073>` (`0x164` / `0x20001`), `qcom,board-id = <45 0>`. Same 1 s path.

This **refutes** the hypothesis that CONTROL failed **only** because those properties were missing.

Remaining explanations that still fit:

1. This ABL revision does not select DTB from the v2 field on `fastboot boot` (uses slot `vendor_boot_a` / other firmware DT).
2. Selection uses v2 DTB then still dies on `dtbo_a` overlay / pmic-id / another match bit, with the same 1 s envelope.
3. Failure is **before** DTB selection (kernel Image/EFI/load window) and is therefore DTB-invariant.

(1) and (2) both mean Route A’s “single image carries the DT” claim is false in practice. Distinguishing them needs neutralizing `dtbo_a` or replacing `vendor_boot` — that is Route B, and it is a Slot B write, not another v2 image.

## 4. Static ABL evidence (unchanged, now constrained by the matrix)

Thyme `abl.img` = QcomModulePkg `LinuxLoader` (LZMA, `product/thyme/.../LinuxLoader.dll`). XBL: `DefaultBDSBootApp = "LinuxLoader"`. CONFIRMED_BINARY.

| Item | Grade |
|---|---|
| Fastboot Boot path | YES |
| v2 header parser | YES |
| `dtb_addr` as copy destination | NO (`UpdateBootParams` UEFI/PCD windows) |
| AArch64 jump | `kernel(DeviceTreeLoadAddr, 0, 0, 0)` CONFIRMED_SOURCE |
| `LoadAndValidateDtboImg` in `BootLinux` | always called CONFIRMED_SOURCE |
| v2 DTB pages as *successful* x0 | **REFUTED by device matrix** |

`Booting OKAY` + 1 s USB hole + Fastboot protocol without a redrawn logo matches `CmdBoot`: stop USB, `BootLinux` error, `ResetBootDevImage`, Fastboot stays resident. That is not a kernel USB gadget.

## 5. x0

```
X0_SOURCE = NOT OBSERVED
            (ABL source would set DeviceTreeLoadAddr after DTB selection;
             header.dtb_addr is not x0)
X0_POINTS_TO_V2_DTB = REFUTED
```

Refuted claim: “this `fastboot boot` v2 path correctly takes the image DTB and passes it as Linux `x0`.”

Reasons:

- No kernel liveness (no gadget, 1–2 s back to Fastboot).
- NO-DTB / BAD-DTB / QC-IDS do not change that path, so the v2 DTB is not the control variable.
- `x1=x2=x3=0` would hold **if** the jump ran; the jump is not observed.

## 6. vendor_boot_a

```
VENDOR_BOOT_A_USED = UNKNOWN
```

- CAF v2 `CheckImageHeader`: DTB from **boot.img** pages, not vendor_boot. `CmdBoot` registers one RAM `"boot"` image.
- CAF v3 `fastboot boot`: `LoadImageAndAuth` still loads **slot** `vendor_boot` + `dtbo` (Route B, CONFIRMED_CAF_ABL). Xiaomi ABL is that family.
- Device: v2 DTB mutations are invisible. Compatible with “v2 DTB ignored, slot vendor_boot DTB used” **or** “v2 DTB used then a later common fail”.

Cannot write YES (no log that vendor_boot was read on these v2 boots). Cannot write NO (then the matrix is hard to explain unless every v2 DTB path dies in the same 1 s).

## 7. dtbo_a

```
DTBO_A_USED_DURING_FASTBOOT_BOOT = YES
DOWNSTREAM_OVERLAY_CONTAMINATION_RISK = YES
```

`BootLinux` always `LoadAndValidateDtboImg`. Slot A has stock dtbo, entry 21, `board-id <45 0>`. Mainline DTB has no `__symbols__`. Overlay apply cannot be assumed to be a no-op.

QC-IDS did not produce a longer hang or a gadget, so overlay was not shown to succeed. Route A is **not** a self-contained image while `dtbo_a` stays in this path.

Erase/flash dtbo is still forbidden here.

## 8. Failure classification

```
CLASS A: ABL accepts image but never enters kernel.
Confidence: HIGH
```

| Why CLASS A | Why not D/E | Residual |
|---|---|---|
| OKAY is pre-`BootLinux` | no USB gadget | CLASS C (jump + immediate death + watchdog reboot to Fastboot) not **fully** excluded without UART |
| 1–2 s hole matches USB stop + `BootLinux` return | no initramfs signal | If x0 were stock vendor_boot DT + mainline Image, all four variants would also look identical |
| DTB variants do not extend the black interval | | That would still be “wrong DT”, not Route A success |

Not CLASS B as a *verified* jump-with-bad-x0: no evidence of payload entry.

## 9. Route A final gate

```
ROUTE_A_REFUTED
```

v2 is a header this ABL will **parse** (download + OKAY). It is not a proven, isolatable DTB delivery path on thyme.

- Accepting the image ≠ `x0` = v2 DTB.
- The DTB we put in the v2 field is not an experimental lever.
- Remaining forks require replacing **vendor_boot** and/or **dtbo** on a writable slot = Route B.

Do not spend another GHA kernel hour on v2 packing. Do not RAM-boot marker-dtb / cmdline-probe.

## 10. Switch to Route B

Yes.

Route B: stock Android 13 shape.

```
boot_b          header v3   (Image + initramfs, no DTB field)
vendor_boot_b   header v3   (mainline sm8250-xiaomi-thyme.dtb + vendor cmdline)
dtbo_b          one no-op overlay, qcom,board-id = <45 0>
```

Already designed and GHA-built on `route-b-v3` (`docs/route-b-v3-boot-chain.md`). `fastboot boot` of **v3 boot alone** still pulls `vendor_boot_a` + `dtbo_a` from the **active** slot — it does **not** validate the mainline DTB. The real experiment is **Slot B writes**, never Slot A.

This close-out does **not** flash Route B.

### Unique next milestone

```
ROUTE_B_SLOT_B_TRIPLE_WRITE
```

1. Re-verify GHA Route B artifacts (boot-v3 + vendor_boot-v3 + no-op dtbo) SHA256.
2. Preflight: `product=thyme`, `unlocked=yes`, `current-slot=a`, `slot-count=2`.
3. Human-gated, Slot B only:

   `fastboot flash boot_b` / `vendor_boot_b` / `dtbo_b`

   No `set_active`. No `*_a`. No vbmeta.
4. Observe USB identity (not `172.16.42.1`). Rollback = reflash stock `*_b`.

## 11. GitHub Actions / git

| Item | Value |
|---|---|
| Matrix workflow | `route-a-v2-boot-investigation.yml` |
| Matrix run | [34142844651](https://github.com/ChuenSan/xiaomi10s/actions/runs/34142844651) success, 19m11s |
| Artifact | `thyme-route-a-v2-b588c04d4b151374ac05c2c1323bafbee28c3f38` |
| New GHA this close-out | none (docs only; no new images) |

## 12. Files

- `docs/route-a-report.md` (this file)
- `docs/route-a-abl-evidence.md` (device matrix vs static)
- `configs/route-a/variants.md` (stop v2 variants)
- `README.md` (Route A closed)

## 13. mem0

Long-term: `ROUTE_A_REFUTED`; matrix four-way same 1–2 s Fastboot return; `X0_POINTS_TO_V2_DTB=REFUTED`; `DTBO_A_USED=YES`; `VENDOR_BOOT_A_USED=UNKNOWN`; `172.16.42.1` invalid; CLASS A HIGH; next = Route B Slot B triple write.
