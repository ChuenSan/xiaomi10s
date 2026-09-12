# Route R3 P1 — Linux boot contract + handoff geometry + minimal /init

Stage: `MAINLINE_V2_R3_P1_LINUX_BOOT_CONTRACT_CI`

CI / source audit only. No device operation. No local kernel/DTB/initramfs
build, assembly, link, binary patch, mkbootimg, or binary validation.

```text
mem0 read:                         YES
LOCAL_BUILD:                       NO
LOCAL_VALIDATION:                  NO
LOCAL_VALIDATOR:                   NO
LOCAL_SOURCE_GATE:                 NO
LOCAL_ACTIONLINT:                  NO
LOCAL_BINARY_VALIDATION:           NO
GHA_ONLY:                          YES
DEVICE_OPERATION:                  NO
ADB_DEVICE_CHANGE:                 NO
FASTBOOT:                          NO
FLASH:                             NO
SET_ACTIVE:                        NO
EXPERIMENTAL_BOOT:                 NO
Slot A written:                    NO
M5N FREEZE:                        YES
file/directory deletion:           NO
READY_FOR_DEVICE:                  forbidden this round
```

Public workflow: `.github/workflows/thyme-r3-p1-linux-boot-contract.yml`
(source-audit + init/trampoline/DTB prototype). Does not emit a flashable
boot image. Clean Image rebuild: private GHA /
`workflow_dispatch` only.

Private builder pin: `ChuenSan/thyme-mainline-private-ci`

Final Gate:

```text
R3_P1_LINUX_BOOT_CONTRACT=INCOMPLETE
R3_P1_BOOT_CONTRACT_INCOMPLETE
Primary blocker=RAM_MAP
```

Not `R3_P1_BOOT_CONTRACT_FEASIBLE`. This round forbids READY_FOR_DEVICE.

---

## 1. P0 proven baseline

Authoritative P0: `MAINLINE_V2_R3_P0_TIMING_PAIR_ENTRY_PROVEN`

```text
A8  programmed delay  8s   BOOTING_OKAY→kernel_start  14.148s
A24 programmed delay 24s   BOOTING_OKAY→kernel_start  30.141s
observed differential     15.993s
expected                  16.000s
error                     -0.007s
```

```text
ABL_EXECUTES_CONTROLLED_KERNEL_PAYLOAD_ENTRY=YES
SHIM_ENTRY_PROVEN=YES
SHIM_TIMER_CONTROLLED_PATH_EXECUTED=YES
EXECUTABLE_PLACEMENT_PROVEN=YES
```

Closed: “does ABL jump to payload offset 0?”. Do not re-prove it.

Not proven by P0: Linux entry contract, runtime DTB, /init, physical S,
2MB alignment, MMU/cache/EL, copydown.

Current B unchanged:

```text
AUTHORITATIVE_CURRENT_B=M5D+M5H+M5M-B
boot_b prefix 35110912
  SHA256 4db8151b110ad870b06d1bf87079ed06783bf469509fd886d56705c76ff85e63
dtbo_b whole
  SHA256 c5a355b942bf287d13a9c02e1fe96c13ebf43f20b61be7e05763b8d23872aba8
active: Slot A
```

---

## 2. Evidence ladder E0–E5

```text
E0  ABL→shim                         PROVEN
E1  shim→normal Mainline entry       NOT_PROVEN
E2  Mainline early boot              NOT_PROVEN
E3  initramfs mounted                NOT_PROVEN
E4  /init executed                   NOT_PROVEN
E5  USB gadget                       FROZEN
```

Next work is E1–E4. USB is not a P1 success condition.

Future device checkpoints, if ever authorized:

```text
P1-B0  Mainline controlled entry
P1-B1  Mainline reaches normal kernel path
P1-C   embedded /init executes
P1-D   USB / network
```

---

## 3. Clean Image provenance

