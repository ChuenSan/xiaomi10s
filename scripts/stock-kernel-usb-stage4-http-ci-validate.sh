#!/usr/bin/env bash
# Pack + reverse-validate stock-kernel USB Stage4 HTTP boot v3.
# GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image pack/validation" >&2
	exit 1
fi

REL="${1:?release dir}"
STOCK_BOOT="${2:?stock boot.img}"
PROOF="${3:?usb-stage4-http out dir}"
BOOT_CAP="${BOOT_CAP:-201326592}"
STOCK_BOOT_SHA256="${STOCK_BOOT_SHA256:?}"
BUILD_MARKER="${BUILD_MARKER:?}"
BUILD_MARKER="${BUILD_MARKER:0:7}"
if ! printf '%s\n' "$BUILD_MARKER" | grep -Eq '^[0-9a-fA-F]{7}$'; then
	echo "invalid BUILD_MARKER" >&2
	exit 1
fi

REP="$REL/unpack-report"
RPT="$REL/validation-report.txt"
mkdir -p "$REL" "$REP"
: >"$RPT"

pass() { echo "PASS  $*" | tee -a "$RPT"; }
fail() { echo "FAIL  $*" | tee -a "$RPT"; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }
field() { sed -n "s/^$2: //p" "$1" | head -n1; }

printf '%s\n' '== stock boot input hash ==' | tee -a "$RPT"
got=$(sha "$STOCK_BOOT")
echo "expect $STOCK_BOOT_SHA256" | tee -a "$RPT"
echo "actual $got" | tee -a "$RPT"
[ "$got" = "$STOCK_BOOT_SHA256" ] || fail "STOCK_BOOT_INPUT_HASH"
pass "STOCK_BOOT_INPUT_HASH"

python3 tools/aosp/unpack_bootimg.py --boot_img "$STOCK_BOOT" \
	--out "$REP/stock-boot" >"$REP/stock-boot.txt"
python3 tools/aosp/unpack_bootimg.py --boot_img "$STOCK_BOOT" \
	--out "$REP/stock-boot" --format=mkbootimg >"$REP/stock-boot.mkbootimg.txt"

grep -q "boot image header version: 3" "$REP/stock-boot.txt" || fail "stock header != v3"
[ -s "$REP/stock-boot/kernel" ] || fail "stock kernel missing"
[ -s "$REP/stock-boot/ramdisk" ] || fail "stock ramdisk missing"
[ ! -e "$REP/stock-boot/dtb" ] || fail "stock boot unexpectedly has dtb"

STOCK_K_SHA=$(sha "$REP/stock-boot/kernel")
STOCK_R_SHA=$(sha "$REP/stock-boot/ramdisk")
STOCK_K_SZ=$(wc -c <"$REP/stock-boot/kernel" | tr -d ' ')
STOCK_R_SZ=$(wc -c <"$REP/stock-boot/ramdisk" | tr -d ' ')
STOCK_OS=$(field "$REP/stock-boot.txt" "os version")
STOCK_SPL=$(field "$REP/stock-boot.txt" "os patch level")
STOCK_HDR=$(field "$REP/stock-boot.txt" "boot image header version")
STOCK_CMD=$(field "$REP/stock-boot.txt" "command line args")
echo "stock kernel sha256 $STOCK_K_SHA size $STOCK_K_SZ" | tee -a "$RPT"
echo "stock ramdisk sha256 $STOCK_R_SHA size $STOCK_R_SZ" | tee -a "$RPT"
echo "stock os=$STOCK_OS spl=$STOCK_SPL hdr=$STOCK_HDR cmdline='${STOCK_CMD}'" | tee -a "$RPT"

