# Slot B kernel_init entry control

Predecessor: REST_INIT pair STRONG on Slot B (35.392403s / 28.218802s,
delta -7.173600s). All recorded boot-chain hashes remained unchanged.

## Source boundary

Linux 6.6.156 `init/main.c`:

- `rest_init` first creates PID1 using `user_mode_thread(kernel_init, NULL, CLONE_FS)`.
- It creates kthreadd, completes `kthreadd_done`, then explicitly schedules.
- Under voluntary preemption, PID1 can be scheduled earlier and wait for that completion.
- `kernel_init` begins with `wait_for_completion(&kthreadd_done)`, followed by
  `kernel_init_freeable`, asynchronous init completion and userspace execution.

The next checkpoint is at the canonical `kernel_init` entry, expected Image
offset `0x10c2030` (rederived and checked in Actions, never assumed sufficient).
A matched positive proves PID1 was created and scheduled at this entry.
It does not prove completion of the kthreadd wait, the whole rest_init body,
SMP initialization, driver initcalls, initramfs readiness or `/init` execution.

## Artifact construction

Reuse the reconciled kernel audit bundle from `35040148509`; no kernel rebuild.
Compose both 8s and 1s variants from the exact normal FIX8 payload, not from any
previous instrumented payload. Preserve the original landing instruction.
Both windows must pass the ELF byte/section/symbol/incoming-branch/relocation/
runtime-rewrite checks. Only the timer immediate differs between the two
members. Public Actions emit payloads and a pair manifest; private Actions
wrap and independently verify both boot images, including the complete
boot-image two-byte diff. No local compilation, packing or binary validation.

## Device contract (before any kernel_init test)

The B partitions stay stock V14 vendor/DTBO plus the proven P15 recovery boot.
Both tests begin with normal Android A → ADB reboot bootloader → confirmed
active B. A is never flashed. Freeze both full boot SHAs in the CI-tested
observer before executing either image.

Run KINIT8 once. Only a valid automatic Fastboot return plus an unchanged
post-test partition/context readback permits KINIT1 once. Primary expected
delta: `KINIT1_TOTAL - KINIT8_TOTAL = -7s`. STRONG abs(error)<=1s; SUPPORTED
<=2s. No return or manual recovery invalidates the pair and forbids an
automatic second trial. Absolute timing alone does not prove entry.

REST8/REST1 and old RESET8/RESET1 are not rerun as part of this stage.
