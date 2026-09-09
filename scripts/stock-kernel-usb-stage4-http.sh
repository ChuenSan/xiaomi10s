#!/usr/bin/env bash
# Stage4: dynamic macOS NCM discovery, interface-bound L3/HTTP, recovery.
# The only fastboot write is boot_b. Host IPv4 is temporary; no route is added.
set -u

REPO_DIR="${REPO_DIR:-/Volumes/LinuxDev/thyme-mainline}"
ARTIFACT_DIR="${ARTIFACT_DIR:-$REPO_DIR/artifacts/usb-stage4-http}"
DEVICE_IP="10.66.73.1"
HOST_IP="10.66.73.2"
NETMASK="255.255.255.0"
HTTP_PORT=8080
FASTBOOT_TIMEOUT=120
POLL=0.5
PING_COUNT=1
EXPECTED_VENDOR_BOOT_SHA="aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"
EXPECTED_DTBO_SHA="018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"
EXPECTED_VBMETA_SHA="37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c"
EXPECTED_VBMETA_SYSTEM_SHA="3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355"
EXPECTED_VENDOR_BOOT_BYTES=100663296
EXPECTED_DTBO_BYTES=33554432
EXPECTED_VBMETA_BYTES=8192
EXPECTED_VBMETA_SYSTEM_BYTES=4096
TCP_PARSER="$REPO_DIR/scripts/stock-kernel-usb-stage4-http-tcp-parser.awk"

cd "$REPO_DIR" || exit 1
mkdir -p work
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="work/usb-stage4-http-${STAMP}.log"
CAPTURE_LOG="work/usb-stage4-http-${STAMP}.tcpdump.log"
HTTP_BODY_LOG="work/usb-stage4-http-${STAMP}.body"
HTTP_HEADERS_LOG="work/usb-stage4-http-${STAMP}.headers"
HTTP_VERBOSE_LOG="work/usb-stage4-http-${STAMP}.curl.log"
exec > >(tee "$LOG") 2>&1

FLASHED=NO
RECOVERED=NO
TCPDUMP_PID=''

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

parse_tcp_capture() {
	awk -v host="$HOST_IP" -v device="$DEVICE_IP" -v port="$HTTP_PORT" \
		-f "$TCP_PARSER" "$1"
}

descriptor_match() {
	local profile
	profile=$(system_profiler SPUSBDataType 2>/dev/null || true)
	printf '%s\n' "$profile" | grep -Fq 'Stock Kernel USB Stage4 HTTP:' || return 1
	printf '%s\n' "$profile" | grep -Fq 'Product ID: 0x0104' || return 1
	printf '%s\n' "$profile" | grep -Fq 'Vendor ID: 0x1d6b' || return 1
	printf '%s\n' "$profile" | grep -Fq 'Manufacturer: thyme-mainline' || return 1
	printf '%s\n' "$profile" | grep -Fq 'Serial Number: THYME-USB4' || return 1
	return 0
}

