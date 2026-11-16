"""Capture README screenshots of the app on Windows with a simulated speaker.

Run from the repository root:  python tools/screenshots.py [output_dir]
Used by the build workflow when started manually.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp()  # don't touch the real config
os.environ.setdefault("EDIFIER_LANG", "en")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ctypes.windll.shcore.SetProcessDpiAwareness(2)

from PIL import ImageGrab  # noqa: E402

from edifier_ctl import config, gui  # noqa: E402
from edifier_ctl.controller import State  # noqa: E402
from edifier_ctl.i18n import t  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
config.set_values(tray_icon=True)  # the update check starts after 10 s, past the capture


class FakeController:
    def __init__(self, on_state) -> None:
        self._on_state = on_state
        self.state = State(
            status=t("connected", name="EDIFIER R990BT"), connected=True, name="EDIFIER R990BT",
            source=1, volume=9, eq=0, prompt_tone=True,
        )

    def start(self) -> None:
        self._on_state(self.state)

    def stop(self) -> None:
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


gui.Controller = FakeController


def window_rect(widget) -> tuple[int, int, int, int]:
    hwnd = int(widget.wm_frame(), 16)
    rect = wt.RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wt.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    # Drop the 1 px border, which can show whatever is behind the window.
    return rect.left + 1, rect.top + 1, rect.right - 1, rect.bottom - 1


def grab(widget, name: str) -> None:
    widget.update()
    OUT.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=window_rect(widget), all_screens=True).save(OUT / name)
    print("saved", OUT / name)


app = gui.App()
root = app.root
root.geometry("+40+40")
root.attributes("-topmost", True)


def step1() -> None:
    grab(root, "main-window.png")
    app._show_settings()
    win = app._settings_window
    # Same height as the main window, so both images line up in the README.
    win.update()
    win.geometry(f"{win.winfo_width()}x{root.winfo_height()}+520+40")
    win.attributes("-topmost", True)
    root.after(1500, lambda: step2(win))


def step2(win) -> None:
    grab(win, "settings.png")
    app._quit()


root.after(2500, step1)
app.run()
