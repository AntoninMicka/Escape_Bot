#!/usr/bin/env python3
"""Minimální lokální DNS a HTTP responder pro captive detekci."""

from __future__ import annotations

import argparse
import selectors
import socket
import struct


def dns_response(query: bytes, gateway: str) -> bytes | None:
    if len(query) < 12:
        return None
    transaction_id = query[:2]
    question_count = struct.unpack("!H", query[4:6])[0]
    if question_count != 1:
        return None

    offset = 12
    while offset < len(query) and query[offset] != 0:
        label_length = query[offset]
        offset += label_length + 1
    if offset + 5 > len(query):
        return None
    offset += 1
    query_type = struct.unpack("!H", query[offset : offset + 2])[0]
    question = query[12 : offset + 4]

    answer_count = 1 if query_type == 1 else 0
    header = transaction_id + struct.pack("!HHHHH", 0x8180, 1, answer_count, 0, 0)
    if not answer_count:
        return header + question
    answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 30, 4) + socket.inet_aton(gateway)
    return header + question + answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="10.42.0.1")
    parser.add_argument("--game-url", default="https://10.42.0.1:8088/")
    args = parser.parse_args()

    selector = selectors.DefaultSelector()
    dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns.bind(("0.0.0.0", 1053))
    dns.setblocking(False)
    selector.register(dns, selectors.EVENT_READ, "dns")

    http = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    http.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http.bind(("0.0.0.0", 8091))
    http.listen(32)
    http.setblocking(False)
    selector.register(http, selectors.EVENT_READ, "http")

    location = args.game_url.encode("ascii")
    response = (
        b"HTTP/1.1 302 Found\r\n"
        + b"Location: " + location + b"\r\n"
        + b"Cache-Control: no-store\r\n"
        + b"Connection: close\r\n"
        + b"Content-Length: 0\r\n\r\n"
    )

    while True:
        for key, _ in selector.select():
            if key.data == "dns":
                query, address = dns.recvfrom(4096)
                answer = dns_response(query, args.gateway)
                if answer:
                    dns.sendto(answer, address)
            else:
                connection, _ = http.accept()
                try:
                    connection.settimeout(1)
                    connection.recv(4096)
                    connection.sendall(response)
                finally:
                    connection.close()


if __name__ == "__main__":
    main()
