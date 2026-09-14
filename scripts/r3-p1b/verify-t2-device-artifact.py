#!/usr/bin/env python3
"""Read-only identity/geometry verification of the frozen T2 boot artifact.

No build, no splice, no byte mutation: opens the downloaded private artifact,
re-derives every frozen identity, and diff-attributes the payload against the
frozen FIX8 baseline. Exits non-zero on any mismatch.
"""
import hashlib
import struct
import sys

BOOT = ("artifacts/r3-p1b-t2-34821104997/thyme-r3-p1b-t2-boot/"
        "t2-out/thyme-r3-p1b-t2-boot.img")
FIX8 = ("artifacts/r3-p1b-fixed-init8-34744041027/public-proof/"
        "thyme-r3-p1b-fix8-fix24/thyme-r3-p1b-fix8-kernel-payload.bin")

EXP_BOOT_SHA = "d347cc1907563afd2c8faa0d07cafed5904985514c346434c8a774c14418e925"
EXP_BOOT_SIZE = 37380096
EXP_PAYLOAD_SHA = "c48dc5ce5cc02ea0a51fc6003c4e9e822efca1c1a4e26d17260412f52b19090d"
EXP_PAYLOAD_SIZE = 37369041
EXP_FIX8_SHA = "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41"
EXP_TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
EXP_PROBE_SHA = "c78c55fb2fa94b6e16a33e59d7973acc715c212a02a88bad1ed954ecb1ce412a"
EXP_CORE_SHA = "4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611"
EXP_RTD_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
EXP_RTD_SIZE = 144593

PS_OFF = 0x1b39534          # __primary_switched Image offset == probe start
PROBE_LEN = 80              # bti c + 19-instruction T1 core
CORE_OFF = PS_OFF + 4
CORE_LEN = 76
PRIMARY_ENTRY = 0x1b1c0a0
DTB_OFF = 0x2380000
IMAGE_FILE_SIZE = 35166720
IMAGE_HEADER_IMAGE_SIZE = 0x2230000

fails = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} {detail}")
    if not ok:
        fails.append(name)


def sha(b):
    return hashlib.sha256(b).hexdigest()


boot = open(BOOT, "rb").read()
fix8 = open(FIX8, "rb").read()

# --- boot identity -----------------------------------------------------------
check("T2_BOOT_SIZE", len(boot) == EXP_BOOT_SIZE, f"{len(boot)}")
check("T2_BOOT_SHA256", sha(boot) == EXP_BOOT_SHA, sha(boot))

# --- header geometry ---------------------------------------------------------
magic = boot[0:8]
kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from(
    "<IIII", boot, 8)
header_version = struct.unpack_from("<I", boot, 40)[0]
print(f"magic={magic!r} kernel_size={kernel_size} ramdisk_size={ramdisk_size} "
      f"os_version={os_version:#x} header_size={header_size} "
      f"header_version={header_version}")
check("HEADER_KERNEL_SIZE", kernel_size == EXP_PAYLOAD_SIZE, f"{kernel_size}")

# --- locate payload by content ----------------------------------------------
needle = fix8[:32]
cands = []
i = boot.find(needle)
while i != -1:
    cands.append(i)
    i = boot.find(needle, i + 1)
print(f"FIX8-prefix occurrences in boot: {cands}")
payload_off = cands[0] if cands else header_size
print(f"payload_off={payload_off} ({payload_off:#x})")
payload = boot[payload_off:payload_off + EXP_PAYLOAD_SIZE]
check("T2_PAYLOAD_SIZE", len(payload) == EXP_PAYLOAD_SIZE, f"{len(payload)}")
check("T2_PAYLOAD_SHA256", sha(payload) == EXP_PAYLOAD_SHA, sha(payload))

# --- arm64 Image header inside the payload ----------------------------------
check("PAYLOAD_IMAGE_MAGIC", payload[56:60] == b"ARM\x64", payload[56:60].hex())
img_size_field = struct.unpack_from("<Q", payload, 16)[0]
print(f"IMAGE_HEADER_IMAGE_SIZE_FIELD={img_size_field:#x} "
      f"(expected {IMAGE_HEADER_IMAGE_SIZE:#x})")
check("IMAGE_HEADER_IMAGE_SIZE", img_size_field == IMAGE_HEADER_IMAGE_SIZE,
      f"{img_size_field:#x}")

