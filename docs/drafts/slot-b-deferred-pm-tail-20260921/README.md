# PM-tail pair draft — not qualified

Moved here without deletion for the user-requested 2026-09-21 handoff:

- `deferred_pm_tail_probe.py`
- `test_deferred_pm_tail_probe.py`
- `thyme-slot-b-deferred-pm-tail.yml`

These files were never committed in active script/workflow locations, executed,
assembled, validated by CI, packed, identity-frozen, observer-registered or
used on the device. They are outside unittest discovery and Actions workflow
loading. The `docs/**` path is also ignored by generic Linux build CI.

The proposed new cases are `defer_pmtail8/1`, stage `pm_tail`, preserving
PACIASP at Image `0x8de450` and placing the established terminal 56-byte core
in `[0x8de454,0x8de48c)`. The complete 100-byte parent and unchanged 196-byte
worker are constrained. No PM-tail boot image exists.

**Do not dispatch this draft workflow or treat these files as ready.** In
particular, the compositor does not yet invoke the newly qualified
`linked_jump_table_audit.py`. Its inherited `runtime_rewrites.__jump_table`
value describes only the missing standalone section, not the real folded
1,065-record table. The source/manifest contracts also do not yet incorporate
the new jump-label source/table identities. Copying this draft directly into
active locations would omit a known required gate.

Next work must integrate the passing linked-table audit and actual identities,
complete the manifest/pair and negative-fixture coverage, and review the full
new compositor. Only then qualify it through Actions, private pack plus a
fresh-job independent verification, actual identity freeze and observer gates.
No private PM-tail workflow or observer implementation was created this round.

Read `docs/handoff-2026-09-21-pm-tail-metadata.md` first. Completed afterfree and
all older device cases remain rerun-forbidden. Builds and executable validation
remain GHA-only; Slot A and firmware remain protected.
