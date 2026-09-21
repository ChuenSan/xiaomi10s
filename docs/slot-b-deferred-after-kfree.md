# Deferred worker after-kfree boundary

Status: public audit, private pack/fresh-job reverify, observer and private
provenance gates passed. Full identities are recorded in
`scripts/slot_b/deferred_after_kfree_identities.json`. The user requested a
conversation handoff after qualification. Neither after-kfree member was
device-tested. Gate: `AFTER_KFREE_READY_FOR_LIVE_PREFLIGHT`.

| Gate | Actions receipt | Result |
|---|---|---|
| Public source, binary audit and independent re-audit | `35573581801` at `cc693ac6e92a587a0244cc18736a45346042ceab` | PASS; 19 tests, no skips |
| Same-source full suite | `35573581872` | PASS; 604 tests, 18 skips; four new artifact-dependent tests passed in the dedicated audit |
| Private pack and separate `independent-reverify` job | `35580754081` at `44fca85594faa1ebd6f21656602f37c4baa0e41e` | Both jobs PASS; identical complete identity reports |
| Public observer and full identity agreement | `35590309126` at `573ccee87bf658b618bab2c579df81483ed54734` | PASS; 31 dedicated and 38 base tests, no skips |
| Authenticated private observer provenance | `35590327114` at private `853ac9f300cf578a39efa744eccc58e670ebabd1` | PASS; verified observer checkout is `573ccee87bf658b618bab2c579df81483ed54734` |
| Integrated full suite | `35590309460` at `573ccee87bf658b618bab2c579df81483ed54734` | PASS; 635 tests, 18 artifact/source-dependent skips |
| Compact52/text54 regressions | `35590309306` / `35590309163` | PASS; 148 cross-identity rejections each |

The resumed defensive source/CFG and private workflow-contract reviews found
no blocking defect. Observer integration reuses the four-file `7c05a44` change;
it also binds the frozen boot hashes to authenticated private run/job receipts
and both identity reports. Registering the two new images requires 148
cross-identity rejections in each compact52/text54 observer gate. All 24 public
workflows triggered at the observer freeze passed. No successful candidate
audit or pack was rerun; no local validator, build or binary audit was executed.

The selected-device pair proved mutex acquisition, a nonempty active list and
the original device-pointer load. The next proposed terminal pair starts at
Image `0x8e848c`, immediately after the original `kfree()` call at `0x8e8488`.
Its 56-byte window ends at `0x8e84c4`, before the empty-list target `0x8e84c8`.

The original 196-byte `deferred_probe_work_func` prefix and suffix are retained.
No extra pointer/name read or branch retarget is proposed. The original empty
branch bypasses the complete window. The retained backedge at `0x8e84c4` is
unreachable from the terminal timer/PSCI/local-WFE core.

A strong new 8/1-second pair would support only the original path through
`list_del_init()`, return from `get_device()`, the original deferred-reason
pointer loads and return from `kfree()`. The worker ignores `get_device()`'s
return value, so this must not be described as successful reference acquisition.
The reason field's clearing store, mutex unlock, PM-list movement, bus/device
probe, identity, culprit, late completion and `/init` remain unproven.

The completed Actions audit covers source/opcode/window/full-parent incoming,
rewrite, RELA/RELR and exception-fixup checks, independent public re-audit,
private envelope packing and fresh-job re-verification. Dedicated public and
private observer gates also passed. Maximum programmed spin remains eight seconds;
neither the historical return cluster nor the host observation timeout proves
a hardware recovery deadline.

Proposed cases are `defer_afterfree8` then `defer_afterfree1`, one RAM-only
Slot B boot each after all gates. Restore healthy Android A and verify all
16 partition hashes and the 52666368-byte P15 prefix between members. Stop on
any anomaly. All eight completed deferred cases remain rerun-FORBIDDEN.

## Exact continuation

Next stage: `MAINLINE_V2_R3_SLOT_B_DEFERRED_AFTER_KFREE_TRUE_DEVICE_PAIR`.
Read latest mem0, this document and current Git/CI state first. Refresh the
live Android A identity/health, all 16 full partition hashes and P15 prefix;
then use the qualified observer with the frozen private run `35580754081`.
Execute `defer_afterfree8` once, restore healthy A and verify all hashes, then
permit `defer_afterfree1` once only with a valid first-member result. Each
member requires Android-A ADB origin, B selection, last-moment B validation,
automatic Fastboot B return and retry 7 to 6. No partition image write is needed.

Last complete read-only snapshot: host `2026-09-21T09:55:36.387084+00:00`,
healthy stock Android A, root available, empty pstore, all 16 hashes and P15
prefix unchanged. This continuation performed no reboot, slot selection or
experimental boot. Refresh this historical snapshot before a future boot.

Evidence: `artifacts/slot-b-deferred-after-kfree-20260921/`, including final
public run receipts, public/private observer logs, full suite, regressions and
the read-only device snapshot. OEM images remain at
`/Volumes/LinuxDev/thyme-mainline-private-ci/artifacts/slot-b-deferred-after-kfree-20260921-pack/`.

The source-only possibility of a bare compact44 probe after `mutex_unlock` at
`[0x8e849c,0x8e84c8)` is not qualified or authorized by this stage. It would
replace the original backedge and remove DAIFSet/ISB/WFE from the diagnostic
core. That is an experiment-boundary change requiring separate explicit
authorization and new gates; it must not be treated as an automatic next boot.

DTS/config review found no frozen-baseline drift. UFS and some USB PHY drivers
remain modules in the archived config, while the minimal `/init` does not load
modules. This limits later hardware usability but does not establish the
current deferred-device cause or justify changing the frozen baseline.
