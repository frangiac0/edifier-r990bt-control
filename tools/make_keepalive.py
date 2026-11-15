"""Generate low-level, low-frequency test tones to keep the speaker's
auto-mute (noise gate) open during quiet passages.

Usage: python tools/make_keepalive.py [output_dir]
"""

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 48000
SECONDS = 60  # 25 Hz fits an exact number of cycles, so the file loops without a click
FREQ = 25
LEVELS_DB = (-40, -50, -60)


def write_tone(path: Path, level_db: float) -> None:
    amp = 32767 * 10 ** (level_db / 20)
    frames = bytearray()
    for i in range(RATE * SECONDS):
        frames += struct.pack("<h", round(amp * math.sin(2 * math.pi * FREQ * i / RATE)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for level in LEVELS_DB:
        path = out / f"keepalive_{FREQ}hz_{abs(level)}db.wav"
        write_tone(path, level)
        print(path)
