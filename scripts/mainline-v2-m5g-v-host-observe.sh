#!/usr/bin/env bash
# Observe the single M5G-V Slot B boot on macOS.
# Selects Slot B, issues exactly one fastboot reboot. Never flashes.
set -euo pipefail

FASTBOOT="${FASTBOOT:-fastboot}"
POLL_SECONDS="${POLL_SECONDS:-0.25}"
DISAPPEAR_TIMEOUT_SECONDS="${DISAPPEAR_TIMEOUT_SECONDS:-10}"
HARD_WINDOW_SECONDS="${HARD_WINDOW_SECONDS:-12}"
REFERENCE_B_SECONDS="${REFERENCE_B_SECONDS:-5.008}"

now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
present() {
	"$FASTBOOT" devices 2>/dev/null | awk '$2 == "fastboot" { found = 1 } END { exit !found }'
}
getvar() {
	"$FASTBOOT" getvar "$1" 2>&1 | sed -n "s/^$1: \(.*\)$/\1/p" | head -n1
}
wait_until() {
	local deadline="$1" want_present="$2"
	while python3 - "$deadline" <<'PY'
import sys
import time
sys.exit(0 if time.time() < float(sys.argv[1]) else 1)
PY
	do
		if [ "$want_present" = yes ] && present; then
			return 0
		fi
		if [ "$want_present" = no ] && ! present; then
			return 0
		fi
		sleep "$POLL_SECONDS"
	done
	return 1
}
fail() { echo "OBSERVE-FAIL: $*" >&2; exit 1; }
print_timestamp() {
	local label="$1" value="$2"
	echo "${label}=${value}"
	python3 - "$label" "$value" <<'PY'
import datetime
import sys
label, value = sys.argv[1:]
stamp = datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
print(f"{label}_ISO={stamp.isoformat(timespec='milliseconds').replace('+00:00', 'Z')}")
PY
}

present || fail "Fastboot device is not present"
PRE_SLOT="$(getvar current-slot)"
RETRY_B="$(getvar slot-retry-count:b)"
UNBOOTABLE_B="$(getvar slot-unbootable:b)"
echo "PRE_CURRENT_SLOT=${PRE_SLOT:-UNKNOWN}"
echo "PRE_SLOT_RETRY_COUNT_B=${RETRY_B:-UNKNOWN}"
echo "PRE_SLOT_UNBOOTABLE_B=${UNBOOTABLE_B:-UNKNOWN}"

cat <<'EOF'
== thyme Mainline V2 M5G-V host observation ==
TEST: MAINLINE_V2_M5G_V_SINGLE_STOCK_DTB_TRUE_DEVICE_CONTROL
REFERENCE CELL B: M5D boot + M1 single Mainline DTB vendor_boot + Stock dtbo -> 5.008s
TEST: SAME M5D boot + single exact Stock DTB0 vendor_boot + SAME Stock dtbo
SLOT B: one boot only
SLOT A: no write, no slot mutation beyond active selection
USB evidence: Fastboot identity only (18d1:d00d)
HARD WINDOW: 12 seconds
If no automatic return: hardware Vol-Down+Power to Fastboot. Do not ordinary reboot.
EOF

echo "issuing exactly one: fastboot set_active b"
"$FASTBOOT" set_active b
POST_SLOT="$(getvar current-slot)"
POST_RETRY_B="$(getvar slot-retry-count:b)"
POST_UNBOOTABLE_B="$(getvar slot-unbootable:b)"
echo "POST_CURRENT_SLOT=${POST_SLOT:-UNKNOWN}"
echo "POST_SLOT_RETRY_COUNT_B=${POST_RETRY_B:-UNKNOWN}"
echo "POST_SLOT_UNBOOTABLE_B=${POST_UNBOOTABLE_B:-UNKNOWN}"
[ "$POST_SLOT" = b ] || fail "current-slot must be b after set_active, got ${POST_SLOT:-UNKNOWN}"
[ "${POST_UNBOOTABLE_B:-no}" = no ] || fail "slot-unbootable:b must be no, got ${POST_UNBOOTABLE_B:-UNKNOWN}"

