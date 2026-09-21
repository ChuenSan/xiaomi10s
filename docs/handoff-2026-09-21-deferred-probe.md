# Xiaomi Mi 10S mainline handoff — 2026-09-21

Continuation update: the new selected-device pair is now complete. Read
`docs/slot-b-deferred-selected-device.md` and the top of
`docs/route-r3-current-status.md` before the historical handoff below.
SELECTED8/1 gave STRONG evidence for mutex acquisition, a nonempty active list
and the original first-device pointer load. They are also rerun-FORBIDDEN.
The user explicitly authorized subagents for this continuation; that overrides
the historical no-delegation clause below. All build/Slot A/experiment gates
remain in force.

## Stop reason and authoritative state

The user requested a conversation switch and complete closeout. This is an
intentional handoff, **not** a boot-success claim or a device-recovery blocker.
No additional experiment should be inferred from unfinished source drafts.

Read this file, `docs/slot-b-deferred-probe-callsite-isolation.md`, and the
latest mem0 handoff under agent `bzg-thyme-mainline` before continuing. Semantic
search order is not chronological; verify dates/metadata. The first 150 rows
from `get_memories` also did not include the newest project records.

Final read-only device check: **2026-09-21T03:28:50Z**. `41a5627b`, product
`thyme`, model M2102J2SC, stock Android A, `ro.boot.slot_suffix=_a`,
`sys.boot_completed=1`, kernel `4.19.157-perf-g9d90dd04aa7c`, root via Magisk.
Pstore is empty. All 16 recorded boot-chain hashes and the P15 boot_b prefix
match the beginning of this continuation. No further device boot occurred
after the six experiments listed below.

## Workspaces and commits

| Purpose | Repository / location | Branch / known head |
|---|---|---|
| Active public work | `ChuenSan/xiaomi10s`, `/Volumes/LinuxDev/thyme-mainline-slot-b-continuation` | `route-b-slot-b-continuation`; tested source/observer freeze `06a1d79e3b8bace3c3c3da7a100c2f2df0839b74`; closeout commit contains this file |
| Private OEM envelope packing | `ChuenSan/thyme-mainline-private-ci`, `/Volumes/LinuxDev/thyme-mainline-private-ci` | `main`, `52e88c4caa5577ca0e5a1e679e1e4f8adaa29e1b` |
| Old dirty workspace — do not reset/clean/pull over it | `/Volumes/LinuxDev/thyme-mainline` | `route-b-v3`, `5550dc258f7d7a82c6908267ef101eeb5b299205` |

The old workspace still has its original tracked modifications to `.gitignore`
and `docs/route-b-mainline-v2-m3-earliest-entry-short-time-signature.md`.
They were not edited. Pre-existing untracked artifacts/caches in all worktrees
are retained; do not delete them or confuse them with unfinished source work.
No subagent was invoked during this continuation.

Relevant public commits, in order:

- `d3e0668`: first deferred prequeue/postflush fixed-window audit/composition.
- `0eef215`: unit-fixture correction for CI jobs without a kernel checkout.
- `7921561`: freeze prequeue/postflush identities and observer gates.
- `c552708`: record four device boots and start worker forensic audit.
- `cbb1f8a`: scoped deferred-worker callback candidate + forensic evidence.
- `c16c515`: fix actionlint SC2066 by removing a one-item shell loop.
- `06a1d79`: freeze independently verified worker identities and observer gates.

## Completed true-device experiments

All were **one RAM-only Slot B `fastboot boot` per member**, with ADB origin
from healthy Android A, explicit B selection, final-moment B validation,
automatic Fastboot B return, and retry count 7→6. Android A was restored and
all recorded hashes checked after every member. Partition image writes: **0**.
Slot A flash/erase/format: **0**. Local builds/binary validators: **0**.

| Case | Total seconds | Matched pair result |
|---|---:|---|
| `defer_prequeue8` | 35.423422125 | reference |
| `defer_prequeue1` | 28.465627750 | delta −6.957794375, error +0.042205625: **STRONG** |
| `defer_postflush8` | 48.591122792 | reference |
| `defer_postflush1` | 48.346502500 | delta −0.244620292: **SHIFT_NOT_OBSERVED** |
| `defer_worker8` | 35.517175625 | reference |
| `defer_worker1` | 28.475640458 | delta −7.041535167, error −0.041535167: **STRONG** |

All six cases are now **rerun-FORBIDDEN**. No no-return, manual recovery, or
unexpected USB transport loss occurred in these six tests.

### What is proven

- The earlier late initcall index 54 `deferred_probe_initcall` entry remains
  PROVEN; `LATEST_PROVEN_LATE_INDEX=54`.
- At Image `0x8e7614`, its first inlined trigger has completed the enable flag,
  mutex/list-splice/unlock prefix and reached the first queue submission setup.
