#!/usr/bin/env bash
# Build static aarch64 init-proof ELF + gzip newc initramfs. GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local compile/pack" >&2
	exit 1
fi

SRC="${PWD}/initramfs/init-proof.c"
LDS="${PWD}/initramfs/init-proof.ld"
VERIFY="${PWD}/initramfs/verify-init-proof-elf.py"
OUT="${1:-$PWD/out-init-proof}"
CC="${CROSS_COMPILE:-aarch64-linux-gnu-}gcc"
LD="${CROSS_COMPILE:-aarch64-linux-gnu-}ld"
STRIP="${CROSS_COMPILE:-aarch64-linux-gnu-}strip"
READELF="${CROSS_COMPILE:-aarch64-linux-gnu-}readelf"

command -v "$CC" >/dev/null || { echo "missing $CC" >&2; exit 1; }
command -v "$LD" >/dev/null || { echo "missing $LD" >&2; exit 1; }
test -f "$SRC" && test -f "$LDS" && test -f "$VERIFY" || { echo "missing init-proof sources" >&2; exit 1; }

mkdir -p "$OUT"

verify_elf() {
	local f=$1 delay=$2
	local info
	info=$(file -b "$f")
	echo "file $f: $info"
	echo "$info" | grep -q "ELF 64-bit LSB" || { echo "not ELF 64-bit LSB: $f" >&2; exit 1; }
	echo "$info" | grep -qi aarch64 || { echo "not aarch64: $f" >&2; exit 1; }
	python3 "$VERIFY" "$f"
	"$READELF" -h "$f" | grep -Eq 'Type:[[:space:]]+EXEC' || { echo "ELF type not EXEC: $f" >&2; exit 1; }
	if "$READELF" -l "$f" | grep -q INTERP; then
		echo "INTERP present: $f" >&2
		exit 1
	fi
	if "$READELF" -d "$f" 2>/dev/null | grep -q NEEDED; then
		echo "dynamic NEEDED: $f" >&2
		exit 1
	fi
	echo "$info" | grep -q "statically linked" || echo "note: file(1) omitted 'statically linked'; INTERP/NEEDED empty"
	strings "$f" | grep -q "THYME-INITEXEC-PROOF" || { echo "ident missing: $f" >&2; exit 1; }
	strings "$f" | grep -q "DELAY=${delay}" || { echo "DELAY=$delay missing: $f" >&2; exit 1; }
	strings "$f" | grep -q "bootloader" || { echo "bootloader string missing: $f" >&2; exit 1; }
	"$READELF" -h "$f" | grep -q "Machine:.*AArch64" || { echo "Machine not AArch64: $f" >&2; exit 1; }
}

build_one() {
	local delay=$1
	local obj="$OUT/init-proof-${delay}s.o"
	local elf="$OUT/init-proof-${delay}s"
	local root="$OUT/root-${delay}s"
	local cpio="$OUT/initramfs-${delay}s.cpio.gz"

	"$CC" -ffreestanding -nostdlib -static -no-pie -fno-pic \
		-fno-stack-protector -fno-asynchronous-unwind-tables -fno-ident \
		-Os -Wall -Werror \
		-Wl,-e,main -Wl,--build-id=none -Wl,-z,noexecstack \
		-Wl,-Ttext-segment=0x400000 \
		-DDELAY_SECONDS="$delay" \
		-o "$elf" "$SRC"
	"$STRIP" -s "$elf"
	"$READELF" -h "$elf" | grep -E 'Entry point|Type:|Machine:' || true
	"$READELF" -l "$elf" || true
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