```text
R3_P1_CLEAN_IMAGE_PROVENANCE
  Linux version:          6.6.156
  source commit:          8b73de7da85fde281a385e0b26eda9bffd3ca477
  patch queue:            patches/linux-6.6/*.patch
                          (0001 dt-bindings + 0002 thyme DTS only)
                          SHA256 d470701d58d62bf10b96adb4dbf0c639945afccd45d4d3f039e8051e7aaaf1b5
  experiments excluded:   patches/experiments/m2 m3 m4b
  config baseline:        arm64 defconfig + configs/thyme-route-b.config
                          + configs/thyme-r3-p1.config
  historical config SHA:  4ae37ddc7831151b35bb937e2fbc8bf101cac54a5c09b0f6cba3a673b8a3da49
  toolchain pin:          LLVM 18.1.3 / ubuntu-24.04  (P0/M5I class)
  DTS source:             sm8250-xiaomi-thyme.dts from 0002
  initramfs config:       CONFIG_INITRAMFS_SOURCE injected by GHA
```

Historical clean Image (diagnostic reference, not the P1 execution payload):

```text
M0 GHA run:     34322563307
commit:         23a2d6c
Image SHA256:   22d0ee238bb727bca29f9abb241786c94d333928001de5f051aa017da77ba2b6
boot SHA256:    378190377e8e2dcf43287d548cccfd5796ecc9cbb31b37ffd8446e181c7826bb
vmlinux SHA:    NOT_IN_M0_ARTIFACT
System.map SHA: NOT_IN_M0_ARTIFACT
PRIMARY_ENTRY_NORMAL: SOURCE_EXPECTED (unpatched head.S; M4B was first b .)
```

M0 cannot be the P1 payload: it has no built-in initramfs
(`CONFIG_INITRAMFS_SOURCE=""` in the firstboot/M0 lineage) and used unpinned
`ubuntu-latest` clang. P1 Image SHA / vmlinux SHA / System.map SHA /
primary_entry file offset are PENDING a pinned GHA rebuild.

```text
P1_CLEAN_IMAGE_BINARY=PENDING_GHA_REBUILD
M5D_SPIN_CONTROL_EXCLUDED=YES
```

---

## 4. M5D diagnostic-only status

```text
M5D_IS_FULL_LINUX_BOOT_BASELINE=NO
M5D_FULL_BOOT_BASELINE=NO
```

M5D Image SHA256 `5d1d3c3370dc5617f94af1e9b66128a16e95166d7e440b9ea820f7a2c91c974a`

```text
code0          0x146c7028   b primary_entry
text_offset    0x80000
image_size     0x2220000
flags          0xa
PE offset      0
primary_entry  Image 0x1b1c0a0  first word 0x14000000  b .
```

Allowed uses: boot v3 envelope, ramdisk SHA
`b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de`,
header/layout comparison, ABL acceptance reference.

Forbidden: normal Linux execution payload.

Do not assume clean Image fields equal M5D. Measure on the rebuilt Image.

---

## 5. ARM64 boot contract (Linux 6.6)

Source: `linux-6.6/Documentation/arch/arm64/booting.rst` and
`arch/arm64/kernel/head.S`.

```text
LINUX_6_6_ARM64_BOOT_CONTRACT
  x0:  physical address of DTB in system RAM
  x1:  0
  x2:  0
  x3:  0
  CPU: non-secure EL2 (recommended) or EL1; PSTATE.DAIF masked
  ENTRY_MMU_REQUIRED_STATE=off
  ENTRY_DCACHE_REQUIRED_STATE=off
  ENTRY_ICACHE_REQUIRED_STATE=on_or_off_no_stale
  Image: text_offset bytes from a 2MB-aligned base; ≥image_size bytes free
  DTB: 8-byte aligned, ≤2MiB, not in a 2MB block that needs special attrs
  DTB lifetime: readable/writable through early boot / unflatten
  initrd: if present, inside a 1GB-aligned ≤32GB window covering the Image
```

`head.S` comment at `primary_entry`:

