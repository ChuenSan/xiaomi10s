# Route B stock-kernel USB Stage4 HTTP — thyme

Stage: `STOCK_KERNEL_USB_STAGE4_HTTP_LIVENESS`
Status: implementation ready; CI/device evidence pending
Device: Xiaomi Mi 10S (`thyme` / SM8250)
Kernel: stock exact `4.19.157-perf`
Endpoint: `10.66.73.1:8080`

## Scope

Stage3B is accepted as:

```text
USB_NCM_END_TO_END_L3_CONFIRMED=YES
DEV_ADDR_CORRELATION_IN_THIS_RUN=NOT_AVAILABLE
```

Stage4 adds only a freestanding static ARM64 TCP listener and one minimal
HTTP/1.1 response. The verified configfs/NCM/UDC, `usb0` IFF_UP, and device
IPv4 setup are reused. No SSH, telnet, DHCP, DNS, TLS, framework, or default
route is added.

## CI

```text
workflow:  thyme-stock-kernel-usb-stage4-http
run:       PENDING
commit:    PENDING
artifact:  thyme-stock-kernel-usb-stage4-http-<sha>
marker:    BUILD=<7-char-commit-marker>
```

Required CI gates:

```text
STOCK_KERNEL_EXACT=PASS
STATIC_INIT=PASS
ENTRY_IN_RX_LOAD=PASS
STAGE2_USB_NETWORK_CORE_REUSED=PASS
DEVICE_IP_LITERAL=10.66.73.1
HTTP_BIND_IP=10.66.73.1
HTTP_PORT=8080
HTTP_RESPONSE_200_PRESENT=PASS
CONTENT_LENGTH_VALIDATION=PASS
HTTP_READY_MARKER=PASS
NO_HTTP_EMPTY_REPLY_PATH=PASS
NO_INADDR_ANY_HTTP_BIND=PASS
NO_DHCP=PASS
NO_DEFAULT_ROUTE=PASS
FAILSAFE_RESTART2=PASS
BOOT_V3=PASS
REVERSE_UNPACK=PASS
SIZE_GATE=PASS
READY_FOR_USB_STAGE4_HTTP
```

The build, static ARM64 ELF check, initramfs generation, boot v3 packing, and
reverse unpack all run in GitHub Actions. No local compiler or image builder
is permitted.

Artifact contents:

```text
stock-kernel-usb-stage4-http-boot-v3.img
usb-stage4-http-init
initramfs.cpio.gz
SHA256SUMS
validation-report.txt
unpack-report/
```

## Device behavior

```text
USB VID:PID       1d6b:0104
Manufacturer      thyme-mainline
Product           Stock Kernel USB Stage4 HTTP
Serial            THYME-USB4
device IP         10.66.73.1/24
HTTP bind         10.66.73.1:8080
hold              60s maximum
normal exit       restart2("bootloader")
```

The PID1 sequence is:

```text
configfs/NCM → UDC bind → dynamic usb0 → IFF_UP → 10.66.73.1/24
→ UDC configured + carrier=1 → socket/SO_REUSEADDR → bind → listen
→ HTTP_READY → up to 5 request/response connections → HOLD_DONE
→ restart2("bootloader")
```

Required device markers include:

```text
THYME-USB4:INIT
THYME-USB4:CONFIGFS_OK
THYME-USB4:UDC=<name>
THYME-USB4:NCM_OK
THYME-USB4:UDC_BOUND
THYME-USB4:NETDEV=<name>
THYME-USB4:IFF_UP_OK
THYME-USB4:DEVICE_IP_VERIFIED
THYME-USB4:UDC_CONFIGURED
THYME-USB4:CARRIER=1
THYME-USB4:SOCKET_OK
THYME-USB4:BIND_ATTEMPT=10.66.73.1:8080
THYME-USB4:BIND_OK
THYME-USB4:LISTEN_OK:10.66.73.1:8080
THYME-USB4:HTTP_READY
THYME-USB4:ACCEPT_OK
THYME-USB4:REQUEST_RX
THYME-USB4:HTTP_200_SENT
THYME-USB4:HOLD_DONE
THYME-USB4:REBOOT_BOOTLOADER
```

## Host run record

Fill only from the bounded Stage4 run:

```text
NEW_IF:                         PENDING
host IP:                        10.66.73.2/24
link:                           PENDING
route interface:                PENDING
ICMP regression sent/received:  PENDING
curl binding:                   --interface NEW_IF --ipv4
exact curl:                     PENDING
connected:                      PENDING
status:                         PENDING
content type:                   PENDING
body identity:                  PENDING
build marker:                   PENDING
capture interface:              PENDING
ARP:                            PENDING
ICMP:                           PENDING
TCP SYN:                        PENDING
TCP SYN-ACK:                    PENDING
HTTP data:                      PENDING
HTTP_READY:                     PENDING
ACCEPT_OK:                      PENDING
REQUEST_RX:                     PENDING
HTTP_200_SENT:                  PENDING
retry before/after boot:        PENDING
Android A restored:             PENDING
```

The host test must dynamically discover the new THYME `enX`, configure the
address with temporary `ifconfig`, verify `route -n get 10.66.73.1`, run one
source/interface-bound ICMP regression, and then run:

```sh
curl --interface "$NEW_IF" --ipv4 --max-time 5 -v \
  http://10.66.73.1:8080/
```

A bare curl, TCP connect, empty reply, malformed response, wrong body, or
response observed on another interface is not a pass.

## Final classification

```text
FINAL_GATE=USB_STAGE4_HTTP_LIVENESS_PASS
FINAL_GATE=USB_STAGE4_DEVICE_HTTP_SETUP_FAILED
FINAL_GATE=USB_STAGE4_L3_REGRESSION
FINAL_GATE=USB_STAGE4_TCP_CONNECT_FAILED
FINAL_GATE=USB_STAGE4_HTTP_APPLICATION_FAILED
FINAL_GATE=USB_STAGE4_HTTP_IDENTITY_MISMATCH
FINAL_GATE=USB_STAGE4_INCONCLUSIVE
```

`STOCK_KERNEL_CONTROL_PATH_COMPLETE=YES` is recorded only after the device
run obtains the expected HTTP 200 and unique body, with the interface-bound
route/capture evidence and Android A recovery.
