# Xiaomi Mi 10S handoff — PM-tail metadata, 2026-09-21

Continuation supersedes this historical stop: PMTAIL8/1 are complete and
**DEFERRED_PM_TAIL_ENTRY_PROVEN**. Read `docs/slot-b-deferred-pm-tail.md` and
the current-status top before acting. Do not repeat the now-completed pair.

## Stop reason and current gate

The user requested complete closeout and a new conversation. Work is paused
intentionally, not completed and not blocked by a disconnected device. Do not
start another experiment until the user resumes the continuation.

Read this document, the top of `docs/route-r3-current-status.md`,
`docs/slot-b-deferred-after-kfree.md`, and the latest dated mem0 record under
`bzg-thyme-mainline`. Search rank is not chronological. The old 11:59 UTC
preflight-only memory predates already-completed AFTERFREE8/1: never rerun them.

- Latest physical boundary: **DEFERRED_REASON_KFREE_RETURN_PROVEN**.
- New static gate: **LINKED_JUMP_TABLE_PM_WORKER_SAFE**.
- PM-tail entry/return, bus/device/driver probe, culprit, late initcalls
  completion, `/init` and usable mainline Linux: **NOT_PROVEN**.
- USB: **FROZEN**. No new PM-tail image or device readiness exists.

## Workspaces and source authority

| Purpose | Repository / cwd | Branch and source state |
|---|---|---|
| Active public work | `ChuenSan/xiaomi10s`, `/Volumes/LinuxDev/thyme-mainline-slot-b-continuation` | `route-b-slot-b-continuation`; tested active source `00094b32ef511699be7e817cb5f13cdb58558e8a`; this document's commit is the later closeout |
| Private packing | `ChuenSan/thyme-mainline-private-ci`, `/Volumes/LinuxDev/thyme-mainline-private-ci` | `main`, unchanged `853ac9f300cf578a39efa744eccc58e670ebabd1` |
| Old dirty worktree — preserve | `/Volumes/LinuxDev/thyme-mainline` | historical `5550dc2`; original `.gitignore` and M3-document changes were not edited |

Active scripts/workflows are unchanged by the closeout documentation/draft
move. All owned active-source changes were committed and pushed:

- `d3e8ab0`: new folded jump-label audit, negative tests and isolated workflow.
- `00094b3`: narrowly handle the archived `.rodata` `WAMS` flag representation,
  with a regression using an actual readelf-format row.

No existing observer, image identity, DTS, kernel patch, shared binary helper,
private workflow or recovery image was changed. The worktree has no CodeGraph
index; do not create one or rescan the old indexed repository to resume.

## Physical results reconciled, not repeated

AFTERFREE8/1 had already run before this conversation, once each RAM-only in B:
35.193026708 / 28.421630667 seconds; delta -6.771396041, error +0.228603959:
**STRONG**. Both returned automatically to Fastboot B with retry count 7 to 6.
Android A and all 16-chain/P15 hashes were verified between and after them.
Authoritative results are under
`artifacts/slot-b-deferred-after-kfree-20260921/live-20260921T115757Z/`.

This proves the original list removal, `get_device()` return, reason-pointer
loads and `kfree()` return. It does not prove reference acquisition succeeded,
an allocation was freed, the reason-clearing store executed, worker unlock,
PM-tail entry, a particular device/driver probe, identity or root cause.
`LATEST_PROVEN_LATE_INDEX=54` remains unchanged. The prior second-flush pair's
no observed shift is not a claim of non-execution.

All ten completed deferred cases are **rerun-FORBIDDEN**: prequeue8/1,
postflush8/1, worker8/1, selected8/1 and afterfree8/1. Historical completed
entry/initcall pairs and frozen index55/text54/compact52/btic51 remain frozen.

This conversation performed **zero experimental boots, zero slot selections,
zero partition-image writes, zero Slot A writes and zero local builds or
executable source/binary validation**. Its device operations were read-only.

## New static evidence and the repaired coverage gap

Existing PM-tail feasibility `35603065440` at `16efb7f` had already passed
8 tests and identified `device_pm_move_to_tail` at Image `0x8de450`, size 100.
The original `PACIASP` can be retained with a proposed 56-byte terminal core
at `[0x8de454,0x8de48c)`. The sole direct caller is the original worker BL at
`0x8e84a0`. That earlier run generated no candidate and was not rerun here.

