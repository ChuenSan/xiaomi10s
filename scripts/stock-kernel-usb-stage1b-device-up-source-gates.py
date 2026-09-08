#!/usr/bin/env python3
"""Source gates for stock-kernel USB Stage1B device-netdev IFF_UP. CI only."""
import re
import sys
from pathlib import Path

src = Path("initramfs/usb-stage1b-device-up-init.c").read_text()

need = [
    "THYME-USB1B",
    "Stock Kernel USB Stage1B Device Up",
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
    "SIOCSIFFLAGS",
    "SYS_ioctl",
    "SYS_socket",
    "old_flags | IFF_UP",
    "THYME-USB1B:FAIL:NO_UDC",
    "THYME-USB1B:FAIL:CONFIGFS",
    "THYME-USB1B:FAIL:NO_NETDEV",
    "THYME-USB1B:FAIL:",
    "fail_errno(\"BIND\"",
    "fail_errno(\"IFF_UP\"",
    "fail_errno(\"SIOCGIFFLAGS\"",
    "THYME-USB1B:UDC_BOUND",
    "THYME-USB1B:MOUNT_CONFIGFS",
    "THYME-USB1B:STAT_CONFIG=",
    "THYME-USB1B:STAT_USB_GADGET=",
    "THYME-USB1B:UDC_CLASS_PRESENT",
    "THYME-USB1B:FAIL:UDC_CLASS_MISSING",
    "THYME-USB1B:BIND_ATTEMPT:",
    "THYME-USB1B:HOLD_DONE",
    "THYME-USB1B:PREBIND_STATE=",
    "THYME-USB1B:POSTBIND_STATE=",
    "THYME-USB1B:MAX_SPEED=",
    "THYME-USB1B:PREBIND_NETS=",
    "THYME-USB1B:NETDEV_AFTER_FUNCTION=",
    "THYME-USB1B:NETDEV_AFTER_LINK=",
    "THYME-USB1B:NETDEV_AFTER_BIND=",
    "THYME-USB1B:NETDEV_FOUND=",
    "THYME-USB1B:UDC_CONFIGURED",
    "THYME-USB1B:SIOCGIFFLAGS=YES",
    "THYME-USB1B:SIOCSIFFLAGS=YES",
    "THYME-USB1B:FLAGS_BEFORE=",
    "THYME-USB1B:IFF_UP_ATTEMPT",
    "THYME-USB1B:IFF_UP_OK",
    "THYME-USB1B:FLAGS_AFTER=",
    "THYME-USB1B:ADMIN_UP_AFTER=",
    "THYME-USB1B:DEV_ADDR=",
    "THYME-USB1B:HOST_ADDR=",
    "WRITE_IDVENDOR",
    "NCM_CREATE",
    "SYMLINK",
    ":ERRNO=",
    "CARRIER_ERRNO=",
    "ADMIN=",
    "OPER=",
]
missing = [s for s in need if s not in src]
if missing:
    raise SystemExit(f"source missing {missing}")

if "O_DIRECTORY" in src:
    raise SystemExit("usb-stage1b-device-up-init.c still references O_DIRECTORY")
if re.search(r"000200000|00200000", src):
    raise SystemExit("usb-stage1b-device-up-init.c still has generic O_DIRECTORY numeric")

forbid = [
    "SIOCSIFADDR",
    "SIOCSIFDSTADDR",
    "SIOCSIFNETMASK",
    "SIOCADDRT",
    "SIOCSIFMTU",
    "ifconfig",
    "DHCP",
    "dhclient",
    "10.66",
    "READ_ONLY_NETDEV_OBSERVATION",
]
hit = [s for s in forbid if s in src]
if hit:
    raise SystemExit(f"forbidden tokens {hit}")

if "old_flags | IFF_UP" not in src:
    raise SystemExit("missing old_flags | IFF_UP")
if re.search(r"ifr(?:\.u)?\.flags\s*=\s*IFF_UP\b", src):
    raise SystemExit("direct flags = IFF_UP is forbidden; must OR old_flags")
if re.search(r"ifr_flags\s*=\s*IFF_UP\b", src):
    raise SystemExit("direct ifr_flags = IFF_UP is forbidden")

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
print("USB0_CORE_REUSED PASS")
print("NETDEV_DISCOVERY PASS")
print("SIOCGIFFLAGS PASS")
print("SIOCSIFFLAGS PASS")
print("IFF_UP_OR_OLD_FLAGS PASS")
print("NO_IP_CONFIGURATION PASS")
print("NO_IP_LOGIC PASS")
print("NETDEV_DIFF_LOGIC PASS")
print("FAILSAFE PASS")
print("DIRECTORY_CHECK_IMPL newfstatat")
print("DESCRIPTOR_ONLY_PRODUCT Stock Kernel USB Stage1B Device Up")
print("DESCRIPTOR_ONLY_SERIAL THYME-USB1B")
print("source gates PASS")
sys.exit(0)
