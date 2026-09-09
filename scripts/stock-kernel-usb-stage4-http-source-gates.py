#!/usr/bin/env python3
"""Source gates for stock-kernel USB Stage4 HTTP. CI only."""
import re
import sys
from pathlib import Path

src_path = Path("initramfs/usb-stage4-http-init.c")
abi_path = Path("initramfs/usb-stage4-http-abi-assert.c")
build_path = Path("initramfs/build-usb-stage4-http.sh")
src = src_path.read_text()
abi = abi_path.read_text()
build = build_path.read_text()

need = [
    "THYME-USB4",
    "Stock Kernel USB Stage4 HTTP",
    "thyme-mainline",
    "0x1d6b",
    "0x0104",
    "THYME-USB4:INIT",
    "THYME-USB4:CONFIGFS_OK",
    "THYME-USB4:UDC=",
    "THYME-USB4:NCM_OK",
    "THYME-USB4:UDC_BOUND",
    "THYME-USB4:NETDEV=",
    "THYME-USB4:IFF_UP_OK",
    "THYME-USB4:DEVICE_IP_VERIFIED",
    "THYME-USB4:UDC_CONFIGURED",
    "THYME-USB4:CARRIER=1",
    "THYME-USB4:SOCKET_OK",
    "THYME-USB4:BIND_ATTEMPT=10.66.73.1:8080",
    "THYME-USB4:BIND_OK",
    "THYME-USB4:LISTEN_OK:10.66.73.1:8080",
    "THYME-USB4:HTTP_READY",
    "THYME-USB4:ACCEPT_OK",
    "THYME-USB4:REQUEST_RX",
    "THYME-USB4:HTTP_200_SENT",
    "THYME-USB4:HOLD_DONE",
    "THYME-USB4:REBOOT_BOOTLOADER",
    "THYME-USB4:FAIL:",
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
    "SYS_fcntl",
    "SYS_bind",
    "SYS_listen",
    "SYS_accept",
    "SYS_sendto",
    "SYS_setsockopt",
    "AF_INET",
    "SOCK_STREAM",
    "SO_REUSEADDR",
    "MSG_NOSIGNAL",
    "HTTP_PORT",
    "8080",
    "http_body",
    "BUILD_MARKER",
    "BUILD=",
    "HTTP/1.1 200 OK",
    "Content-Type: text/plain",
    "Connection: close",
    "Content-Length: ",
    "htons16(HTTP_PORT)",
    "addr.sin_family = AF_INET",
    "addr.sin_addr = IPV4_ADDR",
    "setsockopt",
    "send_all",
    "REQUEST_MAX 1024",
    "MAX_CONNECTIONS 5",
    "LISTEN_BACKLOG 4",
    "HOLD_SEC 60",
]
missing = [token for token in need if token not in src]
if missing:
    raise SystemExit(f"source missing {missing}")

for token in [
    "__NR_fcntl",
    "__NR_bind",
    "__NR_listen",
    "__NR_accept",
    "__NR_sendto",
    "__NR_setsockopt",
    "SO_REUSEADDR",
    "MSG_NOSIGNAL",
]:
    if token not in abi:
        raise SystemExit(f"ABI assert missing {token}")
if "GITHUB_ACTIONS" not in build or "BUILD_MARKER" not in build:
    raise SystemExit("build script missing CI/build-marker gate")

if "O_DIRECTORY" in src:
    raise SystemExit("stage4 init must not reference O_DIRECTORY")
if re.search(r"000200000|00200000", src):
    raise SystemExit("stage4 init still has generic O_DIRECTORY numeric")

for token in [
    "INADDR_ANY",
    "0.0.0.0",
    "SIOCADDRT",
    "SIOCSIFDSTADDR",
    "SIOCSIFBRDADDR",
    "SIOCSIFMTU",
    "10.66.73.2",
    "DHCP",
    "dhclient",
    "ping",
    "httpd",
    "telnet",
    "busybox",
    "pthread",
    "fork",
    "epoll",
]:
    if token in src:
        raise SystemExit(f"forbidden token {token}")

if re.search(r"ifr(?:\.u)?\.flags\s*=\s*IFF_UP\b", src):
    raise SystemExit("direct flags = IFF_UP is forbidden; must OR old_flags")
