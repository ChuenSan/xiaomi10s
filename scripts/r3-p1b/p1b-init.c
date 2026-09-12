/* thyme R3 P1B minimal PID 1: raw aarch64 syscalls only, no libc runtime.
 * Sleep DELAY_SECONDS via clock_nanosleep, then request reboot.
 * If reboot returns, exit PID 1 -> kernel panic; RT-D bootargs panic=5
 * gives the automatic recovery fallback. Depends on no procfs, sysfs,
 * devtmpfs, console, USB, or UFS. First evidence is only: PID 1 executed.
 */
#ifndef DELAY_SECONDS
#error "DELAY_SECONDS required"
#endif

#define SYS_clock_nanosleep	115
#define SYS_exit_group		94
#define SYS_reboot		142

#define CLOCK_MONOTONIC		1
#define EINTR			4

#define LINUX_REBOOT_MAGIC1	0xfee1dead
#define LINUX_REBOOT_MAGIC2	672274793
#define LINUX_REBOOT_CMD_RESTART 0x01234567

static long sys3(long nr, long a0, long a1, long a2)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;

	__asm__ volatile ("svc #0"
			  : "+r"(x0)
			  : "r"(x8), "r"(x1), "r"(x2)
			  : "memory", "cc");
	return x0;
}

static long sys4(long nr, long a0, long a1, long a2, long a3)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	register long x3 __asm__("x3") = a3;

	__asm__ volatile ("svc #0"
			  : "+r"(x0)
			  : "r"(x8), "r"(x1), "r"(x2), "r"(x3)
			  : "memory", "cc");
	return x0;
}

struct ts {
	long tv_sec;
	long tv_nsec;
};

#define STR2(x) #x
#define STR(x) STR2(x)
#if DELAY_SECONDS < 10
#define DELAY_STR "0" STR(DELAY_SECONDS)
#else
#define DELAY_STR STR(DELAY_SECONDS)
#endif

/* used: survives -Os dead-code elimination; fixed width keeps the INIT8/INIT24
 * pair byte-length identical so image geometry matches across delays.
 */
__attribute__((used)) static const char ident[] =
	"THYME-R3-P1B-INIT DELAY=" DELAY_STR " CMD=restart";

void main(void)
{
	struct ts req = { DELAY_SECONDS, 0 };
	struct ts rem = { 0, 0 };
	long r;

	while (sys3(SYS_clock_nanosleep, CLOCK_MONOTONIC, (long)&req,
		    (long)&rem) == -EINTR)
		req = rem;

	r = sys4(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
		 LINUX_REBOOT_CMD_RESTART, 0);
	sys3(SYS_exit_group, r, 0, 0);
	for (;;)
		;
}
