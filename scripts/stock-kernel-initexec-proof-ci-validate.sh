#!/usr/bin/env bash
# Pack + reverse-validate stock-kernel init-exec proof boot v3. GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image pack/validation" >&2
	exit 1
fi

REL="${1:?release dir}"
STOCK_BOOT="${2:?stock boot.img}"
PROOF="${3:?init-proof out dir}"
BOOT_CAP="${BOOT_CAP:-201326592}"
STOCK_BOOT_SHA256="${STOCK_BOOT_SHA256:?}"

REP="$REL/unpack-report"
RPT="$REL/validation-report.txt"
DIFF="$REL/stock-kernel-initexec-proof-image-diff.md"
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
	local f=$1 delay=$2
	local info
	[ -s "$f" ] || fail "INIT_PROOF_STATIC_ARM64 missing $f"
	info=$(file -b "$f")
	echo "$info" | tee -a "$RPT"
	echo "$info" | grep -q "ELF 64-bit LSB" || fail "INIT_PROOF_STATIC_ARM64 not ELF 64-bit LSB"
	echo "$info" | grep -qi aarch64 || fail "INIT_PROOF_STATIC_ARM64 not aarch64"
	readelf -h "$f" | grep -Eq 'Type:[[:space:]]+EXEC' || fail "INIT_PROOF_STATIC_ARM64 type not EXEC"
	if readelf -l "$f" | grep -q INTERP; then
		fail "INIT_PROOF_STATIC_ARM64 INTERP $f"
	fi
	if readelf -d "$f" 2>/dev/null | grep -q NEEDED; then
		fail "INIT_PROOF_STATIC_ARM64 NEEDED $f"
	fi
	strings "$f" | grep -q "THYME-INITEXEC-PROOF" || fail "INIT_PROOF_STATIC_ARM64 ident"
	strings "$f" | grep -q "DELAY=${delay}" || fail "INIT_PROOF_STATIC_ARM64 DELAY=$delay"
	strings "$f" | grep -q "bootloader" || fail "INIT_PROOF_STATIC_ARM64 bootloader"
	if [ "$delay" = 15 ]; then
		if strings "$f" | grep -q "DELAY=30"; then
			fail "P15 ELF contains DELAY=30"
		fi
	else
		if strings "$f" | grep -q "DELAY=15"; then
			fail "P30 ELF contains DELAY=15"
		fi
	fi
}

check_variant() {
	local delay=$1
	local img="$REL/stock-kernel-initexec-proof-${delay}s.img"
	local ramdisk="$PROOF/initramfs-${delay}s.cpio.gz"
	local elf="$PROOF/init-proof-${delay}s"
	local tag="p${delay}s"
	local un="$REP/${tag}-boot"
	local info="$REP/${tag}-boot.txt"
	local list="$REP/${tag}-initramfs.list"
	local root="$REP/${tag}-initramfs-root"

	[ -s "$ramdisk" ] || fail "missing $ramdisk"
	[ -s "$elf" ] || fail "missing $elf"
	verify_static_arm64 "$elf" "$delay"

	pack_boot "$ramdisk" "$img"
	test -s "$img" || fail "packed image missing $img"

	python3 tools/aosp/unpack_bootimg.py --boot_img "$img" --out "$un" >"$info"

	grep -q "boot image header version: 3" "$info" || fail "BOOT_HEADER_V3 $tag"
	[ ! -e "$un/dtb" ] || fail "$tag boot unexpectedly has dtb"

	local k_sha r_sha k_sz r_sz os spl hdr cmd img_sz ours
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

	echo "$tag kernel sha256 $k_sha size $k_sz" | tee -a "$RPT"
	echo "$tag ramdisk sha256 $r_sha size $r_sz" | tee -a "$RPT"
	echo "$tag image size $img_sz" | tee -a "$RPT"

	[ "$k_sha" = "$STOCK_K_SHA" ] || fail "STOCK_KERNEL_EXACT_MATCH $tag"
	[ "$k_sz" = "$STOCK_K_SZ" ] || fail "STOCK_KERNEL_EXACT_MATCH size $tag"
	[ "$r_sha" = "$ours" ] || fail "REVERSE_UNPACK ramdisk $tag"
	[ "$hdr" = "3" ] || fail "REVERSE_UNPACK header $tag"
	[ "$os" = "$STOCK_OS" ] || fail "REVERSE_UNPACK os $tag"
	[ "$spl" = "$STOCK_SPL" ] || fail "REVERSE_UNPACK spl $tag"
	[ "$cmd" = "$STOCK_CMD" ] || fail "REVERSE_UNPACK cmdline $tag"

	gzip -dc "$ramdisk" | cpio -t >"$list" 2>/dev/null
	grep -Eq '(^|/)init$' "$list" || fail "RAMDISK_CONTAINS_INIT $tag"
	if grep -Eqi 'busybox|telnetd|httpd|configfs|10\.66\.73' "$list"; then
		fail "ramdisk has non-proof content $tag"
	fi
	mkdir -p "$root"
	gzip -dc "$ramdisk" | (cd "$root" && cpio -id --quiet 2>/dev/null)
	local packed=""
	for cand in "$root/init" "$root/./init"; do
		[ -s "$cand" ] && packed=$cand && break
	done
	[ -n "$packed" ] || fail "packed /init missing $tag"
	test -x "$packed" || fail "RAMDISK_CONTAINS_INIT /init not executable $tag"
	[ "$(sha "$packed")" = "$(sha "$elf")" ] || fail "packed /init != ELF $tag"
	verify_static_arm64 "$packed" "$delay"
	[ "$(stat -c '%a' "$packed")" = "755" ] || echo "note: /init mode $(stat -c '%a' "$packed")" | tee -a "$RPT"

	[ "$img_sz" -le "$BOOT_CAP" ] || fail "SIZE_GATE $tag $img_sz > $BOOT_CAP"

	[ "$k_sha" = "$STOCK_K_SHA" ] || fail "ONLY_RAMDISK_CHANGED kernel $tag"
	[ "$hdr" = "$STOCK_HDR" ] || fail "ONLY_RAMDISK_CHANGED hdr $tag"
	[ "$os" = "$STOCK_OS" ] || fail "ONLY_RAMDISK_CHANGED os $tag"
	[ "$spl" = "$STOCK_SPL" ] || fail "ONLY_RAMDISK_CHANGED spl $tag"
	[ "$cmd" = "$STOCK_CMD" ] || fail "ONLY_RAMDISK_CHANGED cmdline $tag"
	[ "$r_sha" != "$STOCK_R_SHA" ] || fail "ONLY_RAMDISK_CHANGED ramdisk still stock $tag"

	eval "P${delay}_K_SHA=$k_sha"
	eval "P${delay}_R_SHA=$r_sha"
	eval "P${delay}_R_SZ=$r_sz"
	eval "P${delay}_IMG_SZ=$img_sz"
	eval "P${delay}_HDR=$hdr"
	eval "P${delay}_OS=$os"
	eval "P${delay}_SPL=$spl"
	eval "P${delay}_CMD=\$cmd"
}

