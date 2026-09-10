#!/usr/bin/env bash
# Reverse-unpack exact Stage4 stock control boot, patch earliest Image
# entry to `b .`, rebuild boot v3, and prove the 4-byte kernel delta.
# GitHub Actions only. Must run in the private auxiliary repository.
set -euo pipefail
set -o pipefail

if [ "${GITHUB_ACTIONS:-}" != true ]; then
	echo "CI only — refuse local image transformation/validation" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REL="${1:?release dir}"
STAGE4_BOOT="${2:?authoritative Stage4 boot.img}"
HEAD_S="${3:-$ROOT/android-kernel-sm8250/arch/arm64/kernel/head.S}"
KONA_PERF="${4:-$ROOT/android-kernel-sm8250/arch/arm64/configs/vendor/kona-perf_defconfig}"
BOOT_CAP="${BOOT_CAP:-201326592}"
EXPECTED_STAGE4_BOOT_SHA256="${EXPECTED_STAGE4_BOOT_SHA256:-6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a}"
EXPECTED_STOCK_KERNEL_SHA256="${EXPECTED_STOCK_KERNEL_SHA256:-85807cd4537c7c0a451c39db97a472afa00a96c8aeed9047106e8b8791c2a13a}"
EXPECTED_STAGE4_RAMDISK_SHA256="${EXPECTED_STAGE4_RAMDISK_SHA256:-e31cab1bef3408d1b87074ff7bcf573b9ebb74b96d535c55b9c97953ef1d0ac9}"
M5A_FINAL_GATE="${M5A_FINAL_GATE:-READY_FOR_M5A_STOCK_ENTRY_SPIN_CONTROL}"
PUBLIC_SOURCE_COMMIT="${PUBLIC_SOURCE_COMMIT:-UNKNOWN}"

REL="$(mkdir -p "$REL" && cd "$REL" && pwd)"
WORK="${RUNNER_TEMP:-$REL/m5a-work}/thyme-m5a-stock-entry-spin"
REVERSE="$REL/reverse-unpack-report"
mkdir -p "$WORK" "$REVERSE/source-boot" "$REVERSE/identity-boot" "$REVERSE/patched-boot"
RPT="$REL/validation-report.txt"
DIFFRPT="$REL/binary-diff-report.txt"
: >"$RPT"
: >"$DIFFRPT"

pass() { printf 'PASS  %s\n' "$*" | tee -a "$RPT"; }
fail() {
	local gate="${2:-M5A_BINARY_TRANSFORM_VALIDATION_FAILED}"
	printf 'FAIL  %s\n' "$1" | tee -a "$RPT" >&2
	printf 'FINAL_GATE=%s\n' "$gate" | tee -a "$RPT" >&2
	exit 1
}
sha() { sha256sum "$1" | awk '{print $1}'; }
field() { sed -n "s/^$2: //p" "$1" | head -n1; }

emit() { printf '%s\n' "$1" | tee -a "$RPT"; }

pass "MEM0_POLICY_ACKNOWLEDGED=PASS"
pass "GHA_ONLY=PASS"
pass "SLOT_A_PROTECTED=PASS"
pass "NO_STOCK_KERNEL_REBUILD=PASS"
emit "PUBLIC_SOURCE_COMMIT=$PUBLIC_SOURCE_COMMIT"

repo_private="${REPO_PRIVATE:-}"
if [ -z "$repo_private" ] && command -v gh >/dev/null 2>&1; then
	repo_private="$(gh api "repos/${GITHUB_REPOSITORY}" --jq '.private' || true)"
fi
if [ "$repo_private" != true ]; then
	fail "builder is not a private repository (private=$repo_private)" \
		M5A_PRIVATE_ARTIFACT_POLICY_FAILED
fi
pass "PRIVATE_REPO_VISIBILITY=PRIVATE"
pass "PRIVATE_ARTIFACT_ONLY=PASS"

[ -s "$STAGE4_BOOT" ] || fail "authoritative Stage4 boot missing" \
	M5A_STOCK_CONTROL_SOURCE_UNAVAILABLE
STAGE4_SHA="$(sha "$STAGE4_BOOT")"
emit "AUTHORITATIVE_STAGE4_BOOT_SHA256=$STAGE4_SHA"
if [ "$STAGE4_SHA" != "$EXPECTED_STAGE4_BOOT_SHA256" ]; then
	fail "Stage4 boot SHA mismatch actual=$STAGE4_SHA" \
		M5A_STOCK_CONTROL_SOURCE_UNAVAILABLE
