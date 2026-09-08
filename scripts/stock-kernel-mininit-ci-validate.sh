#!/usr/bin/env bash
# Pack + reverse-validate stock-kernel-mininit boot v3. GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image pack/validation" >&2
	exit 1
fi

REL="${1:?release dir}"
STOCK_BOOT="${2:?stock boot.img}"
INITRAMFS="${3:?initramfs.cpio.gz}"
BUSYBOX="${4:?busybox static}"
INIT_SRC="${5:?init source}"
BOOT_CAP="${BOOT_CAP:-201326592}"
STOCK_BOOT_SHA256="${STOCK_BOOT_SHA256:?}"

REP="$REL/unpack-report"
RPT="$REL/validation-report.txt"
DIFF="$REL/stock-kernel-mininit-image-diff.md"
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
STOCK_IMG_SZ=$(wc -c <"$STOCK_BOOT" | tr -d ' ')
echo "stock kernel sha256 $STOCK_K_SHA size $STOCK_K_SZ" | tee -a "$RPT"
echo "stock ramdisk sha256 $STOCK_R_SHA size $STOCK_R_SZ" | tee -a "$RPT"
echo "stock os=$STOCK_OS spl=$STOCK_SPL hdr=$STOCK_HDR cmdline='${STOCK_CMD}'" | tee -a "$RPT"

echo "== pack control boot v3 (stock kernel + our ramdisk) ==" | tee -a "$RPT"
python3 - <<PY
import shlex, subprocess, sys
from pathlib import Path
mk = Path("$REP/stock-boot.mkbootimg.txt").read_text().strip()
args = shlex.split(mk)
ramdisk = "$INITRAMFS"
out = "$REL/stock-kernel-mininit-boot-v3.img"
for i, a in enumerate(args):
    if a == "--ramdisk":
        args[i + 1] = ramdisk
cmd = [sys.executable, "tools/aosp/mkbootimg.py", *args, "-o", out]
print("mkbootimg:", " ".join(shlex.quote(x) for x in cmd), flush=True)
subprocess.check_call(cmd)
PY
test -s "$REL/stock-kernel-mininit-boot-v3.img" || fail "control image missing"
cp "$INITRAMFS" "$REL/initramfs.cpio.gz"
cp "$BUSYBOX" "$REL/busybox-aarch64-static"
cp "$INIT_SRC" "$REL/stock-kernel-mininit-init"

python3 tools/aosp/unpack_bootimg.py --boot_img "$REL/stock-kernel-mininit-boot-v3.img" \
	--out "$REP/control-boot" >"$REP/control-boot.txt"

grep -q "boot image header version: 3" "$REP/control-boot.txt" || fail "BOOT_HEADER_V3"
[ ! -e "$REP/control-boot/dtb" ] || fail "control boot unexpectedly has dtb"
pass "BOOT_HEADER_V3"

CTRL_K_SHA=$(sha "$REP/control-boot/kernel")
CTRL_R_SHA=$(sha "$REP/control-boot/ramdisk")
CTRL_K_SZ=$(wc -c <"$REP/control-boot/kernel" | tr -d ' ')
CTRL_R_SZ=$(wc -c <"$REP/control-boot/ramdisk" | tr -d ' ')
CTRL_OS=$(field "$REP/control-boot.txt" "os version")
CTRL_SPL=$(field "$REP/control-boot.txt" "os patch level")
CTRL_HDR=$(field "$REP/control-boot.txt" "boot image header version")
CTRL_CMD=$(field "$REP/control-boot.txt" "command line args")
CTRL_IMG_SZ=$(wc -c <"$REL/stock-kernel-mininit-boot-v3.img" | tr -d ' ')
OURS_R_SHA=$(sha "$REL/initramfs.cpio.gz")

echo "control kernel sha256 $CTRL_K_SHA size $CTRL_K_SZ" | tee -a "$RPT"
echo "control ramdisk sha256 $CTRL_R_SHA size $CTRL_R_SZ" | tee -a "$RPT"

[ "$CTRL_K_SHA" = "$STOCK_K_SHA" ] || fail "STOCK_KERNEL_EXACT_MATCH"
[ "$CTRL_K_SZ" = "$STOCK_K_SZ" ] || fail "STOCK_KERNEL_EXACT_MATCH size"
pass "STOCK_KERNEL_EXACT_MATCH"

[ "$CTRL_R_SHA" = "$OURS_R_SHA" ] || fail "REVERSE_UNPACK ramdisk != initramfs"
[ "$CTRL_HDR" = "3" ] || fail "REVERSE_UNPACK header"
[ "$CTRL_OS" = "$STOCK_OS" ] || fail "REVERSE_UNPACK os version $CTRL_OS != $STOCK_OS"
[ "$CTRL_SPL" = "$STOCK_SPL" ] || fail "REVERSE_UNPACK os patch $CTRL_SPL != $STOCK_SPL"
[ "$CTRL_CMD" = "$STOCK_CMD" ] || fail "REVERSE_UNPACK cmdline '$CTRL_CMD' != '$STOCK_CMD'"
pass "REVERSE_UNPACK"

gzip -dc "$REL/initramfs.cpio.gz" | cpio -t >"$REP/initramfs.list" 2>/dev/null
grep -Eq '(^|/)init$' "$REP/initramfs.list" || fail "no /init"
for a in init busybox cat mount ifconfig telnetd httpd dmesg sh; do
	grep -q "$a" "$REP/initramfs.list" || fail "applet/file missing: $a"
