#!/usr/bin/env bash
# Route B host observer (macOS). READ-ONLY toward the phone.
# Success requires USB identity + new enX + interface-bound HTTP.
# ping via the default route is NOT a pass.
set -euo pipefail
DEVIP="${DEVIP:-10.66.73.1}"
HOSTIP="${HOSTIP:-10.66.73.2}"
SERIAL="${SERIAL:-THYME-MAINLINE-B}"

echo "== Route B host observe =="
echo "VPN note: default route on this Mac is typically utun (full tunnel)."
echo "Do not treat ping $DEVIP as gadget identity."
echo

echo "-- USB (system_profiler) --"
system_profiler SPUSBDataType 2>/dev/null | awk -v s="$SERIAL" '
  BEGIN { blk="" }
  /^[ ]*Product ID:/ { blk=$0; next }
  { blk=blk "\n" $0 }
  $0 ~ s { print blk; found=1 }
  END { if (!found) print "SERIAL NOT FOUND: " s }
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
echo "Pass only if body contains ROUTE=B and HTTP is 200, and USB serial is $SERIAL."
echo "If 'fastboot devices' still lists the phone, Linux did not take USB."
