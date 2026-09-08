/*
 * PID 1: STOCK_KERNEL_USB_ENUM_STAGE0
 * configfs gadget + UDC bind on stock 4.19. Freestanding aarch64.
 *
 * TEST ONLY identity 1d6b:0104 (Linux Foundation gadget).
 * NOT PRODUCTION USB IDENTITY.
 *
 * Chosen function: ncm (live /proc/config.gz: CONFIG_USB_CONFIGFS_NCM=y;
 * CONFIG_USB_CONFIGFS_ACM is not set; CONFIG_USB_CONFIGFS_ECM is not set).
 * No IP, routing, HTTP, telnet.
 *
 * GitHub Actions only.
 */
#define SYS_mkdirat 34
#define SYS_symlinkat 36
#define SYS_mount 40
#define SYS_openat 56
#define SYS_close 57
#define SYS_getdents64 61
#define SYS_write 64
#define SYS_sync 81
#define SYS_nanosleep 101
#define SYS_reboot 142
#define SYS_mknodat 33

#define AT_FDCWD (-100)
#define O_RDONLY 0
#define O_WRONLY 1
#define O_DIRECTORY 000200000
#define EINTR 4
#define EEXIST 17
#define ENOENT 2
#define EBUSY 16
#define S_IFCHR 0020000

#define LINUX_REBOOT_MAGIC1 0xfee1dead
#define LINUX_REBOOT_MAGIC2 672274793
#define LINUX_REBOOT_CMD_RESTART2 0xA1B2C3D4

#define HOLD_SEC 30
#define FAIL_SEC 5
#define UDC_TRIES 10

struct timespec {
	long tv_sec;
	long tv_nsec;
};

static const char cmd_bl[] = "bootloader";
static const char kmsg_path[] = "/dev/kmsg";
static const char nl[] = "\n";

static const char m_init[] = "THYME-USB0:INIT";
static const char m_sysfs[] = "THYME-USB0:SYSFS_OK";
static const char m_cfg[] = "THYME-USB0:CONFIGFS_OK";
static const char m_udc_pfx[] = "THYME-USB0:UDC=";
static const char m_gad[] = "THYME-USB0:GADGET_CREATED";
static const char m_fn[] = "THYME-USB0:FUNCTION=ncm";
static const char m_lnk[] = "THYME-USB0:FUNCTION_LINKED";
static const char m_bound[] = "THYME-USB0:UDC_BOUND";
static const char m_hold[] = "THYME-USB0:HOLD";
static const char m_reboot[] = "THYME-USB0:REBOOT_BOOTLOADER";
static const char m_fail_sysfs[] = "THYME-USB0:FAIL:SYSFS";
static const char m_fail_cfg[] = "THYME-USB0:FAIL:CONFIGFS";
static const char m_fail_udc[] = "THYME-USB0:FAIL:NO_UDC";
static const char m_fail_fn[] = "THYME-USB0:FAIL:FUNCTION";
static const char m_fail_bind[] = "THYME-USB0:FAIL:BIND";

static const char p_dev[] = "/dev";
static const char p_sys[] = "/sys";
static const char p_udc[] = "/sys/class/udc";
static const char p_cfg_std[] = "/sys/kernel/config";
static const char p_cfg_and[] = "/config";
static const char pref_udc[] = "a600000.dwc3";

static const char src_devtmpfs[] = "devtmpfs";
static const char src_sysfs[] = "sysfs";
static const char src_configfs[] = "configfs";

static const char s_vid[] = "0x1d6b\n";
static const char s_pid[] = "0x0104\n";
static const char s_bcdusb[] = "0x0200\n";
static const char s_bcddev[] = "0x0100\n";
static const char s_mfg[] = "thyme-mainline\n";
static const char s_prod[] = "Stock Kernel USB Enum Stage0\n";
static const char s_ser[] = "THYME-USB0\n";
static const char s_cfg[] = "Stage0\n";
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
	long fd;

	fd = sys4(SYS_openat, AT_FDCWD, (long)kmsg_path, O_WRONLY, 0);
	if (fd < 0)
		return;
	sys4(SYS_write, fd, (long)a, slen(a), 0);
	sys4(SYS_write, fd, (long)b, slen(b), 0);
	sys4(SYS_write, fd, (long)nl, 1, 0);
	sys1(SYS_close, fd);
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

static int mkdir_one(const char *path)
{
	long r;

	r = sys4(SYS_mkdirat, AT_FDCWD, (long)path, 0755, 0);
	if (r == 0 || r == -EEXIST)
		return 0;
	return (int)r;
}

static int mkdir_p(const char *path)
{
	char buf[160];
	unsigned i, n;

	n = slen(path);
	if (n == 0 || n >= sizeof(buf))
		return -1;
	for (i = 0; i <= n; i++)
		buf[i] = path[i];
	for (i = 1; i <= n; i++) {
		if (buf[i] != '/' && buf[i] != 0)
			continue;
		buf[i] = 0;
		if (mkdir_one(buf))
			return -1;
		buf[i] = path[i];
	}
	return 0;
}

static int write_str(const char *path, const char *s)
{
	long fd, n, w;

	fd = sys4(SYS_openat, AT_FDCWD, (long)path, O_WRONLY, 0);
	if (fd < 0)
		return (int)fd;
	n = slen(s);
	w = sys4(SYS_write, fd, (long)s, n, 0);
	sys1(SYS_close, fd);
	if (w < 0)
		return (int)w;
	if (w != n)
		return -1;
	return 0;
}