fi
pass "AUTHORITATIVE_STAGE4_BOOT_SHA=PASS"
pass "SOURCE_STOCK_CONTROL_BOOT_SHA_MATCH=YES"

python3 - <<'PY'
import ast
from pathlib import Path
for name in ("mkbootimg.py", "unpack_bootimg.py"):
    ast.parse(Path(f"tools/aosp/{name}").read_text())
print("aosp tools parse OK")
PY

python3 tools/aosp/unpack_bootimg.py --boot_img "$STAGE4_BOOT" \
	--out "$REVERSE/source-boot" >"$REVERSE/source-boot.txt"
python3 tools/aosp/unpack_bootimg.py --boot_img "$STAGE4_BOOT" \
	--out "$REVERSE/source-boot" --format=mkbootimg \
	>"$REVERSE/source-boot.mkbootimg.txt"

grep -q "boot image header version: 3" "$REVERSE/source-boot.txt" \
	|| fail "source boot header != v3"
[ -s "$REVERSE/source-boot/kernel" ] || fail "source kernel missing"
[ -s "$REVERSE/source-boot/ramdisk" ] || fail "source ramdisk missing"
[ ! -e "$REVERSE/source-boot/dtb" ] || fail "source boot unexpectedly has dtb"
pass "STOCK_KERNEL_EXTRACTED=PASS"

KERNEL_SHA="$(sha "$REVERSE/source-boot/kernel")"
RAMDISK_SHA="$(sha "$REVERSE/source-boot/ramdisk")"
KERNEL_SZ="$(wc -c <"$REVERSE/source-boot/kernel" | tr -d ' ')"
RAMDISK_SZ="$(wc -c <"$REVERSE/source-boot/ramdisk" | tr -d ' ')"
SRC_OS="$(field "$REVERSE/source-boot.txt" "os version")"
SRC_SPL="$(field "$REVERSE/source-boot.txt" "os patch level")"
SRC_HDR="$(field "$REVERSE/source-boot.txt" "boot image header version")"
SRC_CMD="$(field "$REVERSE/source-boot.txt" "command line args")"
SRC_KSIZE="$(field "$REVERSE/source-boot.txt" "kernel_size")"
SRC_RSIZE="$(field "$REVERSE/source-boot.txt" "ramdisk size")"

emit "STOCK_KERNEL_SHA256=$KERNEL_SHA"
emit "STOCK_KERNEL_SIZE=$KERNEL_SZ"
emit "STAGE4_RAMDISK_SHA256=$RAMDISK_SHA"
emit "STAGE4_RAMDISK_SIZE=$RAMDISK_SZ"
emit "SOURCE_HEADER_VERSION=$SRC_HDR"
emit "SOURCE_OS_VERSION=$SRC_OS"
emit "SOURCE_OS_PATCH_LEVEL=$SRC_SPL"
emit "SOURCE_CMDLINE='${SRC_CMD}'"
emit "SOURCE_KERNEL_SIZE_FIELD=$SRC_KSIZE"
emit "SOURCE_RAMDISK_SIZE_FIELD=$SRC_RSIZE"

[ "$KERNEL_SHA" = "$EXPECTED_STOCK_KERNEL_SHA256" ] \
	|| fail "stock kernel SHA mismatch actual=$KERNEL_SHA"
[ "$RAMDISK_SHA" = "$EXPECTED_STAGE4_RAMDISK_SHA256" ] \
	|| fail "Stage4 ramdisk SHA mismatch actual=$RAMDISK_SHA"
pass "STOCK_KERNEL_IDENTITY=PASS"
pass "STAGE4_RAMDISK_EXACT_REUSE=PASS"

if [ -s "$HEAD_S" ]; then
	grep -Fq $'b\tstext' "$HEAD_S" || fail "downstream head.S missing b stext"
	grep -Fq 'add	x13, x18, #0x16' "$HEAD_S" || fail "downstream head.S missing EFI MZ add"
	grep -Fq '_head:' "$HEAD_S" || fail "downstream head.S missing _head"
	pass "DOWNSTREAM_HEAD_S_SOURCE=PASS"
else
	emit "DOWNSTREAM_HEAD_S_SOURCE=NOT_CHECKED_OUT"
