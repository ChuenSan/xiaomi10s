#!/usr/bin/env bash
# Read-only M1 context check. Artifact identity is the first N artifact bytes.
# Whole-partition hashes are observations only and never gate a match.
set -euo pipefail
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METADATA_FILE="${M1_CONTEXT_METADATA_FILE:-$SCRIPT_DIR/mainline-v2-m1-context-metadata.env}"
MODE="device"
FIXTURE_DIR=""
FIXTURE_READ_LIMIT_PARTITION=""
FIXTURE_READ_LIMIT=""

fail() {
	printf 'M1_CONTEXT_GATE=FAIL\nM1_CONTEXT_FAILURE=%s\n' "$*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Usage:
  bash scripts/mainline-v2-m1-context-check.sh [--metadata FILE]
  bash scripts/mainline-v2-m1-context-check.sh --fixture DIR --metadata FILE

The default mode checks Android A through adb and performs no device writes.
--fixture is CI-only synthetic input. --fixture-read-limit is CI-only fault
injection for the exact-read negative test.
EOF
}

while [ "$#" -gt 0 ]; do
	case "$1" in
		--metadata)
			[ "$#" -ge 2 ] || fail "--metadata requires a file"
			METADATA_FILE="$2"
			shift 2
			;;
		--fixture)
			[ "$#" -ge 2 ] || fail "--fixture requires a directory"
			MODE="fixture"
			FIXTURE_DIR="$2"
			shift 2
			;;
		--fixture-read-limit)
			[ "$#" -ge 3 ] || fail "--fixture-read-limit requires PARTITION BYTES"
			[ "$MODE" = fixture ] || fail "--fixture-read-limit is fixture-only"
			FIXTURE_READ_LIMIT_PARTITION="$2"
			FIXTURE_READ_LIMIT="$3"
			shift 3
			;;
		--help|-h)
			usage
			exit 0
			;;
		*)
			fail "unknown argument: $1"
			;;
	esac
done

[ -r "$METADATA_FILE" ] || fail "artifact size/SHA metadata missing: $METADATA_FILE"
# The metadata file is repository-controlled and contains values only.
# shellcheck disable=SC1090
. "$METADATA_FILE"

require_metadata() {
	local name="$1"
	local value="${!name:-}"
	[ -n "$value" ] || fail "required artifact metadata missing: $name"
}

validate_size_metadata() {
	local name="$1"
	local value="${!name:-}"
	require_metadata "$name"
	case "$value" in
		*[!0-9]*) fail "artifact size metadata is not decimal: $name" ;;
	esac
	[ "$value" -gt 0 ] || fail "artifact size metadata is zero: $name"
}

validate_sha_metadata() {
	local name="$1"
	local value="${!name:-}"
	require_metadata "$name"
	case "$value" in
		*[!0123456789abcdefABCDEF]*) fail "artifact SHA metadata is not hex: $name" ;;
	esac
	[ "${#value}" -eq 64 ] || fail "artifact SHA metadata is not SHA256: $name"
}

require_metadata M1_PRIVATE_CI_RUN
require_metadata M1_ARTIFACT_SOURCE
require_metadata M1_VENDOR_BOOT_ARTIFACT_NAME
require_metadata M1_DTBO_ARTIFACT_NAME
validate_size_metadata M1_VENDOR_BOOT_ARTIFACT_SIZE
validate_sha_metadata M1_VENDOR_BOOT_ARTIFACT_SHA256
validate_size_metadata M1_DTBO_ARTIFACT_SIZE
validate_sha_metadata M1_DTBO_ARTIFACT_SHA256

validate_decimal_output() {
	awk '
	NF == 0 { next }
	NF != 1 || $1 !~ /^[0-9]+$/ { bad = 1; next }
	count++
	value = $1
	END {
		if (bad || count != 1)
			exit 1
		print value
	}'
}

validate_sha_output() {
	awk '
	NF == 0 { next }
	$1 !~ /^[0-9a-fA-F]+$/ || length($1) != 64 { bad = 1; next }
	count++
	value = tolower($1)
	END {
		if (bad || count != 1)
			exit 1
		print value
	}'
}

parse_decimal() {
	local raw="$1"
	printf '%s\n' "$raw" | validate_decimal_output
}

parse_sha() {
	local raw="$1"
	printf '%s\n' "$raw" | validate_sha_output
}

ADB="${ADB:-adb}"
adb_call() {
	if [ -n "${ADB_SERIAL:-}" ]; then
		"$ADB" -s "$ADB_SERIAL" "$@"
	else
		"$ADB" "$@"
	fi
}

adb_su() {
	local output
	if ! output="$(adb_call shell su -c "$1" 2>/dev/null)"; then
		return 1
	fi
	printf '%s\n' "$output" | tr -d '\r'
}

