/*
 * PID 1: STOCK_KERNEL_USB_STAGE1B_DEVICE_NETDEV_UP
 * USB0 path reused: newfstatat + S_ISDIR, configfs NCM, UDC bind.
 * Added: SIOCSIFFLAGS old_flags | IFF_UP after netdev appears.
 * Freestanding aarch64. No IP, no route.
 *
 * TEST ONLY identity 1d6b:0104 (Linux Foundation gadget).
 * NOT PRODUCTION USB IDENTITY.
 *
 * GitHub Actions only.
 */
#ifndef __aarch64__
#error "usb-stage1b-device-up-init is aarch64 only"
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

#ifndef AT_FDCWD
#define AT_FDCWD (-100)
#endif

#define EINTR 4
#define ENOENT 2
#define EBUSY 16
#define EEXIST 17

#define S_IFMT 00170000
#define S_IFDIR 0040000
#define S_IFCHR 0020000
#define S_ISDIR(m) (((m) & S_IFMT) == S_IFDIR)

#define HOLD_SEC 30
#define FAIL_SEC 5
#define UDC_TRIES 10
#define NETDEV_WAIT_TRIES 40
#define NETDEV_WAIT_NS 50000000L

#define AF_INET 2
#define SOCK_DGRAM 2
#define SIOCGIFFLAGS 0x8913
#define SIOCSIFFLAGS 0x8914
#define IFF_UP 1
#define IFNAMSIZ 16
#define MAX_NETS 32
#define DT_REG 8

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
_Static_assert(IFF_UP == 1, "IFF_UP");
_Static_assert(__NR_ioctl == 29, "ioctl");
_Static_assert(__NR_socket == 198, "socket");

/* aarch64 64-bit ifreq: 16-byte name + 24-byte union. */
struct k_ifreq {
	char ifr_name[IFNAMSIZ];
	union {
		short flags;
		char pad[24];
	} u;
};

_Static_assert(sizeof(struct k_ifreq) == 40, "aarch64 ifreq size");

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

static const char m_init[] = "THYME-USB1B:INIT";
static const char m_sysfs[] = "THYME-USB1B:SYSFS_OK";
static const char m_udc_class[] = "THYME-USB1B:UDC_CLASS_PRESENT";
static const char m_cfg[] = "THYME-USB1B:CONFIGFS_OK";
static const char m_cfg_mnt_ok[] = "THYME-USB1B:CONFIGFS_MOUNT_OK";
static const char m_udc_pfx[] = "THYME-USB1B:UDC=";
static const char m_gad_dir[] = "THYME-USB1B:GADGET_DIR_OK";
static const char m_strings[] = "THYME-USB1B:STRINGS_OK";
static const char m_cfg_ok[] = "THYME-USB1B:CONFIG_OK";
static const char m_gad[] = "THYME-USB1B:GADGET_CREATED";
static const char m_ncm[] = "THYME-USB1B:NCM_OK";
static const char m_fn[] = "THYME-USB1B:FUNCTION=ncm";
static const char m_link[] = "THYME-USB1B:LINK_OK";
static const char m_lnk[] = "THYME-USB1B:FUNCTION_LINKED";
static const char m_bind_pfx[] = "THYME-USB1B:BIND_ATTEMPT:";
static const char m_bound[] = "THYME-USB1B:UDC_BOUND";
static const char m_hold[] = "THYME-USB1B:HOLD";
static const char m_hold_done[] = "THYME-USB1B:HOLD_DONE";
static const char m_reboot[] = "THYME-USB1B:REBOOT_BOOTLOADER";
static const char m_fail_sysfs[] = "THYME-USB1B:FAIL:SYSFS";
static const char m_fail_udc_class[] = "THYME-USB1B:FAIL:UDC_CLASS_MISSING";
static const char m_fail_cfg[] = "THYME-USB1B:FAIL:CONFIGFS";
static const char m_fail_udc[] = "THYME-USB1B:FAIL:NO_UDC";
static const char m_udc_configured[] = "THYME-USB1B:UDC_CONFIGURED";
static const char m_siocg[] = "THYME-USB1B:SIOCGIFFLAGS=YES";
static const char m_siocs[] = "THYME-USB1B:SIOCSIFFLAGS=YES";
static const char m_iff_attempt[] = "THYME-USB1B:IFF_UP_ATTEMPT";
static const char m_iff_ok[] = "THYME-USB1B:IFF_UP_OK";
static const char m_fail_netdev[] = "THYME-USB1B:FAIL:NO_NETDEV";

