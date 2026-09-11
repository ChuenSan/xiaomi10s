#!/usr/bin/env bash
# M5J single Slot B boot observation on macOS. Observation only: never flashes,
# never recovers, never boots B twice.
#
# After the 12s primary window we stop. We never poll for a later Fastboot and
# never call such an arrival an automatic return; a later Fastboot is only ever
# user manual physical recovery.
set -euo pipefail

FASTBOOT="${FASTBOOT:-fastboot}"
POLL_SECONDS="${POLL_SECONDS:-0.25}"
DISAPPEAR_TIMEOUT_SECONDS="${DISAPPEAR_TIMEOUT_SECONDS:-10}"
HARD_WINDOW_SECONDS="${HARD_WINDOW_SECONDS:-12}"

now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
present() {
	"$FASTBOOT" devices 2>/dev/null | awk '$2 == "fastboot" { found = 1 } END { exit !found }'
}
getvar() {
	"$FASTBOOT" getvar "$1" 2>&1 | sed -n "s/^$1: \(.*\)$/\1/p" | head -n1
}
before() {
	python3 - "$1" <<'PY'
import sys
import time
sys.exit(0 if time.time() < float(sys.argv[1]) else 1)
PY
}
wait_until() {
	local deadline="$1" want_present="$2"
	while before "$deadline"; do
		if [ "$want_present" = yes ] && present; then return 0; fi
		if [ "$want_present" = no ] && ! present; then return 0; fi
		sleep "$POLL_SECONDS"
	done
	return 1
}
fail() { echo "OBSERVE-FAIL: $*" >&2; exit 1; }
print_timestamp() {
	echo "$1=$2"
	python3 - "$1" "$2" <<'PY'
import datetime
import sys
label, value = sys.argv[1:]
stamp = datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
print(f"{label}_ISO={stamp.isoformat(timespec='milliseconds').replace('+00:00', 'Z')}")
PY
}

present || fail "Fastboot device is not present"
echo "PRE_CURRENT_SLOT=$(getvar current-slot)"
echo "PRE_SLOT_RETRY_COUNT_B=$(getvar slot-retry-count:b)"
echo "PRE_SLOT_UNBOOTABLE_B=$(getvar slot-unbootable:b)"

cat <<'EOF'
== thyme Mainline V2 M5J host observation ==
TEST: MAINLINE_V2_M5J_DTBO_STOCK_TABLE_NOOP_PAYLOAD_TRUE_DEVICE_CONTROL
REFERENCE M5H: Stock 29-entry dtbo + Stock thyme entry21 -> >12s
TEST: same 29-entry Stock table + M1 no-op entry21 payload
ONLY WRITE THIS ROUND: dtbo_b (already done)
DO NOT WRITE: boot_b vendor_boot_b vbmeta* firmware ANY *_a
SLOT B: one boot only. SLOT A: no write.
USB evidence: Fastboot identity only (18d1:d00d)
HARD WINDOW: 12 seconds
If no automatic return: stop. User manual physical Fastboot recovery only.
EOF

echo "issuing exactly one: fastboot set_active b"
"$FASTBOOT" set_active b
POST_SLOT="$(getvar current-slot)"
POST_RETRY_B="$(getvar slot-retry-count:b)"
POST_UNBOOTABLE_B="$(getvar slot-unbootable:b)"
echo "POST_CURRENT_SLOT=${POST_SLOT:-UNKNOWN}"
echo "POST_SLOT_RETRY_COUNT_B=${POST_RETRY_B:-UNKNOWN}"
echo "POST_SLOT_UNBOOTABLE_B=${POST_UNBOOTABLE_B:-UNKNOWN}"
[ "$POST_SLOT" = b ] || fail "current-slot must be b, got ${POST_SLOT:-UNKNOWN}"
[ "${POST_UNBOOTABLE_B:-no}" = no ] || fail "slot-unbootable:b must be no, got ${POST_UNBOOTABLE_B:-UNKNOWN}"

echo "HARD_WINDOW_SECONDS=$HARD_WINDOW_SECONDS"
echo "SECOND_B_BOOT_FORBIDDEN=YES"
echo "issuing exactly one: fastboot reboot"
"$FASTBOOT" reboot