print_descriptor_snapshot() {
	echo 'USB_ENUMERATED=YES'
	echo 'USB_VID_PID=1d6b:0104'
	echo 'USB_MANUFACTURER=thyme-mainline'
	echo 'USB_PRODUCT=Stock Kernel USB Stage4 HTTP'
	echo 'USB_SERIAL=THYME-USB4'
	system_profiler SPUSBDataType 2>/dev/null | grep -E \
		'Product ID: 0x0104|Vendor ID: 0x1d6b|Manufacturer: thyme-mainline|Product: Stock Kernel USB Stage4 HTTP|Serial Number: THYME-USB4' || true
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

partition_hash() {
	local partition=$1 bytes=$2
	adb shell su -c "dd if=/dev/block/by-name/$partition bs=$bytes count=1 2>/dev/null | sha256sum" 2>/dev/null |
		tr -d '\r' | awk 'NF { print $1; exit }'
}

verify_partition() {
	local partition=$1 bytes=$2 expected=$3 got
	got=$(partition_hash "$partition" "$bytes")
	echo "$partition bytes=$bytes sha256=${got:-UNAVAILABLE} expected=$expected"
	[ "$got" = "$expected" ] || fail_preflight "$partition stock hash mismatch"
}

fail_preflight() {
	echo "PREFLIGHT_STOP: $*"
	echo 'No Stage4 flash/start was authorized by this script.'
	exit 1
}

stop_tcpdump() {
	if [ -n "$TCPDUMP_PID" ]; then
		kill "$TCPDUMP_PID" 2>/dev/null || true
		wait "$TCPDUMP_PID" 2>/dev/null || true
		TCPDUMP_PID=''
	fi
}

recover_android_a() {
	local current
	stop_tcpdump
	if adb_present; then
		local slot boot
		slot=$(adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r')
		boot=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
		if [ "$slot" = _a ] && [ "$boot" = 1 ]; then
			RECOVERED=YES
			return 0
		fi
	fi
	if ! fastboot_present; then
		echo 'RECOVERY: fastboot unavailable'
		return 1
	fi
	current=$(getvar current-slot)
	echo "RECOVERY_CURRENT_SLOT=$current"
	if [ "$current" != a ]; then
		fastboot set_active a || return 1
	fi
	fastboot reboot || return 1
	if wait_for_android_a; then
		RECOVERED=YES
		return 0
	fi
	return 1
}

on_exit() {
	stop_tcpdump
	if [ "$FLASHED" = YES ] && [ "$RECOVERED" != YES ]; then
		echo 'RECOVERY_ATTEMPT=EXIT_GUARD'
		recover_android_a || true
	fi
}
trap on_exit EXIT

printf '%s\n' '== STOCK_KERNEL_USB_STAGE4_HTTP =='
printf '%s\n' "LOG=$LOG"
printf '%s\n' "CAPTURE_LOG=$CAPTURE_LOG"
printf '%s\n' 'Policy: GHA-built artifact only; boot_b write only; slot A protected; no manual route; no persistent host network change.'
printf '%s\n' 'Test endpoint: 10.66.73.1:8080; host: dynamic THYME enX with 10.66.73.2/24.'

IMAGE="$ARTIFACT_DIR/stock-kernel-usb-stage4-http-boot-v3.img"
INIT="$ARTIFACT_DIR/usb-stage4-http-init"
MANIFEST="$ARTIFACT_DIR/SHA256SUMS"
[ -s "$IMAGE" ] || fail_preflight "missing $IMAGE"
[ -s "$INIT" ] || fail_preflight "missing $INIT"
[ -s "$MANIFEST" ] || fail_preflight "missing $MANIFEST"
[ -s "$TCP_PARSER" ] || fail_preflight "missing $TCP_PARSER"
( cd "$ARTIFACT_DIR" && sha256sum -c SHA256SUMS ) || fail_preflight 'artifact SHA256SUMS mismatch'
IMAGE_BYTES=$(wc -c <"$IMAGE" | tr -d ' ')
EXPECTED_BOOT_SHA=$(awk '$2 == "stock-kernel-usb-stage4-http-boot-v3.img" { print $1; exit }' "$MANIFEST")
BUILD_MARKER=$(strings "$INIT" | sed -n 's/^BUILD=\([0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]\)$/\1/p' | head -n 1)
[ -n "$EXPECTED_BOOT_SHA" ] || fail_preflight 'Stage4 boot SHA missing from manifest'
[ -n "$BUILD_MARKER" ] || fail_preflight 'Stage4 BUILD marker missing from init'
# The artifact's HTTP contract was validated in GHA; do not rerun a local validator.
CURL_HELP=$(curl --help all 2>&1 || true)
printf '%s\n' "$CURL_HELP" | grep -Eq -- '--interface' || fail_preflight 'curl lacks --interface support'
printf '%s\n' "$CURL_HELP" | grep -Eq -- '--ipv4' || fail_preflight 'curl lacks --ipv4 support'
echo 'CURL_INTERFACE_SUPPORTED=YES'
echo 'CURL_IPV4_SUPPORTED=YES'
echo "ARTIFACT_IMAGE_BYTES=$IMAGE_BYTES"
echo "ARTIFACT_BOOT_SHA=$EXPECTED_BOOT_SHA"
echo "ARTIFACT_BUILD_MARKER=$BUILD_MARKER"

if ! sudo -v; then
	fail_preflight 'sudo authorization unavailable; rerun after sudo -v'
fi
echo 'SUDO_AUTHORIZED=YES'

if ! adb_present; then
	if fastboot_present; then
		CURRENT=$(getvar current-slot)
		[ "$CURRENT" = a ] || fail_preflight "current-slot=$CURRENT, expected a"
		fastboot reboot || fail_preflight 'fastboot reboot to Android A failed'
	else
		fail_preflight 'neither adb Android A nor fastboot is present'
	fi
fi
wait_for_android_a || fail_preflight 'Android A did not return'
ADB_SLOT=$(adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r')
ADB_BOOT_COMPLETED=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
echo '--- Android A read-only preflight ---'
echo 'ADB_DEVICE_PRESENT=YES'
echo "slot_suffix=$ADB_SLOT"
echo "boot_completed=$ADB_BOOT_COMPLETED"
[ "$ADB_SLOT" = _a ] || fail_preflight "slot_suffix=$ADB_SLOT"
[ "$ADB_BOOT_COMPLETED" = 1 ] || fail_preflight "boot_completed=$ADB_BOOT_COMPLETED"
ADB_ID=$(adb shell su -c id 2>/dev/null | tr -d '\r')
echo "ROOT_ID=$ADB_ID"
printf '%s\n' "$ADB_ID" | grep -Fq 'uid=0' || fail_preflight 'root read-only access unavailable'

PRE_BOOT_HASH=$(partition_hash boot_b "$IMAGE_BYTES")
echo "boot_b_before_flash bytes=$IMAGE_BYTES sha256=${PRE_BOOT_HASH:-UNAVAILABLE}"
verify_partition vendor_boot_b "$EXPECTED_VENDOR_BOOT_BYTES" "$EXPECTED_VENDOR_BOOT_SHA"
verify_partition dtbo_b "$EXPECTED_DTBO_BYTES" "$EXPECTED_DTBO_SHA"
verify_partition vbmeta_b "$EXPECTED_VBMETA_BYTES" "$EXPECTED_VBMETA_SHA"
verify_partition vbmeta_system_b "$EXPECTED_VBMETA_SYSTEM_BYTES" "$EXPECTED_VBMETA_SYSTEM_SHA"
echo 'OTHER_B_PAYLOADS_STOCK_HASH_MATCH=YES'

adb reboot bootloader || fail_preflight 'adb reboot bootloader failed'
for i in $(seq 1 120); do
	fastboot_present && break
	sleep 0.5
done
fastboot_present || fail_preflight 'Fastboot did not reappear for flash gate'

PRODUCT=$(getvar product)
UNLOCKED=$(getvar unlocked)
CURRENT=$(getvar current-slot)
SUCCESSFUL_B=$(getvar slot-successful:b)
UNBOOTABLE_B=$(getvar slot-unbootable:b)
RETRY_BEFORE=$(getvar slot-retry-count:b)
SNAPSHOT=$(getvar snapshot-update-status)
BATTERY=$(getvar battery-soc-ok)
echo '--- Flash gate ---'
echo "product=$PRODUCT"
echo "unlocked=$UNLOCKED"
echo "current-slot=$CURRENT"
echo "slot-successful:b=$SUCCESSFUL_B"
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
case "$RETRY_BEFORE" in ''|*[!0-9]*) fail_preflight "slot-retry-count:b=$RETRY_BEFORE unavailable" ;; esac
[ "$RETRY_BEFORE" -gt 0 ] || fail_preflight "slot-retry-count:b=$RETRY_BEFORE is not greater than zero"

echo 'STAGE4 HTTP'
echo 'WRITE: boot_b ONLY'
echo 'DEVICE: 10.66.73.1:8080'
echo 'SLOT A: PROTECTED'
echo "BUILD: $BUILD_MARKER"

if ! fastboot flash boot_b "$IMAGE"; then
	echo 'FLASH_FAILED=YES'
	exit 1
fi
FLASHED=YES
echo 'FLASH_BOOT_B_ONLY=YES'
AFTER_FLASH_CURRENT=$(getvar current-slot)
AFTER_FLASH_UNBOOTABLE=$(getvar slot-unbootable:b)
echo "AFTER_FLASH_CURRENT_SLOT=$AFTER_FLASH_CURRENT"
echo "AFTER_FLASH_SLOT_UNBOOTABLE_B=$AFTER_FLASH_UNBOOTABLE"
[ "$AFTER_FLASH_CURRENT" = a ] || exit 1
[ "$AFTER_FLASH_UNBOOTABLE" = no ] || exit 1

# Return to Android A before the single B start, then verify the written prefix.
fastboot reboot || exit 1
wait_for_android_a || exit 1
POST_FLASH_HASH=$(partition_hash boot_b "$IMAGE_BYTES")
echo "boot_b_after_flash bytes=$IMAGE_BYTES sha256=${POST_FLASH_HASH:-UNAVAILABLE} expected=$EXPECTED_BOOT_SHA"
[ "$POST_FLASH_HASH" = "$EXPECTED_BOOT_SHA" ] || exit 1
verify_partition vendor_boot_b "$EXPECTED_VENDOR_BOOT_BYTES" "$EXPECTED_VENDOR_BOOT_SHA"
verify_partition dtbo_b "$EXPECTED_DTBO_BYTES" "$EXPECTED_DTBO_SHA"
verify_partition vbmeta_b "$EXPECTED_VBMETA_BYTES" "$EXPECTED_VBMETA_SHA"
verify_partition vbmeta_system_b "$EXPECTED_VBMETA_SYSTEM_BYTES" "$EXPECTED_VBMETA_SYSTEM_SHA"
echo 'POST_FLASH_OTHER_B_PAYLOADS_STOCK=YES'

adb reboot bootloader || exit 1
for i in $(seq 1 120); do
	fastboot_present && break
	sleep 0.5
done
fastboot_present || exit 1
CURRENT=$(getvar current-slot)
[ "$CURRENT" = a ] || exit 1
RETRY_BEFORE_START=$(getvar slot-retry-count:b)
echo "RETRY_BEFORE_START=$RETRY_BEFORE_START"
fastboot set_active b || exit 1
AFTER_SET_ACTIVE=$(getvar current-slot)
RETRY_AFTER_SET_ACTIVE=$(getvar slot-retry-count:b)
UNBOOTABLE_AFTER_SET_ACTIVE=$(getvar slot-unbootable:b)
echo "AFTER_SET_ACTIVE=$AFTER_SET_ACTIVE"
echo "RETRY_AFTER_SET_ACTIVE=$RETRY_AFTER_SET_ACTIVE"
echo "UNBOOTABLE_AFTER_SET_ACTIVE=$UNBOOTABLE_AFTER_SET_ACTIVE"
[ "$AFTER_SET_ACTIVE" = b ] || exit 1
[ "$UNBOOTABLE_AFTER_SET_ACTIVE" = no ] || exit 1
case "$RETRY_AFTER_SET_ACTIVE" in ''|*[!0-9]*) exit 1 ;; esac
[ "$RETRY_AFTER_SET_ACTIVE" -gt 0 ] || exit 1

echo 'issuing exactly one Stage4 start: fastboot reboot'
fastboot reboot || exit 1
T_FINISHED=$(now)

echo "fastboot_reboot_finished_unix=$T_FINISHED"

BASE_EN=$(en_list | sort -u | tr '\n' ' ')
echo "BASE_EN=$BASE_EN"
PRE_ROUTE=$(route -n get "$DEVICE_IP" 2>&1 || true)
echo 'route -n get 10.66.73.1 before gadget:'
printf '%s\n' "$PRE_ROUTE"
PRE_ROUTE_IF=$(printf '%s\n' "$PRE_ROUTE" | route_interface)
echo "PRETEST_ROUTE_INTERFACE=${PRE_ROUTE_IF:-NONE}"
case "$PRE_ROUTE_IF" in utun*) echo 'PREEXISTING_ROUTE_COLLISION=YES' ;; *) echo 'PREEXISTING_ROUTE_COLLISION=NO' ;; esac

