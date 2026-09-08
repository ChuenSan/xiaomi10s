#!/usr/bin/env bash
# Pack + reverse-validate stock-kernel USB Stage1B device-up boot v3.
# GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image pack/validation" >&2
	exit 1
fi

REL="${1:?release dir}"
STOCK_BOOT="${2:?stock boot.img}"
PROOF="${3:?usb-stage1b-device-up out dir}"
BOOT_CAP="${BOOT_CAP:-201326592}"
STOCK_BOOT_SHA256="${STOCK_BOOT_SHA256:?}"

REP="$REL/unpack-report"
RPT="$REL/validation-report.txt"
mkdir -p "$REL" "$REP"
: >"$RPT"

pass() { echo "PASS  $*" | tee -a "$RPT"; }
fail() { echo "FAIL  $*" | tee -a "$RPT"; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }
field() { sed -n "s/^$2: //p" "$1" | head -n1; }

echo "== stock boot input hash ==" | tee -a "$RPT"
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

pack_boot() {
	local ramdisk=$1 out=$2
	python3 - "$REP/stock-boot.mkbootimg.txt" "$ramdisk" "$out" <<'PY'
import shlex, subprocess, sys
from pathlib import Path
mk, ramdisk, out = sys.argv[1], sys.argv[2], sys.argv[3]
args = shlex.split(Path(mk).read_text().strip())
for i, a in enumerate(args):
    if a == "--ramdisk":
        args[i + 1] = ramdisk
cmd = [sys.executable, "tools/aosp/mkbootimg.py", *args, "-o", out]
print("mkbootimg:", " ".join(shlex.quote(x) for x in cmd), flush=True)
subprocess.check_call(cmd)
PY
}

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
	strings "$f" | grep -q "THYME-USB1B:INIT" || fail "STATIC_INIT THYME-USB1B"
	strings "$f" | grep -q "Stock Kernel USB Stage1B Device Up" || fail "STATIC_INIT product"
	strings "$f" | grep -q "bootloader" || fail "STATIC_INIT bootloader"
	strings "$f" | grep -q "ncm.usb0" || fail "STATIC_INIT ncm.usb0"
	strings "$f" | grep -q "/sys/class/udc" || fail "STATIC_INIT UDC discovery"
	strings "$f" | grep -q "/sys/class/net" || fail "STATIC_INIT net class"
	strings "$f" | grep -q "/config" || fail "STATIC_INIT /config"
	strings "$f" | grep -q "configfs" || fail "STATIC_INIT configfs"
	strings "$f" | grep -q "THYME-USB1B:MOUNT_CONFIGFS" || fail "STATIC_INIT mount log"
	strings "$f" | grep -q "THYME-USB1B:STAT_USB_GADGET" || fail "STATIC_INIT stat log"
	strings "$f" | grep -q "THYME-USB1B:NETDEV_FOUND" || fail "STATIC_INIT NETDEV_FOUND"
	strings "$f" | grep -q "THYME-USB1B:UDC_CONFIGURED" || fail "STATIC_INIT UDC_CONFIGURED"
	strings "$f" | grep -q "THYME-USB1B:HOLD_DONE" || fail "STATIC_INIT HOLD_DONE"
	strings "$f" | grep -q "THYME-USB1B:FLAGS_BEFORE" || fail "STATIC_INIT FLAGS_BEFORE"
	strings "$f" | grep -q "THYME-USB1B:IFF_UP_ATTEMPT" || fail "STATIC_INIT IFF_UP_ATTEMPT"
	strings "$f" | grep -q "THYME-USB1B:IFF_UP_OK" || fail "STATIC_INIT IFF_UP_OK"
	strings "$f" | grep -q "THYME-USB1B:FLAGS_AFTER" || fail "STATIC_INIT FLAGS_AFTER"
	strings "$f" | grep -q "THYME-USB1B:SIOCSIFFLAGS=YES" || fail "STATIC_INIT SIOCSIFFLAGS"
	strings "$f" | grep -q "THYME-USB1B:FAIL:NO_NETDEV" || fail "STATIC_INIT NO_NETDEV"
}

python3 scripts/stock-kernel-usb-stage1b-device-up-source-gates.py | tee -a "$RPT" \
	|| fail "SOURCE_GATES"
gcc -O2 -Wall -Werror -o "$REL/usb-stage0-isdir-host-test" \
	initramfs/usb-stage0-isdir-host-test.c
