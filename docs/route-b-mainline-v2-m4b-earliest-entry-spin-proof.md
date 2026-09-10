# Route B Mainline V2 M4B — earliest-entry spin proof

Status: CI gate passed; one-shot Slot B device test is pending explicit approval.
Final device gate is not assigned until the single B observation exists.

This experiment is intentionally narrower than M1–M3. It changes only the Mainline
`boot_b` kernel payload and places one unconditional branch at the first instruction
of `primary_entry`. It does not change the M1 DT context, ramdisk, `/init`, vbmeta,
firmware, or Slot A.

## Frozen forensic context

```text
Device: Xiaomi Mi 10S (thyme / SM8250)
Linux: 6.6.156
Linux base: 8b73de7da85fde281a385e0b26eda9bffd3ca477
M1 elapsed: 4.821s
M2 elapsed: 4.598s
M3 elapsed: 4.790s
M4: RESET_SOURCE_INCONCLUSIVE
M4 oops change: stock Android 4.19 controlled reboot-to-bootloader record
Mainline pstore/watchdog/timer exception/Mainline PC-LR evidence: none
Local build/validation: prohibited
GHA build/validation: required
Slot A: permanently protected
Allowed experiment slot: B only
B boots: one maximum
```

The stable approximately 4.7-second return remains ambiguous. M4 established that
the changed oops record was a stock Android controlled restart, not Mainline crash
evidence. M4B removes timer access, delay arithmetic, MMU-dependent work, firmware
calls, and all active reboot paths from the instrumentation itself.

## Exact source position

Pinned Linux 6.6.156 source has this entry structure:

```text
Image entry symbol: _text
Image header: efi_signature_nop; b primary_entry
primary_entry original first instruction: bl record_mmu_state
primary_entry original path: record_mmu_state -> preserve_boot_args -> create_idmap
```

The source and linker evidence are:

```text
arch/arm64/kernel/head.S
  __HEAD
  efi_signature_nop
  b primary_entry
  SYM_CODE_START(primary_entry)
  bl record_mmu_state

arch/arm64/kernel/vmlinux.lds.S
  ENTRY(_text)
```

M4B applies only:

```asm
SYM_CODE_START(primary_entry)
.Lthyme_m4b_earliest_entry_spin:
	b .Lthyme_m4b_earliest_entry_spin

	bl	record_mmu_state
```

Therefore the honest boundary is:

```text
Before primary_entry: the required Image header/trampoline code remains.
Within primary_entry: no instruction precedes the M4B branch.
M4B first primary_entry instruction: unconditional b to its own address.
After the branch: unreachable for this experiment.
```

There is no `mrs`, `msr`, load/store, timer access, `wfe`, `wfi`, `smc`, `hvc`,
`svc`, `brk`, `udf`, MMIO access, PSCI reset, stack access, or memory access in
the M4B snippet. The loop is a plain branch-to-self; `/init` must not execute.

## CI-only implementation

```text
Patch:
  patches/experiments/mainline-v2-m4b-earliest-entry-spin.patch

Validator:
  scripts/mainline-v2-m4b-ci-validate.sh

Workflow:
  .github/workflows/thyme-mainline-v2-m4b-earliest-entry-spin.yml
```

The workflow is the only location permitted to apply patches, compile the kernel,
disassemble `vmlinux`, pack Android boot v3, reverse-unpack it, and run gates. The
baseline is checked against the exact Linux commit before the current Mainline
patch queue and the experimental patch are applied.

The exact M0/M1 P15 inputs are downloaded from the immutable M0 Actions artifact and
must retain these hashes:

```text
Image:             22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6
/init:             aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8
initramfs.cpio.gz: b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
```

The artifact is limited to:

```text
mainline-v2-m4b-entry-spin-boot-v3.img
Image
mainline-v2-m4b-earliest-entry-spin.patch
SHA256SUMS
validation-report.txt
reverse-unpack-report/
```

No `vendor_boot`, `dtbo`, `vbmeta`, or firmware artifact is emitted.

## Required CI proof

The validation report must contain the following source identity:

```text
IMAGE_ENTRY_SYMBOL=_text
PRIMARY_ENTRY_SYMBOL=primary_entry
FIRST_ORIGINAL_PRIMARY_ENTRY_INSN=bl record_mmu_state
M4B_FIRST_PRIMARY_ENTRY_INSN=b .Lthyme_m4b_earliest_entry_spin
NO_INSTRUCTION_BEFORE_SPIN_WITHIN_PRIMARY_ENTRY=PASS
```

It must also prove the final payload, not only the patch text:

```text
EARLIEST_SPIN_SOURCE=PASS
EARLIEST_SPIN_DISASSEMBLY=PASS
SELF_BRANCH_TARGET=PASS
SELF_BRANCH_DISASSEMBLY=PASS
PRIMARY_ENTRY_SPIN_FIRST=PASS
IMAGE_HEADER_BRANCH_TO_PRIMARY_ENTRY=PASS
PRIMARY_ENTRY_IMAGE_SELF_BRANCH=PASS
```

The required gates are:

```text
MEM0_POLICY_ACKNOWLEDGED=PASS
MAINLINE_VERSION_PINNED=PASS
M4B_PATCH_APPLIED=PASS
M3_TIMER_INSTRUMENTATION_ABSENT=PASS
PRIMARY_ENTRY_SPIN_FIRST=PASS
SELF_BRANCH_DISASSEMBLY=PASS
NO_TIMER_SYSREG=PASS
NO_MMIO=PASS
NO_EXCEPTION_INSTRUCTION=PASS
NO_PSCI_REBOOT=PASS
RAMDISK_EXACT_REUSE=PASS
INIT_BINARY_EXACT_REUSE=PASS
BOOT_HEADER_V3=PASS
REVERSE_UNPACK=PASS
KERNEL_PAYLOAD_EXACT=PASS
SIZE_GATE=PASS
NO_VENDOR_BOOT_ARTIFACT=PASS
NO_DTBO_ARTIFACT=PASS

Final CI gate:
READY_FOR_MAINLINE_V2_M4B_ENTRY_SPIN
```

If any gate fails, no device operation is safe.

## Completed CI run

```text
CI_RUN=34464472317
CI_COMMIT=ace24d1c4f9537ab8726c551fa0d88155b581f7a
CI_RESULT=success
CI_ACTIONLINT=PASS
ARTIFACT=thyme-mainline-v2-m4b-entry-spin-ace24d1c4f9537ab8726c551fa0d88155b581f7a
KERNEL_VERSION=6.6.156
LINUX_BASE_COMMIT=8b73de7da85fde281a385e0b26eda9bffd3ca477
IMAGE_SHA256=52e429db5ba7ba411598625f706dc11d3d7c247458a932969e9913db0d1511a2
BOOT_SHA256=622a09516ddfcda7efad3cc42b92d2c205130ba7b0a8cf8cbba32c26a822b4c0
PATCH_SHA256=30738f0e27f8ecc2d44a3a6e9c9c86b2d1991dfe1b7ba2bfa317448c1bba0833
BOOT_IMAGE_SIZE=35110912
FINAL_CI_GATE=READY_FOR_MAINLINE_V2_M4B_ENTRY_SPIN
LOCAL_BUILD=NO
DEVICE_TEST=NOT_RUN
```

Disassembly of the built `vmlinux` `primary_entry`:

```text
ffff800081b1c0a0 <primary_entry>:
ffff800081b1c0a0:       14000000        b       ffff800081b1c0a0 <primary_entry>
ffff800081b1c0a4:       94007464        bl      ffff800081b39234 <record_mmu_state>
```

The Image header at `_text+4` is `b primary_entry` (`0x146c7027`), and the first
word at Image offset `0x1b1c0a0` is `0x14000000` (`b .`). That is the earliest
instruction inside `primary_entry`; the Image still has the required header
trampoline `efi_signature_nop; b primary_entry` before that symbol.

M3 timer instrumentation is absent. The exact M0/M1 P15 ramdisk and `/init` were
reused. No `vendor_boot`, `dtbo`, `vbmeta`, or firmware artifact was emitted.

## Frozen M1 context

The device context must remain the corrected M1 prefix domain:

```text
vendor_boot_b first 114688 bytes SHA256:
29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5

dtbo_b first 387 bytes SHA256:
316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1

vbmeta_b: stock
vbmeta_system_b: stock
firmware: stock
```

Whole partition hashes are observations only. The fixed prefix-domain verifier must
pass from Android A before the write and after the write. If either prefix differs,
stop; do not repair the context in this experiment.

## Device gate

Before any device operation, read mem0 again and acknowledge:

```text
GHA_ONLY=YES
SLOT_A_WRITTEN=NO
ONLY_BOOT_B=YES
ONE_B_BOOT=YES
M1_CONTEXT_PREFIX_DOMAIN=YES
RECOVER_A=YES
```

Android A read-only preflight must report:

```text
ro.boot.slot_suffix=_a
sys.boot_completed=1
root uid=0
```

Then run the corrected `scripts/mainline-v2-m1-context-check.sh` and require both
M1 prefix matches, stock `vbmeta_b`/`vbmeta_system_b`, and no firmware change.

Fastboot preflight must report `product=thyme`, `unlocked=yes`, `current-slot=a`,
`snapshot-update-status=none`, `battery-soc-ok=yes`, and record B retry/unbootable
metadata. The sole write is:

```text
fastboot flash boot_b mainline-v2-m4b-entry-spin-boot-v3.img
```

