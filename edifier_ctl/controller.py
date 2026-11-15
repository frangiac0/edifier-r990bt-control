"""Mantiene la conexion con el parlante en un hilo propio y expone operaciones simples.

La interfaz grafica llama a los metodos publicos desde su hilo; todo el trabajo BLE
ocurre en un bucle asyncio aparte. Los cambios de estado se informan por callback.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from . import protocol as p
from . import r990bt
from .client import EdifierClient, scan

POLL_SECONDS = 2.0
# Despues de un cambio, el parlante tarda unos segundos en informar el valor nuevo.
HOLD_SECONDS = 4.0
RETRY_SECONDS = 5.0


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


@dataclass(frozen=True)
class State:
    status: str = "Buscando parlante..."
    connected: bool = False
    name: str | None = None
    source: int | None = None
    volume: int | None = None
    volume_max: int = r990bt.VOLUME_MAX
    eq: int | None = None


class Controller:
    def __init__(self, on_state: Callable[[State], None]) -> None:
        self._on_state = on_state
        self._state = State()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="ble", daemon=True)
        self._client: EdifierClient | None = None
        self._lock: asyncio.Lock | None = None
        self._stopping = False
        self._config = load_config()
        self._hold: dict[str, float] = {}

    # --- API para la interfaz (cualquier hilo) ---

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
        fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            fut.result(timeout=5)
        except Exception:
            pass

    def set_source(self, source: int) -> None:
        self._submit(self._do_set_source(source))

    def set_volume(self, volume: int) -> None:
        self._submit(self._do_set_volume(volume))

    def set_eq(self, preset: int) -> None:
        self._submit(self._do_set_eq(preset))

    def forget_device(self) -> None:
        self._config.pop("address", None)
        save_config(self._config)

    # --- Interno ---

    def _submit(self, coro) -> None:
        if self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        else:
            coro.close()

    def _update(self, **changes) -> None:
        self._state = replace(self._state, **changes)
        self._on_state(self._state)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._lock = asyncio.Lock()
        self._loop.run_until_complete(self._main())

    async def _main(self) -> None:
        while not self._stopping:
            try:
                await self._session()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # cualquier fallo BLE: reintentar
                self._update(connected=False, status=f"Sin conexion ({type(exc).__name__}). Reintentando...")
            finally:
                if self._client:
                    try:
                        await self._client.disconnect()
                    except Exception:
                        pass
                    self._client = None
            if not self._stopping:
                await asyncio.sleep(RETRY_SECONDS)

    async def _find_address(self) -> str | None:
        if self._config.get("address"):
            return self._config["address"]
        self._update(connected=False, status="Buscando parlante...")
        found = await scan(timeout=8.0)
        if not found:
            self._update(status="No se encontro el parlante. Pone musica por Bluetooth o cerra ConneX en el celular.")
            return None
        return found[0][0].address

    async def _session(self) -> None:
        address = await self._find_address()
        if address is None:
            return
        self._update(status="Conectando...")
        client = EdifierClient(address)
        self._client = client
        await client.connect()
        if self._config.get("address") != address:
            self._config["address"] = address
            save_config(self._config)

        name_frame = await self._request(p.OP_NAME)
        name = name_frame.payload.decode("utf-8", "replace").strip() if name_frame else "Edifier"
        self._update(connected=True, name=name, status=f"Conectado a {name}")

        misses = 0
        while not self._stopping:
            ok = await self._poll()
            misses = 0 if ok else misses + 1
            if misses >= 3 or not client.is_connected:
                raise ConnectionError("el parlante dejo de responder")
            await asyncio.sleep(POLL_SECONDS)

    async def _request(self, opcode: int, payload: bytes = b"") -> p.Frame | None:
        assert self._lock is not None
        if self._client is None:
            return None
        async with self._lock:
            return await self._client.request(opcode, payload)

    async def _poll(self) -> bool:
        changes = {}
        src = await self._request(p.OP_SOURCE_GET)
        if src and len(src.payload) >= 2:
            changes["source"] = src.payload[1]
        vol = await self._request(p.OP_VOLUME_GET)
        if vol and len(vol.payload) >= 2:
            changes["volume_max"] = vol.payload[0] or r990bt.VOLUME_MAX
            changes["volume"] = vol.payload[1]
        eq = await self._request(p.OP_EQ_GET)
        if eq and eq.payload:
            changes["eq"] = eq.payload[0]
        now = time.monotonic()
        changes = {k: v for k, v in changes.items() if self._hold.get(k, 0) <= now}
        if src is None and vol is None and eq is None:
            return False
        if changes and any(getattr(self._state, k) != v for k, v in changes.items()):
            self._update(**changes)
        return True

    async def _do_set_source(self, source: int) -> None:
        await self._request(p.OP_SOURCE_SET, bytes([r990bt.SOURCE_GROUP, source]))
        self._hold["source"] = time.monotonic() + HOLD_SECONDS
        self._update(source=source)

    async def _do_set_volume(self, volume: int) -> None:
        volume = max(0, min(volume, self._state.volume_max))
        await self._request(p.OP_VOLUME_SET, bytes([volume]))
        self._hold["volume"] = time.monotonic() + HOLD_SECONDS
        self._update(volume=volume)

    async def _do_set_eq(self, preset: int) -> None:
        await self._request(p.OP_EQ_SET, bytes([preset]))
        self._hold["eq"] = time.monotonic() + HOLD_SECONDS
        self._update(eq=preset)

    async def _shutdown(self) -> None:
        for task in asyncio.all_tasks(self._loop):
            if task is not asyncio.current_task():
                task.cancel()
        if self._client:
            await self._client.disconnect()