```text
MMU = off, D-cache = off, I-cache = on or off,
x0 = physical address to the FDT blob.
```

Normal `primary_entry` first instruction is `bl record_mmu_state`, then
`bl preserve_boot_args`, `bl create_idmap`. A first instruction of `b .`
is M4B/M5D spin and is FAIL for a clean Image.

`record_mmu_state` / `init_kernel_el` can observe MMU-on+D-cache-on (EFI
stub path) and later write `INIT_SCTLR_ELx_MMU_OFF`. That is **not** the
ABL contract:

- Protocol: MMU must be off. D-cache off. Image cleaned to PoC.
- If C==0, `record_mmu_state` clears x19 even if M==1, then
  `preserve_boot_args` takes the MMU-off invalidation path.
- Kernel does not “just turn MMU off” as a general ABL fix.

Previous wording “MMU=off (kernel可自行关)” is withdrawn.

---

## 6. ABL EL / MMU / cache evidence

ABL source is not in this tree. Xiaomi thyme ABL is QcomModulePkg
LinuxLoader (inferred same generation as SM8250 CAF).

```text
ABL_HANDOFF_CURRENTEL=LIKELY   EL1 or EL2, not EL3
  evidence: P0 SMC 0x84000009 produced SYSTEM_RESET; EL3 would not SMC
  confidence: MEDIUM
ABL_HANDOFF_MMU=UNKNOWN
  P0 PC-relative code ran; identity map if MMU-on is unproven
  confidence: none as a Linux contract
ABL_HANDOFF_DCACHE=UNKNOWN
ABL_HANDOFF_ICACHE=LIKELY coherent enough for the loaded payload
  evidence: P0 executed from ABL-loaded bytes
  confidence: MEDIUM for I-cache of shim only
```

P0 does **not** prove the Linux entry contract. Probe design (not executed):

```text
R3_P1_STATE_PROBE_CI
  same P0 geometry (code0 → 0x40), no stack, no RAM store, no SCTLR write
  delay = 8 + 16*(EL==EL2) + 32*(SCTLR_ELx.M) + 64*(SCTLR_ELx.C)
  then PSCI SYSTEM_RESET 0x84000009 SMC
  source: scripts/r3-p1/p1-state-probe.S
```

`TRAMPOLINE_STATE_POLICY=PRESERVE` until a probe says otherwise.
Do not ERET, do not write SCTLR, do not flush all caches on the direct path.

---

## 7. Runtime DTB requirements

Bootshim/trampoline means Linux **must not** consume ABL x0 (Stock vendor
DT + dtbo). The runtime DTB must be self-contained:

```text
FDT magic / totalsize valid
compatible xiaomi,thyme / qcom,sm8250
/memory device_type=memory and nonzero banks
reserved-memory: stock no-map firmware carveouts
CPUs / PSCI (arm,psci-1.0 method=smc) / arm,armv8-timer / GICv3
chosen bootargs explicit
```

Must not depend on ABL dynamic /memory fixup, Stock dtbo overlay, or
vendor_boot DT merge.

---

## 8. RAM map

```text
THYME_PHYSICAL_MEMORY_MAP
```

| item | SOURCE | VALUE | CONFIDENCE |
|---|---|---|---|
| DRAM window class | sm8250.dtsi `memory@80000000` | base 0x80000000, size 0 “bootloader fills” | HIGH as SoC window, NOT a bank map |
| Stock raw /memory | thyme-stock-merged.dts | `reg = <0 0 0 0>` placeholder | HIGH that raw Stock DTB0 is not a RAM map |
| M1 raw DTB | sm8250.dtsi inherited | `memory@80000000` size 0 | HIGH |
| Stock mem-offline | thyme-stock-merged.dts | SKU offlining table, not banks | LOW as size hint, not a map |
| lmi boards | sm8250-xiaomi-lmi.dts | explicit 3-bank map | NONE for thyme (different product) |
| /proc/iomem | not captured | — | MISSING |
| runtime FDT /memory/reg | not captured | — | MISSING |
| Android A MemTotal | not captured | — | MISSING |

