"""Window and tray icon to control the Edifier R990BT."""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from tkinter import ttk

from . import r990bt
from .controller import Controller, State
from .i18n import t

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    Image = None

try:  # The tray icon is optional: without pystray the app still works.
    import pystray

    if Image is None:
        pystray = None
except Exception:  # library missing or no tray support
    pystray = None

ACCENT = "#1f6feb"
BG = "#f6f7f9"
FG = "#1d2129"
MUTED = "#6b7280"


def make_icon_image(size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rounded_rectangle((14 * s, 4 * s, 50 * s, 60 * s), radius=8 * s, fill=(29, 33, 41, 255))
    d.ellipse((22 * s, 30 * s, 42 * s, 50 * s), fill=(31, 111, 235, 255))
    d.ellipse((28 * s, 36 * s, 36 * s, 44 * s), fill=(29, 33, 41, 255))
    d.ellipse((28 * s, 12 * s, 36 * s, 20 * s), fill=(31, 111, 235, 255))
    return img


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Edifier R990BT")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._events: queue.Queue = queue.Queue()
        self._state = State()
        self._dragging_volume = False
        self.tray = None

        self._build()
        self._set_window_icon()
        self.controller = Controller(on_state=lambda st: self._events.put(("state", st)))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._pump)
        self._setup_tray()
        self.controller.start()

    # --- Window layout ---

    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 14))
        style.configure("Muted.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Section.TLabel", foreground=MUTED, font=("Segoe UI Semibold", 9))
        style.configure("TScale", background=BG)

        frame = ttk.Frame(self.root, padding=(20, 16, 20, 18))
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Edifier R990BT", style="Title.TLabel").pack(anchor="w")
        self.status_var = tk.StringVar(value=self._state.status)
        ttk.Label(frame, textvariable=self.status_var, style="Muted.TLabel", wraplength=300).pack(anchor="w", pady=(2, 14))

        ttk.Label(frame, text=t("input"), style="Section.TLabel").pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(6, 16))
        self.source_var = tk.IntVar(value=-1)
        self.source_buttons = []
        for code, label in r990bt.SOURCES.items():
            b = tk.Radiobutton(
                row, text=label, value=code, variable=self.source_var, indicatoron=False,
                command=lambda c=code: self.controller.set_source(c),
                width=10, pady=8, relief="flat", bd=0, font=("Segoe UI", 10),
                bg="#e5e7eb", fg=FG, activebackground="#d1d5db",
                selectcolor=ACCENT, cursor="hand2",
            )
            b.pack(side="left", expand=True, fill="x", padx=2)
            self.source_buttons.append(b)

        head = ttk.Frame(frame)
        head.pack(fill="x")
        ttk.Label(head, text=t("volume"), style="Section.TLabel").pack(side="left")
        self.volume_label = tk.StringVar(value="-")
        ttk.Label(head, textvariable=self.volume_label, style="Muted.TLabel").pack(side="right")
        vrow = ttk.Frame(frame)
        vrow.pack(fill="x", pady=(6, 16))
        self.btn_down = ttk.Button(vrow, text="-", width=3, command=lambda: self._step_volume(-1))
        self.btn_down.pack(side="left")
        self.volume_var = tk.DoubleVar(value=0)
        self.volume_scale = ttk.Scale(
            vrow, from_=0, to=r990bt.VOLUME_MAX, variable=self.volume_var, command=self._on_volume_drag
        )
        self.volume_scale.pack(side="left", fill="x", expand=True, padx=8)
        self.volume_scale.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging_volume", True))
        self.volume_scale.bind("<ButtonRelease-1>", self._on_volume_release)
        self.btn_up = ttk.Button(vrow, text="+", width=3, command=lambda: self._step_volume(1))
        self.btn_up.pack(side="left")

        ttk.Label(frame, text=t("eq"), style="Section.TLabel").pack(anchor="w")
        erow = ttk.Frame(frame)
        erow.pack(fill="x", pady=(6, 0))
        self.eq_var = tk.IntVar(value=-1)
        self.eq_buttons = []
        for code, label in r990bt.EQ_PRESETS.items():
            b = ttk.Radiobutton(erow, text=label, value=code, variable=self.eq_var,
                                command=lambda c=code: self.controller.set_eq(c))
            b.pack(side="left", padx=(0, 12))
            self.eq_buttons.append(b)

        self._set_enabled(False)

    def _set_window_icon(self) -> None:
        if Image is None:
            return
        try:
            from PIL import ImageTk

            self._icon_photo = ImageTk.PhotoImage(make_icon_image(64))
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # --- Tray ---

    def _setup_tray(self) -> None:
        if pystray is None:
            return
        items = [
            pystray.MenuItem(
                label, (lambda c: lambda icon, item: self.controller.set_source(c))(code),
                checked=(lambda c: lambda item: self._state.source == c)(code), radio=True,
            )
            for code, label in r990bt.SOURCES.items()
        ]
        menu = pystray.Menu(
            *items,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("show_window"), lambda: self._events.put(("show", None)), default=True),
            pystray.MenuItem(t("quit"), lambda: self._events.put(("quit", None))),
        )
        self.tray = pystray.Icon("edifier-r990bt", make_icon_image(), "Edifier R990BT", menu)
        self.tray.run_detached()

    # --- Events ---

    def _pump(self) -> None:
        try:
            while True:
                kind, data = self._events.get_nowait()
                if kind == "state":
                    self._apply_state(data)
                elif kind == "show":
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                elif kind == "quit":
                    self._quit()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _apply_state(self, st: State) -> None:
        self._state = st
        self.status_var.set(st.status)
        self._set_enabled(st.connected)
        self.source_var.set(st.source if st.source is not None else -1)
        self.eq_var.set(st.eq if st.eq is not None else -1)
        self.volume_scale.configure(to=st.volume_max)
        if st.volume is not None and not self._dragging_volume:
            self.volume_var.set(st.volume)
            self.volume_label.set(f"{st.volume} / {st.volume_max}")
        if self.tray is not None:
            name = r990bt.SOURCES.get(st.source, "-") if st.connected else t("disconnected")
            self.tray.title = f"Edifier R990BT: {name}"
            self.tray.update_menu()

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for b in self.source_buttons:
            b.configure(state=state)
        for w in (self.btn_down, self.btn_up, self.volume_scale, *self.eq_buttons):
            w.state(["!disabled"] if enabled else ["disabled"])

    def _on_volume_drag(self, value: str) -> None:
        self.volume_label.set(f"{round(float(value))} / {self._state.volume_max}")

    def _on_volume_release(self, _event) -> None:
        self._dragging_volume = False
        value = round(self.volume_var.get())
        self.volume_var.set(value)
        self.controller.set_volume(value)

    def _step_volume(self, delta: int) -> None:
        current = self._state.volume if self._state.volume is not None else round(self.volume_var.get())
        self.controller.set_volume(current + delta)

    def _on_close(self) -> None:
        if self.tray is not None:
            self.root.withdraw()  # keep running in the tray
        else:
            self._quit()

    def _quit(self) -> None:
        if self.tray is not None:
            self.tray.stop()
        self.controller.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def self_test() -> int:
    """Used by the build to check that the bundled exe can load its BLE and tray backends."""
    import bleak  # noqa: F401
    from bleak import BleakClient, BleakScanner  # noqa: F401

    if sys.platform == "win32":
        import bleak.backends.winrt.client  # noqa: F401
        import bleak.backends.winrt.scanner  # noqa: F401
    make_icon_image()
    if sys.platform == "win32" and pystray is None:
        return 2
    return 0


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    App().run()


if __name__ == "__main__":
    main()
