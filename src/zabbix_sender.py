"""Minimal Zabbix sender: push values to trapper items without pyzabbix.

Protocol: b"ZBXD\\x01" + 8-byte little-endian payload length + JSON body.
"""
from __future__ import annotations

import json
import socket
import struct

HEADER = b"ZBXD\x01"


def encode(host: str, key: str, value: float | str) -> bytes:
    payload = {
        "request": "sender data",
        "data": [{"host": host, "key": key, "value": value}],
    }
    body = json.dumps(payload).encode()
    return HEADER + struct.pack("<Q", len(body)) + body


def send(host: str, key: str, value: float | str, server: str, port: int = 10051) -> dict:
    data = encode(host, key, value)
    with socket.create_connection((server, port), timeout=5) as sock:
        sock.sendall(data)
        raw = sock.recv(4096)
    if not raw.startswith(HEADER):
        raise ValueError("bukan respons zabbix sender")
    length = struct.unpack("<Q", raw[5:13])[0]
    return json.loads(raw[13 : 13 + length].decode())


if __name__ == "__main__":
    import os

    server = os.environ.get("ZABBIX_HOST", "127.0.0.1")
    print(send("payment-switch-01", "settlement.failure.pct", 0.42, server))
