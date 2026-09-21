# Slot B deferred-probe callsite isolation

Continuation from `e8862d3` (2026-09-21). The user authorizes continued,
evidence-driven CI and necessary Slot B tests. Existing completed pairs stay
frozen; no local build, no Slot A write, no partition write is needed here.

## Causal question

Index 54 `deferred_probe_initcall` entry is PROVEN. Index 55's matched pair
showed no delay shift; that is not proof of non-execution. The source at
Linux 6.6.156 `drivers/base/dd.c:343` enables deferred probes, triggers and
flushes the work twice, then optionally schedules the timeout worker.
The existing public run `35520679000` includes its full disassembly.

The next fixed callsites use the frozen FIX8 payload, not a kernel rebuild:

| Case | Image offset | Boundary | Positive matched-pair evidence |
|---|---|---|---|
| `prequeue` | `0x8e7614` | first inlined trigger, after `mutex_unlock`, before `queue_work_on` | deferred enable, mutex and first list splice returned |
| `postflush` | `0x8e76b8` | immediately after second `flush_work` | both deferred-work flushes returned |

Each replaces exactly 56 bytes with the existing terminal elapsed-CNTPCT/PSCI
core. Neither touches the frozen entry window `[0x8e7564,0x8e75a0)` nor the
alternative-instruction sites `0x8e75b4` / `0x8e764c`. The exception is scoped
to these two literal body windows of the already-audited index-54 parent;
there is no global `.text` policy switch, trampoline or PREL32 retarget.
All normal instructions preceding the chosen window remain unchanged.

## Gates and interpretation

GitHub Actions checks pinned ELF/Image/config/base payload identity, source
ordering, the table registration, exact callsite bytes, predecessor BL target,
whole-code incoming branches, symbol/section/extent boundaries, literals,
relocations, runtime rewrite overlap, RT-D and the existing builtin initramfs.
The single known parent string-address delta is allowed only at `+0x1c`, +8
bytes, with identical referenced string content. Candidate windows are exact.
A fresh audit re-verifies both pair members; they differ only in the two bytes
encoding the 8-second versus 1-second delay. Original PAC prologue and frame
remain intact; the probe never returns or executes the original suffix.

Private Actions uses the frozen FIX8 boot envelope, changes only the selected
56-byte kernel window, checks the extracted payload, and independently
re-verifies the downloaded boot pair. OEM-derived images remain private.
The device observer must freeze exact SHA identities and pass Actions fixtures
before either member executes. Each starts from healthy Android A, selects B,
checks B immediately before RAM boot, executes once, then returns to healthy A
and rechecks the 16-chain hashes and P15 prefix. A is never flashed.

Order: prequeue 8/1, then postflush 8/1 only if the first pair is valid and the
device remains healthy. A positive pair is a boundary proof, not proof of USB
or `/init`. A negative pair narrows the investigation without assigning a root
cause. Any no-return/transport anomaly stops device execution for recovery.

## Actual results (2026-09-21)

Public audit/reverify `35553769346` @ `d3e0668` passed both windows. Private
pack + independent reverify: prequeue `35554007042`, postflush `35554009619`
@ private `dc1f800`. Freeze `7921561`; observer identity agreement
`35554398477` PASS. All 22 workflows triggered by the freeze passed, including
the full 526-test suite. The first integration failure was a unit fixture
requiring an unchecked-out submodule; `0eef215` made that fixture standalone.
The production audit still checks the actual pinned Linux source. Public
re-audit `35553891868` also passed after this test-only correction.

| Case | Total seconds | Return | Pair verdict |
|---|---:|---|---|
| `defer_prequeue8` | 35.423422125 | automatic Fastboot B, retry 7→6 | first member |
| `defer_prequeue1` | 28.465627750 | automatic Fastboot B, retry 7→6 | STRONG, delta −6.957794375, error +0.042205625 |
| `defer_postflush8` | 48.591122792 | automatic Fastboot B, retry 7→6 | first member |
| `defer_postflush1` | 48.346502500 | automatic Fastboot B, retry 7→6 | SHIFT_NOT_OBSERVED, delta −0.244620292 |

