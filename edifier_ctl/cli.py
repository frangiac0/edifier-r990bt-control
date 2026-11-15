"""Herramienta de diagnostico por linea de comandos.

Uso:  python -m edifier_ctl <comando> [opciones]
Todo lo que se muestra queda guardado tambien en diagnostico.txt.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys

from . import protocol as p
from . import config
from .client import ADVERTISED_UUIDS, EdifierClient, find_speaker, is_edifier_service, scan, scan_all

LOG_PATH = "diagnostico.txt"
_log_file = None


def out(text: str = "") -> None:
    print(text, flush=True)
    if _log_file:
        _log_file.write(text + "\n")
        _log_file.flush()


def show_frame(frame: p.Frame) -> None:
    out(f"  <- {frame.describe()}")


async def resolve_address(address: str | None):
    """Direccion indicada, la guardada de una vez anterior, o la primera que aparezca."""
    if address:
        return address
    saved = config.saved_address()
    if saved:
        out(f"Usando el parlante guardado {saved}")
        return saved
    out("Buscando parlante Edifier (hasta 20 s)...")
    device = await find_speaker(timeout=20.0)
    if device is None:
        out(
            "No se encontro ningun parlante Edifier por BLE.\n"
            "Proba poniendo musica por Bluetooth en el parlante y volve a intentar, "
            "o usa 'scan --all' para ver todos los dispositivos."
        )
        raise SystemExit(1)
    out(f"Encontrado {device.name or '(sin nombre)'} {device.address}")
    config.remember_address(device.address)
    return device


async def cmd_forget(args) -> None:
    config.forget_address()
    out("Direccion guardada borrada. La proxima vez se va a buscar el parlante de nuevo.")


async def cmd_scan(args) -> None:
    out(f"Buscando dispositivos BLE ({args.timeout:.0f} s)...")
    rows = await (scan_all(args.timeout) if args.all else scan(args.timeout))
    if not rows:
        out("No se encontro nada. Con --all se listan todos los dispositivos BLE.")
    for device, name, uuids, rssi in rows:
        out(f"{device.address}  {rssi:>4} dBm  {name or '(sin nombre)'}")
        for u in uuids:
            mark = "  <- Edifier" if is_edifier_service(u) or u in ADVERTISED_UUIDS else ""
            out(f"      {u}{mark}")


async def cmd_gatt(args) -> None:
    address = await resolve_address(args.address)
    client = EdifierClient(address)
    await client.connect(require_service=False)
    try:
        for line in await client.gatt_dump():
            out(line)
    finally:
        await client.disconnect()


async def cmd_info(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        out(f"Servicio de control: {client.service_uuid}")
        queries = [
            ("Capacidades", p.OP_CAPABILITIES),
            ("Nombre", p.OP_NAME),
            ("Firmware", p.OP_FIRMWARE),
            ("Entrada", p.OP_SOURCE_GET),
            ("Volumen", p.OP_VOLUME_GET),
            ("Ecualizador", p.OP_EQ_GET),
        ]
        for label, op in queries:
            out(f"{label}:")
            out(f"  -> {p.build(op).hex(' ').upper()}")
            frame = await client.request(op)
            if frame is None:
                out("  (sin respuesta)")
                continue
            show_frame(frame)
            if op == p.OP_NAME:
                out(f"  texto: {frame.payload.decode('utf-8', 'replace')}")
            elif op == p.OP_FIRMWARE:
                out(f"  version: {'.'.join(str(b) for b in frame.payload)}")
            elif op == p.OP_SOURCE_GET and len(frame.payload) >= 2:
                out(f"  grupo {frame.payload[0]:02X}, entrada {frame.payload[1]:02X}")
            elif op == p.OP_VOLUME_GET and len(frame.payload) >= 2:
                out(f"  maximo {frame.payload[0]}, actual {frame.payload[1]}")


async def cmd_watch(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        out("Observando la entrada activa. Cambiala con la perilla del parlante,")
        out("esperando unos segundos en cada una. Ctrl+C para terminar.\n")
        last = None
        try:
            while True:
                current = await client.get_source()
                if current != last:
                    stamp = dt.datetime.now().strftime("%H:%M:%S")
                    if current is None:
                        out(f"{stamp}  sin respuesta a la consulta de entrada")
                    else:
                        out(f"{stamp}  grupo {current[0]:02X}  entrada {current[1]:02X}")
                    last = current
                await asyncio.sleep(args.interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass


async def cmd_source(args) -> None:
    address = await resolve_address(args.address)
    group, source = int(args.group, 16), int(args.source, 16)
    async with EdifierClient(address, on_frame=show_frame) as client:
        out(f"  -> {p.build(p.OP_SOURCE_SET, bytes([group, source])).hex(' ').upper()}")
        ack = await client.set_source(group, source)
        out("ACK recibido" if ack else "Sin ACK")
        await asyncio.sleep(3)
        current = await client.get_source()
        out(f"Entrada leida despues: {current[0]:02X} {current[1]:02X}" if current else "No se pudo leer la entrada")


async def cmd_send(args) -> None:
    address = await resolve_address(args.address)
    payload = p.parse_hex(" ".join(args.payload)) if args.payload else b""
    frame = p.build(int(args.opcode, 16), payload, int(args.app, 16))
    async with EdifierClient(address, on_frame=show_frame) as client:
        out(f"  -> {frame.hex(' ').upper()}")
        await client.send_raw(frame)
        await asyncio.sleep(args.wait)


def main(argv: list[str] | None = None) -> None:
    global _log_file
    parser = argparse.ArgumentParser(prog="edifier_ctl", description="Diagnostico BLE para Edifier R990BT")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="buscar parlantes por BLE")
    s.add_argument("--all", action="store_true", help="mostrar todos los dispositivos BLE")
    s.add_argument("--timeout", type=float, default=10.0)
    s.set_defaults(func=cmd_scan)

    for name, func, help_text in [
        ("gatt", cmd_gatt, "listar servicios y caracteristicas del parlante"),
        ("info", cmd_info, "consultar capacidades, nombre, firmware, entrada, volumen y EQ"),
        ("watch", cmd_watch, "mostrar la entrada activa mientras se cambia con la perilla"),
    ]:
        s = sub.add_parser(name, help=help_text)
        s.add_argument("--address", help="direccion BLE (si se omite, se busca sola)")
        if name == "watch":
            s.add_argument("--interval", type=float, default=1.5)
        s.set_defaults(func=func)

    s = sub.add_parser("source", help="cambiar la entrada (valores en hexadecimal)")
    s.add_argument("group", help="byte de grupo, el que muestra 'watch'")
    s.add_argument("source", help="codigo de entrada, el que muestra 'watch'")
    s.add_argument("--address")
    s.set_defaults(func=cmd_source)

    s = sub.add_parser("forget", help="olvidar el parlante guardado y volver a buscarlo")
    s.set_defaults(func=cmd_forget)

    s = sub.add_parser("send", help="mandar un comando arbitrario (uso avanzado)")
    s.add_argument("opcode", help="opcode en hexadecimal, por ejemplo 61")
    s.add_argument("payload", nargs="*", help="bytes de datos en hexadecimal")
    s.add_argument("--app", default="EC")
    s.add_argument("--wait", type=float, default=3.0)
    s.add_argument("--address")
    s.set_defaults(func=cmd_send)

    args = parser.parse_args(argv)
    _log_file = open(LOG_PATH, "a", encoding="utf-8")
    out(f"\n=== {dt.datetime.now():%Y-%m-%d %H:%M:%S}  {' '.join(sys.argv[1:])} ===")
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # mostrar el error en el log para poder compartirlo
        out(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)
    finally:
        _log_file.close()
