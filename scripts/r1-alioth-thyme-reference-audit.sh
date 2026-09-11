#!/usr/bin/env bash
# GHA-only R1 reference dump. No local DTB/Image validation.
set -euo pipefail

if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local reference dump/decompile" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/r1-reference-pins.env"

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; exit 1; }

fdt_prop() {
	local dtb="$1" path="$2" name="$3" type="${4:-}"
	if [ -n "$type" ]; then
		if fdtget -t "$type" "$dtb" "$path" "$name" >/dev/null 2>&1; then
			fdtget -t "$type" "$dtb" "$path" "$name" | tr '\n' ' ' | xargs
			return
		fi
	elif fdtget "$dtb" "$path" "$name" >/dev/null 2>&1; then
		fdtget "$dtb" "$path" "$name" | tr '\n' ' ' | xargs
		return
	fi
	printf 'NONE'
}

dump_dtb_root() {
	local dtb="$1" report="$2" label="$3"
	local dts="${report%.txt}.dts"
	{
		echo "LABEL=$label"
		echo "DTB_PATH=$dtb"
		echo "DTB_SIZE=$(wc -c <"$dtb" | tr -d ' ')"
		echo "DTB_SHA256=$(sha256sum "$dtb" | awk '{print $1}')"
		echo "MODEL=$(fdt_prop "$dtb" / model)"
		echo "COMPATIBLE=$(fdt_prop "$dtb" / compatible)"
		echo "MSM_ID=$(fdt_prop "$dtb" / qcom,msm-id u)"
		echo "BOARD_ID=$(fdt_prop "$dtb" / qcom,board-id u)"
		echo "PMIC_ID=$(fdt_prop "$dtb" / qcom,pmic-id)"
		echo "CHOSEN_STDOUT=$(fdt_prop "$dtb" /chosen stdout-path)"
		echo "CHOSEN_BOOTARGS=$(fdt_prop "$dtb" /chosen bootargs)"
		echo "ALIAS_SERIAL0=$(fdt_prop "$dtb" /aliases serial0)"
		echo "ROOT_PROPS=$(fdtget -p "$dtb" / 2>/dev/null | tr '\n' ' ' | xargs || true)"
		echo "ROOT_NODES=$(fdtget -l "$dtb" / 2>/dev/null | tr '\n' ' ' | xargs || true)"
		if fdtget -l "$dtb" /reserved-memory >/dev/null 2>&1; then
			echo "RESERVED_MEMORY_NODES=$(fdtget -l "$dtb" /reserved-memory | tr '\n' ' ' | xargs)"
		else
			echo "RESERVED_MEMORY_NODES=NONE"
		fi
		if fdtget -p "$dtb" /memory >/dev/null 2>&1; then
			echo "MEMORY_NODE=PRESENT"
			echo "MEMORY_REG=$(fdt_prop "$dtb" /memory reg x)"
		else
			echo "MEMORY_NODE=ABSENT"
		fi
	} | tee "$report"
	dtc -I dtb -O dts -o "$dts" "$dtb" 2>"${report%.txt}.dtc.log" || \
		fail "DTC_DECOMPILE $label"
	pass "DTC_DECOMPILE $label $(wc -l <"$dts" | tr -d ' ') lines"
}

dump_dtbo() {
	local img="$1" work="$2" report="$3"
	python3 "$ROOT/tools/aosp/mkdtboimg.py" dump "$img" --dtb "$work/dtbo-frag" \
		>"$work/dtbo.dump.txt"
	local n
	n="$(find "$work" -maxdepth 1 -type f -name 'dtbo-frag.*' | wc -l | tr -d ' ')"
	local frag="$work/dtbo-frag.0"
	[ -s "$frag" ] || fail "DTBO_FRAGMENT_MISSING"
	dtc -I dtb -O dts -o "$work/dtbo-frag.dts" "$frag" 2>"$work/dtbo-frag.dtc.log"
	{
		echo "DTBO_SIZE=$(wc -c <"$img" | tr -d ' ')"
		echo "DTBO_SHA256=$(sha256sum "$img" | awk '{print $1}')"
		echo "DTBO_ENTRY_COUNT=$n"
		echo "MODEL=$(fdt_prop "$frag" / model)"
		echo "COMPATIBLE=$(fdt_prop "$frag" / compatible)"
		echo "MSM_ID=$(fdt_prop "$frag" / qcom,msm-id u)"
		echo "BOARD_ID=$(fdt_prop "$frag" / qcom,board-id u)"
		echo "ROOT_PROPS=$(fdtget -p "$frag" / 2>/dev/null | tr '\n' ' ' | xargs || true)"
		echo "ROOT_NODES=$(fdtget -l "$frag" / 2>/dev/null | tr '\n' ' ' | xargs || true)"
		echo "HAS_PLUGIN_MARKER=$(grep -c '/plugin/' "$work/dtbo-frag.dts" || true)"
		echo "HAS_FRAGMENT=$(grep -c 'fragment@' "$work/dtbo-frag.dts" || true)"
		echo "TARGET_PATH=$(grep -E 'target-path|target =' "$work/dtbo-frag.dts" | tr '\n' ' ' | xargs || true)"
		echo "NOOP_MARKER=$(grep -c 'qcom,thyme-route-b-noop' "$work/dtbo-frag.dts" || true)"
		echo "FIXUPS=$(grep -c '__fixups__\|__local_fixups__\|__symbols__' "$work/dtbo-frag.dts" || true)"
	} | tee "$report"
}

