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
        "power_off": "Turn off",
        "power_off_confirm": "Turn the speaker off?\n\nIt can only be turned back on with the knob on the speaker.",
        "powered_off": "Speaker off. Turn it on with the knob; the app will reconnect.",
        "keepalive": "Prevent auto-mute",
        "keepalive_hint": "Plays an inaudible 25 Hz tone from this PC so the speaker doesn't mute in quiet scenes. Only works for audio coming from this PC.",
        "level": "Level",
        "phone": "PHONE REMOTE",
        "phone_enable": "Allow control from a phone on this Wi-Fi",
        "show_qr": "Show QR",
        "qr_title": "Scan with your phone",
        "web_forbidden": "Open the link shown in the Edifier R990BT app on your PC.",
        "web_offline": "Can't reach the PC. Is the app running?",
        "web_error": "Could not start the phone remote: {error}",
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
        "power_off": "Apagar",
        "power_off_confirm": "¿Apagar el parlante?\n\nSolo se puede volver a prender con la perilla del parlante.",
        "powered_off": "Parlante apagado. Prendelo con la perilla; la app se reconecta sola.",
        "keepalive": "Evitar enmudecimiento",
        "keepalive_hint": "Reproduce desde esta PC un tono de 25 Hz inaudible para que el parlante no se enmudezca en escenas silenciosas. Solo sirve para el audio que sale de esta PC.",
        "level": "Nivel",
        "phone": "CONTROL DESDE EL CELULAR",
        "phone_enable": "Permitir controlarlo desde un celular en este Wi-Fi",
        "show_qr": "Ver QR",
        "qr_title": "Escaneá con el celular",
        "web_forbidden": "Abrí el enlace que muestra la app Edifier R990BT en la PC.",
        "web_offline": "No se puede conectar con la PC. ¿Está abierta la app?",
        "web_error": "No se pudo iniciar el control desde el celular: {error}",
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
