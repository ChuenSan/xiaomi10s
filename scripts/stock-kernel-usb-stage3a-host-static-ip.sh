#!/usr/bin/env bash
# Stage3A: dynamic macOS NCM discovery, ephemeral host IPv4, route verification.
# No build, flash, ping, HTTP, ARP, or manual route changes.
set -u

REPO_DIR="/Volumes/LinuxDev/thyme-mainline"
EXPECTED_BOOT_SHA="88c4d8a5be098a508356120a02bdfb16e78b576b1876aaa98d06e945b7316b49"
EXPECTED_BOOT_BYTES=52670464
FASTBOOT_TIMEOUT=90
POLL=0.5

cd "$REPO_DIR" || exit 1
mkdir -p work
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="work/usb-stage3a-host-static-ip-${STAMP}.log"
exec > >(tee "$LOG") 2>&1

now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }

adb_present() {
	adb devices 2>/dev/null | awk 'NR > 1 && $2 == "device" { found=1 } END { exit(found ? 0 : 1) }'
}

fastboot_present() {
	fastboot devices 2>/dev/null | awk 'NF >= 2 && $2 == "fastboot" { found=1 } END { exit(found ? 0 : 1) }'
}

getvar() {
	fastboot getvar "$1" 2>&1 | sed -n "s/^$1: //p" | head -n 1
}

en_list() {
	ifconfig -l 2>/dev/null | tr ' ' '\n' | grep -E '^en[0-9]+$' || true
}

new_en_candidates() {
	local current
	current=$(en_list)
	python3 - "$BASE_EN" "$current" <<'PY'
import sys
base = set(sys.argv[1].split())
current = set(sys.argv[2].split())
for name in sorted(current - base):
    if name.startswith("en") and name[2:].isdigit():
        print(name)
PY
}

interface_mac() {
	ifconfig "$1" 2>/dev/null | awk '/^[[:space:]]*ether / { print tolower($2); exit }'
}

route_interface() {
	awk -F ': *' '/^[[:space:]]*interface:/ { print $2; exit }'
}

route_field() {
	awk -F ': *' -v key="$1" '$1 ~ "^[[:space:]]*" key "$" { print $2; exit }'
}

descriptor_match() {
	# The Stage2 root device is visible in system_profiler, not the IOUSB tree.
	USB_PROFILE=$(system_profiler SPUSBDataType 2>/dev/null || true)
	printf '%s\n' "$USB_PROFILE" | grep -Fq 'Stock Kernel USB Stage2 Device IP:' || return 1
	printf '%s\n' "$USB_PROFILE" | grep -Fq 'Product ID: 0x0104' || return 1
	printf '%s\n' "$USB_PROFILE" | grep -Fq 'Vendor ID: 0x1d6b' || return 1
	printf '%s\n' "$USB_PROFILE" | grep -Fq 'Manufacturer: thyme-mainline' || return 1
	printf '%s\n' "$USB_PROFILE" | grep -Fq 'Serial Number: THYME-USB2' || return 1
	return 0
}

print_descriptor_snapshot() {
	echo "USB_ENUMERATED=YES"
	echo "USB_VID_PID=1d6b:0104"
	echo "USB_MANUFACTURER=thyme-mainline"
	echo "USB_PRODUCT=Stock Kernel USB Stage2 Device IP"
	echo "USB_SERIAL_MATCH=YES"
	system_profiler SPUSBDataType 2>/dev/null | grep -E \
		'Product ID: 0x0104|Vendor ID: 0x1d6b|Manufacturer: thyme-mainline|Product: Stock Kernel USB Stage2 Device IP' || true
}

