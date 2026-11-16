"""Check GitHub releases for a newer version and replace the running exe.

The latest release must be readable without a token, so the repository (or
the one named in RELEASES_REPO) has to be public.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

RELEASES_REPO = "frangiac0/edifier-r990bt-control"
PORTABLE_ASSET = "EdifierR990BT.exe"
SETUP_ASSET = "EdifierR990BT-Setup.exe"
UPDATED_FLAG = "--updated"
_TIMEOUT = 15


@dataclass
class Release:
    version: str
    page_url: str
    asset_url: str | None
    sha256: str | None = None
    # (version, markdown body) of every release newer than this one, newest first.
    notes: list[tuple[str, str]] = field(default_factory=list)


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
    wanted = SETUP_ASSET if is_installed() else PORTABLE_ASSET
    asset = next((a for a in data.get("assets", []) if a.get("name") == wanted), None)
    return Release(
        version=tag.lstrip("v"),
        page_url=data.get("html_url") or f"https://github.com/{RELEASES_REPO}/releases/latest",
        asset_url=asset.get("browser_download_url") if asset else None,
        sha256=_digest(asset),
        notes=_notes_since(__version__) or [(tag.lstrip("v"), data.get("body") or "")],
    )


def _notes_since(current: str) -> list[tuple[str, str]]:
    """Release notes of every published release newer than `current`."""
    url = f"https://api.github.com/repos/{RELEASES_REPO}/releases?per_page=30"
    try:
        with _request(url) as resp:
            releases = json.load(resp)
    except (OSError, ValueError):
        return []
    notes = [
        (r["tag_name"].lstrip("v"), r.get("body") or "")
        for r in releases
        if r.get("tag_name") and not r.get("draft") and not r.get("prerelease")
        and _parse(r["tag_name"]) > _parse(current)
    ]
    return sorted(notes, key=lambda n: _parse(n[0]), reverse=True)


def _digest(asset: dict | None) -> str | None:
    # GitHub computes this when the asset is uploaded ("sha256:<hex>").
    digest = (asset or {}).get("digest") or ""
    algo, _, value = digest.partition(":")
    return value.lower() if algo == "sha256" and len(value) == 64 else None


def can_self_update() -> bool:
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def is_installed() -> bool:
    """True for the copy installed by the setup program (it has an uninstaller
    next to it); False for the portable exe."""
    return can_self_update() and Path(sys.executable).with_name("unins000.exe").exists()


_pending_setup: Path | None = None


def _download(url: str, dest: Path, sha256: str) -> None:
    sha = hashlib.sha256()
    try:
        with _request(url) as resp, open(dest, "wb") as f:
            while chunk := resp.read(1 << 16):
                f.write(chunk)
                sha.update(chunk)
    except OSError:
        dest.unlink(missing_ok=True)
        raise
    if sha.hexdigest() != sha256:
        dest.unlink(missing_ok=True)
        raise UpdateError("checksum mismatch")


def _old_path(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".old.exe")


def install(release: Release) -> None:
    """Prepare the update. The caller must then call restart() and quit.

    Installed copy: download the setup program, which restart() runs silently;
    it waits for the app to close, replaces it and opens it again.
    Portable exe: download the new exe next to the running one and swap them
    (Windows allows renaming a running exe)."""
    global _pending_setup
    if not (can_self_update() and release.asset_url and release.sha256):
        raise UpdateError("manual")
    if is_installed():
        setup = Path(tempfile.gettempdir()) / f"EdifierR990BT-Setup-{release.version}.exe"
        try:
            _download(release.asset_url, setup, release.sha256)
        except OSError as e:
            raise UpdateError(str(e)) from e
        _pending_setup = setup
        return
    exe = Path(sys.executable)
    new = exe.with_name(exe.stem + ".new.exe")
    try:
        _download(release.asset_url, new, release.sha256)
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
    if _pending_setup is not None:
        spawn([str(_pending_setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"])
    else:
        spawn([sys.executable, UPDATED_FLAG])


def spawn(args: list[str]) -> None:
    """Start an independent copy of the app.

    Without PYINSTALLER_RESET_ENVIRONMENT, the new onefile exe reuses this
    process's temporary _MEI folder (inherited through the environment),
    which is deleted when this process exits, and the new copy fails to
    load Tk.
    """
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(args, env=env, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


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
