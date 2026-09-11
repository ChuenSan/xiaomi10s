# Route B R1 — boot/handoff reference matrix

Stage: `MAINLINE_V2_R1_ALIOTH_THYME_REFERENCE_AUDIT`

```text
local build:                 NO
local Image/DTB decompile:   NO
GHA-only validation:         YES
device operation (R1):       NO
Slot A written:              NO
B at R1 close:               M1 DT context + M5D boot_b
B after later M5E:           Stock DT context + M5D boot_b
M5E_HEADER_LOAD_SEMANTICS_AUDIT:        PAUSED
M5E_STOCK_DT_TRUE_DEVICE_CROSSOVER:     EXECUTED, see docs/route-b-mainline-v2-m5e-dt-context-crossover-control.md
```

mem0 was read first (`user_id=default`, agent `bzg-thyme-mainline`).

## Frozen identities

```text
M0/M1 boot_b SHA256     378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
M5D boot_b SHA256       4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
M1 vendor_boot N=114688 29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
M1 dtbo N=387           316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
M1 raw DTB              a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
M1 ABL DTB              cefafcca5fa926998cd7b9aa320ce28fc52aad156c942e0adc0d9152f81ae9b0
```

Exact M1 `vendor_boot` unpack remains private-CI (`ChuenSan/thyme-mainline-private-ci`
run `34338768052`). Public GHA reconstructs the ABL DTB and no-op DTBO from the
same source recipe and dumps them. Match against the SHAs above is a gate, not
an assumption.

## Four-way DT matrix

| Field | Stock thyme | Mainline thyme M1 | Alioth Mainline | Astide thyme |
|---|---|---|---|---|
| kernel | stock 4.19 | Linux 6.6.156 | Linux 7.2.2 | 4.19.325 |
| model | kona v2.1 SoC (merged root) | Xiaomi Mi 10S (thyme) | Xiaomi POCO F3 | Qualcomm… xiaomi thyme (overlay) |
| compatible | `qcom,kona` (base) | `xiaomi,thyme`, `qcom,sm8250` | `xiaomi,alioth`, `qcom,sm8250` | overlay: `qcom,kona-mtp/kona/mtp` |
| msm-id | `<0x164 0x20001>` on **base** | source DTS: **absent**; ABL DTB: `<356 0x20001>` injected | `<356 0x20001>` on **base** | `<356 0x20001>` on kona-v2.1 **base** |
| board-id | `<0 0>` on **base**; `<45 0>` on **overlay** | source DTS: **absent**; ABL DTB: `<45 0>` on **base**; no-op DTBO: `<45 0>` | `<44 0>` on **base** | `<0 0>` base; `<45 0>` overlay |
| pmic-id (root) | NONE | NONE | NONE | NONE |
| /memory | placeholder `reg=<0 0 0 0>` | ABSENT in DTS | ABSENT in DTS | SoC base (stock-like) |
| reserved-memory | stock map (xbl_aop `0x80600000+0x260000`, adsp `0x8bb00000+0x2500000`, …) | upstream sm8250.dtsi (not overridden) | upstream deleted + stock-like rebuild | downstream kona + thyme overlay |
| chosen stdout-path | NONE | `serial0:115200n8` | NONE | NONE in overlay root |
| serial0 | `qup_uart@988000` (uart2) | `&uart2` | `&uart6` | stock path (SoC + overlay) |
| DTBO | 29-entry family pack; entry 21 thyme | 1-entry no-op, board-id `<45 0>`, marker `qcom,thyme-route-b-noop` | NONE in repo | `thyme-sm8250-overlay.dtbo` vs 3 kona bases |
| DTB packaging | vendor_boot v3, 4 concatenated FDTs (~1.61 MiB) | vendor_boot v3, **single** ABL DTB | raw DTB only | kernel dtbo + kona dtb; no vendor_boot in repo |
| EFI stub | stock 4.19 `# CONFIG_EFI`; PE offset 0 | empirical MZ (M5B); M5D PE field 0, payload kept | `CONFIG_EFI_STUB=y`, zboot off | `# CONFIG_EFI is not set` |

