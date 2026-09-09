#!/usr/bin/env bash
# Build and reverse-validate the Mainline V2 M0 boot-v3 image. GitHub Actions only.
set -euo pipefail

if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image build/validation" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REL="${1:?release dir}"
IMAGE="${2:?Mainline Image}"
INITRAMFS="${3:?initramfs.cpio.gz}"
INIT_PROOF="${4:?static init-proof ELF}"
BOOT_CAP="${BOOT_CAP:-201326592}"
BOOT_NAME="mainline-v2-m0-stockdt-initexec-boot-v3.img"
REL="$(mkdir -p "$REL" && cd "$REL" && pwd)"
REP="$REL/unpack-report"
RPT="$REL/validation-report.txt"
mkdir -p "$REP"
: >"$RPT"

pass() { printf 'PASS  %s\n' "$*" | tee -a "$RPT"; }
fail() { printf 'FAIL  %s\n' "$*" | tee -a "$RPT" >&2; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }

[ -s "$IMAGE" ] || fail "MAINLINE_IMAGE_BUILD missing Image"
[ -s "$INIT_PROOF" ] || fail "INIT_PROOF missing"
[ -s "$INITRAMFS" ] || fail "INITRAMFS missing"

IMAGE_SHA=$(sha "$IMAGE")
INIT_PROOF_SHA=$(sha "$INIT_PROOF")
INITRAMFS_SHA=$(sha "$INITRAMFS")
KERNEL_VERSION="${KERNEL_VERSION:-UNKNOWN}"
LINUX_BASE_COMMIT="${LINUX_BASE_COMMIT:-UNKNOWN}"
PATCH_QUEUE_SHA256="${PATCH_QUEUE_SHA256:-UNKNOWN}"
CONFIG_SHA256="${CONFIG_SHA256:-UNKNOWN}"
INIT_SOURCE_SHA256="${INIT_SOURCE_SHA256:-UNKNOWN}"
INIT_PROOF_EXACT_REUSE="${INIT_PROOF_EXACT_REUSE:-NO}"
INIT_PROOF_SOURCE_REBUILD="${INIT_PROOF_SOURCE_REBUILD:-UNKNOWN}"

{
	echo "MAINLINE_KERNEL_VERSION=$KERNEL_VERSION"
	echo "LINUX_BASE_COMMIT=$LINUX_BASE_COMMIT"
	echo "PATCH_QUEUE_SHA256=$PATCH_QUEUE_SHA256"
	echo "CONFIG_SHA256=$CONFIG_SHA256"
	echo "INIT_PROOF_EXACT_REUSE=$INIT_PROOF_EXACT_REUSE"
	echo "INIT_PROOF_SOURCE_REBUILD=$INIT_PROOF_SOURCE_REBUILD"
	echo "INIT_SOURCE_SHA256=$INIT_SOURCE_SHA256"
	echo "MAINLINE_IMAGE_SHA256=$IMAGE_SHA"
	echo "INIT_PROOF_SHA256=$INIT_PROOF_SHA"
	echo "INITRAMFS_SHA256=$INITRAMFS_SHA"
} | tee -a "$RPT"

case "$KERNEL_VERSION" in
	6.6.*) pass "MAINLINE_KERNEL_VERSION=$KERNEL_VERSION" ;;
	*) fail "MAINLINE_KERNEL_VERSION=$KERNEL_VERSION" ;;
esac

python3 - "$IMAGE" <<'PY'
from pathlib import Path
import sys

image = Path(sys.argv[1]).read_bytes()
if image[:2] == b"\x1f\x8b":
    raise SystemExit("Image is gzip-compressed; M0 requires raw Image")
if len(image) < 0x3c or image[0x38:0x3c] != b"ARMd":
    raise SystemExit("Image lacks the arm64 raw Image magic")
PY
pass "ARM64_IMAGE"
pass "ARM64_IMAGE_RAW"

INIT_SRC="$ROOT/initramfs/init-proof.c"
VERIFY="$ROOT/initramfs/verify-init-proof-elf.py"
READELF="${CROSS_COMPILE:-aarch64-linux-gnu-}readelf"
command -v "$READELF" >/dev/null || fail "missing $READELF"
[ -s "$INIT_SRC" ] || fail "init-proof source missing"
python3 "$VERIFY" "$INIT_PROOF" || fail "INIT_ENTRY_RX"

INFO=$(file -b "$INIT_PROOF")
echo "INIT_PROOF_FILE=$INFO" | tee -a "$RPT"
echo "$INFO" | grep -q 'ELF 64-bit LSB' || fail "INIT_PROOF_STATIC not ELF64"
echo "$INFO" | grep -qi 'aarch64\|ARM aarch64' || fail "INIT_PROOF_STATIC not ARM64"
"$READELF" -h "$INIT_PROOF" | grep -Eq 'Type:[[:space:]]+EXEC' || fail "INIT_PROOF_STATIC not ET_EXEC"
"$READELF" -h "$INIT_PROOF" | grep -Eq 'Machine:[[:space:]]+AArch64' || fail "INIT_PROOF_STATIC not AArch64"
if "$READELF" -l "$INIT_PROOF" | grep -q INTERP; then
	fail "INIT_PROOF_STATIC has dynamic interpreter"
fi
if "$READELF" -d "$INIT_PROOF" 2>/dev/null | grep -q NEEDED; then
	fail "INIT_PROOF_STATIC has dynamic dependency"