- `deferred_probe_work_func` entry is PROVEN. Its parent is
  `0xffff8000808e8424`, 196 bytes in `.text`; the original `paciasp` was preserved
  and the 56-byte terminal core occupied Image `[0x8e8428,0x8e8460)`.
- Therefore the deferred work callback does start. This does **not** by itself
  prove that `queue_work_on` returned; the worker may start concurrently.

### What remains unproven

- Completion of the second `flush_work` at Image `0x8e76b8`.
- Worker list-lock acquisition, a nonempty deferred list, which device is first,
  execution/return of a particular device's probe, and the root-cause driver.
- Late initcalls completion, initramfs wait entry/return, console setup,
  `/init` execution, usable mainline boot, and USB/network functionality.

`SHIFT_NOT_OBSERVED` is **not** equivalent to "never executed". The working
investigation interval is deferred work submission/processing through the
second flush, with callback entry now proven. Do not return to a blind
late-index entry search or claim that all of `deferred_probe_initcall` is done.

## CI and artifact authority

| Stage | Public audit / source | Private pack + fresh-job independent reverify | Observer gate |
|---|---|---|---|
| prequeue | `35553769346` @ `d3e0668` | `35554007042` @ `dc1f800` | `35554398477` @ `7921561` |
| postflush | same public run | `35554009619` @ `dc1f800` | same observer run |
| worker forensic, no candidate | `35555269943` @ `c552708` | none | none |
| worker | `35555866440` @ `c16c515` | `35556073389` @ `52e88c4` | `35556276869` @ `06a1d79` |

Every run above succeeded. All 22 workflows triggered by the last freeze
`06a1d79` completed successfully. Full source/observer suite `35556276784`:
**526 tests, OK, skipped=14** (source-dependent tests in the no-submodule job).
The production binary audits separately fetched and checked pinned Linux.
No relevant Actions job remains running at closeout. Publishing the isolated
source drafts in closeout commit `b1de55e` automatically triggered generic
`linux-6.6-ci` run `35558011309`. That exact run was intentionally CANCELLED
while fetching Linux, before configuration or kernel/image builds. It is not
a kernel failure or draft-validation evidence. The draft directory is outside
slot_b-specific triggers, but not the generic Linux CI path filter.

Historical failures are resolved, not device/kernel failures:
`35553769353` (test assumed a checked-out kernel; fixed `0eef215`, full suite
`35553891939` and public re-audit `35553891868` passed), and `35555700057`
(actionlint SC2066; fixed `c16c515`, replaced by `35555866440`).
A host preflight pipeline also stopped with SIGPIPE before B selection and
before any experimental boot; product/current-slot checks were then completed
without `tee | grep -q` on live Fastboot output. Do not count that as a boot.

### Immutable foundations

- Linux 6.6.156 base: `8b73de7da85fde281a385e0b26eda9bffd3ca477` plus the
  repository patch queue.
- Public audit bundle run `35040148509`, artifact
  `thyme-slot-b-kernel-audit-bundle`, vmlinux SHA256
  `295bfdb12184052a79c1aea35ce4a93a5833c42bdb7b4bd9173973312ade00ff`.
- Public FIX8 payload run `34741153230`, artifact `thyme-r3-p1b-fix8-fix24`,
  payload SHA256 `4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41`.
- Private FIX8 boot run `34744041027`, artifact `thyme-r3-p1b-fix8-fix24-boot`,
  base boot SHA256 `ba3d8789356fd69af1a4adb5a22aebf8b3c427528143793b3358e886aa462ab5`.
- Tested candidate size: **37380096 bytes**, all six images. Authoritative
  per-case full boot/payload SHA identities are in
  `scripts/slot_b/deferred_probe_identities.json` and `scripts/slot_b/observe.py`.
  Do not transcribe/truncate/reconstruct them from memory.

### Evidence locations

Root: `artifacts/slot-b-deferred-probe-20260921/`.

- `device-round/`: six per-case result/events JSONs, host logs, slot selections,
  origin checks, per-member Android recovery and 16-chain/P15 snapshots,
  `closeout-*` read-only final checks.
- `public-audit/`, `worker-forensic/`, `worker-audit/`: CI-produced audits,
  disassembly, config, geometry and full SHA reports.
- `observer/`, `worker-observer/`, `closeout-public-ci.json`: gates and CI state.
- `private/{prequeue,postflush,worker}/`: downloaded boot images and identity
  JSONs; corresponding `*-reverify/` directories. **These OEM-derived images
  are local/private only and must not be added to the public repository.**

## Current B recovery baseline

B is **stock V14 vendor_boot/dtbo plus the already-proven P15 recovery boot**,
not the obsolete M5D+M5H+M5M-B context from earlier records. Current B was not
rewritten in this continuation.

