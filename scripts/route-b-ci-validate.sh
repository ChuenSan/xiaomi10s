#!/usr/bin/env bash
# Route B reverse-validation. GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image validation" >&2
	exit 1
fi

REL="${1:?release dir}"
REP="$REL/unpack-report"
RPT="$REL/route-b-validation-report.txt"
STOCK_CMDLINE="${STOCK_CMDLINE:?}"
BOOT_CAP=201326592
VENDOR_CAP=100663296
DTBO_CAP=33554432
mkdir -p "$REP"
: >"$RPT"
pass() { echo "PASS  $*" | tee -a "$RPT"; }
fail() { echo "FAIL  $*" | tee -a "$RPT"; exit 1; }

sha() { sha256sum "$1" | awk '{print $1}'; }

python3 tools/aosp/unpack_bootimg.py --boot_img "$REL/experimental-boot-v3.img" \
	--out "$REP/boot-v3" >"$REP/boot-v3.txt"
python3 tools/aosp/unpack_bootimg.py --boot_img "$REL/experimental-vendor_boot-v3.img" \
	--out "$REP/vendor_boot-v3" >"$REP/vendor_boot-v3.txt"

grep -q "boot image header version: 3" "$REP/boot-v3.txt" || fail "boot header != v3"
[ ! -e "$REP/boot-v3/dtb" ] || fail "v3 boot unexpectedly has dtb"
[ "$(sha "$REP/boot-v3/kernel")" = "$(sha "$REL/Image")" ] || fail "boot kernel != Image"
[ "$(sha "$REP/boot-v3/ramdisk")" = "$(sha "$REL/initramfs.cpio.gz")" ] || fail "boot ramdisk != initramfs"
pass "boot v3 header, no DTB, kernel/ramdisk SHA256"

grep -q "vendor boot image header version: 3" "$REP/vendor_boot-v3.txt" || fail "vendor_boot header != v3"
grep -Eq "page size: 0x0*1000" "$REP/vendor_boot-v3.txt" || fail "vendor_boot page size != 4096"
grep -Eq "kernel load address: 0x0*8000" "$REP/vendor_boot-v3.txt" || fail "kernel_addr"
grep -Eq "ramdisk load address: 0x0*1000000" "$REP/vendor_boot-v3.txt" || fail "ramdisk_addr"
grep -Eq "kernel tags load address: 0x0*100" "$REP/vendor_boot-v3.txt" || fail "tags_addr"
grep -Eq "dtb address: 0x0*1f00000" "$REP/vendor_boot-v3.txt" || fail "dtb_addr"
grep -F "$STOCK_CMDLINE" "$REP/vendor_boot-v3.txt" || fail "vendor cmdline mismatch"
DTB="$REP/vendor_boot-v3/dtb"
[ -s "$DTB" ] || fail "vendor_boot DTB missing"
[ "$(sha "$DTB")" = "$(sha "$REL/sm8250-xiaomi-thyme.dtb")" ] || fail "vendor_boot DTB SHA256 != mainline DTB"
fdtget "$DTB" / compatible | tr ' ' '\n' | grep -qx 'qcom,sm8250' || fail "DTB lacks qcom,sm8250"
pass "vendor_boot v3 fields + DTB exact SHA256"

python3 tools/aosp/mkdtboimg.py dump "$REL/experimental-dtbo.img" \
	--dtb "$REP/dtbo-frag" >"$REP/dtbo.dump.txt"
n=$(find "$REP" -name 'dtbo-frag.*' | wc -l | tr -d ' ')
[ "$n" = 1 ] || fail "dtbo entry count $n != 1"
dtc -I dtb -O dts "$REP/dtbo-frag.0" >"$REP/dtbo-frag.dts.txt" 2>/dev/null
grep -q 'qcom,thyme-route-b-noop' "$REP/dtbo-frag.dts.txt" || fail "noop marker missing"
python3 - "$REP/dtbo-frag.dts.txt" <<'PY'
import re, sys
m = re.search(r'qcom,board-id\s*=\s*<([^>]*)>\s*;', open(sys.argv[1]).read())
assert m, 'no board-id'
nums = [int(c, 0) for c in m.group(1).split()]
assert nums == [45, 0], nums
PY
fdtoverlay -i "$REL/sm8250-xiaomi-thyme.dtb" "$REL/noop.dtbo" -o "$REP/merged.dtb"
dtc -I dtb -O dts "$REL/sm8250-xiaomi-thyme.dtb" >"$REP/mainline-dtb.dts.txt"
dtc -I dtb -O dts "$REP/merged.dtb" >"$REP/merged.dts.txt"
fdtget "$REP/merged.dtb" / qcom,thyme-route-b-noop >/dev/null || fail "merged lacks marker"
grep -v thyme-route-b-noop "$REP/merged.dts.txt" >"$REP/merged-clean.dts"
grep -v thyme-route-b-noop "$REP/mainline-dtb.dts.txt" >"$REP/mainline-clean.dts"
diff -u "$REP/mainline-clean.dts" "$REP/merged-clean.dts" >"$REP/mainline-vs-merged.diff" \
	|| fail "noop overlay mutated the mainline tree"
pass "dtbo 1 entry, board-id <45 0>, fdtoverlay no-op"

check_size() {
	local img=$1 cap=$2 s
	s=$(wc -c <"$REL/$img")
	echo "$img = $s <= $cap" | tee -a "$RPT"
	[ "$s" -le "$cap" ] || fail "OVERSIZE $img"
}
check_size experimental-boot-v3.img "$BOOT_CAP"
check_size experimental-vendor_boot-v3.img "$VENDOR_CAP"
check_size experimental-dtbo.img "$DTBO_CAP"
pass "size gates"

# initramfs static structure (no ARM64 exec)
gzip -dc "$REL/initramfs.cpio.gz" | cpio -t >/tmp/initramfs.list 2>/dev/null
grep -q 'init' /tmp/initramfs.list || fail "no /init"
for a in init cat mount ifconfig telnetd httpd dmesg sh; do
	grep -q "$a" /tmp/initramfs.list || fail "applet/file missing: $a"
done
INIT_SRC="${GITHUB_WORKSPACE}/initramfs/route-b-init"
grep -q 'ROUTE=B' "$INIT_SRC" || fail "ROUTE=B missing in init"
grep -q 'THYME-MAINLINE-B' "$INIT_SRC" || fail "serial string missing in init"
grep -q '10.66.73.1' "$INIT_SRC" || fail "Route B IP missing in init"
grep -q 'httpd -p 0.0.0.0:8080' "$INIT_SRC" || fail "httpd bind missing"
pass "initramfs static structure"
echo "ALL ROUTE B VALIDATION PASS" | tee -a "$RPT"
