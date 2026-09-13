#!/usr/bin/env python3
"""R3 P1B init control fix: prove the FIXED /init ABI end to end.

GitHub Actions only. Modes:
  source-gate  static ABI/boundary checks over the fixed init source, the
               proof script, the public workflow and the fix doc
  audit        identity + disassembly ABI gates over the freshly built
               FIX8/FIX24 pair (4-arg clock_nanosleep, flags=0, req/rem slot
               assignment, live delay constant, EINTR retry, fail-closed
               exits, reboot ABI, pair semantic delta, cpio + payload
               containment, RT-D trailer, trampoline identity)
  negative     compile four broken fixtures (old 3-arg ABI, flags slot
               holding &req, dead rqtp, unchecked return) and prove the same
               audit checkers/QEMU runtime band REJECT each one
  qemu         pinned qemu-aarch64 user-mode execution of the exact FIX8 and
               FIX24 /init binaries with -strace: positive control, EINTR
               interruption fixture, per-binary strace ABI, requested
               duration, syscall return, wallclock bands and the preregistered
               pair delta (STRONG 15.5-16.5s, SUPPORTED 15.0-17.0s, else FAIL)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import time
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local audit/execution")

REPO = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
INIT_C = HERE / "p1b-init.c"
WF = REPO / ".github" / "workflows" / "thyme-r3-p1b-init-control-fix.yml"
DOC = REPO / "docs" / "route-r3-p1b-init-control-fix.md"

RT_D_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
RT_D_SIZE = 144593
RT_D_BOOTARGS = b"rdinit=/init panic=5 loglevel=7"
S_RESIDUE = 0x80000
ALIGN_2M = 0x200000
TRAMP_OFFSET = 0x40
CODE1_LE = b"\x0f\x00\x00\x14"  # b 0x40
DELAY_PAIR = (8, 24)

STRONG_BAND = (15.5, 16.5)
SUPPORTED_BAND = (15.0, 17.0)
RUNTIME_BAND = {8: (6.5, 9.5), 24: (22.5, 25.5)}

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
        fail("P1B_FIX_CMD_FAILED",
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
        fail("P1B_FIX_DISASM_FAILED", str(path))
    return lines


def write_disasm(out: Path, tag: str, lines: list[str]) -> None:
    (out / f"{tag}-disasm.txt").write_text("\n".join(lines) + "\n")


def _block(lines: list[str], start_pat: str, back: int) -> tuple[int, list[str]]:
    starts = [i for i, l in enumerate(lines)
              if re.search(start_pat, l)]
    if not starts:
        return -1, []
    start = starts[0]
    svc = next((i for i in range(start, len(lines))
                if re.search(r"\bsvc\b", lines[i])), None)
    if svc is None:
        return -1, []
    return start, lines[max(0, start - back):svc]


ZERO_X1 = (r"\bmov\s+[wx]1, [wx]zr\b", r"\b(movz|mov)\s+[wx]1, #(0x0|0)\b")


def init_abi_violations(lines: list[str], delay: int) -> list[str]:
    """Static 4-arg clock_nanosleep ABI audit. Returns violation labels."""
    v: list[str] = []
    start, block = _block(lines, r"\b(movz|mov)\s+[wx]8, #(0x73|115)\b", 16)
    if not block:
        return ["clock_nanosleep_block_missing"]
    joined = "\n".join(block)
    if not re.search(r"\b(movz|mov)\s+[wx]0, #(0x1|1)\b", joined):
        v.append("clockid_not_monotonic")
    if not any(re.search(p, joined) for p in ZERO_X1):
        v.append("flags_slot_not_zero")
    if re.search(r"\b(mov|add)\s+x1, (sp|x29)\b", joined):
        v.append("flags_slot_holds_pointer")
    if not re.search(r"\b(add|mov)\s+x2, (sp|x29)\b", joined):
        v.append("req_pointer_missing")
    if not re.search(r"\b(add|mov)\s+x3, (sp|x29)\b", joined):
        v.append("x3_not_set")
    imm = rf"\b(movz|mov)\s+[wx][0-9]+, #(0x{delay:x}|{delay})\b"
    if not re.search(imm, joined) or not re.search(r"\b(stp|str)\s+.*\[sp\b",
                                                   joined):
        v.append("delay_constant_not_live")
    if not re.search(r"\bcmn\s+x0, #(0x4|4)\b", "\n".join(lines)):
        v.append("eintr_retry_missing")
    if not re.search(r"\b(movz|mov)\s+[wx]0, #(0x6f|111)\b", "\n".join(lines)):
        v.append("sleep_fail_exit_missing")
    if not re.search(r"\b(movz|mov)\s+[wx]0, #(0x70|112)\b", "\n".join(lines)):
        v.append("reboot_fail_exit_missing")
    rstart, rblock = _block(lines, r"\b(movz|mov)\s+[wx]8, #(0x8e|142)\b", 14)
    if not rblock:
        v.append("reboot_block_missing")
    else:
        rj = "\n".join(rblock)
        for bad, label in (
            (r"\b(movz|mov)\s+[wx]0, #(0xdead|57005)\b", "reboot_magic1_low"),
            (r"\bmovk\s+[wx]0, #(0xfee1|65249), lsl #16\b", "reboot_magic1_high"),
            (r"\b(movz|mov)\s+[wx]1, #(0x1969|6505)\b", "reboot_magic2_low"),
            (r"\bmovk\s+[wx]1, #(0x2812|10258), lsl #16\b", "reboot_magic2_high"),
            (r"\b(movz|mov)\s+[wx]2, #(0x4567|17767)\b", "reboot_cmd_low"),
            (r"\bmovk\s+[wx]2, #(0x123|291), lsl #16\b", "reboot_cmd_high"),
            (r"\bmov\s+x3, [wx]zr\b", "reboot_arg3_not_zero"),
        ):
            if not re.search(bad, rj):
                v.append(label)
    return v


def parse_cpio(data: bytes) -> list[dict]:
    entries, off = [], 0
    while off + 6 <= len(data):
        if data[off:off + 6] not in (b"070701", b"070702"):
            fail("P1B_FIX_CPIO_FAILED", f"magic at {off:#x}")
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
        fail("P1B_FIX_CPIO_FAILED", "no trailer")
    return entries


def pair_identity(auth: Path, out: Path) -> dict[str, bytes]:
    names = {
        "init8": "p1b-init-fix8", "init24": "p1b-init-fix24",
        "cpio8": "initramfs-fix8.cpio", "cpio24": "initramfs-fix24.cpio",
        "pay8": "thyme-r3-p1b-fix8-kernel-payload.bin",
        "pay24": "thyme-r3-p1b-fix24-kernel-payload.bin",
    }
    paths = {k: auth / n for k, n in names.items()}
    for p in paths.values():
        if not p.is_file() or p.stat().st_size == 0:
            fail("P1B_FIX_PAIR_MISSING", str(p))
    sums = run(["sha256sum", "-c", "SHA256SUMS"], cwd=auth)
    (out / "sha256sums-check.txt").write_text(sums.stdout + sums.stderr)
    emit("FIXED_PAIR_SHA256SUMS_MATCH=PASS")
    b = {k: p.read_bytes() for k, p in paths.items()}
    return b


def containment(b: dict[str, bytes], out: Path) -> None:
    for tag, ikey, ckey, pkey in (("fix8", "init8", "cpio8", "pay8"),
                                  ("fix24", "init24", "cpio24", "pay24")):
        es = parse_cpio(b[ckey])
        names = [e["name"] for e in es]
        if names != ["dev", "init", "proc", "sys"]:
            fail("P1B_FIX_CPIO_FAILED", f"{tag}: {names}")
        ini = es[1]
        if ini["mode"] != 0o100755 or ini["uid"] or ini["gid"]:
            fail("P1B_FIX_CPIO_FAILED", f"{tag}: mode/uid/gid")
        if ini["filesize"] != len(b[ikey]) or ini["data"] != b[ikey]:
            fail("P1B_FIX_CPIO_FAILED", f"{tag}: data != /init binary")
        pay = b[pkey]
        if pay.count(b[ckey]) != 1:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: cpio occurrences != 1")
        if pay.count(b[ikey]) != 1:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: /init occurrences != 1")
        if sha(pay[-RT_D_SIZE:]) != RT_D_SHA:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: RT-D trailer")
        dtb_offset = len(pay) - RT_D_SIZE
        if (S_RESIDUE + dtb_offset) % ALIGN_2M:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: DTB geometry")
        if pay[dtb_offset:dtb_offset + 4] != b"\xd0\x0d\xfe\xed":
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: FDT magic")
        if RT_D_BOOTARGS not in pay[dtb_offset:]:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: bootargs")
        if pay[4:8] != CODE1_LE:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: code1 not b 0x40")
        emit(f"FIXED_{tag.upper()}_CPIO_PAYLOAD_RT_D_CONTAINMENT=PASS "
             f"(payload {len(pay)} B, DTB_OFFSET {dtb_offset:#x})")
    other = {"fix8": "cpio24", "fix24": "cpio8"}
    for tag, ckey, pkey in (("fix8", "cpio8", "pay8"),
                            ("fix24", "cpio24", "pay24")):
        if b[other[tag]] in b[pkey]:
            fail("P1B_FIX_EMBED_FAILED", f"{tag}: wrong-delay cpio embedded")
    if len(b["pay8"]) != len(b["pay24"]):
        fail("P1B_FIX_PAIR_FAILED", "payload sizes differ")
    tramp8 = b["pay8"][TRAMP_OFFSET:TRAMP_OFFSET + 48]
    tramp24 = b["pay24"][TRAMP_OFFSET:TRAMP_OFFSET + 48]
    if tramp8 != tramp24:
        fail("P1B_FIX_PAIR_FAILED", "trampoline bytes differ between pair")
    emit("FIXED_PAIR_GEOMETRY_IDENTICAL=YES "
         "(payload size, code1 b 0x40, trampoline bytes, RT-D trailer)")


def audit(auth: Path, out: Path, objdump: str) -> None:
    b = pair_identity(auth, out)

    dis = {"fix8": disasm_lines(objdump, auth / "p1b-init-fix8"),
           "fix24": disasm_lines(objdump, auth / "p1b-init-fix24")}
    write_disasm(out, "fix8", dis["fix8"])
    write_disasm(out, "fix24", dis["fix24"])

    containment(b, out)

    for tag, delay in (("fix8", 8), ("fix24", 24)):
        v = init_abi_violations(dis[tag], delay)
        if v:
            fail("P1B_FIX_INIT_ABI_FAILED", f"{tag}: {v}")
        emit(f"FIXED_{tag.upper()}_CLOCK_NANOSLEEP_ABI=PASS "
             f"(4-arg: x0=CLOCK_MONOTONIC x1=0 x2=&req x3=&rem)")
        emit(f"FIXED_{tag.upper()}_RETURN_HANDLING=PASS "
             f"(EINTR retry, exit_group(111) sleep failure, "
             f"exit_group(112) reboot returned)")
        emit(f"DELAY_CONSTANT_IS_LIVE=YES ({tag}: {delay}s -> req.tv_sec)")
    emit("FIXED_INIT_REBOOT_ABI=PASS (magic1 0xfee1dead, magic2 0x28121969, "
         "cmd 0x01234567, arg x3=0)")

    d8, d24 = dis["fix8"], dis["fix24"]
    diffs = [(a, x) for a, x in zip(d8, d24) if a != x]
    if len(d8) != len(d24) or not 1 <= len(diffs) <= 4:
        fail("P1B_FIX_SEMANTIC_DELTA",
             f"{len(d8)} vs {len(d24)} lines, diffs={len(diffs)}")
    for a, x in diffs:
        norm = lambda s: re.sub(
            r"\s+", " ",
            re.sub(r"#-?(0x[0-9a-f]+|\d+)", "#",
                   re.sub(r"^[0-9a-f]+\s+", "", s)))
        if norm(a) != norm(x):
            fail("P1B_FIX_SEMANTIC_DELTA", f"{a!r} vs {x!r}")
    (out / "fixed-init-pair-diff.txt").write_text(
        "\n".join(f"- {a}\n+ {x}" for a, x in diffs) + "\n")
    emit(f"FIXED_INIT_INSTRUCTION_DIFFS={len(diffs)} ({diffs})")
    if b"THYME-R3-P1B-INIT ABI4 DELAY=08" not in b["init8"] or \
            b"THYME-R3-P1B-INIT ABI4 DELAY=24" not in b["init24"]:
        fail("P1B_FIX_SEMANTIC_DELTA", "ident strings")
    emit("P1B_FIXED_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY "
         "(instruction diff + rodata ident 08/24)")

    gates = [
        "P1B_FIX_AUDIT_GATES=PASS",
        "FIXED_INIT_CLOCK_NANOSLEEP_ABI=4ARG_FLAGS0_REQ_REM",
        "DELAY_CONSTANT_IS_LIVE=YES",
        "FIXED_INIT_RETURN_HANDLING=FAIL_CLOSED_EINTR_RETRY",
        "P1B_FIXED_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY",
        "FIXED_PAIR_GEOMETRY_IDENTICAL=YES",
        "RT_D_SHA=" + RT_D_SHA,
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "audit-gates.txt").write_text("\n".join(gates) + "\n")


QEMU_GCC_FLAGS = ["-ffreestanding", "-nostdlib", "-static", "-no-pie",
                  "-fno-pic", "-fno-stack-protector",
                  "-fno-asynchronous-unwind-tables", "-Os",
                  "-Wl,--build-id=none"]

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

EINTR_FIXTURE_C = r"""/* EINTR interruption fixture: ITIMER_REAL fires SIGALRM 1s into a 4s
 * relative clock_nanosleep. Proves the raw syscall returns -EINTR with the
 * remaining interval and that a retry completes the full requested delay.
 */