wait_for_android_a() {
	local i slot boot
	for i in $(seq 1 180); do
		if adb_present; then
			slot=$(adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r')
			boot=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
			if [ "$slot" = _a ] && [ "$boot" = 1 ]; then return 0; fi
		fi
		sleep 0.5
	done
	return 1
}

fail_preflight() {
	echo "PREFLIGHT_STOP: $*"
	echo "No Stage3A boot attempt was started."
	exit 1
}

printf '%s\n' '== STOCK_KERNEL_USB_STAGE3A_HOST_STATIC_IP =='
printf '%s\n' "LOG=$LOG"
printf '%s\n' 'Policy: NO BUILD / NO FLASH / NO PING / NO HTTP / NO ARP / NO MANUAL ROUTE'
printf '%s\n' 'The script must be run directly from an interactive terminal.'

if ! sudo -v; then
	fail_preflight 'sudo authorization unavailable; rerun after sudo -v in this terminal'
fi

echo 'SUDO_AUTHORIZED=YES'

# Ensure Android A is the read-only source of the boot_b hash.
if ! adb_present; then
	if fastboot_present; then
		CURRENT=$(getvar current-slot)
		[ "$CURRENT" = a ] || fail_preflight "current-slot=$CURRENT, expected a"
		echo 'FASTBOOT_INITIAL=YES; returning to Android A for read-only hash preflight'
		fastboot reboot || fail_preflight 'fastboot reboot to Android A failed'
	else
		fail_preflight 'neither adb Android device nor fastboot device is present'
	fi
fi

if ! wait_for_android_a; then
	fail_preflight 'Android A did not return on adb'
fi
ADB_SLOT=$(adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r')
ADB_BOOT_COMPLETED=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
echo '--- Android A read-only preflight ---'
echo 'ADB_DEVICE_PRESENT=YES'
echo "slot_suffix=$ADB_SLOT"
echo "boot_completed=$ADB_BOOT_COMPLETED"
[ "$ADB_SLOT" = _a ] || fail_preflight "adb slot_suffix=$ADB_SLOT, expected _a"
[ "$ADB_BOOT_COMPLETED" = 1 ] || fail_preflight "sys.boot_completed=$ADB_BOOT_COMPLETED, expected 1"

ADB_ID=$(adb shell su -c id 2>/dev/null | tr -d '\r')
echo "ROOT_ID=$ADB_ID"
printf '%s\n' "$ADB_ID" | grep -Fq 'uid=0' || fail_preflight 'root read-only access unavailable'
BOOT_HASH=$(adb shell su -c "dd if=/dev/block/by-name/boot_b bs=${EXPECTED_BOOT_BYTES} count=1 2>/dev/null | sha256sum" 2>/dev/null | tr -d '\r' | awk 'NF { print $1; exit }')
echo "boot_b_prefix_sha256=$BOOT_HASH"
echo "boot_b_expected_sha256=$EXPECTED_BOOT_SHA"
[ "$BOOT_HASH" = "$EXPECTED_BOOT_SHA" ] || fail_preflight 'boot_b Stage2 SHA mismatch; STOP without flashing'
echo 'BOOT_B_STAGE2_HASH_MATCH=YES'

adb reboot bootloader || fail_preflight 'adb reboot bootloader failed'
for i in $(seq 1 120); do
	if fastboot_present; then break; fi
	sleep 0.5
done
fastboot_present || fail_preflight 'Fastboot did not reappear after adb reboot bootloader'

echo '--- Fastboot preflight ---'
PRODUCT=$(getvar product)
UNLOCKED=$(getvar unlocked)
CURRENT=$(getvar current-slot)
UNBOOTABLE_B=$(getvar slot-unbootable:b)
RETRY_BEFORE=$(getvar slot-retry-count:b)
SNAPSHOT=$(getvar snapshot-update-status)
BATTERY=$(getvar battery-soc-ok)
echo "product=$PRODUCT"
echo "unlocked=$UNLOCKED"
echo "current-slot=$CURRENT"
echo "slot-unbootable:b=$UNBOOTABLE_B"
echo "slot-retry-count:b=$RETRY_BEFORE"
echo "snapshot-update-status=$SNAPSHOT"
echo "battery-soc-ok=$BATTERY"
[ "$PRODUCT" = thyme ] || fail_preflight "product=$PRODUCT"
[ "$UNLOCKED" = yes ] || fail_preflight "unlocked=$UNLOCKED"
[ "$CURRENT" = a ] || fail_preflight "current-slot=$CURRENT"
[ "$UNBOOTABLE_B" = no ] || fail_preflight "slot-unbootable:b=$UNBOOTABLE_B"
[ "$SNAPSHOT" = none ] || fail_preflight "snapshot-update-status=$SNAPSHOT"
[ "$BATTERY" = yes ] || fail_preflight "battery-soc-ok=$BATTERY"
[ -n "$RETRY_BEFORE" ] || fail_preflight 'slot-retry-count:b unavailable'

echo '--- Host baseline while Fastboot ---'
echo 'ifconfig -a:'
ifconfig -a
PRE_ROUTE=$(route -n get 10.66.73.1 2>&1 || true)
echo 'route -n get 10.66.73.1:'
printf '%s\n' "$PRE_ROUTE"
PRE_ROUTE_IF=$(printf '%s\n' "$PRE_ROUTE" | route_interface)
echo "PRETEST_ROUTE_INTERFACE=${PRE_ROUTE_IF:-NONE}"
case "$PRE_ROUTE_IF" in
	utun*) PREEXISTING_ROUTE_COLLISION=YES ;;
	*) PREEXISTING_ROUTE_COLLISION=NO ;;
