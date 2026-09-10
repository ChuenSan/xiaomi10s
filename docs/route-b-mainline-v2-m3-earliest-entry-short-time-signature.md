# Route B Mainline V2 M3 — earliest-entry short time signature

Status: CI gate passed; no M3 device boot has been performed.
M3 is a single-purpose Slot B experiment. It changes only the `boot_b` kernel
payload and does not change the M1 DT context, ramdisk, vbmeta, firmware, or
Slot A.

## Frozen result context

| Item | Recorded value |
|---|---|
| device | Xiaomi Mi 10S (`thyme` / SM8250) |
| Linux | 6.6.156 |
| Linux base | `8b73de7da85fde281a385e0b26eda9bffd3ca477` |
| M1 elapsed | `4.821s` |
| M2 elapsed | `4.598s` |
| baseline mean | `4.710s` |
| M2 20-second signature | not observed |
| M2 final gate | `MAINLINE_V2_M2_CHECKPOINT_NOT_REACHED` |
| M2 interpretation | `CHECKPOINT_EXECUTION_STRICTLY_REFUTED=NO` |
| local build/validation | prohibited |
| CI build/validation | GitHub Actions only |
| Slot A | permanently protected |

M2's approximately 4–5 second return is retained as historical evidence. It
cannot by itself prove that ABL did not enter Mainline: an external firmware,
bootloader, or hardware watchdog could reset the device before a 20-second
busy-wait completed.

The project constraints and latest M1/M2 results were read from mem0 before
this implementation:

```text
MEM0_READ_BEFORE_IMPLEMENTATION=YES
MEM0_CONSTRAINTS_ACKNOWLEDGED=PASS
```

## M3 checkpoint and patch

The pinned `arch/arm64/kernel/head.S` primary path is:

```text
primary_entry
  -> record_mmu_state
  -> preserve_boot_args
  -> M3 checkpoint
  -> create_idmap
  -> init_kernel_el
  -> __cpu_setup
```

The experimental patch is:

```text
patches/experiments/mainline-v2-m3-earliest-entry-short-delay.patch
```

The exact M3 checkpoint is the block in `primary_entry` immediately after the
return from `preserve_boot_args` and immediately before `create_idmap`. This is
strictly earlier than the historical M2 block, which was after `init_kernel_el`
and `mov x20, x0`, before `__cpu_setup`.

The CI report for run `34432765989` emits:

```text
M2_CHECKPOINT_FILE=arch/arm64/kernel/head.S
M2_CHECKPOINT_SYMBOL=primary_entry
M2_CHECKPOINT_OFFSET=byte:3652,line:126
M3_CHECKPOINT_FILE=arch/arm64/kernel/head.S
M3_CHECKPOINT_SYMBOL=primary_entry
M3_CHECKPOINT_OFFSET=byte:2920,line:93
M3_EARLIER_THAN_M2=YES
M3_POSITION_BEFORE_M2=YES
```

M3 uses exactly:

```text
counter: CNTFRQ_EL0 + CNTPCT_EL0
delay: 2 seconds
scratch: x0, x1, x2, x3
saved FDT: x21
calls in delay block: none
system-register writes in delay block: none
```

`preserve_boot_args` has already stored the original `x0`–`x3` values and the
FDT pointer in `x21`. The delay therefore leaves the primary boot state,
SCTLR state, and saved DTB pointer untouched.

## Timer access audit

The M3 location is before `init_kernel_el`, so the source audit must not reuse
M2's post-`init_kernel_el` assumption. The CI validator rechecks the exact
pinned source and requires all of the following:

1. Linux booting requirements permit entry at EL2 or EL1.
2. `CNTFRQ` is initialized by the bootloader.
3. When entering at EL1, `CNTHCTL_EL2.EL1PCTEN` is set where available.
4. The existing arm64 accessor uses the ordered `CNTPCT_EL0` read.
5. The M3 block has no call, system-register write, or register outside
   `x0`–`x3`.

The audit basis is the pinned `Documentation/arch/arm64/booting.rst`,
`arch/arm64/include/asm/arch_timer.h`, and
`arch/arm64/include/asm/el2_setup.h`. This is a boot-protocol/source audit,
not a claim that an uncooperative firmware cannot trap the access. If the
exact source audit cannot establish the required access contract, the CI gate
must stop as `M3_EARLY_TIMER_NOT_SAFE`; no device artifact may be used.

