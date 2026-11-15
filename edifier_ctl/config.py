"""Configuracion compartida por la app y la herramienta de diagnostico."""

from __future__ import annotations

import json
import os
from pathlib import Path


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "edifier-r990bt-control" / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(data: dict) -> None:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def saved_address() -> str | None:
    return load_config().get("address")


def remember_address(address: str) -> None:
    data = load_config()
    if data.get("address") != address:
        data["address"] = address
        save_config(data)


def forget_address() -> None:
    data = load_config()
    if data.pop("address", None) is not None:
        save_config(data)