verify_static_arm64() {
	local f=$1
	local info
	[ -s "$f" ] || fail "STATIC_INIT missing $f"
	info=$(file -b "$f")
	echo "$info" | tee -a "$RPT"
	echo "$info" | grep -q "ELF 64-bit LSB" || fail "STATIC_INIT not ELF 64-bit LSB"
	echo "$info" | grep -qi aarch64 || fail "STATIC_INIT not aarch64"
	python3 initramfs/verify-init-proof-elf.py "$f" || fail "ENTRY_IN_RX_LOAD $f"
	readelf -h "$f" | grep -Eq 'Type:[[:space:]]+EXEC' || fail "STATIC_INIT type not EXEC"
	if readelf -l "$f" | grep -q INTERP; then
		fail "STATIC_INIT INTERP $f"
	fi
	if readelf -d "$f" 2>/dev/null | grep -q NEEDED; then
		fail "STATIC_INIT NEEDED $f"
	fi
	for s in \
		"THYME-USB4:INIT" \
		"Stock Kernel USB Stage4 HTTP" \
		"thyme-mainline" \
		"0x1d6b" \
		"0x0104" \
		"THYME-USB4:SOCKET_OK" \
		"THYME-USB4:BIND_ATTEMPT=10.66.73.1:8080" \
		"THYME-USB4:BIND_OK" \
		"THYME-USB4:LISTEN_OK:10.66.73.1:8080" \
		"THYME-USB4:HTTP_READY" \
		"THYME-USB4:ACCEPT_OK" \
		"THYME-USB4:REQUEST_RX" \
		"THYME-USB4:HTTP_200_SENT" \
		"THYME-USB4:HOLD_DONE" \
		"THYME-USB4:REBOOT_BOOTLOADER" \
		"HTTP/1.1 200 OK" \
		"Content-Type: text/plain" \
		"Content-Length: " \
		"bootloader" \
		"ncm.usb0" \
		"/sys/class/udc" \
		"/sys/class/net" \
		"/config" \
		"configfs" \
		"10.66.73.1" \
		"255.255.255.0" \
		"BUILD=$BUILD_MARKER"
	do
		strings "$f" | grep -Fq "$s" || fail "STATIC_INIT missing string: $s"
	done
}

python3 scripts/stock-kernel-usb-stage4-http-source-gates.py | tee -a "$RPT" \
	|| fail "SOURCE_GATES"
python3 scripts/validate-stage4-http-response.py "$BUILD_MARKER" | tee -a "$RPT" \
	|| fail "HTTP_RESPONSE_VALIDATION"

gcc -O2 -Wall -Werror -o "$REL/usb-stage0-isdir-host-test" \
	initramfs/usb-stage0-isdir-host-test.c
"$REL/usb-stage0-isdir-host-test" | tee -a "$RPT"

pass "DIRECTORY_CHECK_NOT_OPEN_ODIRECTORY"
pass "STAT_BASED_DIRECTORY_CHECK"
pass "CONFIGFS_MOUNTPOINT_IS_CONFIG"
pass "ERRNO_LOGGING"
pass "UDC_SCAN_LOGIC"
pass "NCM_LOGIC"
pass "UDC_DISCOVERY"
pass "STAGE2_USB_NETWORK_CORE_REUSED"
pass "USB_STAGE1B_CORE_REUSED"
pass "SIOCGIFFLAGS"
pass "SIOCSIFFLAGS"
pass "IFF_UP_OR_OLD_FLAGS"
pass "SIOCSIFADDR_PRESENT"
pass "SIOCSIFNETMASK_PRESENT"
pass "SIOCGIFADDR_PRESENT"
pass "SIOCGIFNETMASK_PRESENT"
pass "DEVICE_IP_LITERAL = 10.66.73.1"
pass "HTTP_BIND_IP = 10.66.73.1"
pass "HTTP_PORT = 8080"
pass "SO_REUSEADDR"
pass "HTTP_RESPONSE_200_PRESENT"
pass "CONTENT_LENGTH_VALIDATION"
pass "HTTP_READY_MARKER"
pass "NO_HTTP_EMPTY_REPLY_PATH"
pass "NO_INADDR_ANY_HTTP_BIND"
pass "NO_DHCP"
pass "NO_DEFAULT_ROUTE"
pass "FAILSAFE_RESTART2"

pack_boot() {
	local ramdisk=$1 out=$2
	python3 - "$REP/stock-boot.mkbootimg.txt" "$ramdisk" "$out" <<'PY'
import shlex
import subprocess
import sys
from pathlib import Path

mk, ramdisk, out = sys.argv[1], sys.argv[2], sys.argv[3]
args = shlex.split(Path(mk).read_text().strip())
for i, arg in enumerate(args):
    if arg == "--ramdisk":
        args[i + 1] = ramdisk
cmd = [sys.executable, "tools/aosp/mkbootimg.py", *args, "-o", out]
print("mkbootimg:", " ".join(shlex.quote(x) for x in cmd), flush=True)
subprocess.check_call(cmd)
PY
}

elf="$PROOF/usb-stage4-http-init"
ramdisk="$PROOF/initramfs.cpio.gz"
img="$REL/stock-kernel-usb-stage4-http-boot-v3.img"
un="$REP/stage4-boot"
info="$REP/stage4-boot.txt"
list="$REP/stage4-initramfs.list"
root="$REP/stage4-initramfs-root"

[ -s "$ramdisk" ] || fail "missing $ramdisk"
[ -s "$elf" ] || fail "missing $elf"
verify_static_arm64 "$elf"
pass "STATIC_INIT"
pass "ENTRY_IN_RX_LOAD"
pass "ENTRY_RX"

pack_boot "$ramdisk" "$img"
test -s "$img" || fail "packed image missing $img"

