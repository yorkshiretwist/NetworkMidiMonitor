# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import struct

import pytest

from networkmidimonitor.rtpmidi import (RtpMidiSession, build_bye, build_clock, build_invite,
                                         parse_rtp_midi, parse_session)


def rtp(payload: bytes, seq=1, ssrc=0xABCD) -> bytes:
    return struct.pack("!BBHII", 0x80, 0x61, seq, 1000, ssrc) + payload


# ------------------------------------------------------------- payload parsing

def test_single_command():
    p = parse_rtp_midi(rtp(bytes([0x03, 0x90, 0x3C, 0x64])))
    assert p.seq == 1 and p.ssrc == 0xABCD
    assert p.commands == [(0, bytes([0x90, 0x3C, 0x64]))]


def test_two_commands_with_delta():
    p = parse_rtp_midi(rtp(bytes([0x07, 0x90, 0x3C, 0x64, 0x10, 0x80, 0x3C, 0x00])))
    assert p.commands == [(0, bytes([0x90, 0x3C, 0x64])), (16, bytes([0x80, 0x3C, 0x00]))]


def test_first_delta_present_when_z_set():
    p = parse_rtp_midi(rtp(bytes([0x24, 0x05, 0x90, 0x3C, 0x64])))
    assert p.commands == [(5, bytes([0x90, 0x3C, 0x64]))]


def test_running_status_in_command_list():
    p = parse_rtp_midi(rtp(bytes([0x07, 0x90, 0x3C, 0x64, 0x00, 0x3E, 0x50])))
    assert [c[1] for c in p.commands] == [bytes([0x90, 0x3C, 0x64]), bytes([0x90, 0x3E, 0x50])]


def test_long_header_and_journal_flag_ignored():
    body = bytes([0x90, 0x3C, 0x64])
    payload = bytes([0x80 | 0x40, len(body)]) + body + b"\x00\x00\x00\x00"  # B + J set, journal junk
    p = parse_rtp_midi(rtp(payload))
    assert p.commands == [(0, body)]


def test_variable_length_delta():
    p = parse_rtp_midi(rtp(bytes([0x08, 0x90, 0x3C, 0x64, 0x81, 0x00, 0x80, 0x3C, 0x00])))
    assert p.commands[1][0] == 128


def test_rejects_garbage():
    assert parse_rtp_midi(b"") is None
    assert parse_rtp_midi(b"\x00" * 20) is None  # wrong RTP version


# ---------------------------------------------------------------- session pdus

def test_session_roundtrip():
    pkt = parse_session(build_invite(b"IN", 0x1234, 0x5678, "Studio PC"))
    assert pkt == {"cmd": "IN", "version": 2, "token": 0x1234, "ssrc": 0x5678, "name": "Studio PC"}
    assert parse_session(build_bye(1, 2))["cmd"] == "BY"
    ck = parse_session(build_clock(9, 1, 10, 20, 30))
    assert ck["count"] == 1 and ck["t"] == (10, 20, 30)
    assert parse_session(b"\x80\x61") is None


# ----------------------------------------------------------- live session test

class Client(asyncio.DatagramProtocol):
    def __init__(self):
        self.q: asyncio.Queue = asyncio.Queue()
        self.transport = None

    def connection_made(self, t):
        self.transport = t

    def datagram_received(self, data, addr):
        self.q.put_nowait((data, addr))

    async def get(self):
        return await asyncio.wait_for(self.q.get(), 3)


async def make_client(port: int) -> Client:
    loop = asyncio.get_running_loop()
    _, c = await loop.create_datagram_endpoint(Client, local_addr=("127.0.0.1", port))
    return c


@pytest.fixture
async def session():
    got, changes = [], []
    s = RtpMidiSession("TestMon", "127.0.0.1", lambda src, m: got.append((src, m)),
                       lambda: changes.append(1), port=15004, advertise=False)
    await s.start()
    yield s, got
    await s.stop()


async def test_accepts_invitation_and_receives_midi(session):
    s, got = session
    ctrl, data = await make_client(16004), await make_client(16005)
    ctrl.transport.sendto(build_invite(b"IN", 7, 0xABCD, "rtpMIDI Desktop"), ("127.0.0.1", s.port))
    reply, _ = await ctrl.get()
    assert parse_session(reply)["cmd"] == "OK" and parse_session(reply)["token"] == 7
    data.transport.sendto(build_invite(b"IN", 7, 0xABCD, "rtpMIDI Desktop"), ("127.0.0.1", s.port + 1))
    reply, _ = await data.get()
    assert parse_session(reply)["cmd"] == "OK"
    assert s.peer_list()[0]["connected"] and s.peer_list()[0]["name"] == "rtpMIDI Desktop"

    data.transport.sendto(rtp(bytes([0x03, 0x90, 0x3C, 0x64]), seq=1), ("127.0.0.1", s.port + 1))
    data.transport.sendto(rtp(bytes([0x03, 0x80, 0x3C, 0x00]), seq=4), ("127.0.0.1", s.port + 1))  # seq 2,3 lost
    await asyncio.sleep(0.2)
    assert [(src, m.text) for src, m in got] == [("rtpMIDI Desktop", "Note On C4 vel 100"),
                                                 ("rtpMIDI Desktop", "Note Off C4 vel 0")]
    assert s.peer_list()[0]["lost"] == 2

    # clock sync handshake: CK0 -> CK1
    data.transport.sendto(build_clock(0xABCD, 0, 123, 0, 0), ("127.0.0.1", s.port + 1))
    ck = parse_session((await data.get())[0])
    assert ck["cmd"] == "CK" and ck["count"] == 1 and ck["t"][0] == 123

    ctrl.transport.sendto(build_bye(7, 0xABCD), ("127.0.0.1", s.port))
    await asyncio.sleep(0.2)
    assert s.peer_list() == []


async def test_inviting_a_peer(session):
    s, got = session
    ctrl, data = await make_client(17004), await make_client(17005)
    s.invite("127.0.0.1", 17004)
    pkt, _ = await ctrl.get()
    inv = parse_session(pkt)
    assert inv["cmd"] == "IN" and inv["name"] == "TestMon"
    ctrl.transport.sendto(build_invite(b"OK", inv["token"], 0x4242, "Remote"), ("127.0.0.1", s.port))
    pkt, _ = await data.get()  # we now invite on the data port
    assert parse_session(pkt)["cmd"] == "IN"
    data.transport.sendto(build_invite(b"OK", inv["token"], 0x4242, "Remote"), ("127.0.0.1", s.port + 1))
    ck, _ = await data.get()  # initiator starts clock sync
    assert parse_session(ck)["cmd"] == "CK" and parse_session(ck)["count"] == 0
    assert s.peer_list()[0]["connected"]


async def test_ignores_its_own_invitation(session):
    s, _ = session
    c = await make_client(18004)
    c.transport.sendto(build_invite(b"IN", 1, s.ssrc, "me"), ("127.0.0.1", s.port))
    await asyncio.sleep(0.3)
    assert c.q.empty() and s.peer_list() == []
