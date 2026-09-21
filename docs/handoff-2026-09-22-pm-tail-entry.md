# Xiaomi Mi 10S handoff — PM-tail entry, 2026-09-22

## Stop and reading order

The user requested complete closeout, memory archival and a new conversation.
Work is intentionally paused. This is not project completion or device loss.
Do not start another build, experiment or slot change until continuation resumes.

Read this document, `docs/slot-b-deferred-pm-tail.md`, the current-status top,
and the latest canonical mem0 handoff under `bzg-thyme-mainline`.
Some earlier memory prose has corrupted Git identifiers, including a short
private prefix. Do not use memory-prose hashes operationally. Obtain full
identities from Git, `scripts/slot_b/deferred_pm_tail_identities.json` and the
committed CI receipts. Semantic memory rank is not chronological.

## Repositories and preserved state

- Public: `ChuenSan/xiaomi10s`, cwd
  `/Volumes/LinuxDev/thyme-mainline-slot-b-continuation`, branch
  `route-b-slot-b-continuation`. This document's commit is the closing commit.
  Active scripts/workflows are unchanged from the tested observer freeze;
  resolve its full SHA through `observer-runs-cea1cd9.json` below.
- Private: `ChuenSan/thyme-mainline-private-ci`, cwd
  `/Volumes/LinuxDev/thyme-mainline-private-ci`, branch `main`. Its source is
  unchanged from the private commit in the frozen identities JSON.
- Both tracked trees were clean before the documentation-only closeout.
  Existing untracked artifacts/caches remain intact; nothing was deleted.
- Old `/Volumes/LinuxDev/thyme-mainline` remains on `route-b-v3`, with its
  original modified `.gitignore` and M3 earliest-entry document untouched.
- No CodeGraph index exists in the continuation worktree. Do not create one
  or rescan the old indexed root to continue.

## Completed runtime milestone

**DEFERRED_PM_TAIL_ENTRY_PROVEN**. Exactly one RAM-only Slot B boot per member:

| Member | Automatic Fastboot B return | Retry count |
|---|---:|---|
| PMTAIL8 | 35.580534792 s | 7 to 6 |
| PMTAIL1 | 28.447709084 s | 7 to 6 |

Delta -7.132825708 s; error -0.132825708 s against -7 s: **STRONG**.
Proven: original reason-clear store executed, worker `mutex_unlock()` returned,
and `device_pm_move_to_tail()` entry. Not proven: persistent field state,
SRCU/PM locking, PM-list movement, PM-tail return, any bus/driver probe,
device identity/culprit, late-initcall completion, `/init` or usable Linux.
USB remains frozen; latest proven late index remains 54.

Both members automatically returned without manual recovery. Android A was
restored after each, with all 16-chain/P15 hashes unchanged before/between/after.
There were **two experimental RAM boots, zero partition-image flashes and zero
Slot A image writes**. Slot selection for recovery is not permission to flash A.

All twelve completed deferred cases are rerun-forbidden: prequeue8/1,
postflush8/1, worker8/1, selected8/1, afterfree8/1 and pmtail8/1. All previously
completed entry/initcall probes and frozen index55/text54/compact52/btic51,
LATE_HIGH1, RESET1, FIX24, M5N and USB remain frozen.

## CI and identity authority

| Gate | Run | Verified result |
|---|---|---|
| Public PM-tail producer | `35620158321` | 38 new + 8 feasibility + 19 after-kfree + 5 linked tests, all executed; assembly/audit/fresh re-audit passed |
| Producer full suite | `35620158234` | 686 tests, 33 source/artifact skips |
| Private pack and independent-reverify | `35621265916` | Separate jobs both passed, identical complete reports |
| Public observer | `35624011702` | 15 dedicated + 38 base tests, all executed; actual pair agreement passed |
| Private observer provenance | `35624011695` | Authenticated source/run/job/artifact agreement passed |
| Observer full suite | `35624011687` | 701 tests, 33 source/artifact skips |

All 25 public workflows at the observer freeze passed. Required new skipped
source/artifact tests ran in the dedicated producer job. No local source tests,
source/binary audit tools, assembly or kernel/image build occurred. No kernel rebuild was
needed; existing bundle/FIX8 inputs were reused.

The active compositor executes the complete linked jump-table audit, carries
its current-run report at the pair root, and binds it through both manifests,
private reports, frozen identities and authenticated private provenance.
Standalone `__jump_table` section absence is not absence of folded metadata.
The inherited shared section parser was not changed.

Authority paths under `artifacts/slot-b-deferred-pm-tail-20260921/`:

- `public-audit-35620158321/`, `public-audit-run.json`
- `observer-35624011702/`, `observer-runs-cea1cd9.json`
- `private-pack-run.json`, `private-observer-run.json`
- `private-reverify-35621265916-identity.json`
- `device-round/`, especially both `result.json` and `events.json` files
- `closeout-public-runs.json`, `closeout-private-runs.json`

Use `scripts/slot_b/deferred_pm_tail_identities.json` for actual full image,
payload, report, public-pair and commit identities; never fill placeholders.

