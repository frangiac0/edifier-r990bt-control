"""Check GitHub releases for a newer version and replace the running exe.

The latest release must be readable without a token, so the repository (or
the one named in RELEASES_REPO) has to be public.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

RELEASES_REPO = "frangiac0/edifier-r990bt-control"
ASSET_NAME = "EdifierR990BT.exe"
UPDATED_FLAG = "--updated"
_TIMEOUT = 15


@dataclass
class Release:
    version: str
    page_url: str
    asset_url: str | None


class UpdateError(Exception):
    pass


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def _request(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "edifier-r990bt-control-updater",
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=_TIMEOUT)


def check() -> Release | None:
    """Return the latest release if it is newer than this one, else None.
    Raises UpdateError if the releases can't be read."""
    url = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
    try:
        with _request(url) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise UpdateError("not_public" if e.code == 404 else f"HTTP {e.code}") from e
    except (OSError, ValueError) as e:
        raise UpdateError(str(e)) from e
    tag = data.get("tag_name") or ""
    if not tag or _parse(tag) <= _parse(__version__):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    return Release(
        version=tag.lstrip("v"),
        page_url=data.get("html_url") or f"https://github.com/{RELEASES_REPO}/releases/latest",
        asset_url=asset.get("browser_download_url") if asset else None,
    )


def can_self_update() -> bool:
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _old_path(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".old.exe")


def install(release: Release) -> None:
    """Download the new exe next to the running one and swap them. Windows
    allows renaming a running exe, so no helper script is needed. The caller
    must then call restart() and quit."""
    if not (can_self_update() and release.asset_url):
        raise UpdateError("manual")
    exe = Path(sys.executable)
    new = exe.with_name(exe.stem + ".new.exe")
    try:
        with _request(release.asset_url) as resp, open(new, "wb") as f:
            while chunk := resp.read(1 << 16):
                f.write(chunk)
        if new.stat().st_size < 1_000_000:  # sanity check: the real exe is tens of MB
            raise UpdateError("download too small")
        old = _old_path(exe)
        old.unlink(missing_ok=True)
        exe.rename(old)
        try:
            new.rename(exe)
        except OSError:
            old.rename(exe)
            raise
    except OSError as e:
        new.unlink(missing_ok=True)
        raise UpdateError(str(e)) from e


def restart() -> None:
    args = [sys.executable, UPDATED_FLAG]
    subprocess.Popen(args, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def cleanup() -> None:
    """Remove the previous exe left by an update."""
    if can_self_update():
        try:
            _old_path(Path(sys.executable)).unlink(missing_ok=True)
        except OSError:
            pass


def open_page(url: str) -> None:
    import webbrowser

    webbrowser.open(url)