T_DISAPPEAR=''
T_GADGET=''
T_EN=''
T_EN_GONE=''
T_GADGET_GONE=''
T_REAPPEAR=''
NEW_IF=''
USB_IDENTITY_MATCHED=NO
USB_ENUMERATED=NO
NEW_IF_FOUND=NO
HOST_LINK_ACTIVE_BEFORE_IP=NO
HOST_LINK_ACTIVE_AFTER_IP=NO
HOST_STATIC_ADDR_VERIFIED=NO
CONNECTED_ROUTE_PRESENT=NO
ROUTE_INTERFACE=''
ROUTE_GATEWAY=''
ROUTE_FLAGS=''
CONFIG_RC=125
IP_ATTEMPTED=NO
TEST_BLOCKED=NO
TEST_ATTEMPTED=NO
L3_REGRESSION=NO
PING_RC=125
PING_SENT=0
PING_RECEIVED=0
PING_LOSS=UNAVAILABLE
PING_OUTPUT=''
CURL_RC=125
CURL_CODE=000
CURL_ATTEMPTED=NO
CURL_CONNECTED=NO
HTTP_STATUS=NO
HTTP_HEADERS_VALID=NO
HTTP_CONTENT_TYPE=NO
HTTP_BODY_IDENTITY=NO
HTTP_BUILD_MATCH=NO
TCPDUMP_STARTED=NO
TCP_SYN_CAPTURED=NO
TCP_SYNACK_CAPTURED=NO
TCP_ACK_CAPTURED=NO
TCP_HTTP_DATA_CAPTURED=NO
HTTP_GET_CAPTURED=NO
HTTP_200_CAPTURED=NO
ARP_REQUEST_CAPTURED=NO
ARP_REPLY_CAPTURED=NO
ICMP_REQUEST_CAPTURED=NO
ICMP_REPLY_CAPTURED=NO
TEST_WINDOW_EXPIRED=NO
RECOVERY_SLOT=''
RECOVERY_BOOT_COMPLETED=''
DEADLINE=$(python3 -c "print(float('$T_FINISHED') + $FASTBOOT_TIMEOUT)")