Usable RAM banks: **UNKNOWN**. Do not copy lmi banks. Do not invent 8GiB.

---

## 9. Reserved-memory map

Stock merged DT (vendor_boot DTB0 + dtbo entry21), CONFIRMED_STOCK.
Mainline `sm8250.dtsi` matches several PIL windows and **mismatches**
thyme for XBL/SLPI/ADSP/SPSS/secure heap (elish already deletes those).

| region | base | size | SOURCE | CONFIDENCE |
|---|---|---|---|---|
| hyp | 0x80000000 | 0x600000 | stock + sm8250.dtsi | HIGH |
| xbl_aop | 0x80600000 | 0x260000 | stock / elish override | HIGH |
| cmd_db | 0x80860000 | 0x20000 | stock + sm8250.dtsi | HIGH |
| xbl uefi log | 0x80880000 | 0x14000 | stock | HIGH |
| smem | 0x80900000 | 0x200000 | stock + sm8250.dtsi | HIGH |
| removed | 0x80b00000 | 0x5300000 | stock + sm8250.dtsi | HIGH |
| pil camera | 0x86200000 | 0x500000 | stock + sm8250.dtsi | HIGH |
| wlan_fw | 0x86700000 | 0x100000 | stock + sm8250.dtsi | HIGH |
| ipa_fw / gsi / gpu | 0x86800000… | stock-matched | stock + sm8250.dtsi | HIGH |
| npu / video / cvp | 0x86900000… | 0x500000 each | stock + sm8250.dtsi | HIGH |
| cdsp | 0x87800000 | 0x1400000 | stock + sm8250.dtsi | HIGH |
| slpi | 0x88c00000 | 0x2f00000 | stock (dtsi has 0x1500000) | HIGH stock |
| adsp | 0x8bb00000 | 0x2500000 | stock (dtsi 0x8a100000) | HIGH stock |
| spss | 0x8e000000 | 0x100000 | stock (dtsi 0x8be00000) | HIGH stock |
| cdsp_secure_heap | 0x8e100000 | 0x4600000 | stock (dtsi 0x8bf00000) | HIGH stock |
| cont_splash | 0x9c000000 | 0x2300000 | stock | HIGH |
| dfps | 0x9e300000 | 0x100000 | stock | HIGH |
| disp_rdump | 0xb0400000 | 0x1000000 | stock | HIGH |
| ramoops | — | — | stock: absent | HIGH absent |
| modem/mpss | — | — | stock: no PIL node | UNKNOWN path |

Reusable CMA/qseecom pools exist in stock; they are allocator-sized, not
absolute carveouts. Minimal /init PoC may omit them.

---

## 10. M1 raw DTB limitations

```text
historical M1 raw SHA256
  a91a512d4d8699dcae73bff3e0c5a758972e82eaa0b34e87ae1eb1528b9ede40
M5I reproduced byte-for-byte: YES (private run 34572191475)
```

Audit from pinned source (0002 + sm8250.dtsi), M5G/M5I records, and the
M1 ABL packaging DTB (`cefafcca…`, memory@80000000 zero size):

| node | status |
|---|---|
| /memory | size 0 placeholder |
| reserved-memory | SoC generic; slpi/adsp/spss/xbl **wrong vs stock thyme** |
| chosen | stdout-path only; no bootargs |
| CPUs / PSCI / timer / GIC | present via sm8250.dtsi |
| UFS / USB | present in thyme.dts |
| firmware carveouts | incomplete vs stock |
| ABL msm-id / board-id | only on ABL packaging form, not Linux-required |

```text
M1_RAW_DTB_IS_FULL_RUNTIME_BASELINE=NO
M1_RUNTIME_DTB_SELF_CONTAINED=NO
memory valid=NO
reserved-memory valid=NO  (wrong sizes / missing splash+XBL log)
```