fi
strings "$INIT_PROOF" | grep -q 'THYME-INITEXEC-PROOF' || fail "INIT_PROOF identity missing"
strings "$INIT_PROOF" | grep -q 'DELAY=15' || fail "INIT_DELAY is not 15"
strings "$INIT_PROOF" | grep -q 'bootloader' || fail "RESTART2 bootloader string missing"
grep -Fq 'SYS_nanosleep' "$INIT_SRC" || fail "init-proof source lacks nanosleep"
grep -Fq 'LINUX_REBOOT_CMD_RESTART2' "$INIT_SRC" || fail "init-proof source lacks RESTART2"
grep -Fq '"bootloader"' "$INIT_SRC" || fail "init-proof source lacks bootloader"
grep -Fq 'for (;;)' "$INIT_SRC" || fail "init-proof source lacks PID1 failure loop"
grep -Fq 'if (fd < 0)' "$INIT_SRC" || fail "init-proof source lacks non-blocking kmsg failure path"
pass "INIT_PROOF"
pass "INIT_PROOF_STATIC"
pass "INIT_ENTRY_RX"
pass "INIT_DELAY=15"
pass "RESTART2_BOOTLOADER"
pass "PID1_FAILURE_SLEEP_LOOP"

if grep -Eiq 'configfs|usb|socket|listen|10\.66\.73' "$INIT_SRC"; then
	fail "INIT_PROOF source contains non-M0 userspace"
fi
pass "RAMDISK_SCOPE_MINIMAL"

gzip -t "$INITRAMFS" || fail "RAMDISK_GZIP"
pass "RAMDISK_GZIP"

BOOT="$REL/$BOOT_NAME"
python3 "$ROOT/tools/aosp/mkbootimg.py" \
	--kernel "$IMAGE" \
	--ramdisk "$INITRAMFS" \
	--header_version 3 \
	--os_version 13.0.0 \
	--os_patch_level 2023-09 \
	-o "$BOOT"
test -s "$BOOT" || fail "BOOT_IMAGE missing"

UN="$REP/boot-v3"
mkdir -p "$UN"
python3 "$ROOT/tools/aosp/unpack_bootimg.py" \
	--boot_img "$BOOT" \
	--out "$UN" >"$REP/boot-v3.txt" 2>&1

grep -q 'boot image header version: 3' "$REP/boot-v3.txt" || fail "BOOT_HEADER_V3"
[ ! -e "$UN/dtb" ] || fail "BOOT_HEADER_V3 image unexpectedly carries DTB"
[ ! -e "$UN/recovery_dtbo" ] || fail "BOOT image unexpectedly carries recovery dtbo"
[ -s "$UN/kernel" ] || fail "reverse unpack kernel missing"
[ -s "$UN/ramdisk" ] || fail "reverse unpack ramdisk missing"
[ "$(sha "$UN/kernel")" = "$IMAGE_SHA" ] || fail "KERNEL_PAYLOAD_EXACT"
[ "$(sha "$UN/ramdisk")" = "$INITRAMFS_SHA" ] || fail "RAMDISK_PAYLOAD_EXACT"
pass "BOOT_HEADER_V3"
pass "REVERSE_UNPACK"
pass "KERNEL_PAYLOAD_EXACT"
pass "RAMDISK_PAYLOAD_EXACT"

LIST="$REP/initramfs.list"
gzip -dc "$INITRAMFS" | cpio -t >"$LIST" 2>/dev/null
python3 - "$LIST" <<'PY'
from pathlib import Path
import sys

entries = [line.strip() for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
normalized = [entry[2:] if entry.startswith("./") else entry for entry in entries]
if set(normalized) != {".", "init"} or len(normalized) != 2:
    raise SystemExit(f"unexpected M0 ramdisk entries: {entries!r}")
PY
ROOTFS="$REP/initramfs-root"
mkdir -p "$ROOTFS"
gzip -dc "$INITRAMFS" | (cd "$ROOTFS" && cpio -id --quiet --no-absolute-filenames 2>/dev/null)
[ -x "$ROOTFS/init" ] || fail "RAMDISK_VALID /init not executable"
[ "$(sha "$ROOTFS/init")" = "$INIT_PROOF_SHA" ] || fail "RAMDISK_VALID /init differs from init-proof"
[ "$(stat -c '%a' "$ROOTFS/init")" = 755 ] || fail "RAMDISK_VALID /init mode is not 755"
pass "RAMDISK_VALID"
pass "INITRAMFS_UNPACK"

BOOT_SHA=$(sha "$BOOT")
BOOT_SIZE=$(wc -c <"$BOOT" | tr -d ' ')
echo "BOOT_IMAGE_SHA256=$BOOT_SHA" | tee -a "$RPT"
echo "BOOT_IMAGE_SIZE=$BOOT_SIZE" | tee -a "$RPT"
[ "$BOOT_SIZE" -le "$BOOT_CAP" ] || fail "PARTITION_SIZE $BOOT_SIZE > $BOOT_CAP"
pass "PARTITION_SIZE=$BOOT_SIZE <= $BOOT_CAP"

if find "$REL" -maxdepth 1 -type f \( \
	-name 'vendor_boot*' -o -name 'dtbo*' -o -name 'vbmeta*' \
\) -print -quit | grep -q .; then
	fail "FORBIDDEN_VENDOR_BOOT_DTBO_VBMETA_ARTIFACT"
fi
pass "NO_VENDOR_BOOT_ARTIFACT"
pass "NO_DTBO_ARTIFACT"
pass "NO_VBMETA_ARTIFACT"

pass "MAINLINE_IMAGE_BUILD"
pass "MAINLINE_INITRAMFS_UNPACK"
pass "READY_FOR_MAINLINE_V2_M0"
echo "ALL MAINLINE V2 M0 STOCK-DT INITEXEC VALIDATION PASS" | tee -a "$RPT"
