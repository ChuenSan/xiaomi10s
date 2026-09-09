/*
 * PID 1: STOCK_KERNEL_USB_STAGE4_HTTP
 * USB0/Stage1B path reused: newfstatat + S_ISDIR, configfs NCM, UDC bind,
 * SIOCSIFFLAGS old_flags | IFF_UP.
 * Added: SIOCSIFADDR 10.66.73.1 + SIOCSIFNETMASK 255.255.255.0, then GET verify,
 * followed by a bounded TCP/HTTP listener on 10.66.73.1:8080.
 * No default route, no host address, no userspace network setup.
 *
 * TEST ONLY identity 1d6b:0104 (Linux Foundation gadget).
 * NOT PRODUCTION USB IDENTITY.
 *
 * GitHub Actions only.
 */
#ifndef __aarch64__
#error "usb-stage4-http-init is aarch64 only"
#endif

#include <asm/unistd.h>
#include <linux/fcntl.h>
#include <linux/reboot.h>

#define SYS_mkdirat __NR_mkdirat
#define SYS_mknodat __NR_mknodat
#define SYS_symlinkat __NR_symlinkat
#define SYS_mount __NR_mount
#define SYS_openat __NR_openat
#define SYS_close __NR_close
#define SYS_getdents64 __NR_getdents64
#define SYS_read __NR_read
#define SYS_write __NR_write
#define SYS_sync __NR_sync
#define SYS_nanosleep __NR_nanosleep
#define SYS_reboot __NR_reboot
#define SYS_newfstatat __NR_newfstatat
#define SYS_ioctl __NR_ioctl
#define SYS_socket __NR_socket
#define SYS_fcntl __NR_fcntl
#define SYS_bind __NR_bind
#define SYS_listen __NR_listen
#define SYS_accept __NR_accept
#define SYS_sendto __NR_sendto
#define SYS_setsockopt __NR_setsockopt

#ifndef AT_FDCWD
#define AT_FDCWD (-100)
#endif

#define EINTR 4
#define EAGAIN 11
#define ENOENT 2
#define EBUSY 16
#define EEXIST 17

#define S_IFMT 00170000
#define S_IFDIR 0040000
#define S_IFCHR 0020000
#define S_ISDIR(m) (((m) & S_IFMT) == S_IFDIR)

#define HOLD_SEC 60
#define FAIL_SEC 5
#define UDC_TRIES 10
#define NETDEV_WAIT_TRIES 40
#define NETDEV_WAIT_NS 50000000L
#define LINK_READY_TRIES 100
#define LINK_READY_NS 100000000L
#define ACCEPT_POLL_NS 100000000L
#define REQUEST_WAIT_NS 50000000L
#define REQUEST_TRIES 40
#define SEND_TRIES 40
#define MAX_CONNECTIONS 5
#define LISTEN_BACKLOG 4
#define REQUEST_MAX 1024
#define RESPONSE_MAX 512
#define HTTP_PORT 8080

#define AF_INET 2
#define SOCK_STREAM 1
#define SOCK_DGRAM 2
#ifndef SOL_SOCKET
#define SOL_SOCKET 1
#endif
#ifndef SO_REUSEADDR
#define SO_REUSEADDR 2
#endif
#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0x4000
#endif
#ifndef F_GETFL
#define F_GETFL 3
#endif
#ifndef F_SETFL
#define F_SETFL 4
#endif
#ifndef O_NONBLOCK
#define O_NONBLOCK 00004000
#endif
#define SIOCGIFFLAGS 0x8913
#define SIOCSIFFLAGS 0x8914
#define SIOCGIFADDR 0x8915
#define SIOCSIFADDR 0x8916
#define SIOCGIFNETMASK 0x891b
#define SIOCSIFNETMASK 0x891c
#define IFF_UP 1
#define IFNAMSIZ 16
#define MAX_NETS 32
#define DT_REG 8
/* 10.66.73.1 / 255.255.255.0 as network-order bytes in a LE uint32 */
#define IPV4_ADDR 0x0149420au
#define IPV4_MASK 0x00ffffffu

/* aarch64 asm-generic/stat.h (stock 4.19 UAPI). st_mode at offset 16. */
struct kstat {
	unsigned long st_dev;
	unsigned long st_ino;
	unsigned int st_mode;
	unsigned int st_nlink;
	unsigned int st_uid;
	unsigned int st_gid;
	unsigned long st_rdev;
	unsigned long __pad1;
	long st_size;
	int st_blksize;
	int __pad2;
	long st_blocks;
	long st_atime;
	unsigned long st_atime_nsec;
	long st_mtime;
	unsigned long st_mtime_nsec;
	long st_ctime;
	unsigned long st_ctime_nsec;
	unsigned int __unused4;
	unsigned int __unused5;
};

_Static_assert(sizeof(struct kstat) == 128, "aarch64 struct stat size");
_Static_assert(__builtin_offsetof(struct kstat, st_mode) == 16,
	       "aarch64 st_mode offset");
_Static_assert(SIOCGIFFLAGS == 0x8913, "SIOCGIFFLAGS");
_Static_assert(SIOCSIFFLAGS == 0x8914, "SIOCSIFFLAGS");
_Static_assert(SIOCGIFADDR == 0x8915, "SIOCGIFADDR");
_Static_assert(SIOCSIFADDR == 0x8916, "SIOCSIFADDR");
_Static_assert(SIOCGIFNETMASK == 0x891b, "SIOCGIFNETMASK");
_Static_assert(SIOCSIFNETMASK == 0x891c, "SIOCSIFNETMASK");
_Static_assert(IFF_UP == 1, "IFF_UP");
_Static_assert(__NR_ioctl == 29, "ioctl");
_Static_assert(__NR_socket == 198, "socket");
_Static_assert(__NR_fcntl == 25, "fcntl");
_Static_assert(__NR_bind == 200, "bind");
_Static_assert(__NR_listen == 201, "listen");
_Static_assert(__NR_accept == 202, "accept");
_Static_assert(__NR_sendto == 206, "sendto");
_Static_assert(__NR_setsockopt == 208, "setsockopt");
_Static_assert(SOL_SOCKET == 1, "SOL_SOCKET");
_Static_assert(SO_REUSEADDR == 2, "SO_REUSEADDR");
_Static_assert(MSG_NOSIGNAL == 0x4000, "MSG_NOSIGNAL");
_Static_assert(F_GETFL == 3, "F_GETFL");
_Static_assert(F_SETFL == 4, "F_SETFL");
_Static_assert(O_NONBLOCK == 00004000, "O_NONBLOCK");
_Static_assert(HTTP_PORT == 8080, "HTTP port");
_Static_assert(IPV4_ADDR == 0x0149420au, "10.66.73.1");
_Static_assert(IPV4_MASK == 0x00ffffffu, "255.255.255.0");

struct k_sockaddr_in {
	unsigned short sin_family;
	unsigned short sin_port;
	unsigned int sin_addr;
	char zero[8];
};

_Static_assert(sizeof(struct k_sockaddr_in) == 16, "sockaddr_in");

/* aarch64 64-bit ifreq: 16-byte name + 24-byte union. */
struct k_ifreq {
	char ifr_name[IFNAMSIZ];
	union {
		short flags;
		struct k_sockaddr_in addr;
		char pad[24];
	} u;
};

_Static_assert(sizeof(struct k_ifreq) == 40, "aarch64 ifreq size");
_Static_assert(__builtin_offsetof(struct k_ifreq, u.addr.sin_addr) == 20,
	       "sin_addr offset");

struct timespec {
	long tv_sec;
	long tv_nsec;
};

struct net_set {
	char name[MAX_NETS][IFNAMSIZ];
	unsigned n;
};

static const char cmd_bl[] = "bootloader";
static const char kmsg_path[] = "/dev/kmsg";
static const char nl[] = "\n";

