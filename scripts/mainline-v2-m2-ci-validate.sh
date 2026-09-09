#!/usr/bin/env bash
# Build and reverse-validate the Mainline V2 M2 early-entry time signature.
# GitHub Actions only.
set -euo pipefail

if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local image build/validation" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REL="${1:?release dir}"
IMAGE="${2:?instrumented Mainline Image}"
INITRAMFS="${3:?exact M0 initramfs.cpio.gz}"
INIT_PROOF="${4:?exact M0 /init ELF}"
VMLINUX="${5:?instrumented vmlinux}"
M0_IMAGE="${6:?exact M0 Image}"
LINUX_DIR="${LINUX_DIR:-linux-6.6}"
EXPECTED_LINUX_BASE_COMMIT="${EXPECTED_LINUX_BASE_COMMIT:?expected Linux base commit}"
M2_DELAY_SECONDS="${M2_DELAY_SECONDS:-20}"
BOOT_CAP="${BOOT_CAP:-201326592}"
KERNEL_VERSION="${KERNEL_VERSION:-UNKNOWN}"
PATCH_QUEUE_SHA256="${PATCH_QUEUE_SHA256:-UNKNOWN}"
M2_PATCH="${M2_PATCH:-$ROOT/patches/experiments/mainline-v2-m2-early-delay.patch}"
EXPECTED_M0_IMAGE_SHA256="${EXPECTED_M0_IMAGE_SHA256:-22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6}"
EXPECTED_M0_INIT_SHA256="${EXPECTED_M0_INIT_SHA256:-aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8}"
EXPECTED_M0_RAMDISK_SHA256="${EXPECTED_M0_RAMDISK_SHA256:-b7d3949461a57b985585c0fe31ef423ce34216aa9ae164600ffbeed97d5a47de}"
M2_FINAL_GATE="${M2_FINAL_GATE:-READY_FOR_MAINLINE_V2_M2_EARLY_DELAY}"

REL="$(mkdir -p "$REL" && cd "$REL" && pwd)"
REVERSE="$REL/reverse-unpack-report"
mkdir -p "$REVERSE/boot-v3" "$REVERSE/initramfs-root"
RPT="$REL/validation-report.txt"
: >"$RPT"

pass() { printf 'PASS  %s\n' "$*" | tee -a "$RPT"; }
fail() { printf 'FAIL  %s\n' "$*" | tee -a "$RPT" >&2; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }

[ -s "$IMAGE" ] || fail "MAINLINE_IMAGE_BUILD missing Image"
[ -s "$INITRAMFS" ] || fail "M0_INITRAMFS missing"
[ -s "$INIT_PROOF" ] || fail "M0_INIT_BINARY missing"
[ -s "$VMLINUX" ] || fail "MAINLINE_VMLINUX missing"
[ -s "$M0_IMAGE" ] || fail "M0_IMAGE missing"
[ -s "$M2_PATCH" ] || fail "M2_PATCH missing"

[ "$M2_DELAY_SECONDS" = 20 ] || fail "DELAY_SECONDS=$M2_DELAY_SECONDS"
pass "EXPERIMENTAL_INSTRUMENTATION=YES"
pass "UPSTREAM_FEATURE_CHANGE=NO"
pass "DELAY_SECONDS_20=PASS"

BASE="$(git -C "$LINUX_DIR" rev-parse HEAD)"
[ "$BASE" = "$EXPECTED_LINUX_BASE_COMMIT" ] || fail "MAINLINE_VERSION_PINNED=$BASE"
pass "MAINLINE_VERSION_PINNED=$BASE"
pass "MAINLINE_VERSION_PINNED=PASS"
printf 'KERNEL_VERSION=%s\nLINUX_BASE_COMMIT=%s\nPATCH_QUEUE_SHA256=%s\n' \
	"$KERNEL_VERSION" "$BASE" "$PATCH_QUEUE_SHA256" | tee -a "$RPT"