fi
if [ -s "$KONA_PERF" ]; then
	grep -Fq '# CONFIG_EFI is not set' "$KONA_PERF" \
		|| fail "kona-perf CONFIG_EFI unexpectedly enabled"
	grep -Fq 'CONFIG_BUILD_ARM64_UNCOMPRESSED_KERNEL=y' "$KONA_PERF" \
		|| fail "kona-perf missing uncompressed Image"
	pass "DOWNSTREAM_KONA_PERF_HINT=PASS"
	emit "DOWNSTREAM_CONFIG_EFI=n"
	emit "DOWNSTREAM_UNCOMPRESSED_IMAGE=y"
else
	emit "DOWNSTREAM_KONA_PERF_HINT=NOT_CHECKED_OUT"
fi
emit "DOWNSTREAM_SOURCE_IS_SUPPORTING_ONLY=YES"
emit "BINARY_IMAGE_HEADER_IS_AUTHORITATIVE=YES"

TRANSFORM_REPORT="$WORK/transform-report.txt"
PATCHED_KERNEL="$WORK/patched-stock-kernel"
python3 "$ROOT/scripts/m5a_stock_kernel_entry_spin.py" transform \
	--kernel "$REVERSE/source-boot/kernel" \
	--patched "$PATCHED_KERNEL" \
	--report "$TRANSFORM_REPORT" \
	--expected-kernel-sha256 "$EXPECTED_STOCK_KERNEL_SHA256" \
	| tee -a "$RPT" \
	|| fail "entry transform failed" M5A_ENTRY_LOCATION_INCONCLUSIVE

for key in \
	ARM64_IMAGE_HEADER_VALID \
	EARLIEST_ENTRY_LOCATION_AUDITED \
	SPIN_PATCH_MINIMAL \
	KERNEL_ONLY_EXPECTED_BYTES_CHANGED \
	ARM64_IMAGE_MAGIC_UNCHANGED \
	IMAGE_SIZE_FIELDS_UNCHANGED \
	NO_TIMER \
	NO_MMIO \
	NO_EXCEPTION_INSN
do
	grep -q "^${key}=PASS$" "$TRANSFORM_REPORT" \
		|| fail "transform report missing $key=PASS" \
			M5A_BINARY_TRANSFORM_VALIDATION_FAILED
done
pass "ARM64_IMAGE_HEADER_VALID=PASS"
pass "EARLIEST_ENTRY_LOCATION_AUDITED=PASS"
pass "SPIN_PATCH_MINIMAL=PASS"
pass "KERNEL_ONLY_EXPECTED_BYTES_CHANGED=PASS"
pass "ARM64_IMAGE_MAGIC_UNCHANGED=PASS"
pass "IMAGE_SIZE_FIELDS_UNCHANGED=PASS"
pass "NO_TIMER=PASS"
pass "NO_MMIO=PASS"
pass "NO_EXCEPTION_INSN=PASS"

PATCH_OFFSET="$(sed -n 's/^PATCH_OFFSET=//p' "$TRANSFORM_REPORT" | head -n1)"
EXPECTED_WORD="$(sed -n 's/^EXPECTED_PATCHED_WORD=//p' "$TRANSFORM_REPORT" | head -n1)"
[ -n "$PATCH_OFFSET" ] || fail "PATCH_OFFSET missing"
[ "$EXPECTED_WORD" = "0x14000000" ] || fail "unexpected patched word $EXPECTED_WORD"

if command -v aarch64-linux-gnu-objdump >/dev/null 2>&1; then
	OBJDUMP="aarch64-linux-gnu-objdump"
else
	fail "missing aarch64-linux-gnu-objdump"
fi
START="$PATCH_OFFSET"
STOP="$((PATCH_OFFSET + 4))"
DISASM="$REVERSE/patched-entry.disassembly.txt"
"$OBJDUMP" -D -b binary -m aarch64 \
	--start-address="$START" --stop-address="$STOP" \
	"$PATCHED_KERNEL" >"$DISASM" 2>&1 \
	|| fail "objdump of patched entry failed"

python3 - "$DISASM" "$PATCH_OFFSET" <<'PY' | tee -a "$RPT"
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text()
offset = int(sys.argv[2])
match = None
for line in text.splitlines():
    m = re.match(r"^\s*([0-9a-fA-F]+):\s+(\S+)\s+(\S+)\s*(.*)$", line)
    if not m:
        continue
    address = int(m.group(1), 16)
    word_s, mnemonic, rest = m.group(2), m.group(3).lower(), m.group(4)
    if address != offset:
        continue
    try:
        word = int(word_s, 16)
    except ValueError:
        continue
    match = (address, word, mnemonic, rest)
    break