while python3 -c "import time; raise SystemExit(0 if time.time() < $DEADLINE else 1)"; do
	FB=NO
	fastboot_present && FB=YES
	if [ "$FB" = NO ] && [ -z "$T_DISAPPEAR" ]; then
		T_DISAPPEAR=$(now)
		echo "fastboot_disappear_unix=$T_DISAPPEAR"
	fi

	DESC=NO
	if descriptor_match; then DESC=YES; fi
	if [ "$DESC" = YES ] && [ "$USB_ENUMERATED" = NO ]; then
		USB_ENUMERATED=YES
		USB_IDENTITY_MATCHED=YES
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
			echo "new_en_appear_unix=$T_EN"
			echo "NEW_IF=$NEW_IF"
			echo "HOST_MAC=$(interface_mac "$NEW_IF")"
			ifconfig "$NEW_IF" 2>/dev/null || true
		fi
	fi

	if [ -n "$NEW_IF" ] && [ "$IP_ATTEMPTED" = NO ]; then
		IF_STATE=$(ifconfig "$NEW_IF" 2>/dev/null || true)
		if printf '%s\n' "$IF_STATE" | grep -Eq '^[[:space:]]*status: active'; then
			HOST_LINK_ACTIVE_BEFORE_IP=YES
			IP_ATTEMPTED=YES
			echo "CONFIG_COMMAND=sudo ifconfig $NEW_IF inet $HOST_IP netmask $NETMASK"
			sudo -n ifconfig "$NEW_IF" inet "$HOST_IP" netmask "$NETMASK"
			CONFIG_RC=$?
			echo "CONFIG_RETURN=$CONFIG_RC"
			AFTER_IP=$(ifconfig "$NEW_IF" 2>/dev/null || true)
			printf '%s\n' "$AFTER_IP"
			if printf '%s\n' "$AFTER_IP" | grep -Eq "inet $HOST_IP([[:space:]]|$)" && \
				printf '%s\n' "$AFTER_IP" | grep -Eq 'netmask (0xffffff00|255\.255\.255\.0)'; then
				HOST_STATIC_ADDR_VERIFIED=YES
			fi
			if printf '%s\n' "$AFTER_IP" | grep -Eq '^[[:space:]]*status: active'; then
				HOST_LINK_ACTIVE_AFTER_IP=YES
			fi
			echo "HOST_STATIC_ADDR_VERIFIED=$HOST_STATIC_ADDR_VERIFIED"
			echo "HOST_LINK_ACTIVE_AFTER_IP=$HOST_LINK_ACTIVE_AFTER_IP"
			if [ "$CONFIG_RC" -ne 0 ] || [ "$HOST_STATIC_ADDR_VERIFIED" != YES ] || \
				[ "$HOST_LINK_ACTIVE_AFTER_IP" != YES ]; then
				L3_REGRESSION=YES
				TEST_BLOCKED=YES
				echo 'HOST_L3_GATE=FAILED; refusing ping/curl'
			elif [ "$CONFIG_RC" -eq 0 ] && [ "$HOST_STATIC_ADDR_VERIFIED" = YES ]; then
				ROUTE_DURING=$(route -n get "$DEVICE_IP" 2>&1 || true)
				echo 'route -n get 10.66.73.1 during Stage4:'
				printf '%s\n' "$ROUTE_DURING"
				ROUTE_INTERFACE=$(printf '%s\n' "$ROUTE_DURING" | route_interface)
				ROUTE_GATEWAY=$(printf '%s\n' "$ROUTE_DURING" | route_field gateway)
				ROUTE_FLAGS=$(printf '%s\n' "$ROUTE_DURING" | route_field flags)
				NETSTAT_DURING=$(netstat -rn -f inet 2>&1 || true)
				CONNECTED_LINES=$(printf '%s\n' "$NETSTAT_DURING" | grep '10\.66\.73' || true)
				printf '%s\n' "${CONNECTED_LINES:-NONE}"
				if [ -n "$CONNECTED_LINES" ] && printf '%s\n' "$CONNECTED_LINES" | grep -Fq "$NEW_IF"; then
					CONNECTED_ROUTE_PRESENT=YES
				fi
				echo "ROUTE_INTERFACE=${ROUTE_INTERFACE:-NONE}"
				echo "ROUTE_GATEWAY=${ROUTE_GATEWAY:-NONE}"
				echo "ROUTE_FLAGS=${ROUTE_FLAGS:-NONE}"
				echo "CONNECTED_ROUTE_PRESENT=$CONNECTED_ROUTE_PRESENT"
				if [ "$ROUTE_INTERFACE" != "$NEW_IF" ] || [ "$CONNECTED_ROUTE_PRESENT" != YES ]; then
					TEST_BLOCKED=YES
					echo "ROUTE_COLLISION=YES; refusing ping/curl"
				fi
			fi
		elif [ -n "$T_EN" ]; then
			ELAPSED=$(python3 -c "import time; print(time.time() - float('$T_EN'))")
			if python3 -c "raise SystemExit(0 if float('$ELAPSED') > 8 else 1)"; then
				L3_REGRESSION=YES
				TEST_BLOCKED=YES
				IP_ATTEMPTED=YES
				echo 'HOST_LINK_ACTIVE_BEFORE_IP=NO'
			fi
		fi
	fi

	if [ "$TEST_ATTEMPTED" = NO ] && [ "$TEST_BLOCKED" = NO ] && \
		[ "$HOST_STATIC_ADDR_VERIFIED" = YES ] && [ "$HOST_LINK_ACTIVE_AFTER_IP" = YES ] && \
		[ "$ROUTE_INTERFACE" = "$NEW_IF" ] && [ "$CONNECTED_ROUTE_PRESENT" = YES ]; then
		TEST_ATTEMPTED=YES
		echo "CAPTURE_COMMAND=sudo tcpdump -ni $NEW_IF 'arp or icmp or tcp port 8080'"
		sudo -n tcpdump -ni "$NEW_IF" -l 'arp or icmp or tcp port 8080' >"$CAPTURE_LOG" 2>&1 &
		TCPDUMP_PID=$!
		sleep 0.2
		if kill -0 "$TCPDUMP_PID" 2>/dev/null; then TCPDUMP_STARTED=YES; fi

		PING_HELP=$(ping -h 2>&1 || true)
		if printf '%s\n' "$PING_HELP" | grep -Eq -- '(-b boundif|\[-b boundif\])' && \
			printf '%s\n' "$PING_HELP" | grep -Eq -- '(-S src_addr|\[-S src_addr\])'; then
			PING_COMMAND="ping -n -S $HOST_IP -b $NEW_IF -c 1 -W 1000 -t 6 $DEVICE_IP"
			echo "PING_COMMAND=$PING_COMMAND"
			PING_OUTPUT=$(ping -n -S "$HOST_IP" -b "$NEW_IF" -c "$PING_COUNT" -W 1000 -t 6 "$DEVICE_IP" 2>&1)
			PING_RC=$?
			printf '%s\n' "$PING_OUTPUT"
			PING_SENT=$(printf '%s\n' "$PING_OUTPUT" | sed -n 's/^\([0-9][0-9]*\) packets transmitted, \([0-9][0-9]*\) packets received[,\.].*/\1/p' | tail -n 1)
			PING_RECEIVED=$(printf '%s\n' "$PING_OUTPUT" | sed -n 's/^\([0-9][0-9]*\) packets transmitted, \([0-9][0-9]*\) packets received[,\.].*/\2/p' | tail -n 1)
			PING_LOSS=$(printf '%s\n' "$PING_OUTPUT" | sed -n 's/.* \([0-9][0-9.]*%\) packet loss.*/\1/p' | tail -n 1)
			[ -n "$PING_SENT" ] || PING_SENT=0
			[ -n "$PING_RECEIVED" ] || PING_RECEIVED=0
			[ -n "$PING_LOSS" ] || PING_LOSS=UNAVAILABLE
			echo "PING_RC=$PING_RC"
			echo "PING_SENT=$PING_SENT"
			echo "PING_RECEIVED=$PING_RECEIVED"
			echo "PING_LOSS=$PING_LOSS"
			if [ "$PING_RC" -ne 0 ] || [ "$PING_RECEIVED" -ne "$PING_COUNT" ]; then
				L3_REGRESSION=YES
				TEST_BLOCKED=YES
				echo 'FINAL_GATE_CANDIDATE=USB_STAGE4_L3_REGRESSION; curl forbidden'
			fi
		else
			TEST_BLOCKED=YES
			echo 'PING_BINDING_CAPABILITY=UNAVAILABLE; curl forbidden'
		fi

		if [ "$TEST_BLOCKED" = NO ]; then
			CURL_ATTEMPTED=YES
			echo "CURL_COMMAND=curl --interface $NEW_IF --ipv4 --max-time 5 -v -D $HTTP_HEADERS_LOG -o $HTTP_BODY_LOG -w '%{http_code}' http://$DEVICE_IP:$HTTP_PORT/"
			CURL_CODE=$(curl --interface "$NEW_IF" --ipv4 --max-time 5 -v \
				-D "$HTTP_HEADERS_LOG" -o "$HTTP_BODY_LOG" -w '%{http_code}' \
				"http://$DEVICE_IP:$HTTP_PORT/" 2>"$HTTP_VERBOSE_LOG")
			CURL_RC=$?
			echo "CURL_RC=$CURL_RC"
			echo "CURL_CODE=$CURL_CODE"
			if grep -Eq 'Connected to 10\.66\.73\.1.*port 8080' "$HTTP_VERBOSE_LOG"; then CURL_CONNECTED=YES; fi
			if grep -Fq '< HTTP/1.1 200 OK' "$HTTP_VERBOSE_LOG" && [ "$CURL_CODE" = 200 ]; then HTTP_STATUS=YES; fi
			if grep -Eiq '^< Content-Type: text/plain' "$HTTP_VERBOSE_LOG"; then HTTP_CONTENT_TYPE=YES; fi
			if python3 - "$HTTP_HEADERS_LOG" "$HTTP_BODY_LOG" <<'PY'