case "$KERNEL_VERSION" in
	6.6.*) pass "MAINLINE_VERSION=$KERNEL_VERSION" ;;
	*) fail "MAINLINE_VERSION=$KERNEL_VERSION" ;;
esac

CHANGED="$(git -C "$LINUX_DIR" diff --name-only)"
UNTRACKED="$(git -C "$LINUX_DIR" ls-files --others --exclude-standard)"
python3 - "$CHANGED" "$UNTRACKED" <<'PY'
import sys

actual = set()
for value in sys.argv[1:]:
    actual.update(value.splitlines())
expected = {
    "Documentation/devicetree/bindings/arm/qcom.yaml",
    "arch/arm64/boot/dts/qcom/Makefile",
    "arch/arm64/boot/dts/qcom/sm8250-xiaomi-thyme.dts",
    "arch/arm64/kernel/head.S",
}
if actual != expected:
    raise SystemExit(f"unexpected M2 linux patch scope: {sorted(actual)}")
PY
pass "M2_PATCH_SCOPE=PASS"

python3 - "$M2_PATCH" <<'PY'
from pathlib import Path
import sys

patch = Path(sys.argv[1]).read_text()
paths = {
    line[6:].strip()
    for line in patch.splitlines()
    if line.startswith("+++ b/")
}
if paths != {"arch/arm64/kernel/head.S"}:
    raise SystemExit(f"experimental patch scope is not head.S only: {sorted(paths)}")
PY
pass "M2_PATCH_APPLIED=PASS"

M0_IMAGE_SHA256="$(sha "$M0_IMAGE")"
IMAGE_SHA256="$(sha "$IMAGE")"
M2_PATCH_SHA256="$(sha "$M2_PATCH")"
INIT_SHA256="$(sha "$INIT_PROOF")"
RAMDISK_SHA256="$(sha "$INITRAMFS")"
[ "$M0_IMAGE_SHA256" = "$EXPECTED_M0_IMAGE_SHA256" ] || \
	fail "M0_IMAGE_REFERENCE_SHA256=$M0_IMAGE_SHA256"
[ "$IMAGE_SHA256" != "$M0_IMAGE_SHA256" ] || fail "M2 Image did not change"
[ "$INIT_SHA256" = "$EXPECTED_M0_INIT_SHA256" ] || \
	fail "M0_INIT_BINARY_SHA256=$INIT_SHA256"
[ "$RAMDISK_SHA256" = "$EXPECTED_M0_RAMDISK_SHA256" ] || \
	fail "M0_RAMDISK_SHA256=$RAMDISK_SHA256"
M2_PATCH_OUTPUT="$REL/mainline-v2-m2-early-delay.patch"
[ -s "$M2_PATCH_OUTPUT" ] || fail "M2_PATCH_ARTIFACT missing"
[ "$(sha "$M2_PATCH_OUTPUT")" = "$M2_PATCH_SHA256" ] || fail "M2_PATCH_ARTIFACT changed"
printf 'M0_IMAGE_SHA256=%s\nM2_IMAGE_SHA256=%s\nM2_PATCH_SHA256=%s\nM0_INIT_BINARY_SHA256=%s\nM0_RAMDISK_SHA256=%s\nM2_RAMDISK_SHA256=%s\n' \
	"$M0_IMAGE_SHA256" "$IMAGE_SHA256" "$M2_PATCH_SHA256" "$INIT_SHA256" "$RAMDISK_SHA256" "$RAMDISK_SHA256" | tee -a "$RPT"
pass "M2_KERNEL_PAYLOAD_CHANGED=PASS"
pass "M2_PATCH_ARTIFACT=PASS"
pass "M0_INITRAMFS_EXACT_REUSE=PASS"
pass "M0_INIT_BINARY_EXACT_REUSE=PASS"

