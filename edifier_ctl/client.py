"""BLE client for ConneX-compatible Edifier speakers."""

from __future__ import annotations

import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol as p

# On documented models the control service is 4809xxxx-1a48-11e9-ab14-d663bd873d93
# (xxxx depends on the model) and the characteristics are always these two.
SERVICE_SUFFIX = "-1a48-11e9-ab14-d663bd873d93"
NOTIFY_CHAR = "48090001" + SERVICE_SUFFIX
WRITE_CHAR = "48090002" + SERVICE_SUFFIX
WRITE_CHUNK = 20
NAME_MAX_BYTES = 30  # R990BT capability byte 3 = 02


# UUID the R990BT advertises so that ConneX can find it.
ADVERTISED_UUIDS = {"0000d300-0000-1000-8000-00805f9b34fb"}


def is_edifier_service(uuid: str) -> bool:
    uuid = uuid.lower()
    return uuid.startswith("4809") and uuid.endswith(SERVICE_SUFFIX)


def looks_like_edifier(device: BLEDevice, adv) -> bool:
    name = (adv.local_name or device.name or "").lower()
    uuids = [u.lower() for u in adv.service_uuids]
    return "edifier" in name or any(u in ADVERTISED_UUIDS or is_edifier_service(u) for u in uuids)


async def find_speaker(timeout: float = 20.0) -> BLEDevice | None:
    """Wait for the first Edifier speaker. The speaker advertises intermittently, so use a
    long timeout; the search returns as soon as it shows up."""
    return await BleakScanner.find_device_by_filter(looks_like_edifier, timeout=timeout)


async def scan(timeout: float = 10.0) -> list[tuple[BLEDevice, str, list[str], int]]:
    """Return (device, name, advertised uuids, rssi) for Edifier candidates."""
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    result = []
    for device, adv in found.values():
        if looks_like_edifier(device, adv):
            name = adv.local_name or device.name or ""
            result.append((device, name, [u.lower() for u in adv.service_uuids], adv.rssi))
    result.sort(key=lambda r: -r[3])
    return result


async def scan_all(timeout: float = 10.0):
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    rows = []
    for device, adv in found.values():
        rows.append((device, adv.local_name or device.name or "", [u.lower() for u in adv.service_uuids], adv.rssi))
    rows.sort(key=lambda r: -r[3])
    return rows


class EdifierClient:
    def __init__(self, address: str | BLEDevice, on_frame: Callable[[p.Frame], None] | None = None) -> None:
        self.address = address if isinstance(address, str) else address.address
        self._client = BleakClient(address)
        self._parser = p.FrameParser()
        self._queue: asyncio.Queue[p.Frame] = asyncio.Queue()
        self._on_frame = on_frame
        self._write_with_response = True
        self.service_uuid: str | None = None

    async def __aenter__(self) -> "EdifierClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def connect(self, require_service: bool = True) -> None:
        await self._client.connect(timeout=30.0)
        if not require_service:
            return
        service = next((s for s in self._client.services if is_edifier_service(s.uuid)), None)
        if service is None:
            raise RuntimeError(
                "Connected, but the Edifier control service is missing. "
                "Run the 'gatt' command to see which services the speaker exposes."
            )
        self.service_uuid = service.uuid
        write_char = service.get_characteristic(WRITE_CHAR)
        if write_char is None or service.get_characteristic(NOTIFY_CHAR) is None:
            raise RuntimeError(f"Service {service.uuid} lacks the expected characteristics.")
        self._write_with_response = "write" in write_char.properties
        await self._client.start_notify(service.get_characteristic(NOTIFY_CHAR), self._handle)

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    async def disconnect(self) -> None:
        if self._client.is_connected:
            await self._client.disconnect()

    def _handle(self, _char, data: bytearray) -> None:
        for frame in self._parser.feed(bytes(data)):
            if self._on_frame:
                self._on_frame(frame)
            self._queue.put_nowait(frame)

    async def send_raw(self, data: bytes) -> None:
        # ConneX writes long frames in 20-byte pieces and the speaker reassembles them.
        for i in range(0, len(data), WRITE_CHUNK):
            await self._client.write_gatt_char(WRITE_CHAR, data[i : i + WRITE_CHUNK], response=self._write_with_response)

    async def request(self, opcode: int, payload: bytes = b"", timeout: float = 3.0, app: int = 0xEC) -> p.Frame | None:
        """Send a request and wait for the first reply with the same opcode."""
        while not self._queue.empty():
            self._queue.get_nowait()
        await self.send_raw(p.build(opcode, payload, app))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while (remaining := deadline - loop.time()) > 0:
            try:
                frame = await asyncio.wait_for(self._queue.get(), remaining)
            except asyncio.TimeoutError:
                break
            if frame.opcode == opcode and frame.header != p.HOST:
                return frame
        return None

    async def gatt_dump(self) -> list[str]:
        lines = []
        for service in self._client.services:
            lines.append(f"Servicio {service.uuid}  {service.description}")
            for char in service.characteristics:
                lines.append(f"    Caracteristica {char.uuid}  [{', '.join(char.properties)}]")
        return lines

    # --- High-level operations ---

    async def get_source(self) -> tuple[int, int] | None:
        frame = await self.request(p.OP_SOURCE_GET)
        if frame and len(frame.payload) >= 2:
            return frame.payload[0], frame.payload[1]
        return None

    async def set_source(self, group: int, source: int) -> p.Frame | None:
        return await self.request(p.OP_SOURCE_SET, bytes([group, source]))

    async def power_off(self) -> None:
        """Turn the speaker off. It sends no reply and cannot be turned back on over BLE."""
        await self.send_raw(p.build(p.OP_POWER_OFF))

    async def get_name(self) -> str | None:
        frame = await self.request(p.OP_NAME)
        return frame.payload.decode("utf-8", "replace").strip() if frame else None

    async def set_name(self, name: str) -> p.Frame | None:
        data = name.strip().encode("utf-8")
        if not data or len(data) > NAME_MAX_BYTES:
            raise ValueError(f"the name must be 1 to {NAME_MAX_BYTES} bytes long")
        return await self.request(p.OP_NAME_SET, data)

    async def get_prompt_tone(self) -> bool | None:
        frame = await self.request(p.OP_PROMPT_TONE_GET)
        return frame.payload[0] == 1 if frame and frame.payload else None

    async def set_prompt_tone(self, enabled: bool) -> p.Frame | None:
        return await self.request(p.OP_PROMPT_TONE_SET, bytes([1 if enabled else 0]))

    async def get_volume(self) -> tuple[int, int] | None:
        frame = await self.request(p.OP_VOLUME_GET)
        if frame and len(frame.payload) >= 2:
            return frame.payload[0], frame.payload[1]
        return None

    async def set_volume(self, value: int) -> p.Frame | None:
        return await self.request(p.OP_VOLUME_SET, bytes([value]))

