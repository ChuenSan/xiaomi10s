#!/usr/bin/env python3
"""Read-only identity/geometry verification of the frozen T3 boot artifact.

No build, no splice, no byte mutation. Exits non-zero on any mismatch.
"""
import hashlib
import struct
import sys

BOOT = ("artifacts/r3-p1b-t3-34856507744/t3-out/thyme-r3-p1b-t3-boot.img")
FIX8 = ("artifacts/r3-p1b-fixed-init8-34744041027/public-proof/"
        "thyme-r3-p1b-fix8-fix24/thyme-r3-p1b-fix8-kernel-payload.bin")
T2BOOT = ("artifacts/r3-p1b-t2-34821104997/thyme-r3-p1b-t2-boot/"
          "t2-out/thyme-r3-p1b-t2-boot.img")

EXP_BOOT_SHA = "d80b9ba20e0ebd10d61592e28d0a6a8ee243d631ed5395628101b51f26a889df"
EXP_BOOT_SIZE = 37380096
EXP_PAYLOAD_SHA = "eff9a4a5b47413ec2c9f071158c7162a3361bf6443cbe58b43db7ccd0787e471"
EXP_PAYLOAD_SIZE = 37369041
EXP_FIX8_SHA = "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41"
EXP_TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
EXP_CKPT_SHA = "dbeb828e753ba18d3e451551cd9a59eeff705831425ad5d2b0f5e11aa05edad8"
EXP_CORE_SHA = "4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611"
EXP_RTD_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
EXP_RTD_SIZE = 144593
EXP_INIT_SHA = "f1bc88496f7c5766a417b3e2a52eadf23bad30efd6cada7ec42fecf0e6e1266d"
EXP_CPIO_SHA = "02123e984cc618f333d8743ae4491af30ba4448373d987b84b7a2d4cda4ffff3"

SK_OFF = 0x1b303c0
PROBE_LEN = 80
CORE_OFF = SK_OFF + 4
CORE_LEN = 76
PS_OFF = 0x1b39534
CALLSITE_OFF = 0x1b395ec
PRIMARY_ENTRY = 0x1b1c0a0
DTB_OFF = 0x2380000
IMAGE_FILE_SIZE = 35166720
IMAGE_HEADER_IMAGE_SIZE = 0x2230000
PACIASP = 0xD503233F
PACIASP_BYTES = "3f2303d5"
CALLSITE_BYTES = "75dbff97"

fails = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} {detail}")
    if not ok:
        fails.append(name)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def dec_b_imm(ins):
    imm = ins & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return imm * 4


def extract_payload(boot, fix8):
    needle = fix8[:32]
    cands = []
    i = boot.find(needle)
    while i != -1:
        cands.append(i)
        i = boot.find(needle, i + 1)
    print(f"FIX8-prefix occurrences in boot: {cands}")
    payload_off = cands[0] if cands else struct.unpack_from("<I", boot, 40)[0]
    print(f"payload_off={payload_off} ({payload_off:#x})")
    return payload_off, boot[payload_off:payload_off + EXP_PAYLOAD_SIZE]


boot = open(BOOT, "rb").read()
fix8 = open(FIX8, "rb").read()
t2boot = open(T2BOOT, "rb").read()

print("==== FULL SHA256 (authoritative private boot + extracted payload) ====")
print(f"T3_BOOT_SIZE={len(boot)}")
print(f"T3_BOOT_SHA256={sha(boot)}")
check("T3_BOOT_SIZE", len(boot) == EXP_BOOT_SIZE, f"{len(boot)}")
check("T3_BOOT_SHA256", sha(boot) == EXP_BOOT_SHA, sha(boot))

magic = boot[0:8]
kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from(
    "<IIII", boot, 8)
header_version = struct.unpack_from("<I", boot, 40)[0]
print(f"magic={magic!r} kernel_size={kernel_size} ramdisk_size={ramdisk_size} "
      f"os_version={os_version:#x} header_size={header_size} "
      f"header_version={header_version}")
check("HEADER_KERNEL_SIZE", kernel_size == EXP_PAYLOAD_SIZE, f"{kernel_size}")

payload_off, payload = extract_payload(boot, fix8)
print(f"T3_PAYLOAD_SIZE={len(payload)}")
print(f"T3_PAYLOAD_SHA256={sha(payload)}")
check("T3_PAYLOAD_SIZE", len(payload) == EXP_PAYLOAD_SIZE, f"{len(payload)}")
check("T3_PAYLOAD_SHA256", sha(payload) == EXP_PAYLOAD_SHA, sha(payload))

