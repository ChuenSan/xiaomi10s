/*
 * PID 1 execution proof for stock 4.19.
 * Sleep DELAY_SECONDS, then LINUX_REBOOT_CMD_RESTART2 "bootloader".
 * Freestanding aarch64, no libc. GitHub Actions only.
 */
#ifndef DELAY_SECONDS
#error DELAY_SECONDS required
#endif

#define STR_(x) #x
#define STR(x) STR_(x)

#define SYS_openat 56
#define SYS_close 57
#define SYS_write 64
#define SYS_sync 81
#define SYS_nanosleep 101
#define SYS_reboot 142

#define AT_FDCWD (-100)
#define O_WRONLY 1
#define EINTR 4

#define LINUX_REBOOT_MAGIC1 0xfee1dead
#define LINUX_REBOOT_MAGIC2 672274793
#define LINUX_REBOOT_CMD_RESTART2 0xA1B2C3D4

struct timespec {
	long tv_sec;
	long tv_nsec;
};

static const char ident[] =
	"THYME-INITEXEC-PROOF DELAY=" STR(DELAY_SECONDS) " CMD=bootloader";
static const char cmd[] = "bootloader";
static const char kmsg_path[] = "/dev/kmsg";
static const char kmsg_nl[] = "\n";

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
	sys4(SYS_write, fd, (long)kmsg_nl, 1, 0);
	sys1(SYS_close, fd);
}

void _start(void) __attribute__((noreturn));

void _start(void)
{
	kmsg_mark();
	sleep_sec(DELAY_SECONDS);
	sys1(SYS_sync, 0);
	sys4(SYS_reboot,
	     LINUX_REBOOT_MAGIC1,
	     LINUX_REBOOT_MAGIC2,
	     LINUX_REBOOT_CMD_RESTART2,
	     (long)cmd);
	for (;;)
		sleep_sec(3600);
}

asm(".section .note.GNU-stack,\"\",@progbits");