if [ "$MODE" = device ]; then
	ADB_DEVICES="$(adb_call devices 2>/dev/null)" || fail "adb device query failed"
	printf '%s\n' "$ADB_DEVICES" | awk '
		NR > 1 && $2 == "device" { found = 1 }
		END { exit(found ? 0 : 1) }
	' || fail "Android A device is not available through adb"

	ADB_SLOT="$(adb_su 'getprop ro.boot.slot_suffix')" || fail "cannot read ro.boot.slot_suffix"
	ADB_BOOT_COMPLETED="$(adb_su 'getprop sys.boot_completed')" || fail "cannot read sys.boot_completed"
	ROOT_ID="$(adb_su 'id')" || fail "cannot read root identity"
	[ "$ADB_SLOT" = _a ] || fail "Android slot is not _a: ${ADB_SLOT:-UNAVAILABLE}"
	[ "$ADB_BOOT_COMPLETED" = 1 ] || fail "Android A is not boot-complete: ${ADB_BOOT_COMPLETED:-UNAVAILABLE}"
	case "$ROOT_ID" in
		*uid=0*) ;;
		*) fail "root read access is unavailable: ${ROOT_ID:-UNAVAILABLE}" ;;
	esac

	printf '%s\n' 'CONTEXT_CHECK=MAINLINE_V2_M3_CONTEXT_GATE_HASH_DOMAIN_FIX'
	printf '%s\n' 'MODE=ANDROID_A_READ_ONLY'
	printf '%s\n' 'DEVICE_WRITES=NO'
	printf 'slot_suffix=%s\nboot_completed=%s\nROOT_ID=%s\n' \
		"$ADB_SLOT" "$ADB_BOOT_COMPLETED" "$ROOT_ID"
else
	[ -d "$FIXTURE_DIR" ] || fail "synthetic fixture directory missing: $FIXTURE_DIR"
	[ -z "${ADB_SERIAL:-}" ] || fail "ADB_SERIAL is not used in fixture mode"
	printf '%s\n' 'CONTEXT_CHECK=MAINLINE_V2_M3_CONTEXT_GATE_HASH_DOMAIN_FIX'
	printf '%s\n' 'MODE=SYNTHETIC_FIXTURE'
	printf '%s\n' 'DEVICE_WRITES=NO'
	printf '%s\n' 'SYNTHETIC_FIXTURE=YES'
fi

printf 'M1_PRIVATE_CI_RUN=%s\nM1_ARTIFACT_SOURCE=%s\n' \
	"$M1_PRIVATE_CI_RUN" "$M1_ARTIFACT_SOURCE"
printf 'M1_VENDOR_BOOT_ARTIFACT_FILE=%s\nM1_VENDOR_BOOT_ARTIFACT_SIZE=%s\nM1_VENDOR_BOOT_ARTIFACT_SHA256=%s\n' \
	"$M1_VENDOR_BOOT_ARTIFACT_NAME" \
	"$M1_VENDOR_BOOT_ARTIFACT_SIZE" \
	"$(printf '%s' "$M1_VENDOR_BOOT_ARTIFACT_SHA256" | tr '[:upper:]' '[:lower:]')"
printf 'M1_DTBO_ARTIFACT_FILE=%s\nM1_DTBO_ARTIFACT_SIZE=%s\nM1_DTBO_ARTIFACT_SHA256=%s\n' \
	"$M1_DTBO_ARTIFACT_NAME" \
	"$M1_DTBO_ARTIFACT_SIZE" \
	"$(printf '%s' "$M1_DTBO_ARTIFACT_SHA256" | tr '[:upper:]' '[:lower:]')"

fixture_measure() {
	local path="$1"
	local read_limit="$2"
	python3 - "$path" "$read_limit" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

path = Path(sys.argv[1])
read_limit = int(sys.argv[2])
with path.open("rb") as source:
    data = source.read(read_limit)
print(len(data))
print(sha256(data).hexdigest())
PY
}

fixture_whole_sha() {
	local path="$1"
	local override="${path}.whole.sha256"
	local raw
	if [ -f "$override" ]; then
		raw="$(tr -d '[:space:]' < "$override")"
	else
		raw="$(sha256sum "$path")"
	fi
	parse_sha "$raw"
}