static const char p_dev[] = "/dev";
static const char p_sys[] = "/sys";
static const char p_udc[] = "/sys/class/udc";
static const char p_net[] = "/sys/class/net";
static const char p_cfg[] = "/config";
static const char p_gadget[] = "/config/usb_gadget";
static const char p_cfg_std[] = "/sys/kernel/config";
static const char p_gadget_std[] = "/sys/kernel/config/usb_gadget";
static const char pref_udc[] = "a600000.dwc3";
static const char skip_bond[] = "bonding_masters";

static const char src_none[] = "none";
static const char src_sysfs[] = "sysfs";
static const char src_configfs[] = "configfs";

static const char s_vid[] = "0x1d6b\n";
static const char s_pid[] = "0x0104\n";
static const char s_bcdusb[] = "0x0200\n";
static const char s_bcddev[] = "0x0100\n";
static const char s_mfg[] = "thyme-mainline\n";
static const char s_prod[] = "Stock Kernel USB Stage1B Device Up\n";
static const char s_ser[] = "THYME-USB1B\n";
static const char s_cfg[] = "Stage1BDevUp\n";
static const char s_pwr[] = "120\n";

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

	cat_str(b, &i, sizeof(b), "THYME-USB1B:FAIL:");
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

	cat_str(b, &i, sizeof(b), "THYME-USB1B:MOUNT_CONFIGFS:RET=");
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
	kmsg_stat("THYME-USB1B:STAT_CONFIG=", p_cfg, 0);
	kmsg_stat("THYME-USB1B:STAT_USB_GADGET=", p_gadget, 1);
	if (is_dir(p_gadget))
		return pcat(root, cap, p_cfg, "");

	mkdir_p(p_cfg_std);
	r = mount_raw(src_none, p_cfg_std, src_configfs);
	kmsg_mount_configfs(r);
	kmsg_stat("THYME-USB1B:STAT_USB_GADGET=", p_gadget_std, 1);
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
	cat_str(line, &i, sizeof(line), "THYME-USB1B:IF=");
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
	cat_str(line, &i, sizeof(line), "THYME-USB1B:IF=");
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
	cat_str(line, &i, sizeof(line), "THYME-USB1B:IF=");
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
		kmsg2("THYME-USB1B:NETDEV_FOUND=", ifname);
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
	cat_str(line, &i, sizeof(line), "THYME-USB1B:FLAGS_BEFORE=");
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
	cat_str(line, &i, sizeof(line), "THYME-USB1B:FLAGS_AFTER=");
	cat_hex(line, &i, sizeof(line), (unsigned long)after);
	kmsg(line);
	kmsg2("THYME-USB1B:ADMIN_UP_AFTER=", (after & IFF_UP) ? "YES" : "NO");
}

