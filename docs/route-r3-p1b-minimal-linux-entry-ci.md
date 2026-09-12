# Route R3 · P1B — Minimal Linux Entry (CI only)

MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI. First real mainline Linux candidate
(BCI: ABL → minimal handoff trampoline → normal Linux 6.6.156 primary_entry →
RT-D → built-in initramfs → /init). CI-ONLY round: every build and validation
runs on GitHub Actions; no device operation; Slot A never written; M5N frozen;
Current B unchanged.

## 0. Constraints (immutable this round)

- LOCAL_BUILD=NO, LOCAL_VALIDATION=NO, LOCAL_SOURCE_GATE=NO,
  LOCAL_ACTIONLINT=NO, LOCAL_BINARY_VALIDATION=NO. Kernel, initramfs, DTB
  verification, assembly, link, objdump, boot packing and binary validation all
  run on GHA public + private runners.
- NO DEVICE OPERATION: no fastboot boot/flash/set_active, no copydown, no
  device file pushes. Slot A untouched. Current B = M5D+M5H+M5M-B unchanged.
- M5N_TARGETING_ISOLATION=FROZEN.
- COPYDOWN_REQUIRED=NO (LOAD_ALIGNMENT_BLOCKER=CLOSED, R3_LOAD_ALIGNMENT_PROVEN).
- Public repo must not carry M5D bytes or flashable boot images: the public
  workflow does not splice M5D and does not emit a flashable boot image;
  splicing + boot v3 packing run in the private repo only (LAP pattern).

## 1. Frozen true-device evidence (reused, not re-researched)

- ABL executes payload at offset 0 (STRONG, P0/LAP observer lineage).
- Entry state EL1, M=0, C=0 (STRONG; R3_ENTRY_STATE_PRIMARY_CONTRACT_SATISFIED,
  private run 34678013953).
- S mod 2MiB = 0x80000 (STRONG; R3_LOAD_ALIGNMENT_PROVEN, run 34683393244,
  boot 35110912 bytes SHA 6403ad52-lineage verdict MATCH).
- LOAD_ALIGNMENT_BLOCKER=CLOSED; COPYDOWN_REQUIRED=NO.
- RT-D: SHA256 4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327,
  144593 bytes, chosen bootargs `rdinit=/init panic=5 loglevel=7`. RT-D must not
  change this round.

## 2. Clean Image provenance

- Source: Linux 6.6.156 at commit 8b73de7da85fde281a385e0b26eda9bffd3ca477
  (submodule, asserted in CI at checkout).
- Patches: patches/linux-6.6 0001 + 0002 only; patch queue SHA
  d470701d58d62bf10b96adb4dbf0c639945afccd45d4d3f039e8051e7aaaf1b5 asserted by
  the builder before apply.
- Config: defconfig + configs/thyme-route-b.config + configs/thyme-r3-p1b.config
  (+ per-build INITRAMFS_SOURCE fragment) via merge_config.sh + olddefconfig.
- Toolchain: pinned LLVM 18.1.3 (noble apt), LLVM=1 kernel build; gcc
  aarch64-linux-gnu for /init only.
- Build: `make Image` in an isolated O= directory per delay plus a clean
  baseline O= with INITRAMFS_SOURCE empty.

## 3. Baseline reproduction (M0 compare)

Clean baseline (no trampoline, no builtin initramfs, clean config set) Image is
compared to the historical M0 GHA run 34322563307 Image
22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6.
Verdict M0_BASELINE_REPRODUCED=YES on byte-identity, else PARTIAL with explicit
source/config/patch/primary_entry/header correspondence proof recorded in the
CI log and manifest. Result: PARTIAL (run 34696279424,
CLEAN_IMAGE_SHA256=005d5aba192005b0a45c789acac8568bbee0c9c84c527984301afff52fdcbc85;
scope = toolchain/build metadata only — source commit 8b73de7d, patch queue
d470701d, config line, primary_entry offset 0x1b1c0a0, header semantics and
file_size 0x2179a00 all correspond; kernel builds embed UTS_VERSION build
metadata, so cross-run byte identity of Image is not attainable).

## 4. Normal primary_entry proof (PRIMARY_ENTRY_NORMAL=YES)