#define SYS_rt_sigaction 134
#define SYS_rt_sigreturn 139
#define SYS_setitimer 103
#define SYS_clock_nanosleep 115
#define SYS_exit_group 94
#define CLOCK_MONOTONIC 1
#define EINTR 4
#define SIGALRM 14
#define SA_RESTORER 0x04000000
#define ITIMER_REAL 0
#define SLEEP_SECONDS 4
#define ALARM_SECONDS 1
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
static volatile int got_signal;
static void handler(int sig) { (void)sig; got_signal = 1; }
void sig_restore(void);
__asm__ (".text\n.globl sig_restore\nsig_restore:\n"
	 "	mov	x8, #139\n"
	 "	svc	#0\n");
struct ts { long tv_sec; long tv_nsec; };
struct ksa {
	void (*handler)(int);
	unsigned long flags;
	void (*restorer)(void);
	unsigned long mask;
};
struct itimerval {
	struct { long tv_sec; long tv_usec; } it_interval, it_value;
};
void _start(void)
{
	struct ksa sa = { handler, SA_RESTORER, sig_restore, 0 };
	struct itimerval it = { { 0, 0 }, { ALARM_SECONDS, 0 } };
	struct ts req = { SLEEP_SECONDS, 0 };
	struct ts rem = { 0, 0 };
	long r;

	sys4(SYS_rt_sigaction, SIGALRM, (long)&sa, 0, 8);
	sys4(SYS_setitimer, ITIMER_REAL, (long)&it, 0, 0);
	r = sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0,
		 (long)&req, (long)&rem);
	if (r == 0)
		sys4(SYS_exit_group, 124, 0, 0, 0); /* no interruption: broken */
	if (r != -EINTR)
		sys4(SYS_exit_group, 120, 0, 0, 0);
	if (!got_signal)
		sys4(SYS_exit_group, 121, 0, 0, 0);
	if (rem.tv_sec < 1 || rem.tv_sec > SLEEP_SECONDS - 1)
		sys4(SYS_exit_group, 122, 0, 0, 0);
	req = rem;
	r = sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0,
		 (long)&req, (long)&rem);
	if (r != 0)
		sys4(SYS_exit_group, 123, 0, 0, 0);
	sys4(SYS_exit_group, 0, 0, 0, 0);
	for (;;)
		;
}
"""

NF_TEMPLATES: dict[str, str] = {
    # exact old-bug replica: 3-arg clock_nanosleep call
    "nf1-sys3-old-abi": r"""