static const char m_init[] = "THYME-USB4:INIT";
static const char m_sysfs[] = "THYME-USB4:SYSFS_OK";
static const char m_udc_class[] = "THYME-USB4:UDC_CLASS_PRESENT";
static const char m_cfg[] = "THYME-USB4:CONFIGFS_OK";
static const char m_cfg_mnt_ok[] = "THYME-USB4:CONFIGFS_MOUNT_OK";
static const char m_udc_pfx[] = "THYME-USB4:UDC=";
static const char m_gad_dir[] = "THYME-USB4:GADGET_DIR_OK";
static const char m_strings[] = "THYME-USB4:STRINGS_OK";
static const char m_cfg_ok[] = "THYME-USB4:CONFIG_OK";
static const char m_gad[] = "THYME-USB4:GADGET_CREATED";
static const char m_ncm[] = "THYME-USB4:NCM_OK";
static const char m_fn[] = "THYME-USB4:FUNCTION=ncm";
static const char m_link[] = "THYME-USB4:LINK_OK";
static const char m_lnk[] = "THYME-USB4:FUNCTION_LINKED";
static const char m_bind_pfx[] = "THYME-USB4:BIND_ATTEMPT:";
static const char m_bound[] = "THYME-USB4:UDC_BOUND";
static const char m_netdev[] = "THYME-USB4:NETDEV=";
static const char m_device_ip[] = "THYME-USB4:DEVICE_IP_VERIFIED";
static const char m_carrier[] = "THYME-USB4:CARRIER=1";
static const char m_socket[] = "THYME-USB4:SOCKET_OK";
static const char m_reuseaddr[] = "THYME-USB4:SO_REUSEADDR_OK";
static const char m_bind_attempt[] = "THYME-USB4:BIND_ATTEMPT=10.66.73.1:8080";
static const char m_bind_ok[] = "THYME-USB4:BIND_OK";
static const char m_listen_ok[] = "THYME-USB4:LISTEN_OK:10.66.73.1:8080";
static const char m_http_ready[] = "THYME-USB4:HTTP_READY";
static const char m_accept[] = "THYME-USB4:ACCEPT_OK";
static const char m_request_rx[] = "THYME-USB4:REQUEST_RX";
static const char m_http_sent[] = "THYME-USB4:HTTP_200_SENT";
static const char m_no_request[] = "THYME-USB4:NO_REQUEST_BEFORE_TIMEOUT";
static const char m_hold[] = "THYME-USB4:HOLD";
static const char m_hold_done[] = "THYME-USB4:HOLD_DONE";
static const char m_reboot[] = "THYME-USB4:REBOOT_BOOTLOADER";
static const char m_fail_sysfs[] = "THYME-USB4:FAIL:SYSFS";
static const char m_fail_udc_class[] = "THYME-USB4:FAIL:UDC_CLASS_MISSING";
static const char m_fail_cfg[] = "THYME-USB4:FAIL:CONFIGFS";
static const char m_fail_udc[] = "THYME-USB4:FAIL:NO_UDC";
static const char m_udc_configured[] = "THYME-USB4:UDC_CONFIGURED";
static const char m_siocg[] = "THYME-USB4:SIOCGIFFLAGS=YES";
static const char m_siocs[] = "THYME-USB4:SIOCSIFFLAGS=YES";
static const char m_iff_attempt[] = "THYME-USB4:IFF_UP_ATTEMPT";
static const char m_iff_ok[] = "THYME-USB4:IFF_UP_OK";
static const char m_fail_netdev[] = "THYME-USB4:FAIL:NO_NETDEV";
static const char m_addr_ok[] = "THYME-USB4:ADDR_SET_OK";
static const char m_mask_ok[] = "THYME-USB4:NETMASK_SET_OK";
static const char m_ip_ok[] = "THYME-USB4:DEVICE_IPV4_VERIFIED";
static const char m_ip_yes[] = "THYME-USB4:DEVICE_STATIC_IPV4_VERIFIED=YES";
static const char m_fib_ok[] = "THYME-USB4:FIB_LOCAL_ADDR_PRESENT";
static const char m_fib_no[] = "THYME-USB4:FIB_LOCAL_ADDR_NOT_FOUND";
static const char m_rt_ok[] = "THYME-USB4:CONNECTED_ROUTE_PRESENT";
static const char m_rt_no[] = "THYME-USB4:CONNECTED_ROUTE_ABSENT";
static const char m_fail_mismatch[] = "THYME-USB4:FAIL:IPV4_MISMATCH";

static const char p_dev[] = "/dev";
static const char p_sys[] = "/sys";
static const char p_proc[] = "/proc";
static const char p_udc[] = "/sys/class/udc";
static const char p_net[] = "/sys/class/net";
static const char p_fib[] = "/proc/net/fib_trie";
static const char p_rt[] = "/proc/net/route";
static const char p_cfg[] = "/config";
static const char p_gadget[] = "/config/usb_gadget";
static const char p_cfg_std[] = "/sys/kernel/config";
static const char p_gadget_std[] = "/sys/kernel/config/usb_gadget";
static const char pref_udc[] = "a600000.dwc3";
static const char skip_bond[] = "bonding_masters";
static const char ip_addr_str[] = "10.66.73.1";
static const char ip_mask_str[] = "255.255.255.0";

static const char src_none[] = "none";
static const char src_sysfs[] = "sysfs";
static const char src_configfs[] = "configfs";
static const char src_proc[] = "proc";

static const char s_vid[] = "0x1d6b\n";
static const char s_pid[] = "0x0104\n";
static const char s_bcdusb[] = "0x0200\n";
static const char s_bcddev[] = "0x0100\n";
static const char s_mfg[] = "thyme-mainline\n";
static const char s_prod[] = "Stock Kernel USB Stage4 HTTP\n";
static const char s_ser[] = "THYME-USB4\n";
static const char s_cfg[] = "Stage4HTTP\n";
static const char s_pwr[] = "120\n";

#ifndef BUILD_MARKER
#define BUILD_MARKER "UNSET"
#endif

static const char http_body[] =
	"CONTROL=STOCK_KERNEL_USB_STAGE4\n"
	"DEVICE=thyme\n"
	"KERNEL=4.19.157-perf\n"
	"USB=NCM\n"
	"DEVICE_IP=10.66.73.1\n"
	"HTTP_READY=YES\n"
	"STAGE0_USB_ENUM=PASS\n"
	"STAGE1_LINK=PASS\n"
	"STAGE2_DEVICE_IP=PASS\n"
	"STAGE3_ICMP=PASS\n"
	"BUILD=" BUILD_MARKER "\n";

static const char http_prefix[] =
	"HTTP/1.1 200 OK\r\n"
	"Content-Type: text/plain\r\n"
	"Connection: close\r\n"
	"Content-Length: ";

static long sys6(long nr, long a0, long a1, long a2, long a3, long a4, long a5)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	register long x3 __asm__("x3") = a3;
	register long x4 __asm__("x4") = a4;
	register long x5 __asm__("x5") = a5;
	__asm__ volatile("svc #0"
			 : "+r"(x0)
			 : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
			 : "memory", "cc");
	return x0;
}

static long sys4(long nr, long a0, long a1, long a2, long a3)
{
	return sys6(nr, a0, a1, a2, a3, 0, 0);
}

static long sys1(long nr, long a0)
{
	return sys4(nr, a0, 0, 0, 0);
}

static unsigned slen(const char *s)
{
	unsigned n = 0;
	while (s[n])
		n++;
	return n;
}

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return *a == *b;
}

static int pcat(char *dst, unsigned cap, const char *a, const char *b)
{
	unsigned i = 0, j = 0;

	while (a[i]) {
		if (i + 1 >= cap)
			return -1;
		dst[i] = a[i];
		i++;
	}
	while (b[j]) {
		if (i + 1 >= cap)
			return -1;
		dst[i++] = b[j++];
	}
	dst[i] = 0;
	return 0;
}

