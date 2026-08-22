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
import time
from dataclasses import dataclass

from pitcrew.diagnostics import log

# **`log` RETURNS a logger; it does not take a message.** Every diagnostic
# in this module used to call `log(f"hud-wear: ...")`, which built a logger
# NAMED after the message and emitted nothing - so the sampler could fail on
# every sample of every lap and say so eight different ways, in silence.
# That is the failure mode CLAUDE.md 7 exists to forbid: a capture that
# degrades quietly instead of loudly. Bind it once, here.
_log = log("hud")

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
# A drop this large between readings is a fresh set, not wear going
# backwards. Wear is monotonic within a stint and the only thing that
# resets it is a tyre change - the gauge snapping back to white is a
# cleaner detector than anything the telemetry offers.
FRESH_SET_DROP = 0.25
# How far past its own interval a held reading may be and still be the
# lap reading. Wider than one interval so a single missed tick does not
# force a grab on the crossing, and far short of a lap so a stale number
# can never be filed as a fresh one.
STALE_MARGIN_S = 3.0
# How long the worker waits on the queue before looking round. Short
# enough that stop() is prompt; the free-run interval is enforced against
# the clock, so this does not set the sample rate.
QUEUE_WAIT_S = 0.5
# Free-run failures are logged no more often than this.
FREE_RUN_LOG_SPACING_S = 30.0
# Sentinel: no crossing asked, take a free-running sample.
_FREE_RUN = object()


@dataclass(frozen=True)
class Reading:
    """A gauge reading, or an honest account of why there is not one."""

    wear: dict[str, float | None] | None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.wear is not None and any(
            v is not None for v in self.wear.values())