esac
echo "PREEXISTING_ROUTE_COLLISION=$PREEXISTING_ROUTE_COLLISION"
echo 'netstat -rn -f inet:'
netstat -rn -f inet || true
echo 'networksetup -listallhardwareports:'
networksetup -listallhardwareports || true
echo 'system_profiler SPUSBDataType selected baseline fields:'
system_profiler SPUSBDataType 2>/dev/null | grep -E 'Product ID|Vendor ID|Manufacturer|Location ID|Product:' | grep -v 'Serial Number' | head -80 || true
BASE_EN=$(en_list | sort -u | tr '\n' ' ')
echo "BASE_EN=$BASE_EN"

# Only the whitelisted slot activation and reboot occur here.
fastboot set_active b || fail_preflight 'fastboot set_active b failed'
AFTER_SET_ACTIVE=$(getvar current-slot)
RETRY_AFTER_SET_ACTIVE=$(getvar slot-retry-count:b)
echo "AFTER_SET_ACTIVE=$AFTER_SET_ACTIVE"
echo "RETRY_AFTER_SET_ACTIVE=$RETRY_AFTER_SET_ACTIVE"
[ "$AFTER_SET_ACTIVE" = b ] || fail_preflight "current-slot after set_active=$AFTER_SET_ACTIVE"

echo 'issuing exactly one Stage2 start: fastboot reboot'
fastboot reboot || fail_preflight 'fastboot reboot failed'
T_FINISHED=$(now)
echo "fastboot_reboot_finished_unix=$T_FINISHED"

T_DISAPPEAR=''
T_GADGET=''
T_GADGET_GONE=''
T_EN=''
T_EN_GONE=''
T_REAPPEAR=''
NEW_IF=''
USB_ENUMERATED=NO
NEW_IF_FOUND=NO
HOST_LINK_ACTIVE_BEFORE_IP=NO
HOST_LINK_ACTIVE_AFTER_IP=NO
HOST_IPV4LL_BEFORE_STATIC=NO
HOST_STATIC_ADDR_VERIFIED=NO
CONNECTED_ROUTE_PRESENT=NO
ROUTE_INTERFACE=''
ROUTE_GATEWAY=''
ROUTE_FLAGS=''
HOST_MAC=''
NCM_HOST_ADDR_FROM_HOST_IFACE=''
NCM_HOST_ADDR_FROM_PSTORE=''
NCM_HOST_MAC_MATCH=NO
NCM_HOST_ADDR_CORRELATION=UNAVAILABLE
RECOVERY_SLOT=''
RECOVERY_BOOT_COMPLETED=''
CURRENT_AFTER_BOOT=''
IP_ATTEMPTED=NO
CONFIG_RC=125
LINK_FAILURE=NO
GADGET_SEEN=NO
DEADLINE=$(python3 -c "print(float('$T_FINISHED') + $FASTBOOT_TIMEOUT)")