The first inlined deferred trigger's mutex/list-splice/unlock prefix is now
PROVEN. The interval of interest is `[0x8e7614, 0x8e76b8)`: first work enqueue,
first flush, the second trigger, and second flush. This does not yet identify
a particular worker/driver or establish that the second flush never executes.
Changing `deferred_probe_timeout` is not a justified fix: the timeout worker
is scheduled only after this unproven interval.

Every member ran exactly once from healthy Android A, with last-moment B
confirmation; all four are now rerun-FORBIDDEN. Android A was restored after
each member, with the 16-chain hashes and P15 prefix unchanged. No no-return,
manual recovery, partition write, Slot A write, local build or local binary
validator occurred. A host preflight pipeline initially stopped with SIGPIPE
before B selection; inspection confirmed Fastboot A and no experimental boot,
then the same read-only check was completed without an early-closing pipeline.

`LATEST_PROVEN_LATE_INDEX=54`; late completion, initramfs wait, console and
`/init` remain NOT_PROVEN. USB remains FROZEN. Evidence is under
`artifacts/slot-b-deferred-probe-20260921/`; identities are independently
transcribed in `scripts/slot_b/deferred_probe_identities.json`. Next action is
an Actions-only disassembly/geometry audit of the deferred worker and workqueue
path before selecting another causal checkpoint or intervention.

## Worker follow-up

Forensic run `35555269943` PASS: `deferred_probe_work_func` is 196 bytes at
`0xffff8000808e8424`. Its original `paciasp` can be preserved with a 56-byte
terminal core at `0x8e8428`; this interval is byte-exact, has no incoming
branch, and is disjoint from all runtime rewrite sites. The loop back edge
lands at `0x8e8460`, exactly after the proposed window. By contrast, naive
56-byte probes immediately before/after `bus_probe_device` are REJECTED:
the empty-list branch at `0x8e8454` enters their interior at `0x8e84c8`.
Those rejected windows are not candidates and must not be flashed or booted.

The next fixed `worker` pair therefore observes the first workqueue callback
activation, before it locks the list. Source requires the single deferred
work registration and the enable flag's sole assignment in late index 54.
This is a separate, literal callback-scoped `.text` diagnostic, not a global
policy relaxation and not an initcall-table replacement. It proves worker
entry only; it does not prove that the list is nonempty or any device probe
runs. The public workflow now generates only the selected new target, never
automatically regenerating the completed prequeue/postflush pairs.

## Worker device result and user-requested closeout

Worker public audit/reverify `35555866440` @ `c16c515` and private pack +
independent reverify `35556073389` @ `52e88c4` passed. Observer freeze `06a1d79`
and gate `35556276869` passed; all 22 workflows at that freeze succeeded,
including 526 tests (14 source-dependent tests skipped in the no-submodule job).

`defer_worker8` ran once: 35.517175625 s. `defer_worker1` ran once:
28.475640458 s. Delta −7.041535167 s, error −0.041535167 s → **STRONG**,
`DEFERRED_WORKER_ENTRY=PROVEN`. Both automatically returned to Fastboot B,
retry 7→6. Android A was restored after each, with all 16 hashes and P15
prefix unchanged. These two cases are now also rerun-FORBIDDEN. Callback
entry does not prove a device was selected or that queue_work_on returned;
the callback and submitter run concurrently.

The user then requested a conversation switch. The final read-only device
check at 2026-09-21T03:28:50Z still shows healthy Android A, root, empty pstore
and unchanged hashes. Total this continuation: six RAM boots, zero partition
writes, no Slot A write, no local build. Mainline `/init` remains NOT_PROVEN.

The unfinished name-channel proposal was moved, without deletion, to
`drafts/slot-b-deferred-name-20260921/`. It has no CI qualification, packed
images, frozen identities, decoder or device result. It is outside active
source/test discovery and must not be treated as ready. Full continuation
instructions: `docs/handoff-2026-09-21-deferred-probe.md`.