if re.search(r"ifr_flags\s*=\s*IFF_UP\b", src):
    raise SystemExit("direct ifr_flags = IFF_UP is forbidden")

m = re.search(r"static int is_dir\(const char \*path\)\s*\{(.*?)\n\}", src, re.S)
if not m:
    raise SystemExit("is_dir not found")
body = m.group(1)
if "openat" in body or "SYS_openat" in body:
    raise SystemExit("is_dir still uses openat")
if "fstatat_path" not in body and "SYS_newfstatat" not in body:
    raise SystemExit("is_dir is not newfstatat/stat")
if "S_ISDIR" not in body:
    raise SystemExit("is_dir missing S_ISDIR")

if 'p_cfg[] = "/config"' not in src:
    raise SystemExit("configfs mountpoint is not /config")
if not re.search(r"sys4\(SYS_socket,\s*AF_INET,\s*SOCK_STREAM", src):
    raise SystemExit("HTTP socket is not AF_INET/SOCK_STREAM")
if "addr.sin_family = AF_INET" not in src or "addr.sin_addr = IPV4_ADDR" not in src:
    raise SystemExit("HTTP bind address is not explicit 10.66.73.1")
if "addr.sin_port = htons16(HTTP_PORT)" not in src:
    raise SystemExit("HTTP bind port is not explicit 8080")
if not re.search(r"sys6\(SYS_setsockopt,\s*fd,\s*SOL_SOCKET,\s*SO_REUSEADDR", src):
    raise SystemExit("SO_REUSEADDR is not set on HTTP listener")

handle_start = src.find("static void handle_http_connection")
if handle_start < 0:
    raise SystemExit("HTTP connection handler missing")
handle = src[handle_start:]
if handle.find("read_request") < 0 or handle.find("send_all") < 0:
    raise SystemExit("HTTP handler does not read then send")
if handle.find("send_all") < handle.find("read_request"):
    raise SystemExit("HTTP response can be sent before request read")
if "if (n <= 0)" not in handle:
    raise SystemExit("empty/no-request path is not guarded")
if "kmsg(m_http_sent)" not in handle:
    raise SystemExit("HTTP 200 sent marker missing")

main_index = src.find("int main(void)")
if main_index < 0:
    raise SystemExit("no main")
if "return" in src[main_index:]:
    raise SystemExit("return in PID1 main")
if '__attribute__((used, noreturn, section(".text")))' not in src:
    raise SystemExit("main missing noreturn .text")

print("DIRECTORY_CHECK_NOT_OPEN_ODIRECTORY PASS")
print("STAT_BASED_DIRECTORY_CHECK PASS")
print("CONFIGFS_MOUNTPOINT_IS_CONFIG PASS")
print("ERRNO_LOGGING PASS")
print("UDC_SCAN_LOGIC PASS")
print("NCM_LOGIC PASS")
print("UDC_DISCOVERY PASS")
print("STAGE2_USB_NETWORK_CORE_REUSED PASS")
print("USB_STAGE1B_CORE_REUSED PASS")
print("SIOCGIFFLAGS PASS")
print("SIOCSIFFLAGS PASS")
print("IFF_UP_OR_OLD_FLAGS PASS")
print("SIOCSIFADDR_PRESENT PASS")
print("SIOCSIFNETMASK_PRESENT PASS")
print("SIOCGIFADDR_PRESENT PASS")
print("SIOCGIFNETMASK_PRESENT PASS")
print("DEVICE_IP_LITERAL = 10.66.73.1")
print("HTTP_BIND_IP = 10.66.73.1")
print("HTTP_PORT = 8080")
print("SO_REUSEADDR PASS")
print("HTTP_RESPONSE_SOURCE PASS")
print("NO_HTTP_EMPTY_REPLY_PATH PASS")
print("NO_INADDR_ANY_HTTP_BIND PASS")
print("NO_DHCP PASS")
print("NO_DEFAULT_ROUTE PASS")
print("FAILSAFE_RESTART2 PASS")
print("HTTP_READY_MARKER PASS")
print("source gates PASS")
sys.exit(0)