static void cat_str(char *dst, unsigned *i, unsigned cap, const char *s)
{
	while (*s && *i + 1 < cap)
		dst[(*i)++] = *s++;
	dst[*i] = 0;
}

static void cat_long(char *dst, unsigned *i, unsigned cap, long v)
{
	char tmp[24];
	unsigned n = 0;
	unsigned long u;

	if (v < 0) {
		if (*i + 1 < cap)
			dst[(*i)++] = '-';
		u = (unsigned long)(-v);
	} else {
		u = (unsigned long)v;
	}
	do {
		tmp[n++] = (char)('0' + (u % 10));
		u /= 10;
	} while (u);
	while (n && *i + 1 < cap)
		dst[(*i)++] = tmp[--n];
	dst[*i] = 0;
}

static unsigned short htons16(unsigned short v)
{
	return (unsigned short)((v >> 8) | (v << 8));
}

static unsigned build_http_response(char *dst, unsigned cap)
{
	unsigned i = 0;

	cat_str(dst, &i, cap, http_prefix);
	cat_long(dst, &i, cap, (long)slen(http_body));
	cat_str(dst, &i, cap, "\r\n\r\n");
	cat_str(dst, &i, cap, http_body);
	return i;
}

static void cat_hex(char *dst, unsigned *i, unsigned cap, unsigned long v)
{
	char tmp[16];
	unsigned n = 0;

	cat_str(dst, i, cap, "0x");
	if (v == 0) {
		cat_str(dst, i, cap, "0");
		return;
	}
	while (v && n < sizeof(tmp)) {
		unsigned d = (unsigned)(v & 0xf);
		tmp[n++] = (char)(d < 10 ? '0' + d : 'a' + (d - 10));
		v >>= 4;
	}
	while (n && *i + 1 < cap)
		dst[(*i)++] = tmp[--n];
	dst[*i] = 0;
}

static void sleep_ts(long sec, long nsec)
{
	struct timespec rem;
	long r;

	rem.tv_sec = sec;
	rem.tv_nsec = nsec;
	for (;;) {
		r = sys4(SYS_nanosleep, (long)&rem, (long)&rem, 0, 0);
		if (r == 0)
			break;
		if (r != -EINTR)
			break;
	}
}

static void kmsg(const char *s)
{
	long fd, n;

	fd = sys4(SYS_openat, AT_FDCWD, (long)kmsg_path, O_WRONLY, 0);
	if (fd < 0)
		return;
	n = slen(s);
	sys4(SYS_write, fd, (long)s, n, 0);
	sys4(SYS_write, fd, (long)nl, 1, 0);
	sys1(SYS_close, fd);
}

static void kmsg2(const char *a, const char *b)
{
	char line[192];
	unsigned i = 0;

	cat_str(line, &i, sizeof(line), a);
	cat_str(line, &i, sizeof(line), b);
	kmsg(line);
}

static void kmsg_errno(const char *tag, long r)
{
	char line[160];
	unsigned i = 0;

	cat_str(line, &i, sizeof(line), tag);
	cat_str(line, &i, sizeof(line), ":ERRNO=");
	cat_long(line, &i, sizeof(line), r < 0 ? -r : r);
	kmsg(line);
}

static void kmsg_count(const char *tag, long n)
{
	char line[160];
	unsigned i = 0;

	cat_str(line, &i, sizeof(line), tag);
	cat_long(line, &i, sizeof(line), n);
	kmsg(line);
}

__attribute__((noreturn)) static void halt(void)
{
	for (;;)
		sleep_ts(3600, 0);
}

__attribute__((noreturn)) static void reboot_bl(void)
{
	sys1(SYS_sync, 0);
	sys4(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
	     LINUX_REBOOT_CMD_RESTART2, (long)cmd_bl);
	halt();
}

__attribute__((noreturn)) static void fail(const char *marker)
{
	kmsg(marker);
	sleep_ts(FAIL_SEC, 0);
	reboot_bl();
}

__attribute__((noreturn)) static void fail_errno(const char *tag, long r)
{
	char b[160];
	unsigned i = 0;

	cat_str(b, &i, sizeof(b), "THYME-USB4:FAIL:");
	cat_str(b, &i, sizeof(b), tag);
	cat_str(b, &i, sizeof(b), ":ERRNO=");
	cat_long(b, &i, sizeof(b), r < 0 ? -r : r);
	kmsg(b);
	sleep_ts(FAIL_SEC, 0);
	reboot_bl();
}

static long mkdir_one(const char *path)
{
	long r;

	r = sys4(SYS_mkdirat, AT_FDCWD, (long)path, 0755, 0);
	if (r == 0 || r == -EEXIST)
		return 0;
	return r;
}

static long mkdir_p(const char *path)
{
	char buf[160];
	unsigned i, n;
	long r;

	n = slen(path);
	if (n == 0 || n >= sizeof(buf))
		return -1;
	for (i = 0; i <= n; i++)
		buf[i] = path[i];
	for (i = 1; i <= n; i++) {
		if (buf[i] != '/' && buf[i] != 0)
			continue;
		buf[i] = 0;
		r = mkdir_one(buf);
		if (r)
			return r;
		buf[i] = path[i];
	}
	return 0;
}

static long write_str(const char *path, const char *s)
{
	long fd, n, w;

	fd = sys4(SYS_openat, AT_FDCWD, (long)path, O_WRONLY, 0);
	if (fd < 0)
		return fd;
	n = slen(s);
	w = sys4(SYS_write, fd, (long)s, n, 0);
	sys1(SYS_close, fd);
	if (w < 0)
		return w;
	if (w != n)
		return -5;
	return 0;
}

static long fstatat_path(const char *path, struct kstat *st)
{
	return sys4(SYS_newfstatat, AT_FDCWD, (long)path, (long)st, 0);
}

static int is_dir(const char *path)
{
	struct kstat st;
	long r;

	r = fstatat_path(path, &st);
	if (r < 0)
		return 0;
	return S_ISDIR(st.st_mode);
}

static void kmsg_stat(const char *tag, const char *path, int with_mode)
{
	struct kstat st;
	char b[192];
	unsigned i = 0;
	long r;

	r = fstatat_path(path, &st);
	cat_str(b, &i, sizeof(b), tag);
	if (r == 0) {
		cat_str(b, &i, sizeof(b), "0");
		if (with_mode) {
			cat_str(b, &i, sizeof(b), ":MODE=");
			cat_long(b, &i, sizeof(b), (long)st.st_mode);
		}
		cat_str(b, &i, sizeof(b), ":ERRNO=0");
	} else {
		cat_str(b, &i, sizeof(b), "-1");
		if (with_mode)
			cat_str(b, &i, sizeof(b), ":MODE=0");
		cat_str(b, &i, sizeof(b), ":ERRNO=");
		cat_long(b, &i, sizeof(b), -r);
	}
	kmsg(b);
}

static long mount_raw(const char *src, const char *dst, const char *type)
{
	return sys6(SYS_mount, (long)src, (long)dst, (long)type, 0, 0, 0);
}

static void kmsg_mount_configfs(long r)
{
	char b[160];
	unsigned i = 0;

	cat_str(b, &i, sizeof(b), "THYME-USB4:MOUNT_CONFIGFS:RET=");
	cat_long(b, &i, sizeof(b), r);
	cat_str(b, &i, sizeof(b), ":ERRNO=");
	cat_long(b, &i, sizeof(b), r < 0 ? -r : 0);
	kmsg(b);
	if (r == 0)
		kmsg(m_cfg_mnt_ok);
}

static int copy_name(char *dst, unsigned cap, const char *src)
{
	unsigned i = 0;

	while (src[i] && src[i] != '\n') {
		if (i + 1 >= cap)
			return -1;
		dst[i] = src[i];
		i++;
	}
	if (i == 0)
		return -1;
	dst[i] = 0;
	return 0;
}

