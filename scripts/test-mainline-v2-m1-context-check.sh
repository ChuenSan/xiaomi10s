#!/usr/bin/env bash
# Synthetic M1 context-domain tests. They are intentionally CI-only.
set -euo pipefail
set -o pipefail

if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo "CI only — refuse local verifier/fixture tests" >&2
	exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$ROOT/scripts/mainline-v2-m1-context-check.sh"
AUTHORITATIVE="$ROOT/scripts/mainline-v2-m1-context-metadata.env"
TEST_ROOT="${RUNNER_TEMP:-$ROOT/work}/mainline-v2-m1-context-${GITHUB_RUN_ID:-ci}-${GITHUB_RUN_ATTEMPT:-1}"
BASE_METADATA="$TEST_ROOT/synthetic-metadata.env"
WRONG_SHA_METADATA="$TEST_ROOT/wrong-sha-metadata.env"
MISSING_SIZE_METADATA="$TEST_ROOT/missing-size-metadata.env"
MISSING_SHA_METADATA="$TEST_ROOT/missing-sha-metadata.env"
HISTORICAL_WHOLE_METADATA="$TEST_ROOT/historical-whole-metadata.env"
mkdir -p "$TEST_ROOT"

fail_test() {
	echo "CONTEXT-TEST-FAIL: $*" >&2
	exit 1
}

assert_line() {
	local file="$1"
	local line="$2"
	grep -Fqx "$line" "$file" || fail_test "missing line in $file: $line"
}

run_pass() {
	local label="$1"
	local fixture="$2"
	local metadata="$3"
	shift 3
	local log="$TEST_ROOT/$label.log"
	if ! bash "$CHECKER" --fixture "$fixture" --metadata "$metadata" "$@" >"$log" 2>&1; then
		cat "$log"
		fail_test "$label expected PASS"
	fi
	cat "$log"
}

run_fail() {
	local label="$1"
	local fixture="$2"
	local metadata="$3"
	shift 3
	local log="$TEST_ROOT/$label.log"
	if bash "$CHECKER" --fixture "$fixture" --metadata "$metadata" "$@" >"$log" 2>&1; then
		cat "$log"
		fail_test "$label expected FAIL"
	fi
	cat "$log"
}

for line in \
	'M1_PRIVATE_CI_RUN="34338768052"' \
	'M1_ARTIFACT_SOURCE="M1 private CI run 34338768052"' \
	'M1_VENDOR_BOOT_ARTIFACT_SIZE="114688"' \
	'M1_VENDOR_BOOT_ARTIFACT_SHA256="29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5"' \
	'M1_DTBO_ARTIFACT_SIZE="387"' \
	'M1_DTBO_ARTIFACT_SHA256="316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1"'; do
	assert_line "$AUTHORITATIVE" "$line"
done
echo 'M1_CONTEXT_ARTIFACT_METADATA=PASS'

python3 - "$TEST_ROOT" "$BASE_METADATA" "$WRONG_SHA_METADATA" \
	"$MISSING_SIZE_METADATA" "$MISSING_SHA_METADATA" "$HISTORICAL_WHOLE_METADATA" <<'PY'
from hashlib import sha256
from pathlib import Path
import shutil
import sys

root, base_metadata, wrong_sha_metadata, missing_size_metadata, missing_sha_metadata, historical_whole_metadata = map(Path, sys.argv[1:])

vendor_size = 114688
dtbo_size = 387
vendor_prefix = bytes((index * 29 + 7) & 0xff for index in range(vendor_size))
dtbo_prefix = bytes((index * 47 + 11) & 0xff for index in range(dtbo_size))
vendor_tail = b"synthetic-vendor-tail\x00" + bytes(range(251))
dtbo_tail = b"synthetic-dtbo-tail\x00" + bytes(range(31))
vendor_partition = vendor_prefix + vendor_tail
dtbo_partition = dtbo_prefix + dtbo_tail
vendor_sha = sha256(vendor_prefix).hexdigest()
dtbo_sha = sha256(dtbo_prefix).hexdigest()

base = root / "case-base"
base.mkdir()
(base / "vendor_boot_b").write_bytes(vendor_partition)
(base / "dtbo_b").write_bytes(dtbo_partition)

for name in ("case-d-prefix-mismatch", "case-f-short-read", "case-g-wrong-sha", "case-h-historical-whole"):
    destination = root / name
    destination.mkdir()
    shutil.copyfile(base / "vendor_boot_b", destination / "vendor_boot_b")
    shutil.copyfile(base / "dtbo_b", destination / "dtbo_b")

