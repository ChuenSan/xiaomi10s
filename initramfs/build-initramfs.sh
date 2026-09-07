#!/usr/bin/env bash
# Build the thyme first-boot initramfs:  BusyBox 1.36.1 static aarch64
# + /init + cpio.gz.  GITHUB ACTIONS ONLY — never run locally..
#
# Usage ( CI*:  apt provides gcc-aarch64-linux-gnu;  run from repo root..
set -euo pipefail

# pinned to the newest tag the GitHub mirror actually publishes (1_36_1*:
# busybox.net TLS is unreachable from GitHub runners (verified 2026-09*..
BUSYBOX_VERSION="1.36.1"
TARBALL="busybox-${BUSYBOX_VERSION}.tar.gz"
# GitHub mirror busybox.net is flaky from CI; official mirror/busybox tags: 1_36_1
URL="https://github.com/mirror/busybox/archive/refs/tags/${BUSYBOX_VERSION//./_}.tar.gz"
BUSYBOX_SRC="${1:-$PWD/.cache/busybox-${BUSYBOX_VERSION}}"
CONFIG_SRC="${2:-$PWD/configs/busybox-thyme.config}"
OUT_DIR="${3:-$PWD/out-initramfs}"
INIT_SRC="${4:-$PWD/initramfs/init}"

CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"

echo "== busybox ${BUSYBOX_VERSION} (static aarch64*"
command -v "${CROSS_COMPILE}gcc" || { echo "CROSS GCC MISSING: ${CROSS_COMPILE}gcc"; exit 1; }
if [ ! -f "${BUSYBOX_SRC}/.config" ]; then
	mkdir -p "$(dirname "${BUSYBOX_SRC}")"
	if [ ! -f "${BUSYBOX_SRC}/Makefile" ]; then
		mkdir -p "${BUSYBOX_SRC}"
		if ! curl -fsSL "${URL}" -o "${BUSYBOX_SRC}.tar.gz"; then
			echo "DOWNLOAD FAILED: ${URL}" >&2
			exit 1
		fi
		echo "== busybox: tarball downloaded =="
		tar -xzf "${BUSYBOX_SRC}.tar.gz" -C "${BUSYBOX_SRC}" --strip-components 1
		echo "== busybox: source extracted =="
	fi
fi

cd "${BUSYBOX_SRC}"
cp "${CONFIG_SRC}" .config
echo "== busybox: defconfig =="
# busybox kconfig prompts for each choice/NEW symbol when .config is a fragment;
# a FULL defconfig carries every symbol ( hence zero prompts*; wrap in pty anyway for
# the rare tty check, feeding 200 default answers just in case.
command -v script >/dev/null || { echo "script (util-linux) missing — needed as TTY bridge for busybox defconfig"; exit 1; }
i=0; while [ "$i" -lt 200 ]; do echo Y; i=$((i+1)); done > /tmp/bb-answers
script -qefc "make defconfig" /dev/null < /tmp/bb-answers
echo "== busybox: defconfig done =="
# defconfig defaults enable ash/applets/symlinks; static is the sole flip we need.
# ( kernel-om' kernel' scripts/config tool is absent from busybox; text sed is enough*.
# busybox kconfig writes an unset bool as '# CONFIG_STATIC is not set' ( not CONFIG_STATIC=n*;
# kernels' scripts/config tool is absent from busybox; cover both forms with sed.*
sed -i -e 's/^CONFIG_STATIC=n$/CONFIG_STATIC=y/' -e 's/^# CONFIG_STATIC is not set$/CONFIG_STATIC=y/' .config
grep -q "^CONFIG_STATIC=y$" .config || { echo "CONFIG_STATIC=y not in .config after defconfig+sed"; exit 1; }
echo "== busybox: overlay done =="
make -j"$(nproc)" CROSS_COMPILE="${CROSS_COMPILE}" busybox
echo "== busybox: build done =="

# ---- assemble initramfs root ----
rm -rf "${OUT_DIR}/root"
mkdir -p "${OUT_DIR}/root"
make CROSS_COMPILE="${CROSS_COMPILE}" CONFIG_PREFIX="${OUT_DIR}/root" install
echo "== busybox: install done =="

install -Dm755 "${INIT_SRC}" "${OUT_DIR}/root/init"
#( busybox has already created /bin + applet symlinks in the prefix*.{
# ( busybox has already created /bin + applet symlinks in the prefix*

# ---- cpio.gz ----
( cd "${OUT_DIR}/root" && find . -print0 | cpio --null -ov --format=newc \
	| gzip -9 > "${OUT_DIR}/initramfs.cpio.gz" 2>/dev/null)

# ---- self-validation ----
test -x "${OUT_DIR}/root/init" || { echo "init not executable"; exit 1; }
test -x "${OUT_DIR}/root/bin/busybox" || { echo "busybox missing"; exit 1; }
file "${OUT_DIR}/root/bin/busybox" | grep -q "statically linked" \
	|| { echo "busybox not static"; exit 1; }
for a in cat mount ifconfig telnetd httpd dmesg sh; do
	test -x "${OUT_DIR}/root/bin/${a}" || { echo "applet symlink missing: ${a}"; exit 1; }
done

echo "== initramfs artifacts =="
ls -la "${OUT_DIR}/initramfs.cpio.gz" "${OUT_DIR}/root/bin/busybox"
echo "BUSYBOX_VERSION=${BUSYBOX_VERSION}" > "${OUT_DIR}/busybox-version.txt"
echo "OK initramfs"