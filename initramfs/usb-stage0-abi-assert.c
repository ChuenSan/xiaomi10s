/*
 * Compile with aarch64-linux-gnu-gcc. Proves the helper toolchain
 * is arm64 UAPI, not asm-generic/x86 O_* values.
 *
 * Same UAPI headers as usb-stage0-init.c (linux/fcntl.h), not
 * glibc <fcntl.h> which hides O_DIRECT unless _GNU_SOURCE.
 */
#ifndef __aarch64__
#error "usb-stage0 ABI assert is aarch64 only"
#endif

#include <linux/fcntl.h>
#include <asm/unistd.h>

_Static_assert(O_DIRECTORY == 040000, "aarch64 O_DIRECTORY must be 040000");
_Static_assert(O_DIRECT == 0200000, "aarch64 O_DIRECT must be 0200000");
_Static_assert(__NR_newfstatat == 79, "aarch64 newfstatat must be 79");
_Static_assert(__NR_openat == 56, "aarch64 openat");
_Static_assert(__NR_getdents64 == 61, "aarch64 getdents64");
_Static_assert(AT_FDCWD == -100, "AT_FDCWD");

int usb0_abi_anchor;