Required report fields:

```text
COUNTER_SOURCE=CNTFRQ_EL0+CNTPCT_EL0
EARLY_TIMER_AUDIT_BASIS=arm64 boot protocol EL2-or-EL1 and EL1PCTEN
EARLY_TIMER_ACCESS_AUDITED=PASS
M3_SCRATCH_REGISTERS=x0,x1,x2,x3
BOOT_ARGS_PRESERVED=YES
SAVED_DTB_POINTER=x21
```

## GitHub Actions pipeline

Workflow:

```text
.github/workflows/thyme-mainline-v2-m3-earliest-entry-short-delay.yml
```

Validator:

```text
scripts/mainline-v2-m3-ci-validate.sh
```

The workflow is the only place where checkout, patch application, kernel
compilation, disassembly, boot-image packing, reverse unpacking, and image
validation are run. It downloads these immutable references:

```text
M0 Actions run: 34322563307
M0 Image SHA256: 22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6
M0 /init SHA256: aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8
M0 ramdisk SHA256: b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de

M2 Actions run: 34360812930
M2 Image SHA256: 4b37a48819730d3fae43f8eeff9d2a6c8fbaa9f28432819d52cce8407f6826b4
```

The M2 validation report is checked for the same M0 initramfs and `/init`
hashes. M3 then reuses the M0 files directly and verifies:

```text
M0_M1_M2_RAMDISK_EXACT_REUSE=PASS
RAMDISK_SHA_EXACT_REUSE=PASS
INIT_BINARY_EXACT_REUSE=PASS
```

The M3 artifact is limited to:

```text
mainline-v2-m3-early-short-delay-boot-v3.img
Image
mainline-v2-m3-earliest-entry-short-delay.patch
SHA256SUMS
validation-report.txt
reverse-unpack-report/
```

No `vendor_boot`, `dtbo`, `vbmeta`, or firmware artifact is emitted. The
instrumentation is CI-only:

```text
EXPERIMENTAL_INSTRUMENTATION=YES
FINAL_MAINLINE_PATCH=NO
```

CI result:

```text
CI_RUN=34432765989
CI_COMMIT=a8e91bc68def8f0b8edf688ba9da42eec31ed2e6
CI_RESULT=success
CI_ACTIONLINT=PASS
ARTIFACT=thyme-mainline-v2-m3-early-short-delay-a8e91bc68def8f0b8edf688ba9da42eec31ed2e6
IMAGE_SHA256=396532942ef01e1965ebf3d49ff41271581833c1d29e43c51a580d5d81694e7f
BOOT_SHA256=80afd2859333ea47d3aaa1fbdf6ec8cc678e65510de96c8f3671baad99d1a7ff
M3_PATCH_SHA256=69e765a39abd60e35921d1f86310456ac7b6956bbe5c652041334dd9a19fde60
BOOT_IMAGE_SIZE=35110912
FINAL_CI_GATE=READY_FOR_MAINLINE_V2_M3_EARLY_SHORT_DELAY
```

Required CI gate:

```text
MEM0_CONSTRAINTS_ACKNOWLEDGED=PASS
MAINLINE_VERSION_PINNED=PASS
M3_PATCH_APPLIED=PASS
M3_EARLIER_THAN_M2=PASS
EARLY_TIMER_ACCESS_AUDITED=PASS
M3_DELAY_SECONDS_2=PASS
BOOT_ARGS_PRESERVED=PASS
MAINLINE_IMAGE_BUILD=PASS
M0_M1_M2_RAMDISK_EXACT_REUSE=PASS
INIT_BINARY_EXACT_REUSE=PASS
BOOT_HEADER_V3=PASS
REVERSE_UNPACK=PASS
KERNEL_PAYLOAD_EXACT=PASS
SIZE_GATE=PASS
NO_VENDOR_BOOT_ARTIFACT=PASS
NO_DTBO_ARTIFACT=PASS
NO_VBMETA_ARTIFACT=PASS
NO_FIRMWARE_ARTIFACT=PASS
READY_FOR_MAINLINE_V2_M3_EARLY_SHORT_DELAY
```