python3 tools/aosp/unpack_bootimg.py --boot_img "$img" --out "$un" >"$info"
grep -q "boot image header version: 3" "$info" || fail "BOOT_V3"
[ ! -e "$un/dtb" ] || fail "stage4 boot unexpectedly has dtb"

k_sha=$(sha "$un/kernel")
r_sha=$(sha "$un/ramdisk")
k_sz=$(wc -c <"$un/kernel" | tr -d ' ')
r_sz=$(wc -c <"$un/ramdisk" | tr -d ' ')
os=$(field "$info" "os version")
spl=$(field "$info" "os patch level")
hdr=$(field "$info" "boot image header version")
cmd=$(field "$info" "command line args")
img_sz=$(wc -c <"$img" | tr -d ' ')
ours=$(sha "$ramdisk")

echo "stage4 kernel sha256 $k_sha size $k_sz" | tee -a "$RPT"
echo "stage4 ramdisk sha256 $r_sha size $r_sz" | tee -a "$RPT"
echo "stage4 image size $img_sz" | tee -a "$RPT"

[ "$k_sha" = "$STOCK_K_SHA" ] || fail "STOCK_KERNEL_EXACT"
[ "$k_sz" = "$STOCK_K_SZ" ] || fail "STOCK_KERNEL_EXACT size"
[ "$r_sha" = "$ours" ] || fail "REVERSE_UNPACK ramdisk"
[ "$hdr" = "3" ] || fail "REVERSE_UNPACK header"
[ "$os" = "$STOCK_OS" ] || fail "REVERSE_UNPACK os"
[ "$spl" = "$STOCK_SPL" ] || fail "REVERSE_UNPACK spl"
[ "$cmd" = "$STOCK_CMD" ] || fail "REVERSE_UNPACK cmdline"

pass "STOCK_KERNEL_EXACT"
pass "BOOT_V3"
pass "REVERSE_UNPACK"

gzip -dc "$ramdisk" | cpio -t >"$list" 2>/dev/null
grep -Eq '(^|/)init$' "$list" || fail "RAMDISK_CONTAINS_INIT"
if grep -Eqi 'busybox|telnetd|httpd' "$list"; then
	fail "ramdisk has non-HTTP content"
fi
mkdir -p "$root"
gzip -dc "$ramdisk" | (cd "$root" && cpio -id --quiet 2>/dev/null)
packed=""
for cand in "$root/init" "$root/./init"; do
	[ -s "$cand" ] && packed=$cand && break
done
[ -n "$packed" ] || fail "packed /init missing"
test -x "$packed" || fail "packed /init not executable"
[ "$(sha "$packed")" = "$(sha "$elf")" ] || fail "packed /init != ELF"
verify_static_arm64 "$packed"
strings "$packed" | grep -Fq "BUILD=$BUILD_MARKER" || fail "packed BUILD marker"
strings "$packed" | grep -Fq "CONTROL=STOCK_KERNEL_USB_STAGE4" || fail "packed body identity"
strings "$packed" | grep -Fq "KERNEL=4.19.157-perf" || fail "packed kernel identity"
strings "$packed" | grep -Fq "HTTP_READY=YES" || fail "packed HTTP_READY body"

[ "$img_sz" -le "$BOOT_CAP" ] || fail "SIZE_GATE $img_sz > $BOOT_CAP"
[ "$r_sha" != "$STOCK_R_SHA" ] || fail "ONLY_RAMDISK_CHANGED ramdisk still stock"
pass "SIZE_GATE $img_sz <= $BOOT_CAP"
pass "ONLY_RAMDISK_CHANGED"

cp "$elf" "$REL/usb-stage4-http-init"
cp "$ramdisk" "$REL/initramfs.cpio.gz"
IMG_SHA=$(sha "$img")
echo "BUILD_MARKER $BUILD_MARKER" | tee -a "$RPT"
echo "CHOSEN_FUNCTION ncm" | tee -a "$RPT"
echo "TEST_ONLY_VID_PID 1d6b:0104 NOT PRODUCTION USB IDENTITY" | tee -a "$RPT"
echo "DESCRIPTOR product=Stock Kernel USB Stage4 HTTP serial=THYME-USB4" | tee -a "$RPT"
echo "ONLY INTENTIONAL PAYLOAD CHANGE: generic ramdisk (+ device 10.66.73.1/24 + TCP/HTTP listener)" | tee -a "$RPT"
echo "BOOT_V3_SHA256 $IMG_SHA" | tee -a "$RPT"
echo "READY_FOR_USB_STAGE4_HTTP" | tee -a "$RPT"
echo "ALL STOCK KERNEL USB STAGE4 HTTP VALIDATION PASS" | tee -a "$RPT"