static int is_dir(const char *path)
{
	long fd;

	fd = sys4(SYS_openat, AT_FDCWD, (long)path, O_RDONLY | O_DIRECTORY, 0);
	if (fd < 0)
		return 0;
	sys1(SYS_close, fd);
	return 1;
}

static int mount_fs(const char *src, const char *dst, const char *type)
{
	long r;

	r = sys6(SYS_mount, (long)src, (long)dst, (long)type, 0, 0, 0);
	if (r == 0 || r == -EEXIST || r == -EBUSY)
		return 0;
	return (int)r;
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

static int scan_udc(char *out, unsigned cap)
{
	unsigned char rec[1024];
	char first[64];
	char pref[64];
	long fd, nread;
	unsigned pos, found = 0, have_pref = 0;

	first[0] = 0;
	pref[0] = 0;
	fd = sys4(SYS_openat, AT_FDCWD, (long)p_udc, O_RDONLY | O_DIRECTORY, 0);
	if (fd < 0)
		return (int)fd;
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

static int discover_udc(char *out, unsigned cap)
{
	int tries, r;

	for (tries = 0; tries < UDC_TRIES; tries++) {
		r = scan_udc(out, cap);
		if (r == 0)
			return 0;
		sleep_ts(0, 300000000L);
	}
	return r;
}

static int prep_dev(void)
{
	long fd;

	mkdir_one(p_dev);
	mount_fs(src_devtmpfs, p_dev, src_devtmpfs);
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
	/* Prefer /config: Android A stock mountpoint, and it is on
	 * initramfs rootfs so mkdir works. /sys/kernel/config is sysfs
	 * and mkdir there often fails (stock DEVTMPFS is also unset).
	 */
	if (mkdir_one(p_cfg_and) == 0 &&
	    mount_fs(src_configfs, p_cfg_and, src_configfs) == 0 &&
	    is_dir("/config/usb_gadget"))
		return pcat(root, cap, p_cfg_and, "");
	if (mkdir_p(p_cfg_std) == 0 &&
	    mount_fs(src_configfs, p_cfg_std, src_configfs) == 0 &&
	    is_dir("/sys/kernel/config/usb_gadget"))
		return pcat(root, cap, p_cfg_std, "");
	return -1;
}

static int gwrite(const char *gdir, const char *leaf, const char *val)
{
	char p[192];

	if (pcat(p, sizeof(p), gdir, leaf))
		return -1;
	return write_str(p, val);
}

static int build_gadget(const char *root)
{
	char gdir[128];
	char p[192];
	char tgt[192];
	char lnk[192];

	if (pcat(gdir, sizeof(gdir), root, "/usb_gadget/g1"))
		return -1;
	if (mkdir_p(gdir))
		return -1;
	if (gwrite(gdir, "/idVendor", s_vid))
		return -1;
	if (gwrite(gdir, "/idProduct", s_pid))
		return -1;
	if (gwrite(gdir, "/bcdUSB", s_bcdusb))
		return -1;
	if (gwrite(gdir, "/bcdDevice", s_bcddev))
		return -1;
	if (pcat(p, sizeof(p), gdir, "/strings/0x409"))
		return -1;
	if (mkdir_p(p))
		return -1;
	if (gwrite(gdir, "/strings/0x409/manufacturer", s_mfg))
		return -1;
	if (gwrite(gdir, "/strings/0x409/product", s_prod))
		return -1;
	if (gwrite(gdir, "/strings/0x409/serialnumber", s_ser))
		return -1;
	if (pcat(p, sizeof(p), gdir, "/configs/c.1/strings/0x409"))
		return -1;
	if (mkdir_p(p))
		return -1;
	if (gwrite(gdir, "/configs/c.1/strings/0x409/configuration", s_cfg))
		return -1;
	if (gwrite(gdir, "/configs/c.1/MaxPower", s_pwr))
		return -1;
	kmsg(m_gad);

	if (pcat(p, sizeof(p), gdir, "/functions/ncm.usb0"))
		return -2;
	if (mkdir_p(p))
		return -2;
	kmsg(m_fn);

	if (pcat(tgt, sizeof(tgt), gdir, "/functions/ncm.usb0"))
		return -2;
	if (pcat(lnk, sizeof(lnk), gdir, "/configs/c.1/ncm.usb0"))
		return -2;
	if (sys4(SYS_symlinkat, (long)tgt, AT_FDCWD, (long)lnk, 0) < 0)
		return -2;
	kmsg(m_lnk);
	return 0;
}

static int bind_udc(const char *root, const char *udc)
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
	int r;

	prep_dev();
	kmsg(m_init);

	if (mkdir_p(p_sys) || mount_fs(src_sysfs, p_sys, src_sysfs))
		fail(m_fail_sysfs);
	kmsg(m_sysfs);

	if (setup_configfs(cfgroot, sizeof(cfgroot)))
		fail(m_fail_cfg);
	kmsg(m_cfg);

	if (discover_udc(udc, sizeof(udc)))
		fail(m_fail_udc);
	kmsg2(m_udc_pfx, udc);

	r = build_gadget(cfgroot);
	if (r == -2)
		fail(m_fail_fn);
	if (r)
		fail(m_fail_cfg);

	if (bind_udc(cfgroot, udc))
		fail(m_fail_bind);
	kmsg(m_bound);
	kmsg(m_hold);
	sleep_ts(HOLD_SEC, 0);
	kmsg(m_reboot);
	reboot_bl();
}
