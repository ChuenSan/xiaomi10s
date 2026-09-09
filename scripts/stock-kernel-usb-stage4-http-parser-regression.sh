#!/usr/bin/env bash
# GHA-only semantic regression tests for the Stage4 tcpdump parser.
set -euo pipefail

if [ -z "${GITHUB_ACTIONS:-}" ]; then
	echo 'CI only — refuse local parser validation' >&2
	exit 1
fi

PARSER="scripts/stock-kernel-usb-stage4-http-tcp-parser.awk"
HOST_SCRIPT="scripts/stock-kernel-usb-stage4-http.sh"
[ -s "$PARSER" ]
[ -s "$HOST_SCRIPT" ]
grep -Fq 'stock-kernel-usb-stage4-http-tcp-parser.awk' "$HOST_SCRIPT"
grep -Fq 'TCP_PARSE_OUTPUT=$(parse_tcp_capture' "$HOST_SCRIPT"
grep -Fq "grep -Fqx 'SYN'" "$HOST_SCRIPT"
grep -Fq "grep -Fqx 'SYNACK'" "$HOST_SCRIPT"
grep -Fq '[ "$HTTP_GET_CAPTURED" = YES ]' "$HOST_SCRIPT"
grep -Fq '[ "$HTTP_200_CAPTURED" = YES ]' "$HOST_SCRIPT"
grep -Fq 'STAGE4_CONFIRM_ONLY' "$HOST_SCRIPT"
grep -Fq 'FLASH_BOOT_B_ONLY=SKIPPED' "$HOST_SCRIPT"
grep -Fq 'refusing no-flash confirmation' "$HOST_SCRIPT"

got_for() {
	local fixture=$1
	printf '%s\n' "$fixture" |
		awk -v host=10.66.73.2 -v device=10.66.73.1 -v port=8080 \
			-f "$PARSER" |
		awk 'BEGIN { sep = "" } { printf "%s%s", sep, $0; sep = " " } END { print "" }'
}

expect_exact() {
	local name=$1 expected=$2 fixture=$3 got
	got=$(got_for "$fixture")
	if [ "$got" != "$expected" ]; then
		echo "FAIL $name expected=[$expected] got=[$got]" >&2
		exit 1
	fi
}

expect_absent() {
	local name=$1 label=$2 fixture=$3 got
	got=$(got_for "$fixture")
	if printf '%s\n' "$got" | tr ' ' '\n' | grep -Fxq "$label"; then
		echo "FAIL $name unexpectedly emitted $label: [$got]" >&2
		exit 1
	fi
}

classic=$'13:00:00.000001 IP 10.66.73.2.55911 > 10.66.73.1.8080: Flags [S], seq 1, win 65535, length 0\n13:00:00.000002 IP 10.66.73.1.8080 > 10.66.73.2.55911: Flags [S.], seq 2, ack 2, win 65160, length 0'
ecn=$'13:00:00.000003 IP 10.66.73.2.55911 > 10.66.73.1.8080: Flags [SEW], seq 1, win 65535, length 0\n13:00:00.000004 IP 10.66.73.1.8080 > 10.66.73.2.55911: Flags [S.E], seq 2, ack 2, win 65160, length 0'
ack=$'13:00:00.000005 IP 10.66.73.2.55911 > 10.66.73.1.8080: Flags [.], ack 3, win 2059, length 0'
pshack=$'13:00:00.000006 IP 10.66.73.2.55911 > 10.66.73.1.8080: Flags [P.], seq 3:79, ack 3, win 2059, length 78: HTTP: GET / HTTP/1.1'
wrong_direction=$'13:00:00.000007 IP 10.66.73.1.55911 > 10.66.73.2.8080: Flags [S], seq 4, win 65160, length 0'
wrong_port=$'13:00:00.000008 IP 10.66.73.2.55911 > 10.66.73.1.9090: Flags [SEW], seq 5, win 65535, length 0'
http=$'13:00:00.000009 IP 10.66.73.2.55911 > 10.66.73.1.8080: Flags [P.], seq 1:79, ack 1, length 78: HTTP: GET / HTTP/1.1\n13:00:00.000010 IP 10.66.73.1.8080 > 10.66.73.2.55911: Flags [P.], seq 1:287, ack 79, length 286: HTTP: HTTP/1.1 200 OK'

expect_exact TCP_PARSE_CLASSIC_SYN_AND_SYNACK 'SYN SYNACK' "$classic"
echo 'TCP_PARSE_CLASSIC_SYN = PASS'
echo 'TCP_PARSE_CLASSIC_SYNACK = PASS'
expect_exact TCP_PARSE_ECN_SYN_AND_SYNACK 'SYN SYNACK' "$ecn"
echo 'TCP_PARSE_ECN_SYN = PASS'
echo 'TCP_PARSE_ECN_SYNACK = PASS'
expect_absent TCP_PARSE_ACK_NOT_SYN SYN "$ack"
expect_absent TCP_PARSE_ACK_NOT_SYNACK SYNACK "$ack"
echo 'TCP_PARSE_ACK_NOT_SYN = PASS'
echo 'TCP_PARSE_ACK_NOT_SYNACK = PASS'
expect_absent TCP_PARSE_PSHACK_NOT_SYN SYN "$pshack"
expect_absent TCP_PARSE_PSHACK_NOT_SYNACK SYNACK "$pshack"
echo 'TCP_PARSE_PSHACK_NOT_SYNACK = PASS'
expect_absent TCP_PARSE_WRONG_DIRECTION_REJECTED SYN "$wrong_direction"
expect_absent TCP_PARSE_WRONG_DIRECTION_REJECTED_SYNACK SYNACK "$wrong_direction"
echo 'TCP_PARSE_WRONG_DIRECTION_REJECTED = PASS'
expect_absent TCP_PARSE_WRONG_PORT_REJECTED SYN "$wrong_port"
expect_absent TCP_PARSE_WRONG_PORT_REJECTED_SYNACK SYNACK "$wrong_port"
echo 'TCP_PARSE_WRONG_PORT_REJECTED = PASS'
expect_exact TCP_PARSE_HTTP_DIRECTION 'HTTP_DATA HTTP_GET HTTP_DATA HTTP_200' "$http"
echo 'TCP_PARSE_HTTP_GET_DIRECTION = PASS'
echo 'TCP_PARSE_HTTP_200_DIRECTION = PASS'
echo 'STAGE4_HOST_SCRIPT_GATE = PASS'
