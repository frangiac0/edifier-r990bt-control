"""Start with Windows (per user, no admin rights) and single-instance handling.

Autostart uses the value EdifierR990BT under
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. The registry is the
source of truth, so turning the entry off in Task Manager > Startup apps is
reflected in the app's checkbox.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE_NAME = "EdifierR990BT"
MINIMIZED_FLAG = "--minimized"

_MUTEX_NAME = "Local\\EdifierR990BT.Instance"
_SHOW_EVENT_NAME = "Local\\EdifierR990BT.Show"

try:
    import winreg
except ImportError:  # not Windows
    winreg = None


def available() -> bool:
    return winreg is not None


def command() -> str:
    """Command line that starts this app hidden in the tray."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {MINIMIZED_FLAG}'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = Path(__file__).resolve().parent.parent / "Edifier R990BT.pyw"
    return f'"{exe}" "{script}" {MINIMIZED_FLAG}'


def _registered() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except OSError:
        return None


def _disabled_in_task_manager() -> bool:
    # Task Manager stores 12 bytes; an odd first byte (03) means disabled.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value) and value[0] % 2 == 1
    except OSError:
        return False


def is_enabled() -> bool:
    if winreg is None:
        return False
    return _registered() is not None and not _disabled_in_task_manager()


def set_enabled(enabled: bool) -> bool:
    """Create or remove the Run entry. Returns the resulting state."""
    if winreg is None:
        return False
    try:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
    except OSError:
        return is_enabled()
    # Clear a "disabled" mark left by Task Manager, so the checkbox wins.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
    return is_enabled()


def refresh() -> None:
    """If enabled, point the entry at the current executable (e.g. after the
    exe was moved or replaced by a download in another folder)."""
    if winreg is None:
        return
    current = _registered()
    if current is not None and current != command() and not _disabled_in_task_manager():
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        except OSError:
            pass


# --- Single instance ---------------------------------------------------------
# Only one process can hold the BLE connection to the speaker. A second launch
# (e.g. double-clicking the exe while the autostarted copy sits in the tray)
# signals the running one to show its window and exits.

_handles: list = []


def acquire_single_instance(on_show, wait_s: float = 0) -> bool:
    """Return True if this is the first instance. Then `on_show` is called
    from a background thread whenever another launch asks to be shown.
    Return False if another instance was already running (it was signalled).
    With `wait_s`, first wait that long for a running instance to exit
    (used right after an update, while the old copy is closing)."""
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateEventW.restype = wintypes.HANDLE
    k32.OpenEventW.restype = wintypes.HANDLE
    ERROR_ALREADY_EXISTS = 183
    EVENT_MODIFY_STATE = 0x0002

    import time

    deadline = time.monotonic() + wait_s
    while True:
        mutex = k32.CreateMutexW(None, False, _MUTEX_NAME)
        if not (mutex and ctypes.get_last_error() == ERROR_ALREADY_EXISTS) or time.monotonic() >= deadline:
            break
        k32.CloseHandle(mutex)
        time.sleep(0.25)
    if mutex and ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        event = k32.OpenEventW(EVENT_MODIFY_STATE, False, _SHOW_EVENT_NAME)
        if event:
            k32.SetEvent(event)
            k32.CloseHandle(event)
        k32.CloseHandle(mutex)
        return False
    event = k32.CreateEventW(None, False, False, _SHOW_EVENT_NAME)  # auto-reset
    _handles.extend(h for h in (mutex, event) if h)
    if event:
        def wait() -> None:
            while True:
                if k32.WaitForSingleObject(event, 0xFFFFFFFF) == 0:
                    on_show()
                else:
                    return

        threading.Thread(target=wait, name="show-event", daemon=True).start()
    return True
