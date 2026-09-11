# Reference R3 — cloned repository identity

Stage: `THYME_REFERENCE_R3_LMI_BOOTCHAIN_AUDIT`

Read-only clones under `refs/`. `refs/` is already in `.gitignore`. This
round did not modify ignore rules and did not add these trees as submodules.

```text
LOCAL_BUILD=NO
LOCAL_VALIDATION=NO
LOCAL_VALIDATOR=NO
LOCAL_SOURCE_GATE=NO
LOCAL_ACTIONLINT=NO
LOCAL_BINARY_VALIDATION=NO
DEVICE_OPERATION=NO
Slot A written=NO
CURRENT_ROUTE_B_CHANGED=NO
```

No tokens, credentials, serials, or cpuid are recorded.

## A. linux-sm8250-xiaomi-lmi

```text
URL:              https://github.com/ccc007ccc/linux-sm8250-xiaomi-lmi.git
local path:       refs/linux-sm8250-xiaomi-lmi
default branch:   master
cloned branch:    master
HEAD:             3a8409fb1020b5952310072713ce97edea5e65d7
HEAD short:       3a8409fb1
HEAD date:        2026-06-17T08:59:28+08:00
HEAD subject:     完善 lmi 相机网络模式和音频分发配置
author:           ccc007ccc <ccc007mc@gmail.com>
size on disk:     2.0G
shallow:          YES (depth=1, .git/shallow present)
partial clone:    NO
tag count:        0 (this clone; remote ls-remote also showed no tags)
branch list:      master
                  remotes/origin/HEAD -> origin/master
                  remotes/origin/master
remote heads:     only master (git ls-remote)
Makefile:         VERSION=7 PATCHLEVEL=1 SUBLEVEL=0
                  NAME=Baby Opossum Posse
lmi/locks/kernel.lock:
                  stale pin tag=v6.18.30 (2026-05-14); does not match HEAD Makefile
```

GitHub compare `torvalds:master...ccc007ccc:master` at audit time:

```text
status:           diverged
ahead_by:         74
behind_by:        32603
total_commits:    74
```

The “~74 commits ahead of torvalds” claim is the unique lmi-side commit
count versus **current** `torvalds/linux` master. It is not “lmi contains
current torvalds plus 74”. The tree is 7.1.0-era + 74 lmi commits, and is
tens of thousands of commits behind current torvalds.

## B. sm8250-xiaomi-lmi-boot

```text
URL:              https://github.com/ccc007ccc/sm8250-xiaomi-lmi-boot.git
local path:       refs/sm8250-xiaomi-lmi-boot
default branch:   master
cloned branch:    master
HEAD:             31e61561469081af7fe5ee9b4218299f3980bd6b
HEAD short:       31e6156
HEAD date:        2026-05-25T02:29:43+08:00
HEAD subject:     补充 lmi boot 发布使用说明
author:           ccc007ccc <ccc007mc@gmail.com>
size on disk:     596K
shallow:          YES (depth=1, .git/shallow present)
partial clone:    NO
tag count:        0
branch list:      master
                  remotes/origin/HEAD -> origin/master
                  remotes/origin/master
remote heads:     only master
```

Tracked content is scripts, bootshim assembly, locks, and a vendored
Ubuntu `mkbootimg`. Generated `builds/`, `captures/`, and OEM blobs are
not in the public tree.

## C. sm8250-xiaomi-lmi-initramfs

```text
cloned:           NO
remote HEAD:      ca90a154cc10db18ab28d524235ef3f8c8d14e47 (ls-remote master)
reason:           bootshim → Linux initramfs handoff is explained by
                  CONFIG_INITRAMFS_SOURCE in lmi/configs/m1.config plus
                  the boot.img --ramdisk packing in
                  scripts/mkboot-linux-copydown-lmi.sh.
                  Contents of the cpio (boot menu, UFS probe) are
                  post-entry userspace and were not required to answer
                  ABL / x0 / DTB decoupling.
```

## D. sunflower2333/linux

```text
full cloned:      NO
URL:              https://github.com/sunflower2333/linux.git
inspection:       git ls-remote + GitHub contents/API
default branch:   master
master SHA:       8241a9201ba76f7d077992c4d70cc15ae55d31e2
other heads:      6.18-lts, old
tags:             many release-25.* tags; none named lmi/sm8250/xiaomi/kona/phone
Makefile:         VERSION=7 PATCHLEVEL=2 SUBLEVEL=0 EXTRAVERSION=-rc5
fork:             YES, parent=torvalds/linux
description:      "Linux kernel source tree"
sm8250 Xiaomi DTS in qcom/Makefile:
                  umi, elish-boe, elish-csot, pipa
                  NOT lmi, NOT thyme, NOT alioth
code search:      0 hits for sm8250-xiaomi-lmi / xiaomi,lmi / repo xiaomi+lmi
```

No patch-id / ancestry fetch was performed. Relationship evidence did not
justify a shallow clone.

## Already present (not cloned this round)

```text
refs/alioth-mainline-7.2.2
refs/astidelabs-sm8250
```