"$REL/usb-stage0-isdir-host-test" | tee -a "$RPT"
pass "DIRECTORY_CHECK_NOT_OPEN_ODIRECTORY"
pass "STAT_BASED_DIRECTORY_CHECK"
pass "CONFIGFS_MOUNTPOINT_IS_CONFIG"
pass "CONFIGFS_STAT_LOGGING"
pass "ERRNO_LOGGING"
pass "UDC_SCAN_LOGIC"
pass "CONFIGFS_PATH_FIX"
pass "ERRNO_MARKERS"
pass "NCM_LOGIC"
pass "UDC_DISCOVERY"
pass "USB0_CORE_REUSED"
pass "USB0_REGRESSION_CHECK"
pass "NETDEV_DISCOVERY"
pass "SIOCGIFFLAGS"
pass "SIOCSIFFLAGS"
pass "IFF_UP_OR_OLD_FLAGS"
pass "NO_IP_CONFIGURATION"
pass "NO_IP_LOGIC"
pass "NETDEV_DIFF_LOGIC"
pass "FAILSAFE"
pass "FAILSAFE_RESTART2"
echo "DIRECTORY_CHECK_IMPL newfstatat/stat" | tee -a "$RPT"
echo "IFF_UP old_flags | IFF_UP" | tee -a "$RPT"
echo "DESCRIPTOR_ONLY_CHANGE product/serial (Stage1B Device Up / THYME-USB1B)" | tee -a "$RPT"

elf="$PROOF/usb-stage1b-device-up-init"
ramdisk="$PROOF/initramfs.cpio.gz"
img="$REL/stock-kernel-usb-stage1b-device-up-boot-v3.img"
un="$REP/stage1b-boot"
info="$REP/stage1b-boot.txt"
list="$REP/stage1b-initramfs.list"
root="$REP/stage1b-initramfs-root"

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
[ ! -e "$un/dtb" ] || fail "stage1b boot unexpectedly has dtb"

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

echo "stage1b kernel sha256 $k_sha size $k_sz" | tee -a "$RPT"
echo "stage1b ramdisk sha256 $r_sha size $r_sz" | tee -a "$RPT"
echo "stage1b image size $img_sz" | tee -a "$RPT"

[ "$k_sha" = "$STOCK_K_SHA" ] || fail "STOCK_KERNEL_EXACT"
[ "$k_sz" = "$STOCK_K_SZ" ] || fail "STOCK_KERNEL_EXACT size"
[ "$r_sha" = "$ours" ] || fail "REVERSE_UNPACK ramdisk"
[ "$hdr" = "3" ] || fail "REVERSE_UNPACK header"
[ "$os" = "$STOCK_OS" ] || fail "REVERSE_UNPACK os"
[ "$spl" = "$STOCK_SPL" ] || fail "REVERSE_UNPACK spl"
[ "$cmd" = "$STOCK_CMD" ] || fail "REVERSE_UNPACK cmdline"

gzip -dc "$ramdisk" | cpio -t >"$list" 2>/dev/null
grep -Eq '(^|/)init$' "$list" || fail "RAMDISK_CONTAINS_INIT"
if grep -Eqi 'busybox|telnetd|httpd' "$list"; then
	fail "ramdisk has non-observe content"
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

[ "$img_sz" -le "$BOOT_CAP" ] || fail "SIZE_GATE $img_sz > $BOOT_CAP"
[ "$r_sha" != "$STOCK_R_SHA" ] || fail "ONLY_RAMDISK_CHANGED ramdisk still stock"

cp "$elf" "$REL/usb-stage1b-device-up-init"
cp "$ramdisk" "$REL/initramfs.cpio.gz"

pass "STOCK_KERNEL_EXACT"
pass "BOOT_V3"
pass "REVERSE_UNPACK"
pass "SIZE_GATE $img_sz <= $BOOT_CAP"

IMG_SHA=$(sha "$img")
echo "CHOSEN_FUNCTION ncm" | tee -a "$RPT"
echo "TEST_ONLY_VID_PID 1d6b:0104 NOT PRODUCTION USB IDENTITY" | tee -a "$RPT"
echo "DESCRIPTOR_ONLY_CHANGE product=Stock Kernel USB Stage1B Device Up serial=THYME-USB1B" | tee -a "$RPT"
echo "ONLY INTENTIONAL PAYLOAD CHANGE: generic ramdisk (+ device netdev IFF_UP)" | tee -a "$RPT"
echo "BOOT_V3_SHA256 $IMG_SHA" | tee -a "$RPT"
echo "READY_FOR_USB_STAGE1B_DEVICE_UP" | tee -a "$RPT"
echo "ALL STOCK KERNEL USB STAGE1B DEVICE UP VALIDATION PASS" | tee -a "$RPT"