- `nm` vmlinux: primary_entry−_text offset computed dynamically (no constant).
- `objdump` first instruction of primary_entry must be `bl record_mmu_state`
  (head.S 6.6.156 first body instruction); `b .` self-branches, timer loops and
  PSCI probes are forbidden tokens.
- code1 must equal `b primary_entry` (0x14000000 | ((off_primary−4)/4)) before
  patching; code0 (efi_signature_nop) must be untouched in the final payload.
- Historical cross-check: M5D/P0 primary_entry at Image offset 0x1b1c0a0.

## 5. Exact boot protocol (Linux 6.6.156 booting.rst + head.S)

- CPU: AArch64, EL1 preferred; MMU off, D-cache off, I-cache don't-care.
- x0 = physical DTB address; x1 = x2 = x3 = 0.
- "All forms of interrupts must be masked in PSTATE.DAIF" → trampoline executes
  `msr daifset, #0xf` (explicit, no device probe needed).
- Bootloader must not modify DTB; DTB 8-byte aligned, within first 2 MiB of
  memory crossing a 2 MiB boundary, not inside a region needing special
  attributes; at least image_size bytes from image start must be free for the
  kernel to use (DTB outside that footprint is safe).
- Kernel expects primary boot protocol entry at Image start (code0 path), not
  the EFI stub path.

## 6. DTB placement decision

- §3 re-audit: head.S create_idmap maps `_text .. _end + MAX_FDT_SIZE +
  SWAPPER_BLOCK_SIZE` and remaps the FDT region after the kernel image with
  normal RW MMU flags; the kernel natively supports the FDT sitting inside or
  immediately after the image footprint.
- Verdict: DTB_INSIDE_KERNEL_IMAGE_ALLOWED_BY_PROTOCOL=YES (protocol permits;
  head.S has explicit FDT remap handling).
- Selected: RT-D TRAILER OUTSIDE image_size (task §4 preference) —
  DTB_OFFSET ≥ image_size keeps RT-D byte-identity independent of kernel
  footprint and avoids overlapping the idmap hole layout; conditional on
  ABL full-kernel_size load (§9), which is proven.

## 7. S-residue geometry (S_RESIDUE=0x80000)

- S mod 2MiB = 0x80000 (STRONG device fact). All offsets below are relative to
  S; absolute S is not needed by the trampoline (PC-relative only) and remains
  a documented unknown (§19).
- (S + DTB_OFFSET) mod 2MiB == 0 → RT-D starts exactly at the first 2 MiB
  boundary after the kernel footprint; DTB 8-byte alignment satisfied with
  margin; RT-D size 144593 < 2 MiB so one fresh 2 MiB region hosts it.
- gap = DTB_OFFSET − image_size ∈ [0, 2MiB).
- RAM capacity (RT-D memory banks): bank1 0x80000000 + 0x39900000 (921 MiB)
  alone far exceeds payload + trailer (~36 MiB).

## 8. Dynamic DTB_OFFSET formula (no hardcoded image_size)

- DTB_OFFSET = align_up(image_size + 0x80000, 0x200000) − 0x80000.
- Asserts: (S_residue + DTB_OFFSET) mod 0x200000 == 0; DTB_OFFSET ≥ image_size.
- Formula unit tests in CI: image_size 0x2220000 → 0x2380000 (gap 0x160000);
  0x2208000 → 0x2380000; 0x1B1C0A0 → 0x1B80000. P1B actual: image_size
  0x2230000 → DTB_OFFSET 0x2380000, gap 0x150000, payload 37369041 bytes.

## 9. ABL loads full kernel_size (ABL_LOADS_FULL_BOOT_KERNEL_SIZE=YES)

