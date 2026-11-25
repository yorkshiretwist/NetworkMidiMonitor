# SPDX-License-Identifier: GPL-3.0-or-later
from networkmidimonitor.midi import StreamParser, note_name


def parse(data: bytes):
    return StreamParser().feed(data)


def test_note_names():
    assert note_name(60) == "C4"
    assert note_name(61) == "C#4"
    assert note_name(0) == "C-1"


def test_note_on_off():
    (m,) = parse(bytes([0x90, 0x3C, 0x64]))
    assert (m.kind, m.channel, m.text) == ("note_on", 1, "Note On C4 vel 100")
    (m,) = parse(bytes([0x80, 0x3C, 0x00]))
    assert m.kind == "note_off"


def test_note_on_velocity_zero_is_note_off():
    (m,) = parse(bytes([0x99, 0x26, 0x00]))
    assert (m.kind, m.channel) == ("note_off", 10)


def test_running_status():
    msgs = parse(bytes([0x90, 0x3C, 0x64, 0x3E, 0x50]))
    assert [m.text for m in msgs] == ["Note On C4 vel 100", "Note On D4 vel 80"]


def test_running_status_persists_across_feeds():
    p = StreamParser()
    p.feed(bytes([0x90, 0x3C, 0x64]))
    (m,) = p.feed(bytes([0x3E, 0x50]))
    assert m.text == "Note On D4 vel 80"


def test_realtime_interleaved_does_not_break_running_status():
    msgs = parse(bytes([0x90, 0x3C, 0xF8, 0x64, 0x3E, 0x50]))
    assert [m.kind for m in msgs] == ["clock", "note_on", "note_on"]


def test_control_change_and_program_change():
    (cc,) = parse(bytes([0xB1, 0x07, 0x60]))
    assert cc.text == "CC 7 (Volume) = 96" and cc.channel == 2
    (pc,) = parse(bytes([0xC0, 0x05]))
    assert (pc.kind, pc.text) == ("program_change", "Program Change 5")


def test_pitch_bend():
    (m,) = parse(bytes([0xE0, 0x00, 0x40]))
    assert m.text == "Pitch Bend +0"
    (m,) = parse(bytes([0xE1, 0x00, 0x48]))
    assert m.text == "Pitch Bend +1024"
    (m,) = parse(bytes([0xE0, 0x00, 0x00]))
    assert m.text == "Pitch Bend -8192"


def test_sysex_and_system_messages():
    (m,) = parse(bytes([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]))
    assert (m.kind, m.text) == ("sysex", "SysEx 6 bytes")
    (m,) = parse(bytes([0xFE]))
    assert m.kind == "active_sensing"
    (m,) = parse(bytes([0xF2, 0x10, 0x01]))
    assert m.text == "Song Position 144"


def test_stray_data_and_truncation_are_ignored():
    assert parse(bytes([0x3C, 0x64])) == []
    assert parse(bytes([0x90, 0x3C])) == []