Sources: `docs/stock-rom-analysis.md` (existing stock context),
`patches/linux-6.6/0002-*.patch`, `scripts/mainline-v2-m1-ci-validate.sh`,
`refs/alioth-mainline-7.2.2` DTS/CMake, `refs/astidelabs-sm8250` overlay/Makefile.

## M1 artifact findings (source recipe + historical CI)

Public source DTS (`sm8250-xiaomi-thyme.dts`) has **no** `qcom,msm-id` /
`qcom,board-id`. M1 CI copies the DTB and `fdtput`s:

```text
qcom,msm-id  = <356 131073>    # 356=0x164=SM8250, 131073=0x20001
qcom,board-id = <45 0>
ABL_PACKAGING_METADATA_ADDED=YES
```

That ABL DTB is what `mkbootimg --dtb` places in `vendor_boot`. Raw DTB SHA
`a91a512d…` ≠ ABL DTB SHA `cefafcca…`.

No-op DTBO (exact source in M1 validator):

```text
/plugin/
model       = "Xiaomi Mi 10S (thyme) Route B no-op"
compatible  = "qcom,kona-mtp", "qcom,kona", "qcom,mtp"
qcom,board-id = <45 0>
fragment@0  target-path = "/"
__overlay__ qcom,thyme-route-b-noop
```

Linux OF: no-op (marker only). ABL: selectable overlay **if** it matches by
board-id like stock entry 21. It is not a stock-sized thyme overlay.

```text
M1_DTB_MODEL=Xiaomi Mi 10S (thyme)          # source; GHA dump confirms
M1_DTB_COMPATIBLE=xiaomi,thyme qcom,sm8250
M1_DTB_MSM_ID=source NONE; packaged 356 131073
M1_DTB_BOARD_ID=source NONE; packaged 45 0
M1_DTBO_BOARD_ID=45 0
M1_DTBO_MSM_ID=NONE
EXACT_M1_VENDOR_BOOT_DUMP=PRIVATE_CI_REQUIRED
```

## Image header matrix

| Field | Stock 4.19 | Mainline thyme M5D | Alioth 7.2.2 |
|---|---|---|---|
| code0 | parsed (PE offset 0) | direct `b primary_entry` (M5B+; MZ removed) | PENDING_GHA; config EFI_STUB=y |
| text_offset | `0x80000` | `0x80000` | PENDING_GHA |
| image_size | `0x3d0b000` | `0x2220000` | PENDING_GHA |
| flags | `0xa` | `0xa` | PENDING_GHA |
| magic | ARM64 | ARM64 | PENDING_GHA |
| PE offset | `0x0` | `0x0` (payload still present) | PENDING_GHA |
| EFI stub config | no | arm64 defconfig + empirical MZ on M0–M4B | `CONFIG_EFI_STUB=y` `EFI_ZBOOT` n |
| EFI zboot | n | n | n |

M5B/M5C/M5D already showed MZ / text_offset / PE-offset field changes do not
suppress the 4.7s return under M1 DT.

```text
ALIOTH_SUCCESS_WITH_EFI_STUB_CONFIG=YES
MAINLINE_EFI_HEADER_AS_ROOT_CAUSE=DEPRIORITIZED_BY_ALIOTH_REFERENCE
```

Reference only; not thyme causal proof. Binary alioth header still PENDING_GHA.

## Difference classes

**CLASS A — ABL-visible / pre-kernel (priority)**

1. vendor_boot DTB *shape*: stock 4 concatenated kona FDTs vs M1 single
   Mainline FDT.
2. dtbo *table*: 29 family overlays vs 1 no-op.
3. board-id *placement*: stock/Astide put `<45 0>` only on the overlay and
   `<0 0>` on the base; M1 (following alioth DTS) puts `<45 0>` on the base
   DTB *and* on the no-op overlay.
4. base compatible: `qcom,kona` vs `xiaomi,thyme`/`qcom,sm8250`.
5. `/memory` placeholder present on stock base, absent on Mainline thyme/alioth DTS.

Alioth puts board-id on the base DTB, but this repo does **not** show that
Xiaomi ABL consumed that DTB via vendor_boot/dtbo. Stock/Astide document the
protocol thyme ABL used at M0.

