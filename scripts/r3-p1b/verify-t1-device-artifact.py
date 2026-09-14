#!/usr/bin/env python3
"""Read-only identity/geometry verification of the frozen T1 boot artifact.

No build, no splice, no byte mutation: opens the downloaded private artifact,
re-derives every frozen identity, and diff-attributes the payload against the
frozen FIX8 baseline. Exits non-zero on any mismatch.
"""
import hashlib
import struct
import sys

BOOT = "artifacts/r3-p1b-t1-34807172879/t1-out/thyme-r3-p1b-t1-boot.img"
FIX8 = ("artifacts/r3-p1b-fixed-init8-34744041027/public-proof/"
        "thyme-r3-p1b-fix8-fix24/thyme-r3-p1b-fix8-kernel-payload.bin")

EXP_BOOT_SHA = "a4fa083f289219facb0a69062749dd6a9d2f667c4aa044b25b78c36b0da7e3df"
EXP_BOOT_SIZE = 37380096
EXP_PAYLOAD_SHA = "3e654ee55c517b8a652b6441fcfd26a7b651ecfae6a3d673db248f667157f0fb"
EXP_PAYLOAD_SIZE = 37369041
EXP_FIX8_SHA = "4f34eabf670a735b3a10ebd0fb005e937faba881ea23fdc0843cf4ac96cceb41"
EXP_TRAMP_SHA = "362d9c6e08863f79327364532372c6ecc9086e6211635e7fa4a6db4d747dc623"
EXP_CKPT_SHA = "4d792df5f7688af9a48480bf69c5afeaeade290bacfce0878876c9ab6dd93611"
EXP_RTD_SHA = "4849743205af9d00f4b5bcd01070aac68be7dc60954975069356d29fe33df327"
EXP_RTD_SIZE = 144593

PRIMARY_ENTRY = 0x1b1c0a0
CKPT_OFF = 0x2230000
CKPT_LEN = 76
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
check("T1_BOOT_SIZE", len(boot) == EXP_BOOT_SIZE, f"{len(boot)}")
check("T1_BOOT_SHA256", sha(boot) == EXP_BOOT_SHA, sha(boot))

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
check("T1_PAYLOAD_SIZE", len(payload) == EXP_PAYLOAD_SIZE, f"{len(payload)}")
check("T1_PAYLOAD_SHA256", sha(payload) == EXP_PAYLOAD_SHA, sha(payload))

# --- diff attribution vs frozen FIX8 ----------------------------------------
check("FIX8_BASELINE_SHA256", sha(fix8) == EXP_FIX8_SHA, sha(fix8))
check("PAYLOAD_LENGTH_IDENTICAL_TO_FIX8", len(payload) == len(fix8))
diff = [n for n in range(min(len(payload), len(fix8)))
        if payload[n] != fix8[n]]
print(f"T1_DIFF_BYTE_COUNT={len(diff)}")
ranges = []
for n in diff:
    if ranges and n == ranges[-1][1]:
        ranges[-1][1] = n + 1
    else:
        ranges.append([n, n + 1])
print("T1_DIFF_RANGES=" + str([[hex(a), hex(b)] for a, b in ranges]))
# Gate convention: two FAMILIES reported as region unions; the raw byte census
# splits family B wherever a composed byte equals the zero baseline.
fam_a = [r for r in ranges if r[1] <= PRIMARY_ENTRY + 4]
fam_b = [r for r in ranges if r[0] >= CKPT_OFF]
n_a = sum(b - a for a, b in fam_a)
n_b = sum(b - a for a, b in fam_b)
check("T1_DIFF_BYTE_COUNT", len(diff) == 75, f"{len(diff)}")
check("T1_DIFF_FAMILY_A_PRIMARY_ENTRY_ONLY",
      fam_a == [[PRIMARY_ENTRY, PRIMARY_ENTRY + 4]] and n_a == 4,
      f"A={n_a} {[[hex(a), hex(b)] for a, b in fam_a]}")
check("T1_DIFF_FAMILY_B_CHECKPOINT_REGION_ONLY",
      n_b == 71 and all(CKPT_OFF <= a and b <= CKPT_OFF + CKPT_LEN
                        for a, b in fam_b),
      f"B={n_b} in [0x2230000,0x223004c)")
check("T1_PAYLOAD_DIFF_ATTRIBUTED",
      n_a + n_b == 75 and len(fam_a) + len(fam_b) == len(ranges),
      "PRIMARY_ENTRY_PATCH_PLUS_CHECKPOINT_REGION_ONLY")

# --- primary_entry patch decode ---------------------------------------------
patched = struct.unpack_from("<I", payload, PRIMARY_ENTRY)[0]
orig = struct.unpack_from("<I", fix8, PRIMARY_ENTRY)[0]


def dec_b(ins):
    imm26 = ins & 0x3FFFFFF
    if imm26 & (1 << 25):
        imm26 -= 1 << 26
    return imm26 * 4


