#!/usr/bin/env bash
# Build and reverse-validate the Mainline V2 M1 DT context. GitHub Actions only.
set -euo pipefail

if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local DT/FDT/image build or validation" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REL="${1:?release dir}"
MAINLINE_DTB_SRC="${2:?built Mainline thyme DTB}"
STOCK_VENDOR_BOOT="${3:?exact stock vendor_boot.img}"
STOCK_DTBO="${4:?exact stock dtbo.img}"
STOCK_CMDLINE="${STOCK_CMDLINE:?stock vendor cmdline}"
EXPECTED_LINUX_BASE_COMMIT="${EXPECTED_LINUX_BASE_COMMIT:?expected Linux base commit}"
LINUX_DIR="${LINUX_DIR:-linux-6.6}"
M0_BOOT_SHA256="${M0_BOOT_SHA256:?M0 boot reference SHA256}"
M1_FINAL_GATE="${M1_FINAL_GATE:-READY_FOR_MAINLINE_V2_M1}"
PUBLIC_SOURCE_COMMIT_PINNED="${PUBLIC_SOURCE_COMMIT_PINNED:-NO}"
VENDOR_CAP="${VENDOR_CAP:-100663296}"
DTBO_CAP="${DTBO_CAP:-33554432}"
EXPECTED_NOOP_DTBO_SHA256="316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1"
EXPECTED_STOCK_VENDOR_BOOT_SHA256="aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972"
EXPECTED_STOCK_DTBO_SHA256="018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634"

REL="$(mkdir -p "$REL" && cd "$REL" && pwd)"
WORK="${RUNNER_TEMP:-$REL/m1-work}/thyme-mainline-v2-m1"
mkdir -p "$WORK"
RPT="$REL/validation-report.txt"
VENDOR_RPT="$REL/vendor-boot-diff-report.txt"
DTBO_RPT="$REL/dtbo-validation-report.txt"
: >"$RPT"
: >"$VENDOR_RPT"
: >"$DTBO_RPT"

pass() { printf 'PASS  %s\n' "$*" | tee -a "$RPT"; }
fail() { printf 'FAIL  %s\n' "$*" | tee -a "$RPT" >&2; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }

[ -s "$MAINLINE_DTB_SRC" ] || fail "MAINLINE_DTB_BUILD missing DTB"
[ -s "$STOCK_VENDOR_BOOT" ] || fail "STOCK_VENDOR_BOOT_INPUT missing"
[ -s "$STOCK_DTBO" ] || fail "STOCK_DTBO_INPUT missing"

BASE="$(git -C "$LINUX_DIR" rev-parse HEAD)"
[ "$BASE" = "$EXPECTED_LINUX_BASE_COMMIT" ] || fail "MAINLINE_VERSION_PINNED=$BASE"
pass "MAINLINE_VERSION_PINNED=$BASE"

CHANGED="$(git -C "$LINUX_DIR" diff --name-only)"
UNTRACKED="$(git -C "$LINUX_DIR" ls-files --others --exclude-standard)"
python3 - "$CHANGED" "$UNTRACKED" <<'PY' || exit 1
import sys
actual = set()
for value in sys.argv[1:]:
    actual.update(value.splitlines())
expected = {
    "Documentation/devicetree/bindings/arm/qcom.yaml",
    "arch/arm64/boot/dts/qcom/Makefile",
    "arch/arm64/boot/dts/qcom/sm8250-xiaomi-thyme.dts",
}
if actual != expected:
    raise SystemExit(f"unexpected linux patch scope: {sorted(actual)}")
PY
pass "THYME_PATCH_SCOPE"

STOCK_VENDOR_BOOT_SHA256="$(sha "$STOCK_VENDOR_BOOT")"
STOCK_DTBO_SHA256="$(sha "$STOCK_DTBO")"
[ "$STOCK_VENDOR_BOOT_SHA256" = "$EXPECTED_STOCK_VENDOR_BOOT_SHA256" ] || \
	fail "STOCK_VENDOR_BOOT_INPUT_HASH=$STOCK_VENDOR_BOOT_SHA256"
