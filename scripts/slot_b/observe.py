#!/usr/bin/env python3
"""One Slot-B RAM boot, returning through the proven stock P15 recovery image."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import queue
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

IMAGES = {
    "recovery": (52666368, "133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34"),
    "reset8": (37380096, "1422a187bb82cca1dfd85ec0805e2fcb6b6fdea1d48d1a09f8a8e68c9e825b7f"),
    "reset1": (37380096, "43b9737ac02cd4947b2173109cf6f5dc49b85d5291dbc438c8a2945600aa0ae8"),
    "rest8": (37380096, "1832c179c924f2d21dd2aa16440759833c069353a920feff98240493214358bd"),
    "rest1": (37380096, "e4b06d5785e010aa4b340f72f65974cf03c09b6e9654249d41cab6b1808226b4"),
    "kinit8": (37380096, "420248dd42f02c1e68f703523165e3d74e24b7a4a20177cdfcb51584d16dcc24"),
    "kinit1": (37380096, "38d5c5eedf8ec87a095976c5c9b31a1b9780b3bafe25961fdf76b24e3e978bd7"),
    "free8": (37380096, "9c294a544cf1e178b7f638a40901fbddf97e3556ff57f18646114cd2d921be93"),
    "free1": (37380096, "8cf15312cd5803d33c8e889c5a87ad22edaa050da5455a92e68c37adfffffa19"),
    "smp8": (37380096, "915214b436376189a4bd871b574567d07a3884edf9706a9c6971829912ead689"),
    "smp1": (37380096, "fbdb4ef8cddf228977953f5371e65e7134e121867f4b932637546fa43bfb2950"),
    "initcalls8": (37380096, "15a9c504d4a44b8596c5d73d002bb8d5e9c5cf50c44fcc0c2a53da89f2cb2fe5"),
    "initcalls1": (37380096, "b07810cf2d8d17b7518d63033c650a8272f89dccee73d2a03e278455a2e6e65f"),
    "console8": (37380096, "9892a58c7627df78f5fc3acd64926aa054a2c9b6ca1f05ef65e2c0d289fd445d"),
    "console1": (37380096, "c116cf585516f1e6d9835a90ef0324745fd12f84f5d7cb36528e7aa73f2983b1"),
    "pure8": (37380096, "86d5c664e17675cf23322158782f2a0d2b9a7a1f075adc98c51f441ff4612a4b"),
    "pure1": (37380096, "08346222366202abf2d033b0f9bc9d3c11ac3ccd806727bf0d17d40dcf0ba57a"),
    "core8": (37380096, "5d7d5b88668e1925e3a79c677c2b630bb81d66135fec2761016de1da52fd7272"),
    "core1": (37380096, "a66c3f7a95e05905f5f65d96cb7f378ccdad9edf33814271425829ce10fe3e6c"),
    "postcore8": (37380096, "141d67931f8792036119c131d93ffa74649af2c6c44d086b489851230075355c"),
    "postcore1": (37380096, "4762a9fd29e109affb1c8864247887334508d9af2d6b183b7bf0200a05b697f1"),
    "arch8": (37380096, "7fcdbd0de81d0396280b941ed9cf7f2a4b3f9818b5ffe131fa59cfc49524e48d"),
    "arch1": (37380096, "f1aa8943131f768ceb7a7a0b160877195bb01ca69ba8252697fe6f5fe1a23113"),
    "subsys8": (37380096, "e082e530e4fce6dbe61f9cbe225851966fa35d1f80e4ab1dd69b5af9ba9175f1"),
    "subsys1": (37380096, "df14e7bcdf409deeeede70d7217f420091a6e9a292b0670443df50c0a0e8b9a1"),
    "fs8": (37380096, "cfc9f3f9c931126aceb47a5dcc39c12227f34eceb7ad2d9e6642088f3b7e6594"),
    "fs1": (37380096, "2377b227fd0eb4105330eec64f19843d7d64d42f994b12b999571cca6f4e3a1b"),

}
PAIRS = {
    "reset1": ("reset8", "machine_restart_entry", "original_restart_body"),
    "rest1": ("rest8", "rest_init_entry", "rest_init_body"),
    "kinit1": ("kinit8", "kernel_init_entry", "kthreadd_done_wait_completed"),
    "free1": ("free8", "kernel_init_freeable_entry", "kernel_init_freeable_body"),
    "smp1": ("smp8", "smp_init_entry", "smp_bringup_completed"),
    "initcalls1": ("initcalls8", "do_initcalls_entry", "initcall_levels_completed"),
    "console1": ("console8", "console_on_rootfs_entry", "console_opened"),
    "pure1": ("pure8", "pure_initcalls_completed", "core_initcalls_completed"),
    "core1": ("core8", "core_initcalls_completed", "first_postcore_initcall_body"),
    "postcore1": ("postcore8", "postcore_initcalls_completed", "first_arch_initcall_body"),
    "arch1": ("arch8", "arch_initcalls_completed", "first_subsys_initcall_body"),
    "subsys1": ("subsys8", "subsys_initcalls_completed", "first_fs_initcall_body"),
    "fs1": ("fs8", "fs_initcalls_completed", "first_device_initcall_body"),
}
ORIGIN_CASES = {case for second, spec in PAIRS.items() if second != "reset1"
                for case in (spec[0], second)}
CONTEXT = {
    "boot_b_prefix": IMAGES["recovery"][1],
    "vendor_boot_b": "aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972",
    "dtbo_b": "018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634",
}
PROTOCOL = "slot-b-p15-fastboot-return-v1"
ARCH_GEOMETRY = {
    "target": "topology_init", "va": 0xFFFF800081B346FC, "offset": 0x1B346FC,
    "function_size": 188, "window": 160, "entry": "paciasp",
    "back_edge_src": 0x9C, "back_edge_dst": 0x38,
}
SUBSYS_GEOMETRY = {
    "target": "create_debug_debugfs_entry", "va": 0xFFFF8000800149E0,
    "offset": 0x149E0, "function_size": 56, "window": 56, "entry": "paciasp",
    "core_size": 52, "daifset": "ABSENT", "prel32_unchanged": True,
    "core_size": 52, "daifset": "ABSENT", "prel32_unchanged": True,
}
FS_GEOMETRY = {
    "target": "register_arm64_panic_block", "va": 0xFFFF800081B347B8,
    "offset": 0x1B347B8, "function_size": 48, "stub_size": 8, "entry": "paciasp",
    "architecture": "ENTRY_TRAMPOLINE", "island_offset": 0xFFCC,
    "island_end": 0x10000, "island_va": 0xFFFF80008000FFCC, "core_size": 52,
    "daifset": "ABSENT", "prel32_unchanged": True, "live_tramp_untouched": True,
    "direct_b": True,
}

REST_ORIGIN = "ANDROID_A_ADB_REBOOT_BOOTLOADER_THEN_SELECT_B"
VARS = ("product", "unlocked", "current-slot", "slot-count",
        "snapshot-update-status", "battery-soc-ok", "max-download-size",
        "slot-unbootable:b", "slot-retry-count:b", "slot-successful:a")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_identity(case, size, digest):
    require(case in IMAGES and (size, digest) == IMAGES[case], "IMAGE_IDENTITY_MISMATCH")


def validate_arch_geometry(window):
    require(window != 60, "ARCH_60B_WINDOW_REJECTED")
    require(window == ARCH_GEOMETRY["window"], "ARCH_WINDOW_NOT_160")
    require(ARCH_GEOMETRY["window"] <= ARCH_GEOMETRY["function_size"],
            "ARCH_WINDOW_EXCEEDS_FUNCTION")
    require(ARCH_GEOMETRY["back_edge_src"] + 4 <= window, "ARCH_BACKEDGE_SOURCE_LIVE")
    require(ARCH_GEOMETRY["entry"] == "paciasp", "ARCH_ENTRY_NOT_PACIASP")


def validate_subsys_geometry(window):
    require(window != 60, "SUBSYS_60B_WINDOW_REJECTED")
    require(window != 57, "SUBSYS_57B_WINDOW_REJECTED")
    require(window == SUBSYS_GEOMETRY["window"], "SUBSYS_WINDOW_NOT_56")
    require(SUBSYS_GEOMETRY["window"] == SUBSYS_GEOMETRY["function_size"],
            "SUBSYS_WINDOW_EXCEEDS_FUNCTION")
    require(SUBSYS_GEOMETRY["entry"] == "paciasp", "SUBSYS_ENTRY_NOT_PACIASP")
    require(SUBSYS_GEOMETRY["core_size"] == 52, "SUBSYS_CORE_NOT_52")
    require(SUBSYS_GEOMETRY["daifset"] == "ABSENT", "SUBSYS_DAIFSET_PRESENT")
    require(SUBSYS_GEOMETRY["prel32_unchanged"] is True, "SUBSYS_PREL32_CHANGED")


def validate_fs_geometry(window):
    require(window != 56, "FS_56B_INLINE_REJECTED")
    require(window != 60, "FS_60B_INLINE_REJECTED")
    require(window != 57, "FS_57B_WINDOW_REJECTED")
    require(window == FS_GEOMETRY["stub_size"], "FS_STUB_NOT_8")
    require(FS_GEOMETRY["stub_size"] <= FS_GEOMETRY["function_size"],
            "FS_STUB_EXCEEDS_FUNCTION")
    require(FS_GEOMETRY["function_size"] == 48, "FS_FUNCTION_NOT_48")
    require(FS_GEOMETRY["entry"] == "paciasp", "FS_ENTRY_NOT_PACIASP")
    require(FS_GEOMETRY["architecture"] == "ENTRY_TRAMPOLINE",
            "FS_ARCHITECTURE_NOT_TRAMPOLINE")
    require(FS_GEOMETRY["island_offset"] == 0xFFCC, "FS_ISLAND_NOT_FFCC")
    require(FS_GEOMETRY["island_end"] == 0x10000, "FS_ISLAND_END")
    require(FS_GEOMETRY["core_size"] == 52, "FS_CORE_NOT_52")
    require(FS_GEOMETRY["daifset"] == "ABSENT", "FS_DAIFSET_PRESENT")
    require(FS_GEOMETRY["prel32_unchanged"] is True, "FS_PREL32_CHANGED")
    require(FS_GEOMETRY["live_tramp_untouched"] is True, "FS_LIVE_TRAMP_MUTATED")
    require(FS_GEOMETRY["direct_b"] is True, "FS_NOT_DIRECT_B")
    require(FS_GEOMETRY["target"] == "register_arm64_panic_block", "FS_WRONG_TARGET")


def validate_context(context, case=None):
    require(all(context.get(k) == v for k, v in CONTEXT.items()), "B_CONTEXT_MISMATCH")
    require(context.get("slot_a_unchanged") is True, "SLOT_A_UNCHANGED_NOT_VERIFIED")
    require(context.get("readback_verified") is True, "B_READBACK_NOT_VERIFIED")
    if case in ORIGIN_CASES:
        require(context.get("bootloader_origin") == REST_ORIGIN, "BOOTLOADER_ORIGIN_MISMATCH")


def validate_preflight(values, size):
    expected = {"product": "thyme", "unlocked": "yes", "current-slot": "b",
                "slot-count": "2", "snapshot-update-status": "none",
                "battery-soc-ok": "yes", "slot-unbootable:b": "no",
                "slot-successful:a": "yes"}
    for key, value in expected.items():
        require(values.get(key) == value, f"PREFLIGHT_REJECTED:{key}")
    require(int(values.get("slot-retry-count:b", "0"), 0) >= 2, "B_RETRIES_TOO_LOW")
    require(int(values.get("max-download-size", "0"), 0) >= size, "DOWNLOAD_TOO_LARGE")


def pair_verdict(baseline, result):
    second = result.get("case")
    require(second in PAIRS, "PAIR_MEMBER_MISMATCH")
    first, proof_key, unproved_key = PAIRS[second]
    for record, case in zip((baseline, result), (first, second)):
        if second != "reset1":
            require(record.get("bootloader_origin") == REST_ORIGIN, "PAIR_ORIGIN_MISMATCH")
        require(record.get("protocol") == PROTOCOL, "PAIR_PROTOCOL_MISMATCH")
        require(record.get("case") == case, "PAIR_MEMBER_MISMATCH")
        require(record.get("image_sha256") == IMAGES[case][1], "PAIR_IDENTITY_MISMATCH")
        require(record.get("status") == "AUTOMATIC_FASTBOOT_RETURN", "PAIR_RETURN_NOT_VALID")
        require(record.get("final_slot") == "b", "PAIR_NOT_SLOT_B")
        require(record.get("experimental_boots") == 1, "PAIR_BOOT_COUNT_INVALID")
        require(record.get("context") == CONTEXT, "PAIR_CONTEXT_MISMATCH")
        require(not isinstance(record.get("total_s"), bool) and
                isinstance(record.get("total_s"), (int, float)) and
                math.isfinite(record["total_s"]) and record["total_s"] > 0,
                "PAIR_TIMING_INVALID")
    delta = result["total_s"] - baseline["total_s"]
    error = delta + 7.0
    verdict = "STRONG" if abs(error) <= 1.0 else (
        "SUPPORTED" if abs(error) <= 2.0 else "SHIFT_NOT_OBSERVED")
    grade = "PROVEN" if verdict == "STRONG" else (
        "SUPPORTED" if verdict == "SUPPORTED" else "NOT_PROVEN")
    out = {"delta_s": delta, "expected_delta_s": -7.0, "error_s": error,
           "verdict": verdict, proof_key: grade, unproved_key: "NOT_PROVEN",
           "init_executed": "NOT_PROVEN"}
    if second == "core1":
        core_grade = "STRONGLY_SUPPORTED" if verdict == "SUPPORTED" else grade
        out.update(core_initcalls_completed=core_grade,
                   first_postcore_initcall_entry=core_grade,
                   postcore_initcalls_completed="NOT_PROVEN",
                   console_on_rootfs_entry="NOT_PROVEN")
        if verdict == "SHIFT_NOT_OBSERVED":
            out.update(core_initcalls_checkpoint_shift_not_observed="YES",
                       next="CORE_INITCALLS_FAILURE_ISOLATION_CI")
    elif second == "postcore1":
        postcore_grade = "STRONGLY_SUPPORTED" if verdict == "SUPPORTED" else grade
        out.update(postcore_initcalls_completed=postcore_grade,
                   first_arch_initcall_entry=postcore_grade,
                   first_arch_initcall_body="NOT_PROVEN",
                   arch_initcalls_completed="NOT_PROVEN",
                   subsys_initcalls_completed="NOT_PROVEN",
                   fs_initcalls_completed="NOT_PROVEN",
                   device_initcalls_completed="NOT_PROVEN",
                   late_initcalls_completed="NOT_PROVEN",
                   wait_for_initramfs_return="NOT_PROVEN",
                   console_on_rootfs_entry="NOT_PROVEN",
                   usb="FROZEN")
        if verdict == "SHIFT_NOT_OBSERVED":
            out.update(postcore_initcalls_checkpoint_shift_not_observed="YES",
                       next="POSTCORE_INITCALLS_FAILURE_ISOLATION_CI")
    elif second == "arch1":
        arch_grade = "STRONGLY_SUPPORTED" if verdict == "SUPPORTED" else grade
        out.update(arch_initcalls_completed=arch_grade,
                   first_subsys_initcall_entry=arch_grade,
                   first_subsys_initcall_body="NOT_PROVEN",
                   subsys_initcalls_completed="NOT_PROVEN",
                   fs_initcalls_completed="NOT_PROVEN",
                   device_initcalls_completed="NOT_PROVEN",
                   late_initcalls_completed="NOT_PROVEN",
                   wait_for_initramfs_return="NOT_PROVEN",
                   console_on_rootfs_entry="NOT_PROVEN",
                   usb="FROZEN")
        if verdict == "SHIFT_NOT_OBSERVED":
            out.update(arch_initcalls_checkpoint_shift_not_observed="YES",
                       next="ARCH_INITCALLS_FAILURE_ISOLATION_CI")
    elif second == "subsys1":
        subsys_grade = "STRONGLY_SUPPORTED" if verdict == "SUPPORTED" else grade
        out.update(subsys_initcalls_completed=subsys_grade,
                   first_fs_initcall_entry=subsys_grade,
                   first_fs_initcall_body="NOT_PROVEN",
                   fs_initcalls_completed="NOT_PROVEN",
                   device_initcalls_completed="NOT_PROVEN",
                   late_initcalls_completed="NOT_PROVEN",
                   wait_for_initramfs_return="NOT_PROVEN",
                   console_on_rootfs_entry="NOT_PROVEN",
                   usb="FROZEN")
        if verdict == "SHIFT_NOT_OBSERVED":
            out.update(subsys_initcalls_checkpoint_shift_not_observed="YES",
                       next="SUBSYS_INITCALLS_FAILURE_ISOLATION_CI")
    elif second == "fs1":
        fs_grade = "STRONGLY_SUPPORTED" if verdict == "SUPPORTED" else grade
        out.update(fs_initcalls_completed=fs_grade,
                   first_device_initcall_entry=fs_grade,
                   first_device_initcall_body="NOT_PROVEN",
                   device_initcalls_completed="NOT_PROVEN",
                   late_initcalls_completed="NOT_PROVEN",
                   wait_for_initramfs_return="NOT_PROVEN",
                   console_on_rootfs_entry="NOT_PROVEN",
                   usb="FROZEN")
        if verdict == "SHIFT_NOT_OBSERVED":
            out.update(fs_initcalls_checkpoint_shift_not_observed="YES",
                       next="FS_INITCALLS_FAILURE_ISOLATION_CI")
    return out



class Observer:
    def __init__(self, args):
        self.args = args
        self.fb = ["fastboot", "-s", args.serial]
        self.events = []
        self.boots = 0

    def boot_counts(self):
        recovery = self.boots if self.args.case == "recovery" else 0
        return {"host_boot_commands": self.boots,
                "experimental_boots": self.boots - recovery,
                "recovery_control_boots": recovery}

    def log(self, event, **fields):
        row = {"utc": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        self.events.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)

    def command(self, args, timeout=4):
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        require(p.returncode == 0, "HOST_COMMAND_FAILED")
        return p.stdout + p.stderr

    def getvar(self, key):
        out = self.command(self.fb + ["getvar", key])
        match = re.search(rf"^(?:\(bootloader\)\s*)?{re.escape(key)}:\s*(\S+)\s*$", out, re.M)
        require(match is not None, f"GETVAR_MISSING:{key}")
        return match[1]

    def present(self, program, state):
        try:
            lines = self.command([program, "devices"], timeout=2).splitlines()
            return any(line.split()[:2] == [self.args.serial, state] for line in lines)
        except (ValueError, subprocess.TimeoutExpired):
            return False

    def launch(self):
        require(self.boots == 0, "SECOND_EXPERIMENTAL_BOOT_FORBIDDEN")
        require(self.getvar("current-slot") == "b", "LAST_MOMENT_SLOT_NOT_B")
        command = self.fb + (["reboot"] if self.args.case == "recovery" else
                             ["boot", str(self.args.image)])
        self.boots += 1
        self.log("COMMAND_START", operation="reboot_b" if self.args.case == "recovery"
                 else "ram_boot_b", case=self.args.case)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        lines = queue.Queue()

        def reader():
            for line in proc.stdout:
                lines.put((time.monotonic(), line.rstrip()))
            lines.put((time.monotonic(), None))

        threading.Thread(target=reader, daemon=True).start()
        accepted = None
        deadline = time.monotonic() + 45
        try:
            while True:
                timestamp, line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
                if line is None:
                    break
                self.log("FASTBOOT_OUT", text=line.replace(self.args.serial, "<device>"))
                require("FAILED" not in line, "BOOT_COMMAND_FAILED_NO_RETRY")
                if "okay" in line.lower() and "booting" in line.lower():
                    accepted = timestamp
            require(proc.wait(timeout=3) == 0 and accepted is not None,
                    "BOOT_NOT_ACCEPTED_NO_RETRY")
        except (queue.Empty, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()
            raise ValueError("COMMAND_TIMEOUT_BOOT_STATE_UNCERTAIN_NO_RETRY") from None
        self.log("BOOTING_OKAY")
        return accepted

    def observe(self, start):
        gone = False
        first_return = None
        while time.monotonic() - start < 120:
            now = time.monotonic()
            present = self.present("fastboot", "fastboot")
            if not present:
                first_return = None
                if not gone:
                    gone = True
                    self.log("FASTBOOT_DISAPPEARED", elapsed_s=now - start)
                if self.present("adb", "device"):
                    self.log("UNEXPECTED_ADB_RETURN")
                    return {"status": "UNEXPECTED_ADB_RETURN"}
            elif gone:
                if first_return is None:
                    first_return = now
                    self.log("FASTBOOT_FIRST_RETURN", elapsed_s=now - start)
                elif now - first_return >= 3:
                    slot = self.getvar("current-slot")
                    require(self.getvar("product") == "thyme" and slot == "b",
                            "RETURN_IDENTITY_OR_SLOT_MISMATCH")
                    return {"status": "AUTOMATIC_FASTBOOT_RETURN", "final_slot": slot,
                            "total_s": first_return - start,
                            "b_retries": self.getvar("slot-retry-count:b")}
            time.sleep(0.10)
        return {"status": "NO_RETURN_WITHIN_120S", "manual_timing_excluded": True}

    def run(self):
        image = self.args.image.read_bytes()
        digest = hashlib.sha256(image).hexdigest()
        validate_identity(self.args.case, len(image), digest)
        context = json.loads(self.args.context.read_text())
        validate_context(context, self.args.case)
        baseline = None
        if self.args.case in PAIRS:
            require(self.args.baseline is not None, "MATCHED_8S_BASELINE_REQUIRED")
            baseline = json.loads(self.args.baseline.read_text())
            # Validate the reference before any device command, without assigning a verdict.
            candidate = {**baseline, "case": self.args.case, "image_sha256": IMAGES[self.args.case][1]}
            pair_verdict(baseline, candidate)
        self.args.output.mkdir(parents=True, exist_ok=False)
        result = {"protocol": PROTOCOL, "case": self.args.case, "image_sha256": digest,
                  "context": CONTEXT, "ci_run": self.args.ci_run,
                  "bootloader_origin": context.get("bootloader_origin", "UNRECORDED"),
                  "normal_boot_candidate": False,
                  "slot_a_written": False, "partition_writes": 0}
        try:
            values = {key: self.getvar(key) for key in VARS}
            self.log("PREFLIGHT", **values)
            validate_preflight(values, len(image))
            start = self.launch()
            result.update(self.observe(start))
            result.update(self.boot_counts())
            if baseline is not None and result["status"] == "AUTOMATIC_FASTBOOT_RETURN":
                result["pair"] = pair_verdict(baseline, result)
            self.log("RESULT", **result)
        except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
            result.update(status="STOP", reason=str(exc).replace(self.args.serial, "<device>"),
                          **self.boot_counts())
            self.log("STOP", **result)
        finally:
            (self.args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            (self.args.output / "events.json").write_text(json.dumps(self.events, indent=2) + "\n")
        return 0 if result["status"] == "AUTOMATIC_FASTBOOT_RETURN" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=IMAGES, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ci-run", required=True)
    parser.add_argument("--authorize-slot-b-only", action="store_true", required=True)
    args = parser.parse_args()
    return Observer(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
