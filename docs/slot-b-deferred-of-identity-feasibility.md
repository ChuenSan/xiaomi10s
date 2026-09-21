# Deferred OF identity feasibility

Actions run `35569628684` at
`5db47d6a72d26f98251755c28dbcc2ca9cdff935` verified the immutable kernel audit
bundle `35040148509` and FIX8 payload `34741153230`. Its report is
`COMPILER_OFFSETS_AND_RT_D_MAP_PROVEN`; 24 rejection/layout tests passed.
No kernel rebuild, candidate image, added runtime read or device operation
occurred.

## Compiler evidence

LLVM 18 read the original ELF DWARF, including every named definition and its
direct members. Complete definitions agreed; none was rejected or conflicting.

| Type | Structure bytes | Complete definitions | Member byte offsets |
|---|---:|---:|---|
| `device` | 784 | 3006 | `of_node`: 672 |
| `device_node` | 208 | 1703 | `phandle`: 8; `full_name`: 16 |

These are compiler-reported offsets, not manually inferred C layouts. Member
value widths and referenced type chains were not extracted and remain
unqualified. The `full_name` offset does not establish a runtime absolute path.

## Frozen DT map

The exact RT-D trailer contains 919 nodes: 531 unique nonzero phandles and
388 nodes without a phandle property. No explicit zero, conflicting alias,
reserved handle, duplicate handle, path or property was accepted. Each mapped
handle records an absolute DT path, compatible strings and original status.

A mapped handle identifies a DT-node association. It does not uniquely identify
a Linux device, establish which device is first at runtime, or identify a
faulty driver. A runtime zero cannot distinguish an absent phandle property
from an explicit zero. `dev->of_node` can be null, shared or reassigned.

## Remaining gates

Any future identity probe still needs actual load-width/type resolution,
pinned-source lifetime and initialization evidence, exact assembled/read/window
validation, a coherent predicate and calibrated decoder, private verification,
frozen identities and observer gates. Cross-boot name/handle fragments cannot
be combined into an observed identity. A complete full-handle equality checked
independently in each boot is a possible future predicate, not a qualified
channel.

The immediate diagnostic being prepared is the original worker's after-`kfree`
boundary, which adds no new dereference. See
`docs/slot-b-deferred-after-kfree.md`. The selected8/1 and six earlier deferred
cases remain rerun-FORBIDDEN.

Evidence: `artifacts/slot-b-deferred-of-20260921/`. Full report, DT map,
tool receipts, test log and artifact metadata are retained. The 71435888-byte
raw DWARF text is retained locally and in the CI artifact
`thyme-deferred-of-identity-forensic`; it is not added to Git. The CI artifact
receipt records its download authority. No OEM data is part of this audit.

The host-timed read-only device check at `2026-09-21T06:27:45Z` found healthy
Android A, empty pstore and unchanged 16-chain/P15 hashes. No experiment was
performed during that check.
