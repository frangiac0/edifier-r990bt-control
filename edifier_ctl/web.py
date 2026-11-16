"""Small web server so the speaker can be controlled from a phone on the same Wi-Fi.

Every request must carry the access key that is part of the URL shown (and QR-coded)
in the desktop app, so other people on the network cannot use it.
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from . import r990bt
from .i18n import LANG, t

DEFAULT_PORT = 8765


def new_key() -> str:
    return secrets.token_urlsafe(9)


def lan_ip() -> str:
    """Best guess of this PC's address on the local network (no traffic is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class RemoteTarget:
    """What the web server can read and do. The app supplies the callables."""

    def __init__(
        self,
        get_state: Callable[[], dict],
        set_source: Callable[[int], None],
        set_volume: Callable[[int], None],
        set_eq: Callable[[int], None],
        set_keepalive: Callable[[bool, int | None], None],
        power_off: Callable[[], None],
        pair: Callable[[], None],
    ) -> None:
        self.get_state = get_state
        self.set_source = set_source
        self.set_volume = set_volume
        self.set_eq = set_eq
        self.set_keepalive = set_keepalive
        self.power_off = power_off
        self.pair = pair


class WebRemote:
    def __init__(self, target: RemoteTarget, key: str, port: int = DEFAULT_PORT, host: str = "0.0.0.0") -> None:
        self.target = target
        self.key = key
        self.port = port
        self.host = host
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://{lan_ip()}:{self.port}/?k={self.key}"

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self._server:
            return
        remote = self

        class Handler(_Handler):
            ctx = remote

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="web", daemon=True).start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


class _Handler(BaseHTTPRequestHandler):
    ctx: WebRemote
    server_version = "EdifierRemote"

    def log_message(self, *args) -> None:  # keep the console quiet
        pass

    def _authorized(self, query: dict) -> bool:
        given = self.headers.get("X-Key") or (query.get("k") or [""])[0]
        return secrets.compare_digest(given, self.ctx.key)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if not self._authorized(query):
            self._send(403, t("web_forbidden").encode(), "text/plain; charset=utf-8")
            return
        if url.path == "/":
            self._send(200, render_page().encode(), "text/html; charset=utf-8")
        elif url.path == "/api/state":
            self._json(200, self.ctx.target.get_state())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if not self._authorized(parse_qs(url.query)):
            self._json(403, {"error": "forbidden"})
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "bad request"})
            return
        tgt = self.ctx.target
        try:
            if url.path == "/api/source":
                source = int(body["source"])
                if source not in r990bt.SOURCES:
                    raise ValueError
                tgt.set_source(source)
            elif url.path == "/api/volume":
                tgt.set_volume(int(body["volume"]))
            elif url.path == "/api/eq":
                preset = int(body["eq"])
                if preset not in r990bt.EQ_PRESETS:
                    raise ValueError
                tgt.set_eq(preset)
            elif url.path == "/api/keepalive":
                level = body.get("level")
                tgt.set_keepalive(bool(body["enabled"]), int(level) if level is not None else None)
            elif url.path == "/api/power_off":
                tgt.power_off()
            elif url.path == "/api/pair":
                tgt.pair()
            else:
                self._json(404, {"error": "not found"})
                return
        except (KeyError, TypeError, ValueError):
            self._json(400, {"error": "bad request"})
            return
        self._json(200, {"ok": True})


def render_page() -> str:
    labels = {
        "input": t("input"), "volume": t("volume"), "eq": t("eq"),
        "keepalive": t("keepalive"), "keepalive_hint": t("keepalive_hint"),
        "power_off": t("power_off"), "power_off_confirm": t("power_off_confirm"),
        "pair": t("pair"), "pair_confirm": t("pair_confirm"),
        "offline": t("web_offline"),
    }
    data = {
        "sources": [[k, v] for k, v in r990bt.SOURCES.items()],
        "presets": [[k, t(v)] for k, v in r990bt.EQ_PRESETS.items()],
        "levels": [-60, -50, -40],
        "t": labels,
    }
    return PAGE.replace("__LANG__", LANG).replace("__DATA__", json.dumps(data))