**CLASS B — kernel-visible early memory**

reserved-memory: thyme Mainline inherits upstream sm8250.dtsi; stock and
alioth-override maps agree with each other and disagree with upstream.
Post-handoff reference. Not claimed as the 4.7s cause.

**CLASS C — post-entry peripherals**

UART (`uart2` vs alioth `uart6`), USB/UFS/Wi-Fi/display/sound. Needed for a
later server image. Not the current handoff Gate.

Priority: `A >> B >> C`.

## M0 → M1 reinterpretation

Same exact `boot_b`. Only DT context changed.

```text
M0 stock DT:   no ~4.7s timed Fastboot return (within the M0 window)
M1 Mainline DT: 4.821s automatic Fastboot return
M2–M5D:        4.492–4.790s, all sharing M1 DT
M5A stock kernel + stock DT: >12s, no automatic return
```

`UNCONDITIONAL_4P7S_WATCHDOG=REFUTED_BY_CONTROL`. Kernel vs DT is still not
fully isolated (M5A also changed the kernel). Header-field scans under M1 DT
did not move the timer.

CLASS A candidates that can explain ABL taking a different path:

1. Concatenated kona table + 29-entry dtbo replaced by one Mainline FDT +
   one no-op overlay (packaging).
2. board-id `<45 0>` on the *base* DTB, unlike stock base `<0 0>`.
3. Missing `/memory` placeholder on the Mainline DTB.
4. Base compatible / missing kona identity.

Do not conclude which candidate is causal. Do not treat reserved-memory or
UART as the 4.7s explanation.

## Fact gates

```text
R1_DTB_BOOTLOADER_METADATA_DIFFERENCE_FOUND=YES
  # placement: M1 packaged base DTB carries board-id <45 0>;
  # stock/Astide base carries <0 0> and overlay carries <45 0>.
  # values: packaged msm-id/board-id numbers are the correct thyme pair.
  # raw source DTS still lacks both properties.

R1_DT_PACKAGING_DIFFERENCE_FOUND=YES
  # 4-concatenated vendor_boot DTBs vs 1; 29 dtbo entries vs 1.
  # alioth repo: BOOT_PACKAGING_NOT_PRESENT_IN_REPO.

R1_ALIOTH_SUCCESS_HEADER_MATCHES_MAINLINE_STYLE=CONFIG_YES_BINARY_PENDING_GHA
  # CONFIG_EFI_STUB=y, EFI_ZBOOT n. Image bytes: GHA dispatch.

R1_NO_DECISIVE_REFERENCE_DIFFERENCE=NO
```

## Recommended next stage — executed as M5E

```text
RECOMMENDED=M5E_DT_CONTEXT_CROSSOVER_TRUE_DEVICE
EXECUTED=YES
FINAL_GATE=MAINLINE_V2_M5E_STOCK_DT_SUPPRESSES_4P7S
```

M1 packaged selector *values* match thyme (`356/0x20001`, `45 0`) and follow
the alioth-on-base *pattern*. That is not “missing IDs” versus alioth.
M5E kept exact M5D boot and swapped only M1 DT → Stock DT. The ~4.7s
automatic Fastboot return was suppressed (`>12s`). Image-header-as-sole-cause
is not supported. Next isolation, not executed:
`MAINLINE_V2_M5F_DT_CONTEXT_FACTORIAL_ISOLATION`.

Paused alternatives remain paused:

- `M5E_CORRECTED_DTB_METADATA_CONTROL_CI` — CI-only vendor_boot whose base
  DTB uses stock-like `board-id <0 0>` and keeps the no-op overlay at `<45 0>`.
- `M5F_M0_VS_M5D_BOOT_AUDIT` — not indicated; crossover suppressed 4.7s.
- Image header patches — still forbidden.

## Alioth vs thyme server leftovers (CLASS C)

Safe to reuse later, not now: GENI UART, DWC3 HS gadget, UFS QCOM+QMP,
QCA6390/ATH11K. Not safe to copy: alioth board-id 44, uart6, PM8008 camera
PMIC, panel/touch, reserved-memory overrides without a thyme stock check.