DEADLINE="$(python3 - "$DISAPPEAR_TIMEOUT_SECONDS" <<'PY'
import sys, time
print(time.time() + float(sys.argv[1]))
PY
)"
if ! wait_until "$DEADLINE" no; then
	echo "T_DISAPPEAR=NOT_OBSERVED"
	echo "AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=UNKNOWN"
	echo "MANUAL_RECOVERY_REQUIRED=NO"
	echo "FINAL_GATE=MAINLINE_V2_M5J_NOT_SAFE"
	exit 0
fi
T_DISAPPEAR="$(now)"
print_timestamp "FASTBOOT_DISAPPEAR_TIMESTAMP" "$T_DISAPPEAR"

DEADLINE="$(python3 - "$T_DISAPPEAR" "$HARD_WINDOW_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
if wait_until "$DEADLINE" yes; then
	T_REAPPEAR="$(now)"
	print_timestamp "FASTBOOT_REAPPEAR_TIMESTAMP" "$T_REAPPEAR"
	python3 - "$T_DISAPPEAR" "$T_REAPPEAR" <<'PY'
import sys
elapsed = float(sys.argv[2]) - float(sys.argv[1])
print(f"FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR={elapsed:.3f}")
print("AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=YES")
print("MANUAL_RECOVERY_REQUIRED=NO")
print("MANUAL_RECOVERY=NO")
if 4.3 <= elapsed <= 5.3:
    print("M5J_NOOP_PAYLOAD_EFFECT=YES")
    print("M1_NOOP_PAYLOAD_ALONE_SUFFICIENT=YES")
    print("M1_NOOP_PAYLOAD_SUFFICIENT_ON_STOCK_TABLE=STRONGLY_SUPPORTED")
    print("STOCK_DTBO_CONTAINER_WITH_NOOP_PAYLOAD_COMPATIBLE=NOT_SUPPORTED")
    print("ONE_ENTRY_DTBO_PACKAGING_CAUSAL_FAMILY=NOT_ESTABLISHED")
    print("FINAL_GATE=MAINLINE_V2_M5J_NOOP_PAYLOAD_RESTORES_4P7S")
elif elapsed <= 12.0:
    print("M5J_NOOP_PAYLOAD_EFFECT=INCONCLUSIVE")
    print("M1_NOOP_PAYLOAD_ALONE_SUFFICIENT=INCONCLUSIVE")
    print("STOCK_DTBO_CONTAINER_WITH_NOOP_PAYLOAD_COMPATIBLE=INCONCLUSIVE")
    print("ONE_ENTRY_DTBO_PACKAGING_CAUSAL_FAMILY=INCONCLUSIVE")
    print("FINAL_GATE=MAINLINE_V2_M5J_DTBO_CONTROL_INCONCLUSIVE")
else:
    print("M5J_NOOP_PAYLOAD_EFFECT=INCONCLUSIVE")
    print("FINAL_GATE=MAINLINE_V2_M5J_DTBO_CONTROL_INCONCLUSIVE")
PY
else
	echo "FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED"
	echo "AUTOMATIC_FASTBOOT_REAPPEAR_WITHIN_12S=NO"
	echo "PRIMARY_OBSERVATION=>12s"
	echo "MANUAL_FASTBOOT_RECOVERY_AFTER_WINDOW=REQUIRED"
	echo "MANUAL_RECOVERY_REQUIRED=YES"
	echo "M5J_NOOP_PAYLOAD_EFFECT=NO"
	echo "M1_NOOP_PAYLOAD_ALONE_SUFFICIENT=NO"
	echo "STOCK_DTBO_CONTAINER_WITH_NOOP_PAYLOAD_COMPATIBLE=STRONGLY_SUPPORTED"
	echo "ONE_ENTRY_DTBO_PACKAGING_CAUSAL_FAMILY=STRONGLY_SUPPORTED"
	echo "FINAL_GATE=MAINLINE_V2_M5J_STOCK_TABLE_NOOP_SUPPRESSES_4P7S"
	echo "STOP: no further polling. Any later Fastboot is user manual recovery."
	echo "Do not ordinary reboot. Do not boot B again."
fi

echo
echo "Observation complete. SECOND_B_BOOT_FORBIDDEN=YES"