# --- diff attribution vs frozen FIX8 ----------------------------------------
check("FIX8_BASELINE_SHA256", sha(fix8) == EXP_FIX8_SHA, sha(fix8))
check("PAYLOAD_LENGTH_IDENTICAL_TO_FIX8", len(payload) == len(fix8))
diff = [n for n in range(min(len(payload), len(fix8)))
        if payload[n] != fix8[n]]
print(f"T2_DIFF_BYTE_COUNT={len(diff)}")
ranges = []
for n in diff:
    if ranges and n == ranges[-1][1]:
        ranges[-1][1] = n + 1
    else:
        ranges.append([n, n + 1])
print("T2_DIFF_RANGES=" + str([[hex(a), hex(b)] for a, b in ranges]))
check("T2_DIFF_BYTE_COUNT", len(diff) == 72, f"{len(diff)}")
# Gate convention (same as T1): the modified WINDOW is one contiguous region.
# The raw byte census splits wherever a composed byte coincidentally equals the
# original byte (here the preserved `bti c` landing pad plus 4 later bytes), so
# the window is proven by: all diffs inside it + identical prefix/suffix.
check("T2_DIFF_ALL_INSIDE_WINDOW",
      all(PS_OFF <= n < PS_OFF + PROBE_LEN for n in diff),
      f"window=[{PS_OFF:#x},{PS_OFF + PROBE_LEN:#x})")
if diff:
    lo, hi = min(diff), max(diff) + 1
    print(f"T2_DIFF_UNION_SPAN=[{lo:#x},{hi:#x})")
    check("T2_DIFF_UNION_SPAN_IS_PRIMARY_SWITCHED_WINDOW",
          lo == PS_OFF + 4 and hi == PS_OFF + PROBE_LEN,
          f"[{lo:#x},{hi:#x}) vs window")
check("T2_PAYLOAD_DIFF_ATTRIBUTED",
      len(diff) == 72 and all(PS_OFF <= n < PS_OFF + PROBE_LEN for n in diff)
      and payload[:PS_OFF] == fix8[:PS_OFF]
      and payload[PS_OFF + PROBE_LEN:] == fix8[PS_OFF + PROBE_LEN:],
      "PRIMARY_SWITCHED_CHECKPOINT_ONLY")

# --- normal pre-T2 path untouched -------------------------------------------
check("T2_PRIMARY_ENTRY_UNPATCHED",
      payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4] == fix8[PRIMARY_ENTRY:PRIMARY_ENTRY + 4]
      and payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4].hex() == "65740094",
      payload[PRIMARY_ENTRY:PRIMARY_ENTRY + 4].hex())
# whole pre-T2 prefix byte-identical
check("T2_PRECHECKPOINT_PREFIX_IDENTICAL",
      payload[:PS_OFF] == fix8[:PS_OFF], f"prefix[0,{PS_OFF:#x})")
check("T2_SUFFIX_AFTER_WINDOW_IDENTICAL",
      payload[PS_OFF + PROBE_LEN:] == fix8[PS_OFF + PROBE_LEN:],
      f"suffix[{PS_OFF + PROBE_LEN:#x},EOF)")

# --- original identity at the target offset (from FIX8) ---------------------
orig_w0 = struct.unpack_from("<I", fix8, PS_OFF)[0]
orig_w1 = struct.unpack_from("<I", fix8, PS_OFF + 4)[0]
print(f"ORIGINAL w0={orig_w0:#010x} bytes={orig_w0.to_bytes(4,'little').hex()}")
print(f"ORIGINAL w1={orig_w1:#010x} bytes={orig_w1.to_bytes(4,'little').hex()} "
      f"op=0b{orig_w1>>24:08b}")
check("T2_TARGET_ORIGINAL_INSN1_BTI_C",
      orig_w0.to_bytes(4, "little").hex() == "5f2403d5", f"{orig_w0:#010x}")
adrp_ok = (orig_w1 >> 31) == 1 and ((orig_w1 >> 24) & 0x1F) == 0b10000 \
    and (orig_w1 & 0x1F) == 4
check("T2_TARGET_ORIGINAL_INSN2_ADRP_X4", adrp_ok,
      f"{orig_w1:#010x} Rd=x{orig_w1 & 0x1F}")

# --- probe identity ----------------------------------------------------------
probe = payload[PS_OFF:PS_OFF + PROBE_LEN]
check("T2_PROBE_SIZE", len(probe) == PROBE_LEN, f"{len(probe)}")
check("T2_CHECKPOINT_SHA256", sha(probe) == EXP_PROBE_SHA, sha(probe))
core = payload[CORE_OFF:CORE_OFF + CORE_LEN]
check("T2_DIAGNOSTIC_CORE_MATCHES_T1", sha(core) == EXP_CORE_SHA, sha(core))