while python3 -c "import time; raise SystemExit(0 if time.time() < $DEADLINE else 1)"; do
	FB=NO
	if fastboot_present; then FB=YES; fi
	if [ "$FB" = NO ] && [ -z "$T_DISAPPEAR" ]; then
		T_DISAPPEAR=$(now)
		echo "fastboot_disappear_unix=$T_DISAPPEAR"
	fi

	DESC=NO
	if descriptor_match; then DESC=YES; fi
	if [ "$DESC" = YES ] && [ "$GADGET_SEEN" = NO ]; then
		GADGET_SEEN=YES
		USB_ENUMERATED=YES
		T_GADGET=$(now)
		echo "gadget_appear_unix=$T_GADGET"
		print_descriptor_snapshot
	fi

	if [ -z "$NEW_IF" ]; then
		CANDIDATES=$(new_en_candidates)
		CAND_COUNT=$(printf '%s\n' "$CANDIDATES" | awk 'NF { n++ } END { print n + 0 }')
		if [ "$DESC" = YES ] && [ "$CAND_COUNT" -eq 1 ]; then
			NEW_IF=$(printf '%s\n' "$CANDIDATES" | awk 'NF { print; exit }')
		elif [ "$DESC" = YES ] && [ "$CAND_COUNT" -gt 1 ]; then
			echo "NEW_IF_AMBIGUOUS=YES candidates=$(printf '%s' "$CANDIDATES" | tr '\n' ' ')"
		fi
		if [ -n "$NEW_IF" ]; then
			NEW_IF_FOUND=YES
			T_EN=$(now)
			HOST_MAC=$(interface_mac "$NEW_IF")
			NCM_HOST_ADDR_FROM_HOST_IFACE="$HOST_MAC"
			if [ -n "$HOST_MAC" ]; then
				NCM_HOST_MAC_MATCH=YES
				NCM_HOST_ADDR_CORRELATION=HOST_INTERFACE_MAC
			fi
			echo "new_en_appear_unix=$T_EN"
			echo "NEW_IF=$NEW_IF"
			echo "HOST_MAC=$HOST_MAC"
			echo "NCM_HOST_ADDR_FROM_HOST_IFACE=$NCM_HOST_ADDR_FROM_HOST_IFACE"
			echo "NCM_HOST_ADDR_CORRELATION=$NCM_HOST_ADDR_CORRELATION"
			echo "--- $NEW_IF before static IPv4 ---"
			ifconfig "$NEW_IF" 2>/dev/null || true
			if ifconfig "$NEW_IF" 2>/dev/null | grep -Eq 'inet 169\.254\.'; then
				HOST_IPV4LL_BEFORE_STATIC=YES
			fi
			echo "HOST_IPV4LL_BEFORE_STATIC=$HOST_IPV4LL_BEFORE_STATIC"
		fi
	fi

	if [ -n "$NEW_IF" ] && [ "$IP_ATTEMPTED" = NO ]; then
		IF_STATE=$(ifconfig "$NEW_IF" 2>/dev/null || true)
		if printf '%s\n' "$IF_STATE" | grep -Eq '^[[:space:]]*status: active'; then
			HOST_LINK_ACTIVE_BEFORE_IP=YES
			if printf '%s\n' "$IF_STATE" | grep -Eq 'inet 169\\.254\\.'; then
				HOST_IPV4LL_BEFORE_STATIC=YES
			fi
			echo "HOST_LINK_ACTIVE_BEFORE_IP=YES"
			echo "HOST_IPV4LL_BEFORE_STATIC=$HOST_IPV4LL_BEFORE_STATIC"
			IP_ATTEMPTED=YES
			echo "CONFIG_COMMAND=sudo ifconfig $NEW_IF inet 10.66.73.2 netmask 255.255.255.0"
			sudo ifconfig "$NEW_IF" inet 10.66.73.2 netmask 255.255.255.0
			CONFIG_RC=$?
			echo "CONFIG_RETURN=$CONFIG_RC"
			echo "--- $NEW_IF immediately after static IPv4 ---"
			AFTER_IP=$(ifconfig "$NEW_IF" 2>/dev/null || true)
			printf '%s\n' "$AFTER_IP"
			if printf '%s\n' "$AFTER_IP" | grep -Eq 'inet 10\.66\.73\.2([[:space:]]|$)' && \
				printf '%s\n' "$AFTER_IP" | grep -Eq 'netmask (0xffffff00|255\.255\.255\.0)'; then
				HOST_STATIC_ADDR_VERIFIED=YES
			fi
			echo "HOST_STATIC_ADDR_VERIFIED=$HOST_STATIC_ADDR_VERIFIED"
			if printf '%s\n' "$AFTER_IP" | grep -Eq '^[[:space:]]*status: active'; then
				HOST_LINK_ACTIVE_AFTER_IP=YES
			fi
			echo "HOST_LINK_ACTIVE_AFTER_IP=$HOST_LINK_ACTIVE_AFTER_IP"

			if [ "$HOST_STATIC_ADDR_VERIFIED" = YES ]; then
				ROUTE_DURING=$(route -n get 10.66.73.1 2>&1 || true)
				echo 'route -n get 10.66.73.1 during test:'
				printf '%s\n' "$ROUTE_DURING"
				ROUTE_INTERFACE=$(printf '%s\n' "$ROUTE_DURING" | route_interface)
				ROUTE_GATEWAY=$(printf '%s\n' "$ROUTE_DURING" | route_field gateway)
				ROUTE_FLAGS=$(printf '%s\n' "$ROUTE_DURING" | route_field flags)
				echo "ROUTE_INTERFACE=$ROUTE_INTERFACE"
				echo "ROUTE_GATEWAY=${ROUTE_GATEWAY:-NONE}"
				echo "ROUTE_FLAGS=${ROUTE_FLAGS:-NONE}"
				NETSTAT_DURING=$(netstat -rn -f inet 2>&1 || true)
				echo 'connected-route candidates during test:'
				CONNECTED_LINES=$(printf '%s\n' "$NETSTAT_DURING" | grep '10\.66\.73' || true)
				printf '%s\n' "${CONNECTED_LINES:-NONE}"
				if [ -n "$CONNECTED_LINES" ] && printf '%s\n' "$CONNECTED_LINES" | grep -Fq "$NEW_IF"; then
					CONNECTED_ROUTE_PRESENT=YES
				fi
				echo "CONNECTED_ROUTE_PRESENT=$CONNECTED_ROUTE_PRESENT"
			fi
		elif [ -n "$T_EN" ] && python3 -c "import time; raise SystemExit(0 if time.time() > $(python3 -c "print(float('$T_EN') + 8)") else 1)"; then
			LINK_FAILURE=YES
			IP_ATTEMPTED=YES
			echo 'HOST_LINK_ACTIVE_BEFORE_IP=NO; link remained inactive for the observation window'
		fi
	fi

	if [ -n "$NEW_IF" ] && [ -z "$T_EN_GONE" ]; then
		if ! ifconfig "$NEW_IF" >/dev/null 2>&1; then
			T_EN_GONE=$(now)
			echo "new_en_disappear_unix=$T_EN_GONE if=$NEW_IF"
		fi
	fi
	if [ "$GADGET_SEEN" = YES ] && [ "$FB" = YES ] && [ "$DESC" = NO ] && [ -z "$T_GADGET_GONE" ]; then
		T_GADGET_GONE=$(now)
		echo "gadget_disappear_unix=$T_GADGET_GONE"
	fi
	if [ "$GADGET_SEEN" = YES ] && [ "$FB" = YES ] && [ "$DESC" = NO ]; then
		T_REAPPEAR=$(now)
		echo "fastboot_reappear_unix=$T_REAPPEAR"
		break
	fi
	sleep "$POLL"
