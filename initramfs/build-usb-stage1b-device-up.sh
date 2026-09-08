#!/usr/bin/env bash
# Build static aarch64 usb-stage1b-device-up-init + gzip newc initramfs.
# GitHub Actions only.
set -euo pipefail
if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local compile/pack" >&2
	exit 1
fi

SRC="${PWD}/initramfs/usb-stage1b-device-up-init.c"
ABI="${PWD}/initramfs/usb-stage1b-device-up-abi-assert.c"
VERIFY="${PWD}/initramfs/verify-init-proof-elf.py"
OUT="${1:-$PWD/out-usb-stage1b-device-up}"
CC="${CROSS_COMPILE:-aarch64-linux-gnu-}gcc"
STRIP="${CROSS_COMPILE:-aarch64-linux-gnu-}strip"
READELF="${CROSS_COMPILE:-aarch64-linux-gnu-}readelf"

command -v "$CC" >/dev/null || { echo "missing $CC" >&2; exit 1; }
test -f "$SRC" && test -f "$VERIFY" && test -f "$ABI" || { echo "missing usb-stage1b-device-up sources" >&2; exit 1; }

mkdir -p "$OUT"
elf="$OUT/usb-stage1b-device-up-init"
root="$OUT/root"
cpio="$OUT/initramfs.cpio.gz"

"$CC" -ffreestanding -Wall -Werror -dM -E -x c \
	-include linux/fcntl.h -include linux/sockios.h /dev/null \
	| grep -E 'O_DIRECTORY|O_DIRECT|SIOCGIFFLAGS|SIOCSIFFLAGS' | tee "$OUT/abi-oflags.txt" || true
"$CC" -ffreestanding -Wall -Werror -c -o "$OUT/usb-stage1b-device-up-abi-assert.o" "$ABI"
echo "ABI_ASSERT PASS O_DIRECTORY=040000 O_DIRECT=0200000 newfstatat=79 ioctl=29 socket=198 SIOCGIFFLAGS=0x8913 SIOCSIFFLAGS=0x8914"

"$CC" -ffreestanding -nostdlib -static -no-pie -fno-pic \
	-fno-stack-protector -fno-asynchronous-unwind-tables -fno-ident \
	-Os -Wall -Werror \
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
	"THYME-USB1B:INIT" \
	"Stock Kernel USB Stage1B Device Up" \
	"THYME-USB1B" \
	"bootloader" \
	"ncm.usb0" \
	"/sys/class/udc" \
	"/sys/class/net" \
	"/config" \
	"configfs" \
	"THYME-USB1B:MOUNT_CONFIGFS" \
	"THYME-USB1B:STAT_USB_GADGET" \
	"THYME-USB1B:BIND_ATTEMPT" \
	"THYME-USB1B:NETDEV_FOUND" \
	"THYME-USB1B:FLAGS_BEFORE" \
	"THYME-USB1B:IFF_UP_ATTEMPT" \
	"THYME-USB1B:IFF_UP_OK" \
	"THYME-USB1B:FLAGS_AFTER" \
	"THYME-USB1B:UDC_CONFIGURED" \
	"THYME-USB1B:HOLD_DONE" \
	"THYME-USB1B:FAIL:NO_NETDEV"
do
	strings "$elf" | grep -q "$s" || { echo "missing string: $s" >&2; exit 1; }
done
strings "$elf" | grep -q "THYME-USB1B:SIOCSIFFLAGS=YES" || { echo "missing SIOCSIFFLAGS marker" >&2; exit 1; }
"$READELF" -h "$elf" | grep -q "Machine:.*AArch64" || { echo "Machine not AArch64" >&2; exit 1; }

mkdir -p "$root"
install -m 0755 "$elf" "$root/init"
test -x "$root/init"
( cd "$root" && find . -print0 | cpio --null -ov --format=newc \
	| gzip -n -9 >"$cpio" )
test -s "$cpio"
echo "built $elf $(wc -c <"$elf" | tr -d ' ')B  $cpio $(wc -c <"$cpio" | tr -d ' ')B"
echo "OK usb-stage1b-device-up-init"
