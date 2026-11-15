"""Generate gate_test.wav: a fixed sequence of tones at known levels and silences,
to find where the speaker's auto-mute kicks in and whether a keep-alive tone helps.

Timeline (also printed when run):
  0:00  reference tone, -20 dB, 5 s
  0:05  steady tone stepping down every 8 s: -30, -35, -40, -45, -50, -55, -60 dB
  1:01  silence, 20 s
  1:21  three short beeps at -30 dB, 1 s apart (is the first one cut?)
  1:24  silence, 20 s
  1:44  three short beeps at -45 dB, 1 s apart
  1:47  end

Usage: python tools/make_gate_test.py [output_dir]
"""

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 48000
FREQ = 440
FADE = 0.02  # seconds, avoids clicks


def tone(seconds: float, level_db: float) -> list[float]:
    n = int(RATE * seconds)
    amp = 10 ** (level_db / 20)
    f = int(RATE * FADE)
    out = []
    for i in range(n):
        env = min(1.0, i / f, (n - 1 - i) / f)
        out.append(amp * env * math.sin(2 * math.pi * FREQ * i / RATE))
    return out


def silence(seconds: float) -> list[float]:
    return [0.0] * int(RATE * seconds)


def beeps(level_db: float) -> list[float]:
    s = []
    for _ in range(3):
        s += tone(0.3, level_db) + silence(0.7)
    return s


def build() -> list[float]:
    s = tone(5, -20)
    for level in (-30, -35, -40, -45, -50, -55, -60):
        s += tone(8, level)
    s += silence(20) + beeps(-30) + silence(20) + beeps(-45)
    return s


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "gate_test.wav"
    samples = build()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", round(32767 * x)) for x in samples))
    print(path, f"{len(samples) / RATE:.0f} s")
