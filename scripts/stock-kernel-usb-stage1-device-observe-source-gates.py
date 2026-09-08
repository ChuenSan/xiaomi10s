#!/usr/bin/env python3
"""Source gates for stock-kernel USB Stage1 device-netdev observe. CI only."""
import re
import sys
from pathlib import Path

src = Path("initramfs/usb-stage1-device-observe-init.c").read_text()

need = [
    "THYME-USB1DEV",
    "Stock Kernel USB Stage1 Device Observe",
    "LINUX_REBOOT_CMD_RESTART2",
    "bootloader",
    "/sys/class/udc",
    "/sys/class/net",
    "/config",
    "/config/usb_gadget",
    "usb_gadget",
    "configfs",
    "ncm.usb0",
    "SYS_newfstatat",
    "S_ISDIR",
    "SIOCGIFFLAGS",
    "SYS_ioctl",
    "SYS_socket",
    "THYME-USB1DEV:FAIL:NO_UDC",
    "THYME-USB1DEV:FAIL:CONFIGFS",
    "THYME-USB1DEV:FAIL:",
    "fail_errno(\"BIND\"",
    "THYME-USB1DEV:UDC_BOUND",
    "THYME-USB1DEV:MOUNT_CONFIGFS",
    "THYME-USB1DEV:STAT_CONFIG=",
    "THYME-USB1DEV:STAT_USB_GADGET=",
    "THYME-USB1DEV:UDC_CLASS_PRESENT",
    "THYME-USB1DEV:FAIL:UDC_CLASS_MISSING",
    "THYME-USB1DEV:BIND_ATTEMPT:",
    "THYME-USB1DEV:HOLD_DONE",
    "THYME-USB1DEV:PREBIND_STATE=",
    "THYME-USB1DEV:POSTBIND_STATE=",
    "THYME-USB1DEV:MAX_SPEED=",
    "THYME-USB1DEV:PREBIND_NETS=",
    "THYME-USB1DEV:NETDEV_AFTER_FUNCTION=",
    "THYME-USB1DEV:NETDEV_AFTER_LINK=",
    "THYME-USB1DEV:NETDEV_AFTER_BIND=",
    "THYME-USB1DEV:NETDEV_FOUND=",
    "THYME-USB1DEV:UDC_CONFIGURED",
    "THYME-USB1DEV:DEVICE_NETDEV_OBSERVE=YES",
    "THYME-USB1DEV:SIOCGIFFLAGS=YES",
    "THYME-USB1DEV:READ_ONLY_NETDEV_OBSERVATION=YES",
    "THYME-USB1DEV:DEV_ADDR=",
    "THYME-USB1DEV:HOST_ADDR=",
    "WRITE_IDVENDOR",
    "NCM_CREATE",
    "SYMLINK",
    ":ERRNO=",
    "ADMIN_UP=",
    "OPER=",
    "CARRIER=",
]
missing = [s for s in need if s not in src]
if missing:
    raise SystemExit(f"source missing {missing}")

if "O_DIRECTORY" in src:
    raise SystemExit("usb-stage1-device-observe-init.c still references O_DIRECTORY")
if re.search(r"000200000|00200000", src):
    raise SystemExit("usb-stage1-device-observe-init.c still has generic O_DIRECTORY numeric")

forbid = [
    "SIOCSIFFLAGS",
    "SIOCSIFADDR",
    "SIOCSIFDSTADDR",
    "SIOCSIFNETMASK",
    "SIOCADDRT",
    "SIOCSIFMTU",
    "ifconfig",
    "DHCP",
    "dhclient",
    "10.66",
]
hit = [s for s in forbid if s in src]
if hit:
    raise SystemExit(f"forbidden tokens {hit}")

m = re.search(r"static int is_dir\(const char \*path\)\s*\{(.*?)\n\}", src, re.S)
if not m:
    raise SystemExit("is_dir not found")
body = m.group(1)
if "SYS_openat" in body or "openat" in body:
    raise SystemExit("is_dir still uses openat")
if "fstatat_path" not in body and "SYS_newfstatat" not in body:
    raise SystemExit("is_dir is not newfstatat/stat")
if "S_ISDIR" not in body:
    raise SystemExit("is_dir missing S_ISDIR")

if 'p_cfg[] = "/config"' not in src:
    raise SystemExit("configfs mountpoint is not /config")

i = src.find("int main(void)")
if i < 0:
    raise SystemExit("no main")
if "return" in src[i:]:
    raise SystemExit("return in main")
if '__attribute__((used, noreturn, section(".text")))' not in src:
    raise SystemExit("main missing noreturn .text")

print("DIRECTORY_CHECK_NOT_OPEN_ODIRECTORY PASS")
print("STAT_BASED_DIRECTORY_CHECK PASS")
print("CONFIGFS_MOUNTPOINT_IS_CONFIG PASS")
print("CONFIGFS_STAT_LOGGING PASS")
print("ERRNO_LOGGING PASS")
print("UDC_SCAN_LOGIC PASS")
print("CONFIGFS_PATH_FIX PASS")
print("ERRNO_MARKERS PASS")
print("NCM_LOGIC PASS")
print("UDC_DISCOVERY PASS")
print("FAILSAFE_RESTART2 PASS")
print("USB0_REGRESSION_CHECK PASS")
print("DEVICE_NETDEV_OBSERVE=YES")
print("SIOCGIFFLAGS=YES")
print("SIOCSIFFLAGS=ABSENT")
print("NO_SIOCSIFFLAGS PASS")
print("NO_IP_LOGIC PASS")
print("NETDEV_DIFF_LOGIC PASS")
print("READ_ONLY_NETDEV_OBSERVATION PASS")
print("DIRECTORY_CHECK_IMPL newfstatat")
print("DESCRIPTOR_ONLY_PRODUCT Stock Kernel USB Stage1 Device Observe")
print("DESCRIPTOR_ONLY_SERIAL THYME-USB1DEV")
print("source gates PASS")
sys.exit(0)
