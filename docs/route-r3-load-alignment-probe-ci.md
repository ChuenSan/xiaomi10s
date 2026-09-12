# Route R3 — Load Alignment Probe (CI)

Milestone: `MAINLINE_V2_R3_LOAD_ALIGNMENT_PROBE_CI`
Previous final gate: `FINAL_GATE_PREVIOUS=R3_ENTRY_STATE_PRIMARY_CONTRACT_SATISFIED`
Target final gate: `READY_FOR_R3_LOAD_ALIGNMENT_PROBE_DEVICE_CONTROL` or
`R3_LOAD_ALIGNMENT_PROBE_CI_NOT_READY`

## 1. Why alignment still matters

The stock payload execution proof (P0) and the entry-state probe proved that
ABL executes code loaded in the temporary fastboot boot payload and that the
entry state is EL1, MMU off (`M=0`), D-cache off (`C=0`). That established
`EXECUTABLE_PLACEMENT_PROVEN=YES` for the probe payload itself.

`EXECUTABLE_PLACEMENT_PROVEN=YES` does NOT imply
`MAINLINE_IMAGE_PLACEMENT_CONTRACT_PROVEN=YES`. The Linux arm64 Image boot
protocol still requires the runtime address S of Image byte 0 to satisfy
`S mod 2MiB == 0x80000` (`text_offset`). Until that single geometric hard
condition is measured, the direct-in-place handoff path stays blocked and
P1B (clean mainline Image entry) must not be attempted.

## 2. P0 / entry-state proven baseline

- P0 ABL→controlled shim: PROVEN. A8/A24 timing delta 15.993s vs expected
  16.000s.
- P0 pairs: A8 14.148s → 8s (A8 overhead: 6.148s), A24 30.141s → 24s
  (A24 overhead: 6.141s). `P0_RESET_OVERHEAD_REF=6.1445`.
- P0 timer source: `P0_TIMER_SOURCE=CNTPCT`; termination:
  `P0_TERMINATION_METHOD=PSCI_SYSTEM_RESET`; conduit: `THYME_PSCI_CONDUIT=SMC`.
- Entry-state probe true-device: bucket 4s, BOOTING_OKAY→kernel_start 10.094s,
  programmed estimate 3.949s, error −0.051s, verdict STRONG.
  Decoded: CurrentEL=EL1, SCTLR_EL1.M=0, SCTLR_EL1.C=0.
- RT-D completed and frozen: `RT_D_DTB_SHA256` =
  4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327.
- Boot envelope reference: exact M5D boot, `M5D_BOOT_SHA256` =
  4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63.

## 3. Stock kernel supporting evidence

`STOCK_KERNEL_CODE_BASE=0xa0080000`, so `0xa0080000 mod 0x200000 = 0x80000`.
This is classified `LOAD_ALIGNMENT_SUPPORTING_EVIDENCE`, `SUPPORTING_ONLY`.
It shows the stock kernel sits where the arm64 boot protocol wants it, but it
says nothing about where ABL actually places a temporary fastboot boot
payload. No amount of static reading can substitute for the runtime
measurement in this round.

## 4. Why absolute S is unnecessary

The direct trampoline only needs `S mod 2MiB` to decide placement validity.
Therefore this round asks exactly one question:
`R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M == 0x80000 ?` — nothing else. No absolute
S is computed, recorded, or hardcoded anywhere in the probe, and a mismatch
result must never be interpreted as a guess of S.

## 5. Probe architecture

Pure position-independent ARM64 assembly (`scripts/r3-lap/r3-lap-probe.S`),
register-only, linked at payload offset 0 with `image_base` (= `_start`) at
kernel payload offset 0 and the probe body at offset 0x40 behind the frozen
ARM64 Image header (code0/code1 branch to 0x40). The probe computes the
runtime address of `image_base` with a single PC-relative ADR, masks the low
21 bits, compares against 0x80000, and converts the verdict into one of two
preregistered delays, then ends with the P0-proven CNTPCT wait and PSCI
SYSTEM_RESET. Constraints: NO STACK, NO DATA MEMORY READ, NO DATA MEMORY
WRITE, NO DTB ACCESS, NO x0 DEREFERENCE, NO ABSOLUTE ADDRESS, NO
RELOCATIONS. Only PC-relative address calculation, integer arithmetic,
CNTPCT, and PSCI SYSTEM_RESET are used.

## 6. Image-base PC-relative calculation

`image_base` is a linker symbol at kernel payload offset 0, verified after
link by `readelf -s` (image_base=0, _start=0, probe_entry=0x40, no UND
symbols). The probe body references it with `adr x0, image_base`, so x0
becomes S, the runtime address of Image byte 0 — the same address ABL jumped
to (code0 is at payload offset 0 and P0 proved ABL executes it). Because the
symbol and the ADR live in the same Image, no absolute address exists and
`ELF_RELOCATIONS=0` after link. Disassembly gates prove the ADR target is
payload offset 0 in both target-address and PC-relative objdump print forms.

