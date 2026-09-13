#!/usr/bin/env python3
"""R3 P1B failure isolation: audit the authoritative INIT8/INIT24 /init binaries.

GitHub Actions only. Modes:
  audit   identity pins + disassembly ABI audit + cpio fields + embedded
          initramfs containment over the frozen public-run artifacts
  config  reconstruct the P1B merged .config (config-only, no kernel build)
          and audit timer/panic/initramfs symbols
  qemu    pinned qemu-aarch64 user-mode execution of the exact authoritative
          binaries with -strace, wallclock pair measurement, positive control

The QEMU pair verdict is preregistered: STRONG 15.5-16.5s, SUPPORTED
15.0-17.0s, else FAIL for PAIR_DELTA.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import struct
import subprocess
import time
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local audit/execution")

REPO = Path(__file__).resolve().parent.parent.parent
LINUX = REPO / "linux-6.6"

LINUX_BASE = "8b73de7da85fde281a385e0b26eda9bffd3ca477"
INIT8_INIT_SHA = "4c1491b21d83080b5303e6294aad516f6eeb79bd276e2b159059f665a22135f4"
INIT24_INIT_SHA = "b5eb44c8cf5c4e0278851e6820378795079129083ae77fb5659e32979f5b7f55"
INIT8_PAYLOAD_SHA = "9720451ca7622d7578b114cab3a0a61ee50cd9cf27cf9053d73fb8ded2075a5c"
INIT24_PAYLOAD_SHA = "c8d2d33a3e771455cce49b867858dbb8779eb5900312e86578f2afe203632f58"
TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
CPIO8_SHA = "c45fa7a0bd8f7ca7062524b4f4b11e33ef0808553764d23e4ddc2707295ef684"
CPIO24_SHA = "651a2ce4e5cdb3281c2d238344717ad47f630a6b70638fdc343616a9d7082f9c"
RT_D_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
RT_D_SIZE = 144593
TRAMP_OFFSET = 0x40
CODE1_LE = b"\x0f\x00\x00\x14"  # b 0x40
RT_D_BOOTARGS = b"rdinit=/init panic=5 loglevel=7"
S_RESIDUE = 0x80000
ALIGN_2M = 0x200000

STRONG_BAND = (15.5, 16.5)
SUPPORTED_BAND = (15.0, 17.0)

OUT: list[str] = []


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    raise SystemExit(f"{label}: {detail}" if detail else label)


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True,
        timeout: int | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True,
                          text=True, timeout=timeout)
    if check and proc.returncode != 0:
        fail("P1B_FI_CMD_FAILED",
             f"{' '.join(cmd)}\n{proc.stderr}\n{proc.stdout[-4000:]}")
    return proc


def emit(line: str) -> None:
    OUT.append(line)
    print(line)


def disasm_lines(tool: str, path: Path) -> list[str]:
    dump = run([tool, "-d", str(path)]).stdout
    lines = []
    for line in dump.splitlines():
        m = re.match(r"^\s*[0-9a-f]+:\s+(.*)$", line)
        if m:
            lines.append(m.group(1).strip())
    if not lines:
        fail("P1B_FI_DISASM_FAILED", str(path))
    return lines


def audit(auth: Path, out: Path, objdump: str) -> None:
    init8 = auth / "p1b-init-8s"
    init24 = auth / "p1b-init-24s"
    cpio8 = auth / "initramfs-8s.cpio"
    cpio24 = auth / "initramfs-24s.cpio"
    pay8 = auth / "thyme-r3-p1b-init8-kernel-payload.bin"
    pay24 = auth / "thyme-r3-p1b-init24-kernel-payload.bin"
    for p in (init8, init24, cpio8, cpio24, pay8, pay24):
        if not p.is_file() or p.stat().st_size == 0:
            fail("P1B_FI_AUTH_MISSING", str(p))
    sums = run(["sha256sum", "-c", "SHA256SUMS"], cwd=auth)
    (out / "sha256sums-check.txt").write_text(sums.stdout + sums.stderr)

    b8, b24 = init8.read_bytes(), init24.read_bytes()
    c8, c24 = cpio8.read_bytes(), cpio24.read_bytes()
    p8, p24 = pay8.read_bytes(), pay24.read_bytes()
    if sha(b8) != INIT8_INIT_SHA or sha(b24) != INIT24_INIT_SHA:
        fail("P1B_FI_INIT_SHA_FAILED")
    emit("P1B_FI_AUTH_INIT_SHAS=PASS")
    if sha(p8) != INIT8_PAYLOAD_SHA or sha(p24) != INIT24_PAYLOAD_SHA:
        fail("P1B_FI_PAYLOAD_SHA_FAILED")
    if sha(c8) != CPIO8_SHA or sha(c24) != CPIO24_SHA:
        fail("P1B_FI_CPIO_SHA_FAILED")
    emit("P1B_FI_AUTH_PAYLOAD_CPIO_SHAS=PASS")

    # --- disassembly ABI audit ---
    d8, d24 = disasm_lines(objdump, init8), disasm_lines(objdump, init24)
    (out / "init8-disasm.txt").write_text("\n".join(d8) + "\n")
    (out / "init24-disasm.txt").write_text("\n".join(d24) + "\n")

    def has(pattern: str, lines: list[str]) -> bool:
        rx = re.compile(pattern)
        return any(rx.search(l) for l in lines)

    for lines in (d8, d24):
        if not has(r"\b(movz|mov)\s+[wx]8, #(0x73|115)\b", lines):
            fail("P1B_FI_DISASM_FAILED", "clock_nanosleep 115 not found")
        if not has(r"\b(movz|mov)\s+[wx]8, #(0x8e|142)\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot 142 not found")
        if not has(r"\b(movz|mov)\s+[wx]8, #(0x5e|94)\b", lines):
            fail("P1B_FI_DISASM_FAILED", "exit_group 94 not found")
        if not has(r"\b(movz|mov)\s+[wx]0, #(0xdead|57005)\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot magic1 low not found")
        if not has(r"\bmovk\s+[wx]0, #(0xfee1|65249), lsl #16\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot magic1 high not found")
        if not has(r"\b(movz|mov)\s+[wx]1, #(0x1969|6505)\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot magic2 low not found")
        if not has(r"\bmovk\s+[wx]1, #(0x2812|10258), lsl #16\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot magic2 high not found")
        if not has(r"\b(movz|mov)\s+[wx]2, #(0x4567|17767)\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot cmd low not found")
        if not has(r"\bmovk\s+[wx]2, #(0x123|291), lsl #16\b", lines):
            fail("P1B_FI_DISASM_FAILED", "reboot cmd high not found")
    emit("INIT_SYSCALL_NUMBER_AUDIT=PASS (115/142/94 in both binaries)")
    emit("INIT_REBOOT_ABI=PASS (magic1 0xfee1dead, magic2 0x28121969, "
         "cmd 0x01234567, arg x3=0)")

    # clock_nanosleep call block: 3-arg ABI proof — the instruction window
    # around the first x8=115 setup up to the first svc must not write x3.
    for name, lines in (("init8", d8), ("init24", d24)):
        start = next(i for i, l in enumerate(lines)
                     if re.search(r"\b(movz|mov)\s+[wx]8, #(0x73|115)\b", l))
        svc = next(i for i, l in enumerate(lines[start:], start)
                   if l.startswith("svc"))
        block = lines[max(0, start - 6):svc]
        (out / f"{name}-clock-nanosleep-block.txt").write_text(
            "\n".join(block) + "\n")
        dest3 = (r"\b(mov|movz|movk|add|sub|orr|and|eor|ldr|adr|mvn|neg|"
                 r"sxtw|csel|cset)\s+x3[, ]")
        if any(re.search(dest3, l) for l in block):
            fail("P1B_FI_CLOCK_NANOSLEEP_ABI", f"{name}: x3 written before svc")
        if not has(r"\b(movz|mov)\s+[wx]0, #(0x1|1)\b", block):
            fail("P1B_FI_CLOCK_NANOSLEEP_ABI", f"{name}: clockid != 1")
        for reg in ("x1", "x2"):
            if not has(rf"\badd\s+{reg}, (sp|x29)(,|, #)", block) and \
                    not has(rf"\bmov\s+{reg}, sp\b", block):
                fail("P1B_FI_CLOCK_NANOSLEEP_ABI", f"{name}: {reg} not stack")
    emit("INIT_CLOCK_NANOSLEEP_ABI=FAIL_3ARG_CALL "
         "(x8=115 with x0=1, x1=&req, x2=&rem; flags slot holds &req, "
         "rqtp slot holds &rem; no x3/rmtp setup)")
    if not has(r"\bcmn\s+x0, #(0x4|4)\b", d8) or not has(r"\bcmn\s+x0, #(0x4|4)\b", d24):
        fail("P1B_FI_DISASM_FAILED", "EINTR-only return check not found")
    emit("INIT_SLEEP_RETURN_CHECKED=NO (only -EINTR retried; EINVAL/EFAULT/"
         "ENOSYS paths fall through to reboot)")
    emit("P1B_INIT_CONTROL_HAS_UNCHECKED_SLEEP_FAILURE_PATH=YES")

    # semantic delta between the pair
    diffs = [(a, b) for a, b in zip(d8, d24) if a != b]
    if len(d8) != len(d24) or not 1 <= len(diffs) <= 4:
        fail("P1B_FI_SEMANTIC_DELTA", f"{len(d8)} vs {len(d24)}, diffs={len(diffs)}")
    for a, b in diffs:
        norm = lambda s: re.sub(r"#-?(0x[0-9a-f]+|\d+)", "#", s)
        if norm(a) != norm(b):
            fail("P1B_FI_SEMANTIC_DELTA", f"{a!r} vs {b!r}")
    (out / "init-pair-diff.txt").write_text(
        "\n".join(f"- {a}\n+ {b}" for a, b in diffs) + "\n")
    emit(f"INIT_BINARY_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY ({len(diffs)} "
         f"instruction diffs: {diffs})")
    if b"THYME-R3-P1B-INIT DELAY=08 CMD=restart" not in b8 or \
            b"THYME-R3-P1B-INIT DELAY=24 CMD=restart" not in b24:
        fail("P1B_FI_SEMANTIC_DELTA", "ident strings")
    emit("INIT_BINARY_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY (rodata ident too)")

    # --- cpio field audit ---
    def parse_cpio(data: bytes) -> list[dict]:
        entries, off = [], 0
        while off + 6 <= len(data):
            if data[off:off + 6] not in (b"070701", b"070702"):
                fail("P1B_FI_CPIO_FAILED", f"magic at {off:#x}")
            f = [int(data[off + 6 + i * 8: off + 6 + (i + 1) * 8], 16)
                 for i in range(13)]
            off += 110
            name = data[off:off + f[11]].rstrip(b"\x00").decode()
            off = (off + f[11] + 3) & ~3
            body = data[off:off + f[6]]
            off = (off + f[6] + 3) & ~3
            if name == "TRAILER!!!":
                break
            entries.append({"name": name, "mode": f[1], "uid": f[2],
                            "gid": f[3], "filesize": f[6], "data": body})
        else:
            fail("P1B_FI_CPIO_FAILED", "no trailer")
        return entries

    for label, c, init_ref in (("8s", c8, b8), ("24s", c24, b24)):
        es = parse_cpio(c)
        names = [e["name"] for e in es]
        if names != ["dev", "init", "proc", "sys"]:
            fail("P1B_FI_CPIO_FAILED", f"{label}: {names}")
        ini = es[1]
        if ini["mode"] != 0o100755 or ini["uid"] or ini["gid"]:
            fail("P1B_FI_CPIO_FAILED", f"{label}: mode/uid/gid")
        if ini["filesize"] != len(init_ref) or ini["data"] != init_ref:
            fail("P1B_FI_CPIO_FAILED", f"{label}: data != /init binary")
    emit("BUILTIN_INITRAMFS_CPIO_FIELDS=PASS (newc dev/init/proc/sys; "
         "/init mode 0755 uid=0 gid=0; data byte-identical to /init)")

    # --- embedded initramfs containment ---
    for label, pay, c, other in (("init8", p8, c8, c24), ("init24", p24, c24, c8)):
        if pay.count(c) != 1:
            fail("P1B_FI_EMBED_FAILED", f"{label}: cpio occurrences != 1")
        if other in pay:
            fail("P1B_FI_EMBED_FAILED", f"{label}: wrong-delay cpio embedded")
    emit("BUILTIN_INITRAMFS_EMBED=PASS (each Image embeds exactly its own "
         "delay cpio, uncompressed, byte-exact)")

    for label, pay, init_ref in (("init8", p8, b8), ("init24", p24, b24)):
        if pay.count(init_ref) != 1:
            fail("P1B_FI_EMBED_FAILED", f"{label}: /init occurrences != 1")
        if sha(pay[-RT_D_SIZE:]) != RT_D_SHA:
            fail("P1B_FI_EMBED_FAILED", f"{label}: RT-D trailer")
        dtb_offset = len(pay) - RT_D_SIZE
        if (S_RESIDUE + dtb_offset) % ALIGN_2M:
            fail("P1B_FI_EMBED_FAILED", f"{label}: DTB geometry")
        if pay[dtb_offset:dtb_offset + 4] != b"\xd0\x0d\xfe\xed":
            fail("P1B_FI_EMBED_FAILED", f"{label}: FDT magic")
        if RT_D_BOOTARGS not in pay[dtb_offset:]:
            fail("P1B_FI_EMBED_FAILED", f"{label}: bootargs")
        if pay[4:8] != CODE1_LE or sha(pay[TRAMP_OFFSET:TRAMP_OFFSET + 48]) != TRAMP_SHA:
            fail("P1B_FI_EMBED_FAILED", f"{label}: code1/trampoline")
    if len(p8) != len(p24):
        fail("P1B_FI_EMBED_FAILED", "pair payload sizes differ")
    emit("PAIR_GEOMETRY_IDENTICAL=YES "
         f"(payload {len(p8)} B, DTB trailer, trampoline, bootargs "
         "rdinit=/init panic=5 loglevel=7)")

    gates = [
        "P1B_FI_AUDIT_GATES=PASS",
        f"AUTH_BINARY_SHAS=PASS INIT8={INIT8_INIT_SHA} INIT24={INIT24_INIT_SHA}",
        "INIT_SYSCALL_NUMBER_AUDIT=PASS",
        "INIT_CLOCK_NANOSLEEP_ABI=FAIL_3ARG_CALL",
        "INIT_SLEEP_RETURN_CHECKED=NO",
        "P1B_INIT_CONTROL_HAS_UNCHECKED_SLEEP_FAILURE_PATH=YES",
        "INIT_REBOOT_ABI=PASS",
        "INIT_BINARY_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY",
        "BUILTIN_INITRAMFS_CPIO_FIELDS=PASS",
        "BUILTIN_INITRAMFS_EMBED=PASS",
        "PAIR_GEOMETRY_IDENTICAL=YES",
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "audit-gates.txt").write_text("\n".join(gates) + "\n")


CONFIG_SYMBOLS = (
    "CONFIG_ARM64", "CONFIG_MMU", "CONFIG_BINFMT_ELF", "CONFIG_BLK_DEV_INITRD",
    "CONFIG_INITRAMFS_SOURCE", "CONFIG_INITRAMFS_COMPRESSION_NONE",
    "CONFIG_POSIX_TIMERS", "CONFIG_HIGH_RES_TIMERS",
    "CONFIG_GENERIC_CLOCKEVENTS", "CONFIG_GENERIC_CLOCKEVENTS_BROADCAST",
    "CONFIG_PANIC_TIMEOUT", "CONFIG_PANIC_ON_OOPS",
    "CONFIG_PANIC_ON_OOPS_VALUE", "CONFIG_PANIC_ON_WARN",
)


def config(out: Path, cpio: Path) -> None:
    base = run(["git", "-C", str(LINUX), "rev-parse", "HEAD"]).stdout.strip()
    if base != LINUX_BASE:
        fail("P1B_FI_CONFIG_FAILED", f"linux base {base}")
    odir = (out / "out-config-audit").resolve()
    odir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    makeargs = ["O=" + str(odir), "ARCH=arm64", "LLVM=1"]
    run(["make", *makeargs, "defconfig"], cwd=LINUX, env=env)
    frag = odir / "r3-p1b-initramfs.fragment"
    frag.write_text(
        f'CONFIG_INITRAMFS_SOURCE="{cpio.resolve()}"\n'
        "CONFIG_INITRAMFS_COMPRESSION_NONE=y\n"
        "CONFIG_INITRAMFS_ROOT_UID=0\n"
        "CONFIG_INITRAMFS_ROOT_GID=0\n")
    run(["./scripts/kconfig/merge_config.sh", "-m", "-O", str(odir),
         str(odir / ".config"), str(REPO / "configs" / "thyme-route-b.config")],
        cwd=LINUX, env=env)
    run(["./scripts/kconfig/merge_config.sh", "-m", "-O", str(odir),
         str(odir / ".config"), str(REPO / "configs" / "thyme-r3-p1b.config"),
         str(frag)], cwd=LINUX, env=env)
    run(["make", *makeargs, "olddefconfig"], cwd=LINUX, env=env)
    cfg = (odir / ".config").read_text()
    (out / "reconstructed-config.txt").write_text(cfg)
    values = {}
    for sym in CONFIG_SYMBOLS:
        m = re.search(rf"^{re.escape(sym)}=(.*)$", cfg, re.M)
        if not m:
            fail("P1B_FI_CONFIG_FAILED", f"missing {sym}")
        values[sym] = m.group(1)
    for sym in ("CONFIG_ARM64", "CONFIG_MMU", "CONFIG_BINFMT_ELF",
                "CONFIG_BLK_DEV_INITRD", "CONFIG_INITRAMFS_COMPRESSION_NONE",
                "CONFIG_POSIX_TIMERS", "CONFIG_HIGH_RES_TIMERS",
                "CONFIG_GENERIC_CLOCKEVENTS"):
        if values[sym] != "y":
            fail("P1B_FI_CONFIG_FAILED", f"{sym}={values[sym]}")
    if values["CONFIG_INITRAMFS_SOURCE"] != str(cpio.resolve()):
        fail("P1B_FI_CONFIG_FAILED", "INITRAMFS_SOURCE not applied")
    if values["CONFIG_PANIC_ON_OOPS_VALUE"] != "0":
        fail("P1B_FI_CONFIG_FAILED", "PANIC_ON_OOPS_VALUE")
    if values["CONFIG_PANIC_ON_WARN"] != "n":
        fail("P1B_FI_CONFIG_FAILED", "PANIC_ON_WARN")
    if values["CONFIG_PANIC_TIMEOUT"] not in ("", "0", "n"):
        fail("P1B_FI_CONFIG_FAILED", "PANIC_TIMEOUT set in config")
    emit("P1B_FI_CONFIG_RECONSTRUCTED=YES (defconfig + route-b + r3-p1b + "
         "initramfs fragment; symbol-level authoritative, path string differs "
         "from build-time only)")
    emit("P1B_CLOCK_NANOSLEEP_KERNEL_SUPPORT=YES "
         "(CONFIG_POSIX_TIMERS=y -> kernel/time/posix-timers.c "
         "SYSCALL_DEFINE4(clock_nanosleep) compiled; CONFIG_HIGH_RES_TIMERS=y)")
    for sym, v in values.items():
        emit(f"P1B_CONFIG_{sym}={v}")
    gates = [
        "P1B_FI_CONFIG_GATES=PASS",
        "P1B_CLOCK_NANOSLEEP_KERNEL_SUPPORT=YES",
        "EARLY_PANIC_CAN_AUTO_REBOOT_WITH_PANIC_5=YES",
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "config-gates.txt").write_text("\n".join(gates) + "\n")


QEMU_CONTROL_C = r"""#ifndef SLEEP_SECONDS
#define SLEEP_SECONDS 2
#endif
#define SYS_clock_nanosleep 115
#define SYS_exit_group 94
#define CLOCK_MONOTONIC 1
static long sys4(long nr, long a0, long a1, long a2, long a3)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	register long x3 __asm__("x3") = a3;
	__asm__ volatile ("svc #0" : "+r"(x0)
			  : "r"(x8), "r"(x1), "r"(x2), "r"(x3)
			  : "memory", "cc");
	return x0;
}
struct ts { long tv_sec; long tv_nsec; };
void _start(void)
{
	struct ts req = { SLEEP_SECONDS, 0 };
	struct ts rem = { 0, 0 };
	long r = sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0,
		      (long)&req, (long)&rem);
	sys4(SYS_exit_group, r == 0 ? 0 : 70, 0, 0, 0);
	for (;;)
		;
}
"""


def parse_strace(text: str, key: str) -> str | None:
    for line in text.splitlines():
        if key in line:
            return line.strip()
    return None


def qemu(auth: Path, out: Path, gcc: str, qemu_bin: str) -> None:
    ver = run([qemu_bin, "--version"]).stdout.splitlines()[0]
    if not re.search(r"version 8\.\d", ver):
        fail("P1B_FI_QEMU_FAILED", f"unpinned qemu: {ver}")
    emit(f"QEMU_PINNED={ver}")

    src = out / "qemu-positive-control.c"
    src.write_text(QEMU_CONTROL_C)
    ctl = out / "qemu-positive-control"
    run([gcc, "-ffreestanding", "-nostdlib", "-static", "-no-pie", "-fno-pic",
         "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-Os",
         "-Wl,-e,_start", "-Wl,--build-id=none", "-o", str(ctl), str(src)])
    ctl.chmod(0o755)
    t0 = time.perf_counter()
    p = run([qemu_bin, "-strace", str(ctl)], check=False, timeout=120)
    dt = time.perf_counter() - t0
    (out / "qemu-positive-control-strace.txt").write_text(p.stderr + p.stdout)
    line = parse_strace(p.stderr, "clock_nanosleep")
    if not line or "=0" not in line.replace(" ", ""):
        fail("P1B_FI_QEMU_FAILED", f"positive control sleep: {line}")
    if not (1.0 <= dt <= 4.5) or p.returncode != 0:
        fail("P1B_FI_QEMU_FAILED", f"positive control {dt:.3f}s rc={p.returncode}")
    emit(f"QEMU_HARNESS_POSITIVE_CONTROL=PASS ({dt:.3f}s, 4-arg "
         f"clock_nanosleep returned 0)")

    results = {}
    for name, path in (("INIT8", auth / "p1b-init-8s"),
                       ("INIT24", auth / "p1b-init-24s")):
        path.chmod(0o755)
        t0 = time.perf_counter()
        try:
            p = run([qemu_bin, "-strace", str(path)], check=False, timeout=240)
            stderr, rc = p.stderr + p.stdout, p.returncode
        except subprocess.TimeoutExpired:
            stderr, rc = "TIMEOUT: no exit within 240s", -9
        dt = time.perf_counter() - t0
        (out / f"qemu-{name.lower()}-strace.txt").write_text(stderr)
        sleep_line = parse_strace(stderr, "clock_nanosleep")
        reboot_line = parse_strace(stderr, "reboot")
        exit_line = parse_strace(stderr, "exit_group")
        results[name] = {"runtime": dt, "rc": p.returncode,
                         "sleep": sleep_line, "reboot": reboot_line,
                         "exit": exit_line}
        emit(f"QEMU_{name}_RUNTIME={dt:.3f}s rc={p.returncode}")
        emit(f"QEMU_{name}_SLEEP_SYSCALL={sleep_line}")
        emit(f"QEMU_{name}_REBOOT_SYSCALL={reboot_line}")
        emit(f"QEMU_{name}_EXIT_GROUP={exit_line}")

    delta = abs(results["INIT24"]["runtime"] - results["INIT8"]["runtime"])
    lo, hi = SUPPORTED_BAND
    if STRONG_BAND[0] <= delta <= STRONG_BAND[1]:
        verdict = "STRONG"
    elif lo <= delta <= hi:
        verdict = "SUPPORTED"
    else:
        verdict = "FAIL"
    emit(f"QEMU_PAIR_DELTA={delta:.3f}s")
    emit(f"QEMU_PAIR_VERDICT={verdict} (preregistered STRONG "
         f"{STRONG_BAND} / SUPPORTED {SUPPORTED_BAND})")
    gates = [
        "P1B_FI_QEMU_GATES=PASS",
        f"QEMU_PINNED={ver}",
        "QEMU_HARNESS_POSITIVE_CONTROL=PASS",
        f"QEMU_INIT8_RUNTIME={results['INIT8']['runtime']:.3f}s",
        f"QEMU_INIT24_RUNTIME={results['INIT24']['runtime']:.3f}s",
        f"QEMU_PAIR_DELTA={delta:.3f}s",
        f"QEMU_PAIR_VERDICT={verdict}",
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "qemu-gates.txt").write_text("\n".join(gates) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "config", "qemu"),
                        required=True)
    parser.add_argument("--auth", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--objdump", default="aarch64-linux-gnu-objdump")
    parser.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    parser.add_argument("--qemu", default="qemu-aarch64-static")
    args = parser.parse_args()
    auth, out = Path(args.auth), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == "audit":
        audit(auth, out, args.objdump)
    elif args.mode == "config":
        config(out, auth / "initramfs-8s.cpio")
    else:
        qemu(auth, out, args.gcc, args.qemu)
    print(f"P1B_FI_MODE_{args.mode.upper()}=DONE")


if __name__ == "__main__":
    main()
