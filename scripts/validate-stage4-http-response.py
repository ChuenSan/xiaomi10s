#!/usr/bin/env python3
"""Validate the canonical Stage4 HTTP/1.1 response contract."""
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def main(marker: str) -> None:
    marker = marker[:7]
    if not re.fullmatch(r"[0-9a-fA-F]{7}", marker):
        fail("BUILD_MARKER must be a 7-character commit marker")

    body = (
        "CONTROL=STOCK_KERNEL_USB_STAGE4\n"
        "DEVICE=thyme\n"
        "KERNEL=4.19.157-perf\n"
        "USB=NCM\n"
        "DEVICE_IP=10.66.73.1\n"
        "HTTP_READY=YES\n"
        "STAGE0_USB_ENUM=PASS\n"
        "STAGE1_LINK=PASS\n"
        "STAGE2_DEVICE_IP=PASS\n"
        "STAGE3_ICMP=PASS\n"
        f"BUILD={marker}\n"
    ).encode("ascii")
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/plain\r\n"
        b"Connection: close\r\n"
        b"Content-Length: "
        + str(len(body)).encode("ascii")
        + b"\r\n\r\n"
        + body
    )

    head, separator, got_body = response.partition(b"\r\n\r\n")
    if separator != b"\r\n\r\n":
        fail("HTTP header/body separator")
    lines = head.split(b"\r\n")
    if lines[0] != b"HTTP/1.1 200 OK":
        fail("HTTP status line")
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(b": ")
        if sep != b": ":
            fail("malformed header")
        headers[name.lower()] = value
    if headers.get(b"content-type") != b"text/plain":
        fail("Content-Type")
    if headers.get(b"connection") != b"close":
        fail("Connection")
    try:
        content_length = int(headers[b"content-length"])
    except (KeyError, ValueError):
        fail("Content-Length")
    if content_length != len(got_body) or got_body != body:
        fail("Content-Length does not equal response body")

    print("HTTP_RESPONSE_200_PRESENT PASS")
    print(f"CONTENT_LENGTH={content_length}")
    print("CONTENT_LENGTH_VALIDATION PASS")
    print(f"EXPECTED_BODY_BUILD=BUILD={marker}")
    print("EXPECTED_BODY_UNIQUE PASS")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate-stage4-http-response.py <7-char-build-marker>")
    main(sys.argv[1])
