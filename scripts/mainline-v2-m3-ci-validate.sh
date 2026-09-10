#!/usr/bin/env bash
# Build and reverse-validate the Mainline V2 M3 early-entry time signature.
# GitHub Actions only.
set -euo pipefail
set -o pipefail

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
M2_IMAGE="${7:?exact M2 Image}"
M2_REPORT="${8:?exact M2 validation report}"
LINUX_DIR="${LINUX_DIR:-linux-6.6}"
EXPECTED_LINUX_BASE_COMMIT="${EXPECTED_LINUX_BASE_COMMIT:?expected Linux base commit}"
M3_DELAY_SECONDS="${M3_DELAY_SECONDS:-2}"
BOOT_CAP="${BOOT_CAP:-201326592}"
KERNEL_VERSION="${KERNEL_VERSION:-UNKNOWN}"
PATCH_QUEUE_SHA256="${PATCH_QUEUE_SHA256:-UNKNOWN}"
M3_PATCH="${M3_PATCH:-$ROOT/patches/experiments/mainline-v2-m3-earliest-entry-short-delay.patch}"
EXPECTED_M0_IMAGE_SHA256="${EXPECTED_M0_IMAGE_SHA256:-22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6}"
EXPECTED_M0_INIT_SHA256="${EXPECTED_M0_INIT_SHA256:-aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8}"
EXPECTED_M0_RAMDISK_SHA256="${EXPECTED_M0_RAMDISK_SHA256:-b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de}"
EXPECTED_M2_IMAGE_SHA256="${EXPECTED_M2_IMAGE_SHA256:-4b37a48819730d3fae43f8eeff9d2a6c8fbaa9f28432819d52cce8407f6826b4}"
M3_FINAL_GATE="${M3_FINAL_GATE:-READY_FOR_MAINLINE_V2_M3_EARLY_SHORT_DELAY}"

REL="$(mkdir -p "$REL" && cd "$REL" && pwd)"
REVERSE="$REL/reverse-unpack-report"
mkdir -p "$REVERSE/boot-v3" "$REVERSE/initramfs-root"
RPT="$REL/validation-report.txt"
: >"$RPT"

pass() { printf 'PASS  %s\n' "$*" | tee -a "$RPT"; }
fail() { printf 'FAIL  %s\n' "$*" | tee -a "$RPT" >&2; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }

pass "MEM0_CONSTRAINTS_ACKNOWLEDGED=PASS"
pass "GHA_ONLY_BUILD_VALIDATION=PASS"
pass "SLOT_A_PROTECTED=PASS"

for input in "$IMAGE" "$INITRAMFS" "$INIT_PROOF" "$VMLINUX" "$M0_IMAGE" "$M2_IMAGE" "$M2_REPORT" "$M3_PATCH"; do
	[ -s "$input" ] || fail "missing input: $input"
done

M2_IMAGE_SHA256="$(sha "$M2_IMAGE")"
[ "$M2_IMAGE_SHA256" = "$EXPECTED_M2_IMAGE_SHA256" ] || \
	fail "M2_IMAGE_REFERENCE_SHA256=$M2_IMAGE_SHA256"
grep -Fxq "M0_INIT_BINARY_SHA256=$EXPECTED_M0_INIT_SHA256" "$M2_REPORT" || \
	fail "M2_INIT_REFERENCE_SHA256"
grep -Fxq "M0_RAMDISK_SHA256=$EXPECTED_M0_RAMDISK_SHA256" "$M2_REPORT" || \
	fail "M2_RAMDISK_REFERENCE_SHA256"
grep -Fxq 'PASS  M0_INITRAMFS_EXACT_REUSE=PASS' "$M2_REPORT" || \
	fail "M2_INITRAMFS_REUSE_GATE"
grep -Fxq 'PASS  M0_INIT_BINARY_EXACT_REUSE=PASS' "$M2_REPORT" || \
	fail "M2_INIT_REUSE_GATE"
pass "M2_ARTIFACT_REFERENCE=PASS"
pass "M0_M1_M2_RAMDISK_EXACT_REUSE=PASS"
pass "RAMDISK_SHA_EXACT_REUSE=PASS"
pass "INIT_BINARY_EXACT_REUSE=PASS"

[ "$M3_DELAY_SECONDS" = 2 ] || fail "DELAY_SECONDS=$M3_DELAY_SECONDS"
pass "EXPERIMENTAL_INSTRUMENTATION=YES"
pass "FINAL_MAINLINE_PATCH=NO"
pass "M3_DELAY_SECONDS_2=PASS"

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
    raise SystemExit(f"unexpected M3 linux patch scope: {sorted(actual)}")
