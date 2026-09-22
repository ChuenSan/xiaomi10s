# Deferred worker PM-lock return

Status: **DEFERRED_PM_LOCK_RETURN_STATIC_FEASIBLE**. Runtime remains
**DEFERRED_PM_TAIL_ENTRY_PROVEN**; no after-lock device experiment has run.
The user resumed continuation and explicitly approved parent takeover after
the t-grok-4.7/xhigh writer timed out without producing any source files.
No independent subagent review completed. Evidence is parent review plus Actions.

## Static qualification

Actions `35671827755`, source `f09a011b39088a61942b4a8a9db67ee3ca099f22`,
passed 12 new tests and 70 inherited tests, all executed. Two fresh audit
processes produced identical reports. Full suite `35671827678` passed
713 tests with 36 source/artifact-dependent skips; required new source tests
ran in the dedicated job. No local tests, assembly or binary audit ran.

The original return boundary is Image `0x8de478`, immediately after the
`device_pm_lock()` BL at `0x8de474`; the original SRCU BL is `0x8de46c`.
The exact 100-byte parent and 196-byte worker match ELF/Image/FIX8. The sole
worker caller, original call targets, full-function incoming/literal/symbol,
RELA/RELR, exception and rewrite gates passed. All 1,065 folded jump-label
records were checked afresh against both complete functions.

The 56-byte suffix is rejected: it leaves `0x8de4b0 -> 0x8de48c` entering
the overwrite window. The qualified **prospective** footprint is 60 bytes,
ending exactly at `0x8de4b4`: the existing 56-byte terminal core plus an
unreachable 4-byte NOP. The original 40-byte prefix and its 32-byte stack
frame remain unchanged. The frame is intentionally left outstanding on the
terminal reset/WFE path. This audit generated no candidate or boot image.

Reference report:
`artifacts/slot-b-deferred-pm-lock-20260922/feasibility-35671827755/pm-lock/feasibility.json`.
Downloaded-file SHA256:
`f647c436b71fc86dccf11d69db5c2a6f00a70f61498f4500c767e5c6e5f6e567`.
Run receipts and test logs are retained in the same evidence root.

## Next gate and limits

Next: Actions-only composition and fresh re-audit of a new after-lock 8s/1s
pair, then private packing and fresh-job verification, actual identity freeze,
and public/private observer qualification. No after-lock device readiness is
claimed. Reuse the existing bundle/FIX8 inputs; no kernel rebuild is needed.

A positive new pair could prove the two original calls returned. It would not
prove persistent lock state, a valid SRCU index, PM-list movement, PM-tail
return, bus/driver probe, device identity, culprit, late completion or `/init`.
USB and all historical completed/frozen experiments remain frozen.

Current B remains stock V14 vendor_boot/dtbo plus P15 recovery. No partition
image writes, slot selections or experimental boots occurred in this static
round; Slot A remains protected. New tests must be RAM-only in confirmed B,
with healthy Android A recovery and all 16-chain/P15 checks between members.
