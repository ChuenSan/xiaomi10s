# Mainline V2 M1 context hash-domain audit

Stage: `MAINLINE_V2_M3_CONTEXT_GATE_HASH_DOMAIN_FIX`

This change is limited to the Android A read-only M1 context verifier and its
GitHub Actions synthetic tests. It does not change the kernel, M3 patch or
artifact, DTS/DTBO contents, or device partitions. No M1 OEM-derived binary is
stored in the public repository.

## Historical failure and correction

The original M3 read-only preflight was stopped as:

```text
MAINLINE_V2_M3_NOT_SAFE
```

Its comparison incorrectly used a whole physical partition SHA256 as though
it were the SHA256 of the smaller M1 artifact file. The audit classified the
result as:

```text
M1_CONTEXT_INTACT_HASH_DOMAIN_MISMATCH
REAL_M1_CONTEXT_DRIFT=NO
M1_CONTEXT_PAYLOAD_MATCH=YES
M3_PREFLIGHT_HASH_DOMAIN_BUG=YES
M3_EXPECTED_HASH_BUG=NO
```

The corrected identity rule is:

1. `ARTIFACT_SIZE` and `ARTIFACT_SHA256` identify the M1 artifact file.
2. The device verifier reads exactly the first `ARTIFACT_SIZE` bytes of the
   corresponding partition and computes `DEVICE_PREFIX_SHA256`.
3. Only `DEVICE_PREFIX_SHA256 == ARTIFACT_SHA256` can produce a context match.
4. `WHOLE_PARTITION_SHA256` may be recorded as observational metadata only;
   it is never compared with the artifact SHA and never gates PASS/FAIL.

## Authoritative M1 artifact metadata

Source: private CI run `34338768052`.

| Artifact | `ARTIFACT_SIZE` | `ARTIFACT_SHA256` |
|---|---:|---|
| `mainline-v2-m1-vendor_boot.img` | `114688` | `29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5` |
| `mainline-v2-m1-dtbo.img` | `387` | `316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1` |

The values are kept as metadata only in:

```text
scripts/mainline-v2-m1-context-metadata.env
```

## Read-only verifier

The device entry point is:

```text
scripts/mainline-v2-m1-context-check.sh
```

It requires Android A (`ro.boot.slot_suffix=_a`, `sys.boot_completed=1`, and
root read access), queries the block-device size, verifies the exact prefix
byte count, hashes that prefix, then records the optional whole-partition
hash. Its device path uses only `adb shell su -c` read operations:

```text
blockdev --getsize64 /dev/block/by-name/<partition>
dd if=/dev/block/by-name/<partition> bs=1 count=<ARTIFACT_SIZE> | wc -c
dd if=/dev/block/by-name/<partition> bs=1 count=<ARTIFACT_SIZE> | sha256sum
sha256sum /dev/block/by-name/<partition>       # observation only
```

`bs=1` and the byte-count check are intentional: `dtbo_b` uses the odd,
non-block-aligned size `387`, not a rounded 512- or 4096-byte read. Missing
metadata, a short partition, a short prefix read, or a prefix mismatch fails
closed. There is no whole-hash fallback.

The fixture mode is CI-only and does not contact a device. It exists only to
exercise the same domain decision with synthetic bytes; it accepts an explicit
short-read fault and an observation-only whole-hash sidecar for negative tests.

## GitHub Actions tests

Workflow:

```text
.github/workflows/thyme-mainline-v2-m1-context-gate.yml
```

Test script:

```text
scripts/test-mainline-v2-m1-context-check.sh
```

The synthetic suite covers:

| Case | Condition | Result |
|---|---|---|
| A | `114688`-byte exact vendor prefix, different tail | PASS |
| B | `387`-byte exact DTBO prefix, different tail | PASS |
| C | whole SHA differs from artifact SHA, prefix exact | PASS |
| D | one prefix byte differs | FAIL |
| E | partition shorter than artifact | FAIL |
| F | returned prefix length is not exact | FAIL |
| G | artifact SHA metadata is wrong | FAIL |
| H | historical whole SHA is observed but prefix is wrong | FAIL |