done

if [ -z "$T_REAPPEAR" ] && fastboot_present; then
	T_REAPPEAR=$(now)
	echo "fastboot_reappear_unix=$T_REAPPEAR"
fi

echo '--- Stage3A observation summary ---'
echo "USB_ENUMERATED=$USB_ENUMERATED"
echo "NEW_IF_FOUND=$NEW_IF_FOUND"
echo "NEW_IF=${NEW_IF:-NONE}"
echo "HOST_LINK_ACTIVE_BEFORE_IP=$HOST_LINK_ACTIVE_BEFORE_IP"
echo "HOST_IPV4LL_BEFORE_STATIC=$HOST_IPV4LL_BEFORE_STATIC"
echo "HOST_STATIC_ADDR_VERIFIED=$HOST_STATIC_ADDR_VERIFIED"
echo "HOST_LINK_ACTIVE_AFTER_IP=$HOST_LINK_ACTIVE_AFTER_IP"
echo "ROUTE_INTERFACE=${ROUTE_INTERFACE:-NONE}"
echo "CONNECTED_ROUTE_PRESENT=$CONNECTED_ROUTE_PRESENT"
echo 'NO_PING_RUN=YES'
echo 'NO_HTTP_RUN=YES'
echo 'NO_ARP_RUN=YES'
echo 'NO_MANUAL_ROUTE_ADD=YES'