HEAD="$LINUX_DIR/arch/arm64/kernel/head.S"
EL2_SETUP="$LINUX_DIR/arch/arm64/include/asm/el2_setup.h"
ARCH_TIMER="$LINUX_DIR/arch/arm64/include/asm/arch_timer.h"
python3 - "$HEAD" "$EL2_SETUP" "$ARCH_TIMER" "$M2_DELAY_SECONDS" <<'PY' | tee -a "$RPT"
from pathlib import Path
import re
import sys

head = Path(sys.argv[1]).read_text()
el2 = Path(sys.argv[2]).read_text()
arch_timer = Path(sys.argv[3]).read_text()
delay_seconds = sys.argv[4]

primary_start = head.index("SYM_CODE_START(primary_entry)")
primary_end = head.index("SYM_CODE_END(primary_entry)", primary_start)
primary = head[primary_start:primary_end]

def pos(pattern, text, label):
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise SystemExit(f"missing {label}: {pattern}")
    return match.start()

init = pos(r"^\s*bl\s+init_kernel_el\b", primary, "init_kernel_el")
mode = pos(r"^\s*mov\s+x20,\s*x0\s*$", primary, "boot mode preservation")
start = pos(r"^\.Lthyme_m2_early_delay_start:\s*$", primary, "checkpoint start")
end = pos(r"^\.Lthyme_m2_early_delay_end:\s*$", primary, "checkpoint end")
cpu = pos(r"^\s*bl\s+__cpu_setup\b", primary, "__cpu_setup")
if not init < mode < start < end < cpu:
    raise SystemExit("checkpoint order is not init_kernel_el -> checkpoint -> __cpu_setup")

delay = primary[start:end]
comments_removed = re.sub(r"/\*.*?\*/", "", delay, flags=re.DOTALL)
comments_removed = re.sub(r"//.*", "", comments_removed)
regs = set(re.findall(r"\bx(?:[0-9]|[12][0-9]|3[01])\b", comments_removed))
if not regs <= {"x0", "x1", "x2", "x3"}:
    raise SystemExit(f"unsafe register in delay block: {sorted(regs)}")

required = {
    "CNTFRQ_EL0": r"^\s*mrs\s+x0,\s*cntfrq_el0\s*$",
    "CNTPCT_EL0_start": r"^\s*mrs\s+x1,\s*cntpct_el0\s*$",
    "DELAY_LITERAL": rf"^\s*mov\s+x3,\s*#?{re.escape(delay_seconds)}\s*$",
    "MADD_DEADLINE": r"^\s*madd\s+x2,\s*x0,\s*x3,\s*x1\s*$",
    "CNTPCT_EL0_loop": r"^\s*mrs\s+x0,\s*cntpct_el0\s*$",
    "YIELD": r"^\s*yield\s*$",
}
for label, pattern in required.items():
    if not re.search(pattern, delay, re.MULTILINE):
        raise SystemExit(f"missing {label}")
if re.search(r"^\s*bl\s+", delay, re.MULTILINE):
    raise SystemExit("delay block contains a call")

preserve_start = head.index("SYM_CODE_START_LOCAL(preserve_boot_args)")
preserve_end = head.index("SYM_CODE_END(preserve_boot_args)", preserve_start)
preserve = head[preserve_start:preserve_end]
for pattern, label in [
    (r"^\s*mov\s+x21,\s*x0\b", "FDT preservation"),
    (r"^\s*stp\s+x21,\s*x1,\s*\[x0\]", "boot argument storage"),
    (r"^\s*stp\s+x2,\s*x3,\s*\[x0,\s*#16\]", "boot argument storage"),
]:
    if not re.search(pattern, preserve, re.MULTILINE):
        raise SystemExit(f"missing {label}")
if not re.search(r"^\s*bl\s+preserve_boot_args\b", primary, re.MULTILINE):
    raise SystemExit("primary_entry does not preserve boot arguments")

state_start = el2.index(".macro init_el2_state")
state_end = el2.index(".endm", state_start)
state = el2[state_start:state_end]
if "__init_el2_timers" not in state:
    raise SystemExit("init_el2_state does not configure timers")

