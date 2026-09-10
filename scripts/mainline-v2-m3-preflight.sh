#!/usr/bin/env bash
# Mainline V2 M3 Fastboot preflight. READ-ONLY: no flash, slot change, or reboot.
set -euo pipefail

ART_DIR="${1:-$PWD/artifacts}"
FASTBOOT="${FASTBOOT:-fastboot}"
IMAGE_NAME="mainline-v2-m3-early-short-delay-boot-v3.img"

fail() { echo "PREFLIGHT-FAIL: $*" >&2; exit 1; }
getvar() {
	"$FASTBOOT" getvar "$1" 2>&1 | sed -n "s/^$1: \(.*\)$/\1/p" | head -n1
}

"$FASTBOOT" devices 2>/dev/null | awk '$2 == "fastboot" { found = 1 } END { exit !found }' || \
	fail "Fastboot device unreachable"

PRODUCT="$(getvar product)"
UNLOCKED="$(getvar unlocked)"
CURRENT="$(getvar current-slot)"
SNAPSHOT="$(getvar snapshot-update-status)"
BATTERY="$(getvar battery-soc-ok)"
HAS_BOOT="$(getvar has-slot:boot)"
HAS_VENDOR_BOOT="$(getvar has-slot:vendor_boot)"
HAS_DTBO="$(getvar has-slot:dtbo)"
HAS_VENDOR_BOOT="${HAS_VENDOR_BOOT:-UNKNOWN}"
HAS_DTBO="${HAS_DTBO:-UNKNOWN}"
UNBOOTABLE_B="$(getvar slot-unbootable:b)"
RETRY_B="$(getvar slot-retry-count:b)"

cat <<EOF
== thyme Mainline V2 M3 Fastboot preflight (READ-ONLY) ==
product                 = ${PRODUCT:-UNKNOWN}
unlocked                = ${UNLOCKED:-UNKNOWN}
current-slot            = ${CURRENT:-UNKNOWN}
snapshot-update-status  = ${SNAPSHOT:-UNKNOWN}
battery-soc-ok          = ${BATTERY:-UNKNOWN}
has-slot:boot           = ${HAS_BOOT:-UNKNOWN}
has-slot:vendor_boot    = ${HAS_VENDOR_BOOT:-UNKNOWN}
has-slot:dtbo           = ${HAS_DTBO:-UNKNOWN}
slot-unbootable:b       = ${UNBOOTABLE_B:-UNKNOWN}
slot-retry-count:b      = ${RETRY_B:-UNKNOWN}
EOF

[ "$PRODUCT" = thyme ] || fail "product is not thyme"
[ "$UNLOCKED" = yes ] || fail "bootloader is not unlocked"
[ "$CURRENT" = a ] || fail "current-slot must be a"
[ "$SNAPSHOT" = none ] || fail "snapshot-update-status is not none"
[ "$BATTERY" = yes ] || fail "battery-soc-ok is not yes"
[ "$HAS_BOOT" = yes ] || fail "has-slot:boot is not yes"
case "$HAS_VENDOR_BOOT" in
	yes|UNKNOWN) ;;
	*) fail "unexpected has-slot:vendor_boot=$HAS_VENDOR_BOOT" ;;
esac
case "$HAS_DTBO" in
	yes|UNKNOWN) ;;
	*) fail "unexpected has-slot:dtbo=$HAS_DTBO" ;;
esac

IMAGE="$ART_DIR/$IMAGE_NAME"
MANIFEST="$ART_DIR/SHA256SUMS"
[ -s "$IMAGE" ] || fail "missing $IMAGE"
[ -s "$MANIFEST" ] || fail "missing $MANIFEST"
( cd "$ART_DIR" && sha256sum -c SHA256SUMS ) || fail "artifact SHA256 mismatch"

cat <<'EOF'
TEST: MAINLINE_V2_M3_EARLIEST_ENTRY_SHORT_TIME_SIGNATURE
DELAY: 2 SECONDS
WRITE: boot_b ONLY
KEEP: exact M1 vendor_boot_b and dtbo_b context
KEEP: stock vbmeta_b and vbmeta_system_b
SLOT A: PROTECTED / NO WRITE
USB: Fastboot identity only (18d1:d00d); no gadget/network test
M3_FASTBOOT_PREFLIGHT=PASS
EOF
