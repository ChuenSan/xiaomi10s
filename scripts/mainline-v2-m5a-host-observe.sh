#!/usr/bin/env bash
# Observe the single M5A Slot B stock-entry-spin boot on macOS.
# Issues exactly one fastboot reboot. Never flashes or changes slots.
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
== thyme Mainline V2 M5A host observation ==
TEST: MAINLINE_V2_M5A_STOCK_ENTRY_SPIN_TRUE_DEVICE_CONTROL
INSTRUMENTATION: stock 4.19 Image offset 0 = b .
SLOT B: one boot only
SLOT A: protected; no write or slot mutation by this script
USB evidence: Fastboot identity only (18d1:d00d)
HARD WINDOW: 12 seconds
If no automatic return: hardware Vol-Down+Power to Fastboot. Do not ordinary reboot.
EOF

echo "current-slot=$CURRENT_SLOT"
echo "BASELINE_MEAN_SECONDS=$BASELINE_MEAN_SECONDS"
echo "HARD_WINDOW_SECONDS=$HARD_WINDOW_SECONDS"
echo "SECOND_B_BOOT_FORBIDDEN=YES"

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
	echo "STOCK_SPIN_BASELINE_RETURN_SUPPRESSED=UNKNOWN"
	echo "MANUAL_RECOVERY_REQUIRED=NO"
	echo "FINAL_GATE=MAINLINE_V2_M5A_INCONCLUSIVE"
	exit 0
fi
print_timestamp "FASTBOOT_DISAPPEAR_TIMESTAMP" "$T_DISAPPEAR"
echo "FASTBOOT_USB_DISAPPEAR=$T_DISAPPEAR"
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
	echo "FASTBOOT_USB_REAPPEAR=$T_REAPPEAR"
	echo "T_REAPPEAR=$T_REAPPEAR"
else
	T_REAPPEAR=""
	echo "FASTBOOT_USB_REAPPEAR=NOT_OBSERVED"
	echo "FASTBOOT_REAPPEAR_TIMESTAMP=NOT_OBSERVED"
	echo "T_REAPPEAR=NOT_OBSERVED"
fi

if [ -n "$T_REAPPEAR" ]; then
	python3 - "$T_DISAPPEAR" "$T_REAPPEAR" "$BASELINE_MEAN_SECONDS" <<'PY'
import sys
elapsed = float(sys.argv[2]) - float(sys.argv[1])
delta = elapsed - float(sys.argv[3])
print(f"FASTBOOT_USB_DISAPPEAR_TO_REAPPEAR={elapsed:.3f}")
print(f"M5A_ELAPSED={elapsed:.3f}")
print(f"M5A_DELTA_FROM_BASELINE={delta:.3f}")
if 4.3 <= elapsed <= 5.3:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("STOCK_SPIN_BASELINE_RETURN_SUPPRESSED=NO")
    print("STOCK_ENTRY_SPIN_CONTROL_FLOW_EFFECT=NO")
    print("STOCK_RAW_ENTRY_EXECUTION=NOT_CONFIRMED")
    print("UNCONDITIONAL_KERNEL_INDEPENDENT_4P7S_WATCHDOG=STRONGLY_SUPPORTED")
    print("EXTERNAL_OR_FIRMWARE_4P7S_RESET_HYPOTHESIS=STRONGLY_SUPPORTED")
    print("MAINLINE_PRE_ENTRY_OR_HANDOFF_FAILURE_HYPOTHESIS=UNKNOWN")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M5A_STOCK_SPIN_4P7S_RETURN")
elif elapsed <= 12.0:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("STOCK_SPIN_BASELINE_RETURN_SUPPRESSED=UNKNOWN")
    print("STOCK_ENTRY_SPIN_CONTROL_FLOW_EFFECT=INCONCLUSIVE")
    print("STOCK_RAW_ENTRY_EXECUTION=NOT_CONFIRMED")
    print("UNCONDITIONAL_KERNEL_INDEPENDENT_4P7S_WATCHDOG=UNKNOWN")
    print("MAINLINE_PRE_ENTRY_OR_HANDOFF_FAILURE_HYPOTHESIS=UNKNOWN")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M5A_INCONCLUSIVE")
else:
    print("AUTOMATIC_FASTBOOT_REAPPEAR=YES")
    print("STOCK_SPIN_BASELINE_RETURN_SUPPRESSED=UNKNOWN")
    print("MANUAL_RECOVERY_REQUIRED=NO")
    print("FINAL_GATE=MAINLINE_V2_M5A_INCONCLUSIVE")
PY
else
	echo "AUTOMATIC_FASTBOOT_REAPPEAR=NO"
	echo "STOCK_SPIN_BASELINE_RETURN_SUPPRESSED=YES"
	echo "STOCK_ENTRY_SPIN_CONTROL_FLOW_EFFECT=YES"
	echo "STOCK_RAW_ENTRY_EXECUTION=STRONGLY_CONFIRMED"
	echo "UNCONDITIONAL_KERNEL_INDEPENDENT_4P7S_WATCHDOG=REFUTED_BY_CONTROL"
	echo "UNCONDITIONAL_4P7S_EXTERNAL_WATCHDOG=REFUTED_BY_CONTROL"
	echo "MAINLINE_PRE_ENTRY_OR_HANDOFF_FAILURE_HYPOTHESIS=STRONGLY_SUPPORTED"
	echo "MANUAL_RECOVERY_REQUIRED=YES"
	echo "FINAL_GATE=MAINLINE_V2_M5A_STOCK_SPIN_SUPPRESSES_4P7S"
	echo "Recover with hardware Vol-Down+Power to Fastboot. Do not ordinary reboot."
fi

echo
echo "Observation complete. SECOND_B_BOOT_FORBIDDEN=YES"
echo "Do not boot Slot B again. Select A from Fastboot."
