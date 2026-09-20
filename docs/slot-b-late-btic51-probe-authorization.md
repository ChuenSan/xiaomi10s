# Slot B late index-51 BTI-C probe authorization (2026-09-20)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_INDEX51_BTIC_PROBE_AUTHORIZATION_CI`.
CI-only (`DEVICE_BOOT=0`). Final gate:
**`R3_SLOT_B_LATE_INDEX51_BTIC_PROBE_CI_READY`**.

## Round intent

Working diagnostic interval after POST50: `50..55`. Index 50
`clk_debug_init` ENTRY=PROVEN (STRONG). Index 55 `genpd_debug_init` remains
`CHECKPOINT_SHIFT_NOT_OBSERVED`. This round licenses a **new additive**
probe family for the previously excluded BTI-C pad at index 51
`setup_vcpu_hotplug_event`. It does not relax `.text` policy, trampoline /
island, PREL32 retarget, or cross-function overwrite. PACIASP family rules
stay frozen.

## Geometry (fresh GHA, never copied)

| Field | Value |
|---|---|
| symbol | `setup_vcpu_hotplug_event` |
| source | `drivers/xen/cpu_hotplug.c` `late_initcall(...)` |
| target VA / Image | `0xffff800081b87130` / `0x1b87130` |
| table slot / word | `0xffff800081d0c3a4` / `0xffe7ad8c` (PREL32 `-1593972`) |
| section | `.init.text` |
| function | 64 B |
| entry pad | `bti c` `0xD503245F` preserved verbatim |
| window / core | 60 B / 56 B `BTI_C_PLUS_56B_ULTRACOMPACT` |
| tail | `[0x1b8716c,0x1b87170)` original `ret` `0xD65F03C0`, `DEAD_PROVEN` |
| CFG | derived window **exactly 60**; one overwritten interior `cbz +0xc → +0x38`; `surviving_into_interior=[]` |
| window agreement | `EXACT` (bundle Image vs FIX8 over 64 B) |
| pair diff | `[0x1b8713d,0x1b8713f)` `DELAY_CONSTANT_ONLY` (8s `0xD37DF12A` / 1s `0xD340FD2A`) |

Original 64 B decode (bundle vmlinux, matches frozen FIX8): `bti c`;
`adrp/ldr xen_domain`; `cbz` to `mov w0,#-19`; interior `paciasp`/`stp`/`bl
register_xenstore_notifier`/`autiasp`/`ret`; tail `ret`. Diagnostic path is
fail-closed (`smc #0` then `wfe; b`).

## BTI-C semantics

`BTI_C_ENTRY_SEMANTICS_PASS=YES`. Kernel
`CONFIG_ARM64_BTI_KERNEL=y` / `CONFIG_ARM64_BTI=y`. Initcall dispatch is
`do_one_initcall: ret = fn();` (BLR, BTYPE=0b10). Preserved `bti c`
accepts that class and clears BTYPE; the 56 B core has no PAC/RET and
does not restore LR. `bti j` / `bti jc` substitution and pad deletion
are rejected. Design is legal with SCTLR_EL1.BT1 on or off.

## Gate chain (all GHA, no local build)

| Stage | Run | Result |
|---|---|---|
| Public CI (`LATE_INDEX51_BTIC_PROBE_AUTHORIZATION_CI`) | `35484163146` @ `bcddf53` | SUCCESS — 16 geometry gates PASS, BTI sub-gates PASS, tail `DEAD_PROVEN` |
| Private pack | `35484634512` @ private `523614d` | SUCCESS — boots `BTIC51_8` `d0e4cce8…7e7796` / `BTIC51_1` `55379664…5994dd` (37380096) |
| Independent reverify | `35484884319` | SUCCESS (`reverify_only=true`) |
| Identity freeze | `00b06c9` | `observe.py` four SHA constants + `IMAGES["late_btic518/1"]` |
| Observer fixtures | `35485189370` | SUCCESS — family `btic51`, 120 cross-identity rejections |

Payloads: `BTIC51_8` `ae437348164e2ccaa47e4ba238576b6ab05bfda23bd63f18bda48f161b3f88ef`,
`BTIC51_1` `49b9499d2656b7b8b16d39dc9863eb743a1e570a5ee544aea95b6a3a6b4f920e`.

## Runtime evidence (unchanged)

`LATEST_PROVEN_LATE_INDEX=50`. `LATE_INITCALLS_COMPLETED`,
`WAIT_FOR_INITRAMFS_ENTRY`, `WAIT_FOR_INITRAMFS_RETURN`,
`CONSOLE_ON_ROOTFS`, `INIT_EXECUTED` stay `NOT_PROVEN`. `LATE_HIGH1`
stays `NOT_EXECUTED`. No device boot, `PARTITION_WRITES=0`,
`SLOT_A_WRITTEN=NO`. Dirty worktree `/Volumes/LinuxDev/thyme-mainline`
@`5550dc2` untouched.

## Next

After explicit user authorization only:
`MAINLINE_V2_R3_SLOT_B_LATE_INDEX51_BTIC_DEVICE_PAIR` — one RAM-only Slot B
boot per member. STRONG would advance `LATEST_PROVEN_LATE_INDEX` to 51.
This round does **not** auto-switch to index 54 `.text`.