## 7. LOW21 comparison

`LOW21=S&0x1fffff` (mask built as movz 0xffff + movk 0x1f, lsl #16), then
`MODULUS=0x200000` semantics via `and`, compared against
`REQUIRED_LOW21=0x80000` (movz 0x8 + lsl #16). The comparison is a plain
register `cmp`; no memory access, no DTB, no x0 dereference.

## 8. 8/24 encoding

- `ALIGNMENT_MATCH -> 8s` (LOW21 == 0x80000)
- `ALIGNMENT_MISMATCH -> 24s` (LOW21 != 0x80000)

The 8s/24s pair is reused because P0 already proved it is reliably
resolvable on this device (15.993s delta vs 16.000s expected). No additional
low-address buckets are introduced; this round is pass/fail only.

## 9. Timing decoder

Future decode: `PROGRAMMED_ESTIMATE = BOOTING_OKAY→kernel_start − 6.1445s`,
nearest of 8s/24s. `TIMING_TOLERANCE_STRONG=0.75`,
`TIMING_TOLERANCE_SUPPORTED=1.5`, else `R3_LOAD_ALIGNMENT_PROBE_INCONCLUSIVE`
(no mismatch may be claimed from an inconclusive result). The 8s bucket
decodes `R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M=0x80000` and
`MAINLINE_IMAGE_ALIGNMENT_CONTRACT=SUPPORTED_BY_PROBE`; the 24s bucket
decodes `R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M_MISMATCH=YES` with
`S_NOT_GUESSED=YES`. Decoder fixtures also prove the entry-state probe's
10.094s observation falls OUTSIDE both alignment buckets, so the two probe
generations cannot be confused.

## 10. Boot envelope

Same P0/entry-state proven envelope, only the probe code is replaced:
Android boot header v3 (header_size 1580), kernel payload 35101184, boot
total 35110912, ramdisk 595 bytes at offset 35106816 (same reference),
cmdline same (empty), Image header text_offset `0x80000`, image_size
`0x2220000`, flags `0xa`, PE offset 0, magic ARM\x64. Splice is verified
byte-exact: every differing byte vs M5D lies inside the kernel payload
region; header and tail are byte-identical to M5D.

## 11. No-stack / no-memory proof

Disassembly gates enumerate the complete probe body in address order and
reject any store family (str/strb/strh/stp/stur/stlr/stxr/...), any load
family (ldr/ldrb/ldrh/ldp/ldur/...), `sp`, `adrp`, `msr`, `eret`, `hvc`,
`svc`, `bl/blr/ret`, `cntvct`, and GOT references. The instruction allowlist
is exactly: b/b.eq/b.hs, cmp, mrs, mov/movz/movk, and, lsl, mul, sub, isb,
yield, wfe, smc, adr. Negative fixtures inject a store, a stack
modification, and a wrong-offset ADR and must be REJECTED.

## 12. Relocation proof

Object-file gate: any relocation class outside `R_AARCH64_ADR_PREL_LO21`
(plain PC-relative ADR) fails — `R_AARCH64_ABS*`, `R_AARCH64_RELATIVE`, GOT
classes are all rejected. Linked-ELF gate: `readelf -r` must show zero
relocations (`ELF_RELOCATIONS=0`). Negative fixtures: a literal-pool
absolute-address implementation and a `.quad` cross-section absolute symbol
relocation must both be REJECTED at the object gate.

## 13. Observer bug fix

The previous true-device observer crashed with an uninitialized state key
`transient_fastboot` (`KeyError`) at summary time, after all data collection.
The fixed observer (`scripts/r3-lap/observe-r3-load-alignment.py`)
initializes every state key including `transient_fastboot` and
`stable_fastboot` to explicit defaults, reads them back with `.get()` in the
summary path, and exposes `emit_summary`/`decode_alignment`/`recovery_kind`
as injectable functions. `observer-summary-fixtures.py` runs the summary
path under synthetic states: TRANSIENT_PRESENT, TRANSIENT_ABSENT,
ANDROID_RETURN, STABLE_FASTBOOT_RETURN, MANUAL_RECOVERY_NO_RETURN, plus
DECODE_MATCH/DECODE_MISMATCH/DECODE_INCONCLUSIVE/SUPPORTED and a
legacy-state-missing-keys regression. Required result:
`OBSERVER_SUMMARY_FIXTURE=PASS`, `OBSERVER_KEYERROR_FIXED=YES`.

## 14. GHA gates

Public CI (`thyme-r3-load-alignment-probe.yml`) runs, on pinned LLVM
18.1.3 / ubuntu-24.04: actionlint, py_compile of all three scripts, source
gate (probe/observer/fixture/doc/workflow tokens, forbidden patterns),
decoder fixtures, observer summary fixtures, assemble+disassembly+relocation
gates with all negative fixtures, synthetic boot-envelope negative fixtures,
and an assert that no flashable output exists. The public workflow does not
splice M5D and does not emit a boot image. Private CI
(`ChuenSan/thyme-mainline-private-ci` `thyme-r3-load-alignment-probe.yml`)
adds the exact M5D splice and emits `thyme-r3-load-alignment-probe.img`
plus gates/manifest/disasm/SHA256SUMS/DO_NOT_FLASH.

## 15. Future device safety

When (and only when) separately approved: active slot A, current B unchanged
(`AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B`), `PARTITION_WRITES=0`,
`SET_ACTIVE=NO`, Slot A never written, single experimental action
`fastboot boot thyme-r3-load-alignment-probe.img` (`FASTBOOT_BOOT_ONLY=YES`),
observe BOOTING_OKAY→kernel_start once, `SECOND_BOOT_FORBIDDEN=YES`, no
second probe boot, observer artifact identity enforced via
`R3_PROBE_BOOT_IMG` + `R3_PROBE_SHA256` before any boot.

## 16. Future branches

- 8s bucket STRONG/SUPPORTED → `R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M=0x80000`,
  `MAINLINE_IMAGE_ALIGNMENT_CONTRACT=SUPPORTED/PROVEN_BY_PROBE`;
  `COPYDOWN_REQUIRED=NO` for the first normal Linux attempt; recommended next
  milestone `MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI`.
- 24s bucket → `R3_FASTBOOT_BOOT_IMAGE_BASE_MOD_2M_MISMATCH=YES`; direct P1B
  direct path forbidden; recommended next: `R3_P1_LOAD_GEOMETRY_ISOLATION_CI`
  or copydown geometry research. Never guess S.
- Anything else → `R3_LOAD_ALIGNMENT_PROBE_INCONCLUSIVE`; enter probe failure
  isolation; do not record an alignment mismatch.

## 17. P1B architecture after PASS

If the alignment probe passes, P1B prefers NO COPYDOWN: a clean Linux
6.6.156 Image plus a tiny early PC-relative trampoline plus an embedded
self-contained RT-D plus a built-in deterministic initramfs. RT-D is linked
into a dedicated read-only section inside the Image footprint (preferred
over an Image trailer beyond image_size, because ABL trailing-byte load
semantics remain unproven); the trampoline sets x0 = &embedded_rt_dtb
PC-relatively, masks DAIF only if the exact boot contract requires it, and
branches into normal primary_entry. M5D keeps only its known-good Android
boot envelope reference role; the P1B Image itself must be a clean normal
Linux 6.6.156 with no deliberate b-loop. First goal is /init execution proof
(INIT TIMING SIGNATURE), not USB; no mechanical global icache invalidation
without a self-modifying copy.

## Constraints

```text
LOCAL_BUILD:                       NO
LOCAL_VALIDATION:                  NO
LOCAL_VALIDATOR:                   NO
LOCAL_SOURCE_GATE:                 NO
LOCAL_ACTIONLINT:                  NO
LOCAL_BINARY_VALIDATION:           NO
GHA_ONLY:                          YES
DEVICE_OPERATION:                  NO
PARTITION_WRITES:                  0
Slot A written:                    NO
SET_ACTIVE:                        NO
```

## Private build record

Public CI run 34683220593 (commit 7068f0d, all gates green,
`OBSERVER_SUMMARY_FIXTURE=PASS`). Private packing run 34683393244 in
`ChuenSan/thyme-mainline-private-ci` (workflow commit
3083fefd1be1606642c3ac9535cc33d7cff6a1c4, the run's GITHUB_SHA), public
source pin 7068f0db9a8eb67d86482ab5edd604928a6ed7ea, toolchain LLVM 18.1.3
on ubuntu-24.04:

- artifact `thyme-r3-load-alignment-probe.img`: size 35110912, SHA256
  6403ad5258a768a3ed91acc23f219b2cb55fbbf04358d25d9e8c1afab515a4ba
- kernel payload `Image-r3-load-alignment-probe`: SHA256
  f1b9fe9fa4dd455502a035a876d10f5bcdf92937214a4268f11c5af0f18e9682
- probe binary `r3-lap-probe.bin`: SHA256
  c6675eac04ec79538d3ede96209980ef4bb5aff5340f0a677832c27008f5e7b8
- disassembly anchor: `adr x0, 0x0 <image_base>` at offset 0x44; objdump
  prints the ADR in target-address form; gate accepts target and
  PC-relative print forms.
- Future device round identity env:
  `R3_PROBE_SHA256=6403ad5258a768a3ed91acc23f219b2cb55fbbf04358d25d9e8c1afab515a4ba`
  with `R3_PROBE_BOOT_IMG` pointing at this exact artifact.

## Final gate

`READY_FOR_R3_LOAD_ALIGNMENT_PROBE_DEVICE_CONTROL` if every CI gate is green
and the private artifact exists; otherwise
`R3_LOAD_ALIGNMENT_PROBE_CI_NOT_READY`. Device operation stays NO this
round; `M5N FROZEN`; USB frozen; RT-D frozen at the SHA above.