bad_prefix = bytearray(vendor_partition)
bad_prefix[0] ^= 1
(root / "case-d-prefix-mismatch" / "vendor_boot_b").write_bytes(bad_prefix)

(root / "case-e-partition-short").mkdir()
(root / "case-e-partition-short" / "vendor_boot_b").write_bytes(vendor_prefix[:-1])
shutil.copyfile(base / "dtbo_b", root / "case-e-partition-short" / "dtbo_b")

bad_historical_prefix = bytearray(vendor_partition)
bad_historical_prefix[1] ^= 1
(root / "case-h-historical-whole" / "vendor_boot_b").write_bytes(bad_historical_prefix)
(root / "case-h-historical-whole" / "vendor_boot_b.whole.sha256").write_text(
    "3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614\n",
    encoding="ascii",
)
(root / "case-h-historical-whole" / "dtbo_b.whole.sha256").write_text(
    f"{dtbo_sha}\n",
    encoding="ascii",
)

metadata = f'''# Synthetic fixture metadata; not an OEM artifact.
M1_PRIVATE_CI_RUN="synthetic-fixture"
M1_ARTIFACT_SOURCE="synthetic CI fixture"
M1_VENDOR_BOOT_ARTIFACT_NAME="synthetic-vendor_boot.img"
M1_VENDOR_BOOT_ARTIFACT_SIZE="{vendor_size}"
M1_VENDOR_BOOT_ARTIFACT_SHA256="{vendor_sha}"
M1_DTBO_ARTIFACT_NAME="synthetic-dtbo.img"
M1_DTBO_ARTIFACT_SIZE="{dtbo_size}"
M1_DTBO_ARTIFACT_SHA256="{dtbo_sha}"
'''
base_metadata.write_text(metadata, encoding="ascii")
wrong_sha_metadata.write_text(metadata.replace(vendor_sha, "0" * 64), encoding="ascii")
historical_whole_metadata.write_text(metadata.replace(
    vendor_sha,
    "3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614",
), encoding="ascii")
missing_size_metadata.write_text(metadata.replace(
    f'M1_VENDOR_BOOT_ARTIFACT_SIZE="{vendor_size}"',
    'M1_VENDOR_BOOT_ARTIFACT_SIZE=""',
), encoding="ascii")
missing_sha_metadata.write_text(metadata.replace(
    f'M1_VENDOR_BOOT_ARTIFACT_SHA256="{vendor_sha}"',
    'M1_VENDOR_BOOT_ARTIFACT_SHA256=""',
), encoding="ascii")
PY

BASE_FIXTURE="$TEST_ROOT/case-base"
run_pass case-a-prefix-exact "$BASE_FIXTURE" "$BASE_METADATA"
assert_line "$TEST_ROOT/case-a-prefix-exact.log" 'DEVICE_VENDOR_BOOT_PREFIX_BYTES=114688'
assert_line "$TEST_ROOT/case-a-prefix-exact.log" 'M1_VENDOR_BOOT_PREFIX_MATCH=YES'
echo 'VENDOR_BOOT_PREFIX_DOMAIN=PASS'

run_pass case-b-nonaligned-387 "$BASE_FIXTURE" "$BASE_METADATA"
assert_line "$TEST_ROOT/case-b-nonaligned-387.log" 'DEVICE_DTBO_PREFIX_BYTES=387'
assert_line "$TEST_ROOT/case-b-nonaligned-387.log" 'M1_DTBO_PREFIX_MATCH=YES'
echo 'DTBO_PREFIX_DOMAIN=PASS'
echo 'NON_ALIGNED_387_BYTE_READ=PASS'
echo 'NON_BLOCK_ALIGNED_PREFIX_387=PASS'

run_pass case-c-whole-observation "$BASE_FIXTURE" "$BASE_METADATA"
C_LOG="$TEST_ROOT/case-c-whole-observation.log"
VENDOR_WHOLE="$(awk -F= '/^DEVICE_VENDOR_BOOT_WHOLE_SHA256=/{print $2}' "$C_LOG")"
DTBO_WHOLE="$(awk -F= '/^DEVICE_DTBO_WHOLE_SHA256=/{print $2}' "$C_LOG")"
VENDOR_ARTIFACT="$(awk -F= '/^M1_VENDOR_BOOT_ARTIFACT_SHA256=/{print $2}' "$C_LOG")"
DTBO_ARTIFACT="$(awk -F= '/^M1_DTBO_ARTIFACT_SHA256=/{print $2}' "$C_LOG")"
[ -n "$VENDOR_WHOLE" ] && [ "$VENDOR_WHOLE" != "$VENDOR_ARTIFACT" ] || \
	fail_test 'vendor whole hash unexpectedly became artifact identity'
