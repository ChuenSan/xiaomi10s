# Route A v2 differential matrix — CLOSED

Built only by `.github/workflows/route-a-v2-boot-investigation.yml`.
Do not retune `kernel_addr` / `ramdisk_addr` / `dtb_addr`.
Do not add more v2 variants. `ROUTE_A_REFUTED` (`docs/route-a-report.md`).

| Dir | Change | Device (RAM-only) |
|---|---|---|
| control | baseline v2 | OKAY, ~1 s, Fastboot back, no gadget |
| no-dtb | `dtb_size=0` | OKAY, ~2 s, same class |
| bad-dtb | FDT magic zeroed | OKAY, ~1 s, same class |
| qc-ids | `qcom,msm-id <0x164 0x20001>`, `qcom,board-id <45 0>` | OKAY, ~1 s, same class |
| marker-dtb | unique `/model` | **not run** (needs kernel liveness) |
| cmdline-probe | `route_a_cmdline_probe=1` | **not run** (needs kernel liveness) |