done
mkdir -p "$REP/initramfs-root"
gzip -dc "$REL/initramfs.cpio.gz" | (cd "$REP/initramfs-root" && cpio -id --quiet 2>/dev/null)
PACKED_INIT=""
for cand in "$REP/initramfs-root/init" "$REP/initramfs-root/./init"; do
	[ -s "$cand" ] && PACKED_INIT=$cand && break
done
[ -n "$PACKED_INIT" ] && [ -s "$PACKED_INIT" ] || fail "packed /init missing"
grep -q 'CONTROL=STOCK_KERNEL_MININIT' "$PACKED_INIT" || fail "CONTROL string missing"
grep -q 'THYME-STOCKK-MININIT' "$PACKED_INIT" || fail "serial missing"
grep -q 'Stock Kernel MinInit Control' "$PACKED_INIT" || fail "product string missing"
grep -q 'thyme-mainline' "$PACKED_INIT" || fail "manufacturer missing"
grep -q '10.66.73.1' "$PACKED_INIT" || fail "experiment subnet missing"
grep -q '/control-status' "$PACKED_INIT" || fail "control-status breadcrumb missing"
grep -q 'DO_NOT_MOUNT_METADATA' "$PACKED_INIT" || fail "metadata guard comment missing"
if grep -Eq '^[^#]*mount[[:space:]].*/metadata' "$PACKED_INIT"; then
	fail "init mounts /metadata"
fi
if grep -Eq '^[^#]*mount[[:space:]].*/(system|vendor|product)' "$PACKED_INIT"; then
	fail "init mounts Android volumes"
fi
grep -q 'USBNET=ncm' "$PACKED_INIT" || fail "NCM not default"
pass "INITRAMFS_STRUCTURE"

[ "$CTRL_IMG_SZ" -le "$BOOT_CAP" ] || fail "PARTITION_SIZE $CTRL_IMG_SZ > $BOOT_CAP"
pass "PARTITION_SIZE $CTRL_IMG_SZ <= $BOOT_CAP"

ONLY=PASS
if [ "$CTRL_K_SHA" != "$STOCK_K_SHA" ]; then ONLY=FAIL; fi
if [ "$CTRL_HDR" != "$STOCK_HDR" ]; then ONLY=FAIL; fi
if [ "$CTRL_OS" != "$STOCK_OS" ]; then ONLY=FAIL; fi
if [ "$CTRL_SPL" != "$STOCK_SPL" ]; then ONLY=FAIL; fi
if [ "$CTRL_CMD" != "$STOCK_CMD" ]; then ONLY=FAIL; fi
if [ "$CTRL_R_SHA" = "$STOCK_R_SHA" ]; then ONLY=FAIL; fi
[ "$ONLY" = PASS ] || fail "ONLY_RAMDISK_CHANGED"
pass "ONLY_RAMDISK_CHANGED"

cat >"$DIFF" <<EOF
# stock vs stock-kernel-mininit boot.img

Input stock boot.img SHA256: \`$got\`
Control image: \`stock-kernel-mininit-boot-v3.img\`

| Field | Stock | Control | Match |
|---|---|---|---|
| header version | $STOCK_HDR | $CTRL_HDR | $( [ "$STOCK_HDR" = "$CTRL_HDR" ] && echo YES || echo NO ) |
| kernel size | $STOCK_K_SZ | $CTRL_K_SZ | $( [ "$STOCK_K_SZ" = "$CTRL_K_SZ" ] && echo YES || echo NO ) |
| ramdisk size | $STOCK_R_SZ | $CTRL_R_SZ | NO (intentional) |
| os version | $STOCK_OS | $CTRL_OS | $( [ "$STOCK_OS" = "$CTRL_OS" ] && echo YES || echo NO ) |
| os patch level | $STOCK_SPL | $CTRL_SPL | $( [ "$STOCK_SPL" = "$CTRL_SPL" ] && echo YES || echo NO ) |
| cmdline | \`$STOCK_CMD\` | \`$CTRL_CMD\` | $( [ "$STOCK_CMD" = "$CTRL_CMD" ] && echo YES || echo NO ) |
| kernel SHA256 | \`$STOCK_K_SHA\` | \`$CTRL_K_SHA\` | YES |
| ramdisk SHA256 | \`$STOCK_R_SHA\` | \`$CTRL_R_SHA\` | NO (intentional) |
| total image size | $STOCK_IMG_SZ | $CTRL_IMG_SZ | NO (expected) |

ONLY INTENTIONAL PAYLOAD CHANGE:
generic ramdisk

Expected non-payload differences (not a STOP):

- ramdisk size/hash: Android first-stage ramdisk replaced by BusyBox mininit
- total image size: stock is partition-padded (128 MiB) with AVB footer;
  control is unpadded mkbootimg output without AVB footer.
  Unlocked device + stock \`vbmeta_b\` flags=2 does not require a boot footer.

If kernel SHA256, header version, os version, os patch level, or cmdline
had drifted, this script would have failed with ONLY_RAMDISK_CHANGED.

Gadget class: **NCM** (stock \`kona-perf\` has \`CONFIG_USB_CONFIGFS_NCM=y\`
and does not enable ECM). VID/PID \`0x1d6b:0x0104\` Linux Foundation.
EOF

echo "ONLY INTENTIONAL PAYLOAD CHANGE: generic ramdisk" | tee -a "$RPT"
echo "READY_FOR_STOCK_KERNEL_MININIT_CONTROL" | tee -a "$RPT"
echo "ALL STOCK KERNEL MININIT VALIDATION PASS" | tee -a "$RPT"
