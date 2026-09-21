# Deferred worker selected-device boundary

Continuation of the 2026-09-21 worker-entry proof. The six completed deferred
cases remain frozen. This is a new terminal diagnostic, not a normal boot fix.

## Why this boundary

The worker starts, but mutex acquisition, a nonempty active list and selection
of a device are not yet proven. Existing CI disassembly places
`ldr x20, [x8, #0x20]` at Image `0x8e8464`, before list removal and
`get_device()`. A new 56-byte terminal 8/1-second pair starts at `0x8e8468`.
It adds no device or name dereference. A positive matched pair proves the
source-audited prefix through this load; it does not establish pointer validity,
a device name, `get_device()` or `bus_probe_device()` execution, or a culprit.

The original empty-list branch `0x8e8454 -> 0x8e84c8` bypasses the entire
`[0x8e8468,0x8e84a0)` window. The retained loop backedge targets `0x8e8460`,
before the hook. The terminal core cannot execute the original suffix: it
resets through PSCI or remains in its local fallback loop. The full 196-byte
parent and unchanged prefix/suffix must match pinned ELF, Image and FIX8.

## Name draft remains unqualified

Independent source review found that `device_rename()`/`kobject_rename()` can
replace and free `kobj.name` without the deferred-list mutex. The mutex's
device-lifetime argument does not pin that separate allocation. This is an
unclosed safety proof, not evidence of a rename on thyme.

The proposed nibble symbols and invalid marker are only one second apart.
The existing pair channel accepts a one-second error for STRONG; observed
Fastboot timing does not provide a hard jitter bound. Calibration cannot prove
that the same device is first across boots, and separate fragments cannot be
combined into an observed name without a coherent identity check. The draft
under `drafts/slot-b-deferred-name-20260921/` remains unassembled and unqualified.

## Qualification and interpretation

The dedicated selected-device workflow must verify exact original and assembled
opcodes, source order, whole-code incoming branches, symbol/section bounds,
relocations, runtime rewrites, exception fixup destinations, immutable payload
and RT-D/initramfs identity. The pair may differ only in its 8/1 delay encoding.
Private packing and a fresh-job verification must preserve every boot-envelope
byte outside the selected window. Full identities and a dedicated observer
gate are required before either new case can run.

Device order is `defer_selected8`, healthy Android A recovery and all 16-chain
plus P15 hash checks, then `defer_selected1`, followed by the same recovery.
Both require last-moment Slot B confirmation and one RAM boot only. Any anomaly
stops testing. A no-shift result remains NOT_PROVEN, not proof of an empty list.
Late initcalls completion, console, `/init` and usable Linux remain unproven;
USB remains frozen. No local build or source/binary validator is permitted.

Initial continuation check at `2026-09-21T03:54:16Z`: healthy Android A,
root available, pstore empty, all 16 partition hashes and the P15 prefix equal
the previous closeout. Evidence is retained under
`artifacts/slot-b-deferred-selected-20260921/device-round/pre-*`; no experiment was
performed during this check.

## CI identities

Public audit and independent re-audit `35564673598` passed at
`867cf8a7bf7ae90c7b80eb5265515f6e546c944a`. Full-suite run `35564673558`
passed 549 tests with 14 existing source-dependent skips. Actual assembly has
no relocations; the complete worker's rewrite, relocation, direct-entry and
exception-fixup gates passed.

Private run `35565769017` at `5d7c8fe4ae7fd3bb539a12d72457f9c5e37376cb`
passed packing and a fresh-job verification of downloaded images. Both boot
images are 37380096 bytes and differ only at the two delay-encoding bytes.
Authoritative full identities are in
`scripts/slot_b/deferred_selected_identities.json`; they were populated from
the CI receipts. OEM images remain under the private repository's local
`artifacts/slot-b-deferred-selected-20260921/packed/` directory.

The selected observer must pass its own Actions gate before either image is
used. No selected-device experiment is implied by these CI results.

## Actual selected-device result

Both new members ran exactly once as RAM-only Slot B boots:

| Case | Total seconds | Return |
|---|---:|---|
| `defer_selected8` | 35.420613167 | automatic Fastboot B, retry 7 to 6 |
| `defer_selected1` | 28.249236500 | automatic Fastboot B, retry 7 to 6 |

Delta is **-7.171376667 seconds**, error **-0.171376667 seconds**, **STRONG**.
The deferred mutex was acquired, the active list was nonempty, and the original
first device-pointer load completed. These two cases are now **rerun-FORBIDDEN**.
`LATEST_PROVEN_LATE_INDEX` remains 54. Device identity, pointer validity,
`get_device()`, `bus_probe_device()`, a culprit, late completion and `/init`
remain NOT_PROVEN; USB remains frozen.

The final selected observer gate was `35566868731` at
`2afa061035be58849dfbcf57add5bbf11d85687a`. It reconciled full public identities
and passed selected safety/negative tests. Earlier observer gate `35566401493`
also passed. Full suite `35566401477` passed **561 tests, 14 skipped**.
Two historical workflow checks (`35566401465`, `35566401486`) initially failed
because they required 140 cross-identity rejections after the registry grew to
144. All actual rejection fixtures passed. The count correction also explicitly
requires rejection of both selected images; replacement runs `35566808357` and
`35566808348` passed. No old experiment was repeated.

Android A was restored after each member. At **2026-09-21T06:19:28Z**, serial
`41a5627b`, thyme/M2102J2SC, `_a`, boot completed, stock kernel and root were
healthy; pstore was empty. All 16 full partition hashes and the 52666368-byte
P15 prefix matched before, between and after the pair. Current B remains
stock V14 vendor_boot/dtbo with P15 boot. This continuation used **2 RAM boots,
0 partition image writes, 0 Slot A writes, 0 local builds**.

Evidence is under `artifacts/slot-b-deferred-selected-20260921/`; OEM boot
images remain outside the public worktree in the private repository directory.
The root operator sourced `--ci-run` from the frozen identity JSON and checked
the first record's run and full SHA before permitting the second. Shared
observer `ci_run` is a record label rather than a live CI-authority lookup.

The next feasibility investigation is compiler-produced `device.of_node` /
`device_node.phandle` layout and a full phandle map from the exact RT-D trailer.
Static OF nodes avoid the separate kobject-name allocation's rename lifetime
gap, but absent/zero phandles, shared nodes and cross-boot selection still need
explicit treatment. No new identity-channel experiment follows from this
source-level possibility alone.