The suite also checks missing size/SHA metadata and emits these regression
gates:

```text
HASH_DOMAIN_PREFIX_NOT_WHOLE=PASS
NON_BLOCK_ALIGNED_PREFIX_387=PASS
TAIL_BYTES_IGNORED_FOR_ARTIFACT_IDENTITY=PASS
PREFIX_MISMATCH_FAIL_CLOSED=PASS
WHOLE_SHA_NOT_USED_AS_ARTIFACT_GATE=PASS
```

GHA result for commit `81ae2b268688133795463441446f5e19815402fc`:

```text
CI_RUN=34442084099
CI_RESULT=success
M1_CONTEXT_ARTIFACT_METADATA=PASS
VENDOR_BOOT_PREFIX_DOMAIN=PASS
DTBO_PREFIX_DOMAIN=PASS
NON_ALIGNED_387_BYTE_READ=PASS
TAIL_PRESERVATION_MODEL=PASS
WHOLE_HASH_OBSERVATION_ONLY=PASS
FAIL_CLOSED=PASS
HASH_DOMAIN_PREFIX_NOT_WHOLE=PASS
NON_BLOCK_ALIGNED_PREFIX_387=PASS
TAIL_BYTES_IGNORED_FOR_ARTIFACT_IDENTITY=PASS
PREFIX_MISMATCH_FAIL_CLOSED=PASS
WHOLE_SHA_NOT_USED_AS_ARTIFACT_GATE=PASS
READY_FOR_M3_CONTEXT_READONLY_RECHECK
```

## Frozen device observations

The prior read-only audit already established the following and is not
repeated as a whole-partition identity comparison:

```text
vendor_boot_b partition size: 100663296
vendor_boot_b prefix N:       114688
vendor_boot_b prefix SHA256:  29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
vendor_boot_b whole SHA256:   3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614

 dtbo_b partition size:        33554432
 dtbo_b prefix N:              387
 dtbo_b prefix SHA256:         316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
 dtbo_b whole SHA256:          b8127f44ea27080ea2852dc806a58dd5c3ae47616a6c0d50bfe83b3972fd001a
```

Corrected Android A read-only recheck at `2026-09-10T05:44:42Z`:

```text
slot_suffix=_a
boot_completed=1

vendor_boot_b partition size=100663296
vendor_boot_b prefix N=114688
vendor_boot_b prefix SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
vendor_boot_b whole SHA256=3fd702b13ae87cd6e53c1fb8ae8ae053f300de5f7a3da760dd42f568a91b9614
M1_VENDOR_BOOT_PREFIX_MATCH=YES

dtbo_b partition size=33554432
dtbo_b prefix N=387
dtbo_b prefix SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
dtbo_b whole SHA256=b8127f44ea27080ea2852dc806a58dd5c3ae47616a6c0d50bfe83b3972fd001a
M1_DTBO_PREFIX_MATCH=YES

WHOLE_HASH_GATE=NO
vbmeta_b=stock
vbmeta_system_b=stock
firmware_prefixes=xbl_b,abl_b,tz_b MATCH_STOCK
M3_BOOT_SHA256=80afd2859333ea47d3aaa1fbdf6ec8cc678e65510de96c8f3671baad99d1a7ff
M3_BOOT_ARTIFACT_MATCH=YES
M3_CONTEXT_PREFLIGHT_SAFE=YES
M3_CONTEXT_GATE_FIXED_AND_READONLY_PASS
```

The firmware prefix observation covered `xbl_b` (`3575808` bytes), `abl_b`
(`208896` bytes), and `tz_b` (`3190784` bytes); each matched the known stock
image prefix. No full firmware re-audit was performed.

## Current safety boundary

Until the Actions gate passes and the corrected Android A check is completed,
the only allowed activity is read-only verification. This round performs no
Fastboot operation, no slot mutation, no B boot, and no partition write. The
only possible next action after a complete PASS is a separately approved M3
true-device `boot_b`-only test.