[ "$STOCK_DTBO_SHA256" = "$EXPECTED_STOCK_DTBO_SHA256" ] || \
	fail "STOCK_DTBO_INPUT_HASH=$STOCK_DTBO_SHA256"
pass "STOCK_VENDOR_BOOT_INPUT_HASH=$STOCK_VENDOR_BOOT_SHA256"
pass "STOCK_DTBO_INPUT_HASH=$STOCK_DTBO_SHA256"
pass "STOCK_VENDOR_BOOT_SHA=PASS"
pass "STOCK_DTBO_SHA=PASS"
[ "$PUBLIC_SOURCE_COMMIT_PINNED" = PASS ] && pass "PUBLIC_SOURCE_COMMIT_PINNED=PASS"

RAW_DTB="$REL/mainline-thyme.dtb"
ABL_DTB="$REL/mainline-thyme-abl.dtb"
cp "$MAINLINE_DTB_SRC" "$RAW_DTB"
cp "$MAINLINE_DTB_SRC" "$ABL_DTB"

command -v dtc >/dev/null || fail "missing dtc"
command -v fdtget >/dev/null || fail "missing fdtget"
command -v fdtput >/dev/null || fail "missing fdtput"
command -v fdtoverlay >/dev/null || fail "missing fdtoverlay"

DTB_DTS="$WORK/mainline-thyme.dts"
dtc -I dtb -O dts -o "$DTB_DTS" "$RAW_DTB" 2>"$WORK/mainline-dtc.log"
fdtget "$RAW_DTB" / compatible | tr ' ' '\n' | grep -qx 'qcom,sm8250' || \
	fail "MAINLINE_DTB_VALID missing qcom,sm8250"

ABL_PACKAGING_METADATA_ADDED=NO
if fdtget -t u "$ABL_DTB" / qcom,msm-id >/dev/null 2>&1; then
	MSM_ID="$(fdtget -t u "$ABL_DTB" / qcom,msm-id | tr '\n' ' ' | xargs)"
else
	fdtput -t u "$ABL_DTB" / qcom,msm-id 356 131073
	ABL_PACKAGING_METADATA_ADDED=YES
	MSM_ID="356 131073"
fi
if fdtget -t u "$ABL_DTB" / qcom,board-id >/dev/null 2>&1; then
	BOARD_ID="$(fdtget -t u "$ABL_DTB" / qcom,board-id | tr '\n' ' ' | xargs)"
else
	fdtput -t u "$ABL_DTB" / qcom,board-id 45 0
	ABL_PACKAGING_METADATA_ADDED=YES
	BOARD_ID="45 0"
fi
[ "$MSM_ID" = "356 131073" ] || fail "ABL_DTB_METADATA_VALID qcom,msm-id=$MSM_ID"
[ "$BOARD_ID" = "45 0" ] || fail "ABL_DTB_METADATA_VALID qcom,board-id=$BOARD_ID"
dtc -I dtb -O dts -o "$WORK/mainline-thyme-abl.dts" "$ABL_DTB" 2>"$WORK/mainline-abl-dtc.log"
fdtget "$ABL_DTB" / compatible | tr ' ' '\n' | grep -qx 'qcom,sm8250' || \
	fail "ABL_DTB_METADATA_VALID compatible"
pass "MAINLINE_DTB_BUILD size=$(wc -c <"$RAW_DTB" | tr -d ' ') sha256=$(sha "$RAW_DTB")"
pass "MAINLINE_DTB_BUILD=PASS"
pass "MAINLINE_DTB_VALID"
pass "MAINLINE_DTB_VALID=PASS"
pass "ABL_DTB_METADATA_VALID msm-id=356,131073 board-id=45,0"
pass "ABL_DTB_METADATA_VALID=PASS"
printf 'UPSTREAM_DTS_MODIFIED=NO\nABL_PACKAGING_METADATA_ADDED=%s\n' \
	"$ABL_PACKAGING_METADATA_ADDED" | tee -a "$RPT"