static long scan_udc(char *out, unsigned cap)
{
	unsigned char rec[1024];
	char first[64];
	char pref[64];
	long fd, nread;
	unsigned pos, found = 0, have_pref = 0;

	first[0] = 0;
	pref[0] = 0;
	fd = sys4(SYS_openat, AT_FDCWD, (long)p_udc, O_RDONLY, 0);
	if (fd < 0)
		return fd;
	for (;;) {
		nread = sys4(SYS_getdents64, fd, (long)rec, sizeof(rec), 0);
		if (nread <= 0)
			break;
		pos = 0;
		while (pos + 19 < (unsigned)nread) {
			unsigned reclen = (unsigned)rec[pos + 16] |
					  ((unsigned)rec[pos + 17] << 8);
			const char *nm = (const char *)(rec + pos + 19);

			if (reclen < 20 || pos + reclen > (unsigned)nread)
				break;
			if (nm[0] != '.') {
				if (!found && copy_name(first, sizeof(first), nm) == 0)
					found = 1;
				if (streq(nm, pref_udc) &&
				    copy_name(pref, sizeof(pref), nm) == 0)
					have_pref = 1;
			}
			pos += reclen;
		}
	}
	sys1(SYS_close, fd);
	if (!found)
		return -ENOENT;
	if (have_pref)
		return copy_name(out, cap, pref);
	return copy_name(out, cap, first);
}

static long discover_udc(char *out, unsigned cap)
{
	int tries;
	long r = -ENOENT;

	for (tries = 0; tries < UDC_TRIES; tries++) {
		r = scan_udc(out, cap);
		if (r == 0)
			return 0;
		sleep_ts(0, 300000000L);
	}
	return r;
}

static void log_udc_sysfs(const char *udc, const char *leaf, const char *tag)
{
	char a[128], b[160], val[48], line[192];
	unsigned i = 0;
	long fd, n;

	if (pcat(a, sizeof(a), p_udc, "/"))
		return;
	if (pcat(b, sizeof(b), a, udc))
		return;
	if (pcat(a, sizeof(a), b, "/"))
		return;
	if (pcat(b, sizeof(b), a, leaf))
		return;
	i = 0;
	cat_str(line, &i, sizeof(line), tag);
	fd = sys4(SYS_openat, AT_FDCWD, (long)b, O_RDONLY, 0);
	if (fd < 0) {
		cat_str(line, &i, sizeof(line), "UNREAD:ERRNO=");
		cat_long(line, &i, sizeof(line), -fd);
		kmsg(line);
		return;
	}
	n = sys4(SYS_read, fd, (long)val, sizeof(val) - 1, 0);
	sys1(SYS_close, fd);
	if (n < 0) {
		cat_str(line, &i, sizeof(line), "UNREAD:ERRNO=");
		cat_long(line, &i, sizeof(line), -n);
		kmsg(line);
		return;
	}
	val[n] = 0;
	while (n && (val[n - 1] == '\n' || val[n - 1] == '\r' || val[n - 1] == ' '))
		val[--n] = 0;
	cat_str(line, &i, sizeof(line), val);
	kmsg(line);
}

static int read_trim(const char *path, char *out, unsigned cap)
{
	long fd, n;

	if (cap == 0)
		return -1;
	fd = sys4(SYS_openat, AT_FDCWD, (long)path, O_RDONLY, 0);
	if (fd < 0)
		return (int)fd;
	n = sys4(SYS_read, fd, (long)out, cap - 1, 0);
	sys1(SYS_close, fd);
	if (n < 0)
		return (int)n;
	while (n && (out[n - 1] == '\n' || out[n - 1] == '\r' || out[n - 1] == ' '))
		n--;
	out[n] = 0;
	return 0;
}

static int prep_dev(void)
{
	long fd;

	mkdir_one(p_dev);
	fd = sys4(SYS_openat, AT_FDCWD, (long)kmsg_path, O_WRONLY, 0);
	if (fd >= 0) {
		sys1(SYS_close, fd);
		return 0;
	}
	sys4(SYS_mknodat, AT_FDCWD, (long)kmsg_path, S_IFCHR | 0600,
	     (1 << 8) | 11);
	return 0;
}

static int setup_configfs(char *root, unsigned cap)
{
	long r;

	mkdir_one(p_cfg);
	r = mount_raw(src_none, p_cfg, src_configfs);
	kmsg_mount_configfs(r);
	if (r != 0 && r != -EBUSY) {
		r = mount_raw(src_configfs, p_cfg, src_configfs);
		kmsg_mount_configfs(r);
	}
	kmsg_stat("THYME-USB4:STAT_CONFIG=", p_cfg, 0);
	kmsg_stat("THYME-USB4:STAT_USB_GADGET=", p_gadget, 1);
	if (is_dir(p_gadget))
		return pcat(root, cap, p_cfg, "");

	mkdir_p(p_cfg_std);
	r = mount_raw(src_none, p_cfg_std, src_configfs);
	kmsg_mount_configfs(r);
	kmsg_stat("THYME-USB4:STAT_USB_GADGET=", p_gadget_std, 1);
	if (is_dir(p_gadget_std))
		return pcat(root, cap, p_cfg_std, "");
	return -1;
}

static long gwrite(const char *gdir, const char *leaf, const char *val)
{
	char p[192];

	if (pcat(p, sizeof(p), gdir, leaf))
		return -1;
	return write_str(p, val);
}

static void must_gwrite(const char *gdir, const char *leaf, const char *val,
			const char *tag)
{
	long r;

	r = gwrite(gdir, leaf, val);
	if (r)
		fail_errno(tag, r);
}

static int net_in_set(const struct net_set *set, const char *name)
{
	unsigned i;

	for (i = 0; i < set->n; i++) {
		if (streq(set->name[i], name))
			return 1;
	}
	return 0;
}

static void scan_nets(struct net_set *set)
{
	unsigned char rec[1024];
	long fd, nread;
	unsigned pos;

	set->n = 0;
	fd = sys4(SYS_openat, AT_FDCWD, (long)p_net, O_RDONLY, 0);
	if (fd < 0)
		return;
	for (;;) {
		nread = sys4(SYS_getdents64, fd, (long)rec, sizeof(rec), 0);
		if (nread <= 0)
			break;
		pos = 0;
		while (pos + 19 < (unsigned)nread) {
			unsigned reclen = (unsigned)rec[pos + 16] |
					  ((unsigned)rec[pos + 17] << 8);
			unsigned char dtype = rec[pos + 18];
			const char *nm = (const char *)(rec + pos + 19);

			if (reclen < 20 || pos + reclen > (unsigned)nread)
				break;
			if (nm[0] != '.' && dtype != DT_REG &&
			    !streq(nm, skip_bond) && set->n < MAX_NETS) {
				if (copy_name(set->name[set->n], IFNAMSIZ, nm) == 0)
					set->n++;
			}
			pos += reclen;
		}
	}
	sys1(SYS_close, fd);
}

static int first_new_net(const struct net_set *base, const struct net_set *cur,
			 char *out, unsigned cap)
{
	unsigned i;

	for (i = 0; i < cur->n; i++) {
		if (!net_in_set(base, cur->name[i]))
			return copy_name(out, cap, cur->name[i]);
	}
	return -1;
}

static void kmsg_nets(const char *tag, const struct net_set *set)
{
	char line[192];
	unsigned i = 0, n;

	cat_str(line, &i, sizeof(line), tag);
	if (set->n == 0) {
		cat_str(line, &i, sizeof(line), "NONE");
		kmsg(line);
		return;
	}
	for (n = 0; n < set->n; n++) {
		if (n)
			cat_str(line, &i, sizeof(line), ",");
		cat_str(line, &i, sizeof(line), set->name[n]);
	}
	kmsg(line);
}

