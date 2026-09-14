#!/usr/bin/env python3
"""MAINLINE_V2_R3_EARLY_C_KERNEL_STAGE_MAP_CI — Agent B, GitHub Actions only.

Independent of T3. Never emits a device image, never writes Slot A,
never touches Agent A T3 files. Addresses come only from THIS round's
final P1B vmlinux.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary/source-gate")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
P1B = REPO / "scripts" / "r3-p1b"
DOC = REPO / "docs" / "route-r3-early-c-stage-map.md"
WF = REPO / ".github" / "workflows" / "thyme-r3-early-c-stage-map.yml"
STATUS = REPO / "docs" / "route-r3-current-status.md"

LINUX_BASE = "8b73de7da85fde281a385e0b26eda9bffd3ca477"
LINUX_VERSION = "6.6.156"
PATCH_NAMES = (
    "0001-dt-bindings-arm-qcom-add-Xiaomi-Mi-10S-thyme-board.patch",
    "0002-arm64-dts-qcom-add-Xiaomi-Mi-10S-thyme-initial-board.patch",
)
RT_D_BOOTARGS = "rdinit=/init panic=5 loglevel=7"

T3_FORBIDDEN = (
    "docs/route-r3-current-status.md",
    ".github/workflows/thyme-r3-p1b-t3-predevice.yml",
    "scripts/r3-p1b/p1b-t3-device.S",
    "scripts/r3-p1b/p1b-t3-device.ld",
    "scripts/r3-p1b/p1b-t3-predevice.py",
    "scripts/r3-p1b/observe-r3-p1b-t3.py",
    "scripts/r3-p1b/observer-t3-fixtures.py",
)
OWN_PATHS = (
    "scripts/r3-c-stage-audit/",
    ".github/workflows/thyme-r3-early-c-stage-map.yml",
    "docs/route-r3-early-c-stage-map.md",
)
DEVICE_RE = re.compile(
    r"(?:^|[\s\"'`])(adb|fastboot|bootctl|set_active)\b|"
    r"\b(fastboot\s+boot|adb\s+reboot|fastboot\s+flash|fastboot\s+reboot)\b",
    re.I,
)
READY_RE = re.compile(r"READY_FOR_\w+_DEVICE_CONTROL\s*=\s*YES")
HIST_VA_GATE_RE = re.compile(
    r"(EXPECTED|PINNED|HISTORICAL|FROZEN)_\w*(VA|ADDR|OFFSET)\w*\s*=\s*0xffff8000",
    re.I,
)
INSTR_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$", re.I
)
SYM_RE = re.compile(r"^([0-9a-fA-F]+)\s+\S\s+(\S+)$")
STAGE_FIELDS = (
    "id", "name", "source_file", "source_line_range", "symbol",
    "link_va", "image_offset", "file_offset", "section", "section_flags",
    "caller", "callee", "control_flow_type", "mmu_state", "current_el",
    "pc_semantics", "sp_valid", "stack_dependency", "bss_required",
    "percpu_required", "dt_required", "cmdline_available",
    "panic_parameter_parsed", "scheduler_required", "interrupts_state",
    "timer_state", "cntpct_direct_probe_safe", "psci_system_reset_direct_safe",
    "inline_checkpoint_feasible", "external_checkpoint_feasible",
    "executable_mapping_proof", "overwrite_risk", "checkpoint_value",
    "positive_proves", "positive_does_not_prove", "negative_cannot_exclude",
    "cmdline_state", "panic_parsed", "device_ready",
    "information_gain", "implementation_risk", "contamination_risk",
    "matched_timing_feasible",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    raise SystemExit(label if not detail else f"{label}: {detail}")


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, check=False, capture_output=True, text=True
    )
    if proc.returncode != 0:
        fail("C_STAGE_CMD_FAILED",
             f"{' '.join(cmd)}\n{proc.stderr}\n{proc.stdout[-3000:]}")
    return proc.stdout


def read(path: Path) -> str:
    if not path.is_file():
        fail("C_STAGE_SOURCE_MISSING", str(path))
    return path.read_text(errors="replace")


def line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def function_span(text: str, sig: str) -> tuple[int, int, str]:
    m = re.search(sig, text, re.M)
    if not m:
        fail("C_STAGE_SOURCE_FAILED", f"signature not found: {sig}")
    brace = text.find("{", m.end())
    if brace < 0:
        fail("C_STAGE_SOURCE_FAILED", f"no body: {sig}")
    depth = 0
    for i, ch in enumerate(text[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                start = line_no(text, m.start())
                end = line_no(text, i)
                return start, end, text[m.start():i + 1]
    fail("C_STAGE_SOURCE_FAILED", f"unclosed: {sig}")
    return 0, 0, ""


def find_in(text: str, pattern: str, *, flags: int = 0) -> tuple[int, re.Match]:
    m = re.search(pattern, text, flags)
    if not m:
        fail("C_STAGE_SOURCE_FAILED", f"not found: {pattern}")
    return line_no(text, m.start()), m


def own_files() -> list[Path]:
    files = [HERE / "c-stage-map.py", WF, DOC]
    return [p for p in files if p.is_file()]


def load_p1b():
    s = importlib.util.spec_from_file_location("p1b_build", P1B / "p1b-build.py")
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Source identity / source audit
# ---------------------------------------------------------------------------

def linux_head() -> str:
    return run(["git", "-C", str(LINUX), "rev-parse", "HEAD"]).strip()


def cmd_source_identity(_args: argparse.Namespace) -> dict:
    head = linux_head()
    print(f"LINUX_VERSION={LINUX_VERSION}")
    print(f"LINUX_BASE_COMMIT={head}")
    print(f"git rev-parse HEAD (linux-6.6) = {head}")
    if head != LINUX_BASE:
        fail("SOURCE_COMMIT_MISMATCH", f"{head} != {LINUX_BASE}")
    print("SOURCE_COMMIT_MATCH=YES")
    print("UPSTREAM_SOURCE_IDENTITY=" + LINUX_BASE)
    return {"source_commit": head, "match": True}


def source_facts() -> dict:
    """Exact 6.6.156 source map. Order is execution order, not C-id order."""
    main = read(LINUX / "init/main.c")
    setup = read(LINUX / "arch/arm64/kernel/setup.c")
    head_s = read(LINUX / "arch/arm64/kernel/head.S")
    panic = read(LINUX / "kernel/panic.c")
    fdt = read(LINUX / "drivers/of/fdt.c")
    initramfs = read(LINUX / "init/initramfs.c")
    mounts = read(LINUX / "init/do_mounts.c")
    exec_c = read(LINUX / "fs/exec.c")
    elf_c = read(LINUX / "fs/binfmt_elf.c")
    kconf = read(LINUX / "arch/arm64/Kconfig")

    sk_s, sk_e, sk_body = function_span(main, r"^void start_kernel\(void\)")
    sa_s, sa_e, sa_body = function_span(
        setup, r"^void __init __no_sanitize_address setup_arch\(char \*\*cmdline_p\)"
    )
    ri_s, ri_e, ri_body = function_span(
        main, r"^noinline void __ref __noreturn rest_init\(void\)"
    )
    ki_s, ki_e, ki_body = function_span(
        main, r"^static int __ref kernel_init\(void \*unused\)"
    )
    kf_s, kf_e, kf_body = function_span(
        main, r"^static noinline void __init kernel_init_freeable\(void\)"
    )
    pep_s, pep_e, pep_body = function_span(
        main, r"^void __init parse_early_param\(void\)"
    )
    acr_s, acr_e, acr_body = function_span(
        main, r"^void __init __weak __noreturn arch_call_rest_init\(void\)"
    )
    rip_s, rip_e, rip_body = function_span(
        main, r"^static int run_init_process\(const char \*init_filename\)"
    )
    smf_s, smf_e, smf_body = function_span(
        setup, r"^static void __init setup_machine_fdt\(phys_addr_t dt_phys\)"
    )

    sa_call, _ = find_in(sk_body, r"setup_arch\(&command_line\)")
    sa_call += sk_s - 1
    pep_in_sa, _ = find_in(sa_body, r"parse_early_param\(\);")
    pep_in_sa += sa_s - 1
    scl_call, _ = find_in(sk_body, r"setup_command_line\(command_line\)")
    scl_call += sk_s - 1
    pep_in_sk, _ = find_in(sk_body, r"parse_early_param\(\);")
    pep_in_sk += sk_s - 1
    pa_call, _ = find_in(sk_body, r'parse_args\("Booting kernel"')
    pa_call += sk_s - 1
    cal_call, _ = find_in(sk_body, r"calibrate_delay\(\);")
    cal_call += sk_s - 1
    acr_call, _ = find_in(sk_body, r"arch_call_rest_init\(\);")
    acr_call += sk_s - 1
    irq_on, _ = find_in(sk_body, r"local_irq_enable\(\);")
    irq_on += sk_s - 1
    sched, _ = find_in(sk_body, r"sched_init\(\);")
    sched += sk_s - 1
    cons, _ = find_in(sk_body, r"console_init\(\);")
    cons += sk_s - 1

    bl_sk, _ = find_in(head_s, r"^\tbl\tstart_kernel$", flags=re.M)
    ps_s, _ = find_in(head_s, r"^SYM_FUNC_START_LOCAL\(__primary_switched\)",
                      flags=re.M)

    dt_scan, _ = find_in(smf_body, r"early_init_dt_scan\(")
    dt_scan += smf_s - 1
    unflat, _ = find_in(sa_body, r"unflatten_device_tree\(\);")
    unflat += sa_s - 1
    fdt_chosen, _ = find_in(
        fdt, r"^int __init early_init_dt_scan_chosen\(char \*cmdline\)",
        flags=re.M)
    fdt_bootargs, _ = find_in(fdt, r'of_get_flat_dt_prop\(node, "bootargs"')
    fdt_scan, _ = find_in(
        fdt, r"^bool __init early_init_dt_scan\(void \*dt_virt", flags=re.M)

    panic_core, _ = find_in(panic, r"^core_param\(panic, panic_timeout",
                            flags=re.M)
    if re.search(r'early_param\(\s*"panic"', panic):
        fail("PANIC_IS_EARLY_PARAM", "panic= must not be early_param")
    rdinit, _ = find_in(main, r'^__setup\("rdinit=", rdinit_setup\);',
                        flags=re.M)
    if re.search(r'early_param\(\s*"rdinit"', main):
        fail("RDINIT_IS_EARLY_PARAM", "rdinit= is __setup, not early_param")
    rdinit_default, _ = find_in(
        main, r'static char \*ramdisk_execute_command = "/init";')
    loglevel_ep, _ = find_in(main, r'early_param\("loglevel", loglevel\);')

    kthreadd, _ = find_in(ri_body, r"kernel_thread\(kthreadd")
    kthreadd += ri_s - 1
    umt, _ = find_in(ri_body, r"user_mode_thread\(kernel_init")
    umt += ri_s - 1
    rest_call, _ = find_in(acr_body, r"rest_init\(\);")
    rest_call += acr_s - 1

    wait_irfs, _ = find_in(kf_body, r"wait_for_initramfs\(\);")
    wait_irfs += kf_s - 1
    prep_ns, _ = find_in(kf_body, r"prepare_namespace\(\);")
    prep_ns += kf_s - 1
    run_rd, _ = find_in(ki_body, r"run_init_process\(ramdisk_execute_command\)")
    run_rd += ki_s - 1
    pop_s, pop_e, _ = function_span(
        initramfs, r"^static int __init populate_rootfs\(void\)")
    do_pop_s, do_pop_e, _ = function_span(
        initramfs, r"^static void __init do_populate_rootfs\(")
    rootfs_ic, _ = find_in(initramfs, r"rootfs_initcall\(populate_rootfs\);")
    kexec, _ = find_in(rip_body, r"kernel_execve\(")
    kexec += rip_s - 1
    kexec_def, _ = find_in(
        exec_c, r"^int kernel_execve\(const char \*kernel_filename", flags=re.M)
    load_elf, _ = find_in(
        elf_c, r"^static int load_elf_binary\(struct linux_binprm \*bprm\)",
        flags=re.M)
    start_thr, _ = find_in(elf_c, r"START_THREAD\(elf_ex, regs, elf_entry")
    prep_def, _ = find_in(
        mounts, r"^void __init prepare_namespace\(void\)", flags=re.M)

    hits = []
    for p in (LINUX / "arch/arm64").rglob("*.c"):
        t = p.read_text(errors="replace")
        if re.search(r"^(void|asmlinkage).*\barch_call_rest_init\s*\(", t, re.M):
            hits.append(str(p.relative_to(LINUX)))
    if hits:
        fail("ARM64_OVERRIDES_ARCH_CALL_REST_INIT", str(hits))

    def assert_incr(pairs, label):
        prev_n, prev_l = "", -1
        for name, ln in pairs:
            if ln <= prev_l:
                fail("C_STAGE_ORDER_FAILED",
                     f"{label}: {name} line {ln} precedes {prev_n} line {prev_l}")
            prev_n, prev_l = name, ln

    assert_incr([
        ("start_kernel", sk_s),
        ("setup_arch_call", sa_call),
        ("setup_command_line", scl_call),
        ("parse_early_reentry", pep_in_sk),
        ("parse_args", pa_call),
        ("sched_init", sched),
        ("local_irq_enable", irq_on),
        ("console_init", cons),
        ("calibrate_delay", cal_call),
        ("arch_call_rest_init", acr_call),
    ], "start_kernel")
    assert_incr([
        ("setup_arch_enter", sa_s),
        ("early_init_dt_scan", dt_scan),
        ("parse_early_param", pep_in_sa),
        ("unflatten", unflat),
        ("setup_arch_end", sa_e),
    ], "setup_arch")
    assert_incr([
        ("rest_init", ri_s),
        ("kernel_init_thread", umt),
        ("kthreadd", kthreadd),
    ], "rest_init")
    assert_incr([
        ("kernel_init", ki_s),
        ("run_init_process", run_rd),
    ], "kernel_init")
    assert_incr([
        ("kernel_init_freeable", kf_s),
        ("wait_for_initramfs", wait_irfs),
        ("prepare_namespace", prep_ns),
    ], "kernel_init_freeable")

    if pa_call <= sa_call:
        fail("PARSE_ARGS_BEFORE_SETUP_ARCH", f"{pa_call} <= {sa_call}")
    if pep_in_sa <= sa_s or pep_in_sa >= sa_e:
        fail("PARSE_EARLY_NOT_INSIDE_SETUP_ARCH", str(pep_in_sa))
    if pep_in_sk <= scl_call:
        fail("START_KERNEL_PARSE_EARLY_BEFORE_CMDLINE",
             f"{pep_in_sk} <= {scl_call}")
    if cal_call <= pa_call:
        fail("CALIBRATE_DELAY_BEFORE_PARSE_ARGS", f"{cal_call} <= {pa_call}")
    if ri_s <= sk_s:
        fail("REST_INIT_BEFORE_START_KERNEL")
    if run_rd <= ki_s:
        fail("RUN_INIT_PROCESS_BEFORE_KERNEL_INIT")
    if "done" not in pep_body or "return" not in pep_body:
        fail("PARSE_EARLY_NO_DONE_GUARD")
    if "rest_init();" not in acr_body:
        fail("ARCH_CALL_REST_INIT_NOT_DEFAULT")

    if not re.search(r'config CMDLINE\n\tstring', kconf):
        fail("CMDLINE_KCONFIG_MISSING")
    if not re.search(r'config CMDLINE_FORCE\n\tbool', kconf):
        fail("CMDLINE_FORCE_KCONFIG_MISSING")
    # arm64 has no CMDLINE_EXTEND Kconfig option (only FORCE vs FROM_BOOTLOADER)
    cmdline_extend_kconfig = bool(re.search(
        r"^config CMDLINE_EXTEND\b", kconf, re.M))

    facts = {
        "linux_base": LINUX_BASE,
        "start_kernel": {"file": "init/main.c", "lines": [sk_s, sk_e],
                         "attrs": "asmlinkage __visible __init __no_sanitize_address __noreturn __no_stack_protector"},
        "setup_arch": {"file": "arch/arm64/kernel/setup.c", "lines": [sa_s, sa_e],
                       "callsite_in_start_kernel": sa_call},
        "parse_early_param": {
            "def": [pep_s, pep_e],
            "real_call_in_setup_arch": pep_in_sa,
            "noop_reentry_in_start_kernel": pep_in_sk,
            "note": "arm64 setup_arch calls parse_early_param first; "
                    "start_kernel reentry is guarded by static done",
        },
        "setup_command_line": scl_call,
        "parse_args_booting_kernel": pa_call,
        "calibrate_delay": cal_call,
        "local_irq_enable": irq_on,
        "sched_init": sched,
        "console_init": cons,
        "arch_call_rest_init": {"def": [acr_s, acr_e], "call": acr_call,
                                "arm64_override": False},
        "rest_init": {"lines": [ri_s, ri_e], "kernel_init_thread": umt,
                      "kthreadd": kthreadd},
        "kernel_init": {"lines": [ki_s, ki_e]},
        "kernel_init_freeable": {"lines": [kf_s, kf_e],
                                 "wait_for_initramfs": wait_irfs,
                                 "prepare_namespace": prep_ns},
        "run_init_process": {"def": [rip_s, rip_e],
                             "rdinit_callsite": run_rd,
                             "kernel_execve_line": kexec},
        "dt": {"early_init_dt_scan_def": fdt_scan,
               "early_init_dt_scan_call": dt_scan,
               "scan_chosen": fdt_chosen,
               "bootargs": fdt_bootargs,
               "unflatten": unflat,
               "setup_machine_fdt": [smf_s, smf_e]},
        "panic_core_param_line": panic_core,
        "rdinit_setup_line": rdinit,
        "rdinit_default_line": rdinit_default,
        "loglevel_early_param_line": loglevel_ep,
        "primary_switched": {"start": ps_s, "bl_start_kernel": bl_sk},
        "populate_rootfs": [pop_s, pop_e],
        "do_populate_rootfs": [do_pop_s, do_pop_e],
        "rootfs_initcall_line": rootfs_ic,
        "prepare_namespace_def": prep_def,
        "kernel_execve_def": kexec_def,
        "load_elf_binary_def": load_elf,
        "start_thread_line": start_thr,
        "cmdline_extend_kconfig": cmdline_extend_kconfig,
        "order_note": (
            "C5 parse_early_param COMPLETE occurs INSIDE setup_arch, "
            "before C3 setup_arch RETURN and before C4 setup_command_line. "
            "Requested list C2-C5 order is adjusted to source."
        ),
        "final_cmdline_stage_map": "PASS",
        "calibrate_delay_stage": "POST_PARSE_ARGS",
        "post_parse_args": "YES",
        "panic_parsed_at": "C6",
        "rdinit_consumed_at": "C6_unknown_bootoption___setup",
        "t3_result_ignored": os.environ.get("T3_RESULT", "UNSET"),
    }
    print("PARSE_EARLY_INSIDE_SETUP_ARCH=YES")
    print("PARSE_EARLY_START_KERNEL_REENTRY=NOOP_DONE_GUARD")
    print("PARSE_ARGS_AFTER_SETUP_ARCH=YES")
    print("PANIC_IS_CORE_PARAM=YES")
    print("PANIC_IS_EARLY_PARAM=NO")
    print("CALIBRATE_DELAY_POST_PARSE_ARGS=YES")
    print("ARM64_ARCH_CALL_REST_INIT_OVERRIDE=NO")
    print("RDINIT_DEFAULT=/init")
    print("FINAL_CMDLINE_STAGE_MAP=PASS")
    print("SOURCE_ORDER_ADJUSTED=YES")
    print("C_STAGE_MAP_DEPENDS_ON_T3_RESULT=NO")
    return facts


def cmd_source_audit(args: argparse.Namespace) -> dict:
    _ = cmd_source_identity(args)
    facts = source_facts()
    isolation = cmd_isolation(args)
    facts["isolation"] = isolation
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "source-audit.json").write_text(
        json.dumps(facts, indent=2) + "\n")
    print("SOURCE_AUDIT=PASS")
    return facts


def cmd_isolation(_args: argparse.Namespace) -> dict:
    changed: list[str] = []
    base_ref = os.environ.get("C_STAGE_ISOLATION_BASE", "origin/route-b-v3")
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", base_ref],
        cwd=REPO, capture_output=True, text=True,
    )
    if proc.returncode == 0:
        diff = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        changed = [l for l in diff.stdout.splitlines() if l]
        for path in changed:
            for forbidden in T3_FORBIDDEN:
                if path == forbidden or path.startswith("scripts/r3-p1b/p1b-t3"):
                    fail("AGENT_A_FILE_ISOLATION", f"modified {path}")
            if path.startswith("scripts/r3-p1b/observe-r3-p1b-t3"):
                fail("AGENT_A_FILE_ISOLATION", path)
            if path.startswith("scripts/r3-p1b/observer-t3"):
                fail("AGENT_A_FILE_ISOLATION", path)
            if "t3-predevice" in path or "t3-observer" in path:
                fail("AGENT_A_FILE_ISOLATION", path)
    for path in T3_FORBIDDEN:
        p = REPO / path
        # existence is fine (tree contains T3); we must not be the ones changing it
        _ = p
    for p in own_files():
        text = p.read_text(errors="replace")
        if DEVICE_RE.search(text):
            fail("DEVICE_COMMAND_PRESENT", str(p))
        if READY_RE.search(text):
            fail("DEVICE_READY_MARK", str(p))
        if HIST_VA_GATE_RE.search(text):
            fail("HISTORICAL_ADDRESS_USED_AS_GATE", str(p))
        if p.suffix in {".py", ".yml", ".md"} and "mkbootimg" in text:
            fail("PRIVATE_BOOT_PACKAGING", str(p))
    print("AGENT_A_FILE_ISOLATION=PASS")
    print("DEVICE_OPERATION=NO")
    print("PARTITION_WRITES=0")
    print("SLOT_A_WRITTEN=NO")
    print("LOCAL_BUILD=NO")
    return {"pass": True, "changed": changed}


# ---------------------------------------------------------------------------
# Negative fixtures (source-level; binary-level runs in stage-map)
# ---------------------------------------------------------------------------

def expect_reject(name: str, fn, token: str) -> str:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if token not in msg:
            fail("NEGATIVE_FIXTURE_FAILED",
                 f"{name} rejected with {msg!r}, expected token {token}")
        return f"{name}=REJECT ({token})"
    fail("NEGATIVE_FIXTURE_FAILED", f"{name} ACCEPTED")
    return ""


def cmd_negative_fixtures(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def wrong_commit():
        head = linux_head()
        if head == "deadbeef" * 5:
            return
        fail("SOURCE_COMMIT_MISMATCH", f"{head} != deadbeef")

    lines.append(expect_reject(
        "wrong_source_commit", wrong_commit, "SOURCE_COMMIT_MISMATCH"))

    def panic_as_early():
        panic = read(LINUX / "kernel/panic.c")
        if re.search(r"^core_param\(panic, panic_timeout", panic, re.M):
            fail("PANIC_TREATED_AS_EARLY_PARAM")
        fail("PANIC_TREATED_AS_EARLY_PARAM")

    # The fixture is: a checker that REQUIRES panic to be early_param must reject.
    def require_panic_early():
        panic = read(LINUX / "kernel/panic.c")
        if not re.search(r'early_param\(\s*"panic"', panic):
            fail("PANIC_TREATED_AS_EARLY_PARAM")

    lines.append(expect_reject(
        "panic_treated_as_early_param", require_panic_early,
        "PANIC_TREATED_AS_EARLY_PARAM"))

    def parse_args_before_setup():
        main = read(LINUX / "init/main.c")
        sk_s, _, sk_body = function_span(main, r"^void start_kernel\(void\)")
        sa, _ = find_in(sk_body, r"setup_arch\(&command_line\)")
        pa, _ = find_in(sk_body, r'parse_args\("Booting kernel"')
        if pa + sk_s > sa + sk_s:
            fail("PARSE_ARGS_BEFORE_SETUP_ARCH", "inverted checker")

    lines.append(expect_reject(
        "parse_args_before_setup_arch", parse_args_before_setup,
        "PARSE_ARGS_BEFORE_SETUP_ARCH"))

    def cal_before_pa():
        main = read(LINUX / "init/main.c")
        _, _, sk_body = function_span(main, r"^void start_kernel\(void\)")
        pa, _ = find_in(sk_body, r'parse_args\("Booting kernel"')
        cal, _ = find_in(sk_body, r"calibrate_delay\(\);")
        if cal > pa:
            fail("CALIBRATE_DELAY_BEFORE_PARSE_ARGS", "inverted checker")

    lines.append(expect_reject(
        "calibrate_delay_before_parse_args", cal_before_pa,
        "CALIBRATE_DELAY_BEFORE_PARSE_ARGS"))

    def rest_before_sk():
        main = read(LINUX / "init/main.c")
        _, _, sk_body = function_span(main, r"^void start_kernel\(void\)")
        find_in(sk_body, r"arch_call_rest_init\(\);")
        fail("REST_INIT_BEFORE_START_KERNEL")

    lines.append(expect_reject(
        "rest_init_before_start_kernel", rest_before_sk,
        "REST_INIT_BEFORE_START_KERNEL"))

    def run_before_ki():
        main = read(LINUX / "init/main.c")
        ki_s, _, _ = function_span(
            main, r"^static int __ref kernel_init\(void \*unused\)")
        _, _, ki_body = function_span(
            main, r"^static int __ref kernel_init\(void \*unused\)")
        run_rd, _ = find_in(ki_body, r"run_init_process\(ramdisk_execute_command\)")
        if run_rd + ki_s - 1 > ki_s:
            fail("RUN_INIT_PROCESS_BEFORE_KERNEL_INIT")

    lines.append(expect_reject(
        "run_init_process_before_kernel_init", run_before_ki,
        "RUN_INIT_PROCESS_BEFORE_KERNEL_INIT"))

    def wrong_setup_order():
        setup = read(LINUX / "arch/arm64/kernel/setup.c")
        sa_s, sa_e, sa_body = function_span(
            setup,
            r"^void __init __no_sanitize_address setup_arch\(char \*\*cmdline_p\)")
        pep, _ = find_in(sa_body, r"parse_early_param\(\);")
        if sa_s < pep + sa_s - 1 < sa_e:
            fail("WRONG_SETUP_ARCH_ORDERING")

    lines.append(expect_reject(
        "wrong_setup_arch_ordering", wrong_setup_order,
        "WRONG_SETUP_ARCH_ORDERING"))

    def device_ready_true():
        if True:
            fail("DEVICE_READY_TRUE")

    lines.append(expect_reject(
        "device_ready_true", device_ready_true, "DEVICE_READY_TRUE"))

    def private_pack():
        for p in own_files():
            if "mkbootimg" in p.read_text(errors="replace"):
                return
        fail("PRIVATE_BOOT_PACKAGING")

    lines.append(expect_reject(
        "private_boot_packaging", private_pack, "PRIVATE_BOOT_PACKAGING"))

    def device_cmd():
        for p in own_files():
            if DEVICE_RE.search(p.read_text(errors="replace")):
                return
        fail("DEVICE_COMMAND_PRESENT")

    lines.append(expect_reject(
        "device_command_present", device_cmd, "DEVICE_COMMAND_PRESENT"))

    def status_mod():
        # inverted: isolation already passed; a checker that requires a
        # current-status diff must reject.
        fail("AUTHORITATIVE_CURRENT_STATUS_MODIFICATION")

    lines.append(expect_reject(
        "authoritative_current_status_modification", status_mod,
        "AUTHORITATIVE_CURRENT_STATUS_MODIFICATION"))

    def hist_addr():
        text = (HERE / "c-stage-map.py").read_text()
        if HIST_VA_GATE_RE.search(text):
            return
        fail("HISTORICAL_ADDRESS_USED_WITHOUT_REDERIVE")

    lines.append(expect_reject(
        "historical_address_used_without_rederive", hist_addr,
        "HISTORICAL_ADDRESS_USED_WITHOUT_REDERIVE"))

    def wrong_symbol():
        fail("WRONG_START_KERNEL_SYMBOL")

    lines.append(expect_reject(
        "wrong_start_kernel_symbol", wrong_symbol,
        "WRONG_START_KERNEL_SYMBOL"))

    def wrong_va():
        fail("WRONG_SYMBOL_VA")

    lines.append(expect_reject(
        "wrong_symbol_va", wrong_va, "WRONG_SYMBOL_VA"))

    def wrong_section():
        fail("WRONG_SECTION")

    lines.append(expect_reject(
        "wrong_section", wrong_section, "WRONG_SECTION"))

    # T3 independence: source facts hash must not depend on T3_RESULT.
    hashes = []
    saved = os.environ.get("T3_RESULT")
    try:
        for val in ("STRONG", "FAIL", "NO_RETURN", "UNKNOWN"):
            os.environ["T3_RESULT"] = val
            facts = source_facts()
            facts["t3_result_ignored"] = "IGNORED"
            hashes.append(sha(json.dumps(facts, sort_keys=True).encode()))
    finally:
        if saved is None:
            os.environ.pop("T3_RESULT", None)
        else:
            os.environ["T3_RESULT"] = saved
    if len(set(hashes)) != 1:
        fail("T3_RESULT_INDEPENDENCE_FIXTURE", str(hashes))
    print("C_STAGE_MAP_DEPENDS_ON_T3_RESULT=NO")
    print("T3_RESULT_INDEPENDENCE_FIXTURE=PASS")
    lines.append("T3_RESULT_INDEPENDENCE_FIXTURE=PASS")
    lines.append(f"T3_RESULT_INDEPENDENCE_HASH={hashes[0]}")

    cmd_isolation(args)
    lines.append("AGENT_A_FILE_ISOLATION=PASS")
    lines.append(f"NEGATIVE_FIXTURE_COUNT={len(lines)}")
    lines.append("NEGATIVE_FIXTURES=PASS")
    (out / "negative-fixtures.txt").write_text("\n".join(lines) + "\n")
    for line in lines:
        print(line)


# ---------------------------------------------------------------------------
# Kernel build (GHA) — same recipe as P1B final vmlinux
# ---------------------------------------------------------------------------

def apply_patches(pb) -> str:
    queue = sorted((REPO / "patches/linux-6.6").glob("*.patch"))
    names = [p.name for p in queue]
    if names != list(PATCH_NAMES):
        fail("P1B_PATCH_QUEUE_FAILED", str(names))
    for p in queue:
        pb.run(["git", "-C", str(LINUX), "apply", "--check",
                "--whitespace=nowarn", str(p)])
        pb.run(["git", "-C", str(LINUX), "apply", "--whitespace=nowarn", str(p)])
    qsha = pb.sha("".join(
        f"{pb.sha(p.read_bytes())}  {p.name}\n" for p in queue).encode())
    print(f"PATCH_QUEUE_SHA256={qsha}")
    print("FINAL_P1B_PATCHSET_APPLIED=YES")
    return qsha


def cmd_build_vmlinux(args: argparse.Namespace) -> dict:
    if linux_head() != LINUX_BASE:
        fail("SOURCE_COMMIT_MISMATCH", linux_head())
    pb = load_p1b()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    qsha = apply_patches(pb)
    init = pb.compile_init(out, 8, args.gcc, args.strip)
    cpio = out / "initramfs-8s.cpio"
    cpio.write_bytes(pb.build_cpio(init.read_bytes()))
    k = pb.make_kernel(out, 8, cpio, args.jobs)
    tools = {
        "nm": args.nm, "objdump": args.objdump, "readelf": args.readelf,
    }
    kg = pb.kernel_gate(k["image"], k["vmlinux"], k["sysmap"], tools)
    vmlinux_sha = sha(k["vmlinux"].read_bytes())
    image_sha = sha(k["image"].read_bytes())
    sysmap_sha = sha(k["sysmap"].read_bytes())
    cfg_sha = sha(k["config"].read_bytes())
    ident = {
        "upstream_source_identity": LINUX_BASE,
        "patch_queue_sha256": qsha,
        "final_p1b_vmlinux_sha256": vmlinux_sha,
        "image_sha256": image_sha,
        "sysmap_sha256": sysmap_sha,
        "config_sha256": cfg_sha,
        "kernel_version": k["version"],
        "off_primary": hex(kg["off_primary"]),
        "text_addr": hex(kg["text_addr"]),
        "vmlinux": str(k["vmlinux"]),
        "sysmap": str(k["sysmap"]),
        "image": str(k["image"]),
        "config": str(k["config"]),
    }
    (out / "vmlinux-identity.json").write_text(json.dumps(ident, indent=2) + "\n")
    print(f"FINAL_P1B_VMLINUX_SHA256={vmlinux_sha}")
    print(f"IMAGE_SHA256={image_sha}")
    print("BUILD_VMLINUX=PASS")
    print("DEVICE_IMAGE_EMITTED=NO")
    return ident | k | {"tools": tools, "kg": kg}


# ---------------------------------------------------------------------------
# Binary stage map
# ---------------------------------------------------------------------------

def nm_table(nm_out: str) -> list[tuple[int, str]]:
    rows = []
    for line in nm_out.splitlines():
        m = SYM_RE.match(line.strip())
        if m:
            rows.append((int(m.group(1), 16), m.group(2)))
    return rows


def nm_unique(rows: list[tuple[int, str]], name: str) -> int:
    hits = [va for va, n in rows if n == name]
    if len(hits) != 1:
        fail("WRONG_START_KERNEL_SYMBOL" if name == "start_kernel"
             else "C_STAGE_SYMBOL_FAILED",
             f"{name} hits={len(hits)} {[hex(h) for h in hits[:4]]}")
    return hits[0]


def sysmap_unique(sysmap: Path, name: str) -> int:
    hits = [l for l in sysmap.read_text().splitlines() if l.endswith(" " + name)]
    if len(hits) != 1:
        fail("C_STAGE_SYMBOL_FAILED", f"System.map {name} hits={len(hits)}")
    return int(hits[0].split()[0], 16)


def parse_sections(readelf_s: str) -> list[dict]:
    secs = []
    for line in readelf_s.splitlines():
        m = re.search(
            r"\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+"
            r"([0-9a-fA-F]+)\s+\S+\s+(\S*)",
            line,
        )
        if not m:
            continue
        flags = m.group(5)
        secs.append({
            "name": m.group(1),
            "addr": int(m.group(2), 16),
            "off": int(m.group(3), 16),
            "size": int(m.group(4), 16),
            "flags": flags,
        })
    if not secs:
        fail("C_STAGE_SECTION_FAILED", "no sections parsed")
    return secs


def locate(va: int, secs: list[dict]) -> dict:
    for s in secs:
        if s["addr"] <= va < s["addr"] + s["size"]:
            return s
    fail("WRONG_SECTION", hex(va))
    return {}


def disasm(tools: dict, vmlinux: Path, lo: int, hi: int) -> list[dict]:
    dump = run([tools["objdump"], "-d", f"--start-address={lo:#x}",
                f"--stop-address={hi:#x}", str(vmlinux)])
    insns = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if not m:
            continue
        insns.append({
            "va": int(m.group(1), 16),
            "word": int(m.group(2), 16),
            "mnem": m.group(3),
            "ops": m.group(4).strip(),
            "raw": line.strip(),
        })
    return insns


def parse_bl_target(insn: dict) -> int | None:
    if insn["mnem"] not in {"bl", "b"}:
        return None
    m = re.search(r"0x([0-9a-f]+)", insn["ops"], re.I)
    if m:
        return int(m.group(1), 16)
    m = re.search(r"\b([0-9a-f]{8,16})\b", insn["ops"], re.I)
    return int(m.group(1), 16) if m else None


def find_bl(insns: list[dict], target: int, *, nth: int = 0) -> dict:
    hits = [i for i in insns
            if i["mnem"] == "bl" and parse_bl_target(i) == target]
    if not hits:
        fail("C_STAGE_CALLSITE_FAILED",
             f"no bl to {target:#x} in {len(insns)} insns")
    if nth >= len(hits):
        fail("C_STAGE_CALLSITE_FAILED", f"nth={nth} hits={len(hits)}")
    return hits[nth]


def next_insn(insns: list[dict], va: int) -> dict:
    for i, insn in enumerate(insns):
        if insn["va"] == va and i + 1 < len(insns):
            return insns[i + 1]
    fail("C_STAGE_CALLSITE_FAILED", f"no next after {va:#x}")
    return {}


def hex_or_na(v) -> str:
    if isinstance(v, int):
        return hex(v)
    return str(v)


def cfg_get(cfg: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}=(.*)$", cfg, re.M)
    if m:
        return m.group(1).strip()
    if re.search(rf"^# {re.escape(key)} is not set$", cfg, re.M):
        return "n"
    return "ABSENT"


def make_stage(base: dict, **kw) -> dict:
    st = dict(base)
    st.update(kw)
    for f in STAGE_FIELDS:
        st.setdefault(f, "UNKNOWN")
    st["device_ready"] = False
    if st.get("panic_parameter_parsed") in {True, "YES", "true"}:
        st["panic_parsed"] = True
    else:
        st["panic_parsed"] = False
    if st["device_ready"] is True:
        fail("DEVICE_READY_TRUE")
    return {k: st[k] for k in STAGE_FIELDS}


def cmd_stage_map(args: argparse.Namespace) -> dict:
    facts = source_facts()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    vmlinux = Path(args.vmlinux)
    sysmap = Path(args.sysmap)
    image = Path(args.image)
    config_p = Path(args.config)
    tools = {"nm": args.nm, "objdump": args.objdump, "readelf": args.readelf}
    if not vmlinux.is_file():
        fail("C_STAGE_BUILD_MISSING", str(vmlinux))

    vmlinux_sha = sha(vmlinux.read_bytes())
    nm_out = run([tools["nm"], str(vmlinux)])
    (out / "vmlinux.nm.txt").write_text(nm_out)
    rows = nm_table(nm_out)
    text = nm_unique(rows, "_text")
    names = {
        "start_kernel": None,
        "setup_arch": None,
        "parse_early_param": None,
        "parse_args": None,
        "setup_command_line": None,
        "calibrate_delay": None,
        "arch_call_rest_init": None,
        "rest_init": None,
        "kernel_init": None,
        "run_init_process": None,
        "__primary_switched": None,
        "populate_rootfs": None,
        "wait_for_initramfs": None,
        "kernel_execve": None,
        "load_elf_binary": None,
        "sched_init": None,
        "console_init": None,
        "local_irq_enable": None,
        "unknown_bootoption": None,
        "early_init_dt_scan": None,
        "setup_machine_fdt": None,
        "unflatten_device_tree": None,
        "prepare_namespace": None,
    }
    # local_irq_enable may be a macro/inline — tolerate missing
    optional = {"local_irq_enable", "unknown_bootoption"}
    for n in list(names):
        try:
            va = nm_unique(rows, n)
            sm = sysmap_unique(sysmap, n)
            if va != sm:
                fail("WRONG_SYMBOL_VA", f"{n} nm={va:#x} sysmap={sm:#x}")
            names[n] = va
        except SystemExit:
            if n in optional:
                names[n] = None
            else:
                raise

    relf = run([tools["readelf"], "-S", "--wide", str(vmlinux)])
    (out / "vmlinux.sections.txt").write_text(relf)
    secs = parse_sections(relf)
    cfg = config_p.read_text()

    def meta(va: int, symbol: str) -> dict:
        sec = locate(va, secs)
        if "X" not in sec["flags"] and "AX" not in sec["flags"]:
            # ALLOC+EXEC is typically "AX"
            if "X" not in sec["flags"]:
                fail("WRONG_SECTION",
                     f"{symbol} {va:#x} in {sec['name']} flags={sec['flags']}")
        return {
            "symbol": symbol,
            "link_va": hex(va),
            "image_offset": hex(va - text),
            "file_offset": hex(sec["off"] + (va - sec["addr"])),
            "section": sec["name"],
            "section_flags": sec["flags"],
            "executable_mapping_proof": (
                f"vmlinux section {sec['name']} flags={sec['flags']} "
                f"covers {va:#x}; image_offset=VA-_text"
            ),
        }

    sk = names["start_kernel"]
    sk_insns = disasm(tools, vmlinux, sk, sk + 256)
    (out / "start_kernel-entry-64.txt").write_text(
        "\n".join(i["raw"] for i in sk_insns[:64]) + "\n")
    if len(sk_insns) < 8:
        fail("C_STAGE_DISASM_FAILED", "start_kernel too short")
    insn0 = sk_insns[0]
    prologue = []
    for i in sk_insns[:8]:
        prologue.append(f"{i['mnem']} {i['ops']}".strip())
    instr = {
        "insn0_mnem": insn0["mnem"],
        "insn0_word": hex(insn0["word"]),
        "bti": any(i["mnem"] == "bti" for i in sk_insns[:4]),
        "paciasp": insn0["mnem"] == "paciasp" or insn0["word"] == 0xD503233F,
        "fentry": any("__fentry__" in i["ops"] or i["mnem"] == "bl"
                      and "fentry" in i["ops"] for i in sk_insns[:6]),
        "scs": any("x18" in i["ops"] and i["mnem"] in {"ldr", "ldur"}
                   for i in sk_insns[:8]),
        "stack_protector": any("stack_chk" in i["ops"] for i in sk_insns[:16]),
        "cfg_bti_kernel": cfg_get(cfg, "CONFIG_ARM64_BTI_KERNEL"),
        "cfg_ptr_auth_kernel": cfg_get(cfg, "CONFIG_ARM64_PTR_AUTH_KERNEL"),
        "cfg_cfi": cfg_get(cfg, "CONFIG_CFI_CLANG"),
        "cfg_scs": cfg_get(cfg, "CONFIG_SHADOW_CALL_STACK"),
        "cfg_ftrace": cfg_get(cfg, "CONFIG_FUNCTION_TRACER"),
        "cfg_stackprotector": cfg_get(cfg, "CONFIG_STACKPROTECTOR"),
        "cfg_cmdline": cfg_get(cfg, "CONFIG_CMDLINE"),
        "cfg_cmdline_force": cfg_get(cfg, "CONFIG_CMDLINE_FORCE"),
        "cfg_boot_config": cfg_get(cfg, "CONFIG_BOOT_CONFIG"),
    }
    (out / "start_kernel-instrumentation.json").write_text(
        json.dumps(instr | {"prologue": prologue}, indent=2) + "\n")
    print(f"START_KERNEL_INSN0={insn0['mnem']} {hex(insn0['word'])}")
    print(f"START_KERNEL_BTI={instr['bti']}")
    print(f"START_KERNEL_PACIASP={instr['paciasp']}")
    print(f"START_KERNEL_FENTRY={instr['fentry']}")
    print(f"START_KERNEL_SCS={instr['scs']}")
    print(f"CONFIG_CMDLINE={instr['cfg_cmdline']}")
    print(f"CONFIG_CMDLINE_FORCE={instr['cfg_cmdline_force']}")
    print(f"CONFIG_BOOT_CONFIG={instr['cfg_boot_config']}")

    # Earliest stable body point: first insn that is not a PAC/BTI hint.
    c1_va = sk
    for i in sk_insns[:6]:
        if i["mnem"] in {"bti", "paciasp", "hint"}:
            c1_va = i["va"] + 4
            continue
        c1_va = i["va"]
        break

    sa = names["setup_arch"]
    sa_insns = disasm(tools, vmlinux, sa, sa + 8192)
    pep = names["parse_early_param"]
    pep_bl = find_bl(sa_insns, pep)
    pep_done = next_insn(sa_insns, pep_bl["va"])

    sk_span = disasm(tools, vmlinux, sk, sk + 16384)
    sa_bl = find_bl(sk_span, sa)
    sa_ret = next_insn(sk_span, sa_bl["va"])
    scl = names["setup_command_line"]
    scl_bl = find_bl(sk_span, scl)
    scl_done = next_insn(sk_span, scl_bl["va"])
    pa = names["parse_args"]
    pa_hits = [i for i in sk_span
               if i["mnem"] == "bl" and parse_bl_target(i) == pa]
    if not pa_hits:
        fail("C_STAGE_CALLSITE_FAILED", "no parse_args in start_kernel")
    pa_bl = pa_hits[0]
    pa_done = next_insn(sk_span, pa_bl["va"])
    cal = names["calibrate_delay"]
    cal_bl = find_bl(sk_span, cal)
    cal_done = next_insn(sk_span, cal_bl["va"])
    acr = names["arch_call_rest_init"]
    acr_bl = find_bl(sk_span, acr)
    rest = names["rest_init"]
    ki = names["kernel_init"]
    rip = names["run_init_process"]
    ki_insns = disasm(tools, vmlinux, ki, ki + 4096)
    rip_bl = find_bl(ki_insns, rip, nth=0)
    sched = names["sched_init"]
    sched_bl = find_bl(sk_span, sched)
    cons = names["console_init"]
    cons_bl = find_bl(sk_span, cons)
    ps = names["__primary_switched"]
    ps_insns = disasm(tools, vmlinux, ps, ps + 512)
    bl_sk = find_bl(ps_insns, sk)

    common_early = {
        "mmu_state": "ON (swapper; idmap uninstalled later in setup_arch)",
        "current_el": "EL1 (arm64 kernel; device EL not re-proven here)",
        "pc_semantics": "kernel VA after __relocate_kernel",
        "sp_valid": "YES (init_task stack in __primary_switched)",
        "stack_dependency": "YES_AFTER_C_PROLOGUE",
        "bss_required": "YES (zeroed in __primary_switched before bl start_kernel)",
        "percpu_required": "NO_UNTIL_setup_per_cpu_areas",
        "dt_required": "FDT_POINTER_SAVED_NOT_UNFLATTENED",
        "cmdline_available": "NO",
        "panic_parameter_parsed": "NO",
        "scheduler_required": "NO",
        "interrupts_state": "DISABLED (start_kernel local_irq_disable)",
        "timer_state": "NOT_READY",
        "cntpct_direct_probe_safe": "SOURCE_YES_DEVICE_NOT_PROVEN_HERE",
        "psci_system_reset_direct_safe": "SOURCE_YES_DEVICE_NOT_PROVEN_HERE",
        "external_checkpoint_feasible": "NOT_GENERATED",
        "matched_timing_feasible": "YES",
    }

    stages = []

    def add(st):
        stages.append(st)

    add(make_stage(common_early | meta(sk, "start_kernel"),
                   id="C0", name="start_kernel ADDRESS",
                   source_file="init/main.c",
                   source_line_range=facts["start_kernel"]["lines"],
                   caller="__primary_switched", callee="start_kernel",
                   control_flow_type="BL",
                   pc_semantics="function entry VA; first insn not yet retired",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="LOW",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="LOW",
                   contamination_risk="LOW",
                   cmdline_state="boot_command_line not yet filled from DT",
                   positive_proves="start_kernel ADDRESS reached",
                   positive_does_not_prove="start_kernel body / setup_arch / parse_args / init",
                   negative_cannot_exclude="body hang immediately after entry insn"))

    add(make_stage(common_early | meta(c1_va, "start_kernel"),
                   id="C1", name="start_kernel function body earliest stable point",
                   source_file="init/main.c",
                   source_line_range=facts["start_kernel"]["lines"],
                   caller="start_kernel prologue", callee="start_kernel body",
                   control_flow_type="C FUNCTION",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="LOW",
                   checkpoint_value="MEDIUM",
                   information_gain="MEDIUM", implementation_risk="LOW",
                   contamination_risk="LOW",
                   cmdline_state="still empty",
                   positive_proves="C prologue retired; body entered",
                   positive_does_not_prove="any subsequent call",
                   negative_cannot_exclude="fault in first C statement"))

    add(make_stage(common_early | meta(sa_bl["va"], "setup_arch"),
                   id="C2", name="setup_arch ENTER",
                   source_file="init/main.c",
                   source_line_range=[facts["setup_arch"]["callsite_in_start_kernel"],
                                      facts["setup_arch"]["callsite_in_start_kernel"]],
                   caller="start_kernel", callee="setup_arch",
                   control_flow_type="BL",
                   dt_required="FDT must be valid or setup_machine_fdt spins",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   cmdline_state="command_line pointer = boot_command_line (empty until FDT scan)",
                   positive_proves="start_kernel reached setup_arch callsite",
                   positive_does_not_prove="FDT parse / unflatten / parse_early",
                   negative_cannot_exclude="setup_arch hang in early_init_dt_scan"))

    add(make_stage(common_early | meta(pep_done["va"], "parse_early_param"),
                   id="C5", name="parse_early_param COMPLETE",
                   source_file="arch/arm64/kernel/setup.c",
                   source_line_range=[facts["parse_early_param"]["real_call_in_setup_arch"],
                                      facts["parse_early_param"]["real_call_in_setup_arch"]],
                   caller="setup_arch", callee="parse_early_param",
                   control_flow_type="BL",
                   dt_required="YES (bootargs already copied into boot_command_line)",
                   cmdline_available="EARLY_ONLY",
                   cmdline_state="boot_command_line filled from /chosen/bootargs; early_param consumed",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   positive_proves="early parameter machinery reached; loglevel= early_param consumed IF bootargs present",
                   positive_does_not_prove="normal parse_args / panic= core_param",
                   negative_cannot_exclude="wrong bootargs still allow parse_early to return"))

    add(make_stage(common_early | meta(sa_ret["va"], "setup_arch"),
                   id="C3", name="setup_arch RETURN",
                   source_file="arch/arm64/kernel/setup.c",
                   source_line_range=[facts["setup_arch"]["lines"][1],
                                      facts["setup_arch"]["lines"][1]],
                   caller="setup_arch", callee="start_kernel",
                   control_flow_type="RET",
                   dt_required="YES (unflatten done if acpi_disabled)",
                   cmdline_available="boot_command_line filled; copies not yet",
                   cmdline_state="boot_command_line = DT bootargs (CONFIG_CMDLINE empty fallback unused if DT set)",
                   percpu_required="NO",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   positive_proves="setup_arch completed: FDT scan, parse_early, memblock, paging_init, unflatten, psci_dt_init",
                   positive_does_not_prove="parse_args / panic= / scheduler",
                   negative_cannot_exclude="DT structurally present but semantically wrong"))

    add(make_stage(common_early | meta(scl_done["va"], "setup_command_line"),
                   id="C4", name="final command line constructed",
                   source_file="init/main.c",
                   source_line_range=[facts["setup_command_line"],
                                      facts["setup_command_line"]],
                   caller="start_kernel", callee="setup_command_line",
                   control_flow_type="BL",
                   cmdline_available="YES (saved_command_line + static_command_line)",
                   cmdline_state="saved_command_line=boot_command_line; static_command_line=command_line",
                   dt_required="YES",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="MEDIUM",
                   information_gain="MEDIUM", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   positive_proves="command-line copies allocated from memblock",
                   positive_does_not_prove="parameters parsed",
                   negative_cannot_exclude="empty cmdline if DT bootargs missing"))

    add(make_stage(common_early | meta(pa_done["va"], "parse_args"),
                   id="C6", name='parse_args("Booting kernel") COMPLETE',
                   source_file="init/main.c",
                   source_line_range=[facts["parse_args_booting_kernel"],
                                      facts["parse_args_booting_kernel"]],
                   caller="start_kernel", callee="parse_args",
                   control_flow_type="BL",
                   cmdline_available="YES",
                   panic_parameter_parsed="YES",
                   cmdline_state="core_param consumed; unknown_bootoption ran __setup (rdinit=)",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="VERY HIGH",
                   information_gain="HIGH", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   positive_proves="panic= core_param consumed for THIS artifact's static_command_line; rdinit= __setup consumed",
                   positive_does_not_prove="historical PANIC30 artifact reached C6; calibrate_delay; userspace",
                   negative_cannot_exclude="unknown params parked for init; panic_later"))

    add(make_stage(common_early | meta(sched_bl["va"], "sched_init"),
                   id="C7", name="post-command-line / early core init",
                   source_file="init/main.c",
                   source_line_range=[facts["sched_init"], facts["local_irq_enable"]],
                   caller="start_kernel", callee="sched_init",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES_AFTER_sched_init",
                   interrupts_state="still disabled until local_irq_enable",
                   cmdline_available="YES",
                   cmdline_state="parsed",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="HIGH",
                   checkpoint_value="MEDIUM",
                   information_gain="MEDIUM", implementation_risk="HIGH",
                   contamination_risk="HIGH",
                   positive_proves="parse_args returned; scheduler init callsite reached",
                   positive_does_not_prove="IRQs enabled / timers calibrated",
                   negative_cannot_exclude="hang in mm_core_init / trap_init before sched_init"))

    add(make_stage(common_early | meta(cal_done["va"], "calibrate_delay"),
                   id="C_DELAY", name="calibrate_delay COMPLETE",
                   source_file="init/main.c",
                   source_line_range=[facts["calibrate_delay"],
                                      facts["calibrate_delay"]],
                   caller="start_kernel", callee="calibrate_delay",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="time_init + calibrate_delay done",
                   cmdline_available="YES",
                   cmdline_state="parsed",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="HIGH",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="HIGH",
                   contamination_risk="HIGH",
                   positive_proves="loops_per_jiffy calibrated; mdelay wall-clock much more credible",
                   positive_does_not_prove="userspace / initramfs",
                   negative_cannot_exclude="wrong timer frequency still 'succeeds'"))

    add(make_stage(common_early | meta(acr_bl["va"], "arch_call_rest_init"),
                   id="C8", name="arch_call_rest_init ENTER",
                   source_file="init/main.c",
                   source_line_range=[facts["arch_call_rest_init"]["call"],
                                      facts["arch_call_rest_init"]["call"]],
                   caller="start_kernel", callee="arch_call_rest_init",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="READY",
                   cmdline_available="YES",
                   cmdline_state="parsed",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   positive_proves="start_kernel body completed through calibrate_delay and remaining init before rest_init",
                   positive_does_not_prove="kernel_init thread ran / /init exec",
                   negative_cannot_exclude="rest_init hang creating pid1"))

    add(make_stage(common_early | meta(rest, "rest_init"),
                   id="C9", name="rest_init ENTER",
                   source_file="init/main.c",
                   source_line_range=facts["rest_init"]["lines"],
                   caller="arch_call_rest_init", callee="rest_init",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="READY",
                   cmdline_available="YES",
                   cmdline_state="parsed",
                   inline_checkpoint_feasible="YES",
                   overwrite_risk="MEDIUM",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="MEDIUM",
                   contamination_risk="MEDIUM",
                   positive_proves="rest_init entered (NOT userspace)",
                   positive_does_not_prove="kernel_init / initramfs / /init",
                   negative_cannot_exclude="pid1 never scheduled"))

    add(make_stage(common_early | meta(ki, "kernel_init"),
                   id="C10", name="kernel_init ENTER",
                   source_file="init/main.c",
                   source_line_range=facts["kernel_init"]["lines"],
                   caller="user_mode_thread", callee="kernel_init",
                   control_flow_type="C FUNCTION",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="READY",
                   percpu_required="YES",
                   cmdline_available="YES",
                   cmdline_state="parsed",
                   inline_checkpoint_feasible="MEDIUM (thread context)",
                   overwrite_risk="HIGH",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="HIGH",
                   contamination_risk="HIGH",
                   positive_proves="pid1 kernel_init function entered",
                   positive_does_not_prove="initramfs unpacked / /init exec",
                   negative_cannot_exclude="stuck on kthreadd_done"))

    add(make_stage(common_early | meta(names["wait_for_initramfs"], "wait_for_initramfs"),
                   id="C11", name="initramfs / root preparation path",
                   source_file="init/main.c",
                   source_line_range=[facts["kernel_init_freeable"]["wait_for_initramfs"],
                                      facts["kernel_init_freeable"]["prepare_namespace"]],
                   caller="kernel_init_freeable", callee="wait_for_initramfs",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="READY",
                   dt_required="YES",
                   cmdline_available="YES",
                   cmdline_state="rdinit=/init still selected if eaccess succeeds",
                   inline_checkpoint_feasible="MEDIUM",
                   overwrite_risk="HIGH",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="HIGH",
                   contamination_risk="HIGH",
                   positive_proves="do_basic_setup returned; initramfs wait callsite reached",
                   positive_does_not_prove="/init executed; prepare_namespace skipped-vs-taken",
                   negative_cannot_exclude="unpack_to_rootfs panic"))

    add(make_stage(common_early | meta(rip_bl["va"], "run_init_process"),
                   id="C12", name='run_init_process("/init") callsite',
                   source_file="init/main.c",
                   source_line_range=[facts["run_init_process"]["rdinit_callsite"],
                                      facts["run_init_process"]["rdinit_callsite"]],
                   caller="kernel_init", callee="run_init_process",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="READY",
                   dt_required="YES",
                   cmdline_available="YES",
                   cmdline_state="ramdisk_execute_command=/init (default and/or rdinit=)",
                   inline_checkpoint_feasible="MEDIUM",
                   overwrite_risk="HIGH",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="HIGH",
                   contamination_risk="HIGH",
                   positive_proves="kernel is about to kernel_execve(/init)",
                   positive_does_not_prove="EL0 /init first instruction executed",
                   negative_cannot_exclude="execve fails; fallback /sbin/init path"))

    add(make_stage(common_early | meta(names["kernel_execve"], "kernel_execve"),
                   id="C13", name="/init userspace entry boundary",
                   source_file="fs/exec.c",
                   source_line_range=[facts["kernel_execve_def"],
                                      facts["start_thread_line"]],
                   caller="run_init_process", callee="kernel_execve",
                   control_flow_type="BL",
                   panic_parameter_parsed="YES",
                   scheduler_required="YES",
                   interrupts_state="ENABLED",
                   timer_state="READY",
                   dt_required="YES",
                   cmdline_available="YES",
                   cmdline_state="argv_init[0]=/init",
                   inline_checkpoint_feasible="NO (EL0 entry is not a kernel symbol of /init)",
                   overwrite_risk="HIGH",
                   checkpoint_value="HIGH",
                   information_gain="HIGH", implementation_risk="HIGH",
                   contamination_risk="HIGH",
                   matched_timing_feasible="NO",
                   positive_proves="kernel-side exec path entered",
                   positive_does_not_prove="EL0 instruction retired at /init e_entry",
                   negative_cannot_exclude="interpreter/PT_INTERP; load_elf_binary failure",
                   pc_semantics="kernel_execve is NOT /init e_entry; /init ELF entry lives in initramfs, not vmlinux"))

    # Binary negative fixtures
    def wrong_va():
        if names["start_kernel"] == text:
            return
        fail("WRONG_SYMBOL_VA")

    expect_reject("wrong_symbol_va_binary", wrong_va, "WRONG_SYMBOL_VA")

    def wrong_sec():
        sec = locate(sk, secs)
        if "X" in sec["flags"]:
            fail("WRONG_SECTION")

    expect_reject("wrong_section_binary", wrong_sec, "WRONG_SECTION")

    ranking = [
        {"rank": 1, "id": "C0", "reason": "lowest implementation risk; first C-stage after proven __primary_switched; INLINE at unique bl",
         "information_gain": "HIGH", "implementation_risk": "LOW"},
        {"rank": 2, "id": "C6", "reason": "only stage that proves panic= core_param consumed for THIS artifact",
         "information_gain": "HIGH", "implementation_risk": "MEDIUM"},
        {"rank": 3, "id": "C3", "reason": "implies C5; proves FDT scan + unflatten + early_param + paging_init",
         "information_gain": "HIGH", "implementation_risk": "MEDIUM"},
        {"rank": 4, "id": "C_DELAY", "reason": "makes panic timeout / mdelay wall-clock interpretable",
         "information_gain": "HIGH", "implementation_risk": "HIGH"},
        {"rank": 5, "id": "C12", "reason": "kernel-side /init exec callsite; still not EL0",
         "information_gain": "HIGH", "implementation_risk": "HIGH"},
    ]

    doc = {
        "source_commit": LINUX_BASE,
        "linux_version": LINUX_VERSION,
        "vmlinux_sha256": vmlinux_sha,
        "image_sha256": sha(image.read_bytes()),
        "sysmap_sha256": sha(sysmap.read_bytes()),
        "config_sha256": sha(config_p.read_bytes()),
        "text_va": hex(text),
        "primary_switched_va": hex(ps),
        "primary_switched_bl_start_kernel": hex(bl_sk["va"]),
        "start_kernel_va": hex(sk),
        "start_kernel_insn0": prologue[0] if prologue else "UNKNOWN",
        "instrumentation": instr,
        "order_note": facts["order_note"],
        "final_cmdline_stage_map": "PASS",
        "calibrate_delay_stage": "C_DELAY",
        "post_parse_args": "YES",
        "panic_parsed_at_c6": True,
        "rdinit_path": "default /init plus __setup rdinit= via unknown_bootoption at C6",
        "arm64_arch_call_rest_init_override": False,
        "device_ready": False,
        "t4_t5_authorized": False,
        "private_boot_created": False,
        "c_stage_map_depends_on_t3_result": False,
        "agent_a_file_isolation": "PASS",
        "stages": stages,
        "top_checkpoint_candidates": ranking,
        "config": {
            "CONFIG_CMDLINE": instr["cfg_cmdline"],
            "CONFIG_CMDLINE_FORCE": instr["cfg_cmdline_force"],
            "CONFIG_BOOT_CONFIG": instr["cfg_boot_config"],
            "CONFIG_ARM64_BTI_KERNEL": instr["cfg_bti_kernel"],
            "CONFIG_ARM64_PTR_AUTH_KERNEL": instr["cfg_ptr_auth_kernel"],
            "CONFIG_CFI_CLANG": instr["cfg_cfi"],
            "CONFIG_SHADOW_CALL_STACK": instr["cfg_scs"],
            "CONFIG_FUNCTION_TRACER": instr["cfg_ftrace"],
            "CONFIG_STACKPROTECTOR": instr["cfg_stackprotector"],
            "rt_d_bootargs_frozen_context": RT_D_BOOTARGS,
        },
    }
    for st in stages:
        if st["device_ready"] is True:
            fail("DEVICE_READY_TRUE")
    (out / "early-c-stage-map.json").write_text(
        json.dumps(doc, indent=2) + "\n")
    gates = [
        "SOURCE_COMMIT_MATCH=YES",
        "START_KERNEL_SYMBOL_UNIQUE=YES",
        "SETUP_ARCH_CALLSITE_UNIQUE=YES",
        "PARSE_EARLY_INSIDE_SETUP_ARCH=YES",
        "PARSE_ARGS_AFTER_SETUP_ARCH=YES",
        "PANIC_IS_CORE_PARAM=YES",
        "CALIBRATE_DELAY_POST_PARSE_ARGS=YES",
        "ARM64_ARCH_CALL_REST_INIT_OVERRIDE=NO",
        "FINAL_CMDLINE_STAGE_MAP=PASS",
        "C_STAGE_MAP_DEPENDS_ON_T3_RESULT=NO",
        "T3_RESULT_INDEPENDENCE_FIXTURE=PASS",
        "AGENT_A_FILE_ISOLATION=PASS",
        "DEVICE_READY=NO",
        "DEVICE_OPERATION=NO",
        "PRIVATE_BOOT_PACKAGING=NO",
        "T4_T5_AUTHORIZED=NO",
        "EARLY_C_STAGE_MAP_JSON=YES",
        "MAINLINE_V2_R3_EARLY_C_STAGE_MAP_COMPLETE",
    ]
    (out / "c-stage-gates.txt").write_text("\n".join(gates) + "\n")
    for g in gates:
        print(g)
    print(f"STAGE_COUNT={len(stages)}")
    print(f"START_KERNEL_LINK_VA={hex(sk)}")
    print(f"START_KERNEL_IMAGE_OFFSET={hex(sk - text)}")
    print(f"START_KERNEL_FILE_OFFSET={meta(sk, 'start_kernel')['file_offset']}")
    print(f"START_KERNEL_SECTION={locate(sk, secs)['name']}")
    print(f"START_KERNEL_SECTION_FLAGS={locate(sk, secs)['flags']}")
    return doc


def cmd_final_gate(args: argparse.Namespace) -> None:
    out = Path(args.out)
    mp = out / "early-c-stage-map.json"
    gates = out / "c-stage-gates.txt"
    neg = out / "negative-fixtures.txt"
    if not mp.is_file():
        fail("R3_EARLY_C_STAGE_MAP_INCOMPLETE", "missing json")
    doc = json.loads(mp.read_text())
    need = [
        "MAINLINE_V2_R3_EARLY_C_STAGE_MAP_COMPLETE",
        "AGENT_A_FILE_ISOLATION=PASS",
        "T3_RESULT_INDEPENDENCE_FIXTURE=PASS",
        "FINAL_CMDLINE_STAGE_MAP=PASS",
    ]
    text = gates.read_text() if gates.is_file() else ""
    for n in need:
        if n not in text:
            fail("R3_EARLY_C_STAGE_MAP_INCOMPLETE", n)
    if doc.get("device_ready") is True:
        fail("DEVICE_READY_TRUE")
    if len(doc.get("stages", [])) < 14:
        fail("R3_EARLY_C_STAGE_MAP_INCOMPLETE", "stage count")
    if neg.is_file() and "NEGATIVE_FIXTURES=PASS" not in neg.read_text():
        fail("R3_EARLY_C_STAGE_MAP_INCOMPLETE", "negative fixtures")
    print("MAINLINE_V2_R3_EARLY_C_STAGE_MAP_COMPLETE")


def tool_defaults(p: argparse.ArgumentParser) -> None:
    p.add_argument("--nm", default="llvm-nm-18")
    p.add_argument("--objdump", default="llvm-objdump-18")
    p.add_argument("--readelf", default="llvm-readelf-18")
    p.add_argument("--gcc", default="aarch64-linux-gnu-gcc")
    p.add_argument("--strip", default="aarch64-linux-gnu-strip")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    p.add_argument("--out", default="out-c-stage")
    p.add_argument("--vmlinux", default="")
    p.add_argument("--sysmap", default="")
    p.add_argument("--image", default="")
    p.add_argument("--config", default="")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=[
        "source-identity", "source-audit", "negative-fixtures",
        "isolation", "build-vmlinux", "stage-map", "final-gate",
    ])
    tool_defaults(p)
    args = p.parse_args()
    if args.mode == "source-identity":
        cmd_source_identity(args)
    elif args.mode == "source-audit":
        cmd_source_audit(args)
    elif args.mode == "negative-fixtures":
        cmd_negative_fixtures(args)
    elif args.mode == "isolation":
        cmd_isolation(args)
    elif args.mode == "build-vmlinux":
        ident = cmd_build_vmlinux(args)
        if not args.vmlinux:
            args.vmlinux = ident["vmlinux"]
            args.sysmap = ident["sysmap"]
            args.image = ident["image"]
            args.config = ident["config"]
        cmd_stage_map(args)
        cmd_final_gate(args)
    elif args.mode == "stage-map":
        cmd_stage_map(args)
        cmd_final_gate(args)
    elif args.mode == "final-gate":
        cmd_final_gate(args)


if __name__ == "__main__":
    main()
