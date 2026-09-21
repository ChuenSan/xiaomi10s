# Deferred worker after-kfree boundary

Status: public audit and private pack/fresh-job reverify passed. Full identities
are recorded in `scripts/slot_b/deferred_after_kfree_identities.json`. Observer
integration and private provenance gates are pending; no device test occurred.

| Gate | Actions receipt | Result |
|---|---|---|
| Public source, binary audit and independent re-audit | `35573581801` at `cc693ac6e92a587a0244cc18736a45346042ceab` | PASS; 19 tests, no skips |
| Same-source full suite | `35573581872` | PASS; 604 tests, 18 skips; four new artifact-dependent tests passed in the dedicated audit |
| Private pack and separate `independent-reverify` job | `35580754081` at `44fca85594faa1ebd6f21656602f37c4baa0e41e` | Both jobs PASS; identical complete identity reports |

The resumed defensive source/CFG and private workflow-contract reviews found
no blocking defect. Observer integration reuses the four-file `7c05a44` change;
it also binds the frozen boot hashes to authenticated private run/job receipts
and both identity reports. Registering the two new images requires 148
cross-identity rejections in each compact52/text54 observer gate. These observer
changes still require Actions qualification. No successful audit is rerun.

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
private observer gates remain required. Maximum programmed spin remains eight seconds;
neither the historical return cluster nor the host observation timeout proves
a hardware recovery deadline.

Proposed cases are `defer_afterfree8` then `defer_afterfree1`, one RAM-only
Slot B boot each after all gates. Restore healthy Android A and verify all
16 partition hashes and the 52666368-byte P15 prefix between members. Stop on
any anomaly. All eight completed deferred cases remain rerun-FORBIDDEN.
