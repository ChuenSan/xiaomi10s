# Deferred worker after-kfree boundary

Status: source implementation and independent review in progress. No candidate
is CI-qualified, identity-frozen, observer-qualified or device-tested yet.

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

The proposal requires fresh Actions source/opcode/window/full-parent incoming,
rewrite, RELA/RELR and exception-fixup checks, independent public re-audit,
private envelope packing and fresh-job re-verification, actual full identities,
and dedicated observer gates. Maximum programmed spin remains eight seconds;
neither the historical return cluster nor the host observation timeout proves
a hardware recovery deadline.

Proposed cases are `defer_afterfree8` then `defer_afterfree1`, one RAM-only
Slot B boot each after all gates. Restore healthy Android A and verify all
16 partition hashes and the 52666368-byte P15 prefix between members. Stop on
any anomaly. All eight completed deferred cases remain rerun-FORBIDDEN.
