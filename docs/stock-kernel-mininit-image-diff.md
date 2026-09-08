# stock vs stock-kernel-mininit boot.img

Input stock boot.img SHA256: `9d8c12c529b3df74ab8eea68b15e4284a2b1fa0c4d4c5572b986df9d9ce3e9be`
Control image: `stock-kernel-mininit-boot-v3.img`

| Field | Stock | Control | Match |
|---|---|---|---|
| header version | 3 | 3 | YES |
| kernel size | 52654096 | 52654096 | YES |
| ramdisk size | 19729764 | 1187476 | NO (intentional) |
| os version | 13.0.0 | 13.0.0 | YES |
| os patch level | 2023-09 | 2023-09 | YES |
| cmdline | `` | `` | YES |
| kernel SHA256 | `85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a` | `85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a` | YES |
| ramdisk SHA256 | `a6fdec8e681e2c89640e9eac751faed0a9dec238b038505279920cf3f97cb496` | `580d971938fb616f18acd5d9dd005ccf8ed38b1b3ae0c2738d101cc93fde9b7f` | NO (intentional) |
| total image size | 134217728 | 53850112 | NO (expected) |

ONLY INTENTIONAL PAYLOAD CHANGE:
generic ramdisk

Expected non-payload differences (not a STOP):

- ramdisk size/hash: Android first-stage ramdisk replaced by BusyBox mininit
- total image size: stock is partition-padded (128 MiB) with AVB footer;
  control is unpadded mkbootimg output without AVB footer.
  Unlocked device + stock `vbmeta_b` flags=2 does not require a boot footer.

If kernel SHA256, header version, os version, os patch level, or cmdline
had drifted, this script would have failed with ONLY_RAMDISK_CHANGED.

Gadget class: **NCM** (stock `kona-perf` has `CONFIG_USB_CONFIGFS_NCM=y`
and does not enable ECM). VID/PID `0x1d6b:0x0104` Linux Foundation.
