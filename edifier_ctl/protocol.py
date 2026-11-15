"""Formato de tramas del protocolo BLE de Edifier ConneX.

Basado en la documentacion comunitaria de otros modelos (M60, M90, MR5BT).
Para el R990BT el formato todavia no esta verificado.

    AA EC opcode len_hi len_lo payload... checksum   pedido del host
    BB EC opcode len_hi len_lo payload... checksum   respuesta del parlante
    CC EC ...                                        algunos ACK

checksum = byte bajo de la suma de todos los bytes anteriores.
"""

from __future__ import annotations

from dataclasses import dataclass

HOST = 0xAA
REPLY_HEADERS = (0xBB, 0xCC)
APP_CODES = (0xEC, 0xED)

# Opcodes conocidos en otros modelos de la familia.
OP_CAPABILITIES = 0xD8
OP_NAME = 0xC9
OP_FIRMWARE = 0xC6
OP_SOURCE_GET = 0x61
OP_SOURCE_SET = 0x62
OP_VOLUME_GET = 0x66
OP_VOLUME_SET = 0x67
OP_EQ_GET = 0xD5
OP_EQ_SET = 0xC4
OP_MEDIA = 0xC2
OP_A2DP_STATE = 0xC3

OPCODE_NAMES = {
    OP_CAPABILITIES: "capacidades",
    OP_NAME: "nombre",
    OP_FIRMWARE: "firmware",
    OP_SOURCE_GET: "entrada (consulta)",
    OP_SOURCE_SET: "entrada (cambio)",
    OP_VOLUME_GET: "volumen (consulta)",
    OP_VOLUME_SET: "volumen (cambio)",
    OP_EQ_GET: "ecualizador (consulta)",
    OP_EQ_SET: "ecualizador (cambio)",
    OP_MEDIA: "reproduccion",
    OP_A2DP_STATE: "estado del audio Bluetooth",
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
        name = OPCODE_NAMES.get(self.opcode, "desconocido")
        return f"{self.raw.hex(' ').upper()}  [op {self.opcode:02X} {name}, datos: {self.payload.hex(' ').upper() or '-'}]"


class FrameParser:
    """Rearma tramas a partir de notificaciones BLE que pueden llegar partidas o juntas."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        frames: list[Frame] = []
        while True:
            # Descartar basura hasta un encabezado plausible.
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