def dec_bl(ins):
    imm26 = ins & 0x3FFFFFF
    if imm26 & (1 << 25):
        imm26 -= 1 << 26
    return imm26 * 4


print(f"ORIG word={orig:#010x} bytes={orig.to_bytes(4,'little').hex()} "
      f"op=0b{orig>>26:06b} target={hex(PRIMARY_ENTRY + dec_bl(orig))}")
print(f"T1   word={patched:#010x} bytes={patched.to_bytes(4,'little').hex()} "
      f"op=0b{patched>>26:06b} target={hex(PRIMARY_ENTRY + dec_b(patched))}")
check("T1_PRIMARY_ENTRY_ORIGINAL_BYTES", orig.to_bytes(4, "little").hex() == "65740094")
check("T1_PRIMARY_ENTRY_ORIGINAL_TARGET", PRIMARY_ENTRY + dec_bl(orig) == 0x1b39234)
check("T1_BRANCH_OPCODE", (patched >> 26) == 0b000101, f"0b{patched>>26:06b}")
check("T1_BRANCH_TARGET", PRIMARY_ENTRY + dec_b(patched) == CKPT_OFF,
      hex(PRIMARY_ENTRY + dec_b(patched)))
check("T1_BRANCH_DISTANCE", CKPT_OFF - PRIMARY_ENTRY == 0x713f60,
      hex(CKPT_OFF - PRIMARY_ENTRY))

