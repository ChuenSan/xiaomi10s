#!/usr/bin/env bash
# USB Stage1 device-observe preflight — READ-ONLY. No flash/erase/format/set_active/reboot.
set -euo pipefail
ART_DIR="${1:-$PWD/artifacts}"
FASTBOOT="${FASTBOOT:-fastboot}"
fail() { echo "PREFLIGHT-FAIL: $*" >&2; exit 1; }

echo "== thyme stock-kernel USB Stage1 device-observe preflight (READ-ONLY) =="
"$FASTBOOT" devices >/dev/null 2>&1 || fail "fastboot device unreachable"

getvar() { "$FASTBOOT" getvar "$1" 2>&1 | sed -n "s/^$1: \(.*\)$/\1/p" | head -n1; }

PRODUCT=$(getvar product)
UNLOCKED=$(getvar unlocked)
CURRENT=$(getvar current-slot)
UNBOOTABLE_B=$(getvar slot-unbootable:b)
SNAPSHOT=$(getvar snapshot-update-status)
BATTERY=$(getvar battery-soc-ok)

echo "product                 = ${PRODUCT:-UNKNOWN}"
echo "unlocked                = ${UNLOCKED:-UNKNOWN}"
echo "current-slot            = ${CURRENT:-UNKNOWN}"
echo "slot-successful:b       = $(getvar slot-successful:b)"
echo "slot-unbootable:b       = ${UNBOOTABLE_B:-UNKNOWN}"
echo "slot-retry-count:b      = $(getvar slot-retry-count:b)"
echo "snapshot-update-status  = ${SNAPSHOT:-UNKNOWN}"
echo "battery-soc-ok          = ${BATTERY:-UNKNOWN}"

[ "$PRODUCT" = thyme ] || fail "product is not thyme"
[ "$UNLOCKED" = yes ] || fail "bootloader not unlocked"
[ "$CURRENT" = a ] || fail "current-slot must be a"
[ "$SNAPSHOT" = none ] || fail "snapshot-update-status != none"
[ "$UNBOOTABLE_B" = no ] || fail "slot-unbootable:b != no"
[ "$BATTERY" = yes ] || fail "battery-soc-ok != yes"

IMG="$ART_DIR/stock-kernel-usb-stage1-device-observe-boot-v3.img"
MANIFEST="$ART_DIR/SHA256SUMS"
[ -f "$IMG" ] || fail "missing $IMG"
[ -f "$MANIFEST" ] || fail "missing $MANIFEST"
( cd "$ART_DIR" && sha256sum -c SHA256SUMS )

echo
echo "USB STAGE1 DEVICE NETDEV OBSERVE"
echo
echo "TEST:"
echo "STOCK_KERNEL_USB_STAGE1_DEVICE_NETDEV_OBSERVE"
echo
echo "WRITE:"
echo "boot_b ONLY"
echo
echo "SLOT A:"
echo "NO WRITE"
echo
echo "vendor_boot_b:"
echo "NO WRITE"
echo
echo "dtbo_b:"
echo "NO WRITE"
echo
echo "vbmeta_b:"
echo "NO WRITE"
echo
echo "NO:"
echo "IFF_UP / IP / route / ping / DHCP / Stage1B"
echo
echo "EXPECTED:"
echo "custom gadget 1d6b:0104 thyme-mainline / Stock Kernel USB Stage1 Device Observe / THYME-USB1DEV"
echo "hold ~30s then automatic Fastboot return"
echo
echo "Preflight PASSED (no writes performed)."
