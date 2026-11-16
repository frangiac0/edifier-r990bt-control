"""Settings shared by the app and the diagnostic tool."""

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


def get(key: str, default=None):
    return load_config().get(key, default)


def set_values(**values) -> None:
    data = load_config()
    data.update(values)
    save_config(data)


# --- Custom EQ profiles -------------------------------------------------------
# Stored as {name: [6 gains]}. Built-in defaults are merged in when reading, so
# new app versions can add profiles without overwriting the user's own.

def eq_profiles() -> dict:
    """All EQ profiles: built-in defaults plus the user's saved ones."""
    from . import r990bt

    profiles = {name: list(gains) for name, gains in r990bt.DEFAULT_EQ_PROFILES.items()}
    saved = load_config().get("eq_profiles", {})
    if isinstance(saved, dict):
        for name, gains in saved.items():
            profiles[str(name)] = list(r990bt.clamp_gains(gains))
    return profiles


def save_eq_profile(name: str, gains) -> None:
    from . import r990bt

    data = load_config()
    profiles = dict(data.get("eq_profiles", {})) if isinstance(data.get("eq_profiles"), dict) else {}
    profiles[name] = list(r990bt.clamp_gains(gains))
    data["eq_profiles"] = profiles
    save_config(data)


def delete_eq_profile(name: str) -> None:
    data = load_config()
    profiles = data.get("eq_profiles")
    if isinstance(profiles, dict) and name in profiles:
        del profiles[name]
        save_config(data)