echo "BASELINE_CELL_B_SECONDS=$REFERENCE_B_SECONDS"
echo "HARD_WINDOW_SECONDS=$HARD_WINDOW_SECONDS"
echo "SECOND_B_BOOT_FORBIDDEN=YES"

echo "issuing exactly one: fastboot reboot"
T_REBOOT_COMMAND_START="$(now)"
"$FASTBOOT" reboot
T_REBOOT_COMMAND_DONE="$(now)"
echo "FASTBOOT_REBOOT_COMMAND_DONE=$T_REBOOT_COMMAND_DONE"

T_DISAPPEAR_DEADLINE="$(python3 - "$T_REBOOT_COMMAND_DONE" "$DISAPPEAR_TIMEOUT_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
if wait_until "$T_DISAPPEAR_DEADLINE" no; then
	T_DISAPPEAR="$(now)"
else
	echo "FASTBOOT_USB_DISAPPEAR=NOT_OBSERVED"
	echo "T_DISAPPEAR=NOT_OBSERVED"
	echo "AUTOMATIC_FASTBOOT_REAPPEAR=UNKNOWN"
	echo "M5G_V_4P7S_RETURN_SUPPRESSED=UNKNOWN"
	echo "MANUAL_RECOVERY_REQUIRED=NO"
	echo "FINAL_GATE=MAINLINE_V2_M5G_V_INCONCLUSIVE"
	exit 0
fi
print_timestamp "FASTBOOT_DISAPPEAR_TIMESTAMP" "$T_DISAPPEAR"
echo "T_DISAPPEAR=$T_DISAPPEAR"

echo "waiting only through the hard 12-second observation window"
T_REAPPEAR_DEADLINE="$(python3 - "$T_DISAPPEAR" "$HARD_WINDOW_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
if wait_until "$T_REAPPEAR_DEADLINE" yes; then
	T_REAPPEAR="$(now)"
	print_timestamp "FASTBOOT_REAPPEAR_TIMESTAMP" "$T_REAPPEAR"
	echo "T_REAPPEAR=$T_REAPPEAR"
else
	T_REAPPEAR=""
	echo "FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED"
	echo "T_REAPPEAR=NOT_OBSERVED"
fi

if [ -n "$T_REAPPEAR" ]; then
	python3 - "$T_DISAPPEAR" "$T_REAPPEAR" "$REFERENCE_B_SECONDS" <<'PY'
import sys
elapsed = float(sys.argv[2]) - float(sys.argv[1])
delta = elapsed - float(sys.argv[3])
print(f"FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR={elapsed:.3f}")
print(f"M5G_V_ELAPSED={elapsed:.3f}")
print(f"M5G_V_DELTA_FROM_CELL_B={delta:.3f}")
if 4.3 <= elapsed <= 5.3:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("M5G_V_4P7S_RETURN_SUPPRESSED=NO")
    print("V_SINGLE_STOCK_DTB_EFFECT=NO")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M5G_V_STOCK_DTB_NO_EFFECT")
elif elapsed <= 12.0:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("M5G_V_4P7S_RETURN_SUPPRESSED=UNKNOWN")
    print("V_SINGLE_STOCK_DTB_EFFECT=INCONCLUSIVE")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M5G_V_INCONCLUSIVE")
else:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("M5G_V_4P7S_RETURN_SUPPRESSED=UNKNOWN")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M5G_V_INCONCLUSIVE")
PY
else
	echo "AUTOMATIC_FASTBOOT_REAPPEAR=NO"
	echo "M5G_V_4P7S_RETURN_SUPPRESSED=YES"
	echo "V_SINGLE_STOCK_DTB_EFFECT=YES"
	echo "MANUAL_RECOVERY_REQUIRED=YES"
	echo "FINAL_GATE=MAINLINE_V2_M5G_V_STOCK_DTB_SUPPRESSES_4P7S"
	echo "Recover with hardware Vol-Down+Power to Fastboot. Do not ordinary reboot."
fi

echo
echo "Observation complete. SECOND_B_BOOT_FORBIDDEN=YES"
echo "Do not boot Slot B again. Select A from Fastboot."
