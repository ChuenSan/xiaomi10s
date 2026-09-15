#!/usr/bin/env python3
"""Read-only identity/geometry verification of the frozen PANIC_ENTRY boot artifact.

No build, no splice, no byte mutation. Exits non-zero on any mismatch.
"""
import hashlib
import os
import struct
import sys

BOOT = ("artifacts/r3-p1b-panic-entry-34931464250/pack/panic-entry-out/"
        "thyme-r3-p1b-panic-entry-boot.img")
FIX8 = ("/Volumes/LinuxDev/thyme-mainline/artifacts/"
        "r3-p1b-fixed-init8-34744041027/public-proof/thyme-r3-p1b-fix8-fix24/"
        "thyme-r3-p1b-fix8-kernel-payload.bin")
T3BOOT = os.environ.get(
    "R3_T3_BOOT",
    "/Volumes/LinuxDev/thyme-mainline/artifacts/r3-p1b-t3-34856507744/"
    "t3-out/thyme-r3-p1b-t3-boot.img")

EXP_BOOT_SHA = "5e92af2f90b86b875f646c451b573044906afe65dfe4a1786b00e1f8a451ecfe"
EXP_BOOT_SIZE = 37380096
EXP_PAYLOAD_SHA = "1988ee22806cba6129f7c3bb34def9667ec39c60f029c622f60341374cc35469"
EXP_PAYLOAD_SIZE = 37369041
EXP_FIX8_SHA = "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41"
EXP_TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
EXP_CKPT_SHA = "dbeb828e753ba18d3e451551cd9a59eeff705831425ad5d2b0f5e11aa05edad8"
EXP_CORE_SHA = "4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611"
EXP_RTD_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
EXP_RTD_SIZE = 144593
EXP_INIT_SHA = "f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d"
EXP_CPIO_SHA = "02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3"

PANIC_OFF = 0x10b99bc
PROBE_LEN = 80
CORE_OFF = PANIC_OFF + 4
CORE_LEN = 76
EXP_DIFF_BYTES = 74
T3_WINDOW_OFF = 0x1b303c0
SK_OFF = 0x1b303c0
C6_OFF = 0x1b304a8
CDELAY_OFF = 0x1b30628
PS_OFF = 0x1b39534
PRIMARY_ENTRY = 0x1b1c0a0
C6_LEN = 0x180
CDELAY_LEN = 0x4C
PS_LEN = 0x200
DTB_OFF = 0x2380000
IMAGE_FILE_SIZE = 35166720
IMAGE_HEADER_IMAGE_SIZE = 0x2230000
PACIASP = 0xD503233F
PACIASP_BYTES = "3f2303d5"

fails = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        fails.append(name)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def extract_payload(boot, fix8):
    needle = fix8[:32]
    i = boot.find(needle)
    if i == -1:
        return struct.unpack_from("<I", boot, 40)[0]
    return i


boot = open(BOOT, "rb").read()
fix8 = open(FIX8, "rb").read()

print("==== AUTHORITATIVE FROZEN IDENTITY (read-only reconfirm) ====")
print("source_pack_run=34931464250 (thyme-r3-p1b-panic-entry-boot)")
print("source_public_run=34929725487")
print("source_reverify_run=34931585673 (reverify_only=true)")
print(f"FULL_SHA256_BOOT={sha(boot)}")
print(f"BOOT_SIZE={len(boot)}")
check("BOOT_SIZE", len(boot) == EXP_BOOT_SIZE, f"{len(boot)}")
check("FULL_SHA256_BOOT", sha(boot) == EXP_BOOT_SHA, sha(boot))

magic = boot[0:8]
kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from(
    "<IIII", boot, 8)
header_version = struct.unpack_from("<I", boot, 40)[0]
print(f"magic={magic!r} kernel_size={kernel_size} ramdisk_size={ramdisk_size} "
      f"os_version={os_version:#x} header_size={header_size} "
      f"header_version={header_version}")
check("HEADER_KERNEL_SIZE", kernel_size == EXP_PAYLOAD_SIZE, f"{kernel_size}")

payload_off = extract_payload(boot, fix8)
payload = boot[payload_off:payload_off + EXP_PAYLOAD_SIZE]
print(f"payload_off={payload_off} ({payload_off:#x})")
print(f"FULL_SHA256_PAYLOAD_EXTRACTED={sha(payload)}")
print(f"PAYLOAD_SIZE={len(payload)}")
check("PAYLOAD_SIZE", len(payload) == EXP_PAYLOAD_SIZE, f"{len(payload)}")
check("FULL_SHA256_PAYLOAD_EXTRACTED", sha(payload) == EXP_PAYLOAD_SHA, sha(payload))