Otherwise: `NO DEVICE TEST`.

## M1 context gate hash-domain correction

The original M3 read-only preflight was stopped as `MAINLINE_V2_M3_NOT_SAFE`
because it compared whole physical partition SHA256 values with the smaller
M1 artifact-file SHA256 values. The audit result was
`M1_CONTEXT_INTACT_HASH_DOMAIN_MISMATCH`; it did not establish M1 context
drift. The corrected verifier is:

```text
scripts/mainline-v2-m1-context-check.sh
```

It identifies each artifact with authoritative `ARTIFACT_SIZE` and
`ARTIFACT_SHA256` metadata from private CI run `34338768052`, reads exactly the
first N bytes of the corresponding device partition, and compares only that
prefix SHA256 with the artifact SHA256. The whole partition SHA256 is recorded
as observation-only and has `WHOLE_HASH_GATE=NO`.

Authoritative metadata:

```text
vendor_boot: N=114688 SHA256=29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
dtbo:        N=387    SHA256=316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
```

Synthetic prefix-domain tests run only in GitHub Actions through
`.github/workflows/thyme-mainline-v2-m1-context-gate.yml`. No device operation
is part of that workflow. See
`docs/mainline-v2-m1-context-hash-domain-audit.md` for the test matrix and
read-only boundary.

## M1 DT context freeze

The only device payload change permitted for M3 is `boot_b`:

```text
vendor_boot_b: exact M1 context
              SHA256 29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
dtbo_b:       exact M1 context
              SHA256 316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
vbmeta_b:     stock
vbmeta_system_b: stock
firmware:     stock
ramdisk:      exact M0/M1/M2 P15 reuse
```

If either M1 context hash differs during Android A preflight, stop. Do not
replace it as part of M3.

## Device gate — not yet run

Before any device operation, read mem0 again and record:

```text
MEM0_READ_BEFORE_DEVICE_TEST=YES
LOCAL_BUILD=NO
GHA_ONLY=YES
SLOT_A_WRITTEN=NO
```

From restored Android A, require read-only:

```text
ro.boot.slot_suffix=_a
sys.boot_completed=1
root=uid=0
boot_b: current M0 payload before the M3 write
vendor_boot_b: exact M1 hash above
dtbo_b: exact M1 hash above
vbmeta_b / vbmeta_system_b: stock hashes
```

Enter Fastboot and run the read-only preflight:

```bash
bash scripts/mainline-v2-m3-preflight.sh <m3-artifact-dir>
```

It must report `product=thyme`, `unlocked=yes`, `current-slot=a`,
`snapshot-update-status=none`, and `battery-soc-ok=yes`.

The sole permitted write is:

```text
fastboot flash boot_b <verified-artifact>/mainline-v2-m3-early-short-delay-boot-v3.img
```

Never write `vendor_boot_b`, `dtbo_b`, `vbmeta*`, firmware, or any `*_a`
partition. Return to Android A after the write and verify the `boot_b` hash
against the GHA `SHA256SUMS`; recheck both M1 context hashes and vbmeta hashes.
Do not boot B during this post-write verification.

In Fastboot, record B metadata, set B active once, and confirm `retry:b > 0`
before the one reboot:

```text
fastboot set_active b
fastboot reboot
```

There must be exactly one B boot. The observer performs only the reboot:

```bash
bash scripts/mainline-v2-m3-host-observe.sh
```

It observes only the `18d1:d00d` Fastboot USB identity. It waits at least 15
seconds, and if Fastboot has not returned continues until 60 seconds. It does
not test USB gadget, UDC, configfs, NCM, IPv4, ICMP, or HTTP.

## Timing classification

The host observer records timestamps automatically:

```text
FASTBOOT_DISAPPEAR_TIMESTAMP
FASTBOOT_REAPPEAR_TIMESTAMP
M3_ELAPSED
M3_DELTA_FROM_BASELINE
MANUAL_KEY_REQUIRED
```

The short signature gate is:

```text
M3_ELAPSED >= 5.7s
M3_DELTA_FROM_BASELINE >= 1.0s
```

A return around 6–8 seconds is strong evidence for:

```text
2S_TIME_SIGNATURE=YES
ABL_TO_MAINLINE_EARLY_ENTRY=CONFIRMED
MAINLINE_EARLIEST_CHECKPOINT_EXECUTION=CONFIRMED
Final Gate: MAINLINE_V2_M3_EARLY_ENTRY_CONFIRMED
```

A return around 4–5 seconds records:

```text
2S_TIME_SIGNATURE=NO
EARLIEST_SHORT_DELAY_SIGNATURE_NOT_OBSERVED=YES
ABL_TO_MAINLINE_EARLY_ENTRY=NOT_CONFIRMED
Final Gate: MAINLINE_V2_M3_EARLIEST_CHECKPOINT_NOT_CONFIRMED
```

This does not assert `ABL DID NOT ENTER KERNEL`; the watchdog caveat remains.
An intermediate result is `MAINLINE_V2_M3_INCONCLUSIVE`. No automatic return by
60 seconds is `MAINLINE_V2_M3_NO_AUTOMATIC_RETURN`; do not perform another B
boot.

## Recovery

After the one observation, return to Fastboot if necessary, select A, and
reboot once:

```text
fastboot set_active a
fastboot reboot
```

Never write Slot A. Confirm:

```text
ro.boot.slot_suffix=_a
sys.boot_completed=1
Android A restored=YES
```

Only after A is restored may the read-only `oops`, `minidump`, `rawdump`, and
`logdump` checks be recorded. Pstore evidence is auxiliary, not required for
the timing pass.

## Final report record

The completed report must fill every field below from GHA, the single host
observation, and A recovery. Do not invent pending values.

```text
Constraints:
mem0 read: YES/NO
local build: NO
GHA only: YES
Slot A written: NO

Baseline:
M1: 4.821s
M2: 4.598s
baseline mean: 4.710s
M2 20s signature: NOT_OBSERVED
watchdog caveat: RECORDED

M3:
checkpoint file: arch/arm64/kernel/head.S
checkpoint symbol: primary_entry
checkpoint offset: byte:2920,line:93
position vs M2: earlier; M3_POSITION_BEFORE_M2=YES
M2 checkpoint offset: byte:3652,line:126
timer: CNTFRQ_EL0+CNTPCT_EL0
delay: 2s
scratch registers: x0,x1,x2,x3
boot args preserved: YES

CI:
run: 34432765989
commit: a8e91bc68def8f0b8edf688ba9da42eec31ed2e6
artifact: thyme-mainline-v2-m3-early-short-delay-a8e91bc68def8f0b8edf688ba9da42eec31ed2e6
Image SHA: 396532942ef01e1965ebf3d49ff41271581833c1d29e43c51a580d5d81694e7f
boot SHA: 80afd2859333ea47d3aaa1fbdf6ec8cc678e65510de96c8f3671baad99d1a7ff
patch SHA: 69e765a39abd60e35921d1f86310456ac7b6956bbe5c652041334dd9a19fde60

Exact reuse:
ramdisk:
init:
M1 vendor_boot:
M1 dtbo:
vbmeta*:

Device writes:
boot_b:
vendor_boot_b: NO
dtbo_b: NO
vbmeta*: NO
firmware: NO
Slot A: NO
B boots: 1

Timing:
Fastboot disappear:
Fastboot reappear:
elapsed:
delta from baseline:
manual key: NO

Pstore:
Mainline evidence:

Conclusion:
2S_TIME_SIGNATURE: YES/NO
ABL_TO_MAINLINE_EARLY_ENTRY: CONFIRMED/NOT_CONFIRMED
Final Gate:

Recovery:
Android A restored: YES/NO
slot_suffix:
boot_completed:
```

The allowed final gates are only:

```text
MAINLINE_V2_M3_EARLY_ENTRY_CONFIRMED
MAINLINE_V2_M3_EARLIEST_CHECKPOINT_NOT_CONFIRMED
MAINLINE_V2_M3_NO_AUTOMATIC_RETURN
MAINLINE_V2_M3_EARLY_TIMER_NOT_SAFE
MAINLINE_V2_M3_KERNEL_PANIC
MAINLINE_V2_M3_INCONCLUSIVE
MAINLINE_V2_M3_NOT_SAFE
```