PAGE = """<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Edifier R990BT</title>
<style>
:root { --bg:#f6f7f9; --card:#ffffff; --fg:#1d2129; --muted:#6b7280; --chip:#e5e7eb; --accent:#1f6feb; --danger:#c62828; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1115; --card:#181b21; --fg:#e7e9ee; --muted:#9aa1ad; --chip:#262a33; --accent:#3b82f6; --danger:#ef5350; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:440px; margin:0 auto; padding:20px 16px 40px; }
h1 { font-size:22px; margin:0; }
#status { color:var(--muted); font-size:14px; margin:4px 0 20px; min-height:20px; }
section { background:var(--card); border-radius:14px; padding:14px; margin-bottom:12px; }
h2 { font-size:12px; letter-spacing:.06em; color:var(--muted); margin:0 0 10px; font-weight:600; display:flex; justify-content:space-between; }
.row { display:flex; gap:8px; }
.row button { flex:1; }
button { font:inherit; border:0; border-radius:10px; padding:14px 8px; background:var(--chip); color:var(--fg); cursor:pointer; }
button.on { background:var(--accent); color:#fff; }
button:disabled { opacity:.45; }
input[type=range] { width:100%; accent-color:var(--accent); height:32px; }
.vol { display:flex; align-items:center; gap:10px; }
.vol button { flex:0 0 52px; font-size:20px; padding:10px 0; }
label.switch { display:flex; align-items:center; justify-content:space-between; gap:12px; }
label.switch input { width:22px; height:22px; accent-color:var(--accent); }
.hint { color:var(--muted); font-size:13px; margin:8px 0 10px; }
button.wide { width:100%; margin-bottom:12px; }
#power { width:100%; background:transparent; color:var(--danger); border:1px solid var(--danger); }
</style>
</head>
<body>
<main>
  <h1>Edifier R990BT</h1>
  <div id="status"></div>
  <section><h2 id="l-input"></h2><div class="row" id="sources"></div></section>
  <section>
    <h2><span id="l-volume"></span><span id="vol-text"></span></h2>
    <div class="vol"><button id="vdown">-</button><input type="range" id="vol" min="0" max="16" step="1"><button id="vup">+</button></div>
  </section>
  <section><h2 id="l-eq"></h2><div class="row" id="presets"></div></section>
  <section id="ka-section">
    <label class="switch"><span id="l-ka"></span><input type="checkbox" id="ka"></label>
    <div class="hint" id="l-ka-hint"></div>
    <div class="row" id="levels"></div>
  </section>
  <button id="pair" class="wide"></button>
  <button id="power"></button>
</main>
<script>
const D = __DATA__;
const KEY = new URLSearchParams(location.search).get("k") || "";
const $ = (id) => document.getElementById(id);
let state = null, dragging = false;

$("l-input").textContent = D.t.input;
$("l-volume").textContent = D.t.volume;
$("l-eq").textContent = D.t.eq;
$("l-ka").textContent = D.t.keepalive;
$("l-ka-hint").textContent = D.t.keepalive_hint;
$("power").textContent = D.t.power_off;
$("pair").textContent = D.t.pair;

function post(path, body) {
  return fetch(path + "?k=" + encodeURIComponent(KEY), {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {}),
  }).then(() => setTimeout(refresh, 300));
}
function chips(container, items, onClick) {
  return items.map(([code, label]) => {
    const b = document.createElement("button");
    b.textContent = label; b.dataset.code = code;
    b.onclick = () => onClick(code);
    $(container).appendChild(b);
    return b;
  });
}
const srcButtons = chips("sources", D.sources, (c) => post("/api/source", {source: c}));
const eqButtons = chips("presets", D.presets, (c) => post("/api/eq", {eq: c}));
const lvlButtons = chips("levels", D.levels.map((l) => [l, l + " dB"]), (l) => post("/api/keepalive", {enabled: true, level: l}));

const vol = $("vol");
vol.addEventListener("input", () => { dragging = true; $("vol-text").textContent = vol.value + " / " + vol.max; });
vol.addEventListener("change", () => { dragging = false; post("/api/volume", {volume: +vol.value}); });
$("vdown").onclick = () => state && post("/api/volume", {volume: state.volume - 1});
$("vup").onclick = () => state && post("/api/volume", {volume: state.volume + 1});
$("ka").onchange = (e) => post("/api/keepalive", {enabled: e.target.checked});
$("power").onclick = () => { if (confirm(D.t.power_off_confirm)) post("/api/power_off"); };
$("pair").onclick = () => { if (confirm(D.t.pair_confirm)) post("/api/pair"); };

function render(s) {
  state = s;
  $("status").textContent = s.status;
  const on = s.connected;
  srcButtons.forEach((b) => { b.disabled = !on; b.classList.toggle("on", +b.dataset.code === s.source); });
  eqButtons.forEach((b) => { b.disabled = !on; b.classList.toggle("on", +b.dataset.code === s.eq); });
  [vol, $("vdown"), $("vup"), $("power"), $("pair")].forEach((el) => el.disabled = !on);
  vol.max = s.volume_max;
  if (!dragging && s.volume != null) { vol.value = s.volume; $("vol-text").textContent = s.volume + " / " + s.volume_max; }
  $("ka-section").style.display = s.keepalive_available ? "" : "none";
  $("ka").checked = s.keepalive;
  lvlButtons.forEach((b) => b.classList.toggle("on", s.keepalive && +b.dataset.code === s.keepalive_level));
}
function refresh() {
  fetch("/api/state?k=" + encodeURIComponent(KEY)).then((r) => r.json()).then(render)
    .catch(() => { $("status").textContent = D.t.offline; });
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""