M5I symbolized M1 only adds DTC `__symbols__`. It does not fill RAM.

---

## 11. Runtime DTB selection

| id | description | memory | reserved | kernel fidelity | ABL-independent | overlay-independent | maintainability |
|---|---|---|---|---|---|---|---|
| RT-A | historical M1 raw | FAIL size 0 | SoC generic, thyme-wrong | high source | yes if x0 replaced | yes | stale binary |
| RT-B | M5I symbolized M1 | FAIL size 0 | same as RT-A | high | yes | still overlay-incompatible | metadata only |
| RT-C | M1 source + verified static memory/reserved | blocked on RAM banks | stock no-map can be applied | high | yes | yes | good |
| RT-D | dedicated runtime-only DTS | blocked on RAM banks | stock no-map in `scripts/r3-p1/dts/` | high | yes | yes | **preferred** |

```text
R3_RUNTIME_DTB_BASELINE=RT-D
RT-D path: scripts/r3-p1/dts/sm8250-xiaomi-thyme-runtime.dts
self-contained this round: NO
DTB SHA this round: PENDING GHA prototype (will fail memory_nonzero)
```

Do not mix ABL-facing msm-id/board-id into the Linux runtime DTB.
ABL-facing context stays Stock vendor_boot_a + dtbo_a.

---

## 12. Initramfs source

```text
IR-B  new GHA-generated minimal initramfs
source: scripts/r3-p1/p1-init.c
no busybox, no mutable download
BUILT_IN_INITRAMFS=YES
ANDROID_BOOT_RAMDISK_ROLE=M5D/P0 envelope reference only
LINUX_INITRAMFS_ROLE=kernel CONFIG_INITRAMFS_SOURCE → /init
```

IR-A (M0/P15 boot ramdisk, SHA `b7d3949461a57b9855850cfe31ef423ce34216aa9ae164600ffbeed97d5a47de`)
is the known-good Android v3 ramdisk and may remain in the boot header so
ABL packaging stays M5D-shaped. Linux PID 1 must come from the built-in
cpio, not from that ramdisk.

---

## 13. /init design

`/init` is a static ET_EXEC aarch64 ELF, no PT_INTERP, uid 0 gid 0 mode
0755, mtime normalized in GHA.

```text
mount proc
mount sysfs
mount devtmpfs
read /proc/uptime, /proc/cmdline, /proc/device-tree/model  (best-effort)
sleep N
sync
reboot syscall LINUX_REBOOT_CMD_RESTART
failure path: sleep loop
ident: THYME-R3-P1-INIT DELAY=N CMD=restart
```

UFS rootfs is not required for E4. USB is frozen until after E4.

---

## 14. Init timing checkpoint

```text
LINUX_INIT_TIMING_SIGNATURE
INIT-A  DELAY=8s  then RESTART → Android A
INIT-B  DELAY=24s then RESTART → Android A
missing /init: panic=5 → automatic reboot (different host gap)
```

Host metric remains P0-class: BOOTING_OKAY → Android A `kernel_start`
(wallclock − `/proc/uptime`). Expected INIT-A vs INIT-B differential
16s if kernel+init both ran. This round designs only; no device.

---

## 15. Direct trampoline geometry

```text
ARCH-A  DIRECT IN-PLACE X0 TRAMPOLINE     preferred
ARCH-B  APPENDED IMAGE/TRAMPOLINE         not needed if ARCH-A fits
ARCH-C  COPYDOWN                          only if placement/alignment fails
```

Model:

```text
ABL
  → clean Mainline Image (code0 → 0x40, P0 geometry)
  → trampoline: x0 = PC-relative runtime DTB, x1=x2=x3=0
  → PRESERVE EL/MMU/cache
  → B primary_entry  (relative, ~27MiB, within ±128MiB)
NO COPYDOWN
```

Safe trampoline region: Image `[0x40, 0x10000)` EFI stub. P0 proved it
executable. Not head.S idmap, not BSS, not live text. DTB does **not**
fit in that 64KiB hole (M1 DTB 105960 bytes).