## Final device and retained artifacts

Fresh read-only closeout: host **2026-09-21T23:26:54Z**, thyme/M2102J2SC,
Android A (`_a`, boot_completed=1), root, stock 4.19.157 kernel, empty pstore,
battery 100%, 26 C. All 16 full boot-chain hashes and the P15 prefix matched
the pre-experiment baseline. Evidence:
`artifacts/slot-b-deferred-pm-tail-20260921/closeout-20260921T232654Z/`.
The closeout itself performed no reboot, slot selection or partition write.

Current B is **stock V14 vendor_boot/dtbo plus proven P15 recovery**, not the
old M5D test context. Its P15 prefix is 52,666,368 bytes, not the full boot_b
partition. Keep prefix and full-partition hashes distinct. The observation
endpoint is P15 Fastboot return, not the historical Android-A return endpoint.

Both already-tested 37,380,096-byte boot files were rechecked at closeout and
match the frozen full hashes. They remain in the private workspace:
`artifacts/slot-b-deferred-pm-tail-20260921/packed-35621265916/`.
Do not rebuild, re-download or rerun them. The original B backups and all old
artifacts/caches remain preserved.

During acquisition, the host's TUN route was slow and the configured local
HTTP proxy port refused connections. Four HTTP-range downloads and a bounded
remainder transfer recovered the same Actions ZIP. Its full hash matched
GitHub's archive digest; the extracted image hashes matched CI. This was
artifact acquisition, not local image packing or patching. Raw fragments,
archive, signed URL configurations and private observer receipts remain under
the private artifact root. Never publish signed URLs or OEM image files, and
never apply a local binary delta to manufacture a future candidate.

## Unfinished next step — not yet started

No after-lock script, workflow, draft, payload, boot image, identity freeze,
observer gate or device test exists. The filesystem was checked at closeout.
Only the proposal in the PM-tail result document and archived disassembly exists.

Investigate the original return boundary after `device_pm_lock()` at Image
`0x8de478`. SRCU BL is `0x8de46c`; PM-lock BL is `0x8de474`. A naive 56-byte
window leaves `0x8de4b0 -> 0x8de48c` entering its interior. The proposed 60-byte
window reaches the exact parent end `0x8de4b4` and would include that backedge.
This is a hypothesis for a safe window, **not a passed feasibility gate**.

When continuation is authorized:

1. Audit feasibility in Actions only: exact original 100-byte parent and
   196-byte worker/caller, source and original call targets, incoming edges,
   RELA/RELR, exception fixups and complete folded jump-label metadata.
   Reject naive 56 bytes; qualify any 60-byte footprint/padding and terminal
   closure explicitly. Preserve the original prefix and stack-frame semantics.
2. Only after that passes, qualify a new matched pair in Actions, then private
   pack plus fresh-job independent reverify, actual full identity freeze and
   public/private observer provenance and negative tests.
3. Only then consider one B-only RAM boot per new member with recovery and
   all hash checks between. No repeat of completed PMTAIL8/1.

A future positive result could prove the two original calls returned, not
persistent lock state, a valid SRCU index, PM movement, PM-tail return, bus
probe, culprit or `/init`. Do not call PM locking the root cause without
further evidence. A missing timing shift is not proof of non-execution.
Reuse kernel bundle `35040148509`, public FIX8 `34741153230` and private FIX8
boot `34744041027`; no need for a kernel rebuild has been established.

## Delegation and constraints

The same-model writer and retained retry failed on model-service rate-limit /
unknown response errors. Their partial diffs were preserved. The user then
explicitly approved direct parent takeover. No independent subagent review
completed; do not invent one. The failed/cancelled missions are terminal.
At closeout there are **no active subagents, artifact transfers, or relevant
public/private Actions runs**. Do not restart them for this handoff.

- All compilation, assembly, linking, kernel/DT/image generation, tests and
  executable source/binary validators are GitHub-Actions-only. No local build,
  actionlint/readelf/objdump/test execution or GITHUB_ACTIONS spoofing.
  Local artifact acquisition/integrity checks and the CI-qualified device
  observer do not authorize local image creation or bypassing CI qualification.
- Never flash, erase, format or destructively modify Slot A, firmware or
  protected vbmeta partitions. Parent alone operates the device, serialized.
- Reconfirm current-slot B immediately before every experimental RAM boot or
  permitted B write. Prefer RAM boot and preserve P15. Recover untouched A
  for read-only checks; compare all 16-chain/P15 hashes between members and
  stop on identity mismatch, anomalous return, or device loss.
- No deletion, reset/clean or discarded prior work. No blind driver disabling,
  deferred_probe_timeout changes, generic bus-entry probe or unqualified
  compact44 substitution. All existing frozen cases stay frozen.
- Device binary acquisition uses `adb shell -T`, never `adb exec-out su -c`
  because the latter has proven CR corruption in this environment.
- Subagents, if used on a later authorized continuation, default to the current
  session model. No silent model/CLI fallback. Keep a single device operator.

Current instruction: archive this state and stop for the conversation switch.
