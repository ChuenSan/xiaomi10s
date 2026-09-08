#!/usr/bin/env bash
# Build static aarch64 init-proof ELF + gzip newc initramfs. GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local compile/pack" >&2
	exit 1
fi

SRC="${PWD}/initramfs/init-proof.c"
OUT="${1:-$PWD/out-init-proof}"
CC="${CROSS_COMPILE:-aarch64-linux-gnu-}gcc"
LD="${CROSS_COMPILE:-aarch64-linux-gnu-}ld"
STRIP="${CROSS_COMPILE:-aarch64-linux-gnu-}strip"

command -v "$CC" >/dev/null || { echo "missing $CC" >&2; exit 1; }
command -v "$LD" >/dev/null || { echo "missing $LD" >&2; exit 1; }
test -f "$SRC" || { echo "missing $SRC" >&2; exit 1; }

mkdir -p "$OUT"

verify_elf() {
	local f=$1 delay=$2
	local info
	info=$(file -b "$f")
	echo "file $f: $info"
	echo "$info" | grep -q "ELF 64-bit LSB" || { echo "not ELF 64-bit LSB: $f" >&2; exit 1; }
	echo "$info" | grep -qi aarch64 || { echo "not aarch64: $f" >&2; exit 1; }
	readelf -h "$f" | grep -Eq 'Type:[[:space:]]+EXEC' || { echo "ELF type not EXEC: $f" >&2; exit 1; }
	if readelf -l "$f" | grep -q INTERP; then
		echo "INTERP present: $f" >&2
		exit 1
	fi
	if readelf -d "$f" 2>/dev/null | grep -q NEEDED; then
		echo "dynamic NEEDED: $f" >&2
		exit 1
	fi
	echo "$info" | grep -q "statically linked" || echo "note: file(1) omitted 'statically linked'; INTERP/NEEDED empty"
	strings "$f" | grep -q "THYME-INITEXEC-PROOF" || { echo "ident missing: $f" >&2; exit 1; }
	strings "$f" | grep -q "DELAY=${delay}" || { echo "DELAY=$delay missing: $f" >&2; exit 1; }
	strings "$f" | grep -q "bootloader" || { echo "bootloader string missing: $f" >&2; exit 1; }
	readelf -h "$f" | grep -q "Machine:.*AArch64" || { echo "Machine not AArch64: $f" >&2; exit 1; }
}

build_one() {
	local delay=$1
	local obj="$OUT/init-proof-${delay}s.o"
	local elf="$OUT/init-proof-${delay}s"
	local root="$OUT/root-${delay}s"
	local cpio="$OUT/initramfs-${delay}s.cpio.gz"

	"$CC" -ffreestanding -fno-stack-protector -fno-asynchronous-unwind-tables \
		-fno-ident -fno-pic -Os -Wall -Werror \
		-DDELAY_SECONDS="$delay" \
		-c "$SRC" -o "$obj"
	"$LD" -static --build-id=none -e _start -o "$elf" "$obj"
	"$STRIP" -s "$elf"
	verify_elf "$elf" "$delay"

	mkdir -p "$root"
	install -m 0755 "$elf" "$root/init"
	test -x "$root/init"
	( cd "$root" && find . -print0 | cpio --null -ov --format=newc \
		| gzip -n -9 >"$cpio" )
	test -s "$cpio"
	echo "built $elf $(wc -c <"$elf" | tr -d ' ')B  $cpio $(wc -c <"$cpio" | tr -d ' ')B"
}

build_one 15
build_one 30
test "$(sha256sum "$OUT/init-proof-15s" | awk '{print $1}')" != \
	"$(sha256sum "$OUT/init-proof-30s" | awk '{print $1}')" \
	|| { echo "15s ELF == 30s ELF" >&2; exit 1; }
cp "$OUT/init-proof-15s" "$OUT/init-proof"
echo "OK init-proof"