PY
pass "M3_PATCH_SCOPE=PASS"

python3 - "$M3_PATCH" <<'PY'
from pathlib import Path
import sys

paths = {
    line[6:].strip()
    for line in Path(sys.argv[1]).read_text().splitlines()
    if line.startswith("+++ b/")
}
if paths != {"arch/arm64/kernel/head.S"}:
    raise SystemExit(f"experimental patch scope is not head.S only: {sorted(paths)}")
PY
pass "M3_PATCH_APPLIED=PASS"

M0_IMAGE_SHA256="$(sha "$M0_IMAGE")"
IMAGE_SHA256="$(sha "$IMAGE")"
M3_PATCH_SHA256="$(sha "$M3_PATCH")"
INIT_SHA256="$(sha "$INIT_PROOF")"
RAMDISK_SHA256="$(sha "$INITRAMFS")"
[ "$M0_IMAGE_SHA256" = "$EXPECTED_M0_IMAGE_SHA256" ] || \
	fail "M0_IMAGE_REFERENCE_SHA256=$M0_IMAGE_SHA256"
[ "$IMAGE_SHA256" != "$M0_IMAGE_SHA256" ] || fail "M3 Image did not change"
[ "$IMAGE_SHA256" != "$M2_IMAGE_SHA256" ] || fail "M3 Image did not change from M2"
[ "$INIT_SHA256" = "$EXPECTED_M0_INIT_SHA256" ] || \
	fail "M0_INIT_BINARY_SHA256=$INIT_SHA256"
[ "$RAMDISK_SHA256" = "$EXPECTED_M0_RAMDISK_SHA256" ] || \
	fail "M0_RAMDISK_SHA256=$RAMDISK_SHA256"
M3_PATCH_OUTPUT="$REL/mainline-v2-m3-earliest-entry-short-delay.patch"
[ -s "$M3_PATCH_OUTPUT" ] || fail "M3_PATCH_ARTIFACT missing"
[ "$(sha "$M3_PATCH_OUTPUT")" = "$M3_PATCH_SHA256" ] || fail "M3_PATCH_ARTIFACT changed"
printf 'M0_IMAGE_SHA256=%s\nM2_IMAGE_SHA256=%s\nM3_IMAGE_SHA256=%s\nM3_PATCH_SHA256=%s\nM0_INIT_BINARY_SHA256=%s\nM0_RAMDISK_SHA256=%s\nM1_RAMDISK_SHA256=%s\nM2_RAMDISK_SHA256=%s\nM3_RAMDISK_SHA256=%s\n' \
	"$M0_IMAGE_SHA256" "$M2_IMAGE_SHA256" "$IMAGE_SHA256" "$M3_PATCH_SHA256" \
	"$INIT_SHA256" "$RAMDISK_SHA256" "$RAMDISK_SHA256" "$RAMDISK_SHA256" "$RAMDISK_SHA256" | tee -a "$RPT"
pass "M3_KERNEL_PAYLOAD_CHANGED=PASS"
pass "M3_PATCH_ARTIFACT=PASS"

HEAD="$LINUX_DIR/arch/arm64/kernel/head.S"
BOOTING="$LINUX_DIR/Documentation/arch/arm64/booting.rst"
EL2_SETUP="$LINUX_DIR/arch/arm64/include/asm/el2_setup.h"
ARCH_TIMER="$LINUX_DIR/arch/arm64/include/asm/arch_timer.h"
M2_PATCH="$ROOT/patches/experiments/mainline-v2-m2-early-delay.patch"
if python3 - "$HEAD" "$BOOTING" "$EL2_SETUP" "$ARCH_TIMER" "$M2_PATCH" "$M3_DELAY_SECONDS" <<'PY' | tee -a "$RPT"
from pathlib import Path
import re
import sys

head = Path(sys.argv[1]).read_text()
booting = Path(sys.argv[2]).read_text()
el2 = Path(sys.argv[3]).read_text()
arch_timer = Path(sys.argv[4]).read_text()
m2_patch = Path(sys.argv[5]).read_text()
delay_seconds = sys.argv[6]

primary_start = head.index("SYM_CODE_START(primary_entry)")
primary_end = head.index("SYM_CODE_END(primary_entry)", primary_start)
primary = head[primary_start:primary_end]