Preferred DTB placement: `.incbin` / `.rodata` inside the Image file
(live section, 8-byte aligned, covered by image_size, not BSS). PC-relative
x0 via `adr+ldr+add` / `adrp`. Does not require trailing-load proof.

Forbidden: stuffing file_size→image_size padding. That range is kernel
footprint (M5D file 35101184 vs image_size 0x2220000). Prove with vmlinux
ELF sections + `image_size` in GHA.

Trailer after `image_size`: only if `ABL_LOADS_KERNEL_TRAILING_BYTES=YES`.
Not proven on thyme → BLOCK, not FAIL.

```text
direct trampoline feasible: INCONCLUSIVE (alignment of S unknown)
needs absolute S: NO
PC-relative x0: YES
normal primary_entry branch: YES (±128MiB)
```

---

## 16. Load-address requirement

```text
DIRECT_PATH_NEEDS_ABSOLUTE_S=NO
COPYDOWN_PATH_NEEDS_ABSOLUTE_S=NO for the copy itself (PC-relative)
  YES to prove dest vs reserved RAM / 2MB base numerically
S = ABL runtime address of Image byte 0 = UNKNOWN
```

`BOARD_KERNEL_BASE=0x00000000`, vendor_boot `kernel_addr=0x8000` are
mkbootimg packaging. Not physical S. 0x8000 is not DRAM.

---

## 17. Alignment requirement

Protocol: Image byte 0 sits `text_offset` past a 2MB-aligned base.

```text
S_MOD_2M_REQUIRED=YES     S ≡ text_offset (0x80000) (mod 2MiB)
S_MOD_64K_REQUIRED=NO     not an ARM64 Image placement rule
OTHER_ALIGNMENT_REQUIREMENT=DTB 8-byte; DTB not in a special 2MiB block
MAINLINE_IMAGE_PLACEMENT_VALID=UNKNOWN
```

flags bit3=1 (value 0xa) means 48-bit-range placement, not “near DRAM”.

P0 proved executable placement of a tiny shim, not Linux 2MB alignment.

---

## 18. Bootloader trailing-load behavior

Android boot v3 header `kernel_size` is the payload length. Stock 4.19
kernel ~50.2MiB and M5D/P0 35101184-byte payloads were accepted and
entered. CAF `BootLinux` copies the kernel object described by that
header (Xiaomi fork INFERRED).

```text
ABL_LOADS_FULL_KERNEL_SIZE=YES
  scope: boot header kernel_size
  confidence: HIGH protocol + thyme stock/M5D/P0 acceptance
  Xiaomi C source: INFERRED (not in tree)
ABL_LOADS_KERNEL_TRAILING_BYTES=YES iff those bytes are inside kernel_size
  trailing past ARM64 image_size: NOT_PROVEN on thyme → BLOCK for trailer DTB
```

---

## 19. Cache plan

```text
DIRECT_CACHE_PLAN
  no Image copy. Do not paste lmi dc cvau + ic iallu over the Image.
  ABL already loaded the payload. isb around GPR/x0 setup is enough
  (same class as P0).
COPYDOWN_CACHE_PLAN
  after copy: dc cvau/cvac [dest, dest+len) and DTB to PoC by VA,
  dsb ish, ic iallu, dsb ish, isb.
  booting.rst: loaded kernel image cleaned to PoC; no stale I-cache.
```

---

## 20. ABL-facing Stock context

Future P1 device work, if approved, stays:

```text
R3_P1_ABL_CONTEXT_BASELINE=ACTIVE_A_STOCK
fastboot boot  (temporary)
current-slot a
Stock vendor_boot_a + Stock dtbo_a
PARTITION_WRITES=0
P0 precedent: PROVEN
```

Linux runtime DTB is independent of that ABL-facing pair.

Current B (M5D+M5H+M5M-B) is not touched.

---

## 21. Frozen M5N / hardware scope