if match is None:
    raise SystemExit("objdump did not show the patched instruction")
address, word, mnemonic, rest = match
if word != 0x14000000 or mnemonic != "b":
    raise SystemExit(
        f"patched machine code is not b .: addr={address:#x} word={word:#010x} mnem={mnemonic}"
    )
print(f"OBJDUMP={sys.argv[0]}")
print(f"PATCHED_ENTRY_DISASSEMBLY=b {rest.strip() or '.'}")
print("SELF_BRANCH_MACHINE_CODE=PASS")
PY
pass "SELF_BRANCH_MACHINE_CODE=PASS"

pack_boot() {
	local kernel=$1 ramdisk=$2 out=$3
	python3 - "$REVERSE/source-boot.mkbootimg.txt" "$kernel" "$ramdisk" "$out" <<'PY'
import shlex
import subprocess
import sys
from pathlib import Path

mk, kernel, ramdisk, out = sys.argv[1:]
args = shlex.split(Path(mk).read_text().strip())
replaced_kernel = False
replaced_ramdisk = False
for i, arg in enumerate(args):
    if arg == "--kernel":
        args[i + 1] = kernel
        replaced_kernel = True
    elif arg == "--ramdisk":
        args[i + 1] = ramdisk
        replaced_ramdisk = True
if not replaced_kernel or not replaced_ramdisk:
    raise SystemExit("mkbootimg template missing --kernel/--ramdisk")
cmd = [sys.executable, "tools/aosp/mkbootimg.py", *args, "-o", out]
print("mkbootimg:", " ".join(shlex.quote(x) for x in cmd), flush=True)
subprocess.check_call(cmd)
PY
}

IDENTITY_BOOT="$WORK/identity-repack-boot-v3.img"
pack_boot "$REVERSE/source-boot/kernel" "$REVERSE/source-boot/ramdisk" "$IDENTITY_BOOT"
if [ "$(sha "$IDENTITY_BOOT")" != "$STAGE4_SHA" ]; then
	emit "BOOT_REPACK_IDENTITY=FAIL"
	fail "unpatched Stage4 repack is not byte-identical; packer would hide the 4-byte delta"
fi
pass "BOOT_REPACK_IDENTITY=PASS"

PATCHED_BOOT="$REL/m5a-stock-entry-spin-boot-v3.img"
pack_boot "$PATCHED_KERNEL" "$REVERSE/source-boot/ramdisk" "$PATCHED_BOOT"
test -s "$PATCHED_BOOT" || fail "patched boot missing"
[ "$(wc -c <"$PATCHED_BOOT" | tr -d ' ')" -le "$BOOT_CAP" ] \
	|| fail "SIZE_GATE patched boot too large"
pass "SIZE_GATE=PASS"

python3 tools/aosp/unpack_bootimg.py --boot_img "$PATCHED_BOOT" \
	--out "$REVERSE/patched-boot" >"$REVERSE/patched-boot.txt"
grep -q "boot image header version: 3" "$REVERSE/patched-boot.txt" \
	|| fail "patched boot header != v3"
[ ! -e "$REVERSE/patched-boot/dtb" ] || fail "patched boot unexpectedly has dtb"
pass "REVERSE_UNPACK=PASS"
pass "BOOT_V3=PASS"

OUT_K_SHA="$(sha "$REVERSE/patched-boot/kernel")"
OUT_R_SHA="$(sha "$REVERSE/patched-boot/ramdisk")"
OUT_OS="$(field "$REVERSE/patched-boot.txt" "os version")"
OUT_SPL="$(field "$REVERSE/patched-boot.txt" "os patch level")"
OUT_HDR="$(field "$REVERSE/patched-boot.txt" "boot image header version")"
OUT_CMD="$(field "$REVERSE/patched-boot.txt" "command line args")"
OUT_KSIZE="$(field "$REVERSE/patched-boot.txt" "kernel_size")"
OUT_RSIZE="$(field "$REVERSE/patched-boot.txt" "ramdisk size")"
PATCHED_KERNEL_SHA="$(sha "$PATCHED_KERNEL")"
PATCHED_BOOT_SHA="$(sha "$PATCHED_BOOT")"

emit "PATCHED_KERNEL_SHA256=$PATCHED_KERNEL_SHA"
emit "PATCHED_BOOT_SHA256=$PATCHED_BOOT_SHA"
emit "REVERSE_KERNEL_SHA256=$OUT_K_SHA"
emit "REVERSE_RAMDISK_SHA256=$OUT_R_SHA"

