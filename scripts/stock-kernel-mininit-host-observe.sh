#!/usr/bin/env bash
# Stock-kernel mininit host observer (macOS). READ-ONLY toward the phone.
# Pass requires USB identity + new enX + interface-bound HTTP. ping is not a pass.
set -euo pipefail
DEVIP="${DEVIP:-10.66.73.1}"
HOSTIP="${HOSTIP:-10.66.73.2}"
SERIAL="${SERIAL:-THYME-STOCKK-MININIT}"
PRODUCT="${PRODUCT:-Stock Kernel MinInit Control}"

echo "== stock-kernel mininit host observe =="
echo "VPN note: default route on this Mac is typically utun. ping $DEVIP is not identity."
echo

echo "-- USB (system_profiler) --"
system_profiler SPUSBDataType 2>/dev/null | awk -v s="$SERIAL" -v p="$PRODUCT" '
  BEGIN { blk="" }
  /^[ ]*Product ID:/ { blk=$0; next }
  { blk=blk "\n" $0 }
  index($0, s) || index($0, p) { print blk; found=1 }
  END { if (!found) print "USB IDENTITY NOT FOUND: " s " / " p }
'

echo
echo "-- ioreg serial --"
ioreg -p IOUSB -w0 -l 2>/dev/null | grep -A2 -F "$SERIAL" || echo "ioreg: serial not present"

echo
echo "-- candidate en* (exclude en0 LAN) --"
ifconfig -l | tr ' ' '\n' | grep -E '^en[0-9]+$' | grep -v '^en0$' || true

echo
echo "Next (manual, after a NEW enX appears):"
echo "  sudo ifconfig enX $HOSTIP netmask 255.255.255.0 up"
echo "  curl --interface enX http://$DEVIP:8080/status.txt"
echo "Pass only if USB serial is $SERIAL, HTTP 200, body has CONTROL=STOCK_KERNEL_MININIT"
echo "and STAGE_6_USERSPACE_READY."
echo "If fastboot devices still lists the phone, Linux did not take USB."
