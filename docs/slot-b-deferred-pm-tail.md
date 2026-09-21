# Deferred worker PM-tail entry

Status: **DEFERRED_PM_TAIL_ENTRY_PROVEN**. PMTAIL8/1 completed once each,
RAM-only in Slot B. Both cases are now rerun-forbidden, alongside all ten
previous deferred cases. This advances the after-kfree result, not `/init`
or usable mainline Linux. USB remains frozen; latest proven late index is 54.

## Actual device result

| Member | Automatic Fastboot B return | Retry count |
|---|---:|---|
| `defer_pmtail8` | 35.580534792 s | 7 to 6 |
| `defer_pmtail1` | 28.447709084 s | 7 to 6 |

Delta: **-7.132825708 s**; error against -7 s: **-0.132825708 s**;
verdict: **STRONG**. This proves the original reason-clearing store executed,
the worker's `mutex_unlock()` returned, and `device_pm_move_to_tail()` was
entered. It does not prove persistent field state, SRCU/PM locking, PM-list
movement, PM-tail return, any bus/driver probe, device identity, culprit,
late-initcall completion, `/init`, or usable Linux.

The parent checked current-slot B immediately before each experimental boot.
No partition image was flashed. Existing Android A was restored after each
member; all 16 recorded boot-chain hashes and the 52,666,368-byte P15 prefix
matched before, between and after. Final stock Android A had root, completed
boot and empty pstore. B remains stock V14 vendor_boot/dtbo plus P15 recovery.

Device evidence: `artifacts/slot-b-deferred-pm-tail-20260921/device-round/`.
Final recovery snapshot: `after1-20260921T165802Z/`; subsequent full-hash checks
also matched. The first member's absolute time was not used as proof alone.

## Qualification

| Gate | Actions run | Source / result |
|---|---|---|
| Public composition and fresh re-audit | `35620158321` | `b01b9f6`; 38 new tests plus 8 feasibility, 19 after-kfree and 5 linked-table tests, all executed |
| Producer full suite | `35620158234` | 686 tests, 33 source/artifact-dependent skips |
| Private pack and fresh-job independent reverify | `35621265916` | private `4e7c641`; both passed, identical complete reports |
| Public observer and identity agreement | `35624011702` | `cea1cd9`; 15 dedicated and 38 base tests, all executed |
| Private observer provenance | `35624011695` | verified public observer checkout `cea1cd9` |
| Observer full suite | `35624011687` | 701 tests, 33 source/artifact-dependent skips |

All 25 public workflows at the observer freeze succeeded. The new tests skipped
in the general suite ran in the dedicated producer job. No kernel rebuild,
local compilation, assembly, image generation or local validator was used.
The terminal core was assembled in Actions. The complete linked jump-label
report is executed afresh, included at the public pair root, and bound through
manifests, private identity, observer freeze and authenticated private receipts.

Exact identities: `scripts/slot_b/deferred_pm_tail_identities.json`.
OEM-derived boot images remain only in the private workspace under
`artifacts/slot-b-deferred-pm-tail-20260921/packed-35621265916/`.
Their sizes and full SHA256 match the private Actions reports. Slow host
artifact transfer was recovered using HTTP ranges; the reconstructed download
matched GitHub's original archive digest. No image was locally rebuilt or
patched. Signed download URLs and raw transfer fragments remain private.

The delegated writer failed on model-service rate-limit/unknown errors; its
retained retry also failed. Partial diffs were preserved. The user explicitly
approved direct parent takeover. Final authority is parent source review and
actual Actions results, not a claimed completed independent subagent review.

## Next boundary

The archived disassembly places the original SRCU call at Image `0x8de46c`
and `device_pm_lock()` call at `0x8de474`. The next candidate is their return
boundary at `0x8de478`, before PM-list movement. A naive 56-byte window leaves
the original backedge at `0x8de4b0` entering its interior. A proposed 60-byte
window ending exactly at parent end `0x8de4b4` can include that backedge.
This requires an Actions-only feasibility audit before any new pair, packing,
identity freeze or device operation. It is not yet qualified or device-ready.
Do not alter or rerun the now-frozen entry pair, and do not substitute a generic
bus-entry probe or the unqualified compact44 alternative.
