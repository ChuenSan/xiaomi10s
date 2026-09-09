/*
 * aarch64 UAPI assert for USB Stage4 HTTP.
 * linux/fcntl.h + linux/sockios.h, not glibc <fcntl.h>/<net/if.h>.
 */
#ifndef __aarch64__
#error "usb-stage4-http ABI assert is aarch64 only"
#endif

#include <asm/unistd.h>
#include <linux/fcntl.h>
#include <linux/sockios.h>

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

_Static_assert(O_DIRECTORY == 040000, "aarch64 O_DIRECTORY must be 040000");
_Static_assert(O_DIRECT == 0200000, "aarch64 O_DIRECT must be 0200000");
_Static_assert(__NR_newfstatat == 79, "aarch64 newfstatat must be 79");
_Static_assert(__NR_openat == 56, "aarch64 openat");
_Static_assert(__NR_getdents64 == 61, "aarch64 getdents64");
_Static_assert(__NR_ioctl == 29, "aarch64 ioctl");
_Static_assert(__NR_socket == 198, "aarch64 socket");
_Static_assert(__NR_fcntl == 25, "aarch64 fcntl");
_Static_assert(__NR_bind == 200, "aarch64 bind");
_Static_assert(__NR_listen == 201, "aarch64 listen");
_Static_assert(__NR_accept == 202, "aarch64 accept");
_Static_assert(__NR_sendto == 206, "aarch64 sendto");
_Static_assert(__NR_setsockopt == 208, "aarch64 setsockopt");
_Static_assert(SOL_SOCKET == 1, "SOL_SOCKET");
_Static_assert(SO_REUSEADDR == 2, "SO_REUSEADDR");
_Static_assert(MSG_NOSIGNAL == 0x4000, "MSG_NOSIGNAL");
_Static_assert(F_GETFL == 3, "F_GETFL");
_Static_assert(F_SETFL == 4, "F_SETFL");
_Static_assert(O_NONBLOCK == 00004000, "O_NONBLOCK");
_Static_assert(AT_FDCWD == -100, "AT_FDCWD");
_Static_assert(SIOCGIFFLAGS == 0x8913, "SIOCGIFFLAGS");
_Static_assert(SIOCSIFFLAGS == 0x8914, "SIOCSIFFLAGS");
_Static_assert(SIOCGIFADDR == 0x8915, "SIOCGIFADDR");
_Static_assert(SIOCSIFADDR == 0x8916, "SIOCSIFADDR");
_Static_assert(SIOCGIFNETMASK == 0x891b, "SIOCGIFNETMASK");
_Static_assert(SIOCSIFNETMASK == 0x891c, "SIOCSIFNETMASK");

int usb4_http_abi_anchor;
