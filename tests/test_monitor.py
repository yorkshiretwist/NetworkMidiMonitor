# SPDX-License-Identifier: GPL-3.0-or-later
import time

from networkmidimonitor.midi import decode
from networkmidimonitor.monitor import Monitor, Settings


def test_state_includes_server_time(tmp_path):
    mon = Monitor(Settings(tmp_path / "s.json"), advertise=False)
    assert abs(mon.state()["now"] - time.time()) < 2


def test_emit_builds_events(tmp_path):
    mon = Monitor(Settings(tmp_path / "s.json"), advertise=False)
    mon.emit("cable 1 (10.0.0.2)", decode(bytes([0x90, 0x3C, 0x64])))
    mon.emit("Studio PC", decode(bytes([0x80, 0x3C, 0x00])))
    a, b = mon.drain()
    assert (a["proto"], a["ch"], a["kind"], a["raw"]) == ("mc", 1, "note_on", "90 3C 64")
    assert b["proto"] == "rtp" and mon.total == 2 and mon.drain() == []
