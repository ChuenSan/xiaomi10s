# Slot B continuation — 2026-09-16

Source baseline: `5139927` on `route-b-v3-panic-entry-integration`.
The original dirty worktree at `5550dc2` and the previous integration worktree
are untouched. Work continues on `route-b-slot-b-continuation`.

## Reconciled progress

mem0's latest record is restart-chokepoint PREDEVICE completion. Repository
commit `5139927` and successful Actions runs additionally confirm its device
gate finalization: public `34988458482`, private pack `34987624341`, independent
reverification `34988018208`. These completed stages will not be rebuilt.
C_DELAY reachability is proven; panic-entry delay pair did not shift. Normal
`/init` and USB under mainline remain unproven. PANIC30/FIX24/M5N stay frozen.

## Why the existing observer cannot be used

`observe-r3-p1b-reset8.py` requires active slot A and measures automatic Android A
return. A bare change to active B is unsafe: PSCI reset would execute the old
M5D `boot_b`, which is not a recovery image. Its A-return timing model would also
be invalid. The new observer rejects A instead of relaxing that guard.

## Recovery context

The user authorized continuous, evidence-driven device testing, GitHub-Actions-
only builds, and B-only boot-partition writes. Before any write:

1. Read and preserve full B boot/vendor_boot/dtbo backups locally; verify the
   frozen M5D+M5H+M5M-B identities. Keep all backups, never delete them.
2. Record A boot/vendor_boot/dtbo/vbmeta/firmware hashes. Never write A, vbmeta,
   firmware, system, super, userdata, or erase/format anything.
3. Verify device identity, unlocked state, battery and snapshot state. Select B
   and re-read `current-slot=b` before **each** explicit `_b` flash.
4. Install the already Actions-built, device-proven stock P15 control in
   `boot_b`, with exact stock V14 vendor_boot/dtbo in B. This is a recovery
   context change, not a repeat of the old mainline experiments.
5. Boot the unchanged Android A only for readback, then compare every protected
   hash. Slot selection is not a flash. Return to B for all experiments.
6. Validate the recovery context once. P15 starts stock 4.19, sleeps 15 seconds,
   and issues `restart2("bootloader")`, without mounting user filesystems.

| B artifact | provenance | SHA256 |
| --- | --- | --- |
| P15 boot (52666368 bytes) | public Actions `34217537211` | `133e063b16e6b89d0493dd93de6c77f17b14f2baad59c5722e00b5442ea87d34` |
| stock vendor_boot | private release `stock-V14.0.6.0.TGACNXM-context` | `aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972` |
| stock dtbo | same private release | `018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634` |

## Reset pair on B

Reuse exact RESET8/RESET1 private artifacts; no local build, repack or patch.
Run RESET8 once, evaluate its real outcome, then run RESET1 once only if the
B recovery path and RESET8 record are valid. Each command is a RAM-only
`fastboot boot` with B verified immediately beforehand. Each reset is expected
to execute one **known recovery B boot**, distinct from the experimental boot.
The observer itself cannot flash or switch slots and rejects a second launch.

New primary endpoint: `Booting OKAY -> first stable Fastboot return`, including
the common P15 recovery path. Never compare these totals to old A-return totals.
The sole causal comparison remains `RESET1_TOTAL - RESET8_TOTAL`, expected
`-7s`; absolute error <=1s is STRONG, <=2s SUPPORTED. Invalid return, manual
recovery, wrong slot, changed context or artifact identity: no pair claim.
No shift reduces the `machine_restart` hypothesis, but cannot exclude all
Linux or firmware reset sources. A positive proves entry only, not the caller,
the original restart body or `/init` execution.

Observer tests and any subsequent image builds run only in GitHub Actions.
Local operations are source editing, downloads, hashing, read-only device
checks, explicitly B-gated flashing and observation. Serial/token/CPUID and
OEM binaries must not be committed or placed in public Actions artifacts.