cmd="${1:?mode}"
case "$cmd" in
source-pins)
	grep -Fq "$ALIOTH_HEAD" "$ROOT/scripts/r1-reference-pins.env"
	grep -Fq "$ASTIDE_HEAD" "$ROOT/scripts/r1-reference-pins.env"
	grep -Fq "$M1_VENDOR_BOOT_SHA256" "$ROOT/scripts/r1-reference-pins.env"
	grep -Fq "$M1_DTBO_SHA256" "$ROOT/scripts/r1-reference-pins.env"
	grep -Fq 'GITHUB_ACTIONS' "$ROOT/scripts/r1-alioth-thyme-reference-audit.sh"
	grep -Fq 'GITHUB_ACTIONS' "$ROOT/scripts/r1-parse-arm64-image-header.py"
	if git -C "$ROOT" ls-files | grep -E '(^|/)refs/'; then
		fail "REFERENCE_REPO_TRACKED"
	fi
	pass "R1_SOURCE_PINS"
	echo "EXACT_M1_VENDOR_BOOT_DUMP=PRIVATE_CI_REQUIRED"
	echo "EXACT_M1_DTBO_RECONSTRUCT=PUBLIC_GHA"
	echo "ALIOTH_IMAGE_DTB_BUILD=GHA_DISPATCH"
	;;
dump-image)
	img="${2:?Image}"
	out="${3:?report}"
	python3 "$ROOT/scripts/r1-parse-arm64-image-header.py" "$img" "$out"
	echo "IMAGE_SHA256=$(sha256sum "$img" | awk '{print $1}')" | tee -a "$out"
	pass "IMAGE_HEADER $out"
	;;
dump-dtb)
	dump_dtb_root "${2:?dtb}" "${3:?report}" "${4:?label}"
	;;
reconstruct-thyme-m1-dt)
	linux="${2:?linux dir}"
	out="${3:?out dir}"
	mkdir -p "$out"
	raw="$linux/out/arch/arm64/boot/dts/qcom/sm8250-xiaomi-thyme.dtb"
	[ -s "$raw" ] || fail "THYME_DTB_MISSING $raw"
	cp "$raw" "$out/mainline-thyme.dtb"
	dump_dtb_root "$out/mainline-thyme.dtb" "$out/thyme-raw-dtb.txt" thyme-raw
	abl="$out/mainline-thyme-abl.dtb"
	cp "$out/mainline-thyme.dtb" "$abl"
	added=NO
	if [ "$(fdt_prop "$abl" / qcom,msm-id u)" = NONE ]; then
		fdtput -t u "$abl" / qcom,msm-id "$QCOM_ID_SM8250" "$MSM_ID_REV"
		added=YES
	fi
	if [ "$(fdt_prop "$abl" / qcom,board-id u)" = NONE ]; then
		fdtput -t u "$abl" / qcom,board-id "$THYME_BOARD_ID_0" "$THYME_BOARD_ID_1"
		added=YES
	fi
	dump_dtb_root "$abl" "$out/thyme-abl-dtb.txt" thyme-abl
	echo "ABL_PACKAGING_METADATA_ADDED=$added" | tee -a "$out/thyme-abl-dtb.txt"
	raw_sha="$(sha256sum "$out/mainline-thyme.dtb" | awk '{print $1}')"
	abl_sha="$(sha256sum "$abl" | awk '{print $1}')"
	{
		echo "RAW_DTB_SHA256=$raw_sha"
		echo "EXPECTED_RAW_DTB_SHA256=$M1_RAW_DTB_SHA256"
		echo "RAW_DTB_SHA_MATCH=$([ "$raw_sha" = "$M1_RAW_DTB_SHA256" ] && echo YES || echo NO)"
		echo "ABL_DTB_SHA256=$abl_sha"
		echo "EXPECTED_ABL_DTB_SHA256=$M1_ABL_DTB_SHA256"
		echo "ABL_DTB_SHA_MATCH=$([ "$abl_sha" = "$M1_ABL_DTB_SHA256" ] && echo YES || echo NO)"
		echo "EXACT_M1_VENDOR_BOOT_UNPACK=PRIVATE_CI_REQUIRED"
	} | tee "$out/thyme-dtb-sha.txt"
	noop_dts="$out/noop.dts"
	cat >"$noop_dts" <<'EOF'
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
	dtc -@ -O dtb -o "$out/noop.dtbo" "$noop_dts"
	python3 "$ROOT/tools/aosp/mkdtboimg.py" create "$out/mainline-v2-m1-dtbo.img" \
		--version=0 --page_size=4096 "$out/noop.dtbo"
	dump_dtbo "$out/mainline-v2-m1-dtbo.img" "$out" "$out/thyme-dtbo.txt"
	dtbo_sha="$(sha256sum "$out/mainline-v2-m1-dtbo.img" | awk '{print $1}')"
	{
		echo "RECONSTRUCTED_DTBO_SHA256=$dtbo_sha"
		echo "EXPECTED_M1_DTBO_SHA256=$M1_DTBO_SHA256"
		echo "DTBO_SHA_MATCH=$([ "$dtbo_sha" = "$M1_DTBO_SHA256" ] && echo YES || echo NO)"
	} | tee -a "$out/thyme-dtbo.txt"
	pass "THYME_M1_DT_RECONSTRUCT"
	;;
*)
	fail "unknown mode $cmd"
	;;
esac
