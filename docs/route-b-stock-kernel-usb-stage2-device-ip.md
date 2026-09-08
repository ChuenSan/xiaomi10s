# Stock kernel USB Stage2 device static IP

Slot B workflow: `.github/workflows/thyme-stock-kernel-usb-stage2-device-ip.yml`.

Reuses the Stage1B USB0 path (newfstatat + S_ISDIR directory check, configfs
NCM gadget, `usb0` netdev discovery, `SIOCGIFFLAGS` / `SIOCSIFFLAGS` with
`old_flags | IFF_UP`) and adds **device-side static IPv4** on `usb0`:

```
10.66.73.1/24
```

After `IFF_UP` succeeds, PID1 calls:

| syscall | purpose |
| --- | --- |
| `SIOCSIFADDR` | set device address `10.66.73.1` |
| `SIOCSIFNETMASK` | set netmask `255.255.255.0` |
| `SIOCGIFADDR` | read back and verify |
| `SIOCGIFNETMASK` | read back and verify |

On mismatch it logs `THYME-USB2:FAIL:IPV4_MISMATCH` and reboots into the
bootloader; on success it logs
`THYME-USB2:DEVICE_STATIC_IPV4_VERIFIED=YES` and holds for ~30 s before an
automatic Fastboot return.

## What is NOT done

- No host-side IPv4 configuration, no `dhcp`, no default route.
- No `SIOCSIFBRDADDR`, no `SIOCADDRT`, no `172.16.42.x` host address.
- No ping, no HTTP, no mainline kernel, no DTS, no vendor_boot / dtbo /
  vbmeta writes.
- Slot A (vendor partition) is protected; only `boot_b` is written.

## Gating

The workflow is the gate for this slot. It fetches the official V14.0.6.0
boot.img, runs `scripts/stock-kernel-usb-stage2-device-ip-source-gates.py`,
builds the static `usb-stage2-device-ip-init` + ramdisk, packs a v3 boot image
and reverse-validates it with
`scripts/stock-kernel-usb-stage2-device-ip-ci-validate.sh`.

```sh
gh workflow run thyme-stock-kernel-usb-stage2-device-ip.yml --ref route-b-v3
```

## Host observation (manual)

`scripts/stock-kernel-usb-stage2-device-ip-host-observe.sh` watches the host
side: Fastboot disappearance, Stage2 gadget enumeration, new `enX` status and
Fastboot return. It is read-only — no host IP, no ping, no writes.