# Read retry metadata before restoring Android A.
if fastboot_present; then
	RETRY_AFTER_BOOT=$(getvar slot-retry-count:b)
	UNBOOTABLE_AFTER_BOOT=$(getvar slot-unbootable:b)
	CURRENT_AFTER_BOOT=$(getvar current-slot)
	echo '--- Fastboot after Stage2 window ---'
	echo "current-slot=$CURRENT_AFTER_BOOT"
	echo "slot-retry-count:b=$RETRY_AFTER_BOOT"
	echo "slot-unbootable:b=$UNBOOTABLE_AFTER_BOOT"
	if [ "$CURRENT_AFTER_BOOT" = b ]; then
		fastboot set_active a
		SET_A_RC=$?
		echo "set_active_a_return=$SET_A_RC"
		if [ "$SET_A_RC" -eq 0 ]; then
			CURRENT_AFTER_SET_A=$(getvar current-slot)
			echo "current-slot-after-set_active_a=$CURRENT_AFTER_SET_A"
			fastboot reboot
			wait_for_android_a && echo 'Android_A_RESTORED=YES' || echo 'Android_A_RESTORED=NO'
		else
			echo 'Android_A_RESTORED=NO; set_active a failed'
		fi
	else
		echo 'STAGE2_CURRENT_SLOT_REGRESSION=YES'
	fi
else
	echo 'Fastboot did not return within the bounded observation window'
fi

