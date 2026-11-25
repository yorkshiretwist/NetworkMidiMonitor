# SPDX-License-Identifier: GPL-3.0-or-later
"""UDP multicast MIDI listener (QmidiNet / ipMIDI / multimidicast compatible)."""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Callable

from .midi import MidiMessage, StreamParser

log = logging.getLogger(__name__)

DEFAULT_GROUP = "225.0.0.37"
BASE_PORT = 21928  # cable 1


def cable_number(port: int) -> int:
    return port - BASE_PORT + 1


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, port: int, on_message: Callable[[str, MidiMessage], None]) -> None:
        self.port = port
        self.on_message = on_message
        self.parsers: dict[str, StreamParser] = {}

    def datagram_received(self, data, addr):  # type: ignore[override]
        parser = self.parsers.setdefault(addr[0], StreamParser())
        try:
            msgs = parser.feed(data)
        except Exception:
            log.exception("bad multicast datagram from %s", addr)
            return
        source = f"cable {cable_number(self.port)} ({addr[0]})"
        for m in msgs:
            self.on_message(source, m)


def _make_socket(group: str, port: int, iface_ip: str) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(("", port))
        mreq = socket.inet_aton(group) + socket.inet_aton(iface_ip)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.setblocking(False)
    except OSError:
        s.close()
        raise
    return s


class MulticastListener:
    def __init__(self, group: str, iface_ip: str, on_message: Callable[[str, MidiMessage], None]) -> None:
        self.group = group
        self.iface_ip = iface_ip
        self.on_message = on_message
        self._transports: dict[int, asyncio.DatagramTransport] = {}

    @property
    def active_ports(self) -> set[int]:
        return set(self._transports)

    async def open_port(self, port: int) -> None:
        if port in self._transports:
            return
        sock = _make_socket(self.group, port, self.iface_ip)
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _Proto(port, self.on_message), sock=sock)
        self._transports[port] = transport  # type: ignore[assignment]

    def close_port(self, port: int) -> None:
        t = self._transports.pop(port, None)
        if t:
            t.close()

    def close_all(self) -> None:
        for port in list(self._transports):
            self.close_port(port)