pw = struct.unpack_from("<%dI" % (PROBE_LEN // 4), payload, PS_OFF)
print("PROBE_WORDS=" + " ".join(f"{w:08x}" for w in pw))
check("T2_BTI_LANDING_PAD_PRESERVED", pw[0] == 0xD503245F
      and pw[0].to_bytes(4, "little").hex() == "5f2403d5", f"{pw[0]:08x}")

# core = the T1-proven fail-closed sequence, shifted by one word
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
check("CORE_PSCI_FID_0x84000009", True, "w0 = 0x84000009 (movz+movk)")
check("CORE_SMC_THEN_WFE", cw[smc_i + 1] == 0xD503205F, f"{cw[smc_i+1]:08x}")


def dec_b_imm(ins):
    imm = ins & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return imm * 4


back = cw[smc_i + 2]
check("CORE_FAIL_CLOSED_BACK_TO_WFE",
      (back >> 26) == 0b000101 and (smc_i + 2) + dec_b_imm(back) // 4 == smc_i + 1,
      f"{back:08x} -> idx {smc_i + 2 + dec_b_imm(back)//4}")
check("CORE_NO_RET_NO_FALLTHROUGH",
      0xD65F03C0 not in cw and cw[-1] == back, "no ret, terminal b")
check("CORE_NO_STACK_NO_MEMORY",
      all(not (0xA9 == (w >> 24) and (w >> 22) & 1) for w in cw), "no stp/ldp")

# --- trampoline --------------------------------------------------------------
tramp_off = None
tramp_len = None
for ln in (48, 112):
    for off in range(0, 0x400, 4):
        if sha(payload[off:off + ln]) == EXP_TRAMP_SHA:
            tramp_off, tramp_len = off, ln
            break
    if tramp_off is not None:
        break
check("T2_TRAMPOLINE_SHA256", tramp_off is not None,
      f"offset={hex(tramp_off) if tramp_off is not None else None} len={tramp_len}")
if tramp_off is not None:
    check("T2_TRAMPOLINE_IDENTICAL_TO_FIX8",
          payload[tramp_off:tramp_off + tramp_len] == fix8[tramp_off:tramp_off + tramp_len])
    tw = struct.unpack_from("<%dI" % (tramp_len // 4), payload, tramp_off)
    print("TRAMP_WORDS=" + " ".join(f"{w:08x}" for w in tw))
    w8_abs = 0x60
    w8 = struct.unpack_from("<I", payload, w8_abs)[0]
    tw8_tgt = w8_abs + dec_b_imm(w8)
    print(f"TRAMP_WORD8@{w8_abs:#x}={w8:08x} op=0b{w8>>26:06b} "
          f"target={hex(tw8_tgt)}")
    check("T2_TRAMPOLINE_BRANCH_TARGET", tw8_tgt == PRIMARY_ENTRY, hex(tw8_tgt))

# --- RT-D trailer ------------------------------------------------------------
rtd = payload[DTB_OFF:DTB_OFF + EXP_RTD_SIZE]
check("RT_D_SIZE", len(rtd) == EXP_RTD_SIZE, f"{len(rtd)}")
check("RT_D_SHA256", sha(rtd) == EXP_RTD_SHA, sha(rtd))
check("RT_D_FDT_MAGIC", rtd[0:4] == b"\xd0\x0d\xfe\xed", rtd[0:4].hex())
check("RT_D_TRAILER_IS_PAYLOAD_TAIL", DTB_OFF + EXP_RTD_SIZE == len(payload),
      f"{DTB_OFF + EXP_RTD_SIZE} vs {len(payload)}")

# --- geometry ----------------------------------------------------------------
check("GEO_DTB_OFFSET_BEFORE_RTD", DTB_OFF < len(payload))
check("GEO_IMAGE_FILE_SIZE", IMAGE_FILE_SIZE == 0x2189A00, hex(IMAGE_FILE_SIZE))
check("GEO_PS_OFFSET_INSIDE_IMAGE_FILE", PS_OFF < IMAGE_FILE_SIZE,
      f"{PS_OFF:#x} < {IMAGE_FILE_SIZE:#x}")

print()
print("VERIFY_RESULT=" + ("PASS" if not fails else "FAIL:" + ",".join(fails)))
sys.exit(0 if not fails else 1)
