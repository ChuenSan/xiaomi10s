# Slot B rest_init checkpoint

## Recovered evidence

The user restored Fastboot after RESET8's no-return. Product/unlocked matched;
slot remained B and B retry count remained 6 (same as before RESET8). Selecting
the untouched Android A restored ADB/root. All 16 recorded A/B boot-chain full
hashes, plus the P15 boot prefix, match the post-preparation baseline.

Pstore remains empty. OEM oops record 1253 contains only the stock P15 control:
`Run /init` at 1.419841s, restart at 16.420051s (15.000210s difference).
No Mainline trace is present. Logdump/rawdump match the older baseline. These
are not evidence that Mainline never ran or that any particular reset cause
was responsible. RESET8/RESET1 are not retried.

## Next controlled question

Does the FIX8 normal kernel path reach `rest_init()` after `calibrate_delay()`?
Linux `init/main.c` calls `arch_call_rest_init()` at the end of `start_kernel`;
the arm64 weak implementation calls `rest_init`. This entry precedes kernel
thread creation, SMP bring-up, driver initcalls and `/init` execution.

The checkpoint reuses the exact 76-byte, device-proven 8s CNTPCT + PSCI reset
core, preceded by the unchanged original PAC/BTI entry word. It is composed
from frozen FIX8, not from the RESET8-instrumented payload. Only the audited
entry window changes; trampoline, RT-D, initramfs and all other bytes remain
frozen. All compilation, composition and binary checks are GitHub Actions only.

A positive matched pair shows entry reachability and the preceding normal
start_kernel path, not rest_init's body or a completed Linux boot. A missing
return is inconclusive and requires recovery; never execute a second blind boot.

## Preregistered device pair

REST8 is already audited by public run `35036419486` and privately packed and
independently verified by `35038457905`. REST1 is composed using that preserved
audit bundle: only the timer immediate changes 8→1 (two bytes at
`[0x10c1f58,0x10c1f5a)`). It does not rebuild the kernel.

Both tests must originate from a normal Android A boot followed by
`adb reboot bootloader`, then verified selection of B. A is never flashed.
Do not mix this route with the preceding P15-origin RESET8 experiment.
The P15 recovery partition and stock B vendor/DTBO must stay byte-identical.
Run REST8 once. Only after a valid automatic Fastboot return and a read-only
post-test context check may REST1 execute once. A single return only records
a reference; it does not establish the checkpoint's reachability.

Primary equation: `REST1_TOTAL - REST8_TOTAL = -7s`, same Fastboot endpoint
as the B observer. Absolute error <=1s is STRONG, <=2s SUPPORTED; otherwise
NOT_CONFIRMED. Manual recovery, transport loss, wrong slot/origin/identity or
changed recovery context invalidates the pair. Never use old A-return totals
or tune these thresholds after seeing results.

## Audit and reuse

The prior release artifacts omitted vmlinux. This Actions workflow therefore
builds one matching audit kernel and preserves Image, vmlinux, System.map,
configuration and hashes as `thyme-slot-b-kernel-audit-bundle`. Subsequent
checkpoint audits consume that bundle without rebuilding the kernel.

The new branch scan explicitly adds `_text` to Image offsets and checks B/BL,
B.cond, CBZ/CBNZ and TBZ/TBNZ. The legacy T3 scanner mixes offset-space PCs with
VA-space windows and its disassembly confirmation excludes several branch
families; it is not used here. Unit tests cover the high-VA case and backward
branches. Runtime table extraction fails closed; alternative instruction
ranges are checked for overlap, not only starting addresses.

The selected function's VA, extent, section, original instructions and frozen
bytes must agree. Interior symbols, incoming branches, literals, relocations,
exception/alternative/jump/static-call records are checked before emission.
OEM boot wrapping stays in private Actions. Slot B retains stock V14 + P15
recovery. Before a device test, freeze the new boot SHA and extend the B-only
observer allowlist in CI. No Slot A, vbmeta or firmware flash is involved.