def read_gauge(png, layout: dict | None = None) -> Reading:
    """Transcribe the four bars from a canvas screenshot.

    Pure: bytes in, a reading out. Everything that can go wrong returns a
    `Reading` with a reason rather than raising, because the caller is a lap
    handler and the lap matters more than the gauge.
    """
    layout = layout or LAYOUT_1720x916

    if isinstance(png, CropFrame):
        # **A crop, whose geometry was verified where it was cut.** The source
        # measured the canvas it took this from; if that was not the calibrated
        # one the crop is of the wrong rectangle and the refusal is the same
        # refusal, made one step earlier.
        if tuple(png.canvas) != CANVAS:
            return Reading(None, f"canvas is {png.canvas[0]}x{png.canvas[1]}, "
                                 f"not {CANVAS[0]}x{CANVAS[1]} - the gauge "
                                 f"layout is calibrated to that geometry and "
                                 f"cannot be scaled")
        import numpy as np

        frame = np.asarray(png.pixels).astype(int)
        ox, oy = png.origin
        layout = {corner: (x0 - ox, x1 - ox, y0 - oy, y1 - oy)
                  for corner, (x0, x1, y0, y1) in layout.items()}
        bx0, by0, bx1, by1 = layout_bounds(layout)
        if (bx0 < 0 or by0 < 0
                or by1 >= frame.shape[0] or bx1 >= frame.shape[1]):
            # The crop does not contain the gauge. Never read partially: a bar
            # clipped at the edge reads as a bar that is short of white.
            return Reading(None, f"crop at {png.origin} is "
                                 f"{frame.shape[1]}x{frame.shape[0]} and does "
                                 f"not contain the gauge")
    else:
        try:
            import io

            import numpy as np
            from PIL import Image

            frame = np.array(
                Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
        except Exception as exc:                             # noqa: BLE001
            return Reading(None, f"frame could not be decoded: {exc}")

        height, width = frame.shape[0], frame.shape[1]
        if (width, height) != CANVAS:
            # **Refused, not rescaled.** The constants are pixel positions on
            # this canvas; on any other they point somewhere else entirely, and
            # a confident reading of the wrong rectangle is the failure this
            # whole module exists to avoid.
            return Reading(None, f"canvas is {width}x{height}, not "
                                 f"{CANVAS[0]}x{CANVAS[1]} - the gauge layout "
                                 f"is calibrated to that geometry and cannot "
                                 f"be scaled")

    peak = max(int(frame[y0:y1 + 1, x0:x1 + 1].max())
               for (x0, x1, y0, y1) in layout.values())
    if peak <= LIVE_PEAK:
        # **Before calling it dimmed, check whether the gauge simply is not
        # there.** In VR it is drawn on the dashboard and moves with head
        # position, so the calibrated rectangle is looking at trim. A located
        # gauge is read; a genuinely dark frame still says so.
        # **Only a full canvas can be searched.** The locator exists because
        # the gauge moves; a crop is a bet that it did not, so on a crop there
        # is nowhere to look and the dim verdict stands.
        moved = None if isinstance(png, CropFrame) else locate_gauge(frame)
        if moved is not None:
            return _read_bars(frame, moved, quantisation_note=True)
        return Reading(None, f"frame is dimmed (gauge peaks at {peak}) - paused, "
                             f"in a menu, or the HUD is drawn in 3D and the "
                             f"gauge is not where the flat layout expects it")

    return _read_bars(frame, layout)


def _read_bars(frame, layout: dict, *,
               quantisation_note: bool = False) -> Reading:
    """Red rows over classified rows, per bar. The transcription itself."""
    out: dict[str, float | None] = {}
    shortest = None
    for corner, (x0, x1, y0, y1) in layout.items():
        bar = frame[y0:y1 + 1, x0:x1 + 1]
        rows = bar.shape[0]
        shortest = rows if shortest is None else min(shortest, rows)
        r, g, b = bar[..., 0], bar[..., 1], bar[..., 2]
        # A located gauge is dimmer and smaller, so it is classified on the
        # looser thresholds it was found with. The fixed layout keeps the
        # strict ones, which is what the 0.5% verification was taken on.
        if quantisation_note:
            red = ((r > VR_RED_MIN) & (r - g > VR_RED_SEPARATION)
                   & (r - b > VR_RED_SEPARATION))
            white = ((r > VR_WHITE_MIN) & (g > VR_WHITE_MIN)
                     & (b > VR_WHITE_MIN))
            floor = max(4, rows // 2)
        else:
            red = ((r > RED_MIN) & (r - g > RED_SEPARATION)
                   & (r - b > RED_SEPARATION))
            white = (r > WHITE_MIN) & (g > WHITE_MIN) & (b > WHITE_MIN)
            floor = MIN_CLASSIFIED_ROWS
        n_red = int((red.mean(axis=1) > 0.5).sum())
        n_white = int((white.mean(axis=1) > 0.5).sum())
        total = n_red + n_white
        out[corner] = n_red / total if total >= floor else None

    if all(v is None for v in out.values()):
        return Reading(out, "no bar showed enough classified rows to read")
    if quantisation_note and shortest:
        # **Said, because it changes what the number is worth.** One pixel of
        # an 18 px bar is 5.6% of tyre life - about a lap at Monza - against
        # 3.3% on the flat HUD's 30 px.
        return Reading(out, f"located on a moving HUD; bars are {shortest} px, "
                            f"so one pixel is {100 / shortest:.1f}% of tyre "
                            f"life - fit a slope across the stint rather than "
                            f"trusting one reading")
    return Reading(out)


# --- finding the gauge when it will not hold still -------------------------
#
# **In VR the HUD is drawn on the car's dashboard in 3D**, so it translates and
# skews with head position: measured across one 48-second recording, the
# cluster moved about 200 px horizontally and 95 px vertically during ordinary
# driving. A fixed rectangle tracks nothing there.
#
# It is also smaller. The bars are 18-20 px tall against 30 on the flat HUD, so
# one pixel is about 5.6% of tyre life - roughly a whole lap at Monza, against
# 3.3% flat. **That quantisation is fundamental and the locator cannot improve
# it**; what makes it survivable is the same discipline the offline tool
# already uses, fitting a slope across a stint rather than trusting any single
# reading.

# A bar is a short vertical strip: red at the top, white below it. These bound
# what counts as one, and they are deliberately loose on position and tight on
# shape - position is the thing that moves.
VR_BAR_MIN_H, VR_BAR_MAX_H = 8, 40
VR_BAR_MIN_W, VR_BAR_MAX_W = 3, 16
# The four bars sit either side of a small car icon. Two x positions, two y
# bands, all within this of each other.
VR_CLUSTER_W, VR_CLUSTER_H = 130, 90
# Looser than the flat thresholds, because the dashboard is dim and the panel
# is lit by the scene rather than composited over it.
VR_RED_MIN, VR_RED_SEPARATION, VR_WHITE_MIN = 95, 40, 135


def _vr_masks(frame):
    import numpy as np

    r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
    red = (r > VR_RED_MIN) & (r - g > VR_RED_SEPARATION) &           (r - b > VR_RED_SEPARATION)
    white = ((r > VR_WHITE_MIN) & (g > VR_WHITE_MIN) & (b > VR_WHITE_MIN)
             & (abs(r - g) < 45) & (abs(g - b) < 45))
    return red, white, np.asarray(red | white)


def locate_gauge(frame) -> dict | None:
    """Find the four bars in a frame that will not hold them still.

    Returns a layout in the same shape as `LAYOUT_1720x916` - `{corner:
    (x0, x1, y0, y1)}` - or None where four bars in a 2x2 could not be found.

    **None is the expected answer much of the time** and is not a failure: the
    panel is often edge-on, out of frame, or behind the wheel. Sampling more
    often costs nothing but a screenshot, and a stint's slope survives gaps.
    """
    import numpy as np

    red, white, solid = _vr_masks(frame)
    height, width = solid.shape
    found = []
    for x in range(width):
        column = solid[:, x]
        if not column.any():
            continue
        idx = np.where(column)[0]
        for run in np.split(idx, np.where(np.diff(idx) > 1)[0] + 1):
            if not (VR_BAR_MIN_H <= len(run) <= VR_BAR_MAX_H):
                continue
            y0, y1 = int(run[0]), int(run[-1])
            third = max(1, (y1 - y0) // 3)
            if (red[y0:y0 + third + 1, x].mean() > 0.5
                    and white[y1 - third:y1 + 1, x].mean() > 0.7):
                found.append((x, y0, y1))
    if len(found) < VR_BAR_MIN_W * 4:
        return None

    # Adjacent columns of similar extent are one bar.
    #
    # **Several bars are open at once, and that is the whole difficulty.** A
    # single linear scan cannot do this. Sorting by column interleaves the top
    # and bottom bar of the same column, which share an x; sorting by row
    # breaks a bar apart the moment perspective drifts its rows across its own
    # width, which is exactly what a HUD painted on a dashboard does. Measured
    # both ways on one real recording: column-first read a fifth of the frames,
    # row-first read a fourteenth.
    #
    # So every open bar is kept and each run joins the one it continues.
    open_bars: list[list] = []
    for item in sorted(found, key=lambda c: (c[0], c[1])):
        for bar in open_bars:
            last = bar[-1]
            if item[0] - last[0] <= 1 and abs(item[1] - last[1]) <= 4:
                bar.append(item)
                break
        else:
            open_bars.append([item])

    shaped = []
    for group in open_bars:
        if not VR_BAR_MIN_W <= len(group) <= VR_BAR_MAX_W:
            continue
        xs = [c[0] for c in group]
        shaped.append((min(xs), max(xs),
                       int(np.median([c[1] for c in group])),
                       int(np.median([c[2] for c in group]))))
    if len(shaped) < 4:
        return None

    # Four of them, close together, in two columns and two rows. Anything
    # looser finds brake lights and kerbs.
    best = None
    for anchor in shaped:
        near = [b for b in shaped
                if abs(b[0] - anchor[0]) < VR_CLUSTER_W
                and abs(b[2] - anchor[2]) < VR_CLUSTER_H]
        if len(near) < 4:
            continue
        near = sorted(near, key=lambda b: (b[0], b[2]))[:4]
        spread = max(b[1] for b in near) - min(b[0] for b in near)
        if best is None or spread < best[0]:
            best = (spread, near)
    if best is None:
        return None

    quad = best[1]
    left = sorted(quad[:2], key=lambda b: b[2])
    right = sorted(quad[2:], key=lambda b: b[2])
    if len(left) != 2 or len(right) != 2:
        return None
    # Left column is the near side, top of each column is the front axle -
    # the same arrangement the flat HUD uses.
    return {"fl": left[0], "rl": left[1], "fr": right[0], "rr": right[1]}


@dataclass(frozen=True)
class CropFrame:
    """A gauge-sized crop of the canvas, with the origin it was cut from.

    **The point of this type is that the geometry was checked at the source
    rather than by counting pixels here.** `read_gauge` refuses a PNG whose
    canvas is not 1720x916 because the layout constants are pixel positions on
    that canvas and mean nothing on another. A crop cannot be checked that way
    - it is 82x76 by construction - so the source that cut it carries the
    canvas it measured, and it is that figure which is verified.

    `pixels` is RGB, `origin` is the crop's top-left in canvas coordinates.
    """

    pixels: object
    origin: tuple[int, int]
    canvas: tuple[int, int]


def layout_bounds(layout: dict) -> tuple[int, int, int, int]:
    """The bounding box of a layout, as (x0, y0, x1, y1) inclusive."""
    xs = [v[0] for v in layout.values()] + [v[1] for v in layout.values()]
    ys = [v[2] for v in layout.values()] + [v[3] for v in layout.values()]
    return min(xs), min(ys), max(xs), max(ys)


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


# --- the local screen, at a five-hundredth of the cost --------------------
#
# **Measured 22 Aug 2026, on this PC (Core Ultra 5 125U, 2560x1440):**
#
#   mss grab of the 82x76 gauge region     wall 16.68 ms   CPU  0.21 ms
#   mss grab of the full 2560x1440 screen  wall 33.14 ms   CPU 12.50 ms
#   PIL ImageGrab, same 82x76 bbox         wall 50.07 ms   CPU 23.05 ms
#   transcribing the four bars                             CPU  0.10 ms
#
# against `ObsSource`'s measured **537 ms of OBS CPU per screenshot**. The
# whole difference is what is being asked for: OBS renders, PNG-encodes and
# base64s a 1720x916 canvas over a socket, where this copies 6,232 pixels.
#
# Three things that are not obvious in those numbers:
#
# * **The 16.68 ms wall time is vsync, not work.** It is 1/60 s to three
#   decimals - the grab blocks on the compositor - and the CPU actually burned
#   is 0.21 ms. It therefore belongs on the worker thread, which is where the
#   sampler already puts it.
# * **Crop at capture, never after.** Grabbing the screen and slicing in numpy
#   costs 12.50 ms against 0.21; PIL costs 23.05 ms for the identical 82x76
#   output because it copies the whole screen regardless of the bbox. The
#   cheap path is the one that asks the OS for the rectangle.
# * **The cost is flat in area** - 600x200 measured 0.52 ms against 82x76's
#   0.21 - so it is the round trip that is paid for, not the pixels.
#
# **What it costs to be right: the pixels have to be on screen.** The socket
# does not care whether OBS is visible, minimised or behind the app; this
# reads what the monitor shows. That is the trade, and it is why `ObsSource`
# stays and stays the default.

# OBS's projector windows, whose client area IS the canvas - which is what
# makes this self-locating rather than a rectangle he has to calibrate.
PROJECTOR_TITLES = ("windowed projector (program)",
                    "windowed projector (preview)",
                    "fullscreen projector (program)")


class ScreenSource:
    """The gauge region, read straight off the desktop.

    Point OBS at a **Windowed Projector (Program)** and size it 1:1 - right
    click the preview, Windowed Projector, then size the window until its
    client area is the canvas. This finds that window by title, so nothing has
    to be calibrated and moving it costs nothing.

    Returns a `CropFrame`, never PNG bytes: there is no encode step here and
    adding one would put back most of what this exists to remove.
    """

    def __init__(self, title_hint: str = "") -> None:
        # A hint narrows the search where several projectors are open. Empty
        # means "any program projector", which is the normal case.
        self.title_hint = title_hint.strip().lower()

    def _window(self):
        """(hwnd, title) of the projector, or (None, reason)."""
        try:
            import win32gui
        except ImportError:
            return None, "pywin32 is not installed"
        hits = []

        def visit(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            low = title.lower()
            if not any(name in low for name in PROJECTOR_TITLES):
                return
            if self.title_hint and self.title_hint not in low:
                return
            hits.append((hwnd, title))

        try:
            win32gui.EnumWindows(visit, None)
        except Exception as exc:                             # noqa: BLE001
            return None, f"could not enumerate windows: {type(exc).__name__}"
        if not hits:
            return None, ("no OBS projector window is open - right click the "
                          "preview in OBS and choose Windowed Projector "
                          "(Program)")
        # **The first, and it is said when there are others.** Two projectors
        # showing different scenes would otherwise be chosen between silently.
        if len(hits) > 1:
            _log.info(f"hud-wear: {len(hits)} projector windows open, using "
                f"{hits[0][1]!r}")
        return hits[0], None

    def grab(self):
        """(CropFrame, None) or (None, reason). Never raises."""
        found, why = self._window()
        if found is None:
            return None, why
        hwnd, title = found
        try:
            import win32gui

            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            ox, oy = win32gui.ClientToScreen(hwnd, (left, top))
        except Exception as exc:                             # noqa: BLE001
            return None, f"{title!r}: {type(exc).__name__}: {exc}"

        width, height = right - left, bottom - top
        if (width, height) != CANVAS:
            # **Refused, not rescaled**, for the reason `read_gauge` refuses a
            # PNG of the wrong size: a scaled projector moves every calibrated
            # pixel. Resizing the window is a two-second fix; guessing at a
            # scale factor is a wrong wear number.
            return None, (f"{title!r} client area is {width}x{height}, not "
                          f"{CANVAS[0]}x{CANVAS[1]} - resize the projector to "
                          f"the canvas, or use the OBS source instead")

        gx0, gy0, gx1, gy1 = layout_bounds(LAYOUT_1720x916)
        try:
            import mss
            import numpy as np
        except ImportError as exc:
            return None, f"{exc.name} is not installed"
        try:
            with mss.mss() as sct:
                shot = sct.grab({"left": ox + gx0, "top": oy + gy0,
                                 "width": gx1 - gx0 + 1,
                                 "height": gy1 - gy0 + 1})
            # mss hands back BGRA; the reader wants RGB.
            pixels = np.asarray(shot)[..., 2::-1]
        except Exception as exc:                             # noqa: BLE001
            return None, f"screen grab failed: {type(exc).__name__}: {exc}"
        return CropFrame(pixels=pixels, origin=(gx0, gy0), canvas=CANVAS), None


class LiveWearSampler:
    """Gauge readings off the race path, filed one per lap.

    `request` is called from the lap handler and returns immediately. The grab,
    the decode and the write all happen on a worker thread, and the queue holds
    **one** lap: if a reading is still in flight when the next crossing lands,
    the older request is dropped. A wear figure filed against the wrong lap is
    worse than a gap, and a queue that grows is a queue that is already wrong.

    ### Free-running, where the frames are cheap enough for it

    With `interval_s` set the worker also samples on its own between crossings,
    and a crossing then files **the last good reading taken before it** rather
    than grabbing afresh. That is not a new rule - it is the one
    `tools/read_hud_wear.py::attach` already applies to a recorded race, for
    the same reason: the gauge at the line is what that lap left the tyre at,
    and a sample taken after the crossing belongs to the next lap.

    Two things it buys, and one it does not:

    * **A paused or dimmed frame at the crossing no longer costs the lap.** The
      reading from a few seconds earlier stands in, and on a quantised gauge
      those are usually the same number anyway.
    * **A stint gets a series instead of a point.** The advice above for a
      30 px bar is to fit a slope across the stint rather than trust any single
      reading; at one sample every two seconds there are hundreds to fit rather
      than the twenty-odd a race has laps.
    * **It does not make a single reading finer.** One pixel is 3.3% of tyre
      life whatever the rate. Sampling faster pins the step transitions, which
      tightens the slope; it does not subdivide a step.

    `interval_s = 0` keeps the original behaviour exactly: nothing is sampled
    until a crossing asks for it.

    **Only a crossing failure counts toward standing down.** A free-run grab
    failing every two seconds would exhaust the budget in ten and take the
    whole session gauge with it - and a projector window shut for a minute is
    not the same event as the gauge being unreadable at the line.
    """

    def __init__(self, source, write, *, on_status=None,
                 interval_s: float = 0.0) -> None:
        self._source = source
        self._write = write
        self._status = on_status
        self._interval_s = max(0.0, float(interval_s))
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._failures = 0
        self.stood_down = False
        # The most recent good reading and when it was taken. Written and read
        # on the worker thread only.
        self._latest: tuple[float, Reading] | None = None
        # Every good reading this stint, for the slope fit. Cleared on a fresh
        # set, the same way the offline tool splits stints.
        self.series: list[tuple[float, dict]] = []
        self._last_free_log = 0.0

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
                lap_id = self._queue.get(timeout=QUEUE_WAIT_S)
            except queue.Empty:
                # Nothing asked. Free-running turns the idle wait into a
                # sample; without it the loop simply goes round again.
                lap_id = _FREE_RUN
            if lap_id is None:
                return
            try:
                if lap_id is _FREE_RUN:
                    self._free_run()
                else:
                    self._sample(lap_id)
            except Exception as exc:                         # noqa: BLE001
                # Nothing here may reach the caller. The lap is recorded
                # whatever the gauge does.
                _log.warning(f"hud-wear: unhandled {type(exc).__name__}: {exc}")

    def _free_run(self) -> None:
        """One un-asked-for sample, kept but never filed against a lap."""
        if not self._interval_s or self.stood_down:
            return
        now = time.monotonic()
        if self._latest is not None and now - self._latest[0] < self._interval_s:
            return
        reading, _ = self._read()
        if reading.ok:
            self._keep(now, reading)
        elif now - self._last_free_log > FREE_RUN_LOG_SPACING_S:
            # Sparse, deliberately. A shut projector is one fact, not one fact
            # every two seconds.
            self._last_free_log = now
            _log.warning(f"hud-wear: no free-run reading: {reading.reason}")

    def _read(self) -> tuple[Reading, bool]:
        """Grab and transcribe. Returns (reading, the source itself failed).

        **The two failures are not the same failure and must not be counted
        together.** A source that cannot produce a frame is a connection
        problem - OBS shut, the projector closed - and it is what standing down
        exists for. A frame that arrives and cannot be read is a paused game or
        a menu, which is a normal thing that happens several times a session.
        """
        frame, why = self._source.grab()
        if frame is None:
            return Reading(None, why), True
        return read_gauge(frame), False

    def _keep(self, at: float, reading: Reading) -> None:
        """Hold a good reading, and cut the series where a fresh set went on."""
        worst = max((v for v in reading.wear.values() if v is not None),
                    default=None)
        if worst is not None and self.series:
            previous = max((v for v in self.series[-1][1].values()
                            if v is not None), default=None)
            if previous is not None and previous - worst > FRESH_SET_DROP:
                # The gauge only goes backwards for one reason.
                _log.info(f"hud-wear: fresh set - gauge dropped "
                    f"{previous * 100:.0f}% to {worst * 100:.0f}%")
                self.series = []
        self._latest = (at, reading)
        self.series.append((at, dict(reading.wear)))

    def latest(self) -> Reading | None:
        """The most recent good reading, or None."""
        return self._latest[1] if self._latest else None

    def _sample(self, lap_id: int) -> None:
        now = time.monotonic()
        held = self._latest
        if (self._interval_s
                and held is not None
                and now - held[0] <= self._interval_s + STALE_MARGIN_S):
            # **The last sample before the crossing is this lap reading**, the
            # same rule the offline tool applies to a recorded race. Nothing is
            # grabbed on the crossing at all.
            reading = held[1]
        else:
            reading, source_failed = self._read()
            if source_failed:
                self._failed(f"lap {lap_id}: {reading.reason}")
                return
            if reading.ok:
                self._keep(now, reading)
        if not reading.ok:
            # A dimmed or unreadable frame is not a connection failure - it is
            # a normal thing that happens when the game is paused - so it does
            # not count toward standing down.
            _log.warning(f"hud-wear: lap {lap_id}: {reading.reason}")
            return
        self._failures = 0
        self._write(lap_id, reading.wear)
        worst = max((v for v in reading.wear.values() if v is not None),
                    default=None)
        _log.info(f"hud-wear: lap {lap_id}: "
            + ", ".join(f"{k.upper()} "
                        + ("--" if v is None else f"{v * 100:.0f}%")
                        for k, v in sorted(reading.wear.items()))
            + (f" (worst {worst * 100:.0f}%)" if worst is not None else ""))
        if self._status:
            self._status(reading)

    def _failed(self, message: str) -> None:
        self._failures += 1
        _log.warning(f"hud-wear: {message}")
        if self._failures >= MAX_CONSECUTIVE_FAILURES:
            self.stood_down = True
            _log.warning(f"hud-wear: stood down after {self._failures} consecutive "
                f"failures - it will not be retried this session")
