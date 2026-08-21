"""Reading GT7's tyre-wear gauge off the OBS capture, live, once a lap.

**GT7 broadcasts no tyre wear channel in any packet format.** `CLAUDE.md` §3.3
calls that the single most consequential fact in the document, and the app's
answer has been to model wear and ask the driver to corroborate it from the
in-game gauge. He reads it once or twice a stint at best - across five sessions
running, including the two that mattered most, he read it zero times.

**The gauge is on screen for the whole race and OBS is already pointed at it.**
`tools/read_hud_wear.py` proved the transcription against a recorded file and
was verified to 0.5% across two independent stints. This is the same reading,
taken at each lap crossing instead of afterwards.

### What was measured before this was written

On 21 Aug 2026, against the live capture:

* **Round trip 520 ms, and about 537 ms of OBS CPU per screenshot.** At one per
  90-second lap that is **0.6% of one core**, which is affordable. At one per
  second it is 51% of a core, which is not - so this samples on the crossing and
  nowhere else.
* **The canvas is 1720x916, exactly the geometry `LAYOUT_1720x916` was
  calibrated on.** Screenshot the SCENE, not the `PS5` source: the scene renders
  at canvas resolution, the source at the card's own, and every calibrated
  constant would need re-probing.
* **A 1720x916 PNG is about 2 MB and `websockets` caps frames at 1 MB.** Left at
  the default it does not truncate, it closes the socket with a 1009 - which
  mid-race reads as "OBS went away" rather than "the frame was large".
* **A paused frame is dimmed and desaturated by about 45%**: every bar peaks at
  137 where the reader needs 150 for white and 110 for red, so all four read
  null. That is the correct refusal, and the rule it gives is
  **detect the dim and skip the frame - never relax the thresholds to meet it.**
  Relaxing them lets a dimmed frame produce a number, and a wrong wear figure is
  far worse than a missing one.

### What this deliberately is not

**It never touches the race path.** Every grab happens on a worker thread, the
queue is one deep, and any failure at all - OBS shut, socket closed, canvas the
wrong size, gauge unreadable - produces a logged reason and nothing else. A
perception layer that can stall a lap handler is worse than no perception layer.

**In VR it does not work yet, and it says so rather than guessing.** GT7 draws
its HUD on the car's dashboard in 3D there, so the gauge moves with head
position - measured at roughly 200 px of drift - and a fixed rectangle tracks
nothing. The flat-screen path is proven; the VR locator is separate work.
"""
from __future__ import annotations

import base64
import hashlib
import json
import queue
import threading
from dataclasses import dataclass

from pitcrew.diagnostics import log

# The calibrated gauge, in canvas pixels. Four vertical bars flanking the car
# icon in the HUD's bottom-left cluster; each fills red from the top as the
# tyre wears and the remainder stays white.
LAYOUT_1720x916 = {
    "fl": (339, 348, 800, 829),
    "rl": (339, 348, 846, 875),
    "fr": (411, 420, 800, 829),
    "rr": (411, 420, 846, 875),
}
CANVAS = (1720, 916)

# A bar reads red where the channel separation is unmistakable and white where
# every channel is high. Anything else - the dark HUD backing, bloom from
# scenery behind a translucent panel - is neither.
RED_MIN, RED_SEPARATION, WHITE_MIN = 110, 55, 150
# A bar that cannot show at least this many classified rows is not read at all
# rather than guessed. The bar is 30 px tall.
MIN_CLASSIFIED_ROWS = 20
# Below this peak the frame is dimmed - a pause menu, a transition, a replay
# overlay - and no threshold in it means what it usually means. Measured: a
# paused frame peaks at 137, a live one at 255.
LIVE_PEAK = 165

# Frames larger than the library's default cap; see the module docstring.
MAX_FRAME_BYTES = 16 * 1024 * 1024
CONNECT_TIMEOUT_S = 4.0
# Consecutive failures before the sampler stands down for the session. It says
# so once and stops trying: an error repeated every lap is noise, and by then
# something needs a human anyway.
MAX_CONSECUTIVE_FAILURES = 5


@dataclass(frozen=True)
class Reading:
    """A gauge reading, or an honest account of why there is not one."""

    wear: dict[str, float | None] | None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.wear is not None and any(
            v is not None for v in self.wear.values())