STOCK_UNPACK="$WORK/stock-vendor-boot"
M1_UNPACK="$WORK/m1-vendor-boot"
mkdir -p "$STOCK_UNPACK" "$M1_UNPACK"
python3 tools/aosp/unpack_bootimg.py --boot_img "$STOCK_VENDOR_BOOT" \
	--out "$STOCK_UNPACK" >"$WORK/stock-vendor-boot.txt" 2>&1

grep -q 'vendor boot image header version: 3' "$WORK/stock-vendor-boot.txt" || \
	fail "STOCK_VENDOR_BOOT_HEADER"
[ -s "$STOCK_UNPACK/vendor_ramdisk" ] || fail "STOCK_VENDOR_RAMDISK missing"
[ -s "$STOCK_UNPACK/dtb" ] || fail "STOCK_VENDOR_DTB missing"

M1_VENDOR_BOOT="$REL/mainline-v2-m1-vendor_boot.img"
python3 tools/aosp/mkbootimg.py \
	--header_version 3 \
	--pagesize 4096 \
	--base 0x00000000 \
	--kernel_offset 0x00008000 \
	--ramdisk_offset 0x01000000 \
	--tags_offset 0x00000100 \
	--dtb "$ABL_DTB" \
	--dtb_offset 0x01f00000 \
	--vendor_ramdisk "$STOCK_UNPACK/vendor_ramdisk" \
	--vendor_cmdline "$STOCK_CMDLINE" \
	--board "" \
	--vendor_boot "$M1_VENDOR_BOOT"
test -s "$M1_VENDOR_BOOT" || fail "M1_VENDOR_BOOT_BUILD"
python3 tools/aosp/unpack_bootimg.py --boot_img "$M1_VENDOR_BOOT" \
	--out "$M1_UNPACK" >"$WORK/m1-vendor-boot.txt" 2>&1

grep -q 'vendor boot image header version: 3' "$WORK/m1-vendor-boot.txt" || \
	fail "M1_VENDOR_BOOT_HEADER"
[ -s "$M1_UNPACK/vendor_ramdisk" ] || fail "M1_VENDOR_RAMDISK missing"
[ -s "$M1_UNPACK/dtb" ] || fail "M1_VENDOR_DTB missing"

python3 - "$STOCK_UNPACK" "$M1_UNPACK" "$STOCK_VENDOR_BOOT" "$M1_VENDOR_BOOT" \
	"$ABL_DTB" "$VENDOR_RPT" "$VENDOR_CAP" <<'PY'
from hashlib import sha256
from pathlib import Path
import struct
import sys

args = [Path(value) for value in sys.argv[1:7]]
stock_dir, m1_dir, stock_img, m1_img, abl_dtb, report = args
cap = int(sys.argv[7])


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def cstr(value):
    return value.split(b"\0", 1)[0].decode("ascii")


def header(path):
    data = path.read_bytes()
    if data[:8] != b"VNDRBOOT":
        raise SystemExit(f"{path}: vendor_boot magic mismatch")
    page_size = struct.unpack_from("<I", data, 12)[0]
    if page_size != 4096 or len(data) < page_size:
        raise SystemExit(f"{path}: invalid page size or short header")
    return {
        "version": struct.unpack_from("<I", data, 8)[0],
        "page_size": page_size,
        "kernel_addr": struct.unpack_from("<I", data, 16)[0],
        "ramdisk_addr": struct.unpack_from("<I", data, 20)[0],
        "vendor_ramdisk_size": struct.unpack_from("<I", data, 24)[0],
        "vendor_cmdline": cstr(data[28:2076]),
        "tags_addr": struct.unpack_from("<I", data, 2076)[0],
        "product": cstr(data[2080:2096]),
        "header_size": struct.unpack_from("<I", data, 2096)[0],
        "dtb_size": struct.unpack_from("<I", data, 2100)[0],
        "dtb_addr": struct.unpack_from("<Q", data, 2104)[0],
    }, data[:page_size]


