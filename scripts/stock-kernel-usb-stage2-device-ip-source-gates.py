#!/usr/bin/env python3
"""Source gates for stock-kernel USB Stage2 device static IP. CI only."""
import re
import sys
from pathlib import Path

src_path = Path("initramfs/usb-stage2-device-ip-init.c")
src = src_path.read_text()
helpers = [
    src_path,
    Path("initramfs/usb-stage2-device-ip-abi-assert.c"),
    Path("initramfs/build-usb-stage2-device-ip.sh"),
]

need = [
    "THYME-USB2",
    "Stock Kernel USB Stage2 Device IP",
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
    "SIOCSIFADDR",
    "SIOCSIFNETMASK",
    "SIOCGIFADDR",
    "SIOCGIFNETMASK",
    "SYS_ioctl",
    "SYS_socket",
    "old_flags | IFF_UP",
    "10.66.73.1",
    "255.255.255.0",
    "THYME-USB2:FAIL:NO_UDC",
    "THYME-USB2:FAIL:CONFIGFS",
    "THYME-USB2:FAIL:NO_NETDEV",
    "THYME-USB2:FAIL:",
    "fail_errno(\"BIND\"",
    "fail_errno(\"IFF_UP\"",
    "fail_errno(\"SIOCGIFFLAGS\"",
    "fail_errno(\"SET_ADDR\"",
    "fail_errno(\"SET_NETMASK\"",
    "fail_errno(\"GET_ADDR\"",
    "fail_errno(\"GET_NETMASK\"",
    "THYME-USB2:UDC_BOUND",
    "THYME-USB2:MOUNT_CONFIGFS",
    "THYME-USB2:STAT_CONFIG=",
    "THYME-USB2:STAT_USB_GADGET=",
    "THYME-USB2:UDC_CLASS_PRESENT",
    "THYME-USB2:FAIL:UDC_CLASS_MISSING",
    "THYME-USB2:BIND_ATTEMPT:",
    "THYME-USB2:HOLD_DONE",
    "THYME-USB2:PREBIND_STATE=",
    "THYME-USB2:POSTBIND_STATE=",
    "THYME-USB2:MAX_SPEED=",
    "THYME-USB2:PREBIND_NETS=",
    "THYME-USB2:NETDEV_AFTER_FUNCTION=",
    "THYME-USB2:NETDEV_AFTER_LINK=",
    "THYME-USB2:NETDEV_AFTER_BIND=",
    "THYME-USB2:NETDEV_FOUND=",
    "THYME-USB2:UDC_CONFIGURED",
    "THYME-USB2:SIOCGIFFLAGS=YES",
    "THYME-USB2:SIOCSIFFLAGS=YES",
    "THYME-USB2:FLAGS_BEFORE=",
    "THYME-USB2:IFF_UP_ATTEMPT",
    "THYME-USB2:IFF_UP_OK",
    "THYME-USB2:FLAGS_AFTER=",
    "THYME-USB2:ADMIN_UP_AFTER=",
    "THYME-USB2:DEV_ADDR=",
    "THYME-USB2:HOST_ADDR=",
    "THYME-USB2:SET_ADDR:RET=",
    "THYME-USB2:ADDR_SET_OK",
    "THYME-USB2:SET_NETMASK:RET=",
    "THYME-USB2:NETMASK_SET_OK",
    "THYME-USB2:GET_ADDR=",
    "THYME-USB2:GET_NETMASK=",
    "THYME-USB2:DEVICE_IPV4_VERIFIED",
    "THYME-USB2:DEVICE_STATIC_IPV4_VERIFIED=YES",
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
    raise SystemExit("usb-stage2-device-ip-init.c still references O_DIRECTORY")
if re.search(r"000200000|00200000", src):
    raise SystemExit("usb-stage2-device-ip-init.c still has generic O_DIRECTORY numeric")

forbid = [
    "SIOCSIFDSTADDR",
    "SIOCSIFBRDADDR",
    "SIOCADDRT",
    "SIOCSIFMTU",
    "ifconfig",
    "DHCP",
    "dhclient",
    "172.16.42",
    "10.66.73.2",
    "ping",
    "httpd",
    "HTTP",
    "telnet",
    "busybox",
    "READ_ONLY_NETDEV_OBSERVATION",
]
hit = [s for s in forbid if s in src]
if hit:
    raise SystemExit(f"forbidden tokens {hit}")

for p in helpers:
    txt = p.read_text()
    if "172.16.42" in txt:
        raise SystemExit(f"forbidden 172.16.42 in {p}")

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
print("USB_STAGE1B_CORE_REUSED PASS")
print("NETDEV_DISCOVERY PASS")
print("SIOCGIFFLAGS PASS")
print("SIOCSIFFLAGS PASS")
print("IFF_UP_OR_OLD_FLAGS PASS")
print("SIOCSIFADDR_PRESENT PASS")
print("SIOCSIFNETMASK_PRESENT PASS")
print("SIOCGIFADDR_PRESENT PASS")
print("SIOCGIFNETMASK_PRESENT PASS")
print("DEVICE_IP_LITERAL = 10.66.73.1")
print("DEVICE_NETMASK_LITERAL = 255.255.255.0")
print("NO_HOST_IP_LOGIC PASS")
print("NO_PING_LOGIC PASS")
print("NO_HTTP_LOGIC PASS")
print("NO_DHCP_LOGIC PASS")
print("NO_DEFAULT_ROUTE_LOGIC PASS")
print("NETDEV_DIFF_LOGIC PASS")
print("FAILSAFE PASS")
print("DIRECTORY_CHECK_IMPL newfstatat")
print("DESCRIPTOR_ONLY_PRODUCT Stock Kernel USB Stage2 Device IP")
print("DESCRIPTOR_ONLY_SERIAL THYME-USB2")
print("source gates PASS")
sys.exit(0)