def read_gauge(png: bytes, layout: dict | None = None) -> Reading:
    """Transcribe the four bars from a canvas screenshot.

    Pure: bytes in, a reading out. Everything that can go wrong returns a
    `Reading` with a reason rather than raising, because the caller is a lap
    handler and the lap matters more than the gauge.
    """
    layout = layout or LAYOUT_1720x916
    try:
        import io

        import numpy as np
        from PIL import Image

        frame = np.array(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    except Exception as exc:                                 # noqa: BLE001
        return Reading(None, f"frame could not be decoded: {exc}")

    height, width = frame.shape[0], frame.shape[1]
    if (width, height) != CANVAS:
        # **Refused, not rescaled.** The constants are pixel positions on this
        # canvas; on any other they point somewhere else entirely, and a
        # confident reading of the wrong rectangle is the failure this whole
        # module exists to avoid.
        return Reading(None, f"canvas is {width}x{height}, not "
                             f"{CANVAS[0]}x{CANVAS[1]} - the gauge layout is "
                             f"calibrated to that geometry and cannot be scaled")

    peak = max(int(frame[y0:y1 + 1, x0:x1 + 1].max())
               for (x0, x1, y0, y1) in layout.values())
    if peak <= LIVE_PEAK:
        return Reading(None, f"frame is dimmed (gauge peaks at {peak}) - paused, "
                             f"in a menu, or mid-transition")

    out: dict[str, float | None] = {}
    for corner, (x0, x1, y0, y1) in layout.items():
        bar = frame[y0:y1 + 1, x0:x1 + 1]
        r, g, b = bar[..., 0], bar[..., 1], bar[..., 2]
        red = (r > RED_MIN) & (r - g > RED_SEPARATION) & (r - b > RED_SEPARATION)
        white = (r > WHITE_MIN) & (g > WHITE_MIN) & (b > WHITE_MIN)
        n_red = int((red.mean(axis=1) > 0.5).sum())
        n_white = int((white.mean(axis=1) > 0.5).sum())
        total = n_red + n_white
        out[corner] = n_red / total if total >= MIN_CLASSIFIED_ROWS else None

    if all(v is None for v in out.values()):
        return Reading(out, "no bar showed enough classified rows to read")
    return Reading(out)


class ObsSource:
    """One canvas screenshot per call, over obs-websocket 5.x.

    Opened and closed per grab. A long-lived socket would be cheaper and would
    also be one more thing holding state across a session that already has a
    telemetry stream, a haptics engine and a serial port to keep alive.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4455,
                 password: str = "") -> None:
        self.host, self.port, self.password = host, port, password

    def _connected(self, work):
        """Open, authenticate, run `work(request)`, close. Never raises."""
        try:
            from websockets.sync.client import connect
        except ImportError:
            return None, "the websockets package is not installed"
        try:
            with connect(f"ws://{self.host}:{self.port}",
                         open_timeout=CONNECT_TIMEOUT_S,
                         close_timeout=CONNECT_TIMEOUT_S,
                         max_size=MAX_FRAME_BYTES) as ws:
                self._identify(ws, json.loads(ws.recv(timeout=CONNECT_TIMEOUT_S)))
                return work(lambda kind, data=None: self._request(ws, kind, data)), None
        except Exception as exc:                             # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"

    def grab(self) -> tuple[bytes | None, str | None]:
        def work(request):
            scene = request("GetCurrentProgramScene")
            name = (scene.get("sceneName")
                    or scene.get("currentProgramSceneName"))
            if not name:
                raise RuntimeError("OBS did not name a program scene")
            shot = request("GetSourceScreenshot", {
                "sourceName": name, "imageFormat": "png",
                "imageWidth": CANVAS[0], "imageHeight": CANVAS[1]})
            data = shot.get("imageData") or ""
            if "," not in data:
                raise RuntimeError("OBS returned no image data")
            return base64.b64decode(data.split(",", 1)[1])

        return self._connected(work)

    def recording(self) -> tuple[bool | None, str | None]:
        got, why = self._connected(lambda request: request("GetRecordStatus"))
        if got is None:
            return None, why
        return bool(got.get("outputActive")), None

    def start_recording(self) -> tuple[bool | None, str | None]:
        """Begin recording, unless OBS is already doing so.

        **Returns False when it was already running**, which is not a failure
        and is the signal the caller needs: a recording this app did not start
        is not a recording this app may stop.
        """
        def work(request):
            if bool(request("GetRecordStatus").get("outputActive")):
                return False
            request("StartRecord")
            return True

        return self._connected(work)

    def stop_recording(self) -> tuple[str | None, str | None]:
        """Stop, and return the file OBS wrote."""
        def work(request):
            if not bool(request("GetRecordStatus").get("outputActive")):
                return None
            return (request("StopRecord") or {}).get("outputPath")

        return self._connected(work)

    def _identify(self, ws, hello: dict) -> None:
        payload = {"rpcVersion": 1}
        auth = (hello.get("d") or {}).get("authentication")
        if auth:
            secret = base64.b64encode(hashlib.sha256(
                (self.password + auth["salt"]).encode()).digest()).decode()
            payload["authentication"] = base64.b64encode(hashlib.sha256(
                (secret + auth["challenge"]).encode()).digest()).decode()
        ws.send(json.dumps({"op": 1, "d": payload}))
        got = json.loads(ws.recv(timeout=CONNECT_TIMEOUT_S))
        if got.get("op") != 2:
            raise RuntimeError(f"OBS refused the connection: {got}")

    def _request(self, ws, kind: str, data: dict | None = None) -> dict:
        ws.send(json.dumps({"op": 6, "d": {
            "requestType": kind, "requestId": kind, "requestData": data or {}}}))
        while True:
            got = json.loads(ws.recv(timeout=CONNECT_TIMEOUT_S))
            if got.get("op") == 7 and got["d"].get("requestId") == kind:
                status = got["d"]["requestStatus"]
                if not status.get("result"):
                    raise RuntimeError(f"{kind} failed: {status}")
                return got["d"].get("responseData") or {}


class LiveWearSampler:
    """One gauge reading per lap, off the race path.

    `request` is called from the lap handler and returns immediately. The grab,
    the decode and the write all happen on a worker thread, and the queue holds
    **one** lap: if a reading is still in flight when the next crossing lands,
    the older request is dropped. A wear figure filed against the wrong lap is
    worse than a gap, and a queue that grows is a queue that is already wrong.
    """

    def __init__(self, source, write, *, on_status=None) -> None:
        self._source = source
        self._write = write
        self._status = on_status
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._failures = 0
        self.stood_down = False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hud-wear",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)

    def request(self, lap_id: int) -> None:
        """Ask for a reading. Never blocks, never raises, may be dropped."""
        if self.stood_down or self._thread is None:
            return
        try:
            self._queue.put_nowait(lap_id)
        except queue.Full:
            # The previous lap's reading has not finished. Drop the older one:
            # the newer crossing is the one whose wear is still true.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(lap_id)
            except (queue.Empty, queue.Full):
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                lap_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if lap_id is None:
                return
            try:
                self._sample(lap_id)
            except Exception as exc:                         # noqa: BLE001
                # Nothing here may reach the caller. The lap is recorded
                # whatever the gauge does.
                log(f"hud-wear: unhandled {type(exc).__name__}: {exc}")

    def _sample(self, lap_id: int) -> None:
        png, why = self._source.grab()
        if png is None:
            self._failed(f"lap {lap_id}: {why}")
            return
        reading = read_gauge(png)
        if not reading.ok:
            # A dimmed or unreadable frame is not a connection failure - it is
            # a normal thing that happens when the game is paused - so it does
            # not count toward standing down.
            log(f"hud-wear: lap {lap_id}: {reading.reason}")
            return
        self._failures = 0
        self._write(lap_id, reading.wear)
        worst = max((v for v in reading.wear.values() if v is not None),
                    default=None)
        log(f"hud-wear: lap {lap_id}: "
            + ", ".join(f"{k.upper()} "
                        + ("--" if v is None else f"{v * 100:.0f}%")
                        for k, v in sorted(reading.wear.items()))
            + (f" (worst {worst * 100:.0f}%)" if worst is not None else ""))
        if self._status:
            self._status(reading)

    def _failed(self, message: str) -> None:
        self._failures += 1
        log(f"hud-wear: {message}")
        if self._failures >= MAX_CONSECUTIVE_FAILURES:
            self.stood_down = True
            log(f"hud-wear: stood down after {self._failures} consecutive "
                f"failures - it will not be retried this session")