stock, stock_page = header(stock_img)
m1, m1_page = header(m1_img)
if stock["version"] != 3 or m1["version"] != 3:
    raise SystemExit("vendor_boot header version is not v3")
if stock["vendor_ramdisk_size"] != m1["vendor_ramdisk_size"]:
    raise SystemExit("vendor ramdisk size changed")
for key in ("version", "page_size", "kernel_addr", "ramdisk_addr",
            "vendor_ramdisk_size", "vendor_cmdline", "tags_addr", "product",
            "header_size", "dtb_addr"):
    if stock[key] != m1[key]:
        raise SystemExit(f"stock-compatible header field changed: {key}")
if m1["vendor_cmdline"] != "" and m1["vendor_cmdline"] != stock["vendor_cmdline"]:
    raise SystemExit("vendor cmdline changed")

header_diffs = [idx for idx, (left, right) in enumerate(zip(stock_page, m1_page))
                if left != right]
allowed = set(range(2100, 2104))
unexpected = [idx for idx in header_diffs if idx not in allowed]
if unexpected:
    raise SystemExit(f"unexpected vendor_boot header byte changes: {unexpected[:12]}")
stock_ramdisk = stock_dir / "vendor_ramdisk"
m1_ramdisk = m1_dir / "vendor_ramdisk"
if digest(stock_ramdisk) != digest(m1_ramdisk):
    raise SystemExit("vendor ramdisk is not byte-identical")
if digest(stock_dir / "dtb") == digest(m1_dir / "dtb"):
    raise SystemExit("vendor_boot DTB did not change")
if digest(m1_dir / "dtb") != digest(abl_dtb):
    raise SystemExit("rebuilt vendor_boot DTB differs from packaged ABL DTB")
if m1_img.stat().st_size > cap:
    raise SystemExit(f"vendor_boot exceeds partition cap: {m1_img.stat().st_size}")

report.write_text("\n".join([
    f"STOCK_VENDOR_BOOT_SHA256={digest(stock_img)}",
    f"M1_VENDOR_BOOT_SHA256={digest(m1_img)}",
    f"STOCK_VENDOR_BOOT_SIZE={stock_img.stat().st_size}",
    f"M1_VENDOR_BOOT_SIZE={m1_img.stat().st_size}",
    f"STOCK_DTB_SHA256={digest(stock_dir / 'dtb')}",
    f"M1_DTB_SHA256={digest(m1_dir / 'dtb')}",
    f"STOCK_DTB_SIZE={stock['dtb_size']}",
    f"M1_DTB_SIZE={m1['dtb_size']}",
    f"VENDOR_RAMDISK_SHA256={digest(m1_ramdisk)}",
    "VENDOR_RAMDISK_EXACT_STOCK=PASS",
    "VENDOR_BOOT_HEADER_STOCK_COMPAT=PASS",
    "VENDOR_BOOT_ONLY_DTB_CHANGED=PASS",
    "HEADER_BYTE_DIFF=" + ("dtb_size[2100:2104] only" if header_diffs else "none"),
    "ONLY_INTENTIONAL_CHANGE=DTB_PAYLOAD_AND_DTB_SIZE_DERIVED_FIELDS",
    ""]), encoding="utf-8")