check_variant 15
check_variant 30

[ "$P15_K_SHA" = "$P30_K_SHA" ] || fail "P15/P30 kernel mismatch"
[ "$P15_R_SHA" != "$P30_R_SHA" ] || fail "P15 ramdisk == P30 ramdisk"

cp "$PROOF/init-proof-15s" "$REL/init-proof-15s"
cp "$PROOF/init-proof-30s" "$REL/init-proof-30s"
cp "$PROOF/init-proof-15s" "$REL/init-proof"
cp "$PROOF/initramfs-15s.cpio.gz" "$REL/initramfs-15s.cpio.gz"
cp "$PROOF/initramfs-30s.cpio.gz" "$REL/initramfs-30s.cpio.gz"

pass "STOCK_KERNEL_EXACT_MATCH"
pass "INIT_PROOF_STATIC_ARM64"
pass "BOOT_HEADER_V3"
pass "RAMDISK_CONTAINS_INIT"
pass "REVERSE_UNPACK"
pass "ONLY_RAMDISK_CHANGED"
pass "SIZE_GATE $P15_IMG_SZ $P30_IMG_SZ <= $BOOT_CAP"

P15_IMG_SHA=$(sha "$REL/stock-kernel-initexec-proof-15s.img")
P30_IMG_SHA=$(sha "$REL/stock-kernel-initexec-proof-30s.img")

cat >"$DIFF" <<EOF
# stock vs init-exec proof boot.img

Input stock boot.img SHA256: \`$got\`

| Field | Stock | P15 | P30 |
|---|---|---|---|
| header version | $STOCK_HDR | $P15_HDR | $P30_HDR |
| kernel SHA256 | \`$STOCK_K_SHA\` | \`$P15_K_SHA\` | \`$P30_K_SHA\` |
| ramdisk SHA256 | \`$STOCK_R_SHA\` | \`$P15_R_SHA\` | \`$P30_R_SHA\` |
| ramdisk size | $STOCK_R_SZ | $P15_R_SZ | $P30_R_SZ |
| os version | $STOCK_OS | $P15_OS | $P30_OS |
| os patch level | $STOCK_SPL | $P15_SPL | $P30_SPL |
| cmdline | \`$STOCK_CMD\` | \`$P15_CMD\` | \`$P30_CMD\` |
| image size | $STOCK_IMG_SZ | $P15_IMG_SZ | $P30_IMG_SZ |

P15 image SHA256: \`$P15_IMG_SHA\`
P30 image SHA256: \`$P30_IMG_SHA\`

ONLY INTENTIONAL PAYLOAD CHANGE:
generic ramdisk (/init = static aarch64 ELF, sleep then RESTART2 "bootloader")

Expected non-payload differences (not a STOP):

- ramdisk size/hash: Android first-stage ramdisk replaced by init-proof
- total image size: stock is partition-padded (128 MiB) with AVB footer;
  proof images are unpadded mkbootimg output without AVB footer.
  Unlocked device + stock \`vbmeta_b\` flags=2 does not require a boot footer.

No USB gadget, no BusyBox, no Android mounts.
EOF

echo "ONLY INTENTIONAL PAYLOAD CHANGE: generic ramdisk" | tee -a "$RPT"
echo "P15_IMG_SHA256 $P15_IMG_SHA" | tee -a "$RPT"
echo "P30_IMG_SHA256 $P30_IMG_SHA" | tee -a "$RPT"
echo "READY_FOR_INIT_EXEC_PROOF" | tee -a "$RPT"
echo "ALL STOCK KERNEL INIT EXEC PROOF VALIDATION PASS" | tee -a "$RPT"
