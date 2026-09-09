# Route B stock-kernel USB Stage4 HTTP — thyme

Stage: `STOCK_KERNEL_USB_STAGE4_HTTP_LIVENESS`
Status: complete; parser CI and no-flash device confirmation passed
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

Device image CI:

```text
workflow:  thyme-stock-kernel-usb-stage4-http
run:       34314918464
commit:    c780694cee3978e130465a677290ff139bbd6775
artifact:  thyme-stock-kernel-usb-stage4-http-c780694cee3978e130465a677290ff139bbd6775
marker:    BUILD=c780694
boot sha:  6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a
result:    ALL STOCK KERNEL USB STAGE4 HTTP VALIDATION PASS
```

Parser fix and host confirmation CI:

```text
fix commit:       5ff3b2c2b500cff715acc78ba98a00424b52383e
no-flash commit:  3acec79c5daf20c162e7e1557155dd68402251df
workflow:         thyme-stock-kernel-usb-stage4-http-parser
run:              34317126126
image rebuild:    NO
```

Parser regression gates:

```text
TCP_PARSE_CLASSIC_SYN = PASS
TCP_PARSE_CLASSIC_SYNACK = PASS
TCP_PARSE_ECN_SYN = PASS
TCP_PARSE_ECN_SYNACK = PASS
TCP_PARSE_ACK_NOT_SYN = PASS
TCP_PARSE_PSHACK_NOT_SYNACK = PASS
TCP_PARSE_WRONG_DIRECTION_REJECTED = PASS
TCP_PARSE_WRONG_PORT_REJECTED = PASS
STAGE4_HOST_SCRIPT_GATE = PASS
```

Parser change:

```text
old: fixed Flags [S] and Flags [S.]
new: AWK bracket-flag extraction + source/destination IP/port direction
ECN SYN: supported ([SEW])
ECN SYN-ACK: supported ([S.E])
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

Run 1 preserved the original raw result. Device communication passed, but
fixed-string TCP flag parsing classified the run as inconclusive:

```text
log:                 work/usb-stage4-http-20260909-133751.log
NEW_IF:              en14
route:               10.66.73.1 -> en14
ICMP:                1/1, 0.0% loss
curl:                en14, connected, HTTP 200, body 201 bytes, BUILD=c780694
raw tcpdump:         ARP, ICMP, [SEW] SYN, [S.E] SYN-ACK, GET, HTTP 200
original SYN gate:   NO
original SYN-ACK:    NO
ORIGINAL_FINAL_GATE: USB_STAGE4_INCONCLUSIVE
Android A restored:  YES
```

Run 2 used the same `boot_b` image with `STAGE4_CONFIRM_ONLY=YES`; no image
was built and no boot partition was flashed:

```text
log:                 work/usb-stage4-http-20260909-140343.log
mode:                confirmation-only
boot_b reused:       YES
boot_b sha:          6b5689c99f56f42757e97c65ddd093f289c124f70f856261934c502501d0570a
NEW_IF:              en14
host IP:             10.66.73.2/24, verified
link:                active
route:               10.66.73.1 -> en14
connected route:     10.66.73/24 -> en14
ICMP:                1/1, 0.0% loss
curl binding:        --interface en14 --ipv4
connected:           YES
status:              HTTP 200
content type:        text/plain
headers:             valid, Content-Length=201
body identity:       YES
build marker:        BUILD=c780694
capture interface:   en14
ARP:                 request/reply captured
ICMP:                request/reply captured
TCP SYN:             YES ([SEW])
TCP SYN-ACK:         YES ([S.E])
TCP ACK:             YES
HTTP GET:            YES
HTTP 200:            YES
HTTP data:           YES
retry before/after:  6 / 6 (after set_active: 7)
Android A restored:  YES
```

The pre-test `utun4` route collision was observed, but the connected route
used during the test was `en14`; no manual route was added. The pstore was
empty, so device kmsg markers were unavailable; the runtime listener is
independently proven by the interface-bound HTTP exchange.

Run 2 read-only partition guard:

```text
vendor_boot_b:    aac7e11f3b481bb6c51a7b011ae35bed230d1fa132e6f0bcae46e5aade041972
                  stock match
dtbo_b:           018fa85c9c299df73cd6b6e86c60eae2125ac30a0e3ac0ca14d428aaefe64634
                  stock match
vbmeta_b:         37dfac44f336157d69b616e3567cdccff90273b36cd862a86f57abe1930f9d9c
                  stock match
vbmeta_system_b:  3217455014b5bb0cc05b638489589738863aeb6cc6b9423d56989b21fa8b8355
                  stock match
```

Read-only dump baseline captured before the Stage4 runs (16 MiB prefixes):

```text
oops:      0f80d3b210ffe6a87215873e2649833526f8f0ea6eb1ea98137e9a19f4315514
minidump:  4f00e3599293cb23b4dc9ed5bd97a7740f2c39dc573f99c411bbde68598fb8ef
logdump:   080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e
rawdump:   080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e
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

Final result:

```text
FINAL_GATE=USB_STAGE4_HTTP_LIVENESS_PASS
USB_NCM_END_TO_END_L3_CONFIRMED=YES
APPLICATION_LIVENESS_CONFIRMED=YES
STOCK_KERNEL_CONTROL_PATH_COMPLETE=YES
```

`STOCK_KERNEL_CONTROL_PATH_COMPLETE=YES` is recorded after the no-flash
confirmation obtained the expected HTTP 200 and unique body, with the
interface-bound route/capture evidence and Android A recovery. The original
Run 1 log remains unchanged and is retained as historical raw evidence.