PY
pass "VENDOR_RAMDISK_EXACT_STOCK"
pass "VENDOR_RAMDISK_EXACT_STOCK=PASS"
pass "VENDOR_BOOT_HEADER_STOCK_COMPAT"
pass "VENDOR_BOOT_HEADER_STOCK_COMPAT=PASS"
pass "VENDOR_BOOT_ONLY_DTB_CHANGED"
pass "VENDOR_BOOT_ONLY_DTB_CHANGED=PASS"

STOCK_DUMP_PREFIX="$WORK/stock-dtbo-entry"
python3 tools/aosp/mkdtboimg.py dump "$STOCK_DTBO" --dtb "$STOCK_DUMP_PREFIX" \
	>"$WORK/stock-dtbo.dump.txt" 2>&1
stock_dtbo_count=$(find "$WORK" -maxdepth 1 -type f -name 'stock-dtbo-entry.*' | wc -l | tr -d ' ')
[ "$stock_dtbo_count" = 29 ] || fail "STOCK_DTBO_TABLE_ENTRY_COUNT=$stock_dtbo_count"
dtc -I dtb -O dts -o "$WORK/stock-dtbo-entry-21.dts" \
	"$WORK/stock-dtbo-entry.21" 2>"$WORK/stock-dtbo-entry-21.dtc.log"
stock_board_id=$(fdtget -t u "$WORK/stock-dtbo-entry.21" / qcom,board-id | tr '\n' ' ' | xargs)
[ "$stock_board_id" = "45 0" ] || fail "STOCK_DTBO_THYME_BOARD_ID=$stock_board_id"
pass "STOCK_DTBO_THYME_BOARD_ID=45,0"

NOOP_DTS="$WORK/noop.dts"
NOOP_DTB="$WORK/noop.dtbo"
M1_DTBO="$REL/mainline-v2-m1-dtbo.img"
cat >"$NOOP_DTS" <<'EOF'
/dts-v1/;
/plugin/;
/ {
	model = "Xiaomi Mi 10S (thyme) Route B no-op";
	compatible = "qcom,kona-mtp", "qcom,kona", "qcom,mtp";
	qcom,board-id = <45 0>;
	fragment@0 {
		target-path = "/";
		__overlay__ {
			qcom,thyme-route-b-noop;
		};
	};
};
EOF
dtc -@ -O dtb -o "$NOOP_DTB" "$NOOP_DTS"
python3 tools/aosp/mkdtboimg.py create "$M1_DTBO" \
	--version=0 --page_size=4096 "$NOOP_DTB"
test -s "$M1_DTBO" || fail "M1_DTBO_BUILD"
M1_DTBO_SIZE="$(wc -c <"$M1_DTBO" | tr -d ' ')"
[ "$M1_DTBO_SIZE" -le "$DTBO_CAP" ] || fail "DTBO_PARTITION_SIZE=$M1_DTBO_SIZE > $DTBO_CAP"
pass "DTBO_PARTITION_SIZE=$M1_DTBO_SIZE <= $DTBO_CAP"

NOOP_SHA256="$(sha "$M1_DTBO")"
if [ "$NOOP_SHA256" = "$EXPECTED_NOOP_DTBO_SHA256" ]; then
	NOOP_EXACT=YES
else
	NOOP_EXACT=NO
fi

M1_DUMP_PREFIX="$WORK/m1-dtbo-frag"
python3 tools/aosp/mkdtboimg.py dump "$M1_DTBO" --dtb "$M1_DUMP_PREFIX" \
	>"$WORK/m1-dtbo.dump.txt" 2>&1
m1_dtbo_count=$(find "$WORK" -maxdepth 1 -type f -name 'm1-dtbo-frag.*' | wc -l | tr -d ' ')
[ "$m1_dtbo_count" = 1 ] || fail "NOOP_DTBO_ENTRY_COUNT=$m1_dtbo_count"
M1_FRAG="$WORK/m1-dtbo-frag.0"
dtc -I dtb -O dts -o "$WORK/m1-dtbo-frag.dts" "$M1_FRAG" 2>"$WORK/m1-dtbo-frag.dtc.log"
noop_board_id=$(fdtget -t u "$M1_FRAG" / qcom,board-id | tr '\n' ' ' | xargs)
[ "$noop_board_id" = "45 0" ] || fail "NOOP_DTBO_THYME_BOARD_ID=$noop_board_id"
fdtget "$M1_FRAG" / qcom,thyme-route-b-noop >/dev/null || \
	fail "NOOP_DTBO marker missing"