import sys
from pathlib import Path
headers = Path(sys.argv[1]).read_bytes().replace(b"\r\n", b"\n").splitlines()
body = Path(sys.argv[2]).read_bytes()
if not headers or headers[0] != b"HTTP/1.1 200 OK":
    raise SystemExit(1)
values = {}
for line in headers[1:]:
    if b":" in line:
        key, value = line.split(b":", 1)
        values[key.lower()] = value.strip()
try:
    length = int(values[b"content-length"])
except (KeyError, ValueError):
    raise SystemExit(1)
if length != len(body) or values.get(b"content-type") != b"text/plain":
    raise SystemExit(1)
PY
			then
				HTTP_HEADERS_VALID=YES
			fi
			for line in \
				'CONTROL=STOCK_KERNEL_USB_STAGE4' \
				'DEVICE=thyme' \
				'KERNEL=4.19.157-perf' \
				'USB=NCM' \
				'DEVICE_IP=10.66.73.1' \
				'HTTP_READY=YES' \
				'STAGE0_USB_ENUM=PASS' \
				'STAGE1_LINK=PASS' \
				'STAGE2_DEVICE_IP=PASS' \
				'STAGE3_ICMP=PASS'; do
				if ! grep -Fxq "$line" "$HTTP_BODY_LOG"; then HTTP_BODY_IDENTITY=NO; break; fi
				HTTP_BODY_IDENTITY=YES
			done
			if grep -Fxq "BUILD=$BUILD_MARKER" "$HTTP_BODY_LOG"; then HTTP_BUILD_MATCH=YES; fi
		fi
	fi

	if [ -n "$CAPTURE_LOG" ] && [ -f "$CAPTURE_LOG" ]; then
		HOST_RE=$(printf '%s' "$HOST_IP" | sed 's/\./\\./g')
		DEVICE_RE=$(printf '%s' "$DEVICE_IP" | sed 's/\./\\./g')
		if grep -Eq "ARP.*Request.*$DEVICE_RE" "$CAPTURE_LOG"; then ARP_REQUEST_CAPTURED=YES; fi
		if grep -Eq "ARP.*Reply.*$DEVICE_RE" "$CAPTURE_LOG"; then ARP_REPLY_CAPTURED=YES; fi
		if grep -Eq "$HOST_RE.*ICMP echo request" "$CAPTURE_LOG"; then ICMP_REQUEST_CAPTURED=YES; fi
		if grep -Eq "$DEVICE_RE.*ICMP echo reply" "$CAPTURE_LOG"; then ICMP_REPLY_CAPTURED=YES; fi
		TCP_PARSE_OUTPUT=$(parse_tcp_capture "$CAPTURE_LOG" 2>/dev/null || true)
		if printf '%s\n' "$TCP_PARSE_OUTPUT" | grep -Fqx 'SYN'; then TCP_SYN_CAPTURED=YES; fi
		if printf '%s\n' "$TCP_PARSE_OUTPUT" | grep -Fqx 'SYNACK'; then TCP_SYNACK_CAPTURED=YES; fi
		if grep -Eq "$HOST_RE\.[0-9]+ > $DEVICE_RE\.8080: Flags \[\.\]" "$CAPTURE_LOG"; then TCP_ACK_CAPTURED=YES; fi
		if printf '%s\n' "$TCP_PARSE_OUTPUT" | grep -Fqx 'HTTP_DATA'; then TCP_HTTP_DATA_CAPTURED=YES; fi
		if printf '%s\n' "$TCP_PARSE_OUTPUT" | grep -Fqx 'HTTP_GET'; then HTTP_GET_CAPTURED=YES; fi
		if printf '%s\n' "$TCP_PARSE_OUTPUT" | grep -Fqx 'HTTP_200'; then HTTP_200_CAPTURED=YES; fi
	fi

	if [ -n "$NEW_IF" ] && [ -z "$T_EN_GONE" ] && ! ifconfig "$NEW_IF" >/dev/null 2>&1; then
		T_EN_GONE=$(now)
		echo "new_en_disappear_unix=$T_EN_GONE if=$NEW_IF"
	fi
	if [ "$USB_ENUMERATED" = YES ] && [ "$FB" = YES ] && [ "$DESC" = NO ] && [ -z "$T_GADGET_GONE" ]; then
		T_GADGET_GONE=$(now)
		echo "gadget_disappear_unix=$T_GADGET_GONE"
	fi
	if [ "$USB_ENUMERATED" = YES ] && [ "$FB" = YES ] && [ "$DESC" = NO ]; then
		T_REAPPEAR=$(now)
		echo "fastboot_reappear_unix=$T_REAPPEAR"
		break
	fi
	sleep "$POLL"
