#!/usr/bin/env bash
# R3 RUNTIME_DTB_COMPLETION_CI — Android A READ-ONLY runtime evidence capture.
# No reboot, no fastboot, no partition write, no slot change. Host-side capture
# only; all parsing/validation happens in GitHub Actions.
set -euo pipefail
set -o pipefail

OUT_DIR="${1:?usage: r3-runtime-capture.sh OUT_DIR}"
ADB="${ADB:-adb}"

fail() {
	printf 'R3_RUNTIME_CAPTURE=FAIL\nR3_RUNTIME_CAPTURE_FAILURE=%s\n' "$*" >&2
	exit 1
}

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

adb_su() {
	# exec-out is binary-safe and does not inject CRLF.
	adb exec-out su -c "$1" 2>/dev/null
}

adb_su_text() {
	adb_su "$1" | tr -d '\r'
}

require_state() {
	local value expected label
	value="$1"
	expected="$2"
	label="$3"
	[ "$value" = "$expected" ] || fail "$label=$value expected=$expected"
}

# ---- baseline (read-only) -------------------------------------------------
DEV_STATE="$("$ADB" devices 2>/dev/null | awk 'NR > 1 && $2 == "device" {found=1} END {print found ? "present" : "absent"}')"
require_state "$DEV_STATE" present "adb_device"

SLOT="$(adb_su_text 'getprop ro.boot.slot_suffix')"
BOOT_COMPLETED="$(adb_su_text 'getprop sys.boot_completed')"
ROOT_ID="$(adb_su_text 'id')"
require_state "$SLOT" _a "slot_suffix"
require_state "$BOOT_COMPLETED" 1 "boot_completed"
case "$ROOT_ID" in *uid=0*) ;; *) fail "root unavailable: ${ROOT_ID:-none}" ;; esac

{
	printf 'R3_RUNTIME_CAPTURE=ANDROID_A_READ_ONLY\n'
	printf 'slot_suffix=%s\nboot_completed=%s\n' "$SLOT" "$BOOT_COMPLETED"
	printf 'uname=%s\n' "$(adb_su_text 'uname -a')"
	printf 'device=%s\n' "$(adb_su_text 'getprop ro.product.device')"
} > "$OUT_DIR/baseline.txt"

# ---- LEVEL 1: runtime FDT binary ------------------------------------------
FDT_PATH=/sys/firmware/fdt
if adb_su "test -e $FDT_PATH" >/dev/null 2>&1; then
	adb_su "cat $FDT_PATH" > "$OUT_DIR/thyme-stock-runtime-fdt.bin"
	RUNTIME_FDT_AVAILABLE=YES
else
	RUNTIME_FDT_AVAILABLE=NO
fi

# ---- runtime OF tree (full enumeration, private) ---------------------------
adb_su 'tar -C /sys/firmware/devicetree/base -cf - .' \
	> "$OUT_DIR/thyme-stock-android-a-devicetree.tar" || true
[ -s "$OUT_DIR/thyme-stock-android-a-devicetree.tar" ] \
	|| fail "runtime OF tree tar capture empty"

# ---- LEVEL 2/3: proc + sysfs ----------------------------------------------
adb_su_text 'cat /proc/iomem' > "$OUT_DIR/thyme-stock-android-a-iomem.txt"
adb_su_text 'cat /proc/meminfo' > "$OUT_DIR/thyme-stock-android-a-meminfo.txt"
adb_su_text 'cat /sys/devices/system/memory/block_size_bytes 2>/dev/null' \
	> "$OUT_DIR/thyme-stock-android-a-memory-block-size.txt"
adb_su_text 'for f in /sys/devices/system/memory/memory*/phys_index; do echo "== $f"; cat "$f"; done 2>/dev/null' \
	> "$OUT_DIR/thyme-stock-android-a-memory-phys-index.txt"
adb_su_text 'for f in /sys/devices/system/memory/memory*/state; do echo "== $f"; cat "$f"; done 2>/dev/null' \
	> "$OUT_DIR/thyme-stock-android-a-memory-state.txt"
adb_su_text 'dmesg | grep -Ei "Memory:|OF: reserved mem|Reserved memory|CMA|cma|memblock|Kernel code|Kernel data|Kernel bss|Kernel Offset"' \
	> "$OUT_DIR/thyme-stock-android-a-dmesg-memory-filtered.txt" || true

# ---- integrity manifest (hashes only; parsing stays GHA-only) --------------
: > "$OUT_DIR/manifest.txt"
for f in baseline.txt thyme-stock-runtime-fdt.bin \
	thyme-stock-android-a-devicetree.tar \
	thyme-stock-android-a-iomem.txt thyme-stock-android-a-meminfo.txt \
	thyme-stock-android-a-memory-block-size.txt \
	thyme-stock-android-a-memory-phys-index.txt \
	thyme-stock-android-a-memory-state.txt \
	thyme-stock-android-a-dmesg-memory-filtered.txt; do
	p="$OUT_DIR/$f"
	if [ -e "$p" ]; then
		printf '%s\t%s\t%s\n' "$f" "$(wc -c < "$p" | tr -d ' ')" \
			"$(shasum -a 256 "$p" | awk '{print $1}')" >> "$OUT_DIR/manifest.txt"
	fi
done

# ---- post-capture state re-confirm (no device state change) ---------------
SLOT_AFTER="$(adb_su_text 'getprop ro.boot.slot_suffix')"
BOOT_AFTER="$(adb_su_text 'getprop sys.boot_completed')"
require_state "$SLOT_AFTER" _a "slot_suffix_after"
require_state "$BOOT_AFTER" 1 "boot_completed_after"

printf 'R3_RUNTIME_CAPTURE=PASS\n'
printf 'RUNTIME_FDT_AVAILABLE=%s\n' "$RUNTIME_FDT_AVAILABLE"
printf 'OUT_DIR=%s\n' "$OUT_DIR"
printf 'slot_suffix_after=%s\nboot_completed_after=%s\n' "$SLOT_AFTER" "$BOOT_AFTER"
printf 'DEVICE_REBOOT=NO\nPARTITION_WRITES=0\nSLOT_A_WRITTEN=NO\n'
