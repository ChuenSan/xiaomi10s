#!/usr/bin/env bash
# Observe the single Mainline V2 M4B Slot B boot on macOS.
# This script issues exactly one fastboot reboot and never flashes or changes slots.
set -euo pipefail

FASTBOOT="${FASTBOOT:-fastboot}"
POLL_SECONDS="${POLL_SECONDS:-0.25}"
DISAPPEAR_TIMEOUT_SECONDS="${DISAPPEAR_TIMEOUT_SECONDS:-10}"
HARD_WINDOW_SECONDS="${HARD_WINDOW_SECONDS:-12}"
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
== thyme Mainline V2 M4B host observation ==
TEST: MAINLINE_V2_M4B_EARLIEST_ENTRY_SPIN_PROOF
INSTRUMENTATION: pure b . self loop at primary_entry first instruction
SLOT B: one boot only
SLOT A: protected; no write or slot mutation by this script
USB evidence: Fastboot identity only (18d1:d00d); no screen or network evidence
Recovery: manual Fastboot recovery is required if the 12-second window has no return
EOF

echo "current-slot=$CURRENT_SLOT"
echo "BASELINE_MEAN_SECONDS=$BASELINE_MEAN_SECONDS"
echo "HARD_WINDOW_SECONDS=$HARD_WINDOW_SECONDS"

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
	echo "AUTOMATIC_FASTBOOT_REAPPEAR=UNKNOWN"
	echo "ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED"
	echo "MANUAL_RECOVERY_REQUIRED=NO"
	echo "FINAL_GATE=MAINLINE_V2_M4B_INCONCLUSIVE"
	exit 0
fi
print_timestamp "FASTBOOT_DISAPPEAR_TIMESTAMP" "$T_DISAPPEAR"
echo "FASTBOOT_USB_DISAPPEAR=$T_DISAPPEAR"

echo "waiting only through the hard 12-second observation window"
T_REAPPEAR_DEADLINE="$(python3 - "$T_DISAPPEAR" "$HARD_WINDOW_SECONDS" <<'PY'
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"
if wait_until "$T_REAPPEAR_DEADLINE" yes; then
	T_REAPPEAR="$(now)"
	print_timestamp "FASTBOOT_REAPPEAR_TIMESTAMP" "$T_REAPPEAR"
	echo "FASTBOOT_USB_REAPPEAR=$T_REAPPEAR"
else
	T_REAPPEAR=""
	echo "FASTBOOT_USB_REAPPEAR=NOT_OBSERVED"
	echo "FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED"
fi

if [ -n "$T_REAPPEAR" ]; then
	python3 - "$T_DISAPPEAR" "$T_REAPPEAR" "$BASELINE_MEAN_SECONDS" <<'PY'
import sys
elapsed = float(sys.argv[2]) - float(sys.argv[1])
delta = elapsed - float(sys.argv[3])
print(f"FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR={elapsed:.3f}")
print(f"M4B_ELAPSED={elapsed:.3f}")
print(f"M4B_DELTA_FROM_BASELINE={delta:.3f}")
if 4.3 <= elapsed <= 5.3:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("M4B_SPIN_SUPPRESSION_EFFECT=NO")
    print("BASELINE_EARLY_RETURN_SUPPRESSED=NO")
    print("ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED")
    print("MAINLINE_PRIMARY_ENTRY=NOT_CONFIRMED")
    print("EXTERNAL_4P7S_RESET_HYPOTHESIS=SUPPORTED")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M4B_ENTRY_SPIN_NOT_CONFIRMED")
elif elapsed <= 10.0:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("M4B_SPIN_SUPPRESSION_EFFECT=INCONCLUSIVE")
    print("BASELINE_EARLY_RETURN_SUPPRESSED=NO")
    print("ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED")
    print("MAINLINE_PRIMARY_ENTRY=NOT_CONFIRMED")
    print("EXTERNAL_4P7S_RESET_HYPOTHESIS=UNKNOWN")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M4B_INCONCLUSIVE")
else:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("M4B_SPIN_SUPPRESSION_EFFECT=INCONCLUSIVE")
    print("BASELINE_EARLY_RETURN_SUPPRESSED=NO")
    print("ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED")
    print("MAINLINE_PRIMARY_ENTRY=NOT_CONFIRMED")
    print("EXTERNAL_4P7S_RESET_HYPOTHESIS=UNKNOWN")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M4B_INCONCLUSIVE")
PY
else
	echo "BASELINE_EARLY_RETURN_SUPPRESSED=YES"
	echo "M4B_SPIN_CONTROL_FLOW_EFFECT=YES"
	echo "ABL_TO_MAINLINE_ENTRY=CONFIRMED"
	echo "MAINLINE_PRIMARY_ENTRY=CONFIRMED"
	echo "EXTERNAL_4P7S_RESET_HYPOTHESIS=UNKNOWN"
	echo "MANUAL_RECOVERY_REQUIRED=YES"
	echo "FINAL_GATE=MAINLINE_V2_M4B_ENTRY_SPIN_CONFIRMED"
	echo "Do not issue an ordinary reboot; recover directly to Fastboot, then select A."
fi

echo
echo "Observation complete. Do not boot Slot B again."