verify_partition() {
	local label="$1"
	local partition="$2"
	local artifact_size="$3"
	local artifact_sha="$4"
	local artifact_name="$5"
	local device_path="/dev/block/by-name/$partition"
	local path partition_size prefix_count prefix_raw prefix_sha whole_sha whole_raw
	local read_limit="$artifact_size"

	case "$partition" in
		*[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-]*)
			fail "invalid partition name: $partition"
			;;
	esac

	if [ "$MODE" = fixture ]; then
		path="$FIXTURE_DIR/$partition"
		[ -f "$path" ] || fail "fixture partition missing: $path"
		if ! partition_size="$(wc -c < "$path" | tr -d '[:space:]' | parse_decimal)"; then
			fail "cannot query fixture partition size: $partition"
		fi
		if [ "$FIXTURE_READ_LIMIT_PARTITION" = "$partition" ]; then
			read_limit="$FIXTURE_READ_LIMIT"
		fi
		case "$read_limit" in
			*[!0-9]*) fail "fixture read limit is not decimal: $read_limit" ;;
		esac
		if ! prefix_raw="$(fixture_measure "$path" "$read_limit")"; then
			fail "fixture prefix read failed: $partition"
		fi
		if ! prefix_count="$(printf '%s\n' "$prefix_raw" | sed -n '1p' | parse_decimal)"; then
			fail "fixture prefix byte count is invalid: $partition"
		fi
		if ! prefix_sha="$(printf '%s\n' "$prefix_raw" | sed -n '2p' | parse_sha)"; then
			fail "fixture prefix SHA is invalid: $partition"
		fi
	else
		path="$device_path"
		if ! partition_raw="$(adb_su "blockdev --getsize64 '$device_path'")"; then
			fail "cannot query partition size: $partition"
		fi
		if ! partition_size="$(parse_decimal "$partition_raw")"; then
			fail "partition size query is invalid: $partition"
		fi
		if ! prefix_raw="$(adb_su "dd if='$device_path' bs=1 count=$artifact_size 2>/dev/null | wc -c")"; then
			fail "prefix byte-count read failed: $partition"
		fi
		if ! prefix_count="$(parse_decimal "$prefix_raw")"; then
			fail "prefix byte-count output is invalid: $partition"
		fi
		if ! prefix_raw="$(adb_su "set -o pipefail; dd if='$device_path' bs=1 count=$artifact_size 2>/dev/null | sha256sum")"; then
			fail "prefix SHA read failed: $partition"
		fi
		if ! prefix_sha="$(parse_sha "$prefix_raw")"; then
			fail "prefix SHA output is invalid: $partition"
		fi
	fi

	printf 'DEVICE_%s_PARTITION_SIZE=%s\n' "$label" "$partition_size"
	printf 'DEVICE_%s_PREFIX_BYTES=%s\n' "$label" "$prefix_count"
	[ "$partition_size" -ge "$artifact_size" ] || \
		fail "$partition is smaller than artifact $artifact_name: partition=$partition_size artifact=$artifact_size"
	[ "$prefix_count" = "$artifact_size" ] || \
		fail "$partition prefix read was not exact: read=$prefix_count artifact=$artifact_size"
	printf 'DEVICE_%s_PREFIX_SHA=%s\nDEVICE_%s_PREFIX_SHA256=%s\n' \
		"$label" "$prefix_sha" "$label" "$prefix_sha"
	[ "$prefix_sha" = "$(printf '%s' "$artifact_sha" | tr '[:upper:]' '[:lower:]')" ] || \
		fail "$partition prefix SHA mismatch: artifact=$artifact_sha device=$prefix_sha"
	printf 'M1_%s_PREFIX_MATCH=YES\nM1_%s_CONTEXT_MATCH=YES\n' "$label" "$label"

	if [ "$MODE" = fixture ]; then
		if ! whole_sha="$(fixture_whole_sha "$path")"; then
			fail "fixture whole SHA observation is invalid: $partition"
		fi
	else
		whole_sha="UNAVAILABLE"
		if whole_raw="$(adb_su "sha256sum '$device_path'")"; then
			if parsed_whole="$(parse_sha "$whole_raw")"; then
				whole_sha="$parsed_whole"
			fi
		fi
	fi
	printf 'DEVICE_%s_WHOLE_SHA256=%s\nWHOLE_%s_SHA256=%s\n' \
		"$label" "$whole_sha" "$label" "$whole_sha"
	printf 'WHOLE_%s_HASH_GATE=NO\nWHOLE_%s_HASH_ROLE=OBSERVATION_ONLY\n' "$label" "$label"
}

verify_partition VENDOR_BOOT vendor_boot_b \
	"$M1_VENDOR_BOOT_ARTIFACT_SIZE" \
	"$M1_VENDOR_BOOT_ARTIFACT_SHA256" \
	"$M1_VENDOR_BOOT_ARTIFACT_NAME"
verify_partition DTBO dtbo_b \
	"$M1_DTBO_ARTIFACT_SIZE" \
	"$M1_DTBO_ARTIFACT_SHA256" \
	"$M1_DTBO_ARTIFACT_NAME"

printf '%s\n' 'M1_CONTEXT_PAYLOAD_MATCH=YES'
printf '%s\n' 'WHOLE_PARTITION_HASH_ROLE=OBSERVATION_ONLY'
printf '%s\n' 'WHOLE_HASH_GATE=NO'
printf '%s\n' 'HASH_DOMAIN_PREFIX_NOT_WHOLE=PASS'
printf '%s\n' 'M1_CONTEXT_GATE=PASS'
