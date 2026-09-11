#!/usr/bin/env bash
# M5J post-observation recovery: restore active slot A. Never boots B again.
#
# If the 12s window produced no automatic return, Fastboot presence at this point
# is the result of the user's manual physical recovery. That arrival time is a
# MANUAL_RECOVERY time and is recorded as such - never as an automatic return.
set -euo pipefail

FASTBOOT="${FASTBOOT:-fastboot}"
MANUAL_RECOVERY="${MANUAL_RECOVERY:-NO}"

getvar() {
	"$FASTBOOT" getvar "$1" 2>&1 | sed -n "s/^$1: \(.*\)$/\1/p" | head -n1
}
present() {
	"$FASTBOOT" devices 2>/dev/null | awk '$2 == "fastboot" { found = 1 } END { exit !found }'
}

present || { echo "RECOVERY-FAIL: Fastboot device is not present" >&2; exit 1; }

echo "MANUAL_RECOVERY=$MANUAL_RECOVERY"
echo "PRE_CURRENT_SLOT=$(getvar current-slot)"
echo "PRE_SLOT_RETRY_COUNT_B=$(getvar slot-retry-count:b)"
echo "PRE_SLOT_UNBOOTABLE_B=$(getvar slot-unbootable:b)"
echo "PRE_SLOT_SUCCESSFUL_B=$(getvar slot-successful:b)"

echo "issuing: fastboot set_active a"
"$FASTBOOT" set_active a
POST_SLOT="$(getvar current-slot)"
echo "POST_CURRENT_SLOT=${POST_SLOT:-UNKNOWN}"
[ "$POST_SLOT" = a ] || { echo "RECOVERY-FAIL: current-slot must be a, got ${POST_SLOT:-UNKNOWN}" >&2; exit 1; }

echo "issuing: fastboot reboot"
"$FASTBOOT" reboot
echo "RECOVERY_SET_ACTIVE_A_DONE=YES"
echo "SECOND_B_BOOT_FORBIDDEN=YES"