def match(pattern, text, label):
    result = re.search(pattern, text, re.MULTILINE)
    if not result:
        raise SystemExit(f"missing {label}: {pattern}")
    return result

def loc(offset):
    return f"byte:{offset},line:{head.count(chr(10), 0, offset) + 1}"

preserve = match(r"^\s*bl\s+preserve_boot_args\b", primary, "preserve_boot_args").start()
m3_start = match(r"^\.Lthyme_m3_earliest_delay_start:\s*$", primary, "M3 checkpoint start").start()
m3_end = match(r"^\.Lthyme_m3_earliest_delay_end:\s*$", primary, "M3 checkpoint end").start()
create = match(r"^\s*bl\s+create_idmap\b", primary, "create_idmap").start()
init = match(r"^\s*bl\s+init_kernel_el\b", primary, "init_kernel_el").start()
cpu = match(r"^\s*bl\s+__cpu_setup\b", primary, "__cpu_setup").start()
m2_anchor = match(r"^\s*mov\s+x20,\s*x0\s*$", primary, "M2 checkpoint anchor")
m2_start = primary.find("\n", m2_anchor.end()) + 1

if not preserve < m3_start < m3_end < create < init < cpu:
    raise SystemExit("M3 order is not preserve_boot_args -> checkpoint -> create_idmap -> init_kernel_el -> __cpu_setup")
if not m3_start < m2_start:
    raise SystemExit("M3 checkpoint is not earlier than M2 checkpoint")
for pattern in (r"\.Lthyme_m2_early_delay_start:", r"\.Lthyme_m2_early_delay_end:",
                r"bl\s+init_kernel_el", r"mov\s+x20,\s*x0",
                r"__cpu_setup follows below"):
    if not re.search(pattern, m2_patch):
        raise SystemExit(f"historical M2 checkpoint evidence missing: {pattern}")

delay = primary[m3_start:m3_end]
comments_removed = re.sub(r"/\*.*?\*/", "", delay, flags=re.DOTALL)
comments_removed = re.sub(r"//.*", "", comments_removed)
regs = set(re.findall(r"\bx(?:[0-9]|[12][0-9]|3[01])\b", comments_removed))
if not regs <= {"x0", "x1", "x2", "x3"}:
    raise SystemExit(f"unsafe register in M3 delay block: {sorted(regs)}")
if re.search(r"^\s*(bl|blr)\b", delay, re.MULTILINE):
    raise SystemExit("M3 delay block contains a call")
if re.search(r"^\s*msr\b", delay, re.MULTILINE):
    raise SystemExit("M3 delay block writes system state")

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

preserve_start = head.index("SYM_CODE_START_LOCAL(preserve_boot_args)")
preserve_end = head.index("SYM_CODE_END(preserve_boot_args)", preserve_start)
preserve_body = head[preserve_start:preserve_end]
for pattern, label in [
    (r"^\s*mov\s+x21,\s*x0\b", "FDT preservation"),
    (r"^\s*stp\s+x21,\s*x1,\s*\[x0\]", "boot argument storage"),
    (r"^\s*stp\s+x2,\s*x3,\s*\[x0,\s*#16\]", "boot argument storage"),
]:
    if not re.search(pattern, preserve_body, re.MULTILINE):
        raise SystemExit(f"missing {label}")

if "CNTFRQ must be programmed with the timer frequency" not in booting:
    raise SystemExit("boot protocol CNTFRQ requirement missing")
if "CNTHCTL_EL2 must have EL1PCTEN (bit 0) set where available" not in booting:
    raise SystemExit("boot protocol EL1 counter-access requirement missing")
if "either in EL2 (RECOMMENDED" not in booting or "or in EL1." not in booting:
    raise SystemExit("boot protocol EL2/EL1 entry requirement missing")
if "__init_el2_timers" not in el2 or "msr\tcnthctl_el2" not in el2:
    raise SystemExit("EL2 timer initialization source missing")
if "isb\n mrs %0, cntpct_el0" not in arch_timer:
    raise SystemExit("existing ordered CNTPCT_EL0 accessor missing")