# Read-only recovery checks. Pstore is optional; the host-side NCM MAC is primary.
if adb_present; then
	RECOVERY_SLOT=$(adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r')
	RECOVERY_BOOT_COMPLETED=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
	echo '--- Android A recovery ---'
	echo "slot_suffix=$RECOVERY_SLOT"
	echo "boot_completed=$RECOVERY_BOOT_COMPLETED"
	PSTORE_RAW=$(adb shell su -c 'for f in /sys/fs/pstore/*; do if [ -f "$f" ]; then grep "THYME-USB2:\(HOST_ADDR\|NCM_IFNAME\)=" "$f"; fi; done' 2>/dev/null | tr -d '\r' || true)
	NCM_HOST_ADDR_FROM_PSTORE=$(printf '%s\n' "$PSTORE_RAW" | sed -n 's/.*THYME-USB2:HOST_ADDR=\([0-9A-Fa-f:]*\).*/\1/p' | tr '[:upper:]' '[:lower:]' | tail -n 1)
	NCM_IFNAME_FROM_PSTORE=$(printf '%s\n' "$PSTORE_RAW" | sed -n 's/.*THYME-USB2:NCM_IFNAME=\([^[:space:]]*\).*/\1/p' | tail -n 1)
	echo "NCM_HOST_ADDR_FROM_PSTORE=${NCM_HOST_ADDR_FROM_PSTORE:-UNAVAILABLE}"
	echo "NCM_IFNAME_FROM_PSTORE=${NCM_IFNAME_FROM_PSTORE:-UNAVAILABLE}"
	if [ -n "$NCM_HOST_ADDR_FROM_PSTORE" ]; then
		if [ -n "$HOST_MAC" ] && [ "$HOST_MAC" = "$NCM_HOST_ADDR_FROM_PSTORE" ]; then
			NCM_HOST_MAC_MATCH=YES
			NCM_HOST_ADDR_CORRELATION=PSTORE_MATCH
		else
			NCM_HOST_MAC_MATCH=NO
			NCM_HOST_ADDR_CORRELATION=PSTORE_MISMATCH
		fi
	fi
	echo "NCM_HOST_ADDR_FROM_HOST_IFACE=${NCM_HOST_ADDR_FROM_HOST_IFACE:-UNAVAILABLE}"
	echo "NCM_HOST_ADDR_CORRELATION=$NCM_HOST_ADDR_CORRELATION"
	echo "NCM_HOST_MAC_MATCH=$NCM_HOST_MAC_MATCH"
else
	echo 'Android_A_RESTORED=NO'
fi

POST_ROUTE=$(route -n get 10.66.73.1 2>&1 || true)
echo 'route -n get 10.66.73.1 post-test:'
printf '%s\n' "$POST_ROUTE"
POST_ROUTE_IF=$(printf '%s\n' "$POST_ROUTE" | route_interface)
echo "POSTTEST_ROUTE_INTERFACE=${POST_ROUTE_IF:-NONE}"
if [ -n "$NEW_IF" ]; then
	if ifconfig "$NEW_IF" >/dev/null 2>&1; then
		echo "NEW_IF_AFTER_RECOVERY=REMAINS:$NEW_IF"
		ifconfig "$NEW_IF" || true
	else
		echo "NEW_IF_AFTER_RECOVERY=DISAPPEARED:$NEW_IF"
	fi
fi

FINAL_GATE=''
if [ "$USB_ENUMERATED" = YES ] && \
	[ "$NEW_IF_FOUND" = YES ] && \
	[ "$HOST_LINK_ACTIVE_BEFORE_IP" = YES ] && \
	[ "$HOST_STATIC_ADDR_VERIFIED" = YES ] && \
	[ "$HOST_LINK_ACTIVE_AFTER_IP" = YES ] && \
	[ "$ROUTE_INTERFACE" = "$NEW_IF" ] && \
	[ "$CONNECTED_ROUTE_PRESENT" = YES ] && \
	[ "$NCM_HOST_MAC_MATCH" = YES ] && \
	[ "$RECOVERY_SLOT" = _a ] && \
	[ "$RECOVERY_BOOT_COMPLETED" = 1 ]; then
	FINAL_GATE=USB_STAGE3A_HOST_STATIC_IP_ROUTE_PASS
elif [ "$CONFIG_RC" -ne 0 ] && [ "$IP_ATTEMPTED" = YES ]; then
	FINAL_GATE=USB_STAGE3A_HOST_IP_CONFIG_FAILED
elif [ "$LINK_FAILURE" = YES ] || { [ "$HOST_STATIC_ADDR_VERIFIED" = YES ] && [ "$HOST_LINK_ACTIVE_AFTER_IP" != YES ]; }; then
	FINAL_GATE=USB_STAGE3A_IP_SET_LINK_REGRESSION
elif [ -n "$ROUTE_INTERFACE" ] && [ "$ROUTE_INTERFACE" != "$NEW_IF" ]; then
	FINAL_GATE=USB_STAGE3A_ROUTE_COLLISION
elif [ "$HOST_STATIC_ADDR_VERIFIED" = YES ] && [ "$CONNECTED_ROUTE_PRESENT" != YES ]; then
	FINAL_GATE=USB_STAGE3A_NO_CONNECTED_ROUTE
elif [ "$GADGET_SEEN" != YES ] || [ "$CURRENT_AFTER_BOOT" != b ]; then
	FINAL_GATE=USB_STAGE3A_STAGE2_REGRESSION
else
	FINAL_GATE=USB_STAGE3A_INCONCLUSIVE
fi

echo "FINAL_GATE=$FINAL_GATE"
echo "RESULT_LOG=$LOG"
echo 'Stop after Stage3A. No ICMP or HTTP was run.'
exit 0
