"""Command-line tool for diagnostics and scripting.

Usage:  python -m edifier_ctl <command> [options]
Everything printed is also appended to diagnostics.txt.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys

from . import config, r990bt
from . import protocol as p
from .client import ADVERTISED_UUIDS, EdifierClient, find_speaker, is_edifier_service, scan, scan_all

LOG_PATH = "diagnostics.txt"
_log_file = None

SOURCE_ALIASES = {"bt": 0x01, "bluetooth": 0x01, "line1": 0x02, "line2": 0x03}


def out(text: str = "") -> None:
    print(text, flush=True)
    if _log_file:
        _log_file.write(text + "\n")
        _log_file.flush()


def show_frame(frame: p.Frame) -> None:
    out(f"  <- {frame.describe()}")


async def resolve_address(address: str | None):
    """The given address, the one saved from an earlier run, or the first speaker found."""
    if address:
        return address
    saved = config.saved_address()
    if saved:
        out(f"Using saved speaker {saved}")
        return saved
    out("Searching for an Edifier speaker (up to 20 s)...")
    device = await find_speaker(timeout=20.0)
    if device is None:
        out(
            "No Edifier speaker found over BLE.\n"
            "Play something on the speaker over Bluetooth and try again, "
            "or run 'scan --all' to list every BLE device."
        )
        raise SystemExit(1)
    out(f"Found {device.name or '(no name)'} {device.address}")
    config.remember_address(device.address)
    return device


async def cmd_forget(args) -> None:
    config.forget_address()
    out("Saved address cleared. The speaker will be searched for again next time.")


async def cmd_scan(args) -> None:
    out(f"Scanning for BLE devices ({args.timeout:.0f} s)...")
    rows = await (scan_all(args.timeout) if args.all else scan(args.timeout))
    if not rows:
        out("Nothing found. Use --all to list every BLE device.")
    for device, name, uuids, rssi in rows:
        out(f"{device.address}  {rssi:>4} dBm  {name or '(no name)'}")
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
        out(f"Control service: {client.service_uuid}")
        queries = [
            ("Capabilities", p.OP_CAPABILITIES),
            ("Name", p.OP_NAME),
            ("Firmware", p.OP_FIRMWARE),
            ("Input", p.OP_SOURCE_GET),
            ("Volume", p.OP_VOLUME_GET),
            ("EQ preset", p.OP_EQ_GET),
        ]
        for label, op in queries:
            out(f"{label}:")
            out(f"  -> {p.build(op).hex(' ').upper()}")
            frame = await client.request(op)
            if frame is None:
                out("  (no reply)")
                continue
            show_frame(frame)
            if op == p.OP_NAME:
                out(f"  text: {frame.payload.decode('utf-8', 'replace')}")
            elif op == p.OP_FIRMWARE:
                out(f"  version: {'.'.join(str(b) for b in frame.payload)}")
            elif op == p.OP_SOURCE_GET and len(frame.payload) >= 2:
                name = r990bt.SOURCES.get(frame.payload[1], "?")
                out(f"  group {frame.payload[0]:02X}, input {frame.payload[1]:02X} ({name})")
            elif op == p.OP_VOLUME_GET and len(frame.payload) >= 2:
                out(f"  max {frame.payload[0]}, current {frame.payload[1]}")


async def cmd_watch(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        out("Watching the active input. Change it with the speaker knob,")
        out("waiting a few seconds on each one. Ctrl+C to stop.\n")
        last = None
        try:
            while True:
                current = await client.get_source()
                if current != last:
                    stamp = dt.datetime.now().strftime("%H:%M:%S")
                    if current is None:
                        out(f"{stamp}  no reply to the input query")
                    else:
                        out(f"{stamp}  group {current[0]:02X}  input {current[1]:02X}")
                    last = current
                await asyncio.sleep(args.interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass


def parse_source(values: list[str]) -> tuple[int, int]:
    if len(values) == 1 and values[0].lower() in SOURCE_ALIASES:
        return r990bt.SOURCE_GROUP, SOURCE_ALIASES[values[0].lower()]
    if len(values) == 2:
        return int(values[0], 16), int(values[1], 16)
    raise SystemExit("Use: source bt|line1|line2   or   source <group> <input> (hex)")


async def cmd_source(args) -> None:
    group, source = parse_source(args.values)
    address = await resolve_address(args.address)
    async with EdifierClient(address, on_frame=show_frame if args.verbose else None) as client:
        out(f"  -> {p.build(p.OP_SOURCE_SET, bytes([group, source])).hex(' ').upper()}")
        ack = await client.set_source(group, source)
        out("ACK received" if ack else "No ACK")
        if args.verbose:
            await asyncio.sleep(3)
            current = await client.get_source()
            out(f"Input read back: {current[0]:02X} {current[1]:02X}" if current else "Could not read the input")


async def cmd_volume(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        current = await client.get_volume()
        if args.value is None:
            out(f"Volume {current[1]} / {current[0]}" if current else "No reply")
            return
        maximum = current[0] if current else r990bt.VOLUME_MAX
        value = args.value
        if args.value.startswith(("+", "-")):
            if not current:
                raise SystemExit("Could not read the current volume.")
            value = current[1] + int(args.value)
        value = max(0, min(int(value), maximum))
        ack = await client.set_volume(value)
        out(f"Volume set to {value}" + ("" if ack else " (no ACK)"))


EQ_ALIASES = {"music": 0x00, "game": 0x01, "movie": 0x02}


def parse_preset(value: str) -> int:
    if value.lower() in EQ_ALIASES:
        return EQ_ALIASES[value.lower()]
    if value.isdigit() and int(value) in r990bt.EQ_PRESETS:
        return int(value)
    raise argparse.ArgumentTypeError("use music, movie or game")


async def cmd_eq(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        ack = await client.request(p.OP_EQ_SET, bytes([args.preset]))
        out(f"EQ preset {args.preset} selected" + ("" if ack else " (no ACK)"))


async def cmd_off(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        await client.power_off()
        out("Power-off sent. Turn the speaker back on with its knob.")


async def cmd_name(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        if args.new_name:
            ack = await client.set_name(" ".join(args.new_name))
            out("Name sent" + ("" if ack else " (no ACK)"))
            await asyncio.sleep(0.5)
        out(f"Name: {await client.get_name()}")


async def cmd_tone(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        if args.state:
            ack = await client.set_prompt_tone(args.state == "on")
            out("Prompt tone " + args.state + ("" if ack else " (no ACK)"))
            await asyncio.sleep(0.5)
        state = await client.get_prompt_tone()
        out("Prompt tone: " + ("unknown (no reply)" if state is None else "on" if state else "off"))


async def cmd_pair(args) -> None:
    address = await resolve_address(args.address)
    async with EdifierClient(address) as client:
        await client.disconnect_audio()
        out("Audio device disconnected; the speaker is in pairing mode.")
        out("Connect the new device to EDIFIER R990BT. Control commands work again in a minute or two.")


async def cmd_send(args) -> None:
    address = await resolve_address(args.address)
    payload = p.parse_hex(" ".join(args.payload)) if args.payload else b""
    frame = p.build(int(args.opcode, 16), payload, int(args.app, 16))
    async with EdifierClient(address, on_frame=show_frame) as client:
        out(f"  -> {frame.hex(' ').upper()}")
        await client.send_raw(frame)
        await asyncio.sleep(args.wait)


# --- Safe read-only opcode probing ---------------------------------------
#
# These are the opcodes we already know change the speaker's state or are part
# of firmware update / reset. The probe NEVER sends any of them, and it only
# ever sends an empty payload, so it cannot carry data into a write command.
DANGEROUS_OPCODES = {
    p.OP_SOURCE_SET, p.OP_VOLUME_SET, p.OP_EQ_SET, p.OP_NAME_SET,
    p.OP_PROMPT_TONE_SET, p.OP_POWER_OFF, p.OP_DISCONNECT_AUDIO, p.OP_MEDIA,
    0x07,              # factory reset
    0x10, 0x11, 0x12,  # firmware update
    0x86, 0x87,        # multi prompt tone set
    0xC2, 0xB8,        # playback / LAN-switch set
}

# Opcodes that look like queries: the known read opcodes, plus the even/low
# partners of known get/set pairs. Default probe target; low risk.
LIKELY_QUERY_OPCODES = [
    p.OP_CAPABILITIES, p.OP_NAME, p.OP_FIRMWARE, p.OP_SOURCE_GET,
    p.OP_VOLUME_GET, p.OP_EQ_GET, p.OP_PROMPT_TONE_GET, p.OP_A2DP_STATE,
    0x60, 0x63, 0x64, 0x65, 0x68, 0x69,   # neighbours of input/volume gets
    0xC5, 0xC7, 0xC8, 0xCB, 0xCC, 0xCF,   # neighbours of name/firmware/eq
    0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD6, 0xD7, 0xD9,  # around eq/capabilities
    0xDA, 0xDB, 0xDC, 0xF0, 0xF1, 0xF8, 0xFB, 0xFC,  # status-like ranges
]


async def cmd_probe(args) -> None:
    address = await resolve_address(args.address)
    if args.range:
        lo, hi = (int(x, 16) for x in args.range)
        if not (0 <= lo <= hi <= 0xFF):
            out("Range must be two hex bytes, low high (e.g. --range 60 70).")
            raise SystemExit(2)
        targets = list(range(lo, hi + 1))
        if not args.i_understand_the_risk:
            out(
                "A range sweep sends every opcode in the range except the known "
                "dangerous ones. Unknown opcodes could still change the speaker.\n"
                "Re-run with --i-understand-the-risk to proceed."
            )
            raise SystemExit(2)
    else:
        targets = list(LIKELY_QUERY_OPCODES)

    skipped = sorted(o for o in targets if o in DANGEROUS_OPCODES)
    targets = [o for o in targets if o not in DANGEROUS_OPCODES]
    known = {
        p.OP_CAPABILITIES, p.OP_NAME, p.OP_FIRMWARE, p.OP_SOURCE_GET,
        p.OP_VOLUME_GET, p.OP_EQ_GET, p.OP_PROMPT_TONE_GET, p.OP_A2DP_STATE,
    }

    out(f"Probing {len(targets)} read-only opcodes (empty payload, {args.wait}s each).")
    if skipped:
        out("Skipped (known state-changing): " + " ".join(f"{o:02X}" for o in skipped))
    out("Only opcodes that reply are shown. Nothing is written to the speaker.\n")

    answered = []
    async with EdifierClient(address) as client:
        for op in targets:
            reply = await client.request(op, b"", timeout=args.wait)
            if reply is None:
                continue
            tag = "known" if op in known else "UNDOCUMENTED"
            answered.append((op, reply, tag))
            out(f"  {op:02X} -> {reply.describe()}   [{tag}]")

    out("")
    new = [(o, r) for o, r, t in answered if t == "UNDOCUMENTED"]
    if new:
        out(f"{len(new)} undocumented opcode(s) replied: " + " ".join(f"{o:02X}" for o, _ in new))
        out("Share this output; these are candidates for new read commands.")
    else:
        out("No undocumented opcodes replied. Nothing new beyond what is known.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edifier_ctl", description="Edifier R990BT BLE control and diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str, func, address: bool = True):
        s = sub.add_parser(name, help=help_text)
        if address:
            s.add_argument("--address", help="BLE address (default: saved speaker, or search)")
        s.set_defaults(func=func)
        return s

    s = command("scan", "search for speakers over BLE", cmd_scan, address=False)
    s.add_argument("--all", action="store_true", help="list every BLE device")
    s.add_argument("--timeout", type=float, default=10.0)

    command("gatt", "list the speaker's GATT services", cmd_gatt)
    command("info", "query capabilities, name, firmware, input, volume and EQ", cmd_info)
    s = command("watch", "print the active input while you change it with the knob", cmd_watch)
    s.add_argument("--interval", type=float, default=1.5)

    s = command("source", "switch input: bt, line1, line2 (or <group> <input> in hex)", cmd_source)
    s.add_argument("values", nargs="+")
    s.add_argument("-v", "--verbose", action="store_true", help="show raw frames and read the input back")

    s = command("volume", "show the volume, or set it: 8, +1, -2", cmd_volume)
    s.add_argument("value", nargs="?")

    s = command("eq", "select EQ preset: music, movie, game (or 0, 2, 1)", cmd_eq)
    s.add_argument("preset", type=parse_preset)

    s = command("name", "show the speaker name, or change it (up to 30 characters)", cmd_name)
    s.add_argument("new_name", nargs="*")

    s = command("tone", "show the Bluetooth prompt tone setting, or turn it on/off", cmd_tone)
    s.add_argument("state", nargs="?", choices=["on", "off"])

    command("pair", "disconnect the audio device and put the speaker in pairing mode", cmd_pair)
    command("off", "turn the speaker off (it can only be turned on with the knob)", cmd_off)
    command("forget", "forget the saved speaker and search again next time", cmd_forget, address=False)

    s = command("probe", "safely query read-only opcodes to look for undocumented ones", cmd_probe)
    s.add_argument("--range", nargs=2, metavar=("LOW", "HIGH"),
                   help="sweep a hex opcode range instead of the curated list (e.g. 60 70)")
    s.add_argument("--i-understand-the-risk", action="store_true",
                   help="required for --range: unknown opcodes could change the speaker")
    s.add_argument("--wait", type=float, default=1.0, help="seconds to wait for each reply")

    s = command("send", "send an arbitrary command (advanced)", cmd_send)
    s.add_argument("opcode", help="opcode in hex, e.g. 61")
    s.add_argument("payload", nargs="*", help="payload bytes in hex")
    s.add_argument("--app", default="EC")
    s.add_argument("--wait", type=float, default=3.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    global _log_file
    # argparse would read "-2" as an option; accept "volume -2" by marking the end of options.
    raw = list(sys.argv[1:] if argv is None else argv)
    if len(raw) >= 2 and raw[0] == "volume" and raw[1].startswith("-") and raw[1][1:].isdigit():
        raw.insert(1, "--")
    args = build_parser().parse_args(raw)

    _log_file = open(LOG_PATH, "a", encoding="utf-8")
    out(f"\n=== {dt.datetime.now():%Y-%m-%d %H:%M:%S}  {' '.join(raw)} ===")
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # log the error so it can be shared
        out(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)
    finally:
        _log_file.close()