done

if [ -z "$T_REAPPEAR" ]; then
	TEST_WINDOW_EXPIRED=YES
	echo 'TEST_WINDOW_EXPIRED=YES'
fi
stop_tcpdump

if fastboot_present; then
	RETRY_AFTER_BOOT=$(getvar slot-retry-count:b)
	UNBOOTABLE_AFTER_BOOT=$(getvar slot-unbootable:b)
	CURRENT_AFTER_BOOT=$(getvar current-slot)
	echo '--- Fastboot after Stage4 window ---'
	echo "current-slot=$CURRENT_AFTER_BOOT"
	echo "slot-retry-count:b=$RETRY_AFTER_BOOT"
	echo "slot-unbootable:b=$UNBOOTABLE_AFTER_BOOT"
	recover_android_a || true
else
	echo 'FASTBOOT_AFTER_STAGE4=NO'
	recover_android_a || true
fi
if adb_present; then
	RECOVERY_SLOT=$(adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r')
	RECOVERY_BOOT_COMPLETED=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
fi
PSTORE_RAW=''
if [ "$RECOVERED" = YES ] && adb_present; then
	PSTORE_RAW=$(adb shell su -c 'for f in /sys/fs/pstore/* /proc/last_kmsg; do if [ -f "$f" ]; then grep "THYME-USB4:" "$f"; fi; done' 2>/dev/null | tr -d '\r' || true)
fi
printf '%s\n' "$PSTORE_RAW" >"$LOG.pstore"
DEVICE_KMSG_AVAILABLE=NO
DEVICE_LISTEN_OK=NO
if printf '%s\n' "$PSTORE_RAW" | grep -Fq 'THYME-USB4:INIT'; then DEVICE_KMSG_AVAILABLE=YES; fi
if printf '%s\n' "$PSTORE_RAW" | grep -Fq 'THYME-USB4:LISTEN_OK:10.66.73.1:8080'; then DEVICE_LISTEN_OK=YES; fi
for marker in HTTP_READY ACCEPT_OK REQUEST_RX HTTP_200_SENT; do
	if printf '%s\n' "$PSTORE_RAW" | grep -Fq "THYME-USB4:$marker"; then
		echo "DEVICE_$marker=YES"
	else
		echo "DEVICE_$marker=NO"
	fi
done

printf '%s\n' '--- Stage4 observation summary ---'
echo "USB_IDENTITY_MATCHED=$USB_IDENTITY_MATCHED"
echo "NEW_IF_FOUND=$NEW_IF_FOUND"
echo "NEW_IF=${NEW_IF:-NONE}"
echo "HOST_STATIC_ADDR_VERIFIED=$HOST_STATIC_ADDR_VERIFIED"
echo "HOST_LINK_ACTIVE_BEFORE_IP=$HOST_LINK_ACTIVE_BEFORE_IP"
echo "HOST_LINK_ACTIVE_AFTER_IP=$HOST_LINK_ACTIVE_AFTER_IP"
echo "ROUTE_INTERFACE=${ROUTE_INTERFACE:-NONE}"
echo "CONNECTED_ROUTE_PRESENT=$CONNECTED_ROUTE_PRESENT"
echo "PING_SOURCE=$HOST_IP"
echo "PING_DESTINATION=$DEVICE_IP"
echo "PING_SENT=$PING_SENT"
echo "PING_RECEIVED=$PING_RECEIVED"
echo "PING_LOSS=$PING_LOSS"
echo "CURL_BINDING=${NEW_IF:-NONE}"
echo "CURL_ATTEMPTED=$CURL_ATTEMPTED"
echo "CURL_CONNECTED=$CURL_CONNECTED"
echo "HTTP_STATUS_200=$HTTP_STATUS"
echo "HTTP_CONTENT_TYPE=$HTTP_CONTENT_TYPE"
echo "HTTP_HEADERS_VALID=$HTTP_HEADERS_VALID"
echo "HTTP_BODY_IDENTITY=$HTTP_BODY_IDENTITY"
echo "HTTP_BUILD_MATCH=$HTTP_BUILD_MATCH"
echo "TCPDUMP_USED=$TCPDUMP_STARTED"
echo "TCPDUMP_CAPTURE_INTERFACE=${NEW_IF:-NONE}"
echo "ARP_REQUEST_CAPTURED=$ARP_REQUEST_CAPTURED"
echo "ARP_REPLY_CAPTURED=$ARP_REPLY_CAPTURED"
echo "ICMP_REQUEST_CAPTURED=$ICMP_REQUEST_CAPTURED"
echo "ICMP_REPLY_CAPTURED=$ICMP_REPLY_CAPTURED"
echo "TCP_SYN_CAPTURED=$TCP_SYN_CAPTURED"
echo "TCP_SYNACK_CAPTURED=$TCP_SYNACK_CAPTURED"
echo "TCP_ACK_CAPTURED=$TCP_ACK_CAPTURED"
echo "TCP_HTTP_DATA_CAPTURED=$TCP_HTTP_DATA_CAPTURED"
echo "HTTP_GET_CAPTURED=$HTTP_GET_CAPTURED"
echo "HTTP_200_CAPTURED=$HTTP_200_CAPTURED"
echo "DEVICE_KMSG_AVAILABLE=$DEVICE_KMSG_AVAILABLE"
echo "DEVICE_LISTEN_OK=$DEVICE_LISTEN_OK"
echo "RECOVERY_SLOT=${RECOVERY_SLOT:-NONE}"
echo "RECOVERY_BOOT_COMPLETED=${RECOVERY_BOOT_COMPLETED:-NONE}"
echo "ANDROID_A_RESTORED=$RECOVERED"

overall_http_identity=NO
if [ "$HTTP_BODY_IDENTITY" = YES ] && [ "$HTTP_BUILD_MATCH" = YES ]; then overall_http_identity=YES; fi
FINAL_GATE=USB_STAGE4_INCONCLUSIVE
if [ "$L3_REGRESSION" = YES ]; then
	FINAL_GATE=USB_STAGE4_L3_REGRESSION
elif [ "$DEVICE_KMSG_AVAILABLE" = YES ] && [ "$DEVICE_LISTEN_OK" = NO ]; then
	FINAL_GATE=USB_STAGE4_DEVICE_HTTP_SETUP_FAILED
elif [ "$CURL_CONNECTED" = YES ] && [ "$HTTP_STATUS" = YES ] && \
	[ "$overall_http_identity" != YES ]; then
	FINAL_GATE=USB_STAGE4_HTTP_IDENTITY_MISMATCH
elif [ "$CURL_CONNECTED" != YES ] && [ "$CURL_ATTEMPTED" = YES ]; then
	FINAL_GATE=USB_STAGE4_TCP_CONNECT_FAILED
elif [ "$CURL_CONNECTED" = YES ] && { [ "$HTTP_STATUS" != YES ] || [ "$HTTP_HEADERS_VALID" != YES ]; }; then
	FINAL_GATE=USB_STAGE4_HTTP_APPLICATION_FAILED
elif [ "$USB_IDENTITY_MATCHED" = YES ] && [ "$NEW_IF_FOUND" = YES ] && \
	[ "$HOST_STATIC_ADDR_VERIFIED" = YES ] && [ "$HOST_LINK_ACTIVE_AFTER_IP" = YES ] && \
	[ "$ROUTE_INTERFACE" = "$NEW_IF" ] && [ "$CONNECTED_ROUTE_PRESENT" = YES ] && \
	[ "$PING_RECEIVED" -eq "$PING_COUNT" ] && [ "$CURL_CONNECTED" = YES ] && \
	[ "$HTTP_STATUS" = YES ] && [ "$HTTP_HEADERS_VALID" = YES ] && \
	[ "$overall_http_identity" = YES ] && [ "$TCPDUMP_STARTED" = YES ] && \
	[ "$TCP_SYN_CAPTURED" = YES ] && [ "$TCP_SYNACK_CAPTURED" = YES ] && \
	[ "$TCP_ACK_CAPTURED" = YES ] && [ "$TCP_HTTP_DATA_CAPTURED" = YES ] && \
	[ "$HTTP_GET_CAPTURED" = YES ] && [ "$HTTP_200_CAPTURED" = YES ] && \
	[ "$RECOVERY_SLOT" = _a ] && [ "$RECOVERY_BOOT_COMPLETED" = 1 ]; then
	FINAL_GATE=USB_STAGE4_HTTP_LIVENESS_PASS
elif [ "$CURL_CONNECTED" = YES ] && [ "$HTTP_STATUS" = YES ] && [ "$overall_http_identity" = YES ]; then
	FINAL_GATE=USB_STAGE4_INCONCLUSIVE
elif [ "$RECOVERED" = YES ] && [ "$USB_IDENTITY_MATCHED" = YES ] && [ "$NEW_IF_FOUND" = YES ] && \
	[ "$TCPDUMP_STARTED" = YES ] && [ "$TCP_SYN_CAPTURED" = NO ]; then
	FINAL_GATE=USB_STAGE4_TCP_CONNECT_FAILED
fi

echo "FINAL_GATE=$FINAL_GATE"
echo "RESULT_LOG=$LOG"
echo "PACKET_CAPTURE_LOG=$CAPTURE_LOG"
echo "PSTORE_LOG=$LOG.pstore"
echo "BUILD_MARKER=$BUILD_MARKER"
echo 'No persistent host network change, manual route add, VPN change, or slot-A write was performed.'

[ "$FINAL_GATE" = USB_STAGE4_HTTP_LIVENESS_PASS ]
