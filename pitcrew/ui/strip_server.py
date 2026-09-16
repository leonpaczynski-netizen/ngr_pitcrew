"""Serves the strip page and its numbers over the local network.

**Standard library only.** One read-only page and one JSON document, polled
four times a second by a phone on the same Wi-Fi - nothing here justifies a
web framework, and a dependency the app does not already carry is one more
thing to install on the rig.

**It observes and advises, like the rest of the app** (CLAUDE.md §8): the
page has no controls and there is no route that accepts anything. `GET /`
is the page, `GET /strip/state` is the numbers, everything else is 404.

**Staleness is decided here, where the clock is.** The phone cannot compare
its clock with the PC's, so every answer carries `age_s` - how long since the
app last published - and `stale_after_s`, the one number both sides judge it
by. A page frozen on "4 laps to the stop" is the zero-that-survives-into-a-
decision failure CLAUDE.md §7 warns about; the page blanks instead.

**And it knows whether anyone is reading.** `live()` is true while a page has
polled within `LIVE_WITHIN_S`, which is what lets the ultrawide take the gaps
and laps to the stop back the moment the phone drops (his choice, 15 Sep
2026).
"""
from __future__ import annotations

import json
import math
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic

from pitcrew.diagnostics import log

DEFAULT_PORT = 8765
# The board ticks every 250 ms. Six missed ticks is not a slow tick, it is a
# feed that has stopped - and a race number held for 1.5 s is already one the
# driver may act on.
STALE_AFTER_S = 1.5
# How recently a page must have polled to count as reading. The page polls
# every 250 ms; two seconds of silence is a phone that has gone.
LIVE_WITHIN_S = 2.0

PAGE = Path(__file__).with_name("strip.html")

# **What the home screen needs, beside the page** (16 Sep 2026). Installed as
# a PWA the page had no icon at all - iOS falls back to a screenshot, which
# here is a black rectangle - so the manifest and the icons are served from
# the same folder the page is. Cut from `icon-src.png` by
# `tools/make_icons.py`; a missing one is logged and 404s rather than
# stopping the strip, which is the thing he actually races with.
STATIC = {
    "/manifest.webmanifest": ("strip.webmanifest",
                              "application/manifest+json"),
    "/icon-180.png": ("icon-180.png", "image/png"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}


class _Server(ThreadingHTTPServer):
    """**No address reuse.** `HTTPServer` turns SO_REUSEADDR on, and on
    Windows that lets a second socket bind a port something else is already
    listening on - so a taken port would "start" and the phone would be
    answered by whichever socket Windows picked. A port that is taken must
    fail to bind, and say so."""
    allow_reuse_address = False
    daemon_threads = True


def _finite(value):
    """Non-finite floats become null. JSON has no NaN, and a browser that
    refuses the document shows NO DATA for a reason nobody can see."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def lan_address() -> str | None:
    """This PC's address on the local network, for the URL he types into the
    phone. A UDP `connect` picks the outbound interface without sending a
    packet. None where there is no network to name."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))       # TEST-NET-1: never routed
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


class StripServer:
    """The page, the latest numbers, and who has asked for them."""

    def __init__(self, port: int = DEFAULT_PORT, host: str = "0.0.0.0",
                 clock=monotonic) -> None:
        self.port = port
        self.host = host
        self._clock = clock
        self._lock = threading.Lock()
        self._body: dict | None = None
        self._published_at: float | None = None
        self._last_poll: float | None = None
        self._last_client: str | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        """Bind and serve. False - logged as an error, not raised - when the
        port is taken: the strip is an output and must not cost him the app."""
        if self._httpd is not None:
            return True
        try:
            page = PAGE.read_bytes()
        except OSError as exc:
            log("ui").error("the strip page is missing (%s): %s", PAGE, exc)
            return False
        # Read once, like the page: these change when the icons are re-cut,
        # which is a restart either way.
        assets: dict[str, tuple[bytes, str]] = {}
        for route, (name, kind) in STATIC.items():
            try:
                assets[route] = (PAGE.with_name(name).read_bytes(), kind)
            except OSError as exc:
                log("ui").error("the strip is missing %s: %s - the phone's "
                                "home-screen icon will not load", name, exc)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):                           # noqa: N802
                path = self.path.split("?", 1)[0]
                if path in ("/", "/strip"):
                    self._send(200, "text/html; charset=utf-8", page)
                elif path in assets:
                    body, kind = assets[path]
                    self._send(200, kind, body)
                elif path == "/strip/state":
                    body = server._answer(self.client_address[0])
                    self._send(200, "application/json", body)
                else:
                    self._send(404, "text/plain; charset=utf-8", b"not here")

            def _send(self, code, kind, body):
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):               # four a second
                pass

        try:
            self._httpd = _Server((self.host, self.port), Handler)
        except OSError as exc:
            log("ui").error(
                "the strip page could not listen on port %d: %s - the phone "
                "will not connect until that port is free", self.port, exc)
            return False
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="strip-server", daemon=True)
        self._thread.start()
        log("ui").info("strip page serving at %s", self.url())
        return True

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def url(self) -> str:
        return f"http://{lan_address() or 'localhost'}:{self.port}/"

    # ----------------------------------------------------------------- data

    def publish(self, body: dict) -> None:
        """The latest payload from `StripComposer.compose`."""
        clean = _finite(body)
        with self._lock:
            self._body = clean
            self._published_at = self._clock()

    def live(self) -> bool:
        """A page has polled within `LIVE_WITHIN_S`."""
        with self._lock:
            last = self._last_poll
        return last is not None and self._clock() - last <= LIVE_WITHIN_S

    @property
    def last_client(self) -> str | None:
        return self._last_client

    def _answer(self, client: str) -> bytes:
        now = self._clock()
        with self._lock:
            self._last_poll = now
            self._last_client = client
            body = dict(self._body) if self._body is not None else None
            published = self._published_at
        if body is None:
            body = {"v": 1, "idle": False, "empty": True}
        body["age_s"] = None if published is None else round(now - published, 3)
        body["stale_after_s"] = STALE_AFTER_S
        return json.dumps(body, allow_nan=False).encode("utf-8")
