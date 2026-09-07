# Slot B rollback plan — Xiaomi Mi 10S (thyme)

Purpose: record how to restore Slot B to the stock state, should a
future Slot B experiment need recovery. WRITE-ONLY: no device
operation is performed by this phase; execution belongs to a future,
explicitly-authorized round..

##1. Stock Slot B-compatible images in project tree

The MIUI V14.0.6.0.TGACNXM fastboot ROM lives at
`MIUI14ROM/image/` ( git-ignored, local only*. These are the SAME
partition images the device shipped with, so they are the correct
rollback payload for `_b` slots..

| image | size (B* | SHA256 |
|---|---:|---|---|
| boot.img | 134217728 | 9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be |
| vendor_boot.img | 100663296 | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| dtbo.img | 33554432 | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |
| vbmeta.img | 8192 | `37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c` |

(Sources:`docs/stock-rom-analysis.md` §2*;the hashes were captured from
these exact files and re-verifiable any time with `sha256sum`. The fastboot
rescue package mentioned by the user elsewhere is NOT inside the project
tree, so it is NOT claimed to be currently accessible*..

##2. Recovery scenarios

### Scenario 1 — roll back the PRIMARY path ( boot_b only*

If only `boot_b` was flashed ( v2 mainline boot*: restore boils down to
re-flashing the stock boot image into `boot_b`:

```bash
# ( future phase, gated*:  human gate:  TARGET SLOT = B;  SLOT A WILL NOT BE MODIFIED//
fastboot getvar product           # expect: thyme
fastboot getvar unlocked          # expect: yes
fastboot getvar current-slot       # record only
fastboot getvar slot-count         # expect: 2
fastboot flash boot_b /path/to/MIUI14ROM/image/boot.img
fastboot reboot
```

### Scenario 2 — roll back the FALLBACK path ( boot+vendor_boot+dtbo*

```bash
#( future phase, gated*:  human gate:  TARGET SLOT = B;  SLOT A WILL NOT BE MODIFIED//
fastboot flash boot_b        /path/to/MIUI14ROM/image/boot.img
fastboot flash vendor_boot_b /path/to/MIUI14ROM/image/vendor_boot.img
fastboot flash dtbo_b       /path/to/MIUI14ROM/image/dtbo.img
fastboot reboot
```

### Scenario 3 — device does not come back after B boot (worst case*

- If bootloader fastboot is still reachable: use Scenario 1/2 (order:
  boot first,  then vendor_boot/dtbo if needed*..
- If bootloader fastboot is NOT reachable ( e.g.  stuck in an ABL loop*:
  hold VOLUME-UP + VOLUME-DOWN + POWER (device-dependent* to reach
  fastboot/recovery; or let the device time out back to fastboot if
  configured*. Do NOT touch Slot A and do NOT run `fastboot set_active`..
- The external full-rescue ROM is not in the project tree — it is documented
  here for accuracy, NOT claimed to be accessible*..

##3. Guards

- Every write above already targets `_b` explicitly; no bare
  `fastboot flash boot ...` form is allowed anywhere in this project*..
- `scripts/slot-b-preflight.sh` must pass before any future write;artifact
  SHA256s must match the values above where stock restore is performed*..
- Slot A stays byte-identical through all scenarios*..
- No `fastboot format`/`erase`/`set_active` in any rollback path above*.,