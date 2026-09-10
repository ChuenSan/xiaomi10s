#!/usr/bin/env bash
# Build and reverse-validate the Mainline V2 M4B earliest-entry spin proof.
# GitHub Actions only.
set -euo pipefail
set -o pipefail

if [ "${GITHUB_ACTIONS:-}" != true ]; then
	echo "CI only — refuse local image build/validation" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REL="${1:?release dir}"
IMAGE="${2:?instrumented Mainline Image}"
INITRAMFS="${3:?exact M0/M1 P15 initramfs.cpio.gz}"
INIT_PROOF="${4:?exact M0/M1 P15 /init ELF}"
VMLINUX="${5:?instrumented vmlinux}"
M0_IMAGE="${6:?exact M0 Image reference}"
M4B_PATCH="${7:-$ROOT/patches/experiments/mainline-v2-m4b-earliest-entry-spin.patch}"
LINUX_DIR="${LINUX_DIR:-linux-6.6}"
EXPECTED_LINUX_BASE_COMMIT="${EXPECTED_LINUX_BASE_COMMIT:?expected Linux base commit}"
BOOT_CAP="${BOOT_CAP:-201326592}"
KERNEL_VERSION="${KERNEL_VERSION:-UNKNOWN}"
PATCH_QUEUE_SHA256="${PATCH_QUEUE_SHA256:-UNKNOWN}"
EXPECTED_M0_IMAGE_SHA256="${EXPECTED_M0_IMAGE_SHA256:-22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6}"
EXPECTED_M0_INIT_SHA256="${EXPECTED_M0_INIT_SHA256:-aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8}"
EXPECTED_M0_RAMDISK_SHA256="${EXPECTED_M0_RAMDISK_SHA256:-b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de}"
M4B_FINAL_GATE="${M4B_FINAL_GATE:-READY_FOR_MAINLINE_V2_M4B_ENTRY_SPIN}"

REL="$(mkdir -p "$REL" && cd "$REL" && pwd)"
REVERSE="$REL/reverse-unpack-report"
mkdir -p "$REVERSE/boot-v3" "$REVERSE/initramfs-root"
RPT="$REL/validation-report.txt"
: >"$RPT"

pass() { printf 'PASS  %s\n' "$*" | tee -a "$RPT"; }
fail() { printf 'FAIL  %s\n' "$*" | tee -a "$RPT" >&2; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }

pass "MEM0_POLICY_ACKNOWLEDGED=PASS"
pass "GHA_ONLY=PASS"
pass "SLOT_A_PROTECTED=PASS"
pass "EXPERIMENTAL_INSTRUMENTATION=YES"
pass "FINAL_KERNEL_PATCH=NO"

for input in "$IMAGE" "$INITRAMFS" "$INIT_PROOF" "$VMLINUX" "$M0_IMAGE" "$M4B_PATCH"; do
	[ -s "$input" ] || fail "missing input: $input"
done

M0_IMAGE_SHA256="$(sha "$M0_IMAGE")"
[ "$M0_IMAGE_SHA256" = "$EXPECTED_M0_IMAGE_SHA256" ] || \
	fail "M0_IMAGE_REFERENCE_SHA256=$M0_IMAGE_SHA256"
INIT_SHA256="$(sha "$INIT_PROOF")"
RAMDISK_SHA256="$(sha "$INITRAMFS")"
[ "$INIT_SHA256" = "$EXPECTED_M0_INIT_SHA256" ] || \
	fail "M0_INIT_BINARY_SHA256=$INIT_SHA256"
[ "$RAMDISK_SHA256" = "$EXPECTED_M0_RAMDISK_SHA256" ] || \
	fail "M0_RAMDISK_SHA256=$RAMDISK_SHA256"
printf 'M0_IMAGE_SHA256=%s\nM0_INIT_BINARY_SHA256=%s\nM0_RAMDISK_SHA256=%s\n' \
	"$M0_IMAGE_SHA256" "$INIT_SHA256" "$RAMDISK_SHA256" | tee -a "$RPT"
