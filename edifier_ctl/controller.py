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
# After "pair", the BLE link drops for a minute or two; keep showing pairing mode meanwhile.
PAIRING_STATUS_SECONDS = 180.0


@dataclass(frozen=True)
class State:
    status: str = ""
    connected: bool = False
    name: str | None = None
    source: int | None = None
    volume: int | None = None
    volume_max: int = r990bt.VOLUME_MAX
    eq: int | None = None
    prompt_tone: bool | None = None
    eq_mode: str = "preset"          # "preset" or "custom"
    custom_gains: tuple = (0, 0, 0, 0, 0, 0)
    custom_name: str | None = None
    track_title: str | None = None
    track_artist: str | None = None
    sleep_timer_min: int = 0        # speaker's native scheduled power-off (0 = off)


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
        self._pairing_until = 0.0
        # Remember the last EQ mode so a saved custom curve is reapplied on connect.
        mode = config.get("eq_mode", "preset")
        if mode == "custom":
            gains = r990bt.clamp_gains(config.get("custom_gains", (0,) * 6))
            self._state = replace(self._state, eq_mode="custom", custom_gains=gains,
                                  custom_name=config.get("custom_name"))
            self._apply_custom_on_connect = True
        else:
            self._apply_custom_on_connect = False

    # --- API for the GUI (any thread) ---

    @property
    def state(self) -> State:
        return self._state

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

    def set_custom_eq(self, gains, name: str | None = None) -> None:
        self._submit(self._do_set_custom_eq(tuple(gains), name))

    def set_prompt_tone(self, enabled: bool) -> None:
        self._submit(self._do_set_prompt_tone(enabled))

    def set_name(self, name: str, on_done: Callable[[bool], None] | None = None) -> None:
        self._submit(self._do_set_name(name, on_done))

    def pair(self) -> None:
        self._submit(self._do_pair())

    def power_off(self) -> None:
        self._submit(self._do_power_off())

    def set_sleep_timer(self, minutes: int) -> None:
        self._submit(self._do_set_sleep_timer(minutes))

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
                elif time.monotonic() < self._pairing_until:
                    self._update(connected=False, status=t("pairing_status"))
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
                try:
                    await asyncio.sleep(RETRY_SECONDS)
                except asyncio.CancelledError:
                    break

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
        if not self._powered_off and time.monotonic() >= self._pairing_until:
            self._update(status=t("connecting"))
        client = EdifierClient(address, on_frame=self._on_frame)
        self._client = client
        await client.connect()
        config.remember_address(client.address)

        name_frame = await self._request(p.OP_NAME)
        name = name_frame.payload.decode("utf-8", "replace").strip() if name_frame else "Edifier"
        self._powered_off = False
        self._update(connected=True, name=name, status=t("connected", name=name))
        await self._refresh_prompt_tone()
        if self._apply_custom_on_connect and self._state.eq_mode == "custom":
            await self._send_custom_eq(self._state.custom_gains)

        misses = 0
        while not self._stopping:
            ok = await self._poll()
            misses = 0 if ok else misses + 1
            if misses >= 3 or not client.is_connected:
                raise ConnectionError("speaker stopped responding")
            await asyncio.sleep(POLL_SECONDS)

    def _on_frame(self, frame: p.Frame) -> None:
        # The speaker pushes the current track title (0x01) and artist (0x02).
        if frame.opcode == p.OP_SONG_NAME:
            title = frame.payload.decode("utf-8", "replace").strip() or None
            if title != self._state.track_title:
                self._update(track_title=title)
        elif frame.opcode == p.OP_SINGER_NAME:
            artist = frame.payload.decode("utf-8", "replace").strip() or None
            if artist != self._state.track_artist:
                self._update(track_artist=artist)

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
        tmr = await self._request(p.OP_TIMER_GET)
        if tmr and len(tmr.payload) >= 2:
            changes["sleep_timer_min"] = (tmr.payload[0] << 8) | tmr.payload[1]
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

    async def _refresh_prompt_tone(self) -> None:
        frame = await self._request(p.OP_PROMPT_TONE_GET)
        if frame and frame.payload:
            self._update(prompt_tone=frame.payload[0] == 1)

    async def _do_set_prompt_tone(self, enabled: bool) -> None:
        await self._request(p.OP_PROMPT_TONE_SET, bytes([1 if enabled else 0]))
        await asyncio.sleep(0.5)
        await self._refresh_prompt_tone()

    async def _do_set_name(self, name: str, on_done) -> None:
        ok = False
        try:
            data = name.strip().encode("utf-8")
            if self._client and 0 < len(data) <= 30:
                await self._request(p.OP_NAME_SET, data)
                await asyncio.sleep(0.5)
                frame = await self._request(p.OP_NAME)
                if frame:
                    new_name = frame.payload.decode("utf-8", "replace").strip()
                    ok = new_name == name.strip()
                    self._update(name=new_name, status=t("connected", name=new_name))
        finally:
            if on_done:
                on_done(ok)

    async def _do_pair(self) -> None:
        if self._client is None or self._lock is None:
            return
        self._pairing_until = time.monotonic() + PAIRING_STATUS_SECONDS
        async with self._lock:
            await self._client.disconnect_audio()
        self._update(connected=False, status=t("pairing_status"))
        try:
            await self._client.disconnect()
        except Exception:
            pass

    async def _do_set_sleep_timer(self, minutes: int) -> None:
        minutes = max(0, min(600, int(minutes)))
        if minutes:
            await self._request(p.OP_TIMER_SET, bytes([(minutes >> 8) & 0xFF, minutes & 0xFF]))
        else:
            await self._request(p.OP_TIMER_CANCEL)
        self._hold["sleep_timer_min"] = time.monotonic() + HOLD_SECONDS
        self._update(sleep_timer_min=minutes)

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
        self._apply_custom_on_connect = False
        config.set_values(eq_mode="preset")
        self._update(eq=preset, eq_mode="preset", custom_name=None)

    async def _send_custom_eq(self, gains) -> None:
        for opcode, payload in r990bt.custom_eq_frames(gains):
            await self._request(opcode, payload)
            await asyncio.sleep(0.05)

    async def _do_set_custom_eq(self, gains, name) -> None:
        gains = r990bt.clamp_gains(gains)
        await self._send_custom_eq(gains)
        self._apply_custom_on_connect = True
        config.set_values(eq_mode="custom", custom_gains=list(gains), custom_name=name)
        self._update(eq_mode="custom", custom_gains=gains, custom_name=name)

    async def _shutdown(self) -> None:
        for task in asyncio.all_tasks(self._loop):
            if task is not asyncio.current_task():
                task.cancel()
        if self._client:
            await self._client.disconnect()
