# SPDX-License-Identifier: GPL-3.0-or-later
"""Core: owns the listeners, settings, event buffer and statistics."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Callable

import ifaddr

from .midi import MidiMessage
from .multicast import BASE_PORT, DEFAULT_GROUP, MulticastListener, cable_number
from .rtpmidi import RtpMidiSession

log = logging.getLogger(__name__)

SETTINGS_PATH = Path.home() / ".networkmidimonitor.json"
HISTORY = 5000
MC_PORT_COUNT = 4  # cables shown in the sidebar (ports 21928..21931)


def list_interfaces() -> list[dict]:
    out = []
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if ip.is_IPv4:
                out.append({"ip": ip.ip, "name": adapter.nice_name})
    out.sort(key=lambda i: (i["ip"].startswith("127."), i["ip"].startswith("169.254."), i["name"]))
    return out


class Settings:
    DEFAULTS = {"interface": None, "mc_group": DEFAULT_GROUP, "mc_ports": [BASE_PORT],
                "rtp_name": "NetworkMidiMonitor", "rtp_port": 5006}  # 5004 is rtpMIDI's default; stay clear of it

    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path
        self.data = dict(self.DEFAULTS)
        try:
            self.data.update(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, indent=2))
        except OSError:
            log.warning("could not save settings to %s", self.path)


class Monitor:
    def __init__(self, settings: Settings | None = None, advertise: bool = True) -> None:
        self.settings = settings or Settings()
        self.advertise = advertise
        self.events: deque[dict] = deque(maxlen=HISTORY)
        self.pending: list[dict] = []
        self.total = 0
        self._rate_marks: deque[float] = deque()
        self.notices: deque[str] = deque(maxlen=5)
        self.mc: MulticastListener | None = None
        self.rtp: RtpMidiSession | None = None
        self.on_state_change: Callable[[], None] = lambda: None
        self._seq = 0
        self.interfaces = list_interfaces()
        if self.settings.data["interface"] not in {i["ip"] for i in self.interfaces}:
            self.settings.data["interface"] = self.interfaces[0]["ip"] if self.interfaces else "127.0.0.1"

    # -- lifecycle
    async def start(self) -> None:
        await self._open_network()

    async def stop(self) -> None:
        await self._close_network()

    async def _open_network(self) -> None:
        ip = self.settings.data["interface"]
        self.mc = MulticastListener(self.settings.data["mc_group"], ip, self.emit)
        for port in self.settings.data["mc_ports"]:
            await self._open_mc_port(port)
        # Bind to all addresses so peers on loopback (e.g. rtpMIDI on this PC) can be invited;
        # a socket bound to the LAN address cannot send to 127.0.0.1. The chosen interface is
        # the address announced over mDNS.
        self.rtp = RtpMidiSession(self.settings.data["rtp_name"], "0.0.0.0", self.emit, self._changed,
                                  port=self.settings.data["rtp_port"], advertise=self.advertise,
                                  advertise_ip=ip)
        try:
            await self.rtp.start()
        except OSError as e:
            self._notice(f"RTP-MIDI unavailable: {e}")
            self.rtp = None

    async def _close_network(self) -> None:
        if self.mc:
            self.mc.close_all()
        if self.rtp:
            await self.rtp.stop()
        self.mc = self.rtp = None

    async def _open_mc_port(self, port: int) -> None:
        assert self.mc
        try:
            await self.mc.open_port(port)
        except OSError as e:
            self._notice(f"Multicast port {port}: {e}")
            ports = self.settings.data["mc_ports"]
            if port in ports:
                ports.remove(port)

    def _notice(self, text: str) -> None:
        log.warning(text)
        self.notices.append(text)

    def _changed(self) -> None:
        self.on_state_change()

    # -- events
    def emit(self, source: str, msg: MidiMessage) -> None:
        self._seq += 1
        proto = "mc" if source.startswith("cable ") else "rtp"
        ev = {"id": self._seq, "t": time.time(), "proto": proto, "source": source,
              "ch": msg.channel, "kind": msg.kind, "text": msg.text, "raw": msg.hex}
        self.events.append(ev)
        self.pending.append(ev)
        self.total += 1
        self._rate_marks.append(time.monotonic())

    def drain(self) -> list[dict]:
        out, self.pending = self.pending, []
        return out

    # -- commands from the UI
    async def command(self, cmd: dict) -> None:
        name = cmd.get("cmd")
        if name == "set_interface":
            ip = str(cmd.get("ip"))
            if ip in {i["ip"] for i in self.interfaces} and ip != self.settings.data["interface"]:
                self.settings.data["interface"] = ip
                await self._close_network()
                await self._open_network()
        elif name == "mc_port":
            port = int(cmd["port"])
            if not BASE_PORT <= port < BASE_PORT + MC_PORT_COUNT:
                return
            ports = self.settings.data["mc_ports"]
            if cmd.get("enabled") and port not in ports:
                ports.append(port)
                await self._open_mc_port(port)
            elif not cmd.get("enabled") and port in ports:
                ports.remove(port)
                self.mc.close_port(port)  # type: ignore[union-attr]
        elif name == "invite" and self.rtp:
            host, _, port = str(cmd.get("host", "")).strip().partition(":")
            if host:
                self.rtp.invite(host, int(port) if port.isdigit() else 5004)
        elif name == "disconnect" and self.rtp:
            self.rtp.disconnect(int(cmd["ssrc"]))
        self.settings.save()
        self._changed()

    # -- state for the UI
    def stats(self) -> dict:
        now = time.monotonic()
        while self._rate_marks and now - self._rate_marks[0] > 1.0:
            self._rate_marks.popleft()
        lost = sum(p["lost"] for p in self.rtp.peer_list()) if self.rtp else 0
        return {"total": self.total, "rate": len(self._rate_marks), "lost": lost}

    def state(self) -> dict:
        active = self.mc.active_ports if self.mc else set()
        return {
            "type": "state",
            "now": time.time(),  # lets the UI align its timeline clock with the server's
            "interfaces": self.interfaces,
            "interface": self.settings.data["interface"],
            "multicast": {"group": self.settings.data["mc_group"],
                          "ports": [{"port": BASE_PORT + i, "cable": cable_number(BASE_PORT + i),
                                     "enabled": (BASE_PORT + i) in active} for i in range(MC_PORT_COUNT)]},
            "rtp": {"name": self.settings.data["rtp_name"], "port": self.rtp.port if self.rtp else None,
                    "peers": self.rtp.peer_list() if self.rtp else []},
            "stats": self.stats(),
            "notices": list(self.notices),
        }