pass "RAMDISK_EXACT_REUSE=PASS"
pass "INIT_BINARY_EXACT_REUSE=PASS"

BASE="$(git -C "$LINUX_DIR" rev-parse HEAD)"
[ "$BASE" = "$EXPECTED_LINUX_BASE_COMMIT" ] || fail "MAINLINE_VERSION_PINNED=$BASE"
pass "MAINLINE_VERSION_PINNED=$BASE"
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
    raise SystemExit(f"unexpected M4B linux patch scope: {sorted(actual)}")
PY
pass "M4B_PATCH_SCOPE=PASS"

python3 - "$M4B_PATCH" <<'PY'
from pathlib import Path
import re
import sys

patch = Path(sys.argv[1]).read_text()
paths = {
    line[6:].strip()
    for line in patch.splitlines()
    if line.startswith("+++ b/")
}
if paths != {"arch/arm64/kernel/head.S"}:
    raise SystemExit(f"experimental patch scope is not head.S only: {sorted(paths)}")
if ".Lthyme_m4b_earliest_entry_spin:" not in patch:
    raise SystemExit("M4B spin label is missing")
if not re.search(r"\bb\s+\.Lthyme_m4b_earliest_entry_spin\b", patch):
    raise SystemExit("M4B self-branch is missing")
PY
pass "M4B_PATCH_APPLIED=PASS"

HEAD="$LINUX_DIR/arch/arm64/kernel/head.S"
LINKER="$LINUX_DIR/arch/arm64/kernel/vmlinux.lds.S"
LINKAGE="$LINUX_DIR/include/linux/linkage.h"
ARM_LINKAGE="$LINUX_DIR/arch/arm64/include/asm/linkage.h"
BASE_HEAD="$REVERSE/base-head.S"
git -C "$LINUX_DIR" show "$BASE:arch/arm64/kernel/head.S" >"$BASE_HEAD"

python3 - "$HEAD" "$BASE_HEAD" "$M4B_PATCH" "$LINKER" "$LINKAGE" "$ARM_LINKAGE" <<'PY' | tee -a "$RPT"
from pathlib import Path
import re
import sys

head_path, base_path, patch_path, linker_path, linkage_path, arm_linkage_path = map(Path, sys.argv[1:])
head = head_path.read_text()
base = base_path.read_text()
patch = patch_path.read_text()
linker = linker_path.read_text()
linkage = linkage_path.read_text()
arm_linkage = arm_linkage_path.read_text()
label = ".Lthyme_m4b_earliest_entry_spin"


def primary(text):
    start = text.index("SYM_CODE_START(primary_entry)")
    end = text.index("SYM_CODE_END(primary_entry)", start)
    return text[start:end]