print("M2_CHECKPOINT_FILE=arch/arm64/kernel/head.S")
print("M2_CHECKPOINT_SYMBOL=primary_entry")
print(f"M2_CHECKPOINT_OFFSET={loc(primary_start + m2_start)}")
print("M2_CHECKPOINT_AFTER=init_kernel_el return (mov x20, x0)")
print("M2_CHECKPOINT_BEFORE=__cpu_setup")
print("M3_CHECKPOINT_FILE=arch/arm64/kernel/head.S")
print("M3_CHECKPOINT_SYMBOL=primary_entry")
print(f"M3_CHECKPOINT_OFFSET={loc(primary_start + m3_start)}")
print("M3_CHECKPOINT_AFTER=preserve_boot_args return")
print("M3_CHECKPOINT_BEFORE=create_idmap")
print("M3_EARLIER_THAN_M2=YES")
print("M3_POSITION_BEFORE_M2=YES")
print("COUNTER_SOURCE=CNTFRQ_EL0+CNTPCT_EL0")
print("EARLY_TIMER_AUDIT_BASIS=arm64 boot protocol EL2-or-EL1 and EL1PCTEN")
print("EARLY_TIMER_ACCESS_AUDITED=PASS")
print("M3_SCRATCH_REGISTERS=x0,x1,x2,x3")
print("BOOT_ARGS_PRESERVED=YES")
print("SAVED_DTB_POINTER=x21")
print("SCTLR_STATE_PRESERVED=YES")
print("PRIMARY_BOOT_STATE_PRESERVED=YES")
PY
then
	:
else
	fail "M3_EARLY_TIMER_NOT_SAFE"
fi
pass "M3_EARLIER_THAN_M2=PASS"
pass "EARLY_TIMER_ACCESS_AUDITED=PASS"
pass "BOOT_ARGS_PRESERVED=PASS"
pass "M3_SCRATCH_REGISTERS=x0,x1,x2,x3"

python3 - "$INITRAMFS" "$INIT_PROOF" "$REVERSE/initramfs-root" <<'PY'
from pathlib import Path
import subprocess
import sys

ramdisk, init_proof, root = map(Path, sys.argv[1:])
root.mkdir(parents=True, exist_ok=True)
with ramdisk.open("rb") as source:
    subprocess.run(
        ["gzip", "-dc"],
        stdin=source,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout
with ramdisk.open("rb") as source:
    cpio = subprocess.Popen(
        ["cpio", "-idm", "--no-absolute-filenames"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    compressed = subprocess.run(["gzip", "-dc", str(ramdisk)], check=True,
                                stdout=subprocess.PIPE).stdout
    _, stderr = cpio.communicate(compressed)
    if cpio.returncode:
        raise SystemExit(stderr.decode(errors="replace"))
init = root / "init"
if not init.is_file():
    raise SystemExit("initramfs has no /init")
if init.read_bytes() != init_proof.read_bytes():
    raise SystemExit("initramfs /init differs from exact init proof")
PY
pass "RAMDISK_GZIP=PASS"
pass "INIT_BINARY_EXACT_REUSE=PASS"
pass "RAMDISK_SHA_EXACT_REUSE=PASS"

python3 - "$IMAGE" <<'PY'
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
if data[:2] == b"\x1f\x8b":
    raise SystemExit("Image is gzip-compressed; M3 requires raw Image")
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
grep -Eiq 'mov[[:space:]]+x3,[[:space:]]*#(0x)?2([[:space:]]|$)' "$DISASM" || \
	fail "DELAY_INSTRUCTION_LITERAL"
grep -Eiq 'madd[[:space:]]+x2,[[:space:]]*x0,[[:space:]]*x3,[[:space:]]*x1' "$DISASM" || \
	fail "TIMER_INSTRUCTION_MADD"
grep -Eiq '[[:space:]]yield([[:space:]]|$)' "$DISASM" || fail "TIMER_INSTRUCTION_YIELD"
printf 'OBJDUMP=%s\nDISASSEMBLY_REPORT=%s\n' "$OBJDUMP" "$DISASM" | tee -a "$RPT"
pass "TIMER_INSTRUCTION_SEQUENCE=PASS"
pass "M3_DELAY_SECONDS_2=PASS"

BOOT="$REL/mainline-v2-m3-early-short-delay-boot-v3.img"
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
pass "BOOT_HEADER_V3=PASS"
pass "BOOT_V3=PASS"
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
pass "M1_VENDOR_BOOT_CONTEXT=EXACT_M1_REQUIRED"
pass "M1_DTBO_CONTEXT=EXACT_M1_REQUIRED"
pass "VBMETA_CONTEXT=STOCK_REQUIRED"

pass "$M3_FINAL_GATE"
printf '%s\n' "$M3_FINAL_GATE" | tee -a "$RPT"
echo "ALL MAINLINE V2 M3 EARLIEST-ENTRY SHORT-DELAY VALIDATION PASS" | tee -a "$RPT"
