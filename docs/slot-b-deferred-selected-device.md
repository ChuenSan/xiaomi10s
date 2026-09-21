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
`artifacts/slot-b-deferred-name-20260921/device-round/pre-*`; no experiment was
performed during this check.
