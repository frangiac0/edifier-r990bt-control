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
        "eq_music": "Music",
        "eq_movie": "Movie",
        "eq_game": "Game",
        "pair": "Pair new device",
        "pair_confirm": "Disconnect the current Bluetooth audio device and put the speaker in pairing mode?\n\nThen connect the new device to \"EDIFIER R990BT\". The app will reconnect to the speaker in a minute or two.",
        "pairing_status": "Pairing mode: connect the new device to \"EDIFIER R990BT\". The app will reconnect shortly.",
        "settings": "Settings...",
        "settings_title": "Speaker settings",
        "speaker_name": "Speaker name",
        "save": "Save",
        "name_hint": "Up to 30 characters. Phones and PCs may keep showing the old name until they reconnect or pair again.",
        "name_saved": "Name changed.",
        "name_failed": "The speaker did not accept the name.",
        "name_too_long": "The name must be 1 to 30 characters (accents count double).",
        "prompt_tone": "Prompt tone when Bluetooth connects",
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
        "autostart": "Start with Windows (in the tray)",
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
        "eq_music": "Música",
        "eq_movie": "Película",
        "eq_game": "Juegos",
        "pair": "Emparejar dispositivo",
        "pair_confirm": "¿Desconectar el dispositivo de audio actual y poner el parlante en modo emparejamiento?\n\nDespués conectá el nuevo dispositivo a \"EDIFIER R990BT\". La app se reconecta al parlante en uno o dos minutos.",
        "pairing_status": "Modo emparejamiento: conectá el nuevo dispositivo a \"EDIFIER R990BT\". La app se reconecta en breve.",
        "settings": "Ajustes...",
        "settings_title": "Ajustes del parlante",
        "speaker_name": "Nombre del parlante",
        "save": "Guardar",
        "name_hint": "Hasta 30 caracteres. Los celulares y la PC pueden seguir mostrando el nombre anterior hasta que se reconecten o se vuelvan a emparejar.",
        "name_saved": "Nombre cambiado.",
        "name_failed": "El parlante no aceptó el nombre.",
        "name_too_long": "El nombre debe tener entre 1 y 30 caracteres (los acentos cuentan doble).",
        "prompt_tone": "Tono de aviso al conectar el Bluetooth",
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
        "autostart": "Iniciar con Windows (en la bandeja)",
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
