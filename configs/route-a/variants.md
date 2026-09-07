# Route A v2 differential matrix

Built only by `.github/workflows/route-a-v2-boot-investigation.yml`.

Do not retune `kernel_addr` / `ramdisk_addr` / `dtb_addr` in these variants.

| Dir | Change | Why |
|---|---|---|
| control | same recipe as first `experimental-boot-v2.img` | baseline |
| no-dtb | `dtb_size=0`, DTB pages dropped | ABL `DTB Image not present` vs later fail |
| bad-dtb | same size, FDT magic zeroed | magic parse vs msm-id |
| marker-dtb | `/model` unique string only | observe DTB if kernel lives |
| qc-ids | add `qcom,msm-id <0x164 0x20001>` and `qcom,board-id <45 0>` | ABL GetSocDtb keys; no hardware nodes |
| cmdline-probe | `route_a_cmdline_probe=1` | v2 cmdline vs ABL-generated |

APPENDED-DTB-to-kernel is not in this matrix (`docs/route-a-abl-evidence.md` §9).
x0 probe is deferred.