Do not write `vendor_boot_b`, `dtbo_b`, `vbmeta*`, firmware, or any Slot A
partition. Return to Android A without booting B and independently verify the
written `boot_b` SHA against CI, then recheck the M1 prefixes and stock vbmeta.

Only after that verification:

```text
fastboot set_active b
fastboot reboot
```

This is the only B boot. The host observer only watches the `18d1:d00d` Fastboot
identity and measures its disappearance/reappearance. It does not probe `/init`,
USB gadget, network, or any MMIO path. The observation window is hard-limited to
12 seconds; it must not wait 60 seconds.

## Device classification

### Case A — baseline return

If Fastboot automatically reappears at approximately 4.3–5.3 seconds without a
key press:

```text
M4B_SPIN_SUPPRESSION_EFFECT=NO
ABL_TO_MAINLINE_ENTRY=NOT_CONFIRMED
MAINLINE_PRIMARY_ENTRY=NOT_CONFIRMED
EXTERNAL_4P7S_RESET_HYPOTHESIS=SUPPORTED
FINAL_GATE=MAINLINE_V2_M4B_ENTRY_SPIN_NOT_CONFIRMED
```

This does not prove that ABL failed to enter the Image. It strengthens the external
reset hypothesis because a pure self-branch has no timer trap, MMU fault, DT error,
or explicit reboot path.

### Case B — baseline return suppressed

If Fastboot does not return through the 10–12 second window, stop waiting and
perform the known physical Fastboot recovery. Do not issue an ordinary reboot while
B is active; that could enter the spin again.

```text
BASELINE_EARLY_RETURN_SUPPRESSED=YES
M4B_SPIN_CONTROL_FLOW_EFFECT=YES
ABL_TO_MAINLINE_ENTRY=CONFIRMED
MAINLINE_PRIMARY_ENTRY_EXECUTION=CONFIRMED
MANUAL_RECOVERY_REQUIRED=YES
FINAL_GATE=MAINLINE_V2_M4B_ENTRY_SPIN_CONFIRMED
```

On entering Fastboot, read B metadata first, select A, confirm `current-slot=a`,
and reboot once to Android A.

### Case C — intermediate return

A return later than baseline but before the hard window is:

```text
MAINLINE_V2_M4B_INCONCLUSIVE
```

Do not repeat B. Preserve the exact timing and recovery metadata.

## Result record

Do not fill pending values from expectation. Record only GHA logs, the one host
observation, and read-only Android A evidence:

```text
Constraints:
mem0 read: YES/NO
local build: NO
GHA only: YES
Slot A written: NO

Baseline:
M1: 4.821s
M2: 4.598s
M3: 4.790s
M4: RESET_SOURCE_INCONCLUSIVE

M4B instrumentation:
kernel: 6.6.156
commit: 8b73de7...
IMAGE_ENTRY_SYMBOL: _text
PRIMARY_ENTRY_SYMBOL: primary_entry
FIRST_ORIGINAL_PRIMARY_ENTRY_INSN:
M4B_FIRST_PRIMARY_ENTRY_INSN:
disassembly verified: YES/NO
timer instructions: NO
MMIO: NO
PSCI/SMC/HVC: NO
WFE/WFI: NO
BRK/UDF: NO

CI:
run:
commit:
artifact:
Image SHA:
boot SHA:
patch SHA:

Context:
M1 vendor_boot prefix: MATCH/MISMATCH
M1 dtbo prefix: MATCH/MISMATCH
vbmeta: STOCK/UNKNOWN

Device writes:
boot_b: YES/NO
other B partitions: NO
Slot A: NO WRITE

Runtime:
Fastboot disappear:
automatic Fastboot reappear: YES/NO
elapsed if automatic:
elapsed before manual recovery:
baseline 4.7s return suppressed: YES/NO
manual recovery required: YES/NO
B boots: 1

Pstore:
Mainline evidence:

Conclusion:
ABL_TO_MAINLINE_ENTRY: CONFIRMED/NOT_CONFIRMED
MAINLINE_PRIMARY_ENTRY: CONFIRMED/NOT_CONFIRMED
EXTERNAL_4P7S_RESET_HYPOTHESIS: SUPPORTED/UNKNOWN

Recovery:
Android A restored: YES/NO
slot_suffix:
boot_completed:

Final Gate:
MAINLINE_V2_M4B_ENTRY_SPIN_CONFIRMED
MAINLINE_V2_M4B_ENTRY_SPIN_NOT_CONFIRMED
MAINLINE_V2_M4B_EXTERNAL_RESET_SUSPECTED
MAINLINE_V2_M4B_INCONCLUSIVE
MAINLINE_V2_M4B_NOT_SAFE
```

The final report and mem0 update must be written only after the one permitted B boot
and Android A recovery. Do not store serials, tokens, or CPU identifiers.
