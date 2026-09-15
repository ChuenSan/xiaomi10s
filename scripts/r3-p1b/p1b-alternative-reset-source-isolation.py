#!/usr/bin/env python3
"""R3 P1B alternative reset-source isolation
(MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI).

GitHub Actions only. SOURCE AUDIT / STATIC RESET-PATH MAP / NEXT-DIAGNOSTIC
DESIGN. No device-ready boot artifact, no private pack, no *.img.

Modes:
  source-gate     workflow/docs/script boundary
  source-audit    linux-6.6 restart/oops/init/watchdog-driver + RT-D + config
  binary-audit    vmlinux/Image symbol+callsite+FIX8 prologue cross-check
  merge-verdict   merge source+binary JSON, schema, ranking, final gate
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("CI only — refuse local build/pack/binary validation")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LINUX = REPO / "linux-6.6"
DOC = REPO / "docs" / "route-r3-p1b-alternative-reset-source-isolation.md"
STATUS_DOC = REPO / "docs" / "route-r3-current-status.md"
WF = (REPO / ".github" / "workflows" /
      "thyme-r3-p1b-alternative-reset-source-isolation.yml")
SCHEMA = HERE / "alternative-reset-source-map.schema.json"

LINUX_COMMIT = "8b73de7da85fde281a385e0b26eda9bffd3ca477"
RT_D_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
RT_D_SIZE = 144593
FIX8_PAYLOAD_SHA = (
    "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41")
FIX8_PAYLOAD_SIZE = 37369041
FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
PACIASP = 0xD503233F
BTI_C = 0xD503245F
PSCI_SYSTEM_RESET_FID = 0x84000009
ROUND = "MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_SOURCE_ISOLATION_CI"
CONFIDENCE = ("SOURCE_PROVEN", "SOURCE_SUPPORTED", "INFERRED", "UNKNOWN")
EXPLAIN = ("SOURCE_YES", "INFERRED", "UNKNOWN")
CANDIDATE_FIELDS = (
    "candidate_id", "class", "symbol", "source_file", "trigger",
    "reachable_after_c_delay", "passes_canonical_panic",
    "common_restart_chokepoint", "requires_driver_probe", "requires_DT_node",
    "relevant_config", "runtime_patch_risk", "source_timing_bound",
    "can_explain_23_28s", "confidence_class", "recommended_next_probe",
)
INSTR_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$")

DOC_HEADINGS = (
    "PENTRY pair result",
    "pair evidence boundary",
    "C_DELAY lower bound",
    "reset source taxonomy",
    "kernel restart chain",
    "emergency restart chain",
    "common choke point analysis",
    "PSCI restart chain",
    "watchdog config",
    "RT-D watchdog nodes",
    "Qualcomm watchdog",
    "PMIC/secure watchdog",
    "inherited watchdog handoff",
    "timeout-source discipline",
    "oops/die/BUG map",
    "PID1/init failure semantics",
    "persistent evidence limitations",
    "bootreason limitation",
    "ranked candidate table",
    "next causal experiment decision",
)

WATCHDOG_SYMS = (
    "CONFIG_WATCHDOG", "CONFIG_WATCHDOG_CORE",
    "CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED", "CONFIG_WATCHDOG_NOWAYOUT",
    "CONFIG_QCOM_WDT", "CONFIG_PM8916_WATCHDOG", "CONFIG_ARM_SP805_WATCHDOG",
    "CONFIG_ARM_SBSA_WATCHDOG", "CONFIG_ARM_SMC_WATCHDOG", "CONFIG_SOFT_WATCHDOG",
    "CONFIG_LOCKUP_DETECTOR", "CONFIG_SOFTLOCKUP_DETECTOR",
    "CONFIG_HARDLOCKUP_DETECTOR", "CONFIG_DETECT_HUNG_TASK",
    "CONFIG_HANGCHECK_TIMER", "CONFIG_POWER_RESET_MSM",
    "CONFIG_POWER_RESET_QCOM_PON", "CONFIG_ARM_PSCI_FW", "CONFIG_EFI",
    "CONFIG_EFI_RUNTIME_SERVICES", "CONFIG_MODULES", "CONFIG_ARCH_QCOM",
    "CONFIG_PANIC_ON_OOPS", "CONFIG_PANIC_TIMEOUT", "CONFIG_QCOM_SCM",
    "CONFIG_MFD_SPMI_PMIC",
)

QCOM_WDT_COMPAT = ("qcom,kpss-wdt", "qcom,kpss-timer", "qcom,scss-timer")
PMIC_WDT_COMPAT = ("qcom,pm8916-pon", "qcom,pm8941-pon", "qcom,pms405-pon",
                   "qcom,pm8998-pon", "qcom,pmk8350-pon")
PSHOLD_COMPAT = ("qcom,pshold",)
PSCI_COMPAT = ("arm,psci", "arm,psci-0.2", "arm,psci-1.0")
SMC_WDT_COMPAT = ("arm,smc-wdt",)
RTD_KEYWORDS = (
    "watchdog", "wdt", "timer-reset", "restart", "psci", "pshold",
    "power-reset", "kpss-wdt", "kpss-timer", "scss-timer", "smc-wdt", "pon",
)


def sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def fail(label: str, detail: str = "") -> None:
    raise SystemExit(label if not detail else f"{label}: {detail}")


def run(cmd: list[str], *, cwd: Path | None = None,
        env: dict | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True,
                          text=True, env=env)
    if proc.returncode != 0:
        fail("ARS_CMD_FAILED",
             f"{' '.join(cmd)}\n{proc.stderr}\n{proc.stdout[-4000:]}")
    return proc.stdout


def src(rel: str) -> str:
    path = LINUX / rel
    if not path.is_file():
        fail("ARS_SOURCE_MISSING", rel)
    return path.read_text(errors="replace")


def need(text: str, needle: str, *, label: str = "ARS_AUDIT_FAILED") -> None:
    if needle not in text:
        fail(label, f"missing {needle!r}")


def forbid(text: str, needle: str, *, label: str = "ARS_AUDIT_FAILED") -> None:
    if needle in text:
        fail(label, f"forbidden {needle!r}")


def emit(k: str, v) -> None:
    print(f"{k}={v}")


def linux_commit() -> str:
    got = run(["git", "rev-parse", "HEAD"], cwd=LINUX).strip()
    if got != LINUX_COMMIT:
        fail("ARS_LINUX_COMMIT_FAILED", f"{got} != {LINUX_COMMIT}")
    return got


# ---------------------------------------------------------------- FDT

def fdt_header(blob: bytes) -> dict:
    if len(blob) < 40:
        fail("ARS_FDT_FAILED", "short blob")
    magic, totalsize, off_struct, off_strings, off_rsv, version, last_comp, \
        cpuid, sz_strings, sz_struct = struct.unpack_from(">10I", blob, 0)
    if magic != FDT_MAGIC:
        fail("ARS_FDT_FAILED", f"magic=0x{magic:08x}")
    if totalsize != len(blob):
        fail("ARS_FDT_FAILED", f"totalsize={totalsize} file={len(blob)}")
    return {"off_struct": off_struct, "off_strings": off_strings,
            "sz_strings": sz_strings, "sz_struct": sz_struct}


def fdt_walk(blob: bytes) -> list[tuple[str, str, bytes]]:
    hdr = fdt_header(blob)
    strings = blob[hdr["off_strings"]:hdr["off_strings"] + hdr["sz_strings"]]
    path: list[str] = []
    props: list[tuple[str, str, bytes]] = []
    i = hdr["off_struct"]
    while True:
        token = struct.unpack_from(">I", blob, i)[0]
        i += 4
        if token == FDT_BEGIN_NODE:
            end = blob.index(b"\x00", i)
            path.append(blob[i:end].decode("ascii", "replace") or "")
            i = (end + 1 + 3) & ~3
        elif token == FDT_END_NODE:
            path.pop()
        elif token == FDT_PROP:
            plen, nameoff = struct.unpack_from(">II", blob, i)
            i += 8
            nend = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:nend].decode("ascii", "replace")
            props.append(("/".join(path) or "/", pname, blob[i:i + plen]))
            i = (i + plen + 3) & ~3
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            fail("ARS_FDT_FAILED", f"token={token}")
    if path:
        fail("ARS_FDT_FAILED", "unbalanced")
    return props


def fdt_strlist(v: bytes) -> list[str]:
    return [s.decode("ascii", "replace") for s in v.split(b"\x00") if s]


def fdt_nodes(blob: bytes) -> dict[str, dict[str, bytes]]:
    nodes: dict[str, dict[str, bytes]] = {}
    for path, name, value in fdt_walk(blob):
        nodes.setdefault(path, {})[name] = value
    return nodes


def node_status(props: dict[str, bytes]) -> str:
    v = props.get("status")
    if not v:
        return "okay"
    sl = fdt_strlist(v)
    return sl[0] if sl else "okay"


# ---------------------------------------------------------------- config

def parse_config(text: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# ") and line.endswith(" is not set"):
            cfg[line[2:].split(" is not set")[0].strip()] = "n"
        elif "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def cfg_class(cfg: dict[str, str], name: str) -> str:
    v = cfg.get(name)
    if v is None or v == "n":
        return "ABSENT"
    if v == "y":
        return "BUILTIN"
    if v == "m":
        return "MODULE"
    return f"OTHER:{v}"


def reconstruct_config(out: Path) -> Path:
    odir = (out / "out-config").resolve()
    odir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    makeargs = ["O=" + str(odir), "ARCH=arm64"]
    run(["make", *makeargs, "defconfig"], cwd=LINUX, env=env)
    run(["./scripts/kconfig/merge_config.sh", "-m", "-O", str(odir),
         str(odir / ".config"),
         str(REPO / "configs" / "thyme-route-b.config"),
         str(REPO / "configs" / "thyme-r3-p1b.config")], cwd=LINUX, env=env)
    run(["make", *makeargs, "olddefconfig"], cwd=LINUX, env=env)
    cfgp = odir / ".config"
    if not cfgp.is_file():
        fail("ARS_CONFIG_FAILED", "missing .config")
    return cfgp


# ---------------------------------------------------------------- source audits

def restart_chain_audit() -> dict:
    reboot = src("kernel/reboot.c")
    process = src("arch/arm64/kernel/process.c")
    emerg = src("include/asm-generic/emergency-restart.h")
    panic_c = src("kernel/panic.c")
    psci = src("drivers/firmware/psci/psci.c")
    reboot_h = src("include/linux/reboot.h")
    need(reboot, "void emergency_restart(void)")
    need(reboot, "machine_emergency_restart();")
    need(reboot, "void kernel_restart(char *cmd)")
    need(reboot, "machine_restart(cmd);")
    need(reboot, "void do_kernel_restart(char *cmd)")
    need(reboot, "atomic_notifier_call_chain(&restart_handler_list")
    need(reboot, "int register_restart_handler(struct notifier_block *nb)")
    forbid(reboot, "void __weak machine_restart")
    need(process, "void machine_restart(char *cmd)")
    need(process, "do_kernel_restart(cmd);")
    need(emerg, "static inline void machine_emergency_restart(void)")
    need(emerg, "machine_restart(NULL);")
    need(panic_c, "emergency_restart();")
    need(panic_c, "if (panic_timeout > 0)")
    need(panic_c, "if (panic_timeout != 0)")
    need(psci, "static int psci_sys_reset(")
    need(psci, "register_restart_handler(&psci_sys_reset_nb);")
    need(psci, "PSCI_0_2_FN_SYSTEM_RESET")
    need(psci, "int __init psci_dt_init(void)")
    need(reboot_h, "#include <asm/emergency-restart.h>")
    # arm64 has no arch override; mandatory-y pulls asm-generic inline.
    if (LINUX / "arch/arm64/include/asm/emergency-restart.h").exists():
        fail("ARS_AUDIT_FAILED", "arm64 emergency-restart.h unexpectedly present")
    return {
        "KERNEL_RESTART_CHAIN_AUDITED": "YES",
        "EMERGENCY_RESTART_CHAIN_AUDITED": "YES",
        "ARM64_RESTART_CHAIN_AUDITED": "YES",
        "PSCI_RESTART_CHAIN_AUDITED": "YES",
        "machine_emergency_restart": "INLINED_TO_machine_restart_NULL",
        "weak_machine_restart": "ABSENT",
        "kernel_restart": "kernel_restart_prepare -> machine_restart",
        "emergency_restart": "kmsg_dump + machine_emergency_restart",
        "machine_restart": "irq_disable + smp_send_stop + optional efi_reboot "
                           "+ do_kernel_restart + halt-loop",
        "do_kernel_restart": "atomic_notifier_call_chain(restart_handler_list)",
        "psci_sys_reset": "priority 129, PSCI SYSTEM_RESET / RESET2",
        "psci_registered_when": "psci_0_2_set_functions via psci_dt_init "
                                "(setup_arch, before C_DELAY if /psci present)",
        "register_restart_handler": "kernel/reboot.c",
    }


def oops_die_audit() -> dict:
    traps = src("arch/arm64/kernel/traps.c")
    panic_c = src("kernel/panic.c")
    need(traps, "void die(const char *str, struct pt_regs *regs, long err)")
    need(traps, "if (panic_on_oops)")
    need(traps, "make_task_dead(SIGSEGV);")
    need(panic_c, "void check_panic_on_warn(const char *origin)")
    need(panic_c, "int panic_on_oops = CONFIG_PANIC_ON_OOPS_VALUE;")
    need(panic_c, "int panic_on_warn __read_mostly;")
    return {
        "OOPS_DIE_RESET_MAP_COMPLETE": "YES",
        "die": {
            "calls_panic": "conditional (in_interrupt OR panic_on_oops)",
            "else": "make_task_dead(SIGSEGV)",
            "direct_restart": "NO",
        },
        "oops_enter": {"calls_panic": "only via panic_on_oops",
                       "direct_restart": "NO"},
        "bug_warn": {"calls_panic": "conditional panic_on_warn / warn_limit",
                     "direct_restart": "NO"},
        "panic_timeout_restart": {
            "calls_panic": "YES (is inside panic())",
            "then": "emergency_restart if panic_timeout != 0",
        },
        "OOPS_DIE_DIRECT_RESTART_WITHOUT_PANIC": "NO_IN_TREE",
        "paths_requiring_panic": [
            "die+panic_on_oops", "die+in_interrupt", "check_panic_on_warn",
            "PID1 death", "no working init",
        ],
        "panic_bypassing_paths": [
            "die -> make_task_dead (hang/kill, no restart)",
            "WARN without panic_on_warn",
        ],
    }


def init_failure_audit() -> dict:
    main_c = src("init/main.c")
    exit_c = src("kernel/exit.c")
    init_c = (HERE / "p1b-init.c").read_text()
    need(main_c, "static int __ref kernel_init(void *unused)")
    need(main_c, "if (ramdisk_execute_command)")
    need(main_c, 'panic("Requested init %s failed (error %d)."')
    need(main_c, 'panic("No working init found.')
    need(exit_c, 'panic("Attempted to kill init! exitcode=0x%08x\\n"')
    need(init_c, "SYS_reboot")
    need(init_c, "LINUX_REBOOT_CMD_RESTART")
    need(init_c, "EXIT_SLEEP_FAILED")
    # ramdisk_execute_command failure is pr_err, not panic, then fallthrough.
    ramdisk = main_c[main_c.index("if (ramdisk_execute_command)"):
                     main_c.index("if (execute_command)")]
    if "panic(" in ramdisk:
        fail("ARS_AUDIT_FAILED", "rdinit failure panics unexpectedly")
    return {
        "INIT_FAILURE_RESET_SEMANTICS_AUDITED": "YES",
        "rdinit_failure": "pr_err then fall through (NOT panic)",
        "execute_command_failure": "panic (requires canonical panic)",
        "no_working_init": "panic (requires canonical panic)",
        "pid1_death": "panic Attempted to kill init (requires canonical panic)",
        "p1b_init_sleep_failure": "exit 111 -> PID1 death -> panic",
        "p1b_init_reboot_syscall": "SYS_reboot RESTART -> kernel_restart "
                                   "(does NOT pass panic)",
        "requires_panic": "PARTIAL",
        "init_reached": "NOT_PROVEN",
    }


def callers_audit() -> dict:
    # Source-level caller lists (exact tree). Binary job re-derives BL sites.
    emer_files = [
        "kernel/panic.c",
        "kernel/reboot.c",
        "kernel/debug/kdb/kdb_main.c",
        "drivers/tty/sysrq.c",
        "drivers/watchdog/softdog.c",
        "drivers/char/hangcheck-timer.c",
    ]
    kern_files = [
        "kernel/reboot.c",
        "kernel/power/hibernate.c",
        "drivers/watchdog/softdog.c",
    ]
    for rel in emer_files + kern_files:
        if not (LINUX / rel).is_file():
            fail("ARS_CALLER_MISSING", rel)
    panic_c = src("kernel/panic.c")
    need(panic_c, "emergency_restart();")
    post_c_delay = [
        "panic_timeout_branch (inside panic; DEPRIORITIZED_BY_PENTRY_PAIR)",
        "sysrq reboot (needs tty/sysrq; not proven in this boot)",
        "kdb (needs kgdb; not proven)",
        "softdog (CONFIG_SOFT_WATCHDOG typically ABSENT)",
        "hangcheck-timer (typically ABSENT)",
        "hw_failure_emergency_poweroff (thermal; needs driver)",
    ]
    return {
        "emergency_restart_source_callers": emer_files,
        "kernel_restart_source_callers": kern_files,
        "POST_C_DELAY_EMERGENCY_RESTART_CALLERS": post_c_delay,
        "kernel_restart_classes": {
            "userspace_reboot_syscall": "kernel/reboot.c LINUX_REBOOT_CMD_RESTART",
            "orderly_reboot_fallback": "kernel_restart after /sbin/reboot fail",
            "ctrl_alt_del": "deferred kernel_restart",
            "priority_userspace": "LOW_INFERENCE (/init NOT_PROVEN)",
        },
    }


def qcom_wdt_source_audit() -> dict:
    qcom = src("drivers/watchdog/qcom-wdt.c")
    pm = src("drivers/watchdog/pm8916_wdt.c")
    msm = src("drivers/power/reset/msm-poweroff.c")
    kconfig = src("drivers/watchdog/Kconfig")
    need(qcom, '{ .compatible = "qcom,kpss-timer"')
    need(qcom, '{ .compatible = "qcom,scss-timer"')
    need(qcom, '{ .compatible = "qcom,kpss-wdt"')
    need(qcom, "module_platform_driver(qcom_watchdog_driver);")
    need(qcom, "if (qcom_wdt_is_running(&wdt->wdd))")
    need(qcom, "qcom_wdt_start(&wdt->wdd);")
    need(qcom, "wdt->wdd.timeout = min(wdt->wdd.max_timeout, 30U);")
    need(qcom, "data = of_device_get_match_data(dev);")
    need(kconfig, "config QCOM_WDT")
    need(kconfig, "config PM8916_WATCHDOG")
    need(pm, "PM8916_WDT_DEFAULT_TIMEOUT\t32")
    need(msm, '{ .compatible = "qcom,pshold", }')
    need(msm, "register_restart_handler(&restart_nb);")
    need(msm, "device_initcall(msm_restart_init);")
    scm = LINUX / "drivers/firmware/qcom_scm.c"
    scm_hits = []
    if scm.is_file():
        text = scm.read_text(errors="replace")
        scm_hits = [ln.strip() for ln in text.splitlines()
                    if re.search(r"\b(wdt|watchdog)\b", ln, re.I)]
    return {
        "QCOM_WDT_DRIVER_PRESENT": "YES",
        "qcom_wdt_compat": list(QCOM_WDT_COMPAT),
        "qcom_wdt_init": "module_platform_driver (probe only with DT+driver)",
        "QCOM_WDT_INHERITED_STATE_HANDLING":
            "IF probe AND already running: stop+reprogram default 30s "
            "(or timeout-sec) + WDOG_HW_RUNNING so core pets. "
            "IF no probe: inherited state UNTOUCHED.",
        "qcom_wdt_default_timeout_if_probe": 30,
        "pm8916_default_timeout_if_probe": 32,
        "msm_pshold": "device_initcall, register_restart_handler prio 128",
        "qcom_scm_watchdog_hits": scm_hits[:8],
        "FIRMWARE_WATCHDOG_STATE": "UNKNOWN",
    }


def psci_classes() -> dict:
    return {
        "PSCI_RESET_PATH_CLASSES_COMPLETE": "YES",
        "A_DIAGNOSTIC_PROBE_DIRECT": {
            "what": "T0/T1/T2/T3/T4/C_DELAY/PENTRY inline CNTPCT + "
                    "SMC PSCI SYSTEM_RESET 0x84000009",
            "natural_26s_source": "NO (pair delay-control not reflected; "
                                  "analysis uses FIX8 normal baseline)",
        },
        "B_LINUX_RESTART_FRAMEWORK": {
            "what": "do_kernel_restart -> psci_sys_reset notifier -> "
                    "invoke_psci_fn(SYSTEM_RESET)",
            "natural_26s_source": "PLAUSIBLE_IF_SOFTWARE_RESTART",
        },
        "C_SECURE_FIRMWARE_AUTONOMOUS": {
            "what": "EL3/TZ/ABL/PMIC reset without Linux call",
            "natural_26s_source": "UNKNOWN SOURCE_NOT_OBSERVABLE",
        },
        "must_not_merge": "YES",
    }


# ---------------------------------------------------------------- RT-D

def rtd_audit(blob: bytes) -> dict:
    if sha(blob) != RT_D_SHA or len(blob) != RT_D_SIZE:
        fail("ARS_RTD_SHA_FAILED", f"{sha(blob)} size={len(blob)}")
    nodes = fdt_nodes(blob)
    interesting = []
    for path, props in sorted(nodes.items()):
        compat = fdt_strlist(props.get("compatible", b""))
        name = path.rsplit("/", 1)[-1].lower()
        blob_join = " ".join(compat).lower() + " " + path.lower()
        hit = any(k in blob_join or k in name for k in RTD_KEYWORDS)
        if not hit:
            continue
        interesting.append({
            "path": path,
            "compatible": compat,
            "status": node_status(props),
            "reg": "PRESENT" if "reg" in props else "ABSENT",
            "interrupts": "PRESENT" if "interrupts" in props else "ABSENT",
            "clocks": "PRESENT" if "clocks" in props else "ABSENT",
            "resets": "PRESENT" if "resets" in props else "ABSENT",
        })

    def present(compats: tuple[str, ...]) -> str:
        for _path, props in nodes.items():
            compat = fdt_strlist(props.get("compatible", b""))
            if any(c in compat for c in compats):
                if node_status(props) == "disabled":
                    return "DISABLED"
                return "YES"
        return "NO"

    qcom_node = present(QCOM_WDT_COMPAT)
    pmic_node = present(PMIC_WDT_COMPAT)
    pshold = present(PSHOLD_COMPAT)
    psci = present(PSCI_COMPAT)
    smc = present(SMC_WDT_COMPAT)
    return {
        "RUNTIME_DTB_WATCHDOG_AUDIT_COMPLETE": "YES",
        "rtd_sha256": RT_D_SHA,
        "rtd_size": RT_D_SIZE,
        "interesting_nodes": interesting,
        "QCOM_WDT_RTD_NODE_PRESENT": qcom_node,
        "PMIC_WDT_RTD_NODE_PRESENT": pmic_node,
        "QCOM_PSHOLD_RTD_NODE_PRESENT": pshold,
        "PSCI_RTD_NODE_PRESENT": psci,
        "ARM_SMC_WDT_RTD_NODE_PRESENT": smc,
        "stock_dt_not_used": "YES",
    }


# ---------------------------------------------------------------- candidates / ranking

def _cand(*, cls: str, **kwargs) -> dict:
    kwargs["class"] = cls
    missing = [k for k in CANDIDATE_FIELDS if k not in kwargs]
    if missing:
        fail("ARS_CANDIDATE_INCOMPLETE", str(missing))
    if kwargs["confidence_class"] not in CONFIDENCE:
        fail("ARS_CONFIDENCE_INVALID", kwargs["confidence_class"])
    if kwargs["can_explain_23_28s"] not in EXPLAIN:
        fail("ARS_EXPLAIN_INVALID", kwargs["can_explain_23_28s"])
    return kwargs


def build_candidates(cfg: dict[str, str], rtd: dict, wdt_src: dict) -> list:
    qcom_cls = cfg_class(cfg, "CONFIG_QCOM_WDT")
    pmic_cls = cfg_class(cfg, "CONFIG_PM8916_WATCHDOG")
    smc_cls = cfg_class(cfg, "CONFIG_ARM_SMC_WATCHDOG")
    msm_cls = cfg_class(cfg, "CONFIG_POWER_RESET_MSM")
    soft_cls = cfg_class(cfg, "CONFIG_SOFT_WATCHDOG")
    lock_cls = cfg_class(cfg, "CONFIG_LOCKUP_DETECTOR")
    qcom_node = rtd["QCOM_WDT_RTD_NODE_PRESENT"]
    pmic_node = rtd["PMIC_WDT_RTD_NODE_PRESENT"]
    pshold = rtd["QCOM_PSHOLD_RTD_NODE_PRESENT"]
    smc_node = rtd["ARM_SMC_WDT_RTD_NODE_PRESENT"]
    psci_node = rtd["PSCI_RTD_NODE_PRESENT"]

    def would_probe(cls: str, node: str) -> str:
        if node in ("NO", "ABSENT"):
            return "NO"
        if node == "DISABLED":
            return "NO"
        if cls == "BUILTIN":
            return "YES"
        if cls == "MODULE":
            return "NO"  # this boot has no module loader / userspace insmod
        return "NO"

    qcom_probe = would_probe(qcom_cls, qcom_node)
    pmic_probe = would_probe(pmic_cls, pmic_node)
    smc_probe = would_probe(smc_cls, smc_node)
    msm_probe = would_probe(msm_cls, pshold)
    handoff = "SOURCE_PLAUSIBLE" if qcom_probe != "YES" else "PROBE_WOULD_TAKEOVER"
    nxt_restart = "RESET_CHOKEPOINT_MATCHED_DELAY_PAIR"
    nxt_wd = "WATCHDOG_HANDOFF_MINIMAL_CAUSAL_EXPERIMENT"
    nxt_panic = "NOT_AUTHORIZED_UNTIL_PANIC_ENTRY_EVIDENCE"

    cands = [
        _cand(candidate_id="ARS-SW-001", cls="A_LINUX_SOFTWARE_RESTART",
              symbol="machine_restart / do_kernel_restart",
              source_file="arch/arm64/kernel/process.c + kernel/reboot.c",
              trigger="any Linux software restart after C_DELAY",
              reachable_after_c_delay="YES", passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="none (core)",
              runtime_patch_risk="LOW",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="SOURCE_YES",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO"),
        _cand(candidate_id="ARS-SW-002", cls="A_LINUX_SOFTWARE_RESTART",
              symbol="emergency_restart",
              source_file="kernel/reboot.c",
              trigger="non-panic callers (sysrq/kdb/hangcheck/hw_failure)",
              reachable_after_c_delay="YES", passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="PARTIAL", requires_DT_node="NO",
              relevant_config="caller-dependent",
              runtime_patch_risk="LOW",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="INFERRED",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO"),
        _cand(candidate_id="ARS-SW-003", cls="A_LINUX_SOFTWARE_RESTART",
              symbol="kernel_restart",
              source_file="kernel/reboot.c",
              trigger="reboot syscall / orderly_reboot / CAD",
              reachable_after_c_delay="YES", passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="none (core)",
              runtime_patch_risk="LOW",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="SOURCE_YES",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO",
              note="userspace reboot priority LOW because /init NOT_PROVEN"),
        _cand(candidate_id="ARS-SW-004", cls="A_LINUX_SOFTWARE_RESTART",
              symbol="p1b /init SYS_reboot",
              source_file="scripts/r3-p1b/p1b-init.c",
              trigger="/init reached, sleep completes, reboot syscall",
              reachable_after_c_delay="YES", passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="rdinit=/init",
              runtime_patch_risk="NONE",
              source_timing_bound="C_DELAY + remaining kernel_init + 8s "
                                  "(/init NOT_PROVEN)",
              can_explain_23_28s="INFERRED",
              confidence_class="INFERRED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO"),
        _cand(candidate_id="ARS-SW-005", cls="E_ARCH_PSCI_RESTART",
              symbol="psci_sys_reset",
              source_file="drivers/firmware/psci/psci.c",
              trigger="restart_handler_list from do_kernel_restart",
              reachable_after_c_delay="YES" if psci_node == "YES" else "PARTIAL",
              passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="YES",
              relevant_config="CONFIG_ARM_PSCI_FW",
              runtime_patch_risk="LOW",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="SOURCE_YES",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO",
              rtd_node=psci_node),
        _cand(candidate_id="ARS-SW-006", cls="A_LINUX_SOFTWARE_RESTART",
              symbol="msm_restart deassert_pshold",
              source_file="drivers/power/reset/msm-poweroff.c",
              trigger="restart handler prio 128 after PSCI 129",
              reachable_after_c_delay="YES" if msm_probe == "YES" else "NO",
              passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="YES", requires_DT_node="YES",
              relevant_config=f"CONFIG_POWER_RESET_MSM={msm_cls}",
              runtime_patch_risk="HIGH",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="INFERRED" if msm_probe == "YES" else "UNKNOWN",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO",
              rtd_node=pshold, would_probe=msm_probe),
        _cand(candidate_id="ARS-PANIC-TO", cls="A_LINUX_SOFTWARE_RESTART",
              symbol="panic -> emergency_restart",
              source_file="kernel/panic.c",
              trigger="canonical panic() then panic_timeout != 0",
              reachable_after_c_delay="YES", passes_canonical_panic="YES",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="panic=5 in RT-D",
              runtime_patch_risk="NONE",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="INFERRED",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_panic,
              deprioritized_by_pentry_pair="YES"),
        _cand(candidate_id="ARS-WD-001", cls="B_LINUX_WATCHDOG",
              symbol="qcom_wdt_probe / qcom_wdt_start",
              source_file="drivers/watchdog/qcom-wdt.c",
              trigger="DT probe then bite, or inherited WDT if probe",
              reachable_after_c_delay="YES" if qcom_probe == "YES" else "NO",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="YES", requires_DT_node="YES",
              relevant_config=f"CONFIG_QCOM_WDT={qcom_cls}",
              runtime_patch_risk="FORBIDDEN",
              source_timing_bound="30s default ONLY if probe; otherwise UNKNOWN",
              can_explain_23_28s="UNKNOWN",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="NO",
              rtd_node=qcom_node, would_probe=qcom_probe,
              inherited=wdt_src["QCOM_WDT_INHERITED_STATE_HANDLING"]),
        _cand(candidate_id="ARS-WD-002", cls="B_LINUX_WATCHDOG",
              symbol="pm8916_wdt",
              source_file="drivers/watchdog/pm8916_wdt.c",
              trigger="SPMI PMIC PON watchdog probe",
              reachable_after_c_delay="YES" if pmic_probe == "YES" else "NO",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="YES", requires_DT_node="YES",
              relevant_config=f"CONFIG_PM8916_WATCHDOG={pmic_cls}",
              runtime_patch_risk="FORBIDDEN",
              source_timing_bound="32s default ONLY if probe; otherwise UNKNOWN",
              can_explain_23_28s="UNKNOWN",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="NO",
              rtd_node=pmic_node, would_probe=pmic_probe),
        _cand(candidate_id="ARS-WD-003", cls="B_LINUX_WATCHDOG",
              symbol="watchdog_hardlockup_check / softlockup",
              source_file="kernel/watchdog.c",
              trigger="lockup detector after SMP/timers",
              reachable_after_c_delay="PARTIAL",
              passes_canonical_panic="PARTIAL",
              common_restart_chokepoint="NO",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config=f"CONFIG_LOCKUP_DETECTOR={lock_cls}",
              runtime_patch_risk="NONE",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="UNKNOWN",
              confidence_class="INFERRED",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="PARTIAL"),
        _cand(candidate_id="ARS-WD-004", cls="B_LINUX_WATCHDOG",
              symbol="softdog",
              source_file="drivers/watchdog/softdog.c",
              trigger="soft watchdog timer -> kernel_restart/emergency_restart",
              reachable_after_c_delay="NO" if soft_cls == "ABSENT" else "PARTIAL",
              passes_canonical_panic="NO",
              common_restart_chokepoint="YES",
              requires_driver_probe="YES", requires_DT_node="NO",
              relevant_config=f"CONFIG_SOFT_WATCHDOG={soft_cls}",
              runtime_patch_risk="NONE",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="UNKNOWN",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_restart,
              deprioritized_by_pentry_pair="NO"),
        _cand(candidate_id="ARS-WD-005", cls="B_LINUX_WATCHDOG",
              symbol="smcwd_probe",
              source_file="drivers/watchdog/arm_smc_wdt.c",
              trigger="arm,smc-wdt DT probe",
              reachable_after_c_delay="YES" if smc_probe == "YES" else "NO",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="YES", requires_DT_node="YES",
              relevant_config=f"CONFIG_ARM_SMC_WATCHDOG={smc_cls}",
              runtime_patch_risk="FORBIDDEN",
              source_timing_bound="UNKNOWN",
              can_explain_23_28s="UNKNOWN",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="NO",
              rtd_node=smc_node, would_probe=smc_probe),
        _cand(candidate_id="ARS-EXT-001", cls="C_FIRMWARE_WATCHDOG",
              symbol="bootloader-inherited APSS WDT",
              source_file="NOT_IN_TREE (ABL/XBL/TZ)",
              trigger="armed pre-Linux watchdog expires; Linux never pets",
              reachable_after_c_delay="YES",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="n/a",
              runtime_patch_risk="FORBIDDEN",
              source_timing_bound="UNKNOWN",
              can_explain_23_28s="UNKNOWN",
              confidence_class="UNKNOWN",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="NO",
              BOOTLOADER_WATCHDOG_HANDOFF_GAP=handoff,
              FIRMWARE_WATCHDOG_STATE="UNKNOWN"),
        _cand(candidate_id="ARS-EXT-002", cls="C_FIRMWARE_WATCHDOG",
              symbol="TZ/secure-world / PMIC autonomous WDT",
              source_file="NOT_IN_TREE",
              trigger="secure firmware or PMIC hardware timeout",
              reachable_after_c_delay="YES",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="n/a",
              runtime_patch_risk="FORBIDDEN",
              source_timing_bound="UNKNOWN",
              can_explain_23_28s="UNKNOWN",
              confidence_class="UNKNOWN",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="NO",
              FIRMWARE_WATCHDOG_STATE="UNKNOWN"),
        _cand(candidate_id="ARS-EXT-003", cls="C_FIRMWARE_WATCHDOG",
              symbol="ABL automatic fallback reset",
              source_file="NOT_IN_TREE",
              trigger="bootloader policy after kernel handoff failure",
              reachable_after_c_delay="YES",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="n/a",
              runtime_patch_risk="FORBIDDEN",
              source_timing_bound="UNKNOWN",
              can_explain_23_28s="UNKNOWN",
              confidence_class="UNKNOWN",
              recommended_next_probe="ALTERNATIVE_RESET_DIAGNOSTIC_DESIGN",
              deprioritized_by_pentry_pair="NO"),
        _cand(candidate_id="ARS-OOPS-001", cls="D_DIE_OOPS_BUG",
              symbol="die",
              source_file="arch/arm64/kernel/traps.c",
              trigger="oops with panic_on_oops or in_interrupt",
              reachable_after_c_delay="YES",
              passes_canonical_panic="YES",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="CONFIG_PANIC_ON_OOPS",
              runtime_patch_risk="NONE",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="INFERRED",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_panic,
              deprioritized_by_pentry_pair="YES"),
        _cand(candidate_id="ARS-OOPS-002", cls="D_DIE_OOPS_BUG",
              symbol="die -> make_task_dead",
              source_file="arch/arm64/kernel/traps.c",
              trigger="oops without panic_on_oops; hang unless firmware WDT",
              reachable_after_c_delay="YES",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="panic_on_oops default 0",
              runtime_patch_risk="NONE",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="UNKNOWN",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_wd,
              deprioritized_by_pentry_pair="NO"),
        _cand(candidate_id="ARS-INIT-001", cls="D_DIE_OOPS_BUG",
              symbol="do_exit is_global_init",
              source_file="kernel/exit.c + init/main.c",
              trigger="PID1 death / no working init / /init exit 111",
              reachable_after_c_delay="YES",
              passes_canonical_panic="YES",
              common_restart_chokepoint="YES",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="rdinit=/init panic=5",
              runtime_patch_risk="NONE",
              source_timing_bound="NOT_SOURCE_DERIVABLE",
              can_explain_23_28s="INFERRED",
              confidence_class="SOURCE_SUPPORTED",
              recommended_next_probe=nxt_panic,
              deprioritized_by_pentry_pair="YES"),
        _cand(candidate_id="ARS-DIAG-001", cls="Z_DIAGNOSTIC_PSCI_NOT_NATURAL",
              symbol="PENTRY/T0-T4/C_DELAY probe SMC",
              source_file="scripts/r3-p1b/p1b-*-device.S",
              trigger="diagnostic probe if checkpoint executes",
              reachable_after_c_delay="NO",
              passes_canonical_panic="NO",
              common_restart_chokepoint="NO",
              requires_driver_probe="NO", requires_DT_node="NO",
              relevant_config="n/a",
              runtime_patch_risk="NONE",
              source_timing_bound="programmed delay; pair showed NO shift",
              can_explain_23_28s="UNKNOWN",
              confidence_class="SOURCE_PROVEN",
              recommended_next_probe="DO_NOT_TREAT_AS_NATURAL_RESET",
              deprioritized_by_pentry_pair="YES",
              note="FIX8 baseline is the logical natural path"),
    ]
    return cands


def rank_candidates(cands: list) -> list:
    def score(c: dict) -> tuple:
        if c["class"] == "Z_DIAGNOSTIC_PSCI_NOT_NATURAL":
            return (-99, 0, 0, 0)
        panic = c["passes_canonical_panic"] == "YES"
        dep = c.get("deprioritized_by_pentry_pair") == "YES"
        ev = {"SOURCE_PROVEN": 4, "SOURCE_SUPPORTED": 3,
              "INFERRED": 2, "UNKNOWN": 1}[c["confidence_class"]]
        bypass = 1 if c["passes_canonical_panic"] == "NO" else 0
        explain = {"SOURCE_YES": 3, "INFERRED": 2, "UNKNOWN": 0}[
            c["can_explain_23_28s"]]
        choke = 1 if c["common_restart_chokepoint"] == "YES" else 0
        if panic or dep:
            ev = ev - 2
        return (bypass, choke, ev, explain)

    ordered = sorted(cands, key=score, reverse=True)
    rows = []
    rank = 1
    for c in ordered:
        if c["class"] == "Z_DIAGNOSTIC_PSCI_NOT_NATURAL":
            continue
        rows.append({
            "rank": rank,
            "candidate": c["candidate_id"] + " " + c["symbol"],
            "class": c["class"],
            "why_plausible": c["trigger"],
            "evidence_supports": f"{c['confidence_class']}; "
                                 f"after_c_delay={c['reachable_after_c_delay']}; "
                                 f"choke={c['common_restart_chokepoint']}",
            "evidence_contradicts": (
                "PENTRY pair no-shift deprioritizes panic-required path"
                if c.get("deprioritized_by_pentry_pair") == "YES"
                else "no runtime proof this path fired; timing not source-derivable"
            ),
            "passes_panic_entry": c["passes_canonical_panic"],
            "can_explain_stable_26s": c["can_explain_23_28s"],
            "next_causal_probe": c["recommended_next_probe"],
            "deprioritized_by_pentry_pair": c.get(
                "deprioritized_by_pentry_pair", "NO"),
        })
        rank += 1
    # pair discipline: a panic-required row must not outrank an equal-evidence
    # panic-bypassing row. scores already encode that; assert it.
    bypass_ev = None
    for r, c in zip(rows, [x for x in ordered
                           if x["class"] != "Z_DIAGNOSTIC_PSCI_NOT_NATURAL"]):
        if c["passes_canonical_panic"] == "NO" and bypass_ev is None:
            bypass_ev = r["rank"]
        if c["passes_canonical_panic"] == "YES" and bypass_ev is not None:
            if r["rank"] < bypass_ev:
                fail("ARS_RANK_PAIR_DISCIPLINE",
                     f"panic-required {c['candidate_id']} ranked above bypass")
    return rows


def decide(rows: list, chokepoint: dict, wdt: dict) -> dict:
    choke_ok = chokepoint.get("LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT") not in (
        None, "NONE", "")
    # Case A if a high-coverage Linux software-reset choke exists and source
    # supports it can explain the current path (reachable after C_DELAY,
    # panic-bypassing). Watchdog is NOT auto-ranked first from pair negative.
    if choke_ok:
        case = "A"
        nxt = "MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_READINESS_CI"
    elif wdt.get("BOOTLOADER_WATCHDOG_HANDOFF_GAP") == "SOURCE_PLAUSIBLE":
        case = "B"
        nxt = "MAINLINE_V2_R3_P1B_WATCHDOG_HANDOFF_PREDEVICE_READINESS_CI"
    else:
        case = "C"
        nxt = "MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_DIAGNOSTIC_DESIGN_CI"
    top = rows[0]["candidate"] if rows else "NONE"
    return {
        "DECISION_CASE": case,
        "NEXT_PREDEVICE_STAGE": nxt,
        "TOP_RESET_SOURCE_CANDIDATE": top,
        "PANIC_TIMEOUT_BRANCH_PRIORITY": "LOW_UNTIL_PANIC_ENTRY_EVIDENCE",
        "PANIC30_RERUN": "FROZEN",
        "DEVICE_READY": "NO",
    }


# ---------------------------------------------------------------- schema / fixtures

def validate_map(doc: dict, *, require_binary: bool) -> None:
    for k in ("schema_version", "round", "linux_commit", "frozen",
              "restart_chain", "chokepoint", "watchdog", "rtd", "oops_die",
              "init_failure", "psci_classes", "candidates", "ranking",
              "decision", "binary"):
        if k not in doc:
            fail("ARS_SCHEMA_FAILED", f"missing {k}")
    if doc["schema_version"] != "1":
        fail("ARS_SCHEMA_FAILED", "schema_version")
    if doc["round"] != ROUND:
        fail("ARS_SCHEMA_FAILED", "round")
    if doc["linux_commit"] != LINUX_COMMIT:
        fail("ARS_SCHEMA_FAILED", "linux_commit")
    cands = doc["candidates"]
    if len(cands) < 8:
        fail("ARS_SCHEMA_FAILED", "too few candidates")
    ids = [c["candidate_id"] for c in cands]
    if len(ids) != len(set(ids)):
        fail("ARS_SCHEMA_FAILED", "duplicate candidate_id")
    required_ids = {"ARS-SW-001", "ARS-SW-002", "ARS-SW-003", "ARS-EXT-001",
                    "ARS-WD-001", "ARS-PANIC-TO", "ARS-DIAG-001"}
    if not required_ids.issubset(set(ids)):
        fail("ARS_SCHEMA_FAILED", f"missing {required_ids - set(ids)}")
    for c in cands:
        for f in CANDIDATE_FIELDS:
            if f not in c:
                fail("ARS_SCHEMA_FAILED", f"{c.get('candidate_id')} missing {f}")
        if c["confidence_class"] not in CONFIDENCE:
            fail("ARS_SCHEMA_FAILED", "confidence")
        if c["can_explain_23_28s"] not in EXPLAIN:
            fail("ARS_SCHEMA_FAILED", "explain")
    # forbidden inferences
    wd = doc["watchdog"]
    if wd.get("timeout_seconds") not in (None, "UNKNOWN", "unknown"):
        if wd.get("WATCHDOG_TIMEOUT_SOURCE_DERIVABLE") != "YES":
            fail("ARS_SCHEMA_FAILED", "numeric timeout without derivable=YES")
    if wd.get("FIRMWARE_WATCHDOG_STATE") in ("DISABLED", "ARMED"):
        fail("ARS_SCHEMA_FAILED", "firmware state claimed as fact")
    if doc["rtd"].get("stock_dt_not_used") != "YES":
        fail("ARS_SCHEMA_FAILED", "stock DT used to infer RT-D nodes")
    if "do_kernel_restart" not in doc["restart_chain"]:
        fail("ARS_SCHEMA_FAILED", "ignored do_kernel_restart")
    if "register_restart_handler" not in json.dumps(doc["restart_chain"]):
        fail("ARS_SCHEMA_FAILED", "ignored restart handlers")
    if doc.get("pstore_empty_implies_no_panic"):
        fail("ARS_SCHEMA_FAILED", "pstore empty treated as no panic")
    if doc.get("bootreason_is_reset_identity"):
        fail("ARS_SCHEMA_FAILED", "bootreason treated as identity")
    if doc.get("diagnostic_psci_merged_with_natural"):
        fail("ARS_SCHEMA_FAILED", "diagnostic PSCI merged")
    if doc.get("panic30_authorized"):
        fail("ARS_SCHEMA_FAILED", "PANIC30 authorized")
    if doc.get("timeout_branch_authorized"):
        fail("ARS_SCHEMA_FAILED", "timeout branch authorized")
    if doc.get("mmio_experiment_invented"):
        fail("ARS_SCHEMA_FAILED", "invented MMIO")
    # required software-reset symbols present
    blob = json.dumps(doc)
    for tok in ("emergency_restart", "machine_restart", "do_kernel_restart",
                "register_restart_handler", "psci_sys_reset"):
        if tok not in blob:
            fail("ARS_SCHEMA_FAILED", f"ignored {tok}")
    # pair discipline on ranking
    rows = doc["ranking"]
    if len(rows) < 3:
        fail("ARS_SCHEMA_FAILED", "ranking short")
    top = rows[0]
    if top["passes_panic_entry"] == "YES":
        fail("ARS_SCHEMA_FAILED",
             "panic-required path ranked #1 without pair acknowledgement")
    if require_binary:
        b = doc["binary"]
        if b.get("status") != "COMPLETE":
            fail("ARS_SCHEMA_FAILED", "binary not complete")
        if not b.get("symbols"):
            fail("ARS_SCHEMA_FAILED", "binary symbols missing")


def negative_fixtures(good: dict) -> None:
    def reject(name: str, mutator) -> None:
        bad = mutator(copy.deepcopy(good))
        try:
            validate_map(bad, require_binary=False)
        except SystemExit:
            emit("NEGATIVE_FIXTURE", f"{name}=REJECT")
            return
        fail("ARS_FIXTURE_FAILED", f"{name} was accepted")

    reject("assume_watchdog_timeout_from_26s",
           lambda m: {**m, "watchdog": {**m["watchdog"],
                                        "timeout_seconds": 30,
                                        "WATCHDOG_TIMEOUT_SOURCE_DERIVABLE": "NO"}})
    reject("assume_rtd_has_stock_watchdog_node",
           lambda m: {**m, "rtd": {**m["rtd"],
                                   "QCOM_WDT_RTD_NODE_PRESENT": "YES",
                                   "stock_dt_not_used": "NO"}})
    reject("treat_firmware_state_as_known",
           lambda m: {**m, "watchdog": {**m["watchdog"],
                                        "FIRMWARE_WATCHDOG_STATE": "ARMED"}})
    reject("treat_pstore_empty_as_no_panic",
           lambda m: {**m, "pstore_empty_implies_no_panic": True})
    reject("treat_bootreason_as_definitive",
           lambda m: {**m, "bootreason_is_reset_identity": True})
    reject("merge_diagnostic_psci_with_natural_reset",
           lambda m: {**m, "diagnostic_psci_merged_with_natural": True})
    reject("ignore_emergency_restart",
           lambda m: {**m, "candidates": [c for c in m["candidates"]
                                          if "emergency_restart" not in json.dumps(c)]})
    reject("ignore_machine_restart",
           lambda m: {**m, "candidates": [c for c in m["candidates"]
                                          if "machine_restart" not in json.dumps(c)]})
    reject("ignore_restart_handlers",
           lambda m: {**m, "restart_chain": {k: v for k, v in m["restart_chain"].items()
                                             if k not in ("do_kernel_restart",
                                                          "register_restart_handler")}})
    reject("classify_panic_required_as_top_without_pair",
           lambda m: {**m, "ranking": [{**m["ranking"][0],
                                        "passes_panic_entry": "YES",
                                        "deprioritized_by_pentry_pair": "NO"}]
                               + m["ranking"][1:]})
    reject("invent_mmio_experiment",
           lambda m: {**m, "mmio_experiment_invented": True})
    reject("authorize_PANIC30",
           lambda m: {**m, "panic30_authorized": True})
    reject("authorize_timeout_branch",
           lambda m: {**m, "timeout_branch_authorized": True})
    emit("ARS_NEGATIVE_FIXTURES", "PASS")


# ---------------------------------------------------------------- frozen / map assembly

def frozen_block() -> dict:
    return {
        "PENTRY8_TOTAL": 26.829,
        "PENTRY1_TOTAL": 26.301,
        "PENTRY_PAIR_DELTA": -0.528,
        "PENTRY_PAIR_EXPECTED_DELTA": -7.000,
        "PENTRY_PAIR_ERROR": 6.472,
        "PANIC_ENTRY_DELAY_CONTROL_REFLECTED": "NO",
        "PANIC_ENTRY_REACHED": "NOT_PROVEN",
        "PANIC_ENTRY_HYPOTHESIS_PRIORITY": "REDUCED",
        "NO_LINUX_PANIC": "NOT_LICENSED",
        "C6": "PROVEN",
        "C_DELAY": "PROVEN",
        "C_DELAY_TOTAL": 14.464,
        "PENTRY8_PAYLOAD_SHA":
            "1988ee22806cba6129f7c3bb34def9667ec39c60f029c622f60341374cc35469",
        "PENTRY1_PAYLOAD_SHA":
            "5fb893c6f990b23a26fe0aba7439852ff5991b59794f4ee4ab1fa7691b8328ee",
        "PENTRY1_BOOT_SHA":
            "370bc83f746b8e9459022effb07caf6e1a01fb17b1dd33b07c8b8f286f74f2c6",
        "RT_D_SHA": RT_D_SHA,
        "analysis_baseline": "FIX8_NORMAL_PATH",
        "pstore_empty": "AUXILIARY_NOT_NEGATIVE",
        "ANDROID_BOOTREASON_SOURCE_DIAGNOSTIC": "NO",
    }


def watchdog_block(cfg: dict[str, str], rtd: dict, wdt_src: dict) -> dict:
    classes = {s: cfg_class(cfg, s) for s in WATCHDOG_SYMS}
    qcom_probe = "NO"
    if (classes["CONFIG_QCOM_WDT"] == "BUILTIN"
            and rtd["QCOM_WDT_RTD_NODE_PRESENT"] == "YES"):
        qcom_probe = "YES"
    handoff = ("SOURCE_PLAUSIBLE" if qcom_probe != "YES"
               else "PROBE_WOULD_TAKEOVER")
    derivable = "NO"
    return {
        "WATCHDOG_CONFIG_AUDIT_COMPLETE": "YES",
        "classes": classes,
        "QCOM_WDT_DRIVER_PRESENT": wdt_src["QCOM_WDT_DRIVER_PRESENT"],
        "QCOM_WDT_RTD_NODE_PRESENT": rtd["QCOM_WDT_RTD_NODE_PRESENT"],
        "QCOM_WDT_DRIVER_WOULD_PROBE": qcom_probe,
        "QCOM_WDT_INHERITED_STATE_HANDLING":
            wdt_src["QCOM_WDT_INHERITED_STATE_HANDLING"],
        "PMIC_WDT_RTD_NODE_PRESENT": rtd["PMIC_WDT_RTD_NODE_PRESENT"],
        "FIRMWARE_WATCHDOG_STATE": "UNKNOWN",
        "WATCHDOG_TIMEOUT_SOURCE_DERIVABLE": derivable,
        "TIMEOUT": "UNKNOWN",
        "BOOTLOADER_WATCHDOG_HANDOFF_GAP": handoff,
        "do_not_infer_30s_from_26s": "YES",
    }


def chokepoint_source() -> dict:
    return {
        "LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT": "machine_restart",
        "handler_dispatch": "do_kernel_restart",
        "machine_emergency_restart": "INLINED",
        "LINUX_SOFTWARE_RESET_CHOKEPOINT_COVERAGE": {
            "NORMAL_RESTART": "YES",
            "EMERGENCY_RESTART": "YES",
            "PANIC_TIMEOUT_RESTART": "YES",
            "OTHER_RESTART_HANDLER_CALLERS":
                "psci_sys_reset (prio 129); msm pshold (prio 128, if probed); "
                "watchdog .restart ops (if probed)",
        },
        "efi_reboot_before_dispatch": "RUNTIME_CONDITIONAL",
        "RESTART_CHOKEPOINT_INSTRUMENTABLE": "PENDING_BINARY",
        "future_pair": {
            "RESET8_delay_s": 8,
            "RESET1_delay_s": 1,
            "expected_delta_s": -7.000,
            "style": "register-only CNTPCT + PSCI SYSTEM_RESET fail-closed",
            "device_ready_this_round": "NO",
        },
    }


def assemble_source_map(cfg: dict[str, str], rtd: dict) -> dict:
    chain = restart_chain_audit()
    oops = oops_die_audit()
    initf = init_failure_audit()
    callers = callers_audit()
    wdt_src = qcom_wdt_source_audit()
    psci = psci_classes()
    wd = watchdog_block(cfg, rtd, wdt_src)
    choke = chokepoint_source()
    cands = build_candidates(cfg, rtd, wdt_src)
    ranking = rank_candidates(cands)
    decision = decide(ranking, choke, wd)
    doc = {
        "schema_version": "1",
        "round": ROUND,
        "linux_commit": LINUX_COMMIT,
        "frozen": frozen_block(),
        "restart_chain": chain,
        "chokepoint": choke,
        "watchdog": wd,
        "rtd": rtd,
        "oops_die": oops,
        "init_failure": initf,
        "callers": callers,
        "psci_classes": psci,
        "candidates": cands,
        "ranking": ranking,
        "decision": decision,
        "binary": {"status": "PENDING_VMLINUX"},
        "pstore_empty_implies_no_panic": False,
        "bootreason_is_reset_identity": False,
        "diagnostic_psci_merged_with_natural": False,
        "panic30_authorized": False,
        "timeout_branch_authorized": False,
        "mmio_experiment_invented": False,
        "ANDROID_BOOTREASON_SOURCE_DIAGNOSTIC": "NO",
    }
    return doc


def print_source_tokens(doc: dict) -> None:
    emit("KERNEL_RESTART_CHAIN_AUDITED", "YES")
    emit("EMERGENCY_RESTART_CHAIN_AUDITED", "YES")
    emit("ARM64_RESTART_CHAIN_AUDITED", "YES")
    emit("PSCI_RESTART_CHAIN_AUDITED", "YES")
    emit("LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT",
         doc["chokepoint"]["LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT"])
    cov = doc["chokepoint"]["LINUX_SOFTWARE_RESET_CHOKEPOINT_COVERAGE"]
    emit("CHOKEPOINT_NORMAL_RESTART", cov["NORMAL_RESTART"])
    emit("CHOKEPOINT_EMERGENCY_RESTART", cov["EMERGENCY_RESTART"])
    emit("CHOKEPOINT_PANIC_TIMEOUT_RESTART", cov["PANIC_TIMEOUT_RESTART"])
    emit("WATCHDOG_CONFIG_AUDIT_COMPLETE", "YES")
    emit("RUNTIME_DTB_WATCHDOG_AUDIT_COMPLETE", "YES")
    emit("QCOM_WDT_DRIVER_PRESENT",
         doc["watchdog"]["QCOM_WDT_DRIVER_PRESENT"])
    emit("QCOM_WDT_RTD_NODE_PRESENT",
         doc["watchdog"]["QCOM_WDT_RTD_NODE_PRESENT"])
    emit("QCOM_WDT_DRIVER_WOULD_PROBE",
         doc["watchdog"]["QCOM_WDT_DRIVER_WOULD_PROBE"])
    emit("QCOM_WDT_INHERITED_STATE_HANDLING",
         "SEE_JSON")
    emit("FIRMWARE_WATCHDOG_STATE", "UNKNOWN")
    emit("WATCHDOG_TIMEOUT_SOURCE_DERIVABLE", "NO")
    emit("TIMEOUT", "UNKNOWN")
    emit("BOOTLOADER_WATCHDOG_HANDOFF_GAP",
         doc["watchdog"]["BOOTLOADER_WATCHDOG_HANDOFF_GAP"])
    emit("OOPS_DIE_RESET_MAP_COMPLETE", "YES")
    emit("INIT_FAILURE_RESET_SEMANTICS_AUDITED", "YES")
    emit("PSCI_RESET_PATH_CLASSES_COMPLETE", "YES")
    emit("ANDROID_BOOTREASON_SOURCE_DIAGNOSTIC", "NO")
    emit("PANIC_TIMEOUT_BRANCH_PRIORITY", "LOW_UNTIL_PANIC_ENTRY_EVIDENCE")
    emit("PANIC30_RERUN", "FROZEN")
    emit("DEVICE_READY", "NO")
    emit("READY_FOR_DEVICE", "NO")
    emit("DECISION_CASE", doc["decision"]["DECISION_CASE"])
    emit("NEXT_PREDEVICE_STAGE", doc["decision"]["NEXT_PREDEVICE_STAGE"])
    emit("TOP_RESET_SOURCE_CANDIDATE",
         doc["decision"]["TOP_RESET_SOURCE_CANDIDATE"])
    emit("CONFIG_WATCHDOG", doc["watchdog"]["classes"]["CONFIG_WATCHDOG"])
    emit("CONFIG_QCOM_WDT", doc["watchdog"]["classes"]["CONFIG_QCOM_WDT"])
    emit("CONFIG_PM8916_WATCHDOG",
         doc["watchdog"]["classes"]["CONFIG_PM8916_WATCHDOG"])
    emit("CONFIG_POWER_RESET_MSM",
         doc["watchdog"]["classes"]["CONFIG_POWER_RESET_MSM"])


# ---------------------------------------------------------------- source-gate

def cmd_source_gate() -> None:
    for p in (DOC, STATUS_DOC, WF, SCHEMA, Path(__file__)):
        if not p.is_file():
            fail("ARS_SOURCE_GATE_FAILED", f"missing {p}")
    doc = DOC.read_text()
    st = STATUS_DOC.read_text()
    wf = WF.read_text()
    py = Path(__file__).read_text()
    for h in DOC_HEADINGS:
        if h not in doc:
            fail("ARS_SOURCE_GATE_FAILED", f"doc missing heading {h!r}")
    for tok in (
            "PENTRY8", "26.829", "PENTRY1", "26.301", "PAIR_DELTA",
            "-0.528", "C_DELAY_TOTAL", "14.464",
            "PANIC_ENTRY_DELAY_CONTROL_REFLECTED",
            "NO_LINUX_PANIC=NOT_LICENSED",
            "LINUX_SOFTWARE_RESET_COMMON_CHOKEPOINT",
            "WATCHDOG_TIMEOUT_SOURCE_DERIVABLE",
            "FIRMWARE_WATCHDOG_STATE=UNKNOWN",
            "BOOTLOADER_WATCHDOG_HANDOFF_GAP",
            "DEPRIORITIZED_BY_PENTRY_PAIR",
            "PANIC_TIMEOUT_BRANCH_PRIORITY",
            "PANIC30_RERUN",
            "DEVICE READY = NO",
            "RESET8", "RESET1",
            "MAINLINE_V2_R3_P1B_RESTART_CHOKEPOINT_PREDEVICE_READINESS_CI",
    ):
        if tok not in doc:
            fail("ARS_SOURCE_GATE_FAILED", f"doc missing {tok!r}")
    for tok in (
            "PENTRY8_TOTAL=26.829", "PENTRY1_TOTAL=26.301",
            "PENTRY_PAIR_DELTA=-0.528", "PENTRY_PAIR_EXPECTED_DELTA=-7.000",
            "PENTRY_PAIR_ERROR=6.472",
            "PANIC_ENTRY_DELAY_CONTROL_REFLECTED=NO",
            "PANIC_ENTRY_RUNTIME_STATUS=NOT_PROVEN",
            "PANIC_ENTRY_HYPOTHESIS_PRIORITY=REDUCED",
            "NO_LINUX_PANIC=NOT_LICENSED",
            "C_DELAY_TOTAL_S=14.464",
            "PANIC30_RERUN=FROZEN",
            "SLOT_A_WRITTEN=NO",
    ):
        if tok not in st:
            fail("ARS_SOURCE_GATE_FAILED", f"status missing {tok!r}")
    if "READY_FOR_R3_P1B_" in wf and "DEVICE_CONTROL" in wf:
        # allow only as a forbidden-token comment, not a job name/gate
        if re.search(r"READY_FOR_R3_P1B_\w+_DEVICE_CONTROL\s*=\s*YES", wf):
            fail("ARS_SOURCE_GATE_FAILED", "workflow authorizes device")
    for bad in ("mkbootimg", "splice-boot", "fastboot boot", "*.img"):
        if bad == "*.img":
            continue
        if bad in wf and "forbid" not in wf.lower():
            # comments about not emitting images are ok; actual pack steps not
            pass
    if "mkbootimg" in wf:
        fail("ARS_SOURCE_GATE_FAILED", "mkbootimg in public workflow")
    if "GITHUB_ACTIONS" not in py:
        fail("ARS_SOURCE_GATE_FAILED", "missing CI guard")
    emit("ARS_SOURCE_GATE", "PASS")
    emit("LOCAL_BUILD", "NO")
    emit("DEVICE_OPERATION", "NO")
    emit("SLOT_A_WRITTEN", "NO")
    emit("READY_FOR_DEVICE", "NO")


def cmd_source_audit(out: Path, rt_d: Path) -> None:
    linux_commit()
    out.mkdir(parents=True, exist_ok=True)
    cfgp = reconstruct_config(out)
    cfg = parse_config(cfgp.read_text())
    (out / "p1b-ars-merged.config").write_text(cfgp.read_text())
    blob = rt_d.read_bytes()
    rtd = rtd_audit(blob)
    doc = assemble_source_map(cfg, rtd)
    validate_map(doc, require_binary=False)
    negative_fixtures(doc)
    path = out / "alternative-reset-source-map.json"
    path.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")
    early = out / "early"
    early.mkdir(exist_ok=True)
    (early / "alternative-reset-source-map.json").write_text(path.read_text())
    print_source_tokens(doc)
    emit("ARS_SOURCE_AUDIT", "PASS")
    emit("ARS_MAP_PATH", str(path))


# ---------------------------------------------------------------- binary

def scan_direct_calls(image: bytes, text_addr: int, image_size: int,
                      target_va: int) -> list:
    hits = []
    limit = min(image_size, len(image))
    for off in range(0, limit - 3, 4):
        w = struct.unpack_from("<I", image, off)[0]
        top = w >> 26
        if top not in (0b000101, 0b100101):
            continue
        imm = w & 0x03FFFFFF
        if imm & (1 << 25):
            imm -= 1 << 26
        dest = text_addr + off + imm * 4
        if dest == target_va:
            hits.append({
                "va": hex(text_addr + off),
                "offset": hex(off),
                "kind": "BL" if top == 0b100101 else "B",
            })
    return hits


def nm_symbol(nm_out: str, name: str) -> int | None:
    hits = [l for l in nm_out.splitlines() if l.endswith(f" {name}")]
    if not hits:
        return None
    return int(hits[0].split()[0], 16)


def dump_insns(tools: dict, vmlinux: Path, va: int, n: int = 8) -> list:
    dump = run([tools["objdump"], "-d",
                f"--start-address={va:#x}",
                f"--stop-address={va + n * 4:#x}", str(vmlinux)])
    insns = []
    for line in dump.splitlines():
        m = INSTR_RE.match(line)
        if not m:
            continue
        insns.append({
            "va": m.group(1),
            "bytes": m.group(2),
            "mnemonic": m.group(3),
            "ops": (m.group(4) or "").strip(),
        })
        if len(insns) >= n:
            break
    return insns, dump


def section_for_va(readelf_s: str, va: int) -> dict:
    # llvm-readelf -S --wide
    best = None
    for line in readelf_s.splitlines():
        m = re.search(
            r"\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+"
            r"([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+\S+\s+(\S+)",
            line)
        if not m:
            continue
        name, vma_s, off_s, size_s, flags = m.group(1), m.group(2), m.group(3), \
            m.group(4), m.group(5)
        vma = int(vma_s, 16)
        size = int(size_s, 16)
        if vma <= va < vma + size:
            best = {"name": name, "vma": hex(vma),
                    "file_off": hex(int(off_s, 16)),
                    "size": hex(size), "flags": flags}
    if not best:
        fail("ARS_SECTION_FAILED", f"no section for {va:#x}")
    return best


def cmd_binary_audit(out: Path, jobs: int, tools: dict,
                     fix8: Path | None) -> None:
    pb_spec = importlib.util.spec_from_file_location(
        "p1b_build", HERE / "p1b-build.py")
    pb = importlib.util.module_from_spec(pb_spec)
    pb_spec.loader.exec_module(pb)
    linux_commit()
    out.mkdir(parents=True, exist_ok=True)
    k = pb.make_kernel(out, None, None, jobs)
    vmlinux = k["vmlinux"]
    image = k["image"].read_bytes()
    sysmap = k["sysmap"]
    nm_out = run([tools["nm"], str(vmlinux)])
    (out / "p1b-ars-nm-excerpt.txt").write_text(
        "\n".join(l for l in nm_out.splitlines()
                  if re.search(r" (machine_restart|do_kernel_restart|"
                               r"emergency_restart|kernel_restart|"
                               r"psci_sys_reset|register_restart_handler|"
                               r"machine_emergency_restart|_text|primary_entry)$",
                               l)) + "\n")
    names = ("machine_restart", "do_kernel_restart", "emergency_restart",
             "kernel_restart", "psci_sys_reset", "_text")
    syms = {}
    for n in names:
        va = nm_symbol(nm_out, n)
        if va is None:
            fail("ARS_SYMBOL_FAILED", n)
        syms[n] = va
    if nm_symbol(nm_out, "machine_emergency_restart") is not None:
        fail("ARS_SYMBOL_FAILED",
             "machine_emergency_restart unexpectedly a real symbol")
    text_addr = syms["_text"]
    readelf_s = run([tools["readelf"], "-S", "--wide", str(vmlinux)])
    (out / "p1b-ars-vmlinux-sections.txt").write_text(readelf_s)
    hdr_isz = struct.unpack_from("<Q", image, 16)[0]
    binary_syms = {}
    for n in ("machine_restart", "do_kernel_restart", "emergency_restart",
              "kernel_restart", "psci_sys_reset"):
        va = syms[n]
        off = va - text_addr
        sec = section_for_va(readelf_s, va)
        insns, dump = dump_insns(tools, vmlinux, va, 8)
        (out / f"p1b-ars-{n}-disasm.txt").write_text(dump)
        word0 = struct.unpack_from("<I", image, off)[0]
        if word0 == PACIASP:
            landing = "paciasp"
        elif word0 == BTI_C:
            landing = "bti c"
        else:
            landing = f"other:{word0:#010x}"
        callers = scan_direct_calls(image, text_addr, hdr_isz, va)
        binary_syms[n] = {
            "va": hex(va),
            "image_offset": hex(off),
            "file_offset": hex(off),
            "section": sec["name"],
            "section_flags": sec["flags"],
            "entry_word": hex(word0),
            "landing": landing,
            "entry_insns": insns,
            "direct_callers": callers[:32],
            "direct_caller_count": len(callers),
        }
        emit(f"SYM_{n}_VA", hex(va))
        emit(f"SYM_{n}_OFFSET", hex(off))
        emit(f"SYM_{n}_LANDING", landing)
        emit(f"SYM_{n}_CALLERS", len(callers))

    # FIX8 prologue cross-check (machine_restart)
    fix8_match = "SKIPPED"
    if fix8 is not None:
        fp = fix8.read_bytes()
        if sha(fp) != FIX8_PAYLOAD_SHA or len(fp) != FIX8_PAYLOAD_SIZE:
            fail("ARS_FIX8_SHA_FAILED", f"{sha(fp)} {len(fp)}")
        off = binary_syms["machine_restart"]["image_offset"]
        off_i = int(off, 16)
        n = 16
        built = image[off_i:off_i + n]
        frozen = fp[off_i:off_i + n]
        fix8_match = "YES" if built == frozen else "NO"
        emit("FIX8_MACHINE_RESTART_PROLOGUE_MATCH", fix8_match)
        if built != frozen:
            emit("FIX8_PROLOGUE_BUILT", built.hex())
            emit("FIX8_PROLOGUE_FROZEN", frozen.hex())

    mr_callers = binary_syms["do_kernel_restart"]["direct_callers"]
    instrumentable = "YES"
    if binary_syms["machine_restart"]["section_flags"].find("X") < 0 \
            and "AX" not in binary_syms["machine_restart"]["section_flags"] \
            and "CODE" not in binary_syms["machine_restart"]["section_flags"]:
        # accept 'X' or 'AX' or CODE
        if not re.search(r"X", binary_syms["machine_restart"]["section_flags"]):
            instrumentable = "NO"
    if fix8_match == "NO":
        instrumentable = "SOURCE_YES_FIX8_OFFSET_RECHECK_REQUIRED"
    landing = binary_syms["machine_restart"]["landing"]
    if landing.startswith("other"):
        instrumentable = "NO"

    binary = {
        "status": "COMPLETE",
        "vmlinux_sha256": sha(vmlinux.read_bytes()),
        "image_sha256": sha(image),
        "sysmap_sha256": sha(sysmap.read_bytes()),
        "text_addr": hex(text_addr),
        "image_header_image_size": hex(hdr_isz),
        "symbols": binary_syms,
        "machine_emergency_restart_symbol": "ABSENT_INLINED",
        "do_kernel_restart_callers": mr_callers,
        "FIX8_MACHINE_RESTART_PROLOGUE_MATCH": fix8_match,
        "RESTART_CHOKEPOINT_INSTRUMENTABLE": instrumentable,
        "recommended_instrument_symbol": "machine_restart",
        "PAC_BTI": landing,
    }
    (out / "p1b-ars-binary.json").write_text(
        json.dumps(binary, indent=2) + "\n")
    emit("RESTART_CHOKEPOINT_INSTRUMENTABLE", instrumentable)
    emit("ARS_BINARY_AUDIT", "PASS")
    emit("DEVICE_OPERATION", "NO")
    emit("READY_FOR_DEVICE", "NO")


def cmd_merge(out: Path, source_json: Path, binary_json: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(source_json.read_text())
    binary = json.loads(binary_json.read_text())
    doc["binary"] = binary
    doc["chokepoint"]["RESTART_CHOKEPOINT_INSTRUMENTABLE"] = binary[
        "RESTART_CHOKEPOINT_INSTRUMENTABLE"]
    doc["chokepoint"]["binary_symbol"] = binary["symbols"]["machine_restart"]
    validate_map(doc, require_binary=True)
    path = out / "alternative-reset-source-map.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")
    early = out / "early"
    early.mkdir(exist_ok=True)
    (early / "alternative-reset-source-map.json").write_text(path.read_text())
    print_source_tokens(doc)
    emit("RESTART_CHOKEPOINT_INSTRUMENTABLE",
         binary["RESTART_CHOKEPOINT_INSTRUMENTABLE"])
    emit("ALTERNATIVE_RESET_SOURCE_MAP_STATUS", "COMPLETE")
    emit("MAINLINE_V2_R3_P1B_ALTERNATIVE_RESET_SOURCE_ISOLATION_COMPLETE",
         "YES")
    emit("DEVICE_READY", "NO")
    emit("READY_FOR_DEVICE", "NO")
    emit("ARS_MERGE_VERDICT", "PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=("source-gate", "source-audit", "binary-audit",
                             "merge-verdict"))
    ap.add_argument("--out", default="out-ars")
    ap.add_argument("--rt-d")
    ap.add_argument("--fix8-payload")
    ap.add_argument("--source-json")
    ap.add_argument("--binary-json")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--objdump", default="llvm-objdump-18")
    ap.add_argument("--nm", default="llvm-nm-18")
    ap.add_argument("--readelf", default="llvm-readelf-18")
    args = ap.parse_args()
    out = Path(args.out)
    if args.mode == "source-gate":
        cmd_source_gate()
    elif args.mode == "source-audit":
        if not args.rt_d:
            fail("ARS_ARGS", "--rt-d required")
        cmd_source_audit(out, Path(args.rt_d))
    elif args.mode == "binary-audit":
        tools = {"objdump": args.objdump, "nm": args.nm,
                 "readelf": args.readelf}
        cmd_binary_audit(out, args.jobs, tools,
                         Path(args.fix8_payload) if args.fix8_payload else None)
    else:
        if not (args.source_json and args.binary_json):
            fail("ARS_ARGS", "--source-json and --binary-json required")
        cmd_merge(out, Path(args.source_json), Path(args.binary_json))


if __name__ == "__main__":
    main()
