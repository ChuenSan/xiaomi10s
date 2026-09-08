#!/usr/bin/env bash
# Observe Fastboot disappear, Stage2 gadget enum, new enX status, Fastboot return.
# Call from Fastboot with current-slot already b. Does not flash, set_active, or configure IP.
set -euo pipefail
FASTBOOT="${FASTBOOT:-fastboot}"
TIMEOUT="${TIMEOUT:-90}"
POLL="${POLL:-0.1}"

now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
present() { "$FASTBOOT" devices 2>/dev/null | grep -Eq $'\t *fastboot'; }
adb_present() { adb devices 2>/dev/null | grep -q $'\tdevice$'; }
usb_text() { ioreg -p IOUSB -l -w0 2>/dev/null || true; }
has_gadget() {
	usb_text | grep -Eq 'THYME-USB2|Stock Kernel USB Stage2 Device IP|thyme-mainline'
}
en_list() { ifconfig -l 2>/dev/null | tr ' ' '\n' | grep -E '^en[0-9]+$' || true; }

echo "== stock-kernel USB Stage2 device-ip host observe =="
present || { echo "OBSERVE-FAIL: not in Fastboot" >&2; exit 1; }

echo "TEST: STOCK_KERNEL_USB_STAGE2_DEVICE_STATIC_IP"
echo "timeout=${TIMEOUT}s poll=${POLL}s"
echo "-- USB baseline --"
ifconfig -l 2>/dev/null || true
system_profiler SPUSBDataType 2>/dev/null | grep -E 'Product ID|Vendor ID|Serial Number|Manufacturer|Location ID|Product:' | head -40 || true
usb_text | grep -E 'USB Serial Number|idVendor|idProduct|USB Product Name|USB Vendor Name|Fastboot|d00d|18d1' | head -40 || true
BASE_IF=$(ifconfig -l 2>/dev/null || true)
BASE_EN=$(en_list | sort | tr '\n' ' ')
echo "baseline_en=$BASE_EN"
echo "-- ifconfig -a baseline --"
ifconfig -a 2>/dev/null || true

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
T_EN=""
T_EN_GONE=""
NEW_IF=""
SAMPLE_DONE=""
DEADLINE=$(python3 -c "print(float('$T_FINISHED') + $TIMEOUT)")
STATE=wait_disappear
GADGET_SEEN=NO
EN_SEEN=NO
IPV4LL=NO

dump_new_if() {
	local ifn="$1"
	echo "-- $ifn --"
	ifconfig "$ifn" 2>/dev/null || true
	ifconfig "$ifn" 2>/dev/null | grep -E 'ether |status:|media:|mtu |flags=|inet ' || true
	if ifconfig "$ifn" 2>/dev/null | grep -Eq 'inet 169\.254\.'; then
		IPV4LL=YES
		echo "HOST_AUTOCONFIG_IPV4LL=YES"
	fi
	echo "HOST_PROJECT_IPV4_CONFIGURED=NO"
}

next_sample() {
	python3 - "$T_EN" "$SAMPLE_DONE" <<'PY'
import sys, time
t_en = float(sys.argv[1])
done = set(x for x in sys.argv[2].split(",") if x)
elapsed = time.time() - t_en
for t in (0.1, 0.5, 1, 2, 5, 10, 20):
    key = str(t)
    if key in done:
        continue
    if elapsed + 0.05 >= t:
        print(key)
        break
PY
}

while python3 -c "import sys,time; sys.exit(0 if $DEADLINE > time.time() else 1)"; do
	FB=no
	present && FB=yes
	GAD=no
	has_gadget && GAD=yes
	CUR_EN=$(en_list | sort | tr '\n' ' ')
	if [ -z "$NEW_IF" ]; then
		NEW_IF=$(python3 - "$BASE_EN" "$CUR_EN" <<'PY'
import sys
base=set(sys.argv[1].split())
cur=set(sys.argv[2].split())
new=sorted(cur-base)
print(new[0] if new else "")
PY
)
	fi

	if [ "$STATE" = wait_disappear ]; then
		if [ "$FB" = no ]; then
			T_DISAPPEAR=$(now)
			STATE=wait_gadget
			echo "fastboot_disappear_unix=$T_DISAPPEAR"
		fi
	elif [ "$STATE" = wait_gadget ]; then
		if [ -n "$NEW_IF" ] && [ -z "$T_EN" ]; then
			T_EN=$(now)
			EN_SEEN=YES
			echo "new_en_appear_unix=$T_EN if=$NEW_IF"
			dump_new_if "$NEW_IF"
		fi
		if [ "$GAD" = yes ] && [ -z "$T_GADGET" ]; then
			T_GADGET=$(now)
			GADGET_SEEN=YES
			echo "gadget_appear_unix=$T_GADGET"
			echo "-- gadget ioreg --"
			usb_text | grep -E 'THYME-USB2|Stock Kernel USB Stage2 Device IP|thyme-mainline|USB Serial Number|idVendor|idProduct|USB Product Name|USB Vendor Name|bcdUSB' | head -40 || true
			echo "-- system_profiler --"
			system_profiler SPUSBDataType 2>/dev/null | grep -A20 -E '1d6b|0104|THYME-USB2|Stage2' || true
			echo "-- ifconfig --"
			ifconfig -l 2>/dev/null || true
			[ -n "$NEW_IF" ] && dump_new_if "$NEW_IF"
			STATE=wait_gadget_gone
		elif [ "$FB" = yes ] && [ -z "$T_REAPPEAR" ]; then
			T_REAPPEAR=$(now)
			echo "fastboot_reappear_unix=$T_REAPPEAR"
			break
		fi
	elif [ "$STATE" = wait_gadget_gone ]; then
		if [ -n "$NEW_IF" ] && [ -n "$T_EN" ]; then
			hit=$(next_sample || true)
			if [ -n "$hit" ]; then
				echo "-- sample T+${hit}s $NEW_IF $(now) --"
				dump_new_if "$NEW_IF"
				SAMPLE_DONE="${SAMPLE_DONE:+$SAMPLE_DONE,}$hit"
			fi
		fi
		if [ -n "$NEW_IF" ]; then
			ifconfig "$NEW_IF" 2>/dev/null | grep -E 'status:|media:|ether ' || echo "$NEW_IF gone-or-unread"
		fi
		if [ -n "$NEW_IF" ] && [ -z "$T_EN_GONE" ]; then
			if ! ifconfig "$NEW_IF" >/dev/null 2>&1; then
				T_EN_GONE=$(now)
				echo "new_en_disappear_unix=$T_EN_GONE if=$NEW_IF"
			fi
		fi
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
echo "new_en=${NEW_IF:-NONE}"
echo "new_en_appear=${T_EN:-NONE}"
echo "new_en_disappear=${T_EN_GONE:-NONE}"
echo "fastboot_reappear=${T_REAPPEAR:-NONE}"
echo "adb_device=${T_ADB:-NONE}"
echo "gadget_seen=$GADGET_SEEN"
echo "en_seen=$EN_SEEN"
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
if [ -n "$T_EN" ] && [ -n "$T_EN_GONE" ]; then
	python3 -c "print(f'en_lifetime_s={float(\"$T_EN_GONE\") - float(\"$T_EN\"):.3f}')"
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
echo "HOST_AUTOCONFIG_IPV4LL=$IPV4LL"
echo "HOST_PROJECT_IPV4_CONFIGURED=NO"
echo "manual IPv4 configured=NO"
echo "NO host IP / route / ifconfig up performed"
echo "NO ping"
echo "Observe done (no writes)."
