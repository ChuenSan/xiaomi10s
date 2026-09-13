/* thyme R3 P1B minimal PID 1: raw aarch64 syscalls only, no libc runtime.
 * ABI4: sleep DELAY_SECONDS via 4-arg clock_nanosleep(CLOCK_MONOTONIC, 0,
 * &req, &rem), then request reboot. Fail-closed: ret == 0 completes the sleep;
 * ret == -EINTR retries with the remaining timespec until the full requested
 * delay has elapsed; any other failure exits PID 1 with 111 so the kernel
 * panics and RT-D bootargs panic=5 recovers Android A; a returned reboot exits
 * with 112. A sleep failure must never masquerade as a completed delayed
 * reboot. Depends on no procfs, sysfs, devtmpfs, console, USB, or UFS.
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

#define EXIT_SLEEP_FAILED	111
#define EXIT_REBOOT_RETURNED	112

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

/* used: survives -Os dead-code elimination; fixed width keeps the FIX8/FIX24
 * pair byte-length identical so image geometry matches across delays.
 */
__attribute__((used)) static const char ident[] =
	"THYME-R3-P1B-INIT ABI4 DELAY=" DELAY_STR;

void main(void)
{
	struct ts req = { DELAY_SECONDS, 0 };
	struct ts rem = { 0, 0 };
	long r;

	for (;;) {
		r = sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0,
			 (long)&req, (long)&rem);
		if (r == 0)
			break;
		if (r != -EINTR)
			for (;;)
				sys4(SYS_exit_group, EXIT_SLEEP_FAILED, 0, 0, 0);
		req = rem;
	}

	r = sys4(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
		 LINUX_REBOOT_CMD_RESTART, 0);
	(void)r;
	for (;;)
		sys4(SYS_exit_group, EXIT_REBOOT_RETURNED, 0, 0, 0);
}
