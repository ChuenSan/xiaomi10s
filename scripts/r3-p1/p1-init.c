/*
 * Minimal PID 1 for R3 P1 built-in initramfs.
 * Mount proc/sysfs/devtmpfs, sample /proc, sleep, reboot to active slot.
 * Freestanding aarch64. GitHub Actions only.
 */
#ifndef DELAY_SECONDS
#error DELAY_SECONDS required
#endif

#define STR_(x) #x
#define STR(x) STR_(x)

#define SYS_openat 56
#define SYS_close 57
#define SYS_read 63
#define SYS_write 64
#define SYS_sync 81
#define SYS_nanosleep 101
#define SYS_mkdirat 34
#define SYS_mount 165
#define SYS_reboot 142

#define AT_FDCWD (-100)
#define O_RDONLY 0
#define O_WRONLY 1
#define EINTR 4

#define LINUX_REBOOT_MAGIC1 0xfee1dead
#define LINUX_REBOOT_MAGIC2 672274793
#define LINUX_REBOOT_CMD_RESTART 0x01234567

struct timespec {
	long tv_sec;
	long tv_nsec;
};

static const char ident[] =
	"THYME-R3-P1-INIT DELAY=" STR(DELAY_SECONDS) " CMD=restart";
static const char kmsg_path[] = "/dev/kmsg";
static const char proc[] = "proc";
static const char sysfs[] = "sysfs";
static const char devtmpfs[] = "devtmpfs";
static const char proc_dir[] = "/proc";
static const char sys_dir[] = "/sys";
static const char dev_dir[] = "/dev";
static const char uptime_path[] = "/proc/uptime";
static const char cmdline_path[] = "/proc/cmdline";
static const char model_path[] = "/proc/device-tree/model";

static long sys4(long nr, long a0, long a1, long a2, long a3)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	register long x3 __asm__("x3") = a3;
	__asm__ volatile("svc #0"
			 : "+r"(x0)
			 : "r"(x8), "r"(x1), "r"(x2), "r"(x3)
			 : "memory", "cc");
	return x0;
}

static long sys5(long nr, long a0, long a1, long a2, long a3, long a4)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	register long x3 __asm__("x3") = a3;
	register long x4 __asm__("x4") = a4;
	__asm__ volatile("svc #0"
			 : "+r"(x0)
			 : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4)
			 : "memory", "cc");
	return x0;
}

static long sys1(long nr, long a0)
{
	return sys4(nr, a0, 0, 0, 0);
}

static void sleep_sec(long sec)
{
	struct timespec rem;
	long r;

	rem.tv_sec = sec;
	rem.tv_nsec = 0;
	for (;;) {
		r = sys4(SYS_nanosleep, (long)&rem, (long)&rem, 0, 0);
		if (r == 0)
			return;
		if (r != -EINTR)
			return;
	}
}

static void kmsg_mark(void)
{
	long fd, n;

	n = 0;
	while (ident[n])
		n++;
	fd = sys4(SYS_openat, AT_FDCWD, (long)kmsg_path, O_WRONLY, 0);
	if (fd < 0)
		return;
	sys4(SYS_write, fd, (long)ident, n, 0);
	sys1(SYS_close, fd);
}

static void sample(const char *path)
{
	char buf[128];
	long fd, n;

	fd = sys4(SYS_openat, AT_FDCWD, (long)path, O_RDONLY, 0);
	if (fd < 0)
		return;
	n = sys4(SYS_read, fd, (long)buf, 128, 0);
	(void)n;
	sys1(SYS_close, fd);
}

static void prepare_fs(void)
{
	sys4(SYS_mkdirat, AT_FDCWD, (long)proc_dir, 0755, 0);
	sys4(SYS_mkdirat, AT_FDCWD, (long)sys_dir, 0755, 0);
	sys4(SYS_mkdirat, AT_FDCWD, (long)dev_dir, 0755, 0);
	sys5(SYS_mount, (long)proc, (long)proc_dir, (long)proc, 0, 0);
	sys5(SYS_mount, (long)sysfs, (long)sys_dir, (long)sysfs, 0, 0);
	sys5(SYS_mount, (long)devtmpfs, (long)dev_dir, (long)devtmpfs, 0, 0);
}

__attribute__((used, noreturn, section(".text")))
int main(void)
{
	prepare_fs();
	kmsg_mark();
	sample(uptime_path);
	sample(cmdline_path);
	sample(model_path);
	sleep_sec(DELAY_SECONDS);
	sys1(SYS_sync, 0);
	sys4(SYS_reboot,
	     LINUX_REBOOT_MAGIC1,
	     LINUX_REBOOT_MAGIC2,
	     LINUX_REBOOT_CMD_RESTART,
	     0);
	for (;;)
		sleep_sec(3600);
}
