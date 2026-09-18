"""Serves the strip page and its numbers over the local network.

**Standard library only.** One read-only page and one JSON document, polled
four times a second by a phone on the same Wi-Fi - nothing here justifies a
web framework, and a dependency the app does not already carry is one more
thing to install on the rig.

**It observes and advises, like the rest of the app** (CLAUDE.md §8), and it
never reaches GT7. `GET /` is the phone's page, `GET /tablet` the tablet's,
`GET /<page>/state` their numbers.

**One route accepts anything, and only for the app** (17 Sep 2026): the
tablet's buttons POST to `/tablet/press` - George on or off, the beep's fuel
column, "I'm pitting this lap". A press must carry `press_key` (the code in
the settings, compared in constant time), names one of `PRESS_ACTIONS`, is
capped in size, and is handed to `on_press` - which only emits a queued Qt
signal. Everything else is 404, and a press the app is not listening for is
503 rather than a silent success.

**Staleness is decided here, where the clock is.** The phone cannot compare
its clock with the PC's, so every answer carries `age_s` - how long since the
app last published - and `stale_after_s`, the one number both sides judge it
by. A page frozen on "4 laps to the stop" is the zero-that-survives-into-a-
decision failure CLAUDE.md §7 warns about; the page blanks instead.

**And it knows whether anyone is reading.** `live()` is true while a page has
polled within `LIVE_WITHIN_S`, which is what lets the ultrawide take the gaps
and laps to the stop back the moment the phone drops (his choice, 15 Sep
2026).

**Two pages, tracked apart** (17 Sep 2026, his three-screen split): the phone
strip at `/` and the tablet's field at `/tablet`, each with its own payload,
age and liveness. One `live()` for both would hand the ultrawide's gaps to a
phone that no longer shows them.
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
# What a press may ask for, and the largest body one may send.
PRESS_ACTIONS = {"george": (True, False), "fuel": ("save", "full"),
                 "pit": (True, False)}
PRESS_MAX_BYTES = 512
# Wrong codes before presses are refused for a while. A six-digit code on a
# LAN listener is small enough to hammer, and each refusal writes a log line.
PRESS_WRONG_LIMIT = 5
PRESS_COOL_OFF_S = 30.0

PAGE = Path(__file__).with_name("strip.html")
# The pages served: the routes that draw each, its file, and where its numbers
# come from.
STRIP, TABLET = "strip", "tablet"
PAGES = {
    STRIP: (("/", "/strip"), "strip.html", "/strip/state"),
    TABLET: (("/tablet",), "tablet.html", "/tablet/state"),
}

# **What the home screen needs, beside the page** (16 Sep 2026). Installed as
# a PWA the page had no icon at all - iOS falls back to a screenshot, which
# here is a black rectangle - so the manifest and the icons are served from
# the same folder the page is. Cut from `icon-src.png` by
# `tools/make_icons.py`; a missing one is logged and 404s rather than
# stopping the strip, which is the thing he actually races with.
STATIC = {
    "/manifest.webmanifest": ("strip.webmanifest",
                              "application/manifest+json"),
    # The tablet's own, because the phone's `start_url` is "/" - installed
    # from the tablet, that manifest would launch the phone's page.
    "/tablet.webmanifest": ("tablet.webmanifest",
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
        # Per page: the latest payload, when it was published, when a page
        # last asked for it, and who asked.
        self._state = {name: {"body": None, "at": None, "poll": None,
                              "client": None} for name in PAGES}
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        # The tablet's buttons: the code a press must carry, and what is
        # called with `(action, value)` once it does. None refuses them all.
        self.press_key: str | None = None
        self.on_press = None
        self._wrong_presses = 0
        self._cool_off_until = 0.0

    # ------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        """Bind and serve. False - logged as an error, not raised - when the
        port is taken: the strip is an output and must not cost him the app."""
        if self._httpd is not None:
            return True
        # **The strip is what he races with; the tablet is not.** A missing
        # strip page refuses to start; a missing tablet page is logged and its
        # route 404s - one going wrong must not cost him the other.
        pages: dict[str, bytes] = {}
        for name, (_, filename, _) in PAGES.items():
            try:
                pages[name] = PAGE.with_name(filename).read_bytes()
            except OSError as exc:
                log("ui").error("the %s page is missing (%s): %s", name,
                                filename, exc)
                if name == STRIP:
                    return False
        routes_to_page = {route: pages[name]
                          for name, (routes, _, _) in PAGES.items()
                          if name in pages for route in routes}
        state_routes = {state: name for name, (_, _, state) in PAGES.items()}
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
                if path in routes_to_page:
                    self._send(200, "text/html; charset=utf-8",
                               routes_to_page[path])
                elif path in assets:
                    body, kind = assets[path]
                    self._send(200, kind, body)
                elif path in state_routes:
                    body = server._answer(state_routes[path],
                                          self.client_address[0])
                    self._send(200, "application/json", body)
                else:
                    self._send(404, "text/plain; charset=utf-8", b"not here")

            def do_POST(self):                          # noqa: N802
                path = self.path.split("?", 1)[0]
                if path != "/tablet/press":
                    self._send(404, "text/plain; charset=utf-8", b"not here")
                    return
                code, answer = server._press(self.headers, self.rfile)
                self._send(code, "application/json",
                           json.dumps(answer).encode("utf-8"))

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

    def publish(self, body: dict, page: str = STRIP) -> None:
        """The latest payload for one page - the strip composer's by default,
        `ui/tablet.compose`'s for the tablet."""
        clean = _finite(body)
        with self._lock:
            self._state[page].update(body=clean, at=self._clock())

    def live(self, page: str = STRIP) -> bool:
        """That page has polled within `LIVE_WITHIN_S`."""
        with self._lock:
            last = self._state[page]["poll"]
        return last is not None and self._clock() - last <= LIVE_WITHIN_S

    def last_client_of(self, page: str = STRIP) -> str | None:
        return self._state[page]["client"]

    @property
    def last_client(self) -> str | None:
        return self.last_client_of(STRIP)

    def _press(self, headers, stream) -> tuple[int, dict]:
        """One press from the tablet: `(status, answer)`. Request thread.

        Refused, and logged, for a wrong code, an unknown action or value, or
        a body too big to be a press. **Accepted is not done**: the answer says
        the press was handed over, and the page reads the result back off the
        state it polls, so a press that changed nothing is visible as such.
        """
        import hmac

        if self._clock() < self._cool_off_until:
            return 429, {"ok": False, "why": "too many wrong codes"}
        # **A press says it is one.** Without this a `text/plain` body is a
        # CORS simple request, so any page open in a browser on his network
        # could post one without a preflight.
        kind = (headers.get("Content-Type") or "").split(";")[0].strip()
        if kind != "application/json":
            return 415, {"ok": False, "why": "not a press"}
        try:
            length = int(headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 < length <= PRESS_MAX_BYTES:
            return 400, {"ok": False, "why": "not a press"}
        try:
            press = json.loads(stream.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return 400, {"ok": False, "why": "not a press"}
        if not isinstance(press, dict):
            return 400, {"ok": False, "why": "not a press"}
        key = self.press_key
        if not key or not hmac.compare_digest(str(press.get("key", "")), key):
            self._wrong_presses += 1
            if self._wrong_presses >= PRESS_WRONG_LIMIT:
                self._cool_off_until = self._clock() + PRESS_COOL_OFF_S
                self._wrong_presses = 0
                log("ui").warning("tablet presses refused for %.0f s: %d wrong "
                                  "codes", PRESS_COOL_OFF_S, PRESS_WRONG_LIMIT)
            else:
                log("ui").warning("tablet press refused: wrong code")
            return 403, {"ok": False, "why": "wrong code"}
        self._wrong_presses = 0
        action, value = press.get("action"), press.get("value")
        if action not in PRESS_ACTIONS or value not in PRESS_ACTIONS[action]:
            return 400, {"ok": False, "why": "unknown press"}
        if self.on_press is None:
            return 503, {"ok": False, "why": "the app is not taking presses"}
        try:
            self.on_press(action, value)
        except Exception as exc:                            # noqa: BLE001
            # The app went away under a press in flight. A 500 to the tablet,
            # never an exception out of a request thread.
            log("ui").warning("a tablet press could not be handed over: %s",
                              exc)
            return 500, {"ok": False, "why": "the app did not take it"}
        return 202, {"ok": True}

    def _answer(self, page: str, client: str) -> bytes:
        now = self._clock()
        with self._lock:
            state = self._state[page]
            state.update(poll=now, client=client)
            body = dict(state["body"]) if state["body"] is not None else None
            published = state["at"]
        if body is None:
            body = {"v": 1, "idle": False, "empty": True}
        body["age_s"] = None if published is None else round(now - published, 3)
        body["stale_after_s"] = STALE_AFTER_S
        return json.dumps(body, allow_nan=False).encode("utf-8")