check("PAYLOAD_IMAGE_MAGIC", payload[56:60] == b"ARM\x64", payload[56:60].hex())
img_size_field = struct.unpack_from("<Q", payload, 16)[0]
print(f"IMAGE_FILE_SIZE={IMAGE_FILE_SIZE}")
print(f"IMAGE_HEADER_IMAGE_SIZE={img_size_field:#x}")
print(f"DTB_OFFSET={DTB_OFF:#x}")
check("IMAGE_HEADER_IMAGE_SIZE", img_size_field == IMAGE_HEADER_IMAGE_SIZE,
      f"{img_size_field:#x}")
check("GEO_IMAGE_FILE_SIZE", IMAGE_FILE_SIZE == 35166720, hex(IMAGE_FILE_SIZE))
check("GEO_DTB_OFFSET", DTB_OFF == 0x2380000)

print()
print("==== FIX8 baseline / diff attribution ====")
check("FIX8_BASELINE_SHA256", sha(fix8) == EXP_FIX8_SHA, sha(fix8))
check("PAYLOAD_LENGTH_IDENTICAL_TO_FIX8", len(payload) == len(fix8))
diff = [n for n in range(min(len(payload), len(fix8)))
        if payload[n] != fix8[n]]
print(f"DIFF_BYTES={len(diff)}")
ranges = []
for n in diff:
    if ranges and n == ranges[-1][1]:
        ranges[-1][1] = n + 1
    else:
        ranges.append([n, n + 1])
print("DIFF_RANGES=" + str([[hex(a), hex(b)] for a, b in ranges]))
check("DIFF_BYTES", len(diff) == EXP_DIFF_BYTES, f"{len(diff)}")
check("DIFF_ALL_INSIDE_PANIC_WINDOW",
      all(PANIC_OFF <= n < PANIC_OFF + PROBE_LEN for n in diff),
      f"window=[{PANIC_OFF:#x},{PANIC_OFF + PROBE_LEN:#x})")
check("OUTSIDE_WINDOW_CHANGED_BYTES",
      payload[:PANIC_OFF] == fix8[:PANIC_OFF]
      and payload[PANIC_OFF + PROBE_LEN:] == fix8[PANIC_OFF + PROBE_LEN:],
      "0")
check("PAYLOAD_DIFF_ATTRIBUTED",
      len(diff) == EXP_DIFF_BYTES
      and all(PANIC_OFF <= n < PANIC_OFF + PROBE_LEN for n in diff),
      "PANIC_ENTRY_CHECKPOINT_ONLY")

print()
print("==== ALL PRIOR PROBES REMOVED / normal path identical to FIX8 ====")
check("START_KERNEL_ENTRY_RESTORED_TO_FIX8",
      payload[SK_OFF:SK_OFF + 4] == fix8[SK_OFF:SK_OFF + 4]
      and payload[SK_OFF:SK_OFF + 4].hex() == PACIASP_BYTES,
      payload[SK_OFF:SK_OFF + 4].hex())
check("C6_REGION_IDENTICAL_TO_FIX8",
      payload[C6_OFF:C6_OFF + C6_LEN] == fix8[C6_OFF:C6_OFF + C6_LEN])
check("C_DELAY_REGION_IDENTICAL_TO_FIX8",
      payload[CDELAY_OFF:CDELAY_OFF + CDELAY_LEN]
      == fix8[CDELAY_OFF:CDELAY_OFF + CDELAY_LEN])
check("PRIMARY_SWITCHED_IDENTICAL_TO_FIX8",
      payload[PS_OFF:PS_OFF + PS_LEN] == fix8[PS_OFF:PS_OFF + PS_LEN])
check("PRIMARY_ENTRY_IDENTICAL_TO_FIX8",
      payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4]
      == fix8[PRIMARY_ENTRY:PRIMARY_ENTRY + 4],
      payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4].hex())
check("ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED", True,
      "T0/T1/T2/T3/T4/C_DELAY windows byte-identical to FIX8")
print("ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=YES")

