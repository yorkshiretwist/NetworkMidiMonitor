# SPDX-License-Identifier: GPL-3.0-or-later
"""MIDI byte-stream parsing and human-readable decoding."""
from __future__ import annotations

from dataclasses import dataclass

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CC_NAMES = {
    0: "Bank Select", 1: "Mod Wheel", 2: "Breath", 4: "Foot", 5: "Portamento Time",
    6: "Data Entry", 7: "Volume", 10: "Pan", 11: "Expression", 64: "Sustain",
    65: "Portamento", 66: "Sostenuto", 67: "Soft Pedal", 71: "Resonance", 74: "Cutoff",
    91: "Reverb", 93: "Chorus", 120: "All Sound Off", 121: "Reset Controllers",
    123: "All Notes Off",
}

REALTIME = {
    0xF8: ("clock", "Timing Clock"),
    0xFA: ("start", "Start"),
    0xFB: ("continue", "Continue"),
    0xFC: ("stop", "Stop"),
    0xFE: ("active_sensing", "Active Sensing"),
    0xFF: ("system_reset", "System Reset"),
}


def note_name(n: int) -> str:
    """Middle C (60) is C4."""
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


@dataclass(frozen=True)
class MidiMessage:
    raw: bytes
    channel: int | None  # 1-16, or None for system messages
    kind: str
    text: str

    @property
    def hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.raw)


def _data_length(status: int) -> int:
    if status < 0xF0:
        return 1 if (status & 0xF0) in (0xC0, 0xD0) else 2
    return {0xF1: 1, 0xF2: 2, 0xF3: 1}.get(status, 0)


def read_message(data, i: int, running: int | None):
    """Read one message from ``data`` at offset ``i``.

    Returns ``(message_bytes_or_None, next_index, running_status)``.
    ``None`` means the byte was skipped (stray data) or the message was truncated.
    """
    b = data[i]
    if b >= 0xF8:  # real-time: never touches running status
        return bytes([b]), i + 1, running
    if b == 0xF0:  # SysEx: runs to F7 (or end of data if segmented)
        end = bytes(data).find(b"\xf7", i)
        if end == -1:
            return bytes(data[i:]), len(data), None
        return bytes(data[i:end + 1]), end + 1, None
    if b >= 0x80:
        status, start = b, i + 1
    else:
        if running is None:
            return None, i + 1, running
        status, start = running, i
    n = _data_length(status)
    chunk = data[start:start + n]
    new_running = status if status < 0xF0 else None
    if len(chunk) < n:
        return None, len(data), new_running  # truncated
    return bytes([status]) + bytes(chunk), start + n, new_running


def decode(msg: bytes) -> MidiMessage:
    status = msg[0]
    if status >= 0xF8:
        kind, text = REALTIME.get(status, ("unknown", f"Realtime {status:02X}"))
        return MidiMessage(msg, None, kind, text)
    if status == 0xF0:
        return MidiMessage(msg, None, "sysex", f"SysEx {len(msg)} bytes")
    if status >= 0xF0:
        d = msg[1:]
        if status == 0xF1:
            return MidiMessage(msg, None, "mtc", f"MTC Quarter Frame {d[0]:02X}")
        if status == 0xF2:
            return MidiMessage(msg, None, "song_position", f"Song Position {d[0] | d[1] << 7}")
        if status == 0xF3:
            return MidiMessage(msg, None, "song_select", f"Song Select {d[0]}")
        if status == 0xF6:
            return MidiMessage(msg, None, "tune_request", "Tune Request")
        return MidiMessage(msg, None, "unknown", f"System {status:02X}")

    ch = (status & 0x0F) + 1
    d = msg[1:]
    t = status & 0xF0
    if t == 0x90 and d[1] > 0:
        return MidiMessage(msg, ch, "note_on", f"Note On {note_name(d[0])} vel {d[1]}")
    if t == 0x90 or t == 0x80:
        return MidiMessage(msg, ch, "note_off", f"Note Off {note_name(d[0])} vel {d[1]}")
    if t == 0xA0:
        return MidiMessage(msg, ch, "poly_aftertouch", f"Poly Aftertouch {note_name(d[0])} = {d[1]}")
    if t == 0xB0:
        name = CC_NAMES.get(d[0])
        label = f"CC {d[0]}" + (f" ({name})" if name else "")
        return MidiMessage(msg, ch, "control_change", f"{label} = {d[1]}")
    if t == 0xC0:
        return MidiMessage(msg, ch, "program_change", f"Program Change {d[0]}")
    if t == 0xD0:
        return MidiMessage(msg, ch, "channel_aftertouch", f"Channel Aftertouch = {d[0]}")
    return MidiMessage(msg, ch, "pitch_bend", f"Pitch Bend {(d[0] | d[1] << 7) - 8192:+d}")


class StreamParser:
    """Byte-wise parser for a raw MIDI stream.

    Keeps running status and handles real-time bytes interleaved inside other messages.
    """

    def __init__(self) -> None:
        self.status: int | None = None  # current/running channel status
        self.data = bytearray()
        self.sysex: bytearray | None = None

    def feed(self, data: bytes) -> list[MidiMessage]:
        out: list[MidiMessage] = []
        for b in data:
            if b >= 0xF8:  # real-time can appear anywhere
                out.append(decode(bytes([b])))
            elif b == 0xF7 and self.sysex is not None:
                self.sysex.append(b)
                out.append(decode(bytes(self.sysex)))
                self.sysex = None
            elif b >= 0x80:
                self.sysex, self.data = None, bytearray()
                if b == 0xF0:
                    self.sysex, self.status = bytearray([b]), None
                elif _data_length(b) == 0:
                    self.status = None
                    out.append(decode(bytes([b])))
                else:
                    self.status = b
            elif self.sysex is not None:
                self.sysex.append(b)
            elif self.status is not None:
                self.data.append(b)
                if len(self.data) == _data_length(self.status):
                    out.append(decode(bytes([self.status]) + bytes(self.data)))
                    self.data = bytearray()
                    if self.status >= 0xF0:  # system common doesn't set running status
                        self.status = None
        return out
