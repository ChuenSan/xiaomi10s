/*
 * aarch64 UAPI assert for USB Stage2 device static IP.
 * linux/fcntl.h + linux/sockios.h, not glibc <fcntl.h>/<net/if.h>.
 */
#ifndef __aarch64__
#error "usb-stage2-device-ip ABI assert is aarch64 only"
#endif

#include <asm/unistd.h>
#include <linux/fcntl.h>
#include <linux/sockios.h>

_Static_assert(O_DIRECTORY == 040000, "aarch64 O_DIRECTORY must be 040000");
_Static_assert(O_DIRECT == 0200000, "aarch64 O_DIRECT must be 0200000");
_Static_assert(__NR_newfstatat == 79, "aarch64 newfstatat must be 79");
_Static_assert(__NR_openat == 56, "aarch64 openat");
_Static_assert(__NR_getdents64 == 61, "aarch64 getdents64");
_Static_assert(__NR_ioctl == 29, "aarch64 ioctl");
_Static_assert(__NR_socket == 198, "aarch64 socket");
_Static_assert(AT_FDCWD == -100, "AT_FDCWD");
_Static_assert(SIOCGIFFLAGS == 0x8913, "SIOCGIFFLAGS");
_Static_assert(SIOCSIFFLAGS == 0x8914, "SIOCSIFFLAGS");
_Static_assert(SIOCGIFADDR == 0x8915, "SIOCGIFADDR");
_Static_assert(SIOCSIFADDR == 0x8916, "SIOCSIFADDR");
_Static_assert(SIOCGIFNETMASK == 0x891b, "SIOCGIFNETMASK");
_Static_assert(SIOCSIFNETMASK == 0x891c, "SIOCSIFNETMASK");

int usb2_abi_anchor;
