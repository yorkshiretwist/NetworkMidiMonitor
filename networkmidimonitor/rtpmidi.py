# SPDX-License-Identifier: GPL-3.0-or-later
"""RTP-MIDI (RFC 6295) payload parsing and the Apple network-MIDI session peer."""
from __future__ import annotations

import asyncio
import logging
import random
import shutil
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable

from .midi import MidiMessage, decode, read_message

log = logging.getLogger(__name__)

SERVICE_TYPE = "_apple-midi._udp.local."
PROTOCOL_VERSION = 2


# ---------------------------------------------------------------- RTP payload

@dataclass
class RtpMidiPacket:
    seq: int
    timestamp: int
    ssrc: int
    commands: list[tuple[int, bytes]] = field(default_factory=list)  # (delta, raw message)


def _read_vlq(data: bytes, i: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if i >= len(data):
            break
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            break
    return value, i


def parse_rtp_midi(packet: bytes) -> RtpMidiPacket | None:
    """Parse an RTP packet carrying a MIDI command section. Journal is ignored."""
    if len(packet) < 13 or packet[0] >> 6 != 2:
        return None
    csrc = packet[0] & 0x0F
    offset = 12 + 4 * csrc
    if packet[0] & 0x10:  # header extension
        if len(packet) < offset + 4:
            return None
        offset += 4 + 4 * struct.unpack_from("!H", packet, offset + 2)[0]
    if offset >= len(packet):
        return None
    seq, timestamp, ssrc = struct.unpack_from("!HII", packet, 2)
    payload = packet[offset:]

    header = payload[0]
    long_len, has_z = bool(header & 0x80), bool(header & 0x20)
    if long_len:
        if len(payload) < 2:
            return None
        length, pos = ((header & 0x0F) << 8) | payload[1], 2
    else:
        length, pos = header & 0x0F, 1
    section = payload[pos:pos + length]

    result = RtpMidiPacket(seq, timestamp, ssrc)
    i, running, first = 0, None, True
    while i < len(section):
        if first and not has_z:
            delta = 0
        else:
            delta, i = _read_vlq(section, i)
        first = False
        if i >= len(section):
            break
        msg, i, running = read_message(section, i, running)
        if msg:
            result.commands.append((delta, msg))
    return result


# ------------------------------------------------------------ session packets

def build_invite(cmd: bytes, token: int, ssrc: int, name: str) -> bytes:
    """cmd is b'IN', b'OK' or b'NO'."""
    return (b"\xff\xff" + cmd + struct.pack("!III", PROTOCOL_VERSION, token, ssrc)
            + name.encode("utf-8", "replace") + b"\x00")


def build_bye(token: int, ssrc: int) -> bytes:
    return b"\xff\xffBY" + struct.pack("!III", PROTOCOL_VERSION, token, ssrc)


def build_clock(ssrc: int, count: int, t1: int, t2: int, t3: int) -> bytes:
    return b"\xff\xffCK" + struct.pack("!IB3xQQQ", ssrc, count, t1, t2, t3)


def parse_session(data: bytes) -> dict | None:
    """Parse an Apple session packet; returns None if it isn't one."""
    if len(data) < 4 or data[:2] != b"\xff\xff":
        return None
    cmd = data[2:4].decode("ascii", "replace")
    if cmd in ("IN", "OK", "NO", "BY"):
        if len(data) < 16:
            return None
        version, token, ssrc = struct.unpack_from("!III", data, 4)
        name = data[16:].split(b"\x00", 1)[0].decode("utf-8", "replace")
        return {"cmd": cmd, "version": version, "token": token, "ssrc": ssrc, "name": name}
    if cmd == "CK":
        if len(data) < 36:
            return None
        ssrc, count, t1, t2, t3 = struct.unpack_from("!IB3xQQQ", data, 4)
        return {"cmd": cmd, "ssrc": ssrc, "count": count, "t": (t1, t2, t3)}
    return {"cmd": cmd}


# ------------------------------------------------------------------- the peer

@dataclass
class Peer:
    ssrc: int
    name: str
    host: str
    ctrl_port: int
    data_port: int | None = None
    token: int = 0
    initiator: bool = False  # True when we invited them
    connected: bool = False
    last_seq: int | None = None
    lost: int = 0


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, handler: Callable[[bytes, tuple], None]) -> None:
        self.handler = handler
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport):  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data, addr):  # type: ignore[override]
        try:
            self.handler(data, addr)
        except Exception:  # never let a malformed packet kill the socket
            log.exception("error handling packet from %s", addr)


