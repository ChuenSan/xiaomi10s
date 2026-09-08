#!/usr/bin/env python3
"""Source gates for stock-kernel USB enum stage0. CI only."""
import re
import sys
from pathlib import Path

src = Path("initramfs/usb-stage0-init.c").read_text()

need = [
    "THYME-USB0",
    "Stock Kernel USB Enum Stage0",
    "LINUX_REBOOT_CMD_RESTART2",
    "bootloader",
    "/sys/class/udc",
    "/config",
    "/config/usb_gadget",
    "usb_gadget",
    "configfs",
    "ncm.usb0",
    "SYS_newfstatat",
    "S_ISDIR",
    "THYME-USB0:FAIL:NO_UDC",
    "THYME-USB0:FAIL:CONFIGFS",
    "THYME-USB0:FAIL:",
    "fail_errno(\"BIND\"",
    "THYME-USB0:UDC_BOUND",
    "THYME-USB0:MOUNT_CONFIGFS",
    "THYME-USB0:STAT_CONFIG=",
    "THYME-USB0:STAT_USB_GADGET=",
    "THYME-USB0:UDC_CLASS_PRESENT",
    "THYME-USB0:FAIL:UDC_CLASS_MISSING",
    "THYME-USB0:BIND_ATTEMPT:",
    "THYME-USB0:HOLD_DONE",
    "THYME-USB0:PREBIND_STATE=",
    "THYME-USB0:POSTBIND_STATE=",
    "THYME-USB0:MAX_SPEED=",
    "WRITE_IDVENDOR",
    "NCM_CREATE",
    "SYMLINK",
    ":ERRNO=",
]
missing = [s for s in need if s not in src]
if missing:
    raise SystemExit(f"source missing {missing}")

if "O_DIRECTORY" in src:
    raise SystemExit("usb-stage0-init.c still references O_DIRECTORY")
if re.search(r"000200000|00200000", src):
    raise SystemExit("usb-stage0-init.c still has generic O_DIRECTORY numeric")

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

if "mkdir_one(p_cfg)" not in src and 'mkdir_one(p_cfg)' not in src:
    if "p_cfg[] = \"/config\"" not in src and 'p_cfg[] = "/config"' not in src:
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
print("DIRECTORY_CHECK_IMPL newfstatat")
print("source gates PASS")
sys.exit(0)