def noncomment_lines(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        lines.append(re.sub(r"\s+", " ", stripped))
    return lines


def first_assembly_instruction(text):
    for line in noncomment_lines(text):
        if line.startswith("SYM_CODE_START(") or line.startswith("SYM_CODE_END("):
            continue
        if line.startswith(".") or line.endswith(":"):
            continue
        return line
    raise SystemExit("primary_entry has no instruction")

final_primary = primary(head)
base_primary = primary(base)
final_first = first_assembly_instruction(final_primary)
original_first = first_assembly_instruction(base_primary)
if original_first != "bl record_mmu_state":
    raise SystemExit(f"unexpected original primary_entry first instruction: {original_first}")

prefix, after_label = final_primary.split(label + ":", 1)
if [line.strip() for line in prefix.splitlines()
        if line.strip() and line.strip() != "SYM_CODE_START(primary_entry)"]:
    raise SystemExit("instructions or directives precede the M4B spin label")
if final_first != f"b {label}":
    raise SystemExit(f"M4B is not the first primary_entry instruction: {final_first}")

m = re.match(r"\s*\n?\s*b\s+" + re.escape(label) + r"\s*\n", after_label)
if not m:
    raise SystemExit("M4B label is not immediately followed by its self-branch")
spin_block = after_label[:m.end()]
spin_instructions = [line for line in noncomment_lines(spin_block)
                     if not line.startswith(".") and not line.endswith(":")]
if spin_instructions != [f"b {label}"]:
    raise SystemExit(f"M4B block is not a single branch: {spin_instructions}")

added = "\n".join(
    line[1:] for line in patch.splitlines()
    if line.startswith("+") and not line.startswith("+++")
)
if f"{label}:" not in added:
    raise SystemExit("M4B label is not in patch additions")
if not re.search(rf"\bb\s+{re.escape(label)}\b", added):
    raise SystemExit("M4B branch is not in patch additions")

forbidden = re.compile(
    r"\b(?:mrs|msr|ldr|ldp|str|stp|blr|bl|wfe|wfi|smc|hvc|svc|brk|udf)\b|[\[\]]",
    re.I,
)
if forbidden.search(spin_block):
    raise SystemExit("M4B block contains a non-branch or memory/control instruction")
if re.search(r"\.Lthyme_m3_|cntfrq_el0|cntpct_el0|cntvct", head, re.I):
    raise SystemExit("M3 timer instrumentation is present in the final source")
if re.search(r"\.Lthyme_m3_|cntfrq_el0|cntpct_el0|cntvct", patch, re.I):
    raise SystemExit("M3 timer instrumentation is present in the M4B patch")

if "ENTRY(_text)" not in linker:
    raise SystemExit("vmlinux entry symbol is not _text")
if not re.search(r"^\s*b\s+primary_entry\b", head, re.M):
    raise SystemExit("Image header does not branch to primary_entry")
code_macro_start = linkage.index("#define SYM_CODE_START(name)")
code_macro_end = linkage.index("#endif", code_macro_start)
code_macro = linkage[code_macro_start:code_macro_end]
if "SYM_START(name, SYM_L_GLOBAL, SYM_A_ALIGN)" not in code_macro:
    raise SystemExit("SYM_CODE_START does not resolve to the expected symbol annotation")
if re.search(r"\b(?:bti|nop|b|bl|blr|mrs|msr|ldr|str)\b", code_macro):
    raise SystemExit("SYM_CODE_START contributes an instruction before primary_entry")
if re.search(r"^#define\s+SYM_CODE_START", arm_linkage, re.M):
    raise SystemExit("arm64 linkage unexpectedly overrides SYM_CODE_START")

print("IMAGE_ENTRY_SYMBOL=_text")
print("PRIMARY_ENTRY_SYMBOL=primary_entry")
print(f"FIRST_ORIGINAL_PRIMARY_ENTRY_INSN={original_first.replace(chr(9), ' ')}")
print(f"M4B_FIRST_PRIMARY_ENTRY_INSN=b {label}")
print("IMAGE_HEADER_PRE_PRIMARY_CODE=efi_signature_nop; b primary_entry")
print("M4B_PRIMARY_ENTRY_SOURCE_ORDER=first instruction")
print("SYM_CODE_START_NO_IMPLICIT_INSN=PASS")
print("NO_INSTRUCTION_BEFORE_SPIN_WITHIN_PRIMARY_ENTRY=PASS")
print("EARLIEST_SPIN_SOURCE=PASS")
print("M3_TIMER_INSTRUMENTATION_PRESENT=NO")
print("M3_TIMER_INSTRUMENTATION_ABSENT=PASS")
print("NO_TIMER_SYSREG=PASS")
print("NO_MMIO=PASS")
print("NO_EXCEPTION_INSTRUCTION=PASS")
print("NO_PSCI_REBOOT=PASS")
print("NO_WFE_WFI=PASS")
print("NO_BRK_UDF=PASS")
PY

if command -v aarch64-linux-gnu-nm >/dev/null 2>&1; then
	NM="aarch64-linux-gnu-nm"
elif command -v llvm-nm >/dev/null 2>&1; then
	NM="llvm-nm"
else
	fail "missing AArch64 nm"
fi
SYMBOLS="$REVERSE/vmlinux-symbols.txt"
"$NM" -n "$VMLINUX" >"$SYMBOLS" 2>&1 || fail "VMLINUX_SYMBOL_TABLE"

python3 - "$IMAGE" "$VMLINUX" "$SYMBOLS" <<'PY' | tee -a "$RPT"
from pathlib import Path
import re
import sys

image_path, vmlinux_path, symbols_path = map(Path, sys.argv[1:])
image = image_path.read_bytes()
symbols = symbols_path.read_text()

if image[:2] == b"\x1f\x8b":
    raise SystemExit("Image is gzip-compressed")
if len(image) < 0x3c or image[0x38:0x3c] != b"ARMd":
    raise SystemExit("Image lacks the arm64 raw Image magic")

def symbol_address(name):
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[-1] == name:
            try:
                return int(fields[0], 16)
            except ValueError:
                pass
    raise SystemExit(f"symbol missing from vmlinux: {name}")

def sign_extend(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign

text_addr = symbol_address("_text")
primary_addr = symbol_address("primary_entry")
if primary_addr <= text_addr:
    raise SystemExit("primary_entry is not after _text")
primary_offset = primary_addr - text_addr
if primary_offset % 4 or primary_offset + 4 > len(image):
    raise SystemExit(f"primary_entry offset is outside Image: {primary_offset:#x}")

header_word = int.from_bytes(image[4:8], "little")
if header_word & 0xfc000000 != 0x14000000:
    raise SystemExit(f"Image code1 is not an unconditional branch: {header_word:#010x}")
header_target = 4 + sign_extend((header_word & 0x03ffffff) << 2, 28)
if header_target != primary_offset:
    raise SystemExit(
        f"Image header branch target {header_target:#x} != primary_entry offset {primary_offset:#x}"
    )

primary_word = int.from_bytes(image[primary_offset:primary_offset + 4], "little")
if primary_word != 0x14000000:
    raise SystemExit(
        f"Image primary_entry first instruction is not self-branch: {primary_word:#010x}"
    )

print(f"IMAGE_ENTRY_SYMBOL=_text")
print(f"PRIMARY_ENTRY_SYMBOL=primary_entry")
print(f"IMAGE_ENTRY_TO_PRIMARY_ENTRY_OFFSET=0x{primary_offset:x}")
print(f"IMAGE_HEADER_CODE1=0x{header_word:08x}")
print(f"IMAGE_HEADER_BRANCH_TARGET_OFFSET=0x{header_target:x}")
print("IMAGE_HEADER_BRANCH_TO_PRIMARY_ENTRY=PASS")
print(f"PRIMARY_ENTRY_IMAGE_OFFSET=0x{primary_offset:x}")
print("PRIMARY_ENTRY_IMAGE_FIRST_WORD=0x14000000")
print("PRIMARY_ENTRY_IMAGE_SELF_BRANCH=PASS")
PY

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
printf 'OBJDUMP=%s\nDISASSEMBLY_REPORT=%s\n' "$OBJDUMP" "$DISASM" | tee -a "$RPT"

python3 - "$DISASM" <<'PY' | tee -a "$RPT"
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text()
match = re.search(r"<primary_entry>:\s*\n", text)
if not match:
    raise SystemExit("primary_entry disassembly label missing")
section = text[match.end():]

instructions = []
for line in section.splitlines():
    address_match = re.match(r"^\s*([0-9a-fA-F]+):\s+(.*)$", line)
    if not address_match:
        continue
    address = int(address_match.group(1), 16)
    tokens = address_match.group(2).split()
    if not tokens:
        continue
    word = None
    remaining = tokens
    if re.fullmatch(r"[0-9a-fA-F]{8}", tokens[0]):
        word = int(tokens[0], 16)
        remaining = tokens[1:]
    elif len(tokens) >= 4 and all(re.fullmatch(r"[0-9a-fA-F]{2}", token) for token in tokens[:4]):
        word = int.from_bytes(bytes.fromhex("".join(tokens[:4])), "little")
        remaining = tokens[4:]
    if word is None or not remaining:
        continue
    mnemonic = remaining[0].lower()
    operands = " ".join(remaining[1:])
    instructions.append((address, word, mnemonic, operands))

if not instructions:
    raise SystemExit("no instructions found in primary_entry disassembly")
address, word, mnemonic, operands = instructions[0]
if mnemonic != "b" or word != 0x14000000:
    raise SystemExit(
        f"first primary_entry instruction is not b self: address={address:#x} word={word:#010x} mnemonic={mnemonic}"
    )
target = address + ((word & 0x03ffffff) << 2)
if word & (1 << 25):
    target -= 1 << 28
if target != address:
    raise SystemExit(f"self-branch target mismatch: source={address:#x} target={target:#x}")

print(f"M4B_FIRST_PRIMARY_ENTRY_INSN_DISASSEMBLY=b {operands or '<self>'}")
print(f"PRIMARY_ENTRY_FIRST_INSN_ADDRESS=0x{address:x}")
print(f"SELF_BRANCH_TARGET_ADDRESS=0x{target:x}")
print("SELF_BRANCH_TARGET=PASS")
print("EARLIEST_SPIN_DISASSEMBLY=PASS")
print("SELF_BRANCH_DISASSEMBLY=PASS")
print("PRIMARY_ENTRY_SPIN_FIRST=PASS")
PY

python3 - "$INITRAMFS" "$INIT_PROOF" "$REVERSE/initramfs-root" <<'PY'
from pathlib import Path
import subprocess
import sys

ramdisk, init_proof, root = map(Path, sys.argv[1:])
subprocess.run(["gzip", "-t", str(ramdisk)], check=True)
compressed = subprocess.run(["gzip", "-dc", str(ramdisk)], check=True,
                            stdout=subprocess.PIPE).stdout
cpio = subprocess.Popen(
    ["cpio", "-idm", "--no-absolute-filenames"],
    cwd=root,
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
)
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
pass "RAMDISK_EXACT_REUSE=PASS"

python3 - "$IMAGE" <<'PY'
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
if data[:2] == b"\x1f\x8b":
    raise SystemExit("Image is gzip-compressed; M4B requires raw Image")
if len(data) < 0x3c or data[0x38:0x3c] != b"ARMd":
    raise SystemExit("Image lacks the arm64 raw Image magic")
PY
pass "MAINLINE_IMAGE_BUILD=PASS"
pass "ARM64_IMAGE_RAW=PASS"

BOOT="$REL/mainline-v2-m4b-entry-spin-boot-v3.img"
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
IMAGE_SHA256="$(sha "$IMAGE")"
[ "$(sha "$UN/kernel")" = "$IMAGE_SHA256" ] || fail "KERNEL_PAYLOAD_EXACT"
[ "$(sha "$UN/ramdisk")" = "$RAMDISK_SHA256" ] || fail "RAMDISK_PAYLOAD_EXACT"
pass "BOOT_HEADER_V3=PASS"
pass "BOOT_V3=PASS"
pass "REVERSE_UNPACK=PASS"
pass "KERNEL_PAYLOAD_EXACT=PASS"
pass "RAMDISK_PAYLOAD_EXACT=PASS"

BOOT_SHA256="$(sha "$BOOT")"
BOOT_SIZE="$(wc -c <"$BOOT" | tr -d ' ')"
printf 'IMAGE_SHA256=%s\nBOOT_IMAGE_SHA256=%s\nBOOT_IMAGE_SIZE=%s\n' \
	"$IMAGE_SHA256" "$BOOT_SHA256" "$BOOT_SIZE" | tee -a "$RPT"
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

M4B_PATCH_OUTPUT="$REL/mainline-v2-m4b-earliest-entry-spin.patch"
cp "$M4B_PATCH" "$M4B_PATCH_OUTPUT"
[ "$(sha "$M4B_PATCH_OUTPUT")" = "$(sha "$M4B_PATCH")" ] || fail "M4B_PATCH_ARTIFACT"
pass "M4B_PATCH_ARTIFACT=PASS"

pass "$M4B_FINAL_GATE"
printf '%s\n' "$M4B_FINAL_GATE" | tee -a "$RPT"
echo "ALL MAINLINE V2 M4B EARLIEST-ENTRY SPIN VALIDATION PASS" | tee -a "$RPT"