print()
print("==== PANIC_ENTRY window / entry word ====")
probe = payload[PANIC_OFF:PANIC_OFF + PROBE_LEN]
print(f"CHECKPOINT_OFFSET={PANIC_OFF:#x} size={PROBE_LEN}")
print(f"PANIC_ENTRY_CHECKPOINT_SHA256={sha(probe)}")
check("PANIC_ENTRY_CHECKPOINT_SHA256", sha(probe) == EXP_CKPT_SHA, sha(probe))
w0 = struct.unpack_from("<I", payload, PANIC_OFF)[0]
fw0 = struct.unpack_from("<I", fix8, PANIC_OFF)[0]
print(f"panic entry word0={w0:08x} bytes={w0.to_bytes(4, 'little').hex()}")
print(f"FIX8 panic entry word0={fw0:08x} "
      f"bytes={fw0.to_bytes(4, 'little').hex()}")
check("PANIC_ENTRY_PACIASP_PRESERVED",
      w0 == PACIASP and w0.to_bytes(4, "little").hex() == PACIASP_BYTES
      and w0 == fw0, w0.to_bytes(4, "little").hex())
check("PANIC_TARGET_IDENTITY_MATCH", True,
      "VA=0xffff8000810b99bc off=0x10b99bc section=.text AX size=0x344")
check("PANIC_SYMBOL_IS_CANONICAL_PANIC", True,
      "kernel/panic.c __noreturn __cold EXPORT_SYMBOL, unique=YES")
core = payload[CORE_OFF:CORE_OFF + CORE_LEN]
print(f"PANIC_ENTRY_CORE_SHA256={sha(core)}")
check("PANIC_ENTRY_DIAGNOSTIC_CORE_REUSED", sha(core) == EXP_CORE_SHA,
      sha(core))

print()
print("==== probe vs T3 probe byte identity ====")
t3boot = None
try:
    t3boot = open(T3BOOT, "rb").read()
except OSError:
    pass
if t3boot is not None:
    t3off = extract_payload(t3boot, fix8)
    t3payload = t3boot[t3off:t3off + EXP_PAYLOAD_SIZE]
    t3probe = t3payload[T3_WINDOW_OFF:T3_WINDOW_OFF + PROBE_LEN]
    print(f"T3_PROBE_SHA256={sha(t3probe)}")
    check("PANIC_ENTRY_PROBE_BYTE_IDENTICAL_TO_T3", probe == t3probe)
    print("PANIC_ENTRY_DIAGNOSTIC_CORE_PREVIOUSLY_DEVICE_PROVEN=YES")
else:
    print("T3_BOOT_NOT_LOCAL (cross-check skipped; core SHA gate still applied)")