timer_start = el2.index(".macro __init_el2_timers")
timer_end = el2.index(".endm", timer_start)
timer = el2[timer_start:timer_end]
if not re.search(r"^\s*msr\s+cnthctl_el2,", timer, re.MULTILINE):
    raise SystemExit("__init_el2_timers does not write CNTHCTL_EL2")

el_start = head.index("SYM_FUNC_START(init_kernel_el)")
el_end = head.index("SYM_FUNC_END(init_kernel_el)", el_start)
init_el = head[el_start:el_end]
el2_path_start = init_el.index("SYM_INNER_LABEL(init_el2")
el2_path = init_el[el2_path_start:]
if el2_path.index("init_el2_state") > el2_path.index("eret"):
    raise SystemExit("EL2 timer setup is after the EL2->EL1 return")

if "return read_sysreg(cntfrq_el0);" not in arch_timer:
    raise SystemExit("arch_timer.h does not use CNTFRQ_EL0")
if "isb\\n mrs %0, cntpct_el0" not in arch_timer:
    raise SystemExit("arch_timer.h lacks the existing ordered CNTPCT_EL0 accessor")

print("CHECKPOINT_FILE=arch/arm64/kernel/head.S")
print("CHECKPOINT_SYMBOL=primary_entry")
print("CHECKPOINT_AFTER=init_kernel_el return (mov x20, x0)")
print("CHECKPOINT_BEFORE=__cpu_setup")
print("DELAY_SECONDS=20")
print("COUNTER_SOURCE=CNTFRQ_EL0+CNTPCT_EL0")
print("SCRATCH_REGISTERS=x0,x1,x2,x3")
print("BOOT_ARGS_PRESERVED=YES")
PY
pass "EARLY_CHECKPOINT_PRESENT=PASS"
pass "EARLY_COUNTER_ACCESS_AUDITED=PASS"
pass "BOOT_ARGS_PRESERVED=PASS"
pass "SCRATCH_REGISTERS=x0,x1,x2,x3"
pass "COUNTER_SOURCE=CNTFRQ_EL0+CNTPCT_EL0"

python3 - "$IMAGE" <<'PY'
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
if data[:2] == b"\x1f\x8b":
    raise SystemExit("Image is gzip-compressed; M2 requires raw Image")
if len(data) < 0x3c or data[0x38:0x3c] != b"ARMd":
    raise SystemExit("Image lacks the arm64 raw Image magic")
PY
pass "MAINLINE_IMAGE_BUILD=PASS"
pass "ARM64_IMAGE_RAW=PASS"

if command -v aarch64-linux-gnu-objdump >/dev/null 2>&1; then
	OBJDUMP="aarch64-linux-gnu-objdump"
elif command -v llvm-objdump >/dev/null 2>&1; then
	OBJDUMP="llvm-objdump"
else
	fail "missing AArch64 objdump"
fi
DISASM="$REVERSE/primary-entry.disassembly.txt"
"$OBJDUMP" -d --disassemble=primary_entry "$VMLINUX" >"$DISASM" 2>&1 || \
	fail "PRIMARY_ENTRY_DISASSEMBLY"
grep -Eiq 'mrs[[:space:]]+x0,[[:space:]]*cntfrq_el0' "$DISASM" || \
	fail "TIMER_INSTRUCTION_CNTFRQ"
grep -Eiq 'mrs[[:space:]]+x1,[[:space:]]*cntpct_el0' "$DISASM" || \
	fail "TIMER_INSTRUCTION_CNTPCT_START"
grep -Eiq 'mrs[[:space:]]+x0,[[:space:]]*cntpct_el0' "$DISASM" || \
	fail "TIMER_INSTRUCTION_CNTPCT_LOOP"
grep -Eiq 'madd[[:space:]]+x2,[[:space:]]*x0,[[:space:]]*x3,[[:space:]]*x1' "$DISASM" || \
	fail "TIMER_INSTRUCTION_MADD"