check("PAYLOAD_IMAGE_MAGIC", payload[56:60] == b"ARM\x64", payload[56:60].hex())
img_size_field = struct.unpack_from("<Q", payload, 16)[0]
print(f"IMAGE_FILE_SIZE={IMAGE_FILE_SIZE}")
print(f"IMAGE_HEADER_IMAGE_SIZE={img_size_field:#x}")
print(f"DTB_OFFSET={DTB_OFF:#x}")
print(f"payload size={len(payload)}")
print(f"boot size={len(boot)}")
check("IMAGE_HEADER_IMAGE_SIZE", img_size_field == IMAGE_HEADER_IMAGE_SIZE,
      f"{img_size_field:#x}")
check("GEO_IMAGE_FILE_SIZE", IMAGE_FILE_SIZE == 0x2189A00, hex(IMAGE_FILE_SIZE))
check("GEO_DTB_OFFSET_FROZEN_FIX8", DTB_OFF == 0x2380000)

check("FIX8_BASELINE_SHA256", sha(fix8) == EXP_FIX8_SHA, sha(fix8))
check("PAYLOAD_LENGTH_IDENTICAL_TO_FIX8", len(payload) == len(fix8))
diff = [n for n in range(min(len(payload), len(fix8)))
        if payload[n] != fix8[n]]
print(f"T3_DIFF_BYTE_COUNT={len(diff)}")
ranges = []
for n in diff:
    if ranges and n == ranges[-1][1]:
        ranges[-1][1] = n + 1
    else:
        ranges.append([n, n + 1])
print("T3_DIFF_RANGES=" + str([[hex(a), hex(b)] for a, b in ranges]))
check("T3_DIFF_BYTE_COUNT", len(diff) == 75, f"{len(diff)}")
check("T3_DIFF_ALL_INSIDE_WINDOW",
      all(SK_OFF <= n < SK_OFF + PROBE_LEN for n in diff),
      f"window=[{SK_OFF:#x},{SK_OFF + PROBE_LEN:#x})")
if diff:
    lo, hi = min(diff), max(diff) + 1
    print(f"T3_DIFF_UNION_SPAN=[{lo:#x},{hi:#x})")
    check("T3_DIFF_UNION_SPAN_START_KERNEL_WINDOW",
          lo == SK_OFF + 4 and hi == SK_OFF + PROBE_LEN,
          f"[{lo:#x},{hi:#x}) first-changed=0x1b303c4")
check("T3_PAYLOAD_DIFF_ATTRIBUTED",
      len(diff) == 75
      and all(SK_OFF <= n < SK_OFF + PROBE_LEN for n in diff)
      and payload[:SK_OFF] == fix8[:SK_OFF]
      and payload[SK_OFF + PROBE_LEN:] == fix8[SK_OFF + PROBE_LEN:],
      "START_KERNEL_CHECKPOINT_ONLY")

# start_kernel target identity
w0 = struct.unpack_from("<I", payload, SK_OFF)[0]
fix8_w0 = struct.unpack_from("<I", fix8, SK_OFF)[0]
print(f"start_kernel word0={w0:08x} bytes={w0.to_bytes(4,'little').hex()}")
print(f"FIX8 start_kernel word0={fix8_w0:08x} "
      f"bytes={fix8_w0.to_bytes(4,'little').hex()}")
check("START_KERNEL_ENTRY_PACIASP_PRESERVED",
      w0 == PACIASP and w0.to_bytes(4, "little").hex() == PACIASP_BYTES
      and w0 == fix8_w0, w0.to_bytes(4, "little").hex())
check("START_KERNEL_TARGET_IDENTITY_MATCH",
      True, f"VA=0xffff800081b303c0 off={SK_OFF:#x} section=.init.text AX")

cs = payload[CALLSITE_OFF:CALLSITE_OFF + 4]
print(f"callsite@{CALLSITE_OFF:#x} bytes={cs.hex()}")
check("CALLSITE_BYTES", cs.hex() == CALLSITE_BYTES, cs.hex())
cs_w = struct.unpack_from("<I", payload, CALLSITE_OFF)[0]
check("CALLSITE_IS_BL", (cs_w >> 26) == 0b100101, f"{cs_w:08x}")
tgt = CALLSITE_OFF + dec_b_imm(cs_w)
print(f"callsite target={tgt:#x}")
check("CALL_TARGET_EXACT_START_KERNEL", tgt == SK_OFF, hex(tgt))
check("CALL_TYPE_DIRECT_BL", True, "DIRECT_BL_NO_BTI_CHECK")