static long ioctl_flags(long sock, const char *ifname)
{
	struct k_ifreq ifr;
	unsigned i;
	long r;

	if (sock < 0)
		return sock;
	for (i = 0; i < sizeof(ifr); i++)
		((char *)&ifr)[i] = 0;
	if (copy_name(ifr.ifr_name, IFNAMSIZ, ifname))
		return -1;
	r = sys4(SYS_ioctl, sock, SIOCGIFFLAGS, (long)&ifr, 0);
	if (r < 0)
		return r;
	return (long)(unsigned short)ifr.u.flags;
}

static int net_sysfs(const char *ifname, const char *leaf, char *out, unsigned cap)
{
	char a[128], b[160];

	if (pcat(a, sizeof(a), p_net, "/") || pcat(b, sizeof(b), a, ifname) ||
	    pcat(a, sizeof(a), b, "/") || pcat(b, sizeof(b), a, leaf))
		return -1;
	return read_trim(b, out, cap);
}

static void cat_carrier_field(char *dst, unsigned *i, unsigned cap,
			       const char *ifname)
{
	char a[128], b[160], val[32];
	long fd, n;

	if (pcat(a, sizeof(a), p_net, "/") || pcat(b, sizeof(b), a, ifname) ||
	    pcat(a, sizeof(a), b, "/") || pcat(b, sizeof(b), a, "carrier")) {
		cat_str(dst, i, cap, "CARRIER_ERRNO=1");
		return;
	}
	fd = sys4(SYS_openat, AT_FDCWD, (long)b, O_RDONLY, 0);
	if (fd < 0) {
		cat_str(dst, i, cap, "CARRIER_ERRNO=");
		cat_long(dst, i, cap, -fd);
		return;
	}
	n = sys4(SYS_read, fd, (long)val, sizeof(val) - 1, 0);
	sys1(SYS_close, fd);
	if (n < 0) {
		cat_str(dst, i, cap, "CARRIER_ERRNO=");
		cat_long(dst, i, cap, -n);
		return;
	}
	while (n && (val[n - 1] == '\n' || val[n - 1] == '\r' || val[n - 1] == ' '))
		n--;
	val[n] = 0;
	cat_str(dst, i, cap, "CARRIER=");
	cat_str(dst, i, cap, val[0] ? val : "NA");
}

static void log_ncm_attr(const char *gdir, const char *leaf, const char *tag)
{
	char p[192], val[64];
	int r;

	if (pcat(p, sizeof(p), gdir, "/functions/ncm.usb0/") ||
	    pcat(p, sizeof(p), p, leaf))
		return;
	r = read_trim(p, val, sizeof(val));
	if (r < 0)
		kmsg2(tag, "NOT_PRESENT");
	else if (val[0] == 0)
		kmsg2(tag, "NOT_PRESENT");
	else
		kmsg2(tag, val);
}