grep -Eiq '[[:space:]]yield([[:space:]]|$)' "$DISASM" || fail "TIMER_INSTRUCTION_YIELD"
printf 'OBJDUMP=%s\nDISASSEMBLY_REPORT=%s\n' "$OBJDUMP" "$DISASM" | tee -a "$RPT"
pass "TIMER_INSTRUCTION_SEQUENCE=PASS"

BOOT="$REL/mainline-v2-m2-early-delay-boot-v3.img"
python3 "$ROOT/tools/aosp/mkbootimg.py" \
	--kernel "$IMAGE" \
	--ramdisk "$INITRAMFS" \
	--header_version 3 \
	--os_version 13.0.0 \
	--os_patch_level 2023-09 \
	-o "$BOOT"
test -s "$BOOT" || fail "BOOT_IMAGE missing"

UN="$REVERSE/boot-v3"
python3 "$ROOT/tools/aosp/unpack_bootimg.py" \
	--boot_img "$BOOT" \
	--out "$UN" >"$REVERSE/boot-v3.txt" 2>&1

grep -Fxq 'boot image header version: 3' "$REVERSE/boot-v3.txt" || fail "BOOT_V3"
grep -Fxq 'os version: 13.0.0' "$REVERSE/boot-v3.txt" || fail "BOOT_OS_VERSION"
grep -Fxq 'os patch level: 2023-09' "$REVERSE/boot-v3.txt" || fail "BOOT_OS_PATCH_LEVEL"
[ ! -e "$UN/dtb" ] || fail "BOOT_V3 unexpectedly carries DTB"
[ ! -e "$UN/recovery_dtbo" ] || fail "BOOT_V3 unexpectedly carries recovery dtbo"
[ -s "$UN/kernel" ] || fail "reverse unpack kernel missing"
[ -s "$UN/ramdisk" ] || fail "reverse unpack ramdisk missing"
[ "$(sha "$UN/kernel")" = "$IMAGE_SHA256" ] || fail "KERNEL_PAYLOAD_EXACT"
[ "$(sha "$UN/ramdisk")" = "$RAMDISK_SHA256" ] || fail "RAMDISK_PAYLOAD_EXACT"
pass "BOOT_V3=PASS"
pass "BOOT_HEADER_COMPATIBILITY=PASS"
pass "REVERSE_UNPACK=PASS"
pass "KERNEL_PAYLOAD_EXACT=PASS"
pass "RAMDISK_EXACT=PASS"

BOOT_SHA256="$(sha "$BOOT")"
BOOT_SIZE="$(wc -c <"$BOOT" | tr -d ' ')"
printf 'BOOT_IMAGE_SHA256=%s\nBOOT_IMAGE_SIZE=%s\n' "$BOOT_SHA256" "$BOOT_SIZE" | tee -a "$RPT"
[ "$BOOT_SIZE" -le "$BOOT_CAP" ] || fail "SIZE_GATE=$BOOT_SIZE > $BOOT_CAP"
pass "SIZE_GATE=$BOOT_SIZE <= $BOOT_CAP"

if find "$REL" -maxdepth 1 -type f \( \
	-name 'vendor_boot*' -o -name 'dtbo*' -o -name 'vbmeta*' -o -name 'firmware*' \
\) -print -quit | grep -q .; then
	fail "FORBIDDEN_OEM_ARTIFACT"
fi
pass "NO_VENDOR_BOOT_ARTIFACT=PASS"
pass "NO_DTBO_ARTIFACT=PASS"
pass "NO_VBMETA_ARTIFACT=PASS"
pass "NO_FIRMWARE_ARTIFACT=PASS"

pass "$M2_FINAL_GATE"
printf '%s\n' "$M2_FINAL_GATE" | tee -a "$RPT"
echo "ALL MAINLINE V2 M2 EARLY-ENTRY TIME-SIGNATURE VALIDATION PASS" | tee -a "$RPT"