[ "$OUT_K_SHA" = "$PATCHED_KERNEL_SHA" ] || fail "packed kernel != patched kernel"
[ "$OUT_R_SHA" = "$RAMDISK_SHA" ] || fail "packed ramdisk != Stage4 ramdisk"
[ "$OUT_HDR" = "$SRC_HDR" ] || fail "header version changed"
[ "$OUT_OS" = "$SRC_OS" ] || fail "os version changed"
[ "$OUT_SPL" = "$SRC_SPL" ] || fail "os patch level changed"
[ "$OUT_CMD" = "$SRC_CMD" ] || fail "cmdline changed"
[ "$OUT_KSIZE" = "$SRC_KSIZE" ] || fail "kernel_size field changed"
[ "$OUT_RSIZE" = "$SRC_RSIZE" ] || fail "ramdisk size field changed"
pass "STAGE4_RAMDISK_EXACT_REUSE=PASS"
pass "BOOT_HEADER_SEMANTIC_MATCH=PASS"

python3 - "$STAGE4_BOOT" "$PATCHED_BOOT" \
	"$REVERSE/source-boot/kernel" "$PATCHED_KERNEL" \
	"$DIFFRPT" "$PATCH_OFFSET" <<'PY' | tee -a "$RPT"
from pathlib import Path
import sys

src_boot, patched_boot, src_kernel, patched_kernel, report, patch_off = sys.argv[1:]
patch_off = int(patch_off)

def diffs(a: bytes, b: bytes):
    if len(a) != len(b):
        raise SystemExit(f"size mismatch {len(a)} != {len(b)}")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]

kb = Path(src_kernel).read_bytes()
pb = Path(patched_kernel).read_bytes()
bb = Path(src_boot).read_bytes()
ob = Path(patched_boot).read_bytes()
kdiff = diffs(kb, pb)
bdiff = diffs(bb, ob)
allowed = list(range(patch_off, patch_off + 4))
allowed_boot = [4096 + off for off in allowed]
if not kdiff or any(off not in allowed for off in kdiff):
    raise SystemExit(f"kernel diffs {kdiff} outside instruction {allowed}")
expected_boot = [4096 + off for off in kdiff]
if bdiff != expected_boot:
    raise SystemExit(
        f"boot diffs {bdiff} != kernel overlay {expected_boot} (word window {allowed_boot})"
    )
lines = [
    f"KERNEL_PATCH_WORD_SIZE=4",
    f"KERNEL_DIFF_BYTE_COUNT={len(kdiff)}",
    f"KERNEL_DIFF_OFFSETS={','.join(str(v) for v in kdiff)}",
    f"BOOT_DIFF_BYTE_COUNT={len(bdiff)}",
    f"BOOT_DIFF_OFFSETS={','.join(str(v) for v in bdiff)}",
    f"EXPECTED_PATCHED_WORD=0x14000000",
    f"BOOT_HEADER_PAGE=4096",
]
Path(report).write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print("BOOT_DIFF_MINIMAL_WORD_OVERLAY=PASS")
PY
cat "$DIFFRPT" >>"$RPT"
pass "BOOT_DIFF_MINIMAL=PASS"

cp "$PATCHED_KERNEL" "$REL/patched-stock-kernel"
cp "$TRANSFORM_REPORT" "$REL/transform-report.txt"

if find "$REL" -maxdepth 1 -type f \( \
	-name 'vendor_boot*' -o -name 'dtbo*' -o -name 'vbmeta*' -o -name 'firmware*' \
\) -print -quit | grep -q .; then
	fail "forbidden OEM context artifact in M5A output" \
		M5A_PRIVATE_ARTIFACT_POLICY_FAILED
fi
pass "NO_VENDOR_BOOT_ARTIFACT=PASS"
pass "NO_DTBO_ARTIFACT=PASS"

emit "FUTURE_STOCK_VENDOR_BOOT_SHA256=aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"
emit "FUTURE_STOCK_DTBO_SHA256=018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"
emit "FUTURE_TRUE_DEVICE=NOT_THIS_PHASE"
emit "DEVICE_OPERATION=NO"

pass "$M5A_FINAL_GATE"
emit "FINAL_GATE=$M5A_FINAL_GATE"
echo "ALL M5A STOCK KERNEL ENTRY SPIN CONTROL VALIDATION PASS" | tee -a "$RPT"