static void log_if_detail(const char *ifname, long sock)
{
	char val[64], line[192];
	unsigned i = 0;
	long fl;
	int r;

	fl = ioctl_flags(sock, ifname);
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:IF=");
	cat_str(line, &i, sizeof(line), ifname);
	cat_str(line, &i, sizeof(line), ":FLAGS=");
	if (fl < 0) {
		cat_str(line, &i, sizeof(line), "NOT_PRESENT");
		cat_str(line, &i, sizeof(line), ":ADMIN_UP=NA");
	} else {
		cat_hex(line, &i, sizeof(line), (unsigned long)fl);
		cat_str(line, &i, sizeof(line), ":ADMIN_UP=");
		cat_str(line, &i, sizeof(line), (fl & IFF_UP) ? "YES" : "NO");
	}
	cat_str(line, &i, sizeof(line), ":OPER=");
	r = net_sysfs(ifname, "operstate", val, sizeof(val));
	if (r < 0) {
		cat_str(line, &i, sizeof(line), "ERRNO=");
		cat_long(line, &i, sizeof(line), -r);
	} else {
		cat_str(line, &i, sizeof(line), val[0] ? val : "NA");
	}
	cat_str(line, &i, sizeof(line), ":");
	cat_carrier_field(line, &i, sizeof(line), ifname);
	cat_str(line, &i, sizeof(line), ":MTU=");
	r = net_sysfs(ifname, "mtu", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NOT_PRESENT" : val);
	kmsg(line);

	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:IF=");
	cat_str(line, &i, sizeof(line), ifname);
	cat_str(line, &i, sizeof(line), ":MAC=");
	r = net_sysfs(ifname, "address", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NOT_PRESENT" : val);
	cat_str(line, &i, sizeof(line), ":IDX=");
	r = net_sysfs(ifname, "ifindex", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NOT_PRESENT" : val);
	cat_str(line, &i, sizeof(line), ":ADDR_LEN=");
	r = net_sysfs(ifname, "addr_len", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NOT_PRESENT" : val);
	cat_str(line, &i, sizeof(line), ":TYPE=");
	r = net_sysfs(ifname, "type", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NOT_PRESENT" : val);
	kmsg(line);

	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:IF=");
	cat_str(line, &i, sizeof(line), ifname);
	cat_str(line, &i, sizeof(line), ":SYSFLAGS=");
	r = net_sysfs(ifname, "flags", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NOT_PRESENT" : val);
	cat_str(line, &i, sizeof(line), ":CARRIER_CHANGES=");
	r = net_sysfs(ifname, "carrier_changes", val, sizeof(val));
	cat_str(line, &i, sizeof(line), r < 0 || val[0] == 0 ? "NA" : val);
	kmsg(line);
}

static int maybe_find_netdev(const struct net_set *base, char *ifname,
			     unsigned cap, const char *tag)
{
	struct net_set cur;

	scan_nets(&cur);
	if (tag)
		kmsg_nets(tag, &cur);
	if (ifname[0])
		return 1;
	if (first_new_net(base, &cur, ifname, cap) == 0) {
		kmsg2("THYME-USB4:NETDEV_FOUND=", ifname);
		kmsg2(m_netdev, ifname);
		return 1;
	}
	return 0;
}

static int udc_state_is_configured(const char *udc, char *val, unsigned cap)
{
	char a[128], b[160];

	if (pcat(a, sizeof(a), p_udc, "/") || pcat(b, sizeof(b), a, udc) ||
	    pcat(a, sizeof(a), b, "/") || pcat(b, sizeof(b), a, "state"))
		return 0;
	if (read_trim(b, val, cap) < 0) {
		if (cap)
			val[0] = 0;
		return 0;
	}
	return streq(val, "configured");
}

static void wait_netdev(const struct net_set *base, char *ifname, unsigned cap)
{
	int tries;

	if (ifname[0])
		return;
	for (tries = 0; tries < NETDEV_WAIT_TRIES; tries++) {
		if (maybe_find_netdev(base, ifname, cap, 0))
			return;
		sleep_ts(0, NETDEV_WAIT_NS);
	}
	fail(m_fail_netdev);
}

static void set_iff_up(long sock, const char *ifname)
{
	struct k_ifreq ifr;
	unsigned i;
	long r;
	long old_flags;
	long after;
	char line[192];

	if (sock < 0)
		fail_errno("SOCK", sock);
	for (i = 0; i < sizeof(ifr); i++)
		((char *)&ifr)[i] = 0;
	if (copy_name(ifr.ifr_name, IFNAMSIZ, ifname))
		fail_errno("SIOCGIFFLAGS", -1);
	r = sys4(SYS_ioctl, sock, SIOCGIFFLAGS, (long)&ifr, 0);
	if (r < 0)
		fail_errno("SIOCGIFFLAGS", r);
	old_flags = (long)(unsigned short)ifr.u.flags;
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:FLAGS_BEFORE=");
	cat_hex(line, &i, sizeof(line), (unsigned long)old_flags);
	kmsg(line);
	kmsg(m_iff_attempt);
	ifr.u.flags = (short)(old_flags | IFF_UP);
	r = sys4(SYS_ioctl, sock, SIOCSIFFLAGS, (long)&ifr, 0);
	if (r < 0)
		fail_errno("IFF_UP", r);
	kmsg(m_iff_ok);
	for (i = 0; i < sizeof(ifr); i++)
		((char *)&ifr)[i] = 0;
	if (copy_name(ifr.ifr_name, IFNAMSIZ, ifname))
		fail_errno("SIOCGIFFLAGS", -1);
	r = sys4(SYS_ioctl, sock, SIOCGIFFLAGS, (long)&ifr, 0);
	if (r < 0)
		fail_errno("SIOCGIFFLAGS", r);
	after = (long)(unsigned short)ifr.u.flags;
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:FLAGS_AFTER=");
	cat_hex(line, &i, sizeof(line), (unsigned long)after);
	kmsg(line);
	kmsg2("THYME-USB4:ADMIN_UP_AFTER=", (after & IFF_UP) ? "YES" : "NO");
}

static void cat_ipv4(char *dst, unsigned *i, unsigned cap, unsigned int addr)
{
	cat_long(dst, i, cap, (long)(addr & 0xffu));
	cat_str(dst, i, cap, ".");
	cat_long(dst, i, cap, (long)((addr >> 8) & 0xffu));
	cat_str(dst, i, cap, ".");
	cat_long(dst, i, cap, (long)((addr >> 16) & 0xffu));
	cat_str(dst, i, cap, ".");
	cat_long(dst, i, cap, (long)((addr >> 24) & 0xffu));
}

static void ifr_clear(struct k_ifreq *ifr)
{
	unsigned i;

	for (i = 0; i < sizeof(*ifr); i++)
		((char *)ifr)[i] = 0;
}

static int ifr_set_name(struct k_ifreq *ifr, const char *ifname)
{
	ifr_clear(ifr);
	return copy_name(ifr->ifr_name, IFNAMSIZ, ifname);
}

static int get_ipv4(long sock, const char *ifname, unsigned int *addr)
{
	struct k_ifreq ifr;
	long r;

	if (sock < 0 || ifr_set_name(&ifr, ifname))
		return -1;
	r = sys4(SYS_ioctl, sock, SIOCGIFADDR, (long)&ifr, 0);
	if (r < 0)
		return (int)r;
	*addr = ifr.u.addr.sin_addr;
	return 0;
}

static int find_str(const char *hay, const char *needle)
{
	unsigned i, j;

	if (!needle[0])
		return 1;
	for (i = 0; hay[i]; i++) {
		j = 0;
		while (needle[j] && hay[i + j] == needle[j])
			j++;
		if (!needle[j])
			return 1;
	}
	return 0;
}

static void scan_file_needle(const char *path, const char *needle, const char *ok,
			     const char *bad)
{
	char buf[544];
	unsigned keep, have = 0, i;
	long fd, n;
	int found = 0;

	keep = slen(needle);
	if (keep < 8)
		keep = 8;
	if (keep > 32)
		keep = 32;
	fd = sys4(SYS_openat, AT_FDCWD, (long)path, O_RDONLY, 0);
	if (fd < 0) {
		kmsg(bad);
		return;
	}
	for (;;) {
		n = sys4(SYS_read, fd, (long)(buf + have),
			 (long)(sizeof(buf) - 1 - have), 0);
		if (n <= 0)
			break;
		have += (unsigned)n;
		buf[have] = 0;
		if (find_str(buf, needle)) {
			found = 1;
			break;
		}
		if (have > keep) {
			for (i = 0; i < keep; i++)
				buf[i] = buf[have - keep + i];
			have = keep;
		}
	}
	sys1(SYS_close, fd);
	kmsg(found ? ok : bad);
}

static void setup_proc(void)
{
	long r;
	char b[96];
	unsigned i = 0;

	mkdir_one(p_proc);
	r = mount_raw(src_proc, p_proc, src_proc);
	if (r != 0 && r != -EBUSY) {
		cat_str(b, &i, sizeof(b), "THYME-USB4:PROC_MOUNT:ERRNO=");
		cat_long(b, &i, sizeof(b), -r);
		kmsg(b);
		return;
	}
	kmsg("THYME-USB4:PROC_OK");
}

static void set_ipv4(long sock, const char *ifname)
{
	struct k_ifreq ifr;
	long r;
	unsigned i;
	unsigned int got_addr = 0, got_mask = 0;
	char line[192];

	if (sock < 0)
		fail_errno("SOCK", sock);
	kmsg2("THYME-USB4:EXPECT_ADDR=", ip_addr_str);
	kmsg2("THYME-USB4:EXPECT_NETMASK=", ip_mask_str);

	if (ifr_set_name(&ifr, ifname))
		fail_errno("SET_ADDR", -1);
	ifr.u.addr.sin_family = AF_INET;
	ifr.u.addr.sin_port = 0;
	ifr.u.addr.sin_addr = IPV4_ADDR;
	r = sys4(SYS_ioctl, sock, SIOCSIFADDR, (long)&ifr, 0);
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:SET_ADDR:RET=");
	cat_long(line, &i, sizeof(line), r);
	cat_str(line, &i, sizeof(line), ":ERRNO=");
	cat_long(line, &i, sizeof(line), r < 0 ? -r : 0);
	kmsg(line);
	if (r < 0)
		fail_errno("SET_ADDR", r);
	kmsg(m_addr_ok);

	if (ifr_set_name(&ifr, ifname))
		fail_errno("SET_NETMASK", -1);
	ifr.u.addr.sin_family = AF_INET;
	ifr.u.addr.sin_port = 0;
	ifr.u.addr.sin_addr = IPV4_MASK;
	r = sys4(SYS_ioctl, sock, SIOCSIFNETMASK, (long)&ifr, 0);
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:SET_NETMASK:RET=");
	cat_long(line, &i, sizeof(line), r);
	cat_str(line, &i, sizeof(line), ":ERRNO=");
	cat_long(line, &i, sizeof(line), r < 0 ? -r : 0);
	kmsg(line);
	if (r < 0)
		fail_errno("SET_NETMASK", r);
	kmsg(m_mask_ok);

	if (ifr_set_name(&ifr, ifname))
		fail_errno("GET_ADDR", -1);
	r = sys4(SYS_ioctl, sock, SIOCGIFADDR, (long)&ifr, 0);
	if (r < 0)
		fail_errno("GET_ADDR", r);
	got_addr = ifr.u.addr.sin_addr;
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:GET_ADDR=");
	cat_ipv4(line, &i, sizeof(line), got_addr);
	kmsg(line);

	if (ifr_set_name(&ifr, ifname))
		fail_errno("GET_NETMASK", -1);
	r = sys4(SYS_ioctl, sock, SIOCGIFNETMASK, (long)&ifr, 0);
	if (r < 0)
		fail_errno("GET_NETMASK", r);
	got_mask = ifr.u.addr.sin_addr;
	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:GET_NETMASK=");
	cat_ipv4(line, &i, sizeof(line), got_mask);
	kmsg(line);

	if (got_addr != IPV4_ADDR || got_mask != IPV4_MASK)
		fail(m_fail_mismatch);
	kmsg(m_ip_ok);
	kmsg(m_device_ip);
	kmsg(m_ip_yes);
	scan_file_needle(p_fib, ip_addr_str, m_fib_ok, m_fib_no);
	scan_file_needle(p_rt, ifname, m_rt_ok, m_rt_no);
}

static void sample_t(long t_ms, const char *udc, char *ifname, unsigned cap,
		     const struct net_set *base, long sock, int *saw_cfg)
{
	char udc_state[48], oper[48], line[192];
	unsigned i = 0;
	unsigned int addr = 0;
	long fl;
	int r;
	int cfg;

	cfg = udc_state_is_configured(udc, udc_state, sizeof(udc_state));
	if (cfg && !*saw_cfg) {
		kmsg(m_udc_configured);
		*saw_cfg = 1;
	}
	if (!ifname[0])
		maybe_find_netdev(base, ifname, cap, 0);

	i = 0;
	cat_str(line, &i, sizeof(line), "THYME-USB4:T=");
	cat_long(line, &i, sizeof(line), t_ms);
	cat_str(line, &i, sizeof(line), ":FLAGS=");
	if (!ifname[0]) {
		cat_str(line, &i, sizeof(line), "NA:ADMIN=NA:OPER=NA:CARRIER=NA:UDC=");
		cat_str(line, &i, sizeof(line), udc_state[0] ? udc_state : "NA");
		kmsg(line);
		return;
	}
	fl = ioctl_flags(sock, ifname);
	if (fl < 0)
		cat_str(line, &i, sizeof(line), "NA");
	else
		cat_hex(line, &i, sizeof(line), (unsigned long)fl);
	cat_str(line, &i, sizeof(line), ":ADMIN=");
	if (fl < 0)
		cat_str(line, &i, sizeof(line), "NA");
	else
		cat_str(line, &i, sizeof(line), (fl & IFF_UP) ? "1" : "0");
	cat_str(line, &i, sizeof(line), ":OPER=");
	r = net_sysfs(ifname, "operstate", oper, sizeof(oper));
	if (r < 0) {
		cat_str(line, &i, sizeof(line), "ERRNO=");
		cat_long(line, &i, sizeof(line), -r);
	} else {
		cat_str(line, &i, sizeof(line), oper[0] ? oper : "NA");
	}
	cat_str(line, &i, sizeof(line), ":");
	cat_carrier_field(line, &i, sizeof(line), ifname);
	cat_str(line, &i, sizeof(line), ":UDC=");
	cat_str(line, &i, sizeof(line), udc_state[0] ? udc_state : "NA");
	cat_str(line, &i, sizeof(line), ":ADDR=");
	if (get_ipv4(sock, ifname, &addr))
		cat_str(line, &i, sizeof(line), "NA");
	else
		cat_ipv4(line, &i, sizeof(line), addr);
	kmsg(line);
}

static int carrier_is_up(const char *ifname)
{
	char val[16];

	return net_sysfs(ifname, "carrier", val, sizeof(val)) == 0 &&
		streq(val, "1");
}

static void wait_link_ready(const char *udc, char *ifname, unsigned cap,
			    const struct net_set *base, long sock)
{
	char state[48];
	int saw_cfg = 0;
	int tries;

	for (tries = 0; tries < LINK_READY_TRIES; tries++) {
		int cfg = udc_state_is_configured(udc, state, sizeof(state));
		long flags = ioctl_flags(sock, ifname);

		if (cfg && !saw_cfg) {
			kmsg(m_udc_configured);
			saw_cfg = 1;
		}
		if (cfg && flags >= 0 && (flags & IFF_UP) && carrier_is_up(ifname)) {
			kmsg(m_carrier);
			sample_t(0, udc, ifname, cap, base, sock, &saw_cfg);
			return;
		}
		sleep_ts(0, LINK_READY_NS);
	}
	fail("THYME-USB4:FAIL:USB_LINK_NOT_READY");
}

static long set_nonblock(long fd)
{
	long flags;
	long r;

	flags = sys4(SYS_fcntl, fd, F_GETFL, 0, 0);
	if (flags < 0)
		return flags;
	r = sys4(SYS_fcntl, fd, F_SETFL, flags | O_NONBLOCK, 0);
	return r;
}

static long read_request(long fd, char *buf, unsigned cap)
{
	unsigned tries;
	long n;

	if (cap == 0)
		return -1;
	for (tries = 0; tries < REQUEST_TRIES; tries++) {
		n = sys4(SYS_read, fd, (long)buf, (long)cap, 0);
		if (n >= 0)
			return n;
		if (n != -EAGAIN && n != -EINTR)
			return n;
		sleep_ts(0, REQUEST_WAIT_NS);
	}
	return -EAGAIN;
}

static long send_all(long fd, const char *buf, unsigned len)
{
	unsigned sent = 0;
	unsigned tries = 0;
	long n;

	while (sent < len) {
		n = sys6(SYS_sendto, fd, (long)(buf + sent),
			  (long)(len - sent), MSG_NOSIGNAL, 0, 0);
		if (n > 0) {
			sent += (unsigned)n;
			tries = 0;
			continue;
		}
		if (n == -EINTR || n == -EAGAIN) {
			if (++tries >= SEND_TRIES)
				return n;
			sleep_ts(0, REQUEST_WAIT_NS);
			continue;
		}
		return n == 0 ? -5 : n;
	}
	return (long)sent;
}

static long setup_http_listener(void)
{
	struct k_sockaddr_in addr;
	int reuse = 1;
	unsigned i;
	long fd;
	long r;

	fd = sys4(SYS_socket, AF_INET, SOCK_STREAM, 0, 0);
	if (fd < 0)
		fail_errno("SOCKET_HTTP", fd);
	kmsg(m_socket);

	r = sys6(SYS_setsockopt, fd, SOL_SOCKET, SO_REUSEADDR,
		 (long)&reuse, sizeof(reuse), 0);
	if (r < 0)
		fail_errno("SO_REUSEADDR", r);
	kmsg(m_reuseaddr);

	for (i = 0; i < sizeof(addr); i++)
		((char *)&addr)[i] = 0;
	addr.sin_family = AF_INET;
	addr.sin_port = htons16(HTTP_PORT);
	addr.sin_addr = IPV4_ADDR;
	kmsg(m_bind_attempt);
	r = sys4(SYS_bind, fd, (long)&addr, sizeof(addr), 0);
	if (r < 0)
		fail_errno("BIND_HTTP", r);
	kmsg(m_bind_ok);

	r = sys4(SYS_listen, fd, LISTEN_BACKLOG, 0, 0);
	if (r < 0)
		fail_errno("LISTEN", r);
	kmsg(m_listen_ok);

	r = set_nonblock(fd);
	if (r < 0)
		fail_errno("HTTP_NONBLOCK", r);
	return fd;
}

static void handle_http_connection(long fd, const char *response,
				   unsigned response_len, int *saw_request)
{
	char request[REQUEST_MAX];
	long n;
	long sent;

	{
		long r = set_nonblock(fd);

		if (r < 0) {
			kmsg_errno("THYME-USB4:FAIL:HTTP_CONN_NONBLOCK", r);
			sys1(SYS_close, fd);
			return;
		}
	}
	n = read_request(fd, request, sizeof(request));
	if (n <= 0) {
		if (n < 0)
			kmsg_errno("THYME-USB4:REQUEST_WAIT", n);
		sys1(SYS_close, fd);
		return;
	}
	*saw_request = 1;
	kmsg(m_request_rx);
	kmsg_count("THYME-USB4:REQUEST_RX:BYTES=", n);

	sent = send_all(fd, response, response_len);
	if (sent < 0) {
		kmsg_errno("THYME-USB4:FAIL:SEND_HTTP", sent);
		sys1(SYS_close, fd);
		return;
	}
	kmsg(m_http_sent);
	kmsg_count("THYME-USB4:HTTP_200_SENT:BYTES=", sent);
	sys1(SYS_close, fd);
}

static void serve_http(long listener)
{
	char response[RESPONSE_MAX];
	unsigned response_len;
	unsigned connections = 0;
	unsigned tick;
	int saw_request = 0;

	response_len = build_http_response(response, sizeof(response));
	if (response_len == 0 || response_len >= sizeof(response))
		fail("THYME-USB4:FAIL:RESPONSE_TOO_LARGE");
	kmsg(m_http_ready);
	kmsg("THYME-USB4:HOLD_SEC=60");
	kmsg(m_hold);
	for (tick = 0; tick < HOLD_SEC * 10u; tick++) {
		if (connections < MAX_CONNECTIONS) {
			long fd = sys4(SYS_accept, listener, 0, 0, 0);

			if (fd >= 0) {
				connections++;
				kmsg(m_accept);
				handle_http_connection(fd, response, response_len,
						       &saw_request);
			} else if (fd != -EAGAIN && fd != -EINTR) {
				fail_errno("ACCEPT", fd);
			}
		}
		sleep_ts(0, ACCEPT_POLL_NS);
	}
	if (!saw_request)
		kmsg(m_no_request);
}

static void build_gadget(const char *root, const struct net_set *base,
			 char *ifname, unsigned ifcap)
{
	char gdir[128];
	char p[192];
	char tgt[192];
	char lnk[192];
	long r;

	if (pcat(gdir, sizeof(gdir), root, "/usb_gadget/g1"))
		fail_errno("GADGET_PATH", -1);
	r = mkdir_p(gdir);
	if (r)
		fail_errno("MKDIR_GADGET", r);
	kmsg(m_gad_dir);

	must_gwrite(gdir, "/idVendor", s_vid, "WRITE_IDVENDOR");
	must_gwrite(gdir, "/idProduct", s_pid, "WRITE_IDPRODUCT");
	must_gwrite(gdir, "/bcdUSB", s_bcdusb, "WRITE_BCDUSB");
	must_gwrite(gdir, "/bcdDevice", s_bcddev, "WRITE_BCDDEVICE");

	if (pcat(p, sizeof(p), gdir, "/strings/0x409"))
		fail_errno("STRINGS_PATH", -1);
	r = mkdir_p(p);
	if (r)
		fail_errno("MKDIR_STRINGS", r);
	must_gwrite(gdir, "/strings/0x409/manufacturer", s_mfg, "WRITE_MFG");
	must_gwrite(gdir, "/strings/0x409/product", s_prod, "WRITE_PRODUCT");
	must_gwrite(gdir, "/strings/0x409/serialnumber", s_ser, "WRITE_SERIAL");
	kmsg(m_strings);

	if (pcat(p, sizeof(p), gdir, "/configs/c.1/strings/0x409"))
		fail_errno("CONFIG_PATH", -1);
	r = mkdir_p(p);
	if (r)
		fail_errno("MKDIR_CONFIG", r);
	must_gwrite(gdir, "/configs/c.1/strings/0x409/configuration", s_cfg,
		    "WRITE_CFGSTR");
	must_gwrite(gdir, "/configs/c.1/MaxPower", s_pwr, "WRITE_MAXPOWER");
	kmsg(m_cfg_ok);
	kmsg(m_gad);

	if (pcat(p, sizeof(p), gdir, "/functions/ncm.usb0"))
		fail_errno("NCM_PATH", -1);
	r = mkdir_p(p);
	if (r)
		fail_errno("NCM_CREATE", r);
	kmsg(m_ncm);
	kmsg(m_fn);
	log_ncm_attr(gdir, "dev_addr", "THYME-USB4:DEV_ADDR=");
	log_ncm_attr(gdir, "host_addr", "THYME-USB4:HOST_ADDR=");
	log_ncm_attr(gdir, "ifname", "THYME-USB4:NCM_IFNAME=");
	maybe_find_netdev(base, ifname, ifcap, "THYME-USB4:NETDEV_AFTER_FUNCTION=");

	if (pcat(tgt, sizeof(tgt), gdir, "/functions/ncm.usb0"))
		fail_errno("SYMLINK_TGT", -1);
	if (pcat(lnk, sizeof(lnk), gdir, "/configs/c.1/ncm.usb0"))
		fail_errno("SYMLINK_LNK", -1);
	r = sys4(SYS_symlinkat, (long)tgt, AT_FDCWD, (long)lnk, 0);
	if (r < 0)
		fail_errno("SYMLINK", r);
	kmsg(m_link);
	kmsg(m_lnk);
	log_ncm_attr(gdir, "dev_addr", "THYME-USB4:DEV_ADDR=");
	log_ncm_attr(gdir, "host_addr", "THYME-USB4:HOST_ADDR=");
	log_ncm_attr(gdir, "ifname", "THYME-USB4:NCM_IFNAME=");
	maybe_find_netdev(base, ifname, ifcap, "THYME-USB4:NETDEV_AFTER_LINK=");
}

static long bind_udc(const char *root, const char *udc)
{
	char p[192];
	char body[80];

	if (pcat(p, sizeof(p), root, "/usb_gadget/g1/UDC"))
		return -1;
	if (pcat(body, sizeof(body), udc, "\n"))
		return -1;
	return write_str(p, body);
}

__attribute__((used, noreturn, section(".text")))
int main(void)
{
	char cfgroot[64];
	char udc[64];
	char ifname[IFNAMSIZ];
	struct net_set base;
	long r;
	long sock;
	long http_sock;

	ifname[0] = 0;
	prep_dev();
	kmsg(m_init);
	kmsg(m_siocg);
	kmsg(m_siocs);

	if (mkdir_p(p_sys))
		fail(m_fail_sysfs);
	r = mount_raw(src_sysfs, p_sys, src_sysfs);
	if (r != 0 && r != -EBUSY)
		fail(m_fail_sysfs);
	kmsg(m_sysfs);
	setup_proc();
	kmsg_stat("THYME-USB4:STAT_UDC_CLASS=", p_udc, 1);
	if (!is_dir(p_udc))
		fail(m_fail_udc_class);
	kmsg(m_udc_class);

	if (setup_configfs(cfgroot, sizeof(cfgroot)))
		fail(m_fail_cfg);
	kmsg(m_cfg);

	r = discover_udc(udc, sizeof(udc));
	if (r)
		fail(m_fail_udc);
	kmsg2(m_udc_pfx, udc);

	log_udc_sysfs(udc, "state", "THYME-USB4:PREBIND_STATE=");
	log_udc_sysfs(udc, "maximum_speed", "THYME-USB4:MAX_SPEED=");
	log_udc_sysfs(udc, "current_speed", "THYME-USB4:CURRENT_SPEED=");

	scan_nets(&base);
	kmsg_nets("THYME-USB4:PREBIND_NETS=", &base);

	sock = sys4(SYS_socket, AF_INET, SOCK_DGRAM, 0, 0);
	if (sock < 0)
		fail_errno("SOCK", sock);
	kmsg("THYME-USB4:SOCK_OK");

	build_gadget(cfgroot, &base, ifname, sizeof(ifname));

	kmsg2(m_bind_pfx, udc);
	r = bind_udc(cfgroot, udc);
	if (r)
		fail_errno("BIND", r);
	kmsg(m_bound);
	log_udc_sysfs(udc, "state", "THYME-USB4:POSTBIND_STATE=");
	maybe_find_netdev(&base, ifname, sizeof(ifname),
			  "THYME-USB4:NETDEV_AFTER_BIND=");
	wait_netdev(&base, ifname, sizeof(ifname));
	log_if_detail(ifname, sock);
	set_iff_up(sock, ifname);
	set_ipv4(sock, ifname);
	wait_link_ready(udc, ifname, sizeof(ifname), &base, sock);
	kmsg2(m_netdev, ifname);

	http_sock = setup_http_listener();
	serve_http(http_sock);
	if (ifname[0]) {
		char gdir[128];

		log_if_detail(ifname, sock);
		if (!pcat(gdir, sizeof(gdir), cfgroot, "/usb_gadget/g1")) {
			log_ncm_attr(gdir, "dev_addr", "THYME-USB4:DEV_ADDR=");
			log_ncm_attr(gdir, "host_addr", "THYME-USB4:HOST_ADDR=");
			log_ncm_attr(gdir, "ifname", "THYME-USB4:NCM_IFNAME=");
		}
	} else {
		kmsg("THYME-USB4:NETDEV_FOUND=NONE");
	}
	if (http_sock >= 0)
		sys1(SYS_close, http_sock);
	if (sock >= 0)
		sys1(SYS_close, sock);
	kmsg(m_hold_done);
	kmsg(m_reboot);
	reboot_bl();
}
