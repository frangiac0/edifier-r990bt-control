"""Frame format of the Edifier ConneX BLE protocol.

Based on community documentation for other models (M60, M90, MR5BT) and
verified on an R990BT.

    AA EC opcode len_hi len_lo payload... checksum   host request
    BB EC opcode len_hi len_lo payload... checksum   speaker reply
    CC EC ...                                        some ACKs

checksum = low byte of the sum of all preceding bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

HOST = 0xAA
REPLY_HEADERS = (0xBB, 0xCC)
APP_CODES = (0xEC, 0xED)

# Opcodes known from this speaker family.
OP_SONG_NAME = 0x01         # current track title (pushed by the speaker)
OP_SINGER_NAME = 0x02       # current track artist (pushed by the speaker)
OP_CAPABILITIES = 0xD8
OP_NAME = 0xC9
OP_FIRMWARE = 0xC6
OP_SOURCE_GET = 0x61
OP_SOURCE_SET = 0x62
OP_VOLUME_GET = 0x66
OP_VOLUME_SET = 0x67
OP_EQ_GET = 0xD5
OP_CUSTOM_EQ_GET = 0x43     # custom EQ query (ConneX custom_eq_query)
OP_CUSTOM_EQ_SET = 0x44     # custom EQ set one band (ConneX custom_eq_set)
OP_EQ_SET = 0xC4
OP_MEDIA = 0xC2
OP_A2DP_STATE = 0xC3
OP_POWER_OFF = 0xCE
OP_DISCONNECT_AUDIO = 0xCD
OP_NAME_SET = 0xCA
OP_CONTROL_GET = 0xF0       # generic control-setting query (ConneX tap_query)
OP_CONTROL_SET = 0xF1       # generic control-setting write (ConneX tap_set)
OP_BT_ADDRESS = 0xC8        # returns the Classic Bluetooth (BR/EDR) address (discovered)
OP_C7_STATUS = 0xC7         # one-byte status, meaning unknown (discovered)
OP_PROMPT_TONE_GET = 0xF9
OP_PROMPT_TONE_SET = 0xFA

OPCODE_NAMES = {
    OP_CAPABILITIES: "capabilities",
    OP_NAME: "name",
    OP_FIRMWARE: "firmware",
    OP_SOURCE_GET: "input (query)",
    OP_SOURCE_SET: "input (set)",
    OP_VOLUME_GET: "volume (query)",
    OP_VOLUME_SET: "volume (set)",
    OP_EQ_GET: "EQ (query)",
    OP_EQ_SET: "EQ (set)",
    OP_MEDIA: "playback",
    OP_A2DP_STATE: "Bluetooth audio state",
    OP_POWER_OFF: "power off",
    OP_DISCONNECT_AUDIO: "disconnect Bluetooth audio",
    OP_NAME_SET: "name (set)",
    OP_BT_ADDRESS: "Bluetooth address",
    OP_CONTROL_GET: "control setting (query)",
    OP_CONTROL_SET: "control setting (set)",
    OP_C7_STATUS: "status C7 (unknown)",
    OP_PROMPT_TONE_GET: "prompt tone (query)",
    OP_PROMPT_TONE_SET: "prompt tone (set)",
}


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def build(opcode: int, payload: bytes = b"", app: int = 0xEC) -> bytes:
    body = bytes([HOST, app, opcode, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF]) + payload
    return body + bytes([checksum(body)])


@dataclass
class Frame:
    header: int
    app: int
    opcode: int
    payload: bytes
    raw: bytes

    @property
    def is_ack(self) -> bool:
        return self.header == 0xCC

    def describe(self) -> str:
        from .opcodes import OPCODE_NAMES as FULL
        name = OPCODE_NAMES.get(self.opcode) or FULL.get(self.opcode, "unknown")
        return f"{self.raw.hex(' ').upper()}  [op {self.opcode:02X} {name}, data: {self.payload.hex(' ').upper() or '-'}]"


class FrameParser:
    """Reassembles frames from BLE notifications, which may arrive split or merged."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        frames: list[Frame] = []
        while True:
            # Skip garbage until a plausible header.
            while len(self._buf) >= 2 and not (
                self._buf[0] in REPLY_HEADERS + (HOST,) and self._buf[1] in APP_CODES
            ):
                del self._buf[0]
            if len(self._buf) < 6:
                return frames
            length = (self._buf[3] << 8) | self._buf[4]
            total = 5 + length + 1
            if len(self._buf) < total:
                return frames
            raw = bytes(self._buf[:total])
            if checksum(raw[:-1]) != raw[-1]:
                del self._buf[0]
                continue
            del self._buf[:total]
            frames.append(Frame(raw[0], raw[1], raw[2], raw[5:-1], raw))


def parse_hex(text: str) -> bytes:
    return bytes.fromhex(text.replace(":", " ").replace(",", " "))