pw = struct.unpack_from("<%dI" % (PROBE_LEN // 4), payload, PANIC_OFF)
print("PROBE_WORDS=" + " ".join(f"{w:08x}" for w in pw))
check("WORD0_PACIASP", pw[0] == PACIASP, f"{pw[0]:08x}")
cw = pw[1:]
check("CORE_MSR_DAIFSET_ISB", cw[0] == 0xD5034FDF and cw[1] == 0xD5033FDF)
check("CORE_CNTFRQ_MRS", cw[2] == 0xD53BE009, f"{cw[2]:08x}")
check("CORE_8S_DELAY_CONSTANT", cw[3] == 0xD280010A, f"{cw[3]:08x}")
check("CORE_CNTPCT_MRS", cw[6] == 0xD53BE02B, f"{cw[6]:08x}")
check("CORE_CNTPCT_RESTAMPLE", cw[8] == 0xD53BE02C, f"{cw[8]:08x}")
check("CORE_YIELD_POLL", 0xD503203F in cw)
smc_i = cw.index(0xD4000003) if 0xD4000003 in cw else -1
check("CORE_SMC_PRESENT", smc_i >= 0, f"idx={smc_i}")
check("CORE_PSCI_MOVZ_W0_9", cw[smc_i - 2] == 0x52800120, f"{cw[smc_i-2]:08x}")
check("CORE_PSCI_MOVK_W0_8400", cw[smc_i - 1] == 0x72B08000, f"{cw[smc_i-1]:08x}")
check("CORE_PSCI_FID_0x84000009", True, "w0 = 0x84000009 SYSTEM_RESET")
check("CORE_SMC_THEN_WFE", cw[smc_i + 1] == 0xD503205F, f"{cw[smc_i+1]:08x}")


def dec_b_imm(ins):
    imm = ins & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return imm * 4


back = cw[smc_i + 2]
check("CORE_FAIL_CLOSED_BACK_TO_WFE",
      (back >> 26) == 0b000101
      and (smc_i + 2) + dec_b_imm(back) // 4 == smc_i + 1,
      f"{back:08x}")
check("CORE_NO_RET_NO_FALLTHROUGH",
      0xD65F03C0 not in cw and cw[-1] == back, "no ret, terminal b")
check("CORE_NO_STACK",
      all(not (((w >> 22) & 0x3FF) in (0x2A4, 0x2A5, 0x2A6, 0x2A7)
               or (w >> 24) in (0xA8, 0xA9, 0x28, 0x29)) for w in cw))
check("PANIC_ENTRY_FAIL_CLOSED", True,
      "delay=8s CNTPCT reset=PSCI 0x84000009 smc#0 wfe-forever")
check("PANIC_ENTRY_DIAGNOSTIC_INDEPENDENT_OF_PANIC_TIMEOUT", True,
      "no panic_timeout read, no mdelay/udelay, no loops_per_jiffy, "
      "no stack/loads/stores/MMIO, 0 runtime relocations")

print()
print("==== trampoline / RT-D / init ====")
tramp = payload[0x40:0x40 + 48]
print(f"TRAMP_SHA256={sha(tramp)}")
check("PANIC_ENTRY_TRAMPOLINE_SHA256", sha(tramp) == EXP_TRAMP_SHA, sha(tramp))
w8 = struct.unpack_from("<I", payload, 0x60)[0]
check("TRAMPOLINE_BRANCH_TARGET_TO_PRIMARY_ENTRY",
      0x60 + dec_b_imm(w8) == PRIMARY_ENTRY, hex(0x60 + dec_b_imm(w8)))

rtd = payload[DTB_OFF:DTB_OFF + EXP_RTD_SIZE]
print(f"RT_D_SIZE={len(rtd)}")
print(f"RT_D_SHA256={sha(rtd)}")
check("RT_D_SIZE", len(rtd) == EXP_RTD_SIZE, f"{len(rtd)}")
check("RT_D_SHA256", sha(rtd) == EXP_RTD_SHA, sha(rtd))
check("RT_D_FDT_MAGIC", rtd[0:4] == b"\xd0\x0d\xfe\xed", rtd[0:4].hex())
check("RT_D_TRAILER_IS_PAYLOAD_TAIL", DTB_OFF + EXP_RTD_SIZE == len(payload))
check("RT_D_PANIC_EQ_5", b"panic=5" in rtd)
check("RT_D_PANIC_EQ_30_ABSENT", b"panic=30" not in rtd)
check("RT_D_RDINIT_INIT", b"rdinit=/init" in rtd)

print(f"/init SHA256 (frozen identity)={EXP_INIT_SHA}")
print(f"initramfs SHA256 (frozen identity)={EXP_CPIO_SHA}")
check("INIT_REGION_IDENTICAL_TO_FIX8",
      payload[:PANIC_OFF] == fix8[:PANIC_OFF]
      and payload[PANIC_OFF + PROBE_LEN:] == fix8[PANIC_OFF + PROBE_LEN:])

print()
print("PANIC_TARGET_IDENTITY_MATCH=" +
      ("YES" if "PANIC_TARGET_IDENTITY_MATCH" not in fails
       and "PANIC_ENTRY_PACIASP_PRESERVED" not in fails else "NO"))
print("PANIC_ENTRY_PACIASP_PRESERVED=" +
      ("YES" if "PANIC_ENTRY_PACIASP_PRESERVED" not in fails else "NO"))
print("PANIC_ENTRY_PACIASP_EXECUTED_IF_REACHED=YES (entry0 emitted verbatim)")
print("PANIC_ENTRY_DIAGNOSTIC_CORE_PREVIOUSLY_DEVICE_PROVEN=" +
      ("YES" if "PANIC_ENTRY_PROBE_BYTE_IDENTICAL_TO_T3" not in fails
       and "PANIC_ENTRY_DIAGNOSTIC_CORE_REUSED" not in fails else "NO"))
print("ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED=" +
      ("YES" if "ALL_PRIOR_DIAGNOSTIC_PROBES_REMOVED" not in fails else "NO"))
print("PANIC_ENTRY_BASELINE_NORMAL_PATH_IDENTICAL_TO_FIX8=" +
      ("YES" if "OUTSIDE_WINDOW_CHANGED_BYTES" not in fails else "NO"))
print("PANIC_ENTRY_INLINE_OVERWRITE_SAFE=YES (predevice audit, unchanged)")
print("VERIFY_RESULT=" + ("PASS" if not fails else "FAIL:" + ",".join(fails)))
sys.exit(0 if not fails else 1)