[ -n "$DTBO_WHOLE" ] && [ "$DTBO_WHOLE" != "$DTBO_ARTIFACT" ] || \
	fail_test 'dtbo whole hash unexpectedly became artifact identity'
assert_line "$C_LOG" 'WHOLE_HASH_GATE=NO'
assert_line "$C_LOG" 'WHOLE_PARTITION_HASH_ROLE=OBSERVATION_ONLY'
echo 'TAIL_PRESERVATION_MODEL=PASS'
echo 'TAIL_BYTES_IGNORED_FOR_ARTIFACT_IDENTITY=PASS'
echo 'WHOLE_HASH_OBSERVATION_ONLY=PASS'
echo 'WHOLE_SHA_NOT_USED_AS_ARTIFACT_GATE=PASS'

auto_fail_reason() {
	local label="$1"
	local expected="$2"
	grep -Fq "$expected" "$TEST_ROOT/$label.log" || \
		fail_test "missing failure reason in $TEST_ROOT/$label.log: $expected"
}

run_fail case-d-prefix-mismatch "$TEST_ROOT/case-d-prefix-mismatch" "$BASE_METADATA"
auto_fail_reason case-d-prefix-mismatch 'M1_CONTEXT_FAILURE=vendor_boot_b prefix SHA mismatch: artifact='
echo 'PREFIX_MISMATCH_FAIL_CLOSED=PASS'

run_fail case-e-partition-short "$TEST_ROOT/case-e-partition-short" "$BASE_METADATA"
auto_fail_reason case-e-partition-short 'M1_CONTEXT_FAILURE=vendor_boot_b is smaller than artifact synthetic-vendor_boot.img: partition=114687 artifact=114688'
echo 'PARTITION_SHORT_FAIL_CLOSED=PASS'

run_fail case-f-short-read "$BASE_FIXTURE" "$BASE_METADATA" \
	--fixture-read-limit vendor_boot_b 114687
auto_fail_reason case-f-short-read 'M1_CONTEXT_FAILURE=vendor_boot_b prefix read was not exact: read=114687 artifact=114688'
echo 'EXACT_READ_FAIL_CLOSED=PASS'

run_fail case-g-wrong-sha "$TEST_ROOT/case-g-wrong-sha" "$WRONG_SHA_METADATA"
auto_fail_reason case-g-wrong-sha 'M1_CONTEXT_FAILURE=vendor_boot_b prefix SHA mismatch: artifact=0000000000000000000000000000000000000000000000000000000000000000 device='
echo 'WRONG_ARTIFACT_SHA_FAIL_CLOSED=PASS'

run_fail case-h-historical-whole "$TEST_ROOT/case-h-historical-whole" "$HISTORICAL_WHOLE_METADATA"
H_LOG="$TEST_ROOT/case-h-historical-whole.log"
assert_line "$TEST_ROOT/case-h-historical-whole/vendor_boot_b.whole.sha256" '3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614'
assert_line "$TEST_ROOT/case-h-historical-whole/dtbo_b.whole.sha256" "$(awk -F= '/^M1_DTBO_ARTIFACT_SHA256=/{print $2}' "$TEST_ROOT/case-b-nonaligned-387.log")"
auto_fail_reason case-h-historical-whole 'M1_CONTEXT_FAILURE=vendor_boot_b prefix SHA mismatch: artifact=3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614 device='
echo 'HISTORICAL_WHOLE_HASH_NOT_A_GATE=PASS'

run_fail case-i-missing-size "$BASE_FIXTURE" "$MISSING_SIZE_METADATA"
assert_line "$TEST_ROOT/case-i-missing-size.log" 'M1_CONTEXT_FAILURE=required artifact metadata missing: M1_VENDOR_BOOT_ARTIFACT_SIZE'
run_fail case-j-missing-sha "$BASE_FIXTURE" "$MISSING_SHA_METADATA"
assert_line "$TEST_ROOT/case-j-missing-sha.log" 'M1_CONTEXT_FAILURE=required artifact metadata missing: M1_VENDOR_BOOT_ARTIFACT_SHA256'
echo 'M1_ARTIFACT_METADATA_FAIL_CLOSED=PASS'

echo 'HASH_DOMAIN_PREFIX_NOT_WHOLE=PASS'
echo 'FAIL_CLOSED=PASS'
echo 'M1_CONTEXT_GATE_CI=PASS'
echo 'FINAL_GATE=READY_FOR_M3_CONTEXT_READONLY_RECHECK'
