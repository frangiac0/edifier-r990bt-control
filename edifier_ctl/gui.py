"""Window and tray icon to control the Edifier R990BT."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from dataclasses import asdict

from . import __version__, autostart, config, keepalive, r990bt, updater, web
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

TIMER_MINUTES = (15, 30, 45, 60, 90, 120, 180)


def timer_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h" + (f" {m} min" if m else "")


def load_scenes() -> list[dict]:
    scenes = []
    for s in config.get("scenes", []) or []:
        try:
            source, eq = int(s["source"]), int(s["eq"])
        except (KeyError, TypeError, ValueError):
            continue
        if source in r990bt.SOURCES and eq in r990bt.EQ_PRESETS:
            scenes.append({"name": str(s.get("name") or "?")[:24], "source": source, "eq": eq})
    return scenes


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


def open_connect_flyout() -> None:
    """Press Win+K, which opens the Windows panel to connect wireless audio devices."""
    import ctypes

    user32 = ctypes.windll.user32
    VK_LWIN, VK_K, KEYUP = 0x5B, 0x4B, 0x0002
    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(VK_K, 0, 0, 0)
    user32.keybd_event(VK_K, 0, KEYUP, 0)
    user32.keybd_event(VK_LWIN, 0, KEYUP, 0)


def render_notes(text: tk.Text, notes: list[tuple[str, str]]) -> None:
    """Show GitHub release notes (Markdown) in a read-only Text widget."""
    import re

    text.tag_configure("version", font=("Segoe UI Semibold", 12), spacing1=6, spacing3=4)
    text.tag_configure("heading", font=("Segoe UI Semibold", 10), spacing1=8, spacing3=2)
    text.tag_configure("bullet", lmargin1=6, lmargin2=20, spacing1=2)
    text.tag_configure("bold", font=("Segoe UI Semibold", 10))
    text.tag_configure("code", font=("Consolas", 9), background="#eef0f3")

    def inline(line: str, base: tuple) -> None:
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)  # links: keep the text
        for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", line):
            if part.startswith("**") and part.endswith("**"):
                text.insert("end", part[2:-2], base + ("bold",))
            elif part.startswith("`") and part.endswith("`"):
                text.insert("end", part[1:-1], base + ("code",))
            else:
                text.insert("end", re.sub(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)", r"\1", part), base)

    if not notes:
        text.insert("end", t("update_no_notes"))
    for version, body in notes:
        text.insert("end", t("version", version=version) + "\n", ("version",))
        for raw in (body or "").replace("\r", "").split("\n"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                text.insert("end", line.lstrip("#").strip() + "\n", ("heading",))
            elif line[:2] in ("- ", "* "):
                text.insert("end", "•  ", ("bullet",))
                inline(line[2:], ("bullet",))
                text.insert("end", "\n", ("bullet",))
            else:
                inline(line, ())
                text.insert("end", "\n")
        text.insert("end", "\n")
    text.configure(state="disabled")


class App:
    def __init__(self, start_minimized: bool = False, events: queue.Queue | None = None) -> None:
        self.root = tk.Tk()
        self.root.title("Edifier R990BT")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._events: queue.Queue = events if events is not None else queue.Queue()
        self._state = State()
        self._dragging_volume = False
        self.tray = None
        self.keepalive = keepalive.KeepAlive()
        self.web: web.WebRemote | None = None
        self._qr_window = None

        self._build()
        self._set_window_icon()
        self.controller = Controller(on_state=lambda st: self._events.put(("state", st)))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._pump)
        self._setup_tray()
        self.root.bind("<Unmap>", self._on_unmap)
        if start_minimized:
            if self._to_tray("minimize_to_tray"):
                self.root.withdraw()
            else:
                self.root.iconify()
        self._restore_settings()
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

        title = ttk.Frame(frame)
        title.pack(fill="x")
        ttk.Label(title, text="Edifier R990BT", style="Title.TLabel").pack(side="left")
        if sys.platform == "win32":
            ttk.Button(title, text=t("connect_audio"), command=open_connect_flyout).pack(side="right")
        self.status_var = tk.StringVar(value=self._state.status)
        ttk.Label(frame, textvariable=self.status_var, style="Muted.TLabel", wraplength=300).pack(anchor="w", pady=(2, 14))

        # Shown only when a newer release is found.
        self.update_bar = ttk.Frame(frame)
        self.update_msg = tk.StringVar(value="")
        ttk.Label(self.update_bar, textvariable=self.update_msg, wraplength=200).pack(side="left")
        self.btn_update = ttk.Button(self.update_bar, text=t("update_now"), command=self._confirm_update)
        self.btn_update.pack(side="right")
        self._release = None

        self.input_label = ttk.Label(frame, text=t("input"), style="Section.TLabel")
        self.input_label.pack(anchor="w")
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
        for code, key in r990bt.EQ_PRESETS.items():
            b = ttk.Radiobutton(erow, text=t(key), value=code, variable=self.eq_var,
                                command=lambda c=code: self.controller.set_eq(c))
            b.pack(side="left", padx=(0, 12))
            self.eq_buttons.append(b)

        shead = ttk.Frame(frame)
        shead.pack(fill="x", pady=(16, 0))
        ttk.Label(shead, text=t("scenes"), style="Section.TLabel").pack(side="left")
        ttk.Button(shead, text=t("scenes_edit"), command=self._edit_scenes).pack(side="right")
        self.scenes_row = ttk.Frame(frame)
        self.scenes_row.pack(fill="x", pady=(6, 0))
        self.scene_buttons = []
        self._render_scenes()

        ttk.Separator(frame).pack(fill="x", pady=(18, 12))

        ka_row = ttk.Frame(frame)
        ka_row.pack(fill="x")
        self.ka_var = tk.BooleanVar(value=False)
        self.ka_check = ttk.Checkbutton(ka_row, text=t("keepalive"), variable=self.ka_var, command=self._on_keepalive_ui)
        self.ka_check.pack(side="left")
        self.ka_level_var = tk.StringVar(value=f"{keepalive.DEFAULT_LEVEL_DB} dB")
        self.ka_level = ttk.Combobox(
            ka_row, textvariable=self.ka_level_var, state="readonly", width=8,
            values=[f"{level} dB" for level in keepalive.LEVELS_DB],
        )
        self.ka_level.pack(side="right")
        self.ka_level.bind("<<ComboboxSelected>>", lambda e: self._on_keepalive_ui())
        ttk.Label(frame, text=t("keepalive_hint"), style="Muted.TLabel", wraplength=300).pack(anchor="w", pady=(4, 0))
        if not keepalive.available():
            self.ka_check.state(["disabled"])
            self.ka_level.state(["disabled"])

        ttk.Label(frame, text=t("phone"), style="Section.TLabel").pack(anchor="w", pady=(16, 0))
        self.web_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text=t("phone_enable"), variable=self.web_var, command=self._on_web_ui).pack(anchor="w", pady=(6, 0))
        wrow = ttk.Frame(frame)
        wrow.pack(fill="x", pady=(6, 0))
        self.web_url_var = tk.StringVar(value="")
        self.web_url = ttk.Entry(wrow, textvariable=self.web_url_var, state="readonly", font=("Segoe UI", 9))
        self.web_url.pack(side="left", fill="x", expand=True)
        self.btn_qr = ttk.Button(wrow, text=t("show_qr"), command=self._show_qr)
        self.btn_qr.pack(side="left", padx=(8, 0))
        self.btn_qr.state(["disabled"])

        trow = ttk.Frame(frame)
        trow.pack(fill="x", pady=(16, 0))
        ttk.Label(trow, text=t("timer")).pack(side="left")
        self.timer_var = tk.StringVar(value=t("timer_off"))
        self.timer_box = ttk.Combobox(
            trow, textvariable=self.timer_var, state="readonly", width=12,
            values=[t("timer_off")] + [timer_label(m) for m in TIMER_MINUTES],
        )
        self.timer_box.pack(side="left", padx=(8, 0))
        self.timer_box.bind("<<ComboboxSelected>>", lambda e: self._on_timer_ui())
        self.timer_info = tk.StringVar(value="")
        ttk.Label(trow, textvariable=self.timer_info, style="Muted.TLabel").pack(side="left", padx=(8, 0))
        self._timer_job = None
        self._timer_deadline = None

        brow = ttk.Frame(frame)
        brow.pack(fill="x", pady=(14, 0))
        self.btn_settings = ttk.Button(brow, text=t("settings"), command=self._show_settings)
        self.btn_settings.pack(side="left")
        self.btn_pair = ttk.Button(brow, text=t("pair"), command=self._confirm_pair)
        self.btn_pair.pack(side="left", padx=(8, 0))
        self.btn_power = ttk.Button(brow, text=t("power_off"), command=self._confirm_power_off)
        self.btn_power.pack(side="right")
        self._settings_window = None

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
        def scene_items():
            return [
                pystray.MenuItem(s["name"], (lambda sc: lambda: self._apply_scene(sc))(s))
                for s in self._scenes
            ] or [pystray.MenuItem(t("scenes_none"), None, enabled=False)]

        def timer_items():
            yield pystray.MenuItem(
                t("timer_off"), lambda: self._events.put(("timer", 0)),
                checked=lambda item: self._timer_deadline is None, radio=True,
            )
            for m in TIMER_MINUTES:
                yield pystray.MenuItem(
                    timer_label(m), (lambda mm: lambda: self._events.put(("timer", mm)))(m),
                    checked=(lambda mm: lambda item: self._timer_minutes == mm)(m), radio=True,
                )

        menu = pystray.Menu(
            *items,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("scenes_menu"), pystray.Menu(scene_items)),
            pystray.MenuItem(t("timer"), pystray.Menu(timer_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("pair"), lambda: self._events.put(("pair", None))),
            pystray.MenuItem(t("show_window"), lambda: self._events.put(("show", None)), default=True),
            pystray.MenuItem(t("quit"), lambda: self._events.put(("quit", None))),
        )
        self.tray = pystray.Icon("edifier-r990bt", make_icon_image(), "Edifier R990BT", menu)
        shown = bool(config.get("tray_icon", True))
        self.tray.run_detached(setup=lambda icon: setattr(icon, "visible", shown))

    def _tray_visible(self) -> bool:
        return self.tray is not None and bool(config.get("tray_icon", True))

    def _to_tray(self, key: str) -> bool:
        """Whether minimizing/closing (by config key) should hide the window in the tray."""
        return self._tray_visible() and bool(config.get(key, False))

    def _on_unmap(self, event) -> None:
        if event.widget is self.root and self.root.state() == "iconic" and self._to_tray("minimize_to_tray"):
            self.root.after_idle(self.root.withdraw)

    # --- Events ---

    def _pump(self) -> None:
        try:
            while True:
                kind, data = self._events.get_nowait()
                if kind == "state":
                    self._apply_state(data)
                elif kind == "show":
                    self.root.deiconify()
                    self.root.state("normal")
                    self.root.lift()
                    self.root.focus_force()
                elif kind == "pair":
                    self.root.deiconify()
                    self.root.lift()
                    self._confirm_pair()
                elif kind == "name_result":
                    win = self._settings_window
                    if win is not None and win.winfo_exists():
                        win._name_msg.set(t("name_saved") if data else t("name_failed"))
                        win._save_btn.state(["!disabled"])
                elif kind == "keepalive":
                    enabled, level = data
                    self._set_keepalive(enabled, level)
                elif kind == "timer":
                    self._set_timer(data)
                elif kind == "update_checked":
                    self._on_update_checked(*data)
                elif kind == "update_installed":
                    self._on_update_installed(data)
                elif kind == "quit":
                    self._quit()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _apply_state(self, st: State) -> None:
        self._state = st
        self._refresh_settings_window(st)
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
        for w in (self.btn_down, self.btn_up, self.volume_scale, self.btn_power, self.btn_pair, *self.eq_buttons, *self.scene_buttons):
            w.state(["!disabled"] if enabled else ["disabled"])

    # --- Settings, keep-alive and phone remote ---

    # --- Scenes ---

    def _render_scenes(self) -> None:
        self._scenes = load_scenes()
        for w in self.scenes_row.winfo_children():
            w.destroy()
        self.scene_buttons = []
        if not self._scenes:
            ttk.Label(self.scenes_row, text=t("scenes_empty"), style="Muted.TLabel", wraplength=300).pack(anchor="w")
            return
        for i, scene in enumerate(self._scenes):
            b = ttk.Button(self.scenes_row, text=scene["name"], command=lambda s=scene: self._apply_scene(s))
            b.grid(row=i // 3, column=i % 3, sticky="ew", padx=(0 if i % 3 == 0 else 4, 0), pady=(0, 4))
            self.scene_buttons.append(b)
        for c in range(3):
            self.scenes_row.columnconfigure(c, weight=1, uniform="scene")
        if not self._state.connected:
            for b in self.scene_buttons:
                b.state(["disabled"])
        if self.tray is not None:
            self.tray.update_menu()

    def _apply_scene(self, scene: dict) -> None:
        self.controller.set_source(scene["source"])
        self.controller.set_eq(scene["eq"])

    def _edit_scenes(self) -> None:
        win = getattr(self, "_scenes_window", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = tk.Toplevel(self.root)
        win.title(t("scenes_title"))
        win.configure(bg=BG)
        win.resizable(False, False)
        self._scenes_window = win
        body = ttk.Frame(win, padding=(20, 16, 20, 18))
        body.pack(fill="both", expand=True)

        scenes = load_scenes()
        sources = list(r990bt.SOURCES.items())
        presets = [(code, t(key)) for code, key in r990bt.EQ_PRESETS.items()]

        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        listbox = tk.Listbox(left, height=8, width=18, exportselection=False, activestyle="none",
                             font=("Segoe UI", 10), relief="solid", bd=1, highlightthickness=0)
        listbox.pack(fill="y", expand=True)
        lbtn = ttk.Frame(left)
        lbtn.pack(fill="x", pady=(6, 0))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", padx=(16, 0))
        name_var = tk.StringVar()
        source_var = tk.StringVar()
        eq_var = tk.StringVar()
        ttk.Label(right, text=t("scene_name")).pack(anchor="w")
        name_entry = ttk.Entry(right, textvariable=name_var, width=22)
        name_entry.pack(anchor="w", pady=(4, 10))
        ttk.Label(right, text=t("input").capitalize()).pack(anchor="w")
        source_box = ttk.Combobox(right, textvariable=source_var, state="readonly", width=20,
                                  values=[label for _, label in sources])
        source_box.pack(anchor="w", pady=(4, 10))
        ttk.Label(right, text=t("eq").capitalize()).pack(anchor="w")
        eq_box = ttk.Combobox(right, textvariable=eq_var, state="readonly", width=20,
                              values=[label for _, label in presets])
        eq_box.pack(anchor="w", pady=(4, 0))
        fields = (name_entry, source_box, eq_box)

        loading = False

        def save() -> None:
            config.set_values(scenes=scenes)
            self._render_scenes()

        def refresh_list(select: int | None) -> None:
            listbox.delete(0, "end")
            for s in scenes:
                listbox.insert("end", s["name"])
            if select is not None and scenes:
                select = min(select, len(scenes) - 1)
                listbox.selection_set(select)
                listbox.see(select)
            load_selected()

        def selected() -> int | None:
            sel = listbox.curselection()
            return sel[0] if sel else None

        def load_selected(_event=None) -> None:
            nonlocal loading
            i = selected()
            loading = True
            if i is None:
                name_var.set("")
                source_var.set("")
                eq_var.set("")
                for w in fields:
                    w.state(["disabled"])
            else:
                s = scenes[i]
                for w in fields:
                    w.state(["!disabled"])
                source_box.state(["readonly"])
                eq_box.state(["readonly"])
                name_var.set(s["name"])
                source_var.set(r990bt.SOURCES[s["source"]])
                eq_var.set(dict(presets)[s["eq"]])
            loading = False
            del_btn.state(["disabled"] if i is None else ["!disabled"])

        def on_change(*_args) -> None:
            i = selected()
            if loading or i is None:
                return
            s = scenes[i]
            s["name"] = name_var.get().strip()[:24] or "?"
            s["source"] = next((c for c, label in sources if label == source_var.get()), s["source"])
            s["eq"] = next((c for c, label in presets if label == eq_var.get()), s["eq"])
            listbox.delete(i)
            listbox.insert(i, s["name"])
            listbox.selection_set(i)
            save()

        def add() -> None:
            st = self._state
            scenes.append({
                "name": t("scene_default_name", n=len(scenes) + 1),
                "source": st.source if st.source in r990bt.SOURCES else sources[0][0],
                "eq": st.eq if st.eq in r990bt.EQ_PRESETS else presets[0][0],
            })
            save()
            refresh_list(len(scenes) - 1)
            name_entry.focus_set()
            name_entry.select_range(0, "end")

        def delete() -> None:
            i = selected()
            if i is None:
                return
            del scenes[i]
            save()
            refresh_list(i)

        ttk.Button(lbtn, text=t("scene_add"), command=add).pack(side="left")
        del_btn = ttk.Button(lbtn, text=t("scene_delete"), command=delete)
        del_btn.pack(side="right")
        ttk.Label(right, text=t("scenes_hint"), style="Muted.TLabel", wraplength=180).pack(anchor="w", pady=(14, 0))

        listbox.bind("<<ListboxSelect>>", load_selected)
        name_var.trace_add("write", on_change)
        source_box.bind("<<ComboboxSelected>>", on_change)
        eq_box.bind("<<ComboboxSelected>>", on_change)
        refresh_list(0)

    # --- Sleep timer ---

    @property
    def _timer_minutes(self) -> int | None:
        return getattr(self, "_timer_set_minutes", None) if self._timer_deadline else None

    def _on_timer_ui(self) -> None:
        label = self.timer_var.get()
        minutes = next((m for m in TIMER_MINUTES if timer_label(m) == label), 0)
        self._set_timer(minutes)

    def _set_timer(self, minutes: int) -> None:
        if self._timer_job is not None:
            self.root.after_cancel(self._timer_job)
            self._timer_job = None
        if minutes:
            self._timer_deadline = time.time() + minutes * 60
            self._timer_set_minutes = minutes
            self.timer_var.set(timer_label(minutes))
            self._timer_tick()
        else:
            self._timer_deadline = None
            self.timer_var.set(t("timer_off"))
            self.timer_info.set("")
        if self.tray is not None:
            self.tray.update_menu()

    def _timer_tick(self) -> None:
        remaining = self._timer_deadline - time.time()
        if remaining <= 0:
            self._timer_job = None
            self._set_timer(0)
            self.controller.power_off()
            return
        at = time.strftime("%H:%M", time.localtime(self._timer_deadline))
        self.timer_info.set(t("timer_at", time=at))
        self._timer_job = self.root.after(int(min(remaining, 20) * 1000), self._timer_tick)

    # --- Updates ---

    def _auto_check_updates(self) -> None:
        if config.get("auto_update", True):
            self._check_updates(manual=False)
        self.root.after(24 * 3600 * 1000, self._auto_check_updates)

    def _check_updates(self, manual: bool) -> None:
        def work() -> None:
            try:
                result = updater.check()
            except updater.UpdateError as e:
                result = e
            self._events.put(("update_checked", (result, manual)))

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _set_update_status(self, text: str) -> None:
        win = self._settings_window
        if win is not None and win.winfo_exists():
            win._update_status.set(text)
            win._update_btn.state(["!disabled"])

    def _on_update_checked(self, result, manual: bool) -> None:
        if isinstance(result, updater.UpdateError):
            msg = t("update_not_public") if str(result) == "not_public" else t("update_error", error=result)
            if manual:
                self._set_update_status(msg)
            return
        if result is None:
            if manual:
                self._set_update_status(t("update_none", version=__version__))
            return
        self._release = result
        text = t("update_available", version=result.version)
        self._set_update_status(text)
        self.update_msg.set(text)
        if not self.update_bar.winfo_ismapped():
            self.update_bar.pack(fill="x", pady=(0, 14), before=self.input_label)
        if self._tray_visible() and not self.root.winfo_viewable() and not manual:
            try:
                self.tray.notify(text, "Edifier R990BT")
            except Exception:
                pass

    def _confirm_update(self) -> None:
        release = self._release
        if release is None:
            return
        self._show_update_dialog(release)

    def _show_update_dialog(self, release) -> None:
        win = getattr(self, "_update_window", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = tk.Toplevel(self.root)
        self._update_window = win
        win.title(t("update_title"))
        win.configure(bg=BG)
        win.transient(self.root)
        body = ttk.Frame(win, padding=(20, 16, 20, 18))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=t("update_heading", version=release.version), style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=t("update_current", version=__version__), style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        box = ttk.Frame(body)
        box.pack(fill="both", expand=True)
        text = tk.Text(box, width=56, height=16, wrap="word", relief="solid", bd=1, highlightthickness=0,
                       font=("Segoe UI", 10), bg="white", fg=FG, padx=10, pady=8, cursor="arrow")
        scroll = ttk.Scrollbar(box, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        render_notes(text, release.notes)

        brow = ttk.Frame(body)
        brow.pack(fill="x", pady=(12, 0))
        ttk.Button(brow, text=t("update_later"), command=win.destroy).pack(side="right")
        can_install = updater.can_self_update() and release.asset_url and release.sha256

        def install() -> None:
            win.destroy()
            if can_install:
                self._install_update(release)
            else:
                updater.open_page(release.page_url)

        ttk.Button(brow, text=t("update_now") if can_install else t("update_download"),
                   command=install).pack(side="right", padx=(0, 8))
        ttk.Button(brow, text=t("update_github"), command=lambda: updater.open_page(release.page_url)).pack(side="left")

    def _install_update(self, release) -> None:
        self.btn_update.state(["disabled"])
        self.update_msg.set(t("update_downloading"))

        def work() -> None:
            try:
                updater.install(release)
                self._events.put(("update_installed", None))
            except updater.UpdateError as e:
                self._events.put(("update_installed", e))

        threading.Thread(target=work, name="update-install", daemon=True).start()

    def _on_update_installed(self, error) -> None:
        if error is None:
            self._quit(restart=True)
            return
        self.btn_update.state(["!disabled"])
        self.update_msg.set(t("update_available", version=self._release.version))
        if messagebox.askyesno("Edifier R990BT", t("update_failed", error=error), icon="warning", parent=self.root):
            updater.open_page(self._release.page_url)

    # --- Settings, keep-alive and phone remote ---

    def _restore_settings(self) -> None:
        autostart.refresh()
        self.root.after(10_000, self._auto_check_updates)
        level = config.get("keepalive_level", keepalive.DEFAULT_LEVEL_DB)
        self._set_keepalive(bool(config.get("keepalive", False)), level, save=False)
        if config.get("web_enabled", False):
            self.web_var.set(True)
            self._on_web_ui()

    def _on_keepalive_ui(self) -> None:
        level = int(self.ka_level_var.get().split()[0])
        self._set_keepalive(self.ka_var.get(), level)

    def _set_keepalive(self, enabled: bool, level: int | None, save: bool = True) -> None:
        self.keepalive.set(enabled, level)
        self.ka_var.set(self.keepalive.enabled)
        self.ka_level_var.set(f"{self.keepalive.level_db} dB")
        if save:
            config.set_values(keepalive=self.keepalive.enabled, keepalive_level=self.keepalive.level_db)

    def _web_state(self) -> dict:
        data = asdict(self._state)
        data.update(
            keepalive=self.keepalive.enabled,
            keepalive_level=self.keepalive.level_db,
            keepalive_available=keepalive.available(),
        )
        return data

    def _on_web_ui(self) -> None:
        if self.web_var.get():
            key = config.get("web_key") or web.new_key()
            port = int(config.get("web_port", web.DEFAULT_PORT))
            target = web.RemoteTarget(
                get_state=self._web_state,
                set_source=lambda src: self.controller.set_source(src),
                set_volume=lambda v: self.controller.set_volume(v),
                set_eq=lambda p: self.controller.set_eq(p),
                set_keepalive=lambda en, lvl: self._events.put(("keepalive", (en, lvl))),
                power_off=lambda: self.controller.power_off(),
                pair=lambda: self.controller.pair(),
            )
            self.web = web.WebRemote(target, key=key, port=port)
            try:
                self.web.start()
            except OSError as exc:
                self.web = None
                self.web_var.set(False)
                messagebox.showerror("Edifier R990BT", t("web_error", error=exc), parent=self.root)
                return
            config.set_values(web_enabled=True, web_key=key, web_port=port)
            self.web_url_var.set(self.web.url)
            self.btn_qr.state(["!disabled"])
        else:
            if self.web:
                self.web.stop()
                self.web = None
            config.set_values(web_enabled=False)
            self.web_url_var.set("")
            self.btn_qr.state(["disabled"])
            if self._qr_window is not None:
                self._qr_window.destroy()
                self._qr_window = None

    def _show_qr(self) -> None:
        if not self.web:
            return
        if self._qr_window is not None and self._qr_window.winfo_exists():
            self._qr_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title(t("qr_title"))
        win.configure(bg="white")
        win.resizable(False, False)
        url = self.web.url
        try:
            import qrcode
            from PIL import ImageTk

            img = qrcode.make(url, box_size=8, border=2).get_image()
            win._photo = ImageTk.PhotoImage(img)
            tk.Label(win, image=win._photo, bg="white").pack(padx=16, pady=(16, 8))
        except Exception:
            pass
        tk.Label(win, text=url, bg="white", fg=FG, font=("Segoe UI", 9)).pack(padx=16, pady=(0, 16))
        self._qr_window = win

    def _show_settings(self) -> None:
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title(t("settings_title"))
        win.configure(bg=BG)
        win.resizable(False, False)
        body = ttk.Frame(win, padding=(20, 16, 20, 18))
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=t("speaker_section"), style="Section.TLabel").pack(anchor="w")
        ttk.Label(body, text=t("speaker_name")).pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(6, 0))
        name_var = tk.StringVar(value=self._state.name or "")
        entry = ttk.Entry(row, textvariable=name_var, width=30)
        entry.pack(side="left", fill="x", expand=True)
        msg_var = tk.StringVar(value="")

        def done(ok: bool) -> None:
            self._events.put(("name_result", ok))

        def save() -> None:
            name = name_var.get().strip()
            if not name or len(name.encode("utf-8")) > 30:
                msg_var.set(t("name_too_long"))
                return
            save_btn.state(["disabled"])
            self.controller.set_name(name, on_done=done)

        save_btn = ttk.Button(row, text=t("save"), command=save)
        save_btn.pack(side="left", padx=(8, 0))
        ttk.Label(body, text=t("name_hint"), style="Muted.TLabel", wraplength=320).pack(anchor="w", pady=(4, 0))
        ttk.Label(body, textvariable=msg_var, style="Muted.TLabel", wraplength=320).pack(anchor="w", pady=(4, 0))

        tone_var = tk.BooleanVar(value=bool(self._state.prompt_tone))
        tone = ttk.Checkbutton(
            body, text=t("prompt_tone"), variable=tone_var,
            command=lambda: self.controller.set_prompt_tone(tone_var.get()),
        )
        tone.pack(anchor="w", pady=(12, 0))

        ttk.Separator(body).pack(fill="x", pady=(18, 12))
        ttk.Label(body, text=t("app_section"), style="Section.TLabel").pack(anchor="w")

        autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        autostart_check = ttk.Checkbutton(
            body, text=t("autostart"), variable=autostart_var,
            command=lambda: autostart_var.set(autostart.set_enabled(autostart_var.get())),
        )
        autostart_check.pack(anchor="w", pady=(8, 0))
        if not autostart.available():
            autostart_check.state(["disabled"])

        tray_var = tk.BooleanVar(value=self._tray_visible())
        min_var = tk.BooleanVar(value=bool(config.get("minimize_to_tray", False)))
        close_var = tk.BooleanVar(value=bool(config.get("close_to_tray", False)))

        def apply_tray() -> None:
            config.set_values(
                tray_icon=tray_var.get(), minimize_to_tray=min_var.get(), close_to_tray=close_var.get(),
            )
            if self.tray is not None:
                self.tray.visible = tray_var.get()
            sub = ["!disabled"] if tray_var.get() else ["disabled"]
            min_check.state(sub)
            close_check.state(sub)

        tray_check = ttk.Checkbutton(body, text=t("tray_icon"), variable=tray_var, command=apply_tray)
        tray_check.pack(anchor="w", pady=(6, 0))
        min_check = ttk.Checkbutton(body, text=t("minimize_to_tray"), variable=min_var, command=apply_tray)
        min_check.pack(anchor="w", padx=(22, 0), pady=(4, 0))
        close_check = ttk.Checkbutton(body, text=t("close_to_tray"), variable=close_var, command=apply_tray)
        close_check.pack(anchor="w", padx=(22, 0), pady=(4, 0))
        ttk.Label(body, text=t("app_hint"), style="Muted.TLabel", wraplength=320).pack(anchor="w", pady=(6, 0))

        auto_var = tk.BooleanVar(value=bool(config.get("auto_update", True)))
        ttk.Checkbutton(
            body, text=t("auto_update"), variable=auto_var,
            command=lambda: config.set_values(auto_update=auto_var.get()),
        ).pack(anchor="w", pady=(12, 0))
        urow = ttk.Frame(body)
        urow.pack(fill="x", pady=(6, 0))
        update_status = tk.StringVar(value=t("version", version=__version__))
        ttk.Label(urow, textvariable=update_status, style="Muted.TLabel", wraplength=200).pack(side="left")

        def check_now() -> None:
            update_btn.state(["disabled"])
            update_status.set(t("update_checking"))
            self._check_updates(manual=True)

        update_btn = ttk.Button(urow, text=t("update_check"), command=check_now)
        update_btn.pack(side="right")
        win._update_status = update_status
        win._update_btn = update_btn
        if self.tray is None:
            for w in (tray_check, min_check, close_check):
                w.state(["disabled"])
        elif not tray_var.get():
            min_check.state(["disabled"])
            close_check.state(["disabled"])

        win._name_msg = msg_var
        win._name_entry = entry
        win._save_btn = save_btn
        win._tone_var = tone_var
        win._tone = tone
        self._settings_window = win
        self._refresh_settings_window(self._state)

    def _refresh_settings_window(self, st: State) -> None:
        win = self._settings_window
        if win is None or not win.winfo_exists():
            return
        speaker = ["!disabled"] if st.connected else ["disabled"]
        win._name_entry.state(speaker)
        win._save_btn.state(speaker)
        if st.prompt_tone is not None:
            win._tone_var.set(st.prompt_tone)
        win._tone.state(speaker if st.prompt_tone is not None else ["disabled"])

    def _confirm_pair(self) -> None:
        if messagebox.askyesno("Edifier R990BT", t("pair_confirm"), parent=self.root):
            self.controller.pair()

    def _confirm_power_off(self) -> None:
        if messagebox.askyesno("Edifier R990BT", t("power_off_confirm"), icon="warning", parent=self.root):
            self.controller.power_off()

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
        if self._to_tray("close_to_tray"):
            self.root.withdraw()  # keep running in the tray
        else:
            self._quit()

    def _quit(self, restart: bool = False) -> None:
        if restart:
            # The new copy waits for this one to exit before taking over.
            updater.restart()
        self.keepalive.stop()
        if self.web:
            self.web.stop()
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

    import qrcode  # noqa: F401

    from . import web  # noqa: F401

    from . import autostart, updater  # noqa: F401

    autostart.command()
    if sys.platform == "win32":
        import winreg  # noqa: F401
        import winsound  # noqa: F401
        import bleak.backends.winrt.client  # noqa: F401
        import bleak.backends.winrt.scanner  # noqa: F401
    make_icon_image()
    if sys.platform == "win32" and pystray is None:
        return 2
    return 0


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if "--self-test-restart" in sys.argv:
        # Build check: start a copy the way an update does, then exit at once.
        out = sys.argv[sys.argv.index("--self-test-restart") + 1]
        updater.spawn([sys.executable, "--self-test-child", out])
        sys.exit(0)
    if "--self-test-child" in sys.argv:
        out = sys.argv[sys.argv.index("--self-test-child") + 1]
        time.sleep(3)  # let the parent exit and remove its temporary files
        root = tk.Tk()
        ttk.Style(root).theme_use("clam")
        root.destroy()
        with open(out, "w", encoding="utf-8") as f:
            f.write("ok")
        sys.exit(0)
    events: queue.Queue = queue.Queue()
    updater.cleanup()
    wait = 30 if updater.UPDATED_FLAG in sys.argv else 0
    if not autostart.acquire_single_instance(lambda: events.put(("show", None)), wait_s=wait):
        return  # the running copy shows its window
    App(start_minimized=autostart.MINIMIZED_FLAG in sys.argv, events=events).run()


if __name__ == "__main__":
    main()
