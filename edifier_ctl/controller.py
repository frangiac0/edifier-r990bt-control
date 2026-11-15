"""Keeps the speaker connection on its own thread and exposes simple operations.

The GUI calls the public methods from its own thread; all BLE work runs on a
separate asyncio loop. State changes are reported through a callback.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from . import protocol as p
from . import r990bt
from . import config
from .client import EdifierClient, find_speaker
from .i18n import t

POLL_SECONDS = 2.0
# After a change, the speaker takes a few seconds to report the new value.
HOLD_SECONDS = 4.0
RETRY_SECONDS = 5.0


@dataclass(frozen=True)
class State:
    status: str = ""
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
        self._hold: dict[str, float] = {}
        self._powered_off = False

    # --- API for the GUI (any thread) ---

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

    def power_off(self) -> None:
        self._submit(self._do_power_off())

    def forget_device(self) -> None:
        config.forget_address()

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
            except Exception as exc:  # any BLE failure: retry
                if self._powered_off:
                    self._update(connected=False, status=t("powered_off"))
                else:
                    self._update(connected=False, status=t("retrying", error=type(exc).__name__))
            finally:
                if self._client:
                    try:
                        await self._client.disconnect()
                    except Exception:
                        pass
                    self._client = None
            if not self._stopping:
                await asyncio.sleep(RETRY_SECONDS)

    async def _find_address(self):
        saved = config.saved_address()
        if saved:
            return saved
        self._update(connected=False, status=t("searching"))
        device = await find_speaker(timeout=20.0)
        if device is None:
            self._update(status=t("not_found"))
        return device

    async def _session(self) -> None:
        address = await self._find_address()
        if address is None:
            return
        if not self._powered_off:
            self._update(status=t("connecting"))
        client = EdifierClient(address)
        self._client = client
        await client.connect()
        config.remember_address(client.address)

        name_frame = await self._request(p.OP_NAME)
        name = name_frame.payload.decode("utf-8", "replace").strip() if name_frame else "Edifier"
        self._powered_off = False
        self._update(connected=True, name=name, status=t("connected", name=name))

        misses = 0
        while not self._stopping:
            ok = await self._poll()
            misses = 0 if ok else misses + 1
            if misses >= 3 or not client.is_connected:
                raise ConnectionError("speaker stopped responding")
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

    async def _do_power_off(self) -> None:
        if self._client is None or self._lock is None:
            return
        self._powered_off = True
        async with self._lock:
            await self._client.power_off()
        self._update(connected=False, status=t("powered_off"))
        try:
            await self._client.disconnect()
        except Exception:
            pass

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