Independent read-only review found that the inherited section-based scanner
reported `__jump_table: ABSENT`, although linker symbols place 1,065 records
inside `.rodata`. The old result means no separately named section, not no
runtime jump-label metadata. This was a concrete missing check, not evidence
of a device fault or an actual overlap.

New active files:

- `scripts/slot_b/linked_jump_table_audit.py`
- `scripts/slot_b/test_linked_jump_table_audit.py`
- `.github/workflows/thyme-slot-b-linked-jump-table.yml`

The new audit resolves matching nm/System.map bounds, requires the complete
folded mapping and byte-exact ELF/Image/FIX8 table, checks the pinned relative
ABI/config, and decodes both signed-relative code and target fields. Both
instruction-write overlap and destination entry are checked over the complete
100-byte PM-tail parent and 196-byte worker. RELA/RELR writes overlapping the
table are rejected. It does not patch images or generate a kernel candidate.

| Receipt | Result |
|---|---|
| `35611491629` at `d3e8ab0` | Failed closed at `.rodata` flags, before table-record inspection; dedicated tests passed |
| `35613385810` at `00094b32ef511699be7e817cb5f13cdb58558e8a` | **PASS**: all 5 dedicated tests executed, actual binary audit passed |
| `35613385680` at the same source | **PASS**: 648 tests, 22 skipped |

The first failure was traced to shared `_flag_tokens`: it ignores letter groups
longer than three characters and therefore reports `alloc=False` for `WAMS`.
The fix is local to the new audit: require the archived raw readelf source and
exact `WAMS` flags. The shared parser was not changed and its limitation still
exists for other consumers. No address/identity/overlap gate was waived.

The 22 full-suite skips are 14 historical artifact-dependent tests, four
already-qualified after-kfree tests, three source-dependent PM feasibility
tests, and the new linked-table source test. The new source test ran in the
5-test dedicated job; prior dedicated jobs qualified the earlier groups.
The unvalidated PM-tail draft tests were **not** part of these 648 tests.

Exact passing table evidence:

- Image bounds `[0x1a97528,0x1a9b7b8)`, 17,040 bytes, 1,065 records.
- Table SHA256:
  `82b8114fdc566a524c09496766c44f1c6fa804272a379a028c2f1e9248af4733`.
- `include/linux/jump_label.h` SHA256:
  `3da4ded9cccf8a7538348b3aa9309367d01309c03069505b8751931030f7d87d`.
- Full agreement: **ELF_IMAGE_FIX8_EXACT**; protected code/target overlaps: **0**.

Use the committed CI JSON instead of reconstructing identities from prose:
`artifacts/slot-b-deferred-pm-tail-20260921/linked-jump-35613385810/audit/linked-jump/linked-jump-table.json`.
Sibling `run.json`, `full-suite-run.json`, downloaded tests, disassembly and
entry reports preserve the receipts. Failed evidence remains under
`linked-jump-35611491629/`; nothing was deleted.

This is additive metadata qualification only. The existing PM feasibility
script still uses the old standalone-section view. A new compositor must
explicitly invoke and bind the new linked-table gate before claiming readiness.

## Unfinished source — isolated, not qualified

Three previously untracked files were moved, without deletion, to
`docs/drafts/slot-b-deferred-pm-tail-20260921/`:
`deferred_pm_tail_probe.py`, `test_deferred_pm_tail_probe.py`, and
`thyme-slot-b-deferred-pm-tail.yml`. Its README describes the exact deficits.
They were never active in a committed CI source or dispatched as a workflow.
`docs/**` is ignored by generic Linux CI and these files are outside active
Actions loading and unittest discovery.

The draft targets new `defer_pmtail8/1` cases with no added pointer reads,
unchanged worker and a terminal PACIASP-plus-56-byte design. It freezes the
100-byte parent and the old five source-file hashes. **It does not yet invoke
or bind the newly qualified linked-table audit**, and its inherited metadata
still says the standalone jump section is absent. Do not dispatch it unchanged.

