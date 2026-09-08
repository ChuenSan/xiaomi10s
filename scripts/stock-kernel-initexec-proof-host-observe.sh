#!/usr/bin/env bash
# Time Fastboot disappear/reappear after one `fastboot reboot`.
# Call from Fastboot with current-slot already b. Does not flash or set_active.
set -euo pipefail
FASTBOOT="${FASTBOOT:-fastboot}"
TIMEOUT="${TIMEOUT:-180}"
POLL="${POLL:-0.75}"

now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
present() { "$FASTBOOT" devices 2>/dev/null | grep -q $'\tfastboot'; }

echo "== stock-kernel init-exec proof host observe =="
present || { echo "OBSERVE-FAIL: not in Fastboot" >&2; exit 1; }

echo "TEST: STOCK KERNEL INIT EXECUTION PROOF"
echo "timeout=${TIMEOUT}s poll=${POLL}s"
echo "issuing: fastboot reboot"
T0=$(now)
"$FASTBOOT" reboot
T_FINISHED=$(now)
echo "fastboot_reboot_finished_unix=$T_FINISHED"
echo "fastboot_reboot_cmd_dt=$(python3 -c "print(f'{$T_FINISHED - $T0:.3f}')")"

T_DISAPPEAR=""
T_REAPPEAR=""
DEADLINE=$(python3 -c "print($T_FINISHED + $TIMEOUT)")
STATE=wait_disappear

while python3 -c "import sys; sys.exit(0 if $DEADLINE > __import__('time').time() else 1)"; do
	if present; then
		if [ "$STATE" = wait_reappear ] && [ -z "$T_REAPPEAR" ]; then
			T_REAPPEAR=$(now)
			echo "fastboot_reappear_unix=$T_REAPPEAR"
			break
		fi
	else
		if [ "$STATE" = wait_disappear ] && [ -z "$T_DISAPPEAR" ]; then
			T_DISAPPEAR=$(now)
			STATE=wait_reappear
			echo "fastboot_disappear_unix=$T_DISAPPEAR"
		fi
	fi
	sleep "$POLL"
done

echo
echo "-- USB (ioreg Fastboot / d00d) --"
ioreg -p IOUSB -w0 -l 2>/dev/null | grep -E 'd00d|Fastboot|18d1' | head -20 || echo "ioreg: no Fastboot/d00d hit"

echo
echo "TIMING:"
echo "fastboot_reboot_finished=$T_FINISHED"
echo "fastboot_disappear=${T_DISAPPEAR:-NONE}"
echo "fastboot_reappear=${T_REAPPEAR:-NONE}"
if [ -n "$T_DISAPPEAR" ]; then
	python3 -c "print(f'disappear_after_s={float(\"$T_DISAPPEAR\") - float(\"$T_FINISHED\"):.3f}')"
else
	echo "disappear_after_s=NONE"
fi
if [ -n "$T_REAPPEAR" ]; then
	python3 -c "print(f'reappear_after_s={float(\"$T_REAPPEAR\") - float(\"$T_FINISHED\"):.3f}')"
	echo "manual_key_required=NO"
else
	echo "reappear_after_s=NONE"
	echo "manual_key_required=YES_OR_STILL_RUNNING"
fi
echo "Observe done (no writes)."