```text
M5N_TARGETING_ISOLATION=FROZEN
target-path family ~4.8s / target+fixup family >12s is enough causality
```

Frozen until P1 is shown infeasible or a new ABL-facing context is
required.

Nonessential hardware FROZEN: display, audio, camera, modem, touch,
sensor, GPU, Wi-Fi, Bluetooth, charging.

Keep: CPU, memory, interrupt, timer, PSCI. UFS later. USB after /init.

---

## 22. Blockers

```text
NORMAL_IMAGE     source locked; P1 binary PENDING pinned GHA rebuild
RUNTIME_DTB      RT-D chosen; not self-contained
RAM_MAP          usable banks UNKNOWN          ← primary
RESERVED_MEMORY  stock no-map map KNOWN
INITRAMFS        source+design closed; GHA prototype
ENTRY_STATE      EL LIKELY, MMU/D-cache UNKNOWN
ALIGNMENT        S mod 2MiB UNKNOWN
GEOMETRY         ARCH-A preferred, INCONCLUSIVE on alignment
COPYDOWN         not required yet
```

CI fail-closed (GHA):

- Image: 6.6.156, normal primary_entry, no `b .`, pinned commit/patches
- DTB: FDT valid, compatible, **memory nonzero or contract=NO**
- initramfs: `/init` exec, uid/gid/mode, deterministic, config includes it
- entry state UNKNOWN ⇒ cannot become device-ready
- overlap / out-of-range B / relocs / boot v3 / kernel_size ⇒ FAIL
- trailing bytes not proven loaded ⇒ BLOCK trailer DTB

---

## 23. Recommended next stage

Not `MAINLINE_V2_R3_P1B_MINIMAL_LINUX_ENTRY_CI` yet.

```text
next: R3_RUNTIME_DTB_COMPLETION_CI
```

Need a bounded **read-only Android A** capture (separate approval):

```text
/proc/iomem
/proc/meminfo
/proc/device-tree/memory/reg
```

Then fill RT-D `/memory` banks. Do not flash. Do not touch Slot A.

If RAM is closed and EL/MMU remain UNKNOWN, run designed
`R3_ENTRY_STATE_PROBE_CI` (fastboot boot, 0 writes) before true Linux.

Copydown only if ARCH-A alignment/placement is disproven.

---

## Contract A — NORMAL IMAGE

Clean lineage is M0-class 6.6.156 without m2/m3/m4b. Exact M5D Image is
excluded. P1 payload must be GHA-rebuilt with built-in initramfs.

## Contract B — RUNTIME DTB / RAM / RESERVED

RT-D selected. Reserved-memory can be stock-accurate now. RAM banks cannot.
`M1_RUNTIME_DTB_SELF_CONTAINED=NO`.

## Contract C — INITRAMFS + /init

`BUILT_IN_INITRAMFS=YES`. Static `p1-init.c`. Timing pair 8s/24s designed.

## Contract D — EL / MMU / CACHE / REGS

Protocol: x0=DTB, x1=x2=x3=0, EL1/EL2 NS, DAIF masked,
`ENTRY_MMU_REQUIRED_STATE=off`, `ENTRY_DCACHE_REQUIRED_STATE=off`,
I-cache on or off. ABL MMU/D-cache UNKNOWN. Policy PRESERVE + probe.

## Contract E — HANDOFF GEOMETRY / x0 / ENTRY

ARCH-A. `DIRECT_PATH_NEEDS_ABSOLUTE_S=NO`. `S_MOD_2M_REQUIRED=YES`.
DTB PC-relative inside Image .rodata preferred. Trailer BLOCKED.

---

## Cmdline

```text
R3_MINIMAL_CMDLINE=rdinit=/init panic=5 loglevel=7
```

earlycon/console are optional and must not be success dependencies (no UART).

---

## Constraints recap

```text
mem0 read: YES
local build: NO
GHA-only: YES
device operation: NO
Slot A written: NO
```