# --- checkpoint region -------------------------------------------------------
ckpt = payload[CKPT_OFF:CKPT_OFF + CKPT_LEN]
check("T1_CHECKPOINT_SHA256", sha(ckpt) == EXP_CKPT_SHA, sha(ckpt))
ckpt_words = struct.unpack_from("<%dI" % (CKPT_LEN // 4), payload, CKPT_OFF)
print("CKPT_WORDS=" + " ".join(f"{w:08x}" for w in ckpt_words))
# Fail-closed terminal + PSCI FID construction, decoded from the built words.
idx = {w: i for i, w in enumerate(ckpt_words)}
smc_i = ckpt_words.index(0xD4000003) if 0xD4000003 in ckpt_words else -1


def dec_b_imm(ins):
    imm = ins & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return imm * 4


def dec_bcond(ins):
    imm = (ins >> 5) & 0x7FFFF
    if imm & (1 << 18):
        imm -= 1 << 19
    return imm * 4


print(f"SMC_INDEX={smc_i} tail=" +
      " ".join(f"{w:08x}" for w in ckpt_words[smc_i:]) if smc_i >= 0 else "")
check("CKPT_MSR_DAIFSET_ISB", ckpt_words[0] == 0xD5034FDF
      and ckpt_words[1] == 0xD5033FDF)
check("CKPT_CNTFRQ_MRS", ckpt_words[2] == 0xD53BE009, f"{ckpt_words[2]:08x}")
check("CKPT_8S_DELAY_CONSTANT", ckpt_words[3] == 0xD280010A,  # mov x10, #8
      f"{ckpt_words[3]:08x}")
check("CKPT_CNTPCT_MRS", ckpt_words[6] == 0xD53BE02B,
      f"{ckpt_words[6]:08x}")           # + 0xD53BE02C re-sample
check("CKPT_CNTPCT_RESTAMPLE", ckpt_words[8] == 0xD53BE02C,
      f"{ckpt_words[8]:08x}")
check("CKPT_YIELD_POLL", 0xD503203F in ckpt_words)
check("CKPT_REGISTER_ONLY_NO_STACK", all(
    not (0xA9 == (w >> 24) and (w >> 22) & 1) for w in ckpt_words), "no stp/ldp")
check("CKPT_PSCI_MOVZ_W0_9", ckpt_words[smc_i - 2] == 0x52800120,
      f"{ckpt_words[smc_i-2]:08x}")     # mov  w0, #9
check("CKPT_PSCI_MOVK_W0_8400", ckpt_words[smc_i - 1] == 0x72B08000,
      f"{ckpt_words[smc_i-1]:08x}")     # movk w0, #0x8400, lsl #16
check("CKPT_PSCI_FID_0x84000009", True, "w0 = 0x84000009 (movz+movk)")
check("CKPT_SMC_THEN_WFE", ckpt_words[smc_i + 1] == 0xD503205F,
      f"{ckpt_words[smc_i+1]:08x}")
back = ckpt_words[smc_i + 2]
check("CKPT_FAIL_CLOSED_BACK_TO_WFE",
      (back >> 26) == 0b000101 and (smc_i + 2) + dec_b_imm(back) // 4 == smc_i + 1,
      f"{back:08x} -> idx {smc_i + 2 + dec_b_imm(back)//4}")
check("CKPT_NO_RET_NO_FALLTHROUGH",
      0xD65F03C0 not in ckpt_words and ckpt_words[-1] == (back), "no ret")
check("CKPT_NO_BRANCH_TO_PRIMARY_ENTRY",
      all(not ((w >> 26) == 0b000101 and
               PRIMARY_ENTRY == CKPT_OFF + i * 4 + dec_b_imm(w))
          for i, w in enumerate(ckpt_words)), "fail-closed")
bc = ckpt_words[11]
check("CKPT_DELAY_ELAPSED_BRANCHES_TO_RESET",
      (bc >> 24) == 0x54 and 11 + dec_bcond(bc) // 4 == smc_i - 2,
      f"{bc:08x} -> idx {11 + dec_bcond(bc)//4} (=mov w0,#9)")

# --- padding safety ----------------------------------------------------------
pad = payload[IMAGE_HEADER_IMAGE_SIZE:DTB_OFF]
nonzero = [n for n, v in enumerate(pad) if v]
outside = [n for n in nonzero
           if not (CKPT_OFF <= IMAGE_HEADER_IMAGE_SIZE + n < CKPT_OFF + CKPT_LEN)]
print(f"PADDING_LEN={len(pad)} NONZERO={len(nonzero)} "
      f"OUTSIDE_CHECKPOINT={len(outside)}")
check("T1_CHECKPOINT_PADDING_REGION_SAFE",
      len(outside) == 0 and len(nonzero) == len([n for n in nonzero
                                                 if IMAGE_HEADER_IMAGE_SIZE + n
                                                 < CKPT_OFF + CKPT_LEN]),
      f"nonzero_inside_ckpt={len(nonzero)}")
check("T1_CHECKPOINT_OUTSIDE_IMAGE_SIZE", CKPT_OFF >= IMAGE_HEADER_IMAGE_SIZE)
check("T1_CHECKPOINT_OUTSIDE_IMAGE_FILE", CKPT_OFF >= IMAGE_FILE_SIZE)
check("T1_CHECKPOINT_BEFORE_RTD", CKPT_OFF + CKPT_LEN <= DTB_OFF)

# --- RT-D trailer ------------------------------------------------------------
rtd = payload[DTB_OFF:DTB_OFF + EXP_RTD_SIZE]
check("RT_D_SIZE", len(rtd) == EXP_RTD_SIZE, f"{len(rtd)}")
check("RT_D_SHA256", sha(rtd) == EXP_RTD_SHA, sha(rtd))
check("RT_D_FDT_MAGIC", rtd[0:4] == b"\xd0\x0d\xfe\xed", rtd[0:4].hex())
check("RT_D_TRAILER_IS_PAYLOAD_TAIL", DTB_OFF + EXP_RTD_SIZE == len(payload),
      f"{DTB_OFF + EXP_RTD_SIZE} vs {len(payload)}")

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
if tramp_off is None:
    # brute force over the trampoline neighbourhood
    for off in range(0, 0x4000, 4):
        if sha(payload[off:off + 112]) == EXP_TRAMP_SHA:
            tramp_off, tramp_len = off, 112
            break
check("T1_TRAMPOLINE_SHA256", tramp_off is not None,
      f"offset={hex(tramp_off) if tramp_off is not None else None} len={tramp_len}")
if tramp_off is not None:
    check("T1_TRAMPOLINE_IDENTICAL_TO_FIX8",
          payload[tramp_off:tramp_off + tramp_len] == fix8[tramp_off:tramp_off + tramp_len])
    tw = struct.unpack_from("<%dI" % (tramp_len // 4), payload, tramp_off)
    print("TRAMP_WORDS=" + " ".join(f"{w:08x}" for w in tw))
    # Word 8 sits at the trampoline's absolute payload offset 0x60 (doc s.4/14);
    # a B is PC-relative to its own address, so the target is 0x60 + imm*4.
    w8_abs = 0x60
    w8 = struct.unpack_from("<I", payload, w8_abs)[0]
    tw8_tgt = w8_abs + dec_b(w8)
    print(f"TRAMP_WORD8@{w8_abs:#x}={w8:08x} op=0b{w8>>26:06b} "
          f"target={hex(tw8_tgt)}")
    check("T1_TRAMPOLINE_BRANCH_WORD8_IS_B", (w8 >> 26) == 0b000101,
          f"0b{w8>>26:06b}")
    check("T1_TRAMPOLINE_BRANCH_TARGET", tw8_tgt == PRIMARY_ENTRY,
          hex(tw8_tgt))
    # x0 setup: adr x0,#imm ; ldr x9,<literal 0x0237ff98> ; add x0,x0,x9
    check("TRAMP_X0_STATIC_DTB", tw[4] == 0x8B090000 and tw[10] == 0x0237FF98
          and tw8_tgt == PRIMARY_ENTRY, f"x0 -> 0x{0x68 + 0x0237FF98:x}")
    check("TRAMP_X1_X2_X3_ZERO",
          tw[5] == 0xAA1F03E1 and tw[6] == 0xAA1F03E2 and tw[7] == 0xAA1F03E3)

print()
print("VERIFY_RESULT=" + ("PASS" if not fails else "FAIL:" + ",".join(fails)))
sys.exit(0 if not fails else 1)
