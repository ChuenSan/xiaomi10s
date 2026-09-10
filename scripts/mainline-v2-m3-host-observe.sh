#!/usr/bin/env bash
# Observe the single Mainline V2 M3 Slot B boot on macOS.
# This script issues exactly one `fastboot reboot`; it never flashes or changes slots.
set -euo pipefail

FASTBOOT="${FASTBOOT:-fastboot}"
POLL_SECONDS="${POLL_SECONDS:-0.25}"
DISAPPEAR_TIMEOUT_SECONDS="${DISAPPEAR_TIMEOUT_SECONDS:-10}"
MIN_WINDOW_SECONDS="${MIN_WINDOW_SECONDS:-15}"
MAX_WINDOW_SECONDS="${MAX_WINDOW_SECONDS:-60}"
M1_REFERENCE_SECONDS="${M1_REFERENCE_SECONDS:-4.821}"
M2_REFERENCE_SECONDS="${M2_REFERENCE_SECONDS:-4.598}"
BASELINE_MEAN_SECONDS="${BASELINE_MEAN_SECONDS:-4.710}"

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
CURRENT_SLOT="$(getvar current-slot)"
[ "$CURRENT_SLOT" = b ] || fail "current-slot must be b, got ${CURRENT_SLOT:-UNKNOWN}"

cat <<'EOF'
== thyme Mainline V2 M3 host observation ==
TEST: MAINLINE_V2_M3_EARLIEST_ENTRY_SHORT_TIME_SIGNATURE
SLOT B: one boot only
SLOT A: protected; no write or slot mutation by this script
USB evidence: Fastboot identity only (18d1:d00d); no network evidence
EOF

echo "current-slot=$CURRENT_SLOT"
echo "M1_REFERENCE_SECONDS=$M1_REFERENCE_SECONDS"
echo "M2_REFERENCE_SECONDS=$M2_REFERENCE_SECONDS"
echo "BASELINE_MEAN_SECONDS=$BASELINE_MEAN_SECONDS"
echo "MIN_WINDOW_SECONDS=$MIN_WINDOW_SECONDS"
echo "MAX_WINDOW_SECONDS=$MAX_WINDOW_SECONDS"

echo "issuing exactly one: fastboot reboot"
T_REBOOT_COMMAND_START="$(now)"
"$FASTBOOT" reboot
T_REBOOT_COMMAND_DONE="$(now)"
echo "FASTBOOT_REBOOT_COMMAND_DONE=$T_REBOOT_COMMAND_DONE"
python3 - "$T_REBOOT_COMMAND_START" "$T_REBOOT_COMMAND_DONE" <<'PY'
import sys
print(f"FASTBOOT_REBOOT_COMMAND_DURATION={float(sys.argv[2]) - float(sys.argv[1]):.3f}")
PY

T_DISAPPEAR_DEADLINE="$(python3 - "$T_REBOOT_COMMAND_DONE" "$DISAPPEAR_TIMEOUT_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
if wait_until "$T_DISAPPEAR_DEADLINE" no; then
	T_DISAPPEAR="$(now)"
else
	echo "FASTBOOT_USB_DISAPPEAR=NOT_OBSERVED"
	echo "FASTBOOT_DISAPPEAR_TIMESTAMP=NOT_OBSERVED"
	echo "2S_TIME_SIGNATURE=NO"
	echo "EARLY_SHORT_DELAY_EFFECT=NOT_OBSERVED"
	echo "MANUAL_KEY_REQUIRED=NO"
	echo "FINAL_GATE=MAINLINE_V2_M3_INCONCLUSIVE"
	exit 0
fi
print_timestamp "FASTBOOT_DISAPPEAR_TIMESTAMP" "$T_DISAPPEAR"
echo "FASTBOOT_USB_DISAPPEAR=$T_DISAPPEAR"

T_REAPPEAR_DEADLINE="$(python3 - "$T_DISAPPEAR" "$MAX_WINDOW_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
if wait_until "$T_REAPPEAR_DEADLINE" yes; then
	T_REAPPEAR="$(now)"
	print_timestamp "FASTBOOT_REAPPEAR_TIMESTAMP" "$T_REAPPEAR"
	echo "FASTBOOT_USB_REAPPEAR=$T_REAPPEAR"
else
	echo "FASTBOOT_USB_REAPPEAR=NOT_OBSERVED"
	echo "FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED"
	T_REAPPEAR=""
fi

# Keep the device observed through the minimum 15-second window. No second boot
# and no network or gadget probe occurs.
MIN_DEADLINE="$(python3 - "$T_DISAPPEAR" "$MIN_WINDOW_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
python3 - "$MIN_DEADLINE" <<'PY'
import sys
import time
remaining = float(sys.argv[1]) - time.time()
if remaining > 0:
    time.sleep(remaining)
PY

if [ -n "$T_REAPPEAR" ]; then
	python3 - "$T_DISAPPEAR" "$T_REAPPEAR" "$BASELINE_MEAN_SECONDS" <<'PY'
import sys
elapsed = float(sys.argv[2]) - float(sys.argv[1])
delta = elapsed - float(sys.argv[3])
print(f"FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR={elapsed:.3f}")
print(f"M3_ELAPSED={elapsed:.3f}")
print(f"M3_DELTA_FROM_BASELINE={delta:.3f}")
if elapsed >= 5.7 and delta >= 1.0:
    print("2S_TIME_SIGNATURE=YES")
    print("SHORT_DELAY_EFFECT_DETECTED=YES")
    print("ABL_TO_MAINLINE_EARLY_ENTRY=CONFIRMED")
    print("MAINLINE_EARLIEST_CHECKPOINT_EXECUTION=CONFIRMED")
    print("FINAL_GATE=MAINLINE_V2_M3_EARLY_ENTRY_CONFIRMED")
elif elapsed <= 5.0:
    print("2S_TIME_SIGNATURE=NO")
    print("EARLIEST_SHORT_DELAY_SIGNATURE_NOT_OBSERVED=YES")
    print("ABL_TO_MAINLINE_EARLY_ENTRY=NOT_CONFIRMED")
    print("FINAL_GATE=MAINLINE_V2_M3_EARLIEST_CHECKPOINT_NOT_CONFIRMED")
else:
    print("2S_TIME_SIGNATURE=NO")
    print("EARLIEST_SHORT_DELAY_SIGNATURE_NOT_OBSERVED=YES")
    print("ABL_TO_MAINLINE_EARLY_ENTRY=NOT_CONFIRMED")
    print("FINAL_GATE=MAINLINE_V2_M3_INCONCLUSIVE")
PY
	echo "MANUAL_KEY_REQUIRED=NO"
else
	echo "FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR=NOT_MEASURED"
	echo "M3_ELAPSED=NOT_MEASURED"
	echo "2S_TIME_SIGNATURE=NO"
	echo "ABL_TO_MAINLINE_EARLY_ENTRY=NOT_CONFIRMED"
	echo "MANUAL_KEY_REQUIRED=NOT_APPLICABLE"
	echo "FINAL_GATE=MAINLINE_V2_M3_NO_AUTOMATIC_RETURN"
fi

echo
if command -v ioreg >/dev/null 2>&1; then
	echo "-- macOS USB identity snapshot (18d1:d00d / Fastboot) --"
	ioreg -p IOUSB -w0 -l 2>/dev/null | grep -Ei '18d1|d00d|Fastboot' | head -20 || \
		echo "ioreg: no 18d1:d00d Fastboot hit"
fi

echo "Observation complete. Recovery must not boot Slot B again."
