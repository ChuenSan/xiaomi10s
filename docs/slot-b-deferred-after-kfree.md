# Deferred worker after-kfree boundary

Status: the RAM-only Slot B pair is **COMPLETE**, with a **STRONG** timing
shift. Gate: `DEFERRED_REASON_KFREE_RETURN_PROVEN`. Both `defer_afterfree8`
and `defer_afterfree1` are now **rerun-FORBIDDEN**, along with the eight earlier
deferred cases. Full identities remain in
`scripts/slot_b/deferred_after_kfree_identities.json`; no candidate was rebuilt.
The 11:59 UTC mem0 snapshot and the earlier preflight-only handoff predate
these results. The resumed continuation reconciled the existing raw records
rather than repeating either boot.

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
the original device-pointer load. The after-kfree terminal pair starts at
Image `0x8e848c`, immediately after the original `kfree()` call at `0x8e8488`.
Its 56-byte window ends at `0x8e84c4`, before the empty-list target `0x8e84c8`.

The original 196-byte `deferred_probe_work_func` prefix and suffix are retained.
There is no extra pointer/name read or branch retarget. The original empty
branch bypasses the complete window. The retained backedge at `0x8e84c4` is
unreachable from the terminal timer/PSCI/local-WFE core.

The STRONG pair proves the original path through `list_del_init()`, return
from `get_device()`, the original deferred-reason pointer loads and return
from `kfree()`. The worker ignores `get_device()`'s return value: successful
reference acquisition, a non-null reason and an allocation actually freed are
not proven. The reason field's clearing store, mutex unlock, PM-list movement,
bus/device probe, identity, culprit, late completion and `/init` remain unproven.

The completed Actions audit covers source/opcode/window/full-parent incoming,
rewrite, RELA/RELR and exception-fixup checks, independent public re-audit,
private envelope packing and fresh-job re-verification. Dedicated public and
private observer gates also passed. Maximum programmed spin remains eight seconds;
neither the historical return cluster nor the host observation timeout proves
a hardware recovery deadline.

## Completed device pair (2026-09-21)

| Member | Automatic Fastboot return | Final state |
|---|---:|---|
| `defer_afterfree8` | 35.193026708 s | B, retries 7 to 6, one RAM boot |
| `defer_afterfree1` | 28.421630667 s | B, retries 7 to 6, one RAM boot |

Delta is -6.771396041 s, error +0.228603959 s against the -7 s expectation:
**STRONG**. Each raw event log records Android-A origin, last-moment B preflight,
Sending/Booting OKAY, disappearance and automatic return. Healthy Android A
and unchanged 16-chain/P15 hashes were verified between members and after both.
The pair used two RAM boots, zero partition-image writes and zero Slot A writes.
Current B remains the P15 recovery boot with stock V14 vendor_boot/dtbo.

Raw evidence: `artifacts/slot-b-deferred-after-kfree-20260921/live-20260921T115757Z/`.
A fresh read-only reconciliation at host `2026-09-21T12:45:38Z` again found
healthy stock Android A/root, empty pstore, all 16 full partition hashes and
the 52666368-byte P15 prefix unchanged. It is stored in the sibling
`reconcile-20260921T124538Z/`. The reconciliation itself performed no reboot,
slot selection or partition write. Source and raw-event reviews agreed with
the limited proof above; neither review substitutes for CI or device evidence.

## Exact continuation

PM-tail feasibility `35603065440` is complete: original `device_pm_move_to_tail()`
entry at Image `0x8de450`, size 100, sole direct worker caller `0x8e84a0`.
The later linked jump-label audit `35613385810` closed a concrete coverage gap:
1,065 records folded into `.rodata`, exact ELF/Image/FIX8 agreement, no protected
PM-tail/worker rewrite or destination overlap. The shared section-only scanner
still cannot represent that folded table; new candidates must explicitly invoke
`scripts/slot_b/linked_jump_table_audit.py` rather than inherit an `ABSENT` claim.
No new PM-tail candidate or device readiness exists. The unqualified draft is
isolated under `docs/drafts/slot-b-deferred-pm-tail-20260921/`.
Read `docs/handoff-2026-09-21-pm-tail-metadata.md` for the current stop state and
remaining compositor/private/observer gates. Do not use an unqualified generic
`bus_probe_device()` entry: other callers would not prove this worker's progress.

Qualification receipts remain under `artifacts/slot-b-deferred-after-kfree-20260921/`.
OEM images remain at
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