#define SYS_clock_nanosleep 115
#define SYS_exit_group 94
#define SYS_reboot 142
#define CLOCK_MONOTONIC 1
#define EINTR 4
static long sys3(long nr, long a0, long a1, long a2)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	__asm__ volatile ("svc #0" : "+r"(x0)
			  : "r"(x8), "r"(x1), "r"(x2) : "memory", "cc");
	return x0;
}
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
	struct ts req = { 8, 0 };
	struct ts rem = { 0, 0 };
	long r;
	while (sys3(SYS_clock_nanosleep, CLOCK_MONOTONIC, (long)&req,
		    (long)&rem) == -EINTR)
		req = rem;
	r = sys4(SYS_reboot, 0xfee1dead, 672274793, 0x01234567, 0);
	sys4(SYS_exit_group, 112, 0, 0, 0);
	(void)r;
	for (;;)
		;
}
""",
    # 4-arg call but flags slot holds &req
    "nf2-flags-slot-pointer": r"""
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
	struct ts req = { 8, 0 };
	struct ts rem = { 0, 0 };
	sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, (long)&req,
	     (long)&req, (long)&rem);
	sys4(SYS_exit_group, 0, 0, 0, 0);
	for (;;)
		;
}
""",
    # 4-arg ABI, full retry/fail-closed structure, but rqtp = &rem (zeroed):
    # disasm-clean by construction, only the runtime band can reject it
    "nf3-dead-rqtp": r"""
