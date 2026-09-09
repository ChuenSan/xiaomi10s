#!/usr/bin/env bash
# Build static aarch64 usb-stage4-http-init + gzip newc initramfs.
# GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local compile/pack" >&2
	exit 1
fi

SRC="${PWD}/initramfs/usb-stage4-http-init.c"
ABI="${PWD}/initramfs/usb-stage4-http-abi-assert.c"
VERIFY="${PWD}/initramfs/verify-init-proof-elf.py"
OUT="${1:-$PWD/out-usb-stage4-http}"
CC="${CROSS_COMPILE:-aarch64-linux-gnu-}gcc"
STRIP="${CROSS_COMPILE:-aarch64-linux-gnu-}strip"
READELF="${CROSS_COMPILE:-aarch64-linux-gnu-}readelf"

BUILD_MARKER="${BUILD_MARKER:-${GITHUB_SHA:-}}"
BUILD_MARKER="${BUILD_MARKER:0:7}"
if ! printf '%s\n' "$BUILD_MARKER" | grep -Eq '^[0-9a-fA-F]{7}$'; then
	echo "BUILD_MARKER must be a 7-character commit marker" >&2
	exit 1
fi

command -v "$CC" >/dev/null || { echo "missing $CC" >&2; exit 1; }
test -f "$SRC" && test -f "$VERIFY" && test -f "$ABI" || {
	echo "missing usb-stage4-http sources" >&2
	exit 1
}

mkdir -p "$OUT"
elf="$OUT/usb-stage4-http-init"
root="$OUT/root"
cpio="$OUT/initramfs.cpio.gz"
marker_h="$OUT/build-marker.h"
printf '#define BUILD_MARKER "%s"\n' "$BUILD_MARKER" >"$marker_h"

echo "BUILD_MARKER=$BUILD_MARKER"
"$CC" -ffreestanding -Wall -Werror -dM -E -x c \
	-include linux/fcntl.h -include linux/sockios.h /dev/null \
	| grep -E '__NR_(socket|fcntl|bind|listen|accept|sendto|setsockopt)|O_NONBLOCK|F_GETFL|F_SETFL' \
	| tee "$OUT/abi-oflags.txt" || true
"$CC" -ffreestanding -Wall -Werror -c -o "$OUT/usb-stage4-http-abi-assert.o" "$ABI"
echo "ABI_ASSERT PASS O_DIRECTORY=040000 O_DIRECT=0200000 newfstatat=79 ioctl=29 socket=198 fcntl=25 bind=200 listen=201 accept=202 sendto=206 setsockopt=208 SO_REUSEADDR=2"

"$CC" -ffreestanding -nostdlib -static -no-pie -fno-pic \
	-fno-stack-protector -fno-asynchronous-unwind-tables -fno-ident \
	-Os -Wall -Werror -include "$marker_h" \
	-Wl,-e,main -Wl,--build-id=none -Wl,-z,noexecstack \
	-Wl,-Ttext-segment=0x400000 \
	-o "$elf" "$SRC"
"$STRIP" -s "$elf"
"$READELF" -h "$elf" | grep -E 'Entry point|Type:|Machine:' || true
"$READELF" -l "$elf" || true

info=$(file -b "$elf")
echo "file $elf: $info"
echo "$info" | grep -q "ELF 64-bit LSB" || { echo "not ELF 64-bit LSB" >&2; exit 1; }
echo "$info" | grep -qi aarch64 || { echo "not aarch64" >&2; exit 1; }
python3 "$VERIFY" "$elf"
"$READELF" -h "$elf" | grep -Eq 'Type:[[:space:]]+EXEC' || { echo "ELF type not EXEC" >&2; exit 1; }
if "$READELF" -l "$elf" | grep -q INTERP; then
	echo "INTERP present" >&2
	exit 1
fi
if "$READELF" -d "$elf" 2>/dev/null | grep -q NEEDED; then
	echo "dynamic NEEDED" >&2
	exit 1
fi
for s in \
	"THYME-USB4:INIT" \
	"Stock Kernel USB Stage4 HTTP" \
	"thyme-mainline" \
	"0x1d6b" \
	"0x0104" \
	"THYME-USB4" \
	"THYME-USB4:SOCKET_OK" \
	"THYME-USB4:BIND_ATTEMPT=10.66.73.1:8080" \
	"THYME-USB4:BIND_OK" \
	"THYME-USB4:LISTEN_OK:10.66.73.1:8080" \
	"THYME-USB4:HTTP_READY" \
	"THYME-USB4:ACCEPT_OK" \
	"THYME-USB4:REQUEST_RX" \
	"THYME-USB4:HTTP_200_SENT" \
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
	strings "$elf" | grep -Fq "$s" || { echo "missing string: $s" >&2; exit 1; }
done
"$READELF" -h "$elf" | grep -q "Machine:.*AArch64" || { echo "Machine not AArch64" >&2; exit 1; }

mkdir -p "$root"
install -m 0755 "$elf" "$root/init"
test -x "$root/init"
( cd "$root" && find . -print0 | cpio --null -ov --format=newc \
	| gzip -n -9 >"$cpio" )
test -s "$cpio"
echo "built $elf $(wc -c <"$elf" | tr -d ' ')B  $cpio $(wc -c <"$cpio" | tr -d ' ')B"
echo "OK usb-stage4-http-init BUILD=$BUILD_MARKER"