## Reusable ELF export correction

REST1 run `35038941457` was correctly rejected by `BUNDLE_HASH_MISMATCH:vmlinux`.
The first audit used inherited `llvm-objcopy --dump-section` calls with no
output ELF. LLVM documents that omission as an in-place rewrite; the dump
file does not disable normal object-copy operations. The bundle manifest was
written before these calls, so its ELF-container hash preceded the rewrite.

The new audit reads sections by their ELF file offsets and checks the ELF hash
again at exit. RELR bitmap advancement also now matches arm64 `head.S`: every
bitmap advances 63 words, including trailing zero bits. Regression tests cover
that case. No old mutable extraction helper is used for the new audit.

`reconcile_bundle.py` accepts only the known original export and exact original
manifest. It requires unchanged Image/config/System.map, exact Image
reproduction using `arch/arm64/boot/Makefile` flags, and a match for every
System.map symbol before exporting reconciled provenance. The old and archived
ELF hashes are retained. A mismatch stops the workflow; no kernel rebuild or
unconditional hash replacement is permitted. This reconciliation runs in
Actions, never locally.

Reconciliation passed in `35040148509`: the archived ELF reproduces the exact
original Image and matches all 167212 System.map entries. Its container SHA is
`295bfdb12184052a79c1aea35ce4a93a5833c42bdb7b4bd9173973312ade00ff`.
The corrected audit checked 284143 relocation sites and preserved the ELF hash.
The same run holds the reconciled reusable kernel bundle; no kernel rebuild ran.

## Frozen device pair artifacts

| member | public run | private pack + independent verify | boot SHA256 |
| --- | --- | --- | --- |
| REST8 | `35036419486` | `35038457905` | `1832c179c924f2d21dd2aa16440759833c069353a920feff98240493214358bd` |
| REST1 | `35040148509` | `35040497721` | `e4b06d5785e010aa4b340f72f65974cf03c09b6e9654249d41cab6b1808226b4` |

Both boots are 37380096 bytes. Public payloads: REST8
`22086188014e015c2aa0c79783a06de1036234e211064415dbd18e896ae04360`, REST1
`2aa3ce7e5f6edb337fea3510c0288a45f975bc3ee3de186eab613f3e5bea6746`.
The corrected REST1 audit also reconstructs and checks the exact REST8
reference; it does not replace the already privately verified REST8 image.
The B observer pins both full boot SHAs, requires the declared Android-A-to-
bootloader-to-B origin, and cannot run the second member without a valid first
record. Observer CI `35041014819` passed before device execution.

## True-device result (2026-09-16 UTC)

Two different RAM-only Slot B boots, each launched from the preregistered
Android-A → Bootloader → B route; no partition flash occurred this round.

| member | Booting OKAY | automatic Fastboot return total |
| --- | --- | --- |
| REST8 | 00:44:56.387 | 35.392402583s |
| REST1 | 00:48:34.703 | 28.218802167s |

`DELTA=-7.173600416s`, expected `-7s`, error `-0.173600416s`: **STRONG**.
`REST_INIT_ENTRY=PROVEN`; the preceding normal start_kernel path is proven.
`REST_INIT_BODY=NOT_PROVEN`, `INIT_EXECUTED=NOT_PROVEN`. This is not a normal
Linux boot-success claim. Both returns remained on B and consumed one P15
recovery boot (retry 7→6). All 16 recorded A/B boot-chain hashes and the P15
prefix matched before, between and after the pair. Android A is healthy again.

Next: audit `kernel_init()` entry (`init/main.c`), the PID1 initialization task
created by `user_mode_thread`. A positive there proves the task was created
and scheduled, not that its initial `kthreadd_done` wait completed or `/init`
ran. Reuse the reconciled kernel bundle; do not rebuild or rerun REST8/REST1.