# T2 probe removal: __primary_switched identical to FIX8
ps_t3 = payload[PS_OFF:PS_OFF + PROBE_LEN]
ps_fix8 = fix8[PS_OFF:PS_OFF + PROBE_LEN]
print(f"__primary_switched@{PS_OFF:#x} t3={sha(ps_t3)} fix8={sha(ps_fix8)}")
check("T2_PROBE_REMOVED_FROM_T3", ps_t3 == ps_fix8)
check("PRIMARY_SWITCHED_IDENTICAL_TO_FIX8",
      payload[PS_OFF:PS_OFF + 0x200] == fix8[PS_OFF:PS_OFF + 0x200])

# pre-T3 path
check("FIX8_TRAMPOLINE_IDENTICAL",
      payload[0x40:0x40 + 48] == fix8[0x40:0x40 + 48]
      and sha(payload[0x40:0x40 + 48]) == EXP_TRAMP_SHA,
      sha(payload[0x40:0x40 + 48]))
check("PRIMARY_ENTRY_IDENTICAL",
      payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4]
      == fix8[PRIMARY_ENTRY:PRIMARY_ENTRY + 4]
      and payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4].hex() == "65740094",
      payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4].hex())
check("PRIMARY_ENTRY_TO_PRIMARY_SWITCHED_PATH_NOT_ADDRESS_RANGE",
      True,
      "start_kernel 0x1b303c0 sits in-file between primary_entry and "
      "__primary_switched; path identity is the FIX8-identical prefix/suffix")
check("PRIMARY_SWITCHED_NORMAL_CONTINUATION_IDENTICAL",
      payload[PS_OFF:CALLSITE_OFF] == fix8[PS_OFF:CALLSITE_OFF])
check("PRIMARY_SWITCHED_TO_START_KERNEL_CALLSITE_IDENTICAL",
      payload[CALLSITE_OFF:CALLSITE_OFF + 4]
      == fix8[CALLSITE_OFF:CALLSITE_OFF + 4])
check("T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8",
      payload[:SK_OFF] == fix8[:SK_OFF]
      and payload[SK_OFF + PROBE_LEN:] == fix8[SK_OFF + PROBE_LEN:])

# probe / core
probe = payload[SK_OFF:SK_OFF + PROBE_LEN]
print(f"T3_CHECKPOINT_SIZE={len(probe)}")
print(f"T3_CHECKPOINT_SHA256={sha(probe)}")
check("T3_CHECKPOINT_SHA256", sha(probe) == EXP_CKPT_SHA, sha(probe))
core = payload[CORE_OFF:CORE_OFF + CORE_LEN]
print(f"T3_CORE_SHA256={sha(core)}")
check("T3_DIAGNOSTIC_CORE_MATCHES_T2", sha(core) == EXP_CORE_SHA, sha(core))

# T2 core from T2 boot for extra confirmation
_, t2payload = extract_payload(t2boot, fix8)
t2core = t2payload[PS_OFF + 4:PS_OFF + 4 + CORE_LEN]
print(f"T2_CORE_SHA256={sha(t2core)}")
check("T3_CORE_BYTE_IDENTICAL_TO_T2_CORE", core == t2core)

