# Unvalidated deferred-device name channel draft

**DRAFT_ONLY / NOT_CI_VALIDATED / NOT_DEVICE_READY.** Preserved when the user
requested a conversation handoff on 2026-09-21. Files were moved here without
deletion, outside the active slot_b workflow triggers and unittest discovery.
The generic linux-6.6-ci does not ignore this directory: its closeout-triggered
run was intentionally cancelled before kernel configuration/build. That generic
workflow would not validate this draft even if it completed. No source
in this directory has been assembled, built, binary-validated, packed or run
on the device. Do not treat the successful worker-pair CI as validation of
these files.

## Proposed design, not a qualified experiment

- Target `deferred_probe_work_func`, parent Image `[0x8e8424,0x8e84e8)`.
- Proposed window `[0x8e8468,0x8e84c8)`, 96 bytes, just after the original
  `ldr x20, [x8, #0x20]` selects the first deferred device.
- `x20` is intended to hold `struct device *`; read `device.kobj.name` while
  the deferred-list mutex is still held and before list removal. The source
  declares `kobj` first in `struct device`, and `name` first in `struct kobject`;
  the frozen config has `CONFIG_RANDSTRUCT_NONE=y`. Lifetime, registration /
  `init_name` semantics and exact binary ABI still require complete CI review.
- Candidate variants: `ref8`, `ref1`, `b0lo`, `b0hi`, `b1lo`, `b1hi`. A proposed
  guarded name-byte read encodes a nibble as 1..16 seconds; null/empty-pointer
  guards use a proposed 17-second invalid marker. The core terminates through
  PSCI and cannot resume normal probing. None of these timings has been tested.
- Only byte offsets 0 and 1 are proposed. The nonempty-first-byte guard is
  intended to bound the second-byte access. No arbitrary string traversal.
- The empty-list branch should retain its original target `0x8e84c8`, exactly
  at the proposed window end. This 96-byte geometry has NOT yet passed CI.

## Missing before any device use

1. Review source/ABI, lock/lifetime, empty-list control flow, watchdog headroom,
   byte bounds, and the draft assembly against the Python opcode assertions.
2. Add an isolated, Actions-only workflow. Compile every variant, check length,
   relocation-free assembly, incoming branches, runtime rewrite tables,
   immutable base/trailer/envelope identity and independent re-verification.
3. Add private packing/reverification. Existing public/private deferred-probe
   workflows accept only `prequeue`, `postflush`, `worker`; their default is
   **worker**, an already completed/frozen pair. Do not dispatch the default.
4. Implement and CI-test a fail-closed timing decoder, calibration quality,
   invalid-marker rejection, jitter/ambiguity rejection and evidence semantics.
5. Freeze authoritative full boot/payload SHAs and add dedicated observer
   identities/gates. There are currently no name-channel observer cases.
6. Only after all gates pass: explicit Slot B checks, one RAM boot per candidate,
   calibration first, recovery and partition-hash checks between members.

Reading a first pending device's name would NOT itself identify the faulty
driver, prove that its probe ran, or demonstrate Linux `/init` execution. Do
not disable that driver merely because it appears first.

The draft imports the active `scripts/slot_b` helpers; its new location is
intentionally not directly executable/discoverable. Future integration must
be deliberate and remain entirely within GitHub Actions for compilation,
assembly, image generation and binary validation.
