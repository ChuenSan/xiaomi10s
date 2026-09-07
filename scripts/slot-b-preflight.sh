#!/usr/bin/env bash
# Slot B preflight checker — Xiaomi Mi 10S (thyme*)
# READ-ONLY. No flash/erase/format/set_active/reboot logic exists here.
# Verifies:  fastboot device identity,  unlock state,  slot topology,,
# artifact SHA256s, then prints the Slot A/B protection notice and exits..
#
# Usage:  bash scripts/slot-b-preflight.sh [artifacts-dir]
# Env:   FASTBOOT=...   (default fastboot*
set -euo pipefail

ART_DIR="${1:-$PWD/artifacts}"
FASTBOOT="${FASTBOOT:-fastboot}"

fail() { echo "PREFLIGHT-FAIL:  $*" >&2; exit 1; }

echo "== thyme Slot B preflight (READ-ONLY* =="
"$FASTBOOT" devices >/dev/null 2>&1 || fail "fastboot device unreachable ( bootloader mode required*)"

getvar() { "$FASTBOOT" getvar "$1" 2>/dev/null | sed -n "s/^$1: \(.*\)$/\1/p"; }

PRODUCT=$(getvar product)
UNLOCKED=$(getvar unlocked)
CURRENT=$(getvar current-slot)
SLOT_COUNT=$(getvar slot-count)
HAS_BOOT=$(getvar has-slot:boot)
HAS_VB=$(getvar has-slot:vendor_boot)
HAS_DTBO=$(getvar has-slot:dtbo)

echo "product        = ${PRODUCT:-UNKNOWN}"
echo "unlocked       = ${UNLOCKED:-UNKNOWN}"
echo "current-slot    = ${CURRENT:-UNKNOWN}"
echo "slot-count      = ${SLOT_COUNT:-UNKNOWN}"
echo "has-slot:boot            = ${HAS_BOOT:-UNKNOWN}"
echo "has-slot:vendor_boot     = ${HAS_VB:-UNKNOWN}"
echo "has-slot:dtbo            = ${HAS_DTBO:-UNKNOWN}"

[ "$PRODUCT"      = "thyme" ] || fail "product is not thyme"
[ "$UNLOCKED"     = "yes"  ] || fail "bootloader not unlocked"
[ "$SLOT_COUNT"   = "2"    ] || fail "slot-count != 2"
[ "$HAS_BOOT"     = "yes"  ] || fail "has-slot:boot != yes"
[ "$HAS_VB"       = "yes"  ] || fail "has-slot:vendor_boot != yes"
[ "$HAS_DTBO"     = "yes"  ] || fail "has-slot:dtbo != yes"

echo "== artifact SHA256 check =="
MANIFEST="${ART_DIR}/SHA256SUMS"
[ -f "$MANIFEST" ] || fail "missing artifact manifest:  $MANIFEST"
( cd "$ART_DIR" && sha256sum -c "$MANIFEST" 2>/dev/null ) \
	|| fail "artifact hash mismatch"

echo "===================================================================="
echo "  SLOT A:  PROTECTED — DO NOT WRITE"
echo "  SLOT B:  EXPERIMENT TARGET"
echo
echo "  Preflight PASSED.  Ready for gated, explicit-_b writes"
echo "  ( see docs/slot-b-first-boot-runbook.md *."
echo "===================================================================="