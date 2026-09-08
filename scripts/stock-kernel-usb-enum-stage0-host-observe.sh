#!/usr/bin/env bash
# Observe Fastboot disappear, custom gadget enum, Fastboot return.
# Call from Fastboot with current-slot already b. Does not flash or set_active.
set -euo pipefail
FASTBOOT="${FASTBOOT:-fastboot}"
TIMEOUT="${TIMEOUT:-90}"
POLL="${POLL:-0.5}"

now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
present() { "$FASTBOOT" devices 2>/dev/null | grep -Eq $'\t *fastboot'; }
adb_present() { adb devices 2>/dev/null | grep -q $'\tdevice$'; }
usb_text() { ioreg -p IOUSB -l -w0 2>/dev/null || true; }
has_gadget() {
	usb_text | grep -Eq 'THYME-USB0|Stock Kernel USB Enum Stage0|thyme-mainline'
}

echo "== stock-kernel USB enum stage0 host observe =="
present || { echo "OBSERVE-FAIL: not in Fastboot" >&2; exit 1; }

echo "TEST: STOCK_KERNEL_USB_ENUM_STAGE0"
echo "timeout=${TIMEOUT}s poll=${POLL}s"
echo "-- USB baseline --"
ifconfig -l 2>/dev/null || true
usb_text | grep -E 'USB Serial Number|idVendor|idProduct|USB Product Name|USB Vendor Name|Fastboot|d00d|18d1' | head -40 || true
BASE_IF=$(ifconfig -l 2>/dev/null || true)

echo "issuing: fastboot reboot"
T0=$(now)
"$FASTBOOT" reboot
T_FINISHED=$(now)
echo "fastboot_reboot_finished_unix=$T_FINISHED"

T_DISAPPEAR=""
T_GADGET=""
T_GADGET_GONE=""
T_REAPPEAR=""
T_ADB=""
DEADLINE=$(python3 -c "print(float('$T_FINISHED') + $TIMEOUT)")
STATE=wait_disappear
GADGET_SEEN=NO

while python3 -c "import sys,time; sys.exit(0 if $DEADLINE > time.time() else 1)"; do
	FB=no
	present && FB=yes
	GAD=no
	has_gadget && GAD=yes

	if [ "$STATE" = wait_disappear ]; then
		if [ "$FB" = no ]; then
			T_DISAPPEAR=$(now)
			STATE=wait_gadget
			echo "fastboot_disappear_unix=$T_DISAPPEAR"
		fi
	elif [ "$STATE" = wait_gadget ]; then
		if [ "$GAD" = yes ] && [ -z "$T_GADGET" ]; then
			T_GADGET=$(now)
			GADGET_SEEN=YES
			echo "gadget_appear_unix=$T_GADGET"
			echo "-- gadget ioreg --"
			usb_text | grep -E 'THYME-USB0|Stock Kernel USB Enum Stage0|thyme-mainline|USB Serial Number|idVendor|idProduct|USB Product Name|USB Vendor Name|idVendor|bcdUSB' | head -40 || true
			echo "-- ifconfig --"
			ifconfig -l 2>/dev/null || true
			STATE=wait_gadget_gone
		elif [ "$FB" = yes ] && [ -z "$T_REAPPEAR" ]; then
			T_REAPPEAR=$(now)
			echo "fastboot_reappear_unix=$T_REAPPEAR"
			break
		fi
	elif [ "$STATE" = wait_gadget_gone ]; then
		if [ "$GAD" = no ] && [ -z "$T_GADGET_GONE" ]; then
			T_GADGET_GONE=$(now)
			echo "gadget_disappear_unix=$T_GADGET_GONE"
			STATE=wait_reappear
		fi
	elif [ "$STATE" = wait_reappear ]; then
		if [ "$FB" = yes ] && [ -z "$T_REAPPEAR" ]; then
			T_REAPPEAR=$(now)
			echo "fastboot_reappear_unix=$T_REAPPEAR"
			break
		fi
	fi
	if [ -z "$T_ADB" ] && adb_present; then
		T_ADB=$(now)
		echo "adb_device_unix=$T_ADB"
		break
	fi
	sleep "$POLL"
done

echo
echo "TIMING:"
echo "fastboot_reboot_finished=$T_FINISHED"
echo "fastboot_disappear=${T_DISAPPEAR:-NONE}"
echo "gadget_appear=${T_GADGET:-NONE}"
echo "gadget_disappear=${T_GADGET_GONE:-NONE}"
echo "fastboot_reappear=${T_REAPPEAR:-NONE}"
echo "adb_device=${T_ADB:-NONE}"
echo "gadget_seen=$GADGET_SEEN"
echo "ifaces_before=$BASE_IF"
echo "ifaces_after=$(ifconfig -l 2>/dev/null || true)"
if [ -n "$T_DISAPPEAR" ]; then
	python3 -c "print(f'disappear_after_s={float(\"$T_DISAPPEAR\") - float(\"$T_FINISHED\"):.3f}')"
fi
if [ -n "$T_GADGET" ]; then
	python3 -c "print(f'gadget_after_s={float(\"$T_GADGET\") - float(\"$T_FINISHED\"):.3f}')"
fi
if [ -n "$T_GADGET_GONE" ] && [ -n "$T_GADGET" ]; then
	python3 -c "print(f'gadget_hold_s={float(\"$T_GADGET_GONE\") - float(\"$T_GADGET\"):.3f}')"
fi
if [ -n "$T_REAPPEAR" ]; then
	python3 -c "print(f'reappear_after_s={float(\"$T_REAPPEAR\") - float(\"$T_FINISHED\"):.3f}')"
	echo "manual_key_required=NO"
elif [ -n "$T_ADB" ]; then
	echo "manual_key_required=NO_ADB_FELL_BACK"
else
	echo "reappear_after_s=NONE"
	echo "manual_key_required=YES_OR_STILL_RUNNING"
fi
echo "Observe done (no writes)."