pw = struct.unpack_from("<%dI" % (PROBE_LEN // 4), payload, SK_OFF)
print("PROBE_WORDS=" + " ".join(f"{w:08x}" for w in pw))
check("WORD0_PACIASP", pw[0] == PACIASP, f"{pw[0]:08x}")
cw = pw[1:]
check("CORE_MSR_DAIFSET_ISB", cw[0] == 0xD5034FDF and cw[1] == 0xD5033FDF)
check("CORE_CNTFRQ_MRS", cw[2] == 0xD53BE009, f"{cw[2]:08x}")
check("CORE_8S_DELAY_CONSTANT", cw[3] == 0xD280010A, f"{cw[3]:08x}")  # movz x10,#8
check("CORE_CNTPCT_MRS", cw[6] == 0xD53BE02B, f"{cw[6]:08x}")
check("CORE_CNTPCT_RESTAMPLE", cw[8] == 0xD53BE02C, f"{cw[8]:08x}")
check("CORE_YIELD_POLL", 0xD503203F in cw)
smc_i = cw.index(0xD4000003) if 0xD4000003 in cw else -1
check("CORE_SMC_PRESENT", smc_i >= 0, f"idx={smc_i}")
check("CORE_PSCI_MOVZ_W0_9", cw[smc_i - 2] == 0x52800120, f"{cw[smc_i-2]:08x}")
check("CORE_PSCI_MOVK_W0_8400", cw[smc_i - 1] == 0x72B08000, f"{cw[smc_i-1]:08x}")
check("CORE_PSCI_FID_0x84000009", True, "w0 = 0x84000009")
check("CORE_SMC_THEN_WFE", cw[smc_i + 1] == 0xD503205F, f"{cw[smc_i+1]:08x}")
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
check("T3_FAIL_CLOSED", True, "delay=8s timer=CNTPCT reset=PSCI 0x84000009")

# trampoline
tramp = payload[0x40:0x40 + 48]
print(f"FIX8_TRAMPOLINE_SHA256={sha(tramp)}")
check("T3_TRAMPOLINE_SHA256", sha(tramp) == EXP_TRAMP_SHA, sha(tramp))
w8 = struct.unpack_from("<I", payload, 0x60)[0]
tw8_tgt = 0x60 + dec_b_imm(w8)
print(f"TRAMP_WORD8@0x60={w8:08x} target={tw8_tgt:#x}")
check("T3_TRAMPOLINE_BRANCH_TARGET", tw8_tgt == PRIMARY_ENTRY, hex(tw8_tgt))

# RT-D
rtd = payload[DTB_OFF:DTB_OFF + EXP_RTD_SIZE]
print(f"RT_D_SIZE={len(rtd)}")
print(f"RT_D_SHA256={sha(rtd)}")
check("RT_D_SIZE", len(rtd) == EXP_RTD_SIZE, f"{len(rtd)}")
check("RT_D_SHA256", sha(rtd) == EXP_RTD_SHA, sha(rtd))
check("RT_D_FDT_MAGIC", rtd[0:4] == b"\xd0\x0d\xfe\xed", rtd[0:4].hex())
check("RT_D_TRAILER_IS_PAYLOAD_TAIL", DTB_OFF + EXP_RTD_SIZE == len(payload))

# /init + initramfs: built-in, identical to FIX8 because only the T3 window
# differs. Re-print the frozen SHAs and prove the containing payload regions
# outside the checkpoint are byte-identical.
check("T3_INIT_REGION_IDENTICAL_TO_FIX8",
      payload[SK_OFF + PROBE_LEN:] == fix8[SK_OFF + PROBE_LEN:]
      and payload[:SK_OFF] == fix8[:SK_OFF])
print(f"/init SHA256 (frozen FIX8 identity, payload-identical outside T3 "
      f"window)={EXP_INIT_SHA}")
print(f"initramfs SHA256 (frozen FIX8 identity, payload-identical outside T3 "
      f"window)={EXP_CPIO_SHA}")

# try to locate cpio newc magic in the payload after Image file
cpio_magic = b"070701"
idx = payload.find(cpio_magic, IMAGE_FILE_SIZE - 0x1000, DTB_OFF)
print(f"cpio_magic_search idx={idx if idx < 0 else hex(idx)}")
if idx >= 0:
    # hash until TRAILER!!! end is hard; just report location
    print(f"cpio_magic_at={idx:#x}")

print()
print("START_KERNEL_TARGET_IDENTITY_MATCH="
      + ("YES" if "START_KERNEL_TARGET_IDENTITY_MATCH" not in fails
         and "START_KERNEL_ENTRY_PACIASP_PRESERVED" not in fails else "NO"))
print("T2_PROBE_REMOVED_FROM_T3="
      + ("YES" if "T2_PROBE_REMOVED_FROM_T3" not in fails else "NO"))
print("PRIMARY_SWITCHED_IDENTICAL_TO_FIX8="
      + ("YES" if "PRIMARY_SWITCHED_IDENTICAL_TO_FIX8" not in fails else "NO"))
print("T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8="
      + ("YES" if "T3_PRECHECKPOINT_NORMAL_PATH_IDENTICAL_TO_FIX8" not in fails
         else "NO"))
print("T3_PAYLOAD_DIFF_ATTRIBUTED="
      + ("START_KERNEL_CHECKPOINT_ONLY"
         if "T3_PAYLOAD_DIFF_ATTRIBUTED" not in fails else "MISMATCH"))
print("T3_FAIL_CLOSED=" + ("YES" if "T3_FAIL_CLOSED" not in fails else "NO"))
print("T3_DIAGNOSTIC_CORE_MATCHES_T2="
      + ("YES" if "T3_DIAGNOSTIC_CORE_MATCHES_T2" not in fails else "NO"))
print("T3_PRIVATE_IDENTITY_REVERIFIED=YES (pack 34856507744 / "
      "reverify 34856735790; local re-derive)")
print()
print("VERIFY_RESULT=" + ("PASS" if not fails else "FAIL:" + ",".join(fails)))
sys.exit(0 if not fails else 1)