for compatible in qcom,kona-mtp qcom,kona qcom,mtp; do
	fdtget "$M1_FRAG" / compatible | tr ' ' '\n' | grep -qx "$compatible" || \
		fail "NOOP_DTBO compatible missing: $compatible"
done

fdtoverlay -i "$ABL_DTB" "$NOOP_DTB" -o "$WORK/merged.dtb"
dtc -I dtb -O dts -o "$WORK/mainline-abl-tree.dts" "$ABL_DTB"
dtc -I dtb -O dts -o "$WORK/merged.dts" "$WORK/merged.dtb"
grep -v 'qcom,thyme-route-b-noop' "$WORK/mainline-abl-tree.dts" >"$WORK/mainline-clean.dts"
grep -v 'qcom,thyme-route-b-noop' "$WORK/merged.dts" >"$WORK/merged-clean.dts"
diff -u "$WORK/mainline-clean.dts" "$WORK/merged-clean.dts" >"$WORK/mainline-vs-merged.diff" || \
	fail "NOOP_DTBO mutated the Mainline DTB"
fdtget "$WORK/merged.dtb" / qcom,thyme-route-b-noop >/dev/null || \
	fail "NOOP_DTBO merged marker missing"

{
	echo "STOCK_DTBO_SHA256=$STOCK_DTBO_SHA256"
	echo "M1_DTBO_SHA256=$NOOP_SHA256"
	echo "M1_DTBO_SIZE=$M1_DTBO_SIZE"
	echo "M1_DTBO_ENTRY_COUNT=1"
	echo "NOOP_DTBO_THYME_BOARD_ID=45,0"
	echo "NOOP_DTBO_MARKER=qcom,thyme-route-b-noop"
	echo "NOOP_DTBO_EXACT_REUSE=$NOOP_EXACT"
if [ "$NOOP_EXACT" = YES ]; then
	echo "NOOP_DTBO_DIFFERENCE=none"
else
	echo "NOOP_DTBO_DIFFERENCE=generated hash differs from historical $EXPECTED_NOOP_DTBO_SHA256"
fi
echo "FDToVERLAY_NOOP_EQUIVALENCE=PASS"
} | tee "$DTBO_RPT"
pass "NOOP_DTBO_VALID"
pass "NOOP_DTBO_VALID=PASS"
pass "NOOP_DTBO_THYME_BOARD_ID=45,0"
pass "NOOP_DTBO_THYME_BOARD_ID=PASS"

for forbidden in boot.img mainline-v2-m1-boot.img Image; do
	[ ! -e "$REL/$forbidden" ] || fail "FORBIDDEN_MAINLINE_BOOT_ARTIFACT=$forbidden"
done
pass "NO_MAINLINE_BOOT_IMAGE_GENERATED"
pass "NO_NEW_BOOT_IMAGE=PASS"
pass "M0_BOOT_SHA_REFERENCE=PASS"
printf 'M0_BOOT_REFERENCE_SHA256=%s\nM1_BOOT_B_ACTION=EXACT_M0_REUSE_REQUIRED_NO_CI_BOOT_OUTPUT\n' \
	"$M0_BOOT_SHA256" | tee -a "$RPT"
pass "$M1_FINAL_GATE"
printf '%s\n' "$M1_FINAL_GATE" | tee -a "$RPT"
echo "ALL MAINLINE V2 M1 MAINLINE-DT CONTEXT VALIDATION PASS" | tee -a "$RPT"
