"""Cliente BLE para parlantes Edifier compatibles con ConneX."""

from __future__ import annotations

import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol as p

# En los modelos documentados el servicio de control es 4809xxxx-1a48-11e9-ab14-d663bd873d93
# (xxxx cambia segun el modelo) y las caracteristicas son siempre estas dos.
SERVICE_SUFFIX = "-1a48-11e9-ab14-d663bd873d93"
NOTIFY_CHAR = "48090001" + SERVICE_SUFFIX
WRITE_CHAR = "48090002" + SERVICE_SUFFIX


# UUID que anuncia el R990BT para que ConneX lo encuentre.
ADVERTISED_UUIDS = {"0000d300-0000-1000-8000-00805f9b34fb"}


def is_edifier_service(uuid: str) -> bool:
    uuid = uuid.lower()
    return uuid.startswith("4809") and uuid.endswith(SERVICE_SUFFIX)


def looks_like_edifier(device: BLEDevice, adv) -> bool:
    name = (adv.local_name or device.name or "").lower()
    uuids = [u.lower() for u in adv.service_uuids]
    return "edifier" in name or any(u in ADVERTISED_UUIDS or is_edifier_service(u) for u in uuids)


async def find_speaker(timeout: float = 20.0) -> BLEDevice | None:
    """Espera hasta encontrar el primer parlante Edifier. El parlante se anuncia de forma
    intermitente, asi que conviene un tiempo largo; la busqueda corta apenas aparece."""
    return await BleakScanner.find_device_by_filter(looks_like_edifier, timeout=timeout)


async def scan(timeout: float = 10.0) -> list[tuple[BLEDevice, str, list[str], int]]:
    """Devuelve (dispositivo, nombre, uuids anunciados, rssi) de los candidatos Edifier."""
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
                "Conectado, pero no aparece el servicio de control de Edifier. "
                "Usa el comando 'gatt' para ver que servicios expone el parlante."
            )
        self.service_uuid = service.uuid
        write_char = service.get_characteristic(WRITE_CHAR)
        if write_char is None or service.get_characteristic(NOTIFY_CHAR) is None:
            raise RuntimeError(f"El servicio {service.uuid} no tiene las caracteristicas esperadas.")
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
        await self._client.write_gatt_char(WRITE_CHAR, data, response=self._write_with_response)

    async def request(self, opcode: int, payload: bytes = b"", timeout: float = 3.0, app: int = 0xEC) -> p.Frame | None:
        """Manda un pedido y espera la primera respuesta con el mismo opcode."""
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

    # --- Operaciones de alto nivel (formato tomado de otros modelos, sin verificar en R990BT) ---

    async def get_source(self) -> tuple[int, int] | None:
        frame = await self.request(p.OP_SOURCE_GET)
        if frame and len(frame.payload) >= 2:
            return frame.payload[0], frame.payload[1]
        return None

    async def set_source(self, group: int, source: int) -> p.Frame | None:
        return await self.request(p.OP_SOURCE_SET, bytes([group, source]))

    async def get_volume(self) -> tuple[int, int] | None:
        frame = await self.request(p.OP_VOLUME_GET)
        if frame and len(frame.payload) >= 2:
            return frame.payload[0], frame.payload[1]
        return None

    async def set_volume(self, value: int) -> p.Frame | None:
        return await self.request(p.OP_VOLUME_SET, bytes([value]))

