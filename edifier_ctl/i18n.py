"""User-interface strings. English by default, Spanish when Windows (or the
EDIFIER_LANG environment variable) says so."""

from __future__ import annotations

import locale
import os
import sys

STRINGS = {
    "en": {
        "input": "INPUT",
        "volume": "VOLUME",
        "eq": "EQUALIZER",
        "show_window": "Show window",
        "quit": "Quit",
        "disconnected": "disconnected",
        "searching": "Searching for speaker...",
        "connecting": "Connecting...",
        "connected": "Connected to {name}",
        "not_found": "Speaker not found. Play something over Bluetooth, or close ConneX on your phone.",
        "retrying": "No connection ({error}). Retrying...",
    },
    "es": {
        "input": "ENTRADA",
        "volume": "VOLUMEN",
        "eq": "ECUALIZADOR",
        "show_window": "Mostrar ventana",
        "quit": "Salir",
        "disconnected": "desconectado",
        "searching": "Buscando parlante...",
        "connecting": "Conectando...",
        "connected": "Conectado a {name}",
        "not_found": "No se encontró el parlante. Poné música por Bluetooth o cerrá ConneX en el celular.",
        "retrying": "Sin conexión ({error}). Reintentando...",
    },
}


def _detect() -> str:
    forced = os.environ.get("EDIFIER_LANG", "").lower()[:2]
    if forced in STRINGS:
        return forced
    if sys.platform == "win32":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if lang_id & 0x3FF == 0x0A:  # LANG_SPANISH, any region
                return "es"
            return "en"
        except Exception:
            pass
    code = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    return "es" if code.startswith(("es", "spanish")) else "en"


LANG = _detect()


def t(key: str, **kwargs) -> str:
    text = STRINGS[LANG].get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text
