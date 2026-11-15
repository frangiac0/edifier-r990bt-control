"""Plays a quiet, very low tone through the default Windows output so that the
speaker never mutes its amplifier during quiet passages.

The speaker mutes when the audio stream stops or the signal drops below a very
low threshold. A 25 Hz tone at -40..-60 dBFS keeps both from happening and is
practically inaudible. Only audio played by this PC is affected: it does not
help a device connected to the speaker's RCA inputs.
"""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

LEVELS_DB = (-60, -50, -40)
DEFAULT_LEVEL_DB = -50
FREQ = 25
RATE = 48000
SECONDS = 4  # whole number of 25 Hz cycles, so the loop is seamless

try:
    import winsound
except ImportError:  # not on Windows
    winsound = None


def available() -> bool:
    return winsound is not None


def _tone_file(level_db: int) -> Path:
    path = Path(tempfile.gettempdir()) / f"edifier-keepalive-{FREQ}hz-{abs(level_db)}db.wav"
    if not path.exists():
        amp = 32767 * 10 ** (level_db / 20)
        data = b"".join(
            struct.pack("<h", round(amp * math.sin(2 * math.pi * FREQ * i / RATE))) for i in range(RATE * SECONDS)
        )
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(data)
    return path


class KeepAlive:
    def __init__(self) -> None:
        self.enabled = False
        self.level_db = DEFAULT_LEVEL_DB

    def set(self, enabled: bool, level_db: int | None = None) -> None:
        if level_db is not None and level_db in LEVELS_DB:
            self.level_db = level_db
        self.enabled = enabled and available()
        self._apply()

    def stop(self) -> None:
        self.enabled = False
        self._apply()

    def _apply(self) -> None:
        if winsound is None:
            return
        if self.enabled:
            flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP | winsound.SND_NODEFAULT
            winsound.PlaySound(str(_tone_file(self.level_db)), flags)
        else:
            winsound.PlaySound(None, 0)
