# Route B Mainline V2 M2 — early-entry time signature

Status: implementation prepared; GitHub Actions and the one-shot device gate are
pending. M2 answers only whether ABL executed the Mainline ARM64 kernel through
one very-early checkpoint.

## Frozen experiment

| Item | M2 value |
|---|---|
| Linux | 6.6.156 |
| base commit | `8b73de7da85fde281a385e0b26eda9bffd3ca477` |
| checkpoint | `primary_entry`, after `init_kernel_el` returns and `mov x20, x0` |
| checkpoint end | before `__cpu_setup` |
| counter | `CNTFRQ_EL0` + `CNTPCT_EL0` |
| delay | 20 seconds, busy-wait |
| boot change | `boot_b` kernel payload only |
| generic ramdisk | exact M0 artifact reuse |
| `vendor_boot_b` | exact M1 context, unchanged |
| `dtbo_b` | exact M1 context, unchanged |
| `vbmeta_b` / `vbmeta_system_b` | stock, unchanged |
| USB/IP/HTTP | not tested |

M1 reference timing is fixed at `4.821 s` from Fastboot USB disappearance to
reappearance. M2 does not call `kernel_restart()`, `panic()`, or a PSCI reset.
The delay falls through to the original kernel entry path.

## Source audit decision

The pinned Linux source has this primary path:

```text
primary_entry
  -> record_mmu_state
  -> preserve_boot_args
  -> create_idmap
  -> init_kernel_el
  -> __cpu_setup
  -> __primary_switch
```

The experimental patch inserts the checkpoint between `init_kernel_el` and
`__cpu_setup` in:

```text
arch/arm64/kernel/head.S
```

`preserve_boot_args` saves the original FDT pointer in `x21` and records `x0`
through `x3` in `boot_args`. The delay uses only `x0`–`x3`; the primary boot
path registers `x19`–`x25` remain untouched.

For an EL2 entry, `init_kernel_el` invokes `init_el2_state`; its
`__init_el2_timers` setup writes `CNTHCTL_EL2` before the `eret` to the EL1
kernel path. For a direct EL1 entry, the counter registers are already EL1
accessible. The existing arm64 arch-timer accessor uses `CNTFRQ_EL0` and an
ordered `isb` + `CNTPCT_EL0` read. The CI source gate rechecks these facts at the
pinned source, rather than trusting the patch comment.

The patch is deliberately not an upstream feature change:

```text
patches/experiments/mainline-v2-m2-early-delay.patch
EXPERIMENTAL_INSTRUMENTATION=YES
UPSTREAM_FEATURE_CHANGE=NO
```

## GitHub Actions only

Workflow:

```text
.github/workflows/thyme-mainline-v2-m2-early-entry-delay.yml
```

Validator:

```text
scripts/mainline-v2-m2-ci-validate.sh
```

The workflow downloads the exact M0 Actions artifact from run `34322563307` and
checks these immutable inputs before packaging:

```text
M0 Image:              22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6
M0 /init:              aab8211a07d26f7a05937618d851891fe0eb1398c6567560927cdd67a5ae02e8
M0 initramfs:          b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de
```

All checkout, patch application, kernel compilation, disassembly, image
packing, reverse unpack, and SHA validation run in GitHub Actions. Local work is
limited to source review, Git operations, hashing, and read-only device queries;
no local build or validator is permitted.

The CI gate must include:

```text
MAINLINE_VERSION_PINNED=PASS
M2_PATCH_APPLIED=PASS
EARLY_CHECKPOINT_PRESENT=PASS
EARLY_COUNTER_ACCESS_AUDITED=PASS
DELAY_SECONDS_20=PASS
BOOT_ARGS_PRESERVED=PASS
MAINLINE_IMAGE_BUILD=PASS
M0_INITRAMFS_EXACT_REUSE=PASS
M0_INIT_BINARY_EXACT_REUSE=PASS
BOOT_V3=PASS
REVERSE_UNPACK=PASS
KERNEL_PAYLOAD_EXACT=PASS
RAMDISK_EXACT=PASS
SIZE_GATE=PASS
NO_VENDOR_BOOT_ARTIFACT=PASS
NO_DTBO_ARTIFACT=PASS
```

Final artifact scope:

```text
mainline-v2-m2-early-delay-boot-v3.img
Image
mainline-v2-m2-early-delay.patch
SHA256SUMS
validation-report.txt
reverse-unpack-report/
```

No `vendor_boot`, `dtbo`, `vbmeta`, or firmware artifact is emitted.

## Device gate

Read mem0 and record the preflight before any device operation. Start from
Android A and verify, read-only:

```text
ro.boot.slot_suffix = _a
sys.boot_completed  = 1
root                = uid=0
boot_b              = M0 SHA256 378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
vendor_boot_b       = M1 SHA256 29ba377ecae631273103f944d9833070c25e7c4dd2f0b7fce439cc2c80d9d1e5
dtbo_b              = M1 SHA256 316c12d9bbff26072f0924a9bd4b9d524c0dd2869b73e9743a0fb441af15d9c1
vbmeta_b            = stock SHA256 37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
vbmeta_system_b     = stock SHA256 3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
```

If either M1 context hash differs, stop. In Fastboot, run the read-only
preflight and require:

```bash
bash scripts/mainline-v2-m2-preflight.sh <artifact-dir>
```

It must report:

```text
product=thyme
unlocked=yes
current-slot=a
snapshot-update-status=none
battery-soc-ok=yes
```

The only permitted write is:

```bash
fastboot flash boot_b <verified-m2-artifact>/mainline-v2-m2-early-delay-boot-v3.img
```

Never write any `*_a`, `vendor_boot_b`, `dtbo_b`, `vbmeta*`, or firmware.

After the write, return to Android A and independently verify the new `boot_b`
SHA against the CI artifact. Recheck that `vendor_boot_b` and `dtbo_b` still
match M1 and that both vbmeta partitions remain stock. Then enter Fastboot,
record metadata, set the active slot to B, and boot B exactly once:

```bash
fastboot set_active b
fastboot reboot
```

The host observer performs only that one reboot and never flashes or changes a
slot:

```bash
bash scripts/mainline-v2-m2-host-observe.sh
```

Timing uses only:

```text
FASTBOOT_USB_DISAPPEAR
FASTBOOT_USB_REAPPEAR
```

The observer records the Fastboot USB identity (`18d1:d00d`) and does not use
network, VPN, USB-gadget, or HTTP evidence.

When Fastboot returns, do not boot B again. Restore A:

```bash
fastboot set_active a
fastboot reboot
```

Confirm `ro.boot.slot_suffix=_a` and `sys.boot_completed=1`. If B does not
return automatically within 60 seconds, recover Fastboot physically and perform
only the same A recovery; classify the run before any further experiment.

## Timing classification

```text
M1_REFERENCE_M1_ELAPSED = 4.821 s
M2_DELAY_SECONDS         = 20
```

Pass only when Fastboot returns automatically and:

```text
M2 elapsed >= 20 s
M2 elapsed - 4.821 s >= 15 s
```

Expected strong range is approximately `23–30 s`. The allowed final gates are:

```text
MAINLINE_V2_M2_EARLY_ENTRY_CONFIRMED
MAINLINE_V2_M2_CHECKPOINT_NOT_REACHED
MAINLINE_V2_M2_NO_AUTOMATIC_RETURN
MAINLINE_V2_M2_KERNEL_PANIC
MAINLINE_V2_M2_INCONCLUSIVE
MAINLINE_V2_M2_NOT_SAFE
```

A return around `4–7 s` is `MAINLINE_V2_M2_CHECKPOINT_NOT_REACHED`; a small
change such as `6–10 s` is `MAINLINE_V2_M2_INCONCLUSIVE`. No pstore marker is
required for the time-signature pass, but any Mainline pstore evidence is
recorded as auxiliary evidence after A is restored.

## Result record

```text
mem0 read:
local build: NO
GHA only:
Slot A flashed: NO

M1 elapsed: 4.821s
Mainline version: 6.6.156
Mainline commit: 8b73de7da85fde281a385e0b26eda9bffd3ca477

checkpoint file: arch/arm64/kernel/head.S
checkpoint symbol: primary_entry
checkpoint after: init_kernel_el return (mov x20, x0)
checkpoint before: __cpu_setup
counter: CNTFRQ_EL0+CNTPCT_EL0
delay: 20
registers: x0,x1,x2,x3
boot args preserved:

CI commit:
CI run:
artifact:
Image SHA:
boot SHA:
patch SHA:

M0/M1 initramfs exact reuse:
M1 vendor_boot unchanged:
M1 dtbo unchanged:

FASTBOOT_USB_DISAPPEAR:
FASTBOOT_USB_REAPPEAR:
elapsed:
delta vs M1:
manual key:

Mainline evidence:
panic:
Conclusion:
EARLY_TIME_SIGNATURE:
ABL_TO_MAINLINE_EARLY_CODE:
Final Gate:

Android A restored: YES/NO
slot_suffix:
boot_completed:
```

If the signature is confirmed, the next experiment is M3: move one checkpoint
later toward `start_kernel`, without changing USB, DTS, vendor boot, DTBO, or
any Slot A partition.
