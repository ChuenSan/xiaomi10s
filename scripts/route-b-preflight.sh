#!/usr/bin/env bash
# Route B preflight — READ-ONLY. No flash/erase/format/set_active/reboot.
set -euo pipefail
ART_DIR="${1:-$PWD/artifacts}"
FASTBOOT="${FASTBOOT:-fastboot}"
fail() { echo "PREFLIGHT-FAIL: $*" >&2; exit 1; }

echo "== thyme Route B preflight (READ-ONLY) =="
"$FASTBOOT" devices >/dev/null 2>&1 || fail "fastboot device unreachable"

getvar() { "$FASTBOOT" getvar "$1" 2>/dev/null | sed -n "s/^$1: \(.*\)$/\1/p"; }

PRODUCT=$(getvar product)
UNLOCKED=$(getvar unlocked)
CURRENT=$(getvar current-slot)
SLOT_COUNT=$(getvar slot-count)
HAS_BOOT=$(getvar has-slot:boot)
HAS_VB=$(getvar has-slot:vendor_boot)
HAS_DTBO=$(getvar has-slot:dtbo)
echo "product              = ${PRODUCT:-UNKNOWN}"
echo "unlocked             = ${UNLOCKED:-UNKNOWN}"
echo "current-slot         = ${CURRENT:-UNKNOWN}"
echo "slot-count           = ${SLOT_COUNT:-UNKNOWN}"
echo "has-slot:boot        = ${HAS_BOOT:-UNKNOWN}"
echo "has-slot:vendor_boot = ${HAS_VB:-UNKNOWN}"
echo "has-slot:dtbo        = ${HAS_DTBO:-UNKNOWN}"
echo "slot-successful:b    = $(getvar slot-successful:b)"
echo "slot-unbootable:b    = $(getvar slot-unbootable:b)"
echo "slot-retry-count:b   = $(getvar slot-retry-count:b)"
echo "snapshot-update-status = $(getvar snapshot-update-status)"

[ "$PRODUCT" = thyme ] || fail "product is not thyme"
[ "$UNLOCKED" = yes ] || fail "bootloader not unlocked"
[ "$SLOT_COUNT" = 2 ] || fail "slot-count != 2"
[ "$HAS_BOOT" = yes ] || fail "has-slot:boot != yes"
[ "$HAS_VB" = yes ] || fail "has-slot:vendor_boot != yes"
[ "$HAS_DTBO" = yes ] || fail "has-slot:dtbo != yes"

MANIFEST="${ART_DIR}/SHA256SUMS"
[ -f "$MANIFEST" ] || fail "missing $MANIFEST"
( cd "$ART_DIR" && sha256sum -c SHA256SUMS )

echo
echo "TARGET SLOT: B"
echo "SLOT A: PROTECTED"
echo "Preflight PASSED (no writes performed)."
