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

## Executed results

Public observer safety CI `35031615785`, source `ddd09bc`, passed all seven
original tests. The downloaded CI source-hash manifest matched the locally
executed observer. Neither a local compilation nor local image generation ran.

B backup/readback found real partition sizes: boot 201326592, vendor_boot
100663296, dtbo 33554432 bytes. Full original backups are retained under
`.cache/slot-b-continuation/device-before/` and match their on-device hashes.
The first boot backup was quarantined, not deleted: `adb exec-out su -c`
inserted 420768 CR bytes before LF (201747360 instead of 201326592 bytes).
A newline probe demonstrated the transport fault; `adb shell -T` preserved
bytes, and a fresh acquisition matched the device's full SHA256.

Only `vendor_boot_b`, `dtbo_b`, and `boot_b` were flashed, each after an explicit
`current-slot=b` check. Subsequent readback matched all three intended images.
The following protected partitions matched their before-write hashes:
A boot/vendor_boot/dtbo/vbmeta/vbmeta_system/abl/xbl/tz, and
B vbmeta/vbmeta_system/abl/xbl/tz. No A partition was written.

### P15 recovery control

At `2026-09-15T22:42:23.949Z`, one ordinary B recovery-control boot started.
Fastboot disappeared and returned automatically after **25.908241s**;
`current-slot=b`, retry count 7→6. This proves the new B recovery context
works when reached. It cannot guarantee that a hung experimental kernel
will reset into it. The original observer recorded its generic launch counter
as `experimental_boots=1`; this was one **recovery control**, not a mainline
experiment. The subsequent counter fix separates these categories.

### RESET8 — blocked, no repeated boot

Exact private RESET8 boot `1422a187…5b7f` was used unchanged. Preflight was
B / unlocked / no snapshot / battery okay / retry 6. One RAM boot command:

| event | UTC on 2026-09-15 |
| --- | --- |
| command start | 22:43:34.515 |
| Booting OKAY | 22:43:35.697 |
| Fastboot disappeared | 22:43:36.965 |
| 120-second observation expired | 22:45:35.840 |

`RESET8_STATUS=NO_RETURN_WITHIN_120S`. Direct protocol checks and the macOS USB
tree subsequently showed no ADB, Fastboot, or phone USB enumeration. No return
time can be assigned; no automatic P15 recovery boot was observed.
`RESET1_EXECUTED=NO`, `RESET_PAIR_VERDICT=NOT_EVALUABLE`.
`MACHINE_RESTART_ENTRY_REACHED=NOT_PROVEN`, `INIT_EXECUTED=NOT_PROVEN`.
Neither a Linux panic nor a firmware watchdog cause is inferred from absence.
Old A-return totals must not be used to fill the missing B endpoint.

Evidence: `artifacts/slot-b-continuation-20260916/` (sanitized text only).
B remains last-known stock V14 + P15; configured slot was B before transport
loss. No post-RESET8 live slot or partition checksum is claimed.

### Required recovery and next step

Gate: **BLOCKED_ON_PHYSICAL_FASTBOOT_RECOVERY**, not waiting for permission.
The user has already authorized continued work. Software commands cannot
recover a phone absent from both ADB and Fastboot.

Keep USB connected, hold **Volume-Down + Power** to enter Fastboot (the same
manual recovery documented by M5G/M5H). Do not clear data or ordinary-reboot
an unknown state. Once re-enumerated, first read product/unlocked/current-slot
and retry state, then recover the unchanged Android A for read-only logs and
post-test B/protected-partition hashes. Do not automatically rerun RESET8 or
run RESET1 with an invalid reference.

The kernel source places `rest_init`, scheduling, and SMP bring-up after the
already proven `calibrate_delay` checkpoint. The existing source audit also
shows QCOM_WDT is a module, so its boot-enabled watchdog takeover cannot run
in this built-in-initramfs environment. These remain investigation candidates,
not established causes; acquire the recovery logs before selecting or building
the next controlled diagnostic. No watchdog MMIO or speculative kernel change
was attempted during transport loss.