Source audit, CodeLinaro CAF LA.UM.9.12.c26 QcomModulePkg (work/p1b-abl
copies; upstream: https://git.codelinaro.org/clo/la/abl/tianocore/edk2):

- BootLinux.c UpdateBootParamsSizeAndCmdLine: v3 header →
  `KernelSize = BootImgHdrV3->kernel_size` (header field, exact payload len).
- Non-gzip 64-bit path: `gBS->CopyMem(KernelLoadAddr, ImageBuffer + PageSize,
  KernelSize)` — the full kernel_size bytes are copied to the load address;
  ABL_LOADS_KERNEL_TRAILING_BYTES=YES for any bytes inside kernel_size. The
  RT-D trailer is inside kernel_size by construction (payload len = DTB_OFFSET
  + 144593), so ABL places it at S + DTB_OFFSET.
- KernelLoadAddr = buffer_base + KERNEL_64BIT_LOAD_OFFSET (0x80000,
  QcomModulePkg.dec) — independent source-level cross-validation of the device
  fact S mod 2MiB = 0x80000.
- Explicit ABL bounds check is `ImageSize ≤ DeviceTreeLoadAddr − KernelLoadAddr`
  (Image-header image_size, not KernelSize); CopyMem itself is unbounded —
  margin analysis in §19.
- Behavioral cross-validation: M5D payload (kernel_size 35101184, image_size
  0x217F000) fully loaded and executed to primary_entry on device six times
  (M5x lineage); LAP run proved offset-0 execution with the same path.

## 10. Trampoline design (minimal handoff, no memory writes)

- Image header words: code0 efi_signature_nop untouched; code1 (offset 4,
  original `b primary_entry`) patched to `b 0x40` (0x1400000F) → r3_handoff_entry
  at 0x40, inside the reserved __EFI_PE_HEADER hole [0x40, 0x10000) (P1 doc §15).
- r3_handoff_entry (scripts/r3-p1b/p1b-trampoline.S, linked at 0 by
  p1b-trampoline.ld):

```asm
r3_handoff_entry:
    msr  daifset, #0xf          /* booting.rst: mask all DAIF */
    isb
    adr  x0, dtb_rel
    ldr  x9, dtb_rel
    add  x0, x0, x9             /* x0 = S + off(dtb_rel) + P1B_DTB_REL = S + DTB_OFFSET */
    mov  x1, xzr                /* booting.rst: x1=x2=x3=0 */
    mov  x2, xzr
    mov  x3, xzr
b_primary:
    .inst 0x14000000 | (((P1B_ENTRY_REL)/4) & 0x03ffffff)   /* b primary_entry */
dtb_rel: .quad P1B_DTB_REL
```

- Injection (two-pass): PASS1 builds kernel+initramfs → image_size → DTB_OFFSET;
  PASS2 assembles trampoline with P1B_DTB_REL = DTB_OFFSET − (TRAMP_OFFSET +
  off(dtb_rel)) and P1B_ENTRY_REL = off(primary_entry) − (TRAMP_OFFSET +
  off(b_primary)) — all distances are payload-resident because the trampoline
  runs at payload offset 0x40 (hard gates assert x0 algebra == DTB_OFFSET and
  branch target == off_primary), then patches code1, zero-pads to DTB_OFFSET,
  appends RT-D. PASS1==PASS2 image_size asserted (single kernel build; PASS2
  adds no kernel bytes — padding only).
- Properties: PC-relative only (adr), no absolute S/GOT references, runtime
  relocations = 0 (readelf gate), no store/stack/MMU/cache/EL changes, no
  `ic iallu` (D-cache off ⇒ I-cache coherence for writes N/A; we write nothing),
  branch range to primary_entry ~27.7 MiB inside ±128 MiB, ISA store regex
  (incl. adrp) must not match the disassembly.

## 11. DAIF policy

booting.rst 6.6.156 explicitly requires "All forms of interrupts must be masked
in PSTATE.DAIF" at primary entry → the trampoline masks all four bits
unconditionally (`msr daifset, #0xf` + isb). No DAIF state probe on device is
needed; the requirement is taken from the protocol document, not from
guesswork.

## 12. RT-D identity (frozen)

- SHA256 4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327,
  144593 bytes, fdt totalsize and chosen bootargs
  `rdinit=/init panic=5 loglevel=7` asserted.
- Source: public GHA run 34678001413 artifact (workflow input, default pinned);
  downloaded in CI with sha256sum -c before use; re-verified after trailer
  extraction (public build) and again in the private pack gates
  (P1B_RT_D_TRAILER_SHA_EXACT=PASS).
- P1B cmdline = RT-D bootargs verbatim (frozen RT-D contract, unchanged).

## 13. Built-in initramfs (deterministic)

- Mechanism: CONFIG_INITRAMFS_SOURCE=<deterministic uncompressed newc cpio>,
  CONFIG_INITRAMFS_COMPRESSION_NONE=y, ROOT_UID/GID=0 (configs/thyme-r3-p1b.config).
- Contents: empty dirs dev/ init/proc/sys + /init (mode 0755, uid 0, gid 0);
  fixed ino/nlink/mtime=0, sorted entry order, TRAILER!!! — rebuilt twice in CI
  byte-identical (REBUILD_IDENTICAL=YES gate).
- Kernel embeds the cpio at build time → ramdisk_size in boot v3 stays the
  known-good M5D ramdisk (kernel_size is the only size field that changes).

## 14. /init implementation (minimal static syscall-only PID1)

- scripts/r3-p1b/p1b-init.c + p1b-init.ld: freestanding static ET_EXEC aarch64
  (gcc -nostdlib -no-pie, ENTRY(main), linked at 0x400000), no PT_INTERP, no
  NEEDED entries (readelf gates), no libc/busybox.
- Behavior: clock_nanosleep(CLOCK_MONOTONIC, delay) retry on EINTR →
  reboot(LINUX_REBOOT_CMD_RESTART) → if reboot returns, exit_group (PID1 exit
  ⇒ kernel panic, RT-D panic=5 reboots the device as fallback).
- Ident string `THYME-R3-P1B-INIT DELAY=N CMD=restart` (N=8/24) — the observable
  mainline execution signature for the future INIT8 run.

## 15. INIT8 / INIT24 pair

- Only difference: /init delay constant 8 vs 24 seconds; ident strings are the
  same length so image_size, DTB_OFFSET, gap, padding len, trampoline bytes,
  primary_entry offset, payload size and boot geometry are identical across the
  pair (pair gate asserts all of them).
- Both built in one GHA job from the same toolchain; /init compiled once per
  delay; cpio built twice per delay (byte-identical assert).
- P1B_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY is a hard gate
  (P1B_BUILD_PAIR_GATES=PASS).

## 16. Boot v3 packaging (private repo only)

- Splice: M5D known-good boot v3 envelope (header v3 1580 bytes + zero pad to
  4096, then kernel, pad, then exact M5D ramdisk bytes and tail pad). Changes:
  kernel_size field (offset 8) rewritten to payload len + kernel payload bytes
  replaced; ramdisk bytes, cmdline (frozen RT-D bootargs), os_version, reserved,
  header_version, header pad, ramdisk_size all byte-exact vs M5D.
- Envelope gate: header diff confined to [8,12) (kernel_size only) —
  P1B_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY.
- No more fixed boot size 35110912 (task §31): total size derives from payload;
  capacity gate vs 201326592 bytes with ≥ 16 MiB margin
  (P1B_BOOT_CAPACITY=PASS).
- M5D pin: private run 34487382191, artifact
  thyme-mainline-v2-m5d-pe-offset-zero-1a30f48d5ef86ff2dce7df6f761ca925f60aa9e7,
  boot mainline-v2-m5d-pe-offset-zero-spin-boot-v3.img, SHA256
  4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63.

## 17. Public/private CI split

- Public (ChuenSan/xiaomi10s, .github/workflows/thyme-r3-p1b-minimal-linux-entry.yml):
  actionlint + source gate → clean baseline build + M0 compare → INIT8/INIT24
  pair build (kernel, trampoline, payload headers, disassembly gates, RT-D
  trailer, manifests). Emits payloads + reports; does not splice M5D and does
  not emit a flashable boot image (asserted).
- Private (ChuenSan/thyme-mainline-private-ci): checks out pinned public
  commit, downloads the public payload artifacts (SHA-pinned via
  workflow_dispatch inputs), downloads the pinned M5D boot, splices and packs
  boot v3 twice (INIT8, INIT24), runs pack gates, emits
  thyme-r3-p1b-init8-init24-boot + DO_NOT_FLASH.txt. Device operation none.
- Results (2026-09-12):
  - Public run 34696279424 @ commit ff34d08426855375923172832669216aa0c2f4c6
    (jobs: source audit, clean baseline, INIT8/INIT24 pair — all PASS).
    Image (pair) header: image_size 0x2230000, text_offset 0x0, file_size
    0x2189a00, flags 0xa; primary_entry offset 0x1b1c0a0 (PRIMARY_ENTRY_NORMAL=YES).
    Trampoline sha256 362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623
    (48 bytes, identical across pair); branch 0x60 → 0x1b1c0a0, x0 → 0x2380000.
    INIT8 /init sha256 4c1491b21d83080b5303e6294aad516f6eeb79bd276e2b159059f665a22135f4;
    INIT24 /init sha256 b5eb44c8cf5c4e0278851e6820378795079129083ae77fb5659e32979f5b7f55;
    INIT8 payload sha256 9720451ca7622d7578b114cab3a0a61ee50cd9cf27cf9053d73fb8ded2075a5c;
    INIT24 payload sha256 c8d2d33a3e771455cce49b867858dbb8779eb5900312e86578f2afe203632f58;
    P1B_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY.
  - Private run 34698327535 (M5D splice + boot v3 pack + pack gates — PASS):
    INIT8 boot 37380096 bytes sha256
    e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264;
    INIT24 boot sha256
    948455f45b0d4cb8b7a2f7a26807c70aa4ef9b84e5d83a62c84d61401f83159f;
    P1B_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY,
    P1B_RT_D_TRAILER_SHA_EXACT=PASS, P1B_BOOT_CAPACITY=PASS
    (201326592 − 37380096 ≈ 156.4 MiB free), READY_FOR_DEVICE=NO.

## 18. Fail-closed gates (all must PASS for READY)

- Normal Image gate: header (image_size ≥ file_size, flags LE + bit3, reserved
  zero), code0/code1 words, primary_entry disasm (`bl record_mmu_state`, no
  b ./timer/PSCI), trampoline disasm token chain (msr daifset, isb, adr/ldr/add,
  mov xzr, b) with store/adrp/sctlr/eret/bl/ic-iallu/tlbi forbidden, `.quad`
  little-endian bytes present in objdump -s, ELF relocations 0.
- DTB placement: payload len == DTB_OFFSET + 144593, FDT magic 0xd00dfeed at
  DTB_OFFSET, residue congruence, DTB_OFFSET ≥ image_size, gap < 2 MiB.
- Handoff algebra: TRAMP_OFFSET + off(dtb_rel) + P1B_DTB_REL == DTB_OFFSET
  (x0 lands on the FDT) and TRAMP_OFFSET + off(b_primary) + P1B_ENTRY_REL ==
  off_primary (branch lands on primary_entry); both are hard gates.
- RT-D trailer: exact SHA after extraction, chosen bootargs frozen.
- Pair: P1B_INIT_PAIR_SEMANTIC_DELTA=DELAY_CONSTANT_ONLY (equal geometry,
  differing /init + cpio SHAs).
- Packaging (private): envelope diff [8,12) only, capacity margin, tail pad,
  ramdisk byte-exact, trailer SHA re-verify.
- Source gate: pinned SHAs/tokens present in doc/scripts/workflow; public
  workflow contains no splice-boot/mkbootimg/device verbs; formula unit tests.

## 19. Remaining unknowns (recorded, not blockers per §7-§8)

1. ABL load-buffer margin beyond the explicit check: M5D proves
   DeviceTreeLoadAddr − KernelLoadAddr ≥ 0x217F000 (its image_size passed the
   explicit check); P1B needs ≥ image_size (~0x2230000, PENDING) for the check
   plus CopyMem span KernelSize = DTB_OFFSET + 144593 (~+1.45 MiB beyond
   image_size, unbounded by any check). Fallback PCDs
   (RamdiskEndAddress=0x05600000) suggest ~80 MiB headroom, but the effective
   thyme PCD values are unknown. Isolation: first failure-analysis item.
2. Absolute S: only S mod 2MiB = 0x80000 is proven. Bank geometry makes
   S = 0xa0080000 (stock kernel code base) the strong candidate — its 61 MiB
   stock footprint ends 0xA3D8B000 inside bank1 (ends 0xB9900000), and the
   alternative S = 0x80080000 would overlap the hyp no-map region
   [0x80000000, 0x80600000) by 0x58000 bytes, which stock demonstrably survives,
   so 0x80080000 is effectively excluded. P1B footprint (~36 MiB: payload
   37369041 + boot envelope tail) at 0xa0080000 ends ≈ 0xA242B800 and clears
   all RT-D reserved-memory regions (cont_splash ends 0x9E300000, disp_rdump
   starts 0xB0400000). Still recorded as unknown because only the residue is
   device-proven.
3. create_idmap completeness under the observed entry state (EL1, M=0, C=0) has
   not been device-proven past primary_entry — M5x proved execution reaching
   primary_entry; P1B relies on 6.6.156 source logic from there.
4. Timer/clock state handed over by ABL (CNTFRQ etc.) is assumed per
   booting.rst contract; INIT8/INIT24 sleep relies on the arch timer.
5. Header text_offset field archaeology: 6.6.156 head.S declares `.quad 0` and
   the built Image confirms text_offset 0x0; the M5C/M5D doc records of
   0x80000 are historical records only (geometry uses the device-proven S
   residue 0x80000, unaffected).

## 20. Future INIT8 experiment design (not this round)

- INIT8 first, only INIT8 authorized after user approval; INIT24 stays
  NOT AUTHORIZED until INIT8 results return (§46 differential design: 16 s
  delta → MAINLINE_INIT_EXECUTION_TIMING_PAIR_PROOF).
- fastboot boot only: PARTITION_WRITES=0, Stock vendor_boot_a/dtbo_a in place
  (active slot A), current B untouched, M5N frozen; copydown stays fallback-only.
- Observation targets: ABL_LOG_KERNEL_START → BOOTING_OKAY → kernel_start →
  PROVISIONAL_MAINLINE_INIT_SIGNATURE (ident DELAY=8) → reboot back to slot A
  Android. Any no-return isolates per §19 ladder (buffer margin → trampoline →
  DTB → head.S → memory → timer → initramfs → /init → reboot call).

## 21. Final gate enumeration

- READY_FOR_R3_P1B_INIT8_DEVICE_CONTROL=YES requires every gate in §18 PASS
  plus M0_BASELINE_REPRODUCED=YES (or PARTIAL with proof) and
  PRIMARY_ENTRY_NORMAL=YES.
- Otherwise exactly one of: R3_P1B_BLOCKED_BY_KERNEL_TRAILER_LOAD,
  R3_P1B_BLOCKED_BY_DTB_PLACEMENT, R3_P1B_BLOCKED_BY_IMAGE_PROVENANCE,
  R3_P1B_CI_NOT_READY.
- Regardless of verdict: P1B device executed: NO; READY_FOR_DEVICE=NO until
  user approval; M5N_TARGETING_ISOLATION=FROZEN; COPYDOWN_REQUIRED=NO;
  Current B unchanged.

## 22. TRUE DEVICE INIT8 RESULT (2026-09-12)

MAINLINE_V2_R3_P1B_INIT8_TRUE_DEVICE_CONTROL. One experimental boot only
(EXPERIMENTAL_BOOTS=1), PARTITION_WRITES=0, no flash/erase/set_active, Slot A
never written, SECOND_BOOT_FORBIDDEN honored, INIT24 NOT executed. mem0 read
twice (round start + before `adb reboot bootloader`). Observer =
`scripts/r3-p1b/observe-r3-p1b-init8.py` (LAP-derived; source changes gated by
public GHA run 34702388735, OBSERVER_INIT8_SUMMARY_FIXTURE=PASS,
OBSERVER_INIT8_AST_DEADLOCK_GATE=PASS).

### 22.1 Artifact full identity (authoritative GHA, full SHAs, all MATCH)

| Item | SHA256 | Source |
|---|---|---|
| boot INIT8 (37380096 B) | e6ac6308f274de34b89222bb011f20a00465d26f5b9d9c6cd923e2f722911264 | private run 34698327535 |
| kernel payload (37369041 B) | 9720451ca7622d7578b114cab3a0a61ee50cd9cf27cf9053d73fb8ded2075a5c | public run 34696279424 + embedded re-extract |
| clean Image | 005d5aba192005b0a45c789acac8568bbee0c9c84c527984301afff52fdcbc85 | public clean-baseline |
| trampoline (48 B) | 362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623 | public pair artifact |
| /init (INIT8) | 4c1491b21d83080b5303e6294aad516f6eeb79bd276e2b159059f665a22135f4 | public pair artifact |
| initramfs cpio (8s) | c45fa7a0bd8f7ca7062524b4f4b11e33ef0808553764d23e4ddc2707295ef684 | public pair artifact |
| RT-D trailer (144593 B) | 4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327 | embedded trailer re-extract |

Boot img header kernel_size field = 37369041 (matches P1B_KERNEL_SIZE); DTB at
0x2380000; P1B_ENVELOPE_VS_M5D=KERNEL_PAYLOAD_AND_KERNEL_SIZE_ONLY;
P1B_PACK_GATES=PASS. All MATCH=YES → proceed.

### 22.2 Preboot CopyMem recheck (source/evidence only)

P1B_PREBOOT_COPYMEM_STATUS=UNKNOWN (NO_CONTRADICTION) — no explicit source
evidence that kernel_size exceeds ABL destination/staging capacity, and no
dangerous-overlap counter-evidence; experiment proceeded, CopyMem remains the
first isolation candidate. Source evidence (LA.UM.9.12.c26):
FastbootCmds.h MIN_BUFFER_SIZE=67108864 (download buffer ≥ 64 MiB) vs P1B
need 0x80000+37369041 = 37451681 B (35.72 MiB); CmdDownload rejects
`mNumDataBytes > MaxDownLoadSize` BEFORE any CopyMem; CmdBoot re-checks
`(MaxDownLoadSize − (ImageSizeActual − SigActual)) < PageSize`; BootLinux.c
kernel64 check `ImageSize ≤ DeviceTreeLoadAddr − KernelLoadAddr` else
RETURN_OUT_OF_RESOURCES (fail-fast before kernel entry); fallback destination
BaseMem()=0x80000000 + KernelLoadAddress 0x80000, KernelEndAddr = BaseMemory +
RamdiskEndAddress 0x05600000 → CopyMem dest end 0x82422A91 < 0x85600000
(~50 MiB margin). Live preflight: `max-download-size=805306368` (768 MiB).
Effective runtime values of the UEFI-var path (KernelBaseAddr/KernelSize)
remain unproven — UNKNOWN retained.

### 22.3 Preflight

Android A baseline: slot_suffix=_a, boot_completed=1, root uid=0, Stock
4.19.157-perf-g9d90dd04aa7c. Fastboot getvar: product=thyme, unlocked=yes,
current-slot=a, snapshot-update-status=none, battery-soc-ok=yes,
max-download-size=805306368; slot a: retry=6/unbootable=no/successful=yes;
slot b: retry=7/unbootable=no/successful=no. Current B pre-test all four
domains MATCH (boot_b M5D 4db8151b…, vendor_boot_b head 2d58ef94…/tail
5d98f207…, dtbo_b M5M-B c5a355b9…aba8).

### 22.4 Fastboot acceptance

Sending: OKAY (+0.928s after T_COMMAND_START). Booting: OKAY (+1.149s). No
FAIL lines. R3_P1B_INIT8_BOOT_NOT_ACCEPTED=NO.

### 22.5 Timeline (UTC 2026-09-12, absolute host clock)

```
T_COMMAND_START            15:33:35.513Z
T_SENDING_OKAY             15:33:36.441Z
T_BOOTING_OKAY             15:33:36.662Z
T_USB_NONE                 15:33:38.014Z
T_FASTBOOT_DISAPPEAR       15:33:38.016Z   (BOOTING_OKAY + 1.354s)
T_USB_FIRST_REENUM         15:34:08.782Z   (18d1:4ee7 adb gadget)
T_ADB_FIRST_SEEN           15:34:09.375Z   (uptime 9.53s)
RETURNED_ANDROID_KERNEL_START 15:33:59.845Z (= host_before 15:34:09.375Z − /proc/uptime 9.53s)
T_BOOT_COMPLETED           15:34:18.542Z
```

P1B_INIT8_BOOTING_TO_RETURNED_KERNEL_START = **23.184s**
(BOOTING_OKAY → returned Android A kernel_start; future INIT24 differential
baseline, INIT24_BASELINE_SAVED=YES). Independent cross-check via
BOOT_COMPLETED snapshot: kernel_start 15:33:59.825Z → 23.164s (Δ 20 ms).
No P0-overhead bucket decoding applied this round (task §14/§16); no Mainline
kernel-start moment derived.

### 22.6 Observed behavior

Automatic reset: YES (P1B_INIT8_AUTOMATIC_RESET_OBSERVED=YES). Android A
auto-return: YES (ANDROID_A_AUTO_RETURNED=YES, RECOVERY_KIND=
AUTOMATIC_ANDROID_RETURN). Stable Fastboot return: NO
(P1B_AUTOMATIC_FASTBOOT_RETURN=NO) → P1B_4P7S_PATH_OBSERVED=NO (no
pre-primary-entry failure signature). Manual recovery: NO. USB behavior: no
custom/mainline gadget at any point; adb re-enumerated only after Android A
returned (18d1:4ee7); E5 USB stays FROZEN.

### 22.7 Persistent evidence (pstore/dumps, read-only, nothing cleared)

pstore: 0 entries. rawdump whole 254bcc3fc4f27172636df4bf32de9f107f620d559b20
d760197e452b97453917 and logdump whole 3b6a07d0d404fab4e23b6d34bc6696a6a312dd9
2821332385e5af7c01c421351 — byte-identical to entry-state/LAP rounds
(UNCHANGED). minidump (ace865ca…), oops (5745f412…), logfs (3261fb5e…) are
boot-time deltas only; bounded content scan (16 MiB prefix each, all dumps)
found every `Run /init as init process` and `Linux version` line to be Stock
4.19.157-perf (including historical panic deltas). EXPLICIT_MAINLINE_6.6_
EVIDENCE=NO; EXPLICIT_INIT_EVIDENCE=NO. Note: absence is expected, not
contradictory — this artifact configures no persistent console/pstore sink;
loglevel=7 output goes only to a UART we do not have.

### 22.8 Evidence ladder

```
E0 ABL→shim                PROVEN      (P0/LAP lineage, unchanged)
E1 normal Mainline reached SUPPORTED   (no 4.7s pre-entry failure signature;
                                        auto-reset timing consistent; no direct log)
E2 early kernel boot       SUPPORTED   (indirect only, no persistent mainline log)
E3 initramfs               NOT_PROVEN  (no direct evidence)
E4 /init                   PROVISIONAL (single auto-reset consistent with the
                                        8s delay; competing paths panic=5 / early
                                        panic / firmware reset / init-reboot not
                                        excluded → INIT24 pair required)
E5 USB                     FROZEN
```

### 22.9 Current B post-test

All four domains re-verified MATCH post-test:
`CURRENT_B_UNCHANGED_AFTER_P1B_INIT8=YES`. Android A restored:
slot_suffix=_a, boot_completed=1, root uid=0, Stock 4.19.157-perf,
bootreason=bootloader → `ANDROID_A_RESTORED=YES`.

### 22.10 Causal limits, final gate, next

A single INIT8 auto-reset cannot prove /init execution (§25): competing reset
paths include panic=5, early mainline panic, other firmware reset, and /init
reboot. No MAINLINE_INIT_PROVEN / MAINLINE_INIT_EXECUTED claim is made. Final
gate: `MAINLINE_V2_R3_P1B_INIT8_SIGNATURE_OBSERVED`
(P1B_INIT8_PROVISIONAL_SIGNATURE=YES). Next stage:
`MAINLINE_V2_R3_P1B_INIT24_TIMING_CONFIRMATION` — INIT24 requires separate
user approval; core metric `INIT24_TOTAL − INIT8_TOTAL ≈ +16.000s` with
INIT8_TOTAL = 23.184s as the frozen baseline. CopyMem/staging margin stays
first failure-isolation item if INIT24 returns abnormally. M5N FROZEN;
device final: Android A.