static void sample_t(long t_ms, const char *udc, char *ifname, unsigned cap,
		     const struct net_set *base, long sock, int *saw_cfg)
{
	char udc_state[48], oper[48], line[192];
	unsigned i = 0;
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
	cat_str(line, &i, sizeof(line), "THYME-USB1B:T=");
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
	kmsg(line);
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
	log_ncm_attr(gdir, "dev_addr", "THYME-USB1B:DEV_ADDR=");
	log_ncm_attr(gdir, "host_addr", "THYME-USB1B:HOST_ADDR=");
	log_ncm_attr(gdir, "ifname", "THYME-USB1B:NCM_IFNAME=");
	maybe_find_netdev(base, ifname, ifcap, "THYME-USB1B:NETDEV_AFTER_FUNCTION=");

	if (pcat(tgt, sizeof(tgt), gdir, "/functions/ncm.usb0"))
		fail_errno("SYMLINK_TGT", -1);
	if (pcat(lnk, sizeof(lnk), gdir, "/configs/c.1/ncm.usb0"))
		fail_errno("SYMLINK_LNK", -1);
	r = sys4(SYS_symlinkat, (long)tgt, AT_FDCWD, (long)lnk, 0);
	if (r < 0)
		fail_errno("SYMLINK", r);
	kmsg(m_link);
	kmsg(m_lnk);
	log_ncm_attr(gdir, "dev_addr", "THYME-USB1B:DEV_ADDR=");
	log_ncm_attr(gdir, "host_addr", "THYME-USB1B:HOST_ADDR=");
	log_ncm_attr(gdir, "ifname", "THYME-USB1B:NCM_IFNAME=");
	maybe_find_netdev(base, ifname, ifcap, "THYME-USB1B:NETDEV_AFTER_LINK=");
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

static void hold_observe(const char *udc, char *ifname, unsigned cap,
			 const struct net_set *base, long sock)
{
	int saw_cfg = 0;
	static const long gap_ms[] = { 100, 400, 500, 1000, 3000, 5000, 10000,
				       10000 };
	unsigned n;
	long t_ms = 0;

	kmsg(m_hold);
	sample_t(0, udc, ifname, cap, base, sock, &saw_cfg);
	for (n = 0; n < sizeof(gap_ms) / sizeof(gap_ms[0]); n++) {
		sleep_ts(gap_ms[n] / 1000, (gap_ms[n] % 1000) * 1000000L);
		t_ms += gap_ms[n];
		sample_t(t_ms, udc, ifname, cap, base, sock, &saw_cfg);
	}
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
	kmsg_stat("THYME-USB1B:STAT_UDC_CLASS=", p_udc, 1);
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

	log_udc_sysfs(udc, "state", "THYME-USB1B:PREBIND_STATE=");
	log_udc_sysfs(udc, "maximum_speed", "THYME-USB1B:MAX_SPEED=");
	log_udc_sysfs(udc, "current_speed", "THYME-USB1B:CURRENT_SPEED=");

	scan_nets(&base);
	kmsg_nets("THYME-USB1B:PREBIND_NETS=", &base);

	sock = sys4(SYS_socket, AF_INET, SOCK_DGRAM, 0, 0);
	if (sock < 0)
		fail_errno("SOCK", sock);
	kmsg("THYME-USB1B:SOCK_OK");

	build_gadget(cfgroot, &base, ifname, sizeof(ifname));

	kmsg2(m_bind_pfx, udc);
	r = bind_udc(cfgroot, udc);
	if (r)
		fail_errno("BIND", r);
	kmsg(m_bound);
	log_udc_sysfs(udc, "state", "THYME-USB1B:POSTBIND_STATE=");
	maybe_find_netdev(&base, ifname, sizeof(ifname),
			  "THYME-USB1B:NETDEV_AFTER_BIND=");
	wait_netdev(&base, ifname, sizeof(ifname));
	log_if_detail(ifname, sock);
	set_iff_up(sock, ifname);

	hold_observe(udc, ifname, sizeof(ifname), &base, sock);
	if (ifname[0]) {
		char gdir[128];

		log_if_detail(ifname, sock);
		if (!pcat(gdir, sizeof(gdir), cfgroot, "/usb_gadget/g1")) {
			log_ncm_attr(gdir, "dev_addr", "THYME-USB1B:DEV_ADDR=");
			log_ncm_attr(gdir, "host_addr", "THYME-USB1B:HOST_ADDR=");
			log_ncm_attr(gdir, "ifname", "THYME-USB1B:NCM_IFNAME=");
		}
	} else {
		kmsg("THYME-USB1B:NETDEV_FOUND=NONE");
	}
	if (sock >= 0)
		sys1(SYS_close, sock);
	kmsg(m_hold_done);
	kmsg(m_reboot);
	reboot_bl();
}