Missing stages, in order:

1. Integrate the linked-table gate and actual table/header identities into the
   new compositor, manifests and verification; distinguish standalone-section
   evidence from complete linked metadata. Complete focused negative tests and
   direct review, including all-worker provenance and terminal closure.
2. Qualify the new pair entirely in Actions: actual core assembly, complete
   source/binary audit and re-audit of downloaded/generated members. Reuse the
   existing kernel bundle; no reason for another kernel rebuild has been found.
3. Add a distinct private workflow, pack into the frozen envelope and require
   fresh-job independent verification. No private PM-tail workflow exists yet.
4. Freeze actual full boot/payload hashes and public/private commit/run
   identities, then implement and CI-test observer provenance, negative safety
   gates and conservative pair grading. No PM-tail observer identity exists.
5. Only after all gates and renewed user scope permit, consider one B-only RAM
   boot per new member, with healthy A restoration and all hash checks between.

A positive PM-tail pair could incrementally prove the original reason-clear
store, worker `mutex_unlock()` return and PM-tail entry. It would not prove
persistent field state, SRCU/PM-lock acquisition, PM-list movement, PM-tail
return, bus/driver probe, device identity, culprit, `/init` or USB. A generic
bus-entry or compact44 alternative remains outside the qualified design.

## Final read-only device state

Host timestamp **2026-09-21T14:46:13Z**. Device `41a5627b`, thyme/M2102J2SC,
healthy stock Android A (`_a`, boot_completed=1), root available, kernel
`4.19.157-perf-g9d90dd04aa7c`, empty pstore, battery 100%, temperature 26.5 C.
All 16 full boot-chain hashes and the first 52,666,368 bytes of `boot_b` match
the start-of-conversation snapshot and prior closeout. Current B remains stock
V14 vendor_boot/dtbo plus the proven P15 recovery boot.

Evidence:
`artifacts/slot-b-deferred-pm-tail-20260921/closeout-20260921T144613Z/`.
The P15 prefix hash is
`133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34`;
it is not the full boot_b partition hash. The initial fresh snapshot is
`resume-20260921T135341Z/`. Use host time; the device clock is not authoritative.

## Delegation and remaining infrastructure

The initial Codex `gpt-5.4` and `gpt-5.4-mini` children failed at model startup
with “not supported when using Codex with a ChatGPT account”; they produced no
review evidence. An explicitly reported same-protocol retry using this
session's registered `我的-responses/gpt-6-astra` succeeded. No CLI or foreground
fallback was used. Boundary/integration reviews and the focused linked-table
review are complete; no child remains running. The focused review preceded
the WAMS correction; final correction authority is direct source inspection
and passing Actions, not an invented later independent review.

All relevant public/private Actions jobs were complete at closeout; none were
queued or running. No job was dispatched by this closeout.

## Constraints carried forward

- All compilation, assembly, linking, kernel/DT/image generation, tests and
  executable source/binary validators run **only in GitHub Actions**. No local
  make/clang/dtc/objdump/readelf/actionlint/tests or GITHUB_ACTIONS spoofing.
- Never flash, erase, format, or destructively write **Slot A or firmware**.
  Parent alone operates ADB/Fastboot, serialized; reconfirm current-slot=b
  immediately before each experimental boot or any permitted B write.
- Prefer RAM boot and preserve P15. Restore healthy Android A and compare all
  16-chain/P15 hashes between tests; stop on anomalies. Selecting A for recovery
  is not permission to write its partition images.
- All completed experiments remain rerun-forbidden. LATE_HIGH1, RESET1, FIX24,
  M5N and USB stay frozen. Do not blindly disable drivers, change
  deferred_probe_timeout, or use rejected before/after-bus windows.
- No file/directory deletion, clean/reset, discarding artifacts or overwriting
  old modifications. OEM-derived images remain private. Binary acquisition
  uses `adb shell -T`, never `adb exec-out su -c` (known CR insertion).
- No placeholder/truncated production identities, generic `.text` waiver,
  bypassed provenance or unsupported mainline-success claim.
- Subagents are authorized when continuation resumes; keep clear read/write
  ownership and one device operator. Current instruction is closeout and stop.