#define SYS_clock_nanosleep 115
#define SYS_exit_group 94
#define SYS_reboot 142
#define CLOCK_MONOTONIC 1
#define EINTR 4
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
	struct ts req = { 8, 0 };
	struct ts rem = { 0, 0 };
	long r;
	for (;;) {
		r = sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0,
			 (long)&rem, (long)&req);
		if (r == 0)
			break;
		if (r != -EINTR)
			for (;;)
				sys4(SYS_exit_group, 111, 0, 0, 0);
		req = rem;
	}
	r = sys4(SYS_reboot, 0xfee1dead, 672274793, 0x01234567, 0);
	(void)r;
	for (;;)
		sys4(SYS_exit_group, 112, 0, 0, 0);
}
""",
    # correct 4-arg call, return value unchecked, straight to reboot
    "nf4-unchecked-return": r"""
#define SYS_clock_nanosleep 115
#define SYS_exit_group 94
#define SYS_reboot 142
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
	struct ts req = { 8, 0 };
	struct ts rem = { 0, 0 };
	sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0, (long)&req, (long)&rem);
	sys4(SYS_reboot, 0xfee1dead, 672274793, 0x01234567, 0);
	sys4(SYS_exit_group, 112, 0, 0, 0);
	for (;;)
		;
}
""",
}


def compile_fixture(out: Path, name: str, source: str, gcc: str,
                    entry: str = "_start") -> Path:
    src = out / f"{name}.c"
    src.write_text(source)
    elf = out / name
    run([gcc, *QEMU_GCC_FLAGS, f"-Wl,-e,{entry}", "-o", str(elf), str(src)])
    elf.chmod(0o755)
    return elf


def qemu_run(qemu_bin: str, path: Path, timeout: int = 240,
             strace: bool = True) -> tuple[float, int, str]:
    cmd = [qemu_bin] + (["-strace"] if strace else []) + [str(path)]
    t0 = time.perf_counter()
    try:
        p = run(cmd, check=False, timeout=timeout)
        text, rc = p.stderr + p.stdout, p.returncode
    except subprocess.TimeoutExpired:
        text, rc = "TIMEOUT: no exit within timeout", -9
    dt = time.perf_counter() - t0
    return dt, rc, text


def qemu(auth: Path, out: Path, gcc: str, qemu_bin: str) -> None:
    ver = run([qemu_bin, "--version"]).stdout.splitlines()[0]
    if not re.search(r"version 8\.\d", ver):
        fail("P1B_FIX_QEMU_FAILED", f"unpinned qemu: {ver}")
    emit(f"QEMU_PINNED={ver}")

    # identity re-check: the binaries executed must be the /init bytes embedded
    # in the freshly built pair payloads (exact-binary requirement)
    b = pair_identity(auth, out)
    containment(b, out)
    emit("QEMU_EXACT_BINARY_IDENTITY=PASS (executed bytes == cpio /init == "
         "payload-embedded)")

    ctl = compile_fixture(out, "qemu-positive-control", QEMU_CONTROL_C, gcc)
    dt, rc, text = qemu_run(qemu_bin, ctl)
    (out / "qemu-positive-control-strace.txt").write_text(text)
    line = next((l for l in text.splitlines() if "clock_nanosleep" in l), "")
    if "CLOCK_MONOTONIC,0,{tv_sec = 2,tv_nsec = 0}" not in line \
            or not line.rstrip().endswith("= 0"):
        fail("P1B_FIX_QEMU_FAILED", f"positive control strace: {line}")
    if not (1.0 <= dt <= 4.5) or rc != 0:
        fail("P1B_FIX_QEMU_FAILED", f"positive control {dt:.3f}s rc={rc}")
    emit(f"QEMU_HARNESS_POSITIVE_CONTROL=PASS ({dt:.3f}s, 4-arg flags=0 "
         f"tv_sec=2 returned 0)")

    eintr = compile_fixture(out, "qemu-eintr-fixture", EINTR_FIXTURE_C, gcc)
    dt, rc, text = qemu_run(qemu_bin, eintr)
    (out / "qemu-eintr-fixture-strace.txt").write_text(text)
    if rc != 0:
        fail("P1B_FIX_QEMU_FAILED",
             f"EINTR fixture rc={rc} (120 no-EINTR / 121 no-signal / "
             f"122 bad remaining / 123 retry failed / 124 unbroken sleep)")
    if not (3.0 <= dt <= 7.0):
        fail("P1B_FIX_QEMU_FAILED", f"EINTR fixture runtime {dt:.3f}s")
    if not re.search(r"errno=4\b", text):
        fail("P1B_FIX_QEMU_FAILED", "no interrupted clock_nanosleep in strace")
    emit(f"QEMU_EINTR_FIXTURE=PASS ({dt:.3f}s, -EINTR observed with "
         f"remaining interval, retry completed full delay)")

    results = {}
    for tag, delay, key in (("fix8", 8, "init8"), ("fix24", 24, "init24")):
        path = auth / f"p1b-init-{tag}"
        dt, rc, text = qemu_run(qemu_bin, path)
        (out / f"qemu-{tag}-strace.txt").write_text(text)
        line = next((l for l in text.splitlines()
                     if "clock_nanosleep" in l), "")
        body = line.split(" ", 1)[-1].strip() if line else ""
        want = (f"clock_nanosleep(CLOCK_MONOTONIC,0,"
                f"{{tv_sec = {delay},tv_nsec = 0}}")
        strace_ok = body.startswith(want) and body.rstrip().endswith("= 0")
        reboot_line = next((l for l in text.splitlines()
                            if "reboot(" in l), "")
        exit_line = next((l for l in text.splitlines()
                          if "exit_group" in l), "")
        lo, hi = RUNTIME_BAND[delay]
        runtime_ok = lo <= dt <= hi
        return_ok = rc == 112 and "errno=1" in reboot_line \
            and "exit_group(112)" in exit_line
        results[tag] = {"runtime": dt, "rc": rc, "strace": body,
                        "strace_ok": strace_ok, "runtime_ok": runtime_ok,
                        "return_ok": return_ok}
        (out / f"qemu-{tag}-strace-line.txt").write_text(body + "\n")
        emit(f"QEMU_{tag.upper()}_BINARY_SHA={sha(b[key])}")
        emit(f"QEMU_{tag.upper()}_STRACE={body}")
        emit(f"QEMU_{tag.upper()}_REBOOT={reboot_line.strip()}")
        emit(f"QEMU_{tag.upper()}_EXIT_GROUP={exit_line.strip()}")
        emit(f"QEMU_{tag.upper()}_RUNTIME={dt:.3f}s rc={rc}")
        emit(f"QEMU_{tag.upper()}_STRACE_ABI={'PASS' if strace_ok else 'FAIL'}")
        emit(f"QEMU_{tag.upper()}_REQUESTED_DURATION="
             f"{'PASS' if strace_ok and runtime_ok else 'FAIL'}")
        emit(f"QEMU_{tag.upper()}_SYSCALL_RETURN="
             f"{'PASS' if return_ok else 'FAIL'}")
        emit(f"QEMU_{tag.upper()}_WALLCLOCK="
             f"{'PASS' if runtime_ok else 'FAIL'}")

    delta = abs(results["fix24"]["runtime"] - results["fix8"]["runtime"])
    if STRONG_BAND[0] <= delta <= STRONG_BAND[1]:
        verdict = "STRONG"
    elif SUPPORTED_BAND[0] <= delta <= SUPPORTED_BAND[1]:
        verdict = "SUPPORTED"
    else:
        verdict = "FAIL"
    emit(f"QEMU_FIXED_PAIR_DELTA={delta:.3f}s")
    emit(f"QEMU_FIXED_PAIR_VERDICT={verdict} (preregistered STRONG "
         f"{STRONG_BAND} / SUPPORTED {SUPPORTED_BAND})")

    all_ok = (all(results[t]["strace_ok"] and results[t]["runtime_ok"]
                  and results[t]["return_ok"] for t in ("fix8", "fix24"))
              and verdict != "FAIL")
    gates = [
        "P1B_FIX_QEMU_GATES=PASS" if all_ok else "P1B_FIX_QEMU_GATES=FAIL",
        f"QEMU_PINNED={ver}",
        "QEMU_HARNESS_POSITIVE_CONTROL=PASS",
        "QEMU_EINTR_FIXTURE=PASS",
        "QEMU_EXACT_BINARY_IDENTITY=PASS",
        f"QEMU_FIX8_RUNTIME={results['fix8']['runtime']:.3f}s",
        f"QEMU_FIX24_RUNTIME={results['fix24']['runtime']:.3f}s",
        f"QEMU_FIXED_PAIR_DELTA={delta:.3f}s",
        f"QEMU_FIXED_PAIR_VERDICT={verdict}",
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "qemu-gates.txt").write_text("\n".join(gates) + "\n")
    if not all_ok:
        fail("P1B_FIX_QEMU_GATES_FAILED", f"delta={delta:.3f}s verdict={verdict}")


def negative(out: Path, gcc: str, qemu_bin: str) -> None:
    cases = [
        ("nf1-sys3-old-abi", ["x3_not_set", "flags_slot_not_zero"]),
        ("nf2-flags-slot-pointer", ["flags_slot_not_zero"]),
        ("nf4-unchecked-return", ["eintr_retry_missing",
                                  "sleep_fail_exit_missing"]),
    ]
    for name, expected in cases:
        elf = compile_fixture(out, name, NF_TEMPLATES[name], gcc)
        v = init_abi_violations(disasm_lines("aarch64-linux-gnu-objdump", elf),
                                8)
        missing = [e for e in expected if e not in v]
        if missing:
            fail("P1B_FIX_NEGATIVE_FAILED", f"{name}: not rejected ({missing})")
        emit(f"NEGATIVE_FIXTURE_REJECT={name} (violations {sorted(set(v) & set(expected))})")
    # nf3 is disasm-clean by construction: only the runtime band rejects it
    elf = compile_fixture(out, "nf3-dead-rqtp", NF_TEMPLATES["nf3-dead-rqtp"],
                          gcc)
    v = init_abi_violations(disasm_lines("aarch64-linux-gnu-objdump", elf), 8)
    if v:
        fail("P1B_FIX_NEGATIVE_FAILED",
             f"nf3 expected disasm-clean, got {v}")
    dt, rc, _ = qemu_run(qemu_bin, elf, timeout=60)
    if 6.5 <= dt:
        fail("P1B_FIX_NEGATIVE_FAILED",
             f"nf3 slept {dt:.3f}s — runtime band failed to reject dead rqtp")
    emit(f"NEGATIVE_FIXTURE_REJECT=nf3-dead-rqtp (disasm-clean, runtime "
         f"{dt:.3f}s outside [6.5, 9.5] -> REJECT)")
    gates = [
        "P1B_FIX_NEGATIVE_GATES=PASS",
        "NEGATIVE_SYS3_OLD_ABI=REJECT",
        "NEGATIVE_FLAGS_SLOT_POINTER=REJECT",
        "NEGATIVE_DEAD_RQTP=REJECT_RUNTIME_ONLY",
        "NEGATIVE_UNCHECKED_RETURN=REJECT",
        "DEVICE_OPERATION=NO",
        "READY_FOR_DEVICE=NO",
    ]
    (out / "negative-gates.txt").write_text("\n".join(gates) + "\n")


def source_gate(_args: argparse.Namespace) -> None:
    for path in (INIT_C, WF, DOC, Path(__file__),
                 HERE / "p1b-build.py", HERE / "p1b-init.ld",
                 HERE / "p1b-trampoline.S"):
        if not path.is_file() or path.stat().st_size == 0:
            fail("P1B_FIX_SOURCE_GATE_FAILED", f"missing {path}")
    init_c = INIT_C.read_text()
    wf = WF.read_text()
    doc = DOC.read_text()
    for token in ("sys4(SYS_clock_nanosleep, CLOCK_MONOTONIC, 0,",
                  "(long)&req, (long)&rem)", "EXIT_SLEEP_FAILED",
                  "EXIT_REBOOT_RETURNED", "THYME-R3-P1B-INIT ABI4 DELAY="):
        if token not in init_c:
            fail("P1B_FIX_SOURCE_GATE_FAILED", f"init missing {token}")
    if re.search(r"\bsys3\b", init_c):
        fail("P1B_FIX_SOURCE_GATE_FAILED", "init must not use 3-arg wrapper")
    for token in (
        "BROKEN_3_ARG", "OLD_INIT_DELAY_CONTROL_BROKEN=YES",
        "FIXED_4ARG", "EINTR", "exit_group(111)", "exit_group(112)",
        "15.5", "16.5", "15.0", "17.0", "6.6.156",
        "8b73de7da85fde281a385e0b26eda9bffd3ca477",
        "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327",
        "DELAY_CONSTANT_ONLY", "FIXED_INIT8_PROVISIONAL_SIGNATURE",
        "PANIC30", "FROZEN", "MAINLINE_V2_R3_P1B_FIXED_INIT8_TRUE_DEVICE_CONTROL",
        "thyme-r3-p1b-fix8-fix24",
    ):
        if token not in doc:
            fail("P1B_FIX_SOURCE_GATE_FAILED", f"doc missing {token}")
    if re.search(r"^\s+run:.*\b(fastboot|adb)\b", wf, re.M):
        fail("P1B_FIX_SOURCE_GATE_FAILED", "public workflow has device verbs")
    if "splice-boot" in wf or "mkbootimg" in wf:
        fail("P1B_FIX_SOURCE_GATE_FAILED", "public workflow packs boot images")
    if "DEVICE_OPERATION=NO" not in wf:
        fail("P1B_FIX_SOURCE_GATE_FAILED", "workflow boundary marker")
    print("P1B_FIX_SOURCE_GATE=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(
        "source-gate", "audit", "negative", "qemu"), required=True)
    parser.add_argument("--auth")
    parser.add_argument("--out", default="out-r3-p1b-fix")
    parser.add_argument("--objdump", default="aarch64-linux-gnu-objdump")
    parser.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    parser.add_argument("--qemu", default="qemu-aarch64-static")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == "source-gate":
        source_gate(args)
    elif args.mode == "audit":
        audit(Path(args.auth), out, args.objdump)
    elif args.mode == "negative":
        negative(out, args.gcc, args.qemu)
    else:
        qemu(Path(args.auth), out, args.gcc, args.qemu)
    print(f"P1B_FIX_MODE_{args.mode.upper()}=DONE")


if __name__ == "__main__":
    main()