class RtpMidiSession:
    """Listens as an Apple network-MIDI participant and reports incoming MIDI.

    on_message(source, message): called for every decoded MIDI message.
    on_change(): called whenever the peer list or counters change.
    """

    def __init__(self, name: str, bind_ip: str, on_message: Callable[[str, MidiMessage], None],
                 on_change: Callable[[], None], port: int = 5004, advertise: bool = True,
                 advertise_ip: str | None = None) -> None:
        self.name = name
        self.bind_ip = bind_ip
        self.advertise_ip = advertise_ip or bind_ip  # address announced over mDNS
        self.base_port = port
        self.advertise = advertise
        self.on_message = on_message
        self.on_change = on_change
        self.ssrc = random.getrandbits(32)
        self.port: int | None = None
        self.peers: dict[int, Peer] = {}
        self._invites: dict[int, dict] = {}  # token -> outstanding invitation
        self._t0 = time.monotonic()
        self._ctrl: _Proto | None = None
        self._data: _Proto | None = None
        self._tasks: set[asyncio.Task] = set()
        self._zc = None
        self._zc_info = None
        self._dnssd: asyncio.subprocess.Process | None = None

    # -- lifecycle
    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        last_err: Exception | None = None
        for port in range(self.base_port, self.base_port + 12, 2):
            ctrl, data = _Proto(self._on_control), _Proto(self._on_data)
            try:
                await loop.create_datagram_endpoint(lambda: ctrl, local_addr=(self.bind_ip, port))
                try:
                    await loop.create_datagram_endpoint(lambda: data, local_addr=(self.bind_ip, port + 1))
                except OSError:
                    ctrl.transport.close()
                    raise
            except OSError as e:
                last_err = e
                continue
            self._ctrl, self._data, self.port = ctrl, data, port
            break
        else:
            raise OSError(f"could not bind RTP-MIDI ports starting at {self.base_port}: {last_err}")
        self._spawn(self._clock_loop())
        if self.advertise:
            await self._register_mdns()

    async def stop(self) -> None:
        for p in list(self.peers.values()):
            if p.connected and self._ctrl and self._ctrl.transport:
                self._ctrl.transport.sendto(build_bye(p.token, self.ssrc), (p.host, p.ctrl_port))
        for t in list(self._tasks):
            t.cancel()
        if self._dnssd and self._dnssd.returncode is None:
            self._dnssd.terminate()
        if self._zc:
            try:
                await self._zc.async_unregister_service(self._zc_info)
                await self._zc.async_close()
            except Exception:
                log.debug("mdns shutdown failed", exc_info=True)
        for proto in (self._ctrl, self._data):
            if proto and proto.transport:
                proto.transport.close()
        self.peers.clear()

    async def _register_via_bonjour(self) -> bool:
        """Announce through the system Bonjour daemon (`dns-sd`), if present.

        Needed on Windows: the Bonjour daemon doesn't see announcements made by another
        process on the same PC, so rtpMIDI's Directory would never list us otherwise.
        """
        exe = shutil.which("dns-sd")
        if not exe:
            return False
        try:
            self._dnssd = await asyncio.create_subprocess_exec(
                exe, "-R", self.name, "_apple-midi._udp", "local", str(self.port),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            await asyncio.sleep(0.5)
            return self._dnssd.returncode is None
        except OSError:
            return False

    async def _register_mdns(self) -> None:
        if await self._register_via_bonjour():
            return
        try:
            from zeroconf import ServiceInfo
            from zeroconf.asyncio import AsyncZeroconf
            self._zc = AsyncZeroconf(interfaces=[self.advertise_ip])
            host = socket.gethostname().split(".")[0]
            self._zc_info = ServiceInfo(
                SERVICE_TYPE, f"{self.name}.{SERVICE_TYPE}", port=self.port,
                addresses=[socket.inet_aton(self.advertise_ip)], server=f"{host}.local.")
            await self._zc.async_register_service(self._zc_info)
        except Exception as e:
            log.warning("mDNS advertising failed (peers must invite us by IP): %s", e)
            self._zc = None

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.ensure_future(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def _now(self) -> int:
        return int((time.monotonic() - self._t0) * 10000)  # 100 µs units

    # -- outgoing invitations
    def invite(self, host: str, port: int = 5004) -> None:
        token = random.getrandbits(32)
        self._invites[token] = {"host": host, "port": port}
        self._spawn(self._invite_loop(token, host, port))

    async def _invite_loop(self, token: int, host: str, port: int) -> None:
        for _ in range(12):
            inv = self._invites.get(token)
            if inv is None or inv.get("done"):
                return
            if self._ctrl and self._ctrl.transport:
                self._ctrl.transport.sendto(build_invite(b"IN", token, self.ssrc, self.name), (host, port))
            await asyncio.sleep(1.0)
        self._invites.pop(token, None)
        log.warning("invitation to %s:%s timed out", host, port)

    def disconnect(self, ssrc: int) -> None:
        p = self.peers.pop(ssrc, None)
        if p and self._ctrl and self._ctrl.transport:
            self._ctrl.transport.sendto(build_bye(p.token, self.ssrc), (p.host, p.ctrl_port))
        self.on_change()

    # -- packet handling
    def _on_control(self, data: bytes, addr: tuple) -> None:
        pkt = parse_session(data)
        if pkt:
            self._session_packet(pkt, addr, on_data_port=False)

    def _on_data(self, data: bytes, addr: tuple) -> None:
        pkt = parse_session(data)
        if pkt:
            self._session_packet(pkt, addr, on_data_port=True)
            return
        rtp = parse_rtp_midi(data)
        if rtp:
            self._rtp_packet(rtp, addr)

    def _session_packet(self, pkt: dict, addr: tuple, on_data_port: bool) -> None:
        cmd = pkt["cmd"]
        if pkt.get("ssrc") == self.ssrc:  # our own packet (e.g. invited ourselves): ignore
            return
        proto = self._data if on_data_port else self._ctrl
        send = proto.transport.sendto  # type: ignore[union-attr]
        if cmd == "IN":
            peer = self.peers.get(pkt["ssrc"])
            if peer is None:
                peer = self.peers[pkt["ssrc"]] = Peer(pkt["ssrc"], pkt["name"], addr[0], addr[1] - (1 if on_data_port else 0))
            peer.token, peer.name = pkt["token"], pkt["name"] or peer.name
            if on_data_port:
                peer.data_port, peer.connected = addr[1], True
            else:
                peer.host, peer.ctrl_port = addr[0], addr[1]
            send(build_invite(b"OK", pkt["token"], self.ssrc, self.name), addr)
            self.on_change()
        elif cmd == "OK":
            inv = self._invites.get(pkt["token"])
            if inv is None:
                return
            peer = self.peers.get(pkt["ssrc"])
            if peer is None:
                peer = self.peers[pkt["ssrc"]] = Peer(pkt["ssrc"], pkt["name"], addr[0], inv["port"],
                                                      token=pkt["token"], initiator=True)
            if not on_data_port:  # control OK: now invite on the data port
                send_data = self._data.transport.sendto  # type: ignore[union-attr]
                send_data(build_invite(b"IN", pkt["token"], self.ssrc, self.name), (addr[0], addr[1] + 1))
            else:
                peer.data_port, peer.connected = addr[1], True
                inv["done"] = True
                self._invites.pop(pkt["token"], None)
                self._send_clock0(peer)
            self.on_change()
        elif cmd == "NO":
            self._invites.pop(pkt["token"], None)
            log.warning("invitation rejected by %s", pkt.get("name"))
        elif cmd == "BY":
            if self.peers.pop(pkt["ssrc"], None):
                self.on_change()
        elif cmd == "CK" and on_data_port:
            count, (t1, t2, _t3) = pkt["count"], pkt["t"]
            if count == 0:
                send(build_clock(self.ssrc, 1, t1, self._now(), 0), addr)
            elif count == 1:
                send(build_clock(self.ssrc, 2, t1, t2, self._now()), addr)

    def _send_clock0(self, peer: Peer) -> None:
        if peer.data_port and self._data and self._data.transport:
            self._data.transport.sendto(build_clock(self.ssrc, 0, self._now(), 0, 0), (peer.host, peer.data_port))

    async def _clock_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            for p in list(self.peers.values()):
                if p.initiator and p.connected:
                    self._send_clock0(p)

    def _rtp_packet(self, rtp: RtpMidiPacket, addr: tuple) -> None:
        peer = self.peers.get(rtp.ssrc)
        source = peer.name if peer else addr[0]
        if peer:
            if peer.last_seq is not None:
                gap = (rtp.seq - ((peer.last_seq + 1) & 0xFFFF)) & 0xFFFF
                if 0 < gap < 0x8000:
                    peer.lost += gap
                    self.on_change()
            peer.last_seq = rtp.seq
        for _delta, raw in rtp.commands:
            self.on_message(source, decode(raw))

    def peer_list(self) -> list[dict]:
        return [{"ssrc": p.ssrc, "name": p.name, "host": p.host, "connected": p.connected, "lost": p.lost}
                for p in self.peers.values()]