The P15 prefix is the first **52666368 bytes** of `boot_b` (4096 × 12858), SHA256
`133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34`.
Do not confuse that prefix digest with the full boot_b partition digest.
All 16 authoritative full-partition values are in
`device-round/closeout-partition-sha256.sorted`; the observer's expected B
context is `device-round/context.json`. The final hashes match the initial
`pre-partition-sha256.sorted` and the prior text54 post snapshot exactly.

## Rejected geometry and unresolved diagnosis

Forensic `35555269943` rejected naive 56-byte windows immediately before
`bus_probe_device` (`0x8e84a8`) or after it (`0x8e84ac`): the empty-list branch
at `0x8e8454` targets `0x8e84c8`, inside those windows. Neither unsafe candidate
was generated or booted. Do not bypass the incoming-branch gate or reuse a
nearby window without proving its complete control flow and rewrite closure.

`deferred_probe_timeout` is scheduled only after the unproven second flush;
changing that timeout is not an evidenced fix for the current interval.
External search found only generic deferred-probe/Qualcomm bring-up guidance,
not a thyme-specific root cause. No driver, clock, power-domain or DT node has
been disabled based on those generic suggestions. The frozen RT-D command line
is still `rdinit=/init panic=5 loglevel=7`.

## Unfinished work — isolated draft, not ready

`drafts/slot-b-deferred-name-20260921/` contains the **unvalidated** files
`deferred-name.S`, `deferred_name_probe.py`, `test_deferred_name_probe.py` and
its README. They were moved out of `scripts/slot_b` during closeout so they
cannot be mistaken for active CI-tested code or picked up by its unittest
suite. No files were deleted.

The proposal is a 96-byte read-only name-nibble timing probe at
`[0x8e8468,0x8e84c8)`, after the first device pointer is loaded into x20 but
before list removal, while the deferred mutex is held. Six proposed variants:
8/1-second calibration plus low/high nibbles of name bytes 0/1; a proposed
17-second invalid-pointer marker. **None is assembled, CI-validated, packed,
identity-frozen, registered with the observer, or device-tested.**

Missing: full source/ABI/lifetime/`init_name` review, actual opcode/relocation
and window validation, watchdog/invalid-marker review, a fail-closed calibrated
decoder with ambiguity tests, Actions integration, private packing/reverify,
full identity freeze, observer gates, then any new device authorization/gates.
The existing public/private deferred-probe workflows accept only prequeue,
postflush and worker and currently default to **worker**. Do not dispatch that
default as the "next step"; it regenerates an already completed case.

Prefer an isolated new workflow for the draft rather than accidentally
rebuilding old frozen pairs. Test calibration before any encoded member. If
timing is ambiguous, the list/identity is unstable, a name pointer is invalid,
or a return/transport anomaly occurs, stop and record the uncertainty. A name
would identify a first pending device, not prove that it is the failing driver.

## Non-negotiable constraints for the next conversation

1. Read latest mem0 and these current files first; preserve completed evidence.
2. No local compile, assemble, link, kernel build, DT/image generation, source
   validator/actionlint or binary validator/objdump/readelf. Use GitHub Actions.
   Local editing, log review, checked downloads, read-only device hashing and
   the CI-gated device observer are distinct from building artifacts.
3. **Never flash/erase/format/write Slot A partitions or firmware.** Confirm
   `current-slot=b` immediately before any experimental boot or B write.
   Prefer RAM-only `fastboot boot`; keep the proven B recovery context intact.
4. Re-selecting healthy A for recovery is not permission to flash A. Verify A
   health and all 16-chain/P15 hashes between tests. Stop on anomalous state.
5. Do not re-run these six cases, earlier completed entry/initcall pairs,
   text54/compact52/btic51, or the frozen index55 no-shift pair. LATE_HIGH1,
   RESET1, FIX24, M5N and USB remain frozen; do not silently repurpose them.
6. No file/directory deletion, cleaning, resetting or discarding existing work.
   Preserve old dirty workspace `5550dc2`. Isolate by rename when necessary.
7. Acquire binary data through **`adb shell -T`**, never `adb exec-out su -c`:
   earlier on-device testing proved CR insertion by exec-out on this Mac /
   ADB / Magisk combination. Never use or silently repair corrupt acquisitions.
8. OEM-derived images stay private. No placeholder SHA, generic `.text` policy
   relaxation, bypassed identity gate, unreviewed branch window or blind retry.
9. No successful mainline-boot claim until new actual evidence supports it.
   The current gate is worker-entry proof, not `/init` or usable Linux.
10. Use Chinese to address 白子哥, English for tool/model interaction, and do not
    delegate unless newly authorized. CodeGraph timed out in the old indexed
    root; the active continuation worktree has no index. Do not create an index
    or perform a historical rescan merely to continue this handoff.
